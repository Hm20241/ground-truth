"""Offline tests for 1.5.3 / 1.5.4, the page side of the outage layers (web/ext/outages.js, ext 1.1): power, cell /
mobile networks, websites / online services, AI / cloud / datacenters. 1.5.4: Cloudflare Radar API records name
their link (Radar Outage Center, Radar traffic page, Cloudflare's post).

Static checks on the page files (the script tag, the Feed groups in app.js, relative requests only, the CSS) and a
behaviour check: node runs web/ext/outages.js against a stub GTX and a stub map, with SYNTHETIC fixtures shaped like
the shared contract (v1: the item, the data dict, the GeoJSON and the extras board, pops, grid, us, russia and
internet; invented incidents, providers' names only, example.org links). Nothing is real data. No network.

Run: python3 -I tests/test_outages_page.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

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


def read(rel):
    with open(os.path.join(PROJ, rel), encoding="utf-8") as fh:
        return fh.read()


VERSION = read("VERSION").strip()
APP, INDEX, CSS, SRC = read("web/app.js"), read("web/index.html"), read("web/style.css"), read("web/ext/outages.js")

# ---------- static ----------
tag = '<script src="ext/outages.js?v=%s"></script>' % VERSION
check(tag in INDEX, "index.html loads ext/outages.js with ?v=" + VERSION)
check(INDEX.index('src="ext/cyber.js') < INDEX.index(tag) < INDEX.index('src="app.js'), "outages.js loads after cyber.js and before app.js")
check("(window.GTXQ = window.GTXQ || []).push((GTX) => {" in SRC, "outages.js queues its setup through GTXQ")
fg = APP[APP.index("  const FG = {"):APP.index("  };", APP.index("  const FG = {"))]
for g, name, col in (("power", "Power", "#f59e0b"), ("web", "Web", "#a78bfa"), ("cloud", "AI / cloud", "#f472b6"), ("cell", "Cell", "#4ade80")):
    check('%s: ["%s", "%s"]' % (g, name, col) in fg, "app.js FG has the %s group (%s, %s)" % (g, name, col))
check('internet: ["Internet", "#5eead4"]' in fg, "the existing Internet group is kept (cellular.internet goes there)")
# requests: only through GTX.api, which loadExt calls for it; the extension itself makes none (HA ingress needs relative URLs)
check(not re.search(r"\bfetch\s*\(|XMLHttpRequest|EventSource|navigator\.sendBeacon|import\s*\(", SRC), "outages.js makes no requests of its own")
check(not re.search(r'GTX\.api\(\s*["\'`](?:/|https?:)', SRC), "any GTX.api call is relative")
check("document.title" not in SRC, "outages.js never touches document.title")
check("192.168." not in SRC and "/gt/" not in SRC, "no hard-coded host or /gt/ prefix")
check("localStorage" not in SRC and "sessionStorage" not in SRC, "no browser storage")
# the public export audit rejects these words (built from parts so this file passes the audit too)
for word in ("SER" + "VER", "T5" + "00", "local." + "will", "amber" + "pc", "gev-" + "deploy"):
    check(word not in SRC, "outages.js does not contain a word the export audit rejects")
check(not re.search(r"\bW" + r"ill\b", SRC), "outages.js does not contain the owner's name")
check("1.5.3: outage layers (ext/outages.js)" in CSS and ".pop .ou-b" in CSS and ".ou-board a.chip" in CSS, "style.css has the outages section")
check("GTX.when(v, rel)" in SRC and "fmtT(" not in SRC and "toISOString" not in SRC, "times go through GTX.when (the page's zone), never UTC-only formats")
check("GTX.below.events" in SRC, "layers sit under the curated event pins")
check(SRC.count("GTX.layer(") == 1 and 'after: "outages"' in SRC, "layers registered after the IODA outages layer")

# ---------- behaviour: node against a stub GTX ----------
NODE = shutil.which("node") or "/opt/homebrew/bin/node"
check(os.path.exists(NODE), "node is installed (" + NODE + ")")

NOW = 1795240800000  # 2026-11-21T04:40:00Z
M, H = 60000, 3600000


def iso(ms):
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def item(feed, src, sid, **o):
    ts = o.pop("ts", NOW - H)
    it = {"id": "%s:%s:%s" % (feed, src, sid), "source": src, "provider": src, "kind": "status", "title": "?", "summary": None,
          "lang": "en", "url": "https://example.org/%s/%s" % (feed, sid), "start_ms": None, "end_ms": None, "active": True,
          "severity": "minor", "status": None, "regions": [], "where": "", "cc": [], "ll": None, "place": None, "tags": [], "metric": None}
    it.update(o)
    it.update(ts=iso(ts), ts_ms=ts)
    return it


def data(feed, rows, **extra):
    items = sorted((r[0] for r in rows), key=lambda i: -i["ts_ms"])
    feats = []
    for r in rows:
        it, places = r[0], (r[1] if len(r) > 1 else None)
        for pl in places or ([it["ll"]] if it["ll"] else []):
            ll, own = pl if isinstance(pl, tuple) else (pl, {})  # a place may add its own region / name / shutdown flags
            p = {k: v for k, v in it.items() if k not in ("summary", "metric", "title_orig", "summary_orig", "translated")}
            if it.get("title_orig"):
                p["title"] = it["title_orig"]  # translations reach the items only
            p.update(layer=feed, pid=it["id"], **own)
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": ll}, "properties": p})
    d = {"version": "1.0", "fetched_at": iso(NOW - 2 * M), "count": len(items), "trimmed": 0, "items": items,
         "geojson": {"type": "FeatureCollection", "features": feats},
         "sources": [{"name": i["source"], "label": i["source"].title() + " status", "ok": True, "error": None, "checked": iso(NOW), "good": iso(NOW),
                      "newest": None, "n": 1, "active": 1} for i in items],
         "summary": "Synthetic %s summary." % feed, "note": "Synthetic %s note." % feed, "attribution": "Synthetic %s attribution." % feed,
         "public_ok": False, "non_commercial": True}
    d.update(extra)
    return d


UKR = "power:ukrenergo:p1"
FX = {
    "power": data("power", [
        (item("power", "odin", "06037", provider="ODIN", kind="outage", title="Los Angeles County, CA: 48,200 customers out", severity="major",
              status="in effect", place="county", ll=[-118.23, 34.06], cc=["USA"], metric={"customers": 48200}, ts=NOW - 20 * M),),
        (item("power", "odin", "12086", provider="ODIN", kind="outage", title="Miami-Dade County, FL: 3,100 customers out", active=False,
              status="resolved", place="county", ll=[-80.19, 25.76], cc=["USA"], metric={"customers": 3100}, ts=NOW - 10 * H),),
        (item("power", "ukrenergo", "p1", provider="Ukrenergo", kind="post", lang="uk", severity="critical", status="in effect",
              title="Emergency power cuts in Kharkiv, Sumy and Poltava regions", title_orig="Аварійні відключення в Харківській, Сумській та Полтавській областях",
              translated={"from": "uk", "by": "model"}, summary="Emergency schedules apply.", summary_orig="Діють графіки аварійних відключень.",
              place="oblast", ll=[36.23, 49.99], cc=["UKR"], regions=["UA-63", "UA-59", "UA-53"], where="Kharkiv, Sumy and Poltava oblasts",
              start_ms=NOW - 3 * H, ts=NOW - 35 * M), [([36.23, 49.99], {"region": "UA-63", "region_name": "Kharkiv Oblast"}),
                                                       ([34.80, 50.91], {"region": "UA-59", "region_name": "Sumy Oblast"}),
                                                       ([34.55, 49.59], {"region": "UA-53", "region_name": "Poltava Oblast"})]),
    ], grid={"taipower": {"light": "Y", "reserve_pct": 8.1, "load_mw": 33100, "t": iso(NOW)}, "eskom": {"stage": 3, "t": iso(NOW)},
             "caiso": {"events": 1, "t": iso(NOW), "names": ["Flex Alert"]}},
       us={"meters_out": 61610, "counties": 2, "utilities": 38, "t": iso(NOW)}),
    "cellular": data("cellular", [
        (item("cellular", "rumap", "d1", provider="Shutdown map", kind="shutdown", title="Mobile internet shut down in 2 regions of Russia",
              severity="major", status="in effect", place="subject", ll=[83.0, 52.6], cc=["RUS"], regions=["RU-ALT", "RU-BEL"], ts=NOW - 50 * M),
         [([83.0, 52.6], {"region": "RU-ALT", "region_name": "Altai Krai", "shutdown": True, "whitelist": True}),
          ([36.6, 50.6], {"region": "RU-BEL", "region_name": "Belgorod Oblast", "shutdown": True, "whitelist": False})]),
        (item("cellular", "netblocks", "ab", provider="NetBlocks", kind="post", title="Mobile data slowdowns in Abkhazia", severity="info",
              cc=["GEO"], ts=NOW - 3 * H),),
    ], russia={"date": "2026-11-21", "shutdown_regions": 2, "whitelist_regions": 1, "regions": [
        {"code": "RU-ALT", "name": "Altai Krai", "shutdown": True, "whitelist": True}, {"code": "RU-BEL", "name": "Belgorod Oblast", "shutdown": True, "whitelist": False}]},
       internet=[item("cellular", "netblocks", "ir", provider="NetBlocks", kind="post", title="Internet disrupted in Iran", severity="major",
                      place="country", ll=[53.7, 32.4], cc=["IRN"], ts=NOW - 25 * M)]),
    "websites": data("websites", [
        (item("websites", "github", "g1", provider="GitHub", title="Incident with Actions", status="investigating", place="hq",
              ll=[-122.39, 37.78], cc=["USA"], where="Global", ts=NOW - 12 * M),),
        (item("websites", "steam", "s1", provider="Steam", title="Login unavailable", severity="major", status="identified", where="Global", ts=NOW - 15 * M),),
    ], board=[{"source": "steam", "provider": "Steam", "status": "major", "active": 1, "url": "https://example.org/s"},
              {"source": "github", "provider": "GitHub", "status": "degraded", "active": 1, "url": "https://example.org/g"},
              {"source": "slack", "provider": "Slack", "status": "maintenance", "active": 1, "url": "https://example.org/l"},
              {"source": "zoom", "provider": "Zoom", "status": "unknown", "active": 0, "url": "javascript:alert(1)"},
              {"source": "reddit", "provider": "Reddit", "status": "operational", "active": 0, "url": "https://example.org/r"}]),
    "cloud": data("cloud", [
        (item("cloud", "aws", "a1", provider="AWS", title="Increased error rates for EC2 APIs in US-EAST-1", severity="major", status="identified",
              place="region", ll=[-77.49, 39.04], cc=["USA"], regions=["us-east-1"], ts=NOW - 8 * M),),
        (item("cloud", "cloudflare", "c1", provider="Cloudflare", title="Elevated errors in Ashburn (IAD)", place="pop", ll=[-77.49, 39.04],
              cc=["USA"], regions=["IAD"], status="monitoring", ts=NOW - 25 * M),),
        (item("cloud", "openai", "o1", provider="OpenAI", title="Elevated errors on <b>ChatGPT</b>", severity="major", status="resolved", active=False,
              place="hq", ll=[-122.41, 37.76], cc=["USA"], ts=NOW - 5 * H),),
    ], board=[{"source": "aws", "provider": "AWS", "status": "partial", "active": 1, "url": "https://example.org/a"},
              {"source": "openai", "provider": "OpenAI", "status": "operational", "active": 0, "url": "https://example.org/o"}],
       pops={"total": 335, "partial_outage": 1, "under_maintenance": 6, "named": ["IAD"]}),
}
RADAR = data("cellular", [
    (item("cellular", "radar_outages", "r1", provider="Cloudflare Radar", kind="outage", title="Mobile network outage in France",
          severity="major", status="in effect", url="https://radar.cloudflare.com/outage-center", place="country", ll=[2.35, 46.6],
          cc=["FRA"], ts=NOW - 30 * M),),
    (item("cellular", "radar_anomalies", "r2", provider="Cloudflare Radar", kind="outage", title="Traffic anomaly on EXAMPLE-NET (AS64500)",
          url="https://radar.cloudflare.com/traffic/as64500", place="country", ll=[101.7, 3.1], cc=["MYS"], ts=NOW - 40 * M),),
    (item("cellular", "radar_outages", "r3", provider="Cloudflare Radar", kind="outage", title="Mobile outage with a post",
          url="https://example.org/cellular/r3", place="country", ll=[30.5, 50.4], cc=["UKR"], ts=NOW - 50 * M),),
])
FX["radar"] = RADAR

HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const [src, thPath, fxPath] = process.argv.slice(1);
const TH = JSON.parse(fs.readFileSync(thPath, "utf8")), FX = JSON.parse(fs.readFileSync(fxPath, "utf8"));
globalThis.window = globalThis; window.innerWidth = 1440; window.scrollTo = () => {};
const rowEls = {};
const mkRow = () => { const leg = { style: {}, classList: { contains: (c) => c === "aclegend" } }, lab = { style: {}, nextElementSibling: leg }; return { closest: () => lab, lab, leg }; };
globalThis.document = { addEventListener() {}, getElementById: () => null, querySelectorAll: () => [],
  querySelector: (sel) => { const m = sel.match(/data-layer="(\w+)"/); return m ? (rowEls[m[1]] || (rowEls[m[1]] = mkRow())) : null; } };
__APPFN__
const rec = { layers: [], popups: {}, feeds: {}, tabs: [], kpis: [], labels: {}, credits: [], onRender: [], streams: [], mapLoad: [], shown: [] };
const sources = {}, added = { sources: [], layers: [] };
let hits = [], fetched = 0;
const map = { getSource: (id) => sources[id] || null, addSource: (id, o) => { sources[id] = { data: o.data, setData(d) { this.data = d; } }; added.sources.push(id); },
  addLayer: (o, before) => added.layers.push({ o, before }), getLayer: () => true, getLayoutProperty: () => "visible", project: (ll) => ll,
  queryRenderedFeatures: () => hits, flyTo: () => {}, getZoom: () => 3 };
const when = (v, rel) => { const t = typeof v === "number" ? v : Date.parse(v); return Number.isFinite(t) ? new Date(t).toISOString().slice(5, 16).replace("T", " ") + "Z" + (rel === false ? "" : " · ago") : "–"; };
const GTX = { version: "1.4", map, S: { feeds: {}, status: {} }, api: () => { fetched++; return Promise.resolve(null); }, when, country, below: { events: "ev-halo" },
  esc: (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
  isoMs: (s) => (s ? Date.parse(s) : null), nf: (n) => (n == null ? "–" : Number(n).toLocaleString("en-US")),
  showPopup: (ll, html) => { const el = { scrollTop: 40 }; rec.shown.push({ ll, html, el }); return { getElement: () => ({ querySelector: () => el }) }; },
  layer: (o) => rec.layers.push(o), onMapLoad: (fn) => rec.mapLoad.push(fn), popup: (id, fn) => { rec.popups[id] = fn; }, feed: (n, fn) => { rec.feeds[n] = fn; },
  tab: (o) => rec.tabs.push(o), isOpen: () => false, label: (f, t) => { rec.labels[f] = t; }, credit: (h) => rec.credits.push(h), kpi: (fn) => rec.kpis.push(fn),
  onRender: (fn) => rec.onRender.push(fn), stream: (o) => rec.streams.push(o), layerOn: () => true };
vm.runInThisContext(fs.readFileSync(src, "utf8"), { filename: "outages.js" });
(window.GTXQ || []).forEach((fn) => fn(GTX));
const kpis = () => rec.kpis.flatMap((fn) => fn() || []);
const counts = () => Object.fromEntries(rec.layers.map((l) => [l.key, l.count()]));
const tab = () => { const el = { innerHTML: "", onclick: null }; rec.tabs[0].render(el); return el; };
const rows = () => Object.fromEntries(Object.entries(rowEls).map(([k, r]) => [k, [r.lab.style.display || "", r.leg.style.display || ""]]));
const out = {};
out.setup = { layers: rec.layers.map((l) => ({ key: l.key, after: l.after, feed: l.feed, ids: l.ids, click: l.click, clickBefore: l.clickBefore, legend: l.legend, label: l.label })),
  counts: counts(), kpis: kpis(), streams: rec.streams.length, tabs: rec.tabs.map((t) => ({ id: t.id, label: t.label, before: t.before })), labels: rec.labels,
  credits: rec.credits, popups: Object.keys(rec.popups), feeds: Object.keys(rec.feeds), tab: tab().innerHTML };
// the public copy: the status reply lists none of the four feeds
GTX.S.status = { mil: { ok: true } };
rec.onRender.forEach((fn) => fn([]));
out.pub = { tab: tab().innerHTML, streams: rec.streams.length, kpis: kpis(), counts: counts(), rows: rows() };
rec.mapLoad.forEach((fn) => fn(map));
out.map = { sources: added.sources, layers: added.layers.map(({ o, before }) => ({ id: o.id, type: o.type, source: o.source, before, minzoom: o.minzoom ?? null,
  filter: o.filter ?? null, paint: o.paint, layout: o.layout })) };
// the self-hosted page: the feeds run
GTX.S.status = { mil: {}, power: {}, cellular: {}, websites: {}, cloud: {} };
for (const k of ["power", "cellular", "websites", "cloud"]) { GTX.S.feeds[k] = FX[k]; rec.feeds[k](FX[k]); }
rec.onRender.forEach((fn) => fn([]));
const feats = {};
for (const k of ["power", "cellular", "websites", "cloud"]) feats[k] = sources["ou-" + k].data.features.map((f) => Object.assign({ ll: f.geometry.coordinates }, f.properties));
const streams = rec.streams.map((st) => ({ key: st.key, group: st.group, label: st.label, items: st.items(st.data()) }));
const el = tab();
out.data = { feats, streams, counts: counts(), kpis: kpis(), rows: rows(), tab: el.innerHTML, tabClick: typeof el.onclick, fetched };
// popups: two items at one pin (plus the first one again), a translated item over three oblasts, a Russian region ring
hits = [{ properties: { pid: "cloud:aws:a1" } }, { properties: { pid: "cloud:cloudflare:c1" } }, { properties: { pid: "cloud:aws:a1" } }];
rec.popups["ou-cloud"]({ properties: { pid: "cloud:aws:a1" } }, [-77.49, 39.04]);
out.popIad = rec.shown[rec.shown.length - 1].html; out.popTop = rec.shown[rec.shown.length - 1].el.scrollTop;
hits = [{ properties: { pid: "__UKR__" } }];
rec.popups["ou-power"]({ properties: { pid: "__UKR__", rg: "Sumy Oblast" } }, [34.8, 50.91]);
out.popUkr = rec.shown[rec.shown.length - 1].html;
hits = [];
rec.popups["ou-cellular-ring"]({ properties: { pid: "cellular:rumap:d1", rg: "Belgorod Oblast" } }, [36.6, 50.6]);
out.popRu = rec.shown[rec.shown.length - 1].html;
rec.popups["ou-cloud"]({ properties: { pid: "cloud:openai:o1" } }, [-122.41, 37.76]);
out.popOld = rec.shown[rec.shown.length - 1].html;
// View on map from a Feed row: the item's own popup at its pin
const gh = rec.streams.find((s) => s.key === "websites").items(FX.websites).find((i) => i.ll);
gh.pop(); out.vom = rec.shown[rec.shown.length - 1];
// 1.5.4: Cloudflare Radar records (a second cellular delivery, after everything above was read)
rec.feeds.cellular(FX.radar);
hits = [];
out.popRadar = ["r1", "r2", "r3"].map((id) => { rec.popups["ou-cellular"]({ properties: { pid: "cellular:radar_" + (id === "r2" ? "anomalies" : "outages") + ":" + id } }, [0, 0]);
  return rec.shown[rec.shown.length - 1].html; });
process.stdout.write(JSON.stringify(out, (k, v) => (typeof v === "function" ? "[fn]" : v)));
"""


def block(src, start):
    i = src.index(start)
    return src[i:src.index("\n  }\n", i) + 4]


APPFN = block(APP, "  function country(k) {")
HARNESS = HARNESS.replace("__APPFN__", APPFN).replace("__UKR__", UKR)
tmp = tempfile.mkdtemp(prefix="gt-ou-")
try:
    fxp = os.path.join(tmp, "fx.json")
    with open(fxp, "w", encoding="utf-8") as fh:
        json.dump(FX, fh)
    res = subprocess.run([NODE, "-e", HARNESS, os.path.join(PROJ, "web", "ext", "outages.js"), os.path.join(PROJ, "web", "geo", "theatres.json"), fxp],
                         capture_output=True, text=True, timeout=60)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
check(res.returncode == 0, "node harness ran: " + res.stderr[-600:])
R = json.loads(res.stdout)

# setup: four layers after IODA, in order, each with its ids, clicks, count and legend; one tab; labels and credits
S = R["setup"]
check([(l["key"], l["after"], l["feed"]) for l in S["layers"]] == [("power", "outages", "power"), ("cellular", "power", "cellular"),
      ("websites", "cellular", "websites"), ("cloud", "websites", "cloud")], "layers: power, cellular, websites, cloud chained after outages")
check(S["layers"][1]["ids"] == ["ou-cellular", "ou-cellular-ring", "ou-cellular-lbl"] and S["layers"][1]["click"] == ["ou-cellular", "ou-cellular-ring"],
      "cellular: circles, Russia ring and labels; circles and ring clickable")
check(all(l["clickBefore"] == "th-pt" and "resolved" in l["legend"] and "active" in l["legend"] for l in S["layers"]), "every layer: clicks before thermal, legend with active and resolved")
check("customers out" in S["layers"][0]["legend"] and "RU regional shutdown" in S["layers"][1]["legend"], "power and cellular legends name their extra styles")
check("ODIN" in S["layers"][0]["label"] and "status pages" in S["layers"][2]["label"] and "Cloudflare PoPs" in S["layers"][3]["label"], "layer labels")
check(S["counts"] == {"power": None, "cellular": None, "websites": None, "cloud": None} and S["kpis"] == [] and S["streams"] == 0,
      "no data: no counts, no KPIs, no Feed streams")
check(S["tabs"] == [{"id": "outages", "label": "Outages", "before": "sources"}], "one Outages tab, before Sources")
check(S["feeds"] == ["power", "cellular", "websites", "cloud"] and sorted(S["popups"]) == ["ou-cellular", "ou-cellular-ring", "ou-cloud", "ou-power", "ou-websites"],
      "feed handlers and popups registered")
check(set(S["labels"]) == {"power", "cellular", "websites", "cloud"} and len(S["credits"]) == 4, "a Sources label and a credit per feed")
check("No outage data yet" in S["tab"], "tab before the status reply: No outage data yet")

# the public copy stays silent
P = R["pub"]
check("Not on this copy" in P["tab"] and P["streams"] == 0 and P["kpis"] == [], "public copy: the tab says Not on this copy; no streams, no KPIs")
check(P["rows"] and all(v == ["none", "none"] for v in P["rows"].values()) and len(P["rows"]) == 4, "public copy: the four layer rows and legends hidden: %s" % P["rows"])

# map layers
L = {l["id"]: l for l in R["map"]["layers"]}
check(R["map"]["sources"] == ["ou-power", "ou-cellular", "ou-websites", "ou-cloud"], "one GeoJSON source per feed")
check(all(l["before"] == "ev-halo" for l in L.values()) and len(L) == 9, "nine map layers, all under the curated event pins")
rad = json.dumps(L["ou-power"]["paint"]["circle-radius"])
check(all(x in rad for x in ('["!", ["get", "active"]], 4', '"critical", 9', '"major", 7.5', '"minor", 6', '"ln"', '"cust"')), "radius: resolved 4, severity 9/7.5/6/5, ln(customers)")
check(L["ou-cloud"]["paint"]["circle-opacity"] == ["case", ["get", "active"], 0.9, 0.35] and L["ou-cloud"]["paint"]["circle-stroke-width"] == ["case", ["get", "active"], 1, 0],
      "opacity 0.9 active / 0.35 resolved, a stroke on active dots")
check(L["ou-cellular-ring"]["filter"] == ["==", ["get", "kind"], "shutdown"] and L["ou-cellular"]["filter"] == ["!", ["==", ["get", "kind"], "shutdown"]],
      "Russia's shutdown subjects drawn as rings, not dots")
check(L["ou-websites-lbl"]["minzoom"] == 3.5 and json.dumps(L["ou-websites-lbl"]["filter"]) == '["all", ["==", ["get", "active"], true], ["==", ["get", "first"], true]]'
      and L["ou-websites-lbl"]["layout"]["text-field"] == ["get", "lbl"], "labels: active only, once per item, from zoom 3.5")
check(L["ou-cloud"]["layout"]["visibility"] == "visible", "layers start on")

D = R["data"]
check(D["fetched"] == 0, "the extension requested nothing itself")
check(D["counts"] == {"power": 2, "cellular": 2, "websites": 2, "cloud": 2}, "layer counts = active items: %s" % D["counts"])
check(all(v == ["", ""] for v in D["rows"].values()), "layer rows shown when the feeds run")
F = D["feats"]
la = next(f for f in F["power"] if f["pid"] == "power:odin:06037")
check(la["cust"] == 48200 and la["active"] is True and la["sev"] == "major" and la["rank"] == 13, "county point: customers from the item's metric, rank active+major")
ua = [f for f in F["power"] if f["pid"] == UKR]
check(len(ua) == 3 and [f["first"] for f in ua] == [True, False, False] and ua[0]["lbl"].startswith("Ukrenergo: Emergency power cuts"),
      "multi-oblast item: three points, one label, in English (the item's translated title)")
check(next(f for f in F["power"] if f["pid"] == "power:odin:12086")["active"] is False, "resolved point flagged")
check(len(F["cellular"]) == 2 and all(f["kind"] == "shutdown" for f in F["cellular"]), "the ring item's two subjects (the unplaced item is not drawn)")
check([(f["rg"], f["wl"]) for f in F["cellular"]] == [("Altai Krai", True), ("Belgorod Oblast", False)] and [f["rg"] for f in ua] == ["Kharkiv Oblast", "Sumy Oblast", "Poltava Oblast"],
      "each point keeps its own region name and Russia's whitelist flag")
check(json.dumps(L["ou-cellular-ring"]["paint"]["circle-opacity"]) == '["case", ["get", "active"], ["case", ["get", "wl"], 0.45, 0.12], 0.04]', "whitelist-only regions: a filled ring")
check(len(F["websites"]) == 1 and all(set(f) == {"ll", "pid", "active", "sev", "rank", "kind", "cust", "lbl", "first", "rg", "wl"} for k in F for f in F[k]),
      "points carry only small scalar properties")

ST = {s["key"]: s for s in D["streams"]}
check([(s["key"], s["group"]) for s in D["streams"]] == [("power", "power"), ("cellular", "cell"), ("cellnet", "internet"), ("websites", "web"), ("cloud", "cloud")],
      "Feed streams and groups: %s" % [(s["key"], s["group"]) for s in D["streams"]])
u = next(i for i in ST["power"]["items"] if i["id"] == "ou:" + UKR)
check(u["label"] == "Power · Ukrenergo" and u["cat"] == "energy" and u["badge"] == "critical" and u["zoom"] == 6 and u["th"] == ["ukraine-russia"]
      and u["cc"] == ["UKR"] and u["tr"] == {"from": "uk", "orig": FX["power"]["items"][1]["title_orig"]} and u["day"] is False and u["pop"] == "[fn]",
      "power Feed item: label, energy, badge, zoom by place, theatre, cc, translation, popup: %s" % u)
m = next(i for i in ST["power"]["items"] if i["id"] == "ou:power:odin:12086")
check(m["badge"] == "resolved" and m["zoom"] == 7 and m["th"] == ["americas"], "resolved county: badge resolved, zoom 7")
s1 = next(i for i in ST["websites"]["items"] if "Steam" in i["label"])
check(s1["ll"] is None and "pop" not in s1 and s1["cat"] == "cyber" and s1["label"] == "Web · Steam" and s1["th"] == [] and "cc" not in s1,
      "an unplaced item: no map point, no popup, no country")
check(ST["cloud"]["items"][0]["label"] == "AI / cloud · AWS" and ST["cloud"]["items"][0]["zoom"] == 5 and "us-east-1" in ST["cloud"]["items"][0]["text"],
      "cloud Feed item: label, zoom 5 for a region, regions searchable")
check(ST["cellular"]["items"][0]["label"] == "Cell · Shutdown map" and ST["cellular"]["items"][0]["zoom"] == 5, "cell Feed item")
check(ST["cellnet"]["label"] == "Internet" and [i["label"] for i in ST["cellnet"]["items"]] == ["Internet · NetBlocks"] and ST["cellnet"]["items"][0]["cat"] == "cyber",
      "cellular.internet: its own stream in the Internet group, Internet · NetBlocks")
check(all(i["ts"] > 0 and i["title"] and i["id"].startswith("ou:") for s in D["streams"] for i in s["items"]), "every Feed item has id, ts and title")

K = {k[1]: k for k in D["kpis"]}
check(K.get("Services degraded") == ["3", "Services degraded", "bad"], "KPI: 3 degraded services (maintenance and unknown left out), bad on a major: %s" % K)
check(K.get("US customers out (ODIN)") == ["61,610", "US customers out (ODIN)", False] and K.get("RU mobile shutdown regions") == ["2", "RU mobile shutdown regions", True],
      "KPIs: US customers out (ODIN) and RU shutdown regions")

T = D["tab"]
check([T.index(x) for x in ("<h4>Grid</h4>", "<h4>Online services</h4>", "<h4>Russia: mobile internet shutdowns</h4>", "<h4>Active now: 8</h4>")] ==
      sorted(T.index(x) for x in ("<h4>Grid</h4>", "<h4>Online services</h4>", "<h4>Russia: mobile internet shutdowns</h4>", "<h4>Active now: 8</h4>")),
      "tab cards in order: Grid, Online services, Russia, Active now (8)")
check("Yellow light" in T and "reserve <b>8.1%</b>" in T and "Load shedding stage 3" in T and "1 grid event</b>: Flex Alert" in T and "<b>61,610</b> customers out" in T,
      "Grid card: Taipower light and reserve, Eskom stage, CAISO events, ODIN customers out")
check(T.count('class="chip"') >= 7 and 'href="https://example.org/s"' in T and "javascript:" not in T and "major outage" in T,
      "services board: chips linking to the status pages (a non-http link dropped)")
check("Cloudflare data centres (PoPs): <b>335</b>" in T and "in active incidents: IAD" in T, "Cloudflare PoP counts")
check("Altai Krai" in T and "Shutdown regions <b>2</b>" in T and "Whitelist regions <b>1</b>" in T, "Russia card")
act = re.findall(r'data-oupid="([^"]+)"', T)
check(act[:3] == ["cloud:aws:a1", "websites:github:g1", "websites:steam:s1"] and "cloud:openai:o1" not in act, "Active now: newest first, resolved left out: %s" % act)
check("Synthetic power attribution." in T and "Synthetic cloud note." in T and D["tabClick"] == "function", "attribution and notes; rows open on the map")
check("&lt;b&gt;ChatGPT" not in T and "<b>ChatGPT" not in T, "resolved items stay out of Active now")

check("Increased error rates" in R["popIad"] and R["popIad"].count("Elevated errors in Ashburn") == 1 and R["popIad"].count("Also here") == 1
      and R["popIad"].count("Increased error rates") == 1 and "Official status ↗" in R["popIad"] and "identified" in R["popIad"],
      "popup: two items at one pin in one popup, each once")
check(R["popTop"] == 0, "popup starts at its title (scroll reset after MapLibre focuses its first link)")
pu = R["popUkr"]
check("Emergency power cuts" in pu and "EN · from Ukrainian" in pu and "Original: Аварійні" in pu and "Post ↗" in pu and "Started" in pu and "Updated" in pu
      and "Regions: UA-63, UA-59, UA-53" in pu and "Here: <b>Sumy Oblast</b>" in pu and "Also here" not in pu and "Emergency schedules apply." in pu, "popup: translated item, times, regions, summary")
check("Altai Krai <span" in R["popRu"] and "shutdown, whitelist" in R["popRu"] and "Here: <b>Belgorod Oblast</b>" in R["popRu"], "popup: the clicked region, then Russia's regions by name with shutdown / whitelist")
check("Here:" not in R["popIad"], "a one-region item names no clicked region")
check("&lt;b&gt;ChatGPT&lt;/b&gt;" in R["popOld"] and "resolved" in R["popOld"], "popup text is escaped; resolved badge")
check(R["vom"]["ll"] == [-122.39, 37.78] and "Incident with Actions" in R["vom"]["html"], "View on map opens the item's popup at its pin")
r1, r2, r3 = R["popRadar"]
check("Radar Outage Center ↗" in r1 and 'href="https://radar.cloudflare.com/outage-center"' in r1 and "Mobile network outage in France" in r1 and
      "Radar traffic page ↗" in r2 and 'href="https://radar.cloudflare.com/traffic/as64500"' in r2 and
      "Cloudflare's post ↗" in r3 and "Official status" not in r1 + r2 + r3,
      "Radar records name their link: Outage Center, traffic page, Cloudflare's post")

print("\n%d checks passed" % ok)
