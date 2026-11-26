#!/usr/bin/env python3
"""Ground Truth server: one process, one port. Serves web/ and /api/*, refreshes feeds in the background.

Env: GT_HOST (default 127.0.0.1), GT_PORT (default 8790), GT_MAP_REFRESH (seconds, default 900),
     GT_DATA (state folder, default ./data), GT_MYMAPS_MID and FIRECRAWL_API_KEY (secrets; else local files),
     GT_MYMAPS_CHANNEL (0.10.0 map auto-follow; else $GT_SEED/mymaps.channel or the local config), GT_MAP_OVERLAP_H.
All URLs the page uses are relative, so it also works behind a path prefix (e.g. Caddy /gt/).
"""
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from gt import alerts, analysis, extfeeds, feeds, geo, mymaps, translate  # noqa: E402
extfeeds.load(feeds.REGISTRY)  # 0.11.0: per-release feed modules (gt/extfeeds.py)
extfeeds.load_private(feeds.REGISTRY)  # 1.8.0: private modules (gt/private/), absent from the public copy

VERSION = open(os.path.join(ROOT, "VERSION")).read().strip()
WEB = os.path.join(ROOT, "web")
CACHE = feeds.CACHE
MAP_REFRESH = int(os.environ.get("GT_MAP_REFRESH", "900"))

STATE = {}          # feed name -> {"ok", "at", "data", "error", "ms"}
LOCK = threading.Lock()
RUNNING = set()
DERIVED = {"events": None, "stats": None, "summary": None, "czib_geo": None, "outages_geo": None, "advisories_geo": None}


def _load_disk_cache():
    for name in list(feeds.REGISTRY) + ["mymaps"]:
        p = os.path.join(CACHE, name + ".json")
        if os.path.exists(p):
            try:
                with open(p) as fh:
                    rec = json.load(fh)
            except Exception:
                continue
            if isinstance(rec, dict):  # 1.7.3: a cache file holding null or a list used to stop the scheduler
                STATE[name] = rec


def _age(name):
    s = STATE.get(name)
    if not s or not s.get("at"):
        return 1e12
    try:
        t = dt.datetime.strptime(s["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):  # 1.7.3: an unreadable stamp means "refresh now", not a dead scheduler
        return 1e12
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds()


# ---------------- push (1.0 / Phase D): /api/stream, Server-Sent Events ----------------
# Every finished feed run is published here; open pages refetch just that feed instead of waiting for their timers.
BUS = {"seq": 0, "log": collections.deque(maxlen=256)}
BUS_COND = threading.Condition()
STREAMS = {"n": 0}
MAX_STREAMS = 24          # each open page holds one thread
STREAM_LIFE_S = 1800      # then the browser reconnects (EventSource does it by itself)


def publish(kind, **data):
    with BUS_COND:
        BUS["seq"] += 1
        BUS["log"].append((BUS["seq"], kind, json.dumps(dict(data, seq=BUS["seq"]), separators=(",", ":"))))
        BUS_COND.notify_all()


def _run(name, fn):
    t0 = time.time()
    try:
        data = fn()
        rec = {"ok": True, "at": feeds.now_iso(), "data": data, "error": None, "ms": int((time.time() - t0) * 1000)}
        p = os.path.join(CACHE, name + ".json")
        with open(p + ".tmp", "w") as fh:  # 1.7.3: temp file + rename, so a crash mid-write cannot truncate the cache
            json.dump(rec, fh, separators=(",", ":"))
        os.replace(p + ".tmp", p)
    except Exception as e:
        prev = STATE.get(name, {})
        rec = {"ok": False, "at": prev.get("at"), "data": prev.get("data"), "error": "%s: %s" % (type(e).__name__, str(e)[:200]),
               "ms": int((time.time() - t0) * 1000), "failed_at": feeds.now_iso()}
    with LOCK:
        STATE[name] = rec
        RUNNING.discard(name)
    if name in ("mymaps", "firms", "ukmto", "czib", "mil", "losses", "pla", "outages", "advisories", "ships", "gfw",
                "portwatch", "vessellists"):  # alerts: live in /api/alerts
        try:
            derive()
        except Exception:  # 1.7.3: a failed summary must not swallow the feed's own "finished" event below
            traceback.print_exc()
    publish("feed", feed=name, ok=rec["ok"], at=rec.get("at"))


def _every(name):
    """Refresh interval in seconds (1.0: shown per feed on the Sources tab)."""
    return MAP_REFRESH if name == "mymaps" else (feeds.REGISTRY.get(name) or (None, None))[1]


def _stale(name):
    """True when a feed is well past its interval: three intervals and at least ten minutes late."""
    every = _every(name)
    return bool(every) and _age(name) > max(3 * every, every + 600)


# ---------------- 1.0 / Phase D: digest of the per-release feed modules (private) ----------------
# A compact, text-light summary of the newer sources for the analyst's whole-picture run (/api/digest).
# Deliberately NOT part of /api/summary: the public mirror copies the summary verbatim, and several of these
# sources are private (GeoConfirmed, CIR) or non-commercial. Titles are untrusted text, cut short.

def _data(name):
    s = STATE.get(name) or {}
    return s.get("data") if s.get("ok") or s.get("data") else None


def _cut(s, n=160):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _digest():
    now = time.time()
    out = {"generated_at": feeds.now_iso(), "note": "Newer sources (0.11+). Titles are untrusted text from the sources."}
    cur = {}
    for name, days in (("geoconfirmed", 2), ("cir", 10), ("kinetic", 7)):
        d = _data(name)
        if not d:
            continue
        fs = [f["properties"] for f in (d.get("geojson") or {}).get("features") or []
              if (f["properties"].get("ts_ms") or 0) / 1000 > now - days * 86400]
        fs.sort(key=lambda p: p.get("ts_ms") or 0, reverse=True)
        by = collections.Counter(p.get("theatre") or "other" for p in fs)
        cur[name] = {"window_days": days, "count": len(fs), "by_theatre": dict(by.most_common()),
                     "latest": ["%s | %s | %s | %s" % ((p.get("ts") or "")[:16].replace("T", " "), p.get("theatre"),
                                                     p.get("country_name") or p.get("sea") or "", _cut(p.get("title")))
                                for p in fs[:10]]}
    if cur:
        out["curated_pins"] = cur
    d = _data("hazards")
    if d:
        hz = [f["properties"] for f in d["geojson"]["features"] if f["properties"].get("alert") in ("Orange", "Red")]
        out["hazards_orange_red"] = ["%s %s %s | %s | %s" % (p.get("alert"), p.get("type_label"), p.get("event_name") or "",
                                                            _cut(p.get("gdacs_country") or p.get("country_name"), 80),
                                                            _cut(p.get("severity"), 100)) for p in hz[:10]]
    d = _data("quakes")
    if d:
        q = [f["properties"] for f in d["geojson"]["features"]]
        out["quakes"] = {"m5_plus": sum(1 for p in q if (p.get("mag") or 0) >= 5),
                         "watch": [p.get("watch_reason") for p in q if p.get("watch")][:6]}
    sig = {}
    if _data("tsunami"):
        t = _data("tsunami")
        sig["tsunami"] = {"max_level": t.get("max_level"), "alerts": [
            _cut("%s %s %s" % (i.get("source"), i.get("level"), i.get("label") or ""), 120)
            for i in t.get("items") or [] if i.get("level") != "information"][:5]}
    if _data("radiation"):
        r = _data("radiation")
        sig["radiation"] = {"flagged_stations": r.get("count"), "network_flag": (r.get("summary") or {}).get("network_flag")}
    if _data("ntas"):
        sig["ntas_active"] = _data("ntas").get("level")
    if _data("ofac"):
        sig["ofac_latest"] = ["%s %s" % (i.get("date"), _cut(i.get("title"), 140)) for i in _data("ofac").get("items", [])[:5]]
    if _data("squawk"):
        sig["squawks_now"] = ["%s %s %s" % (f["properties"].get("squawk"), f["properties"].get("flight") or "",
                                            f["properties"].get("country_name") or f["properties"].get("sea") or "")
                              for f in _data("squawk")["geojson"]["features"]][:8]
    if _data("tfr"):
        sig["us_tfr"] = (_data("tfr").get("by_status") or {})
    if sig:
        out["signals"] = sig
    d = _data("wire")
    if d:  # 0.12.0: counts per theatre and the newest placed headlines (wire.summary keeps it under 2 KB)
        try:
            from gt import wire as _wire
            out["wire"] = _wire.summary(translate.apply(d))  # 1.5.0: English headlines for the analyst too
        except Exception as e:  # noqa: BLE001  (never break the digest)
            out["wire"] = {"error": type(e).__name__}
    d = _data("telegram")
    if d:  # channel named on every line: several channels are partisan
        lat = {}
        for x in d.get("items") or []:
            th = x.get("theatre")
            if th and len(lat.setdefault(th, [])) < 3:
                lat[th].append("%s @%s [%s] %s" % ((x.get("ts") or "")[11:16], x.get("channel"),
                                                  ",".join((x.get("countries") or [])[:2]) or "-", _cut(x.get("title"), 110)))
        out["telegram"] = {"by_theatre": d.get("by_theatre") or {}, "latest": lat,
                           "note": "Channel posts are the channels' own unverified claims; some are partisan."}
    cy, bg = _data("cyber"), _data("bgp")
    if cy or bg:
        out["cyber"] = {"summary": _cut((cy or {}).get("summary"), 420), "infocon": ((cy or {}).get("infocon") or {}).get("level"),
                        "routing_drops": [r.get("name") for r in (bg or {}).get("countries") or [] if r.get("level") == "drop"],
                        "routing_dips": [r.get("name") for r in (bg or {}).get("countries") or [] if r.get("level") == "dip"]}
    return out


def _mymaps():
    fc, st = mymaps.run()
    return {"title": fc["title"], "map_day": fc["map_day"], "events": st["events"], "archive": st["archive"],
            "follow": st.get("follow")}


def scheduler():
    jobs = dict(feeds.REGISTRY)
    jobs["mymaps"] = (_mymaps, MAP_REFRESH)
    while True:
        _tick(jobs)
        time.sleep(5)


def _tick(jobs):
    """One scheduler pass. 1.7.3: a job that cannot be started (bad cached stamp, no thread to spare) is logged and
    skipped; before, the exception ended the scheduler thread and every feed stopped refreshing for good."""
    for name, (fn, every) in jobs.items():
        try:
            failed_recently = (STATE.get(name) or {}).get("failed_at")
            if name in RUNNING:
                continue
            if _age(name) >= every and not (failed_recently and _since(failed_recently) < min(every, 300)):
                with LOCK:
                    RUNNING.add(name)
                try:
                    threading.Thread(target=_run, args=(name, fn), daemon=True).start()
                except Exception:
                    with LOCK:
                        RUNNING.discard(name)
                    raise
        except Exception:
            traceback.print_exc()


def _since(iso):
    try:
        t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):  # 1.7.3: an unreadable stamp never holds a retry back
        return 1e12
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds()


# ---------------- analysis ----------------

def _km(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = math.radians(b[0] - a[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _iso_ms(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def corroborate(fc):
    """Attach satellite-thermal and UKMTO corroboration to curated events."""
    firms = (STATE.get("firms") or {}).get("data") or {}
    pts = firms.get("points") or []
    ukm = ((STATE.get("ukmto") or {}).get("data") or {}).get("items") or []
    n_th = n_uk = 0
    for f in fc["features"]:
        p = f["properties"]
        if p.get("kind") != "event" or f["geometry"]["type"] != "Point":
            continue
        c = f["geometry"]["coordinates"]
        if p.get("category") in ("strike", "energy", "missile", "maritime", "drone") and p.get("ts_ms"):
            hits = []
            for lon, lat, frp, ts, conf, dn, *_sat in pts:
                if abs(lon - c[0]) > 0.2 or abs(lat - c[1]) > 0.15:
                    continue
                d = _km(c, (lon, lat))
                dtm = (_iso_ms(ts) - p["ts_ms"]) / 3600000
                # detections must start no earlier than 1 h before the report: earlier heat at the
                # same spot is usually a persistent source (smelter, refinery, gas flare), not the event
                if d <= 12 and -1 <= dtm <= 18:
                    hits.append((d, frp, ts))
            if hits:
                n_th += 1
                p["thermal"] = {"n": len(hits), "nearest_km": round(min(h[0] for h in hits), 1),
                                "max_frp": round(max(h[1] for h in hits), 1), "first": min(h[2] for h in hits)}
        if p.get("theatre") == "middle-east" and p.get("category") == "maritime":
            near = [i for i in ukm if i.get("coord") and _km(c, i["coord"]) <= 60]
            if near:
                n_uk += 1
                p["ukmto"] = [{"num": i["num"], "date": i["date"], "type": i["type"]} for i in near[:4]]
    return n_th, n_uk


def derive():
    try:
        with open(os.path.join(mymaps.DATA, "latest.geojson")) as fh:
            fc = json.load(fh)
        with open(os.path.join(mymaps.DATA, "stats.json")) as fh:
            st = json.load(fh)
    except FileNotFoundError:
        return
    n_th, n_uk = corroborate(fc)
    ev = [f["properties"] for f in fc["features"] if f["properties"]["kind"] == "event"]
    newest = max((e.get("ts_ms") or 0) for e in ev) if ev else 0
    now_ms = int(time.time() * 1000)

    def window(hours, ref):
        return [e for e in ev if e.get("ts_ms") and ref - e["ts_ms"] <= hours * 3600000]
    d = lambda n: (STATE.get(n) or {}).get("data") or {}
    last24 = window(24, now_ms)
    by_th = {}
    for e in last24:
        by_th[e["theatre"]] = by_th.get(e["theatre"], 0) + 1
    latest = sorted(ev, key=lambda e: -(e.get("ts_ms") or 0))[:1]
    ukm = d("ukmto").get("items") or []
    week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    firms_by = {}
    for lon, lat, *_ in d("firms").get("points") or []:
        th = feeds.in_any_clip(lon, lat)
        firms_by[th] = firms_by.get(th, 0) + 1
    summary = {
        "version": VERSION, "generated": feeds.now_iso(), "map_title": st.get("title"), "map_day": st.get("map_day"),
        "map_follow": st.get("follow"),  # 0.10.0: auto-follow status (days, times, flags; never IDs)
        "events_total": len(ev), "events_24h": len(last24), "events_6h": len(window(6, now_ms)),
        "events_24h_by_theatre": by_th, "newest_event_age_min": int((now_ms - newest) / 60000) if newest else None,
        "latest_event": {k: latest[0].get(k) for k in ("title", "theatre", "category", "ts", "url", "country_name")} if latest else None,
        "thermal_corroborated": n_th, "ukmto_matched": n_uk,
        "mil_aircraft": d("mil").get("count"), "mil_aircraft_by_role": d("mil").get("roles"),
        "mil_aircraft_notable": _mil_notable(d("mil")), "ru_losses_personnel_today": (d("losses").get("increase") or {}).get("personnel_units"),
        "ru_losses_day": d("losses").get("day"), "ukmto_incidents_7d": sum(1 for i in ukm if i["date"] >= week_ago),
        "ukmto_latest": ukm[0] if ukm else None, "firms_hotspots_by_theatre": firms_by,
        "taiwan_pla": d("pla"), "israel_alerts": {"active_now": d("tzevalive").get("active_now"), "cities_alerted_24h": d("tzeva").get("cities_alerted_24h"),
                                              "last_alert": d("tzeva").get("last_alert")},
        "airspace_czib_active": d("czib").get("active"),
        "firms_by_satellite": d("firms").get("by_satellite"),
        "internet_outages": _outage_summary(d("outages")),
        "travel_advisories": _advisory_summary(d("advisories")),
        "ships_last_hour_by_area": {k: {x: v.get(x) for x in ("ships_1h", "underway", "tankers", "cargo")}
                                    for k, v in (d("ships").get("areas") or {}).items()} or None,
        "ship_types_known_pct": d("ships").get("typed_pct"),
        "ship_traffic_gfw": _gfw_summary(d("gfw")),
        "chokepoint_transits_portwatch": feeds.portwatch.summary(d("portwatch")),
        "listed_ships_heard": _listed_summary(d("ships"), d("vessellists")),
        "feeds_ok": sum(1 for v in STATE.values() if v.get("ok")), "feeds_total": len(STATE),
    }
    DERIVED.update(events=fc, stats=st, summary=summary, czib_geo=_czib_geo(),
                   outages_geo=_outages_geo(d("outages")), advisories_geo=_advisories_geo(d("advisories")))


def _outage_summary(o):
    """Compact view for the summary and the analyst: watched countries, their regions, the biggest elsewhere."""
    if not o:
        return None
    cs = o.get("countries") or []
    pick = lambda c: {"country": c["name"], "ongoing": c["ongoing"], "max_score": c["max_score"], "last": c.get("last"),
                      "sources": sorted({e["source"] for e in c["events"]})}
    return {"window_h": o.get("window_h"), "countries_with_outages": len(cs),
            "watched_countries": [pick(c) for c in cs if c["watched"]][:10],
            "watched_regions": [{k: r[k] for k in ("country", "region", "start", "hours", "ongoing", "source")}
                                for r in (o.get("regions") or [])[:12]],
            "largest_elsewhere": [pick(c) for c in sorted((c for c in cs if not c["watched"]),
                                                          key=lambda c: -c["max_score"])[:3]]}


# Summary keys under a NON-COMMERCIAL licence (Global Fishing Watch, CC BY-NC 4.0). Strip these, and anything the
# analyst derives from them, before any trading use of /api/summary or the analysis history.
NON_COMMERCIAL_KEYS = ("ship_traffic_gfw", "chokepoint_transits_portwatch", "listed_ships_heard")  # 0.9.0: IMF PortWatch,
# OpenSanctions (CC BY-NC 4.0)
# 0.11.0+: the per-release feed modules never enter the summary; each feed's non_commercial flag is in /api/status
# ("modules"). /api/digest, /api/cyber_geo and /api/news_geo are built from them and are non-commercial as a whole. The analyst's
# whole-picture run (1.4+) reads /api/digest, so its picture is non-commercial too: never feed it to trading.


def _listed_summary(sh, vl, limit=12):
    """Ships heard on AIS in the last hour whose IMO or MMSI is on a sanctions, shadow-fleet or detention list
    (OpenSanctions, NON-COMMERCIAL). Marks: S sanctioned, G Ukraine GUR shadow-fleet list, D port-state detention."""
    if not sh or not vl:
        return None
    rows = sh.get("listed") or []
    by_area, by_mark = {}, {}
    for r in rows:
        for m in r.get("marks") or "":
            by_mark[m] = by_mark.get(m, 0) + 1
        if set(r.get("marks") or "") & set("SG"):
            by_area[r["area"]] = by_area.get(r["area"], 0) + 1
    rows = [r for r in rows if set(r.get("marks") or "") & set("SG")] + [r for r in rows if not set(r.get("marks") or "") & set("SG")]
    return {"heard_1h": len(rows), "by_mark": by_mark, "sanctioned_or_shadow_by_area": by_area, "list_version": vl.get("version"), "licence": vl.get("licence"),
            "ships": [{k: r.get(k) for k in ("name", "cls", "flag", "area", "marks", "lists", "sog", "dest", "match")}
                      for r in rows[:limit]],
            "note": "A list entry about the ship's identifiers, not proof of what it is doing now; MMSIs get reused."}


NOTABLE_ROLES = ("tanker", "isr", "drone", "bomber")


def _mil_notable(m, limit=15):
    """Tankers, ISR/patrol, drones and bombers on ADS-B now, for the analyst: who, what, roughly where."""
    out = []
    for f in (m.get("geojson") or {}).get("features", []):
        p = f["properties"]
        if p.get("role") not in NOTABLE_ROLES:
            continue
        lon, lat = f["geometry"]["coordinates"]
        out.append({"callsign": p.get("flight") or None, "role": p["role"], "type": p.get("tname") or p.get("type"),
                    "operator": p.get("owner"), "lat": round(lat, 1), "lon": round(lon, 1), "alt_ft": p.get("alt"),
                    "theatre": feeds.in_any_clip(lon, lat)})
    out.sort(key=lambda x: (NOTABLE_ROLES.index(x["role"]), x["theatre"] is None))
    return out[:limit] or None


def _gfw_summary(g):
    """Compact GFW view for the summary and the analyst: per-area daily ship counts against two baselines."""
    if not g or not g.get("areas"):
        return None
    keep = ("label", "kind", "last_full_day_vessels", "avg_7d", "median_prior_28d", "change_vs_28d_pct",
            "same_week_last_year_avg", "change_vs_last_year_pct", "gaps_30d", "stale")
    areas = {}
    for k, a in g["areas"].items():
        x = {f: a[f] for f in keep if a.get(f) is not None}
        x["top_flags_per_day_7d"] = (a.get("top_flags_7d") or [])[:5]
        t = (a.get("types_by_day") or {}).get(a.get("last_full_day"))
        if t:
            x["types_last_full_day"] = t
        areas[k] = x
    return {"data_through": g.get("data_through"), "licence": g.get("licence"), "areas": areas,
            "ais_off_events_30d": [{f: e.get(f) for f in ("area", "start", "hours", "name", "flag", "type")}
                                   for e in (g.get("gaps") or [])[:8]],
            "note": "Distinct non-fishing ships seen per day (satellite + terrestrial AIS), about 4 days behind; "
                    "ships with AIS switched off are not counted."}


def _advisory_summary(a):
    if not a:
        return None
    recent = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    return {"level4": a.get("level4"), "level3": a.get("level3"), "watching_since": a.get("watching_since"),
            "level_changes": a.get("changes", [])[:10],
            "updated_14d_level3plus": [{k: i[k] for k in ("country", "level", "date")} for i in a.get("items", [])
                                       if i["level"] >= 3 and i["date"] >= recent][:15]}


def _feature(a3, props):
    shape = geo.country_shapes().get(a3)
    return {"type": "Feature", "geometry": shape["geom"], "properties": props} if shape else None


_CYBER_GEO = {"key": None, "fc": None}


def _cyber_geo():
    """0.13.0: country shapes with the cyber feed's per-country counts and the bgp routing level (private)."""
    c, b = STATE.get("cyber") or {}, STATE.get("bgp") or {}
    key = (c.get("at"), b.get("at"))
    if _CYBER_GEO["fc"] is not None and _CYBER_GEO["key"] == key:
        return _CYBER_GEO["fc"]
    rows = {}
    for a3, r in ((c.get("data") or {}).get("by_country") or {}).items():
        rows[a3] = {k: r.get(k) or 0 for k in ("ransom_7d", "ransom_ci_7d", "ransom_24h", "attacks_7d", "attacks_ci_7d",
                                                "ddos_now", "ddos_7d")}
        rows[a3]["sectors"] = ", ".join("%s %d" % kv for kv in sorted((r.get("ci_sectors") or {}).items(),
                                                                     key=lambda kv: -kv[1])[:5])
        rows[a3]["groups"] = ", ".join((r.get("groups") or [])[:5])
    for r in (b.get("data") or {}).get("countries") or []:
        if r.get("a3"):
            pct = r.get("pct") or {}
            rows.setdefault(r["a3"], {"ransom_7d": 0, "ransom_ci_7d": 0, "ddos_now": 0, "ddos_7d": 0}).update(
                bgp=r.get("level"), bgp_v4=pct.get("v4"), bgp_asns=pct.get("asns"), bgp_a2=r.get("a2"),
                bgp_reasons="; ".join(r.get("reasons") or []))
    feats = []
    for a3, p in rows.items():
        shape = geo.country_shapes().get(a3)
        if shape:
            feats.append({"type": "Feature", "geometry": shape["geom"], "properties": dict(p, a3=a3, name=shape["name"])})
    fc = {"type": "FeatureCollection", "features": feats}
    _CYBER_GEO.update(key=key, fc=fc)
    return fc


_NEWS_GEO = {"key": None, "fc": None}


def _news_geo():
    """0.12.0: one point per country (Natural Earth label point) with wire and Telegram story counts (private)."""
    w, t = STATE.get("wire") or {}, STATE.get("telegram") or {}
    key = (w.get("at"), t.get("at"))
    if _NEWS_GEO["fc"] is not None and _NEWS_GEO["key"] == key:
        return _NEWS_GEO["fc"]
    rows = {}
    for feed, d in (("wire", w.get("data") or {}), ("tg", t.get("data") or {})):
        for span, field in (("48h", "by_country"), ("24h", "by_country_24h")):
            for a3, n in (d.get(field) or {}).items():
                rows.setdefault(a3, {"wire_48h": 0, "wire_24h": 0, "tg_48h": 0, "tg_24h": 0})["%s_%s" % (feed, span)] = n
    feats = []
    for a3, p in rows.items():
        shape = geo.country_shapes().get(a3) or {}
        if shape.get("label"):
            p.update(a3=a3, name=shape["name"], theatre=geo.theatre_for_a3(a3), n24=p["wire_24h"] + p["tg_24h"],
                     n48=p["wire_48h"] + p["tg_48h"])
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": shape["label"]}, "properties": p})
    feats.sort(key=lambda f: -f["properties"]["n48"])
    fc = {"type": "FeatureCollection", "features": feats}
    _NEWS_GEO.update(key=key, fc=fc)
    return fc


def _outages_geo(o):
    feats = []
    for c in (o or {}).get("countries") or []:
        a3 = geo.a3_for_a2(c["code"])
        f = a3 and _feature(a3, {"code": c["code"], "name": c["name"], "ongoing": c["ongoing"], "watched": c["watched"],
                                 "max_score": c["max_score"], "n": len(c["events"]), "last": c.get("last")})
        if f:
            feats.append(f)
    return {"type": "FeatureCollection", "features": feats}


def _advisories_geo(a):
    best = {}
    for i in (a or {}).get("items") or []:
        if i["level"] < 3:
            continue
        for a3 in geo.a3s_for_name(i["country"]):
            if a3 not in best or i["level"] > best[a3]["level"]:
                best[a3] = i
    feats = [_feature(a3, {k: i.get(k) for k in ("country", "level", "label", "date", "url")}) for a3, i in best.items()]
    return {"type": "FeatureCollection", "features": [f for f in feats if f]}


_CZIB_GEO = {"key": None, "fc": None}


def _czib_geo():
    zones = ((STATE.get("czib") or {}).get("data") or {}).get("zones") or []
    names = {(z.get("country") or "").lower(): z for z in zones}
    if not names:
        return {"type": "FeatureCollection", "features": []}
    # 1.7.3: derive() runs after every one of 13 feeds (one of them every 45 s) and this used to re-read the 3 MB
    # Natural Earth file each time. The answer only changes when the zone list does.
    key = json.dumps(zones, sort_keys=True)
    if _CZIB_GEO["key"] == key:
        return _CZIB_GEO["fc"]
    with open(geo.REF, encoding="utf-8") as fh:
        ne = json.load(fh)
    alias = {"russian federation": "russia", "iran (islamic republic of)": "iran", "syrian arab republic": "syria",
             "united states": "united states of america"}
    feats = []
    for f in ne["features"]:
        p = f["properties"]
        cands = {(p.get(k) or "").lower() for k in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN")}
        hit = next((names[n] for n in names if n in cands or alias.get(n) in cands), None)
        if not hit:
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        slim = [[[[round(x, 2), round(y, 2)] for x, y in ring[::3] + [ring[0]]] for ring in poly] for poly in polys]
        feats.append({"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": slim},
                      "properties": {"name": hit["name"], "country": hit["country"], "valid_until": hit["valid_until"]}})
    fc = {"type": "FeatureCollection", "features": feats}
    _CZIB_GEO.update(key=key, fc=fc)
    return fc


def brief():
    fc = DERIVED["events"]
    if not fc:
        return {"theatres": []}
    ev = [f["properties"] for f in fc["features"] if f["properties"]["kind"] == "event"]
    now_ms = int(time.time() * 1000)
    out = []
    for th, label in geo.THEATRES.items():
        items = sorted([e for e in ev if e["theatre"] == th], key=lambda e: -(e.get("ts_ms") or 0))
        if not items:
            continue
        cats, places = {}, {}
        for e in items:
            cats[e["category"]] = cats.get(e["category"], 0) + 1
            pl = e.get("sea") if e.get("sea") not in (None, "offshore", "open ocean") else e.get("country_name")
            if pl:
                places[pl] = places.get(pl, 0) + 1
        top = lambda d, n: [k for k, _ in sorted(d.items(), key=lambda kv: -kv[1])[:n]]
        out.append({"theatre": th, "label": label, "count": len(items),
                    "last_24h": sum(1 for e in items if e.get("ts_ms") and now_ms - e["ts_ms"] <= 86400000),
                    "top_categories": [{"category": c, "n": cats[c]} for c in top(cats, 4)],
                    "hotspots": [{"place": p, "n": places[p]} for p in top(places, 4)],
                    "thermal": sum(1 for e in items if e.get("thermal")),
                    "headlines": [{"title": e["title"], "ts": e.get("ts"), "url": e.get("url"), "handle": e.get("handle")} for e in items[:5]]})
    return {"generated": feeds.now_iso(), "method": "rule-based v0.1 (counts, hotspots, latest headlines)", "theatres": out}


# ---------------- X post enrichment (on demand, cached) ----------------

def xpost(post_id):
    if not re.fullmatch(r"\d{5,25}", post_id or ""):
        raise ValueError("bad id")
    d = os.path.join(CACHE, "x")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, post_id + ".json")
    if os.path.exists(p):
        return json.load(open(p))
    t = feeds.get_json("https://api.fxtwitter.com/status/" + post_id, timeout=20).get("tweet") or {}
    media = [{"type": m.get("type"), "url": m.get("thumbnail_url") or m.get("url")}
             for m in ((t.get("media") or {}).get("all") or [])][:4]
    out = {"text": t.get("text"), "created_at": t.get("created_at"), "author": (t.get("author") or {}).get("name"),
           "handle": (t.get("author") or {}).get("screen_name"), "likes": t.get("likes"), "views": t.get("views"),
           "lang": t.get("lang"), "media": media, "community_note": bool(t.get("community_note"))}
    json.dump(out, open(p, "w"))
    return out


# ---------------- HTTP ----------------

GZIP_MIN = 1024  # bytes; smaller answers are not worth a gzip header


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):
        if args and isinstance(args[0], str) and "/api/" in args[0]:
            return
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    def _json(self, obj, code=200, cache="no-store", etag=None):
        body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()
        if etag:  # polled every few seconds: an unchanged answer is a 304 with no body
            tag = '"%s"' % etag
            if self.headers.get("If-None-Match") == tag:
                self.send_response(304)
                self.send_header("ETag", tag)
                self.send_header("Cache-Control", cache)
                self.end_headers()
                return
        # 1.7.3: gzip for clients that ask for it. Nothing in front of this server compresses, and feed/ships alone
        # is about 400 KB of JSON every few minutes per open page (about 130 KB gzipped, 8 ms at level 5).
        zipped = len(body) >= GZIP_MIN and "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
        if zipped:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", cache)
        self.send_header("Vary", "Accept-Encoding")
        if zipped:
            self.send_header("Content-Encoding", "gzip")
        if etag:
            self.send_header("ETag", tag)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self):
        """Server-Sent Events: "hello" (version) on connect, then one "feed" event per finished feed run."""
        with BUS_COND:
            if STREAMS["n"] >= MAX_STREAMS:
                return self._json({"error": "too many open streams"}, 503)
            STREAMS["n"] += 1
            last = BUS["seq"]
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            hello = json.dumps({"version": VERSION, "seq": last}, separators=(",", ":"))
            self.wfile.write(("retry: 15000\nevent: hello\ndata: %s\n\n" % hello).encode())
            self.wfile.flush()
            end = time.time() + STREAM_LIFE_S
            while time.time() < end:
                with BUS_COND:
                    BUS_COND.wait_for(lambda: BUS["seq"] > last, timeout=20)
                    items = [x for x in BUS["log"] if x[0] > last]
                if items:
                    last = items[-1][0]
                    out = "".join("id: %d\nevent: %s\ndata: %s\n\n" % x for x in items)
                else:
                    out = ": ping\n\n"   # keeps proxies from timing the stream out
                self.wfile.write(out.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass
        finally:
            with BUS_COND:
                STREAMS["n"] -= 1

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        if not path.startswith("/api/"):
            if path.endswith(".js") or path.endswith(".css"):
                pass
            return super().do_GET()
        try:
            if path == "/api/events":
                return self._json(DERIVED["events"] or {"type": "FeatureCollection", "features": []})
            if path == "/api/stats":
                return self._json(DERIVED["stats"] or {})
            if path == "/api/summary":
                return self._json(dict(DERIVED["summary"] or {}, analyst=analysis.headline(), regional_alerts=alerts.summary(STATE)))
            if path == "/api/alerts":
                v = alerts.view(STATE)
                stable = dict(v, generated=None, israel=dict(v["israel"], at=None, live_at=None), regions=dict(v["regions"], at=None),
                              embassy=dict(v["embassy"], at=None))
                tag = hashlib.sha1(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
                return self._json(v, cache="no-cache", etag=tag)  # the tag ignores fetch times, so quiet polls are 304s
            if path == "/api/analysis":
                return self._json(analysis.overview())
            if path == "/api/analysis/events":
                return self._json(analysis.events())
            if path == "/api/analysis/history":
                q = urllib.parse.parse_qs(u.query)
                lim = int((q.get("limit") or ["48"])[0]) if (q.get("limit") or ["48"])[0].isdigit() else 48
                return self._json(analysis.history(lim, full=(q.get("full") or ["0"])[0] == "1"))
            if path == "/api/brief":
                return self._json(brief())
            if path == "/api/czib_geo":
                return self._json(DERIVED["czib_geo"] or {"type": "FeatureCollection", "features": []}, cache="max-age=3600")
            if path in ("/api/outages_geo", "/api/advisories_geo"):
                return self._json(DERIVED[path[5:]] or {"type": "FeatureCollection", "features": []}, cache="max-age=300")
            if path == "/api/stream":
                return self._stream()
            if path == "/api/cyber_geo":
                return self._json(_cyber_geo(), cache="no-store")
            if path == "/api/news_geo":
                return self._json(_news_geo(), cache="no-store")
            if path == "/api/digest":
                return self._json(_digest(), cache="no-store")
            if path.startswith("/api/private/"):
                hit = _private_get(path, u.query)
                return self._json(*hit) if hit else self._json({"error": "not found"}, 404)
            if path == "/api/status":
                return self._json({"version": VERSION, "now": feeds.now_iso(), "modules": extfeeds.status(),
                                   **{_PRIV_KEY: _private_web()},
                                   "streams": STREAMS["n"], "feeds": {
                    k: {"ok": v.get("ok"), "at": v.get("at"), "age_s": int(_age(k)) if v.get("at") else None,
                        "error": v.get("error"), "ms": v.get("ms"), "running": k in RUNNING,
                        "every": _every(k), "stale": _stale(k)}
                    for k, v in sorted(STATE.items())}})
            if path == "/api/xpost":
                q = urllib.parse.parse_qs(u.query)
                return self._json(xpost((q.get("id") or [""])[0]), cache="max-age=86400")
            m = re.fullmatch(r"/api/feed/([a-z]+)", path)
            if m and m.group(1) in STATE:
                s = STATE[m.group(1)]
                data = translate.apply(s.get("data"), m.group(1)) if m.group(1) in translate.FEEDS else s.get("data")  # 1.5.0; 1.5.3 feed
                return self._json({"ok": s.get("ok"), "at": s.get("at"), "error": s.get("error"), "data": data},
                                  cache="no-store")
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": "%s" % type(e).__name__}, 500)


_PRIV_KEY = "private_web"  # the status key that lists web/private scripts (the public audit looks for it in site data)


def _private_web():
    """1.8.0: script names in web/private/ (the private pages' code), so a page loads exactly what this server has.
    Empty where the folder is absent (the public copy)."""
    try:
        return sorted(f for f in os.listdir(os.path.join(WEB, "private")) if re.fullmatch(r"[A-Za-z0-9_-]+\.js", f))
    except OSError:
        return []


def _private_get(path, query):
    try:
        from gt.private import routes
    except ImportError:
        return None
    return routes.get(path, urllib.parse.parse_qs(query))


def _post(handler):
    """POST /api/analysis/{events,picture}: analyst results, and (1.5.0) POST /api/translations: English for
    non-English Feed items (gt/translate.py). Both token-gated with the analyst's token (see gt/analysis.py)."""
    path = urllib.parse.urlparse(handler.path).path
    if path.startswith("/api/private/"):  # 1.8.0: private routes (gt/private/routes.py), absent from the public copy
        try:
            from gt.private import routes
        except ImportError:
            return handler._json({"error": "not found"}, 404)
        try:
            n = int(handler.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if not 0 < n <= analysis.MAX_BODY:
            return handler._json({"error": "body must be 1 byte to %d bytes" % analysis.MAX_BODY}, 413)
        try:
            body = json.loads(handler.rfile.read(n).decode("utf-8"))
            hit = routes.post(path, body, handler.headers.get("X-GT-Token")) if isinstance(body, dict) else ({"error": "body must be a JSON object"}, 400)
        except ValueError as e:
            return handler._json({"error": str(e)[:200]}, 400)
        except Exception as e:
            traceback.print_exc()
            return handler._json({"error": type(e).__name__}, 500)
        return handler._json(*hit) if hit else handler._json({"error": "not found"}, 404)
    if path not in ("/api/analysis/events", "/api/analysis/picture", "/api/translations"):
        return handler._json({"error": "not found"}, 404)
    if not analysis.authorized(handler.headers.get("X-GT-Token")):
        return handler._json({"error": "forbidden"}, 403)
    try:
        n = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        n = 0
    if not 0 < n <= analysis.MAX_BODY:
        return handler._json({"error": "body must be 1 byte to %d bytes" % analysis.MAX_BODY}, 413)
    try:
        body = json.loads(handler.rfile.read(n).decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("body must be a JSON object")
        if path == "/api/translations":
            return handler._json(translate.store(body.get("items"), body.get("run")))
        if path.endswith("/events"):
            return handler._json(analysis.merge_events(body.get("items"), body.get("run")))
        return handler._json(analysis.store_picture(body.get("picture"), body.get("run")))
    except ValueError as e:
        return handler._json({"error": str(e)[:200]}, 400)
    except Exception as e:
        traceback.print_exc()
        return handler._json({"error": type(e).__name__}, 500)


Handler.do_POST = _post


def main():
    host = os.environ.get("GT_HOST", "127.0.0.1")
    port = int(os.environ.get("GT_PORT") or os.environ.get("PORT") or "8790")
    _load_disk_cache()
    derive()
    threading.Thread(target=scheduler, daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    print("Ground Truth %s on http://%s:%d" % (VERSION, host, port), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
