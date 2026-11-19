#!/usr/bin/env python3
"""Ground Truth server: one process, one port. Serves web/ and /api/*, refreshes feeds in the background.

Env: GT_HOST (default 127.0.0.1), GT_PORT (default 8790), GT_MAP_REFRESH (seconds, default 900),
     GT_DATA (state folder, default ./data), GT_MYMAPS_MID and FIRECRAWL_API_KEY (secrets; else local files).
All URLs the page uses are relative, so it also works behind a path prefix (e.g. Caddy /gt/).
"""
import datetime as dt
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
from gt import alerts, analysis, feeds, geo, mymaps  # noqa: E402

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
                STATE[name] = json.load(open(p))
            except Exception:
                pass


def _age(name):
    s = STATE.get(name)
    if not s or not s.get("at"):
        return 1e12
    t = dt.datetime.strptime(s["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds()


def _run(name, fn):
    t0 = time.time()
    try:
        data = fn()
        rec = {"ok": True, "at": feeds.now_iso(), "data": data, "error": None, "ms": int((time.time() - t0) * 1000)}
        with open(os.path.join(CACHE, name + ".json"), "w") as fh:
            json.dump(rec, fh, separators=(",", ":"))
    except Exception as e:
        prev = STATE.get(name, {})
        rec = {"ok": False, "at": prev.get("at"), "data": prev.get("data"), "error": "%s: %s" % (type(e).__name__, str(e)[:200]),
               "ms": int((time.time() - t0) * 1000), "failed_at": feeds.now_iso()}
    with LOCK:
        STATE[name] = rec
        RUNNING.discard(name)
    if name in ("mymaps", "firms", "ukmto", "czib", "mil", "losses", "pla", "outages", "advisories", "ships", "gfw"):  # alerts: live in /api/alerts
        derive()


def _mymaps():
    fc, st = mymaps.run()
    return {"title": fc["title"], "map_day": fc["map_day"], "events": st["events"], "archive": st["archive"]}


def scheduler():
    jobs = dict(feeds.REGISTRY)
    jobs["mymaps"] = (_mymaps, MAP_REFRESH)
    while True:
        for name, (fn, every) in jobs.items():
            failed_recently = STATE.get(name, {}).get("failed_at")
            if name in RUNNING:
                continue
            if _age(name) >= every and not (failed_recently and _since(failed_recently) < min(every, 300)):
                with LOCK:
                    RUNNING.add(name)
                threading.Thread(target=_run, args=(name, fn), daemon=True).start()
        time.sleep(5)


def _since(iso):
    t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
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
        "ships_last_hour_by_area": {k: {x: v.get(x) for x in ("ships_1h", "underway", "tankers")}
                                    for k, v in (d("ships").get("areas") or {}).items()} or None,
        "ship_traffic_gfw": _gfw_summary(d("gfw")),
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
NON_COMMERCIAL_KEYS = ("ship_traffic_gfw",)


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


def _czib_geo():
    zones = ((STATE.get("czib") or {}).get("data") or {}).get("zones") or []
    names = {(z.get("country") or "").lower(): z for z in zones}
    if not names:
        return {"type": "FeatureCollection", "features": []}
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
    return {"type": "FeatureCollection", "features": feats}


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
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", cache)
        if etag:
            self.send_header("ETag", tag)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
                stable = dict(v, generated=None, israel=dict(v["israel"], at=None, live_at=None), regions=dict(v["regions"], at=None))
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
            if path == "/api/status":
                return self._json({"version": VERSION, "now": feeds.now_iso(), "feeds": {
                    k: {"ok": v.get("ok"), "at": v.get("at"), "age_s": int(_age(k)) if v.get("at") else None,
                        "error": v.get("error"), "ms": v.get("ms"), "running": k in RUNNING}
                    for k, v in sorted(STATE.items())}})
            if path == "/api/xpost":
                q = urllib.parse.parse_qs(u.query)
                return self._json(xpost((q.get("id") or [""])[0]), cache="max-age=86400")
            m = re.fullmatch(r"/api/feed/([a-z]+)", path)
            if m and m.group(1) in STATE:
                s = STATE[m.group(1)]
                return self._json({"ok": s.get("ok"), "at": s.get("at"), "error": s.get("error"), "data": s.get("data")},
                                  cache="no-store")
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": "%s" % type(e).__name__}, 500)


def _post(handler):
    """POST /api/analysis/{events,picture}: analyst results, token-gated (see gt/analysis.py)."""
    path = urllib.parse.urlparse(handler.path).path
    if path not in ("/api/analysis/events", "/api/analysis/picture"):
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
