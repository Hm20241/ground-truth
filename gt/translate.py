"""English translations of non-English Feed items. v1.1, 2026-11-21 (Ground Truth 1.5.0; 1.1, 1.5.3: the `power`
feed too, for Ukrenergo and the Ministry of Energy, which post in Ukrainian).

Asked for: "if a feed item is in another language please translate to english". The server does not translate.
A scheduled job (`analyst/analyst.py translate`, every 5 min, on the analyst's machine) reads feed/telegram
and feed/wire, sends the items whose `lang` is not "en" and which carry no translation yet to Claude Haiku (no
tools, structured output, the same tool-less call as the analyst) and POSTs the English to /api/translations with
the analyst's write token. (Google's free translate endpoint answered HTTP 429 to the first request on 2026-11-21,
so it is not used.)

This module keeps the translations (CACHE/translations.json, 7 days, at most MAX entries, keyed by the item id) and
folds them into those two feeds when they are served: title and summary become the English text, the originals move
to title_orig / summary_orig, `translated` = {"from": lang, "by": model}, and the category is worked out again from
the English title (the keyword classifier only reads English). Items without a translation are served as they are.

Everything posted is untrusted model output: ids, language codes and model names must match tight patterns, text is
cut to TITLE_MAX / SUMMARY_MAX and stripped of control characters, and at most MAX_POST items are taken per POST.
The page escapes all of it. Same terms as the feeds it translates: PUBLIC_OK False, NON_COMMERCIAL True.
"""
import json
import os
import re
import threading
import time

from . import mymaps, wire

VERSION = "1.1"
FEEDS = ("wire", "telegram", "power")
RECLASSIFY = ("wire", "telegram")   # 1.1: only these get their category worked out again from the English
KEEP_S = 7 * 86400
MAX = 6000
MAX_POST = 200
TITLE_MAX = 300
SUMMARY_MAX = 400
FILE = "translations.json"   # in wire.CACHE (the feeds' cache folder)
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_LANG = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")
_MODEL = re.compile(r"^[A-Za-z0-9_.:-]{1,48}$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LOCK = threading.Lock()
_STORE = None   # {id: {"t": title, "s": summary or None, "from": lang, "by": model, "at": epoch s}}


def _path():
    return os.path.join(wire.CACHE, FILE)


def _load():
    global _STORE
    if _STORE is None:
        try:
            d = json.load(open(_path(), encoding="utf-8"))
            _STORE = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            _STORE = {}
    return _STORE


def _save(st):
    os.makedirs(wire.CACHE, exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, _path())


def _text(v, n):
    if not isinstance(v, str):
        return None
    v = _CTRL.sub("", v).strip()
    return wire.cut(v, n) if v else None


def store(items, run=None, now=None):
    """POST /api/translations body -> {"stored", "rejected", "total"}. Raises ValueError on a malformed body."""
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    now = time.time() if now is None else now
    by = (run or {}).get("model") if isinstance(run, dict) else None
    by = by if isinstance(by, str) and _MODEL.match(by) else "model"
    ok = bad = 0
    with _LOCK:
        st = _load()
        for it in items[:MAX_POST]:
            if not isinstance(it, dict):
                bad += 1
                continue
            iid, lang = it.get("id"), it.get("from")
            title = _text(it.get("title"), TITLE_MAX)
            if not (isinstance(iid, str) and _ID.match(iid) and isinstance(lang, str) and _LANG.match(lang) and title):
                bad += 1
                continue
            st[iid] = {"t": title, "s": _text(it.get("summary"), SUMMARY_MAX), "from": lang, "by": by, "at": int(now)}
            ok += 1
        bad += max(0, len(items) - MAX_POST)
        cutoff = now - KEEP_S
        for k in [k for k, v in st.items() if not isinstance(v, dict) or (v.get("at") or 0) < cutoff]:
            del st[k]
        if len(st) > MAX:
            for k in sorted(st, key=lambda k: st[k].get("at") or 0)[:len(st) - MAX]:
                del st[k]
        if ok:
            _save(st)
        return {"stored": ok, "rejected": bad, "total": len(st)}


def apply(data, feed=None):
    """A feed's data dict -> the same with its translated items in English (a copy; the cached result is untouched).
    1.1: `feed` names the feed; outside RECLASSIFY an item keeps its own category and tags (the power feed's tags,
    such as "emergency" or "schedule", are not the keyword classifier's)."""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return data
    with _LOCK:
        st = dict(_load())
    if not st:
        return data
    out, n = [], 0
    for it in data["items"]:
        tr = st.get(it.get("id")) if isinstance(it, dict) else None
        if not tr or (it.get("lang") or "en") == "en":
            out.append(it)
            continue
        cat, tags = mymaps.classify(tr["t"], None)
        new = dict(it, title=tr["t"], title_orig=it.get("title"), translated={"from": tr.get("from") or it.get("lang"),
                                                                               "by": tr.get("by") or "model"})
        if (feed is None or feed in RECLASSIFY) and (cat != "other" or it.get("category") in (None, "other")):
            new["category"], new["tags"] = cat, tags
        if it.get("summary"):
            new["summary_orig"] = it["summary"]
            new["summary"] = tr.get("s") or it["summary"]
        out.append(new)
        n += 1
    return dict(data, items=out, translated=n)


def stats():
    with _LOCK:
        st = _load()
        return {"version": VERSION, "kept": len(st), "newest": max((v.get("at") or 0 for v in st.values()), default=None)}
