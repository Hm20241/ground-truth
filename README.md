# Ground Truth

An OSINT conflict watch floor. It turns the *Global War News Map* (a daily-updated public Google My Maps) into a timestamped, classified, archived feed, then fuses it with live open sources: front lines, fire satellites, maritime incidents, military aircraft, ship traffic, internet outages and travel advisories. Coverage is global: Ukraine–Russia, Europe/NATO, Middle East/Gulf, Indo-Pacific, South and Central Asia, Africa and the Americas.

An optional analyst agent (Claude, headless, no tools) writes a note on every new event and a whole-picture assessment every few hours.

![Watch floor, global view with the Brief tab](docs/shot-brief.png)

<img src="docs/shot-phone.png" alt="Phone layout" width="260">

## Run

```bash
cp config/mymaps.example.json config/mymaps.local.json   # then put the map ID in it
python3 server.py                                         # http://127.0.0.1:8790
GT_HOST=0.0.0.0 GT_PORT=8790 python3 server.py            # LAN / container
python3 -m gt.mymaps                                      # one-off ingest + archive
```

It needs only the Python 3.9+ standard library. State is written to `data/` (or `$GT_DATA`).

On macOS, privacy controls (TCC) can stop `/usr/bin/python3` from reading `~/Desktop`; use a Homebrew Python or keep the checkout elsewhere.

## Configuration

| Setting | Where |
|---|---|
| Source map ID | `config/mymaps.local.json` (git-ignored; see `config/mymaps.example.json`) or `$GT_MYMAPS_MID` |
| Firecrawl key (UKMTO, CENTCOM releases) | `$FIRECRAWL_API_KEY` or `~/.config/firecrawl/key` |
| AISStream key (ships) | `$AISSTREAM_API_KEY`, `$GT_SEED/aisstream.key` or `~/.config/aisstream/key` (`tools/aisstream-key.sh` saves it hidden) |
| Global Fishing Watch token (ship traffic) | `$GFW_API_TOKEN`, `$GT_SEED/gfw.key` or `~/.config/globalfishingwatch/key` (`tools/gfw-key.sh` saves it hidden) |
| Analyst write key | `$GT_SEED/analyst.token` or `$GT_DATA/analyst.token` on the server (with none, every analyst write is refused), `~/.config/ground-truth/analyst_token` for the runner |
| Analyst model access | the Claude Code CLI's own login, or a `claude setup-token` token in `~/.config/ground-truth/claude_token` |

Every other feed is keyless. `/api/status` shows the health of each feed.

Firecrawl use is capped per source per day (`FIRECRAWL_DAILY` in `gt/feeds.py`), so the free tier's 1,000 credits a month are enough. Run only one polling instance per key.

## Layout

| Path | What |
|---|---|
| `server.py` | One-port HTTP server, background scheduler, analysis (corroboration, brief, summary) |
| `gt/mymaps.py` | KML fetch, parse, classify, timestamp, archive (`data/snapshots`, `data/groundtruth.sqlite`) |
| `gt/feeds.py` | Live feeds and refresh intervals (`REGISTRY`) |
| `gt/ais.py` | AISStream ship sampler: a stdlib websocket client, 60 s sample every 5 min, ships kept 3 h |
| `gt/gfw.py` | Global Fishing Watch ship traffic: daily non-fishing ship counts for 4 chokepoints and 6 seas over a year, the same week last year, ship lists at chokepoints, AIS-off events. Every 6 h, about 4 days behind |
| `gt/aircraft.py` | Military aircraft identity: registry type and operator from hexdb.io (cached per airframe), and a role (tanker, ISR, fighter, transport, helicopter, ...) for the map icons |
| `gt/geo.py` | Offline country, sea and theatre lookup (Natural Earth 1:50m in `ref/`) |
| `gt/analysis.py` | Analyst results store (`$GT_DATA/analysis/`): per-event notes and whole-picture history |
| `web/` | Watch floor client (MapLibre GL). Every URL is relative, so it works behind a path prefix such as `/gt/` |
| `analyst/analyst.py` | The analyst runner: `cycle`, `events`, `picture`, `status`, `--dry-run`. Calls `claude -p` with no tools, no MCP and an empty working directory, and posts results to the server. Run `cycle` every 30 minutes from cron or launchd. Point it at your server with `base_url` in `analyst/config.json` or `$GT_BASE_URL` |
| `analyst/claude-token.sh` | Saves a long-lived Claude token for the runner, hidden |
| `deploy/image/` | Runtime container: Python plus a supervisor that runs the bind-mounted app and restarts it when `VERSION` changes |
| `tests/` | Offline tests (no network): `python3 -I tests/test_060.py`, `test_050.py`, `test_040.py`, `test_centcom.py` |
| `tools/local_test.py` | Runs the app on a throwaway copy of `data/` with Firecrawl off, on port 8791 |

## API

| Endpoint | Returns |
|---|---|
| `/api/events` | Curated map events and overlays, with `thermal` and `ukmto` corroboration |
| `/api/summary` | Compact KPIs, built for dashboard REST sensors |
| `/api/brief` | Rule-based per-theatre brief |
| `/api/status` | Health of every feed |
| `/api/feed/<name>` | One feed: mil, front, losses, firms, ukmto, gdelt, tzeva, pla, czib, official, outages, advisories, ships, gfw, cables |
| `/api/outages_geo`, `/api/advisories_geo` | Country shapes for the internet-outage and travel-advisory (Level 3–4) map layers |
| `/api/xpost?id=` | Text and media of one X post, fetched on demand and cached |
| `/api/analysis` | Analyst overview: latest picture, events analysed, recent runs |
| `/api/analysis/events` | Per-event analyst notes, keyed by event id |
| `/api/analysis/history?limit=&full=1` | Past whole-picture assessments, newest first |
| `POST /api/analysis/events`, `/api/analysis/picture` | Analyst writes. Need the `X-GT-Token` header |

## Data terms

- **Global Fishing Watch data is CC BY-NC 4.0, non-commercial only.** The page shows "Powered by Global Fishing Watch" linked to globalfishingwatch.org wherever the data appears, and the token stays server-side. `server.NON_COMMERCIAL_KEYS` lists the summary keys to strip before any commercial use, and analyst pictures written with prompt `pic3` or later contain GFW-derived reasoning.
- **Aircraft photos come from Planespotters.net** under its photo API terms: the browser asks the API directly, the image loads straight from their CDN with its URL unchanged, the photographer is credited next to it, and the thumbnail is a plain link to the photo page. Never store, proxy or re-host the images, and never use them or their metadata to build ML datasets.
- **Aircraft types and operators come from hexdb.io** (free, keyless), looked up once per airframe and cached.
- Country shapes are Natural Earth (public domain). The bundled MapLibre GL JS keeps its own BSD licence header.

## Caveats

- The source map is one curator's selection of social-media posts. Treat it as unverified.
- Categories are keyword-assigned.
- Analyst notes are model output from unverified posts. They're labelled with model, prompt version and time, and the page shows them escaped, as text only.
- Thermal hits include gas flares and industrial heat.
- AIS coverage comes from volunteer receivers: dense in Europe, none in the Gulf or Red Sea. Zero ships there means no data.
- GFW counts are about 4 days behind and only include ships transmitting AIS. A fall can mean fewer ships or more ships running dark. Chokepoint boxes also count ships at anchor inside them. AIS-off events come from a GFW prototype model and only count gaps that start at least 50 nm from shore.
- IODA outages are automatic detections. A Google-traffic dip alone is weak evidence.
- Scraped content stays private to the instance. Links go back to the originals.
