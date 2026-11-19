"""Live feeds. Each fetcher returns a JSON-serialisable dict; the server caches and refreshes them.

Every source here was tested keyless on 2026-11-15 except UKMTO and the CENTCOM public releases,
which go through Firecrawl (Cloudflare / Akamai block plain HTTP clients) using the key in
~/.config/firecrawl/key. Firecrawl use is capped per source per day (FIRECRAWL_DAILY).
0.4.0 adds IODA internet outages, US travel advisories, War Department releases, the NOAA-21 fire
satellite and AISStream ship positions (gt/ais.py, free key).
0.5.0 adds Global Fishing Watch ship traffic (gt/gfw.py, free non-commercial token): daily ship counts for
chokepoints and seas the volunteer AIS network can't hear, about 4 days behind, plus AIS-off events.
That feed is CC BY-NC 4.0: never pass it to the trading agent.
0.6.0 identifies military aircraft (gt/aircraft.py): registry type and operator from hexdb.io, cached per
airframe, and a role (tanker, ISR, fighter, ...) for the map icons. Photos are fetched by the browser.
0.7.0 adds live regional air-raid and missile alerts (gt/alerts.py, keyless): Israel every 5 s (Tzeva Adom),
Ukraine, Russian regions and Poland every 60 s (alerts.in.ua SITREP, ubilling.net.ua fallback).
0.8.0 adds US embassy and consulate alerts (gt/embassy.py, keyless): 38 posts' own alert RSS, conditional
requests, Middle East and Europe posts every 5 min, the rest every 15 min.
0.9.0 tracks tankers: the AIS feed keeps a 30-day vessel registry (gt/ais.py 1.1), flags from the MMSI (gt/mid.py),
marks ships on sanctions, shadow-fleet and detention lists (gt/sanctions.py, OpenSanctions, CC BY-NC, daily) and
adds IMF PortWatch chokepoint transits (gt/portwatch.py, every 6 h). Both new sources are non-commercial: never
for the trading agent.
"""
import email.utils
import csv
import datetime as dt
import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from . import aircraft, alerts, embassy, geo, portwatch, sanctions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# GT_DATA moves all state out of the code folder (the container mounts code read-only at /app, data at /data).
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")
UA = "Mozilla/5.0 (GroundTruth/0.7 personal OSINT dashboard)"
os.makedirs(CACHE, exist_ok=True)

# Theatre boxes used to clip global feeds (lon_min, lat_min, lon_max, lat_max)
CLIP = {
    "ukraine-russia": (21.0, 43.0, 60.0, 60.0),
    "middle-east": (32.0, 11.0, 63.0, 40.0),
    "europe-nato": (-11.0, 35.0, 32.0, 71.0),
}


def get(url, timeout=30, headers=None, data=None):
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url, **kw):
    return json.loads(get(url, **kw))


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def in_any_clip(lon, lat):
    for name, (x0, y0, x1, y1) in CLIP.items():
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            return name
    return None


# ---------------- military aircraft (ADS-B) ----------------

_REGISTRY = None


def _aircraft_registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = aircraft.Registry(os.path.join(CACHE, "aircraft_registry.json"))
    return _REGISTRY


def mil_aircraft():
    last_err = None
    for src, url in (("adsb.lol", "https://api.adsb.lol/v2/mil"), ("adsb.fi", "https://opendata.adsb.fi/api/v2/mil")):
        try:
            d = get_json(url, timeout=20)
            feats = []
            for a in d.get("ac", []):
                if a.get("lat") is None or a.get("lon") is None:
                    continue
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]},
                              "properties": {"hex": a.get("hex"), "flight": (a.get("flight") or "").strip(), "reg": a.get("r"),
                                             "type": a.get("t"), "alt": a.get("alt_baro"), "gs": a.get("gs"),
                                             "track": a.get("track") or 0, "squawk": a.get("squawk"), "category": a.get("category"),
                                             "emergency": a.get("emergency"), "nic": a.get("nic"), "nacp": a.get("nac_p")}})
            break
        except Exception as e:  # fall through to the next provider
            last_err = e
    else:
        raise RuntimeError("all ADS-B providers failed: %s" % last_err)
    # Identity: registry lookups for new airframes (non-ICAO "~" addresses have no registry entry), then roles.
    reg = _aircraft_registry()
    try:
        lookups = reg.fill([f["properties"]["hex"] for f in feats if re.fullmatch(r"[0-9a-f]{6}", f["properties"]["hex"] or "")])
    except Exception as e:  # the registry is a nicety; never lose the positions over it
        lookups = {"error": "%s: %s" % (type(e).__name__, str(e)[:120])}
    roles = {}
    for f in feats:
        p = aircraft.enrich(f["properties"], reg.get(f["properties"]["hex"]))
        roles[p["role"]] = roles.get(p["role"], 0) + 1
    return {"source": src, "count": len(feats), "roles": roles, "registry": lookups,
            "geojson": {"type": "FeatureCollection", "features": feats}}


# ---------------- DeepStateMap frontline ----------------

def deepstate():
    d = get_json("https://deepstatemap.live/api/history/last", timeout=45)
    feats = []
    for f in d["map"]["features"]:
        if f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            continue
        p = f["properties"]
        name = (p.get("name") or "").split("///")
        label = name[1].strip() if len(name) > 1 else name[0].strip()
        feats.append({"type": "Feature", "geometry": f["geometry"],
                      "properties": {"label": label, "fill": p.get("fill", "#bcaaa4"),
                                     "fill_opacity": float(p.get("fill-opacity", 0.3)), "stroke": p.get("stroke", "#bcaaa4")}})
    return {"snapshot_id": d.get("id"), "updated": d.get("datetime"), "count": len(feats),
            "geojson": {"type": "FeatureCollection", "features": feats}}


# ---------------- Russian losses (Ukrainian General Staff) ----------------

def ru_losses():
    d = get_json("https://russianwarship.rip/api/v2/statistics/latest")["data"]
    return {"date": d.get("date"), "day": d.get("day"), "stats": d.get("stats"), "increase": d.get("increase")}


# ---------------- NASA FIRMS thermal anomalies ----------------

FIRMS_FILES = [  # keyless global 24 h files; SNPP stalled on 2026-11-12, so it is left out
    ("N20", "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv"),
    ("N21", "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_24h.csv"),
]


def firms():
    """Point = [lon, lat, frp, ts, confidence, day/night, satellite]."""
    pts, by_sat, errors = [], {}, {}
    for sat, url in FIRMS_FILES:
        try:
            raw = get(url, timeout=120).decode("utf-8", "replace")
        except Exception as e:
            errors[sat] = "%s: %s" % (type(e).__name__, str(e)[:120])
            continue
        n = 0
        for r in csv.DictReader(io.StringIO(raw)):
            try:
                lat, lon = float(r["latitude"]), float(r["longitude"])
            except (KeyError, ValueError):
                continue
            th = in_any_clip(lon, lat)
            if not th or r.get("confidence") == "l":
                continue
            t = r.get("acq_time", "0000").zfill(4)
            ts = "%sT%s:%s:00Z" % (r.get("acq_date"), t[:2], t[2:])
            pts.append([round(lon, 4), round(lat, 4), float(r.get("frp") or 0), ts, r.get("confidence"), r.get("daynight"), sat])
            n += 1
        by_sat[sat] = n
    if not by_sat:
        raise RuntimeError("no FIRMS file could be read: %s" % errors)
    pts.sort(key=lambda q: q[3])
    return {"satellite": "NOAA-20 + NOAA-21 VIIRS 375 m", "count": len(pts), "by_satellite": by_sat, "errors": errors,
            "points": pts, "note": "Thermal anomalies include gas flares and field fires; use as corroboration, not proof."}


# ---------------- UKMTO maritime incidents (via Firecrawl) ----------------

FIRECRAWL_KEY = os.path.expanduser("~/.config/firecrawl/key")
FIXED_SEA = {
    "strait of hormuz": (56.35, 26.45), "arabian gulf": (51.5, 27.0), "persian gulf": (51.5, 27.0),
    "gulf of oman": (58.0, 24.6), "gulf of aden": (47.0, 12.6), "red sea": (40.0, 18.0), "bab el-mandeb": (43.4, 12.6),
}
BEARINGS = {"north": 0, "northeast": 45, "north-east": 45, "east": 90, "southeast": 135, "south-east": 135,
            "south": 180, "southwest": 225, "south-west": 225, "west": 270, "northwest": 315, "north-west": 315}


# Calls per day per source. 6-hourly refreshes need 4; the rest leaves room for restarts and retries.
# Worst case 16/day = ~480 credits a month, inside the free tier's 1,000.
FIRECRAWL_DAILY = {"ukmto": 8, "centcom": 8}


def _firecrawl_budget_ok(tag):
    p = os.path.join(CACHE, "firecrawl_budget.json")
    today = dt.date.today().isoformat()
    try:
        b = json.load(open(p))
    except Exception:
        b = {}
    if b.get("date") != today:
        b = {"date": today, "calls": 0}
    by = b.setdefault("by", {})
    if by.get(tag, 0) >= FIRECRAWL_DAILY.get(tag, 4):
        return False
    by[tag] = by.get(tag, 0) + 1
    b["calls"] = b.get("calls", 0) + 1
    json.dump(b, open(p, "w"))
    return True


def firecrawl_markdown(url, tag, max_age_s=3600):
    """Page markdown via Firecrawl. max_age_s bounds how old a Firecrawl-cached copy may be
    (the v2 API otherwise serves copies up to 2 days old)."""
    key = (os.environ.get("FIRECRAWL_API_KEY") or "").strip() or open(FIRECRAWL_KEY).read().strip()
    if not _firecrawl_budget_ok(tag):
        raise RuntimeError("Firecrawl daily budget for %s reached" % tag)
    body = json.dumps({"url": url, "formats": ["markdown"], "onlyMainContent": True,
                       "maxAge": int(max_age_s * 1000)}).encode()
    d = json.loads(get("https://api.firecrawl.dev/v2/scrape", timeout=90, data=body,
                       headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}))
    return d["data"]["markdown"], d["data"].get("metadata", {}).get("creditsUsed")


def _geocode(q):
    p = os.path.join(CACHE, "geocode.json")
    try:
        cache = json.load(open(p))
    except Exception:
        cache = {}
    if q in cache:
        return cache[q]
    time.sleep(1.1)  # Nominatim policy: max 1 req/s, cache everything
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 1, "viewbox": "30,5,65,35", "bounded": 1})
    try:
        r = get_json(url, headers={"User-Agent": "GroundTruth/0.2 (personal research dashboard)"})
        cache[q] = [float(r[0]["lon"]), float(r[0]["lat"])] if r else None
    except Exception:
        cache[q] = None
    json.dump(cache, open(p, "w"))
    return cache[q]


def _offset(lon, lat, nm, bearing_deg):
    d = nm * 1852 / 6371000.0
    b = math.radians(bearing_deg)
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return [round(math.degrees(lo2), 4), round(math.degrees(la2), 4)]


def locate_ukmto(text):
    m = re.search(r"(\d+)\s*NM\s+(north-?east|north-?west|south-?east|south-?west|north|south|east|west)\s+of\s+([A-Z][\w’'\- ]+?(?:,\s*[A-Z][\w ]+)?)(?=[.\n]|\sin\s)", text, re.I)
    if m:
        nm, brg, place = int(m.group(1)), m.group(2).lower(), m.group(3).strip()
        base = _geocode(place)
        if base:
            return _offset(base[0], base[1], nm, BEARINGS.get(brg, 0)), "%s NM %s of %s" % (nm, brg, place), "offset"
    low = text.lower()
    for k, (lo, la) in FIXED_SEA.items():
        if k in low:
            return [lo, la], k.title(), "area-centroid"
    return None, None, None


def ukmto():
    md, credits = firecrawl_markdown("https://www.ukmto.org/", "ukmto")  # homepage lists ~60 recent incidents
    with open(os.path.join(CACHE, "ukmto_raw.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    rx = re.compile(r"###\s*\[(?P<type>[A-Za-z ]+?)\s+UKMTO\s*\\?#(?P<num>\d+)\]\((?P<url>[^)]+)\)\s*\n\s*-\s*!\[\]\([^)]*\)\s*(?P<date>\d{1,2} \w+ \d{4})\s*\n(?P<text>.*?)(?=\n###|\nExplore|\Z)", re.S)
    items = []
    for m in rx.finditer(md):
        text = re.sub(r"\s+", " ", m.group("text")).strip()
        coord, where, method = locate_ukmto(text)
        try:
            date = dt.datetime.strptime(m.group("date"), "%d %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            date = m.group("date")
        items.append({"num": int(m.group("num")), "type": m.group("type").strip(), "date": date, "text": text[:420],
                      "url": m.group("url").replace("\\", ""), "coord": coord, "where": where, "geo_method": method})
    items.sort(key=lambda i: (i["date"], i["num"]), reverse=True)
    return {"count": len(items), "located": sum(1 for i in items if i["coord"]), "credits_used": credits, "items": items}


# ---------------- GDELT machine-coded conflict events ----------------

_gdelt_buf = {}


def gdelt(max_files=8):
    """Material-conflict events (CAMEO roots 18-20) with city-level geo from the 15-minute export."""
    last = get("http://data.gdeltproject.org/gdeltv2/lastupdate.txt").decode().split("\n")
    url = [l.split()[-1] for l in last if l.endswith(".export.CSV.zip")][0]
    stamp = re.search(r"(\d{14})", url).group(1)
    want = [stamp]
    t = dt.datetime.strptime(stamp, "%Y%m%d%H%M%S")
    for i in range(1, max_files):
        want.append((t - dt.timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S"))
    for s in want:
        if s in _gdelt_buf:
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(get("http://data.gdeltproject.org/gdeltv2/%s.export.CSV.zip" % s, timeout=40)))
        except Exception:
            continue
        rows = []
        for line in z.read(z.namelist()[0]).decode("utf-8", "replace").split("\n"):
            c = line.split("\t")
            if len(c) < 61 or c[28] not in ("18", "19", "20") or c[51] not in ("3", "4"):
                continue
            try:
                lat, lon = float(c[56]), float(c[57])
            except ValueError:
                continue
            rows.append([round(lon, 3), round(lat, 3), c[26], c[52][:60], c[6][:30], c[16][:30], int(c[31] or 0), c[60][:240]])
        _gdelt_buf[s] = rows
    for k in list(_gdelt_buf):
        if k not in want:
            del _gdelt_buf[k]
    pts = [r for k in sorted(_gdelt_buf) for r in _gdelt_buf[k]]
    return {"window_files": len(_gdelt_buf), "latest": stamp, "count": len(pts), "points": pts,
            "fields": ["lon", "lat", "cameo", "place", "actor1", "actor2", "mentions", "url"],
            "note": "Machine-coded from news; noisy. Treat as a heat signal."}


# ---------------- regional air-raid / missile alerts ----------------
# Israel (Tzeva Adom, mirroring Home Front Command), Ukraine, Russian regions and Poland (alerts.in.ua SITREP):
# see gt/alerts.py. 0.6's tzevaadom() (history once a minute, borrowed Origin/Referer headers) is replaced.


# ---------------- Taiwan MND daily PLA activity ----------------

def taiwan_pla():
    base = "https://air.mnd.gov.tw/EN/News/"
    lst = get(base + "News_List.aspx?CID=214").decode("utf-8", "replace")
    link = re.search(r'News_Detail\.aspx\?CID=214&(?:amp;)?ID=(\d+)', lst)
    if not link:
        raise RuntimeError("MND list layout changed")
    url = base + "News_Detail.aspx?CID=214&ID=" + link.group(1)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", get(url).decode("utf-8", "replace")))

    def n(rx):
        m = re.search(rx, txt, re.I)
        return int(m.group(1)) if m else None
    date = re.search(r"(\d{4}/\d{2}/\d{2})", txt)
    return {"date": date.group(1) if date else None, "aircraft": n(r"(\d+)\s+sorties? of PLA aircraft"),
            "plan_ships": n(r"(\d+)\s+PLAN (?:ships|vessels)"), "official_ships": n(r"(\d+)\s+official ships"),
            "entered_adiz": n(r"(\d+)\s+out of \d+\s+sorties?"), "url": url}


# ---------------- EASA conflict-zone airspace bulletins ----------------

def easa_czib():
    d = get_json("https://www.easa.europa.eu/en/domains/air-operations/czibs/export-json?page&_format=json")
    zones = [{"name": z.get("name"), "country": z.get("country"), "status": z.get("status"),
              "valid_until": z.get("valid_until_date"), "issued": (z.get("issued_date") or "")[:10]}
             for z in d.get("conflict_zones", [])]
    active = [z for z in zones if (z["status"] or "").lower() == "active"]
    return {"count": len(zones), "active": len(active), "zones": active}


# ---------------- official statements ----------------

# CENTCOM: the RSS "News Articles" channel (ArticleCS ContentType=1) stopped updating in Feb 2026, no RSS
# channel carries the public releases, and the HTML pages sit behind Akamai, which refuses plain HTTP
# clients. So the releases list is read through Firecrawl, at most every CENTCOM_EVERY seconds.
CENTCOM_URL = "https://www.centcom.mil/MEDIA/PUBLIC-RELEASES/"
CENTCOM_EVERY = 6 * 3600
CENTCOM_RETRY = 3 * 3600  # after a failed fetch, so a broken page can't drain the Firecrawl budget
OFFICIAL_RSS = [
    # War Department (formerly DoD, defense.gov) news releases; ContentType=9, checked current on 2026-11-16
    ("War Dept", "https://www.war.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=9&Site=945&max=15"),
    ("UK MoD", "https://www.gov.uk/government/organisations/ministry-of-defence.atom"),
]
# Routine items with no watch-floor value (UK MoD posts regulatory notices and welfare guidance to the same feed).
OFFICIAL_SKIP = re.compile(r"^(Regulation:|Notice of|Contracts for)", re.I)
_CENTCOM_RX = re.compile(
    r"(?P<date>[A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+\d{4})\s*\n\s*\[(?P<title>[^\]\n]+)\]"
    r"\((?P<url>https?://www\.centcom\.mil/MEDIA/PUBLIC-RELEASES/Article/(?P<id>\d+)/[^)\s]*)\)")


def _centcom_date(s):
    """'Nov. 7, 2026' / 'Sept. 30, 2026' / 'May 2, 2026' -> '2026-11-07'."""
    mon, rest = s.split(None, 1)
    try:
        return dt.datetime.strptime("%s %s" % (mon.rstrip(".")[:3].title(), rest), "%b %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return s


def parse_centcom_releases(md):
    items, seen = [], set()
    for m in _CENTCOM_RX.finditer(md):
        if m.group("id") in seen:
            continue
        seen.add(m.group("id"))
        items.append({"source": "CENTCOM", "title": m.group("title").replace("\\", "").strip(),
                      "url": m.group("url"), "date": _centcom_date(m.group("date"))})
    items.sort(key=lambda i: i["date"], reverse=True)
    return items


def centcom_releases():
    """(items, fetched_at, error). Served from cache/centcom_releases.json between Firecrawl reads."""
    p = os.path.join(CACHE, "centcom_releases.json")
    try:
        c = json.load(open(p))
    except Exception:
        c = {}
    now = time.time()
    if c.get("items") and now - c.get("fetched", 0) < CENTCOM_EVERY:
        return c["items"], c.get("at"), None
    if now - c.get("failed", 0) < CENTCOM_RETRY:
        return c.get("items") or [], c.get("at"), c.get("error")
    try:
        md, _credits = firecrawl_markdown(CENTCOM_URL, "centcom")
        items = parse_centcom_releases(md)
        if not items:
            raise ValueError("no releases found on %s (page layout changed?)" % CENTCOM_URL)
        c = {"fetched": now, "at": now_iso(), "items": items}
        err = None
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, str(e)[:160])
        c.update({"failed": now, "error": err})
    json.dump(c, open(p, "w"))
    return c.get("items") or [], c.get("at"), err


def _iso(s):
    """RSS pubDate (RFC 822) or Atom ISO 8601 -> 'YYYY-MM-DDTHH:MM:SSZ'; anything else unchanged."""
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                d = dt.datetime.strptime(s.strip(), "%a, %d %b %Y")
            except ValueError:
                return s
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rss(who, url):
    out = []
    root = ET.fromstring(get(url))
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"):
            continue
        g = {c.tag.split("}")[-1]: c for c in it}
        link = g.get("link")
        href = (link.get("href") or link.text) if link is not None else None
        date = g.get("pubDate") if "pubDate" in g else g.get("updated")
        out.append({"source": who, "title": (g["title"].text or "").strip() if "title" in g else "",
                    "url": href, "date": _iso(date.text.strip()) if date is not None and date.text else None})
    return out


def official():
    """Newest first within each source, then interleaved, so every source shows near the top
    (the analyst reads the first 8, the page shows the first 10)."""
    groups, errors = [], {}
    items, fetched, err = centcom_releases()
    if err:
        errors["CENTCOM"] = err
    groups.append(items or [{"source": "CENTCOM", "title": "feed error: %s" % (err or "no items"),
                             "url": CENTCOM_URL, "date": None}])
    for who, url in OFFICIAL_RSS:
        try:
            g = _rss(who, url)
        except Exception as e:
            errors[who] = "%s: %s" % (type(e).__name__, str(e)[:160])
            g = [{"source": who, "title": "feed error: %s" % type(e).__name__, "url": url, "date": None}]
        g = [i for i in g if not OFFICIAL_SKIP.match(i["title"] or "")] or g
        g.sort(key=lambda i: i["date"] or "", reverse=True)
        groups.append(g)
    merged = [g[i] for i in range(max(len(g) for g in groups)) for g in groups if i < len(g)]
    return {"count": len(merged), "items": merged[:30], "centcom_fetched": fetched, "errors": errors}


# ---------------- internet outages (IODA, Georgia Tech) ----------------

IODA = "https://api.ioda.inetintel.cc.gatech.edu/v2"
# Countries whose outages the summary (and so the analyst) always lists; others only when large.
WATCH_A2 = {"UA", "RU", "BY", "MD", "IL", "PS", "LB", "SY", "IQ", "IR", "YE", "SA", "AE", "QA", "BH", "KW", "OM",
            "JO", "EG", "TW", "KP", "PL", "LT", "LV", "EE", "FI", "GE", "AM", "AZ"}
IODA_REGION_COUNTRIES = ("UA", "RU", "BY", "IL", "PS", "LB", "SY", "IQ", "IR", "YE", "TW")
IODA_SOURCES = {"bgp": "routing (BGP)", "ping-slash24": "active probing", "merit-nt": "darknet traffic",
                "gtr": "Google traffic"}


def _ioda_regions():
    """{region code: (name, country code)} for the watched countries, refreshed weekly."""
    p = os.path.join(CACHE, "ioda_regions.json")
    try:
        c = json.load(open(p))
        if time.time() - c["fetched"] < 7 * 86400 and c.get("regions"):
            return c["regions"]
    except Exception:
        c = {}
    regions = {}
    for cc in IODA_REGION_COUNTRIES:
        try:
            d = get_json("%s/entities/query?entityType=region&relatedTo=country/%s" % (IODA, cc), timeout=40)
        except Exception:
            return c.get("regions") or regions
        for e in d.get("data") or []:
            regions[e["code"]] = [e["name"], (e.get("attrs") or {}).get("country_code") or cc]
    json.dump({"fetched": time.time(), "regions": regions}, open(p, "w"))
    return regions


def _ioda_events(entity_type, frm, until):
    q = urllib.parse.urlencode({"from": frm, "until": until, "entityType": entity_type, "limit": 3000})
    return get_json("%s/outages/events?%s" % (IODA, q), timeout=90).get("data") or []


def outages(hours=72):
    """Country and (for watched countries) region outage events in the last `hours`."""
    until = int(time.time())
    frm = until - hours * 3600
    iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def rec(x):
        end = x["start"] + x["duration"]
        return {"start": iso(x["start"]), "end": iso(min(end, until)), "hours": round(x["duration"] / 3600, 1),
                "ongoing": end >= until - 1800, "score": int(x.get("score") or 0), "source": x.get("datasource")}
    countries = {}
    for x in _ioda_events("country", frm, until):
        if x["start"] + x["duration"] < frm:
            continue
        a2 = x["location"].split("/")[-1]
        c = countries.setdefault(a2, {"code": a2, "name": x.get("location_name") or a2, "watched": a2 in WATCH_A2,
                                      "events": [], "max_score": 0, "ongoing": False})
        r = rec(x)
        c["events"].append(r)
        c["max_score"] = max(c["max_score"], r["score"])
        c["ongoing"] = c["ongoing"] or r["ongoing"]
    for c in countries.values():
        c["events"].sort(key=lambda r: r["start"], reverse=True)
        c["events"] = c["events"][:6]
        c["last"] = c["events"][0]["end"]
    regions = []
    reg = _ioda_regions()
    for x in _ioda_events("region", frm, until):
        code = x["location"].split("/")[-1]
        if code not in reg or x["start"] + x["duration"] < frm:
            continue
        r = rec(x)
        r.update({"region": reg[code][0], "country": reg[code][1]})
        regions.append(r)
    regions.sort(key=lambda r: r["start"], reverse=True)
    ranked = sorted(countries.values(), key=lambda c: (c["watched"], c["ongoing"], c["max_score"]), reverse=True)
    return {"window_h": hours, "count": len(ranked), "countries": ranked, "regions": regions[:150],
            "sources": IODA_SOURCES,
            "note": "Automatic detections. Google-traffic (gtr) dips can be holidays or measurement noise; "
                    "a drop seen by routing and probing together is the strongest signal."}


# ---------------- US State Department travel advisories ----------------

STATE_TA = "https://travel.state.gov/_res/rss/TAsTWs.xml"


def advisories():
    """Every country's current advisory level, plus level changes seen since Ground Truth started watching."""
    root = ET.fromstring(get(STATE_TA, timeout=60))
    items, seen = [], set()
    for it in root.iter("item"):
        m = re.match(r"(.+?)\s+-\s+Level\s+(\d)\s*:\s*(.+)$", (it.findtext("title") or "").strip())
        if not m or m.group(1).strip() in seen:
            continue
        seen.add(m.group(1).strip())
        items.append({"country": m.group(1).strip(), "level": int(m.group(2)), "label": m.group(3).strip(),
                      "date": (_iso(it.findtext("pubDate")) or "")[:10], "url": it.findtext("link")})
    if len(items) < 100:
        raise ValueError("only %d advisories parsed; feed format changed?" % len(items))
    p = os.path.join(CACHE, "advisory_levels.json")
    try:
        prev = json.load(open(p))
    except Exception:
        prev = {"since": now_iso(), "levels": {}, "changes": []}
    changes = prev.get("changes") or []
    for i in items:
        old = prev["levels"].get(i["country"])
        if old is not None and old != i["level"]:
            changes.append({"country": i["country"], "from": old, "to": i["level"], "seen": now_iso(), "date": i["date"]})
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    changes = [c for c in changes if c["seen"] >= cutoff]
    json.dump({"since": prev.get("since") or now_iso(), "levels": {i["country"]: i["level"] for i in items},
               "changes": changes}, open(p, "w"))
    items.sort(key=lambda i: (-i["level"], i["country"]))
    return {"count": len(items), "level4": sum(1 for i in items if i["level"] == 4),
            "level3": sum(1 for i in items if i["level"] == 3), "items": items,
            "changes": changes[::-1][:40], "watching_since": prev.get("since") or now_iso()}


# ---------------- ships (AISStream, sampled) ----------------

MAX_SHIP_POINTS = 3000  # keeps feed/ships (and its public copy) to a few hundred KB
SHIP_RANK = {"tanker": 0, "cargo": 1, "military": 2, "passenger": 3}


def _load_json(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def _dump_json(path, obj):
    with open(path + ".tmp", "w") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    os.replace(path + ".tmp", path)


def ships():
    """One AIS sample merged into the 3-hour store and the 30-day registry, then the map points, tanker cards,
    tanker tracks and listed ships for the page. Points: [lon, lat, sog, cog, class, name, mmsi, ts, dest, hdg,
    flag, marks, imo, draught, length]; marks come from the OpenSanctions vessel lists (non-commercial)."""
    from . import ais, mid
    now = dt.datetime.now(dt.timezone.utc)
    bo = ais.Backoff(os.path.join(CACHE, "ais_backoff.json"))
    bo.check(now)
    vp, rp = os.path.join(CACHE, "ais_vessels.json"), os.path.join(CACHE, "ais_registry.json")
    vessels, reg = _load_json(vp, {}), _load_json(rp, {})
    try:
        heard, st = ais.sample()
    except ais.HandshakeError as e:
        if e.code == 429:
            bo.hit(now)
        raise
    bo.clear()
    now = dt.datetime.now(dt.timezone.utc)
    ais.learn(reg, heard, now.date())
    reg = ais.prune_registry(reg, now.date())
    vessels = ais.merge(vessels, heard, now, reg)
    _dump_json(vp, vessels)
    _dump_json(rp, reg)
    return ships_view(vessels, reg, st, now, ais, mid)


def ships_view(vessels, reg, st, now, ais, mid):
    counts = ais.counts(vessels, now)
    for c in counts.values():
        c["listed"] = 0
    hour = (now - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pts, tankers, listed, tracks = [], [], [], {}
    for mmsi, v in vessels.items():
        if v.get("lat") is None or (v.get("ts") or "") < hour:
            continue
        box = ais.box_of(v["lat"], v["lon"])
        if not box:
            continue
        cls, flag = ais.ship_class(v.get("type")), mid.iso2_of(mmsi)
        hit = sanctions.lookup(imo=v.get("imo"), mmsi=mmsi)
        marks = hit["marks"] if hit else ""
        pts.append([v["lon"], v["lat"], v.get("sog"), v.get("cog"), cls, v.get("name") or "", int(mmsi), v.get("ts"),
                    v.get("dest") or "", v.get("hdg"), flag, marks, v.get("imo") or "", v.get("dr"), v.get("len")])
        card = None
        if cls == "tanker" or hit:
            hist = ((reg.get(mmsi) or {}).get("dr") or [])
            card = {"mmsi": int(mmsi), "name": v.get("name") or "", "cls": cls, "flag": flag, "imo": v.get("imo") or "",
                    "area": box, "lon": v["lon"], "lat": v["lat"], "ts": v.get("ts"), "sog": v.get("sog"), "cog": v.get("cog"),
                    "hdg": v.get("hdg"), "dest": v.get("dest") or "", "eta": v.get("eta") or "", "dr": v.get("dr"),
                    "dr_was": hist[-2] if len(hist) >= 2 else None, "len": v.get("len"), "marks": marks}
        if cls == "tanker":
            tankers.append(card)
            if len(v.get("trk") or []) >= 2:
                tracks[mmsi] = [[p[0], p[1]] for p in v["trk"]]
        if hit:
            if set(marks) & set("SG"):  # area counts: sanctioned or shadow fleet; a port-state detention alone is common
                counts[box]["listed"] += 1
            listed.append(dict(card, lists=hit.get("lists") or [], list_name=hit.get("name") or "", url=hit.get("url") or "",
                               match="IMO" if v.get("imo") and hit.get("imo") == v.get("imo") else "MMSI"))
    if len(pts) > MAX_SHIP_POINTS:  # keep listed ships, tankers and cargo first, then ships under way
        pts.sort(key=lambda p: (not p[11], SHIP_RANK.get(p[4], 9), (p[2] or 0) < 1))
        pts = pts[:MAX_SHIP_POINTS]
    order = lambda c: (min(("SGD".index(m) for m in c["marks"] if m in "SGD"), default=3), c["area"], -(c["sog"] or 0))
    tankers.sort(key=order)
    listed.sort(key=order)
    heard_1h = sum(c["ships_1h"] for c in counts.values())
    typed_1h = sum(c["typed"] for c in counts.values())
    boxes = {k: dict(label=b[0], theatre=b[1], bbox=[b[3], b[2], b[5], b[4]], no_live_coverage=k in ais.NO_COVERAGE, **counts[k])
             for k, b in ais.BOXES.items()}
    return {"count": len(pts), "sample": st, "areas": boxes, "points": pts, "tankers": tankers, "tracks": tracks,
            "listed": listed, "typed_pct": round(100.0 * typed_1h / heard_1h) if heard_1h else None,
            "registry": {"ships": len(reg), "with_type": sum(1 for e in reg.values() if e.get("t")),
                         "with_imo": sum(1 for e in reg.values() if e.get("imo")), "days": ais.REG_DAYS},
            "lists": {"attribution": sanctions.ATTRIBUTION, "attribution_url": sanctions.ATTRIBUTION_URL,
                      "licence": sanctions.LICENCE},
            "note": "Volunteer terrestrial AIS receivers: dense in Europe, absent in the Gulf and Red Sea. "
                    "No ships in an area means no coverage, not no traffic. Military ships rarely transmit. "
                    "List marks match a ship's IMO or MMSI to a public list entry; MMSIs get reused and spoofed."}


# ---------------- chokepoint traffic (Global Fishing Watch, ~4 days behind) ----------------

def gfw_traffic():
    """Daily ship counts per area and AIS-off events from GFW (gt/gfw.py). NON-COMMERCIAL licence:
    never pass this feed to the trading agent. An area that fails keeps its previous result (marked stale)."""
    from . import gfw
    p = os.path.join(CACHE, "gfw_areas.json")
    try:
        prev = json.load(open(p))
    except Exception:
        prev = {}
    today = dt.datetime.now(dt.timezone.utc).date()
    areas, errors, gap_list = {}, {}, []
    for k, (_label, kind, _theatre, _ring) in gfw.AREAS.items():
        try:
            areas[k] = dict(gfw.presence(k, today), fetched=now_iso())
        except Exception as e:
            errors[k] = "%s: %s" % (type(e).__name__, str(e)[:160])
            if k in prev:
                areas[k] = dict(prev[k], stale=True)
        if kind == "sea":
            try:
                gap_list += gfw.gaps(k, today)
            except Exception as e:
                errors["gaps:" + k] = "%s: %s" % (type(e).__name__, str(e)[:160])
    fresh = {k: v for k, v in areas.items() if not v.get("stale")}
    if not fresh:
        raise RuntimeError("GFW: every area failed: " + "; ".join("%s %s" % kv for kv in list(errors.items())[:2]))
    json.dump(dict(prev, **fresh), open(p, "w"), separators=(",", ":"))
    gap_list.sort(key=lambda g: g["start"], reverse=True)
    for k, a in areas.items():
        if a["kind"] == "sea":
            a["gaps_30d"] = sum(1 for g in gap_list if g["area"] == k)
    return {"count": len(areas), "areas": areas, "gaps": gap_list,
            "data_through": max(a["last_full_day"] for a in fresh.values()), "errors": errors,
            "attribution": gfw.ATTRIBUTION, "attribution_url": gfw.ATTRIBUTION_URL, "licence": gfw.LICENCE,
            "note": "Satellite plus terrestrial AIS via Global Fishing Watch, about 4 days behind real time. Vessels = distinct "
                    "ships seen in the area that day; for the small chokepoint boxes that is close to a daily transit count "
                    "(plus ships at anchor in the box). The newest day is usually still filling in and is left out of the "
                    "averages. Ships that switch AIS off are not counted."}


# ---------------- submarine cables (static) ----------------

def cables():
    d = get_json("https://www.submarinecablemap.com/api/v3/cable/cable-geo.json", timeout=60)
    for f in d["features"]:
        f["properties"] = {"name": f["properties"].get("name"), "color": f["properties"].get("color")}
    return {"count": len(d["features"]), "geojson": d}


REGISTRY = {
    # name: (function, refresh seconds)
    "mil": (mil_aircraft, 45),
    "front": (deepstate, 1800),
    "losses": (ru_losses, 3600),
    "firms": (firms, 3 * 3600),
    "ukmto": (ukmto, 6 * 3600),
    "gdelt": (gdelt, 900),
    "tzeva": (alerts.israel_feed, 20),       # Tzofar history + HFC messages (ETag: 304 when unchanged)
    "tzevalive": (alerts.israel_live, 5),    # Tzofar live notifications (Cloudflare-cached 5 s)
    "airalerts": (alerts.regions, 60),       # alerts.in.ua SITREP (If-Modified-Since)
    "embassy": (embassy.poll, 60),           # US embassy alert RSS: only the posts that are due (If-Modified-Since)
    "pla": (taiwan_pla, 3 * 3600),
    "czib": (easa_czib, 12 * 3600),
    "official": (official, 1800),
    "outages": (outages, 900),
    "advisories": (advisories, 6 * 3600),
    "ships": (ships, 300),
    "gfw": (gfw_traffic, 6 * 3600),
    "portwatch": (portwatch.poll, 6 * 3600),  # IMF PortWatch chokepoint transits, ~3 days behind (non-commercial)
    "vessellists": (sanctions.poll, 86400),    # OpenSanctions maritime lists; CSV only when the version changes
    "cables": (cables, 7 * 86400),
}
