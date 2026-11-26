"""Offline tests for 1.7.1: themes ask only for feeds the copy lists, and Eastern times read am/pm in every theme."""
import pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
R = lambda p: (ROOT / p).read_text(encoding="utf-8")
n = bad = 0
def check(ok, what):
    global n, bad
    n += 1
    if not ok:
        bad += 1
        print("FAIL:", what)
V = R("VERSION").strip()
check(tuple(map(int, V.split("."))) >= (1, 7, 1), "VERSION is 1.7.1 or later")
for page in ("index.html", "dispatch.html", "atlas.html", "floor.html"):
    h = R("web/" + page)
    check("?v=" + V in h and "?v=1.7.0" not in h, page + " loads its files at the current version")
D, DS = R("web/themes/dispatch/dispatch.js"), R("web/themes/dispatch/dispatch-sections.js")
A, AU = R("web/themes/atlas/core.js"), R("web/themes/atlas/ui.js")
F, FB = R("web/themes/floor/core.js"), R("web/themes/floor/board.js")
APP = R("web/app.js")
for name, src in (("Dispatch", D + DS), ("Atlas", A + AU), ("Watch Floor", F + FB + R("web/themes/floor/panels.js"))):
    check("Not on this copy." in src, name + " says when the copy does not carry a feed")
    check(re.search(r"status[\s\S]{0,40}\.feeds|feeds\b[\s\S]{0,60}status", src), name + " reads the status's feed list")
m = re.search(r"const fmtTime = [\s\S]*?\n\s*// The analyst", D)
check(m and '"en-US"' in m.group(0) and 'hour: "numeric"' in m.group(0) and '"America/New_York"' in m.group(0), "Dispatch: Eastern times are am/pm")
check('toLocaleTimeString("en-GB", { timeZone: zone()' not in D, "Dispatch: no 24-hour clock for the page's zone")
check("zText" in D and "G.zText" in DS and "createTreeWalker" in DS, "Dispatch: UTC times in text get Eastern beside them")
check("(?! \\()" in D, "Dispatch: a time already converted is not converted twice")
check("WF.zText" in F and "WF.zText" in FB and "Times inside the text are UTC" not in FB, "Watch Floor: analyst times get Eastern beside them")
check("hour12: true" in A and "hour12: true" in F and "hour12: true" in APP, "Classic, Atlas and Watch Floor format Eastern as am/pm")
check('const tzT = (ms, tz) => new Date(ms).toLocaleTimeString("en-US"' in APP, "Classic: local alert times are am/pm")
check('`${p.timeZoneName} · ${utc.slice(11, 16)}Z`' not in APP, "Classic: no UTC time under the Eastern clock")
for src, name in ((D, "dispatch"), (A, "atlas"), (F, "floor")):
    check(not re.search(r"method:\s*[\"'](POST|PUT|DELETE)", src), name + " is GET only")
print("test_171_copy_times: %d checks, %d failed" % (n, bad))
sys.exit(1 if bad else 0)
