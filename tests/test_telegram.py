"""Offline tests for 0.12.0: Telegram channel posts from the public previews (gt/telegram.py).
Never touches the network: tests/fixtures/telegram/ holds SYNTHETIC pages (the real t.me/s/ structure, an invented
channel and invented posts), every fetch is patched and sockets are blocked.

Run: python3 -I tests/test_telegram.py
"""
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures", "telegram")
sys.path.insert(0, PROJ)
TMP = tempfile.mkdtemp(prefix="gt-telegram-")
os.environ["GT_DATA"] = os.path.join(TMP, "data")


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import geo, telegram, wire  # noqa: E402

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
PAGE, QUIET = fx("examplechan.html"), fx("nopreview.html")
slept = []
telegram._sleep = slept.append

# ---------------- module contract ----------------

check(telegram.VERSION == "1.1" and telegram.PUBLIC_OK is False and telegram.NON_COMMERCIAL is True,
      "VERSION 1.1, PUBLIC_OK False, NON_COMMERCIAL True")
check(list(telegram.FEEDS) == ["telegram"] and telegram.FEEDS["telegram"] == (telegram.poll, 300),
      "FEEDS = {'telegram': (poll, 300)}")
check(not set(telegram.FEEDS) & set(wire.FEEDS), "feed name does not clash with the wire")
check(len(telegram.CHANNELS) == 14 and len(set(telegram.CHANNELS)) == 14 and
      all(re.match(r"^[A-Za-z0-9_]{3,64}$", c) for c in telegram.CHANNELS), "14 channels, valid unique names")
check(all(c in telegram.CHANNELS and a3 in geo.country_shapes() for c, a3 in telegram.HINTS.items()),
      "channel hints are listed channels and map a3 codes")
check(telegram.INTERVAL >= 300 and telegram.WINDOW == 48 * H and telegram.MAX_ITEMS == 300, "5 min, 48 h, 300 posts")

# ---------------- helpers ----------------

check([telegram.views(v) for v in ("213K", "4.51K", "1.2M", "987", "2,048", "", None, "n/a")] ==
      [213000, 4510, 1200000, 987, 2048, None, None, None], "views(): K / M / plain / comma / unreadable")
check(telegram.lang_of("Удары по Харькову") == "ru" and telegram.lang_of("Удари по Харкову, їхні") == "uk" and
      telegram.lang_of("אזעקה בצפון") == "he" and telegram.lang_of("قصف في الشمال") == "ar" and
      telegram.lang_of("Strike in the north") == "en" and telegram.lang_of("123 !!") is None, "lang_of()")
check(telegram.tidy("Headline\n\n\n➖➖➖➖\nSubscribe: @examplechan\n@examplechan\nBody line\n\n") ==
      "Headline\n\nBody line", "tidy(): separators, signature, handle-only lines and blank runs out")
check(telegram.tidy("News line\nBig casino bonus, promo code X") == "News line", "tidy(): advert line out")
check(telegram.to_text('A&amp;B<br/><b>bold</b> <i class="emoji"><b>\U0001F525</b></i><br>end') ==
      "A&B\nbold \U0001F525\nend", "to_text(): entities, <br> breaks, emoji kept")

# ---------------- parser ----------------

posts, skipped = telegram.parse_page(PAGE, "examplechan")
P = {p["id"]: p for p in posts}
check(sorted(P) == [990, 1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009] and skipped == 1,
      "parse_page: 10 posts, the service message skipped and counted")
check(all(p["channel"] == "examplechan" for p in posts), "channel taken from data-post")
check(P[1001]["t"] == NOW - 50 * 60 and P[1001]["views"] == 12300 and P[1001]["has_photo"] and
      not P[1001]["has_video"], "post time, views '12.3K', photo flag")
check(P[1001]["text"].startswith("\U0001F1F8\U0001F1E9 SUDAN: Heavy shelling") and "&" in P[1001]["text"] and
      "<" not in P[1001]["text"] and "\n" in P[1001]["text"], "text: flag emoji kept, tags out, line breaks kept")
check("Taiwan" not in P[1002]["text"] and P[1002]["text"].startswith("Gangs block") and not P[1002]["has_photo"],
      "reply post: the quoted reply's text and thumbnail are not taken")
check(P[1003]["text"] == "" and P[1003]["has_video"] and P[1003]["t"] == NOW - 30 * 60,
      "media-only video post: no text, video flag, time from the footer (not the video duration)")
check(P[1004]["text"] == "" and P[1004]["has_other_media"] and P[1004]["views"] == 1200000,
      "missing-text post with only Telegram's 'view in Telegram' box")
check(P[1006]["forwarded"] and P[1006]["forwarded_from"] == "Example Source" and P[1006]["views"] == 2048,
      "forwarded post: the source name")
check(P[1007]["forwarded"] and P[1007]["forwarded_from"] is None and P[1007]["has_document"],
      "forward from a hidden name: forwarded, no name; document flag")
check(P[1008]["has_photo"] and P[1008]["has_other_media"], "photo plus unsupported media")
check(telegram.parse_page(QUIET, "examplequiet") == ([], 0), "a page without posts parses to nothing")
check(telegram.parse_page(b"", "x") == ([], 0) and telegram.parse_page("<html>broken <div", "x") == ([], 0),
      "empty or broken HTML does not raise")
cut_page = PAGE.decode("utf-8")
cut_page = cut_page[:cut_page.index('data-post="examplechan/1002"') + 400]
cp, _ = telegram.parse_page(cut_page, "examplechan")
check([p["id"] for p in cp][-1] == 1002 and cp[-1]["t"] is None, "a page cut mid-post still parses the rest")

# ---------------- items ----------------

items = {p["id"]: telegram.make_item(p, "examplechan", NOW) for p in posts}
check(items[990] is None, "a post older than 48 h is dropped")
check(items[1005] is None, "an advert-only post is dropped")
check(items[1009] is None, "a post with neither text nor media is dropped")
check(telegram.make_item(cp[-1], "examplechan", NOW) is None, "a post without a time is dropped")
it = items[1001]
url = "https://t.me/examplechan/1001"
check(it["url"] == url and it["id"] == hashlib.sha1(url.encode()).hexdigest()[:16], "post link and id")
check(it["source"] == "telegram" and it["source_label"] == "@examplechan" and it["kind"] == "telegram" and
      it["channel"] == "examplechan", "source 'telegram', source_label '@<channel>', kind 'telegram'")
check(it["ts"] == "2026-11-20T05:10:00Z" and it["ts_ms"] == (NOW - 3000) * 1000 and it["lang"] == "en", "ts, lang")
check(it["countries"] == ["SDN"] and it["theatre"] == "africa" and it["placed"] == "text",
      "placed by gt/placer.py: flag + El Fasher -> SDN, africa")
check(it["title"].startswith("\U0001F1F8\U0001F1E9 SUDAN: Heavy shelling") and len(it["title"]) <= 160,
      "title: the first line, <= 160 characters")
check(it["summary"] == "Residents describe fires in the eastern districts & a power cut across the city.",
      "summary: the rest, signature and separator removed")
check(it["views"] == 12300 and it["has_photo"] is True and it["has_video"] is False and it["also_in"] == [],
      "views and media flags on the item")
wire_keys = {"id", "title", "url", "source", "source_label", "ts_ms", "ts", "lang", "countries", "theatre", "placed",
             "category", "tags", "summary", "also_in", "kind"}
good = [x for x in items.values() if x]
check(len(good) == 7 and all(wire_keys <= set(x) for x in good), "7 items, all with the wire schema keys")
check(items[1002]["countries"] == ["HTI"] and items[1002]["summary"] is None, "Port-au-Prince -> HTI")
check(items[1003]["title"] == "(video)" and items[1003]["countries"] == [] and items[1003]["lang"] is None,
      "media-only post: title '(video)', unplaced")
check(items[1004]["title"] == "(media: open in Telegram)", "missing-text post: '(media: open in Telegram)'")
check(items[1006]["title"].startswith("\U0001F1FA\U0001F1E6 Удары по Харькову") and items[1006]["lang"] == "ru" and
      items[1006]["countries"] == ["UKR"] and items[1006]["summary"] is None,
      "hashtag-only first line skipped; Russian text placed UKR")
check(items[1007]["title"] == "Example statement on the northern border." and items[1007]["countries"] == [],
      "no place named and no channel hint: unplaced")
check(items[1008]["countries"] == ["ISR"] and items[1008]["theatre"] == "middle-east", "flag + Galilee -> ISR")
hinted = telegram.make_item(P[1007], "idfofficial", NOW)
check(hinted["countries"] == ["ISR"] and hinted["placed"] == "source" and hinted["url"].endswith("examplechan/1007"),
      "idfofficial fills in ISR when a post names no place")
fut = dict(P[1001], t=NOW + 5 * H)
check(telegram.make_item(fut, "examplechan", NOW)["ts_ms"] == NOW * 1000, "a time far in the future is clamped")
check(json.loads(json.dumps(good, ensure_ascii=False)) == good, "items are JSON-serialisable")

# ---------------- polling ----------------

state_file = os.path.join(wire.CACHE, telegram.STATE)


class Net(object):
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        ch = url.rsplit("/", 1)[-1]
        r = self.pages.get(ch, 404)
        if isinstance(r, int):
            raise urllib.error.HTTPError(url, r, "HTTP %d" % r, None, None)
        if isinstance(r, Exception):
            raise r
        return 200, {}, r


def reset():
    if os.path.exists(state_file):
        os.remove(state_file)
    del slept[:]


reset()
net = Net({"examplechan": PAGE, "examplequiet": QUIET})
out = telegram.poll(now=NOW, fetch=net, channels=("examplechan", "examplequiet"))
check(net.calls == ["https://t.me/s/examplechan", "https://t.me/s/examplequiet"] and slept == [telegram.STAGGER],
      "each channel's t.me/s/ page, one after the other, 1.5 s apart")
check(set(out) >= {"version", "fetched_at", "count", "sources", "attribution", "items", "by_theatre", "by_country"},
      "output has the contract keys")
check(out["count"] == len(out["items"]) == 7 and out["fetched"] == 2, "7 posts returned")
check([x["ts_ms"] for x in out["items"]] == sorted([x["ts_ms"] for x in out["items"]], reverse=True), "newest first")
rows = {r["name"]: r for r in out["sources"]}
check(rows["examplechan"]["ok"] is True and rows["examplechan"]["n"] == 7 and rows["examplechan"]["posts"] == 10 and
      rows["examplechan"]["skipped"] == 1 and rows["examplechan"]["newest"] == "2026-11-20T05:55:00Z",
      "channel row: ok, n, posts, skipped, newest")
check(rows["examplequiet"]["ok"] is False and "no posts" in rows["examplequiet"]["error"],
      "a channel without a preview reports an error; the feed carries on")
check(out["by_country"].get("SDN") == 1 and out["by_theatre"].get("unplaced") == 3, "by_country / by_theatre")
js = json.dumps(out, ensure_ascii=False)
check(len(js.encode()) < 400000 and os.path.exists(state_file) and
      not [f for f in os.listdir(wire.CACHE) if f.endswith(".tmp")], "under 400 KB; state saved atomically")
net.calls = []
out2 = telegram.poll(now=NOW + 60, fetch=net, channels=("examplechan", "examplequiet"))
check(net.calls == [] and out2["count"] == 7, "60 s later: no channel due, the stored posts are returned")
out3 = telegram.poll(now=NOW + 330, fetch=net, channels=("examplechan", "examplequiet"))
check(len(net.calls) == 2 and out3["count"] == 7, "5 min later: both due again; the same posts are not duplicated")

reset()
net = Net({"aaaslow": 429, "examplechan": PAGE})
out4 = telegram.poll(now=NOW, fetch=net, channels=("aaaslow", "examplechan"))
check(net.calls == ["https://t.me/s/aaaslow"] and out4["count"] == 0, "429: the round stops at once")
st = json.load(open(state_file, encoding="utf-8"))
check(st["sources"]["aaaslow"]["backoff_until"] == NOW + telegram.BACKOFF, "429: that channel waits an hour")
net.calls = []
out5 = telegram.poll(now=NOW + 60, fetch=net, channels=("aaaslow", "examplechan"))
check(net.calls == ["https://t.me/s/examplechan"] and out5["count"] == 7, "the next call fetches the others")

reset()
net = Net({"examplechan": gzip.compress(PAGE)})
check(telegram.poll(now=NOW, fetch=net, channels=("examplechan",))["count"] == 7, "gzip body without a header")

reset()
net = Net({"one": 500, "two": urllib.error.URLError("timed out"), "three": QUIET})
try:
    telegram.poll(now=NOW, fetch=net, channels=("one", "two", "three"))
    msg = None
except RuntimeError as e:
    msg = str(e)
check(msg and msg.startswith("all Telegram channels failing: 3"), "every channel failing raises")

reset()
out6 = telegram.poll(now=NOW, fetch=Net({"examplechan": PAGE}), channels=("examplechan",))
out7 = telegram.poll(now=NOW + 49 * H, fetch=Net({"examplechan": PAGE}), channels=("examplechan",))
check(out6["count"] == 7 and out7["count"] == 0 and out7["total"] == 0, "48 h window: old posts leave")

# cap: a page with 350 posts -> newest 300
blk = PAGE.decode("utf-8")
a = blk.index('<div class="tgme_widget_message_wrap', blk.index('data-post="examplechan/1001"') - 400)
b = blk.index('<div class="tgme_widget_message_wrap', a + 10)
one = blk[a:b]
many = "".join(one.replace("examplechan/1001", "examplechan/%d" % (5000 + k))
               .replace("2026-11-20T05:10:00+00:00", "2026-11-20T%02d:%02d:00+00:00" % (k // 60, k % 60))
               for k in range(350))
reset()
out8 = telegram.poll(now=NOW, fetch=Net({"examplechan": "<html>%s</html>" % many}), channels=("examplechan",))
check(out8["count"] == 300 and out8["total"] == 350 and out8["items"][0]["url"].endswith("/5349"),
      "at most 300 posts returned, newest first")
check(len(json.dumps(out8, ensure_ascii=False).encode()) < 400000, "capped output under 400 KB")

shutil.rmtree(TMP, ignore_errors=True)
print("%d checks passed" % ok)
