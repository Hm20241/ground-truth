# Changelog

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
