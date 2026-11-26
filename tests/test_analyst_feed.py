"""Offline tests for analyst 1.6 (GT 1.7.3): a 15-minute tick, and the Feed makes a new picture due."""
import importlib.util, pathlib, sys, time, calendar
ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("analyst", ROOT / "analyst" / "analyst.py")
A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
n = bad = 0
def check(ok, what):
    global n, bad
    n += 1
    if not ok:
        bad += 1; print("FAIL:", what)
A.log = lambda m: None
now = time.time()
def iso(t): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
state = {}
def fake_get(path, timeout=30):
    if path == "analysis": return {"picture": {"generated_at": iso(state["pic"])} if state.get("pic") else None}
    if path == "analysis/events": return {str(k): {"analyzed_at": iso(t)} for k, t in enumerate(state.get("notes", []))}
    if path.startswith("feed/"):
        v = state.get(path)
        if isinstance(v, Exception): raise v
        return {"data": {"items": [{"ts_ms": t * 1000} for t in (v or [])]}}
    raise ValueError(path)
A.api_get = fake_get
check(A.ANALYST_VERSION == "1.6", "version 1.6")
check(A.CFG["picture_min_gap_min"] == 14 and A.CFG["picture_feed_trigger"] == 5 and A.CFG["picture_every_h"] == 3.0, "defaults")
plists = sorted((ROOT / "analyst" / "launchd").glob("*gt-analyst.plist"))  # absent in the public copy
check(not plists or "<integer>900</integer>" in plists[0].read_text(), "launchd tick is 15 minutes")
state.clear(); check(A.picture_due()[0] is True, "no picture yet: due")
state.update(pic=now - 20 * 60, **{"feed/wire": [now - 60, now - 120, now - 180], "feed/telegram": [now - 30, now - 90]})
due, why = A.picture_due(); check(due and "5 new Feed items" in why, "5 new Feed items after 20 min: due (%s)" % why)
state["feed/telegram"] = [now - 30]
due, why = A.picture_due(); check(not due and "4 new Feed items" in why, "4 new items: not due (%s)" % why)
state.update(pic=now - 10 * 60, **{"feed/telegram": [now - 30, now - 90, now - 95]})
check(A.picture_due()[0] is False, "inside the 14-minute gap: not due, whatever the Feed did")
state.update(pic=now - 20 * 60, **{"feed/wire": [now - 3600] * 9, "feed/telegram": [now - 7200] * 9})
check(A.picture_due()[0] is False, "items older than the picture do not count")
state.update(**{"feed/wire": [now + 3600] * 9, "feed/telegram": []})
check(A.picture_due()[0] is False, "items stamped in the future do not count")
state.update(**{"feed/wire": OSError("down"), "feed/telegram": [now - 1] * 5})
check(A.picture_due()[0] is True, "one unreadable feed does not block the other")
state.update(**{"feed/wire": OSError("down"), "feed/telegram": ValueError("bad")})
check(A.picture_due()[0] is False, "both feeds unreadable: not due, no crash")
A.CFG["picture_feed_trigger"] = 0; state.update(**{"feed/wire": [now - 1] * 50, "feed/telegram": []})
check(A.picture_due()[0] is False, "trigger 0 turns the Feed rule off")
A.CFG["picture_feed_trigger"] = 5
state.update(pic=now - 4 * 3600); check(A.picture_due()[0] is True, "3-hour rule still applies")
state.update(pic=now - 20 * 60, notes=[now - 60] * 15, **{"feed/wire": [], "feed/telegram": []})
check(A.picture_due()[0] is True, "15 newly analysed events still make it due")
print("test_analyst_feed: %d checks, %d failed" % (n, bad)); sys.exit(1 if bad else 0)
