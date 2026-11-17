#!/usr/bin/env python3
"""Run Ground Truth locally on a throwaway copy of data/, with Firecrawl switched off. v1.0, 2026-11-16.

The production instance is the one that polls Firecrawl (free tier, capped per source per day), so local test runs
must not spend its credits. This copies data/ to a temp folder, makes every Firecrawl call fail fast
(UKMTO and CENTCOM then keep whatever their caches hold), and serves on GT_PORT (default 8791).
Every other feed is fetched live. Stop it with Ctrl-C; the temp copy is deleted on exit.

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
print("local test: data copy in %s, port %s, Firecrawl off" % (tmp, os.environ["GT_PORT"]), flush=True)
try:
    import server
    server.main()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
