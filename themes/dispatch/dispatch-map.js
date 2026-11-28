/* Ground Truth 1.7.0, theme "Dispatch": the map figure.
   One MapLibre map inside one <figure>; the figure is moved between the front page, the map page and the wall view.
   Five topic switches stand in for the Classic theme's layer checkboxes. Glyph drawings and the fronts rule are the
   Classic theme's (web/app.js GLYPHS, web/ext/fronts.js build()): every event pin with a time, from the source map or
   one of the three other pin sources, within 75 km of the line, in the last 24 and 72 hours. */
(() => {
  "use strict";
  const G = window.GT2, { S, $, esc, nf } = G;
  const INK = "#15171a", PAPER = "#ffffff", RED = "#b3261e", AMBER = "#b36b00", SEA = "#1f5f8b", SLATE = "#37474f", GREY = "#6b7078";

  // ---------- glyphs (from web/app.js) ----------
  const GLYPHS = {
    megaphone: { fill: "M3 9.5H7.5L17 4.5V19.5L7.5 14.5H3Z M7.2 15.6L9.6 21H12.4L10.3 16.3Z", stroke: [["M19.6 9.2Q21.4 12 19.6 14.8", 1.6]] },
    fire: { fill: "M12.6 2C13.4 6.2 18 8.4 18 14A6 6 0 0 1 6 14C6 11 7.6 9.4 8.8 7.6C9.3 9.6 10.2 10.6 11.2 10.8C11 7.6 11.2 4.4 12.6 2Z M12 13.2C13 15 14.4 15.6 14.4 17.4A2.4 2.4 0 0 1 9.6 17.4C9.6 15.8 11 15 12 13.2Z" },
    plane: { fill: "M12 1.8C12.9 1.8 13.3 3 13.3 4.6V9L21.5 14.2V16.2L13.3 13.7V18.4L15.8 20.3V21.9L12 20.8L8.2 21.9V20.3L10.7 18.4V13.7L2.5 16.2V14.2L10.7 9V4.6C10.7 3 11.1 1.8 12 1.8Z" },
    officer: { fill: "M7.2 5.9L8.6 2.6H15.4L16.8 5.9Z M12 6.6A3.3 3.3 0 1 1 11.99 6.6Z M4.6 21.4C4.6 16.4 7.6 14 12 14C16.4 14 19.4 16.4 19.4 21.4Z" },
    truck: { fill: "M1.8 6.5H14V16.5H1.8Z M15.2 9.5H19.2L22.2 12.8V16.5H15.2Z M6 15.2A2.5 2.5 0 1 1 5.99 15.2Z M18.2 15.2A2.5 2.5 0 1 1 18.19 15.2Z" },
    gunner: { fill: "M16.4 4A2.7 2.7 0 1 1 16.39 4Z M12.4 10.4H19.6L20.2 21.4H13Z M1.8 8.6H13.4V10.6L1.8 9.9Z M9.4 10.4H11.4V13.2H9.4Z" },
    ship: { fill: "M2.6 13.4H21.4L18.6 18.6H5.4Z M6.2 8.8H17.8V12.4H6.2Z M10.4 4.6H13.6V7.8H10.4Z", stroke: [["M2.6 21.4Q4.2 19.8 5.8 21.4T9 21.4T12.2 21.4T15.4 21.4T18.6 21.4T21.8 21.4", 1.5]] },
    wreck: { fill: "M3.4 13.6L19.6 6.4L18.4 13.2L8.4 17.8Z M9.8 9.6L7 3.4L8.9 2.7L12.2 8.6Z", stroke: [["M2.6 21.4Q4.2 19.8 5.8 21.4T9 21.4T12.2 21.4T15.4 21.4T18.6 21.4T21.8 21.4", 1.5], ["M14.2 15.4L17.8 19", 1.5], ["M17.8 15.4L14.2 19", 1.5]] },
    skull: { fill: "M12 2.4C7.4 2.4 4.8 5.4 4.8 9.2C4.8 11.6 6 13.3 7.8 14.2V16.6H16.2V14.2C18 13.3 19.2 11.6 19.2 9.2C19.2 5.4 16.6 2.4 12 2.4Z M9.2 7.4A1.9 1.9 0 1 0 9.21 7.4Z M14.8 7.4A1.9 1.9 0 1 0 14.81 7.4Z M12 11.2L10.9 13.4H13.1Z", stroke: [["M4.6 18.2L19.4 22", 2], ["M19.4 18.2L4.6 22", 2]] },
    bridge: { fill: "M1.8 13H22.2V15.6H1.8Z M6 4.4H8.2V20.6H6Z M15.8 4.4H18V20.6H15.8Z", stroke: [["M1.8 12L7.1 5", 1.3], ["M7.1 5Q12 13.4 16.9 5", 1.3], ["M16.9 5L22.2 12", 1.3]] },
    helicopter: { fill: "M4.6 12.4C4.6 9.6 7.4 8.4 10.6 8.4C14.6 8.4 16.8 10.4 16.8 13C16.8 15.2 14.8 16.2 12 16.2H8.2C6 16.2 4.6 14.6 4.6 12.4Z M16 10.8L22.2 9.2V11.4L16.6 13.6Z M10 5.6H11.8V8.6H10Z", stroke: [["M2.6 5.4H19.2", 1.7], ["M5.6 19.6H16", 1.5], ["M7.8 16.2V19.6", 1.3], ["M13 16.2V19.6", 1.3]] },
    train: { fill: "M6.4 2.6H17.6A2.4 2.4 0 0 1 20 5V15.4A2.4 2.4 0 0 1 17.6 17.8H6.4A2.4 2.4 0 0 1 4 15.4V5A2.4 2.4 0 0 1 6.4 2.6Z M6.4 5.4H11.2V10.4H6.4Z M12.8 5.4H17.6V10.4H12.8Z M8 12.8A1.4 1.4 0 1 0 8.01 12.8Z M16 12.8A1.4 1.4 0 1 0 16.01 12.8Z", stroke: [["M7.6 18.4L5.4 22", 1.6], ["M16.4 18.4L18.6 22", 1.6]] },
    bolt: { fill: "M13.8 1.8L5.6 13.2H11L9.4 22.2L18.4 10.2H12.8Z" },
    swords: { stroke: [["M4 3.6L17.2 16.8", 2.2], ["M20 3.6L6.8 16.8", 2.2], ["M14.4 19.2L19.6 14", 2], ["M9.6 19.2L4.4 14", 2], ["M17.6 17.2L20.6 20.4", 2.4], ["M6.4 17.2L3.4 20.4", 2.4]] },
    anchor: { stroke: [["M12 3.2A1.9 1.9 0 1 1 11.99 3.2Z", 1.7], ["M12 7V20.6", 2.2], ["M8 10.4H16", 2], ["M4.2 13.6C4.8 18.4 8.4 20.6 12 20.6C15.6 20.6 19.2 18.4 19.8 13.6", 2]] },
    shield: { fill: "M12 2.2L20.2 5.2V11C20.2 16.2 16.6 20 12 21.8C7.4 20 3.8 16.2 3.8 11V5.2Z M12 5.4L6.6 7.4V11C6.6 14.6 8.8 17.2 12 18.6Z" },
  };
  const ICON_GLYPH = { 1830: "megaphone", 1571: "fire", 1504: "plane", 1657: "officer", 1722: "truck", 1812: "gunner", 1569: "ship",
    1864: "wreck", 1556: "skull", 1528: "bridge", 1593: "helicopter", 1716: "train", 1660: "bolt" };
  const CAT_GLYPH = { strike: "fire", energy: "bolt", maritime: "ship", casualty: "skull", aviation: "plane", drone: "plane", forces: "officer" };
  const glyphOf = (p) => ICON_GLYPH[p.icon] || (GLYPHS[p.glyph] ? p.glyph : "") || CAT_GLYPH[p.category] || "dot";
  function drawGlyph(name, px, ink, disc, scale) {
    const c = document.createElement("canvas"), sh = GLYPHS[name]; c.width = c.height = px;
    const g = c.getContext("2d");
    if (disc) {
      g.beginPath(); g.arc(px / 2, px / 2, px / 2 - (disc.ring ? 2.5 : 0.5), 0, Math.PI * 2); g.fillStyle = disc.fill; g.fill();
      if (disc.ring) { g.lineWidth = Math.max(2.5, px / 16); g.strokeStyle = disc.ring; g.stroke(); }
    }
    if (!sh) return c;
    const k = (px / 24) * (scale || (disc ? 0.58 : 1));
    g.translate(px / 2 - 12 * k, px / 2 - 12 * k); g.scale(k, k); g.lineCap = g.lineJoin = "round";
    g.fillStyle = g.strokeStyle = ink;
    if (sh.fill) g.fill(new Path2D(sh.fill), "evenodd");
    (sh.stroke || []).forEach(([d, w]) => { g.lineWidth = w; g.stroke(new Path2D(d)); });
    return c;
  }
  const glyphUrl = (name, col) => drawGlyph(name, 40, "#fff", { fill: col }).toDataURL();

  // ---------- map ----------
  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/";
  const map = new maplibregl.Map({
    container: "map", attributionControl: { compact: true }, center: [24, 34], zoom: 1.6, maxPitch: 0, dragRotate: false, renderWorldCopies: true,
    style: {
      version: 8,
      glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
      sources: {
        // the light member of the Esri canvas family the Classic theme uses (it uses World_Dark_Gray_*)
        base: { type: "raster", tileSize: 256, maxzoom: 16, attribution: "Basemap © Esri", tiles: [ESRI + "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"] },
        ref: { type: "raster", tileSize: 256, maxzoom: 16, tiles: [ESRI + "World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"] },
      },
      layers: [
        { id: "bg", type: "background", paint: { "background-color": "#e9e7e1" } },
        { id: "base", type: "raster", source: "base", paint: { "raster-saturation": -0.3, "raster-contrast": 0.08 } },
      ],
    },
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  const empty = { type: "FeatureCollection", features: [] };
  const fc = (features) => ({ type: "FeatureCollection", features });
  const pt = (ll, properties) => ({ type: "Feature", geometry: { type: "Point", coordinates: ll }, properties });
  const mapImage = (id, c) => map.hasImage(id) || map.addImage(id, { width: c.width, height: c.height, data: c.getContext("2d").getImageData(0, 0, c.width, c.height).data }, { pixelRatio: 2 });
  const FAMCOL = Object.fromEntries(Object.entries(G.FAMILY).map(([k, v]) => [k, v[1]]));
  map.on("styleimagemissing", (e) => {
    const m = /^pin-([a-z]+)-([a-z]+)$/.exec(e.id);
    if (m) mapImage(e.id, drawGlyph(m[1], 64, "#fff", { fill: FAMCOL[m[2]] || GREY, ring: "#fff" }));
  });

  // ---------- topics ----------
  const TOPICS = {
    conflict: { label: "Conflict", layers: ["ds-fill", "ar-fill", "ar-line", "fr-case", "fr-line", "fr-dash", "fr-dot", "fr-ico", "ev-recent", "ev-pin"], cats: null, fronts: null },
    air: { label: "Air", layers: ["jam-fill", "ev-recent", "ev-pin", "mil-ico"], cats: ["aviation", "missile", "drone"], feeds: ["mil", "gpsjam"] },
    sea: { label: "Sea", layers: ["ship-dot", "fr-case", "fr-dash", "fr-ico", "cp-dot", "cp-txt", "uk-ico", "ev-recent", "ev-pin"], cats: ["maritime"], fronts: ["blockade"], feeds: ["ukmto", "portwatch", "ships"] },
    outages: { label: "Outages", layers: ["ev-recent", "ev-pin"], cats: ["energy", "cyber"] },
    hazards: { label: "Hazards", layers: ["hz-dot", "qk-dot"], cats: [], feeds: ["quakes", "hazards"] },
  };
  const ALL_LAYERS = ["ds-fill", "ar-fill", "ar-line", "jam-fill", "ship-dot", "fr-case", "fr-line", "fr-dash", "fr-dot", "hz-dot", "qk-dot", "cp-dot", "cp-txt", "uk-ico", "ev-recent", "ev-pin", "mil-ico", "fr-ico"];
  let topic = TOPICS[G.store.get("topic")] ? G.store.get("topic") : "conflict", ready = false, regions = null, h3wait = null;

  // ---------- fronts (rule from web/ext/fronts.js) ----------
  const KIND = {
    contact: ["Front line", RED, "swords", "Line of contact between the two sides, as the source map draws it."],
    supposed: ["Supposed front line", AMBER, "swords", "A front line the source map marks as unconfirmed."],
    blockade: ["Blockade line", RED, "anchor", "A naval blockade line on the source map."],
    defense: ["Defence line", RED, "shield", "A defensive line or perimeter on the source map."],
  };
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
  function segKm(p, a, b) {
    const k = Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32;
    const ax = (a[0] - p[0]) * k, ay = (a[1] - p[1]) * 110.57, bx = (b[0] - p[0]) * k, by = (b[1] - p[1]) * 110.57;
    const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L)) : 0;
    return Math.hypot(ax + t * dx, ay + t * dy);
  }
  const lineKm = (p, cs) => { let d = Infinity; for (let i = 1; i < cs.length; i++) d = Math.min(d, segKm(p, cs[i - 1], cs[i])); return d; };
  const ptKm = (a, b) => Math.hypot((b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32, (b[1] - a[1]) * 110.57);
  const lenKm = (cs) => { let n = 0; for (let i = 1; i < cs.length; i++) n += ptKm(cs[i - 1], cs[i]); return n; };
  function midPoint(cs) {
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
  function buildFronts() {
    const feats = (S.events || {}).features || [], now = Date.now();
    const pins = feats.filter((f) => f.properties.kind === "event" && f.geometry && f.geometry.type === "Point" && f.properties.ts_ms);
    FRONTS = feats.filter((f) => f.properties.kind === "overlay" && f.geometry && f.geometry.type === "LineString").map((f) => {
      const p = f.properties, cs = f.geometry.coordinates, kind = kindOf(p, cs.length);
      if (!kind || !KIND[kind]) return null;
      const near = pins.filter((e) => lineKm(e.geometry.coordinates, cs) <= 75).sort((a, b) => b.properties.ts_ms - a.properties.ts_ms);
      return { id: p.id, kind, name: p.title || KIND[kind][0], theatre: p.theatre, where: p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name,
        cs, mid: midPoint(cs), km: lenKm(cs), n24: near.filter((e) => now - e.properties.ts_ms < 864e5).length, n72: near.filter((e) => now - e.properties.ts_ms < 2592e5).length,
        last: near[0] ? near[0].properties : null };
    }).filter(Boolean).sort((a, b) => b.n72 - a.n72 || b.km - a.km);
  }
  G.fronts = () => { buildFronts(); return FRONTS; }; G.frontKind = KIND; G.glyphUrl = glyphUrl;

  // ---------- layers ----------
  map.on("load", () => {
    Object.entries(KIND).forEach(([k, [, col, glyph]]) => mapImage("fr-" + k, drawGlyph(glyph, 72, "#fff", { fill: col, ring: "#fff" })));
    mapImage("uk-hot", drawGlyph("anchor", 64, "#fff", { fill: RED, ring: "#fff" }));
    mapImage("uk-cool", drawGlyph("anchor", 64, "#fff", { fill: SEA, ring: "#fff" }));
    mapImage("ac-plane", drawGlyph("plane", 64, "#fff", { fill: SLATE, ring: "#fff" }, 0.64));
    mapImage("ac-heli", drawGlyph("helicopter", 64, "#fff", { fill: SLATE, ring: "#fff" }, 0.6));
    ["deepstate", "alertreg", "jam", "ships", "fronts", "hazards", "quakes", "choke", "ukmto", "events", "mil"].forEach((id) => map.addSource(id, { type: "geojson", data: empty }));
    const zoomW = (a, b, c) => ["interpolate", ["linear"], ["zoom"], 2, a, 6, b, 9, c];
    map.addLayer({ id: "ds-fill", type: "fill", source: "deepstate", paint: { "fill-color": "#8c3b2e", "fill-opacity": 0.16 } });
    map.addLayer({ id: "ar-fill", type: "fill", source: "alertreg", paint: { "fill-color": ["get", "col"], "fill-opacity": 0.2 } });
    map.addLayer({ id: "ar-line", type: "line", source: "alertreg", paint: { "line-color": ["get", "col"], "line-width": 1, "line-opacity": 0.7 } });
    map.addLayer({ id: "jam-fill", type: "fill", source: "jam", paint: { "fill-color": ["get", "col"], "fill-opacity": 0.32 } });
    map.addLayer({ id: "base-ref", type: "raster", source: "ref", paint: { "raster-opacity": 0.95 } });
    map.addLayer({ id: "ship-dot", type: "circle", source: "ships", paint: { "circle-radius": zoomW(1.9, 2.8, 4.2), "circle-color": ["get", "col"], "circle-opacity": 0.9 } });   // 1.7.3: was 1.2 px at 0.75, close to invisible at world zoom
    const isLine = ["==", ["geometry-type"], "LineString"], round = { "line-cap": "round", "line-join": "round" };
    map.addLayer({ id: "fr-case", type: "line", source: "fronts", filter: isLine, layout: round, paint: { "line-color": "#fff", "line-opacity": 0.9, "line-width": zoomW(4.6, 6.6, 8.4) } });
    map.addLayer({ id: "fr-line", type: "line", source: "fronts", filter: ["all", isLine, ["==", ["get", "kind"], "contact"]], layout: round, paint: { "line-color": ["get", "col"], "line-width": zoomW(2.4, 3.6, 4.8) } });
    map.addLayer({ id: "fr-dash", type: "line", source: "fronts", filter: ["all", isLine, ["in", ["get", "kind"], ["literal", ["blockade", "supposed"]]]], paint: { "line-color": ["get", "col"], "line-width": zoomW(2.4, 3.6, 4.8), "line-dasharray": [2.4, 1.6] } });
    map.addLayer({ id: "fr-dot", type: "line", source: "fronts", filter: ["all", isLine, ["==", ["get", "kind"], "defense"]], paint: { "line-color": ["get", "col"], "line-width": zoomW(2.4, 3.6, 4.8), "line-dasharray": [0.6, 1.4] } });
    map.addLayer({ id: "hz-dot", type: "circle", source: "hazards", paint: { "circle-radius": ["match", ["get", "alert"], "Red", 10, "Orange", 8, 4.5], "circle-color": ["get", "col"], "circle-opacity": 0.85, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
    map.addLayer({ id: "qk-dot", type: "circle", source: "quakes", paint: { "circle-radius": ["interpolate", ["linear"], ["get", "mag"], 4, 5, 6, 12, 7.5, 22], "circle-color": ["get", "col"], "circle-opacity": 0.12, "circle-stroke-color": ["get", "col"], "circle-stroke-width": 1.8 } });
    map.addLayer({ id: "cp-dot", type: "circle", source: "choke", paint: { "circle-radius": 5, "circle-color": "#fff", "circle-stroke-color": ["get", "col"], "circle-stroke-width": 2.5 } });
    map.addLayer({ id: "cp-txt", type: "symbol", source: "choke", layout: { "text-field": ["get", "label"], "text-font": ["Open Sans Regular"], "text-size": 12.5, "text-offset": [0, 0.9], "text-anchor": "top", "text-max-width": 9, "text-optional": true },
      paint: { "text-color": ["get", "col"], "text-halo-color": "#fff", "text-halo-width": 1.8 } });
    map.addLayer({ id: "uk-ico", type: "symbol", source: "ukmto", layout: { "icon-image": ["get", "img"], "icon-size": zoomW(0.42, 0.62, 0.8), "icon-allow-overlap": true, "icon-ignore-placement": true }, paint: { "icon-opacity": ["get", "op"] } });
    map.addLayer({ id: "ev-recent", type: "circle", source: "events", filter: ["==", ["get", "recent"], true], paint: { "circle-radius": zoomW(10, 15, 20), "circle-color": RED, "circle-opacity": 0.14, "circle-stroke-color": RED, "circle-stroke-width": 1.5 } });
    map.addLayer({ id: "ev-pin", type: "symbol", source: "events", layout: { "icon-image": ["get", "pin"], "icon-size": zoomW(0.42, 0.62, 0.84), "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["get", "rank"] },
      paint: { "icon-opacity": ["get", "op"] } });
    map.addLayer({ id: "mil-ico", type: "symbol", source: "mil", layout: { "icon-image": ["get", "img"], "icon-size": zoomW(0.46, 0.62, 0.8), "icon-rotate": ["get", "rot"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true } });
    map.addLayer({ id: "fr-ico", type: "symbol", source: "fronts", filter: ["==", ["geometry-type"], "Point"], layout: { "icon-image": ["concat", "fr-", ["get", "kind"]], "icon-size": zoomW(0.46, 0.66, 0.84),
      "icon-allow-overlap": true, "icon-ignore-placement": true, "text-field": ["step", ["zoom"], "", 3.4, ["get", "name"]], "text-size": 12.5, "text-font": ["Open Sans Regular"], "text-offset": [0, 1.3], "text-anchor": "top", "text-optional": true, "text-max-width": 10 },
      paint: { "text-color": "#7d1a14", "text-halo-color": "#fff", "text-halo-width": 1.8 } });
    ready = true; $("maploading").hidden = true;
    fetch("geo/alert-regions.json?v=0.7.0").then((r) => r.json()).then((j) => { regions = new Map(j.features.map((f) => [f.id, f])); drawAlerts(); }).catch(() => {});
    ["ev-pin", "fr-ico", "fr-line", "fr-dash", "fr-dot", "uk-ico", "cp-dot", "mil-ico", "qk-dot", "hz-dot", "ship-dot", "ar-fill"].forEach((id) => {
      map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
    });
    map.on("click", onClick);
    map.on("moveend", renderInView);
    applyTopic(); drawAll(); applyView(S.route);
  });

  // ---------- drawing the data ----------
  function drawEvents() {
    if (!ready || !S.events) return;
    const now = Date.now(), cats = TOPICS[topic].cats;
    const feats = S.events.features.filter((f) => f.properties.kind === "event" && f.geometry && f.geometry.type === "Point" && (!cats || cats.includes(f.properties.category))).map((f) => {
      const p = f.properties, age = p.ts_ms ? now - p.ts_ms : Infinity;
      return pt(f.geometry.coordinates, { id: p.id, pin: "pin-" + glyphOf(p) + "-" + G.fam(p.category), rank: (p.ts_ms || 0) / 1e7, recent: age < 6 * 3600e3 && p.ts_source !== "date", op: age < 864e5 ? 1 : age < 2592e5 ? 0.85 : 0.6 });
    });
    map.getSource("events").setData(fc(feats));
    buildFronts();
    const kinds = TOPICS[topic].fronts;
    map.getSource("fronts").setData(fc(FRONTS.filter((f) => !kinds || kinds.includes(f.kind)).flatMap((f) => [
      { type: "Feature", geometry: { type: "LineString", coordinates: f.cs }, properties: { id: f.id, kind: f.kind, col: KIND[f.kind][1] } },
      pt(f.mid, { id: f.id, kind: f.kind, name: f.name })])));
  }
  const alertRegions = () => ((((S.alerts || {}).regions || {}).regions) || []).filter((r) => r.kind === "alert");
  function drawAlerts() {
    if (!ready || !regions) return;
    map.getSource("alertreg").setData(fc(alertRegions().filter((r) => regions.has(r.id)).sort((a, b) => (a.level === "red") - (b.level === "red"))
      .map((r) => ({ type: "Feature", geometry: regions.get(r.id).geometry, properties: { id: r.id, col: r.level === "red" ? RED : AMBER } }))));
  }
  // 1.7.3: a source is rebuilt only when its feed is a new copy (each fetch makes a new object), not at every reload
  // and topic change; and it is rebuilt as soon as a new copy arrives ("feed" below), so a popup, which looks its
  // entry up by position in the feed, always reads the copy the dots were drawn from.
  const drawn = {};
  const fresh = (name) => { const d = S.feeds[name]; if (!d || drawn[name] === d) return false; drawn[name] = d; return true; };
  // the time of the newest ship position in a copy of the ships feed, worked out once per copy
  G.shipsAt = (sh) => { if (sh._newest == null) { let m = 0; (sh.points || []).forEach((p) => { const t = Date.parse(p[7]); if (t > m) m = t; }); sh._newest = m; } return sh._newest; };
  function drawTopicFeeds() {
    if (!ready) return;
    const F = S.feeds, now = Date.now();
    if (fresh("front") && F.front.geojson) map.getSource("deepstate").setData(fc(F.front.geojson.features.filter((f) => /occupied|CADR/i.test(f.properties.label || ""))));
    if (fresh("mil") && F.mil.geojson) map.getSource("mil").setData(fc(F.mil.geojson.features.map((f) => pt(f.geometry.coordinates, { hex: f.properties.hex, img: f.properties.role === "helicopter" ? "ac-heli" : "ac-plane", rot: f.properties.role === "helicopter" ? 0 : Number(f.properties.track) || 0 }))));
    if (F.gpsjam && window.h3 && fresh("gpsjam")) {
      const feats = [];
      (F.gpsjam.items || []).forEach(([h, lv]) => {
        if (lv !== "high" && lv !== "medium") return;
        let ring; try { ring = window.h3.cellToBoundary(h, true); } catch (e) { return; }
        const xs = ring.map((c) => c[0]); if (Math.max(...xs) - Math.min(...xs) > 180) return;   // skip cells across the date line
        feats.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: { col: lv === "high" ? RED : AMBER } });
      });
      map.getSource("jam").setData(fc(feats));
    }
    if (fresh("ukmto")) map.getSource("ukmto").setData(fc((F.ukmto.items || []).filter((i) => i.coord).map((i, n) => {
      const age = now - Date.parse(i.date + "T00:00:00Z");
      return pt(i.coord, { n, img: /attack|hijack/i.test(i.type) ? "uk-hot" : "uk-cool", op: age < 8 * 864e5 ? 1 : 0.45 });
    })));
    if (fresh("portwatch")) map.getSource("choke").setData(fc((F.portwatch.chokepoints || []).map((c, n) => {
      const ch = (c.change_vs_year_pct || {}).total;
      return pt([c.lon, c.lat], { n, col: ch != null && ch <= -50 ? RED : SEA, label: c.name + (ch != null ? "\n" + (ch > 0 ? "+" : "") + ch + "% on last year" : "") });
    })));
    if (fresh("ships")) map.getSource("ships").setData(fc((F.ships.points || []).map((p, n) => pt([p[0], p[1]], { n, col: p[4] === "tanker" ? INK : "#5b7f99" }))));
    if (fresh("quakes") && F.quakes.geojson) map.getSource("quakes").setData(fc(F.quakes.geojson.features.map((f, n) => pt(f.geometry.coordinates, { n, mag: f.properties.mag || 4, col: f.properties.watch ? RED : INK }))));
    if (fresh("hazards") && F.hazards.geojson) map.getSource("hazards").setData(fc(F.hazards.geojson.features.filter((f) => f.properties.type !== "EQ").map((f, n) => pt(f.geometry.coordinates, { n: F.hazards.geojson.features.indexOf(f), alert: f.properties.alert, col: f.properties.alert === "Red" ? RED : f.properties.alert === "Orange" ? AMBER : GREY }))));
  }
  function drawAll() { drawEvents(); drawAlerts(); drawTopicFeeds(); renderCaption(); renderInView(); }

  function loadTopicFeeds() {
    const names = topicFeeds();
    const jobs = names.map((n) => G.need(n).catch(() => null));
    if (topic === "air" && !window.h3) jobs.push(G.statusKnown.then(() => {
      if (G.absent("gpsjam")) return null;   // the hexagon decoder is only for GPS interference
      h3wait = h3wait || new Promise((res) => { const s = document.createElement("script"); s.src = "vendor/h3-js.umd.js?v=4.5.0"; s.onload = res; s.onerror = res; document.head.appendChild(s); });
      return h3wait;
    }));
    return Promise.all(jobs).then(() => { drawTopicFeeds(); renderCaption(); renderInView(); });
  }
  const topicEmpty = (k) => { const t = TOPICS[k]; return Array.isArray(t.cats) && !t.cats.length && (t.feeds || []).length > 0 && t.feeds.every(G.absent); };
  function syncTopics() {   // a topic with no pins of its own and no feed on this copy would lead to nothing: its switch is hidden
    document.querySelectorAll("#topics [data-topic]").forEach((b) => { b.hidden = topicEmpty(b.dataset.topic); });
    if (topicEmpty(topic)) { topic = "conflict"; applyTopic(); }
  }
  function applyTopic() {
    document.querySelectorAll("#topics [data-topic]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.topic === topic)));
    if (!ready) return;
    ALL_LAYERS.forEach((id) => map.setLayoutProperty(id, "visibility", TOPICS[topic].layers.includes(id) ? "visible" : "none"));
    if (pop) pop.remove();
    drawEvents(); renderCaption(); loadTopicFeeds();
  }
  $("topics").innerHTML = Object.entries(TOPICS).map(([k, t]) => `<button type="button" class="topic" data-topic="${k}" aria-pressed="${k === topic}">${t.label}</button>`).join("");
  $("topics").addEventListener("click", (e) => { const b = e.target.closest("[data-topic]"); if (!b) return; topic = b.dataset.topic; G.store.set("topic", topic); applyTopic(); renderInView(); });

  // ---------- caption ----------
  const lg = (cls, txt) => `<span class="lg"><i class="${cls}" aria-hidden="true"></i>${txt}</span>`;
  // a feed this copy does not carry (1.7.1): one plain line, not an error
  const FEEDNAME = { front: "Occupied areas (DeepState)", mil: "Military aircraft", gpsjam: "GPS interference", ukmto: "Incidents at sea (UKMTO)", portwatch: "Chokepoint traffic", ships: "Ships", quakes: "Earthquakes", hazards: "Disaster alerts" };
  const notHere = (names) => { const gone = names.filter(G.absent); return gone.length ? ` <span class="muted">${gone.map((n) => FEEDNAME[n]).join(", ")}: not on this copy.</span>` : ""; };
  const notLoaded = (names) => { const bad = names.filter((n) => S.failed[n] && !S.feeds[n]); return bad.length ? ` <span class="warn">Could not load: ${bad.join(", ")}.</span>` : ""; };
  function renderCaption() {
    const s = S.summary || {}, F = S.feeds; let h = "";
    if (wall.on) { $("mapcap").innerHTML = wall.caption || ""; return; }
    const row = (...items) => `<span class="lgrow">${items.join("")}</span>`;
    if (topic === "conflict") {
      const ar = alertRegions(), red = ar.filter((r) => r.level === "red").length;
      // the pins on the map: the source map's and the other pin sources', counted as drawn
      const ps = G.pinStats(), others = Object.entries(G.PINSRC).filter(([k]) => ps.by[k]).map(([k, v]) => `${esc(v[0])} (${nf(ps.by[k])})`);
      const from = others.length ? `Pins come from the source map (${nf(ps.by.map || 0)}), ${others.length > 1 ? others.slice(0, -1).join(", ") + " and " + others[others.length - 1] : others[0]}. ` : "";
      h = `<b>Conflict.</b> ${nf(S.events ? ps.h24 : s.events_24h)} of the ${nf(S.events ? ps.total : s.events_total)} event pins are from the last 24 hours. Older pins are faded; a red ring marks the last 6 hours. ${from}`
        + `${ar.length ? `${G.plural(ar.length, "region")} ${ar.length === 1 ? "is" : "are"} under an air-raid alert now (${nf(red)} red). ` : ""}Lines are drawn as the source map draws them.` + notLoaded(["front"]) + notHere(["front"])
        + row(lg("ln", "Front line"), lg("ln dash", "Blockade"), lg("ln dots", "Defence line"), `<span class="lg"><i class="sw red"></i><i class="sw amber"></i>Air-raid alert, red and yellow</span>`, G.absent("front") ? "" : lg("sw rust", "Occupied, per DeepState"))
        + row(...Object.entries(G.FAMILY).map(([k, v]) => lg("dot f-" + k, v[0])));
    } else if (topic === "air") {
      const n = ((F.mil || {}).geojson || { features: [] }).features.length, j = F.gpsjam || {};
      h = `<b>Air.</b> ${F.mil ? nf(n) + " military aircraft are being heard on open receivers now. " : G.absent("mil") ? "" : "Loading aircraft. "}Pins are the map’s aviation, missile and drone events. Restricted airspace is listed in the <a href="#/air">Air</a> section and is not drawn on this map.` + notLoaded(["mil", "gpsjam"]) + notHere(["mil", "gpsjam"])
        + row(G.absent("mil") ? "" : lg("pinx slate", "Military aircraft"), j.levels ? `<span class="lg"><i class="sw red"></i><i class="sw amber"></i>High and medium GPS interference, ${esc(G.fmtDate(j.date))}</span>` : "", lg("dot f-violent", "Missile or drone event"), lg("dot f-military", "Aviation event"));
    } else if (topic === "sea") {
      const u = F.ukmto || {}, sh = F.ships || {};
      h = `<b>Sea.</b> Incidents reported to UKMTO${u.located != null ? ` (${nf(u.located)} placed; the last 7 days at full strength)` : ""}, chokepoints with their traffic against a year ago, and the map’s own sea events. `
        + `${sh.points ? `Small dots are ${nf(sh.points.length)} ships heard by volunteer receivers: none in the Gulf or Red Sea means no coverage there, not no ships.${G.shipsAt(sh) ? ` Newest position heard ${esc(G.when(G.shipsAt(sh)))} ${G.zlabel()}.` : ""}${sh._ok === false ? ` <span class="warn">The last refresh of the ship feed failed; these are the positions it had.</span>` : ""}` : ""}` + notLoaded(["ukmto", "portwatch", "ships"]) + notHere(["ukmto", "portwatch", "ships"])
        + row(lg("pinx red", "Attack or hijack"), lg("pinx sea", "Other incident or sea event"), lg("ring sea", "Chokepoint"), lg("ring red", "Chokepoint down by half or more"), lg("ln dash", "Blockade line"),
          sh.points ? `<span class="lg"><i class="dot" style="width:7px;height:7px;background:#5b7f99" aria-hidden="true"></i>Ship heard</span><span class="lg"><i class="dot" style="width:7px;height:7px;background:${INK}" aria-hidden="true"></i>Tanker</span>` : "");
    } else if (topic === "outages") {
      const o = s.internet_outages || {};
      h = `<b>Outages.</b> Pins are the map’s energy, infrastructure and communications events. ${o.countries_with_outages != null ? `${nf(o.countries_with_outages)} countries had internet outages in ${nf(o.window_h)} hours: ` : ""}`
        + `outage areas, power, mobile networks and cables are listed in the <a href="#/outages">Outages and cyber</a> section and are not drawn on this map.`
        + row(lg("dot f-infra", "Energy, infrastructure or communications event"));
    } else if (topic === "hazards") {
      const q = F.quakes || {}, hz = F.hazards || {};
      const parts = [q.count != null ? `${nf(q.count)} earthquakes of magnitude 4 or more in ${nf(q.window_hours)} hours` : G.absent("quakes") ? "" : "Loading earthquakes", hz.count != null ? `${nf(hz.count)} disaster alerts from GDACS in ${nf(hz.window_days)} days` : ""].filter(Boolean);
      h = `<b>Hazards.</b> ${parts.length ? parts.join(" and ") + ". " : ""}Fires are counted in the <a href="#/hazards">Hazards</a> section.` + notLoaded(["quakes", "hazards"]) + notHere(["quakes", "hazards"])
        + row(lg("ring", "Earthquake, sized by magnitude"), lg("ring red", "Earthquake on the watch list"), lg("dot f-violent", "Red"), lg("dot amberdot", "orange"), lg("dot f-words", "green disaster alert"));
    }
    $("mapcap").innerHTML = h;
  }

  // ---------- popups ----------
  let pop = null;
  function showPopup(ll, html) {
    if (pop) pop.remove();
    pop = new maplibregl.Popup({ maxWidth: "320px", className: "gtpop", offset: 12 }).setLngLat(ll).setHTML(html).addTo(map);
  }
  const link = (u, t) => (G.httpUrl(u) ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${t}</a>` : "");
  const card = (kick, title, lines, more) => `<div class="pc"><p class="pc-k">${kick}</p><h4>${esc(title)}</h4>${lines.filter(Boolean).map((l) => `<p>${l}</p>`).join("")}${more ? `<p class="pc-l">${more}</p>` : ""}</div>`;
  function eventCard(id) {
    const f = ((S.events || {}).features || []).find((x) => x.properties.id === id); if (!f) return null;
    const p = f.properties, place = p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name, from = G.pinSource(p);
    return { ll: f.geometry.coordinates, html: card(`<i class="dot f-${G.fam(p.category)}"></i>${esc(G.cat(p.category)[0])}`, p.title,
      [[esc(place || ""), esc(G.thName(p.theatre))].filter(Boolean).join(" · "),
        p.ts_ms ? (p.ts_source === "date" ? `${esc(G.dayOnly(p.ts_ms))} (date only)` : `${esc(G.when(p.ts_ms))} ${G.zlabel()} (${esc(G.ago(p.ts_ms))})`) : "No time given",
        // a pin from one of the other sources names it, with its credit; none means the source map
        from ? `<span class="muted">From ${esc(from)}${p.attribution ? " · " + esc(p.attribution) : ""}.${p.source_note ? " " + esc(p.source_note) : ""}</span>` : ""],
      link(p.url, `Open the source${p.handle ? " (@" + esc(p.handle) + ")" : ""}`)) };
  }
  function frontCard(f) {
    const [label, , , what] = KIND[f.kind], l = f.last;
    return card(esc(label), f.name, [`${esc(f.where || "")} · about ${nf(Math.round(f.km))} km`, esc(what),
      `<b>${nf(f.n24)}</b> event pin${f.n24 === 1 ? "" : "s"} within 75 km in the last 24 hours, <b>${nf(f.n72)}</b> in 72.${l ? ` Newest: “${esc(l.title)}” (${esc(G.ago(l.ts_ms))}).` : ""}`,
      `<span class="muted">Drawn by the source map’s curator. It moves only when they redraw it.</span>`]);
  }
  function onClick(e) {
    const ids = ["ev-pin", "fr-ico", "uk-ico", "cp-dot", "mil-ico", "qk-dot", "hz-dot", "fr-line", "fr-dash", "fr-dot", "ship-dot", "ar-fill"].filter((id) => map.getLayer(id) && map.getLayoutProperty(id, "visibility") !== "none");
    const hit = map.queryRenderedFeatures([[e.point.x - 5, e.point.y - 5], [e.point.x + 5, e.point.y + 5]], { layers: ids })[0];
    if (!hit) return;
    const p = hit.properties, id = hit.layer.id, F = S.feeds, at = hit.geometry.type === "Point" ? hit.geometry.coordinates : e.lngLat;
    if (id === "ev-pin") { const c = eventCard(p.id); if (c) showPopup(c.ll, c.html); return; }
    if (id.startsWith("fr-")) { const f = FRONTS.find((x) => x.id === p.id); if (f) showPopup(id === "fr-ico" ? f.mid : e.lngLat, frontCard(f)); return; }
    if (id === "uk-ico") { const i = ((F.ukmto || {}).items || []).filter((x) => x.coord)[p.n]; if (i) showPopup(at, card(`Maritime incident · ${esc(i.type || "")}`, i.where || "At sea", [esc(G.fmtDate(i.date)), esc(String(i.text || "").replace(/^.*?Incident Time:\s*\d{3,4}\s*UTC\s*/i, ""))], link(i.url, "Open the UKMTO notice"))); return; }
    if (id === "cp-dot") { const c = ((F.portwatch || {}).chokepoints || [])[p.n]; if (c) showPopup(at, card("Chokepoint", c.name, [`${nf((c.last || {}).total)} ships on ${esc(G.fmtDate(c.last_day))}; ${nf((c.avg7 || {}).total)} a day over 7 days.`, `Same week last year: ${nf((c.year_ago7 || {}).total)} a day${(c.change_vs_year_pct || {}).total != null ? ` (${c.change_vs_year_pct.total > 0 ? "+" : ""}${nf(c.change_vs_year_pct.total)}%)` : ""}.`, `<span class="muted">IMF PortWatch, about 3 days behind.</span>`])); return; }
    if (id === "mil-ico") { const a = (F.mil.geojson.features.find((x) => x.properties.hex === p.hex) || {}).properties; if (a) showPopup(at, card(`Military aircraft · ${esc(a.role || "")}`, a.tname || a.type || "Type unknown", [esc(a.owner || ""), `${a.flight ? "Callsign " + esc(String(a.flight).trim()) + " · " : ""}${a.alt != null ? esc(String(a.alt)) + (isNaN(a.alt) ? "" : " ft") : ""}${a.gs ? " · " + nf(Math.round(a.gs)) + " kt" : ""}`])); return; }
    if (id === "qk-dot") { const q = (F.quakes.geojson.features[p.n] || {}).properties; if (q) showPopup(at, card(q.watch ? "Earthquake · on the watch list" : "Earthquake", `Magnitude ${q.mag}, ${q.place || ""}`, [`${esc(G.when(G.isoMs(q.time)))} ${G.zlabel()} · ${nf(q.depth_km)} km deep`, q.watch_reason ? esc(q.watch_reason) : ""], link(q.url, "Open the record"))); return; }
    if (id === "hz-dot") { const h = (F.hazards.geojson.features[p.n] || {}).properties; if (h) showPopup(at, card(`${esc(h.type_label || "Hazard")} · ${esc(h.alert || "")} alert`, h.event_name || h.name || "", [esc(h.severity || ""), esc(String(h.name || "").slice(0, 160))], link(h.url, "Open GDACS"))); return; }
    if (id === "ship-dot") { const sp = ((F.ships || {}).points || [])[p.n], t = sp ? Date.parse(sp[7]) : NaN; if (sp) showPopup(at, card("Ship", sp[5] || "Name not heard", [`${esc(sp[4] || "type unknown")}${sp[10] ? " · flag " + esc(sp[10]) : ""}`, sp[8] ? "Bound for " + esc(sp[8]) : "",
      t ? `Heard ${esc(G.when(t))} ${G.zlabel()} (${esc(G.ago(t))})` : ""])); return; }   // 1.7.3: when the position was heard
    if (id === "ar-fill") { const r = alertRegions().find((x) => x.id === p.id); if (r) showPopup(e.lngLat, card(`Air-raid alert · ${esc(r.level || "")}`, r.en || r.name, [r.since ? `Since ${esc(G.when(G.isoMs(r.since)))} ${G.zlabel()} (${esc(r.duration || "")})` : "", `<span class="muted">Not a safety tool: follow official alerts.</span>`])); }
  }
  G.on("show", (pid) => {
    const c = eventCard(pid); if (!c) return;
    const fly = () => { if (topic !== "conflict") { topic = "conflict"; applyTopic(); } map.flyTo({ center: c.ll, zoom: Math.max(map.getZoom(), 5.2), speed: 1.6 }); showPopup(c.ll, c.html); };
    if (S.route.view === "map" || (S.route.view === "home" && window.innerWidth > 900)) { fly(); $("mapfig").scrollIntoView({ block: "nearest", behavior: "smooth" }); }
    else { location.hash = "#/map"; setTimeout(fly, 250); }
  });

  // ---------- "In view" list on the map page ----------
  function renderInView() {
    if (!ready || S.route.view !== "map" || window.innerWidth <= 900) return;
    const b = map.getBounds(), inb = (ll) => ll && b.contains(ll), F = S.feeds; let html = "", n = 0, what = "", gone = false;
    if (topic === "conflict" || topic === "outages" || topic === "air" || topic === "sea") {
      const cats = TOPICS[topic].cats, list = S.entries.filter((e) => e.src === "pin" && inb(e.ll) && (!cats || cats.includes(e.cat)));
      n = list.length; what = `event pin${n === 1 ? "" : "s"}`;
      html = list.slice(0, 40).map((e) => G.entryHtml(e, { date: true })).join("");
      if (topic === "sea" && F.ukmto) {
        const u = (F.ukmto.items || []).filter((i) => i.coord && inb(i.coord)).slice(0, 12);
        html = (u.length ? `<h3 class="grp"><span>Maritime incidents (UKMTO)</span></h3>` + u.map((i) => `<article class="entry"><time class="e-time">${esc(G.fmtDate(i.date))}</time><div class="e-body"><p class="e-kick"><i class="dot ${/attack|hijack/i.test(i.type) ? "f-violent" : "f-sea"}"></i>${esc(i.type || "")}</p><h3 class="e-title">${link(i.url, esc(i.where || "At sea")) || esc(i.where || "At sea")}</h3><p class="e-sum">${esc(String(i.text || "").replace(/^.*?Incident Time:\s*\d{3,4}\s*UTC\s*/i, "").slice(0, 200))}…</p></div></article>`).join("") : "") + (n ? `<h3 class="grp"><span>Event pins</span></h3>` : "") + html;
      }
      if (topic === "sea" && F.ships) what += `, ${nf((F.ships.points || []).filter((p) => inb([p[0], p[1]])).length)} ships`;   // 1.7.3: the ships in view are counted, as aircraft are
      if (topic === "air" && F.mil) { const m = F.mil.geojson.features.filter((f) => inb(f.geometry.coordinates)); what = `event pin${n === 1 ? "" : "s"}, ${nf(m.length)} military aircraft`; }
    } else if (topic === "hazards") {
      const q = ((F.quakes || {}).geojson || { features: [] }).features.filter((f) => inb(f.geometry.coordinates)).sort((a, c) => c.properties.mag - a.properties.mag);
      n = q.length; what = `earthquake${n === 1 ? "" : "s"}`; gone = G.absent("quakes");
      html = q.slice(0, 40).map((f) => `<article class="entry"><time class="e-time">M ${esc(f.properties.mag)}</time><div class="e-body"><h3 class="e-title">${link(f.properties.url, esc(f.properties.place || "")) || esc(f.properties.place || "")}</h3><p class="e-src">${esc(G.when(G.isoMs(f.properties.time)))} ${G.zlabel()}${f.properties.watch ? " · on the watch list" : ""}</p></div></article>`).join("");
    }
    $("inview-n").textContent = gone ? "" : `${nf(n)} ${what}`;
    $("inview").innerHTML = gone ? `<p class="none">${G.NOT_HERE}</p>` : html || `<p class="none">Nothing from this topic in this part of the map.</p>`;
    $("inview-hint").textContent = `${TOPICS[topic].label}: ${topic === "hazards" ? "largest" : "newest"} first. Move the map and this list follows it.`;
  }

  // ---------- where the figure sits ----------
  const wall = { on: false, timer: null, i: 0, caption: "" };
  // The wall view needs no touch: the map walks through the tensest theatres, one every 40 seconds.
  const SIZES = { "ev-pin": [0.42, 0.62, 0.84], "fr-ico": [0.46, 0.66, 0.84] };
  const pinScale = (k) => Object.entries(SIZES).forEach(([id, [a, b, c]]) => map.setLayoutProperty(id, "icon-size", ["interpolate", ["linear"], ["zoom"], 2, a * k, 6, b * k, 9, c * k]));
  function wallStep() {
    const pic = (S.analysis || {}).picture || {}, by = (S.summary || {}).events_24h_by_theatre || {};
    const stops = (pic.theatres || []).filter((t) => G.THEATRES[t.theatre]).sort((a, b) => b.status - a.status).slice(0, 4);
    if (!stops.length) { wall.caption = `<b>The world.</b> ${nf((S.summary || {}).events_24h)} events pinned in the last 24 hours.`; renderCaption(); return; }
    const t = stops[wall.i % stops.length], next = stops[(wall.i + 1) % stops.length]; wall.i++;
    const [lon, lat, z] = G.THEATRES[t.theatre][1];
    map.flyTo({ center: [lon, lat], zoom: z + 0.4, speed: 0.6 });
    wall.caption = `<b>${esc(G.THEATRES[t.theatre][0])}.</b> Tension ${esc(t.status)} of 10${t.trend ? ", " + esc(t.trend) : ""}. ${G.plural(by[t.theatre] || 0, "event")} pinned in the last 24 hours.${stops.length > 1 ? ` <span class="muted">Next: ${esc(G.THEATRES[next.theatre][0])}.</span>` : ""}`;
    renderCaption();
  }
  function applyView(r) {
    const slot = { home: "slot-home", map: "slot-map", wall: "slot-wall" }[r.view];
    if (!slot) return;
    const fig = $("mapfig");
    if (fig.parentNode.id !== slot) $(slot).appendChild(fig);
    wall.on = r.view === "wall";
    clearInterval(wall.timer); wall.timer = null;
    requestAnimationFrame(() => {
      map.resize();
      if (!ready) return;
      pinScale(wall.on ? 1.5 : 1);
      if (wall.on) { if (topic !== "conflict") { topic = "conflict"; applyTopic(); } wall.i = 0; wallStep(); wall.timer = setInterval(wallStep, 40000); }
      if (r.q.topic && TOPICS[r.q.topic] && r.q.topic !== topic) { topic = r.q.topic; applyTopic(); }
      if (r.q.c) { const [lon, lat] = r.q.c.split(",").map(Number); if (isFinite(lon) && isFinite(lat)) map.jumpTo({ center: [lon, lat], zoom: Number(r.q.z) || 5 }); }
      renderCaption(); renderInView();
    });
  }
  G.on("route", applyView);
  const topicFeeds = () => [...(TOPICS[topic].feeds || []), ...(topic === "conflict" ? ["front"] : [])];
  // 1.7.3: at each reload the open topic asks again for its feeds that are due (they were fetched once and never again)
  G.on("data", () => { syncTopics(); drawAll(); if (ready && ["home", "map", "wall"].includes(S.route.view) && topicFeeds().some(G.due)) loadTopicFeeds(); if (wall.on && ready && wall.i === 0) wallStep(); });
  G.on("feed", () => { drawTopicFeeds(); });
  G.on("render", () => { renderCaption(); renderInView(); });
  window.addEventListener("resize", () => requestAnimationFrame(() => map.resize()));
  $("mapclose").addEventListener("click", () => { location.hash = "#/"; });
  G.map = map; G.topic = () => topic; G.setTopic = (k) => { if (TOPICS[k]) { topic = k; applyTopic(); renderInView(); } };
  applyView(S.route);
})();
