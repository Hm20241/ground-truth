"""Military aircraft identity for the ADS-B layer, 1.0 (Ground Truth 0.6.0).

ADS-B only broadcasts an ICAO type designator ("C17", "K35R", "B762"), and sometimes the wrong one: the
USAF's KC-46A tankers report "B762". So each new airframe (by its 24-bit hex) is looked up once on hexdb.io
(free, keyless; registry type name, ICAO code and registered owner) and cached for 30 days, 7 days if hexdb
doesn't know it. The role (tanker, ISR, fighter, ...) drives the map icon and comes from, in order:
the registry type name, the designator table below, then the ADS-B emitter category.

Photos are NOT fetched here: Planespotters' terms want server clients to send a contact address, so the
browser asks Planespotters directly when a popup opens (see web/app.js).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

HEXDB = "https://hexdb.io/api/v2/aircraft/"
UA = "GroundTruth/0.6 (personal non-commercial OSINT dashboard)"
FOUND_TTL = 30 * 86400
MISS_TTL = 7 * 86400
BUDGET = 25          # lookups per feed run (the feed runs every 45 s)
DEADLINE = 9.0       # seconds of lookups per feed run at most
GAP = 0.2            # seconds between lookups

ROLES = {  # key: label (shown in the popup and the map key)
    "fighter": "fighter / attack", "bomber": "bomber", "tanker": "tanker", "transport": "transport",
    "isr": "ISR / patrol / AEW", "helicopter": "helicopter", "tiltrotor": "tiltrotor", "drone": "drone",
    "jet": "VIP / airliner / bizjet", "light": "trainer / light", "other": "type unknown",
}

# ICAO designator -> (role, name). Common military types; anything missing falls back to the registry name.
TYPES = {
    # tankers
    "K35R": ("tanker", "Boeing KC-135R Stratotanker"), "K35E": ("tanker", "Boeing KC-135E Stratotanker"),
    "KC46": ("tanker", "Boeing KC-46A Pegasus"), "KC10": ("tanker", "McDonnell Douglas KC-10 Extender"),
    "IL78": ("tanker", "Ilyushin Il-78 Midas"),
    # bombers
    "B52": ("bomber", "Boeing B-52 Stratofortress"), "B1": ("bomber", "Rockwell B-1B Lancer"),
    "B2": ("bomber", "Northrop B-2 Spirit"), "TU95": ("bomber", "Tupolev Tu-95 Bear"),
    "T160": ("bomber", "Tupolev Tu-160 Blackjack"), "TU22": ("bomber", "Tupolev Tu-22M Backfire"),
    # fighters, attack and jet trainers
    "F16": ("fighter", "General Dynamics F-16 Fighting Falcon"), "F15": ("fighter", "McDonnell Douglas F-15 Eagle"),
    "F18H": ("fighter", "Boeing F/A-18E/F Super Hornet"), "F18S": ("fighter", "McDonnell Douglas F/A-18 Hornet"),
    "F35": ("fighter", "Lockheed Martin F-35 Lightning II"), "F22": ("fighter", "Lockheed Martin F-22 Raptor"),
    "EUFI": ("fighter", "Eurofighter Typhoon"), "RFAL": ("fighter", "Dassault Rafale"), "GRIF": ("fighter", "Saab JAS 39 Gripen"),
    "TOR": ("fighter", "Panavia Tornado"), "MIR2": ("fighter", "Dassault Mirage 2000"), "A10": ("fighter", "Fairchild A-10 Thunderbolt II"),
    "F4": ("fighter", "McDonnell Douglas F-4 Phantom II"), "F5": ("fighter", "Northrop F-5"),
    "SU27": ("fighter", "Sukhoi Su-27 Flanker"), "SU30": ("fighter", "Sukhoi Su-30 Flanker"), "SU35": ("fighter", "Sukhoi Su-35 Flanker"),
    "SU34": ("fighter", "Sukhoi Su-34 Fullback"), "SU24": ("fighter", "Sukhoi Su-24 Fencer"), "SU25": ("fighter", "Sukhoi Su-25 Frogfoot"),
    "MG29": ("fighter", "Mikoyan MiG-29 Fulcrum"), "MG31": ("fighter", "Mikoyan MiG-31 Foxhound"),
    "T38": ("fighter", "Northrop T-38 Talon"), "HAWK": ("fighter", "BAE Systems Hawk"), "M346": ("fighter", "Leonardo M-346 Master"),
    "L159": ("fighter", "Aero L-159 Alca"), "L39": ("fighter", "Aero L-39 Albatros"), "T45": ("fighter", "Boeing T-45 Goshawk"),
    "ALPJ": ("fighter", "Dassault/Dornier Alpha Jet"), "HAR": ("fighter", "Harrier"),
    # transports
    "C17": ("transport", "Boeing C-17 Globemaster III"), "C5": ("transport", "Lockheed C-5 Galaxy"),
    "C5M": ("transport", "Lockheed C-5M Super Galaxy"), "A400": ("transport", "Airbus A400M Atlas"),
    "C130": ("transport", "Lockheed C-130 Hercules"), "C30J": ("transport", "Lockheed Martin C-130J Super Hercules"),
    "C160": ("transport", "Transall C-160"), "C295": ("transport", "Airbus C295"), "CN35": ("transport", "Airbus CN235"),
    "C27J": ("transport", "Leonardo C-27J Spartan"), "IL76": ("transport", "Ilyushin Il-76 Candid"),
    "A124": ("transport", "Antonov An-124 Ruslan"), "AN12": ("transport", "Antonov An-12 Cub"), "AN26": ("transport", "Antonov An-26 Curl"),
    "AN72": ("transport", "Antonov An-72 Coaler"), "Y20": ("transport", "Xian Y-20 Kunpeng"), "E390": ("transport", "Embraer C-390 Millennium"),
    "AT76": ("transport", "ATR 72"), "AT75": ("transport", "ATR 72"), "AT45": ("transport", "ATR 42"),
    # ISR, maritime patrol, AEW
    "R135": ("isr", "Boeing RC-135"), "E3TF": ("isr", "Boeing E-3 Sentry (AWACS)"), "E3CF": ("isr", "Boeing E-3 Sentry (AWACS)"),
    "E6": ("isr", "Boeing E-6 Mercury"), "E8": ("isr", "Northrop Grumman E-8 JSTARS"), "P8": ("isr", "Boeing P-8 Poseidon"),
    "P3": ("isr", "Lockheed P-3 Orion"), "P1": ("isr", "Kawasaki P-1"), "ATLA": ("isr", "Dassault Atlantique 2"),
    "E2": ("isr", "Northrop Grumman E-2 Hawkeye"), "E767": ("isr", "Boeing E-767 AWACS"), "E737": ("isr", "Boeing E-7 Wedgetail"),
    "U2": ("isr", "Lockheed U-2 Dragon Lady"), "A50": ("isr", "Beriev A-50 Mainstay"), "IL38": ("isr", "Ilyushin Il-38 May"),
    # helicopters and tiltrotors
    "H60": ("helicopter", "Sikorsky H-60 Black Hawk / Seahawk"), "H47": ("helicopter", "Boeing CH-47 Chinook"),
    "H53": ("helicopter", "Sikorsky H-53 Sea Stallion"), "H53S": ("helicopter", "Sikorsky CH-53E/K"),
    "H64": ("helicopter", "Boeing AH-64 Apache"), "H1": ("helicopter", "Bell H-1"), "UH1": ("helicopter", "Bell UH-1 Iroquois"),
    "EC35": ("helicopter", "Airbus H135"), "EC45": ("helicopter", "Airbus H145"), "EC25": ("helicopter", "Airbus H225 Super Puma"),
    "AS32": ("helicopter", "Airbus AS332 Super Puma"), "NH90": ("helicopter", "NHIndustries NH90"), "EH10": ("helicopter", "AgustaWestland AW101 Merlin"),
    "A139": ("helicopter", "Leonardo AW139"), "A149": ("helicopter", "Leonardo AW149"), "A169": ("helicopter", "Leonardo AW169"),
    "LYNX": ("helicopter", "Westland Lynx / Wildcat"), "AS65": ("helicopter", "Airbus AS365 Dauphin"), "S92": ("helicopter", "Sikorsky S-92"),
    "MI8": ("helicopter", "Mil Mi-8 Hip"), "MI24": ("helicopter", "Mil Mi-24 Hind"), "KA27": ("helicopter", "Kamov Ka-27 Helix"),
    "TIGR": ("helicopter", "Airbus Tiger"), "V22": ("tiltrotor", "Bell Boeing V-22 Osprey"),
    # drones
    "Q4": ("drone", "Northrop Grumman RQ-4 Global Hawk / MQ-4C Triton"), "Q9": ("drone", "General Atomics MQ-9 Reaper"),
    "Q1": ("drone", "General Atomics MQ-1 Predator"), "HRON": ("drone", "IAI Heron"), "TB2": ("drone", "Baykar Bayraktar TB2"),
    "HERM": ("drone", "Elbit Hermes"),
    # VIP, airliner and business jets
    "A319": ("jet", "Airbus A319"), "A320": ("jet", "Airbus A320"), "A321": ("jet", "Airbus A321"),
    "A332": ("jet", "Airbus A330-200"), "A333": ("jet", "Airbus A330-300"), "A343": ("jet", "Airbus A340-300"),
    "A345": ("jet", "Airbus A340-500"), "A359": ("jet", "Airbus A350-900"), "A310": ("jet", "Airbus A310"),
    "B737": ("jet", "Boeing 737-700"), "B738": ("jet", "Boeing 737-800"), "B38M": ("jet", "Boeing 737 MAX 8"),
    "B752": ("jet", "Boeing 757-200"), "B762": ("jet", "Boeing 767-200"), "B763": ("jet", "Boeing 767-300"),
    "B77W": ("jet", "Boeing 777-300ER"), "B744": ("jet", "Boeing 747-400"), "B748": ("jet", "Boeing 747-8"),
    "GLF4": ("jet", "Gulfstream IV"), "GLF5": ("jet", "Gulfstream V"), "GLF6": ("jet", "Gulfstream G650"),
    "GLEX": ("jet", "Bombardier Global Express"), "GL5T": ("jet", "Bombardier Global 5000"), "CL60": ("jet", "Bombardier Challenger 600"),
    "FA7X": ("jet", "Dassault Falcon 7X"), "FA8X": ("jet", "Dassault Falcon 8X"), "F900": ("jet", "Dassault Falcon 900"),
    "F2TH": ("jet", "Dassault Falcon 2000"), "C560": ("jet", "Cessna Citation V"), "C680": ("jet", "Cessna Citation Sovereign"),
    "LJ35": ("jet", "Learjet 35 (C-21)"), "E135": ("jet", "Embraer Legacy / ERJ-135"), "E145": ("jet", "Embraer ERJ-145"),
    "E190": ("jet", "Embraer E190"), "E35L": ("jet", "Embraer Legacy 600"), "H25B": ("jet", "Hawker 800"),
    # trainers and light / utility aircraft
    "PC21": ("light", "Pilatus PC-21"), "PC7": ("light", "Pilatus PC-7"), "PC9": ("light", "Pilatus PC-9"),
    "PC12": ("light", "Pilatus PC-12"), "TEX2": ("light", "Beechcraft T-6 Texan II"), "CT4": ("light", "Pacific Aerospace CT-4 Airtrainer"),
    "G120": ("light", "Grob G 120"), "G115": ("light", "Grob G 115"), "TUCA": ("light", "Embraer Tucano"),
    "SR22": ("light", "Cirrus SR22"), "DA42": ("light", "Diamond DA42"), "DA62": ("light", "Diamond DA62"),
    "BE20": ("light", "Beechcraft King Air 200 (C-12)"), "B350": ("light", "Beechcraft King Air 350"), "B190": ("light", "Beechcraft 1900"),
    "C208": ("light", "Cessna 208 Caravan"), "DHC6": ("light", "de Havilland Canada DHC-6 Twin Otter"), "D228": ("light", "Dornier 228"),
    "BN2P": ("light", "Britten-Norman Islander"), "P68": ("light", "Vulcanair P.68"),
}

# Registry type names beat designators: airliner and bizjet airframes are flown as tankers, ISR and drones.
_NAME_RULES = [
    ("tanker", r"\bKC-|MRTT|Voyager|Tanker|Pegasus|Ph[eé]nix|Il-78|Extender"),
    ("drone", r"Reaper|Predator|Global Hawk|Triton|Heron|Hermes|Bayraktar|\b[RM]Q-\d|\bUAV\b|Drone|Watchkeeper|Protector"),
    ("bomber", r"\bB-(1|2|21|52)[A-Z]?\b|Stratofortress|Lancer|Spirit|Tu-95|Tu-160|Tu-22"),
    ("isr", r"\b(RC|EC|WC|OC|EP|E|P)-\d|AWACS|Sentry|Hawkeye|Poseidon|Orion|Rivet|Wedgetail|Sentinel|JSTARS|Mercury|Atlantique|"
            r"Airseeker|Erieye|GlobalEye|Dragon Lady|Mainstay|Compass Call"),
    ("tiltrotor", r"Osprey|V-22|Tiltrotor"),
    ("helicopter", r"helicopter|Chinook|Black Hawk|Blackhawk|Seahawk|Apache|Merlin|Wildcat|Puma|Lynx|Huey|Cobra|Kiowa|Sea King|"
                   r"Cougar|NH ?90|\b[UCAMHSR]H-\d|\bAW1\d\d|\bH1[2-7]\d\b|\bH2\d\d\b|Mi-\d|Ka-\d"),
    ("fighter", r"\bF-\d|F/A-18|Eurofighter|Typhoon|Rafale|Gripen|Tornado|Harrier|Su-\d|MiG-|Mirage|\bA-10|Alpha Jet|\bT-38|"
                r"Talon|Goshawk|M-346|Hawk T"),
    ("transport", r"Globemaster|Galaxy|Hercules|Atlas|A400|Il-76|C-295|CN-?235|Spartan|C-27|Transall|An-\d|Y-20|C-390|Millennium"),
]
_NAME_RULES = [(role, re.compile(rx, re.I)) for role, rx in _NAME_RULES]
_NOT_ISR = re.compile(r"\bMC-130|\bEC-?135\b", re.I)  # special-ops Hercules is a transport; EC135 is a helicopter


def classify(icao=None, name=None, category=None):
    """Pure: the icon role for one aircraft."""
    if name:
        for role, rx in _NAME_RULES:
            if rx.search(name) and not (role == "isr" and _NOT_ISR.search(name)):
                return role
    if icao and icao.upper() in TYPES:
        return TYPES[icao.upper()][0]
    if category == "A7":
        return "helicopter"
    if category == "B6":
        return "drone"
    if category == "A1":
        return "light"
    return "other"


def type_name(icao=None, registry=None, manufacturer=None):
    """Best human name: the registry's ("KC-46A Pegasus", with the maker in front), else the table's."""
    if registry:
        reg = registry.strip()
        if manufacturer and not reg.lower().startswith(manufacturer.lower()):
            return "%s %s" % (manufacturer.strip(), reg)
        return reg
    if icao and icao.upper() in TYPES:
        return TYPES[icao.upper()][1]
    return None


class Registry:
    """hexdb lookups, cached on disk per hex. Used only by the mil feed thread (one at a time)."""

    def __init__(self, path, fetch=None, clock=time.time, sleep=time.sleep):
        self.path, self.clock, self.sleep = path, clock, sleep
        self.fetch = fetch or _hexdb
        try:
            self.db = json.load(open(path))
        except (OSError, ValueError):
            self.db = {}

    def fresh(self, hx):
        e = self.db.get(hx)
        return bool(e) and self.clock() - e["t"] < (FOUND_TTL if e.get("ok") else MISS_TTL)

    def fill(self, hexes, budget=BUDGET, deadline=DEADLINE):
        """Look up hexes not cached yet, within the budget and deadline. Stops at the first network error."""
        t0, done, todo = self.clock(), 0, [h for h in dict.fromkeys(hexes) if h and not self.fresh(h)]
        for hx in todo[:budget]:
            if self.clock() - t0 > deadline:
                break
            try:
                rec = self.fetch(hx)
            except Exception:
                break  # hexdb down or slow: try again next run, keep what we have
            self.db[hx] = dict(rec or {}, t=self.clock(), ok=rec is not None)
            done += 1
            self.sleep(GAP)
        if done:
            self.save()
        return {"looked_up": done, "waiting": max(0, len(todo) - done), "known": len(self.db)}

    def save(self):
        now = self.clock()
        keep = {h: e for h, e in self.db.items() if now - e["t"] < (FOUND_TTL if e.get("ok") else MISS_TTL)}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(keep, fh, separators=(",", ":"))
        os.replace(tmp, self.path)
        self.db = keep

    def get(self, hx):
        e = self.db.get(hx)
        return e if e and e.get("ok") else None


def _hexdb(hx):
    """One hexdb v2 lookup: the record, or None if hexdb has no such aircraft. Raises on network trouble."""
    req = urllib.request.Request(HEXDB + urllib.request.quote(hx), headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return {"type": d.get("type"), "icao": d.get("icao_type_code"), "mfr": d.get("manufacturer"),
            "owner": d.get("registered_owner"), "reg": d.get("registration")}


def enrich(props, reg_entry):
    """Pure: add role, type name and operator to one mil feature's properties."""
    r = reg_entry or {}
    icao = r.get("icao") or props.get("type")
    name = type_name(icao, r.get("type"), r.get("mfr"))
    props["role"] = classify(icao, name, props.get("category"))
    props["tname"] = name
    if r.get("owner"):
        props["owner"] = r["owner"]
    if r.get("icao") and r["icao"] != props.get("type"):
        props["icao_reg"] = r["icao"]  # what the registry says when the transponder's designator differs
    if not props.get("reg") and r.get("reg"):
        props["reg"] = r["reg"]
    return props
