"""Offline tests for 0.8.0: US embassy alerts (gt/embassy.py).
Never touches the network. Fixtures are real alert feeds saved on 2026-11-18 (UTC), cut to 4 items each, the body
HTML cut after the alert template and stripped of links and tag attributes:
  embassy/pl.xml  pl.usembassy.gov  Warsaw illumination-round test, Medicare notice, Krakow shooting, Independence Day marches
  embassy/ua.xml  ua.usembassy.gov  Kyiv infrastructure attacks, Europe-wide holiday travel, demonstration, Lviv consular outreach
  embassy/tw.xml  www.ait.org.tw    typhoon, air-defence exercises, Kaohsiung flood closure, voting notice
  embassy/ru.xml  ru.usembassy.gov  the same holiday travel alert, Tsaritsyno threat, health alert, drone disruptions

Run: python3 -I tests/test_080.py
"""
import datetime as dt
import email.utils
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "embassy")
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)
from gt import alerts, embassy  # noqa: E402

alerts.CACHE = os.path.join(TMP, "cache")  # embassy state goes through alerts._load/_save
os.makedirs(alerts.CACHE, exist_ok=True)
STATE_FILE = os.path.join(alerts.CACHE, embassy.STATE)
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


alerts.urllib.request.urlopen = no_network
raw = {cc: open(os.path.join(FX, cc + ".xml"), "rb").read() for cc in ("pl", "ua", "tw", "ru")}
ts = lambda s: int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())
NOW = ts("2026-11-18T20:00:00Z")
KINDS = {"departure", "shelter", "demonstration", "weather", "health", "advisory", "worldwide", "security", "routine", "other"}
CODES = [p[0] for p in embassy.POSTS]

# ---- the post table
P = embassy.POSTS
check(len(P) == 38 and len(set(CODES)) == 38, "38 posts, unique codes")
check(sum(p[5] == "fast" for p in P) == 28 and sum(p[5] == "slow" for p in P) == 10, "28 fast, 10 slow")
check(CODES[:3] == ["IL", "LB", "IQ"] and CODES[27] == "AZ" and CODES[28:30] == ["TW", "CN"] and CODES[-1] == "VE", "table order")
check(all(p[6].startswith("https://") and p[6].endswith("/category/alert/feed/") for p in P), "every URL is a category/alert feed")
u = {p[0]: p[6] for p in P}
check(u["TW"] == "https://www.ait.org.tw/category/alert/feed/" and u["CN"] == "https://china.usembassy-china.org.cn/category/alert/feed/"
      and u["PL"] == "https://pl.usembassy.gov/category/alert/feed/", "AIT and Beijing domains, usembassy pattern elsewhere")
check(all(round(p[3], 2) == p[3] and round(p[4], 2) == p[4] and -90 < p[3] < 90 and -180 < p[4] < 180 for p in P),
      "city centres at 2 decimals")
check(dict((p[0], (p[3], p[4])) for p in P)["MX"] == (19.43, -99.13), "western longitudes are negative")

# ---- parsing the real feeds
p = {cc: embassy.parse_feed(raw[cc], cc.upper()) for cc in raw}
check(all(len(v) == 4 for v in p.values()), "4 items from each fixture")
FIELDS = {"id", "c", "title", "url", "t", "kind", "loc", "event"}
allx = [x for v in p.values() for x in v]
check(all(set(x) == FIELDS for x in allx), "every item has exactly the spec fields")
check(all(isinstance(x["t"], int) and len(x["id"]) == 12 and int(x["id"], 16) >= 0 and x["url"].startswith("https://")
          for x in allx), "t is an int epoch, id is 12 hex, url is the post link")
check(all(x["kind"] in KINDS for x in allx), "kinds are known values")
check(all((x["loc"] is None or len(x["loc"]) <= 160) and (x["event"] is None or len(x["event"]) <= 240) for x in allx),
      "loc <= 160 and event <= 240 chars")
check(all("&#" not in x["title"] and "&amp;" not in x["title"] and "  " not in x["title"] and x["title"] == x["title"].strip()
          for x in allx), "titles unescaped, whitespace collapsed")
w = p["pl"][0]
check(w["title"] == "Security Alert: U.S. Embassy Warsaw (November 18, 2026)" and w["t"] == ts("2026-11-18T17:37:57Z")
      and w["kind"] == "security" and w["c"] == "PL", "Warsaw 18 Nov: title, UTC time, security")
check(w["loc"] == "Warsaw, Zielonka, Marki, Kobyłka, Wołomin and Legionowo", "Location with the colon outside the bold label")
check(w["event"].startswith("The Polish Ministry of National Defense reports") and w["event"].endswith("…")
      and len(w["event"]) <= 240 and not w["event"][:-1].endswith(" "), "Event across paragraphs, cut on a word with an ellipsis")
k = p["pl"][2]
check(b"&#8211;" in raw["pl"] and k["title"] == "Security Alert – Shooting in Krakow Main Market Square", "&#8211; in a title -> en dash")
check(k["loc"] is None and k["event"].startswith("Local police confirmed reports of shots fired"), "Event without a Location")
check(p["pl"][1]["kind"] == "other" and not embassy.keep(p["pl"][1]), "Medicare notice: other, dropped")
check(p["pl"][3]["kind"] == "demonstration" and p["pl"][3]["loc"] is None and p["pl"][3]["event"] is None,
      "Independence Day marches: demonstration, no template -> loc/event None")
ua = p["ua"]
check(ua[0]["loc"] == "Ukraine, all districts" and ua[0]["event"].startswith("Due to attacks on Ukraine"), "Kyiv 17 Nov template")
check(" ".encode("utf-8") in raw["ua"] and ua[2]["title"] == "Demonstration Alert – U.S. Embassy Kyiv (November 4, 2026",
      "narrow no-break space in a title collapses to one space")
check(ua[2]["kind"] == "demonstration" and ua[2]["loc"] == "Syretsky Park, Kyiv, Ukraine", "Kyiv demonstration and its location")
check(ua[1]["title"] == "Security Alert: Holiday Travel, November 13, 2026" and ua[1]["loc"] == "Europewide", "holiday travel alert (UA)")
check(ua[3]["kind"] == "routine" and not embassy.keep(ua[3]), "ALERT - MESSAGE FOR U.S. CITIZENS (Lviv consular day): routine, dropped")
tw = p["tw"]
check(tw[0]["kind"] == "weather" and tw[0]["title"] == "Weather Alert: AIT Taipei Typhoon Advisory"
      and tw[0]["loc"].startswith("Northern and Eastern Taiwan"), "AIT typhoon advisory: weather")
check(tw[1]["kind"] == "shelter" and embassy.keep(tw[1]), "Urban Resilience (Air Defense) exercises: shelter")
check(tw[2]["kind"] == "weather" and embassy.keep(tw[2]), "AIT Kaohsiung office closed for flooding: weather (an office is not the embassy)")
check(tw[3]["kind"] == "other" and not embassy.keep(tw[3]), "voting notice: other, dropped")
ru = p["ru"]
check(ru[0]["title"] == ua[1]["title"] and ru[0]["id"] != ua[1]["id"] and ru[0]["c"] == "RU", "the same alert posted by Moscow")
check(ru[1]["kind"] == "security" and ru[1]["loc"] is None and ru[1]["event"] is None, "Tsaritsyno threat: security, no template")
check(ru[2]["kind"] == "health" and ru[2]["loc"] == "Irkutsk, Russia", "health alert with location")
check(ru[3]["kind"] == "shelter" and embassy.keep(ru[3]), "routine message about drone flight disruptions: body decides (shelter)")

# ---- robustness: bad items are skipped, a document that is not RSS raises
bad = (b'<rss version="2.0"><channel><title>t</title>'
       b'<item><title>No date</title><link>https://x.test/1</link></item>'
       b'<item><title>Bad date</title><link>https://x.test/2</link><pubDate>someday</pubDate></item>'
       b'<item><link>https://x.test/3</link><pubDate>Wed, 18 Nov 2026 10:00:00 +0000</pubDate></item>'
       b'<item><title>No link</title><pubDate>Wed, 18 Nov 2026 10:00:00 +0000</pubDate></item>'
       b'<item><title>Security Alert:  Double &amp;#8211; encoded\n</title><guid>https://x.test/5</guid>'
       b'<pubDate>Wed, 18 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>')
r = embassy.parse_feed(bad, "XX")
check(len(r) == 1 and r[0]["title"] == "Security Alert: Double – encoded" and r[0]["url"] == "https://x.test/5"
      and r[0]["t"] == ts("2026-11-18T10:00:00Z") and r[0]["loc"] is None and r[0]["event"] is None,
      "missing date/title/link skipped; guid stands in for link; double-encoded entity; no body")
for doc, what in ((b"<html><body>blocked</body></html>", "an HTML page"), (b"not xml at all", "garbage")):
    try:
        embassy.parse_feed(doc, "XX")
        check(False, "%s raises" % what)
    except Exception:
        check(True, "%s raises (so the post keeps its old items)" % what)

# ---- the template parser
L = lambda h, t="Demonstration Alert": embassy._template(embassy._lines(h), t)
check(L("<p><strong>Location</strong>: Riga</p><p><strong>Event:</strong> A march.</p><p>Second paragraph.</p>"
        "<p><strong>Actions to Take:</strong></p><ul><li>Avoid the area.</li></ul>") == ("Riga", "A march. Second paragraph.", ""),
      "Event stops at Actions to Take")
check(L("<p>Location: Russia Event: Escalating drone threat</p><p>Assistance</p><p>Embassy</p>")[:2] == ("Russia", "Escalating drone threat"),
      "Location and Event on one line; Assistance stops the event")
check(L("<p><b>Location:</b></p><p>Baku</p><p><b>Event :</b> Rally</p>")[:2] == ("Baku", "Rally"), "label on its own line, space before colon")
check(L("<div>Demonstration Alert</div><p>Demonstration Alert</p><p>Crowds expected downtown.</p>") == (None, None, "Crowds expected downtown."),
      "no template: the repeated title is dropped and the lead kept")
check(embassy._cut("word " * 100, 240).endswith("…") and len(embassy._cut("word " * 100, 240)) <= 240
      and embassy._cut("short ", 240) == "short" and embassy._cut("", 9) is None, "_cut: word boundary, ellipsis, None for empty")

# ---- classify: every kind, the tricky titles and the noise
C = [("Ordered Departure of Non-Emergency U.S. Government Employees", "", "departure"),
     ("Security Alert: Authorized Departure from U.S. Embassy Beirut", "", "departure"),
     ("Alert: U.S. Embassy Sanaa Suspends Operations", "", "departure"),
     ("Message for U.S. Citizens: Evacuation Flights from Tel Aviv", "", "departure"),
     ("U.S. Embassy Closed Due to Security Situation", "", "departure"),
     ("U.S. Embassy Closed for Thanksgiving", "", "other"),
     ("Security Alert: Shelter in Place Order for Jerusalem", "", "shelter"),
     ("Routine Message for U.S. Citizens: Nationwide Civil Defense Siren Test", "", "shelter"),
     ("Security Alert: Missile and Drone Attacks Across Israel", "", "shelter"),
     ("Security Alert: Air Raid Warnings in Kyiv", "", "shelter"),
     ("Demonstration Alert – U.S. Embassy Kyiv", "", "demonstration"),
     ("Demonstration Alert: Message to U.S. Citizens (October 8, 2026)", "", "demonstration"),
     ("Security Alert: Nationwide Transport Strike", "", "demonstration"),
     ("Security Alert: Political Rallies in Tbilisi", "", "demonstration"),
     ("Weather Alert: AIT Taipei Typhoon Advisory", "", "weather"),
     ("Earthquake – Message for U.S. Citizens", "", "weather"),
     ("Health Alert – U.S. Embassy Moscow, Russia (October 6, 2026)", "", "health"),
     ("Worldwide Caution: Public Health Arrival Restrictions and Enhanced Ebola Screening", "", "health"),
     ("Travel Advisory: Lebanon October 2026", "", "advisory"),
     ("Worldwide Caution", "", "worldwide"),
     ("Security Alert – Worldwide Caution, June 22, 2025", "", "worldwide"),
     ("Security Alert: Exercise Increased Caution", "", "security"),
     ("Security Alert: Holiday Travel, November 13, 2026", "", "security"),
     ("Security Alert: U.S. Embassy Warsaw (November 18, 2026)", "", "security"),
     ("Security Message: Large Public Events", "", "security"),
     ("Alert: U.S. Embassy Baghdad", "", "security"),
     ("Security Alert: U.S. Embassy Moscow", "Drone attacks have occurred", "security"),
     ("ALERT – MESSAGE FOR U.S. CITIZENS: CONSULAR OFFICERS TO OFFER SERVICES IN LVIV", "", "routine"),
     ("Routine Message: Voting in U.S. Elections from Overseas", "", "routine"),
     ("Routine Message: Voting in U.S. Elections from Overseas", "Protests are expected near the Embassy.", "demonstration"),
     ("Routine message: Emergency Preparedness", "As typhoon Fung Wong is departing Taiwan", "weather"),
     ("November 12th Meet and Greet with U.S. Embassy Senior Consular Staff", "", "other"),
     ("Online Form Filler Required for U.S. Passport Applications", "", "other"),
     ("Online Form Filler Required for U.S. Passport Applications", "This security alert reminds applicants", "other"),
     ("Medicare Changes Effective November 9, 2026", "", "other"),
     ("Voting in U.S. Elections from Overseas", "Be an Active Voter by taking the necessary steps", "other"),
     ("Generally Speaking: Strikebreaker Rallying", "", "other")]
bad = [(t, x, want, embassy.classify(t, x)) for t, x, want in C if embassy.classify(t, x) != want]
check(not bad, "classify table, %d titles (%s)" % (len(C), bad or "all"))
check(embassy.classify("") == "other" and embassy.classify(None) == "other", "empty title -> other")

# ---- keep()
K = [({"kind": "other", "title": "Meet and Greet"}, False),
     ({"kind": "security", "title": "Security Alert"}, True),
     ({"kind": "weather", "title": "Weather Alert"}, True),
     ({"kind": "routine", "title": "Routine Message: Voting in U.S. Elections from Overseas", "event": None}, False),
     ({"kind": "routine", "title": "Routine Message", "event": "A curfew is in effect from 22:00."}, True),
     ({"kind": "routine", "title": "Routine Message: Airport Closures", "event": None}, True),
     ({"kind": "routine", "title": "Message for U.S. Citizens: Border Crossing Delays"}, True),
     ({"kind": "routine", "title": "Message for U.S. Citizens", "event": "Large-scale Air Defense exercises on Monday"}, True),
     ({"kind": "routine", "title": "Message for U.S. Citizens: Embassy Closed for Thanksgiving"}, False),
     ({"kind": "routine", "title": "Message for U.S. Citizens: Embassy Closed", "event": "Roads are closed."}, True)]
bad = [(x["title"], want) for x, want in K if embassy.keep(x) != want]
check(not bad, "keep() rules (%s)" % (bad or "all"))

# ---- poll(): an injected fetch serves the fixtures (an empty feed for the other posts)
EMPTY = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
SERVE = {"PL": raw["pl"], "UA": raw["ua"], "TW": raw["tw"], "RU": raw["ru"]}
BY_URL = {p[6]: p[0] for p in P}
ARGS = []


def fake(calls, serve=SERVE, fail=None):
    def f(url, timeout=None, conditional=False):
        c = BY_URL[url]
        calls.append(c)
        ARGS.append((timeout, conditional))
        if fail and (c in fail or "*" in fail):
            raise fail.get(c) or fail["*"]
        return serve.get(c, EMPTY)
    return f


def reset():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


def http(code):
    return urllib.error.HTTPError("https://x.test/", code, "err", {}, None)


reset()
seen, c = [], []
d = embassy.poll(now=NOW, fetch=fake(c))
check(d["fetched"] == 8 and c == CODES[:8], "cold start: 8 posts, oldest-due first in table order")
check(set(ARGS) == {(15, True)}, "fetches use timeout 15 s and conditional requests")
check(os.path.exists(STATE_FILE) and os.path.dirname(STATE_FILE).startswith(TMP), "state saved to the temp cache only")
seen += c
for i, want in enumerate((CODES[8:16], CODES[16:24], CODES[24:32], CODES[32:38]), 1):
    c = []
    d = embassy.poll(now=NOW + 60 * i, fetch=fake(c))
    check(c == want, "run %d fetches the next posts due (%s..%s)" % (i + 1, want[0], want[-1]))
    seen += c
check(sorted(seen) == sorted(CODES) and d["fetched"] == 6, "5 runs sweep all 38 posts once")
c = []
check(embassy.poll(now=NOW + 250, fetch=fake(c))["fetched"] == 0 and c == [], "nothing due 250 s in: no fetch")
c = []
embassy.poll(now=NOW + 300, fetch=fake(c))
check(c == CODES[:8], "first fast posts due again after 300 s")
for t in (360, 420):
    embassy.poll(now=NOW + t, fetch=fake([]))
c = []
embassy.poll(now=NOW + 480, fetch=fake(c))
check(c == ["FI", "GE", "AM", "AZ"], "at +480 s only the fast posts are due, the slow tier (TW...) waits 900 s")
c = []
embassy.poll(now=NOW + 180 + 900, fetch=fake(c), max_fetch=38)
check(c == CODES[:32], "at +1080 s: every fast post, then TW/CN/KR/JP (fetched at +180); PH... (fetched at +240) not yet")

# merged view data after a clean sweep
reset()
d = embassy.poll(now=NOW, fetch=fake([]), max_fetch=38)
check(d["fetched"] == 38 and d["errors"] == 0, "one call with max_fetch=38 sweeps everything, no errors")
it = d["items"]
check([x["c"] for x in it] == ["PL", "UA", "UA"], "7-day window at 18 Nov 20:00: Warsaw 18th, Kyiv 17th, holiday travel 13th (%s)"
      % [x["c"] for x in it])
h = it[2]
check(h["posts"] == ["RU", "UA"] and h["c"] == "UA" and h["t"] == ts("2026-11-13T18:43:46Z") and h["url"] == ua[1]["url"],
      "holiday travel from Kyiv and Moscow: one item, both posts, c = first in table order, newest t")
check(all(x["posts"] == [x["c"]] for x in it[:2]), "single-post items list their own post")
check(not any("Shooting in Krakow" in x["title"] for x in it), "11-day-old Krakow alert outside the 7-day window")
ps = d["posts"]
check([x["c"] for x in ps] == CODES and all(set(x) == set(embassy.POST_FIELDS) for x in ps), "posts in table order, spec fields")
pp = {x["c"]: x for x in ps}
check(pp["PL"]["last_t"] == w["t"] and pp["PL"]["ok"] is True and pp["PL"]["err"] is None and pp["PL"]["n"] == "Poland"
      and pp["PL"]["city"] == "Warsaw" and (pp["PL"]["lat"], pp["PL"]["lon"]) == (52.23, 21.01), "post block: last_t, ok, name, city")
check(pp["TW"]["last_t"] == tw[0]["t"] and pp["IL"]["last_t"] is None, "last_t also for posts quiet this week; None when nothing kept")
st = alerts._load(embassy.STATE, {})
check(all(set(st[c]) >= {"items", "next_due", "checked", "ok", "err", "backoff_until"} for c in CODES), "per-post state fields")
check(st["PL"]["next_due"] == NOW + 300 and st["TW"]["next_due"] == NOW + 900 and st["PL"]["checked"] == NOW, "next_due by tier")

# the window edge: on 13 Nov 20:00 the Krakow shooting (7 Nov 15:52) is in, the 6 Nov marches are out
reset()
d13 = embassy.poll(now=ts("2026-11-13T20:00:00Z"), fetch=fake([]), max_fetch=38)
tl = [x["title"] for x in d13["items"]]
check(any("Shooting in Krakow" in t for t in tl) and not any("Week of Polish Independence Day" in t for t in tl), "7-day cutoff edge")

# 403: that post backs off an hour, keeps its old items, the rest are served
reset()
embassy.poll(now=NOW, fetch=fake([]), max_fetch=38)
c = []
d = embassy.poll(now=NOW + 300, fetch=fake(c, fail={"PL": http(403)}), max_fetch=38)
st = alerts._load(embassy.STATE, {})
check(st["PL"]["backoff_until"] == NOW + 300 + 3600 and st["PL"]["err"] == "HTTP 403" and st["PL"]["ok"] is False, "403 -> 1 h backoff")
check(d["errors"] == 1 and {x["c"]: x for x in d["posts"]}["PL"]["err"] == "HTTP 403", "the post block shows the error")
check([x["c"] for x in d["items"]] == ["PL", "UA", "UA"], "PL's last good items and the other posts still served")
c = []
embassy.poll(now=NOW + 600, fetch=fake(c), max_fetch=38)
check("PL" not in c and "UA" in c, "PL skipped while backed off, UA polled on time")
c = []
embassy.poll(now=NOW + 300 + 3600, fetch=fake(c), max_fetch=38)
check("PL" in c and alerts._load(embassy.STATE, {})["PL"]["ok"] is True, "PL retried after the hour, recovers")
# other errors retry at the normal interval
c = []
embassy.poll(now=NOW + 300 + 3600 + 300, fetch=fake(c, fail={"UA": urllib.error.URLError("timed out")}), max_fetch=38)
s = alerts._load(embassy.STATE, {})["UA"]
check(s["err"].startswith("URLError") and not s.get("backoff_until") and s["next_due"] == NOW + 300 + 3600 + 600 and s["items"],
      "URLError: error recorded, no backoff, retry in 300 s, old items kept")
# 429 ends the round
reset()
c = []
d = embassy.poll(now=NOW, fetch=fake(c, fail={"IL": http(429)}))
check(c == ["IL"] and d["fetched"] == 1, "429 stops this call's round")
c = []
embassy.poll(now=NOW + 60, fetch=fake(c))
check(c == CODES[1:9], "next call carries on with the other posts, IL backed off")

# every attempted post failing -> RuntimeError (only once at least 5 have been tried)
reset()
d = embassy.poll(now=NOW, fetch=fake([], fail={"*": http(403)}), max_fetch=3)
check(d["errors"] == 3, "3 posts failing: not yet an outage")
try:
    embassy.poll(now=NOW + 60, fetch=fake([], fail={"*": http(403)}), max_fetch=3)
    check(False, "6 of 6 failing raises")
except RuntimeError as e:
    check(str(e).startswith("all embassy feeds failing:") and "HTTP 403" in str(e), "6 of 6 failing -> RuntimeError (%s)" % e)
check(sum(1 for v in alerts._load(embassy.STATE, {}).values() if v.get("backoff_until")) == 6, "backoffs saved before raising")
reset()
embassy.poll(now=NOW, fetch=fake([], fail={"IL": http(403), "LB": http(403), "IQ": http(403), "JO": http(403)}), max_fetch=5)
check(embassy.poll(now=NOW + 60, fetch=fake([]), max_fetch=0)["errors"] == 4, "one post working among 5 tried: no outage")

# max 60 items, newest first
syn = "".join("<item><title>Security Alert: Synthetic %d</title><link>https://x.test/s%d</link><pubDate>%s</pubDate></item>"
              % (i, i, email.utils.formatdate(NOW - 600 * i, usegmt=True)) for i in range(70))
SYN = dict(SERVE, IL=('<rss version="2.0"><channel><title>s</title>%s</channel></rss>' % syn).encode("utf-8"))
reset()
big = embassy.poll(now=NOW, fetch=fake([], serve=SYN), max_fetch=38)
check(len(big["items"]) == 60 and big["items"][0]["t"] == NOW and all(a["t"] >= b["t"] for a, b in zip(big["items"], big["items"][1:])),
      "capped at 60, newest first")

# ---- view(): slim, stable, counts
reset()
da = embassy.poll(now=NOW, fetch=fake([]), max_fetch=38)
v1, v2 = embassy.view(da, now=NOW), embassy.view(da, now=NOW)
check(v1 == v2 and v1["counts"] == {"24h": 1, "72h": 2}, "view counts: 1 in 24 h (Warsaw), 2 in 72 h (+ Kyiv)")
check(all(set(x) == set(embassy.VIEW_FIELDS) for x in v1["items"]) and len(v1["posts"]) == 38, "view fields")
js = json.dumps(v1)
check(not any(k in js for k in ('"checked"', '"next_due"', '"backoff_until"', '"fetched"')), "no per-post check times in the view")
db = embassy.poll(now=NOW + 300, fetch=fake([]))
dc = embassy.poll(now=NOW + 600, fetch=fake([]))
check(db["fetched"] == 8 and embassy.view(db, now=NOW + 300) == embassy.view(dc, now=NOW + 600) == v1,
      "quiet polls give an identical view (stable ETag)")
check(embassy.view(None) == embassy.view({}) == {"items": [], "posts": [], "counts": {"24h": 0, "72h": 0}}, "view of no data")
check(len(embassy.view(big, now=NOW)["items"]) == 40 and embassy.view(big, now=NOW)["counts"]["24h"] == 60, "view shows 40, counts all")
one = embassy.view({"items": da["items"][:1], "posts": da["posts"][20:21]}, now=NOW)
print("     view() example:", json.dumps(one, ensure_ascii=False))

# ---- summary() for the analyst
s = embassy.summary(da, now=NOW)
check(s["alerts_24h"] == 1 and len(s["latest"]) == 3, "summary: 1 alert in 24 h, 3 latest")
check(s["latest"][0] == {"post": "PL", "kind": "security", "title": "Security Alert: U.S. Embassy Warsaw (November 18, 2026)",
                         "at": "2026-11-18T17:37:57Z"} and s["latest"][2]["post"] == "RU+UA", "summary entries; merged post 'RU+UA'")
check(len(json.dumps(s).encode()) < 1024, "summary < 1 KB (%d)" % len(json.dumps(s)))
huge = {"items": [{"c": "IL", "posts": CODES[:20], "kind": "departure", "title": "Ordered Departure " * 20, "t": NOW - i}
                  for i in range(10)]}
sh = embassy.summary(huge, now=NOW)
check(len(json.dumps(sh).encode()) < 1024 and len(json.dumps(sh, ensure_ascii=False).encode()) < 1024 and sh["latest"],
      "summary stays under 1 KB with long titles and 20-post merges (%d, %d entries)" % (len(json.dumps(sh)), len(sh["latest"])))
check(all(len(x["title"]) <= 100 for x in embassy.summary(big, now=NOW)["latest"]), "summary titles <= 100 chars")
check(embassy.summary(None) == {"alerts_24h": 0, "latest": []} and embassy.summary({"items": [{"x": 1}]}) == {"error": "KeyError"},
      "summary of nothing; bad data -> error type, never raises")
print("%d checks passed" % ok)
