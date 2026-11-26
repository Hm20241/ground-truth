// Ground Truth page extension: battle fronts (1.6.0, ext 1.0).
// The source map's own legend says "Red Lines represent frontlines, Yellow represents supposed front lines". This
// layer draws exactly those lines (gt/mymaps.py front_kind: contact / blockade / defense / supposed), gives each
// a marker, and counts the event pins near it. No line is invented here: a front exists only while the map's
// curator keeps drawing it. DeepState's occupied-territory outline stays its own layer.
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { S, esc, nf, ago, map } = GTX;
  const RED = "#ff4d4d", YEL = "#ffd600", NEAR_KM = 75;
  // kind -> [label, colour, glyph, what the line means]
  const KIND = {
    contact: ["Front line", RED, "swords", "Line of contact between the two sides, as the source map draws it."],
    supposed: ["Supposed front line", YEL, "swords", "A front line the source map marks as unconfirmed (yellow in its legend)."],
    blockade: ["Blockade line", RED, "anchor", "A naval blockade line on the source map."],
    defense: ["Defence line", RED, "shield", "A defensive line or perimeter on the source map."],
  };
  // The same rule as gt/mymaps.py front_kind, for data from a server older than 1.6.0.
  const kindOf = (p, n) => {
    if (p.front_kind) return p.front_kind;
    const col = String(p.stroke || "").toUpperCase(), t = String(p.title || "").toLowerCase();
    if ((col !== "#A52714" && col !== "#FFD600") || ["damage", "bridge", "river", "border", "lane", "airbase"].includes(p.overlay_type)) return null;
    if (col === "#FFD600") return "supposed";
    if (/blockade/.test(t)) return "blockade";
    if (/defen[cs]e (chain|line)|perimeter/.test(t)) return "defense";
    return /front/.test(t) || n >= 3 ? "contact" : null;
  };
  const RAD = Math.PI / 180;
  // km from a point to a segment, on a local flat sheet (fine at these distances)
  function segKm(p, a, b) {
    const k = Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32;
    const ax = (a[0] - p[0]) * k, ay = (a[1] - p[1]) * 110.57, bx = (b[0] - p[0]) * k, by = (b[1] - p[1]) * 110.57;
    const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L)) : 0;
    return Math.hypot(ax + t * dx, ay + t * dy);
  }
  const lineKm = (pt, cs) => { let d = Infinity; for (let i = 1; i < cs.length; i++) d = Math.min(d, segKm(pt, cs[i - 1], cs[i])); return d; };
  const ptKm = (a, b) => Math.hypot((b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32, (b[1] - a[1]) * 110.57);
  const lenKm = (cs) => { let n = 0; for (let i = 1; i < cs.length; i++) n += ptKm(cs[i - 1], cs[i]); return n; };
  function midPoint(cs) {  // the point half-way along the line, so the marker sits on it
    const seg = []; let total = 0;
    for (let i = 1; i < cs.length; i++) { const d = ptKm(cs[i - 1], cs[i]); seg.push(d); total += d; }
    let run = total / 2;
    for (let i = 0; i < seg.length; i++) {
      if (run <= seg[i] || i === seg.length - 1) { const t = seg[i] ? Math.min(1, run / seg[i]) : 0; return [cs[i][0] + (cs[i + 1][0] - cs[i][0]) * t, cs[i][1] + (cs[i + 1][1] - cs[i][1]) * t]; }
      run -= seg[i];
    }
    return cs[0];
  }
  let FRONTS = [];
  function build() {
    const feats = (S.events || {}).features || [], now = Date.now();
    const pins = feats.filter((f) => f.properties.kind === "event" && f.geometry && f.geometry.type === "Point" && f.properties.ts_ms);
    FRONTS = feats.filter((f) => f.properties.kind === "overlay" && f.geometry.type === "LineString").map((f) => {
      const p = f.properties, cs = f.geometry.coordinates, kind = kindOf(p, cs.length);
      if (!kind || !KIND[kind]) return null;
      const near = pins.filter((e) => lineKm(e.geometry.coordinates, cs) <= NEAR_KM).sort((a, b) => b.properties.ts_ms - a.properties.ts_ms);
      const xs = cs.map((c) => c[0]), ys = cs.map((c) => c[1]);
      return { id: p.id, kind, name: p.title || KIND[kind][0], theatre: p.theatre, where: p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name,
        cs, mid: midPoint(cs), km: lenKm(cs), bbox: [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]],
        n24: near.filter((e) => now - e.properties.ts_ms < 24 * 3600e3).length, n72: near.filter((e) => now - e.properties.ts_ms < 72 * 3600e3).length,
        last: near[0] ? near[0].properties : null };
    }).filter(Boolean).sort((a, b) => b.n72 - a.n72 || b.km - a.km);
  }
  const shown = () => FRONTS.filter((f) => S.theatre === "global" || f.theatre === S.theatre);

  GTX.layer({ key: "fronts", label: "Battle fronts (source map lines)", feed: "mymaps", on: true, after: "overlays",
    ids: ["fr-case", "fr-line", "fr-dash", "fr-dot", "fr-ico"], click: ["fr-ico", "fr-line", "fr-dash", "fr-dot"], clickBefore: "ov-line",
    count: () => shown().length, legend: `<div id="frlist" class="frlist"></div>` });

  GTX.onMapLoad((m) => {
    Object.entries(KIND).forEach(([k, [, col, glyph]]) => GTX.mapImage("fr-" + k, GTX.drawGlyph(glyph, 72, "#0d0f11", { fill: col, ring: "#0d0f11" })));
    m.addSource("fronts", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    const vis = { visibility: GTX.layerOn("fronts") ? "visible" : "none" }, below = GTX.below.events;
    const isLine = ["==", ["geometry-type"], "LineString"], of = (...k) => ["all", isLine, ["in", ["get", "kind"], ["literal", k]]];
    const w = ["interpolate", ["linear"], ["zoom"], 2, 2.2, 6, 3.4, 9, 4.6];
    m.addLayer({ id: "fr-case", type: "line", source: "fronts", filter: isLine, layout: { ...vis, "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#0d0f11", "line-opacity": 0.85, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 4.4, 6, 6.4, 9, 8] } }, below);
    m.addLayer({ id: "fr-line", type: "line", source: "fronts", filter: of("contact"), layout: { ...vis, "line-cap": "round", "line-join": "round" },
      paint: { "line-color": ["get", "col"], "line-width": w } }, below);
    m.addLayer({ id: "fr-dash", type: "line", source: "fronts", filter: of("blockade", "supposed"), layout: vis,
      paint: { "line-color": ["get", "col"], "line-width": w, "line-dasharray": [2.4, 1.6] } }, below);
    m.addLayer({ id: "fr-dot", type: "line", source: "fronts", filter: of("defense"), layout: vis,
      paint: { "line-color": ["get", "col"], "line-width": w, "line-dasharray": [0.6, 1.4] } }, below);
    m.addLayer({ id: "fr-ico", type: "symbol", source: "fronts", filter: ["==", ["geometry-type"], "Point"], layout: { ...vis,
      "icon-image": ["concat", "fr-", ["get", "kind"]], "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.5, 6, 0.72, 9, 0.9],
      "icon-allow-overlap": true, "icon-ignore-placement": true, "text-field": ["step", ["zoom"], "", 3.2, ["get", "name"]], "text-size": 11.5,
      "text-font": ["Open Sans Regular"], "text-offset": [0, 1.35], "text-anchor": "top", "text-optional": true, "text-max-width": 10 },
      paint: { "text-color": "#ffd9d9", "text-halo-color": "#0d0f11", "text-halo-width": 1.6 } }, below);
  });

  const rowHtml = (f) => {
    const [label, col, glyph] = KIND[f.kind];
    return `<button type="button" class="frrow" data-fr="${esc(f.id)}" title="${esc(label)} · ${esc(f.where || "")} · ${nf(Math.round(f.km))} km long. Pins within ${NEAR_KM} km in the last 72 h. Click to go there.">
      <img class="glico" src="${GTX.drawGlyph(glyph, 40, "#0d0f11", { fill: col }).toDataURL()}" alt=""><span class="nm">${esc(f.name)}</span><span class="ct${f.n24 ? " hot" : ""}">${nf(f.n72)}</span></button>`;
  };
  function popup(f, lngLat) {
    const [label, col, , what] = KIND[f.kind], l = f.last;
    GTX.showPopup(lngLat || f.mid, `<div class="pop"><h5>${esc(f.name)}</h5>
      <div class="meta"><span style="color:${col}">▬</span> ${esc(label)} · ${esc(f.where || "")} · about ${nf(Math.round(f.km))} km</div>
      <div>${esc(what)}</div>
      <div class="post"><b>${nf(f.n24)}</b> event pin${f.n24 === 1 ? "" : "s"} within ${NEAR_KM} km in the last 24 h, <b>${nf(f.n72)}</b> in 72 h.${l ? ` Newest: “${esc(l.title)}” (${esc(ago(l.ts_ms))}).` : " None dated near it."}</div>
      <div class="muted small">Drawn by the source map's curator; it moves only when they redraw it. Not a live trace of the front.</div></div>`);
  }
  GTX.popup("fr-ico", (ft, ll) => { const f = FRONTS.find((x) => x.id === ft.properties.id); if (f) popup(f, ll); });
  ["fr-line", "fr-dash", "fr-dot"].forEach((id) => GTX.popup(id, (ft, ll) => { const f = FRONTS.find((x) => x.id === ft.properties.id); if (f) popup(f, ll); }));

  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest(".frrow"); if (!b) return;
    const f = FRONTS.find((x) => x.id === b.dataset.fr); if (!f) return;
    map.fitBounds(f.bbox, { padding: 90, maxZoom: 7.5, duration: 900 });
    map.once("moveend", () => popup(f));
  });

  GTX.onRender(() => {
    build();
    const list = shown(), src = map.getSource("fronts");
    if (src) src.setData({ type: "FeatureCollection", features: list.flatMap((f) => [
      { type: "Feature", geometry: { type: "LineString", coordinates: f.cs }, properties: { id: f.id, kind: f.kind, col: KIND[f.kind][1] } },
      { type: "Feature", geometry: { type: "Point", coordinates: f.mid }, properties: { id: f.id, kind: f.kind, name: f.name } }]) });
    const el = document.getElementById("frlist");
    if (el) el.innerHTML = list.length ? list.map(rowHtml).join("") : `<span class="muted">No front line on the source map${S.theatre === "global" ? "" : " in this theatre"}.</span>`;
  });
  GTX.fronts = () => FRONTS;  // read by the tests
});
