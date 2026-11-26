"""Offline tests for 1.7.3, Atlas theme: ships say how old they are, loaded feeds are asked for again when they are due,
a feed that did not answer is tried again, a run of failed replies reads as offline, and one bad record cannot stop the page.

Static checks on web/themes/atlas/, and node runs core.js against a stub browser (no DOM library, no network).

Run: python3 -I tests/test_173_atlas.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1


def read(rel):
    with open(os.path.join(PROJ, rel), encoding="utf-8") as fh:
        return fh.read()


CORE, MAP, UI, CSS = (read("web/themes/atlas/" + f) for f in ("core.js", "map.js", "ui.js", "atlas.css"))
PAGE = read("web/atlas.html")

# ---------- ships ----------
check("heard: p[7]" in MAP and '"Position heard"' in MAP, "a ship's card says when its position was heard")
check("The ship feed reported an error at its last run" not in UI and "shipNote(d.ships, st.ships)" in UI, "the Sea page says how old the newest ship position is instead of a bare error line")
check("Loading ship positions" in UI and "Ship positions did not load. They will be tried again." in UI, "the Sea page says when ships are still loading or did not load")
check('"Military ships that transmit (larger dot)", ["ships"]' in UI, "the Sea legend explains the red ship dots")
check(re.search(r'"ship-pt": \["sea"\]', MAP) is not None, "ship dots belong to the Sea topic")

# ---------- null fields ----------
check("c.avg7.total" not in MAP and "c.year_ago7.total" not in MAP and "c.avg7.total" not in UI, "a chokepoint with no 7-day figures cannot throw")
check("c.name.toLowerCase()" not in UI, "search copes with a place that has no name")
check("${esc(g)}%" in UI, "the chokepoint change figure is escaped")
check("try { build(); } catch" in CORE, "one bad record cannot stop the screens from drawing")

# ---------- timers and listeners ----------
check("setInterval(refresh, 60000)" in CORE, "loaded feeds are checked every minute for a refresh that is due")
check('UI.mode !== "wall") return;' in UI, "a late wall step does nothing once the wall is left")
check('rz.addEventListener("pointercancel", up)' in UI and 'rz.removeEventListener("pointercancel", up)' in UI, "a cancelled panel drag lets go of its listeners")

# ---------- links, text size, requests ----------
for name, src in (("core.js", CORE), ("map.js", MAP), ("ui.js", UI), ("atlas.html", PAGE)):
    for m in re.finditer(r"<a\b[^>]*target=\"_blank\"[^>]*>", src):
        check("noopener" in m.group(0), name + ": a link that opens a new tab has rel noopener")
    check(not re.search(r"method:\s*[\"'](POST|PUT|DELETE|PATCH)", src), name + " is GET only")
    check(not re.search(r"fetch\(\s*[\"'`](https?:)?//", src), name + " asks only relative addresses")
small = [m.group(0) for m in re.finditer(r"font-size:\s*([\d.]+)px", CSS) if float(m.group(1)) < 14]
check(not small, "no text under 14 px in atlas.css: %s" % small[:3])
check(re.findall(r"fetch\(([^)]{0,40})", CORE + MAP + UI) == ['"api/" + p, { cache: "no-cache" }', '"geo/alert-regions.json"'], "Atlas makes requests in two places only: api() and the region shapes")

# ---------- logic: node runs core.js against a stub browser ----------
NODE = shutil.which("node") or "/opt/homebrew/bin/node"
JS = r"""
const fs = require("fs"), vm = require("vm");
let NOW = Date.parse("2026-11-26T05:00:00Z");
const RealDate = Date;
class FakeDate extends RealDate { constructor(...a) { if (a.length) super(...a); else super(NOW); } static now() { return NOW; } }
const calls = {}, fail = new Set(), replies = {};
const fetchStub = (url) => { calls[url] = (calls[url] || 0) + 1;
  if (fail.has(url) || fail.has("*")) return Promise.reject(new Error("down"));
  const body = replies[url]; if (body === undefined) return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
  return Promise.resolve({ ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(body)) }); };
const store = {};
const win = { localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } }, matchMedia: () => ({ matches: false }) };
const doc = { hidden: false, getElementById: () => null };
const errors = [];
const ctx = { window: win, document: doc, localStorage: win.localStorage, matchMedia: win.matchMedia, fetch: fetchStub, Date: FakeDate, Intl, Math, JSON, Promise, Map, Set, WeakMap, Number, String, Object, Array, Error,
  setTimeout, clearTimeout, setInterval: () => 0, console: { error: (...a) => errors.push(a.map(String).join(" ")), log() {} } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[process.argv.length - 1], "utf8"), ctx);
const A = win.ATLAS, S = A.S, wait = (ms) => new Promise((r) => setTimeout(r, ms));
const feed = (data) => ({ ok: true, at: "2026-11-26T05:00:00Z", error: null, data });
const out = {};
(async () => {
  replies["api/status"] = { feeds: { ships: { every: 300 }, mil: { every: 45 }, portwatch: { every: 21600 }, quakes: { every: 300 }, hazards: { every: 900 }, wire: { every: 300 } } };
  // ok:false with data: the last good ships are still shown
  replies["api/feed/ships"] = { ok: false, at: "2026-11-26T05:00:00Z", error: "TimeoutError", data: { count: 2, points: [[1, 2, 0, 0, "tanker", "A", 1, "2026-11-26T04:59:00Z"], [3, 4, 0, 0, "military", "B", 2, "2026-11-26T04:58:00Z"]] } };
  replies["api/feed/mil"] = feed({ geojson: { features: [] } });
  replies["api/feed/portwatch"] = feed({ chokepoints: [] });
  replies["api/feed/quakes"] = feed({ count: 1, geojson: { features: [{ properties: { id: "q1", time: "2026-11-26T04:00:00Z", mag: 5, place: "x" }, geometry: null }] } });
  replies["api/feed/hazards"] = feed({ geojson: { features: [] } });
  await A.need(["ships", "mil", "portwatch"]);
  out.shipsKept = (S.d.ships || {}).count === 2 && S.loaded.has("ships") && !S.failed.has("ships");
  out.first = calls["api/feed/ships"];
  await A.load("ships"); out.again = calls["api/feed/ships"];            // fresh: not asked again
  out.notListed = (await A.load("gfw"), calls["api/feed/gfw"] || 0);     // not in status: never asked
  NOW += 6 * 60000;
  out.dueAll = A.due(NOW).slice().sort();                                // topic "all": ships are heavy and not on the map
  S.topic = "sea"; out.dueSea = A.due(NOW).slice().sort();
  await A.load("ships"); out.aged = calls["api/feed/ships"];             // older than its 5 minutes: asked again
  out.ttl = [A.ttl("ships"), A.ttl("mil"), A.ttl("portwatch"), A.ttl("outages_geo")];
  // a feed that does not answer is tried again after 2 minutes
  fail.add("api/feed/hazards"); await A.load("hazards");
  out.failed = S.failed.has("hazards"); out.dueSoon = A.due(NOW + 60000).includes("hazards"); out.dueLater = A.due(NOW + 130000).includes("hazards");
  fail.delete("api/feed/hazards"); await A.load("hazards"); out.recovered = S.loaded.has("hazards") && !S.failed.has("hazards");
  await wait(120); out.netOk = S.net;
  // four failed replies in a row read as offline; one good reply clears it
  fail.add("*"); for (const n of ["alerts", "summary", "analysis", "events"]) await A.load(n, true);
  await wait(120); out.netDown = S.net;
  fail.delete("*"); replies["api/summary"] = {}; await A.load("summary", true); await wait(120); out.netBack = S.net;
  // one bad record does not stop the build, and the data event still fires
  let fired = 0; A.on("data", () => { fired++; });
  replies["api/news_geo"] = { features: [{ properties: { a3: "XXX", name: null }, geometry: null }, null, { properties: { a3: "UKR", name: "Ukraine", theatre: "ukraine-russia" }, geometry: { coordinates: [31, 49] } }] };
  replies["api/feed/wire"] = feed({ items: [] });
  await A.load("news_geo", true); await A.load("quakes", true); await wait(120);
  out.fired = fired > 0; out.cc = S.cc.has("UKR") && !S.cc.has("XXX"); out.quakeEntry = S.entries.some((e) => e.kind === "Earthquake" && e.ll === null);
  // a thrown build is caught: the event still fires
  replies["api/events"] = { features: [{ properties: null }] }; fired = 0; await A.load("events", true); await wait(120);
  out.firedAfterThrow = fired > 0; out.buildErrorLogged = errors.some((e) => /Atlas build/.test(e));
  // fronts: the box test keeps Classic's 75 km count. A west-east line at 48 N; one degree of latitude is 110.57 km.
  const pin = (id, lon, lat) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { kind: "event", id, ts_ms: NOW - 3600e3, title: id, category: "strike" } });
  const kmLon = Math.cos(48 * Math.PI / 180) * 111.32;
  replies["api/events"] = { features: [
    { type: "Feature", geometry: { type: "LineString", coordinates: [[30, 48], [32, 48]] }, properties: { kind: "overlay", id: "L", front_kind: "contact", title: "Line" } },
    pin("in50n", 31, 48 + 50 / 110.57), pin("in74n", 31, 48 + 74 / 110.57), pin("out76n", 31, 48 + 76 / 110.57), pin("out100s", 31, 48 - 100 / 110.57),
    pin("in70e", 32 + 70 / kmLon, 48), pin("out80e", 32 + 80 / kmLon, 48), pin("in70w", 30 - 70 / kmLon, 48), pin("far", 60, 10)] };
  errors.length = 0; await A.load("events", true); await wait(120);
  out.front = S.fronts.map((f) => [f.n24, f.n72, f.bbox]); out.noErrors = errors.length === 0;
  console.log(JSON.stringify(out));
})();
"""
if not os.path.exists(NODE):
    print("SKIP: node not found, logic checks not run")
else:
    r = subprocess.run([NODE, "-e", JS, "--", os.path.join(PROJ, "web/themes/atlas/core.js")], capture_output=True, text=True, timeout=60)
    check(r.returncode == 0 and r.stdout.strip(), "node runs core.js against the stub: " + r.stderr[-400:])
    o = json.loads(r.stdout.strip().splitlines()[-1])
    check(o["shipsKept"], "a ships reply marked ok:false that still holds ships is shown, not dropped")
    check(o["first"] == 1 and o["again"] == 1, "a fresh feed is not asked for twice")
    check(o["notListed"] == 0, "a feed the status does not list is never asked for")
    check(o["dueAll"] == ["mil"], "after 6 minutes the aircraft are due; ships wait while their topic is not on the map; chokepoints are not due: %s" % o["dueAll"])
    check(o["dueSea"] == ["mil", "ships"], "with the Sea topic on the map the ships are due too: %s" % o["dueSea"])
    check(o["aged"] == 2, "opening a topic again after its feed's refresh time asks for the feed again")
    check(o["ttl"] == [300000, 300000, 21600000, 300000], "a feed is refreshed at its own pace, never faster than 5 minutes: %s" % o["ttl"])
    check(o["failed"] and not o["dueSoon"] and o["dueLater"] and o["recovered"], "a feed that did not answer is tried again after 2 minutes and recovers")
    check(o["netOk"] == "ok" and o["netDown"] == "offline" and o["netBack"] != "offline", "four failed replies in a row read as offline; a good reply clears it: %s %s %s" % (o["netOk"], o["netDown"], o["netBack"]))
    check(o["fired"] and o["cc"] and o["quakeEntry"], "records with no geometry or no name are skipped or kept without a place, and the screens still draw")
    check(o["firedAfterThrow"] and o["buildErrorLogged"], "a build that throws is logged and the data event still fires")
    check(o["front"] and o["front"][0][0] == 4 and o["front"][0][1] == 4 and o["front"][0][2] == [[30, 48], [32, 48]] and o["noErrors"], "the front count keeps pins within 75 km and no others: %s" % o["front"])

print("test_173_atlas: %d checks passed" % ok)
