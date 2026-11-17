"""Global Fishing Watch ship traffic for the waters the volunteer AIS network can't hear.
v1.0, 2026-11-16 (Ground Truth 0.5.0).

GFW merges satellite and terrestrial AIS, so it covers the Gulf, Hormuz and the Red Sea, but it runs
about 96 hours behind real time. Per area, every run makes (one report at a time, GFW's rule):

* a 4Wings report on `public-global-presence:latest` (one AIS position per vessel per hour), spatially
  aggregated over the area, daily, grouped by flag, fishing boats and gear left out, for the last 366 days
  (the API maximum). Summing
  `vesselIDs` over flags gives the distinct ships seen in the area each day. For the small chokepoint
  boxes that is close to a daily transit count (plus ships at anchor inside the box).
* the same report for the matching 7 days a year earlier (the year-long series stops ~10 days short).
* chokepoints only: the per-vessel report (`group-by=VESSEL_ID`) for the last 12 days, for vessel types
  and the names of the ships seen.
* seas only: AIS-off events (`public-global-gaps-events:latest`, a GFW prototype): a ship stops
  transmitting for 12 h or more, at least 50 nm from shore, where satellite reception is good.

Probed 2026-11-16: `group-by` for presence accepts FLAG, VESSEL_ID, MMSI (not VESSEL_TYPE or GEARTYPE);
date-range end is exclusive; at most 366 days per report; `filters[0]` takes SQL-like vessel_type tests;
the newest day is ~4 days back; the events API returns every gap that
overlaps the window, including multi-year ones, so gaps are filtered here.

Licence: CC BY-NC 4.0, NON-COMMERCIAL ONLY. Wherever the data is shown, "Powered by Global Fishing Watch"
must link to https://globalfishingwatch.org. Never pass this data (or anything derived from it) to the
trading agent. The token stays server-side.

The token is read from $GFW_API_TOKEN, else $GT_SEED/gfw.key (container), else ~/.config/globalfishingwatch/key
(the Mac). It is never logged.
"""
import datetime as dt
import json
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://gateway.api.globalfishingwatch.org/v3"
PRESENCE = "public-global-presence:latest"
GAPS = "public-global-gaps-events:latest"
UA = "GroundTruth/0.5 (personal non-commercial OSINT dashboard)"
YEAR_DAYS = 366       # API maximum per report
SHIP_DAYS = 12        # per-vessel window for chokepoints
GAP_DAYS = 30
GAP_LIMIT = 200       # kept per area
MAX_GAP_H = 14 * 24   # longer "gaps" are mostly ships laid up, not going dark
MAX_GAP_PAGES = 10    # 100 events a page
MAX_KN = 40           # faster "speeds" are position jumps
ATTRIBUTION = "Powered by Global Fishing Watch"
ATTRIBUTION_URL = "https://globalfishingwatch.org"
LICENCE = "CC BY-NC 4.0: non-commercial use only; never for the trading agent"
# Fishing boats and gear swamp the counts (thousands of them in the Taiwan Strait and the Gulf) and say
# little about shipping, so every report leaves them out. Probed 2026-11-16: Taiwan Strait 4,500-12,000 a
# day unfiltered, 2,400-3,300 with this filter.
NON_FISHING = 'vessel_type not in ("fishing","gear")'


def _box(lon0, lat0, lon1, lat1):
    return [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]


# name: (label, kind, theatre, polygon ring [lon, lat]); chokepoints are small boxes across the shipping lanes.
AREAS = {
    "hormuz": ("Strait of Hormuz", "chokepoint", "middle-east", _box(56.25, 26.2, 56.75, 26.85)),
    "bab_el_mandeb": ("Bab el-Mandeb", "chokepoint", "middle-east", _box(43.15, 12.35, 43.65, 12.95)),
    "suez": ("Suez Canal (south)", "chokepoint", "middle-east", _box(32.45, 30.0, 32.7, 30.25)),
    "kerch": ("Kerch Strait", "chokepoint", "ukraine-russia", _box(36.4, 45.2, 36.75, 45.45)),
    "gulf": ("Persian Gulf", "sea", "middle-east",
             [[47.8, 30.4], [48.2, 28.6], [49.8, 26.2], [50.6, 24.4], [52.0, 23.9], [54.6, 24.0], [56.1, 24.9],
              [56.3, 26.2], [56.6, 27.3], [54.2, 27.2], [51.0, 29.0], [49.6, 30.5], [47.8, 30.4]]),
    "gulf_of_oman": ("Gulf of Oman", "sea", "middle-east", _box(56.8, 22.4, 60.5, 25.8)),
    "red_sea": ("Red Sea", "sea", "middle-east",
                [[32.5, 29.95], [33.6, 27.3], [35.5, 24.0], [37.0, 20.5], [38.5, 18.0], [39.4, 15.6], [41.5, 13.6],
                 [43.2, 12.4], [43.6, 12.7], [43.2, 13.8], [42.7, 15.5], [42.4, 17.0], [40.5, 19.5], [39.0, 21.8],
                 [37.5, 24.5], [35.5, 27.5], [34.9, 29.5], [34.4, 29.6], [32.5, 29.95]]),
    "gulf_of_aden": ("Gulf of Aden", "sea", "middle-east", _box(43.7, 11.0, 51.5, 14.6)),
    "black_sea": ("Black Sea and Sea of Azov", "sea", "ukraine-russia", _box(27.4, 41.15, 41.9, 47.4)),
    "taiwan_strait": ("Taiwan Strait", "sea", "indo-pacific", _box(117.5, 22.5, 121.0, 26.0)),
}


def api_key():
    k = (os.environ.get("GFW_API_TOKEN") or "").strip()
    if k:
        return k
    for p in (os.path.join(os.environ.get("GT_SEED") or "/seed", "gfw.key"),
              os.path.expanduser("~/.config/globalfishingwatch/key")):
        try:
            k = open(p, encoding="utf-8").read().strip()
            if k:
                return k
        except OSError:
            pass
    raise RuntimeError("no Global Fishing Watch token configured")


class GFWError(RuntimeError):
    pass


def call(path, params=None, body=None, timeout=150, tries=4):
    """One API call. Retries a busy report slot (429 'concurrent report'), 5xx and network errors."""
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + api_key(), "User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode("utf-8", "replace")
            last = "HTTP %s %s" % (e.code, detail.replace("\n", " ")[:200])
            busy = e.code == 429 and "concurrent" in detail.lower()
            if e.code < 500 and not busy:
                raise GFWError(last) from None   # bad token, rate cap or a bad request: retrying won't help
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = "%s: %s" % (type(e).__name__, e)
        if attempt < tries - 1:
            time.sleep(20 * (attempt + 1))
    raise GFWError(last or "no response")


def _day(d):
    return d.strftime("%Y-%m-%d")


def _rows(d):
    return [r for e in (d.get("entries") or []) for rows in e.values() for r in (rows or [])]


def report(ring, start, end, group="FLAG", filt=NON_FISHING):
    """Presence rows for [start, end) over one polygon ring, daily, spatially aggregated, fishing boats left out."""
    params = {"spatial-resolution": "LOW", "temporal-resolution": "DAILY", "group-by": group,
              "datasets[0]": PRESENCE, "format": "JSON", "spatial-aggregation": "true",
              "date-range": "%s,%s" % (_day(start), _day(end))}
    if filt:
        params["filters[0]"] = filt
    return _rows(call("/4wings/report", params, {"geojson": {"type": "Polygon", "coordinates": [ring]}}))


def by_day_flag(rows):
    """{day: {flag: distinct vessels}} from FLAG-grouped rows."""
    out = {}
    for r in rows:
        day = (r.get("date") or "")[:10]
        if day:
            f = out.setdefault(day, {})
            fl = r.get("flag") or "?"
            f[fl] = f.get(fl, 0) + int(r.get("vesselIDs") or 0)
    return out


def daily_series(flags, start, end):
    """Totals per day from start to end (inclusive dates), None where GFW returned nothing."""
    out, d = [], start
    while d <= end:
        f = flags.get(_day(d))
        out.append(sum(f.values()) if f else None)
        d += dt.timedelta(days=1)
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 1) if xs else None


MIN_BASE = 5  # ships/day: below this a percentage change is noise (Kerch 3.5 vs 1.0 read as +250%)


def _pct(a, b):
    return round(100.0 * (a - b) / b) if a is not None and b is not None and b >= MIN_BASE else None


def summarise(area, flags, year_ago_flags, vessel_rows):
    """Pure: everything shown and handed to the analyst for one area.
    The newest day GFW returns is often still filling in, so it is shown but left out of the averages."""
    label, kind, theatre, ring = AREAS[area]
    days = sorted(flags)
    if not days:
        return None
    start = dt.date.fromisoformat(days[0])
    newest = dt.date.fromisoformat(days[-1])
    last_full = newest - dt.timedelta(days=1) if len(days) > 1 else newest
    series = daily_series(flags, start, newest)
    full = series[:-1] if len(series) > 1 else series
    rec, base = full[-7:], full[-35:-7]
    avg7 = _mean(rec)
    med28 = statistics.median([x for x in base if x is not None]) if any(x is not None for x in base) else None
    ya_days = [_day(last_full - dt.timedelta(days=365 + i)) for i in range(7)]
    ya = _mean([sum(year_ago_flags[d].values()) for d in ya_days if d in year_ago_flags])
    week = [_day(last_full - dt.timedelta(days=i)) for i in range(7)]
    fl = {}
    for d in week:
        for k, v in (flags.get(d) or {}).items():
            fl[k] = fl.get(k, 0) + v
    out = {"label": label, "kind": kind, "theatre": theatre, "ring": ring,
           "start": days[0], "daily": series, "newest_day": days[-1], "newest_day_vessels": series[-1],
           "last_full_day": _day(last_full), "last_full_day_vessels": full[-1],
           "avg_7d": avg7, "median_prior_28d": med28, "change_vs_28d_pct": _pct(avg7, med28),
           "same_week_last_year_avg": ya, "change_vs_last_year_pct": _pct(avg7, ya),
           "top_flags_7d": [[k, round(v / 7.0, 1)] for k, v in sorted(fl.items(), key=lambda kv: -kv[1])[:8]]}
    if vessel_rows is not None:
        out.update(ships_summary(vessel_rows, _day(last_full)))
    return out


def ships_summary(rows, day):
    """Chokepoints: vessel types per day and the ships seen on `day` (from VESSEL_ID-grouped rows)."""
    types, ships = {}, {}
    for r in rows:
        d = (r.get("date") or "")[:10]
        vid = r.get("vesselId") or r.get("vessel_id")
        if not d or not vid:
            continue
        vt = (r.get("vesselType") or r.get("vessel_type") or "unknown").lower()
        types.setdefault(d, {}).setdefault(vt, set()).add(vid)
        if d == day and vid not in ships:
            kn = r.get("speed") if isinstance(r.get("speed"), (int, float)) else None
            ships[vid] = {"name": (r.get("shipName") or "").strip(), "flag": r.get("flag"), "type": vt,
                          "mmsi": r.get("mmsi"), "imo": r.get("imo") or None,
                          # over 40 kn is a position jump (GPS interference or spoofing), not a real speed
                          "kn": round(kn, 1) if kn is not None and kn <= MAX_KN else None,
                          "jump": kn is not None and kn > MAX_KN,
                          "in": (r.get("entryTimestamp") or "")[11:16] or None}
    return {"types_by_day": {d: {t: len(v) for t, v in sorted(ty.items(), key=lambda kv: -len(kv[1]))}
                             for d, ty in sorted(types.items())},
            "ships_last_full_day": sorted(ships.values(), key=lambda s: (s["in"] or "", s["name"]))[:120]}


def presence(area, today=None):
    """Live: the three reports for one area, summarised."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    ring = AREAS[area][3]
    flags = by_day_flag(report(ring, today - dt.timedelta(days=YEAR_DAYS - 1), today + dt.timedelta(days=1)))
    if not flags:
        raise GFWError("no presence rows")
    last_full = dt.date.fromisoformat(max(flags)) - dt.timedelta(days=1)
    ya_end = last_full - dt.timedelta(days=364)              # exclusive end: covers last_full-365 back 7 days
    year_ago = by_day_flag(report(ring, ya_end - dt.timedelta(days=7), ya_end))
    vessels = None
    if AREAS[area][1] == "chokepoint":
        vessels = report(ring, today - dt.timedelta(days=SHIP_DAYS), today + dt.timedelta(days=1), group="VESSEL_ID")
    return summarise(area, flags, year_ago, vessels)


# ---------------- AIS-off events ----------------

def inside(lon, lat, ring):
    """Ray-casting point-in-polygon for one ring of [lon, lat]."""
    hit = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def gaps(area, today=None, days=GAP_DAYS, limit=GAP_LIMIT):
    """AIS-off events that START inside the window, last under MAX_GAP_H and switch off inside the area."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    start = _day(today - dt.timedelta(days=days))
    ring = AREAS[area][3]
    body = {"datasets": [GAPS], "startDate": start, "endDate": _day(today + dt.timedelta(days=1)),
            "geometry": {"type": "Polygon", "coordinates": [ring]}}
    out, offset = [], 0
    for _ in range(MAX_GAP_PAGES):
        d = call("/events", {"limit": 100, "offset": offset}, body)
        rows = d.get("entries") or []
        out += filter_gaps((parse_gap(r, area) for r in rows), start, ring)
        nxt = d.get("nextOffset")
        if not rows or nxt in (None, offset):
            break
        offset = nxt
    out.sort(key=lambda g: g["start"], reverse=True)
    return out[:limit]


def filter_gaps(parsed, start, ring):
    return [g for g in parsed if g and g["start"] >= start and (g["hours"] or 0) <= MAX_GAP_H
            and inside(g["lon"], g["lat"], ring)]


def _num(x, nd=1):
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def parse_gap(r, area):
    g = r.get("gap") or {}
    off = g.get("offPosition") or r.get("position") or {}
    v = r.get("vessel") or {}
    if _num(off.get("lon"), 3) is None or _num(off.get("lat"), 3) is None or not r.get("start"):
        return None
    hours = _num(g.get("durationHours"))
    if hours is None and r.get("end"):
        try:
            hours = round((dt.datetime.fromisoformat(r["end"].replace("Z", "+00:00")) -
                           dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00"))).total_seconds() / 3600, 1)
        except ValueError:
            hours = None
    on = g.get("onPosition") or {}
    return {"area": area, "start": r["start"][:19] + "Z", "end": r["end"][:19] + "Z" if r.get("end") else None,
            "hours": hours, "lon": _num(off["lon"], 3), "lat": _num(off["lat"], 3),
            "on_lon": _num(on.get("lon"), 3), "on_lat": _num(on.get("lat"), 3), "km": _num(g.get("distanceKm")),
            "intentional": g.get("intentionalDisabling"),
            "name": (v.get("name") or "").strip(), "flag": v.get("flag"), "mmsi": v.get("ssvid"),
            "type": (v.get("type") or "").lower() or None, "id": r.get("id")}
