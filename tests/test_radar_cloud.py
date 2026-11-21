"""Offline tests for 1.5.5: Cloudflare Radar platform outages and cloud-region traffic anomalies on the websites and
cloud layers (gt/services.py 1.1, which reads the lists gt/disruption.py 1.2 fetches for the power / cell feeds).
Sockets are blocked; nothing touches the network, and a fake Radar token is set before the import, so the real
~/.config file is never read. Fixtures:
  tests/fixtures/services/ REAL (Radar API answers of 2026-11-21, ~02:00 UTC, no token in them):
    radar_platform.json   the 8 PLATFORM-type outage annotations of the last 52 weeks (entities cut to 3; origins and
                          originsDetails whole: 80 Azure origins on the Microsoft 365 record 1749)
    radar_origins.json    traffic anomalies of the last 28 days: both ORIGIN rows (oracle-eu-frankfurt-1,
                          microsoft-uaenorth), an UNVERIFIED LOCATION row and two AS rows (one tied to an outage)
  SYNTHETIC (real field names, invented times around the clock 2026-11-21T05:00Z):
    radar_platform_synthetic.json  copies of the real records moved into the window: 9101 AWS me-south-1 active,
        9102 Google Cloud europe-west2 resolved, 9103 Microsoft 365 global (an official M365 item covers it),
        9104 Meta, 9105 Google us-central1 with an end 2 h ahead, 9106 ended 130 h ago, 9107 AWS me-central-1 (an
        official AWS item covers it), 9108 no named service and an internal link
    radar_origins_synthetic.json   ORIGIN rows: OCI Frankfurt active, Azure UAE North resolved, an UNVERIFIED one,
        one tied to annotation 9105, hetzner-fsn1 (a provider Radar's table here does not know), an Azure region
        with no city, AWS us-east-1 (an official AWS item covers it) and AWS eu-central-1
    aws_radar_synthetic.rss        two AWS status items in the window: me-central-1 and us-east-1
  tests/fixtures/services/*.json, *.rss and tests/fixtures/disruption/* serve the other sources as their own suites do.
Run: python3 -I tests/test_radar_cloud.py
"""
import copy
import datetime as dt
import json
import os
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
SFX = os.path.join(HERE, "fixtures", "services")
DFX = os.path.join(HERE, "fixtures", "disruption")
TMP = tempfile.mkdtemp()
os.environ["GT_DATA"] = TMP
os.environ["GT_SEED"] = TMP                       # no cfradar.key there
FAKE_TOKEN = "test-token-not-real-0123456789"
os.environ["CF_RADAR_TOKEN"] = FAKE_TOKEN
sys.path.insert(0, PROJ)


def _blocked(*a, **k):
    raise AssertionError("network use in an offline test")


from gt import disruption as ds  # noqa: E402
from gt import services as S  # noqa: E402
from gt import telegram  # noqa: E402

socket.socket.connect = _blocked          # after the import: ssl subclasses socket.socket
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
ds.urllib.request.urlopen = _blocked
S.urllib.request.urlopen = _blocked
ds._fetch = _blocked                      # the services feeds never fetch Radar themselves
ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


RS = {n: open(os.path.join(SFX, n), "rb").read() for n in sorted(os.listdir(SFX))}
RD = {n: open(os.path.join(DFX, n), "rb").read() for n in sorted(os.listdir(DFX))}
NOW = dt.datetime(2026, 11, 21, 5, 0, tzinfo=dt.timezone.utc)
NT = int(NOW.timestamp())
T = lambda *a: int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())
ITEM = {"id", "source", "provider", "kind", "title", "summary", "lang", "url", "ts", "ts_ms", "start_ms", "end_ms",
        "active", "severity", "status", "regions", "where", "cc", "ll", "place", "tags", "metric"}
SRC = {"name", "label", "ok", "error", "checked", "good", "newest", "n", "active"}

# ---- the shared fetch: disruption's sources, Radar answered by the synthetic files ----
D_URLS = {ds.ODIN_URL: "odin_cty.json", ds.ODIN_MAP_URL: "odin_map.json", ds.NETBLOCKS_URL: "netblocks.xml",
          ds.CFRADAR_URL: "cfradar.xml", ds.TAIPOWER_URL: "taipower.json", ds.ESKOM_URL: "eskom.txt",
          ds.CAISO_URL: "caiso.json", ds.MONITOR_RU_URL: "monitor_ru.json",
          telegram.PAGE % "Ukrenergo": "ukrenergo.html", telegram.PAGE % "energyofukraine": "minenergo.html"}
RADAR_BODY = {ds.RADAR_OUTAGES_URL: RS["radar_platform_synthetic.json"],
              ds.RADAR_ANOMALIES_URL: RS["radar_origins_synthetic.json"]}


def dfake(over=None, fail=None, log=None):
    over, fail = over or {}, fail or {}

    def fetch(url, headers):
        if log is not None:
            log.append((url, dict(headers or {})))
        if url in fail:
            raise urllib.error.HTTPError(url, fail[url], "HTTP %d" % fail[url], None, None)
        if url in over:
            return 200, {}, over[url]
        if url in RADAR_BODY:
            return 200, {}, RADAR_BODY[url]
        return 200, {}, RD[D_URLS[url]]
    return fetch


SERVE = {"github": "github.json", "zoom": "zoom.json", "slack": "slack_active.json", "paypal": "paypal.rss",
         "gworkspace": "workspace.json", "m365": "m365_active.json", "cloudflare": "cloudflare.json",
         "aws": "aws_radar_synthetic.rss", "azure": "azure.rss", "gcp": "gcp.json", "oci": "oci.rss",
         "digitalocean": "statuspage_synthetic.json", "linode": "linode.json", "hetzner": "hetzner.atom",
         "ovh": "ovh.json", "openai": "openai.json", "huggingface": "hf.rss", "lambda": "lambda.json",
         "dcd": "dcd.rss", "dck": "dck.rss", "register": "news_synthetic.rss"}
BY_URL = {S.SOURCES[k]["url"]: k for k in S.SOURCES}


def sfake(log=None):
    def f(url, etag=None, lm=None):
        k = BY_URL[url]                                  # KeyError for anything but a status source
        if log is not None:
            log.append(url)
        return RS[SERVE[k]] if k in SERVE else b'{"page": {}, "incidents": []}'
    return f


def reset(which=("d", "s")):
    for mod, w in ((ds, "d"), (S, "s")):
        p = os.path.join(TMP, "cache", mod.STATE_FILE)
        if w in which and os.path.exists(p):
            os.remove(p)
    S._INFLIGHT.clear()


def store(sources):
    """Write the disruption state as disruption.py would (to test what services.py makes of it)."""
    os.makedirs(os.path.join(TMP, "cache"), exist_ok=True)
    with open(os.path.join(TMP, "cache", ds.STATE_FILE), "w", encoding="utf-8") as f:
        json.dump({"version": ds.VERSION, "sources": sources}, f)


def radar_of(feed):
    return {i["id"].split(":", 2)[2]: i for i in feed["items"] if i["source"] in S.RADAR}


def row(feed, name):
    return next(r for r in feed["sources"] if r["name"] == name)


# ================= parsers (disruption 1.2) =================
anns = {a["id"]: a for a in ds.parse_radar_outages(RS["radar_platform.json"])}
check(sorted(anns) == ["1532", "1533", "1538", "1541", "1621", "1659", "1727", "1749"] and
      all(a["type"] == "PLATFORM" for a in anns.values()), "real: the 8 PLATFORM annotations parse")
m = anns["1749"]["origins"]
check(len(m) == 80 and m[0]["slug"].startswith("microsoft-") and m[0]["name"].startswith("Microsoft") and
      len({o["slug"] for o in m}) == 80, "real 1749: 80 Azure origins, deduplicated, with their names")
check(anns["1621"]["origins"] == [] and anns["1621"]["asns"][0]["name"] == "FACEBOOK" and
      [o["slug"] for o in anns["1727"]["origins"]] == ["google-europe-west2"],
      "real: Meta has no origin but its network; Google Cloud names europe-west2")
old = {a["id"]: a for a in ds.parse_radar_outages(RD["radar_outages.json"])}
check(old["1749"]["origins"] and old["1749"]["origins"][0]["slug"].startswith("microsoft-") and
      all(isinstance(a["origins"], list) for a in old.values()),
      "the power / cell suite's (trimmed) fixture: every annotation now carries its origins list")
anoms = {a["id"]: a for a in ds.parse_radar_anomalies(RS["radar_origins.json"])}
og = {a["origin"]["slug"]: a for a in anoms.values() if a["origin"]}
check(sorted(og) == ["microsoft-uaenorth", "oracle-eu-frankfurt-1"] and all(a["type"] == "ORIGIN" for a in og.values())
      and all(a["origin"] is None for a in anoms.values() if a["type"] != "ORIGIN"),
      "real: the two ORIGIN anomalies carry their region; LOCATION / AS rows carry none")
check(og["oracle-eu-frankfurt-1"]["status"] in ("VERIFIED", "TP") and
      og["oracle-eu-frankfurt-1"]["origin"]["name"] != "oracle-eu-frankfurt-1",
      "real: the OCI anomaly is verified and named")
check([ds._origin(s) for s in ("Bad Slug", "x", "../etc/passwd", "amazon", "-us-east-1", 7, None)] == [None] * 7 and
      ds._origin("Amazon-US-East-1", "n")["slug"] == "amazon-us-east-1" and
      ds._origin("oracle-eu-frankfurt-1")["name"] == "oracle-eu-frankfurt-1",
      "origin slugs: odd ones refused, case folded, the slug stands in for a missing name")

# ================= origin_region =================
OR = {s: S.origin_region(s) for s in ("amazon-me-central-1", "amazon-me-south-1", "google-europe-west2",
                                      "google-us-central1", "microsoft-uaenorth", "microsoft-germanywc",
                                      "microsoft-australiacentral2", "microsoft-global", "microsoft-centraluseuap",
                                      "oracle-eu-frankfurt-1", "oracle-us-ashburn-1", "hetzner-fsn1", "amazon-", "")}
check(OR["amazon-me-central-1"] == ("amazon", "me-central-1", "dubai") and
      OR["amazon-me-south-1"] == ("amazon", "me-south-1", "manama") and
      OR["google-europe-west2"] == ("google", "europe-west2", "london") and
      OR["google-us-central1"] == ("google", "us-central1", "councilbluffs"), "AWS / Google origins -> region + city")
check(OR["microsoft-uaenorth"] == ("microsoft", "UAE North", "dubai") and
      OR["microsoft-germanywc"] == ("microsoft", "Germany West Central", "frankfurt") and
      OR["microsoft-australiacentral2"] == ("microsoft", "Australia Central 2", "canberra"),
      "Azure origins: display names, Radar's short ids included")
check(OR["oracle-eu-frankfurt-1"] == ("oracle", "eu-frankfurt-1", "frankfurt") and
      OR["oracle-us-ashburn-1"][2] == "ashburn", "OCI origins -> the city in the region id")
check(OR["microsoft-global"] == ("microsoft", None, None) and OR["microsoft-centraluseuap"] == (
    "microsoft", "centraluseuap", None) and OR["hetzner-fsn1"] is None and OR["amazon-"] is None and OR[""] is None
      and S.origin_region(None) is None, "global, unknown-region and unknown-provider origins")

# ================= real records =================
P = {k: S.platform_record(a, NT) for k, a in anns.items()}
m365 = P["1749"]
check(m365["route"] == "websites" and m365["provider"] == "Microsoft 365" and m365["severity"] == "critical" and
      m365["match"] == ("m365",) and [p["place"] for p in m365["pins"]] == ["hq"] and
      m365["pins"][0]["label"] == "Global (HQ: Redmond)" and m365["codes"] == [] and m365["resolved"],
      "real 1749: Microsoft 365, websites, critical (global), pinned at the HQ, resolved")
check("Seen in traffic to 80 Microsoft Azure origins; shown at the HQ." in m365["summary"] and
      "Cause: technical problem." in m365["summary"] and m365["url"].startswith("https://x.com/CloudflareRadar/"),
      "real 1749: the summary says why it sits at the HQ; the link is Cloudflare's post")
g = P["1727"]
check(g["route"] == "cloud" and g["provider"] == "Google Cloud" and g["severity"] == "major" and
      [p["city"] for p in g["pins"]] == ["london"] and g["codes"] == ["europe-west2"] and g["match"] == ("gcp",),
      "real 1727: Google Cloud at London (europe-west2), major")
check([p["city"] for p in P["1659"]["pins"]] == ["councilbluffs"] and
      P["1659"]["url"].startswith("https://status.cloud.google.com/incidents/"),
      "real 1659: Council Bluffs; the link is Google's own incident")
check(P["1621"]["provider"] == "Meta" and P["1621"]["route"] == "websites" and P["1621"]["match"] == () and
      P["1621"]["pins"][0]["label"] == "Global (HQ: Menlo Park)", "real 1621: Meta (from its network), at Menlo Park")
check([p["city"] for k in ("1541", "1532") for p in P[k]["pins"]] == ["dubai", "dubai"] and
      [p["city"] for k in ("1538", "1533") for p in P[k]["pins"]] == ["manama", "manama"] and
      all(P[k]["provider"] == "AWS" and P[k]["route"] == "cloud" for k in ("1541", "1532", "1538", "1533")),
      "real AWS records: me-central-1 at Dubai, me-south-1 at Manama")
check(P["1538"]["title"] == "Disruption due to drone activity (AWS me-south-1)" and
      "military-action" in P["1538"]["tags"] and "power-outage" in P["1533"]["tags"] and
      all("platform" in r["tags"] and r["kind"] == "outage" for r in P.values()),
      "real: a short title gets the provider and region; the cause is a tag")
O = {og_["origin"]["slug"]: S.origin_record(og_, NT) for og_ in og.values()}
oci, az = O["oracle-eu-frankfurt-1"], O["microsoft-uaenorth"]
check(oci["title"].startswith("Traffic anomaly at ") and oci["title"].endswith("(Frankfurt)") and
      oci["url"] == "https://radar.cloudflare.com/cloud-observatory/oracle/eu-frankfurt-1" and
      oci["provider"] == "Oracle Cloud (OCI)" and oci["severity"] == "minor" and oci["match"] == ("oci",),
      "real ORIGIN: OCI Frankfurt, minor, linked to its Cloud Observatory page")
check(az["url"] == "https://radar.cloudflare.com/cloud-observatory/microsoft/uaenorth" and
      [p["city"] for p in az["pins"]] == ["dubai"] and az["codes"] == ["UAE North"] and az["resolved"],
      "real ORIGIN: Azure UAE North at Dubai, resolved")
check(all(S.origin_record(a, NT) is None for a in anoms.values() if a["type"] != "ORIGIN"),
      "LOCATION / AS anomalies are not cloud records (the power / cell feeds keep them)")


# ================= the same event: real official items =================
def official(key, name, nt):
    now = dt.datetime.fromtimestamp(nt, dt.timezone.utc)
    recs = S.PARSERS[S.SOURCES[key]["fmt"]](RS[name], now, S.SOURCES[key], None)["records"]
    out = []
    for r in recs:
        feed = S._route(key, r)
        it, pl = S.make_item(feed, key, r, nt)
        if it:
            out.append((it, pl))
    return out


def matches(rec, key, name, nt):
    return [it["id"] for it, pl in official(key, name, nt) if S.same_event(rec, it, pl, nt)]


n1 = T(2026, 11, 6, 0, 0)                     # Google's items carry their last update (postmortems come weeks later)
check(matches(S.platform_record(anns["1727"], n1), "gcp", "gcp.json", n1) == ["cloud:gcp:Xs2XTHzAVC9YnafnPyzj"],
      "real: Radar 1727 is Google's europe-west2 incident of 10-20 (same provider, time and region)")
n2 = T(2026, 10, 20, 0, 0)
check(matches(S.platform_record(anns["1659"], n2), "gcp", "gcp.json", n2) == ["cloud:gcp:J5ia5t9p3g9Q5Wi7r8Ev"],
      "real: Radar 1659 links Google's own incident J5ia5t9p3g9Q5Wi7r8Ev")
far = dict(S.platform_record(anns["1659"], n2), start=n2 - 40 * 86400, end=n2 - 39 * 86400)
check(matches(far, "gcp", "gcp.json", n2) == ["cloud:gcp:J5ia5t9p3g9Q5Wi7r8Ev"],
      "the same incident link matches even when the times do not")
n3 = T(2026, 4, 30, 12, 0)
m3 = matches(S.platform_record(anns["1541"], n3), "aws", "aws.rss", n3)
check(len(m3) == 1 and "me-central-1" in m3[0], "real: Radar 1541 (strikes) is AWS's me-central-1 item of 04-30")
check(matches(S.platform_record(anns["1533"], n3), "aws", "aws.rss", n3) == [] and
      matches(S.platform_record(anns["1727"], n3), "aws", "aws.rss", n3) == [],
      "real: an older me-south-1 record and another provider's record match nothing")

# ================= the full path: disruption fetches, services reads =================
reset()
dlog, slog = [], []
p0 = ds.power(now=NOW, fetch=dfake(log=dlog))
c0 = ds.cellular(now=NOW, fetch=dfake(log=dlog))
w = S.websites(now=NOW, fetch=sfake(log=slog))
cl = S.cloud(now=NOW, fetch=sfake(log=slog))
radar_calls = [u for u, _h in dlog if u.startswith(ds.RADAR_API)]
check(sorted(radar_calls) == sorted([ds.RADAR_OUTAGES_URL, ds.RADAR_ANOMALIES_URL]) and
      not any("cloudflare.com/client" in u for u in slog),
      "one Radar fetch per list across all four feeds; the websites / cloud feeds send none")
check(all(h.get("Authorization") == "Bearer " + FAKE_TOKEN for u, h in dlog if u.startswith(ds.RADAR_API)),
      "the token goes only in the Radar request's Authorization header")
blob = json.dumps([w, cl, p0, c0]) + open(os.path.join(TMP, "cache", S.STATE_FILE)).read() + \
    open(os.path.join(TMP, "cache", ds.STATE_FILE)).read()
check(FAKE_TOKEN not in blob, "the token is in no feed and no state file")
plat_ids = {"9101", "9102", "9103", "9104", "9105", "9106", "9107", "9108"}
check(not any(i["id"].split(":")[-1] in plat_ids for i in p0["items"] + c0["items"]),
      "the power / cell feeds still leave PLATFORM records out")
RW, RC = radar_of(w), radar_of(cl)
check(sorted(RW) == ["9104"], "websites: Meta stays; Microsoft 365 9103 is the official M365 item's event")
m365_items = [i for i in w["items"] if i["source"] == "m365"]
check(m365_items and all("radar" in i["tags"] for i in m365_items if i["active"]),
      "the official Microsoft 365 item it matched gets the 'radar' tag")
check(sorted(RC) == ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002",
                     "00000000-0000-4000-8000-000000000005", "00000000-0000-4000-8000-000000000006",
                     "00000000-0000-4000-8000-000000000008", "9101", "9102", "9105", "9108"],
      "cloud: 4 platform records and 5 region anomalies; old, unverified, outage-linked and matched ones left out")
aws = {i["regions"][0] if i["regions"] else None: i for i in cl["items"] if i["source"] == "aws"}
check(sorted(aws) == ["me-central-1", "us-east-1"] and all("radar" in i["tags"] for i in aws.values()),
      "both official AWS items carry the 'radar' tag (9107 and the us-east-1 anomaly matched them)")
check(all(set(i) == ITEM for i in list(RW.values()) + list(RC.values())) and
      all("radar" in i["tags"] and i["kind"] == "outage" for i in list(RW.values()) + list(RC.values())),
      "Radar items keep the item contract; kind 'outage', tag 'radar'")
a1, g2, g5, x8 = RC["9101"], RC["9102"], RC["9105"], RC["9108"]
check(a1["provider"] == "AWS" and a1["active"] and a1["status"] == "in effect" and a1["regions"] == ["me-south-1"] and
      a1["where"] == "Manama, BH" and a1["severity"] == "major" and a1["id"] == "cloud:radar_platform:9101",
      "9101: AWS me-south-1, in effect, at Manama")
check(not g2["active"] and g2["status"] == "resolved" and g2["ts_ms"] == T(2026, 11, 21, 4, 0) * 1000 and
      g2["end_ms"] == g2["ts_ms"], "9102: resolved an hour ago; its time is the end")
check(g5["active"] and g5["end_ms"] == (NT + 7200) * 1000 and g5["ts_ms"] == (NT - 6 * 3600) * 1000,
      "9105: an end ahead keeps it in effect (shown at its start)")
check(x8["provider"] == "Online platform" and x8["ll"] is None and x8["url"] == ds.RADAR_CENTER and
      not any(f["properties"]["pid"] == x8["id"] for f in cl["geojson"]["features"]),
      "9108: no provider named: listed, not on the map, linked to the Outage Center (never the internal host)")
o1 = RC["00000000-0000-4000-8000-000000000001"]
o5, o6 = RC["00000000-0000-4000-8000-000000000005"], RC["00000000-0000-4000-8000-000000000006"]
o8 = RC["00000000-0000-4000-8000-000000000008"]
check(o1["active"] and o1["severity"] == "minor" and o1["where"].startswith("Frankfurt") and
      o1["url"].endswith("/cloud-observatory/oracle/eu-frankfurt-1") and o1["id"].startswith("cloud:radar_origins:"),
      "OCI Frankfurt anomaly: in effect, minor, Cloud Observatory link")
check(o5["provider"] == "Hetzner" and o5["ll"] is None and o5["url"] == "https://radar.cloudflare.com/cloud-observatory"
      and o6["place"] == "hq" and o6["where"] == "Global (HQ: Redmond)" and o6["regions"] == ["centraluseuap"],
      "an unknown provider: no pin; an Azure region with no city: the HQ")
check(o8["where"].startswith("Frankfurt") and o8["provider"] == "AWS", "AWS eu-central-1: no official item there, kept")
azi = [i for i in cl["items"] if i["source"] == "azure" and i["active"]]
check(azi and azi[0]["regions"] == ["East US 2"] and "radar" not in azi[0]["tags"],
      "the Azure anomaly with no city is not merged into Azure's East US 2 incident (another region code)")
feats = {f["properties"]["pid"] for f in cl["geojson"]["features"]}
check({a1["id"], g2["id"], g5["id"], o1["id"], o6["id"], o8["id"]} <= feats and o5["id"] not in feats and
      all(f["properties"]["layer"] == "cloud" for f in cl["geojson"]["features"]),
      "GeoJSON: every pinned Radar item is a point on the cloud layer")
check("Cloudflare Radar: 1 platform outage in 72 h, 1 in effect; 1 more matched an official item." in w["summary"],
      "websites summary: 1 platform outage, 1 in effect, 1 matched")
check("Cloudflare Radar: 4 platform outages and 5 cloud-region anomalies in 72 h, 7 in effect; 2 more matched an "
      "official item." in cl["summary"], "cloud summary: 4 + 5, 7 in effect, 2 matched")
rw, rp, ro = row(w, "radar_platform"), row(cl, "radar_platform"), row(cl, "radar_origins")
check(set(rw) == SRC and set(rp) == SRC and set(ro) == SRC and rw["ok"] and rp["ok"] and ro["ok"] and
      rw["n"] == 1 and rp["n"] == 4 and rp["active"] == 3 and ro["n"] == 5 and ro["active"] == 4 and
      rp["checked"] == "2026-11-21T05:00:00Z", "source rows: ok, counts, checked = the shared fetch's time")
check([r["name"] for r in w["sources"]][-1:] == ["radar_platform"] and
      [r["name"] for r in cl["sources"]][-2:] == ["radar_platform", "radar_origins"] and
      all(r["source"] not in S.RADAR for r in cl["board"]), "Radar rows come last; the status board stays official")
check(w["attribution"].endswith("; Cloudflare Radar (platform outage annotations: CC BY-NC 4.0). Linked per item; "
                                "private, non-commercial use.") and
      "Cloudflare Radar (platform outage annotations, cloud-region traffic anomalies: CC BY-NC 4.0)" in
      cl["attribution"] and w["public_ok"] is False and cl["public_ok"] is False and w["non_commercial"] and
      cl["non_commercial"], "attribution names Radar's licence; both feeds stay private and non-commercial")
check("Cloudflare Radar" in S.NOTE["websites"] and "Cloudflare Radar" in S.NOTE["cloud"] and w["version"] == "1.1",
      "notes explain the Radar records; feed version 1.1")

# ================= rows: stale, not fetched, failed, damaged =================
later = NOW + dt.timedelta(hours=3)
cs = S.cloud(now=later, fetch=sfake())
check(not row(cs, "radar_platform")["ok"] and row(cs, "radar_platform")["error"].startswith(
    "stale: the power / cell feeds last fetched Radar at 2026-11-21T05:00:00Z") and radar_of(cs),
      "3 h without a Radar fetch: the rows say stale; the last records still show")
reset(("d",))
cn = S.cloud(now=NOW, fetch=sfake())
check(not radar_of(cn) and row(cn, "radar_origins")["error"].startswith("not fetched yet") and
      "Cloudflare Radar" not in cn["summary"] and not any("radar" in i["tags"] for i in cn["items"]),
      "no shared fetch yet: rows say so; no Radar items, tags or summary line")
reset(("d",))
ds.cellular(now=NOW, fetch=dfake(fail={ds.RADAR_OUTAGES_URL: 401}))
cf = S.cloud(now=NOW, fetch=sfake())
check(not row(cf, "radar_platform")["ok"] and "401" in row(cf, "radar_platform")["error"] and
      FAKE_TOKEN not in json.dumps(cf) and row(cf, "radar_origins")["ok"] and
      not any(i["source"] == "radar_platform" for i in cf["items"]) and
      any(i["source"] == "radar_origins" for i in cf["items"]),
      "a Radar 401: that row fails alone, the token not in the error; the anomalies still show")
bad = {"radar_outages": {"ok": True, "t": NT, "good": NT, "data": {"anns": {
    "a": "x", "b": {"type": "PLATFORM"}, "c": {"type": "PLATFORM", "id": "c", "start": "2026-11-21"},
    "d": {"type": "PLATFORM", "id": "d", "start": NT - 60, "end": "soon"},
    "e": {"type": "PLATFORM", "id": "e", "start": NT - 60, "end": None, "desc": 7, "origins": ["x", {"slug": 5}],
          "asns": ["y"]}}}},
    "radar_anomalies": {"ok": True, "t": NT, "good": NT, "data": {"anoms": [1, 2]}}}
store(bad)
cb = S.cloud(now=NOW, fetch=sfake())
check(sorted(radar_of(cb)) == ["e"] and radar_of(cb)["e"]["provider"] == "Online platform" and
      row(cb, "radar_origins")["n"] == 0, "damaged stored rows are skipped one by one; the feed is built")
open(os.path.join(TMP, "cache", ds.STATE_FILE), "w").write("{not json")
cj = S.cloud(now=NOW, fetch=sfake())
check(not radar_of(cj) and row(cj, "radar_platform")["error"].startswith("not fetched yet") and cj["items"],
      "an unreadable disruption state: no Radar, the official items stand")
real_rows = ds.radar_rows
ds.radar_rows = lambda: 1 / 0
ce = S.cloud(now=NOW, fetch=sfake())
ds.radar_rows = real_rows
check(ce["items"] and not radar_of(ce), "radar_rows() raising never fails the cloud feed")

# ================= same_event edge cases =================
rec = S.platform_record(copy.deepcopy(ds.parse_radar_outages(RS["radar_platform_synthetic.json"])[0]), NT)
it = {"source": "aws", "url": S.SOURCES["aws"]["page"], "start_ms": None, "ts_ms": (NT - 3600) * 1000,
      "end_ms": None, "active": True}
pl_far = [{"place": "region", "city": "ashburn"}]
check(rec["sid"] == "9101" and not S.same_event(rec, it, pl_far, NT) and S.same_event(rec, it, [], NT) and
      S.same_event(rec, it, [{"place": "region", "city": "manama"}], NT),
      "same_event: another region is another event; an unplaced official item counts")
check(not S.same_event(rec, dict(it, ts_ms=(rec["start"] - 4 * 3600) * 1000, active=False), [], NT) and
      not S.same_event(rec, dict(it, source="gcp"), [], NT),
      "same_event: 4 h before the record, or another provider, is not the same")
hq = dict(rec, pins=[{"place": "hq", "city": "seattle"}], codes=["me-south-1"])
check(S.same_event(hq, dict(it, regions=["ME-South-1"]), [], NT) and not S.same_event(hq, dict(it, regions=[
    "us-east-1"]), [], NT) and S.same_event(dict(hq, codes=[]), dict(it, regions=["us-east-1"]), [], NT) and
      S.same_event(dict(hq, codes=["UAE North"]), dict(it, regions=["uaenorth"]), [], NT),
      "same_event without cities: region codes decide (case and spacing ignored); no code on one side counts")
check(not S.same_event(dict(rec, url=S.SOURCES["aws"]["page"]), dict(it, ts_ms=(NT - 99 * 3600) * 1000,
                                                                      active=False), [], NT),
      "same_event: the generic status page is no link to an incident")

print("\n%d checks passed" % ok)
