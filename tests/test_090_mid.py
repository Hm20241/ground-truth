"""Offline tests for 0.9.0: flag state from an AIS MMSI (gt/mid.py).
Never touches the network: the MID table is a constant in the module.

Run: python3 -I tests/test_090_mid.py
"""
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import mid  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def iso(m):
    f = mid.MID.get(m)
    return f and f[0]


# ---- the table
M = mid.MID
check(isinstance(M, dict) and len(M) >= 270, "table has >= 270 MIDs (%d)" % len(M))
check(len(M) == 292, "292 MIDs, as in the ITU table read 2026-11-19")
check(all(isinstance(k, int) and 201 <= k <= 775 for k in M), "every key is an int in 201..775")
check(all(isinstance(v, tuple) and len(v) == 2 for v in M.values()), "every value is (iso2, name)")
check(all(len(c) == 2 and c.isascii() and c.isalpha() and c.isupper() for c, _ in M.values()),
      "every ISO2 is two upper-case letters")
check(all(isinstance(n, str) and n.strip() == n and n for _, n in M.values()), "every name is a non-empty string")
check(all(k // 100 in (2, 3, 4, 5, 6, 7) for k in M), "first MID digit is 2-7 (regions)")
check(not any(k in M for k in (217, 221, 222, 223, 260, 302, 474, 600, 700, 776, 799)), "unallocated MIDs are absent")

# ---- well-known flags
check(iso(636) == iso(637) == "LR" and M[636][1] == "Liberia", "636, 637 Liberia")
check(iso(538) == "MH", "538 Marshall Islands")
check(all(iso(m) == "PA" for m in list(range(351, 358)) + list(range(370, 375))), "351-357, 370-374 Panama")
check(iso(273) == "RU", "273 Russia")
check(iso(412) == iso(413) == iso(414) == "CN", "412-414 China")
check(iso(477) == "HK" and iso(453) == "MO" and iso(416) == "TW", "477 Hong Kong, 453 Macao, 416 Taiwan")
check(all(iso(m) == "SG" for m in range(563, 567)), "563-566 Singapore")
check(all(iso(m) == "MT" for m in (215, 229, 248, 249, 256)), "215/229/248/249/256 Malta")
check(all(iso(m) == "CY" for m in (209, 210, 212)), "209/210/212 Cyprus")
check(all(iso(m) == "GR" for m in (237, 239, 240, 241)), "237/239/240/241 Greece")
check(iso(422) == "IR", "422 Iran")
check(iso(620) == iso(616) == "KM", "620, 616 Comoros")
check(iso(626) == "GA", "626 Gabon")
check(iso(613) == "CM", "613 Cameroon")
check(iso(341) == "KN", "341 Saint Kitts and Nevis")
check(iso(667) == "SL", "667 Sierra Leone")
check(iso(572) == "TV", "572 Tuvalu")
check(iso(511) == "PW", "511 Palau")
check(all(iso(m) == "US" for m in (303, 338, 366, 367, 368, 369)), "303, 338, 366-369 United States")
check(all(iso(m) == "GB" for m in range(232, 236)), "232-235 United Kingdom")
check(iso(236) == "GI" and iso(231) == "FO" and iso(331) == "GL" and iso(358) == "PR",
      "territories keep their own code: 236 GI, 231 FO, 331 GL, 358 PR")
check(iso(204) == iso(255) == iso(263) == "PT", "204 Azores, 255 Madeira, 263 Portugal -> PT")
check(iso(635) == iso(618) == iso(607) == "TF", "Kerguelen, Crozet, St Paul/Amsterdam -> TF")
check(iso(306) == "CW" and iso(307) == "AW", "306 Curacao (shared), 307 Aruba")
check(iso(201) == "AL" and iso(775) == "VE" and iso(622) == "EG" and iso(271) == "TR", "201 AL, 271 TR, 622 EG, 775 VE")

# ---- full MMSIs
check(mid.flag_of(636012345) == ("LR", "Liberia"), "636012345 (int) -> LR Liberia")
check(mid.flag_of("273345000") == ("RU", "Russia"), "'273345000' (str) -> RU")
check(mid.flag_of(" 538007123\n") == ("MH", "Marshall Islands"), "surrounding whitespace is ignored")
check(mid.flag_of("477123400")[0] == "HK" and mid.flag_of(422123456)[0] == "IR", "HK and IR ships")
check(mid.iso2_of(636012345) == "LR" and mid.iso2_of("563001234") == "SG", "iso2_of -> 'LR', 'SG'")
check(mid.flag_of(201000000)[0] == "AL" and mid.flag_of(775999999)[0] == "VE", "lowest and highest MIDs")

# ---- None: not a ship station, malformed, or unallocated
NONE = [
    ("002731234", "coast station 00MID"),
    ("027312345", "group call 0MID"),
    (27312345, "group call as int (leading zero lost)"),
    (2731234, "coast station as int"),
    ("111273456", "SAR aircraft 111MID"),
    ("982731234", "craft associated with a parent ship 98MID"),
    ("992731234", "aid to navigation 99MID"),
    ("970123456", "SART 970"),
    ("972123456", "MOB 972"),
    ("974123456", "EPIRB-AIS 974"),
    ("836612345", "handheld VHF 8MID"),
    (800000000, "first digit 8"),
    (100000000, "first digit 1"),
    (12345, "too short"),
    ("6360123456", "too long"),
    ("63601234", "8 digits"),
    ("abc", "non-numeric"),
    ("63601234x", "trailing letter"),
    ("636 12345", "inner space"),
    ("+63601234", "sign"),
    ("63601234١", "non-ASCII digit"),
    ("", "empty string"),
    (None, "None"),
    (636012345.0, "float"),
    (True, "bool"),
    (-636012345, "negative int"),
    ([636012345], "list"),
    (b"636012345", "bytes"),
    ("217123456", "unallocated MID 217"),
    ("302123456", "unallocated MID 302"),
    (474123456, "unallocated MID 474"),
    ("799123456", "unallocated MID 799"),
]
for v, what in NONE:
    check(mid.flag_of(v) is None and mid.iso2_of(v) == "", "None/'' for %s (%r)" % (what, v))

# ---- fast enough for the feed: plain dict lookups
ships = ["%d%06d" % (m, i) for i in range(10) for m in sorted(M)] * 7  # ~20,000 MMSIs
t0 = time.perf_counter()
n = sum(1 for s in ships if mid.iso2_of(s))
dt_ms = (time.perf_counter() - t0) * 1000
check(n == len(ships), "every synthetic ship MMSI gets a flag (%d)" % n)
check(dt_ms < 500, "%d lookups in %.1f ms" % (len(ships), dt_ms))
print("%d checks passed" % ok)
