"""Offline tests for 0.11.0 foundations: the per-release module loader (gt/extfeeds.py), the push stream
(/api/stream, Server-Sent Events) and the per-feed freshness fields in /api/status.
No network: sockets may only reach 127.0.0.1 (the in-process test server).

Run: python3 -I tests/test_0110_ext.py
"""
import datetime as dt
import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)
TMP = tempfile.mkdtemp(prefix="gt-ext-")
os.environ["GT_DATA"] = os.path.join(TMP, "data")
os.environ["GT_SEED"] = os.path.join(TMP, "seed")
os.environ.pop("GT_EXT_FEEDS", None)

_connect = socket.socket.connect


def loopback_only(self, addr, *a, **k):
    if isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "::1"):
        return _connect(self, addr, *a, **k)
    raise AssertionError("network call in an offline test: %r" % (addr,))


socket.socket.connect = loopback_only
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)
    ok += 1


# ---------- extfeeds ----------
from gt import extfeeds  # noqa: E402

check(extfeeds.ENABLED == () or all(m in extfeeds.ALL for m in extfeeds.ENABLED), "ENABLED only names known modules")
check(extfeeds.enabled() == extfeeds.ENABLED, "no env: enabled() is ENABLED")
os.environ["GT_EXT_FEEDS"] = "all"
check(extfeeds.enabled() == extfeeds.ALL, "GT_EXT_FEEDS=all: every module")
os.environ["GT_EXT_FEEDS"] = "cyber, nosuchmodule ,wire"
check(extfeeds.enabled() == ("cyber", "wire"), "GT_EXT_FEEDS list: unknown names dropped")

good = types.ModuleType("gt.fakegood")
good.VERSION = "9.9"
good.FEEDS = {"fakealpha": (lambda now=None, fetch=None: {"count": 0}, 120), "fakebeta": (lambda **k: {}, 300)}
good.PUBLIC_OK = {"fakealpha": True}
good.NON_COMMERCIAL = True
bad = types.ModuleType("gt.fakenames")
bad.FEEDS = {"Bad-Name": (lambda **k: {}, 60), "mil": (lambda **k: {}, 60), "fakegamma": (lambda **k: {}, 60)}
sys.modules["gt.fakegood"], sys.modules["gt.fakenames"] = good, bad
REAL_ALL = extfeeds.ALL
extfeeds.ALL = extfeeds.ALL + ("fakegood", "fakenames", "fakemissing")
os.environ["GT_EXT_FEEDS"] = "fakegood,fakemissing,fakenames"
reg = {"mil": ("builtin", 45)}
meta = extfeeds.load(reg)
check(reg["mil"] == ("builtin", 45), "a module cannot replace a built-in feed")
check(set(reg) == {"mil", "fakealpha", "fakebeta", "fakegamma"}, "valid feeds registered: %s" % sorted(reg))
check(reg["fakealpha"][1] == 120 and isinstance(reg["fakebeta"][1], int), "interval kept as int")
check(meta["fakealpha"] == {"module": "fakegood", "version": "9.9", "every": 120, "public_ok": True, "non_commercial": True},
      "META carries module, version, interval, per-feed PUBLIC_OK and NON_COMMERCIAL: %s" % meta.get("fakealpha"))
check(meta["fakebeta"]["public_ok"] is False, "PUBLIC_OK dict: a feed it does not name is not public")
check(meta["fakegamma"]["version"] is None and meta["fakegamma"]["non_commercial"] is False, "module without flags: defaults")
check("fakemissing" in extfeeds.ERRORS and "ModuleNotFoundError" in extfeeds.ERRORS["fakemissing"], "import failure reported, not fatal")
check("fakenames:Bad-Name" in extfeeds.ERRORS and "fakenames:mil" in extfeeds.ERRORS, "bad name and clash reported")
st = extfeeds.status()
check(st["enabled"] == ["fakegood", "fakemissing", "fakenames"] and "fakealpha" in st["feeds"], "status() shape")
json.dumps(st)  # must serialise for /api/status
os.environ.pop("GT_EXT_FEEDS")
extfeeds.ALL = REAL_ALL

# ---------- server: push stream + status ----------
import server  # noqa: E402  (module import runs extfeeds.load with the release's ENABLED list; no threads start)
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]


def get(path):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    c.request("GET", path)
    return c, c.getresponse()


def read_event(resp, want, limit=10):
    """Read SSE blocks until one has `event: <want>`; returns {field: value}."""
    end = time.time() + limit
    block = {}
    while time.time() < end:
        line = resp.fp.readline().decode()
        if not line:
            return None
        line = line.rstrip("\n")
        if not line:
            if block.get("event") == want:
                return block
            block = {}
        elif not line.startswith(":") and ":" in line:
            k, v = line.split(":", 1)
            block[k] = v.strip()
    return None


c1, r1 = get("/api/stream")
check(r1.status == 200 and r1.getheader("Content-Type", "").startswith("text/event-stream"), "stream: 200 text/event-stream")
check(r1.getheader("Cache-Control") == "no-store" and r1.getheader("X-Accel-Buffering") == "no", "stream: no-store, no proxy buffering")
hello = read_event(r1, "hello")
check(hello and json.loads(hello["data"])["version"] == server.VERSION, "stream: hello carries the server version")
check(server.STREAMS["n"] == 1, "stream: counted while open")
server.publish("feed", feed="fakealpha", ok=True, at="2026-11-20T06:00:00Z")
ev = read_event(r1, "feed")
check(ev and json.loads(ev["data"])["feed"] == "fakealpha" and int(ev["id"]) == json.loads(ev["data"])["seq"],
      "stream: a published feed run arrives with matching id/seq")
for i in range(3):
    server.publish("feed", feed="burst%d" % i, ok=True, at=None)
got = [json.loads(read_event(r1, "feed")["data"])["feed"] for _ in range(3)]
check(got == ["burst0", "burst1", "burst2"], "stream: a burst arrives in order, none lost: %s" % got)

server.MAX_STREAMS = 1
c2, r2 = get("/api/stream")
check(r2.status == 503, "stream: over MAX_STREAMS -> 503")
r2.read(); c2.close()

r1.close(); c1.close()  # the browser goes away: the server notices on its next write and frees the slot
t_end = time.time() + 5
while server.STREAMS["n"] and time.time() < t_end:
    server.publish("feed", feed="probe", ok=True, at=None)
    time.sleep(0.05)
check(server.STREAMS["n"] == 0, "stream: slot released after the client disconnects")

server.MAX_STREAMS, server.STREAM_LIFE_S = 24, 0  # life is fixed when a stream opens; 0 = hello, then close
c4, r4 = get("/api/stream")
rest = r4.read().decode()  # returns only because the server closes the stream
check("event: hello" in rest and "event: feed" not in rest, "stream: ends at its lifetime (browser reconnects by itself)")
c4.close()
time.sleep(0.1)
check(server.STREAMS["n"] == 0, "stream: slot released when the stream ends")
server.STREAM_LIFE_S = 1800

now = dt.datetime.now(dt.timezone.utc)
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
server.STATE.update({"mil": {"ok": True, "at": iso(now)}, "gdelt": {"ok": True, "at": iso(now - dt.timedelta(hours=2))},
                     "cables": {"ok": True, "at": iso(now - dt.timedelta(days=5))}})
c3, r3 = get("/api/status")
s = json.loads(r3.read())
check("modules" in s and "streams" in s, "status: modules and streams listed")
check(s["feeds"]["mil"]["every"] == 45 and s["feeds"]["mil"]["stale"] is False, "status: mil every 45 s, fresh")
check(s["feeds"]["gdelt"]["stale"] is True, "status: gdelt 2 h old on a 15 min interval is stale")
check(s["feeds"]["cables"]["stale"] is False, "status: weekly cables 5 days old is not stale")
check(server._every("mymaps") == server.MAP_REFRESH and server._every("nosuch") is None, "_every: source map and unknown feed")

# digest: private, compact, built only from feeds that exist
pin = lambda t, title, th: {"type": "Feature", "geometry": {"type": "Point", "coordinates": [30, 50]}, "properties": {  # noqa: E731
    "ts_ms": int((now - dt.timedelta(hours=t)).timestamp() * 1000), "ts": iso(now - dt.timedelta(hours=t)),
    "theatre": th, "country_name": "Ukraine", "title": title, "kind": "event"}}
server.STATE["geoconfirmed"] = {"ok": True, "at": iso(now), "data": {"geojson": {"type": "FeatureCollection", "features": [
    pin(1, "Synthetic strike " + "x" * 300, "ukraine-russia"), pin(5, "Synthetic two", "africa"), pin(100, "Too old", "africa")]}}}
server.STATE["hazards"] = {"ok": True, "at": iso(now), "data": {"geojson": {"features": [
    {"properties": {"alert": "Orange", "type_label": "Flood", "event_name": "Synth", "gdacs_country": "A, " * 80, "severity": "s"}},
    {"properties": {"alert": "Green", "type_label": "Wildfire"}}]}}}
c5, r5 = get("/api/digest")
dg = json.loads(r5.read())
gc = dg["curated_pins"]["geoconfirmed"]
check(gc["count"] == 2 and gc["by_theatre"] == {"ukraine-russia": 1, "africa": 1}, "digest: 48 h window and theatre counts: %s" % gc)
check(len(gc["latest"][0]) < 220 and gc["latest"][0].endswith("…"), "digest: untrusted titles cut short")
check(len(dg["hazards_orange_red"]) == 1 and len(dg["hazards_orange_red"][0]) < 260, "digest: Orange/Red only, country list cut")
check("cir" not in dg["curated_pins"] and "signals" not in dg and "wire" not in dg and "cyber" not in dg,
      "digest: absent feeds leave no keys")

# 0.12.0/0.13.0 digest sections and the news points (private)
ms = lambda h: int((now - dt.timedelta(hours=h)).timestamp() * 1000)  # noqa: E731
story = lambda i, h, th, cc, **k: dict({"id": i, "title": "Synthetic story %s" % i, "ts_ms": ms(h), "ts": iso(now - dt.timedelta(hours=h)),  # noqa: E731
                                         "theatre": th, "countries": cc, "placed": "text", "category": "other", "also_in": []}, **k)
server.STATE["wire"] = {"ok": True, "at": iso(now), "data": {"items": [story("w1", 1, "africa", ["SDN"]), story("w2", 2, "africa", ["SDN"])],
                                                             "by_theatre": {"africa": 2}, "by_country": {"SDN": 2, "ZZZ": 4}, "by_country_24h": {"SDN": 2}}}
server.STATE["telegram"] = {"ok": True, "at": iso(now), "data": {"items": [story("t1", 1, "ukraine-russia", ["UKR"], channel="examplechan")],
                                                                 "by_theatre": {"ukraine-russia": 1}, "by_country": {"UKR": 1, "SDN": 1}, "by_country_24h": {"UKR": 1}}}
server.STATE["cyber"] = {"ok": True, "at": iso(now), "data": {"summary": "Synthetic cyber summary " + "y" * 600, "infocon": {"level": "green"}}}
server.STATE["bgp"] = {"ok": True, "at": iso(now), "data": {"countries": [{"name": "Atlantis", "level": "drop"}, {"name": "Lemuria", "level": "ok"}]}}
c7, r7 = get("/api/digest")
dg = json.loads(r7.read())
check(dg["wire"]["latest"]["africa"][0].endswith("Synthetic story w1") and dg["wire"]["licence"] == "non-commercial", "digest: wire summary")
check(dg["telegram"]["latest"]["ukraine-russia"][0].split()[1] == "@examplechan", "digest: Telegram lines name the channel")
check(len(dg["cyber"]["summary"]) < 430 and dg["cyber"]["routing_drops"] == ["Atlantis"] and dg["cyber"]["infocon"] == "green",
      "digest: cyber summary cut, routing drops listed")
c8, r8 = get("/api/news_geo")
ng = {f["properties"]["a3"]: f for f in json.loads(r8.read())["features"]}
check(set(ng) == {"SDN", "UKR"}, "news_geo: one point per known country, unknown codes dropped: %s" % sorted(ng))
sd = ng["SDN"]["properties"]
check((sd["wire_48h"], sd["wire_24h"], sd["tg_48h"], sd["n24"], sd["n48"]) == (2, 2, 1, 2, 3) and sd["theatre"] == "africa",
      "news_geo: wire and Telegram counts per country: %s" % sd)
check(ng["SDN"]["geometry"]["type"] == "Point" and len(ng["SDN"]["geometry"]["coordinates"]) == 2, "news_geo: label point")
server.derive()   # builds the summary from STATE, as the scheduler does
c6, r6 = get("/api/summary")
summ = r6.read().decode()
check(r6.status == 200 and len(summ) > 50 and summ != "null", "summary was built (the guard below means something)")
check(all(x not in summ for x in ("curated_pins", "Synthetic strike", "hazards_orange_red", "Synthetic story", "examplechan",
                                    "Synthetic cyber", "Atlantis")),
      "summary (copied verbatim to the public mirror) carries none of the digest")
srv.shutdown()

# ---------- page ----------
app = open(os.path.join(PROJ, "web", "app.js"), encoding="utf-8").read()
idx = open(os.path.join(PROJ, "web", "index.html"), encoding="utf-8").read()
check('new EventSource("api/stream")' in app and "window.GTX = {" in app and "window.GTXQ" in app, "page: push client and GTX API present")
check(app.index("window.GTX = {") < app.index("(window.GTXQ || []).forEach"), "page: queue drains after GTX exists")
check("briefColumn(o) { EXT.briefCols.push(o); }" in app and "briefCoverage(s) + b.theatres" in app,
      "page: Brief coverage columns come from the extensions (1.0.0)")
from gt import feeds  # noqa: E402
check(feeds.REGISTRY["official"][1] == 600 and feeds.CENTCOM_EVERY >= 6 * 3600,
      "1.0.0: official statements every 10 min while CENTCOM (Firecrawl) keeps its 6 h cache")
ext = [l for l in idx.splitlines() if 'src="ext/' in l]
check(all(idx.index(l) < idx.index('src="app.js') for l in ext), "page: extension scripts load before app.js")
ver = open(os.path.join(PROJ, "VERSION")).read().strip()
check(idx.count("?v=%s" % ver) >= 2 and all("?v=%s" % ver in l for l in ext), "page: every asset carries ?v=%s" % ver)
# Each page extension belongs to feed modules; a release loads it exactly when it runs those modules (extfeeds.ENABLED),
# so the page never shows an empty layer or tab for a feed the server does not run.
EXT_MODULES = {"curated.js": ("geoconfirmed", "curated"), "hazards.js": ("hazards",), "wire.js": ("wire", "telegram"),
               "signals.js": ("signals",), "airspace.js": ("airspace",), "cyber.js": ("cyber",),
               "outages.js": ("services", "disruption")}
files = sorted(n for n in os.listdir(os.path.join(PROJ, "web", "ext")) if n.endswith(".js"))
check(set(files) == set(EXT_MODULES), "page: every extension file is mapped to its modules: %s" % files)
check(all(m in extfeeds.ALL for ms in EXT_MODULES.values() for m in ms), "page: the map names only known modules")
release = extfeeds.ENABLED  # the release default, not an env override (GT_EXT_FEEDS was cleared above)
for name in files:
    src = open(os.path.join(PROJ, "web", "ext", name), encoding="utf-8").read()
    check("GTXQ" in src, "page: %s queues through GTXQ" % name)
    want = all(m in release for m in EXT_MODULES[name])
    check(('src="ext/%s' % name in idx) == want, "page: %s %s (release modules %s)" % (
        name, "is loaded" if want else "is not loaded", ", ".join(release) or "none"))

# 1.1.0: GPSJAM hexes need h3-js in the page. The vendored file is the one from the npm tarball h3-js-4.5.0.tgz
# (registry sha512 integrity checked on download, 2026-11-20); its hash is pinned so a swapped file fails here.
import hashlib  # noqa: E402
h3_path = os.path.join(PROJ, "web", "vendor", "h3-js.umd.js")
check(os.path.exists(h3_path) and hashlib.sha256(open(h3_path, "rb").read()).hexdigest() ==
      "4180c39bcf5e6bb8f1f236d8a245e51416a0109a3195a475f442ef0a290ca08a", "1.1.0: vendored h3-js 4.5.0 matches the pinned sha256")
check(os.path.exists(os.path.join(PROJ, "web", "vendor", "h3-js-LICENSE.txt")), "1.1.0: h3-js Apache-2.0 licence ships with it")
h3_tag = 'src="vendor/h3-js.umd.js?v=4.5.0"'
check((h3_tag in idx) == ("airspace" in release), "1.1.0: the page loads h3-js exactly when the airspace module runs")
check(h3_tag not in idx or idx.index(h3_tag) < idx.index('src="ext/airspace.js'), "1.1.0: h3-js loads before ext/airspace.js")
asrc = open(os.path.join(PROJ, "web", "ext", "airspace.js"), encoding="utf-8").read()
check('typeof window.h3 === "undefined"' in asrc and 'GTX.feed("gpsjam"' in asrc and "x + 360" in asrc,
      "1.1.0: airspace.js draws GPSJAM hexes, copes without h3-js and keeps antimeridian cells whole")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d checks passed" % ok)
