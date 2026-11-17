# Changelog

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
