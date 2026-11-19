"""Offline tests for 0.9.0: OpenSanctions maritime vessel lists (gt/sanctions.py).
Never touches the network. Fixtures are real OpenSanctions files saved on 2026-11-19 (UTC), version 20261118150306-fnv:
  sanctions/index.json    the collection's index.json cut to a dozen keys; the maritime.csv resource's checksum and
                          size rewritten to the fixture's
  sanctions/maritime.csv  30 real vessel rows: every row for 13 IMOs plus 2 rows without an IMO
    SKIPPER 9304667          OFAC (+ US CSL) as "Adisa", GUR shadow fleet as SKIPPER          -> SG
    EAGLE S 9329760          EU x2 sources, UK, Canada, GUR shadow fleet, Abuja MOU detention -> SGD
    KASTOS 1016226           GUR ship list without the shadow-fleet topic                     -> G  "GUR list"
    BAHJAT 9405954           OFAC without MMSI; a Tokyo MOU inspection row (before it) has it -> S, MMSI from inspection
    TONG HUNG SAN 7937317    OFAC, UN 1718, EU, Switzerland, France, RUSI report (as Chong Chon Gang too)
    Kum Song 8511809         RUSI report only                                                 -> not indexed
    CANADA EXPRESS 9861251   Tokyo MOU inspection only                                        -> not indexed
    PRIMROSE 9065077         Tokyo MOU detention                                              -> D
    VOLGO-DON 5066 8873752   Paris MOU banned                                                 -> D
    MSC GEORGIA II 9357107   Abuja MOU detention; inspection row after it with 2 MMSIs        -> D
    VERUDA 9585546           Tokyo + Black Sea MOU detentions; only an 8-digit MMSI           -> D, no MMSI
    NAYA FALCON / SANANDAJ   GUR list / OFAC, both listed with MMSI 677049100                 -> MMSI goes to OFAC's
    NEGA (no IMO)            GUR list, MMSI 273337970                                         -> G by MMSI only
    Sofos (no IMO, no MMSI)  Swiss list                                                       -> dropped

Run: python3 -I tests/test_090_sanctions.py
"""
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "sanctions")
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)
from gt import sanctions  # noqa: E402

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


sanctions.urllib.request.urlopen = no_network
T = [1000.0]
sanctions._clock = lambda: T[0]  # lookup()'s once-a-minute mtime check runs on this clock
INDEX_RAW = open(os.path.join(FX, "index.json"), "rb").read()
CSV_RAW = open(os.path.join(FX, "maritime.csv"), "rb").read()
INDEX = json.loads(INDEX_RAW)
V1 = INDEX["version"]
CSV_URL = INDEX["resources"][0]["url"]
PATH = sanctions.index_path()
NOW = 1795064400  # 2026-11-19T05:00:00Z
calls = []


def server(index, files):
    """fetch() serving index.json and CSVs from memory; a value that is an exception is raised."""
    def fetch(url):
        calls.append(url)
        if url == sanctions.INDEX_URL:
            v = index
        else:
            v = files[url]
        if isinstance(v, Exception):
            raise v
        return v if isinstance(v, bytes) else json.dumps(v).encode()
    return fetch


def new_version(version, csv_bytes, checksum=True):
    """index.json for another version whose maritime.csv is csv_bytes (checksum rewritten unless False)."""
    d = json.loads(INDEX_RAW)
    d["version"] = version
    r = d["resources"][0]
    r["url"] = "https://data.opensanctions.org/artifacts/maritime/%s/maritime.csv" % version
    r["size"] = len(csv_bytes)
    if checksum:
        r["checksum"] = hashlib.sha1(csv_bytes).hexdigest()
    else:
        r.pop("checksum")
    return d, r["url"]


def file_bytes():
    return open(PATH, "rb").read()


# ---- constants and docstring
check(sanctions.ATTRIBUTION == "OpenSanctions (CC BY-NC 4.0), from OFAC, EU, UK, GUR and other lists"
      and sanctions.ATTRIBUTION_URL == "https://www.opensanctions.org/datasets/maritime/"
      and sanctions.LICENCE == "CC BY-NC 4.0: non-commercial use only; never for the trading agent", "credits and licence")
check(sanctions.__doc__.splitlines()[0] == '''OpenSanctions maritime vessel lists (keyless, daily): sanctioned, shadow-fleet and detained ships by IMO/MMSI. v1.0, 2026-11-19 (Ground Truth 0.9.0).''',
      "docstring first line")
check(sanctions.CACHE == os.path.join(TMP, "cache") and os.path.basename(PATH) == "vessellists_index.json",
      "index under GT_DATA/cache, not the server's own vessellists.json")
check(all(e is None or (e[0] in ("S", "G", "D", "") and e[1]) for e in sanctions.LISTS.values()), "LISTS entries well formed")
check(set(INDEX["datasets"]) <= set(sanctions.LISTS), "every dataset of the 2026-11-18 collection is in LISTS")

# ---- before any index exists
check(not os.path.exists(PATH) and sanctions.lookup(imo="IMO9304667", mmsi=353024000) is None, "no index file -> None")
check(sanctions.summary(None) is None and sanctions.summary({}) is None, "summary of nothing -> None")

# ---- identifiers
n = sanctions.norm_imo
check(n("IMO9329760") == n("imo 9329760") == n(9329760) == n("9329760") == n(" IMO9329760 ") == n(9329760.0) == "9329760",
      "IMO normalised from 'IMO…', int, str, float")
check(all(n(x) is None for x in (None, 0, "", "0", "IMO", "IMO0000000", 932976, "93297600", True, "IMO93297A0", 9.5, "９３２９７６０")),
      "bad IMOs -> None (0, blank, 6/8 digits, letters, bool, full-width digits)")
m = sanctions.norm_mmsi
check(m(353024000) == m("353024000") == m(" 353024000 ") == "353024000", "MMSI from int or str")
check(all(m(x) is None for x in (None, 0, "", 35302400, "3530240001", "000000000", "35302400A", True)), "bad MMSIs -> None")

# ---- parsing the real rows
vessels, st = sanctions.parse_csv(CSV_RAW)
check(st == {"rows": 30, "vessel_rows": 30, "no_identifier": 1}, "30 rows, 1 without IMO or MMSI (%s)" % st)
check(len(vessels) == 12, "12 marked ships (RUSI-only, inspection-only and no-identifier rows dropped): %d" % len(vessels))
check(all(len(v) == 7 for v in vessels), "vessel rows are [name, flag, imo, mmsis, marks, lists, id]")
check(all((v[2] == "" or (len(v[2]) == 7 and v[2].isdigit())) and all(len(x) == 9 and x.isdigit() for x in v[3])
          for v in vessels), "imo 7 digits (or ''), MMSIs 9 digits")
check(all(v[4] and set(v[4]) <= set("SGD") and v[4] == "".join(c for c in "SGD" if c in v[4]) for v in vessels),
      "marks non-empty, in S G D order")
check([v[2] for v in vessels if v[2]] == sorted(v[2] for v in vessels if v[2]), "sorted by IMO")

# ---- poll(): first run
calls.clear()
d1 = sanctions.poll(now=NOW, fetch=server(INDEX, {CSV_URL: CSV_RAW}))
check(calls == [sanctions.INDEX_URL, CSV_URL], "first poll: index.json, then the CSV it names")
KEYS = {"version", "fetched", "vessels", "with_imo", "with_mmsi", "by_mark", "by_list", "attribution", "attribution_url",
        "licence", "note"}
check(set(d1) == KEYS, "poll() returns exactly the public keys")
check(d1["version"] == V1 and d1["fetched"] == "2026-11-19T05:00:00Z", "version and fetched time")
check(d1["vessels"] == 12 and d1["with_imo"] == 11 and d1["with_mmsi"] == 8, "counts: 12 ships, 11 with IMO, 8 with MMSI")
check(d1["by_mark"] == {"S": 5, "G": 5, "D": 5}, "by_mark S 5, G 5, D 5: %s" % d1["by_mark"])
check(d1["by_list"]["OFAC"] == 4 and d1["by_list"]["GUR shadow fleet"] == 2 and d1["by_list"]["GUR list"] == 3
      and d1["by_list"]["EU"] == 2 and d1["by_list"]["Tokyo MOU detained"] == 2 and "US CSL" not in d1["by_list"]
      and len(d1["by_list"]) <= 12, "by_list counts per ship, EU once per ship, US CSL hidden next to OFAC")
check(list(d1["by_list"].values()) == sorted(d1["by_list"].values(), reverse=True), "by_list largest first")
blob = json.dumps(d1)
check(len(blob.encode()) < 2048 and not any(isinstance(v, list) for v in d1.values()) and "9304667" not in blob,
      "public result has no vessel rows and is under 2 KB (%d bytes)" % len(blob.encode()))
check(os.path.exists(PATH) and not os.path.exists(PATH + ".tmp"), "index file written atomically (no .tmp left)")
doc = json.loads(file_bytes())
check(doc["format"] == 1 and doc["version"] == V1 and len(doc["vessels"]) == 12, "index file: format 1, version, 12 ships")
aliases, captions = set(), set()
for row in csv.DictReader(io.StringIO(CSV_RAW.decode())):
    captions.add(" ".join(row["caption"].upper().split()))
    aliases.update(a.strip().upper() for a in row["aliases"].split(";") if a.strip())
text = file_bytes().decode().upper()
only_alias = sorted(a for a in aliases - captions if len(a) > 3)
check(only_alias and not any(json.dumps(a)[1:-1] in text for a in only_alias)
      and '"COUNTRIES"' not in text and '"ALIASES"' not in text and "KH;RU;SL" not in text,
      "no aliases (%d checked) and no country lists in the index file" % len(only_alias))

# ---- marks for each kind
L = sanctions.lookup
r = L(imo="IMO9304667")
check(r == {"marks": "SG", "lists": ["OFAC", "GUR shadow fleet"], "name": "SKIPPER", "imo": "9304667",
            "url": "https://www.opensanctions.org/entities/ofac-39692/", "flag": "pa", "match": "imo"},
      "SKIPPER: SG, OFAC + GUR shadow fleet, GUR's current name over OFAC's 'Adisa', link to the OFAC entry")
r = L(imo=9329760)
check(r["marks"] == "SGD" and r["lists"] == ["EU", "UK", "Canada", "GUR shadow fleet", "Abuja MOU detained"]
      and r["name"] == "EAGLE S" and r["flag"] == "ck", "EAGLE S: SGD, EU listed by two sources shows once")
r = L(imo="1016226")
check(r["marks"] == "G" and r["lists"] == ["GUR list"] and r["name"] == "KASTOS", "KASTOS: G, GUR list (no shadow topic)")
r = L(imo="IMO7937317")
check(r["marks"] == "S" and r["lists"] == ["OFAC", "UN", "EU", "Switzerland", "France", "RUSI DPRK report"]
      and r["name"] == "TONG HUNG SAN" and r["url"].endswith("/ofac-17069/"),
      "TONG HUNG SAN: six lists in table order, RUSI as context, most common name")
r = L(imo=9065077)
check(r["marks"] == "D" and r["lists"] == ["Tokyo MOU detained"] and r["name"] == "PRIMROSE", "PRIMROSE: D, Tokyo MOU")
r = L(imo=8873752)
check(r["marks"] == "D" and r["lists"] == ["Paris MOU banned"], "VOLGO-DON 5066: D, Paris MOU banned")
r = L(imo=9585546)
check(r["marks"] == "D" and r["lists"] == ["Tokyo MOU detained", "Black Sea MOU detained"], "VERUDA: two detention lists")
check(L(mmsi=23829710) is None and L(mmsi="023829710") is None, "VERUDA's 8-digit MMSI is not indexed")
check(L(imo=8511809) is None, "RUSI report only -> None")
check(L(imo=9861251) is None and L(mmsi=563120800) is None, "PSC inspection only -> None (IMO and MMSI)")
check(L(imo=1234567) is None and L(imo=1234567, mmsi=211000000) is None and L() is None, "unknown ship -> None")

# ---- MMSI fallback
r = L(mmsi=353024000)
check(r["name"] == "SKIPPER" and r["match"] == "mmsi", "MMSI alone finds SKIPPER, match 'mmsi'")
r = L(imo="IMO1234567", mmsi="353024000")
check(r["imo"] == "9304667" and r["match"] == "mmsi", "unlisted IMO + listed MMSI -> MMSI match (caller sees imo differs)")
check(L(imo=9304667, mmsi=636023893)["name"] == "SKIPPER", "IMO wins over a different ship's MMSI")
check(L(imo=0, mmsi=636023893)["name"] == "KASTOS" and L(imo="", mmsi="636023893")["name"] == "KASTOS", "IMO 0 / blank ignored")
r = L(mmsi=273337970)
check(r["name"] == "NEGA" and r["imo"] is None and r["marks"] == "G" and r["match"] == "mmsi", "no-IMO ship found by MMSI")
check(L(mmsi=422036300)["name"] == "BAHJAT", "MMSI from an inspection row listed before the sanction row")
check(L(mmsi=636021302)["name"] == "MSC GEORGIA II" and L(mmsi=635021302)["name"] == "MSC GEORGIA II",
      "both MMSIs of a 'a;b' field, from an inspection row listed after the detention row")
check(L(mmsi=445117000)["name"] == "TONG HUNG SAN", "second MMSI of the UN 1718 row")
check(L(mmsi=677049100)["name"] == "SANANDAJ" and L(imo=8033120)["name"] == "NAYA FALCON",
      "an MMSI on two ships goes to the stronger mark (S over G); IMO still finds the other")
check(L(mmsi=35302400) is None and L(mmsi="3530240001") is None, "MMSI that isn't 9 digits -> None")
r = L(imo=9304667)
r["lists"].append("X")
r["marks"] = "?"
check(L(imo=9304667)["lists"] == ["OFAC", "GUR shadow fleet"] and L(imo=9304667)["marks"] == "SG",
      "callers can't change the index through a result")

# ---- same version: no CSV download
calls.clear()
before = file_bytes()
d1b = sanctions.poll(now=NOW + 86400, fetch=server(INDEX, {CSV_URL: AssertionError("CSV fetched again")}))
check(calls == [sanctions.INDEX_URL], "same version: index.json only, no CSV download")
check(d1b == d1 and file_bytes() == before, "same version: same result (fetched = first download), file untouched")

# ---- new version: re-index
lines = CSV_RAW.decode().splitlines(True)
CSV2 = "".join(x for x in lines if "IMO9329760" not in x).encode()
IDX2, URL2 = new_version("20261119150306-abc", CSV2)
calls.clear()
d2 = sanctions.poll(now=NOW + 2 * 86400, fetch=server(IDX2, {URL2: CSV2}))
check(calls == [sanctions.INDEX_URL, URL2], "new version: CSV downloaded from the URL index.json names")
check(d2["version"] == "20261119150306-abc" and d2["vessels"] == 11 and d2["by_mark"] == {"S": 4, "G": 4, "D": 4},
      "new version re-indexed: 11 ships")
check(L(imo=9329760) is None and L(imo=9304667)["marks"] == "SG", "lookup sees the new lists at once (EAGLE S gone)")
good = file_bytes()

# ---- failed refreshes leave the old index in place and raise
def must_raise(fn, exc, what):
    try:
        fn()
    except exc as e:
        check(file_bytes() == good and not os.path.exists(PATH + ".tmp") and L(imo=9304667)["marks"] == "SG",
              "%s -> %s, old index kept" % (what, type(e).__name__))
        return
    check(False, what + " raised nothing")


IDX3, URL3 = new_version("20261120150306-def", CSV_RAW)
must_raise(lambda: sanctions.poll(fetch=server(IDX3, {URL3: urllib.error.URLError("timed out")})), urllib.error.URLError,
           "failed CSV fetch")
must_raise(lambda: sanctions.poll(fetch=server(urllib.error.HTTPError(sanctions.INDEX_URL, 503, "busy", {}, None), {})),
           urllib.error.HTTPError, "failed index.json fetch")
must_raise(lambda: sanctions.poll(fetch=server(b"<html>", {})), ValueError, "index.json that isn't JSON")
must_raise(lambda: sanctions.poll(fetch=server({"name": "maritime"}, {})), ValueError, "index.json without a version")
IDX4, URL4 = new_version("20261120150306-def", CSV_RAW)
must_raise(lambda: sanctions.poll(fetch=server(IDX4, {URL4: CSV_RAW[:3000]})), ValueError, "truncated CSV (checksum)")
BAD = b'"name","number"\n"x","1"\n'
IDX5, URL5 = new_version("20261120150306-def", BAD)
must_raise(lambda: sanctions.poll(fetch=server(IDX5, {URL5: BAD})), ValueError, "CSV missing the expected columns")
try:
    sanctions.parse_csv(BAD)
except ValueError as e:
    check("imo" in str(e) and "datasets" in str(e), "the error names the missing columns: %s" % e)
EMPTY = lines[0].encode()
IDX6, URL6 = new_version("20261120150306-def", EMPTY, checksum=False)
must_raise(lambda: sanctions.poll(fetch=server(IDX6, {URL6: EMPTY})), ValueError, "header-only CSV, no checksum given")
ORGS = "".join(lines[:1] + [x.replace('"VESSEL"', '"ORGANIZATION"', 1) for x in lines[1:]]).encode()
IDX7, URL7 = new_version("20261120150306-def", ORGS)
must_raise(lambda: sanctions.poll(fetch=server(IDX7, {URL7: ORGS})), ValueError, "organisation rows only")
check(sanctions.parse_csv(ORGS.replace(b'"ORGANIZATION"', b'"VESSEL"', 1))[0][0][0] == "SKIPPER",
      "one vessel row among organisations is still indexed")
d = json.loads(INDEX_RAW)
d["resources"] = []
FALLBACK = "https://data.opensanctions.org/artifacts/maritime/20261120150306-ghi/maritime.csv"
d["version"] = "20261120150306-ghi"
calls.clear()
check(sanctions.poll(fetch=server(d, {FALLBACK: CSV_RAW}))["vessels"] == 12 and calls[-1] == FALLBACK,
      "index.json without resources: CSV from the versioned artifacts URL")
good = file_bytes()

# ---- lookup reloads when another process rewrites the file (checked at most once a minute)
T[0] += 1000
check(L(imo=9329760)["marks"] == "SGD", "loaded state before the rewrite")
doc = json.loads(good)
for v in doc["vessels"]:
    if v[2] == "9329760":
        v[4], v[5] = "S", ["UK"]
doc["vessels"] = [v for v in doc["vessels"] if v[2] != "9065077"]
with open(PATH, "w") as fh:
    json.dump(doc, fh)
st0 = os.stat(PATH)
os.utime(PATH, ns=(st0.st_atime_ns, st0.st_mtime_ns + 5 * 10 ** 9))
T[0] += 30
check(L(imo=9329760)["marks"] == "SGD" and L(imo=9065077) is not None, "30 s later: no stat yet, old lists")
T[0] += 31
check(L(imo=9329760)["lists"] == ["UK"] and L(imo=9065077) is None, "61 s later: mtime changed, file reloaded")
with open(PATH, "w") as fh:
    fh.write('{"format": 1, "vessels": [')
T[0] += 61
check(L(imo=9329760)["lists"] == ["UK"], "a half-written file is ignored, the loaded lists stay")
calls.clear()
check(sanctions.poll(fetch=server(d, {FALLBACK: CSV_RAW}))["vessels"] == 12 and len(calls) == 2,
      "poll with an unreadable index file downloads again, even for the same version")
check(L(imo=9329760)["lists"] == ["EU", "UK", "Canada", "GUR shadow fleet", "Abuja MOU detained"], "and repairs lookups")
os.remove(PATH)
T[0] += 61
check(L(imo=9329760) is not None, "index file deleted: the loaded lists stay until a new one appears")

# ---- default fetch: honest User-Agent, 120 s for the CSV
seen = []


class FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    seen.append((req.full_url, req.get_header("User-agent"), timeout))
    return FakeResp(INDEX_RAW if req.full_url.endswith(".json") else CSV_RAW)


sanctions.urllib.request.urlopen = fake_urlopen
d = sanctions.poll(now=NOW)
sanctions.urllib.request.urlopen = no_network
check(d["vessels"] == 12 and seen == [(sanctions.INDEX_URL, "GroundTruth/0.9 (personal non-commercial OSINT dashboard)", 30),
                                      (CSV_URL, "GroundTruth/0.9 (personal non-commercial OSINT dashboard)", 120)],
      "default fetch: User-Agent, 30 s for index.json, 120 s for the CSV")

# ---- summary() for the analyst
s = sanctions.summary(d)
check(s == {"version": V1, "vessels": 12, "by_mark": {"S": 5, "G": 5, "D": 5}, "licence": sanctions.LICENCE},
      "summary: version, count, marks, licence")
check(len(json.dumps(s)) < 256, "summary is tiny (%d bytes)" % len(json.dumps(s)))
print("%d checks passed" % ok)
