"""Google My Maps ingest: fetch KML -> normalised GeoJSON events + overlays, archive, diff.

The map ID lives in config/mymaps.local.json and is never printed.
Run:  python3 -m gt.mymaps            (fetch, archive, write data/latest.geojson + data/stats.json)
      python3 -m gt.mymaps --file x.kml (parse a local KML instead of fetching)
"""
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import statistics
import sys
import urllib.request
import xml.etree.ElementTree as ET

from . import geo, mapfollow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
NS = {"k": "http://www.opengis.net/kml/2.2"}
UA = "GroundTruth/0.2 (personal OSINT dashboard)"
TWITTER_EPOCH_MS = 1288834974657

# My Maps icon code -> (category, label, glyph). 1.6.0: every code is named after the map's own icon file
# (icons/onion/<code>-<name>_4x.png on the map page, read 2026-11-24): 1830-mormon (a trumpeter), 1571-fire,
# 1504-airport-plane, 1657-police-officer, 1722-truck, 1812-hunting (a rifleman firing), 1569-ferry,
# 1864-shipwreck, 1556-death-skull, 1528-bridge, 1593-helicopter, 1716-train, 1660-power-lightning.
# The glyph is the page's drawing of that icon (web/app.js GLYPHS). Before 1.6.0, 1569 and 1528 read "Other".
ICONS = {
    "1830": ("report", "News / statement", "megaphone"), "1571": ("strike", "Strike / fire", "fire"),
    "1504": ("drone", "Aircraft / drone", "plane"), "1812": ("missile", "Firing / air defence", "gunner"),
    "1864": ("maritime", "Ship hit / wreck", "wreck"), "1569": ("maritime", "Ship / naval movement", "ship"),
    "1593": ("aviation", "Helicopter", "helicopter"), "1556": ("casualty", "Casualties", "skull"),
    "1657": ("forces", "Personnel / forces", "officer"), "1722": ("forces", "Vehicles / equipment", "truck"),
    "1660": ("energy", "Power / infrastructure", "bolt"), "1528": ("energy", "Bridge", "bridge"),
    "1716": ("energy", "Rail", "train"),
}

CATEGORIES = {
    "maritime": "Maritime", "energy": "Energy / infrastructure", "missile": "Missile / air defence",
    "drone": "Drone", "strike": "Strike / explosion", "alert": "Alert / force posture",
    "cyber": "Comms / outage", "security": "Security incident", "casualty": "Casualties",
    "forces": "Forces / equipment", "aviation": "Aviation", "political": "Political / statement",
    "report": "Report", "other": "Other",
}

# Ordered: first match becomes the primary category; all matches become tags.
RULES = [
    ("maritime", r"\b(ships?|tankers?|vessels?|port|lng|naval|navy|carriers?|mines?|minefield|hormuz|strait|sulina|grounding|anti-ship|frigate|boats?|shipping)\b"),
    ("energy", r"\b(refiner(y|ies)|pipeline|power ?plant|powerplant|pumping|fuel|oil|gas|tpp|substation|depot|aluminum|energy|grid|plant)\b"),
    ("missile", r"\b(missiles?|ballistic|tels?|sams?|air defen[cs]es?|shorad|intercept(ed|ions?)?|shot down|launch(es|ed)?|iskander|kinzhal|patriot|interceptions)\b"),
    ("drone", r"\b(drones?|uavs?|ugvs?|shahed|geran|lucas)\b"),
    ("security", r"\b(bomb threat|bomb found|was a bomb|threats?|credible|car bomb(ing)?|assassinations?)\b"),
    ("strike", r"\b(strikes?|struck|hit|explosions?|bomb(ed|s|ing)?|burn(s|ing)?|fires?|attacks?|attacked|smoke|destroyed|tatters|airstrikes?)\b"),
    ("alert", r"\b(sirens?|alerts?|air raid|shelters?|lockdown|force protection|fpcon|evac(uation)?|dispersing|warns?)\b"),
    ("cyber", r"\b(outages?|ground stop|connection|connectivity|starlink|frequency|interference|jamming|cyber|internet|disruptions?)\b"),
    ("casualty", r"\b(killed|dead|losses|casualt(y|ies)|died|surrender)\b"),
    ("forces", r"\b(soldiers?|troops|forces|patrol|column|spgs?|withdraw|exercises?|pla|balloons?|deploy(ed)?|positions?|helicopters?)\b"),
    ("political", r"\b(talks|claims?|statement|says|demands?|president|minister|pm|netanyahu|waiver|regime|unlawful|support|meeting|neutral|liar|delusional|concerned|schedule|vp|mossad|isw|assess(ment|ent)|pushes back|fact check)\b"),
]

OVERLAY_RULES = [
    ("frontline", r"front|rebel controlled|partisan"),
    ("border", r"border|nato"),
    ("lane", r"lane|route|shipping"),
    ("zone", r"minefield|blockade|perimeter|defen[cs]e chain|occupation|left\b"),
    ("damage", r"destroyed|damaged|knocked out|operational|attack|hit|powerplant"),
    ("bridge", r"bridge"),
    ("river", r"reka|river"),
    ("airbase", r"saky|simferopol|simeropol|dzankhoi|dzhankoi|air(port|field|base)"),
]


def load_config():
    """The map ID is private: GT_MYMAPS_MID (container) or config/mymaps.local.json (local)."""
    mid = (os.environ.get("GT_MYMAPS_MID") or "").strip()
    if mid:
        return {"name": os.environ.get("GT_MYMAPS_NAME") or "Global War News Map", "mid": mid}
    with open(os.path.join(ROOT, "config", "mymaps.local.json"), encoding="utf-8") as fh:
        return json.load(fh)["maps"][0]


def fetch_kml(mid, timeout=60):
    url = "https://www.google.com/maps/d/kml?mid=%s&forcekml=1" % mid
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def snowflake_ms(post_id):
    return (int(post_id) >> 22) + TWITTER_EPOCH_MS


def parse_source(desc):
    """Pull the first URL out of a description and identify platform / handle / post id."""
    m = re.search(r"https?://[^\s<\"']+", desc or "")
    if not m:
        return {}
    url = m.group(0).split("?")[0]
    out = {"url": url, "platform": "web", "handle": None, "post_id": None}
    x = re.match(r"https?://(?:www\.)?(?:x|twitter)\.com/([^/]+)/status/(\d+)", url)
    if x:
        out.update(platform="x", handle=x.group(1), post_id=x.group(2))
        return out
    rd = re.match(r"https?://(?:www\.)?reddit\.com/r/([^/]+)/", url)
    if rd:
        out.update(platform="reddit", handle="r/" + rd.group(1))
        return out
    tg = re.match(r"https?://t\.me/([^/]+)/(\d+)", url)
    if tg:
        out.update(platform="telegram", handle=tg.group(1), post_id=tg.group(2))
    return out


def classify(title, icon_cat):
    t = (title or "").lower()
    tags = [cat for cat, rx in RULES if re.search(rx, t)]
    primary = tags[0] if tags else (icon_cat or "other")
    if icon_cat and icon_cat not in tags:
        tags.append(icon_cat)
    return primary, tags


def overlay_type(name):
    n = (name or "").lower()
    for t, rx in OVERLAY_RULES:
        if re.search(rx, n):
            return t
    return "other"


# 1.6.0: battle fronts. The map's own legend: "Red Lines represent frontlines, Yellow represents supposed front
# lines. The Blue line represents shared NATO/RU Borders." So a front is a red or yellow LINE, never a polygon
# and never a line the name marks as something else (a bridge span's damage state, a river, a border).
FRONT_RED, FRONT_YELLOW = "#A52714", "#FFD600"
FRONT_KINDS = [
    ("blockade", r"blockade"),
    ("defense", r"defen[cs]e (chain|line)|perimeter"),
    ("contact", r"front"),
]


def front_kind(name, stroke, otype, npoints):
    """contact / blockade / defense / supposed for a line overlay that is a front by the map's legend, else None."""
    col = (stroke or "").upper()
    if col not in (FRONT_RED, FRONT_YELLOW) or otype in ("damage", "bridge", "river", "border", "lane", "airbase"):
        return None
    if col == FRONT_YELLOW:
        return "supposed"
    n = (name or "").lower()
    for kind, rx in FRONT_KINDS:
        if re.search(rx, n):
            return kind
    return "contact" if npoints >= 3 else None  # an unnamed red line; a 2-point red stub is a marker, not a front


def _style_parts(style):
    s = (style or "").lstrip("#")
    parts = s.split("-")
    info = {"style": s}
    if s.startswith("icon-") and len(parts) >= 3:
        info.update(icon=parts[1], batch=parts[2])
    elif s.startswith("line-") and len(parts) >= 3:
        info.update(stroke="#" + parts[1], stroke_width=round(int(parts[2]) / 1000, 2))
    elif s.startswith("poly-") and len(parts) >= 4:
        info.update(stroke="#" + parts[1], stroke_width=round(int(parts[2]) / 1000, 2),
                    fill_opacity=round(int(parts[3]) / 255, 2))
    return info


def _coords(el):
    return [[float(v) for v in c.split(",")[:2]] for c in el.text.split()]


def parse(kml_bytes):
    root = ET.fromstring(kml_bytes)
    doc = root.find("k:Document", NS)
    title = doc.findtext("k:name", default="", namespaces=NS)
    m = re.search(r"Day\s+(\d+)", title)
    map_day = int(m.group(1)) if m else None
    feats = []
    for pm in doc.iter("{%s}Placemark" % NS["k"]):
        name = (pm.findtext("k:name", default="", namespaces=NS) or "").strip()
        desc = pm.findtext("k:description", default="", namespaces=NS) or ""
        st = _style_parts(pm.findtext("k:styleUrl", default="", namespaces=NS))
        pt = pm.find(".//k:Point/k:coordinates", NS)
        ls = pm.find(".//k:LineString/k:coordinates", NS)
        pg = pm.find(".//k:Polygon/k:outerBoundaryIs/k:LinearRing/k:coordinates", NS)
        if pt is not None:
            c = _coords(pt)[0]
            geom = {"type": "Point", "coordinates": c}
            anchor = c
        elif ls is not None:
            cs = _coords(ls)
            geom = {"type": "LineString", "coordinates": cs}
            anchor = cs[len(cs) // 2]
        elif pg is not None:
            cs = _coords(pg)
            geom = {"type": "Polygon", "coordinates": [cs]}
            anchor = [sum(p[0] for p in cs) / len(cs), sum(p[1] for p in cs) / len(cs)]
        else:
            continue
        src = parse_source(desc)
        loc = geo.locate(anchor[0], anchor[1])
        props = {"title": name, "map_day": map_day, **loc, **{k: v for k, v in st.items() if k != "style"}}
        if geom["type"] == "Point" and src.get("url"):
            icon_cat, icon_label, glyph = ICONS.get(st.get("icon"), ("other", "Other", ""))
            cat, tags = classify(name, icon_cat)
            props.update(kind="event", category=cat, tags=tags, icon_label=icon_label, glyph=glyph, **src)
            if src.get("platform") == "x":
                ms = snowflake_ms(src["post_id"])
                props.update(ts_ms=ms, ts_source="x-snowflake")
            key = src["url"]
        else:
            props.update(kind="overlay", overlay_type=overlay_type(name), note=re.sub(r"<[^>]+>", " ", desc).strip()[:300] or None)
            if geom["type"] == "LineString":
                fk = front_kind(name, st.get("stroke"), props["overlay_type"], len(geom["coordinates"]))
                if fk:
                    props["front_kind"] = fk
            key = "%s|%s|%s" % (name, geom["type"], json.dumps(geom["coordinates"])[:200])
        props["id"] = hashlib.sha1(key.encode()).hexdigest()[:16]
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    _estimate_missing_times(feats)
    for f in feats:
        ms = f["properties"].get("ts_ms")
        if ms:
            f["properties"]["ts"] = dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"type": "FeatureCollection", "title": title, "map_day": map_day, "features": feats}


def _estimate_missing_times(feats):
    """Undated pins (Reddit share links) get the median time of their colour batch, flagged as estimates."""
    by_batch = {}
    for f in feats:
        p = f["properties"]
        if p.get("ts_ms"):
            by_batch.setdefault(p.get("batch"), []).append(p["ts_ms"])
    for f in feats:
        p = f["properties"]
        if p.get("kind") == "event" and not p.get("ts_ms") and by_batch.get(p.get("batch")):
            p.update(ts_ms=int(statistics.median(by_batch[p["batch"]])), ts_source="batch-estimate")


def stats(fc, now_ms=None):
    ev = [f["properties"] for f in fc["features"] if f["properties"]["kind"] == "event"]
    ov = [f["properties"] for f in fc["features"] if f["properties"]["kind"] == "overlay"]
    now_ms = now_ms or max((e.get("ts_ms") or 0) for e in ev) if ev else 0

    def count(key, items):
        out = {}
        for i in items:
            out[i.get(key) or "unknown"] = out.get(i.get(key) or "unknown", 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    dated = sorted(e["ts_ms"] for e in ev if e.get("ts_ms"))
    hours = {}
    for e in ev:
        if e.get("ts_ms"):
            h = dt.datetime.fromtimestamp(e["ts_ms"] / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:00Z")
            hours.setdefault(h, {}).setdefault(e["theatre"], 0)
            hours[h][e["theatre"]] += 1
    return {
        "title": fc["title"], "map_day": fc["map_day"],
        "events": len(ev), "overlays": len(ov),
        "window": {"first": dated[0] if dated else None, "last": dated[-1] if dated else None},
        "by_theatre": count("theatre", ev), "by_category": count("category", ev),
        "by_platform": count("platform", ev), "by_country": count("country_name", ev),
        "top_sources": dict(list(count("handle", ev).items())[:15]),
        "overlay_types": count("overlay_type", ov),
        "by_hour": dict(sorted(hours.items())),
        "ts_quality": count("ts_source", ev),
    }


# ---------- archive ----------

def _db():
    os.makedirs(DATA, exist_ok=True)
    con = sqlite3.connect(os.path.join(DATA, "groundtruth.sqlite"))
    con.execute("""create table if not exists events(
        id text primary key, first_seen text, last_seen text, map_day int, kind text, title text,
        category text, theatre text, country text, sea text, platform text, handle text, url text,
        ts_ms int, ts_source text, geometry text, props text)""")
    con.execute("""create table if not exists snapshots(
        fetched_at text, map_day int, sha256 text, features int, path text)""")
    return con


def archive(kml_bytes, fc):
    """Save the raw KML when it changed and upsert every feature. Returns (changed, new_ids)."""
    sha = hashlib.sha256(kml_bytes).hexdigest()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = _db()
    last = con.execute("select sha256 from snapshots order by fetched_at desc limit 1").fetchone()
    changed = not last or last[0] != sha
    if changed:
        snapdir = os.path.join(DATA, "snapshots")
        os.makedirs(snapdir, exist_ok=True)
        path = os.path.join(snapdir, "%s_day%s_%s.kml" % (now.replace(":", ""), fc["map_day"], sha[:8]))
        with open(path, "wb") as fh:
            fh.write(kml_bytes)
        con.execute("insert into snapshots values(?,?,?,?,?)", (now, fc["map_day"], sha, len(fc["features"]), os.path.relpath(path, ROOT)))
    new_ids = []
    for f in fc["features"]:
        p = f["properties"]
        row = con.execute("select id from events where id=?", (p["id"],)).fetchone()
        if row:
            con.execute("update events set last_seen=?, map_day=? where id=?", (now, p["map_day"], p["id"]))
        else:
            new_ids.append(p["id"])
            con.execute("insert into events values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                p["id"], now, now, p["map_day"], p["kind"], p["title"], p.get("category"), p["theatre"],
                p.get("country"), p.get("sea"), p.get("platform"), p.get("handle"), p.get("url"),
                p.get("ts_ms"), p.get("ts_source"), json.dumps(f["geometry"]), json.dumps(p)))
    con.commit()
    total = con.execute("select count(*) from events").fetchone()[0]
    snaps = con.execute("select count(*) from snapshots").fetchone()[0]
    con.close()
    return {"changed": changed, "sha256": sha[:12], "new": len(new_ids), "archived_total": total, "snapshots": snaps}


def run(kml_path=None):
    if kml_path:
        with open(kml_path, "rb") as fh:
            raw = fh.read()
        fc, follow = parse(raw), None
    else:
        # 0.10.0: the curator rolls to a new map about weekly; mapfollow picks the newest one the publisher links
        # and keeps the previous map in the mix for a while. Only the current map's KML is snapshotted.
        maps, follow = mapfollow.resolve(load_config()["mid"], fetch_kml, parse)
        raw, fc = maps[0][1], mapfollow.merge(maps)
    st = stats(fc)
    st["archive"] = archive(raw, fc)
    if follow:
        st["follow"] = follow
    st["fetched_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "latest.geojson"), "w", encoding="utf-8") as fh:
        json.dump(fc, fh, separators=(",", ":"))
    with open(os.path.join(DATA, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    return fc, st


if __name__ == "__main__":
    path = sys.argv[sys.argv.index("--file") + 1] if "--file" in sys.argv else None
    _, s = run(path)
    print(json.dumps({k: s[k] for k in ("title", "events", "overlays", "by_theatre", "by_category", "ts_quality", "archive")}, indent=1))
