"""Live ship positions from AISStream.io (free key), sampled in short bursts. v1.1, 2026-11-19 (Ground Truth 0.9.0).

AISStream is a websocket feed. The standard library has no websocket client and the runtime image holds
only Python, so this module speaks just enough RFC 6455 (TLS, handshake, framing, ping/pong) to read it.

Each run connects, subscribes to the watch boxes, listens for SAMPLE_S seconds and merges what it heard
into cache/ais_vessels.json (last position per ship, kept KEEP_H hours). A ship at anchor reports every
3 minutes and one under way every 2-10 s, so a 60 s sample every 5 minutes sees nearly every ship within
the hour. Coverage is terrestrial receivers run by volunteers: thin far offshore, so absence is not proof.

1.1 (0.9.0):
* Vessel registry (cache/ais_registry.json, 30 days per ship): type, name, IMO, call sign, size, destination,
  ETA and the last 5 draught values. A ship sends its type only every ~6 minutes, which a 60 s sample often
  misses; with the registry a ship heard once keeps its type for a month. Class B ships' type and name now come
  from StaticDataReport too.
* permessage-deflate (RFC 7692). Since Sept 2026 AISStream caps uncompressed connections per user and drops the
  excess silently. The subscription is sent uncompressed (allowed); server messages are inflated with zlib.
* HTTP 429 at the handshake starts a back-off (10, 20, 40, 60 min) instead of retrying every 5 minutes.
* Short tracks for tankers: one point per 15 minutes, last 3 hours, at most 12 points.
* Four more watch boxes on tanker routes: Singapore/Malacca, Gibraltar, the Dover Strait and the US Gulf coast.
  Measured 2026-11-19 in one 60 s sample: 38, 18, 10 and 65 ships (volunteer coverage there is thin), against
  204 in the Baltic in 25 s, so they add little load. Port Said and the northern Suez approach were already inside
  east_med and red_sea.
* AISStream answered HTTP 429 to a second connection from the same account while another instance was connected (2026-11-19),
  so in practice one connection at a time, not the three its docs mention. Test runs must sample in the production instance's gap.

The key is read from $AISSTREAM_API_KEY, else $GT_SEED/aisstream.key (container), else
~/.config/aisstream/key (the Mac). It is never logged.
"""
import base64
import datetime as dt
import json
import os
import socket
import ssl
import struct
import time
import zlib

HOST, PATH = "stream.aisstream.io", "/v0/stream"
SAMPLE_S = 60
KEEP_H = 3
MAX_MSGS = 60000  # safety stop for one sample
REG_DAYS = 30
TRACK_MIN_S = 15 * 60
TRACK_KEEP = 12
TRACK_CLASSES = ("tanker",)
UA = "GroundTruth/0.9 (personal non-commercial OSINT dashboard)"

# name: (label, theatre, lat_min, lon_min, lat_max, lon_max). Order matters where boxes touch: first match wins.
BOXES = {
    "hormuz": ("Persian Gulf, Hormuz, Gulf of Oman", "middle-east", 22.0, 47.5, 30.6, 60.5),
    "red_sea": ("Red Sea, Bab el-Mandeb, Gulf of Aden", "middle-east", 11.0, 32.0, 30.0, 51.5),
    "east_med": ("Eastern Mediterranean", "middle-east", 30.5, 28.5, 37.2, 36.5),
    "black_sea": ("Black Sea and Sea of Azov", "ukraine-russia", 40.5, 27.0, 47.6, 42.0),
    "baltic": ("Baltic Sea", "europe-nato", 53.5, 9.5, 60.8, 30.5),
    "taiwan": ("Taiwan Strait", "indo-pacific", 21.5, 117.0, 26.6, 122.6),
    "malacca": ("Singapore and Malacca Straits", "indo-pacific", 1.0, 100.0, 6.0, 104.5),
    "gibraltar": ("Strait of Gibraltar", "europe-nato", 35.7, -6.2, 36.4, -5.0),
    "dover": ("Dover Strait", "europe-nato", 50.6, 0.6, 51.8, 2.6),
    "us_gulf": ("US Gulf Coast (Houston to the Mississippi)", "americas", 27.8, -95.6, 30.1, -88.8),
}
# Boxes with no live volunteer receivers (checked 2026-11-19): drawn with a "no live coverage" note.
NO_COVERAGE = ("hormuz", "red_sea")


def box_of(lat, lon):
    for k, (_l, _t, la0, lo0, la1, lo1) in BOXES.items():
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return k
    return None


def ship_class(t):
    """AIS ship-type code -> coarse class."""
    if not t:
        return "unknown"
    if 80 <= t <= 89:
        return "tanker"
    if 70 <= t <= 79:
        return "cargo"
    if 60 <= t <= 69:
        return "passenger"
    if t == 35:
        return "military"
    if t == 30:
        return "fishing"
    if t in (31, 32, 52):
        return "tug"
    if t in (50, 51, 53, 54, 55, 58, 59):
        return "service"
    return "other"


def api_key():
    k = (os.environ.get("AISSTREAM_API_KEY") or "").strip()
    if k:
        return k
    for p in (os.path.join(os.environ.get("GT_SEED") or "/seed", "aisstream.key"),
              os.path.expanduser("~/.config/aisstream/key")):
        try:
            k = open(p, encoding="utf-8").read().strip()
            if k:
                return k
        except OSError:
            pass
    raise RuntimeError("no AISStream key configured")


# ---------- minimal websocket client ----------

class HandshakeError(ConnectionError):
    def __init__(self, code, status):
        ConnectionError.__init__(self, "handshake refused: %s" % status)
        self.code = code


class WS:
    wire, deflate, reset_ctx, _inflate = 0, False, False, None  # defaults for test doubles built with WS.__new__

    def __init__(self, host, path, timeout=20, deflate=True):
        raw = socket.create_connection((host, 443), timeout=timeout)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        self.wire = 0  # bytes read off the socket, for the sample stats
        key = base64.b64encode(os.urandom(16)).decode()
        ext = "Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits\r\n" if deflate else ""
        self.s.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n%s"
                        "User-Agent: %s\r\n\r\n" % (path, host, key, ext, UA)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.s.recv(4096)
            if not chunk:
                raise ConnectionError("closed during handshake")
            head += chunk
        head, self.buf = head.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split()
        code = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        if code != 101:
            self.s.close()
            raise HandshakeError(code, lines[0][:80])
        hdrs = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                hdrs[k.strip().lower()] = (hdrs.get(k.strip().lower(), "") + "," + v.strip()).strip(",")
        exts = hdrs.get("sec-websocket-extensions", "").lower()
        self.deflate = "permessage-deflate" in exts
        self.reset_ctx = "server_no_context_takeover" in exts
        self._inflate = zlib.decompressobj(-15)

    def _send(self, opcode, payload):
        mask = os.urandom(4)
        n = len(payload)
        hdr = bytes([0x80 | opcode])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send_text(self, text):
        self._send(0x1, text.encode())  # RSV1 clear: uncompressed, which RFC 7692 allows

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError("connection closed")
            self.wire += len(chunk)
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        """Next complete data message as bytes (inflated if it was compressed), or None when the server closes."""
        parts, comp = [], False
        while True:
            b0, b1 = self._read(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                return None
            if op == 0x9:
                self._send(0xA, data)
                continue
            if op == 0xA:
                continue
            if op in (0x1, 0x2):
                comp = bool(b0 & 0x40)
            parts.append(data)
            if b0 & 0x80:
                msg = b"".join(parts)
                if comp:
                    if not self.deflate:
                        raise ConnectionError("compressed frame without permessage-deflate")
                    if self.reset_ctx or self._inflate is None:
                        self._inflate = zlib.decompressobj(-15)
                    msg = self._inflate.decompress(msg + b"\x00\x00\xff\xff")
                return msg

    def close(self):
        try:
            self._send(0x8, b"")
        except OSError:
            pass
        self.s.close()


# ---------- back-off after HTTP 429 ----------

class Backoff:
    """A small state file: after a 429 the next attempts wait 10, 20, 40, then 60 minutes."""
    STEPS_MIN = (10, 20, 40, 60)

    def __init__(self, path):
        self.path = path
        try:
            self.st = json.load(open(path))
        except Exception:
            self.st = {}

    def check(self, now):
        until = self.st.get("until")
        if until and now.strftime("%Y-%m-%dT%H:%M:%SZ") < until:
            raise RuntimeError("AISStream: backing off after HTTP 429 until %s" % until)

    def hit(self, now):
        n = int(self.st.get("n") or 0)
        wait = self.STEPS_MIN[min(n, len(self.STEPS_MIN) - 1)]
        self.st = {"n": n + 1, "until": (now + dt.timedelta(minutes=wait)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        self._save()

    def clear(self):
        if self.st:
            self.st = {}
            self._save()

    def _save(self):
        with open(self.path + ".tmp", "w") as fh:
            json.dump(self.st, fh)
        os.replace(self.path + ".tmp", self.path)


# ---------- sampling ----------

def _ts(meta):
    """'2026-11-16 03:21:07.123456 +0000 UTC' -> '2026-11-16T03:21:07Z'."""
    t = (meta.get("time_utc") or "")[:19]
    return t.replace(" ", "T") + "Z" if len(t) == 19 else None


def _clean(s, n=24):
    """AIS text fields are padded with spaces or '@'."""
    return (s or "").replace("@", " ").strip()[:n]


def imo_ok(n):
    """A real IMO ship number: 7 digits whose last digit is the weighted check digit."""
    s = str(n or "")
    if len(s) != 7 or not s.isdigit() or s == "0000000":
        return False
    return sum(int(s[i]) * (7 - i) for i in range(6)) % 10 == int(s[6])


def _dims(rec, d):
    d = d or {}
    ln = (d.get("A") or 0) + (d.get("B") or 0)
    bm = (d.get("C") or 0) + (d.get("D") or 0)
    if 0 < ln < 500:
        rec["len"] = ln
    if 0 < bm < 80:
        rec["beam"] = bm


def parse_static(rec, kind, body):
    """Fold a ShipStaticData (class A) or StaticDataReport (class B) message into a per-ship record."""
    if kind == "ShipStaticData":
        if body.get("Type"):
            rec["type"] = body["Type"]
        if _clean(body.get("Name"), 32):
            rec["name"] = _clean(body.get("Name"), 32)
        if imo_ok(body.get("ImoNumber")):
            rec["imo"] = str(body["ImoNumber"])
        if _clean(body.get("CallSign"), 8):
            rec["cs"] = _clean(body.get("CallSign"), 8)
        _dims(rec, body.get("Dimension"))
        dr = body.get("MaximumStaticDraught")
        if isinstance(dr, (int, float)) and 0 < dr < 26:
            rec["dr"] = round(float(dr), 1)
        if _clean(body.get("Destination")):
            rec["dest"] = _clean(body.get("Destination"))
        eta = body.get("Eta") or {}
        mo, dy = eta.get("Month") or 0, eta.get("Day") or 0
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            hh, mi = eta.get("Hour") or 0, eta.get("Minute") or 0
            rec["eta"] = "%02d-%02d %02d:%02d" % (mo, dy, hh if hh < 24 else 0, mi if mi < 60 else 0)
    elif kind == "StaticDataReport":
        a, b = body.get("ReportA") or {}, body.get("ReportB") or {}
        if a.get("Valid") and _clean(a.get("Name"), 32):
            rec["name"] = _clean(a.get("Name"), 32)
        if b.get("Valid"):
            if b.get("ShipType"):
                rec["type"] = b["ShipType"]
            if _clean(b.get("CallSign"), 8):
                rec["cs"] = _clean(b.get("CallSign"), 8)
            _dims(rec, b.get("Dimension"))


STATIC_KINDS = ("ShipStaticData", "StaticDataReport")


def sample(seconds=SAMPLE_S, boxes=None):
    """Listen for `seconds`; returns ({mmsi: partial record}, stats)."""
    boxes = BOXES if boxes is None else boxes
    ws = WS(HOST, PATH)
    try:
        ws.send_text(json.dumps({"APIKey": api_key(),
                                 "BoundingBoxes": [[[b[2], b[3]], [b[4], b[5]]] for b in boxes.values()],
                                 "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport"]
                                 + list(STATIC_KINDS)}))
        ws.s.settimeout(15)
        seen, n_msgs, n_static, raw_bytes, t_end = {}, 0, 0, 0, time.time() + seconds
        while time.time() < t_end and n_msgs < MAX_MSGS:
            try:
                raw = ws.recv()
            except socket.timeout:
                break
            if raw is None:
                break
            n_msgs += 1
            raw_bytes += len(raw)
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if "error" in m and not m.get("MessageType"):
                raise RuntimeError("AISStream: %s" % str(m["error"])[:160])
            meta, kind = m.get("MetaData") or {}, m.get("MessageType")
            body = (m.get("Message") or {}).get(kind) or {}
            mmsi = meta.get("MMSI") or body.get("UserID")
            if not mmsi:
                continue
            rec = seen.setdefault(str(mmsi), {})
            name = _clean(meta.get("ShipName"), 32)
            if name:
                rec["name"] = name
            if kind in STATIC_KINDS:
                n_static += 1
                parse_static(rec, kind, body)
                continue
            lat, lon = body.get("Latitude", meta.get("latitude")), body.get("Longitude", meta.get("longitude"))
            if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                continue
            rec.update({"lat": round(lat, 4), "lon": round(lon, 4), "ts": _ts(meta),
                        "sog": body.get("Sog"), "cog": body.get("Cog"),
                        "hdg": body.get("TrueHeading") if body.get("TrueHeading") not in (None, 511) else None,
                        "nav": body.get("NavigationalStatus"), "cls_b": kind == "StandardClassBPositionReport"})
        return seen, {"messages": n_msgs, "static_messages": n_static, "ships_heard": len(seen),
                      "compressed": ws.deflate, "wire_kb": round(ws.wire / 1024), "json_kb": round(raw_bytes / 1024)}
    finally:
        ws.close()


# ---------- registry and merge ----------

# sample-record key -> registry key
STATIC_KEYS = (("type", "t"), ("name", "n"), ("imo", "imo"), ("cs", "cs"), ("len", "len"), ("beam", "bm"),
               ("dest", "dest"), ("eta", "eta"))


def learn(reg, heard, today):
    """Fold what a sample heard into the registry {mmsi: entry}. Draught keeps the last 5 changes (>= 0.2 m)."""
    day = today.isoformat()
    for mmsi, r in heard.items():
        e = reg.get(mmsi)
        if e is None:
            if not any(r.get(k) not in (None, "") for k, _ in STATIC_KEYS) and not r.get("dr"):
                continue
            e = reg[mmsi] = {"first": day}
        for k, short in STATIC_KEYS:
            if r.get(k) not in (None, ""):
                e[short] = r[k]
        if r.get("dr"):
            hist = e.setdefault("dr", [])
            if not hist or abs(hist[-1][0] - r["dr"]) >= 0.2:
                hist.append([r["dr"], day])
                del hist[:-5]
        e["last"] = day
    return reg


def prune_registry(reg, today, days=REG_DAYS):
    cutoff = (today - dt.timedelta(days=days)).isoformat()
    return {k: e for k, e in reg.items() if (e.get("last") or "") >= cutoff}


def _secs(ts):
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()


def merge(vessels, heard, now, reg=None):
    """Fold a sample into the per-ship store, fill gaps from the registry, extend tanker tracks and drop ships
    not heard for KEEP_H hours."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for mmsi, r in heard.items():
        v = vessels.setdefault(mmsi, {})
        v.update({k: val for k, val in r.items() if val is not None})
        v["seen"] = stamp  # static-only records (name, type) are kept too, until a position arrives
    if reg:
        for mmsi, v in vessels.items():
            e = reg.get(mmsi)
            if not e:
                continue
            for k, short in STATIC_KEYS:
                if v.get(k) in (None, "") and e.get(short) not in (None, ""):
                    v[k] = e[short]
            if v.get("dr") is None and e.get("dr"):
                v["dr"] = e["dr"][-1][0]
    cutoff = (now - dt.timedelta(hours=KEEP_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for mmsi in heard:
        v = vessels[mmsi]
        if v.get("lat") is None or not v.get("ts") or ship_class(v.get("type")) not in TRACK_CLASSES:
            continue
        trk = [p for p in (v.get("trk") or []) if p[2] >= cutoff]
        if not trk or _secs(v["ts"]) - _secs(trk[-1][2]) >= TRACK_MIN_S:
            trk.append([v["lon"], v["lat"], v["ts"]])
        v["trk"] = trk[-TRACK_KEEP:]
    return {k: v for k, v in vessels.items() if (v.get("seen") or "") >= cutoff}


def counts(vessels, now):
    """Per box: ships heard in the last hour, how many under way, how many tankers, and how many have a type."""
    hour = (now - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {k: {"ships_1h": 0, "underway": 0, "tankers": 0, "cargo": 0, "military": 0, "typed": 0} for k in BOXES}
    for v in vessels.values():
        if v.get("lat") is None:
            continue
        b = box_of(v["lat"], v["lon"])
        if not b or (v.get("ts") or "") < hour:
            continue
        c = out[b]
        c["ships_1h"] += 1
        if (v.get("sog") or 0) >= 1.0:
            c["underway"] += 1
        cls = ship_class(v.get("type"))
        if cls != "unknown":
            c["typed"] += 1
        if cls in ("tanker", "cargo", "military"):
            c[cls + ("s" if cls == "tanker" else "")] += 1
    return out
