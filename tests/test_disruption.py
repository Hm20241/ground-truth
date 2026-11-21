"""Offline tests for 1.5.3: the power and cell-network layers (gt/disruption.py, feeds `power` and `cellular`).
Sockets are blocked; nothing touches the network. Fixtures in tests/fixtures/disruption/, all fetched once on
2026-11-20/21 and trimmed, except the four marked SYNTHETIC:
  odin_cty.json        ODIN county view (odi?format=JSON&view=county): 14 of 77 rows, incl. the three counties at 500+
  odin_map.json        ODIN county map (odi/map?scale=COUNTY): 3 of 75 entries (Lucas OH, Los Angeles CA, Montgomery
                       PA); Harris TX is left out on purpose (a county over the threshold that has no geometry yet)
  netblocks.xml        NetBlocks Mastodon RSS: header + 8 of 20 items (the channel's handle line replaced)
  cfradar.xml          Cloudflare Radar Bluesky RSS: header + 9 of 30 items (power, mobile, internet and trivia posts)
  ukrenergo.html       t.me/s/Ukrenergo: 5 of 19 post blocks (two feature posts, an emergency post, an update, a
                       schedule post); data-view attributes and image URLs stripped
  minenergo.html       t.me/s/energyofukraine: 3 of 14 post blocks (an aid post, two supply posts), stripped the same way
  taipower.json, eskom.txt, caiso.json, monitor_ru.json   the real bodies as fetched (Taipower green light; Eskom "1"
                       = no load shedding; CAISO with no event; Na Svyazi's snapshot 493 of 2026-11-20, whole)
  ukrenergo_emergency_synthetic.html   SYNTHETIC: the 5657 block with a new id, time and text naming three oblasts in
                       three case forms (Львівщині, Волинській області, Київській області) plus the city (Києві)
  taipower_orange_synthetic.json       SYNTHETIC: the real body with an orange light (5.2 % reserve)
  eskom_stage4_synthetic.txt           SYNTHETIC: "5" (stage 4)
  caiso_eea_synthetic.json             SYNTHETIC: an EEA 2 event in August (Pacific daylight time), shaped like the
                       ActiveEvents fields read by CAISO's own Today's Outlook page

Run: python3 -I tests/test_disruption.py
"""
import datetime as dt
import gzip
import json
import os
import re
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "disruption")
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def _blocked(*a, **k):
    raise AssertionError("network use in an offline test")


from gt import disruption as ds  # noqa: E402
from gt import extfeeds, telegram  # noqa: E402

socket.socket.connect = _blocked          # after the import: ssl subclasses socket.socket
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
ds.urllib.request.urlopen = _blocked
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def raises(fn, exc, text=""):
    try:
        fn()
    except exc as e:
        return text in str(e)
    return False


RAW = {n: open(os.path.join(FX, n), "rb").read() for n in sorted(os.listdir(FX))}
J = {n: json.loads(b) for n, b in RAW.items() if n.endswith(".json")}
UE_PAGE, ME_PAGE = telegram.PAGE % "Ukrenergo", telegram.PAGE % "energyofukraine"
URLS = {ds.ODIN_URL: "odin_cty.json", ds.ODIN_MAP_URL: "odin_map.json", ds.NETBLOCKS_URL: "netblocks.xml",
        ds.CFRADAR_URL: "cfradar.xml", ds.TAIPOWER_URL: "taipower.json", ds.ESKOM_URL: "eskom.txt",
        ds.CAISO_URL: "caiso.json", ds.MONITOR_RU_URL: "monitor_ru.json", UE_PAGE: "ukrenergo.html",
        ME_PAGE: "minenergo.html"}
ETAGS = {ds.TAIPOWER_URL: '"tp-1"'}
NOW = dt.datetime(2026, 11, 21, 9, 0, tzinfo=dt.timezone.utc)
NT = int(NOW.timestamp())
SIZE = lambda x: len(json.dumps(x, separators=(",", ":"), ensure_ascii=False).encode())
ISO = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
T = lambda *a: int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())
TAG = re.compile(r"<[A-Za-z/!][^>]*>|&(?:amp|lt|gt|quot|nbsp|#\d+);")
BASE = {"version", "fetched_at", "count", "trimmed", "items", "geojson", "sources", "summary", "note", "attribution",
        "public_ok", "non_commercial"}
ITEM = {"id", "source", "provider", "kind", "title", "summary", "lang", "url", "ts", "ts_ms", "start_ms", "end_ms",
        "active", "severity", "status", "regions", "where", "cc", "ll", "place", "tags", "metric"}
SRC = {"name", "label", "ok", "error", "checked", "good", "newest", "n", "active"}
PLACE_PROPS = {"region", "region_name", "shutdown", "whitelist"}


def reset():
    p = os.path.join(TMP, "cache", ds.STATE_FILE)
    if os.path.exists(p):
        os.remove(p)


def state():
    return json.load(open(os.path.join(TMP, "cache", ds.STATE_FILE), encoding="utf-8"))


def fake(over=None, fail=(), log=None):
    """Serves fixtures by URL. over: url -> bytes; fail: urls that raise (a dict url -> HTTP code raises that code);
    log: list of (url, request headers). Taipower answers 304 to its own ETag."""
    over = over or {}

    def fetch(url, headers):
        if log is not None:
            log.append((url, dict(headers or {})))
        if url in fail:
            code = fail.get(url) if isinstance(fail, dict) else None
            if code:
                raise urllib.error.HTTPError(url, code, "HTTP %d" % code, None, None)
            raise OSError("connection refused (test)")
        tag = ETAGS.get(url)
        if tag and url not in over and (headers or {}).get("If-None-Match") == tag:
            return 304, {"ETag": tag}, b""
        return 200, ({"ETag": tag} if tag else {}), over[url] if url in over else RAW[URLS[url]]
    return fetch


def urls(log):
    return [u for u, _h in log]


def by_id(d):
    return {i["id"]: i for i in d["items"]}


def feats(d, pid):
    return [f for f in d["geojson"]["features"] if f["properties"]["pid"] == pid]


def odin_variant(**counts):
    """The real ODIN rows with metersAffected changed per FIPS (f39095=300), as bytes."""
    d = json.loads(RAW["odin_cty.json"])
    for r in d["outage"]:
        k = "f" + r["communityDescriptor"]
        if k in counts:
            r["metersAffected"] = counts[k]
    return json.dumps(d).encode()


def rss_redate(name, needle, date):
    """The real RSS with one item's pubDate replaced (the item that contains `needle`)."""
    x = RAW[name].decode("utf-8")
    items = re.findall(r"(?s)<item>.*?</item>", x)
    it = [i for i in items if needle in i][0]
    return x.replace(it, re.sub(r"<pubDate>[^<]*</pubDate>", "<pubDate>%s</pubDate>" % date, it)).encode()


def post_text(name, source, needle):
    return [p["text"] for p in ds.parse_rss(RAW[name], source) if needle in p["text"]][0]


def tg_posts(name, channel):
    return {p["id"]: telegram.tidy(p["text"]) for p in telegram.parse_page(RAW[name], channel)[0]}


# ---------------- module surface ----------------

check(set(ds.FEEDS) == {"power", "cellular"} and all(e == 300 for _f, e in ds.FEEDS.values()),
      "FEEDS: power and cellular, every 300 s")
check(ds.PUBLIC_OK == {"power": False, "cellular": False} and ds.NON_COMMERCIAL == {"power": True, "cellular": True},
      "PUBLIC_OK False and NON_COMMERCIAL True for both feeds")
check("disruption" in extfeeds.ALL and "disruption" in extfeeds.ENABLED, "extfeeds lists and enables the module")
check(ds.UA == "GroundTruth/1.5 (personal non-commercial OSINT dashboard)", "the contract's User-Agent")
check(ds.STATE_FILE == "disruption_state.json" and ds.CACHE == os.path.join(TMP, "cache"),
      "state lives in <GT_DATA>/cache/disruption_state.json")

# ---------------- classifier ----------------

NB, CF = "netblocks.xml", "cfradar.xml"
check(ds.classify(post_text(NB, "netblocks", "much of #Ukraine"), "netblocks") == "power",
      "classify: NetBlocks Ukraine connectivity post naming power cuts -> power")
check(ds.classify(post_text(CF, "cfradar", "600,000"), "cfradar") == "power",
      "classify: Radar strikes on energy infrastructure (Dnipropetrovsk) -> power")
check(ds.classify(post_text(CF, "cfradar", "WEB Aruba"), "cfradar") == "power", "classify: Aruba blackout -> power")
check(ds.classify(post_text(CF, "cfradar", "Orange (AS3215)"), "cfradar") == "mobile",
      "classify: Orange (AS3215) mobile network outage -> mobile")
check(ds.classify(post_text(CF, "cfradar", "Digicel (AS27653), t"), "cfradar") == "mobile",
      "classify: Digicel, Haiti's largest mobile operator -> mobile")
check(ds.classify(post_text(CF, "cfradar", "Salt (AS15796)"), "cfradar") == "internet",
      "classify: Salt fixed-line disruption -> internet")
check(ds.classify(post_text(CF, "cfradar", "Chukotka"), "cfradar") == "internet",
      "classify: Russia's Far East disruptions -> internet")
check(ds.classify(post_text(NB, "netblocks", "#Pakistan"), "netblocks") == "internet",
      "classify: NetBlocks Pakistan cable decline -> internet")
for needle in ("GTAVI", "redesign", ".si domains"):
    check(ds.classify(post_text(CF, "cfradar", needle), "cfradar") is None,
          "classify: Radar trivia dropped (%s)" % needle)
check(ds.classify("Radar shows a new record for HTTP/3 adoption.", "netblocks") == "internet" and
      ds.classify("Radar shows a new record for HTTP/3 adoption.", "cfradar") is None,
      "classify: NetBlocks posts default to internet, Radar posts with no match are dropped")
check(ds.classify("Power cuts knocked out mobile service across Gaza.") == "power",
      "classify: power wins over mobile")
check(ds.classify("MegaFon subscribers lost 4G in Belgorod.") == "mobile" and
      ds.classify("Mobile internet was cut in Dagestan.") == "mobile" and
      ds.classify("Traffic from operator Kcell (AS29355) fell by half.") == "mobile",
      "classify: operator names, 3G/4G/5G and 'operator (ASnnnn)' -> mobile")
check(ds.classify("The party came to power after the vote; connectivity was restricted.") == "internet",
      "classify: political 'came to power' is not an electricity post")
check(ds.classify("The mts.ru website is down for some users", "cfradar") is None,
      "classify: an operator name must stand alone (not inside a host name)")

# ---------------- oblast / subject matching ----------------

check(ds.match_en("Kyiv Oblast and Kyiv") == ["UA-32", "UA-30"] and ds.match_en("in Kyiv region") == ["UA-32"],
      "match_en: Kyiv Oblast (UA-32) vs Kyiv city (UA-30)")
check(ds.match_en("Moscow Oblast, Moscow") == ["RU-MOS", "RU-MOW"], "match_en: Moscow Oblast vs Moscow city")
check(ds.match_en(post_text(CF, "cfradar", "Chukotka")) == ["RU-CHU", "RU-MAG", "RU-KAM", "RU-SAK"],
      "match_en: Chukotka, Magadan Oblast, Kamchatka, Sakhalin Oblast")
check(ds.match_en("Vladimir Putin spoke; Jewish groups met") == [] and
      ds.match_en("in Vladimir Oblast and the Jewish Autonomous Oblast") == ["RU-VLA", "RU-YEV"],
      "match_en: 'Vladimir' and 'Jewish' need their suffix")
check(ds.match_en("Altai Republic and Altai Krai") == ["RU-AL", "RU-ALT"], "match_en: the two Altais")
check(ds.match_en(post_text(NB, "netblocks", "Sevastopol")) == ["UA-43", "UA-40"],
      "match_en: occupied Crimea and Sevastopol are Ukrainian codes")
check(ds.match_en("St. Petersburg and Odessa and Zaporizhzhia") == ["RU-SPE", "UA-51", "UA-23"],
      "match_en: alternative spellings")
for word in ("Львівська область", "у Львівській області", "Львівщини", "Львівщина", "на Львівщині", "Львові"):
    check(ds.match_uk(word) == ["UA-46"], "match_uk: %s -> Lviv" % word)
check(ds.match_uk("Київська область; м. Київ") == ["UA-32", "UA-30"] and ds.match_uk("на Київщині") == ["UA-32"] and
      ds.match_uk("у Києві") == ["UA-30"] and ds.match_uk("Київської міської влади") == ["UA-30"],
      "match_uk: Kyiv Oblast (UA-32) vs Kyiv city (UA-30)")
check(ds.match_uk("з 07:00 за київським часом") == [], "match_uk: 'київським часом' is a time zone, not a place")
check(ds.match_uk("на Харківщині, на Сумщині, Дніпровщині, Полтавщині, по Одесі, по Запоріжжю") ==
      ["UA-63", "UA-59", "UA-12", "UA-53", "UA-51", "UA-23"], "match_uk: -щина forms and city names")
check(ds.match_uk("Донеччина, Вінниччина, Закарпатській") == ["UA-14", "UA-05", "UA-21"],
      "match_uk: -ччина forms and Zakarpattia")
syn = list(tg_posts("ukrenergo_emergency_synthetic.html", "Ukrenergo").values())[0]
check(ds.match_uk(syn) == ["UA-46", "UA-07", "UA-32", "UA-30"],
      "match_uk: synthetic post, three case forms + the city, in order of mention")
REG = ds.regions()
GEO = json.load(open(os.path.join(PROJ, "web", "geo", "alert-regions.json"), encoding="utf-8"))
RINGS = {f["id"]: ds._largest(f["geometry"]) for f in GEO["features"]}
check(len(REG) == 110 and sum(1 for r in REG.values() if r["c"] == "UA") == 27, "regions: 27 oblasts + 83 subjects")
check(all(ds._inside(r["ll"][0], r["ll"][1], RINGS[c]) for c, r in REG.items() if c not in ds.CITY_LL),
      "regions: every centroid lies inside its own region")
check(not ds._inside(REG["UA-32"]["ll"][0], REG["UA-32"]["ll"][1], RINGS["UA-30"]) and
      not ds._inside(REG["RU-MOS"]["ll"][0], REG["RU-MOS"]["ll"][1], RINGS["RU-MOW"]),
      "regions: Kyiv Oblast and Moscow Oblast points are outside the cities they surround")
check(REG["UA-30"]["ll"] == ds.CITY_LL["UA-30"] and REG["RU-MOW"]["ll"] == ds.CITY_LL["RU-MOW"] and
      REG["RU-CHU"]["ll"][0] > 160, "regions: city centres, and Chukotka not pulled across the antimeridian")
check(REG["UA-51"]["en"] == "Odesa" and REG["RU-ALT"]["en"] == "Altai Krai", "regions: English display names")

# ---------------- Telegram keep rules and tags ----------------

UE, ME = tg_posts("ukrenergo.html", "Ukrenergo"), tg_posts("minenergo.html", "energyofukraine")
check(set(UE) == {5641, 5654, 5657, 5658, 5659} and set(ME) == {8334, 8340, 8345}, "Telegram fixtures parse")
check(not ds.tg_keep(UE[5641]) and not ds.tg_keep(UE[5654]) and not ds.tg_keep(ME[8334]),
      "tg_keep: video feature, investment conference and aid posts dropped")
check(all(ds.tg_keep(UE[k]) for k in (5657, 5658, 5659)) and ds.tg_keep(ME[8340]) and ds.tg_keep(ME[8345]),
      "tg_keep: emergency, update, schedule and supply posts kept")
check("emergency" in ds.tg_tags(UE[5657]) and "schedule" in ds.tg_tags(UE[5659]) and
      "emergency" not in ds.tg_tags(UE[5659]), "tg_tags: emergency vs schedule")
check(ds.tg_tags("Аварійно-ремонтні бригади працюють") == [] and
      ds.tg_tags("Електропостачання відновлено у Львові") == ["restored"],
      "tg_tags: repair crews are not 'emergency'; restored")
check(ds.tg_keep("Через ворожу атаку на підстанцію внаслідок пошкоджень є знеструмлення.") and
      not ds.tg_keep("Дякуємо партнерам за пакет допомоги для енергетиків."), "tg_keep: attack consequences vs thanks")

# ---------------- parsers ----------------

check(ds.roc_time("115.11.21(六)12:40") == T(2026, 11, 21, 4, 40) and
      ds.roc_time("115.08.04(二)14:30") == T(2026, 8, 4, 6, 30) and ds.roc_time("2026.11.21 03:56") ==
      T(2026, 11, 20, 19, 56) and ds.roc_time("soon") is None, "roc_time: ROC year + 1911, Taiwan time UTC+8")
tp = ds.parse_taipower(RAW["taipower.json"])
check(tp == {"light": "G", "reserve_pct": 20.4, "load_mw": 26699, "util_pct": 65.0, "peak_hours": "17:00-19:00",
             "t": T(2026, 11, 21, 4, 40)}, "parse_taipower: green, 20.4 %, curr_load x 10 MW, publish time")
tpo = ds.parse_taipower(RAW["taipower_orange_synthetic.json"])
check(tpo["light"] == "O" and tpo["reserve_pct"] == 5.2 and tpo["load_mw"] == 38105, "parse_taipower: orange")
check(raises(lambda: ds.parse_taipower(b'{"records":[{"fore_peak_resv_indicator":"Q"}]}'), ValueError, "light"),
      "parse_taipower: an unknown light raises")
check([ds.parse_eskom(b) for b in (b"1", b"2", b"5", b"9", b'"3"', b"99", b"0", b"-1", b"1\r\n")] ==
      [0, 1, 4, 8, 2, None, None, None, 0], "parse_eskom: stage = value - 1; 99 / out of range = updating (None)")
check(raises(lambda: ds.parse_eskom(b"<html>maintenance</html>"), ValueError), "parse_eskom: a non-number raises")
check([ds.eskom_sev(s) for s in (1, 2, 3, 5, 6, 8)] == ["minor", "minor", "major", "major", "critical", "critical"],
      "eskom severity: 1-2 minor, 3-5 major, 6+ critical")
check(ds.pt_time("2026-08-20T16:00:00") == T(2026, 8, 20, 23, 0) and ds.pt_time("2026-12-01T16:00:00") ==
      T(2026, 12, 2, 0, 0), "pt_time: PDT is UTC-7, PST is UTC-8")
check(ds.pt_time("2026-03-08T01:59:00") == T(2026, 3, 8, 9, 59) and ds.pt_time("2026-03-08T03:00:00") ==
      T(2026, 3, 8, 10, 0) and ds.pt_time("2026-11-01T00:30:00") == T(2026, 11, 1, 7, 30) and
      ds.pt_time("2026-11-01T02:30:00") == T(2026, 11, 1, 10, 30), "pt_time: the 2026 DST switches (Mar 8, Nov 1)")
check(ds.pt_time("2026-08-20T16:00:00-07:00") == T(2026, 8, 20, 23, 0) and ds.pt_time("") is None and
      ds.pt_time(None) is None, "pt_time: an explicit offset is honoured; empty -> None")
check([ds.caiso_sev(t) for t in ("EEA 2", "EEA Watch", "Flex Alert", "RMO", "Transmission Emergency")] ==
      ["major", "minor", "minor", "minor", "info"], "CAISO severity: EEA major, Watch / Flex Alert / RMO minor")
cev = ds.parse_caiso(RAW["caiso_eea_synthetic.json"])["current"][0]
check(cev["id"] == "4321" and cev["type"] == "EEA 2" and cev["start"] == T(2026, 8, 20, 23, 0) and
      cev["end"] == T(2026, 8, 21, 4, 0) and cev["updated"] == T(2026, 8, 20, 22, 45) and
      "<" not in cev["messages"][0]["text"], "parse_caiso: Pacific times to UTC, message HTML stripped")
check(ds.parse_caiso(RAW["caiso.json"]) == {"current": [], "upcoming": 0}, "parse_caiso: the real empty answer")
rows = J["odin_cty.json"]["outage"]
od = ds.parse_odin(RAW["odin_cty.json"])
check(set(od["hot"]) == {"39095", "48201", "06037"} and od["hot"]["39095"]["n"] == 5410 and
      od["meters_out"] == sum(r["metersAffected"] for r in rows) and od["rows"] == 14 and
      od["utilities"] == len({r["names"][0]["name"] for r in rows}), "parse_odin: counties at 500+, totals")
agg = json.loads(RAW["odin_cty.json"])
extra = dict(agg["outage"][3], metersAffected=100, names=[{"name": "SECOND UTILITY CO", "nameType": "UtilityName"}])
agg["outage"].append(extra)
od2 = ds.parse_odin(json.dumps(agg).encode())
check(od2["hot"].get("36025", {}).get("n") == 539 and len(od2["hot"]["36025"]["utils"]) == 2 and
      od2["hot"]["36025"]["utils"][0][1] == 439, "parse_odin: utilities summed per county (439 + 100 crosses 500)")
check("36025" not in od["hot"] and od2["utilities"] == od["utilities"] + 1, "parse_odin: 439 alone stays under")
om = ds.parse_odin_map(RAW["odin_map.json"])
check(set(om) == {"39095", "06037", "42091"} and om["39095"]["county"] == "Lucas" and
      -83.89 < om["39095"]["ll"][0] < -82.99 and 41.41 < om["39095"]["ll"][1] < 41.96,
      "parse_odin_map: county centroids inside the county's envelope")
check(-119.0 < om["06037"]["ll"][0] < -117.6 and 33.6 < om["06037"]["ll"][1] < 34.9,
      "parse_odin_map: Los Angeles (MultiPolygon) placed on the mainland, not the islands")
mr = ds.parse_monitor_ru(RAW["monitor_ru.json"])
raw_sd = J["monitor_ru.json"]["data"][0]["map_state"]["shutdowns"]["regions"]
check(len(mr) == 1 and mr[0]["id"] == 493 and mr[0]["date"] == "2026-11-19" and
      mr[0]["created"] == T(2026, 11, 20, 9, 56, 58), "parse_monitor_ru: snapshot 493 of 2026-11-19")
check(len(raw_sd) > 100 and len(mr[0]["shutdown"]) == 66 and len(mr[0]["whitelist"]) == 65 and
      set(mr[0]["whitelist"]) <= set(mr[0]["shutdown"]), "parse_monitor_ru: regions de-duplicated (66 / 65)")
check(raises(lambda: ds.parse_monitor_ru(b'{"status":"error","data":[]}'), ValueError), "parse_monitor_ru: error")
nbp, cfp = ds.parse_rss(RAW[NB], "netblocks"), ds.parse_rss(RAW[CF], "cfradar")
check(len(nbp) == 8 and len(cfp) == 9 and all(re.match(r"^\d+$", p["id"]) for p in nbp) and
      all(p["url"].startswith("https://bsky.app/profile/radar.cloudflare.com/post/") for p in cfp),
      "parse_rss: Mastodon status ids, Bluesky post links")
check(not any(TAG.search(p["text"]) for p in nbp + cfp), "parse_rss: descriptions become plain text")
title, summ = ds.title_summary(ds._strip_tags(post_text(NB, "netblocks", "much of #Ukraine")))
check(title == "Confirmed: Metrics show declines in internet connectivity across much of Ukraine." and summ and
      "#" not in summ and "http" not in summ, "title_summary: first sentence; the rest without hashtags or links")
title, summ = ds.title_summary("Traffic in St. Petersburg fell. More later.")
check(title == "Traffic in St. Petersburg fell." and summ == "More later.", "title_summary: abbreviations")

# ---------------- placement of posts ----------------

pl = ds.place_post(post_text(NB, "netblocks", "Sevastopol"))
check(pl[3] == ["UA-43", "UA-40"] and pl[1] == "oblast" and len(pl[0]) == 2 and pl[4][0] == "UKR",
      "place_post: Crimea + Sevastopol -> two oblast points")
pl = ds.place_post(post_text(CF, "cfradar", "Chukotka"))
check(pl[1] == "subject" and len(pl[0]) == 4 and pl[0][0]["ll"] == REG["RU-CHU"]["ll"] and pl[4] == ["RUS"],
      "place_post: four Russian subjects -> four subject points")
pl = ds.place_post(post_text(NB, "netblocks", "#Iraq"))
check(pl[1] == "country" and pl[2] == "Iraq, Jordan" and len(pl[0]) == 2, "place_post: two country hashtags")
pl = ds.place_post(post_text(CF, "cfradar", "WEB Aruba"))
check(pl[1] == "country" and pl[4][0] == "ABW" and pl[0][0]["ll"] == ds.countries()["ABW"][0],
      "place_post: placer's country at its centroid")
pl = ds.place_post(post_text(NB, "netblocks", "Apple"))
check(pl[0] == [] and pl[1] is None, "place_post: nothing to place -> listed, not pinned")

# ---------------- scenario 1: both feeds, every source once ----------------

reset()
log = []
p1 = ds.power(now=NOW, fetch=fake(log=log))
c1 = ds.cellular(now=NOW, fetch=fake(log=log))
U = urls(log)
check(U.count(ds.NETBLOCKS_URL) == 1 and U.count(ds.CFRADAR_URL) == 1,
      "one fetch of each shared RSS serves both feeds")
check(sorted(U) == sorted(URLS), "first poll: every source fetched once, ODIN map once (unknown counties)")
check(set(p1) == BASE | {"grid", "us"} and set(c1) == BASE | {"russia", "internet"},
      "data dict keys exactly as the contract (power + grid/us, cellular + russia/internet)")
ALL_ITEMS = p1["items"] + c1["items"] + c1["internet"]
check(all(set(i) == ITEM for i in ALL_ITEMS), "item keys exactly as the contract")
check(all(set(s) == SRC for s in p1["sources"] + c1["sources"]) and
      [s["name"] for s in p1["sources"]] == list(ds.FEED_SOURCES["power"]) and
      [s["name"] for s in c1["sources"]] == list(ds.FEED_SOURCES["cellular"]), "sources rows: keys and order")
check(all(s["ok"] and s["error"] is None and s["checked"] == ISO(NT) for s in p1["sources"] + c1["sources"]),
      "all sources ok")
check(p1["version"] == c1["version"] == "1.0" and p1["fetched_at"] == ISO(NT) and p1["public_ok"] is False and
      c1["non_commercial"] is True and p1["count"] == len(p1["items"]) and p1["trimmed"] == 0,
      "version, fetched_at, count, trimmed, flags")
check(all(i["ts_ms"] <= NT * 1000 for i in ALL_ITEMS) and
      all(a["ts_ms"] >= b["ts_ms"] for d in (p1, c1) for a, b in zip(d["items"], d["items"][1:])),
      "never a future item; newest first")
check(all(NT - i["ts_ms"] // 1000 <= ds.WINDOW or i["active"] for i in ALL_ITEMS), "window: 72 h plus active")
check(all(re.match(r"^[A-Za-z0-9_.:-]{1,160}$", i["id"]) for i in ALL_ITEMS) and
      len({i["id"] for i in ALL_ITEMS}) == len(ALL_ITEMS), "ids unique and fit the translation job's pattern")
check(all(i["id"].startswith("power:" + i["source"] + ":") for i in p1["items"]) and
      all(i["id"].startswith("cellular:" + i["source"] + ":") for i in c1["items"] + c1["internet"]),
      "ids are <feed>:<source>:<stable id>")
check(not any(TAG.search(i["title"] or "") or TAG.search(i["summary"] or "") for i in ALL_ITEMS) and
      all(len(i["title"]) <= 240 and len(i["summary"] or "") <= 400 for i in ALL_ITEMS) and
      len(p1["summary"]) <= 700 and len(c1["summary"]) <= 700, "no HTML; title / summary lengths")
check(all(i["severity"] in ds.SEV_RANK and i["status"] in ("investigating", "identified", "monitoring", "resolved",
                                                             "in effect", None) and
          i["kind"] in ("status", "news", "grid", "outage", "shutdown", "post") and
          i["place"] in ("region", "pop", "hq", "country", "county", "oblast", "subject", None) and
          (i["ll"] is None) == (i["place"] is None) for i in ALL_ITEMS), "enums: severity, status, kind, place")
json.dumps(p1, allow_nan=False), json.dumps(c1, allow_nan=False)
check(SIZE(p1) < ds.MAX_BYTES and SIZE(c1) < ds.MAX_BYTES, "both feeds under 300 KB")

P1 = by_id(p1)
lu, ha, la = P1["power:odin:39095:20261121"], P1["power:odin:48201:20261121"], P1["power:odin:06037:20261121"]
check(lu["title"] == "Power outage: 5,410 customers out in Lucas County, OH" and lu["metric"] == {"customers": 5410}
      and lu["place"] == "county" and lu["cc"] == ["USA"] and lu["active"] and lu["start_ms"] == NT * 1000 and
      lu["end_ms"] is None and lu["kind"] == "outage" and lu["status"] == "in effect" and lu["severity"] == "major",
      "ODIN: Lucas County item (title, metric, county place, start)")
check(lu["regions"] == ["US-OH", "39095"] and lu["provider"] == "The Toledo Edison Co" and
      "participating utilities only" in lu["summary"], "ODIN: regions, utility as provider, coverage caveat")
check(ha["ll"] is None and ha["where"] == "FIPS 48201, TX" and feats(p1, ha["id"]) == [] and la["ll"] is not None,
      "ODIN: a county missing from the map is listed but not pinned")
check(sum(1 for i in p1["items"] if i["source"] == "odin") == 3, "ODIN: exactly the three counties at 500+")
check(p1["us"] == {"meters_out": od["meters_out"], "counties": 3, "utilities": od["utilities"], "t": ISO(NT)},
      "us extra: meters_out (all rows), counties at 500+, utilities, t")
check(p1["grid"] == {"taipower": {"light": "G", "reserve_pct": 20.4, "load_mw": 26699, "t": "2026-11-21T04:40:00Z"},
                     "eskom": {"stage": 0, "t": ISO(NT)}, "caiso": {"events": 0, "t": ISO(NT), "names": []}},
      "grid extra: Taipower green, Eskom stage 0, CAISO no event")
check(not any(i["source"] in ("taipower", "eskom", "caiso") for i in p1["items"]),
      "no grid item while green / stage 0 / no CAISO event")
check("participating utilities" in p1["note"] and "ODIN" in p1["attribution"] and "Lucas County" in p1["summary"],
      "note, attribution and summary")
e57, e58, e59 = P1["power:ukrenergo:5657"], P1["power:ukrenergo:5658"], P1["power:ukrenergo:5659"]
check(e57["severity"] == "major" and "emergency" in e57["tags"] and e57["regions"] == ["UA-46", "UA-21", "UA-26"]
      and e57["where"] == "Lviv, Zakarpattia, Ivano-Frankivsk" and e57["place"] == "oblast" and e57["lang"] == "uk"
      and e57["cc"] == ["UKR"] and e57["url"] == "https://t.me/Ukrenergo/5657" and e57["provider"] == "Ukrenergo",
      "Ukrenergo emergency post: major, three oblasts, Ukrainian, post link")
f57 = feats(p1, e57["id"])
check([f["geometry"]["coordinates"] for f in f57] == [REG[c]["ll"] for c in e57["regions"]] and
      [f["properties"]["region"] for f in f57] == e57["regions"], "GeoJSON: one feature per oblast")
check(e59["severity"] == "minor" and "schedule" in e59["tags"] and e59["where"] == "Ukraine" and
      e59["place"] == "country" and e59["ll"] == ds.countries()["UKR"][0], "schedule post: minor, Ukraine centroid")
check(e59["active"] and not e57["active"] and "Ukraine: hourly outage schedules in effect" in p1["summary"],
      "tomorrow's schedule (posted 16:30Z the day before) is active now; a 27 h old emergency post is not")
UEP = state()["sources"]["ukrenergo"]["data"]["posts"]
late59 = [i for i in ds.tg_items("ukrenergo", UEP, T(2026, 11, 21, 22, 1)) if i["id"].endswith(":5659")]
check(len(late59) == 1 and not late59[0]["active"], "... and ends at that day's Kyiv midnight (22:00Z in winter)")
check(ds.kyiv_day_end(T(2026, 11, 20, 16, 30), 1) == T(2026, 11, 21, 22) and
      ds.kyiv_day_end(T(2026, 11, 20, 22, 30)) == T(2026, 11, 21, 22) and
      ds.kyiv_day_end(T(2026, 7, 1, 12)) == T(2026, 7, 1, 21) and
      ds.kyiv_day_end(T(2026, 3, 28, 12), 1) == T(2026, 3, 29, 21), "kyiv_day_end: EET / EEST and the March switch")
check(len(feats(p1, e58["id"])) == len(e58["regions"]) == 12 and e58["where"].endswith("and 7 more"),
      "update post: twelve oblasts, twelve features, short where")
check("power:ukrenergo:5641" not in P1 and "power:ukrenergo:5654" not in P1 and "power:minenergo:8334" not in P1,
      "feature, conference and aid posts are not items")
m40, m45 = P1["power:minenergo:8340"], P1["power:minenergo:8345"]
check(m40["provider"] == "Ministry of Energy of Ukraine" and m40["regions"][:2] == ["UA-63", "UA-59"] and
      m45["regions"] == ["UA-32", "UA-30"], "Ministry posts: -щина oblasts; Kyiv Oblast and Kyiv city apart")
nbu = [i for i in p1["items"] if i["source"] == "netblocks"]
check(len(nbu) == 1 and nbu[0]["kind"] == "post" and nbu[0]["place"] == "country" and nbu[0]["cc"][0] == "UKR" and
      nbu[0]["url"].startswith("https://mastodon.social/@netblocks/") and nbu[0]["severity"] == "major" and
      not nbu[0]["active"], "NetBlocks power post: in power, Ukraine, inactive after 6 h")
check(not any(i["id"].split(":", 1)[1] == nbu[0]["id"].split(":", 1)[1] for i in c1["items"] + c1["internet"]),
      "a power post is not repeated in the cellular feed")
FP = p1["geojson"]["features"]
check(p1["geojson"]["type"] == "FeatureCollection" and
      len(FP) == sum(len(i["_places"]) for i in ds.window(
          ds.odin_items(state()["sources"]["odin"]["data"], state()["odin_geo"], NT), NT)) +
      sum(len(feats(p1, i["id"])) for i in p1["items"] if i["source"] != "odin"), "GeoJSON feature count")
check(all(f["geometry"]["type"] == "Point" and f["properties"]["layer"] == "power" and f["properties"]["pid"] in P1
          and set(f["properties"]) - PLACE_PROPS == ITEM - {"summary", "metric"} | {"layer", "pid"} for f in FP),
      "GeoJSON: points; properties = item minus summary/metric plus layer and pid")
check(len(FP) == sum(len(feats(p1, i["id"])) for i in p1["items"]) and
      all(len(feats(p1, i["id"])) == (len(i["regions"]) if i["place"] in ("oblast", "subject") else 1)
          for i in p1["items"] if i["ll"]), "GeoJSON: one feature per (item, place); only pinned items")

mon = by_id(c1)["cellular:monitor_ru:493"]
check(mon["title"] == "Russia: mobile internet cut in 66 regions, whitelists in 65" and mon["severity"] == "major"
      and mon["kind"] == "shutdown" and mon["active"] and mon["place"] == "subject" and mon["cc"] == ["RUS"] and
      mon["metric"] == {"shutdown_regions": 66, "whitelist_regions": 65} and mon["ts"] == "2026-11-20T09:56:58Z" and
      mon["start_ms"] == T(2026, 11, 19, 12) * 1000, "monitor-ru: one item per snapshot, active, map date at noon")
fm = feats(c1, mon["id"])
known = [c for c in mr[0]["shutdown"] if c in REG]
check(len(fm) == len(known) and len({f["properties"]["region"] for f in fm}) == len(fm) and
      all(f["geometry"]["coordinates"] == REG[f["properties"]["region"]]["ll"] for f in fm),
      "monitor-ru: one feature per region at its subject centroid (%d)" % len(fm))
check(all(f["properties"]["shutdown"] is True and f["properties"]["whitelist"] ==
          (f["properties"]["region"] in mr[0]["whitelist"]) and f["properties"]["layer"] == "cellular" for f in fm),
      "monitor-ru: features carry shutdown / whitelist")
ru = c1["russia"]
check(set(ru) == {"date", "shutdown_regions", "whitelist_regions", "regions"} and ru["date"] == "2026-11-19" and
      ru["shutdown_regions"] == 66 and ru["whitelist_regions"] == 65 and len(ru["regions"]) == 66 and
      all(set(r) == {"code", "name", "shutdown", "whitelist"} for r in ru["regions"]) and
      {r["code"]: r["name"] for r in ru["regions"]}.get("RU-ALT") == "Altai Krai", "russia extra (English names)")
check([i["source"] for i in c1["internet"]] == ["cfradar", "netblocks"] and
      all("internet" in i["tags"] and i["kind"] == "post" for i in c1["internet"]) and
      not any(f["properties"]["pid"] in {i["id"] for i in c1["internet"]} for f in c1["geojson"]["features"]),
      "internet list: Salt and Pakistan, not on the cell layer")
check(not any(i["kind"] == "post" for i in c1["items"]), "no mobile post inside 72 h in the real fixtures")
check({s["name"]: s["n"] for s in c1["sources"]} == {"netblocks": 1, "cfradar": 1, "monitor_ru": 1},
      "cellular source rows count the internet posts too")
check("66 regions" in c1["summary"] and "Internet" in c1["summary"], "cellular summary")

# ---------------- cadence, conditional GET, stable ids, ODIN start / end ----------------

log = []
p1b = ds.power(now=NT + 60, fetch=fake(log=log))
ds.cellular(now=NT + 60, fetch=fake(log=log))
check(log == [], "nothing is due a minute later")
check([i["id"] for i in p1b["items"]] == [i["id"] for i in p1["items"]], "a rebuild from state keeps every id")
log = []
p2 = ds.power(now=NT + 600, fetch=fake(log=log, over={ds.ODIN_URL: odin_variant(f39095=300),
                                                      UE_PAGE: RAW["ukrenergo_emergency_synthetic.html"]}))
c2 = ds.cellular(now=NT + 600, fetch=fake(log=log))
check(set(urls(log)) == {ds.ODIN_URL, ds.NETBLOCKS_URL, ds.TAIPOWER_URL, ds.CAISO_URL, UE_PAGE, ME_PAGE},
      "10 min later: ODIN, NetBlocks, Taipower, CAISO and both channels are due; Radar, Eskom, monitor-ru not")
check(dict(log)[ds.TAIPOWER_URL].get("If-None-Match") == '"tp-1"' and p2["grid"]["taipower"]["light"] == "G" and
      state()["sources"]["taipower"]["ok"], "conditional GET: Taipower's 304 keeps the cached reading")
check(ds.ODIN_MAP_URL not in urls(log), "ODIN map not refetched within 30 min (Harris still unknown)")
P2 = by_id(p2)
check(set(P1) <= set(P2), "ids stable across polls")
lu2 = P2["power:odin:39095:20261121"]
check(not lu2["active"] and lu2["end_ms"] == (NT + 600) * 1000 and lu2["start_ms"] == NT * 1000 and
      lu2["status"] == "resolved" and lu2["title"] == "Power outage ended: Lucas County, OH (peak 5,410 customers out)"
      and lu2["ts_ms"] == (NT + 600) * 1000, "ODIN: a county under 500 ends (same id, end_ms, kept)")
check(p2["us"]["counties"] == 2 and P2["power:odin:48201:20261121"]["active"], "ODIN: the others stay active")
s57 = P2["power:ukrenergo:5700"]
check(s57["active"] and s57["severity"] == "major" and s57["regions"] == ["UA-46", "UA-07", "UA-32", "UA-30"] and
      s57["where"] == "Lviv, Volyn, Kyiv Oblast, Kyiv" and len(feats(p2, s57["id"])) == 4 and
      {"emergency", "schedule"} <= set(s57["tags"]) and "power:ukrenergo:5657" in P2,
      "synthetic emergency post: active, four places; earlier posts kept from state")
check("Ukraine: emergency outages in Lviv" in p2["summary"], "power summary names Ukraine's emergency outages")
check([i["id"] for i in c2["items"]] == [i["id"] for i in c1["items"]], "cellular ids stable")
p3 = ds.power(now=NT + 1200, fetch=fake(over={ds.ODIN_URL: odin_variant(f39095=900)}))
lu3 = by_id(p3)["power:odin:39095:20261121"]
check(lu3["active"] and lu3["start_ms"] == NT * 1000 and lu3["end_ms"] is None and lu3["metric"]["customers"] == 900,
      "ODIN: crossing again the same day resumes the same item")
log = []
ds.power(now=NT + 1800, fetch=fake(log=log, over={ds.ODIN_URL: odin_variant(f39095=900)}))
check(urls(log).count(ds.ODIN_MAP_URL) == 1 and ds.ESKOM_URL in urls(log), "30 min later: the map and Eskom again")
ds.power(now=NT + 2400, fetch=fake(over={ds.ODIN_URL: odin_variant(f39095=300)}))
late = NT + 2400 + ds.ENDED_KEEP + 600
p4 = ds.power(now=late, fetch=fake(over={ds.ODIN_URL: odin_variant(f39095=300)}))
check("power:odin:39095:20261121" not in by_id(p4) and "power:odin:48201:20261121" in by_id(p4) and
      by_id(p4)["power:odin:48201:20261121"]["start_ms"] == NT * 1000, "ODIN: an ended county goes after 24 h")

# ---------------- grid stress: Taipower orange, Eskom stage 4 and the 99 hold, CAISO EEA ----------------

reset()
pt = ds.power(now=NOW, fetch=fake(over={ds.TAIPOWER_URL: RAW["taipower_orange_synthetic.json"],
                                        ds.ESKOM_URL: RAW["eskom_stage4_synthetic.txt"]}))
PT = by_id(pt)
ti = [i for i in pt["items"] if i["source"] == "taipower"]
check(len(ti) == 1 and ti[0]["kind"] == "grid" and ti[0]["severity"] == "major" and ti[0]["active"] and
      ti[0]["title"] == "Taiwan grid: orange light, forecast peak reserve 5.2 %" and ti[0]["cc"] == ["TWN"] and
      ti[0]["ll"] == ds.countries()["TWN"][0] and ti[0]["ts"] == "2026-11-21T08:30:00Z",
      "Taipower orange light: a major grid item at the Taiwan centroid")
check(pt["grid"]["taipower"] == {"light": "O", "reserve_pct": 5.2, "load_mw": 38105, "t": "2026-11-21T08:30:00Z"},
      "grid.taipower follows the light")
ei = [i for i in pt["items"] if i["source"] == "eskom"]
check(len(ei) == 1 and ei[0]["title"] == "South Africa: Eskom load shedding stage 4" and ei[0]["severity"] == "major"
      and ei[0]["active"] and ei[0]["cc"] == ["ZAF"] and ei[0]["metric"] == {"stage": 4} and
      pt["grid"]["eskom"] == {"stage": 4, "t": ISO(NT)}, "Eskom stage 4: a major item, grid.eskom stage 4")
check("load shedding stage 4" in pt["summary"] and "orange light" in pt["summary"], "power summary: grid stress")
ph = ds.power(now=NT + 1800, fetch=fake(over={ds.ESKOM_URL: b"99", ds.TAIPOWER_URL: RAW["taipower.json"]}))
eh = [i for i in ph["items"] if i["source"] == "eskom"]
check(ph["grid"]["eskom"] == {"stage": 4, "t": ISO(NT)} and len(eh) == 1 and eh[0]["active"] and
      eh[0]["id"] == ei[0]["id"] and state()["sources"]["eskom"]["data"]["updating"],
      "Eskom 99 (updating): the previous stage is held")
tg = [i for i in ph["items"] if i["source"] == "taipower"]
check(len(tg) == 1 and not tg[0]["active"] and tg[0]["id"] == ti[0]["id"] and tg[0]["end_ms"] == (NT + 1800) * 1000
      and tg[0]["title"] == "Taiwan grid back to green (was orange)" and ph["grid"]["taipower"]["light"] == "G",
      "Taipower back to green: the item ends (same id)")
pe = ds.power(now=NT + 3600, fetch=fake())
ee = [i for i in pe["items"] if i["source"] == "eskom"]
check(pe["grid"]["eskom"]["stage"] == 0 and len(ee) == 1 and not ee[0]["active"] and
      ee[0]["end_ms"] == (NT + 3600) * 1000 and "suspended" in ee[0]["title"], "Eskom back to 1: the item ends")

reset()
SUMMER = T(2026, 8, 20, 23, 30)
pc = ds.power(now=SUMMER, fetch=fake(over={ds.CAISO_URL: RAW["caiso_eea_synthetic.json"]}))
ci = [i for i in pc["items"] if i["source"] == "caiso"]
check(len(ci) == 1 and ci[0]["id"] == "power:caiso:4321" and ci[0]["active"] and ci[0]["severity"] == "major" and
      ci[0]["title"] == "California grid (CAISO): EEA 2 in effect" and ci[0]["start_ms"] == T(2026, 8, 20, 23) * 1000
      and ci[0]["ts_ms"] == T(2026, 8, 20, 22, 45) * 1000 and ci[0]["ll"] == ds.CAISO_LL and ci[0]["place"] == "hq"
      and ci[0]["regions"] == ["US-CA"] and "Energy Emergency Alert 2" in ci[0]["summary"],
      "CAISO EEA 2 (August, PDT): a major item pinned at the Folsom control centre")
check(pc["grid"]["caiso"] == {"events": 1, "t": ISO(SUMMER), "names": ["EEA 2"]} and "EEA 2 in effect" in
      pc["summary"], "grid.caiso and the summary name the event")
pc2 = ds.power(now=SUMMER + 600, fetch=fake())
ci2 = [i for i in pc2["items"] if i["source"] == "caiso"]
check(len(ci2) == 1 and not ci2[0]["active"] and ci2[0]["end_ms"] == (SUMMER + 600) * 1000 and
      ci2[0]["status"] == "resolved" and pc2["grid"]["caiso"]["events"] == 0, "CAISO: an event that leaves the list ends")

# ---------------- mobile posts, future stamps ----------------

reset()
cm = ds.cellular(now=NOW, fetch=fake(over={
    ds.CFRADAR_URL: rss_redate(CF, "Orange (AS3215)", "21 Nov 2026 07:30 +0000"),
    ds.NETBLOCKS_URL: rss_redate(NB, "Pakistan", "Sun, 22 Nov 2026 10:00:00 +0000")}))
mob = [i for i in cm["items"] if i["kind"] == "post"]
check(len(mob) == 1 and mob[0]["source"] == "cfradar" and mob[0]["tags"] == ["mobile"] and mob[0]["active"] and
      mob[0]["where"] == "France" and mob[0]["cc"][0] == "FRA" and mob[0]["ll"] == ds.countries()["FRA"][0] and
      len(feats(cm, mob[0]["id"])) == 1, "a mobile post is a cellular item on the cell layer")
pak = [i for i in cm["internet"] if i["source"] == "netblocks"]
check(len(pak) == 1 and pak[0]["ts_ms"] == NT * 1000, "a post stamped in the future is clamped to now")
check("Orange" in cm["summary"], "cellular summary names the newest mobile post")

# ---------------- failures, budget, back-off ----------------

reset()
pf = ds.power(now=NOW, fetch=fake(fail=(ds.TAIPOWER_URL,)))
cf = ds.cellular(now=NOW, fetch=fake(fail=(ds.MONITOR_RU_URL,)))
row = {s["name"]: s for s in pf["sources"] + cf["sources"]}
check(not row["taipower"]["ok"] and "OSError" in row["taipower"]["error"] and row["taipower"]["good"] is None and
      pf["grid"]["taipower"] is None and pf["grid"]["eskom"] is not None and pf["count"] > 0,
      "a failing source only marks its row (Taipower)")
check(not row["monitor_ru"]["ok"] and cf["russia"] is None and len(cf["internet"]) == 2,
      "monitor-ru failing leaves the cellular feed working")
reset()
log = []
check(raises(lambda: ds.power(now=NOW, fetch=fake(log=log, fail=(ds.ODIN_URL, ds.TAIPOWER_URL, ds.ESKOM_URL))),
             RuntimeError, "no source has answered"), "power raises when no source has ever answered")
check(urls(log) == [ds.ODIN_URL, ds.TAIPOWER_URL, ds.ESKOM_URL], "a poll stops after 3 failures in a row")
log = []
pr = ds.power(now=NT + 1, fetch=fake(log=log))
check(ds.ODIN_URL not in urls(log) and ds.CAISO_URL in urls(log) and pr["grid"]["caiso"] is not None,
      "the next call tries the rest; failed sources wait for their retry")
reset()
check(raises(lambda: ds.cellular(now=NOW, fetch=fake(fail=tuple(URLS))), RuntimeError, "no source has answered"),
      "cellular raises when no source has ever answered")
ds.cellular(now=NT + 2000, fetch=fake())    # past the 30 min retry of every source
cc2 = ds.cellular(now=NT + 20000, fetch=fake(fail=tuple(URLS)))
check(cc2["russia"] is not None and not any(s["ok"] for s in cc2["sources"]) and
      all(s["good"] for s in cc2["sources"]), "after one success, an all-failing poll serves the cached data")
reset()
calls = []


def slow_clock():
    calls.append(1)
    return 0 if len(calls) <= 2 else 100


log = []
ds.power(now=NOW, fetch=fake(log=log), clock=slow_clock)
check(urls(log) == [ds.ODIN_URL, ds.ODIN_MAP_URL], "a poll stops fetching after its 45 s budget")
reset()
ds.power(now=NOW, fetch=fake(fail={UE_PAGE: 429}))
sv = state()["sources"]["ukrenergo"]
check(sv["backoff_until"] == NT + 3600 and "429" in sv["error"], "Telegram 429: one hour back-off")
log = []
ds.power(now=NT + 600, fetch=fake(log=log))
check(UE_PAGE not in urls(log) and ME_PAGE in urls(log), "backed-off channel skipped, the other polled")
log = []
ds.power(now=NT + 3600, fetch=fake(log=log))
check(UE_PAGE in urls(log) and state()["sources"]["ukrenergo"]["ok"], "the channel is retried after the back-off")

# ---------------- caps ----------------

fake_items = [{"id": "power:x:%d" % k, "ts_ms": k, "active": k % 3 == 0, "kind": "post" if k % 2 else "grid"}
              for k in range(450, 0, -1)]
kept, dropped = ds._cap(fake_items)
gone = [i for i in fake_items if i not in kept]
old_posts = sorted((i for i in fake_items if not i["active"] and i["kind"] == "post"), key=lambda i: i["ts_ms"])
check(len(kept) == 400 and dropped == 50 and gone == sorted(old_posts[:50], key=lambda i: -i["ts_ms"]) and
      kept == [i for i in fake_items if i in kept], "item cap 400: the oldest inactive posts go first, order kept")
reset()
ds.power(now=NOW, fetch=fake())
old_max = ds.MAX_BYTES
ds.MAX_BYTES = 20000
try:
    small = ds.power(now=NOW, fetch=fake(fail=tuple(URLS)))
finally:
    ds.MAX_BYTES = old_max
check(SIZE(small) <= 20000 and small["trimmed"] > 0 and small["count"] == len(small["items"]) and
      all(f["properties"]["pid"] in by_id(small) for f in small["geojson"]["features"]),
      "byte cap: items and their features trimmed together")

# ---------------- default fetch ----------------


class Resp:
    def __init__(self, body, enc=None, status=200):
        self.body, self.status = body, status
        self.headers = {"Content-Encoding": enc} if enc else {}

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen = {}


def fake_open(req, timeout=None):
    seen.update(ua=req.get_header("User-agent"), ae=req.get_header("Accept-encoding"),
                inm=req.get_header("If-none-match"), timeout=timeout)
    return Resp(gzip.compress(RAW["eskom.txt"]), "gzip")


ds.urllib.request.urlopen = fake_open
st_, _h, body = ds._fetch(ds.ESKOM_URL, {"If-None-Match": '"x"'})
check(st_ == 200 and body == b"1" and seen == {"ua": ds.UA, "ae": "gzip", "inm": '"x"', "timeout": ds.TIMEOUT},
      "default fetch: contract UA, gzip decoded, validators passed, timeout")


def not_modified(req, timeout=None):
    raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", None, None)


ds.urllib.request.urlopen = not_modified
check(ds._fetch(ds.TAIPOWER_URL)[0] == 304, "default fetch: 304 is an answer, not an error")
ds.urllib.request.urlopen = lambda req, timeout=None: Resp(b"x" * (ds.MAX_BODY + 1))
check(raises(lambda: ds._fetch(ds.ODIN_URL), ValueError, "over"), "default fetch: oversized body refused")
ds.urllib.request.urlopen = _blocked
print("     power summary:   ", p1["summary"])
print("     cellular summary:", c1["summary"])
print("%d checks passed" % ok)
