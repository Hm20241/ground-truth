"""Offline tests for 1.7.3, the Watch Floor theme (web/floor.html, web/themes/floor/).

Static checks on the theme's files, and node runs web/themes/floor/core.js against a stub browser (no DOM library,
no network): a reply the page cannot read and a request that never answers must both end as an error and leave the
"loading" set, so the feed is asked for again at the next refresh.

Run: python3 -I tests/test_173_floor.py
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


CORE, MAP, PANELS, BOARD, CSS = (read("web/themes/floor/" + f) for f in ("core.js", "map.js", "panels.js", "board.js", "floor.css"))
JS = CORE + MAP + PANELS + BOARD

# ---------- ships ----------
ships = MAP[MAP.index("    ships() {"):MAP.index("    ukmto() {")]
check('sg = !!l && /[SG]/.test(l.marks || "")' in ships, "a ship is marked only when a list says sanctioned (S) or shadow fleet (G), as Classic's isSG does")
check("listed: sg," in ships and "listed: !!l" not in ships, "the amber mark follows that rule, not 'is on any list' (port detentions are not sanctions)")
check('sg ? " · <b>on a sanctions or shadow-fleet list</b>"' in ships, "only such a ship is worded as sanctioned in its popup")
check('l ? " Lists: "' in ships, "any listed ship still names its lists in the popup")
sea_c = PANELS[PANELS.index("  function seaC()"):PANELS.index("  // ---------- Outages and cyber")]
check("fs && (!fs.ok || fs.stale)" in sea_c and "last good run" in sea_c, "the ships panel says when the ship feed failed or is overdue")
check("a.bbox.map(Number).join" in sea_c, "a sea area's box reaches the page as numbers only")

# ---------- a map view loads what it draws ----------
check("const viewFeeds = (v) => ((WF.VIEWS[v] || {}).feeds || []).map(([f]) => f);" in BOARD, "the feeds behind a map view are read from WF.VIEWS")
check("else if (d.view) { WF.need(viewFeeds(d.view)); WF.setView(d.view);" in BOARD, "picking a map view asks for that view's feeds (Sea on another board drew no ships)")
check("...B[S.board].need, ...viewFeeds(S.view)" in BOARD, "the two-minute refresh covers the view on screen as well as the board")
views = dict(re.findall(r'^    (\w+): \{ name: "[^"]+", pins: .*?, feeds: (\[\[.*?\]\]), legend', MAP, re.M))
check(set(views) == {"conflict", "air", "sea", "outages", "hazards", "advisories"}, "six map views, each naming its feeds (%s)" % sorted(views))
check(all(n in views["sea"] for n in ('"ships"', '"ukmto"', '"portwatch"')), "the Sea view names ships, incidents at sea and chokepoints")

# ---------- hardening ----------
check("if (![lon, lat, z].every(Number.isFinite)) return;" in BOARD, "a row with no position does nothing when pressed")
check('data-fly="${+ll[0]},${+ll[1]},${+z || 5}"' in PANELS, "a row's position reaches the page as numbers only")
check('lost ? "amber"' in BOARD and '"No feed status since "' in BOARD, "the feed light says when the status stopped answering")
check("No feed status since ${esc(lostAt)}" in BOARD, "the Systems panel says it too (the wall view shows no light)")
check("dirty.add(name)" in BOARD and "function render() { flushMap();" in BOARD, "map sources are rebuilt once a frame, before the page is drawn")
check(re.search(r"html\.wall \{ font-size: max\(16px, 1\.146vw\); \}", CSS) is not None, "wall view type never drops under the page's 16 px base")
sizes = [float(x) for x in re.findall(r"font(?:-size)?:[^;{}]*?(?<![\d.])(\d*\.\d+|\d+)rem", CSS)]
check(sizes and min(sizes) >= 0.875, "no type under 0.875 rem (14 px) in floor.css (smallest %s rem)" % (min(sizes) if sizes else "?"))
check(re.search(r"font(?:-size)?:[^;{}]*?(?<![\d.])(?:[0-9]|1[0-3])(?:\.\d+)?px", CSS) is None, "no type set under 14 px in floor.css")
blank = JS.count('target="_blank"')
check(blank and blank == JS.count('target="_blank" rel="noopener"'), "every link that opens a new tab has rel=noopener (%d)" % blank)
check("—" not in re.sub(r"/\*.*?\*/|//[^\n]*", "", JS, flags=re.S), "no em dash in text a reader sees")

# ---------- behaviour: node runs core.js against a stub browser ----------
node = shutil.which("node")
check(node is not None, "node is installed (needed for the behaviour checks)")
HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");
const timers = [];
const replies = {};   // path -> "hang" | {status, body} ; default 200 {}
const asked = [];
const win = { addEventListener() {}, AbortController };
const ctx = { window: win, document: { getElementById: () => null, addEventListener() {}, hidden: false }, localStorage: { getItem: () => null, setItem() {} },
  location: { search: "" }, URLSearchParams, Intl, Date, Math, Number, JSON, Promise, Map, Set, Object, Array, String, Error, TypeError, console, AbortController,
  requestAnimationFrame: () => 1, clearTimeout: (i) => { if (timers[i]) timers[i].off = true; }, setTimeout: (fn, ms) => timers.push({ fn, ms }) - 1,
  fetch: (url, opt) => { asked.push(url); const r = replies[url];
    if (r === "hang") return new Promise((_, rej) => { opt.signal.addEventListener("abort", () => { const e = new Error("aborted"); e.name = "AbortError"; rej(e); }); });
    const rr = r || { status: 200, body: "{}" };
    return Promise.resolve({ ok: rr.status === 200, status: rr.status, json: () => Promise.resolve(JSON.parse(rr.body)) }); } };
vm.runInNewContext(src, ctx);
const WF = win.WF, tick = () => new Promise((r) => setImmediate(r));
const state = (n) => ({ loading: WF.LOADING.has(n), err: WF.ERR[n] || null, have: n in WF.D });
(async () => {
  const out = {};
  replies["api/status"] = { status: 200, body: JSON.stringify({ now: "2026-11-26T05:00:00Z", feeds: { ships: { ok: true }, wire: { ok: true } } }) };
  replies["api/feed/ships"] = { status: 502, body: "{}" };
  WF.load("ships"); out.heldBeforeStatus = asked.length === 0 && WF.held() === 1;
  await WF.load("status"); await tick(); await tick();
  out.askedAfterStatus = asked.slice();
  out.notListed = (await WF.load("telegram"), asked.includes("api/feed/telegram"));
  // a reply the page cannot read
  replies["api/feed/ships"] = { status: 200, body: "null" };
  await WF.load("ships"); out.unreadable = state("ships");
  // an HTTP error
  replies["api/feed/ships"] = { status: 502, body: "{}" };
  await WF.load("ships"); out.http = state("ships");
  // a request that never answers: the page's own 60 s timer gives up on it
  replies["api/feed/ships"] = "hang";
  const p = WF.load("ships"); await tick();
  out.hungLoading = WF.LOADING.has("ships");
  const t = timers.filter((x) => !x.off).pop(); out.timerMs = t.ms; t.fn(); await p;
  out.hung = state("ships");
  // and it recovers
  replies["api/feed/ships"] = { status: 200, body: JSON.stringify({ ok: false, error: "TimeoutError", data: { count: 2, points: [[1, 2], [3, 4]] } }) };
  await WF.load("ships"); out.recovered = state("ships"); out.count = WF.D.ships.count;
  out.liveTimers = timers.filter((x) => !x.off).length;
  // times: Eastern am/pm by default, UTC on request
  out.et = WF.fmtT(Date.UTC(2026, 10, 26, 5, 8, 5)); out.etSecs = WF.fmtT(Date.UTC(2026, 6, 4, 17, 0, 9), true);
  WF.setZone("utc"); out.utc = WF.fmtT(Date.UTC(2026, 10, 26, 5, 8, 5)); WF.setZone("et");
  out.ago = [WF.ago(Date.now() - 17 * 60000), WF.ago(Date.now() - 125 * 60000), WF.ago(NaN)];
  console.log(JSON.stringify(out));
})();
"""
r = subprocess.run([node, "-e", HARNESS, "--", os.path.join(PROJ, "web/themes/floor/core.js")], capture_output=True, text=True, timeout=60)
check(r.returncode == 0, "the node harness runs (%s)" % r.stderr.strip()[-300:])
o = json.loads(r.stdout)
check(o["heldBeforeStatus"], "a feed is not asked for before the status has answered")
check("api/feed/ships" in o["askedAfterStatus"], "a held feed is asked for once the status lists it")
check(o["notListed"] is False, "a feed the status does not list is never asked for")
check(o["unreadable"] == {"loading": False, "err": "the reply could not be read", "have": False}, "a reply the page cannot read is an error in plain words and leaves the loading set (%s)" % o["unreadable"])
check(o["http"] == {"loading": False, "err": "HTTP 502", "have": False}, "an HTTP error is reported and leaves the loading set")
check(o["hungLoading"] is True and o["timerMs"] == 60000, "a request with no answer is given 60 seconds")
check(o["hung"] == {"loading": False, "err": "no answer in 60 s", "have": False}, "after that it is an error and leaves the loading set (%s)" % o["hung"])
check(o["recovered"] == {"loading": False, "err": None, "have": True} and o["count"] == 2, "the next good reply clears the error, and a feed marked failing still gives its last ships")
check(o["liveTimers"] == 0, "every request clears its own timer")
check(o["et"] == "12:08 AM" and o["etSecs"] == "1:00:09 PM", "times show as am/pm Eastern by default, winter and summer (%s, %s)" % (o["et"], o["etSecs"]))
check(o["utc"] == "05:08Z", "UTC on request")
check(o["ago"] == ["17 min ago", "2 h 5 min ago", "–"], "time-since wording (%s)" % o["ago"])

print("test_173_floor: %d checks passed" % ok)
