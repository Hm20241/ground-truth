"""Airspace signals: emergency squawks, GNSS interference and US temporary flight restrictions.
v1.0, 2026-11-20 (Ground Truth 0.13.0, Phase C).

Three feeds (FEEDS below), all keyless outbound GETs:

* `squawk` (60 s): aircraft squawking 7500 (unlawful interference), 7600 (radio failure) or 7700 (emergency),
  worldwide. adsb.lol `/v2/sqk/<code>` (readsb JSON, `ac[]`, ODbL) for the three codes; adsb.fi's identical
  `/api/v2/sqk/<code>` only when adsb.lol fails (adsb.fi: 1 request/s, "personal, non-commercial use only"), so
  calls to it are spaced 1.1 s apart, and a provider that fails once is skipped for the rest of that poll. Empty
  lists are normal. A 6 h memory of every aircraft seen (identity, squawk, first/last seen, last position, alt,
  gs, up to 20 track points) lives in <cache>/airspace_squawk.json. Military = readsb dbFlags & 1 (the field is
  absent for civil aircraft). Probed 2026-11-20: the three calls take ~0.35 s each; the one hit was an MLAT
  helicopter on 7500 with no `emergency` field, which is why a single sighting is shown as unconfirmed.

* `gpsjam` (3600 s): GPSJAM's daily GNSS-interference map (gpsjam.org, John Wiseman), H3 resolution 4.
  `data/manifest.csv` (date, suspect, num_bad_aircraft_hexes, source; served gzip-encoded even unasked) is read
  at most once per 59 minutes, and not at all once yesterday's file is in (the next one cannot exist before
  00:00 UTC). The daily `data/<date>-h3_4.csv` (hex, count_good_aircraft, count_bad_aircraft; ~190 KB gzip,
  ~48,000 hexes on 2026-11-19) is downloaded once per new date (a failed download retries hourly, 3 tries per
  date). Levels use GPSJAM's own rule, read from its FAQ and its map code on 2026-11-20:
  share = (bad - 1) / (good + bad); low < 2 %, medium < 10 %, high otherwise. The "- 1" is GPSJAM's denoising for
  hexes with little traffic; there is no other minimum-aircraft threshold. Only medium and high hexes are output,
  capped at HEX_CAP (high first, then medium, each by share then by aircraft count). No hex -> country summary:
  that needs H3 decoding, which the page does with h3-js.
  Terms: gpsjam.org states no licence or reuse terms; its About page credits airplanes.live and ADS-B Exchange.
  So this feed is private (PUBLIC_OK False) and treated as non-commercial until John Wiseman says otherwise.

* `tfr` (900 s): US temporary flight restrictions from the FAA (tfr.faa.gov, US public domain).
  `tfrapi/getTfrList` (86 TFRs on 11-20) is the list. Shapes come from the FAA site's own sources, found in its
  Nuxt bundle on 2026-11-20: the GeoServer WFS `TFR:V_TFR_LOC` (every shape in one ~22 KB call; asked for in
  EPSG:4326, answered lon/lat; 85 polygons for 74 TFRs, circles pre-drawn as 37-point rings; no altitudes or
  times), and per NOTAM the XNOTAM XML `download/detail_<n_nnnn>.xml` (effective/expiry times in UTC, the local
  time zone, and per area: name, floor, ceiling, schedule, the raw shape (CIR circle, GRC points, CWA/CCA arcs)
  and the FAA's merged ring). XML is fetched only for new or changed TFRs (cache key notam_id + mod_abs_time),
  at most 30 per poll, 60 s per poll; geometry per area: a single CIR becomes a 64-point ring, else the merged
  ring, else the raw shape with arcs drawn every 5 degrees. A TFR with no XML yet shows its WFS polygon.
  12 of the 86 have no shape at all (nationwide notices; tfrapi/noShapeTfrList).

Every feed returns {"version", "fetched_at", "count", "sources": [{name, ok, error, newest, n}], "attribution",
...}, points/polygons under "geojson" and lists under "items". One failing source never fails a feed; the feed
raises only when it has nothing at all to show.
"""
import csv
import datetime as dt
import gzip
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from . import geo

VERSION = "1.0"
ATTRIBUTION = {
    "squawk": "ADS-B data: adsb.lol (ODbL)",
    "squawk_fallback": "adsb.fi open data (personal, non-commercial use)",
    "gpsjam": "GNSS interference: GPSJAM (gpsjam.org) by John Wiseman, from airplanes.live and ADS-B Exchange data",
    "tfr": "Temporary flight restrictions: FAA (tfr.faa.gov), US public domain. Not for navigation.",
}
ATTRIBUTION_URL = {"squawk": "https://adsb.lol", "gpsjam": "https://gpsjam.org", "tfr": "https://tfr.faa.gov"}
LICENCE = {
    "squawk": "adsb.lol data is ODbL 1.0 (attribution, share-alike for derived databases); the adsb.fi fallback "
              "is personal, non-commercial use only",
    "gpsjam": "No licence stated by gpsjam.org; kept off the public mirror, non-commercial, until the author agrees",
    "tfr": "FAA data, US public domain",
}
PUBLIC_OK = {"squawk": True, "gpsjam": False, "tfr": True}
# squawk: True because the adsb.fi fallback is non-commercial; gpsjam: no terms, so treated as non-commercial.
NON_COMMERCIAL = {"squawk": True, "gpsjam": True, "tfr": False}

UA = "Mozilla/5.0 (compatible; GroundTruth/0.13; personal OSINT dashboard)"
TIMEOUT = 20

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")   # the same folder as feeds.CACHE

_sleep = time.sleep      # patched by the tests
_clock = time.monotonic


# ---------------- shared helpers ----------------

def _fetch(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)
    return body


def _gunzip(b):
    """Bytes, gunzipped when they are gzip (the GPSJAM files are, whatever the client asked for)."""
    if isinstance(b, str):
        return b.encode("utf-8")
    return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b


def _utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    if isinstance(now, (int, float)):
        return dt.datetime.fromtimestamp(now, dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


def _iso(ts):
    if ts is None:
        return None
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(e):
    return "%s: %s" % (type(e).__name__, str(e)[:160])


def _path(name):
    return os.path.join(CACHE, "airspace_%s.json" % name)


def _load(name):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(name, obj):
    os.makedirs(CACHE, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    os.replace(tmp, _path(name))


def _src(name):
    return {"name": name, "ok": None, "error": None, "newest": None, "n": 0}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _locate(lon, lat):
    try:
        return geo.locate(lon, lat)
    except Exception:  # noqa: BLE001  placement is a nicety
        return {"country": None, "country_name": None, "sea": None, "theatre": "other"}


# ---------------- squawk: 7500 / 7600 / 7700 ----------------

SQUAWKS = {"7500": "hijack / unlawful interference", "7600": "radio failure", "7700": "general emergency"}
SQK_PROVIDERS = (("adsb.lol", "https://api.adsb.lol/v2/sqk/"), ("adsb.fi", "https://opendata.adsb.fi/api/v2/sqk/"))
SQK_TIMEOUT = 10        # 3 codes x 2 providers must fit well inside the 60 s interval
FI_GAP = 1.1            # adsb.fi: 1 request per second
MEMORY_S = 6 * 3600
MEMORY_MAX = 120        # aircraft kept (typically 0-10 squawk at once); keeps the payload < 300 KB
TRAIL_MAX = 20
SQK_NOTE = ("Aircraft squawking 7500, 7600 or 7700 now (geojson) and in the last 6 hours (items). A squawk is "
            "often set by mistake or for seconds: `polls` counts the 60 s checks that saw it, and readsb's "
            "`emergency` field (when the transponder sends one) confirms the code. Military = adsb.lol's "
            "database flag. MLAT positions are estimates.")


def _sqk_fetch(fetch):
    """{code: (provider, response dict)} plus per-provider stats."""
    stats = {name: dict(_src(name), codes=[]) for name, _ in SQK_PROVIDERS}
    got, dead, fi_calls = {}, set(), 0
    for code in SQUAWKS:
        for name, base in SQK_PROVIDERS:
            if name in dead:
                continue
            st = stats[name]
            if name == "adsb.fi":
                if fi_calls:
                    _sleep(FI_GAP)
                fi_calls += 1
            try:
                d = json.loads(_gunzip(fetch(base + code)))
                ac = d.get("ac") if isinstance(d, dict) else None
                if ac is None and isinstance(d, dict) and d.get("total") == 0:
                    ac = []
                if not isinstance(ac, list):
                    raise ValueError("%s: no ac[] list" % name)
            except Exception as e:  # noqa: BLE001  next provider; skip this one for the rest of the poll
                st["ok"], st["error"] = False, _err(e)
                dead.add(name)
                continue
            if st["ok"] is None:
                st["ok"] = True
            st["n"] += len(ac)
            st["codes"].append(code)
            snap = d.get("now")
            if isinstance(snap, (int, float)):
                st["newest"] = max(st["newest"] or "", _iso(snap / 1000.0))
            got[code] = (name, dict(d, ac=ac))
            break
    return got, [stats[name] for name, _ in SQK_PROVIDERS]


def _rnd(v, k=4):
    return None if v is None else round(float(v), k)


def _sighting(a, code, provider, snap):
    """One readsb aircraft -> the fields the memory keeps."""
    lat, lon, pos_age, stale = a.get("lat"), a.get("lon"), a.get("seen_pos"), False
    if lat is None or lon is None:
        lp = a.get("lastPosition") or {}
        lat, lon, pos_age, stale = lp.get("lat"), lp.get("lon"), lp.get("seen_pos"), True
    pos = [_rnd(lon), _rnd(lat)] if lat is not None and lon is not None else None
    seen = _num(a.get("seen")) or 0.0
    flags = a.get("dbFlags") or 0
    return {
        "hex": (a.get("hex") or "").lower(), "flight": (a.get("flight") or "").strip() or None,
        "reg": a.get("r"), "type": a.get("t"), "desc": a.get("desc"), "op": a.get("ownOp"),
        "squawk": str(a.get("squawk") or code), "emergency": a.get("emergency"),
        "mil": bool(int(flags) & 1) if isinstance(flags, (int, float)) else False,
        "seen_t": int(snap - seen), "pos": pos, "pos_t": int(snap - (_num(pos_age) or 0.0)) if pos else None,
        "stale_pos": stale if pos else None, "mlat": bool(a.get("mlat")) or a.get("type") == "mlat",
        "alt": a.get("alt_baro"), "gs": _rnd(a.get("gs"), 1), "track": _rnd(a.get("track"), 1), "source": provider,
    }


def merge_sightings(memory, sightings, now_ts):
    """Pure: fold this poll's sightings into the 6 h memory (hex -> entry); returns (memory, current hexes)."""
    current = []
    for s in sightings:
        hx = s["hex"]
        if not hx:
            continue
        e = memory.get(hx)
        if e is None:
            e = memory[hx] = {"hex": hx, "first_seen": s["seen_t"], "polls": 0, "squawks": [], "trail": []}
        if hx not in current:
            e["polls"] += 1
            current.append(hx)
        for k in ("flight", "reg", "type", "desc", "op"):
            if s.get(k):
                e[k] = s[k]
        e.update(squawk=s["squawk"], meaning=SQUAWKS.get(s["squawk"]), emergency=s["emergency"],
                 mil=bool(s["mil"] or e.get("mil")), last_seen=max(e.get("last_seen") or 0, s["seen_t"]),
                 alt=s["alt"], gs=s["gs"], track=s["track"], source=s["source"], mlat=s["mlat"])
        e["first_seen"] = min(e["first_seen"], s["seen_t"])
        if s["squawk"] not in e["squawks"]:
            e["squawks"].append(s["squawk"])
        if s["pos"]:
            moved = e.get("pos") != s["pos"]
            e.update(pos=s["pos"], pos_t=s["pos_t"], stale_pos=s["stale_pos"])
            if moved or "loc" not in e:
                e["loc"] = _locate(s["pos"][0], s["pos"][1])
            last = e["trail"][-1] if e["trail"] else None
            if not last or [last[0], last[1]] != s["pos"]:
                e["trail"].append([s["pos"][0], s["pos"][1], s["alt"], s["pos_t"]])
                del e["trail"][:-TRAIL_MAX]
    cutoff = now_ts - MEMORY_S
    for hx in [h for h, e in memory.items() if (e.get("last_seen") or 0) < cutoff]:
        del memory[hx]
    if len(memory) > MEMORY_MAX:
        keep = sorted(memory, key=lambda h: (h in current, memory[h].get("last_seen") or 0), reverse=True)[:MEMORY_MAX]
        memory = {h: memory[h] for h in keep}
    return memory, current


def _sqk_item(e, current):
    loc = e.get("loc") or {}
    return {"hex": e["hex"], "flight": e.get("flight"), "reg": e.get("reg"), "type": e.get("type"),
            "desc": e.get("desc"), "op": e.get("op"), "squawk": e.get("squawk"), "squawks": e.get("squawks"),
            "meaning": e.get("meaning"), "emergency": e.get("emergency"), "mil": e.get("mil", False),
            "current": e["hex"] in current, "polls": e.get("polls"), "first_seen": _iso(e.get("first_seen")),
            "last_seen": _iso(e.get("last_seen")), "pos": e.get("pos"), "pos_time": _iso(e.get("pos_t")),
            "stale_pos": e.get("stale_pos"), "mlat": e.get("mlat"), "alt": e.get("alt"), "gs": e.get("gs"),
            "track": e.get("track"), "source": e.get("source"), "trail": e.get("trail") or [],
            "country": loc.get("country"), "country_name": loc.get("country_name"), "sea": loc.get("sea"),
            "theatre": loc.get("theatre")}


def squawk(now=None, fetch=None):
    now, fetch = _utc(now), fetch or (lambda u: _fetch(u, SQK_TIMEOUT))
    now_ts = now.timestamp()
    got, sources = _sqk_fetch(fetch)
    if not got:
        raise RuntimeError("all ADS-B providers failed: " + "; ".join(s["error"] or "-" for s in sources))
    sightings = []
    for code, (provider, d) in got.items():
        snap = d.get("now")
        snap = snap / 1000.0 if isinstance(snap, (int, float)) and abs(snap / 1000.0 - now_ts) < 3600 else now_ts
        for a in d["ac"]:
            if isinstance(a, dict):
                try:
                    sightings.append(_sighting(a, code, provider, snap))
                except (TypeError, ValueError):  # 1.7.3: one malformed aircraft used to fail the whole 60 s feed
                    continue
    state = _load("squawk")
    memory, current = merge_sightings(state.get("aircraft") or {}, sightings, now_ts)
    _save("squawk", {"t": int(now_ts), "aircraft": memory})

    items = [_sqk_item(e, current) for e in memory.values()]
    items.sort(key=lambda i: (not i["current"], -(memory[i["hex"]].get("last_seen") or 0)))
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": i["pos"]},
              "properties": {k: v for k, v in i.items() if k not in ("pos", "trail")}}
             for i in items if i["current"] and i["pos"]]
    used_fi = any(i["source"] == "adsb.fi" for i in items)
    by_code = {c: sum(1 for i in items if i["current"] and i["squawk"] == c) for c in SQUAWKS}
    missing = [c for c in SQUAWKS if c not in got]
    return {"version": VERSION, "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "count": len(current),
            "recent": len(items), "by_code": by_code, "codes_missing": missing, "sources": sources,
            "attribution": ATTRIBUTION["squawk"] + ("; " + ATTRIBUTION["squawk_fallback"] if used_fi else ""),
            "attribution_url": ATTRIBUTION_URL["squawk"], "licence": LICENCE["squawk"],
            "public_ok": PUBLIC_OK["squawk"], "non_commercial": NON_COMMERCIAL["squawk"], "meanings": SQUAWKS,
            "memory_hours": MEMORY_S // 3600, "note": SQK_NOTE,
            "geojson": {"type": "FeatureCollection", "features": feats}, "items": items}


# ---------------- gpsjam: daily GNSS interference (H3 res 4) ----------------

GPSJAM_MANIFEST = "https://gpsjam.org/data/manifest.csv"
GPSJAM_DAY = "https://gpsjam.org/data/%s-h3_4.csv"
MANIFEST_GAP = 3540      # s: at most one manifest read an hour (59 min, for scheduler jitter)
DAY_RETRY_GAP = 3540     # s between tries of a day file that failed
DAY_MAX_TRIES = 3        # per date
HEX_CAP = 5000           # medium + high hexes kept (~35 bytes each)
LOW_MAX, MEDIUM_MAX = 0.02, 0.10
COLOURS = {"low": "#33ff33", "medium": "#ffff33", "high": "#ff3333"}   # GPSJAM's own, fill-opacity 0.5
GPSJAM_RULE = ("share = (bad - 1) / (good + bad) per hex over the UTC day; low < 2 %, medium 2-10 %, high > 10 % "
               "(GPSJAM's FAQ and map code; the -1 damps hexes with little traffic)")
GPSJAM_NOTE = ("Hexes where aircraft reported degraded GNSS accuracy (ADS-B NACp) over one UTC day, H3 resolution 4 "
               "(~1,770 km2). Usually jamming or spoofing, but not always: GPSJAM notes military trainers over Texas "
               "block their own antennas. Updated daily soon after 00:00 UTC. `suspect` = GPSJAM flags the day's data.")
_H3 = re.compile(r"[0-9a-f]{15}")


def parse_manifest(text):
    """[(date, suspect, num_bad_hexes)] oldest first; columns found by header name."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("GPSJAM manifest is empty")
    head = [h.strip().lower() for h in rows[0]]
    if "date" not in head:
        raise ValueError("GPSJAM manifest without a date column: %s" % head)
    di, si = head.index("date"), head.index("suspect") if "suspect" in head else None
    ni = next((i for i, h in enumerate(head) if h.startswith("num")), None)
    out = []
    for r in rows[1:]:
        if len(r) <= di or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[di].strip()):
            continue
        sus = si is not None and len(r) > si and r[si].strip().lower() == "true"
        n = int(r[ni]) if ni is not None and len(r) > ni and r[ni].strip().isdigit() else None
        out.append((r[di].strip(), sus, n))
    if not out:
        raise ValueError("GPSJAM manifest has no dated rows")
    out.sort()
    return out


def level(good, bad):
    """GPSJAM's colour rule for one hex."""
    total = good + bad
    share = (bad - 1) / total if total else 0.0
    return "low" if share < LOW_MAX else "medium" if share < MEDIUM_MAX else "high"


def parse_day(body, cap=HEX_CAP):
    """Daily CSV (gzip or plain) -> {levels, hexes_total, items [[h3, level, good, bad]], cap}."""
    text = _gunzip(body).decode("utf-8-sig")
    rd = csv.reader(io.StringIO(text))
    head = [h.strip().lower() for h in next(rd, [])]
    try:
        hi, gi, bi = head.index("hex"), head.index("count_good_aircraft"), head.index("count_bad_aircraft")
    except ValueError:
        raise ValueError("GPSJAM day file: unexpected header %s" % head)
    levels, kept, bad_rows = {"low": 0, "medium": 0, "high": 0}, [], 0
    for r in rd:
        try:
            hx, good, bad = r[hi].strip().lower(), int(r[gi]), int(r[bi])
        except (IndexError, ValueError):
            bad_rows += 1
            continue
        if not _H3.fullmatch(hx) or good < 0 or bad < 0 or good + bad == 0:
            bad_rows += 1
            continue
        lv = level(good, bad)
        levels[lv] += 1
        if lv != "low":
            kept.append([hx, lv, good, bad])
    total = sum(levels.values())
    if not total:
        raise ValueError("GPSJAM day file has no hex rows")
    kept.sort(key=lambda h: (h[1] != "high", -((h[3] - 1) / (h[2] + h[3])), -(h[2] + h[3]), h[0]))
    dropped = max(0, len(kept) - cap)
    return {"levels": levels, "hexes_total": total, "rows_skipped": bad_rows, "items": kept[:cap],
            "cap": {"max": cap, "dropped": dropped,
                    "order": "high before medium, then by bad share, then by aircraft count; the rest dropped"}}


def gpsjam(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    now_ts = now.timestamp()
    state = _load("gpsjam")
    res = state.get("result")
    have = (res or {}).get("date") or ""
    yesterday = (now.date() - dt.timedelta(days=1)).isoformat()
    m = state.get("manifest") or {}
    msrc = dict(_src("manifest"), fetched=False)

    due = now_ts - (m.get("t") or 0) >= MANIFEST_GAP
    if due and have < yesterday:
        msrc["fetched"] = True
        try:
            rows = parse_manifest(_gunzip(fetch(GPSJAM_MANIFEST)).decode("utf-8-sig"))
            m = {"t": int(now_ts), "ok": True, "error": None, "newest": rows[-1][0], "suspect": rows[-1][1],
                 "n": len(rows)}
        except Exception as e:  # noqa: BLE001  keep the last good newest date
            m = dict(m, t=int(now_ts), ok=False, error=_err(e))
        state["manifest"] = m
    msrc.update(ok=m.get("ok"), error=m.get("error"), newest=m.get("newest"), n=m.get("n") or 0,
                checked_at=_iso(m.get("t")))

    dsrc = dict(_src("day"), fetched=False)
    want = m.get("newest")
    if want and want > have:
        tries = state.get("tries") or {}
        if tries.get("date") != want:
            tries = {"date": want, "n": 0, "t": 0}
        if tries["n"] < DAY_MAX_TRIES and now_ts - tries["t"] >= DAY_RETRY_GAP:
            tries.update(n=tries["n"] + 1, t=int(now_ts))
            dsrc["fetched"] = True
            try:
                p = parse_day(fetch(GPSJAM_DAY % want))
                res = dict(p, date=want, suspect=bool(m.get("suspect")), processed_at=_iso(now_ts))
                state["result"] = res
                dsrc["ok"] = True
            except Exception as e:  # noqa: BLE001  the last good day stays on the map
                dsrc.update(ok=False, error=_err(e))
                tries["error"] = dsrc["error"]
        else:
            dsrc.update(ok=False, error=tries.get("error") or "waiting to retry %s" % want)
        state["tries"] = tries
    elif res:
        dsrc["ok"] = True
    if res:
        dsrc.update(newest=res["date"], n=res["hexes_total"])
    _save("gpsjam", state)
    if not res:
        raise RuntimeError("GPSJAM: no day processed yet (manifest: %s; day: %s)" % (msrc["error"] or "ok",
                                                                                  dsrc["error"] or "not tried"))
    return {"version": VERSION, "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "count": len(res["items"]),
            "date": res["date"], "suspect": res.get("suspect", False), "processed_at": res.get("processed_at"),
            "levels": res["levels"], "hexes_total": res["hexes_total"], "resolution": 4,
            "items_format": ["h3", "level", "good", "bad"], "cap": res["cap"], "rule": GPSJAM_RULE,
            "colours": COLOURS, "sources": [msrc, dsrc], "attribution": ATTRIBUTION["gpsjam"],
            "attribution_url": ATTRIBUTION_URL["gpsjam"], "licence": LICENCE["gpsjam"],
            "public_ok": PUBLIC_OK["gpsjam"], "non_commercial": NON_COMMERCIAL["gpsjam"], "note": GPSJAM_NOTE,
            "items": res["items"]}


# ---------------- tfr: US temporary flight restrictions ----------------

TFR_LIST = "https://tfr.faa.gov/tfrapi/getTfrList"
TFR_WFS = ("https://tfr.faa.gov/geoserver/TFR/ows?service=WFS&version=1.1.0&request=GetFeature"
           "&typeName=TFR:V_TFR_LOC&maxFeatures=500&outputFormat=application/json&srsname=EPSG:4326")
TFR_XML = "https://tfr.faa.gov/download/detail_%s.xml"
TFR_PAGE = "https://tfr.faa.gov/tfr3/?page=detail_%s"
DETAIL_BUDGET = 30       # XML fetches per poll
DETAIL_DEADLINE = 60.0   # s of XML fetching per poll
DETAIL_GAP = 0.3         # s between XML fetches
DETAIL_RETRY = 3600      # s before a failed XML is tried again (6 h after a 404)
DETAIL_MAX_NET_ERRORS = 3
CIRCLE_POINTS = 64
ARC_STEP = 5.0           # degrees
TEXT_MAX = 400
R_NM = 3440.065
_UOM_NM = {"NM": 1.0, "KM": 1 / 1.852, "M": 1 / 1852.0, "FT": 1 / 6076.12, "SM": 0.868976, "MI": 0.868976}
_NOTAM_ID = re.compile(r"\d{1,2}/\d{1,5}")
TFR_NOTE = ("FAA temporary flight restrictions. status: active (now inside effective..expires), upcoming, expired, or "
            "unknown (no NOTAM detail fetched yet; shape from the FAA map service, no altitudes). Floors and "
            "ceilings are as published: AGL, MSL or flight level. Not for navigation.")


def _deg(s):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([NSEW])", (s or "").strip().upper())
    if not m:
        raise ValueError("bad coordinate %r" % s)
    v = float(m.group(1))
    return -v if m.group(2) in "SW" else v


def _utc_iso(s):
    """'2026-11-21T06:00:00' (XNOTAM times are UTC) -> '2026-11-21T06:00:00Z'."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _mod_iso(s):
    """mod_abs_time '202611200403' (UTC) -> ISO."""
    try:
        return dt.datetime.strptime(str(s).strip()[:12], "%Y%m%d%H%M").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _dest(lon, lat, brg, nm):
    p1, l1, th, d = math.radians(lat), math.radians(lon), math.radians(brg), nm / R_NM
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(th))
    l2 = l1 + math.atan2(math.sin(th) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return [round((math.degrees(l2) + 540) % 360 - 180, 5), round(math.degrees(p2), 5)]


def _bearing_nm(c, p):
    p1, p2, dl = math.radians(c[1]), math.radians(p[1]), math.radians(p[0] - c[0])
    brg = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                  math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return brg, 2 * R_NM * math.asin(min(1.0, math.sqrt(h)))


def circle_ring(lon, lat, r_nm, n=CIRCLE_POINTS):
    """Closed n-point ring (n + 1 coordinates), counter-clockwise as RFC 7946 asks."""
    ring = [_dest(lon, lat, -360.0 * i / n, r_nm) for i in range(n)]
    return ring + [ring[0]]


def arc_points(c, p, q, r_nm, clockwise, step=ARC_STEP):
    """Points strictly between p and q on the arc around c (clockwise = bearing increasing)."""
    b0, b1 = _bearing_nm(c, p)[0], _bearing_nm(c, q)[0]
    sweep = (b1 - b0) % 360 if clockwise else -((b0 - b1) % 360)
    if abs(sweep) < 1e-9:
        sweep = 360.0 if clockwise else -360.0
    n = max(2, int(math.ceil(abs(sweep) / step)))
    return [_dest(c[0], c[1], b0 + sweep * i / n, r_nm) for i in range(1, n)]


def _txt(e, path):
    x = e.find(path)
    return x.text.strip() if x is not None and x.text and x.text.strip() else None


def _pt(v, lat="geoLat", lon="geoLong"):
    la, lo = _txt(v, lat), _txt(v, lon)
    return [round(_deg(lo), 5), round(_deg(la), 5)] if la and lo else None


def _radius_nm(v):
    r = _num(_txt(v, "valRadiusArc"))
    return None if r is None else r * _UOM_NM.get((_txt(v, "uomRadiusArc") or "NM").upper(), 1.0)


def _close(ring):
    if ring and ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    return ring if len(ring) >= 4 else None


def _shape_ring(avx):
    """XNOTAM Avx vertices (GRC points, CWA/CCA arcs to the next vertex) -> closed ring."""
    pts = []
    for i, v in enumerate(avx):
        kind = (_txt(v, "codeType") or "GRC").upper()
        if kind in ("CWA", "CCA"):
            own = _pt(v)
            if own:
                pts.append(own)
            c, r = _pt(v, "geoLatArc", "geoLongArc"), _radius_nm(v)
            nxt = next((_pt(w) for w in avx[i + 1:] if _pt(w)), None) or (pts[0] if pts else None)
            if c and pts and nxt:
                r = r if r else _bearing_nm(c, pts[-1])[1]
                pts += arc_points(c, pts[-1], nxt, r, kind == "CWA")
        else:
            p = _pt(v)
            if p:
                pts.append(p)
    return _close(pts)


def _alt(code, val, uom):
    v = _num(val)
    if v is None:
        return None
    code, uom = (code or "").upper() or None, (uom or "FT").upper()
    if uom == "FL":
        text = "UNL" if v >= 999 else "FL%03d" % v
    elif v == 0 and code in (None, "HEI", "SFC"):
        text = "SFC"
    else:
        ref = {"HEI": "AGL", "ALT": "MSL"}.get(code or "", "")
        text = ("%d %s %s" % (v, "m" if uom == "M" else "ft", ref)).strip()
    return {"val": int(v) if v.is_integer() else v, "uom": uom, "ref": code, "text": text}


def parse_detail(body):
    """XNOTAM-Update XML (bytes) -> the parts GT uses."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    body = body.strip()
    root = ET.fromstring(body[3:] if body[:3] == b"\xef\xbb\xbf" else body)   # the FAA files start with a BOM
    n = root.find(".//Not")
    if n is None:
        raise ValueError("XNOTAM without a Not element")
    seq, year = _txt(n, "NotUid/noSeqNo"), _txt(n, "NotUid/dateIndexYear")
    areas = []
    for grp in n.iter("TFRAreaGroup"):
        a = grp.find("aseTFRArea")
        if a is None:
            continue
        sched = a.findall("ScheduleGroup")
        area = {"name": _txt(a, "txtName"),
                "floor": _alt(_txt(a, "codeDistVerLower"), _txt(a, "valDistVerLower"), _txt(a, "uomDistVerLower")),
                "ceiling": _alt(_txt(a, "codeDistVerUpper"), _txt(a, "valDistVerUpper"), _txt(a, "uomDistVerUpper")),
                "effective": _utc_iso(_txt(sched[0], "dateEffective")) if sched else None,
                "expires": _utc_iso(_txt(sched[0], "dateExpire")) if sched else None,
                "scheduled": (_txt(a, "isScheduledTfrArea") or "").upper() == "TRUE",
                "days": [d.text.strip() for d in a.findall("dayCode") if d.text and d.text.strip()],
                "geom": "none", "rings": []}
        shapes = [abd for s in grp.findall("aseShapes") for abd in s.findall("Abd")]
        avx0 = shapes[0].findall("Avx") if len(shapes) == 1 else []
        if len(avx0) == 1 and (_txt(avx0[0], "codeType") or "").upper() == "CIR":
            c, r = _pt(avx0[0]) or _pt(avx0[0], "geoLatArc", "geoLongArc"), _radius_nm(avx0[0])
            if c and r:
                area.update(geom="circle", rings=[circle_ring(c[0], c[1], r)],
                            circle={"lon": c[0], "lat": c[1], "r_nm": round(r, 3)})
        if not area["rings"]:
            merged = [_close([p for p in (_pt(v) for v in m.findall("Avx")) if p])
                      for m in grp.findall("abdMergedArea")]
            if any(merged):
                area.update(geom="merged", rings=[r for r in merged if r])
        if not area["rings"] and shapes:
            rings = [_shape_ring(abd.findall("Avx")) for abd in shapes]
            if any(rings):
                area.update(geom="shape", rings=[r for r in rings if r])
        areas.append(area)
    text = re.sub(r"\s+", " ", _txt(n, "txtDescrUSNS") or "").strip()
    return {"notam_id": "%s/%s" % (year[-1], seq) if seq and year else None,
            "issued": _utc_iso(_txt(n, "NotUid/dateIssued")), "effective": _utc_iso(_txt(n, "dateEffective")),
            "expires": _utc_iso(_txt(n, "dateExpire")), "tz": _txt(n, "codeTimeZone"),
            "cfr": _txt(n, "TfrNot/codeType"), "city": _txt(n, "AffLocGroup/txtNameCity"),
            "state": _txt(n, "AffLocGroup/txtNameUSState"), "facility": _txt(n, "codeFacility"),
            "areas": areas, "text": text[:TEXT_MAX] + ("..." if len(text) > TEXT_MAX else "")}


def parse_list(d):
    if not isinstance(d, list):
        raise ValueError("getTfrList: expected a list, got %s" % type(d).__name__)
    out = []
    for t in d:
        nid = str((t or {}).get("notam_id") or "").strip()
        if not _NOTAM_ID.fullmatch(nid):
            continue
        out.append({"notam_id": nid, "type": t.get("type"), "description": (t.get("description") or "").strip(),
                    "state": t.get("state"), "facility": t.get("facility"),
                    "mod": str(t.get("mod_abs_time") or "").strip(), "is_new": t.get("is_new") == "Y"})
    return out


def parse_wfs(d):
    """GeoServer GeoJSON -> {notam_id: {"rings": [...], "type", "title", "state", "facility", "mod"}}."""
    feats = (d or {}).get("features")
    if not isinstance(feats, list):
        raise ValueError("TFR WFS: no features")
    out = {}
    for f in feats:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        nid = str(p.get("NOTAM_KEY") or "").split("-")[0]
        if not _NOTAM_ID.fullmatch(nid) or g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        e = out.setdefault(nid, {"rings": [], "type": p.get("LEGAL"), "title": (p.get("TITLE") or "").strip(),
                                 "state": p.get("STATE"), "facility": p.get("CNS_LOCATION_ID"),
                                 "mod": str(p.get("LAST_MODIFICATION_DATETIME") or "")})
        for poly in polys:
            if poly and len(poly[0]) >= 4:
                e["rings"].append([[round(float(x), 5), round(float(y), 5)] for x, y in (c[:2] for c in poly[0])])
    return out


def _status(eff, exp, now_iso):
    if eff is None and exp is None:
        return "active"   # published with no times: in force until cancelled
    if exp and exp <= now_iso:
        return "expired"
    if eff and eff > now_iso:
        return "upcoming"
    return "active"


def _centroid(rings):
    pts = [p for r in rings for p in r[:-1]]
    return [round(sum(p[0] for p in pts) / len(pts), 4), round(sum(p[1] for p in pts) / len(pts), 4)] if pts else None


def _span(areas, key, lowest):
    vals = [a[key] for a in areas if a.get(key)]
    if not vals:
        return None
    ft = lambda x: x["val"] * (100 if x["uom"] == "FL" else 3.28084 if x["uom"] == "M" else 1)  # noqa: E731
    return (min if lowest else max)(vals, key=ft)["text"]


def tfr(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    now_ts, now_iso = now.timestamp(), now.strftime("%Y-%m-%dT%H:%M:%SZ")
    state = _load("tfr")
    details = state.get("details") or {}
    lsrc, wsrc, dsrc = _src("faa_list"), _src("faa_shapes"), dict(_src("faa_detail"), pending=0, cached=0)

    try:
        lst = parse_list(json.loads(_gunzip(fetch(TFR_LIST))))
        if not lst and (state.get("list") or {}).get("items"):
            # 1.7.3: the FAA always has TFRs in force; an empty answer after a full one is a fault, and taking it as
            # the list emptied the map and threw away every cached NOTAM detail
            raise ValueError("getTfrList: empty list")
        state["list"] = {"t": int(now_ts), "items": lst}
        lsrc["ok"] = True
    except Exception as e:  # noqa: BLE001  fall back to the last good list
        lst = (state.get("list") or {}).get("items")
        lsrc.update(ok=False, error=_err(e), stale_since=_iso((state.get("list") or {}).get("t")))
    try:
        shapes = parse_wfs(json.loads(_gunzip(fetch(TFR_WFS))))
        state["shapes"] = {"t": int(now_ts), "by_id": shapes}
        wsrc["ok"] = True
    except Exception as e:  # noqa: BLE001
        shapes = (state.get("shapes") or {}).get("by_id") or {}
        wsrc.update(ok=False, error=_err(e), stale_since=_iso((state.get("shapes") or {}).get("t")))
    if lst is None:
        if not shapes:
            raise RuntimeError("FAA TFR list and shapes both failed: %s; %s" % (lsrc["error"], wsrc["error"]))
        lst = [{"notam_id": k, "type": v["type"], "description": v["title"], "state": v["state"],
                "facility": v["facility"], "mod": v["mod"], "is_new": False} for k, v in shapes.items()]
    lsrc.update(n=len(lst), newest=max((_mod_iso(t["mod"]) or "" for t in lst), default="") or None)
    wsrc.update(n=sum(len(v["rings"]) for v in shapes.values()),
                newest=max((_mod_iso(v["mod"]) or "" for v in shapes.values()), default="") or None)

    # NOTAM XML only for new or changed TFRs (and failed ones after DETAIL_RETRY)
    def due(t):
        e = details.get(t["notam_id"])
        if not e or e.get("mod") != t["mod"]:
            return True
        return not e.get("ok") and now_ts - (e.get("t") or 0) >= (6 * 3600 if e.get("missing") else DETAIL_RETRY)
    todo = sorted((t for t in lst if due(t)), key=lambda t: t["mod"], reverse=True)
    t0, fetched, net_errors, errors = _clock(), 0, 0, []
    for t in todo[:DETAIL_BUDGET]:
        if _clock() - t0 > DETAIL_DEADLINE or net_errors >= DETAIL_MAX_NET_ERRORS:
            break
        if fetched:
            _sleep(DETAIL_GAP)
        fetched += 1
        nid = t["notam_id"]
        try:
            det = parse_detail(_gunzip(fetch(TFR_XML % nid.replace("/", "_"))))
            details[nid] = {"mod": t["mod"], "t": int(now_ts), "ok": True, "data": det}
            net_errors = 0
        except urllib.error.HTTPError as e:
            details[nid] = {"mod": t["mod"], "t": int(now_ts), "ok": False, "missing": e.code == 404, "error": _err(e)}
            errors.append("%s %s" % (nid, _err(e)))
        except Exception as e:  # noqa: BLE001  network or parse trouble: try again after DETAIL_RETRY
            details[nid] = {"mod": t["mod"], "t": int(now_ts), "ok": False, "error": _err(e)}
            errors.append("%s %s" % (nid, _err(e)))
            if isinstance(e, (urllib.error.URLError, OSError)):
                net_errors += 1
    ids = {t["notam_id"] for t in lst}
    details = {k: v for k, v in details.items() if k in ids}
    state["details"] = details
    _save("tfr", state)
    dsrc.update(ok=not errors, error="; ".join(errors[:3]) or None, n=fetched,
                pending=sum(1 for t in lst if due(t)),
                cached=sum(1 for v in details.values() if v.get("ok")),
                newest=max((v["data"].get("issued") or "" for v in details.values() if v.get("ok")), default="")
                or None)

    feats, items, counts = [], [], {"active": 0, "upcoming": 0, "expired": 0, "unknown": 0}
    for t in lst:
        nid = t["notam_id"]
        e = details.get(nid) or {}
        det = e.get("data") if e.get("ok") else None
        fresh = bool(det) and e.get("mod") == t["mod"]
        base = {"notam_id": nid, "type": t["type"], "title": t["description"], "state": t["state"],
                "facility": t["facility"], "url": TFR_PAGE % nid.replace("/", "_")}
        rings_all = []
        if det and (fresh or nid not in shapes):
            eff, exp = det["effective"], det["expires"]
            status = _status(eff, exp, now_iso)
            for a in det["areas"]:
                if not a["rings"]:
                    continue
                rings_all += a["rings"]
                a_status = _status(a["effective"] or eff, a["expires"] or exp, now_iso)
                g = ({"type": "Polygon", "coordinates": [a["rings"][0]]} if len(a["rings"]) == 1 else
                     {"type": "MultiPolygon", "coordinates": [[r] for r in a["rings"]]})
                props = dict(base, area=a["name"], floor=(a["floor"] or {}).get("text"),
                             ceiling=(a["ceiling"] or {}).get("text"), effective=a["effective"] or eff,
                             expires=a["expires"] or exp, days=a["days"] or None, status=a_status, geom=a["geom"])
                if a.get("circle"):
                    props["circle"] = a["circle"]
                feats.append({"type": "Feature", "geometry": g, "properties": props})
            item = dict(base, effective=eff, expires=exp, tz=det["tz"], cfr=det["cfr"], status=status,
                        floor=_span(det["areas"], "floor", True), ceiling=_span(det["areas"], "ceiling", False),
                        areas=len(det["areas"]), geom="faa_xml" if fresh else "faa_xml_old", text=det["text"])
        else:
            status = "unknown"
            w = shapes.get(nid)
            if w:
                rings_all = w["rings"]
                for r in w["rings"]:
                    feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [r]},
                                  "properties": dict(base, area=None, floor=None, ceiling=None, effective=None,
                                                     expires=None, days=None, status=status, geom="faa_wfs")})
            item = dict(base, effective=None, expires=None, tz=None, cfr=None, status=status, floor=None,
                        ceiling=None, areas=len(w["rings"]) if w else 0, geom="faa_wfs" if w else None, text=None)
        counts[status] += 1
        c = _centroid(rings_all)
        loc = _locate(c[0], c[1]) if c else {}
        item.update(mod=_mod_iso(t["mod"]), is_new=t["is_new"], has_shape=bool(rings_all), centre=c,
                    country=loc.get("country"), theatre=loc.get("theatre"))
        items.append(item)
    order = {"active": 0, "upcoming": 1, "unknown": 2, "expired": 3}
    items.sort(key=lambda i: i["mod"] or "", reverse=True)   # newest change first ...
    items.sort(key=lambda i: order[i["status"]])              # ... within each status (stable sort)
    by_type = {}
    for i in items:
        by_type[i["type"] or "?"] = by_type.get(i["type"] or "?", 0) + 1
    return {"version": VERSION, "fetched_at": now_iso, "count": len(items), "by_status": counts, "by_type": by_type,
            "with_shape": sum(1 for i in items if i["has_shape"]), "sources": [lsrc, wsrc, dsrc],
            "attribution": ATTRIBUTION["tfr"], "attribution_url": ATTRIBUTION_URL["tfr"], "licence": LICENCE["tfr"],
            "public_ok": PUBLIC_OK["tfr"], "non_commercial": NON_COMMERCIAL["tfr"], "note": TFR_NOTE,
            "geojson": {"type": "FeatureCollection", "features": feats}, "items": items}


FEEDS = {"squawk": (squawk, 60), "gpsjam": (gpsjam, 3600), "tfr": (tfr, 900)}
