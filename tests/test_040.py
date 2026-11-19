"""Offline tests for the 0.4.0 sources (gt/feeds.py, gt/ais.py, gt/geo.py, server.py summaries).
Never touches the network: every fetch is stubbed with saved responses from 2026-11-16.

Run: python3 -I tests/test_040.py
"""
import datetime as dt
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures")
os.environ["GT_DATA"] = tempfile.mkdtemp()
os.environ["GT_SEED"] = os.path.join(os.environ["GT_DATA"], "no-seed")
sys.path.insert(0, PROJ)
from gt import ais, feeds, geo  # noqa: E402

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


feeds.get = no_network

# ---- geo name / code lookup
check(geo.a3s_for_name("Israel, the West Bank and Gaza") == ["ISR", "PSX"], "advisory name with several places")
check(geo.a3s_for_name("Burma (Myanmar)") == ["MMR"] and geo.a3s_for_name("Côte d’Ivoire") == ["CIV"], "aliases and curly apostrophe")
check(geo.a3s_for_name("Niger") == ["NER"] and geo.a3s_for_name("Mexico Travel Advisory") == ["MEX"], "Niger is not Nigeria; suffix dropped")
check(geo.a3_for_a2("UA") == "UKR" and geo.a3_for_a2("NO") == "NOR" and geo.a3_for_a2("PS") == "PSX", "ISO2 lookup incl. -99 codes")

# ---- travel advisories
xml = open(os.path.join(FX, "state_advisories.xml"), "rb").read()
feeds.get = lambda url, **k: xml
try:
    feeds.advisories()
    check(False, "a 6-item feed is refused")
except ValueError:
    check(True, "a feed with under 100 advisories is refused (format change guard)")
big = xml.replace(b"</channel>", b"".join(
    b"<item><title>Land%d - Level 1: Exercise Normal Precautions</title><pubDate>Fri, 23 Oct 2026</pubDate>"
    b"<link>https://example.invalid/%d</link></item>" % (i, i) for i in range(120)) + b"</channel>")
feeds.get = lambda url, **k: big
a = feeds.advisories()
iran = next(i for i in a["items"] if i["country"] == "Iran")
check(iran["level"] == 4 and iran["date"] == "2026-10-23" and iran["label"] == "Do Not Travel", "Iran parsed: level 4, date, label")
check(a["items"][0]["level"] == 4 and a["changes"] == [], "sorted by level; first run has no changes")
feeds.get = lambda url, **k: big.replace(b"Iran - Level 4: Do Not Travel", b"Iran - Level 3: Reconsider Travel")
a2 = feeds.advisories()
check(len(a2["changes"]) == 1 and a2["changes"][0]["country"] == "Iran" and a2["changes"][0]["from"] == 4
      and a2["changes"][0]["to"] == 3, "a level change is recorded")
check(feeds._iso("Fri, 23 Oct 2026") == "2026-10-23T00:00:00Z", "date-only RSS pubDate parses")

# ---- IODA outages
io = json.load(open(os.path.join(FX, "ioda_sample.json")))
now = max(x["start"] + x["duration"] for x in io["country"] + io["region"]) + 600


def fake_get_json(url, **k):
    if "/entities/query" in url:
        return {"data": io["ua_regions"] if "country/UA" in url else []}
    if "entityType=country" in url:
        return {"data": io["country"]}
    if "entityType=region" in url:
        return {"data": io["region"]}
    raise AssertionError(url)


feeds.get_json = fake_get_json
real_time = feeds.time.time
feeds.time.time = lambda: now
o = feeds.outages(hours=24 * 8)
feeds.time.time = real_time
codes = [c["code"] for c in o["countries"]]
check(set(codes) <= {"IL", "IR", "CN", "FI", "UA"} and codes, "countries aggregated by code")
check(all(c["watched"] == (c["code"] in feeds.WATCH_A2) for c in o["countries"]), "watched flag")
check([c["watched"] for c in o["countries"]] == sorted((c["watched"] for c in o["countries"]), reverse=True), "watched countries first")
check(o["regions"] and all(r["country"] == "UA" for r in o["regions"]), "only regions of watched countries kept (others dropped)")
check(all(len(c["events"]) <= 6 for c in o["countries"]), "events capped per country")

# ---- official filter + War Dept present
check(feeds.OFFICIAL_SKIP.match("Regulation: Notice of proposed amendments") and not feeds.OFFICIAL_SKIP.match("Royal Navy returns"),
      "UK MoD regulatory notices filtered")
check(any(w == "War Dept" and "ContentType=9" in u for w, u in feeds.OFFICIAL_RSS), "War Dept releases feed configured")

# ---- FIRMS: both satellites, one failing
csv_row = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"


def fake_firms(url, **k):
    if "noaa-21" in url:
        raise OSError("down")
    return (csv_row + "31.5,34.4,330,0.4,0.4,2026-11-15,2318,N20,n,2,290,12.5,N\n"
            "-30.0,150.0,330,0.4,0.4,2026-11-15,2318,N20,n,2,290,12.5,N\n").encode()


feeds.get = fake_firms
f = feeds.firms()
check(f["count"] == 1 and f["points"][0][6] == "N20" and "N21" in f["errors"], "FIRMS keeps one satellite when the other fails; clip applied")
feeds.get = lambda url, **k: (_ for _ in ()).throw(OSError("down"))
try:
    feeds.firms()
    check(False, "both satellites down raises")
except RuntimeError:
    check(True, "both satellites down raises (server keeps the old data)")

# ---- AIS: framing, merge, counts
class FakeSock:
    def __init__(self, data):
        self.data, self.sent = data, b""

    def recv(self, n):
        out, self.data = self.data[:n], self.data[n:]
        return out

    def sendall(self, b):
        self.sent += b


def frame(op, payload, fin=True):
    n = len(payload)
    hdr = bytes([(0x80 if fin else 0) | op]) + (bytes([n]) if n < 126 else bytes([126]) + n.to_bytes(2, "big"))
    return hdr + payload


msg = json.dumps({"MessageType": "PositionReport", "MetaData": {"MMSI": 273000001, "ShipName": "TEST TANKER ",
                  "latitude": 59.4, "longitude": 24.7, "time_utc": "2026-11-16 03:00:00.1 +0000 UTC"},
                  "Message": {"PositionReport": {"Sog": 11.2, "Cog": 80.0, "TrueHeading": 511, "Latitude": 59.4,
                                                 "Longitude": 24.7, "NavigationalStatus": 0}}}).encode()
ws = ais.WS.__new__(ais.WS)
ws.s, ws.buf = FakeSock(frame(0x9, b"hi") + frame(0x1, msg[:50], fin=False) + frame(0x0, msg[50:]) + frame(0x8, b"")), b""
check(ws.recv() == msg, "ping answered, fragmented message reassembled")
check(ws.s.sent[:1] == b"\x8a", "pong sent for the ping")
check(ws.recv() is None, "close frame ends the stream")

t0 = dt.datetime(2026, 11, 16, 3, 5, tzinfo=dt.timezone.utc)
heard = {"273000001": {"name": "TEST TANKER", "lat": 59.4, "lon": 24.7, "ts": "2026-11-16T03:00:00Z", "sog": 11.2, "cog": 80.0,
                       "hdg": None}, "273000002": {"type": 84, "name": "STATIC ONLY"}}
v = ais.merge({}, heard, t0)
check("273000002" in v and v["273000002"]["type"] == 84, "static-only record kept for later")
v = ais.merge(v, {"273000002": {"lat": 59.5, "lon": 24.8, "ts": "2026-11-16T03:04:00Z", "sog": 0.2}, "273000001": {"type": 81}}, t0)
c = ais.counts(v, t0)
check(c["baltic"] == {"ships_1h": 2, "underway": 1, "tankers": 2, "cargo": 0, "military": 0, "typed": 2},  # 0.9.0 adds typed
      "counts per area (type joined later)")
v = ais.merge(v, {}, t0 + dt.timedelta(hours=4))
check(v == {}, "ships not heard for 3 h are dropped")
check(ais.box_of(26.5, 56.3) == "hormuz" and ais.box_of(0, 0) is None, "box lookup")
check(ais.ship_class(35) == "military" and ais.ship_class(None) == "unknown", "ship classes")
os.environ["AISSTREAM_API_KEY"] = "k" * 40
check(ais.api_key() == "k" * 40, "key from the environment first")

# ---- server summaries (no scheduler, no network)
import server  # noqa: E402
s = server._outage_summary(o)
check(s["countries_with_outages"] == len(o["countries"]) and len(s["watched_regions"]) <= 12, "outage summary is compact")
s = server._advisory_summary(a2)
check(s["level4"] == a2["level4"] and s["level_changes"][0]["country"] == "Iran", "advisory summary carries changes")
g = server._advisories_geo(a)
names = {f["properties"]["country"] for f in g["features"]}
check("Iran" in names and all(f["properties"]["level"] >= 3 for f in g["features"]), "advisory map: level 3-4 only")
g = server._outages_geo(o)
check(len(g["features"]) == len(o["countries"]) and all(f["geometry"]["type"] == "MultiPolygon" for f in g["features"]), "outage map: one shape per country")
pts = [[34.4, 31.5, 12.5, "2026-11-15T23:18:00Z", "n", "N", "N21"]]
server.STATE["firms"] = {"data": {"points": pts}}
fc = {"features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [34.41, 31.5]},
                    "properties": {"kind": "event", "category": "strike", "ts_ms": server._iso_ms("2026-11-15T23:00:00Z")}}]}
n_th, _ = server.corroborate(fc)
check(n_th == 1, "thermal corroboration works with the 7-field FIRMS points")
print("%d checks passed" % ok)
