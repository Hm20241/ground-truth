"""Offline tests for 0.13.0 airspace signals (gt/airspace.py): emergency squawks, GPSJAM GNSS interference, FAA TFRs.
Never touches the network: sockets are blocked and every fetch is a fake that serves fixtures by URL.
Fixtures (tests/fixtures/airspace/) are SYNTHETIC: the exact structure of the live responses checked on 2026-11-20,
with invented hexes, registrations, NOTAM numbers, places and coordinates (over open water or empty land):
  sqk_lol_<code>.json / sqk_fi_<code>.json   readsb /v2/sqk/<code> snapshots (adsb.lol / adsb.fi)
  gpsjam_manifest*.csv                       manifest.csv (served gzip; raw() gzips it); *_next adds 2026-11-20
  gpsjam_<date>-h3_4.csv                     daily hex files (served gzip), level edge cases + 3 malformed rows
  tfr_list.json                              tfrapi/getTfrList (5 TFRs + 1 malformed id)
  tfr_wfs.json                               GeoServer WFS TFR:V_TFR_LOC, EPSG:4326
  tfr_detail_6_000N.xml                      XNOTAM-Update detail XML (BOM, CIR / GRC+CWA / no shape)

Run: python3 -I tests/test_airspace.py
"""
import datetime as dt
import gzip
import json
import math
import os
import shutil
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "airspace")
TMP = tempfile.mkdtemp(prefix="gt-airspace-")
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import airspace as A  # noqa: E402

A.urllib.request.urlopen = no_network
SLEEPS = []
A._sleep = SLEEPS.append

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def raw(name):
    """Fixture bytes. GPSJAM serves gzip; its fixtures are kept as plain CSV (the public audit refuses binaries)
    and gzipped here, so the code under test still sees the bytes as served."""
    if name.endswith(".csv.gz"):
        with open(os.path.join(FX, name[:-3]), "rb") as fh:
            return gzip.compress(fh.read(), mtime=0)
    with open(os.path.join(FX, name), "rb") as fh:
        return fh.read()


def raises(fn, exc, text=""):
    try:
        fn()
    except exc as e:
        return text in str(e)
    return False


def at(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def wipe(name):
    p = A._path(name)
    if os.path.exists(p):
        os.remove(p)


def size(d):
    return len(json.dumps(d, separators=(",", ":")).encode())


def nm(a, b):
    return A._bearing_nm(a, b)[1]


def signed_area(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:])) / 2


NOW = at("2026-11-20T12:00:00Z")
CONTRACT = ("version", "fetched_at", "count", "sources", "attribution")
check(A.CACHE == os.path.join(TMP, "cache"), "cache under GT_DATA/cache (the feeds.CACHE folder)")

# ================= squawk =================
SQK = {(p, c): raw("sqk_%s_%s.json" % ("lol" if p == "adsb.lol" else "fi", c)) for p in ("adsb.lol", "adsb.fi")
       for c in ("7500", "7600", "7700")}


def sqk_fetch(log, down=(), ac=None, now_ms=None, bad=()):
    """down: providers that fail; bad: (provider, code) answering junk; ac: code -> replacement ac list."""
    def fetch(url):
        prov = "adsb.lol" if "adsb.lol" in url else "adsb.fi"
        code = url.rsplit("/", 1)[1]
        log.append((prov, code))
        assert url in (A.SQK_PROVIDERS[0][1] + code, A.SQK_PROVIDERS[1][1] + code), url
        if prov in down:
            raise urllib.error.URLError("%s down" % prov)
        if (prov, code) in bad:
            return b"<html>502 Bad Gateway</html>"
        d = json.loads(SQK[(prov, code)])
        if ac is not None and code in ac:
            d["ac"] = ac[code]
        if now_ms is not None:
            d["now"] = now_ms
        return json.dumps(d).encode()
    return fetch


wipe("squawk")
log = []
d = A.squawk(now=NOW, fetch=sqk_fetch(log))
check(log == [("adsb.lol", "7500"), ("adsb.lol", "7600"), ("adsb.lol", "7700")] and not SLEEPS,
      "normal poll: 3 adsb.lol calls, adsb.fi untouched, no waiting")
check(all(k in d for k in CONTRACT) and d["version"] == "1.0" and d["fetched_at"] == "2026-11-20T12:00:00Z",
      "squawk: contract keys, version 1.0, fetched_at = now")
check(d["count"] == 4 and d["recent"] == 4 and d["by_code"] == {"7500": 1, "7600": 0, "7700": 3},
      "4 squawking now: 3 on 7700, 1 on 7500, 7600 empty (empty lists are normal)")
lol, fi = d["sources"]
check(lol["name"] == "adsb.lol" and lol["ok"] is True and lol["n"] == 4 and lol["codes"] == ["7500", "7600", "7700"]
      and lol["newest"] == "2026-11-20T12:00:00Z", "adsb.lol source: ok, n, codes, newest from the snapshot `now`")
check(fi["name"] == "adsb.fi" and fi["ok"] is None and fi["n"] == 0, "adsb.fi listed as not needed (ok None)")
check(d["attribution"] == "ADS-B data: adsb.lol (ODbL)" and d["public_ok"] is True, "attribution adsb.lol (ODbL), public")
items = {i["hex"]: i for i in d["items"]}
c, m, n_, h = items["f0a001"], items["f0a002"], items["f0a003"], items["f0a004"]
check(c["flight"] == "TST101" and c["reg"] == "X-TEST1" and c["type"] == "A320" and c["squawk"] == "7700"
      and c["meaning"] == "general emergency" and c["emergency"] == "general" and c["mil"] is False,
      "civil 7700: callsign trimmed, reg, type, meaning, readsb emergency field")
check(c["pos"] == [34.0, 43.5] and c["sea"] == "Black Sea" and c["theatre"] == "ukraine-russia"
      and "country" in c and "country_name" in c, "geo.locate fields on the last position (Black Sea)")
check(c["first_seen"] == "2026-11-20T11:59:59Z" and c["pos_time"] == "2026-11-20T11:59:58Z" and c["polls"] == 1,
      "times from snapshot now - seen / seen_pos")
check(m["mil"] is True and m["stale_pos"] is True and m["pos"] == [18.2, 35.1] and m["pos_time"] == "2026-11-20T11:55:00Z",
      "dbFlags & 1 = military; lastPosition used and flagged stale")
check(c["stale_pos"] is False and h["mlat"] is True and h["meaning"] == "hijack / unlawful interference"
      and h["emergency"] is None, "MLAT 7500 without an emergency field kept, flagged mlat")
check(n_["pos"] is None and n_["current"] is True, "aircraft with no position: listed, not mapped")
feats = d["geojson"]["features"]
check(d["geojson"]["type"] == "FeatureCollection" and len(feats) == 3
      and {f["properties"]["hex"] for f in feats} == {"f0a001", "f0a002", "f0a004"}
      and all(f["geometry"]["type"] == "Point" and "trail" not in f["properties"] for f in feats),
      "geojson: Points for the 3 current aircraft with a position")
check(json.loads(json.dumps(d)) == d and size(d) < 300000, "squawk payload JSON-serialisable, < 300 KB")

# second poll a minute later: the civil aircraft moved, the 7500 one is gone
moved = dict(json.loads(SQK[("adsb.lol", "7700")])["ac"][0], lat=43.6, lon=34.2)
mil_ac, nopos_ac = json.loads(SQK[("adsb.lol", "7700")])["ac"][1:]
T2 = NOW + dt.timedelta(seconds=60)
d2 = A.squawk(now=T2, fetch=sqk_fetch([], ac={"7700": [moved, mil_ac, nopos_ac], "7500": []}, now_ms=int(T2.timestamp() * 1000)))
i2 = {i["hex"]: i for i in d2["items"]}
check(d2["count"] == 3 and d2["recent"] == 4 and i2["f0a004"]["current"] is False and i2["f0a001"]["current"] is True,
      "gone from the list: kept in the 6 h memory, current False")
check(i2["f0a001"]["polls"] == 2 and i2["f0a001"]["first_seen"] == "2026-11-20T11:59:59Z"
      and [p[:2] for p in i2["f0a001"]["trail"]] == [[34.0, 43.5], [34.2, 43.6]] and i2["f0a001"]["pos"] == [34.2, 43.6],
      "merge: polls counted, first_seen kept, trail grows when the position changes")
check(len(i2["f0a002"]["trail"]) == 1, "unchanged position adds no trail point")
check([i["current"] for i in d2["items"]] == [True, True, True, False], "items: current first, then most recent")
mem = json.load(open(A._path("squawk")))
check(set(mem["aircraft"]) == {"f0a001", "f0a002", "f0a003", "f0a004"} and not os.path.exists(A._path("squawk") + ".tmp"),
      "memory written atomically to airspace_squawk.json")

# trail capped at 20 points
t = T2
for k in range(25):
    t += dt.timedelta(seconds=60)
    a = dict(moved, lat=43.6 + 0.01 * (k + 1))
    d3 = A.squawk(now=t, fetch=sqk_fetch([], ac={"7700": [a], "7500": []}, now_ms=int(t.timestamp() * 1000)))
tr = {i["hex"]: i for i in d3["items"]}["f0a001"]["trail"]
check(len(tr) == A.TRAIL_MAX == 20 and tr[-1][1] == round(43.6 + 0.25, 4), "trail keeps the newest 20 points")

# 6 h memory: everything ages out
late = NOW + dt.timedelta(hours=6, minutes=30)
d4 = A.squawk(now=late, fetch=sqk_fetch([], ac={"7700": [], "7500": []}, now_ms=int(late.timestamp() * 1000)))
check(d4["count"] == 0 and d4["recent"] == 0 and d4["items"] == [] and d4["geojson"]["features"] == [],
      "after 6 h with no sightings the memory is empty")

# failover: adsb.lol down -> adsb.fi, spaced 1.1 s, lol tried only once
wipe("squawk")
log, SLEEPS[:] = [], []
d = A.squawk(now=NOW, fetch=sqk_fetch(log, down=("adsb.lol",)))
check(log == [("adsb.lol", "7500"), ("adsb.fi", "7500"), ("adsb.fi", "7600"), ("adsb.fi", "7700")],
      "adsb.lol fails once -> skipped for the rest of the poll, adsb.fi serves all three codes")
check(SLEEPS == [A.FI_GAP, A.FI_GAP] and A.FI_GAP >= 1.0, "adsb.fi calls spaced >= 1 s (its 1 request/s limit)")
lol, fi = d["sources"]
check(lol["ok"] is False and "down" in lol["error"] and fi["ok"] is True and fi["n"] == 1,
      "sources: adsb.lol error recorded, adsb.fi ok")
check(d["count"] == 1 and d["items"][0]["source"] == "adsb.fi" and d["items"][0]["sea"] == "Baltic Sea"
      and "adsb.fi" in d["attribution"] and d["attribution"].startswith("ADS-B data: adsb.lol (ODbL)"),
      "fallback aircraft served; attribution names adsb.fi")

# partial: junk from adsb.lol on 7600 only
wipe("squawk")
log, SLEEPS[:] = [], []
d = A.squawk(now=NOW, fetch=sqk_fetch(log, bad=(("adsb.lol", "7600"),)))
check(log == [("adsb.lol", "7500"), ("adsb.lol", "7600"), ("adsb.fi", "7600"), ("adsb.fi", "7700")]
      and SLEEPS == [A.FI_GAP], "junk body (no ac[]) = failure; failover from that code on")
check(d["sources"][0]["ok"] is False and d["sources"][0]["codes"] == ["7500"] and d["codes_missing"] == []
      and d["count"] == 2, "partial failure: still a full result, per-provider codes recorded")

# one code lost on both providers
wipe("squawk")
d = A.squawk(now=NOW, fetch=sqk_fetch([], bad=(("adsb.lol", "7700"), ("adsb.fi", "7700"))))
check(d["codes_missing"] == ["7700"] and d["count"] == 1, "a code no provider answered is reported in codes_missing")

# all fail -> raise, memory untouched
A.squawk(now=NOW, fetch=sqk_fetch([]))
before = open(A._path("squawk")).read()
check(raises(lambda: A.squawk(now=NOW, fetch=sqk_fetch([], down=("adsb.lol", "adsb.fi"))), RuntimeError,
             "all ADS-B providers failed"), "both providers down: the feed raises (server keeps the last data)")
check(open(A._path("squawk")).read() == before, "failed poll leaves the memory file alone")

# a burst far beyond reality (150 aircraft x 25 polls) stays capped and under 300 KB
wipe("squawk")
base = json.loads(SQK[("adsb.lol", "7700")])["ac"][0]
t = NOW
for k in range(25):
    t += dt.timedelta(seconds=60)
    burst = [dict(base, hex="f1%04x" % j, lat=40 + j * 0.01 + k * 0.001, lon=20 + j * 0.01) for j in range(150)]
    d = A.squawk(now=t, fetch=sqk_fetch([], ac={"7700": burst, "7500": []}, now_ms=int(t.timestamp() * 1000)))
check(d["recent"] == A.MEMORY_MAX == 120 and d["count"] == 150 and size(d) < 300000,
      "burst of 150 aircraft: memory capped at 120, payload %d bytes < 300 KB" % size(d))

# merge_sightings is pure and prunes by last_seen
mem, cur = A.merge_sightings({"old": {"hex": "old", "last_seen": 0, "first_seen": 0, "polls": 1, "squawks": [], "trail": []}},
                             [], NOW.timestamp())
check(mem == {} and cur == [], "merge_sightings drops entries older than 6 h")

# ================= gpsjam =================
DAY19, DAY20 = raw("gpsjam_2026-11-19-h3_4.csv.gz"), raw("gpsjam_2026-11-20-h3_4.csv.gz")


def gj_fetch(log, manifest="gpsjam_manifest.csv.gz", fail=()):
    def fetch(url):
        log.append(url)
        if url == A.GPSJAM_MANIFEST:
            if "manifest" in fail:
                raise urllib.error.URLError("manifest down")
            return raw(manifest)
        if "day" in fail:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
        if url == A.GPSJAM_DAY % "2026-11-19":
            return DAY19
        if url == A.GPSJAM_DAY % "2026-11-20":
            return DAY20
        raise AssertionError("unexpected url " + url)
    return fetch


man = A.parse_manifest(gzip.decompress(raw("gpsjam_manifest.csv.gz")).decode())
check(man[0] == ("2022-02-14", True, 89) and man[-1] == ("2026-11-19", False, 589), "manifest parsed by column name, oldest first")
check(raises(lambda: A.parse_manifest("when,what\n1,2\n"), ValueError, "date column"), "manifest without a date column rejected")
check([A.level(98, 2), A.level(0, 1), A.level(1, 1), A.level(500, 0)] == ["low"] * 4,
      "low: < 2 % after GPSJAM's bad - 1 (a lone bad aircraft is damped away)")
check([A.level(97, 3), A.level(90, 10), A.level(47, 3)] == ["medium"] * 3, "medium: 2 % (boundary) up to < 10 %")
check([A.level(89, 11), A.level(8, 2), A.level(3, 40)] == ["high"] * 3, "high: 10 % (boundary) and above")
p = A.parse_day(DAY19)
check(p["levels"] == {"low": 4, "medium": 3, "high": 3} and p["hexes_total"] == 10 and p["rows_skipped"] == 3,
      "day file: gzip CSV parsed, per-level counts over all hexes, 3 malformed rows skipped")
check([h[0] for h in p["items"]] == ["841e00fffffffff", "841e00bffffffff", "841e00dffffffff", "841e009ffffffff",
                                     "841e013ffffffff", "841e007ffffffff"],
      "only medium + high kept: high first, by share, then by aircraft count")
check(p["items"][0] == ["841e00fffffffff", "high", 3, 40], "row = [h3, level, good, bad]")
check(A.parse_day(gzip.decompress(DAY19))["levels"] == p["levels"], "plain (un-gzipped) CSV parses the same")
pc = A.parse_day(DAY19, cap=2)
check(len(pc["items"]) == 2 and pc["cap"]["dropped"] == 4 and pc["items"][1][1] == "high" and "high before medium"
      in pc["cap"]["order"], "cap: keeps the worst hexes, reports how many were dropped and the rule")

wipe("gpsjam")
log = []
g = A.gpsjam(now=NOW, fetch=gj_fetch(log))
check(log == [A.GPSJAM_MANIFEST, A.GPSJAM_DAY % "2026-11-19"], "first poll: manifest, then the newest day file")
check(all(k in g for k in CONTRACT) and g["date"] == "2026-11-19" and g["count"] == 6 and g["suspect"] is False
      and g["levels"]["high"] == 3 and g["items_format"] == ["h3", "level", "good", "bad"] and g["resolution"] == 4,
      "gpsjam output: date, count of kept hexes, levels, item format")
ms, ds = g["sources"]
check(ms["name"] == "manifest" and ms["ok"] and ms["fetched"] and ms["newest"] == "2026-11-19" and ms["n"] == 4
      and ds["name"] == "day" and ds["ok"] and ds["fetched"] and ds["newest"] == "2026-11-19" and ds["n"] == 10,
      "gpsjam sources: manifest and day, both fetched and ok")
check(g["public_ok"] is False and g["non_commercial"] is True and "GPSJAM" in g["attribution"]
      and g["colours"] == {"low": "#33ff33", "medium": "#ffff33", "high": "#ff3333"}, "private, non-commercial, GPSJAM colours")

log = []
g2 = A.gpsjam(now=NOW + dt.timedelta(hours=1), fetch=gj_fetch(log))
check(log == [] and g2["items"] == g["items"] and g2["sources"][0]["fetched"] is False,
      "yesterday's file is in: no manifest read until the next UTC day (cached result served)")
log = []
g3 = A.gpsjam(now=at("2026-11-21T00:30:00Z"), fetch=gj_fetch(log))
check(log == [A.GPSJAM_MANIFEST] and g3["date"] == "2026-11-19", "next day: manifest read, no new date -> no day download")
log = []
A.gpsjam(now=at("2026-11-21T01:00:00Z"), fetch=gj_fetch(log, "gpsjam_manifest_next.csv.gz"))
check(log == [], "manifest read at most once an hour (30 min later: skipped)")
log = []
g4 = A.gpsjam(now=at("2026-11-21T01:30:00Z"), fetch=gj_fetch(log, "gpsjam_manifest_next.csv.gz"))
check(log == [A.GPSJAM_MANIFEST, A.GPSJAM_DAY % "2026-11-20"] and g4["date"] == "2026-11-20" and g4["suspect"] is True
      and g4["count"] == 1 and g4["items"] == [["841e021ffffffff", "high", 10, 9]],
      "new date in the manifest -> that day downloaded once; GPSJAM's suspect flag carried")
log = []
A.gpsjam(now=at("2026-11-21T03:00:00Z"), fetch=gj_fetch(log, "gpsjam_manifest_next.csv.gz"))
check(log == [], "processed date never downloaded again")

# day file failure keeps the last good day, retries hourly, 3 tries per date
wipe("gpsjam")
A.gpsjam(now=NOW, fetch=gj_fetch([]))
log = []
f1 = A.gpsjam(now=at("2026-11-21T01:30:00Z"), fetch=gj_fetch(log, "gpsjam_manifest_next.csv.gz", fail=("day",)))
check(log == [A.GPSJAM_MANIFEST, A.GPSJAM_DAY % "2026-11-20"] and f1["date"] == "2026-11-19"
      and f1["sources"][1]["ok"] is False and "503" in f1["sources"][1]["error"],
      "day download fails: the last good day stays, the error is in sources")
log = []
f2 = A.gpsjam(now=at("2026-11-21T01:40:00Z"), fetch=gj_fetch(log, "gpsjam_manifest_next.csv.gz", fail=("day",)))
check(log == [] and f2["sources"][1]["ok"] is False, "no retry within the hour")
for hh in ("02:31", "03:32"):
    A.gpsjam(now=at("2026-11-21T%s:00Z" % hh), fetch=gj_fetch([], "gpsjam_manifest_next.csv.gz", fail=("day",)))
log = []
A.gpsjam(now=at("2026-11-21T05:00:00Z"), fetch=gj_fetch(log, "gpsjam_manifest_next.csv.gz"))
check(A.GPSJAM_DAY % "2026-11-20" not in log, "after 3 failed tries a date is not downloaded again")

# manifest failure
wipe("gpsjam")
check(raises(lambda: A.gpsjam(now=NOW, fetch=gj_fetch([], fail=("manifest",))), RuntimeError, "no day processed yet"),
      "first ever poll with the manifest down: raises")
log = []
check(raises(lambda: A.gpsjam(now=NOW + dt.timedelta(minutes=5), fetch=gj_fetch(log)), RuntimeError) and log == [],
      "a failed manifest read still counts toward the once-an-hour limit")
A.gpsjam(now=NOW + dt.timedelta(hours=1), fetch=gj_fetch([]))
st = json.load(open(A._path("gpsjam")))
st["manifest"]["t"] -= 7200
st["result"]["date"] = "2026-11-18"
json.dump(st, open(A._path("gpsjam"), "w"))
g5 = A.gpsjam(now=NOW + dt.timedelta(hours=1), fetch=gj_fetch([], fail=("manifest", "day")))
check(g5["sources"][0]["ok"] is False and "manifest down" in g5["sources"][0]["error"] and g5["date"] == "2026-11-18",
      "manifest down with a cached day: feed still answers, manifest error reported")
check(json.loads(json.dumps(g)) == g and size(g) < 300000, "gpsjam payload JSON-serialisable, < 300 KB")
huge = "hex,count_good_aircraft,count_bad_aircraft\n" + "".join("84%013x,%d,%d\n" % (j, j % 50, 99) for j in range(9000))
wipe("gpsjam")
gh = A.gpsjam(now=NOW, fetch=lambda u: raw("gpsjam_manifest.csv.gz") if u == A.GPSJAM_MANIFEST else gzip.compress(huge.encode()))
check(gh["count"] == A.HEX_CAP == 5000 and gh["cap"]["dropped"] == 4000 and size(gh) < 300000,
      "9,000 bad hexes: capped at 5,000, payload %d bytes < 300 KB" % size(gh))

# ================= tfr =================
TFR = {A.TFR_LIST: raw("tfr_list.json"), A.TFR_WFS: raw("tfr_wfs.json")}
XML = {n: raw("tfr_detail_6_%s.xml" % n) for n in ("0001", "0002", "0003", "0005")}


def tfr_fetch(log, fail=(), lst=None, xml_down=False):
    def fetch(url):
        log.append(url)
        if url in TFR:
            if (url == A.TFR_LIST and "list" in fail) or (url == A.TFR_WFS and "wfs" in fail):
                raise urllib.error.URLError("faa down")
            return lst if (url == A.TFR_LIST and lst is not None) else TFR[url]
        assert url.startswith("https://tfr.faa.gov/download/detail_6_") and url.endswith(".xml"), url
        if xml_down:
            raise urllib.error.URLError("timed out")
        n = url[-8:-4]
        if n not in XML:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return XML[n]
    return fetch


def xml_calls(log):
    return [u.rsplit("detail_", 1)[1] for u in log if "detail_" in u]


lst = A.parse_list(json.loads(TFR[A.TFR_LIST]))
check([t["notam_id"] for t in lst] == ["6/0001", "6/0002", "6/0003", "6/0004", "6/0005"] and lst[1]["is_new"] is True
      and lst[1]["mod"] == "202611200403", "TFR list parsed; malformed notam_id ('../0006') dropped")
check(A._mod_iso("202611200403") == "2026-11-20T04:03:00Z" and A._utc_iso("2026-11-21T06:00:00") == "2026-11-21T06:00:00Z",
      "mod_abs_time and XNOTAM times read as UTC")
w = A.parse_wfs(json.loads(TFR[A.TFR_WFS]))
check(set(w) == {"6/0001", "6/0002", "6/0004", "6/0005"} and len(w["6/0002"]["rings"]) == 2
      and len(w["6/0001"]["rings"][0]) == 37 and w["6/0004"]["type"] == "VIP", "WFS: shapes grouped per NOTAM (lon/lat)")

# geometry
d1 = A.parse_detail(XML["0001"])
a1 = d1["areas"][0]
ring = a1["rings"][0]
check(d1["notam_id"] == "6/0001" and d1["effective"] == "2026-11-19T05:00:00Z" and d1["expires"] == "2026-11-29T05:00:00Z"
      and d1["tz"] == "UTC" and d1["cfr"] == "91.137(a)(1)" and d1["issued"] == "2026-11-18T21:31:00Z",
      "detail XML (with BOM): id, issued, effective, expires, time zone, CFR part")
check(a1["geom"] == "circle" and a1["circle"] == {"lon": -90.5, "lat": 27.5, "r_nm": 3.0}, "single CIR shape -> circle")
check(len(ring) == A.CIRCLE_POINTS + 1 == 65 and ring[0] == ring[-1] and len({tuple(p) for p in ring}) == 64,
      "circle -> closed 64-point ring")
check(all(abs(nm([-90.5, 27.5], p) - 3.0) < 0.01 for p in ring) and signed_area(ring) > 0,
      "every vertex 3.0 NM from the centre; counter-clockwise (RFC 7946)")
check(a1["floor"]["text"] == "SFC" and a1["ceiling"]["text"] == "5000 ft AGL" and a1["ceiling"]["ref"] == "HEI",
      "floor SFC, ceiling 5000 ft AGL")
check(len(d1["text"]) <= A.TEXT_MAX + 3 and d1["text"].startswith("!FDC 6/0001") and d1["text"].endswith("..."),
      "NOTAM text kept, truncated")
d2_ = A.parse_detail(XML["0002"])
aa, ab = d2_["areas"]
check(aa["geom"] == "merged" and aa["floor"]["text"] == "2400 ft MSL" and aa["ceiling"]["text"] == "FL180"
      and ab["scheduled"] and ab["days"] == ["Tuesday", "Thursday"] and ab["effective"] == "2026-11-25T11:00:00Z",
      "multi-area TFR: merged ring, MSL / FL limits, per-area schedule and days")
import xml.etree.ElementTree as ET  # noqa: E402
root = ET.fromstring(XML["0002"][3:])
shape = A._shape_ring(next(root.iter("aseShapes")).find("Abd").findall("Avx"))
centre = [-88.0, 29.0]
arcpts = shape[2:-1]
check(shape[0] == shape[-1] and len(arcpts) >= 30 and all(abs(nm(centre, p) - 11.0) < 0.01 for p in arcpts)
      and all(p[0] < -88.0 for p in arcpts), "CWA arc drawn from S to N clockwise: 11 NM from the centre, west side")
check(max(min(nm(p, q) for p in shape) for q in aa["rings"][0]) < 0.01,
      "every vertex of the (10-degree) merged ring lies on the drawn (5-degree) arc")
d3_ = A.parse_detail(XML["0003"])
check(d3_["areas"][0]["geom"] == "none" and d3_["areas"][0]["rings"] == [] and d3_["areas"][0]["ceiling"]["text"] == "UNL"
      and d3_["expires"] is None, "nationwide notice: no geometry, FL999 = UNL, open-ended")
check(raises(lambda: A.parse_detail(b"<html>maintenance</html>"), ValueError, "Not"), "non-XNOTAM body rejected")

# full polls
wipe("tfr")
A.DETAIL_BUDGET = 2
log, SLEEPS[:] = [], []
r = A.tfr(now=NOW, fetch=tfr_fetch(log))
check(log[:2] == [A.TFR_LIST, A.TFR_WFS] and xml_calls(log) == ["6_0002.xml", "6_0001.xml"] and SLEEPS == [A.DETAIL_GAP],
      "first poll: list, shapes, then XML for the newest changes only, within the per-poll budget (2 here)")
check(all(k in r for k in CONTRACT) and r["count"] == 5 and r["sources"][2]["pending"] == 3 and r["sources"][2]["n"] == 2
      and r["sources"][2]["ok"] is True, "tfr: 5 TFRs, 2 details fetched, 3 pending")
it = {i["notam_id"]: i for i in r["items"]}
check(it["6/0001"]["status"] == "active" and it["6/0001"]["geom"] == "faa_xml" and it["6/0001"]["floor"] == "SFC"
      and it["6/0001"]["ceiling"] == "5000 ft AGL" and it["6/0001"]["url"] == "https://tfr.faa.gov/tfr3/?page=detail_6_0001",
      "TFR with XML: status, limits, FAA page link")
check(it["6/0004"]["status"] == "unknown" and it["6/0004"]["geom"] == "faa_wfs" and it["6/0004"]["has_shape"]
      and it["6/0004"]["floor"] is None, "TFR without XML yet: WFS polygon, status unknown, no limits")
check(it["6/0003"]["has_shape"] is False and it["6/0003"]["geom"] is None, "no-shape TFR listed without geometry")
fs = r["geojson"]["features"]
circ = [f for f in fs if f["properties"]["notam_id"] == "6/0001"]
check(len(circ) == 1 and circ[0]["properties"]["geom"] == "circle" and len(circ[0]["geometry"]["coordinates"][0]) == 65
      and circ[0]["properties"]["ceiling"] == "5000 ft AGL", "geojson: XML circle replaces the 37-point WFS ring")
b = [f["properties"] for f in fs if f["properties"]["notam_id"] == "6/0002"]
check([(p["area"], p["status"]) for p in b] == [("Area A", "active"), ("Area B", "upcoming")]
      and b[1]["days"] == ["Tuesday", "Thursday"], "one feature per area, each with its own status")
check(it["6/0001"]["centre"] and it["6/0001"]["theatre"] == "americas", "TFR centre placed with geo.locate")

log = []
r2 = A.tfr(now=NOW + dt.timedelta(minutes=15), fetch=tfr_fetch(log))
check(xml_calls(log) == ["6_0005.xml", "6_0003.xml"], "second poll: cached XML not refetched, next 2 pending fetched")
log = []
r3 = A.tfr(now=NOW + dt.timedelta(minutes=30), fetch=tfr_fetch(log))
check(xml_calls(log) == ["6_0004.xml"] and r3["sources"][2]["error"].startswith("6/0004 HTTPError"),
      "third poll: the last one, a 404, recorded")
it3 = {i["notam_id"]: i for i in r3["items"]}
check(it3["6/0005"]["status"] == "expired" and it3["6/0003"]["status"] == "active" and it3["6/0004"]["status"] == "unknown"
      and r3["by_status"] == {"active": 3, "upcoming": 0, "expired": 1, "unknown": 1} and r3["with_shape"] == 4,
      "statuses: expired, open-ended active, 404 -> WFS only")
check([i["status"] for i in r3["items"]] == ["active", "active", "active", "unknown", "expired"]
      and [i["notam_id"] for i in r3["items"]][:3] == ["6/0002", "6/0001", "6/0003"],
      "items sorted active, upcoming, unknown, expired; newest change first within a status")
log = []
A.tfr(now=NOW + dt.timedelta(hours=1), fetch=tfr_fetch(log))
check(xml_calls(log) == [], "404 not retried within 6 h; nothing else due")
log = []
A.tfr(now=NOW + dt.timedelta(hours=7), fetch=tfr_fetch(log))
check(xml_calls(log) == ["6_0004.xml"], "404 retried after 6 h")

# changed TFR -> refetch just that one
lst_mod = json.loads(TFR[A.TFR_LIST])
lst_mod[0]["mod_abs_time"] = "202611201130"
log = []
A.tfr(now=NOW + dt.timedelta(hours=8), fetch=tfr_fetch(log, lst=json.dumps(lst_mod).encode()))
check(xml_calls(log) == ["6_0001.xml"], "mod_abs_time changed -> only that TFR's XML refetched")

# network trouble on XML: stop after 3 consecutive errors, retry after an hour
wipe("tfr")
A.DETAIL_BUDGET = 30
log = []
r = A.tfr(now=NOW, fetch=tfr_fetch(log, xml_down=True))
check(len(xml_calls(log)) == A.DETAIL_MAX_NET_ERRORS == 3 and r["sources"][2]["ok"] is False and r["count"] == 5
      and r["with_shape"] == 4 and all(i["status"] == "unknown" for i in r["items"]),
      "XML server down: 3 tries then stop; WFS shapes still shown")
log = []
A.tfr(now=NOW + dt.timedelta(minutes=15), fetch=tfr_fetch(log))
check(xml_calls(log) == ["6_0003.xml", "6_0004.xml"],
      "failed XML not retried for an hour (only the never-tried ones, newest change first)")

# list / shapes failures
wipe("tfr")
A.tfr(now=NOW, fetch=tfr_fetch([]))
r = A.tfr(now=NOW + dt.timedelta(minutes=15), fetch=tfr_fetch([], fail=("list",)))
check(r["sources"][0]["ok"] is False and r["sources"][0]["stale_since"] == "2026-11-20T12:00:00Z" and r["count"] == 5,
      "list down: last good list used, stale_since reported")
r = A.tfr(now=NOW + dt.timedelta(minutes=30), fetch=tfr_fetch([], fail=("wfs",)))
check(r["sources"][1]["ok"] is False and r["sources"][1]["n"] == 5 and r["with_shape"] == 4,
      "shapes down: last good WFS shapes used")
wipe("tfr")
r = A.tfr(now=NOW, fetch=tfr_fetch([], fail=("list",)))
check(r["count"] == 4 and r["sources"][0]["ok"] is False, "list down with no cache: TFRs built from the WFS shapes")
wipe("tfr")
check(raises(lambda: A.tfr(now=NOW, fetch=tfr_fetch([], fail=("list", "wfs"))), RuntimeError, "both failed"),
      "list and shapes down, nothing cached: raises")

# a TFR that leaves the list is dropped from the detail cache
wipe("tfr")
A.tfr(now=NOW, fetch=tfr_fetch([]))
short = json.dumps(json.loads(TFR[A.TFR_LIST])[:2]).encode()
r = A.tfr(now=NOW + dt.timedelta(minutes=15), fetch=tfr_fetch([], lst=short))
check(set(json.load(open(A._path("tfr")))["details"]) == {"6/0001", "6/0002"} and r["count"] == 2,
      "cancelled TFRs pruned from the cache")
check(json.loads(json.dumps(r)) == r and size(r) < 300000 and r["public_ok"] is True and r["non_commercial"] is False
      and "FAA" in r["attribution"], "tfr payload JSON-serialisable, < 300 KB, public domain")

# ================= module contract =================
check(A.VERSION == "1.0" and set(A.FEEDS) == {"squawk", "gpsjam", "tfr"}
      and A.FEEDS["squawk"] == (A.squawk, 60) and A.FEEDS["gpsjam"] == (A.gpsjam, 3600) and A.FEEDS["tfr"] == (A.tfr, 900),
      "FEEDS: squawk 60 s, gpsjam 3600 s, tfr 900 s")
check(all(n.isalpha() and n.islower() for n in A.FEEDS) and set(A.PUBLIC_OK) == set(A.FEEDS) == set(A.NON_COMMERCIAL)
      and isinstance(A.LICENCE, dict) and all(k in A.ATTRIBUTION for k in A.FEEDS), "names [a-z]+; per-feed flags and terms")
check("@" not in A.UA and "mailto" not in A.UA.lower(), "generic User-Agent, no contact details")


class FakeResp:
    def __init__(self, body, enc):
        self.body, self.headers = body, {"Content-Encoding": enc} if enc else {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


SEEN = []


def fake_urlopen(req, timeout=None):
    SEEN.append((req.full_url, req.get_header("User-agent"), req.get_header("Accept-encoding"), timeout))
    return FakeResp(gzip.compress(b"hello") if "gz" in req.full_url else b"plain", "gzip" if "gz" in req.full_url else None)


A.urllib.request.urlopen = fake_urlopen
check(A._fetch("https://example.invalid/gz") == b"hello" and A._fetch("https://example.invalid/x", 10) == b"plain"
      and SEEN[0][1] == A.UA and SEEN[0][2] == "gzip" and SEEN[0][3] == A.TIMEOUT <= 20 and SEEN[1][3] == 10,
      "_fetch: generic UA, asks for gzip, decodes Content-Encoding gzip, timeout <= 20 s")
A.urllib.request.urlopen = no_network
from gt import feeds  # noqa: E402
check(not set(A.FEEDS) & set(feeds.REGISTRY), "no clash with gt/feeds.py REGISTRY")
import inspect  # noqa: E402
check(all(list(inspect.signature(fn).parameters) == ["now", "fetch"] for fn, _ in A.FEEDS.values()),
      "every feed callable is (now=None, fetch=None)")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d checks passed" % ok)
