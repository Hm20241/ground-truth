"""Analyst results store, v1.0 (2026-11-15).

The analyst runner (analyst/analyst.py) posts two kinds of results:
  * per-event notes   POST /api/analysis/events   {"run": {...}, "items": [{"id": ..., ...}, ...]}
  * the whole picture POST /api/analysis/picture  {"run": {...}, "picture": {...}}
Both need the header X-GT-Token. The token comes from $GT_ANALYST_TOKEN, else the file
$GT_SEED/analyst.token (the read-only seed mount, so it can be set without recreating the container),
else $GT_DATA/analyst.token (local runs). With no token configured, every write is refused.

The store is shape-agnostic: it keeps whatever fields the runner's schema produces, clipped to sane
sizes. Everything here is model output derived from untrusted posts, so it is data only: the page
escapes it before display and nothing on the server ever interprets it.
"""
import hmac
import json
import os
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
ADIR = os.path.join(DATA, "analysis")
PDIR = os.path.join(ADIR, "pictures")
LOCK = threading.Lock()
MAX_BODY = 2000000
HISTORY_KEEP = 500
RUNS_KEEP = 200
STORE_VERSION = "1.0"


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def token():
    t = (os.environ.get("GT_ANALYST_TOKEN") or "").strip()
    if t:
        return t
    for p in (os.path.join(os.environ.get("GT_SEED") or "/seed", "analyst.token"), os.path.join(DATA, "analyst.token")):
        try:
            with open(p, encoding="utf-8") as fh:
                t = fh.read().strip()
            if t:
                return t
        except OSError:
            pass
    return ""


def authorized(header_value):
    t = token()
    return bool(t) and hmac.compare_digest(t.encode(), (header_value or "").strip().encode())


def _clip(v, depth=0):
    """Bound the size of anything we store: strings 1200 chars, lists 25 items, dicts 40 keys, depth 6."""
    if depth > 6:
        return None
    if isinstance(v, str):
        return v[:1200]
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, list):
        return [_clip(x, depth + 1) for x in v[:25]]
    if isinstance(v, dict):
        return {str(k)[:60]: _clip(x, depth + 1) for k, x in list(v.items())[:40]}
    return str(v)[:200]


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _log_run(kind, run, n):
    runs = _read(os.path.join(ADIR, "runs.json"), [])
    r = _clip(run if isinstance(run, dict) else {})
    r.update({"kind": kind, "n": n, "stored_at": _now()})
    runs.append(r)
    _write(os.path.join(ADIR, "runs.json"), runs[-RUNS_KEEP:])


def merge_events(items, run):
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    with LOCK:
        store = _read(os.path.join(ADIR, "events.json"), {})
        n = 0
        for it in items[:200]:
            if not isinstance(it, dict) or not isinstance(it.get("id"), str) or not 0 < len(it["id"]) <= 40:
                continue
            rec = _clip(it)
            rec["analyzed_at"] = _now()
            if isinstance(run, dict):
                rec["model"] = str(run.get("model") or "")[:60]
                rec["prompt_version"] = str(run.get("prompt_version") or "")[:20]
            store[it["id"]] = rec
            n += 1
        if not n:
            raise ValueError("no valid items")
        _write(os.path.join(ADIR, "events.json"), store)
        _log_run("events", run, n)
    return {"ok": True, "stored": n, "total": len(store)}


def store_picture(pic, run):
    if not isinstance(pic, dict) or not pic.get("headline"):
        raise ValueError("picture must be an object with a headline")
    rec = _clip(pic)
    rec["generated_at"] = _now()
    if isinstance(run, dict):
        rec["model"] = str(run.get("model") or "")[:60]
        rec["prompt_version"] = str(run.get("prompt_version") or "")[:20]
        rec["events_considered"] = run.get("events_considered")
    with LOCK:
        _write(os.path.join(ADIR, "picture_latest.json"), rec)
        _write(os.path.join(PDIR, rec["generated_at"].replace(":", "") + ".json"), rec)
        files = sorted(f for f in os.listdir(PDIR) if f.endswith(".json"))
        for f in files[:-HISTORY_KEEP]:
            try:
                os.remove(os.path.join(PDIR, f))
            except OSError:
                pass
        _log_run("picture", run, 1)
    return {"ok": True, "generated_at": rec["generated_at"]}


def events():
    return _read(os.path.join(ADIR, "events.json"), {})


def picture():
    return _read(os.path.join(ADIR, "picture_latest.json"), None)


def headline():
    """Compact view for /api/summary (Home Assistant, the trading agent later)."""
    p = picture()
    if not p:
        return None
    return {k: p.get(k) for k in ("headline", "overall_tension", "trend", "confidence", "generated_at")}


def overview():
    runs = _read(os.path.join(ADIR, "runs.json"), [])
    return {"store_version": STORE_VERSION, "picture": picture(), "events_analyzed": len(events()),
            "writes_enabled": bool(token()), "runs": runs[-12:][::-1]}


def history(limit=48, full=False):
    try:
        files = sorted((f for f in os.listdir(PDIR) if f.endswith(".json")), reverse=True)[:max(1, min(limit, HISTORY_KEEP))]
    except OSError:
        return []
    out = []
    for f in files:
        p = _read(os.path.join(PDIR, f), None)
        if not p:
            continue
        if full:
            out.append(p)
        else:
            out.append({k: p.get(k) for k in ("generated_at", "headline", "overall_tension", "trend", "confidence")})
    return out
