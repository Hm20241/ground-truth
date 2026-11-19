"""IMF PortWatch daily chokepoint transits (keyless ArcGIS). v1.0, 2026-11-19 (Ground Truth 0.9.0).

PortWatch counts the ships that cross each of 28 maritime chokepoints every day, by type (container, dry bulk,
general cargo, ro-ro, tanker), from UN Global Platform satellite AIS (Spire, plus FleetMon terrestrial). A ship is
counted once per passage; it can count again only after 48 h. It matters most for Hormuz and Bab el-Mandeb, where
no free live AIS reaches.

Every 6 hours (feed `portwatch`) one poll makes, against the public ArcGIS FeatureServers on services9.arcgis.com:
* the daily table `Daily_Chokepoints_Data` from today - 45 days (about 42 days x 28 rows, one call, ~25 KB gzipped),
  paged with resultOffset while the server says exceededTransferLimit;
* the same table for the 7 calendar dates one year before the last 7 days (28 x 7 rows, ~5 KB);
* the chokepoint positions (`PortWatch_chokepoints_database`), only when the cached copy in
  <GT_DATA>/cache/portwatch_points.json is older than 7 days or lacks a chokepoint. A failed refresh falls back to
  the cached copy.

Probed 2026-11-19: `date` is esriFieldTypeDateOnly and comes back as a "YYYY-MM-DD" string, not epoch ms;
`date >= DATE '2026-10-05'` and `timestamp '... 00:00:00'` both filter it; maxRecordCount is 10,000 (not 1,000) and
a smaller resultRecordCount pages correctly; portid is "chokepoint1" .. "chokepoint28" (4 = Bab el-Mandeb Strait,
6 = Strait of Hormuz); the newest day (2026-11-15 on 11-19) was complete, all 28 rows, normal totals, so the data
runs about 3-4 days behind; a bad query answers HTTP 200 with an {"error": ...} body; gzip is honoured
(255 KB -> 25 KB). A day only counts once every chokepoint seen in the last week has a row for it.

Terms (IMF, https://www.imf.org/external/terms.htm): publishing and distribution allowed with the attribution
"Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)", data must not be altered (it is only averaged
here, never edited), commercial reuse needs IMF permission. Ground Truth is non-commercial: this data and anything
derived from it must never reach the trading agent.
"""
import datetime as dt
import gzip
import json
import os
import urllib.parse
import urllib.request

VERSION = "1.0"
ATTRIBUTION = "Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)"
ATTRIBUTION_URL = "https://portwatch.imf.org"
LICENCE = "IMF PortWatch: attribution required, unaltered; non-commercial here, never for the trading agent"
NOTE = ("Daily transits counted by IMF PortWatch from satellite AIS, about 3 days behind. A ship counts once per "
        "passage (48 h before it can count again). avg7 = mean of the last 7 days, year_ago7 = the same dates a year "
        "earlier, change % is blank when the year-ago mean is under 3 ships a day. tanker_dwt = PortWatch's estimate "
        "of the cargo the tankers carried on the last day, metric tonnes.")

_BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
DAILY_URL = _BASE + "Daily_Chokepoints_Data/FeatureServer/0/query"
POINTS_URL = _BASE + "PortWatch_chokepoints_database/FeatureServer/0/query"
# capacity_tanker = PortWatch's "trade volume" for tankers: each ship's estimated payload share x its deadweight
# tonnage, summed over the day, in metric tonnes (not the raw DWT of the ships). It is served as `tanker_dwt`.
FIELDS = "date,portid,portname,n_container,n_dry_bulk,n_general_cargo,n_roro,n_tanker,n_total,capacity_tanker"
UA = "GroundTruth/0.9 (personal non-commercial OSINT dashboard)"
TIMEOUT = 60
PAGE = 2000         # rows asked per call; the server caps at its own maxRecordCount and flags the rest
MAX_PAGES = 20
WINDOW_DAYS = 45    # rows kept per poll, from today - 45 d
SPARK_DAYS = 30
MEAN_DAYS = 7
MIN_BASE = 3.0      # ships/day: below this a year-ago mean gives no percentage
POINTS_MAX_AGE = 7 * 86400
POINTS_FILE = "portwatch_points.json"
PINNED_IDS = ("chokepoint6", "chokepoint4")             # Strait of Hormuz, Bab el-Mandeb Strait
PINNED_WORDS = ("hormuz", "bab el-mandeb", "bab-el-mandeb", "bab al-mandab")
SUMMARY_TOP = 10
SUMMARY_MAX = 2048

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)
    return body


def _query(fetch, url, params):
    """All rows of an ArcGIS query, paged with resultOffset. Raises on an error body or a broken page."""
    rows, offset = [], 0
    for _ in range(MAX_PAGES):
        p = dict(params, resultOffset=offset, resultRecordCount=PAGE, returnGeometry="false", f="json")
        d = json.loads(fetch(url + "?" + urllib.parse.urlencode(p, quote_via=urllib.parse.quote)))
        if not isinstance(d, dict):
            raise ValueError("PortWatch: unexpected response %s" % type(d).__name__)
        if d.get("error"):
            e = d["error"]
            raise RuntimeError("PortWatch query error %s: %s %s" % (e.get("code"), e.get("message"), "; ".join(
                str(x) for x in e.get("details") or [])))
        feats = d.get("features")
        if not isinstance(feats, list):
            raise ValueError("PortWatch: response without features")
        rows.extend(f.get("attributes") or {} for f in feats)
        if not (d.get("exceededTransferLimit") and feats):
            return rows
        offset += len(feats)
    raise RuntimeError("PortWatch: still paging after %d pages" % MAX_PAGES)


def _day(s):
    return dt.date.fromisoformat(str(s)[:10])


def _year_back(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 February
        return d.replace(year=d.year - 1, day=28)


def _int(v):
    return None if v is None else int(v)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _r1(x):
    return None if x is None else round(x, 1)


def _utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


# ---------------- chokepoint positions (cached 7 days) ----------------

def _points_path():
    return os.path.join(CACHE, POINTS_FILE)


def _load_points():
    try:
        with open(_points_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d.get("points"), dict) and d["points"] else None
    except (OSError, ValueError, AttributeError):
        return None


def _save_points(d):
    os.makedirs(CACHE, exist_ok=True)
    tmp = _points_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, separators=(",", ":"))
    os.replace(tmp, _points_path())


def _fetch_points(fetch, now):
    pts = {}
    for a in _query(fetch, POINTS_URL, {"where": "1=1", "outFields": "portid,portname,lat,lon",
                                        "orderByFields": "ObjectId"}):
        if a.get("portid") and a.get("lat") is not None and a.get("lon") is not None:
            pts[a["portid"]] = {"name": a.get("portname"), "lat": round(float(a["lat"]), 3),
                                "lon": round(float(a["lon"]), 3)}
    if not pts:
        raise RuntimeError("PortWatch: no chokepoint positions")
    return {"t": int(now.timestamp()), "fetched": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "points": pts}


def points(fetch=None, now=None, need=()):
    """portid -> {name, lat, lon}. Refreshes when the cache is older than 7 days or lacks a portid in `need`;
    a failed refresh falls back to the cached copy (raises only when there is none)."""
    fetch, now = fetch or _fetch, _utc(now)
    cached = _load_points()
    fresh = cached and now.timestamp() - cached.get("t", 0) < POINTS_MAX_AGE
    if fresh and all(p in cached["points"] for p in need):
        return cached["points"]
    try:
        d = _fetch_points(fetch, now)
    except Exception:
        if cached:
            return cached["points"]
        raise
    _save_points(d)
    return d["points"]


# ---------------- the feed ----------------

def _pinned(pid, name):
    n = (name or "").lower()
    return pid in PINNED_IDS or any(w in n for w in PINNED_WORDS)


def _pct(cur, base):
    if cur is None or base is None or base < MIN_BASE:
        return None
    return int(round((cur - base) / base * 100))


def _group(rows):
    by = {}
    for a in rows:
        pid, d = a.get("portid"), a.get("date")
        if pid and d:
            by.setdefault(pid, {})[_day(d)] = a
    return by


def poll(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    start = now.date() - dt.timedelta(days=WINDOW_DAYS)
    by = _group(_query(fetch, DAILY_URL, {"where": "date >= DATE '%s'" % start.isoformat(), "outFields": FIELDS,
                                          "orderByFields": "date,portid"}))
    if not by:
        raise RuntimeError("PortWatch returned no rows since %s" % start.isoformat())

    # newest complete day: every chokepoint seen in the last week has a row for it
    counts = {}
    for days in by.values():
        for d in days:
            counts[d] = counts.get(d, 0) + 1
    dates = sorted(counts)
    recent = set(dates[-MEAN_DAYS:])
    expected = sum(1 for days in by.values() if recent & set(days))
    through = next((d for d in reversed(dates) if counts[d] >= expected), dates[-1])

    win = [through - dt.timedelta(days=i) for i in range(MEAN_DAYS)]
    ya_end = _year_back(through)
    ya_start = ya_end - dt.timedelta(days=MEAN_DAYS - 1)
    ya = _group(_query(fetch, DAILY_URL, {
        "where": "date >= DATE '%s' AND date <= DATE '%s'" % (ya_start.isoformat(), ya_end.isoformat()),
        "outFields": FIELDS, "orderByFields": "date,portid"}))
    pts = points(fetch, now, need=tuple(by))

    out = []
    for pid, days in by.items():
        days = {d: a for d, a in days.items() if d <= through}
        if not days:
            continue
        last_day = max(days)
        a = days[last_day]
        name = a.get("portname") or (pts.get(pid) or {}).get("name") or pid
        cur = [days[d] for d in win if d in days]
        old = list((ya.get(pid) or {}).values())
        avg = {k: _mean([_int(r.get("n_" + k)) for r in cur]) for k in ("tanker", "total")}
        base = {k: _mean([_int(r.get("n_" + k)) for r in old]) for k in ("tanker", "total")}
        p = pts.get(pid) or {}
        spark_from = through - dt.timedelta(days=SPARK_DAYS - 1)
        out.append({
            "id": pid, "name": name, "lat": p.get("lat"), "lon": p.get("lon"),
            "last_day": last_day.isoformat(),
            "last": {"tanker": _int(a.get("n_tanker")), "total": _int(a.get("n_total")),
                     "container": _int(a.get("n_container")), "dry_bulk": _int(a.get("n_dry_bulk")),
                     "general_cargo": _int(a.get("n_general_cargo")), "roro": _int(a.get("n_roro")),
                     "tanker_dwt": _int(a.get("capacity_tanker"))},
            "avg7": {k: _r1(v) for k, v in avg.items()},
            "year_ago7": {k: _r1(v) for k, v in base.items()},
            "change_vs_year_pct": {k: _pct(avg[k], base[k]) for k in ("tanker", "total")},
            "spark": [[d.isoformat(), _int(days[d].get("n_tanker")), _int(days[d].get("n_total"))]
                      for d in sorted(days) if d >= spark_from],
            "pinned": _pinned(pid, name),
        })

    def key(c):
        t = c["change_vs_year_pct"]["tanker"]
        return (not c["pinned"], t is None, t if t is not None else 0, c["name"])

    out.sort(key=key)
    return {"data_through": through.isoformat(), "count": len(out), "fetched": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "chokepoints": out, "attribution": ATTRIBUTION, "attribution_url": ATTRIBUTION_URL, "licence": LICENCE,
            "note": NOTE}


def summary(data):
    """Compact view for the analyst (< 2 KB as compact JSON): the pinned chokepoints plus the 10 with the largest
    |tanker change %| vs a year ago. Lists are [tankers, total]. Never raises."""
    if not data:
        return None
    try:
        cps = data.get("chokepoints") or []
        pinned = [c for c in cps if c.get("pinned")]
        rest = [c for c in cps if not c.get("pinned") and c["change_vs_year_pct"]["tanker"] is not None]
        rest.sort(key=lambda c: (-abs(c["change_vs_year_pct"]["tanker"]), c["name"]))
        pair = lambda d: [d.get("tanker"), d.get("total")]
        rows = [{"name": c["name"], "day": pair(c["last"]), "avg7": pair(c["avg7"]), "yago7": pair(c["year_ago7"]),
                 "chg": pair(c["change_vs_year_pct"])} for c in pinned + rest[:SUMMARY_TOP]]
        s = {"data_through": data.get("data_through"), "licence": LICENCE,
             "key": "[tankers,total] ships/day: day=last day, avg7=last 7 days, yago7=same dates a year earlier, "
                    "chg=% vs a year ago (null if base <3/day)",
             "chokepoints": rows}
        while rows and len(json.dumps(s, separators=(",", ":"), ensure_ascii=False).encode()) >= SUMMARY_MAX:
            rows.pop()
        return s
    except Exception as e:
        return {"error": type(e).__name__}
