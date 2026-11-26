#!/usr/bin/env python3
"""Serve this checkout's web/ against a running instance's API, read-only. v1.2, 2026-11-24 (1.2: GT_WEB picks the folder served).

A page change can be tried on the real data before it is deployed, without running any feed locally (no third-party
calls, no Firecrawl or AISStream use). Static files come from web/; every GET under /api/ is passed to
GT_UPSTREAM (default http://127.0.0.1:8790/), /api/stream included (server-sent events, streamed line by line).
Anything but GET/HEAD is refused. Listens on 127.0.0.1 only, port GT_PORT (default 8793).
1.1: the path is decoded and normalised before it is checked (so %2e%2e cannot climb out of /api/), and redirects
are not followed, so a request can only ever reach GT_UPSTREAM + api/...

  python3 -I tools/live_proxy.py
"""
import http.server
import os
import posixpath
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.environ.get("GT_WEB") or os.path.join(ROOT, "web")  # 1.2: GT_WEB serves another copy of web/ (design prototypes)
UPSTREAM = os.environ.get("GT_UPSTREAM", "http://127.0.0.1:8790/").rstrip("/") + "/"
PORT = int(os.environ.get("GT_PORT", "8793"))
PASS_HEADERS = ("Content-Type", "Cache-Control", "ETag", "Last-Modified")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None  # a 3xx comes back to the page as it is


OPENER = urllib.request.build_opener(NoRedirect)


def upstream_path(raw):
    """"api/feed/wire?x=1" for a safe request path, else None."""
    path, _, query = raw.partition("?")
    clean = posixpath.normpath(urllib.parse.unquote(path))
    if not clean.startswith("/api/") or "\\" in clean or any(ord(c) < 32 for c in clean):
        return None
    return urllib.parse.quote(clean.lstrip("/")) + ("?" + query if query else "")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):
        if not self.path.startswith("/api/"):
            return
        sys.stderr.write("%s %s\n" % (self.command, self.path[:120]))

    def do_GET(self):
        if not self.path.startswith("/api/"):
            return super().do_GET()
        path = upstream_path(self.path)
        if not path:
            return self.send_error(400)
        req = urllib.request.Request(UPSTREAM + path, headers={"User-Agent": "gt-live-proxy/1.1"})
        if self.headers.get("If-None-Match"):
            req.add_header("If-None-Match", self.headers["If-None-Match"])
        try:
            up = OPENER.open(req, timeout=3600 if path.startswith("api/stream") else 60)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        except OSError as e:
            return self.send_error(502, str(e)[:80])
        with up:
            self.send_response(up.status)
            for h in PASS_HEADERS:
                if up.headers.get(h):
                    self.send_header(h, up.headers[h])
            if (up.headers.get("Content-Type") or "").startswith("text/event-stream"):
                self.end_headers()
                try:
                    for line in up:
                        self.wfile.write(line)
                        self.wfile.flush()
                except OSError:
                    pass
                return
            body = up.read()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _refuse(self):
        self.send_error(405)

    do_POST = do_PUT = do_DELETE = do_PATCH = _refuse


if __name__ == "__main__":
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print("Ground Truth web/ on http://127.0.0.1:%d, API from %s (read-only)" % (PORT, UPSTREAM), flush=True)
    srv.serve_forever()
