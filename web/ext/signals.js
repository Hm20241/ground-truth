// Ground Truth page extension: strategic signals (0.13.0, ext 1.0; ext 1.1, 1.2.0: Feed-tab streams; ext 1.2, 1.3.0: times
// in the page's zone with the time since; ext 1.3, 1.4.0: Feed items carry cc (country) for the title bar).
// Tsunami and volcano bulletins (PTWC, NTWC, JMA), Germany's gamma network (BfS) as a nuclear tripwire, US
// sanctions actions (OFAC) and the US terrorism advisory (DHS NTAS). Map points for bulletins and flagged
// radiation stations; everything in a Signals tab. Feeds: /api/feed/{tsunami,radiation,ofac,ntas} (gt/signals.py).
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { esc, fmtT, fmtD, isoMs, nf, showPopup } = GTX;
  const empty = { type: "FeatureCollection", features: [] };
  const TSU = { warning: "#f05252", advisory: "#f2853d", watch: "#f2b33d", information: "#60a5fa" };
  const RAD = "#e879f9";
  const when = (v, rel) => GTX.when(v, rel);  // 1.3.0: the page's zone (Eastern or UTC) and the time since
  const F = () => GTX.S.feeds;

  GTX.layer({ key: "signals", label: "Tsunami bulletins, radiation flags", feed: "tsunami", after: "quakes",
    ids: ["sg-tsu", "sg-rad"], click: ["sg-tsu", "sg-rad"], clickBefore: "th-pt",
    count: () => ((F().tsunami || {}).geojson ? F().tsunami.geojson.features.length : 0) + ((F().radiation || {}).count || 0),
    legend: Object.entries(TSU).map(([k, c]) => `<span><i class="lsw dot" style="background:${c}"></i>${k}</span>`).join("") +
      `<span><i class="lsw ring" style="border-color:${RAD}"></i>radiation above baseline</span>` });

  GTX.onMapLoad((map) => {
    map.addSource("tsunami", { type: "geojson", data: empty });
    map.addSource("radflag", { type: "geojson", data: empty });
    const vis = { visibility: GTX.layerOn("signals") ? "visible" : "none" };
    map.addLayer({ id: "sg-tsu", type: "circle", source: "tsunami", layout: vis, paint: {
      "circle-radius": ["match", ["get", "level"], "information", 6, 9],
      "circle-color": ["match", ["get", "level"], "warning", TSU.warning, "advisory", TSU.advisory, "watch", TSU.watch, TSU.information],
      "circle-opacity": 0.8, "circle-stroke-width": 1.5, "circle-stroke-color": "#0b0e11" } }, GTX.below.events);
    map.addLayer({ id: "sg-rad", type: "circle", source: "radflag", layout: vis, paint: {
      "circle-radius": 8, "circle-color": "rgba(0,0,0,0)", "circle-stroke-width": 2.5, "circle-stroke-color": RAD } }, GTX.below.events);
  });

  const redraw = () => { if (GTX.isOpen("signals")) renderTab(document.getElementById("tab-signals")); };
  GTX.feed("tsunami", (d) => { const s = GTX.map.getSource("tsunami"); if (s) s.setData(d.geojson || empty); redraw(); });
  GTX.feed("radiation", (d) => { const s = GTX.map.getSource("radflag"); if (s) s.setData(d.geojson || empty); redraw(); });
  GTX.feed("ofac", redraw);
  GTX.feed("ntas", redraw);
  // 1.2.0 (ext 1.1): bulletins, radiation flags, NTAS advisories and OFAC actions also run in the main Feed tab.
  const pt = (f) => (f.geometry && f.geometry.type === "Point" ? f.geometry.coordinates : null);
  // 1.4.0 (ext 1.3): cc for the Feed row's title bar: the server's country for a bulletin's or a flagged station's point,
  // the US for NTAS. OFAC has none: its countries are read off programme names in the title, and a programme is not a place.
  GTX.stream({ key: "tsunami", group: "hazards", label: "Tsunami / volcano", data: () => F().tsunami, items: (d) => (d.items || []).map((i) => ({
    id: "ts:" + i.id, ts: isoMs(i.issued), url: i.url, label: i.source || "Bulletin", badge: i.level,
    title: `${i.cancelled && !/cancel/i.test(i.label || "") ? "Cancelled: " : ""}${i.label || i.title || "Bulletin"}${i.volcano || i.region ? ": " + (i.volcano || i.region) : ""}`,
    where: i.country_name || i.sea || "", th: i.theatre || (i.source === "JMA" ? "indo-pacific" : null),
    ll: i.lon != null && i.lat != null ? [i.lon, i.lat] : null, zoom: 5, cc: i.country || i.country_name || undefined })) });
  GTX.stream({ key: "radiation", group: "hazards", label: "BfS gamma", data: () => F().radiation, items: (d) => ((d.geojson || {}).features || []).map((f) => { const p = f.properties || {};
    return { id: "rad:" + p.id + p.measured, ts: isoMs(p.measured), title: `Gamma dose above baseline: ${p.name} (${p.ratio}×, ${p.value_usv} µSv/h)`,
      th: "europe-nato", ll: pt(f), zoom: 7, cc: p.country || undefined }; }) });
  GTX.stream({ key: "ntas", group: "alerts", label: "DHS NTAS", data: () => F().ntas, items: (d) => (d.items || []).map((a) => ({
    id: "ntas:" + (a.start || a.start_et), ts: isoMs(a.start), title: `NTAS ${a.type || a.kind || "bulletin"}${a.end_et ? " (to " + a.end_et + ")" : ""}`, url: a.url,
    text: a.summary, th: "americas", cc: "USA" })) });
  GTX.stream({ key: "ofac", group: "official", label: "OFAC", data: () => F().ofac, items: (d) => (d.items || []).map((i) => ({
    id: "ofac:" + i.url, ts: GTX.dayMs(i.date), day: true, title: i.title, url: i.url, badge: (i.programs || []).slice(0, 2).join(", "),
    text: (i.programs || []).join(" "), th: i.theatres || [] })) });

  GTX.popup("sg-tsu", (f, lngLat) => {
    const p = f.properties;
    showPopup(lngLat, `<div class="pop"><h5>${esc(p.label || p.title || "Bulletin")}</h5>
      <div class="meta"><span style="color:${TSU[p.level] || TSU.information}">●</span> ${esc(p.source)} · ${esc(p.level)} · ${when(p.issued)}</div>
      <div>${p.magnitude != null ? "M" + p.magnitude + " · " : ""}${esc(p.region || "")}</div>
      ${p.url ? `<div><a href="${esc(p.url)}" target="_blank" rel="noopener">Bulletin ↗</a></div>` : ""}
      <div class="muted small">${p.source === "JMA" ? "Source: Japan Meteorological Agency website (jma.go.jp); label and level are Ground Truth's reading of the Japanese text." : "NOAA tsunami warning centres, public domain."}</div></div>`);
  });
  GTX.popup("sg-rad", (f, lngLat) => {
    const p = f.properties;
    showPopup(lngLat, `<div class="pop"><h5>Gamma dose rate above baseline: ${esc(p.name)}</h5>
      <div class="meta">BfS station ${esc(p.id)} · measured ${when(p.measured)}</div>
      <div><b>${p.value_usv} µSv/h</b>, ${p.ratio}× the ${p.baseline_kind === "station" ? "station's own" : "network"} baseline of ${p.baseline_usv} µSv/h.</div>
      <div class="muted small">Rain washes radon progeny down and often doubles readings for an hour or two; a real release shows at many stations at once. Data: Bundesamt für Strahlenschutz (dl-de/by-2-0).</div></div>`);
  });

  function renderTab(el) {
    if (!el) return;
    const t = F().tsunami, r = F().radiation, o = F().ofac, n = F().ntas;
    const rs = (r || {}).summary || {};
    const sec = (title, body) => `<div class="card"><h4>${title}</h4>${body}</div>`;
    el.innerHTML =
      sec("US terrorism advisory (DHS NTAS)", !n ? `<div class="muted small">No data yet.</div>` : n.active
        ? n.items.map((a) => `<div class="stale">${esc(a.kind || a.type || "Bulletin")} · ${esc(a.start_et || "")} to ${esc(a.end_et || "open")}</div><div class="post">${esc(a.summary || "")}</div>${a.url ? `<a href="${esc(a.url)}" target="_blank" rel="noopener">DHS ↗</a>` : ""}`).join("")
        : `<div class="muted small">No active NTAS advisory (${nf(n.in_feed || 0)} in the feed).</div>`) +
      sec("Tsunami and volcano bulletins, 72 h", !t ? `<div class="muted small">No data yet.</div>` : (t.items || []).length
        ? `<ul class="feed">${t.items.map((i) => `<li style="--c:${TSU[i.level] || TSU.information}"><div><b>${esc(i.label || i.title || "")}</b></div><div class="muted small">${esc(i.source)} · ${esc(i.level)} · ${when(i.issued)}${i.region ? " · " + esc(i.region) : ""}${i.url ? ` · <a href="${esc(i.url)}" target="_blank" rel="noopener">bulletin ↗</a>` : ""}</div></li>`).join("")}</ul>`
        : `<div class="muted small">No bulletins in the last 72 hours.</div>`) +
      sec("Radiation (German gamma network, BfS)", !r ? `<div class="muted small">No data yet.</div>` :
        `<div>${nf(rs.reporting || 0)} of ${nf(rs.stations || 0)} stations reporting · network median ${rs.network_median_usv != null ? rs.network_median_usv + " µSv/h" : "–"}${rs.network_change_pct != null ? ` (${rs.network_change_pct > 0 ? "+" : ""}${rs.network_change_pct}% vs baseline)` : ""} · measured to ${when(rs.measured_until)}</div>` +
        (rs.network_flag ? `<div class="stale">The whole network is up on its baseline: check the news and the wind.</div>` : "") +
        ((r.geojson || empty).features.length ? `<ul class="feed">${r.geojson.features.map((f) => `<li style="--c:${RAD}"><b>${esc(f.properties.name)}</b> <span class="muted small">${f.properties.value_usv} µSv/h · ${f.properties.ratio}× baseline · ${when(f.properties.measured)}</span></li>`).join("")}</ul>`
          : `<div class="muted small">No station above ${(rs.thresholds || {}).ratio || 2}× its baseline.</div>`)) +
      sec("US sanctions actions (OFAC)", !o ? `<div class="muted small">No data yet.</div>` :
        `<ul class="feed">${(o.items || []).slice(0, 15).map((i) => `<li><div><a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a></div><div class="muted small">${esc(i.date)} · ${(i.programs || []).map((p) => `<span class="badge">${esc(p)}</span>`).join(" ")}</div></li>`).join("")}</ul>`) +
      `<div class="muted small">NOAA, DHS and OFAC: US government, public domain. JMA: Japan Meteorological Agency website (edited). BfS: dl-de/by-2-0.</div>`;
  }
  GTX.tab({ id: "signals", label: "Signals", before: "sources", render: renderTab });

  GTX.kpi(() => {
    const t = F().tsunami, r = F().radiation, n = F().ntas, out = [];
    if (t && t.alert) out.push([esc(t.max_level), "Tsunami bulletin", true]);
    if (r && r.alert) out.push([nf(r.count || 0) + (((r.summary || {}).network_flag) ? " + network" : ""), "Radiation flags", true]);
    if (n && n.active) out.push([esc(n.level || "active"), "NTAS advisory", true]);
    return out;
  });
  GTX.label("tsunami", "Tsunami + volcano bulletins (PTWC, NTWC, JMA)");
  GTX.label("radiation", "BfS gamma dose network (Germany)");
  GTX.label("ofac", "OFAC recent sanctions actions");
  GTX.label("ntas", "DHS NTAS terrorism advisories");
  GTX.credit(`Tsunami bulletins: NOAA PTWC/NTWC and the Japan Meteorological Agency website (edited).
    Radiation: Bundesamt für Strahlenschutz (dl-de/by-2-0). Sanctions: US Treasury OFAC. Terrorism advisories: DHS NTAS.`);
});
