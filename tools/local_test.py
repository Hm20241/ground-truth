#!/usr/bin/env python3
"""Run Ground Truth locally on a throwaway copy of data/, with Firecrawl switched off. v1.2, 2026-11-19.

The production instance is the one that polls Firecrawl (free tier, capped per source per day), so local test runs
must not spend its credits. This copies data/ to a temp folder, makes every Firecrawl call fail fast
(UKMTO and CENTCOM then keep whatever their caches hold), and serves on GT_PORT (default 8791).
Every other feed is fetched live. Stop it with Ctrl-C; the temp copy is deleted on exit.

1.1: AISStream refuses a second connection from the same account or address (HTTP 429), and the production
instance samples for 60 s every 5 minutes. So local AIS samples first wait until its ship feed is idle (read from
GT_PROD_STATUS, its /api/status URL) and then listen for 40 s (GT_LOCAL_AIS=gap, the default).
GT_LOCAL_AIS=off makes the ship feed fail fast instead.
1.2: the status URL comes from GT_PROD_STATUS; an empty one skips the wait.

  python3 tools/local_test.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(prefix="gt-test-")
shutil.copytree(os.path.join(ROOT, "data"), os.path.join(tmp, "data"))
os.environ["GT_DATA"] = os.path.join(tmp, "data")
os.environ.setdefault("GT_PORT", "8791")
os.environ["GT_SEED"] = os.path.join(tmp, "no-seed")  # never read container seed files
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from gt import feeds  # noqa: E402


def _no_firecrawl(url, tag, max_age_s=3600):
    raise RuntimeError("Firecrawl is off in local tests (tools/local_test.py)")


feeds.firecrawl_markdown = _no_firecrawl

from gt import ais  # noqa: E402

_real_sample = ais.sample
PROD_STATUS = os.environ.get("GT_PROD_STATUS", "")


def _gap_sample(seconds=ais.SAMPLE_S, boxes=None):
    import json, time, urllib.request
    if os.environ.get("GT_LOCAL_AIS", "gap") == "off":
        raise RuntimeError("AIS is off in this local test (GT_LOCAL_AIS=off)")
    for _ in range(80 if PROD_STATUS else 0):  # up to ~6 min
        try:
            f = json.load(urllib.request.urlopen(PROD_STATUS, timeout=10))["feeds"]["ships"]
            if not f.get("running") and (f.get("age_s") or 999) < 180:
                break
        except Exception:
            pass
        time.sleep(5)
    return _real_sample(40, boxes)


ais.sample = _gap_sample
print("local test: data copy in %s, port %s, Firecrawl off" % (tmp, os.environ["GT_PORT"]), flush=True)
try:
    import server
    server.main()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
