"""Offline tests for 0.13.0: the cyber and routing layer (gt/cyber.py, feeds `cyber` and `bgp`).
Sockets are blocked; nothing touches the network. Fixtures in tests/fixtures/cyber/:
  kev.json, ics.xml, all.xml   CISA (US public domain), real responses of 2026-11-20 trimmed: KEV entries added
                               2026-11-03..18 plus two from 2021; 6 ICS and 4 all-advisories items, descriptions cut
                               after their Background list
  rwl_recent.json, rwl_month.json, rwl_press.json   ransomware.live v2 /recentvictims, /victims/2026/11 and
                               /recentcyberattacks: SYNTHETIC (real keys, invented organisations, groups and links)
  infocon.json                 SANS ISC /api/infocon?json (the real body is just {"status":"green"})
  ddosia.json                  witha.name /data/last.json: SYNTHETIC (invented hosts, documentation-range IPs)
  ripe_series.json, ripe_empty.json   RIPEstat country-resource-stats, 1h, 2026-11-12T00 .. 2026-11-20T03: real
                               envelope, SYNTHETIC counts; rows with equal values merged into several intervals as
                               RIPEstat does; the empty one is what RIPEstat returns for an unknown country.

Run: python3 -I tests/test_cyber.py
"""
import datetime as dt
import gzip
import json
import os
import re
import socket
import statistics
import sys
import tempfile
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "cyber")
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
sys.path.insert(0, PROJ)


def _blocked(*a, **k):
    raise AssertionError("network use in an offline test")


from gt import cyber as cy  # noqa: E402

socket.socket.connect = _blocked          # after the import: ssl subclasses socket.socket
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
cy.urllib.request.urlopen = _blocked
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def raises(fn, exc, text=""):
    try:
        fn()
    except exc as e:
        return text in str(e)
    return False


RAW = {n: open(os.path.join(FX, n), "rb").read() for n in sorted(os.listdir(FX))}
J = {n: json.loads(b) for n, b in RAW.items() if n.endswith(".json")}
NOW = dt.datetime(2026, 11, 20, 5, 30, tzinfo=dt.timezone.utc)
NT = int(NOW.timestamp())
URLS = {cy.KEV_URL: "kev.json", cy.CISA_ICS_URL: "ics.xml", cy.CISA_ALL_URL: "all.xml",
        cy.RWL_RECENT_URL: "rwl_recent.json", cy.RWL_PRESS_URL: "rwl_press.json",
        cy.ISC_INFOCON_URL: "infocon.json", cy.DDOSIA_URL: "ddosia.json"}
SIZE = lambda x: len(json.dumps(x, separators=(",", ":"), ensure_ascii=False).encode())


def reset():
    for n in (cy.STATE_FILE, cy.BGP_FILE):
        p = os.path.join(TMP, "cache", n)
        if os.path.exists(p):
            os.remove(p)


def state():
    return json.load(open(os.path.join(TMP, "cache", cy.STATE_FILE)))


def fake(over=None, fail=(), log=None, ripe=None):
    """Serves fixtures by URL. over: url -> bytes; fail: urls (or 'ripe') that raise; ripe: a2 -> bytes."""
    over = over or {}

    def fetch(url):
        if log is not None:
            log.append(url)
        base = url.split("?")[0] if url.startswith(cy.RIPE_URL) else url
        if url in fail or base in fail or ("ripe" in fail and base == cy.RIPE_URL):
            raise urllib.error.URLError("down: " + base)
        if base == cy.RIPE_URL:
            a2 = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["resource"][0]
            return (ripe or {}).get(a2, RAW["ripe_series.json"])
        if url in over:
            return over[url]
        if url.startswith(cy.RWL_API + "/victims/"):
            return RAW["rwl_month.json"]
        return RAW[URLS[url]]
    return fetch


# ================= timestamps and small helpers =================
T = cy._ts
check(T("2026-11-19T22:18:09.330734+00:00") == int(dt.datetime(2026, 11, 19, 22, 18, 9, tzinfo=dt.timezone.utc).timestamp())
      and T("2026-11-20T03:01:02.5+00:00") == T("2026-11-20T03:01:02Z") and T("2026-11-20T03:01:02") == T("2026-11-20 03:01:02"),
      "_ts: microseconds, odd fractions, Z, naive = UTC, space separator")
check(T("2026-11-20T05:00:00+02:00") == T("2026-11-20T03:00:00Z") and T("2026-11-18") == T("2026-11-18T00:00:00")
      and T("") is None and T(None) is None and T("not a date") is None and T("2026-13-01") is None,
      "_ts: offsets, plain dates, junk -> None")
check(cy._rfc822("Thu, 19 Nov 26 12:00:00 +0000") == T("2026-11-19T12:00:00Z") and cy._rfc822("garbage") is None,
      "CISA pubDate with a 2-digit year -> 2026")
check(cy._a3("UA") == "UKR" and cy._a3("ps") == "PSX" and cy._a3("KP") == "PRK" and cy._a3("XK") == "KOS"
      and cy._a3("UK") is None and cy._a3("PO") is None and cy._a3("") is None and cy._a3("USA") is None,
      "a2 -> a3 via geo (UK/PO are not ISO codes)")
check(cy._a3s_for_names("Australia, New Zealand") == ["AUS", "NZL"] and cy._a3s_for_names("United States") == ["USA"]
      and cy._a3s_for_names("Worldwide") == [], "country names -> a3")

# ================= sector tags and the critical-infrastructure flag =================
CI = {"Healthcare": True, "Energy & Utilities": True, "Government & Defense": True, "Transportation/Logistics": True,
      "Telecommunication": True, "Water and Wastewater Systems": True, "Public Sector": True, "Oil & Gas": True,
      "Manufacturing": False, "Hospitality": False, "Technology": False, "Financial Services": False,
      "Retail & E-Commerce": False, "Agriculture and Food Production": False, "Education": False, "": False,
      "Critical Manufacturing": False, "Critical Manufacturing, Energy": True}
check(all(cy.is_ci(cy.sector_tags(s)) == v for s, v in CI.items()), "CI flag: energy/water/health/gov/defence/transport/"
      "telecom yes; manufacturing, hospitality (not 'hospital'), IT, finance no")
check(cy.sector_tags("Government & Defense") == ["government", "defense"]
      and cy.sector_tags("Healthcare and Public Health") == ["healthcare"]
      and cy.sector_tags("Nuclear Reactors, Materials, and Waste") == ["nuclear"], "sector tags")

# ================= KEV =================
kev = cy.parse_kev(RAW["kev.json"], NOW)
ki = kev["items"]
check(kev["catalog"] == {"version": "2026.11.18", "released": "2026-11-18T19:17:41.0354Z", "count": 1786},
      "KEV catalog version, release time and count")
added = sorted(v["dateAdded"] for v in J["kev.json"]["vulnerabilities"] if v["dateAdded"] >= "2026-11-06")
check(len(ki) == len(added) == 18 and all(i["ts"][:10] >= "2026-11-06" for i in ki), "KEV: the 18 added since 2026-11-06 (14 days)")
check([i["ts_ms"] for i in ki] == sorted((i["ts_ms"] for i in ki), reverse=True), "KEV newest first")
k0 = next(i for i in ki if i["id"] == "kev:CVE-2026-40217")
check(k0["kind"] == "kev" and k0["title"].startswith("CVE-2026-40217 BerriAI LiteLLM") and k0["ts"] == "2026-11-18T00:00:00Z"
      and k0["url"] == "https://nvd.nist.gov/vuln/detail/CVE-2026-40217" and k0["countries"] == [] and k0["sector"] is None
      and k0["vendor"] == "BerriAI" and k0["ransomware"] is False and k0["tags"] == ["kev"], "KEV item fields")
kj = json.loads(RAW["kev.json"])
kj["vulnerabilities"][-1]["knownRansomwareCampaignUse"] = "Known"
kr = cy.parse_kev(json.dumps(kj).encode(), NOW)["items"]
check(sum(i["ransomware"] for i in kr) == 1 and "ransomware" in next(i for i in kr if i["ransomware"])["tags"],
      "KEV ransomware use 'Known' -> ransomware flag and tag")
check(raises(lambda: cy.parse_kev(b'{"title": "x"}', NOW), ValueError, "KEV"), "KEV without a list -> ValueError")

# ================= CISA RSS =================
ics = cy.parse_cisa_rss(RAW["ics.xml"])
alla = cy.parse_cisa_rss(RAW["all.xml"])
I = {i["id"]: i for i in ics}
check(len(ics) == 6 and all(i["kind"] == "ics" for i in ics), "ICS RSS: 6 advisories")
lib, brk, dor = I["cisa:icsa-26-323-03"], I["cisa:icsa-26-323-02"], I["cisa:icsa-26-321-01"]
check(lib["title"] == "libumqtt" and lib["ts"] == "2026-11-19T12:00:00Z" and lib["cvss"] == 8.6 and lib["hq"] == "CHN"
      and lib["deployed"] == "Worldwide" and lib["countries"] == [] and lib["ci"] is True
      and lib["sector"].startswith("Critical Manufacturing, Energy") and {"energy", "water", "transport"} <= set(lib["tags"]),
      "ICS item: sectors, CVSS, HQ China, deployed worldwide -> no countries")
check(brk["countries"] == ["AUS", "NZL"] and brk["hq"] == "AUS" and brk["cvss"] == 9.6 and "cvss9" in brk["tags"]
      and brk["tags"][:1] == ["transport"], "ICS item deployed in Australia, New Zealand -> [AUS, NZL]; CVSS 9.6 -> cvss9")
check(dor["sector"] == "Water and Wastewater Systems" and dor["ci"] and dor["hq"] == "USA", "water advisory -> CI")
check(I["cisa:icsa-26-321-05"]["ci"] is True and "manufacturing" in I["cisa:icsa-26-321-05"]["tags"], "manufacturing + energy -> CI")
A = {i["id"]: i for i in alla}
check(sorted(A) == ["cisa:critical-java-vulnerability-requires-immediate-patching", "cisa:icsa-26-323-02",
                    "cisa:us-government-partners-urge-hardening-industrial-refrigeration-and-cold-chain-monitoring-systems"],
      "all-advisories RSS: the 'CISA Adds N KEV' alert is dropped (KEV covers it)")
check(A["cisa:icsa-26-323-02"] == brk, "the same ICS advisory parses the same from both feeds")
check(A["cisa:critical-java-vulnerability-requires-immediate-patching"]["kind"] == "cisa"
      and A["cisa:critical-java-vulnerability-requires-immediate-patching"]["tags"] == ["alert"]
      and "guidance" in A["cisa:us-government-partners-urge-hardening-industrial-refrigeration-and-cold-chain-monitoring-systems"]["tags"],
      "kind/tags by link path: alert, guidance")
syn = (b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
       b'<item><title>PRC State-Sponsored Actors Target Example Networks</title>'
       b'<link>https://www.cisa.gov/news-events/cybersecurity-advisories/aa26-300a</link>'
       b'<pubDate>Mon, 16 Nov 26 12:00:00 +0000</pubDate><description>&lt;p&gt;x&lt;/p&gt;</description></item>'
       b'<item><title>CISA Releases Two Industrial Control Systems Advisories</title>'
       b'<link>https://www.cisa.gov/news-events/alerts/2026/11/16/x</link><pubDate>Mon, 16 Nov 26 12:00:00 +0000</pubDate></item>'
       b'<item><title>Example Infusion Pump</title><link>https://www.cisa.gov/news-events/ics-medical-advisories/icsma-26-300-01</link>'
       b'<pubDate>Mon, 16 Nov 26 12:00:00 +0000</pubDate><description>&lt;strong&gt;Critical Infrastructure Sectors: '
       b'&lt;/strong&gt;Healthcare and Public Health&lt;/li&gt;</description></item>'
       b'<item><title>No date</title><link>https://www.cisa.gov/x</link></item></channel></rss>')
S = cy.parse_cisa_rss(syn)
check([i["id"] for i in S] == ["cisa:aa26-300a", "cisa:icsma-26-300-01"] and S[0]["tags"] == ["advisory", "joint", "actor:CHN"]
      and S[1]["kind"] == "ics" and S[1]["ci"] and S[1]["tags"][:2] == ["medical", "healthcare"],
      "joint advisory -> actor:CHN tag; ICS roundup alert dropped; medical advisory -> healthcare; undated item skipped")
check(raises(lambda: cy.parse_cisa_rss(b"<html>busy</html>"), ValueError) and
      raises(lambda: cy.parse_cisa_rss(b"<rss"), Exception), "RSS without a channel / broken XML raises")

# ================= ransomware.live victims =================
V = cy.parse_rwl_victims(RAW["rwl_recent.json"])
check(len(V) == 12 and all(set(r) == {"id", "group", "a2", "sector", "disc", "attack", "url"} for r in V),
      "victims: 12 minimal records, no name/description/domain/claim_url/screenshot kept")
check(V[0]["a2"] == "US" and V[1]["a2"] == "UA" and V[6]["a2"] is None and V[10]["a2"] is None,
      "victim country: ISO codes kept, '' and 'UK' -> None")
check(V[6]["sector"] is None and V[11]["sector"] is None and V[0]["sector"] == "Healthcare", "'Not Found' and '' sector -> None")
check(V[8]["disc"] == T("2026-11-19T06:00:00+00:00") and V[8]["attack"] == T("2026-11-18T00:00:00+00:00")
      and V[0]["id"] == cy.parse_rwl_victims(RAW["rwl_recent.json"])[0]["id"] and V[0]["id"].startswith("rwl:"),
      "victim times; ids stable (hash of the ransomware.live link)")
check(raises(lambda: cy.parse_rwl_victims(b'{"error": "rate limit"}'), ValueError, "expected a list"), "victims: non-list -> ValueError")

# ================= press attacks =================
P = cy.parse_rwl_press(RAW["rwl_press.json"])
PT = {p["title"][:20]: p for p in P}
check(len(P) == 8 and all(p["kind"] == "attack" and "press" in p["tags"] for p in P), "press: 8 items")
check(PT["Example air-raid ale"]["countries"] == [] and PT["Cyberattack on examp"]["countries"] == []
      and PT["Example retailer rep"]["countries"] == [] and PT["[Exclusive] Example "]["countries"] == ["KOR"]
      and PT["Zehn Tage mit Papier"]["countries"] == ["DEU"], "press codes: UK/PO/SW ambiguous -> none, KO -> KOR, DE -> DEU")
check(PT["[Exclusive] Example "]["ci"] and PT["Zehn Tage mit Papier"]["ci"] and PT["Example City of Spri"]["ci"]
      and PT["Cyberattack on examp"]["ci"] and not PT["Example retailer rep"]["ci"] and not PT["Example widgets make"]["ci"]
      and PT["Example City of Spri"]["ci_basis"] == "keywords", "press CI from keywords: hospital, Klinik, city of, ePUAP")
check(PT["[Exclusive] Example "]["claimed_by"] == "grpalpha" and "claimed" in PT["[Exclusive] Example "]["tags"]
      and PT["[Exclusive] Example "]["claim"] == J["rwl_recent.json"][0]["url"], "press item claimed by a gang links its claim")
check(not any("summary" in p or "victim" in p or "domain" in p for p in P), "press: no summaries, victim fields or domains")

# ================= infocon, DDoSia =================
check(cy.parse_infocon(RAW["infocon.json"]) == {"level": "green"} and raises(lambda: cy.parse_infocon(b'{"status":"puce"}'), ValueError)
      and raises(lambda: cy.parse_infocon(b'[]'), ValueError), "infocon green; unknown level raises")
D = cy.parse_ddosia(RAW["ddosia.json"])
check(D["rules"] == 12 and D["hosts"] == ["app.example.io", "portal.example.gal", "sede.example.gob.es", "tickets.example.co.uk",
                                          "www.example-ayto.es", "www.example-transit.com", "www.example.eus", "www.example.gov.pl"],
      "DDoSia: 12 rules -> 8 unique hosts (case and trailing dot folded, IP literal dropped)")
check([cy.host_a2(h) for h in D["hosts"]] == [None, "ES", "ES", "GB", "ES", None, "ES", "PL"],
      "host country by ccTLD: .es/.eus/.gal -> ES, .uk -> GB, .pl -> PL; .com/.io unattributed")
check(raises(lambda: cy.parse_ddosia(b'{"randoms": []}'), ValueError), "DDoSia without targets raises")

# ================= the cyber feed =================
reset()
log = []
c1 = cy.cyber(now=NOW, fetch=fake(log=log))
check(len(log) == 8 and log.count(cy.RWL_MONTH_URL % (2026, 11)) == 1, "first poll: 7 sources + 1 month bootstrap = 8 calls")
for key in ("version", "fetched_at", "count", "sources", "attribution", "items", "by_country", "infocon", "summary"):
    assert key in c1, key
check(c1["version"] == "1.0" and c1["fetched_at"] == "2026-11-20T05:30:00Z" and c1["count"] == len(c1["items"]),
      "contract keys; count = items")
check([s["name"] for s in c1["sources"]] == [n for n, _, _, _ in cy.CYBER_SOURCES] and all(
      set(s) >= {"name", "ok", "error", "newest", "n"} and s["ok"] and s["error"] is None for s in c1["sources"]),
      "sources: one row per source with name/ok/error/newest/n")
SR = {s["name"]: s for s in c1["sources"]}
check(SR["cisa_kev"]["n"] == 18 and SR["cisa_kev"]["newest"] == "2026-11-18T00:00:00Z" and SR["cisa_ics"]["n"] == 5
      and SR["cisa_all"]["n"] == 1 and SR["ransomware_live"]["n"] == 15 and SR["ransomware_live_press"]["n"] == 7
      and SR["ddosia"]["n"] == 1 and SR["sans_isc"]["n"] == 1, "per-source counts in their windows")
check(SR["ransomware_live"]["cover_from"] == "2026-11-13T05:30:00Z", "month bootstrap -> 7-day coverage from the first poll")
check("Source: Ransomware.live" in c1["attribution"] and any(a["url"] == "https://www.ransomware.live" for a in c1["attribution_links"])
      and c1["non_commercial"] is True and c1["public_ok"] is False and c1["licence"] == cy.LICENCE["cyber"],
      "attribution names and links Ransomware.live; non-commercial, not public")
items = c1["items"]
check([i["ts_ms"] for i in items] == sorted((i["ts_ms"] for i in items), reverse=True) and len({i["id"] for i in items}) == len(items),
      "items newest first, unique ids")
check(all(set(i) >= {"id", "kind", "title", "url", "ts_ms", "ts", "countries", "sector", "tags", "ci"} and cy._iso(i["ts_ms"] // 1000) == i["ts"]
          and all(re.match(r"^[A-Z]{3}$", a) for a in i["countries"]) and i["url"].startswith("http") for i in items),
      "item schema: id, kind, title, url, ts_ms = ts, countries are a3 codes")
K = {}
for i in items:
    K[i["kind"]] = K.get(i["kind"], 0) + 1
check(K == {"kev": 18, "ics": 5, "cisa": 1, "ransom": 15, "attack": 7, "ddos": 1}, "items by kind: %s" % K)
check(not any(i["id"] == "cisa:icsa-26-295-17" for i in items) and not any(i["ts"] < "2026-11-06" for i in items if i["kind"] in ("kev", "ics", "cisa")),
      "14-day window for CISA/KEV (22 Oct advisory and 5 Nov guidance out)")
check(not any(i["kind"] == "ransom" and i["ts"] < "2026-11-13T05:30" for i in items)
      and not any(i["kind"] == "attack" and i["ts"] < "2026-11-13" for i in items), "7-day window for ransomware claims and press")
R = {i["id"]: i for i in items if i["kind"] == "ransom"}
r0 = R[cy.parse_rwl_victims(RAW["rwl_recent.json"])[0]["id"]]
check(r0["title"] == "Ransomware claim: Healthcare victim in United States of America (grpalpha)" and r0["countries"] == ["USA"]
      and r0["ci"] and r0["url"] == J["rwl_recent.json"][0]["url"] and "press" in r0["tags"],
      "ransom item: sector + country + group, links ransomware.live, press-confirmed tag")
check(sum(i["ci"] for i in R.values()) == 9, "9 of 15 claims are critical infrastructure")
blob = json.dumps(c1, ensure_ascii=False)
check(not any(s in blob for s in ("Invented test text", "000-00-0000", ".onion", "images.example.invalid", "Invented summary",
                                  "Example Regional Hospital", "exampleregionalhospital.example", "Example Power Cooperative")),
      "no victim names, descriptions, domains, onion links, screenshots or press summaries served")
check(not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", blob), "no IP addresses in the output (DDoSia targets by host only)")
json.dumps(c1, allow_nan=False)
check(SIZE(c1) < cy.MAX_BYTES and c1["trimmed"] == 0, "output is plain JSON, small (%d bytes), nothing trimmed" % SIZE(c1))

# by_country
B = c1["by_country"]
check(B["USA"]["ransom_7d"] == 6 and B["USA"]["ransom_ci_7d"] == 3 and B["USA"]["ci_sectors"] == {"healthcare": 2, "energy": 1}
      and B["USA"]["groups"][0] == "grpalpha" and B["USA"]["attacks_7d"] == 1 and B["USA"]["attacks_ci_7d"] == 1,
      "by_country USA: 6 claims (3 CI: healthcare 2, energy 1), 1 press attack")
check(B["UKR"]["ransom_7d"] == 2 and B["UKR"]["ransom_ci_7d"] == 2 and B["ISR"]["ransom_7d"] == 2 and "FRA" not in B,
      "by_country UKR/ISR from recent + month; the FR bank (12 Nov) is outside 7 days")
check(B["ESP"]["ddos_now"] == 4 and B["ESP"]["ddos_7d"] == 4 and B["GBR"]["ddos_now"] == 1 and B["POL"]["ddos_now"] == 1
      and B["KOR"]["attacks_7d"] == 1 and B["DEU"]["ransom_7d"] == 2, "by_country DDoSia hosts and press attacks")
check(c1["unattributed"] == {"ransom_7d": 2, "ransom_ci_7d": 1, "attacks_7d": 4, "ddos_7d": 2}, "unattributed counts kept apart: %s" % c1["unattributed"])
check(c1["infocon"]["level"] == "green" and c1["kev_catalog"]["count"] == 1786, "infocon and KEV catalog meta")
check(c1["summary"].startswith("ISC infocon green. Ransomware claims 7 d: 15 (9 critical infrastructure: "
                               "energy 2, government 2, healthcare 2, transport 2); most USA 6")
      and "DDoSia targets now: 8 hosts (ES 4, other domains 2, GB 1)" in c1["summary"] and len(c1["summary"]) <= cy.SUMMARY_MAX,
      "summary: %s" % c1["summary"])
dd = next(i for i in items if i["kind"] == "ddos")
check(dd["countries"][0] == "ESP" and set(dd["countries"]) == {"ESP", "GBR", "POL"} and len(dd["hosts"]) == 8
      and dd["title"].startswith("DDoSia (NoName057(16)) target list: 8 hosts (Spain 4"), "DDoSia item")

# cadences
log2 = []
c2 = cy.cyber(now=NOW + dt.timedelta(seconds=900), fetch=fake(log=log2))
check(log2 == [] and c2["items"] == c1["items"], "+15 min: nothing due, same items from the cache")
log3 = []
cy.cyber(now=NOW + dt.timedelta(seconds=1800), fetch=fake(log=log3))
check(log3 == [cy.CISA_ICS_URL, cy.CISA_ALL_URL], "+30 min: only the two CISA RSS feeds")
log4 = []
cy.cyber(now=NOW + dt.timedelta(seconds=3600), fetch=fake(log=log4))
check(len(log4) == 7 and not any("/victims/" in u for u in log4), "+60 min: every source once; coverage whole -> no bootstrap")

# a failing source keeps its cached data; the others go on
log5 = []
c5 = cy.cyber(now=NOW + dt.timedelta(seconds=7200), fetch=fake(fail={cy.KEV_URL, cy.RWL_RECENT_URL}, log=log5))
S5 = {s["name"]: s for s in c5["sources"]}
check(not S5["cisa_kev"]["ok"] and "URLError" in S5["cisa_kev"]["error"] and S5["cisa_kev"]["n"] == 18
      and not S5["ransomware_live"]["ok"] and S5["ransomware_live"]["n"] == 15 and S5["cisa_ics"]["ok"]
      and S5["cisa_kev"]["good"] == "2026-11-20T06:30:00Z", "failing KEV and ransomware.live: error shown, cached items still served")
log6 = []
cy.cyber(now=NOW + dt.timedelta(seconds=7200 + 900), fetch=fake(log=log6))
check(cy.KEV_URL in log6 and cy.RWL_RECENT_URL not in log6, "retry: KEV after 15 min; ransomware.live not before 30 min")
log7 = []
cy.cyber(now=NOW + dt.timedelta(seconds=7200 + 1800), fetch=fake(log=log7))
check(cy.RWL_RECENT_URL in log7, "ransomware.live retried at 30 min")

reset()
check(raises(lambda: cy.cyber(now=NOW, fetch=fake(fail=set(URLS))), RuntimeError, "no source"), "every source down, no cache -> RuntimeError")
reset()
c8 = cy.cyber(now=NOW, fetch=fake(fail=set(URLS) - {cy.ISC_INFOCON_URL}))
check(c8["count"] == 0 and c8["infocon"]["level"] == "green" and sum(s["ok"] for s in c8["sources"]) == 1,
      "one source up is enough for a (thin) feed")
reset()
bad = {cy.RWL_RECENT_URL: b"<html>429 Too Many Requests</html>", cy.DDOSIA_URL: b"[]", cy.CISA_ALL_URL: b"not xml"}
c9 = cy.cyber(now=NOW, fetch=fake(over=bad))
S9 = {s["name"]: s for s in c9["sources"]}
check(not S9["ransomware_live"]["ok"] and not S9["ddosia"]["ok"] and not S9["cisa_all"]["ok"] and S9["cisa_kev"]["ok"]
      and c9["count"] == 18 + 5 + 7, "bad bodies fail only their own source")

# ransomware.live store: gap -> re-bootstrap (at most daily), month change -> one month per poll
reset()
cy.cyber(now=NOW, fetch=fake())
later = NOW + dt.timedelta(days=3)
shift = lambda s: cy._iso(cy._ts(s) + 3 * 86400)      # (3.9's fromisoformat rejects '.5' fractions)
rec3 = [dict(v, discovered=shift(v["discovered"]), attackdate=shift(v["attackdate"]), url=v["url"] + "x3")
        for v in J["rwl_recent.json"]]
log10 = []
c10 = cy.cyber(now=later, fetch=fake(over={cy.RWL_RECENT_URL: json.dumps(rec3).encode()}, log=log10))
st10 = state()["sources"]["ransomware_live"]["data"]
check(log10.count(cy.RWL_MONTH_URL % (2026, 11)) == 1 and st10["cover_from"] == cy._ts("2026-11-16T05:30:00Z"),
      "a gap in the recent list -> month list fetched again (24 h after the last try)")
check(all(r["disc"] >= cy._ts("2026-11-16T05:30:00Z") for r in st10["v"].values()) and len(st10["v"]) == 13 + 12,
      "store pruned to 7 days: 13 older claims survive (Nov 15 and 14 dropped) + 12 new = %d" % len(st10["v"]))
reset()
dec = dt.datetime(2026, 12, 3, 12, 0, tzinfo=dt.timezone.utc)
rec13 = json.dumps([dict(v, discovered=cy._iso(cy._ts(v["discovered"]) + 13 * 86400),
                         attackdate=cy._iso(cy._ts(v["attackdate"]) + 13 * 86400)) for v in J["rwl_recent.json"]]).encode()
log11 = []
c11 = cy.cyber(now=dec, fetch=fake(log=log11, over={cy.RWL_RECENT_URL: rec13}))
check([u for u in log11 if "/victims/" in u] == [cy.RWL_MONTH_URL % (2026, 11)] and
      state()["sources"]["ransomware_live"]["data"]["cover_from"] > cy._ts("2026-11-26T12:00:00Z"),
      "across a month change: one month per poll, coverage still short")
log12 = []
cy.cyber(now=dec + dt.timedelta(hours=1), fetch=fake(log=log12, over={cy.RWL_RECENT_URL: rec13}))
check([u for u in log12 if "/victims/" in u] == [cy.RWL_MONTH_URL % (2026, 12)] and
      state()["sources"]["ransomware_live"]["data"]["cover_from"] == cy._ts("2026-11-26T13:00:00Z"),
      "next poll fetches the other month -> coverage whole")
log13 = []
cy.cyber(now=dec + dt.timedelta(hours=2), fetch=fake(log=log13, over={cy.RWL_MONTH_URL % (2026, 12): b"oops",
                                                                       cy.RWL_RECENT_URL: rec13}))
check(not any("/victims/" in u for u in log13), "no bootstrap once coverage is whole")
reset()
c14 = cy.cyber(now=NOW, fetch=fake(fail={cy.RWL_MONTH_URL % (2026, 11)}))
S14 = {s["name"]: s for s in c14["sources"]}
check(S14["ransomware_live"]["ok"] and "URLError" in S14["ransomware_live"]["boot_error"] and S14["ransomware_live"]["n"] == 12
      and S14["ransomware_live"]["cover_from"] == "2026-11-18T17:30:00Z" and "counted since 2026-11-18 17:30" in c14["summary"],
      "a failed bootstrap: recent claims still count, coverage start shown")
log15 = []
cy.cyber(now=NOW + dt.timedelta(hours=1), fetch=fake(log=log15))
check(not any("/victims/" in u for u in log15), "a failed bootstrap waits a day before trying that month again")

# DDoSia: config change, 'now' expires with a stale source
reset()
cy.cyber(now=NOW, fetch=fake())
dj = json.loads(RAW["ddosia.json"])
dj["targets"] = [t for t in dj["targets"] if not t["host"].endswith(".pl")] + [dict(dj["targets"][0], host="www.example.lt")]
c16 = cy.cyber(now=NOW + dt.timedelta(hours=1), fetch=fake(over={cy.DDOSIA_URL: json.dumps(dj).encode()}))
ddi = [i for i in c16["items"] if i["kind"] == "ddos"]
check(len(ddi) == 2 and c16["by_country"]["LTU"]["ddos_now"] == 1 and c16["by_country"]["POL"]["ddos_now"] == 0
      and c16["by_country"]["POL"]["ddos_7d"] == 1, "a new target list -> a second ddos item; Poland no longer 'now', still in 7 d")
c17 = cy.cyber(now=NOW + dt.timedelta(hours=8), fetch=fake(fail={cy.DDOSIA_URL}))
check(all(c["ddos_now"] == 0 for c in c17["by_country"].values()) and c17["by_country"]["ESP"]["ddos_7d"] == 4,
      "DDoSia down over 6 h -> nothing counted as 'now', 7-day counts kept")

# caps: 600 claims -> 400 items, CI claims kept, counts whole
reset()
many = []
for n in range(600):
    sect = ["Healthcare", "Manufacturing", "Technology", "Retail & E-Commerce", "Energy & Utilities", "Other"][n % 6]
    many.append(dict(J["rwl_recent.json"][0], activity=sect, country=["US", "DE", "FR", "BR"][n % 4],
                     discovered=cy._iso(NT - 60 - n * 900).replace("Z", "+00:00"), url="https://www.ransomware.live/id/T%04d" % n))
c18 = cy.cyber(now=NOW, fetch=fake(over={cy.RWL_RECENT_URL: json.dumps(many).encode()}))
rk = [i for i in c18["items"] if i["kind"] == "ransom"]
# 600 synthetic claims + 6 more from the month bootstrap (3 recent-list ones, school, ministry, airport) = 606
check(c18["count"] == cy.MAX_ITEMS and c18["trimmed"] == 606 + 18 + 5 + 1 + 7 + 1 - 400, "items capped at 400 (trimmed %d)" % c18["trimmed"])
check(sum(1 for i in rk if i["ci"]) == 200 + 4 and len(rk) == 400 - 32
      and sum(1 for i in c18["items"] if i["kind"] in ("kev", "ics", "cisa", "ddos", "attack")) == 18 + 5 + 1 + 1 + 7,
      "trim drops non-CI claims only: all CI claims, KEV, CISA, press and DDoSia kept")
check(sum(c["ransom_7d"] for c in c18["by_country"].values()) + c18["unattributed"]["ransom_7d"] == 606,
      "by_country counts every claim, trimmed or not")
check(SIZE(c18) <= cy.MAX_BYTES, "capped output %d bytes" % SIZE(c18))
old = cy.MAX_BYTES
cy.MAX_BYTES = 60000
c19 = cy.cyber(now=NOW + dt.timedelta(seconds=60), fetch=fake())
cy.MAX_BYTES = old
check(SIZE(c19) <= 60000 and c19["count"] < 400 and c19["trimmed"] > 0, "byte cap: %d bytes, %d items" % (SIZE(c19), c19["count"]))
check(not os.path.exists(os.path.join(TMP, "cache", cy.STATE_FILE + ".tmp")) and isinstance(state()["sources"], dict),
      "cache written atomically as cyber_state.json")

# ================= RIPEstat parsing and the drop rule =================


def expand(raw):
    """Independent expansion of a RIPEstat answer: {datetime: (v4, v6, asns)}."""
    out = {}
    for e in json.loads(raw)["data"]["stats"]:
        for tl in e["timeline"]:
            t, end = dt.datetime.fromisoformat(tl["starttime"]), dt.datetime.fromisoformat(tl["endtime"])
            while t <= end:
                out[t] = (e["v4_prefixes_ris"], e["v6_prefixes_ris"], e["asns_ris"])
                t += dt.timedelta(hours=1)
    return out


def encode(series, latest=None):
    """{datetime: (v4, v6, asns)} -> a RIPEstat answer with one entry per hour."""
    d = json.loads(RAW["ripe_series.json"])
    d["data"]["stats"] = [{"timeline": [{"starttime": t.strftime("%Y-%m-%dT%H:%M:%S"), "endtime": t.strftime("%Y-%m-%dT%H:%M:%S")}],
                           "v4_prefixes_ris": v[0], "v6_prefixes_ris": v[1], "asns_ris": v[2], "v4_prefixes_stats": -1,
                           "v6_prefixes_stats": -1, "asns_stats": 61, "stats_date": t.strftime("%Y-%m-%dT00:00:00")}
                          for t, v in sorted(series.items())]
    if latest:
        d["data"]["latest_time"] = latest
    return json.dumps(d).encode()


BASE = expand(RAW["ripe_series.json"])
HOURS = sorted(BASE)


def variant(last=4, v4=None, v6=None, asn=None, scale=None, shift_h=0):
    s = {}
    for k, t in enumerate(HOURS):
        a, b, c = BASE[t]
        if scale:
            a, b, c = scale
        if k >= len(HOURS) - last:
            a = a if v4 is None else v4
            b = b if v6 is None else v6
            c = c if asn is None else asn
        s[t - dt.timedelta(hours=shift_h)] = (a, b, c)
    return encode(s)


series, latest = cy.parse_ripe(RAW["ripe_series.json"], "UA")
check(len(json.loads(RAW["ripe_series.json"])["data"]["stats"]) == 14 and len(series) == 196 == len(BASE)
      and all(series[int(t.replace(tzinfo=dt.timezone.utc).timestamp())] == tuple(float(x) for x in v) for t, v in BASE.items()),
      "merged RIPEstat rows (14 entries, up to 17 intervals) expand to 196 hourly points")
check(latest == cy._ts("2026-11-20T03:59:59") and max(series) == cy._ts("2026-11-20T03:00:00"), "latest_time and newest point")
check(raises(lambda: cy.parse_ripe(RAW["ripe_empty.json"], "QQ"), ValueError, "no data points"), "unknown country (empty stats) raises")
er = json.loads(RAW["ripe_series.json"])
er.update(status="error", status_code=400, messages=[["error", "bad resource"]])
check(raises(lambda: cy.parse_ripe(json.dumps(er).encode(), "UA"), RuntimeError, "status error"), "RIPEstat error status raises")
an = cy.analyse(series, NT)
lastp = HOURS[-1]
bpts = [BASE[t] for t in HOURS if lastp - dt.timedelta(days=7) <= t <= lastp - dt.timedelta(hours=6)]
b4 = statistics.median(v[0] for v in bpts)
n4 = statistics.median(BASE[t][0] for t in HOURS[-3:])
check(an["level"] == "ok" and an["reasons"] == [] and an["base"]["v4"] == cy._num(b4) and an["now"]["v4"] == cy._num(n4)
      and an["pct"]["v4"] == round((n4 - b4) / b4 * 100, 1) and an["latest"] == "2026-11-20T03:00:00Z",
      "baseline = median of 7 d .. 6 h before; now = median of the last 3 h (one-hour dip to 940 ignored)")
check(an["spark"]["start"] == "2026-11-13T06:00:00Z" and an["spark"]["step_h"] == 3 and len(an["spark"]["v4"]) == 56
      and an["spark"]["v4"][-1] == cy._num(BASE[lastp][0]), "spark: 7 days at 3 h steps, newest last")


def level(raw):
    s, _ = cy.parse_ripe(raw)
    return cy.analyse(s, NT)


L = {name: level(raw) for name, raw in {
    "v4drop": variant(v4=850), "dip": variant(v4=940), "asndrop": variant(asn=37), "asndip": variant(asn=38),
    "blackout": variant(v4=0, v6=0, asn=0), "v6only": variant(v6=10), "single": variant(last=1, v4=500),
    "two": variant(last=2, v4=500), "small": variant(scale=(4, 0, 1), v4=3), "smallout": variant(scale=(4, 0, 1), v4=0, asn=0),
    "stale": variant(v4=850, shift_h=20)}.items()}
check(L["v4drop"]["level"] == "drop" and L["v4drop"]["reasons"][0].startswith("IPv4 prefixes -15.") and L["v4drop"]["diff"]["v4"] < -100,
      "IPv4 -15 %% for 4 h -> drop (%s)" % L["v4drop"]["reasons"])
check(L["dip"]["level"] == "dip" and L["asndrop"]["level"] == "drop" and L["asndrop"]["reasons"] == ["ASNs -7.5% (-3)"]
      and L["asndip"]["level"] == "drop" and L["asndip"]["reasons"] == ["ASNs -5.0% (-2)"],
      "IPv4 -6 % -> dip; ASNs -3 (-7.5 %) -> drop; ASNs 40 -> 38 is exactly -5 % and 2 fewer -> drop (bounds inclusive)")
check(L["blackout"]["level"] == "drop" and L["blackout"]["reasons"][0].startswith("no IPv4 prefixes visible"), "total blackout -> drop")
check(L["v6only"]["level"] == "ok" and L["v6only"]["pct"]["v6"] < -50, "IPv6 -80 %% alone never flags")
check(L["single"]["level"] == "ok" and L["two"]["level"] == "drop", "one bad (partial) hour is ignored; two of the last three count")
check(L["small"]["level"] == "ok" and L["small"]["pct"]["v4"] == -25.0 and L["smallout"]["level"] == "drop",
      "tiny network: 4 -> 3 prefixes (-25 %%, 1 fewer) stays ok; 4 -> 0 is a drop")
check(L["stale"]["level"] == "stale" and "over 12 h old" in L["stale"]["reasons"][0], "newest point 20 h old -> stale, not drop")
# the ASN dip band: 2+ fewer and -2.5 %% .. -5 %%
big = level(variant(scale=(1000, 50, 80), asn=77))
check(big["level"] == "dip" and big["reasons"] == ["ASNs -3.8% (-3)"], "ASNs 80 -> 77 (-3.8 %%) -> dip")

# ================= the bgp feed: stagger, priorities, failures =================
reset()
log = []
ripe = {"SY": variant(v4=850), "IR": variant(v4=940), "KP": variant(scale=(4, 0, 1), v4=0, asn=0)}
g1 = cy.bgp(now=NOW, fetch=fake(log=log, ripe=ripe))
q = [urllib.parse.parse_qs(urllib.parse.urlsplit(u).query) for u in log]
check(len(log) == 19 <= cy.BGP_MAX_PER_POLL and [x["resource"][0] for x in q] == list(cy.WATCH),
      "first poll: all 19 watched countries (never fetched), within the 20-call cap")
check(all(x["sourceapp"] == ["groundtruth"] and x["resolution"] == ["1h"] and x["starttime"] == ["2026-11-12T05:00:00"] for x in q),
      "RIPEstat calls: sourceapp=groundtruth, 1h, starttime = 8 days back on the hour")
for key in ("version", "fetched_at", "count", "sources", "attribution", "countries", "drops", "dips", "summary", "thresholds"):
    assert key in g1, key
check(g1["count"] == 19 and g1["sources"][0]["name"] == "ripestat" and g1["sources"][0]["ok"] and g1["sources"][0]["requests"] == 19
      and g1["sources"][0]["newest"] == "2026-11-20T03:00:00Z" and g1["sources"][0]["n"] == 19, "bgp sources row")
check(g1["drops"] == ["PRK", "SYR"] and g1["dips"] == ["IRN"] and [r["a2"] for r in g1["countries"][:3]] == ["KP", "SY", "IR"],
      "drops first, worst IPv4 change first (KP blackout -100 %, SY -15 %), then dips (IR)")
check(g1["summary"].startswith("DROP North Korea: no IPv4 prefixes visible") and "; DROP Syria: IPv4 prefixes -15." in g1["summary"]
      and "; DIP Iran: IPv4 prefixes -6." in g1["summary"], "bgp summary: %s" % g1["summary"])
row = next(r for r in g1["countries"] if r["a2"] == "PS")
check(row["a3"] == "PSX" and row["theatre"] == "middle-east" and row["url"] == "https://stat.ripe.net/PS" and row["level"] == "ok"
      and row["fetched"] == "2026-11-20T05:30:00Z" and set(row) >= {"now", "base", "pct", "diff", "spark", "reasons", "latest"},
      "country row: a2/a3/name/theatre/url/now/base/pct/spark")
check(g1["non_commercial"] is True and g1["public_ok"] is False and "re-distribution" in g1["licence"]
      and g1["attribution"] == "RIPEstat, RIPE NCC (RIS routing data)", "bgp licence: non-commercial, not public")
json.dumps(g1, allow_nan=False)
check(SIZE(g1) < 40000, "bgp output %d bytes" % SIZE(g1))
log = []
cy.bgp(now=NOW + dt.timedelta(seconds=300), fetch=fake(log=log, ripe=ripe))
check(log == [], "every country fetched under 10 min ago -> no calls")
log = []
g2 = cy.bgp(now=NOW + dt.timedelta(seconds=900), fetch=fake(log=log, ripe=ripe))
got = [urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)["resource"][0] for u in log]
rest = sorted(a for a in cy.WATCH if a not in ("SY", "IR", "KP"))
check(len(got) == cy.BGP_PER_POLL == 7 and got[:3] == ["IR", "KP", "SY"] and got[3:] == rest[:4],
      "then 7 a poll: drop/dip countries first, then the oldest (%s)" % got)
log = []
cy.bgp(now=NOW + dt.timedelta(seconds=1800), fetch=fake(log=log, ripe=ripe))
got2 = [urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)["resource"][0] for u in log]
check(got2[:3] == ["IR", "KP", "SY"] and got2[3:] == rest[4:8], "the next poll takes the next oldest")
seen = {}
for k in range(6):
    log = []
    cy.bgp(now=NOW + dt.timedelta(seconds=2700 + 900 * k), fetch=fake(log=log))
    for u in log:
        a2 = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)["resource"][0]
        seen.setdefault(a2, []).append(k)
    assert len(log) <= cy.BGP_PER_POLL
check(set(seen) == set(cy.WATCH), "every country refreshed within %d polls of 7" % 6)
g3 = cy.bgp(now=NOW + dt.timedelta(seconds=2700 + 900 * 6), fetch=fake())
check(g3["drops"] == [] and g3["dips"] == [] and g3["summary"].startswith("No routing drop in 19 of 19"), "recovered -> no drops")

# failures
reset()
log = []
check(raises(lambda: cy.bgp(now=NOW, fetch=fake(fail={"ripe"}, log=log)), RuntimeError, "no country has data") and len(log) == cy.BGP_MAX_FAILS,
      "RIPEstat down, no cache: stops after 3 failures in a row, raises")
reset()
g4 = cy.bgp(now=NOW, fetch=fake(ripe={"BY": RAW["ripe_empty.json"], "LB": b"<html>502</html>"}))
P4 = {r["a2"]: r for r in g4["countries"]}
check(P4["BY"]["level"] == "pending" and "no data points" in P4["BY"]["error"] and P4["LB"]["level"] == "pending"
      and g4["count"] == 17 and not g4["sources"][0]["ok"] and "Pending: BY, LB." in g4["summary"],
      "two bad countries -> pending with their error; the other 17 fine")
log = []
g5 = cy.bgp(now=NOW + dt.timedelta(hours=13), fetch=fake(fail={"ripe"}, log=log))
check(len(log) == cy.BGP_MAX_FAILS and g5["count"] == 17 and all(r["level"] in ("stale", "pending") for r in g5["countries"])
      and g5["sources"][0]["ok"] is False and not g5["drops"], "RIPEstat down 13 h: cached rows turn stale, no false drops")
reset()
ticks = iter(range(0, 10000, 50))
log = []
cy.bgp(now=NOW, fetch=fake(log=log), clock=lambda: next(ticks))
check(len(log) == 1, "the 90 s time budget ends a slow poll early (%d call)" % len(log))
check(json.load(open(os.path.join(TMP, "cache", cy.BGP_FILE)))["countries"]["UA"]["ok"] is True
      and not os.path.exists(os.path.join(TMP, "cache", cy.BGP_FILE + ".tmp")), "bgp cache written atomically as cyber_bgp.json")

# ================= module contract =================
src = open(os.path.join(PROJ, "gt", "feeds.py"), encoding="utf-8").read()
reg = src[src.index("REGISTRY = {"):]
reg = reg[:reg.index("\n}")]
existing = set(re.findall(r'^\s*"([a-z]+)":', reg, re.M))
check(len(existing) >= 20 and set(cy.FEEDS) == {"cyber", "bgp"} and not set(cy.FEEDS) & existing
      and all(re.match(r"^[a-z]+$", n) for n in cy.FEEDS), "FEEDS cyber + bgp: lowercase, no clash with feeds.REGISTRY")
check(cy.FEEDS["cyber"] == (cy.cyber, 900) and cy.FEEDS["bgp"] == (cy.bgp, 900) and cy.VERSION == "1.0"
      and set(cy.PUBLIC_OK) == set(cy.FEEDS) == set(cy.NON_COMMERCIAL) == set(cy.LICENCE)
      and all(n in cy.ATTRIBUTION and n in cy.ATTRIBUTION_URL for n, _, _, _ in cy.CYBER_SOURCES), "module constants")
check(cy.TIMEOUT <= 30 and "@" not in cy.UA and "mailto" not in cy.UA.lower() and "http" not in cy.UA, "UA has no contact details; timeout <= 30 s")
check(cy.CACHE == os.path.join(TMP, "cache"), "cache folder = <GT_DATA>/cache (feeds.CACHE)")


class Resp:
    def __init__(self, body, enc):
        self.body, self.headers = body, {"Content-Encoding": enc} if enc else {}

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen_req = {}


def fake_open(req, timeout=None):
    seen_req.update(ua=req.get_header("User-agent"), ae=req.get_header("Accept-encoding"), timeout=timeout)
    return Resp(gzip.compress(RAW["infocon.json"]), "gzip")


cy.urllib.request.urlopen = fake_open
check(cy._fetch(cy.ISC_INFOCON_URL) == RAW["infocon.json"] and seen_req == {"ua": cy.UA, "ae": "gzip", "timeout": 30},
      "default fetch: generic UA, gzip decoded, 30 s timeout")
cy.urllib.request.urlopen = lambda req, timeout=None: Resp(b"x" * (cy.MAX_BODY + 1), None)
check(raises(lambda: cy._fetch(cy.KEV_URL), ValueError, "over"), "oversized body refused")
cy.urllib.request.urlopen = _blocked
print("     cyber summary:", c1["summary"])
print("     bgp summary:  ", g1["summary"])
print("%d checks passed" % ok)
