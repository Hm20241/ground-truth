"""Offline tests for 0.10.0: source-map auto-follow (gt/mapfollow.py) and its use in gt/mymaps.run().
Never touches the network: KML and RSS are synthetic, every fetch is patched, sockets are blocked.

Run: python3 -I tests/test_0100_follow.py
"""
import json
import os
import shutil
import socket
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)
TMP = tempfile.mkdtemp(prefix="gt-follow-")
os.environ["GT_DATA"] = os.path.join(TMP, "data")
os.environ["GT_SEED"] = os.path.join(TMP, "seed")
os.environ.pop("GT_MYMAPS_CHANNEL", None)
os.environ.pop("GT_MYMAPS_MID", None)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import mapfollow, mymaps  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


EPOCH = 1288834974657
H = 3600000
T0 = 1795100000000  # 2026-11-18, the fixed "now" for the tests
CH = "UC" + "x" * 22
A, B, C, D = ("mapA" + "a" * 20, "mapB" + "b" * 20, "mapC" + "c" * 20, "mapD" + "d" * 20)
IDS = (A, B, C, D, CH)


def sid(ms):
    return str((ms - EPOCH) << 22)


def kml(day, pins):
    """pins: [(name, ms, lon, lat)] as X-linked point events, plus one overlay line."""
    pm = "".join(
        "<Placemark><name>%s</name><description>https://x.com/src/status/%s</description>"
        "<styleUrl>#icon-1899-0288D1</styleUrl><Point><coordinates>%s,%s,0</coordinates></Point></Placemark>"
        % (n, sid(ms), lon, lat) for n, ms, lon, lat in pins)
    pm += ("<Placemark><name>Front line</name><styleUrl>#line-000000-1200</styleUrl>"
           "<LineString><coordinates>36.0,48.0,0 37.0,48.5,0</coordinates></LineString></Placemark>")
    return ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            "<name>Global War News Map Day %d</name>%s</Document></kml>" % (day, pm)).encode()


P1 = ("Strike on depot", T0 - 30 * H, 37.5, 47.1)
P2 = ("Drone attack", T0 - 20 * H, 36.2, 49.9)
P3 = ("Missile launch", T0 - 6 * H, 51.4, 35.7)
P4 = ("Explosion", T0 - 1 * H, 35.5, 33.9)
MAPS = {A: kml(1728, [P1, P2, P3]), B: kml(1729, [P3, P4]), C: kml(1700, [P1]), D: kml(1730, [P4])}
FETCHED = []
GONE = set()


def fetch_kml(mid):
    FETCHED.append(mid)
    if mid in GONE:
        raise OSError("HTTP Error 404: Not Found for %s" % mid)
    return MAPS[mid]


def rss(*entries):
    """entries: [(published_iso, map_id or None, url_form)]."""
    body = ""
    for pub, mid, form in entries:
        link = (form % mid) if mid else "https://example.org/merch"
        body += ("<entry><published>%s</published><media:group><media:description>Day N Global War News Map:\n%s\n"
                 "Support: https://example.org/support</media:description></media:group></entry>" % (pub, link))
    return ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">'
            "%s</feed>" % body).encode()


EDIT = "https://www.google.com/maps/d/edit?mid=%s&amp;usp=sharing"
VIEW = "https://www.google.com/maps/d/u/0/viewer?ll=1,2&amp;mid=%s"
RSS_NOW = [None]


def fetch_rss(ch):
    if isinstance(RSS_NOW[0], Exception):
        raise RSS_NOW[0]
    return RSS_NOW[0]


mapfollow.fetch_rss = fetch_rss


def no_ids(obj, what):
    s = json.dumps(obj)
    check(not any(i in s for i in IDS), what + ": no map or channel ID in the status")


def reset():
    if os.path.exists(mapfollow.STATE):
        os.remove(mapfollow.STATE)
    FETCHED.clear()
    GONE.clear()


# ---- RSS parsing ----
x = rss(("2026-11-17T06:40:50+00:00", A, EDIT), ("2026-11-20T03:01:05+00:00", B, VIEW), ("2026-11-19T07:04:50+00:00", None, EDIT))
check(mapfollow.latest_link(x) == (B, "2026-11-20T03:01:05+00:00"), "latest_link: newest entry wins whatever the order; viewer + u/0 form")
check(mapfollow.latest_link(rss(("2026-11-20T00:00:00+00:00", A, EDIT))) == (A, "2026-11-20T00:00:00+00:00"), "latest_link: edit link with &amp;usp")
check(mapfollow.latest_link(rss(("2026-11-20T00:00:00+00:00", None, EDIT))) is None, "latest_link: no My Maps link -> None")

# ---- channel precedence ----
os.makedirs(os.environ["GT_SEED"], exist_ok=True)
fake_root = os.path.join(TMP, "root")
os.makedirs(os.path.join(fake_root, "config"))
real_root, mapfollow.ROOT = mapfollow.ROOT, fake_root
check(mapfollow.channel() is None, "channel: nothing configured -> None (auto-follow off)")
json.dump({"maps": [{"mid": A, "channel": "UC" + "c" * 22}]}, open(os.path.join(fake_root, "config", "mymaps.local.json"), "w"))
check(mapfollow.channel() == "UC" + "c" * 22, "channel: local config")
open(os.path.join(os.environ["GT_SEED"], "mymaps.channel"), "w").write("UC" + "s" * 22 + "\n")
check(mapfollow.channel() == "UC" + "s" * 22, "channel: seed file beats the local config")
os.environ["GT_MYMAPS_CHANNEL"] = CH
check(mapfollow.channel() == CH, "channel: env beats the seed file")
os.environ["GT_MYMAPS_CHANNEL"] = "not-a-channel"
check(mapfollow.channel() is None, "channel: malformed value -> None")
os.environ["GT_MYMAPS_CHANNEL"] = CH
mapfollow.ROOT = real_root

# ---- follow off: plain single map ----
reset()
os.environ["GT_MYMAPS_CHANNEL"] = ""
os.remove(os.path.join(os.environ["GT_SEED"], "mymaps.channel"))
mapfollow.ROOT = fake_root
os.remove(os.path.join(fake_root, "config", "mymaps.local.json"))
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0)
check([r for r, _, _ in maps] == ["current"] and maps[0][2]["map_day"] == 1728, "off: reads the configured map only")
check(info["enabled"] is False and info["checked_at"] is None and FETCHED == [A], "off: no feed read, one KML fetch")
os.environ["GT_MYMAPS_CHANNEL"] = CH

# ---- switch to a newer map ----
reset()
RSS_NOW[0] = rss(("2026-11-20T03:01:05+00:00", B, EDIT), ("2026-11-19T07:04:50+00:00", A, EDIT))
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0)
check([(r, fc["map_day"]) for r, _, fc in maps] == [("current", 1729), ("previous", 1728)], "switch: Day 1729 current, Day 1728 kept as previous")
check(info["switched"] and info["ok"] and info["map_day"] == 1729 and info["previous_day"] == 1728, "switch: status says moved 1728 -> 1729")
check(info["overlap_until"] == mapfollow._iso(T0 + 48 * H), "switch: previous map kept for 48 h")
check(FETCHED == [A, B], "switch: each KML fetched once (the old map is reused as previous)")
fc = mapfollow.merge(maps)
titles = sorted(f["properties"]["title"] for f in fc["features"] if f["properties"]["kind"] == "event")
check(titles == sorted(["Missile launch", "Explosion", "Strike on depot", "Drone attack"]), "merge: shared pin once, old-only pins added")
check(fc["map_day"] == 1729 and fc["merged_previous"] == 2, "merge: title/day from the current map, 2 pins from the previous")
check(sum(1 for f in fc["features"] if f["properties"]["kind"] == "overlay") == 1, "merge: overlays only from the current map")
st = json.load(open(mapfollow.STATE))
check(st["mid"] == B and st["prev"] == A and st["base"] == A, "state: follows B, remembers A, base unchanged")
check(oct(os.stat(mapfollow.STATE).st_mode & 0o777) == "0o600", "state: file is chmod 600")
no_ids(info, "switch")

# ---- next cycle: stays on B, still merges A ----
FETCHED.clear()
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0 + 1 * H)
check([fc["map_day"] for _, _, fc in maps] == [1729, 1728] and not info["switched"], "next cycle: no re-switch, overlap still on")
check(FETCHED == [B, A], "next cycle: reads B then the previous A")

# ---- overlap over ----
FETCHED.clear()
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0 + 49 * H)
check([fc["map_day"] for _, _, fc in maps] == [1729] and info["overlap_until"] is None, "after 48 h: previous map dropped")
check(json.load(open(mapfollow.STATE))["prev"] is None and FETCHED == [B], "after 48 h: old ID forgotten, one fetch")
check(info["previous_day"] == 1728 and info["switched_at"] == mapfollow._iso(T0), "after 48 h: switch day and time still shown")

# ---- an older map linked (rerun of an old video) ----
FETCHED.clear()
RSS_NOW[0] = rss(("2026-11-21T03:00:00+00:00", C, EDIT))
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0 + 50 * H)
check(maps[0][2]["map_day"] == 1729 and not info["switched"] and "not newer" in (info["note"] or ""), "older link: kept Day 1729")
FETCHED.clear()
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0 + 51 * H)
check(FETCHED == [B] and "checked before" in (info["note"] or ""), "older link: not fetched again next cycle")

# ---- feed failure: map still read, error carries no IDs ----
FETCHED.clear()
RSS_NOW[0] = OSError("HTTP Error 500 for channel %s" % CH)
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0 + 52 * H)
check(maps[0][2]["map_day"] == 1729 and info["ok"] is False and "OSError" in info["error"], "feed down: current map still read, ok=false")
no_ids(info, "feed down")

# ---- current map deleted, newer one linked: rescued ----
reset()
GONE.add(A)
RSS_NOW[0] = rss(("2026-11-20T03:01:05+00:00", B, EDIT))
maps, info = mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0)
check(maps[0][2]["map_day"] == 1729 and len(maps) == 1 and info["switched"], "old map gone: switched to the linked map")

# ---- current map deleted and feed down: raises without IDs ----
reset()
GONE.add(A)
RSS_NOW[0] = OSError("timed out")
try:
    mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0)
    check(False, "old map gone + feed down: raises")
except RuntimeError as e:
    check(not any(i in str(e) for i in IDS), "old map gone + feed down: raises, message has no IDs")

# ---- a hand change of the configured map wins ----
reset()
RSS_NOW[0] = rss(("2026-11-20T03:01:05+00:00", B, EDIT))
mapfollow.resolve(A, fetch_kml, mymaps.parse, now_ms=T0)
RSS_NOW[0] = rss(("2026-11-20T03:01:05+00:00", B, EDIT))
maps, info = mapfollow.resolve(D, fetch_kml, mymaps.parse, now_ms=T0 + H)
check(maps[0][2]["map_day"] == 1730 and json.load(open(mapfollow.STATE))["base"] == D, "hand change: new configured map (Day 1730) wins")
check(not info["switched"] and "not newer" in (info["note"] or ""), "hand change: the feed's Day 1729 does not pull it back")

# ---- mymaps.run end to end ----
reset()
RSS_NOW[0] = rss(("2026-11-20T03:01:05+00:00", B, EDIT))
mymaps.fetch_kml = fetch_kml
mymaps.load_config = lambda: {"name": "test", "mid": A}
fc, st = mymaps.run()
check(st["events"] == 4 and st["map_day"] == 1729 and st["follow"]["switched"], "run: merged events, Day 1729, follow status in stats")
check(st["archive"]["snapshots"] == 1, "run: only the current map's KML is snapshotted")
disk = json.load(open(os.path.join(os.environ["GT_DATA"], "stats.json")))
check(disk["follow"]["map_day"] == 1729, "run: stats.json carries the follow status")
no_ids(disk, "stats.json")
no_ids(json.load(open(os.path.join(os.environ["GT_DATA"], "latest.geojson"))), "latest.geojson")
fc, st = mymaps.run()
check(st["archive"]["snapshots"] == 1 and st["archive"]["changed"] is False, "run again: current KML unchanged, no new snapshot (no A/B flip-flop)")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d checks passed" % ok)
