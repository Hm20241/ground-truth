# Changelog

## 1.5.4 (2026-11-21): Cloudflare Radar API outage records on the power and cell layers (self-hosted only)
- **Two new sources in `gt/disruption.py` 1.1:** the Cloudflare Radar API's outage annotations and its traffic anomalies, each polled every 15 minutes and shared by the power and cell feeds.
  - Power cuts go on the power layer, mobile-network outages on the cell layer, and the rest in the Internet list. Single-service (PLATFORM) records are left out for now.
  - Each record is pinned at its Ukrainian oblast or Russian region where Radar names one, else at its country. Severity follows Radar's scope (nationwide, regional, one network).
  - Radar's own social posts that repeat an annotation are dropped.
- **Needs a free Cloudflare API token** with Account > Radar > Read. `tools/cfradar-key.sh` saves it, hidden, to `~/.config/cloudflare/radar_token`; a container reads `$GT_SEED/cfradar.key`. Without one, both sources say "not configured" and the feeds carry on.
- **Popups name the link:** "Radar Outage Center", "Radar traffic page" or "Cloudflare's post".
- **Not on this copy:** Radar data is CC BY-NC 4.0, and the power and cell feeds stay on self-hosted copies only.

## 1.5.3 (2026-11-21): outage layers for power, cell networks, websites and AI / cloud (self-hosted only)
- **New modules:** `gt/services.py` and `gt/disruption.py`, plus the page extension `web/ext/outages.js`.
- **Four separate map layers,** each with its own Feed chip:
  - **Power outages:** US county outages from ODIN, Ukraine's grid operator and energy ministry, Taiwan's supply light, South Africa's load-shedding stage and California grid emergencies.
  - **Cell / mobile networks:** mobile-network disruption posts from NetBlocks and Cloudflare Radar, and Russia's regional mobile-internet shutdowns.
  - **Websites / online services:** official status pages.
  - **AI, cloud and datacenters:** official status pages, Cloudflare PoP incidents and datacenter incident headlines.
- **Also new:** an Outages tab, KPIs and source credits.
- **Not on this copy:** none of these sources has a clear licence to republish, so all four feeds run on self-hosted copies only. Here the layers stay empty and the Outages tab says "Not on this copy".
- **Downdetector is not used:** it has no free API, and its terms forbid automated access.

## 1.5.2 (2026-11-21): "--GitHub" in the GitHub Pages tab title
- On GitHub Pages (any `*.github.io` host) the tab and window title reads "Ground Truth --GitHub", so this copy is easy to tell apart from a self-hosted one. A self-hosted copy keeps "Ground Truth".

## 1.5.1 (2026-11-21): date-only rows never in the future; real icon files
- A date-only Feed row sits at the start of its day, but never later than now. A source ahead of the page's zone (Taiwan's defence ministry dates its report in Taiwan time) used to sort up to 4 hours into the future, above every newer item. Its label still names the source's own day, and the tooltip says so.
- The page icon now comes from files beside the page: `favicon.svg`, a 32 px PNG and a 180 px `apple-touch-icon.png`. Before, it was only an inline SVG, which Safari and iOS commonly skip.

## 1.5.0 (2026-11-21): mobile layout, news ticker, resizable sidebars, warships worldwide, more sources, translations
- Phones: two columns in landscape. In portrait, a better map/list split, with the timeline hidden on small screens.
- Popups fit the screen and sit above the map controls.
- The header takes two rows on phones, and its stats strip swipes sideways. Tap targets are larger.
- The rail drawer gets a backdrop, closes on Escape and has a close button. Tabs and source chips scroll sideways.
- The search box is 16 px, so iOS does not zoom. The layout keeps to the safe-area insets.
- Sidebars on a PC: drag either sidebar's inner edge to resize it (double-click resets it); a tab collapses it so the map gets the room. Saved per browser.
- News ticker: a broadcast-style ticker under the header shows the newest Feed items, with flag, country, headline and time since. It updates by itself, holds on hover or focus and scrolls with the wheel. SRC picks its source groups; a pause button and a speed button (0.5x to 3x) sit beside it. All saved per browser.
- Feed rows with a place get a "View on map" button.
- On the public copy the page no longer tries the push stream, and the post-text button is hidden. The public status lists only the feeds the copy carries.
- The ticker runs in category segments, each opened by a coloured category block, strikes first and other news last.
- Warships worldwide: AIS samples listen worldwide and keep military ships wherever they are heard. They are drawn larger with a white outline and labelled from zoom 4.5, and a Military card in the Sea tab lists them by flag.
- News wire: 44 RSS feeds and 30 Google News searches (attacks on Russia and Iran, interceptions, ballistic launches, sirens and drone launches worldwide, Iran and the Middle East). Every Google query is kept under 200 characters, past which Google ignores `when:1d`. Telegram: 14 channels.
- English translations of non-English wire and Telegram items (`gt/translate.py`, `analyst.py translate`). Each one is tagged "EN · from …", with the original in the tooltip.
- The panel's tabs wrap to a second row instead of running past a narrow panel.

## 1.4.3 (2026-11-20): tooltips on a PC
- With a mouse, every element with a title gets a styled tooltip after a short delay, in place of the browser's plain one. Touch screens are left alone, and screen readers still read the title.
- New titles: what each KPI tile counts, each layer's source and freshness, every tab, theatre and category, and the time range buttons.

## 1.4.2 (2026-11-20): every map layer starts on
- The core layers that started off (travel advisories, GDELT, EASA conflict-zone airspace, submarine cables) and the cyber, TFR, GPSJAM and news-volume layers now start on. Their data was already loaded, so the page makes no new requests.

## 1.4.1 (2026-11-20): the time in the title bar, a bigger PC header
- Each Feed row's date, time and time since move into its title bar.
- On a PC (901 px and wider) the header is taller and easier to read, with the clock between the brand and the live light. The KPI strip is centred. Phones keep the compact header.

## 1.4.0 (2026-11-20): a title bar on every Feed item, and the version with a live light
- Every Feed row opens with a bar: flag, country, then the category in the item's colour. Stream items name their country in a new `cc` field (GTX API 1.4). With no country the bar names the sea, the theatre or "Global", and never guesses. Where the system draws no emoji flags, the ISO code shows in a small box. Country names are searchable.
- The header shows the page's version and a live light: Live (push stream connected), Polling, Offline, Public copy or Connecting. Its tooltip gives the reason, the page and server versions, and how many feeds are OK.
- The source map's "Day N" tile leaves the header strip.

## 1.3.0 (2026-11-20): Eastern time by default, and the time since
- Every time shows in Eastern time (EST/EDT) by default, with the time since ("3h ago"; future times read "in 2h"). The header clock or the rail's Times chips switch to UTC, and the choice is saved per browser.
- Date-only items (CENTCOM, UKMTO, OFAC, PLA, losses, CZIB, some map pins) stay on their own day in either zone, and the time filters span that whole day.
- Analyst prose stays in UTC, with the Eastern time beside each "HH:MMZ". The API stays in UTC.
- GTX API 1.3: `when`, `fmtDay`, `zone()`.

## 1.2.0 (2026-11-20): one Feed for every source
- The Feed tab merges the map pins and 17 other sources, newest first, with a chip per source group (Map pins, Official, Maritime, Alerts, Internet, Airspace, Hazards, Cyber, Wire, Telegram). The theatre, time range, brush, category chips and search all apply. It draws 300 rows, then "Show more".
- `web/geo/theatres.json` maps countries to theatres, so items that only name a country follow the theatre filter and can fly the map.
- Tools: `tools/build_theatres.py`, `tools/live_proxy.py` (try a page change against a running instance's API, GET only) and `tools/feed_check.js` (a headless check of the Feed tab).
- Positions and measurements (fire pixels, ships, aircraft, ship-traffic counts, the front line, cables, GPSJAM) stay map layers.

## 1.1.0 (2026-11-20): GPS jamming and spoofing hexes (GPSJAM)
- A map layer of GPSJAM's daily interference hexes: amber where 2–10 % of aircraft are affected, red over 10 %. Popups give the counts and link to GPSJAM.
- h3-js 4.5.0 (Apache-2.0) is vendored in `web/vendor/` to turn H3 cell ids into hexagons, with its hash pinned in the tests. Cells across the antimeridian are kept whole.
- GPSJAM states no licence, so the layer is non-commercial and not on the public copy.

## 1.0.0 (2026-11-20): real time everywhere, all theatres in the brief
- Brief tab: "All sources by theatre", one row per theatre and one column per source (source map, GeoConfirmed, CIR, GDACS, wire, Telegram), built in the page through `GTX.briefColumn` (GTX API 1.1). `/api/brief` is unchanged.
- Official releases (War Department, UK MoD) every 10 min, was 30. CENTCOM keeps its 6 h cache and daily Firecrawl cap.

## 0.13.0 (2026-11-20): strategic signals, airspace, cyber and internet routing
- Signals: tsunami and volcano bulletins (PTWC, NTWC, JMA), Germany's BfS gamma network checked against each station's own baseline, OFAC recent actions and DHS NTAS advisories. A Signals tab and map points.
- Airspace: emergency squawks 7500/7600/7700 worldwide (adsb.lol), FAA temporary flight restrictions with shapes, and GPSJAM's daily feed (drawn from 1.1.0).
- Cyber: CISA KEV, ICS and general advisories, Ransomware.live claims and press-reported attacks, SANS ISC infocon and DDoSia target lists; victim names, domains and target IPs are never stored. RIPEstat routing visibility for 19 watched countries against a 7-day baseline. A Cyber layer and tab, and `/api/cyber_geo`.
- All eight extension modules are now enabled.

## 0.12.0 (2026-11-20): news wire and Telegram
- News wire: 25 publisher RSS feeds and 15 Google News searches, each on its own cadence, 48 h of stories, with the same story from several outlets merged.
- Ten public Telegram channels, read from their web previews every 5 min.
- `gt/placer.py` places stories and posts on countries and a theatre from their text.
- A Wire tab (wire and Telegram lists that follow the theatre, a text filter, "Most covered" and a country filter), a news-volume layer, and `/api/news_geo`.
- Both sources are non-commercial and not on the public copy.

## 0.11.0 (2026-11-20): extension modules, verified pins, natural hazards, push
- Extension modules: `gt/extfeeds.py` loads the modules a release enables. Each module declares its feeds and its sources' terms (`LICENCE`, `ATTRIBUTION`, `PUBLIC_OK`, `NON_COMMERCIAL`), and a module that fails to load never stops the server. Page extensions in `web/ext/` use the `window.GTX` API.
- GeoConfirmed volunteer geolocations worldwide, CIR Eyes on Russia and S2 Underground's Iran kinetic events join the event layer. The source map wins, and duplicate posts are dropped.
- GDACS disaster alerts and EMSC + USGS earthquakes M4+, with explosion types and shallow quakes in watched areas flagged.
- Push: `/api/stream` (Server-Sent Events) tells open pages when a feed changes, with polling as the fallback. `/api/status` gains each feed's interval, a stale flag and the modules, and the Sources tab shows each feed's freshness.
- `/api/digest` for the analyst. Analyst 1.4 reads it, so its pictures draw on non-commercial sources.

## 0.10.0 (2026-11-19): source-map auto-follow
- The curator starts a new My Maps file about weekly and links it from their channel. Ground Truth reads the channel's public RSS feed and follows the newest linked map when its "Day N" is at least the current one, keeping the previous map's pins for 48 h while the new map fills. A hand change of the configured map always wins.
- The rail shows the auto-follow state, and the Feed shows a notice for 12 h after the map moves.
- Map and channel IDs stay private: status and summary carry days, times and flags only.

## 0.9.1 (2026-11-19): source-map freshness
- The Feed tab warns when the source map has had no new pin for 12 h, with the newest pin's time and when Ground Truth last checked the map; the notice turns red when the check is failing. The rail shows the newest pin's age and the last check.

## 0.9.0 (2026-11-19): tankers and commercial shipping
- AIS sampler 1.1: compressed websocket (permessage-deflate), a back-off after HTTP 429, a 30-day vessel registry learnt from static reports (type, IMO, size, destination, ETA, draught), and tanker tracks. Four more areas: Singapore/Malacca, Gibraltar, the Dover Strait and the US Gulf coast. The Gulf and Red Sea boxes are marked "no live receiver coverage".
- Flag state from the MMSI (ITU Maritime Identification Digits).
- IMF PortWatch daily chokepoint transits: 28 chokepoints, tankers per day against the same week a year ago, a 30-day sparkline. About 3 days behind.
- OpenSanctions maritime list marks: sanctioned ships and ships on Ukraine's GUR shadow-fleet list get rings; port-state detentions show in popups and cards.
- Page: tanker icons with headings, tracks, ship filter chips, a chokepoint layer and table, a "Hormuz tankers/day" KPI and a listed-ship card.
- PortWatch and OpenSanctions data are non-commercial: their summary keys are in `server.NON_COMMERCIAL_KEYS`, and the page credits them wherever they appear.

## 0.8.0 (2026-11-18): US embassy alerts
- Alert RSS from 38 US embassies and consulates, classified (departure or closure, shelter, demonstration, weather, health, advisory, security), merged across posts and kept 7 days. Map rings, popups, an Alerts card, and a banner for shelter or departure alerts.

## 0.7.0 (2026-11-18): air-raid and missile alerts
- Israel sirens (Tzeva Adom) and Ukraine, Russia and Poland air-raid alerts (alerts.in.ua), with region shapes, an Alerts tab and a banner. New endpoint `/api/alerts`.

## 0.6.0 (2026-11-16): military aircraft identity
- Aircraft types and operators from hexdb.io, cached per airframe. The registry name beats the transponder designator (a KC-46A sends "B762").
- Role-based silhouette icons: tanker, ISR, fighter, transport, helicopter, tiltrotor, drone, jet, light. Tankers blue, ISR and drones amber, bombers violet, emergencies red.
- Planespotters photos, fetched by the browser with the photographer credited.
- Popups pan into view.
- Summary keys `mil_aircraft_by_role` and `mil_aircraft_notable`.

## 0.5.0 (2026-11-15): Global Fishing Watch ship traffic (analyst 1.3)
- Daily non-fishing ship counts for 4 chokepoints and 6 seas over a year, compared with the same week last year, plus ship lists at chokepoints and AIS-off events. Refreshed every 6 h.
- Data is CC BY-NC 4.0: flagged non-commercial in the summary, with attribution wherever it appears.
- The analyst explains the ship-traffic counts.

## 0.4.0 (2026-11-15): outages, advisories, ships (analyst 1.2)
- IODA internet outages, by country and for watched regions.
- US State Department travel advisories (Level 3–4 map layer and a level-change log).
- War Department releases.
- A second fire satellite (NOAA-21).
- AISStream live ship positions.

## 0.3.1 (2026-11-15): CENTCOM releases
- CENTCOM public releases read through Firecrawl every 6 h, cached, with a per-source daily cap.

## 0.3.0 (2026-11-15): analyst agent (analyst 1.0, 1.1)
- Per-event notes and a whole-picture assessment by Claude, run headless with no tools, posted to a token-gated API and shown escaped.
- 1.1 adds an optional slow mode that expires on its own.

## 0.2.0 (2026-11-15): container
- Runtime image with a supervisor that hot-reloads the app when `VERSION` changes.
- Works behind a reverse-proxy path prefix.

## 0.1.0 (2026-11-15): first prototype
- My Maps ingest, classification, timestamps and archive.
- Live feeds and the watch floor client.
