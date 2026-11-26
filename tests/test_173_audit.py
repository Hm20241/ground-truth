"""Offline tests for the 1.7.3 backend audit: the AIS feed's failure modes (gt/ais.py, gt/feeds.py ships_view) and the
server's scheduler, cache writes, summary step and gzip (server.py, gt/mymaps.py). Never touches the network.

Run: python3 -I tests/test_173_audit.py
"""
import datetime as dt
import gzip
import io
import json
import os
import socket
import ssl
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
os.environ["GT_DATA"] = tempfile.mkdtemp()
os.environ["GT_SEED"] = os.path.join(os.environ["GT_DATA"], "no-seed")
os.environ["AISSTREAM_API_KEY"] = "k" * 40
sys.path.insert(0, PROJ)
from gt import ais, feeds, mid, mymaps, sanctions  # noqa: E402

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

# ---- AIS: a server that takes the connection and never answers the handshake (seen live 2026-11-26)


class SilentSock:
    closed = 0

    def sendall(self, b):
        pass

    def recv(self, n):
        raise socket.timeout("The read operation timed out")

    def close(self):
        SilentSock.closed += 1


class FakeCtx:
    def wrap_socket(self, raw, server_hostname=None):
        return raw


real_conn, real_ctx = socket.create_connection, ssl.create_default_context
socket.create_connection = lambda addr, timeout=None: SilentSock()
ssl.create_default_context = lambda: FakeCtx()
try:
    ais.WS("example.invalid", "/x", timeout=20)
    check(False, "a silent handshake raises")
except ConnectionError as e:
    check("handshake" in str(e) and "20 s" in str(e), "a silent handshake says what happened: %s" % e)
except socket.timeout:
    check(False, "a silent handshake is reported as a handshake fault, not a bare read timeout")
check(SilentSock.closed == 1, "the socket is closed when the handshake fails")


class RefuseSock(SilentSock):
    def recv(self, n):
        return b"HTTP/1.1 429 Too Many Requests\r\n\r\n"


SilentSock.closed = 0
socket.create_connection = lambda addr, timeout=None: RefuseSock()
try:
    ais.WS("example.invalid", "/x")
    check(False, "HTTP 429 raises")
except ais.HandshakeError as e:
    check(e.code == 429 and SilentSock.closed == 1, "HTTP 429 is still a HandshakeError (back-off), socket closed once")
socket.create_connection, ssl.create_default_context = real_conn, real_ctx

# ---- AIS: a sample that hears nothing is a failure, not an empty "ok"


class DeadWS:
    wire, deflate = 0, True

    def __init__(self, *a, **k):
        self.s = self
        self.msgs = list(DeadWS.script)

    def settimeout(self, t):
        pass

    def send_text(self, t):
        pass

    def recv(self):
        if not self.msgs:
            return None
        m = self.msgs.pop(0)
        if m is socket.timeout:
            raise socket.timeout("timed out")
        return m

    def close(self):
        pass


real_ws = ais.WS
ais.WS = DeadWS
for script, what in (([], "closed right after the subscription"), ([socket.timeout], "silent for 15 s")):
    DeadWS.script = script
    try:
        ais.sample(seconds=5)
        check(False, "an empty sample raises (%s)" % what)
    except RuntimeError as e:
        check("no messages" in str(e), "stream %s -> the feed fails instead of reporting an empty sample" % what)
pos = json.dumps({"MessageType": "PositionReport", "MetaData": {"MMSI": 273000001, "time_utc": "2026-11-26 05:00:00.1 +0000 UTC"},
                  "Message": {"PositionReport": {"Latitude": 59.4, "Longitude": 24.7, "Sog": 1.0}}}).encode()
DeadWS.script = [pos, socket.timeout]
heard, st = ais.sample(seconds=5)
check(st["messages"] == 1 and "273000001" in heard, "a sample cut short after some messages is still used")
ais.WS = real_ws

# ---- ships_view: a listed (sanctioned) warship outside every watch box has no area
NOW = dt.datetime(2026, 11, 26, 5, 0, tzinfo=dt.timezone.utc)
TS = "2026-11-26T04:50:00Z"
vessels = {
    "273000009": {"name": "RUS WARSHIP 555", "type": 35, "lat": 10.0, "lon": -40.0, "ts": TS, "sog": 12.0, "seen": TS},   # open Atlantic
    "273000010": {"name": "SHADOW ONE", "type": 80, "lat": 59.4, "lon": 24.7, "ts": TS, "sog": 9.0, "seen": TS},          # Baltic tanker
}
real_lookup = sanctions.lookup
sanctions.lookup = lambda imo=None, mmsi=None: {"marks": "S", "lists": ["x"], "name": "n", "url": "u", "imo": None}
try:
    v = feeds.ships_view(vessels, {}, {}, NOW, ais, mid)
    check(len(v["listed"]) == 2 and v["areas"]["baltic"]["listed"] == 1,
          "a listed warship outside the boxes is listed, counted in no area (was KeyError: None)")
    check({c["area"] for c in v["listed"]} == {None, "baltic"} and v["listed"][0]["area"] is None,
          "listed ships with and without an area sort together (was TypeError)")
except (KeyError, TypeError) as e:
    check(False, "a listed warship outside every box breaks the ships feed: %r" % (e,))
sanctions.lookup = real_lookup

# ---- mymaps.run: latest.geojson and stats.json are replaced whole (server.derive reads them from other threads)
kml = (b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Map Day 7</name>'
       b'<Placemark><name>Strike</name><description>https://x.com/a/status/1990000000000000000</description>'
       b'<styleUrl>#icon-1571-A52714</styleUrl><Point><coordinates>30.5,50.4,0</coordinates></Point></Placemark>'
       b'</Document></kml>')
kp = os.path.join(os.environ["GT_DATA"], "t.kml")
open(kp, "wb").write(kml)
mymaps.run(kp)
good = open(os.path.join(mymaps.DATA, "latest.geojson")).read()
real_dump = json.dump


def half_dump(obj, fh, **kw):
    fh.write('{"type":"FeatureColl')
    raise OSError("disk full")


mymaps.json.dump = half_dump
try:
    mymaps.run(kp)
except OSError:
    pass
mymaps.json.dump = real_dump
check(open(os.path.join(mymaps.DATA, "latest.geojson")).read() == good, "a failed write leaves the last good latest.geojson in place")

# ---- server: scheduler, cache, summary step, gzip
import server  # noqa: E402

# a cache file that is not an object, and unreadable time stamps
for name, text in (("mil", "null"), ("front", "[1,2]"), ("losses", '{"ok":true,"at":"yesterday","data":{}}')):
    open(os.path.join(server.CACHE, name + ".json"), "w").write(text)
server._load_disk_cache()
check("mil" not in server.STATE and "front" not in server.STATE, "a cache file holding null or a list is ignored")
check(server._age("losses") == 1e12 and server._since("garbage") == 1e12 and server._since(None) == 1e12,
      "an unreadable time stamp reads as very old")

started = []
real_thread = server.threading.Thread


class FakeThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.args = args

    def start(self):
        if self.args[0] == "boom":
            raise RuntimeError("can't start new thread")
        started.append(self.args[0])


server.threading.Thread = FakeThread
server.STATE["bad"] = None  # what a null cache file used to leave behind
jobs = {"bad": (lambda: {}, 60), "boom": (lambda: {}, 60), "good": (lambda: {}, 60)}
err, sys.stderr = sys.stderr, io.StringIO()
try:
    server._tick(jobs)
    raised = False
except Exception:
    raised = True
sys.stderr = err
server.threading.Thread = real_thread
check(not raised and started == ["bad", "good"], "one job that cannot start does not stop the scheduler or the jobs after it")
check("boom" not in server.RUNNING, "a job whose thread never started is not left marked as running")
server.RUNNING.clear()
del server.STATE["bad"]

# _run: the cache file is written whole, and a failing derive() still publishes the feed event
seq = server.BUS["seq"]
real_derive = server.derive


def bad_derive():
    raise ValueError("half-written latest.geojson")


server.derive = bad_derive
err, sys.stderr = sys.stderr, io.StringIO()
try:
    server._run("ships", lambda: {"count": 1})
    raised = False
except Exception:
    raised = True
sys.stderr = err
server.derive = real_derive
check(not raised and server.BUS["seq"] == seq + 1 and server.STATE["ships"]["ok"], "a failing summary step still publishes the feed's event")
check(json.load(open(os.path.join(server.CACHE, "ships.json")))["data"] == {"count": 1}
      and not os.path.exists(os.path.join(server.CACHE, "ships.json.tmp")), "feed cache written through a temp file")
server._run("ships", lambda: {"count": {1, 2}})  # not JSON-serialisable: the run fails, the good cache file stays
check(server.STATE["ships"]["ok"] is False and json.load(open(os.path.join(server.CACHE, "ships.json")))["data"] == {"count": 1},
      "a result that cannot be written leaves the last good cache file intact")

# czib_geo: same answer, without re-reading Natural Earth while the zone list is unchanged
server.STATE["czib"] = {"data": {"zones": [{"name": "CZIB-1", "country": "Ukraine", "valid_until": "2027-01-31"}]}}
a = server._czib_geo()
opened = []
check(len(a["features"]) == 1 and a["features"][0]["properties"]["country"] == "Ukraine", "czib_geo: one shape for Ukraine")
import builtins  # noqa: E402
bo = builtins.open


def counting_open(p, *a2, **k):
    if str(p) == server.geo.REF:
        opened.append(p)
    return bo(p, *a2, **k)


builtins.open = counting_open
b = server._czib_geo()
server.STATE["czib"]["data"]["zones"].append({"name": "CZIB-2", "country": "Iran (Islamic Republic of)", "valid_until": "2027-01-31"})
c = server._czib_geo()
builtins.open = bo
check(b == a and len(opened) == 1 and len(c["features"]) == 2, "czib_geo: cached while the zones are unchanged, rebuilt when they change")


class FakeHandler:
    def __init__(self, headers):
        self.headers, self.out, self.wfile, self.code = headers, [], io.BytesIO(), None

    def send_response(self, code):
        self.code = code

    def send_header(self, k, v):
        self.out.append((k, v))

    def end_headers(self):
        pass


big = {"points": [[i, i * 2, "name %d" % i] for i in range(2000)]}
plain = json.dumps(big, separators=(",", ":"), ensure_ascii=False).encode()
h = FakeHandler({"Accept-Encoding": "gzip, deflate, br"})
server.Handler._json(h, big)
hd = dict(h.out)
check(hd.get("Content-Encoding") == "gzip" and gzip.decompress(h.wfile.getvalue()) == plain
      and int(hd["Content-Length"]) == len(h.wfile.getvalue()) < len(plain) / 2 and hd.get("Vary") == "Accept-Encoding",
      "a large JSON answer is gzipped for a client that accepts it (%d -> %d bytes)" % (len(plain), len(h.wfile.getvalue())))
h = FakeHandler({})
server.Handler._json(h, big)
check("Content-Encoding" not in dict(h.out) and h.wfile.getvalue() == plain, "no Accept-Encoding: the same bytes as before")
h = FakeHandler({"Accept-Encoding": "gzip"})
server.Handler._json(h, {"error": "not found"}, 404)
check("Content-Encoding" not in dict(h.out) and h.code == 404, "small answers are not compressed")
h = FakeHandler({"Accept-Encoding": "gzip", "If-None-Match": '"abc"'})
server.Handler._json(h, big, etag="abc")
check(h.code == 304 and h.wfile.getvalue() == b"", "an unchanged ETag is still a 304 with no body")
print("%d checks passed" % ok)
