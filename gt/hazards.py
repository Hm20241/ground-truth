"""Natural hazards: GDACS multi-hazard alerts and EMSC/USGS earthquakes. v1.0, 2026-11-20 (Ground Truth 0.11.0).

Feed `hazards` (every 15 min), GDACS, the UN/European Commission Global Disaster Alert and Coordination System:
* `geteventlist/SEARCH` for EQ;TC;FL;VO;DR, all alert levels, fromDate = today - 7 d, paged with `pagenumber`
  (100 events a page, newest `todate` first) until a short page, at most 6 pages (2 on 11-20: 139 events);
* WF (wildfires) in two calls of up to 2 pages: Orange;Red (usually an empty body), all kept; then Green, kept only
  while current and only the WF_GREEN_MAX largest by burnt area. GDACS lists ~130 small Green fires at a time, all
  ending "today" (so page order among them is arbitrary), and they would drown the conflict layer; FIRMS already
  shows heat. The number dropped is in the output.
An event is kept while GDACS calls it current or when it ended in the last 7 days; episodes of one event collapse to
the newest. Every event becomes one point (GDACS's centroid; any polygon or bbox geometry is reduced to its centre).

Feed `quakes` (every 5 min):
* EMSC FDSN (seismicportal.eu), the 200 newest events of M4+ (about 6 days on 11-20);
* USGS FDSN `eventtype=nuclear explosion` and `eventtype=explosion`, last 7 days;
* only when EMSC fails: USGS M4+ for the last 48 h as a stand-in.
EMSC and USGS copies of one event (origin times within 60 s, epicentres within 50 km) merge into one point. Kept:
M4+ from the last 48 h, plus any "watch" event from the last 7 days. Watch = any nuclear-explosion type, any other
explosion type located in a watched area, or a shallow (<= 10 km) M4+ event in a watched area. Watched areas:
PRK, IRN, ISR, PAK, IND, SYR, YEM, plus land (or near shore) in the middle-east theatre and the ukraine-russia theatre
west of 60 E (gt/geo.py puts all of Russia, Kamchatka included, in ukraine-russia; mid-ocean ridge quakes in the Gulf
of Aden have no country and stay out). Other explosions (almost all US/Canada quarry blasts, M1-2) are dropped.
EMSC fixes many depths at 10 km, so "shallow" is a tripwire, not a finding: it asks a human to look.

Probed 2026-11-20 05:20Z: GDACS's API answered a plain Mozilla-prefixed UA (only its RSS sits behind the WAF); page
size is fixed at 100 (`pagesize` is ignored) and a page past the end, or a query with no match, is an EMPTY body
(not JSON); every geometry was a Point; times are naive UTC ("2026-11-20T02:57:18"); `datemodified` is the freshness
mark (newest 04:45:59Z). EMSC: times carry 2 fractional digits ("03:42:40.51Z", which Python 3.9's fromisoformat
rejects), depth is positive km in properties (negative in the geometry), `evtype` uses ISF event-type codes (ke/se
earthquake, kn/sn nuclear explosion, kx/sx, kh/sh, km/sm other explosions). USGS: `time` is epoch ms, depth km in
the geometry; 0 nuclear and 12 explosion events in 7 days, all quarry blasts in WA/OR/NV/BC, M1.0-2.3.

Terms: GDACS terms of use (March 2025) give no licence clause; the site's copyright link is the European Commission
legal notice (reuse authorised with acknowledgement). Data are "as is", automatic, and no substitute for national
alerts. EMSC: CC BY 4.0, "Credit: EMSC-CSEM SeismicPortal, https://www.seismicportal.eu" (seismicportal.eu/terms).
USGS: US public domain. All three are fine for the public mirror with the credits below.
"""
import datetime as dt
import gzip
import json
import math
import os
import re
import urllib.parse
import urllib.request

from . import geo

VERSION = "1.0"
UA = "GroundTruth/0.11 (personal non-commercial OSINT dashboard)"
GDACS_UA = "Mozilla/5.0 (GroundTruth/0.11 personal OSINT dashboard)"
TIMEOUT = 30
MAX_BYTES = 300000

ATTRIBUTION = {
    "gdacs": "GDACS, Global Disaster Alert and Coordination System (United Nations OCHA/UNOSAT and European Commission "
             "JRC/ECHO), gdacs.org",
    "emsc": "Credit: EMSC-CSEM SeismicPortal, https://www.seismicportal.eu (CC BY 4.0)",
    "usgs": "U.S. Geological Survey Earthquake Hazards Program, earthquake.usgs.gov (public domain)",
}
ATTRIBUTION_URL = {"gdacs": "https://www.gdacs.org", "emsc": "https://www.seismicportal.eu",
                   "usgs": "https://earthquake.usgs.gov"}
LICENCE = {
    "hazards": "GDACS: reuse with acknowledgement (European Commission legal notice); 'as is', automatic, not a "
               "substitute for national alerts",
    "quakes": "EMSC data CC BY 4.0 (credit EMSC-CSEM SeismicPortal); USGS public domain",
}
NON_COMMERCIAL = {"hazards": False, "quakes": False}
PUBLIC_OK = {"hazards": True, "quakes": True}
NOTE = {
    "hazards": "GDACS automatic alerts (Green/Orange/Red = expected humanitarian impact), current or ended in the last "
               "7 days. One point per event at GDACS's centroid. Green wildfires: only the largest current ones.",
    "quakes": "M4+ earthquakes from the last 48 h (EMSC, USGS explosions merged) plus 'watch' events from the last "
              "7 days. Watch = nuclear-explosion type, an explosion in a watched area, or a shallow (<= 10 km) M4+ "
              "event in PRK, IRN, ISR, PAK, IND, SYR, YEM, the Middle East or Ukraine/western Russia (on or near "
              "land). Preliminary parameters; EMSC often fixes depth at 10 km.",
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")   # same folder as gt/feeds.py CACHE; this module keeps no state there

# ---------------- GDACS ----------------
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
GDACS_TYPES = "EQ;TC;FL;VO;DR"
GDACS_LEVELS = "Green;Orange;Red"
GDACS_PAGE = 100        # the API's fixed page size
GDACS_MAX_PAGES = 6
GDACS_DAYS = 7
WF_PAGES = 2           # per wildfire call (Orange;Red, then Green)
WF_GREEN_MAX = 25
TYPE_LABEL = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano", "DR": "Drought",
              "WF": "Wildfire", "TS": "Tsunami"}
LEVEL_RANK = {"Red": 0, "Orange": 1, "Green": 2}

# ---------------- earthquakes ----------------
EMSC_URL = "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&orderby=time&limit=200&minmag=4"
EMSC_DETAIL = "https://www.seismicportal.eu/eventdetails.html?unid="
USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
QUAKE_HOURS = 48
WATCH_DAYS = 7
MIN_MAG = 4.0
SHALLOW_KM = 10.0
WATCH_THEATRES = ("ukraine-russia", "middle-east")
WATCH_COUNTRIES = ("PRK", "IRN", "ISR", "PAK", "IND", "SYR", "YEM")
RU_WEST_OF = 60.0       # the ukraine-russia theatre counts for the watch only west of this longitude
DEDUPE_S = 60
DEDUPE_KM = 50.0
# ISF event-type codes as EMSC serves them in `evtype` (k = known, s = suspected, f/d = felt/damaging)
ISF = {"uk": "unknown", "de": "earthquake", "fe": "earthquake", "ke": "earthquake", "se": "earthquake",
       "kr": "rockburst", "sr": "rockburst", "ki": "induced event", "si": "induced event",
       "km": "mine explosion", "sm": "mine explosion", "kh": "chemical explosion", "sh": "chemical explosion",
       "kx": "experimental explosion", "sx": "experimental explosion", "kn": "nuclear explosion",
       "sn": "nuclear explosion", "ls": "landslide"}


# ---------------- helpers ----------------

def _gunzip(b):
    """Bodies are sometimes gzip without a Content-Encoding header (and injected fetchers return raw bytes)."""
    b = b or b""
    return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b


def _fetch(url, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return _gunzip(r.read())


def _fetch_gdacs(url):
    return _fetch(url, ua=GDACS_UA)


def _utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def parse_ts(s):
    """ISO-8601 (or epoch ms) -> aware UTC datetime, None if unparseable. No zone = UTC. Accepts 1-9 fractional
    digits and 'Z' (Python 3.9's fromisoformat takes neither)."""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return dt.datetime.fromtimestamp(s / 1000.0, dt.timezone.utc)
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


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def km(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _locate(lon, lat):
    try:
        g = geo.locate(lon, lat) or {}
    except Exception:
        g = {}
    return {"country": g.get("country"), "country_name": g.get("country_name"), "sea": g.get("sea"),
            "theatre": g.get("theatre") or "other"}


def _err(e):
    return "%s: %s" % (type(e).__name__, str(e)[:200])


def _src(name, ok, error=None, newest=None, n=0):
    return {"name": name, "ok": ok, "error": error, "newest": newest, "n": n}


def _size(d):
    return len(json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode())


def _fit(out, max_bytes=None):
    """Drop features from the end (the lowest priority) until the payload is under max_bytes."""
    max_bytes = max_bytes or MAX_BYTES
    feats = out["geojson"]["features"]
    dropped = 0
    while feats and _size(out) > max_bytes:
        step = max(1, len(feats) // 20)
        del feats[-step:]
        dropped += step
    out["count"] = len(feats)
    if dropped:
        out["trimmed"] = dropped
    return out


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


def _pt(lon, lat, props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 3), round(lat, 3)]},
            "properties": props}


# ---------------- GDACS ----------------

def gdacs_url(types, levels, since, until, page):
    q = [("eventlist", types), ("alertlevel", levels), ("fromDate", since.isoformat()),
         ("toDate", until.isoformat()), ("pagenumber", page)]
    return GDACS_URL + "?" + urllib.parse.urlencode(q, safe=";")


def _gdacs_page(body):
    body = _gunzip(body)
    if not body.strip():
        return []   # GDACS answers an empty body when nothing (more) matches
    d = json.loads(body)
    if not isinstance(d, dict) or not isinstance(d.get("features"), list):
        raise ValueError("GDACS: response without features")
    return d["features"]


def _gdacs_pages(fetch, types, levels, since, until, max_pages):
    feats, truncated = [], False
    for page in range(1, max_pages + 1):
        fs = _gdacs_page(fetch(gdacs_url(types, levels, since, until, page)))
        feats.extend(fs)
        if len(fs) < GDACS_PAGE:
            break
    else:
        truncated = True
    return feats, truncated


def _clean(s, cap=200):
    """GDACS names carry double spaces, empty list slots (', ,') and a trailing ', ' (drought country lists)."""
    s = re.sub(r"\s*,(?:\s*,)+", ",", " ".join(str(s or "").split())).strip(" ,;")
    return (s[:cap - 1].rstrip(" ,;") + "\u2026" if len(s) > cap else s) or None


def _centre(f):
    """(lon, lat) of a GDACS feature: the Point, else the centre of its bbox or of its coordinates."""
    g = f.get("geometry") or {}
    c = g.get("coordinates")
    if g.get("type") == "Point" and isinstance(c, list) and len(c) >= 2:
        return _num(c[0]), _num(c[1])
    bb = f.get("bbox")
    if isinstance(bb, list) and len(bb) >= 4 and all(_num(x) is not None for x in bb[:4]):
        return (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    xs, ys = [], []

    def walk(v):
        if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
            xs.append(v[0])
            ys.append(v[1])
        elif isinstance(v, list):
            for w in v:
                walk(w)
    walk(c)
    if xs:
        return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    return None, None


def _gdacs_event(f):
    p = f.get("properties") or {}
    et, eid = p.get("eventtype"), p.get("eventid")
    lon, lat = _centre(f)
    if not et or eid is None or lon is None or lat is None:
        return None
    sev = p.get("severitydata") if isinstance(p.get("severitydata"), dict) else {}
    urls = p.get("url") if isinstance(p.get("url"), dict) else {}
    level = p.get("alertlevel") if p.get("alertlevel") in LEVEL_RANK else "Green"
    t_from, t_to, t_mod = parse_ts(p.get("fromdate")), parse_ts(p.get("todate")), parse_ts(p.get("datemodified"))
    props = {
        "id": "%s%s" % (et, eid), "type": et, "type_label": TYPE_LABEL.get(et, et),
        "name": _clean(p.get("name") or p.get("description")), "event_name": p.get("eventname") or None,
        "alert": level, "alert_score": _num(p.get("alertscore")), "episode_alert": p.get("episodealertlevel"),
        "severity": " ".join(str(sev.get("severitytext") or "").split()) or None,
        "severity_value": _num(sev.get("severity")), "severity_unit": sev.get("severityunit") or None,
        "gdacs_country": _clean(p.get("country")), "iso3": p.get("iso3") or None,
        "affected": [a.get("iso3") for a in (p.get("affectedcountries") or []) if isinstance(a, dict) and a.get("iso3")],
        "from": _iso(t_from), "to": _iso(t_to), "modified": _iso(t_mod),
        "current": str(p.get("iscurrent")).lower() == "true", "episode": p.get("episodeid"),
        "origin": p.get("source") or None, "url": urls.get("report"), "source": "GDACS",
    }
    return {"lon": lon, "lat": lat, "props": props, "t_to": t_to, "t_mod": t_mod,
            "ep": (_num(p.get("episodeid")) or 0, t_mod or dt.datetime.min.replace(tzinfo=dt.timezone.utc))}


def _collapse(events):
    """One entry per event: the newest episode."""
    best = {}
    for e in events:
        k = e["props"]["id"]
        if k not in best or e["ep"] > best[k]["ep"]:
            best[k] = e
    return list(best.values())


def _recent(e, since):
    return e["props"]["current"] or (e["t_to"] is not None and e["t_to"] >= since)


def gdacs(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch_gdacs
    since = now - dt.timedelta(days=GDACS_DAYS)
    d0, d1 = since.date(), now.date() + dt.timedelta(days=1)
    sources, events, truncated, wf_dropped = [], [], False, 0

    try:
        feats, truncated = _gdacs_pages(fetch, GDACS_TYPES, GDACS_LEVELS, d0, d1, GDACS_MAX_PAGES)
        evs = [e for e in (_gdacs_event(f) for f in feats) if e]
        mods = [e["t_mod"] for e in evs if e["t_mod"]]
        evs = [e for e in _collapse(evs) if _recent(e, since)]
        events += evs
        sources.append(_src("GDACS", True, newest=_iso(max(mods)) if mods else None, n=len(evs)))
    except Exception as e:
        sources.append(_src("GDACS", False, _err(e)))

    try:
        feats = _gdacs_pages(fetch, "WF", "Orange;Red", d0, d1, WF_PAGES)[0]
        feats += _gdacs_pages(fetch, "WF", "Green", d0, d1, WF_PAGES)[0]
        evs = [e for e in (_gdacs_event(f) for f in feats) if e]
        mods = [e["t_mod"] for e in evs if e["t_mod"]]
        evs = [e for e in _collapse(evs) if _recent(e, since)]
        big = [e for e in evs if e["props"]["alert"] != "Green"]
        green = sorted((e for e in evs if e["props"]["alert"] == "Green" and e["props"]["current"]),
                       key=lambda e: -(e["props"]["severity_value"] or 0))
        keep = big + green[:WF_GREEN_MAX]
        wf_dropped = len(evs) - len(keep)
        events += keep
        sources.append(_src("GDACS wildfires", True, newest=_iso(max(mods)) if mods else None, n=len(keep)))
    except Exception as e:
        sources.append(_src("GDACS wildfires", False, _err(e)))

    if not any(s["ok"] for s in sources):
        raise RuntimeError("GDACS: every source failed: " + "; ".join(s["error"] for s in sources))

    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    events = _collapse(events)
    events.sort(key=lambda e: (LEVEL_RANK[e["props"]["alert"]], -((e["t_to"] or epoch) - epoch).total_seconds(),
                               e["props"]["id"]))
    feats = []
    for e in events:
        props = dict(e["props"])
        props.update(_locate(e["lon"], e["lat"]))
        feats.append(_pt(e["lon"], e["lat"], props))
    by_type, by_alert = {}, {}
    for f in feats:
        p = f["properties"]
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1
        by_alert[p["alert"]] = by_alert.get(p["alert"], 0) + 1
    out = {"version": VERSION, "fetched_at": _iso(now), "count": len(feats), "window_days": GDACS_DAYS,
           "by_type": by_type, "by_alert": by_alert, "wildfires_green_dropped": wf_dropped,
           "truncated": truncated, "sources": sources, "attribution": [ATTRIBUTION["gdacs"]],
           "attribution_url": ATTRIBUTION_URL["gdacs"], "licence": LICENCE["hazards"],
           "public_ok": PUBLIC_OK["hazards"], "non_commercial": NON_COMMERCIAL["hazards"], "note": NOTE["hazards"],
           "geojson": _fc(feats)}
    return _fit(out)


# ---------------- earthquakes ----------------

def usgs_url(since, eventtype=None, minmag=None):
    q = [("format", "geojson"), ("orderby", "time"), ("starttime", since.strftime("%Y-%m-%dT%H:%M:%S"))]
    if eventtype:
        q.append(("eventtype", eventtype))
    if minmag is not None:
        q.append(("minmagnitude", minmag))
    return USGS_URL + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def _features(body, who):
    d = json.loads(_gunzip(body))
    feats = d.get("features") if isinstance(d, dict) else None
    if not isinstance(feats, list):
        raise ValueError("%s: response without features" % who)
    return feats


def _title(s):
    s = " ".join(str(s or "").split())
    return s.title() if s.isupper() else s


def emsc_events(body):
    out = []
    for f in _features(body, "EMSC"):
        p = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates") or []
        lon = _num(p.get("lon")) if p.get("lon") is not None else (_num(c[0]) if len(c) > 1 else None)
        lat = _num(p.get("lat")) if p.get("lat") is not None else (_num(c[1]) if len(c) > 1 else None)
        depth = _num(p.get("depth"))
        if depth is None and len(c) > 2 and _num(c[2]) is not None:
            depth = abs(_num(c[2]))
        t, mag = parse_ts(p.get("time")), _num(p.get("mag"))
        if lon is None or lat is None or t is None or mag is None:
            continue
        code = str(p.get("evtype") or "").strip().lower()
        unid = str(p.get("unid") or f.get("id") or "")
        out.append({"id": "emsc:" + unid, "src": "EMSC", "t": t, "lon": lon, "lat": lat, "depth": depth, "mag": mag,
                    "magtype": p.get("magtype"), "place": _title(p.get("flynn_region")),
                    "kind": ISF.get(code, "earthquake" if not code else "other (%s)" % code),
                    "suspected": code[:1] == "s", "agency": p.get("auth"),
                    "url": EMSC_DETAIL + urllib.parse.quote(unid) if unid else None})
    return out


def usgs_events(body):
    out = []
    for f in _features(body, "USGS"):
        p = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates") or []
        if len(c) < 2 or _num(c[0]) is None or _num(c[1]) is None or not f.get("id"):
            continue
        t = parse_ts(p.get("time"))
        if t is None:
            continue
        out.append({"id": "usgs:" + str(f["id"]), "src": "USGS", "t": t, "lon": _num(c[0]), "lat": _num(c[1]),
                    "depth": _num(c[2]) if len(c) > 2 else None, "mag": _num(p.get("mag")),
                    "magtype": p.get("magType"), "place": p.get("place"),
                    "kind": str(p.get("type") or "earthquake").lower(), "suspected": False,
                    "agency": (str(p.get("net") or "").upper() or None), "url": p.get("url")})
    return out


def merge(emsc, usgs):
    """EMSC events plus USGS events, an event reported by both merged into the EMSC one (origin times within
    DEDUPE_S, epicentres within DEDUPE_KM; the closest in time wins). A USGS explosion type overrides 'earthquake'."""
    out = [dict(e) for e in emsc]
    seen = set()
    for u in usgs:
        if u["id"] in seen:
            continue
        seen.add(u["id"])
        best = None
        for e in out:
            if e["src"] != "EMSC":
                continue
            ds = abs((e["t"] - u["t"]).total_seconds())
            if ds <= DEDUPE_S:
                d = km(e["lon"], e["lat"], u["lon"], u["lat"])
                if d <= DEDUPE_KM and (best is None or (ds, d) < best[0]):
                    best = ((ds, d), e)
        if best:
            e = best[1]
            e.update(src="EMSC+USGS", usgs_id=u["id"], usgs_url=u["url"])
            if u["kind"] != "earthquake" and e["kind"] in ("earthquake", "unknown"):
                e["kind"] = u["kind"]
            if e["mag"] is None:
                e["mag"] = u["mag"]
        else:
            out.append(dict(u))
    return out


def _is_explosion(kind):
    return "explosion" in kind or "blast" in kind


def watched_area(e, loc):
    """In a watch-list country, or on/near land in a watched theatre. Russia counts only west of 60 E (European
    Russia, Novaya Zemlya), so Kamchatka and the Kurils stay out; points with no country within geo.locate's reach
    (the Gulf of Aden and Arabian Sea ridges, which quake every week) stay out."""
    a3, th = loc.get("country"), loc.get("theatre")
    if a3 in WATCH_COUNTRIES:
        return True
    if not a3 or th not in WATCH_THEATRES:
        return False
    return th != "ukraine-russia" or e["lon"] <= RU_WEST_OF


def watch_reason(e, loc):
    """Why an event is on watch, or None."""
    kind = e["kind"]
    where = loc.get("country_name") or loc.get("sea") or geo.THEATRES.get(loc.get("theatre"), loc.get("theatre"))
    if "nuclear" in kind:
        return "%snuclear explosion (%s)" % ("suspected " if e.get("suspected") else "", e["src"])
    if not watched_area(e, loc):
        return None
    if _is_explosion(kind):
        return "%s in a watched area: %s" % (kind, where)
    if e["mag"] is not None and e["mag"] >= MIN_MAG and e["depth"] is not None and e["depth"] <= SHALLOW_KM:
        return "shallow M%.1f (%g km) in a watched area: %s" % (e["mag"], round(e["depth"], 1), where)
    return None


def quakes(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    cut, wcut = now - dt.timedelta(hours=QUAKE_HOURS), now - dt.timedelta(days=WATCH_DAYS)
    sources, emsc, usgs = [], [], []
    try:
        emsc = emsc_events(fetch(EMSC_URL))
        sources.append(_src("EMSC", True, newest=_iso(max((e["t"] for e in emsc), default=None)), n=len(emsc)))
    except Exception as e:
        sources.append(_src("EMSC", False, _err(e)))
    for name, kind in (("USGS nuclear explosion", "nuclear explosion"), ("USGS explosion", "explosion")):
        try:
            evs = usgs_events(fetch(usgs_url(wcut, eventtype=kind)))
            usgs += evs
            sources.append(_src(name, True, newest=_iso(max((e["t"] for e in evs), default=None)), n=len(evs)))
        except Exception as e:
            sources.append(_src(name, False, _err(e)))
    if not sources[0]["ok"]:   # EMSC down: USGS M4+ for the window as a stand-in
        try:
            evs = usgs_events(fetch(usgs_url(cut, minmag=MIN_MAG)))
            usgs += evs
            sources.append(_src("USGS M4+ (EMSC fallback)", True,
                                newest=_iso(max((e["t"] for e in evs), default=None)), n=len(evs)))
        except Exception as e:
            sources.append(_src("USGS M4+ (EMSC fallback)", False, _err(e)))
    if not any(s["ok"] for s in sources):
        raise RuntimeError("quakes: every source failed: " + "; ".join(s["error"] for s in sources))

    feats = []
    for e in merge(emsc, usgs):
        if e["t"] < wcut or e["t"] > now + dt.timedelta(hours=1):
            continue
        explosion = _is_explosion(e["kind"])
        recent_m4 = e["t"] >= cut and e["mag"] is not None and e["mag"] >= MIN_MAG and not explosion
        maybe_watch = ("nuclear" in e["kind"] or explosion or
                       (e["mag"] is not None and e["mag"] >= MIN_MAG and e["depth"] is not None
                        and e["depth"] <= SHALLOW_KM))
        if not (recent_m4 or maybe_watch):
            continue
        loc = _locate(e["lon"], e["lat"])
        why = watch_reason(e, loc)
        if not (recent_m4 or why):
            continue   # quarry blasts and old non-watch events
        props = {"id": e["id"], "source": e["src"], "time": _iso(e["t"]),
                 "mag": round(e["mag"], 1) if e["mag"] is not None else None, "magtype": e["magtype"],
                 "depth_km": round(e["depth"], 1) if e["depth"] is not None else None, "place": e["place"],
                 "kind": e["kind"], "suspected": bool(e.get("suspected")), "agency": e["agency"],
                 "watch": bool(why), "watch_reason": why, "url": e["url"]}
        if e.get("usgs_url"):
            props["usgs_url"] = e["usgs_url"]
        props.update(loc)
        feats.append((e["t"], _pt(e["lon"], e["lat"], props)))
    feats.sort(key=lambda x: (not x[1]["properties"]["watch"], -x[0].timestamp(), x[1]["properties"]["id"]))
    feats = [f for _, f in feats]
    used = [k for k, s in (("emsc", "EMSC"), ("usgs", "USGS")) if any(x["name"].startswith(s) and x["ok"]
                                                                     for x in sources)]
    out = {"version": VERSION, "fetched_at": _iso(now), "count": len(feats),
           "watch_count": sum(1 for f in feats if f["properties"]["watch"]), "window_hours": QUAKE_HOURS,
           "watch_days": WATCH_DAYS, "sources": sources, "attribution": [ATTRIBUTION[k] for k in used],
           "attribution_url": [ATTRIBUTION_URL[k] for k in used], "licence": LICENCE["quakes"],
           "public_ok": PUBLIC_OK["quakes"], "non_commercial": NON_COMMERCIAL["quakes"], "note": NOTE["quakes"],
           "geojson": _fc(feats)}
    return _fit(out)


FEEDS = {"hazards": (gdacs, 900), "quakes": (quakes, 300)}
