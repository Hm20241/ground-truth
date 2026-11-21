#!/usr/bin/env python3
"""Build web/geo/theatres.json, the page's country -> theatre table. v1.1, 2026-11-20 (Ground Truth 1.2.0).

1.1: an ISO-2 code shared by several shapes goes to the largest (AU was Ashmore and Cartier Is., now Australia);
aliases for the names the State Department and EASA use that Natural Earth spells differently (Gaza, The West Bank,
Republic of Congo, The Kyrgyz Republic, Naoero, French Saint Martin). Caribbean overseas parts of France and the
Netherlands have no shape of their own at 1:50m, so they stay unplaced (Global only) rather than land in Europe.

The Feed tab merges items from every source; items that only name a country (US embassy alerts, internet outages,
cyber incidents, sanctions, advisories) follow the theatre filter through this table. It comes from the same
code the server uses to place wire stories (gt/geo.py theatre_for_a3 over ref/ne_50m_countries.geojson), so the
page and the server always agree.

  python3 -I tools/build_theatres.py          write the file
  python3 -I tools/build_theatres.py --check  exit 1 if the file is missing or out of date

Output: {"v": 1, "a3": {A3: [theatre, lon, lat, name]}, "a2": {A2: A3}, "names": {lower-case name: A3}}.
theatre is "" for countries outside every theatre (Antarctica, small territories); lon/lat is a label point
inside the country.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gt import geo  # noqa: E402

OUT = os.path.join(ROOT, "web", "geo", "theatres.json")
# names as the sources write them (lower case, straight apostrophes) -> ISO-3
ALIASES = {"gaza": "PSX", "gaza strip": "PSX", "the west bank": "PSX", "west bank": "PSX", "republic of congo": "COG",
           "the kyrgyz republic": "KGZ", "kyrgyz republic": "KGZ", "naoero": "NRU", "french saint martin": "MAF"}


def _area(geom):
    """Rough size of a shape: the sum of its rings' bounding boxes, in square degrees."""
    total = 0.0
    polys = geom["coordinates"] if geom.get("type") == "MultiPolygon" else [geom.get("coordinates") or []]
    for poly in polys:
        for ring in poly[:1]:
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            if xs:
                total += (max(xs) - min(xs)) * (max(ys) - min(ys))
    return total


def build():
    shapes = geo.country_shapes()
    a3, a2, names = {}, {}, {}
    size = {code: _area(shapes[code].get("geom") or {}) for code in shapes}
    for code in sorted(shapes):
        s = shapes[code]
        th = geo.theatre_for_a3(code)
        lon, lat = (s.get("label") or [None, None])[:2]
        a3[code] = [th if th != "other" else "", lon, lat, s.get("name") or code]
        if s.get("a2") and len(s["a2"]) == 2 and (s["a2"] not in a2 or size[code] > size[a2[s["a2"]]]):
            a2[s["a2"]] = code
        for n in sorted(s.get("names") or []):
            names.setdefault(n, code)
    for n, code in ALIASES.items():
        if code in a3:
            names.setdefault(n, code)
    return {"v": 1, "a3": a3, "a2": a2, "names": names}


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def main():
    text = dump(build())
    if "--check" in sys.argv:
        try:
            ok = open(OUT, encoding="utf-8").read() == text
        except OSError:
            ok = False
        print("theatres.json", "up to date" if ok else "OUT OF DATE: run python3 -I tools/build_theatres.py")
        return 0 if ok else 1
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    t = json.loads(text)
    print("wrote", OUT, len(text), "bytes,", len(t["a3"]), "countries,", len(t["names"]), "names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
