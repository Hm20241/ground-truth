// Ground Truth page extension: natural hazards (0.11.0, ext 1.1: 1.0.0 Brief column; ext 1.2, 1.2.0: Feed-tab streams;
// ext 1.3, 1.3.0: times in the page's zone with the time since; ext 1.4, 1.4.0: Feed items carry cc (country) for the title bar).
// GDACS alerts worldwide (earthquakes, cyclones, floods, volcanoes, droughts, wildfires; Green/Orange/Red) and
// earthquakes from EMSC + USGS, with shallow quakes in watched areas and any USGS "explosion" type ringed as a
// tripwire. Feeds: /api/feed/hazards (15 min), /api/feed/quakes (5 min), from gt/hazards.py.
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { esc, fmtT, fmtD, isoMs, nf, showPopup } = GTX;
  const empty = { type: "FeatureCollection", features: [] };
  const ALERT = { Red: "#f05252", Orange: "#f2853d", Green: "#3ecf8e" };
  const QK = "#67e8f9", WATCH = "#f2b33d";
  const link = (u) => (/^https?:\/\//i.test(u || "") ? u : null);  // 1.7.3: only http(s) addresses become links
  const when = (v, rel) => GTX.when(v, rel);  // 1.3.0: the page's zone (Eastern or UTC) and the time since

  GTX.layer({ key: "hazards", label: "Natural hazards (GDACS alerts)", feed: "hazards", after: "outages",
    ids: ["hz-green", "hz-pt", "hz-label"], click: ["hz-pt", "hz-green"], clickBefore: "th-pt",
    count: () => { const d = GTX.S.feeds.hazards; return d ? ((d.by_alert || {}).Orange || 0) + ((d.by_alert || {}).Red || 0) : null; },
    legend: Object.entries(ALERT).map(([k, c]) => `<span><i class="lsw dot" style="background:${c}"></i>${k}${k === "Green" ? " (zoom in)" : ""}</span>`).join("") });
  GTX.layer({ key: "quakes", label: "Earthquakes M4+ (EMSC, USGS)", feed: "quakes", after: "hazards",
    ids: ["qk-ring", "qk-pt"], click: ["qk-pt"], clickBefore: "th-pt",
    count: () => (GTX.S.feeds.quakes || {}).count,
    legend: `<span><i class="lsw dot" style="background:${QK}"></i>size = magnitude</span><span><i class="lsw ring" style="border-color:${WATCH}"></i>watch area or explosion</span>` });

  GTX.onMapLoad((map) => {
    map.addSource("hazards", { type: "geojson", data: empty });
    map.addSource("quakes", { type: "geojson", data: empty });
    const vis = (k) => ({ visibility: GTX.layerOn(k) ? "visible" : "none" });
    const col = ["match", ["get", "alert"], "Red", ALERT.Red, "Orange", ALERT.Orange, ALERT.Green];
    // Green alerts are minor: shown from zoom 4, and Green earthquakes not at all (the quakes layer has them).
    map.addLayer({ id: "hz-green", type: "circle", source: "hazards", minzoom: 4, layout: vis("hazards"),
      filter: ["all", ["==", ["get", "alert"], "Green"], ["!=", ["get", "type"], "EQ"]], paint: {
      "circle-radius": 4, "circle-color": ALERT.Green, "circle-opacity": 0.45,
      "circle-stroke-width": 1, "circle-stroke-color": "#0b0e11" } }, GTX.below.events);
    map.addLayer({ id: "hz-pt", type: "circle", source: "hazards", layout: vis("hazards"),
      filter: ["!=", ["get", "alert"], "Green"], paint: {
      "circle-radius": ["match", ["get", "alert"], "Red", 8, 7], "circle-color": col, "circle-opacity": 0.85,
      "circle-stroke-width": 1, "circle-stroke-color": "#0b0e11" } }, GTX.below.events);
    map.addLayer({ id: "hz-label", type: "symbol", source: "hazards", filter: ["!=", ["get", "alert"], "Green"],
      layout: Object.assign(vis("hazards"), { "text-field": ["concat", ["get", "type_label"], ": ", ["coalesce", ["get", "event_name"], ["get", "gdacs_country"], ""]],
        "text-size": 10.5, "text-offset": [0, 1.2], "text-anchor": "top", "text-max-width": 14, "text-optional": true, "text-font": ["Open Sans Regular"] }),
      paint: { "text-color": col, "text-halo-color": "#0b0e11", "text-halo-width": 1.2 } }, GTX.below.events);
    map.addLayer({ id: "qk-ring", type: "circle", source: "quakes", filter: ["==", ["get", "watch"], true], layout: vis("quakes"), paint: {
      "circle-radius": ["interpolate", ["linear"], ["coalesce", ["get", "mag"], 4], 4, 9, 7, 18],
      "circle-color": "rgba(0,0,0,0)", "circle-stroke-width": 2, "circle-stroke-color": WATCH } }, GTX.below.events);
    map.addLayer({ id: "qk-pt", type: "circle", source: "quakes", layout: vis("quakes"), paint: {
      "circle-radius": ["interpolate", ["linear"], ["coalesce", ["get", "mag"], 4], 4, 3, 7, 12],
      "circle-color": ["case", ["in", "explosion", ["get", "kind"]], ALERT.Red, QK], "circle-opacity": 0.7,
      "circle-stroke-width": 1, "circle-stroke-color": "#0b0e11" } }, GTX.below.events);
  });

  GTX.feed("hazards", (d) => { const s = GTX.map.getSource("hazards"); if (s) s.setData(d.geojson || empty); });
  GTX.feed("quakes", (d) => { const s = GTX.map.getSource("quakes"); if (s) s.setData(d.geojson || empty); });
  // 1.2.0 (ext 1.2): both feeds also run in the main Feed tab. A GDACS alert sorts by its latest episode.
  const pt = (f) => (f.geometry && f.geometry.type === "Point" ? f.geometry.coordinates : null);
  const feats = (d) => ((d.geojson || {}).features || []).filter((f) => f.properties);
  // 1.3.0: GDACS gives droughts and wildfires as dates only (UTC midnight); they show as those days
  const dayOnly = (p) => (p.type === "DR" || p.type === "WF") && isoMs(p.to || p.from) % 86400000 === 0;
  const span = (p, v) => (dayOnly(p) ? GTX.fmtDay(isoMs(v)) : when(v, false));
  // 1.4.0 (ext 1.4): cc for the Feed row's title bar. GDACS: only the countries GDACS itself names (affected, else iso3; ISO-3),
  // the pin's own country first when GDACS names it; none when GDACS names none. Quakes: the server's country for the epicentre.
  const gdCc = (p) => { const a = (p.affected || []).length ? p.affected : p.iso3 ? [p.iso3] : [];
    return !a.length ? undefined : a.includes(p.country) ? [p.country].concat(a.filter((c) => c !== p.country)) : a; };
  // GDACS gives a flood's end as a day still to come (live 11-24 02:35Z: "Flood in Indonesia", episode updated 11-23 23:06Z,
  // to 11-25 01:00Z), so the row sat "in 22h" above every newer item. An end not reached yet is not the latest news: the
  // event sorts by GDACS's last update of it (modified), never later than now. Droughts and wildfires keep their day rule.
  const latest = (p) => {
    const t = isoMs(p.to) || isoMs(p.from), now = Date.now();
    if (!(t > now) || dayOnly(p)) return t;
    const m = isoMs(p.modified);
    return m > 0 && m <= now ? m : now;
  };
  GTX.stream({ key: "hazards", group: "hazards", label: "GDACS", data: () => GTX.S.feeds.hazards, items: (d) => feats(d).map((f) => { const p = f.properties;
    return { id: "gd:" + p.id, ts: latest(p), day: dayOnly(p), title: `${p.alert ? p.alert + " alert: " : ""}${p.name || p.type_label || "Hazard"}`, url: p.url,
      where: p.severity || "", badge: p.type_label, th: p.theatre || null, ll: pt(f), zoom: 5, cc: gdCc(p) }; }) });
  GTX.stream({ key: "quakes", group: "hazards", label: "Earthquakes", data: () => GTX.S.feeds.quakes, items: (d) => feats(d).map((f) => { const p = f.properties;
    return { id: "eq:" + p.id, ts: isoMs(p.time), title: `M${p.mag != null ? p.mag : "?"} ${p.kind && p.kind !== "earthquake" ? p.kind : "earthquake"}: ${p.place || p.country_name || ""}`,
      url: p.url, where: p.depth_km != null ? p.depth_km + " km deep" : "", label: p.source ? "Quakes · " + p.source : "Quakes",
      badge: p.watch ? "tripwire" : p.suspected ? "suspected" : "", text: p.watch_reason, th: p.theatre || null, ll: pt(f), zoom: 6, cc: p.country || undefined }; }) });

  const hzPopup = (f, lngLat) => {
    const p = f.properties;
    showPopup(lngLat, `<div class="pop"><h5>${esc(p.type_label)}${p.event_name ? ": " + esc(p.event_name) : ""}</h5>
      <div class="meta"><span style="color:${ALERT[p.alert] || ALERT.Green}">●</span> GDACS ${esc(p.alert)} alert · ${esc(p.gdacs_country || p.country_name || "")} · ${p.current ? "ongoing" : "ended"}</div>
      <div>${esc(p.name || "")}</div>
      ${p.severity ? `<div class="post">${esc(p.severity)}</div>` : ""}
      <div>From ${span(p, p.from)}${p.to ? " to " + span(p, p.to) : ""}${p.type === "DR" ? " · drought: the point is a regional centre" : ""}</div>
      ${link(p.url) ? `<div><a href="${esc(link(p.url))}" target="_blank" rel="noopener">GDACS report ↗</a></div>` : ""}
      <div class="muted small">GDACS (UN OCHA and European Commission JRC)${p.origin ? ", data from " + esc(p.origin) : ""}. Alert levels are modelled estimates of humanitarian impact.</div></div>`);
  };
  GTX.popup("hz-pt", hzPopup);
  GTX.popup("hz-green", hzPopup);
  GTX.popup("qk-pt", (f, lngLat) => {
    const p = f.properties, expl = /explosion/.test(p.kind || "");
    showPopup(lngLat, `<div class="pop"><h5>${expl ? esc(p.kind) : "M" + esc(p.mag != null ? p.mag : "?") + " earthquake"}: ${esc(p.place || "")}</h5>
      <div class="meta">${when(p.time)} · ${p.depth_km != null ? esc(p.depth_km) + " km deep" : "depth unknown"}${p.magtype ? " · " + esc(p.magtype) : ""} · ${esc(p.agency || p.source || "")}</div>
      ${p.watch ? `<div class="stale">Tripwire: ${esc(p.watch_reason)}. A shallow quake or an explosion in a watched area can be a test or a strike; it is usually natural.</div>` : ""}
      <div>${link(p.url) ? `<a href="${esc(link(p.url))}" target="_blank" rel="noopener">${esc(p.source || "Source")} event ↗</a>` : ""}${link(p.usgs_url) ? ` · <a href="${esc(link(p.usgs_url))}" target="_blank" rel="noopener">USGS ↗</a>` : ""}</div>
      <div class="muted small">Preliminary parameters. ${p.source === "EMSC" ? "Credit: EMSC-CSEM SeismicPortal (CC BY 4.0)." : "USGS, public domain."}</div></div>`);
  });

  GTX.kpi(() => {
    const h = GTX.S.feeds.hazards, q = GTX.S.feeds.quakes, out = [];
    const big = h ? ((h.by_alert || {}).Red || 0) + ((h.by_alert || {}).Orange || 0) : 0;
    if (big) out.push([nf(big), "Hazard alerts (Orange/Red)", ((h.by_alert || {}).Red || 0) > 0]);
    if (q && q.watch_count) out.push([nf(q.watch_count), "Quakes in watch areas", true]);
    return out;
  });
  // Brief tab, "All sources by theatre" (1.0.0)
  GTX.briefColumn({ label: "Hazards", title: "GDACS Orange and Red alerts now", counts: () => {
    const d = GTX.S.feeds.hazards; if (!d) return null;
    const o = {}; ((d.geojson || {}).features || []).forEach((f) => { const p = f.properties || {}; if (p.theatre && (p.alert === "Orange" || p.alert === "Red")) o[p.theatre] = (o[p.theatre] || 0) + 1; });
    return o; }, note: "Hazards are GDACS Orange and Red alerts." });
  GTX.label("hazards", "GDACS disaster alerts (UN OCHA / EC JRC)");
  GTX.label("quakes", "Earthquakes: EMSC SeismicPortal + USGS (explosion tripwire)");
  GTX.credit(`Disaster alerts: <a href="https://www.gdacs.org" target="_blank" rel="noopener">GDACS</a> (UN and European Commission).
    Earthquakes: <a href="https://www.seismicportal.eu" target="_blank" rel="noopener">EMSC-CSEM SeismicPortal</a> (CC BY 4.0) and USGS (public domain).`);
});
