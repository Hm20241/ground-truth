"""Offline tests for 1.6.0: battle fronts and source-map pin icons.

Server side (gt/mymaps.py): the icon table names every My Maps code after the map's own icon file, and a line
overlay gets front_kind by the map's legend (red line = front, yellow = supposed front). Page side: static checks
on the page files, and node runs web/ext/fronts.js against a stub GTX with SYNTHETIC lines and pins (invented
names and coordinates; nothing is real data). No network.

Run: python3 -I tests/test_160_fronts.py
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import mymaps  # noqa: E402

# ---------- icon table ----------
NAMES = {"1830": "megaphone", "1571": "fire", "1504": "plane", "1657": "officer", "1722": "truck", "1812": "gunner",
         "1569": "ship", "1864": "wreck", "1556": "skull", "1528": "bridge", "1593": "helicopter", "1716": "train",
         "1660": "bolt"}
check(set(mymaps.ICONS) == set(NAMES), "the icon table covers exactly the 13 codes the map uses")
for code, glyph in NAMES.items():
    cat, label, g = mymaps.ICONS[code]
    check(g == glyph, "icon %s draws %s" % (code, glyph))
    check(cat in mymaps.CATEGORIES and label and label != "Other", "icon %s has a real category and label" % code)
check(mymaps.ICONS["1569"][0] == "maritime", "the ferry icon is maritime (was Other before 1.6.0)")
check(mymaps.ICONS["1528"][1] == "Bridge", "the bridge icon is labelled Bridge (was Other before 1.6.0)")

# ---------- front_kind ----------
RED, YEL, BLUE, BLACK = "#A52714", "#FFD600", "#01579B", "#000000"
fk = mymaps.front_kind
check(fk("Frontline", RED, "frontline", 135) == "contact", "a red line named Frontline is a contact front")
check(fk("Russian front", RED, "frontline", 7) == "contact", "Russian front is a contact front")
check(fk("Blockade line", RED, "zone", 2) == "blockade", "a 2-point red blockade line is a blockade front")
check(fk("Island Defense Chain", RED, "zone", 15) == "defense", "a red defence chain is a defence line")
check(fk("Air defense perimeter", RED, "zone", 5) == "defense", "a red perimeter is a defence line")
check(fk("Anything", YEL, "other", 4) == "supposed", "a yellow line is a supposed front (the map's legend)")
check(fk("some red line", RED, "other", 6) == "contact", "an unnamed red line with 3+ points is a front")
check(fk("stub", RED, "other", 2) is None, "an unnamed 2-point red stub is not a front")
check(fk("knocked Out", RED, "damage", 2) is None, "a red damage marker is not a front")
check(fk("Bridge", RED, "bridge", 4) is None, "a red bridge span is not a front")
check(fk("NATO/RU Border", BLUE, "border", 10) is None, "a blue border is not a front")
check(fk("Rebel Controlled Area", BLACK, "frontline", 8) is None, "a black line is not a front by the legend")
check(fk("Frontline", "#a52714", "frontline", 9) == "contact", "the colour compare ignores case")
check(fk("Frontline", None, "frontline", 9) is None, "no stroke, no front")

# ---------- parse(): a synthetic KML ----------
def pm(name, style, geom, desc=""):
    return "<Placemark><name>%s</name><description><![CDATA[%s]]></description><styleUrl>#%s</styleUrl>%s</Placemark>" % (name, desc, style, geom)


def line(pts):
    return "<LineString><coordinates>%s</coordinates></LineString>" % " ".join("%s,%s,0" % p for p in pts)


def poly(pts):
    return "<Polygon><outerBoundaryIs><LinearRing><coordinates>%s</coordinates></LinearRing></outerBoundaryIs></Polygon>" % " ".join("%s,%s,0" % p for p in pts)


def point(x, y):
    return "<Point><coordinates>%s,%s,0</coordinates></Point>" % (x, y)


POST = "https://x.com/example/status/%d"
KML = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Test Map Day 9</name>'
       + pm("Frontline", "line-A52714-5650-nodesc", line([(30, 48), (31, 48), (32, 48.5)]))
       + pm("Blockade line", "line-A52714-1970-nodesc", line([(57, 25), (58, 24)]))
       + pm("Maybe front", "line-FFD600-3000-nodesc", line([(10, 10), (11, 10), (12, 10)]))
       + pm("Damaged", "line-A52714-6420-nodesc", line([(36, 45), (36.01, 45)]))
       + pm("NATO/RU Border", "line-01579B-4290-nodesc", line([(24, 55), (25, 56), (26, 57)]))
       + pm("Destroyed", "poly-A52714-2600-189-nodesc", poly([(37, 47), (37.1, 47), (37.1, 47.1), (37, 47)]))
       + pm("convoy escort", "icon-1569-A52714", point(20, 32), POST % 2123514985724932298)
       + pm("dang", "icon-1528-097138", point(36.5, 45.3), POST % 2123514985724932299)
       + pm("moving", "icon-1716-097138", point(33, 49), POST % 2123514985724932300)
       + pm("mystery", "icon-1999-097138", point(33, 50), POST % 2123514985724932301)
       + "</Document></kml>").encode()
fc = mymaps.parse(KML)
by = {f["properties"]["title"]: f["properties"] for f in fc["features"]}
check(by["Frontline"].get("front_kind") == "contact", "parse: Frontline carries front_kind contact")
check(by["Blockade line"].get("front_kind") == "blockade", "parse: Blockade line carries front_kind blockade")
check(by["Maybe front"].get("front_kind") == "supposed", "parse: a yellow line carries front_kind supposed")
for name in ("Damaged", "NATO/RU Border", "Destroyed"):
    check("front_kind" not in by[name], "parse: %s has no front_kind" % name)
check(by["Frontline"]["overlay_type"] == "frontline" and by["Blockade line"]["overlay_type"] == "zone", "parse: overlay_type is unchanged")
check(by["convoy escort"]["glyph"] == "ship" and by["convoy escort"]["category"] == "maritime", "parse: a ferry pin is a ship, maritime")
check(by["dang"]["glyph"] == "bridge" and by["dang"]["icon_label"] == "Bridge", "parse: a bridge pin is a bridge")
check(by["moving"]["glyph"] == "train", "parse: a train pin is a train")
check(by["mystery"]["glyph"] == "" and by["mystery"]["icon_label"] == "Other", "parse: an unknown icon code stays Other with no glyph")
check(all("front_kind" not in f["properties"] for f in fc["features"] if f["geometry"]["type"] != "LineString"), "parse: only lines get front_kind")

# ---------- page files: static ----------
def read(*p):
    with open(os.path.join(PROJ, *p), encoding="utf-8") as fh:
        return fh.read()


APP, FR, HTML, CSS = read("web", "app.js"), read("web", "ext", "fronts.js"), read("web", "index.html"), read("web", "style.css")
VER = read("VERSION").strip()
check(re.search(r'<script src="ext/fronts\.js\?v=%s"></script>' % re.escape(VER), HTML), "index.html loads ext/fronts.js with the current version")
check(HTML.index("ext/fronts.js") < HTML.index('src="app.js'), "fronts.js loads before app.js")
check(not re.search(r"https?://", FR), "fronts.js makes no absolute request and links nowhere")
check(".frrow" in CSS and ".glico" in CSS, "style.css has the fronts list and glyph rules")
m = re.search(r"const ICON_GLYPH = \{(.*?)\};", APP, re.S)
check(m, "app.js has ICON_GLYPH")
page_icons = dict(re.findall(r"(\d{4}): \"([a-z]+)\"", m.group(1)))
check(page_icons == NAMES, "the page's icon table matches gt/mymaps.py ICONS")
glyphs = set(re.findall(r"^    ([a-z]+): \{ (?:fill|stroke):", APP, re.M))
check(set(NAMES.values()) | {"swords", "anchor", "shield"} <= glyphs, "every glyph the tables name is drawn in GLYPHS")
check('"ev-ico"' in APP and 'events: ["ev-halo", "ev-pt", "ev-ico", "ev-label"]' in APP, "the pin badge layer belongs to the events layer group")
check("styleimagemissing" in APP, "pin badges are drawn on demand")

# ---------- behaviour: node against a stub GTX ----------
NODE = shutil.which("node") or "/opt/homebrew/bin/node"
check(os.path.exists(NODE), "node is installed (" + NODE + ")")
HARNESS = r"""
const fs = require("fs");
const NOW = Date.UTC(2026, 10, 24, 12);
Date.now = () => NOW;
const H = 3600e3;
const ov = (id, title, stroke, cs, extra) => ({ type: "Feature", geometry: { type: "LineString", coordinates: cs }, properties: Object.assign({ id, kind: "overlay", title, stroke, overlay_type: "other", theatre: "t1", country_name: "Testland" }, extra || {}) });
const ev = (id, lon, lat, ageH) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { id, kind: "event", title: "pin " + id, ts_ms: NOW - ageH * H, theatre: "t1" } });
const S = { theatre: "global", events: { features: [
  ov("A", "Frontline", "#A52714", [[30, 48], [31, 48], [32, 48]], { front_kind: "contact", overlay_type: "frontline" }),
  ov("B", "Blockade line", "#A52714", [[57, 25], [58, 24]], { overlay_type: "zone", theatre: "t2" }),       // no front_kind: the page's own rule
  ov("C", "Maybe", "#FFD600", [[10, 10], [11, 10], [12, 10]]),
  ov("D", "NATO/RU Border", "#01579B", [[24, 55], [25, 56], [26, 57]], { overlay_type: "border" }),
  ov("E", "Damaged", "#A52714", [[36, 45], [36.01, 45]], { overlay_type: "damage" }),
  ov("F", "Island Defense Chain", "#A52714", [[120, 20], [121, 22], [122, 24]], { overlay_type: "zone" }),
  { type: "Feature", geometry: { type: "Polygon", coordinates: [[[1, 1], [2, 1], [2, 2], [1, 1]]] }, properties: { id: "P", kind: "overlay", title: "Front field", stroke: "#A52714" } },
  ev("e1", 31, 48.3, 2), ev("e2", 31.5, 47.6, 30), ev("e3", 31, 49.5, 1), ev("e4", 30.2, 48.1, 100), ev("e5", 57.5, 24.6, 5),
  { type: "Feature", geometry: { type: "Point", coordinates: [31, 48] }, properties: { id: "u", kind: "event", title: "undated" } },
] } };
let renderFn, loadFn, layer, data, popups = {}, images = [], added = [], shownPopup = null;
const map = { getSource: () => ({ setData: (d) => { data = d; } }), addSource() {}, addLayer(l) { added.push(l.id); }, fitBounds() {}, once() {} };
const GTX = { S, map, esc: (s) => String(s == null ? "" : s), nf: (n) => String(n), ago: () => "ago", below: { events: "ev-halo" },
  layer(o) { layer = o; }, onMapLoad(fn) { loadFn = fn; }, onRender(fn) { renderFn = fn; }, popup(id, fn) { popups[id] = fn; },
  layerOn: () => true, mapImage(id) { images.push(id); }, drawGlyph: () => ({ toDataURL: () => "data:," }), showPopup(ll, html) { shownPopup = { ll, html }; } };
global.window = { GTXQ: [] }; global.document = { getElementById: () => null, addEventListener() {} };
eval(fs.readFileSync(process.argv[1], "utf8"));
global.window.GTXQ.forEach((fn) => fn(GTX));
loadFn(map); renderFn();
const fronts = GTX.fronts().map((f) => ({ id: f.id, kind: f.kind, km: f.km, mid: f.mid, n24: f.n24, n72: f.n72, last: f.last && f.last.id, where: f.where }));
const all = data;
S.theatre = "t2"; renderFn(); const t2 = data.features.map((f) => f.properties.id + ":" + f.geometry.type);
S.theatre = "global"; renderFn();
popups["fr-ico"]({ properties: { id: "A" } }, [31, 48]);
console.log(JSON.stringify({ fronts, layer: { key: layer.key, ids: layer.ids, click: layer.click, after: layer.after, count: layer.count() }, images, added,
  nfeat: all.features.length, kinds: all.features.filter((f) => f.geometry.type === "Point").map((f) => f.properties.kind), t2, popup: shownPopup.html }));
"""
res = subprocess.run([NODE, "-e", HARNESS, os.path.join(PROJ, "web", "ext", "fronts.js")], capture_output=True, text=True, timeout=60)
check(res.returncode == 0, "node harness ran: " + res.stderr[-800:])
out = json.loads(res.stdout)
F = {f["id"]: f for f in out["fronts"]}
check(set(F) == {"A", "B", "C", "F"}, "fronts are the red and yellow lines only (no border, damage stub or polygon): %s" % sorted(F))
check(F["A"]["kind"] == "contact" and F["B"]["kind"] == "blockade" and F["C"]["kind"] == "supposed" and F["F"]["kind"] == "defense", "each front has its kind, with or without the server's front_kind")
check(140 < F["A"]["km"] < 155, "a 2-degree line at 48N is about 149 km long: %.1f" % F["A"]["km"])
check(abs(F["A"]["mid"][0] - 31) < 0.01 and abs(F["A"]["mid"][1] - 48) < 0.01, "the marker sits half-way along the line")
check(abs(F["B"]["mid"][0] - 57.5) < 0.02 and abs(F["B"]["mid"][1] - 24.5) < 0.02, "a 2-point line's marker is its middle")
check(F["A"]["n24"] == 1 and F["A"]["n72"] == 2, "front A counts pins within 75 km: 1 in 24 h, 2 in 72 h (got %s / %s)" % (F["A"]["n24"], F["A"]["n72"]))
check(F["A"]["last"] == "e1", "front A's newest nearby pin is e1 (the 100 h pin and the far pin do not count as newest)")
check(F["B"]["n24"] == 1 and F["C"]["n72"] == 0, "the blockade line has its own pin; the far line has none")
check(out["fronts"][0]["id"] == "A", "the busiest front lists first")
check(out["layer"]["key"] == "fronts" and out["layer"]["after"] == "overlays" and out["layer"]["count"] == 4, "the layer registers after the overlays row and counts 4 fronts")
check(set(out["added"]) == set(out["layer"]["ids"]) == {"fr-case", "fr-line", "fr-dash", "fr-dot", "fr-ico"}, "every registered map layer is added")
check(set(out["images"]) == {"fr-contact", "fr-supposed", "fr-blockade", "fr-defense"}, "one marker image per kind")
check(out["nfeat"] == 8 and sorted(out["kinds"]) == ["blockade", "contact", "defense", "supposed"], "the map source holds a line and a marker per front")
check(sorted(out["t2"]) == ["B:LineString", "B:Point"], "a theatre filter keeps only that theatre's fronts")
check("Frontline" in out["popup"] and "1</b> event pin within 75 km" in out["popup"] and "Not a live trace" in out["popup"], "the popup names the front, its count and the caveat")

print("test_160_fronts: %d checks passed" % ok)
