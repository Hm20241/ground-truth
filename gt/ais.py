"""Live ship positions from AISStream.io (free key), sampled in short bursts. v1.0, 2026-11-16 (Ground Truth 0.4.0).

AISStream is a websocket feed. The standard library has no websocket client and the runtime image holds
only Python, so this module speaks just enough RFC 6455 (TLS, handshake, framing, ping/pong) to read it.

Each run connects, subscribes to the watch boxes, listens for SAMPLE_S seconds and merges what it heard
into cache/ais_vessels.json (last position per ship, kept KEEP_H hours). A ship at anchor reports every
3 minutes and one under way every 2-10 s, so a 60 s sample every 5 minutes sees nearly every ship within
the hour. Coverage is terrestrial receivers run by volunteers: thin far offshore, so absence is not proof.

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

HOST, PATH = "stream.aisstream.io", "/v0/stream"
SAMPLE_S = 60
KEEP_H = 3
MAX_MSGS = 60000  # safety stop for one sample

# name: (label, theatre, lat_min, lon_min, lat_max, lon_max)
BOXES = {
    "hormuz": ("Persian Gulf, Hormuz, Gulf of Oman", "middle-east", 22.0, 47.5, 30.6, 60.5),
    "red_sea": ("Red Sea, Bab el-Mandeb, Gulf of Aden", "middle-east", 11.0, 32.0, 30.0, 51.5),
    "east_med": ("Eastern Mediterranean", "middle-east", 30.5, 28.5, 37.2, 36.5),
    "black_sea": ("Black Sea and Sea of Azov", "ukraine-russia", 40.5, 27.0, 47.6, 42.0),
    "baltic": ("Baltic Sea", "europe-nato", 53.5, 9.5, 60.8, 30.5),
    "taiwan": ("Taiwan Strait", "indo-pacific", 21.5, 117.0, 26.6, 122.6),
}


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

class WS:
    def __init__(self, host, path, timeout=20):
        raw = socket.create_connection((host, 443), timeout=timeout)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n"
                        "User-Agent: GroundTruth/0.4 (personal OSINT dashboard)\r\n\r\n" % (path, host, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.s.recv(4096)
            if not chunk:
                raise ConnectionError("closed during handshake")
            head += chunk
        head, self.buf = head.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0].decode("latin-1")
        if " 101 " not in status + " ":
            raise ConnectionError("handshake refused: %s" % status)

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
        self._send(0x1, text.encode())

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError("connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        """Next complete data message as bytes, or None when the server closes."""
        parts = []
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
            parts.append(data)
            if b0 & 0x80:
                return b"".join(parts)

    def close(self):
        try:
            self._send(0x8, b"")
        except OSError:
            pass
        self.s.close()


# ---------- sampling ----------

def _ts(meta):
    """'2026-11-16 03:21:07.123456 +0000 UTC' -> '2026-11-16T03:21:07Z'."""
    t = (meta.get("time_utc") or "")[:19]
    return t.replace(" ", "T") + "Z" if len(t) == 19 else None


def sample(seconds=SAMPLE_S):
    """Listen for `seconds`; returns ({mmsi: partial record}, stats)."""
    ws = WS(HOST, PATH)
    try:
        ws.send_text(json.dumps({"APIKey": api_key(),
                                 "BoundingBoxes": [[[b[2], b[3]], [b[4], b[5]]] for b in BOXES.values()],
                                 "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport",
                                                        "ShipStaticData"]}))
        ws.s.settimeout(15)
        seen, n_msgs, t_end = {}, 0, time.time() + seconds
        while time.time() < t_end and n_msgs < MAX_MSGS:
            try:
                raw = ws.recv()
            except socket.timeout:
                break
            if raw is None:
                break
            n_msgs += 1
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
            name = (meta.get("ShipName") or "").strip()
            if name:
                rec["name"] = name
            if kind == "ShipStaticData":
                if body.get("Type"):
                    rec["type"] = body["Type"]
                if (body.get("Destination") or "").strip():
                    rec["dest"] = body["Destination"].strip()[:24]
                continue
            lat, lon = body.get("Latitude", meta.get("latitude")), body.get("Longitude", meta.get("longitude"))
            if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                continue
            rec.update({"lat": round(lat, 4), "lon": round(lon, 4), "ts": _ts(meta),
                        "sog": body.get("Sog"), "cog": body.get("Cog"),
                        "hdg": body.get("TrueHeading") if body.get("TrueHeading") not in (None, 511) else None,
                        "nav": body.get("NavigationalStatus"), "cls_b": kind == "StandardClassBPositionReport"})
        return seen, {"messages": n_msgs, "ships_heard": len(seen)}
    finally:
        ws.close()


def merge(vessels, heard, now):
    """Fold a sample into the per-ship store and drop ships not heard for KEEP_H hours."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for mmsi, r in heard.items():
        v = vessels.setdefault(mmsi, {})
        v.update({k: val for k, val in r.items() if val is not None})
        v["seen"] = stamp  # static-only records (name, type) are kept too, until a position arrives
    cutoff = (now - dt.timedelta(hours=KEEP_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {k: v for k, v in vessels.items() if (v.get("seen") or "") >= cutoff}


def counts(vessels, now):
    """Per box: ships heard in the last hour, how many under way, how many tankers."""
    hour = (now - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {k: {"ships_1h": 0, "underway": 0, "tankers": 0, "cargo": 0, "military": 0} for k in BOXES}
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
        if cls in ("tanker", "cargo", "military"):
            c[cls + ("s" if cls == "tanker" else "")] += 1
    return out
