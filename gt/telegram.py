"""Telegram channel posts from the public web previews. v1.1, 2026-11-20 (Ground Truth 1.5.0; v1.0 in 0.12.0).

Feed `telegram` (called every 300 s). Each channel's public preview page `https://t.me/s/<channel>` (no login, no
API key, the newest ~20 posts) is fetched at most once every 5 min, one channel after another, 1.5 s apart.
CHANNELS is a plain constant for the main thread to edit; every channel in it answered one test fetch on
2026-11-20 (all ten had a public preview, newest posts between 11-19 17:57Z and 11-20 05:17Z). 1.1 adds
Faytuks_Network, the live channel of Faytuks News (asked for: "faytuks news telegram"); the older handles
faytuksnews, FaytuksTelegram and FaytuksNewss last posted in 2026-02, 2024-04 and 2022-05. 1.1 also adds, for the
Middle East (asked for: "iran activity ... and middle east as a whole"; each had posts from the last 24 h on
2026-11-21): Middle_East_Spectator (anonymous aggregator, pro-Axis tilt), AlMayadeenEnglish (Al Mayadeen, aligned
with Hezbollah and the "Axis of Resistance"; its website feed is blocked) and irna_en (IRNA, Iran's state news
agency; its website sits behind a bot wall).

The page is fragile HTML, so the parser is tolerant: it cuts the page at each `data-post="<channel>/<id>"` and,
inside each piece, takes the `<time datetime=...>`, the post's own `tgme_widget_message_text` (not the quoted
reply's `js-message_reply_text`), the view count ("213K"), photo / video / document flags and the forward name.
A piece it cannot read is skipped and counted; a page without any post is reported as that channel's error.
Text keeps line breaks and emoji; channel signatures, separators and casino adverts are removed; posts that are
only an advert are dropped. A post without text keeps its media flags and gets a title such as "(video)".

Items use the wire schema (gt/wire.py) with source "telegram", source_label "@<channel>", the post link
`https://t.me/<channel>/<id>`, kind "telegram", plus views, has_photo, has_video, forwarded and forwarded_from (often
hidden, so None). A post whose media Telegram will not preview gets the title "(media: open in Telegram)". Countries
come from gt/placer.py (which reads flag emoji and Russian / Ukrainian names too); idfofficial and UkraineNow fill in
ISR / UKR when a post names no place. 48 h kept, newest 300 returned.

Terms: posts are the channels' own content, shown as short text with a link back. PUBLIC_OK is False, NON_COMMERCIAL
is True. Several channels are partisan (rybar is Russian military-blogger content; idfofficial is a party to the
war); the UI should show the channel on every post.
"""
import hashlib
import html
import re
import threading
import time
import urllib.error

from . import geo, mymaps, placer, wire

VERSION = "1.1"
LICENCE = ("Telegram channel posts, each the channel's own content: short text with a link back; non-commercial, "
           "never for the trading agent, not for the public mirror.")
ATTRIBUTION = "Public Telegram channel previews (t.me/s/<channel>); each post links to its channel."
NON_COMMERCIAL = True
PUBLIC_OK = False

CHANNELS = ("OSINTdefender", "rybar", "intelslava", "WarMonitors", "DDGeopolitics", "BellumActaNews",
            "CIG_telegram", "nexta_live", "UkraineNow", "idfofficial", "Faytuks_Network", "Middle_East_Spectator",
            "AlMayadeenEnglish", "irna_en")
HINTS = {"idfofficial": "ISR", "UkraineNow": "UKR", "irna_en": "IRN"}  # official / single-country channels
PAGE = "https://t.me/s/%s"
POST = "https://t.me/%s/%s"
INTERVAL = 300         # s, per channel at most
SLACK = 20
STAGGER = 1.5          # s between two channel requests
WINDOW = 48 * 3600
MAX_ITEMS = 300
MAX_STORE = 3000
MAX_BYTES = 400000
TITLE_MAX = 160
SUMMARY_MAX = 200
BACKOFF = 3600         # after 403 / 429
STATE = "telegram_state.json"
_LOCK = threading.Lock()
_sleep = time.sleep    # tests replace it

# ---------------- parsing ----------------

_POST = re.compile(r'data-post="([A-Za-z0-9_]{3,64})/(\d+)"')
_TIME = re.compile(r'<time\b[^>]*\bdatetime="([^"]+)"')
_TEXT_OPEN = re.compile(r'<div\b[^>]*\bclass="([^"]*\btgme_widget_message_text\b[^"]*)"[^>]*>')
_DIV = re.compile(r"<(/?)div\b[^>]*>", re.I)
_VIEWS = re.compile(r'class="tgme_widget_message_views"[^>]*>\s*([^<]+?)\s*<')
_FWD = re.compile(r'class="tgme_widget_message_forwarded_from_name"[^>]*>(.*?)</(?:a|span)>', re.S)
_PHOTO = re.compile(r'class="[^"]*\btgme_widget_message_photo(?:_wrap)?\b')
_VIDEO = re.compile(r'class="[^"]*\btgme_widget_message_(?:video_player|video_wrap|video|roundvideo)\b|<video\b')
_DOC = re.compile(r'class="[^"]*\btgme_widget_message_(?:document|voice|poll|sticker|location|venue|audio)')
_SERVICE = re.compile(r'class="[^"]*\bservice_message\b')
_UNSUPPORTED = re.compile(r'class="[^"]*\bmessage_media_not_supported\b')  # "view in Telegram" media
_FWD_ANY = re.compile(r'class="[^"]*\btgme_widget_message_forwarded_from\b')
_FOOTER = re.compile(r"(?i)^\W*(?:subscribe|join|follow|support us|share|подписаться|подписывайтесь|підписатись|"
                     r"підписуйтесь|поддержать|надіслати новину|прислать новость|ми у whatsapp|мы в whatsapp|"
                     r"наш чат|our chat|chat room)\b")
_SPAM = re.compile(r"(?i)rainbet|casino|sportsbook|non-kyc|promo code|airdrop|\bbet now\b|\b18\+")
_SEP = re.compile(r"^[\s\-–—_=~•·➖▪️*|]{3,}$")
_HANDLE_ONLY = re.compile(r"^[\W\d_]*(?:@\w+[\W_]*)+$")
_HASHTAGS_ONLY = re.compile(r"^(?:\s*#\w+)+\s*$")


def views(s):
    """'213K' -> 213000, '1.2M' -> 1200000, '987' -> 987; None when unreadable."""
    m = re.match(r"^\s*([\d.,]+)\s*([KkMm]?)\s*$", s or "")
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(round(n * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]))


def _inner_div(block, start):
    """HTML inside the <div> whose opening tag ends at `start`, up to its matching </div>."""
    depth = 1
    for m in _DIV.finditer(block, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return block[start:m.start()]
    return block[start:]


def to_text(h):
    """Message HTML -> plain text with line breaks (emoji kept: they sit in <b> inside <i class="emoji">)."""
    h = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", h or "")
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</blockquote>|</pre>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in html.unescape(h).split("\n")]
    return "\n".join(lines).strip()


def tidy(text):
    """Channel signatures, separators, handle-only lines and adverts out; blank runs collapsed."""
    out = []
    for ln in (text or "").split("\n"):
        s = ln.strip()
        if not s:
            if out and out[-1]:
                out.append("")
            continue
        if _SEP.match(s) or _HANDLE_ONLY.match(s) or _FOOTER.match(s) or _SPAM.search(s):
            continue
        out.append(s)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def lang_of(text):
    letters = [c for c in text or "" if c.isalpha()]
    if not letters:
        return None
    n = float(len(letters))
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    if cyr / n > 0.3:
        return "uk" if re.search("[іїєґІЇЄҐ]", text) else "ru"
    if sum(1 for c in letters if "֐" <= c <= "׿") / n > 0.3:
        return "he"
    if sum(1 for c in letters if "؀" <= c <= "ۿ") / n > 0.3:
        return "ar"
    return "en"


def _title(text, media):
    """-> (title, rest): the first line with words in it (hashtag-only lines skipped), and the text after it."""
    lines = (text or "").split("\n")
    for k, ln in enumerate(lines):
        s = ln.strip()
        if s and not _HASHTAGS_ONLY.match(s) and sum(1 for c in s if c.isalpha()) >= 3:
            return wire.cut(s, TITLE_MAX), "\n".join(lines[k + 1:]).strip()
    if text and text.strip():
        return wire.cut(text.strip().split("\n")[0], TITLE_MAX), ""
    return ("(%s)" % media if media else None), ""


def parse_page(page, channel=None):
    """A t.me/s/ page -> (posts, skipped). posts: dicts with channel, id, t, text, views, has_photo, has_video,
    has_document, has_other_media (Telegram's "view in Telegram" box), forwarded, forwarded_from (None when the
    name is hidden). Pieces that cannot be read are counted in `skipped`, never raised."""
    if isinstance(page, bytes):
        page = page.decode("utf-8", "replace")
    marks = list(_POST.finditer(page))
    starts = [max(page.rfind("<", 0, m.start()), 0) for m in marks]  # from the tag that carries data-post
    posts, skipped = [], 0
    for k, m in enumerate(marks):
        block = page[starts[k]:starts[k + 1] if k + 1 < len(marks) else len(page)]
        try:
            if _SERVICE.search(block[:600]):
                skipped += 1
                continue
            tm = _TIME.search(block)
            t = wire.parse_time(tm.group(1)) if tm else None
            text = ""
            for tx in _TEXT_OPEN.finditer(block):
                if "reply" in tx.group(1):
                    continue
                text = to_text(_inner_div(block, tx.end()))
                break
            vm, fm = _VIEWS.search(block), _FWD.search(block)
            reply_cut = re.sub(r'(?s)<a\b[^>]*class="tgme_widget_message_reply\b.*?</a>', "", block)
            posts.append({"channel": m.group(1), "id": int(m.group(2)), "t": t, "text": text,
                          "views": views(vm.group(1)) if vm else None,
                          "has_photo": bool(_PHOTO.search(reply_cut)), "has_video": bool(_VIDEO.search(reply_cut)),
                          "has_document": bool(_DOC.search(reply_cut)),
                          "has_other_media": bool(_UNSUPPORTED.search(reply_cut)),
                          "forwarded": bool(_FWD_ANY.search(reply_cut)),
                          "forwarded_from": wire.clean(fm.group(1)) or None if fm else None})
        except Exception:  # noqa: BLE001  fragile HTML: skip the piece, keep the page
            skipped += 1
    return posts, skipped


def make_item(post, channel, now):
    """A parsed post -> a wire-schema item, or None (no time, older than 48 h, empty, or only an advert)."""
    t = post.get("t")
    if t is None or now - t > WINDOW:
        return None
    if t > now + wire.FUTURE_SLACK:
        t = int(now)
    raw = post.get("text") or ""
    if raw and _SPAM.search(raw) and not tidy(raw):
        return None
    text = tidy(raw)
    media = "video" if post.get("has_video") else "photo" if post.get("has_photo") else \
        "document" if post.get("has_document") else "media: open in Telegram" if post.get("has_other_media") else None
    if not text and not media:
        return None
    title, rest = _title(text, media)
    ch = post.get("channel") or channel
    url = POST % (ch, post["id"])
    pl = placer.place(text[:600]) if text else {"countries": [], "theatre": None}
    countries, theatre, placed = pl["countries"], pl["theatre"], ("text" if pl["countries"] or pl["theatre"]
                                                                  else None)
    hint = HINTS.get(channel)
    if not countries and hint:
        countries, theatre, placed = [hint], geo.theatre_for_a3(hint), "source"
    cat, tags = mymaps.classify(title if not title.startswith("(") else "", None)
    return {"id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:16], "title": title, "url": url,
            "source": "telegram", "source_label": "@" + channel, "channel": channel, "ts_ms": int(t) * 1000,
            "ts": wire._iso(int(t)), "lang": lang_of(text), "countries": countries, "theatre": theatre,
            "placed": placed, "category": cat, "tags": tags,
            "summary": wire.cut(rest.replace("\n", " "), SUMMARY_MAX) if rest else None, "also_in": [],
            "kind": "telegram", "views": post.get("views"), "has_photo": post.get("has_photo", False),
            "has_video": post.get("has_video", False), "forwarded": post.get("forwarded", False),
            "forwarded_from": post.get("forwarded_from")}


# ---------------- polling ----------------

def _get(channel, fetch):
    status, _h, body = fetch(PAGE % channel, {})
    if status and status >= 400:
        raise urllib.error.HTTPError(PAGE % channel, status, "HTTP %d" % status, None, None)
    posts, skipped = parse_page(wire._ungzip(body or b""), channel)
    if not posts:
        raise ValueError("no posts on the page (preview off, or the layout changed)")
    return posts, skipped


def poll(now=None, fetch=None, channels=None):
    """Feed `telegram` (every 300 s): fetch the channels that are due, return the newest posts."""
    now = wire._now_epoch(now)
    fetch = fetch or wire._fetch
    channels = tuple(channels or CHANNELS)
    with _LOCK:
        st = wire.load_state(STATE)
        due = []
        for ch in channels:
            s = st["sources"].get(ch) or {}
            nd = max(s.get("next_due") or 0, s.get("backoff_until") or 0)
            if nd <= now + SLACK:
                due.append((nd, ch))
        due.sort()
        fetched = 0
        for k, (_nd, ch) in enumerate(due):
            if k:
                _sleep(STAGGER)
            s = st["sources"].setdefault(ch, {})
            s["checked"] = int(now)
            s["next_due"] = int(now + INTERVAL)
            fetched += 1
            try:
                posts, skipped = _get(ch, fetch)
            except Exception as e:  # noqa: BLE001  one channel never fails the feed
                s.update(ok=False, error=wire._err(e))
                if isinstance(e, urllib.error.HTTPError) and e.code in (403, 429):
                    s["backoff_until"] = int(now + BACKOFF)
                    if e.code == 429:
                        break  # asked to slow down: the rest wait for the next call
                continue
            s.update(ok=True, error=None, backoff_until=None, posts=len(posts), skipped=skipped)
            for p in posts:
                try:
                    it = make_item(p, ch, now)
                except Exception:  # noqa: BLE001  one odd post never fails its channel
                    it = None
                if it is None:
                    continue
                s["newest_t"] = max(s.get("newest_t") or 0, it["ts_ms"] // 1000)
                st["items"].setdefault(it["id"], it)
        keep = [x for x in st["items"].values() if now * 1000 - x["ts_ms"] <= WINDOW * 1000]
        keep.sort(key=lambda x: (-x["ts_ms"], x["id"]))
        st["items"] = {x["id"]: x for x in keep[:MAX_STORE]}
        if fetched:
            wire.save_state(st, STATE)
        tried = [c for c in channels if (st["sources"].get(c) or {}).get("checked")]
        bad = [c for c in tried if st["sources"][c].get("ok") is False]
        if len(tried) >= 3 and len(bad) == len(tried):
            errs = sorted({st["sources"][c].get("error") or "?" for c in bad})
            raise RuntimeError("all Telegram channels failing: %d (%s)" % (len(bad), "; ".join(errs)[:200]))
        return _output(st, now, channels, fetched, keep)


def _output(st, now, channels, fetched, keep):
    per = {}
    by_theatre, by_country, by_country_24h = {}, {}, {}
    for x in keep:
        per[x["channel"]] = per.get(x["channel"], 0) + 1
        th = x.get("theatre") or "unplaced"
        by_theatre[th] = by_theatre.get(th, 0) + 1
        if x.get("countries"):
            c = x["countries"][0]
            by_country[c] = by_country.get(c, 0) + 1
            if now * 1000 - x["ts_ms"] <= 86400 * 1000:
                by_country_24h[c] = by_country_24h.get(c, 0) + 1
    rows = []
    for ch in channels:
        s = st["sources"].get(ch) or {}
        rows.append({"name": ch, "label": "@" + ch, "ok": s.get("ok"), "error": s.get("error"),
                     "newest": wire._iso(s.get("newest_t")), "n": per.get(ch, 0), "posts": s.get("posts"),
                     "skipped": s.get("skipped"), "checked": wire._iso(s.get("checked"))})
    out = {"version": VERSION, "fetched_at": wire._iso(int(now)), "count": 0, "total": len(keep), "fetched": fetched,
           "sources": rows, "attribution": ATTRIBUTION, "licence": LICENCE, "items": keep[:MAX_ITEMS],
           "by_theatre": by_theatre, "by_country": by_country, "by_country_24h": by_country_24h}
    return wire.fit(out, MAX_BYTES)


FEEDS = {"telegram": (poll, 300)}
