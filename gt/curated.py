"""Curated conflict-event layers from public ArcGIS FeatureServers (keyless). v1.0, 2026-11-20 (Ground Truth 0.11.0).

Two feeds, plus the helpers that gt/geoconfirmed.py shares (event schema, ids, timing, caps, state files):

* `cir` (every 3 h): Centre for Information Resilience, Eyes on Russia. Verified civilian harm and infrastructure
  damage in Ukraine and Russia, each entry checked against open-source footage. Layer `EoR_completed_entries`
  on services-eu1.arcgis.com. CIR publishes about a week late on purpose, so a 21-day window holds about two
  weeks of entries (~12-20 a day).
* `kinetic` (every 3 h): S2 Underground's Iran Kinetic Events (strikes, sunk merchant ships, downed aircraft
  around Iran and the Gulf), each with X research links. Layer `Iran_Kinetic_Events` (layer 3) on
  services.arcgis.com. Low volume (about 0.2-0.7 a day), so a 60-day window.

One poll is one ArcGIS query per feed: `<date field> >= timestamp '<today - window> 00:00:00'`, newest first,
paged with resultOffset while the server says exceededTransferLimit (1000 a page, at most 10 pages). The whole
window is asked for every time, so a full answer is authoritative: entries that left the layer leave the feed.
When a later page fails, the rows already read are merged with the last poll's rows (cached in
<GT_DATA>/cache/curated_<feed>.json) and the source is marked ok=false with the page error; when the first page
fails the poll raises and the scheduler keeps the last good data.

Probed 2026-11-20 (keyless, HTTP 200, gzip honoured):
* CIR: maxRecordCount 1000; TIMESTAMP is esriFieldTypeDate holding the day at 00:00Z (no time of day); latitude
  and longitude fields equal the point geometry; Link is one URL, mostly t.me/<channel>/<n> (a few x.com,
  facebook, instagram, and private t.me/c/<chat>/<n>); 263 rows for 2026-10-30..11-13, the newest dated 11-13;
  Entry_Number ("XX12345") is unique; several entries share one Link (one post, several damaged sites: 263
  entries, 216 links);
  Graphic_content_level is "1 - None" .. "5 - Graphic"; Primary_category is one of Civilian Infrastructure Damage,
  Civilian Casualty, Munitions, Bombing or explosion.
* S2: maxRecordCount 2000; Date is esriFieldTypeDate at 00:00Z; Description is mostly empty, IncidentName is the
  headline; Research1 is an X post for 38 of 40 rows (Research2 rarely, Research3 never); the X post is 25 h
  before to 78 h after the Date; IncidentType values MerchantVesselSunk, IranianBallisticMissileStrike,
  AmericanAircraftDowned; 40 rows for 2026-09-21..11-19.

Times (shared with GeoConfirmed): a time zoned in the source's own text wins (GeoConfirmed DTGs), else the
earliest X post id (snowflake = when the post went up) within 2 days before / 5 days after the stated day
(ts_source "x-snowflake"), else the stated day at 12:00Z, never later than now (ts_source "date").

Ids follow gt/mymaps.parse(): sha1 of parse_source(url)["url"], first 16 hex, so a pin built from the same post
as a source-map pin gets the same id. When several entries cite one post, the one seen first keeps that id and
the others get sha1("<feed>:<source id>"); entries without a URL always get the latter.

Terms:
* CIR: "we provide open access to the results of our analysis" (info-res.org/faqs). No licence is stated, so it
  is treated as non-commercial and kept off the public mirror until CIR agrees. Never for the trading agent.
* S2 Underground: "S2 Underground (c) 2025 by S2A1 is licensed under CC BY-NC-SA 4.0". Public use is fine with
  the credit, the licence link and a note of changes; non-commercial; anything derived and republished must be
  CC BY-NC-SA too. Never for the trading agent.
"""
import datetime as dt
import gzip
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from . import geo, mymaps

VERSION = "1.0"
UA = "GroundTruth/0.11 (personal non-commercial OSINT dashboard)"
TIMEOUT = 30
PAGE = 1000           # rows asked per ArcGIS call (CIR's maxRecordCount)
MAX_PAGES = 10
MAX_FEATURES = 2000
MAX_BYTES = 290000    # compact JSON of the features; the envelope adds ~2 KB, so a payload stays under ~300 KB
TITLE_MAX = 140
DESC_MAX = 300
LINKS_MAX = 3
DAY_MS = 86400000
SNOW_BEFORE_MS = 2 * DAY_MS   # an X post may go up a little before the stated (local) day ...
SNOW_AFTER_MS = 5 * DAY_MS    # ... or days after it; outside this the post is a repost, use the day
FUTURE_SLACK_MS = 600000

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")   # = feeds.CACHE

_ARC_EU = "https://services-eu1.arcgis.com/06WOSMGHsCnaFyMp/arcgis/rest/services/"
_ARC_S2 = "https://services.arcgis.com/OeCRCKr7XFYQNdyJ/arcgis/rest/services/"
CIR_URL = _ARC_EU + "EoR_completed_entries/FeatureServer/0/query"
KINETIC_URL = _ARC_S2 + "Iran_Kinetic_Events/FeatureServer/3/query"
CIR_FIELDS = ("OBJECTID,TIMESTAMP,Link,Description,Primary_category,Secondary_category,Sector_affected,Town_or_City,"
              "province,country,latitude,longitude,Graphic_content_level,Entry_Number,Credit")
KINETIC_FIELDS = ("OBJECTID,IncidentType,IncidentName,Date,Description,Notes,Research1,Research2,Research3,ReportCredit,"
                  "CivilianKilled,CivilianWounded,EnemyKilled,EnemyWounded,FriendlyKilled,FriendlyWounded,NeutralKilled,"
                  "NeutralWounded")

ATTRIBUTION = {
    "cir": "Centre for Information Resilience, Eyes on Russia: verified incidents",
    "kinetic": "S2 Underground, Iran Kinetic Events. S2 Underground (c) 2025 by S2A1, licensed under CC BY-NC-SA 4.0",
}
ATTRIBUTION_URL = {"cir": "https://eyesonrussia.org", "kinetic": "https://creativecommons.org/licenses/by-nc-sa/4.0/"}
LICENCE = {
    "cir": "No licence stated; CIR offers 'open access to the results of our analysis' (info-res.org/faqs). "
           "Non-commercial, private dashboard only (not the public mirror) until CIR agrees; never for the trading agent",
    "kinetic": "CC BY-NC-SA 4.0 (S2 Underground (c) 2025 by S2A1): credit + licence link, non-commercial, "
               "share-alike; never for the trading agent",
}
CHANGES = {"kinetic": "Changes: category, country and theatre added by Ground Truth; text shortened."}
NON_COMMERCIAL = {"cir": True, "kinetic": True}
PUBLIC_OK = {"cir": False, "kinetic": True}
LABEL = {"cir": "CIR Eyes on Russia", "kinetic": "S2 Underground"}
WINDOW_DAYS = {"cir": 21, "kinetic": 60}
NOTE = {
    "cir": "Civilian harm and infrastructure damage verified by CIR, published about a week after the day. "
           "Day-only dates (shown at 12:00Z) unless the link is an X post. graphic = CIR's 1-5 content level.",
    "kinetic": "Strikes, sunk ships and downed aircraft logged by S2 Underground with X research links. "
               "Time = the first X post when it is within days of the logged day, else the day at 12:00Z.",
}

# Source categories -> mymaps category, used only when the title's keywords give none.
CIR_CATEGORY = {"civilian casualty": "casualty", "civilian infrastructure damage": "strike",
                "bombing or explosion": "strike", "munitions": "strike"}
KINETIC_CATEGORY = (("vessel", "maritime"), ("ship", "maritime"), ("missile", "missile"), ("drone", "drone"),
                    ("aircraft", "aviation"), ("strike", "strike"))
CASUALTY_FIELDS = ("CivilianKilled", "CivilianWounded", "EnemyKilled", "EnemyWounded", "FriendlyKilled",
                   "FriendlyWounded", "NeutralKilled", "NeutralWounded")


# ---------------- shared helpers (also used by gt/geoconfirmed.py) ----------------

def utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


def iso(ms):
    return None if ms is None else dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_ms(day):
    return int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def fetch_url(url, ua=UA, timeout=TIMEOUT, accept=None):
    """GET with an honest User-Agent and gzip; returns the body bytes."""
    h = {"User-Agent": ua, "Accept-Encoding": "gzip"}
    if accept:
        h["Accept"] = accept
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=min(timeout, TIMEOUT)) as r:
        body = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)
    return body


def err_text(e):
    """A short error string without local paths or anything private."""
    if isinstance(e, urllib.error.HTTPError):
        return "HTTP %s" % e.code
    if isinstance(e, urllib.error.URLError):
        return "URLError: %s" % (type(e.reason).__name__ if not isinstance(e.reason, str) else e.reason[:80])
    if isinstance(e, OSError):   # timeouts, resets, file errors: never echo a path
        return "%s%s" % (type(e).__name__, " errno %s" % e.errno if e.errno else "")
    return "%s: %s" % (type(e).__name__, re.sub(r"(/[^\s/]+){2,}", "<path>", str(e))[:160])


def clean_text(s, n):
    """Tags stripped, entities decoded, whitespace collapsed, cut to n characters at a word."""
    if not s:
        return ""
    s = re.sub(r"(?i)<\s*/?\s*(br|hr|p|div|li|tr)\b[^>]*>", " ", str(s))
    s = re.sub(r"<[^>]*>", "", s)
    s = html.unescape(s)
    s = re.sub(r"<[^>]*>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > n:
        cut = s[:n - 1]
        sp = cut.rfind(" ")
        s = (cut[:sp] if sp > n - 40 else cut).rstrip(" ,;:-") + "…"
    return s


def first_line(s):
    """The text before the first <br>/<hr>/newline, as a headline."""
    for part in re.split(r"(?i)<\s*(?:br|hr)\b[^>]*>|\n", s or ""):
        t = clean_text(part, TITLE_MAX)
        if t:
            return t
    return ""


_URL = re.compile(r"https?://[^\s<>\"']+")
_BARE = re.compile(r"^(?:www\.)?(?:t\.me|x\.com|twitter\.com|facebook\.com|instagram\.com)/\S+")


def find_urls(text):
    """URLs in order, with the punctuation that CSV and prose glue to them removed; bare t.me/x.com links get https."""
    text = text or ""
    out = [u.rstrip(",.;:)]}»") for u in _URL.findall(text)]
    if not out and _BARE.match(text.strip()):
        out = ["https://" + text.strip().split()[0].rstrip(",.;:)]}")]
    return [u for u in out if len(u) > 10]


def source_info(url):
    """mymaps.parse_source() of one URL (same url normalisation, so the same id), with private and preview
    Telegram links fixed: t.me/c/<chat>/<n> has no public handle."""
    s = mymaps.parse_source(url) if url else {}
    out = {"url": s.get("url"), "platform": s.get("platform"), "handle": s.get("handle"), "post_id": s.get("post_id"),
           "link_private": False}
    u = out["url"] or ""
    if re.match(r"https?://t\.me/c/\d+", u):
        out.update(platform="telegram", handle=None, post_id=None, link_private=True)
    else:
        m = re.match(r"https?://t\.me/s/([^/]+)/(\d+)", u)
        if m:
            out.update(platform="telegram", handle=m.group(1), post_id=m.group(2))
    return out


def x_post_ids(urls):
    out = []
    for u in urls:
        m = re.match(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[^/]+/status(?:es)?/(\d{15,20})", u)
        if m:
            out.append(m.group(1))
    return out


def pick_time(day, now, post_ids=(), zoned_ms=None):
    """(ts_ms, ts_source) for an entry dated `day` (a date): a zoned time from the source near the day, else the
    earliest X post near the day, else the day at 12:00Z (never after now)."""
    d0, now_ms = day_ms(day), int(utc(now).timestamp() * 1000)
    if zoned_ms is not None and d0 - DAY_MS <= zoned_ms <= d0 + 2 * DAY_MS and zoned_ms <= now_ms + FUTURE_SLACK_MS:
        return int(zoned_ms), "name-dtg"
    for s in sorted(mymaps.snowflake_ms(p) for p in post_ids):
        if d0 - SNOW_BEFORE_MS <= s <= d0 + SNOW_AFTER_MS and s <= now_ms + FUTURE_SLACK_MS:
            return s, "x-snowflake"
    return min(d0 + DAY_MS // 2, now_ms), "date"


def valid_lonlat(lon, lat):
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    if lon != lon or lat != lat or not (-180 <= lon <= 180 and -90 <= lat <= 90) or (lon == 0 and lat == 0):
        return None
    return lon, lat


def make_feature(lon, lat, title, ts, src, source, label, description=None, extras=None, fallback_cat=None):
    """A Point Feature in the curated-event schema. `id` is set later by assign_ids()."""
    cat, tags = mymaps.classify(title, None)
    if cat == "other" and fallback_cat:
        cat = fallback_cat
        if fallback_cat not in tags:
            tags = tags + [fallback_cat]
    loc = geo.locate(lon, lat)
    props = {"id": None, "title": title, "kind": "event", "category": cat, "tags": tags,
             "ts_ms": ts[0], "ts": iso(ts[0]), "ts_source": ts[1],
             "url": src.get("url"), "platform": src.get("platform"), "handle": src.get("handle"),
             "post_id": src.get("post_id"),
             "country": loc.get("country"), "country_name": loc.get("country_name"), "sea": loc.get("sea"),
             "theatre": loc.get("theatre"), "source": source, "source_label": label,
             "description": description if description and description != title else None}
    props.update(extras or {})
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": props}


def _sha16(s):
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def assign_ids(entries, source):
    """entries: [{"sid", "first_seen", "feature"}]. The entry seen first for a URL gets mymaps' id for that URL;
    other entries citing the same URL, and entries without one, get sha1("<source>:<sid>")."""
    taken = set()
    for e in sorted(entries, key=lambda e: (e["first_seen"], str(e["sid"]))):
        p = e["feature"]["properties"]
        url = p.get("url")
        if url and url not in taken:
            taken.add(url)
            p["id"] = _sha16(url)
        else:
            p["id"] = _sha16("%s:%s" % (source, e["sid"]))
    return entries


def cap_features(feats, max_n=None, max_bytes=None):
    """Newest first; keeps at most max_n features and max_bytes of compact JSON. Returns (kept, dropped)."""
    max_n = MAX_FEATURES if max_n is None else max_n
    max_bytes = MAX_BYTES if max_bytes is None else max_bytes
    kept, total = [], 0
    for f in feats[:max_n]:
        b = len(json.dumps(f, separators=(",", ":"), ensure_ascii=False).encode()) + 1
        if total + b > max_bytes:
            break
        kept.append(f)
        total += b
    return kept, len(feats) - len(kept)


def sort_newest(feats):
    feats.sort(key=lambda f: (-(f["properties"].get("ts_ms") or 0), f["properties"]["id"] or ""))
    return feats


def state_path(name):
    return os.path.join(CACHE, name)


def load_state(name):
    try:
        with open(state_path(name), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(name, d):
    """Atomic: write <name>.tmp, then os.replace."""
    os.makedirs(CACHE, exist_ok=True)
    p = state_path(name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, p)


def envelope(feed, now, feats, sources, attribution, licence, public_ok, non_commercial, note, window_days, dropped):
    return {"version": VERSION, "feed": feed, "fetched_at": utc(now).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": len(feats), "window_days": window_days, "sources": sources, "attribution": attribution,
            "licence": licence, "public_ok": public_ok, "non_commercial": non_commercial, "note": note,
            "capped": {"dropped": dropped, "max_features": MAX_FEATURES, "max_bytes": MAX_BYTES,
                       "rule": "newest first; oldest dropped past max_features or max_bytes of compact JSON"},
            "geojson": {"type": "FeatureCollection", "features": feats}}


def newest_iso(feats):
    ms = [f["properties"]["ts_ms"] for f in feats if f["properties"].get("ts_ms")]
    return iso(max(ms)) if ms else None


# ---------------- ArcGIS ----------------

def _arcgis_page(fetch, url, label):
    d = json.loads(fetch(url))
    if not isinstance(d, dict):
        raise ValueError("%s: unexpected response %s" % (label, type(d).__name__))
    if d.get("error"):
        e = d["error"]
        raise RuntimeError("%s query error %s: %s" % (label, e.get("code"), str(e.get("message"))[:120]))
    if not isinstance(d.get("features"), list):
        raise ValueError("%s: response without features" % label)
    return d


def arcgis_query(fetch, url, params, label="ArcGIS", page=PAGE, max_pages=MAX_PAGES):
    """(rows, error, pages): rows are (attributes, geometry) pairs of a query paged with resultOffset.
    The first page failing raises; a later failure stops paging and comes back as `error` with the rows so far."""
    rows, offset = [], 0
    for i in range(max_pages):
        p = dict(params, resultOffset=offset, resultRecordCount=page, f="json")
        try:
            d = _arcgis_page(fetch, url + "?" + urllib.parse.urlencode(p, quote_via=urllib.parse.quote), label)
        except Exception as e:
            if i == 0:
                raise
            return rows, "page %d: %s" % (i + 1, err_text(e)), i
        feats = d["features"]
        rows.extend(((f or {}).get("attributes") or {}, (f or {}).get("geometry")) for f in feats)
        if not (d.get("exceededTransferLimit") and feats):
            return rows, None, i + 1
        offset += len(feats)
    return rows, "still paging after %d pages" % max_pages, max_pages


def _day_from_ms(v):
    try:
        return dt.datetime.fromtimestamp(int(v) / 1000, dt.timezone.utc).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _geom_lonlat(g):
    g = g or {}
    return valid_lonlat(g.get("x"), g.get("y"))


# ---------------- CIR Eyes on Russia ----------------

def _cir_sid(a):
    e = (a.get("Entry_Number") or "").strip()
    return e or ("oid%s" % a.get("OBJECTID"))


def _graphic(level):
    m = re.match(r"\s*(\d)", level or "")
    return int(m.group(1)) if m else None


def _cir_build(a, g, now):
    day = _day_from_ms(a.get("TIMESTAMP"))
    if day is None:
        return None, "no_date"
    ll = valid_lonlat(a.get("longitude"), a.get("latitude")) or _geom_lonlat(g)
    if not ll:
        return None, "bad_coords"
    urls = find_urls(a.get("Link") or "")
    src = source_info(urls[0] if urls else None)
    desc = clean_text(a.get("Description"), DESC_MAX)
    cat0 = (a.get("Primary_category") or "").strip()
    place = clean_text(a.get("Town_or_City"), 60) or None
    title = clean_text(a.get("Description"), TITLE_MAX) or ", ".join(x for x in (cat0, place) if x) or "CIR entry"
    level = clean_text(a.get("Graphic_content_level"), 40) or None
    extras = {"graphic_level": level, "graphic": _graphic(level), "cir_category": cat0 or None,
              "cir_secondary": clean_text(a.get("Secondary_category"), 80) or None,
              "sector": clean_text(a.get("Sector_affected"), 60) or None, "place": place,
              "province": clean_text(a.get("province"), 60) or None, "entry": _cir_sid(a),
              "credit": clean_text(a.get("Credit"), 40) or None, "link_private": src["link_private"]}
    f = make_feature(ll[0], ll[1], title, pick_time(day, now, x_post_ids(urls)), src, "cir", LABEL["cir"], desc,
                     extras, CIR_CATEGORY.get(cat0.lower()))
    return f, day


# ---------------- S2 Underground Iran Kinetic Events ----------------

def _kinetic_sid(a):
    return "oid%s" % a.get("OBJECTID")


def _camel_words(s):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s or "").strip()


def _kinetic_build(a, g, now):
    day = _day_from_ms(a.get("Date"))
    if day is None:
        return None, "no_date"
    ll = _geom_lonlat(g)
    if not ll:
        return None, "bad_coords"
    urls = []
    for k in ("Research1", "Research2", "Research3"):
        for u in find_urls(a.get(k) or ""):
            if u not in urls:
                urls.append(u)
    src = source_info(urls[0] if urls else None)
    itype = (a.get("IncidentType") or "").strip()
    label = _camel_words(itype)
    title = clean_text(a.get("IncidentName"), TITLE_MAX) or label or "Kinetic event"
    desc = clean_text(" ".join(x for x in (a.get("Description"), a.get("Notes")) if x), DESC_MAX)
    cas = {re.sub(r"(?<=[a-z])(?=[A-Z])", "_", k).lower(): int(a[k]) for k in CASUALTY_FIELDS
           if isinstance(a.get(k), (int, float)) and a.get(k)}
    low = itype.lower()
    fallback = next((c for w, c in KINETIC_CATEGORY if w in low), None)
    extras = {"incident_type": itype or None, "incident_label": label or None, "casualties": cas or None,
              "report_credit": clean_text(a.get("ReportCredit"), 60) or None,
              "links": urls[1:1 + LINKS_MAX] or None, "link_private": src["link_private"]}
    f = make_feature(ll[0], ll[1], title, pick_time(day, now, x_post_ids(urls)), src, "kinetic", LABEL["kinetic"],
                     desc, extras, fallback)
    return f, day


LAYERS = {
    "cir": {"url": CIR_URL, "fields": CIR_FIELDS, "date": "TIMESTAMP", "sid": _cir_sid, "build": _cir_build,
            "state": "curated_cir.json", "name": "CIR Eyes on Russia (ArcGIS)"},
    "kinetic": {"url": KINETIC_URL, "fields": KINETIC_FIELDS, "date": "Date", "sid": _kinetic_sid,
                "build": _kinetic_build, "state": "curated_kinetic.json", "name": "S2 Iran Kinetic Events (ArcGIS)"},
}


def poll_layer(feed, now=None, fetch=None):
    cfg, now, fetch = LAYERS[feed], utc(now), fetch or fetch_url
    window = WINDOW_DAYS[feed]
    since = now.date() - dt.timedelta(days=window)
    now_ms = int(now.timestamp() * 1000)
    rows, err, pages = arcgis_query(fetch, cfg["url"], {
        "where": "%s >= timestamp '%s 00:00:00'" % (cfg["date"], since.isoformat()), "outFields": cfg["fields"],
        "orderByFields": "%s DESC,OBJECTID DESC" % cfg["date"], "returnGeometry": "true", "outSR": "4326"},
        label=LABEL[feed])
    old = load_state(cfg["state"]).get("rows")
    old = old if isinstance(old, dict) else {}
    cur = {}
    for a, g in rows:
        sid = cfg["sid"](a)
        prev = old.get(sid) if isinstance(old.get(sid), dict) else {}
        cur[sid] = {"first_seen": prev.get("first_seen") or now_ms, "a": a, "g": g}
    if err:   # partial answer: keep last poll's rows that this one did not reach
        for sid, r in old.items():
            if sid not in cur and isinstance(r, dict) and "a" in r:
                cur[sid] = r
    dropped = {"no_date": 0, "bad_coords": 0, "outside_window": 0, "future": 0, "cap": 0}
    entries, keep = [], {}
    for sid, r in cur.items():
        f, day = cfg["build"](r["a"], r.get("g"), now)
        if f is None:
            dropped[day] += 1
            continue
        if day < since:
            dropped["outside_window"] += 1
            continue
        if day > now.date() + dt.timedelta(days=1):
            dropped["future"] += 1
            continue
        entries.append({"sid": sid, "first_seen": r["first_seen"], "feature": f})
        keep[sid] = r
    assign_ids(entries, feed)
    feats, dropped["cap"] = cap_features(sort_newest([e["feature"] for e in entries]))
    source = {"name": cfg["name"], "ok": err is None, "error": err, "newest": newest_iso(feats), "n": len(feats),
              "rows": len(rows), "pages": pages, "dropped": dropped}
    try:
        save_state(cfg["state"], {"v": 1, "feed": feed, "saved": iso(now_ms), "rows": keep})
    except OSError as e:
        source["state_error"] = err_text(e)
    attribution = [{"text": ATTRIBUTION[feed], "url": ATTRIBUTION_URL[feed], "licence": LICENCE[feed]}]
    if feed in CHANGES:
        attribution[0]["changes"] = CHANGES[feed]
    return envelope(feed, now, feats, [source], attribution, LICENCE[feed], PUBLIC_OK[feed], NON_COMMERCIAL[feed],
                    NOTE[feed], window, dropped["cap"])


def poll_cir(now=None, fetch=None):
    return poll_layer("cir", now, fetch)


def poll_kinetic(now=None, fetch=None):
    return poll_layer("kinetic", now, fetch)


FEEDS = {"cir": (poll_cir, 10800), "kinetic": (poll_kinetic, 10800)}
