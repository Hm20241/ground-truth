"""Offline tests for 0.12.0: the live wire (gt/wire.py).
Never touches the network: the feeds in tests/fixtures/wire/ are SYNTHETIC (real RSS 2.0 / RDF 1.0 / Atom / Google
News structure, invented headlines), every fetch is patched and sockets are blocked.

Run: python3 -I tests/test_wire.py
"""
import email.message
import gzip
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures", "wire")
sys.path.insert(0, PROJ)
TMP = tempfile.mkdtemp(prefix="gt-wire-")
os.environ["GT_DATA"] = os.path.join(TMP, "data")


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import geo, mymaps, wire  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def fx(name):
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


NOW = 1795154400  # 2026-11-20T06:00:00Z
H = 3600
RSS2, RDF, ATOM, GN, BROKEN = (fx("rss2_example.xml"), fx("rdf_example.xml"), fx("atom_example.xml"),
                               fx("gnews_example.xml"), fx("broken_example.xml"))
EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel><title>Empty example</title></channel></rss>'
slept = []
wire._sleep = slept.append


def by_title(items, start):
    return [x for x in items if x["title"].startswith(start)]


# ---------------- module contract ----------------

check(wire.VERSION == "1.1" and wire.PUBLIC_OK is False and wire.NON_COMMERCIAL is True,
      "VERSION 1.1, PUBLIC_OK False, NON_COMMERCIAL True")
check(list(wire.FEEDS) == ["wire"] and wire.FEEDS["wire"] == (wire.poll, 300), "FEEDS = {'wire': (poll, 300)}")
check(all(n.isalpha() and n.islower() for n in wire.FEEDS), "feed name is lowercase letters only")
check(wire.TIMEOUT <= 20 and "@" not in wire.UA and "mailto" not in wire.UA.lower() and "http" not in wire.UA,
      "generic UA without contact details, timeout <= 20 s")
check(wire.LICENCE and wire.ATTRIBUTION, "licence and attribution text present")
slugs = [s[0] for s in wire.SOURCES]
check(len(slugs) == len(set(slugs)) and len(slugs) >= 30, "%d sources, unique slugs" % len(slugs))
check(all(s[2].startswith("https://") for s in wire.SOURCES), "every source URL is https")
_gqs = [urllib.parse.unquote_plus(s[2].split("q=", 1)[1].split("&", 1)[0]) for s in wire.SOURCES if wire._is_gnews(s[0])]
check(all(len(q) <= 195 and q.endswith("when:1d") for q in _gqs),
      "every Google News query ends with when:1d and stays under 195 characters (Google ignores when:1d past ~200): "
      "longest %d" % max(len(q) for q in _gqs))
_gph = sum(3600.0 / s[3] for s in wire.SOURCES if wire._is_gnews(s[0]))
check(_gph <= wire.GNEWS_PER_CALL * 12, "Google News requests per hour (%.0f) fit %d per 5-min call" % (_gph, wire.GNEWS_PER_CALL))
check(all(s[3] in (wire.FAST, wire.MID, wire.SLOW, wire.HOURLY) for s in wire.SOURCES), "every cadence is a known one")
shapes = geo.country_shapes()
check(all(h is None or (h[1:] in geo.THEATRES if h.startswith("@") else h in shapes) for *_x, h in wire.SOURCES),
      "every source hint is a map a3 or a known @theatre")
check(sum(1 for s in slugs if s.startswith("gn-")) >= 10 and "gn-reuters" in slugs and "gn-ap" in slugs,
      "Google News stand-ins for Reuters / AP plus topical searches")
gnmx = wire._BY_SLUG["gn-mexico"]
check("hl=es-419" in gnmx[2] and "gl=MX" in gnmx[2] and gnmx[4] == "es", "Mexico search is Spanish es-419 / MX")

# ---------------- parsing ----------------

e = wire.parse_feed(RSS2)
check(len(e) == 6, "RSS 2.0: 6 entries (the one without a headline is skipped)")
check(e[0]["title"] == "Drone strike hits fuel depot in Kharkiv region" and e[0]["t"] == NOW - 50 * 60,
      "RSS 2.0: CDATA title and RFC 822 pubDate")
check(e[5]["url"] == "https://news.example.org/articles/ex1005", "RSS 2.0: permalink guid stands in for a missing link")
check(e[5]["t"] == NOW - 3 * H, "RSS 2.0: 'EST' zone in pubDate")
e = wire.parse_feed(RDF)
check(len(e) == 3, "RDF 1.0: 3 items")
check(e[2]["url"].startswith("https://www.example.net/en/myanmar-junta-airstrike/"), "RDF: rdf:about when no <link>")
check(e[2]["t"] == NOW - int(4.5 * H), "RDF: dc:date with +01:00 offset")
e = wire.parse_feed(ATOM)
check(len(e) == 2 and e[0]["url"] == "https://defence.example.com/2026/11/20/navy-intercepts-drones/",
      "Atom: rel=alternate link, not the enclosure")
check(e[0]["t"] == NOW - H, "Atom: <published> before <updated>")
check("example visit" in wire.clean(e[1]["summary"]), "Atom: <content> when there is no <summary>")
e = wire.parse_feed(GN)
check(len(e) == 3 and e[0]["publisher"] == "Reuters" and e[2]["publisher"] is None, "Google News: <source> publisher")
e = wire.parse_feed(BROKEN)
check(len(e) == 2, "broken feed (bare &, &nbsp; &mdash;, control character) is repaired and parsed")
check(wire.clean(e[0]["title"]) == "Q&A: what the example border deal means — and what it does not",
      "broken feed: HTML entities decoded")
check(wire.clean(e[1]["title"]) == "Protesters rally in Caracas overnight", "broken feed: control character dropped")
check([x["title"] for x in wire.parse_feed(gzip.compress(RSS2))] == [x["title"] for x in wire.parse_feed(RSS2)],
      "gzip body without a Content-Encoding header is unpacked by its magic bytes")
check(len(wire.parse_feed(zlib.compress(RDF))) == 3, "deflate body is unpacked too")
for bad, what in ((b"<!DOCTYPE html><html><body>Blocked</body></html>", "an HTML page"),
                  (b"\x00\x01 not xml", "garbage")):
    try:
        wire.parse_feed(bad)
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    check(raised, "parse_feed raises on %s (the source row shows the error)" % what)

check(wire.parse_time("Fri, 20 Nov 2026 06:00:00 GMT") == NOW and wire.parse_time("2026-11-20T06:00:00Z") == NOW,
      "parse_time: RFC 822 and ISO Z")
check(wire.parse_time("2026-11-20T08:00:00+02:00") == NOW and wire.parse_time("2026-11-20T01:00:00-0500") == NOW,
      "parse_time: ISO offsets with and without the colon")
check(wire.parse_time("2026-11-20") == NOW - 6 * H and wire.parse_time("not a date") is None and
      wire.parse_time("") is None, "parse_time: date only, garbage -> None")
check(wire.clean("A &amp;amp; B <b>bold</b><br/>next&nbsp;line") == "A & B bold next line", "clean(): entities, tags")
c = wire.cut("word " * 100, 50)
check(len(c) <= 50 and c.endswith("…") and wire.cut("short", 50) == "short" and wire.cut("", 9) is None,
      "cut(): word boundary, ellipsis, <= n")
check(wire.canonical_url("https://x.example/a?utm_source=rss&id=7&maca=en-1&at_medium=RSS#top") ==
      "https://x.example/a?id=7", "canonical_url: tracking parameters and fragment off, others kept")
g = "https://news.google.com/rss/articles/example-article-0001?oc=5"
check(wire.canonical_url(g) == g, "canonical_url: Google News links untouched")

# ---------------- items ----------------

BBC = ("bbc", "BBC News", "https://feeds.example.invalid/rss2", wire.FAST, "en", None)
raw = wire.parse_feed(RSS2)
items = [wire.make_item(BBC, r, NOW) for r in raw]
check(items[4] is None, "an entry older than 48 h is dropped")
it = items[0]
check(it["url"] == "https://news.example.org/articles/ex1001" and
      it["id"] == hashlib.sha1(it["url"].encode()).hexdigest()[:16], "id = sha1(canonical url)[:16]")
check(it["ts"] == "2026-11-20T05:10:00Z" and it["ts_ms"] == (NOW - 3000) * 1000, "ts (ISO Z) and ts_ms")
check(it["countries"] == ["UKR"] and it["theatre"] == "ukraine-russia" and it["placed"] == "text",
      "placed from the headline: Kharkiv -> UKR, ukraine-russia")
check(it["source"] == "bbc" and it["source_label"] == "BBC News" and it["lang"] == "en" and it["kind"] == "wire" and
      it["also_in"] == [], "source slug / label, lang, kind 'wire', empty also_in")
check((it["category"], it["tags"]) == mymaps.classify(it["title"], None), "category and tags from mymaps.classify")
keys = {"id", "title", "url", "source", "source_label", "ts_ms", "ts", "lang", "countries", "theatre", "placed",
        "category", "tags", "summary", "also_in", "kind"}
check(all(set(x) == keys for x in items if x), "item schema: exactly the wire keys")
check(items[1]["summary"] == "Aid groups warn of disease as river levels keep rising." and
      items[1]["countries"] == ["SOM"], "summary: HTML stripped; Somalia placed")
check(items[2]["summary"] is None and items[2]["countries"] == [] and items[2]["placed"] is None,
      "summary equal to the title is dropped; an unplaceable headline stays unplaced")
check(items[3]["title"] == "Ceasefire talks resume in Doha & Cairo" and items[3]["countries"][:2] == ["QAT", "EGY"],
      "entity in a plain title; two countries, first mention first")
check(items[3]["summary"] == "Negotiators return for a third example round.", "WordPress 'appeared first on' tail cut")
check(items[3]["url"] == "https://news.example.org/articles/ex1004?page=2", "utm_* off, page=2 kept")
long_raw = dict(raw[1], summary="lorem ipsum " * 60)
check(len(wire.make_item(BBC, long_raw, NOW)["summary"]) <= wire.SUMMARY_MAX, "summary <= 200 characters")
TWZ = ("twz", "The War Zone", "https://feeds.example.invalid/atom", wire.SLOW, "en", None)
a = [wire.make_item(TWZ, r, NOW) for r in wire.parse_feed(ATOM)]
check(a[0]["title"] == "Navy intercepts drones over the Red Sea" and a[0]["countries"] == [] and
      a[0]["theatre"] == "middle-east", "Atom: HTML title cleaned; Red Sea gives a theatre without a country")
check(a[1]["ts_ms"] == NOW * 1000, "a pubDate more than 1 h in the future becomes the time first seen")
GNS = ("gn-test", "Google News: test", "https://news.google.com/rss/search?q=test", wire.MID, "en", "HTI")
gi = [wire.make_item(GNS, r, NOW) for r in wire.parse_feed(GN)]
check(gi[0]["title"] == "Rebels seize town in eastern Congo as talks stall" and gi[0]["source_label"] == "Reuters",
      "Google News: ' - Reuters' off the title, publisher as source_label")
check(gi[0]["countries"] == ["COD"] and gi[0]["placed"] == "text", "bare 'Congo' is the DRC (text beats the hint)")
check(gi[2]["source_label"] == "The Example Times" and gi[2]["title"] == "Port talks stall again",
      "Google News: publisher from the title when <source> is missing")
check(gi[2]["countries"] == ["HTI"] and gi[2]["placed"] == "source", "single-topic search fills in its country")
check(all(x["summary"] is None and x["via"] == "Google News" and x["url"].startswith("https://news.google.com/")
          for x in gi), "Google News: no summary, via Google News, link kept as it is")
BRK = ("broken", "Broken Example", "https://feeds.example.invalid/broken", wire.MID, "en", "@americas")
bi = [wire.make_item(BRK, r, NOW) for r in wire.parse_feed(BROKEN)]
check(bi[0]["countries"] == [] and bi[0]["theatre"] == "americas" and bi[0]["placed"] == "source",
      "regional desk fills in its theatre when no place is named")
check(bi[1]["countries"] == ["VEN"] and bi[1]["placed"] == "text", "Caracas -> VEN")
check(wire.make_item(BBC, {"title": "", "url": "https://x.example/1", "t": NOW}, NOW) is None and
      wire.make_item(BBC, {"title": "Headline", "url": "", "t": NOW}, NOW) is None, "no title or no link -> None")
check(wire.make_item(BBC, {"title": "Undated example headline", "url": "https://x.example/2", "t": None}, NOW)
      ["ts_ms"] == NOW * 1000, "an undated entry gets the time first seen")

# ---------------- de-duplication ----------------

check(wire.title_tokens("The Drone strikes in Kyiv, officials say") == frozenset(["drone", "strikes", "kyiv",
                                                                                  "officials"]),
      "title tokens: stop words and punctuation out")
check(wire.title_tokens("Ataque en Michoacán") == wire.title_tokens("ataque en michoacan"), "title tokens fold accents")
check(abs(wire.jaccard(frozenset("abcd"), frozenset("abce")) - 0.6) < 1e-9, "jaccard")
DW = ("dw", "DW", "https://feeds.example.invalid/rdf", wire.FAST, "en", None)
d = [wire.make_item(DW, r, NOW) for r in wire.parse_feed(RDF)]
stories, by_th, by_c, by_c24, total = wire.build([x for x in items if x] + d, NOW)
fuel = by_title(stories, "Drone strike hits fuel depot")
check(len(fuel) == 1 and fuel[0]["source"] == "bbc" and fuel[0]["also_in"] == ["dw"],
      "Jaccard >= 0.8: one story, the earliest kept (BBC 05:10), DW listed in also_in")
check(len(by_title(stories, "Drone strike hits power plant")) == 1, "a different target stays a separate story")
check(total == 7 and len(stories) == 7, "7 stories from 8 items")
check([x["ts_ms"] for x in stories] == sorted([x["ts_ms"] for x in stories], reverse=True), "newest first")
old = dict(d[0], id="x-old", ts_ms=d[0]["ts_ms"] - 30 * H * 1000, url="https://x.example/old")
s2 = wire.build([d[0], old], NOW + 0)[0]
check(len(s2) == 2, "the same title 30 h apart is two stories (24 h title window)")
unplaced = dict(items[0], id="u1", countries=[], theatre=None, placed=None, ts_ms=items[0]["ts_ms"] - 1000)
s3 = wire.build([unplaced, d[0]], NOW)[0]
check(len(s3) == 1 and s3[0]["id"] == "u1" and s3[0]["countries"] == ["UKR"],
      "an unplaced story borrows the countries of a placed duplicate")
check(by_c.get("UKR") == 2 and by_th.get("ukraine-russia") == 2 and by_th.get("unplaced") == 1,
      "by_country counts the primary country per story; by_theatre has 'unplaced'")
check(by_c24 == by_c, "by_country_24h (all within 24 h here)")
many = [dict(items[0], id="m%03d" % k, url="https://x.example/m%d" % k, ts_ms=(NOW - k * 60) * 1000,
             title="Example story alpha%03d beta%03d gamma%03d" % (k, k, k)) for k in range(700)]
s4 = wire.build(many, NOW, max_items=600)
check(len(s4[0]) == 600 and s4[4] == 700 and s4[0][0]["id"] == "m000", "max_items: newest 600 stories returned, total 700 reported")
check(wire.MAX_ITEMS >= 3000 and wire.MAX_BYTES >= 2000000, "1.7.4: the default cap covers a full day (about 2,100 stories, 1.6 MB)")
day = [dict(items[0], id="d%04d" % k, url="https://x.example/d%d" % k, ts_ms=(NOW - k * 34) * 1000,
            title="Day story alpha%04d beta%04d gamma%04d delta%04d" % (k, k, k, k), summary="s" * 190) for k in range(2500)]
s5 = wire.build(day, NOW)
o5 = wire.fit({"items": s5[0]})
check(len(s5[0]) == 2500 and o5["count"] == 2500 and o5["span_h"] >= 23.5,
      "1.7.4: 2,500 stories over 24 h are all served (%d bytes), span_h %s" % (len(json.dumps(o5)), o5.get("span_h")))
check(wire.fit({"items": []}).get("span_h") is None, "fit() on an empty list: no span_h, no crash")
big = {"items": [dict(items[0], summary="x" * 200, id=str(k)) for k in range(400)]}
wire.fit(big, 20000)
check(len(json.dumps(big, ensure_ascii=False, separators=(",", ":")).encode()) < 20000 and
      big["count"] == len(big["items"]) and big["count"] > 0, "fit(): the oldest trimmed until under the byte cap")

# ---------------- HTTP ----------------

seen_req = []


class FakeResp(object):
    def __init__(self, body, headers, status=200):
        self.body, self.status = body, status
        self.headers = email.message.Message()
        for k, v in headers.items():
            self.headers[k] = v

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    seen_req.append((req, timeout))
    u = req.full_url
    if u.endswith("/gz"):
        return FakeResp(gzip.compress(RSS2), {"Content-Encoding": "gzip", "ETag": '"e1"'})
    if u.endswith("/304"):
        h = email.message.Message()
        h["ETag"] = '"e1"'
        raise urllib.error.HTTPError(u, 304, "Not Modified", h, None)
    if u.endswith("/500"):
        raise urllib.error.HTTPError(u, 500, "Server Error", email.message.Message(), None)
    return FakeResp(RDF, {})


real_urlopen = urllib.request.urlopen
urllib.request.urlopen = fake_urlopen
try:
    st, hd, body = wire._fetch("https://feeds.example.invalid/gz", {"If-None-Match": '"e0"'})
    check(st == 200 and body == RSS2 and wire._hget(hd, "etag") == '"e1"',
          "_fetch: Content-Encoding gzip unpacked; headers kept (case-insensitive lookup)")
    req, tmo = seen_req[-1]
    check(req.get_header("User-agent") == wire.UA and req.get_header("Accept-encoding") == "gzip" and
          req.get_header("If-none-match") == '"e0"' and tmo == wire.TIMEOUT,
          "_fetch: UA, Accept-Encoding gzip, conditional header and timeout sent")
    st, hd, body = wire._fetch("https://feeds.example.invalid/304")
    check(st == 304 and body == b"" and wire._hget(hd, "ETag") == '"e1"', "_fetch: 304 -> (304, headers, b'')")
    try:
        wire._fetch("https://feeds.example.invalid/500")
        raised = None
    except urllib.error.HTTPError as ex:
        raised = ex.code
    check(raised == 500, "_fetch: other HTTP errors raise")
finally:
    urllib.request.urlopen = real_urlopen

# ---------------- polling ----------------

U, G = "https://feeds.example.invalid/", "https://news.google.com/rss/search?q=test-"
TEST_SOURCES = (
    ("bbc", "BBC News", U + "rss2", wire.FAST, "en", None),
    ("dw", "DW", U + "rdf", wire.FAST, "en", None),
    ("twz", "The War Zone", U + "atom", wire.SLOW, "en", None),
    ("broken", "Broken Example", U + "broken", wire.MID, "en", "@americas"),
) + tuple(("gn-" + c, "Google News: " + c, G + c, wire.MID, "en", None) for c in "abcdef")
wire.SOURCES = TEST_SOURCES
wire.GNEWS_PER_CALL = 4  # the polling checks below were written for a cap of 4 (the live cap is 5 since 1.1)
state_file = os.path.join(wire.CACHE, wire.STATE)


class Net(object):
    """Fake fetch(url, headers): serves fixtures with an ETag / Last-Modified and answers 304 to a match."""

    def __init__(self):
        self.calls, self.fail = [], {}
        self.pages = {U + "rss2": RSS2, U + "rdf": RDF, U + "atom": ATOM, U + "broken": BROKEN,
                      G + "a": GN, G + "b": GN}

    def __call__(self, url, headers=None):
        headers = headers or {}
        self.calls.append((url, dict(headers)))
        f = self.fail.get(url)
        if f:
            if isinstance(f, int):
                raise urllib.error.HTTPError(url, f, "HTTP %d" % f, None, None)
            raise f
        body = self.pages.get(url, EMPTY_RSS)
        tag = '"%s"' % hashlib.sha1(body).hexdigest()[:8]
        if url in (U + "rss2", U + "rdf"):  # these two send validators
            if headers.get("If-None-Match") == tag:
                return 304, {"ETag": tag}, b""
            return 200, {"ETag": tag, "Last-Modified": "Fri, 20 Nov 2026 05:30:00 GMT"}, body
        return 200, {}, body

    def urls(self):
        return [c[0] for c in self.calls]


def reset():
    if os.path.exists(state_file):
        os.remove(state_file)
    del slept[:]


reset()
net = Net()
out = wire.poll(now=NOW, fetch=net)
check(sorted(net.urls()) == sorted([U + "rss2", U + "rdf", U + "atom", U + "broken"] +
                                   [G + c for c in "abcd"]),
      "cold start: every plain source plus the first 4 Google searches (cap per call)")
check(slept == [wire.GNEWS_GAP] * 3, "Google searches 4 s apart, one after the other")
check(os.path.exists(state_file) and not [f for f in os.listdir(wire.CACHE) if f.endswith(".tmp")],
      "state saved as cache/wire_state.json, no temp file left (atomic replace)")
check(set(out) >= {"version", "fetched_at", "count", "sources", "attribution", "items", "by_theatre", "by_country"},
      "output has the contract keys")
check(out["version"] == "1.1" and out["fetched_at"] == "2026-11-20T06:00:00Z" and out["fetched"] == 8,
      "version, fetched_at, fetched")
check(out["count"] == len(out["items"]) == 14 and out["total"] == 14, "14 stories (15 items, one title duplicate)")
js = json.dumps(out, ensure_ascii=False)
check(len(js.encode()) < 400000 and json.loads(js)["count"] == 14, "JSON-serialisable, under 400 KB")
rows = {r["name"]: r for r in out["sources"]}
check(set(rows) == {s[0] for s in TEST_SOURCES} and all(set(r) >= {"name", "ok", "error", "newest", "n"}
                                                       for r in rows.values()),
      "one source row per source with name / ok / error / newest / n")
check(rows["bbc"]["ok"] is True and rows["bbc"]["n"] == 5 and rows["bbc"]["newest"] == "2026-11-20T05:10:00Z",
      "bbc row: ok, 5 items, newest 05:10Z")
check(rows["gn-e"]["ok"] is None and rows["gn-e"]["checked"] is None, "Google searches over the cap wait (not tried)")
rebels = by_title(out["items"], "Rebels seize town")
check(len(rebels) == 1 and rebels[0]["source"] == "gn-a" and rebels[0]["also_in"] == ["gn-b"] and
      rows["gn-b"]["n"] == 3, "the same URL from two sources is one item; the second is listed in also_in")
check(by_title(out["items"], "Drone strike hits fuel depot")[0]["also_in"] == ["dw"], "title duplicate across feeds")
st = json.load(open(state_file, encoding="utf-8"))
first = {s[0]: st["sources"][s[0]]["next_due"] - NOW for s in TEST_SOURCES if s[0] in st["sources"]}
check(all(s[3] * 0.5 - 1 <= first[s[0]] <= s[3] for s in TEST_SOURCES if s[0] in first),
      "first round: each next check between half and one full cadence ahead (spread)")
check(st["sources"]["bbc"]["etag"] and st["sources"]["bbc"]["lm"], "ETag and Last-Modified kept in the state")

net.calls = []
del slept[:]
out2 = wire.poll(now=NOW + 60, fetch=net)
check(net.urls() == [G + "e", G + "f"] and slept == [wire.GNEWS_GAP] and out2["fetched"] == 2,
      "60 s later: only the 2 Google searches left over from the cold start")
net.calls = []
out2 = wire.poll(now=NOW + 120, fetch=net)
check(net.calls == [] and out2["fetched"] == 0 and out2["count"] == 14, "120 s: nothing due, no request")

T2 = NOW + 330
st = json.load(open(state_file, encoding="utf-8"))
due = sorted(k for k, v in st["sources"].items() if v["next_due"] <= T2 + wire.SLACK)
net.calls = []
out3 = wire.poll(now=T2, fetch=net)
got = {u for u in net.urls()}
want = {s[2] for s in TEST_SOURCES if s[0] in due}
check(got == want and {U + "rss2", U + "rdf"} <= got and U + "atom" not in got,
      "per-source cadence: only the due sources are fetched (5-min ones yes, 30-min one no)")
hdr = dict(net.calls)[U + "rss2"]
check(hdr.get("If-None-Match") == st["sources"]["bbc"]["etag"] and hdr.get("If-Modified-Since"),
      "conditional GET: If-None-Match and If-Modified-Since sent")
rows3 = {r["name"]: r for r in out3["sources"]}
check(rows3["bbc"]["status"] == 304 and rows3["bbc"]["ok"] is True and rows3["bbc"]["n"] == 5 and
      out3["count"] == 14, "304: nothing parsed, the stored items stay")
st3 = json.load(open(state_file, encoding="utf-8"))
check(st3["sources"]["bbc"]["next_due"] == T2 + wire.FAST, "after the first round the cadence is exact (5 min)")

net.fail[U + "rdf"] = urllib.error.URLError("timed out")
out4 = wire.poll(now=T2 + 330, fetch=net)
r4 = {r["name"]: r for r in out4["sources"]}
check(r4["dw"]["ok"] is False and "URLError" in r4["dw"]["error"] and r4["bbc"]["ok"] is True and
      out4["count"] == 14, "one failing source shows its error; the feed and its items carry on")

# 429 from Google pauses every search; 403 pauses that source
reset()
net = Net()
net.fail[G + "a"] = 429
net.fail[U + "rss2"] = 403
out5 = wire.poll(now=NOW, fetch=net)
check(G + "b" not in net.urls() and slept == [], "Google 429: the chain stops at once")
st5 = json.load(open(state_file, encoding="utf-8"))
check(all(st5["sources"]["gn-" + c]["backoff_until"] == NOW + wire.BACKOFF for c in "abcdef"),
      "Google 429: all searches pause for an hour")
check(st5["sources"]["bbc"]["backoff_until"] == NOW + wire.BACKOFF and
      {r["name"]: r for r in out5["sources"]}["bbc"]["error"] == "HTTP 403", "403: that source pauses for an hour")
net.calls = []
wire.poll(now=NOW + 400, fetch=net)
check(not [u for u in net.urls() if u.startswith(G) or u == U + "rss2"],
      "paused sources are not asked again before the hour is up")
net.calls = []
del net.fail[G + "a"]
del net.fail[U + "rss2"]
wire.poll(now=NOW + wire.BACKOFF + 1, fetch=net)
check(G + "a" in net.urls() and U + "rss2" in net.urls(), "after the hour they are asked again")

# all failing raises; corrupt state starts fresh
reset()
net = Net()
for s in TEST_SOURCES:
    net.fail[s[2]] = 500
try:
    wire.poll(now=NOW, fetch=net)
    msg = None
except RuntimeError as ex:
    msg = str(ex)
check(msg and msg.startswith("all wire sources failing") and "HTTP 500" in msg, "every source failing raises")
with open(state_file, "w") as fh:
    fh.write("{not json")
out6 = wire.poll(now=NOW, fetch=Net())
check(out6["count"] == 14, "a corrupt state file is replaced by a fresh start")

# 48 h retention
out7 = wire.poll(now=NOW + 49 * H, fetch=Net())
st7 = json.load(open(state_file, encoding="utf-8"))
check(all((NOW + 49 * H) * 1000 - x["ts_ms"] <= wire.WINDOW * 1000 for x in st7["items"].values()) and
      not by_title(out7["items"], "Drone strike hits fuel depot"), "items older than 48 h leave the state and output")
check(len(st7["items"]) <= wire.MAX_STORE, "state capped at MAX_STORE")

# datetime `now`, summary for the analyst
import datetime as dt  # noqa: E402
reset()
out8 = wire.poll(now=dt.datetime(2026, 11, 20, 6, 0, 0), fetch=Net())
check(out8["fetched_at"] == "2026-11-20T06:00:00Z", "poll accepts a naive UTC datetime for now")
sm = wire.summary(out8)
check(len(json.dumps(sm, ensure_ascii=False)) < 2048 and "ukraine-russia" in sm["latest"],
      "summary(): under 2 KB, newest placed headlines per theatre")
check(wire.summary(None)["by_theatre"] == {}, "summary(None) does not raise")
_t0 = 1763618400000  # 2025-11-20T06:00Z; only differences matter
_mk = lambda i, cat, also, mins: {"id": i, "title": i, "theatre": "africa", "placed": "text", "countries": ["SDN"],  # noqa: E731
                                  "category": cat, "also_in": also, "ts_ms": _t0 - mins * 60000, "ts": "2025-11-20T05:00:00Z"}
_rk = wire.summary({"items": [_mk("football", "other", [], 0), _mk("strike", "strike", [], 50),
                              _mk("wide", "other", ["a", "b"], 20), _mk("old strike", "strike", ["a"], 13 * 60)]}, per_theatre=3)
check([x.split("] ")[1] for x in _rk["latest"]["africa"]] == ["strike", "wide", "football"],
      "summary(): conflict category first, then outlets, then newest; nothing older than 12 h: %s" % _rk["latest"])

shutil.rmtree(TMP, ignore_errors=True)
print("%d checks passed" % ok)
