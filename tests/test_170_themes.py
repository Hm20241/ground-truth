"""Offline tests for 1.7.0: themes (Classic, Dispatch, Atlas, Watch Floor) and the theme button.

Static checks on the page files, and node runs web/themes/switch.js and web/themes/open.js against a stub browser
(no DOM library, no network). A theme is one page at the web root plus its own folder under web/themes/.

Run: python3 -I tests/test_170_themes.py
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


VERSION = read("VERSION").strip()
INDEX, APP, CSS, SWITCH, OPEN = read("web/index.html"), read("web/app.js"), read("web/style.css"), read("web/themes/switch.js"), read("web/themes/open.js")
THEMES = {"dispatch": "dispatch.html", "atlas": "atlas.html", "floor": "floor.html"}

# ---------- version ----------
check(tuple(map(int, VERSION.split("."))) >= (1, 7, 0), "VERSION is 1.7.0 or later")

# ---------- Classic: opener, button slot, switcher ----------
check('<html lang="en" data-gt-theme="classic">' in INDEX, "index.html says it is the Classic theme")
i_open, i_css = INDEX.find('src="themes/open.js?v=%s"' % VERSION), INDEX.find('href="style.css')
check(-1 < i_open < i_css, "index.html loads themes/open.js first, before its stylesheet, with ?v=" + VERSION)
i_live, i_slot, i_kpis = INDEX.find('id="live"'), INDEX.find('id="themeslot"'), INDEX.find('id="kpis"')
check(-1 < INDEX.find('class="livewrap"') < i_live < i_slot < i_kpis, "the theme slot sits after the version / live pill, inside the same wrapper, before the figures")
check('src="themes/switch.js?v=%s" data-mount="#themeslot"' % VERSION in INDEX, "index.html loads the switcher and mounts it in the slot")
check(INDEX.find("themes/switch.js") < INDEX.find('src="app.js'), "the switcher loads before app.js")
check(".livewrap { display: flex; flex-direction: column;" in CSS, "the wrapper stacks the pill over the theme button")
check("--gtt-menu-bg" in CSS, "Classic sets the switcher's colours")
check(re.search(r'ships: \[[^\]]*"ship-mil-lbl"', APP) is not None, "warship name labels belong to the Ships layer group (they stayed on when Ships was off)")

# ---------- switcher file ----------
ids = re.findall(r'\{ id: "(\w+)", name: "([^"]+)", href: "([^"]+)"', SWITCH)
check([i[0] for i in ids] == ["classic", "dispatch", "atlas", "floor"], "the switcher lists Classic, Dispatch, Atlas, Watch Floor in that order")
check(all(os.path.isfile(os.path.join(PROJ, "web", href)) for _i, _n, href in ids), "every theme's page exists at the web root")
check(all(not href.startswith(("/", "http")) for _i, _n, href in ids), "theme links are relative")
check('role="menu"' in SWITCH.replace("setAttribute(\"role\", \"menu\")", 'role="menu"') and "menuitemradio" in SWITCH and "aria-expanded" in SWITCH, "the menu is a labelled menu of radio items")
check("Escape" in SWITCH and "ArrowDown" in SWITCH, "the menu works from the keyboard")
check("min-height:44px" in SWITCH, "menu rows are at least 44 px high")
check("fetch(" not in SWITCH and "XMLHttpRequest" not in SWITCH and "fetch(" not in OPEN, "the theme files make no requests")

# ---------- theme pages ----------
for tid, page in THEMES.items():
    html = read("web/" + page)
    check('data-gt-theme="%s"' % tid in html, "%s names its theme on <html>" % page)
    check("themes/switch.js?v=%s" % VERSION in html, "%s loads the shared switcher with ?v=%s" % (page, VERSION))
    own = re.findall(r'(?:src|href)="(themes/%s/[^"]+)"' % tid, html)
    check(len(own) >= 2, "%s loads its own CSS and JS from themes/%s/ (%d)" % (page, tid, len(own)))
    check(all(u.endswith("?v=" + VERSION) for u in own), "%s: every theme asset is cache-busted with ?v=%s" % (page, VERSION))
    check(all(os.path.isfile(os.path.join(PROJ, "web", u.split("?")[0])) for u in own), "%s: every theme asset exists" % page)
    refs = re.findall(r'(?:src|href)="([^"]+)"', html)
    local = [u for u in refs if not u.startswith(("http://", "https://", "#", "data:", "mailto:"))]
    check(all(not u.startswith("/") for u in local), "%s: local URLs are relative (work under /gt/ and ingress)" % page)
    check(all(os.path.isfile(os.path.join(PROJ, "web", u.split("?")[0].split("#")[0])) for u in local if u.split("?")[0].split("#")[0]), "%s: every local file it names exists" % page)
    folder = os.path.join(PROJ, "web", "themes", tid)
    files = sorted(f for f in os.listdir(folder) if f.endswith((".js", ".css")))
    src = html + "".join(read("web/themes/%s/%s" % (tid, f)) for f in files)
    js = "".join(read("web/themes/%s/%s" % (tid, f)) for f in files if f.endswith(".js"))
    check("GTTheme.mount(" in src, "%s draws the theme button" % tid)
    check("GTTheme.version" in src, "%s shows the version beside its live status" % tid)
    check("GTTheme.go(" in src and "Open Classic" in src and "classic" in src, "%s: placeholders offer Classic" % tid)
    check("in this concept" not in src.lower(), "%s: no 'in this concept' wording left" % tid)
    check("Not in this theme yet" in src, "%s: placeholders say 'Not in this theme yet'" % tid)
    check(all(re.search(r"\b%s\b" % n, js) for n in ("geoconfirmed", "cir", "kinetic")) and "postKey" in js, "%s merges the three extra pin sources like Classic (same-post rule)" % tid)
    check(re.search(r'["\'`](?:https?:)?//(?:(?:\d{1,3}\.){3}\d{1,3}|localhost)', src) is None, "%s: no numeric or localhost address" % tid)
    check(re.search(r'fetch\(\s*["\'`]/', js) is None and '"/api/' not in js and "'/api/" not in js and "`/api/" not in js, "%s: api paths are relative" % tid)
    check(re.search(r'method:\s*["\'](?:POST|PUT|DELETE|PATCH)', js) is None, "%s only reads (GET)" % tid)
    check("api/digest" not in js, "%s does not call the private digest endpoint" % tid)
    check(re.search(r"inner[Ww]idth\s*>=\s*1800", js) is None, "%s: the wall view never starts by itself on a wide screen" % tid)

# ---------- behaviour: node against a stub browser ----------
node = shutil.which("node")
check(node is not None, "node is installed (needed for the behaviour checks)")
HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const [switchSrc, openSrc] = process.argv.slice(-2).map((p) => fs.readFileSync(p, "utf8"));
function world(o) {
  const store = Object.assign({}, o.store || {});
  const loc = { search: o.search || "", hash: o.hash || "", hostname: o.host === undefined ? "gt.example.net" : o.host, href: "start", replaced: null, replace(u) { this.replaced = u; } };
  const ls = o.blocked ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } }
    : { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  const doc = { title: "Ground Truth", currentScript: { getAttribute: (n) => (n === "src" ? "themes/switch.js?v=9.9.9" : null) }, readyState: "complete",
    documentElement: { getAttribute: (n) => (n === "data-gt-theme" ? o.theme || null : null) }, addEventListener() {}, getElementById: () => null };
  const win = { addEventListener() {} };
  const ctx = { window: win, document: doc, localStorage: ls, location: loc };
  win.localStorage = ls; win.location = loc;
  return { ctx, store, loc, win, doc };
}
const out = {};
// open.js
const op = (o) => { const w = world(o); vm.runInNewContext(openSrc, w.ctx); return w.loc.replaced; };
out.open = {
  plain_dispatch: op({ store: { "gt.theme": "dispatch" } }), plain_atlas: op({ store: { "gt.theme": "atlas" } }), plain_floor: op({ store: { "gt.theme": "floor" } }),
  classic: op({ store: { "gt.theme": "classic" } }), none: op({}), junk: op({ store: { "gt.theme": "../evil" } }), junk2: op({ store: { "gt.theme": "dispatch.html?x" } }),
  query: op({ store: { "gt.theme": "atlas" }, search: "?embed=1" }), hash: op({ store: { "gt.theme": "atlas" }, hash: "#x" }), blocked: op({ blocked: true }),
};
// switch.js
const sw = (o) => { const w = world(o); vm.runInNewContext(switchSrc, w.ctx); return Object.assign(w, { T: w.win.GTTheme }); };
let w = sw({ theme: "dispatch" });
out.current = w.T.current; out.version = w.T.version; out.ids = w.T.THEMES.map((t) => t.id);
out.goClassic = w.T.go("classic"); out.afterGo = { href: w.loc.href, saved: w.store["gt.theme"] };
w = sw({ theme: "atlas" }); out.goSame = w.T.go("atlas"); out.sameHref = w.loc.href; out.sameSaved = w.store["gt.theme"];
w = sw({}); out.defaultTheme = w.T.current; out.goBad = w.T.go("nope"); out.badHref = w.loc.href; out.badSaved = w.store["gt.theme"] || null;
out.goFloor = w.T.go("floor"); out.floorHref = w.loc.href;
w = sw({ blocked: true }); out.blockedGo = w.T.go("dispatch"); out.blockedHref = w.loc.href; out.blockedSaved = w.T.saved();
out.mountMissing = w.T.mount(null);
out.titles = {}; [["server", "10.0.0.5"], ["name", "server.lan"], ["ha", "homeassistant.local"], ["local", "localhost"], ["loop", "127.0.0.1"], ["v6", "[::1]"], ["sub", "gt.localhost"],
  ["pages", "someone.github.io"], ["PAGES", "Someone.GitHub.IO"], ["fake", "github.io.example.com"], ["file", ""]].forEach(([k, h]) => { const x = sw({ host: h }); out.titles[k] = x.doc.title; });
out.copy = sw({ host: "localhost" }).T.copy;
console.log(JSON.stringify(out));
"""
r = subprocess.run([node, "-e", HARNESS, "--", os.path.join(PROJ, "web/themes/switch.js"), os.path.join(PROJ, "web/themes/open.js")],
                   capture_output=True, text=True, timeout=60)
check(r.returncode == 0, "the node harness runs (%s)" % r.stderr.strip()[-300:])
o = json.loads(r.stdout)
op = o["open"]
check(op["plain_dispatch"] == "dispatch.html" and op["plain_atlas"] == "atlas.html" and op["plain_floor"] == "floor.html", "a plain visit opens the remembered theme, by a relative URL")
check(op["classic"] is None and op["none"] is None, "Classic, or no choice yet, stays on index.html")
check(op["junk"] is None and op["junk2"] is None, "only the three known theme names are followed")
check(op["query"] is None and op["hash"] is None, "a link with a query or a hash stays on Classic")
check(op["blocked"] is None, "blocked storage does not break the page")
check(o["current"] == "dispatch" and o["defaultTheme"] == "classic", "the switcher reads the page's theme, Classic when unnamed")
check(o["version"] == "9.9.9", "the switcher takes the version from its own ?v=")
check(o["goClassic"] is True and o["afterGo"] == {"href": "index.html", "saved": "classic"}, "choosing Classic remembers it and opens index.html")
check(o["goSame"] is True and o["sameHref"] == "start" and o["sameSaved"] == "atlas", "choosing the current theme remembers it and does not reload")
check(o["goBad"] is False and o["badHref"] == "start" and o["badSaved"] is None, "an unknown theme does nothing")
check(o["goFloor"] is True and o["floorHref"] == "floor.html", "choosing Watch Floor opens floor.html")
check(o["blockedGo"] is True and o["blockedHref"] == "dispatch.html" and o["blockedSaved"] is None, "with storage blocked the link still works")
check(o["mountMissing"] is None, "mounting into a missing element is a no-op")
t = o["titles"]
check(t["server"] == t["name"] == t["ha"] == "Ground Truth: Server", "the server's copy (and Home Assistant's view of it) is titled 'Ground Truth: Server'")
check(t["local"] == t["loop"] == t["v6"] == t["sub"] == t["file"] == "Ground Truth: Local" and o["copy"] == "Local", "a copy run on this computer is titled 'Ground Truth: Local'")
check(t["pages"] == t["PAGES"] == "Ground Truth: GitHub", "the github.io copy is titled 'Ground Truth: GitHub'")
check(t["fake"] == "Ground Truth: Server", "only a host ending in .github.io counts as the GitHub copy")

print("test_170_themes: %d checks passed" % ok)
