// Ground Truth page extension: airspace signals (0.13.0 ext 1.0; 1.1.0 ext 1.1 adds the GPSJAM hexes; 1.2.0 ext 1.2 Feed-tab streams;
// 1.3.0 ext 1.3 times in the page's zone with the time since; 1.4.0 ext 1.4 Feed items carry cc (country) for the title bar;
// 1.4.2 ext 1.5 TFR and GPSJAM layers start on, like every layer).
// Emergency squawks 7500/7600/7700 worldwide (adsb.lol, adsb.fi fallback), US temporary flight restrictions (FAA)
// and GPSJAM's daily GNSS-interference hexes. Feeds: /api/feed/squawk (60 s), /api/feed/tfr (15 min),
// /api/feed/gpsjam (hourly check, new day ~00:00 UTC), from gt/airspace.py.
// GPSJAM sends H3 cell ids (resolution 4); the page turns them into hexagons with h3-js (vendor/h3-js.umd.js,
// window.h3). GPSJAM states no licence: private page only, non-commercial, never on the public mirror.
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { esc, fmtT, fmtD, nf, isoMs, showPopup } = GTX;
  const empty = { type: "FeatureCollection", features: [] };
  const SQ_COL = { "7500": "#f05252", "7700": "#f2853d", "7600": "#facc15" };
  const TFR_COL = { active: "#f05252", upcoming: "#f2b33d", unknown: "#9aa4ae", expired: "#5d656e" };
  const GJ_COL = { medium: "#f2b33d", high: "#f05252" };  // GPSJAM's own scale is yellow / red; low hexes are not sent
  const when = (v, rel) => GTX.when(v, rel);  // 1.3.0: the page's zone (Eastern or UTC) and the time since
  const link = (u) => (/^https?:\/\//i.test(u || "") ? u : null);  // 1.7.3: only http(s) addresses become links
  const gjShare = (good, bad) => Math.max(0, (bad - 1) / (good + bad));  // GPSJAM's rule (gt/airspace.py level())

  GTX.layer({ key: "squawk", label: "Emergency squawks 7500 / 7600 / 7700 (live)", feed: "squawk", after: "mil",
    ids: ["sq-halo", "sq-pt", "sq-label"], click: ["sq-pt"], clickBefore: "mil-pt",
    count: () => (GTX.S.feeds.squawk || {}).count,
    legend: [["7500", "7500 unlawful interference"], ["7700", "7700 emergency"], ["7600", "7600 radio failure"]]
      .map(([c, t]) => `<span><i class="lsw" style="background:${SQ_COL[c]}"></i>${t}</span>`).join("") });
  GTX.layer({ key: "tfr", label: "US flight restrictions (FAA TFRs)", feed: "tfr", after: "czib",
    ids: ["tfr-fill", "tfr-line"], click: ["tfr-fill"], clickBefore: "cz-fill",
    count: () => { const t = GTX.S.feeds.tfr; return t ? (t.by_status || {}).active : null; },
    legend: [["active", "active"], ["upcoming", "upcoming"], ["unknown", "times not read yet"]]
      .map(([s, t]) => `<span><i class="lsw" style="background:${TFR_COL[s]}"></i>${t}</span>`).join("") });
  GTX.layer({ key: "gpsjam", label: "GPS jamming / spoofing (GPSJAM, daily)", feed: "gpsjam", after: "tfr",
    ids: ["gj-fill", "gj-line"], click: ["gj-fill"], clickBefore: "cz-fill",
    count: () => { const g = GTX.S.feeds.gpsjam; return g ? g.count : null; },
    legend: [["medium", "2–10 % of aircraft"], ["high", "over 10 %"]]
      .map(([l, t]) => `<span><i class="lsw" style="background:${GJ_COL[l]}"></i>${t}</span>`).join("") });

  // GPSJAM items [h3, level, good, bad] -> GeoJSON hexagons. A cell that crosses the antimeridian gets its western
  // longitudes shifted by +360 so MapLibre draws one small hexagon, not a band around the world.
  function gjGeo(g) {
    if (!g || !Array.isArray(g.items) || typeof window.h3 === "undefined") return empty;
    const features = [];
    for (const [h, level, good, bad] of g.items) {
      let ring;
      try { ring = window.h3.cellToBoundary(h, true); } catch (e) { continue; }
      const lons = ring.map((p) => p[0]);
      if (Math.max(...lons) - Math.min(...lons) > 180) ring = ring.map(([x, y]) => [x < 0 ? x + 360 : x, y]);
      features.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] },
        properties: { h3: h, level, good, bad, share: gjShare(good, bad) } });
    }
    return { type: "FeatureCollection", features };
  }

  GTX.onMapLoad((map) => {
    map.addSource("squawks", { type: "geojson", data: empty });
    map.addSource("tfrs", { type: "geojson", data: empty });
    map.addSource("gpsjam", { type: "geojson", data: empty });
    const vis = (key) => ({ visibility: GTX.layerOn(key) ? "visible" : "none" });
    map.addLayer({ id: "gj-fill", type: "fill", source: "gpsjam", layout: vis("gpsjam"), paint: {
      "fill-color": ["match", ["get", "level"], "high", GJ_COL.high, GJ_COL.medium],
      "fill-opacity": ["match", ["get", "level"], "high", 0.42, 0.26] } }, "cz-fill");
    map.addLayer({ id: "gj-line", type: "line", source: "gpsjam", layout: vis("gpsjam"), paint: {
      "line-color": ["match", ["get", "level"], "high", GJ_COL.high, GJ_COL.medium],
      "line-width": 0.6, "line-opacity": 0.6 } }, "cz-fill");
    map.addLayer({ id: "tfr-fill", type: "fill", source: "tfrs", layout: vis("tfr"), paint: {
      "fill-color": ["match", ["get", "status"], "active", TFR_COL.active, "upcoming", TFR_COL.upcoming, "expired", TFR_COL.expired, TFR_COL.unknown],
      "fill-opacity": ["match", ["get", "status"], "active", 0.16, 0.08] } }, "cz-fill");
    map.addLayer({ id: "tfr-line", type: "line", source: "tfrs", layout: vis("tfr"), paint: {
      "line-color": ["match", ["get", "status"], "active", TFR_COL.active, "upcoming", TFR_COL.upcoming, TFR_COL.unknown],
      "line-width": 1.2, "line-opacity": 0.8 } }, "cz-fill");
    map.addLayer({ id: "sq-halo", type: "circle", source: "squawks", layout: vis("squawk"), paint: {
      "circle-radius": 16, "circle-color": ["match", ["get", "squawk"], "7500", SQ_COL["7500"], "7700", SQ_COL["7700"], SQ_COL["7600"]],
      "circle-opacity": 0.18, "circle-stroke-width": 1.5,
      "circle-stroke-color": ["match", ["get", "squawk"], "7500", SQ_COL["7500"], "7700", SQ_COL["7700"], SQ_COL["7600"]] } });
    map.addLayer({ id: "sq-pt", type: "circle", source: "squawks", layout: vis("squawk"), paint: {
      "circle-radius": 6, "circle-color": ["match", ["get", "squawk"], "7500", SQ_COL["7500"], "7700", SQ_COL["7700"], SQ_COL["7600"]],
      "circle-stroke-width": 1.5, "circle-stroke-color": "#0b0e11" } });
    map.addLayer({ id: "sq-label", type: "symbol", source: "squawks", layout: Object.assign(vis("squawk"), {
      "text-field": ["concat", ["get", "squawk"], " ", ["coalesce", ["get", "flight"], ["get", "hex"]]],
      "text-size": 11, "text-offset": [0, 1.5], "text-anchor": "top", "text-font": ["Open Sans Regular"] }),
      paint: { "text-color": "#f4f4f5", "text-halo-color": "#0b0e11", "text-halo-width": 1.2 } });
  });

  GTX.feed("squawk", (d) => { const s = GTX.map.getSource("squawks"); if (s) s.setData(d.geojson || empty); });
  GTX.feed("tfr", (d) => { const s = GTX.map.getSource("tfrs"); if (s) s.setData(d.geojson || empty); });
  GTX.feed("gpsjam", (d) => { const s = GTX.map.getSource("gpsjam"); if (s) s.setData(gjGeo(d)); });
  // 1.2.0 (ext 1.2): emergency squawks and FAA TFRs also run in the main Feed tab (GPSJAM is a daily map, not a feed).
  // 1.4.0 (ext 1.4): cc for the Feed row's title bar: the server's country for the aircraft's position (none without one);
  // a TFR is US airspace (territories included), so always the US.
  GTX.stream({ key: "squawk", group: "airspace", label: "Squawk", data: () => GTX.S.feeds.squawk, items: (d) => (d.items || []).map((i) => ({
    id: "sq:" + i.hex + i.first_seen, ts: isoMs(i.first_seen), title: `Squawk ${i.squawk}${i.meaning ? " (" + i.meaning + ")" : ""}: ${i.flight || i.reg || i.hex}${i.desc ? " · " + i.desc : ""}`,
    badge: i.current ? "now" : i.mil ? "military" : "", ll: Array.isArray(i.pos) ? i.pos : null, zoom: 7, cc: i.country || undefined })) });
  const at = (iso) => { const t = isoMs(iso); return t ? fmtD(t) + " " + fmtT(t) : ""; };
  const tfrSpan = (i) => (i.effective ? "from " + at(i.effective) + (i.expires ? " to " + at(i.expires) : "") : i.expires ? "to " + at(i.expires) : "");
  GTX.stream({ key: "tfr", group: "airspace", label: "FAA TFR", data: () => GTX.S.feeds.tfr, items: (d) => (d.items || []).map((i) => ({
    // sorted by when the FAA issued or last changed it; many TFRs are published days before they start
    id: "tfr:" + i.notam_id, ts: isoMs(i.mod) || isoMs(i.effective), title: `TFR ${i.notam_id}: ${i.type || ""} · ${i.title || ""}`, url: i.url,
    where: tfrSpan(i), badge: i.is_new ? "new" : "", text: i.text,
    th: i.theatre || null, ll: Array.isArray(i.centre) ? i.centre : null, zoom: 8, cc: "USA" })) });

  GTX.popup("sq-pt", (f, lngLat) => {
    const p = f.properties, alt = p.alt === "ground" ? "on the ground" : p.alt != null ? nf(p.alt) + " ft" : "altitude unknown";
    const confirmed = p.emergency && p.emergency !== "none";
    showPopup(lngLat, `<div class="pop"><h5>Squawk ${esc(p.squawk)}: ${esc(p.meaning || "")}</h5>
      <div class="meta">${esc(p.flight || "no callsign")} · ${esc(p.reg || p.hex)}${p.type ? " · " + esc(p.type) : ""}${p.mil ? " · military" : ""}</div>
      <div>${alt}${p.gs != null ? " · " + Math.round(p.gs) + " kt" : ""} · ${esc(p.country_name || p.sea || "")}${p.mlat ? " · MLAT position (estimate)" : ""}</div>
      <div>${confirmed ? `Transponder emergency field: <b>${esc(p.emergency)}</b>.` : "No emergency field from the transponder: may be a mis-set code."}
        Seen in ${nf(p.polls)} check${p.polls === 1 ? "" : "s"} since ${when(p.first_seen)}.</div>
      <div><a href="https://globe.adsb.lol/?icao=${encodeURIComponent(p.hex)}" target="_blank" rel="noopener">Track on adsb.lol ↗</a></div>
      <div class="muted small">${esc((GTX.S.feeds.squawk || {}).attribution || "adsb.lol (ODbL)")}</div></div>`);
  });
  GTX.popup("tfr-fill", (f, lngLat) => {
    const p = f.properties;
    showPopup(lngLat, `<div class="pop"><h5>TFR ${esc(p.notam_id)}: ${esc(p.type || "")}</h5>
      <div class="meta">${esc(p.status)}${p.area ? " · " + esc(p.area) : ""} · ${esc(p.facility || "")} ${esc(p.state || "")}</div>
      <div>${esc(p.title || "")}</div>
      <div>${p.floor || p.ceiling ? `Altitudes: ${esc(p.floor || "?")} to ${esc(p.ceiling || "?")}` : "Altitudes and times: not read yet"}${p.effective ? `<br>From ${when(p.effective, false)} to ${p.expires ? when(p.expires, false) : "further notice"}` : ""}</div>
      ${link(p.url) ? `<div><a href="${esc(link(p.url))}" target="_blank" rel="noopener">FAA notice ↗</a></div>` : ""}
      <div class="muted small">FAA (tfr.faa.gov), US public domain. Not for navigation.</div></div>`);
  });
  GTX.popup("gj-fill", (f, lngLat) => {
    const p = f.properties, g = GTX.S.feeds.gpsjam || {}, total = p.good + p.bad;
    let lat = lngLat.lat, lon = lngLat.lng;
    try { if (window.h3) [lat, lon] = window.h3.cellToLatLng(p.h3); } catch (err) { /* 1.7.3: a cell h3 cannot read: link to the clicked point */ }
    const link = `https://gpsjam.org/?lat=${lat.toFixed(2)}&lon=${lon.toFixed(2)}&z=6&date=${encodeURIComponent(g.date || "")}`;
    showPopup(lngLat, `<div class="pop"><h5>GPS interference: ${p.level === "high" ? "high" : "medium"}</h5>
      <div class="meta">GPSJAM · UTC day ${esc(g.date || "?")}${g.suspect ? " · GPSJAM flags this day's data as suspect" : ""}</div>
      <div><b>${nf(p.bad)}</b> of ${nf(total)} aircraft in this hexagon reported degraded GPS accuracy
        (${Math.round(gjShare(p.good, p.bad) * 1000) / 10} % by GPSJAM's rule).</div>
      <div class="muted small">Usually jamming or spoofing, but not always: some military aircraft block their own antennas.
        Each hexagon is about 1,770 km².</div>
      <div><a href="${link}" target="_blank" rel="noopener">Open in GPSJAM ↗</a></div>
      <div class="muted small">${esc(g.attribution || "GPSJAM (gpsjam.org) by John Wiseman")}. No licence stated: private view, non-commercial.</div></div>`);
  });

  GTX.kpi(() => { const s = GTX.S.feeds.squawk; return s && s.count ? [[nf(s.count), "Emergency squawks now", (s.by_code || {})["7500"] > 0]] : []; });
  GTX.label("squawk", "Emergency squawks (adsb.lol → adsb.fi)");
  GTX.label("tfr", "FAA temporary flight restrictions");
  GTX.label("gpsjam", "GPS jamming / spoofing (GPSJAM, daily)");
  GTX.credit(`Emergency squawks: <a href="https://adsb.lol" target="_blank" rel="noopener">adsb.lol</a> (ODbL), adsb.fi as fallback.
    Flight restrictions: <a href="https://tfr.faa.gov" target="_blank" rel="noopener">FAA</a> (public domain, not for navigation).
    GPS interference: <a href="https://gpsjam.org" target="_blank" rel="noopener">GPSJAM</a> by John Wiseman, from airplanes.live and
    ADS-B Exchange data (no licence stated; non-commercial). Hexagons drawn with h3-js (Apache-2.0).`);
});
