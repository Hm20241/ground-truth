"""Offline tests for 0.9.0: the AIS vessel registry, compression, back-off and tanker tracks (gt/ais.py 1.1), and the
ship feed's joins (flags, vessel lists, tanker cards, point cap) in gt/feeds.py.
Never touches the network: AISStream is replaced by canned samples, and the vessel-list index is a tiny fixture.
The flag table, PortWatch and vessel-list modules have their own tests (test_090_mid/portwatch/sanctions.py).

Run: python3 -I tests/test_090.py
"""
import datetime as dt
import json
import os
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)
from gt import ais  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 19, 6, 0, 0, tzinfo=UTC)

# ---------- IMO check digit ----------
check(ais.imo_ok(9074729) and ais.imo_ok("9074729"), "IMO 9074729 passes the check digit")
check(not ais.imo_ok(9074728), "a wrong check digit fails")
check(not ais.imo_ok(0) and not ais.imo_ok("") and not ais.imo_ok(123456) and not ais.imo_ok("IMO9074729"), "0, blank, 6 digits, prefixed fail")

# ---------- static messages ----------
rec = {}
ais.parse_static(rec, "ShipStaticData", {
    "Type": 80, "Name": "ATLANTIC STAR@@@@   ", "ImoNumber": 9074729, "CallSign": "V7AB3  ", "Destination": "FUJAIRAH@@@",
    "Dimension": {"A": 200, "B": 44, "C": 20, "D": 22}, "MaximumStaticDraught": 14.8,
    "Eta": {"Month": 11, "Day": 21, "Hour": 24, "Minute": 60}})
check(rec["type"] == 80 and rec["name"] == "ATLANTIC STAR" and rec["imo"] == "9074729" and rec["cs"] == "V7AB3",
      "ShipStaticData: type, name (padding stripped), IMO, call sign")
check(rec["len"] == 244 and rec["beam"] == 42 and rec["dr"] == 14.8 and rec["dest"] == "FUJAIRAH",
      "ShipStaticData: length, beam, draught, destination")
check(rec["eta"] == "11-21 00:00", "ETA: out-of-range hour and minute (24, 60 = not available) become 00")
rec2 = {}
ais.parse_static(rec2, "ShipStaticData", {"Type": 0, "ImoNumber": 0, "MaximumStaticDraught": 0, "Eta": {"Month": 0, "Day": 0},
                                          "Dimension": {"A": 0, "B": 0, "C": 0, "D": 0}, "Name": "", "Destination": "@@@@"})
check(rec2 == {}, "ShipStaticData with every field 'not available' adds nothing")
rec3 = {}
ais.parse_static(rec3, "StaticDataReport", {"ReportA": {"Valid": True, "Name": "SEA BREEZE"},
                                             "ReportB": {"Valid": True, "ShipType": 37, "CallSign": "SB1",
                                                         "Dimension": {"A": 8, "B": 4, "C": 2, "D": 2}}})
check(rec3 == {"name": "SEA BREEZE", "type": 37, "cs": "SB1", "len": 12, "beam": 4}, "StaticDataReport parts A and B")
rec4 = {}
ais.parse_static(rec4, "StaticDataReport", {"ReportA": {"Valid": False, "Name": "X"}, "ReportB": {"Valid": False, "ShipType": 80}})
check(rec4 == {}, "StaticDataReport parts marked invalid are ignored")


# ---------- websocket: compressed and plain frames ----------
class FakeSock:
    def __init__(self, data):
        self.data, self.sent = data, b""

    def recv(self, n):
        out, self.data = self.data[:n], self.data[n:]
        return out

    def sendall(self, b):
        self.sent += b

    def close(self):
        pass


def frame(payload, op=0x1, fin=True, rsv1=False):
    b0 = (0x80 if fin else 0) | (0x40 if rsv1 else 0) | op
    n = len(payload)
    if n < 126:
        hdr = bytes([b0, n])
    elif n < 65536:
        hdr = bytes([b0, 126]) + struct.pack(">H", n)
    else:
        hdr = bytes([b0, 127]) + struct.pack(">Q", n)
    return hdr + payload


def deflate_stream(msgs):
    """Compress messages the way a server with context takeover does: one compressor, sync-flushed per message."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    out = []
    for m in msgs:
        z = c.compress(m) + c.flush(zlib.Z_SYNC_FLUSH)
        check(z.endswith(b"\x00\x00\xff\xff"), "test setup: sync flush ends with 00 00 ff ff")
        out.append(z[:-4])
    return out


def fake_ws(data, deflate=True, reset=False):
    w = ais.WS.__new__(ais.WS)
    w.s, w.buf, w.wire, w.deflate, w.reset_ctx, w._inflate = FakeSock(data), b"", 0, deflate, reset, zlib.decompressobj(-15)
    return w


m1, m2 = json.dumps({"MessageType": "PositionReport", "n": 1}).encode() * 20, json.dumps({"n": 2}).encode() * 30
z1, z2 = deflate_stream([m1, m2])
w = fake_ws(frame(z1, rsv1=True) + frame(b"", op=0x9) + frame(z2, rsv1=True) + frame(b"plain text") + frame(b"", op=0x8))
check(w.recv() == m1, "compressed message inflated")
check(w.recv() == m2, "second compressed message inflated with the shared context, ping in between answered")
check(w.s.sent[:1] == b"\x8a", "the ping got a pong")
check(w.recv() == b"plain text", "an uncompressed message on a deflate connection passes through")
check(w.recv() is None, "close frame -> None")
check(w.wire > 0 and w.wire < len(m1) + len(m2), "wire bytes counted, smaller than the inflated JSON")
# fragmented compressed message: RSV1 only on the first frame
z = deflate_stream([m1])[0]
w = fake_ws(frame(z[:10], fin=False, rsv1=True) + frame(z[10:], op=0x0))
check(w.recv() == m1, "fragmented compressed message reassembled then inflated")
# no-context-takeover servers: a fresh inflater per message
c1 = zlib.compressobj(9, zlib.DEFLATED, -15)
a = (c1.compress(m1) + c1.flush(zlib.Z_SYNC_FLUSH))[:-4]
c2 = zlib.compressobj(9, zlib.DEFLATED, -15)
b = (c2.compress(m1) + c2.flush(zlib.Z_SYNC_FLUSH))[:-4]
w = fake_ws(frame(a, rsv1=True) + frame(b, rsv1=True), reset=True)
check(w.recv() == m1 and w.recv() == m1, "server_no_context_takeover: each message inflates on its own")
w = fake_ws(frame(z, rsv1=True), deflate=False)
try:
    w.recv()
    check(False, "compressed frame without negotiation raises")
except ConnectionError:
    check(True, "compressed frame without negotiation raises")

# ---------- back-off ----------
bp = os.path.join(TMP, "bo.json")
bo = ais.Backoff(bp)
bo.check(NOW)
check(True, "no back-off state: check passes")
bo.hit(NOW)
try:
    ais.Backoff(bp).check(NOW + dt.timedelta(minutes=9))
    check(False, "within 10 min of a 429: check raises")
except RuntimeError as e:
    check("06:10:00Z" in str(e), "within 10 min of a 429: check raises and names the time")
ais.Backoff(bp).check(NOW + dt.timedelta(minutes=10, seconds=1))
check(True, "after 10 min: check passes")
bo2 = ais.Backoff(bp)
bo2.hit(NOW)
bo2.hit(NOW)
bo2.hit(NOW)
bo2.hit(NOW)
check(json.load(open(bp))["until"] == "2026-11-19T07:00:00Z", "back-off grows 10, 20, 40, then caps at 60 min")
bo2.clear()
check(json.load(open(bp)) == {}, "success clears the back-off")

# ---------- registry ----------
reg = {}
d1, d2, d3 = dt.date(2026, 11, 16), dt.date(2026, 11, 18), dt.date(2026, 11, 19)
ais.learn(reg, {"636012345": {"type": 80, "name": "ATLANTIC STAR", "imo": "9074729", "dr": 9.1, "lat": 25.0, "lon": 56.0},
                "273000001": {"lat": 59.0, "lon": 20.0}}, d1)
check(set(reg) == {"636012345"}, "a ship heard with no static data and no name is not registered")
check(reg["636012345"] == {"first": "2026-11-16", "t": 80, "n": "ATLANTIC STAR", "imo": "9074729", "dr": [[9.1, "2026-11-16"]],
                           "last": "2026-11-16"}, "registry entry: compact keys, first/last day, draught history")
ais.learn(reg, {"636012345": {"dr": 9.2}}, d2)
check(reg["636012345"]["dr"] == [[9.1, "2026-11-16"]] and reg["636012345"]["last"] == "2026-11-18",
      "a draught change under 0.2 m is not a new value; last day still moves")
ais.learn(reg, {"636012345": {"dr": 14.8, "dest": "SIKKA"}}, d3)
check(reg["636012345"]["dr"] == [[9.1, "2026-11-16"], [14.8, "2026-11-19"]] and reg["636012345"]["dest"] == "SIKKA",
      "a 5.7 m draught rise is recorded with its day")
for i in range(6):
    ais.learn(reg, {"636012345": {"dr": 5.0 + i}}, d3)
check(len(reg["636012345"]["dr"]) == 5 and reg["636012345"]["dr"][-1][0] == 10.0, "draught history keeps the last 5")
reg["111111111"] = {"first": "2026-10-01", "n": "OLD", "last": "2026-10-19"}
reg = ais.prune_registry(reg, d3)
check("111111111" not in reg and "636012345" in reg, "entries not heard for over 30 days are pruned")

# ---------- merge: registry fill and tracks ----------
reg = {"636012345": {"t": 80, "n": "ATLANTIC STAR", "imo": "9074729", "dr": [[9.1, "2026-11-16"], [14.8, "2026-11-19"]],
                     "dest": "SIKKA", "last": "2026-11-19"}}


def pos(lat, lon, t):
    return {"lat": lat, "lon": lon, "ts": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "sog": 12.0, "cog": 90.0}


vessels = ais.merge({}, {"636012345": pos(25.0, 56.0, NOW), "273000001": pos(59.0, 20.0, NOW)}, NOW, reg)
v = vessels["636012345"]
check(v["type"] == 80 and v["name"] == "ATLANTIC STAR" and v["imo"] == "9074729" and v["dr"] == 14.8 and v["dest"] == "SIKKA",
      "a position-only sample gets type, name, IMO, newest draught and destination from the registry")
check(v["trk"] == [[56.0, 25.0, "2026-11-19T06:00:00Z"]] and "trk" not in vessels["273000001"],
      "tankers get a track point; untyped ships don't")
t = NOW
for mins in (5, 10, 16, 31, 47):
    t2 = NOW + dt.timedelta(minutes=mins)
    vessels = ais.merge(vessels, {"636012345": pos(25.0, 56.0 + mins / 100.0, t2)}, t2, reg)
check([p[2][11:16] for p in vessels["636012345"]["trk"]] == ["06:00", "06:16", "06:31", "06:47"],
      "track points at least 15 minutes apart")
for k in range(20):
    t2 = NOW + dt.timedelta(minutes=50 + 15 * k)
    vessels = ais.merge(vessels, {"636012345": pos(25.0, 57.0 + k / 100.0, t2)}, t2, reg)
trk = vessels["636012345"]["trk"]
check(len(trk) == 12 and trk[-1][2] == "2026-11-19T11:35:00Z", "track keeps at most 12 points")
check(all(p[2] >= "2026-11-19T08:35:00Z" for p in trk), "track keeps only the last 3 hours")
check("273000001" not in vessels, "ships not heard for 3 hours drop out of the store")

# ---------- counts ----------
vs = {"1": {"lat": 25.0, "lon": 56.0, "ts": "2026-11-19T05:30:00Z", "type": 80, "sog": 11},
      "2": {"lat": 25.1, "lon": 56.1, "ts": "2026-11-19T05:30:00Z", "sog": 0},
      "3": {"lat": 59.0, "lon": 20.0, "ts": "2026-11-19T04:30:00Z", "type": 70}}
c = ais.counts(vs, NOW)
check(c["hormuz"] == {"ships_1h": 2, "underway": 1, "tankers": 1, "cargo": 0, "military": 0, "typed": 1},
      "counts: last hour only, typed share counted")
check(c["baltic"]["ships_1h"] == 0, "counts: a ship last heard over an hour ago is not counted")

# ---------- the ship feed's view: flags, list marks, tanker cards, tracks, cap ----------
from gt import feeds, mid  # noqa: E402
import server  # noqa: E402

LISTED = {"marks": "SG", "lists": ["OFAC", "GUR shadow fleet"], "name": "OLD NAME", "imo": "9074729",
          "url": "https://www.opensanctions.org/entities/vessel-x/"}
feeds.sanctions.lookup = lambda imo=None, mmsi=None: (LISTED if imo == "9074729" else
                                                       dict(LISTED, marks="D", lists=["Tokyo MOU detained"], imo="")
                                                       if str(mmsi) == "538000002" else None)
T = "2026-11-19T05:50:00Z"
vessels = {
    "636012345": {"lat": 26.0, "lon": 56.3, "ts": T, "type": 80, "name": "ATLANTIC STAR", "imo": "9074729", "dr": 14.8, "len": 244,
                  "sog": 12.0, "cog": 90.0, "hdg": 91, "dest": "SIKKA", "eta": "11-21 00:00",
                  "trk": [[56.1, 26.0, "2026-11-19T05:20:00Z"], [56.3, 26.0, T]]},
    "538000002": {"lat": 59.0, "lon": 20.0, "ts": T, "type": 84, "name": "BALTIC TANKER", "sog": 0.2, "trk": [[20.0, 59.0, T]]},
    "273000001": {"lat": 59.1, "lon": 20.1, "ts": T, "type": 70, "name": "CARGO ONE", "sog": 9.0},
    "211000003": {"lat": 59.2, "lon": 20.2, "ts": "2026-11-19T04:00:00Z", "type": 80},  # over an hour old
    "211000004": {"name": "STATIC ONLY", "type": 80},                                   # no position yet
    "211000005": {"lat": 0.0, "lon": 0.0, "ts": T, "type": 80},                         # outside every box
}
reg = {"636012345": {"dr": [[9.1, "2026-11-16"], [14.8, "2026-11-19"]], "t": 80}, "273000001": {"t": 70}}
d = feeds.ships_view(vessels, reg, {"messages": 3}, NOW, ais, mid)
check(d["count"] == 3 and len(d["points"]) == 3, "points: only ships heard in the last hour inside a box")
pt = [p for p in d["points"] if p[6] == 636012345][0]
check(len(pt) == 15 and pt[4] == "tanker" and pt[10] == "LR" and pt[11] == "SG" and pt[12] == "9074729" and pt[13] == 14.8 and pt[14] == 244,
      "point row: class, flag from the MMSI, list marks, IMO, draught, length at indices 4 and 10-14")
check([p for p in d["points"] if p[6] == 273000001][0][10:12] == ["RU", ""], "an unlisted Russian-flag cargo ship: flag RU, no marks")
check([t["mmsi"] for t in d["tankers"]] == [636012345, 538000002], "tanker cards: both tankers heard in the last hour, listed first")
t0 = d["tankers"][0]
check(t0["area"] == "hormuz" and t0["dr_was"] == [9.1, "2026-11-16"] and t0["eta"] == "11-21 00:00" and t0["marks"] == "SG",
      "tanker card: area, previous draught from the registry, ETA, marks")
check(list(d["tracks"]) == ["636012345"] and d["tracks"]["636012345"] == [[56.1, 26.0], [56.3, 26.0]],
      "tracks: only tankers with 2+ points, as [lon, lat]")
ls = {x["mmsi"]: x for x in d["listed"]}
check(set(ls) == {636012345, 538000002}, "listed: both matched ships")
check(ls[636012345]["match"] == "IMO" and ls[636012345]["lists"] == ["OFAC", "GUR shadow fleet"] and ls[636012345]["list_name"] == "OLD NAME",
      "listed: matched on IMO, list labels and the name on the list")
check(ls[538000002]["match"] == "MMSI" and ls[538000002]["marks"] == "D", "listed: MMSI fallback match")
check(d["areas"]["hormuz"]["listed"] == 1 and d["areas"]["baltic"]["listed"] == 0,
      "area counts carry sanctioned or shadow-fleet ships; a detention alone doesn't count")
check(d["areas"]["hormuz"]["no_live_coverage"] is True and d["areas"]["baltic"]["no_live_coverage"] is False,
      "areas flag the boxes with no live receivers")
check(d["areas"]["hormuz"]["bbox"] == [47.5, 22.0, 60.5, 30.6], "areas carry their box as [west, south, east, north]")
check(d["typed_pct"] == 100 and d["registry"] == {"ships": 2, "with_type": 2, "with_imo": 0, "days": 30},
      "typed share and registry stats")
check(set(d["lists"]) == {"attribution", "attribution_url", "licence"}, "the feed carries the vessel-list credit")
check(len(json.dumps(d)) < 6000, "small feed for a handful of ships")

big = {}
for i in range(3200):
    cls_t = 80 if i < 100 else 70 if i < 600 else 37
    big[str(211100000 + i)] = {"lat": 55.0 + (i % 50) * 0.01, "lon": 15.0 + (i // 50) * 0.01, "ts": T, "type": cls_t,
                              "sog": 5.0 if i % 2 else 0.0, "imo": "9074729" if i == 3199 else None}
d2 = feeds.ships_view(big, {}, {}, NOW, ais, mid)
classes = [p[4] for p in d2["points"]]
check(d2["count"] == 3000, "points capped at 3,000")
check(classes.count("tanker") == 100 and classes.count("cargo") == 500, "the cap keeps every tanker and cargo ship")
check(any(p[6] == 211103199 for p in d2["points"]), "the cap keeps listed ships even when they are 'other'")
check(len(d2["tankers"]) == 100, "tanker cards are not capped by the points cap")

ssum = server._listed_summary(d, {"version": "20261119", "licence": "CC BY-NC 4.0"})
check(ssum["heard_1h"] == 2 and ssum["sanctioned_or_shadow_by_area"] == {"hormuz": 1} and ssum["by_mark"] == {"S": 1, "G": 1, "D": 1}
      and ssum["list_version"] == "20261119", "analyst summary of listed ships: marks, sanctioned/shadow by area, list version")
check(len(json.dumps(ssum)) < 2048 and server._listed_summary(d, None) is None, "listed summary is small, None without lists")
check("listed_ships_heard" in server.NON_COMMERCIAL_KEYS and "chokepoint_transits_portwatch" in server.NON_COMMERCIAL_KEYS
      and "ship_traffic_gfw" in server.NON_COMMERCIAL_KEYS, "new non-commercial summary keys are fenced off from trading")
check(feeds.REGISTRY["portwatch"][1] == 6 * 3600 and feeds.REGISTRY["vessellists"][1] == 86400, "new feeds registered")

# ---- 1.5.0 (ais 1.2): worldwide military ships
check(ais.is_military("GOUWE", 35) and ais.is_military("WARSHIP", None) and ais.is_military("GERMAN WARSHIP F224", 0)
      and ais.is_military("HNLMS SCHIEDAM", None) and ais.is_military("DNK NAVY MARIE MILJO", 90), "type 35 or a navy name is military")
check(not ais.is_military("HMS CARGO STAR", 70) and not ais.is_military("JS SHENG", 80) and not ais.is_military("FS YACHT", 37)
      and not ais.is_military("NAVY PIER FERRY", 60) and not ais.is_military("HSBC", None) and not ais.is_military("", None)
      and not ais.is_military("LE MULET COUREAU", None) and not ais.is_military("HS HOOD", None) and ais.is_military("RFA TIDESPRING", None),
      "a navy-looking name on a civilian type, a pleasure craft or a bare word is not military")
check(ais.vessel_class({"name": "FRENCH WARSHIP", "type": None}) == "military" and ais.vessel_class({"type": 80}) == "tanker",
      "vessel_class folds navy names into military")
heard = {"1": {"lat": 59.0, "lon": 20.0, "type": 70},                       # in the Baltic box
         "2": {"lat": 32.7, "lon": -117.9, "name": "WARSHIP"},              # San Diego, military by name
         "3": {"lat": 10.0, "lon": -30.0, "type": 70},                      # mid-Atlantic cargo: dropped
         "4": {"type": 35, "name": "GOUWE", "mpos": [53.0, 4.8]},           # static only, military
         "5": {"type": 80, "mpos": [59.1, 20.1]},                           # static only, inside a box
         "6": {"type": 80, "mpos": [10.0, -30.0]},                          # static only, outside: dropped
         "7": {"lat": 10.0, "lon": -30.0},                                  # military by the registry's type
         "8": {"lat": 11.0, "lon": -31.0}}                                  # already stored: kept
kept, far = ais.keep(heard, {"8": {}}, {"7": {"t": 35}})
check(sorted(kept) == ["1", "2", "4", "5", "7", "8"] and far == 3, "keep(): boxes, military anywhere, stored ships; %s %s" % (sorted(kept), far))
check(all("mpos" not in r for r in kept.values()), "keep() drops the MetaData position before the merge")
T3 = (NOW - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
vm = {"366000001": {"lat": 32.7, "lon": -117.9, "ts": T3, "name": "WARSHIP", "sog": 12.0},      # 2 h old, outside every box
      "211211490": {"lat": 54.35, "lon": 10.14, "ts": T, "name": "GERMAN WARSHIP", "type": 35},  # in the Baltic box
      "273000009": {"lat": 10.0, "lon": -30.0, "ts": T, "type": 70},                            # outside, civilian: not shown
      "227000001": {"lat": 43.1, "lon": 5.9, "ts": (NOW - dt.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"), "type": 35}}
dm = feeds.ships_view(vm, {}, {}, NOW, ais, mid)
check(sorted(p[6] for p in dm["points"]) == [211211490, 366000001] and all(p[4] == "military" for p in dm["points"]),
      "military ships anywhere within 3 h are points; a civilian ship outside the boxes and a 4 h old warship are not")
mc = {c["mmsi"]: c for c in dm["military"]}
check(set(mc) == {211211490, 366000001} and mc[366000001]["area"] is None and mc[211211490]["area"] == "baltic"
      and mc[366000001]["flag"] == "US" and dm["military_by_flag"] == {"DE": 1, "US": 1}, "military cards: area, flag, count by flag")
check(mc[366000001]["theatre"] == "americas" and dm["areas"]["baltic"]["military"] == 1, "military card theatre; box count")

print("%d checks passed" % ok)
