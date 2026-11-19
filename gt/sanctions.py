"""OpenSanctions maritime vessel lists (keyless, daily): sanctioned, shadow-fleet and detained ships by IMO/MMSI. v1.0, 2026-11-19 (Ground Truth 0.9.0).

Source: the OpenSanctions "maritime" collection, free and keyless. INDEX_URL (a 307 to the dated copy) names the
current version and its maritime.csv resource (about 5.2 MB with a SHA-1); the CSV is downloaded only when the
version changes, so a daily poll is one small request on most days. OpenSanctions rebuilds the set daily.

The CSV has one row per source listing, not per ship: a tanker on the EU, UK, Canadian and GUR lists is four rows with
the same IMO (on 2026-11-18: 23,915 rows, 21,055 of them vessels, about 9,500 distinct IMOs). Vessel rows are merged
by IMO (by MMSI when a row has no IMO); organisations, people, aliases and linked countries are dropped. Rows with
neither identifier (mostly the Swiss list, which names ships without an IMO) cannot be matched to AIS and are dropped.

Marks, from the row's source dataset (table LISTS below; for a dataset not in the table, from the row's topic):
  S  on a government sanctions list: OFAC SDN, EU, UK, Switzerland, UN 1718, Canada, France, Monaco, Belgium ...
  G  on Ukraine's GUR "War & Sanctions" ship list. Rows OpenSanctions tags as shadow fleet (topic mare.shadow) are
     labelled "GUR shadow fleet"; the rest of GUR's ship list (oligarch yachts, Russian-flag ships) "GUR list".
  D  port-state control: detained by the Tokyo, Black Sea or Abuja MOU, or banned by the Paris MOU. Not a sanction:
     a record of a safety inspection outcome, kept apart from S on purpose.
A ship can carry several marks ("SGD"). Records only of PSC inspections (ext_*_psc) give MMSIs but no mark.

Licence: CC BY-NC 4.0, attribution "OpenSanctions". Fine for the public page with the credit shown; NON-COMMERCIAL
ONLY, never for the trading agent.

A match is a list entry about a ship's identifiers, not proof of what the ship is doing now: MMSIs get reused when
a ship is reflagged and spoofed by ships hiding their identity, and some listed IMOs belong to scrapped or renamed
hulls. lookup() says whether it matched on IMO or only on MMSI.

The index is written to CACHE/vessellists_index.json (not vessellists.json: server.py keeps every feed's last result
in CACHE/<feed>.json). lookup() keeps it in memory and rereads it when its mtime changes (checked once a minute).
Stdlib only, Python 3.9+.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")
INDEX_FILE = "vessellists_index.json"  # in CACHE
FORMAT = 1

INDEX_URL = "https://data.opensanctions.org/datasets/latest/maritime/index.json"
CSV_URL = "https://data.opensanctions.org/artifacts/maritime/{version}/maritime.csv"  # if index.json names no resource
ENTITY_URL = "https://www.opensanctions.org/entities/{id}/"
UA = "GroundTruth/0.9 (personal non-commercial OSINT dashboard)"
TIMEOUT_INDEX = 30
TIMEOUT_CSV = 120
RECHECK = 60  # s between mtime checks in lookup()
REQUIRED = ("type", "caption", "imo", "mmsi", "id", "datasets")  # risk and flag are optional

ATTRIBUTION = "OpenSanctions (CC BY-NC 4.0), from OFAC, EU, UK, GUR and other lists"
ATTRIBUTION_URL = "https://www.opensanctions.org/datasets/maritime/"
LICENCE = "CC BY-NC 4.0: non-commercial use only; never for the trading agent"
NOTE = ("A match is a list entry about a ship's IMO or MMSI, not proof of what it is doing now: MMSIs get reused and "
        "spoofed. S = sanctions list, G = Ukraine GUR ship list, D = port-state control detention or ban (not a "
        "sanction).")

# Source dataset -> (mark, label). Order = display order of the labels and the pick of a ship's name and link.
# Counts are vessel rows on 2026-11-18. Mark "" = context: shown in a marked ship's lists, never a mark on its own.
# None = skip the row's marks and labels (its MMSIs still count for a ship that is marked by another row).
LISTS = {
    # ---- S: government sanctions lists (all carry OpenSanctions' topic "sanction")
    "us_ofac_sdn": ("S", "OFAC"),                       # 1,570  US Treasury SDN list
    "us_ofac_cons": ("S", "OFAC non-SDN"),              # 0      in the collection, no vessels yet
    "un_1718_vessels": ("S", "UN"),                     # 59     UN Security Council 1718 committee (DPRK)
    "eu_journal_sanctions": ("S", "EU"),                # 750    EU Official Journal
    "eu_sanctions_map": ("S", "EU"),                    # 866    EU Sanctions Map (the same EU listings, another source)
    "eu_fsf": ("S", "EU"),                              # 2      EU Financial Sanctions Files
    "gb_fcdo_sanctions": ("S", "UK"),                   # 694
    "ch_seco_sanctions": ("S", "Switzerland"),          # 708    (539 more without IMO or MMSI are dropped)
    "ca_dfatd_sema_sanctions": ("S", "Canada"),         # 731
    "fr_tresor_gels_avoir": ("S", "France"),            # 40     national asset freezes
    "mc_fund_freezes": ("S", "Monaco"),                 # 40     (none has an IMO or MMSI)
    "be_fod_sanctions": ("S", "Belgium"),               # 2
    "ae_local_terrorists": ("S", "UAE terror list"),    # 1
    "us_cbp_forced_labor": ("S", "US CBP forced labour"),  # 4  AMBIGUOUS: a CBP import ban (withhold release order);
    #                                                         OpenSanctions tags it "sanction", so it counts as S
    "us_trade_csl": ("S", "US CSL"),                    # 1,570  Commerce consolidated screening list: re-publishes
    #                                                         the OFAC SDN vessels (label hidden next to "OFAC")
    # Not in the maritime set on 2026-11-18; named so their labels are short if they join it.
    "au_dfat_sanctions": ("S", "Australia"),
    "jp_mof_sanctions": ("S", "Japan"),
    "nz_russia_sanctions": ("S", "New Zealand"),
    # ---- G: Ukraine's Defence Intelligence (GUR) War & Sanctions portal, ship section. 896 of the 1,488 rows carry
    # the topic mare.shadow (SHADOW_LABEL); the other 592 are mostly Russian-flag ships and oligarch yachts, topic
    # "poi" only. GUR's list is not a sanction (no legal effect), so G stays apart from S.
    "ua_war_sanctions": ("G", "GUR list"),
    # ---- D: port-state control (PSC) outcomes, not sanctions
    "tokyo_mou_detention": ("D", "Tokyo MOU detained"),          # 6,078
    "black_sea_mou_detention": ("D", "Black Sea MOU detained"),  # 1,334
    "abuja_mou_detention": ("D", "Abuja MOU detained"),          # 215
    "paris_mou_banned": ("D", "Paris MOU banned"),               # 148  refused access after repeated detentions
    #                                                                  (topic reg.warn, not mare.detained)
    # ---- context only
    "kp_rusi_reports": ("", "RUSI DPRK report"),        # 766    RUSI research on North Korean sanctions evasion
    # ---- inspection records, not detentions (no topic): identifiers only
    "ext_tokyo_mou_psc": None,                          # 4,502
    "ext_abuja_mou_psc": None,                          # 1,057
}
SHADOW_LABEL = {"ua_war_sanctions": "GUR shadow fleet"}  # label for that dataset's rows tagged mare.shadow
HIDE_NEXT_TO = {"US CSL": "OFAC"}  # drop the first label when the ship also shows the second
TOPIC_MARK = (("sanction", "S"), ("mare.shadow", "G"), ("mare.detained", "D"))  # datasets not in LISTS
MARK_ORDER = "SGD"

_POS = {}
for _i, (_ds, _e) in enumerate(LISTS.items()):
    if _e:
        _POS.setdefault(_e[1], _i + 0.5)
        if _ds in SHADOW_LABEL:
            _POS.setdefault(SHADOW_LABEL[_ds], _i + 0.25)  # shadow fleet before the plain GUR label
_MRANK = {"S": 0, "G": 1, "D": 2, "": 3}
# Name and flag from the source that tracks renames and reflags best: GUR's list, then PSC records, then the
# sanctions lists (they keep the name and flag at the time of designation); the most common name among equals.
_FRESH = {"G": 3, "D": 2, "S": 1, "": 0}
_IMO_RE = re.compile(r"[0-9]{7}")
_MMSI_RE = re.compile(r"[0-9]{9}")


def _iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def index_path():
    return os.path.join(CACHE, INDEX_FILE)


def http_get(url, timeout=None):
    """Default fetch: plain GET with an honest User-Agent (urllib follows the 307 from the 'latest' index)."""
    if timeout is None:
        timeout = TIMEOUT_CSV if url.endswith(".csv") else TIMEOUT_INDEX
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------- identifiers ----------------

def norm_imo(v):
    """'IMO9187629' / 'imo 9187629' / 9187629 / '9187629' -> '9187629'; anything else (0, '', 123) -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, float):
        if not (abs(v) < 1e10 and v == int(v)):  # NaN, inf, fractions
            return None
        v = int(v)
    s = str(v).strip().upper()
    if s.startswith("IMO"):
        s = s[3:].lstrip(" :.-")
    return s if _IMO_RE.fullmatch(s) and s != "0000000" else None


def norm_mmsi(v):
    """9 ASCII digits (int or str) -> str; anything else (8 or 10 digits, 0, '') -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, float):
        if not (abs(v) < 1e10 and v == int(v)):  # NaN, inf, fractions
            return None
        v = int(v)
    s = str(v).strip()
    return s if _MMSI_RE.fullmatch(s) and s != "000000000" else None


def _split(s):
    return [x.strip() for x in (s or "").split(";") if x.strip()]


# ---------------- parse ----------------

def _row_lists(datasets, topics):
    """-> [(mark, label, pos)] for one CSV row; [] when the row only carries identifiers."""
    out = []
    for ds in datasets:
        e = LISTS.get(ds, False)
        if e is None:
            continue
        if e is False:  # not in the table: mark from the row's topic, raw dataset name as the label
            if ds.startswith("ext_"):
                continue  # enrichment records (inspections), never a listing
            mark = next((m for t, m in TOPIC_MARK if t in topics), "")
            out.append((mark, ds, 1000))
            continue
        mark, label = e
        if ds in SHADOW_LABEL and "mare.shadow" in topics:
            label = SHADOW_LABEL[ds]
        out.append((mark, label, _POS.get(label, 1000)))
    return out


def parse_csv(raw):
    """maritime.csv bytes -> (vessels, stats). Streams the rows; keeps ships with at least one mark.

    vessels: sorted list of [name, flag, imo, [mmsi...], marks, [label...], entity id]."""
    rd = csv.reader(io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline=""))
    header = next(rd, None)
    col = {h.strip().lower(): i for i, h in enumerate(header or [])}
    missing = [c for c in REQUIRED if c not in col]
    if missing:
        raise ValueError("maritime.csv lacks column(s): " + ", ".join(missing))
    c_type, c_name, c_imo, c_mmsi, c_id, c_ds = (col[c] for c in REQUIRED)
    c_risk, c_flag = col.get("risk"), col.get("flag")
    width = max(col.values()) + 1
    groups = {}  # key -> [rank, {name: [n, fresh]}, ((fresh, single), flag), imo, mmsis, marks, labels{label: pos}, id]
    extra = {}  # imo -> MMSIs from inspection-only rows
    st = {"rows": 0, "vessel_rows": 0, "no_identifier": 0}
    for row in rd:
        st["rows"] += 1
        if len(row) < width or row[c_type].strip().upper() != "VESSEL":
            continue
        st["vessel_rows"] += 1
        imo = norm_imo(row[c_imo])
        mmsis = [m for m in (norm_mmsi(x) for x in _split(row[c_mmsi])) if m]
        if not imo and not mmsis:
            st["no_identifier"] += 1
            continue
        topics = set(_split(row[c_risk])) if c_risk is not None else set()
        lists = _row_lists(_split(row[c_ds]), topics)
        if not lists:  # an inspection record: its MMSIs count for the ship if a listing names the same IMO
            if imo:
                extra.setdefault(imo, []).extend(mmsis)
            continue
        key = ("i" + imo) if imo else ("m" + mmsis[0])
        g = groups.get(key)
        if g is None:
            g = groups[key] = [(99, 0), {}, ((-1, False), ""), imo or "", [], set(), {}, ""]
        for m in mmsis:
            if m not in g[4]:
                g[4].append(m)
        rank = min((_MRANK[m], p) for m, _, p in lists)
        if rank < g[0]:  # the link goes to the strongest listing (OFAC first)
            g[0], g[7] = rank, row[c_id].strip()
        fresh = max(_FRESH[m] for m, _, _ in lists)
        name = " ".join(row[c_name].upper().split())
        if name:
            nv = g[1].setdefault(name, [0, -1])
            nv[0] += 1
            nv[1] = max(nv[1], fresh)
        flags = _split(row[c_flag].lower()) if c_flag is not None else []
        if flags and (fresh, len(flags) == 1) > g[2][0]:  # a single flag beats a "cm;pw" from the same kind of source
            g[2] = ((fresh, len(flags) == 1), flags[0])
        for m, label, p in lists:
            if m:
                g[5].add(m)
            g[6].setdefault(label, p)
    vessels = []
    for key in sorted(groups):
        rank, names, flag, imo, mmsis, marks, labels, eid = groups[key]
        if not marks:
            continue  # context only (a RUSI report and nothing else)
        for m in extra.get(imo, ()) if imo else ():
            if m not in mmsis:
                mmsis.append(m)
        for a, b in HIDE_NEXT_TO.items():
            if a in labels and b in labels:
                del labels[a]
        name = max(names.items(), key=lambda kv: (kv[1][1], kv[1][0], kv[0]))[0] if names else ""
        vessels.append([name, flag[1], imo, mmsis, "".join(m for m in MARK_ORDER if m in marks),
                        sorted(labels, key=lambda x: (labels[x], x)), eid])
    if not vessels:
        raise ValueError("maritime.csv: no listed vessels in %d rows" % st["rows"])
    return vessels, st


def stats(vessels):
    by_list = {}
    for v in vessels:
        for label in v[5]:
            by_list[label] = by_list.get(label, 0) + 1
    top = sorted(by_list.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    return {"vessels": len(vessels), "with_imo": sum(1 for v in vessels if v[2]),
            "with_mmsi": sum(1 for v in vessels if v[3]),
            "by_mark": {m: sum(1 for v in vessels if m in v[4]) for m in MARK_ORDER},
            "by_list": dict(top)}


def _public(doc):
    """poll()'s return value (served at /api/feed/vessellists): counts and credits, no vessel rows."""
    out = {"version": doc.get("version"), "fetched": doc.get("fetched")}
    out.update(doc.get("stats") or {})
    out.update(attribution=ATTRIBUTION, attribution_url=ATTRIBUTION_URL, licence=LICENCE, note=NOTE)
    return out


# ---------------- in-memory index for lookup() ----------------

_LOCK = threading.Lock()
_IDX = {"imo": {}, "mmsi": {}, "mtime": None, "version": None, "path": None}
_CHECKED = [None]  # monotonic time of the last mtime check
_clock = time.monotonic


def _build(vessels, mtime, version, path):
    imo, mmsi, rank = {}, {}, {}
    for name, flag, i, mmsis, marks, labels, eid in vessels:
        e = (marks, tuple(labels), name, i or None, ENTITY_URL.format(id=eid) if eid else None, flag or None)
        if i:
            imo[i] = e
        r = (_MRANK[marks[0]], -len(marks))
        for m in mmsis:  # an MMSI on several ships (reused after a reflag): keep the one with the strongest mark
            if m not in mmsi or r < rank[m]:
                mmsi[m], rank[m] = e, r
    return {"imo": imo, "mmsi": mmsi, "mtime": mtime, "version": version, "path": path}


def _load_doc(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("vessels"), list):
        raise ValueError("not a v%d vessel index" % FORMAT)
    return doc


def _current():
    """The in-memory index, reloaded when the file's mtime changes (checked at most every RECHECK s)."""
    global _IDX
    now, path = _clock(), index_path()
    last = _CHECKED[0]
    if last is not None and now - last < RECHECK and _IDX["path"] == path:
        return _IDX
    with _LOCK:
        _CHECKED[0] = now
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            return _IDX  # no index yet (or it went away): keep what is loaded, if anything
        if mtime == _IDX["mtime"] and _IDX["path"] == path:
            return _IDX
        try:
            doc = _load_doc(path)
        except (OSError, ValueError):
            return _IDX  # half-written by hand or another format: keep the old one, retry next minute
        _IDX = _build(doc["vessels"], mtime, doc.get("version"), path)
        return _IDX


def lookup(imo=None, mmsi=None):
    """IMO first, then MMSI -> {"marks", "lists", "name", "imo", "url", "flag", "match"} or None.

    flag is the listed flag (may differ from the one on AIS); match is "imo" or "mmsi" (weaker: MMSIs get reused)."""
    idx = _current()
    if not idx["imo"] and not idx["mmsi"]:
        return None
    e, how = None, "imo"
    i = norm_imo(imo)
    if i:
        e = idx["imo"].get(i)
    if e is None:
        m = norm_mmsi(mmsi)
        e, how = (idx["mmsi"].get(m) if m else None), "mmsi"
    if e is None:
        return None
    return {"marks": e[0], "lists": list(e[1]), "name": e[2], "imo": e[3], "url": e[4], "flag": e[5], "match": how}


# ---------------- feed ----------------

def _csv_resource(idx, version):
    for r in idx.get("resources") or []:
        if isinstance(r, dict) and (r.get("name") == "maritime.csv" or str(r.get("path", "")).endswith("maritime.csv")):
            if r.get("url"):
                return r["url"], r.get("checksum")
    return CSV_URL.format(version=version), None


def poll(now=None, fetch=None):
    """Feed `vessellists` (daily): re-index the CSV when OpenSanctions publishes a new version.

    Raises on a failed index or CSV fetch, a checksum mismatch or a CSV without the expected columns; the index
    file is only replaced after a good parse, so a failed refresh leaves the old one in place."""
    global _IDX
    now = now or time.time()
    get = fetch or http_get
    idx = json.loads(get(INDEX_URL))
    version = str((idx or {}).get("version") or "").strip()
    if not version:
        raise ValueError("maritime index.json names no version")
    path = index_path()
    try:
        old = _load_doc(path)
    except (OSError, ValueError):
        old = None
    if old and old.get("version") == version:
        return _public(old)
    url, sha1 = _csv_resource(idx, version)
    raw = get(url)
    if sha1 and re.fullmatch(r"[0-9a-f]{40}", str(sha1)) and hashlib.sha1(raw).hexdigest() != sha1:
        raise ValueError("maritime.csv checksum mismatch (%d bytes): truncated or replaced download" % len(raw))
    vessels, st = parse_csv(raw)
    doc = {"format": FORMAT, "version": version, "fetched": _iso(now), "source": url, "csv_bytes": len(raw),
           "parse": st, "stats": stats(vessels), "vessels": vessels}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, path)
    with _LOCK:  # lookup() sees the new lists at once, without rereading the file
        _IDX = _build(vessels, os.stat(path).st_mtime_ns, version, path)
        _CHECKED[0] = _clock()
    return _public(doc)


def summary(data):
    """For the analyst (tiny): listed ships by mark, the list version and the licence."""
    if not data:
        return None
    try:
        return {"version": data.get("version"), "vessels": data.get("vessels"), "by_mark": data.get("by_mark"),
                "licence": LICENCE}
    except Exception as e:  # never break /api/summary
        return {"error": type(e).__name__}
