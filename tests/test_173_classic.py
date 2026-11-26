"""Offline tests for 1.7.3, Classic theme (web/app.js): the audit fixes.

Static checks on the page file, and node runs the Sea tab's freshness note against stub data (no DOM library, no network).

Run: python3 -I tests/test_173_classic.py
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


with open(os.path.join(PROJ, "web", "app.js"), encoding="utf-8") as fh:
    APP = fh.read()

# ---------- one malformed reply does not stop the load ----------
i0, i1 = APP.index("function loadAll()"), APP.index("function loadExt(")
LOAD = APP[i0:i1]
check('const step = (what, fn) => { try { fn(); } catch (err) { console.error("loadAll: " + what, err); } };' in LOAD, "loadAll applies each reply inside its own try/catch")
for name in ("setShips", "setThermal", "setGdelt", "setGfw", "setPw", "setUkmto"):
    check(re.search(r'step\("[a-z]+", \(\) => (\{ [^;]+; )?%s\(' % name, LOAD) is not None, "loadAll guards " + name)
check('step("render", render);' in LOAD and LOAD.index('step("render", render);') < LOAD.index("Object.keys(EXT.feeds).forEach"), "the redraw is guarded and the extension feeds load after it either way")
for src in ("ships", "thermal", "gdelt"):
    check('map.getSource("%s").setData({ type: "FeatureCollection", features: (d.points || []).map(' % src in APP, src + ": a reply with no points draws nothing instead of throwing")

# ---------- push stream: tried again after it was closed ----------
check("const PUSH_RETRY = 2 * 60000;" in APP and "{ es.close(); setTimeout(startPush, PUSH_RETRY); }" in APP, "a closed push stream is opened again")
check("if (PUBLIC || !window.EventSource) return;" in APP, "the public copy still opens no stream")

# ---------- Sea tab ----------
i0, i1 = APP.index("function shipFreshNote()"), APP.index("function pwTable()")
SEA = APP[i0:i1]
check("el.innerHTML = shipFreshNote() + pwTable() + militaryCard()" in SEA, "the Sea tab opens with how fresh the ships are")
check('st.ok === false || st.stale' in SEA and 'class="stale"' in SEA, "a failed or overdue ship feed is said in plain words")
check('details[open] > summary' in SEA and "x.parentNode.open = true" in SEA, "an opened list stays open over a redraw")
check("(d.items || []).map(" in SEA and "#${esc(i.num)}" in SEA, "UKMTO cards: no items is fine, the number is escaped")
check("if (!a || !a.ring) return;" in SEA, "a traffic card whose area has gone does nothing")
check('data-ship="${esc(c.mmsi)}"' in APP and 'data-ship="${c.mmsi}"' not in APP, "ship rows escape the MMSI")

# ---------- escaping and links ----------
check(re.search(r'target="_blank"(?! rel="noopener")', APP) is None, 'every target="_blank" link has rel="noopener"')
for raw in ("#${p.num}", "${p.frp} MW", "${p.mentions} mentions", "${p.thermal.n} VIIRS", "`#${u.num} ", "#${s.ukmto_latest.num}", "<b>${t.count}</b>", "(${c.n})", "(${h.n})"):
    check(raw not in APP, "feed value no longer written raw: " + raw)
check('String(emU[0].title || "").slice(0, 90)' in APP, "an embassy alert with no title cannot stop the banner")
check('Math.round(p.track) + "°" : "–"' in APP, "an aircraft with no track shows a dash, not NaN")

# ---------- Brief and Sources: a failed call is handled ----------
i0, i1 = APP.index("function renderBrief()"), APP.index("function briefCoverage(")
BRIEF = APP[i0:i1]
check(".catch((err) => {" in BRIEF and "The brief did not load." in BRIEF and "if (!Array.isArray(b.theatres)) b.theatres = [];" in BRIEF, "Brief: a failed or malformed reply leaves a plain line, not a blank tab")
check("const u = linkUrl(h.url)" in BRIEF, "Brief headlines link only http(s) addresses")
i0, i1 = APP.index("function renderSources()"), APP.index("// ---------- 1.0: push ----------")
SRC = APP[i0:i1]
check("The source list did not load." in SRC and SRC.count(".catch(") >= 2, "Sources: both calls are caught")
check("—" not in "".join(re.findall(r"The [a-z' ]+ (?:did not load|feed's last refresh)[^`]*", APP)), "no em dash in the new reader text")

# ---------- node: the freshness note ----------
node = shutil.which("node")
if node:
    fn = APP[APP.index("  let shipNewest = [null, null];"):APP.index("  function renderSea() {")]
    js = r"""
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
const nf = (n) => (n == null ? "–" : Number(n).toLocaleString("en-US"));
const isoMs = (s) => (s ? Date.parse(s) : null);
const when = (t) => "T" + t;
const S = { feeds: {}, status: {} };
""" + fn + r"""
const out = {};
out.none = shipFreshNote();
S.feeds.ships = { count: 3, points: [[0, 0, 0, 0, "x", "A", 1, "2026-11-26T05:00:00Z"], [0, 0, 0, 0, "x", "B", 2, "2026-11-26T05:07:00Z"], [0, 0, 0, 0, "x", "C", 3, null]] };
S.status = { ships: { ok: true, stale: false } };
out.ok = shipFreshNote();
S.status = { ships: { ok: false } };
out.failed = shipFreshNote();
S.status = { ships: { ok: true, stale: true } };
out.late = shipFreshNote();
S.feeds.ships = { count: 0 };
S.status = {};
out.empty = shipFreshNote();
console.log(JSON.stringify(out));
"""
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    check(r.returncode == 0, "node runs the freshness note: " + r.stderr[-300:])
    o = json.loads(r.stdout)
    newest = str(int(__import__("datetime").datetime(2026, 11, 26, 5, 7, tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000))
    check(o["none"] == "" and o["empty"] == "", "no ships feed, or one with no positions and no fault: no note")
    check("3 ships on the map" in o["ok"] and "T" + newest in o["ok"] and "stale" not in o["ok"], "healthy feed: the count and the newest position time")
    check('class="stale"' in o["failed"] and "last refresh failed" in o["failed"] and "T" + newest in o["failed"], "failed feed: a warning with the newest position time")
    check("is overdue" in o["late"], "overdue feed: said as overdue")

print("ok: %d checks" % ok)
