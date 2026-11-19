/* Ground Truth v0.9 - watch floor client. All API paths are relative so the app runs behind a prefix.
   0.7.0: air-raid and missile alerts (Israel: Tzeva Adom; Ukraine, Russia, Poland: alerts.in.ua), Alerts tab, siren banner.
   0.8.0: US embassy alerts (38 posts' own feeds): map rings, popups, an Alerts-tab card, banner rows for shelter/departure.
   0.9.0: tankers: heading arrows, 3-hour tracks, Tankers / Cargo / Other filter, flag, IMO, draught; rings for ships on
   sanctions, shadow-fleet and detention lists (OpenSanctions); IMF PortWatch chokepoint transits (map, popup, table). */
(() => {
  "use strict";
  const THEATRES = {
    "global": ["Global", "#e4e7ea", [-20, 18, 4]],
    "ukraine-russia": ["Ukraine – Russia", "#5aa7ff", [36.5, 49.2, 5.2]],
    "middle-east": ["Middle East / Gulf", "#f2a33a", [50.5, 27.5, 4.6]],
    "europe-nato": ["Europe / NATO", "#a98bff", [15, 54, 3.8]],
    "americas": ["Americas / US", "#3ecf8e", [-85, 33, 3.2]],
    "indo-pacific": ["Indo-Pacific", "#f472b6", [125, 27, 3.8]],
    "south-asia": ["South & Central Asia", "#2dd4bf", [70, 30, 4]],
    "africa": ["Africa", "#e5c84b", [20, 8, 3]],
  };
  const CATS = {
    strike: ["Strike / explosion", "#f05252"], energy: ["Energy / infrastructure", "#f59e0b"],
    missile: ["Missile / air defence", "#e879f9"], drone: ["Drone", "#a3e635"], maritime: ["Maritime", "#38bdf8"],
    alert: ["Alert / force posture", "#fde047"], cyber: ["Comms / outage", "#2dd4bf"], security: ["Security incident", "#c084fc"],
    casualty: ["Casualties", "#fb7185"], forces: ["Forces / equipment", "#94a3b8"], aviation: ["Aviation", "#93c5fd"],
    political: ["Political / statement", "#818cf8"], report: ["Report", "#9ca3af"], other: ["Other", "#6b7280"],
  };
  const UKMTO_COL = { Attack: "#f05252", "Suspicious Activity": "#f59e0b", Advisory: "#38bdf8", Hijack: "#c084fc" };
  const S = { theatre: "global", cats: new Set(Object.keys(CATS)), q: "", hours: 0, brush: null,
              events: null, feeds: {}, status: {}, summary: {}, sel: null, ai: { ov: null, ev: {} }, alerts: null };
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const api = (p) => fetch("api/" + p, { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));
  const fmtT = (ms) => new Date(ms).toISOString().slice(11, 16) + "Z";
  const fmtD = (ms) => new Date(ms).toISOString().slice(5, 10).replace("-", "/");
  const ago = (ms) => { const m = Math.round((Date.now() - ms) / 60000); return m < 60 ? m + "m ago" : m < 2880 ? Math.round(m / 60) + "h ago" : Math.round(m / 1440) + "d ago"; };
  const nf = (n) => (n == null ? "–" : Number(n).toLocaleString("en-US"));

  // ---------- map ----------
  const map = new maplibregl.Map({
    container: "map", attributionControl: { compact: true }, center: [30, 35], zoom: 2.4, maxPitch: 0, dragRotate: false,
    style: {
      version: 8,
      glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
      sources: {
        base: { type: "raster", tileSize: 256, maxzoom: 16, attribution: "Basemap © Esri",
          tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"] },
        ref: { type: "raster", tileSize: 256, maxzoom: 16,
          tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"] },
      },
      layers: [
        { id: "bg", type: "background", paint: { "background-color": "#0d0f11" } },
        { id: "base", type: "raster", source: "base", paint: { "raster-brightness-max": 0.85, "raster-saturation": -0.4 } },
      ],
    },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

  const empty = { type: "FeatureCollection", features: [] };
  const LAYERS = [
    // key, label, feed for status, default on
    ["events", "Curated events (source map)", "mymaps", true],
    ["overlays", "Map overlays: fronts, lanes, zones", "mymaps", true],
    ["front", "DeepState front line", "front", true],
    ["alerts", "Air-raid alerts: UA, RU, PL (live)", "airalerts", true],
    ["israel", "Israel sirens (Tzeva Adom, live)", "tzevalive", true],
    ["embassy", "US embassy alerts (7 days)", "embassy", true],
    ["thermal", "NASA thermal anomalies (24h)", "firms", true],
    ["ukmto", "UKMTO maritime incidents", "ukmto", true],
    ["mil", "Military aircraft (ADS-B)", "mil", true],
    ["ships", "Ships (AIS, last hour)", "ships", true],
    ["choke", "Chokepoint transits (IMF PortWatch, ~3 days behind)", "portwatch", true],
    ["gfw", "Ship traffic (GFW, ~4 days behind)", "gfw", true],
    ["outages", "Internet outages (IODA, 72h)", "outages", true],
    ["advisories", "US travel advisories (Level 3–4)", "advisories", false],
    ["gdelt", "GDELT conflict signal (2h)", "gdelt", false],
    ["czib", "EASA conflict-zone airspace", "czib", false],
    ["cables", "Submarine cables", "cables", false],
  ];
  const GROUPS = {
    events: ["ev-halo", "ev-pt", "ev-label"], overlays: ["ov-fill", "ov-line", "ov-border", "ov-lane"], front: ["front-fill", "front-line"],
    thermal: ["th-pt"], ukmto: ["uk-pt"], mil: ["mil-pt", "mil-label"], gdelt: ["gd-pt"], czib: ["cz-fill", "cz-line"], cables: ["cab-line"],
    ships: ["ship-trk", "ship-pt", "ship-arrow", "ship-listed", "ais-nocov", "ais-nocov-label"], choke: ["pw-pt", "pw-label"], outages: ["out-fill", "out-line"], advisories: ["adv-fill", "adv-line"], gfw: ["gfw-fill", "gfw-line", "gfw-gap"],
    alerts: ["ar-fill", "ar-line", "ar-dash"], israel: ["il-fill", "il-line", "il-halo", "il-pt", "il-label"],
    embassy: ["em-pt", "em-label"],
  };
  // Click priority, top first; the same list sets the pointer cursor. Region fills are huge, so they come late.
  const CLICK_ORDER = ["ev-pt", "il-pt", "em-pt", "uk-pt", "mil-pt", "ship-listed", "ship-arrow", "ship-pt", "pw-pt", "gfw-gap", "th-pt", "gd-pt", "ov-line", "ov-border", "ov-lane", "il-fill",
    "ov-fill", "cz-fill", "ar-fill", "front-fill", "out-fill", "gfw-fill", "adv-fill"];
  const SHIP_COL = { tanker: "#f2b33d", cargo: "#38bdf8", military: "#f05252", passenger: "#a3e635", fishing: "#2dd4bf", tug: "#9aa4ae", service: "#9aa4ae", other: "#c9ced4", unknown: "#c9ced4" };
  // Global Fishing Watch data is CC BY-NC 4.0: this attribution must appear wherever it is shown.
  const GFW_ATTR = `<a href="https://globalfishingwatch.org" target="_blank" rel="noopener">Powered by Global Fishing Watch</a>`;
  const GFW_COL = ["case", ["!", ["has", "chg"]], "#9aa4ae", ["<=", ["get", "chg"], -50], "#f05252", ["<=", ["get", "chg"], -20], "#f2b33d", [">=", ["get", "chg"], 20], "#38bdf8", "#9aa4ae"];
  const gfwCol = (c) => (c == null ? "#9aa4ae" : c <= -50 ? "#f05252" : c <= -20 ? "#f2b33d" : c >= 20 ? "#38bdf8" : "#9aa4ae");
  // 0.9.0 shipping. PortWatch (IMF) wants this citation wherever its data is shown; OpenSanctions is CC BY-NC 4.0.
  const PW_ATTR = `<a href="https://portwatch.imf.org" target="_blank" rel="noopener">Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)</a>`;
  const OS_ATTR = `Vessel lists: <a href="https://www.opensanctions.org/datasets/maritime/" target="_blank" rel="noopener">OpenSanctions</a> (CC BY-NC 4.0), from OFAC, EU, UK, GUR and others`;
  const MARK = { S: ["Sanctioned", "#f05252"], G: ["Shadow fleet (GUR list)", "#fb923c"], D: ["Detained (port state control)", "#f2b33d"] };
  // Rings only for sanctioned (S) or shadow-fleet-listed (G) ships: a port-state detention (D) alone is common (7,000+ ships)
  // and is usually a safety defect, so it shows in popups and lists, not as a ring.
  const SG_FILTER = ["any", ["in", "S", ["get", "marks"]], ["in", "G", ["get", "marks"]]];
  const isSG = (m) => /[SG]/.test(m || "");
  const SHIP_GRPS = [["tanker", "Tankers"], ["cargo", "Cargo"], ["other", "Other"]];
  const shipGrp = (cls) => (cls === "tanker" || cls === "cargo" ? cls : "other");
  const AREA_NAME = (k) => (((S.feeds.ships || {}).areas || {})[k] || {}).label || String(k).replace(/_/g, " ");
  let REGION_NAMES = null;
  const regionName = (iso2) => {
    if (!iso2) return "";
    try { REGION_NAMES = REGION_NAMES || new Intl.DisplayNames(["en"], { type: "region" }); return REGION_NAMES.of(iso2) || iso2; } catch (e) { return iso2; }
  };
  const markBadges = (m) => [...(m || "")].map((c) => MARK[c] ? `<span class="badge mk" style="border-color:${MARK[c][1]};color:${MARK[c][1]}">${esc(MARK[c][0])}</span>` : "").join(" ");
  const IODA_SRC = { bgp: "routing (BGP)", "ping-slash24": "active probing", "merit-nt": "darknet traffic", gtr: "Google traffic" };

  // ---------- military aircraft: silhouettes by role (48-unit box, nose up, rotated by track on the map) ----------
  const AC_ROLES = { fighter: "fighter / attack", bomber: "bomber", tanker: "tanker", transport: "transport", isr: "ISR / patrol / AEW",
    helicopter: "helicopter", tiltrotor: "tiltrotor", drone: "drone", jet: "VIP / airliner / bizjet", light: "trainer / light", other: "type unknown" };
  const AC_SHORT = { fighter: "fighter", bomber: "bomber", tanker: "tanker", transport: "transport", isr: "ISR", helicopter: "heli",
    tiltrotor: "tiltrotor", drone: "drone", jet: "VIP/jet", light: "light", other: "unknown" };
  const AC_COL = { tanker: "#38bdf8", isr: "#f2b33d", drone: "#f2b33d", bomber: "#c084fc" }, AC_BASE = "#e8ecf0", AC_EMERG = "#f05252";
  const RING = (cx, cy, r) => `M${cx + r} ${cy} A${r} ${r} 0 1 1 ${cx - r} ${cy} A${r} ${r} 0 1 1 ${cx + r} ${cy}`;
  const JET = "M22.5 5Q24 1 25.5 5L25.5 41Q24 44 22.5 41Z M25.5 18L43 29L43 31.5L25.5 25Z M22.5 18L5 29L5 31.5L22.5 25Z M25.5 37L32 42L32 44L25.5 41.5Z M22.5 37L16 42L16 44L22.5 41.5Z";
  const AC_SHAPES = {
    fighter: { fill: "M24 2L26.5 14L41 30L41 33L27 31L27.5 39L33 44L33 46L24 44L15 46L15 44L20.5 39L21 31L7 33L7 30L21.5 14Z" },
    bomber: { fill: "M22.5 4Q24 1 25.5 4L25.5 42L22.5 42Z M25 15L46 30L46 33L25 25Z M23 15L2 30L2 33L23 25Z M25 37L33 43L33 45L25 42Z M23 37L15 43L15 45L23 42Z" },
    transport: { fill: "M21 6Q24 1 27 6L27 40Q24 44 21 40Z M27 17L45 24L45 27L27 23Z M21 17L3 24L3 27L21 23Z M27 38L34 42L34 44.5L27 42Z M21 38L14 42L14 44.5L21 42Z" },
    jet: { fill: JET },
    tanker: { fill: JET + " M23.2 41L24.8 41L24.8 47.5L23.2 47.5Z M24 44.5L28.5 46.6L28.5 47.8L24 46.2Z M24 44.5L19.5 46.6L19.5 47.8L24 46.2Z" },
    isr: { fill: JET, stroke: [[RING(24, 27, 6.5), 2.6]] },
    helicopter: { fill: "M24 11Q29 11 29 20Q29 29 24 30Q19 29 19 20Q19 11 24 11Z M23 28L25 28L25 44L23 44Z M19 41L29 41L29 43.4L19 43.4Z",
      stroke: [[RING(24, 20, 17), 1.8], ["M12 8L36 32 M36 8L12 32", 2]] },
    tiltrotor: { fill: "M22 6Q24 2 26 6L26 40L22 40Z M8 18L40 18L40 22L8 22Z M17 37L31 37L31 40.5L17 40.5Z", stroke: [[RING(8, 20, 7.5), 2], [RING(40, 20, 7.5), 2]] },
    drone: { fill: "M23 8Q24 4 25 8L25 38L23 38Z M2 19L46 19L46 22L2 22Z M25 35L31 41L30 42.5L24.5 37.5Z M23 35L17 41L18 42.5L23.5 37.5Z" },
    light: { fill: "M22.5 9Q24 6 25.5 9L25 38L23 38Z M8 18L40 18L40 23L8 23Z M18 35L30 35L30 38L18 38Z M18 6L30 6L30 7.6L18 7.6Z" },
    other: { fill: "M24 3L39 43L24 35L9 43Z" },
  };
  function drawAircraft(role, col, px) {
    const c = document.createElement("canvas"), sh = AC_SHAPES[role] || AC_SHAPES.other, k = px / 48;
    c.width = c.height = px;
    const g = c.getContext("2d"); g.scale(k, k); g.lineJoin = "round";
    const body = new Path2D(sh.fill);
    g.strokeStyle = "#0d0f11"; g.lineWidth = 2.4; g.stroke(body);                         // dark edge, readable over busy layers
    (sh.stroke || []).forEach(([d, w]) => { g.lineWidth = w + 2.4; g.stroke(new Path2D(d)); });
    g.fillStyle = col; g.fill(body); g.strokeStyle = col;
    (sh.stroke || []).forEach(([d, w]) => { g.lineWidth = w; g.stroke(new Path2D(d)); });
    return c;
  }
  const acCol = (role) => AC_COL[role] || AC_BASE;
  const AC_URL = Object.fromEntries(Object.keys(AC_ROLES).map((r) => [r, drawAircraft(r, acCol(r), 48).toDataURL()]));
  const acIcon = (role) => `<img class="acico" src="${AC_URL[role] || AC_URL.other}" alt="">`;
  function addShipImages() {
    const c = drawAircraft("other", SHIP_COL.tanker, 96); // the plain arrow, in tanker gold
    map.addImage("ship-tanker", { width: 96, height: 96, data: c.getContext("2d").getImageData(0, 0, 96, 96).data }, { pixelRatio: 2 });
  }
  function addAircraftImages() {
    Object.keys(AC_ROLES).forEach((r) => [["", acCol(r)], ["-e", AC_EMERG]].forEach(([sfx, col]) => {
      const c = drawAircraft(r, col, 96);
      map.addImage("ac-" + r + sfx, { width: 96, height: 96, data: c.getContext("2d").getImageData(0, 0, 96, 96).data }, { pixelRatio: 2 });
    }));
  }
  // Planespotters photo API, asked by the browser: their terms want server clients to send a contact address, and the
  // image must load from their CDN into the viewer's browser, unchanged, credited, the thumbnail linking to its photo page.
  const PHOTOS = new Map(); // hex -> Promise<html>, this session only (their terms allow caching answers for 24 h)
  const PS_IMG = /^https:\/\/[a-z0-9.-]+\.(plnspttrs|planespotters)\.net\//i, PS_LINK = /^https:\/\/www\.planespotters\.net\//i;
  const noPhoto = () => `<span class="muted small">No photo of this airframe on Planespotters.</span>`;
  function acPhoto(hex, reg) {
    if (!/^[0-9a-f]{6}$/i.test(hex)) return Promise.resolve(noPhoto());
    if (!PHOTOS.has(hex)) PHOTOS.set(hex, (async () => {
      const get = async (path) => {
        const r = await fetch("https://api.planespotters.net/pub/photos/" + path);
        if (!r.ok) throw new Error("HTTP " + r.status);
        return (await r.json()).photos || [];
      };
      let ph = await get("hex/" + hex);
      if (!ph.length && reg && reg.length >= 4 && /[A-Z]/i.test(reg)) ph = await get("reg/" + encodeURIComponent(reg));
      const x = ph[0], img = x && (x.thumbnail_large || x.thumbnail);
      if (!img || !PS_IMG.test(img.src || "") || !PS_LINK.test(x.link || "")) return noPhoto();
      return `<a href="${esc(x.link)}" target="_blank"><img src="${esc(img.src)}" alt="Photo of ${esc(reg || hex)}"></a>` +
        `<div class="muted small">Photo: ${esc(x.photographer || "unknown")} · <a href="${esc(x.link)}" target="_blank">Planespotters.net</a></div>`;
    })().catch(() => { PHOTOS.delete(hex); return `<span class="muted small">Photo lookup failed (Planespotters unreachable).</span>`; }));
    return PHOTOS.get(hex);
  }

  map.on("load", () => {
    addAircraftImages(); addShipImages();
    ["cables", "advisories", "outages", "gfw", "czib", "front", "alertreg", "ilarea", "overlays", "gdelt", "thermal", "gfwgap", "aisbox", "pw", "shiptrk", "ships", "ukmto", "events", "mil", "embpt", "ilpt"].forEach((id) => map.addSource(id, { type: "geojson", data: empty }));
    map.addLayer({ id: "cab-line", type: "line", source: "cables", layout: { visibility: "none" }, paint: { "line-color": "#22d3ee", "line-opacity": 0.28, "line-width": 0.8 } });
    map.addLayer({ id: "adv-fill", type: "fill", source: "advisories", layout: { visibility: "none" }, paint: { "fill-color": ["match", ["get", "level"], 4, "#f05252", "#f2853d"], "fill-opacity": ["match", ["get", "level"], 4, 0.12, 0.07] } });
    map.addLayer({ id: "adv-line", type: "line", source: "advisories", layout: { visibility: "none" }, paint: { "line-color": ["match", ["get", "level"], 4, "#f05252", "#f2853d"], "line-opacity": 0.5, "line-width": 0.8, "line-dasharray": [3, 3] } });
    map.addLayer({ id: "out-fill", type: "fill", source: "outages", paint: { "fill-color": "#a78bfa", "fill-opacity": ["case", ["get", "ongoing"], 0.3, ["get", "watched"], 0.18, 0.07] } });
    map.addLayer({ id: "out-line", type: "line", source: "outages", paint: { "line-color": "#a78bfa", "line-opacity": ["case", ["any", ["get", "ongoing"], ["get", "watched"]], 0.8, 0.3], "line-width": ["case", ["get", "ongoing"], 1.6, 0.8] } });
    map.addLayer({ id: "gfw-fill", type: "fill", source: "gfw", paint: { "fill-color": GFW_COL, "fill-opacity": ["case", ["==", ["get", "kind"], "chokepoint"], 0.22, 0.06] } });
    map.addLayer({ id: "gfw-line", type: "line", source: "gfw", paint: { "line-color": GFW_COL, "line-opacity": 0.75, "line-width": ["case", ["==", ["get", "kind"], "chokepoint"], 1.8, 1], "line-dasharray": [4, 2] } });
    map.addLayer({ id: "cz-fill", type: "fill", source: "czib", layout: { visibility: "none" }, paint: { "fill-color": "#f2b33d", "fill-opacity": 0.07 } });
    map.addLayer({ id: "cz-line", type: "line", source: "czib", layout: { visibility: "none" }, paint: { "line-color": "#f2b33d", "line-opacity": 0.6, "line-width": 1, "line-dasharray": [2, 2] } });
    map.addLayer({ id: "front-fill", type: "fill", source: "front", paint: { "fill-color": ["get", "fill"], "fill-opacity": ["*", 0.75, ["get", "fill_opacity"]] } });
    map.addLayer({ id: "front-line", type: "line", source: "front", paint: { "line-color": ["get", "stroke"], "line-opacity": 0.55, "line-width": 0.7 } });
    // 0.7.0 alerts, under the place-name layer so names stay readable
    map.addLayer({ id: "ar-fill", type: "fill", source: "alertreg", paint: { "fill-color": ["get", "col"],
      "fill-opacity": ["match", ["get", "kind"], "alert", ["match", ["get", "level"], "red", 0.3, 0.2], 0.07] } });
    map.addLayer({ id: "ar-line", type: "line", source: "alertreg", filter: ["==", ["get", "kind"], "alert"], paint: { "line-color": ["get", "col"], "line-opacity": 0.9, "line-width": 1.3 } });
    map.addLayer({ id: "ar-dash", type: "line", source: "alertreg", filter: ["!=", ["get", "kind"], "alert"], paint: { "line-color": ["get", "col"], "line-opacity": 0.8, "line-width": 1, "line-dasharray": [3, 2] } });
    map.addLayer({ id: "il-fill", type: "fill", source: "ilarea", layout: { "fill-sort-key": ["get", "rank"] }, paint: { "fill-color": ["get", "col"],
      "fill-opacity": ["match", ["get", "st"], "siren", 0.5, "early", 0.3, "shelter", 0.35, 0.18] } });
    map.addLayer({ id: "il-line", type: "line", source: "ilarea", paint: { "line-color": ["get", "col"], "line-opacity": 0.9, "line-width": 0.8 } });
    map.addLayer({ id: "base-ref", type: "raster", source: "ref", paint: { "raster-opacity": 0.75 } });
    map.addLayer({ id: "ov-fill", type: "fill", source: "overlays", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": ["coalesce", ["get", "stroke"], "#999"], "fill-opacity": ["*", 0.6, ["coalesce", ["get", "fill_opacity"], 0.3]] } });
    const lineOf = ["==", ["geometry-type"], "LineString"];
    map.addLayer({ id: "ov-line", type: "line", source: "overlays", filter: ["all", lineOf, ["!", ["in", ["get", "overlay_type"], ["literal", ["border", "lane"]]]]], paint: {
      "line-color": ["match", ["get", "overlay_type"], "frontline", "#ff5b5b", ["coalesce", ["get", "stroke"], "#aaa"]],
      "line-width": ["match", ["get", "overlay_type"], "frontline", 2.2, 1.2], "line-opacity": 0.9 } });
    map.addLayer({ id: "ov-border", type: "line", source: "overlays", filter: ["all", lineOf, ["==", ["get", "overlay_type"], "border"]],
      paint: { "line-color": "#4f8cff", "line-width": 1.6, "line-dasharray": [3, 2], "line-opacity": 0.9 } });
    map.addLayer({ id: "ov-lane", type: "line", source: "overlays", filter: ["all", lineOf, ["==", ["get", "overlay_type"], "lane"]],
      paint: { "line-color": "#b48cff", "line-width": 1.8, "line-dasharray": [1, 1.5], "line-opacity": 0.95 } });
    map.addLayer({ id: "gd-pt", type: "circle", source: "gdelt", layout: { visibility: "none" }, paint: { "circle-radius": 2.6, "circle-color": "#d7dbe0", "circle-opacity": 0.4 } });
    map.addLayer({ id: "th-pt", type: "circle", source: "thermal", paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "frp"], 0, 1.4, 50, 3, 300, 6], "circle-color": "#ff7a1a",
      "circle-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.45, 7, 0.85], "circle-blur": 0.3 } });
    map.addLayer({ id: "gfw-gap", type: "circle", source: "gfwgap", paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3.5, 8, 6], "circle-color": "#0d0f11", "circle-stroke-color": "#fb923c", "circle-stroke-width": 2 } });
    // 0.9.0: AIS boxes with no live receivers get a dashed outline and a note, so an empty map isn't read as empty seas
    map.addLayer({ id: "ais-nocov", type: "line", source: "aisbox", filter: ["==", ["geometry-type"], "Polygon"], paint: {
      "line-color": "#9aa4ae", "line-opacity": 0.5, "line-width": 1, "line-dasharray": [2, 3] } });
    map.addLayer({ id: "ais-nocov-label", type: "symbol", source: "aisbox", minzoom: 3.6, filter: ["==", ["geometry-type"], "Point"], layout: {
      "text-field": ["get", "note"], "text-size": 10.5, "text-max-width": 14, "text-optional": true, "text-font": ["Open Sans Regular"] },
      paint: { "text-color": "#aeb6bf", "text-halo-color": "#0d0f11", "text-halo-width": 1.3 } });
    // IMF PortWatch chokepoints: sized by tankers a day (7-day mean), coloured by the change against the same week a year ago
    map.addLayer({ id: "pw-pt", type: "circle", source: "pw", paint: {
      "circle-radius": ["interpolate", ["linear"], ["sqrt", ["get", "t7"]], 0, 4, 3, 7, 10, 13], "circle-color": GFW_COL, "circle-opacity": 0.85,
      "circle-stroke-color": "#0d0f11", "circle-stroke-width": 1.6 } });
    map.addLayer({ id: "pw-label", type: "symbol", source: "pw", minzoom: 3.4, layout: {
      "text-field": ["get", "lbl"], "text-size": 10.5, "text-offset": [0, 1.3], "text-anchor": "top", "text-max-width": 12, "text-optional": true, "text-font": ["Open Sans Regular"] },
      paint: { "text-color": "#cfd5db", "text-halo-color": "#0d0f11", "text-halo-width": 1.3 } });
    map.addLayer({ id: "ship-trk", type: "line", source: "shiptrk", paint: {
      "line-color": SHIP_COL.tanker, "line-opacity": 0.4, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.6, 8, 1.6] } });
    map.addLayer({ id: "ship-pt", type: "circle", source: "ships", filter: ["!", ["get", "arrow"]], paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, ["case", ["==", ["get", "cls"], "tanker"], 2, 1.4], 6, ["case", ["==", ["get", "cls"], "tanker"], 3.4, 2.6], 10, 4.5],
      "circle-color": ["get", "col"],
      "circle-opacity": ["case", ["get", "moving"], 0.85, 0.45], "circle-stroke-width": 0 } });
    map.addLayer({ id: "ship-arrow", type: "symbol", source: "ships", filter: ["get", "arrow"], layout: {
      "icon-image": "ship-tanker", "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.2, 6, 0.3, 10, 0.44], "icon-rotate": ["get", "rot"],
      "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true } });
    map.addLayer({ id: "ship-listed", type: "circle", source: "ships", filter: SG_FILTER, paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 4, 6, 6.5, 10, 9], "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": ["match", ["slice", ["get", "marks"], 0, 1], "S", MARK.S[1], "G", MARK.G[1], MARK.D[1]], "circle-stroke-width": 1.8 } });
    applyShipFilter();
    map.addLayer({ id: "uk-pt", type: "circle", source: "ukmto", paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3.5, 8, 7], "circle-color": "#0d0f11",
      "circle-stroke-color": ["coalesce", ["get", "col"], "#38bdf8"], "circle-stroke-width": 2, "circle-opacity": ["get", "op"], "circle-stroke-opacity": ["get", "op"] } });
    map.addLayer({ id: "ev-halo", type: "circle", source: "events", filter: ["==", ["get", "recent"], true], paint: {
      "circle-radius": 14, "circle-color": ["get", "col"], "circle-opacity": 0.18, "circle-blur": 0.6 } });
    map.addLayer({ id: "ev-pt", type: "circle", source: "events", paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 3.6, 6, 6, 10, 8], "circle-color": ["get", "col"],
      "circle-stroke-color": ["case", ["has", "thermal"], "#ff7a1a", "#0d0f11"], "circle-stroke-width": ["case", ["has", "thermal"], 2.6, 1.2],
      "circle-opacity": ["case", ["get", "est"], 0.75, 1] } });
    map.addLayer({ id: "ev-label", type: "symbol", source: "events", minzoom: 5.5, layout: {
      "text-field": ["get", "title"], "text-size": 11, "text-offset": [0, 1.1], "text-anchor": "top", "text-max-width": 12, "text-font": ["Open Sans Regular"] },
      paint: { "text-color": "#cfd5db", "text-halo-color": "#0d0f11", "text-halo-width": 1.4 } });
    map.addLayer({ id: "mil-pt", type: "symbol", source: "mil", layout: {
      "icon-image": ["concat", "ac-", ["coalesce", ["get", "role"], "other"], ["case", ["to-boolean", ["get", "emerg"]], "-e", ""]],
      "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.36, 6, 0.5, 9, 0.66], "icon-rotate": ["get", "track"],
      "icon-rotation-alignment": "map", "icon-allow-overlap": true },
      paint: { "icon-opacity": 0.95 } });
    map.addLayer({ id: "mil-label", type: "symbol", source: "mil", minzoom: 5, layout: {
      "text-field": ["coalesce", ["get", "flight"], ["get", "type"]], "text-size": 10, "text-offset": [0, 1.2], "text-anchor": "top", "text-font": ["Open Sans Regular"] },
      paint: { "text-color": "#aeb6bf", "text-halo-color": "#0d0f11", "text-halo-width": 1.2 } });
    // 0.8.0 US embassy alerts: rings (not dots), so they never read as sirens
    map.addLayer({ id: "em-pt", type: "circle", source: "embpt", layout: { "circle-sort-key": ["get", "rank"] }, paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 4, 6, 6.5, 10, 8.5], "circle-color": "#0d0f11", "circle-opacity": ["get", "op"],
      "circle-stroke-color": ["get", "col"], "circle-stroke-width": 2.2, "circle-stroke-opacity": ["get", "op"] } });
    map.addLayer({ id: "em-label", type: "symbol", source: "embpt", minzoom: 4.5, layout: {
      "text-field": ["get", "city"], "text-size": 10.5, "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true, "text-font": ["Open Sans Regular"] },
      paint: { "text-color": "#cfd5db", "text-halo-color": "#0d0f11", "text-halo-width": 1.3 } });
    // Israel sirens on top of everything: they are the most time-critical marks on the map
    map.addLayer({ id: "il-halo", type: "circle", source: "ilpt", filter: ["==", ["get", "st"], "siren"], paint: {
      "circle-radius": 12, "circle-color": IL_COL.siren, "circle-opacity": 0.3, "circle-blur": 0.35 } });
    map.addLayer({ id: "il-pt", type: "circle", source: "ilpt", layout: { "circle-sort-key": ["get", "rank"] }, paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, ["match", ["get", "st"], "recent", 2, 3.4], 9, ["match", ["get", "st"], "recent", 3.6, 6.5]],
      "circle-color": ["get", "col"], "circle-opacity": ["case", ["get", "fresh"], 1, 0.55],
      "circle-stroke-color": "#0d0f11", "circle-stroke-width": 1 } });
    map.addLayer({ id: "il-label", type: "symbol", source: "ilpt", minzoom: 7.5, filter: ["!=", ["get", "st"], "recent"], layout: {
      "text-field": ["get", "n"], "text-size": 10.5, "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true, "text-font": ["Open Sans Regular"] },
      paint: { "text-color": "#e4e7ea", "text-halo-color": "#0d0f11", "text-halo-width": 1.3 } });

    CLICK_ORDER.forEach((l) => {
      map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
    });
    map.on("click", (e) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: CLICK_ORDER.filter((l) => map.getLayer(l) && map.getLayoutProperty(l, "visibility") !== "none") });
      if (!hits.length) return;
      hits.sort((a, b) => CLICK_ORDER.indexOf(a.layer.id) - CLICK_ORDER.indexOf(b.layer.id));
      popupFor(hits[0], e.lngLat);
    });
    buildRail();
    loadAll();
    setInterval(loadLive, 45000);
    setInterval(loadAll, 5 * 60000);
    REG_GEO.finally(loadAlerts);
    setInterval(loadAlerts, AL_POLL);
    setInterval(() => renderIsrael(false), 2000); // siren -> shelter -> recent happens on the clock, between polls
  });

  // ---------- popups ----------
  let popup = null;
  function showPopup(lngLat, html) {
    if (popup) popup.remove();
    popup = new maplibregl.Popup({ maxWidth: "360px", offset: 10 }).setLngLat(lngLat).setHTML(html).addTo(map);
    const p = popup; requestAnimationFrame(() => fitPopup(p));
    return popup;
  }
  // Pan just enough to keep a popup inside the map (tall ones, e.g. with a photo, can overflow either way).
  function fitPopup(p) {
    if (p !== popup || !p.isOpen()) return;
    if (map.isMoving()) return map.once("moveend", () => fitPopup(p));
    const m = map.getContainer().getBoundingClientRect(), r = p.getElement().getBoundingClientRect(), pad = 12;
    let dx = 0, dy = 0;
    if (r.top < m.top + pad || r.height > m.height - 2 * pad) dy = r.top - m.top - pad;
    else if (r.bottom > m.bottom - pad) dy = r.bottom - m.bottom + pad;
    if (r.left < m.left + pad) dx = r.left - m.left - pad; else if (r.right > m.right - pad) dx = r.right - m.right + pad;
    if (dx || dy) map.panBy([dx, dy], { duration: 250 });
  }
  function popupFor(f, lngLat) {
    const p = f.properties, id = f.layer.id;
    if (id === "ev-pt") return eventPopup(S.events.features.find((x) => x.properties.id === p.id), lngLat);
    if (id === "il-pt" || id === "il-fill") return ilPopup(p.key, lngLat);
    if (id === "ar-fill") return regionPopup(p.id, lngLat);
    if (id === "em-pt") return emPopup(p.c, lngLat);
    if (id === "uk-pt") {
      return showPopup(lngLat, `<div class="pop"><h5>UKMTO ${esc(p.type)} #${p.num}</h5><div class="meta">${esc(p.date)} · ${esc(p.where || "")} · position ${p.geo_method === "offset" ? "from stated range/bearing" : "approximate (area)"}</div>${esc(p.text)}<div><a href="${esc(p.url)}" target="_blank" rel="noopener">UKMTO notice ↗</a></div></div>`);
    }
    if (id === "mil-pt") {
      const role = AC_ROLES[p.role] ? p.role : "other", hx = String(p.hex || ""), pid = "acph-" + hx.replace(/[^0-9a-z]/gi, "");
      const alt = p.alt === "ground" ? "on the ground" : `${nf(p.alt)} ft`;
      const pop = showPopup(lngLat, `<div class="pop"><h5>${esc(p.flight || p.hex)} <span class="muted">${esc(p.type || "")}</span></h5>` +
        `<div class="actype">${acIcon(role)}<b>${esc(p.tname || p.type || "Type not broadcast")}</b></div>` +
        `<div class="meta">${esc(AC_ROLES[role])}${p.owner ? " · " + esc(p.owner) : ""}${p.icao_reg ? ` · registry type ${esc(p.icao_reg)}, transponder says ${esc(p.type || "–")}` : ""}</div>` +
        `<div class="acphoto" id="${pid}"><span class="muted small">Looking for a photo…</span></div>` +
        `<div class="meta">Reg ${esc(p.reg || "–")} · hex ${esc(p.hex)}</div>Alt ${alt} · ${nf(p.gs)} kt · track ${Math.round(p.track)}°<br>Squawk ${esc(p.squawk || "–")}${p.emerg ? ` · <b style="color:#f05252">EMERGENCY ${esc(p.emerg)}</b>` : ""}<br><span class="muted small">NIC ${esc(p.nic ?? "–")} · NACp ${esc(p.nacp ?? "–")} (low values can indicate GNSS interference)</span><div><a href="https://globe.adsb.lol/?icao=${esc(p.hex)}" target="_blank" rel="noopener">Track on adsb.lol ↗</a></div></div>`);
      acPhoto(hx, p.reg).then((h) => {
        const el = document.getElementById(pid); if (!el) return;
        el.innerHTML = h; el.classList.add("done");
        const img = el.querySelector("img"), place = () => { if (popup === pop) { pop.setLngLat(pop.getLngLat()); fitPopup(pop); } }; // re-anchor to the new size
        if (img && !img.complete) img.addEventListener("load", place, { once: true }); else place();
      });
      return pop;
    }
    if (id === "ship-pt" || id === "ship-arrow" || id === "ship-listed") return shipPopup(p, lngLat);
    if (id === "pw-pt") return pwPopup(p.id, lngLat);
    if (id === "out-fill") {
      const o = S.feeds.outages || {}, c = (o.countries || []).find((x) => x.code === p.code) || { events: [] };
      const regs = (o.regions || []).filter((r) => r.country === p.code).slice(0, 6);
      return showPopup(lngLat, `<div class="pop"><h5>${esc(p.name)} · internet outage${p.ongoing ? ` <b style="color:#a78bfa">ONGOING</b>` : ""}</h5><div class="meta">IODA (Georgia Tech), last ${esc(o.window_h || 72)} h</div>
        <ul class="small">${c.events.map((e) => `<li>${esc(e.start.slice(5, 16).replace("T", " "))}Z · ${esc(e.hours)} h · ${esc(IODA_SRC[e.source] || e.source)} · score ${nf(e.score)}${e.ongoing ? " · ongoing" : ""}</li>`).join("")}</ul>
        ${regs.length ? `<div class="sub">Regions</div><ul class="small">${regs.map((r) => `<li>${esc(r.region)} · ${esc(r.start.slice(5, 16).replace("T", " "))}Z · ${esc(r.hours)} h · ${esc(IODA_SRC[r.source] || r.source)}</li>`).join("")}</ul>` : ""}
        <div><a href="https://ioda.inetintel.cc.gatech.edu/country/${esc(p.code)}" target="_blank" rel="noopener">IODA dashboard ↗</a></div><div class="muted small">Automatic detection. Google-traffic dips alone can be noise; routing plus probing together is the strong signal.</div></div>`);
    }
    if (id === "gfw-fill") {
      const a = ((S.feeds.gfw || {}).areas || {})[p.key];
      return a && showPopup(lngLat, `<div class="pop">${gfwHtml(a, true)}</div>`);
    }
    if (id === "gfw-gap") {
      return showPopup(lngLat, `<div class="pop"><h5>AIS switched off: ${esc(p.name || "unnamed vessel")} <span class="muted">${esc((p.type || "").replace(/_/g, " "))}</span></h5>
        <div class="meta">${esc(p.flag || "flag ?")} · MMSI ${esc(p.mmsi || "–")} · off ${esc((p.start || "").slice(5, 16).replace("T", " "))}Z for ${nf(p.hours)} h${p.km != null ? ` · back on ${nf(Math.round(p.km))} km away` : ""}</div>
        ${p.mmsi ? `<div><a href="https://www.marinetraffic.com/en/ais/details/ships/mmsi:${esc(p.mmsi)}" target="_blank" rel="noopener">MarineTraffic ↗</a></div>` : ""}
        <div class="muted small">GFW "AIS off" event (prototype model): a gap of 12 h or more starting at least 50 nm from shore where satellite reception is good. Data runs about 4 days behind. ${GFW_ATTR}</div></div>`);
    }
    if (id === "adv-fill") return showPopup(lngLat, `<div class="pop"><h5>${esc(p.country)}: Level ${esc(p.level)}</h5><div class="meta">US State Department travel advisory · updated ${esc(p.date)}</div>${esc(p.label)}<div><a href="${esc(p.url)}" target="_blank" rel="noopener">Advisory ↗</a></div></div>`);
    if (id === "th-pt") return showPopup(lngLat, `<div class="pop"><h5>Thermal anomaly</h5><div class="meta">${p.sat === "N21" ? "NOAA-21" : "NOAA-20"} VIIRS · ${esc(p.ts)} · conf ${esc(p.conf)} · ${esc(p.dn === "N" ? "night" : "day")}</div>Fire radiative power ${p.frp} MW.<br><span class="muted small">Could be a strike fire, a gas flare or a field fire. Corroborate before trusting.</span></div>`);
    if (id === "gd-pt") return showPopup(lngLat, `<div class="pop"><h5>${esc(p.place)}</h5><div class="meta">GDELT CAMEO ${esc(p.cameo)} · ${esc(p.actor1)} → ${esc(p.actor2)} · ${p.mentions} mentions</div><a href="${esc(p.url)}" target="_blank" rel="noopener">Source article ↗</a><br><span class="muted small">Machine-coded from news. Noisy.</span></div>`);
    if (id === "cz-fill") return showPopup(lngLat, `<div class="pop"><h5>${esc(p.name)}</h5><div class="meta">EASA Conflict Zone Information Bulletin · valid until ${esc(p.valid_until)}</div></div>`);
    if (id === "front-fill") return showPopup(lngLat, `<div class="pop"><h5>${esc(p.label)}</h5><div class="meta">DeepStateMap · ${esc((S.feeds.front || {}).updated || "")}</div></div>`);
    return showPopup(lngLat, `<div class="pop"><h5>${esc(p.title)}</h5><div class="meta">Map overlay · ${esc(p.overlay_type)}</div>${p.note && p.note !== "null" ? esc(p.note) : ""}</div>`);
  }
  function eventPopup(f, lngLat) {
    if (!f) return;
    const p = f.properties, cat = CATS[p.category] || CATS.other;
    const where = [p.country_name, p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : null].filter(Boolean).join(" · ");
    let extra = "";
    if (p.thermal) extra += `<div class="post">🛰 <b>Satellite thermal corroboration:</b> ${p.thermal.n} VIIRS detection(s) within ${p.thermal.nearest_km} km, max FRP ${p.thermal.max_frp} MW, first ${esc(p.thermal.first)}.</div>`;
    if (p.ukmto) extra += `<div class="post">⚓ <b>UKMTO incidents within 60 km:</b> ${p.ukmto.map((u) => `#${u.num} ${esc(u.type)} (${esc(u.date)})`).join(", ")}</div>`;
    const html = `<div class="pop"><h5>${esc(p.title)}</h5>
      <div class="meta"><span style="color:${cat[1]}">●</span> ${esc(cat[0])} · ${p.ts_ms ? fmtD(p.ts_ms) + " " + fmtT(p.ts_ms) + (p.ts_source === "batch-estimate" ? " (est.)" : "") : "undated"} · ${esc(where || (THEATRES[p.theatre] || [p.theatre])[0])}</div>
      <div>${p.platform === "x" ? "𝕏" : p.platform === "reddit" ? "Reddit" : "Web"} · <b>${esc(p.handle || "")}</b> · <a href="${esc(p.url)}" target="_blank" rel="noopener">Open source ↗</a></div>
      ${extra}
      ${aiNote(S.ai.ev[p.id])}
      ${p.platform === "x" ? `<div id="xpost"><button id="loadpost">Load post text</button></div>` : ""}
      <div class="muted small" style="margin-top:6px">Single-curator report, unverified. Category auto-assigned.</div></div>`;
    showPopup(lngLat || f.geometry.coordinates, html);
    const b = $("loadpost");
    if (b) b.onclick = () => {
      b.textContent = "Loading…";
      api("xpost?id=" + encodeURIComponent(p.post_id)).then((x) => {
        $("xpost").innerHTML = `<div class="post">${esc(x.text || "(no text)")}${(x.media || []).filter((m) => m.url).slice(0, 1).map((m) => `<img src="${esc(m.url)}" alt="" loading="lazy">`).join("")}<div class="muted small">${esc(x.author || "")} · ${esc(x.created_at || "")}${x.views ? " · " + nf(x.views) + " views" : ""}${x.community_note ? " · has Community Note" : ""}</div></div>`;
      }).catch(() => ($("xpost").innerHTML = `<div class="muted small">Could not load the post (fxtwitter unavailable).</div>`));
    };
  }

  // ---------- data ----------
  function loadAll() {
    Promise.allSettled([api("events"), api("summary"), api("status"), api("czib_geo"), api("feed/front"), api("feed/ukmto"),
      api("feed/firms"), api("feed/gdelt"), api("feed/cables"), api("analysis"), api("analysis/events"),
      api("outages_geo"), api("advisories_geo"), api("feed/outages"), api("feed/ships"), api("feed/gfw"), api("feed/portwatch")]).then(([ev, sum, st, cz, fr, uk, fi, gd, cb, ao, ae, og, ag, ou, sh, gw, pw]) => {
      if (ao.value) S.ai.ov = ao.value;
      if (ae.value) S.ai.ev = ae.value;
      if (ev.value) S.events = ev.value;
      if (sum.value) S.summary = sum.value;
      if (st.value) S.status = st.value.feeds || {};
      if (cz.value) map.getSource("czib").setData(cz.value);
      if (fr.value && fr.value.data) { S.feeds.front = fr.value.data; map.getSource("front").setData(fr.value.data.geojson); }
      if (uk.value && uk.value.data) { S.feeds.ukmto = uk.value.data; setUkmto(); }
      if (fi.value && fi.value.data) setThermal(fi.value.data);
      if (gd.value && gd.value.data) setGdelt(gd.value.data);
      if (cb.value && cb.value.data) map.getSource("cables").setData(cb.value.data.geojson);
      if (og.value) map.getSource("outages").setData(og.value);
      if (ag.value) map.getSource("advisories").setData(ag.value);
      if (ou.value && ou.value.data) S.feeds.outages = ou.value.data;
      if (sh.value && sh.value.data) setShips(sh.value.data);
      if (gw.value && gw.value.data) setGfw(gw.value.data);
      if (pw.value && pw.value.data) setPw(pw.value.data);
      render();
    });
    loadLive();
  }
  function loadLive() {
    api("feed/mil").then((r) => {
      if (!r.data) return;
      S.feeds.mil = r.data;
      r.data.geojson.features.forEach((f) => { f.properties.emerg = f.properties.emergency && f.properties.emergency !== "none" ? f.properties.emergency : null; });
      map.getSource("mil").setData(r.data.geojson);
      renderKpis(); renderLayerCounts(); renderAcLegend();
    }).catch(() => {});
  }
  function setUkmto() {
    const items = (S.feeds.ukmto.items || []).filter((i) => i.coord);
    const newest = items.length ? Date.parse(items[0].date) : Date.now();
    map.getSource("ukmto").setData({ type: "FeatureCollection", features: items.map((i) => ({ type: "Feature", geometry: { type: "Point", coordinates: i.coord },
      properties: { ...i, col: UKMTO_COL[i.type] || "#38bdf8", op: Math.max(0.35, 1 - (newest - Date.parse(i.date)) / (45 * 86400000)) } })) });
  }
  function setThermal(d) {
    S.feeds.firms = d;
    map.getSource("thermal").setData({ type: "FeatureCollection", features: d.points.map(([lon, lat, frp, ts, conf, dn, sat]) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { frp, ts, conf, dn, sat } })) });
  }
  function setShips(d) {
    S.feeds.ships = d;
    map.getSource("ships").setData({ type: "FeatureCollection", features: d.points.map(([lon, lat, sog, cog, cls, name, mmsi, ts, dest, hdg, flag, marks, imo, dr, len]) => {
      const rot = hdg ?? cog, moving = (sog || 0) >= 1;
      return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] },
        properties: { sog, cog, hdg, cls, grp: shipGrp(cls), name, mmsi, ts, dest, flag: flag || "", marks: marks || "", imo: imo || "", dr, len,
          col: SHIP_COL[cls] || "#c9ced4", moving, arrow: cls === "tanker" && moving && rot != null, rot: rot ?? 0 } };
    }) });
    map.getSource("shiptrk").setData({ type: "FeatureCollection", features: Object.entries(d.tracks || {}).map(([mmsi, pts]) => ({ type: "Feature",
      geometry: { type: "LineString", coordinates: pts }, properties: { mmsi: +mmsi, grp: "tanker" } })) });
    const boxes = Object.entries(d.areas || {}).filter(([, a]) => a.no_live_coverage && a.bbox);
    map.getSource("aisbox").setData({ type: "FeatureCollection", features: boxes.flatMap(([k, a]) => {
      const [w, s, e, n] = a.bbox;
      return [{ type: "Feature", geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, properties: { key: k } },
        { type: "Feature", geometry: { type: "Point", coordinates: [(w + e) / 2, (s + n) / 2] },
          properties: { note: `No live AIS receivers: ${a.label}. See the chokepoint and GFW counts.` } }];
    }) });
  }
  function applyShipFilter() {
    const on = [...(S.shipGrps || new Set(SHIP_GRPS.map(([g]) => g)))], grp = ["in", ["get", "grp"], ["literal", on]];
    if (!map.getLayer("ship-pt")) return;
    map.setFilter("ship-pt", ["all", ["!", ["get", "arrow"]], grp]);
    map.setFilter("ship-arrow", ["all", ["get", "arrow"], grp]);
    map.setFilter("ship-listed", ["all", SG_FILTER, grp]);
    map.setFilter("ship-trk", grp);
  }
  function setPw(d) {
    S.feeds.portwatch = d;
    map.getSource("pw").setData({ type: "FeatureCollection", features: (d.chokepoints || []).filter((c) => c.lon != null && c.lat != null).map((c) => {
      const t7 = (c.avg7 || {}).tanker, chg = (c.change_vs_year_pct || {}).tanker;
      return { type: "Feature", geometry: { type: "Point", coordinates: [c.lon, c.lat] },
        properties: { id: c.id, name: c.name, t7: Math.max(0, t7 || 0), lbl: `${c.name}\n${t7 != null ? nf(t7) : "–"} tankers/day`, ...(chg != null ? { chg } : {}) } };
    }) });
  }
  function shipCard(mmsi) {
    const d = S.feeds.ships || {}, m = +mmsi;
    return (d.listed || []).find((x) => x.mmsi === m) || (d.tankers || []).find((x) => x.mmsi === m) || null;
  }
  function draughtHtml(dr, was) {
    if (dr == null) return "";
    let h = `draught ${nf(dr)} m`;
    if (was && Math.abs(was[0] - dr) >= 0.2) h += `, was ${nf(was[0])} m on ${esc(fmtD(Date.parse(was[1])))} <span class="muted">(${dr > was[0] ? "deeper: likely loaded" : "shallower: likely unloaded"}; crews enter draught by hand, so treat it as a hint)</span>`;
    return h;
  }
  function shipPopup(p, lngLat) {
    const c = shipCard(p.mmsi) || {}, flag = p.flag || c.flag, trk = ((S.feeds.ships || {}).tracks || {})[p.mmsi];
    const lists = c.lists ? `<div class="small">${markBadges(c.marks)}<br>Listed by: ${c.lists.map(esc).join(", ")}${c.list_name && c.list_name !== (p.name || c.name) ? ` · listed as <b>${esc(c.list_name)}</b>` : ""} · matched on ${esc(c.match)}${c.url ? ` · <a href="${esc(c.url)}" target="_blank" rel="noopener">OpenSanctions ↗</a>` : ""}</div>` : (p.marks ? `<div class="small">${markBadges(p.marks)}</div>` : "");
    const dims = [p.len ? `${nf(p.len)} m long` : "", draughtHtml(p.dr ?? c.dr, c.dr_was)].filter(Boolean).join(" · ");
    return showPopup(lngLat, `<div class="pop"><h5>${esc(p.name || "Unnamed vessel")} <span class="muted">${esc(p.cls === "unknown" || !p.cls ? "type unknown" : p.cls)}</span></h5>` +
      `<div class="meta">${flag ? `Flag ${esc(regionName(flag))} (declared) · ` : ""}MMSI ${esc(p.mmsi)}${p.imo ? ` · IMO ${esc(p.imo)}` : ""} · heard ${esc((p.ts || "").slice(11, 16))}Z</div>` +
      `${p.sog != null ? nf(p.sog) + " kt" : "speed –"} · course ${p.cog != null ? Math.round(p.cog) + "°" : "–"}${p.dest ? " · to " + esc(p.dest) : ""}${c.eta ? ` · ETA ${esc(c.eta)} UTC` : ""}` +
      (dims ? `<div class="small">${dims}</div>` : "") + lists +
      (trk ? `<div class="muted small">Track: ${trk.length} positions over the last 3 hours (faint line).</div>` : "") +
      `<div><a href="https://www.marinetraffic.com/en/ais/details/ships/mmsi:${esc(p.mmsi)}" target="_blank" rel="noopener">MarineTraffic ↗</a></div>` +
      `<div class="muted small">AISStream, volunteer receivers. Positions are self-reported and can be spoofed; the flag comes from the MMSI.${c.lists || p.marks ? " A list entry is about the ship's identifiers, not proof of what it is doing now. " + OS_ATTR + "." : ""}</div></div>`);
  }
  function pwSpark(sp, w = 300, h = 44) {
    if (!sp || sp.length < 2) return "";
    const mx = Math.max(1, ...sp.map((r) => r[2] || 0)), x = (i) => (i * w / (sp.length - 1)).toFixed(1), y = (v) => (h - 2 - (v || 0) * (h - 4) / mx).toFixed(1);
    const line = (j, col, wd) => `<polyline fill="none" stroke="${col}" stroke-width="${wd}" points="${sp.map((r, i) => x(i) + "," + y(r[j])).join(" ")}"/>`;
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Daily ships (grey) and tankers (gold), last ${sp.length} days">${line(2, "#6b7480", 1.2)}${line(1, SHIP_COL.tanker, 1.8)}</svg>` +
      `<div class="sparkax"><span>${esc(fmtD(Date.parse(sp[0][0])))}</span><span>tankers (gold) and all ships (grey) a day</span><span>${esc(fmtD(Date.parse(sp[sp.length - 1][0])))}</span></div>`;
  }
  const pct = (x) => (x == null ? "–" : `${x > 0 ? "+" : ""}${x}%`);
  function pwPopup(id, lngLat) {
    const c = ((S.feeds.portwatch || {}).chokepoints || []).find((x) => x.id === id);
    if (!c) return;
    const l = c.last || {}, a = c.avg7 || {}, y = c.year_ago7 || {}, ch = c.change_vs_year_pct || {};
    return showPopup(lngLat || [c.lon, c.lat], `<div class="pop"><h5>${esc(c.name)} <span class="muted">transits</span></h5>` +
      `<div class="meta">Ships through the chokepoint each day, through ${esc(c.last_day)} (IMF PortWatch, about 3 days behind)</div>` +
      `<div class="small">Tankers: <b>${nf(a.tanker)}</b>/day last 7 days, <b>${nf(y.tanker)}</b> a year ago <b style="color:${gfwCol(ch.tanker)}">${pct(ch.tanker)}</b><br>` +
      `All ships: <b>${nf(a.total)}</b>/day, ${nf(y.total)} a year ago <span style="color:${gfwCol(ch.total)}">${pct(ch.total)}</span><br>` +
      `Last day: ${nf(l.tanker)} tankers${l.tanker_dwt ? ` (about ${nf(Math.round(l.tanker_dwt))} t of cargo, IMF estimate)` : ""}, ${nf(l.container)} container, ${nf(l.dry_bulk)} dry bulk, ${nf(l.general_cargo)} general cargo, ${nf(l.roro)} ro-ro; ${nf(l.total)} in all.</div>` +
      pwSpark(c.spark) + `<div class="muted small">Counted from satellite AIS, so ships with AIS off are missed. ${PW_ATTR}</div></div>`);
  }
  function setGfw(d) {
    S.feeds.gfw = d;
    map.getSource("gfw").setData({ type: "FeatureCollection", features: Object.entries(d.areas || {}).map(([key, a]) => ({ type: "Feature",
      geometry: { type: "Polygon", coordinates: [a.ring] },
      properties: { key, kind: a.kind, label: a.label, ...(a.change_vs_last_year_pct != null ? { chg: a.change_vs_last_year_pct } : {}) } })) });
    map.getSource("gfwgap").setData({ type: "FeatureCollection", features: (d.gaps || []).map((g) => ({ type: "Feature", geometry: { type: "Point", coordinates: [g.lon, g.lat] },
      properties: { name: g.name, flag: g.flag, mmsi: g.mmsi, type: g.type, start: g.start, hours: g.hours, km: g.km } })) });
  }
  // Weekly means of the daily counts (newest, still-filling day left out), last bar = the last 7 full days.
  function sparkWeeks(daily, w = 300, h = 44) {
    const d = (daily || []).slice(0, -1), wk = [];
    for (let i = d.length % 7; i + 7 <= d.length; i += 7) {
      const xs = d.slice(i, i + 7).filter((x) => x != null);
      wk.push(xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
    }
    if (!wk.length) return "";
    const max = Math.max(1, ...wk.filter((x) => x != null)), bw = w / wk.length;
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Weekly mean ships per day over the last year">${wk.map((v, i) => v == null ? "" :
      `<rect x="${(i * bw + 0.4).toFixed(1)}" y="${(h - (v / max) * (h - 2)).toFixed(1)}" width="${Math.max(1, bw - 0.8).toFixed(1)}" height="${((v / max) * (h - 2)).toFixed(1)}" fill="${i === wk.length - 1 ? "#38bdf8" : "#5b6672"}"><title>${nf(Math.round(v))} a day</title></rect>`).join("")}</svg>`;
  }
  function gfwHtml(a, full) {
    const pct = (x) => (x == null ? "–" : `${x > 0 ? "+" : ""}${x}%`), col = gfwCol(a.change_vs_last_year_pct);
    const types = (a.types_by_day || {})[a.last_full_day];
    let h = `<h5>${esc(a.label)} <span class="muted">${a.kind === "chokepoint" ? "chokepoint" : "sea area"}${a.stale ? " · stale" : ""}</span></h5>
      <div class="meta">Non-fishing ships seen per day · through ${esc(a.last_full_day)} (about 4 days behind)</div>
      <div><b style="color:${col}">${nf(a.avg_7d)}</b> a day over the last 7 days · <b style="color:${col}">${pct(a.change_vs_last_year_pct)}</b> vs the same week last year (${nf(a.same_week_last_year_avg)}) · ${pct(a.change_vs_28d_pct)} vs the 4 weeks before</div>
      ${sparkWeeks(a.daily)}<div class="sparkax"><span>a year ago</span><span>last week</span></div>
      <div class="small">Flags, ships a day last week: ${(a.top_flags_7d || []).slice(0, 6).map(([f, n]) => `${esc(f === "?" ? "unknown" : f)} ${nf(n)}`).join(" · ") || "–"}</div>`;
    if (types) h += `<div class="small">Types on ${esc(a.last_full_day.slice(5))}: ${Object.entries(types).map(([t, n]) => `${esc(t.replace(/_/g, " "))} ${nf(n)}`).join(" · ")}</div>`;
    if (full && (a.ships_last_full_day || []).length) {
      const sh = a.ships_last_full_day;
      h += `<div class="sub">Ships seen ${esc(a.last_full_day.slice(5))} (${nf(sh.length)})</div><ul class="small">${sh.slice(0, 12).map((x) =>
        `<li>${x.mmsi ? `<a href="https://www.marinetraffic.com/en/ais/details/ships/mmsi:${esc(x.mmsi)}" target="_blank" rel="noopener">${esc(x.name || "unnamed")}</a>` : esc(x.name || "unnamed")} · ${esc(x.flag || "?")} · ${esc((x.type || "").replace(/_/g, " "))}${x.kn != null ? ` · ${nf(x.kn)} kt` : x.jump ? " · position jump" : ""}</li>`).join("")}${sh.length > 12 ? `<li class="muted">and ${nf(sh.length - 12)} more</li>` : ""}</ul>`;
    }
    if (a.gaps_30d != null) h += `<div class="small">AIS-off events starting here, last 30 days: <b>${nf(a.gaps_30d)}</b></div>`;
    return h + `<div class="muted small">Satellite plus shore AIS. Ships with AIS off are not counted, so a fall can mean fewer ships or more ships running dark. ${GFW_ATTR}</div>`;
  }
  function setGdelt(d) {
    S.feeds.gdelt = d;
    map.getSource("gdelt").setData({ type: "FeatureCollection", features: d.points.map(([lon, lat, cameo, place, a1, a2, mentions, url]) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { cameo, place, actor1: a1, actor2: a2, mentions, url } })) });
  }

  // ---------- 0.7.0: air-raid and missile alerts ----------
  // Israel: Tzeva Adom (Home Front Command alerts relayed by Tzofar). Ukraine, Russia, Poland: the alerts.in.ua SITREP.
  // The server sends timestamps only; the page works out "sirens now" etc. on its own clock, so the public copy
  // (refreshed every ~10 min) shows an old siren as past, never as live.
  const PUBLIC = /\.github\.io$/i.test(location.hostname);
  const AL_POLL = PUBLIC ? 60000 : 10000;
  const AR_COL = { red: "#f05252", yellow: "#f2b33d", nominal: "#6b7280", launch: "#c084fc" };
  const IL_COL = { siren: "#f05252", shelter: "#f2853d", early: "#fde047", ended: "#3ecf8e", recent: "#8a929b" };
  const IL_RANK = { recent: 1, ended: 2, shelter: 3, early: 4, siren: 5 };
  const IL_STATE = { siren: "Sirens now", shelter: "Shelter window (first 10 min after the siren)", early: "Early warning: alerts may follow",
    ended: "Incident ended (all clear)", recent: "Alerted in the last 24 h" };
  const IL_SHORT = { siren: "SIREN", shelter: "shelter", early: "early", ended: "all clear", recent: "24 h" };
  const CTRY = { UA: ["Ukraine", "Europe/Kyiv", "Kyiv"], RU: ["Russia", "Europe/Moscow", "Moscow"], PL: ["Poland", "Europe/Warsaw", "Warsaw"] };
  const LVL = { red: "Red: missile or mass-strike threat", yellow: "Yellow: drone or air-attack threat" };
  const PUBLIC_NOTE = "Public copy, refreshed about every 10 minutes, so not live. For real-time sirens use the Home Front Command app, Tzeva Adom or alerts.in.ua.";
  const NOT_SAFETY = "Not a safety tool: follow official alerts (Home Front Command in Israel, Povitryana Tryvoha in Ukraine).";
  const apiRev = (p) => fetch("api/" + p, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : Promise.reject(r.status))); // ETag revalidation: unchanged = 304
  const tzT = (ms, tz) => new Date(ms).toLocaleTimeString("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit" });
  const span = (s) => { const m = Math.max(0, Math.round(s / 60)); return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0") + " min"; };
  const agoS = (s) => (s < 120 ? Math.max(0, Math.round(s)) + " s ago" : span(s) + " ago");
  const isoMs = (s) => (s ? Date.parse(s) : null);
  const httpsUrl = (u) => (/^https:\/\//i.test(u || "") ? u : null);
  const REDUCED = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  let REG = new Map(); // ISO 3166-2 code -> region shape (Natural Earth, simplified)
  const REG_GEO = fetch("geo/alert-regions.json?v=0.7.0").then((r) => r.json()).then((fc) => { REG = new Map(fc.features.map((f) => [f.id, f])); }).catch(() => {});
  const IL = { key: "", siren: [], shelter: [], early: [], ended: [], recent: [], byKey: {}, earlyTitle: "" };
  let regSig = "", bannerHtml = "", pulsing = false;

  function loadAlerts() {
    apiRev("alerts").then((a) => {
      S.alerts = a;
      renderRegions(); renderIsrael(true); renderEmbassy(); renderKpis(); renderLayerCounts();
      if (!$("tab-alerts").classList.contains("hidden")) renderAlerts();
    }).catch(() => {});
  }
  const regCol = (r) => (r.kind === "alert" ? AR_COL[r.level] || AR_COL.red : AR_COL[r.kind] || AR_COL.nominal);
  const regList = () => (((S.alerts || {}).regions || {}).regions || []);
  function renderRegions() {
    const rs = regList(), sig = rs.map((r) => r.id + r.kind + (r.level || "")).join(",") + "|" + REG.size;
    if (sig === regSig || !map.getSource("alertreg")) return;
    regSig = sig;
    const rank = (r) => (r.kind !== "alert" ? 0 : r.level === "red" ? 2 : 1); // red drawn last, on top
    map.getSource("alertreg").setData({ type: "FeatureCollection", features: rs.filter((r) => REG.has(r.id)).sort((a, b) => rank(a) - rank(b))
      .map((r) => ({ type: "Feature", geometry: REG.get(r.id).geometry, properties: { id: r.id, kind: r.kind, level: r.level || "", col: regCol(r) } })) });
  }
  // Per Israeli city: siren (countdown + 60/120 s), all clear (an "incident ended" message), shelter window (10 min, no all
  // clear yet), early warning (a newer HFC early warning, no all clear since), else alerted in the last 24 h.
  function ilCompute(now) {
    const il = (S.alerts || {}).israel || {}, out = { siren: [], shelter: [], early: [], ended: [], recent: [], byKey: {}, earlyTitle: "" };
    const warned = {};
    (il.early || []).forEach((e) => { if (now - e.t <= 1800) (e.cities || []).forEach((x) => { if (!warned[x.id]) warned[x.id] = { e, x }; }); });
    const put = (it) => { out[it.st].push(it); out.byKey[it.key] = it; };
    (il.cities || []).forEach((c) => {
      const age = now - c.t, w = warned[c.id];
      let st = age <= (c.cd || 15) + c.x ? "siren" : c.ended && now - c.ended <= 1800 ? "ended" : !c.ended && age <= 600 ? "shelter" : "recent";
      if (w) { delete warned[c.id]; if (st !== "siren" && w.e.t > c.t && !w.x.ended) st = "early"; }
      put({ key: "c" + c.id, st, c, e: st === "early" ? w.e : null, lon: c.lon, lat: c.lat, n: c.n, poly: c.poly, fresh: age <= 1800 });
    });
    Object.values(warned).forEach(({ e, x }) => {
      const st = !x.ended ? "early" : now - x.ended <= 1800 ? "ended" : null;
      if (st) put({ key: "e" + x.id, st, c: null, e, x, lon: x.lon, lat: x.lat, n: x.n, poly: x.poly, fresh: true });
    });
    if (out.early.length) out.earlyTitle = out.early[0].e.title || "Early warning";
    return out;
  }
  function renderIsrael(force) {
    if (!S.alerts || !map.getSource("ilpt")) return;
    const r = ilCompute(Date.now() / 1000), all = [...r.recent, ...r.ended, ...r.shelter, ...r.early, ...r.siren];
    const key = all.map((i) => i.key + i.st + (i.fresh ? 1 : 0)).join(",");
    Object.assign(IL, r);
    if (!force && key === IL.key) return;
    IL.key = key;
    const props = (i) => ({ key: i.key, n: i.n, st: i.st, col: IL_COL[i.st], rank: IL_RANK[i.st], fresh: i.fresh });
    map.getSource("ilpt").setData({ type: "FeatureCollection", features: all.map((i) => ({ type: "Feature", geometry: { type: "Point", coordinates: [i.lon, i.lat] }, properties: props(i) })) });
    map.getSource("ilarea").setData({ type: "FeatureCollection", features: all.filter((i) => i.poly && (i.st !== "recent" || i.fresh))
      .map((i) => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [i.poly] }, properties: props(i) })) });
    renderBanner();
    if (!force) { renderKpis(); if (!$("tab-alerts").classList.contains("hidden")) renderAlerts(); }
    if (r.siren.length) startPulse();
  }
  function startPulse() {
    if (pulsing || REDUCED) return;
    pulsing = true;
    const step = () => {
      if (!IL.siren.length) { pulsing = false; map.setPaintProperty("il-halo", "circle-radius", 12); map.setPaintProperty("il-halo", "circle-opacity", 0.3); return; }
      const k = (performance.now() % 1400) / 1400;
      map.setPaintProperty("il-halo", "circle-radius", 6 + 20 * k);
      map.setPaintProperty("il-halo", "circle-opacity", 0.5 * (1 - k));
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  const noteHtml = () => `<div class="muted small">${esc(PUBLIC ? PUBLIC_NOTE : NOT_SAFETY)}</div>`;
  function ilHtml(i) {
    const c = i.c, e = i.e, now = Date.now() / 1000;
    let h = `<h5>${esc(i.n)}${c && c.he && c.he !== i.n ? ` <span class="muted">${esc(c.he)}</span>` : ""}</h5>
      <div class="meta">${c && c.a ? esc(c.a) + " · " : ""}Tzeva Adom (Home Front Command alerts)</div>
      <div><b style="color:${IL_COL[i.st]}">${esc(IL_STATE[i.st])}</b></div>`;
    if (c) h += `<div>${esc(c.label)} · ${fmtD(c.t * 1000)} ${fmtT(c.t * 1000)} (${tzT(c.t * 1000, "Asia/Jerusalem")} Israel) · ${agoS(now - c.t)}</div>
      <div class="small">Time to reach shelter here: ${c.cd ? c.cd + " s" : "immediate"}${c.ended ? ` · incident ended ${fmtT(c.ended * 1000)}` : ""}</div>`;
    if (e) h += `<div class="post"><b>${esc(e.title || "Early warning")}</b> <span class="muted small">${fmtT(e.t * 1000)} · ${agoS(now - e.t)}</span><div class="small">${esc(e.body || "")}</div>${i.x && i.x.ended ? `<div class="small">Incident ended ${fmtT(i.x.ended * 1000)}</div>` : ""}</div>`;
    return h + `<div><a href="https://www.tzevaadom.co.il/en/" target="_blank" rel="noopener">Tzeva Adom ↗</a></div>${noteHtml()}`;
  }
  function ilPopup(key, lngLat) {
    const i = IL.byKey[key];
    return i && showPopup(lngLat, `<div class="pop">${ilHtml(i)}</div>`);
  }
  function regionHtml(r) {
    const R = S.alerts.regions, [cn, tz, tzn] = CTRY[r.c] || ["", "UTC", "UTC"], since = isoMs(r.since);
    const local = r.c === "PL" ? r.pl : r.uk, th = (R.threats || []).filter((t) => t.region === r.id);
    const state = r.kind === "alert" ? `<b style="color:${regCol(r)}">${esc(LVL[r.level] || "Air-raid alert")}</b>`
      : r.kind === "nominal" ? `<b style="color:${AR_COL.nominal}">Standing alert</b> <span class="muted small">(occupied region: an administrative alert that is rarely lifted)</span>`
      : `<b style="color:${AR_COL.launch}">Cross-border launch area</b> <span class="muted small">(launches from here are being tracked)</span>`;
    return `<h5>${esc(r.en)} <span class="muted">${esc(cn)}</span></h5>
      <div class="meta">${local && local !== r.en ? esc(local) + " · " : ""}alerts.in.ua${R.as_of ? ", report of " + fmtT(isoMs(R.as_of)) : ""}</div>
      <div>${state}</div>${(r.types || []).length ? `<div>${r.types.map(esc).join(", ")}</div>` : ""}
      ${since ? `<div class="small">Since ${fmtT(since)} (${tzT(since, tz)} ${tzn}) · ${span((Date.now() - since) / 1000)}${PUBLIC ? " as of this copy" : ""}</div>` : ""}
      ${r.n_areas ? `<div class="small">${nf(r.n_areas)} area${r.n_areas > 1 ? "s" : ""}${(r.areas || []).length ? ": " + r.areas.map(esc).join(", ") + (r.n_areas > r.areas.length ? " …" : "") : ""}</div>` : ""}
      ${r.latest ? `<div class="small">Most recent: ${esc(r.latest.name)}${r.latest.at ? " at " + fmtT(isoMs(r.latest.at)) : ""}</div>` : ""}
      ${(r.also || []).includes("launch") ? `<div class="small" style="color:${AR_COL.launch}">Also a tracked launch area</div>` : ""}
      ${th.length ? `<div class="sub">Tracked over this region</div><ul class="small">${th.slice(0, 6).map((t) => `<li>${t.at ? fmtT(isoMs(t.at)) + " · " : ""}${esc(t.what)}${t.n ? " ×" + t.n : ""}${t.msg ? " · " + esc(t.msg) : ""}</li>`).join("")}</ul>` : ""}
      <div><a href="https://alerts.in.ua/en" target="_blank" rel="noopener">alerts.in.ua live map ↗</a></div>`;
  }
  function regionPopup(id, lngLat) {
    const r = regList().find((x) => x.id === id);
    return r && showPopup(lngLat, `<div class="pop">${regionHtml(r)}${noteHtml()}</div>`);
  }
  // ---------- 0.8.0: US embassy alerts ----------
  // The posts' own RSS (Security, Demonstration, Weather ... Alerts), read by the server every 5 or 15 min.
  const EM_KIND = { departure: ["Departure / closure", "#f05252"], shelter: ["Shelter / air defence", "#f05252"],
    security: ["Security", "#f2b33d"], demonstration: ["Demonstration", "#f2b33d"], weather: ["Weather / disaster", "#38bdf8"],
    health: ["Health", "#38bdf8"], advisory: ["Travel advisory", "#a98bff"], worldwide: ["Worldwide caution", "#a98bff"],
    routine: ["Message", "#9aa4ae"] };
  const EM_OLD = "#8a929b", EM_URGENT = new Set(["departure", "shelter"]);
  const emCol = (kind) => (EM_KIND[kind] || EM_KIND.routine)[1];
  const emK = (kind) => (EM_KIND[kind] || EM_KIND.routine)[0];
  const emData = () => (S.alerts || {}).embassy || {};
  const emPost = (c) => (emData().posts || []).find((p) => p.c === c);
  const emPlace = (p) => (p ? (p.city && p.city !== p.n ? `${p.city}, ${p.n}` : p.n) : "");
  const emItemsFor = (c) => (emData().items || []).filter((i) => i.c === c || (i.posts || []).includes(c));
  const emWhere = (i) => { const ps = (i.posts && i.posts.length ? i.posts : [i.c]).map(emPost).filter(Boolean);
    return ps.length <= 1 ? emPlace(ps[0]) : ps.slice(0, 3).map((p) => p.city || p.n).join(", ") + (ps.length > 3 ? ` +${ps.length - 3}` : ""); };
  let emSig = "";
  function renderEmbassy() {
    if (!map.getSource("embpt")) return;
    const now = Date.now() / 1000, rows = [];
    (emData().posts || []).forEach((p) => {
      const it = emItemsFor(p.c); if (!it.length || p.lat == null) return;
      const top = it[0], age = now - top.t, urgent = it.find((i) => EM_URGENT.has(i.kind) && now - i.t <= 86400);
      const k = urgent ? urgent.kind : top.kind, old = age > 3 * 86400;
      rows.push({ c: p.c, lon: p.lon, lat: p.lat, city: p.city || p.n, col: old && !urgent ? EM_OLD : emCol(k), op: age > 86400 && !urgent ? 0.7 : 1,
        rank: urgent ? 3 : old ? 1 : 2 });
    });
    const sig = rows.map((r) => r.c + r.col + r.op).join(",");
    if (sig === emSig) return;
    emSig = sig;
    map.getSource("embpt").setData({ type: "FeatureCollection", features: rows.map((r) => ({ type: "Feature", geometry: { type: "Point", coordinates: [r.lon, r.lat] }, properties: r })) });
  }
  function emItemHtml(i, full) {
    const u = httpsUrl(i.url);
    return `<div class="post"><span class="badge" style="border-color:${emCol(i.kind)};color:${emCol(i.kind)}">${esc(emK(i.kind))}</span> ` +
      `${u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(i.title)}</a>` : esc(i.title)}` +
      `<div class="muted small">${fmtD(i.t * 1000)} ${fmtT(i.t * 1000)} · ${agoS(Date.now() / 1000 - i.t)}${(i.posts || []).length > 1 ? " · " + esc(emWhere(i)) : ""}</div>` +
      (full && i.loc ? `<div class="small"><b>Location:</b> ${esc(i.loc)}</div>` : "") + (full && i.event ? `<div class="small">${esc(i.event)}</div>` : "") + `</div>`;
  }
  function emPopup(c, lngLat) {
    const p = emPost(c), it = emItemsFor(c); if (!p) return;
    return showPopup(lngLat || [p.lon, p.lat], `<div class="pop"><h5>U.S. Embassy · ${esc(emPlace(p))}</h5>
      <div class="meta">The post's own alert feed${p.ok === false ? ` · <b style="color:var(--bad)">feed failing</b>` : ""}</div>
      ${it.slice(0, 5).map((i, n) => emItemHtml(i, n < 2)).join("") || `<div class="muted small">No alerts in the last 7 days.</div>`}
      <div class="muted small">Copies of US State Department messages (public domain). Not a safety tool: enrol in STEP and follow the embassy directly.</div></div>`);
  }
  function emCard() {
    const E = emData(), it = E.items || [], c = E.counts || {}, now = Date.now() / 1000;
    const rows = it.slice(0, 25).map((i) => `<li data-em="${esc(i.c)}"><span class="sw" style="background:${now - i.t > 3 * 86400 && !EM_URGENT.has(i.kind) ? EM_OLD : emCol(i.kind)}"></span>` +
      `<span class="nm">${esc(i.title)}<small>${esc(emWhere(i))} · ${esc(emK(i.kind))}${i.event ? " · " + esc(i.event.slice(0, 160)) : ""}</small></span>` +
      `<span class="tm">${fmtD(i.t * 1000)}<br>${fmtT(i.t * 1000)}</span></li>`).join("");
    const failing = (E.posts || []).filter((p) => p.ok === false).length;
    return `<div class="card"><h4><span class="sw" style="background:${c["24h"] ? EM_KIND.security[1] : "var(--dim)"}"></span>US embassy alerts<span class="lvl muted small">${nf(c["24h"] || 0)} in 24 h · ${nf(c["72h"] || 0)} in 3 days</span></h4>
      ${rows ? `<ul class="al-list">${rows}</ul>` : `<div class="muted small">${E.at ? "No embassy alerts in the last 7 days." : "Waiting for the first sweep of the embassy feeds."}</div>`}
      <div class="muted small" style="margin-top:6px">${nf((E.posts || []).length)} posts watched${failing ? `, <b style="color:var(--bad)">${nf(failing)} failing</b>` : ""}. Middle East and Europe every 5 min, others every 15 min.</div></div>`;
  }
  function bboxOf(g) {
    let w = 180, s = 90, e = -180, n = -90;
    const walk = (a) => { if (typeof a[0] === "number") { w = Math.min(w, a[0]); e = Math.max(e, a[0]); s = Math.min(s, a[1]); n = Math.max(n, a[1]); } else a.forEach(walk); };
    walk(g.coordinates);
    return [[w, s], [e, n]];
  }
  function fitPts(pts, maxZoom) {
    if (!pts.length) return;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: { top: 130, bottom: 60, left: 60, right: 60 }, maxZoom }); // top: room for the banner
  }
  function showRegion(id) {
    const g = REG.get(id); if (!g) return;
    const b = bboxOf(g.geometry);
    map.fitBounds(b, { padding: 60, maxZoom: 7.5 });
    regionPopup(id, [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2]);
  }
  const names = (list) => { const n = [...new Set(list.map((i) => i.n))]; return n.slice(0, 4).join(", ") + (n.length > 4 ? ` +${n.length - 4} more` : ""); };
  function renderBanner() {
    const el = $("alertbar"), rows = [];
    const sep = '<span class="sep">·</span>';
    if (IL.siren.length) rows.push(["bad", "il", `<b>SIRENS IN ISRAEL</b>${sep}${esc([...new Set(IL.siren.map((i) => i.c.label))].join(", "))}${sep}${esc(names(IL.siren))}`]);
    else if (IL.early.length) rows.push(["warn", "il", `<b>ISRAEL: EARLY WARNING</b>${sep}${esc(IL.earlyTitle)}${sep}${nf(IL.early.length)} areas`]);
    else if (IL.shelter.length) rows.push(["amber", "il", `<b>ISRAEL</b>${sep}shelter window after sirens at ${fmtT(IL.shelter[0].c.t * 1000)}${sep}${esc(names(IL.shelter))}`]);
    const pl = regList().filter((r) => r.c === "PL" && r.kind === "alert");
    if (pl.length) rows.push(["warn", "pl", `<b>POLAND</b>${sep}${esc([...new Set(pl.flatMap((r) => r.types || []))].join(", ") || "air-attack threat")}${sep}${esc(pl.map((r) => r.en).join(", "))}`]);
    const emU = (emData().items || []).filter((i) => EM_URGENT.has(i.kind) && Date.now() / 1000 - i.t <= 86400);
    if (emU.length) rows.push(["warn", "em:" + emU[0].c, `<b>US EMBASSY</b>${sep}${esc(emK(emU[0].kind))}${sep}${esc(emWhere(emU[0]))}${sep}${esc(emU[0].title.slice(0, 90))}${emU.length > 1 ? `${sep}+${emU.length - 1} more` : ""}`]);
    const h = rows.map(([c, k, t]) => `<button class="${c}" data-k="${k}"><i></i><span>${t}${PUBLIC ? `${sep}<span class="muted small">public copy, up to 10 min old</span>` : ""}</span></button>`).join("");
    if (h === bannerHtml) return;
    bannerHtml = h; el.innerHTML = h; el.classList.toggle("hidden", !rows.length);
  }
  $("alertbar").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    openTab("alerts");
    if (b.dataset.k === "il") fitPts([...IL.siren, ...IL.early, ...IL.shelter].map((i) => [i.lon, i.lat]), 9);
    else if (b.dataset.k.startsWith("em:")) { const p = emPost(b.dataset.k.slice(3)); if (p) { map.flyTo({ center: [p.lon, p.lat], zoom: Math.max(map.getZoom(), 5), speed: 1.6 }); emPopup(p.c); } }
    else {
      const bs = regList().filter((r) => r.c === "PL" && r.kind === "alert" && REG.has(r.id)).map((r) => bboxOf(REG.get(r.id).geometry));
      fitPts(bs.flat(), 7);
    }
  };
  function alertKpis() {
    const sm = (S.alerts && S.alerts.summary) || S.summary.regional_alerts;
    if (!sm || !sm.ukraine) return [[nf((S.summary.israel_alerts || {}).cities_alerted_24h), "Israel alerts, 24h"]];
    const ua = sm.ukraine, ru = sm.russia || {}, il24 = Object.values((sm.israel || {}).alerts_24h_by_threat || {}).reduce((a, b) => a + b, 0);
    return [
      [`${nf(ua.n)} / ${nf(ru.n)}`, "UA / RU regions on alert", ua.red ? "warn" : false],
      IL.siren.length ? [nf(IL.siren.length), "Israel sirens NOW", "bad"] : [nf(il24), "Israel alerts, 24h", IL.shelter.length || IL.early.length ? "warn" : false],
    ];
  }
  function regRow(r) {
    const since = isoMs(r.since), sub = (r.types || []).join(", ") || (r.kind === "nominal" ? "standing alert" : r.kind === "launch" ? "launch area" : "");
    return `<li data-r="${esc(r.id)}"><span class="sw" style="background:${regCol(r)}"></span><span class="nm">${esc(r.en)}<small>${esc(sub)}${r.n_areas ? ` · ${nf(r.n_areas)} area${r.n_areas > 1 ? "s" : ""}` : ""}</small></span>` +
      `<span class="tm">${since ? fmtT(since) + "<br>" + span((Date.now() - since) / 1000) : ""}</span></li>`;
  }
  function renderAlerts() {
    const el = $("tab-alerts"), A = S.alerts;
    if (!A) { el.innerHTML = `<div class="card"><h4>Air-raid and missile alerts</h4><div class="muted">Loading…</div></div>`; return; }
    const il = A.israel || {}, R = A.regions || {}, rs = R.regions || [], now = Date.now();
    const byLvl = (a, b) => (b.level === "red") - (a.level === "red") || (isoMs(b.since) || 0) - (isoMs(a.since) || 0);
    const al = (c) => rs.filter((r) => r.c === c && r.kind === "alert").sort(byLvl), red = (l) => l.filter((r) => r.level === "red").length;
    const ua = al("UA"), ru = al("RU"), pl = al("PL");
    const launch = rs.filter((r) => r.kind === "launch" || (r.also || []).includes("launch")), nominal = rs.filter((r) => r.kind === "nominal");
    const genAge = (now - (isoMs(A.generated) || now)) / 1000, liveAge = il.live_at ? (now - isoMs(il.live_at)) / 1000 : null;
    const bad = (t) => `<b style="color:var(--bad)">${t}</b>`;
    const head = `<div class="card"><h4>Air-raid and missile alerts</h4>
      <div class="row"><span>Israel <b style="color:${IL.siren.length ? IL_COL.siren : "inherit"}">${nf(IL.siren.length)}</b> sirens now</span><span><b>${nf(IL.shelter.length)}</b> shelter window</span><span><b>${nf(IL.early.length)}</b> early warning</span></div>
      <div class="row"><span>Ukraine <b>${nf(ua.length)}</b> regions (${nf(red(ua))} red)</span><span>Russia <b>${nf(ru.length)}</b> (${nf(red(ru))} red)</span><span>Poland <b>${nf(pl.length)}</b></span></div>
      <div class="muted small">Israel: Tzeva Adom ${il.live_ok ? "live feed OK" : bad("live feed failing")}${liveAge != null ? `, polled ${agoS(liveAge)}` : ""}. Ukraine, Russia, Poland: alerts.in.ua ${R.ok === false ? bad("failing") + " " : ""}${R.as_of ? "report of " + fmtT(isoMs(R.as_of)) : ""}${R.primary_error ? " (fallback source: oblast level only)" : ""}.</div>
      ${PUBLIC ? `<div class="al-note">${esc(PUBLIC_NOTE)}${genAge > 120 ? ` This copy is ${span(genAge)} old.` : ""}</div>` : ""}</div>`;
    const cur = [...IL.siren, ...IL.early, ...IL.shelter, ...IL.ended];
    const curRows = cur.slice(0, 40).map((i) => `<li data-il="${esc(i.key)}"><span class="sw" style="background:${IL_COL[i.st]}"></span><span class="nm">${esc(i.n)}<small>${esc(i.c ? i.c.label : (i.e && i.e.title) || "")}${i.c && i.c.a ? " · " + esc(i.c.a) : ""}</small></span><span class="tm">${esc(IL_SHORT[i.st])}<br>${fmtT((i.c ? i.c.t : i.e.t) * 1000)}</span></li>`).join("")
      + (cur.length > 40 ? `<li class="nc muted small">and ${nf(cur.length - 40)} more</li>` : "");
    const thCol = (th) => (th === 0 || th === 7 ? IL_COL.siren : th === 5 ? IL_COL.shelter : IL_COL.recent);
    const evRows = (il.events || []).slice(0, 15).map((e) => `<li ${e.c ? `data-c="${e.c.join(",")}"` : 'class="nc"'}><span class="sw" style="background:${thCol(e.th)}"></span><span class="nm">${esc(e.label)} · ${nf(e.n)} area${e.n > 1 ? "s" : ""}<small>${esc(e.names.slice(0, 8).join(", "))}${e.n > 8 ? " …" : ""}</small></span><span class="tm">${fmtD(e.t * 1000)}<br>${fmtT(e.t * 1000)}</span></li>`).join("");
    const msgRows = (il.messages || []).slice(0, 6).map((m) => `<li class="nc"><span class="nm">${esc(m.title || m.kind)}<small>${esc(m.kind)}${m.body ? " · " + esc(m.body.slice(0, 240)) : ""}</small></span><span class="tm">${fmtD(m.time * 1000)}<br>${fmtT(m.time * 1000)}</span></li>`).join("");
    const n24 = Object.values(il.counts_24h || {}).reduce((a, b) => a + b, 0);
    const ilCard = `<div class="card"><h4><span class="sw" style="background:${n24 ? IL_COL.siren : "var(--dim)"}"></span>Israel<span class="lvl muted small">${nf(n24)} alerts, 24 h</span></h4>
      ${cur.length ? `<div class="sub">Now</div><ul class="al-list">${curRows}</ul>` : `<div class="muted small">No sirens, shelter window or early warning right now.</div>`}
      ${evRows ? `<div class="sub">Alert waves, last 24 h</div><ul class="al-list">${evRows}</ul>` : `<div class="muted small">No alerts in the last 24 h.</div>`}
      ${msgRows ? `<div class="sub">Home Front Command messages</div><ul class="al-list">${msgRows}</ul>` : ""}</div>`;
    const regCard = (title, list, extra) => `<div class="card"><h4><span class="sw" style="background:${red(list) ? AR_COL.red : list.length ? AR_COL.yellow : "var(--dim)"}"></span>${title}<span class="lvl muted small">${nf(list.length)} on alert</span></h4>` +
      (list.length ? `<ul class="al-list">${list.map(regRow).join("")}</ul>` : `<div class="muted small">No regions on alert.</div>`) + (extra || "") + `</div>`;
    const nomLine = nominal.length ? `<div class="muted small" style="margin-top:6px">Standing alerts (occupied): ${nominal.map((r) => esc(r.en)).join(", ")}</div>` : "";
    const launchList = launch.length ? `<div class="sub">Cross-border launch areas tracked</div><ul class="al-list">${launch.map(regRow).join("")}</ul>` : "";
    const thr = (R.threats || []).slice(0, 15).map((t) => `<li ${t.region ? `data-r="${esc(t.region)}"` : 'class="nc"'}><span class="nm">${esc(t.what)}${t.n ? " ×" + t.n : ""} over ${esc(t.over)}<small>${esc(t.msg || "")}</small></span><span class="tm">${t.at ? fmtT(isoMs(t.at)) : ""}</span></li>`).join("");
    const om = (R.messages || []).slice(0, 10).map((m) => { const u = httpsUrl(m.url);
      return `<li class="nc"><span class="nm">${esc(m.who || "Statement")}${u ? ` <a href="${esc(u)}" target="_blank" rel="noopener">↗</a>` : ""}<small>${esc(m.text)}</small></span><span class="tm">${m.at ? fmtT(isoMs(m.at)) : ""}</span></li>`; }).join("");
    const ended = (R.ended || []).slice(0, 10).map((x) => `<li class="nc"><span class="nm">${esc(x.text)}<small>${esc(x.dur || "")}</small></span><span class="tm">${x.from ? fmtT(isoMs(x.from)) : ""}–${x.to ? fmtT(isoMs(x.to)) : ""}</span></li>`).join("");
    const list = (title, rows) => (rows ? `<div class="card"><h4>${title}</h4><ul class="al-list">${rows}</ul></div>` : "");
    el.innerHTML = head + ilCard + regCard("Ukraine", ua, nomLine) + regCard("Russia", ru, launchList) + (pl.length ? regCard("Poland", pl) : "") + emCard() +
      list("Threats tracked (alerts.in.ua)", thr) + list("Official statements", om) + list("Alerts ended", ended) +
      (R.bluf ? `<div class="card"><h4>alerts.in.ua summary</h4><div class="small">${esc(R.bluf)}</div></div>` : "") +
      `<div class="muted small" style="margin:2px 2px 12px">Israel: <a href="https://www.tzevaadom.co.il/en/" target="_blank" rel="noopener">Tzeva Adom</a> relays Home Front Command alerts. Ukraine, Russia, Poland: the <a href="https://alerts.in.ua/en" target="_blank" rel="noopener">alerts.in.ua</a> situation report, Kyiv times shown in UTC. Region shapes: Natural Earth. US embassy alerts: each post's own feed (public domain). All sources are free and keyless. ${esc(NOT_SAFETY)}</div>`;
  }
  $("tab-alerts").onclick = (e) => {
    if (e.target.closest("a")) return;
    const li = e.target.closest("li"); if (!li) return;
    if (li.dataset.r) showRegion(li.dataset.r);
    else if (li.dataset.em) { const p = emPost(li.dataset.em); if (!p) return; map.flyTo({ center: [p.lon, p.lat], zoom: Math.max(map.getZoom(), 5), speed: 1.6 }); emPopup(p.c); }
    else if (li.dataset.il) { const i = IL.byKey[li.dataset.il]; if (i) { map.flyTo({ center: [i.lon, i.lat], zoom: Math.max(map.getZoom(), 9.5), speed: 1.6 }); ilPopup(i.key, [i.lon, i.lat]); } }
    else if (li.dataset.c) { const [lo, la] = li.dataset.c.split(",").map(Number); map.flyTo({ center: [lo, la], zoom: Math.max(map.getZoom(), 8.5), speed: 1.6 }); }
    else return;
    if (window.innerWidth <= 900) window.scrollTo(0, 0);
  };

  // ---------- filtering + render ----------
  function filtered(ignoreTime) {
    if (!S.events) return [];
    const q = S.q.trim().toLowerCase();
    const newest = Math.max(...S.events.features.map((f) => f.properties.ts_ms || 0));
    return S.events.features.filter((f) => {
      const p = f.properties;
      if (p.kind !== "event") return false;
      if (S.theatre !== "global" && p.theatre !== S.theatre) return false;
      if (!S.cats.has(p.category)) return false;
      if (!ignoreTime) {
        if (S.hours && p.ts_ms && newest - p.ts_ms > S.hours * 3600000) return false;
        if (S.brush && p.ts_ms && (p.ts_ms < S.brush[0] || p.ts_ms > S.brush[1])) return false;
      }
      if (q && ![p.title, p.handle, p.country_name, p.sea, p.category].join(" ").toLowerCase().includes(q)) return false;
      return true;
    });
  }
  function render() {
    if (!S.events) return;
    const list = filtered();
    const newest = Math.max(...S.events.features.map((f) => f.properties.ts_ms || 0));
    const ids = new Set(list.map((f) => f.properties.id));
    map.getSource("events").setData({ type: "FeatureCollection", features: list.map((f) => ({ ...f, properties: { ...f.properties,
      col: (CATS[f.properties.category] || CATS.other)[1], recent: !!f.properties.ts_ms && newest - f.properties.ts_ms < 6 * 3600000,
      est: f.properties.ts_source === "batch-estimate" } })) });
    map.getSource("overlays").setData({ type: "FeatureCollection", features: S.events.features.filter((f) => f.properties.kind === "overlay" && (S.theatre === "global" || f.properties.theatre === S.theatre)) });
    renderFeed(list);
    renderTheatreCounts();
    renderKpis();
    renderLayerCounts();
    drawTimeline();
    if (!$("tab-brief").classList.contains("hidden")) renderBrief();
    if (!$("tab-sea").classList.contains("hidden")) renderSea();
    if (!$("tab-sources").classList.contains("hidden")) renderSources();
    if (!$("tab-ai").classList.contains("hidden")) renderAnalyst();
    $("mapsrc").innerHTML = `Source map: <b>${esc(S.summary.map_title || "")}</b><br>${nf(S.summary.events_total)} events · newest ${S.summary.newest_event_age_min != null ? S.summary.newest_event_age_min + " min ago" : "–"}<br>Archived snapshots power history; see Sources.`;
    void ids;
  }
  function renderFeed(list) {
    const rows = list.slice().sort((a, b) => (b.properties.ts_ms || 0) - (a.properties.ts_ms || 0));
    $("feedcount").textContent = `${rows.length} events${S.theatre !== "global" ? " in " + THEATRES[S.theatre][0] : ""}${S.brush ? " · time-brushed" : ""}`;
    $("feed").innerHTML = rows.map((f) => {
      const p = f.properties, c = (CATS[p.category] || CATS.other)[1];
      const where = p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name || "";
      return `<li data-id="${p.id}" style="--c:${c}"><div class="t">${esc(p.title)}</div><div class="m">
        <span class="time">${p.ts_ms ? fmtD(p.ts_ms) + " " + fmtT(p.ts_ms) : "–"}</span><span>${p.ts_ms ? ago(p.ts_ms) : ""}</span>
        <span>${esc(where)}</span><span>${esc(p.handle || "")}</span>
        ${p.ts_source === "batch-estimate" ? '<span class="badge est">time est.</span>' : ""}
        ${p.thermal ? '<span class="badge th">thermal ✓</span>' : ""}${p.ukmto ? '<span class="badge uk">UKMTO nearby</span>' : ""}${sigBadge(S.ai.ev[p.id])}</div></li>`;
    }).join("");
  }
  $("feed").addEventListener("click", (e) => {
    const li = e.target.closest("li"); if (!li) return;
    const f = S.events.features.find((x) => x.properties.id === li.dataset.id); if (!f) return;
    map.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.getZoom(), 6.5), speed: 1.6 });
    eventPopup(f, f.geometry.coordinates);
    if (window.innerWidth <= 900) window.scrollTo(0, 0);
  });

  function buildRail() {
    $("theatres").innerHTML = Object.entries(THEATRES).map(([k, [n, c]]) =>
      `<button data-th="${k}" class="${k === S.theatre ? "on" : ""}"><span class="sw" style="background:${c}"></span><span class="nm">${n}</span><span class="ct" id="ct-${k}">–</span></button>`).join("");
    $("theatres").onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      S.theatre = b.dataset.th; S.brush = null;
      [...$("theatres").children].forEach((x) => x.classList.toggle("on", x === b));
      const [lon, lat, z] = THEATRES[S.theatre][2]; map.flyTo({ center: [lon, lat], zoom: z, speed: 1.4 });
      $("rail").classList.remove("open"); render();
    };
    $("layers").innerHTML = LAYERS.map(([k, label, feed, on]) =>
      `<label><input type="checkbox" data-layer="${k}" ${on ? "checked" : ""}><span class="dot" id="dot-${k}"></span>${label}<span class="n" id="n-${k}"></span></label>` +
      (k === "mil" ? `<div class="aclegend" id="aclegend"></div>` : "") +
      (k === "ships" ? `<div class="aclegend" id="shipfilter">${SHIP_GRPS.map(([g, t]) => `<button class="chip" data-grp="${g}" title="Show or hide ${t.toLowerCase()}"><i style="background:${SHIP_COL[g] || SHIP_COL.other}"></i>${t}<span class="n" id="sn-${g}"></span></button>`).join("")}</div>` +
        `<div class="aclegend">${[MARK.S, MARK.G].map(([t, c]) => `<span><i class="lsw ring" style="border-color:${c}"></i>${t.replace(" (GUR list)", "")}</span>`).join("")}</div>` : "") +
      (k === "alerts" ? `<div class="aclegend">${[["red", "missile"], ["yellow", "drone / air"], ["nominal", "standing"], ["launch", "launch area"]]
        .map(([c, t]) => `<span><i class="lsw" style="background:${AR_COL[c]}"></i>${t}</span>`).join("")}</div>` : "") +
      (k === "embassy" ? `<div class="aclegend">${[[EM_KIND.shelter[1], "shelter / departure"], [EM_KIND.security[1], "security / protest"], [EM_KIND.weather[1], "weather / health"], [EM_OLD, "older than 3 days"]]
        .map(([c, t]) => `<span><i class="lsw ring" style="border-color:${c}"></i>${t}</span>`).join("")}</div>` : "") +
      (k === "israel" ? `<div class="aclegend">${[["siren", "siren"], ["shelter", "shelter"], ["early", "early warning"], ["ended", "all clear"], ["recent", "24 h"]]
        .map(([c, t]) => `<span><i class="lsw dot" style="background:${IL_COL[c]}"></i>${t}</span>`).join("")}</div>` : "")).join("");
    $("shipfilter").onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      e.preventDefault();
      S.shipGrps = S.shipGrps || new Set(SHIP_GRPS.map(([g]) => g));
      S.shipGrps.has(b.dataset.grp) ? S.shipGrps.delete(b.dataset.grp) : S.shipGrps.add(b.dataset.grp);
      b.classList.toggle("off", !S.shipGrps.has(b.dataset.grp));
      applyShipFilter();
    };
    $("layers").onchange = (e) => {
      const k = e.target.dataset.layer; if (!k) return;
      GROUPS[k].forEach((l) => map.getLayer(l) && map.setLayoutProperty(l, "visibility", e.target.checked ? "visible" : "none"));
    };
    $("cats").innerHTML = Object.entries(CATS).map(([k, [n, c]]) => `<button class="chip" data-cat="${k}"><i style="background:${c}"></i>${n}</button>`).join("");
    $("cats").onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      const k = b.dataset.cat;
      if (e.altKey || e.metaKey) { S.cats = new Set([k]); } else { S.cats.has(k) ? S.cats.delete(k) : S.cats.add(k); }
      [...$("cats").children].forEach((x) => x.classList.toggle("off", !S.cats.has(x.dataset.cat)));
      render();
    };
  }
  function renderTheatreCounts() {
    const all = S.events.features.filter((f) => f.properties.kind === "event");
    Object.keys(THEATRES).forEach((k) => { const el = $("ct-" + k); if (el) el.textContent = k === "global" ? all.length : all.filter((f) => f.properties.theatre === k).length || "·"; });
  }
  function renderAcLegend() {
    const el = $("aclegend"), n = (S.feeds.mil || {}).roles || {};
    if (el) el.innerHTML = Object.keys(AC_ROLES).filter((r) => n[r]).map((r) => `<span title="${esc(AC_ROLES[r])}">${acIcon(r)}${esc(AC_SHORT[r])} ${n[r]}</span>`).join("");
  }
  function renderLayerCounts() {
    const st = S.status, n = {
      events: S.summary.events_total, overlays: S.events ? S.events.features.filter((f) => f.properties.kind === "overlay").length : null,
      front: (S.feeds.front || {}).count, thermal: (S.feeds.firms || {}).count, ukmto: (S.feeds.ukmto || {}).located,
      mil: (S.feeds.mil || {}).count, gdelt: (S.feeds.gdelt || {}).count, czib: S.summary.airspace_czib_active, cables: null,
      ships: (S.feeds.ships || {}).count, choke: (S.feeds.portwatch || {}).count, outages: (S.feeds.outages || {}).count, gfw: (S.feeds.gfw || {}).count,
      advisories: S.summary.travel_advisories ? (S.summary.travel_advisories.level4 || 0) + (S.summary.travel_advisories.level3 || 0) : null,
      alerts: S.alerts ? regList().filter((r) => r.kind === "alert").length : null, israel: S.alerts ? ((S.alerts.israel || {}).cities || []).length : null,
      embassy: S.alerts && S.alerts.embassy ? (S.alerts.embassy.items || []).length : null };
    const sg = {};
    ((S.feeds.ships || {}).points || []).forEach((p) => { const g = shipGrp(p[4]); sg[g] = (sg[g] || 0) + 1; });
    SHIP_GRPS.forEach(([g]) => { const el = $("sn-" + g); if (el) el.textContent = sg[g] ? " " + nf(sg[g]) : ""; });
    LAYERS.forEach(([k, , feed]) => {
      const d = $("dot-" + k), e = $("n-" + k);
      if (d) d.className = "dot " + (st[feed] ? (st[feed].ok ? "ok" : "bad") : "");
      if (e) e.textContent = n[k] != null ? nf(n[k]) : "";
    });
  }
  function hormuzKpi() {
    const h = ((S.feeds.portwatch || {}).chokepoints || []).find((c) => c.id === "chokepoint6");
    if (!h || !h.avg7) return [];
    const ch = (h.change_vs_year_pct || {}).tanker;
    return [[`${nf(h.avg7.tanker)}${ch != null ? ` (${pct(ch)})` : ""}`, "Hormuz tankers/day", ch != null && ch <= -50]];
  }
  function renderKpis() {
    const s = S.summary, pla = s.taiwan_pla || {};
    const pic = (S.ai.ov || {}).picture;
    const k = [
      [s.map_day ? "Day " + s.map_day : "–", "Source map"],
      ...(pic ? [[`${pic.overall_tension}/10 ${TREND[pic.trend] || ""}`, "Analyst tension", pic.overall_tension >= 7]] : []),
      [nf(s.events_6h), "Events, last 6h", s.events_6h > 10],
      [nf(s.events_24h), "Events, 24h"],
      ...alertKpis(), // live alerts early in the strip, so they stay in view on narrower screens
      [nf(s.thermal_corroborated), "Thermal-corroborated"],
      [nf((S.feeds.mil || {}).count ?? s.mil_aircraft), "Mil aircraft (ADS-B)"],
      [nf(s.ukmto_incidents_7d), "UKMTO incidents, 7d", s.ukmto_incidents_7d > 3],
      ...hormuzKpi(),
      [s.ru_losses_personnel_today != null ? "+" + nf(s.ru_losses_personnel_today) : "–", "RU losses (UA GS)"],
      [pla.aircraft != null ? `${pla.aircraft} / ${pla.plan_ships}` : "–", "PLA aircraft / ships"],
    ];
    $("kpis").innerHTML = k.map(([v, l, w]) => `<div class="kpi ${w === "bad" ? "bad" : w ? "warn" : ""}"><b>${esc(v)}</b><small>${esc(l)}</small></div>`).join("");
  }

  // ---------- timeline ----------
  let tlBins = [];
  function drawTimeline() {
    const cv = $("timeline"), dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
    const evs = filtered(true).filter((f) => f.properties.ts_ms);
    if (!evs.length) { tlBins = []; return; }
    const t0 = Math.floor(Math.min(...evs.map((f) => f.properties.ts_ms)) / 3600000) * 3600000;
    const t1 = Math.ceil(Math.max(...evs.map((f) => f.properties.ts_ms)) / 3600000) * 3600000;
    const n = Math.max(1, (t1 - t0) / 3600000), bw = W / n;
    const bins = Array.from({ length: n }, (_, i) => ({ t: t0 + i * 3600000, by: {} }));
    evs.forEach((f) => { const i = Math.min(n - 1, Math.floor((f.properties.ts_ms - t0) / 3600000)); bins[i].by[f.properties.theatre] = (bins[i].by[f.properties.theatre] || 0) + 1; });
    const max = Math.max(1, ...bins.map((b) => Object.values(b.by).reduce((a, c) => a + c, 0)));
    const newest = t1;
    bins.forEach((b, i) => {
      let y = H - 12;
      Object.entries(b.by).forEach(([th, c]) => {
        const h = (c / max) * (H - 16); g.fillStyle = (THEATRES[th] || ["", "#888"])[1];
        const inRange = (!S.hours || newest - b.t <= S.hours * 3600000) && (!S.brush || (b.t + 3600000 > S.brush[0] && b.t < S.brush[1]));
        g.globalAlpha = inRange ? 0.9 : 0.25; g.fillRect(i * bw + 0.5, y - h, Math.max(1, bw - 1), h); y -= h;
      });
    });
    g.globalAlpha = 1; g.fillStyle = "#5d656e"; g.font = "10px Overpass Mono, monospace";
    bins.forEach((b, i) => { const d = new Date(b.t); if (d.getUTCHours() % 12 === 0) { g.fillText(d.toISOString().slice(5, 10).replace("-", "/") + " " + String(d.getUTCHours()).padStart(2, "0") + "Z", i * bw + 2, H - 1); g.fillRect(i * bw, 0, 1, H - 12); } });
    if (S.brush) { g.strokeStyle = "#f2b33d"; g.lineWidth = 1; const x0 = ((S.brush[0] - t0) / 3600000) * bw, x1 = ((S.brush[1] - t0) / 3600000) * bw; g.strokeRect(x0, 1, x1 - x0, H - 14); }
    tlBins = { t0, bw };
  }
  (() => {
    const cv = $("timeline"); let down = null;
    const tAt = (x) => tlBins.t0 + (x / tlBins.bw) * 3600000;
    cv.addEventListener("pointerdown", (e) => { if (!tlBins.t0) return; down = e.offsetX; });
    cv.addEventListener("pointerup", (e) => {
      if (down == null) return;
      const a = Math.min(down, e.offsetX), b = Math.max(down, e.offsetX); down = null;
      if (b - a < 4) { S.brush = null; } else { S.brush = [tAt(a), tAt(b)]; S.hours = 0; [...$("range").children].forEach((x) => x.classList.toggle("on", x.dataset.h === "0")); }
      render();
    });
    $("range").onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      S.hours = +b.dataset.h; S.brush = null; [...$("range").children].forEach((x) => x.classList.toggle("on", x === b)); render();
    };
    window.addEventListener("resize", drawTimeline);
  })();

  // ---------- tabs ----------
  function openTab(t) {
    [...$("tabs").children].forEach((x) => x.classList.toggle("on", x.dataset.tab === t));
    ["feed", "alerts", "brief", "sea", "ai", "sources"].forEach((x) => $("tab-" + x).classList.toggle("hidden", x !== t));
    ({ alerts: renderAlerts, brief: renderBrief, sea: renderSea, ai: renderAnalyst, sources: renderSources })[t]?.();
  }
  $("tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) openTab(b.dataset.tab); };
  $("q").addEventListener("input", (e) => { S.q = e.target.value; render(); });
  $("btnRail").onclick = () => $("rail").classList.toggle("open");
  $("globe").onchange = (e) => map.setProjection({ type: e.target.checked ? "globe" : "mercator" });

  // ---------- analyst (model output: always escaped) ----------
  const TREND = { rising: "▲", steady: "■", easing: "▼" };
  const SIGC = ["", "#5d656e", "#8a929b", "#f2b33d", "#f2853d", "#f05252"];
  function sigBadge(a) {
    if (!a || !a.significance) return "";
    return `<span class="badge sig" style="--s:${SIGC[a.significance] || "#8a929b"}" title="Analyst: significance ${a.significance}/5, ${esc(a.confidence)}, ${esc(a.escalation)}">S${a.significance} · ${esc(a.confidence || "")}</span>`;
  }
  function aiNote(a) {
    if (!a) return "";
    const tags = (a.market_tags || []).filter((t) => t !== "none");
    return `<div class="post ai"><b>Analyst</b> <span class="badge sig" style="--s:${SIGC[a.significance] || "#8a929b"}">S${esc(a.significance)}/5</span> <span class="muted small">${esc(a.confidence)} · ${esc(a.escalation)} · ${esc(a.event_type || "")}</span>
      <div>${esc(a.summary)}</div><div class="muted small">${esc(a.rationale || "")}${tags.length ? " · market themes: " + tags.map(esc).join(", ") : ""}</div></div>`;
  }
  function renderAnalyst() {
    const ov = S.ai.ov || {}, p = ov.picture, total = ((S.events || {}).features || []).filter((f) => f.properties.kind === "event").length;
    const done = Object.keys(S.ai.ev || {}).length;
    const lvl = (n) => (n >= 8 ? "var(--bad)" : n >= 5 ? "var(--accent)" : "var(--ok)");
    const list = (a, cls) => (a && a.length ? `<ul class="${cls || ""}">${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
    const runs = (ov.runs || []).slice(0, 6).map((r) => `<li>${esc((r.stored_at || "").slice(5, 16).replace("T", " "))}Z · ${esc(r.kind)} · ${esc(r.n)} · ${esc(r.secs)}s · ${esc(r.model || "")}</li>`).join("");
    const foot = `<div class="card"><h4>Analyst runs</h4><div class="row"><span><b>${nf(done)}</b> of ${nf(total)} events analysed</span><span>writes ${ov.writes_enabled ? "enabled" : "disabled"}</span></div>${runs ? `<ul class="muted small">${runs}</ul>` : '<div class="muted small">No runs yet.</div>'}
      <div class="muted small" style="margin-top:6px">Claude reads every new event and, every few hours, the whole picture. Its notes are machine analysis of unverified reports: a lead, not a fact.</div></div>`;
    if (!p) { $("tab-ai").innerHTML = `<div class="card"><h4>Situation assessment</h4><div class="muted">No assessment yet.</div></div>` + foot; return; }
    const th = (p.theatres || []).slice().sort((a, b) => (b.status || 0) - (a.status || 0));
    $("tab-ai").innerHTML = `<div class="card ai-head"><h4>${esc(p.headline)}</h4>
        <div class="meter" title="Global tension ${esc(p.overall_tension)}/10"><i style="width:${(p.overall_tension || 0) * 10}%;background:${lvl(p.overall_tension)}"></i></div>
        <div class="row"><span>Tension <b>${esc(p.overall_tension)}/10</b> ${esc(TREND[p.trend] || "")} ${esc(p.trend)}</span><span>Confidence <b>${esc(p.confidence)}</b></span><span>${esc((p.generated_at || "").slice(5, 16).replace("T", " "))}Z</span></div>
        <div>${esc(p.bluf)}</div>${p.changes_since_last && p.changes_since_last.length ? `<div class="sub">Since last assessment</div>${list(p.changes_since_last)}` : ""}</div>` +
      th.map((t) => `<div class="card"><h4><span class="sw" style="background:${(THEATRES[t.theatre] || ["", "#888"])[1]}"></span>${esc((THEATRES[t.theatre] || [t.theatre])[0])}<span class="lvl" style="color:${lvl(t.status)}">${esc(t.status)}/10 ${esc(TREND[t.trend] || "")}</span></h4>
        <div>${esc(t.summary)}</div>${list(t.key_developments)}${t.watch && t.watch.length ? `<div class="sub">Watch</div>${list(t.watch, "muted")}` : ""}</div>`).join("") +
      ((p.indicators || []).length ? `<div class="card"><h4>Escalation indicators</h4><table class="src">${p.indicators.map((i) => `<tr><td>${esc(i.indicator)}<div class="muted small">${esc(i.note)}</div></td><td class="st st-${esc((i.state || "").replace(" ", "-"))}">${esc(i.state)}</td></tr>`).join("")}</table></div>` : "") +
      ((p.market_risk || []).length ? `<div class="card"><h4>Market risk themes</h4><ul>${p.market_risk.map((m) => `<li><b>${esc((m.theme || "").replace("_", " "))}</b> <span class="badge">${esc(m.direction)}</span> ${esc(m.why)}</li>`).join("")}</ul><div class="muted small">Geopolitical context for later trading research, not trade advice.</div></div>` : "") +
      ((p.cross_theatre || []).length ? `<div class="card"><h4>Cross-theatre links</h4>${list(p.cross_theatre)}</div>` : "") +
      ((p.gaps || []).length ? `<div class="card"><h4>Gaps</h4>${list(p.gaps, "muted")}</div>` : "") + foot;
  }

  function renderBrief() {
    api("brief").then((b) => {
      const s = S.summary;
      const head = `<div class="card"><h4>Situation picture</h4><div class="row"><span>Generated <b>${esc((b.generated || "").slice(11, 16))}Z</b></span><span>${esc(b.method)}</span></div>
        <ul><li><b>${nf(s.events_24h)}</b> curated events in the last 24h across ${Object.keys(s.events_24h_by_theatre || {}).length} theatres; <b>${nf(s.thermal_corroborated)}</b> strike/energy reports have a NASA thermal detection nearby.</li>
        <li>Maritime: <b>${nf(s.ukmto_incidents_7d)}</b> UKMTO incidents in 7 days${s.ukmto_latest ? `, latest #${s.ukmto_latest.num} ${esc(s.ukmto_latest.type)} on ${esc(s.ukmto_latest.date)} (${esc(s.ukmto_latest.where || "")})` : ""}.</li>
        <li>Ukraine: Russian losses per Ukraine's General Staff +${nf(s.ru_losses_personnel_today)} personnel (day ${nf(s.ru_losses_day)}). DeepState front snapshot ${esc((S.feeds.front || {}).updated || "–")}.</li>
        <li>Taiwan: ${(s.taiwan_pla || {}).aircraft ?? "–"} PLA aircraft, ${(s.taiwan_pla || {}).plan_ships ?? "–"} PLAN ships (MND ${esc((s.taiwan_pla || {}).date || "")}).</li>
        <li>${nf(s.airspace_czib_active)} active EASA conflict-zone airspace bulletins.</li>${briefExtra(s)}</ul></div>`;
      $("tab-brief").innerHTML = head + b.theatres.map((t) => `<div class="card"><h4><span class="sw" style="background:${(THEATRES[t.theatre] || ["", "#888"])[1]}"></span>${esc(t.label)}</h4>
        <div class="row"><span><b>${t.count}</b> events</span><span><b>${t.last_24h}</b> in 24h</span><span><b>${t.thermal}</b> thermal ✓</span></div>
        <div class="row">Mostly: ${t.top_categories.map((c) => `${esc((CATS[c.category] || CATS.other)[0])} (${c.n})`).join(", ")}</div>
        <div class="row">Hotspots: ${t.hotspots.map((h) => `${esc(h.place)} (${h.n})`).join(", ")}</div>
        <ul>${t.headlines.map((h) => `<li><a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a> <span class="muted small">${esc((h.ts || "").slice(11, 16))}Z · ${esc(h.handle || "")}</span></li>`).join("")}</ul></div>`).join("");
    });
  }
  function briefExtra(s) {
    const io = s.internet_outages, ta = s.travel_advisories, sh = s.ships_last_hour_by_area, gf = s.ship_traffic_gfw, ra = s.regional_alerts;
    let h = "";
    if (ra && ra.ukraine) {
      const le = (ra.israel || {}).latest_event;
      h += `<li>Air-raid alerts${ra.as_of ? ` (alerts.in.ua, ${esc(ra.as_of.slice(11, 16))}Z)` : ""}: Ukraine <b>${nf(ra.ukraine.n)}</b> regions (${nf(ra.ukraine.red || 0)} red), Russia <b>${nf((ra.russia || {}).n)}</b>, Poland ${nf((ra.poland || {}).n)}. Israel: ${le ? `latest alert ${esc(le.label)}, ${nf(le.n)} areas at ${esc((ra.israel.latest_event_at || "").slice(11, 16))}Z` : "no alerts in 24 h"}.</li>`;
    }
    const ue = ra && ra.us_embassies;
    if (ue && ue.alerts_24h != null) h += `<li>US embassy alerts, 24 h: <b>${nf(ue.alerts_24h)}</b>${(ue.latest || []).length ? ` (latest: ${ue.latest.slice(0, 3).map((x) => `${esc(x.post)} ${esc(x.title)}`).join("; ")})` : ""}.</li>`;
    if (io) {
      const w = io.watched_countries || [], r = io.watched_regions || [];
      h += `<li>Internet: ${w.length ? w.map((c) => `<b>${esc(c.country)}</b>${c.ongoing ? " (ongoing)" : ""}`).join(", ") : "no watched country"} with outages in ${esc(io.window_h)} h; ${nf(r.length)} regional outages in watched countries${r.length ? ` (latest ${esc(r[0].region)}, ${esc(r[0].country)})` : ""}. IODA.</li>`;
    }
    if (ta) h += `<li>US travel advisories: <b>${nf(ta.level4)}</b> countries at Level 4, ${nf(ta.level3)} at Level 3${(ta.level_changes || []).length ? `; changes: ${ta.level_changes.slice(0, 3).map((c) => `${esc(c.country)} ${esc(c.from)}→${esc(c.to)}`).join(", ")}` : `; no level changes since ${esc((ta.watching_since || "").slice(0, 10))}`}.</li>`;
    if (sh) h += `<li>Ships heard in the last hour (AIS): ${Object.entries(sh).filter(([, v]) => v.ships_1h).map(([k, v]) => `${esc(AREA_NAME(k))} ${nf(v.ships_1h)}${v.tankers != null ? ` (${nf(v.tankers)} tanker${v.tankers === 1 ? "" : "s"})` : ""}`).join(", ") || "none"}.${s.ship_types_known_pct != null ? ` Ship type known for ${nf(s.ship_types_known_pct)}%.` : ""} No volunteer AIS coverage in the Gulf or Red Sea.</li>`;
    const pwd = S.feeds.portwatch;
    if (pwd && (pwd.chokepoints || []).length) {
      const one = (c) => `${esc(c.name)} <b>${nf((c.avg7 || {}).tanker)}</b> tankers/day${(c.change_vs_year_pct || {}).tanker != null ? ` (${pct(c.change_vs_year_pct.tanker)} vs a year ago)` : ""}`;
      const pick = pwd.chokepoints.filter((c) => c.pinned).concat(pwd.chokepoints.filter((c) => !c.pinned && /suez|malacca|bosporus|panama|gibraltar/i.test(c.name)));
      h += `<li>Chokepoint transits, 7-day mean through ${esc(pwd.data_through)}: ${pick.map(one).join(", ")}. ${PW_ATTR}.</li>`;
    }
    const ls = ((S.feeds.ships || {}).listed || []).filter((x) => isSG(x.marks));
    if (ls.length) {
      const by = {}; ls.forEach((x) => [...x.marks].forEach((m) => (by[m] = (by[m] || 0) + 1)));
      h += `<li>Sanctioned or shadow-fleet ships heard on AIS in the last hour: <b>${nf(ls.length)}</b> (${[["S", "sanctioned"], ["G", "on Ukraine's GUR shadow-fleet list"]].filter(([m]) => by[m]).map(([m, t]) => `${t} ${nf(by[m])}`).join(", ")}). ${OS_ATTR}.</li>`;
    }
    if (gf && gf.areas) {
      const one = ([k, a]) => `${esc(a.label)} <b>${nf(a.avg_7d)}</b>/day${a.change_vs_last_year_pct != null ? ` (${a.change_vs_last_year_pct > 0 ? "+" : ""}${a.change_vs_last_year_pct}% vs a year ago)` : ""}`;
      const ar = Object.entries(gf.areas);
      h += `<li>Ship traffic through ${esc(gf.data_through)}: ${ar.filter(([, a]) => a.kind === "chokepoint").map(one).join(", ")}. Seas: ${ar.filter(([, a]) => a.kind === "sea").map(one).join(", ")}. ${nf((gf.ais_off_events_30d || []).length)} recent AIS-off events. ${GFW_ATTR}.</li>`;
    }
    return h;
  }
  function renderSea() {
    const d = S.feeds.ukmto || { items: [] }, g = S.feeds.gfw;
    const gfwCards = g && g.areas ? `<div class="sub" style="margin:0 0 6px">Ship traffic, non-fishing ships a day (Global Fishing Watch, through ${esc(g.data_through)})</div>` +
      Object.entries(g.areas).map(([k, a]) => `<div class="card gfwcard" data-area="${esc(k)}" style="cursor:pointer">${gfwHtml(a, false)}</div>`).join("") : "";
    $("tab-sea").innerHTML = pwTable() + listedCard() + tankerCards() + gfwCards + `<div class="muted small" style="margin-bottom:8px">UKMTO notices scraped via Firecrawl (site blocks plain clients). Positions from stated range/bearing where given, else area centroid.</div>` +
      d.items.map((i) => `<div class="card" style="cursor:${i.coord ? "pointer" : "default"}" data-c="${i.coord ? i.coord.join(",") : ""}"><h4><span class="sw" style="background:${UKMTO_COL[i.type] || "#38bdf8"}"></span>${esc(i.type)} #${i.num}<span class="muted small" style="margin-left:auto">${esc(i.date)}</span></h4><div class="small">${esc(i.text)}</div><div class="row" style="margin:6px 0 0">${esc(i.where || "unlocated")} · <a href="${esc(i.url)}" target="_blank" rel="noopener">notice ↗</a></div></div>`).join("");
    $("tab-sea").onclick = (e) => {
      if (e.target.tagName === "A") return;
      const pr = e.target.closest("[data-pw]");
      if (pr) {
        const c = ((S.feeds.portwatch || {}).chokepoints || []).find((x) => x.id === pr.dataset.pw);
        if (c) { map.flyTo({ center: [c.lon, c.lat], zoom: 6.5 }); pwPopup(c.id, [c.lon, c.lat]); }
        return;
      }
      const sr = e.target.closest("[data-ship]");
      if (sr) {
        const c = shipCard(sr.dataset.ship), f = c && ((S.feeds.ships || {}).points || []).find((q) => q[6] === c.mmsi);
        if (c) {
          map.flyTo({ center: [c.lon, c.lat], zoom: 9 });
          const [lon, lat, sog, cog, cls, name, mmsi, ts, dest, hdg, flag, marks, imo, dr, len] = f || [c.lon, c.lat, c.sog, c.cog, c.cls, c.name, c.mmsi, c.ts, c.dest, c.hdg, c.flag, c.marks, c.imo, c.dr, c.len];
          shipPopup({ sog, cog, cls, name, mmsi, ts, dest, hdg, flag, marks, imo, dr, len }, [lon, lat]);
        }
        return;
      }
      const ga = e.target.closest(".gfwcard");
      if (ga && e.target.tagName !== "A") {
        // Zoom to the area and open its popup here: other layers (e.g. the Hormuz minefield zone) can cover the box on the map.
        const a = ((S.feeds.gfw || {}).areas || {})[ga.dataset.area], r = a.ring, xs = r.map((p) => p[0]), ys = r.map((p) => p[1]);
        const w = Math.min(...xs), s = Math.min(...ys), e2 = Math.max(...xs), n = Math.max(...ys);
        map.fitBounds([[w, s], [e2, n]], { padding: 60, maxZoom: 9 });
        return showPopup([(w + e2) / 2, (s + n) / 2], `<div class="pop">${gfwHtml(a, true)}</div>`);
      }
      const c = e.target.closest(".card"); if (c && c.dataset.c && e.target.tagName !== "A") { const [lo, la] = c.dataset.c.split(",").map(Number); map.flyTo({ center: [lo, la], zoom: 8 }); } };
  }
  function pwTable() {
    const d = S.feeds.portwatch;
    if (!d || !(d.chokepoints || []).length) return "";
    const row = (c) => {
      const a = c.avg7 || {}, y = c.year_ago7 || {}, ch = (c.change_vs_year_pct || {}).tanker;
      return `<tr data-pw="${esc(c.id)}" style="cursor:pointer"><td>${c.pinned ? "<b>" + esc(c.name) + "</b>" : esc(c.name)}<div class="muted small">all ships ${nf(a.total)}/day</div></td><td class="num"><b>${nf(a.tanker)}</b></td><td class="num muted">${nf(y.tanker)}</td><td class="num" style="color:${gfwCol(ch)}">${pct(ch)}</td></tr>`;
    };
    const all = d.chokepoints, top = all.slice(0, 10), rest = all.slice(10);
    return `<div class="card"><h4>Chokepoint transits <span class="muted small" style="margin-left:auto">through ${esc(d.data_through)}</span></h4>
      <table class="src pwt"><tr><th>Chokepoint</th><th class="num" title="Tankers a day, mean of the last 7 days">Tankers</th><th class="num" title="Same dates a year earlier">Yr ago</th><th class="num">Δ</th></tr>${top.map(row).join("")}</table>
      ${rest.length ? `<details><summary class="muted small">${nf(rest.length)} more chokepoints</summary><table class="src pwt">${rest.map(row).join("")}</table></details>` : ""}
      <div class="muted small">7-day means of daily transits, against the same dates a year earlier (no percentage under 3 ships a day). About 3 days behind; ships with AIS off are not counted. ${PW_ATTR}</div></div>`;
  }
  function shipRow(c) {
    const was = c.dr_was && c.dr != null && Math.abs(c.dr_was[0] - c.dr) >= 0.2 ? (c.dr > c.dr_was[0] ? " ↑" : " ↓") : "";
    return `<li data-ship="${c.mmsi}" style="cursor:pointer">${c.marks ? markBadges(c.marks) + " " : ""}<b>${esc(c.name || "unnamed")}</b>${c.flag ? ` <span class="muted">${esc(c.flag)}</span>` : ""}` +
      ` · ${c.sog != null ? nf(c.sog) + " kt" : "–"}${c.dest ? " · to " + esc(c.dest) : ""}${c.dr != null ? ` · ${nf(c.dr)} m${was}` : ""}</li>`;
  }
  function listedCard() {
    const all = (S.feeds.ships || {}).listed || [], ls = all.filter((c) => isSG(c.marks)), dd = all.filter((c) => !isSG(c.marks));
    if (!all.length) return "";
    const row = (c) => shipRow(c).replace("</li>", `<div class="muted small">${esc(AREA_NAME(c.area))} · ${esc((c.lists || []).join(", "))} · matched on ${esc(c.match)}</div></li>`);
    return `<div class="card"><h4>Sanctioned and shadow-fleet ships heard <span class="muted small" style="margin-left:auto">last hour, AIS</span></h4>` +
      (ls.length ? `<ul class="shiplist">${ls.slice(0, 25).map(row).join("")}${ls.length > 25 ? `<li class="muted">and ${nf(ls.length - 25)} more</li>` : ""}</ul>` : `<div class="muted small">None heard in the last hour.</div>`) +
      (dd.length ? `<details><summary class="muted small">${nf(dd.length)} more with a past port-state detention only</summary><ul class="shiplist">${dd.slice(0, 40).map(row).join("")}</ul></details>` : "") +
      `<div class="muted small">IMO or MMSI on a sanctions list or Ukraine's GUR shadow-fleet list (detentions are usually safety defects). A list entry is about the ship's identifiers, not proof of what it is doing now; MMSIs get reused. ${OS_ATTR}.</div></div>`;
  }
  function tankerCards() {
    const d = S.feeds.ships;
    if (!d || !d.tankers) return "";
    const by = {};
    d.tankers.forEach((t) => (by[t.area] = by[t.area] || []).push(t));
    const areas = Object.entries(d.areas || {});
    const head = `<div class="sub" style="margin:0 0 6px">Tankers heard in the last hour (AIS)${d.typed_pct != null ? ` · ship type known for ${nf(d.typed_pct)}%` : ""}</div>`;
    return head + areas.map(([k, a]) => {
      const ts = by[k] || [];
      if (a.no_live_coverage && !ts.length) return `<div class="card"><h4>${esc(a.label)}<span class="muted small" style="margin-left:auto">no live receivers</span></h4><div class="muted small">Volunteer AIS doesn't reach here. Use the chokepoint transits above and the GFW counts below.</div></div>`;
      if (!ts.length) return "";
      return `<div class="card"><h4>${esc(a.label)}<span class="muted small" style="margin-left:auto">${nf(ts.length)} tanker${ts.length === 1 ? "" : "s"} · ${nf(a.ships_1h)} ships</span></h4><ul class="shiplist">${ts.slice(0, 12).map(shipRow).join("")}${ts.length > 12 ? `<li class="muted">and ${nf(ts.length - 12)} more (see the map)</li>` : ""}</ul></div>`;
    }).join("") + `<div class="muted small" style="margin:-4px 0 10px">Draught ↑ deeper than last time (likely loaded), ↓ shallower (likely unloaded); crews enter draught by hand. Flags are the declared flag from the MMSI.</div>`;
  }
  function renderSources() {
    api("status").then((st) => {
      S.status = st.feeds;
      const label = { mymaps: "Global War News Map (My Maps KML)", mil: "Military ADS-B (adsb.lol → adsb.fi), types from hexdb.io", front: "DeepStateMap front line", losses: "russianwarship.rip (UA General Staff)", firms: "NASA FIRMS NOAA-20 + NOAA-21 VIIRS", ukmto: "UKMTO via Firecrawl", gdelt: "GDELT 2.0 event export", tzeva: "Tzeva Adom history + Home Front Command messages", tzevalive: "Tzeva Adom live sirens (Israel)", airalerts: "alerts.in.ua SITREP (Ukraine, Russia, Poland)", embassy: "US embassy alerts (38 posts' own RSS)", pla: "Taiwan MND PLA report", czib: "EASA CZIB airspace", official: "CENTCOM + War Dept + UK MoD", cables: "TeleGeography cables", outages: "IODA internet outages (Georgia Tech)", advisories: "US State Dept travel advisories", ships: "AISStream ship positions", gfw: "Global Fishing Watch ship traffic", portwatch: "IMF PortWatch chokepoint transits", vessellists: "OpenSanctions vessel lists (sanctions, shadow fleet, detentions)" };
      $("tab-sources").innerHTML = `<table class="src"><tr><th>Feed</th><th>Status</th><th>Age</th></tr>${Object.entries(st.feeds).map(([k, v]) => `<tr><td>${esc(label[k] || k)}</td><td style="color:${v.ok ? "var(--ok)" : "var(--bad)"}">${v.ok ? "OK" : "FAIL"}${v.error ? `<div class="muted small">${esc(v.error)}</div>` : ""}</td><td class="muted">${v.age_s != null ? (v.age_s < 120 ? v.age_s + "s" : Math.round(v.age_s / 60) + "m") : "–"}</td></tr>`).join("")}</table>
        <div class="card" style="margin-top:10px"><h4>Official statements</h4><ul id="offl"></ul></div>
        <div class="muted small">Ground Truth ${esc(st.version)} · personal, non-commercial use. Content belongs to its sources; links go back to originals. Ship traffic: ${GFW_ATTR} (CC BY-NC 4.0). Aircraft types from <a href="https://hexdb.io" target="_blank" rel="noopener">hexdb.io</a>; aircraft photos © their photographers via <a href="https://www.planespotters.net" target="_blank" rel="noopener">Planespotters.net</a>. Alerts: <a href="https://www.tzevaadom.co.il/en/" target="_blank" rel="noopener">Tzeva Adom</a> and <a href="https://alerts.in.ua/en" target="_blank" rel="noopener">alerts.in.ua</a>; region shapes from Natural Earth. US embassy alerts: the posts' own feeds (US government, public domain). Chokepoint transits: ${PW_ATTR}. ${OS_ATTR}. Flags from the ITU maritime identification digits.</div>`;
      api("feed/official").then((o) => { $("offl").innerHTML = ((o.data || {}).items || []).slice(0, 10).map((i) => `<li><span class="badge">${esc(i.source)}</span> <a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a></li>`).join(""); });
    });
  }

  setInterval(() => { $("utc").textContent = new Date().toISOString().slice(11, 19); }, 1000);
})();
