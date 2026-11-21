"""Power and cell-network disruption layers. v1.2, 2026-11-21 (Ground Truth 1.5.5; v1.1 came with 1.5.4, v1.0 with
1.5.3).

1.1 adds Cloudflare Radar's own API (radar_outages, radar_anomalies below; a free read-only token) next to its
Bluesky posts. 1.2 keeps the cloud origins of each annotation and anomaly (`origins`, `origin`) and lends both Radar
lists to gt/services.py through radar_rows(), so its websites and AI / cloud layers show the PLATFORM annotations and
cloud-region (ORIGIN) anomalies this module leaves out, without a second fetch.

Two feeds (FEEDS at the bottom), both called every 300 s, built to the shared 1.5.3 outage-layer contract (the same
item shape, window, caps and GeoJSON as gt/services.py). Each source has its own cadence and cached state in
<GT_DATA>/cache/disruption_state.json; a poll fetches only the sources that are due, so one slow or failing source
never blocks or fails a feed (a feed fails only when none of its sources has ever answered). A poll stops fetching
after 3 failures in a row or 45 s; the rest wait for the next call. Conditional GET (ETag / Last-Modified) where a
source sends validators (Taipower does). One lock covers both feeds: they share the state file and two sources.

`power` (power outages and grid stress):
* odin, every 10 min: ODIN (Oak Ridge National Laboratory / US DOE) county outages, `metersAffected` summed per
  county across utilities. Participating utilities only, so US totals are a floor, not national coverage. Most rows
  are 1-8 meters; a county becomes an item at 500 customers out and stays active while it is at or over that; its
  first poll there is `start_ms`; when it falls below, the item ends (inactive, `end_ms` set) and is kept 24 h. The
  same county crossing again on the same UTC day resumes that day's item. County centroids come from ODIN's
  county map (largest polygon), fetched only when an unknown county crosses the threshold, at most every 30 min,
  and cached in the state for good.
* netblocks (every 10 min) and cfradar (every 15 min): NetBlocks' Mastodon RSS and Cloudflare Radar's Bluesky RSS
  (it redirects to the account's did: address; urllib follows). One fetch serves both feeds: the parsed posts (7
  days) sit in the state. Each post is classified (classify()): power (power, blackout, electricity, grid, energy
  infrastructure, power cuts ...) -> a `power` item; mobile (mobile, cellular, 3G/4G/5G, a mobile operator's name,
  "operator ... (ASnnnn)") and not power -> a `cellular` item; other internet disruptions -> the `cellular` feed's
  `internet` list; Cloudflare Radar posts that are none of these (game launches, certificate trivia) are dropped,
  NetBlocks posts default to internet. Places: Ukrainian oblasts and Russian federal subjects named in English (from
  web/geo/alert-regions.json, plus a few spellings) -> one point per subject; else country hashtags; else
  gt/placer.py's strongest country, at its centroid from web/geo/theatres.json. Title = the first sentence or line.
* radar_outages, every 15 min (1.1): Cloudflare Radar's outage annotations (GET /radar/annotations/outages, the last
  28 days), the curated record behind its Outage Center: cause, scope (nationwide / regional / network), start, end,
  countries, networks (ASNs) and, for some, regions (GeoNames entities). One fetch serves both feeds. Each annotation
  is classified (radar_class()): cause POWER_OUTAGE, or a description naming power / the grid -> a `power` item;
  a description naming mobile networks -> a `cellular` item; anything else -> the `cellular` feed's `internet`
  list (a government-directed one is kind "shutdown"); PLATFORM ones (one online service or cloud region, such as
  Microsoft 365 or AWS me-central-1) are left out here: gt/services.py 1.1 lists them. Active while it has no end, or
  its end is still ahead. Severity: nationwide critical, regional
  major, a single network major when the wording says so (significant, complete, near-total ...), else minor.
  Places: Ukrainian oblasts / Russian subjects in the region entities or the description; else the countries it
  lists (or its networks' countries; else gt/placer.py on the description), at their centroids. The link is the
  annotation's own post when it has a public one, else Radar's Outage Center. A Bluesky post from cfradar that
  repeats an annotation (a shared country, posted from 6 h before its start to 24 h after its end) is dropped.
* radar_anomalies, every 15 min (1.1): Radar's automatically detected traffic anomalies (GET /radar/traffic_anomalies,
  the last 7 days). Kept: status VERIFIED or TP (the confirmed states seen in the data), not linked to an annotation
  (that one already counts), for a country or a network. An anomaly on a known mobile operator's network (Tele2 / T2,
  Beeline, MegaFon, MTS, Celcom, ...; by its network name) -> a `cellular` item; the rest -> the `internet` list.
  Cloud-region (ORIGIN) anomalies are left out here (gt/services.py 1.1 lists them). Country ones major, network ones
  minor; placed at the country.
  radar_rows() (1.2) hands both stored lists, with each source's ok / error / last fetch, to gt/services.py. It reads
  the state file without the lock (the file is replaced atomically; a poll may hold the lock for a minute).
  The token: $CF_RADAR_TOKEN, else $GT_SEED/cfradar.key (the host's read-only seed mount, written by
  deploy/stage.py from tools/cfradar-key.sh's ~/.config/cloudflare/radar_token), else that file. It goes only to
  api.cloudflare.com in the Authorization header and is never logged or stored. Without one, both sources show
  "not configured" and the feeds carry on without them.
* ukrenergo, minenergo, each at most every 10 min: the public t.me/s previews of NEC Ukrenergo and the Ministry of
  Energy of Ukraine, read with gt/telegram.py's _get / parse_page / tidy. Posts in Ukrainian (lang "uk"; the
  translation job adds English). Kept: posts about outages or supply (знеструм-, відключен-, енерго- /
  електропостачан-, графік-, аварійн-, без світла, or an attack on energy with its consequences); dropped: aid,
  conference and video-feature posts that name no outage. Tags: emergency (аварійн-, not аварійно-ремонтні
  crews), schedule (графік / погодинн-), restored (відновлено / відновили / повернули світло), attack. Oblasts are
  matched in any case form from the adjective's root ("Львівська / Львівській / Львівщини" -> Lviv), plus the main
  cities; Kyiv city (UA-30) and Kyiv Oblast (UA-32) are told apart. Severity: emergency major, schedule minor, else
  info. A schedule post for "завтра" (tomorrow) or "сьогодні" (today) stays active until that day's Kyiv midnight;
  other posts for 6 h.
* taipower, every 10 min: Taipower's supply/demand open data. curr_load is in units of 10 MW; publish_time is a ROC
  calendar date in Taiwan time ("115.11.21(六)12:40" = 2026-11-21 04:40Z). grid.taipower always; an item only when
  the forecast peak-reserve light is not green: yellow minor, orange major, red / black critical.
* eskom, every 30 min: Eskom GetStatus, a bare integer; stage = value - 1 (community-documented). 99 or any value
  outside 1..9 means "updating": the previous stage is kept. An item from stage 1 (1-2 minor, 3-5 major, 6+ critical).
* caiso, every 10 min: CAISO Today's Outlook active emergency notices. Times are Pacific wall clock (US DST rule).
  One item per current event, pinned at the Folsom control centre (Sacramento area): EEA major (EEA Watch minor),
  Flex Alert and RMO minor. An event that leaves the list ends and is kept 24 h.

`cellular` (cell / mobile network disruptions): the mobile posts and the `internet` list (newest 60) from the two
RSS feeds above, and
* monitor_ru, every 3 h: Na Svyazi's «Монитор рунета» daily map, the one unauthenticated GET its public page makes
  (/api/shutdown_map_report?n=1; no other route is ever called). Regions repeat inside a snapshot, so each code is
  counted once. One item per snapshot ("Russia: mobile internet cut in 66 regions, whitelists in 65"), major, active
  while it is the newest map and under 3 days old; one GeoJSON point per region at its subject centroid, with
  `shutdown` / `whitelist` in the properties. Undocumented and may break: a failure there only marks that source.

Items: the last 72 h plus every active one (active ones capped at 30 days old), newest first, at most 400 and about
300 KB with the GeoJSON. Posts count as active for 6 h unless they report a recovery (Ukrainian schedule posts:
see above). Ids are stable across polls (the post id, the county FIPS + first day, the snapshot id, the CAISO
event id, the grid episode's start).

Terms: ODIN and CAISO are US public data; Taipower is under Taiwan's Open Government Data Licence (attribution
required); NetBlocks, Cloudflare Radar and the Telegram channels are their own posts, shown as short text with a
link back; Cloudflare Radar's API data is CC BY-NC 4.0 (attribution, non-commercial); Eskom has no stated licence;
monitor-ru is an undocumented endpoint. So PUBLIC_OK is False for both feeds
(kept private in v1, Taipower included) and NON_COMMERCIAL is True (never for the trading agent).
"""
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from . import geo, placer, telegram, wire

VERSION = "1.2"
UA = "GroundTruth/1.5 (personal non-commercial OSINT dashboard)"
TIMEOUT = 15
MAX_BODY = 8 * 1024 * 1024

ODIN_URL = "https://odin.ornl.gov/odi?format=JSON&view=county&pageSize=1000"
ODIN_MAP_URL = "https://odin.ornl.gov/odi/map?scale=COUNTY"
NETBLOCKS_URL = "https://mastodon.social/@netblocks.rss"
CFRADAR_URL = "https://bsky.app/profile/radar.cloudflare.com/rss"
TAIPOWER_URL = "https://service.taipower.com.tw/data/opendata/apply/file/d006020/001.json"
ESKOM_URL = "https://loadshedding.eskom.co.za/LoadShedding/GetStatus"
CAISO_URL = "https://wwwmobile.caiso.com/TodaysOutlookApi/api/EmergencyNotices/v2/ActiveEvents"
MONITOR_RU_URL = "https://monitor-ru.net/api/shutdown_map_report?n=1"
RADAR_API = "https://api.cloudflare.com/client/v4/radar"
RADAR_OUTAGES_URL = RADAR_API + "/annotations/outages?dateRange=28d&limit=200&format=json"
RADAR_ANOMALIES_URL = RADAR_API + "/traffic_anomalies?dateRange=7d&limit=200&format=json"
RADAR_CENTER = "https://radar.cloudflare.com/outage-center"
RADAR_TRAFFIC = "https://radar.cloudflare.com/traffic/%s"     # "as15378" or a lower-case ISO 3166-1 alpha-2 code
TG_CHANNELS = {"ukrenergo": "Ukrenergo", "minenergo": "energyofukraine"}

LINK = {"odin": "https://odin.ornl.gov/", "taipower": "https://www.taipower.com.tw/",
        "eskom": "https://loadshedding.eskom.co.za/", "caiso": "https://www.caiso.com/todays-outlook",
        "monitor_ru": "https://monitor-ru.net/"}

# key: (label, provider, every s, retry s after a failure, slack s)
SOURCES = {
    "odin": ("ODIN US county outages (ORNL / DOE)", "ODIN", 600, 300, 30),
    "netblocks": ("NetBlocks (Mastodon)", "NetBlocks", 600, 300, 30),
    "cfradar": ("Cloudflare Radar (Bluesky)", "Cloudflare Radar", 900, 450, 30),
    "ukrenergo": ("Ukrenergo (Telegram)", "Ukrenergo", 600, 600, 0),       # at most every 10 min
    "minenergo": ("Ministry of Energy of Ukraine (Telegram)", "Ministry of Energy of Ukraine", 600, 600, 0),
    "taipower": ("Taipower supply and demand", "Taipower", 600, 300, 30),
    "eskom": ("Eskom load shedding", "Eskom", 1800, 900, 30),
    "caiso": ("CAISO grid notices", "CAISO", 600, 300, 30),
    "monitor_ru": ("Na Svyazi «Монитор рунета»", "Na Svyazi", 10800, 1800, 30),
    "radar_outages": ("Cloudflare Radar outage annotations", "Cloudflare Radar", 900, 450, 30),
    "radar_anomalies": ("Cloudflare Radar traffic anomalies", "Cloudflare Radar", 900, 450, 30),
}
FEED_SOURCES = {"power": ("odin", "taipower", "eskom", "caiso", "radar_outages", "netblocks", "cfradar", "ukrenergo",
                          "minenergo"),
                "cellular": ("radar_outages", "radar_anomalies", "netblocks", "cfradar", "monitor_ru")}
BACKOFF = 3600            # s after a 403 / 429

ATTRIBUTION = {
    "power": ("ODIN, Oak Ridge National Laboratory / US Department of Energy (participating utilities only); NEC "
              "Ukrenergo and the Ministry of Energy of Ukraine (public Telegram channels); Taiwan Power Company "
              "(Open Government Data License, version 1.0); Eskom; California ISO; NetBlocks; Cloudflare Radar "
              "(outage annotations: CC BY-NC 4.0)"),
    "cellular": ("Cloudflare Radar (outage annotations and traffic anomalies: CC BY-NC 4.0); NetBlocks; Na Svyazi "
                 "«Монитор рунета» (monitor-ru.net)"),
}
NOTE = {
    "power": ("Power outages and grid stress, each source on its own cadence. US: ODIN county outages (participating "
              "utilities only, so totals are a floor), a county from 500 customers out summed across utilities, "
              "ending when it falls below. Ukraine: Ukrenergo and Ministry of Energy posts (Ukrainian; tagged "
              "emergency / schedule / restored; oblasts read from the text). Taiwan: Taipower's forecast peak-reserve "
              "light (an item when not green). South Africa: Eskom's load-shedding stage (an item from stage 1). "
              "California: CAISO's active grid emergency notices. Worldwide: Cloudflare Radar's outage annotations "
              "caused by power cuts (active until Radar records an end), and NetBlocks and Cloudflare Radar posts that "
              "name power, blackouts or the grid (a Radar post that repeats an annotation is dropped). Posts count as "
              "active for 6 h (a Ukrainian schedule post until the end of the day it covers). Last 72 h plus anything "
              "still active."),
    "cellular": ("Cell / mobile network disruptions: Cloudflare Radar's outage annotations that name mobile networks and "
                 "its confirmed traffic anomalies on known mobile operators' networks; NetBlocks (Mastodon) and "
                 "Cloudflare Radar (Bluesky) posts that name mobile, cellular, 3G/4G/5G or a mobile operator "
                 "(power-related ones go to the power layer; other internet disruptions, Radar's included, go to the "
                 "`internet` list, not on this layer); and Na Svyazi's «Монитор рунета» daily map of Russia's regional "
                 "mobile-internet shutdowns and whitelists (only approved sites work), one point per region. Posts "
                 "count as active for 6 h, Radar items until Radar records an end. Last 72 h plus anything still "
                 "active."),
}
NON_COMMERCIAL = {"power": True, "cellular": True}
PUBLIC_OK = {"power": False, "cellular": False}   # v1: private, Taipower's open licence included

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")
STATE_FILE = "disruption_state.json"
GEO_DIR = os.path.join(ROOT, "web", "geo")

WINDOW = 72 * 3600
ACTIVE_MAX = 30 * 86400
ENDED_KEEP = 24 * 3600
POST_KEEP = 7 * 86400
POST_ACTIVE = 6 * 3600
MONITOR_ACTIVE = 3 * 86400
MAX_ITEMS = 400
MAX_BYTES = 300 * 1000
INTERNET_MAX = 60
SUMMARY_MAX = 700
TITLE_MAX = 240
ITEM_SUMMARY_MAX = 400
POLL_BUDGET = 45          # s of fetching per poll
MAX_FAILS = 3             # failures in a row that end a poll's fetching
ODIN_MIN = 500            # customers out in a county
ODIN_MAP_EVERY = 1800
CAISO_LL = [-121.18, 38.68]   # the CAISO control centre in Folsom, Sacramento area
SEV_RANK = {"critical": 0, "major": 1, "minor": 2, "maintenance": 3, "info": 4}
_LOCK = threading.Lock()

STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
    "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
    "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP",
    "72": "PR", "78": "VI",
}
TERRITORY_A3 = {"60": "ASM", "66": "GUM", "69": "MNP", "72": "PRI", "78": "VIR"}
LIGHTS = {"G": ("green", None), "Y": ("yellow", "minor"), "O": ("orange", "major"), "R": ("red", "critical"),
          "B": ("black", "critical")}

# English names of Ukrainian oblasts (alert-regions `en` is the default) and Russian subjects (the `en` core is the
# default: "Republic of", "Krai", "Oblast", "Republic", "Autonomous Okrug" stripped). Longest phrase wins, so
# "Kyiv Oblast" is UA-32 and bare "Kyiv" the city (UA-30); "Vladimir" and "Jewish" need their suffix.
UA_EN = {
    "UA-05": ("Vinnytsia", "Vinnytsya", "Vinnitsa"), "UA-07": ("Volyn", "Volhynia", "Lutsk"),
    "UA-09": ("Luhansk", "Lugansk"), "UA-12": ("Dnipropetrovsk", "Dnepropetrovsk", "Dnipro"),
    "UA-14": ("Donetsk",), "UA-18": ("Zhytomyr", "Zhitomir"),
    "UA-21": ("Zakarpattia", "Zakarpattya", "Transcarpathia", "Uzhhorod"),
    "UA-23": ("Zaporizhzhia", "Zaporizhia", "Zaporizhzhya", "Zaporozhye"), "UA-26": ("Ivano-Frankivsk",),
    "UA-30": ("Kyiv", "Kiev"),
    "UA-32": ("Kyiv Oblast", "Kyiv oblast", "Kyiv region", "Kyiv Region", "Kiev Oblast", "Kiev region"),
    "UA-35": ("Kirovohrad", "Kropyvnytskyi"), "UA-40": ("Sevastopol",), "UA-43": ("Crimea",),
    "UA-46": ("Lviv", "Lvov"), "UA-48": ("Mykolaiv", "Nikolaev"), "UA-51": ("Odesa", "Odessa"),
    "UA-53": ("Poltava",), "UA-56": ("Rivne",), "UA-59": ("Sumy",), "UA-61": ("Ternopil",),
    "UA-63": ("Kharkiv", "Kharkov"), "UA-65": ("Kherson",), "UA-68": ("Khmelnytskyi", "Khmelnytsky", "Khmelnitsky"),
    "UA-71": ("Cherkasy",), "UA-74": ("Chernihiv",), "UA-77": ("Chernivtsi", "Bukovina"),
}
RU_EN = {
    "RU-AL": ("Altai Republic", "Republic of Altai"), "RU-ALT": ("Altai Krai",),
    "RU-CE": ("Chechnya", "Chechen Republic"), "RU-CU": ("Chuvashia", "Chuvash Republic"),
    "RU-KC": ("Karachay-Cherkessia", "Karachay-Cherkess"), "RU-SE": ("North Ossetia",),
    "RU-SA": ("Yakutia", "Sakha"), "RU-UD": ("Udmurtia", "Udmurt Republic"), "RU-YAN": ("Yamalo-Nenets", "Yamal"),
    "RU-KHM": ("Khanty-Mansi", "Yugra"), "RU-YEV": ("Jewish Autonomous Oblast", "Jewish Autonomous Region"),
    "RU-VLA": ("Vladimir Oblast", "Vladimir oblast", "Vladimir region", "Vladimir Region"),
    "RU-MOS": ("Moscow Oblast", "Moscow oblast", "Moscow region", "Moscow Region"), "RU-MOW": ("Moscow",),
    "RU-SPE": ("Saint Petersburg", "St. Petersburg", "St Petersburg"), "RU-BA": ("Bashkortostan", "Bashkiria"),
    "RU-TY": ("Tuva", "Tyva"), "RU-ZAB": ("Zabaykalsky", "Transbaikal"), "RU-PRI": ("Primorsky", "Primorye"),
    "RU-KEM": ("Kemerovo", "Kuzbass"), "RU-ORL": ("Oryol", "Orel"), "RU-ME": ("Mari El",),
}
DISPLAY = {"UA-51": "Odesa", "UA-43": "Crimea", "RU-YEV": "Jewish Autonomous Oblast"}
CITY_LL = {"UA-30": [30.523, 50.45], "UA-40": [33.522, 44.616], "RU-MOW": [37.618, 55.751],
           "RU-SPE": [30.316, 59.939]}   # city centres (the polygon centroids sit off-centre)
# Ukrainian city names and other forms beyond the adjective root and the -щина form
UK_EXTRA = {
    "UA-30": (r"Ки(?:їв|єва|єві|євом|єву)", r"м\.\s*Ки(?:їв|єва|єві)"), "UA-40": (r"Севастопол(?:ь|я|і|ем)",),
    "UA-43": (r"Крим(?:у|ом|і)?", r"Кримськ\w*"), "UA-46": (r"Льв(?:ів|ова|ові|овом)",),
    "UA-63": (r"Харк(?:ів|ова|ові|овом)",), "UA-12": (r"Дніпр(?:о|а|і|ом)", r"Дніпровщин\w*"),
    "UA-51": (r"Одес(?:а|и|і|у|ою)",), "UA-53": (r"Полтав(?:а|и|і|у|ою)",), "UA-65": (r"Херсон(?:а|і|ом|у)?",),
    "UA-74": (r"Черніг(?:ів|ова|ові|овом)",), "UA-48": (r"Микола(?:їв|єва|єві|євом)",),
    "UA-18": (r"Житомир(?:а|і|ом|у)?",), "UA-05": (r"Вінниц(?:я|і|ю|ею)",), "UA-71": (r"Черкас(?:и|ах|ам)",),
    "UA-61": (r"Терноп(?:іль|оля|олі|олем)",), "UA-07": (r"Волин(?:ь|і|ню)", r"Луцьк\w*"),
    "UA-21": (r"Закарпатт\w*", r"Ужгород\w*"), "UA-77": (r"Буковин\w*", r"Чернівц(?:і|ів|ях)"),
    "UA-35": (r"Кропивницьк\w*",), "UA-26": (r"Прикарпатт\w*",),
}

# ---------------- post classification (NetBlocks, Cloudflare Radar) ----------------

_POLITICAL_POWER = re.compile(r"\b(?:came|come|comes|coming|rise|rose|risen|seiz\w*|grab\w*|remain\w*|stay\w*|hold\w*|"
                              r"return\w*|back) (?:to|in) power\b|\bpower (?:struggle|grab|sharing|of)\b|"
                              r"\bsuperpowers?\b|\bpower users?\b", re.I)
_POWER = re.compile(r"\bpower\b|\bblackouts?\b|\belectricity\b|\belectric (?:grid|supply|utility|company)\b|\bgrid\b|"
                    r"\benergy (?:infrastructure|facilit\w+|sites?|system|grid|supply|plants?|networks?)\b|"
                    r"\bsubstations?\b|\bload[- ]shedding\b|\btransmission (?:lines?|network|grid)\b", re.I)
_MOBILE = re.compile(r"\bmobile\b|\bcellular\b|\bcell(?:phone)? (?:networks?|service|towers?|coverage)\b", re.I)
_OPERATORS = re.compile(r"(?<![\w-])(?:Kyivstar|Vodafone Ukraine|lifecell|Lifecell|MegaFon|Megafon|MTS|Beeline|Tele2|"
                        r"T2|Irancell|MCI|Hamrah-e[ -]Aval|Hamrahe Aval|RighTel|Rightel|Turkcell|Verizon|AT&T|"
                        r"T-Mobile|Jazz|Zong|Ufone|Telenor|[345]G|LTE)(?![\w-])")
_OPERATOR_AS = re.compile(r"\boperators?\b[^.\n]{0,80}\(AS\d+\)|\(AS\d+\)[^.\n]{0,80}\boperators?\b", re.I)
_INTERNET = re.compile(r"\bconnectivity\b|\bnetwork data\b|\bshutdowns?\b|\boutages?\b|\bdisrupt\w*|\boffline\b|"
                       r"\brestrict\w*|\bconnection failures?\b|\bblock(?:ed|ing|s)?\b|\bthrottl\w*|"
                       r"\btraffic\b[^.\n]{0,40}\b(?:drop\w*|fell|fall\w*|declin\w*|down|reduc\w*|decreas\w*|cut|lost)\b|"
                       r"\b(?:drop\w*|declin\w*|decreas\w*)\b[^.\n]{0,30}\btraffic\b|\bcable cuts?\b|"
                       r"\bfib(?:er|re)[- ](?:optic )?(?:cables? )?cuts?\b", re.I)
_RECOVERED = re.compile(r"\brecover(?:ed|y|ing)\b|\brestored\b|\bback online\b", re.I)
_CRIT = re.compile(r"\bnation-?wide (?:power |internet |electricity |mobile |telecom )?(?:outages?|blackouts?|"
                   r"shutdowns?|disruptions?)\b|\b(?:outages?|blackouts?|shutdowns?) (?:nation-?wide|across the "
                   r"country)\b|\btotal (?:system failure|blackout|shutdown|outage)|\bknocked out\b|"
                   r"\bcomplete (?:internet )?(?:outage|blackout|shutdown)|\bnear[- ]total\b|\b(?:to|near) zero\b|"
                   r"\blargely offline\b|\bisland-wide\b", re.I)
_MAJ = re.compile(r"\bsignificant\b|\bmajor\b|\bwidespread\b|\bmassive\b|\blarge-scale\b|\bsevere\b|\bmost powerful\b|"
                  r"\blargest\b|\bmuch of\b|\bmultiple regions\b", re.I)


def classify(text, source=None):
    """A post's text -> "power", "mobile", "internet" or None (Cloudflare Radar trivia: dropped). Power wins over
    mobile, mobile over internet; a NetBlocks post that matches nothing counts as internet."""
    t = text or ""
    if _POWER.search(_POLITICAL_POWER.sub(" ", t)):
        return "power"
    if _MOBILE.search(t) or _OPERATORS.search(t) or _OPERATOR_AS.search(t):
        return "mobile"
    if _INTERNET.search(t):
        return "internet"
    return "internet" if source == "netblocks" else None


# ---------------- Ukrainian posts (Ukrenergo, Ministry of Energy) ----------------

_UK_STRONG = re.compile(r"знеструм|відключен|енергопостачан|електропостачан|графік|аварійн(?!о-)|без світла", re.I)
_UK_OUTAGE = re.compile(r"знеструм|відключен|без світла", re.I)
_UK_ATTACK = re.compile(r"атак|обстріл|удар|уражен", re.I)
_UK_ENERGY = re.compile(r"енерг|підстанц|електро|ТЕС|ТЕЦ|ГЕС|ЛЕП")
_UK_CONSEQ = re.compile(r"внаслідок|наслідк|пошкодж|станом на", re.I)
_UK_FEATURE = re.compile(r"Натисніть на відео|за посиланням|допомог\w* від|пакет допомоги|Дякуємо|конференц|"
                         r"інвестиц|МАГАТЕ|програм\w*[^.\n]{0,30}підтримк|доплат|вакансі|конкурс", re.I)
_UK_EMERGENCY = re.compile(r"аварійн(?!о-)", re.I)
_UK_SCHEDULE = re.compile(r"графік|погодинн", re.I)
_UK_RESTORED = re.compile(r"відновлен[оі]\b|відновили|повернули (?:світло|електр)", re.I)
_UK_TOMORROW = re.compile(r"(?<!\w)завтра(?!\w)", re.I)
_UK_TODAY = re.compile(r"(?<!\w)сьогодні(?!\w)", re.I)


def tg_keep(text):
    """True for a post about power supply or outages; aid, conference and feature posts naming no outage are out."""
    t = text or ""
    if _UK_FEATURE.search(t) and not _UK_OUTAGE.search(t):
        return False
    if _UK_STRONG.search(t):
        return True
    return bool(_UK_ATTACK.search(t) and _UK_ENERGY.search(t) and _UK_CONSEQ.search(t))


def tg_tags(text):
    t = text or ""
    tags = [tag for tag, rx in (("emergency", _UK_EMERGENCY), ("schedule", _UK_SCHEDULE), ("restored", _UK_RESTORED))
            if rx.search(t)]
    if _UK_ATTACK.search(t) and _UK_ENERGY.search(t):
        tags.append("attack")
    return tags


# ---------------- small helpers ----------------

def _fetch(url, headers=None):
    """GET -> (status, headers, body). A 304 comes back as (304, headers, b""); other HTTP errors raise."""
    h = {"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "*/*"}
    h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=TIMEOUT) as r:
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


class NotConfigured(RuntimeError):
    """A source that needs a key nobody has set: shown on its row, never counted as a failure in a row."""


def radar_token():
    """The Cloudflare Radar API token, or None: $CF_RADAR_TOKEN, else $GT_SEED/cfradar.key, else
    ~/.config/cloudflare/radar_token. Never logged."""
    k = (os.environ.get("CF_RADAR_TOKEN") or "").strip()
    if k:
        return k
    for p in (os.path.join(os.environ.get("GT_SEED") or "/seed", "cfradar.key"),
              os.path.expanduser("~/.config/cloudflare/radar_token")):
        try:
            with open(p, encoding="utf-8") as fh:
                k = fh.read().strip()
            if k:
                return k
        except OSError:
            pass
    return None


def _now(now):
    if now is None:
        return int(time.time())
    if isinstance(now, dt.datetime):
        return int((now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)).timestamp())
    return int(now)


def _iso(t):
    return dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t is not None else None


def _day(t):
    return dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y%m%d")


def _stamp(t):
    return dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y%m%dT%H%M")


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _err(e):
    return _clip("%s: %s" % (type(e).__name__, e), 200)


def _sha(s, n=12):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _num(n):
    return "{:,}".format(int(n))


def _path(name):
    return os.path.join(CACHE, name)


def _load():
    try:
        with open(_path(STATE_FILE), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(obj):
    os.makedirs(CACHE, exist_ok=True)
    tmp = _path(STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    os.replace(tmp, _path(STATE_FILE))


def _date_noon(s, nt):
    """'YYYY-MM-DD' -> that day's 12:00 UTC, never later than now; None when unreadable."""
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$", s or "")
    if not m:
        return None
    try:
        t = int(dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, tzinfo=dt.timezone.utc).timestamp())
    except ValueError:
        return None
    return min(t, nt)


# ---------------- time zones ----------------

def _nth_sunday(year, month, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_sunday(year, month):
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def kyiv_day_end(t, days=0):
    """Epoch s of the Kyiv midnight that ends the local day of `t` plus `days` days. Kyiv time is UTC+2, UTC+3 from
    the last Sunday of March to the last Sunday of October (01:00 UTC switches, as in the EU)."""
    def off(x):
        y = dt.datetime.fromtimestamp(x, dt.timezone.utc).year
        a = dt.datetime.combine(_last_sunday(y, 3), dt.time(1), dt.timezone.utc).timestamp()
        b = dt.datetime.combine(_last_sunday(y, 10), dt.time(1), dt.timezone.utc).timestamp()
        return 3 if a <= x < b else 2
    local = dt.datetime.fromtimestamp(t + off(t) * 3600, dt.timezone.utc).date() + dt.timedelta(days=days + 1)
    mid = int(dt.datetime(local.year, local.month, local.day, tzinfo=dt.timezone.utc).timestamp())
    return mid - off(mid - 3 * 3600) * 3600


def pacific_to_utc(t):
    """Naive US Pacific wall time -> epoch s. DST from the 2nd Sunday of March 02:00 to the 1st Sunday of November
    02:00 (PDT, UTC-7); otherwise PST (UTC-8). The repeated hour in November reads as PDT."""
    start = dt.datetime.combine(_nth_sunday(t.year, 3, 2), dt.time(2))
    end = dt.datetime.combine(_nth_sunday(t.year, 11, 1), dt.time(2))
    off = 7 if start <= t < end else 8
    return int((t + dt.timedelta(hours=off)).replace(tzinfo=dt.timezone.utc).timestamp())


_RX_PT = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?\s*$")


def pt_time(s):
    """CAISO '2026-08-20T16:00:00' (Pacific wall clock) -> epoch s; a string with an offset keeps it."""
    m = _RX_PT.match(s or "") if isinstance(s, str) else None
    if not m:
        return None
    y, mo, d, h, mi, sec, tz = m.groups()
    if tz:
        return wire.parse_time(s.strip())
    try:
        return pacific_to_utc(dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec or 0)))
    except ValueError:
        return None


_RX_ROC = re.compile(r"^\s*(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})\s*(?:\([^)]*\)|（[^）]*）)?\s*(\d{1,2}):(\d{2})")


def roc_time(s):
    """Taipower '115.11.21(六)12:40' (ROC year, Taiwan time UTC+8) -> epoch s; a 4-digit year is Gregorian."""
    m = _RX_ROC.match(s or "") if isinstance(s, str) else None
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    if y < 1000:
        y += 1911
    try:
        return int(dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone(dt.timedelta(hours=8))).timestamp())
    except ValueError:
        return None


# ---------------- geography ----------------

_GEO = {}


def _ring_area_c(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[i + 1][0], ring[i + 1][1]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a) < 1e-12:
        n = float(len(ring)) or 1.0
        return 0.0, (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)
    return abs(a) / 2, (cx / (3 * a), cy / (3 * a))


def _polys(geom):
    if not isinstance(geom, dict):
        return []
    c = geom.get("coordinates")
    if geom.get("type") == "Polygon" and isinstance(c, list) and c:
        return [c]
    if geom.get("type") == "MultiPolygon" and isinstance(c, list):
        return [p for p in c if isinstance(p, list) and p]
    return []


def _largest(geom):
    """The outer ring of a geometry's largest polygon, or None."""
    best, ba = None, -1.0
    for p in _polys(geom):
        ring = p[0]
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        a, _c = _ring_area_c(ring)
        if a > ba:
            best, ba = ring, a
    return best


def centroid(geom):
    """[lon, lat] of the largest polygon's area centroid (so islands and antimeridian splits do not pull it)."""
    ring = _largest(geom)
    if ring is None:
        return None
    _a, (x, y) = _ring_area_c(ring)
    return [round(x, 3), round(y, 3)]


def _inside(x, y, ring):
    hit = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi, xj, yj = ring[i][0], ring[i][1], ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            hit = not hit
        j = i
    return hit


def _json(name):
    with open(os.path.join(GEO_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def regions():
    """alert-regions.json -> {code: {"c", "en", "uk", "ll"}} for Ukraine's oblasts and Russia's subjects (cached).
    A centroid that lands outside its own polygon or inside a city it surrounds (Kyiv Oblast around Kyiv) moves to
    the nearest grid point that is inside the region and outside that city."""
    if "regions" in _GEO:
        return _GEO["regions"]
    feats = [f for f in (_json("alert-regions.json").get("features") or [])
             if isinstance(f, dict) and (f.get("properties") or {}).get("c") in ("UA", "RU")]
    rings = {f.get("id"): _largest(f.get("geometry")) for f in feats}
    out = {}
    for f in feats:
        code, p, ring = f.get("id"), f.get("properties") or {}, rings.get(f.get("id"))
        if not code or ring is None:
            continue
        ll = CITY_LL.get(code) or centroid(f.get("geometry"))
        cities = [rings[c] for c in CITY_LL if c != code and rings.get(c) and c[:2] == code[:2]]
        if code not in CITY_LL and (not _inside(ll[0], ll[1], ring) or any(_inside(ll[0], ll[1], r) for r in cities)):
            xs, ys = [q[0] for q in ring], [q[1] for q in ring]
            best = None
            for i in range(1, 24):
                for j in range(1, 24):
                    x = min(xs) + (max(xs) - min(xs)) * i / 24.0
                    y = min(ys) + (max(ys) - min(ys)) * j / 24.0
                    if _inside(x, y, ring) and not any(_inside(x, y, r) for r in cities):
                        d2 = (x - ll[0]) ** 2 + (y - ll[1]) ** 2
                        if best is None or d2 < best[0]:
                            best = (d2, [round(x, 3), round(y, 3)])
            if best:
                ll = best[1]
        out[code] = {"c": p.get("c"), "en": DISPLAY.get(code) or p.get("en") or code, "uk": p.get("uk") or "", "ll": ll}
    _GEO["regions"] = out
    return out


def countries():
    """theatres.json -> {a3: ([lon, lat], name)} (cached)."""
    if "countries" not in _GEO:
        _GEO["countries"] = {a3: ([v[1], v[2]], v[3]) for a3, v in (_json("theatres.json").get("a3") or {}).items()
                             if isinstance(v, list) and len(v) >= 4}
    return _GEO["countries"]


def _region_a3(code):
    return {"UA": "UKR", "RU": "RUS"}.get((code or "")[:2])


def _en_core(en):
    s = re.sub(r"^(?:Republic of|Autonomous Republic of)\s+", "", en or "")
    return re.sub(r"\s+(?:Republic|Krai|Oblast|Autonomous Okrug|Autonomous Oblast)$", "", s)


def _en_rx():
    if "en_rx" not in _GEO:
        pairs = []
        for code, r in regions().items():
            if r["c"] == "UA":
                names = UA_EN.get(code) or (r["en"],)
            else:
                names = RU_EN.get(code) or (_en_core(r["en"]),)
            pairs.extend((n, code) for n in names if n)
        pairs.sort(key=lambda x: (-len(x[0]), x[0]))
        _GEO["en_rx"] = (re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n, _ in pairs) + r")(?![\w])"),
                         {n: c for n, c in pairs})
    return _GEO["en_rx"]


def match_en(text):
    """ISO 3166-2 codes of the Ukrainian oblasts and Russian subjects named in English, in order of mention."""
    rx, lookup = _en_rx()
    out = []
    for m in rx.finditer(text or ""):
        c = lookup.get(m.group(1))
        if c and c not in out:
            out.append(c)
    return out


def _uk_rx():
    if "uk_rx" not in _GEO:
        pats = []
        for code, r in regions().items():
            if r["c"] != "UA":
                continue
            uk = r["uk"]
            if uk.endswith(" область"):
                adj = uk[:-len(" область")]
                pats.append((re.escape(adj[:-1]) + r"\w*", code))        # Львівськ-а/-ій/-ої/-у/-ою
                if adj.endswith("цька"):
                    pats.append((re.escape(adj[:-4]) + r"ччин\w*", code))   # Вінниччина, Донеччина
                elif adj.endswith("зька"):
                    pats.append((re.escape(adj[:-4]) + r"жж\w*", code))     # Запоріжжя
                elif adj.endswith("ська"):
                    pats.append((re.escape(adj[:-4]) + r"щин\w*", code))    # Львівщина, Одещина
            pats.extend((p, code) for p in UK_EXTRA.get(code, ()))
        _GEO["uk_rx"] = [(re.compile(r"(?<![\w-])" + p + r"(?![\w-])", re.I), c) for p, c in pats]
    return _GEO["uk_rx"]


_UK_KYIV_TIME = re.compile(r"київськ\w*\s+час\w*", re.I)
_UK_KYIV_CITY = re.compile(r"київськ\w*\s+міськ\w*", re.I)


def match_uk(text):
    """ISO 3166-2 codes of the Ukrainian oblasts named in Ukrainian, any case form, in order of mention."""
    t = _UK_KYIV_CITY.sub("Київ", _UK_KYIV_TIME.sub(" ", text or ""))
    first = {}
    for rx, code in _uk_rx():
        m = rx.search(t)
        if m and (code not in first or m.start() < first[code]):
            first[code] = m.start()
    return [c for c, _ in sorted(first.items(), key=lambda x: (x[1], x[0]))]


# ---------------- parsers ----------------

def parse_odin(body):
    """ODIN county view -> {"hot": {fips: {"n", "utils": [[name, n], ...]}} at or over ODIN_MIN, "meters_out",
    "utilities", "counties_out", "rows"}: metersAffected summed per county across utilities."""
    d = json.loads(body)
    rows = d.get("outage") if isinstance(d, dict) else None
    if not isinstance(rows, list):
        raise ValueError("ODIN: no outage list")
    cty, utils, total = {}, set(), 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        f, n = str(r.get("communityDescriptor") or "").strip(), r.get("metersAffected")
        if not re.match(r"^\d{5}$", f) or isinstance(n, bool) or not isinstance(n, (int, float)) or n < 0:
            continue
        name = next((x.get("name") for x in r.get("names") or [] if isinstance(x, dict)
                     and x.get("nameType") == "UtilityName" and x.get("name")), None)
        name = _clip(name, 80) or "unnamed utility"
        c = cty.setdefault(f, {"n": 0, "utils": {}})
        c["n"] += int(n)
        c["utils"][name] = c["utils"].get(name, 0) + int(n)
        utils.add(name)
        total += int(n)
    hot = {f: {"n": c["n"], "utils": sorted(([u, k] for u, k in c["utils"].items()), key=lambda x: (-x[1], x[0]))[:6]}
           for f, c in cty.items() if c["n"] >= ODIN_MIN}
    return {"hot": hot, "meters_out": total, "utilities": len(utils), "counties_out": len(cty), "rows": len(rows)}


def parse_odin_map(body):
    """ODIN county map -> {fips: {"ll", "county", "state"}}."""
    d = json.loads(body)
    if not isinstance(d, list):
        raise ValueError("ODIN map: expected a list")
    out = {}
    for r in d:
        if not isinstance(r, dict):
            continue
        f = str(r.get("id") or "")
        if not re.match(r"^\d{5}$", f):
            f = next((str(o.get("county")) for o in r.get("outages") or [] if isinstance(o, dict)
                      and re.match(r"^\d{5}$", str(o.get("county") or ""))), "")
        ll = centroid(r.get("feature"))
        if f and ll:
            out[f] = {"ll": ll, "county": _clip(r.get("countyName"), 60) or None,
                      "state": _clip(r.get("stateName"), 40) or None}
    if d and not out:
        raise ValueError("ODIN map: no county geometry")
    return out


def _strip_tags(text):
    """Trailing hashtag runs off (2+ tags, or after punctuation), inline hashtags made words (CamelCase split)."""
    lines = []
    for ln in (text or "").split("\n"):
        m = re.search(r"((?:\s*#\w+)+)\s*$", ln)
        if m:
            head = ln[:m.start()].rstrip()
            if not head or len(re.findall(r"#\w+", m.group(1))) >= 2 or not head[-1:].isalnum():
                ln = head
        ln = re.sub(r"#(\w+)", lambda x: _split_tag(x.group(1)), ln)
        lines.append(re.sub(r"[ \t]+", " ", ln).strip())
    return "\n".join(lines).strip()


def _split_tag(tag):
    if tag[:1].isupper() and not tag.isupper():
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tag)
    return tag


def parse_rss(body, source):
    """NetBlocks (Mastodon) / Cloudflare Radar (Bluesky) RSS -> posts {"id", "url", "t", "text"}. The description is
    HTML (Mastodon) or plain text (Bluesky): either way it becomes plain text with line breaks."""
    root = wire._parse_xml(wire._ungzip(body))
    if wire._local(root.tag) not in ("rss", "channel"):
        raise ValueError("%s: not an RSS document: <%s>" % (source, wire._local(root.tag)))
    out = []
    for it in root.iter():
        if wire._local(it.tag) != "item":
            continue
        f = {}
        for c in it:
            n = wire._local(c.tag)
            if n in ("link", "guid", "pubDate", "description") and n not in f:
                f[n] = "".join(c.itertext()).strip()
        url = f.get("link") or (f.get("guid") if (f.get("guid") or "").startswith("https://") else "")
        t = wire.parse_time(f.get("pubDate"))
        text = telegram.to_text(f.get("description") or "")
        if not url.startswith("https://") or t is None or not text:
            continue
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        pid = tail if re.match(r"^[A-Za-z0-9]{4,40}$", tail) else _sha(url)
        out.append({"id": pid, "url": url, "t": t, "text": text[:4000]})
    return out


def parse_taipower(body):
    """Taipower d006020 -> {"light", "reserve_pct", "load_mw", "util_pct", "peak_hours", "t"}. curr_load is in
    units of 10 MW (萬瓩); publish_time is a ROC date in Taiwan time."""
    d = json.loads(body)
    recs = d.get("records") if isinstance(d, dict) else None
    if not isinstance(recs, list):
        raise ValueError("Taipower: no records")
    m = {}
    for r in recs:
        if isinstance(r, dict):
            m.update(r)
    light = str(m.get("fore_peak_resv_indicator") or "").strip().upper()
    if light not in LIGHTS:
        raise ValueError("Taipower: unknown reserve light %r" % light[:8])
    load = _float(m.get("curr_load"))
    return {"light": light, "reserve_pct": _float(m.get("fore_peak_resv_rate")),
            "load_mw": int(round(load * 10)) if load is not None else None, "util_pct": _float(m.get("curr_util_rate")),
            "peak_hours": _clip(m.get("fore_peak_hour_range"), 20) or None, "t": roc_time(m.get("publish_time"))}


def parse_eskom(body):
    """Eskom GetStatus -> the load-shedding stage (value - 1), or None while Eskom is "updating" (99, or any value
    outside 1..9). A body that is not a bare integer raises."""
    s = (body or b"").decode("utf-8", "replace").strip().strip('"').strip()
    if not re.match(r"^-?\d{1,6}$", s):
        raise ValueError("Eskom: not a stage number: %r" % s[:40])
    v = int(s)
    return v - 1 if 1 <= v <= 9 else None


def parse_caiso(body):
    """CAISO ActiveEvents -> {"current": [event], "upcoming": n}; event: id, type, start, end (epoch s, from Pacific
    wall time), in_effect, updated, messages [{"type", "t", "text"}]."""
    d = json.loads(body)
    if not isinstance(d, dict) or not isinstance(d.get("CurrentEvents"), list):
        raise ValueError("CAISO: no CurrentEvents list")
    evs = []
    for e in d["CurrentEvents"]:
        if not isinstance(e, dict):
            continue
        typ = _clip(wire.clean(str(e.get("EventType") or "")), 60) or "Grid notice"
        start, end = pt_time(e.get("StartDateTime_PT")), pt_time(e.get("EndDateTime_PT"))
        msgs = []
        for x in e.get("EventMessages") or []:
            if isinstance(x, dict):
                msgs.append({"type": _clip(wire.clean(str(x.get("MessageType") or "")), 40) or None,
                             "t": pt_time(x.get("PostDate_PT")),
                             "text": _clip(wire.clean(str(x.get("MessageBody") or "")), 600) or None})
        msgs.sort(key=lambda x: -(x["t"] or 0))
        eid = str(e.get("EventId") or "").strip()
        eid = eid if re.match(r"^[A-Za-z0-9_.-]{1,40}$", eid) else _sha("%s|%s" % (typ, start))
        ie = e.get("InEffect")
        evs.append({"id": eid, "type": typ, "start": start, "end": end, "in_effect": ie if isinstance(ie, bool) else None,
                    "updated": max([x["t"] for x in msgs if x["t"]] or [start or 0]) or None, "messages": msgs[:4]})
    return {"current": evs, "upcoming": len(d.get("UpcomingEvents") or [])}


_RX_CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")


def parse_monitor_ru(body):
    """monitor-ru shutdown_map_report -> snapshots {"id", "created", "date", "shutdown": [codes], "whitelist":
    [codes]}. Regions repeat inside a snapshot; each code counts once. A whitelist region (sd_type 27: shutdown with
    whitelists) is also a shutdown region."""
    d = json.loads(body)
    if not isinstance(d, dict) or d.get("status") != "success" or not isinstance(d.get("data"), list):
        raise ValueError("monitor-ru: unexpected response")
    out = []
    for s in d["data"]:
        if not isinstance(s, dict) or not isinstance(s.get("map_state"), dict):
            continue
        ms = s["map_state"]

        def codes(section):
            sec = ms.get(section) if isinstance(ms.get(section), dict) else {}
            return sorted({str(r.get("name") or "").strip().upper() for r in sec.get("regions") or []
                           if isinstance(r, dict) and _RX_CODE.match(str(r.get("name") or "").strip().upper())})
        wl = codes("whitelists")
        sd = sorted(set(codes("shutdowns")) | set(wl))
        created = wire.parse_time(str(s.get("created_at") or ""))
        sid = str(s.get("id") or "")
        if not re.match(r"^\d{1,9}$", sid) or created is None:
            continue
        out.append({"id": int(sid), "created": created, "date": str(s.get("map_date") or "")[:10] or None,
                    "shutdown": sd, "whitelist": wl})
    if not out:
        raise ValueError("monitor-ru: no snapshot")
    return out


def _radar_result(body, key):
    d = json.loads(body)
    if not isinstance(d, dict) or not d.get("success") or not isinstance(d.get("result"), dict) or \
            not isinstance(d["result"].get(key), list):
        errs = "; ".join(str(e.get("message") or "") for e in (d.get("errors") or []) if isinstance(e, dict)) \
            if isinstance(d, dict) else ""
        raise ValueError("Cloudflare Radar: unexpected response" + (" (%s)" % _clip(errs, 120) if errs else ""))
    return [x for x in d["result"][key] if isinstance(x, dict)]


def _a2(code):
    code = str(code or "").strip().upper()
    return code if re.match(r"^[A-Z]{2}$", code) else None


def _radar_link(url):
    """The annotation's own public post, else None (internal hosts such as *.cfdata.org are never linked)."""
    m = re.match(r"^https://([A-Za-z0-9.-]+)(?:[/?#]|$)", str(url or "").strip())
    if not m or m.group(1).lower().endswith("cfdata.org") or len(url) > 500:
        return None
    return url.strip()


_RX_ORIGIN = re.compile(r"^[a-z][a-z0-9]{1,20}-[a-z0-9][a-z0-9-]{0,40}$")   # "amazon-me-central-1", "microsoft-uaenorth"


def _origin(slug, name=None):
    slug = str(slug or "").strip().lower()
    return {"slug": slug, "name": _clip(name, 80) or slug} if _RX_ORIGIN.match(slug) else None


def parse_radar_outages(body):
    """/radar/annotations/outages -> annotations {"id", "start", "end", "cause", "type", "desc", "url", "loc": [a2],
    "loc_names": {a2: name}, "asns": [{"asn", "name", "cc"}], "geo": [entity names], "origins": [{"slug", "name"}]
    (1.2: the cloud origins, e.g. "amazon-me-central-1" / "Amazon Web Services me-central-1")}; rows without an id or
    start are skipped."""
    out = []
    for a in _radar_result(body, "annotations"):
        aid, start = str(a.get("id") or "").strip(), wire.parse_time(str(a.get("startDate") or ""))
        if not re.match(r"^\d{1,12}$", aid) or start is None:
            continue
        o = a.get("outage") if isinstance(a.get("outage"), dict) else {}
        desc = re.sub(r"\s+", " ", str(a.get("description") or "")).strip()
        loc = [c for c in (_a2(x) for x in a.get("locations") or []) if c]
        names = {_a2(x.get("code")): str(x.get("name") or "").strip() for x in a.get("locationsDetails") or []
                 if isinstance(x, dict) and _a2(x.get("code"))}
        asns = []
        for x in a.get("asnsDetails") or []:
            if isinstance(x, dict) and re.match(r"^\d{1,10}$", str(x.get("asn") or "")):
                lc = x.get("location") if isinstance(x.get("location"), dict) else {}
                asns.append({"asn": int(x["asn"]), "name": _clip(x.get("name"), 80), "cc": _a2(lc.get("code"))})
                if _a2(lc.get("code")) and lc.get("name"):
                    names.setdefault(_a2(lc.get("code")), str(lc["name"]).strip())
        geo_names = [_clip(e.get("entityName"), 80) for e in a.get("entities") or []
                     if isinstance(e, dict) and e.get("entityType") == "GEOLOCATION" and e.get("entityName")]
        origins, seen = [], set()
        for x in [(d.get("origin"), d.get("name")) for d in a.get("originsDetails") or [] if isinstance(d, dict)] + \
                [(s, None) for s in a.get("origins") or [] if isinstance(s, str)]:
            og = _origin(*x)
            if og and og["slug"] not in seen:
                seen.add(og["slug"])
                origins.append(og)
        out.append({"id": aid, "start": start, "end": wire.parse_time(str(a.get("endDate") or "")),
                    "cause": str(o.get("outageCause") or "UNKNOWN").upper(),
                    "type": str(o.get("outageType") or "").upper() or None,
                    "desc": "" if desc in ("-", "") else desc[:1200], "url": _radar_link(a.get("linkedUrl")),
                    "loc": loc, "loc_names": names, "asns": asns[:12], "geo": geo_names[:12], "origins": origins[:120]})
    return out


def parse_radar_anomalies(body):
    """/radar/traffic_anomalies -> {"id" (uuid), "start", "end", "status", "type" (LOCATION / AS / ORIGIN),
    "loc": {"cc", "name"} | None, "asn": {"asn", "name", "cc", "country"} | None, "outage": annotation id | None,
    "seen": [data sources], "origin": {"slug", "name"} | None (1.2: the cloud region of an ORIGIN anomaly)}."""
    out = []
    for a in _radar_result(body, "trafficAnomalies"):
        uid, start = str(a.get("uuid") or "").strip(), wire.parse_time(str(a.get("startDate") or ""))
        if not re.match(r"^[0-9a-fA-F-]{8,64}$", uid) or start is None:
            continue
        ld = a.get("locationDetails") if isinstance(a.get("locationDetails"), dict) else None
        ad = a.get("asnDetails") if isinstance(a.get("asnDetails"), dict) else None
        od = a.get("originDetails") if isinstance(a.get("originDetails"), dict) else {}
        asn = None
        if ad and re.match(r"^\d{1,10}$", str(ad.get("asn") or "")):
            lc = ad.get("location") if isinstance(ad.get("location"), dict) else {}
            asn = {"asn": int(ad["asn"]), "name": _clip(ad.get("name"), 80), "cc": _a2(lc.get("code")),
                   "country": _clip(lc.get("name"), 60) or None}
        out.append({"id": uid.lower(), "start": start, "end": wire.parse_time(str(a.get("endDate") or "")),
                    "status": str(a.get("status") or "").upper(), "type": str(a.get("type") or "").upper(),
                    "loc": {"cc": _a2(ld.get("code")), "name": _clip(ld.get("name"), 60)} if ld and _a2(ld.get("code"))
                    else None, "asn": asn, "outage": str(a["outageId"]) if a.get("outageId") else None,
                    "seen": [str(s) for s in a.get("visibleInDataSources") or []][:6],
                    "origin": _origin(od.get("origin"), od.get("name"))})
    return out


# ---------------- sources (each returns its new cached data) ----------------

def _body(url, s, fetch, conditional=True):
    """Fetch with the source's validators; None on a 304 (the cached data stands)."""
    hdr = {}
    if conditional and s.get("data") is not None:
        if s.get("etag"):
            hdr["If-None-Match"] = s["etag"]
        if s.get("lm"):
            hdr["If-Modified-Since"] = s["lm"]
    status, rh, body = fetch(url, hdr)
    if status == 304:
        if s.get("data") is None:
            raise ValueError("304 without a cached copy")
        return None
    if status and status >= 400:
        raise urllib.error.HTTPError(url, status, "HTTP %d" % status, None, None)
    if conditional:
        s["etag"], s["lm"] = wire._hget(rh, "ETag"), wire._hget(rh, "Last-Modified")
    return wire._ungzip(body or b"")


def _odin_episodes(cty, hot, nt):
    """County items: one per (FIPS, first UTC day); active while at or over the threshold, ended when it falls below."""
    cty = {k: dict(v) for k, v in (cty or {}).items() if isinstance(v, dict)}
    cur = {ep["fips"]: k for k, ep in cty.items() if ep.get("end") is None}
    for fips, c in hot.items():
        k = cur.get(fips)
        if k is None:
            k = "%s:%s" % (fips, _day(nt))
            ep = cty.get(k) or {"fips": fips, "first": nt, "peak": 0}   # same day: that item resumes
            ep["end"] = None
            cty[k] = ep
        ep = cty[k]
        ep.update(last=nt, n=c["n"], peak=max(ep.get("peak") or 0, c["n"]), utils=c["utils"])
    for fips, k in cur.items():
        if fips not in hot:
            cty[k]["end"] = nt
    return {k: ep for k, ep in cty.items() if ep.get("end") is None or nt - ep["end"] <= ENDED_KEEP}


def _src_odin(fetch, nt, s, st):
    prev = s.get("data") or {}
    body = _body(ODIN_URL, s, fetch)
    agg = parse_odin(body) if body is not None else prev.get("agg")
    if not agg:
        raise ValueError("ODIN: nothing cached")
    geo = st.setdefault("odin_geo", {})
    map_error = prev.get("map_error")
    if any(f not in geo for f in agg["hot"]) and nt - (st.get("odin_map_t") or 0) >= ODIN_MAP_EVERY:
        st["odin_map_t"] = nt
        try:
            status, _h, mb = fetch(ODIN_MAP_URL, {})
            if status and status >= 400:
                raise urllib.error.HTTPError(ODIN_MAP_URL, status, "HTTP %d" % status, None, None)
            geo.update(parse_odin_map(wire._ungzip(mb or b"")))
            map_error = None
        except Exception as e:  # noqa: BLE001  the counties still list, unplaced
            map_error = _err(e)
    return {"agg": agg, "cty": _odin_episodes(prev.get("cty"), agg["hot"], nt), "map_error": map_error, "t": nt}


def _src_rss(url, source):
    def fn(fetch, nt, s, st):
        prev = s.get("data") or {}
        body = _body(url, s, fetch)
        posts = dict(prev.get("posts") or {})
        if body is not None:
            for p in parse_rss(body, source):
                p["t"] = min(p["t"], nt)
                posts[p["id"]] = dict(posts.get(p["id"]) or {}, **p)
        return {"posts": {k: p for k, p in posts.items() if nt - p["t"] <= POST_KEEP}}
    return fn


def _src_tg(key):
    channel = TG_CHANNELS[key]

    def fn(fetch, nt, s, st):
        prev = s.get("data") or {}
        raw, skipped = telegram._get(channel, fetch)
        posts = dict(prev.get("posts") or {})
        for p in raw:
            if p.get("t") is None or not p.get("text"):
                continue
            pid = str(p["id"])
            posts[pid] = {"id": pid, "t": min(int(p["t"]), nt), "text": p["text"][:4000],
                          "url": telegram.POST % (p.get("channel") or channel, p["id"])}
        return {"posts": {k: p for k, p in posts.items() if nt - p["t"] <= POST_KEEP}, "skipped": skipped}
    return fn


def _episode(prev, on, nt, rank, info):
    """A grid condition over polls: {"cur": episode or None, "past": [ended episodes, kept 24 h]}."""
    cur = dict((prev or {}).get("cur") or {}) or None
    past = [dict(e) for e in (prev or {}).get("past") or [] if isinstance(e, dict)]
    if on:
        if cur is None:
            cur = {"start": nt, "peak": rank}
        cur.update(info, last=nt, peak=max(cur.get("peak") or 0, rank))
    elif cur is not None:
        cur["end"] = nt
        past.append(cur)
        cur = None
    return {"cur": cur, "past": [e for e in past if nt - e.get("end", nt) <= ENDED_KEEP]}


_LIGHT_RANK = {"G": 0, "Y": 1, "O": 2, "R": 3, "B": 4}


def _src_taipower(fetch, nt, s, st):
    prev = s.get("data") or {}
    body = _body(TAIPOWER_URL, s, fetch)
    cur = parse_taipower(body) if body is not None else prev.get("cur")
    if not cur:
        raise ValueError("Taipower: nothing cached")
    cur = dict(cur, t=min(cur.get("t") or nt, nt))
    ep = _episode(prev.get("ep"), cur["light"] != "G", nt, _LIGHT_RANK[cur["light"]], dict(cur))
    return {"cur": cur, "ep": ep}


def _src_eskom(fetch, nt, s, st):
    prev = s.get("data") or {}
    status, _h, body = fetch(ESKOM_URL, {})
    if status and status >= 400:
        raise urllib.error.HTTPError(ESKOM_URL, status, "HTTP %d" % status, None, None)
    v = parse_eskom(wire._ungzip(body or b""))
    stage, t = prev.get("stage"), prev.get("t")
    if v is not None:
        stage, t = v, nt
    ep = _episode(prev.get("ep"), bool(stage), nt, stage or 0, {"stage": stage}) if stage is not None else \
        prev.get("ep")
    return {"stage": stage, "t": t, "updating": v is None, "ep": ep}


def _src_caiso(fetch, nt, s, st):
    prev = s.get("data") or {}
    body = _body(CAISO_URL, s, fetch)
    cur = parse_caiso(body) if body is not None else {"current": prev.get("current") or [],
                                                       "upcoming": prev.get("upcoming") or 0}
    hist = {k: dict(v) for k, v in (prev.get("hist") or {}).items() if isinstance(v, dict)}
    seen = set()
    for e in cur["current"]:
        rec = dict(hist.get(e["id"]) or {"first": nt}, **e)
        rec.update(last=nt, gone=None)
        hist[e["id"]] = rec
        seen.add(e["id"])
    for k, rec in hist.items():
        if k not in seen and rec.get("gone") is None:
            rec["gone"] = nt
    hist = {k: r for k, r in hist.items() if r.get("gone") is None or nt - r["gone"] <= ENDED_KEEP}
    return {"current": cur["current"], "upcoming": cur["upcoming"], "hist": hist, "t": nt}


def _src_monitor(fetch, nt, s, st):
    prev = s.get("data") or {}
    body = _body(MONITOR_RU_URL, s, fetch)
    snaps = dict(prev.get("snaps") or {})
    if body is not None:
        for sn in parse_monitor_ru(body):
            if sn["created"] <= nt + 3600:
                sn["created"] = min(sn["created"], nt)
                snaps[str(sn["id"])] = sn
    return {"snaps": {k: v for k, v in snaps.items() if nt - v["created"] <= POST_KEEP}}


def _src_radar(url, parse, key):
    """Cloudflare Radar API: the token in the Authorization header only; the answer replaces the cached list (the
    API is the record; the query's date range covers the window)."""
    def fn(fetch, nt, s, st):
        tok = radar_token()
        if not tok:
            raise NotConfigured("not configured: no Cloudflare Radar token (tools/cfradar-key.sh)")
        status, _h, body = fetch(url, {"Authorization": "Bearer " + tok, "Accept": "application/json"})
        if status and status >= 400:
            raise urllib.error.HTTPError(url, status, "HTTP %d" % status, None, None)
        rows = parse(wire._ungzip(body or b""))
        for r in rows:
            r["start"] = min(r["start"], nt)
        return {key: {r["id"]: r for r in rows}, "t": nt}
    return fn


HANDLERS = {"odin": _src_odin, "netblocks": _src_rss(NETBLOCKS_URL, "netblocks"),
            "cfradar": _src_rss(CFRADAR_URL, "cfradar"), "ukrenergo": _src_tg("ukrenergo"),
            "minenergo": _src_tg("minenergo"), "taipower": _src_taipower, "eskom": _src_eskom, "caiso": _src_caiso,
            "monitor_ru": _src_monitor, "radar_outages": _src_radar(RADAR_OUTAGES_URL, parse_radar_outages, "anns"),
            "radar_anomalies": _src_radar(RADAR_ANOMALIES_URL, parse_radar_anomalies, "anoms")}


def _poll(names, nt, fetch, clock, st):
    """Fetch the due sources among `names` (in order) into st["sources"]; stop after MAX_FAILS failures in a row or
    POLL_BUDGET seconds."""
    srcs = st.setdefault("sources", {})
    t0, fails = clock(), 0
    for name in names:
        _label, _prov, every, retry, slack = SOURCES[name]
        s = srcs.get(name) if isinstance(srcs.get(name), dict) else {}
        srcs[name] = s
        if (s.get("backoff_until") or 0) > nt:
            continue
        if s.get("t") and nt - s["t"] < (every if s.get("ok") else retry) - slack:
            continue
        if fails >= MAX_FAILS or clock() - t0 > POLL_BUDGET:
            break
        try:
            s["data"] = HANDLERS[name](fetch, nt, s, st)
            s.update(ok=True, error=None, good=nt, backoff_until=None)
            fails = 0
        except NotConfigured as e:   # no key set: shown on the row, not a failure in a row
            s.update(ok=False, error=_clip(str(e), 200))
        except Exception as e:  # noqa: BLE001  one source never fails the feed
            s.update(ok=False, error=_err(e))
            if isinstance(e, urllib.error.HTTPError) and e.code in (403, 429):
                s["backoff_until"] = nt + BACKOFF
            fails += 1
        s["t"] = nt
    return srcs


# ---------------- items ----------------

_ABBR = re.compile(r"(?:\b(?:St|Mr|Mrs|Ms|Dr|No|vs|approx|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Inc|Co|"
                   r"Ltd|Corp|Gov|Gen|м|вул|обл|ст|тис|млн|грн)|\b[A-Za-z]|\b[A-Z]\.[A-Z])$")


def _first_sentence(line):
    for m in re.finditer(r"[.!?…]+(?=\s)", line):
        head = line[:m.start()]
        if _ABBR.search(head):
            continue
        rest = line[m.end():].lstrip()
        if rest and (rest[0].isupper() or rest[0].isdigit() or not rest[0].isalnum()):
            return line[:m.end()].strip(), rest
    return line.strip(), ""


_LINKLINE = re.compile(r"https?://|radar\.cloudflare\.com/", re.I)


def title_summary(text):
    """-> (title <= 240: the first sentence or line, summary <= 400: the rest; link-only lines dropped)."""
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    lines = [ln for ln in lines if re.search(r"\w", ln)]
    if not lines:
        return None, None
    first = re.sub(r"^[^\w«\"'(]+", "", lines[0])
    title, rest = _first_sentence(first)
    more = ([rest] if rest else []) + lines[1:]
    more = [ln for ln in more if not (_LINKLINE.search(ln) and len(ln.split()) <= 14)]
    return wire.cut(title, TITLE_MAX), (wire.cut(" ".join(more), ITEM_SUMMARY_MAX) if more else None)


def _mk(feed, source, sid, kind, title, summary, url, ts, nt, provider=None, lang="en", start=None, end=None,
        active=False, severity="info", status=None, regions=(), where=None, cc=(), places=(), place=None, tags=(),
        metric=None):
    ts = min(int(ts), nt)
    places = [p for p in places if p and p.get("ll")]
    it = {"id": "%s:%s:%s" % (feed, source, sid), "source": source, "provider": provider or SOURCES[source][1],
          "kind": kind, "title": wire.cut(title, TITLE_MAX) or "(untitled)",
          "summary": wire.cut(summary, ITEM_SUMMARY_MAX) if summary else None, "lang": lang, "url": url,
          "ts": _iso(ts), "ts_ms": ts * 1000, "start_ms": int(start) * 1000 if start else None,
          "end_ms": int(end) * 1000 if end else None, "active": bool(active), "severity": severity,
          "status": status, "regions": list(regions), "where": where, "cc": list(cc),
          "ll": places[0]["ll"] if places else None, "place": place if places else None, "tags": list(tags),
          "metric": metric, "_places": places}
    return it


def _uniq(xs):
    out = []
    for x in xs:
        if x and x not in out:
            out.append(x)
    return out


def _region_places(codes):
    regs = regions()
    return [{"ll": regs[c]["ll"], "props": {"region": c, "region_name": regs[c]["en"]}} for c in codes if c in regs]


def place_post(text):
    """English post text -> (places, place, where, regions, cc): named oblasts / subjects first, then country
    hashtags, then gt/placer.py's strongest country."""
    plain = _strip_tags(text)
    codes = match_en(plain)
    tag_cc = []
    for tag in re.findall(r"#(\w+)", text or ""):
        cs = placer.place(_split_tag(tag))["countries"]
        if cs and cs[0] not in tag_cc:
            tag_cc.append(cs[0])
    lines = [ln for ln in plain.split("\n") if ln.strip()]
    pl = placer.place(lines[0] if lines else "", " ".join(lines[1:]) or None)["countries"] if lines else []
    cn = countries()
    if codes:
        regs = regions()
        cc = _uniq([_region_a3(c) for c in codes] + tag_cc + pl)
        return (_region_places(codes), "oblast" if codes[0].startswith("UA") else "subject",
                _where(regs[c]["en"] for c in codes), codes, cc)
    picks = [a for a in tag_cc if a in cn][:4] or [a for a in pl[:1] if a in cn]
    cc = _uniq(tag_cc + pl)
    if picks:
        return ([{"ll": cn[a][0]} for a in picks], "country", _where(cn[a][1] for a in picks), [], cc)
    return [], None, (cn[cc[0]][1] if cc and cc[0] in cn else None), [], cc


def _post_sev(text):
    """critical / major / minor from the wording; NetBlocks' ℹ️ and "Note:" posts are info unless they report a
    knocked-out or nationwide loss."""
    t = text or ""
    if _CRIT.search(t):
        return "critical"
    if "ℹ" in t[:6] or re.match(r"^\W*Note\b", t):
        return "info"
    return "major" if _MAJ.search(t) else "minor"


def _where(names, n=5):
    names = _uniq(names)
    return ", ".join(names) if len(names) <= n else "%s and %d more" % (", ".join(names[:n]), len(names) - n)


def rss_items(feed, source, posts, nt, want):
    """Posts of one RSS source -> items of the classes in `want` ("power", "mobile", "internet")."""
    out = []
    for p in (posts or {}).values():
        cls = classify(p["text"], source)
        if cls not in want:
            continue
        title, summary = title_summary(_strip_tags(p["text"]))
        if not title:
            continue
        places, place, where, regs, cc = place_post(p["text"])
        tags = {"power": ["power"], "mobile": ["mobile"], "internet": ["internet"]}[cls]
        out.append(_mk(feed, source, p["id"], "post", title, summary, p["url"], p["t"], nt, start=p["t"],
                       active=nt - p["t"] <= POST_ACTIVE and not _RECOVERED.search(p["text"]),
                       severity=_post_sev(p["text"]), regions=regs, where=where, cc=cc, places=places, place=place,
                       tags=tags))
    return out


def tg_items(source, posts, nt):
    """Ukrenergo / Ministry of Energy posts -> power items (Ukrainian; oblasts placed, else the Ukraine centroid)."""
    out = []
    regs, cn = regions(), countries()
    for p in (posts or {}).values():
        text = telegram.tidy(p.get("text") or "")
        if not text or telegram._SPAM.search(text) or not tg_keep(text):
            continue
        title, summary = title_summary(text)
        if not title:
            continue
        tags = tg_tags(text)
        codes = match_uk(text)
        if codes:
            places, place, where = _region_places(codes), "oblast", _where(regs[c]["en"] for c in codes)
        else:
            places, place, where = [{"ll": cn["UKR"][0]}] if "UKR" in cn else [], "country", "Ukraine"
        sev = "major" if "emergency" in tags else "minor" if "schedule" in tags else "info"
        until = p["t"] + POST_ACTIVE
        if "schedule" in tags and _UK_TOMORROW.search(text):     # tomorrow's schedule: in effect all that day
            until = max(until, kyiv_day_end(p["t"], 1))
        elif "schedule" in tags and _UK_TODAY.search(text):
            until = max(until, kyiv_day_end(p["t"], 0))
        out.append(_mk("power", source, p["id"], "post", title, summary, p["url"], p["t"], nt, lang="uk",
                       start=p["t"], active=nt <= until and tags != ["restored"], severity=sev,
                       regions=codes, where=where, cc=["UKR"], places=places, place=place, tags=tags))
    return out


def _county(fips, geo):
    g = geo.get(fips) or {}
    st2 = STATE_FIPS.get(fips[:2])
    name = g.get("county")
    if name:
        if fips != "11001" and not re.search(r"(?:County|Parish|Borough|Census Area|Municipality|Municipio|city|City)$",
                                              name):
            name += {"22": " Parish", "02": " Borough", "72": " Municipio"}.get(fips[:2], " County")
    else:
        name = "FIPS %s" % fips          # not on ODIN's county map yet
    return ("%s, %s" % (name, st2)) if st2 else name


def odin_items(data, geo, nt):
    out = []
    for k, ep in ((data or {}).get("cty") or {}).items():
        fips, n = ep["fips"], int(ep.get("n") or 0)
        g = geo.get(fips) or {}
        label = _county(fips, geo)
        utils = ep.get("utils") or []
        prov = (utils[0][0].title().replace("Llc", "LLC") if utils else "ODIN")
        active = ep.get("end") is None
        title = ("Power outage: %s customers out in %s" % (_num(n), label)) if active else \
            ("Power outage ended: %s (peak %s customers out)" % (label, _num(ep.get("peak") or n)))
        summ = "Utilities reporting: %s. Peak %s since %s. ODIN covers participating utilities only." % (
            "; ".join("%s %s" % (u.title().replace("Llc", "LLC"), _num(c)) for u, c in utils[:4]) or "unknown",
            _num(ep.get("peak") or n), _iso(ep["first"])[:16].replace("T", " ") + "Z")
        peak = ep.get("peak") or n
        sev = "critical" if peak >= 100000 else "major" if peak >= 5000 else "minor"
        a3 = TERRITORY_A3.get(fips[:2])
        st2 = STATE_FIPS.get(fips[:2])
        out.append(_mk("power", "odin", k, "outage", title, summ, LINK["odin"], ep["last"] if active else ep["end"],
                       nt, provider=prov, start=ep["first"], end=ep.get("end"), active=active, severity=sev,
                       status="in effect" if active else "resolved",
                       regions=(["US-" + st2] if st2 else []) + [fips], where=label,
                       cc=[a3, "USA"] if a3 else ["USA"], places=[{"ll": g["ll"]}] if g.get("ll") else [],
                       place="county", tags=["power", "outage"], metric={"customers": n}))
    return out


def _grid_items(source, data, nt, build):
    out = []
    ep = (data or {}).get("ep") or {}
    for e in ([ep["cur"]] if ep.get("cur") else []) + list(ep.get("past") or []):
        it = build(e, e.get("end") is None)
        if it:
            out.append(it)
    return out


def taipower_items(data, nt):
    cn = countries()

    def build(e, active):
        name, sev = LIGHTS.get(e.get("light"), ("unknown", "minor"))
        worst = [k for k, v in _LIGHT_RANK.items() if v == e.get("peak")]
        wname, wsev = LIGHTS.get(worst[0] if worst else e.get("light"), (name, sev))
        title = ("Taiwan grid: %s light, forecast peak reserve %s %%" % (name, e.get("reserve_pct"))) if active else \
            ("Taiwan grid back to green (was %s)" % wname)
        summ = "Taipower supply/demand: load %s MW (%s %% of capacity), forecast peak reserve %s %% at %s." % (
            _num(e["load_mw"]) if e.get("load_mw") is not None else "?", e.get("util_pct"), e.get("reserve_pct"),
            e.get("peak_hours") or "the peak")
        return _mk("power", "taipower", _stamp(e["start"]), "grid", title, summ, LINK["taipower"],
                   (e.get("t") or e["last"]) if active else e["end"], nt, start=e["start"], end=e.get("end"),
                   active=active, severity=(sev or "minor") if active else (wsev or "minor"),
                   status="in effect" if active else "resolved", regions=["TW"], where="Taiwan", cc=["TWN"],
                   places=[{"ll": cn["TWN"][0]}] if "TWN" in cn else [], place="country", tags=["power", "grid"],
                   metric={"reserve_pct": e.get("reserve_pct"), "load_mw": e.get("load_mw")})
    return _grid_items("taipower", data, nt, build)


def eskom_sev(stage):
    return "critical" if stage >= 6 else "major" if stage >= 3 else "minor"


def eskom_items(data, nt):
    cn = countries()

    def build(e, active):
        stage, peak = int(e.get("stage") or 0), int(e.get("peak") or 0)
        title = ("South Africa: Eskom load shedding stage %d" % stage) if active else \
            ("South Africa: Eskom load shedding suspended (peak stage %d)" % peak)
        return _mk("power", "eskom", _stamp(e["start"]), "grid", title,
                   "Eskom national load-shedding status: stage %d now, stage %d at most since %s." % (
                       stage if active else 0, peak, _iso(e["start"])[:16].replace("T", " ") + "Z"),
                   LINK["eskom"], e["last"] if active else e["end"], nt, start=e["start"], end=e.get("end"),
                   active=active, severity=eskom_sev(stage if active else peak),
                   status="in effect" if active else "resolved", regions=["ZA"], where="South Africa", cc=["ZAF"],
                   places=[{"ll": cn["ZAF"][0]}] if "ZAF" in cn else [], place="country",
                   tags=["power", "load-shedding"], metric={"stage": stage if active else 0})
    return _grid_items("eskom", data, nt, build)


def caiso_sev(typ):
    t = (typ or "").upper()
    if re.search(r"\bEEA\b", t):
        return "minor" if "WATCH" in t else "major"
    if re.search(r"FLEX ALERT|\bRMO\b|RESTRICTED MAINTENANCE", t):
        return "minor"
    return "info"


def caiso_items(data, nt):
    out = []
    for k, e in ((data or {}).get("hist") or {}).items():
        gone = e.get("gone")
        start, end = e.get("start"), e.get("end")
        active = gone is None and (e["in_effect"] if e.get("in_effect") is not None else
                                   bool(start and start <= nt and (end is None or nt <= end)))
        when = "%s to %s" % (_iso(start)[:16].replace("T", " ") + "Z" if start else "?",
                             _iso(end)[11:16] + "Z" if end else "until further notice")
        msg = next((m["text"] for m in e.get("messages") or [] if m.get("text")), None)
        title = "California grid (CAISO): %s%s" % (e.get("type"), " in effect" if active else
                                                     (" ended" if gone else " announced"))
        ts = e.get("updated") or start or e.get("first")
        if gone:
            ts = max(ts or 0, gone)
        if active:
            fin = None                      # the scheduled end is in the summary
        else:
            fin = gone or (end if end and end <= nt else None)
        out.append(_mk("power", "caiso", k, "grid", title, "%s. %s" % (when, msg) if msg else when,
                       LINK["caiso"], ts or nt, nt, start=start, end=fin, active=active,
                       severity=caiso_sev(e.get("type")), status="in effect" if active else
                       ("resolved" if gone else None), regions=["US-CA"], where="California", cc=["USA"],
                       places=[{"ll": CAISO_LL}], place="hq", tags=["power", "grid"]))
    return out


def monitor_items(data, nt):
    regs = regions()
    snaps = sorted(((data or {}).get("snaps") or {}).values(), key=lambda s: (s["created"], s["id"]))
    out = []
    for i, sn in enumerate(snaps):
        newest = i == len(snaps) - 1
        sd, wl = sn.get("shutdown") or [], set(sn.get("whitelist") or [])
        active = newest and nt - sn["created"] <= MONITOR_ACTIVE
        places = [{"ll": regs[c]["ll"], "props": {"region": c, "region_name": regs[c]["en"], "shutdown": True,
                                                  "whitelist": c in wl}} for c in sd if c in regs]
        places.sort(key=lambda p: p["props"]["region"] != "RU-MOW")
        title = "Russia: mobile internet cut in %d region%s, whitelists in %d" % (len(sd), "" if len(sd) == 1 else "s",
                                                                                len(wl))
        summ = ("Na Svyazi «Монитор рунета» map for %s: partial mobile-internet shutdowns reported in %d federal "
                "subjects; in %d of them only whitelisted sites work." % (sn.get("date") or "?", len(sd), len(wl)))
        nxt = snaps[i + 1]["created"] if not newest else None
        out.append(_mk("cellular", "monitor_ru", sn["id"], "shutdown", title, summ, LINK["monitor_ru"], sn["created"],
                       nt, start=_date_noon(sn.get("date"), nt) or sn["created"], end=nxt, active=active,
                       severity="major", status="in effect" if active else None, regions=sd,
                       where="Russia (%d regions)" % len(sd), cc=["RUS"], places=places, place="subject",
                       tags=["mobile", "shutdown"] + (["whitelist"] if wl else []),
                       metric={"shutdown_regions": len(sd), "whitelist_regions": len(wl)}))
    return out


# ---------------- Cloudflare Radar API (1.1) ----------------

RADAR_CAUSE = {"POWER_OUTAGE": "Power outage", "GOVERNMENT_DIRECTED": "Government-directed shutdown",
               "MILITARY_ACTION": "Military action", "CABLE_CUT": "Cable cut", "TECHNICAL_PROBLEM": "Technical problem",
               "NETWORK_PROBLEM": "Network problem", "NATURAL_DISASTER": "Natural disaster", "WEATHER": "Weather",
               "CYBERATTACK": "Cyberattack", "MAINTENANCE": "Maintenance", "FIRE": "Fire", "UNKNOWN": "Cause unknown"}
RADAR_SCOPE = {"NATIONWIDE": "nationwide", "REGIONAL": "regional", "NETWORK": "network level", "PLATFORM": "platform"}
CLASSES = ("power", "mobile", "internet")
# A network name that belongs to a mobile operator (Radar anomalies carry only the network's registry name).
_MOBILE_NET = re.compile(r"(?<![A-Za-z0-9])(?:TELE2|T2|BEE|BEELINE|VIMPELCOM|MEGAFON|MTS|CELCOM(?:NET)?|MAXIS|"
                         r"SAFARICOM|AIRTEL|MTN|VODACOM|VODAFONE|KYIVSTAR|LIFECELL|IRANCELL|RIGHTEL|TURKCELL|JAZZ|"
                         r"ZONG|UFONE|TELENOR|T-MOBILE|ZAIN|OOREDOO)(?![A-Za-z])|MOBILE|WIRELESS|CELLULAR", re.I)


def _cause(c):
    return RADAR_CAUSE.get(c) or str(c or "").replace("_", " ").capitalize() or "Cause unknown"


def radar_class(a):
    """An annotation -> "power", "mobile", "internet" or None (PLATFORM: cloud services, not this module's)."""
    if a.get("type") == "PLATFORM":
        return None
    if a.get("cause") == "POWER_OUTAGE":
        return "power"
    c = classify(a.get("desc") or "", "cfradar")
    return c if c in ("power", "mobile") else "internet"


def anomaly_class(x):
    """A traffic anomaly -> "mobile", "internet" or None (unconfirmed, already an annotation, or a cloud region)."""
    if x.get("status") not in ("VERIFIED", "TP") or x.get("outage"):
        return None
    if x.get("type") == "AS" and x.get("asn"):
        return "mobile" if _MOBILE_NET.search(x["asn"].get("name") or "") else "internet"
    if x.get("type") == "LOCATION" and x.get("loc"):
        return "internet"
    return None


def _country_places(a2s):
    """ISO alpha-2 codes -> ([places], [ISO-3 codes], {a3: name}) at the theatres.json centroids (up to 4 placed)."""
    cn = countries()
    a3s = _uniq(geo.a3_for_a2(c) for c in a2s if c)
    return [{"ll": cn[a][0]} for a in a3s if a in cn][:4], a3s, {a: cn[a][1] for a in a3s if a in cn}


_RADAR_MAJ = re.compile(r"\bnation-?wide\b|\bcomplete\b|\btotal\b|\bnear[- ]total\b", re.I)


def _radar_sev(a):
    if a.get("type") == "NATIONWIDE":
        return "critical"
    if a.get("type") == "REGIONAL":
        return "major"
    d = a.get("desc") or ""
    return "major" if _CRIT.search(d) or _MAJ.search(d) or _RADAR_MAJ.search(d) else "minor"


def _net(name, asn):
    """"izzi telecom (AS28548)" stays as it is; "SALT-CH" -> "SALT-CH (AS15796)"."""
    name = name or "AS%d" % asn
    return name if re.search(r"(?<![0-9])AS ?%d(?![0-9])" % asn, name, re.I) else "%s (AS%d)" % (name, asn)


def radar_outage_items(feed, anns, nt, want=CLASSES):
    """Radar outage annotations -> items of the classes in `want` (the class is also a tag)."""
    out = []
    regs = regions()
    for a in (anns or {}).values():
        cls = radar_class(a)
        if cls not in want:
            continue
        desc = a.get("desc") or ""
        sub = [n.split(",")[0].strip() for n in a.get("geo") or [] if n]
        codes = match_en("; ".join(a.get("geo") or [])) or (match_en(desc) if desc else [])
        nets = [_net(x["name"], x["asn"]) for x in a.get("asns") or []]
        a2s = a.get("loc") or _uniq(x.get("cc") for x in a.get("asns") or [])
        cplaces, cc, cnames = _country_places(a2s)
        if not cc and desc:                      # no country in the record: the description's strongest one
            cn = countries()
            cc = [x for x in placer.place(desc)["countries"][:1] if x in cn]
            cplaces, cnames = [{"ll": cn[x][0]} for x in cc], {x: cn[x][1] for x in cc}
        names = a.get("loc_names") or {}
        country = _where([cnames[x] for x in cc if x in cnames] or [names.get(c) for c in a2s]) or None
        if codes:
            places, place, where = _region_places(codes), "oblast" if codes[0].startswith("UA") else "subject", \
                _where(regs[c]["en"] for c in codes)
            cc = _uniq([_region_a3(c) for c in codes] + cc)
        else:
            places, place = cplaces, "country" if cplaces else None
            if sub and country:
                where = "%s (%s)" % (country, ", ".join(sub[:4]) + (" and %d more" % (len(sub) - 4) if len(sub) > 4
                                                                     else ""))
            elif a.get("type") == "NETWORK" and nets:
                where = ", ".join(nets[:2]) + (" +%d" % (len(nets) - 2) if len(nets) > 2 else "") + \
                    (", " + country if country else "")
            else:
                where = country
        title, rest = title_summary(desc) if desc else (None, None)
        if not title:
            title = "%s: internet outage%s" % (_cause(a.get("cause")), (" in " + where) if where else "")
        elif len(title) < 40 and where and where.lower() not in title.lower():    # "Exam shutdown" -> "... (Iraq)"
            title = "%s (%s)" % (title, where)
        facts = "Cause: %s. Scope: %s." % (_cause(a.get("cause")).lower() if a.get("cause") != "UNKNOWN" else
                                          "not stated", RADAR_SCOPE.get(a.get("type") or "", "not stated"))
        if nets:
            facts += " Networks: %s." % ", ".join(nets[:5])
        end = a.get("end")
        active = end is None or end > nt
        out.append(_mk(feed, "radar_outages", a["id"], "shutdown" if a.get("cause") == "GOVERNMENT_DIRECTED" else
                       "outage", title, " ".join(x for x in (rest, facts) if x), a.get("url") or RADAR_CENTER,
                       end if end and end <= nt else a["start"], nt, start=a["start"], end=end, active=active,
                       severity=_radar_sev(a), status="in effect" if active else "resolved", regions=codes,
                       where=where, cc=cc, places=places, place=place,
                       tags=["radar", cls, (a.get("cause") or "unknown").lower().replace("_", "-")]))
    return out


def radar_anomaly_items(feed, anoms, nt, want=("mobile", "internet")):
    """Radar traffic anomalies -> items of the classes in `want` (unconfirmed and already-annotated ones skipped)."""
    out = []
    for x in (anoms or {}).values():
        cls = anomaly_class(x)
        if cls not in want:
            continue
        seen = ", ".join(x.get("seen") or []) or "traffic"
        if x["type"] == "AS":
            n = x["asn"]
            a2, net = n.get("cc"), _net(n.get("name"), n["asn"])
            places, cc, cnames = _country_places([a2])
            country = (cnames.get(cc[0]) if cc else None) or n.get("country")
            title = "Traffic anomaly on %s%s" % (net, (", " + country) if country else "")
            where, url, sev = net + ((", " + country) if country else ""), RADAR_TRAFFIC % ("as%d" % n["asn"]), "minor"
            what = "from the network %s%s" % (net, (" in " + country) if country else "")
        else:
            a2 = x["loc"]["cc"]
            places, cc, cnames = _country_places([a2])
            country = (cnames.get(cc[0]) if cc else None) or x["loc"].get("name") or a2
            title, where, url, sev = "Traffic anomaly across %s" % country, country, RADAR_TRAFFIC % a2.lower(), "major"
            what = "across %s" % country
        end = x.get("end")
        active = end is None or end > nt
        summ = ("Cloudflare Radar's automatic detection flagged an unusual drop in traffic %s, seen in its %s data "
                "(status %s at Cloudflare; no cause given)." % (what, seen, x["status"]))
        out.append(_mk(feed, "radar_anomalies", x["id"], "outage", title, summ, url, end if end and end <= nt else
                       x["start"], nt, start=x["start"], end=end, active=active, severity=sev,
                       status="in effect" if active else "resolved", where=where, cc=cc, places=places,
                       place="country" if places else None, tags=["radar", "anomaly", cls]))
    return out


def drop_repeats(items, refs, nt):
    """Drop Cloudflare Radar's Bluesky posts that repeat an annotation: a shared country, posted from 6 h before the
    annotation's start to 24 h after its end (or now)."""
    spans = [(set(r["cc"]), r["start_ms"] // 1000 - 6 * 3600, (r["end_ms"] // 1000 if r["end_ms"] else nt) + 86400)
             for r in refs if r["cc"] and r["start_ms"]]
    return [i for i in items if not (i["source"] == "cfradar" and i["kind"] == "post" and i["cc"] and any(
        set(i["cc"]) & c and lo <= i["ts_ms"] // 1000 <= hi for c, lo, hi in spans))]


# ---------------- output ----------------

def _pub(it):
    return {k: v for k, v in it.items() if not k.startswith("_")}


def geojson(feed, items):
    """One Point feature per (item, place): properties = the item minus summary and metric, plus layer and pid
    (and the place's own region / name / shutdown flags)."""
    feats = []
    for it in items:
        props = {k: v for k, v in it.items() if k not in ("summary", "metric") and not k.startswith("_")}
        props.update(layer=feed, pid=it["id"])
        for p in it.get("_places") or []:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": p["ll"]},
                          "properties": dict(props, **(p.get("props") or {}))})
    return {"type": "FeatureCollection", "features": feats}


def window(items, nt):
    """The last 72 h, plus active items up to 30 days old."""
    out = []
    for it in items:
        if nt * 1000 - it["ts_ms"] <= WINDOW * 1000:
            out.append(it)
        elif it["active"] and nt * 1000 - (it["start_ms"] or it["ts_ms"]) <= ACTIVE_MAX * 1000:
            out.append(it)
    return sorted(out, key=lambda i: (-i["ts_ms"], i["id"]))


def _size(x):
    return len(json.dumps(x, separators=(",", ":"), ensure_ascii=False).encode())


def _cap(items, max_items=MAX_ITEMS):
    """Newest-first items -> (kept, dropped count): at most max_items, inactive posts dropped first, then other
    inactive items, then the oldest."""
    order = sorted(items, key=lambda i: (0 if not i["active"] and i["kind"] == "post" else 1 if not i["active"] else 2,
                                         i["ts_ms"]))
    drop = {id(i) for i in order[:max(0, len(items) - max_items)]}
    return [i for i in items if id(i) not in drop], len(drop)


def _rows(names, srcs, per, extra_newest):
    rows = []
    for name in names:
        s = srcs.get(name) or {}
        its = per.get(name) or []
        newest = max((i["ts_ms"] // 1000 for i in its), default=None) or extra_newest.get(name)
        rows.append({"name": name, "label": SOURCES[name][0], "ok": bool(s.get("ok")), "error": s.get("error"),
                     "checked": _iso(s.get("t")), "good": _iso(s.get("good")), "newest": _iso(newest), "n": len(its),
                     "active": sum(1 for i in its if i["active"])})
    return rows


def _finish(feed, items, srcs, extras, summary, extra_newest, also=()):
    """Window, sort, caps, GeoJSON, sources rows -> the contract's data dict."""
    nt = extras.pop("_nt")
    full = window(items, nt)
    kept, trimmed = _cap(full)
    per = {}
    for i in full + list(also):
        per.setdefault(i["source"], []).append(i)
    out = {"version": VERSION, "fetched_at": _iso(nt), "count": len(kept), "trimmed": trimmed,
           "items": [_pub(i) for i in kept], "geojson": geojson(feed, kept),
           "sources": _rows(FEED_SOURCES[feed], srcs, per, extra_newest), "summary": _clip(summary, SUMMARY_MAX),
           "note": NOTE[feed], "attribution": ATTRIBUTION[feed], "public_ok": PUBLIC_OK[feed],
           "non_commercial": NON_COMMERCIAL[feed]}
    out.update(extras)
    while kept and _size(out) > MAX_BYTES:
        kept, extra = _cap(kept, max(0, len(kept) * 9 // 10))
        out.update(items=[_pub(i) for i in kept], geojson=geojson(feed, kept), count=len(kept),
                   trimmed=out["trimmed"] + extra)
    return out


def _data(srcs, name):
    return (srcs.get(name) or {}).get("data")


def _check_answered(feed, srcs):
    names = FEED_SOURCES[feed]
    if not any((srcs.get(n) or {}).get("good") for n in names):
        raise RuntimeError("%s: no source has answered yet: %s" % (feed, "; ".join(
            "%s %s" % (n, (srcs.get(n) or {}).get("error") or "not tried") for n in names)))


def _power_summary(items, grid, us, geo, nt):
    parts = []
    if us:
        hot = sorted((i for i in items if i["source"] == "odin" and i["active"]),
                     key=lambda i: -(i["metric"] or {}).get("customers", 0))
        s = "US (ODIN, participating utilities only): %s customers out" % _num(us["meters_out"])
        s += ("; %d counties at %s+: %s." % (len(hot), _num(ODIN_MIN), "; ".join(
            "%s %s" % (i["where"], _num(i["metric"]["customers"])) for i in hot[:3]))) if hot else \
            "; no county at %s+." % _num(ODIN_MIN)
        parts.append(s)
    ua = [i for i in items if i["source"] in ("ukrenergo", "minenergo") and i["active"]]
    em = [i for i in ua if "emergency" in i["tags"]]
    if em:
        i = em[0]
        parts.append("Ukraine: emergency outages%s (%s, %s)." % (
            (" in " + i["where"]) if i["where"] != "Ukraine" else "", i["provider"], i["ts"][11:16] + "Z"))
    elif any("schedule" in i["tags"] for i in ua):
        parts.append("Ukraine: hourly outage schedules in effect (Ukrenergo).")
    elif ua:
        parts.append("Ukraine: %d grid post%s in the last 6 h." % (len(ua), "" if len(ua) == 1 else "s"))
    tp = grid.get("taipower")
    if tp:
        parts.append("Taiwan: %s light, forecast peak reserve %s %%." % (LIGHTS[tp["light"]][0], tp["reserve_pct"]))
    es = grid.get("eskom")
    if es and es.get("stage") is not None:
        parts.append("South Africa: load shedding stage %d." % es["stage"] if es["stage"] else
                     "South Africa: no load shedding.")
    ca = grid.get("caiso")
    if ca:
        parts.append("California (CAISO): %s." % ((", ".join(ca["names"]) + " in effect") if ca["events"] else
                                                   "no grid emergency notice"))
    rad = [i for i in items if i["source"] == "radar_outages"]
    if rad:
        act = sum(1 for i in rad if i["active"])
        parts.append("Cloudflare Radar: %d internet outage%s caused by power cuts in 72 h%s; newest: %s (%s)." % (
            len(rad), "" if len(rad) == 1 else "s", (", %d still in effect" % act) if act else "",
            _clip(rad[0]["title"], 140), rad[0]["where"] or "place not given"))
    posts = [i for i in items if i["source"] in ("netblocks", "cfradar")]
    if posts:
        parts.append("Power posts by NetBlocks / Cloudflare Radar in 72 h: %d; newest: %s" % (
            len(posts), _clip(posts[0]["title"], 160)))
    return " ".join(parts) or "No power disruption reported by the sources that answered."


def _newest_start(rows):
    return max((r["start"] for r in (rows or {}).values()), default=None)


def radar_rows():
    """The Cloudflare Radar API lists these feeds last stored, for gt/services.py (1.2), which never fetches them:
    {"radar_outages": {"rows": {id: annotation}, "ok", "error", "t", "good"}, "radar_anomalies": {...}} (rows as
    parse_radar_outages / parse_radar_anomalies return them; {} before the first answer). No lock: the state file is
    replaced atomically, and a poll may hold the lock for up to a minute."""
    st = _load()
    srcs = st.get("sources") if isinstance(st.get("sources"), dict) else {}
    out = {}
    for name, key in (("radar_outages", "anns"), ("radar_anomalies", "anoms")):
        s = srcs.get(name) if isinstance(srcs.get(name), dict) else {}
        rows = s["data"].get(key) if isinstance(s.get("data"), dict) else None
        out[name] = {"rows": {k: v for k, v in rows.items() if isinstance(v, dict)} if isinstance(rows, dict) else {},
                     "ok": bool(s.get("ok")), "error": s.get("error"), "t": s.get("t"), "good": s.get("good")}
    return out


def power(now=None, fetch=None, clock=time.monotonic):
    """The `power` feed: US county outages (ODIN), Ukraine's grid posts, Taiwan's reserve light, Eskom load shedding,
    CAISO grid notices, and NetBlocks / Cloudflare Radar posts about power."""
    nt, fetch = _now(now), fetch or _fetch
    with _LOCK:
        st = _load()
        srcs = _poll(FEED_SOURCES["power"], nt, fetch, clock, st)
        st = {"version": VERSION, "sources": srcs, "odin_geo": st.get("odin_geo") or {},
              "odin_map_t": st.get("odin_map_t")}
        _save(st)
    _check_answered("power", srcs)
    geo = st["odin_geo"]
    items = odin_items(_data(srcs, "odin"), geo, nt)
    ro = _data(srcs, "radar_outages") or {}
    refs = radar_outage_items("power", ro.get("anns"), nt)          # every class: the posts' repeat check
    items += [i for i in refs if "power" in i["tags"]]
    posts = []
    for name in ("netblocks", "cfradar"):
        posts += rss_items("power", name, (_data(srcs, name) or {}).get("posts"), nt, ("power",))
    items += drop_repeats(posts, refs, nt)
    for name in ("ukrenergo", "minenergo"):
        items += tg_items(name, (_data(srcs, name) or {}).get("posts"), nt)
    tp, es, ca = _data(srcs, "taipower"), _data(srcs, "eskom"), _data(srcs, "caiso")
    items += taipower_items(tp, nt) + eskom_items(es, nt) + caiso_items(ca, nt)
    cur = (tp or {}).get("cur")
    grid = {"taipower": {"light": cur["light"], "reserve_pct": cur["reserve_pct"], "load_mw": cur["load_mw"],
                         "t": _iso(cur.get("t"))} if cur else None,
            "eskom": {"stage": es["stage"], "t": _iso(es.get("t"))} if es and es.get("stage") is not None else None,
            "caiso": None}
    if ca:
        live = [e for e in (ca.get("hist") or {}).values() if e.get("gone") is None]
        grid["caiso"] = {"events": len(live), "t": _iso(ca.get("t")), "names": [e["type"] for e in live]}
    od = _data(srcs, "odin")
    us = {"meters_out": od["agg"]["meters_out"], "counties": len(od["agg"]["hot"]),
          "utilities": od["agg"]["utilities"], "t": _iso(od.get("t"))} if od and od.get("agg") else None
    wnd = window(items, nt)
    extra_newest = {"odin": (od or {}).get("t"), "taipower": (cur or {}).get("t"), "eskom": (es or {}).get("t"),
                    "caiso": (ca or {}).get("t"), "radar_outages": _newest_start(ro.get("anns"))}
    return _finish("power", items, srcs, {"_nt": nt, "grid": grid, "us": us}, _power_summary(wnd, grid, us, geo, nt),
                   extra_newest)


def cellular(now=None, fetch=None, clock=time.monotonic):
    """The `cellular` feed: mobile-network posts (NetBlocks, Cloudflare Radar), Russia's regional mobile-internet
    shutdown map (Na Svyazi), and the other internet-disruption posts in `internet`."""
    nt, fetch = _now(now), fetch or _fetch
    with _LOCK:
        st = _load()
        srcs = _poll(FEED_SOURCES["cellular"], nt, fetch, clock, st)
        _save({"version": VERSION, "sources": srcs, "odin_geo": st.get("odin_geo") or {},
               "odin_map_t": st.get("odin_map_t")})
    _check_answered("cellular", srcs)
    ro, ra = _data(srcs, "radar_outages") or {}, _data(srcs, "radar_anomalies") or {}
    refs = radar_outage_items("cellular", ro.get("anns"), nt)       # every class: the posts' repeat check
    items = [i for i in refs if "mobile" in i["tags"]] + radar_anomaly_items("cellular", ra.get("anoms"), nt,
                                                                             ("mobile",))
    net = [i for i in refs if "internet" in i["tags"]] + radar_anomaly_items("cellular", ra.get("anoms"), nt,
                                                                             ("internet",))
    for name in ("netblocks", "cfradar"):
        posts = (_data(srcs, name) or {}).get("posts")
        items += drop_repeats(rss_items("cellular", name, posts, nt, ("mobile",)), refs, nt)
        net += drop_repeats(rss_items("cellular", name, posts, nt, ("internet",)), refs, nt)
    mon = _data(srcs, "monitor_ru")
    items += monitor_items(mon, nt)
    net = [_pub(i) for i in window(net, nt)[:INTERNET_MAX]]
    russia = None
    snaps = sorted(((mon or {}).get("snaps") or {}).values(), key=lambda s: (s["created"], s["id"]))
    if snaps:
        sn, regs = snaps[-1], regions()
        wl = set(sn["whitelist"])
        russia = {"date": sn.get("date") or _iso(sn["created"])[:10], "shutdown_regions": len(sn["shutdown"]),
                  "whitelist_regions": len(wl),
                  "regions": [{"code": c, "name": (regs.get(c) or {}).get("en") or c, "shutdown": True,
                               "whitelist": c in wl} for c in sn["shutdown"]]}
    wnd = window(items, nt)
    parts = []
    if russia:
        parts.append("Russia (Na Svyazi map of %s): mobile internet cut in %d regions, whitelists in %d." % (
            russia["date"], russia["shutdown_regions"], russia["whitelist_regions"]))
    rad = [i for i in wnd if i["source"] in ("radar_outages", "radar_anomalies")]
    if rad:
        act = sum(1 for i in rad if i["active"])
        parts.append("Cloudflare Radar: %d mobile-network outage%s or confirmed traffic anomal%s in 72 h%s; newest: "
                     "%s." % (len(rad), "" if len(rad) == 1 else "s", "y" if len(rad) == 1 else "ies",
                              (", %d still in effect" % act) if act else "", _clip(rad[0]["title"], 140)))
    mob = [i for i in wnd if i["kind"] == "post"]
    parts.append("Mobile-network posts by NetBlocks / Cloudflare Radar in 72 h: %d%s." % (
        len(mob), ("; newest: " + _clip(mob[0]["title"], 160)) if mob else ""))
    parts.append("Other internet disruptions in 72 h (posts and Radar records): %d (Internet group)." % len(net))
    extra_newest = {"monitor_ru": snaps[-1]["created"] if snaps else None,
                    "radar_outages": _newest_start(ro.get("anns")), "radar_anomalies": _newest_start(ra.get("anoms"))}
    return _finish("cellular", items, srcs, {"_nt": nt, "russia": russia, "internet": net}, " ".join(parts),
                   extra_newest, also=net)


FEEDS = {
    "power": (power, 300),
    "cellular": (cellular, 300),
}
