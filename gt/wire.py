"""Live wire: worldwide news headlines placed by country. v1.1, 2026-11-20 (Ground Truth 1.5.0; v1.0 in 0.12.0).

Feed `wire` (called every 300 s). Each source has its own cadence, kept in <GT_DATA>/cache/wire_state.json, so one
call fetches only the sources that are due (a cold start fetches them all):
* fast, every 5 min: Al Jazeera, BBC World, France 24, DW, Kyiv Independent, Times of Israel;
* every 15 min: BBC Africa / Asia / Latin America / Middle East, Middle East Eye, SCMP, Africanews, allAfrica,
  Guardian Americas, Military Times, UN News, The Moscow Times, Iran International, Ukrinform, and Google News
  searches for site:reuters.com and site:apnews.com (stand-ins for Reuters and AP, which have no feeds), strikes on
  Russia and strikes on Iran;
* every 30 min: The Diplomat, InSight Crime, Haitian Times, the Department of War (defense.gov now redirects to
  war.gov, so the war.gov address is polled), UN Security Council press, Meduza, IranWire, the two heavy feeds,
  Infobae (es, ~0.8 MB) and The War Zone (~0.85 MB, full article text), and Google News searches for drones over
  Russia, blasts and sabotage in Russia, blasts and air defence in Iran, and drone / missile interceptions anywhere
  (1.1, asked for: "attacks on russia and attacks on iran ... drone attacks, missile attacks ... interceptions");
  every 15 min as well: ballistic missile launches and air-raid sirens anywhere (1.1);
* 1.1, asked for: "find as much info on iran activity as you can ... and middle east as a whole": Tasnim
  (IRGC-affiliated) and Mehr (state media) in English, HRANA, Amwaj, the Jerusalem Post's Middle East desk,
  Al-Monitor, Asharq Al-Awsat, The National, LBCI (Lebanon), Shafaq News (Iraq), Al Masirah (Houthi media),
  Kurdistan24, Enab Baladi and North Press (Syria), and Google News searches for the IRGC Navy / Hormuz, Houthi
  attacks, Red Sea / Hormuz shipping, Iraqi militias, the IAEA and Iran, and Hezbollah; and (asked for: "search for drone
  launches as well globally") drone launches and attacks anywhere, every 15 min. State and partisan outlets
  say so in their label. Google News ignores when:1d in a query longer than about 200 characters (tested
  2026-11-21: 214-265 character queries returned items up to 4.7 years old, 0-7 of them from the last day), so
  every query is kept under 195 characters (tests/test_wire.py checks it).
* hourly: Crisis Group (slow server; often nothing inside 48 h), and twelve topical Google News searches (Haiti
  gang, Sudan RSF, Sahel jihadist, Myanmar junta, DRC M23, Kashmir security, Taiwan PLA, Venezuela military, Ecuador
  violence, Colombia ELN, North Korea missile, Somalia al-Shabaab) plus "cártel" in Mexican Spanish. ("cartel"
  without the accent is mostly Spanish festival posters; bare "Kashmir" is ~100 items a day of local civic news.)
At most GNEWS_PER_CALL (5 since 1.1) Google searches per call, 4 s apart, one after the other; a 429/503 from Google pauses all of them for an
hour. The other sources are fetched 6 at a time. Conditional GET (ETag / If-Modified-Since) wherever the source
sends a validator; a 304 costs nothing. A 403/429 leaves that source alone for an hour.

Parsing takes RSS 2.0, RDF 1.0 (DW) and Atom, gzip with or without a Content-Encoding header, HTML entities and
tags in titles and descriptions. Google News titles are "Headline - Publisher": the publisher goes to source_label
and the news.google.com link is kept as it is (redirects are not resolved). Items keep 48 h; the same URL from two
feeds is one item; titles whose word sets overlap by Jaccard >= 0.8 within 24 h are one story (the earliest is
kept, the other sources are listed in also_in). Each item is placed by gt/placer.py from its title and summary;
single-topic sources (Kyiv Independent, Haitian Times, the topical searches) fill in their country, regional desks
their theatre, when the text names none ("placed": "text" / "source" / null).

Returns the newest 600 stories (under 400 KB), counts per theatre and per primary country over the whole 48 h, and
one row per source (ok, error, newest, n). Terms: headlines and links from many publishers, the BBC's feeds are
for personal non-commercial use, Google News results are a grey area. So PUBLIC_OK is False (never for the public
mirror) and NON_COMMERCIAL is True (never for the trading agent).
"""
import calendar
import concurrent.futures
import datetime as dt
import email.utils
import gzip
import hashlib
import html
import html.entities
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib

from . import geo, mymaps, placer

VERSION = "1.1"
LICENCE = ("Headlines and links only, each the property of its publisher; BBC feeds are for personal non-commercial "
           "use; Google News results under Google's terms. Non-commercial, never for the trading agent, not for the "
           "public mirror.")
ATTRIBUTION = ("Headlines link to their publishers: Al Jazeera, BBC News, France 24, DW, Kyiv Independent, Times of "
               "Israel, Middle East Eye, The Diplomat, SCMP, Africanews, allAfrica, The Guardian, Infobae, InSight "
               "Crime, The Haitian Times, The War Zone, Military Times, US Department of War, United Nations, "
               "International Crisis Group, The Moscow Times, Meduza, Iran International, IranWire, Ukrinform, "
               "Tasnim, Mehr News, HRANA, Amwaj.media, The Jerusalem Post, Al-Monitor, Asharq Al-Awsat, The National, "
               "LBCI, Shafaq News, Al Masirah, Kurdistan24, Enab Baladi, North Press Agency; "
               "Reuters, AP and others via Google News.")
NON_COMMERCIAL = True
PUBLIC_OK = False

UA = "Mozilla/5.0 (compatible; GroundTruth/0.12; personal OSINT dashboard)"
TIMEOUT = 20
FAST, MID, SLOW, HOURLY = 300, 900, 1800, 3600
SLACK = 20                 # s: a source due within this of now counts as due (the scheduler drifts a little)
WINDOW = 48 * 3600         # items kept
DEDUPE_WINDOW = 24 * 3600  # title duplicates only within this
JACCARD = 0.8
MAX_ITEMS = 600            # stories returned
MAX_STORE = 6000           # items kept in the state file
MAX_BYTES = 400000         # returned JSON
MAX_BODY = 8 * 1024 * 1024
SUMMARY_MAX = 200
WORKERS = 6
GNEWS_PER_CALL = 5        # 1.1: 30 searches are ~58 requests an hour; 5 per 5-min call allows 60
GNEWS_GAP = 4.0
BACKOFF = 3600             # after 403 / 429 (and 503 from Google)
FUTURE_SLACK = 3600        # a pubDate more than 1 h ahead is replaced by the time first seen
STATE = "wire_state.json"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")  # the same folder as feeds.CACHE

_GN = "https://news.google.com/rss/search?q=%s&hl=en-US&gl=US&ceid=US:en"
_GN_MX = "https://news.google.com/rss/search?q=%s&hl=es-419&gl=MX&ceid=MX:es-419"


def _gq(q, base=_GN):
    return base % urllib.parse.quote_plus(q, safe=":")


# (slug, label, url, every_s, lang, hint). hint fills in a3 or "@theatre" when the text names no place.
SOURCES = (
    ("aljazeera", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", FAST, "en", None),
    ("bbc", "BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", FAST, "en", None),
    ("bbcafrica", "BBC News Africa", "https://feeds.bbci.co.uk/news/world/africa/rss.xml", MID, "en", "@africa"),
    ("bbcasia", "BBC News Asia", "https://feeds.bbci.co.uk/news/world/asia/rss.xml", MID, "en", None),
    ("bbclatam", "BBC News Latin America", "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml", MID, "en",
     "@americas"),
    ("bbcmideast", "BBC News Middle East", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", MID, "en",
     "@middle-east"),
    ("france24", "France 24", "https://www.france24.com/en/rss", FAST, "en", None),
    ("dw", "DW", "https://rss.dw.com/rdf/rss-en-world", FAST, "en", None),
    ("kyivindependent", "Kyiv Independent", "https://kyivindependent.com/news-archive/rss/", FAST, "en", "UKR"),
    ("timesofisrael", "Times of Israel", "https://www.timesofisrael.com/feed/", FAST, "en", "ISR"),
    ("mee", "Middle East Eye", "https://www.middleeasteye.net/rss", MID, "en", "@middle-east"),
    ("diplomat", "The Diplomat", "https://thediplomat.com/feed/", SLOW, "en", "@indo-pacific"),
    ("scmp", "South China Morning Post", "https://www.scmp.com/rss/91/feed/", MID, "en", "@indo-pacific"),
    ("africanews", "Africanews", "https://www.africanews.com/feed/rss", MID, "en", "@africa"),
    ("allafrica", "allAfrica", "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf", MID, "en", "@africa"),
    ("guardianamericas", "The Guardian (Americas)", "https://www.theguardian.com/world/americas/rss", MID, "en",
     "@americas"),
    ("infobae", "Infobae América", "https://www.infobae.com/arc/outboundfeeds/rss/category/america/", SLOW, "es",
     "@americas"),
    ("insightcrime", "InSight Crime", "https://insightcrime.org/feed/", SLOW, "en", "@americas"),
    ("haitiantimes", "The Haitian Times", "https://haitiantimes.com/feed/", SLOW, "en", "HTI"),
    ("twz", "The War Zone", "https://www.twz.com/feed", SLOW, "en", None),
    ("militarytimes", "Military Times", "https://www.militarytimes.com/feed/", MID, "en", None),
    ("dod", "US Department of War",
     "https://www.war.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10", SLOW, "en", None),
    ("unsc", "UN Security Council press", "https://press.un.org/en/rss.xml", SLOW, "en", None),
    ("unnews", "UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml", MID, "en", None),
    ("crisisgroup", "Crisis Group", "https://www.crisisgroup.org/rss.xml", HOURLY, "en", None),
    # 1.1: Russia, Iran and Ukraine desks (each answered a test fetch on 2026-11-20)
    ("moscowtimes", "The Moscow Times", "https://www.themoscowtimes.com/rss/news", MID, "en", "RUS"),
    ("meduza", "Meduza", "https://meduza.io/rss/en/all", SLOW, "en", "RUS"),
    ("iranintl", "Iran International", "https://www.iranintl.com/en/feed", MID, "en", "IRN"),
    ("iranwire", "IranWire", "https://iranwire.com/en/feed/", SLOW, "en", "IRN"),
    ("ukrinform", "Ukrinform", "https://www.ukrinform.net/rss/block-lastnews", MID, "en", "UKR"),
    # 1.1: Iran and the wider Middle East (each answered a test fetch on 2026-11-21 with items from the last 48 h).
    # State and partisan outlets say so in their label, which the page shows on every item.
    ("tasnim", "Tasnim (Iran, IRGC-affiliated)", "https://www.tasnimnews.ir/en/rss/feed/0/0/8/1/TopStories", MID, "en",
     "IRN"),
    ("mehr", "Mehr News (Iran, state media)", "https://en.mehrnews.com/rss", MID, "en", "IRN"),
    ("hrana", "HRANA (Iran rights NGO)", "https://www.en-hrana.org/feed/", SLOW, "en", "IRN"),
    ("amwaj", "Amwaj.media", "https://amwaj.media/feed/en/rss2.xml", HOURLY, "en", "@middle-east"),  # ~0.9 MB, full text
    ("jpost-me", "Jerusalem Post (Middle East)", "https://www.jpost.com/rss/rssfeedsmiddleeastnews.aspx", MID, "en",
     "@middle-east"),
    ("almonitor", "Al-Monitor", "https://www.al-monitor.com/rss", MID, "en", "@middle-east"),
    ("aawsat", "Asharq Al-Awsat (Saudi-owned)", "https://english.aawsat.com/feed", MID, "en", "@middle-east"),
    ("thenational", "The National (UAE)",
     "https://www.thenationalnews.com/arc/outboundfeeds/rss/category/news/mena/?outputType=xml", MID, "en",
     "@middle-east"),
    ("lbci", "LBCI (Lebanon)", "https://www.lbcgroup.tv/Rss/News/en", MID, "en", "LBN"),
    ("shafaq", "Shafaq News (Iraq)", "https://shafaq.com/rss/en", MID, "en", "IRQ"),
    ("masirah", "Al Masirah (Houthi media)", "https://english.masirahtv.net/rss.xml", MID, "en", "YEM"),
    ("kurdistan24", "Kurdistan24 (KDP-affiliated)", "https://www.kurdistan24.net/en/rss.xml", SLOW, "en", "IRQ"),
    ("enabbaladi", "Enab Baladi (Syria)", "https://english.enabbaladi.net/feed/", SLOW, "en", "SYR"),
    ("npa", "North Press Agency (NE Syria)", "https://npasyria.com/en/feed/", SLOW, "en", "SYR"),
    ("gn-reuters", "Reuters (Google News)", _gq("site:reuters.com when:1d"), MID, "en", None),
    ("gn-ap", "AP (Google News)", _gq("site:apnews.com when:1d"), MID, "en", None),
    ("gn-haiti", "Google News: Haiti gangs", _gq("Haiti gang when:1d"), HOURLY, "en", "HTI"),
    ("gn-sudan", "Google News: Sudan RSF", _gq("Sudan RSF when:1d"), HOURLY, "en", "SDN"),
    ("gn-sahel", "Google News: Sahel", _gq("Sahel jihadist when:1d"), HOURLY, "en", "@africa"),
    ("gn-myanmar", "Google News: Myanmar", _gq("Myanmar junta when:1d"), HOURLY, "en", "MMR"),
    ("gn-drc", "Google News: DRC M23", _gq("DRC M23 when:1d"), HOURLY, "en", "COD"),
    ("gn-kashmir", "Google News: Kashmir security",
     _gq("Kashmir (militants OR terrorists OR encounter OR LoC OR army) when:1d"), HOURLY, "en", "IND"),
    ("gn-taiwan", "Google News: Taiwan PLA", _gq("Taiwan PLA when:1d"), HOURLY, "en", "TWN"),
    ("gn-venezuela", "Google News: Venezuela", _gq("Venezuela military when:1d"), HOURLY, "en", "VEN"),
    ("gn-ecuador", "Google News: Ecuador", _gq("Ecuador violence when:1d"), HOURLY, "en", "ECU"),
    ("gn-colombia", "Google News: Colombia ELN", _gq("Colombia ELN when:1d"), HOURLY, "en", "COL"),
    ("gn-northkorea", "Google News: North Korea", _gq("North Korea missile when:1d"), HOURLY, "en", "PRK"),
    ("gn-somalia", "Google News: Somalia", _gq("Somalia al-Shabaab when:1d"), HOURLY, "en", "SOM"),
    ("gn-mexico", "Google News: cárteles (MX)", _gq("cártel when:1d", _GN_MX), HOURLY, "es", "MEX"),
    # 1.1: attacks on Russia and Iran, drone and missile attacks, interceptions. Sampled on 2026-11-20: "strikes on
    # Russia" 98 items, all Ukrainian strikes inside Russia (a looser query drew in Russia's strikes on Ukraine);
    # drones over Russia 100, blasts in Russia 33, strikes on Iran / blasts in Iran 100, interceptions 57.
    ("gn-ru-strikes", "Google News: strikes on Russia",
     _gq('(Ukrainian OR Ukraine) (drone OR drones OR missile) (refinery OR "oil depot" OR airfield OR Belgorod OR '
         'Kursk OR Bryansk OR Rostov OR Krasnodar OR Novorossiysk) when:1d'), MID, "en", "RUS"),
    ("gn-ru-drones", "Google News: drones over Russia",
     _gq('("drone attack" OR "drones shot down" OR "intercepted drones" OR "UAV attack") Russian (region OR governor '
         'OR "defence ministry") -Kyiv -Kharkiv when:1d'), SLOW, "en", "RUS"),
    ("gn-ru-blasts", "Google News: blasts and sabotage in Russia",
     _gq('(explosion OR blast OR fire OR sabotage OR derailment) Russia (plant OR factory OR depot OR railway OR '
         'refinery OR "military unit" OR arsenal) when:1d'), SLOW, "en", "RUS"),
    ("gn-ir-strikes", "Google News: strikes on Iran",
     _gq('("strike on Iran" OR "strikes on Iran" OR "attack on Iran" OR "attacks on Iran" OR "explosion in Iran" '
         'OR "blast in Iran" OR "strikes Iran" OR "hit Iran") when:1d'), MID, "en", "IRN"),
    ("gn-ir-attacks", "Google News: blasts and air defence in Iran",
     _gq('Iran (explosion OR blast OR airstrike OR sabotage OR "air defense") (Tehran OR Isfahan OR Natanz OR Fordow '
         'OR "Bandar Abbas" OR IRGC) when:1d'), SLOW, "en", "IRN"),
    ("gn-intercepts", "Google News: interceptions",
     _gq('(intercepted OR "shot down" OR interception) (drones OR missiles OR "ballistic missile") ("air defense" OR '
         '"air defence" OR military) when:1d'), SLOW, "en", None),
    # 1.1, asked for: "search for drone launches as well globally" (sampled 2026-11-21: 66 items, all from the last
    # 24 h; Ukraine-Russia, the Middle East, Gaza, the Americas and Africa)
    ("gn-drones", "Google News: drone launches and attacks worldwide",
     _gq('("drone attack" OR "drone strike" OR "drones launched" OR "launched drones" OR "kamikaze drone" OR Shahed OR '
         '"loitering munition" OR "FPV drone") when:1d'), MID, "en", None),
    # asked for: "add ballistic missile launches to feed and intercepts and air raid sirens globally" (sampled
    # 2026-11-21: 39 items, Houthi launches at Saudi Arabia, Russian ballistic strikes, a North Korean SLBM test; and
    # 23 items, sirens and air-raid alerts in Poland and Ukraine). Sirens with their own feed (Ukraine, Russia and
    # Poland from alerts.in.ua, Israel from Tzeva Adom) stay on those feeds too.
    ("gn-ballistic", "Google News: ballistic missile launches",
     _gq('("ballistic missile" OR "ballistic missiles" OR ICBM OR "hypersonic missile" OR "missile test" OR '
         '"missile launch") (launched OR launches OR fired OR fires OR test OR tested) when:1d'), MID, "en", None),
    ("gn-sirens", "Google News: air raid sirens",
     _gq('("air raid sirens" OR "air raid siren" OR "air raid alert" OR "air-raid alert" OR "sirens sounded" OR '
         '"sirens sounding" OR "sirens blared" OR "missile alert" OR "rocket sirens") when:1d'), MID, "en", None),
    # 1.1: the Middle East as a whole (sampled 2026-11-21, every item from the last 24 h: 27, 100, 32, 42, 19, 15)
    ("gn-ir-navy", "Google News: IRGC Navy and Hormuz",
     _gq('(IRGC OR "Revolutionary Guard" OR "Revolutionary Guards") (navy OR naval OR tanker OR seize OR seized OR '
         'seizure OR vessel OR Hormuz OR drill OR drills) when:1d'), SLOW, "en", "IRN"),
    ("gn-houthi", "Google News: Houthi attacks",
     _gq('(Houthi OR Houthis OR "Ansar Allah") (missile OR missiles OR drone OR drones OR attack OR attacks OR ship OR '
         'vessel OR "Red Sea" OR strike OR strikes) when:1d'), SLOW, "en", "YEM"),
    ("gn-shipping", "Google News: Red Sea and Hormuz shipping",
     _gq('("Red Sea" OR "Gulf of Aden" OR "Bab el-Mandeb" OR "Strait of Hormuz" OR "Gulf of Oman") (ship OR vessel OR '
         'tanker OR UKMTO OR attacked OR incident OR seized) when:1d'), SLOW, "en", "@middle-east"),
    ("gn-iraq-militia", "Google News: Iraqi militias",
     _gq('("Kataib Hezbollah" OR "Islamic Resistance in Iraq" OR "Iraqi militia" OR "Iraqi militias" OR '
         '"Popular Mobilization" OR "Nujaba") when:1d'), HOURLY, "en", "IRQ"),
    ("gn-iaea-iran", "Google News: IAEA and Iran",
     _gq('(IAEA OR Grossi) Iran (nuclear OR enrichment OR inspectors OR inspections OR uranium) when:1d'), HOURLY, "en",
     "IRN"),
    ("gn-hezbollah", "Google News: Hezbollah",
     _gq('Hezbollah (strike OR strikes OR rocket OR rockets OR drone OR attack OR killed OR "south Lebanon" OR '
         '"southern Lebanon") when:1d'), HOURLY, "en", "LBN"),
)
_BY_SLUG = {s[0]: s for s in SOURCES}
_LOCK = threading.Lock()
_sleep = time.sleep   # tests replace it


def _is_gnews(slug):
    return slug.startswith("gn-")


# ---------------- HTTP ----------------

def _fetch(url, headers=None, timeout=TIMEOUT):
    """GET -> (status, headers dict, body). A 304 comes back as (304, headers, b""); other HTTP errors raise."""
    h = {"User-Agent": UA, "Accept-Encoding": "gzip",
         "Accept": "application/rss+xml, application/rdf+xml, application/atom+xml, application/xml, text/xml, */*"}
    h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            body = r.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ValueError("response over %d bytes" % MAX_BODY)
            hd = dict(r.headers.items())
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
            return getattr(r, "status", 200), hd, body
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, dict((e.headers or {}).items()), b""
        raise


def _ungzip(body):
    """Bodies that are gzip without saying so (or deflate) are unpacked by their magic bytes."""
    if body[:2] == b"\x1f\x8b":
        return gzip.decompress(body)
    if body[:1] == b"\x78" and body[1:2] in (b"\x01", b"\x5e", b"\x9c", b"\xda"):
        try:
            return zlib.decompress(body)
        except zlib.error:
            return body
    return body


def _hget(h, name):
    for k, v in (h or {}).items():
        if k.lower() == name.lower():
            return v
    return None


# ---------------- parsing ----------------

_XML_ENTS = {"amp", "lt", "gt", "quot", "apos"}
_BAD_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_TAG = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")
_WP_TAIL = re.compile(r"\s*(?:The post .{1,300}? appeared first on .{1,120}?\.?|Continue reading\.*|Read more\.*|"
                      r"\[(?:…|\.\.\.)\])\s*$", re.I | re.S)
_TRACKING = re.compile(r"^(?:utm_\w+|maca|at_\w+|ns_\w+|cmpid|ito|ocid|CMP|fbclid|gclid|traffic_source)$")
_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*"
                  r"(Z|[+-]\d{2}:?\d{2})?\s*$", re.I)


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _fix_entities(text):
    """HTML named entities that XML does not know (&nbsp; &mdash;) -> numeric references."""
    def sub(m):
        name = m.group(1)
        if name in _XML_ENTS:
            return m.group(0)
        ch = html.entities.html5.get(name + ";")
        return "".join("&#%d;" % ord(c) for c in ch) if ch else "&amp;" + name + ";"
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", sub, text)


def _parse_xml(body):
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
        text = _BAD_CTRL.sub("", _fix_entities(text))
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
        text = re.sub(r"&(?![A-Za-z][A-Za-z0-9]*;|#\d+;|#x[0-9A-Fa-f]+;)", "&amp;", text)
        return ET.fromstring(text)


def clean(s):
    """Plain text: entities decoded (twice, for double-escaped feeds), tags gone, whitespace collapsed."""
    s = html.unescape(html.unescape(s or ""))
    s = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", s)
    s = _TAG.sub(" ", re.sub(r"(?i)<br\s*/?>|</p>", " ", s))
    return _WS.sub(" ", s).strip()


def cut(s, n):
    """Over n chars: cut on a word boundary and end with an ellipsis (total <= n)."""
    s = _WS.sub(" ", s or "").strip()
    if len(s) <= n:
        return s or None
    c = s[:n - 1]
    if s[n - 1] != " " and " " in c:
        c = c[:c.rindex(" ")]
    return c.rstrip(" ,;:.-–—") + "…"


def parse_time(s):
    """RFC 822 (RSS) or ISO 8601 (RDF dc:date, Atom) -> epoch seconds, or None."""
    s = (s or "").strip()
    if not s:
        return None
    m = _ISO.match(s)
    if m:
        y, mo, d, hh, mi, ss, tz = m.groups()
        t = calendar.timegm((int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0)))
        if tz and tz.upper() != "Z":
            sign = 1 if tz[0] == "+" else -1
            tz = tz[1:].replace(":", "")
            t -= sign * (int(tz[:2]) * 3600 + int(tz[2:4]) * 60)
        return t
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def canonical_url(u):
    """Tracking parameters and fragments off (DW adds ?maca=..., others utm_*). Google News links stay as they are."""
    u = (u or "").strip()
    if not u or "news.google.com" in u:
        return u
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        return u
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))


def _text(el):
    if el is None:
        return ""
    return "".join(el.itertext())


def _entry(el):
    """One <item>/<entry> -> {title, url, t, summary, publisher} (raw text, not yet cleaned)."""
    f = {}
    for c in el:
        n = _local(c.tag)
        if n == "link":
            href = c.get("href")
            if href and (c.get("rel") in (None, "alternate")) and "link" not in f:
                f["link"] = href
            elif not href and (c.text or "").strip() and "link" not in f:
                f["link"] = c.text.strip()
        elif n == "source":
            f.setdefault("publisher", _text(c))
        elif n in ("title", "guid", "pubDate", "date", "published", "updated", "description", "summary",
                   "encoded", "content"):
            f.setdefault(n, _text(c))
    link = f.get("link") or (f.get("guid") if (f.get("guid") or "").startswith("http") else None) or \
        el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about")
    when = f.get("pubDate") or f.get("date") or f.get("published") or f.get("updated")
    summ = f.get("description") or f.get("summary") or f.get("encoded") or f.get("content") or ""
    return {"title": f.get("title") or "", "url": link or "", "t": parse_time(when), "summary": summ,
            "publisher": f.get("publisher")}


def parse_feed(body):
    """RSS 2.0, RDF 1.0 or Atom bytes -> raw entries. A broken entry is skipped; a document that is no feed raises."""
    root = _parse_xml(_ungzip(body))
    kind = _local(root.tag)
    if kind not in ("rss", "RDF", "feed", "channel"):
        raise ValueError("not a feed: <%s>" % kind)
    out = []
    for el in root.iter():
        if _local(el.tag) in ("item", "entry"):
            try:
                e = _entry(el)
            except Exception:
                continue
            if e["title"].strip() and e["url"]:
                out.append(e)
    return out


# ---------------- items ----------------

def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)) if t is not None else None


def _gn_title(title, publisher):
    """Google News "Headline - Publisher" -> (headline, publisher)."""
    if publisher and title.endswith(" - " + publisher):
        return title[:-len(publisher) - 3].strip(), publisher
    m = re.match(r"^(.*\S)\s+[-–—|]\s+([^-–—|]{2,60})$", title)
    if m and not publisher:
        return m.group(1), m.group(2).strip()
    return title, publisher


def _apply_hint(countries, theatre, hint):
    if countries or not hint:
        return countries, theatre, ("text" if countries else ("text" if theatre else None))
    if hint.startswith("@"):
        return [], theatre or hint[1:], ("text" if theatre else "source")
    return [hint], geo.theatre_for_a3(hint), "source"


def make_item(src, raw, now, kind="wire"):
    """A raw feed entry -> a wire item (None when it has no title/link or is older than 48 h)."""
    slug, label, _url, _every, lang, hint = src
    title, publisher = clean(raw.get("title")), None
    if _is_gnews(slug):  # only Google's <source> names the publisher; UN News puts its own tagline there
        title, publisher = _gn_title(title, clean(raw.get("publisher")) or None)
    url = canonical_url(raw.get("url"))
    if not title or not url:
        return None
    t = raw.get("t")
    if t is None or t > now + FUTURE_SLACK:
        t = int(now)
    if now - t > WINDOW:
        return None
    summary = None
    if not _is_gnews(slug):
        s = _WP_TAIL.sub("", clean(raw.get("summary")))
        if s and s.lower() != title.lower():
            summary = cut(s, SUMMARY_MAX)
    pl = placer.place(title, summary)
    countries, theatre, placed = _apply_hint(pl["countries"], pl["theatre"], hint)
    cat, tags = mymaps.classify(title, None)
    it = {"id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:16], "title": cut(title, 300), "url": url,
          "source": slug, "source_label": publisher or label, "ts_ms": int(t) * 1000, "ts": _iso(int(t)),
          "lang": lang, "countries": countries, "theatre": theatre, "placed": placed, "category": cat, "tags": tags,
          "summary": summary, "also_in": [], "kind": kind}
    if _is_gnews(slug):
        it["via"] = "Google News"
    return it


# ---------------- de-duplication by title ----------------

_STOP = set("a an the of in on at to for and or but as by with from into onto over after before is are was were be "
            "been has have had it its this that these those says say said will would could can may might not no new "
            "amid against about than then up down out off more most de la el los las en y del que por para un una "
            "con se al lo".split())


def title_tokens(title):
    return frozenset(w for w in re.findall(r"[^\W_]+", placer._fold(title or "").lower())
                     if len(w) > 1 and w not in _STOP)


def jaccard(a, b):
    return len(a & b) / float(len(a | b)) if (a or b) else 0.0


def cluster(items, threshold=JACCARD, window=DEDUPE_WINDOW):
    """Stories: items (oldest first) whose title word sets overlap >= threshold within `window` of the story's
    first item. Prefix filtering keeps it near linear. Returns lists of items, each list oldest first."""
    items = sorted(items, key=lambda x: (x["ts_ms"], x["id"]))
    toks = [title_tokens(x["title"]) for x in items]
    df = {}
    for T in toks:
        for w in T:
            df[w] = df.get(w, 0) + 1
    index, clusters = {}, []  # token -> [cluster ids]; cluster = [rep_tokens, rep_ts_ms, [items]]
    for x, T in zip(items, toks):
        best, best_j = None, 0.0
        if len(T) >= 3:
            order = sorted(T, key=lambda w: (df[w], w))
            p = len(T) - int(math.ceil(threshold * len(T))) + 1
            seen = set()
            for w in order[:p]:
                for ci in index.get(w, ()):
                    if ci in seen:
                        continue
                    seen.add(ci)
                    U, t0, _ = clusters[ci]
                    if x["ts_ms"] - t0 > window * 1000:
                        continue
                    if min(len(T), len(U)) < threshold * max(len(T), len(U)):
                        continue
                    j = jaccard(T, U)
                    if j >= threshold and j > best_j:
                        best, best_j = ci, j
        else:
            for ci in index.get(("exact", T), ()):
                if x["ts_ms"] - clusters[ci][1] <= window * 1000:
                    best = ci
                    break
        if best is not None:
            clusters[best][2].append(x)
            continue
        ci = len(clusters)
        clusters.append([T, x["ts_ms"], [x]])
        if len(T) >= 3:
            order = sorted(T, key=lambda w: (df[w], w))
            for w in order[:len(T) - int(math.ceil(threshold * len(T))) + 1]:
                index.setdefault(w, []).append(ci)
        else:
            index.setdefault(("exact", T), []).append(ci)
    return [c[2] for c in clusters]


def _story(group):
    rep = dict(group[0])
    others = []
    for x in group:
        for s in [x["source"]] + list(x.get("seen") or []):
            if s != rep["source"] and s not in others:
                others.append(s)
    rep["also_in"] = others
    if not rep.get("countries"):
        donor = next((x for x in group[1:] if x.get("countries") and x.get("placed") == "text"), None) or \
            next((x for x in group[1:] if x.get("countries")), None)
        if donor:
            rep["countries"], rep["theatre"], rep["placed"] = donor["countries"], donor["theatre"], donor["placed"]
    rep.pop("seen", None)
    return rep


def build(items, now, max_items=MAX_ITEMS, max_bytes=MAX_BYTES):
    """Stored items -> (stories newest first capped, by_theatre, by_country, by_country_24h, total)."""
    live = [x for x in items if now * 1000 - x["ts_ms"] <= WINDOW * 1000]
    stories = [_story(g) for g in cluster(live)]
    stories.sort(key=lambda x: (-x["ts_ms"], x["id"]))
    by_theatre, by_country, by_country_24h = {}, {}, {}
    for x in stories:
        th = x.get("theatre") or "unplaced"
        by_theatre[th] = by_theatre.get(th, 0) + 1
        if x.get("countries"):
            c = x["countries"][0]
            by_country[c] = by_country.get(c, 0) + 1
            if now * 1000 - x["ts_ms"] <= 86400 * 1000:
                by_country_24h[c] = by_country_24h.get(c, 0) + 1
    return stories[:max_items], by_theatre, by_country, by_country_24h, len(stories)


def fit(out, max_bytes=MAX_BYTES):
    """Trim the oldest items until the JSON is under max_bytes."""
    items = out["items"]
    size = len(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    while items and size >= max_bytes:
        drop = max(1, len(items) // 20)
        del items[-drop:]
        size = len(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    out["count"] = len(items)
    return out


# ---------------- state ----------------

def _state_path(name=STATE):
    return os.path.join(CACHE, name)


def load_state(name=STATE):
    try:
        with open(_state_path(name), encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d, dict) and isinstance(d.get("sources"), dict) and isinstance(d.get("items"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"v": 1, "sources": {}, "items": {}}


def save_state(st, name=STATE):
    os.makedirs(CACHE, exist_ok=True)
    p = _state_path(name)
    tmp = "%s.%d.tmp" % (p, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)


def _phase(slug):
    """A stable fraction in [0, 1) per source: spreads first-round due times so 15-min sources don't bunch."""
    return int(hashlib.sha1(slug.encode()).hexdigest()[:6], 16) / float(0x1000000)


def _now_epoch(now):
    if now is None:
        return time.time()
    if isinstance(now, dt.datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.timezone.utc)
        return now.timestamp()
    return float(now)


def _err(e):
    if isinstance(e, urllib.error.HTTPError):
        return "HTTP %d" % e.code
    return "%s: %s" % (type(e).__name__, str(e)[:120])


# ---------------- polling ----------------

def _get_source(src, s, fetch):
    """Fetch and parse one source. Returns ("304", None, None) or ("200", headers, entries)."""
    hdr = {}
    if s.get("etag"):
        hdr["If-None-Match"] = s["etag"]
    if s.get("lm"):
        hdr["If-Modified-Since"] = s["lm"]
    status, rh, body = fetch(src[2], hdr)
    if status == 304:
        return 304, rh, None
    if status and status >= 400:
        raise urllib.error.HTTPError(src[2], status, "HTTP %d" % status, None, None)
    return 200, rh, parse_feed(body or b"")


def _record(st, src, now, result=None, error=None):
    slug = src[0]
    s = st["sources"].setdefault(slug, {})
    s["checked"] = int(now)
    first = "fetched" not in s
    every = src[3]
    s["next_due"] = int(now + (every * (0.5 + 0.5 * _phase(slug)) if first else every))
    s["fetched"] = s.get("fetched", 0) + 1
    if error is not None:
        s.update(ok=False, error=_err(error), status=getattr(error, "code", None))
        if isinstance(error, urllib.error.HTTPError) and error.code in (403, 429) or \
                (_is_gnews(slug) and isinstance(error, urllib.error.HTTPError) and error.code == 503):
            s["backoff_until"] = int(now + BACKOFF)
        return 0
    status, rh, entries = result
    s.update(ok=True, error=None, status=status, backoff_until=None)
    if status == 304:
        return 0
    s["etag"] = _hget(rh, "ETag")
    s["lm"] = _hget(rh, "Last-Modified")
    new = 0
    newest = s.get("newest_t")
    for raw in entries:
        try:
            it = make_item(src, raw, now)
        except Exception:  # noqa: BLE001  one odd entry never fails its source
            it = None
        if it is None:
            continue
        newest = max(newest or 0, it["ts_ms"] // 1000)
        old = st["items"].get(it["id"])
        if old is None:
            st["items"][it["id"]] = it
            new += 1
        elif old["source"] != slug and slug not in (old.get("seen") or []):
            old.setdefault("seen", []).append(slug)
    s["newest_t"] = newest
    s["last_n"] = len(entries)
    return new


def _due(st, now, sources):
    due = []
    for src in sources:
        s = st["sources"].get(src[0]) or {}
        nd = max(s.get("next_due") or 0, s.get("backoff_until") or 0)
        if nd <= now + SLACK:
            due.append((nd, src))
    due.sort(key=lambda x: (x[0], x[1][0]))
    return [src for _, src in due]


def poll(now=None, fetch=None):
    """Feed `wire` (every 300 s): fetch the sources that are due, return the 48 h story list."""
    now = _now_epoch(now)
    fetch = fetch or _fetch
    with _LOCK:
        st = load_state()
        due = _due(st, now, SOURCES)
        plain = [s for s in due if not _is_gnews(s[0])]
        google = [s for s in due if _is_gnews(s[0])][:GNEWS_PER_CALL]
        results = {}

        def one(src):
            try:
                return src, _get_source(src, st["sources"].get(src[0]) or {}, fetch), None
            except Exception as e:  # noqa: BLE001  one bad source never fails the feed
                return src, None, e

        def google_chain():
            out = []
            for k, src in enumerate(google):
                if k:
                    _sleep(GNEWS_GAP)
                r = one(src)
                out.append(r)
                e = r[2]
                if isinstance(e, urllib.error.HTTPError) and e.code in (429, 503):
                    break  # Google asked us to slow down: the rest wait for the next call
            return out

        if plain or google:
            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
                gfut = ex.submit(google_chain) if google else None
                for src, res, e in ex.map(one, plain):
                    results[src[0]] = (src, res, e)
                if gfut:
                    for src, res, e in gfut.result():
                        results[src[0]] = (src, res, e)
        for slug in sorted(results):
            src, res, e = results[slug]
            _record(st, src, now, res, e)
            if _is_gnews(slug) and isinstance(e, urllib.error.HTTPError) and e.code in (429, 503):
                for other in SOURCES:  # pause every Google search, not just this one
                    if _is_gnews(other[0]):
                        o = st["sources"].setdefault(other[0], {})
                        o["backoff_until"] = max(o.get("backoff_until") or 0, int(now + BACKOFF))
        # retention: 48 h, newest MAX_STORE
        keep = [x for x in st["items"].values() if now * 1000 - x["ts_ms"] <= WINDOW * 1000]
        keep.sort(key=lambda x: -x["ts_ms"])
        st["items"] = {x["id"]: x for x in keep[:MAX_STORE]}
        if results:
            save_state(st)
        tried = [s for s in SOURCES if (st["sources"].get(s[0]) or {}).get("checked")]
        bad = [s for s in tried if st["sources"][s[0]].get("ok") is False]
        if len(tried) >= 3 and len(bad) == len(tried):
            errs = sorted({st["sources"][s[0]].get("error") or "?" for s in bad})
            raise RuntimeError("all wire sources failing: %d (%s)" % (len(bad), "; ".join(errs)[:200]))
        return _output(st, now, len(results))


def _output(st, now, fetched):
    items = list(st["items"].values())
    stories, by_theatre, by_country, by_country_24h, total = build(items, now)
    per = {}
    for x in items:
        for s in [x["source"]] + list(x.get("seen") or []):
            per[s] = per.get(s, 0) + 1
    rows = []
    for src in SOURCES:
        s = st["sources"].get(src[0]) or {}
        rows.append({"name": src[0], "label": src[1], "ok": s.get("ok"), "error": s.get("error"),
                     "newest": _iso(s.get("newest_t")), "n": per.get(src[0], 0), "status": s.get("status"),
                     "checked": _iso(s.get("checked")), "next": _iso(max(s.get("next_due") or 0,
                                                                         s.get("backoff_until") or 0) or None)})
    out = {"version": VERSION, "fetched_at": _iso(int(now)), "count": len(stories), "total": total,
           "fetched": fetched, "sources": rows, "attribution": ATTRIBUTION, "licence": LICENCE,
           "items": stories, "by_theatre": by_theatre, "by_country": by_country, "by_country_24h": by_country_24h}
    return fit(out)


def summary(data, per_theatre=3, hours=12):
    """Compact view for the analyst (< 2 KB): story counts per theatre and, per theatre, the most telling placed
    headlines of the last `hours` (before the newest story): a conflict category first, then the number of outlets
    carrying the story, then the newest. Most wire items are "other" (sport, business), so newest-first alone
    would hand the analyst football results. Goes to /api/digest only (private), never to /api/summary."""
    try:
        d = data or {}
        out = {"by_theatre": d.get("by_theatre") or {}, "licence": "non-commercial", "latest": {}}
        items = [x for x in d.get("items") or [] if x.get("theatre") and x.get("placed") is not None]
        top = max((x.get("ts_ms") or 0 for x in items), default=0)
        recent = [x for x in items if (x.get("ts_ms") or 0) >= top - hours * 3600 * 1000]
        recent.sort(key=lambda x: (x.get("category") not in (None, "other"), min(len(x.get("also_in") or []), 3),
                                   x.get("ts_ms") or 0), reverse=True)
        for x in recent:
            lst = out["latest"].setdefault(x["theatre"], [])
            if len(lst) < per_theatre:
                lst.append("%s [%s] %s" % (x.get("ts", "")[11:16], ",".join(x.get("countries")[:2]) or "-",
                                           cut(x.get("title"), 90)))
        while len(json.dumps(out, ensure_ascii=False)) >= 2048 and any(out["latest"].values()):
            k = max(out["latest"], key=lambda t: len(out["latest"][t]))
            out["latest"][k].pop()
        return out
    except Exception as e:  # never break the digest
        return {"error": type(e).__name__}


FEEDS = {"wire": (poll, 300)}
