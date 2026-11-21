"""Website and cloud disruption layers: official status pages, the Cloudflare PoP list and datacenter news.
v1.1, 2026-11-21 (Ground Truth 1.5.5; v1.0 came with 1.5.3). 1.1 adds Cloudflare Radar's platform outages and
cloud-region traffic anomalies (see "Cloudflare Radar" below).

Two feeds (FEEDS at the bottom), both every 300 s, sharing one cache (<GT_DATA>/cache/services_state.json). Each
source has its own cadence; a feed poll fetches only the sources that are due (the oldest first), stops fetching
after 3 failures in a row or 45 s, and uses conditional GET (ETag / Last-Modified) where the source sends them.
One failing source never fails a feed: it keeps its last good data. A feed fails only when none of its sources has
ever answered. Sources shared by both feeds (Cloudflare, Google Workspace) are fetched once by whichever feed polls
first; the two feeds may run at the same time, so the cache is re-read and merged under a lock before it is written.

`websites`: website and online-service disruptions.
  GitHub, Discord, Reddit, Zoom, Dropbox, Stripe, Atlassian Jira (Statuspage v2 incidents.json); Slack
  (api/v2.0.0/current, active incidents only); PayPal (RSS); Google Workspace (incidents.json, not Gemini);
  Microsoft 365 consumer (status.cloud.microsoft posts; only big outages are posted, usually all "Operational");
  Cloudflare service incidents (summary.json, every 15 min). Pinned at the company's HQ (place "hq", where
  "Global (HQ: San Francisco)"); when the title names a country (gt.placer) or a macro region (EU / Europe / EMEA,
  APAC, LATAM, Middle East), one pin per named place instead (place "country" / "region").
`cloud`: AI services, cloud providers, CDN PoPs and datacenter incidents.
  AWS (RSS; region from the guid, e.g. "#ec2-us-east-1_<epoch>"), Azure (RSS, active incidents only; item format
  unseen, parsed defensively, regions by display name), Google Cloud (incidents.json, region ids from the affected
  locations), Oracle OCI (RSS served as text/plain; "Service | US East (Ashburn) | ref" titles), DigitalOcean,
  Linode / Akamai Cloud, OVHcloud Public Cloud (Statuspage; regions from component names and title codes), Hetzner
  (Atom; fsn1/nbg1/hel1/ash/hil/sin in titles), Cloudflare PoP incidents (a title naming "(IAD)", pinned at the PoP
  from ref/cf_pops.json, built by tools/build_pops.py), Google Gemini (Workspace incidents whose service is
  Gemini), OpenAI, Anthropic, Mistral, Lambda (Statuspage / incident.io; Lambda's region is in its titles), Hugging
  Face (RSS), and datacenter incident headlines from DatacenterDynamics, Data Center Knowledge and The Register
  On-Prem (every 30 min). Provider regions are pinned at city-level metro coordinates from the tables below (place
  "region"); AI services and region-less incidents at the HQ; news by the first country gt.placer finds in the
  headline (+ summary), at the country centroid of web/geo/theatres.json (place "country"), not pinned without one.

Cloudflare Radar (1.1): two more rows per feed, `radar_platform` (websites, cloud) and `radar_origins` (cloud), built
from the Radar API lists gt/disruption.py already fetches every 15 min for the power and cell layers
(disruption.radar_rows(); never fetched here, so no second request). Radar data is CC BY-NC 4.0.
* PLATFORM outage annotations (one online service or cloud platform; ~8 a year, mostly single cloud regions). The
  provider comes from the description (Microsoft 365, AWS, Google Cloud, Meta ...), else the cloud origins'
  prefix ("amazon-me-central-1" -> AWS), else the networks' names. The record goes to the layer where that provider's
  own status items go (Microsoft 365, Google Workspace, Cloudflare and other websites -> websites; clouds and AI ->
  cloud; Meta -> websites; unknown -> cloud). Pinned at the provider regions its origins name (AWS / Google Cloud /
  Azure / OCI region tables below), or at the HQ when it names none, more than 4, or a "-global" origin. Severity:
  critical when global / worldwide / complete / total, else major. Linked to the annotation's own link (Cloudflare's
  post or the provider's status page), else Radar's Outage Center.
* ORIGIN traffic anomalies (Radar's automatic detection on one cloud region, "oracle-eu-frankfurt-1"): verified
  ones (VERIFIED / TP) not already tied to an annotation, pinned at the region (else the HQ), minor, on the cloud
  layer, linked to the region's Radar Cloud Observatory page.
* Active while Radar has no end or the end is ahead (status "in effect"); the window rules below apply.
* Duplicates: a Radar record is dropped when an official item of the same provider (its status source on the same
  layer) overlaps it in time (3 h slack either side) and shares a region (or either side has none), or has the
  same link; that official item gets the tag "radar". The summary counts both.
* The rows show disruption's ok / error / last fetch; a list older than 2 h reads "stale" (the items still build).

Cadence: 300 s for small JSON / RSS, 600 s for the ~300-500 KB pages (GitHub, Jira, OVH, Google Cloud, Workspace),
900 s for Linode (~815 KB) and Cloudflare's summary (~230 KB), 1800 s for news. A failing source is retried after
at most 300 s (news 900 s). Checked 2026-11-21: Statuspage pages send weak ETags; Google and Hetzner send
Last-Modified; AWS, OCI and PayPal send ETag and / or Last-Modified; incident.io pages, Slack, M365, Azure and HF send
neither. Live check: Google Cloud and GitHub answered 304 to the stored validators.
status.zoom.us redirects to www.zoomstatus.com and the Register's Atom URL to its RSS API; both are followed.

Severity
* Statuspage / incident.io impact: critical -> critical, major -> major, minor -> minor, none -> info,
  maintenance -> maintenance.
* Google (Cloud, Workspace) severity: high -> major, medium -> minor, low -> info.
* Slack type: outage -> major, incident -> minor, notice -> info. M365 status: interruption / outage -> major,
  anything else not operational -> minor.
* Text feeds (AWS, Azure, OCI, Hetzner, HF, PayPal), from the title (+ newest text): "major / complete / full /
  total / global / widespread outage" -> critical; outage, disruption, unavailable, unreachable, down, offline,
  failure -> major; "informational" -> info; anything else -> minor. AWS: "Service disruption" / "Service
  impact" -> major, "Service degradation" / "Performance issues" -> minor, "Informational message" -> info; an incident keeps the worst severity of its updates.
* Datacenter news: info. In-progress maintenance: maintenance.
Active
* Machine-status sources (Statuspage / incident.io, Google, Slack, M365): active while the status is not resolved,
  postmortem or completed and resolved_at / end is empty (Google: newest update not AVAILABLE). Sources that list
  only current incidents (Cloudflare summary, Slack, Azure, M365): an incident that disappears is marked resolved
  at that poll ("cleared" tag) and kept for the 72 h window.
* Text feeds (RSS / Atom): updates are grouped per incident (AWS per service-region, a new incident after a 48 h
  gap; others by their incident id or link). Active while the newest update does not say resolved, restored,
  mitigated, recovered, completed or "operating normally", and only for 24 h after the last update: these feeds
  never retract, so an incident that goes quiet stops counting as active (it keeps its last status word).
* Maintenance is kept only while in progress (Statuspage in_progress / verifying; Hetzner between its start and
  end; HF / PayPal when the newest update says it is under way); scheduled and completed maintenance is dropped.
  Cloudflare's per-PoP maintenance (about 30 at any time) is counted in `pops`, not listed.
* Window: items whose newest update is in the last 72 h, plus every active one up to 30 days after its start.
  Never a future item (more than 5 min ahead is dropped; less is clamped to now). Summaries are plain text.
Board: one row per provider, worst first, from its active items: critical -> major, major -> partial, minor ->
degraded, maintenance -> maintenance; info only or none active -> operational; a source that never answered ->
unknown. `pops` counts Cloudflare's PoP components (named "Ashburn, United States - (IAD)"): ~34 of ~348 are
"partial_outage" at any time, which usually only means traffic was rerouted, so they are counted, never pinned.

Not used: Downdetector (no free API, terms forbid scraping), Apple System Status (terms forbid monitoring),
health.aws.amazon.com JSON (the RSS is the supported feed). Terms: these are the providers' own public status pages
and RSS feeds, read at a modest rate and linked per item; none grants republishing, so both feeds are private
(PUBLIC_OK False) and marked non-commercial. Headlines are linked, never copied beyond title and teaser. Cloudflare
Radar's data is CC BY-NC 4.0 (attribution, non-commercial): it stays in these private, non-commercial feeds.
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zlib

from . import disruption, placer

VERSION = "1.1"
UA = "GroundTruth/1.5 (personal non-commercial OSINT dashboard)"
TIMEOUT = 15                  # s per request: 45 s budget + one last request stays under ~60 s
MAX_BODY = 8 * 1024 * 1024
TIME_BUDGET = 45              # s of fetching per feed poll
MAX_FAILS = 3                 # failures in a row that end a poll's fetching
SLACK = 60                    # s: a source due in under a minute is fetched now
WINDOW = 72 * 3600            # s: resolved items are kept this long after their newest update
ACTIVE_MAX = 30 * 86400       # s: an unresolved item older than this (from its start) is dropped
RSS_ACTIVE = 24 * 3600        # s: a text-feed incident counts as active this long after its last update
CLUSTER_GAP = 48 * 3600       # s: AWS / Azure updates for one key further apart than this are separate incidents
FUTURE_SKEW = 300             # s: timestamps up to this far ahead are clamped to now, later ones dropped
MAX_ITEMS = 400
MAX_BYTES = 300 * 1000
SUMMARY_MAX = 700

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("GT_DATA") or os.path.join(ROOT, "data")
CACHE = os.path.join(DATA_ROOT, "cache")           # the same folder as feeds.CACHE
STATE_FILE = "services_state.json"
THEATRES = os.path.join(ROOT, "web", "geo", "theatres.json")
POPS_FILE = os.path.join(ROOT, "ref", "cf_pops.json")

NON_COMMERCIAL = {"websites": True, "cloud": True}
PUBLIC_OK = {"websites": False, "cloud": False}   # no source grants republishing (contract v1)

SEV_RANK = {"critical": 4, "major": 3, "minor": 2, "maintenance": 1, "info": 0}
BOARD_OF = {"critical": "major", "major": "partial", "minor": "degraded", "maintenance": "maintenance",
            "info": "operational"}
BOARD_RANK = {"major": 0, "partial": 1, "degraded": 2, "maintenance": 3, "unknown": 4, "operational": 5}
IMPACT_SEV = {"critical": "critical", "major": "major", "minor": "minor", "none": "info", "maintenance": "maintenance"}
GOOGLE_SEV = {"high": "major", "medium": "minor", "low": "info"}

# ---------------- places ----------------
# City-level metro coordinates (lon, lat, label, ISO-3): APPROXIMATE, a city centre or the campus town a provider
# names, rounded to 0.01 deg. Enough for a map pin, never a facility location.
CITIES = {
    "ashburn": (-77.49, 39.04, "Ashburn, US", "USA"), "boydton": (-78.39, 36.67, "Boydton, US", "USA"),
    "richmond": (-77.44, 37.54, "Richmond, US", "USA"), "vinthill": (-77.67, 38.75, "Vint Hill, US", "USA"),
    "washington": (-77.04, 38.91, "Washington, US", "USA"), "newyork": (-74.01, 40.71, "New York, US", "USA"),
    "newark": (-74.17, 40.74, "Newark, US", "USA"), "cambridge": (-71.11, 42.37, "Cambridge, US", "USA"),
    "columbus": (-83.0, 39.96, "Columbus, US", "USA"), "chicago": (-87.63, 41.88, "Chicago, US", "USA"),
    "councilbluffs": (-95.86, 41.26, "Council Bluffs, US", "USA"),
    "desmoines": (-93.61, 41.59, "Des Moines, US", "USA"), "kansascity": (-94.58, 39.1, "Kansas City, US", "USA"),
    "monckscorner": (-80.01, 33.2, "Moncks Corner, US", "USA"), "atlanta": (-84.39, 33.75, "Atlanta, US", "USA"),
    "miami": (-80.19, 25.76, "Miami, US", "USA"), "dallas": (-96.8, 32.78, "Dallas, US", "USA"),
    "sanantonio": (-98.49, 29.42, "San Antonio, US", "USA"), "austin": (-97.74, 30.27, "Austin, US", "USA"),
    "cheyenne": (-104.82, 41.14, "Cheyenne, US", "USA"), "phoenix": (-112.07, 33.45, "Phoenix, US", "USA"),
    "saltlake": (-111.89, 40.76, "Salt Lake City, US", "USA"), "lasvegas": (-115.14, 36.17, "Las Vegas, US", "USA"),
    "losangeles": (-118.24, 34.05, "Los Angeles, US", "USA"), "sanjose": (-121.89, 37.34, "San Jose, US", "USA"),
    "fremont": (-121.99, 37.55, "Fremont, US", "USA"), "sanfrancisco": (-122.42, 37.77, "San Francisco, US", "USA"),
    "southsf": (-122.41, 37.65, "South San Francisco, US", "USA"),
    "mountainview": (-122.08, 37.39, "Mountain View, US", "USA"), "boardman": (-119.7, 45.84, "Boardman, US", "USA"),
    "menlopark": (-122.18, 37.45, "Menlo Park, US", "USA"),
    "thedalles": (-121.18, 45.6, "The Dalles, US", "USA"), "hillsboro": (-122.99, 45.52, "Hillsboro, US", "USA"),
    "quincy": (-119.85, 47.23, "Quincy, US", "USA"), "seattle": (-122.33, 47.61, "Seattle, US", "USA"),
    "redmond": (-122.12, 47.67, "Redmond, US", "USA"), "toronto": (-79.38, 43.65, "Toronto, CA", "CAN"),
    "montreal": (-73.57, 45.5, "Montreal, CA", "CAN"), "beauharnois": (-73.87, 45.31, "Beauharnois, CA", "CAN"),
    "quebec": (-71.21, 46.81, "Quebec City, CA", "CAN"), "calgary": (-114.07, 51.05, "Calgary, CA", "CAN"),
    "queretaro": (-100.39, 20.59, "Queretaro, MX", "MEX"), "monterrey": (-100.32, 25.69, "Monterrey, MX", "MEX"),
    "saopaulo": (-46.63, -23.55, "Sao Paulo, BR", "BRA"), "vinhedo": (-46.98, -23.03, "Vinhedo, BR", "BRA"),
    "rio": (-43.17, -22.91, "Rio de Janeiro, BR", "BRA"), "santiago": (-70.67, -33.45, "Santiago, CL", "CHL"),
    "valparaiso": (-71.62, -33.05, "Valparaiso, CL", "CHL"), "bogota": (-74.07, 4.71, "Bogota, CO", "COL"),
    "dublin": (-6.26, 53.35, "Dublin, IE", "IRL"), "london": (-0.13, 51.51, "London, GB", "GBR"),
    "cardiff": (-3.18, 51.48, "Cardiff, GB", "GBR"), "newport": (-3.0, 51.58, "Newport, GB", "GBR"),
    "paris": (2.35, 48.86, "Paris, FR", "FRA"), "marseille": (5.37, 43.3, "Marseille, FR", "FRA"),
    "gravelines": (2.13, 50.99, "Gravelines, FR", "FRA"), "roubaix": (3.17, 50.69, "Roubaix, FR", "FRA"),
    "strasbourg": (7.75, 48.57, "Strasbourg, FR", "FRA"), "brussels": (4.35, 50.85, "Brussels, BE", "BEL"),
    "stghislain": (3.82, 50.45, "St. Ghislain, BE", "BEL"), "amsterdam": (4.9, 52.37, "Amsterdam, NL", "NLD"),
    "eemshaven": (6.83, 53.44, "Eemshaven, NL", "NLD"), "frankfurt": (8.68, 50.11, "Frankfurt, DE", "DEU"),
    "limburg": (8.06, 50.39, "Limburg, DE", "DEU"), "berlin": (13.4, 52.52, "Berlin, DE", "DEU"),
    "brandenburg": (12.53, 52.41, "Brandenburg, DE", "DEU"), "falkenstein": (12.37, 50.48, "Falkenstein, DE", "DEU"),
    "nuremberg": (11.08, 49.45, "Nuremberg, DE", "DEU"), "gunzenhausen": (10.75, 49.12, "Gunzenhausen, DE", "DEU"),
    "zurich": (8.54, 47.38, "Zurich, CH", "CHE"), "geneva": (6.14, 46.2, "Geneva, CH", "CHE"),
    "milan": (9.19, 45.46, "Milan, IT", "ITA"), "turin": (7.69, 45.07, "Turin, IT", "ITA"),
    "madrid": (-3.7, 40.42, "Madrid, ES", "ESP"), "zaragoza": (-0.88, 41.65, "Zaragoza, ES", "ESP"),
    "vienna": (16.37, 48.21, "Vienna, AT", "AUT"), "warsaw": (21.01, 52.23, "Warsaw, PL", "POL"),
    "copenhagen": (12.57, 55.68, "Copenhagen, DK", "DNK"), "oslo": (10.75, 59.91, "Oslo, NO", "NOR"),
    "stavanger": (5.73, 58.97, "Stavanger, NO", "NOR"), "stockholm": (18.07, 59.33, "Stockholm, SE", "SWE"),
    "gavle": (17.14, 60.67, "Gavle, SE", "SWE"), "helsinki": (24.94, 60.17, "Helsinki, FI", "FIN"),
    "hamina": (27.2, 60.57, "Hamina, FI", "FIN"), "athens": (23.73, 37.98, "Athens, GR", "GRC"),
    "telaviv": (34.78, 32.09, "Tel Aviv, IL", "ISR"), "jerusalem": (35.21, 31.77, "Jerusalem, IL", "ISR"),
    "manama": (50.59, 26.23, "Manama, BH", "BHR"), "dubai": (55.27, 25.2, "Dubai, AE", "ARE"),
    "abudhabi": (54.37, 24.45, "Abu Dhabi, AE", "ARE"), "doha": (51.53, 25.29, "Doha, QA", "QAT"),
    "dammam": (50.1, 26.43, "Dammam, SA", "SAU"), "riyadh": (46.68, 24.71, "Riyadh, SA", "SAU"),
    "jeddah": (39.17, 21.49, "Jeddah, SA", "SAU"), "johannesburg": (28.05, -26.2, "Johannesburg, ZA", "ZAF"),
    "capetown": (18.42, -33.92, "Cape Town, ZA", "ZAF"), "mumbai": (72.88, 19.08, "Mumbai, IN", "IND"),
    "pune": (73.86, 18.52, "Pune, IN", "IND"), "hyderabad": (78.49, 17.39, "Hyderabad, IN", "IND"),
    "chennai": (80.27, 13.08, "Chennai, IN", "IND"), "bangalore": (77.59, 12.97, "Bangalore, IN", "IND"),
    "delhi": (77.21, 28.61, "Delhi, IN", "IND"), "jamnagar": (70.06, 22.47, "Jamnagar, IN", "IND"),
    "nagpur": (79.09, 21.15, "Nagpur, IN", "IND"), "singapore": (103.82, 1.35, "Singapore", "SGP"),
    "jakarta": (106.85, -6.21, "Jakarta, ID", "IDN"), "kualalumpur": (101.69, 3.14, "Kuala Lumpur, MY", "MYS"),
    "bangkok": (100.5, 13.76, "Bangkok, TH", "THA"), "hongkong": (114.17, 22.32, "Hong Kong", "HKG"),
    "taipei": (121.56, 25.03, "Taipei, TW", "TWN"), "changhua": (120.54, 24.07, "Changhua, TW", "TWN"),
    "tokyo": (139.69, 35.68, "Tokyo, JP", "JPN"), "osaka": (135.5, 34.69, "Osaka, JP", "JPN"),
    "seoul": (126.98, 37.57, "Seoul, KR", "KOR"), "chuncheon": (127.73, 37.88, "Chuncheon, KR", "KOR"),
    "busan": (129.08, 35.18, "Busan, KR", "KOR"), "beijing": (116.41, 39.9, "Beijing, CN", "CHN"),
    "shanghai": (121.47, 31.23, "Shanghai, CN", "CHN"), "zhongwei": (105.19, 37.51, "Zhongwei, CN", "CHN"),
    "sydney": (151.21, -33.87, "Sydney, AU", "AUS"), "melbourne": (144.96, -37.81, "Melbourne, AU", "AUS"),
    "canberra": (149.13, -35.28, "Canberra, AU", "AUS"), "auckland": (174.76, -36.85, "Auckland, NZ", "NZL"),
}
CITY_ALIASES = {"sao paulo": "saopaulo", "bengaluru": "bangalore", "nurnberg": "nuremberg", "frankfurt am main":
                "frankfurt", "washington dc": "washington", "washington, dc": "washington", "new york city": "newyork",
                "salt lake city": "saltlake", "kuala lumpur": "kualalumpur", "hong kong": "hongkong",
                "tel aviv": "telaviv", "abu dhabi": "abudhabi", "cape town": "capetown", "san jose": "sanjose",
                "san francisco": "sanfrancisco", "los angeles": "losangeles", "las vegas": "lasvegas",
                "new york": "newyork", "rio de janeiro": "rio", "quebec city": "quebec", "montréal": "montreal"}

# Region code -> CITIES key, from each provider's public region list (approximate metro, see above).
AWS_REGIONS = {
    "us-east-1": "ashburn", "us-east-2": "columbus", "us-west-1": "sanjose", "us-west-2": "boardman",
    "us-gov-east-1": "columbus", "us-gov-west-1": "boardman", "ca-central-1": "montreal", "ca-west-1": "calgary",
    "mx-central-1": "queretaro", "sa-east-1": "saopaulo", "eu-west-1": "dublin", "eu-west-2": "london",
    "eu-west-3": "paris", "eu-central-1": "frankfurt", "eu-central-2": "zurich", "eu-south-1": "milan",
    "eu-south-2": "zaragoza", "eu-north-1": "stockholm", "eusc-de-east-1": "brandenburg", "il-central-1": "telaviv",
    "me-south-1": "manama", "me-central-1": "dubai", "af-south-1": "capetown", "ap-south-1": "mumbai",
    "ap-south-2": "hyderabad", "ap-east-1": "hongkong", "ap-east-2": "taipei", "ap-southeast-1": "singapore",
    "ap-southeast-2": "sydney", "ap-southeast-3": "jakarta", "ap-southeast-4": "melbourne",
    "ap-southeast-5": "kualalumpur", "ap-southeast-6": "auckland", "ap-southeast-7": "bangkok",
    "ap-northeast-1": "tokyo", "ap-northeast-2": "seoul", "ap-northeast-3": "osaka", "cn-north-1": "beijing",
    "cn-northwest-1": "zhongwei",
}
GCP_REGIONS = {
    "africa-south1": "johannesburg", "asia-east1": "changhua", "asia-east2": "hongkong", "asia-northeast1": "tokyo",
    "asia-northeast2": "osaka", "asia-northeast3": "seoul", "asia-south1": "mumbai", "asia-south2": "delhi",
    "asia-southeast1": "singapore", "asia-southeast2": "jakarta", "asia-southeast3": "bangkok",
    "australia-southeast1": "sydney", "australia-southeast2": "melbourne", "europe-central2": "warsaw",
    "europe-north1": "hamina", "europe-north2": "stockholm", "europe-southwest1": "madrid",
    "europe-west1": "stghislain", "europe-west2": "london", "europe-west3": "frankfurt", "europe-west4": "eemshaven",
    "europe-west6": "zurich", "europe-west8": "milan", "europe-west9": "paris", "europe-west10": "berlin",
    "europe-west12": "turin", "me-central1": "doha", "me-central2": "dammam", "me-west1": "telaviv",
    "northamerica-northeast1": "montreal", "northamerica-northeast2": "toronto", "northamerica-south1": "queretaro",
    "southamerica-east1": "saopaulo", "southamerica-west1": "santiago", "us-central1": "councilbluffs",
    "us-east1": "monckscorner", "us-east4": "ashburn", "us-east5": "columbus", "us-south1": "dallas",
    "us-west1": "thedalles", "us-west2": "losangeles", "us-west3": "saltlake", "us-west4": "lasvegas",
}
AZURE_REGIONS = {
    "East US": "boydton", "East US 2": "boydton", "Central US": "desmoines", "North Central US": "chicago",
    "South Central US": "sanantonio", "West Central US": "cheyenne", "West US": "sanfrancisco", "West US 2": "quincy",
    "West US 3": "phoenix", "Canada Central": "toronto", "Canada East": "quebec", "Brazil South": "saopaulo",
    "Brazil Southeast": "rio", "Mexico Central": "queretaro", "Chile Central": "santiago", "North Europe": "dublin",
    "West Europe": "amsterdam", "UK South": "london", "UK West": "cardiff", "France Central": "paris",
    "France South": "marseille", "Germany West Central": "frankfurt", "Germany North": "berlin",
    "Switzerland North": "zurich", "Switzerland West": "geneva", "Norway East": "oslo", "Norway West": "stavanger",
    "Sweden Central": "gavle", "Poland Central": "warsaw", "Italy North": "milan", "Spain Central": "madrid",
    "Austria East": "vienna", "Belgium Central": "brussels", "Denmark East": "copenhagen",
    "Greece Central": "athens", "Israel Central": "telaviv", "Qatar Central": "doha", "UAE North": "dubai",
    "UAE Central": "abudhabi", "South Africa North": "johannesburg", "South Africa West": "capetown",
    "Central India": "pune", "South India": "chennai", "West India": "mumbai", "Jio India West": "jamnagar",
    "Jio India Central": "nagpur", "East Asia": "hongkong", "Southeast Asia": "singapore", "Japan East": "tokyo",
    "Japan West": "osaka", "Korea Central": "seoul", "Korea South": "busan", "Australia East": "sydney",
    "Australia Southeast": "melbourne", "Australia Central": "canberra", "Australia Central 2": "canberra",
    "Indonesia Central": "jakarta", "Malaysia West": "kualalumpur", "New Zealand North": "auckland",
    "Taiwan North": "taipei", "China East": "shanghai", "China East 2": "shanghai", "China North": "beijing",
    "China North 2": "beijing", "US Gov Virginia": "boydton", "US Gov Arizona": "phoenix",
    "US Gov Texas": "sanantonio",
}
DO_REGIONS = {"NYC": "newyork", "SFO": "sanfrancisco", "AMS": "amsterdam", "SGP": "singapore", "LON": "london",
              "FRA": "frankfurt", "TOR": "toronto", "BLR": "bangalore", "SYD": "sydney", "ATL": "atlanta",
              "MKC": "kansascity", "RIC": "richmond"}
# IATA-style metro codes used inside provider region names (Linode "US-ORD", OVH "US-WEST-LZ-LAX")
IATA_CITY = {
    "ORD": "chicago", "CHI": "chicago", "SEA": "seattle", "CGK": "jakarta", "SIN": "singapore", "PAR": "paris",
    "CDG": "paris", "MAA": "chennai", "BOM": "mumbai", "MUM": "mumbai", "GRU": "saopaulo", "IAD": "washington",
    "WAS": "washington", "MIA": "miami", "LAX": "losangeles", "LON": "london", "LHR": "london", "MEL": "melbourne",
    "FRA": "frankfurt", "TYO": "tokyo", "NRT": "tokyo", "OSA": "osaka", "KIX": "osaka", "AMS": "amsterdam",
    "MAD": "madrid", "MIL": "milan", "MXP": "milan", "STO": "stockholm", "ARN": "stockholm", "EWR": "newark",
    "NYC": "newyork", "JFK": "newyork", "DFW": "dallas", "DAL": "dallas", "ATL": "atlanta", "YYZ": "toronto",
    "TOR": "toronto", "YUL": "montreal", "SYD": "sydney", "BRU": "brussels", "ZRH": "zurich", "VIE": "vienna",
    "WAW": "warsaw", "CPH": "copenhagen", "HEL": "helsinki", "OSL": "oslo", "MRS": "marseille", "SLC": "saltlake",
    "PHX": "phoenix", "LAS": "lasvegas", "SJC": "sanjose", "SFO": "sanfrancisco", "BOS": "cambridge",
    "DEL": "delhi", "HYD": "hyderabad", "BLR": "bangalore", "ICN": "seoul", "SEL": "seoul", "HKG": "hongkong",
    "TPE": "taipei", "BKK": "bangkok", "KUL": "kualalumpur", "JNB": "johannesburg", "CPT": "capetown",
    "DXB": "dubai", "AUH": "abudhabi", "DOH": "doha", "TLV": "telaviv", "BAH": "manama", "SCL": "santiago",
    "BOG": "bogota", "QRO": "queretaro", "MTY": "monterrey", "AKL": "auckland",
}
LINODE_LEGACY = {"US-EAST": "newark", "US-CENTRAL": "dallas", "US-WEST": "fremont", "US-SOUTHEAST": "atlanta",
                 "CA-CENTRAL": "toronto", "EU-WEST": "london", "EU-CENTRAL": "frankfurt", "AP-SOUTH": "singapore",
                 "AP-NORTHEAST": "tokyo", "AP-WEST": "mumbai", "AP-SOUTHEAST": "sydney"}
OVH_SITES = {"GRA": "gravelines", "RBX": "roubaix", "SBG": "strasbourg", "BHS": "beauharnois", "WAW": "warsaw",
             "DE": "limburg", "LIM": "limburg", "UK": "london", "ERI": "london", "SGP": "singapore", "SYD": "sydney"}
OVH_TOKENS = {"OR": "hillsboro", "VA": "vinthill", "TOR": "toronto", "PAR": "paris", "MIL": "milan",
              "MUM": "mumbai", "SYD": "sydney", "SGP": "singapore"}
HETZNER_SITES = {"FSN": "falkenstein", "NBG": "nuremberg", "HEL": "helsinki", "ASH": "ashburn", "HIL": "hillsboro",
                 "SIN": "singapore"}
HETZNER_NAMES = {"falkenstein": "FSN", "nuremberg": "NBG", "nürnberg": "NBG", "helsinki": "HEL",
                 "ashburn": "ASH", "hillsboro": "HIL", "singapore": "SIN"}
# Lambda names regions, not cities: a representative metro for the region's direction (approximate).
LAMBDA_PREFIX = (("us-east", "ashburn"), ("us-west-1", "sanjose"), ("us-west-2", "phoenix"),
                 ("us-west-3", "saltlake"), ("us-west", "sanjose"), ("us-southeast", "atlanta"), ("us-south", "dallas"),
                 ("us-midwest", "chicago"), ("europe-central", "frankfurt"), ("europe", "frankfurt"),
                 ("asia-south", "mumbai"), ("asia-northeast-1", "tokyo"), ("asia-northeast-2", "seoul"),
                 ("asia", "tokyo"), ("me-", "telaviv"), ("australia", "sydney"))
# Macro regions named in website titles (a representative point; approximate)
MACRO = ((re.compile(r"\b(?:EU\d*|EMEA|[Ee]urope(?:an)?)\b"), (10.0, 50.0, "Europe")),
         (re.compile(r"\b(?:APAC|APJ|[Aa]sia[- ][Pp]acific)\b"), (103.82, 1.35, "Asia-Pacific")),
         (re.compile(r"\b(?:LATAM|[Ll]atin America)\b"), (-46.63, -23.55, "Latin America")),
         (re.compile(r"\b[Mm]iddle East\b"), (55.27, 25.2, "Middle East")))

# ---------------- sources ----------------
# key -> label, provider, format, url, every s, retry s, status page, region family, HQ (CITIES key), tags
SOURCES = {}


def _src(key, label, provider, fmt, url, every, page, family=None, hq=None, tags=(), retry=None):
    SOURCES[key] = {"key": key, "label": label, "provider": provider, "fmt": fmt, "url": url, "every": every,
                    "retry": retry or min(every, 300), "page": page, "family": family, "hq": hq, "tags": list(tags)}


def _sp(key, label, provider, base, every, family=None, hq=None, tags=()):
    _src(key, label, provider, "statuspage", base + "/api/v2/incidents.json", every, base, family, hq, tags)
    SOURCES[key]["base"] = base


_sp("github", "GitHub status", "GitHub", "https://www.githubstatus.com", 600, hq="sanfrancisco")
_sp("discord", "Discord status", "Discord", "https://discordstatus.com", 300, hq="sanfrancisco")
_sp("reddit", "Reddit status", "Reddit", "https://www.redditstatus.com", 300, hq="sanfrancisco")
_sp("zoom", "Zoom status", "Zoom", "https://status.zoom.us", 300, hq="sanjose")
_sp("dropbox", "Dropbox status", "Dropbox", "https://status.dropbox.com", 300, hq="sanfrancisco")
_sp("stripe", "Stripe status", "Stripe", "https://www.stripestatus.com", 300, hq="southsf", tags=("payments",))
_sp("jira", "Atlassian Jira status", "Atlassian Jira", "https://jira-software.status.atlassian.com", 600, hq="sydney")
_src("slack", "Slack status API", "Slack", "slack", "https://slack-status.com/api/v2.0.0/current", 300,
     "https://slack-status.com", hq="sanfrancisco")
_src("paypal", "PayPal status RSS", "PayPal", "paypal", "https://www.paypal-status.com/feed/rss", 300,
     "https://www.paypal-status.com", hq="sanjose", tags=("payments",))
_src("gworkspace", "Google Workspace status", "Google Workspace", "google",
     "https://www.google.com/appsstatus/dashboard/incidents.json", 600, "https://www.google.com/appsstatus/dashboard/",
     hq="mountainview")
_src("m365", "Microsoft 365 consumer status", "Microsoft 365 (consumer)", "m365",
     "https://status.cloud.microsoft/api/posts/m365Consumer", 300, "https://status.cloud.microsoft", hq="redmond")
_src("cloudflare", "Cloudflare status (summary)", "Cloudflare", "cloudflare",
     "https://www.cloudflarestatus.com/api/v2/summary.json", 900, "https://www.cloudflarestatus.com",
     hq="sanfrancisco", tags=("cdn",))
SOURCES["cloudflare"]["base"] = "https://www.cloudflarestatus.com"
_src("aws", "AWS Health Dashboard RSS", "AWS", "aws", "https://status.aws.amazon.com/rss/all.rss", 300,
     "https://health.aws.amazon.com/health/status", family="aws", hq="seattle")
_src("azure", "Azure status RSS", "Microsoft Azure", "azure", "https://rssfeed.azure.status.microsoft/en-us/status/feed/",
     300, "https://azure.status.microsoft/en-us/status/", family="azure", hq="redmond")
_src("gcp", "Google Cloud status", "Google Cloud", "google", "https://status.cloud.google.com/incidents.json", 600,
     "https://status.cloud.google.com", family="gcp", hq="mountainview")
_src("oci", "Oracle Cloud status RSS", "Oracle Cloud (OCI)", "oci",
     "https://ocistatus.oraclecloud.com/api/v2/incident-summary.rss", 300, "https://ocistatus.oraclecloud.com",
     family="oci", hq="austin")
_sp("digitalocean", "DigitalOcean status", "DigitalOcean", "https://status.digitalocean.com", 300, family="do",
    hq="newyork")
_sp("linode", "Akamai Cloud (Linode) status", "Akamai Cloud (Linode)", "https://status.linode.com", 900,
    family="linode", hq="cambridge")
_src("hetzner", "Hetzner status Atom", "Hetzner", "hetzner", "https://status.hetzner.com/en.atom", 300,
     "https://status.hetzner.com", family="hetzner", hq="gunzenhausen")
_sp("ovh", "OVHcloud Public Cloud status", "OVHcloud", "https://public-cloud.status-ovhcloud.com", 600,
    family="ovh", hq="roubaix")
_sp("openai", "OpenAI status", "OpenAI", "https://status.openai.com", 300, hq="sanfrancisco", tags=("ai",))
_sp("anthropic", "Anthropic (Claude) status", "Anthropic", "https://status.claude.com", 300, hq="sanfrancisco",
    tags=("ai",))
_sp("mistral", "Mistral AI status", "Mistral AI", "https://status.mistral.ai", 300, hq="paris", tags=("ai",))
_src("huggingface", "Hugging Face status RSS", "Hugging Face", "hf", "https://status.huggingface.co/feed.rss", 300,
     "https://status.huggingface.co", hq="newyork", tags=("ai",))
_sp("lambda", "Lambda GPU Cloud status", "Lambda", "https://status.lambda.com", 300, family="lambda", hq="sanjose",
    tags=("ai", "gpu"))
_src("dcd", "DatacenterDynamics RSS", "DatacenterDynamics", "news", "https://www.datacenterdynamics.com/en/rss/", 1800,
     "https://www.datacenterdynamics.com", tags=("datacenter",), retry=900)
_src("dck", "Data Center Knowledge RSS", "Data Center Knowledge", "news", "https://www.datacenterknowledge.com/rss.xml",
     1800, "https://www.datacenterknowledge.com", tags=("datacenter",), retry=900)
_src("register", "The Register On-Prem", "The Register", "news", "https://www.theregister.com/on_prem/headlines.atom",
     1800, "https://www.theregister.com/on_prem/", tags=("datacenter",), retry=900)

FEED_SOURCES = {
    "websites": ("github", "discord", "reddit", "zoom", "dropbox", "stripe", "jira", "slack", "paypal", "gworkspace",
                 "m365", "cloudflare"),
    "cloud": ("aws", "azure", "gcp", "oci", "digitalocean", "linode", "hetzner", "ovh", "cloudflare", "gworkspace",
              "openai", "anthropic", "mistral", "huggingface", "lambda", "dcd", "dck", "register"),
}
SPLIT = {"cloudflare": "websites", "gworkspace": "websites"}   # default route of a source serving both feeds
FEED_PROVIDER = {("cloud", "cloudflare"): "Cloudflare network (PoPs)", ("cloud", "gworkspace"): "Google Gemini"}
FEED_TAGS = {("cloud", "cloudflare"): ["pop"], ("cloud", "gworkspace"): ["ai"]}
NOTE = {
    "websites": ("Official status pages of major websites and online services. Incidents updated in the last 72 h "
                 "plus every unresolved one (up to 30 days). Global services are pinned at the company's HQ; a "
                 "country or macro region named in the title moves the pin there (one pin per place). Severity "
                 "follows each page's own impact (critical/major/minor/none -> critical/major/minor/info). "
                 "Maintenance is listed only while in progress. RSS sources (PayPal) count an incident as active "
                 "for 24 h after its last update unless it says resolved. Slack, M365 and Cloudflare list only "
                 "current incidents: one that disappears is marked resolved then. Cloudflare Radar adds the platform "
                 "outages it records for websites and online services (Microsoft 365, Meta ...), from the cell "
                 "layer's Radar fetch; one that matches an official item of the same provider and time is left out."),
    "cloud": ("Cloud, AI-service and datacenter disruptions from the providers' own status pages, pinned at the "
              "named region's metro (approximate) or, for global and AI services, at the HQ. Cloudflare incidents "
              "that name a PoP code such as (IAD) are pinned at that PoP; PoPs shown as partial outage on "
              "Cloudflare's list usually only reroute traffic, so they are counted, not pinned. AWS, Azure, OCI, "
              "Hetzner and Hugging Face are RSS/Atom: an incident counts as active for 24 h after its last update "
              "unless it says resolved, restored or mitigated. Datacenter news: incident headlines only (outage, "
              "fire, power or cooling failure, flood, explosion, attack, sabotage, evacuation), placed by country. "
              "Cloudflare Radar adds its platform outage records for clouds and AI services and the traffic "
              "anomalies it verifies on single cloud regions (AWS, Google Cloud, Azure, Oracle), pinned at the "
              "region or the HQ, active until Radar records an end; one that matches an official item of the same "
              "provider, time and region is left out."),
}

# ---------------- Cloudflare Radar (1.1) ----------------
# Not fetched here: disruption.radar_rows() lends the lists the power / cell feeds fetch. Shaped like SOURCES rows.
RADAR = {
    "radar_platform": {"key": "radar_platform", "label": "Cloudflare Radar platform outages", "provider": "Cloudflare Radar",
                       "fmt": "radar", "url": None, "every": None, "retry": None, "page": disruption.RADAR_CENTER,
                       "family": None, "hq": None, "tags": ["radar"], "from": "radar_outages"},
    "radar_origins": {"key": "radar_origins", "label": "Cloudflare Radar cloud-region anomalies",
                      "provider": "Cloudflare Radar", "fmt": "radar", "url": None, "every": None, "retry": None,
                      "page": "https://radar.cloudflare.com/cloud-observatory", "family": None, "hq": None,
                      "tags": ["radar"], "from": "radar_anomalies"},
}
FEED_RADAR = {"websites": ("radar_platform",), "cloud": ("radar_platform", "radar_origins")}
RADAR_CLOUD = "https://radar.cloudflare.com/cloud-observatory/%s/%s"   # provider prefix, region ("oracle", "eu-frankfurt-1")
RADAR_STALE = 2 * 3600        # s: lists the power / cell feeds stored longer ago than this make the row "stale"
RADAR_SLACK = 3 * 3600        # s: an official item this close to a Radar record's span is the same event
RADAR_GLOBAL = 4              # a platform record naming more provider regions than this is pinned at the HQ
# Radar origin prefix -> (provider, region family, HQ, the provider's status source here)
ORIGIN_PROVIDER = {"amazon": ("AWS", "aws", "seattle", "aws"), "google": ("Google Cloud", "gcp", "mountainview", "gcp"),
                   "microsoft": ("Microsoft Azure", "azure", "redmond", "azure"),
                   "oracle": ("Oracle Cloud (OCI)", "oci", "austin", "oci")}
# Radar's short Azure origin ids that are not the display name without spaces
AZURE_SHORT = {"brazilse": "Brazil Southeast", "germanyn": "Germany North", "germanywc": "Germany West Central",
               "norwaye": "Norway East", "norwayw": "Norway West", "chilec": "Chile Central",
               "switzerlandn": "Switzerland North", "switzerlandw": "Switzerland West", "centralfrance": "France Central",
               "southfrance": "France South"}
# A platform annotation's description (or network names) -> its provider: (pattern, status source here or None,
# provider, layer, HQ). First match wins, so Microsoft 365 comes before Azure and Gemini before Workspace.
_PLAT = (
    (r"(?i)Microsoft 365|Office 365|Exchange Online|\bOutlook\b|Microsoft Teams|OneDrive|SharePoint", "m365",
     "Microsoft 365", "websites", "redmond"),
    (r"(?i)\bGemini\b", "gworkspace", "Google Gemini", "cloud", "mountainview"),
    (r"(?i)Google Workspace|\bGmail\b|Google (?:Drive|Meet|Docs|Calendar)", "gworkspace", "Google Workspace", "websites",
     "mountainview"),
    (r"(?i)\bAzure\b", "azure", "Microsoft Azure", "cloud", "redmond"),
    (r"\bAWS\b|(?i:Amazon Web Services)", "aws", "AWS", "cloud", "seattle"),
    (r"(?i)Google Cloud|\bGCP\b", "gcp", "Google Cloud", "cloud", "mountainview"),
    (r"(?i)Oracle Cloud|\bOCI\b", "oci", "Oracle Cloud (OCI)", "cloud", "austin"),
    (r"(?i)DigitalOcean", "digitalocean", "DigitalOcean", "cloud", "newyork"),
    (r"(?i)\bLinode\b|Akamai", "linode", "Akamai Cloud (Linode)", "cloud", "cambridge"),
    (r"(?i)Hetzner", "hetzner", "Hetzner", "cloud", "gunzenhausen"),
    (r"(?i)\bOVH", "ovh", "OVHcloud", "cloud", "roubaix"),
    (r"(?i)OpenAI|ChatGPT", "openai", "OpenAI", "cloud", "sanfrancisco"),
    (r"(?i)Anthropic|\bClaude\b", "anthropic", "Anthropic", "cloud", "sanfrancisco"),
    (r"(?i)Mistral", "mistral", "Mistral AI", "cloud", "paris"),
    (r"(?i)Hugging ?Face", "huggingface", "Hugging Face", "cloud", "newyork"),
    (r"(?i)Cloudflare", "cloudflare", "Cloudflare", "websites", "sanfrancisco"),
    (r"(?i)GitHub", "github", "GitHub", "websites", "sanfrancisco"),
    (r"(?i)Discord", "discord", "Discord", "websites", "sanfrancisco"),
    (r"(?i)Reddit", "reddit", "Reddit", "websites", "sanfrancisco"),
    (r"(?i)\bZoom\b", "zoom", "Zoom", "websites", "sanjose"),
    (r"(?i)Dropbox", "dropbox", "Dropbox", "websites", "sanfrancisco"),
    (r"(?i)\bStripe\b", "stripe", "Stripe", "websites", "southsf"),
    (r"(?i)Atlassian|\bJira\b", "jira", "Atlassian Jira", "websites", "sydney"),
    (r"(?i)\bSlack\b", "slack", "Slack", "websites", "sanfrancisco"),
    (r"(?i)PayPal", "paypal", "PayPal", "websites", "sanjose"),
    (r"\bMeta\b|(?i:Facebook|Instagram|WhatsApp|Messenger)", None, "Meta", "websites", "menlopark"),
)
PLATFORMS = tuple((re.compile(rx), key, prov, layer, hq) for rx, key, prov, layer, hq in _PLAT)

# ---------------- helpers ----------------

_LOCK = threading.Lock()
_INFLIGHT = set()
_CACHE = {}


def _gunzip(body, limit=MAX_BODY):
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(body, limit + 1)
    if len(out) > limit:
        raise ValueError("decompressed response over %d bytes" % limit)
    return out


def _fetch(url, etag=None, lm=None):
    """GET with gzip and conditional headers -> {"status": 200, "body", "etag", "lm"} or {"status": 304}."""
    h = {"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "*/*"}
    if etag:
        h["If-None-Match"] = etag
    if lm:
        h["If-Modified-Since"] = lm
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=TIMEOUT) as r:
            body = r.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ValueError("response over %d bytes" % MAX_BODY)
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = _gunzip(body)
            return {"status": getattr(r, "status", 200) or 200, "body": body, "etag": r.headers.get("ETag"),
                    "lm": r.headers.get("Last-Modified")}
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return {"status": 304}
        raise


def _utc(now):
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)


def _iso(t):
    return dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_RX_TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")


def _ts(s):
    """Epoch seconds for ISO 8601 ('YYYY-MM-DD[THH:MM[:SS[.f]]][Z|+HH:MM]', naive = UTC), else None (also before 2000)."""
    if not s or not isinstance(s, str):
        return None
    m = _RX_TS.match(s.strip())
    if not m:
        return None
    y, mo, d, h, mi, sec, tz = m.groups()
    try:
        t = dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(sec or 0), tzinfo=dt.timezone.utc)
    except ValueError:
        return None
    off = 0
    if tz and tz != "Z":
        tz = tz.replace(":", "")
        off = (1 if tz[0] == "+" else -1) * (int(tz[1:3]) * 3600 + int(tz[3:5]) * 60)
    out = int(t.timestamp()) - off
    return out if out >= 946684800 else None


def _rfc822(s):
    try:
        t = email.utils.parsedate_to_datetime((s or "").strip())
    except (TypeError, ValueError, IndexError):
        return None
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    out = int(t.timestamp())
    return out if out >= 946684800 else None


def _when(s):
    return _ts(s) or _rfc822(s)


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


_RX_TAG = re.compile(r"(?s)<[^>]*>")
_RX_MD = re.compile(r"\*\*|__|`+|^#+\s*|(?<=\s)#+\s+", re.M)
_RX_MDLINK = re.compile(r"\[([^\]]*)\]\((?:https?://)?[^)]*\)")
_RX_MDESC = re.compile(r"\\([#*_\[\]()`>~|-])")


def _text(s, n=None):
    """Plain text: tags stripped (before and after unescaping), markdown markers dropped, whitespace collapsed."""
    s = str(s or "")
    s = _RX_TAG.sub(" ", s)
    s = html.unescape(s)
    s = _RX_TAG.sub(" ", s)
    s = _RX_MDESC.sub(r"\1", s)
    s = _RX_MDLINK.sub(r"\1", s)
    s = _RX_MD.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return _clip(s, n) if n else s


def _err(e):
    return _clip("%s: %s" % (type(e).__name__, e), 200)


def _sha(s, n=12):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _city_by_name(name):
    f = _fold(re.sub(r"\s*\d+$", "", str(name or "").strip()))
    f = re.sub(r",\s*[a-z]{2}$", "", f)
    if f in CITY_ALIASES:
        return CITY_ALIASES[f]
    c = f.replace(" ", "").replace(".", "")
    return c if c in CITIES else None


def _theatres():
    if "theatres" not in _CACHE:
        try:
            with open(THEATRES, encoding="utf-8") as fh:
                _CACHE["theatres"] = json.load(fh).get("a3") or {}
        except (OSError, ValueError):
            _CACHE["theatres"] = {}
    return _CACHE["theatres"]


def cf_pops():
    """{IATA: [lon, lat, city, ISO-3]} from ref/cf_pops.json ({} when missing)."""
    if "pops" not in _CACHE:
        try:
            with open(POPS_FILE, encoding="utf-8") as fh:
                d = json.load(fh)
            _CACHE["pops"] = {k: v for k, v in d.items() if isinstance(v, list) and len(v) == 4}
        except (OSError, ValueError, AttributeError):
            _CACHE["pops"] = {}
    return _CACHE["pops"]


def _cname(a3):
    r = _theatres().get(a3)
    return r[3] if r else a3


def _path(name):
    return os.path.join(CACHE, name)


def _load(name):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(name, obj):
    os.makedirs(CACHE, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    os.replace(tmp, _path(name))


# ---------------- text rules ----------------

_RX_RESOLVED = re.compile(r"\b(?:resolved|restored|mitigated|recovered|operating normally|completed|back to normal|"
                          r"back to nominal|nominal operations?|fully operational|returned to normal)\b", re.I)
# negated or future phrasing is removed before _RX_RESOLVED is tried ("not yet resolved", "an update once the
# work has been completed", "until it is restored")
_RX_NOT_RESOLVED = re.compile(r"\b(?:not|never)\s+(?:yet\s+|been\s+|fully\s+|been\s+fully\s+)*(?:resolved|restored|"
                              r"mitigated|recovered|completed)\b|\b(?:once|when|until|as soon as|after|before|will|"
                              r"expected to|to be|work to)\b[^.;:!?]{0,80}?\b(?:resolved|restored|mitigated|recovered|"
                              r"completed)\b", re.I)
_RX_CRIT = re.compile(r"\b(?:major|complete|full|total|global|widespread) outage\b", re.I)
_RX_MAJOR = re.compile(r"\b(?:partial outage|outages?|disruptions?|unavailable|unreachable|down|offline|failures?|"
                       r"failing|inaccessible)\b", re.I)
_RX_INFO = re.compile(r"\binformational\b", re.I)
_RX_MAINT = re.compile(r"\bmaintenance\b", re.I)
_RX_UNDERWAY = re.compile(r"\b(?:in progress|underway|under way|has started|have started|we are performing|"
                          r"we(?:'|’)re performing|currently performing|ongoing maintenance)\b", re.I)


def says_resolved(text):
    return bool(_RX_RESOLVED.search(_RX_NOT_RESOLVED.sub(" ", text or "")))


def text_severity(text):
    t = text or ""
    if _RX_CRIT.search(t):
        return "critical"
    if _RX_MAJOR.search(t):
        return "major"
    if _RX_INFO.search(t):
        return "info"
    return "minor"


def _status_text(text, resolved):
    if resolved:
        return "resolved"
    t = (text or "").lower()
    if "monitor" in t:
        return "monitoring"
    if re.search(r"identified|root cause|mitigat|fix (?:is|has been)|deploy", t):
        return "identified"
    return "investigating"


SP_STATUS = {"investigating": "investigating", "identified": "identified", "monitoring": "monitoring",
             "resolved": "resolved", "postmortem": "resolved", "completed": "resolved", "in_progress": "in effect",
             "verifying": "monitoring"}
MAINT_STATUSES = ("scheduled", "in_progress", "verifying", "completed")


def _worst(sevs):
    sevs = [s for s in sevs if s in SEV_RANK]
    return max(sevs, key=lambda s: SEV_RANK[s]) if sevs else "minor"


# ---------------- parsers (body -> {"records": [...], ...}) ----------------
# A record: sid, title, summary, url, ts (newest update), start, end, status, resolved, severity, maint, and
# optionally rss (text-feed active rule), win [start, end] (a maintenance window), comps (component names),
# regions (raw region codes), pops (PoP codes), route (feed), tags.

def _sp_record(i, base):
    """One Statuspage / incident.io incident or scheduled maintenance -> record (None to drop)."""
    if not isinstance(i, dict):
        return None
    sid, name = str(i.get("id") or ""), _text(i.get("name"), 240)
    if not sid or not name:
        return None
    ups = []
    for u in i.get("incident_updates") or []:
        if isinstance(u, dict):
            t = _ts(u.get("display_at")) or _ts(u.get("created_at"))
            if t:
                ups.append((t, u))
    newest = max(ups, key=lambda x: x[0])[1] if ups else {}
    status = str(i.get("status") or "").lower()
    impact = str(i.get("impact") or "").lower()
    maint = impact == "maintenance" or status in MAINT_STATUSES or bool(i.get("scheduled_for"))
    if maint and status == "scheduled":
        return None                                    # not in progress: dropped (re-parsed when it starts)
    times = [x for x in (_ts(i.get("updated_at")), ups and max(t for t, _ in ups), _ts(i.get("created_at"))) if x]
    if not times:
        return None
    resolved = status in ("resolved", "postmortem", "completed") or bool(i.get("resolved_at"))
    comps = [_clip(c.get("name"), 80) for c in i.get("components") or [] if isinstance(c, dict) and c.get("name")]
    return {"sid": sid, "title": name, "summary": _text(newest.get("body"), 400) or None,
            "url": base + "/incidents/" + sid, "ts": max(times),
            "start": _ts(i.get("started_at")) or _ts(i.get("scheduled_for")) or _ts(i.get("created_at")),
            "end": (_ts(i.get("resolved_at")) or _ts(i.get("updated_at"))) if resolved else _ts(i.get("scheduled_until")),
            "status": SP_STATUS.get(status), "resolved": resolved,
            "severity": "maintenance" if maint else IMPACT_SEV.get(impact, "minor"), "maint": maint,
            "comps": comps[:16]}


def _prune(recs, nt):
    """Drop records that can never be listed again: resolved or text-feed ones older than the window, unresolved
    ones past ACTIVE_MAX. A maintenance window still ahead is kept (a 304 would not bring it back)."""
    out = []
    for r in recs:
        win = r.get("win")
        if r.get("maint") and win and (win[1] is None or win[1] >= nt) and not r.get("resolved"):
            out.append(r)
            continue
        if (r.get("resolved") or r.get("rss") or r.get("news")) and r["ts"] < nt - WINDOW:
            continue
        if not r.get("resolved") and not r.get("rss") and (r.get("start") or r["ts"]) < nt - ACTIVE_MAX:
            continue
        out.append(r)
    return out


def _merge_live(prev, recs, nt):
    """For sources listing only current incidents: one that vanished since the last answer is resolved now."""
    seen = {r["sid"] for r in recs}
    out = list(recs)
    for r in ((prev or {}).get("records") or []):
        if r.get("sid") in seen:
            continue
        if not r.get("resolved"):
            r = dict(r, resolved=True, status="resolved", end=nt, ts=nt, tags=list(r.get("tags") or []) + ["cleared"])
        out.append(r)
    return out


def parse_statuspage(body, now, src, prev=None):
    d = json.loads(body)
    if not isinstance(d, dict) or not isinstance(d.get("incidents"), list):
        raise ValueError("Statuspage: no incidents list")
    nt = int(now.timestamp())
    recs = [r for r in (_sp_record(i, src["base"]) for i in d["incidents"]) if r]
    return {"records": _prune(recs, nt)}


_RX_POP_COMP = re.compile(r"^(.*?)\s*-\s*\(([A-Z]{3})\)\s*$")
_RX_CODE = re.compile(r"\(([A-Z]{3})\)")
_RX_POP_MAINT = re.compile(r"^\s*([A-Z]{3})\s*\(")


def parse_cloudflare(body, now, src, prev=None):
    """summary.json -> service incidents (websites), PoP-named incidents (cloud) and PoP component counts."""
    d = json.loads(body)
    if not isinstance(d, dict) or not isinstance(d.get("components"), list):
        raise ValueError("Cloudflare: no components list")
    nt = int(now.timestamp())
    pops = {"total": 0, "partial_outage": 0, "under_maintenance": 0, "major_outage": 0, "degraded_performance": 0}
    codes = set()
    for c in d["components"]:
        m = _RX_POP_COMP.match(str((c or {}).get("name") or "")) if isinstance(c, dict) else None
        if not m or c.get("group"):
            continue
        codes.add(m.group(2))
        pops["total"] += 1
        st = str(c.get("status") or "")
        if st in pops:
            pops[st] += 1
    known = codes | set(cf_pops())
    recs = []
    for i in d.get("incidents") or []:
        r = _sp_record(i, src["base"])
        if not r:
            continue
        named = [c for c in _RX_CODE.findall(r["title"]) if c in known]
        if named:
            r.update(route="cloud", pops=list(dict.fromkeys(named)))
        else:
            r["route"] = "websites"
        recs.append(r)
    pop_maint = 0
    for m in d.get("scheduled_maintenances") or []:
        if not isinstance(m, dict) or str(m.get("status") or "") not in ("in_progress", "verifying"):
            continue
        if _RX_POP_MAINT.match(str(m.get("name") or "")):
            pop_maint += 1                             # routine PoP maintenance: counted, not listed
            continue
        r = _sp_record(m, src["base"])
        if r:
            r["route"] = "websites"
            recs.append(r)
    pops["maintenance_in_progress"] = pop_maint
    return {"records": _prune(_merge_live(prev, recs, nt), nt), "pops": pops}


def parse_slack(body, now, src, prev=None):
    d = json.loads(body)
    if not isinstance(d, dict) or not isinstance(d.get("active_incidents"), list):
        raise ValueError("Slack: no active_incidents list")
    nt = int(now.timestamp())
    recs = []
    for a in d["active_incidents"]:
        if not isinstance(a, dict):
            continue
        title = _text(a.get("title"), 240)
        url = str(a.get("url") or "")
        if not title:
            continue
        typ, st = str(a.get("type") or "").lower(), str(a.get("status") or "").lower()
        if st == "scheduled":
            continue
        maint = typ == "maintenance"
        resolved = st in ("resolved", "completed", "ok")
        notes = [n for n in a.get("notes") or [] if isinstance(n, dict)]
        notes.sort(key=lambda n: _ts(n.get("date_created")) or 0)
        t = [x for x in (_ts(a.get("date_updated")), _ts(a.get("date_created"))) if x]
        if not t:
            continue
        recs.append({"sid": str(a.get("id") or _sha(url or title)), "title": title,
                     "summary": _text(notes[-1].get("body"), 400) if notes else None,
                     "url": url if url.startswith("https://") else src["page"], "ts": max(t),
                     "start": _ts(a.get("date_created")), "end": None,
                     "status": "resolved" if resolved else ("in effect" if maint else "investigating"),
                     "resolved": resolved, "maint": maint,
                     "severity": "maintenance" if maint else {"outage": "major", "incident": "minor",
                                                              "notice": "info"}.get(typ, "minor"),
                     "comps": [_clip(s, 60) for s in a.get("services") or [] if isinstance(s, str)][:12]})
    return {"records": _prune(_merge_live(prev, recs, nt), nt)}


_RX_PP_ID = re.compile(r"\((PP-[A-Z]+-\d+)\)")
_RX_PP_PREFIX = re.compile(r"^\s*([A-Za-z][A-Za-z ]{2,30}):\s*")


def parse_paypal(body, now, src, prev=None):
    """PayPal status RSS: one item per event, "<Status>: <what> (PP-LIVE-n)"; the status prefix may repeat."""
    nt = int(now.timestamp())
    recs = []
    for e in _feed_entries(body):
        m = _RX_PP_ID.search(e["title"]) or re.search(r"eventdetails/(\d+)", e["link"])
        if not m or not e["t"]:
            continue
        title, prefixes = e["title"], []
        while True:
            p = _RX_PP_PREFIX.match(title)
            if not p:
                break
            prefixes.append(p.group(1).strip().lower())
            title = title[p.end():]
        word = prefixes[0] if prefixes else ""
        desc = _text(e["desc"], 400)
        maint = bool(_RX_MAINT.search(title) or _RX_MAINT.search(desc[:200]))
        resolved = bool(re.search(r"resolved|completed|cancel|postponed|rescheduled|closed", word)) or (
            not word and says_resolved(desc))
        if maint and not resolved and not re.search(r"in progress|started|underway", word):
            continue                                   # announced, not under way (or done)
        title = re.sub(r"\s*\(PP-[A-Z]+-\d+\)\s*$", "", title).strip() or e["title"]
        recs.append({"sid": m.group(1), "title": _clip(title, 240), "summary": desc or None,
                     "url": e["link"] if e["link"].startswith("https://") else src["page"], "ts": e["t"],
                     "start": e["t"], "end": e["t"] if resolved else None,
                     "status": "resolved" if resolved else ("in effect" if maint else _status_text(word, False)),
                     "resolved": resolved, "maint": maint, "rss": True,
                     "severity": "maintenance" if maint else text_severity(title + " " + desc)})
    return {"records": _prune(_newest_per_sid(recs), nt)}


def _newest_per_sid(recs):
    by = {}
    for r in recs:
        if r["sid"] not in by or r["ts"] > by[r["sid"]]["ts"]:
            by[r["sid"]] = r
    return list(by.values())


def _md_title(s):
    """Google external_desc -> one line: the line after "Summary:" / "Title:", else the first line."""
    lines = [ln.strip() for ln in str(s or "").replace("\\n", "\n").split("\n") if ln.strip()]
    for k, ln in enumerate(lines):
        if re.match(r"^\W*(?:summary|title)\W*$", ln, re.I) and k + 1 < len(lines):
            return _text(lines[k + 1], 240)
        m = re.match(r"^\W*(?:summary|title)\W*:\W*(.+)$", ln, re.I)
        if m and _text(m.group(1)):
            return _text(m.group(1), 240)
    return _text(lines[0], 240) if lines else ""


def parse_google(body, now, src, prev=None):
    """Google Cloud / Workspace incidents.json (one schema). Workspace Gemini incidents go to the cloud feed."""
    d = json.loads(body)
    if not isinstance(d, list):
        raise ValueError("Google status: expected a list, got %s" % type(d).__name__)
    nt = int(now.timestamp())
    base = src["page"].rstrip("/") + "/"
    recs = []
    for x in d:
        if not isinstance(x, dict) or not x.get("id"):
            continue
        svc = _clip(x.get("service_name"), 80)
        desc = _md_title(x.get("external_desc"))
        if not desc:
            continue
        title = desc if not svc or svc.lower() in desc.lower() else "%s: %s" % (svc, desc)
        mru = x.get("most_recent_update") if isinstance(x.get("most_recent_update"), dict) else {}
        t = [v for v in (_ts(mru.get("when")), _ts(mru.get("modified")), _ts(x.get("modified")), _ts(x.get("begin")))
             if v]
        if not t:
            continue
        resolved = bool(x.get("end")) or str(mru.get("status") or "").upper() == "AVAILABLE"
        summary = re.sub(r"^\s*(?:summary|title|description)\s*:?\s*", "", _text(mru.get("text")), flags=re.I)
        summary = _clip(summary, 400) or None
        locs = (x.get("currently_affected_locations") or []) if not resolved else []
        locs = locs or x.get("previously_affected_locations") or x.get("currently_affected_locations") or []
        rec = {"sid": str(x["id"]), "title": _clip(title, 240), "summary": summary,
               "url": base + str(x.get("uri") or "incidents/" + str(x["id"])).lstrip("/"), "ts": max(t),
               "start": _ts(x.get("begin")), "end": _ts(x.get("end")),
               "status": _status_text(summary, resolved), "resolved": resolved, "maint": False,
               "severity": GOOGLE_SEV.get(str(x.get("severity") or "").lower(), "minor"),
               "regions": [str(l.get("id")) for l in locs if isinstance(l, dict) and l.get("id")][:12]}
        if src["key"] == "gworkspace":
            rec["route"] = "cloud" if re.match(r"gemini\b", svc, re.I) else "websites"
        recs.append(rec)
    return {"records": _prune(recs, nt)}


def parse_m365(body, now, src, prev=None):
    """status.cloud.microsoft posts: one row per service; only non-"Operational" rows are incidents."""
    d = json.loads(body)
    if isinstance(d, dict):
        d = d.get("value") or d.get("posts") or d.get("items")
    if not isinstance(d, list):
        raise ValueError("M365: expected a list of posts")
    nt = int(now.timestamp())
    recs = []
    for p in d:
        if not isinstance(p, dict):
            continue
        st = str(p.get("Status") or "").strip()
        if st.lower() in ("", "operational", "normal", "serviceoperational"):
            continue
        svc = _clip(p.get("ServiceDisplayName") or p.get("ServiceWorkloadName"), 80)
        title = _text(p.get("Title"), 240) or "%s: %s" % (svc, st)
        t = [v for v in (_ts(p.get("InternalDateTime")), _ts(p.get("AuthoredDateTime"))) if v] or \
            [v for v in (_ts(p.get("LastUpdatedTime")),) if v]
        if not t:
            continue
        resolved = bool(re.search(r"restored|resolved|false positive|post-incident|closed", st, re.I))
        recs.append({"sid": str(p.get("Id") or _sha("%s|%s|%s" % (svc, title, min(t)))), "title": title,
                     "summary": _text(p.get("Message"), 400) or None, "url": src["page"], "ts": max(t),
                     "start": min(t), "end": None, "status": _status_text(st, resolved), "resolved": resolved,
                     "maint": False, "comps": [svc] if svc else [],
                     "severity": "major" if re.search(r"interrupt|outage|down", st + " " + title, re.I) else "minor"})
    return {"records": _prune(_merge_live(prev, recs, nt), nt)}


# ---- RSS / Atom ----

_A = "{http://www.w3.org/2005/Atom}"
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
_DC_DATE = "{http://purl.org/dc/elements/1.1/}date"


def _xml(body):
    b = body if isinstance(body, bytes) else str(body).encode("utf-8")
    return ET.fromstring(b.lstrip(b"\xef\xbb\xbf").lstrip())


def _feed_entries(body):
    """RSS 2.0 or Atom -> [{"title", "link", "guid", "t", "pub", "desc" (raw), "cats"}]; entries without a date get
    t None; pub is False when an RSS item has no pubDate (t then comes from dc:date, if any)."""
    root = _xml(body)
    out = []
    ch = root.find("channel")
    if root.tag == "rss" or ch is not None:
        for it in (ch if ch is not None else root).findall("item"):
            desc = it.findtext("description") or it.findtext(_CONTENT) or ""
            out.append({"title": _text(it.findtext("title")), "link": (it.findtext("link") or "").strip(),
                        "guid": (it.findtext("guid") or "").strip(),
                        "t": _rfc822(it.findtext("pubDate") or "") or _when(it.findtext(_DC_DATE) or ""),
                        "pub": bool((it.findtext("pubDate") or "").strip()),
                        "desc": desc, "cats": [_text(c.text) for c in it.findall("category") if c.text]})
    elif root.tag == _A + "feed":
        for e in root.findall(_A + "entry"):
            link = ""
            for ln in e.findall(_A + "link"):
                if ln.get("rel") in (None, "alternate") and ln.get("href"):
                    link = ln.get("href").strip()
                    break
            c = e.find(_A + "content")
            if c is None:
                c = e.find(_A + "summary")
            if c is not None and c.get("type") == "xhtml":
                desc = " ".join(t.strip() for t in c.itertext() if t.strip())
            else:
                desc = (c.text or "") if c is not None else ""
            out.append({"title": _text(e.findtext(_A + "title")), "link": link,
                        "guid": (e.findtext(_A + "id") or "").strip(),
                        "t": _when(e.findtext(_A + "updated") or "") or _when(e.findtext(_A + "published") or ""),
                        "pub": True,
                        "desc": desc, "cats": [_text(x.get("term")) for x in e.findall(_A + "category") if x.get("term")]})
    else:
        raise ValueError("not an RSS or Atom document (%s)" % root.tag[:40])
    return out


def _clusters(entries, keyfn, gap=CLUSTER_GAP):
    """Group entries per key; with a gap, entries further apart than it start a new incident."""
    by = {}
    for e in entries:
        k = keyfn(e)
        if k and e["t"]:
            by.setdefault(k, []).append(e)
    out = []
    for k, es in sorted(by.items()):
        es.sort(key=lambda e: e["t"])
        cur = [es[0]]
        for e in es[1:]:
            if gap and e["t"] - cur[-1]["t"] > gap:
                out.append((k, cur))
                cur = [e]
            else:
                cur.append(e)
        out.append((k, cur))
    return out


_RX_AWS = re.compile(r"\b((?:us-gov|eusc-de|us|eu|ap|sa|ca|me|af|il|mx|cn)-(?:north|south|east|west|central|"
                     r"northeast|southeast|northwest|southwest)-\d)\b", re.I)
AWS_SVC = {"multipleservices": "Multiple services", "ec2": "EC2", "s3": "S3", "rds": "RDS", "lambda": "Lambda",
           "cloudfront": "CloudFront", "route53": "Route 53", "iam": "IAM", "dynamodb": "DynamoDB", "elb": "ELB",
           "ecs": "ECS", "eks": "EKS", "sqs": "SQS", "sns": "SNS", "connect": "Connect", "bedrock": "Bedrock"}


def _aws_key(e):
    g = e["guid"] or e["link"]
    frag = g.split("#", 1)[1] if "#" in g else ""
    return re.sub(r"_\d+$", "", frag) or None


def parse_aws(body, now, src, prev=None):
    """AWS Health Dashboard RSS: one item per update, guid "#<service>-<region>_<epoch>"."""
    nt = int(now.timestamp())
    recs = []
    for key, es in _clusters(_feed_entries(body), _aws_key):
        last = es[-1]
        m = _RX_AWS.search(key)
        region = m.group(1).lower() if m else None
        svc = key[:m.start()].rstrip("-") if m else key
        svc_name = AWS_SVC.get(svc.lower()) or (svc.upper() if len(svc) <= 4 else svc.capitalize())
        sevs = []
        for e in es:
            t = e["title"]
            sevs.append("info" if re.match(r"informational", t, re.I) else
                        "major" if re.match(r"service (?:disruption|impact)", t, re.I) else
                        "minor" if re.match(r"(?:service degradation|performance issues)", t, re.I) else
                        text_severity(t))
        resolved = says_resolved(last["title"] + " " + _text(last["desc"]))
        head = re.sub(r"^(?:Informational message|Service disruption|Service impact|Performance issues|"
                      r"Service is operating normally)\s*:\s*", "", last["title"], flags=re.I)
        title = "%s%s: %s" % (svc_name, " " + region if region else "", head or last["title"])
        url = last["guid"] if last["guid"].startswith("https://") else (last["link"] or src["page"])
        recs.append({"sid": "%s_%d" % (key, es[0]["t"]), "title": _clip(title, 240),
                     "summary": _text(last["desc"], 400) or None, "url": url, "ts": last["t"], "start": es[0]["t"],
                     "end": last["t"] if resolved else None, "status": _status_text(_text(last["desc"]), resolved),
                     "resolved": resolved, "maint": False, "rss": True, "severity": _worst(sevs),
                     "regions": [region] if region else []})
    return {"records": _prune(recs, nt)}


def _strip_status_word(title):
    return re.sub(r"^\s*(?:resolved|mitigated|active|investigating|update|monitoring|identified)\s*[-:–]\s*", "",
                  title, flags=re.I).strip()


def parse_azure(body, now, src, prev=None):
    """Azure status RSS (active incidents only; the item format was unseen on 2026-11-21, so: any title / guid /
    link / pubDate / description, updates grouped by guid, else link, else title without a status word)."""
    nt = int(now.timestamp())
    entries = _feed_entries(body)
    recs = []
    for key, es in _clusters(entries, lambda e: e["guid"] or e["link"] or _strip_status_word(e["title"]).lower()):
        last = es[-1]
        text = "%s %s" % (last["title"], _text(last["desc"]))
        resolved = says_resolved(text)
        url = last["link"] if last["link"].startswith("https://") else src["page"]
        recs.append({"sid": "%s_%d" % (_sha(key), es[0]["t"]),
                     "title": _clip(_strip_status_word(last["title"]) or last["title"], 240),
                     "summary": _text(last["desc"], 400) or None, "url": url, "ts": last["t"], "start": es[0]["t"],
                     "end": last["t"] if resolved else None, "status": _status_text(text, resolved),
                     "resolved": resolved, "maint": bool(_RX_MAINT.search(last["title"])), "rss": True,
                     "severity": _worst([text_severity("%s %s" % (e["title"], _text(e["desc"]))) for e in es])})
    recs = [r for r in recs if not r["maint"] or _RX_UNDERWAY.search("%s %s" % (r["title"], r["summary"] or ""))]
    return {"records": _prune(_merge_live(prev, recs, nt), nt)}   # the feed lists only current incidents


_RX_STRONG = re.compile(r"<strong>\s*([^<]+?)\s*</strong>", re.I)


def parse_oci(body, now, src, prev=None):
    """OCI incident-summary RSS: one item per incident, "Service | Region | ref"; newest update first in the
    description ("<strong>Resolved</strong> - text")."""
    nt = int(now.timestamp())
    recs = []
    for e in _feed_entries(body):
        if not e["t"] or not e["title"]:
            continue
        parts = [p.strip() for p in e["title"].split("|")]
        m = _RX_STRONG.search(e["desc"])
        word = (m.group(1) if m else "").lower()
        text = _text(e["desc"])
        first = _text(e["desc"][m.end():] if m else e["desc"])
        first = re.split(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d{1,2}\s+\d{1,2}:\d{2} UTC", first)[0]
        first = re.sub(r"^[\s\-–:]+", "", first)
        resolved = word in ("resolved", "completed", "postmortem") or (not word and says_resolved(text))
        maint = word in ("scheduled", "in progress") or bool(_RX_MAINT.search(e["title"]))
        if maint and word not in ("in progress",):
            continue
        title = " | ".join(parts[:2]) if len(parts) >= 2 else e["title"]
        recs.append({"sid": e["guid"] or _sha(e["link"] or e["title"]), "title": _clip(title, 240),
                     "summary": _clip(first, 400) or None,
                     "url": e["link"] if e["link"].startswith("https://") else src["page"], "ts": e["t"],
                     "start": e["t"], "end": e["t"] if resolved else None,
                     "status": SP_STATUS.get(word.replace(" ", "_")) or _status_text(word, resolved),
                     "resolved": resolved, "maint": maint, "rss": True,
                     "severity": "maintenance" if maint else text_severity(e["title"] + " " + first),
                     "regions": [parts[1]] if len(parts) >= 3 else []})
    return {"records": _prune(_newest_per_sid(recs), nt)}


_RX_HZ_UPD = re.compile(r"\b(Resolved|Monitoring|Identified|Investigating|Update|Completed|Finished|Closed)\s+"
                        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2}))")
_RX_HZ_START = re.compile(r"\bStart:\s*(\S+)")
_RX_HZ_END = re.compile(r"\b(?:Ends on|Estimated end|End):\s*(\S+)", re.I)
_RX_INCIDENTISH = re.compile(r"outage|disruption|unavailable|failure|degraded|down\b|interrupt|offline", re.I)


def parse_hetzner(body, now, src, prev=None):
    """Hetzner status Atom: one entry per incident (content: Start / end, then "<Status> <time> text" updates,
    newest first). "General" notices (phishing, CVEs) are skipped unless they read like an outage."""
    nt = int(now.timestamp())
    recs = []
    for e in _feed_entries(body):
        if not e["t"] or not e["title"]:
            continue
        cats = [c.lower() for c in e["cats"]]
        if "general" in cats and not _RX_INCIDENTISH.search(e["title"]):
            continue
        text = _text(e["desc"])
        ups = [(m.group(1).lower(), _ts(m.group(2)), m.end(), m.start()) for m in _RX_HZ_UPD.finditer(text)]
        ups = [u for u in ups if u[1]]
        start = _ts((_RX_HZ_START.search(text) or [None, None])[1])
        end_m = _RX_HZ_END.search(text)
        end = _ts(end_m.group(1)) if end_m else None
        maint = bool(_RX_MAINT.search(e["title"]) or end_m or re.search(r"\bplann?ed\b", text, re.I))
        if ups:
            word, ut, a, _ = max(ups, key=lambda u: u[1])
            nxt = min([u[3] for u in ups if u[3] > a] or [len(text)])
            summary = text[a:nxt]
        else:
            word, ut = "", None
            summary = _RX_HZ_END.sub(" ", _RX_HZ_START.sub(" ", text))
        summary = _clip(re.sub(r"^\s*\d{4}-\d{2}-\d{2}T\S+\s*", "", summary.strip()), 400)
        resolved = word in ("resolved", "completed", "finished", "closed") or (not word and says_resolved(summary))
        m = re.search(r"/incident/([0-9a-f-]{8,})", e["link"]) or re.search(r"([0-9a-f]{8}-[0-9a-f-]{20,})", e["guid"])
        rec = {"sid": m.group(1) if m else _sha(e["guid"] or e["title"]), "title": _clip(e["title"], 240),
               "summary": summary or None, "url": e["link"] if e["link"].startswith("https://") else src["page"],
               "ts": max(x for x in (e["t"], ut) if x), "start": start or e["t"],
               "end": end if not resolved else (ut or e["t"]),
               "status": "resolved" if resolved else ("in effect" if maint else SP_STATUS.get(word)),
               "resolved": resolved, "maint": maint, "rss": True,
               "severity": "maintenance" if maint else text_severity(e["title"] + " " + summary),
               "comps": e["cats"][:4]}
        if maint:
            rec["win"] = [start, end]
        recs.append(rec)
    return {"records": _prune(recs, nt)}


def parse_hf(body, now, src, prev=None):
    """Hugging Face (Better Stack) RSS: one item per update, grouped by the incident / maintenance link."""
    nt = int(now.timestamp())
    recs = []
    for key, es in _clusters(_feed_entries(body), lambda e: e["link"] or e["guid"].split("#")[0], gap=None):
        last = es[-1]
        cats = [c.lower() for e in es for c in e["cats"]]
        title = re.sub(r"^\s*Maintenance:\s*", "", last["title"])
        maint = "maintenance" in cats or "/maintenance/" in key or bool(_RX_MAINT.search(last["title"]))
        text = _text(last["desc"])
        resolved = says_resolved(text)
        if maint and (resolved or not _RX_UNDERWAY.search(text)):
            continue                                   # announced or completed, not under way
        m = re.search(r"/(?:incident|maintenance)/(\d+)", key)
        recs.append({"sid": m.group(1) if m else _sha(key), "title": _clip(title, 240), "summary": _clip(text, 400) or None,
                     "url": key if key.startswith("https://") else src["page"], "ts": last["t"], "start": es[0]["t"],
                     "end": last["t"] if resolved else None,
                     "status": "in effect" if maint else _status_text(text, resolved), "resolved": resolved,
                     "maint": maint, "rss": True,
                     "severity": "maintenance" if maint else _worst([text_severity(e["title"]) for e in es])})
    return {"records": _prune(recs, nt)}


# Datacenter news: incident headlines only
_RX_NEWS_KEEP = re.compile(
    r"\boutages?\b|\b(?:goes|went|go|knocked|taken|brought|is|was|remains?|been)\s+(?:down|offline)\b|\bdown for\b|"
    r"\boffline\b|\bfires?\b|\bblaze\b|\bburn(?:s|ed|t|ing)? down\b|\bpower (?:failure|loss|outage|cut)s?\b|"
    r"\blost power\b|\bloses power\b|\bblackout\b|\bcooling (?:failure|fault|issue|problem|outage|loss)s?\b|"
    r"\bfloods?\b|\bflooded\b|\bflooding\b|\bexplosions?\b|\bexplodes?\b|\bexploded\b|\battacks?\b|\battacked\b|"
    r"\bsabotage[ds]?\b|\bevacuat\w*", re.I)
_RX_NEWS_DROP = re.compile(
    r"\b(?:acquir\w*|acquisition|buys?|bought|sells?|sold|deal|merger|invest\w*|funding|raises|ipo|lease[sd]?|"
    r"campus|plans?|planned|files for|tops? out|breaks ground|groundbreaking|construction|builds?|"
    r"expands?|expansion|launch\w*|earnings|revenue|quarterly|profit|opinion|sponsored|podcast|webinar|"
    r"interview|analysis|how|why|lessons|report finds|survey|forecast)\b",
    re.I)


def is_incident_headline(title):
    return bool(_RX_NEWS_KEEP.search(title or "")) and not _RX_NEWS_DROP.search(title or "")


def parse_news(body, now, src, prev=None):
    nt = int(now.timestamp())
    recs = []
    for e in _feed_entries(body):
        title = _clip(e["title"], 240)
        if not title or not e["t"] or not e.get("pub") or e["t"] > nt + FUTURE_SKEW or \
                not e["link"].startswith("http"):
            continue          # undated (event listings carry only dc:date) and future-dated items are never kept
        if not is_incident_headline(title):
            continue
        recs.append({"sid": _sha(e["link"]), "title": title, "summary": _text(e["desc"], 400) or None,
                     "url": e["link"], "ts": e["t"], "start": e["t"], "end": None, "status": None, "resolved": True,
                     "maint": False, "news": True, "severity": "info"})
    return {"records": _prune(recs, nt)}


PARSERS = {"statuspage": parse_statuspage, "cloudflare": parse_cloudflare, "slack": parse_slack,
           "paypal": parse_paypal, "google": parse_google, "m365": parse_m365, "aws": parse_aws,
           "azure": parse_azure, "oci": parse_oci, "hetzner": parse_hetzner, "hf": parse_hf, "news": parse_news}


# ---------------- regions and places ----------------

_AZ_NAMES = sorted(AZURE_REGIONS, key=len, reverse=True)
_RX_AZURE = re.compile(r"\b(%s)\b" % "|".join(re.escape(n) for n in _AZ_NAMES), re.I)
_AZ_IDS = {n.lower().replace(" ", ""): n for n in AZURE_REGIONS}
_RX_AZURE_ID = re.compile(r"\b(%s)\b" % "|".join(sorted(_AZ_IDS, key=len, reverse=True)))
_RX_DO = re.compile(r"\b(%s)(\d)\b" % "|".join(DO_REGIONS), re.I)
_RX_LINODE = re.compile(r"\b(US|ID|SG|FR|IN|BR|GB|AU|DE|JP|NL|ES|IT|SE|CA)-([A-Z]{3})(?:-(\d))?\b", re.I)
_RX_LINODE_OLD = re.compile(r"\b(%s)\b" % "|".join(sorted((k.replace("-", "[- ]") for k in LINODE_LEGACY),
                                                         key=len, reverse=True)), re.I)
_RX_OVH_SITE = re.compile(r"^(%s)\d*(?:-[A-Z])?$" % "|".join(OVH_SITES))
_RX_OVH_REGION = re.compile(r"^(?:EU|AP|US|CA)-[A-Z]+(?:-LZ)?-([A-Z]{2,3})\d*(?:-[A-Z0-9]+)?$")
_RX_HZ_CODE = re.compile(r"\b(FSN|NBG|HEL|ASH|HIL|SIN)\d?\b|\b(fsn|nbg|hel|ash|hil|sin)1\b")
_RX_HZ_NAME = re.compile(r"\b(%s)\b" % "|".join(HETZNER_NAMES), re.I)
_RX_LAMBDA = re.compile(r"\b((?:us|europe|asia|me|australia)-(?:east|west|south|north|central|midwest|southeast|"
                        r"southwest|northeast|northwest)-\d)\b", re.I)
_RX_OCI_ID = re.compile(r"\b[a-z]{2}-([a-z]+)-\d\b")
_RX_PAREN = re.compile(r"\(([^)]+)\)")


def regions(family, rec):
    """[(region code, CITIES key or None)] named by a cloud record (deduplicated by code)."""
    title, comps, raw = rec.get("title") or "", rec.get("comps") or [], rec.get("regions") or []
    out = []
    if family == "aws":
        codes = [c.lower() for c in raw] or [m.lower() for m in _RX_AWS.findall(title)]
        out = [(c, AWS_REGIONS.get(c)) for c in codes]
    elif family == "gcp":
        out = [(c, GCP_REGIONS.get(c)) for c in raw if c != "global"]
    elif family == "azure":
        text = "%s %s" % (title, rec.get("summary") or "")
        names = [_canon_azure(m) for m in _RX_AZURE.findall(text)] + [_AZ_IDS[m] for m in _RX_AZURE_ID.findall(text)]
        out = [(n, AZURE_REGIONS.get(n)) for n in names if n]
    elif family == "oci":
        for seg in raw:
            m = _RX_PAREN.search(seg)
            city = _city_by_name(m.group(1)) if m else None
            if not city:
                mi = _RX_OCI_ID.search(seg)
                city = _city_by_name(mi.group(1)) if mi else None
            out.append((seg, city))
    elif family == "do":
        for s in [title] + comps:
            out += [(a.upper() + n, DO_REGIONS[a.upper()]) for a, n in _RX_DO.findall(s)]
    elif family == "linode":
        for s in [title] + comps:
            for cc, code, n in _RX_LINODE.findall(s):
                out.append(("%s-%s%s" % (cc.upper(), code.upper(), "-" + n if n else ""), IATA_CITY.get(code.upper())))
            for leg in _RX_LINODE_OLD.findall(s):
                k = re.sub(r"[- ]", "-", leg.upper())
                out.append((k, LINODE_LEGACY.get(k)))
    elif family == "ovh":
        toks = list(comps)
        m = re.match(r"^\s*\[([^\]]+)\]", title)
        if m:
            toks += [t.strip() for t in m.group(1).split("/")]
        for t in toks:
            t = t.strip().upper()
            ms, mr = _RX_OVH_SITE.match(t), _RX_OVH_REGION.match(t)
            if ms:
                out.append((t, OVH_SITES[ms.group(1)]))
            elif mr:
                out.append((t, OVH_TOKENS.get(mr.group(1)) or IATA_CITY.get(mr.group(1))))
            elif t == "MUM":
                out.append((t, "mumbai"))
    elif family == "hetzner":
        for a, b in _RX_HZ_CODE.findall(title):
            c = (a or b).upper()
            out.append((c.lower() + ("1" if c in ("FSN", "NBG", "HEL") else ""), HETZNER_SITES[c]))
        for n in _RX_HZ_NAME.findall(title):
            c = HETZNER_NAMES[n.lower()]
            out.append((c.lower() + ("1" if c in ("FSN", "NBG", "HEL") else ""), HETZNER_SITES[c]))
    elif family == "lambda":
        for c in _RX_LAMBDA.findall(title):
            c = c.lower()
            out.append((c, next((k for p, k in LAMBDA_PREFIX if c.startswith(p)), None)))
    seen, res = set(), []
    for code, city in out:
        if code and code not in seen:
            seen.add(code)
            res.append((code, city))
    return res


def _canon_azure(name):
    n = name.lower()
    return next((k for k in AZURE_REGIONS if k.lower() == n), None)


def _city_place(key, code=None):
    lon, lat, label, a3 = CITIES[key]
    return {"ll": [lon, lat], "label": label, "a3": a3, "place": "region", "code": code, "city": key}


def _country_place(a3):
    r = _theatres().get(a3)
    if not r:
        return None
    return {"ll": [r[1], r[2]], "label": r[3], "a3": a3, "place": "country", "code": None, "city": None}


def _hq_place(key):
    lon, lat, label, _ = CITIES[key]
    return {"ll": [lon, lat], "label": "Global (HQ: %s)" % label.split(",")[0], "a3": None, "place": "hq",
            "code": None, "city": key}


def _def(key):
    """A source's definition: a SOURCES row, or a RADAR row (1.1; not fetched here)."""
    return SOURCES.get(key) or RADAR[key]


def places(feed, key, rec):
    """Where an item is pinned: [{"ll", "label", "a3", "place", "code", "city"}], first = primary; [] = not on the map.
    A Radar record carries its own ("pins")."""
    if rec.get("pins") is not None:
        return list(rec["pins"])
    src = SOURCES[key]
    out = []
    for c in rec.get("pops") or []:
        p = cf_pops().get(c)
        if p:
            out.append({"ll": [p[0], p[1]], "label": "%s, %s (%s)" % (p[2], _cname(p[3]), c), "a3": p[3],
                        "place": "pop", "code": c, "city": None})
    if out:
        return out
    if src["family"]:
        seen = set()
        for code, city in regions(src["family"], rec):
            if city and city in CITIES and city not in seen:
                seen.add(city)
                out.append(_city_place(city, code))
        if out:
            return out
    if src["fmt"] == "news":
        cs = placer.place(rec.get("title") or "", rec.get("summary") or None).get("countries") or []
        p = _country_place(cs[0]) if cs else None
        return [p] if p else []
    if feed == "websites" and not src["family"]:
        title = rec.get("title") or ""
        for a3 in (placer.place(title).get("countries") or [])[:3]:
            p = _country_place(a3)
            if p:
                out.append(p)
        for rx, (lon, lat, label) in MACRO:
            if rx.search(title):
                out.append({"ll": [lon, lat], "label": label, "a3": None, "place": "region", "code": None,
                            "city": None})
        if out:
            return out
    if src["hq"]:
        return [_hq_place(src["hq"])]
    return []


# ---------------- items ----------------

def _route(key, rec):
    return rec.get("route") or SPLIT.get(key) or ("websites" if key in FEED_SOURCES["websites"] else "cloud")


def is_active(rec, nt):
    """The active rule (module docstring): machine status, else the text-feed 24 h rule; maintenance by window."""
    if rec.get("news") or rec.get("resolved"):
        return False
    win = rec.get("win")
    if rec.get("maint") and win and (win[0] or win[1]):
        return (win[0] or 0) <= nt and (win[1] is None or nt <= win[1])
    if rec.get("rss"):
        return nt - rec["ts"] <= RSS_ACTIVE
    return True


def _provider(feed, key):
    return FEED_PROVIDER.get((feed, key)) or _def(key)["provider"]


def make_item(feed, key, rec, nt):
    """record -> (item, places) or (None, None) when it is outside the window, in the future or not in progress."""
    ts = rec.get("ts")
    if not ts or ts > nt + FUTURE_SKEW:
        return None, None
    ts = min(int(ts), nt)
    active = is_active(dict(rec, ts=ts), nt)
    if rec.get("maint") and not active:
        return None, None
    if not active and ts < nt - WINDOW:
        return None, None
    start = rec.get("start")
    if active and (start or ts) < nt - ACTIVE_MAX:
        return None, None
    pl = places(feed, key, rec)
    src = _def(key)
    sev = "maintenance" if rec.get("maint") else (rec.get("severity") or "minor")
    status = rec.get("status")
    if rec.get("news"):
        status = None
    elif rec.get("resolved"):
        status = "resolved"
    elif rec.get("maint"):
        status = "in effect"
    elif not active and not rec.get("rss"):
        status = "resolved"
    elif not status:
        status = "investigating" if active else None   # a quiet text-feed incident keeps its last word, or none
    tags = list(dict.fromkeys(src["tags"] + FEED_TAGS.get((feed, key), []) + list(rec.get("tags") or []) +
                              (["maintenance"] if rec.get("maint") else [])))
    hq = bool(pl) and pl[0]["place"] == "hq"
    labels = list(dict.fromkeys(p["label"] for p in pl))
    where = "; ".join(labels[:4]) + (" +%d" % (len(labels) - 4) if len(labels) > 4 else "") if pl else None
    codes = list(dict.fromkeys(list(rec.get("pops") or []) + [c for c, _ in (regions(src["family"], rec)
                                                                               if src["family"] else [])] +
                               list(rec.get("codes") or [])))
    item = {
        "id": "%s:%s:%s" % (feed, key, rec["sid"]), "source": key, "provider": rec.get("provider") or _provider(feed, key),
        "kind": rec.get("kind") or ("news" if rec.get("news") else "status"), "title": _clip(rec.get("title"), 240),
        "summary": _clip(rec.get("summary"), 400) if rec.get("summary") else None, "lang": "en",
        "url": rec.get("url") or src["page"], "ts": _iso(ts), "ts_ms": ts * 1000,
        "start_ms": min(int(start), nt) * 1000 if start else None,
        "end_ms": int(rec["end"]) * 1000 if rec.get("end") else None, "active": active, "severity": sev,
        "status": status, "regions": codes[:12], "where": where or ("Global" if not rec.get("news") else None),
        "cc": [] if hq else list(dict.fromkeys(p["a3"] for p in pl if p["a3"])),
        "ll": pl[0]["ll"] if pl else None, "place": pl[0]["place"] if pl else None, "tags": tags, "metric": None,
    }
    return item, pl


def _cap(items, max_items=MAX_ITEMS, budget=MAX_BYTES - 60000):
    """Newest-first items -> (kept, dropped): news first, then resolved items, oldest first; active items last."""
    sizes = {id(i): 2 * len(json.dumps(i, separators=(",", ":"), ensure_ascii=False).encode()) for i in items}
    total = sum(sizes.values())                       # x2: the GeoJSON repeats most of each item
    order = sorted(items, key=lambda i: (2 if i["active"] else 0 if i["kind"] == "news" else 1, i["ts_ms"]))
    drop, n = set(), len(items)
    for i in order:
        if n <= max_items and total <= budget:
            break
        drop.add(id(i))
        n -= 1
        total -= sizes[id(i)]
    return [i for i in items if id(i) not in drop], len(drop)


def geojson(items, pls, feed):
    feats = []
    for it in items:
        props = {k: v for k, v in it.items() if k not in ("summary", "metric")}
        props.update(layer=feed, pid=it["id"])
        for p in pls.get(it["id"]) or []:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(p["ll"][0], 3),
                                                                                         round(p["ll"][1], 3)]},
                          "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def board(feed, srcs, items):
    rows = []
    for key in FEED_SOURCES[feed]:
        if SOURCES[key]["fmt"] == "news":
            continue
        act = [i for i in items if i["source"] == key and i["active"]]
        if not (srcs.get(key) or {}).get("good"):
            st = "unknown"
        elif act:
            st = BOARD_OF[_worst([i["severity"] for i in act])]
        else:
            st = "operational"
        rows.append({"source": key, "provider": _provider(feed, key), "status": st, "active": len(act),
                     "url": SOURCES[key]["page"]})
    rows.sort(key=lambda r: (BOARD_RANK[r["status"]], -r["active"], r["provider"].lower()))
    return rows


def _summary(feed, items, srcs, pops=None, matched=0):
    act = sorted((i for i in items if i["active"]), key=lambda i: (-SEV_RANK[i["severity"]], -i["ts_ms"], i["id"]))
    keys = [k for k in FEED_SOURCES[feed] if SOURCES[k]["fmt"] != "news"]
    up = sum(1 for k in keys if (srcs.get(k) or {}).get("good"))
    parts = []
    if act:
        parts.append("%d active: %s%s." % (len(act), "; ".join("%s (%s): %s" % (i["provider"], i["severity"],
                                                                                 _clip(i["title"], 80))
                                                                for i in act[:5]),
                                            "; +%d more" % (len(act) - 5) if len(act) > 5 else ""))
    else:
        parts.append("No active incident on the %d status pages answering (%d watched)." % (up, len(keys)))
    res = sum(1 for i in items if not i["active"] and i["kind"] == "status")
    if res:
        parts.append("%d resolved in the last 72 h." % res)
    news = sum(1 for i in items if i["kind"] == "news")
    if news:
        parts.append("%d datacenter incident headline%s in 72 h." % (news, "" if news == 1 else "s"))
    rad = [i for i in items if i["source"] in RADAR]
    if rad or matched:
        plat = sum(1 for i in rad if i["source"] == "radar_platform")
        reg, live = len(rad) - plat, sum(1 for i in rad if i["active"])
        what = ["%d platform outage%s" % (plat, "" if plat == 1 else "s")] + \
            (["%d cloud-region anomal%s" % (reg, "y" if reg == 1 else "ies")] if "radar_origins" in FEED_RADAR[feed]
             else [])
        parts.append("Cloudflare Radar: %s in 72 h%s%s." % (
            " and ".join(what), (", %d in effect" % live) if live else "",
            ("; %d more matched an official item" % matched) if matched else ""))
    if pops and pops.get("total"):
        parts.append("Cloudflare PoPs: %d of %d partial outage (usually rerouted traffic), %d in maintenance." % (
            pops["partial_outage"], pops["total"], pops["under_maintenance"]))
    return _clip(" ".join(parts), SUMMARY_MAX)


def _attribution(feed):
    names = list(dict.fromkeys(_provider(feed, k) for k in FEED_SOURCES[feed] if SOURCES[k]["fmt"] != "news"))
    s = "Official status pages and feeds of " + ", ".join(names)
    news = [SOURCES[k]["provider"] for k in FEED_SOURCES[feed] if SOURCES[k]["fmt"] == "news"]
    if news:
        s += "; datacenter headlines: " + ", ".join(news)
    if feed == "cloud":
        s += "; PoP coordinates: OurAirports (public domain)"
    if FEED_RADAR.get(feed):
        s += "; Cloudflare Radar (platform outage annotations%s: CC BY-NC 4.0)" % (
            ", cloud-region traffic anomalies" if "radar_origins" in FEED_RADAR[feed] else "")
    return s + ". Linked per item; private, non-commercial use."


# ---------------- Cloudflare Radar records (1.1) ----------------

def origin_region(slug):
    """Radar origin "amazon-me-central-1" -> (prefix, region code, CITIES key or None); None for another provider.
    A "-global" origin gives code None. Azure codes are display names ("UAE North") when known."""
    pre, _, rest = str(slug or "").strip().lower().partition("-")
    if pre not in ORIGIN_PROVIDER or not rest:
        return None
    if rest == "global":
        return pre, None, None
    fam = ORIGIN_PROVIDER[pre][1]
    if fam == "aws":
        return pre, rest, AWS_REGIONS.get(rest)
    if fam == "gcp":
        return pre, rest, GCP_REGIONS.get(rest)
    if fam == "azure":
        name = _AZ_IDS.get(rest) or AZURE_SHORT.get(rest)
        return pre, name or rest, AZURE_REGIONS.get(name) if name else None
    m = _RX_OCI_ID.search(rest)
    return pre, rest, _city_by_name(m.group(1)) if m else None


def _who(desc, regs, asns):
    """A platform annotation's provider: {"provider", "key", "route", "hq"}: the description first, then the cloud
    origins' prefix, then the networks' names; None when nothing names one."""
    for text in (desc, " ".join(str(x.get("name") or "") for x in asns or [])):
        for rx, key, prov, layer, hq in PLATFORMS:
            if text and rx.search(text):
                return {"provider": prov, "key": key, "route": layer, "hq": hq}
    pres = [r[0] for r in regs]
    if pres:
        prov, _fam, hq, key = ORIGIN_PROVIDER[max(set(pres), key=pres.count)]
        return {"provider": prov, "key": key, "route": "cloud", "hq": hq}
    return None


_RX_WIDE = re.compile(r"\b(?:global|globally|worldwide|world-wide|complete|total)\b", re.I)


def _span_ok(r):
    """A stored Radar row's start / end are epoch seconds (end None while open); anything else is skipped."""
    st, end = r.get("start"), r.get("end")
    return type(st) is int and st > 0 and (end is None or type(end) is int)


def _radar_span(r, nt):
    end = r.get("end")
    done = end is not None and end <= nt
    return end if done else r["start"], end, done


def platform_record(a, nt):
    """A PLATFORM annotation (disruption.parse_radar_outages row) -> a record for make_item, or None."""
    if a.get("type") != "PLATFORM" or not _span_ok(a):
        return None
    desc = a.get("desc") if isinstance(a.get("desc"), str) else ""
    origins = [o for o in a.get("origins") or [] if isinstance(o, dict) and isinstance(o.get("slug"), str)]
    regs = [r for r in (origin_region(o["slug"]) for o in origins) if r]
    who = _who(desc, regs, [x for x in a.get("asns") or [] if isinstance(x, dict)]) or {"provider": "Online platform", "key": None, "route": "cloud", "hq": None}
    first = {}
    for _p, code, c in regs:
        if c and c not in first:
            first[c] = code                                    # one pin per city, its first region code
    cities = list(first.items())
    wide = any(code is None for _p, code, _c in regs) or len(regs) > RADAR_GLOBAL
    if cities and not wide:
        pins, codes = [_city_place(c, code) for c, code in cities], [code for _c, code in cities]
    else:
        pins, codes = ([_hq_place(who["hq"])] if who["hq"] else []), []
    title, rest = disruption.title_summary(desc) if desc else (None, None)
    if not title:
        title = "%s: platform outage" % who["provider"]
    elif codes and len(title) < 60 and not any(c.lower() in title.lower() for c in codes):
        title = "%s (%s %s)" % (title, who["provider"], ", ".join(codes[:3]))   # "Disruption due to drone activity (AWS me-south-1)"
    facts = "Cloudflare Radar outage record. Cause: %s." % (
        disruption._cause(a.get("cause")).lower() if a.get("cause") not in (None, "UNKNOWN") else "not stated")
    if origins and not codes:
        names = sorted({ORIGIN_PROVIDER[r[0]][0] for r in regs}) or ["cloud"]
        facts += " Seen in traffic to %d %s origin%s; shown at the HQ." % (
            len(origins), " / ".join(names), "" if len(origins) == 1 else "s")
    ts, end, done = _radar_span(a, nt)
    return {"sid": str(a["id"]), "title": title, "summary": " ".join(x for x in (rest, facts) if x), "ts": ts,
            "start": a["start"], "end": end, "resolved": done, "status": None if done else "in effect",
            "severity": "critical" if _RX_WIDE.search(desc) else "major",
            "url": a.get("url") or disruption.RADAR_CENTER, "route": who["route"], "provider": who["provider"],
            "match": (who["key"],) if who["key"] else (), "pins": pins, "codes": codes, "kind": "outage",
            "tags": ["platform", (a.get("cause") or "unknown").lower().replace("_", "-")]}


def origin_record(x, nt):
    """A verified ORIGIN traffic anomaly (disruption.parse_radar_anomalies row) -> a record for make_item, or None."""
    og = x.get("origin") if isinstance(x.get("origin"), dict) else None
    if x.get("type") != "ORIGIN" or x.get("status") not in ("VERIFIED", "TP") or x.get("outage") or not og or \
            not isinstance(og.get("slug"), str) or not _span_ok(x):
        return None
    slug, name = og["slug"], og.get("name") or og["slug"]
    r = origin_region(slug)
    pre, _, rest = slug.partition("-")
    prov, _fam, hq, key = ORIGIN_PROVIDER.get(pre) or (re.sub(r"\s+\S+$", "", name) or name, None, None, None)
    city = r[2] if r else None
    pins = [_city_place(city, r[1])] if city else ([_hq_place(hq)] if hq else [])
    title = "Traffic anomaly at %s%s" % (name, (" (%s)" % CITIES[city][2].split(",")[0]) if city else "")
    seen = ", ".join(x.get("seen") or []) or "traffic"
    ts, end, done = _radar_span(x, nt)
    return {"sid": str(x["id"]), "title": title, "ts": ts, "start": x["start"], "end": end, "resolved": done,
            "summary": ("Cloudflare Radar's automatic detection flagged an unusual drop in traffic to the cloud region "
                        "%s, seen in its %s data (status %s at Cloudflare; no cause given)." % (name, seen, x["status"])),
            "status": None if done else "in effect", "severity": "minor",
            "url": RADAR_CLOUD % (pre, rest) if r else RADAR["radar_origins"]["page"], "route": "cloud",
            "provider": prov, "match": (key,) if key else (), "pins": pins, "codes": [r[1]] if r and r[1] else [],
            "kind": "outage", "tags": ["anomaly", "region"]}


def radar_records(radar, nt):
    """disruption.radar_rows() -> [(source key, record)] for both feeds (each record's "route" picks its feed)."""
    out = []
    for name, key, fn in (("radar_outages", "radar_platform", platform_record),
                          ("radar_anomalies", "radar_origins", origin_record)):
        rows = ((radar or {}).get(name) or {}).get("rows")
        for a in (rows.values() if isinstance(rows, dict) else ()):
            try:
                r = fn(a, nt) if isinstance(a, dict) else None
            except (TypeError, ValueError, KeyError, AttributeError):   # a damaged stored row is skipped
                r = None
            if r:
                out.append((key, r))
    return out


def same_event(rec, it, pl, nt):
    """True when the official item `it` (pins `pl`) reports the event of Radar record `rec`: same link, or same
    provider (rec["match"]), overlapping time (RADAR_SLACK either side) and a shared region: the same city when both
    are pinned at regions, else the same region code, else (either names none) yes."""
    if it["source"] not in rec["match"]:
        return False
    if it["url"] and it["url"] == rec.get("url") and it["url"] != SOURCES[it["source"]]["page"]:
        return True                                  # Radar linked this very incident (not just the status page)
    lo, hi = rec["start"] - RADAR_SLACK, (rec["end"] or nt) + RADAR_SLACK
    a = (it["start_ms"] or it["ts_ms"]) // 1000
    b = it["end_ms"] // 1000 if it["end_ms"] else (nt if it["active"] else it["ts_ms"] // 1000)
    if b < lo or a > hi:
        return False
    rc = {p["city"] for p in rec["pins"] if p["place"] == "region"}
    ic = {p["city"] for p in pl or [] if p["place"] == "region"}
    if rc and ic:
        return bool(rc & ic)
    rk, ik = ({re.sub(r"[\s_-]+", "", str(c).lower()) for c in xs or []} for xs in (rec.get("codes"), it.get("regions")))
    return not rk or not ik or bool(rk & ik)                # "UAE North" == "uaenorth"; an unplaced side counts


def _radar_row(key, radar, mine, nt):
    r = (radar or {}).get(RADAR[key]["from"]) or {}
    ok, err = bool(r.get("ok")), r.get("error")
    if not r.get("t"):
        ok, err = False, "not fetched yet (the power / cell feeds fetch Radar)"
    elif nt - r["t"] > RADAR_STALE:
        ok, err = False, "stale: the power / cell feeds last fetched Radar at %s" % _iso(r["t"])
    return {"name": key, "label": RADAR[key]["label"], "ok": ok, "error": err,
            "checked": _iso(r["t"]) if r.get("t") else None, "good": _iso(r["good"]) if r.get("good") else None,
            "newest": _iso(max(i["ts_ms"] for i in mine) // 1000) if mine else None, "n": len(mine),
            "active": sum(1 for i in mine if i["active"])}


# ---------------- polling ----------------

def _due(s, key, nt):
    src = SOURCES[key]
    wait = src["every"] if s.get("ok") else src["retry"]
    return not s.get("t") or nt - s["t"] >= wait - SLACK


def _run_source(key, s, fetch, now):
    """Fetch and parse one source into its new state (conditional GET; a 304 keeps the cached data)."""
    src = SOURCES[key]
    has = isinstance(s.get("data"), dict)
    res = fetch(src["url"], s.get("etag") if has else None, s.get("lm") if has else None)
    if isinstance(res, (bytes, bytearray)):
        res = {"status": 200, "body": bytes(res)}
    if res.get("status") == 304 and has:
        s["not_modified"] = True                       # unchanged: for live-only lists, nothing vanished either
        return s
    body = res.get("body")
    if body is None:
        raise ValueError("empty response (HTTP %s)" % res.get("status"))
    data = PARSERS[src["fmt"]](body, now, src, s.get("data") if has else None)
    s.update(data=data, etag=res.get("etag"), lm=res.get("lm"), not_modified=False)
    return s


def poll(feed, now=None, fetch=None, clock=time.monotonic):
    """Fetch the due sources of `feed` and build its data dict (the contract in the module docstring)."""
    now, fetch = _utc(now), fetch or _fetch
    nt = int(now.timestamp())
    keys = FEED_SOURCES[feed]
    with _LOCK:
        st = _load(STATE_FILE)
        srcs = st.get("sources") if isinstance(st.get("sources"), dict) else {}
        due = [k for k in keys if _due(srcs.get(k) if isinstance(srcs.get(k), dict) else {}, k, nt)
               and k not in _INFLIGHT]
        due.sort(key=lambda k: ((srcs.get(k) or {}).get("t") or 0, keys.index(k)))
        _INFLIGHT.update(due)
    updated = {}
    try:
        t0, fails = clock(), 0
        for k in due:
            if fails >= MAX_FAILS or clock() - t0 > TIME_BUDGET:
                break
            s = dict(srcs.get(k) or {}) if isinstance(srcs.get(k), dict) else {}
            try:
                s = _run_source(k, s, fetch, now)
                s.update(ok=True, error=None, good=nt)
                fails = 0
            except Exception as e:  # noqa: BLE001  one source never fails the feed
                s.update(ok=False, error=_err(e))
                fails += 1
            s["t"] = nt
            updated[k] = s
    finally:
        with _LOCK:
            _INFLIGHT.difference_update(due)
            st = _load(STATE_FILE)                     # the other feed may have written meanwhile
            srcs = st.get("sources") if isinstance(st.get("sources"), dict) else {}
            srcs = {k: v for k, v in srcs.items() if k in SOURCES and isinstance(v, dict)}
            srcs.update(updated)
            _save(STATE_FILE, {"version": VERSION, "sources": srcs})
    if not any((srcs.get(k) or {}).get("good") for k in keys):
        raise RuntimeError("%s: no source has answered yet: %s" % (feed, "; ".join(
            "%s %s" % (k, (srcs.get(k) or {}).get("error")) for k in keys if srcs.get(k))[:600]))
    try:
        radar = disruption.radar_rows()            # read only: the power / cell feeds fetch Radar
    except Exception:  # noqa: BLE001  Radar never fails these feeds
        radar = {}
    return build(feed, srcs, nt, radar)


def build(feed, srcs, nt, radar=None):
    items, pls = [], {}
    for key in FEED_SOURCES[feed]:
        data = (srcs.get(key) or {}).get("data") or {}
        for rec in data.get("records") or []:
            if not isinstance(rec, dict) or not rec.get("sid") or _route(key, rec) != feed:
                continue
            it, pl = make_item(feed, key, rec, nt)
            if it and it["id"] not in pls:
                items.append(it)
                pls[it["id"]] = pl
    official, matched = list(items), 0
    for key, rec in radar_records(radar, nt):
        if rec["route"] != feed or key not in FEED_RADAR[feed]:
            continue
        it, pl = make_item(feed, key, rec, nt)
        if not it or it["id"] in pls:
            continue
        same = [o for o in official if same_event(rec, o, pls[o["id"]], nt)]
        if same:                                   # the provider's own report stands; it gets the tag
            for o in same:
                o["tags"] = o["tags"] + ([] if "radar" in o["tags"] else ["radar"])
            matched += 1
            continue
        items.append(it)
        pls[it["id"]] = pl
    items.sort(key=lambda i: (-i["ts_ms"], i["id"]))
    full = list(items)
    items, trimmed = _cap(items)
    pops = None
    if feed == "cloud":
        cf = ((srcs.get("cloudflare") or {}).get("data") or {}).get("pops") or {}
        pops = {"total": cf.get("total", 0), "partial_outage": cf.get("partial_outage", 0),
                "under_maintenance": cf.get("under_maintenance", 0),
                "named": sorted({c for i in full if i["source"] == "cloudflare" and i["active"] and i["place"] == "pop"
                                 for c in i["regions"]})}
    sources = []
    for key in FEED_SOURCES[feed]:
        s = srcs.get(key) or {}
        mine = [i for i in full if i["source"] == key]
        sources.append({"name": key, "label": SOURCES[key]["label"], "ok": bool(s.get("ok")), "error": s.get("error"),
                        "checked": _iso(s["t"]) if s.get("t") else None,
                        "good": _iso(s["good"]) if s.get("good") else None,
                        "newest": _iso(max(i["ts_ms"] for i in mine) // 1000) if mine else None, "n": len(mine),
                        "active": sum(1 for i in mine if i["active"])})
    for key in FEED_RADAR[feed]:
        sources.append(_radar_row(key, radar, [i for i in full if i["source"] == key], nt))
    out = {"version": VERSION, "fetched_at": _iso(nt), "count": len(items), "trimmed": trimmed, "items": items,
           "geojson": geojson(items, pls, feed), "sources": sources,
           "summary": _summary(feed, full, srcs, pops, matched),
           "note": NOTE[feed], "attribution": _attribution(feed), "public_ok": PUBLIC_OK[feed],
           "non_commercial": NON_COMMERCIAL[feed], "board": board(feed, srcs, full)}
    if feed == "cloud":
        out["pops"] = pops
    while out["items"] and len(json.dumps(out, separators=(",", ":"), ensure_ascii=False).encode()) > MAX_BYTES:
        keep, extra = _cap(out["items"], max(1, len(out["items"]) * 9 // 10), budget=10 ** 12)
        out.update(items=keep, count=len(keep), trimmed=out["trimmed"] + extra, geojson=geojson(keep, pls, feed))
    return out


def websites(now=None, fetch=None, clock=time.monotonic):
    """The `websites` feed: website and online-service disruptions from official status pages."""
    return poll("websites", now, fetch, clock)


def cloud(now=None, fetch=None, clock=time.monotonic):
    """The `cloud` feed: AI services, cloud providers, Cloudflare PoPs and datacenter incidents."""
    return poll("cloud", now, fetch, clock)


FEEDS = {
    "websites": (websites, 300),
    "cloud": (cloud, 300),
}
