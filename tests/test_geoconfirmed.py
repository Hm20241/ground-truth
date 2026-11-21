"""Offline tests for 0.11.0: GeoConfirmed volunteer geolocations (gt/geoconfirmed.py).
Never touches the network: sockets and urlopen are blocked, every fetch is a fake. The fixtures are SYNTHETIC
(invented placemarks, handles and post ids) in the exact structure the export served on 2026-11-20: UTF-8 with a
BOM, semicolon-separated, LF, "" escapes, the 16 real columns, Source as a comma list with the URLs glued to the
commas, Description with <br>/<nobr>/<a> and entities, undated static placemarks mixed in.
  geoconfirmed/export.csv        18 rows: 3 undated, 15 dated (one too old, one without latitude, one repeated Id)
  geoconfirmed/export_later.csv  the next poll: one placemark retracted, two new (one from an already-used post)
  geoconfirmed/conflicts.json    /api/Conflict shape, 11 conflicts (one private)

Run: python3 -I tests/test_geoconfirmed.py
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
FX = os.path.join(HERE, "fixtures", "geoconfirmed")
TMP = tempfile.mkdtemp(prefix="gt-geoconfirmed-")
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import curated as cu, geoconfirmed as gc, mymaps  # noqa: E402

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


RAW = open(os.path.join(FX, "export.csv"), "rb").read()
LATER = open(os.path.join(FX, "export_later.csv"), "rb").read()
CONF = open(os.path.join(FX, "conflicts.json"), "rb").read()
NOW = dt.datetime(2026, 11, 20, 6, 0, tzinfo=dt.timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)
EPOCH = 1288834974657
STATE = os.path.join(TMP, "cache", gc.STATE_FILE)
CSTATE = os.path.join(TMP, "cache", gc.CONFLICT_FILE)


def uid(n):
    return "0000%04x-5eed-4a11-8b00-%012x" % (n, 0xfeed0000 + n)


def post(s):
    """the synthetic X post id whose snowflake time is s (YYYY-MM-DDTHH:MM, UTC)"""
    ms = int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    return str(((ms - EPOCH) << 22) + 1234567)


def sha16(s):
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def fake(csv_body=None, conf=None, csv_fail=None, conf_fail=None, log=None):
    def fetch(url):
        if log is not None:
            log.append(url)
        if url.startswith(gc.EXPORT_URL + "?"):
            if csv_fail:
                raise csv_fail
            return RAW if csv_body is None else csv_body
        if url == gc.CONFLICT_URL:
            if conf_fail:
                raise conf_fail
            return CONF if conf is None else conf
        raise AssertionError("unexpected URL " + url)
    return fetch


def reset():
    for p in (STATE, CSTATE):
        if os.path.exists(p):
            os.remove(p)


def by_gc(d):
    return {f["properties"]["gc_id"]: f for f in d["geojson"]["features"]}


REQUIRED = ("id", "title", "kind", "category", "tags", "ts_ms", "ts", "ts_source", "url", "platform", "handle",
            "post_id", "country", "country_name", "sea", "theatre", "source", "source_label", "description",
            "conflict", "conflict_short", "faction", "origin", "equipment", "geo_url", "links", "gc_id", "link_private")

# ---- the fixture really has the export's quirks
check(RAW[:3] == b"\xef\xbb\xbf" and RAW[3:].startswith(b"Conflict;Date;Name;Faction;Origin;Latitude;Longitude;PlusCode;"
                                                         b"Description;Source;Geolocation;Equipment;EquipmentItems;Units;OrbatUnits;Id\n"),
      "fixture: UTF-8 BOM, then the real 16-column semicolon header, LF")
check(b'""quoted""' in RAW and b"; crew evacuated" in RAW and b"\r\n" not in RAW, "fixture: \"\" escapes, a quoted ';', no CR")

# ---- CSV parsing
rows = gc.parse_csv(RAW)
check(len(rows) == 18 and set(rows[0]) == set(gc.COLUMNS) and rows[0]["Conflict"] == "Iran", "18 rows, BOM stripped from the first key")
check(rows[1]["Description"] == 'Synthetic pier with a "quoted" name' and rows[0]["Description"] == "Synthetic reference site; radar dome, static",
      "quoted fields: \"\" unescaped, ';' kept inside quotes")
check(sum(1 for r in rows if not r["Date"]) == 3, "3 undated static placemarks in the export")
check(gc.parse_csv(RAW.replace(b"\n", b"\r\n")) == rows, "CRLF line ends parse the same")
check(gc.parse_csv(b"sep=;\n" + RAW) == rows and gc.parse_csv(RAW.decode("utf-8-sig")) == rows, "a sep= line and str input parse the same")
check(raises(lambda: gc.parse_csv(b"<html><body>Service Unavailable</body></html>"), ValueError, "Date/Latitude/Longitude"),
      "an HTML error page -> ValueError")
check(raises(lambda: gc.parse_csv(b""), ValueError, "empty"), "an empty body -> ValueError")
check(gc._num("48,015883") == "48.015883" and gc._num("48.5") == "48.5" and gc._num("") == "", "decimal comma tolerated")

# ---- times: DTG in Name
Z = lambda s: int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
check(gc.parse_dtg("171430Z NOV 26") == Z("2026-11-17T14:30") and gc.parse_dtg("171430ZNOV2026") == Z("2026-11-17T14:30"),
      "military DTG 171430Z NOV 26 (and run together)")
check(gc.parse_dtg("171430C NOV 26") == Z("2026-11-17T11:30") and gc.parse_dtg("170930R NOV 26") == Z("2026-11-17T14:30"),
      "DTG zone letters: C = UTC+3, R = UTC-5")
check(gc.parse_dtg("17 NOV 2026 14:30 UTC") == Z("2026-11-17T14:30") and gc.parse_dtg("17 Nov 2026 - 1430Z") == Z("2026-11-17T14:30")
      and gc.parse_dtg("14 NOV 2026 - 0915 UTC-4") == Z("2026-11-14T13:15") and gc.parse_dtg("17NOV2026 14.30 GMT+3") == Z("2026-11-17T11:30"),
      "day + time with Z/UTC/GMT and an offset")
check(all(gc.parse_dtg(s) is None for s in ("17 NOV 2026", "", None, "17 NOV 2026 14:30", "171430 NOV 26", "321430Z NOV 26",
                                            "17 NOV 2026 25:61 UTC", "171430J NOV 26", "Example Reference Placemark")),
      "day-only, unzoned or impossible names give no time")

# ---- a normal poll
reset()
log = []
d = gc.poll(now=NOW, fetch=fake(log=log))
q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(log[0]).query).items()}
check(len(log) == 2 and log[1] == gc.CONFLICT_URL, "2 requests: the export, then the conflict list")
check(q == {"start": "2026-11-06T00:00:00Z", "end": "2026-11-21T00:00:00Z"} and "T00:00:00Z" in log[0],
      "export window = today - 14 d .. tomorrow, colons left readable")
S = d["sources"][0]
check(d["count"] == 12 and len(d["geojson"]["features"]) == 12 and S["n"] == 12 and S["rows"] == 18 and S["ok"] and S["error"] is None,
      "12 events served from 18 rows")
check(S["dropped"] == {"undated": 3, "bad_date": 0, "outside_window": 1, "future": 0, "duplicate_id": 1, "bad_coords": 1, "cap": 0},
      "dropped: 3 undated, 1 before the window, 1 repeated Id, 1 without a position")
check(d["sources"][1] == {"name": "GeoConfirmed conflict list", "ok": True, "error": None, "newest": None, "n": 10, "cached": False},
      "conflict list: 10 public conflicts (the private one skipped)")
check(d["version"] == gc.VERSION == "1.0" and d["feed"] == "geoconfirmed" and d["fetched_at"] == "2026-11-20T06:00:00Z"
      and d["window_days"] == 14, "version, feed, fetched_at (UTC Z), window")
check(d["public_ok"] is False and d["non_commercial"] is True and d["licence"] == gc.LICENCE and "freely available" in gc.LICENCE
      and d["attribution"] == [{"text": gc.ATTRIBUTION, "url": "https://geoconfirmed.org", "licence": gc.LICENCE}],
      "PUBLIC_OK False, NON_COMMERCIAL True, attribution list")
G = by_gc(d)
check(uid(12) not in G and uid(13) not in G and all(not r["Date"] or r["Id"] in G or r["Id"] in (uid(12), uid(13)) for r in rows),
      "every dated in-window row with a position is served")
check(S["newest"] == "2026-11-20T06:00:00Z", "newest = today's date-only pin, clamped to now")

d1, d2, d3, d4, d5, d6 = (G[uid(n)]["properties"] for n in (4, 5, 6, 7, 8, 9))
d7, d8, d12, d13, d15, d16 = (G[uid(n)]["properties"] for n in (10, 11, 14, 15, 16, 17))
check((d1["ts"], d1["ts_source"]) == ("2026-11-19T14:05:00Z", "x-snowflake") and d1["ts_ms"] == Z("2026-11-19T14:05"),
      "X post first: exact snowflake time")
check((d5["ts"], d5["ts_source"]) == ("2026-11-16T20:10:00Z", "x-snowflake") and d5["platform"] == "telegram",
      "Telegram first, X second: the X post still gives the time; url stays the first link")
check((d4["ts"], d4["ts_source"]) == ("2026-11-17T14:30:00Z", "name-dtg") and (d7["ts"], d7["ts_source"]) == ("2026-11-14T13:15:00Z", "name-dtg"),
      "a zoned DTG in Name wins over the X post (UTC-4 converted)")
check((d6["ts"], d6["ts_source"]) == ("2026-11-15T12:00:00Z", "date") and (d8["ts"], d8["ts_source"]) == ("2026-11-13T12:00:00Z", "date"),
      "no X post, or one weeks off the Date -> the Date at 12:00Z")
check((d12["ts"], d12["ts_source"]) == ("2026-11-20T06:00:00Z", "date"), "today's date-only pin is never after now")
check((d16["ts"], d16["ts_source"]) == ("2026-11-07T22:00:00Z", "x-snowflake"), "an X post the evening before the Date is used")
check((d13["ts"], d15["ts"]) == ("2026-11-19T07:15:00Z", "2026-11-11T21:45:00Z"), "trailing comma and twitter.com spellings still give the time")
check(all(p["ts"] == cu.iso(p["ts_ms"]) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", p["ts"]) for p in (f["properties"] for f in d["geojson"]["features"])),
      "ts = ISO Z of ts_ms everywhere")

# ---- source links, ids, the mymaps rule
u1 = "https://x.com/example_geo/status/%s" % post("2026-11-19T14:05")
check(d1["url"] == u1 and d1["platform"] == "x" and d1["handle"] == "example_geo" and d1["post_id"] == post("2026-11-19T14:05"),
      "url without ?s=20 or the glued comma; platform/handle/post_id from parse_source")
check(d1["id"] == sha16(u1) and d1["links"] == ["https://t.me/example_channel/4242", "https://news.example.com/story-1"]
      and d1["geo_url"] == "https://x.com/example_geoloc/status/%s" % post("2026-11-19T20:00"), "id = sha1(url)[:16]; other links and the geolocation link kept")
kml = ("<?xml version='1.0' encoding='UTF-8'?><kml xmlns='http://www.opengis.net/kml/2.2'><Document><name>Synthetic map Day 1</name>"
       "<Placemark><name>Synthetic pin</name><description>Seen: %s?s=20 more</description><styleUrl>#icon-1504-0288D1</styleUrl><Point><coordinates>37.8,48.0,0</coordinates>"
       "</Point></Placemark><Placemark><name>Synthetic pin 2</name><description>https://t.me/example_il/778</description><styleUrl>#icon-1504-0288D1</styleUrl>"
       "<Point><coordinates>34.78,32.08,0</coordinates></Point></Placemark></Document></kml>" % u1).encode()
mm = {f["properties"]["url"]: f["properties"]["id"] for f in mymaps.parse(kml)["features"]}
check(mm[u1] == d1["id"] and mm["https://t.me/example_il/778"] == d5["id"], "same post on the source map -> the same id (X and Telegram)")
check(d13["url"] == "https://x.com/example_ye/status/%s" % post("2026-11-19T07:15") and d15["url"].startswith("https://twitter.com/example_ir/status/")
      and d15["platform"] == "x", "trailing comma stripped; twitter.com kept as written (mymaps hashes it as written)")
check(d2["url"] == d3["url"] and d2["id"] == sha16(d2["url"]) and d3["id"] == sha16("geoconfirmed:" + uid(6)),
      "two placemarks from one post: the first keeps the post's id, the other gets sha1('geoconfirmed:<Id>')")
check(d12["url"] is None and d12["platform"] is None and d12["id"] == sha16("geoconfirmed:" + uid(14)), "no URL -> sha1('geoconfirmed:<Id>')")
check(d6["platform"] == "web" and d6["url"] == "https://www.facebook.com/example.page/posts/123456", "a web link is the url, platform web")
ids = [f["properties"]["id"] for f in d["geojson"]["features"]]
check(len(set(ids)) == len(ids) and all(re.fullmatch(r"[0-9a-f]{16}", i) for i in ids), "ids unique, 16 hex")

# ---- text, conflicts, geography
check(d1["title"] == "Synthetic drone strike on a depot near the rail line"
      and d1["description"] == "Synthetic drone strike on a depot near the rail line Second line with & entity, no-break and a link",
      "title = first line; description: tags stripped, entities decoded")
check(d2["description"] is None and d13["title"] == "Synthetic tanker fire at sea; crew evacuated", "description None when it equals the title")
check((d1["category"], d1["tags"]) == mymaps.classify(d1["title"], None) and d13["category"] == "maritime" and d15["category"] == "missile",
      "category + tags from mymaps.classify(title, None)")
check((d1["conflict"], d1["conflict_short"]) == ("Ukraine", "Ukraine") and d4["conflict"] == "Israel/Gaza/Lebanon" and d6["conflict"] == "Africa"
      and d8["conflict"] == "Pacific" and d12["conflict"] == "Cartel Map" and d16["conflict"] == "Afghanistan & Pakistan",
      "conflict = the list's full name for the export's short name")
check(d["conflicts"]["Taiwan"] == {"name": "Pacific", "url": "https://geoconfirmed.org/pac"} and set(d["conflicts"]) ==
      {"Ukraine", "Israel", "Sahel", "VEN", "Taiwan", "Cartel", "Yemen", "Iran", "Afgh"}, "envelope: conflict pages for the served pins")
check(d1["faction"] == "Russia" and d1["origin"] == "VID" and d1["equipment"] == "(reported)" and d13["equipment"] == "IRIS Example (synthetic corvette)",
      "faction, origin, equipment")
check((d1["country"], d1["theatre"]) == ("UKR", "ukraine-russia") and (d6["country"], d6["theatre"]) == ("MLI", "africa")
      and (d15["country"], d15["theatre"]) == ("IRN", "middle-east") and d12["theatre"] == "americas", "geo.locate: country and theatre")
check(d13["sea"] == "Red Sea" and d13["theatre"] == "middle-east", "a pin at sea gets the sea area")
check(d1["source"] == "geoconfirmed" and d1["source_label"] == "GeoConfirmed" and d1["kind"] == "event" and d1["link_private"] is False,
      "source slug, label, kind")
check(G[uid(4)]["geometry"] == {"type": "Point", "coordinates": [37.80285, 48.01588]}, "Point, [lon, lat] rounded to 5 decimals")

# ---- schema for every feature
for f in d["geojson"]["features"]:
    p = f["properties"]
    assert f["type"] == "Feature" and f["geometry"]["type"] == "Point" and len(f["geometry"]["coordinates"]) == 2, p["id"]
    assert all(k in p for k in REQUIRED), [k for k in REQUIRED if k not in p]
    assert p["kind"] == "event" and p["category"] in mymaps.CATEGORIES and isinstance(p["tags"], list), p["id"]
    assert p["ts_source"] in ("x-snowflake", "name-dtg", "date") and p["theatre"] in ("ukraine-russia", "middle-east", "africa", "americas",
                                                                                        "indo-pacific", "south-asia", "europe-nato", "other")
    assert 0 < len(p["title"]) <= cu.TITLE_MAX and "<" not in p["title"], p["title"]
    assert p["description"] is None or (len(p["description"]) <= cu.DESC_MAX and "<" not in p["description"]), p["id"]
check(True, "schema: every feature has the curated-event properties, title <= 140, description <= 300, no tags")
order = [f["properties"]["ts_ms"] for f in d["geojson"]["features"]]
check(order == sorted(order, reverse=True), "features newest first")
blob = json.dumps(d, allow_nan=False, separators=(",", ":"), ensure_ascii=False)
check(len(blob.encode()) < 300000 and json.loads(blob)["count"] == 12, "JSON-serialisable (no NaN), %d bytes" % len(blob.encode()))

# ---- state in GT_DATA, atomic
st = json.load(open(STATE))
check(cu.CACHE == os.path.join(TMP, "cache") and os.path.exists(STATE) and os.path.exists(CSTATE)
      and not [n for n in os.listdir(cu.CACHE) if n.endswith(".tmp")], "state in <GT_DATA>/cache, no .tmp left")
check(set(st["rows"]) == set(G) and all(v["first_seen"] == NOW_MS for v in st["rows"].values()), "state: served Ids with their first-seen time")
check(cu.state_path(gc.STATE_FILE).startswith(TMP + os.sep) and cu.state_path(gc.CONFLICT_FILE).startswith(TMP + os.sep)
      and not cu.CACHE.startswith(PROJ + os.sep), "state paths come from GT_DATA, never the repo")

# ---- the next poll: dedupe by Id, retraction, a new pin from a known post, cached conflicts
log2 = []
L = gc.poll(now=NOW + dt.timedelta(hours=1), fetch=fake(csv_body=LATER, log=log2))
G2 = by_gc(L)
check(len(log2) == 1, "an hour later: the export only (conflict list cached for a day)")
check(L["count"] == 13 and uid(8) not in G2 and uid(18) in G2 and uid(19) in G2, "a retracted placemark leaves, two new ones arrive (12 - 1 + 2)")
check(all(G2[k]["properties"]["id"] == G[k]["properties"]["id"] for k in G if k in G2), "ids of the placemarks seen before do not change")
check(G2[uid(19)]["properties"]["url"] == d2["url"] and G2[uid(19)]["properties"]["id"] == sha16("geoconfirmed:" + uid(19))
      and G2[uid(5)]["properties"]["id"] == d2["id"], "a later placemark from a used post never takes the post's id")
check(G2[uid(18)]["properties"]["ts"] == "2026-11-20T05:20:00Z", "the new pin's time from its X post")
st2 = json.load(open(STATE))
check(st2["rows"][uid(4)]["first_seen"] == NOW_MS and st2["rows"][uid(18)]["first_seen"] == NOW_MS + 3600000 and uid(8) not in st2["rows"],
      "state: first-seen kept, the new Id stamped, the retracted Id gone")
lines = LATER.split(b"\n")
i5 = next(i for i, x in enumerate(lines) if uid(5).encode() in x)
i6 = next(i for i, x in enumerate(lines) if uid(6).encode() in x)
lines[i5], lines[i6] = lines[i6], lines[i5]
L2 = gc.poll(now=NOW + dt.timedelta(hours=2), fetch=fake(csv_body=b"\n".join(lines)))
check({k: f["properties"]["id"] for k, f in by_gc(L2).items()} == {k: f["properties"]["id"] for k, f in G2.items()},
      "row order in the export does not change any id")

# ---- an export with no dated rows at all is a glitch: serve the cache
head, *body = RAW.split(b"\n")
undated_only = b"\n".join([head] + [x for x in body if x and x.split(b";")[1] == b""]) + b"\n"
check(sum(1 for r in gc.parse_csv(undated_only) if r["Date"]) == 0, "(glitch fixture: header + 3 undated rows)")
gl = gc.poll(now=NOW + dt.timedelta(hours=3), fetch=fake(csv_body=undated_only))
check(gl["count"] == 13 and gl["sources"][0]["ok"] is False and "no dated rows" in gl["sources"][0]["error"]
      and {k: f["properties"]["id"] for k, f in by_gc(gl).items()} == {k: f["properties"]["id"] for k, f in G2.items()},
      "no dated rows while the cache holds 13: cached pins served, source ok=false")
reset()
e0 = gc.poll(now=NOW, fetch=fake(csv_body=undated_only))
check(e0["count"] == 0 and e0["sources"][0]["ok"] is True and e0["geojson"]["features"] == [], "no dated rows and no cache: an empty, valid feed")

# ---- the window moves
reset()
late = gc.poll(now=NOW + dt.timedelta(days=8), fetch=fake())
check({f["properties"]["gc_id"] for f in late["geojson"]["features"]} == {uid(n) for n in (4, 5, 6, 7, 8, 9, 10, 14, 15)}
      and late["sources"][0]["dropped"]["outside_window"] == 5, "eight days on: pins dated before today - 14 d drop out")
early = gc.poll(now=dt.datetime(2026, 11, 18, 6, 0, tzinfo=dt.timezone.utc), fetch=fake())
check(early["sources"][0]["dropped"]["future"] == 1 and uid(14) not in by_gc(early), "a Date after tomorrow is dropped as future")

# ---- conflict list: cache, refresh, failures never fail the feed
reset()
gc.poll(now=NOW, fetch=fake())
log3 = []
gc.poll(now=NOW + dt.timedelta(hours=25), fetch=fake(log=log3))
check(log3[-1] == gc.CONFLICT_URL, "conflict list refreshed after a day")
myst = RAW.replace(b"\nAfgh;", b"\nMystery;")
log4 = []
gc.poll(now=NOW + dt.timedelta(hours=26), fetch=fake(csv_body=myst, log=log4))
log5 = []
gc.poll(now=NOW + dt.timedelta(hours=32), fetch=fake(csv_body=myst, log=log5))
check(len(log4) == 1 and log5[-1] == gc.CONFLICT_URL, "an unknown conflict refreshes the list only once it is 6 h old")
reset()
gc.poll(now=NOW, fetch=fake())
f1 = gc.poll(now=NOW + dt.timedelta(hours=25), fetch=fake(conf_fail=OSError(13, "Permission denied", "/secret/path/x.json")))
c1 = f1["sources"][1]
check(f1["count"] == 12 and c1["ok"] is False and c1["cached"] is True and "/secret" not in json.dumps(f1)
      and by_gc(f1)[uid(7)]["properties"]["conflict"] == "Israel/Gaza/Lebanon", "conflict list down: cached names used, error has no path")
reset()
f2 = gc.poll(now=NOW, fetch=fake(conf_fail=urllib.error.HTTPError(gc.CONFLICT_URL, 500, "err", {}, None)))
check(f2["count"] == 12 and f2["sources"][1]["ok"] is False and f2["sources"][1]["error"] == "HTTP 500"
      and by_gc(f2)[uid(7)]["properties"]["conflict"] == "Israel" and f2["conflicts"]["Israel"] == {"name": "Israel", "url": None},
      "conflict list down, no cache: short names")
reset()
f3 = gc.poll(now=NOW, fetch=fake(conf=b'{"not": "a list"}'))
check(f3["sources"][1]["ok"] is False and "not a list" in f3["sources"][1]["error"], "a malformed conflict list is an error, not a crash")

# ---- the export failing fails the feed (the scheduler keeps the last good data)
check(raises(lambda: gc.poll(now=NOW, fetch=fake(csv_fail=urllib.error.HTTPError(gc.EXPORT_URL, 503, "busy", {}, None))), urllib.error.HTTPError),
      "export HTTP error -> raises")
log6 = []
check(raises(lambda: gc.poll(now=NOW, fetch=fake(csv_body=b"<html>busy</html>", log=log6)), ValueError) and len(log6) == 1,
      "export not a CSV -> ValueError, and the conflict list is not asked for")

# ---- no Id column: a stable hash of Conflict+Name+Lat+Lon
def drop_last_col(b):
    return b"\n".join(x.rsplit(b";", 1)[0] if x else x for x in b.split(b"\n"))


reset()
noid = drop_last_col(RAW)
n1 = gc.poll(now=NOW, fetch=fake(csv_body=noid))
n2 = gc.poll(now=NOW + dt.timedelta(hours=1), fetch=fake(csv_body=noid))
i1 = sorted(f["properties"]["id"] for f in n1["geojson"]["features"])
r12 = [r for r in gc.parse_csv(noid) if r["Name"] == "20 NOV 2026"][0]
h12 = "h" + sha16("|".join((r12["Conflict"], r12["Name"], r12["Latitude"], r12["Longitude"])))
check(n1["count"] == 12 and i1 == sorted(f["properties"]["id"] for f in n2["geojson"]["features"]) and n1["sources"][0]["dropped"]["duplicate_id"] == 1,
      "no Id column: 12 events, the repeat still caught, ids stable across polls")
check(sha16(u1) in i1 and sha16("geoconfirmed:" + h12) in i1, "no Id column: URL ids unchanged, the URL-less pin hashed from its fields")

# ---- caps
reset()
cu.MAX_BYTES = 3000
c = gc.poll(now=NOW, fetch=fake())
sz = sum(len(json.dumps(f, separators=(",", ":"), ensure_ascii=False).encode()) + 1 for f in c["geojson"]["features"])
newest = [f["properties"]["id"] for f in d["geojson"]["features"]][:c["count"]]
check(0 < c["count"] < 12 and sz <= 3000 and c["capped"]["dropped"] == 12 - c["count"] == c["sources"][0]["dropped"]["cap"]
      and [f["properties"]["id"] for f in c["geojson"]["features"]] == newest and c["capped"]["max_bytes"] == 3000,
      "byte cap: the newest %d kept, the oldest dropped and counted" % c["count"])
cu.MAX_BYTES, cu.MAX_FEATURES = 290000, 5
c5 = gc.poll(now=NOW, fetch=fake())
check(c5["count"] == 5 and c5["capped"]["dropped"] == 7, "feature cap: 5 kept")
cu.MAX_FEATURES = 2000
check(gc.FEEDS == {"geoconfirmed": (gc.poll, 3600)}, "FEEDS: geoconfirmed every 3600 s")
reg = dict(re.findall(r'^\s+"([a-z]+)": \(([\w.]+),', open(os.path.join(PROJ, "gt", "feeds.py")).read(), re.M))
check(all(re.fullmatch(r"[a-z]+", n) and (n not in reg or reg[n].startswith("geoconfirmed.")) for n in gc.FEEDS),
      "feed name lowercase letters, no clash with feeds.REGISTRY")

# ---- the default fetch: honest UA, gzip, timeout <= 30 s
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
    seen.update(url=req.full_url, ua=req.get_header("User-agent"), ae=req.get_header("Accept-encoding"), timeout=timeout)
    return Resp(gzip.compress(RAW), "gzip")


cu.urllib.request.urlopen = fake_open
check(gc._fetch(gc.EXPORT_URL + "?start=x") == RAW and seen["ua"] == "GroundTruth/0.11 (personal non-commercial OSINT dashboard)"
      and seen["ae"] == "gzip" and seen["timeout"] <= 30 and "@" not in seen["ua"], "default fetch: descriptive UA without contact details, gzip, <= 30 s")
cu.urllib.request.urlopen = no_network

ex = {k: v for k, v in d1.items()}
print("     example feature:", json.dumps({"type": "Feature", "geometry": G[uid(4)]["geometry"], "properties": ex}, ensure_ascii=False)[:900])
shutil.rmtree(TMP, ignore_errors=True)
print("%d checks passed" % ok)
