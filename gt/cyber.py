"""Cyber and routing layer: exploited bugs, ICS advisories, ransomware claims, hacktivist DDoS targets and state-level
BGP visibility. v1.0, 2026-11-20 (Ground Truth 0.13.0).

Two feeds (FEEDS at the bottom). Each poll fetches only the sources that are due; everything else comes from the
cache, so one slow or failing source never blocks or fails the feed (it fails only when no source has ever answered).

`cyber` (every 900 s; state in <GT_DATA>/cache/cyber_state.json):
* cisa_kev, hourly: CISA Known Exploited Vulnerabilities JSON; additions in the last 14 days with the ransomware-use
  flag. 1,786 entries, ~1.3 MB (~205 KB gzipped); newest 2026-11-18 on 11-20.
* cisa_ics + cisa_all, every 30 min: the ICS-advisories and all-advisories RSS (30 items each, ~4 and ~2.5 weeks).
  Each ICS description carries "Critical Infrastructure Sectors", "Countries/Areas Deployed", "Company Headquarters
  Location" and a CVSS table; pubDate has a 2-digit year ("Thu, 19 Nov 26 12:00:00 +0000"). The "CISA Adds N Known
  Exploited Vulnerabilities" and "CISA Releases N ICS Advisories" alerts are dropped (they repeat KEV / ICS items).
* ransomware_live + ransomware_live_press, hourly: ransomware.live API v2 (the keyless legacy endpoint) /recentvictims
  (the last 100 leak-site claims, ~1.5 days) and /recentcyberattacks (100 press-reported attacks, ~10 days). Victims
  are kept 7 days in the cache; when coverage is shorter than 7 days (first run, or a gap) the month list
  /victims/YYYY/MM (~740 KB, keyed by attack date) is fetched once a day, one month per poll. Claims are claims, not
  confirmed breaches. Press country codes are not always ISO ("UK" was Ukraine, "PO" both Poland and Portugal), so
  only valid ISO codes are mapped (plus KO -> KR). Victim names, descriptions (they quote leaked personal data),
  domains, onion links and screenshots are never stored or served: titles name the sector, country and group, and
  link to the ransomware.live entry.
* sans_isc, hourly: SANS Internet Storm Center infocon (green/yellow/orange/red).
* ddosia, hourly: witha.name's copy of the target list NoName057(16) hands its volunteer DDoS bots (~300 rules,
  ~25 hosts, updated about twice a day; 2026-11-20 05:06Z: all Spanish). Hosts are counted per country from their
  country-code TLD (.eus/.gal/.cat -> ES, .uk -> GB); .com and similar stay unattributed. Target IPs are never kept.
  witha.name's Atom feed labels CET times as UTC, so a config's time here is when GT first saw it.

`bgp` (every 900 s; state in <GT_DATA>/cache/cyber_bgp.json): RIPEstat country-resource-stats for 19 watched countries:
IPv4/IPv6 prefixes and ASNs seen by RIPE RIS, by country of registration, hourly for the last 8 days in one ~0.5-3 KB
call (entries with equal values are merged into one entry with several timeline intervals; they are expanded here).
The baseline comes from that history, so there is no warm-up. Data lags 2-3 h (03:00 was newest at 05:45Z).
Countries never fetched are all fetched on the first poll (19 calls); after that up to 7 a poll, those with a drop or
dip first, then the oldest, so each is refreshed about every 45 min (~670 calls a day). Three failures in a row or
90 s end a poll's fetching early.

Drop rule (from 8 days of real data for all 19 countries, 2026-11-12..20): now = median of the last 3 hourly points
(the newest bucket can be partial; single-hour dips go away); base = median of the points from 7 days to 6 hours
before the newest (so an ongoing drop does not drag its own baseline). With that, ordinary noise stayed within
-3.8 % (IPv4) and -4.0 % (ASNs) in every country; the one bigger move was a real Sudan event (-12.4 %, 2 h). So:
* drop: IPv4 prefixes <= -10 % and >= 5 fewer, or ASNs <= -5 % and >= 2 fewer, or no IPv4 prefix left at all;
* dip: IPv4 <= -5 % (>= 5 fewer) or ASNs <= -2.5 % (>= 2 fewer);
* IPv6 is shown but never flags: at small counts it swings 25-33 % in a normal week (ET 3 -> 2, AF 15 -> 10);
* stale: the newest point is more than 12 h old (no flag).
The absolute minimums keep 1-prefix wobbles in tiny networks (KP 4 prefixes / 1 ASN, CU, YE) quiet; their total
blackout still flags. IODA (feed `outages`) already watches BGP, probing and darknet signals for outage *events*;
this feed is the always-on routing table behind them.

Not used (checked 2026-11-20): abuse.ch Feodo Tracker (CC0, keyless, but 5 C2 entries, 1 online, file unchanged
since 2026-06-30: no c2 count per country); URLhaus and ThreatFox (Auth-Key required, exports 410 Gone); Cloudflare
Radar (API token required: needs the owner's key); the Kyiv power-outage API (503 behind Incapsula).

Terms: CISA KEV is CC0 1.0 and CISA advisories are US Government public domain. Ransomware.live: free for
non-commercial use with "Source: Ransomware.live" linked on any page that shows it; no polling faster than its
30-minute cache; no republishing of its raw data or re-serving it as an API/feed; the keyless v2 API is "personal
use only". SANS ISC: CC BY-NC-SA 4.0, do not resell; it asks for contact details in the User-Agent, which GT does
not send (house rule). witha.name: no stated licence ("sharing is caring"). RIPEstat: network analysis, monitoring
and research use; no re-packaging or re-distribution of its data; no commercial use without RIPE NCC permission.
So both feeds are non-commercial (never for the trading agent) and private (not for the public mirror).
"""
import datetime as dt
import email.utils
import gzip
import hashlib
import json
import os
import re
import statistics
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import geo

VERSION = "1.0"
UA = "GroundTruth/0.13 (personal non-commercial OSINT dashboard)"
TIMEOUT = 30
MAX_BODY = 8 * 1024 * 1024

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CISA_ICS_URL = "https://www.cisa.gov/cybersecurity-advisories/ics-advisories.xml"
CISA_ALL_URL = "https://www.cisa.gov/cybersecurity-advisories/all.xml"
RWL_API = "https://api.ransomware.live/v2"
RWL_RECENT_URL = RWL_API + "/recentvictims"
RWL_MONTH_URL = RWL_API + "/victims/%04d/%02d"
RWL_PRESS_URL = RWL_API + "/recentcyberattacks"
ISC_INFOCON_URL = "https://isc.sans.edu/api/infocon?json"
DDOSIA_URL = "https://witha.name/data/last.json"
RIPE_URL = "https://stat.ripe.net/data/country-resource-stats/data.json"
NVD_URL = "https://nvd.nist.gov/vuln/detail/"

ATTRIBUTION = {
    "cisa_kev": "CISA Known Exploited Vulnerabilities Catalog (CC0 1.0)",
    "cisa_ics": "CISA ICS advisories (US Government public domain)",
    "cisa_all": "CISA cybersecurity advisories (US Government public domain)",
    "ransomware_live": "Source: Ransomware.live",
    "ransomware_live_press": "Source: Ransomware.live",
    "sans_isc": "SANS Internet Storm Center (CC BY-NC-SA 4.0)",
    "ddosia": "witha.name DDoSia configuration tracker",
    "ripestat": "RIPEstat, RIPE NCC (RIS routing data)",
}
ATTRIBUTION_URL = {
    "cisa_kev": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
    "cisa_ics": "https://www.cisa.gov/news-events/cybersecurity-advisories",
    "cisa_all": "https://www.cisa.gov/news-events/cybersecurity-advisories",
    "ransomware_live": "https://www.ransomware.live",
    "ransomware_live_press": "https://www.ransomware.live",
    "sans_isc": "https://isc.sans.edu",
    "ddosia": "https://witha.name",
    "ripestat": "https://stat.ripe.net",
}
LICENCE = {
    "cyber": ("Mixed. CISA KEV CC0 and CISA advisories public domain; Ransomware.live non-commercial only, named and "
              "linked on the page, no raw-data republishing, polled no faster than 30 min; SANS ISC CC BY-NC-SA 4.0; "
              "witha.name no stated licence. Private page only; never for the trading agent."),
    "bgp": ("RIPEstat terms: network analysis, monitoring and research use; no re-packaging or re-distribution of the "
            "data; no commercial use without RIPE NCC permission. Private page only; never for the trading agent."),
}
NON_COMMERCIAL = {"cyber": True, "bgp": True}    # Ransomware.live + SANS ISC (NC); RIPEstat (no commercial use)
PUBLIC_OK = {"cyber": False, "bgp": False}       # Ransomware.live "no raw data publishing"; RIPEstat "no re-distribution"
NOTE = {
    "cyber": ("Ransomware entries are claims posted on gangs' leak sites, not confirmed breaches. ci = critical "
              "infrastructure: energy/utilities, water, healthcare, government, defence, transport, telecoms, "
              "emergency services, nuclear, dams, chemical (manufacturing, finance and IT are not counted). Press "
              "items are flagged from keywords. DDoSia hosts are NoName057(16)'s current DDoS target list, placed "
              "by country-code domain."),
    "bgp": ("Prefixes and ASNs registered to each country and seen in global routing by RIPE RIS, hourly, 2-3 h "
            "behind. now = median of the last 3 hours; base = median from 7 days to 6 hours before. drop: IPv4 "
            "prefixes -10 % (and 5+) or ASNs -5 % (and 2+); dip: half that. IPv6 never flags. A routing drop means "
            "networks disappeared from the internet; outages without routing changes show in the outages feed."),
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")           # the same folder as feeds.CACHE
STATE_FILE = "cyber_state.json"
BGP_FILE = "cyber_bgp.json"

# cyber windows and caps
KEV_DAYS = 14
CISA_DAYS = 14
RANSOM_DAYS = 7
PRESS_DAYS = 7
DDOS_DAYS = 7
MAX_ITEMS = 400
MAX_BYTES = 300 * 1000
SLACK = 60                    # s: a source due in under a minute is fetched now, so 900 s polls don't drift a slot
BOOT_EVERY = 86400            # s: at most one ransomware.live month bootstrap attempt per month per day
SUMMARY_MAX = 700
DDOS_NOW_MAX_AGE = 6 * 3600   # s: an older DDoSia list is no longer "now"

VICTIM_NAMES = False          # never store ransomware victims' names (privacy; Ransomware.live raw-data rule)

CI_TAGS = ("energy", "water", "healthcare", "government", "defense", "transport", "comms", "emergency", "nuclear",
           "dams", "chemical")
# (tag, regex) for CISA sector lists and ransomware.live activities ("Hospitality" is not healthcare)
SECTOR_WORDS = (
    ("energy", r"\benergy|\butilit|\boil\b|\bgas\b|\belectric|\bpower\b"),
    ("water", r"\bwater|\bwastewater"),
    ("healthcare", r"\bhealth|\bhospitals?\b|\bmedical|\bpharma"),
    ("government", r"\bgovernment|\bpublic sector|\bpublic administration"),
    ("defense", r"\bdefen[cs]e|\bmilitary"),
    ("transport", r"\btransport|\blogistic|\baviation|\bmaritime|\bshipping"),
    ("comms", r"\bcommunications|\btelecom"),
    ("emergency", r"\bemergency"),
    ("nuclear", r"\bnuclear"),
    ("dams", r"\bdams\b"),
    ("chemical", r"\bchemical"),
    ("manufacturing", r"manufactur"),
    ("it", r"\binformation technology|\btechnology"),
    ("financial", r"\bfinanc|\bbank|\binsurance"),
    ("food-ag", r"\bfood|\bagricultur"),
    ("education", r"\beducation"),
    ("commercial", r"\bcommercial facilities"),
)
_SECTOR_RX = [(t, re.compile(p, re.I)) for t, p in SECTOR_WORDS]
# press headlines (many languages): keyword guesses at a critical-infrastructure victim
PRESS_WORDS = (
    ("healthcare", r"\bhospitals?\b|\bclinics?\b|\bhealth|\bmedical\b|\bpatients?\b|h[oô]pital|krankenhaus|klinik"
                   r"|ospedal|szpital|больниц|병원|医院"),
    ("energy", r"\benergy\b|\belectricity\b|\bpower (?:grid|plant|company|utility)|\bgrid operator|\bpipeline"
               r"|\boil\b|\bgas (?:company|supplier|utility)|[ée]nergie|энерг"),
    ("water", r"\bwater (?:utility|company|supplier|authority|board)|\bwastewater|водоканал"),
    ("transport", r"\bairports?\b|\bairlines?\b|\brailways?\b|\brail operator|\bmetro\b|\bport of\b|\btransit\b"
                  r"|a[ée]roport|flughafen|аэропорт|железн"),
    ("comms", r"\btelecoms?\b|\btelecommunications?\b|\bmobile operator|t[ée]l[ée]com"),
    ("government", r"\bgovernment\b|\bministry\b|\bmunicipal|\bcity of\b|\bcity council|\bcounty\b|\bparliament"
                   r"|\bagency\b|minist[eè]re|\bmairie\b|ayuntamiento|gobierno|regierung|министерств|госуслуг|ePUAP"),
    ("defense", r"\bdefen[cs]e\b|\bmilitary\b|\barmy\b|\bnavy\b|\barmed forces\b|военн"),
)
_PRESS_RX = [(t, re.compile(p, re.I)) for t, p in PRESS_WORDS]
PRESS_A2_FIX = {"KO": "KR"}                # ransomware.live press codes seen 2026-11-20; UK/PO/SW are ambiguous
ACTOR_WORDS = (("CHN", r"\b(?:PRC|China|Chinese)\b"), ("RUS", r"\bRussia(?:n)?\b"), ("IRN", r"\bIran(?:ian)?\b"),
               ("PRK", r"\b(?:North Korea(?:n)?|DPRK)\b"))
_ACTOR_RX = [(a, re.compile(p)) for a, p in ACTOR_WORDS]
CISA_SKIP = re.compile(r"^CISA (?:Adds .* Known Exploited Vulnerabilit|Releases .* (?:Industrial Control|ICS))", re.I)
_RX_SECT = re.compile(r"Critical Infrastructure Sectors?:\s*(?:</strong>)?\s*([^<]+)", re.I)
_RX_DEPL = re.compile(r"Countries/Areas Deployed:\s*(?:</strong>)?\s*([^<]+)", re.I)
_RX_HQ = re.compile(r"Company Headquarters Location:\s*(?:</strong>)?\s*([^<]+)", re.I)
_RX_CVSS = re.compile(r"<td>\s*v[234](?:\.\d)?\s+(\d{1,2}(?:\.\d)?)\s*</td>", re.I)
_RX_TAG = re.compile(r"(?s)<[^>]+>")

# DDoSia hostnames -> country by country-code TLD
TLD_A2 = {"uk": "GB", "eus": "ES", "gal": "ES", "cat": "ES", "su": "RU"}
TLD_GENERIC = {"io", "co", "tv", "me", "ai", "ly", "fm", "to", "cc", "ws", "gg", "eu", "app"}
_RX_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}\.)+[a-z][a-z0-9-]{1,62}$")

# bgp
WATCH = ("UA", "RU", "BY", "IR", "IL", "PS", "LB", "SY", "YE", "IQ", "SD", "ET", "MM", "VE", "CU", "TW", "KP", "PK",
         "AF")
SERIES_DAYS = 8
BASE_DAYS = 7
BASE_SKIP_H = 6
NOW_POINTS = 3
MIN_BASE_POINTS = 24
DROP_V4_PCT, DROP_ASN_PCT = -10.0, -5.0
DIP_V4_PCT, DIP_ASN_PCT = -5.0, -2.5
MIN_V4_ABS, MIN_ASN_ABS = 5, 2
STALE_H = 12
SPARK_STEP_H = 3
BGP_PER_POLL = 7
BGP_MAX_PER_POLL = 20
BGP_MIN_AGE = 600
BGP_MAX_FAILS = 3
BGP_TIME_BUDGET = 90
LEVEL_ORDER = {"drop": 0, "dip": 1, "stale": 2, "ok": 3, "pending": 4}


# ---------------- helpers ----------------

def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError("response over %d bytes" % MAX_BODY)
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)
    return body


def _utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


def _iso(t):
    return dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_RX_TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")


def _ts(s):
    """Epoch seconds for 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM[:SS[.ffff]][Z|+HH:MM]' (naive = UTC), or None."""
    if not s or not isinstance(s, str):
        return None
    m = _RX_TS.match(s.strip())
    if not m:
        return None
    y, mo, d, h, mi, sec, tz = m.groups()
    try:
        t = dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(sec or 0), tzinfo=dt.timezone.utc)
    except ValueError:
        return None
    off = 0
    if tz and tz != "Z":
        tz = tz.replace(":", "")
        off = (1 if tz[0] == "+" else -1) * (int(tz[1:3]) * 3600 + int(tz[3:5]) * 60)
    return int(t.timestamp()) - off


def _rfc822(s):
    try:
        t = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        return None
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return int(t.timestamp())


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _err(e):
    return _clip("%s: %s" % (type(e).__name__, e), 200)


def _sha(s, n=12):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


_A3 = {}


def _a3(a2):
    """a3 for an ISO 3166 alpha-2 code, else None (cached)."""
    if not a2 or not isinstance(a2, str) or not re.match(r"^[A-Za-z]{2}$", a2.strip()):
        return None
    a2 = a2.strip().upper()
    if a2 not in _A3:
        _A3[a2] = geo.a3_for_a2(a2)
    return _A3[a2]


def _a2(code):
    """Normalised alpha-2 if it maps to a country, else None."""
    return code.strip().upper() if _a3(code) else None


def _cname(a3):
    return (geo.country_shapes().get(a3) or {}).get("name") or a3


def _a3s_for_names(text):
    found = []
    for part in re.split(r",|;|\band\b|/", text or ""):
        for a3 in geo.a3s_for_name(part.strip()):
            if a3 not in found:
                found.append(a3)
    return found


def sector_tags(text):
    return [tag for tag, rx in _SECTOR_RX if rx.search(text or "")]


def is_ci(tags):
    return any(t in CI_TAGS for t in tags or ())


def ci_tag(tags):
    """The first critical-infrastructure tag ("Government & Defense" -> government), or None."""
    return next((t for t in tags or () if t in CI_TAGS), None)


def _path(name):
    return os.path.join(CACHE, name)


def _load(name):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(name, obj):
    os.makedirs(CACHE, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    os.replace(tmp, _path(name))


def _item(iid, kind, title, url, t, countries, sector, tags, **extra):
    it = {"id": iid, "kind": kind, "title": _clip(title, 240), "url": url, "ts_ms": int(t) * 1000, "ts": _iso(t),
          "countries": countries, "sector": sector, "tags": tags}
    it.update(extra)
    return it


# ---------------- parsers ----------------

def parse_kev(body, now):
    """KEV additions in the last KEV_DAYS days -> {"items", "catalog"}."""
    d = json.loads(body)
    if not isinstance(d, dict) or not isinstance(d.get("vulnerabilities"), list):
        raise ValueError("KEV: no vulnerabilities list")
    cut = now.date() - dt.timedelta(days=KEV_DAYS)
    items = []
    for v in d["vulnerabilities"]:
        if not isinstance(v, dict):
            continue
        cve, t = str(v.get("cveID") or ""), _ts(str(v.get("dateAdded") or "")[:10])
        if not cve.startswith("CVE-") or t is None or dt.datetime.fromtimestamp(t, dt.timezone.utc).date() < cut:
            continue
        ransom = str(v.get("knownRansomwareCampaignUse") or "").lower() == "known"
        items.append(_item("kev:" + cve, "kev", "%s %s" % (cve, v.get("vulnerabilityName") or ""), NVD_URL + cve, t,
                           [], None, ["kev"] + (["ransomware"] if ransom else []), ci=False,
                           vendor=_clip(v.get("vendorProject"), 60), product=_clip(v.get("product"), 80),
                           due=str(v.get("dueDate") or "")[:10] or None, ransomware=ransom))
    items.sort(key=lambda i: (-i["ts_ms"], i["id"]))
    return {"items": items, "catalog": {"version": d.get("catalogVersion"), "released": d.get("dateReleased"),
                                        "count": d.get("count")}}


def _cisa_kind(link):
    p = urllib.parse.urlsplit(link or "").path
    if "/ics-medical-advisories/" in p:
        return "ics", ["medical"]
    if "/ics-advisories/" in p:
        return "ics", []
    if "/cybersecurity-advisories/" in p:
        slug = p.rstrip("/").rsplit("/", 1)[-1].lower()
        return "cisa", ["advisory"] + (["joint"] if slug.startswith("aa") else [])
    if "/alerts/" in p:
        return "cisa", ["alert"]
    if "/analysis-reports/" in p:
        return "cisa", ["analysis"]
    if "/resources-tools/" in p:
        return "cisa", ["guidance"]
    return "cisa", []


def parse_cisa_rss(body):
    """CISA advisory RSS -> items (all of them; the 14-day window is applied when the feed is built)."""
    root = ET.fromstring(body)
    ch = root.find("channel")
    if ch is None:
        raise ValueError("CISA RSS: no channel")
    out = []
    for it in ch.findall("item"):
        title, link = _clip(it.findtext("title"), 200), (it.findtext("link") or "").strip()
        t = _rfc822(it.findtext("pubDate") or "")
        if not title or not link.startswith("https://") or t is None or CISA_SKIP.match(title):
            continue
        desc = it.findtext("description") or ""
        kind, tags = _cisa_kind(link)
        m = _RX_SECT.search(desc)
        sector = _clip(m.group(1), 200) if m else None
        stags = sector_tags(sector) + (["healthcare"] if "medical" in tags and "healthcare" not in sector_tags(sector)
                                       else [])
        dep = _RX_DEPL.search(desc)
        deployed = _clip(dep.group(1), 120) if dep else None
        countries = [] if not deployed or "worldwide" in deployed.lower() else _a3s_for_names(deployed)
        hq = _RX_HQ.search(desc)
        hq3 = (_a3s_for_names(_clip(hq.group(1), 80)) or [None])[0] if hq else None
        cvss = [float(x) for x in _RX_CVSS.findall(desc)]
        actors = [a for a, rx in _ACTOR_RX if rx.search(title)] if kind == "cisa" else []
        tags = tags + stags + ["actor:" + a for a in actors]
        if cvss and max(cvss) >= 9.0:
            tags.append("cvss9")
        slug = urllib.parse.urlsplit(link).path.rstrip("/").rsplit("/", 1)[-1]
        out.append(_item("cisa:" + slug, kind, title, link, t, countries, sector, tags, ci=is_ci(stags),
                         cvss=max(cvss) if cvss else None, hq=hq3, deployed=deployed))
    return out


def parse_rwl_victims(body):
    """ransomware.live victim records -> minimal records (no names, descriptions, domains, onion links)."""
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("ransomware.live: expected a list, got %s" % type(rows).__name__)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "")
        disc = _ts(r.get("discovered")) or _ts(r.get("attackdate"))
        if not url or disc is None:
            continue
        act = _clip(r.get("activity"), 60)
        rec = {"id": "rwl:" + _sha(url), "group": _clip(r.get("group"), 40) or None, "a2": _a2(r.get("country")),
               "sector": None if act.lower() in ("", "not found", "unknown", "n/a") else act, "disc": disc,
               "attack": _ts(r.get("attackdate")),
               "url": url if url.startswith("https://www.ransomware.live/") else None}
        if VICTIM_NAMES:
            rec["name"] = _clip(r.get("victim"), 80)
        out.append(rec)
    return out


def _press_tags(text):
    return [t for t, rx in _PRESS_RX if rx.search(text or "")]


def parse_rwl_press(body):
    """ransomware.live press-reported cyberattacks -> items (headline + link; no summaries)."""
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("ransomware.live press: expected a list, got %s" % type(rows).__name__)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or r.get("link") or "")
        t = _ts(str(r.get("added") or "")) or _ts(str(r.get("date") or ""))
        title = r.get("title") or r.get("victim")
        if not url.startswith("http") or t is None or not title:
            continue
        code = str(r.get("country") or "").strip().upper()
        a3 = _a3(PRESS_A2_FIX.get(code, code))
        tags = _press_tags("%s %s" % (title, r.get("victim") or ""))
        rwl = str(r.get("link") or "")
        gang = _clip(r.get("claim_gang"), 40) or None
        out.append(_item("rwlp:" + _sha(url), "attack", title, url, t, [a3] if a3 else [], tags[0] if tags else None,
                         ["press"] + tags + (["claimed"] if gang else []), ci=is_ci(tags), ci_basis="keywords",
                         claimed_by=gang, incident_date=str(r.get("date") or "")[:10] or None,
                         rwl=rwl if rwl.startswith("https://www.ransomware.live/") else None,
                         claim=str(r.get("claim_url") or "") if str(r.get("claim_url") or "").startswith(
                             "https://www.ransomware.live/") else None))
    return out


def parse_infocon(body):
    d = json.loads(body)
    lvl = str((d or {}).get("status") or "").strip().lower() if isinstance(d, dict) else ""
    if lvl not in ("green", "yellow", "orange", "red"):
        raise ValueError("ISC infocon: unexpected status %r" % lvl[:20])
    return {"level": lvl}


def host_a2(host):
    tld = host.rsplit(".", 1)[-1]
    if tld in TLD_A2:
        return TLD_A2[tld]
    if len(tld) == 2 and tld not in TLD_GENERIC:
        return _a2(tld)
    return None


def parse_ddosia(body):
    """DDoSia config -> {"rules", "hosts"}: unique target hostnames only (IP literals and IPs dropped)."""
    d = json.loads(body)
    if not isinstance(d, dict) or not isinstance(d.get("targets"), list):
        raise ValueError("DDoSia: no targets list")
    hosts = set()
    for t in d["targets"]:
        h = str((t or {}).get("host") or "").strip().lower().rstrip(".") if isinstance(t, dict) else ""
        if _RX_HOST.match(h) and not re.match(r"^[\d.]+$", h):
            hosts.add(h)
    return {"rules": len(d["targets"]), "hosts": sorted(hosts)}


# ---------------- cyber sources (each returns its new cached state) ----------------

def _src_kev(fetch, now, prev):
    return parse_kev(fetch(KEV_URL), now)


def _src_ics(fetch, now, prev):
    return {"items": parse_cisa_rss(fetch(CISA_ICS_URL))}


def _src_all(fetch, now, prev):
    return {"items": parse_cisa_rss(fetch(CISA_ALL_URL))}


def _months(now, days):
    out, d = [], now.date() - dt.timedelta(days=days)
    while d <= now.date():
        ym = (d.year, d.month)
        if ym not in out:
            out.append(ym)
        d += dt.timedelta(days=1)
    return out


def _src_rwl(fetch, now, prev):
    """Merge the newest 100 claims into a 7-day store; bootstrap from the month list while coverage is short."""
    nt = int(now.timestamp())
    store = dict(prev or {})
    vic = dict(store.get("v") or {})
    batch = parse_rwl_victims(fetch(RWL_RECENT_URL))
    if not batch:
        raise ValueError("ransomware.live: no victims in /recentvictims")
    newest_stored = max((r["disc"] for r in vic.values()), default=None)
    oldest_batch = min(r["disc"] for r in batch)
    cover = store.get("cover_from")
    if cover is None or (newest_stored is not None and oldest_batch > newest_stored):
        cover = oldest_batch               # first run, or a gap: coverage restarts at this batch
    for r in batch:
        vic[r["id"]] = r
    cut = nt - RANSOM_DAYS * 86400
    boot = {k: dict(v) for k, v in (store.get("boot") or {}).items() if isinstance(v, dict)}
    boot_error = store.get("boot_error")
    if cover > cut + 3600:
        months = ["%04d-%02d" % ym for ym in _months(now, RANSOM_DAYS)]
        due = [m for m in months if nt - boot.get(m, {}).get("t", 0) >= BOOT_EVERY]
        if due:
            m = due[0]                     # one month per poll (the API allows 1 call a minute per endpoint)
            boot[m] = dict(boot.get(m, {}), t=nt)
            try:
                for r in parse_rwl_victims(fetch(RWL_MONTH_URL % (int(m[:4]), int(m[5:])))):
                    if r["disc"] >= cut:
                        vic.setdefault(r["id"], r)
                boot[m]["ok"] = nt
                boot_error = None
            except Exception as e:  # the recent list still counts
                boot_error = _err(e)
        if all(nt - boot.get(m, {}).get("ok", 0) < BOOT_EVERY for m in months):
            cover = cut
    vic = {k: r for k, r in vic.items() if r["disc"] >= cut}
    return {"v": vic, "cover_from": max(cover, cut), "boot": boot, "boot_error": boot_error}


def _src_press(fetch, now, prev):
    items = parse_rwl_press(fetch(RWL_PRESS_URL))
    if not items:
        raise ValueError("ransomware.live: no items in /recentcyberattacks")
    return {"items": items}


def _src_isc(fetch, now, prev):
    return parse_infocon(fetch(ISC_INFOCON_URL))


def _src_ddosia(fetch, now, prev):
    nt = int(now.timestamp())
    cfg = parse_ddosia(fetch(DDOSIA_URL))
    st = dict(prev or {})
    hosts = dict(st.get("hosts") or {})
    for h in cfg["hosts"]:
        rec = hosts.get(h) or {"a2": host_a2(h), "first": nt}
        rec["last"] = nt
        hosts[h] = rec
    sig = _sha("\n".join(cfg["hosts"]), 16)
    configs = list(st.get("configs") or [])
    if not configs or configs[-1]["sig"] != sig:
        by = {}
        for h in cfg["hosts"]:
            k = hosts[h]["a2"] or "?"
            by[k] = by.get(k, 0) + 1
        configs.append({"t": nt, "sig": sig, "rules": cfg["rules"], "hosts": len(cfg["hosts"]), "by_a2": by,
                        "sample": cfg["hosts"][:12]})
    cut = nt - DDOS_DAYS * 86400
    return {"hosts": {h: r for h, r in hosts.items() if r["last"] >= cut},
            "configs": [c for c in configs if c["t"] >= cut] or configs[-1:], "current": cfg["hosts"],
            "rules": cfg["rules"]}


# name: (function, refresh seconds, retry seconds after a failure)
CYBER_SOURCES = (
    ("cisa_kev", _src_kev, 3600, 900),
    ("cisa_ics", _src_ics, 1800, 900),
    ("cisa_all", _src_all, 1800, 900),
    ("ransomware_live", _src_rwl, 3600, 1800 + SLACK),  # never under 30 min (Ransomware.live fair use)
    ("ransomware_live_press", _src_press, 3600, 1800 + SLACK),
    ("sans_isc", _src_isc, 3600, 900),
    ("ddosia", _src_ddosia, 3600, 900),
)


# ---------------- the cyber feed ----------------

def _ransom_items(store):
    out = []
    for r in (store or {}).get("v", {}).values():
        a3 = _a3(r.get("a2"))
        tags = sector_tags(r.get("sector"))
        where = _cname(a3) if a3 else "unknown country"
        what = ("%s victim" % r["sector"]) if r.get("sector") else "victim (sector unknown)"
        title = "Ransomware claim: %s in %s (%s)" % (what, where, r.get("group") or "unknown group")
        if VICTIM_NAMES and r.get("name"):
            title = "Ransomware claim: %s, %s, %s (%s)" % (r["name"], r.get("sector") or "sector unknown", where,
                                                            r.get("group") or "unknown group")
        out.append(_item(r["id"], "ransom", title, r.get("url") or ATTRIBUTION_URL["ransomware_live"], r["disc"],
                         [a3] if a3 else [], r.get("sector"), ["ransomware"] + tags, ci=is_ci(tags),
                         group=r.get("group")))
    return out


def _ddos_items(st):
    out = []
    for c in (st or {}).get("configs") or []:
        by = sorted(((k, n) for k, n in (c.get("by_a2") or {}).items() if k != "?"), key=lambda x: (-x[1], x[0]))
        a3s = [a for a in (_a3(k) for k, n in by) if a]
        where = ", ".join("%s %d" % (_cname(_a3(k)), n) for k, n in by[:3]) or "no country-code hosts"
        out.append(_item("ddos:" + c["sig"], "ddos", "DDoSia (NoName057(16)) target list: %d hosts (%s)" % (
            c["hosts"], where), ATTRIBUTION_URL["ddosia"], c["t"], a3s, None, ["ddos", "hacktivist"], ci=False,
            hosts=c.get("sample") or [], rules=c.get("rules")))
    return out


def _cap(items, max_items=MAX_ITEMS):
    """Newest-first items -> (kept, dropped): within max_items and MAX_BYTES, dropping non-CI ransomware claims
    first, then non-CI press items, then anything, oldest first."""
    sizes = {id(i): len(json.dumps(i, separators=(",", ":"), ensure_ascii=False).encode()) + 1 for i in items}
    total = sum(sizes.values())
    budget = MAX_BYTES - 40000       # room for by_country, sources and the rest
    order = sorted(items, key=lambda i: (0 if i["kind"] == "ransom" and not i.get("ci") else
                                         1 if i["kind"] == "attack" and not i.get("ci") else 2, i["ts_ms"]))
    drop, n = set(), len(items)
    for i in order:
        if n <= max_items and total <= budget:
            break
        drop.add(id(i))
        n -= 1
        total -= sizes[id(i)]
    return [i for i in items if id(i) not in drop], len(drop)


def _by_country(ransom, press, ddos, nt):
    by, unk = {}, {"ransom_7d": 0, "ransom_ci_7d": 0, "attacks_7d": 0, "ddos_7d": 0}

    def row(a3):
        return by.setdefault(a3, {"ransom_7d": 0, "ransom_ci_7d": 0, "ransom_24h": 0, "attacks_7d": 0,
                                  "attacks_ci_7d": 0, "ddos_now": 0, "ddos_7d": 0, "ci_sectors": {}, "groups": {}})
    for r in (ransom or {}).get("v", {}).values():
        a3 = _a3(r.get("a2"))
        t = ci_tag(sector_tags(r.get("sector")))
        if not a3:
            unk["ransom_7d"] += 1
            unk["ransom_ci_7d"] += bool(t)
            continue
        c = row(a3)
        c["ransom_7d"] += 1
        c["ransom_24h"] += r["disc"] >= nt - 86400
        if t:
            c["ransom_ci_7d"] += 1
            c["ci_sectors"][t] = c["ci_sectors"].get(t, 0) + 1
        if r.get("group"):
            c["groups"][r["group"]] = c["groups"].get(r["group"], 0) + 1
    for i in press:
        if not i["countries"]:
            unk["attacks_7d"] += 1
        for a3 in i["countries"]:
            c = row(a3)
            c["attacks_7d"] += 1
            c["attacks_ci_7d"] += bool(i.get("ci"))
    cur = set((ddos or {}).get("current") or [])
    for h, r in ((ddos or {}).get("hosts") or {}).items():
        a3 = _a3(r.get("a2"))
        if not a3:
            unk["ddos_7d"] += 1
            continue
        c = row(a3)
        c["ddos_7d"] += 1
        c["ddos_now"] += h in cur
    for c in by.values():
        c["groups"] = [g for g, n in sorted(c["groups"].items(), key=lambda x: (-x[1], x[0]))[:3]]
    return by, unk


def _summary(items, by, unk, infocon, kev_items, cisa_items, ddos, rstore, nt):
    parts = []
    if infocon:
        parts.append("ISC infocon %s." % infocon)
    recs = list((rstore or {}).get("v", {}).values())
    cover_from = (rstore or {}).get("cover_from")
    r7 = len(recs)
    sect = {}
    for r in recs:
        t = ci_tag(sector_tags(r.get("sector")))
        if t:
            sect[t] = sect.get(t, 0) + 1
    ci7 = sum(sect.values())
    if r7:
        top = sorted(by.items(), key=lambda x: (-x[1]["ransom_7d"], x[0]))[:3]
        s = "Ransomware claims 7 d: %d (%d critical infrastructure%s); most %s." % (
            r7, ci7, (": " + ", ".join("%s %d" % (t, n) for t, n in sorted(sect.items(), key=lambda x: (-x[1], x[0]))
                                       [:4])) if sect else "",
            ", ".join("%s %d" % (a3, c["ransom_7d"]) for a3, c in top if c["ransom_7d"]))
        if cover_from and cover_from > nt - RANSOM_DAYS * 86400 + 3600:
            s += " (counted since %s)" % _iso(cover_from)[:16].replace("T", " ")
        parts.append(s)
    press = [i for i in items if i["kind"] == "attack"]
    if press:
        parts.append("Press-reported attacks 7 d: %d (%d CI)." % (len(press), sum(1 for i in press if i.get("ci"))))
    if kev_items:
        parts.append("KEV: %d added in 14 d (%d ransomware-linked), newest %s." % (
            len(kev_items), sum(1 for i in kev_items if i.get("ransomware")), kev_items[0]["ts"][:10]))
    ics = [i for i in cisa_items if i["kind"] == "ics"]
    if ics:
        sect = {}
        for i in ics:
            for t in i["tags"]:
                if t in CI_TAGS:
                    sect[t] = sect.get(t, 0) + 1
        parts.append("CISA ICS advisories 14 d: %d%s." % (len(ics), (" (" + ", ".join(
            "%s %d" % (t, n) for t, n in sorted(sect.items(), key=lambda x: (-x[1], x[0]))[:3]) + ")") if sect else ""))
    cur = (ddos or {}).get("current") or []
    if cur:
        by_now = {}
        for h in cur:
            k = (ddos["hosts"].get(h) or {}).get("a2") or "other domains"
            by_now[k] = by_now.get(k, 0) + 1
        parts.append("DDoSia targets now: %d hosts (%s)." % (len(cur), ", ".join(
            "%s %d" % (k, n) for k, n in sorted(by_now.items(), key=lambda x: (-x[1], x[0]))[:3])))
    return _clip(" ".join(parts), SUMMARY_MAX)


def _newest(ts_list):
    ts_list = [t for t in ts_list if t]
    return _iso(max(ts_list)) if ts_list else None


def cyber(now=None, fetch=None):
    """The `cyber` feed: KEV, CISA advisories, ransomware claims and press attacks, ISC infocon, DDoSia targets."""
    now, fetch = _utc(now), fetch or _fetch
    nt = int(now.timestamp())
    state = _load(STATE_FILE)
    srcs = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    for name, fn, every, retry in CYBER_SOURCES:
        s = srcs.get(name) if isinstance(srcs.get(name), dict) else {}
        wait = every if s.get("ok") else retry
        if s.get("t") and nt - s["t"] < wait - SLACK:
            srcs[name] = s
            continue
        try:
            s["data"] = fn(fetch, now, s.get("data"))
            s.update(ok=True, error=None, good=nt)
        except Exception as e:
            s.update(ok=False, error=_err(e))
        s["t"] = nt
        srcs[name] = s
    state = {"version": VERSION, "sources": srcs}
    _save(STATE_FILE, state)
    if not any(s.get("good") for s in srcs.values()):
        raise RuntimeError("cyber: no source has answered yet: " + "; ".join(
            "%s %s" % (n, s.get("error")) for n, s in sorted(srcs.items())))

    d = {n: (srcs.get(n) or {}).get("data") for n, _, _, _ in CYBER_SOURCES}
    kev_from = (now.date() - dt.timedelta(days=KEV_DAYS)).isoformat()
    kev = [i for i in (d["cisa_kev"] or {}).get("items") or [] if i["ts"][:10] >= kev_from]
    cisa = {}
    for n in ("cisa_ics", "cisa_all"):
        for i in (d[n] or {}).get("items") or []:
            if i["ts_ms"] >= (nt - CISA_DAYS * 86400) * 1000:
                cisa.setdefault(i["id"], i)
    cisa = sorted(cisa.values(), key=lambda i: (-i["ts_ms"], i["id"]))
    rstore = d["ransomware_live"] or {}
    rcut = nt - RANSOM_DAYS * 86400
    rstore = dict(rstore, v={k: r for k, r in (rstore.get("v") or {}).items() if r["disc"] >= rcut})
    ransom = _ransom_items(rstore)
    press = [i for i in (d["ransomware_live_press"] or {}).get("items") or []
             if i["ts_ms"] >= (nt - PRESS_DAYS * 86400) * 1000]
    claimed = {i.get("claim") for i in press if i.get("claim")}
    for i in ransom:
        if i["url"] in claimed:
            i["tags"].append("press")
    ddos = d["ddosia"] or {}
    ddos = dict(ddos, configs=[c for c in ddos.get("configs") or [] if c["t"] >= nt - DDOS_DAYS * 86400],
                hosts={h: r for h, r in (ddos.get("hosts") or {}).items() if r["last"] >= nt - DDOS_DAYS * 86400})
    if not ddos["hosts"] or nt - ((srcs.get("ddosia") or {}).get("good") or 0) > DDOS_NOW_MAX_AGE:
        ddos["current"] = []
    ddi = _ddos_items(ddos)
    items = sorted(kev + cisa + ransom + press + ddi, key=lambda i: (-i["ts_ms"], i["kind"], i["id"]))
    full = list(items)
    items, trimmed = _cap(items)
    by, unk = _by_country(rstore, press, ddos, nt)
    infocon = (d["sans_isc"] or {}).get("level")
    isc_good = (srcs.get("sans_isc") or {}).get("good")

    per = {"cisa_kev": kev, "cisa_ics": [i for i in cisa if i["kind"] == "ics"],
           "cisa_all": [i for i in cisa if i["kind"] != "ics"], "ransomware_live": ransom,
           "ransomware_live_press": press, "ddosia": ddi}
    sources = []
    for name, _, _, _ in CYBER_SOURCES:
        s = srcs.get(name) or {}
        row = {"name": name, "ok": bool(s.get("ok")), "error": s.get("error"),
               "newest": _newest([i["ts_ms"] // 1000 for i in per.get(name, [])]), "n": len(per.get(name, [])),
               "checked": _iso(s["t"]) if s.get("t") else None, "good": _iso(s["good"]) if s.get("good") else None}
        if name == "sans_isc":
            row.update(n=1 if infocon else 0, newest=row["good"])
        if name == "ransomware_live":
            row["cover_from"] = _iso(rstore["cover_from"]) if rstore.get("cover_from") else None
            if rstore.get("boot_error"):
                row["boot_error"] = rstore["boot_error"]
        sources.append(row)
    names = []
    for name, _, _, _ in CYBER_SOURCES:
        if ATTRIBUTION[name] not in names:
            names.append(ATTRIBUTION[name])
    out = {
        "version": VERSION, "fetched_at": _iso(nt), "count": len(items), "trimmed": trimmed, "sources": sources,
        "attribution": "; ".join(names),
        "attribution_links": [{"name": n, "text": ATTRIBUTION[n], "url": ATTRIBUTION_URL[n]}
                              for n, _, _, _ in CYBER_SOURCES],
        "licence": LICENCE["cyber"], "non_commercial": NON_COMMERCIAL["cyber"], "public_ok": PUBLIC_OK["cyber"],
        "windows_days": {"kev": KEV_DAYS, "cisa": CISA_DAYS, "ransom": RANSOM_DAYS, "attack": PRESS_DAYS,
                         "ddos": DDOS_DAYS},
        "infocon": {"level": infocon, "checked": _iso(isc_good) if isc_good else None},
        "kev_catalog": (d["cisa_kev"] or {}).get("catalog"),
        "summary": _summary(full, by, unk, infocon, kev, cisa, ddos, rstore, nt),
        "by_country": by, "unattributed": unk, "items": items, "note": NOTE["cyber"],
    }
    while out["items"] and len(json.dumps(out, separators=(",", ":"), ensure_ascii=False).encode()) > MAX_BYTES:
        keep, extra = _cap(out["items"], max(1, len(out["items"]) * 9 // 10))
        out.update(items=keep, count=len(keep), trimmed=out["trimmed"] + extra)
    return out


# ---------------- the bgp feed ----------------

_STEP = {"5m": 300, "1h": 3600, "1d": 86400, "1w": 604800}


def ripe_url(a2, now):
    start = (now - dt.timedelta(days=SERIES_DAYS)).replace(minute=0, second=0, microsecond=0)
    return RIPE_URL + "?" + urllib.parse.urlencode({"resource": a2, "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
                                                    "resolution": "1h", "sourceapp": "groundtruth"})


def parse_ripe(body, a2=""):
    """RIPEstat country-resource-stats -> ({point epoch: (v4, v6, asns)}, latest_time epoch)."""
    d = json.loads(body)
    if not isinstance(d, dict):
        raise ValueError("RIPEstat %s: unexpected %s" % (a2, type(d).__name__))
    if d.get("status") not in (None, "ok"):
        raise RuntimeError("RIPEstat %s: status %s %s" % (a2, d.get("status"), _clip(d.get("messages"), 120)))
    data = d.get("data") or {}
    stats = data.get("stats")
    if not isinstance(stats, list):
        raise ValueError("RIPEstat %s: no stats" % a2)
    step = _STEP.get(data.get("resolution"), 3600)
    series = {}
    for e in stats:
        if not isinstance(e, dict):
            continue
        vals = (e.get("v4_prefixes_ris"), e.get("v6_prefixes_ris"), e.get("asns_ris"))
        if any(not isinstance(v, (int, float)) or v < 0 for v in vals):
            continue
        for tl in e.get("timeline") or []:
            a = _ts((tl or {}).get("starttime"))
            b = _ts((tl or {}).get("endtime")) or a
            if a is None or b < a:
                continue
            x, k = a, 0
            while x <= b and k < 2000:
                series[x] = tuple(float(v) for v in vals)
                x += step
                k += 1
    if not series:
        raise ValueError("RIPEstat %s: no data points" % a2)
    return series, _ts(data.get("latest_time"))


def _num(x):
    if x is None:
        return None
    x = round(float(x), 1)
    return int(x) if x == int(x) else x


def analyse(series, now_ts):
    """Hourly series -> now/base/pct/diff, level and reasons (see the module docstring for the rule)."""
    ts = sorted(series)
    last = ts[-1]
    cur = [statistics.median(series[t][i] for t in ts[-NOW_POINTS:]) for i in range(3)]
    bpts = [t for t in ts if last - BASE_DAYS * 86400 <= t <= last - BASE_SKIP_H * 3600]
    keys = ("v4", "v6", "asns")
    out = {"latest": _iso(last), "now": {k: _num(v) for k, v in zip(keys, cur)}, "base": None, "pct": None,
           "diff": None, "level": "ok", "reasons": []}
    if len(bpts) >= MIN_BASE_POINTS:
        base = [statistics.median(series[t][i] for t in bpts) for i in range(3)]
        diff = [c - b for c, b in zip(cur, base)]
        pct = [round((c - b) / b * 100, 1) if b else None for c, b in zip(cur, base)]
        out.update(base={k: _num(v) for k, v in zip(keys, base)}, pct=dict(zip(keys, pct)),
                   diff={k: _num(v) for k, v in zip(keys, diff)})
        rs, level = [], "ok"
        if cur[0] == 0 and base[0] > 0:
            rs.append("no IPv4 prefixes visible (base %s)" % _num(base[0]))
            level = "drop"
        for i, name, dp, ip, mn in ((0, "IPv4 prefixes", DROP_V4_PCT, DIP_V4_PCT, MIN_V4_ABS),
                                    (2, "ASNs", DROP_ASN_PCT, DIP_ASN_PCT, MIN_ASN_ABS)):
            if pct[i] is None or -diff[i] < mn or (i == 0 and cur[0] == 0):
                continue
            if pct[i] <= dp:
                level = "drop"
                rs.append("%s %s%% (%s)" % (name, pct[i], _num(diff[i])))
            elif pct[i] <= ip:
                level = "dip" if level == "ok" else level
                rs.append("%s %s%% (%s)" % (name, pct[i], _num(diff[i])))
        out.update(level=level, reasons=rs)
    else:
        out["reasons"] = ["baseline needs %d hourly points, has %d" % (MIN_BASE_POINTS, len(bpts))]
    if now_ts - last > STALE_H * 3600:
        out["level"] = "stale"
        out["reasons"] = ["newest point %s is over %d h old" % (_iso(last), STALE_H)] + out["reasons"]
    n = BASE_DAYS * 24 // SPARK_STEP_H
    pts = [last - k * SPARK_STEP_H * 3600 for k in range(n - 1, -1, -1)]
    out["spark"] = {"start": _iso(pts[0]), "step_h": SPARK_STEP_H,
                    "v4": [_num(series[t][0]) if t in series else None for t in pts],
                    "asns": [_num(series[t][2]) if t in series else None for t in pts]}
    return out


def _bgp_pick(cache, nt):
    """Countries to fetch this poll: all never-fetched ones, then drop/dip ones, then the oldest, up to the caps."""
    never = [a for a in WATCH if a not in cache]
    hot = [a for a in WATCH if a in cache and ((cache[a].get("result") or {}).get("level") in ("drop", "dip"))]
    rest = sorted((a for a in WATCH if a in cache and a not in hot), key=lambda a: (cache[a].get("t", 0), a))
    pick = never[:BGP_MAX_PER_POLL]
    for a in sorted(hot, key=lambda a: (cache[a].get("t", 0), a)) + rest:
        if len(pick) >= max(BGP_PER_POLL, len(never)) or len(pick) >= BGP_MAX_PER_POLL:
            break
        if nt - cache[a].get("t", 0) >= BGP_MIN_AGE:
            pick.append(a)
    return pick


def bgp(now=None, fetch=None, clock=time.monotonic):
    """The `bgp` feed: routing visibility of the watched countries against their own 7-day baseline."""
    now, fetch = _utc(now), fetch or _fetch
    nt = int(now.timestamp())
    st = _load(BGP_FILE)
    cache = st.get("countries") if isinstance(st.get("countries"), dict) else {}
    cache = {a: c for a, c in cache.items() if a in WATCH and isinstance(c, dict)}
    pick = _bgp_pick(cache, nt)
    t0, fails, done, errors = clock(), 0, 0, []
    for a2 in pick:
        if fails >= BGP_MAX_FAILS or clock() - t0 > BGP_TIME_BUDGET:
            break
        c = cache.get(a2) or {}
        done += 1
        try:
            series, _latest = parse_ripe(fetch(ripe_url(a2, now)), a2)
            c.update(result=analyse(series, nt), ok=True, error=None, good=nt)
            fails = 0
        except Exception as e:
            c.update(ok=False, error=_err(e))
            errors.append("%s %s" % (a2, c["error"]))
            fails += 1
        c["t"] = nt
        cache[a2] = c
    _save(BGP_FILE, {"version": VERSION, "countries": cache})
    if not any(c.get("result") for c in cache.values()):
        raise RuntimeError("bgp: no country has data yet: " + "; ".join(errors[:3]))

    rows = []
    for a2 in WATCH:
        a3 = _a3(a2)
        c = cache.get(a2) or {}
        row = {"a2": a2, "a3": a3, "name": _cname(a3) if a3 else a2, "theatre": geo.theatre_for_a3(a3) if a3 else None,
               "url": "https://stat.ripe.net/" + a2, "fetched": _iso(c["good"]) if c.get("good") else None,
               "error": c.get("error")}
        res = c.get("result")
        if res:
            res = dict(res)
            if nt - (_ts(res["latest"]) or 0) > STALE_H * 3600 and res["level"] != "stale":
                res["reasons"] = ["newest point %s is over %d h old" % (res["latest"], STALE_H)] + res["reasons"]
                res["level"] = "stale"
            row.update(res)
        else:
            row.update(level="pending", reasons=[], latest=None, now=None, base=None, pct=None, diff=None, spark=None)
        rows.append(row)
    rows.sort(key=lambda r: (LEVEL_ORDER.get(r["level"], 9), ((r.get("pct") or {}).get("v4") or 0), r["a2"]))
    drops = [r["a3"] for r in rows if r["level"] == "drop"]
    dips = [r["a3"] for r in rows if r["level"] == "dip"]
    have = [r for r in rows if r.get("now")]
    if drops or dips:
        summary = "; ".join("%s %s: %s" % (r["level"].upper(), r["name"], ", ".join(r["reasons"]))
                            for r in rows if r["level"] in ("drop", "dip"))
    else:
        summary = "No routing drop in %d of %d watched countries with data." % (len(have), len(WATCH))
    pending = [r["a2"] for r in rows if r["level"] == "pending"]
    if pending:
        summary += " Pending: %s." % ", ".join(pending)
    return {
        "version": VERSION, "fetched_at": _iso(nt), "count": len(have),
        "sources": [{"name": "ripestat", "ok": not errors, "error": "; ".join(errors[:3]) or None,
                     "newest": max((r["latest"] for r in have if r.get("latest")), default=None), "n": len(have),
                     "requests": done}],
        "attribution": ATTRIBUTION["ripestat"], "attribution_url": ATTRIBUTION_URL["ripestat"],
        "licence": LICENCE["bgp"], "non_commercial": NON_COMMERCIAL["bgp"], "public_ok": PUBLIC_OK["bgp"],
        "thresholds": {"drop_v4_pct": DROP_V4_PCT, "drop_asn_pct": DROP_ASN_PCT, "dip_v4_pct": DIP_V4_PCT,
                       "dip_asn_pct": DIP_ASN_PCT, "min_v4_abs": MIN_V4_ABS, "min_asn_abs": MIN_ASN_ABS,
                       "now_points": NOW_POINTS, "base_days": BASE_DAYS, "base_skip_h": BASE_SKIP_H,
                       "stale_h": STALE_H},
        "drops": drops, "dips": dips, "summary": _clip(summary, SUMMARY_MAX), "countries": rows, "note": NOTE["bgp"],
    }


FEEDS = {
    "cyber": (cyber, 900),
    "bgp": (bgp, 900),
}
