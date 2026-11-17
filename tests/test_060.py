"""Offline tests for 0.6.0: military aircraft identity (gt/aircraft.py, feeds.mil_aircraft, server summary).
Never touches the network: ADS-B is the real adsb.lol /v2/mil answer saved on 2026-11-16 (tests/fixtures/adsb_mil.json),
hexdb answers are real records for six of those airframes (tests/fixtures/hexdb_sample.json; null = hexdb 404).

Run: python3 -I tests/test_060.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures")
os.environ["GT_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, PROJ)
from gt import aircraft, feeds  # noqa: E402

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


aircraft.urllib.request.urlopen = no_network
feeds.get = no_network
adsb = json.load(open(os.path.join(FX, "adsb_mil.json")))
HEXDB = json.load(open(os.path.join(FX, "hexdb_sample.json")))

# ---- roles: the registry name wins over the transponder's designator
C = aircraft.classify
check(C("B762", "Boeing KC-46A Pegasus") == "tanker", "KC-46A reporting B762 is a tanker, not an airliner")
check(C("A332", "Airbus Voyager KC3") == "tanker" and C("A332", "Airbus A330 243MRTT") == "tanker", "A330 MRTT / Voyager are tankers")
check(C("A332", "Airbus A330-243") == "jet", "a plain A330 stays a jet")
check(C("R135", "Boeing RC-135U") == "isr" and C("E3TF", "Boeing E-3G Sentry") == "isr" and C("P8", "Boeing P-8A Poseidon") == "isr",
      "RC-135, E-3, P-8 are ISR / patrol / AEW")
check(C("ATLA", "Breguet Atlantique ATL 2") == "isr", "Atlantique is maritime patrol")
check(C("C30J", "Lockheed MC-130J Commando II") == "transport", "MC-130J is not ISR (special-ops Hercules)")
check(C("C30J", "Lockheed KC-130J Super Hercules") == "tanker", "KC-130J is a tanker")
check(C("EC35", "Airbus EC135 P2+") == "helicopter", "EC135 is a helicopter, not an EC- ISR aircraft")
check(C("H60", "Sikorsky UH-60M Black Hawk") == "helicopter" and C("H47") == "helicopter", "Black Hawk and Chinook are helicopters")
check(C("V22", "Bell Boeing CV-22B Osprey") == "tiltrotor", "Osprey is a tiltrotor")
check(C("Q9", "General Atomics MQ-9A Reaper") == "drone" and C("Q4") == "drone", "Reaper and Global Hawk are drones")
check(C("B52", "Boeing B-52H Stratofortress") == "bomber", "B-52 is a bomber")
check(C("F16", "General Dynamics F-16C Fighting Falcon") == "fighter" and C("EUFI") == "fighter", "F-16 and Typhoon are fighters")
check(C("F2TH", "Dassault Falcon 2000") == "jet", "Falcon 2000 (F2TH) is a bizjet, not a fighter")
check(C("PC21") == "light" and C("A319", "Airbus ACJ319 115X") == "jet", "PC-21 trainer and ACJ319 VIP")
check(C("ZZZZ", None, "A7") == "helicopter" and C(None, None, "B6") == "drone" and C(None, None, "A1") == "light",
      "unknown designators fall back to the ADS-B emitter category")
check(C(None, None, None) == "other" and C("ZZZZ", "Mystery 1") == "other", "nothing known -> other")
check(all(r in aircraft.ROLES for r, _ in aircraft.TYPES.values()), "every table role has a label")

# ---- names
N = aircraft.type_name
check(N("KC46", "KC-46A Pegasus", "Boeing") == "Boeing KC-46A Pegasus", "maker put in front of the registry type")
check(N("A319", "Airbus ACJ319", "Airbus") == "Airbus ACJ319", "maker not doubled")
check(N("H47") == "Boeing CH-47 Chinook" and N("ZZZZ") is None and N(None) is None, "table name when the registry has none")

# ---- the registry cache
now = [1_000_000.0]
asked = []


def fake_fetch(hx):
    asked.append(hx)
    if hx == "boom":
        raise OSError("hexdb down")
    return HEXDB.get(hx)


path = os.path.join(os.environ["GT_DATA"], "reg.json")
reg = aircraft.Registry(path, fetch=fake_fetch, clock=lambda: now[0], sleep=lambda s: None)
st = reg.fill(["ae5f95", "ae59fe", "ae5f95", "ae01d5"], budget=2)
check(asked == ["ae5f95", "ae59fe"] and st == {"looked_up": 2, "waiting": 1, "known": 2}, "lookups capped per run, duplicates asked once")
check(reg.get("ae5f95")["type"] == "KC-46A Pegasus" and reg.get("ae59fe") is None and reg.fresh("ae59fe"),
      "a hexdb 404 is cached as a miss (not asked again) but returns nothing")
asked.clear()
reg.fill(["ae5f95", "ae59fe", "ae01d5"])
check(asked == ["ae01d5"], "cached airframes are not asked again")
asked.clear()
st = reg.fill(["boom", "ae1470"])
check(asked == ["boom"] and st["looked_up"] == 0 and "boom" not in reg.db, "a network error stops the run and caches nothing")
reg2 = aircraft.Registry(path, fetch=fake_fetch, clock=lambda: now[0], sleep=lambda s: None)
check(reg2.get("ae01d5")["owner"] == "United States Air Force", "the cache survives a restart (written to disk)")
now[0] += aircraft.MISS_TTL + 1
check(not reg2.fresh("ae59fe") and reg2.fresh("ae5f95"), "misses expire after 7 days, finds last 30")
now[0] += aircraft.FOUND_TTL
reg2.save()
check(reg2.db == {} and json.load(open(path)) == {}, "expired entries are pruned on save")
t0 = [0.0]
slow = aircraft.Registry(path + "2", fetch=lambda hx: (t0.__setitem__(0, t0[0] + 4), {"type": "X"})[1], clock=lambda: t0[0], sleep=lambda s: None)
slow.fill(["a%05d" % i for i in range(20)], deadline=9)
check(len(slow.db) == 3, "lookups stop at the per-run deadline (started at 0, 4 and 8 s of 9)")

# ---- the feed
feeds.get_json = lambda url, **k: adsb
feeds._REGISTRY = aircraft.Registry(os.path.join(feeds.CACHE, "aircraft_registry.json"), fetch=fake_fetch, sleep=lambda s: None)
asked.clear()
d = feeds.mil_aircraft()
fs = d["geojson"]["features"]
placed = [a for a in adsb["ac"] if a.get("lat") is not None]
check(d["source"] == "adsb.lol" and d["count"] == len(placed) == len(fs), "positions kept as before (%d placed)" % len(fs))
check(sum(d["roles"].values()) == d["count"] and all(f["properties"]["role"] in aircraft.ROLES for f in fs), "every aircraft has a role")
check(d["registry"]["looked_up"] == min(aircraft.BUDGET, len({f["properties"]["hex"] for f in fs})), "registry asked for new airframes")
by = {f["properties"]["hex"]: f["properties"] for f in fs}
if "ae5f95" in by:
    p = by["ae5f95"]
    check(p["role"] == "tanker" and p["tname"] == "Boeing KC-46A Pegasus" and p["icao_reg"] == "KC46" and p["type"] == "B762",
          "the KC-46 in the sample: tanker, real name, both designators kept")
heli = [p for p in by.values() if p.get("category") == "A7"]
check(heli and all(p["role"] in ("helicopter", "tiltrotor") for p in heli), "every A7 rotorcraft is drawn as a helicopter or tiltrotor")
feeds._REGISTRY.fetch = lambda hx: (_ for _ in ()).throw(OSError("down"))
feeds._REGISTRY.db.clear()
d2 = feeds.mil_aircraft()
check(d2["count"] == d["count"] and d2["registry"]["looked_up"] == 0, "hexdb down: positions and table roles still served")
adsb2 = dict(adsb, ac=[dict(a, hex="~" + a["hex"]) for a in adsb["ac"]])
feeds.get_json = lambda url, **k: adsb2
asked.clear()
feeds._REGISTRY.fetch = fake_fetch
feeds.mil_aircraft()
check(asked == [], "non-ICAO '~' addresses are never looked up")

# ---- server summary
feeds.get_json = lambda url, **k: adsb
import server  # noqa: E402
n = server._mil_notable(d)
check(n and all(x["role"] in server.NOTABLE_ROLES for x in n) and len(n) <= 15, "notable list holds tankers, ISR, drones, bombers only")
check([server.NOTABLE_ROLES.index(x["role"]) for x in n] == sorted(server.NOTABLE_ROLES.index(x["role"]) for x in n),
      "notable list sorted tankers first")
check(all(x["lat"] == round(x["lat"], 1) for x in n) and len(json.dumps(n)) < 3000, "positions rounded, small (%d chars)" % len(json.dumps(n)))
check(server._mil_notable({}) is None, "no feed -> None")
print("%d checks passed" % ok)
