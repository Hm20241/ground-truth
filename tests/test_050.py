"""Offline tests for 0.5.0: Global Fishing Watch ship traffic (gt/gfw.py, feeds.gfw_traffic, server summary).
Never touches the network: GFW responses are the real Kerch Strait reports saved on 2026-11-16
(tests/fixtures/gfw_kerch.json, fetched before the non-fishing filter was added; the logic is the same).

Run: python3 -I tests/test_050.py
"""
import datetime as dt
import io
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures")
os.environ["GT_DATA"] = tempfile.mkdtemp()
os.environ["GT_SEED"] = os.path.join(os.environ["GT_DATA"], "no-seed")
os.environ.pop("GFW_API_TOKEN", None)
sys.path.insert(0, PROJ)
from gt import feeds, gfw  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


gfw.urllib.request.urlopen = no_network
feeds.get = no_network
gfw.time.sleep = lambda s: None
fx = json.load(open(os.path.join(FX, "gfw_kerch.json")))
flags = gfw.by_day_flag(gfw._rows(fx["flag_365"]))
year_ago = gfw.by_day_flag(gfw._rows(fx["flag_year_ago"]))
vrows = gfw._rows(fx["vessels_8d"])

# ---- token lookup
os.environ["GFW_API_TOKEN"] = "t" * 300
check(gfw.api_key() == "t" * 300, "token from the environment first")
del os.environ["GFW_API_TOKEN"]
seed = os.environ["GT_SEED"]
os.makedirs(seed, exist_ok=True)
open(os.path.join(seed, "gfw.key"), "w").write("s" * 300 + "\n")
check(gfw.api_key() == "s" * 300, "token from $GT_SEED/gfw.key, whitespace stripped")

# ---- flag rows -> daily totals
day = "2025-11-20"
check(flags and sum(flags[day].values()) == sum(r["vesselIDs"] for r in gfw._rows(fx["flag_365"]) if r["date"] == day),
      "daily total = sum of vesselIDs over flags")
s = gfw.summarise("kerch", flags, year_ago, vrows)
days = sorted(flags)
n_days = (dt.date.fromisoformat(days[-1]) - dt.date.fromisoformat(days[0])).days + 1
check(len(s["daily"]) == n_days and s["daily"].count(None) == n_days - len(days), "series fills missing days with None")
check(s["newest_day"] == days[-1] and s["last_full_day"] == "2026-11-11", "newest day kept apart; last full day = day before")
full = s["daily"][:-1]
want7 = [x for x in full[-7:] if x is not None]
check(s["avg_7d"] == round(sum(want7) / len(want7), 1), "7-day mean over full days only, ignoring empty days")
ya_days = ["2025-11-%02d" % d for d in range(5, 12)]
ya_vals = [sum(year_ago[d].values()) for d in ya_days if d in year_ago]
check(s["same_week_last_year_avg"] == round(sum(ya_vals) / len(ya_vals), 1) and s["same_week_last_year_avg"] > 50,
      "year-ago mean over the matching days (Kerch was busy a year ago)")
check(s["change_vs_last_year_pct"] == round(100.0 * (s["avg_7d"] - s["same_week_last_year_avg"]) / s["same_week_last_year_avg"])
      and s["change_vs_last_year_pct"] < -80, "change vs last year computed and shows the Kerch collapse")
check(gfw._pct(3.5, 1.0) is None and gfw._pct(10, 160) == -94 and gfw._pct(5, None) is None,
      "no percentage on a baseline under %d ships/day" % gfw.MIN_BASE)
check(s["top_flags_7d"][0][0] == "RUS" and len(s["top_flags_7d"]) <= 8, "top flags over the last week")
check(s["ring"] == gfw.AREAS["kerch"][3] and s["kind"] == "chokepoint", "area ring and kind carried for the map")

# ---- chokepoint ships
check(s["types_by_day"] and all(isinstance(v, int) for t in s["types_by_day"].values() for v in t.values()), "types per day are counts")
sh = s["ships_last_full_day"]
check(sh and all(x.get("name") is not None and "flag" in x for x in sh), "ships seen on the last full day listed")
fast = [r for r in vrows if (r.get("speed") or 0) > gfw.MAX_KN and r["date"] == "2026-11-11"]
jumps = [x for x in sh if x["jump"]]
check(len(jumps) == len({r["vesselId"] for r in fast}) and all(x["kn"] is None for x in jumps),
      "speeds over 40 kn shown as position jumps, not speeds")

# ---- request shapes (presence() with a stubbed call)
calls = []


def fake_call(path, params=None, body=None, **k):
    calls.append((path, dict(params or {}), body))
    g = params.get("group-by")
    if g == "VESSEL_ID":
        return fx["vessels_8d"]
    a, b = params["date-range"].split(",")
    return fx["flag_year_ago"] if a.startswith("2025-11-0") else fx["flag_365"]


real_call = gfw.call
gfw.call = fake_call
today = dt.date(2026, 11, 16)
p = gfw.presence("kerch", today)
gfw.call = real_call
r1, r2, r3 = calls
a, b = (dt.date.fromisoformat(x) for x in r1[1]["date-range"].split(","))
check((b - a).days <= 366 and b == today + dt.timedelta(days=1), "year report stays within the 366-day API limit, end exclusive")
check(all(c[1]["filters[0]"] == gfw.NON_FISHING for c in calls), "every report leaves fishing boats out")
check(all(c[1]["spatial-aggregation"] == "true" and c[0] == "/4wings/report" for c in calls), "reports are spatially aggregated")
a, b = (dt.date.fromisoformat(x) for x in r2[1]["date-range"].split(","))
check(a == dt.date(2025, 11, 5) and b == dt.date(2025, 11, 12), "year-ago report = the 7 days matching the last full week")
check(r3[1]["group-by"] == "VESSEL_ID" and r1[1]["group-by"] == "FLAG", "chokepoints also get the per-vessel report")
check(r1[2]["geojson"]["coordinates"][0] == gfw.AREAS["kerch"][3], "the area polygon is POSTed as geojson")
calls.clear()
gfw.call = fake_call
gfw.presence("black_sea", today)
gfw.call = real_call
check(len(calls) == 2, "sea areas skip the per-vessel report")

# ---- HTTP handling
seq = []


class Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    seq.append(req)
    if len(seq) == 1:
        raise urllib.error.HTTPError(req.full_url, 429, "busy", {}, io.BytesIO(b'{"detail":"not enabled to perform more than one concurrent report"}'))
    return Resp(b'{"entries":[]}')


gfw.urllib.request.urlopen = fake_urlopen
check(gfw.call("/4wings/report", {"x": 1}, {"geojson": {}}) == {"entries": []} and len(seq) == 2, "a busy report slot is retried")
check(seq[0].get_header("Authorization") == "Bearer " + "s" * 300 and seq[0].get_method() == "POST", "bearer token, POST with a body")


def deny(req, timeout=None):
    seq.append(req)
    raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b'{"error":"Unauthorized"}'))


seq.clear()
gfw.urllib.request.urlopen = deny
try:
    gfw.call("/events", {}, {})
    check(False, "401 raises")
except gfw.GFWError as e:
    check(len(seq) == 1 and "401" in str(e) and "s" * 20 not in str(e), "401 fails at once, token not in the error")
gfw.urllib.request.urlopen = no_network

# ---- AIS-off events
ring = gfw.AREAS["red_sea"][3]
ev = {"start": "2026-11-06T04:17:23.000Z", "end": "2026-11-11T15:23:00.000Z", "id": "x1", "position": {"lat": 0, "lon": 0},
      "vessel": {"name": "ZBM ", "ssvid": "352000001", "flag": "PAN", "type": "cargo"},
      "gap": {"intentionalDisabling": True, "distanceKm": "412.75", "durationHours": 131.1, "offPosition": {"lat": 18.302, "lon": 39.71},
              "onPosition": {"lat": 21.0, "lon": 38.0}}}
g = gfw.parse_gap(ev, "red_sea")
check(g["km"] == 412.8 and g["hours"] == 131.1 and g["name"] == "ZBM" and (g["lon"], g["lat"]) == (39.71, 18.302),
      "gap parsed: distance given as text, off position used")
old = dict(ev, start="2017-01-11T08:11:38.000Z")
long_ = dict(ev, gap=dict(ev["gap"], durationHours=900))
away = dict(ev, gap=dict(ev["gap"], offPosition={"lat": 1.07, "lon": -117.4}))
kept = gfw.filter_gaps([gfw.parse_gap(x, "red_sea") for x in (ev, old, long_, away)], "2026-10-17", ring)
check(len(kept) == 1 and kept[0]["start"] == "2026-11-06T04:17:23Z",
      "gaps kept only if they start in the window, last under 14 days and switch off inside the area")
check(gfw.inside(39.7, 18.3, ring) and not gfw.inside(45.0, 18.3, ring) and not gfw.inside(-117, 1, ring), "point in polygon")

# ---- the feed: one area failing keeps its previous result
fresh = dict(s)


def fake_presence(area, today=None):
    if area == "hormuz":
        raise gfw.GFWError("HTTP 524 timeout")
    return dict(fresh, label=gfw.AREAS[area][0], kind=gfw.AREAS[area][1])


gfw.presence, real_presence = fake_presence, gfw.presence
gfw.gaps, real_gaps = (lambda area, today=None: [dict(g, area=area)] if area == "red_sea" else []), gfw.gaps
json.dump({"hormuz": dict(fresh, label="Strait of Hormuz", avg_7d=10.0)}, open(os.path.join(feeds.CACHE, "gfw_areas.json"), "w"))
d = feeds.gfw_traffic()
check(d["areas"]["hormuz"]["stale"] and d["areas"]["hormuz"]["avg_7d"] == 10.0 and "hormuz" in d["errors"],
      "a failed area keeps its previous result, marked stale, with the error")
check(d["areas"]["red_sea"]["gaps_30d"] == 1 and d["areas"]["gulf"]["gaps_30d"] == 0 and "gaps_30d" not in d["areas"]["suez"],
      "AIS-off counts per sea area")
check(d["attribution"] == "Powered by Global Fishing Watch" and "non-commercial" in d["licence"], "attribution and licence travel with the feed")
gfw.presence = lambda area, today=None: (_ for _ in ()).throw(gfw.GFWError("down"))
try:
    feeds.gfw_traffic()
    check(False, "all areas failing raises")
except RuntimeError:
    check(True, "every area failing raises (the server keeps the old feed)")
gfw.presence, gfw.gaps = real_presence, real_gaps
check(feeds.REGISTRY["gfw"][1] == 6 * 3600, "GFW refreshes every 6 hours")

# ---- server summary
import server  # noqa: E402
sm = server._gfw_summary(d)
check("ship_traffic_gfw" in server.NON_COMMERCIAL_KEYS and "non-commercial" in sm["licence"], "summary flagged non-commercial")
check(set(sm["areas"]) == set(gfw.AREAS) and "daily" not in json.dumps(sm) and "ring" not in sm["areas"]["kerch"],
      "summary is compact (no series, no polygons)")
check(sm["areas"]["kerch"]["types_last_full_day"] and len(sm["ais_off_events_30d"]) == 1, "summary carries types and AIS-off events")
check(len(json.dumps(sm)) < 9000, "summary stays small for the analyst prompt (%d chars)" % len(json.dumps(sm)))
print("%d checks passed" % ok)
