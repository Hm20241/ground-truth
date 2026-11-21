"""Offline tests for 1.3.0: times in Eastern time by default, UTC on request, and the time since (GTX API 1.3).

  python3 -I tests/test_130_tz.py

Behaviour: node runs app.js's own zone helpers (the block between "--- zone helpers" and "--- end zone helpers",
plus isoMs) at fixed times: EST and EDT, both 2026 DST switches, midnight and noon, date-only values, future times,
naive ISO strings, the activity-chart ticks, the tooltips, and a browser whose storage throws.
Static: the page, the header clock and the rail's Times chips, guarded storage, the redraw on a switch, no UTC-only
formats left, the extensions' when(), versions.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
read = lambda p: open(os.path.join(ROOT, p), encoding="utf-8").read()
fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)
        print("FAIL:", what)


APP, IDX, CSS, VERSION = read("web/app.js"), read("web/index.html"), read("web/style.css"), read("VERSION").strip()
EXT = {f: read("web/ext/" + f) for f in ("airspace.js", "hazards.js", "signals.js", "cyber.js", "wire.js")}

# ---------- static ----------
check(tuple(map(int, VERSION.split("."))) >= (1, 3, 0), "VERSION is 1.3.0 or later (%s)" % VERSION)  # 1.4.0: later releases keep 1.3.0's zones
check(re.search(r'version: "1\.([3-9]|\d\d)"', APP) is not None and "fmtDay, when, ago" in APP and "zone: () => ZONE" in APP, "GTX API 1.3 exposes when, fmtDay and zone()")
local = re.findall(r'(?:src|href)="((?:ext/|app\.js|style\.css)[^"]*)"', IDX)  # files, not the data: favicon
check(local and all(u.endswith("?v=" + VERSION) for u in local), "every local asset is cache-busted with ?v=" + VERSION)
check("geo/theatres.json?v=" + VERSION in APP, "theatres.json fetched with ?v=" + VERSION)
check(re.search(r'<button type="button" class="clock" id="clock"><span id="utc">[^<]*</span><small id="clockz">', IDX),
      "header clock is a button with the time (#utc) and the other zone (#clockz)")
check('id="tzchips"' in IDX and 'data-tz="et"' in IDX and 'data-tz="utc"' in IDX and 'role="group"' in IDX.split('id="tzchips"')[1][:200],
      "rail has a labelled Times group with Eastern and UTC chips (the clock is hidden on phones)")
check("button.clock" in CSS and "focus-visible" in CSS.split("1.3.0: the clock is a button")[1], "clock button styles with a focus ring")
a, b = APP.index("// --- zone helpers"), APP.index("// --- end zone helpers")
BLOCK, REST = APP[a:b], APP[:a] + APP[b:]
check("try { return localStorage.getItem(\"gt-tz\")" in BLOCK and "catch (e) { return \"et\"; }" in BLOCK, "stored zone is read in a try, default Eastern")
check(re.search(r'try \{ localStorage\.setItem\("gt-tz", ZONE\); \} catch', APP), "zone is saved in a try")
check(re.search(r"function setZone\(z\) \{[\s\S]{0,300}?zoneUi\(\); tick\(\); rezone\(\);\s*\}", APP), "switching redraws (zoneUi, tick, rezone)")
rz = APP[APP.index("function rezone()"):APP.index("function setZone(")]
check(all(k in rz for k in ("run(render,", "renderBanner", "ext.render(", "renderAlerts", "feedSoon")), "rezone redraws the map, Feed and its notice (render), banner, open tab")
check(all(f in rz for f in ("try {", "catch (err)")), "each redraw step is guarded")
check('$("clock").onclick' in APP and '$("tzchips").onclick' in APP, "clock and chips switch the zone")
check(not re.search(r"\)\}Z|\.slice\(5, ?16\)\.replace\(\"T\"", REST.replace('${utc.slice(11, 16)}Z', "")), "no UTC-only time formats left in app.js")
check("Kyiv times shown in UTC" not in APP and "Kyiv times shown in ${zoneName()}" in APP, "Alerts note names the page's zone")
check(('data-ts="${p.ts_source === "date" ? dayStart(p.ts_ms) : p.ts_ms}"' in APP or 'data-ts="${day ? dayStart(p.ts_ms) : p.ts_ms}"' in APP) and 'data-ts="${i.day ? dayStart(i.ts) : i.ts}"' in APP, "Feed rows carry data-ts")
check("i.day ? fmtDay(i.ts)" in APP and 'p.ts_source === "date" ? fmtDay(p.ts_ms)' in APP, "date-only Feed rows show their own day")
check('title="${esc(altTime(' in APP, "Feed times show the other zone as a tooltip")
check("axisLabel(b.t)" in APP and "getUTCHours() % 12" not in REST, "activity chart ticks follow the zone")
check(not any("(?<" in x for x in [APP] + list(EXT.values())), "no regex lookbehind (older iOS WebViews reject the whole file)")
check("zText(nd.nodeValue, ref)" in APP and "esc(zText(a.summary, isoMs(a.analyzed_at)))" in APP, "Analyst tab and per-event notes get Eastern beside UTC times")
rz2 = APP[APP.index("function rezone()"):APP.index("function setZone(")]
check(rz2.index("STREAMS.forEach((st) => { st._d = null; })") < rz2.index("run(render"), "a switch rebuilds the Feed's cached rows before redrawing (TFR spans carry times)")
check("const start = i.day ? dayStart(i.ts) : i.ts, end = i.day ? dayStart(i.ts + DAY) : i.ts;" in APP and "start > S.brush[1]" in APP, "Feed filter: a date-only item spans its day in the page's zone")
check("ts: i.day ? dayStart(i.ts) : i.ts, group: i.group" in APP and 'f.properties.ts_source === "date" && f.properties.ts_ms ? dayStart(f.properties.ts_ms)' in APP, "Feed sort: date-only rows at the start of their day in the page's zone")
check('data-ts="${i.day ? dayStart(i.ts) : i.ts}"' in APP, "date-only rows' data-ts is where they sort")
check("first ${esc(when(p.thermal.first))}" in APP and "watching_since.slice" not in APP, "thermal first detection and advisories date follow the zone")
check("zText(a.summary, isoMs(a.analyzed_at))" in APP, "per-event analyst notes use the note's own date for the offset")
check("zoneUi()" in APP and '$("utc").title = "Live' not in APP, "push state goes into the clock tooltip")
for f in ("airspace.js", "hazards.js", "signals.js", "cyber.js"):
    check("const when = (v, rel) => GTX.when(v, rel);" in EXT[f], f + ": when() is GTX.when (zone + time since)")
    check(not re.search(r"\)\}Z|toISOString\(\)\.slice", EXT[f]), f + ": no UTC-only formats")
check("when(v, false)" in EXT["hazards.js"] and "span(p, p.to)" in EXT["hazards.js"], "hazards: from/to spans leave out the time since")
check("when(p.effective, false)" in EXT["airspace.js"] and "when(p.expires, false)" in EXT["airspace.js"], "airspace: TFR span leaves out the time since")
check("fmtD(ms)} ${fmtT(ms)} · ${ago(ms)}" in EXT["wire.js"], "wire: unchanged, already zone-following with the time since")

# ---------- behaviour (node runs the page's own helpers) ----------
prose_py = "red at 05:38Z, up from 13 at 03:04Z (to 00:23Z). Not 12:05:38Z, 25:00Z or 0538Z."
NODE = shutil.which("node")
check(bool(NODE), "node is installed")
iso_line = re.search(r"  const isoMs = .*", APP).group(0)
harness = r"""
const BLOCK = %s, ISO = %s;
const NOW = Date.UTC(2026, 10, 20, 6, 12);  // 2026-11-20 06:12Z = 1:12 AM EST
Date.now = () => NOW;
function make(store) {
  const localStorage = store;
  return eval("(() => {" + ISO + "\n" + BLOCK + "return { fmtT, fmtD, fmtDay, when, ago, altTime, axisLabel, zoneAbbr, zoneName, isoMs, zText, dayStart, z: () => ZONE, set: (v) => { ZONE = v; } }; })()");
}
const mem = (v) => ({ getItem: () => v });
const out = {};
const P = make(mem(null)), T = (s) => Date.parse(s);
out.defaultZone = P.z();
out.throwsZone = make({ getItem() { throw new Error("SecurityError"); } }).z();
out.utcStored = make(mem("utc")).z();
out.junkStored = make(mem("ET")).z();
const t = T("2026-11-20T03:12:00Z");
out.et = [P.fmtD(t), P.fmtT(t), P.zoneAbbr(t), P.zoneName()];
out.summer = [P.fmtD(T("2026-07-01T16:05:00Z")), P.fmtT(T("2026-07-01T16:05:00Z")), P.zoneAbbr(T("2026-07-01T16:05:00Z"))];
out.midnight = [P.fmtD(T("2026-11-20T05:00:00Z")), P.fmtT(T("2026-11-20T05:00:00Z"))];
out.noon = P.fmtT(T("2026-11-20T17:00:00Z"));
out.dstStart = [P.fmtT(T("2026-03-08T06:59:00Z")), P.zoneAbbr(T("2026-03-08T06:59:00Z")), P.fmtT(T("2026-03-08T07:00:00Z")), P.zoneAbbr(T("2026-03-08T07:00:00Z"))];
out.dstEnd = [P.fmtT(T("2026-11-01T05:30:00Z")), P.zoneAbbr(T("2026-11-01T05:30:00Z")), P.fmtT(T("2026-11-01T06:30:00Z")), P.zoneAbbr(T("2026-11-01T06:30:00Z"))];
out.dayEt = [P.fmtDay("2026-11-19"), P.fmtDay(Date.UTC(2026, 10, 19)), P.when("2026-11-19")];
out.whenEt = [P.when(t), P.when(t, false), P.when("2026-11-20T03:12:00Z"), P.when(null), P.when(""), P.when("garbage")];
out.naive = [P.isoMs("2026-11-20T03:12:00") === t, P.isoMs("2026-11-20T03:12") === T("2026-11-20T03:12:00Z"), P.isoMs("2026-11-19T22:12:00-05:00") === t, P.isoMs("2026-11-19") === Date.UTC(2026, 10, 19)];
out.ago = [P.ago(NOW - 20000), P.ago(NOW - 45 * 60000), P.ago(NOW - 90 * 60000), P.ago(NOW - 3 * 86400000), P.ago(NOW + 2 * 3600000), P.ago(NOW + 20 * 60000), P.ago(NOW + 20000)];
out.axisEt = [P.axisLabel(T("2026-11-20T05:00:00Z")), P.axisLabel(T("2026-11-20T17:00:00Z")), P.axisLabel(T("2026-11-20T06:00:00Z")), P.axisLabel(T("2026-11-20T00:00:00Z"))];
out.altEt = P.altTime(t);
const U = (y, m, d, h) => Date.UTC(y, m - 1, d, h || 0);
out.dayStartEt = [[2026, 11, 20], [2026, 7, 1], [2026, 3, 8], [2026, 3, 9], [2026, 11, 1], [2026, 11, 2], [2027, 1, 1]].map(([y, m, d]) => (P.dayStart(U(y, m, d)) - U(y, m, d)) / 3600000);
out.dayStartNoon = (P.dayStart(U(2026, 11, 15, 12)) - U(2026, 11, 15)) / 3600000;
out.fmtDaySlash = [P.fmtDay("2026/11/20"), P.fmtDay("2026-11-20"), P.fmtDay(U(2026, 11, 20))];
const prose = "red at 05:38Z, up from 13 at 03:04Z (to 00:23Z). Not 12:05:38Z, 25:00Z or 0538Z.";
out.zEt = [P.zText(prose, T("2026-11-20T09:00:00Z")), P.zText("at 16:05Z", T("2026-07-01T18:00:00Z")), P.zText(""), P.zText(null)];
P.set("utc");
out.utc = [P.fmtD(t), P.fmtT(t), P.zoneAbbr(t), P.zoneName(), P.when(t), P.fmtDay("2026-11-19")];
out.axisUtc = [P.axisLabel(T("2026-11-20T00:00:00Z")), P.axisLabel(T("2026-11-20T12:00:00Z")), P.axisLabel(T("2026-11-20T05:00:00Z"))];
out.altUtc = P.altTime(t);
out.dayStartUtc = P.dayStart(U(2026, 11, 20)) === U(2026, 11, 20) && P.dayStart(U(2026, 11, 20, 12)) === U(2026, 11, 20);
out.zUtc = P.zText(prose, T("2026-11-20T09:00:00Z"));
console.log(JSON.stringify(out));
""" % (json.dumps(BLOCK), json.dumps(iso_line))
r = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, timeout=60) if NODE else None
o = json.loads(r.stdout) if r and r.returncode == 0 and r.stdout.strip() else {}
check(bool(o), "node harness ran" + ("" if o else ": " + ((r.stderr if r else "") or "")[:300]))
if o:
    check(o["defaultZone"] == "et", "default zone is Eastern")
    check(o["throwsZone"] == "et", "storage that throws (private window) still gives Eastern")
    check(o["utcStored"] == "utc" and o["junkStored"] == "et", "a saved 'utc' is kept; anything else reads as Eastern")
    check(o["et"] == ["11/19", "10:12 PM", "EST", "Eastern time"], "03:12Z on 11/20 shows as 11/19 10:12 PM EST: %s" % o["et"])
    check(o["summer"] == ["07/01", "12:05 PM", "EDT"], "16:05Z on 7/1 shows as 12:05 PM EDT: %s" % o["summer"])
    check(o["midnight"] == ["11/20", "12:00 AM"] and o["noon"] == "12:00 PM", "midnight and noon: %s %s" % (o["midnight"], o["noon"]))
    check(o["dstStart"] == ["1:59 AM", "EST", "3:00 AM", "EDT"], "2026-03-08 spring forward: %s" % o["dstStart"])
    check(o["dstEnd"] == ["1:30 AM", "EDT", "1:30 AM", "EST"], "2026-11-01 fall back: %s" % o["dstEnd"])
    check(o["dayEt"] == ["11/19", "11/19", "11/19"], "a date-only value stays its own day in Eastern: %s" % o["dayEt"])
    check(o["whenEt"] == ["11/19 10:12 PM · 3h ago", "11/19 10:12 PM", "11/19 10:12 PM · 3h ago", "–", "–", "–"], "when(): %s" % o["whenEt"])
    check(all(o["naive"]), "isoMs: no-zone times are UTC, offsets and dates as before: %s" % o["naive"])
    check(o["ago"] == ["just now", "45m ago", "2h ago", "3d ago", "in 2h", "in 20m", "just now"], "ago(), past and future: %s" % o["ago"])
    check(o["axisEt"] == ["11/20", "noon", "", ""], "Eastern chart ticks: midnight date, noon: %s" % o["axisEt"])
    check(o["altEt"] == "11/20 03:12Z", "Eastern tooltip shows UTC: %s" % o["altEt"])
    check(o["utc"] == ["11/20", "03:12Z", "UTC", "UTC", "11/20 03:12Z · 3h ago", "11/19"], "UTC mode: %s" % o["utc"])
    check(o["axisUtc"] == ["11/20 00Z", "11/20 12Z", ""], "UTC chart ticks: %s" % o["axisUtc"])
    check(o["altUtc"] == "11/19 10:12 PM EST", "UTC tooltip shows Eastern: %s" % o["altUtc"])
    check(o["zEt"][0] == "red at 05:38Z (12:38 AM), up from 13 at 03:04Z (10:04 PM) (to 00:23Z (7:23 PM)). Not 12:05:38Z, 25:00Z or 0538Z.",
          "analyst prose: Eastern beside each HH:MMZ, others left alone: %s" % o["zEt"][0])
    check(o["zEt"][1] == "at 16:05Z (12:05 PM)" and o["zEt"][2] == "" and o["zEt"][3] is None, "analyst prose: EDT offset in summer, empty passes: %s" % o["zEt"][1:])
    check(o["zUtc"] == prose_py, "analyst prose untouched in UTC mode")
    check(o["dayStartEt"] == [5, 4, 5, 4, 4, 5, 5], "dayStart: Eastern midnight is 05:00Z in winter, 04:00Z in summer, right on both 2026 DST days and across New Year: %s" % o["dayStartEt"])
    check(o["dayStartUtc"], "dayStart is UTC midnight in UTC mode, for a midnight or noon date stamp")
    check(o["dayStartNoon"] == 5, "dayStart: a date-only value stamped at noon UTC (GeoConfirmed) starts its day at Eastern midnight: %s" % o["dayStartNoon"])
    check(o["fmtDaySlash"] == ["11/20", "11/20", "11/20"], "fmtDay reads a YYYY/MM/DD date as that day: %s" % o["fmtDaySlash"])
    # the page must not depend on the browser's own zone: same output with the machine in Chicago and in Kolkata
    env = dict(os.environ)
    runs = []
    for tz in ("America/Chicago", "Asia/Kolkata"):
        env["TZ"] = tz
        rr = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, timeout=60, env=env)
        runs.append(rr.stdout.strip() if rr.returncode == 0 else "ERR " + rr.stderr[:200])
    check(runs[0] == runs[1] == r.stdout.strip() and not runs[0].startswith("ERR"), "same output whatever the browser's own time zone (Chicago, Kolkata)")

EXT_HARNESS = r"""
const fs = require("fs"), vm = require("vm"), path = require("path");
const dir = process.argv[1], FX = JSON.parse(process.argv[2]);
const noop = () => {}, el = () => null;
globalThis.window = globalThis;
globalThis.document = { addEventListener: noop, getElementById: el, querySelector: el, querySelectorAll: () => [], createElement: () => ({ style: {} }) };
const isoMs = (s) => (s ? Date.parse(s) : null);
const streams = [];
const GTX = { version: "1.3", map: { getSource: el, loaded: () => false }, S: { feeds: {}, events: null }, api: () => Promise.resolve(null),
  esc: (s) => String(s), fmtT: () => "T", fmtD: () => "D", fmtDay: () => "DAY", when: () => "WHEN", ago: () => "", nf: (n) => String(n), isoMs,
  showPopup: noop, THEATRES: {}, CATS: {}, below: {}, country: () => null, dayMs: () => null, zone: () => "et", layer: noop, onMapLoad: noop,
  legend: noop, briefColumn: noop, popup: noop, feed: noop, eventSource: noop, tab: noop, isOpen: () => false, label: noop, credit: noop,
  kpi: noop, onRender: noop, refresh: noop, layerOn: () => false, stream: (o) => streams.push(o) };
for (const f of ["hazards", "cyber"]) vm.runInThisContext(fs.readFileSync(path.join(dir, f + ".js"), "utf8"), { filename: f + ".js" });
(window.GTXQ || []).forEach((fn) => fn(GTX));
GTX.S.feeds = FX;
const out = {};
for (const st of streams.filter((x) => x.key === "cyber" || x.key === "hazards")) out[st.key] = st.items(st.data()).map((i) => [i.id, !!i.day]);
process.stdout.write(JSON.stringify(out));
"""
EFX = {"cyber": {"items": [
    {"id": "kev:CVE-1", "kind": "kev", "title": "CVE-1", "url": "https://x/1", "ts": "2026-11-18T00:00:00Z"},
    {"id": "atk:1", "kind": "attack", "title": "Attack", "url": "https://x/2", "ts": "2026-11-20T00:00:00Z", "ts_ms": 1795132800000},
    {"id": "rw:1", "kind": "ransom", "title": "Claim", "url": "https://x/3", "ts": "2026-11-20T00:00:00Z"},
    {"id": "kev:CVE-2", "kind": "kev", "title": "CVE-2", "url": "https://x/4", "ts": "2026-11-18T09:30:00Z"}]},
  "hazards": {"geojson": {"features": [
    {"geometry": {"type": "Point", "coordinates": [10, 10]}, "properties": {"id": "DR1", "type": "DR", "from": "2025-12-21T00:00:00Z", "to": "2026-11-18T00:00:00Z"}},
    {"geometry": {"type": "Point", "coordinates": [10, 10]}, "properties": {"id": "WF1", "type": "WF", "from": "2026-11-19T00:00:00Z", "to": "2026-11-20T00:00:00Z"}},
    {"geometry": {"type": "Point", "coordinates": [10, 10]}, "properties": {"id": "EQ1", "type": "EQ", "from": "2026-11-20T00:00:00Z", "to": "2026-11-20T00:00:00Z"}},
    {"geometry": {"type": "Point", "coordinates": [10, 10]}, "properties": {"id": "FL1", "type": "FL", "from": "2026-11-10T00:00:00Z", "to": "2026-11-20T06:12:00Z"}}]}}}
er = subprocess.run([NODE, "-e", EXT_HARNESS, os.path.join(ROOT, "web", "ext"), json.dumps(EFX)], capture_output=True, text=True, timeout=60) if NODE else None
eo = json.loads(er.stdout) if er and er.returncode == 0 and er.stdout.strip() else {}
check(bool(eo), "extension stream harness ran" + ("" if eo else ": " + ((er.stderr if er else "") or "")[:300]))
if eo:
    check(eo.get("cyber") == [["cy:kev:CVE-1", True], ["cy:atk:1", True], ["cy:rw:1", False], ["cy:kev:CVE-2", False]],
          "cyber: KEV and press-attack dates (UTC midnight) are date-only rows; claims and timed entries are not: %s" % eo.get("cyber"))
    check(eo.get("hazards") == [["gd:DR1", True], ["gd:WF1", True], ["gd:EQ1", False], ["gd:FL1", False]],
          "GDACS: droughts and wildfires (dates only) are date-only rows; quakes and floods are not: %s" % eo.get("hazards"))
check("GTX.fmtDay(i.ts_ms || i.ts) : when(i.ts)" in EXT["cyber.js"] and "From ${span(p, p.from)}" in EXT["hazards.js"], "Cyber tab and GDACS popup show those dates as days")

print("%d checks passed" % (n - len(fails)) if not fails else "%d of %d checks FAILED" % (len(fails), n))
sys.exit(1 if fails else 0)
