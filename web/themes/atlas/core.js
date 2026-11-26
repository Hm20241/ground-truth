/* Ground Truth 1.7.0, Atlas theme, core: helpers, the time zone, icons, the data loaders and the one list of entries
   every screen reads. Read-only: every request is a GET to a relative api/ path. Nothing here is invented; a missing
   feed stays missing. The event pins follow Classic's rule: the source map's pins plus the GeoConfirmed, CIR and
   kinetic pins it does not already carry (web/app.js mergeEvents), and the fronts count those merged pins.
   1.7.1: a copy is asked only for the feeds its api/status lists (the public copy carries about 30 of them); a feed it
   does not list is not an error, and the screens say "Not on this copy." */
(() => {
  "use strict";
  const A = (window.ATLAS = {});
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nf = (n) => (n == null || n === "" ? "–" : Number(n).toLocaleString("en-US"));
  const LS = {
    get(k, d) { try { const v = localStorage.getItem("atlas-" + k); return v == null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("atlas-" + k, String(v)); } catch (e) { /* private window */ } },
  };
  const REDUCED = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);

  // ---------- time: Eastern by default, UTC on request ----------
  const ET = "America/New_York";
  let ZONE = LS.get("tz", "et") === "utc" ? "utc" : "et";
  const tzName = () => (ZONE === "utc" ? "UTC" : ET);
  const DTF = {};
  const parts = (ms, opt, key) => {
    const k = key + tzName(), f = DTF[k] || (DTF[k] = new Intl.DateTimeFormat("en-US", { timeZone: tzName(), ...opt }));
    const o = {}; f.formatToParts(new Date(ms)).forEach((p) => { o[p.type] = p.value; }); return o;
  };
  const fmtT = (ms) => {
    if (ZONE === "utc") return new Date(ms).toISOString().slice(11, 16) + " UTC";
    const p = parts(ms, { hour: "numeric", minute: "2-digit", hour12: true }, "t"); return `${p.hour}:${p.minute} ${p.dayPeriod}`;
  };
  const zoneAbbr = () => (ZONE === "utc" ? "UTC" : parts(Date.now(), { hour: "numeric", timeZoneName: "short" }, "z").timeZoneName);
  const fmtDate = (ms) => { const p = parts(ms, { weekday: "short", day: "numeric", month: "short" }, "d"); return `${p.weekday} ${p.day} ${p.month}`; };
  const dayKey = (ms) => { const p = parts(ms, { year: "numeric", month: "2-digit", day: "2-digit" }, "k"); return `${p.year}-${p.month}-${p.day}`; };
  const dayLabel = (ms) => { const k = dayKey(ms), now = Date.now(); return k === dayKey(now) ? "Today" : k === dayKey(now - 86400000) ? "Yesterday" : fmtDate(ms); };
  const ago = (ms) => {
    const d = Date.now() - ms, m = Math.round(Math.abs(d) / 60000);
    if (m < 1) return "just now";
    const s = m < 60 ? m + " min" : m < 2880 ? Math.round(m / 60) + " h" : Math.round(m / 1440) + " d";
    return d < 0 ? "in " + s : s + " ago";
  };
  // A time with no zone is the server's UTC, never the browser's.
  const isoMs = (s) => (s ? Date.parse(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? s.replace(" ", "T") + "Z" : /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? s + "Z" : s) : NaN);
  const isDay = (s) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s);
  // A date-only value names a day; it sorts at noon UTC of that day, never later than now, and shows as the day alone.
  const dayMs = (s) => Math.min(Date.parse(s + "T12:00:00Z"), Date.now());
  const fmtDayOnly = (s) => { const d = new Date(s + "T12:00:00Z"); return d.toLocaleDateString("en-US", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" }).replace(",", ""); };
  const when = (e) => (e.dateOnly ? fmtDayOnly(e.dateOnly) : `${fmtDate(e.ts)}, ${fmtT(e.ts)} (${ago(e.ts)})`);
  const whenShort = (e) => (e.dateOnly ? fmtDayOnly(e.dateOnly) : ago(e.ts));
  // The analyst writes times in UTC ("05:38Z"). In Eastern mode each gets its Eastern time beside it; the words stay as written.
  const zText = (s, ref) => (ZONE === "utc" || !s ? s || "" : String(s).replace(/(^|[^\d:])([01]\d|2[0-3]):([0-5]\d)Z\b/g, (m, pre, h, mi) => {
    const d = new Date(Number.isFinite(ref) ? ref : Date.now());
    return `${pre}${h}:${mi}Z (${fmtT(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), +h, +mi))})`; }));

  // ---------- icons: 24-unit drawings. The pin glyphs are today's page's own (web/app.js GLYPHS). ----------
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
    // drawn for this theme
    news: { fill: "M4 4.5H20V19.5H4Z M6.5 7.5H17.5V10H6.5Z M6.5 12H11.5V17H6.5Z M13.5 12H17.5V13.6H13.5Z M13.5 15.4H17.5V17H13.5Z" },
    send: { fill: "M21.5 3L2.5 10.8L9.6 13.4L12.2 20.6Z" },
    quake: { stroke: [["M2 12H6L8.5 5L12 19L15.5 8L17.5 12H22", 2]] },
    signal: { stroke: [["M4 9.5C8.5 5 15.5 5 20 9.5", 2], ["M7 13C10 10.2 14 10.2 17 13", 2], ["M12 17.4H12.1", 2.8]] },
    globe: { stroke: [["M12 3A9 9 0 1 1 11.99 3Z", 1.8], ["M3 12H21", 1.6], ["M12 3C8.5 7 8.5 17 12 21C15.5 17 15.5 7 12 3Z", 1.6]] },
    dot: { stroke: [["M12 12H12.1", 7]] },
    search: { stroke: [["M10.5 4A6.5 6.5 0 1 1 10.49 4Z", 2], ["M15.5 15.5L20.5 20.5", 2.2]] },
    close: { stroke: [["M6 6L18 18", 2.2], ["M18 6L6 18", 2.2]] },
    left: { stroke: [["M14.5 5.5L8 12L14.5 18.5", 2.2]] },
    right: { stroke: [["M9.5 5.5L16 12L9.5 18.5", 2.2]] },
    up: { stroke: [["M5.5 14.5L12 8L18.5 14.5", 2.2]] },
    down: { stroke: [["M5.5 9.5L12 16L18.5 9.5", 2.2]] },
    filter: { stroke: [["M4 7H20", 2], ["M7 12H17", 2], ["M10 17H14", 2]] },
    now: { stroke: [["M12 3.5A8.5 8.5 0 1 1 11.99 3.5Z", 2], ["M12 7.5V12L15.2 14", 2]] },
    feed: { stroke: [["M8.5 6.5H20", 2], ["M8.5 12H20", 2], ["M8.5 17.5H20", 2], ["M4.2 6.5H4.3", 2.8], ["M4.2 12H4.3", 2.8], ["M4.2 17.5H4.3", 2.8]] },
    topics: { stroke: [["M12 3.5L21 8.5L12 13.5L3 8.5Z", 1.9], ["M3.8 12.6L12 17.2L20.2 12.6", 1.9], ["M3.8 16.4L12 21L20.2 16.4", 1.9]] },
    more: { stroke: [["M5 12H5.1", 3.4], ["M12 12H12.1", 3.4], ["M19 12H19.1", 3.4]] },
    pause: { stroke: [["M9 6.5V17.5", 2.8], ["M15 6.5V17.5", 2.8]] },
    play: { fill: "M8.5 5.5L19 12L8.5 18.5Z" },
    out: { stroke: [["M10 5H5V19H19V14", 2], ["M13.5 4.5H19.5V10.5", 2], ["M19 5L11 13", 2]] },
    pin: { fill: "M12 2.5C8 2.5 5.2 5.5 5.2 9.2C5.2 14 12 21.5 12 21.5C12 21.5 18.8 14 18.8 9.2C18.8 5.5 16 2.5 12 2.5Z M12 6.6A2.7 2.7 0 1 0 12.01 6.6Z" },
  };
  const ico = (name) => {
    const g = GLYPHS[name] || GLYPHS.dot;
    return `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${g.fill ? `<path d="${g.fill}" fill="currentColor" fill-rule="evenodd"/>` : ""}${
      (g.stroke || []).map(([d, w]) => `<path d="${d}" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`).join("")}</svg>`;
  };
  const ICON_GLYPH = { 1830: "megaphone", 1571: "fire", 1504: "plane", 1657: "officer", 1722: "truck", 1812: "gunner", 1569: "ship",
    1864: "wreck", 1556: "skull", 1528: "bridge", 1593: "helicopter", 1716: "train", 1660: "bolt" };
  const CAT_GLYPH = { strike: "fire", energy: "bolt", maritime: "ship", casualty: "skull", aviation: "plane", drone: "plane", forces: "officer" };

  // ---------- the words and the few colours ----------
  const COL = { red: "#ff7868", amber: "#f7bd62", blue: "#6bb8ff", slate: "#cdd4de" };
  const CATS = { strike: "Strike or explosion", energy: "Energy and infrastructure", missile: "Missile or air defence", drone: "Drone", maritime: "At sea",
    alert: "Alert or force posture", cyber: "Communications or outage", security: "Security incident", casualty: "Casualties", forces: "Forces and equipment",
    aviation: "Aviation", political: "Political statement", report: "Report", other: "Other" };
  // Four pin colours instead of fourteen: fighting, sea, infrastructure, words.
  const catTone = (c) => (c === "maritime" ? "blue" : c === "energy" || c === "cyber" ? "amber" : ["political", "report", "other", "aviation"].includes(c) ? "slate" : "red");
  const REGIONS = {
    "ukraine-russia": ["Ukraine and Russia", [36.5, 49.2, 4.9]], "middle-east": ["Middle East and Gulf", [50.5, 27.5, 4.2]], "europe-nato": ["Europe and NATO", [15, 54, 3.6]],
    "americas": ["Americas", [-85, 33, 3]], "indo-pacific": ["Indo-Pacific", [125, 27, 3.5]], "south-asia": ["South and Central Asia", [70, 30, 3.8]], "africa": ["Africa", [20, 8, 2.9]],
  };
  const regionName = (k) => (REGIONS[k] ? REGIONS[k][0] : "");
  const TOPICS = [
    { k: "all", name: "All", icon: "globe", blurb: "Event pins, fronts, alerts and incidents at sea together." },
    { k: "conflict", name: "Conflict", icon: "swords", blurb: "Event pins, battle fronts and the front area in Ukraine." },
    { k: "alerts", name: "Alerts", icon: "megaphone", blurb: "Air-raid alerts, sirens and US embassy security alerts." },
    { k: "air", name: "Air", icon: "plane", blurb: "Military aircraft, closed airspace, emergency codes and GPS jamming." },
    { k: "sea", name: "Sea", icon: "ship", blurb: "Incidents at sea, chokepoints and ships." },
    { k: "outages", name: "Outages", icon: "bolt", blurb: "Power, internet, mobile networks, websites, cloud services and undersea cables." },
    { k: "cyber", name: "Cyber", icon: "shield", blurb: "Ransomware claims, attacks on critical services and security advisories." },
    { k: "hazards", name: "Hazards", icon: "fire", blurb: "Earthquakes, storms, floods, droughts, wildfires and fires seen from space." },
    { k: "official", name: "Official", icon: "officer", blurb: "Government statements, embassy alerts and travel advisories." },
  ];
  const GROUPS = { pins: "Map pins", wire: "News wire", telegram: "Telegram", official: "Official", alerts: "Alerts", sea: "Sea incidents",
    air: "Air", outages: "Outages", cyber: "Cyber", hazards: "Hazards" };
  const DEFAULT_GROUPS = ["pins", "wire", "telegram", "official", "alerts", "sea"];

  // ---------- state ----------
  const S = { zone: ZONE, dest: "now", page: null, topic: "all", q: "", hours: 0, region: "all", groups: new Set(DEFAULT_GROUPS), sel: null,
    d: {}, entries: [], byId: new Map(), fronts: [], cc: new Map(), reg: new Map(), loaded: new Set(), failed: new Set(), net: "loading",
    lastSeen: Number(LS.get("seen", 0)) || 0, opened: Date.now() };
  const subs = {};
  const on = (ev, fn) => { (subs[ev] = subs[ev] || []).push(fn); };
  const emit = (ev, x) => (subs[ev] || []).forEach((fn) => { try { fn(x); } catch (err) { console.error("Atlas " + ev, err); } });

  // ---------- geometry helpers ----------
  const RAD = Math.PI / 180;
  const ptKm = (a, b) => Math.hypot((b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32, (b[1] - a[1]) * 110.57);
  function segKm(p, a, b) {
    const k = Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32;
    const ax = (a[0] - p[0]) * k, ay = (a[1] - p[1]) * 110.57, bx = (b[0] - p[0]) * k, by = (b[1] - p[1]) * 110.57;
    const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L)) : 0;
    return Math.hypot(ax + t * dx, ay + t * dy);
  }
  const lineKm = (pt, cs) => { let d = Infinity; for (let i = 1; i < cs.length; i++) d = Math.min(d, segKm(pt, cs[i - 1], cs[i])); return d; };
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
  // The middle of a shape's biggest ring: good enough to fly to a country or a region.
  function centre(geom) {
    if (!geom) return null;
    if (geom.type === "Point") return geom.coordinates;
    const rings = geom.type === "Polygon" ? [geom.coordinates[0]] : geom.type === "MultiPolygon" ? geom.coordinates.map((p) => p[0]) : [];
    const r = rings.sort((a, b) => b.length - a.length)[0]; if (!r || !r.length) return null;
    let x = 0, y = 0; r.forEach((c) => { x += c[0]; y += c[1]; }); return [x / r.length, y / r.length];
  }
  const hash = (s) => { let h = 5381; s = String(s); for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0; return h.toString(36); };

  // ---------- loading ----------
  let okN = 0, badN = 0;
  const api = (p) => fetch("api/" + p, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
    .then((j) => { okN++; return j; }, (e) => { badN++; return Promise.reject(e); });
  // name -> path; "feed/x" replies wrap their data in {ok, at, error, data}
  const PATHS = { events: "events", summary: "summary", analysis: "analysis", status: "status", alerts: "alerts", news_geo: "news_geo",
    outages_geo: "outages_geo", cyber_geo: "cyber_geo", advisories_geo: "advisories_geo" };
  const CORE = ["events", "summary", "analysis", "alerts", "status", "news_geo", "wire", "telegram", "front", "ukmto", "official"];
  // Three more pin sources join the source map's pins, as on the Classic page (web/ext/curated.js). name -> [what the card
  // calls it, its note]. A server that has not run one (the public mirror has no GeoConfirmed or CIR) is never asked for it.
  const PIN_SRC = {
    geoconfirmed: ["GeoConfirmed", "Geolocated by GeoConfirmed volunteers; the geolocation usually lands days after the event."],
    cir: ["CIR Eyes on Russia", "CIR publishes about a week after the event, on purpose."],
    kinetic: ["S2 Underground, Iran kinetic events", "Licensed CC BY-NC-SA 4.0; Ground Truth changed the layout and categories."],
  };
  const EXTRA = Object.keys(PIN_SRC);
  const LIGHT = ["mil", "portwatch", "quakes", "hazards", "tfr", "squawk", "power", "cellular", "websites", "cloud", "outages", "outages_geo", "cyber", "advisories", "advisories_geo"];
  // heavier replies wait until their topic is opened
  const TOPIC_NEEDS = { sea: ["ships", "portwatch"], hazards: ["firms", "quakes", "hazards"], outages: ["cables", "outages_geo", "power", "cellular", "websites", "cloud", "outages"],
    cyber: ["cyber", "cyber_geo"], air: ["mil", "tfr", "squawk"], official: ["advisories", "advisories_geo"] };
  // ---------- which feeds this copy carries (1.7.1) ----------
  // Once api/status is known, api/feed/<name> is asked for only when status.feeds lists <name>, as on the Classic page
  // (web/app.js loadExt). A reply that goes with a feed follows it. The five core replies are always asked for. If status
  // itself does not load, every feed is asked for, as before 1.7.1.
  const ALWAYS = ["events", "summary", "analysis", "alerts", "status"];
  const WITH = { news_geo: ["wire", "telegram"], cyber_geo: ["cyber"], outages_geo: ["outages"], advisories_geo: ["advisories"] };
  const has = (name) => { const fs = (S.d.status || {}).feeds; return !fs || ALWAYS.includes(name) || (WITH[name] || [name]).some((n) => n in fs); };
  const hasAny = (names) => (names || []).some(has);
  // the feeds behind a topic pill and behind a Filter source: with none of them on this copy, the control is left out
  const TOPIC_FEEDS = { air: ["mil", "tfr", "squawk"], sea: ["ukmto", "portwatch", "ships"], outages: ["power", "cellular", "websites", "cloud", "outages", "cables"],
    cyber: ["cyber"], hazards: ["firms", "quakes", "hazards"] };
  const GROUP_FEEDS = { wire: ["wire"], telegram: ["telegram"], official: ["official"], sea: ["ukmto"], air: ["tfr", "squawk"],
    outages: ["power", "cellular", "websites", "cloud", "outages"], cyber: ["cyber"], hazards: ["quakes", "hazards"] };
  const topicOn = (k) => !TOPIC_FEEDS[k] || hasAny(TOPIC_FEEDS[k]);
  const groupOn = (g) => !GROUP_FEEDS[g] || hasAny(GROUP_FEEDS[g]);

  const pending = new Map();
  let statusP = null;
  // Everything but the core waits for the first status reply, then is asked for only if this copy carries it.
  function load(name, force) {
    if (ALWAYS.includes(name)) return fetchOne(name, force);
    return (statusP || (statusP = fetchOne("status"))).then(() => (has(name) ? fetchOne(name, force) : undefined));
  }
  function fetchOne(name, force) {
    if (pending.has(name)) return pending.get(name);
    if (S.loaded.has(name) && !force) return Promise.resolve();
    const p = api(PATHS[name] || "feed/" + name).then((j) => {
      const d = PATHS[name] ? j : j && j.data;
      if (d == null) { S.failed.add(name); return; }
      S.d[name] = d; S.loaded.add(name); S.failed.delete(name);
    }).catch(() => { S.failed.add(name); }).finally(() => { pending.delete(name); changed(name); });
    pending.set(name, p); return p;
  }
  const need = (names) => Promise.all((names || []).map((n) => load(n)));
  let t0 = null;
  const changed = (name) => { clearTimeout(t0); t0 = setTimeout(() => { build(); S.net = badN && !okN ? "offline" : S.failed.size ? "partial" : "ok"; emit("data", name); }, 60); };

  function start(wall) {
    fetch("geo/alert-regions.json").then((r) => r.json()).then((fc) => { fc.features.forEach((f) => S.reg.set(f.id, f)); changed("reg"); }).catch(() => {});
    // only the extra pin feeds the server lists in its status: one it has never run would answer "not found"
    const extras = () => { const fs = (S.d.status || {}).feeds || {}; return EXTRA.filter((n) => n in fs); };
    need(CORE).then(async () => {
      for (const n of extras()) await load(n);   // the wall needs these too: its front count uses the merged pins
      if (wall) return;
      for (const n of LIGHT) { await load(n); await new Promise((r) => setTimeout(r, 250)); }  // one at a time: the server has been busy
    });
    setInterval(() => { if (!document.hidden) ["alerts", "summary"].forEach((n) => load(n, true)); }, 60000);
    setInterval(() => { if (!document.hidden) ["events", "wire", "telegram", "analysis", "status"].forEach((n) => load(n, true)); }, 180000);
    setInterval(() => { if (!document.hidden) extras().forEach((n) => load(n, true)); }, 900000);
  }

  // ---------- the event pins: the source map plus three more sources, one rule with the Classic page ----------
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
  // The source map wins: an extra pin is dropped when the map already has its id or the same post. Pins inside one
  // extra feed that cite the same post at different places are kept (they have their own ids).
  function mergedFeatures() {
    const base = (S.d.events || {}).features || [];
    if (!S.d.events) return base;
    const seen = new Set(base.map((f) => f.properties.id)), posts = new Set(base.map((f) => postKey(f.properties.url)).filter(Boolean)), extra = [];
    EXTRA.forEach((name) => ((((S.d[name] || {}).geojson) || {}).features || []).forEach((f) => {
      const p = f && f.properties;
      if (!p || p.kind !== "event" || seen.has(p.id) || posts.has(postKey(p.url))) return;
      seen.add(p.id); extra.push(f);
    }));
    return extra.length ? base.concat(extra) : base;
  }

  // ---------- one list of entries ----------
  const WIRE_TOPIC = { maritime: "sea", cyber: "cyber", energy: "outages", aviation: "air", strike: "conflict", missile: "conflict", drone: "conflict", casualty: "conflict", forces: "conflict", security: "conflict" };
  const OUT_KIND = { power: ["Power outage", "bolt"], cellular: ["Mobile network", "signal"], websites: ["Website or app", "globe"], cloud: ["Cloud service", "globe"] };
  const ccName = (a3) => (S.cc.get(a3) || {}).name || a3;
  function build() {
    const now = Date.now(), out = [], d = S.d;
    const add = (e) => { if (!Number.isFinite(e.ts)) return; if (e.ts > now) e.ts = now; e.topics = e.topics || []; out.push(e); };
    ((d.news_geo || {}).features || []).forEach((f) => S.cc.set(f.properties.a3, { name: f.properties.name, ll: f.geometry.coordinates, region: f.properties.theatre }));
    const feats = mergedFeatures();
    feats.forEach((f) => {
      const p = f.properties; if (p.kind !== "event" || !f.geometry || f.geometry.type !== "Point") return;
      const from = PIN_SRC[p.source];   // no source on a pin means the source map
      const tone = catTone(p.category), glyph = ICON_GLYPH[p.icon] || (GLYPHS[p.glyph] ? p.glyph : "") || CAT_GLYPH[p.category] || "dot";
      const topics = ["conflict"]; if (p.category === "maritime") topics.push("sea"); if (p.category === "energy" || p.category === "cyber") topics.push("outages");
      const facts = [["Pin from", from ? from[0] : p.source ? p.source_label || p.source : "Source map"]];
      if (p.thermal) facts.push(["Satellite", `${p.thermal.n} fire detection${+p.thermal.n === 1 ? "" : "s"} within ${p.thermal.nearest_km} km of this pin`]);
      if (p.ukmto) facts.push(["Sea incidents", `${p.ukmto.length} UKMTO notice${p.ukmto.length === 1 ? "" : "s"} within 60 km: ` + p.ukmto.slice(0, 4).map((u) => `#${u.num} ${u.type}`).join(", ")]);
      add({ id: "p" + hash(p.id), ts: p.ts_ms, title: p.title, kind: "Map pin", label: CATS[p.category] || "Event", group: "pins", topics, tone, c: COL[tone], glyph,
        place: p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name, region: p.theatre, ll: f.geometry.coordinates, url: safeUrl(p.url),
        src: p.handle ? "@" + p.handle : "", urlLabel: p.platform === "x" ? "Open the post on X" : "Open the source post", facts, cat: p.category,
        pinsrc: p.source || "", summary: p.source && p.description ? p.description : "", note: from ? from[1] : "" });
    });
    [["wire", "News wire", "news"], ["telegram", "Telegram", "send"]].forEach(([name, kind, glyph]) => ((d[name] || {}).items || []).forEach((i) => {
      const t = WIRE_TOPIC[i.category];
      add({ id: name[0] + i.id, ts: i.ts_ms, title: i.title, kind, label: kind, group: name, topics: t ? [t] : [], glyph, src: i.source_label, region: i.theatre,
        place: (i.countries || []).slice(0, 2).map(ccName).join(", "), cc: (i.countries || [])[0], url: safeUrl(i.url), summary: i.summary, urlLabel: name === "wire" ? "Read the article" : "Open the post on Telegram",
        facts: (i.also_in || []).length ? [["Also reported by", i.also_in.slice(0, 4).map((x) => (typeof x === "string" ? x : x.source_label || x.source || "")).filter(Boolean).join(", ")]] : [] });
    }));
    ((d.official || {}).items || []).forEach((i, n) => add({ id: "o" + hash(i.url || i.title + n), ts: isDay(i.date) ? dayMs(i.date) : isoMs(i.date), dateOnly: isDay(i.date) ? i.date : null,
      title: i.title, kind: "Official statement", label: "Official statement", group: "official", topics: ["official"], glyph: "officer", src: i.source, url: safeUrl(i.url), urlLabel: "Read the statement" }));
    ((d.ukmto || {}).items || []).forEach((i) => add({ id: "u" + i.num, ts: isDay(i.date) ? dayMs(i.date) : isoMs(i.date), dateOnly: isDay(i.date) ? i.date : null,
      title: `${i.type} at sea: ${i.where || "place not given"}`, kind: "Sea incident", label: "Sea incident", group: "sea", topics: ["sea"], glyph: "anchor", src: "UKMTO notice " + i.num,
      place: i.where, ll: i.coord || null, url: safeUrl(i.url), summary: i.text, urlLabel: "Open the UKMTO notice", tone: i.type === "Attack" ? "red" : "blue",
      note: i.geo_method === "area-centroid" ? "Placed at the middle of the named sea area, not an exact position." : "" }));
    const al = d.alerts || {};
    (((al.regions || {}).regions) || []).filter((r) => r.kind === "alert").forEach((r) => add({ id: "a" + r.id, ts: isoMs(r.since), title: `Air-raid alert: ${r.en}`, kind: "Air-raid alert",
      label: r.level === "red" ? "Air-raid alert, red" : "Air-raid alert, yellow", group: "alerts", topics: ["alerts"], glyph: "megaphone", tone: r.level === "red" ? "red" : "amber", src: "alerts.in.ua",
      place: r.c === "RU" ? "Russia" : r.c === "UA" ? "Ukraine" : r.c, ll: centre((S.reg.get(r.id) || {}).geometry),
      facts: [["In force for", r.duration || "–"], ["Type", (r.types || []).join(", ") || "–"]], note: "Not a safety service: follow official alerts if you are there." }));
    const posts = new Map((((al.embassy || {}).posts) || []).map((p) => [p.c, p]));
    (((al.embassy || {}).items) || []).forEach((i) => { const p = posts.get(i.c) || {};
      add({ id: "e" + i.id, ts: i.t * 1000, title: i.title, kind: "US embassy alert", label: "US embassy alert", group: "alerts", topics: ["alerts", "official"], glyph: "megaphone",
        src: "US Embassy" + (p.city ? " " + p.city : ""), place: p.n || "", ll: p.lon != null ? [p.lon, p.lat] : null, url: safeUrl(i.url), summary: i.event, urlLabel: "Read the alert" }); });
    ((((d.quakes || {}).geojson) || {}).features || []).forEach((f) => { const p = f.properties;
      add({ id: "q" + hash(p.id), ts: isoMs(p.time), title: `Magnitude ${p.mag} earthquake: ${p.place}`, kind: "Earthquake", label: p.suspected ? "Possible explosion" : "Earthquake", group: "hazards", topics: ["hazards"],
        glyph: "quake", src: p.source, place: p.country_name || p.place, ll: f.geometry.coordinates, url: safeUrl(p.url), urlLabel: "Open the earthquake record",
        facts: [["Depth", p.depth_km != null ? p.depth_km + " km" : "–"]].concat(p.watch_reason ? [["Why it is listed", p.watch_reason]] : []), tone: p.watch ? "amber" : "slate" }); });
    ((((d.hazards || {}).geojson) || {}).features || []).forEach((f) => { const p = f.properties;
      add({ id: "h" + hash(p.id), ts: isoMs(p.from), title: p.name, kind: p.type_label || "Hazard", label: (p.type_label || "Hazard") + (p.alert ? ", " + String(p.alert).toLowerCase() + " alert" : ""), group: "hazards", topics: ["hazards"],
        glyph: p.type === "EQ" ? "quake" : "fire", src: "GDACS", place: p.gdacs_country ? String(p.gdacs_country).split(",").slice(0, 2).join(",") : "", ll: f.geometry.coordinates, url: safeUrl(p.url), urlLabel: "Open the GDACS record",
        summary: p.severity, tone: p.alert === "Red" ? "red" : p.alert === "Orange" ? "amber" : "slate" }); });
    Object.keys(OUT_KIND).forEach((name) => ((d[name] || {}).items || []).forEach((i) => add({ id: "x" + hash(i.id), ts: i.ts_ms, title: i.title, kind: OUT_KIND[name][0], label: OUT_KIND[name][0] + (i.status ? ", " + i.status : ""),
      group: "outages", topics: ["outages"], glyph: OUT_KIND[name][1], src: i.provider, place: i.where, ll: i.ll || null, url: safeUrl(i.url), summary: i.summary, urlLabel: "Open the source", active: !!i.active,
      tone: i.active ? "amber" : "slate", sub: name })));
    ((d.outages || {}).countries || []).filter((c) => c.ongoing || c.watched).forEach((c) => { const ev = (c.events || [])[0]; if (!ev) return;
      const geo = (((d.outages_geo || {}).features) || []).find((f) => f.properties.code === c.code);
      add({ id: "i" + c.code, ts: isoMs(ev.start), title: `Internet outage: ${c.name}`, kind: "Internet outage", label: "Internet outage" + (c.ongoing ? ", ongoing" : ", ended"), group: "outages", topics: ["outages"],
        glyph: "signal", src: "IODA", place: c.name, ll: geo ? centre(geo.geometry) : null, facts: [["Lasting", ev.hours + " h" + (ev.ongoing ? " so far" : "")], ["Events in the last 3 days", String((c.events || []).length)]],
        active: !!c.ongoing, tone: c.ongoing ? "amber" : "slate", sub: "internet" }); });
    const CY = { ransom: "Ransomware claim", attack: "Reported cyber attack", ics: "Industrial systems advisory", kev: "Exploited vulnerability", ddos: "Denial-of-service target", cisa: "CISA advisory" };
    ((d.cyber || {}).items || []).forEach((i) => add({ id: "c" + hash(i.id), ts: i.ts_ms, title: i.title, kind: CY[i.kind] || "Cyber", label: CY[i.kind] || "Cyber", group: "cyber", topics: ["cyber"], glyph: "shield",
      src: i.group || "", place: (i.countries || []).slice(0, 2).map(ccName).join(", "), cc: (i.countries || [])[0], url: safeUrl(i.url), urlLabel: "Open the source record",
      facts: [].concat(i.sector ? [["Sector", i.sector]] : [], i.ci ? [["Critical service", "Yes"]] : []), tone: i.ci ? "amber" : "slate",
      note: i.kind === "ransom" ? "A criminal group's own claim, not confirmed by the victim." : "" }));
    ((d.tfr || {}).items || []).forEach((i) => add({ id: "t" + hash(i.notam_id), ts: isoMs(i.effective), title: `Flight restriction: ${i.title}`, kind: "Flight restriction", label: "Flight restriction, " + (i.status || ""), group: "air", topics: ["air"],
      glyph: "plane", src: "FAA", place: i.state ? i.state + ", United States" : "United States", ll: i.centre || null, url: safeUrl(i.url), urlLabel: "Open the FAA notice",
      facts: [["Reason", String(i.type || "").toLowerCase()], ["Height", `${i.floor || "?"} to ${i.ceiling || "?"}`], ["Ends", i.expires ? `${fmtDate(isoMs(i.expires))}, ${fmtT(isoMs(i.expires))}` : "not given"]] }));
    ((d.squawk || {}).items || []).forEach((i) => add({ id: "s" + i.hex + hash(i.first_seen), ts: isoMs(i.first_seen), title: `Emergency code ${i.squawk}: ${i.flight || i.reg || i.hex} (${i.meaning})`, kind: "Aircraft emergency code",
      label: "Aircraft emergency code", group: "air", topics: ["air"], glyph: "plane", src: i.source, place: i.country_name || "", ll: i.pos || null, tone: i.current ? "red" : "slate",
      facts: [["Aircraft", [i.desc, i.op].filter(Boolean).join(", ") || "–"], ["Still sending the code", i.current ? "Yes" : "No"]] }));
    out.sort((a, b) => b.ts - a.ts);
    S.entries = out; S.byId = new Map(out.map((e) => [e.id, e]));
    buildFronts(feats, out);
  }

  // Battle fronts: only the lines the source map's curator draws, and Classic's count (web/ext/fronts.js build()): every
  // event pin with a time, from the source map or one of the three extra sources, within 75 km of the line, in 24 h and 72 h.
  const FRONT_KIND = { contact: ["Front line", "swords", "The line of contact between the two sides, as the source map draws it."],
    supposed: ["Supposed front line", "swords", "A front line the source map marks as unconfirmed."],
    blockade: ["Blockade line", "anchor", "A naval blockade line on the source map."], defense: ["Defence line", "shield", "A defensive line or perimeter on the source map."] };
  function buildFronts(feats, entries) {
    const now = Date.now(), pins = entries.filter((e) => e.group === "pins" && e.ts);   // entries are newest first
    S.fronts = feats.filter((f) => f.properties.kind === "overlay" && f.geometry && f.geometry.type === "LineString" && FRONT_KIND[f.properties.front_kind]).map((f) => {
      const p = f.properties, cs = f.geometry.coordinates, k = FRONT_KIND[p.front_kind];
      const near = pins.filter((e) => lineKm(e.ll, cs) <= 75);
      const xs = cs.map((c) => c[0]), ys = cs.map((c) => c[1]), km = lenKm(cs);
      const n24 = near.filter((e) => now - e.ts < 24 * 3600e3).length, n72 = near.filter((e) => now - e.ts < 72 * 3600e3).length;
      return { id: "f" + hash(p.id), front: true, fkind: p.front_kind, title: p.title || k[0], kind: k[0], label: k[0], glyph: k[1], tone: "red", c: COL.red, region: p.theatre,
        place: p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name, cs, ll: midPoint(cs), km, n24, n72, last: near[0] || null,
        bbox: [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], summary: k[2],
        facts: [["Length", "about " + nf(Math.round(km)) + " km"], ["Pins within 75 km", `${n24} in the last 24 hours, ${n72} in 72 hours`]].concat(near[0] ? [["Newest nearby", `${near[0].title} (${ago(near[0].ts)})`]] : []),
        note: "Drawn by the source map's curator. It moves only when they redraw it; it is not a live trace of the front." };
    }).sort((a, b) => b.n72 - a.n72 || b.km - a.km);
    S.fronts.forEach((f) => S.byId.set(f.id, f));
  }

  // ---------- what the feed shows ----------
  function feed(opts) {
    const o = opts || {}, now = Date.now(), topic = o.topic || S.topic, q = (o.q != null ? o.q : "").trim().toLowerCase();
    return S.entries.filter((e) => (topic === "all" ? (o.allGroups || S.groups.has(e.group)) : e.topics.includes(topic)) &&
      (o.noFilter || ((S.region === "all" || e.region === S.region) && (!S.hours || now - e.ts <= S.hours * 3600e3))) &&
      (!q || (e.title + " " + (e.place || "") + " " + (e.src || "") + " " + e.kind).toLowerCase().includes(q)));
  }
  const setZone = (z) => { ZONE = S.zone = z === "utc" ? "utc" : "et"; LS.set("tz", ZONE); emit("zone"); };

  Object.assign(A, { $, esc, nf, LS, REDUCED, S, on, emit, ico, GLYPHS, COL, CATS, REGIONS, regionName, TOPICS, GROUPS, DEFAULT_GROUPS, FRONT_KIND, TOPIC_NEEDS, PIN_SRC, has, hasAny, topicOn, groupOn,
    fmtT, fmtDate, dayKey, dayLabel, ago, when, whenShort, zText, zoneAbbr, isoMs, setZone, load, need, start, feed, centre, safeUrl, hash, ccName });
})();
