"""Offline reverse geocoding to country, sea area and theatre.

Uses Natural Earth 1:50m admin-0 polygons (public domain) with a bbox prefilter.
Points at sea fall through to named sea boxes, then to the nearest country within ~1.5 deg.
"""
import json
import math
import os

REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ref", "ne_50m_countries.geojson")

THEATRES = {
    "ukraine-russia": "Ukraine – Russia",
    "europe-nato": "Europe / NATO",
    "middle-east": "Middle East / Gulf",
    "south-asia": "South & Central Asia",
    "indo-pacific": "Indo-Pacific",
    "americas": "Americas / US",
    "africa": "Africa",
    "other": "Other",
}

UA_RU = {"UKR", "RUS", "BLR", "MDA"}
MIDEAST = {"IRN", "IRQ", "ISR", "PSX", "PSE", "GAZ", "WEB", "LBN", "SYR", "JOR", "SAU", "ARE", "QAT",
           "BHR", "KWT", "OMN", "YEM", "EGY"}
EUROPE_EXTRA = {"TUR", "GEO", "ARM", "AZE", "CYP", "CYN", "GRL", "ISL"}
SOUTH_ASIA = {"PAK", "IND", "AFG", "BGD", "LKA", "NPL", "BTN", "MDV", "KAZ", "UZB", "TKM", "KGZ", "TJK"}
INDO_PAC = {"CHN", "TWN", "JPN", "KOR", "PRK", "PHL", "VNM", "MNG", "LAO", "KHM", "THA", "MMR", "MYS",
            "SGP", "IDN", "BRN", "TLS", "PNG", "AUS", "NZL", "HKG", "MAC"}

# (lon_min, lat_min, lon_max, lat_max, name, theatre) - most specific first
SEAS = [
    (34.8, 45.2, 39.5, 47.3, "Sea of Azov", "ukraine-russia"),
    (27.0, 40.5, 42.0, 47.0, "Black Sea", "ukraine-russia"),
    (54.5, 25.0, 57.5, 27.2, "Strait of Hormuz", "middle-east"),
    (47.5, 23.5, 56.5, 30.5, "Persian Gulf", "middle-east"),
    (56.0, 21.0, 62.5, 26.5, "Gulf of Oman", "middle-east"),
    (42.5, 11.0, 44.5, 13.5, "Bab el-Mandeb", "middle-east"),
    (32.0, 13.0, 44.0, 30.0, "Red Sea", "middle-east"),
    (43.0, 10.0, 52.0, 15.5, "Gulf of Aden", "middle-east"),
    (52.0, 5.0, 75.0, 25.0, "Arabian Sea", "middle-east"),
    (28.0, 30.5, 36.5, 37.0, "Eastern Mediterranean", "middle-east"),
    (-6.0, 30.0, 28.0, 46.0, "Mediterranean", "europe-nato"),
    (9.0, 53.0, 31.0, 66.0, "Baltic Sea", "europe-nato"),
    (-4.0, 51.0, 9.0, 61.0, "North Sea", "europe-nato"),
    (-10.0, 61.0, 60.0, 82.0, "Norwegian / Barents Sea", "europe-nato"),
    (117.0, 21.5, 122.5, 26.5, "Taiwan Strait", "indo-pacific"),
    (105.0, 0.0, 121.0, 23.0, "South China Sea", "indo-pacific"),
    (121.0, 23.0, 132.0, 35.0, "East China Sea", "indo-pacific"),
    (127.0, 33.0, 142.0, 52.0, "Sea of Japan", "indo-pacific"),
    (-98.0, 8.0, -58.0, 31.0, "Caribbean / Gulf of Mexico", "americas"),
    (-30.0, 30.0, -5.0, 72.0, "North Atlantic (east)", "europe-nato"),
    (-80.0, 20.0, -30.0, 72.0, "North Atlantic (west)", "americas"),
]

_polys = None


def _load():
    global _polys
    if _polys is not None:
        return _polys
    with open(REF, encoding="utf-8") as fh:
        fc = json.load(fh)
    out = []
    for f in fc["features"]:
        p = f["properties"]
        g = f["geometry"]
        if not g:
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        a3 = p.get("ADM0_A3") or p.get("ISO_A3")
        for poly in polys:
            ring = poly[0]
            xs = [c[0] for c in ring]
            ys = [c[1] for c in ring]
            out.append((min(xs), min(ys), max(xs), max(ys), ring, poly[1:], a3, p.get("NAME"), p.get("CONTINENT")))
    _polys = out
    return out


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def country_at(lon, lat):
    for (x0, y0, x1, y1, ring, holes, a3, name, cont) in _load():
        if x0 <= lon <= x1 and y0 <= lat <= y1 and _in_ring(lon, lat, ring):
            if any(_in_ring(lon, lat, h) for h in holes):
                continue
            return a3, name, cont
    return None


def _nearest_country(lon, lat, max_deg=1.5):
    best = None
    for (x0, y0, x1, y1, ring, holes, a3, name, cont) in _load():
        if x0 - max_deg > lon or x1 + max_deg < lon or y0 - max_deg > lat or y1 + max_deg < lat:
            continue
        step = max(1, len(ring) // 400)
        for k in range(0, len(ring), step):
            d = math.hypot((ring[k][0] - lon) * math.cos(math.radians(lat)), ring[k][1] - lat)
            if best is None or d < best[0]:
                best = (d, a3, name, cont)
    if best and best[0] <= max_deg:
        return best[1:]
    return None


def theatre_for_country(a3, continent):
    if a3 in UA_RU:
        return "ukraine-russia"
    if a3 in MIDEAST:
        return "middle-east"
    if a3 in SOUTH_ASIA:
        return "south-asia"
    if a3 in INDO_PAC:
        return "indo-pacific"
    if a3 in EUROPE_EXTRA or continent == "Europe":
        return "europe-nato"
    if continent in ("North America", "South America"):
        return "americas"
    if continent == "Africa":
        return "africa"
    if continent == "Oceania":
        return "indo-pacific"
    return "other"


def locate(lon, lat):
    """Return dict(country, country_name, sea, theatre) for a coordinate."""
    hit = country_at(lon, lat)
    if hit:
        a3, name, cont = hit
        return {"country": a3, "country_name": name, "sea": None, "theatre": theatre_for_country(a3, cont)}
    for (x0, y0, x1, y1, sea, th) in SEAS:
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            near = _nearest_country(lon, lat, 0.6)
            return {"country": near[0] if near else None, "country_name": near[1] if near else None,
                    "sea": sea, "theatre": th}
    near = _nearest_country(lon, lat)
    if near:
        a3, name, cont = near
        return {"country": a3, "country_name": name, "sea": "offshore", "theatre": theatre_for_country(a3, cont)}
    return {"country": None, "country_name": None, "sea": "open ocean", "theatre": "other"}


# ---------- country shapes and name/code lookup (0.4.0: outages and travel advisories) ----------

_shapes = None
# Names the US State Department (and others) use that Natural Earth spells differently.
NAME_ALIASES = {
    "burma": "MMR", "myanmar": "MMR", "cote d'ivoire": "CIV", "côte d'ivoire": "CIV", "turkey": "TUR", "türkiye": "TUR",
    "the bahamas": "BHS", "bahamas": "BHS", "the gambia": "GMB", "gambia": "GMB", "north korea": "PRK",
    "south korea": "KOR", "democratic republic of the congo": "COD", "republic of the congo": "COG",
    "czechia": "CZE", "czech republic": "CZE", "eswatini": "SWZ", "cabo verde": "CPV", "timor-leste": "TLS",
    "west bank": "PSX", "gaza": "PSX", "palestinian territories": "PSX", "macau": "MAC", "hong kong": "HKG",
    "mainland china": "CHN", "china": "CHN", "russia": "RUS", "laos": "LAO", "vietnam": "VNM", "syria": "SYR",
    "iran": "IRN", "united kingdom": "GBR", "north macedonia": "MKD", "micronesia": "FSM", "sao tome and principe": "STP",
    "são tomé and príncipe": "STP", "saint kitts and nevis": "KNA", "saint vincent and the grenadines": "VCT",
    "saint lucia": "LCA", "antigua and barbuda": "ATG", "trinidad and tobago": "TTO", "bosnia and herzegovina": "BIH",
    "brunei": "BRN", "kosovo": "KOS", "curacao": "CUW", "curaçao": "CUW", "taiwan": "TWN", "moldova": "MDA",
    "republic of congo": "COG", "naoero": "NRU", "nauru": "NRU",
}


def country_shapes():
    """{ADM0_A3: {"name", "a2", "continent", "names", "geom", "label"}}; geom is a light MultiPolygon for map fills,
    label a [lon, lat] point inside the country."""
    global _shapes
    if _shapes is not None:
        return _shapes
    with open(REF, encoding="utf-8") as fh:
        fc = json.load(fh)
    out = {}
    for f in fc["features"]:
        p, g = f["properties"], f["geometry"]
        a3 = p.get("ADM0_A3") or p.get("ISO_A3")
        if not g or not a3:
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        slim = [[[[round(x, 2), round(y, 2)] for x, y in ring[::3] + [ring[0]]] for ring in poly] for poly in polys]
        names = {(p.get(k) or "").lower() for k in ("NAME", "NAME_LONG", "ADMIN", "NAME_EN", "FORMAL_EN", "BRK_NAME",
                                                     "NAME_CIAWF", "NAME_SORT")} - {""}
        a2 = p.get("ISO_A2_EH") if p.get("ISO_A2_EH") not in (None, "-99") else p.get("ISO_A2")
        lx, ly = p.get("LABEL_X"), p.get("LABEL_Y")  # Natural Earth's own label point (0.12.0: news bubbles)
        out[a3] = {"name": p.get("NAME"), "a2": a2 if a2 != "-99" else None, "continent": p.get("CONTINENT"),
                   "names": names, "geom": {"type": "MultiPolygon", "coordinates": slim},
                   "label": [round(lx, 2), round(ly, 2)] if lx is not None and ly is not None else None}
    _shapes = out
    return out


def a3_for_a2(a2):
    if not a2:
        return None
    a2 = a2.upper()
    return next((a3 for a3, s in country_shapes().items() if s["a2"] == a2), None)


def a3s_for_name(name):
    """Country codes for a name such as "Israel, the West Bank and Gaza" or "Burma (Myanmar)"."""
    import re
    base = re.sub(r"\s*\(.*?\)", "", (name or "").replace("\u2019", "'")).strip().lower()
    base = re.sub(r"\s+travel advisory$", "", base)
    parts = [base] + [x.strip() for x in re.split(r",|\band\b|&", base) if x.strip()]
    found = []
    for part in parts:
        part = re.sub(r"^the\s+", "", part)
        a3 = NAME_ALIASES.get(part) or next((k for k, s in country_shapes().items() if part in s["names"]), None)
        if a3 and a3 not in found:
            found.append(a3)
        if part == base and found:
            break  # the whole name matched; don't also match its pieces
    return found


def theatre_for_a3(a3):
    s = country_shapes().get(a3) or {}
    return theatre_for_country(a3, s.get("continent"))
