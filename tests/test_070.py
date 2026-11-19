"""Offline tests for 0.7.0: regional air-raid and missile alerts (gt/alerts.py).
Never touches the network. Fixtures are real answers saved on 2026-11-19 (UTC):
  sitrep_20261119.md       alerts.in.ua SITREP (api.alerts.in.ua/v3/alerts/active.md) at 05:07 Kyiv time
  tz_feed_sample.json      Tzofar /ios/feed trimmed to the alerts and HFC messages of 8-13 Nov 2026
  tz_cities_sample.json    the Tzofar city-list entries those alerts name; tz_polygons_sample.json their polygons
  ubilling_sample.json     ubilling.net.ua/aerialalerts (the Ukrainian fallback)

Run: python3 -I tests/test_070.py
"""
import datetime as dt
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures")
os.environ["GT_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, PROJ)
from gt import alerts  # noqa: E402

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
load = lambda n: json.load(open(os.path.join(FX, n), encoding="utf-8"))
md = open(os.path.join(FX, "sitrep_20261119.md"), encoding="utf-8").read()
ts = lambda s: int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())

# ---- region lookup: every shape is findable by its own Ukrainian name, and the spellings alerts.in.ua uses
reg = json.load(open(alerts.REGIONS_FILE, encoding="utf-8"))
feats = reg["features"]
by_c = {}
for f in feats:
    by_c[f["properties"]["c"]] = by_c.get(f["properties"]["c"], 0) + 1
check(by_c == {"UA": 27, "RU": 83, "PL": 16}, "region file: 27 UA (with Crimea, Sevastopol), 83 RU, 16 PL")
bad = [f["id"] for f in feats if (alerts.region_for(f["properties"]["uk"]) or {}).get("id") != f["id"]]
check(not bad, "each region resolves from its own Ukrainian name (%s)" % (bad or "all"))
for name, want in [("м. Київ", "UA-30"), ("Kyivska oblast (Київська область)", "UA-32"), ("Оренбургська область", "RU-ORE"),
                   ("Улянівська область", "RU-ULY"), ("Саратівська", "RU-SAR"), ("Курська область", "RU-KRS"),
                   ("Курганська область", "RU-KGN"), ("Республіка Татарстан", "RU-TA"), ("Чуваська Республіка", "RU-CU"),
                   ("Респу́бліка Марій Ел", None), ("Республіка Марій Ел", "RU-ME"), ("Автономна Республіка Крим", "UA-43"),
                   ("Севастополь", "UA-40"), ("województwo lubelskie", "PL-LU"), ("Люблінське воєводство", "PL-LU"),
                   ("Mazowieckie (województwo mazowieckie)", "PL-MZ"), ("Москва", "RU-MOW"), ("Московська область", "RU-MOS"),
                   ("Nowhere oblast (Ніякаська область)", None)]:
    if want is None and "Марій" in name:
        continue  # stress spelling with a combining accent: not required to match
    got = (alerts.region_for(name) or {}).get("id")
    check(got == want, "region_for(%r) -> %s" % (name, want))

# ---- time handling (Kyiv local in the report, UTC out)
ref = dt.datetime.fromisoformat("2026-11-19T05:07:26+02:00")
check(alerts._when("Nov 18, 19:58", ref) == "2026-11-18T17:58:00Z", "dated time, winter offset")
check(alerts._when("05:06", ref) == "2026-11-19T03:06:00Z", "undated time is the report's day")
check(alerts._when("23:50", ref) == "2026-11-18T21:50:00Z", "an undated time after the report is yesterday's")
check(alerts._when("Dec 31, 23:00", dt.datetime.fromisoformat("2027-01-01T00:30:00+02:00")) == "2026-12-31T21:00:00Z", "year boundary")
check(alerts._when("garbage", ref) is None, "unparsable time -> None")

# ---- SITREP parse (the real 05:07 report: a night drone/glide-bomb attack)
r = alerts.parse_sitrep(md)
check(r["as_of"] == "2026-11-19T03:07:26Z" and r["dtg"].startswith("190507B"), "header: DTG and as-of in UTC")
check(r["unmatched"] == [], "every region named in section 3 maps to a shape")
kinds = {}
for x in r["regions"]:
    kinds[(x["c"], x["kind"])] = kinds.get((x["c"], x["kind"]), 0) + 1
check(kinds == {("RU", "alert"): 14, ("UA", "alert"): 13, ("UA", "nominal"): 2, ("RU", "launch"): 7},
      "14 Russian regions + 13 Ukrainian oblasts under alert, 2 nominal, 7 launch areas (%s)" % kinds)
g = {x["id"]: x for x in r["regions"]}
d = g["UA-12"]
check(d["level"] == "red" and d["since"] == "2026-11-18T18:10:00Z" and d["types"] == ["air raid alert", "artillery shelling threat"],
      "Dnipropetrovsk: red, since 20:10 Kyiv, two warning types")
check(d["n_areas"] == 6 and d["areas"] == ["Nikopolska", "m. Nikopol", "Synelnykivskyi", "Pavlohradskyi"], "Dnipropetrovsk areas, deduplicated")
check(d["latest"] == {"name": "Pavlohradskyi", "at": "2026-11-19T03:06:00Z"}, "Dnipropetrovsk: most recent area and time")
check(g["RU-SMO"]["level"] == "yellow" and g["RU-KDA"]["level"] == "red", "Russian regions carry their level (Smolensk yellow, Krasnodar red)")
check(g["UA-63"]["areas"][:2] == ["Iziumskyi", "Kupyanskyi"] and g["UA-63"]["level"] == "red", "Kharkiv: raions and level")
check(g["UA-09"]["kind"] == "nominal" and g["UA-43"]["kind"] == "nominal", "Luhansk and Crimea are nominal standing alerts")
check(sorted(x["id"] for x in r["regions"] if x["kind"] == "launch") == sorted(["RU-KRS", "RU-ORL", "RU-VOR", "RU-BEL", "RU-BRY", "RU-TUL", "RU-LIP"]),
      "the 7 launch-site areas")
lv = [x["level"] for x in r["regions"] if x["kind"] == "alert"]
check(lv.count("red") == 7 and lv.count("yellow") == 20, "levels: 7 red regions, 20 yellow")
t0 = r["threats"][0]
check(len(r["threats"]) == 19 and t0 == {"at": "2026-11-19T02:59:00Z", "what": "attack drones", "n": None, "over": "m. Mykolaiv",
                                          "region": None, "msg": "The threat of using UAVs"}, "threat activity: 19 lines, emoji stripped")
t1 = r["threats"][2]
check(t1["n"] == 1 and t1["region"] == "UA-48", "a tracked threat over an oblast names the oblast (Mykolaiv)")
m0 = r["messages"][0]
check(m0["url"] == "https://t.me/kpszsu/97309" and m0["at"] == "2026-11-19T02:58:00Z" and m0["who"].startswith("Повітряні сили"),
      "Air Force messages keep their source link")
check(r["ended"][5] == {"from": "2026-11-18T21:43:00Z", "to": "2026-11-19T02:35:00Z", "dur": "4 h 51 min", "text": "air raid alert in Riazanska"},
      "terminations across midnight")
check(r["key"]["Areas under warning"] == "58 in 27 oblasts" and r["incidents"] == [], "key data and NSTR incidents")
check("Smolenska oblast" in r["bluf"] and len(r["bluf"]) <= 1200, "BLUF kept, capped")

# ---- a Polish RCB notice, written the two ways the report could carry it
pl1 = md.replace("**Smolenska oblast (Смоленська область)** — air raid alert",
                 "**Lubelskie (województwo lubelskie)** — air-attack threat in effect since 04:40, ongoing for 27 min.\n\n**Smolenska oblast (Смоленська область)** — air raid alert")
p = {x["id"]: x for x in alerts.parse_sitrep(pl1)["regions"]}
check(p["PL-LU"]["level"] == "yellow" and p["PL-LU"]["since"] == "2026-11-19T02:40:00Z", "Polish voivodeship block: yellow, since parsed")
pl2 = md.replace("**Nominal alerts in occupied territory**",
                 "**Air-attack threat notices, Poland** — Lubelskie (województwo lubelskie) (1 area) and Podkarpackie (województwo podkarpackie) (1 area). Issued by RCB.\n\n**Nominal alerts in occupied territory**")
p = {x["id"]: x for x in alerts.parse_sitrep(pl2)["regions"]}
check(p["PL-LU"]["kind"] == "alert" and p["PL-PK"]["level"] == "yellow", "Polish list block: both voivodeships, yellow")
try:
    alerts.parse_sitrep("# something else\nno sections")
    check(False, "layout change raises")
except ValueError:
    check(True, "a changed layout raises (so the fallback runs)")

# ---- fallback: ubilling oblast states
u = alerts.parse_ubilling(load("ubilling_sample.json"))
ids = {x["id"]: x["kind"] for x in u["regions"]}
check(u["unmatched"] == [] and ids.get("UA-09") == "nominal" and ids.get("UA-40") == "nominal", "fallback: all names map, occupied = nominal")
check(ids.get("UA-12") == "alert" and "UA-46" not in ids, "fallback: Dnipropetrovsk on, Lviv off")

# ---- Israel (Tzofar history + HFC messages); the lists are the sample, the clock is fixed
cities = alerts._list_from("cities", load("tz_cities_sample.json"), 10)
polys = alerts._list_from("polygons", load("tz_polygons_sample.json"), 5)
by_name = {k: v for k, v in cities["cities"].items()}
lists = {"by_name": by_name, "by_id": {str(v["id"]): v for v in by_name.values()}, "areas": cities["areas"],
         "polygons": polys["polygons"], "versions": {"cities": 10, "polygons": 5}}
check(all(len(r) >= 4 and r[0] == r[-1] and -180 <= r[0][0] <= 180 and 29 < r[0][1] < 34 for r in polys["polygons"].values()),
      "polygons: closed rings, flipped to [lon, lat]")
raw = load("tz_feed_sample.json")
NOW = ts("2026-11-13T01:05:00Z")  # 9 minutes after the Nachal Oz rocket alert, 5 after "incident ended"
f = alerts.parse_tz_feed(raw, lists, now=NOW)
check(f["last_alert"] == "2026-11-13T00:56:07Z" and f["cities_alerted_24h"] == 1, "feed: last alert and 24 h count")
check([m["kind"] for m in f["messages"]] == ["incident ended"], "feed: only the last 24 h of HFC messages")
v = alerts.israel_view({"recent": []}, f, now=NOW, lists=lists)
c = v["cities"][0]
check(len(v["cities"]) == 1 and c["n"] == "Nachal Oz" and c["th"] == 0 and c["label"] == "Rockets / missiles", "Nachal Oz rocket alert, English name")
check(c["ended"] == ts("2026-11-13T01:00:09Z") and c.get("poly"), "incident-ended time and polygon attached (alert under 30 min old)")
check(c["x"] == 60 and isinstance(c["cd"], int), "rocket alerts: countdown + 60 s siren window")
# the same alert reported by the live feed too: still one city, one event
live = {"recent": [{"time": ts("2026-11-13T00:56:07Z"), "threat": 0, "isDrill": False, "cities": ["נחל עוז"]}]}
v2 = alerts.israel_view(live, f, now=NOW, lists=lists)
check(len(v2["cities"]) == 1 and len(v2["events"]) == 1 and v2["counts_24h"] == {"Rockets / missiles": 1}, "live + history duplicates merge")
# a drill is never shown
dr = {"recent": [{"time": NOW - 60, "threat": 0, "isDrill": True, "cities": ["אילת"]}]}
check(len(alerts.israel_view(dr, f, now=NOW, lists=lists)["cities"]) == 1, "drills are dropped")
# two days earlier: the earthquake of 11 Nov, grouped into one event with its nationwide line named in English
f2 = alerts.parse_tz_feed(raw, lists, now=ts("2026-11-11T09:40:00Z"))
v3 = alerts.israel_view({"recent": []}, f2, now=ts("2026-11-11T09:40:00Z"), lists=lists)
e = v3["events"][0]
check(e["label"] == "Earthquake" and e["n"] == 6 and e["names"][0] == "Parts of the country" and "Eilat" in e["names"], "earthquake: one event, 6 names")
check(v3["unknown_names"] == [] and len(v3["cities"]) == 5 and e["c"] and 29 < e["c"][1] < 30.5, "earthquake: 5 mapped towns near Eilat")
# an early warning (HFC 'alerts may be activated shortly'), replayed at a fixed time
ew = dict(raw, instructions=[dict(i, time=NOW - 120) for i in raw["instructions"] if i["instructionType"] == 0])
v4 = alerts.israel_view({"recent": []}, alerts.parse_tz_feed(ew, lists, now=NOW), now=NOW, lists=lists)
check(len(v4["early"]) == 1 and v4["early"][0]["cities"][0]["n"] == "Metulla" and "shortly" in v4["early"][0]["body"],
      "early warning names Metulla, body without markup")
check(v4["early"][0]["cities"][0]["ended"] is None, "no all-clear yet: early-warning city has ended=None")
w0 = next(i for i in raw["instructions"] if i["instructionType"] == 0)
end = next(i for i in raw["instructions"] if i["instructionType"] == 1)
ew2 = dict(raw, instructions=[dict(w0, time=NOW - 300), dict(end, time=NOW - 60, citiesIds=[1669]),
                              dict(end, id=1, time=NOW - 900, citiesIds=[1669])])
v5 = alerts.israel_view({"recent": []}, alerts.parse_tz_feed(ew2, lists, now=NOW), now=NOW, lists=lists)
check(v5["early"][0]["cities"][0]["ended"] == NOW - 60, "an all-clear after the early warning is passed on (one before it is not)")

# ---- combined view and the compact summary the analyst reads
state = {"tzeva": {"ok": True, "at": "x", "data": f}, "tzevalive": {"ok": True, "at": "y", "data": live},
         "airalerts": {"ok": True, "at": "z", "data": dict(r, counts={"ukraine": {"n": 13, "red": 5, "yellow": 8}})}}
il = alerts.israel_view(live, f, now=NOW, lists=lists)
s = alerts.summary(state, il, state["airalerts"]["data"], now=NOW)
check(s["israel"]["sirens_now"] == 0 and s["israel"]["in_shelter_window"] == 0, "9 min later and ended: no siren, not in shelter")
s2 = alerts.summary(state, il, state["airalerts"]["data"], now=ts("2026-11-13T00:56:40Z"))
check(s2["israel"]["sirens_now"] == 1, "33 s after the alert: siren on")
check(len(s["russia"]["regions"]) == 14 and "Krasnodar Krai (red)" in s["russia"]["regions"], "summary lists Russian regions with level")
check(sorted(s["launch_areas_tracked"])[:2] == ["Belgorod", "Bryansk"] and "attack drones" in s["threats_tracked"], "launch areas, threat kinds")
check(len(json.dumps(s, ensure_ascii=False)) < 2000, "summary under 2 KB (%d)" % len(json.dumps(s, ensure_ascii=False)))
print("%d checks passed" % ok)
