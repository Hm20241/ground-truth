"""Offline tests for 1.7.2: EPA AirNow air-quality monitors (gt/airnow.py, web/ext/airnow.js).
Never touches the network: sockets are blocked and every fetch is injected. Fixture (tests/fixtures/airnow/):
  hourly_2026112603.dat   the real Hourly AQ Obs file of 2026-11-26 03:00Z trimmed to its header and 27 rows:
                          every site at AQI 101+ that hour (9), 14 lower ones, 4 with no AQI (preliminary EPA
                          AirNow data, credited to the owning agencies)
Bad lines, empty files and odd values are built in the test from that header.

Run: python3 -I tests/test_airnow.py
"""
import datetime as dt
import gzip
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "airnow")
TMP = tempfile.mkdtemp(prefix="gt-airnow-")
os.environ["GT_DATA"] = TMP
os.environ.pop("GT_EXT_FEEDS", None)
sys.path.insert(0, PROJ)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import airnow as an  # noqa: E402
from gt import extfeeds  # noqa: E402

an.urllib.request.urlopen = no_network
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def raises(fn, exc, text=""):
    try:
        fn()
    except exc as e:
        return text in str(e)
    return False


def read(rel):
    return open(os.path.join(PROJ, rel), encoding="utf-8").read()


RAW = open(os.path.join(FX, "hourly_2026112603.dat"), "rb").read()
HEAD = RAW.split(b"\r\n", 1)[0].decode()
COLS = HEAD.replace('"', "").split(",")
NOW = dt.datetime(2026, 11, 26, 4, 40, tzinfo=dt.timezone.utc)
U03 = "https://files.airnowtech.org/airnow/2026/20261126/HourlyAQObs_2026112603.dat"
U02 = "https://files.airnowtech.org/airnow/2026/20261126/HourlyAQObs_2026112602.dat"


def row(**kw):
    """One CSV line in the real column order; unnamed cells are empty."""
    base = {"AQSID": "999000001", "SiteName": "Test Site", "Status": "Active", "EPARegion": "R3", "Latitude": "40.5",
            "Longitude": "-77.5", "CountryCode": "US", "StateName": "PA", "ValidDate": "11/26/2026",
            "ValidTime": "03:00", "DataSource": "Test Agency"}
    base.update(kw)
    return ",".join('"%s"' % base.get(c, "") for c in COLS)


def body(*rows):
    return ("\r\n".join((HEAD,) + rows) + "\r\n").encode()


def fake(files, log=None):
    def fetch(url):
        if log is not None:
            log.append(url)
        v = files.get(url)
        if v is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if isinstance(v, Exception):
            raise v
        return v
    return fetch


# ---- module contract
check(an.VERSION == "1.0" and set(an.FEEDS) == {"airnow"} and an.FEEDS["airnow"] == (an.airnow, 1800),
      "FEEDS: airnow every 1800 s")
check("airnow" in extfeeds.ALL and "airnow" in extfeeds.ENABLED, "extfeeds lists and enables the module")
reg = {}
meta = extfeeds.load(reg)
check(reg.get("airnow") == (an.airnow, 1800) and meta["airnow"]["module"] == "airnow"
      and meta["airnow"]["public_ok"] is True and meta["airnow"]["non_commercial"] is True,
      "extfeeds.load registers the feed with its terms flags")
src = read("gt/airnow.py")
imports = set(re.findall(r"^(?:import|from) ([a-z_.]+)", src, re.M))
check(imports <= {"csv", "datetime", "gzip", "io", "json", "math", "urllib.error", "urllib.request"},
      "standard library only: %s" % sorted(imports))
check(not re.search(r"api[_-]?key|token|password|secrets", src, re.I), "no key, token or secret anywhere in the module")
check(an.url_for(dt.datetime(2026, 11, 26, 3, tzinfo=dt.timezone.utc)) == U03, "the URL is the dated UTC folder and hour")
check(an.url_for(dt.datetime(2027, 1, 1, 0, tzinfo=dt.timezone.utc)).endswith("/airnow/2027/20270101/HourlyAQObs_2027010100.dat"),
      "the URL pads month, day and hour")
check("airnowapi.org/aq" not in src and "API_KEY" not in src, "the keyed AirNow API is not used")

# ---- category mapping: EPA's names, colours and break points
want = {0: "Good", 50: "Good", 51: "Moderate", 100: "Moderate", 101: "Unhealthy for Sensitive Groups",
        150: "Unhealthy for Sensitive Groups", 151: "Unhealthy", 200: "Unhealthy", 201: "Very Unhealthy",
        300: "Very Unhealthy", 301: "Hazardous", 500: "Hazardous", 742: "Hazardous"}
check(all(an.category(k) == v for k, v in want.items()), "category(): every EPA break point")
check(an.category(None) is None and an.category(-1) is None and an.category(float("nan")) is None
      and an.category(True) is None, "category(): no category for a missing, negative or NaN value")
check(an.COLOURS == {"Good": "#00e400", "Moderate": "#ffff00", "Unhealthy for Sensitive Groups": "#ff7e00",
                     "Unhealthy": "#ff0000", "Very Unhealthy": "#8f3f97", "Hazardous": "#7e0023"},
      "colours are EPA's RGB values (0,228,0 / 255,255,0 / 255,126,0 / 255,0,0 / 143,63,151 / 126,0,35)")

# ---- parsing the recorded file
sites, skipped = an.parse(RAW)
by = {s["site"]: s for s in sites}
check(len(sites) == 23 and skipped == 0, "fixture: 23 sites report an AQI, 4 rows without one are not sites (%d)" % len(sites))
check(by["New Delhi"]["aqi"] == 210 and by["New Delhi"]["category"] == "Very Unhealthy"
      and by["New Delhi"]["pollutant"] == "PM2.5" and by["New Delhi"]["us"] is False
      and by["New Delhi"]["place"] == "US embassy monitor, India", "an embassy monitor: AQI, category, pollutant, place")
check(by["Portola"]["state"] == "CA" and by["Portola"]["country"] == "US" and by["Portola"]["us"] is True
      and by["Portola"]["place"] == "CA" and by["Portola"]["aqi"] == 147, "a US site keeps its state")
check(by["Edmonton Central East"]["place"] == "Canada" and by["Edmonton Central East"]["aqi"] == 139
      and by["Edmonton Central East"]["pollutant"] == "PM2.5" and by["Edmonton Central East"]["state"] is None,
      "the highest pollutant wins (ozone 4, PM2.5 139, NO2 30) and N/A is no state")
check(by["West 43rd"]["pollutant"] == "PM10" and by["West 43rd"]["aqi"] == 59, "PM10 is named when it is the highest")
check(by["Experimental Lakes"]["pollutant"] == "ozone" and by["Experimental Lakes"]["aqi"] == 27, "ozone is named when it is the highest")
check(all(s["t"] == dt.datetime(2026, 11, 26, 3, tzinfo=dt.timezone.utc) for s in sites), "ValidDate + ValidTime are read as UTC")
check(by["Cataño 40"]["aqi"] == 170 and "Québec - Vieux-Limoilou" in by, "UTF-8 site names survive")
check(an.parse(gzip.compress(RAW))[0] == sites, "a gzip body parses the same")

# ---- bad lines never crash
bad = body(
    row(AQSID="1", SiteName="Good One", PM25_AQI="42"),
    '"2","Short row","Active"',                                             # wrong width
    row(AQSID="3", SiteName="No coords", Latitude="", Longitude="", PM25_AQI="160"),
    row(AQSID="4", SiteName="Bad coords", Latitude="north", PM25_AQI="160"),
    row(AQSID="5", SiteName="Bad date", ValidDate="yesterday", PM25_AQI="160"),
    row(AQSID="6", SiteName="Text AQI", PM25_AQI="high"),
    row(AQSID="7", SiteName="Negative AQI", PM25_AQI="-5"),
    row(AQSID="8", SiteName="Null island", Latitude="0", Longitude="0", PM25_AQI="160"),
    row(AQSID="9", SiteName="Out of range", Latitude="95", PM25_AQI="160"),
    'complete garbage \x00 "unterminated',
    "",
    row(AQSID="10", SiteName="Decimal AQI", PM25_AQI="151.0", OZONE_AQI="39.0", ValidDate="11/26/26"),
    row(AQSID="11", SiteName="NO2 only", NO2_AQI="120"),
    row(AQSID="12", SiteName="  Spaced   name ", PM10_AQI="301", StateName="MM", CountryCode="US"),
)
bs, bskip = an.parse(bad)
bb = {s["id"]: s for s in bs}
check(set(bb) == {"1", "10", "11", "12"}, "bad lines: only the four readable sites survive (%s)" % sorted(bb))
check(bskip >= 8, "bad lines are counted as skipped (%d)" % bskip)
check(bb["10"]["aqi"] == 151 and bb["10"]["category"] == "Unhealthy" and bb["10"]["t"].year == 2026,
      "'151.0' and a two-digit year are read (the fact sheet's format)")
check(bb["11"]["pollutant"] == "NO2" and bb["11"]["aqi"] == 120, "an NO2-only site counts by its NO2 AQI")
check(bb["12"]["site"] == "Spaced name" and bb["12"]["category"] == "Hazardous" and bb["12"]["place"] == "United States",
      "names are tidied; a mobile monitor (MM) shows its country")

# ---- empty and wrong files
check(an.parse(b"") == ([], 0) and an.parse(b"\r\n\r\n") == ([], 0), "an empty file is no sites, not an error")
check(an.parse((HEAD + "\r\n").encode()) == ([], 0), "a header-only file is no sites")
check(raises(lambda: an.parse(b"<?xml version='1.0'?><Error><Code>NoSuchKey</Code></Error>"), ValueError, "not an Hourly AQ Obs"),
      "an S3 error page is refused as not the product")
check(raises(lambda: an.parse(b"11/26/26|02:00|000020104|CHARLOTTETOWN|-4|NO|PPB|0|x\n"), ValueError),
      "another AirNow product (pipe-delimited) is refused")

# ---- the feed: payload fields
check(an.MIN_REPORTING == 300 and an.HOURS_BACK == 4 and an.CUT == 101 and an.TOP_N == 10, "defaults: 300 sites = full, 4 hours, cut 101, top 10")
an.MIN_REPORTING = 20   # the trimmed fixture has 23 reporting sites
log = []
d = an.airnow(NOW, fake({U03: RAW}, log))
json.dumps(d, allow_nan=False)
feats = d["geojson"]["features"]
P = [f["properties"] for f in feats]
s = d["summary"]
check(log == [U03], "one request when the last complete hour (now - 1 h) is there and full")
check(d["version"] == an.VERSION and d["fetched_at"] == "2026-11-26T04:40:00Z" and d["count"] == len(feats) == 9,
      "payload: version, fetched_at, count = 9 features")
check(all(p["aqi"] >= 101 for p in P) and [p["aqi"] for p in P] == [210, 198, 170, 147, 139, 112, 110, 106, 105],
      "the 101+ cut: only those sites are features, highest first")
check(all(f["geometry"]["type"] == "Point" and len(f["geometry"]["coordinates"]) == 2
          and -180 <= f["geometry"]["coordinates"][0] <= 180 and -90 <= f["geometry"]["coordinates"][1] <= 90 for f in feats),
      "features are [lon, lat] points")
KEYS = {"id", "site", "state", "country", "place", "us", "aqi", "category", "color", "pollutant", "agency", "time",
        "ts_ms", "source"}
check(all(set(p) == KEYS for p in P), "feature properties: %s" % sorted(KEYS))
check(all(p["ts_ms"] == 1795662000000 and p["time"] == "2026-11-26T03:00:00Z" for p in P), "ts_ms is the observation hour in ms")
check(all(p["category"] == an.category(p["aqi"]) and p["color"] == an.COLOURS[p["category"]] for p in P),
      "each feature carries EPA's category and colour for its AQI")
check(all(p["agency"] for p in P), "each feature credits the agency that owns the data")
check(s["reporting"] == 23 and s["unhealthy"] == 9 and s["reporting_us"] == 10 and s["unhealthy_us"] == 6,
      "summary: 23 reporting, 9 at 101+ (6 in the US)")
check(s["by_category"] == {"Good": 8, "Moderate": 6, "Unhealthy for Sensitive Groups": 6, "Unhealthy": 2,
                           "Very Unhealthy": 1, "Hazardous": 0} and sum(s["by_category"].values()) == s["reporting"],
      "summary: counts by category, all six named, adding up")
check(len(s["top"]) == 10 and [t["aqi"] for t in s["top"]] == [210, 198, 170, 147, 139, 112, 110, 106, 105, 73]
      and s["top"][9]["site"] == "Garden" and "lat" not in s["top"][0], "summary: the ten highest, including one under the cut")
check(s["obs_hour"] == "2026-11-26T03:00:00Z" and s["obs_ts_ms"] == 1795662000000 and s["file_hour"] == s["obs_hour"],
      "summary: the observation hour")
check(d["licence"] == an.LICENCE and d["public_ok"] is an.PUBLIC_OK["airnow"] and d["non_commercial"] is True
      and d["attribution"] == [an.ATTRIBUTION] and d["attribution_url"] == "https://www.airnow.gov" and d["note"] == an.NOTE
      and d["preliminary"] is True, "payload: licence, attribution, public_ok, non_commercial, note, preliminary")
check("preliminary" in an.ATTRIBUTION.lower() and "agencies" in an.ATTRIBUTION and "EPA AirNow" in an.ATTRIBUTION,
      "the credit names the agencies and EPA AirNow and says preliminary")
check(all(set(x) == {"name", "ok", "error", "newest", "n"} for x in d["sources"]) and d["sources"][0]["ok"]
      and d["sources"][0]["n"] == 23, "sources rows have the house shape")
check([c["name"] for c in d["categories"]] == [n for _, n, _ in an.CATEGORIES] and d["cut"] == 101, "payload names the category scale")
check(an._size(d) < 12000, "the payload is small (%d bytes)" % an._size(d))
check("—" not in json.dumps(d, ensure_ascii=False) and "—" not in read("web/ext/airnow.js"), "no em dashes in the payload or the page text")

# ---- which hour is used
log = []
d2 = an.airnow(NOW, fake({U02: RAW}, log))
check(log == [U03, U02] and d2["sources"][0]["ok"] is False and "404" in d2["sources"][0]["error"]
      and d2["sources"][1]["ok"] and d2["count"] == 9 and d2["summary"]["file_hour"] == "2026-11-26T02:00:00Z",
      "a missing newest hour (404) falls back to the hour before")
thin = body(row(AQSID="1", SiteName="Lonely", PM25_AQI="155"))
log = []
d3 = an.airnow(NOW, fake({U03: thin, U02: RAW}, log))
check(log == [U03, U02] and d3["summary"]["reporting"] == 23, "a thin newest file is passed over for a full earlier one")
log = []
d4 = an.airnow(NOW, fake({U03: thin}, log))
check(len(log) == 4 and d4["count"] == 1 and d4["summary"]["reporting"] == 1 and d4["summary"]["unhealthy"] == 1
      and d4["summary"]["top"][0]["category"] == "Unhealthy", "when no file is full, the fullest one found is used")
check(len(set(log)) == 4 and log[3].endswith("HourlyAQObs_2026112600.dat"), "four hours are tried, newest first")
midnight = []
try:
    an.airnow(dt.datetime(2026, 11, 26, 0, 10, tzinfo=dt.timezone.utc), fake({}, midnight))
except RuntimeError:
    pass
check(midnight[0].endswith("/airnow/2026/20261125/HourlyAQObs_2026112523.dat"), "just after midnight UTC the feed asks for yesterday's folder")

# ---- failure: raise, so the server keeps the last good data and marks the feed in error
check(raises(lambda: an.airnow(NOW, fake({})), RuntimeError, "every hour failed"), "every hour missing: RuntimeError")
check(raises(lambda: an.airnow(NOW, fake({U03: urllib.error.URLError("down"), U02: TimeoutError("slow")})), RuntimeError, "every hour failed"),
      "network errors: RuntimeError, not a crash")
check(raises(lambda: an.airnow(NOW, fake({U03: b"", U02: (HEAD + "\r\n").encode()})), RuntimeError, "no site reports"),
      "empty files only: RuntimeError (no empty payload replaces good data)")
check(raises(lambda: an.airnow(NOW, fake({U03: b"<Error/>"})), RuntimeError), "an error page everywhere: RuntimeError")
quiet = body(*[row(AQSID=str(i), SiteName="Clean %d" % i, PM25_AQI=str(10 + i)) for i in range(25)])
d5 = an.airnow(NOW, fake({U03: quiet}))
check(d5["count"] == 0 and d5["geojson"]["features"] == [] and d5["summary"]["reporting"] == 25
      and d5["summary"]["unhealthy"] == 0 and len(d5["summary"]["top"]) == 10, "a clean-air hour: no features, summary still there")

# ---- size cap
many = body(*[row(AQSID=str(i), SiteName="Smoke %d" % i, PM25_AQI=str(150 + i % 300), Latitude=str(30 + i % 20),
                  Longitude=str(-120 + i % 40)) for i in range(3000)])
d6 = an.airnow(NOW, fake({U03: many}))
check(an._size(d6) <= an.MAX_BYTES and d6["trimmed"] > 0 and d6["count"] == len(d6["geojson"]["features"]) < 3000
      and d6["summary"]["unhealthy"] == 3000, "a huge smoke day is trimmed under MAX_BYTES; the summary keeps the true count")
check(min(f["properties"]["aqi"] for f in d6["geojson"]["features"]) >= sorted(150 + i % 300 for i in range(3000))[-d6["count"]],
      "trimming drops the lowest readings first")


class Big:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return b"x" * n


an.urllib.request.urlopen = lambda req, timeout=None: Big()
check(raises(lambda: an._fetch(U03), ValueError, "larger than"), "_fetch refuses a body over MAX_READ")
seen = {}


class Small(Big):
    def read(self, n=-1):
        return gzip.compress(RAW)


def opener(req, timeout=None):
    seen.update(url=req.full_url, ua=req.get_header("User-agent"), timeout=timeout)
    return Small()


an.urllib.request.urlopen = opener
check(an._fetch(U03) == RAW and seen["url"] == U03 and seen["timeout"] == an.TIMEOUT and "@" not in seen["ua"]
      and "?" not in seen["url"], "_fetch: a plain GET with a timeout, a generic User-Agent and no query string")
an.urllib.request.urlopen = no_network

# ---- page side
idx, js, ver = read("web/index.html"), read("web/ext/airnow.js"), read("VERSION").strip()
tag = re.search(r'<script src="ext/airnow\.js\?v=([\d.]+)"></script>', idx)
check(tag and tag.group(1) == ver, "index.html loads ext/airnow.js with ?v=" + ver)
check(idx.index('src="ext/fronts.js') < idx.index('src="ext/airnow.js') < idx.index('src="app.js'),
      "airnow.js loads after the other extensions and before app.js")
check("GTXQ" in js and 'GTX.feed("airnow"' in js and 'GTX.tab({ id: "airnow"' in js and 'GTX.popup("aq-pt"' in js
      and 'key: "airnow"' in js and "GTX.when(" in js, "airnow.js: layer, feed, popup and tab through GTX, times through GTX.when")
check(all(c.lower() in js.lower() for c in an.COLOURS.values()) and all(n in js for n in an.COLOURS),
      "airnow.js uses EPA's category names and colours")
check("font-size:14px" in js and not re.search(r"font-size:\s*(?:[0-9]|1[0-3])(?:\.\d+)?px", js), "tab text is 14 px or more")
check("Preliminary" in js and "airnow.gov" in js, "the page says the data are preliminary and credits AirNow")
check("No air quality data here yet" in js, "the tab copes with the feed being absent")
for rel in ("web/app.js", "server.py"):
    check("airnow" not in read(rel), "%s is untouched by this source" % rel)
trading = [os.path.join(dp, n) for dp, _, ns in os.walk(os.path.join(PROJ, "gt")) for n in ns
           if n.endswith(".py") and n != "airnow.py" and n != "extfeeds.py" and "airnow" in open(os.path.join(dp, n), encoding="utf-8").read()]
check(not trading, "no other module reads the airnow feed (it feeds the page only): %s" % trading)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d checks passed" % ok)
