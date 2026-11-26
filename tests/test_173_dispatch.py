"""Offline tests for 1.7.3, the Dispatch theme: feeds are asked for again at each reload, and smaller fixes.

Static checks on web/themes/dispatch/*.js, and node runs the feed cache (fetchFeed and due, cut out of dispatch.js)
against a stub clock and a stub api (no DOM library, no network).

Run: python3 -I tests/test_173_dispatch.py
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


CORE, MAP, SEC, TICK = (read("web/themes/dispatch/" + n) for n in ("dispatch.js", "dispatch-map.js", "dispatch-sections.js", "dispatch-ticker.js"))

# ---------- the feed cache: shorter than the reload, and a feed is asked for again when it is due ----------
m = re.search(r"const FEED_TTL = (\d+)", CORE)
check(m is not None and 60000 <= int(m.group(1)) < 180000, "a feed is kept for less than the 3-minute reload, so each reload gets a new copy")
check("setInterval(() => { if (!document.hidden) loadCore(); }, 180000)" in CORE, "the page still reloads every 3 minutes")
check("< 180000) return Promise.resolve(S.feeds[name])" not in CORE, "the old 3-minute cache test is gone")
check("due, statusKnown" in CORE, "due() is handed to the other Dispatch files")
check("const missing = page.feeds.filter(G.due);" in SEC, "a section asks again for its feeds that are due (not only the ones never loaded)")
check('topicFeeds().some(G.due)) loadTopicFeeds()' in MAP and 'G.on("data"' in MAP, "the open map topic asks again for its feeds at each reload")
check('["home", "map", "wall"].includes(S.route.view)' in MAP, "a map that is not on the page does not refresh its topic feeds")
check('G.on("feed", () => { drawTopicFeeds(); });' in MAP and 'emit("feed", name)' in CORE, "the map redraws a source as soon as a new copy of its feed arrives (popups look entries up by position)")
check('document.addEventListener("visibilitychange"' in CORE and "Date.now() - S.loadedAt >= 180000" in CORE, "a tab shown again after being hidden reloads at once")

# ---------- a source is rebuilt only for a new copy of its feed ----------
for name in ("front", "mil", "gpsjam", "ukmto", "portwatch", "ships", "quakes", "hazards"):
    check('fresh("%s")' % name in MAP, "the %s source is rebuilt only when its feed is a new copy" % name)
check("window.h3 && fresh(\"gpsjam\")" in MAP, "GPS interference is not marked drawn before its hexagon decoder has loaded")

# ---------- ships: the reader is told how old the positions are ----------
check("G.shipsAt = (sh) =>" in MAP and "Newest position heard" in MAP and "Newest position heard" in SEC, "the Sea caption and the Sea section say when the newest ship position was heard")
check("Heard ${esc(G.when(t))} ${G.zlabel()}" in MAP, "a ship popup says when the ship was heard, in the page's zone")
check("The last refresh of the ship feed failed" in MAP, "the Sea caption says so when the ship feed's last refresh failed")
check("No ship figures have arrived yet." in SEC, "a ships feed with no areas gets a plain line, not an empty table")
check("((F.ships || {}).points || [])[p.n]" in MAP and "((F.ukmto || {}).items || [])" in MAP and "((F.portwatch || {}).chokepoints || [])[p.n]" in MAP, "popups do not throw when a feed is missing")
check("(F.quakes.geojson.features[p.n] || {}).properties; if (q)" in MAP and "(F.hazards.geojson.features[p.n] || {}).properties; if (h)" in MAP, "quake and hazard popups skip an entry that is no longer there")

m = re.search(r'id: "ship-dot"[^\n]*"circle-radius": zoomW\(([\d.]+),', MAP)
check(m is not None and float(m.group(1)) >= 1.8, "ship dots are at least 1.8 px at world zoom (they were 1.2 px and close to invisible)")
check(">Ship heard</span>" in MAP and ">Tanker</span>" in MAP, "the Sea caption has a key for the ship dots")
check('if (topic === "sea" && F.ships) what +=' in MAP, "the In view count names the ships in view")

# ---------- smaller fixes ----------
check("try { q[k] = decodeURIComponent(v || \"\"); } catch (e) { q[k] = \"\"; }" in CORE, "a broken %-code in the address does not stop the page")
check(CORE.count("Number.isFinite(i.ts_ms)") == 1 and "!Number.isFinite(p.ts_ms)" in CORE, "an entry whose time is not a number is left out (it would stop the list drawing)")
check("if (r.q.t && jump)" in SEC and 'G.on("route", () => { jump = true; });' in SEC, "the jump to a theatre happens once per visit, not at every reload")
check("nf((c.avg7 || {}).total)" in SEC, "a chokepoint with no 7-day figure does not stop the Sea page")
check("${nf(c.change_vs_year_pct.total)}%)" in MAP, "the chokepoint popup formats the change figure (no raw feed value in the popup)")

# ---------- house rules for the theme's files ----------
for name, src in (("dispatch.js", CORE), ("dispatch-map.js", MAP), ("dispatch-sections.js", SEC), ("dispatch-ticker.js", TICK)):
    for tag in re.findall(r'<a [^>]*target="_blank"[^>]*>', src):
        check('rel="noopener noreferrer"' in tag, "%s: every link that opens a new tab has rel=noopener" % name)
    check(re.search(r"\bmethod\s*:", src) is None and "XMLHttpRequest" not in src and "sendBeacon" not in src, "%s makes GET requests only" % name)
    for url in re.findall(r'fetch\(\s*"([^"]*)"', src):
        check(not url.startswith(("/", "http")), "%s: fetch URLs are relative (%s)" % (name, url))
css = read("web/themes/dispatch/dispatch.css")
small = [float(x) for x in re.findall(r"font(?:-size)?:[^;{}]*?(\d+(?:\.\d+)?)px", css) if float(x) < 14]
check(not small, "no fixed type size under 14 px in dispatch.css")

# ---------- node: the feed cache ----------
node = shutil.which("node")
if node:
    a, b = CORE.find("  const FEED_TTL ="), CORE.find("  // ---------- one rule for pins")
    check(-1 < a < b, "the feed cache block is where the test expects it")
    js = r"""
let NOW = 1000000; const realNow = Date.now; Date.now = () => NOW;
const S = { feeds: {}, failed: {}, status: { feeds: { ships: {}, wire: {} } } }, sent = [], calls = [];
let fail = false;
const api = (p) => { calls.push(p); return fail ? Promise.reject(new Error("502")) : Promise.resolve({ ok: p !== "feed/ships", at: "t", data: { n: calls.length } }); };
const emit = (ev, a) => sent.push(ev + ":" + a);
const absent = (name) => !(name in S.status.feeds);
const statusKnown = Promise.resolve();
""" + CORE[a:b] + r"""
(async () => {
  const out = {};
  out.due0 = due("ships"); out.dueAbsent = due("gfw");
  const first = await need("ships");
  out.first = [first.n, first._ok, calls.length, sent.join()]; out.dueAfter = due("ships");
  NOW += FEED_TTL - 1; await need("ships"); out.cached = calls.length; out.dueJustUnder = due("ships");
  NOW += 1; out.dueAtTtl = due("ships"); const second = await need("ships"); out.second = [second.n, calls.length, second !== first];
  // a failed refresh keeps the copy in hand, marks the failure, and is not due again until the wait is over
  NOW += 180000; fail = true; const third = await need("ships"); out.failKeeps = [third === second, S.failed.ships === true, due("ships")];
  NOW += 180000; fail = false; out.dueAfterFail = due("ships"); const fourth = await need("ships"); out.recovered = [fourth.n, S.failed.ships === undefined];
  // a feed that has never loaded and fails: rejected, marked, retried later
  fail = true; out.neverLoaded = await need("wire").then(() => "resolved", () => "rejected"); out.wireDue = due("wire");
  NOW += FEED_TTL; fail = false; out.wireDueLater = due("wire"); out.wireBack = (await need("wire")).n > 0;
  out.absentAsk = await need("gfw").then(() => "resolved", () => "rejected"); out.calls = calls.join();
  // two askers at once share one request
  NOW += 180000; const before = calls.length; await Promise.all([need("ships"), need("ships")]); out.shared = calls.length - before;
  console.log(JSON.stringify(out));
})();
"""
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    check(r.returncode == 0, "node ran the feed cache: " + r.stderr[-300:])
    o = json.loads(r.stdout)
    check(o["due0"] is True and o["dueAbsent"] is False, "a feed never asked for is due; a feed this copy lacks never is")
    check(o["first"] == [1, False, 1, "feed:ships"] and o["dueAfter"] is False, "the first ask fetches, keeps the envelope's ok flag, announces the new copy, and the feed is then not due")
    check(o["cached"] == 1 and o["dueJustUnder"] is False, "inside the keep time the copy in hand answers")
    check(o["dueAtTtl"] is True and o["second"] == [2, 2, True], "at the keep time the feed is due and a new copy is fetched")
    check(o["failKeeps"] == [True, True, False], "a failed refresh keeps the copy in hand, marks the failure, and does not ask again at once")
    check(o["dueAfterFail"] is True and o["recovered"][0] > 2 and o["recovered"][1] is True, "after the wait a failed feed is asked for again and the failure mark is cleared")
    check(o["neverLoaded"] == "rejected" and o["wireDue"] is False and o["wireDueLater"] is True and o["wireBack"] is True, "a feed that failed with nothing in hand is retried later and comes back")
    check(o["absentAsk"] == "rejected" and "gfw" not in o["calls"], "a feed this copy lacks is never requested")
    check(o["shared"] == 1, "two askers at once share one request")
else:
    print("node not found: skipped the feed cache run")

print("ok: %d checks" % ok)
