"""Offline tests for the 1.7.3 audit fixes in the feed modules: gt/airspace.py (squawk, tfr), gt/disruption.py
(conditional requests), gt/services.py and gt/cyber.py (the payload trim loops). Never touches the network.

Run: python3 -I tests/test_173_feeds.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "airspace")
os.environ["GT_DATA"] = tempfile.mkdtemp(prefix="gt-173-")
os.environ["GT_SEED"] = os.path.join(os.environ["GT_DATA"], "no-seed")
sys.path.insert(0, PROJ)
from gt import airspace as A, cyber, disruption as D, feeds, services as S  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


feeds.get = no_network
A._sleep = lambda s: None
NOW = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)

# ---- squawk: one malformed aircraft is skipped, the rest of the poll is kept
good = {"hex": "abc123", "flight": "TEST1", "lat": 50.0, "lon": 8.0, "seen": 1, "seen_pos": 1, "squawk": "7700"}
bad = {"hex": "def456", "flight": "TEST2", "lat": "n/a", "lon": 8.0, "squawk": "7700"}


def sqk(url):
    code = url.rsplit("/", 1)[1]
    return json.dumps({"now": int(NOW.timestamp() * 1000), "ac": [bad, good] if code == "7700" else []}).encode()


try:
    d = A.squawk(now=NOW, fetch=sqk)
    check([i["hex"] for i in d["items"]] == ["abc123"], "squawk: a malformed aircraft is skipped, the good one is kept")
except ValueError as e:
    check(False, "squawk: one malformed aircraft fails the whole feed (%s)" % e)

# ---- tfr: an empty list after a full one is a fault, not "no TFRs"
TFR = {A.TFR_LIST: open(os.path.join(FX, "tfr_list.json"), "rb").read(), A.TFR_WFS: open(os.path.join(FX, "tfr_wfs.json"), "rb").read()}


def tfr_fetch(lst=None):
    def fetch(url):
        if url in TFR:
            return lst if (url == A.TFR_LIST and lst is not None) else TFR[url]
        return open(os.path.join(FX, "tfr_detail_6_0001.xml"), "rb").read()
    return fetch


r1 = A.tfr(now=NOW, fetch=tfr_fetch())
cached = len(json.load(open(A._path("tfr")))["details"])
r2 = A.tfr(now=NOW + dt.timedelta(minutes=15), fetch=tfr_fetch(lst=b"[]"))
check(r1["count"] > 0 and r2["count"] == r1["count"] and r2["sources"][0]["ok"] is False
      and "empty" in (r2["sources"][0]["error"] or ""), "tfr: an empty FAA list keeps the last good list and says so")
check(len(json.load(open(A._path("tfr")))["details"]) == cached > 0, "tfr: the NOTAM detail cache survives an empty list")

# ---- disruption: a body the handler refuses must not come back as a 304 "ok" on the next poll
name = "taipower"
calls = []
script = [(200, {"ETag": '"A"'}, b"good"), (200, {"ETag": '"B"'}, b"junk"), None]


def handler(fetch, nt, s, st):
    body = D._body("https://example.invalid/x", s, fetch)
    if body == b"junk":
        raise ValueError("unreadable body")
    return {"v": 1} if body is not None else s.get("data")


def fetch(url, hdr):
    calls.append(dict(hdr))
    step = script[len(calls) - 1]
    if step is None:  # third poll: the origin still serves the junk body, tagged "B"
        return (304, {}, b"") if hdr.get("If-None-Match") == '"B"' else (200, {"ETag": '"B"'}, b"junk")
    return step


real = D.HANDLERS[name]
D.HANDLERS[name] = handler
st, every = {}, D.SOURCES[name][2]
for i in range(3):
    D._poll([name], 1000000 + i * 2 * every, fetch, lambda: 0.0, st)
D.HANDLERS[name] = real
s = st["sources"][name]
check(calls[1].get("If-None-Match") == '"A"', "disruption: a good body's ETag is sent on the next poll")
check("If-None-Match" not in calls[2] and s["ok"] is False and "unreadable" in (s["error"] or ""),
      "disruption: after a refused body the next poll is unconditional and the source stays failed (was 304 -> ok)")

# ---- services / cyber: the payload trim loop ends when one oversized item is all that is left


def finishes(fn, what):
    out = {}
    t = threading.Thread(target=lambda: out.update(r=fn()), daemon=True)
    t.start()
    t.join(5)
    check(not t.is_alive(), what)


big = "x" * 4000
real_cap, real_max = S._cap, S.MAX_BYTES
S.MAX_BYTES = 1000


def svc_loop():
    out = {"items": [{"active": True, "kind": "incident", "ts_ms": 1, "t": big}], "trimmed": 0}
    while out["items"] and len(json.dumps(out)) > S.MAX_BYTES:  # the loop at the end of services.build()
        keep, extra = S._cap(out["items"], max(1, len(out["items"]) * 9 // 10), budget=10 ** 12)
        if not extra:
            break
        out.update(items=keep)
    return out


finishes(svc_loop, "services: the trim loop's stop condition holds for one oversized item")
S.MAX_BYTES = real_max
src = open(os.path.join(PROJ, "gt", "services.py")).read() + open(os.path.join(PROJ, "gt", "cyber.py")).read()
check(src.count("if not extra:  # 1.7.3") == 2, "services.build and cyber.cyber both stop when nothing more can be dropped")
k, e = S._cap([{"active": True, "kind": "incident", "ts_ms": 1}], 1, budget=10 ** 12)
k2, e2 = cyber._cap([{"kind": "kev", "ts_ms": 1, "t": "x" * (cyber.MAX_BYTES + 10)}], 1)
check(e == 0 and len(k) == 1, "services._cap never drops below max_items, so the caller must stop itself")
check(len(k2) + e2 == 1, "cyber._cap accounts for every item")
print("%d checks passed" % ok)
