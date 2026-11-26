/* Ground Truth v0.9 - watch floor client. All API paths are relative so the app runs behind a prefix.
   0.7.0: air-raid and missile alerts (Israel: Tzeva Adom; Ukraine, Russia, Poland: alerts.in.ua), Alerts tab, siren banner.
   0.8.0: US embassy alerts (38 posts' own feeds): map rings, popups, an Alerts-tab card, banner rows for shelter/departure.
   0.9.0: tankers: heading arrows, 3-hour tracks, Tankers / Cargo / Other filter, flag, IMO, draught; rings for ships on
   sanctions, shadow-fleet and detention lists (OpenSanctions); IMF PortWatch chokepoint transits (map, popup, table).
   0.9.1: source-map freshness: when Ground Truth last checked the map, and a "quiet" notice after 12 h with no new pin.
   0.10.0: source-map auto-follow: rail line (publisher checked, map moved, previous pins kept until) and a Feed notice
   for 12 h after the map moves to a new day.
   0.11.0: page extensions (window.GTX, web/ext/*.js, queued through window.GTXQ) and push: /api/stream (Server-Sent
   Events) reloads a feed as soon as the server refreshes it; the Sources tab shows each feed's freshness.
   Extensions this release: curated.js (GeoConfirmed, CIR, kinetic pins merged into the events) and hazards.js.
   0.12.0: wire.js: Wire tab (news wire and Telegram, following the rail's theatre) and news bubbles per country.
   0.13.0: signals.js (tsunami, radiation, NTAS, OFAC; Signals tab), airspace.js (emergency squawks, FAA TFRs),
   cyber.js (ransomware / critical-infrastructure / DDoS shading, routing drops; Cyber tab).
   1.0.0: Brief tab "All sources by theatre" (GTX.briefColumn, GTX API 1.1).
   1.2.0: one Feed: the map pins and every other timestamped source (wire, Telegram, official, alerts, UKMTO,
   hazards, airspace, cyber, internet), newest first, with a chip per source group (GTX.stream, GTX API 1.2).
   1.3.0: times in Eastern time (EST/EDT) by default, UTC on request (the header clock, or Times in the rail), and the
   time since next to times (GTX.when, GTX.fmtDay, GTX.zone; GTX API 1.3).
   1.4.0: every Feed item opens with a title bar (flag, country, category; stream items name their country in cc,
   GTX API 1.4); the header shows the page's version and a live light (Live / Polling / Offline / Public copy); the
   source map's Day tile leaves the header strip.
   1.4.1: the Feed row's date, time and time since move into its title bar.
   1.4.2: every map layer starts on (the four core layers that started off, and the extensions' cyber, TFR, GPSJAM, news).
   1.4.3: tooltips on a PC: a styled tooltip for every titled element, and titles for the KPI tiles, layers, tabs,
   theatres, categories, the time range and the title bar's category.
   1.5.0: mobile layout (two-row phone header, landscape columns, drawer with backdrop, popups that fit, tap targets,
   safe areas); a news ticker under the title bar (the head of the Feed, with its own SRC sources, pause and speed);
   resizable, collapsible sidebars on a PC; "View on map" on Feed rows with a place; the public copy skips the push
   stream and the post-text button.
   1.5.1: a date-only Feed row never sorts into the future (dayAt): a source ahead of the page's zone (Taiwan MND) can
   name a day that has not begun here yet.
   1.5.2: on the GitHub Pages copy the tab and window title read "Ground Truth --GitHub". (1.7.0: "Ground Truth: GitHub", set in themes/switch.js.)
   1.5.3: Feed groups Power, Web, AI / cloud and Cell for the outage layers (ext/outages.js).
   1.5.4: no change here (cache-busting only); ext/outages.js 1.1 labels the Cloudflare Radar API links.
   1.5.5: no change here (cache-busting only); ext/outages.js 1.2: Cloudflare Radar platform / cloud-region records. */
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
  const api = (p) => fetch("api/" + p, { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then((j) => (netMark(true, p, j), j), (e) => (netMark(false), Promise.reject(e)));  // 1.4.0: each reply feeds the header's live light
  // --- zone helpers (1.3.0) ---
  // Every time on the page shows in one zone: Eastern (America/New_York: EST, or EDT in summer) by default, UTC on
  // request (click the header clock, or Times in the rail). The choice is saved in this browser only, guarded so a
  // private window still works. fmtT / fmtD show a moment in that zone. fmtDay shows a date-only value (CENTCOM,
  // OFAC, daily counts) as the day it names, so a UTC day never slips back to the evening before in Eastern time.
  // when() is a moment plus the time since it.
  const ET = "America/New_York";
  let ZONE = (() => { try { return localStorage.getItem("gt-tz") === "utc" ? "utc" : "et"; } catch (e) { return "et"; } })();
  const DTF = {};
  const zparts = (ms, tz) => {
    const f = DTF[tz] || (DTF[tz] = new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "numeric",
      minute: "2-digit", second: "2-digit", hour12: true, timeZoneName: "short" }));
    const o = {}; f.formatToParts(new Date(ms)).forEach((p) => { o[p.type] = p.value; }); return o;
  };
  const etT = (ms, secs) => { const p = zparts(ms, ET); return `${p.hour}:${p.minute}${secs ? ":" + p.second : ""} ${p.dayPeriod}`; };
  const fmtT = (ms) => (ZONE === "utc" ? new Date(ms).toISOString().slice(11, 16) + "Z" : etT(ms));
  const fmtD = (ms) => { if (ZONE === "utc") return new Date(ms).toISOString().slice(5, 10).replace("-", "/"); const p = zparts(ms, ET); return p.month + "/" + p.day; };
  const fmtDay = (v) => {
    const m = typeof v === "string" && v.match(/^(\d{4})[-/](\d{2})[-/](\d{2})$/);  // a bare date is the day it names, whatever the browser's zone
    const t = m ? Date.UTC(+m[1], m[2] - 1, +m[3]) : typeof v === "number" ? v : isoMs(v);
    return Number.isFinite(t) ? new Date(t).toISOString().slice(5, 10).replace("-", "/") : "–"; };
  // Eastern's offset from UTC at a moment, in ms (4 h in EDT, 5 h in EST).
  const etOff = (ms) => { const p = zparts(ms, ET);
    return Math.round((ms - Date.UTC(+p.year, p.month - 1, +p.day, (+p.hour % 12) + (p.dayPeriod === "PM" ? 12 : 0), +p.minute, +p.second)) / 60000) * 60000; };
  // A date-only value names a UTC day (sent as its midnight, or its noon by some sources, e.g. GeoConfirmed's date-only
  // pins). dayStart is the moment that day begins in the page's zone (Eastern midnight: 05:00Z in winter, 04:00Z in
  // summer; the second step gets the two DST switch days right), so date-only rows sort and filter with that day's
  // rows instead of with the evening before.
  const dayStart = (ts) => { const d0 = Math.floor(ts / 86400000) * 86400000; return ZONE === "utc" ? d0 : d0 + etOff(d0 + etOff(d0 + 43200000)); };
  // 1.5.1: where a date-only row sits in time: the start of its day, but never later than now. A source ahead of the
  // page's zone can name a day that has not begun here yet: Taiwan MND dates its report in Taiwan time and posts it
  // about 9 AM there (8-10 PM the evening before in Eastern), so its row sat up to 4 h in the future above every newer
  // item. Such a row now sits at the moment it is drawn; its label still names the source's own day.
  const dayAt = (ts) => Math.min(dayStart(ts), Date.now());
  const zoneAbbr = (ms) => (ZONE === "utc" ? "UTC" : zparts(ms == null ? Date.now() : ms, ET).timeZoneName);  // "EST" or "EDT"
  const zoneName = () => (ZONE === "utc" ? "UTC" : "Eastern time");
  // the same moment in the other zone, for tooltips
  const altTime = (ms) => { if (ZONE !== "utc") return new Date(ms).toISOString().slice(5, 16).replace("-", "/").replace("T", " ") + "Z";
    const p = zparts(ms, ET); return `${p.month}/${p.day} ${etT(ms)} ${p.timeZoneName}`; };
  // A future time reads "in 3h" (TFR ends, expiries), not "just now".
  const ago = (ms) => { const d = Date.now() - ms, m = Math.round(Math.abs(d) / 60000);
    if (m < 1) return "just now";
    const s = m < 60 ? m + "m" : m < 2880 ? Math.round(m / 60) + "h" : Math.round(m / 1440) + "d";
    return d < 0 ? "in " + s : s + " ago"; };
  // A moment for display: date and time in the page's zone, then the time since (rel false leaves that off, for spans
  // such as "from X to Y"). Takes ms or an ISO string; a bare YYYY-MM-DD is a date-only value and shows as that day.
  const when = (v, rel) => {
    if (v == null || v === "") return "–";
    if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)) return fmtDay(v);
    const t = typeof v === "number" ? v : isoMs(v);
    if (!Number.isFinite(t)) return "–";
    return fmtD(t) + " " + fmtT(t) + (rel === false ? "" : " · " + ago(t));
  };
  // Activity-chart ticks every 12 hours of the page's zone: UTC "11/20 00Z", "11/20 12Z"; Eastern "11/20" at midnight, "noon".
  const axisLabel = (ms) => {
    if (ZONE === "utc") { const h = new Date(ms).getUTCHours(); return h % 12 ? "" : fmtD(ms) + " " + String(h).padStart(2, "0") + "Z"; }
    const p = zparts(ms, ET); return p.hour !== "12" || p.minute !== "00" ? "" : p.dayPeriod === "AM" ? p.month + "/" + p.day : "noon";
  };
  // Analyst prose is model-written in UTC ("at 05:38Z"). In Eastern mode each such time gets its Eastern time beside it,
  // "05:38Z (12:38 AM)", with the offset of ref's date (when the text was written); the words are left as written.
  // (No regex lookbehind: older iOS WebViews, such as the HA app's, would reject the whole file.)
  const zText = (s, ref) => (ZONE === "utc" || !s ? s : String(s).replace(/(^|[^\d:])([01]\d|2[0-3]):([0-5]\d)Z\b/g, (m, pre, h, mi) => {
    const d = new Date(Number.isFinite(ref) ? ref : Date.now());
    return `${pre}${h}:${mi}Z (${etT(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), +h, +mi))})`; }));
  // --- end zone helpers ---
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
    ["ships", "Ships (AIS) + warships worldwide", "ships", true],
    ["choke", "Chokepoint transits (IMF PortWatch, ~3 days behind)", "portwatch", true],
    ["gfw", "Ship traffic (GFW, ~4 days behind)", "gfw", true],
    ["outages", "Internet outages (IODA, 72h)", "outages", true],
    ["advisories", "US travel advisories (Level 3–4)", "advisories", true],  // 1.4.2: every layer starts on (as asked)
    ["gdelt", "GDELT conflict signal (2h)", "gdelt", true],
    ["czib", "EASA conflict-zone airspace", "czib", true],
    ["cables", "Submarine cables", "cables", true],
  ];
  // 1.4.2: a core layer's first visibility follows its checkbox, or its default before the list is drawn
  const layVis = (k) => { const el = document.querySelector(`#layers input[data-layer="${k}"]`), row = LAYERS.find((l) => l[0] === k); return { visibility: (el ? el.checked : !row || row[3]) ? "visible" : "none" }; };
  const GROUPS = {
    events: ["ev-halo", "ev-pt", "ev-ico", "ev-label"], overlays: ["ov-fill", "ov-line", "ov-border", "ov-lane"], front: ["front-fill", "front-line"],
    thermal: ["th-pt"], ukmto: ["uk-pt"], mil: ["mil-pt", "mil-label"], gdelt: ["gd-pt"], czib: ["cz-fill", "cz-line"], cables: ["cab-line"],
    ships: ["ship-trk", "ship-pt", "ship-mil-lbl", "ship-arrow", "ship-listed", "ais-nocov", "ais-nocov-label"], choke: ["pw-pt", "pw-label"], outages: ["out-fill", "out-line"], advisories: ["adv-fill", "adv-line"], gfw: ["gfw-fill", "gfw-line", "gfw-gap"],
    alerts: ["ar-fill", "ar-line", "ar-dash"], israel: ["il-fill", "il-line", "il-halo", "il-pt", "il-label"],
    embassy: ["em-pt", "em-label"],
  };
  // Click priority, top first; the same list sets the pointer cursor. Region fills are huge, so they come late.
  const CLICK_ORDER = ["ev-pt", "il-pt", "em-pt", "uk-pt", "mil-pt", "ship-listed", "ship-arrow", "ship-pt", "pw-pt", "gfw-gap", "th-pt", "gd-pt", "ov-line", "ov-border", "ov-lane", "il-fill",
    "ov-fill", "cz-fill", "ar-fill", "front-fill", "out-fill", "gfw-fill", "adv-fill"];
  // 0.11.0: extension registry. Each source family since 0.11 lives in web/ext/<name>.js and registers itself
  // through window.GTX (defined at the end of this file) before the map finishes loading.
  const EXT = { mapLoad: [], popups: {}, feeds: {}, events: {}, tabs: [], labels: {}, credits: [], kpis: [], counts: {}, onRender: [], legends: {}, briefCols: [] };
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
  // 1.5.0, "show us military ships around the world": military ships are their own group, shown worldwide.
  const SHIP_GRPS = [["military", "Military"], ["tanker", "Tankers"], ["cargo", "Cargo"], ["other", "Other"]];
  const shipGrp = (cls) => (cls === "tanker" || cls === "cargo" || cls === "military" ? cls : "other");
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
  // 1.6.0: pin glyphs. A source-map pin carries a My Maps icon; ICON_GLYPH names each code after the map's own
  // icon file (1571-fire, 1569-ferry, 1812-hunting = a rifleman firing, 1830-mormon = a trumpeter ...), read from
  // the map page on 2026-11-24 (gt/mymaps.py ICONS). The glyphs are drawn here in a 24-unit box, not copied.
  // fill: even-odd paths (so eye sockets and windows cut out), stroke: [path, width] with round caps.
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
  // pins from the other curated sources have no map icon: the clear categories borrow one, the rest stay a plain dot
  const CAT_GLYPH = { strike: "fire", energy: "bolt", maritime: "ship", casualty: "skull", aviation: "plane", drone: "plane", forces: "officer" };
  const glyphOf = (p) => (p.source && p.source !== "map" ? "" : ICON_GLYPH[p.icon] || (GLYPHS[p.glyph] ? p.glyph : "")) || CAT_GLYPH[p.category] || "";
  // A glyph on a canvas: ink colour, optional disc behind it ({fill, ring}); the glyph fills `scale` of the box.
  function drawGlyph(name, px, ink, disc, scale) {
    const c = document.createElement("canvas"), sh = GLYPHS[name]; c.width = c.height = px;
    const g = c.getContext("2d");
    if (disc) {
      g.beginPath(); g.arc(px / 2, px / 2, px / 2 - (disc.ring ? 1.5 : 0.5), 0, Math.PI * 2); g.fillStyle = disc.fill; g.fill();
      if (disc.ring) { g.lineWidth = Math.max(2, px / 22); g.strokeStyle = disc.ring; g.stroke(); }
    }
    if (!sh) return c;
    const k = (px / 24) * (scale || (disc ? 0.62 : 1));
    g.translate(px / 2 - 12 * k, px / 2 - 12 * k); g.scale(k, k); g.lineCap = g.lineJoin = "round";
    g.fillStyle = g.strokeStyle = ink;
    if (sh.fill) g.fill(new Path2D(sh.fill), "evenodd");
    (sh.stroke || []).forEach(([d, w]) => { g.lineWidth = w; g.stroke(new Path2D(d)); });
    return c;
  }
  const mapImage = (id, c) => map.hasImage(id) || map.addImage(id, { width: c.width, height: c.height, data: c.getContext("2d").getImageData(0, 0, c.width, c.height).data }, { pixelRatio: 2 });
  const PIN_INK = "#0d0f11";
  const glyphUrl = (name, col) => drawGlyph(name, 40, PIN_INK, { fill: col }).toDataURL();
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
    // 1.6.0: a pin badge ("pin-<glyph>-<rrggbb>": category-coloured disc, dark glyph) is drawn the first time a pin asks for it
    map.on("styleimagemissing", (e) => { const m = /^pin-([a-z]+)-([0-9a-f]{6})$/.exec(e.id); if (m && GLYPHS[m[1]]) mapImage(e.id, drawGlyph(m[1], 64, PIN_INK, { fill: "#" + m[2] })); });
    ["cables", "advisories", "outages", "gfw", "czib", "front", "alertreg", "ilarea", "overlays", "gdelt", "thermal", "gfwgap", "aisbox", "pw", "shiptrk", "ships", "ukmto", "events", "mil", "embpt", "ilpt"].forEach((id) => map.addSource(id, { type: "geojson", data: empty }));
    map.addLayer({ id: "cab-line", type: "line", source: "cables", layout: layVis("cables"), paint: { "line-color": "#22d3ee", "line-opacity": 0.28, "line-width": 0.8 } });
    map.addLayer({ id: "adv-fill", type: "fill", source: "advisories", layout: layVis("advisories"), paint: { "fill-color": ["match", ["get", "level"], 4, "#f05252", "#f2853d"], "fill-opacity": ["match", ["get", "level"], 4, 0.12, 0.07] } });
    map.addLayer({ id: "adv-line", type: "line", source: "advisories", layout: layVis("advisories"), paint: { "line-color": ["match", ["get", "level"], 4, "#f05252", "#f2853d"], "line-opacity": 0.5, "line-width": 0.8, "line-dasharray": [3, 3] } });
    map.addLayer({ id: "out-fill", type: "fill", source: "outages", paint: { "fill-color": "#a78bfa", "fill-opacity": ["case", ["get", "ongoing"], 0.3, ["get", "watched"], 0.18, 0.07] } });
    map.addLayer({ id: "out-line", type: "line", source: "outages", paint: { "line-color": "#a78bfa", "line-opacity": ["case", ["any", ["get", "ongoing"], ["get", "watched"]], 0.8, 0.3], "line-width": ["case", ["get", "ongoing"], 1.6, 0.8] } });
    map.addLayer({ id: "gfw-fill", type: "fill", source: "gfw", paint: { "fill-color": GFW_COL, "fill-opacity": ["case", ["==", ["get", "kind"], "chokepoint"], 0.22, 0.06] } });
    map.addLayer({ id: "gfw-line", type: "line", source: "gfw", paint: { "line-color": GFW_COL, "line-opacity": 0.75, "line-width": ["case", ["==", ["get", "kind"], "chokepoint"], 1.8, 1], "line-dasharray": [4, 2] } });
    map.addLayer({ id: "cz-fill", type: "fill", source: "czib", layout: layVis("czib"), paint: { "fill-color": "#f2b33d", "fill-opacity": 0.07 } });
    map.addLayer({ id: "cz-line", type: "line", source: "czib", layout: layVis("czib"), paint: { "line-color": "#f2b33d", "line-opacity": 0.6, "line-width": 1, "line-dasharray": [2, 2] } });
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
    map.addLayer({ id: "gd-pt", type: "circle", source: "gdelt", layout: layVis("gdelt"), paint: { "circle-radius": 2.6, "circle-color": "#d7dbe0", "circle-opacity": 0.4 } });
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
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, ["match", ["get", "cls"], "military", 3.6, "tanker", 2, 1.4], 6, ["match", ["get", "cls"], "military", 5.2, "tanker", 3.4, 2.6], 10, ["match", ["get", "cls"], "military", 7, 4.5]],
      "circle-color": ["get", "col"],
      "circle-opacity": ["case", ["==", ["get", "cls"], "military"], 0.95, ["get", "moving"], 0.85, 0.45],
      "circle-stroke-color": "#fff", "circle-stroke-width": ["case", ["==", ["get", "cls"], "military"], 1.3, 0] } });
    map.addLayer({ id: "ship-mil-lbl", type: "symbol", source: "ships", minzoom: 4.5, filter: ["==", ["get", "cls"], "military"], layout: {
      "text-field": ["get", "name"], "text-size": 10.5, "text-offset": [0, 1.1], "text-anchor": "top", "text-max-width": 12, "text-optional": true, "text-font": ["Open Sans Regular"] },
      paint: { "text-color": "#ffb4b4", "text-halo-color": "#0d0f11", "text-halo-width": 1.3 } });
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
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 3.6, 4, 7, 6, 9.5, 10, 12], "circle-color": ["get", "col"],  // 1.6.0: room for the glyph
      "circle-stroke-color": ["case", ["has", "thermal"], "#ff7a1a", "#0d0f11"], "circle-stroke-width": ["case", ["has", "thermal"], 2.6, 1.2],
      "circle-opacity": ["case", ["get", "est"], 0.75, 1] } });
    // 1.6.0: the badge covers its dot exactly from zoom 4 (a 64 px image at pixelRatio 2 is 32 px wide, so size = radius / 16);
    // the dot stays underneath for the click, the thermal ring and the dark edge
    map.addLayer({ id: "ev-ico", type: "symbol", source: "events", minzoom: 4, filter: ["!=", ["get", "pin"], ""], layout: {
      "icon-image": ["get", "pin"], "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 7 / 16, 6, 9.5 / 16, 10, 12 / 16],
      "icon-allow-overlap": true, "icon-ignore-placement": true }, paint: { "icon-opacity": ["case", ["get", "est"], 0.75, 1] } });
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

    EXT.mapLoad.forEach((fn) => { try { fn(map); } catch (err) { console.error("GTX extension layers", err); } });
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
    setInterval(() => S.push || loadLive(), 45000);
    setInterval(() => Date.now() - lastAll > 4 * 60000 && loadAll(), 5 * 60000);
    startPush();
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
    if (EXT.popups[id]) return EXT.popups[id](f, lngLat);
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
        <ul class="small">${c.events.map((e) => `<li>${esc(when(e.start, false))} · ${esc(e.hours)} h · ${esc(IODA_SRC[e.source] || e.source)} · score ${nf(e.score)}${e.ongoing ? " · ongoing" : ""}</li>`).join("")}</ul>
        ${regs.length ? `<div class="sub">Regions</div><ul class="small">${regs.map((r) => `<li>${esc(r.region)} · ${esc(when(r.start, false))} · ${esc(r.hours)} h · ${esc(IODA_SRC[r.source] || r.source)}</li>`).join("")}</ul>` : ""}
        <div><a href="https://ioda.inetintel.cc.gatech.edu/country/${esc(p.code)}" target="_blank" rel="noopener">IODA dashboard ↗</a></div><div class="muted small">Automatic detection. Google-traffic dips alone can be noise; routing plus probing together is the strong signal.</div></div>`);
    }
    if (id === "gfw-fill") {
      const a = ((S.feeds.gfw || {}).areas || {})[p.key];
      return a && showPopup(lngLat, `<div class="pop">${gfwHtml(a, true)}</div>`);
    }
    if (id === "gfw-gap") {
      return showPopup(lngLat, `<div class="pop"><h5>AIS switched off: ${esc(p.name || "unnamed vessel")} <span class="muted">${esc((p.type || "").replace(/_/g, " "))}</span></h5>
        <div class="meta">${esc(p.flag || "flag ?")} · MMSI ${esc(p.mmsi || "–")} · off ${esc(when(p.start, false))} for ${nf(p.hours)} h${p.km != null ? ` · back on ${nf(Math.round(p.km))} km away` : ""}</div>
        ${p.mmsi ? `<div><a href="https://www.marinetraffic.com/en/ais/details/ships/mmsi:${esc(p.mmsi)}" target="_blank" rel="noopener">MarineTraffic ↗</a></div>` : ""}
        <div class="muted small">GFW "AIS off" event (prototype model): a gap of 12 h or more starting at least 50 nm from shore where satellite reception is good. Data runs about 4 days behind. ${GFW_ATTR}</div></div>`);
    }
    if (id === "adv-fill") return showPopup(lngLat, `<div class="pop"><h5>${esc(p.country)}: Level ${esc(p.level)}</h5><div class="meta">US State Department travel advisory · updated ${esc(p.date)}</div>${esc(p.label)}<div><a href="${esc(p.url)}" target="_blank" rel="noopener">Advisory ↗</a></div></div>`);
    if (id === "th-pt") return showPopup(lngLat, `<div class="pop"><h5>Thermal anomaly</h5><div class="meta">${p.sat === "N21" ? "NOAA-21" : "NOAA-20"} VIIRS · ${esc(when(p.ts))} · conf ${esc(p.conf)} · ${esc(p.dn === "N" ? "night" : "day")}</div>Fire radiative power ${p.frp} MW.<br><span class="muted small">Could be a strike fire, a gas flare or a field fire. Corroborate before trusting.</span></div>`);
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
    if (p.thermal) extra += `<div class="post">🛰 <b>Satellite thermal corroboration:</b> ${p.thermal.n} VIIRS detection(s) within ${p.thermal.nearest_km} km, max FRP ${p.thermal.max_frp} MW, first ${esc(when(p.thermal.first))}.</div>`;
    if (p.ukmto) extra += `<div class="post">⚓ <b>UKMTO incidents within 60 km:</b> ${p.ukmto.map((u) => `#${u.num} ${esc(u.type)} (${esc(u.date)})`).join(", ")}</div>`;
    // 1.5.0: no "Load post text" on the public copy: GitHub Pages has no api/xpost, so the button could only fail
    const html = `<div class="pop"><h5>${esc(p.title)}</h5>
      <div class="meta">${glyphOf(p) ? `<img class="glico" src="${glyphUrl(glyphOf(p), cat[1])}" alt="">` : `<span style="color:${cat[1]}">●</span>`} ${esc(cat[0])}${!p.source && p.icon_label && p.icon_label !== "Other" ? ` · map pin: ${esc(p.icon_label)}` : ""} · ${p.ts_ms ? (p.ts_source === "date" ? fmtDay(p.ts_ms) + " (day only)" : fmtD(p.ts_ms) + " " + fmtT(p.ts_ms) + (p.ts_source === "batch-estimate" ? " (est.)" : "") + " · " + ago(p.ts_ms)) : "undated"} · ${esc(where || (THEATRES[p.theatre] || [p.theatre])[0])}</div>
      ${p.graphic >= 4 ? `<div class="stale">Warning: the linked footage is graphic (${esc(p.source_label || "source")} level ${p.graphic} of 5).</div>` : ""}
      <div>${({ x: "𝕏", reddit: "Reddit", telegram: "Telegram" })[p.platform] || "Web"}${p.handle ? ` · <b>${esc(p.handle)}</b>` : ""} · ${p.link_private || !p.url ? `<span class="muted">${p.url ? "private channel link (members only)" : "no source link"}</span>` : `<a href="${esc(p.url)}" target="_blank" rel="noopener">Open source ↗</a>`}</div>
      ${extra}
      ${aiNote(S.ai.ev[p.id])}
      ${p.platform === "x" && !PUBLIC ? `<div id="xpost"><button id="loadpost">Load post text</button></div>` : ""}
      ${p.description ? `<div class="post">${esc(p.description)}</div>` : ""}
      <div class="muted small" style="margin-top:6px">${p.source ? `From ${esc(p.source_label || p.source)}${p.attribution ? " · " + esc(p.attribution) : ""}.${p.source_note ? " " + esc(p.source_note) : ""} Category auto-assigned.` : "Single-curator report, unverified. Category auto-assigned."}</div></div>`;
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
  let lastAll = 0, allTimer = null;
  function loadAll() {
    lastAll = Date.now();
    Promise.allSettled([api("events"), api("summary"), api("status"), api("czib_geo"), api("feed/front"), api("feed/ukmto"),
      api("feed/firms"), api("feed/gdelt"), api("feed/cables"), api("analysis"), api("analysis/events"),
      api("outages_geo"), api("advisories_geo"), api("feed/outages"), api("feed/ships"), api("feed/gfw"), api("feed/portwatch"),
      api("feed/official"), api("feed/pla"), api("feed/losses"), api("feed/czib"), api("feed/advisories")]).then(([ev, sum, st, cz, fr, uk, fi, gd, cb, ao, ae, og, ag, ou, sh, gw, pw, ...more]) => {
      if (ao.value) S.ai.ov = ao.value;
      if (ae.value) S.ai.ev = ae.value;
      if (ev.value) S.eventsBase = ev.value;
      mergeEvents();
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
      // 1.2.0: read only by the Feed tab
      ["official", "pla", "losses", "czib", "advisories"].forEach((k, n) => { const r = more[n]; if (r.value && r.value.data) S.feeds[k] = r.value.data; });
      render();
      Object.keys(EXT.feeds).forEach((name) => loadExt(name));  // after the status reply: it says which exist
    });
    loadLive();
  }
  // 0.11.0: extension feeds. An event source's points join the curated events (map, Feed, theatre counts); the
  // source map wins on a shared id (same post URL).
  function loadExt(name, pushed) {
    const x = EXT.feeds[name];
    // Only feeds the server has run (the static public mirror has none of them); a push for one always loads it.
    if (!pushed && S.status && !(name in S.status)) return Promise.resolve();
    return api("feed/" + name).then((r) => {
      if (!r || !r.data) return;
      S.feeds[name] = r.data;
      if (x.events) { EXT.events[name] = ((r.data.geojson || {}).features || []).filter((f) => f.properties && f.properties.kind === "event"); mergeEvents(); }
      if (x.fn) { try { x.fn(r.data, r); } catch (err) { console.error("GTX feed " + name, err); } }
      if (x.events) render(); else { renderLayerCounts(); renderKpis(); feedSoon(); }
    }).catch(() => {});
  }
  // One key per post, whatever the spelling: x.com / twitter.com and handle case, t.me/s/ previews, query strings.
  function postKey(u) {
    if (!u) return null;
    const s = String(u).trim();
    let m = s.match(/(?:twitter|x)\.com\/[^/?#]+\/status(?:es)?\/(\d+)/i);
    if (m) return "x:" + m[1];
    m = s.match(/t\.me\/(?:s\/)?([^/?#]+)\/(\d+)/i);
    if (m) return "tg:" + m[1].toLowerCase() + "/" + m[2];
    return s.replace(/^https?:\/\/(www\.)?/i, "").replace(/[?#].*$/, "").replace(/\/$/, "").toLowerCase();
  }
  function mergeEvents() {
    if (!S.eventsBase) return;
    // The source map wins: an extension pin is dropped when the map already has its id or the same post.
    // Pins inside one extension feed that cite the same post at different places are kept (they have their own ids).
    const seen = new Set(S.eventsBase.features.map((f) => f.properties.id)), extra = [];
    const posts = new Set(S.eventsBase.features.map((f) => postKey(f.properties.url)).filter(Boolean));
    Object.values(EXT.events).forEach((fs) => fs.forEach((f) => {
      const p = f.properties;
      if (seen.has(p.id) || posts.has(postKey(p.url))) return;
      seen.add(p.id); extra.push(f);
    }));
    S.events = extra.length ? { ...S.eventsBase, features: S.eventsBase.features.concat(extra) } : S.eventsBase;
    const now = Date.now();
    S.events.features.forEach((f) => pinNotAhead(f.properties, now));  // 1.5.6: no pin dated after now (see notAhead)
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
    if (map.getLayer("ship-mil-lbl")) map.setFilter("ship-mil-lbl", ["all", ["==", ["get", "cls"], "military"], grp]);
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
    return (d.listed || []).find((x) => x.mmsi === m) || (d.tankers || []).find((x) => x.mmsi === m) || (d.military || []).find((x) => x.mmsi === m) || null;
  }
  function draughtHtml(dr, was) {
    if (dr == null) return "";
    let h = `draught ${nf(dr)} m`;
    if (was && Math.abs(was[0] - dr) >= 0.2) h += `, was ${nf(was[0])} m on ${esc(fmtDay(was[1]))} <span class="muted">(${dr > was[0] ? "deeper: likely loaded" : "shallower: likely unloaded"}; crews enter draught by hand, so treat it as a hint)</span>`;
    return h;
  }
  function shipPopup(p, lngLat) {
    const c = shipCard(p.mmsi) || {}, flag = p.flag || c.flag, trk = ((S.feeds.ships || {}).tracks || {})[p.mmsi];
    const lists = c.lists ? `<div class="small">${markBadges(c.marks)}<br>Listed by: ${c.lists.map(esc).join(", ")}${c.list_name && c.list_name !== (p.name || c.name) ? ` · listed as <b>${esc(c.list_name)}</b>` : ""} · matched on ${esc(c.match)}${c.url ? ` · <a href="${esc(c.url)}" target="_blank" rel="noopener">OpenSanctions ↗</a>` : ""}</div>` : (p.marks ? `<div class="small">${markBadges(p.marks)}</div>` : "");
    const dims = [p.len ? `${nf(p.len)} m long` : "", draughtHtml(p.dr ?? c.dr, c.dr_was)].filter(Boolean).join(" · ");
    return showPopup(lngLat, `<div class="pop"><h5>${esc(p.name || "Unnamed vessel")} <span class="muted">${esc(p.cls === "unknown" || !p.cls ? "type unknown" : p.cls)}</span></h5>` +
      `<div class="meta">${flag ? `Flag ${esc(regionName(flag))} (declared) · ` : ""}MMSI ${esc(p.mmsi)}${p.imo ? ` · IMO ${esc(p.imo)}` : ""} · heard ${esc(when(p.ts))}</div>` +
      `${p.sog != null ? nf(p.sog) + " kt" : "speed –"} · course ${p.cog != null ? Math.round(p.cog) + "°" : "–"}${p.dest ? " · to " + esc(p.dest) : ""}${c.eta ? ` · ETA ${esc(c.eta)} UTC` : ""}` +
      (dims ? `<div class="small">${dims}</div>` : "") + lists +
      (trk ? `<div class="muted small">Track: ${trk.length} positions over the last 3 hours (faint line).</div>` : "") +
      `<div><a href="https://www.marinetraffic.com/en/ais/details/ships/mmsi:${esc(p.mmsi)}" target="_blank" rel="noopener">MarineTraffic ↗</a></div>` +
      (p.cls === "military" ? `<div class="muted small">Military: AIS type 35 or a navy name. Most warships switch AIS off at sea or send a generic name, so this is the ships that chose to transmit. Shown worldwide for 3 hours after it was last heard.</div>` : "") +
      `<div class="muted small">AISStream, volunteer receivers. Positions are self-reported and can be spoofed; the flag comes from the MMSI.${c.lists || p.marks ? " A list entry is about the ship's identifiers, not proof of what it is doing now. " + OS_ATTR + "." : ""}</div></div>`);
  }
  function pwSpark(sp, w = 300, h = 44) {
    if (!sp || sp.length < 2) return "";
    const mx = Math.max(1, ...sp.map((r) => r[2] || 0)), x = (i) => (i * w / (sp.length - 1)).toFixed(1), y = (v) => (h - 2 - (v || 0) * (h - 4) / mx).toFixed(1);
    const line = (j, col, wd) => `<polyline fill="none" stroke="${col}" stroke-width="${wd}" points="${sp.map((r, i) => x(i) + "," + y(r[j])).join(" ")}"/>`;
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Daily ships (grey) and tankers (gold), last ${sp.length} days">${line(2, "#6b7480", 1.2)}${line(1, SHIP_COL.tanker, 1.8)}</svg>` +
      `<div class="sparkax"><span>${esc(fmtDay(sp[0][0]))}</span><span>tankers (gold) and all ships (grey) a day</span><span>${esc(fmtDay(sp[sp.length - 1][0]))}</span></div>`;
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
  // 1.7.0: the tab title ("Ground Truth: Local / Server / GitHub") is set for every theme in themes/switch.js
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
  const tzT = (ms, tz) => new Date(ms).toLocaleTimeString("en-US", { timeZone: tz, hour: "numeric", minute: "2-digit" });  // 1.7.1: am/pm
  const span = (s) => { const m = Math.max(0, Math.round(s / 60)); return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0") + " min"; };
  const agoS = (s) => (s < 120 ? Math.max(0, Math.round(s)) + " s ago" : span(s) + " ago");
  const isoMs = (s) => (s ? Date.parse(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? s.replace(" ", "T") + "Z" : /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? s + "Z" : s) : null);  // 1.3.0: a time with no zone is the server's UTC, never the browser's (1.5.6: "YYYY-MM-DD HH:MM" too, which Chrome reads as browser-local)
  const httpsUrl = (u) => (/^https:\/\//i.test(u || "") ? u : null);
  const REDUCED = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  let REG = new Map(); // ISO 3166-2 code -> region shape (Natural Earth, simplified)
  const REG_GEO = fetch("geo/alert-regions.json?v=0.7.0").then((r) => r.json()).then((fc) => { REG = new Map(fc.features.map((f) => [f.id, f])); }).catch(() => {});
  const IL = { key: "", siren: [], shelter: [], early: [], ended: [], recent: [], byKey: {}, earlyTitle: "" };
  let regSig = "", bannerHtml = "", pulsing = false;

  function loadAlerts() {
    apiRev("alerts").then((a) => {
      S.alerts = a;
      renderRegions(); renderIsrael(true); renderEmbassy(); renderKpis(); renderLayerCounts(); feedSoon();
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
      `<div class="muted small" style="margin:2px 2px 12px">Israel: <a href="https://www.tzevaadom.co.il/en/" target="_blank" rel="noopener">Tzeva Adom</a> relays Home Front Command alerts. Ukraine, Russia, Poland: the <a href="https://alerts.in.ua/en" target="_blank" rel="noopener">alerts.in.ua</a> situation report, Kyiv times shown in ${zoneName()}. Region shapes: Natural Earth. US embassy alerts: each post's own feed (public domain). All sources are free and keyless. ${esc(NOT_SAFETY)}</div>`;
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
  const pinOf = (p) => { const g = glyphOf(p); return g ? "pin-" + g + "-" + (CATS[p.category] || CATS.other)[1].slice(1).toLowerCase() : ""; };
  function render() {
    if (!S.events) return;
    const list = filtered();
    const newest = Math.max(...S.events.features.map((f) => f.properties.ts_ms || 0));
    const ids = new Set(list.map((f) => f.properties.id));
    map.getSource("events").setData({ type: "FeatureCollection", features: list.map((f) => ({ ...f, properties: { ...f.properties,
      col: (CATS[f.properties.category] || CATS.other)[1], pin: pinOf(f.properties), recent: !!f.properties.ts_ms && newest - f.properties.ts_ms < 6 * 3600000,
      est: f.properties.ts_source === "batch-estimate" } })) });
    map.getSource("overlays").setData({ type: "FeatureCollection", features: S.events.features.filter((f) => f.properties.kind === "overlay" && (S.theatre === "global" || f.properties.theatre === S.theatre)) });
    safeFeed(list);
    renderTheatreCounts();
    renderKpis();
    renderLayerCounts();
    EXT.onRender.forEach((fn) => { try { fn(list); } catch (err) { console.error("GTX render", err); } });
    drawTimeline();
    if (!$("tab-brief").classList.contains("hidden")) renderBrief();
    if (!$("tab-sea").classList.contains("hidden")) renderSea();
    if (!$("tab-sources").classList.contains("hidden")) renderSources();
    if (!$("tab-ai").classList.contains("hidden")) renderAnalyst();
    const fr = srcFresh();
    $("mapsrc").innerHTML = `Source map: <b>${esc(S.summary.map_title || "")}</b><br>${nf(S.summary.events_total)} events · newest ${fr.newest ? ago(fr.newest) : "–"}`
      + `${fr.stale ? ` <span class="badge stale">quiet ${forH(fr.ageH)}</span>` : ""}<br>${fr.checked ? "Checked " + ago(fr.checked) : "Not checked yet"}`
      + `${fr.ok ? "" : ' · <span class="badge stale bad">check failing</span>'}${followLine(fr.follow)}<br>Archived snapshots power history; see Sources.`;
    void ids;
  }
  // 0.9.1: source-map freshness. The curator's map can go quiet (no new pins) while Ground Truth keeps checking it
  // every 15 min; the time filters count back from the newest pin, so a quiet map would otherwise look current.
  const STALE_H = 12;
  const forH = (h) => (h < 48 ? Math.round(h) + " h" : Math.round(h / 24) + " days");
  function srcFresh() {
    const newest = ((S.eventsBase || {}).features || []).reduce((m, f) => Math.max(m, f.properties.ts_ms || 0), 0) || null;
    const chk = (S.status || {}).mymaps || {};
    const ageH = newest ? (Date.now() - newest) / 3600000 : null;
    return { newest, ageH, stale: ageH != null && ageH >= STALE_H, checked: isoMs(chk.at), ok: chk.ok !== false,
      follow: (S.summary || {}).map_follow || null };
  }
  // 0.10.0: auto-follow. The curator starts a new map about weekly; the server reads the publisher's feed for the
  // newest map link, switches to it, and keeps the previous map's pins for a while. Only days and times reach here.
  const MOVED_NOTICE_H = 12;
  const followOn = (fo) => !!(fo && fo.enabled && fo.ok !== false);
  const movedRecently = (fo) => !!(fo && fo.switched_at && Date.now() - isoMs(fo.switched_at) < MOVED_NOTICE_H * 3600000);
  function followLine(fo) {
    if (!fo || !fo.enabled) return "";
    const until = fo.overlap_until ? isoMs(fo.overlap_until) : null;
    return `<br>Auto-follow ${fo.ok === false ? '<span class="badge stale bad">failing</span>' : "on"}`
      + ` · publisher checked ${fo.checked_at ? ago(isoMs(fo.checked_at)) : "–"}`
      + (fo.switched_at && Date.now() - isoMs(fo.switched_at) < 7 * 86400000 ? ` · moved to Day ${fo.map_day} ${ago(isoMs(fo.switched_at))}` : "")
      + (until ? ` · Day ${fo.previous_day} pins kept to ${fmtD(until)} ${fmtT(until)}` : "");
  }
  function renderSrcNotice() {
    const fr = srcFresh(), el = $("srcstale"), chk = fr.checked ? "checked it " + ago(fr.checked) : "has not checked it yet";
    if (!fr.ok) {
      el.className = "stale bad";
      el.innerHTML = `<b>Source map check failing.</b> Last good check ${fr.checked ? ago(fr.checked) : "never"}, so the pins below may be out of date. See Sources.`;
    } else if (fr.stale) {
      el.className = "stale";
      el.innerHTML = `<b>Source map quiet: no new pins for ${forH(fr.ageH)}</b> (newest ${fmtD(fr.newest)} ${fmtT(fr.newest)}). `
        + (followOn(fr.follow)
          ? `Ground Truth ${chk}, and auto-follow checked the publisher ${ago(isoMs(fr.follow.checked_at))} and found no newer map, so the curator has added nothing since. `
          : `Ground Truth ${chk}; the curator has added nothing since (paused, or moved to a new map). `)
        + `For map pins, 6h / 24h count back from the newest pin; the other sources count back from now.`;
    } else if (movedRecently(fr.follow)) {
      const fo = fr.follow, until = fo.overlap_until ? isoMs(fo.overlap_until) : null;
      el.className = "stale info";
      el.innerHTML = `<b>Source map moved to Day ${fo.map_day}.</b> The publisher started a new map; Ground Truth switched to it `
        + `automatically ${ago(isoMs(fo.switched_at))}${until && fo.previous_day != null ? ` and keeps the Day ${fo.previous_day} pins until ${fmtD(until)} ${fmtT(until)}` : ""}.`;
    } else {
      el.className = "stale hidden";
      el.textContent = "";
    }
    return fr;
  }
  // ---------- 1.2.0: one Feed for every source ----------
  // The Feed tab lists the map pins (the curated source map, plus GeoConfirmed, CIR and S2 pins) and every other
  // timestamped source, newest first. Each source registers a stream (core ones below, the rest in web/ext/*.js):
  //   GTX.stream({key, group, label, data: () => object or null, items: (data) => [item]})
  //   item = {id, ts (ms), day (true: the source gives a date only), title, url, where, th (theatre or [theatres]),
  //           cat (a CATS key, for the rail's category filter), ll ([lon, lat] to fly to), zoom, text (searched), badge, pop,
  //           cc (1.4.0: the country for the title bar, ISO-3/ISO-2/name or an array, primary first; unset when the source has none)}
  // items() runs again only when data() returns a new object. Map pins keep their own time rule (6h / 24h count back
  // from the newest pin); stream items count back from now. A stream item citing a post the map already pins is dropped.
  const FG = {
    map: ["Map pins", "#e4e7ea"], wire: ["Wire", "#cbd5e1"], telegram: ["Telegram", "#7dd3fc"], official: ["Official", "#818cf8"],
    alerts: ["Alerts", "#fde047"], maritime: ["Maritime", "#38bdf8"], hazards: ["Hazards", "#f2853d"], airspace: ["Airspace", "#93c5fd"],
    cyber: ["Cyber", "#2dd4bf"], internet: ["Internet", "#5eead4"],
    power: ["Power", "#f59e0b"], web: ["Web", "#a78bfa"], cloud: ["AI / cloud", "#f472b6"], cell: ["Cell", "#4ade80"],
  };
  const STREAMS = [], FEED_STEP = 300, DAY = 86400000;
  let feedLimit = FEED_STEP, feedRows = [], feedTimer = null, feedPins = [];
  const feedOff = new Set((() => { try { return JSON.parse(localStorage.getItem("gt-feed-off") || "[]"); } catch (err) { return []; } })());
  // country -> [theatre, lon, lat, name], from tools/build_theatres.py (the server's own placement rule)
  let TH = { a3: {}, a2: {}, names: {} };
  fetch("geo/theatres.json?v=1.7.1").then((r) => r.json()).then((t) => { TH = t; STREAMS.forEach((st) => { st._d = null; }); feedSoon(); }).catch(() => {});
  function country(k) {
    if (!k) return null;
    const s = String(k).trim(), u0 = s.toUpperCase();  // ISO-3, ISO-2, or a name ("Côte d’Ivoire", "Mexico Travel Advisory")
    // 1.4.0: theatres.json keys a few places by Natural Earth's code, not ISO-3 (GDACS sends SSD for South Sudan)
    const u = ({ SSD: "SDS", PSE: "PSX", XKX: "KOS", ESH: "SAH", ALA: "ALD" })[u0] || u0;
    const a3 = s.length === 3 && TH.a3[u] ? u : s.length === 2 ? TH.a2[u] : TH.names[s.toLowerCase().replace(/[’`]/g, "'").replace(/\s+travel advisory$/, "")];
    const r = a3 && TH.a3[a3];
    return r ? { a3, th: r[0] || null, ll: r[1] != null ? [r[1], r[2]] : null, name: r[3] } : null;
  }
  const dayMs = (d) => { const m = String(d || "").match(/^(\d{4})[-/](\d{2})[-/](\d{2})/); return m ? Date.UTC(+m[1], m[2] - 1, +m[3]) : null; };
  // --- 1.4.0 title bar: every Feed item opens with a bar of flag, country and category. The country comes from the
  // item's cc (ISO-3, ISO-2 or a name; an array lists the primary first) or a map pin's own country; with none, the
  // bar names the theatre (or Global) instead of guessing. Flags are emoji where the system draws them; Windows
  // draws two letters instead, so there the bar shows the ISO-2 code in a small box.
  const ccList = (cc) => {
    const ks = (Array.isArray(cc) ? cc : cc ? [cc] : []).map(country).filter(Boolean);
    return ks.filter((k, n) => ks.findIndex((x) => x.a3 === k.a3) === n);
  };
  let a2of = {}, a2src = null;
  const iso2 = (a3) => {
    if (a2src !== TH) { a2src = TH; a2of = {}; Object.entries(TH.a2 || {}).forEach(([c2, c3]) => { a2of[c3] = c2; }); }
    return a2of[a3] || null;
  };
  const FLAGS = (() => {
    try {
      const g = document.createElement("canvas").getContext("2d"); g.font = "32px sans-serif";
      const one = g.measureText("\u{1F1FA}").width, two = g.measureText("\u{1F1FA}\u{1F1E6}").width;  // a flag is one glyph
      return one > 0 && two < one * 1.5;
    } catch (err) { return false; }
  })();
  const flag = (a3) => {
    const c = iso2(a3);
    if (!c) return "";
    return FLAGS ? `<span class="fl" aria-hidden="true">${String.fromCodePoint(...[...c].map((ch) => 0x1f1a5 + ch.charCodeAt(0)))}</span>`
      : `<span class="fl tx" aria-hidden="true">${c}</span>`;
  };
  const flag2 = (c) => (!/^[A-Z]{2}$/.test(c || "") ? "" : FLAGS ? `<span class="fl" aria-hidden="true">${String.fromCodePoint(...[...c].map((ch) => 0x1f1a5 + ch.charCodeAt(0)))}</span>`
    : `<span class="fl tx" aria-hidden="true">${c}</span>`);  // 1.5.0: from an ISO-2 code (a ship's MMSI flag)
  const thName = (th) => { const t = Array.isArray(th) ? th[0] : th; return t && THEATRES[t] ? THEATRES[t][0] : null; };
  // 1.4.1: the bar also carries the row's date, time and time since (asked for: "move date and time to title bar", "and
  // the minutes ago text"), between the place and the category; a long country name gives way first.
  const SHORT = { USA: "United States", COD: "DR Congo" };
  function titleBar(ks, alt, cat, when) {
    const k = ks[0], more = ks.slice(1).map((x) => SHORT[x.a3] || x.name);
    const place = k ? `${flag(k.a3)}<span class="cn" title="${esc(k.name)}">${esc(SHORT[k.a3] || k.name)}</span>${more.length ? `<span class="mo" title="${esc(more.join(", "))}">+${more.length}</span>` : ""}`
      : `${alt[0] ? `<span class="fl" aria-hidden="true">${alt[0]}</span>` : ""}<span class="cn${alt[0] ? " gl" : ""}">${esc(alt[1])}</span>`;
    return `<div class="tb">${place}${when ? `<span class="wh">${when}</span>` : ""}<span class="ct" title="Category: ${esc(cat)}">${esc(cat)}</span></div>`;
  }
  // --- end title bar
  const linkUrl =(u) => (/^https?:\/\//i.test(u || "") ? u : null);
  function stream(o) { STREAMS.push(o); feedSoon(); }
  function feedSoon() { if (!feedTimer) feedTimer = setTimeout(() => { feedTimer = null; safeFeed(); }, 250); }
  function safeFeed(list) { try { renderFeed(list); } catch (err) { console.error("Feed", err); } }
  // ---------- 1.5.0: news ticker under the title bar ----------
  // Asked for: "a news ticker that goes below the main title bar with the most recent news feed, make it auto update",
  // "keep country flag and time since", "look like official news station ticker". It is the head of the Feed (same
  // theatre, category, range, source-chip and search filters), newest first, leaving out date-only rows (no time
  // since). It is rebuilt whenever the Feed is, only when its items change, and the crawl keeps its place across a
  // rebuild. Hover or keyboard focus on the headlines holds it, and the wheel scrolls it; with reduced motion it is a
  // still strip you can swipe or scroll. "make ticker speed adjustable": a pause button and a speed button (0.5x to
  // 3x: click for the next, wheel or arrow keys up and down), both saved per browser. "add a ticker source filter
  // too": a SRC menu of the Feed's source groups; the ticker follows it instead of the Feed's source chips (theatre,
  // time range, categories, brush and search still follow the Feed). Saved per browser. "organize ticker feed by
  // category": the crawl runs in segments, one per category in the Feed's category order (strikes first, uncategorised
  // news last), each opened by a coloured category block and holding that category's newest items, newest first.
  const TICK_PER = 4, TICK_OTHER = 6;  // newest items per category segment, and in the last "other news" one
  const TICK_PX = 64, TICK_NEW = 15 * 60000;  // crawl speed at 1x (px/s), "NEW" tag age
  const tickCat = (r) => { const c = r.pin ? r.pin.properties.category : r.it.cat; return c && CATS[c] ? c : "other"; };
  const TICK_SPEEDS = [0.5, 0.75, 1, 1.5, 2, 3];
  const tkPref = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (err) { return d; } };
  const tkSave = (k, v) => { try { localStorage.setItem(k, String(v)); } catch (err) { /* private mode: this visit only */ } };
  const tk = { rows: [], key: "", x: 0, w: 0, last: 0, hold: 0, view: $("tkview"), track: $("tktrack"),
    speed: TICK_SPEEDS.includes(+tkPref("gt-ticker-speed", 1)) ? +tkPref("gt-ticker-speed", 1) : 1,
    paused: tkPref("gt-ticker-paused", "0") === "1", all: [], groups: [], counts: {},
    off: new Set((() => { try { const a = JSON.parse(tkPref("gt-ticker-off", "[]")); return Array.isArray(a) ? a.map(String) : []; } catch (err) { return []; } })()) };
  function tickItem(r, n, copy) {
    let ks, alt, title, cat, ts, src;
    if (r.pin) {
      const p = r.pin.properties;
      const sea = p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : "";  // as the Feed row's bar
      ks = ccList([p.country, p.country_name]); alt = p.country_name ? ["", p.country_name] : sea ? ["🌊", sea] : ["🌐", thName(p.theatre) || "Global"];
      title = p.title; cat = CATS[p.category] || CATS.other; ts = p.ts_ms; src = p.source_label || p.source || "Source map";
    } else {
      const i = r.it;
      ks = i.cn || []; alt = ["🌐", thName(i.th) || "Global"]; title = i.title; ts = i.ts; src = i.label;
      if (i.tr) src += ` · translated from ${langName(i.tr.from)}: ${i.tr.orig}`;
      cat = (i.cat && i.cat !== "other" && CATS[i.cat]) || FG[i.group] || FG.map;
    }
    const k = ks[0];
    const place = k ? `${flag(k.a3)}<b class="tk-c">${esc(SHORT[k.a3] || k.name)}</b>` : `${alt[0] ? `<span class="fl" aria-hidden="true">${alt[0]}</span>` : ""}<b class="tk-c">${esc(alt[1])}</b>`;
    return `<button type="button" class="tk-i" data-tk="${n}" data-ts="${ts}"${copy ? ' tabindex="-1"' : ""} style="--c:${cat[1]}"`
      + ` title="${esc(title)}\n${esc(cat[0])} · ${esc(src)} · ${esc(altTime(ts))}\n${r.pin || (r.it && r.it.ll) ? "Click to show it on the map" : "Click to open the source"}">`
      + `${Date.now() - ts < TICK_NEW ? '<span class="tk-new">NEW</span>' : ""}${place}<span class="tk-h">${esc(title)}</span>`
      + `<span class="tk-ag">${ago(ts)}</span></button>`;
  }
  // all: the Feed's rows before its source chips, as renderFeed builds them (any order).
  function renderTicker(all) {
    if (!tk.track) return;
    if (all) tk.all = all;
    const timed = tk.all.filter((r) => (r.pin ? r.pin.properties.ts_source !== "date" && r.pin.properties.ts_ms > 0 : !r.it.day));
    tk.groups = ["map", ...STREAMS.map((st) => st.group)].filter((g, n, a) => a.indexOf(g) === n);
    tk.counts = {}; timed.forEach((r) => { tk.counts[r.group] = (tk.counts[r.group] || 0) + 1; });
    tickSrcLabel();
    const by = {};
    timed.filter((r) => !tk.off.has(r.group)).sort((a, b) => b.ts - a.ts).forEach((r) => { const c = tickCat(r); (by[c] || (by[c] = [])).push(r); });
    const segs = Object.keys(CATS).filter((c) => by[c]).map((c) => ({ c, total: by[c].length, rows: by[c].slice(0, c === "other" ? TICK_OTHER : TICK_PER) }));
    const list = segs.flatMap((g) => g.rows);
    const key = segs.map((g) => g.c + ":" + g.total + ":" + g.rows.map((r) => (r.pin ? r.pin.properties.id : r.it.id || r.it.title) + "@" + r.ts).join(",")).join("|");
    if (key === tk.key) return;
    tk.key = key; tk.rows = list;
    if (!list.length) {
      tk.track.innerHTML = `<span class="tk-empty">${tk.groups.every((g) => tk.off.has(g)) ? "Every ticker source is off: choose some under SRC" : "No timed items match the filters"}</span>`;
      tk.w = 0; tk.x = 0; tk.track.style.transform = ""; return;
    }
    const runOf = (copy) => { let n = 0; return segs.map((g) => {
      const [name, col] = CATS[g.c], label = g.c === "other" ? "Other news" : name;
      return `<span class="tk-cat${g.c === "other" ? " tk-oth" : ""}" style="--c:${col}" title="${esc(label)}: the newest ${g.rows.length} of ${nf(g.total)} timed items">${esc(label)}</span>`
        + g.rows.map((r) => tickItem(r, n++, copy)).join(""); }).join(""); };
    // Two copies make the loop seamless; the second is hidden from screen readers and the tab order.
    tk.track.innerHTML = `<div class="tk-run">${runOf(false)}</div>` + (REDUCED ? "" : `<div class="tk-run" aria-hidden="true">${runOf(true)}</div>`);
    tickMeasure();
  }
  function tickMeasure() {
    // each copy is at least as wide as the strip, so even a short list loops without a gap
    if (tk.view) tk.track.style.setProperty("--tk-vw", tk.view.clientWidth + "px");
    const first = tk.track && tk.track.firstElementChild;
    tk.w = first && first.classList.contains("tk-run") ? first.offsetWidth : 0;
    if (tk.w) tickPaint();  // keep the crawl's place after a rebuild or a resize
  }
  // The crawl's offset always stays in (-w, 0], whichever way it moved.
  const tickPaint = () => { if (!tk.w || REDUCED) return; tk.x = -(((-tk.x % tk.w) + tk.w) % tk.w); tk.track.style.transform = `translate3d(${tk.x.toFixed(1)}px,0,0)`; };
  function tickFrame(t) {
    const dt = tk.last ? Math.min(0.1, (t - tk.last) / 1000) : 0; tk.last = t;
    if (!tk.hold && !tk.paused && tk.w) { tk.x -= TICK_PX * tk.speed * dt; tickPaint(); }
    requestAnimationFrame(tickFrame);
  }
  function tickCtl() {
    const pb = $("tkpause"), sp = $("tkspeed");
    if (pb) {
      pb.textContent = tk.paused ? "▶" : "❚❚"; pb.setAttribute("aria-pressed", String(tk.paused));
      pb.title = tk.paused ? "Play the ticker" : "Pause the ticker"; pb.setAttribute("aria-label", pb.title);
    }
    if (sp) {
      sp.textContent = tk.speed + "×";
      sp.title = `Ticker speed ${tk.speed}×: click for the next speed; the wheel or arrow keys go up and down`;
      sp.setAttribute("aria-label", `Ticker speed ${tk.speed} times`);
    }
  }
  // ---- the SRC menu: one checkbox per source group, with All and None
  function tickSrcLabel() {
    const b = $("tksrc"); if (!b) return;
    const on = tk.groups.filter((g) => !tk.off.has(g)).length;
    b.textContent = on === tk.groups.length ? "SRC" : `SRC ${on}/${tk.groups.length}`;
    b.title = `Ticker sources: ${on === tk.groups.length ? "all" : on + " of " + tk.groups.length} on. Click to choose (saved per browser); the theatre, time range, categories and search follow the Feed`;
  }
  const tickOffSave = () => tkSave("gt-ticker-off", JSON.stringify([...tk.off]));
  const tickMenuAway = (e) => { if (!e.target.closest("#tkmenu, #tksrc")) tickMenu(false); };
  function tickMenu(open) {
    const b = $("tksrc"), old = $("tkmenu");
    if (old) old.remove();
    document.removeEventListener("pointerdown", tickMenuAway, true);
    if (b) b.setAttribute("aria-expanded", String(!!open));
    if (!open || !b) return;
    const m = document.createElement("div");
    m.id = "tkmenu"; m.className = "tk-menu"; m.setAttribute("role", "group"); m.setAttribute("aria-label", "Ticker sources");
    m.innerHTML = `<div class="tk-mh"><b>Ticker sources</b><button type="button" class="chip" data-tkall="1">All</button><button type="button" class="chip" data-tkall="0">None</button></div>`
      + tk.groups.map((g) => { const [name, c] = FG[g] || [g, "#9ca3af"];
        return `<label class="tk-mi"><input type="checkbox" data-tkg="${esc(g)}"${tk.off.has(g) ? "" : " checked"}><i style="background:${c}"></i><span>${esc(name)}</span><span class="muted">${nf(tk.counts[g] || 0)}</span></label>`; }).join("")
      + '<p class="tk-mf">Counts are timed items now. The theatre, time range, categories and search follow the Feed.</p>';
    document.body.appendChild(m);
    const r = b.getBoundingClientRect();
    m.style.top = Math.round(r.bottom + 6) + "px"; m.style.right = Math.round(Math.max(8, window.innerWidth - r.right)) + "px";
    const sync = () => { m.querySelectorAll("[data-tkg]").forEach((x) => { x.checked = !tk.off.has(x.dataset.tkg); }); tickOffSave(); renderTicker(); };
    m.addEventListener("change", (e) => { const g = e.target.dataset && e.target.dataset.tkg; if (!g) return; if (e.target.checked) tk.off.delete(g); else tk.off.add(g); sync(); });
    m.addEventListener("click", (e) => { const a = e.target.closest("[data-tkall]"); if (!a) return; if (a.dataset.tkall === "1") tk.off.clear(); else tk.groups.forEach((g) => tk.off.add(g)); sync(); });
    m.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); tickMenu(false); b.focus(); } });
    setTimeout(() => document.addEventListener("pointerdown", tickMenuAway, true), 0);
    const first = m.querySelector("input"); if (first) first.focus({ preventScroll: true });
  }
  function tickSpeed(dir) {  // dir 0: next, wrapping round; +1 / -1: up or down, stopping at the ends
    const n = TICK_SPEEDS.indexOf(tk.speed), m = TICK_SPEEDS.length;
    tk.speed = TICK_SPEEDS[dir ? Math.max(0, Math.min(m - 1, n + dir)) : (n + 1) % m];
    tkSave("gt-ticker-speed", tk.speed); tickCtl();
  }
  function tickAgo() {
    if (!tk.track) return;
    const now = Date.now();
    tk.track.querySelectorAll(".tk-i").forEach((b) => {
      const ts = +b.dataset.ts, a = b.querySelector(".tk-ag"), nw = b.querySelector(".tk-new");
      if (a) a.textContent = ago(ts);
      if (nw && now - ts >= TICK_NEW) nw.remove();
    });
  }
  // Opens a Feed row: a map pin or a placed item flies there with its popup; an unplaced item opens its source.
  function openRow(r, viaLink) {
    if (!r) return;
    if (r.it) {
      const i = r.it;
      if (!i.ll) { const u = linkUrl(i.url); if (u && !viaLink) window.open(u, "_blank", "noopener"); return; }
      map.flyTo({ center: i.ll, zoom: Math.max(map.getZoom(), i.zoom || 5), speed: 1.6 });
      let shown = false;
      if (i.pop) { try { i.pop(); shown = true; } catch (err) { /* the map layer is not drawn yet */ } }
      if (!shown) {  // a stream without its own popup: a plain one, so "View on map" always opens the item
        const u = linkUrl(i.url);
        showPopup(i.ll, `<div class="pop"><h5>${esc(i.title)}</h5><div class="meta">${esc(i.label || "")} · ${esc(when(i.ts))}</div>`
          + `${i.text ? `<div class="small">${esc(i.text)}</div>` : ""}${u ? `<div><a href="${esc(u)}" target="_blank" rel="noopener">Open the source ↗</a></div>` : ""}</div>`);
      }
    } else {
      const id = r.pin.properties.id, f = (S.events || { features: [] }).features.find((x) => x.properties.id === id) || r.pin;
      map.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.getZoom(), 6.5), speed: 1.6 });
      eventPopup(f, f.geometry.coordinates);
    }
    if (window.innerWidth <= 900) window.scrollTo(0, 0);
  }
  if (tk.track) {
    // Only the headlines hold the crawl, so it keeps moving while the speed buttons are used.
    const el = tk.view, hold = (on) => { tk.hold = Math.max(0, tk.hold + (on ? 1 : -1)); };
    el.addEventListener("mouseenter", () => hold(true));
    el.addEventListener("mouseleave", () => hold(false));
    el.addEventListener("focusin", () => hold(true));
    el.addEventListener("focusout", () => hold(false));
    // touch: a finger on the strip holds it, and it moves on two seconds after the finger lifts
    el.addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse") { hold(true); setTimeout(() => hold(false), 2500); } });
    el.addEventListener("click", (e) => { const b = e.target.closest("[data-tk]"); if (b) openRow(tk.rows[+b.dataset.tk]); });
    el.addEventListener("wheel", (e) => {  // browse a held or paused strip
      if (!tk.w || REDUCED) return;
      e.preventDefault(); tk.x -= Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY; tickPaint();
    }, { passive: false });
    const pb = $("tkpause"), sp = $("tkspeed"), src = $("tksrc");
    if (src) src.addEventListener("click", () => tickMenu(src.getAttribute("aria-expanded") !== "true"));
    window.addEventListener("resize", () => tickMenu(false));
    if (pb) pb.addEventListener("click", () => { tk.paused = !tk.paused; tkSave("gt-ticker-paused", tk.paused ? 1 : 0); tickCtl(); });
    if (sp) {
      sp.addEventListener("click", () => tickSpeed(0));
      sp.addEventListener("wheel", (e) => { e.preventDefault(); tickSpeed(e.deltaY < 0 ? 1 : -1); }, { passive: false });
      sp.addEventListener("keydown", (e) => {
        const d = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1 }[e.key];
        if (d) { e.preventDefault(); tickSpeed(d); }
      });
    }
    tickCtl();
    if (window.ResizeObserver) new ResizeObserver(tickMeasure).observe(tk.view);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(tickMeasure);
    setInterval(tickAgo, 20000);
    if (!REDUCED) requestAnimationFrame(tickFrame);
  }
  // ---------- end ticker
  // Not in the future: a timed Feed item (stream row or map pin) never sorts or shows later than the moment it was read.
  // A source can give a time that has not come yet (GDACS floods end a forecast day ahead; a wall-clock time read in
  // the wrong zone runs hours ahead), and the row then sat "in 22h" above every newer item. Such a time is kept in
  // `ahead` for the row's tooltip, and the row sits at now. Date-only rows have their own rule (dayAt). TFRs keep
  // theirs: they sort by when the FAA issued them, and their future start and end stay in the row's "from X to Y".
  function notAhead(i, now) {
    now = now || Date.now();
    if (!i.day && Number.isFinite(i.ts) && i.ts > now) { i.ahead = i.ts; i.ts = now; }
    return i;
  }
  function pinNotAhead(p, now) {
    if (p && p.ts_source !== "date" && Number.isFinite(p.ts_ms) && p.ts_ms > now) { p.ts_ahead = p.ts_ms; p.ts_ms = now; }
  }
  const aheadNote = (t) => (t ? ` · the source gave ${fmtD(t)} ${fmtT(t)}, after the time it was read` : "");
  function streamItems() {
    const out = [];
    STREAMS.forEach((st) => {
      let d = null; try { d = st.data(); } catch (err) { d = null; }
      if (!d || typeof d !== "object") return;
      if (st._d !== d) {
        let its = [];
        try { its = (st.items(d) || []).filter((i) => i && Number.isFinite(i.ts) && i.ts > 0 && i.title); } catch (err) { console.error("GTX stream " + st.key, err); }
        its.forEach((i) => { i.group = i.group || st.group; i.label = i.label || st.label; i.src = st.key; i.pk = postOnly(i.url); i.cn = ccList(i.cc); notAhead(i); });
        st._d = d; st._its = its;
      }
      for (const i of st._its) out.push(i);
    });
    return out;
  }
  // Only X and Telegram posts are matched against the map's pins: GDACS, UKMTO, EMSC and FAA links share one page
  // URL apart from the query string, so matching those would hide a whole source behind one pin.
  const postOnly = (u) => { const k = u ? postKey(u) : null; return k && /^(x|tg):/.test(k) ? k : null; };
  const inTheatre = (th) => S.theatre === "global" || (Array.isArray(th) ? th.includes(S.theatre) : th === S.theatre);
  function streamFiltered() {
    const q = S.q.trim().toLowerCase(), now = Date.now();
    const pinned = new Set(((S.events || {}).features || []).map((f) => postOnly(f.properties.url)).filter(Boolean));
    return streamItems().filter((i) => {
      const start = i.day ? dayAt(i.ts) : i.ts, end = i.day ? dayStart(i.ts + DAY) : i.ts;  // 1.3.0: the day in the page's zone (1.5.1: from now at the latest)
      if (!inTheatre(i.th)) return false;
      if (i.cat && CATS[i.cat] && !S.cats.has(i.cat)) return false;
      if (S.hours && now - end > S.hours * 3600000) return false;
      // a day ends where the next begins, so a brush starting at midnight leaves the day before out
      if (S.brush && ((i.day ? end <= S.brush[0] : end < S.brush[0]) || start > S.brush[1])) return false;
      if (q && ![i.title, i.where, i.label, i.text, i.badge, ...(i.cn || []).map((k) => k.name)].join(" ").toLowerCase().includes(q)) return false;
      return !(i.pk && pinned.has(i.pk));
    });
  }
  // 1.5.0: "View on map" on every Feed row with a place (all map pins, stream items with a position). The row's own
  // click does the same; the button makes it visible and reachable from the keyboard.
  const VM_BTN = '<button type="button" class="vm" title="Fly the map here and open the item">◎ View on map</button>';
  function pinRow(f) {
    const p = f.properties, [catName, c] = CATS[p.category] || CATS.other;
    const sea = p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : "";
    // 1.4.0: the country moves up into the title bar; a sea stays in the meta line unless the bar already names it
    const ks = ccList([p.country, p.country_name]), named = ks.length || p.country_name;
    const day = p.ts_source === "date", when = `<span class="time"${p.ts_ms ? ` data-ts="${day ? dayAt(p.ts_ms) : p.ts_ms}"${day ? ' data-day="1" title="Date only: the day as the source gives it, in its own calendar"' : ` title="${esc(altTime(p.ts_ms) + aheadNote(p.ts_ahead))}"`}` : ""}>${!p.ts_ms ? "–" : day ? fmtDay(p.ts_ms) : fmtD(p.ts_ms) + " " + fmtT(p.ts_ms)}</span>`
      + (p.ts_ms ? `<span class="ag">${day ? "date only" : ago(p.ts_ms)}</span>` : "");
    const bar = titleBar(ks, p.country_name ? ["", p.country_name] : sea ? ["🌊", sea] : ["🌐", thName(p.theatre) || "Global"], catName, when);
    const where = named ? sea : "";
    return `<li data-id="${esc(p.id)}" style="--c:${c}">${bar}<div class="t">${esc(p.title)}</div><div class="m">
      ${where ? `<span>${esc(where)}</span>` : ""}<span>${esc(p.handle || "")}</span>${p.source ? `<span class="badge src">${esc(p.source_label || p.source)}</span>` : ""}
      ${p.ts_source === "batch-estimate" ? '<span class="badge est">time est.</span>' : ""}
      ${p.thermal ? '<span class="badge th">thermal ✓</span>' : ""}${p.ukmto ? '<span class="badge uk">UKMTO nearby</span>' : ""}${sigBadge(S.ai.ev[p.id])}${VM_BTN}</div></li>`;
  }
  // 1.5.0: "if a feed item is in another language please translate to english". The server serves Telegram and wire
  // items in English when it holds a translation (Claude, from a job on the Mac); the original is in the tag's tooltip.
  let LANG_NAMES = null;
  const langName = (c) => { try { LANG_NAMES = LANG_NAMES || new Intl.DisplayNames(["en"], { type: "language" }); return LANG_NAMES.of(c) || c; } catch (err) { return c; } };
  const trTag = (i) => (i.tr ? `<span class="badge tr" title="${esc(`Machine translation from ${langName(i.tr.from)}. Original: ${i.tr.orig}`)}">EN · from ${esc(langName(i.tr.from))}</span>` : "");
  function streamRow(i, n) {
    const cat = i.cat && i.cat !== "other" && CATS[i.cat], g = FG[i.group] || FG.map, c = cat ? cat[1] : g[1], u = linkUrl(i.url);
    const ks = i.cn || [], nm = new Set(ks.map((k) => k.name));  // 1.4.0: a where that only lists the bar's countries is dropped
    const where = i.where && !String(i.where).split(/\s*,\s*/).every((w) => nm.has(w)) ? i.where : "";
    const when = `<span class="time" data-ts="${i.day ? dayAt(i.ts) : i.ts}"${i.day ? ' data-day="1" title="Date only: the day as the source gives it, in its own calendar"' : ` title="${esc(altTime(i.ts) + aheadNote(i.ahead))}"`}>${i.day ? fmtDay(i.ts) : fmtD(i.ts) + " " + fmtT(i.ts)}</span><span class="ag">${i.day ? "date only" : ago(i.ts)}</span>`;
    return `<li class="sx${i.ll ? "" : " nl"}" data-sx="${n}" style="--c:${c}">${titleBar(ks, ["🌐", thName(i.th) || "Global"], cat ? cat[0] : g[0], when)}<div class="t">${u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(i.title)}</a>` : esc(i.title)}</div><div class="m">
      ${where ? `<span>${esc(where)}</span>` : ""}
      <span class="badge src" style="border-color:${(FG[i.group] || FG.map)[1]}">${esc(i.label)}</span>${i.badge ? `<span class="badge">${esc(i.badge)}</span>` : ""}${trTag(i)}${i.ll ? VM_BTN : ""}</div></li>`;
  }
  function renderFeedChips(counts) {
    const groups = ["map", ...STREAMS.map((st) => st.group)].filter((g, n, a) => a.indexOf(g) === n);
    $("feedsrc").innerHTML = groups.map((g) => {
      const [name, c] = FG[g] || [g, "#9ca3af"], off = feedOff.has(g);
      return `<button class="chip${off ? " off" : ""}" data-fg="${esc(g)}" aria-pressed="${!off}" title="${off ? "Show" : "Hide"} ${esc(name)} in the Feed"><i style="background:${c}"></i>${esc(name)} <span class="muted">${nf(counts[g] || 0)}</span></button>`;
    }).join("");
  }
  function renderFeed(list) {
    if (list) feedPins = list;
    const fr = renderSrcNotice();
    const all = feedPins.map((f) => ({ pin: f, ts: f.properties.ts_source === "date" && f.properties.ts_ms ? dayAt(f.properties.ts_ms) : f.properties.ts_ms || 0, group: "map" }))
      .concat(streamFiltered().map((i) => ({ it: i, ts: i.day ? dayAt(i.ts) : i.ts, group: i.group })));
    const counts = {};
    all.forEach((r) => { counts[r.group] = (counts[r.group] || 0) + 1; });
    const rows = all.filter((r) => !feedOff.has(r.group)).sort((a, b) => b.ts - a.ts);
    renderFeedChips(counts);
    feedRows = rows.slice(0, feedLimit);
    const pins = rows.filter((r) => r.pin).length, srcs = new Set(rows.filter((r) => r.it).map((r) => r.it.src)).size;
    $("feedcount").textContent = `${nf(rows.length)} items: ${nf(pins)} map pins + ${nf(rows.length - pins)} from ${srcs} other source${srcs === 1 ? "" : "s"}`
      + `${S.theatre !== "global" ? " in " + THEATRES[S.theatre][0] : ""}${S.brush ? " · time-brushed" : ""}${fr.checked ? " · map checked " + ago(fr.checked) : ""}`;
    $("feed").innerHTML = feedRows.map((r, n) => (r.pin ? pinRow(r.pin) : streamRow(r.it, n))).join("")
      + (rows.length > feedLimit ? `<li class="more"><button class="chip" id="feedmore">Show ${nf(Math.min(FEED_STEP, rows.length - feedLimit))} more · ${nf(rows.length - feedLimit)} not shown</button></li>` : "");
    renderTicker(all);  // 1.5.0: the ticker applies its own SRC sources instead of the chips
  }
  $("feedsrc").addEventListener("click", (e) => {
    const b = e.target.closest("[data-fg]"); if (!b) return;
    const g = b.dataset.fg;
    if (feedOff.has(g)) feedOff.delete(g); else feedOff.add(g);
    try { localStorage.setItem("gt-feed-off", JSON.stringify([...feedOff])); } catch (err) { /* private mode: this visit only */ }
    feedLimit = FEED_STEP; renderFeed();
  });
  $("feed").addEventListener("click", (e) => {
    if (e.target.closest("#feedmore")) { feedLimit += FEED_STEP; renderFeed(); return; }
    const li = e.target.closest("li"); if (!li) return;
    if (li.dataset.sx != null) {
      if (e.target.closest("a")) return;  // the title opens the source
      openRow(feedRows[+li.dataset.sx], true);  // a row with no place does nothing (its title is the link)
      return;
    }
    const f = (S.events || { features: [] }).features.find((x) => x.properties.id === li.dataset.id); if (!f) return;
    openRow({ pin: f });
  });

  // Core streams. The extension feeds (wire, Telegram, hazards, signals, airspace, cyber) register theirs in web/ext/.
  stream({ key: "official", group: "official", label: "Official", data: () => S.feeds.official, items: (d) => (d.items || []).map((i) => {
    const dayOnly = String(i.date || "").length <= 10;
    return { id: "off:" + i.url, ts: dayOnly ? dayMs(i.date) : isoMs(i.date), day: dayOnly, title: i.title, url: i.url, label: i.source,
      th: i.source === "CENTCOM" ? "middle-east" : /ukrain|russia|crimea/i.test(i.title || "") ? "ukraine-russia" : null };
  }) });
  stream({ key: "ukmto", group: "maritime", label: "UKMTO", data: () => S.feeds.ukmto, items: (d) => (d.items || []).map((i) => ({
    id: "ukmto:" + i.num, ts: dayMs(i.date), day: true, title: `UKMTO ${i.num != null ? i.num + " " : ""}${i.type || "report"}${i.where ? ": " + i.where : ""}`,
    url: i.url, text: i.text, th: "middle-east", ll: Array.isArray(i.coord) ? i.coord : null, zoom: 6 })) });
  stream({ key: "embassy", group: "alerts", label: "US embassy", data: () => (S.alerts || {}).embassy, items: (d) => (d.items || []).map((i) => {
    const p = emPost(i.c), cs = i.posts && i.posts.length ? i.posts : [i.c];
    return { id: "em:" + i.id, ts: i.t * 1000, cc: cs, title: i.title, url: httpsUrl(i.url), where: emWhere(i) || ((country(i.c) || {}).name || i.c), badge: emK(i.kind),
      th: cs.map((c) => (country(c) || {}).th).filter(Boolean), ll: p && p.lat != null ? [p.lon, p.lat] : null, zoom: 5, pop: p ? () => emPopup(i.c) : null };
  }) });
  stream({ key: "airalerts", group: "alerts", label: "Air raid (UA)", data: () => (S.alerts || {}).regions, items: (d) => [
    ...(d.messages || []).map((m) => ({ id: "ar:" + (m.url || m.at + m.text), ts: isoMs(m.at), cc: "UKR", title: m.text, url: m.url, where: m.who, th: "ukraine-russia" })),
    ...(d.ended || []).map((m) => ({ id: "are:" + m.from + m.text, ts: isoMs(m.to), cc: "UKR", title: `Ended: ${m.text}${m.dur ? " (" + m.dur + ")" : ""}`, th: "ukraine-russia" })),
  ] });
  stream({ key: "tzeva", group: "alerts", label: "Israel sirens", data: () => (S.alerts || {}).israel, items: (d) => [
    ...(d.events || []).map((e) => ({ id: "il:" + e.t + e.label, ts: e.t * 1000, cc: "ISR", title: `${e.label}: ${nf(e.n)} area${e.n > 1 ? "s" : ""}`,
      where: (e.names || []).slice(0, 6).join(", ") + ((e.names || []).length > 6 ? " …" : ""), text: (e.names || []).join(" "),
      th: "middle-east", ll: Array.isArray(e.c) ? e.c : null, zoom: 8 })),
    ...(d.messages || []).map((m) => ({ id: "ilm:" + m.time + m.kind, ts: m.time * 1000, cc: "ISR", title: m.title || m.kind, text: m.body, label: "Home Front Command", th: "middle-east" })),
  ] });
  stream({ key: "advisories", group: "official", label: "State Dept", data: () => S.feeds.advisories, items: (d) => (d.changes || []).map((c) => {
    const k = country(c.country);
    return { id: "adv:" + c.country + c.seen, ts: isoMs(c.seen), cc: c.country, title: `Travel advisory ${c.to > c.from ? "raised" : "lowered"}: ${c.country}, level ${c.from} → ${c.to}`,
      th: k && k.th, ll: k && k.ll, zoom: 4 };
  }) });
  stream({ key: "outages", group: "internet", label: "IODA", data: () => S.feeds.outages, items: (d) => {
    const names = {};
    (d.countries || []).forEach((c) => { names[c.code] = c.name; });
    const ev = (e, code, region) => {
      const k = country(code), name = names[code] || (k && k.name) || code;
      return { id: `io:${code}:${region || ""}:${e.start}:${e.source}`, ts: isoMs(e.start), cc: code, title: `Internet outage${e.ongoing ? " (ongoing)" : ""}: ${region ? region + ", " : ""}${name}`,
        where: e.hours != null ? e.hours + " h" : "", badge: e.source, th: k && k.th, ll: k && k.ll, zoom: 4 };
    };
    return (d.countries || []).flatMap((c) => (c.events || []).map((e) => ev(e, c.code))).concat((d.regions || []).map((r) => ev(r, r.country, r.region)));
  } });
  stream({ key: "pla", group: "official", label: "Taiwan MND", data: () => S.feeds.pla, items: (d) => (d.date ? [{ id: "pla:" + d.date, ts: dayMs(d.date), day: true, cc: "TWN",
    title: `PLA around Taiwan: ${nf(d.aircraft)} aircraft (${nf(d.entered_adiz)} in the ADIZ), ${nf(d.plan_ships)} PLAN ships, ${nf(d.official_ships)} official ships`,
    url: d.url, th: "indo-pacific", ll: [121, 23.7], zoom: 5 }] : []) });
  stream({ key: "losses", group: "official", label: "UA General Staff", data: () => S.feeds.losses, items: (d) => {
    const i = d.increase || {};
    return d.date ? [{ id: "loss:" + d.date, ts: dayMs(d.date), day: true, cc: "UKR", th: "ukraine-russia",
      title: `Russian losses per Ukraine's General Staff, day ${nf(d.day)}: +${nf(i.personnel_units)} personnel, +${nf(i.tanks)} tanks, +${nf(i.artillery_systems)} artillery, +${nf(i.uav_systems)} drones` }] : [];
  } });
  stream({ key: "czib", group: "airspace", label: "EASA CZIB", data: () => S.feeds.czib, items: (d) => (d.zones || []).map((z) => {
    const ks = String(z.country || "").split(/\s*,\s*/).map(country).filter(Boolean);  // "Bahrain, Kuwait, Qatar, Oman, ..."
    return { id: "czib:" + z.name, ts: dayMs(z.issued), day: true, cc: ks.map((k) => k.a3), title: `Conflict zone bulletin: ${z.name}`, where: z.valid_until ? "valid until " + z.valid_until : "",
      url: "https://www.easa.europa.eu/en/domains/air-operations/czibs", th: [...new Set(ks.map((k) => k.th).filter(Boolean))], ll: (ks.find((k) => k.ll) || {}).ll || null, zoom: 4 };
  }) });

  function buildRail() {
    $("theatres").innerHTML = Object.entries(THEATRES).map(([k, [n, c]]) =>
      `<button data-th="${k}" class="${k === S.theatre ? "on" : ""}" title="${k === "global" ? "Every theatre" : `Only ${esc(n)}: the map, the Feed and the counts`}"><span class="sw" style="background:${c}"></span><span class="nm">${n}</span><span class="ct" id="ct-${k}">–</span></button>`).join("");
    $("theatres").onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      S.theatre = b.dataset.th; S.brush = null;
      [...$("theatres").children].forEach((x) => x.classList.toggle("on", x === b));
      const [lon, lat, z] = THEATRES[S.theatre][2]; map.flyTo({ center: [lon, lat], zoom: z, speed: 1.4 });
      setRail(false); render();
    };
    $("layers").innerHTML = LAYERS.map(([k, label, feed, on]) =>
      `<label><input type="checkbox" data-layer="${k}" ${on ? "checked" : ""}><span class="dot" id="dot-${k}"></span>${label}<span class="n" id="n-${k}"></span></label>` +
      (EXT.legends[k] ? `<div class="aclegend">${EXT.legends[k]}</div>` : "") +
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
    $("cats").innerHTML = Object.entries(CATS).map(([k, [n, c]]) => `<button class="chip" data-cat="${k}" title="Show or hide ${esc(n.toLowerCase())} events on the map and in the Feed"><i style="background:${c}"></i>${n}</button>`).join("");
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
      events: S.summary.events_total != null && S.events && S.eventsBase ? S.summary.events_total + S.events.features.length - S.eventsBase.features.length : S.summary.events_total, overlays: S.events ? S.events.features.filter((f) => f.properties.kind === "overlay").length : null,
      front: (S.feeds.front || {}).count, thermal: (S.feeds.firms || {}).count, ukmto: (S.feeds.ukmto || {}).located,
      mil: (S.feeds.mil || {}).count, gdelt: (S.feeds.gdelt || {}).count, czib: S.summary.airspace_czib_active, cables: null,
      ships: (S.feeds.ships || {}).count, choke: (S.feeds.portwatch || {}).count, outages: (S.feeds.outages || {}).count, gfw: (S.feeds.gfw || {}).count,
      advisories: S.summary.travel_advisories ? (S.summary.travel_advisories.level4 || 0) + (S.summary.travel_advisories.level3 || 0) : null,
      alerts: S.alerts ? regList().filter((r) => r.kind === "alert").length : null, israel: S.alerts ? ((S.alerts.israel || {}).cities || []).length : null,
      embassy: S.alerts && S.alerts.embassy ? (S.alerts.embassy.items || []).length : null };
    const sg = {};
    ((S.feeds.ships || {}).points || []).forEach((p) => { const g = shipGrp(p[4]); sg[g] = (sg[g] || 0) + 1; });
    SHIP_GRPS.forEach(([g]) => { const el = $("sn-" + g); if (el) el.textContent = sg[g] ? " " + nf(sg[g]) : ""; });
    Object.entries(EXT.counts).forEach(([k, fn]) => { try { n[k] = fn(); } catch (err) { n[k] = null; } });
    LAYERS.forEach(([k, , feed]) => {
      const d = $("dot-" + k), e = $("n-" + k);
      if (d) d.className = "dot " + (st[feed] ? (st[feed].ok ? "ok" : "bad") : "");
      const lab = d && d.closest("label"), f = st[feed];  // 1.4.3: the row's tooltip names its source and how fresh it is
      if (lab) lab.title = !f ? `Source: ${feed}` : f.ok === false ? `Source ${feed}: failing${f.error ? " (" + String(f.error).slice(0, 140) + ")" : ""}`
        : `Source ${feed}: OK${f.at ? ", updated " + ago(isoMs(f.at)) : ""}${f.stale ? " (overdue)" : ""}`;
      if (e) e.textContent = n[k] != null ? nf(n[k]) : "";
    });
  }
  function hormuzKpi() {
    const h = ((S.feeds.portwatch || {}).chokepoints || []).find((c) => c.id === "chokepoint6");
    if (!h || !h.avg7) return [];
    const ch = (h.change_vs_year_pct || {}).tanker;
    return [[`${nf(h.avg7.tanker)}${ch != null ? ` (${pct(ch)})` : ""}`, "Hormuz tankers/day", ch != null && ch <= -50]];
  }
  // 1.4.3: what each header tile counts, shown as its tooltip on a PC
  const KPI_TIP = {
    "Analyst tension": "The analyst's overall tension score (0 to 10) and its trend, from the latest analyst run. Details in the Analyst tab.",
    "Events, last 6h": "Curated map events in the 6 hours back from the newest pin.",
    "Events, 24h": "Curated map events in the 24 hours back from the newest pin.",
    "UA / RU regions on alert": "Regions under an air-raid alert right now: Ukraine / Russia (alerts.in.ua). Amber when any Ukrainian alert is red (missile).",
    "Israel alerts, 24h": "Tzeva Adom (Home Front Command) alert events in the last 24 hours.",
    "Israel sirens NOW": "Areas in Israel with a siren sounding right now (Tzeva Adom).",
    "Thermal-corroborated": "Curated events with a NASA FIRMS thermal anomaly nearby, a sign of fire or a strike on the ground.",
    "Mil aircraft (ADS-B)": "Military aircraft broadcasting ADS-B right now (adsb.lol, adsb.fi). Many military flights do not broadcast.",
    "UKMTO incidents, 7d": "UK Maritime Trade Operations security incidents reported in the last 7 days.",
    "Hormuz tankers/day": "Tanker transits per day through the Strait of Hormuz, 7-day average, with the change against a year ago (IMF PortWatch, about 3 days behind).",
    "RU losses (UA GS)": "Russian personnel losses reported today by Ukraine's General Staff: one side's claim, not verified.",
    "PLA aircraft / ships": "PLA aircraft and PLAN ships around Taiwan in the latest daily report of Taiwan's Ministry of National Defense.",
    "Emergency squawks now": "Aircraft squawking 7500 (hijack), 7600 (radio failure) or 7700 (emergency) right now.",
    "Routing drops (RIPE)": "Countries whose visible internet routes dropped sharply (RIPEstat).",
    "Hazard alerts (Orange/Red)": "GDACS natural-hazard alerts at Orange or Red right now.",
    "Quakes in watch areas": "Earthquakes M4+ inside the watch areas (near test sites and conflict zones) in the last days.",
    "Tsunami bulletin": "The highest tsunami bulletin level in force (PTWC, NTWC, JMA).",
    "Radiation flags": "BfS gamma-dose stations reading well above their normal level.",
    "NTAS advisory": "A US DHS National Terrorism Advisory System bulletin is in force.",
  };
  function renderKpis() {
    const s = S.summary, pla = s.taiwan_pla || {};
    const pic = (S.ai.ov || {}).picture;
    const k = [
      ...(pic ? [[`${pic.overall_tension}/10 ${TREND[pic.trend] || ""}`, "Analyst tension", pic.overall_tension >= 7]] : []),
      [nf(s.events_6h), "Events, last 6h", s.events_6h > 10],
      [nf(s.events_24h), "Events, 24h"],
      ...alertKpis(), // live alerts early in the strip, so they stay in view on narrower screens
      [nf(s.thermal_corroborated), "Thermal-corroborated"],
      [nf((S.feeds.mil || {}).count ?? s.mil_aircraft), "Mil aircraft (ADS-B)"],
      [nf(s.ukmto_incidents_7d), "UKMTO incidents, 7d", s.ukmto_incidents_7d > 3],
      ...hormuzKpi(),
      ...EXT.kpis.flatMap((fn) => { try { return fn() || []; } catch (err) { return []; } }),
      [s.ru_losses_personnel_today != null ? "+" + nf(s.ru_losses_personnel_today) : "–", "RU losses (UA GS)"],
      [pla.aircraft != null ? `${pla.aircraft} / ${pla.plan_ships}` : "–", "PLA aircraft / ships"],
    ];
    const html = k.map(([v, l, w]) => `<div class="kpi ${w === "bad" ? "bad" : w ? "warn" : ""}"${KPI_TIP[l] ? ` title="${esc(KPI_TIP[l])}"` : ""}><b>${esc(v)}</b><small>${esc(l)}</small></div>`).join("");
    if ($("kpis")._html !== html) { $("kpis").innerHTML = html; $("kpis")._html = html; }  // 1.4.3: unchanged tiles stay put, so a tooltip over one stays up
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
    bins.forEach((b, i) => { const lab = axisLabel(b.t); if (lab) { g.fillText(lab, i * bw + 2, H - 1); g.fillRect(i * bw, 0, 1, H - 12); } });
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
    [...$("tabs").children].forEach((x) => { const el = $("tab-" + x.dataset.tab); if (el) el.classList.toggle("hidden", x.dataset.tab !== t); });
    const ext = EXT.tabs.find((x) => x.id === t);
    if (ext) { try { ext.render($("tab-" + t)); } catch (err) { console.error("GTX tab " + t, err); } return; }
    ({ alerts: renderAlerts, brief: renderBrief, sea: renderSea, ai: renderAnalyst, sources: renderSources })[t]?.();
  }
  $("tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) openTab(b.dataset.tab); };
  $("q").addEventListener("input", (e) => { S.q = e.target.value; render(); });
  // 1.5.0: on phones and tablets (≤900 px) the rail is a drawer. ☰ toggles it; its ✕, a tap on the dimmed page or
  // the map, Escape and picking a theatre close it. On a PC the rail is a column and the class changes nothing.
  // Hoisted, so buildRail's theatre handler can use it too.
  function setRail(open) {
    $("rail").classList.toggle("open", open);
    $("btnRail").setAttribute("aria-expanded", open ? "true" : "false");
  }
  $("btnRail").onclick = () => setRail(!$("rail").classList.contains("open"));
  [$("railClose"), $("railScrim")].forEach((el) => el && (el.onclick = () => setRail(false)));  // guarded: a cached 1.4 page has neither
  map.on("click", () => setRail(false));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !$("rail").classList.contains("open")) return;
    const inside = $("rail").contains(document.activeElement);
    setRail(false);
    if (inside) $("btnRail").focus();  // a keyboard user lands back on ☰, not on a control now off screen
  });
  // ---------- 1.5.0: resizable, collapsible sidebars (PC) ----------
  // Asked for: "make both sidebars expandable with the mouse add collapse button too ... on pc dashboards". From 901 px
  // up, a grip on each sidebar's inner edge drags its width (double-click returns it to the layout's own width, arrow
  // keys nudge it, dragged nearly shut it collapses), and a tab at mid-height collapses it to nothing and back. Only a
  // dragged width or a collapse is stored (per browser); otherwise the stylesheet's widths apply (236 / 372 px, or
  // 210 / 320 px up to 1180 px). The map always keeps at least 360 px. Narrow screens keep the drawer layout.
  const SB = { rail: { min: 180, max: 480 }, panel: { min: 300, max: 760 } }, SB_MAP = 360;
  const sb = (() => { try { const o = JSON.parse(localStorage.getItem("gt-sidebars")); return o && typeof o === "object" ? o : {}; } catch (err) { return {}; } })();
  const appEl = document.querySelector(".app"), sbWide = () => window.innerWidth >= 901;
  const sbOther = (k) => (k === "rail" ? "panel" : "rail");
  const sbNow = (k) => ($(k) ? Math.round($(k).getBoundingClientRect().width) : 0);  // as drawn
  function sbClamp(k, w) {
    const o = sbOther(k), ow = sb[o + "Min"] ? 0 : sbNow(o);
    return Math.round(Math.max(SB[k].min, Math.min(SB[k].max, w, window.innerWidth - ow - SB_MAP)));
  }
  let sbRaf = 0;
  const sbMapResize = () => { if (!sbRaf) sbRaf = requestAnimationFrame(() => { sbRaf = 0; try { map.resize(); } catch (err) { /* map not ready */ } }); };
  function sbApply(resize) {
    ["rail", "panel"].forEach((k) => {
      const shut = !!sb[k + "Min"], custom = Number.isFinite(sb[k]);
      if (shut) appEl.style.setProperty("--" + k + "-w", "0px");
      else if (custom) appEl.style.setProperty("--" + k + "-w", sbClamp(k, sb[k]) + "px");
      else appEl.style.removeProperty("--" + k + "-w");
      appEl.classList.toggle(k + "-min", shut);
    });
    ["rail", "panel"].forEach((k) => {
      const shut = !!sb[k + "Min"], side = k === "rail" ? "left" : "right";
      const g = document.querySelector(`.sb-grip[data-sb="${k}"]`), t = document.querySelector(`.sb-tab[data-sbmin="${k}"]`);
      if (g) { g.setAttribute("aria-valuenow", shut ? 0 : sbNow(k)); g.setAttribute("aria-valuemax", SB[k].max); }
      if (t) {
        t.textContent = (k === "rail") === shut ? "›" : "‹";
        t.setAttribute("aria-expanded", String(!shut));
        t.title = `${shut ? "Open" : "Collapse"} the ${side} sidebar`;
        t.setAttribute("aria-label", t.title);
      }
    });
    if (resize) sbMapResize();
  }
  // At the end of a change: save it, and send one resize so the timeline, ticker and tabs re-measure.
  const sbDone = () => { try { localStorage.setItem("gt-sidebars", JSON.stringify(sb)); } catch (err) { /* private mode: this visit only */ } window.dispatchEvent(new Event("resize")); };
  const sbToggle = (k) => { sb[k + "Min"] = !sb[k + "Min"]; sbApply(true); sbDone(); };
  document.querySelectorAll(".sb-tab").forEach((t) => t.addEventListener("click", () => sbToggle(t.dataset.sbmin)));
  document.querySelectorAll(".sb-grip").forEach((g) => {
    const k = g.dataset.sb;
    g.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || !sbWide()) return;
      e.preventDefault();
      try { g.setPointerCapture(e.pointerId); } catch (err) { /* synthetic event */ }
      g.classList.add("on"); appEl.classList.add("sizing");
      const move = (ev) => {
        const r = appEl.getBoundingClientRect(), w = k === "rail" ? ev.clientX - r.left : r.right - ev.clientX;
        if (w < SB[k].min * 0.6) { if (!sb[k + "Min"]) { sb[k + "Min"] = true; sbApply(true); } return; }  // nearly shut: collapse
        sb[k + "Min"] = false; sb[k] = sbClamp(k, w); sbApply(true);
      };
      const up = () => {
        g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up); g.removeEventListener("pointercancel", up);
        g.classList.remove("on"); appEl.classList.remove("sizing"); sbDone();
      };
      g.addEventListener("pointermove", move); g.addEventListener("pointerup", up); g.addEventListener("pointercancel", up);
    });
    g.addEventListener("dblclick", () => { delete sb[k]; sb[k + "Min"] = false; sbApply(true); sbDone(); });
    g.addEventListener("keydown", (e) => {
      const dir = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
      if (dir) {
        e.preventDefault();
        const grow = dir * (k === "rail" ? 1 : -1), step = e.shiftKey ? 64 : 16;
        if (sb[k + "Min"]) { if (grow > 0) { sb[k + "Min"] = false; sb[k] = sbClamp(k, SB[k].min); } }
        else {
          const w = sbNow(k) + grow * step;
          if (w < SB[k].min) sb[k + "Min"] = true; else sb[k] = sbClamp(k, w);
        }
        sbApply(true); sbDone();
      } else if (e.key === "Enter") { e.preventDefault(); sbToggle(k); }
    });
  });
  window.addEventListener("resize", () => sbApply(false));
  sbApply(true);
  // ---------- end sidebars
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
      <div>${esc(zText(a.summary, isoMs(a.analyzed_at)))}</div><div class="muted small">${esc(zText(a.rationale || "", isoMs(a.analyzed_at)))}${tags.length ? " · market themes: " + tags.map(esc).join(", ") : ""}</div></div>`;
  }
  function renderAnalyst() {
    const ov = S.ai.ov || {}, p = ov.picture, total = ((S.events || {}).features || []).filter((f) => f.properties.kind === "event").length;
    const done = Object.keys(S.ai.ev || {}).length;
    const lvl = (n) => (n >= 8 ? "var(--bad)" : n >= 5 ? "var(--accent)" : "var(--ok)");
    const list = (a, cls) => (a && a.length ? `<ul class="${cls || ""}">${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
    const runs = (ov.runs || []).slice(0, 6).map((r) => `<li>${esc(when(r.stored_at))} · ${esc(r.kind)} · ${esc(r.n)} · ${esc(r.secs)}s · ${esc(r.model || "")}</li>`).join("");
    const foot = `<div class="card"><h4>Analyst runs</h4><div class="row"><span><b>${nf(done)}</b> of ${nf(total)} events analysed</span><span>writes ${ov.writes_enabled ? "enabled" : "disabled"}</span></div>${runs ? `<ul class="muted small">${runs}</ul>` : '<div class="muted small">No runs yet.</div>'}
      <div class="muted small" style="margin-top:6px">Claude reads every new event and, every few hours, the whole picture. Its notes are machine analysis of unverified reports: a lead, not a fact.</div></div>`;
    if (!p) { $("tab-ai").innerHTML = `<div class="card"><h4>Situation assessment</h4><div class="muted">No assessment yet.</div></div>` + foot; return; }
    const th = (p.theatres || []).slice().sort((a, b) => (b.status || 0) - (a.status || 0));
    $("tab-ai").innerHTML = `<div class="card ai-head"><h4>${esc(p.headline)}</h4>
        <div class="meter" title="Global tension ${esc(p.overall_tension)}/10"><i style="width:${(p.overall_tension || 0) * 10}%;background:${lvl(p.overall_tension)}"></i></div>
        <div class="row"><span>Tension <b>${esc(p.overall_tension)}/10</b> ${esc(TREND[p.trend] || "")} ${esc(p.trend)}</span><span>Confidence <b>${esc(p.confidence)}</b></span><span>${esc(when(p.generated_at))}</span></div>
        <div>${esc(p.bluf)}</div>${p.changes_since_last && p.changes_since_last.length ? `<div class="sub">Since last assessment</div>${list(p.changes_since_last)}` : ""}</div>` +
      th.map((t) => `<div class="card"><h4><span class="sw" style="background:${(THEATRES[t.theatre] || ["", "#888"])[1]}"></span>${esc((THEATRES[t.theatre] || [t.theatre])[0])}<span class="lvl" style="color:${lvl(t.status)}">${esc(t.status)}/10 ${esc(TREND[t.trend] || "")}</span></h4>
        <div>${esc(t.summary)}</div>${list(t.key_developments)}${t.watch && t.watch.length ? `<div class="sub">Watch</div>${list(t.watch, "muted")}` : ""}</div>`).join("") +
      ((p.indicators || []).length ? `<div class="card"><h4>Escalation indicators</h4><table class="src">${p.indicators.map((i) => `<tr><td>${esc(i.indicator)}<div class="muted small">${esc(i.note)}</div></td><td class="st st-${esc((i.state || "").replace(" ", "-"))}">${esc(i.state)}</td></tr>`).join("")}</table></div>` : "") +
      ((p.market_risk || []).length ? `<div class="card"><h4>Market risk themes</h4><ul>${p.market_risk.map((m) => `<li><b>${esc((m.theme || "").replace("_", " "))}</b> <span class="badge">${esc(m.direction)}</span> ${esc(m.why)}</li>`).join("")}</ul><div class="muted small">Geopolitical context for later trading research, not trade advice.</div></div>` : "") +
      ((p.cross_theatre || []).length ? `<div class="card"><h4>Cross-theatre links</h4>${list(p.cross_theatre)}</div>` : "") +
      ((p.gaps || []).length ? `<div class="card"><h4>Gaps</h4>${list(p.gaps, "muted")}</div>` : "") + foot;
    // 1.3.0: Eastern beside the analyst's UTC times (text nodes only, so no markup changes)
    const tw = document.createTreeWalker($("tab-ai"), NodeFilter.SHOW_TEXT), ref = isoMs(p.generated_at);
    for (let nd = tw.nextNode(); nd; nd = tw.nextNode()) { const v = zText(nd.nodeValue, ref); if (v !== nd.nodeValue) nd.nodeValue = v; }
  }

  function renderBrief() {
    api("brief").then((b) => {
      const s = S.summary;
      const head = `<div class="card"><h4>Situation picture</h4><div class="row"><span>Generated <b>${esc(when(b.generated))}</b></span><span>${esc(b.method)}</span></div>
        <ul><li><b>${nf(s.events_24h)}</b> curated events in the last 24h across ${Object.keys(s.events_24h_by_theatre || {}).length} theatres; <b>${nf(s.thermal_corroborated)}</b> strike/energy reports have a NASA thermal detection nearby.</li>
        <li>Maritime: <b>${nf(s.ukmto_incidents_7d)}</b> UKMTO incidents in 7 days${s.ukmto_latest ? `, latest #${s.ukmto_latest.num} ${esc(s.ukmto_latest.type)} on ${esc(s.ukmto_latest.date)} (${esc(s.ukmto_latest.where || "")})` : ""}.</li>
        <li>Ukraine: Russian losses per Ukraine's General Staff +${nf(s.ru_losses_personnel_today)} personnel (day ${nf(s.ru_losses_day)}). DeepState front snapshot ${esc((S.feeds.front || {}).updated || "–")}.</li>
        <li>Taiwan: ${(s.taiwan_pla || {}).aircraft ?? "–"} PLA aircraft, ${(s.taiwan_pla || {}).plan_ships ?? "–"} PLAN ships (MND ${esc((s.taiwan_pla || {}).date || "")}).</li>
        <li>${nf(s.airspace_czib_active)} active EASA conflict-zone airspace bulletins.</li>${briefExtra(s)}</ul></div>`;
      $("tab-brief").innerHTML = head + briefCoverage(s) + b.theatres.map((t) => `<div class="card"><h4><span class="sw" style="background:${(THEATRES[t.theatre] || ["", "#888"])[1]}"></span>${esc(t.label)}</h4>
        <div class="row"><span><b>${t.count}</b> events</span><span><b>${t.last_24h}</b> in 24h</span><span><b>${t.thermal}</b> thermal ✓</span></div>
        <div class="row">Mostly: ${t.top_categories.map((c) => `${esc((CATS[c.category] || CATS.other)[0])} (${c.n})`).join(", ")}</div>
        <div class="row">Hotspots: ${t.hotspots.map((h) => `${esc(h.place)} (${h.n})`).join(", ")}</div>
        <ul>${t.headlines.map((h) => `<li><a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a> <span class="muted small">${esc(when(h.ts))} · ${esc(h.handle || "")}</span></li>`).join("")}</ul></div>`).join("");
    });
  }
  // 1.0.0: one row per theatre, one column per source (columns come from the page extensions, so only sources this
  // release runs appear). Built in the page from feeds the page already has; /api/brief (public) is unchanged.
  function briefCoverage(s) {
    const cols = EXT.briefCols.map((c) => { try { return [c, c.counts() || null]; } catch (err) { return [c, null]; } }).filter(([, v]) => v);
    if (!cols.length) return "";
    const ths = Object.keys(THEATRES).filter((k) => k !== "global"), by = s.events_24h_by_theatre || {};
    const cell = (n) => `<td>${n ? nf(n) : `<span class="muted">·</span>`}</td>`;
    return `<div class="card"><h4>All sources by theatre</h4><table class="src"><tr><th>Theatre</th><th title="Curated source map, 24 h">Map 24 h</th>${cols.map(([c]) => `<th title="${esc(c.title || "")}">${esc(c.label)}</th>`).join("")}</tr>
      ${ths.map((k) => `<tr><td><span class="sw" style="background:${THEATRES[k][1]}"></span>${esc(THEATRES[k][0])}</td>${cell(by[k])}${cols.map(([, v]) => cell(v[k])).join("")}</tr>`).join("")}</table>
      <div class="muted small">${cols.map(([c]) => c.note).filter(Boolean).map(esc).join(" ")}</div></div>`;
  }
  function briefExtra(s) {
    const io = s.internet_outages, ta = s.travel_advisories, sh = s.ships_last_hour_by_area, gf = s.ship_traffic_gfw, ra = s.regional_alerts;
    let h = "";
    if (ra && ra.ukraine) {
      const le = (ra.israel || {}).latest_event;
      h += `<li>Air-raid alerts${ra.as_of ? ` (alerts.in.ua, ${esc(when(ra.as_of))})` : ""}: Ukraine <b>${nf(ra.ukraine.n)}</b> regions (${nf(ra.ukraine.red || 0)} red), Russia <b>${nf((ra.russia || {}).n)}</b>, Poland ${nf((ra.poland || {}).n)}. Israel: ${le ? `latest alert ${esc(le.label)}, ${nf(le.n)} areas at ${esc(when(ra.israel.latest_event_at))}` : "no alerts in 24 h"}.</li>`;
    }
    const ue = ra && ra.us_embassies;
    if (ue && ue.alerts_24h != null) h += `<li>US embassy alerts, 24 h: <b>${nf(ue.alerts_24h)}</b>${(ue.latest || []).length ? ` (latest: ${ue.latest.slice(0, 3).map((x) => `${esc(x.post)} ${esc(x.title)}`).join("; ")})` : ""}.</li>`;
    if (io) {
      const w = io.watched_countries || [], r = io.watched_regions || [];
      h += `<li>Internet: ${w.length ? w.map((c) => `<b>${esc(c.country)}</b>${c.ongoing ? " (ongoing)" : ""}`).join(", ") : "no watched country"} with outages in ${esc(io.window_h)} h; ${nf(r.length)} regional outages in watched countries${r.length ? ` (latest ${esc(r[0].region)}, ${esc(r[0].country)})` : ""}. IODA.</li>`;
    }
    if (ta) h += `<li>US travel advisories: <b>${nf(ta.level4)}</b> countries at Level 4, ${nf(ta.level3)} at Level 3${(ta.level_changes || []).length ? `; changes: ${ta.level_changes.slice(0, 3).map((c) => `${esc(c.country)} ${esc(c.from)}→${esc(c.to)}`).join(", ")}` : `; no level changes since ${esc(ta.watching_since ? fmtD(isoMs(ta.watching_since)) : "–")}`}.</li>`;
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
    $("tab-sea").innerHTML = pwTable() + militaryCard() + listedCard() + tankerCards() + gfwCards + `<div class="muted small" style="margin-bottom:8px">UKMTO notices scraped via Firecrawl (site blocks plain clients). Positions from stated range/bearing where given, else area centroid.</div>` +
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
  // 1.5.0: military ships heard anywhere in the last 3 hours, by declared flag
  function militaryCard() {
    const d = S.feeds.ships || {}, all = d.military;
    if (!all) return "";
    const by = {};
    all.forEach((c) => (by[c.flag || "?"] = by[c.flag || "?"] || []).push(c));
    const flags = Object.keys(by).sort((a, b) => by[b].length - by[a].length || a.localeCompare(b));
    const where = (c) => [c.area ? AREA_NAME(c.area) : c.sea && !["offshore", "open ocean"].includes(c.sea) ? c.sea : "", c.near ? (c.sea ? "near " : "") + c.near : c.sea || ""].filter(Boolean).join(", ");
    const row = (c) => `<li data-ship="${c.mmsi}" style="cursor:pointer" title="Fly the map to ${esc(c.name || "this ship")}"><b>${esc(c.name || "unnamed")}</b> · ${c.sog != null ? nf(c.sog) + " kt" : "–"}${c.dest ? " · to " + esc(c.dest) : ""}<div class="muted small">${esc(where(c) || "position known")} · heard ${esc(ago(isoMs(c.ts)))}</div></li>`;
    return `<div class="card"><h4><span class="sw" style="background:${SHIP_COL.military}"></span>Military ships heard worldwide <span class="muted small" style="margin-left:auto">${nf(all.length)} · last 3 h, AIS</span></h4>` +
      (all.length ? flags.map((f) => `<details${all.length <= 30 ? " open" : ""}><summary>${f !== "?" ? flag2(f) + " " + esc(regionName(f)) : "Flag unknown"} <span class="muted">${nf(by[f].length)}</span></summary><ul class="shiplist">${by[f].map(row).join("")}</ul></details>`).join("")
        : `<div class="muted small">None heard in the last 3 hours.</div>`) +
      `<div class="muted small">AIS type 35 or a navy name (WARSHIP, NAVY, HMS, HNLMS, USNS ...). Most warships switch AIS off at sea, so this is the navies that transmit, mostly near European and North American coasts; volunteer receivers do not reach most oceans. Flags are declared, from the MMSI.</div></div>`;
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
      const label = { mymaps: "Global War News Map (My Maps KML)", mil: "Military ADS-B (adsb.lol → adsb.fi), types from hexdb.io", front: "DeepStateMap front line", losses: "russianwarship.rip (UA General Staff)", firms: "NASA FIRMS NOAA-20 + NOAA-21 VIIRS", ukmto: "UKMTO via Firecrawl", gdelt: "GDELT 2.0 event export", tzeva: "Tzeva Adom history + Home Front Command messages", tzevalive: "Tzeva Adom live sirens (Israel)", airalerts: "alerts.in.ua SITREP (Ukraine, Russia, Poland)", embassy: "US embassy alerts (38 posts' own RSS)", pla: "Taiwan MND PLA report", czib: "EASA CZIB airspace", official: "CENTCOM + War Dept + UK MoD", cables: "TeleGeography cables", outages: "IODA internet outages (Georgia Tech)", advisories: "US State Dept travel advisories", ships: "AISStream ship positions", gfw: "Global Fishing Watch ship traffic", portwatch: "IMF PortWatch chokepoint transits", vessellists: "OpenSanctions vessel lists (sanctions, shadow fleet, detentions)", ...EXT.labels };
      const dur = (s) => s == null ? "–" : s < 120 ? Math.round(s) + "s" : s < 7200 ? Math.round(s / 60) + "m" : s < 172800 ? Math.round(s / 3600) + "h" : Math.round(s / 86400) + "d";
      const nStale = Object.values(st.feeds).filter((v) => v.stale).length;
      // 1.0: one freshness row per feed: status, age, how often it is checked, and when the next check is due
      $("tab-sources").innerHTML = (nStale ? `<div class="stale">${nStale} feed${nStale > 1 ? "s are" : " is"} overdue (more than three refresh intervals old).</div>` : "") +
        `<table class="src"><tr><th>Feed</th><th>Status</th><th>Age</th><th title="refresh interval / next check">Every · next</th></tr>${Object.entries(st.feeds).map(([k, v]) => {
          const next = v.every && v.age_s != null ? Math.max(0, v.every - v.age_s) : null;
          const stat = v.running ? ["var(--accent)", "CHECKING"] : v.stale ? ["var(--accent)", "STALE"] : v.ok ? ["var(--ok)", "OK"] : ["var(--bad)", "FAIL"];
          return `<tr><td>${esc(label[k] || k)}</td><td style="color:${stat[0]}">${stat[1]}${v.error ? `<div class="muted small">${esc(v.error)}</div>` : ""}</td><td class="muted">${dur(v.age_s)}</td>` +
            `<td class="muted">${v.every ? dur(v.every) + " · " + (next === 0 ? "due" : dur(next)) : "–"}</td></tr>`;
        }).join("")}</table>
        <div class="card" style="margin-top:10px"><h4>Official statements</h4><ul id="offl"></ul></div>
        <div class="muted small">Ground Truth ${esc(st.version)} · personal, non-commercial use. Content belongs to its sources; links go back to originals. Ship traffic: ${GFW_ATTR} (CC BY-NC 4.0). Aircraft types from <a href="https://hexdb.io" target="_blank" rel="noopener">hexdb.io</a>; aircraft photos © their photographers via <a href="https://www.planespotters.net" target="_blank" rel="noopener">Planespotters.net</a>. Alerts: <a href="https://www.tzevaadom.co.il/en/" target="_blank" rel="noopener">Tzeva Adom</a> and <a href="https://alerts.in.ua/en" target="_blank" rel="noopener">alerts.in.ua</a>; region shapes from Natural Earth. US embassy alerts: the posts' own feeds (US government, public domain). Chokepoint transits: ${PW_ATTR}. ${OS_ATTR}. Flags from the ITU maritime identification digits.${EXT.credits.map((c) => " " + c).join("")}</div>`;
      api("feed/official").then((o) => { $("offl").innerHTML = ((o.data || {}).items || []).slice(0, 10).map((i) => `<li><span class="badge">${esc(i.source)}</span> <a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a></li>`).join(""); });
    });
  }

  // ---------- 1.0: push ----------
  // The server announces every finished feed run on /api/stream (Server-Sent Events). Extension feeds and military
  // aircraft are refetched at once; everything else triggers one full reload, at most once a minute. Without the
  // stream (the static public mirror, an old server) the timers keep the page fresh as before.
  const PAGE_V = ((document.querySelector('script[src*="app.js"]') || {}).src || "").split("v=")[1] || "";
  const PUSH_SKIP = new Set(["tzeva", "tzevalive", "airalerts", "embassy"]); // the alerts timer is already faster
  function pushLoadAll() {
    if (allTimer) return;
    allTimer = setTimeout(() => { allTimer = null; loadAll(); }, Math.max(1500, 60000 - (Date.now() - lastAll)));
  }
  function startPush() {
    // 1.5.0: the public copy is static files on GitHub Pages: there is no api/stream, so opening one only 404s.
    // Its timers keep it fresh, and the header light already reads "Public copy".
    if (PUBLIC || !window.EventSource) return;
    let fails = 0;
    const es = new EventSource("api/stream");
    es.addEventListener("hello", (e) => {
      fails = 0; S.push = true; $("utc").classList.add("push"); zoneUi();
      let h = {}; try { h = JSON.parse(e.data); } catch (err) { /* ignore */ }
      // a new release went live: load it once (the guard stops a loop if a cache serves the old page again)
      if (h.version && PAGE_V && h.version !== PAGE_V) {
        let done = null; try { done = sessionStorage.getItem("gt-reloaded"); sessionStorage.setItem("gt-reloaded", h.version); } catch (err) { /* private mode */ }
        if (done !== h.version) location.reload();
      }
    });
    es.addEventListener("feed", (e) => {
      let m = {}; try { m = JSON.parse(e.data); } catch (err) { return; }
      const f = m.feed;
      if (!f || PUSH_SKIP.has(f)) return;
      if (EXT.feeds[f]) loadExt(f, true);
      else if (f === "mil") loadLive();
      else pushLoadAll();
    });
    es.onerror = () => {
      S.push = false; $("utc").classList.remove("push"); zoneUi();
      if (++fails >= 3 || es.readyState === 2) es.close();
    };
  }

  // ---------- 0.11.0: extension API (web/ext/*.js) ----------
  window.GTX = {
    version: "1.5", GLYPHS, drawGlyph, mapImage, glyphOf, glyphUrl,  // 1.5: glyph drawing for extensions (1.6.0)
    map, S, api, esc, fmtT, fmtD, fmtDay, when, ago, nf, isoMs, showPopup, THEATRES, CATS, country, dayMs,
    zone: () => ZONE,  // 1.3: "et" or "utc"
    below: { events: "ev-halo", sirens: "il-halo" },  // beforeId values for map.addLayer: under curated pins / under sirens
    // {key, label, feed, on, ids: [map layer ids], click: [clickable ids], clickBefore, after: layer key, count: fn, legend: html}
    layer(o) {
      const row = [o.key, o.label, o.feed || o.key, o.on !== false];
      const at = o.after ? LAYERS.findIndex((l) => l[0] === o.after) : -1;
      if (at >= 0) LAYERS.splice(at + 1, 0, row); else LAYERS.push(row);
      GROUPS[o.key] = o.ids || [];
      (o.click || []).forEach((id) => { const i = o.clickBefore ? CLICK_ORDER.indexOf(o.clickBefore) : -1; if (i >= 0) CLICK_ORDER.splice(i, 0, id); else CLICK_ORDER.push(id); });
      if (o.count) EXT.counts[o.key] = o.count;
      if (o.legend) EXT.legends[o.key] = o.legend;
    },
    onMapLoad(fn) { EXT.mapLoad.push(fn); },
    legend(key, html) { EXT.legends[key] = html; },
    // {label, title, note, counts: () => ({theatre: n}) or null when the feed has no data}: a Brief-tab coverage column
    briefColumn(o) { EXT.briefCols.push(o); },
    popup(layerId, fn) { EXT.popups[layerId] = fn; },
    feed(name, fn, opt) { EXT.feeds[name] = { fn, events: !!(opt && opt.events) }; if (opt && opt.every) setInterval(() => S.push || loadExt(name), opt.every); },
    eventSource(name, fn) { EXT.feeds[name] = { fn, events: true }; },
    tab(o) {
      EXT.tabs.push(o);
      const b = document.createElement("button"); b.dataset.tab = o.id; b.textContent = o.label;
      const before = o.before ? [...$("tabs").children].find((x) => x.dataset.tab === o.before) : null;
      $("tabs").insertBefore(b, before || null);
      const d = document.createElement("div"); d.className = "tabbody hidden"; d.id = "tab-" + o.id;
      $("tab-sources").parentNode.insertBefore(d, $("tab-sources"));
    },
    isOpen(tabId) { const el = $("tab-" + tabId); return !!el && !el.classList.contains("hidden"); },
    label(feed, text) { EXT.labels[feed] = text; },
    credit(html) { EXT.credits.push(html); },
    kpi(fn) { EXT.kpis.push(fn); },
    onRender(fn) { EXT.onRender.push(fn); },
    refresh(name) { return loadExt(name); },
    // 1.2: a source for the Feed tab; see "one Feed for every source" above for the item fields
    stream(o) { stream(o); },
    // the checkbox once the layer list is drawn; before that (map load can come first), the layer's registered default
    layerOn(key) {
      const el = document.querySelector(`#layers input[data-layer="${key}"]`);
      if (el) return el.checked;
      const row = LAYERS.find((l) => l[0] === key);
      return !row || row[3];
    },
  };
  // Extensions load BEFORE app.js and queue their setup: (window.GTXQ = window.GTXQ || []).push((GTX) => {...}).
  // The queue runs here, synchronously, so every layer, tab and map hook is registered before the map's load event.
  (window.GTXQ || []).forEach((fn) => { try { fn(window.GTX); } catch (err) { console.error("GTX extension", err); } });
  window.GTXQ = { push: (fn) => fn(window.GTX) };

  // ---------- 1.4.0: version + live light (header) ----------
  // The page's version and one light for how fresh it is. Live: the push stream is connected, so feed updates land
  // within seconds. Polling: no stream, but the server answered in the last 6 min, so the timers keep the page fresh.
  // Offline: the newest call failed and nothing has worked for over a minute, or nothing has worked for 6 min.
  // Public copy: the GitHub Pages mirror has no stream and is rebuilt about every 10 min, so it never shows Polling
  // or Offline (its stream failures are expected). Connecting: the first seconds, before the stream has had a chance.
  // netMark is hoisted and keeps its times on S, so api() can report a reply whenever it lands.
  function netMark(ok, p, j) {
    const n = S.net || (S.net = { ok: 0, bad: 0, ver: "" });
    if (!ok) { n.bad = Date.now(); return; }
    n.ok = Date.now();
    if (p === "status" && j && j.version) n.ver = String(j.version);  // the server's own version, beside the page's
  }
  const LIVE_T0 = Date.now(), LIVE_SHOWN = {};
  const LIVE_TXT = {
    on: ["Live", "Live: the server pushes each feed update as it lands."],
    poll: ["Polling", "Polling: the push stream is off, so the page refreshes on its timers (aircraft every 45 s, the rest every 5 min)."],
    off: ["Offline", "Offline: the server is not answering. The page keeps trying."],
    pub: ["Public copy", "Public copy, refreshed about every 10 minutes, not live."],
    wait: ["Connecting", "Connecting to the server."],
  };
  function liveState(now) {
    const n = S.net || {}, ref = n.ok || LIVE_T0;  // before the first reply, count from page load
    if (PUBLIC) return "pub";
    if (S.push) return "on";
    if ((n.bad > (n.ok || 0) && now - ref > 60000) || now - ref > 6 * 60000) return "off";
    if (!n.ok || (window.EventSource && now - LIVE_T0 < 10000)) return "wait";  // no amber flash while the stream connects
    return "poll";
  }
  // Feed health from the last /api/status: OK = ran fine and not overdue, down = the last run failed.
  function feedHealth() {
    const v = Object.values(S.status || {}), ok = v.filter((f) => f.ok && !f.stale).length;
    const down = v.filter((f) => f.ok === false).length, late = v.filter((f) => f.ok && f.stale).length;
    const more = [down && down + " down", late && late + " overdue"].filter(Boolean).join(", ");
    return { down, txt: v.length ? `${ok}/${v.length} feeds OK` + (more ? ` (${more})` : "") : "" };
  }
  // Once a second; each piece of the DOM is written only when its text changes (the label is aria-live).
  function paintLive() {
    const box = $("live");
    if (!box) return;
    const now = Date.now(), st = liveState(now), n = S.net || {}, h = feedHealth(), [label, why] = LIVE_TXT[st];
    const put = (k, v, fn) => { if (LIVE_SHOWN[k] !== v) { LIVE_SHOWN[k] = v; fn(v); } };
    const vers = `Page ${PAGE_V ? "v" + PAGE_V : "version unknown"} · server ${n.ver ? "v" + n.ver : "version not known yet"}` +
      (PAGE_V && n.ver && PAGE_V !== n.ver ? " (reload for the new release)" : "");
    const tip = [why + ((st === "poll" || st === "off") && n.ok ? ` Last reply ${ago(n.ok)}.` : ""), vers, h.txt].filter(Boolean).join("\n");
    put("cls", "live " + st, (v) => { box.className = v; });
    put("ver", PAGE_V || n.ver ? "v" + (PAGE_V || n.ver) : "", (v) => { $("livev").textContent = v; });
    put("label", label, (v) => { $("livet").textContent = v; });
    put("down", h.down ? ` · ${h.down} down` : "", (v) => { $("liven").textContent = v; });
    put("tip", tip, (v) => { box.title = v; });
  }
  paintLive();
  setInterval(paintLive, 1000);

  // ---------- 1.4.3: tooltips on a PC ----------
  // Asked for: "add tool tips appear on pc dashboards all versions". On a mouse (hover: hover, pointer: fine) every element
  // with a title gets a styled tooltip after 0.35 s instead of the browser's slow, plain one; touch screens are left
  // alone. The title stays on the element at rest (screen readers read it) and is lifted off only while it shows, so
  // two tooltips never stack. Tabs registered by extensions get their tooltips here, after the extensions have run.
  const TAB_TIP = { feed: "Every source, newest first: map pins, wire, Telegram, official, alerts, hazards, airspace, cyber",
    wire: "News wire and Telegram, following the theatre", alerts: "Air-raid alerts, Israel sirens and US embassy alerts",
    brief: "All sources by theatre", sea: "Ships, chokepoints, UKMTO and Hormuz", ai: "The analyst's picture, per theatre",
    signals: "Tsunami, radiation, NTAS and sanctions", cyber: "Ransomware, DDoS targets, CISA alerts and routing",
    sources: "Every feed, how fresh it is, and the credits" };
  document.querySelectorAll("#tabs button[data-tab]").forEach((b) => { if (!b.title && TAB_TIP[b.dataset.tab]) b.title = TAB_TIP[b.dataset.tab]; });
  if (window.matchMedia && matchMedia("(hover: hover) and (pointer: fine)").matches) {
    const tip = document.createElement("div");
    tip.id = "gtip"; tip.setAttribute("role", "tooltip"); tip.hidden = true; document.body.appendChild(tip);
    let cur = null, held = "", timer = null, mx = 0, my = 0;
    const place = () => {
      const r = tip.getBoundingClientRect();
      let L = mx + 14, T = my + 18;
      if (L + r.width > innerWidth - 8) L = Math.max(8, mx - r.width - 10);
      if (T + r.height > innerHeight - 8) T = Math.max(8, my - r.height - 12);
      tip.style.left = L + "px"; tip.style.top = T + "px";
    };
    const hide = () => {
      clearTimeout(timer); timer = null; tip.hidden = true;
      if (cur && !cur.hasAttribute("title") && held) cur.setAttribute("title", held);  // unless the page rewrote it meanwhile
      cur = null; held = "";
    };
    document.addEventListener("mouseover", (e) => {
      const el = e.target.closest ? e.target.closest("[title]") : null;
      if (cur && cur.contains(e.target) && (!el || el === cur || !cur.contains(el))) return;  // still inside the same element
      hide();
      if (!el || !el.title.trim()) return;
      cur = el; held = el.title; el.removeAttribute("title"); mx = e.clientX; my = e.clientY;
      timer = setTimeout(() => { if (!cur || !cur.isConnected) return hide(); tip.textContent = held; tip.hidden = false; place(); }, 350);
    });
    document.addEventListener("mousemove", (e) => { mx = e.clientX; my = e.clientY; if (cur && !cur.isConnected) hide(); else if (!tip.hidden) place(); }, { passive: true });
    document.addEventListener("mouseout", (e) => { if (cur && !cur.contains(e.relatedTarget)) hide(); });
    ["scroll", "mousedown", "keydown", "blur"].forEach((t) => window.addEventListener(t, hide, true));
  }

  // ---------- 1.3.0: the clock and the zone switch ----------
  // The clock shows the page's zone with the other one under it; clicking it switches. Times in the rail does the
  // same on phones, where the clock is hidden.
  function tick() {
    const now = Date.now(), utc = new Date(now).toISOString(), p = zparts(now, ET), et = `${p.hour}:${p.minute}`;
    $("utc").textContent = ZONE === "utc" ? utc.slice(11, 19) : `${et}:${p.second} ${p.dayPeriod}`;
    $("clockz").textContent = ZONE === "utc" ? `UTC · ${et} ${p.dayPeriod} ${p.timeZoneName}` : p.timeZoneName;  // 1.7.1: Eastern shows Eastern only
  }
  function zoneUi() {
    const other = ZONE === "utc" ? "Eastern time" : "UTC";
    $("clock").setAttribute("aria-label", `Times are in ${zoneName()}. Switch to ${other}`);
    $("clock").title = `Times are in ${zoneName()}. Click for ${other}.` + (S.push ? " Live: the server pushes each feed update." : "");
    [...$("tzchips").querySelectorAll("[data-tz]")].forEach((b) => { const on = b.dataset.tz === ZONE; b.classList.toggle("off", !on); b.setAttribute("aria-pressed", on ? "true" : "false"); });
    const ab = $("tzchips").querySelector('[data-tz="et"] .muted');
    if (ab) ab.textContent = zparts(Date.now(), ET).timeZoneName;  // EST or EDT
  }
  // Redraw everything that shows a time: render() covers the map, the chart, the Feed (rebuilt from the sources, not
  // its cache) and its notice, and an open Brief, Sea, Sources or Analyst tab; then the banner and an open Alerts or
  // extension tab. An open map popup is closed.
  function rezone() {
    const run = (fn, what) => { try { fn(); } catch (err) { console.error("time zone redraw: " + what, err); } };
    if (popup) { popup.remove(); popup = null; }  // an open popup would keep the old zone's times
    STREAMS.forEach((st) => { st._d = null; });  // Feed rows are cached per source, some with times in their text (TFR spans)
    run(render, "render");  // also the Feed and its notice
    run(renderBanner, "banner");
    const open = [...$("tabs").children].find((x) => x.classList.contains("on"));
    const ext = open && EXT.tabs.find((x) => x.id === open.dataset.tab);
    if (ext) run(() => ext.render($("tab-" + ext.id)), ext.id);
    else if (open && open.dataset.tab === "alerts") run(renderAlerts, "alerts");
    if (!S.events) run(feedSoon, "feed");  // render() returns early until the map's events load
  }
  function setZone(z) {
    ZONE = z === "utc" ? "utc" : "et";
    try { localStorage.setItem("gt-tz", ZONE); } catch (e) { /* private window: this visit only */ }
    zoneUi(); tick(); rezone();
  }
  $("clock").onclick = () => setZone(ZONE === "utc" ? "et" : "utc");
  $("tzchips").onclick = (e) => { const b = e.target.closest("[data-tz]"); if (b) setZone(b.dataset.tz); };
  zoneUi(); tick();
  setInterval(tick, 1000);
})();
