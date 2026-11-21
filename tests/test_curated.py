"""Offline tests for 0.11.0: CIR Eyes on Russia and S2 Underground Iran Kinetic Events (gt/curated.py), plus the
helpers gt/geoconfirmed.py shares (times, ids, links, text, caps, state).
Never touches the network: sockets and urlopen are blocked, every fetch is a fake. The fixtures are SYNTHETIC
(invented entries, channels and post ids) in the exact structure the two ArcGIS FeatureServers served on
2026-11-20: f=json query answers with objectIdFieldName, uniqueIdField, geometryType, spatialReference, fields,
features [{attributes, geometry {x, y}}], exceededTransferLimit on a page with more to come, date fields as epoch
ms at 00:00Z, and the HTTP-200 {"error": ...} body a bad query gets.
  curated/cir_p0.json     CIR page 1: 3 entries, exceededTransferLimit (two share one Telegram post, one private t.me/c link)
  curated/cir_p1.json     CIR page 2: an X-linked entry, one older than the window, one without a position
  curated/kinetic.json    S2 layer 3: 4 incidents (X / web+X / no link / older than the window)
  curated/error_400.json  the error body; curated/empty.json  a query with no rows

Run: python3 -I tests/test_curated.py
"""
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "curated")
TMP = tempfile.mkdtemp(prefix="gt-curated-")
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import curated as cu, mymaps  # noqa: E402

cu.urllib.request.urlopen = no_network
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


raw = {n: open(os.path.join(FX, n + ".json"), "rb").read() for n in ("cir_p0", "cir_p1", "kinetic", "error_400", "empty")}
J = {n: json.loads(b) for n, b in raw.items()}
NOW = dt.datetime(2026, 11, 20, 6, 0, tzinfo=dt.timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)
EPOCH = 1288834974657
CIR_STATE = os.path.join(TMP, "cache", "curated_cir.json")
KIN_STATE = os.path.join(TMP, "cache", "curated_kinetic.json")


def Z(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def post(s):
    return str(((Z(s) - EPOCH) << 22) + 1234567)


def sha16(s):
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def qs(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


def fake(pages=None, kinetic=None, log=None):
    """pages maps resultOffset -> bytes or an exception for the CIR layer."""
    pages = {0: raw["cir_p0"], 3: raw["cir_p1"]} if pages is None else pages

    def fetch(url):
        if log is not None:
            log.append(url)
        q = qs(url)
        if url.startswith(cu.KINETIC_URL + "?"):
            k = raw["kinetic"] if kinetic is None else kinetic
            if isinstance(k, Exception):
                raise k
            return k
        assert url.startswith(cu.CIR_URL + "?"), url
        b = pages.get(int(q["resultOffset"]))
        if b is None:
            raise AssertionError("unexpected resultOffset " + q["resultOffset"])
        if isinstance(b, Exception):
            raise b
        return b
    return fetch


def reset():
    for p in (CIR_STATE, KIN_STATE):
        if os.path.exists(p):
            os.remove(p)


def by_key(d, key):
    return {f["properties"][key]: f for f in d["geojson"]["features"]}


REQUIRED = ("id", "title", "kind", "category", "tags", "ts_ms", "ts", "ts_source", "url", "platform", "handle", "post_id",
            "country", "country_name", "sea", "theatre", "source", "source_label", "description", "link_private")


def schema_ok(d, slug):
    for f in d["geojson"]["features"]:
        p = f["properties"]
        assert f["type"] == "Feature" and f["geometry"]["type"] == "Point" and len(f["geometry"]["coordinates"]) == 2, p
        assert all(k in p for k in REQUIRED), [k for k in REQUIRED if k not in p]
        assert p["kind"] == "event" and p["source"] == slug and p["category"] in mymaps.CATEGORIES and isinstance(p["tags"], list)
        assert re.fullmatch(r"[0-9a-f]{16}", p["id"]) and p["ts"] == cu.iso(p["ts_ms"]) and p["ts"].endswith("Z")
        assert p["ts_source"] in ("x-snowflake", "date") and 0 < len(p["title"]) <= cu.TITLE_MAX and "<" not in p["title"]
        assert p["description"] is None or len(p["description"]) <= cu.DESC_MAX
    ids = [f["properties"]["id"] for f in d["geojson"]["features"]]
    ts = [f["properties"]["ts_ms"] for f in d["geojson"]["features"]]
    return len(set(ids)) == len(ids) and ts == sorted(ts, reverse=True)


# ---- fixtures have the real shape
check(J["cir_p0"].get("exceededTransferLimit") is True and "exceededTransferLimit" not in J["cir_p1"]
      and J["cir_p0"]["objectIdFieldName"] == "OBJECTID" and J["cir_p0"]["spatialReference"]["wkid"] == 4326,
      "fixture: page 1 flags more rows, page 2 does not; OBJECTID, WGS84")
check({f["name"]: f["type"] for f in J["cir_p0"]["fields"]}["TIMESTAMP"] == "esriFieldTypeDate"
      and all(f["attributes"]["TIMESTAMP"] % 86400000 == 0 for f in J["cir_p0"]["features"]),
      "fixture: TIMESTAMP is esriFieldTypeDate at 00:00Z (epoch ms)")

# ---- shared helpers
d0 = dt.date(2026, 11, 10)
check(cu.pick_time(d0, NOW) == (Z("2026-11-10T12:00"), "date") and cu.pick_time(dt.date(2026, 11, 20), NOW) == (NOW_MS, "date"),
      "no X post: the day at 12:00Z, never after now")
check(cu.pick_time(d0, NOW, [post("2026-11-10T18:00")]) == (Z("2026-11-10T18:00"), "x-snowflake")
      and cu.pick_time(d0, NOW, [post("2026-11-12T00:00"), post("2026-11-10T03:00")]) == (Z("2026-11-10T03:00"), "x-snowflake"),
      "X posts: the earliest one gives the time")
check(cu.pick_time(d0, NOW, [post("2026-11-08T00:00")])[1] == "x-snowflake" and cu.pick_time(d0, NOW, [post("2026-11-07T23:59")])[1] == "date"
      and cu.pick_time(d0, NOW, [post("2026-11-15T00:00")])[1] == "x-snowflake" and cu.pick_time(d0, NOW, [post("2026-11-15T00:01")])[1] == "date",
      "snowflake guard: 2 days before to 5 days after the day")
check(cu.pick_time(dt.date(2026, 11, 20), NOW, [post("2026-11-20T07:00")]) == (NOW_MS, "date"), "an X post 'after now' is not trusted")
check(cu.pick_time(d0, NOW, [], Z("2026-11-10T09:30")) == (Z("2026-11-10T09:30"), "name-dtg")
      and cu.pick_time(d0, NOW, [], Z("2026-11-14T09:30"))[1] == "date", "a zoned source time wins only near the day")
check(cu.find_urls("(2/2) https://x.com/a/status/1234567890123456789, https://t.me/b/5;, , More: https://e.org/p).")
      == ["https://x.com/a/status/1234567890123456789", "https://t.me/b/5", "https://e.org/p"]
      and cu.find_urls("t.me/example/12") == ["https://t.me/example/12"] and cu.find_urls("no link") == [] and cu.find_urls(None) == [],
      "find_urls: glued punctuation stripped, bare t.me links get https")
s1 = cu.source_info("https://t.me/c/1234567890/42")
s2 = cu.source_info("https://t.me/s/example_ch/77")
check(s1 == {"url": "https://t.me/c/1234567890/42", "platform": "telegram", "handle": None, "post_id": None, "link_private": True}
      and (s2["handle"], s2["post_id"], s2["link_private"]) == ("example_ch", "77", False), "source_info: private t.me/c and t.me/s preview links")
check(cu.source_info("https://x.com/h/status/123?s=20") == dict(mymaps.parse_source("https://x.com/h/status/123?s=20"), link_private=False)
      and cu.source_info(None)["url"] is None, "source_info = mymaps.parse_source for ordinary links")
long = "word " * 100
check(len(cu.clean_text(long, 300)) <= 300 and cu.clean_text(long, 300).endswith("…") and cu.clean_text("a<br>b &amp; <b>c</b>", 50) == "a b & c"
      and cu.clean_text("&lt;script&gt;x&lt;/script&gt;", 50) == "x" and cu.clean_text(None, 9) == "", "clean_text: tags, entities, length")
check(cu.first_line("<nobr>Head</nobr> line<br>second") == "Head line" and cu.first_line("<br><br>x") == "x", "first_line: the headline")
check(cu.valid_lonlat("30.5", 50.4) == (30.5, 50.4) and cu.valid_lonlat(0, 0) is None and cu.valid_lonlat(200, 1) is None
      and cu.valid_lonlat(None, 1) is None and cu.valid_lonlat(float("nan"), 1) is None, "valid_lonlat")
check(cu.err_text(urllib.error.HTTPError("u", 503, "x", {}, None)) == "HTTP 503" and cu.err_text(OSError(2, "gone", "/data/cache/x.json")) == "FileNotFoundError errno 2"
      and "/home/someone" not in cu.err_text(ValueError("bad file /home/someone/a/b.json")) and cu.err_text(urllib.error.URLError("timed out")) == "URLError: timed out",
      "err_text: short, never a local path")

# ---- CIR: a normal poll (2 pages)
reset()
log = []
d = cu.poll_cir(now=NOW, fetch=fake(log=log))
q0, q1 = qs(log[0]), qs(log[1])
check(len(log) == 2 and q0["resultOffset"] == "0" and q1["resultOffset"] == "3" and q0["resultRecordCount"] == "1000",
      "paging: 2 calls, the second at resultOffset 3, 1000 a page")
check(q0["where"] == "TIMESTAMP >= timestamp '2026-10-30 00:00:00'" and q0["orderByFields"] == "TIMESTAMP DESC,OBJECTID DESC"
      and q0["outFields"] == cu.CIR_FIELDS and q0["returnGeometry"] == "true" and q0["outSR"] == "4326" and q0["f"] == "json",
      "query: 21-day window, newest first, named fields, WGS84")
check(all(" " not in u and "'" not in u for u in log), "query strings percent-encoded")
S = d["sources"][0]
check(d["count"] == 4 and S["ok"] and S["error"] is None and S["rows"] == 6 and S["pages"] == 2 and S["n"] == 4,
      "4 entries served from 6 rows")
check(S["dropped"] == {"no_date": 0, "bad_coords": 1, "outside_window": 1, "future": 0, "cap": 0}, "dropped: one too old, one without a position")
check(d["version"] == cu.VERSION == "1.0" and d["feed"] == "cir" and d["fetched_at"] == "2026-11-20T06:00:00Z" and d["window_days"] == 21
      and S["newest"] == "2026-11-13T12:00:00Z", "envelope: version, feed, fetched_at, window, newest")
check(d["public_ok"] is False and d["non_commercial"] is True and "open access" in d["licence"]
      and d["attribution"] == [{"text": cu.ATTRIBUTION["cir"], "url": cu.ATTRIBUTION_URL["cir"], "licence": cu.LICENCE["cir"]}],
      "CIR: not public, non-commercial, attribution")
E = by_key(d, "entry")
c1, c2, c3, c4 = (E["XX9000%d" % i]["properties"] for i in (1, 2, 3, 4))
check(c1["url"] == "https://t.me/example_ua_news/31337" and c1["platform"] == "telegram" and c1["handle"] == "example_ua_news"
      and c1["post_id"] == "31337" and c1["id"] == sha16(c1["url"]), "Telegram link: url/platform/handle/post_id; id = sha1(url)")
check(c2["url"] == c1["url"] and c2["id"] == sha16("cir:XX90002"), "a second entry from the same post: id from its Entry_Number")
check(c3["link_private"] is True and c3["url"] == "https://t.me/c/1234567890/42" and c3["handle"] is None and c1["link_private"] is False,
      "private t.me/c link kept, flagged link_private")
check((c1["ts"], c1["ts_source"]) == ("2026-11-13T12:00:00Z", "date") and (c4["ts"], c4["ts_source"]) == ("2026-11-10T18:00:00Z", "x-snowflake"),
      "day-only entries at 12:00Z; an X link gives the post time")
check((c1["graphic_level"], c1["graphic"]) == ("2 - Mild", 2) and (c3["graphic_level"], c3["graphic"]) == ("4 - Severe", 4),
      "graphic content level kept (text and 1-5)")
check(c1["category"] == "strike" and c3["category"] == "casualty" and (c4["category"], c4["tags"]) == ("strike", ["strike"])
      and (c2["category"], c2["cir_category"]) == ("strike", "Civilian Infrastructure Damage"),
      "category from the title, else from CIR's Primary_category")
check(c1["title"] == "Synthetic damaged apartment block after an overnight strike." and c1["description"] is None
      and c1["place"] == "Example City" and c1["province"] == "Example Oblast" and c1["sector"] == "Civilian property" and c3["cir_secondary"] == "Bombing or explosion",
      "title = Description; place, province, sector, secondary")
check((c1["country"], c1["theatre"]) == ("UKR", "ukraine-russia") and c1["source_label"] == "CIR Eyes on Russia"
      and E["XX90001"]["geometry"]["coordinates"] == [30.5234, 50.4501], "geo.locate, label, [lon, lat]")
check(schema_ok(d, "cir"), "schema, unique ids, newest first")
kml = ("<?xml version='1.0' encoding='UTF-8'?><kml xmlns='http://www.opengis.net/kml/2.2'><Document><name>Synthetic Day 2</name>"
       "<Placemark><name>Synthetic pin</name><description>via %s</description><styleUrl>#icon-1571-0288D1</styleUrl>"
       "<Point><coordinates>30.5,50.4,0</coordinates></Point></Placemark></Document></kml>" % c1["url"]).encode()
check(mymaps.parse(kml)["features"][0]["properties"]["id"] == c1["id"], "same post on the source map -> the same id")
st = json.load(open(CIR_STATE))
check(sorted(st["rows"]) == ["XX90001", "XX90002", "XX90003", "XX90004"] and all(r["first_seen"] == NOW_MS for r in st["rows"].values())
      and not [n for n in os.listdir(os.path.join(TMP, "cache")) if n.endswith(".tmp")], "state: the 4 served entries, first-seen, written atomically")

# ---- CIR: one page failing does not fail the feed
log2 = []
pt = cu.poll_cir(now=NOW + dt.timedelta(hours=3), fetch=fake(pages={0: raw["cir_p0"], 3: urllib.error.HTTPError("u", 503, "busy", {}, None)}, log=log2))
check(len(log2) == 2 and pt["count"] == 4 and pt["sources"][0]["ok"] is False and pt["sources"][0]["error"] == "page 2: HTTP 503"
      and "XX90004" in by_key(pt, "entry") and pt["sources"][0]["pages"] == 1, "page 2 down: page 1 + the cached rest, ok=false with the page error")
check({k: f["properties"]["id"] for k, f in by_key(pt, "entry").items()} == {k: f["properties"]["id"] for k, f in E.items()}, "partial poll keeps every id")
reset()
p3 = cu.poll_cir(now=NOW, fetch=fake(pages={0: raw["cir_p0"], 3: b"<html>busy</html>"}))
check(p3["count"] == 3 and p3["sources"][0]["error"].startswith("page 2: JSONDecodeError"), "page 2 garbage, no cache: page 1 served")
check(raises(lambda: cu.poll_cir(now=NOW, fetch=fake(pages={0: urllib.error.URLError("timed out")})), urllib.error.URLError),
      "page 1 down -> raises (the scheduler keeps the last good data)")
check(raises(lambda: cu.poll_cir(now=NOW, fetch=fake(pages={0: raw["error_400"]})), RuntimeError, "query error 400"),
      "HTTP-200 error body on page 1 -> RuntimeError")
check(raises(lambda: cu.poll_cir(now=NOW, fetch=fake(pages={0: b"[]"})), ValueError, "unexpected"), "JSON that is not an object -> ValueError")
e = cu.poll_cir(now=NOW, fetch=fake(pages={0: raw["empty"]}))
check(e["count"] == 0 and e["sources"][0]["ok"] and e["geojson"] == {"type": "FeatureCollection", "features": []}, "no rows: an empty, valid feed")
loop = cu.poll_cir(now=NOW, fetch=lambda u: raw["cir_p0"])
check(loop["count"] == 3 and loop["sources"][0]["error"] == "still paging after %d pages" % cu.MAX_PAGES, "a server that never stops paging is cut off")

# ---- CIR: next polls: retraction, first-seen, a later entry from a used post
reset()
cu.poll_cir(now=NOW, fetch=fake())
p1b = json.loads(raw["cir_p1"])
p1b["features"] = [f for f in p1b["features"] if f["attributes"]["Entry_Number"] != "XX90004"]
p0b = json.loads(raw["cir_p0"])
new = json.loads(json.dumps(p0b["features"][0]))
new["attributes"].update(Entry_Number="XX90007", OBJECTID=91007, TIMESTAMP=Z("2026-11-14T00:00"), Description="Synthetic later damage report.")
p0b["features"].insert(0, new)
n2 = cu.poll_cir(now=NOW + dt.timedelta(hours=3), fetch=fake(pages={0: json.dumps(p0b).encode(), 4: json.dumps(p1b).encode()}))
E2 = by_key(n2, "entry")
check(n2["count"] == 4 and "XX90004" not in E2 and "XX90007" in E2, "a full poll is authoritative: a removed entry leaves, a new one arrives")
check(E2["XX90001"]["properties"]["id"] == c1["id"] and E2["XX90007"]["properties"]["id"] == sha16("cir:XX90007"),
      "the newer entry from the same post does not take the post's id")
st2 = json.load(open(CIR_STATE))
check(st2["rows"]["XX90001"]["first_seen"] == NOW_MS and st2["rows"]["XX90007"]["first_seen"] == NOW_MS + 3 * 3600000 and "XX90004" not in st2["rows"],
      "state: first-seen kept, new entry stamped, removed entry gone")
late = cu.poll_cir(now=NOW + dt.timedelta(days=12), fetch=fake())
check({f["properties"]["entry"] for f in late["geojson"]["features"]} == {"XX90001", "XX90002", "XX90003"}
      and late["sources"][0]["dropped"]["outside_window"] == 2, "twelve days on: entries before today - 21 d drop out client-side too")

# ---- caps
reset()
cu.MAX_BYTES = 1500
cc = cu.poll_cir(now=NOW, fetch=fake())
sz = sum(len(json.dumps(f, separators=(",", ":"), ensure_ascii=False).encode()) + 1 for f in cc["geojson"]["features"])
check(0 < cc["count"] < 4 and sz <= 1500 and cc["capped"]["dropped"] == 4 - cc["count"] and cc["sources"][0]["dropped"]["cap"] == 4 - cc["count"]
      and cc["geojson"]["features"][0]["properties"]["entry"] == "XX90001", "byte cap keeps the newest (%d of 4)" % cc["count"])
cu.MAX_BYTES, cu.MAX_FEATURES = 290000, 2
check(cu.poll_cir(now=NOW, fetch=fake())["count"] == 2, "feature cap")
cu.MAX_FEATURES = 2000
big = [{"properties": {"ts_ms": i}, "x": "y" * 500} for i in range(1000)]
kept, dropped = cu.cap_features(big)
check(len(json.dumps(kept, separators=(",", ":")).encode()) <= cu.MAX_BYTES and dropped == 1000 - len(kept) and kept[0] is big[0],
      "cap_features: 1000 x 0.5 KB -> %d kept under %d bytes" % (len(kept), cu.MAX_BYTES))

# ---- S2 Underground kinetic events
log3 = []
k = cu.poll_kinetic(now=NOW, fetch=fake(log=log3))
qk = qs(log3[0])
check(len(log3) == 1 and qk["where"] == "Date >= timestamp '2026-09-21 00:00:00'" and qk["orderByFields"] == "Date DESC,OBJECTID DESC"
      and qk["outFields"] == cu.KINETIC_FIELDS, "kinetic: one call, 60-day window")
K = by_key(k, "incident_type")
ks = k["sources"][0]
check(k["count"] == 3 and ks["ok"] and ks["dropped"]["outside_window"] == 1 and ks["newest"] == "2026-11-19T11:30:00Z", "3 incidents, one too old")
k1, k2 = K["MerchantVesselSunk"]["properties"], K["IranianBallisticMissileStrike"]["properties"]
k3 = K["AmericanAircraftDowned"]["properties"]
check((k1["ts"], k1["ts_source"]) == ("2026-11-19T11:30:00Z", "x-snowflake") and k1["platform"] == "x" and k1["handle"] == "example_s2"
      and k1["id"] == sha16(k1["url"]) and k1["category"] == "maritime", "X research link: post time, id = sha1(url), maritime")
check(k2["url"] == "https://www.example-news.com/article/1" and k2["platform"] == "web" and (k2["ts"], k2["ts_source"]) == ("2026-11-10T02:00:00Z", "x-snowflake")
      and k2["links"] == ["https://x.com/example_s2/status/%s" % post("2026-11-10T02:00")], "web link first, X in Research2: url = web, time = the X post")
check(k2["category"] == "missile" and k2["casualties"] == {"civilian_killed": 2} and k2["description"] == "Synthetic: impact reported near a base."
      and k2["report_credit"] == "Example Credit" and k2["incident_label"] == "Iranian Ballistic Missile Strike", "category from the IncidentType; casualties; credit")
check(k3["url"] is None and k3["id"] == sha16("kinetic:oid303") and (k3["ts"], k3["ts_source"]) == ("2026-11-08T12:00:00Z", "date")
      and k3["category"] == "aviation" and k3["description"] == "Synthetic note." and k3["casualties"] is None, "no link: id from OBJECTID, day at 12:00Z, Notes as description")
check(all(f["properties"]["theatre"] == "middle-east" for f in k["geojson"]["features"]) and k1["source_label"] == "S2 Underground", "theatre middle-east")
check(k["public_ok"] is True and k["non_commercial"] is True and "CC BY-NC-SA 4.0" in k["attribution"][0]["text"]
      and k["attribution"][0]["url"] == "https://creativecommons.org/licenses/by-nc-sa/4.0/" and "Changes:" in k["attribution"][0]["changes"]
      and "share-alike" in k["licence"], "S2: public with credit, licence link and changes; non-commercial, share-alike")
check(schema_ok(k, "kinetic"), "kinetic schema, unique ids, newest first")
check(raises(lambda: cu.poll_kinetic(now=NOW, fetch=fake(kinetic=urllib.error.HTTPError("u", 502, "x", {}, None))), urllib.error.HTTPError),
      "kinetic layer down -> raises")
check(os.path.exists(KIN_STATE) and json.load(open(KIN_STATE))["feed"] == "kinetic", "kinetic state in <GT_DATA>/cache/curated_kinetic.json")
for out in (d, k):
    json.dumps(out, allow_nan=False)
check(len(json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode()) < 300000, "outputs are plain JSON, small")

# ---- module constants and FEEDS
check(cu.FEEDS == {"cir": (cu.poll_cir, 10800), "kinetic": (cu.poll_kinetic, 10800)}, "FEEDS: cir and kinetic every 10800 s")
reg = dict(re.findall(r'^\s+"([a-z]+)": \(([\w.]+),', open(os.path.join(PROJ, "gt", "feeds.py")).read(), re.M))
check(all(re.fullmatch(r"[a-z]+", n) and (n not in reg or reg[n].startswith("curated.")) for n in cu.FEEDS),
      "feed names lowercase letters, no clash with feeds.REGISTRY")
check(set(cu.PUBLIC_OK) == set(cu.NON_COMMERCIAL) == set(cu.LICENCE) == set(cu.ATTRIBUTION) == set(cu.ATTRIBUTION_URL) == set(cu.FEEDS),
      "PUBLIC_OK, NON_COMMERCIAL, LICENCE, ATTRIBUTION(_URL) per feed")
check(cu.CACHE == os.path.join(TMP, "cache") and cu.state_path("x").startswith(TMP + os.sep), "state lives under GT_DATA")


# ---- default fetch
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
    return Resp(gzip.compress(raw["kinetic"]), "gzip")


cu.urllib.request.urlopen = fake_open
check(cu.fetch_url(cu.KINETIC_URL + "?f=json") == raw["kinetic"] and seen == {"ua": cu.UA, "ae": "gzip", "timeout": 30}
      and cu.fetch_url(cu.CIR_URL, timeout=99) and seen["timeout"] == 30, "default fetch: UA, gzip decoded, timeout capped at 30 s")
cu.urllib.request.urlopen = lambda req, timeout=None: Resp(raw["empty"], None)
check(cu.fetch_url(cu.CIR_URL) == raw["empty"], "default fetch: plain body passed through")
cu.urllib.request.urlopen = no_network

print("     cir example:", json.dumps(E["XX90003"], ensure_ascii=False)[:700])
print("     kinetic example:", json.dumps(K["IranianBallisticMissileStrike"], ensure_ascii=False)[:700])
shutil.rmtree(TMP, ignore_errors=True)
print("%d checks passed" % ok)
