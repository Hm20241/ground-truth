"""Offline tests for 0.13.0 signals: BfS radiation, tsunami/volcano bulletins, OFAC actions, DHS NTAS (gt/signals.py).
Never touches the network: sockets are blocked and every fetch is injected. Fixtures (tests/fixtures/signals/):
  bfs.json            synthetic BfS WFS answer (invented stations, the real 2026-11-20 key set); hours are rebuilt here
  ptwc_pheb.xml       real PTWC Atom of 2026-11-20 (NOAA, public domain)
  ntwc_warning.xml    the real NTWC Atom structure with a synthetic Warning
  jma_eqvol_l.xml     synthetic JMA Atom (Japanese titles and text, invented bulletins)
  ofac_p0.html, ofac_p1.html   real OFAC recent-actions pages 1-2 of 2026-11-20, trimmed to the list (public domain)
  ntas_empty.xml      real DHS NTAS feed of 2026-11-20 (<alerts></alerts>)
  ntas_2023.xml       real NTAS feed of 2023-04-21 (web.archive.org capture, details trimmed; public domain)
  ntas_synthetic.xml  synthetic NTAS 1.1 feed: expired, open-ended elevated (malformed HTML), not yet started

Run: python3 -I tests/test_signals.py
"""
import copy
import datetime as dt
import gzip
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "signals")
TMP = tempfile.mkdtemp(prefix="gt-signals-")
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import signals as sg  # noqa: E402

sg.urllib.request.urlopen = no_network
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def raises(fn, exc, text=""):
    try:
        fn()
    except exc as e:
        return text in str(e)
    return False


RAW = {n: open(os.path.join(FX, n), "rb").read() for n in os.listdir(FX)}
NOW = dt.datetime(2026, 11, 20, 5, 30, tzinfo=dt.timezone.utc)
LOCKEYS = ("country", "country_name", "sea", "theatre")
CACHE = os.path.join(TMP, "cache")


def contract(d, feed):
    json.dumps(d, allow_nan=False)
    return (all(k in d for k in ("version", "fetched_at", "count", "sources", "attribution")) and d["version"] == "1.0"
            and all(set(s) == {"name", "ok", "error", "newest", "n"} for s in d["sources"])
            and d["licence"] == sg.LICENCE[feed] and d["public_ok"] is True and d["non_commercial"] is False
            and len(json.dumps(d).encode()) < 300000)


def reset(name):
    for ext in ("", ".tmp"):
        p = os.path.join(CACHE, "signals_%s.json%s" % (name, ext))
        if os.path.exists(p):
            os.remove(p)


# ---- module contract
check(set(sg.FEEDS) == {"radiation", "tsunami", "ofac", "ntas"} and sg.FEEDS["radiation"] == (sg.radiation, 3600)
      and sg.FEEDS["tsunami"] == (sg.tsunami, 600) and sg.FEEDS["ofac"] == (sg.ofac, 3600)
      and sg.FEEDS["ntas"] == (sg.ntas, 3600), "FEEDS and intervals")
reg = open(os.path.join(PROJ, "gt", "feeds.py"), encoding="utf-8").read().split("REGISTRY = {", 1)[1].split("}", 1)[0]
check(all(n.isalpha() and n.islower() for n in sg.FEEDS) and not any('"%s":' % n in reg for n in sg.FEEDS),
      "feed names: lowercase letters, no clash with gt/feeds.py REGISTRY")
check(all(sg.PUBLIC_OK[k] and not sg.NON_COMMERCIAL[k] for k in sg.FEEDS) and "Bundesamt für Strahlenschutz" in sg.ATTRIBUTION["bfs"]
      and sg.ATTRIBUTION["jma"].startswith("Source: Japan Meteorological Agency website") and "edited" in sg.ATTRIBUTION["jma"],
      "all public OK; BfS and JMA credit lines as their terms ask")

# ================= radiation =================
BFS = json.loads(RAW["bfs.json"])
BASE = {f["properties"]["id"]: f["properties"]["value"] for f in BFS["features"]}


def bfs_body(hour, values=None, drop=()):
    """The fixture re-stamped to end at `hour` (UTC datetime), with some values replaced."""
    d = copy.deepcopy(BFS)
    d["features"] = [f for f in d["features"] if f["properties"]["id"] not in drop]
    for f in d["features"]:
        p = f["properties"]
        if p["value"] is None or p["id"] == "DEZ9009":    # the defect station; the stale one keeps its old hour
            continue
        p["end_measure"] = hour.strftime("%Y-%m-%dT%H:%M:%SZ")
        p["start_measure"] = (hour - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if values and p["id"] in values:
            p["value"] = values[p["id"]]
    return json.dumps(d).encode()


H0 = dt.datetime(2026, 11, 20, 4, 0, tzinfo=dt.timezone.utc)
calls = []


def run(hour, values=None, now=None, drop=(), body=None):
    def fetch(url):
        calls.append(url)
        return body if body is not None else bfs_body(hour, values, drop)
    return sg.radiation(now=now or hour + dt.timedelta(minutes=90), fetch=fetch)


st = sg.bfs_stations(RAW["bfs.json"])
check(len(st) == 9 and st[6]["value"] is None and st[6]["status"] == 2 and st[7]["status"] == 3
      and st[0]["end"] == H0 and st[0]["lon"] == 9.0, "parse: 9 stations, defect value None, status codes, UTC end")
r = run(H0)
check(calls == [sg.BFS_URL] and "typeName=opendata:odlinfo_odl_1h_latest" in sg.BFS_URL and "outputFormat=application/json" in sg.BFS_URL,
      "one WFS call")
check(contract(r, "radiation") and r["count"] == 0 and r["geojson"]["features"] == [] and r["alert"] is False,
      "cold start, normal values: nothing flagged")
S = r["summary"]
check(S["stations"] == 9 and S["reporting"] == 7 and S["fresh"] == 6 and S["not_operating"] == 2
      and S["measured_until"] == "2026-11-20T04:00:00Z" and S["stale"] is False,
      "summary: 9 stations, 7 in Betrieb with a value, 6 fresh (one 18 h old), 2 not operating")
check(S["network_median_usv"] == 0.105 and S["network_baseline_usv"] is None and S["network_change_pct"] is None
      and S["network_flag"] is False and S["stations_with_baseline"] == 0, "network median 0.105, no baseline yet")
check(S["max"] == {"id": "DEZ9003", "name": "Beispieldorf", "value_usv": 0.2, "baseline_usv": None, "lon": 11.0, "lat": 51.0},
      "max = highest fresh station (the 0.5 test-mode and the 0.4 stale station do not count)")
cf = json.load(open(os.path.join(CACHE, "signals_radiation.json")))
check(cf["stations"]["DEZ9001"] == [int(H0.timestamp() // 3600), [100]] and "DEZ9008" not in cf["stations"]
      and "DEZ9009" in cf["stations"] and cf["network"] == [[int(H0.timestamp() // 3600), 105]]
      and not os.path.exists(os.path.join(CACHE, "signals_radiation.json.tmp")),
      "cache: nSv/h history per station and the network median, written atomically")

reset("radiation")
r = run(H0, {"DEZ9001": 0.35})
F = r["geojson"]["features"]
check(r["count"] == 1 and F[0]["properties"]["id"] == "DEZ9001" and F[0]["properties"]["baseline_kind"] == "network"
      and F[0]["properties"]["baseline_usv"] == 0.115 and F[0]["properties"]["ratio"] == 3.04,
      "cold start spike: no own baseline -> network median stands in (0.35 vs 0.115)")
p = F[0]["properties"]
check(p["country"] == "DEU" and p["theatre"] == "europe-nato" and p["source"] == "BfS" and p["name"] == "Teststadt Nord"
      and p["measured"] == "2026-11-20T04:00:00Z" and F[0]["geometry"]["coordinates"] == [9.0, 50.0] and r["alert"] is True,
      "flagged point: geo.locate fields, source, name, measured, alert")

reset("radiation")
for i in range(8):     # 8 normal hours: 04:00 .. 11:00
    r = run(H0 + dt.timedelta(hours=i))
check(r["summary"]["stations_with_baseline"] == 6 and r["count"] == 0 and r["summary"]["network_baseline_usv"] == 0.105
      and r["summary"]["network_change_pct"] == 0 and r["summary"]["network_baseline_hours"] == 7,
      "after 8 normal hours: 6 station baselines, network baseline 0.105 from 7 earlier hours")
H8 = H0 + dt.timedelta(hours=8)
spike = {"DEZ9001": 0.35, "DEZ9002": 0.25, "DEZ9003": 0.31}
r = run(H8, spike)
F = {f["properties"]["id"]: f["properties"] for f in r["geojson"]["features"]}
check(set(F) == {"DEZ9001"} and F["DEZ9001"]["baseline_kind"] == "station" and F["DEZ9001"]["baseline_usv"] == 0.1
      and F["DEZ9001"]["ratio"] == 3.5, "0.35 vs own 0.100 -> flagged (x3.5)")
check("DEZ9002" not in F and "DEZ9003" not in F and "DEZ9009" not in F and "DEZ9008" not in F,
      "0.25 (x2.8 but under 0.3), 0.31 (x1.55), stale 0.4 and test-mode 0.5 -> not flagged")
again = run(H8, spike)
cf = json.load(open(os.path.join(CACHE, "signals_radiation.json")))
check(again["geojson"] == r["geojson"] and len(cf["stations"]["DEZ9001"][1]) == 9 and cf["stations"]["DEZ9001"][1][-1] == 350
      and len(cf["network"]) == 9, "the same hour polled twice -> no second sample, same flags")
r = run(H8 + dt.timedelta(hours=1), {k: round(v * 1.5, 3) for k, v in BASE.items() if v is not None})
S = r["summary"]
check(S["network_flag"] is True and S["network_change_pct"] == 50 and S["network_median_usv"] == 0.158
      and r["alert"] is True and r["count"] == 0, "every station x1.5 -> network +50 % flagged, no single station flagged")
check(sg._step(None, 5, 100) == ([5, [100]], []) and sg._step([5, [100]], 5, 120) == ([5, [120]], [])
      and sg._step([5, [100]], 4, 90) == ([5, [100]], [100]) and sg._step([1, list(range(sg.HIST_MAX))], 2, 7)[0][1][-1] == 7
      and len(sg._step([1, list(range(sg.HIST_MAX))], 2, 7)[0][1]) == sg.HIST_MAX
      and sg._step("junk", 3, 50) == ([3, [50]], []), "history step: new hour, revised hour, older hour, 168 cap, junk record")
r = run(H8 + dt.timedelta(hours=200), drop=("DEZ9006",), now=H8 + dt.timedelta(hours=201))
cf = json.load(open(os.path.join(CACHE, "signals_radiation.json")))
check("DEZ9006" not in cf["stations"] and "DEZ9009" not in cf["stations"] and "DEZ9001" in cf["stations"],
      "stations unseen for over 7 days pruned from the cache")
r = run(H0, now=H0 + dt.timedelta(hours=6))
check(r["summary"]["stale"] is True, "newest value older than 4 h -> stale")
with open(os.path.join(CACHE, "signals_radiation.json"), "w") as fh:
    fh.write("{broken")
check(run(H0)["summary"]["reporting"] == 7, "corrupt cache -> starts over")
check(raises(lambda: run(H0, body=b"<html>maintenance</html>"), RuntimeError, "every source failed"), "BfS error page -> RuntimeError")
check(raises(lambda: run(H0, body=b'{"type":"FeatureCollection","features":[]}'), RuntimeError, "no stations"), "no stations -> RuntimeError")
check(run(H0, body=gzip.compress(bfs_body(H0)))["summary"]["fresh"] == 6, "gzip body decoded")

# ================= tsunami and volcano bulletins =================


def tfake(pheb=None, paaq=None, jma=None, fail=(), log=None):
    def fetch(url):
        if log is not None:
            log.append(url)
        for key, name, body in (("PHEB", "ptwc", pheb), ("PAAQ", "ntwc", paaq), ("eqvol_l", "jma", jma)):
            if key in url:
                if name in fail:
                    raise urllib.error.URLError("%s down" % name)
                return body if body is not None else {"ptwc": RAW["ptwc_pheb.xml"], "ntwc": RAW["ntwc_warning.xml"],
                                                      "jma": RAW["jma_eqvol_l.xml"]}[name]
        raise AssertionError(url)
    return fetch


log = []
t = sg.tsunami(now=NOW, fetch=tfake(log=log))
check(log == [sg.PTWC_FEEDS[0][2], sg.PTWC_FEEDS[1][2], sg.JMA_URL] and sg.JMA_URL.endswith("/eqvol_l.xml"),
      "3 calls: PTWC, NTWC, JMA eqvol_l.xml")
check(contract(t, "tsunami") and t["count"] == 10 and len(t["items"]) == 10, "10 bulletins in the last 72 h")
I = {i["id"]: i for i in t["items"]}
pt = I["ptwc:urn:uuid:c23bd481-3e1a-4962-b760-e2e69b484d1c"]
check(pt["level"] == "information" and pt["label"] == "Tsunami Information Statement Number 1" and pt["magnitude"] == 5.9
      and pt["mag_type"] == "Mwp" and pt["issued"] == "2026-11-18T02:30:47Z" and pt["region"] == "About 94 Miles Southwest Of Guam"
      and pt["centre"] == "NWS PACIFIC TSUNAMI WARNING CENTER HONOLULU HI" and pt["category"] == "Information",
      "real PTWC bulletin: level, label, magnitude, issue time, region (namespaced xhtml summary)")
check(pt["url"].endswith("/WEGM42/WEGM42.txt") and pt["cap_url"].endswith("/PHEBCAP.xml") and pt["lat"] == 12.073
      and pt["lon"] == 143.992 and pt["country"] == "GUM" and pt["theatre"] == "indo-pacific" and pt["source"] == "PTWC",
      "bulletin and CAP links, geo:lat/long, located")
nt = I["ntwc:urn:uuid:00000000-0000-4000-8000-000000000002"]
check(nt["level"] == "warning" and nt["label"] == "Tsunami Warning Number 2" and nt["magnitude"] == 7.4
      and nt["note"] == "* A tsunami warning is in effect for a test coast." and nt["country"] == "USA", "NTWC warning")
J = {i["title_ja"] + "|" + i["issued"]: i for i in t["items"] if i["source"] == "JMA"}
check(len(J) == 8 and not any("降灰予報" in k or "推定噴煙流向報" in k or "震源" in k for k in J),
      "JMA: 8 tsunami/volcano bulletins; ashfall forecasts, plume reports and quake reports skipped")
adv = J["津波警報・注意報・予報a|2026-11-20T03:10:00Z"]
can = J["津波警報・注意報・予報a|2026-11-20T04:40:00Z"]
check(adv["level"] == "advisory" and adv["label"] == "Tsunami advisory" and not adv["cancelled"]
      and adv["country"] == "JPN" and adv["theatre"] == "indo-pacific" and adv["office_ja"] == "気象庁" and adv["lat"] is None,
      "tsunami advisory read from the Japanese text; Japan location fields, no point")
check(can["level"] == "information" and can["cancelled"] and can["label"] == "Tsunami warning / advisory / forecast (cancelled)",
      "cancellation (解除) -> information, marked cancelled")
check(J["津波情報a|2026-11-20T03:12:00Z"]["level"] == "information"
      and J["津波情報a|2026-11-20T03:12:00Z"]["label"] == "Tsunami information (arrival times and heights)", "tsunami information")
sk = J["噴火警報・予報|2026-11-20T01:00:00Z"]
check(sk["level"] == "warning" and sk["alert_level"] == 4 and sk["volcano"] == "Sakurajima" and sk["volcano_ja"] == "桜島"
      and (sk["lat"], sk["lon"]) == (31.58, 130.66) and sk["label"] == "Volcanic warning / forecast",
      "噴火警報（居住地域） level ４ (full-width) -> warning, Sakurajima placed")
kr = J["噴火速報|2026-11-19T22:00:00Z"]
check(kr["level"] == "watch" and kr["volcano"] == "Kirishimayama (Shinmoedake)" and kr["label"] == "Eruption flash report",
      "eruption flash -> watch, volcano from ＜霧島山（新燃岳）で噴火が発生＞")
check(J["火山の状況に関する解説情報|2026-11-19T07:00:00Z"]["level"] == "advisory"
      and J["火山の状況に関する解説情報|2026-11-19T07:00:00Z"]["alert_level"] == 2
      and J["噴火に関する火山観測報|2026-11-19T10:00:00Z"]["volcano"] == "Suwanosejima"
      and J["噴火に関する火山観測報|2026-11-19T10:00:00Z"]["level"] == "information", "crater warning level 2 -> advisory; observation report -> information")
tz = J["火山の状況に関する解説情報|2026-11-19T06:00:00Z"]
check(tz["volcano_ja"] == "テスト山" and tz["volcano"] is None and tz["lat"] is None and tz["level"] == "information"
      and tz["alert_level"] == 1, "unknown volcano: Japanese name kept, no point")
check(not any(i["issued"] < "2026-11-17T05:30:00Z" for i in t["items"]), "the 2026-11-16 bulletin is outside 72 h")
check(t["by_level"] == {"warning": 2, "advisory": 2, "watch": 1, "information": 5} and t["max_level"] == "warning"
      and t["alert"] is True, "levels: 2 warning, 2 advisory, 1 watch, 5 information")
check(len(t["geojson"]["features"]) == 6 and all(all(k in f["properties"] for k in LOCKEYS + ("source",))
                                                 for f in t["geojson"]["features"]),
      "6 bulletins with a point in geojson, each with geo fields and source")
check([i["issued"] for i in t["items"]] == sorted((i["issued"] for i in t["items"]), reverse=True), "newest first")
check(t["sources"][2] == {"name": "JMA", "ok": True, "error": None, "newest": "2026-11-20T04:40:00Z", "n": 9}
      and t["attribution"] == [sg.ATTRIBUTION[k] for k in ("ptwc", "ntwc", "jma")], "sources and credits")
check(sg.tsunami(now=NOW, fetch=tfake(jma=gzip.compress(RAW["jma_eqvol_l.xml"])))["items"] == t["items"], "gzip JMA body decoded")

# persistence and partial failure
p2 = sg.tsunami(now=NOW + dt.timedelta(minutes=10), fetch=tfake(fail=("ptwc", "ntwc"), jma=b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'))
check(p2["count"] == 10 and [s["ok"] for s in p2["sources"]] == [False, False, True] and "URLError" in p2["sources"][0]["error"]
      and p2["attribution"] == [sg.ATTRIBUTION["jma"]], "feeds down or empty -> the 72 h store still serves earlier bulletins")
p3 = sg.tsunami(now=NOW + dt.timedelta(days=4), fetch=tfake(jma=b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>',
                                                            pheb=RAW["ptwc_pheb.xml"], paaq=RAW["ntwc_warning.xml"]))
check(p3["count"] == 0 and p3["max_level"] is None and p3["alert"] is False, "4 days later -> everything aged out")
check(raises(lambda: sg.tsunami(now=NOW, fetch=tfake(fail=("ptwc", "ntwc", "jma"))), RuntimeError, "every source failed"),
      "all three down -> RuntimeError")
bad = sg.tsunami(now=NOW, fetch=tfake(jma=b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><feed/>',
                                      paaq=b"<rss><channel/></rss>"))
check("refused" in bad["sources"][2]["error"] and "not an Atom feed" in bad["sources"][1]["error"],
      "a DTD is refused; RSS instead of Atom -> source error")
check(sg.jma_level("tsunami", "", "津波警報を津波注意報に切り替えました。") == ("advisory", False, "Tsunami advisory")
      and sg.jma_level("tsunami", "", "【大津波警報】大津波警報を発表しました。") == ("warning", False, "Major tsunami warning")
      and sg.jma_level("tsunami", "", "津波予報(若干の海面変動)を発表しました。")[0] == "information"
      and sg.jma_level("tsunami", "", "大津波警報・津波警報・津波注意報を発表しました。")[2] == "Major tsunami warning"
      and sg.jma_level("tsunami", "", "津波警報を解除し、津波注意報を発表しました。")[:2] == ("advisory", False)
      and sg.jma_level("volcano", "噴火警報・予報", "<噴火警戒レベル3(入山規制)に引上げ>") == ("advisory", False, None)
      and sg.jma_level("volcano", "噴火警報・予報", "居住地域の近くまで影響")[0] == "information",
      "level heuristics: downgrade switch, major warning, forecast, level 3, '居住地域' alone is not a warning")

# ================= OFAC =================


def ofake(pages, log=None):
    def fetch(url):
        if log is not None:
            log.append(url)
        p = pages.get(url)
        if isinstance(p, Exception):
            raise p
        if p is None:
            raise AssertionError(url)
        return p
    return fetch


U0, U1, U2 = sg.OFAC_URL, sg.OFAC_URL + "?page=1", sg.OFAC_URL + "?page=2"
log = []
o = sg.ofac(now=NOW, fetch=ofake({U0: RAW["ofac_p0.html"], U1: RAW["ofac_p1.html"]}, log))
check(log == [U0, U1] and o["pages"] == 2, "2 pages: the second reaches past 30 days, so paging stops")
check(contract(o, "ofac") and o["count"] == 12 and o["items"][0]["date"] == "2026-11-19" and o["items"][-1]["date"] == "2026-10-21",
      "12 actions from 2026-10-21 to 2026-11-19")
first = o["items"][0]
check(first["url"] == "https://ofac.treasury.gov/recent-actions/20261119" and first["category"] == "Sanctions List Updates"
      and first["programs"] == ["counter-narcotics", "russia", "cyber"] and first["actions"] == ["designation", "general-license", "faq"]
      and first["countries"] == ["RUS"] and first["theatres"] == ["ukraine-russia"] and first["source"] == "OFAC",
      "tags from the title: programs, actions, countries, theatres")
ext = [i for i in o["items"] if "Extreme Networks" in i["title"]][0]
check("Treasury's Office" in ext["title"] and ext["category"] == "Enforcement Actions" and ext["actions"] == ["enforcement"]
      and ext["programs"] == ["other"], "HTML entities decoded; settlement -> enforcement, program other")
check(o["by_program"]["iran"] == 5 and o["sources"][0]["newest"] == "2026-11-19" and o["sources"][0]["ok"], "counts and source")
log = []
o2 = sg.ofac(now=dt.datetime(2026, 10, 25, 12, tzinfo=dt.timezone.utc),
             fetch=ofake({U0: RAW["ofac_p0.html"], U1: RAW["ofac_p1.html"], U2: urllib.error.HTTPError(U2, 503, "x", {}, None)}, log))
urls = [i["url"] for i in o2["items"]]
check(log == [U0, U1, U2] and o2["sources"][0]["ok"] is False and "HTTPError" in o2["sources"][0]["error"]
      and "https://ofac.treasury.gov/recent-actions/20261013_33" in urls and "https://ofac.treasury.gov/recent-actions/20261009_33" in urls
      and all(i["date"] <= "2026-10-26" for i in o2["items"]) and o2["count"] == 10,
      "page 3 fails -> rows so far served with the error; same-day '_33' rows kept; future rows dropped")
check(raises(lambda: sg.ofac(now=NOW, fetch=ofake({U0: b"<html><body>Access denied</body></html>"})), RuntimeError, "every source failed"),
      "a block page instead of the list -> RuntimeError")
check(sg.tags_for("South Sudan-related Designations")[0] == ["south-sudan"] and sg.tags_for("Sudan-related Designations")[0] == ["sudan"]
      and sg.tags_for("Hizballah-related Designations")[2] == ["LBN"] and sg.tags_for("Publication of OFAC Alert")[1] == ["advisory"]
      and sg.tags_for("Counter Terrorism Designations; Iran-related Designation Removal") == (["counter-terrorism", "iran"],
                                                                                            ["designation", "removal"], ["IRN"]),
      "tags: South Sudan vs Sudan, Hizballah -> Lebanon, alerts, removals")

# ================= NTAS =================


def nfake(body):
    return lambda url: body if url == sg.NTAS_URL else (_ for _ in ()).throw(AssertionError(url))


n0 = sg.ntas(now=NOW, fetch=nfake(RAW["ntas_empty.xml"]))
check(contract(n0, "ntas") and n0["count"] == 0 and n0["active"] is False and n0["items"] == [] and n0["level"] is None
      and n0["sources"][0] == {"name": "DHS NTAS", "ok": True, "error": None, "newest": None, "n": 0},
      "today's empty feed -> active: false, no items")
n1 = sg.ntas(now=dt.datetime(2023, 4, 21, 12, tzinfo=dt.timezone.utc), fetch=nfake(RAW["ntas_2023.xml"]))
a = n1["items"][0]
check(n1["active"] and n1["level"] == "bulletin" and a["type"] == "Bulletin Threat" and a["start"] == "2022-11-30T19:00:00Z"
      and a["end"] == "2023-05-24T18:00:00Z" and a["start_et"] == "2022/11/30 14:00:00",
      "real 2023 bulletin: active then; ET times to UTC (EST +5 h, EDT +4 h)")
check(a["summary"].startswith("Summary of Terrorism Threat to the United States The United States remains")
      and a["locations"] == ["Nationwide"] and a["sectors"] == ["All Sectors"]
      and a["duration"] == "This Bulletin will expire on May 24, 2023 at 2:00 PM ET"
      and a["url"].endswith("22_1130_S1_NTAS-Bulletin-508.pdf") and len(a["summary"]) <= 800, "summary text, locations, sectors, duration, PDF link")
n2 = sg.ntas(now=NOW, fetch=nfake(RAW["ntas_2023.xml"]))
check(n2["active"] is False and n2["count"] == 0 and n2["in_feed"] == 1, "the same bulletin today -> expired, not active")
n3 = sg.ntas(now=NOW, fetch=nfake(RAW["ntas_synthetic.xml"]))
e = n3["items"][0] if n3["items"] else {}
check(n3["count"] == 1 and n3["in_feed"] == 3 and n3["level"] == "elevated" and e.get("kind") == "elevated"
      and e.get("end") is None and e.get("start") == "2026-11-19T14:00:00Z",
      "synthetic: expired and not-yet-started skipped; open-ended elevated alert active (EST)")
check(e["summary"] == "Synthetic elevated alert. A credible threat against a test sector. Unclosed paragraph & an entity."
      and e["url"] == "https://www.dhs.gov/ntas/advisory/test-elevated?ref=feed&v=1"
      and e["locations"] == ["Test City, Example State", "Second Test City"] and e["sectors"] == ["Transportation", "Commercial Facilities"],
      "malformed HTML (<br>, &nbsp;, unclosed <p>) parsed by regex; href entity decoded")
check(raises(lambda: sg.ntas(now=NOW, fetch=nfake(b"<html><title>Access Denied</title></html>")), RuntimeError, "not an alerts feed"),
      "an HTML block page -> RuntimeError")
check(sg.ntas(now=NOW, fetch=nfake(gzip.compress(RAW["ntas_synthetic.xml"])))["count"] == 1, "gzip body decoded")
E = sg.eastern_to_utc
check(E(dt.datetime(2026, 3, 8, 1, 59)) == dt.datetime(2026, 3, 8, 6, 59, tzinfo=dt.timezone.utc)
      and E(dt.datetime(2026, 3, 8, 3, 0)) == dt.datetime(2026, 3, 8, 7, 0, tzinfo=dt.timezone.utc)
      and E(dt.datetime(2026, 11, 1, 1, 0)) == dt.datetime(2026, 11, 1, 5, 0, tzinfo=dt.timezone.utc)
      and E(dt.datetime(2026, 11, 1, 2, 0)) == dt.datetime(2026, 11, 1, 7, 0, tzinfo=dt.timezone.utc),
      "US Eastern DST edges: 2nd Sunday of March, 1st Sunday of November")

# ---- helpers and the default fetch
check(sg.parse_ts("2026-11-20T14:05:29+09:00") == dt.datetime(2026, 11, 20, 5, 5, 29, tzinfo=dt.timezone.utc)
      and sg.parse_ts("2026-11-20T04:00:00Z").hour == 4 and sg.parse_ts("x") is None, "timestamps")


class Resp:
    def __init__(self, body):
        self.body, self.headers = body, {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen = []
sg.urllib.request.urlopen = lambda req, timeout=None: (seen.append((req.get_header("User-agent"), req.get_header("Accept-encoding"),
                                                                    timeout)), Resp(gzip.compress(b"<alerts></alerts>")))[1]
check(sg._fetch(sg.NTAS_URL) == b"<alerts></alerts>" and seen == [(sg.UA, "gzip", 30)] and "GroundTruth" in sg.UA,
      "default fetch: honest UA, gzip, 30 s timeout")
sg.urllib.request.urlopen = no_network

print("     radiation summary:", json.dumps(r["summary"], ensure_ascii=False)[:300])
print("     tsunami item:", json.dumps(sk, ensure_ascii=False)[:300])
print("     ofac item:", json.dumps(first, ensure_ascii=False)[:300])
shutil.rmtree(TMP, ignore_errors=True)
print("%d checks passed" % ok)
