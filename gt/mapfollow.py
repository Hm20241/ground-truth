"""Source-map auto-follow (0.10.0, module 1.0).

The curator starts a fresh My Maps file about once a week ("Global War News Map Day N") and links the current one
in every video description on their channel. Ground Truth used to poll one fixed map, so each roll-over left it on a
frozen map until someone pasted the new ID by hand.

Each map refresh this module:
  1. reads the channel's public RSS feed (no key, one small GET) and takes the newest description that links a
     My Maps file;
  2. switches to that map when its "Day N" is at least the current map's (a re-upload linking an older map never
     drags GT backwards);
  3. keeps reading the previous map for OVERLAP_H hours after a switch, so the feed does not empty while the new
     map fills (pins are merged by their source-URL id, so a copied pin shows once).

Privacy: the channel ID and every map ID stay private. The channel comes from $GT_MYMAPS_CHANNEL, else
$GT_SEED/mymaps.channel (container), else "channel" in config/mymaps.local.json. State, which holds map IDs, lives in
$GT_DATA/mymaps_follow.json (chmod 600, never published). status() carries only days, times and flags.
A hand-made change to the configured map (GT_MYMAPS_MID / the local config) always wins over the followed one.
"""
import datetime as dt
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

FOLLOW_VERSION = "1.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
STATE = os.path.join(DATA, "mymaps_follow.json")
RSS = "https://www.youtube.com/feeds/videos.xml?channel_id=%s"
UA = "GroundTruth/0.10 (personal OSINT dashboard)"
OVERLAP_H = float(os.environ.get("GT_MAP_OVERLAP_H", "48"))
CHANNEL_RX = re.compile(r"UC[A-Za-z0-9_-]{22}")
MID_RX = re.compile(r"google\.com/maps/d/[^\s\"'<>]*?[?&;]mid=([A-Za-z0-9_-]{10,})")
ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def _iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def channel():
    """The publisher's channel ID, or None when auto-follow is not configured."""
    ch = (os.environ.get("GT_MYMAPS_CHANNEL") or "").strip()
    if not ch:
        p = os.path.join(os.environ.get("GT_SEED") or "/seed", "mymaps.channel")
        if os.path.isfile(p):
            ch = open(p, encoding="utf-8").read().strip()
    if not ch:
        try:
            with open(os.path.join(ROOT, "config", "mymaps.local.json"), encoding="utf-8") as fh:
                ch = (json.load(fh)["maps"][0].get("channel") or "").strip()
        except (OSError, ValueError, KeyError, IndexError):
            ch = ""
    return ch if CHANNEL_RX.fullmatch(ch) else None


def fetch_rss(ch, timeout=30):
    req = urllib.request.Request(RSS % ch, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_link(rss_bytes):
    """(map_id, published_iso) from the newest feed entry whose description links a My Maps file, else None."""
    root = ET.fromstring(rss_bytes)
    best = None
    for e in root.iter(ATOM + "entry"):
        pub = e.findtext(ATOM + "published") or ""
        desc = e.findtext(".//" + MEDIA + "description") or ""
        m = MID_RX.search(desc)
        if m and (best is None or pub > best[1]):
            best = (m.group(1), pub)
    return best


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(DATA, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE)


def _err(e, *secrets):
    msg = "%s: %s" % (type(e).__name__, str(e)[:160])
    for s in secrets:
        if s:
            msg = msg.replace(s, "<id>")
    return msg


def resolve(base_mid, fetch_kml, parse, now_ms=None):
    """Pick the map(s) to read this cycle.

    Returns ([(role, kml_bytes, fc), ...], status): "current" first, then "previous" while the overlap lasts.
    Raises only when the current map cannot be read and no newer map was found.
    """
    now_ms = now_ms or int(time.time() * 1000)
    st = load_state()
    if st.get("base") != base_mid:  # first run, or the configured map was changed by hand: that wins
        st = {"base": base_mid, "mid": base_mid}
    cur = st.get("mid") or base_mid
    ch = channel()
    info = {"version": FOLLOW_VERSION, "enabled": bool(ch), "ok": None, "checked_at": None, "error": None,
            "linked_at": None, "note": None, "switched": False}

    cur_raw = cur_fc = cur_err = None
    try:
        cur_raw = fetch_kml(cur)
        cur_fc = parse(cur_raw)
        st["day"] = cur_fc.get("map_day")
    except Exception as e:  # the old map may be gone; a newer one below can still rescue the cycle
        cur_err = e

    prev_raw = prev_fc = None
    if ch:
        info["checked_at"] = _iso(now_ms)
        try:
            link = latest_link(fetch_rss(ch))
            if not link:
                raise ValueError("no My Maps link in the channel's newest videos")
            mid, published = link
            info.update(ok=True, linked_at=published)
            if mid != cur and mid != st.get("rejected"):
                new_raw = fetch_kml(mid)
                new_fc = parse(new_raw)
                nd, cd = new_fc.get("map_day"), st.get("day")
                if nd is not None and (cd is None or nd >= cd):
                    st.update(prev=cur, prev_day=cd, prev_until_ms=now_ms + int(OVERLAP_H * 3600000),
                              mid=mid, day=nd, switched_at=_iso(now_ms), rejected=None)
                    prev_raw, prev_fc = cur_raw, cur_fc
                    cur, cur_raw, cur_fc, cur_err = mid, new_raw, new_fc, None
                    info["switched"] = True
                else:
                    st["rejected"] = mid
                    info["note"] = "newest linked map is Day %s, not newer than the current Day %s; kept the current map" % (nd, cd)
            elif mid == st.get("rejected"):
                info["note"] = "newest linked map was checked before and is older; kept the current map"
        except Exception as e:
            info.update(ok=False, error=_err(e, ch, cur, st.get("rejected")))

    if cur_fc is None:
        save_state(st)
        raise RuntimeError("current map unreadable (%s)" % _err(cur_err, cur, base_mid))

    maps = [("current", cur_raw, cur_fc)]
    overlap = bool(st.get("prev")) and now_ms < (st.get("prev_until_ms") or 0)
    if overlap:
        if prev_fc is None:
            try:
                prev_raw = fetch_kml(st["prev"])
                prev_fc = parse(prev_raw)
            except Exception as e:
                info["note"] = "previous map unreadable (%s)" % _err(e, st["prev"])
        if prev_fc is not None:
            maps.append(("previous", prev_raw, prev_fc))
    elif st.get("prev"):
        st["prev"] = None  # overlap over: forget the old ID, keep its day and the switch time for display
    save_state(st)
    info.update(map_day=cur_fc.get("map_day"), switched_at=st.get("switched_at"), previous_day=st.get("prev_day"),
                overlap_until=_iso(st["prev_until_ms"]) if overlap else None,
                reading=[{"role": r, "day": fc.get("map_day")} for r, _, fc in maps])
    return maps, info


def merge(maps):
    """Current map's features, plus the previous map's events that the current map does not already carry."""
    cur = maps[0][2]
    if len(maps) == 1:
        return cur
    seen = {f["properties"]["id"] for f in cur["features"]}
    extra = []
    for _role, _raw, fc in maps[1:]:
        for f in fc["features"]:
            p = f["properties"]
            if p.get("kind") == "event" and p["id"] not in seen:
                seen.add(p["id"])
                extra.append(f)
    return dict(cur, features=cur["features"] + extra, merged_previous=len(extra))
