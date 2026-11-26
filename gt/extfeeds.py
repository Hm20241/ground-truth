"""Feed modules switched on per release (1.0, Ground Truth 0.11.0).

From 0.11.0 each new source family is its own module (gt/geoconfirmed.py, gt/curated.py, ...) that exposes
  FEEDS = {"<name>": (callable, every_seconds)}      names are [a-z]+ (the /api/feed/<name> route)
  PUBLIC_OK, NON_COMMERCIAL                          a bool, or a {feed: bool} dict
and nothing else is needed to schedule it: load() adds the enabled modules' feeds to feeds.REGISTRY. A module
that fails to import, or a feed whose name clashes, is skipped and reported in /api/status ("modules"), so one bad
module never stops the server.

ENABLED is what this release ships. GT_EXT_FEEDS (comma list, or "all") overrides it for local test runs.
PUBLIC_OK only describes the source's terms; the public static mirror copies a fixed endpoint list
(~/Projects/gt-public/live/publish_live.py), so a feed reaches it only when that list names it.
"""
import importlib
import os
import re

ALL = ("geoconfirmed", "curated", "hazards", "wire", "telegram", "signals", "airspace", "cyber", "services", "disruption", "airnow")
ENABLED = ("geoconfirmed", "curated", "hazards",  # 0.11.0: Phase A (verified pins, natural hazards)
           "wire", "telegram",  # 0.12.0: Phase B (news wire, Telegram)
           "signals", "airspace", "cyber",  # 0.13.0: Phase C (strategic signals, airspace, cyber and routing)
           "services", "disruption",  # 1.5.3: outage layers (websites, AI / cloud, power, cell networks)
           "airnow")  # 1.7.2: EPA AirNow air-quality monitors
META = {}     # feed -> {"module", "version", "every", "public_ok", "non_commercial"}
ERRORS = {}   # module or module:feed -> reason


def _flag(mod, attr, feed):
    v = getattr(mod, attr, False)
    return bool(v.get(feed, False)) if isinstance(v, dict) else bool(v)


def enabled():
    env = (os.environ.get("GT_EXT_FEEDS") or "").strip()
    if env == "all":
        return ALL
    if env:
        return tuple(m.strip() for m in env.split(",") if m.strip() in ALL)
    return ENABLED


def load(registry):
    for m in enabled():
        try:
            mod = importlib.import_module("gt." + m)
        except Exception as e:  # noqa: BLE001  a broken module is reported, not fatal
            ERRORS[m] = "%s: %s" % (type(e).__name__, str(e)[:200])
            continue
        for feed, (fn, every) in (getattr(mod, "FEEDS", None) or {}).items():
            if not re.fullmatch(r"[a-z]+", feed) or feed in registry:
                ERRORS["%s:%s" % (m, feed)] = "feed name invalid or already registered"
                continue
            registry[feed] = (fn, int(every))
            META[feed] = {"module": m, "version": getattr(mod, "VERSION", None), "every": int(every),
                          "public_ok": _flag(mod, "PUBLIC_OK", feed), "non_commercial": _flag(mod, "NON_COMMERCIAL", feed)}
    return META


def status():
    return {"enabled": list(enabled()), "feeds": META, "errors": ERRORS}
