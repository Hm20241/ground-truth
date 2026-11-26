// Ground Truth page extension: EPA AirNow air-quality monitors (1.7.2, ext 1.0).
// Monitors reading AQI 101 or more (Unhealthy for Sensitive Groups or worse) as map points in EPA's own category
// colours, and an "Air" tab with the summary of every reporting monitor. Feed: /api/feed/airnow (30 min), from
// gt/airnow.py. The feed is optional: where the server does not run it (the public copy), the layer stays empty and
// the tab says so; app.js only requests feeds that /api/status lists, so nothing fails.
// AirNow data are preliminary and are shown as received: the page never changes a value or a category.
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { esc, nf, showPopup } = GTX;
  const empty = { type: "FeatureCollection", features: [] };
  // EPA AQI categories and RGB colours (AQI Technical Assistance Document)
  const CATS = [["Good", "#00e400", "0 to 50"], ["Moderate", "#ffff00", "51 to 100"],
    ["Unhealthy for Sensitive Groups", "#ff7e00", "101 to 150"], ["Unhealthy", "#ff0000", "151 to 200"],
    ["Very Unhealthy", "#8f3f97", "201 to 300"], ["Hazardous", "#7e0023", "301 and up"]];
  const COL = Object.fromEntries(CATS.map(([n, c]) => [n, c]));
  const D = () => GTX.S.feeds.airnow;
  const when = (v, rel) => GTX.when(v, rel);  // the page's zone (Eastern by default) and the time since
  const sw = (c) => `<i style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${c};border:1px solid rgba(255,255,255,.55);vertical-align:-1px;margin-right:6px"></i>`;

  GTX.layer({ key: "airnow", label: "Air quality, AQI 101+ (EPA AirNow)", feed: "airnow", after: "quakes",
    ids: ["aq-pt", "aq-label"], click: ["aq-pt"], clickBefore: "th-pt",
    count: () => { const d = D(); return d ? (d.summary || {}).unhealthy || 0 : null; },
    legend: CATS.slice(2).map(([n, c]) => `<span><i class="lsw dot" style="background:${c}"></i>${n}</span>`).join("") });

  GTX.onMapLoad((map) => {
    map.addSource("airnow", { type: "geojson", data: empty });
    const vis = { visibility: GTX.layerOn("airnow") ? "visible" : "none" };
    const col = ["match", ["get", "category"], "Unhealthy for Sensitive Groups", COL["Unhealthy for Sensitive Groups"],
      "Unhealthy", COL.Unhealthy, "Very Unhealthy", COL["Very Unhealthy"], "Hazardous", COL.Hazardous, "#ff7e00"];
    map.addLayer({ id: "aq-pt", type: "circle", source: "airnow", layout: Object.assign({}, vis), paint: {
      "circle-radius": ["interpolate", ["linear"], ["coalesce", ["get", "aqi"], 101], 101, 5, 200, 7, 300, 9, 500, 11],
      "circle-color": col, "circle-opacity": 0.9, "circle-stroke-width": 1.2, "circle-stroke-color": "#f4f6f8" } }, GTX.below.events);
    map.addLayer({ id: "aq-label", type: "symbol", source: "airnow", minzoom: 4,
      layout: Object.assign({}, vis, { "text-field": ["concat", "AQI ", ["to-string", ["get", "aqi"]]], "text-size": 11,
        "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true, "text-font": ["Open Sans Regular"] }),
      paint: { "text-color": "#f4f6f8", "text-halo-color": "#0b0e11", "text-halo-width": 1.3 } }, GTX.below.events);
  });

  const redraw = () => { if (GTX.isOpen("airnow")) renderTab(document.getElementById("tab-airnow")); };
  GTX.feed("airnow", (d) => { const s = GTX.map.getSource("airnow"); if (s) s.setData(d.geojson || empty); redraw(); });

  const where = (p) => [p.site, p.place].filter(Boolean).join(", ");
  GTX.popup("aq-pt", (f, lngLat) => {
    const p = f.properties;
    showPopup(lngLat, `<div class="pop"><h5>${esc(where(p))}</h5>
      <div style="font-size:14px">${sw(COL[p.category] || "#ff7e00")}AQI <b>${esc(String(p.aqi))}</b>: ${esc(p.category || "")}</div>
      <div>Main pollutant: ${esc(p.pollutant || "not given")}</div>
      <div>Observed ${when(p.ts_ms || p.time)}</div>
      <div class="muted small">${p.agency ? esc(p.agency) + ", through " : ""}U.S. EPA AirNow. Preliminary data, not validated.
        <a href="https://www.airnow.gov" target="_blank" rel="noopener">airnow.gov ↗</a></div></div>`);
  });

  function renderTab(el) {
    if (!el) return;
    const d = D(), box = "font-size:14px;line-height:1.45";
    if (!d || !d.summary) {
      el.innerHTML = `<div style="${box}">No air quality data here yet. This copy of the page may not carry the EPA AirNow feed.</div>`;
      return;
    }
    const s = d.summary, by = s.by_category || {}, top = s.top || [];
    const rows = CATS.map(([n, c, range]) => `<tr><td>${sw(c)}${n}</td><td style="white-space:nowrap">${range}</td>
      <td style="text-align:right;font-family:var(--mono)">${nf(by[n] || 0)}</td></tr>`).join("");
    const worst = top.map((p) => `<tr><td>${sw(COL[p.category] || "#888")}${esc(where(p))}</td>
      <td style="text-align:right;font-family:var(--mono)">${esc(String(p.aqi))}</td><td>${esc(p.pollutant || "")}</td></tr>`).join("");
    const th = "text-align:left;color:var(--muted);font-weight:600;padding:5px 4px;border-bottom:1px solid var(--line)";
    const tbl = "width:100%;border-collapse:collapse;font-size:14px";
    el.innerHTML = `<div class="aqtab" style="${box}">
      <div class="card"><h4 style="font-size:15px">Air quality now (EPA AirNow)</h4>
        <div><b>${nf(s.unhealthy || 0)}</b> of ${nf(s.reporting || 0)} monitors read AQI 101 or more
          (${nf(s.unhealthy_us || 0)} of them in the US). They are the points on the map.</div>
        <div>Observed hour: ${when(s.obs_ts_ms || s.obs_hour)}</div></div>
      <div class="card"><h4 style="font-size:15px">Monitors by AQI category</h4>
        <table style="${tbl}"><tr><th style="${th}">Category</th><th style="${th}">AQI</th><th style="${th};text-align:right">Monitors</th></tr>${rows}</table></div>
      <div class="card"><h4 style="font-size:15px">Highest readings</h4>
        ${worst ? `<table style="${tbl}"><tr><th style="${th}">Monitor</th><th style="${th};text-align:right">AQI</th><th style="${th}">Pollutant</th></tr>${worst}</table>` : "<div>No monitor is reporting.</div>"}</div>
      <div class="muted">Preliminary data, not validated, shown as received. Each monitor counts by its highest pollutant
        (NowCast AQI for PM2.5, ozone and PM10). The list includes Canada, Mexico and US embassy monitors abroad.
        Data belong to the federal, state, local and tribal air agencies and come through
        <a href="https://www.airnow.gov" target="_blank" rel="noopener">U.S. EPA AirNow</a>. For health advice use airnow.gov.</div></div>`;
    el.querySelectorAll(".aqtab td").forEach((td) => { td.style.padding = "5px 4px"; td.style.borderBottom = "1px solid var(--line)"; });
  }
  GTX.tab({ id: "airnow", label: "Air", before: "sources", render: renderTab });
  const btn = document.querySelector('#tabs button[data-tab="airnow"]');
  if (btn) btn.title = "EPA AirNow air quality: monitors by AQI category and the highest readings";

  GTX.label("airnow", "Air quality monitors (U.S. EPA AirNow, preliminary)");
  GTX.credit(`Air quality: <a href="https://www.airnow.gov" target="_blank" rel="noopener">U.S. EPA AirNow</a> and its
    partner air agencies (federal, state, local, tribal). Preliminary data.`);
});
