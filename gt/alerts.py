"""Live regional air-raid and missile alerts. v1.0 (Ground Truth 0.7.0), 2026-11-18.

Every source is free and keyless (no paid API, no xAI/Grok):

* Israel: Tzeva Adom (Tzofar), a public mirror of Home Front Command (Pikud HaOref) alerts. oref.org.il refuses
  clients outside Israel. `/notifications` is polled every 5 s (Tzofar's own web page polls it every 3 s as the
  backup to its websocket), `/ios/feed` every 20 s for the alert history and the HFC messages (early warnings,
  "incident ended"). Both sit behind a 5 s Cloudflare cache; the feed is fetched with its ETag, so an unchanged
  feed costs a 304. City names, positions and alert polygons come from Tzofar's static lists, re-fetched only when
  their version changes.
* Ukraine, Russian regions and Poland: alerts.in.ua's public SITREP (`api.alerts.in.ua/v3/alerts/active.md`), which
  their llms.txt offers for automated reading without a token. Fetched every 60 s with If-Modified-Since (304 when
  unchanged). It names every region under an air-raid warning with its level (red = missiles / mass strike,
  yellow = drones), the threats the Ukrainian Air Force is tracking, explosions, and Polish RCB air-threat notices.
  Ukrainian oblast states from ubilling.net.ua (Vadym Klymenko's API) are the fallback if the SITREP fails.

Requests are plain: an honest User-Agent and no borrowed Origin/Referer headers.
"""
import datetime as dt
import difflib
import gzip
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")
REGIONS_FILE = os.path.join(ROOT, "web", "geo", "alert-regions.json")
UA = "Mozilla/5.0 (GroundTruth/0.7 personal OSINT dashboard)"
TZ_API = "https://api.tzevaadom.co.il"
TZ_STATIC = "https://www.tzevaadom.co.il/static/"
SITREP = "https://api.alerts.in.ua/v3/alerts/active.md"
UBILLING = "https://ubilling.net.ua/aerialalerts/"

# Tzofar's threat codes (their app.js THREATS_TITLES), short English labels.
THREATS = {0: "Rockets / missiles", 1: "Hazardous materials", 2: "Terrorist infiltration", 3: "Earthquake",
           4: "Tsunami", 5: "Hostile aircraft (UAV)", 6: "Radiological", 7: "Non-conventional missile",
           8: "General alert", 9: "HFC drill"}
INSTRUCTION = {0: "early warning", 1: "incident ended", 2: "HFC message"}
VIRTUAL = {"בחלק מהאזורים בארץ": "Parts of the country"}  # nationwide placeholders (earthquakes), not on the map
os.makedirs(CACHE, exist_ok=True)
_LOCK = threading.Lock()


# ---------------- HTTP: gzip + conditional requests ----------------

_VALIDATORS = {}  # url -> {"etag", "last_modified", "body"}


def fetch(url, timeout=20, conditional=False):
    """GET with gzip. With conditional=True, sends the last ETag / Last-Modified and returns the cached body on 304."""
    h = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    v = _VALIDATORS.get(url) if conditional else None
    if v:
        if v.get("etag"):
            h["If-None-Match"] = v["etag"]
        if v.get("last_modified"):
            h["If-Modified-Since"] = v["last_modified"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            body = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
            if conditional:
                _VALIDATORS[url] = {"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"), "body": body}
            return body
    except urllib.error.HTTPError as e:
        if e.code == 304 and v:
            return v["body"]
        raise


def fetch_json(url, **kw):
    return json.loads(fetch(url, **kw).decode("utf-8"))


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def _load(name, default):
    try:
        with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(name, obj):
    p = os.path.join(CACHE, name)
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(p + ".tmp", p)


# ---------------- Israel: Tzofar city lists ----------------

_LISTS = {"cities": None, "polygons": None, "loaded": False}
_EMPTY_CITIES = {"cities": {}, "areas": {}}


def _list_from(kind, raw, v):
    if kind == "cities":
        return {"version": v if v is not None else raw.get("@VERSION"), "cities": raw.get("cities") or {},
                "areas": raw.get("areas") or {}}
    polys = {}  # {"<city id>": [[lat, lng], ...]} -> [[lon, lat], ...] at 4 decimals, closed
    for k, pts in raw.items():
        if not k.isdigit() or not isinstance(pts, list):
            continue
        ring = []
        for p in pts:
            if isinstance(p, list) and len(p) >= 2:
                q = [round(float(p[1]), 4), round(float(p[0]), 4)]
                if not ring or ring[-1] != q:
                    ring.append(q)
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            polys[k] = ring
    return {"version": v, "polygons": polys}


def tz_lists(want=None, download=True):
    """{"by_name", "by_id", "areas", "polygons", "versions"}. With download=True (the feed thread only), fetches a list
    that is missing or older than the version `want` names; page requests never wait on a download."""
    with _LOCK:
        if not _LISTS["loaded"]:
            _LISTS.update(cities=_load("tz_cities.json", None), polygons=_load("tz_polygons.json", None), loaded=True)
    want, now = want or {}, time.time()
    for kind, fname in (("cities", "tz_cities.json"), ("polygons", "tz_polygons.json")):
        have = _LISTS[kind]
        stale = have is None or (want.get(kind) is not None and str(have.get("version")) != str(want.get(kind)))
        if download and stale and now - _LISTS.get("tried_" + kind, 0) > 600:  # a failed download waits 10 min
            _LISTS["tried_" + kind] = now
            v = want.get(kind)
            data = _list_from(kind, fetch_json(TZ_STATIC + "%s.json%s" % (kind, "?v=%s" % v if v is not None else ""), timeout=60), v)
            _save(fname, data)
            with _LOCK:
                _LISTS[kind] = data
    with _LOCK:
        c = _LISTS["cities"] or _EMPTY_CITIES
        if _LISTS.get("_indexed") is not c:
            by_name = {}
            for he, x in (c.get("cities") or {}).items():
                by_name[he] = x
                if x.get("he"):
                    by_name[x["he"]] = x
            _LISTS["by_name"] = by_name
            _LISTS["by_id"] = {str(x.get("id")): x for x in (c.get("cities") or {}).values()}
            _LISTS["_indexed"] = c
        return {"by_name": _LISTS["by_name"], "by_id": _LISTS["by_id"], "areas": c.get("areas") or {},
                "polygons": (_LISTS["polygons"] or {}).get("polygons") or {},
                "versions": {"cities": c.get("version"), "polygons": (_LISTS["polygons"] or {}).get("version")}}


# ---------------- Israel: feeds ----------------

_LIVE = {"items": None}  # notificationId -> alert, kept 26 h, persisted in cache/tz_live.json


def israel_live():
    """Feed `tzevalive` (5 s): alerts as they fire. Returns the alerts of the last 30 minutes."""
    raw = fetch_json(TZ_API + "/notifications", timeout=10)
    now = time.time()
    with _LOCK:
        if _LIVE["items"] is None:
            _LIVE["items"] = _load("tz_live.json", {})
        items, changed = _LIVE["items"], False
        for a in raw if isinstance(raw, list) else []:
            if not isinstance(a, dict) or not a.get("cities"):
                continue
            nid = str(a.get("notificationId") or "%s-%s-%s" % (a.get("time"), a.get("threat"), "|".join(a["cities"])[:80]))
            if nid in items:
                continue
            items[nid] = {"time": int(a.get("time") or now), "threat": a.get("threat", 8), "isDrill": bool(a.get("isDrill")),
                          "cities": [c for c in a["cities"] if isinstance(c, str)], "seen": int(now)}
            changed = True
        for k in [k for k, v in items.items() if now - v["time"] > 26 * 3600]:
            del items[k]
            changed = True
        if changed:
            _save("tz_live.json", items)
        recent = sorted((v for v in items.values() if now - v["time"] <= 1800), key=lambda v: -v["time"])
    return {"active_now": sum(len(v["cities"]) for v in recent if not v["isDrill"] and now - v["time"] <= 180),
            "stored": len(items), "recent": recent[:50]}


def israel_feed():
    """Feed `tzeva` (20 s): Tzofar's history and Home Front Command messages, last 24 h, names in English."""
    d = fetch_json(TZ_API + "/ios/feed", timeout=20, conditional=True)
    lists = tz_lists({"cities": d.get("citiesVersion"), "polygons": d.get("polygonsVersion")})
    return parse_tz_feed(d, lists)


def parse_tz_feed(d, lists, now=None):
    now = now or time.time()
    hist, c24 = [], 0
    for g in d.get("alertsHistory") or []:
        for a in g.get("alerts") or []:
            t = int(a.get("time") or 0)
            if not _in_day(t, now):
                continue
            hist.append({"time": t, "threat": a.get("threat", 8), "isDrill": bool(a.get("isDrill")),
                         "cities": [c for c in a.get("cities") or [] if isinstance(c, str)]})
            if not a.get("isDrill"):
                c24 += len(a.get("cities") or [])
    msgs = []
    for i in d.get("instructions") or []:
        t = int(i.get("time") or 0)
        if not _in_day(t, now):
            continue
        msgs.append({"time": t, "type": i.get("instructionType"), "kind": INSTRUCTION.get(i.get("instructionType"), "message"),
                     "title": i.get("titleEn") or i.get("titleHe"), "body": (i.get("bodyEn") or i.get("bodyHe") or "").replace("*", ""),
                     "city_ids": [str(x) for x in i.get("citiesIds") or []], "area_ids": [str(x) for x in i.get("areasIds") or []]})
    hist.sort(key=lambda a: -a["time"])
    msgs.sort(key=lambda m: -m["time"])
    last = next((a["time"] for a in hist if not a["isDrill"]), None)
    recent = [{"time": a["time"], "threat": THREATS.get(a["threat"], "code %s" % a["threat"]), "n": len(a["cities"]),
               "cities": [(lists["by_name"].get(c) or {}).get("en") or c for c in a["cities"][:12]]}
              for a in hist if not a["isDrill"]][:25]
    # active_now / cities_alerted_24h / last_alert / recent keep the 0.6 summary keys working
    return {"last_alert": _iso(last), "active_now": 0, "cities_alerted_24h": c24, "recent": recent,
            "history": hist, "messages": msgs[:40], "lists": lists["versions"]}


def _in_day(t, now):
    return -300 <= now - t <= 86400  # the last 24 h; a stamp more than 5 min in the future is clock trouble, not news


def _extra_s(threat):
    return 60 if threat == 0 else 120  # Tzofar shows an alert for its countdown plus 60 s (rockets) / 120 s (others)


def israel_view(live, feed, now=None, lists=None):
    """Merge live notifications with the history: per city, its latest alert in 24 h, plus events and messages.

    The page works out siren / shelter / early-warning / recent from these timestamps itself, so a copy that is
    minutes old (the public mirror) shows an old siren as recent, not as live."""
    lists = lists or tz_lists(download=False)
    now = now or time.time()
    alerts = list((feed or {}).get("history") or []) + list((live or {}).get("recent") or [])
    seen, merged = set(), []
    for a in sorted(alerts, key=lambda a: a["time"]):
        if a.get("isDrill") or not _in_day(a["time"], now):
            continue
        for c in a["cities"]:
            key = (c, a["threat"], a["time"] // 120)  # the same alert reported by both feeds a few seconds apart
            if key in seen or (c, a["threat"], a["time"] // 120 - 1) in seen:
                continue
            seen.add(key)
            merged.append((a["time"], a["threat"], c))
    msgs = (feed or {}).get("messages") or []
    ended = {}
    for m in msgs:
        if m["type"] == 1:
            for cid in m["city_ids"]:
                ended[cid] = max(ended.get(cid, 0), m["time"])
    cities, unknown = {}, set()
    for t, th, name in merged:
        x = lists["by_name"].get(name)
        if not x or x.get("lat") is None:
            if name not in VIRTUAL:
                unknown.add(name)
            continue
        cid = str(x.get("id"))
        cities[cid] = {"id": cid, "n": x.get("en") or name, "he": x.get("he") or name,
                       "a": ((lists["areas"].get(str(x.get("area"))) or {}).get("en")), "lon": x["lng"], "lat": x["lat"],
                       "cd": x.get("countdown") or 0, "t": t, "th": th, "label": THREATS.get(th, "code %s" % th),
                       "x": _extra_s(th)}
    for cid, c in cities.items():
        e = ended.get(cid)
        c["ended"] = e if e and e >= c["t"] else None
        if now - c["t"] <= 1800 and cid in lists["polygons"]:
            c["poly"] = lists["polygons"][cid]
    # early warnings: the cities they name, so the page can tint them until an alert or "ended" follows
    early = []
    for m in msgs:
        if m["type"] == 0 and now - m["time"] <= 1800:
            pts = []
            for cid in m["city_ids"][:400]:
                x = lists["by_id"].get(cid)
                if x and x.get("lat") is not None:
                    pts.append({"id": cid, "n": x.get("en"), "lon": x["lng"], "lat": x["lat"],
                                "ended": ended[cid] if ended.get(cid, 0) >= m["time"] else None,  # all-clear after it
                                "poly": lists["polygons"].get(cid) if len(m["city_ids"]) <= 400 else None})
            early.append({"t": m["time"], "title": m["title"], "body": m["body"], "cities": pts,
                          "areas": [(lists["areas"].get(a) or {}).get("en") for a in m["area_ids"]]})
    # events: consecutive alerts of one threat type, grouped while gaps stay under 3 min
    events, cur = [], None
    for t, th, name in merged:
        x = lists["by_name"].get(name) or {}
        if cur and cur["th"] == th and t - cur["t_end"] <= 180:
            cur["t_end"] = t
        else:
            cur = {"t": t, "t_end": t, "th": th, "label": THREATS.get(th, "code %s" % th), "names": [], "areas": [], "pts": []}
            events.append(cur)
        nm = x.get("en") or VIRTUAL.get(name) or name
        if nm not in cur["names"]:
            cur["names"].append(nm)
        ar = (lists["areas"].get(str(x.get("area"))) or {}).get("en")
        if ar and ar not in cur["areas"]:
            cur["areas"].append(ar)
        if x.get("lat") is not None:
            cur["pts"].append((x["lng"], x["lat"]))
    out_ev = []
    for e in reversed(events[-60:]):
        pts = e.pop("pts")
        e["n"] = len(e["names"])
        e["names"] = e["names"][:30]
        e["c"] = [round(sum(p[0] for p in pts) / len(pts), 4), round(sum(p[1] for p in pts) / len(pts), 4)] if pts else None
        out_ev.append(e)
    counts = {}
    for t, th, name in merged:
        if now - t <= 86400:
            lbl = THREATS.get(th, "code %s" % th)
            counts[lbl] = counts.get(lbl, 0) + 1
    last = max((t for t, _, _ in merged), default=None)
    msgs = [m for m in msgs if _in_day(m["time"], now)]
    return {"cities": sorted(cities.values(), key=lambda c: -c["t"]), "early": early, "events": out_ev,
            "messages": [{k: m[k] for k in ("time", "kind", "title", "body")} for m in msgs[:20]],
            "counts_24h": counts, "last_alert": _iso(last), "unknown_names": sorted(unknown)[:20]}


# ---------------- Ukraine / Russia / Poland: region lookup ----------------

_REG = {}


def _norm(s):
    s = (s or "").lower().replace("ʼ", "'").replace("’", "'").replace("`", "'")
    s = re.sub(r"\b(м|смт|с)\.\s*", "", s)
    s = re.sub(r"(автономна|автономний|республіка|область|обл\.|край|округ|воєводство|województwo|oblast|krai|respublika|voivodeship)", " ", s)
    s = re.sub(r"[^\w' -]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -")


ALIASES = {  # alerts.in.ua spellings that differ from Natural Earth's Ukrainian names
    "оренбургська": "RU-ORE", "улянівська": "RU-ULY", "саратівська": "RU-SAR", "київ": "UA-30", "москва": "RU-MOW",
    "північна осетія алания": "RU-SE", "північна осетія - аланія": "RU-SE", "кабардино-балкарська": "RU-KB",
    "карачаєво-черкеська": "RU-KC", "чеченська": "RU-CE", "інгушетія": "RU-IN", "калмикія": "RU-KL",
    "севастополь": "UA-40", "крим": "UA-43", "ханти-мансійський - югра": "RU-KHM",
}


def regions_index():
    if not _REG:
        d = json.load(open(REGIONS_FILE, encoding="utf-8"))
        idx, meta = {}, {}
        for f in d["features"]:
            p = f["properties"]
            meta[p["id"]] = {"id": p["id"], "c": p["c"], "en": p["en"], "uk": p["uk"]}
            for nm in (p.get("uk"), p.get("pl"), p.get("en")):
                k = _norm(nm)
                if k and k not in idx:
                    idx[k] = p["id"]
        for k, v in ALIASES.items():
            idx.setdefault(_norm(k), v)
        _REG.update(idx=idx, meta=meta)
    return _REG


def region_for(name):
    """'Smolenska oblast (Смоленська область)' / 'Вінницька область' / 'województwo lubelskie' -> region meta or None."""
    r = regions_index()
    cands = re.findall(r"\(([^()]+)\)", name or "") + [re.sub(r"\s*\([^()]*\)", "", name or "")]
    for c in cands:
        k = _norm(c)
        if k in r["idx"]:
            return r["meta"][r["idx"][k]]
    for c in cands:  # spelling drift: a close Ukrainian / Polish match, never a loose one
        m = difflib.get_close_matches(_norm(c), list(r["idx"]), n=1, cutoff=0.86)
        if m:
            return r["meta"][r["idx"][m[0]]]
    return None


# ---------------- alerts.in.ua SITREP parser ----------------

MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _clean(s):
    return re.sub(r"\s+", " ", _LINK.sub(r"\1", s).replace("**", "")).strip()


def _sections(md):
    out, cur = {}, None
    for line in md.splitlines():
        m = re.match(r"^##\s+(\d+)\.\s+(.+?)\s*$", line)
        if m:
            cur = int(m.group(1))
            out[cur] = {"title": m.group(2), "lines": []}
        elif cur is not None:
            out[cur]["lines"].append(line)
    return out


def _local_clock(md):
    """(local datetime with tzinfo) from the LOCAL TIME line, e.g. '(Europe/Kyiv, 2026-11-19T05:07:26+02:00)'."""
    m = re.search(r"LOCAL TIME.*?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})", md)
    return dt.datetime.fromisoformat(m.group(1)) if m else None


def _when(s, ref):
    """'Nov 18, 19:58' or '05:06' (Kyiv local, the report's day) -> ISO UTC."""
    if not ref or not s:
        return None
    m = re.match(r"^\s*(?:([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?,\s*)?(\d{1,2}):(\d{2})\s*$", s)
    if not m:
        return None
    mon, day, year, hh, mm = m.groups()
    if mon:
        y = int(year) if year else ref.year - (1 if MONTHS.get(mon, 1) > ref.month else 0)
        d = dt.datetime(y, MONTHS.get(mon, ref.month), int(day), int(hh), int(mm), tzinfo=ref.tzinfo)
    else:
        d = ref.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if d > ref + dt.timedelta(minutes=5):  # a time "later" than the report is yesterday's
            d -= dt.timedelta(days=1)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_ENTRY = re.compile(r"([^,()]+?\s*\(([^()]+)\))\s*\((\d+) areas?\)")


def parse_sitrep(md):
    ref = _local_clock(md)
    if ref is None or "CURRENT WARNING STATUS" not in md:
        raise ValueError("SITREP layout changed (no LOCAL TIME line or warning section)")
    sec = _sections(md)
    head = {}
    for k in ("DTG", "WARNING STATE"):
        m = re.search(r"^%s\s+(.+)$" % k, md, re.M)
        head[k] = m.group(1).strip() if m else None
    regions, unmatched = [], []

    def add(name, kind, **kw):
        r = region_for(name)
        if not r:
            unmatched.append(_clean(name))
            return
        prev = next((x for x in regions if x["id"] == r["id"]), None)
        if prev:  # one region can show twice (e.g. an alert plus launch-site activity)
            if kind == "alert" and prev["kind"] != "alert":
                prev.update(kind="alert", **kw)
            elif kind != prev["kind"]:
                prev.setdefault("also", []).append(kind)
            return
        regions.append(dict(r, name=_clean(re.sub(r"\s*\([^()]*\)\s*$", "", name)) or r["en"], kind=kind, **kw))

    for line in (sec.get(3) or {}).get("lines", []):
        m = re.match(r"^\*\*(.+?)\*\*\s+—\s+(.+)$", line.strip())
        if not m:
            continue
        title, rest = m.group(1).strip(), m.group(2).strip()
        tl = title.lower()
        if tl.startswith("nominal alerts") or tl.startswith("cross-border launch") or (region_for(title) is None and _ENTRY.search(rest)):
            kind = "nominal" if tl.startswith("nominal") else "launch" if "launch" in tl else "alert"
            lead = re.split(r"\)\.\s", rest)[0] + ")"  # the list ends at the first ")." ("m. Kyiv" has a ". " inside)
            for e in _ENTRY.finditer(lead):
                add(e.group(1).strip(" ,and"), kind, n_areas=int(e.group(3)),
                    **({"level": "yellow", "types": ["air-attack threat (RCB)"]} if kind == "alert" else {}))
            continue
        tm = re.match(r"^(?P<types>.+?) in effect since (?P<since>(?:[A-Z][a-z]{2} \d{1,2}(?: \d{4})?, )?\d{1,2}:\d{2})"
                      r"(?:, ongoing for (?P<dur>[^.]+))?\.", rest)
        types = re.split(r",\s*|\s+and\s+", tm.group("types")) if tm else []
        lv = re.findall(r"\b(red|yellow)\b \((?:missile|drone)", rest)
        m_lvl = re.search(r"Alert level:\s*(red|yellow)", rest)
        level = "red" if "red" in lv or (m_lvl and m_lvl.group(1) == "red") else "yellow" if lv or m_lvl else None
        areas = []
        am = re.search(r"(\d+) areas? affected:\s*(.+?)(?:\.\s+The most recent|\.\s*$|$)", rest)
        if am:
            body = re.sub(r"\s*\[(?:red|yellow)[^\]]*\]", "", am.group(2))
            for a in re.split(r",\s*(?![^()]*\))", body):
                a = re.sub(r"\s*\[[^\]]*\]", "", a).strip(" .")
                nm = re.sub(r"\s*\([^()]*\)", "", a).strip()
                if nm and nm not in areas:
                    areas.append(nm)
        lm = re.search(r"most recent to go under alert was (.+?) at (\d{1,2}:\d{2})", rest)
        if region_for(title) and region_for(title)["c"] == "PL" and level is None:
            level = "yellow"  # alerts.in.ua records RCB notices as yellow
        add(title, "alert", types=types, level=level or "red",  # "where no level is reported, the warning is treated as red"
            since=_when(tm.group("since"), ref) if tm else None, duration=(tm.group("dur") or "").strip() if tm else None,
            n_areas=int(am.group(1)) if am else None, areas=areas[:20],
            latest={"name": re.sub(r"\s*\([^()]*\)", "", lm.group(1)), "at": _when(lm.group(2), ref)} if lm else None)

    def bullets(n, limit):
        out = []
        for line in (sec.get(n) or {}).get("lines", []):
            if line.startswith("- "):
                out.append(line[2:].strip())
        return out[:limit]

    threats = []
    for b in bullets(4, 40):
        m = re.match(r"^\*\*(\d{1,2}:\d{2}) — (.+?)\*\*\s+over\s+(.+?)\s+—\s+(.+)$", b)
        if m:
            what = re.sub(r"\s*\(\d+ tracked\)", "", m.group(2))
            n = re.search(r"\((\d+) tracked\)", m.group(2))
            over = _clean(m.group(3))
            r = region_for(over) if re.search(r"oblast|krai|respublika|область|край|республіка", over, re.I) else None
            threats.append({"at": _when(m.group(1), ref), "what": what, "n": int(n.group(1)) if n else None,
                            "over": re.sub(r"\s*\([^()]*\)", "", over), "region": r["id"] if r else None,
                            "msg": _clean(m.group(4)).lstrip("🛵🏍💣🚀✈️ ")})
    messages = []
    for b in bullets(6, 15) + bullets(7, 5) + bullets(12, 8):
        m = re.match(r"^\*\*(\d{1,2}:\d{2})\*\*\s+—\s+(.+?)\s+\(\[source\]\((https?://[^)]+)\)\):\s*(.+)$", b)
        if m:
            messages.append({"at": _when(m.group(1), ref), "who": _clean(m.group(2)), "url": m.group(3), "text": _clean(m.group(4))})
        elif not b.startswith("NSTR"):
            link = _LINK.search(b)
            messages.append({"at": None, "who": None, "url": link.group(2) if link else None, "text": _clean(b)})
    messages.sort(key=lambda x: x["at"] or "", reverse=True)
    incidents = [_clean(b) for b in bullets(5, 15)]
    ended = []
    for b in bullets(8, 15):
        m = re.match(r"^\*\*(?:([A-Z][a-z]{2} \d{1,2}), )?(\d{1,2}:\d{2})—(\d{1,2}:\d{2})\*\*\s+\(([^)]+)\)\s+—\s+(.+)$", b)
        if m:
            start = (m.group(1) + ", " + m.group(2)) if m.group(1) else m.group(2)
            ended.append({"from": _when(start, ref), "to": _when(m.group(3), ref), "dur": m.group(4),
                          "text": re.sub(r"\s*\([^()]*\)", "", _clean(m.group(5)))})
    key = {}
    for b in bullets(2, 20):
        m = re.match(r"^\*\*(.+?):\*\*\s*(.+)$", b)
        if m:
            key[m.group(1)] = re.sub(r"\s*\([^()]*\)", "", _clean(m.group(2)))
    bluf = " ".join(x.strip() for x in (sec.get(1) or {}).get("lines", []) if x.strip())
    return {"source": "alerts.in.ua SITREP", "dtg": head["DTG"], "state_line": head["WARNING STATE"],
            "as_of": ref.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "bluf": _clean(bluf)[:1200],
            "key": key, "regions": regions, "unmatched": unmatched[:20], "threats": threats[:25],
            "messages": messages[:15], "incidents": incidents, "ended": ended}


def parse_ubilling(d):
    """Fallback: oblast-level on/off only (no levels, no Russia/Poland)."""
    regions, unmatched = [], []
    for name, s in (d.get("states") or {}).items():
        if not s.get("alertnow"):
            continue
        r = region_for(name)
        if not r:
            unmatched.append(name)
            continue
        nominal = r["id"] in ("UA-09", "UA-43", "UA-40")  # occupied: standing administrative alerts
        when = None
        try:
            kyiv = dt.datetime.strptime(s.get("changed"), "%Y-%m-%d %H:%M:%S")
            when = (kyiv - dt.timedelta(hours=2 if kyiv.month in (1, 2, 3, 11, 12) or kyiv.month == 10 and kyiv.day > 25 else 3)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")  # Kyiv time, roughly; the fallback only needs minutes
        except (TypeError, ValueError):
            pass
        regions.append(dict(r, name=r["en"], kind="nominal" if nominal else "alert", level=None, types=["air raid alert"],
                            since=when, areas=[]))
    return {"source": "ubilling.net.ua (fallback, oblast level only)", "dtg": None, "state_line": None,
            "as_of": None, "bluf": "", "key": {}, "regions": regions, "unmatched": unmatched, "threats": [],
            "messages": [], "incidents": [], "ended": []}


def regions():
    """Feed `airalerts` (60 s)."""
    try:
        md = fetch(SITREP, timeout=20, conditional=True).decode("utf-8")
        out = parse_sitrep(md)
    except Exception as e:
        out = parse_ubilling(fetch_json(UBILLING, timeout=20))
        out["primary_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
    by = {}
    for r in out["regions"]:
        if r["kind"] == "alert":
            k = {"UA": "ukraine", "RU": "russia", "PL": "poland"}[r["c"]]
            by.setdefault(k, {"n": 0, "red": 0, "yellow": 0})
            by[k]["n"] += 1
            if r.get("level") in ("red", "yellow"):
                by[k][r["level"]] += 1
    out["counts"] = by
    return out


# ---------------- combined view + compact summary ----------------

def view(state):
    """GET /api/alerts. `state` is server.STATE."""
    g = lambda n: state.get(n) or {}
    il = israel_view(g("tzevalive").get("data"), g("tzeva").get("data"))
    il.update(ok=bool(g("tzeva").get("ok")), at=g("tzeva").get("at"), live_ok=bool(g("tzevalive").get("ok")),
              live_at=g("tzevalive").get("at"))
    reg = dict(g("airalerts").get("data") or {"regions": []})
    reg.update(ok=bool(g("airalerts").get("ok")), at=g("airalerts").get("at"))
    return {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "israel": il, "regions": reg,
            "summary": summary(state, il, reg)}


def summary(state, il=None, reg=None, now=None):
    """Compact view for /api/summary and the analyst (under 2 KB)."""
    try:
        if il is None or reg is None:
            v = view(state)
            return v["summary"]
        now = now or time.time()
        live = [c for c in il["cities"] if now - c["t"] <= (c["cd"] or 15) + c["x"]]
        shelter = [c for c in il["cities"] if now - c["t"] <= 600 and not c.get("ended")]
        ev = il["events"][0] if il["events"] else None
        al = [r for r in reg.get("regions") or [] if r["kind"] == "alert"]
        pick = lambda c: [("%s (%s)" % (r["en"], r.get("level") or "?")) for r in al if r["c"] == c][:30]
        return {
            "israel": {"sirens_now": len(live), "in_shelter_window": len(shelter),
                       "early_warnings_30min": sum(len(e["cities"]) for e in il["early"]),
                       "alerts_24h_by_threat": il["counts_24h"], "last_alert": il["last_alert"],
                       "latest_event": {k: ev[k] for k in ("label", "n", "areas")} if ev else None,
                       "latest_event_at": _iso(ev["t"]) if ev else None},
            "ukraine": dict((reg.get("counts") or {}).get("ukraine") or {"n": 0}, regions=pick("UA")),
            "russia": dict((reg.get("counts") or {}).get("russia") or {"n": 0}, regions=pick("RU")),
            "poland": dict((reg.get("counts") or {}).get("poland") or {"n": 0}, regions=pick("PL")),
            "launch_areas_tracked": [r["en"] for r in reg.get("regions") or [] if r["kind"] == "launch" or "launch" in r.get("also", [])],
            "threats_tracked": sorted({t["what"] for t in reg.get("threats") or []}),
            "as_of": reg.get("as_of"), "source": reg.get("source"),
        }
    except Exception as e:  # never break /api/summary
        return {"error": type(e).__name__}
