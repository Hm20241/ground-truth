"""Offline checks for gt/translate.py (Ground Truth 1.5.0). Never touches the network.

  python3 -I tests/test_translate.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="gt-tr-")
os.environ["GT_DATA"] = TMP
sys.path.insert(0, ROOT)
from gt import translate, wire  # noqa: E402

ok = 0


def check(cond, msg):
    global ok
    if not cond:
        print("FAIL: " + msg)
        sys.exit(1)
    ok += 1
    print("ok   " + msg)


NOW = 1795300000
check(translate.VERSION == "1.1" and translate.FEEDS == ("wire", "telegram", "power") and translate.RECLASSIFY == ("wire", "telegram"),
      "version and the feeds it serves (1.1: power too; only wire and telegram are reclassified)")
check(wire.CACHE.startswith(TMP), "the store lives in the feeds' cache folder (GT_DATA)")

feed = {"count": 4, "items": [
    {"id": "a1", "lang": "ru", "title": "Удар по Польше", "summary": "Подробности", "category": "other", "tags": []},
    {"id": "b2", "lang": "uk", "title": "Кривий Ріг", "category": "other", "tags": []},
    {"id": "c3", "lang": "en", "title": "Already English", "category": "political", "tags": []},
    {"id": "d4", "lang": "es", "title": "Sin traducción", "category": "other", "tags": []}]}
check(translate.apply(feed) is feed, "nothing stored: the feed is served as it is")

r = translate.store([
    {"id": "a1", "from": "ru", "title": "Missile strike on Poland\x07", "summary": "Details"},
    {"id": "b2", "from": "uk", "title": "Kryvyi Rih"},
    {"id": "c3", "from": "en", "title": "Should not replace English"},
    {"id": "bad id!", "from": "ru", "title": "x"},
    {"id": "e5", "from": "Russian", "title": "x"},
    {"id": "f6", "from": "ru", "title": "   "},
    "not a dict"], {"model": "claude-haiku-5-5"}, now=NOW)
check(r == {"stored": 3, "rejected": 4, "total": 3}, "store: 3 kept; bad id, bad language code, empty title and a non-object rejected: %s" % r)
check(os.path.exists(os.path.join(wire.CACHE, translate.FILE)), "the store is saved to disk")

out = translate.apply(feed)
by = {i["id"]: i for i in out["items"]}
check(out is not feed and feed["items"][0]["title"] == "Удар по Польше", "apply() returns a copy; the cached feed keeps its original text")
a = by["a1"]
check(a["title"] == "Missile strike on Poland" and a["title_orig"] == "Удар по Польше", "title in English (control character stripped), original kept")
check(a["summary"] == "Details" and a["summary_orig"] == "Подробности", "summary in English, original kept")
check(a["translated"] == {"from": "ru", "by": "claude-haiku-5-5"}, "translated: source language and model")
check(a["category"] != "other", "the category is worked out again from the English title: %s" % a["category"])
check("summary" not in by["b2"] and by["b2"]["title"] == "Kryvyi Rih", "an item without a summary gets no summary")
check(by["c3"]["title"] == "Already English" and "translated" not in by["c3"], "an English item is never replaced")
check(by["d4"]["title"] == "Sin traducción" and "translated" not in by["d4"], "an item without a translation stays as it is")
check(out["translated"] == 2 and out["count"] == 4, "the feed reports how many items are in translation")

check(translate.store([{"id": "g7", "from": "ru", "title": "x" * 1000, "summary": "y" * 1000}], {"model": "m"}, now=NOW)["stored"] == 1,
      "long text is accepted and cut")
g = translate._load()["g7"]
check(len(g["t"]) <= translate.TITLE_MAX and len(g["s"]) <= translate.SUMMARY_MAX, "title and summary cut to their limits")
check(translate.store([{"id": "h8", "from": "ru", "title": "t"}], {"model": "bad model name!"}, now=NOW)["stored"] == 1
      and translate._load()["h8"]["by"] == "model", "a malformed model name is replaced")
r2 = translate.store([{"id": "i%d" % n, "from": "ru", "title": "t"} for n in range(250)], None, now=NOW)
check(r2["stored"] == translate.MAX_POST and r2["rejected"] == 50, "at most %d items per POST" % translate.MAX_POST)
r3 = translate.store([{"id": "late", "from": "ru", "title": "t"}], None, now=NOW + translate.KEEP_S + 10)
check(r3["total"] == 1, "translations older than 7 days are dropped: %s" % r3)
for bad in (None, {"items": []}, "x"):
    try:
        translate.store(bad, None)
        check(False, "a non-list body is refused")
    except ValueError:
        pass
check(True, "a non-list body raises ValueError (the server answers 400)")
check(translate.apply(None) is None and translate.apply({"x": 1}) == {"x": 1}, "apply() leaves odd data alone")
# 1.1 (GT 1.5.3): the power feed is translated too, but its items keep their own tags (no keyword reclassification)
translate.store([{"id": "power:ukrenergo:1", "from": "uk", "title": "Emergency power cuts"}], {"model": "m"},
                now=NOW + translate.KEEP_S + 20)
pw = {"count": 1, "items": [{"id": "power:ukrenergo:1", "lang": "uk", "title": "Аварійні відключення", "tags": ["emergency"]}]}
po = translate.apply(pw, "power")["items"][0]
check(po["title"] == "Emergency power cuts" and po["tags"] == ["emergency"] and "category" not in po,
      "power feed: English title, its own tags kept, no category added: %s" % po)
translate.store([{"id": "wire:x:1", "from": "uk", "title": "Missile strike on Kyiv"}], {"model": "m"}, now=NOW + translate.KEEP_S + 20)
wo = translate.apply({"items": [{"id": "wire:x:1", "lang": "uk", "title": "Удар", "category": "other", "tags": []}]}, "wire")["items"][0]
check(wo["category"] != "other", "wire feed: still reclassified from the English title: %s" % wo.get("category"))
check(set(translate.stats()) == {"version", "kept", "newest"}, "stats()")

src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
check('"/api/translations"' in src and "translate.apply(s.get(\"data\"), m.group(1))" in src and "translate.store(" in src,
      "server.py: POST /api/translations (token-gated with the analyst's) and English feeds on GET")
an = open(os.path.join(ROOT, "analyst", "analyst.py"), encoding="utf-8").read()
check('"translate_model": "claude-haiku-5-5"' in an and '"translate.lock"' in an and '"--tools", ""' in an,
      "analyst.py translate: Haiku, its own lock, no tools")
_jobs = os.path.join(ROOT, "analyst", "launchd")  # the private repo's schedule; the public copy leaves it out
_pl = [f for f in (os.listdir(_jobs) if os.path.isdir(_jobs) else []) if f.endswith("gt-translate.plist")]
if _pl:
    pl = open(os.path.join(_jobs, _pl[0]), encoding="utf-8").read()
    check("<string>translate</string>" in pl and "<integer>300</integer>" in pl and "/usr/bin/python3" in pl,
          "launchd job: analyst.py translate every 300 s under /usr/bin/python3")
print("%d checks passed" % ok)
