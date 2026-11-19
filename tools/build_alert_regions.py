#!/usr/bin/env python3
"""Build web/geo/alert-regions.json, the region shapes for the air-raid alert layer. v1.0, 2026-11-18.

Input: Natural Earth 10m admin-1 (public domain), the GeoJSON from
https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_admin_1_states_provinces.geojson
Output: Ukraine's oblasts (with Crimea and Sevastopol, keyed by their UA- ISO codes), Russia's federal
subjects and Poland's voivodeships, simplified (Douglas-Peucker) and rounded to 3 decimals.

  python3 -I tools/build_alert_regions.py /path/to/ne_10m_admin_1_states_provinces.geojson

Feature id = ISO 3166-2 code. Properties: c (UA / RU / PL), en, uk (Ukrainian name, as alerts.in.ua writes it),
pl (Polish name, voivodeships only). gt/alerts.py matches alert names against uk / pl / en.
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "geo", "alert-regions.json")

# Natural Earth slips, fixed here: Moscow city and oblast carry each other's ISO codes, Altai Krai is
# labelled as the Altai Republic, and Kyiv oblast and city share the name "Київ".
FIX = {
    "RU-MOW": {"id": "RU-MOS", "en": "Moscow Oblast", "uk": "Московська область"},
    "RU-MOS": {"id": "RU-MOW", "en": "Moscow", "uk": "Москва"},
    "RU-ALT": {"en": "Altai Krai", "uk": "Алтайський край"},
    "UA-32": {"en": "Kyiv Oblast", "uk": "Київська область"},
    "UA-30": {"en": "Kyiv", "uk": "м. Київ"},
}
TOL = {"UA": 0.006, "PL": 0.008, "RU": 0.02}       # degrees; Russia is huge, so coarser
MIN_AREA = {"UA": 0.0004, "PL": 0.0004, "RU": 0.01}  # square degrees; drops specks and small islands


def _perp(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplify(pts, tol):
    """Iterative Douglas-Peucker on an open polyline."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        best, k = 0.0, None
        for m in range(i + 1, j):
            dd = _perp(pts[m], pts[i], pts[j])
            if dd > best:
                best, k = dd, m
        if k is not None and best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, f in zip(pts, keep) if f]


def ring_area(r):
    return abs(sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1))) / 2


def clean_ring(r, tol):
    s = simplify(r, tol)
    out = []
    for x, y in s:
        q = [round(x, 3), round(y, 3)]
        if not out or q != out[-1]:
            out.append(q)
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def main(src):
    d = json.load(open(src, encoding="utf-8"))
    feats = []
    for f in d["features"]:
        p = f["properties"]
        iso = p.get("iso_3166_2") or ""
        if p.get("adm0_a3") not in ("UKR", "RUS", "POL") or not p.get("name_uk"):
            continue
        c = iso[:2]
        if c not in ("UA", "RU", "PL"):
            continue
        fix = FIX.get(iso, {})
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        tol, min_area = TOL[c], MIN_AREA[c]
        big = max((poly[0] for poly in polys), key=len)
        cx, cy = sum(p[0] for p in big) / len(big), sum(p[1] for p in big) / len(big)
        if c == "RU" and (cx > 56 or cy > 62):  # Siberia, the Far East and the Arctic: far from any alert, keep them light
            tol, min_area = 0.06, 0.05
        out = []
        for poly in polys:
            outer = clean_ring(poly[0], tol)
            if not outer or ring_area(outer) < min_area:
                continue
            holes = [h for h in (clean_ring(r, tol) for r in poly[1:]) if h and ring_area(h) >= min_area]
            out.append([outer] + holes)
        if not out:
            continue
        props = {"id": fix.get("id", iso), "c": c, "en": fix.get("en", p.get("name_en") or p.get("name")),
                 "uk": fix.get("uk", p["name_uk"])}
        if c == "PL":
            props["pl"] = p.get("name_pl")
        geom = {"type": "Polygon", "coordinates": out[0]} if len(out) == 1 else {"type": "MultiPolygon", "coordinates": out}
        feats.append({"type": "Feature", "id": props["id"], "properties": props, "geometry": geom})
    feats.sort(key=lambda x: x["id"])
    ids = [x["id"] for x in feats]
    assert len(ids) == len(set(ids)), "duplicate region ids"
    fc = {"type": "FeatureCollection",
          "source": "Natural Earth 10m admin-1 (public domain), simplified by tools/build_alert_regions.py 1.0",
          "features": feats}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))
    by = {}
    for x in feats:
        by[x["properties"]["c"]] = by.get(x["properties"]["c"], 0) + 1
    print("wrote %s: %d regions %s, %.0f KB" % (os.path.relpath(OUT, ROOT), len(feats), by, os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
