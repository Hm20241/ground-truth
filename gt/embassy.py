"""US embassy alerts. v1.0 (Ground Truth 0.8.0), 2026-11-18.

Every US embassy and consulate posts its security, demonstration, weather and health alerts for US citizens to a
WordPress category whose RSS is free and keyless: `https://<cc>.usembassy.gov/category/alert/feed/` (AIT Taipei and
Embassy Beijing have their own domains). 38 posts are watched, the Middle East and Europe's eastern flank every
5 min ("fast"), East Asia, South Asia and the Americas every 15 min ("slow").

The scheduler calls poll() every 60 s. Each call fetches at most 8 posts that are due, one after the other, with
If-Modified-Since (an unchanged feed costs a 304), so a cold start sweeps all 38 in about 5 calls and the steady
load is about 6 small requests a minute. A post that answers 403 or 429 is left alone for an hour.

Items are the post's title, link and date, a kind from the title (body text only decides routine messages), and
the "Location:" / "Event:" lines of the alert template when present. Consular outreach, voting and benefits
notices are dropped. The same alert posted by several embassies on the same day (Europe-wide holiday travel
alerts) is one item listing every post. Texts are US government works (public domain).

Requests are plain: an honest User-Agent (gt/alerts.py's) and no borrowed Origin/Referer headers.
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import threading
import time
import urllib.error
import xml.etree.ElementTree as ET

from . import alerts

STATE = "embassy_posts.json"  # in alerts.CACHE
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
INTERVAL = {"fast": 300, "slow": 900}
TIMEOUT = 15
BACKOFF = 3600  # after 403 / 429
MAX_FETCH = 8
WINDOW = 7 * 86400
MAX_ITEMS = 60
VIEW_ITEMS = 40
VIEW_FIELDS = ("id", "c", "posts", "title", "url", "t", "kind", "loc", "event")
POST_FIELDS = ("c", "n", "city", "lat", "lon", "ok", "err", "last_t")
_US = "https://%s.usembassy.gov/category/alert/feed/"

# (code, country, city, lat, lon, tier, url); lat/lon are city centres (2 decimals). Order = display order.
POSTS = tuple((c, n, city, lat, lon, tier, url or _US % c.lower()) for c, n, city, lat, lon, tier, url in (
    ("IL", "Israel", "Jerusalem", 31.77, 35.22, "fast", None),
    ("LB", "Lebanon", "Beirut", 33.89, 35.50, "fast", None),
    ("IQ", "Iraq", "Baghdad", 33.31, 44.37, "fast", None),
    ("JO", "Jordan", "Amman", 31.95, 35.93, "fast", None),
    ("SY", "Syria", "Damascus", 33.51, 36.29, "fast", None),
    ("IR", "Iran", "Tehran", 35.69, 51.39, "fast", None),
    ("SA", "Saudi Arabia", "Riyadh", 24.71, 46.68, "fast", None),
    ("AE", "United Arab Emirates", "Abu Dhabi", 24.45, 54.38, "fast", None),
    ("QA", "Qatar", "Doha", 25.29, 51.53, "fast", None),
    ("BH", "Bahrain", "Manama", 26.23, 50.59, "fast", None),
    ("KW", "Kuwait", "Kuwait City", 29.38, 47.99, "fast", None),
    ("OM", "Oman", "Muscat", 23.59, 58.41, "fast", None),
    ("YE", "Yemen", "Sanaa", 15.37, 44.19, "fast", None),
    ("EG", "Egypt", "Cairo", 30.04, 31.24, "fast", None),
    ("TR", "Turkey", "Ankara", 39.93, 32.86, "fast", None),
    ("CY", "Cyprus", "Nicosia", 35.19, 33.38, "fast", None),
    ("UA", "Ukraine", "Kyiv", 50.45, 30.52, "fast", None),
    ("RU", "Russia", "Moscow", 55.76, 37.62, "fast", None),
    ("BY", "Belarus", "Minsk", 53.90, 27.56, "fast", None),
    ("MD", "Moldova", "Chisinau", 47.01, 28.86, "fast", None),
    ("PL", "Poland", "Warsaw", 52.23, 21.01, "fast", None),
    ("LT", "Lithuania", "Vilnius", 54.69, 25.28, "fast", None),
    ("LV", "Latvia", "Riga", 56.95, 24.11, "fast", None),
    ("EE", "Estonia", "Tallinn", 59.44, 24.75, "fast", None),
    ("FI", "Finland", "Helsinki", 60.17, 24.94, "fast", None),
    ("GE", "Georgia", "Tbilisi", 41.72, 44.79, "fast", None),
    ("AM", "Armenia", "Yerevan", 40.18, 44.51, "fast", None),
    ("AZ", "Azerbaijan", "Baku", 40.41, 49.87, "fast", None),
    ("TW", "Taiwan", "Taipei", 25.03, 121.57, "slow", "https://www.ait.org.tw/category/alert/feed/"),
    ("CN", "China", "Beijing", 39.90, 116.41, "slow", "https://china.usembassy-china.org.cn/category/alert/feed/"),
    ("KR", "South Korea", "Seoul", 37.57, 126.98, "slow", None),
    ("JP", "Japan", "Tokyo", 35.68, 139.69, "slow", None),
    ("PH", "Philippines", "Manila", 14.60, 120.98, "slow", None),
    ("PK", "Pakistan", "Islamabad", 33.68, 73.05, "slow", None),
    ("AF", "Afghanistan", "Kabul", 34.53, 69.17, "slow", None),
    ("MX", "Mexico", "Mexico City", 19.43, -99.13, "slow", None),
    ("HT", "Haiti", "Port-au-Prince", 18.54, -72.34, "slow", None),
    ("VE", "Venezuela", "Caracas", 10.48, -66.90, "slow", None),
))
_ORDER = {p[0]: i for i, p in enumerate(POSTS)}
_LOCK = threading.Lock()


# ---------------- classification ----------------

_HOLIDAY = re.compile(r"holiday|thanksgiving|christmas|new year|independence day|labou?r day|memorial day|columbus day|"
                      r"veterans.? day|martin luther king|presidents.? day|juneteenth|national day", re.I)
# First match wins. The closure test is skipped for holiday closures ("Embassy closed for Thanksgiving").
# Bare "Alert" comes after the routine test: "ALERT – MESSAGE FOR U.S. CITIZENS: consular services in Lviv" is routine.
KINDS = tuple((k, re.compile(rx, re.I)) for k, rx in (
    ("departure", r"(?:ordered|authorized) departure|evacuat|suspen(?:d|ds|ded|ding|sion)\b(?:\s+\S+){0,3}?\s+operations"),
    ("closure", r"\b(?:embassy|consulate)\b[^.]{0,40}?\bclos(?:ed|ure|ing|es)\b|\bclos(?:ed|ure|ing)\b[^.]{0,30}?\b(?:embassy|consulate)\b"),
    ("shelter", r"shelter|air.?defen[cs]e|civil defen[cs]e|air.?raid|missile|rocket|drone|siren"),
    ("demonstration", r"demonstration|protest|\brall(?:y|ies)\b|\bstrikes?\b"),
    ("weather", r"weather|typhoon|hurricane|cyclone|\bstorms?\b|flood|earthquake|volcan|wildfire|natural disaster|tsunami"),
    ("health", r"health|outbreak|ebola|cholera|disease|mpox"),
    ("advisory", r"travel advisory"),
    ("worldwide", r"worldwide caution"),
    ("security", r"security (?:alert|message)"),
    ("routine", r"routine message|message (?:for|to) (?:u\.\s?s\.|us|american) citizens"),
    ("security", r"\balert\b"),
))
# Body text can only name one of these (boilerplate mentions "security", "alerts", "Worldwide Caution" everywhere).
BODY_KINDS = ("departure", "closure", "shelter", "demonstration", "weather", "health")
KEEP = re.compile(r"security|shelter|demonstrat|exercise|curfew|closure|closed|evacuat|airport|airspace|border|"
                  r"civil defen|air defen", re.I)


def _kind(s, only=None):
    for k, rx in KINDS:
        if only and k not in only:
            continue
        if rx.search(s):
            if k == "closure":
                if _HOLIDAY.search(s):
                    continue
                k = "departure"
            return k
    return None


def classify(title, text=""):
    """Alert kind from the title; the body (Event text) decides only for routine messages and unknown titles."""
    k = _kind(title or "") or "other"
    if k in ("routine", "other") and text:
        return _kind(text, BODY_KINDS) or k
    return k


def keep(item):
    """Drop noise: unknown kinds, and routine messages that name nothing security-relevant."""
    k = item.get("kind")
    if k == "other":
        return False
    if k != "routine":
        return True
    s = "%s %s" % (item.get("title") or "", item.get("event") or "")
    hits = {w.lower() for w in KEEP.findall(s)}
    if hits - {"closure", "closed"}:
        return True
    return bool(hits) and not _HOLIDAY.search(s)


# ---------------- parsing ----------------

_BLOCK = re.compile(r"(?i)<br\s*/?>|</?(?:p|div|li|ul|ol|h[1-6]|section|tr|td|th|table|blockquote)\b[^>]*>")
_LOC = re.compile(r"(?i)^location\s*:\s*(.*)$")
_EVT = re.compile(r"(?i)^event\s*:\s*(.*)$")
_STOP = re.compile(r"(?i)^(?:actions to take|assistance|location\s*:|contact(?: information)?\s*:)")
_INLINE = re.compile(r"(?i)^(location\s*:.*?)\s+(event\s*:.*)$")


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def _norm(s):
    """Lowercase, punctuation to spaces, whitespace collapsed (the merge key)."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def _cut(s, n):
    """Collapse whitespace; over n chars, cut on a word boundary and end with an ellipsis (total <= n)."""
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= n:
        return s or None
    c = s[:n - 1]
    if s[n - 1] != " " and " " in c:
        c = c[:c.rindex(" ")]
    return c.rstrip(" ,;:.-–—") + "…"


def _epoch(s):
    try:
        d = email.utils.parsedate_to_datetime((s or "").strip())
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def _lines(h):
    h = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", h or "")
    h = re.sub(r"<[^>]*>", "", _BLOCK.sub("\n", h))
    out = (re.sub(r"\s+", " ", ln).strip() for ln in html.unescape(h).split("\n"))
    return [ln for ln in out if ln]


def _template(lines, title):
    """(location, event, lead) from the body lines. lead = opening text, for bodies without the template."""
    nt, i = _norm(title), 0
    while i < len(lines) and i < 3 and _norm(lines[i]) and nt.startswith(_norm(lines[i])):
        i += 1  # the title, repeated as the page header and often as the first paragraph
    flat = []
    for ln in lines[i:]:
        m = _INLINE.match(ln)
        flat.extend(m.groups() if m else [ln])
    loc, ev, mode = None, None, None
    for ln in flat:
        if mode == "loc":
            loc, mode = ln, None
            continue
        m = _LOC.match(ln)
        if m:
            if loc is None:
                loc = m.group(1) or None
                mode = None if loc else "loc"
            elif mode == "event":
                mode = None
            continue
        m = _EVT.match(ln)
        if m and ev is None:
            ev, mode = ([m.group(1)] if m.group(1) else []), "event"
            continue
        if mode == "event":
            if _STOP.match(ln) or sum(len(x) for x in ev) > 1500:
                mode = None
            else:
                ev.append(ln)
    event = " ".join(ev) if ev else None
    return loc, event, (" ".join(flat)[:400] if event is None else "")


def _item(it, code):
    title = _clean(it.findtext("title"))
    link = (it.findtext("link") or it.findtext("guid") or "").strip()
    t = _epoch(it.findtext("pubDate"))
    if not title or not link or t is None:
        return None
    loc, event, lead = _template(_lines(it.findtext(CONTENT) or it.findtext("description")), title)
    return {"id": hashlib.sha1(link.encode("utf-8")).hexdigest()[:12], "c": code, "title": title, "url": link, "t": t,
            "kind": classify(title, (event or lead)[:600]), "loc": _cut(loc, 160), "event": _cut(event, 240)}


def parse_feed(xml_bytes, code):
    """A post's WordPress RSS -> items. A broken item is skipped; a document that is not RSS raises."""
    root = ET.fromstring(xml_bytes)
    ch = root.find("channel")
    if ch is None:
        raise ValueError("no RSS channel")
    out = []
    for it in ch.findall("item"):
        try:
            x = _item(it, code)
        except Exception:
            continue
        if x:
            out.append(x)
    return out


# ---------------- polling ----------------

def _day(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def _merge(items):
    """Same normalised title on the same UTC day = one alert posted by several embassies."""
    groups = {}
    for x in items:
        groups.setdefault((_norm(x["title"]) or x["id"], _day(x["t"])), []).append(x)
    out = []
    for g in groups.values():
        g.sort(key=lambda x: (_ORDER.get(x["c"], 99), -x["t"]))
        m = dict(g[0], t=max(x["t"] for x in g), posts=sorted({x["c"] for x in g}))
        out.append(m)
    out.sort(key=lambda x: -x["t"])
    return out[:MAX_ITEMS]


def _data(st, now, fetched):
    items, posts = [], []
    for c, n, city, lat, lon, tier, url in POSTS:
        s = st.get(c) or {}
        mine = [x for x in s.get("items") or [] if now - x["t"] <= WINDOW]
        items.extend(mine)
        last = max([x["t"] for x in mine] + ([s["last_t"]] if s.get("last_t") else []), default=None)
        posts.append({"c": c, "n": n, "city": city, "lat": lat, "lon": lon, "ok": s.get("ok"), "err": s.get("err"),
                      "last_t": last})
    return {"items": _merge(items), "posts": posts, "fetched": fetched,
            "errors": sum(1 for p in posts if p["ok"] is False)}


def poll(now=None, fetch=None, max_fetch=MAX_FETCH):
    """Feed `embassy` (called every 60 s): fetch the posts that are due, return the merged alert list."""
    now = now or time.time()
    fetch = fetch or alerts.fetch
    with _LOCK:
        st = alerts._load(STATE, {})
        if not isinstance(st, dict):
            st = {}
        due = []
        for i, p in enumerate(POSTS):
            s = st.get(p[0]) if isinstance(st.get(p[0]), dict) else {}
            st[p[0]] = s
            nd = max(s.get("next_due") or 0, s.get("backoff_until") or 0)
            if nd <= now:
                due.append((nd, i))
        due.sort()
        fetched = 0
        for nd, i in due[:max_fetch]:
            code, tier, url = POSTS[i][0], POSTS[i][5], POSTS[i][6]
            s = st[code]
            s["checked"] = int(now)
            s["next_due"] = int(now + INTERVAL[tier])
            fetched += 1
            try:
                items = [x for x in parse_feed(fetch(url, timeout=TIMEOUT, conditional=True), code) if keep(x)]
            except urllib.error.HTTPError as e:
                s.update(ok=False, err="HTTP %d" % e.code)
                if e.code in (403, 429):
                    s["backoff_until"] = int(now + BACKOFF)
                if e.code == 429:
                    break  # asked to slow down: leave the rest of this round for the next call
                continue
            except Exception as e:
                s.update(ok=False, err="%s: %s" % (type(e).__name__, str(e)[:120]))
                continue
            s.update(ok=True, err=None, backoff_until=None,
                     last_t=max((x["t"] for x in items), default=None),
                     items=[x for x in items if now - x["t"] <= WINDOW])  # older ones never reach the view
        if fetched:
            alerts._save(STATE, st)
        tried = [p[0] for p in POSTS if st[p[0]].get("checked")]
        bad = [c for c in tried if st[c].get("ok") is False]
        if len(tried) >= 5 and len(bad) == len(tried):
            errs = sorted({st[c].get("err") or "?" for c in bad})
            raise RuntimeError("all embassy feeds failing: %d posts (%s)" % (len(bad), "; ".join(errs)[:200]))
        return _data(st, now, fetched)


# ---------------- view + compact summary ----------------

def view(data, now=None):
    """Block for /api/alerts. No per-post check times, so the ETag stays put between quiet polls."""
    d = data or {}
    items = d.get("items") or []
    now = now or time.time()
    return {"items": [{k: x.get(k) for k in VIEW_FIELDS} for x in items[:VIEW_ITEMS]],
            "posts": [{k: p.get(k) for k in POST_FIELDS} for p in d.get("posts") or []],
            "counts": {"24h": sum(1 for x in items if now - x["t"] <= 86400),
                       "72h": sum(1 for x in items if now - x["t"] <= 3 * 86400)}}


def summary(data, now=None):
    """For the analyst (under 1 KB): alerts in the last 24 h and the 6 newest."""
    try:
        now = now or time.time()
        items = (data or {}).get("items") or []
        out = {"alerts_24h": sum(1 for x in items if now - x["t"] <= 86400), "latest": []}
        for cap in (100, 80, 60, 40):  # shorter titles first, then fewer entries, until it fits
            out["latest"] = [{"post": "+".join(x.get("posts") or [x["c"]]), "kind": x["kind"],
                              "title": _cut(x["title"], cap), "at": alerts._iso(x["t"])} for x in items[:6]]
            if len(json.dumps(out)) < 1024:
                break
        while out["latest"] and len(json.dumps(out)) >= 1024:
            out["latest"].pop()
        return out
    except Exception as e:  # never break /api/summary
        return {"error": type(e).__name__}
