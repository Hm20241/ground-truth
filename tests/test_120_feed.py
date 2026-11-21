"""Offline tests for 1.2.0, one Feed: every timestamped source in the Feed tab (GTX.stream, GTX API 1.2).

Static checks on the page (core streams, loaders, chips, versions, relative URLs, the theatre table) and a
behaviour check of every extension stream: node runs web/ext/*.js against a stub GTX and fixture records shaped
like the live feeds, then the items each stream yields are checked. No network.

Run: python3 -I tests/test_120_feed.py
"""
import json
import os
import re
import shutil
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


def read(rel):
    with open(os.path.join(PROJ, rel), encoding="utf-8") as fh:
        return fh.read()


VERSION = read("VERSION").strip()
APP, INDEX, CSS = read("web/app.js"), read("web/index.html"), read("web/style.css")
EXT = {n: read("web/ext/%s.js" % n) for n in ("wire", "hazards", "signals", "airspace", "cyber", "curated")}

# ---------- version and assets ----------
check(tuple(map(int, VERSION.split("."))) >= (1, 2, 0), "VERSION is 1.2.0 or later (1.3.0: later releases keep the 1.2.0 Feed)")
check(int((re.search(r'version: "1\.(\d+)"', APP) or [0, -1])[1]) >= 2, "GTX API version 1.2 or later")
local = re.findall(r'(?:src|href)="((?:ext/|app\.js|style\.css)[^"]*)"', INDEX)
check(len(local) == 9, "index.html loads style.css, seven extensions and app.js (%d)" % len(local))  # 1.5.3: outages.js
check(all(u.endswith("?v=" + VERSION) for u in local), "every local asset is cache-busted with ?v=" + VERSION)
check('geo/theatres.json?v=%s' % VERSION in APP, "theatres.json is fetched relative, with ?v=" + VERSION)

# ---------- Feed markup and CSS ----------
i_stale, i_src, i_count = INDEX.find('id="srcstale"'), INDEX.find('id="feedsrc"'), INDEX.find('id="feedcount"')
check(-1 < i_stale < i_src < i_count, "the source chips sit between the quiet-map notice and the count line")
check('role="group"' in INDEX[i_src - 80:i_src + 120], "the chip row is a labelled group")
for sel in (".feedsrc", ".feed li.sx .t", ".feed li.sx.nl", ".feed li.more"):
    check(sel in CSS, "style.css styles " + sel)

# ---------- core streams and loaders (app.js) ----------
core = re.findall(r'^  stream\(\{ key: "(\w+)", group: "(\w+)"', APP, re.M)
want_core = {"official": "official", "ukmto": "maritime", "embassy": "alerts", "airalerts": "alerts", "tzeva": "alerts",
             "advisories": "official", "outages": "internet", "pla": "official", "losses": "official", "czib": "airspace"}
check(dict(core) == want_core, "core streams and their groups: %s" % dict(core))
for f in ("official", "pla", "losses", "czib", "advisories"):
    check('api("feed/%s")' % f in APP, "loadAll fetches feed/" + f)
check('["official", "pla", "losses", "czib", "advisories"].forEach' in APP, "loadAll stores the five feeds in S.feeds")
check("if (x.events) render(); else { renderLayerCounts(); renderKpis(); feedSoon(); }" in APP and "renderKpis(); renderLayerCounts(); feedSoon();" in APP,
      "the Feed refreshes after an extension feed and after the alerts poll")
check("FEED_STEP = 300" in APP and 'id="feedmore"' in APP, "the Feed draws 300 rows at a time with a Show more button")
check(re.search(r'try \{ return JSON\.parse\(localStorage\.getItem\("gt-feed-off"\)', APP) is not None, "reading the hidden groups is guarded")
check(re.search(r'try \{ localStorage\.setItem\("gt-feed-off"', APP) is not None, "saving the hidden groups is guarded")
check("if (e.target.closest(\"a\")) return;" in APP, "clicking a row's link opens the source without flying the map")
check('target="_blank" rel="noopener"' in APP[APP.find("function streamRow"):APP.find("function renderFeedChips")],
      "stream rows link out in a new tab with rel=noopener")
check("stream(o) { stream(o); }" in APP and "country, dayMs," in APP, "GTX exposes stream, country and dayMs")
check("For map pins, 6h / 24h count back from the newest pin; the other sources count back from now." in APP,
      "the quiet-map notice explains both time rules")
check("i.pk && pinned.has(i.pk)" in APP, "a stream item citing a post the map already pins is dropped")

# ---------- relative URLs only (the HA ingress view serves GT under a token path) ----------
for name, src in [("app.js", APP)] + [("ext/%s.js" % k, v) for k, v in EXT.items()]:
    check(not re.search(r'(?:fetch|api|apiRev)\(\s*["\'`]/', src), name + ": no root-absolute fetches")
    check(not re.search(r'(?:fetch|api)\(\s*["\'`]http://', src), name + ": no plain-http fetches (third-party https APIs are fine)")
    check("192.168." not in src and '"/gt/' not in src and "'/gt/" not in src, name + ": no hard-coded server address or /gt/ prefix")

# ---------- theatres.json ----------
from tools import build_theatres  # noqa: E402
built = build_theatres.dump(build_theatres.build())
check(read("web/geo/theatres.json") == built, "web/geo/theatres.json matches tools/build_theatres.py (re-run it)")
TH = json.loads(built)
check(TH["a3"]["UKR"][0] == "ukraine-russia" and TH["a3"]["ISR"][0] == "middle-east", "Ukraine and Israel theatres")
check(TH["a2"]["FI"] == "FIN" and TH["names"]["finland"] == "FIN", "ISO-2 codes and names resolve to ISO-3")
check(all(len(v) == 4 for v in TH["a3"].values()), "every country row is [theatre, lon, lat, name]")
check("other" not in {v[0] for v in TH["a3"].values()}, "countries outside every theatre carry an empty theatre")

# ---------- extension streams, run in node against a stub GTX ----------
NODE = shutil.which("node") or "/opt/homebrew/bin/node"
check(os.path.exists(NODE), "node is installed (" + NODE + ")")
HARNESS = r"""
const fs = require("fs"), vm = require("vm"), path = require("path");
const dir = process.argv[1], TH = JSON.parse(fs.readFileSync(process.argv[2], "utf8")), FX = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const noop = () => {}, el = () => null;
globalThis.window = globalThis;
globalThis.document = { addEventListener: noop, getElementById: el, querySelector: el, querySelectorAll: () => [], createElement: () => ({ style: {} }) };
const isoMs = (s) => (s ? Date.parse(s) : null);
const fmtD = (ms) => new Date(ms).toISOString().slice(5, 10).replace("-", "/"), fmtT = (ms) => new Date(ms).toISOString().slice(11, 16) + "Z";
__APPFN__
const streams = [];
const GTX = { version: "1.2", map: { getSource: el, loaded: () => false }, S: { feeds: {}, events: null }, api: () => Promise.resolve(null),
  esc: (s) => String(s), fmtT, fmtD, ago: () => "", nf: (n) => String(n), isoMs, showPopup: noop, THEATRES: {}, CATS: {}, below: {},
  country, dayMs, layer: noop, onMapLoad: noop, legend: noop, briefColumn: noop, popup: noop, feed: noop, eventSource: noop, tab: noop,
  isOpen: () => false, label: noop, credit: noop, kpi: noop, onRender: noop, refresh: noop, layerOn: () => false, stream: (o) => streams.push(o) };
for (const f of ["wire", "hazards", "signals", "airspace", "cyber", "curated"]) vm.runInThisContext(fs.readFileSync(path.join(dir, f + ".js"), "utf8"), { filename: f + ".js" });
(window.GTXQ || []).forEach((fn) => fn(GTX));
const out = {};
for (const st of streams) {
  GTX.S.feeds = FX;
  const d = st.data();
  out[st.key] = { group: st.group, label: st.label, items: d ? st.items(d) : null };
}
process.stdout.write(JSON.stringify(out, (k, v) => (typeof v === "function" ? "[fn]" : v)));
"""
FX = {
    "wire": {"items": [{"id": "w1", "title": "Drone strike on Odesa port", "url": "https://example.org/a", "source": "kyivindependent",
                        "source_label": "Kyiv Independent", "ts_ms": 1795150000000, "theatre": "ukraine-russia", "countries": ["UKR", "RUS"],
                        "category": "drone", "summary": "port", "also_in": ["reuters", "ap"]}]},
    "telegram": {"items": [{"id": "t1", "title": "Explosions in Belgorod", "url": "https://t.me/s/chan/5", "channel": "chan",
                            "ts_ms": 1795150100000, "theatre": "ukraine-russia", "countries": ["RUS"], "category": "strike"}]},
    "hazards": {"geojson": {"features": [{"geometry": {"type": "Point", "coordinates": [147.1, -6.2]},
                                          "properties": {"id": "EQ1", "alert": "Green", "name": "Earthquake in Papua New Guinea", "type_label": "Earthquake",
                                                         "from": "2026-10-01T00:00:00Z", "to": "2026-11-20T05:17:45Z", "theatre": "indo-pacific",
                                                         "url": "https://www.gdacs.org/x", "severity": "M5.1"}}]}},
    "quakes": {"geojson": {"features": [{"geometry": {"type": "Point", "coordinates": [80.1, 30.2]},
                                         "properties": {"id": "emsc:1", "source": "EMSC", "time": "2026-11-18T04:51:11Z", "mag": 4.1, "depth_km": 10.0,
                                                        "place": "Uttaranchal, India", "kind": "earthquake", "watch": True,
                                                        "watch_reason": "shallow M4.1 in a watched area", "theatre": "south-asia", "url": "https://x"}}]}},
    "tsunami": {"items": [{"id": "jma:1", "source": "JMA", "kind": "volcano", "level": "advisory", "label": "Volcanic activity commentary (cancelled)",
                           "cancelled": True, "issued": "2026-11-20T07:03:59Z", "url": "https://www.data.jma.go.jp/x", "lat": 31.6, "lon": 130.7,
                           "volcano": "Sakurajima", "country_name": "Japan", "theatre": "indo-pacific"}]},
    "radiation": {"geojson": {"features": [{"geometry": {"type": "Point", "coordinates": [11.5, 48.1]},
                                            "properties": {"id": "DEZ1", "name": "Munich", "measured": "2026-11-20T06:00:00Z", "value_usv": 0.21, "ratio": 2.1}}]}},
    "ntas": {"items": [{"type": "National Terrorism Advisory System Bulletin", "kind": "bulletin", "start": "2026-11-01T00:00:00Z",
                        "end_et": "2027-01-31", "url": "https://www.dhs.gov/ntas", "summary": "heightened threat"}]},
    "ofac": {"items": [{"date": "2026-11-19", "title": "Counter Terrorism Designations", "url": "https://ofac.treasury.gov/recent-actions/20261119",
                        "programs": ["counter-terrorism", "iran"], "theatres": ["middle-east"]}]},
    "squawk": {"items": [{"hex": "4d02dd", "flight": "JFA96S", "reg": "LX-FLJ", "desc": "PILATUS PC-12", "squawk": "7600", "meaning": "radio failure",
                          "first_seen": "2026-11-20T07:27:38Z", "pos": [8.16, 45.82], "current": False, "mil": False}]},
    "tfr": {"items": [{"notam_id": "6/8989", "type": "UAS PUBLIC GATHERING", "title": "Houston, TX", "url": "https://tfr.faa.gov/x",
                       "effective": "2026-11-26T14:00:00Z", "expires": "2026-11-26T22:00:00Z", "mod": "2026-11-19T20:00:00Z",
                       "is_new": True, "theatre": "americas", "centre": [-95.4, 29.8]}]},
    "cyber": {"items": [{"id": "ddos:1", "kind": "ddos", "title": "DDoSia target list: 19 hosts (Spain 12)", "url": "https://witha.name",
                         "ts_ms": 1795156280000, "countries": ["ESP"], "sector": None, "ci": False, "tags": ["ddos"]},
                        {"id": "ran:2", "kind": "ransom", "title": "Ransomware claim: hospital", "url": "https://ransomware.live/x",
                         "ts": "2026-11-20T05:00:00Z", "countries": ["UKR", "POL"], "sector": "healthcare", "ci": True}]},
    "bgp": {"countries": [{"a2": "SY", "a3": "SYR", "name": "Syria", "theatre": "middle-east", "url": "https://stat.ripe.net/SY",
                           "latest": "2026-11-20T05:00:00Z", "level": "drop", "reasons": ["visible prefixes -40%"]},
                          {"a2": "FI", "a3": "FIN", "name": "Finland", "theatre": "europe-nato", "latest": "2026-11-20T05:00:00Z", "level": "ok"}]},
}
SCR = os.path.join(PROJ, "tests", ".feed_fixture.json")
with open(SCR, "w", encoding="utf-8") as fh:
    json.dump(FX, fh)


def block(src, start):
    """A top-level function of app.js, from its first line to the closing brace at two spaces."""
    i = src.index(start)
    return src[i:src.index("\n  }\n", i) + 4]


def line(src, start):
    i = src.index(start)
    return src[i:src.index("\n", i) + 1]


APPFN = block(APP, "  function country(k) {") + line(APP, "  const dayMs = ")
HARNESS = HARNESS.replace("__APPFN__", APPFN)
try:
    res = subprocess.run([NODE, "-e", HARNESS, os.path.join(PROJ, "web", "ext"), os.path.join(PROJ, "web", "geo", "theatres.json"), SCR],
                         capture_output=True, text=True, timeout=60)
finally:
    os.remove(SCR)
check(res.returncode == 0, "node harness ran: " + res.stderr[-400:])
R = json.loads(res.stdout)
want_ext = {"wire": "wire", "telegram": "telegram", "hazards": "hazards", "quakes": "hazards", "tsunami": "hazards", "radiation": "hazards",
            "ntas": "alerts", "ofac": "official", "squawk": "airspace", "tfr": "airspace", "cyber": "cyber", "bgp": "internet"}
check({k: v["group"] for k, v in R.items()} == want_ext, "extension streams and groups: %s" % {k: v["group"] for k, v in R.items()})
for k, v in R.items():
    its = v["items"] or []
    check(len(its) >= 1, k + " yields items from its fixture")
    check(all(i.get("ts") and i.get("title") and i.get("id") for i in its), k + ": every item has id, ts and title")

w = R["wire"]["items"][0]
check(w["th"] == "ukraine-russia" and w["cat"] == "drone" and w["label"] == "Kyiv Independent", "wire: theatre, category and outlet")
check(w["where"] == "Ukraine, Russia" and w["badge"] == "+2 more", "wire: countries by name and the outlets that also ran it")
t = R["telegram"]["items"][0]
check(t["label"] == "@chan" and t["ts"] == 1795150100000, "telegram: @channel label, post time")
h = R["hazards"]["items"][0]
check(h["ts"] == 1795151865000 and h["title"] == "Green alert: Earthquake in Papua New Guinea", "GDACS: sorted by the latest episode, alert in the title")
check(h["ll"] == [147.1, -6.2] and h["th"] == "indo-pacific", "GDACS: point and theatre")
q = R["quakes"]["items"][0]
check(q["title"] == "M4.1 earthquake: Uttaranchal, India" and q["badge"] == "tripwire" and q["th"] == "south-asia", "quakes: title, tripwire badge, theatre")
s = R["tsunami"]["items"][0]
check(s["title"] == "Volcanic activity commentary (cancelled): Sakurajima" and s["th"] == "indo-pacific" and s["ll"] == [130.7, 31.6],
      "tsunami/volcano: the server's cancelled label once, the volcano as the place, its theatre and point")
r = R["radiation"]["items"][0]
check("Munich" in r["title"] and "2.1×" in r["title"] and r["th"] == "europe-nato", "radiation flag: station, ratio, Europe")
n = R["ntas"]["items"][0]
check(n["th"] == "americas" and "(to 2027-01-31)" in n["title"], "NTAS: Americas, end date in the title")
o = R["ofac"]["items"][0]
check(o["day"] is True, "OFAC: date only")
check(o["ts"] == 1795046400000 and o["th"] == ["middle-east"] and o["badge"] == "counter-terrorism, iran", "OFAC: start of the UTC day, theatres, programmes")
sq = R["squawk"]["items"][0]
check(sq["ll"] == [8.16, 45.82] and sq["title"].startswith("Squawk 7600 (radio failure): JFA96S"), "squawk: position and title")
tf = R["tfr"]["items"][0]
check(tf["ts"] == 1795118400000, "TFR: sorted by when the FAA issued it, not by its future start")
check(tf["where"] == "from 11/26 14:00Z to 11/26 22:00Z" and tf["badge"] == "new" and tf["ll"] == [-95.4, 29.8], "TFR: active window, new badge, centre")
c1, c2 = R["cyber"]["items"]
check(c1["th"] == ["europe-nato"] and c1["where"] == "Spain" and c1["ll"] == TH["a3"]["ESP"][1:3], "cyber: placed by country")
check(c2["ts"] == 1795150800000 and c2["badge"] == "critical infra" and set(c2["th"]) == {"ukraine-russia", "europe-nato"},
      "cyber: ISO time fallback, critical-infrastructure badge, every country's theatre")
b = R["bgp"]["items"]
check(len(b) == 1 and b[0]["title"] == "Routing drop: Syria" and b[0]["th"] == "middle-east", "RIPE: only drops and dips")

# ---------- core streams and the Feed filter, from app.js's own source ----------
# 1.3.0: the page's own zone helpers (dayStart etc.); the harness runs once in UTC and once in Eastern
ZONE_BLOCK = APP[APP.index("  // --- zone helpers"):APP.index("  // --- end zone helpers")]
CORE = (line(APP, "  const isoMs = ") + ZONE_BLOCK + line(APP, "  const httpsUrl = ") + block(APP, "  function postKey(u) {")
        + APPFN + APP[APP.index("  // --- 1.4.0 title bar"):APP.index("  // --- end title bar")]  # 1.4.0: ccList, flags, titleBar
        + block(APP, "  function streamItems() {") + line(APP, "  const postOnly = ") + line(APP, "  const inTheatre = ")
        + block(APP, "  function streamFiltered() {") + APP[APP.index("  // Core streams."):APP.index("  function buildRail() {")])
CATS_SRC = APP[APP.index("  const CATS = {"):APP.index("};", APP.index("  const CATS = {")) + 3]
NOW = 1795161600000  # 2026-11-20T08:00:00Z
HARNESS2 = r"""
const fs = require("fs");
const TH = JSON.parse(fs.readFileSync(process.argv[1], "utf8")), FX = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const NOW = __NOW__; Date.now = () => NOW;
const DAY = 86400000, STREAMS = [], stream = (o) => STREAMS.push(o), feedSoon = () => {};
const localStorage = { getItem: () => process.argv[3] || null };  // the page's saved zone: "utc", or Eastern by default
const nf = (n) => (n == null ? "-" : Number(n).toLocaleString("en-US"));
__CATS__
const S = { theatre: "global", cats: new Set(Object.keys(CATS)), q: "", hours: 0, brush: null, feeds: FX.feeds, alerts: FX.alerts, events: FX.events };
const POSTS = { IL: { c: "IL", n: "Israel", city: "Jerusalem", lat: 31.77, lon: 35.22 } };
const emPost = (c) => POSTS[c], emWhere = (i) => (POSTS[i.c] ? POSTS[i.c].city : ""), emK = (k) => "K:" + k, emPopup = () => "popup";
__CORE__
const out = { streams: {}, filter: {} };
for (const st of STREAMS) { const d = st.data(); out.streams[st.key] = { group: st.group, items: d ? st.items(d) : null }; }
const run = (patch) => { Object.assign(S, { theatre: "global", cats: new Set(Object.keys(CATS)), q: "", hours: 0, brush: null }, patch);
  return streamFiltered().map((i) => i.id).sort(); };
out.filter.all = run({});
out.filter.me = run({ theatre: "middle-east" });
out.filter.h6 = run({ hours: 6 });
out.filter.brush = run({ brush: [NOW - 3 * 3600000, NOW - 3600000] });
out.filter.q = run({ q: "khasab" });
out.filter.items = streamItems().length;
out.filter.qcc = run({ q: "kuwait" });  // 1.4.0: an item's countries are searched too
out.cn = Object.fromEntries(streamItems().map((i) => [i.id, (i.cn || []).map((k) => k.a3)]));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
out.ne = ["SSD", "PSE", "XKX", "ESH", "ALA", "SS"].map((c) => (country(c) || {}).a3 || null);
out.bar = [titleBar(ccList(["UA", "Poland"]), ["🌐", "Global"], "Strike"), titleBar(ccList(["Atlantis"]), ["🌐", "Global"], "Wire"), FLAGS];
STREAMS.push({ key: "bad", group: "x", data: () => ({}), items: () => [{ id: "nan", ts: NaN, title: "t" }, { id: "neg", ts: -5, title: "t" }, { id: "ok", ts: NOW, title: "t" }] });
out.filter.bad = streamItems().filter((i) => i.src === "bad").map((i) => i.id);
process.stdout.write(JSON.stringify(out, (k, v) => (typeof v === "function" ? "[fn]" : v)));
""".replace("__NOW__", str(NOW)).replace("__CATS__", CATS_SRC).replace("__CORE__", CORE)
FX2 = {
    "feeds": {
        "official": {"items": [{"source": "CENTCOM", "title": "U.S. Forces Disable Cargo Vessel", "url": "https://www.centcom.mil/a", "date": "2026-11-20"},
                               {"source": "UK MoD", "title": "Defence Intelligence update on Ukraine", "url": "https://www.gov.uk/b", "date": "2026-11-20T06:30:00Z"}]},
        "ukmto": {"items": [{"num": 212, "type": "Attack", "date": "2026-11-18", "text": "6NM north of Khasab", "url": "https://www.ukmto.org/recent-incidents",
                             "coord": [56.247, 26.2841], "where": "6 NM north of Khasab, Oman"}]},
        "advisories": {"changes": [{"country": "Gaza", "from": 3, "to": 4, "seen": "2026-11-20T05:00:00Z"},
                                   {"country": "Mexico Travel Advisory", "from": 2, "to": 3, "seen": "2026-11-19T05:00:00Z"}]},
        "outages": {"countries": [{"code": "FI", "name": "Finland", "events": [{"start": "2026-11-19T07:30:00Z", "hours": 24.2, "ongoing": True, "source": "gtr"}]}],
                    "regions": [{"start": "2026-11-20T03:45:00Z", "hours": 0.9, "ongoing": False, "source": "bgp", "region": "Beqaa", "country": "LB"}]},
        "pla": {"date": "2026/11/20", "aircraft": 8, "plan_ships": 7, "official_ships": 2, "entered_adiz": 6, "url": "https://air.mnd.gov.tw/x"},
        "losses": {"date": "2026-11-19", "day": 1730, "increase": {"personnel_units": 1970, "tanks": 2, "artillery_systems": 7, "uav_systems": 515}},
        "czib": {"zones": [{"name": "Airspace of the Gulf", "country": "Bahrain, Kuwait, Qatar, Oman, United Arab Emirates", "issued": "2026-11-01", "valid_until": "30/04/2027"},
                           {"name": "Airspace of Syria", "country": "Syria", "issued": "2017-03-31"}]},
    },
    "alerts": {
        "embassy": {"items": [{"id": "e1", "c": "IL", "posts": ["IL"], "title": "Security Alert", "url": "https://il.usembassy.gov/x", "t": 1795150000, "kind": "security"}]},
        "regions": {"messages": [{"at": "2026-11-20T07:41:00Z", "who": "monitor", "url": "https://t.me/war_monitor/48130", "text": "2 groups of cruise missiles"}],
                    "ended": [{"from": "2026-11-19T21:43:00Z", "to": "2026-11-20T07:23:00Z", "dur": "9 h 40 min", "text": "air raid alert in Kupyanskyi"}]},
        "israel": {"events": [{"t": 1795155000, "label": "Rockets", "n": 3, "names": ["Sderot", "Nir Am", "Ibim"], "c": [34.6, 31.5], "th": 0}],
                   "messages": [{"time": 1795155100, "title": "Leave the shelter", "kind": "all clear", "body": "x"}]},
    },
    # the map pins the same Telegram post as the air-raid message, and a UKMTO page link that must not hide UKMTO
    "events": {"features": [{"properties": {"id": "p1", "url": "https://t.me/s/War_Monitor/48130?single"}},
                            {"properties": {"id": "p2", "url": "https://www.ukmto.org/recent-incidents?x=1"}}]},
}
SCR = os.path.join(PROJ, "tests", ".feed_fixture2.json")
with open(SCR, "w", encoding="utf-8") as fh:
    json.dump(FX2, fh)
try:
    res = subprocess.run([NODE, "-e", HARNESS2, os.path.join(PROJ, "web", "geo", "theatres.json"), SCR, "utc"], capture_output=True, text=True, timeout=60)
    res_et = subprocess.run([NODE, "-e", HARNESS2, os.path.join(PROJ, "web", "geo", "theatres.json"), SCR, ""], capture_output=True, text=True, timeout=60)
finally:
    os.remove(SCR)
check(res.returncode == 0, "core harness ran: " + res.stderr[-600:])
C = json.loads(res.stdout)
CS, FL = C["streams"], C["filter"]
# 1.3.0, Eastern: NOW is 08:00Z = 3 AM Eastern, so yesterday's date-only losses report (11/19) ended 3 h ago in Eastern
# (in the 6 h window) but 8 h ago in UTC (outside it); the other filter results are the same in both zones. The brush
# starts at 05:00Z, exactly Eastern midnight, where that day ends: a day's end is exclusive, so it stays out of the brush
check(res_et.returncode == 0, "core harness ran in Eastern: " + res_et.stderr[-400:])
FLE = json.loads(res_et.stdout)["filter"] if res_et.returncode == 0 else {}
check("loss:2026-11-19" in FLE.get("h6", []) and "loss:2026-11-19" not in FL["h6"], "a date-only day spans that day in the page's zone (Eastern vs UTC, 6 h window)")
check(all(FLE.get(k) == FL[k] for k in ("all", "me", "brush", "q", "items")), "Eastern and UTC agree on every other filter")
check({k: v["group"] for k, v in CS.items()} == want_core, "core streams run from app.js with their groups")
off = {i["label"]: i for i in CS["official"]["items"]}
check(off["CENTCOM"]["day"] is True and off["CENTCOM"]["ts"] == 1795132800000 and off["CENTCOM"]["th"] == "middle-east", "official: CENTCOM date only, Middle East")
check(off["UK MoD"]["day"] is False and off["UK MoD"]["ts"] == 1795156200000 and off["UK MoD"]["th"] == "ukraine-russia", "official: timed release, Ukraine by title")
u = CS["ukmto"]["items"][0]
check(u["title"] == "UKMTO 212 Attack: 6 NM north of Khasab, Oman" and u["ll"] == [56.247, 26.2841] and u["day"] is True, "UKMTO: title, point, date only")
e = CS["embassy"]["items"][0]
check(e["ts"] == 1795150000000 and e["th"] == ["middle-east"] and e["ll"] == [35.22, 31.77] and e["where"] == "Jerusalem" and e["badge"] == "K:security",
      "embassy: seconds to ms, theatre by post, post point")
ar = {i["id"][:3]: i for i in CS["airalerts"]["items"]}
check(ar["ar:"]["th"] == "ukraine-russia" and ar["are"]["title"] == "Ended: air raid alert in Kupyanskyi (9 h 40 min)" and ar["are"]["ts"] == 1795159380000,
      "air raid: SITREP message, and an ended alert at its end time")
il = CS["tzeva"]["items"]
check(il[0]["title"] == "Rockets: 3 areas" and il[0]["ll"] == [34.6, 31.5] and il[1]["label"] == "Home Front Command", "Israel: siren event and Home Front Command message")
adv = {i["title"]: i for i in CS["advisories"]["items"]}
check(adv["Travel advisory raised: Gaza, level 3 → 4"]["th"] == "middle-east", "advisory change: Gaza resolves to the Middle East")
check(adv["Travel advisory raised: Mexico Travel Advisory, level 2 → 3"]["th"] == "americas", "advisory change: the State Dept's 'Mexico Travel Advisory' resolves")
o = {i["title"]: i for i in CS["outages"]["items"]}
check(o["Internet outage (ongoing): Finland"]["th"] == "europe-nato" and o["Internet outage: Beqaa, Lebanon"]["th"] == "middle-east", "outages: country and region, placed")
check(CS["pla"]["items"][0]["ts"] == 1795132800000 and "8 aircraft (6 in the ADIZ)" in CS["pla"]["items"][0]["title"], "PLA: slash date, figures")
check("+1,970 personnel" in CS["losses"]["items"][0]["title"] and CS["losses"]["items"][0]["th"] == "ukraine-russia", "losses: daily increase")
cz = {i["id"]: i for i in CS["czib"]["items"]}
check(cz["czib:Airspace of the Gulf"]["th"] == ["middle-east"] and cz["czib:Airspace of the Gulf"]["ll"], "CZIB: a zone naming five Gulf states lands in the Middle East")
# the filter
check(FL["items"] == sum(len(v["items"]) for v in CS.values()), "every core item reaches the Feed's item list")
check("ar:https://t.me/war_monitor/48130" not in FL["all"], "a Telegram post the map already pins is dropped")
check("ukmto:212" in FL["all"], "a pin citing UKMTO's shared incidents page does not hide UKMTO")
check("ukmto:212" in FL["me"] and "off:https://www.centcom.mil/a" in FL["me"] and "io:FI::2026-11-19T07:30:00Z:gtr" not in FL["me"], "theatre filter keeps the Middle East only")
check("czib:Airspace of the Gulf" in FL["me"], "theatre filter takes a list of theatres")
check("off:https://www.centcom.mil/a" in FL["h6"] and "ukmto:212" not in FL["h6"] and "czib:Airspace of Syria" not in FL["h6"],
      "6h counts back from now; today's date-only items stay, older days go")
check("off:https://www.gov.uk/b" in FL["brush"] and "il:1795155000Rockets" in FL["brush"] and "are:2026-11-19T21:43:00Zair raid alert in Kupyanskyi" not in FL["brush"],
      "brush keeps items inside its window")
check(FL["q"] == ["ukmto:212"], "search reads the item's text too")
check(FL["bad"] == ["ok"], "a stream item with a NaN or negative time is dropped, not drawn")
check(re.search(r"safeFeed\(list\);\n    renderTheatreCounts\(\);", APP) is not None, "a Feed failure cannot stop the rest of render()")


# 1.4.0: title bars. Core items carry cc for the countries the source names, and nothing is guessed
CN = C["cn"]
want_cn = {"em:e1": ["ISR"], "il:1795155000Rockets": ["ISR"], "ar:https://t.me/war_monitor/48130": ["UKR"], "adv:Gaza2026-11-20T05:00:00Z": None,
           "adv:Mexico Travel Advisory2026-11-19T05:00:00Z": ["MEX"], "io:FI::2026-11-19T07:30:00Z:gtr": ["FIN"], "io:LB:Beqaa:2026-11-20T03:45:00Z:bgp": ["LBN"],
           "pla:2026/11/20": ["TWN"], "loss:2026-11-19": ["UKR"], "czib:Airspace of the Gulf": ["BHR", "KWT", "QAT", "OMN", "ARE"], "czib:Airspace of Syria": ["SYR"],
           "off:https://www.centcom.mil/a": [], "off:https://www.gov.uk/b": [], "ukmto:212": []}
check(all(k in CN for k in want_cn), "title bar: every checked core item reached the Feed (%s)" % [k for k in want_cn if k not in CN])
check(all(CN.get(k) == v for k, v in want_cn.items() if v is not None), "title bar: core countries %s" % {k: CN.get(k) for k in want_cn})
check(len(CN.get("adv:Gaza2026-11-20T05:00:00Z") or []) == 1, "title bar: the State Dept's Gaza resolves to one place")
check(FL["qcc"] == ["czib:Airspace of the Gulf"], "search finds an item by a country only its title bar names")
bar_cc, bar_none, flags = C["bar"]
check(">UA<" in bar_cc and ">Ukraine<" in bar_cc and ">+1<" in bar_cc and 'title="Poland"' in bar_cc and ">Strike<" in bar_cc and flags is False,
      "title bar: no emoji flags in node, so the ISO-2 box; primary country, +1 with the rest in the tooltip, category")
check('class="cn gl">Global<' in bar_none and ">Wire<" in bar_none and 'class="fl tx"' not in bar_none, "title bar: an unknown country is not guessed; the fallback names the place")
check("Day \" + s.map_day" not in APP and '"Source map"],' not in APP, "header: the source map's Day tile is gone (1.4.0)")
check(C["ne"] == ["SDS", "PSX", "KOS", "SAH", "ALD", "SDS"], "country(): ISO-3 codes theatres.json keys by Natural Earth's code resolve (%s)" % C["ne"])
PR, SR = block(APP, "  function pinRow(f) {"), block(APP, "  function streamRow(i, n) {")
check('<span class="wh">${when}</span>' in APP and all('class="time"' in r.split('<div class="m">')[0] and 'class="time"' not in r.split('<div class="m">')[1] for r in (PR, SR)),
      "1.4.1: a row's date, time and time since sit in its title bar, not the meta line")
check(".feed .tb .wh {" in CSS and ".feed .tb .ag {" in CSS, "style.css lays out the time in the bar")
LAYER_SRC = APP[APP.index("  const LAYERS = ["):APP.index("  ];", APP.index("  const LAYERS = ["))]
check(", false]," not in LAYER_SRC and LAYER_SRC.count(", true],") >= 17 and 'layout: { visibility: "none" }' not in APP, "1.4.2: every core layer starts on")
check(not any(re.search(r"GTX\.layer\(\{[^\n]*on: false", v) for v in EXT.values()), "1.4.2: no extension layer starts off")
# 1.4.3: tooltips. Every header tile the page or an extension draws has a description; the PC tooltip box exists
KPI_SRC = APP[APP.index("  const KPI_TIP = {"):APP.index("  };", APP.index("  const KPI_TIP = {"))]
labels = ["Analyst tension", "Events, last 6h", "Events, 24h", "UA / RU regions on alert", "Israel alerts, 24h", "Israel sirens NOW", "Thermal-corroborated",
          "Mil aircraft (ADS-B)", "UKMTO incidents, 7d", "Hormuz tankers/day", "RU losses (UA GS)", "PLA aircraft / ships", "Emergency squawks now",
          "Routing drops (RIPE)", "Hazard alerts (Orange/Red)", "Quakes in watch areas", "Tsunami bulletin", "Radiation flags", "NTAS advisory"]
src_all = APP + "".join(EXT.values())
check(all('"%s"' % l in src_all for l in labels), "tooltips: every listed KPI label is still drawn: %s" % [l for l in labels if '"%s"' % l not in src_all])
check(all('"%s":' % l in KPI_SRC for l in labels), "tooltips: every KPI has a description: %s" % [l for l in labels if '"%s":' % l not in KPI_SRC])
check('matchMedia("(hover: hover) and (pointer: fine)")' in APP and "#gtip {" in CSS and "white-space: pre-line" in CSS, "tooltips: a styled box on a mouse only")
check('title="Category: ${esc(cat)}"' in APP and 'data-h="6" title=' in INDEX, "tooltips: the title bar's category and the time range")
check(".feed .tb {" in CSS and ".feed .tb .ct {" in CSS, "style.css styles the title bar")

# 1.5.2: the GitHub Pages copy (and only it) adds "--GitHub" to the tab title
check('if (PUBLIC && !/ --GitHub$/.test(document.title)) document.title += " --GitHub";' in APP and
      APP.index("const PUBLIC = ") < APP.index('document.title += " --GitHub"') and APP.count("document.title") == 2,
      "the tab title gains ' --GitHub' on a github.io host only, once, and nothing else sets the title")
print("%d checks passed" % ok)
