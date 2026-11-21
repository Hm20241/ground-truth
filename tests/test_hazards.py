"""Offline tests for 0.11.0: GDACS hazards and EMSC/USGS quakes (gt/hazards.py).
Never touches the network: sockets are blocked and every fetch is injected. Fixtures (tests/fixtures/hazards/):
  gdacs_p1.json, gdacs_p2.json   synthetic GDACS SEARCH pages in the real 2026-11-20 structure (invented events)
  gdacs_wf.json                  synthetic wildfire page
  emsc.json                      synthetic EMSC FDSN JSON (invented events, real key set; 1-2 fractional digits)
  usgs_explosion.json            synthetic USGS GeoJSON (explosions in Israel, Syria, Washington)
  usgs_nuke.json, usgs_m4.json   synthetic USGS GeoJSON (a nuclear explosion; the M4+ fallback)
  usgs_explosion_real.json       real USGS response of 2026-11-20 trimmed to 3 quarry blasts (US public domain)
  usgs_nuke_empty.json           real empty USGS response of 2026-11-20

Run: python3 -I tests/test_hazards.py
"""
import datetime as dt
import gzip
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "hazards")
TMP = tempfile.mkdtemp(prefix="gt-hazards-")
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import hazards as hz  # noqa: E402

hz.urllib.request.urlopen = no_network
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


RAW = {n[:-5]: open(os.path.join(FX, n), "rb").read() for n in os.listdir(FX) if n.endswith(".json")}
NOW = dt.datetime(2026, 11, 20, 5, 30, tzinfo=dt.timezone.utc)
LOCKEYS = ("country", "country_name", "sea", "theatre")


def q(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


def gdacs_fake(log=None, pages=None, wf=None, fail=()):
    pages = pages if pages is not None else {1: RAW["gdacs_p1"], 2: RAW["gdacs_p2"]}

    def fetch(url):
        if log is not None:
            log.append(url)
        p = q(url)
        assert url.startswith(hz.GDACS_URL), url
        if p["eventlist"] == "WF":
            if "wf" in fail:
                raise urllib.error.HTTPError(url, 503, "busy", {}, None)
            if wf is not None:
                return wf if p["alertlevel"] == "Green" else b""
            levels = p["alertlevel"].split(";")
            body = json.loads(RAW["gdacs_wf"])
            body["features"] = [f for f in body["features"] if f["properties"]["alertlevel"] in levels]
            return json.dumps(body).encode() if (body["features"] and p["pagenumber"] == "1") else b""
        if "main" in fail:
            raise urllib.error.URLError("down")
        return pages.get(int(p["pagenumber"]), b"")
    return fetch


def quake_fake(log=None, emsc=None, expl=None, nuke=None, m4=None, fail=()):
    def fetch(url):
        if log is not None:
            log.append(url)
        if "seismicportal" in url:
            if "emsc" in fail:
                raise urllib.error.URLError("emsc down")
            return RAW["emsc"] if emsc is None else emsc
        p = q(url)
        if p.get("eventtype") == "nuclear explosion":
            if "nuke" in fail:
                raise urllib.error.HTTPError(url, 500, "err", {}, None)
            return RAW["usgs_nuke"] if nuke is None else nuke
        if p.get("eventtype") == "explosion":
            if "expl" in fail:
                raise urllib.error.HTTPError(url, 500, "err", {}, None)
            return RAW["usgs_explosion"] if expl is None else expl
        if p.get("minmagnitude"):
            if "m4" in fail:
                raise urllib.error.URLError("usgs down")
            return RAW["usgs_m4"] if m4 is None else m4
        raise AssertionError(url)
    return fetch


def props(d):
    return {f["properties"]["id"]: f["properties"] for f in d["geojson"]["features"]}


def schema(d, feed):
    json.dumps(d, allow_nan=False)
    need = ("version", "fetched_at", "count", "sources", "attribution", "geojson")
    feats = d["geojson"]["features"]
    return (all(k in d for k in need) and d["version"] == hz.VERSION and d["count"] == len(feats)
            and d["geojson"]["type"] == "FeatureCollection"
            and all(set(s) == {"name", "ok", "error", "newest", "n"} for s in d["sources"])
            and all(f["geometry"]["type"] == "Point" and len(f["geometry"]["coordinates"]) == 2 for f in feats)
            and all(all(k in f["properties"] for k in LOCKEYS + ("source",)) for f in feats)
            and d["licence"] == hz.LICENCE[feed] and d["public_ok"] is hz.PUBLIC_OK[feed]
            and d["non_commercial"] is hz.NON_COMMERCIAL[feed])


# ---- module contract
check(hz.VERSION == "1.0" and set(hz.FEEDS) == {"hazards", "quakes"} and hz.FEEDS["hazards"] == (hz.gdacs, 900)
      and hz.FEEDS["quakes"] == (hz.quakes, 300), "FEEDS: hazards every 900 s, quakes every 300 s")
check(all(n.isalpha() and n.islower() for n in hz.FEEDS), "feed names are lowercase letters")
reg = open(os.path.join(PROJ, "gt", "feeds.py"), encoding="utf-8").read().split("REGISTRY = {", 1)[1].split("}", 1)[0]
check(not any('"%s":' % n in reg for n in hz.FEEDS), "no clash with gt/feeds.py REGISTRY")
check(set(hz.ATTRIBUTION) == {"gdacs", "emsc", "usgs"} and "EMSC-CSEM SeismicPortal" in hz.ATTRIBUTION["emsc"]
      and hz.PUBLIC_OK == {"hazards": True, "quakes": True} and hz.NON_COMMERCIAL == {"hazards": False, "quakes": False},
      "attribution per source; public OK, not non-commercial")

# ---- timestamp quirks
P = hz.parse_ts
check(P("2026-11-20T03:42:40.51Z") == dt.datetime(2026, 11, 20, 3, 42, 40, 510000, dt.timezone.utc),
      "EMSC time with 2 fractional digits (3.9 fromisoformat can't)")
check(P("2026-11-20T02:57:18") == dt.datetime(2026, 11, 20, 2, 57, 18, tzinfo=dt.timezone.utc), "GDACS naive time = UTC")
check(P("2026-11-20T14:05:29+09:00") == dt.datetime(2026, 11, 20, 5, 5, 29, tzinfo=dt.timezone.utc)
      and P("2026-11-19T23:00:00-0500") == dt.datetime(2026, 11, 20, 4, 0, tzinfo=dt.timezone.utc), "offsets to UTC")
check(P(1795121928280) == dt.datetime(2026, 11, 19, 20, 58, 48, 280000, dt.timezone.utc), "USGS epoch ms")
check(P("2026-11-20") == dt.datetime(2026, 11, 20, tzinfo=dt.timezone.utc) and P("") is None and P(None) is None
      and P("yesterday") is None and P("2026-13-40T00:00:00Z") is None and P("2026-11-20T03:42:40.123456789Z").microsecond == 123456,
      "date only, empty, junk, impossible date, 9 fractional digits")
check(abs(hz.km(0, 0, 0, 1) - 111.19) < 0.1 and hz.km(35.0, 31.0, 35.0, 31.0) == 0.0, "haversine km")

# ---- GDACS: a normal poll
hz.GDACS_PAGE = 4          # the fixtures stand in for 100-event pages
hz.WF_GREEN_MAX = 2
log = []
g = hz.gdacs(now=NOW, fetch=gdacs_fake(log))
mains = [q(u) for u in log if q(u)["eventlist"] != "WF"]
wfs = [q(u) for u in log if q(u)["eventlist"] == "WF"]
check(len(log) == 6 and [m["pagenumber"] for m in mains] == ["1", "2", "3"]
      and [(w["alertlevel"], w["pagenumber"]) for w in wfs] == [("Orange;Red", "1"), ("Green", "1"), ("Green", "2")],
      "3 pages (full, full, empty body); wildfires: Orange;Red (short page), Green (full page, then empty)")
check("eventlist=EQ;TC;FL;VO;DR&alertlevel=Green;Orange;Red&fromDate=2026-11-13&toDate=2026-11-21&pagenumber=1" in log[0],
      "query keeps ';' literal, fromDate = today - 7 d, toDate = tomorrow")
check(schema(g, "hazards"), "hazards schema: contract keys, Points, geo.locate fields + source on every point")
P_ = props(g)
order = [f["properties"]["id"] for f in g["geojson"]["features"]]
check(order == ["TC9000002", "WF9100001", "EQ9000001", "DR9000005", "WF9100002", "VO9000004", "FL9000003",
                "WF9100004", "EQ9000007"], "9 events: Red, Orange, Green; newest end first within a level")
check(P_["EQ9000001"]["alert"] == "Orange" and P_["EQ9000001"]["episode"] == 2
      and P_["EQ9000001"]["severity"] == "Magnitude 6.1M, Depth:10km", "two episodes of one event -> the newest (Orange)")
check("EQ9000006" not in P_ and "EQ9000007" in P_ and not P_["EQ9000007"]["current"],
      "ended 10 days ago -> dropped; ended 4 days ago -> kept")
fl = [f for f in g["geojson"]["features"] if f["properties"]["id"] == "FL9000003"][0]
dr = [f for f in g["geojson"]["features"] if f["properties"]["id"] == "DR9000005"][0]
check(fl["geometry"] == {"type": "Point", "coordinates": [33.0, 15.0]} and P_["FL9000003"]["country"] == "SDN",
      "polygon geometry -> its centre point, located in Sudan")
check(dr["geometry"]["coordinates"] == [42.0, 2.0] and P_["DR9000005"]["name"] == "Drought in Kenya, Somalia"
      and P_["DR9000005"]["gdacs_country"] == "Kenya, Somalia", "no geometry -> bbox centre; names cleaned of '  ' and ', '")
check(hz._clean("Drought in Aruba, , Brazil,  , Chile, ") == "Drought in Aruba, Brazil, Chile" and hz._clean(None) is None
      and len(hz._clean("x" * 300)) == 200, "names: empty list slots removed, None stays None, capped at 200")
tc = P_["TC9000002"]
check(tc["type_label"] == "Tropical cyclone" and tc["event_name"] == "TESTA-26" and tc["theatre"] == "other"
      and tc["sea"] == "open ocean" and tc["url"] == "https://www.gdacs.org/report.aspx?eventid=9000002&episodeid=7&eventtype=TC"
      and tc["from"] == "2026-11-15T06:00:00Z" and tc["origin"] == "JTWC", "cyclone: label, name, report URL, UTC dates, at sea")
check(P_["EQ9000001"]["country"] == "IRN" and P_["EQ9000001"]["theatre"] == "middle-east" and P_["EQ9000001"]["iso3"] == "IRN"
      and P_["EQ9000001"]["affected"] == ["IRN"], "earthquake located in Iran / middle-east")
check(g["by_type"] == {"TC": 1, "WF": 3, "EQ": 2, "DR": 1, "VO": 1, "FL": 1} and g["by_alert"] == {"Red": 1, "Orange": 2, "Green": 6},
      "counts by type and alert level")
check({k for k in P_ if k.startswith("WF")} == {"WF9100001", "WF9100004", "WF9100002"} and g["wildfires_green_dropped"] == 2,
      "wildfires: Orange kept, the 2 largest current Green kept, smaller and ended ones dropped")
check(g["sources"] == [{"name": "GDACS", "ok": True, "error": None, "newest": "2026-11-20T03:00:00Z", "n": 6},
                       {"name": "GDACS wildfires", "ok": True, "error": None, "newest": "2026-11-20T02:00:00Z", "n": 3}],
      "sources: newest = latest datemodified, n kept")
check(g["attribution"] == [hz.ATTRIBUTION["gdacs"]] and g["fetched_at"] == "2026-11-20T05:30:00Z" and not g["truncated"],
      "attribution, fetched_at, not truncated")
check(all(isinstance(f["properties"]["current"], bool) for f in g["geojson"]["features"]), "current is a bool, not 'true'")

# ---- GDACS quirks and failures
check(hz._gdacs_page(b"") == [] and hz._gdacs_page(b"  \r\n") == [], "empty body = no events (GDACS's 'nothing matches')")
check(raises(lambda: hz._gdacs_page(b'{"type": "FeatureCollection"}'), ValueError, "without features"), "JSON without features -> ValueError")
check(raises(lambda: hz._gdacs_page(b"<html>WAF</html>"), ValueError), "WAF HTML page -> ValueError")
gz = {1: gzip.compress(RAW["gdacs_p1"]), 2: gzip.compress(RAW["gdacs_p2"])}
check(hz.gdacs(now=NOW, fetch=gdacs_fake(pages=gz, wf=gzip.compress(RAW["gdacs_wf"]))) == g,
      "gzip bodies without a header are decoded (all wildfires in the Green answer: same result)")
gw = hz.gdacs(now=NOW, fetch=gdacs_fake(fail=("wf",)))
check(gw["count"] == 6 and gw["sources"][1]["ok"] is False and "HTTPError" in gw["sources"][1]["error"]
      and gw["sources"][0]["ok"], "wildfire call fails -> the other GDACS events still served, error in sources")
gm = hz.gdacs(now=NOW, fetch=gdacs_fake(fail=("main",)))
check(gm["count"] == 3 and not gm["sources"][0]["ok"] and "URLError" in gm["sources"][0]["error"], "main call fails -> wildfires only")
check(raises(lambda: hz.gdacs(now=NOW, fetch=gdacs_fake(fail=("main", "wf"))), RuntimeError, "every source failed"),
      "both GDACS calls fail -> RuntimeError (the scheduler keeps the last good data)")
hz.GDACS_MAX_PAGES, keep_max = 2, hz.GDACS_MAX_PAGES
gt_ = hz.gdacs(now=NOW, fetch=gdacs_fake(pages={1: RAW["gdacs_p1"], 2: RAW["gdacs_p1"], 3: RAW["gdacs_p1"]}))
hz.GDACS_MAX_PAGES = keep_max
check(gt_["truncated"] is True and gt_["sources"][0]["n"] == 4, "a page cap that is hit -> truncated: true")
check(hz.gdacs(now=dt.datetime(2026, 11, 20, 5, 30), fetch=gdacs_fake()) == g, "naive now is read as UTC")

# ---- size guard
big = json.loads(json.dumps(g))
big["geojson"]["features"] = big["geojson"]["features"] * 40
before = len(big["geojson"]["features"])
fit = hz._fit(big, max_bytes=60000)
check(hz._size(fit) <= 60000 and fit["count"] == len(fit["geojson"]["features"]) < before
      and fit["trimmed"] == before - fit["count"] and fit["geojson"]["features"][0]["properties"]["id"] == "TC9000002",
      "over the size cap -> lowest-priority points trimmed from the end, count and trimmed set")

# ---- quakes: a normal poll
log = []
d = hz.quakes(now=NOW, fetch=quake_fake(log))
check(len(log) == 3 and log[0] == hz.EMSC_URL, "3 calls: EMSC, USGS nuclear explosion, USGS explosion (no fallback)")
check(q(log[1]) == {"format": "geojson", "orderby": "time", "starttime": "2026-11-13T05:30:00", "eventtype": "nuclear explosion"}
      and "eventtype=nuclear%20explosion" in log[1] and q(log[2])["eventtype"] == "explosion", "USGS queries: 7 days, typed")
check(schema(d, "quakes"), "quakes schema: contract keys, Points, geo.locate fields + source on every point")
Q = props(d)
check(len(Q) == 13 and d["count"] == 13 and d["watch_count"] == 7, "13 events kept, 7 on watch")
check(Q["emsc:20261120_9000001"]["watch"] and Q["emsc:20261120_9000001"]["watch_reason"]
      == "shallow M4.6 (8 km) in a watched area: Iran", "shallow M4.6 in Iran -> watch, with the reason")
check(not Q["emsc:20261119_9000002"]["watch"] and Q["emsc:20261119_9000002"]["watch_reason"] is None
      and Q["emsc:20261119_9000002"]["depth_km"] == 80.0, "deep M5.0 in Iran -> kept, no watch")
check(Q["emsc:20261119_9000003"]["watch"] and Q["emsc:20261119_9000003"]["theatre"] == "ukraine-russia", "shallow M4.2 in Ukraine -> watch")
check(not Q["emsc:20261119_9000006"]["watch"] and Q["emsc:20261119_9000006"]["country"] == "RUS",
      "Kamchatka (Russia, east of 60 E) -> no watch")
check(not Q["emsc:20261119_9000007"]["watch"] and Q["emsc:20261119_9000007"]["country"] is None
      and Q["emsc:20261119_9000007"]["sea"] == "Gulf of Aden", "Gulf of Aden ridge, no country -> no watch")
check(not Q["emsc:20261119_9000005"]["watch"] and Q["emsc:20261119_9000005"]["country"] == "JPN", "Japan M5.5 -> kept, no watch")
check(Q["emsc:20261119_9000014"]["watch"] and Q["emsc:20261119_9000014"]["mag"] == 4.0 and Q["emsc:20261119_9000014"]["depth_km"] == 10.0,
      "boundary: M4.0 at 10.0 km in Pakistan -> watch")
check(not Q["emsc:20261119_9000015"]["watch"], "10.1 km -> not shallow")
check("emsc:20261120_9000011" not in Q, "M3.9 in Iran -> dropped")
check("emsc:20261117_9000008" not in Q, "60 h old, no watch -> dropped")
check(Q["emsc:20261116_9000009"]["watch"] and Q["emsc:20261116_9000009"]["time"] == "2026-11-16T09:45:00Z",
      "4-day-old shallow M4.5 in Syria -> kept as watch (7-day window)")
nk = Q["emsc:20261117_9000010"]
check(nk["source"] == "EMSC+USGS" and nk["kind"] == "nuclear explosion" and nk["suspected"] is True and nk["watch"]
      and nk["watch_reason"] == "suspected nuclear explosion (EMSC+USGS)" and nk["country"] == "PRK"
      and nk["usgs_url"] == "https://earthquake.usgs.gov/earthquakes/eventpage/us9000bbb1" and "usgs:us9000bbb1" not in Q,
      "EMSC 'sn' + USGS nuclear explosion 20 s / 9 km apart -> one watch point")
ix = Q["emsc:20261119_9000012"]
check(ix["source"] == "EMSC+USGS" and ix["kind"] == "explosion" and ix["mag"] == 4.1 and ix["watch"]
      and ix["watch_reason"] == "explosion in a watched area: Israel" and "usgs:us9000aaa1" not in Q,
      "EMSC 'ke' + USGS explosion 29 s / 18 km apart -> merged, typed explosion, watch")
sy = Q["usgs:us9000aaa2"]
check(sy["source"] == "USGS" and sy["kind"] == "explosion" and sy["watch"] and sy["mag"] == 2.1 and sy["country"] == "SYR",
      "USGS explosion in Syria (M2.1, no EMSC twin) -> kept as watch")
check("usgs:uw9000aaa3" not in Q and "emsc:20261119_9000013" not in Q, "explosions in Washington / Nevada -> dropped")
check(Q["emsc:20261119_9000005"]["url"] == "https://www.seismicportal.eu/eventdetails.html?unid=20261119_9000005"
      and Q["emsc:20261119_9000005"]["place"] == "Near East Coast Of Honshu, Japan" and Q["emsc:20261119_9000005"]["time"]
      == "2026-11-19T14:20:00Z" and Q["emsc:20261119_9000005"]["magtype"] == "mw", "EMSC detail URL, region title-cased, UTC time")
ids = [f["properties"]["id"] for f in d["geojson"]["features"]]
w = [f["properties"]["watch"] for f in d["geojson"]["features"]]
check(w == sorted(w, reverse=True) and ids[0] == "emsc:20261120_9000001", "watch events first, then newest first")
check(d["sources"][0] == {"name": "EMSC", "ok": True, "error": None, "newest": "2026-11-20T02:00:00Z", "n": 15}
      and d["sources"][1]["n"] == 1 and d["sources"][2]["n"] == 3, "sources: EMSC 15 parsed, USGS 1 + 3")
check(d["attribution"] == [hz.ATTRIBUTION["emsc"], hz.ATTRIBUTION["usgs"]], "EMSC and USGS credited")

# ---- the real USGS sample: quarry blasts never reach the map
dr_ = hz.quakes(now=NOW, fetch=quake_fake(expl=RAW["usgs_explosion_real"], nuke=RAW["usgs_nuke_empty"]))
R = props(dr_)
check(not any(k.startswith("usgs:") for k in R) and dr_["sources"][2]["n"] == 3 and dr_["sources"][1]["n"] == 0,
      "real 2026-11-20 sample: 3 WA/BC quarry blasts parsed, none kept; empty nuclear query fine")
check(R["emsc:20261117_9000010"]["source"] == "EMSC" and R["emsc:20261117_9000010"]["watch"]
      and R["emsc:20261119_9000012"]["kind"] == "earthquake"
      and R["emsc:20261119_9000012"]["watch_reason"] == "shallow M4.1 (2 km) in a watched area: Israel",
      "without USGS twins: EMSC 'sn' alone still on watch; the Israel event stays a (shallow, watched) earthquake")

# ---- partial failure and the EMSC fallback
log = []
fb = hz.quakes(now=NOW, fetch=quake_fake(log, fail=("emsc",)))
F = props(fb)
check(len(log) == 4 and q(log[3]) == {"format": "geojson", "orderby": "time", "starttime": "2026-11-18T05:30:00",
                                       "minmagnitude": "4.0"}, "EMSC down -> USGS M4+ for 48 h as a 4th call")
check(fb["sources"][0]["ok"] is False and "URLError" in fb["sources"][0]["error"]
      and fb["sources"][3]["name"] == "USGS M4+ (EMSC fallback)" and fb["sources"][3]["ok"], "fallback named in sources")
check(set(F) == {"usgs:us9000ccc1", "usgs:us9000ccc2", "usgs:us9000aaa1", "usgs:us9000aaa2", "usgs:us9000bbb1"}
      and F["usgs:us9000ccc1"]["watch"] and F["usgs:us9000bbb1"]["watch"] and not F["usgs:us9000ccc2"]["watch"],
      "fallback: USGS quakes + watched explosions + the nuclear event")
check(fb["attribution"] == [hz.ATTRIBUTION["usgs"]], "only USGS credited when EMSC failed")
pf = hz.quakes(now=NOW, fetch=quake_fake(fail=("nuke", "expl")))
check(pf["count"] == 12 and [s["ok"] for s in pf["sources"]] == [True, False, False], "both USGS calls fail -> EMSC still served")
check(raises(lambda: hz.quakes(now=NOW, fetch=quake_fake(fail=("emsc", "nuke", "expl", "m4"))), RuntimeError, "every source failed"),
      "every quake source fails -> RuntimeError")
bad = hz.quakes(now=NOW, fetch=quake_fake(emsc=b"<html>503</html>", m4=b'{"type":"FeatureCollection","features":[]}'))
check(not bad["sources"][0]["ok"] and "JSONDecodeError" in bad["sources"][0]["error"], "EMSC HTML error page -> source error")
check(raises(lambda: hz.emsc_events(b'{"features": 5}'), ValueError, "without features"), "EMSC JSON without a feature list -> ValueError")
check(hz.quakes(now=NOW, fetch=quake_fake(emsc=gzip.compress(RAW["emsc"]))) == d, "gzip EMSC body decoded")

# ---- merge rules
e0 = {"id": "emsc:x", "src": "EMSC", "t": NOW, "lon": 50.0, "lat": 30.0, "depth": 5.0, "mag": 4.5, "magtype": "mb",
      "place": "X", "kind": "earthquake", "suspected": False, "agency": "EMSC", "url": None}
u_far = dict(e0, id="usgs:a", src="USGS", t=NOW + dt.timedelta(seconds=61), kind="explosion")
u_wide = dict(e0, id="usgs:b", src="USGS", lon=50.6, kind="explosion")
u_near = dict(e0, id="usgs:c", src="USGS", t=NOW + dt.timedelta(seconds=59), lon=50.4, kind="explosion")
m = hz.merge([e0], [u_far, u_wide])
check(len(m) == 3 and m[0]["src"] == "EMSC", "61 s apart or 57 km apart -> not merged")
m = hz.merge([e0], [u_near, dict(u_near, id="usgs:c")])
check(len(m) == 1 and m[0]["src"] == "EMSC+USGS" and m[0]["kind"] == "explosion" and m[0]["usgs_id"] == "usgs:c",
      "59 s and 38 km -> merged once (duplicate USGS id ignored)")
m = hz.merge([e0, dict(e0, id="emsc:y", t=NOW + dt.timedelta(seconds=40))], [dict(u_near, t=NOW + dt.timedelta(seconds=35))])
check(m[1]["src"] == "EMSC+USGS" and m[0]["src"] == "EMSC", "two EMSC candidates -> the closest in time wins")
check(hz.watched_area({"lon": 55.0}, {"country": "RUS", "theatre": "ukraine-russia"})
      and not hz.watched_area({"lon": 61.0}, {"country": "RUS", "theatre": "ukraine-russia"})
      and hz.watched_area({"lon": 130.0}, {"country": "PRK", "theatre": "indo-pacific"})
      and not hz.watched_area({"lon": 49.0}, {"country": None, "theatre": "middle-east"})
      and hz.watched_area({"lon": 49.0}, {"country": "YEM", "theatre": "middle-east"})
      and not hz.watched_area({"lon": 10.0}, {"country": "DEU", "theatre": "europe-nato"}),
      "watched_area: Russia west of 60 E, watch list, middle-east land only")


# ---- default fetchers
class Resp:
    def __init__(self, body, enc):
        self.body, self.headers = body, {"Content-Encoding": enc} if enc else {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen = []


def fake_open(req, timeout=None):
    seen.append((req.full_url, req.get_header("User-agent"), req.get_header("Accept-encoding"), timeout))
    return Resp(gzip.compress(RAW["emsc"]), "gzip")


hz.urllib.request.urlopen = fake_open
check(hz._fetch(hz.EMSC_URL) == RAW["emsc"] and seen[-1] == (hz.EMSC_URL, hz.UA, "gzip", 30) and seen[-1][3] <= 30,
      "default fetch: honest UA, gzip decoded, 30 s timeout")
check(hz._fetch_gdacs(hz.GDACS_URL) == RAW["emsc"] and seen[-1][1] == hz.GDACS_UA and hz.GDACS_UA.startswith("Mozilla/5.0"),
      "GDACS fetch: Mozilla-prefixed UA")
hz.urllib.request.urlopen = no_network

print("     hazards example:", json.dumps(g["geojson"]["features"][2]["properties"], ensure_ascii=False)[:400])
print("     quakes example:", json.dumps(d["geojson"]["features"][0], ensure_ascii=False)[:400])
shutil.rmtree(TMP, ignore_errors=True)
print("%d checks passed" % ok)
