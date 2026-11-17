#!/usr/bin/env python3
"""Ground Truth container supervisor (the image's entrypoint). Version 1.0, 2026-11-15.

* Runs the app: python $GT_APP/server.py (code bind-mounted read-only from the host).
* Hot deploy: when $GT_APP/VERSION changes, the app is restarted on the new code. Publish a new
  version by copying the code first and writing VERSION LAST, so a half-copied tree never starts.
* Restarts the app if it exits, with exponential back-off (2 s .. 60 s) so a bad version can't spin.
* First start: if $GT_DATA is empty and $GT_SEED exists, copies the seed archive in (one time,
  marked by $GT_DATA/.seeded).
"""
import os
import shutil
import signal
import subprocess
import sys
import time

APP = os.environ.get("GT_APP", "/app")
DATA = os.environ.get("GT_DATA", "/data")
SEED = os.environ.get("GT_SEED", "/seed")
POLL = float(os.environ.get("GT_SUPERVISE_POLL", "5"))
SUPERVISOR_VERSION = "1.0"


def log(msg):
    print("[supervise %s] %s %s" % (SUPERVISOR_VERSION, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg),
          flush=True)


def read_version():
    try:
        with open(os.path.join(APP, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def seed():
    os.makedirs(DATA, exist_ok=True)
    marker = os.path.join(DATA, ".seeded")
    if os.path.exists(marker) or not os.path.isdir(SEED):
        return
    if [n for n in os.listdir(DATA) if not n.startswith(".")]:
        log("data folder already has content; not seeding")
    else:
        shutil.copytree(SEED, DATA, dirs_exist_ok=True)
        log("seeded %s from %s" % (DATA, SEED))
    with open(marker, "w") as fh:
        fh.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")


def start():
    log("starting app version %s" % read_version())
    return subprocess.Popen([sys.executable, os.path.join(APP, "server.py")], cwd=APP)


def stop(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main():
    seed()
    version = read_version()
    proc = start()
    started = time.time()
    backoff = 2.0

    def on_term(signum, _frame):
        log("signal %d: stopping" % signum)
        stop(proc)
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    while True:
        time.sleep(POLL)
        if proc.poll() is not None:
            log("app exited with code %s after %.0f s" % (proc.returncode, time.time() - started))
            if time.time() - started > 120:
                backoff = 2.0
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
            version = read_version()
            proc, started = start(), time.time()
            continue
        current = read_version()
        if current and current != version:
            time.sleep(3)  # let the rest of a copy settle, then re-read
            current = read_version()
            if current and current != version:
                log("VERSION %s -> %s: restarting on the new code" % (version, current))
                stop(proc)
                version = current
                proc, started, backoff = start(), time.time(), 2.0


if __name__ == "__main__":
    main()
