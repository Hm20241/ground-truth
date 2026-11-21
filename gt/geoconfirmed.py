"""GeoConfirmed volunteer geolocations, worldwide (keyless CSV export). v1.0, 2026-11-20 (Ground Truth 0.11.0).

GeoConfirmed's volunteers geolocate photos and videos from active conflicts and check each placemark against the
footage before it is published, with the X / Telegram source links. Its public conflicts span Ukraine, Iran,
Israel/Gaza/Lebanon, Syria, Yemen, the Sahel, DR Congo, Venezuela, the Mexican cartels, Taiwan/Pacific,
Afghanistan-Pakistan, India-Pakistan, Thailand-Cambodia, Myanmar and a World map.

Every hour (feed `geoconfirmed`) one poll makes:
* one GET of the global CSV export `https://geoconfirmed.org/api/Map/export/csv?start=<today-14d>T00:00:00Z
  &end=<tomorrow>T00:00:00Z` (documented in https://geoconfirmed.org/openapi/v1.json);
* the conflict list `/api/Conflict` (short name -> full name and map slug), only when the copy in
  <GT_DATA>/cache/geoconfirmed_conflicts.json is a day old (or 6 h old and lacks a conflict the export names).
  A failed refresh falls back to that copy, then to the short names; it never fails the feed.

The export covers the whole 14-day window every time, because geolocations land days after the event, so a full
answer is authoritative: a placemark that left the export (retracted or unapproved) leaves the feed. Rows are
de-duplicated by the export's `Id` (a GUID); <GT_DATA>/cache/geoconfirmed_window.json keeps each Id's first-seen
time (it decides which pin keeps a shared post's id) and the last good rows. An export with no dated rows at all
while that file holds some is treated as a glitch: the cached rows are served and the source is marked ok=false.
A failed export raises (the scheduler keeps the last good data).

Probed 2026-11-20: semicolon-separated, UTF-8 with a BOM, LF line ends, quoted fields with "" escapes and the odd
`;` inside; columns Conflict;Date;Name;Faction;Origin;Latitude;Longitude;PlusCode;Description;Source;Geolocation;
Equipment;EquipmentItems;Units;OrbatUnits;Id. Conflict is the conflict's ShortName (Ukraine, Iran, VEN, Israel,
Sahel, Afgh, Taiwan, ...). The start/end filter applies to Date, but every undated row comes back on every call:
a 3-day query gave 743 rows, 691 of them undated static reference placemarks (~275 KB) and 52 dated events;
the 14-day poll gave 962 rows, 271 dated (~19 a day, 213 of them Ukraine), a 272 KB payload. Date is "YYYY-MM-DD", day only; every dated row's Name was like "17 NOV 2026" (a day, no time), so a
time is taken from Name only when it carries a zoned one (171430Z NOV 26, 17 NOV 2026 14:30 UTC). Source is a
comma-separated list ("(2/2) <url>, <url>, , More information, <url>"), the URLs glued to the commas; the first
URL was an X post in 51 of the 52 dated rows, posted 7 h before to 57 h after the Date. Description has <br>, <nobr>,
<a> and &-entities; its first line is the headline. Several placemarks can cite one post ("(1/2)", "(2/2)"): 42 of the 271.

Times, ids and the event schema are shared with gt/curated.py: a zoned DTG in Name near the Date, else the
earliest X post id near the Date ("x-snowflake"), else the Date at 12:00Z ("date"). The id is mymaps'
sha1(parse_source(url)["url"])[:16] for the first source URL, so a pin from the same post as a source-map pin
shares its id; other placemarks citing that post, and placemarks without a URL, get sha1("geoconfirmed:<Id>").

Terms: the API says the dataset "is freely available for research, journalism, and analytical use through this
API" and asks for a descriptive User-Agent (sent, without contact details). No formal licence, so this feed is
non-commercial and stays on the private dashboard, off the public mirror, until GeoConfirmed agrees. Never for the trading agent.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import re
import urllib.parse

from . import curated as cu

VERSION = "1.0"
ATTRIBUTION = "GeoConfirmed (geoconfirmed.org): volunteer geolocations checked against photo and video"
ATTRIBUTION_URL = "https://geoconfirmed.org"
LICENCE = ("No formal licence; GeoConfirmed's API says its data is 'freely available for research, journalism, and "
           "analytical use'. Non-commercial, private dashboard only (not the public mirror) until GeoConfirmed agrees; never for "
           "the trading agent")
NON_COMMERCIAL = True
PUBLIC_OK = False
NOTE = ("Placemarks geolocated by GeoConfirmed volunteers, last 14 days by event date (they often land days late). "
        "Time = a zoned time in the placemark name, else the first X post when it is within days of the date, "
        "else the date at 12:00Z (ts_source says which).")
SOURCE, LABEL = "geoconfirmed", "GeoConfirmed"

BASE = "https://geoconfirmed.org"
EXPORT_URL = BASE + "/api/Map/export/csv"
CONFLICT_URL = BASE + "/api/Conflict"
WINDOW_DAYS = 14
STATE_FILE = "geoconfirmed_window.json"
CONFLICT_FILE = "geoconfirmed_conflicts.json"
CONFLICT_MAX_AGE = 86400
CONFLICT_RETRY = 6 * 3600   # a conflict the list lacks triggers a refresh at most this often
DESC_KEEP = 3000            # characters of Description kept in the state file
COLUMNS = ("Conflict", "Date", "Name", "Faction", "Origin", "Latitude", "Longitude", "Description", "Source",
           "Geolocation", "Equipment", "Id")

_MON = r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?"
MONTHS = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                          "NOV", "DEC"))}
# 171430Z NOV 26 / 171430ZNOV2026 / 171430C NOV 26 (military DTG: day, hour, minute, zone letter, month, year)
_DTG_MIL = re.compile(r"\b(\d{2})(\d{2})(\d{2})\s?([A-IK-Z])\s*" + _MON + r"\s*'?(\d{4}|\d{2})\b")
# 17 NOV 2026 14:30 UTC / 17 NOV 2026 - 1430Z / 17NOV2026 14.30 GMT+3
_DTG_DAY = re.compile(r"\b(\d{1,2})\s*" + _MON + r"\s*(\d{4})\b[\s,;@|\-–]*(?:AT\s*)?(\d{1,2})[:.H]?(\d{2})\s*"
                      r"\(?\s*(Z|ZULU|UTC|GMT)\b\s*(?:([+-])\s*(\d{1,2})(?::?(\d{2}))?)?")


def _fetch(url):
    return cu.fetch_url(url)


def _zone_hours(c):
    if c == "Z":
        return 0
    if "A" <= c <= "I":
        return ord(c) - ord("A") + 1
    if "K" <= c <= "M":
        return ord(c) - ord("K") + 10
    return -(ord(c) - ord("N") + 1)          # N .. Y = UTC-1 .. UTC-12


def parse_dtg(name):
    """Epoch ms of a zoned date-time in a placemark name, or None (day-only names give None)."""
    s = (name or "").upper()
    try:
        m = _DTG_MIL.search(s)
        if m:
            day, hh, mm, zone, mon, yr = m.groups()
            y = int(yr) + (2000 if len(yr) == 2 else 0)
            t = dt.datetime(y, MONTHS[mon], int(day), int(hh), int(mm), tzinfo=dt.timezone.utc)
            return int((t - dt.timedelta(hours=_zone_hours(zone))).timestamp() * 1000)
        m = _DTG_DAY.search(s)
        if m:
            day, mon, yr, hh, mm, _z, sign, oh, om = m.groups()
            t = dt.datetime(int(yr), MONTHS[mon], int(day), int(hh), int(mm), tzinfo=dt.timezone.utc)
            off = dt.timedelta(hours=int(oh or 0), minutes=int(om or 0)) * (-1 if sign == "-" else 1)
            return int((t - off).timestamp() * 1000)
    except (ValueError, OverflowError):
        return None
    return None


def parse_csv(raw):
    """Rows of the export as dicts keyed by COLUMNS (missing columns -> ""). Handles the BOM, a `sep=` line,
    CRLF, quoted fields with "" and `;` inside. Raises ValueError when the body is not the export."""
    text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
    text = text.lstrip("﻿")
    if text[:4].lower() == "sep=":
        text = text.split("\n", 1)[1] if "\n" in text else ""
    head = text.split("\n", 1)[0]
    delim = ";" if head.count(";") >= head.count(",") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    header = next(reader, None)
    if not header:
        raise ValueError("GeoConfirmed: empty export")
    idx = {h.strip().lstrip("﻿").lower(): i for i, h in enumerate(header)}
    if not all(k in idx for k in ("date", "latitude", "longitude")):
        raise ValueError("GeoConfirmed: the export has no Date/Latitude/Longitude columns")
    cols = [(c, idx.get(c.lower())) for c in COLUMNS]
    rows = []
    for rec in reader:
        if not rec or not any(x.strip() for x in rec):
            continue
        rows.append({c: (rec[i].strip() if i is not None and i < len(rec) else "") for c, i in cols})
    return rows


def _date(s):
    s = (s or "").strip()
    if not s:
        return None, "undated"
    try:
        return dt.date.fromisoformat(s[:10]), None
    except ValueError:
        return None, "bad_date"


def _num(s):
    s = (s or "").strip()
    return s.replace(",", ".") if "." not in s else s


def _sid(r):
    if r.get("Id"):
        return r["Id"].strip().lower()
    key = "|".join((r.get("Conflict") or "", r.get("Name") or "", r.get("Latitude") or "", r.get("Longitude") or ""))
    return "h" + hashlib.sha1(key.encode()).hexdigest()[:16]


def _slim(r):
    out = {c: r.get(c, "") for c in COLUMNS}
    out["Description"] = out["Description"][:DESC_KEEP]
    return out


# ---------------- conflict list ----------------

def _index(conf):
    idx = {}
    for short, c in conf.items():
        for k in (short, c.get("code"), c.get("name")):
            if k:
                idx.setdefault(str(k).strip().lower(), dict(c, short=short))
    return idx


def conflicts(fetch, now, need=()):
    """(short name -> {name, url, code}, source record). Cached a day; never raises."""
    now_s = int(cu.utc(now).timestamp())
    st = cu.load_state(CONFLICT_FILE)
    have = st.get("conflicts") if isinstance(st.get("conflicts"), dict) else {}
    age = now_s - (st.get("t") or 0)
    known = _index(have)
    missing = [n for n in need if n and n.strip().lower() not in known]
    rec = {"name": "GeoConfirmed conflict list", "ok": True, "error": None, "newest": None, "n": len(have),
           "cached": True}
    if have and age < CONFLICT_MAX_AGE and not (missing and age >= CONFLICT_RETRY):
        return have, rec
    try:
        d = json.loads(fetch(CONFLICT_URL))
        if not isinstance(d, list):
            raise ValueError("GeoConfirmed: conflict list is not a list")
        conf = {}
        for c in d:
            if not isinstance(c, dict) or c.get("isPrivate"):
                continue
            short = cu.clean_text(c.get("shortName"), 60)
            if not short:
                continue
            slug = (c.get("url") or "").strip()
            conf[short] = {"name": cu.clean_text(c.get("name"), 80) or short,
                           "url": slug if re.fullmatch(r"[A-Za-z0-9_-]{1,60}", slug) else None,
                           "code": cu.clean_text(c.get("code"), 30) or None}
        if not conf:
            raise ValueError("GeoConfirmed: empty conflict list")
    except Exception as e:
        rec.update(ok=False, error=cu.err_text(e), cached=bool(have))
        return have, rec
    rec.update(n=len(conf), cached=False)
    try:
        cu.save_state(CONFLICT_FILE, {"v": 1, "t": now_s, "conflicts": conf})
    except OSError as e:
        rec["state_error"] = cu.err_text(e)
    return conf, rec


# ---------------- one placemark -> Feature ----------------

def _build(r, cidx, day, now):
    ll = cu.valid_lonlat(_num(r.get("Longitude")), _num(r.get("Latitude")))
    if not ll:
        return None
    urls = cu.find_urls(r.get("Source"))
    src = cu.source_info(urls[0] if urls else None)
    ts = cu.pick_time(day, now, cu.x_post_ids(urls), parse_dtg(r.get("Name")))
    short = cu.clean_text(r.get("Conflict"), 60)
    c = cidx.get(short.lower()) or {}
    cname = c.get("name") or short or None
    faction = cu.clean_text(r.get("Faction"), 60) or None
    title = (cu.first_line(r.get("Description")) or
             " - ".join(x for x in (faction, cname) if x) or cu.clean_text(r.get("Name"), cu.TITLE_MAX) or LABEL)
    geo_urls = cu.find_urls(r.get("Geolocation"))
    links = []
    for u in urls[1:]:
        u = u.split("?")[0]
        if u != src.get("url") and u not in links:
            links.append(u)
    extras = {"conflict": cname, "conflict_short": short or None, "faction": faction, "origin": cu.clean_text(r.get("Origin"), 12) or None,
              "equipment": cu.clean_text(r.get("Equipment"), 120) or None,
              "geo_url": geo_urls[0].split("?")[0] if geo_urls else None,
              "links": links[:cu.LINKS_MAX] or None, "gc_id": r.get("Id") or None, "link_private": src["link_private"]}
    return cu.make_feature(ll[0], ll[1], title, ts, src, SOURCE, LABEL, cu.clean_text(r.get("Description"), cu.DESC_MAX),
                           extras)


# ---------------- the feed ----------------

def poll(now=None, fetch=None):
    now, fetch = cu.utc(now), fetch or _fetch
    today, now_ms = now.date(), int(now.timestamp() * 1000)
    since = today - dt.timedelta(days=WINDOW_DAYS)
    q = {"start": since.isoformat() + "T00:00:00Z", "end": (today + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"}
    rows = parse_csv(fetch(EXPORT_URL + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote, safe=":")))

    dropped = {"undated": 0, "bad_date": 0, "outside_window": 0, "future": 0, "duplicate_id": 0, "bad_coords": 0,
               "cap": 0}
    state = cu.load_state(STATE_FILE)
    old = state.get("rows") if isinstance(state.get("rows"), dict) else {}
    cur = {}

    def take(sid, r, first_seen):
        day, why = _date(r.get("Date"))
        if day is None:
            dropped[why] += 1
        elif day < since:
            dropped["outside_window"] += 1
        elif day > today + dt.timedelta(days=1):
            dropped["future"] += 1
        elif sid in cur:
            dropped["duplicate_id"] += 1
        else:
            cur[sid] = {"first_seen": first_seen, "r": _slim(r), "day": day}

    for r in rows:
        sid = _sid(r)
        prev = old.get(sid) if isinstance(old.get(sid), dict) else {}
        take(sid, r, prev.get("first_seen") or now_ms)
    err = None
    if not cur and old:   # every dated row gone at once: a glitch, not 14 days of retractions
        undated = dropped["undated"]
        for sid, rec in old.items():
            if isinstance(rec, dict) and isinstance(rec.get("r"), dict):
                take(sid, rec["r"], rec.get("first_seen") or now_ms)
        dropped["undated"] = undated
        err = "the export had no dated rows; serving %d cached" % len(cur)

    cmap, crec = conflicts(fetch, now, need={v["r"].get("Conflict") for v in cur.values()})
    cidx = _index(cmap)
    entries, keep = [], {}
    for sid, v in cur.items():
        f = _build(v["r"], cidx, v["day"], now)
        if f is None:
            dropped["bad_coords"] += 1
            continue
        entries.append({"sid": sid, "first_seen": v["first_seen"], "feature": f})
        keep[sid] = {"first_seen": v["first_seen"], "r": v["r"]}
    cu.assign_ids(entries, SOURCE)
    feats, dropped["cap"] = cu.cap_features(cu.sort_newest([e["feature"] for e in entries]))
    src = {"name": "GeoConfirmed export (CSV)", "ok": err is None, "error": err, "newest": cu.newest_iso(feats),
           "n": len(feats), "rows": len(rows), "dropped": dropped}
    try:
        cu.save_state(STATE_FILE, {"v": 1, "saved": cu.iso(now_ms), "rows": keep})
    except OSError as e:
        src["state_error"] = cu.err_text(e)
    attribution = [{"text": ATTRIBUTION, "url": ATTRIBUTION_URL, "licence": LICENCE}]
    out = cu.envelope(SOURCE, now, feats, [src, crec], attribution, LICENCE, PUBLIC_OK, NON_COMMERCIAL, NOTE,
                      WINDOW_DAYS, dropped["cap"])
    # conflict short name -> full name and GeoConfirmed map page, for the conflicts on the served pins only
    out["conflicts"] = {}
    for f in feats:
        short = f["properties"].get("conflict_short")
        if short and short not in out["conflicts"]:
            c = cidx.get(short.lower()) or {}
            out["conflicts"][short] = {"name": c.get("name") or short,
                                       "url": "%s/%s" % (BASE, c["url"]) if c.get("url") else None}
    return out


FEEDS = {"geoconfirmed": (poll, 3600)}
