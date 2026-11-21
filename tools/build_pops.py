"""Build ref/cf_pops.json: Cloudflare PoP code -> [lon, lat, city, country ISO-3]. v1.0, 2026-11-21 (Ground Truth 1.5.3).

gt/services.py pins Cloudflare incidents that name a PoP ("... Washington, DC datacenter (IAD)") at that PoP.

Inputs
* Cloudflare's component list: the live https://www.cloudflarestatus.com/api/v2/summary.json, or a saved copy
  (--summary FILE). PoP components are named "City, Country - (IATA)" (348 on 2026-11-21).
* OurAirports airports.csv (public domain, https://davidmegginson.github.io/ourairports-data/airports.csv, ~12.8 MB):
  downloaded once per run, or read from --airports FILE.
* web/geo/theatres.json for ISO alpha-2 -> alpha-3.

Lookup per PoP code: the airport whose iata_code is the code (large > medium > small > other types, closed last);
else an airport that lists the code among its keywords (old codes Cloudflare still uses: Berlin TXL, Bishkek FRU,
Chisinau KIV, Americana QWJ); else MANUAL below (Jiaxing JXG has no airport). The country comes from the airport,
the city name from Cloudflare's component name. Coordinates are rounded to 3 decimals (~100 m): an airport near the
PoP's metro, which is all a map pin needs. Codes it cannot place are printed and left out.

Run:  python3 -I tools/build_pops.py [--summary FILE] [--airports FILE] [--out ref/cf_pops.json]
"""
import argparse
import csv
import gzip
import io
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY_URL = "https://www.cloudflarestatus.com/api/v2/summary.json"
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
THEATRES = os.path.join(ROOT, "web", "geo", "theatres.json")
OUT = os.path.join(ROOT, "ref", "cf_pops.json")
UA = "GroundTruth/1.5 (personal non-commercial OSINT dashboard)"
TYPE_RANK = {"large_airport": 0, "medium_airport": 1, "small_airport": 2, "heliport": 3, "seaplane_base": 4,
             "balloonport": 5, "closed": 9}
MANUAL = {"JXG": (120.755, 30.746, "CN")}   # Jiaxing, Zhejiang: city centre (no airport), approximate
OVERSEAS = {"RE": "FRA", "GP": "FRA", "MQ": "FRA", "GF": "FRA", "YT": "FRA"}   # not separate in Natural Earth
RX_POP = re.compile(r"^(.*?)\s*-\s*\(([A-Z]{3})\)\s*$")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)
    return body


def pops_from_summary(summary):
    """{code: city} for the PoP components of a Cloudflare summary.json / components.json."""
    out = {}
    for c in summary.get("components") or []:
        m = RX_POP.match(str(c.get("name") or ""))
        if m and not c.get("group"):
            out[m.group(2)] = m.group(1).split(",")[0].strip()
    return out


def airport_index(rows):
    """(by iata_code, by keyword code): code -> best airport row."""
    by_code, by_kw = {}, {}

    def better(a, b):
        return b is None or TYPE_RANK.get(a["type"], 8) < TYPE_RANK.get(b["type"], 8)

    for r in rows:
        code = (r.get("iata_code") or "").strip().upper()
        if len(code) == 3 and better(r, by_code.get(code)):
            by_code[code] = r
        for kw in re.split(r"[,;]", r.get("keywords") or ""):
            kw = kw.strip().upper()
            if re.fullmatch(r"[A-Z]{3}", kw) and better(r, by_kw.get(kw)):
                by_kw[kw] = r
    return by_code, by_kw


def build(pops, rows, a2_to_a3):
    by_code, by_kw = airport_index(rows)
    out, missing = {}, []
    for code, city in sorted(pops.items()):
        r = by_code.get(code) or by_kw.get(code)
        if r:
            lon, lat, a2 = float(r["longitude_deg"]), float(r["latitude_deg"]), r["iso_country"]
        elif code in MANUAL:
            lon, lat, a2 = MANUAL[code]
        else:
            missing.append(code)
            continue
        out[code] = [round(lon, 3), round(lat, 3), city, a2_to_a3.get(a2) or OVERSEAS.get(a2) or a2]
    return out, missing


def dump(table):
    """One code per line (small, diff-friendly)."""
    lines = ["%s:%s" % (json.dumps(k), json.dumps(v, ensure_ascii=False, separators=(",", ":"))) for k, v in
             sorted(table.items())]
    return "{\n" + ",\n".join(lines) + "\n}\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--summary", help="saved Cloudflare summary.json (default: fetch it)")
    ap.add_argument("--airports", help="saved OurAirports airports.csv (default: download it once)")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    summary = json.load(open(a.summary, encoding="utf-8")) if a.summary else json.loads(_get(SUMMARY_URL))
    pops = pops_from_summary(summary)
    if not pops:
        sys.exit("no PoP components in the summary")
    raw = open(a.airports, "rb").read() if a.airports else _get(AIRPORTS_URL)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    a2_to_a3 = json.load(open(THEATRES, encoding="utf-8"))["a2"]
    table, missing = build(pops, rows, a2_to_a3)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(dump(table))
    print("%d PoPs, %d placed -> %s" % (len(pops), len(table), a.out))
    if missing:
        print("not placed: " + ", ".join(missing), file=sys.stderr)


if __name__ == "__main__":
    main()
