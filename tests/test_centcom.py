"""Offline tests for the 0.3.1 CENTCOM reader (gt/feeds.py). Never calls Firecrawl or the network.

Run: python3 -I tests/test_centcom.py
"""
import json, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
proj = os.path.dirname(HERE)
fixture = os.path.join(HERE, "fixtures", "centcom_public_releases.md")  # the live page, 2026-11-15
tmp = tempfile.mkdtemp()
os.environ["GT_DATA"] = tmp
sys.path.insert(0, proj)
from gt import feeds

md = open(fixture, encoding="utf-8").read()
ok = 0
def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what); sys.exit(1)
    ok += 1; print("ok  ", what)

# parser
items = feeds.parse_centcom_releases(md)
check(len(items) == 10, "parses all 10 releases (got %d)" % len(items))
check(items[0]["date"] == "2026-11-07" and items[0]["title"].startswith("U.S. Forces Disable Cargo Vessel"), "newest is Nov 7 2026 blockade release")
check(all(i["url"].startswith("https://www.centcom.mil/MEDIA/PUBLIC-RELEASES/Article/") for i in items), "every url is a release article")
check([i["date"] for i in items] == sorted((i["date"] for i in items), reverse=True), "sorted newest first")
check({i["date"] for i in items} >= {"2026-09-30", "2026-09-05", "2026-10-25"}, "Sept./Oct. dates parse")
check(feeds._centcom_date("May 2, 2026") == "2026-05-02" and feeds._centcom_date("June 12, 2026") == "2026-06-12", "May / June dates parse")
check(not any("ABOUT" in i["title"] for i in items), "footer links ignored")
check(feeds.parse_centcom_releases(md + "\n" + md) == items, "duplicates dropped")
check(feeds.parse_centcom_releases("nothing here") == [], "empty page -> no items")

# date normaliser
check(feeds._iso("Thu, 05 Feb 2026 17:47:00 GMT") == "2026-02-05T17:47:00Z", "RSS pubDate -> ISO")
check(feeds._iso("2026-11-11T11:14:30Z") == "2026-11-11T11:14:30Z", "Atom Z -> ISO")
check(feeds._iso("2026-11-11T11:14:30+01:00") == "2026-11-11T10:14:30Z", "Atom offset -> UTC")
check(feeds._iso("garbage") == "garbage" and feeds._iso(None) is None, "unknown dates pass through")

# cache, refresh and failure back-off (Firecrawl stubbed)
calls = []
def fake_ok(url, tag, max_age_s=3600):
    calls.append(tag); return md, 1
def fake_bad(url, tag, max_age_s=3600):
    calls.append(tag); raise RuntimeError("boom")
def fake_layout(url, tag, max_age_s=3600):
    calls.append(tag); return "redesigned page", 1
feeds.firecrawl_markdown = fake_ok
it, at, err = feeds.centcom_releases()
check(len(it) == 10 and err is None and calls == ["centcom"], "first call fetches through Firecrawl")
it, at, err = feeds.centcom_releases()
check(len(calls) == 1 and len(it) == 10, "second call within 6 h is served from cache")
p = os.path.join(tmp, "cache", "centcom_releases.json")
c = json.load(open(p)); c["fetched"] -= 7 * 3600; json.dump(c, open(p, "w"))
feeds.firecrawl_markdown = fake_bad
it, at, err = feeds.centcom_releases()
check(len(calls) == 2 and len(it) == 10 and "boom" in err, "stale cache + failure keeps the old items and reports the error")
it, at, err = feeds.centcom_releases()
check(len(calls) == 2 and len(it) == 10, "no retry within 3 h of a failure (budget protected)")
c = json.load(open(p)); c["failed"] -= 4 * 3600; json.dump(c, open(p, "w"))
feeds.firecrawl_markdown = fake_layout
it, at, err = feeds.centcom_releases()
check(len(calls) == 3 and len(it) == 10 and "layout" in err, "a layout change is an error, old items kept")
c = json.load(open(p)); c["failed"] -= 4 * 3600; json.dump(c, open(p, "w"))
feeds.firecrawl_markdown = fake_ok
it, at, err = feeds.centcom_releases()
check(len(calls) == 4 and err is None and "error" not in json.load(open(p)), "recovers and clears the error")

# official(): interleave, UK MoD stubbed
feeds._rss = lambda who, url: [{"source": who, "title": "m%d" % n, "url": "u", "date": "2026-11-1%dT00:00:00Z" % n} for n in range(5)] * 5
o = feeds.official()
srcs = [i["source"] for i in o["items"][:9]]
check(srcs == ["CENTCOM", "War Dept", "UK MoD"] * 3, "sources alternate (0.4.0: CENTCOM, War Dept, UK MoD)")
check(o["items"][0]["date"] == "2026-11-07" and o["items"][1]["date"] == "2026-11-14T00:00:00Z", "each source newest first")
check(len(o["items"]) <= 30 and o["errors"] == {} and o["centcom_fetched"], "<=30 items, no errors, fetched stamp")
def bad_rss(who, url): raise OSError("down")
feeds._rss = bad_rss
o = feeds.official()
check("UK MoD" in o["errors"] and any(i["title"].startswith("feed error") for i in o["items"]), "RSS failure shows as an error item")

# per-source budget
bp = os.path.join(tmp, "cache", "firecrawl_budget.json")
json.dump({"date": time.strftime("%Y-%m-%d"), "calls": 5}, open(bp, "w"))  # old-format file
n = sum(feeds._firecrawl_budget_ok("centcom") for _ in range(12))
check(n == 8, "centcom capped at 8/day (old-format budget file accepted)")
check(feeds._firecrawl_budget_ok("ukmto"), "ukmto keeps its own allowance")
print("%d checks passed" % ok)
