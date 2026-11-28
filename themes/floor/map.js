/* "Watch Floor" theme: the map. One MapLibre map, six views (Conflict, Air, Sea, Outages, Hazards, Advisories)
   in place of thirty layer checkboxes. Colour on the map is status only: red = active / kinetic, amber = elevated,
   pale slate = everything else. No map text layers (so no font server is needed); place names come from the
   basemap's own reference tiles. */
(() => {
  "use strict";
  const WF = window.WF, { esc, nf } = WF;
  const RED = "#ff5d55", AMB = "#f5b23c", GRN = "#3fd08f", PALE = "#9aa7b4", INK = "#0d0f11";
  const fc = (features) => ({ type: "FeatureCollection", features });
  const pt = (ll, properties) => ({ type: "Feature", geometry: { type: "Point", coordinates: ll }, properties });
  const link = (u, t) => (WF.url(u) ? `<a href="${esc(WF.url(u))}" target="_blank" rel="noopener">${esc(t || "Open the source")} ↗</a>` : "");
  const pop = (title, meta, body, u, ut) => `<div class="pop"><h3>${esc(title)}</h3><div class="m">${meta}</div>${body ? `<p>${body}</p>` : ""}${link(u, ut) ? `<p>${link(u, ut)}</p>` : ""}</div>`;
  WF.popHtml = pop;

  // `feeds`: the feeds behind a view's layers, named as a reader would, for the "Not on this copy" line in the map key (1.7.1)
  WF.VIEWS = {
    conflict: { name: "Conflict", pins: null, feeds: [["front", "Occupied area"], ["airalerts", "Air-raid alerts"]], legend: `<span><i style="background:${RED}"></i>Strike, missile, casualties</span><span><i style="background:${AMB}"></i>Drone, energy, sea, alert</span><span><i style="background:${PALE}"></i>Other reports</span><span><i class="ln"></i>Front line</span><span><i class="sq" style="background:${RED}"></i><i class="sq" style="background:${AMB}"></i>Air-raid alert</span><span><i class="sq" style="background:${PALE}"></i>Occupied area</span>` },
    air: { name: "Air", pins: ["aviation", "missile", "drone", "alert"], feeds: [["mil", "Military aircraft"], ["czib_geo", "Airspace warnings"], ["gpsjam", "GPS interference"], ["tfr", "US flight restrictions"]], legend: `<span><i style="background:#e8edf2"></i>Military aircraft</span><span><i class="sq" style="background:${AMB}"></i>Airspace warning</span><span><i class="sq" style="background:${RED}"></i>GPS interference, high</span><span><i class="ln" style="border-color:${PALE}"></i>US flight restriction</span>` },
    sea: { name: "Sea", pins: ["maritime"], feeds: [["ships", "Ships"], ["ukmto", "Incidents at sea"], ["portwatch", "Chokepoints"]], legend: `<span><i style="background:#5f6d7a"></i>Ship heard</span><span><i style="background:${AMB}"></i>Sanctioned or shadow-fleet ship</span><span><i style="background:${RED}"></i>Attack at sea</span><span><i style="background:${GRN}"></i>Chokepoint (colour = traffic against last year)</span>` },
    outages: { name: "Outages", pins: ["cyber", "energy"], feeds: [["outages_geo", "Internet outages"], ["power", "Power"], ["cellular", "Mobile"], ["websites", "Web"], ["cloud", "Cloud and AI"]], legend: `<span><i class="sq" style="background:${RED}"></i>Internet outage, ongoing, watched country</span><span><i class="sq" style="background:${AMB}"></i>Ongoing elsewhere</span><span><i style="background:${RED}"></i><i style="background:${AMB}"></i>Power, mobile, web or cloud incident</span>` },
    hazards: { name: "Hazards", pins: [], feeds: [["quakes", "Earthquakes"], ["hazards", "Disaster alerts"]], legend: `<span><i style="background:${PALE}"></i>Earthquake (size = magnitude)</span><span><i style="background:${AMB}"></i>On watch, or orange alert</span><span><i style="background:${RED}"></i>Red alert, or magnitude 6.5+</span>` },
    advisories: { name: "Advisories", pins: [], feeds: [["advisories_geo", "Travel advisories"], ["embassy", "US embassy alerts"]], legend: `<span><i class="sq" style="background:${RED}"></i>Do not travel</span><span><i class="sq" style="background:${AMB}"></i>Reconsider travel</span><span><i style="background:${AMB}"></i>US embassy alert in 72 h</span>` },
  };

  let map, ready = false;
  const pending = {}, LAYERS = [], CLICK = [];
  const set = (WF.mapSet = (name, data) => { if (ready && map.getSource(name)) map.getSource(name).setData(data); else pending[name] = data; });
  const image = (id, c) => map.hasImage(id) || map.addImage(id, { width: c.width, height: c.height, data: c.getContext("2d").getImageData(0, 0, c.width, c.height).data }, { pixelRatio: 2 });
  let popup = null;
  WF.popup = (ll, html) => { if (popup) popup.remove(); popup = new maplibregl.Popup({ maxWidth: "min(22rem, 86vw)", offset: 10 }).setLngLat(ll).setHTML(html).addTo(map); };
  WF.closePopup = () => { if (popup) popup.remove(); popup = null; };

  WF.initMap = () => {
    map = WF.map = new maplibregl.Map({
      container: "map", attributionControl: { compact: true }, center: [20, 30], zoom: 1.5, maxPitch: 0, dragRotate: false, fadeDuration: 0,
      style: { version: 8,
        sources: {
          base: { type: "raster", tileSize: 256, maxzoom: 16, attribution: "Basemap © Esri", tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"] },
          ref: { type: "raster", tileSize: 256, maxzoom: 16, tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"] },
        },
        layers: [{ id: "bg", type: "background", paint: { "background-color": INK } },
          { id: "base", type: "raster", source: "base", paint: { "raster-brightness-max": 0.8, "raster-saturation": -0.5 } }] },
    });
    map.touchZoomRotate.disableRotation();
    if (!WF.S.wall) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", build);
    map.on("styleimagemissing", (e) => {
      const m = /^pin-([a-z]+)-([0-9a-f]{6})$/.exec(e.id);
      if (m) image(e.id, WF.drawGlyph(m[1], 64, INK, { fill: "#" + m[2], ring: INK }));
    });
    if (window.ResizeObserver) new ResizeObserver(() => map.resize()).observe(WF.$("map"));
  };

  function build() {
    const add = (views, def) => { map.addLayer(def); LAYERS.push([def.id, views]); };
    const src = (...ids) => ids.forEach((id) => map.addSource(id, { type: "geojson", data: fc([]) }));
    src("adv", "outages", "czib", "gps", "ds", "alertreg", "ovl", "tfr", "fronts", "ships", "pw", "infra", "quakes", "hazards", "emb", "mil", "ukmto", "events");
    const lv = (prop, map2, dflt) => ["match", ["get", prop], ...Object.entries(map2).flat(), dflt];
    // ---- areas ----
    add(["advisories"], { id: "adv-fill", type: "fill", source: "adv", paint: { "fill-color": ["match", ["get", "level"], 4, RED, AMB], "fill-opacity": ["match", ["get", "level"], 4, 0.22, 0.12] } });
    add(["outages"], { id: "out-fill", type: "fill", source: "outages", paint: { "fill-color": ["case", ["all", ["==", ["get", "ongoing"], true], ["==", ["get", "watched"], true]], RED, ["==", ["get", "ongoing"], true], AMB, PALE], "fill-opacity": ["case", ["get", "ongoing"], 0.2, 0.07] } });
    add(["air"], { id: "cz-fill", type: "fill", source: "czib", paint: { "fill-color": AMB, "fill-opacity": 0.13 } });
    add(["air"], { id: "gps-fill", type: "fill", source: "gps", paint: { "fill-color": lv("level", { high: RED }, AMB), "fill-opacity": lv("level", { high: 0.3 }, 0.18) } });
    add(["conflict"], { id: "ds-fill", type: "fill", source: "ds", paint: { "fill-color": PALE, "fill-opacity": 0.16 } });
    add(["conflict"], { id: "ar-fill", type: "fill", source: "alertreg", paint: { "fill-color": lv("level", { red: RED, yellow: AMB }, PALE), "fill-opacity": lv("level", { red: 0.13, yellow: 0.1 }, 0.04) } });
    add(["conflict"], { id: "ov-fill", type: "fill", source: "ovl", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": PALE, "fill-opacity": 0.13 } });
    // place names from the basemap's reference tiles, above the fills and below the lines and pins
    add("*", { id: "ref", type: "raster", source: "ref", paint: { "raster-opacity": 0.9 } });
    // ---- lines ----
    add(["advisories"], { id: "adv-line", type: "line", source: "adv", paint: { "line-color": ["match", ["get", "level"], 4, RED, AMB], "line-opacity": 0.5, "line-width": 0.8 } });
    add(["outages"], { id: "out-line", type: "line", source: "outages", filter: ["==", ["get", "ongoing"], true], paint: { "line-color": ["case", ["get", "watched"], RED, AMB], "line-opacity": 0.6, "line-width": 0.9 } });
    add(["air"], { id: "cz-line", type: "line", source: "czib", paint: { "line-color": AMB, "line-opacity": 0.7, "line-width": 1, "line-dasharray": [3, 2] } });
    add(["air"], { id: "tfr-line", type: "line", source: "tfr", paint: { "line-color": PALE, "line-opacity": 0.8, "line-width": 1 } });
    add(["conflict"], { id: "ds-line", type: "line", source: "ds", paint: { "line-color": PALE, "line-opacity": 0.45, "line-width": 0.7 } });
    add(["conflict"], { id: "ar-line", type: "line", source: "alertreg", filter: ["in", ["get", "level"], ["literal", ["red", "yellow"]]], paint: { "line-color": lv("level", { red: RED }, AMB), "line-opacity": 0.9, "line-width": 1.3 } });
    add(["conflict"], { id: "ov-line", type: "line", source: "ovl", paint: { "line-color": PALE, "line-opacity": 0.7, "line-width": ["case", ["==", ["geometry-type"], "Polygon"], 0.8, 1.6] } });
    const isLine = ["==", ["geometry-type"], "LineString"], of = (...k) => ["all", isLine, ["in", ["get", "kind"], ["literal", k]]];
    const w = ["interpolate", ["linear"], ["zoom"], 2, 2.2, 6, 3.4, 9, 4.6], FR = ["conflict", "air", "sea"];
    add(FR, { id: "fr-case", type: "line", source: "fronts", filter: isLine, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": INK, "line-opacity": 0.85, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 4.4, 6, 6.4, 9, 8] } });
    add(FR, { id: "fr-line", type: "line", source: "fronts", filter: of("contact"), layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "col"], "line-width": w } });
    add(FR, { id: "fr-dash", type: "line", source: "fronts", filter: of("blockade", "supposed"), paint: { "line-color": ["get", "col"], "line-width": w, "line-dasharray": [2.4, 1.6] } });
    add(FR, { id: "fr-dot", type: "line", source: "fronts", filter: of("defense"), paint: { "line-color": ["get", "col"], "line-width": w, "line-dasharray": [0.6, 1.4] } });
    // ---- points ----
    const stroke = { "circle-stroke-color": INK, "circle-stroke-width": 1 };
    add(["sea"], { id: "ship-pt", type: "circle", source: "ships", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 1.4, 6, 2.6, 9, 4], "circle-color": ["case", ["get", "listed"], AMB, "#5f6d7a"], "circle-opacity": ["case", ["get", "listed"], 1, 0.75] } });
    add(["sea"], { id: "ship-listed", type: "circle", source: "ships", filter: ["==", ["get", "listed"], true], paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 3, 6, 4.5, 9, 6], "circle-color": AMB, ...stroke } });
    add(["sea"], { id: "pw-pt", type: "circle", source: "pw", paint: { "circle-radius": ["get", "r"], "circle-color": ["get", "col"], "circle-opacity": 0.3, "circle-stroke-color": ["get", "col"], "circle-stroke-width": 2 } });
    add(["outages"], { id: "infra-pt", type: "circle", source: "infra", paint: { "circle-radius": ["case", ["get", "big"], 7, 5], "circle-color": ["get", "col"], ...stroke } });
    add(["hazards"], { id: "hz-pt", type: "circle", source: "hazards", paint: { "circle-radius": ["get", "r"], "circle-color": ["get", "col"], "circle-opacity": 0.85, ...stroke } });
    add(["hazards"], { id: "qk-pt", type: "circle", source: "quakes", paint: { "circle-radius": ["get", "r"], "circle-color": ["get", "col"], "circle-opacity": 0.35, "circle-stroke-color": ["get", "col"], "circle-stroke-width": 1.6 } });
    add(["advisories"], { id: "emb-pt", type: "circle", source: "emb", paint: { "circle-radius": 6, "circle-color": AMB, ...stroke } });
    image("ac", WF.drawGlyph("plane", 44, "#e8edf2"));
    image("ac-red", WF.drawGlyph("plane", 44, RED));
    add(["air"], { id: "mil-ico", type: "symbol", source: "mil", layout: { "icon-image": ["case", ["get", "emerg"], "ac-red", "ac"], "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.55, 6, 0.85], "icon-rotate": ["get", "track"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true } });
    add(["sea"], { id: "uk-ico", type: "symbol", source: "ukmto", layout: { "icon-image": ["get", "pin"], "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.5, 6, 0.75], "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["get", "sev"] } });
    add("*", { id: "ev-pt", type: "circle", source: "events", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 2.6, 4, 4.5], "circle-color": ["get", "col"], "circle-opacity": ["get", "o"], "circle-stroke-color": INK, "circle-stroke-width": 0.8, "circle-stroke-opacity": ["get", "o"] }, layout: { "circle-sort-key": ["get", "k"] } });
    add("*", { id: "ev-ico", type: "symbol", source: "events", minzoom: 3.2, layout: { "icon-image": ["get", "pin"], "icon-size": ["interpolate", ["linear"], ["zoom"], 3.2, 0.42, 5.5, 0.6, 8, 0.8], "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["get", "k"] }, paint: { "icon-opacity": ["get", "o"] }, filter: ["!=", ["get", "pin"], ""] });
    Object.entries(WF.FRONT_KIND).forEach(([k, v]) => image("fr-" + k, WF.drawGlyph(v[2], 72, INK, { fill: k === "supposed" ? AMB : RED, ring: INK })));
    add(FR, { id: "fr-ico", type: "symbol", source: "fronts", filter: ["==", ["geometry-type"], "Point"], layout: { "icon-image": ["concat", "fr-", ["get", "kind"]], "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.5, 6, 0.72, 9, 0.9], "icon-allow-overlap": true, "icon-ignore-placement": true } });
    // what a click can land on, topmost first
    CLICK.push("fr-ico", "ev-ico", "ev-pt", "uk-ico", "mil-ico", "emb-pt", "infra-pt", "qk-pt", "hz-pt", "pw-pt", "ship-listed", "ship-pt", "fr-line", "fr-dash", "fr-dot", "ov-line", "tfr-line",
      "ar-fill", "ov-fill", "cz-fill", "gps-fill", "out-fill", "adv-fill", "ds-fill");
    map.on("click", (e) => {
      const ids = CLICK.filter((id) => map.getLayer(id) && map.getLayoutProperty(id, "visibility") !== "none");
      const fs = map.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], { layers: ids });
      const f = fs.sort((a, b) => ids.indexOf(a.layer.id) - ids.indexOf(b.layer.id))[0];
      if (f && f.properties.h) WF.popup(f.geometry.type === "Point" ? f.geometry.coordinates : e.lngLat, f.properties.h);
    });
    map.on("mousemove", (e) => {
      const ids = CLICK.slice(0, 12).filter((id) => map.getLayer(id) && map.getLayoutProperty(id, "visibility") !== "none");
      map.getCanvas().style.cursor = map.queryRenderedFeatures(e.point, { layers: ids }).length ? "pointer" : "";
    });
    ready = true;
    Object.keys(pending).forEach((k) => { if (map.getSource(k)) map.getSource(k).setData(pending[k]); delete pending[k]; });
    WF.setView(WF.S.view, true);
    WF.flyTheatre(WF.S.theatre, true);
    if (WF.onMapReady) WF.onMapReady();
  }

  WF.setView = (v, quiet) => {
    WF.S.view = v;
    if (!ready) return;
    LAYERS.forEach(([id, views]) => map.setLayoutProperty(id, "visibility", views === "*" || views.includes(v) ? "visible" : "none"));
    const pins = WF.VIEWS[v].pins, f = pins ? ["in", ["get", "cat"], ["literal", pins]] : null;
    map.setFilter("ev-pt", f);
    map.setFilter("ev-ico", f ? ["all", ["!=", ["get", "pin"], ""], f] : ["!=", ["get", "pin"], ""]);
    if (!quiet) WF.closePopup();
  };
  WF.flyTheatre = (k, instant) => {
    if (!map) return;
    const [lon, lat, z] = WF.THEATRES[k][1], narrow = window.innerWidth <= 1100;
    if (k === "global") return map.fitBounds([[-128, -38], [152, 66]], { padding: 8, duration: instant ? 0 : 1400 });  // the whole inhabited world, whatever the panel's size
    map[instant ? "jumpTo" : "flyTo"]({ center: [lon, lat], zoom: z - (narrow ? 1 : 0), duration: 1400 });
  };
  WF.focus = (ll, html, zoom) => { map.flyTo({ center: ll, zoom: Math.max(map.getZoom(), zoom || 5.5), duration: 900 }); if (html) WF.popup(ll, html); };
  WF.fitBox = (bbox) => map.fitBounds(bbox, { padding: 70, maxZoom: 7, duration: 900 });

  // ---------- data -> map sources ----------
  const hex = (c) => c.slice(1).toLowerCase();
  const DAY = 24 * 3600e3;
  // A pin from one of the three other pin sources says so in its popup, with that source's credit (as Classic does).
  WF.eventPop = (p) => { const own = !p.source || p.source === "map";
    return pop(p.title || "Untitled pin", `${esc((WF.CATS[p.category] || WF.CATS.other)[0])} · ${esc(p.country_name || WF.tname(p.theatre) || "")}<br>${!p.ts_ms ? "No date" : WF.dayOnly(p) ? esc(WF.dayText(p.ts_ms)) + " (day only)" : esc(WF.when(p.ts_ms))}`,
      own ? "" : `<span class="m">From ${esc(WF.pinSrc(p))}${p.attribution ? " · " + esc(p.attribution) : ""}.${p.source_note ? " " + esc(p.source_note) : ""}</span>`,
      p.url, p.platform === "x" ? "Open the post" : "Open the source"); };
  WF.frontPop = (f) => { const k = WF.FRONT_KIND[f.kind], l = f.last;
    return pop(f.name, `${esc(k[0])} · ${esc(f.where || "")} · about ${nf(Math.round(f.km))} km`, `${esc(k[3])} <b>${nf(f.n24)}</b> pin${f.n24 === 1 ? "" : "s"} within ${WF.NEAR_KM} km in the last 24 h, <b>${nf(f.n72)}</b> in 72 h.${l ? ` Newest: “${esc(l.title)}” (${esc(WF.ago(l.ts_ms))}).` : ""}<br><span class="m">Drawn by the source map's curator. It moves only when they redraw it.</span>`); };
  const SETTERS = {
    events() {
      const feats = (WF.D.events || {}).features || [], now = Date.now();
      set("events", fc(feats.filter((f) => f.properties.kind === "event" && f.geometry && f.geometry.type === "Point").map((f) => {
        const p = f.properties, sev = (WF.CATS[p.category] || WF.CATS.other)[1], g = WF.glyphOf(p), age = now - (p.ts_ms || 0), col = WF.SEVHEX[sev];
        return pt(f.geometry.coordinates, { id: p.id, cat: p.category || "other", col, pin: g ? `pin-${g}-${hex(col)}` : "", o: age < DAY ? 1 : age < 3 * DAY ? 0.8 : 0.45,
          k: sev * 10 + (age < DAY ? 2 : age < 3 * DAY ? 1 : 0), h: WF.eventPop(p) });
      })));
      set("ovl", fc(feats.filter((f) => f.properties.kind === "overlay" && f.geometry && !WF.FRONT_KIND[WF.frontKind(f)]).map((f) => ({ type: "Feature", geometry: f.geometry,
        properties: { h: pop(f.properties.title || "Map overlay", `Drawn on the source map · ${esc(f.properties.overlay_type || "overlay")} · ${esc(f.properties.country_name || "")}`, esc(f.properties.note && f.properties.note !== "None" ? f.properties.note : "")) } }))));
      WF.FRONTS = WF.buildFronts();
      set("fronts", fc(WF.FRONTS.flatMap((f) => { const col = f.kind === "supposed" ? AMB : RED, h = WF.frontPop(f);
        return [{ type: "Feature", geometry: { type: "LineString", coordinates: f.cs }, properties: { id: f.id, kind: f.kind, col, h } }, pt(f.mid, { id: f.id, kind: f.kind, h })]; })));
    },
    front() {
      const fs = (((WF.D.front || {}).geojson || {}).features || []).filter((f) => /occup|CADR/i.test(f.properties.label || ""));
      set("ds", fc(fs.map((f) => ({ type: "Feature", geometry: f.geometry, properties: { h: pop(f.properties.label, "Occupied area, as DeepState maps it", `Updated ${esc((WF.D.front || {}).updated || "")}.`) } }))));
    },
    alerts() {
      const rs = (((WF.D.alerts || {}).regions || {}).regions || []), reg = WF.REG || new Map();
      const rank = (r) => (r.kind !== "alert" ? 0 : r.level === "red" ? 2 : 1);
      set("alertreg", fc(rs.filter((r) => reg.has(r.id)).sort((a, b) => rank(a) - rank(b)).map((r) => ({ type: "Feature", geometry: reg.get(r.id).geometry,
        properties: { level: r.kind === "alert" ? r.level || "red" : "", h: pop(r.en || r.name, r.kind === "alert" ? `Air-raid alert in force · ${esc(r.level || "")} · for ${esc(r.duration || "–")}` : r.kind === "launch" ? "Launch-site activity tracked here" : "Nominal warning (occupied territory)",
          `${esc((r.types || []).join(", "))}${r.since ? ". Since " + esc(WF.when(WF.ms(r.since))) : ""}`) } }))));
      const em = (WF.D.alerts || {}).embassy || {}, now = Date.now() / 1000;
      set("emb", fc((em.posts || []).map((p) => { const its = (em.items || []).filter((i) => (i.posts || []).includes(p.c) && now - i.t < 72 * 3600); return its.length && p.lon != null ? pt([p.lon, p.lat], { h: pop(`US Embassy, ${p.city || p.n}`, `${its.length} alert${its.length === 1 ? "" : "s"} in 72 h`, esc(its[0].title), its[0].url, "Open the alert") }) : null; }).filter(Boolean)));
    },
    mil() {
      set("mil", fc((((WF.D.mil || {}).geojson || {}).features || []).map((f) => { const p = f.properties, em = p.emergency && p.emergency !== "none";
        return pt(f.geometry.coordinates, { track: +p.track || 0, emerg: !!em, h: pop(p.tname || p.type || "Military aircraft", `${esc(p.owner || "Operator not known")} · ${esc(roleName(p.role))}`, `Callsign ${esc((p.flight || "").trim() || "–")} · ${p.alt === "ground" ? "on the ground" : nf(p.alt) + " ft"} · ${nf(Math.round(p.gs || 0))} kt${em ? ` · <b>emergency: ${esc(p.emergency)}</b>` : ""}`) }); })));
    },
    czib_geo() { set("czib", fc(((WF.D.czib_geo || {}).features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: { h: pop(f.properties.name, "Conflict-zone airspace warning (EASA)", `Valid until ${esc(f.properties.valid_until || "–")}.`) } })))); },
    tfr() { set("tfr", fc((((WF.D.tfr || {}).geojson || {}).features || []).filter((f) => f.properties.status !== "expired").map((f) => ({ type: "Feature", geometry: f.geometry, properties: { h: pop(f.properties.title || "Flight restriction", `US temporary flight restriction · ${esc(f.properties.type || "")} · ${esc(f.properties.status || "")}`, `${esc(f.properties.floor || "")} to ${esc(f.properties.ceiling || "")}.`, f.properties.url, "Open the FAA notice") } })))); },
    gpsjam() {
      const d = WF.D.gpsjam || {}, out = [];
      if (window.h3) (d.items || []).forEach(([h, level, good, bad]) => { if (level === "low") return; let ring; try { ring = window.h3.cellToBoundary(h, true); } catch (e) { return; }
        const xs = ring.map((c) => c[0]); if (Math.max(...xs) - Math.min(...xs) > 180) return;
        out.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: { level, h: pop(`GPS interference: ${level}`, `Day of ${esc(d.date || "")} (UTC)`, `${nf(bad)} of ${nf(good + bad)} aircraft here reported degraded GPS.`) } }); });
      set("gps", fc(out));
    },
    ships() {
      // 1.7.3: the amber mark is for a sanctioned (S) or shadow-fleet (G) ship only, the Classic theme's rule (web/app.js
      // isSG) and the rule behind the "on watch lists" counts under the map. A ship with only a port detention on record
      // (D, three in four of the list) was marked and worded as sanctioned; it now keeps its list line and nothing more.
      const d = WF.D.ships || {}, listed = new Map((d.listed || []).map((s) => [s.mmsi, s]));
      set("ships", fc((d.points || []).map(([lon, lat, sog, cog, cls, name, mmsi, ts, dest, hdg, flag]) => { const l = listed.get(mmsi), sg = !!l && /[SG]/.test(l.marks || "");
        return pt([lon, lat], { listed: sg, h: pop(name || "Ship, name not sent", `${esc(cls || "type not known")} · flag ${esc(flag || "–")}${sg ? " · <b>on a sanctions or shadow-fleet list</b>" : ""}`, `${nf(sog)} kt${dest ? " · bound for " + esc(dest) : ""}. Heard ${esc(WF.ago(WF.ms(ts)))}.${l ? " Lists: " + esc((l.lists || []).join(", ")) + "." : ""}`, l && l.url, "Open the list entry") }); })));
    },
    ukmto() {
      set("ukmto", fc(((WF.D.ukmto || {}).items || []).filter((i) => i.coord).map((i) => { const sev = /attack|hijack/i.test(i.type) ? 2 : /suspicious/i.test(i.type) ? 1 : 0;
        return pt(i.coord, { sev, pin: `pin-${sev === 2 ? "wreck" : "ship"}-${hex(WF.SEVHEX[sev])}`, h: pop(`${i.type}: ${i.where || "at sea"}`, `Maritime incident (UKMTO) #${esc(i.num)} · ${esc(i.date || "")}`, esc(String(i.text || "").slice(0, 320)) + (String(i.text || "").length > 320 ? "…" : ""), i.url, "Open the UKMTO notice") }); })));
    },
    portwatch() {
      set("pw", fc(((WF.D.portwatch || {}).chokepoints || []).filter((c) => c.lon != null && c.lat != null).map((c) => { const ch = (c.change_vs_year_pct || {}).total, col = ch == null ? PALE : ch <= -50 ? RED : ch <= -20 ? AMB : GRN;
        return pt([c.lon, c.lat], { col, r: Math.max(5, Math.min(16, 4 + Math.sqrt((c.avg7 || {}).total || 0))), h: pop(c.name, `Chokepoint · ships a day, 7-day average, through ${esc(c.last_day || "")}`, `<b>${nf((c.avg7 || {}).total)}</b> ships a day now, <b>${nf((c.year_ago7 || {}).total)}</b> a year ago${ch == null ? "" : ` (${ch > 0 ? "+" : ""}${nf(ch)}%)`}. Tankers: ${nf((c.avg7 || {}).tanker)} against ${nf((c.year_ago7 || {}).tanker)}.`) }); })));
    },
    outages_geo() { set("outages", fc(((WF.D.outages_geo || {}).features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: { ongoing: !!f.properties.ongoing, watched: !!f.properties.watched,
      h: pop(f.properties.name, `Internet outage · ${f.properties.ongoing ? "ongoing" : "ended"}${f.properties.watched ? " · watched country" : ""}`, `Last seen ${esc(WF.ago(WF.ms(f.properties.last)))}. Automatic detection, last 72 h.`) } })))); },
    infra() {
      const out = [];
      [["power", "Power"], ["cellular", "Mobile network"], ["websites", "Website or service"], ["cloud", "Cloud or AI service"]].forEach(([n, label]) => ((WF.D[n] || {}).items || []).forEach((i) => {
        if (!i.active || !i.ll) return; const big = /major|critical/i.test(i.severity || "");
        out.push(pt(i.ll, { big, col: big ? RED : AMB, h: pop(i.title, `${label} · ${esc(i.provider || "")} · ${esc(i.severity || "")} · ${esc(i.status || "")}`, esc(String(i.summary || "").slice(0, 260)), i.url) })); }));
      set("infra", fc(out));
    },
    quakes() { set("quakes", fc((((WF.D.quakes || {}).geojson || {}).features || []).map((f) => { const p = f.properties, col = p.mag >= 6.5 ? RED : p.watch ? AMB : PALE;
      return pt(f.geometry.coordinates, { col, r: Math.max(3, (p.mag - 3) * 3.2), h: pop(`M${p.mag} · ${p.place || ""}`, `${esc(p.kind || "earthquake")} · ${nf(p.depth_km)} km deep · ${esc(WF.when(WF.ms(p.time)))}`, esc(p.watch ? "On watch: " + (p.watch_reason || "") : ""), p.url) }); }))); },
    hazards() { set("hazards", fc((((WF.D.hazards || {}).geojson || {}).features || []).filter((f) => f.properties.type !== "EQ").map((f) => { const p = f.properties, col = p.alert === "Red" ? RED : p.alert === "Orange" ? AMB : PALE;
      return pt(f.geometry.coordinates, { col, r: p.alert === "Green" ? 3.5 : 7, h: pop(`${p.type_label}: ${p.country_name || p.gdacs_country || ""}`, `Disaster alert (GDACS) · ${esc(p.alert)} · ${p.current ? "current" : "ended"}`, esc(p.severity || ""), p.url, "Open the GDACS report") }); }))); },
    advisories_geo() { set("adv", fc(((WF.D.advisories_geo || {}).features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: { level: f.properties.level, h: pop(f.properties.country, `US travel advisory · level ${esc(f.properties.level)}: ${esc(f.properties.label || "")}`, `Dated ${esc(f.properties.date || "")}.`, f.properties.url, "Open the advisory") } })))); },
  };
  ["power", "cellular", "websites", "cloud"].forEach((n) => { SETTERS[n] = SETTERS.infra; });
  WF.roleShort = (r) => ({ isr: "Surveillance", tanker: "Tankers", transport: "Transport", jet: "Fast jets", helicopter: "Helicopters", tiltrotor: "Tilt-rotors", light: "Light aircraft", drone: "Drones", other: "Other" }[r] || r || "Other");
  const roleName = (WF.roleName = (r) => ({ isr: "Surveillance and reconnaissance", tanker: "Refuelling tanker", transport: "Transport", jet: "Fast jet", helicopter: "Helicopter", tiltrotor: "Tilt-rotor", light: "Light aircraft", drone: "Drone", other: "Other" }[r] || r || "Other"));
  WF.mapData = (name) => { if (SETTERS[name]) try { SETTERS[name](); } catch (e) { console.error("map data " + name, e); } };

  // region shapes for the air-raid alert areas (ISO 3166-2 code -> shape), a static file beside the page (the same
  // URL the Classic theme asks for, so the browser keeps one copy)
  fetch("geo/alert-regions.json?v=0.7.0").then((r) => r.json()).then((g) => { WF.REG = new Map(g.features.map((f) => [f.id, f])); if (WF.D.alerts) SETTERS.alerts(); }).catch(() => {});
})();
