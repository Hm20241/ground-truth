"""Offline tests for 1.7.3: fixes in the Classic page extensions (web/ext/*.js).

Static checks on the extension files, and node runs each changed extension against a stub GTX with SYNTHETIC data
(invented names, coordinates and addresses; nothing is real data). No DOM library, no network.

Run: python3 -I tests/test_173_ext.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
EXT = os.path.join(PROJ, "web", "ext")
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1


def read(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as fh:
        return fh.read()


FILES = sorted(f for f in os.listdir(EXT) if f.endswith(".js"))
SRC = {f: read(f) for f in FILES}

# ---------- static: links ----------
for name, src in SRC.items():
    blank = re.findall(r'<a [^>]*target="_blank"[^>]*>', src)
    check(all('rel="noopener' in a for a in blank), "%s: every new-tab link has rel=noopener" % name)
    # an address from a feed reaches href only through link() / aTag() (http or https only); fixed addresses are literals
    hrefs = re.findall(r'href="\$\{([^}]*)\}', src)
    bad = [h for h in hrefs if not re.match(r"^(esc\((link\([^)]*\)|u)\)|link)$", h.strip())]
    check(not bad, "%s: a feed address is linked only after the http(s) check: %s" % (name, bad))
for name in ("airspace.js", "cyber.js", "hazards.js", "signals.js", "wire.js", "outages.js"):
    check(re.search(r'const link = \(u\) => \(/\^https\?:\\/\\//i\.test\(u \|\| ""\) \? u : null\)', SRC[name]) is not None,
          "%s has the http(s)-only link rule" % name)
for name, src in SRC.items():
    check(not re.search(r"toLocale(Time|Date)?String|\.getHours\(|\.getMinutes\(", src), "%s shows no time in the browser's own zone" % name)
    check("fetch(" not in src and "XMLHttpRequest" not in src, "%s asks the server only through GTX.api" % name)
    check("setInterval(" not in src, "%s starts no timer of its own" % name)

# ---------- static: the fixes ----------
check('((d.by_alert || {}).Orange || 0) + ((d.by_alert || {}).Red || 0)' in SRC["hazards.js"], "the hazards count adds Red when there is no Orange")
check("(n.items || []).map" in SRC["signals.js"], "an active NTAS reply with no list does not stop the Signals tab")
check("r.geojson.features" not in SRC["signals.js"] and "tsunami.geojson.features" not in SRC["signals.js"], "Signals reads map points through the guarded list")
for name in ("wire.js", "cyber.js"):
    check(SRC[name].count("geoT = setTimeout(") == 1 and "if (geoT) return;" in SRC[name], "%s asks for its country points once for two feeds landing together" % name)
check("icoUrl(f.kind, glyph, col)" in SRC["fronts.js"] and SRC["fronts.js"].count(".toDataURL()") == 1, "a front's badge image is drawn once per kind")

NODE = shutil.which("node")
if not NODE:
    print("test_173_ext: %d checks passed (node not found: logic checks skipped)" % ok)
    sys.exit(0)

STUB = r"""
const fs = require("fs");
const NOW = Date.UTC(2026, 10, 24, 12); Date.now = () => NOW;
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const R = { layers: {}, feeds: {}, popups: {}, tabs: {}, streams: {}, render: [], kpis: [], api: [], shown: null, open: {} };
const src = () => ({ setData() {} });
const map = { getSource: src, addSource() {}, addLayer() {}, getLayer: () => null, fitBounds() {}, once() {}, flyTo() {}, getZoom: () => 3 };
const S = { theatre: "global", feeds: {}, status: {}, events: { features: [] } };
const GTX = { S, map, esc, nf: (n) => (n == null ? "–" : Number(n).toLocaleString("en-US")), ago: () => "ago", fmtT: (ms) => { if (!Number.isFinite(ms)) throw new RangeError("Invalid time value"); return "T"; },
  fmtD: () => "D", fmtDay: () => "DAY", when: () => "WHEN", isoMs: (s) => (s ? Date.parse(s) : null), dayMs: () => NOW, country: () => null,
  THEATRES: { t1: ["One", "#fff"] }, below: { events: "ev-halo" }, layerOn: () => true, mapImage() {}, drawGlyph: () => ({ toDataURL: () => { R.glyphs = (R.glyphs || 0) + 1; return "data:,"; } }),
  showPopup(ll, html) { R.shown = html; return { getElement: () => null }; },
  api(p) { R.api.push(p); return Promise.resolve({ type: "FeatureCollection", features: [] }); },
  layer(o) { R.layers[o.key] = o; }, onMapLoad() {}, onRender(fn) { R.render.push(fn); }, popup(id, fn) { R.popups[id] = fn; },
  feed(name, fn) { R.feeds[name] = fn; }, eventSource(name, fn) { R.feeds[name] = fn; }, stream(o) { R.streams[o.key] = o; }, tab(o) { R.tabs[o.id] = o; },
  isOpen: (id) => !!R.open[id], legend() {}, briefColumn() {}, kpi(fn) { R.kpis.push(fn); }, label() {}, credit() {} };
const EL = {};
const el = (id) => EL[id] || (EL[id] = { id, innerHTML: "", dataset: {}, style: {}, classList: { toggle() {}, contains: () => false }, querySelector: () => el(id + ">q"), querySelectorAll: () => [], addEventListener() {}, textContent: "" });
global.window = { GTXQ: [] }; global.document = { getElementById: el, querySelector: () => null, querySelectorAll: () => [], addEventListener() {} };
eval(fs.readFileSync(process.argv[1], "utf8"));
global.window.GTXQ.forEach((fn) => fn(GTX));
"""


def run(name, body):
    res = subprocess.run([NODE, "-e", STUB + body, os.path.join(EXT, name)], capture_output=True, text=True, timeout=60)
    check(res.returncode == 0, "%s: node harness ran: %s" % (name, res.stderr[-800:]))
    return json.loads(res.stdout)


# ---------- fronts: the box shortcut gives the same counts, and a broken overlay is skipped ----------
out = run("fronts.js", r"""
const H = 3600e3; let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const ov = (id, cs, extra) => ({ type: "Feature", geometry: cs ? { type: "LineString", coordinates: cs } : null, properties: Object.assign({ id, kind: "overlay", title: "Frontline " + id, stroke: "#A52714", front_kind: "contact", theatre: "t1" }, extra || {}) });
const lines = { A: [[30, 48], [31, 48.4], [32, 48]], B: [[57, 25], [58, 24]], N: [[20, 69], [24, 70.5]], X: [[178, -17], [179.5, -18]] };
const feats = Object.entries(lines).map(([id, cs]) => ov(id, cs));
feats.push(ov("nogeo", null), ov("onept", [[5, 5]]), { type: "Feature", geometry: { type: "Point", coordinates: [1, 1] }, properties: null });
// pins scattered around every line, many of them close to the 75 km edge
Object.values(lines).forEach((cs, li) => { for (let i = 0; i < 400; i++) { const c = cs[i % cs.length];
  feats.push({ type: "Feature", geometry: { type: "Point", coordinates: [c[0] + (rnd() - 0.5) * 6, c[1] + (rnd() - 0.5) * 3] }, properties: { id: "p" + li + "_" + i, kind: "event", title: "pin", ts_ms: NOW - rnd() * 90 * H, theatre: "t1" } }); } });
S.events = { features: feats };
R.render.forEach((fn) => fn());
const RAD = Math.PI / 180;
const segKm = (p, a, b) => { const k = Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32; const ax = (a[0] - p[0]) * k, ay = (a[1] - p[1]) * 110.57, bx = (b[0] - p[0]) * k, by = (b[1] - p[1]) * 110.57;
  const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L)) : 0; return Math.hypot(ax + t * dx, ay + t * dy); };
const brute = {};
Object.entries(lines).forEach(([id, cs]) => { let n24 = 0, n72 = 0; feats.forEach((f) => { const p = f.properties; if (!p || p.kind !== "event") return;
  let d = Infinity; for (let i = 1; i < cs.length; i++) d = Math.min(d, segKm(f.geometry.coordinates, cs[i - 1], cs[i]));
  if (d <= 75) { if (NOW - p.ts_ms < 24 * H) n24++; if (NOW - p.ts_ms < 72 * H) n72++; } }); brute[id] = [n24, n72]; });
const got = {}; GTX.fronts().forEach((f) => { got[f.id] = [f.n24, f.n72]; });
const g1 = R.glyphs; R.render.forEach((fn) => fn()); R.render.forEach((fn) => fn());
console.log(JSON.stringify({ brute, got, glyphs1: g1, glyphs3: R.glyphs, list: el("frlist").innerHTML.length }));
""")
check(set(out["got"]) == {"A", "B", "N", "X"}, "an overlay with no geometry, one point or no properties is skipped and the other fronts still draw: %s" % sorted(out["got"]))
check(out["got"] == out["brute"], "the box shortcut counts the same pins as checking every pin against every segment: %s vs %s" % (out["got"], out["brute"]))
check(sum(v[1] for v in out["brute"].values()) > 40, "the synthetic pins do fall near the lines (%s)" % out["brute"])
check(out["glyphs1"] == out["glyphs3"] == 1 and out["list"] > 100, "three renders draw the badge image once (one kind on screen), not once per row per render")

# ---------- hazards: count, popup escaping and links ----------
out = run("hazards.js", r"""
const c = (b) => { S.feeds.hazards = b; return R.layers.hazards.count(); };
const counts = [c({ by_alert: { Red: 2 } }), c({ by_alert: { Orange: 3 } }), c({ by_alert: { Red: 1, Orange: 2, Green: 9 } }), c({}), (S.feeds.hazards = null, R.layers.hazards.count())];
R.popups["qk-pt"]({ properties: { mag: "<img src=x>", depth_km: "<b>9</b>", place: "Testplace", time: "2026-11-24T10:00:00Z", url: "javascript:alert(1)", usgs_url: "https://example.org/q", source: "EMSC" } }, [0, 0]);
const qk = R.shown;
R.popups["hz-pt"]({ properties: { type_label: "Flood", alert: "Red", from: "2026-11-23T00:00:00Z", url: "data:text/html,x" } }, [0, 0]);
console.log(JSON.stringify({ counts, qk, hz: R.shown }));
""")
check(out["counts"] == [2, 3, 3, 0, None], "hazards count: Red alone counts (it read 0 before), none is 0, no feed is unknown: %s" % out["counts"])
check("<img" not in out["qk"] and "<b>9</b>" not in out["qk"] and "javascript:" not in out["qk"] and 'href="https://example.org/q"' in out["qk"],
      "the quake popup escapes its figures and links only http(s) addresses")
check("data:text" not in out["hz"] and "GDACS report" not in out["hz"], "the hazard popup drops a link that is not http(s)")

# ---------- signals: malformed replies do not stop the tab ----------
out = run("signals.js", r"""
const tab = el("tab-signals"); let err = "";
const draw = () => { try { R.tabs.signals.render(tab); return tab.innerHTML; } catch (e) { err += String(e) + "; "; return ""; } };
S.feeds = { ntas: { active: true }, tsunami: { items: [{ label: "Wave", source: "PTWC", level: "watch", issued: "2026-11-24T10:00:00Z", url: "javascript:alert(1)" }] },
  radiation: { summary: { network_median_usv: "<i>1</i>" }, geojson: {} }, ofac: { items: [{ title: "Action", url: "ftp://example.org/x", date: "2026-11-23", programs: ["P1"] }] } };
const a = draw();
S.feeds.radiation = { summary: {}, geojson: { features: [null, { properties: { name: "Station", value_usv: "<u>2</u>", ratio: 3, measured: "2026-11-24T10:00:00Z" } }] } };
S.feeds.tsunami = { geojson: { features: [{ properties: {} }, null] } };
const b = draw(), n = R.layers.signals.count();
S.feeds.tsunami = {}; const n0 = R.layers.signals.count();
const rad = R.streams.radiation.items(S.feeds.radiation).length;
R.popups["sg-rad"]({ properties: { name: "Station", id: "1", value_usv: "<u>2</u>", ratio: "<u>3</u>", baseline_usv: 0.1 } }, [0, 0]);
console.log(JSON.stringify({ err, a, b, n, n0, rad, pop: R.shown }));
""")
check(out["err"] == "", "the Signals tab draws with an NTAS reply that has no list and a radiation reply with no points: %s" % out["err"])
check("javascript:" not in out["a"] and "ftp://" not in out["a"] and "Action" in out["a"] and "<i>1</i>" not in out["a"], "Signals links only http(s) addresses and escapes its figures")
check("Station" in out["b"] and "<u>2</u>" not in out["b"], "a flagged station lists with its reading escaped; an empty entry is skipped")
check(out["n"] == 1 and out["n0"] == 0 and out["rad"] == 1, "the Signals count and the radiation Feed rows skip empty entries (%s, %s, %s)" % (out["n"], out["n0"], out["rad"]))
check("<u>" not in out["pop"], "the radiation popup escapes its figures")

# ---------- wire: links, a story with no time, one request for two feeds ----------
out = run("wire.js", r"""
S.feeds.wire = { items: [
  { id: "w1", title: "Bad link story", url: "javascript:alert(1)", theatre: "t1", ts_ms: NOW - 1000, countries: ["AAA"], source_label: "Outlet" },
  { id: "w2", title: "Good story", url: "https://example.org/a", theatre: "t1", countries: ["AAA"], source_label: "Outlet" }], sources: [] };
S.feeds.telegram = { items: [{ id: "t1", kind: "telegram", channel: "chan", title: "Post", url: "tg://resolve?x", theatre: "t1", ts_ms: NOW - 5000, countries: ["AAA"] }], sources: [] };
let err = "";
try { R.popups["nw-pt"]({ properties: { a3: "AAA", name: "Aland" } }, [0, 0]); } catch (e) { err = String(e); }
const pop = R.shown || "";
const tab = el("tab-wire"); R.tabs.wire.render(tab);
const list = el("tab-wire>q").innerHTML;
R.feeds.wire({}); R.feeds.telegram({}); R.feeds.wire({});
setTimeout(() => { const first = R.api.slice(); R.feeds.telegram({}); setTimeout(() => console.log(JSON.stringify({ err, pop, list, first, second: R.api })), 1200); }, 1200);
""")
check(out["err"] == "", "the news popup opens for a story with no time (it threw before): %s" % out["err"])
check("javascript:" not in out["pop"] and "tg://" not in out["pop"] and 'href="https://example.org/a"' in out["pop"] and "Bad link story" in out["pop"],
      "the news popup links only http(s) addresses and still shows the headline")
check("javascript:" not in out["list"] and "tg://" not in out["list"], "the Wire list links only http(s) addresses")
check(out["first"] == ["news_geo"] and out["second"] == ["news_geo", "news_geo"], "three feed landings in a second make one news_geo request; a later one makes the next: %s" % out["second"])

# ---------- cyber: one request for two feeds, links ----------
out = run("cyber.js", r"""
S.feeds.cyber = { items: [{ id: "c1", kind: "kev", title: "Entry", url: "javascript:alert(1)", ts: "2026-11-24T00:00:00Z", cvss: "<b>9</b>" }], infocon: {} };
S.feeds.bgp = { countries: [{ name: "Aland", level: "drop", url: "data:x", pct: {} }] };
const tab = el("tab-cyber"); R.tabs.cyber.render(tab);
R.feeds.cyber({}); R.feeds.bgp({});
setTimeout(() => console.log(JSON.stringify({ html: tab.innerHTML, api: R.api })), 1200);
""")
check(out["api"] == ["cyber_geo"], "the cyber and routing feeds landing together make one cyber_geo request: %s" % out["api"])
check("javascript:" not in out["html"] and "data:x" not in out["html"] and "<b>9</b>" not in out["html"] and "Entry" in out["html"], "the Cyber tab links only http(s) addresses and escapes the score")

# ---------- airspace: popups ----------
out = run("airspace.js", r"""
R.popups["tfr-fill"]({ properties: { notam_id: "1/2345", status: "active", url: "javascript:alert(1)" } }, [0, 0]);
const tfr = R.shown;
R.popups["sq-pt"]({ properties: { squawk: "7700", hex: "abc123", polls: "<b>2</b>", first_seen: "2026-11-24T10:00:00Z" } }, [0, 0]);
const sq = R.shown; let err = "";
global.window.h3 = { cellToLatLng() { throw new Error("bad cell"); } };
try { R.popups["gj-fill"]({ properties: { h3: "zz", level: "high", good: 8, bad: 3 } }, { lat: 10, lng: 20 }); } catch (e) { err = String(e); }
console.log(JSON.stringify({ tfr, sq, err, gj: R.shown }));
""")
check("javascript:" not in out["tfr"] and "FAA notice" not in out["tfr"], "the flight-restriction popup drops a link that is not http(s)")
check("<b>2</b>" not in out["sq"], "the squawk popup escapes its check count")
check(out["err"] == "" and "lat=10.00&lon=20.00" in out["gj"] and "18.2 %" in out["gj"], "the GPS popup opens for a cell h3 cannot read, linking the clicked point")

# ---------- curated: a pin with no properties ----------
out = run("curated.js", r"""
const d = { attribution: "Credit", geojson: { features: [null, { properties: null }, { properties: { kind: "event" } }] } }; let err = "";
try { R.feeds.geoconfirmed(d); } catch (e) { err = String(e); }
S.events = { features: [{ properties: null }, { properties: { kind: "event", source: "cir" } }] };
try { R.render.forEach((fn) => fn()); } catch (e) { err += String(e); }
console.log(JSON.stringify({ err, att: d.geojson.features[2].properties.attribution }));
""")
check(out["err"] == "" and out["att"] == "Credit", "a pin with no properties is skipped and the rest keep their credit: %s" % out["err"])

print("test_173_ext: %d checks passed" % ok)
