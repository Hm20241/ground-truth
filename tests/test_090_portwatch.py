"""Offline tests for 0.9.0: IMF PortWatch chokepoint transits (gt/portwatch.py).
Never touches the network. Fixtures are real ArcGIS responses saved on 2026-11-19 (UTC), trimmed to 7 chokepoints
(Suez, Bab el-Mandeb, Hormuz, Taiwan, Torres, Bering, Kerch) with a `portid IN (...)` filter:
  portwatch/daily_p0.json    2026-10-05 .. 2026-11-15, resultRecordCount=200, page 1 (200 rows, exceededTransferLimit)
  portwatch/daily_p1.json    the same query at resultOffset=200 (94 rows, last page)
  portwatch/year_ago.json    2025-11-09 .. 2025-11-15 (49 rows)
  portwatch/points.json      PortWatch_chokepoints_database, all 28 chokepoints
  portwatch/empty.json       a query with no rows (date >= 2026-11-16)
  portwatch/error_400.json   the HTTP-200 error body for a bad field name

Run: python3 -I tests/test_090_portwatch.py
"""
import datetime as dt
import gzip
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "portwatch")
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)
from gt import portwatch as pw  # noqa: E402

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


pw.urllib.request.urlopen = no_network
raw = {n: open(os.path.join(FX, n + ".json"), "rb").read() for n in ("daily_p0", "daily_p1", "year_ago", "points",
                                                                    "empty", "error_400")}
J = {n: json.loads(b) for n, b in raw.items()}
NOW = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.timezone.utc)
CACHE_FILE = os.path.join(TMP, "cache", pw.POINTS_FILE)
IDS = {"chokepoint1", "chokepoint4", "chokepoint6", "chokepoint11", "chokepoint18", "chokepoint26", "chokepoint28"}


def fake(pages=None, ya=None, pts=None, pts_fail=False, log=None):
    """Serves fixtures by URL; pages maps resultOffset -> bytes for the 45-day query."""
    pages = {0: raw["daily_p0"], 200: raw["daily_p1"]} if pages is None else pages

    def fetch(url):
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
        if log is not None:
            log.append((url, q))
        if "PortWatch_chokepoints_database" in url:
            if pts_fail:
                raise urllib.error.URLError("points down")
            return raw["points"] if pts is None else pts
        assert "Daily_Chokepoints_Data" in url, url
        if "2025-11-09" in q["where"]:
            return raw["year_ago"] if ya is None else ya
        off = int(q["resultOffset"])
        if off not in pages:
            raise AssertionError("unexpected resultOffset %d" % off)
        return pages[off]
    return fetch


def rows(*names):
    return [f["attributes"] for n in names for f in J[n]["features"]]


def mean7(rs, pid, field, d0, d1):
    xs = [r[field] for r in rs if r["portid"] == pid and d0 <= r["date"] <= d1]
    return sum(xs) / len(xs)


def raises(fn, exc, text=""):
    try:
        fn()
    except exc as e:
        return text in str(e)
    return False


def reset_cache():
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)


# ---- fixtures are what the server really returned
check(J["daily_p0"].get("exceededTransferLimit") is True and len(J["daily_p0"]["features"]) == 200, "page 1: 200 rows, exceededTransferLimit")
check("exceededTransferLimit" not in J["daily_p1"] and len(J["daily_p1"]["features"]) == 94, "page 2: 94 rows, last page")
check(J["daily_p0"]["fields"][0] == {"name": "date", "type": "esriFieldTypeDateOnly", "alias": "date", "sqlType": "sqlTypeDate",
                                     "domain": None, "defaultValue": None} and rows("daily_p0")[0]["date"] == "2026-10-05",
      "date is esriFieldTypeDateOnly, served as 'YYYY-MM-DD'")
check({r["portid"] for r in rows("daily_p0", "daily_p1")} == IDS and len(J["points"]["features"]) == 28, "7 chokepoints daily, 28 points")

# ---- a normal poll: paging, the year-ago window, the positions
reset_cache()
log = []
d = pw.poll(now=NOW, fetch=fake(log=log))
daily = [q for u, q in log if "Daily_Chokepoints_Data" in u]
check(len(log) == 4 and [q["resultOffset"] for q in daily] == ["0", "200", "0"], "4 calls: 2 pages, the year-ago window, the positions")
check(daily[0]["where"] == "date >= DATE '2026-10-05'" and daily[0]["resultRecordCount"] == str(pw.PAGE)
      and daily[0]["returnGeometry"] == "false" and daily[0]["f"] == "json" and daily[0]["orderByFields"] == "date,portid",
      "45-day query from today - 45 d, ordered for stable paging")
check(daily[2]["where"] == "date >= DATE '2025-11-09' AND date <= DATE '2025-11-15'", "year-ago query = the same 7 dates a year earlier")
check(all(" " not in u and "+" not in u.split("?", 1)[1] for u, q in log), "query strings percent-encoded")
check(d["data_through"] == "2026-11-15" and d["count"] == 7 and len(d["chokepoints"]) == 7, "data_through 2026-11-15, 7 chokepoints")
check({c["id"] for c in d["chokepoints"]} == IDS and d["fetched"] == "2026-11-19T12:00:00Z", "every id once; fetched = now")
check(d["attribution"] == pw.ATTRIBUTION == "Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)"
      and d["attribution_url"] == "https://portwatch.imf.org" and d["licence"] == pw.LICENCE and "trading agent" in d["licence"]
      and d["note"].startswith("Daily transits counted by IMF PortWatch from satellite AIS, about 3 days behind."),
      "attribution, licence and note")
json.dumps(d, allow_nan=False)
check(True, "output is plain JSON")
C = {c["id"]: c for c in d["chokepoints"]}
hz, bab, suez = C["chokepoint6"], C["chokepoint4"], C["chokepoint1"]
check(hz["name"] == "Strait of Hormuz" and bab["name"] == "Bab el-Mandeb Strait" and suez["name"] == "Suez Canal", "names")
check((hz["lat"], hz["lon"]) == (26.297, 56.86) and (bab["lat"], bab["lon"]) == (12.789, 43.35), "positions from the points layer, 3 decimals")

# ---- the means, against the raw fixture rows
R, Y = rows("daily_p0", "daily_p1"), rows("year_ago")
for c in d["chokepoints"]:
    for k in ("tanker", "total"):
        a = mean7(R, c["id"], "n_" + k, "2026-11-09", "2026-11-15")
        b = mean7(Y, c["id"], "n_" + k, "2025-11-09", "2025-11-15")
        assert c["avg7"][k] == round(a, 1) and c["year_ago7"][k] == round(b, 1), (c["id"], k)
        assert c["change_vs_year_pct"][k] == (None if b < 3 else int(round((a - b) / b * 100))), (c["id"], k)
check(True, "avg7, year_ago7 and change % match the raw rows for all 7 chokepoints")
check(hz["avg7"] == {"tanker": 0.4, "total": 2.3} and hz["year_ago7"] == {"tanker": 46.1, "total": 80.0}
      and hz["change_vs_year_pct"] == {"tanker": -99, "total": -97}, "Hormuz: 0.4/2.3 a day vs 46.1/80.0 a year ago, -99 %/-97 %")
check(bab["avg7"] == {"tanker": 8.9, "total": 25.6} and bab["year_ago7"] == {"tanker": 11.7, "total": 34.7}
      and bab["change_vs_year_pct"] == {"tanker": -24, "total": -26}, "Bab el-Mandeb: 8.9/25.6 vs 11.7/34.7, -24 %/-26 %")
check(isinstance(hz["change_vs_year_pct"]["tanker"], int) and isinstance(hz["avg7"]["tanker"], float), "pct is an int, means are floats")
last = [r for r in R if r["portid"] == "chokepoint4" and r["date"] == "2026-11-15"][0]
check(bab["last_day"] == "2026-11-15" and bab["last"] == {"tanker": last["n_tanker"], "total": last["n_total"],
      "container": last["n_container"], "dry_bulk": last["n_dry_bulk"], "general_cargo": last["n_general_cargo"],
      "roro": last["n_roro"], "tanker_dwt": last["capacity_tanker"]} and bab["last"]["tanker_dwt"] == 579403,
      "last day: counts by type, tanker_dwt = capacity_tanker (t)")
check(hz["last"]["tanker"] == 0 and hz["last"]["total"] == 2, "Hormuz 2026-11-15: 0 tankers, 2 ships")

# ---- the small-base rule
br, tor, ker = C["chokepoint26"], C["chokepoint18"], C["chokepoint28"]
check(br["year_ago7"]["tanker"] < 3 and br["year_ago7"]["total"] < 3 and br["change_vs_year_pct"] == {"tanker": None, "total": None},
      "Bering: year-ago under 3 a day -> no percentages")
check(tor["year_ago7"]["tanker"] == 2.0 and tor["change_vs_year_pct"]["tanker"] is None and isinstance(tor["change_vs_year_pct"]["total"], int),
      "Torres: tanker base 2.0 -> None, total base 8.1 -> a percentage")
check(ker["change_vs_year_pct"] == {"tanker": -90, "total": -97}, "Kerch: 4.4 tankers a day a year ago (>= 3) -> -90 %")
check(pw._pct(1.0, 2.99) is None and pw._pct(6.0, 3.0) == 100 and pw._pct(None, 10) is None and pw._pct(0.0, 3.0) == -100,
      "_pct boundary at 3 ships a day")

# ---- sort order and pinning
order = [c["id"] for c in d["chokepoints"]]
check(order[:2] == ["chokepoint6", "chokepoint4"] and hz["pinned"] and bab["pinned"]
      and not any(c["pinned"] for c in d["chokepoints"][2:]), "Hormuz and Bab el-Mandeb pinned, first")
rest = d["chokepoints"][2:]
tk = [c["change_vs_year_pct"]["tanker"] for c in rest]
nn = [t for t in tk if t is not None]
check(nn == sorted(nn) and tk[len(nn):] == [None] * (len(tk) - len(nn)), "then tanker change ascending, None last")
check([c["name"] for c in rest if c["change_vs_year_pct"]["tanker"] is None] == ["Bering Strait", "Torres Strait"], "None ties by name")
check(pw._pinned("chokepoint99", "Strait of Hormuz") and pw._pinned("chokepoint4", "renamed") and pw._pinned("x", "Bab el-Mandeb Strait")
      and not pw._pinned("chokepoint1", "Suez Canal"), "pinned by portid or by name")

# ---- spark
check(all(len(c["spark"]) == 30 for c in d["chokepoints"]), "spark: 30 days each")
check(hz["spark"][0][0] == "2026-10-17" and hz["spark"][-1] == ["2026-11-15", 0, 2]
      and all(len(p) == 3 and isinstance(p[1], int) and isinstance(p[2], int) for p in hz["spark"]), "spark = [date, tankers, total], oldest first")
check(len(json.dumps(d, separators=(",", ":"))) < 12000, "7-chokepoint output stays small (%d bytes)" % len(json.dumps(d, separators=(",", ":"))))

# ---- the server answering in one page gives the same result
one = dict(J["daily_p0"])
one.pop("exceededTransferLimit")
one["features"] = J["daily_p0"]["features"] + J["daily_p1"]["features"]
log2 = []
d1 = pw.poll(now=NOW, fetch=fake(pages={0: json.dumps(one).encode()}, log=log2))
check(d1 == d and len(log2) == 2, "one unpaged answer = the same result; cached positions -> 2 calls")

# ---- an incomplete newest day is not used
inc = json.loads(raw["daily_p1"])
inc["features"].append({"attributes": dict(inc["features"][-1]["attributes"], date="2026-11-16", portid="chokepoint6",
                                           portname="Strait of Hormuz", n_tanker=50, n_total=90)})
d2 = pw.poll(now=NOW, fetch=fake(pages={0: raw["daily_p0"], 200: json.dumps(inc).encode()}))
check(d2["data_through"] == "2026-11-15" and d2["chokepoints"][0]["last_day"] == "2026-11-15"
      and d2["chokepoints"][0]["avg7"] == hz["avg7"], "a day with 1 of 7 chokepoints is ignored")

# ---- the positions cache
c0 = json.load(open(CACHE_FILE))
check(len(c0["points"]) == 28 and c0["t"] == int(NOW.timestamp()) and c0["points"]["chokepoint6"]["lat"] == 26.297,
      "positions cached in <GT_DATA>/cache/portwatch_points.json")
log3 = []
pw.poll(now=NOW + dt.timedelta(days=6), fetch=fake(log=log3))
check(not any("PortWatch_chokepoints_database" in u for u, q in log3), "fresh cache (6 days) -> no positions call")
log4 = []
d4 = pw.poll(now=NOW + dt.timedelta(days=8), fetch=fake(log=log4, pts_fail=True))
check(any("PortWatch_chokepoints_database" in u for u, q in log4) and d4["chokepoints"][0]["lat"] == 26.297
      and json.load(open(CACHE_FILE))["t"] == c0["t"], "stale cache + failed refresh -> cached positions used, cache kept")
pw.poll(now=NOW + dt.timedelta(days=8), fetch=fake())
check(json.load(open(CACHE_FILE))["t"] == int((NOW + dt.timedelta(days=8)).timestamp()), "stale cache + good refresh -> cache rewritten")
small = json.loads(raw["points"])
small["features"] = [f for f in small["features"] if f["attributes"]["portid"] != "chokepoint28"]
reset_cache()
pw.poll(now=NOW, fetch=fake(pts=json.dumps(small).encode()))
log5 = []
pw.poll(now=NOW, fetch=fake(log=log5))
check(any("PortWatch_chokepoints_database" in u for u, q in log5) and len(json.load(open(CACHE_FILE))["points"]) == 28,
      "a chokepoint missing from a fresh cache -> refresh")
reset_cache()
check(raises(lambda: pw.poll(now=NOW, fetch=fake(pts_fail=True)), urllib.error.URLError), "no cache + failed positions -> raises")
with open(CACHE_FILE, "w") as fh:
    fh.write("{not json")
d6 = pw.poll(now=NOW, fetch=fake())
check(d6 == d and len(json.load(open(CACHE_FILE))["points"]) == 28, "a corrupt cache file is refetched")

# ---- failures raise (the scheduler keeps the last good data)
check(raises(lambda: pw.poll(now=NOW, fetch=fake(pages={0: raw["empty"]})), RuntimeError, "no rows"), "no rows -> RuntimeError")
check(raises(lambda: pw.poll(now=NOW, fetch=fake(pages={0: raw["error_400"]})), RuntimeError, "400"), "error body (HTTP 200) -> RuntimeError")
check(raises(lambda: pw.poll(now=NOW, fetch=fake(ya=raw["error_400"])), RuntimeError, "Invalid field"), "year-ago error body -> RuntimeError")


def down(url):
    raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)


check(raises(lambda: pw.poll(now=NOW, fetch=down), urllib.error.HTTPError), "HTTP error propagates")
check(raises(lambda: pw.poll(now=NOW, fetch=lambda u: b"<html>busy</html>"), ValueError), "non-JSON body -> ValueError")
check(raises(lambda: pw.poll(now=NOW, fetch=lambda u: b"[]"), ValueError, "unexpected"), "JSON that is not an object -> ValueError")
check(raises(lambda: pw.poll(now=NOW, fetch=lambda u: raw["daily_p0"]), RuntimeError, "still paging"),
      "a server that never stops paging -> RuntimeError after %d pages" % pw.MAX_PAGES)
yempty = pw.poll(now=NOW, fetch=fake(ya=raw["empty"]))
check(all(c["year_ago7"] == {"tanker": None, "total": None} and c["change_vs_year_pct"] == {"tanker": None, "total": None}
          for c in yempty["chokepoints"]) and [c["name"] for c in yempty["chokepoints"][:2]] == ["Bab el-Mandeb Strait", "Strait of Hormuz"],
      "no year-ago rows -> None; pinned still first, by name")

# ---- helpers
check(pw._year_back(dt.date(2028, 2, 29)) == dt.date(2027, 2, 28) and pw._year_back(dt.date(2026, 11, 15)) == dt.date(2025, 11, 15),
      "year back, 29 February -> 28 February")
check(pw.poll(now=dt.datetime(2026, 11, 19, 12, 0), fetch=fake()) == d, "naive now is read as UTC")


class Resp:
    def __init__(self, body, enc):
        self.body, self.headers = body, {"Content-Encoding": enc} if enc else {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen = {}


def fake_open(req, timeout=None):
    seen.update(ua=req.get_header("User-agent"), ae=req.get_header("Accept-encoding"), timeout=timeout)
    return Resp(gzip.compress(raw["points"]), "gzip")


pw.urllib.request.urlopen = fake_open
check(pw._fetch(pw.POINTS_URL + "?f=json") == raw["points"] and seen == {
    "ua": "GroundTruth/0.9 (personal non-commercial OSINT dashboard)", "ae": "gzip", "timeout": 60},
    "default fetch: honest User-Agent, gzip decoded, 60 s timeout")
pw.urllib.request.urlopen = lambda req, timeout=None: Resp(raw["empty"], None)
check(pw._fetch(pw.DAILY_URL) == raw["empty"], "default fetch: plain body passed through")
pw.urllib.request.urlopen = no_network

# ---- summary() for the analyst
s = pw.summary(d)
size = lambda x: len(json.dumps(x, separators=(",", ":"), ensure_ascii=False).encode())
check(s["data_through"] == "2026-11-15" and s["licence"] == pw.LICENCE and [c["name"] for c in s["chokepoints"][:2]]
      == ["Strait of Hormuz", "Bab el-Mandeb Strait"], "summary: data_through, licence, pinned first")
check(s["chokepoints"][0] == {"name": "Strait of Hormuz", "day": [0, 2], "avg7": [0.4, 2.3], "yago7": [46.1, 80.0], "chg": [-99, -97]},
      "summary entry = [tankers, total] pairs")
check([c["name"] for c in s["chokepoints"][2:]] == ["Kerch Strait", "Suez Canal", "Taiwan Strait"], "then by |tanker change|, None left out")
check(size(s) < 2048, "summary < 2 KB (%d bytes)" % size(s))
big = json.loads(json.dumps(d))
for i in range(30):
    c = json.loads(json.dumps(C["chokepoint11"]))
    c.update(id="x%d" % i, name="A Very Long Chokepoint Name Number %02d Passage" % i, pinned=False)
    c["change_vs_year_pct"] = {"tanker": (-1) ** i * (i * 7 % 101), "total": i}
    big["chokepoints"].append(c)
sb = pw.summary(big)
mags = [abs(c["chg"][0]) for c in sb["chokepoints"][2:]]
check(len(sb["chokepoints"]) <= 12 and mags == sorted(mags, reverse=True) and sb["chokepoints"][0]["name"] == "Strait of Hormuz",
      "37 chokepoints: pinned + at most 10, largest |change| first")
check(size(sb) < 2048, "summary stays < 2 KB with long names (%d bytes, %d entries)" % (size(sb), len(sb["chokepoints"])))
check(pw.summary(None) is None and pw.summary({}) is None and pw.summary({"chokepoints": [{"x": 1}]}) == {"error": "KeyError"},
      "summary of nothing -> None; bad data -> error type, never raises")
print("     summary() example:", json.dumps(dict(s, chokepoints=s["chokepoints"][:2])))
print("%d checks passed" % ok)
