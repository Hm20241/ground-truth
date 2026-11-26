"""EPA AirNow air-quality monitors. v1.0, 2026-11-25 (Ground Truth 1.7.2).

Feed `airnow` (every 30 min; the data are hourly). Source: the AirNow "Hourly AQ Obs" file product, a public file
with no account and no key:
  https://files.airnowtech.org/airnow/YYYY/YYYYMMDD/HourlyAQObs_YYYYMMDDHH.dat      (date and hour in UTC)
One CSV row per monitoring site: site, coordinates, state, country, the hour, the NowCast AQI for ozone, PM10 and
PM2.5 and the hourly AQI for NO2. A site's AQI here is the highest of those, as on AirNow's own maps.

The feed tries the last complete hour, then up to three hours before it, and uses the newest file in which at least
MIN_REPORTING sites report an AQI (a brand-new file can be thin); if none is that full, the fullest one found.
Kept: every site reading 101 or more ("Unhealthy for Sensitive Groups" or worse) as a point, plus a summary of all
reporting sites (count, count per AQI category, the ten highest, the observation hour). Values are passed on as
received. Category names and colours are EPA's own (AQI Technical Assistance Document; Hourly AQ Obs fact sheet).

Besides the US the file carries Canada, a few Mexican sites and the US Department of State's embassy and consulate
monitors (EPARegion "DS.."), so the worst readings are often abroad. `us` marks sites in the US.

Probed 2026-11-26 04:20Z: files.airnowtech.org answered a plain GET with no key; airnow/today/ holds other products
but NOT HourlyAQObs (404), the dated folder does. A file is ~1.0 MB, 4,367 rows, ~1,770 with an AQI, 9 at 101+. The
file for hour H existed by H+1:21 (fact sheet: written at about :35 past, and rewritten for 72 h as late data
arrive). ValidDate is mm/dd/yyyy (the fact sheet says mm/dd/yy; both are read), AQI values are whole numbers as
text (the fact sheet shows "39.0"; both are read), CountryCode is FIPS 10-4 (IN = India, CH = China), not ISO.

Terms: U.S. EPA AirNow Data Exchange Guidelines (docs.airnowapi.org/docs/DataUseGuidelines.pdf, August 2025).
Data are preliminary, not validated, and "should be considered preliminary"; displays must say so. Credit goes
first to the federal, state, local and tribal agencies that own the data, and to the EPA AirNow program. Values
are not to be altered, and are shown with the AQI categories and their RGB colours. The guidelines do not mention
commercial use at all; because the agencies, not EPA, own the data (and some are Canadian or Mexican), this module
marks the feed non-commercial rather than assume. The guidelines also ask data users to return a signed form with
contact details to the AirNow Data Management Center: that is the owner's call, not this module's.
This feed is a health and hazards picture only; it is not an input to anything else.
"""
import csv
import datetime as dt
import gzip
import io
import json
import math
import urllib.error
import urllib.request

VERSION = "1.0"
UA = "GroundTruth/1.7 (personal non-commercial OSINT dashboard)"
TIMEOUT = 30
MAX_READ = 6000000      # a file is ~1.0 MB; anything over this is not the product we expect
MAX_BYTES = 150000      # the payload cap (a normal payload is a few kB; a wildfire-smoke day has hundreds of points)
MAX_ROWS = 20000

URL = "https://files.airnowtech.org/airnow/%Y/%Y%m%d/HourlyAQObs_%Y%m%d%H.dat"
HOURS_BACK = 4          # the last complete hour and the three before it
MIN_REPORTING = 300     # sites with an AQI for a file to count as full
CUT = 101               # "Unhealthy for Sensitive Groups" starts here
TOP_N = 10

# EPA's AQI categories: (lowest AQI, name, colour). Above 500 is still Hazardous.
CATEGORIES = ((0, "Good", "#00e400"), (51, "Moderate", "#ffff00"),
              (101, "Unhealthy for Sensitive Groups", "#ff7e00"), (151, "Unhealthy", "#ff0000"),
              (201, "Very Unhealthy", "#8f3f97"), (301, "Hazardous", "#7e0023"))
COLOURS = {name: col for _, name, col in CATEGORIES}
POLLUTANTS = (("PM25_AQI", "PM2.5"), ("OZONE_AQI", "ozone"), ("PM10_AQI", "PM10"), ("NO2_AQI", "NO2"))
NEED = ("AQSID", "SiteName", "Latitude", "Longitude", "ValidDate", "ValidTime", "PM25_AQI", "OZONE_AQI", "PM10_AQI")
# FIPS 10-4 country codes as the file uses them (the State Department sites and the neighbours)
FIPS = {"US": "United States", "CA": "Canada", "MX": "Mexico", "AE": "United Arab Emirates", "AF": "Afghanistan",
        "AG": "Algeria", "AJ": "Azerbaijan", "AM": "Armenia", "AR": "Argentina", "BA": "Bahrain", "BG": "Bangladesh",
        "BK": "Bosnia and Herzegovina", "BM": "Burma", "BR": "Brazil", "CD": "Chad", "CE": "Sri Lanka", "CH": "China",
        "CI": "Chile", "CO": "Colombia", "CS": "Costa Rica", "EG": "Egypt", "ET": "Ethiopia", "GH": "Ghana",
        "GT": "Guatemala", "ID": "Indonesia", "IN": "India", "IZ": "Iraq", "JA": "Japan", "JO": "Jordan",
        "KE": "Kenya", "KG": "Kyrgyzstan", "KU": "Kuwait", "KV": "Kosovo", "KZ": "Kazakhstan", "LA": "Laos",
        "MG": "Mongolia", "MZ": "Mozambique", "NI": "Nigeria", "NP": "Nepal", "PE": "Peru", "PK": "Pakistan",
        "QA": "Qatar", "SA": "Saudi Arabia", "TH": "Thailand", "TI": "Tajikistan", "TX": "Turkmenistan",
        "UG": "Uganda", "UZ": "Uzbekistan", "VM": "Vietnam"}

ATTRIBUTION = ("Air quality: U.S. EPA AirNow and the federal, state, local and tribal air agencies that own the data "
               "(airnow.gov/partners). Preliminary, unvalidated data.")
ATTRIBUTION_URL = "https://www.airnow.gov"
LICENCE = ("U.S. EPA AirNow Data Exchange Guidelines (Aug 2025): preliminary data, not for regulatory or trend use; "
           "credit the owning agencies and EPA AirNow; values and AQI colours unaltered. Commercial use is not "
           "addressed, so it is treated as not allowed here.")
PUBLIC_OK = {"airnow": True}        # redistribution with credit and the 'preliminary' label is what the guidelines describe
NON_COMMERCIAL = {"airnow": True}   # not stated in the terms; the agencies own the data, so this stays on the safe side
NOTE = ("AirNow monitors reading AQI 101 or more (Unhealthy for Sensitive Groups or worse) in the newest hourly file, "
        "by each site's highest pollutant. NowCast AQI for PM2.5, ozone and PM10. Preliminary data, not validated; "
        "includes Canada, Mexico and US embassy monitors abroad. Not a safety service: see airnow.gov.")


# ---------------- helpers ----------------

def _gunzip(b):
    b = b or b""
    return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        b = r.read(MAX_READ + 1)
    if len(b) > MAX_READ:
        raise ValueError("AirNow: file larger than %d bytes" % MAX_READ)
    return _gunzip(b)


def _utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def _ms(t):
    return int(t.timestamp() * 1000) if t else None


def _num(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _err(e):
    return "%s: %s" % (type(e).__name__, str(e)[:200])


def _src(name, ok, error=None, newest=None, n=0):
    return {"name": name, "ok": ok, "error": error, "newest": newest, "n": n}


def _size(d):
    return len(json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode())


def category(aqi):
    """EPA's category name for an AQI value, None when it is not a usable AQI."""
    if aqi is None or isinstance(aqi, bool) or not isinstance(aqi, (int, float)) or not math.isfinite(aqi) or aqi < 0:
        return None
    name = CATEGORIES[0][1]
    for lo, n, _ in CATEGORIES:
        if aqi >= lo:
            name = n
    return name


def url_for(hour):
    return hour.strftime(URL)


def _aqi(v):
    """An AQI cell ("152", "39.0", "") -> int, None when empty, not a number, negative or absurd."""
    x = _num(v)
    if x is None or x < 0 or x > 5000:
        return None
    return int(round(x))


def _when(date, time):
    """ValidDate (mm/dd/yyyy or mm/dd/yy) and ValidTime (hh:mm), both UTC -> aware datetime or None."""
    try:
        mo, d, y = (int(x) for x in str(date).strip().split("/"))
        h, mi = (int(x) for x in str(time).strip().split(":")[:2])
        return dt.datetime(y + 2000 if y < 100 else y, mo, d, h, mi, tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def _place(state, country, region):
    """Plain words for where a site is: the state for US sites, else the country."""
    name = FIPS.get(country)
    if country == "US" and state and state not in ("N/A", "MM"):
        return state
    if region[:2] == "DS":
        return "US embassy monitor, %s" % (name or country or "abroad")
    return name or country or state or ""


def parse(body):
    """The Hourly AQ Obs CSV -> (sites, skipped). A site is a dict with its highest AQI; rows with no AQI at all are
    not sites. A row that cannot be read (wrong width, no coordinates, bad time) is counted in `skipped`, never
    raised. Raises ValueError only when the file is not the product at all (no usable header)."""
    text = _gunzip(body).decode("utf-8", "replace").lstrip("﻿")
    if not text.strip():
        return [], 0
    rows = csv.reader(io.StringIO(text))
    try:
        head = [h.strip() for h in next(rows)]
    except (StopIteration, csv.Error):
        return [], 0
    col = {h: i for i, h in enumerate(head)}
    if any(k not in col for k in NEED):
        raise ValueError("AirNow: not an Hourly AQ Obs file (header %r)" % ",".join(head)[:80])
    sites, skipped, n = [], 0, 0
    while n < MAX_ROWS:
        try:
            r = next(rows)
        except StopIteration:
            break
        except csv.Error:
            skipped += 1
            continue
        n += 1
        if not r or not any(c.strip() for c in r):
            continue
        if len(r) != len(head):
            skipped += 1
            continue
        g = lambda k: r[col[k]].strip() if k in col else ""  # noqa: E731
        best = None
        for key, label in POLLUTANTS:
            a = _aqi(g(key))
            if a is not None and (best is None or a > best[0]):
                best = (a, label)
        if best is None:
            if any(g(k) for k, _ in POLLUTANTS):
                skipped += 1   # an AQI cell that is not a usable number
            continue
        lat, lon, t = _num(g("Latitude")), _num(g("Longitude")), _when(g("ValidDate"), g("ValidTime"))
        if (lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0)
                or t is None or not g("AQSID")):
            skipped += 1
            continue
        state, country, region = g("StateName"), g("CountryCode"), g("EPARegion")
        sites.append({"id": g("AQSID"), "site": " ".join(g("SiteName").split())[:80] or g("AQSID"),
                      "state": state if state not in ("", "N/A") else None, "country": country or None,
                      "place": _place(state, country, region), "us": country == "US",
                      "aqi": best[0], "category": category(best[0]), "pollutant": best[1],
                      "agency": " ".join(g("DataSource").split())[:100] or None,
                      "t": t, "lat": lat, "lon": lon})
    return sites, skipped


def _public(s):
    """A site as the payload carries it (no coordinates: those are the feature's geometry)."""
    return {"id": s["id"], "site": s["site"], "state": s["state"], "country": s["country"], "place": s["place"],
            "us": s["us"], "aqi": s["aqi"], "category": s["category"], "color": COLOURS[s["category"]],
            "pollutant": s["pollutant"], "agency": s["agency"], "time": _iso(s["t"]), "ts_ms": _ms(s["t"]),
            "source": "AirNow"}


def _fit(out, max_bytes=None):
    """Drop features from the end (the lowest AQI) until the payload is under max_bytes."""
    max_bytes = max_bytes or MAX_BYTES
    feats = out["geojson"]["features"]
    dropped = 0
    while feats and _size(out) > max_bytes:
        step = max(1, len(feats) // 20)
        del feats[-step:]
        dropped += step
    out["count"] = len(feats)
    if dropped:
        out["trimmed"] = dropped
    return out


def airnow(now=None, fetch=None):
    now, fetch = _utc(now), fetch or _fetch
    last = now.replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=1)
    sources, best = [], None
    for back in range(HOURS_BACK):
        hour = last - dt.timedelta(hours=back)
        name = "AirNow Hourly AQ Obs %s" % hour.strftime("%Y-%m-%d %H:00Z")
        try:
            sites, skipped = parse(fetch(url_for(hour)))
        except Exception as e:  # noqa: BLE001  a missing hour (404) is normal for the newest file
            sources.append(_src(name, False, _err(e)))
            continue
        newest = max((s["t"] for s in sites), default=None)
        sources.append(_src(name, True, newest=_iso(newest), n=len(sites)))
        if best is None or len(sites) > len(best[1]):
            best = (hour, sites, skipped)
        if len(sites) >= MIN_REPORTING:
            break
    if best is None:
        raise RuntimeError("AirNow: every hour failed: " + "; ".join(s["error"] for s in sources))
    hour, sites, skipped = best
    if not sites:
        raise RuntimeError("AirNow: no site reports an AQI in the last %d hourly files" % HOURS_BACK)

    sites.sort(key=lambda s: (-s["aqi"], s["site"], s["id"]))
    by_cat = {n: 0 for _, n, _ in CATEGORIES}
    for s in sites:
        by_cat[s["category"]] += 1
    high = [s for s in sites if s["aqi"] >= CUT]
    obs = max(s["t"] for s in sites)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(s["lon"], 3), round(s["lat"], 3)]},
              "properties": _public(s)} for s in high]
    out = {"version": VERSION, "fetched_at": _iso(now), "count": len(feats),
           "summary": {"reporting": len(sites), "reporting_us": sum(1 for s in sites if s["us"]),
                       "unhealthy": len(high), "unhealthy_us": sum(1 for s in high if s["us"]),
                       "by_category": by_cat, "top": [_public(s) for s in sites[:TOP_N]],
                       "obs_hour": _iso(obs), "obs_ts_ms": _ms(obs), "file_hour": _iso(hour), "skipped": skipped},
           "categories": [{"min": lo, "name": n, "color": c} for lo, n, c in CATEGORIES], "cut": CUT,
           "preliminary": True, "sources": sources, "attribution": [ATTRIBUTION], "attribution_url": ATTRIBUTION_URL,
           "licence": LICENCE, "public_ok": PUBLIC_OK["airnow"], "non_commercial": NON_COMMERCIAL["airnow"],
           "note": NOTE, "geojson": {"type": "FeatureCollection", "features": feats}}
    return _fit(out)


FEEDS = {"airnow": (airnow, 1800)}
