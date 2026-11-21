"""Offline tests for 1.5.3: the website and cloud disruption layers (gt/services.py, feeds `websites` and `cloud`).
Sockets are blocked; nothing touches the network. Fixtures in tests/fixtures/services/:
  REAL responses of 2026-11-21 (~04:50 UTC), trimmed (a few incidents each, update bodies and Google texts cut to
  ~300 characters, components to 4):
    github.json, zoom.json, linode.json, openai.json, digitalocean.json, ovh.json, lambda.json   Statuspage v2 /
        incident.io incidents.json (the full polls serve the synthetic Statuspage file as DigitalOcean)
    cloudflare.json   summary.json: 2 groups, 2 non-PoP components, 8 PoPs (IAD + 2 operational, 3 partial_outage,
                      2 under_maintenance), both open incidents, 2 scheduled maintenances
    gcp.json, workspace.json   Google Cloud / Workspace incidents.json (3 and 2 incidents)
    m365.json, slack.json      Microsoft 365 consumer posts (3 Operational rows) and Slack current (no incident)
    aws.rss (4 items), oci.rss (6), hetzner.atom (6), hf.rss (7), paypal.rss (5)
    dcd.rss, dck.rss, register.rss   news: title, link, pubDate / dc:date and guid only (no article text)
  SYNTHETIC (real field names, invented content, clock 2026-11-21T05:00Z):
    azure.rss                  the live Azure feed was an empty channel: an active, a mitigated and a planned item
    statuspage_synthetic.json  active incident with region components, critical, maintenance in progress /
                               scheduled / completed, future-dated, clock-skewed, stale, old resolved, postmortem
    slack_active.json, m365_active.json   one active incident each (the live bodies had none)
    news_synthetic.rss         fire / outage / cooling / flood headlines plus future, deal, opinion, undated, old
Run: python3 -I tests/test_services.py
"""
import copy
import datetime as dt
import gzip
import json
import os
import re
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "services")
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def _blocked(*a, **k):
    raise AssertionError("network use in an offline test")


from gt import services as S  # noqa: E402

socket.socket.connect = _blocked          # after the import: ssl subclasses socket.socket
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
S.urllib.request.urlopen = _blocked
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def raises(fn, exc, text=""):
    try:
        fn()
    except exc as e:
        return text in str(e)
    return False


RAW = {n: open(os.path.join(FX, n), "rb").read() for n in sorted(os.listdir(FX))}
J = {n: json.loads(b) for n, b in RAW.items() if n.endswith(".json")}
NOW = dt.datetime(2026, 11, 21, 5, 0, tzinfo=dt.timezone.utc)
NT = int(NOW.timestamp())
EMPTY_SP = b'{"page": {}, "incidents": []}'
SERVE = {"github": "github.json", "zoom": "zoom.json", "slack": "slack_active.json", "paypal": "paypal.rss",
         "gworkspace": "workspace.json", "m365": "m365_active.json", "cloudflare": "cloudflare.json",
         "aws": "aws.rss", "azure": "azure.rss", "gcp": "gcp.json", "oci": "oci.rss",
         "digitalocean": "statuspage_synthetic.json", "linode": "linode.json", "hetzner": "hetzner.atom",
         "ovh": "ovh.json", "openai": "openai.json", "huggingface": "hf.rss", "lambda": "lambda.json",
         "dcd": "dcd.rss", "dck": "dck.rss", "register": "news_synthetic.rss"}
BY_URL = {S.SOURCES[k]["url"]: k for k in S.SOURCES}
SIZE = lambda x: len(json.dumps(x, separators=(",", ":"), ensure_ascii=False).encode())


def at(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc)


def fake(over=None, fail=(), log=None, validators=None):
    """fetch(url, etag, lm) serving fixtures by source; `over` {key: bytes or dict}, `fail` keys raise HTTP 500."""
    over = over or {}

    def f(url, etag=None, lm=None):
        k = BY_URL[url]
        if log is not None:
            log.append(k)
        if validators is not None:
            validators[k] = (etag, lm)
        if k in fail:
            raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)
        if k in over:
            return over[k]
        return RAW[SERVE[k]] if k in SERVE else EMPTY_SP
    return f


def reset():
    p = os.path.join(TMP, "cache", S.STATE_FILE)
    if os.path.exists(p):
        os.remove(p)
    S._INFLIGHT.clear()


def state():
    return json.load(open(os.path.join(TMP, "cache", S.STATE_FILE), encoding="utf-8"))


def parse(key, name, now=NOW, prev=None):
    return S.PARSERS[S.SOURCES[key]["fmt"]](RAW[name], now, S.SOURCES[key], prev)["records"]


def items_of(feed, key, recs, now=NOW):
    nt = int(now.timestamp())
    out = []
    for r in recs:
        if S._route(key, r) == feed:
            it, pl = S.make_item(feed, key, r, nt)
            if it:
                out.append((it, pl))
    return out


def by_sid(recs):
    return {r["sid"]: r for r in recs}


# ================= module contract =================
src = open(os.path.join(PROJ, "gt", "feeds.py"), encoding="utf-8").read()
reg = src[src.index("REGISTRY = {"):]
reg = reg[:reg.index("\n}")]
existing = set(re.findall(r'^\s*"([a-z]+)":', reg, re.M))
check(len(existing) >= 20 and set(S.FEEDS) == {"websites", "cloud"} and not set(S.FEEDS) & existing
      and all(re.match(r"^[a-z]+$", n) for n in S.FEEDS), "FEEDS websites + cloud: lowercase, no clash with feeds.REGISTRY")
check(S.FEEDS["websites"] == (S.websites, 300) and S.FEEDS["cloud"] == (S.cloud, 300) and S.VERSION == "1.1"
      and S.PUBLIC_OK == {"websites": False, "cloud": False} and S.NON_COMMERCIAL == {"websites": True, "cloud": True},
      "FEEDS every 300 s; PUBLIC_OK False and NON_COMMERCIAL True per feed")
check(S.UA == "GroundTruth/1.5 (personal non-commercial OSINT dashboard)" and S.TIMEOUT + S.TIME_BUDGET <= 60
      and S.MAX_FAILS == 3 and S.TIME_BUDGET == 45 and S.SLACK == 60, "UA, 3-failure stop, 45 s budget + timeout <= 60 s")
check(S.CACHE == os.path.join(TMP, "cache") and S.STATE_FILE == "services_state.json", "state in <GT_DATA>/cache/services_state.json")
urls = " ".join(s["url"] for s in S.SOURCES.values()).lower()
check(not re.search(r"downdetector|apple\.com|x\.ai|grok|firecrawl|health\.aws\.amazon\.com", urls)
      and all(s["url"].startswith("https://") for s in S.SOURCES.values()),
      "no Downdetector / Apple / xAI / Firecrawl / AWS health JSON; all sources https")
check(all(k in S.SOURCES for f in S.FEED_SOURCES.values() for k in f)
      and set(S.FEED_SOURCES["websites"]) & set(S.FEED_SOURCES["cloud"]) == {"cloudflare", "gworkspace"}
      and all(S.SOURCES[k]["every"] in (300, 600, 900, 1800) for k in S.SOURCES), "source table: shared sources, cadences")
check(all(S.SOURCES[k]["retry"] <= 300 for k in S.SOURCES if S.SOURCES[k]["fmt"] != "news")
      and all(S.SOURCES[k]["retry"] == 900 and S.SOURCES[k]["every"] == 1800 for k in ("dcd", "dck", "register")),
      "retry <= 300 s (news: every 1800 s, retry 900 s)")
# the export audit's banned words, stored reversed so this file does not contain them
bad = re.compile("|".join(r"\b%s\b" % re.escape(w[::-1]) for w in ("REVRES", "005T", "cprebma", "yolped-veg", "lliW",
                                                                     "lliw.lacol")))
own = [os.path.join(PROJ, "gt", "services.py"), os.path.abspath(__file__), os.path.join(PROJ, "tools", "build_pops.py"),
       os.path.join(PROJ, "ref", "cf_pops.json")] + [os.path.join(FX, n) for n in RAW]
check(not [p for p in own if bad.search(open(p, encoding="utf-8").read())], "no host or personal names in code, tests, fixtures")
check(all(c in S._theatres() for c in {v[3] for v in S.CITIES.values()}),
      "every CITIES country is in theatres.json")
tables = [S.AWS_REGIONS, S.GCP_REGIONS, S.AZURE_REGIONS, S.DO_REGIONS, S.IATA_CITY, S.LINODE_LEGACY, S.OVH_SITES,
          S.OVH_TOKENS, S.HETZNER_SITES, dict(S.LAMBDA_PREFIX), S.CITY_ALIASES]
check(all(v in S.CITIES for t in tables for v in t.values()) and all(s["hq"] in S.CITIES for s in S.SOURCES.values()
                                                                    if s["hq"]),
      "every region table and HQ points at a CITIES metro")
pops = S.cf_pops()
check(len(pops) >= 300 and pops["IAD"][3] == "USA" and all(len(v) == 4 and -180 <= v[0] <= 180 and -90 <= v[1] <= 90
                                                           and v[3] in S._theatres() for v in pops.values()),
      "ref/cf_pops.json: %d PoPs, coordinates and ISO-3 countries valid" % len(pops))

# ================= default fetch =================


class Resp:
    def __init__(self, body, enc=None, etag=None, lm=None):
        self.body, self.status = body, 200
        self.headers = {k: v for k, v in (("Content-Encoding", enc), ("ETag", etag), ("Last-Modified", lm)) if v}

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen = {}


def fake_open(req, timeout=None):
    seen.update(ua=req.get_header("User-agent"), ae=req.get_header("Accept-encoding"), timeout=timeout,
                inm=req.get_header("If-none-match"), ims=req.get_header("If-modified-since"))
    return Resp(gzip.compress(RAW["slack.json"]), "gzip", 'W/"abc"', "Sat, 21 Nov 2026 04:50:00 GMT")


S.urllib.request.urlopen = fake_open
r = S._fetch(S.SOURCES["slack"]["url"], 'W/"old"', "Fri, 20 Nov 2026 00:00:00 GMT")
check(r == {"status": 200, "body": RAW["slack.json"], "etag": 'W/"abc"', "lm": "Sat, 21 Nov 2026 04:50:00 GMT"}
      and seen["ua"] == S.UA and seen["ae"] == "gzip" and seen["timeout"] == S.TIMEOUT
      and seen["inm"] == 'W/"old"' and seen["ims"] == "Fri, 20 Nov 2026 00:00:00 GMT",
      "default fetch: UA, gzip decoded, 15 s timeout, If-None-Match / If-Modified-Since sent, validators returned")
S._fetch(S.SOURCES["slack"]["url"])
check(seen["inm"] is None and seen["ims"] is None, "no conditional headers without validators")


def not_modified(req, timeout=None):
    raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)


S.urllib.request.urlopen = not_modified
check(S._fetch(S.SOURCES["slack"]["url"], "x") == {"status": 304}, "HTTP 304 -> {'status': 304}")
S.urllib.request.urlopen = lambda req, timeout=None: Resp(b"x" * (S.MAX_BODY + 1))
check(raises(lambda: S._fetch(S.SOURCES["slack"]["url"]), ValueError, "over"), "oversized body refused")
S.urllib.request.urlopen = lambda req, timeout=None: Resp(gzip.compress(b"\0" * (S.MAX_BODY + 10)), "gzip")
check(raises(lambda: S._fetch(S.SOURCES["slack"]["url"]), ValueError, "decompressed"), "gzip bomb refused")
S.urllib.request.urlopen = _blocked

# ================= rules =================
check(S.says_resolved("This incident has been resolved.") and S.says_resolved("Service is operating normally")
      and S.says_resolved("Services are back to nominal operations.") and S.says_resolved("<strong>Mitigated</strong>")
      and not S.says_resolved("The issue is not yet resolved.") and not S.says_resolved("Not fully restored")
      and not S.says_resolved("We will provide an update once the work has been completed.")
      and not S.says_resolved("We are working to restore service until it is restored")
      and S.says_resolved("Resolved. We will provide an update once the review is completed."),
      "resolved wording: resolved / restored / mitigated / normal; negated and future phrasing ignored")
check([S.text_severity(t) for t in ("Major outage of the API", "Partial outage in EU", "Service disruption",
                                    "Customers unable to log in: login unavailable", "Informational message",
                                    "Increased latency")] == ["critical", "major", "major", "major", "info", "minor"],
      "text severity: major outage critical, outage / disruption / unavailable major, informational info, else minor")
base = {"sid": "x", "title": "t", "ts": NT - 3600, "resolved": False, "maint": False}
check(S.is_active(base, NT) and not S.is_active(dict(base, resolved=True), NT)
      and S.is_active(dict(base, rss=True, ts=NT - 23 * 3600), NT) and not S.is_active(dict(base, rss=True, ts=NT - 25 * 3600), NT)
      and not S.is_active(dict(base, news=True), NT)
      and S.is_active(dict(base, maint=True, win=[NT - 60, NT + 60]), NT)
      and not S.is_active(dict(base, maint=True, win=[NT + 60, NT + 3600]), NT)
      and not S.is_active(dict(base, maint=True, win=[NT - 7200, NT - 60]), NT),
      "active: machine status; text feeds 24 h after the last update; maintenance inside its window; news never")
check(S.BOARD_OF == {"critical": "major", "major": "partial", "minor": "degraded", "maintenance": "maintenance",
                     "info": "operational"} and S.IMPACT_SEV["none"] == "info" and S.GOOGLE_SEV == {
    "high": "major", "medium": "minor", "low": "info"}, "severity and board mappings as documented")
for t in ("Fire at data center in Frankfurt knocks services offline", "Power outage hits colocation facility",
          "Cooling failure takes down cloud region", "Flooding forces evacuation of data hall",
          "Explosion reported at data center", "Data center goes offline after sabotage", "Blaze at server farm"):
    check(S.is_incident_headline(t), "news kept: %s" % t)
for t in ("Operator acquires rival after last year's outage", "Opinion: why outages keep happening",
          "New data center campus plans unveiled", "CyrusOne and KEP top out 48MW data center in Osaka, Japan",
          "Techie rigged off-spec fan near flammable liquid and an exposed motherboard, then left it to run for days",
          "Q3 earnings: outage costs weigh", "AI Workloads Hit by Power-Quality Issues at Data Centers"):
    check(not S.is_incident_headline(t), "news dropped: %s" % t[:60])

# ================= parsers =================
gh = by_sid(parse("github", "github.json"))
check(set(gh) == {"gp7nhc88bwv9", "2zfqmghmg3s3", "dvy0t3mvh1lg"} and gh["dvy0t3mvh1lg"]["severity"] == "critical"
      and gh["2zfqmghmg3s3"]["severity"] == "minor" and all(r["resolved"] and r["status"] == "resolved" for r in gh.values())
      and gh["gp7nhc88bwv9"]["url"] == "https://www.githubstatus.com/incidents/gp7nhc88bwv9"
      and all("<" not in (r["summary"] or "") for r in gh.values()), "Statuspage (GitHub, real): impact, resolved, URL, plain text")
it, pl = S.make_item("websites", "github", gh["dvy0t3mvh1lg"], NT)
check(it["ts"] == "2026-11-20T18:14:41Z" and it["start_ms"] < it["ts_ms"] and it["end_ms"] and it["active"] is False,
      "ts = newest update (postmortem), start before it, end set, not active")
oa = parse("openai", "openai.json")
check(len(oa) == 2 and all(r["url"].startswith("https://status.openai.com/incidents/") and r["comps"] == [] for r in oa)
      and {r["severity"] for r in oa} == {"major", "minor"}, "incident.io (OpenAI, real): no components, URL built from base")
ln = by_sid(parse("linode", "linode.json"))
check(ln["hgq6wzfbdr71"]["comps"][:2] == ["US-ORD (Chicago)", "US-SEA (Seattle)"] and not ln["hgq6wzfbdr71"]["resolved"]
      and ln["hgq6wzfbdr71"]["status"] == "monitoring" and ln["d5ksyyk5x9w5"]["severity"] == "info"
      and "k95n77rlncr6" not in ln, "Statuspage (Linode, real): components, monitoring, impact none -> info, old pruned")
lnm = by_sid(parse("linode", "linode.json", at("2026-10-16T13:00")))["k95n77rlncr6"]
check(lnm["maint"] and lnm["severity"] == "maintenance" and lnm["resolved"]
      and S.make_item("cloud", "linode", lnm, S._ts("2026-10-16T13:00:00Z")) == (None, None),
      "Linode maintenance (real): flagged, and once completed never listed")
do = items_of("cloud", "digitalocean", parse("digitalocean", "digitalocean.json"))
check(len(do) == 1 and do[0][0]["title"] == "Increased Error Rates in SFO3" and do[0][0]["where"] == "San Francisco, US"
      and do[0][0]["regions"] == ["SFO3"] and do[0][0]["status"] == "resolved", "Statuspage (DigitalOcean, real): SFO3 -> San Francisco")
sp = by_sid(parse("digitalocean", "statuspage_synthetic.json"))
check("synmaintlater" not in sp and "synmaintnow" in sp and sp["synmaintnow"]["status"] == "in effect"
      and sp["synmaintnow"]["end"] == S._ts("2026-11-21T08:00:00Z") and "synstale" not in sp and "synoldres" not in sp
      and sp["syncrit1"]["title"] == "Control panel & API unavailable" and sp["syncrit1"]["start"] == S._ts("2026-11-21T04:20:00Z")
      and "<" not in sp["synactive1"]["summary"] and "investigating connectivity issues" in sp["synactive1"]["summary"],
      "synthetic Statuspage: scheduled dropped, stale and old pruned, HTML stripped, -08:00 offsets read")
cf = S.parse_cloudflare(RAW["cloudflare.json"], NOW, S.SOURCES["cloudflare"], None)
cfr = by_sid(cf["records"])
check(cf["pops"]["total"] == 8 and cf["pops"]["partial_outage"] == 3 and cf["pops"]["under_maintenance"] == 2
      and cf["pops"]["maintenance_in_progress"] == 0, "Cloudflare (real): PoP components counted by status")
check(cfr["oz6to8yacrxe"]["route"] == "cloud" and cfr["oz6to8yacrxe"]["pops"] == ["IAD"]
      and cfr["0ocqieaifg7h"]["route"] == "websites" and not cfr["0ocqieaifg7h"].get("pops") and len(cfr) == 2,
      "Cloudflare: the PoP-named incident goes to cloud, the Workers one to websites; scheduled maintenance not listed")
cfx = copy.deepcopy(J["cloudflare.json"])
cfx["scheduled_maintenances"] = [
    {"id": "synpop", "name": "IAD (Washington) on 2026-11-21", "status": "in_progress", "impact": "maintenance",
     "created_at": "2026-11-20T00:00:00Z", "updated_at": "2026-11-21T04:00:00Z", "scheduled_for": "2026-11-21T04:00:00Z",
     "scheduled_until": "2026-11-21T08:00:00Z", "incident_updates": []},
    {"id": "synsvc", "name": "Dashboard maintenance", "status": "in_progress", "impact": "maintenance",
     "created_at": "2026-11-20T00:00:00Z", "updated_at": "2026-11-21T04:00:00Z", "scheduled_for": "2026-11-21T04:00:00Z",
     "scheduled_until": "2026-11-21T08:00:00Z", "incident_updates": []}]
cf2 = S.parse_cloudflare(json.dumps(cfx).encode(), NOW, S.SOURCES["cloudflare"], None)
check(cf2["pops"]["maintenance_in_progress"] == 1 and "synpop" not in by_sid(cf2["records"])
      and by_sid(cf2["records"])["synsvc"]["route"] == "websites",
      "Cloudflare (synthetic): in-progress PoP maintenance counted, not listed; service maintenance listed")
check(parse("slack", "slack.json") == [], "Slack (real): no active incident")
sl = parse("slack", "slack_active.json")
check(len(sl) == 1 and sl[0]["severity"] == "major" and sl[0]["summary"] == "We've identified the cause."
      and sl[0]["url"] == "https://slack-status.com/2026-11/syn9999901" and sl[0]["comps"] == ["Messaging", "Connectivity"],
      "Slack (synthetic): outage -> major, newest note as summary, link")
check(parse("m365", "m365.json") == [], "M365 (real): all Operational -> no records")
m3 = parse("m365", "m365_active.json")
check(len(m3) == 1 and m3[0]["sid"] == "EX9999901" and m3[0]["severity"] == "major"
      and m3[0]["ts"] == S._ts("2026-11-21T04:00:00+00:00"), "M365 (synthetic): ServiceInterruption -> major, 0001 dates ignored")
pp = by_sid(parse("paypal", "paypal.rss", at("2026-11-12T10:00")))
check("PP-LIVE-110644" in pp and pp["PP-LIVE-110644"]["title"] == "Impact to Checkout and Multiple API's"
      and pp["PP-LIVE-110644"]["resolved"] and pp["PP-LIVE-110644"]["severity"] == "major"
      and "PP-LIVE-110458" not in pp and all(not r["maint"] or r["resolved"] for r in pp.values()),
      "PayPal (real): status prefix stripped, Detected Resolved, announced maintenance dropped")
check(all(S.make_item("websites", "paypal", r, S._ts("2026-11-12T10:00:00Z"))[0] is None for r in pp.values() if r["maint"]),
      "PayPal: completed / rescheduled maintenance never listed")
gc = by_sid(parse("gcp", "gcp.json", at("2026-11-05T08:00")))
check(set(gc) == {"Xs2XTHzAVC9YnafnPyzj"} and gc["Xs2XTHzAVC9YnafnPyzj"]["regions"] == ["europe-west2"]
      and gc["Xs2XTHzAVC9YnafnPyzj"]["url"].startswith("https://status.cloud.google.com/incidents/")
      and gc["Xs2XTHzAVC9YnafnPyzj"]["title"].startswith("Multiple Products: Multiple services were experiencing issues"),
      "Google Cloud (real): window prune, regions from the locations, title from external_desc")
gc_all = by_sid(S.parse_google(RAW["gcp.json"], at("2026-07-25T00:00"), S.SOURCES["gcp"], None)["records"])
check(len(gc_all) == 3 and gc_all["T8gmtofFSTGT5tbhyciF"]["regions"] == ["australia-southeast2", "europe-west3"]
      and all(r["resolved"] for r in gc_all.values())
      and not any(re.search(r"[#*\\]", (r["summary"] or "") + r["title"]) for r in gc_all.values()),
      "Google Cloud: all ended incidents resolved, markdown stripped")
ws = by_sid(S.parse_google(RAW["workspace.json"], at("2026-09-12T00:00"), S.SOURCES["gworkspace"], None)["records"])
check(ws["B5V4MfnVp97nxoTYbxdX"]["route"] == "websites"
      and ws["B5V4MfnVp97nxoTYbxdX"]["title"].startswith("Gmail Android App users on the latest Gmail Android release")
      and ws["fJ4691Pe2g9KsTbP8g5F"]["route"] == "cloud" and ws["fJ4691Pe2g9KsTbP8g5F"]["severity"] in ("info", "minor", "major"),
      "Workspace (real): Gmail -> websites with the Title line, Gemini -> cloud")
it, _ = S.make_item("cloud", "gworkspace", ws["fJ4691Pe2g9KsTbP8g5F"], S._ts("2026-09-12T00:00:00Z"))
check(it["provider"] == "Google Gemini" and "ai" in it["tags"] and it["place"] == "hq", "Gemini items: provider Google Gemini, HQ")
aw_all = parse("aws", "aws.rss", at("2026-04-30T08:00"))
check(sorted(r["sid"] for r in aw_all) == ["multipleservices-me-central-1_1777533954", "multipleservices-me-central-1_1789468030",
                                           "multipleservices-me-south-1_1777532831", "multipleservices-me-south-1_1789467748"]
      and all(r["severity"] == "major" and r["rss"] for r in aw_all),
      "AWS (real): grouped per service-region, a 48 h gap starts a new incident, disruption -> major")
aw = parse("aws", "aws.rss", at("2026-09-15T12:00"))
awi = items_of("cloud", "aws", aw, at("2026-09-15T12:00"))
check(len(aw) == 2, "AWS: April incidents pruned in September (quiet text-feed incidents leave after 72 h)")
check(len(awi) == 2 and all(i["active"] for i, _ in awi) and {i["where"] for i, _ in awi} == {"Dubai, AE", "Manama, BH"}
      and all(i["title"].startswith("Multiple services me-") for i, _ in awi), "AWS: region from the guid, 24 h active, metro pin")
check(all(not i["active"] for i, _ in items_of("cloud", "aws", aw, at("2026-09-16T12:00"))),
      "AWS: quiet for over 24 h -> not active")
az = by_sid(parse("azure", "azure.rss"))
a1 = [r for r in az.values() if "Virtual Machines" in r["title"]][0]
a2 = [r for r in az.values() if "Front Door" in r["title"]][0]
check(len(az) == 2 and a1["title"] == "Virtual Machines - East US 2" and not a1["resolved"] and a1["status"] == "identified"
      and a1["start"] == S._rfc822("Sat, 21 Nov 2026 02:40:00 Z") and a2["resolved"] and a1["severity"] == "major",
      "Azure (synthetic): updates grouped by guid, not-yet-resolved stays open, mitigated resolved, planned dropped")
check([c for c, _ in S.regions("azure", a1)] == ["East US 2"] and [c for c, _ in S.regions("azure", a2)] == ["West Europe", "North Europe"],
      "Azure regions by display name and compact id (northeurope)")
oc = by_sid(parse("oci", "oci.rss", at("2025-10-30T10:00")))
check(len(oc) == 1 and list(oc.values())[0]["regions"] == ["Saudi Arabia West (Jeddah)"]
      and list(oc.values())[0]["resolved"] and list(oc.values())[0]["title"] == "Oracle Cloud Network Infrastructure | Saudi Arabia West (Jeddah)",
      "OCI (real): Service | Region title, region kept, Resolved")
oc_all = S.parse_oci(RAW["oci.rss"], at("2024-01-01T00:00"), S.SOURCES["oci"], None)["records"]
places_oci = {r["regions"][0] if r["regions"] else "": [p["label"] for p in S.places("cloud", "oci", r)] for r in oc_all}
check(places_oci.get("Multiple Regions") == ["Global (HQ: Austin)"] and places_oci.get("France South (Marseille)") == ["Marseille, FR"]
      and places_oci.get("US West (San Jose)") == ["San Jose, US"], "OCI placement: city in brackets, Multiple Regions at HQ")
hz = by_sid(parse("hetzner", "hetzner.atom", at("2026-11-21T05:00")))
check("2e715748-fddd-427b-a07b-b34a5a9edee3" not in hz and hz["5538b885-8fe5-42ad-98f7-7f788a8af426"]["status"] == "monitoring"
      and hz["c846961f-000c-4209-89bc-43a8b8a36876"]["win"] == [S._ts("2026-11-23T12:00:00+00:00"), S._ts("2026-11-23T20:00:00+00:00")]
      and not hz["c846961f-000c-4209-89bc-43a8b8a36876"]["resolved"],
      "Hetzner (real): General phishing notice skipped, Monitoring update read, maintenance window kept (not 'completed')")
hzi = {i["id"].split(":")[2]: (i, p) for i, p in items_of("cloud", "hetzner", list(hz.values()))}
check("c846961f-000c-4209-89bc-43a8b8a36876" not in hzi and "e6d41459-0475-4de3-9ddc-4b970f82d882" not in hzi
      and hzi["5538b885-8fe5-42ad-98f7-7f788a8af426"][0]["where"] == "Falkenstein, DE"
      and hzi["5538b885-8fe5-42ad-98f7-7f788a8af426"][0]["active"] is False,
      "Hetzner: future maintenance not listed; fsn1 pinned at Falkenstein; quiet > 24 h not active")
hz2 = by_sid(parse("hetzner", "hetzner.atom", at("2026-11-23T13:00")))
um = S.make_item("cloud", "hetzner", hz2["c846961f-000c-4209-89bc-43a8b8a36876"], S._ts("2026-11-23T13:00:00Z"))
check(um[0] and um[0]["active"] and um[0]["severity"] == "maintenance" and um[0]["status"] == "in effect"
      and [p["label"] for p in um[1]] == ["Helsinki, FI", "Falkenstein, DE"] and "maintenance" in um[0]["tags"],
      "Hetzner: maintenance in its window -> active, severity maintenance, HEL + FSN pins")
hf = by_sid(parse("huggingface", "hf.rss", at("2026-11-13T09:00")))
check(set(hf) == {"1124142"} and hf["1124142"]["resolved"] and hf["1124142"]["start"] == S._rfc822("Fri, 13 Nov 2026 06:30:00 -0000")
      and hf["1124142"]["title"] == "Degraded performance - AWS CDN (Singapore)",
      "Hugging Face (real): updates grouped by incident link; completed maintenance dropped")
hf_old = by_sid(S.parse_hf(RAW["hf.rss"], at("2026-07-16T11:00"), S.SOURCES["huggingface"], None)["records"])
check(hf_old["965809"]["resolved"] and hf_old["965809"]["severity"] == "major", "HF: 'back to nominal operations' resolves")
check(parse("dcd", "dcd.rss") == [] and parse("dck", "dck.rss") == [] and parse("register", "register.rss", at("2026-11-17T14:00")) == [],
      "news (real): no incident headline among deals, construction, opinion")
ev = [e for e in S._feed_entries(RAW["dck.rss"]) if "/events/" in e["link"]]
check(len(ev) == 1 and ev[0]["t"] and ev[0]["pub"] is False, "DCK event listing has dc:date but no pubDate -> never kept")
nw = parse("register", "news_synthetic.rss")
check(sorted(r["title"] for r in nw) == ["Cooling failure takes down cloud region",
                                         "Fire at data center in Frankfurt knocks services offline",
                                         "Flooding forces evacuation of data hall in Jakarta, Indonesia",
                                         "Power outage hits colocation facility in Singapore"]
      and all(r["severity"] == "info" and r["news"] for r in nw),
      "news (synthetic): incident headlines kept; future, deal, opinion, undated, old and campus dropped")
check([r for r in nw if "Frankfurt" in r["title"]][0]["summary"] == "A blaze in a battery room forced an evacuation.",
      "news summary is plain text")

# ================= placement =================


def pl_of(feed, key, title, **kw):
    return S.places(feed, key, dict({"sid": "x", "title": title, "ts": NT}, **kw))


p = pl_of("websites", "github", "Incident with Pull Requests")
check(len(p) == 1 and p[0]["place"] == "hq" and p[0]["label"] == "Global (HQ: San Francisco)" and p[0]["ll"] == [-122.42, 37.77],
      "websites: global incident at the HQ")
check([x["label"] for x in pl_of("websites", "zoom", "Service degradation in the US region")] == ["United States of America"]
      and [x["place"] for x in pl_of("websites", "zoom", "Calls failing in the UK and Australia")] == ["country", "country"]
      and [x["label"] for x in pl_of("websites", "zoom", "Zoom Phone in Europe Region")] == ["Europe"]
      and [x["label"] for x in pl_of("websites", "zoom", "Service degradation for APAC users")] == ["Asia-Pacific"]
      and [x["label"] for x in pl_of("websites", "stripe", "Payments failing")] == ["Global (HQ: South San Francisco)"]
      and [x["label"] for x in pl_of("websites", "jira", "Jira slow")] == ["Global (HQ: Sydney)"],
      "websites: named country / macro region instead of HQ; Stripe and Atlassian HQs")
check([x["label"] for x in pl_of("cloud", "mistral", "API errors")] == ["Global (HQ: Paris)"]
      and [x["label"] for x in pl_of("cloud", "huggingface", "Hub down")] == ["Global (HQ: New York)"]
      and [x["label"] for x in pl_of("cloud", "lambda", "Power event impacting us-southeast-1 connectivity")] == ["Atlanta, US"]
      and [x["label"] for x in pl_of("cloud", "lambda", "Instance launch errors")] == ["Global (HQ: San Jose)"],
      "cloud: AI services at the HQ; Lambda region in the title")
check([x["label"] for x in pl_of("cloud", "ovh", "[BHS1/3/5][Public Cloud] - Incident")] == ["Beauharnois, CA"]
      and [x["label"] for x in pl_of("cloud", "ovh", "[US-WEST-OR][Storage] - x")] == ["Hillsboro, US"]
      and [x["label"] for x in pl_of("cloud", "ovh", "[EU/CA/MUM] - x")] == ["Mumbai, IN"]
      and [x["label"] for x in pl_of("cloud", "ovh", "x", comps=["GRA11", "SBG5", "WAW1"])] == ["Gravelines, FR", "Strasbourg, FR", "Warsaw, PL"],
      "OVH regions from title brackets and components")
check([x["label"] for x in pl_of("cloud", "linode", "x", comps=["US-ORD (Chicago)", "SG-SIN-2 (Singapore 2)", "US-East (Newark)"])]
      == ["Chicago, US", "Singapore", "Newark, US"]
      and [x["label"] for x in pl_of("cloud", "digitalocean", "Errors in SFO3", comps=["Global"])] == ["San Francisco, US"]
      and [x["label"] for x in pl_of("cloud", "hetzner", "Object Storage in location fsn1 partially degraded")] == ["Falkenstein, DE"]
      and [x["label"] for x in pl_of("cloud", "gcp", "x", regions=["global", "nam5", "us-central1"])] == ["Council Bluffs, US"]
      and [x["label"] for x in pl_of("cloud", "aws", "x", regions=["eu-central-1"])] == ["Frankfurt, DE"]
      and [x["label"] for x in pl_of("cloud", "gcp", "x", regions=["global"])] == ["Global (HQ: Mountain View)"],
      "cloud regions: Linode, DigitalOcean, Hetzner, Google (global skipped), AWS; unknown -> HQ")
check(pl_of("cloud", "register", "Cooling failure takes down cloud region") == []
      and [x["label"] for x in pl_of("cloud", "dcd", "Fire at a German data center")] == ["Germany"],
      "news: country centroid from gt.placer, no pin without a country")
p = pl_of("cloud", "cloudflare", "Network Performance Issues in Washington, DC datacenter (IAD)", pops=["IAD"])
check(len(p) == 1 and p[0]["place"] == "pop" and p[0]["ll"] == pops["IAD"][:2] and p[0]["label"].endswith("(IAD)")
      and p[0]["a3"] == "USA", "Cloudflare PoP incident pinned at the PoP from ref/cf_pops.json")

# ================= full polls =================
reset()
log = []
w1 = S.websites(now=NOW, fetch=fake(log=log))
c1 = S.cloud(now=NOW, fetch=fake(log=log))
check(sorted(log) == sorted(set(S.FEED_SOURCES["websites"]) | set(S.FEED_SOURCES["cloud"])),
      "first polls fetch every source once (shared Cloudflare / Workspace fetched by the first feed only)")
BASE = {"version", "fetched_at", "count", "trimmed", "items", "geojson", "sources", "summary", "note", "attribution",
        "public_ok", "non_commercial", "board"}
check(set(w1) == BASE and set(c1) == BASE | {"pops"}, "data dict keys exactly as the contract (cloud adds pops)")
IKEYS = {"id", "source", "provider", "kind", "title", "summary", "lang", "url", "ts", "ts_ms", "start_ms", "end_ms",
         "active", "severity", "status", "regions", "where", "cc", "ll", "place", "tags", "metric"}
check(all(set(i) == IKEYS for d in (w1, c1) for i in d["items"]), "item keys exactly as the contract")
check(all(set(s) == {"name", "label", "ok", "error", "checked", "good", "newest", "n", "active"} for d in (w1, c1) for s in d["sources"])
      and [s["name"] for s in w1["sources"]] == list(S.FEED_SOURCES["websites"]) + list(S.FEED_RADAR["websites"])
      and [s["name"] for s in c1["sources"]] == list(S.FEED_SOURCES["cloud"]) + list(S.FEED_RADAR["cloud"]),
      "source rows: contract keys, one per source, then the Radar rows (1.5.5)")
check(all(set(b) == {"source", "provider", "status", "active", "url"} for d in (w1, c1) for b in d["board"])
      and set(c1["pops"]) == {"total", "partial_outage", "under_maintenance", "named"}, "board rows and pops keys")
check(w1["version"] == "1.1" and w1["fetched_at"] == "2026-11-21T05:00:00Z" and w1["public_ok"] is False
      and w1["non_commercial"] is True and w1["count"] == len(w1["items"]) and w1["trimmed"] == 0
      and len(w1["summary"]) <= 700 and "\n" not in w1["note"] and "\n" not in c1["note"] and w1["attribution"],
      "envelope: version, UTC fetched_at, flags, count, summary <= 700, one-paragraph note")
allit = w1["items"] + c1["items"]
check(all(i["ts_ms"] <= NT * 1000 and (i["start_ms"] or 0) <= NT * 1000 for i in allit), "never a future item")
check(all(i["lang"] == "en" and len(i["title"]) <= 240 and (i["summary"] is None or (len(i["summary"]) <= 400 and "<" not in i["summary"]))
          and i["severity"] in ("critical", "major", "minor", "maintenance", "info")
          and i["status"] in ("investigating", "identified", "monitoring", "resolved", "in effect", None)
          and i["metric"] is None and i["ts"] == S._iso(i["ts_ms"] // 1000) for i in allit),
      "item fields: English, clipped plain text, severity / status vocabularies, UTC ts")
check([i["ts_ms"] for i in c1["items"]] == sorted((i["ts_ms"] for i in c1["items"]), reverse=True), "items newest first")
check(all(i["active"] or i["ts_ms"] >= (NT - 72 * 3600) * 1000 for i in allit)
      and all(not i["active"] or (i["start_ms"] or i["ts_ms"]) >= (NT - 30 * 86400) * 1000 for i in allit),
      "window: 72 h, plus active items up to 30 days old")
ids_c = {i["id"] for i in c1["items"]}
check("cloud:digitalocean:synskew" in ids_c and [i for i in c1["items"] if i["id"] == "cloud:digitalocean:synskew"][0]["ts_ms"] == NT * 1000
      and not ids_c & {"cloud:digitalocean:synfuture", "cloud:digitalocean:synstale", "cloud:digitalocean:synoldres",
                       "cloud:digitalocean:synmaintlater", "cloud:digitalocean:synmaintdone"},
      "skewed timestamp clamped to now; future, stale, old, scheduled and completed dropped")
mi = [i for i in c1["items"] if i["id"] == "cloud:digitalocean:synmaintnow"][0]
check(mi["active"] and mi["severity"] == "maintenance" and mi["status"] == "in effect" and mi["where"] == "Frankfurt, DE",
      "in-progress maintenance kept as severity maintenance")
da = [i for i in c1["items"] if i["id"] == "cloud:digitalocean:synactive1"][0]
check(da["where"] == "New York, US; Amsterdam, NL" and da["cc"] == ["USA", "NLD"] and da["regions"] == ["NYC3", "AMS3"]
      and da["place"] == "region" and da["ll"] == [-74.01, 40.71], "region components pinned at their metros")
cfi = [i for i in c1["items"] if i["source"] == "cloudflare"]
check(len(cfi) == 1 and cfi[0]["place"] == "pop" and c1["pops"] == {"total": 8, "partial_outage": 3, "under_maintenance": 2,
                                                                    "named": ["IAD"]}
      and cfi[0]["provider"] == "Cloudflare network (PoPs)" and "pop" in cfi[0]["tags"],
      "cloud: Cloudflare IAD incident pinned at the PoP; pops counts; partial_outage PoPs not pinned")
wcf = [i for i in w1["items"] if i["source"] == "cloudflare"]
check(len(wcf) == 1 and wcf[0]["place"] == "hq" and wcf[0]["where"] == "Global (HQ: San Francisco)" and wcf[0]["cc"] == []
      and wcf[0]["active"], "websites: Cloudflare Workers incident at the HQ, cc empty")
check(all(i["kind"] == "news" and not i["active"] and i["status"] is None for i in c1["items"] if i["source"] == "register")
      and len([i for i in c1["items"] if i["source"] == "register"]) == 4, "news items: kind news, never active, status null")
# GeoJSON
feats = c1["geojson"]["features"]
per = {}
for f in feats:
    per[f["properties"]["pid"]] = per.get(f["properties"]["pid"], 0) + 1
check(c1["geojson"]["type"] == "FeatureCollection" and per["cloud:digitalocean:synactive1"] == 2
      and all(f["geometry"]["type"] == "Point" and f["properties"]["layer"] == "cloud" and "summary" not in f["properties"]
              and "metric" not in f["properties"] and f["properties"]["pid"] == f["properties"]["id"] for f in feats)
      and set(per) == {i["id"] for i in c1["items"] if i["ll"]} and len(feats) == sum(per.values()),
      "GeoJSON: one Point per (item, place), properties = item minus summary/metric plus layer and pid; unplaced items absent")
check(not [i for i in c1["items"] if i["ll"] is None and i["id"] in per] and
      any(i["ll"] is None for i in c1["items"]), "the unplaced news item has no feature")
# board
bw = {b["source"]: b for b in w1["board"]}
bc = {b["source"]: b for b in c1["board"]}
check(bc["digitalocean"]["status"] == "major" and bc["azure"]["status"] == "partial" and bc["linode"]["status"] == "degraded"
      and bc["openai"]["status"] == "operational" and bw["slack"]["status"] == "partial" and bw["github"]["status"] == "operational"
      and bc["digitalocean"]["active"] == 4 and bc["cloudflare"]["provider"] == "Cloudflare network (PoPs)",
      "board: critical -> major, major -> partial, minor -> degraded, none -> operational")
order = [S.BOARD_RANK[b["status"]] for b in c1["board"]]
check(order == sorted(order) and not any(b["source"] in ("dcd", "dck", "register") for b in c1["board"])
      and len(c1["board"]) == len(S.FEED_SOURCES["cloud"]) - 3, "board worst first, one row per status source")
nact = sum(1 for i in c1["items"] if i["active"])
check(c1["summary"].startswith("%d active: DigitalOcean (critical): Control panel & API unavailable;" % nact)
      and "+%d more" % (nact - 5) in c1["summary"] and "Cloudflare PoPs: 3 of 8 partial outage" in c1["summary"]
      and "4 datacenter incident headlines" in c1["summary"], "summary: active incidents worst first, PoP and news counts")
st = state()
check(set(st["sources"]) == set(S.SOURCES) and st["version"] == "1.1"
      and not os.path.exists(os.path.join(TMP, "cache", S.STATE_FILE + ".tmp")), "state saved atomically with every source")

# ids stable
log = []
w2 = S.websites(now=NOW + dt.timedelta(seconds=600), fetch=fake(log=log))
c2 = S.cloud(now=NOW + dt.timedelta(seconds=600), fetch=fake(log=log))
check(log and {i["id"] for i in w2["items"]} == {i["id"] for i in w1["items"]}
      and {i["id"] for i in c2["items"]} == {i["id"] for i in c1["items"]}, "ids stable across two polls")
reset()
c3 = S.cloud(now=NOW, fetch=fake())
check([i["id"] for i in c3["items"]] == [i["id"] for i in c1["items"]], "ids stable from a fresh state")

# window cap
reset()
many = {"page": {}, "incidents": [
    {"id": "bulk%03d" % n, "name": "Bulk incident %d in NYC1 " % n + "x" * 150, "status": "resolved", "impact": "minor",
     "created_at": S._iso(NT - 3600 - n * 300), "updated_at": S._iso(NT - 60 - n * 300), "resolved_at": S._iso(NT - 60 - n * 300),
     "components": [{"name": "NYC1"}], "incident_updates": [{"status": "resolved", "body": "y" * 600,
                                                            "created_at": S._iso(NT - 60 - n * 300)}]}
    for n in range(500)] + [
    {"id": "bulkactive", "name": "Old but active", "status": "investigating", "impact": "major",
     "created_at": S._iso(NT - 20 * 86400), "updated_at": S._iso(NT - 20 * 86400), "resolved_at": None,
     "components": [], "incident_updates": []}]}
cb = S.cloud(now=NOW, fetch=fake(over={"digitalocean": json.dumps(many).encode()}))
check(cb["count"] <= 400 and cb["trimmed"] > 0 and cb["count"] + cb["trimmed"] >= 500 and SIZE(cb) <= S.MAX_BYTES
      and "cloud:digitalocean:bulkactive" in {i["id"] for i in cb["items"]},
      "cap: <= 400 items and <= 300 KB (%d items, %d trimmed, %d bytes); active items kept" % (cb["count"], cb["trimmed"], SIZE(cb)))
check([i["ts_ms"] for i in cb["items"]] == sorted((i["ts_ms"] for i in cb["items"]), reverse=True)
      and min(i["ts_ms"] for i in cb["items"] if not i["active"]) > min(
          S._ts(x["updated_at"]) for x in many["incidents"]) * 1000, "cap drops the oldest resolved items first")

# failing sources
reset()
wf = S.websites(now=NOW, fetch=fake(fail=("discord", "reddit")))
sw = {s["name"]: s for s in wf["sources"]}
check(not sw["discord"]["ok"] and "HTTPError" in sw["discord"]["error"] and sw["discord"]["good"] is None
      and sw["github"]["ok"] and {b["source"]: b["status"] for b in wf["board"]}["discord"] == "unknown"
      and wf["count"] > 0, "a failing source does not fail the feed; its board row is unknown")
reset()
check(raises(lambda: S.websites(now=NOW, fetch=fake(fail=tuple(S.SOURCES))), RuntimeError, "no source has answered yet"),
      "no source ever answered -> RuntimeError")
reset()
S.websites(now=NOW, fetch=fake())
later = NOW + dt.timedelta(seconds=700)
wk = S.websites(now=later, fetch=fake(fail=("slack",)))
sk = {s["name"]: s for s in wk["sources"]}
check(not sk["slack"]["ok"] and sk["slack"]["good"] == "2026-11-21T05:00:00Z" and any(i["source"] == "slack" for i in wk["items"])
      and {b["source"]: b["status"] for b in wk["board"]}["slack"] == "partial",
      "after a success, a failing source keeps its last good data")
reset()
log = []
try:
    S.cloud(now=NOW, fetch=fake(fail=tuple(S.SOURCES), log=log))
except RuntimeError:
    pass
check(len(log) == 3, "3 failures in a row end a poll's fetching (%d calls)" % len(log))
reset()
ticks = iter(range(0, 10000, 20))
log = []
S.cloud(now=NOW, fetch=fake(log=log), clock=lambda: next(ticks))
check(len(log) == 2, "the 45 s time budget ends a slow poll early (20 s per call: %d calls)" % len(log))

# due / retry cadence
reset()
S.websites(now=NOW, fetch=fake())
S.cloud(now=NOW, fetch=fake(fail=("dcd", "aws")))


def due_after(feed, sec, fail=()):
    log = []
    S.poll(feed, now=NOW + dt.timedelta(seconds=sec), fetch=fake(log=log, fail=fail))
    return set(log)


st0 = copy.deepcopy(state())


def restore():
    with open(os.path.join(TMP, "cache", S.STATE_FILE), "w", encoding="utf-8") as fh:
        json.dump(st0, fh)


check(due_after("websites", 100) == set(), "nothing is due 100 s later")
restore()
d240 = due_after("websites", 240)
check(d240 == {k for k in S.FEED_SOURCES["websites"] if S.SOURCES[k]["every"] == 300},
      "300 s sources due after 240 s (SLACK 60): %s" % sorted(d240))
restore()
d540 = due_after("websites", 540)
check("github" in d540 and "jira" in d540 and "cloudflare" not in d540, "600 s sources due after 540 s; Cloudflare (900 s) not")
restore()
check("cloudflare" in due_after("websites", 840), "Cloudflare due after 840 s")
restore()
dc = due_after("cloud", 240)
check("aws" in dc and "dcd" not in dc and "linode" not in dc, "failed AWS retried after 240 s; failed news waits for 900 s; Linode 900 s")
restore()
check("dcd" in due_after("cloud", 840) and "dck" not in due_after("cloud", 845), "failed news retried after 840 s; good news waits 1800 s")
restore()
S._INFLIGHT.add("github")
check("github" not in due_after("websites", 600), "a source in flight for the other feed is not fetched twice")
S._INFLIGHT.clear()

# conditional GET
reset()
vals = {}
etag_body = {"status": 200, "body": RAW["github.json"], "etag": 'W/"gh1"', "lm": None}
S.websites(now=NOW, fetch=fake(over={"github": etag_body}, validators=vals))
check(vals["github"] == (None, None), "first fetch: no validators")
S.websites(now=NOW + dt.timedelta(seconds=600), fetch=fake(over={"github": {"status": 304}}, validators=vals))
st1 = state()["sources"]["github"]
wv = S.websites(now=NOW + dt.timedelta(seconds=601), fetch=fake())
check(vals["github"] == ('W/"gh1"', None) and st1["not_modified"] and st1["ok"] and st1["etag"] == 'W/"gh1"'
      and len([i for i in wv["items"] if i["source"] == "github"]) == 3, "ETag sent back; 304 keeps the cached incidents")

# live-only lists: a vanished incident is resolved at that poll
reset()
S.cloud(now=NOW, fetch=fake())
gone = copy.deepcopy(J["cloudflare.json"])
gone["incidents"] = [i for i in gone["incidents"] if i["id"] != "oz6to8yacrxe"]
t2 = NOW + dt.timedelta(seconds=900)
c4 = S.cloud(now=t2, fetch=fake(over={"cloudflare": json.dumps(gone).encode()}))
iad = [i for i in c4["items"] if i["id"] == "cloud:cloudflare:oz6to8yacrxe"]
check(iad and not iad[0]["active"] and iad[0]["status"] == "resolved" and "cleared" in iad[0]["tags"]
      and iad[0]["end_ms"] == int(t2.timestamp()) * 1000 and c4["pops"]["named"] == [],
      "Cloudflare: an incident gone from summary.json is resolved then and kept")
reset()
S.websites(now=NOW, fetch=fake())
w5 = S.websites(now=NOW + dt.timedelta(seconds=300), fetch=fake(over={"slack": RAW["slack.json"], "m365": RAW["m365.json"]}))
check(all(not i["active"] and "cleared" in i["tags"] for i in w5["items"] if i["source"] in ("slack", "m365"))
      and len([i for i in w5["items"] if i["source"] in ("slack", "m365")]) == 2, "Slack / M365: cleared incidents resolved")
reset()
S.cloud(now=NOW, fetch=fake())
az_empty = re.sub(rb"(?s)<item>.*</item>", b"", RAW["azure.rss"])
c6 = S.cloud(now=NOW + dt.timedelta(seconds=300), fetch=fake(over={"azure": az_empty}))
azi = [i for i in c6["items"] if i["source"] == "azure"]
check(len(azi) == 2 and all(not i["active"] and i["status"] == "resolved" for i in azi)
      and any("cleared" in i["tags"] for i in azi), "Azure: an item gone from the feed is resolved then")

# board: maintenance only, info only
reset()
mo = {"page": {}, "incidents": [i for i in J["statuspage_synthetic.json"]["incidents"] if i["id"] in ("synmaintnow", "synres")]}
info = {"page": {}, "incidents": [dict(J["statuspage_synthetic.json"]["incidents"][0], id="infoonly", impact="none")]}
cm = S.cloud(now=NOW, fetch=fake(over={"digitalocean": json.dumps(mo).encode(), "linode": json.dumps(info).encode()}))
bm = {b["source"]: b for b in cm["board"]}
check(bm["digitalocean"]["status"] == "maintenance" and bm["linode"]["status"] == "operational" and bm["linode"]["active"] == 1,
      "board: maintenance only -> maintenance; info only -> operational (with its active count)")

print("     websites summary:", w1["summary"])
print("     cloud summary:   ", c1["summary"])
print("%d checks passed" % ok)
