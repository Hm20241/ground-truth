/* Ground Truth 1.7.0, Atlas theme, map: one MapLibre map under everything. The topic pill decides which layers show; a tap on any mark
   opens the same detail card a feed entry opens. Basemap: the dark Esri raster today's page uses. No text layers, so no
   font server is needed (place names come from the Esri reference tiles). */
(() => {
  "use strict";
  const A = window.ATLAS, { S, COL, GLYPHS } = A;
  const INK = "#10131a", BG = "#0d1014";
  const empty = () => ({ type: "FeatureCollection", features: [] });
  const fc = (features) => ({ type: "FeatureCollection", features });
  const pt = (ll, properties) => ({ type: "Feature", geometry: { type: "Point", coordinates: ll }, properties });

  const map = new maplibregl.Map({
    container: "map", attributionControl: { compact: true }, center: [28, 32], zoom: 2.3, minZoom: 1.2, maxPitch: 0, dragRotate: false, fadeDuration: A.REDUCED ? 0 : 250,
    style: { version: 8,
      sources: {
        base: { type: "raster", tileSize: 256, maxzoom: 16, attribution: "Basemap © Esri",
          tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"] },
        ref: { type: "raster", tileSize: 256, maxzoom: 16,
          tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"] },
      },
      layers: [{ id: "bg", type: "background", paint: { "background-color": BG } },
        { id: "base", type: "raster", source: "base", paint: { "raster-brightness-max": 0.9, "raster-saturation": -0.3 } }] },
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  A.map = map;

  // A glyph on a canvas, as today's page draws it: ink on an optional coloured disc.
  function drawGlyph(name, px, ink, disc, scale) {
    const c = document.createElement("canvas"), sh = GLYPHS[name]; c.width = c.height = px;
    const g = c.getContext("2d");
    if (disc) { g.beginPath(); g.arc(px / 2, px / 2, px / 2 - 2, 0, Math.PI * 2); g.fillStyle = disc.fill; g.fill(); g.lineWidth = Math.max(2, px / 20); g.strokeStyle = disc.ring || INK; g.stroke(); }
    if (!sh) return c;
    const k = (px / 24) * (scale || (disc ? 0.6 : 1));
    g.translate(px / 2 - 12 * k, px / 2 - 12 * k); g.scale(k, k); g.lineCap = g.lineJoin = "round"; g.fillStyle = g.strokeStyle = ink;
    if (sh.fill) g.fill(new Path2D(sh.fill), "evenodd");
    (sh.stroke || []).forEach(([d, w]) => { g.lineWidth = w; g.stroke(new Path2D(d)); });
    return c;
  }
  const addImg = (id, c) => map.hasImage(id) || map.addImage(id, { width: c.width, height: c.height, data: c.getContext("2d").getImageData(0, 0, c.width, c.height).data }, { pixelRatio: 2 });

  // layer id -> the topics that show it
  const VIS = {
    "adv-fill": ["official"], "adv-line": ["official"], "cy-fill": ["cyber"], "cy-line": ["cyber"], "out-fill": ["outages"], "out-line": ["outages"], "cab-line": ["outages"],
    "da-fill": ["all", "conflict"], "da-line": ["all", "conflict"], "ar-fill": ["all", "alerts"], "ar-line": ["all", "alerts"], "tfr-fill": ["air"], "tfr-line": ["air"],
    "base-ref": true, "ov-fill": ["all", "conflict"], "ov-line": ["all", "conflict"], "fr-case": ["all", "conflict"], "fr-line": ["all", "conflict"], "fr-dash": ["all", "conflict"],
    "th-pt": ["hazards"], "hz-pt": ["hazards"], "qk-pt": ["hazards"], "ship-pt": ["sea"], "pw-pt": ["sea"], "uk-pt": ["all", "sea"], "og-pt": ["outages"],
    "ev-halo": ["all", "conflict", "sea", "outages"], "ev-pt": ["all", "conflict", "sea", "outages"], "ev-ico": ["all", "conflict", "sea", "outages"], "fr-ico": ["all", "conflict"],
    "mil-pt": ["air"], "sq-pt": ["air"], "em-pt": ["alerts", "official"], "il-pt": ["all", "alerts"],
  };
  // top-most first: what a tap picks when marks overlap
  const CLICK = ["il-pt", "ev-pt", "fr-ico", "sq-pt", "mil-pt", "uk-pt", "em-pt", "pw-pt", "og-pt", "qk-pt", "hz-pt", "ship-pt", "fr-line", "fr-dash", "ar-fill", "tfr-fill", "ov-fill", "out-fill", "cy-fill", "adv-fill"];
  const TONE = ["match", ["get", "tone"], "red", COL.red, "amber", COL.amber, "blue", COL.blue, COL.slate];
  let ready = false;

  map.on("load", () => {
    map.on("styleimagemissing", (e) => { const m = /^pin-([a-z]+)-([a-z]+)$/.exec(e.id); if (m && GLYPHS[m[1]] && COL[m[2]]) addImg(e.id, drawGlyph(m[1], 64, INK, { fill: COL[m[2]] })); });
    Object.entries(A.FRONT_KIND).forEach(([k, v]) => addImg("fr-" + k, drawGlyph(v[1], 72, INK, { fill: "#fff", ring: COL.red })));
    addImg("ac", drawGlyph("plane", 56, "#eef2f7")); addImg("ac-hot", drawGlyph("plane", 56, COL.red));
    ["adv", "cy", "out", "cab", "da", "ar", "tfr", "ov", "fr", "th", "hz", "qk", "ship", "pw", "uk", "og", "ev", "mil", "sq", "em", "il"].forEach((id) => map.addSource(id, { type: "geojson", data: empty() }));
    const L = (o) => map.addLayer(o);
    L({ id: "adv-fill", type: "fill", source: "adv", paint: { "fill-color": ["match", ["get", "level"], 4, COL.red, COL.amber], "fill-opacity": ["match", ["get", "level"], 4, 0.26, 0.14] } });
    L({ id: "adv-line", type: "line", source: "adv", paint: { "line-color": ["match", ["get", "level"], 4, COL.red, COL.amber], "line-opacity": 0.6, "line-width": 1 } });
    L({ id: "cy-fill", type: "fill", source: "cy", paint: { "fill-color": COL.amber, "fill-opacity": ["interpolate", ["linear"], ["get", "n"], 0, 0.05, 5, 0.18, 40, 0.5] } });
    L({ id: "cy-line", type: "line", source: "cy", paint: { "line-color": COL.amber, "line-opacity": 0.45, "line-width": 0.8 } });
    L({ id: "out-fill", type: "fill", source: "out", paint: { "fill-color": COL.amber, "fill-opacity": ["case", ["get", "ongoing"], 0.24, 0.07] } });
    L({ id: "out-line", type: "line", source: "out", paint: { "line-color": COL.amber, "line-opacity": ["case", ["get", "ongoing"], 0.9, 0.35], "line-width": 1 } });
    L({ id: "cab-line", type: "line", source: "cab", paint: { "line-color": COL.slate, "line-opacity": 0.3, "line-width": 0.8 } });
    L({ id: "da-fill", type: "fill", source: "da", filter: ["!=", ["get", "st"], "freed"], paint: { "fill-color": ["match", ["get", "st"], "held", COL.red, COL.slate], "fill-opacity": ["match", ["get", "st"], "held", 0.17, 0.12] } });
    L({ id: "da-line", type: "line", source: "da", paint: { "line-color": ["match", ["get", "st"], "held", COL.red, COL.slate], "line-opacity": 0.4, "line-width": 0.7 } });
    L({ id: "ar-fill", type: "fill", source: "ar", paint: { "fill-color": TONE, "fill-opacity": ["match", ["get", "tone"], "red", 0.34, "amber", 0.22, 0.08] } });
    L({ id: "ar-line", type: "line", source: "ar", paint: { "line-color": TONE, "line-opacity": 0.85, "line-width": 1.1 } });
    L({ id: "tfr-fill", type: "fill", source: "tfr", paint: { "fill-color": COL.blue, "fill-opacity": 0.2 } });
    L({ id: "tfr-line", type: "line", source: "tfr", paint: { "line-color": COL.blue, "line-opacity": 0.9, "line-width": 1.2 } });
    L({ id: "base-ref", type: "raster", source: "ref", paint: { "raster-opacity": 0.8 } });
    L({ id: "ov-fill", type: "fill", source: "ov", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": COL.slate, "fill-opacity": 0.14, "fill-outline-color": COL.slate } });
    L({ id: "ov-line", type: "line", source: "ov", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": COL.slate, "line-opacity": 0.75, "line-width": 1.3, "line-dasharray": [2.5, 2] } });
    const w = ["interpolate", ["linear"], ["zoom"], 2, 2.4, 6, 3.6, 9, 5], round = { "line-cap": "round", "line-join": "round" };
    L({ id: "fr-case", type: "line", source: "fr", filter: ["==", ["geometry-type"], "LineString"], layout: round, paint: { "line-color": BG, "line-opacity": 0.9, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 5, 6, 7, 9, 9] } });
    L({ id: "fr-line", type: "line", source: "fr", filter: ["all", ["==", ["geometry-type"], "LineString"], ["==", ["get", "fkind"], "contact"]], layout: round, paint: { "line-color": COL.red, "line-width": w } });
    L({ id: "fr-dash", type: "line", source: "fr", filter: ["all", ["==", ["geometry-type"], "LineString"], ["!=", ["get", "fkind"], "contact"]], paint: { "line-color": COL.red, "line-width": w, "line-dasharray": [2.2, 1.5] } });
    L({ id: "th-pt", type: "circle", source: "th", paint: { "circle-radius": ["interpolate", ["linear"], ["get", "frp"], 0, 1.5, 50, 3, 300, 6], "circle-color": COL.red, "circle-opacity": 0.55, "circle-blur": 0.3 } });
    L({ id: "hz-pt", type: "circle", source: "hz", paint: { "circle-radius": ["match", ["get", "tone"], "slate", 5, 8], "circle-color": TONE, "circle-opacity": 0.9, "circle-stroke-color": BG, "circle-stroke-width": 1.5 } });
    L({ id: "qk-pt", type: "circle", source: "qk", paint: { "circle-radius": ["interpolate", ["linear"], ["get", "mag"], 4, 5, 6, 11, 8, 20], "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": TONE, "circle-stroke-width": 2.4 } });
    L({ id: "ship-pt", type: "circle", source: "ship", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, ["match", ["get", "cls"], "military", 3.4, 1.6], 7, ["match", ["get", "cls"], "military", 6, 3.4]],
      "circle-color": ["match", ["get", "cls"], "military", COL.red, "tanker", COL.amber, COL.blue], "circle-opacity": ["match", ["get", "cls"], "military", 1, 0.7] } });
    L({ id: "pw-pt", type: "circle", source: "pw", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 7, 6, 12], "circle-color": TONE, "circle-stroke-color": BG, "circle-stroke-width": 2 } });
    L({ id: "uk-pt", type: "circle", source: "uk", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 4.5, 8, 8], "circle-color": BG, "circle-stroke-color": TONE, "circle-stroke-width": 2.6, "circle-opacity": ["get", "op"], "circle-stroke-opacity": ["get", "op"] } });
    L({ id: "og-pt", type: "circle", source: "og", paint: { "circle-radius": ["case", ["get", "active"], 7, 4.5], "circle-color": TONE, "circle-stroke-color": BG, "circle-stroke-width": 1.5 } });
    L({ id: "ev-halo", type: "circle", source: "ev", filter: ["==", ["get", "recent"], true], paint: { "circle-radius": 18, "circle-color": TONE, "circle-opacity": 0.22, "circle-blur": 0.5 } });
    L({ id: "ev-pt", type: "circle", source: "ev", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 4, 4, 8, 6, 11, 10, 14], "circle-color": TONE, "circle-stroke-color": BG, "circle-stroke-width": 1.4 } });
    L({ id: "ev-ico", type: "symbol", source: "ev", minzoom: 3.6, layout: { "icon-image": ["get", "pin"], "icon-size": ["interpolate", ["linear"], ["zoom"], 3.6, 7.5 / 16, 4, 8 / 16, 6, 11 / 16, 10, 14 / 16],
      "icon-allow-overlap": true, "icon-ignore-placement": true } });
    L({ id: "fr-ico", type: "symbol", source: "fr", filter: ["==", ["geometry-type"], "Point"], layout: { "icon-image": ["concat", "fr-", ["get", "fkind"]],
      "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.55, 6, 0.8, 9, 1], "icon-allow-overlap": true, "icon-ignore-placement": true } });
    L({ id: "mil-pt", type: "symbol", source: "mil", layout: { "icon-image": ["case", ["get", "hot"], "ac-hot", "ac"], "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.5, 6, 0.75, 9, 1],
      "icon-rotate": ["get", "track"], "icon-rotation-alignment": "map", "icon-allow-overlap": true } });
    L({ id: "sq-pt", type: "circle", source: "sq", paint: { "circle-radius": 11, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": TONE, "circle-stroke-width": 3 } });
    L({ id: "em-pt", type: "circle", source: "em", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 5, 6, 8], "circle-color": BG, "circle-stroke-color": COL.amber, "circle-stroke-width": 2.6 } });
    L({ id: "il-pt", type: "circle", source: "il", paint: { "circle-radius": ["case", ["get", "now"], 7, 3.5], "circle-color": TONE, "circle-stroke-color": BG, "circle-stroke-width": 1 } });

    CLICK.forEach((l) => { map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; }); map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; }); });
    map.on("click", (e) => {
      const r = 6, box = [[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]];
      const hits = map.queryRenderedFeatures(box, { layers: CLICK.filter((l) => map.getLayoutProperty(l, "visibility") !== "none") });
      if (!hits.length) return;
      // the top layer wins; among stacked marks in it, the one nearest the tap, then the newest (which is drawn on top)
      const dist = (f) => { if (f.geometry.type !== "Point") return 0; const p = map.project(f.geometry.coordinates); return Math.round(Math.hypot(p.x - e.point.x, p.y - e.point.y) / 4); };
      hits.sort((a, b) => CLICK.indexOf(a.layer.id) - CLICK.indexOf(b.layer.id) || dist(a) - dist(b) || (b.properties.ts || 0) - (a.properties.ts || 0));
      const card = cardFor(hits[0], e.lngLat);
      if (card) A.select(card, { fromMap: true });
    });
    ready = true; sync();
  });

  // ---------- data -> sources (each source is rebuilt only when its inputs change) ----------
  const ids = new WeakMap(); let idN = 0;
  const idOf = (o) => (o && typeof o === "object" ? ids.get(o) || (ids.set(o, ++idN), idN) : 0);
  const seen = {};
  const put = (src, key, make) => { if (seen[src] === key) return; seen[src] = key; map.getSource(src).setData(make()); };
  const frontState = (label) => (/occupied|CADR|Transnistria|Prussia/i.test(label || "") ? "held" : /unknown/i.test(label || "") ? "unknown" : "freed");
  function sync() {
    if (!ready) return;
    const d = S.d, now = Date.now(), topic = S.topic, T = (l) => VIS[l] === true || VIS[l].includes(topic);
    Object.keys(VIS).forEach((l) => map.setLayoutProperty(l, "visibility", T(l) ? "visible" : "none"));
    // alert regions are the subject of the Alerts topic and a quiet backdrop everywhere else
    const strong = topic === "alerts";
    map.setPaintProperty("ar-fill", "fill-opacity", ["match", ["get", "tone"], "red", strong ? 0.36 : 0.13, "amber", strong ? 0.24 : 0.07, strong ? 0.08 : 0]);
    map.setPaintProperty("ar-line", "line-opacity", strong ? 0.9 : 0.45);
    const cut = S.hours ? now - S.hours * 3600e3 : 0;
    put("ev", [idOf(d.events), idOf(d.geoconfirmed), idOf(d.cir), idOf(d.kinetic), topic, S.hours, S.entries.length].join(), () => fc(S.entries.filter((e) => e.group === "pins" && e.ts >= cut && (topic === "all" || e.topics.includes(topic)))
      .sort((a, b) => a.ts - b.ts).map((e) => pt(e.ll, { eid: e.id, ts: e.ts, tone: e.tone, pin: `pin-${e.glyph}-${e.tone}`, recent: now - e.ts < 6 * 3600e3 }))));
    put("fr", idOf(d.events) + "|" + S.fronts.length, () => fc(S.fronts.flatMap((f) => [{ type: "Feature", geometry: { type: "LineString", coordinates: f.cs }, properties: { eid: f.id, fkind: f.fkind } }, pt(f.ll, { eid: f.id, fkind: f.fkind })])));
    put("ov", idOf(d.events), () => fc(((d.events || {}).features || []).filter((f) => f.properties.kind === "overlay" && !A.FRONT_KIND[f.properties.front_kind])
      .map((f) => ({ type: "Feature", geometry: f.geometry, properties: { title: f.properties.title, otype: f.properties.overlay_type, note: f.properties.note || "", place: f.properties.country_name || "" } }))));
    put("da", idOf(d.front), () => fc((((d.front || {}).geojson || {}).features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: { st: frontState(f.properties.label), label: f.properties.label } })).filter((f) => f.properties.st !== "freed")));
    put("uk", idOf(d.ukmto) + "|" + S.entries.length, () => { const es = S.entries.filter((e) => e.kind === "Sea incident" && e.ll), newest = es.length ? es[0].ts : now;
      return fc(es.map((e) => pt(e.ll, { eid: e.id, tone: e.tone, op: Math.max(0.4, 1 - (newest - e.ts) / (45 * 86400000)) }))); });
    const al = d.alerts || {};
    put("ar", idOf(d.alerts) + "|" + S.reg.size, () => fc((((al.regions || {}).regions) || []).filter((r) => S.reg.has(r.id)).map((r) => ({ type: "Feature", geometry: S.reg.get(r.id).geometry,
      properties: { eid: "a" + r.id, tone: r.kind !== "alert" ? "slate" : r.level === "red" ? "red" : "amber", name: r.en, rkind: r.kind } }))));
    put("il", idOf(d.alerts), () => fc((((al.israel || {}).cities) || []).filter((c) => c.lon != null).map((c) => pt([c.lon, c.lat], { name: c.n, t: c.t, label: c.label || "", now: now / 1000 - c.t < 600, tone: now / 1000 - c.t < 600 ? "red" : "slate" }))));
    put("em", idOf(d.alerts) + "|" + S.entries.length, () => { const seenPost = new Set();
      return fc(S.entries.filter((e) => e.kind === "US embassy alert" && e.ll && now - e.ts < 72 * 3600e3 && !seenPost.has(e.src) && seenPost.add(e.src)).map((e) => pt(e.ll, { eid: e.id }))); });
    put("mil", idOf(d.mil), () => fc((((d.mil || {}).geojson || {}).features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: { ...f.properties, track: f.properties.track || 0, hot: !!(f.properties.emergency && f.properties.emergency !== "none") } }))));
    put("tfr", idOf(d.tfr), () => fc((((d.tfr || {}).geojson || {}).features || []).filter((f) => f.geometry && f.geometry.type !== "Point").map((f) => ({ type: "Feature", geometry: f.geometry, properties: { eid: "t" + A.hash(f.properties.notam_id) } }))));
    const byGroup = (src, test, extra) => put(src, src + S.entries.length + "|" + idOf(d[extra]), () => fc(S.entries.filter((e) => e.ll && test(e)).map((e) => pt(e.ll, { eid: e.id, tone: e.tone || "slate", active: !!e.active, mag: +(/Magnitude ([\d.]+)/.exec(e.title) || [0, 4])[1] }))));
    byGroup("sq", (e) => e.kind === "Aircraft emergency code", "squawk");
    byGroup("qk", (e) => e.kind === "Earthquake", "quakes");
    byGroup("hz", (e) => e.group === "hazards" && e.kind !== "Earthquake", "hazards");
    byGroup("og", (e) => e.group === "outages" && e.sub !== "internet", "power");
    put("out", idOf(d.outages_geo), () => fc(((d.outages_geo || {}).features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: { eid: "i" + f.properties.code, ongoing: !!f.properties.ongoing, name: f.properties.name } }))));
    put("cy", idOf(d.cyber_geo), () => fc(((d.cyber_geo || {}).features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: { ...f.properties, n: (f.properties.ransom_7d || 0) + (f.properties.attacks_7d || 0) } }))));
    put("adv", idOf(d.advisories_geo), () => d.advisories_geo || empty());
    put("cab", idOf(d.cables), () => (d.cables || {}).geojson || empty());
    put("pw", idOf(d.portwatch), () => fc(((d.portwatch || {}).chokepoints || []).filter((c) => c.pinned || (c.avg7 || {}).total >= 20).map((c) => { const chg = (c.change_vs_year_pct || {}).total;
      return pt([c.lon, c.lat], { pw: c.id, tone: chg == null ? "slate" : chg <= -50 ? "red" : chg <= -20 ? "amber" : "blue" }); })));
    put("ship", idOf(d.ships), () => fc(((d.ships || {}).points || []).map((p) => pt([p[0], p[1]], { sog: p[2], cls: p[4], name: p[5] || "", dest: p[8] || "", flag: p[10] || "" }))));
    put("th", idOf(d.firms), () => fc(((d.firms || {}).points || []).map((p) => pt([p[0], p[1]], { frp: p[2] }))));
  }
  A.on("data", sync); A.on("view", sync);

  // ---------- a tapped mark -> the card ----------
  function cardFor(ft, lngLat) {
    const p = ft.properties, l = ft.layer.id, ll = ft.geometry.type === "Point" ? ft.geometry.coordinates : [lngLat.lng, lngLat.lat];
    if (p.eid && S.byId.has(p.eid)) return S.byId.get(p.eid);
    const base = { id: "m" + l + A.hash(JSON.stringify(ll)), ll, facts: [] };
    if (l === "mil-pt") return { ...base, title: p.flight ? String(p.flight).trim() : p.reg || p.hex, kind: "Military aircraft", label: "Military aircraft", glyph: "plane", src: "adsb.lol",
      facts: [["Type", p.tname || p.type || "–"], ["Operator", p.owner || "–"], ["Height", p.alt != null ? A.nf(p.alt) + " ft" : "–"], ["Speed", p.gs != null ? Math.round(p.gs) + " knots" : "–"]],
      note: "Position as last heard from the aircraft's own transmitter. Aircraft photos are not in this theme yet. They are in the Classic theme.", classic: true };
    if (l === "ship-pt") return { ...base, title: p.name || "Unnamed ship", kind: "Ship", label: "Ship, " + (p.cls || "type unknown"), glyph: "ship", src: "AIS volunteers",
      facts: [["Flag", p.flag || "–"], ["Speed", p.sog != null ? p.sog + " knots" : "–"], ["Destination as sent", p.dest || "–"]], note: "Tracks, sanctions lists and ship details are not in this theme yet. They are in the Classic theme.", classic: true };
    if (l === "pw-pt") { const c = ((S.d.portwatch || {}).chokepoints || []).find((x) => x.id === p.pw); if (!c) return null; const chg = c.change_vs_year_pct || {};
      return { ...base, title: c.name, kind: "Chokepoint", label: "Chokepoint traffic", glyph: "anchor", src: "IMF PortWatch", tone: p.tone,
        facts: [["Ships a day, last 7 days", `${c.avg7.total} (tankers ${c.avg7.tanker})`], ["Same week last year", `${c.year_ago7.total} (tankers ${c.year_ago7.tanker})`],
          ["Change", chg.total == null ? "too few to compare" : `${chg.total > 0 ? "+" : ""}${chg.total}% all ships` + (chg.tanker == null ? "" : `, ${chg.tanker > 0 ? "+" : ""}${chg.tanker}% tankers`)], ["Counted through", c.last_day]] }; }
    if (l === "il-pt") return { ...base, title: p.name, kind: "Siren in Israel", label: p.now ? "Siren in the last 10 minutes" : "Siren in the last 24 hours", glyph: "megaphone", tone: p.tone, ts: p.t * 1000, src: "Home Front Command (Tzeva Adom)",
      note: "Not a safety service: follow official alerts if you are there. Shelter countdowns are not in this theme yet. They are in the Classic theme.", classic: true };
    if (l === "ar-fill") return { ...base, title: p.name, kind: "Alert region", label: p.rkind === "alert" ? "Air-raid alert" : "Standing warning (" + p.rkind + ")", glyph: "megaphone", src: "alerts.in.ua" };
    if (l === "ov-fill") return { ...base, title: p.title || "Area on the source map", kind: "Map overlay", label: "Area drawn on the source map (" + (p.otype || "other") + ")", glyph: "dot", place: p.place, summary: p.note };
    if (l === "cy-fill") return { ...base, title: p.name, kind: "Cyber activity", label: "Cyber activity, last 7 days", glyph: "shield", ll: [lngLat.lng, lngLat.lat],
      facts: [["Ransomware claims", `${p.ransom_7d || 0} (${p.ransom_24h || 0} in 24 hours)`], ["Reported attacks", String(p.attacks_7d || 0)], ["Denial-of-service targets now", String(p.ddos_now || 0)]].concat(p.groups ? [["Groups named", p.groups]] : []) };
    if (l === "adv-fill") return { ...base, title: p.country, kind: "Travel advisory", label: `US travel advisory, level ${p.level}`, glyph: "officer", tone: p.level === 4 ? "red" : "amber", ll: [lngLat.lng, lngLat.lat],
      summary: p.label, facts: [["Last updated", p.date || "–"]], url: A.safeUrl(p.url), urlLabel: "Read the advisory" };
    if (l === "out-fill") return { ...base, title: "Internet outage: " + p.name, kind: "Internet outage", label: "Internet outage" + (p.ongoing ? ", ongoing" : ""), glyph: "signal", ll: [lngLat.lng, lngLat.lat] };
    return null;
  }

  // ---------- moving ----------
  const pad = () => (A.pad ? A.pad() : { top: 0, bottom: 0, left: 0, right: 0 });
  A.flyTo = (ll, zoom, opt) => { const o = { center: ll, zoom: zoom == null ? Math.max(map.getZoom(), 5.2) : zoom, padding: pad(), duration: 1100, essential: false, ...(opt || {}) };
    if (A.REDUCED) map.jumpTo(o); else map.easeTo(o); };
  A.fit = (bbox, maxZoom) => map.fitBounds(bbox, { padding: Object.fromEntries(Object.entries(pad()).map(([k, v]) => [k, v + 60])), maxZoom: maxZoom || 7, duration: A.REDUCED ? 0 : 1100 });
  A.region = (k) => { const r = A.REGIONS[k]; if (r) A.flyTo([r[1][0], r[1][1]], r[1][2]); else A.flyTo([28, 32], 2.3); };
  let ring = null;
  A.mark = (card) => {
    if (ring) { ring.remove(); ring = null; }
    const ll = card && (card.ll || (S.cc.get(card.cc) || {}).ll); if (!ll) return null;
    const el = document.createElement("div"); el.className = "sel-ring" + (card.ll ? "" : " approx");
    ring = new maplibregl.Marker({ element: el }).setLngLat(ll).addTo(map);
    return ll;
  };
})();
