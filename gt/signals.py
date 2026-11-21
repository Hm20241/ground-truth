"""Signals: radiation, tsunami and volcano bulletins, US sanctions actions, US terrorism advisories.
v1.0, 2026-11-20 (Ground Truth 0.13.0). All keyless, all outbound GETs.

Feed `radiation` (hourly): BfS ODL gamma network, Germany (WFS layer opendata:odlinfo_odl_1h_latest, ~1,670
stations, 1-hour means in uSv/h). A per-station history of up to 168 hourly values (7 days) lives in
<GT_DATA>/cache/signals_radiation.json (values in nSv/h, ~1 MB); the baseline is the median of a station's earlier
values (the current hour excluded), used once there are 6. A station is flagged when its value is >= 2x its baseline
AND >= 0.3 uSv/h; without its own baseline yet, the network baseline (or the current network median) stands in. The
network is flagged when the median of the fresh stations is >= 30 % above the median of its own earlier hourly
medians. Only stations "in Betrieb" (site_status 1) with a value count; "fresh" = measured within 3 h of the newest
station. Output: a summary plus the flagged stations, never all 1,670. Rain washes radon progeny down and can lift a
station by 0.05-0.15 uSv/h for an hour or two: that stays under the 0.3 floor almost everywhere.

Feed `tsunami` (every 10 min): NOAA PTWC (PHEBAtom.xml) and NTWC (PAAQAtom.xml) Atom feeds, which hold only the
latest bulletin each, plus JMA's long earthquake/volcano Atom feed eqvol_l.xml (7 days, 10 KB gzipped). Bulletins are
kept for 72 h in <GT_DATA>/cache/signals_tsunami.json so a PTWC bulletin survives the next one. JMA titles are
Japanese; only tsunami and volcano bulletins are kept (routine scheduled ashfall forecasts 降灰予報 and plume-direction
reports are not), each mapped to an English label and a level from its text (NFKC-normalised: full-width digits).
Levels: warning / advisory / watch / information.

Feed `ofac` (hourly): the list page https://ofac.treasury.gov/recent-actions (10 rows a page; `?page=1` next), rows
from the last 30 days, at most 4 pages. Program tags (russia, iran, counter-narcotics, ...) come from the title.

Feed `ntas` (hourly): DHS National Terrorism Advisory System, https://www.dhs.gov/ntas/1.1/feed.xml. Empty
(`<alerts></alerts>`) on 2026-11-20. The 1.1 schema, from the feed itself while bulletins ran (2016, 2023 captures):
<alert start="YYYY/MM/DD HH:MM:SS" end="..." type="Bulletin Threat" href="...pdf"> with <summary> and <details> (raw,
not escaped, HTML), <locations><location>, <sectors><sector>, <duration>, optional <detail_sections>. Times are US
Eastern ("This Bulletin will expire on May 24, 2023 at 2:00 PM ET" for end="2023/05/24 14:00:00"). Parsed with
regular expressions, not an XML parser, because the embedded HTML need not be well-formed.

Probed 2026-11-20 05:22Z: BfS 887 KB JSON (gzip), 1,672 features, 1,555 in Betrieb with a value, network median
0.107 uSv/h, max 0.223, newest end_measure 04:00Z (an hour behind). PHEB newest 2026-11-18 02:30Z (M5.9 SW of Guam,
Information); PAAQ newest 2026-11-13 23:30Z; both feeds' <link rel="self"> point at PAAQAtom.xml (a PTWC quirk).
JMA: extra.xml, which the plan named, carries only weather warnings (604 entries, all 気象/竜巻/土砂); tsunami and
volcano bulletins are in eqvol.xml (10 h) and eqvol_l.xml (7 days: 280 降灰予報（定時）, 10 火山の状況に関する解説情報,
earthquake reports), so this module reads eqvol_l.xml. OFAC: newest /recent-actions/20261119; a second row on one
day gets a suffix (/recent-actions/20261013_33); 10 rows a page reach 2026-10-27. All answered an honest UA.

Terms: BfS: free licences (dl-de/by-2-0 or GeoNutzV, imis.bfs.de/geoportal sitepolicy; WFS AccessConstraints NONE),
attribution required. NOAA, Treasury and DHS: US public domain. JMA: Public Data License 1.0, compatible with CC BY 4.0;
cite "Source: Japan Meteorological Agency website (URL)" and say when content is edited (the English labels and levels
here are edited); JMA warnings are relayed with credit, Ground Truth never issues its own. All fine for the public
mirror with the credits below.
"""
import datetime as dt
import gzip
import html
import json
import os
import re
import statistics
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

from . import geo

VERSION = "1.0"
UA = "GroundTruth/0.13 (personal non-commercial OSINT dashboard)"
TIMEOUT = 30

ATTRIBUTION = {
    "bfs": "Bundesamt für Strahlenschutz (BfS), ODL-Messnetz, odlinfo.bfs.de, Datenlizenz Deutschland "
           "Namensnennung 2.0 (dl-de/by-2-0)",
    "ptwc": "NOAA/NWS Pacific Tsunami Warning Center, tsunami.gov (public domain)",
    "ntwc": "NOAA/NWS National Tsunami Warning Center, tsunami.gov (public domain)",
    "jma": "Source: Japan Meteorological Agency website (https://www.data.jma.go.jp/developer/xml/feed/eqvol_l.xml); "
           "English labels and levels added by Ground Truth (edited)",
    "ofac": "U.S. Department of the Treasury, Office of Foreign Assets Control, ofac.treasury.gov (public domain)",
    "ntas": "U.S. Department of Homeland Security, National Terrorism Advisory System, dhs.gov/ntas (public domain)",
}
LICENCE = {
    "radiation": "BfS open data, dl-de/by-2-0 (attribution required)",
    "tsunami": "NOAA public domain; JMA Public Data License 1.0 / CC BY 4.0 compatible (source credit, edits marked)",
    "ofac": "US Government work, public domain",
    "ntas": "US Government work, public domain",
}
NON_COMMERCIAL = {"radiation": False, "tsunami": False, "ofac": False, "ntas": False}
PUBLIC_OK = {"radiation": True, "tsunami": True, "ofac": True, "ntas": True}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")   # same folder as gt/feeds.py CACHE

# ---------------- radiation ----------------
BFS_URL = ("https://www.imis.bfs.de/ogc/opendata/ows?service=WFS&version=2.0.0&request=GetFeature"
           "&typeName=opendata:odlinfo_odl_1h_latest&outputFormat=application/json")
HIST_MAX = 168          # hourly values kept per station (7 days)
MIN_SAMPLES = 6         # earlier values needed before a baseline counts
FLAG_RATIO = 2.0
FLAG_MIN_USV = 0.3
NET_JUMP = 0.30
FRESH_H = 3             # a station counts when measured within 3 h of the newest station
STALE_H = 4             # the whole network is "stale" when its newest value is older than this
FLAG_MAX = 200
RAD_NOTE = ("BfS gamma dose rate (1-hour mean, uSv/h), Germany. Station flag: >= 2x its own 7-day median and "
            ">= 0.3 uSv/h. Network flag: median >= 30 % above its 7-day median. Rain can lift stations briefly.")

# ---------------- tsunami / volcano ----------------
PTWC_FEEDS = (("PTWC", "ptwc", "https://www.tsunami.gov/events/xml/PHEBAtom.xml"),
              ("NTWC", "ntwc", "https://www.tsunami.gov/events/xml/PAAQAtom.xml"))
JMA_URL = "https://www.data.jma.go.jp/developer/xml/feed/eqvol_l.xml"
TSUNAMI_HOURS = 72
LEVELS = ("warning", "advisory", "watch", "information")
ATOM = "{http://www.w3.org/2005/Atom}"
GEO_NS = "{http://www.w3.org/2003/01/geo/wgs84_pos#}"
PTWC_FIELDS = ("Category", "Bulletin Issue Time", "Preliminary Magnitude", "Lat/Lon", "Affected Region", "Note",
               "Definition")
# JMA Atom titles -> (kind, English label). Anything else with 津波 / 噴火 / 火山 is kept with a generic label.
JMA_TITLES = {
    "津波警報・注意報・予報a": ("tsunami", "Tsunami warning / advisory / forecast"),
    "津波情報a": ("tsunami", "Tsunami information (arrival times and heights)"),
    "沖合の津波観測に関する情報": ("tsunami", "Offshore tsunami observations"),
    "北西太平洋津波情報": ("tsunami", "Northwest Pacific tsunami information"),
    "噴火警報・予報": ("volcano", "Volcanic warning / forecast"),
    "噴火速報": ("volcano", "Eruption flash report"),
    "噴火に関する火山観測報": ("volcano", "Eruption observation report"),
    "火山の状況に関する解説情報": ("volcano", "Volcanic activity commentary"),
    "火山現象に関する海上警報・海上予報": ("volcano", "Marine volcanic warning / forecast"),
}
JMA_SKIP = ("降灰予報", "推定噴煙流向報")
# Volcano names as JMA writes them -> (English, lat, lon); positions are summit approximations (2 decimals).
VOLCANOES = {
    "桜島": ("Sakurajima", 31.58, 130.66), "霧島山": ("Kirishimayama", 31.93, 130.87),
    "霧島山(新燃岳)": ("Kirishimayama (Shinmoedake)", 31.91, 130.88),
    "霧島山(御鉢)": ("Kirishimayama (Ohachi)", 31.89, 130.90), "阿蘇山": ("Asosan", 32.88, 131.10),
    "諏訪之瀬島": ("Suwanosejima", 29.64, 129.71), "口永良部島": ("Kuchinoerabujima", 30.44, 130.22),
    "薩摩硫黄島": ("Satsuma-Iojima", 30.79, 130.31), "浅間山": ("Asamayama", 36.41, 138.52),
    "草津白根山": ("Kusatsu-Shiranesan", 36.62, 138.53), "御嶽山": ("Ontakesan", 35.89, 137.48),
    "富士山": ("Fujisan", 35.36, 138.73), "箱根山": ("Hakoneyama", 35.23, 139.02),
    "伊豆大島": ("Izu-Oshima", 34.72, 139.40), "三宅島": ("Miyakejima", 34.08, 139.53),
    "西之島": ("Nishinoshima", 27.25, 140.88), "硫黄島": ("Ioto", 24.75, 141.29),
    "福徳岡ノ場": ("Fukutoku-Okanoba", 24.28, 141.48), "十勝岳": ("Tokachidake", 43.42, 142.69),
    "北海道駒ヶ岳": ("Hokkaido-Komagatake", 42.06, 140.68), "有珠山": ("Usuzan", 42.54, 140.84),
    "樽前山": ("Tarumaesan", 42.69, 141.38), "雌阿寒岳": ("Meakandake", 43.39, 144.01),
    "蔵王山": ("Zaozan", 38.14, 140.44), "吾妻山": ("Azumayama", 37.73, 140.24),
    "焼岳": ("Yakedake", 36.23, 137.59), "雲仙岳": ("Unzendake", 32.76, 130.29),
    "鶴見岳・伽藍岳": ("Tsurumidake and Garandake", 33.29, 131.43), "九重山": ("Kujusan", 33.09, 131.25),
}
JAPAN = {"country": "JPN", "country_name": "Japan", "sea": None, "theatre": "indo-pacific"}

# ---------------- OFAC ----------------
OFAC_URL = "https://ofac.treasury.gov/recent-actions"
OFAC_DAYS = 30
OFAC_MAX_PAGES = 4
PROGRAMS = (   # (tag, regex on the lower-cased title, ISO3 for the map or None)
    ("counter-narcotics", r"counter ?narcotics|illicit drug|narcotic|fentanyl|kingpin", None),
    ("counter-terrorism", r"counter ?terrorism|terroris", None),
    ("russia", r"russia", "RUS"), ("iran", r"\biran", "IRN"), ("dprk", r"north korea|\bdprk\b", "PRK"),
    ("cyber", r"cyber", None), ("venezuela", r"venezuela", "VEN"), ("cuba", r"\bcuba", "CUB"),
    ("syria", r"\bsyria", "SYR"), ("belarus", r"belarus", "BLR"), ("china", r"\bchin(a|ese)\b|hong kong", "CHN"),
    ("burma", r"burma|myanmar", "MMR"), ("south-sudan", r"south sudan", "SSD"),
    ("sudan", r"(?<!south )sudan", "SDN"), ("yemen", r"yemen|houthi", "YEM"), ("iraq", r"\biraq", "IRQ"),
    ("lebanon", r"lebanon|hizballah|hezbollah", "LBN"), ("libya", r"libya", "LBY"), ("somalia", r"somalia", "SOM"),
    ("mali", r"\bmali\b", "MLI"), ("drc", r"congo", "COD"), ("car", r"central african", "CAF"),
    ("ethiopia", r"ethiopia", "ETH"), ("nicaragua", r"nicaragua", "NIC"), ("balkans", r"balkans", None),
    ("afghanistan", r"afghanistan|taliban", "AFG"), ("haiti", r"haiti", "HTI"), ("zimbabwe", r"zimbabwe", "ZWE"),
    ("west-bank", r"west bank", "PSX"), ("tco", r"transnational criminal", None),
    ("magnitsky", r"magnitsky", None), ("non-proliferation", r"non-?proliferation|weapons of mass destruction", None),
    ("hostages", r"hostage", None), ("election-interference", r"election", None),
    ("icc", r"international criminal court", None), ("paipa", r"intellectual property|paipa", None),
)
ACTIONS = (("designation", r"designation"), ("removal", r"removal|delisting|deletion"),
           ("general-license", r"general licen[cs]e"), ("faq", r"frequently asked"),
           ("enforcement", r"settlement|enforcement|penalt|finding of violation"),
           ("advisory", r"advisory|alert\b|guidance"), ("determination", r"determination"),
           ("update", r"\bupdate"))

# ---------------- NTAS ----------------
NTAS_URL = "https://www.dhs.gov/ntas/1.1/feed.xml"
NTAS_RANK = {"imminent": 0, "elevated": 1, "bulletin": 2}


# ---------------- helpers ----------------

def _gunzip(b):
    b = b or b""
    return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return _gunzip(r.read())


def _utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def parse_ts(s):
    """ISO-8601 -> aware UTC datetime or None; 'Z', offsets, no zone (= UTC), any number of fractional digits."""
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d)(?:\.(\d+))?)?)?\s*(Z|[+-]\d\d:?\d\d)?$",
                 str(s).strip())
    if not m:
        return None
    y, mo, d, h, mi, sec, frac, tz = m.groups()
    try:
        t = dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(sec or 0),
                        int((frac or "0")[:6].ljust(6, "0")), tzinfo=dt.timezone.utc)
    except ValueError:
        return None
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        t -= sign * dt.timedelta(hours=int(tz[1:3]), minutes=int(tz[-2:]))
    return t


def _err(e):
    return "%s: %s" % (type(e).__name__, str(e)[:200])


def _src(name, ok, error=None, newest=None, n=0):
    return {"name": name, "ok": ok, "error": error, "newest": newest, "n": n}


def _locate(lon, lat):
    try:
        g = geo.locate(lon, lat) or {}
    except Exception:
        g = {}
    return {"country": g.get("country"), "country_name": g.get("country_name"), "sea": g.get("sea"),
            "theatre": g.get("theatre") or "other"}


def _path(name):
    return os.path.join(CACHE, "signals_%s.json" % name)


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
        json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, _path(name))


def _text(s):
    """Markup -> plain text: tags out, entities decoded, whitespace collapsed."""
    s = re.sub(r"<(br|/p|/li|/h\d|/div)\b[^>]*>", " ", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(html.unescape(s).replace(" ", " ").split())


def _title(s):
    """Whitespace collapsed; ALL-CAPS text (PTWC) title-cased."""
    s = " ".join(str(s or "").split())
    return s.title() if s.isupper() else s


def _cut(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _median(xs):
    return statistics.median(xs) if xs else None


def _fc(feats):
    return {"type": "FeatureCollection", "features": feats}


def _pt(lon, lat, props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 3), round(lat, 3)]},
            "properties": props}


def _base(feed, keys, sources, now):
    return {"version": VERSION, "fetched_at": _iso(now), "sources": sources,
            "attribution": [ATTRIBUTION[k] for k in keys], "licence": LICENCE[feed], "public_ok": PUBLIC_OK[feed],
            "non_commercial": NON_COMMERCIAL[feed]}


def _all_failed(feed, sources):
    if not any(s["ok"] for s in sources):
        raise RuntimeError("%s: every source failed: %s" % (feed, "; ".join(s["error"] or "?" for s in sources)))


# ---------------- radiation ----------------

def bfs_stations(body):
    d = json.loads(_gunzip(body))
    feats = d.get("features") if isinstance(d, dict) else None
    if not isinstance(feats, list):
        raise ValueError("BfS: response without features")
    out = []
    for f in feats:
        p = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates") or []
        if not p.get("id") or len(c) < 2:
            continue
        v = p.get("value")
        try:
            v = float(v) if v is not None else None
        except (TypeError, ValueError):
            v = None
        out.append({"id": str(p["id"]), "name": p.get("name"), "lon": float(c[0]), "lat": float(c[1]),
                    "status": p.get("site_status"), "value": v, "end": parse_ts(p.get("end_measure"))})
    return out


def _step(rec, h, v):
    """Add value v (nSv/h) for hour h to a [last_hour, values] record; return (record, earlier values)."""
    last, vals = (rec if isinstance(rec, list) and len(rec) == 2 and isinstance(rec[1], list) else (None, []))
    vals = [x for x in vals if isinstance(x, int)]
    if last is None or h > last:
        prior = vals[-HIST_MAX:]
        vals = (vals + [v])[-HIST_MAX:]
        last = h
    elif h == last and vals:
        prior = vals[:-1]
        vals[-1] = v           # BfS may revise the hour once validated
    else:
        prior = vals           # an older hour than recorded: use it, keep history as is
    return [last, vals], prior


def radiation(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    try:
        st = bfs_stations(fetch(BFS_URL))
        if not st:
            raise ValueError("BfS: no stations")
    except Exception as e:
        raise RuntimeError("radiation: every source failed: BfS ODL: %s" % _err(e))
    cache = _load("radiation")
    hist = cache.get("stations") if isinstance(cache.get("stations"), dict) else {}
    net = [x for x in (cache.get("network") or []) if isinstance(x, list) and len(x) == 2]
    now_h = int(now.timestamp() // 3600)

    live = [s for s in st if s["status"] == 1 and s["value"] is not None and s["end"] is not None]
    newest = max((s["end"] for s in live), default=None)
    for s in live:
        h = int(s["end"].timestamp() // 3600)
        hist[s["id"]], prior = _step(hist.get(s["id"]), h, int(round(s["value"] * 1000)))
        s["baseline"] = _median(prior) / 1000.0 if len(prior) >= MIN_SAMPLES else None
    fresh = [s for s in live if newest - s["end"] <= dt.timedelta(hours=FRESH_H)]

    med = _median([s["value"] for s in fresh])
    net_base, change, prior_net = None, None, []
    if med is not None:
        h, v = int(newest.timestamp() // 3600), int(round(med * 1000))
        if not net or h > net[-1][0]:
            prior_net = [x[1] for x in net]
            net.append([h, v])
        elif h == net[-1][0]:
            prior_net = [x[1] for x in net[:-1]]
            net[-1] = [h, v]
        else:
            prior_net = [x[1] for x in net]
        net = net[-HIST_MAX:]
        prior_net = prior_net[-HIST_MAX:]
        if len(prior_net) >= MIN_SAMPLES:
            net_base = _median(prior_net) / 1000.0
            change = (med - net_base) / net_base if net_base else None
    net_flag = change is not None and change >= NET_JUMP

    flagged = []
    for s in fresh:
        base, kind = s["baseline"], "station"
        if base is None:
            base, kind = (net_base or med), "network"
        if base and s["value"] >= FLAG_MIN_USV and s["value"] >= FLAG_RATIO * base:
            flagged.append((s, base, kind))
    flagged.sort(key=lambda x: (-x[0]["value"] / x[1], x[0]["id"]))
    feats = []
    for s, base, kind in flagged[:FLAG_MAX]:
        props = {"id": s["id"], "name": s["name"], "value_usv": round(s["value"], 3), "baseline_usv": round(base, 3),
                 "baseline_kind": kind, "ratio": round(s["value"] / base, 2), "measured": _iso(s["end"]),
                 "source": "BfS"}
        props.update(_locate(s["lon"], s["lat"]))
        feats.append(_pt(s["lon"], s["lat"], props))

    for k in [k for k, r in hist.items() if not isinstance(r, list) or r[0] is None or r[0] < now_h - HIST_MAX]:
        del hist[k]
    _save("radiation", {"v": 1, "saved": _iso(now), "stations": hist, "network": net[-HIST_MAX:]})

    top = max(fresh, key=lambda s: s["value"]) if fresh else None
    summary = {
        "stations": len(st), "reporting": len(live), "fresh": len(fresh),
        "not_operating": sum(1 for s in st if s["status"] != 1),
        "measured_until": _iso(newest), "stale": newest is None or now - newest > dt.timedelta(hours=STALE_H),
        "network_median_usv": round(med, 3) if med is not None else None,
        "network_baseline_usv": round(net_base, 3) if net_base is not None else None,
        "network_change_pct": int(round(change * 100)) if change is not None else None,
        "network_flag": net_flag, "network_baseline_hours": len(prior_net),
        "stations_with_baseline": sum(1 for s in fresh if s["baseline"] is not None),
        "flagged": len(flagged),
        "max": ({"id": top["id"], "name": top["name"], "value_usv": round(top["value"], 3),
                 "baseline_usv": round(top["baseline"], 3) if top["baseline"] is not None else None,
                 "lon": round(top["lon"], 3), "lat": round(top["lat"], 3)} if top else None),
        "thresholds": {"ratio": FLAG_RATIO, "min_usv": FLAG_MIN_USV, "network_jump_pct": int(NET_JUMP * 100),
                       "baseline_min_samples": MIN_SAMPLES, "history_hours": HIST_MAX},
    }
    out = _base("radiation", ["bfs"], [_src("BfS ODL", True, newest=_iso(newest), n=len(live))], now)
    out.update(count=len(feats), alert=bool(feats) or net_flag, summary=summary, note=RAD_NOTE, geojson=_fc(feats))
    return out


# ---------------- tsunami and volcano bulletins ----------------

def _atom(body):
    body = _gunzip(body)
    if b"<!DOCTYPE" in body[:2048] or b"<!ENTITY" in body:
        raise ValueError("Atom feed with a DTD refused")
    root = ET.fromstring(body)
    if root.tag != ATOM + "feed":
        raise ValueError("not an Atom feed: %s" % root.tag[:60])
    return root


def _fields(text):
    labels = "|".join(re.escape(x) for x in PTWC_FIELDS)
    rx = re.compile(r"(%s):\s*(.*?)(?=\s*(?:%s):|$)" % (labels, labels))
    return {k.lower(): v.strip() for k, v in rx.findall(text)}


def _ptwc_level(cat, bulletin):
    s = "%s %s" % (cat or "", bulletin or "")
    s = s.lower()
    if "cancel" in s:
        return "information"
    if "warning" in s or "threat" in s:
        return "warning"
    if "advisory" in s:
        return "advisory"
    if "watch" in s:
        return "watch"
    return "information"


def ptwc_items(body, src):
    """PTWC/NTWC Atom -> bulletins (one per entry)."""
    root = _atom(body)
    bulletin = " ".join((root.findtext(ATOM + "title") or "").split()).title() or None
    centre = " ".join((root.findtext(ATOM + "author/" + ATOM + "name") or "").split()) or None
    out = []
    for e in root.findall(ATOM + "entry"):
        summ = e.find(ATOM + "summary")
        text = " ".join("".join(summ.itertext()).split()) if summ is not None else ""
        f = _fields(text)
        links = {(l.get("rel"), (l.get("title") or "").lower()): l.get("href") for l in e.findall(ATOM + "link")}
        issued = parse_ts(e.findtext(ATOM + "updated"))
        try:
            lat, lon = float(e.findtext(GEO_NS + "lat")), float(e.findtext(GEO_NS + "long"))
        except (TypeError, ValueError):
            lat = lon = None
        m = re.match(r"\s*([\d.]+)\s*\(?(\w*)\)?", f.get("preliminary magnitude", ""))
        cat = f.get("category") or None
        item = {"id": "%s:%s" % (src.lower(), (e.findtext(ATOM + "id") or "").strip() or _iso(issued)),
                "source": src, "kind": "tsunami", "level": _ptwc_level(cat, bulletin), "label": bulletin,
                "category": cat, "centre": centre, "region": _title(e.findtext(ATOM + "title")) or None,
                "issued": _iso(issued), "magnitude": float(m.group(1)) if m else None,
                "mag_type": (m.group(2) or None) if m else None,
                "note": _cut(f.get("note", "").strip(), 300) or None,
                "url": links.get(("alternate", "bulletin")) or next(
                    (h for (r, t), h in links.items() if r == "alternate"), None),
                "cap_url": next((h for (r, t), h in links.items() if "cap" in t), None),
                "lat": lat, "lon": lon}
        item.update(_locate(lon, lat) if lat is not None else {"country": None, "country_name": None, "sea": None,
                                                                 "theatre": "other"})
        if issued:
            out.append(item)
    return out


def _volcano(text):
    """(name as JMA writes it, (English, lat, lon) or None). Most bulletins open 【火山名 X ...】; eruption flash
    reports open <Xで噴火が発生> (NFKC turns ＜＞ into <>)."""
    m = re.search(r"火山名\s+(\S+?)\s", text) or re.search(r"<\s*([^<>\s]+?)\s*で噴火", text)
    name = m.group(1) if m else None
    if not name:
        return None, None
    hit = VOLCANOES.get(name) or VOLCANOES.get(name.split("(")[0])
    return name, hit


TSUNAMI_TERMS = (("大津波警報", "warning", "Major tsunami warning"), ("津波警報", "warning", "Tsunami warning"),
                 ("津波注意報", "advisory", "Tsunami advisory"),
                 ("津波予報", "information", "Tsunami forecast (slight sea-level change)"))


def jma_level(kind, title, text):
    """(level, cancelled, label or None) from a JMA title and its NFKC-normalised text. A heuristic: the Japanese
    title and text and the link are kept next to it. The title alone says nothing (津波警報・注意報・予報a covers all
    three), so tsunami levels come from the text: what is switched to (...に切り替え) or issued (...を発表しました)
    counts first, then a cancellation (解除; "発表していた" = had been issued), then the highest term named."""
    if kind == "tsunami":
        terms = r"((?:(?:大津波警報|津波警報|津波注意報|津波予報)(?:\([^)]*\))?[・、及びと]*)+)"
        m = (re.search(terms + r"(?:へ|に)切り?替え", text) or re.search(terms + r"を発表し(?:ました|ます)", text))
        if m:
            hit = next(t for t in TSUNAMI_TERMS if t[0] in m.group(1))
            return hit[1], False, hit[2]
        if "解除" in text:
            return "information", True, None
        for term, level, label in TSUNAMI_TERMS:
            if term in text:
                return level, False, label
        return "information", False, None
    lv = re.search(r"噴火警戒レベル\s*(\d)", text)
    lv = int(lv.group(1)) if lv else None
    if "噴火特別警報" in text or "噴火警報(居住地域)" in text or (lv or 0) >= 4:
        return "warning", False, None
    if "火口周辺警報" in text or "噴火警報(火口周辺)" in text or lv in (2, 3):
        return "advisory", False, None
    if "噴火速報" in title:
        return "watch", False, None
    return "information", False, None


def jma_items(body):
    root = _atom(body)
    out = []
    for e in root.findall(ATOM + "entry"):
        title = (e.findtext(ATOM + "title") or "").strip()
        if any(w in title for w in JMA_SKIP):
            continue
        kind, label = JMA_TITLES.get(title, (None, None))
        if kind is None:
            if "津波" in title:
                kind, label = "tsunami", "JMA tsunami bulletin"
            elif "噴火" in title or "火山" in title:
                kind, label = "volcano", "JMA volcano bulletin"
            else:
                continue
        raw = (e.findtext(ATOM + "content") or "").strip()
        text = " ".join(unicodedata.normalize("NFKC", raw).split())
        issued = parse_ts(e.findtext(ATOM + "updated"))
        link = next((l.get("href") for l in e.findall(ATOM + "link") if l.get("href")), None)
        level, cancelled, better = jma_level(kind, unicodedata.normalize("NFKC", title), text)
        lv = re.search(r"噴火警戒レベル\s*(\d)", text)
        item = {"id": "jma:" + ((e.findtext(ATOM + "id") or "").strip() or link or _iso(issued)), "source": "JMA",
                "kind": kind, "level": level, "label": (better or label) + (" (cancelled)" if cancelled else ""),
                "cancelled": cancelled, "title_ja": title,
                "office_ja": " ".join((e.findtext(ATOM + "author/" + ATOM + "name") or "").split()) or None,
                "text_ja": _cut(" ".join(raw.split()), 400), "issued": _iso(issued), "url": link,
                "alert_level": int(lv.group(1)) if (kind == "volcano" and lv) else None,
                "volcano_ja": None, "volcano": None, "lat": None, "lon": None}
        if kind == "volcano":
            name, hit = _volcano(text)
            item["volcano_ja"] = name
            if hit:
                item.update(volcano=hit[0], lat=hit[1], lon=hit[2])
        item.update(JAPAN)
        if issued:
            out.append(item)
    return out


def tsunami(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    cut = now - dt.timedelta(hours=TSUNAMI_HOURS)
    sources, fresh, used = [], [], []
    for name, key, url in PTWC_FEEDS:
        try:
            items = ptwc_items(fetch(url), name)
            fresh += items
            used.append(key)
            sources.append(_src(name, True, newest=max((i["issued"] for i in items), default=None), n=len(items)))
        except Exception as e:
            sources.append(_src(name, False, _err(e)))
    try:
        items = jma_items(fetch(JMA_URL))
        fresh += items
        used.append("jma")
        sources.append(_src("JMA", True, newest=max((i["issued"] for i in items), default=None), n=len(items)))
    except Exception as e:
        sources.append(_src("JMA", False, _err(e)))
    _all_failed("tsunami", sources)

    store = _load("tsunami").get("items")
    store = store if isinstance(store, dict) else {}
    for i in fresh:
        store[i["id"]] = i
    keep = {}
    for k, v in store.items():
        t = parse_ts(v.get("issued")) if isinstance(v, dict) else None
        if t is not None and cut < t <= now + dt.timedelta(hours=1):
            keep[k] = v
    _save("tsunami", {"v": 1, "saved": _iso(now), "items": keep})

    items = sorted(keep.values(), key=lambda i: (i["issued"], i["id"]), reverse=True)
    by_level = {lv: sum(1 for i in items if i["level"] == lv) for lv in LEVELS}
    top = next((lv for lv in LEVELS if by_level[lv]), None)
    feats = []
    for i in items:
        if i.get("lat") is not None and i.get("lon") is not None:
            props = {k: v for k, v in i.items() if k not in ("lat", "lon")}
            feats.append(_pt(i["lon"], i["lat"], props))
    out = _base("tsunami", used, sources, now)
    out.update(count=len(items), window_hours=TSUNAMI_HOURS, by_level=by_level, max_level=top,
               alert=top in ("warning", "advisory", "watch"),
               note="Tsunami (PTWC, NTWC, JMA) and Japanese volcano (JMA) bulletins from the last 72 h. JMA labels "
                    "and levels are Ground Truth's reading of the Japanese text; title_ja/text_ja are JMA's words.",
               items=items, geojson=_fc(feats))
    return out


# ---------------- OFAC recent actions ----------------

def tags_for(title):
    t = (title or "").lower()
    programs = [tag for tag, rx, _ in PROGRAMS if re.search(rx, t)]
    actions = [tag for tag, rx in ACTIONS if re.search(rx, t)]
    a3s = []
    for tag, rx, a3 in PROGRAMS:
        if a3 and tag in programs and a3 not in a3s:
            a3s.append(a3)
    return programs or ["other"], actions, a3s


def ofac_rows(page_html):
    """Rows of one recent-actions list page: (date, title, url, category). Raises when the page has no rows."""
    rows = []
    blocks = re.split(r'<div class="[^"]*\bviews-row\b[^"]*">', page_html)[1:]
    for b in blocks:
        m = re.search(r'<a href="(/recent-actions/(\d{8})(?:_\d+)?)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        path, ymd, title = m.group(1), m.group(2), _text(m.group(3))
        try:
            day = dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
        except ValueError:
            continue
        c = re.search(r'<a href="/recent-actions/[a-z][a-z0-9-]*"[^>]*>(.*?)</a>', b, re.S)
        rows.append((day, title, "https://ofac.treasury.gov" + path, _text(c.group(1)) if c else None))
    if not rows and "recent-actions" not in page_html:
        raise ValueError("OFAC: not the recent-actions list page")
    return rows


def ofac(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    cut = now.date() - dt.timedelta(days=OFAC_DAYS)
    rows, err, pages = [], None, 0
    try:
        for page in range(OFAC_MAX_PAGES):
            body = _gunzip(fetch(OFAC_URL if page == 0 else "%s?page=%d" % (OFAC_URL, page))).decode("utf-8",
                                                                                                    "replace")
            got = ofac_rows(body)
            pages += 1
            if page == 0 and not got:
                raise ValueError("OFAC: no rows on the first page")
            rows += got
            if not got or min(r[0] for r in got) < cut or 'rel="next"' not in body:
                break
    except Exception as e:
        err = _err(e)
        if not rows:
            raise RuntimeError("ofac: every source failed: OFAC recent actions: %s" % err)
    items, seen = [], set()
    for day, title, url, cat in rows:
        if day < cut or day > now.date() + dt.timedelta(days=1) or url in seen:
            continue
        seen.add(url)
        programs, actions, a3s = tags_for(title)
        theatres = []
        for a3 in a3s:
            try:
                th = geo.theatre_for_a3(a3)
            except Exception:
                th = None
            if th and th not in theatres:
                theatres.append(th)
        items.append({"date": day.isoformat(), "title": title, "url": url, "category": cat, "programs": programs,
                      "actions": actions, "countries": a3s, "theatres": theatres, "source": "OFAC"})
    items.sort(key=lambda i: (i["date"], i["url"]), reverse=True)
    counts = {}
    for i in items:
        for p in i["programs"]:
            counts[p] = counts.get(p, 0) + 1
    out = _base("ofac", ["ofac"], [_src("OFAC recent actions", err is None, err,
                                        newest=items[0]["date"] if items else None, n=len(items))], now)
    out.update(count=len(items), window_days=OFAC_DAYS, pages=pages, by_program=counts, items=items)
    return out


# ---------------- DHS NTAS ----------------

def _nth_sunday(year, month, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def eastern_to_utc(t):
    """Naive US Eastern wall time -> aware UTC (DST: 2nd Sunday of March 02:00 to 1st Sunday of November 02:00)."""
    start = dt.datetime.combine(_nth_sunday(t.year, 3, 2), dt.time(2))
    end = dt.datetime.combine(_nth_sunday(t.year, 11, 1), dt.time(2))
    off = 4 if start <= t < end else 5
    return (t + dt.timedelta(hours=off)).replace(tzinfo=dt.timezone.utc)


def _ntas_time(s):
    m = re.match(r"\s*(\d{4})[/-](\d\d)[/-](\d\d)(?:[ T](\d\d):(\d\d)(?::(\d\d))?)?", s or "")
    if not m:
        return None
    y, mo, d, h, mi, sec = m.groups()
    try:
        return eastern_to_utc(dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(sec or 0)))
    except ValueError:
        return None


def _inner(block, tag):
    m = re.search(r"<%s\b[^>]*>(.*?)</%s\s*>" % (tag, tag), block, re.S | re.I)
    return m.group(1) if m else ""


def ntas_alerts(body):
    s = _gunzip(body).decode("utf-8", "replace")
    if not re.search(r"<alerts\b", s):
        raise ValueError("NTAS: not an alerts feed")
    out = []
    for attrs, inner in re.findall(r"<alert\b([^>]*)>(.*?)</alert\s*>", s, re.S | re.I):
        a = {k.lower(): html.unescape(v) for k, v in re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', attrs)}
        typ = " ".join(a.get("type", "").split())
        tl = typ.lower()
        kind = "imminent" if "imminent" in tl else "elevated" if "elevated" in tl else "bulletin"
        out.append({"type": typ or None, "kind": kind, "start": _ntas_time(a.get("start")),
                    "end": _ntas_time(a.get("end")), "start_et": a.get("start") or None, "end_et": a.get("end") or None,
                    "url": a.get("href") or None, "summary": _cut(_text(_inner(inner, "summary")), 800),
                    "duration": _text(_inner(inner, "duration")) or None,
                    "locations": [_text(x) for x in re.findall(r"<location\b[^>]*>(.*?)</location>", inner, re.S)
                                  if _text(x)],
                    "sectors": [_text(x) for x in re.findall(r"<sector\b[^>]*>(.*?)</sector>", inner, re.S)
                                if _text(x)]})
    return out


def ntas(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    try:
        alerts = ntas_alerts(fetch(NTAS_URL))
    except Exception as e:
        raise RuntimeError("ntas: every source failed: DHS NTAS: %s" % _err(e))
    active = [a for a in alerts if (a["start"] is None or a["start"] <= now) and (a["end"] is None or now < a["end"])]
    active.sort(key=lambda a: (NTAS_RANK[a["kind"]], -(a["start"] or now).timestamp()))
    items = [dict(a, start=_iso(a["start"]), end=_iso(a["end"]), active=True, source="DHS NTAS") for a in active]
    newest = max((a["start"] for a in alerts if a["start"]), default=None)
    out = _base("ntas", ["ntas"], [_src("DHS NTAS", True, newest=_iso(newest), n=len(alerts))], now)
    out.update(count=len(items), active=bool(items), level=items[0]["kind"] if items else None,
               in_feed=len(alerts), items=items)
    return out


FEEDS = {"radiation": (radiation, 3600), "tsunami": (tsunami, 600), "ofac": (ofac, 3600), "ntas": (ntas, 3600)}
