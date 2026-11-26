/* Ground Truth 1.7.0, "Watch Floor" theme: shared helpers, state and data loading.
   Read-only: every call is a GET to a relative api/ URL. Nothing here writes to the server. */
(() => {
  "use strict";
  const WF = (window.WF = {});
  const $ = (WF.$ = (id) => document.getElementById(id));
  const esc = (WF.esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  WF.url = (u) => (/^https?:\/\//i.test(String(u || "")) ? String(u) : "");  // only web links are ever put in an href
  WF.nf = (n) => (n == null || n === "" || !Number.isFinite(+n) ? "–" : Number(n).toLocaleString("en-US"));

  // Theatres: name, map centre and zoom (the same list as today's page).
  WF.THEATRES = {
    "global": ["All theatres", [20, 30, 1.7]],
    "middle-east": ["Middle East / Gulf", [50.5, 27.5, 4.2]],
    "ukraine-russia": ["Ukraine – Russia", [36.5, 49.2, 4.7]],
    "europe-nato": ["Europe / NATO", [15, 54, 3.5]],
    "americas": ["Americas / US", [-85, 33, 2.9]],
    "indo-pacific": ["Indo-Pacific", [125, 27, 3.4]],
    "south-asia": ["South & Central Asia", [70, 30, 3.6]],
    "africa": ["Africa", [20, 8, 2.7]],
  };
  WF.tname = (k) => (WF.THEATRES[k] || [""])[0];
  // Event types in plain words, and the severity mark each one gets: 2 = kinetic (red), 1 = disruptive (amber), 0 = other.
  WF.CATS = {
    strike: ["Strike / explosion", 2], missile: ["Missile / air defence", 2], casualty: ["Casualties", 2],
    drone: ["Drone", 1], energy: ["Energy / infrastructure", 1], maritime: ["Maritime", 1], alert: ["Alert / force posture", 1],
    cyber: ["Comms / outage", 1], security: ["Security incident", 1],
    forces: ["Forces / equipment", 0], aviation: ["Aviation", 0], political: ["Political / statement", 0], report: ["Report", 0], other: ["Other", 0],
  };
  WF.SEV = ["grey", "amber", "red"];
  WF.SEVHEX = ["#9aa7b4", "#f5b23c", "#ff5d55"];

  // ---------- time: one zone for every time on the page (Eastern by default, UTC on request) ----------
  const ET = "America/New_York";
  let ZONE = (() => { try { return localStorage.getItem("gt-tz") === "utc" ? "utc" : "et"; } catch (e) { return "et"; } })();
  const DTF = {};
  const zparts = (ms, tz) => {
    const f = DTF[tz] || (DTF[tz] = new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric", month: "short", day: "numeric", weekday: "short",
      hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true, timeZoneName: "short" }));
    const o = {}; f.formatToParts(new Date(ms)).forEach((p) => { o[p.type] = p.value; }); return o;
  };
  WF.zone = () => ZONE;
  WF.setZone = (z) => { ZONE = z === "utc" ? "utc" : "et"; try { localStorage.setItem("gt-tz", ZONE); } catch (e) { /* private window */ } };
  WF.zoneAbbr = () => (ZONE === "utc" ? "UTC" : zparts(Date.now(), ET).timeZoneName);
  WF.fmtT = (ms, secs) => {
    if (ZONE === "utc") return new Date(ms).toISOString().slice(11, secs ? 19 : 16) + (secs ? "" : "Z");
    const p = zparts(ms, ET); return `${p.hour}:${p.minute}${secs ? ":" + p.second : ""} ${p.dayPeriod}`;
  };
  // 1.7.1: the analyst writes times in UTC ("05:38Z"). In Eastern mode each gets its Eastern time beside it (as Classic does).
  WF.zText = (s, ref) => (ZONE === "utc" || !s ? s || "" : String(s).replace(/(^|[^\d:])([01]\d|2[0-3]):([0-5]\d)Z\b/g, (m, pre, h, mi) => {
    const d = new Date(Number.isFinite(ref) ? ref : Date.now());
    return `${pre}${h}:${mi}Z (${WF.fmtT(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), +h, +mi))})`; }));
  WF.fmtDay = (ms) => { const p = zparts(ms, ZONE === "utc" ? "UTC" : ET); return `${p.weekday} ${p.day} ${p.month}`; };
  WF.dayKey = (ms) => { const p = zparts(ms, ZONE === "utc" ? "UTC" : ET); return p.year + p.month + p.day; };
  WF.ms = (v) => (typeof v === "number" ? v : v ? Date.parse(v) : NaN);
  WF.ago = (ms) => {
    if (!Number.isFinite(ms)) return "–";
    const d = Date.now() - ms, m = Math.round(Math.abs(d) / 60000);
    if (m < 1) return "just now";
    const s = m < 60 ? m + " min" : m < 2880 ? Math.floor(m / 60) + " h" + (m < 600 && m % 60 ? " " + (m % 60) + " min" : "") : Math.round(m / 1440) + " days";
    return d < 0 ? "in " + s : s + " ago";
  };
  WF.agoShort = (ms) => { if (!Number.isFinite(ms)) return "–"; const m = Math.round(Math.abs(Date.now() - ms) / 60000); return m < 1 ? "now" : m < 60 ? m + "m" : m < 2880 ? Math.round(m / 60) + "h" : Math.round(m / 1440) + "d"; };
  WF.when = (ms) => (Number.isFinite(ms) ? `${WF.fmtDay(ms)}, ${WF.fmtT(ms)} ${WF.zoneAbbr()} (${WF.ago(ms)})` : "–");
  // A pin dated by day only (ts_source "date") names a UTC day and has no clock time worth showing (the rule in
  // today's web/app.js dayStart / dayAt). dayStart is the moment that day begins in the page's zone, dayAt is where
  // such a pin sits in the log (never later than now), dayText is the day it names.
  const OFF = new Intl.DateTimeFormat("en-US", { timeZone: ET, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const etOff = (ms) => { const o = {}; OFF.formatToParts(new Date(ms)).forEach((p) => { o[p.type] = +p.value; });
    return Math.round((ms - Date.UTC(o.year, o.month - 1, o.day, o.hour % 24, o.minute, o.second)) / 60000) * 60000; };
  const DAY0 = new Map();  // UTC day -> the moment it begins in Eastern time
  WF.dayStart = (ts) => { const d0 = Math.floor(ts / 86400000) * 86400000; if (ZONE === "utc") return d0;
    if (!DAY0.has(d0)) DAY0.set(d0, d0 + etOff(d0 + etOff(d0 + 43200000))); return DAY0.get(d0); };
  WF.dayAt = (ts) => Math.min(WF.dayStart(ts), Date.now());
  WF.dayText = (ts) => WF.fmtDay(WF.dayStart(ts) + 43200000);
  WF.dayOnly = (p) => p.ts_source === "date";
  WF.pinT = (p) => (WF.dayOnly(p) && p.ts_ms ? WF.dayAt(p.ts_ms) : p.ts_ms);  // where a pin sits in time on this page

  // ---------- state ----------
  const qs = new URLSearchParams(location.search);
  WF.S = { board: "conflict", view: "conflict", theatre: "global", pane: "board", wide: "", src: "all", wall: qs.has("wall"), shown: 120 };
  WF.D = {};        // loaded data by name
  WF.ERR = {};      // name -> message, for an honest "could not load" line
  WF.LOADING = new Set();

  // "Since you last looked": the time this browser last had the page open, kept in this browser only.
  WF.lastSeen = (() => { try { const v = +localStorage.getItem("gt-c3-seen"); return v > 0 ? v : 0; } catch (e) { return 0; } })();
  const markSeen = () => { try { localStorage.setItem("gt-c3-seen", String(Date.now())); } catch (e) { /* private window */ } };
  if (!WF.S.wall) { window.addEventListener("pagehide", markSeen); document.addEventListener("visibilitychange", () => { if (document.hidden) markSeen(); }); }

  // ---------- data ----------
  const api = (WF.api = (p) => fetch("api/" + p, { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))));
  let raf = 0;
  WF.renderSoon = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (WF.render) WF.render(); }); };
  // name -> [path, pick]: pick takes the reply to the part the page uses
  const feedOf = (n) => ["feed/" + n, (r) => r.data || {}];
  const SRC = {
    events: ["events", (r) => r], summary: ["summary", (r) => r], status: ["status", (r) => r], alerts: ["alerts", (r) => r],
    analysis: ["analysis", (r) => r.picture || null],
    czib_geo: ["czib_geo", (r) => r], outages_geo: ["outages_geo", (r) => r], advisories_geo: ["advisories_geo", (r) => r],
  };
  ["wire", "telegram", "front", "mil", "tfr", "gpsjam", "ships", "ukmto", "portwatch", "power", "cloud", "cellular", "websites", "cyber",
    "quakes", "hazards", "official"].forEach((n) => { SRC[n] = feedOf(n); });

  // ---------- pins: one rule, the same as the Classic theme (web/app.js mergeEvents, web/ext/curated.js) ----------
  // Three more pin sources join the source map's pins. The source map wins: an extra pin is dropped when the map
  // already has its id or the same post. WF.D.events is always the merged set, so the map, the log, the theatre
  // counts and the front counts all read the same pins.
  // name -> [label, note shown with the pin]
  WF.PIN_SRC = {
    geoconfirmed: ["GeoConfirmed", "Geolocated by GeoConfirmed volunteers; the geolocation usually lands days after the event."],
    cir: ["CIR Eyes on Russia", "CIR publishes about a week after the event, on purpose."],
    kinetic: ["S2 Underground", "Licensed CC BY-NC-SA 4.0; Ground Truth changed the layout and categories."],
  };
  const EXTRA = Object.keys(WF.PIN_SRC);
  EXTRA.forEach((n) => { SRC[n] = feedOf(n); });
  WF.pinSrc = (p) => (p.source && p.source !== "map" ? p.source_label || (WF.PIN_SRC[p.source] || [p.source])[0] : "Source map");
  const credit = (a) => (Array.isArray(a) ? a : a ? [{ text: String(a) }] : []).map((x) => (typeof x === "string" ? x : x.text)).filter(Boolean).join("; ");
  let BASE = null;       // the source map's reply, as loaded
  const EXTRAS = {};     // name -> event features of one extra source
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
    if (!BASE) return;
    const feats = BASE.features || [], seen = new Set(feats.map((f) => f.properties.id)), extra = [];
    const posts = new Set(feats.map((f) => postKey(f.properties.url)).filter(Boolean));
    EXTRA.forEach((n) => (EXTRAS[n] || []).forEach((f) => {
      const p = f.properties;
      if (seen.has(p.id) || posts.has(postKey(p.url))) return;
      seen.add(p.id); extra.push(f);
    }));
    WF.D.events = extra.length ? { ...BASE, features: feats.concat(extra) } : BASE;
    const now = Date.now();  // no pin dated after now (day-only pins keep the day they name)
    (WF.D.events.features || []).forEach((f) => { const p = f.properties; if (p && p.ts_source !== "date" && Number.isFinite(p.ts_ms) && p.ts_ms > now) { p.ts_ahead = p.ts_ms; p.ts_ms = now; } });
  }
  function take(name, v) {
    if (name === "events") { BASE = v; mergeEvents(); return; }
    WF.D[name] = v;
    if (EXTRA.includes(name)) {
      const att = credit(v.attribution);
      EXTRAS[name] = ((v.geojson || {}).features || []).filter((f) => f.properties && f.properties.kind === "event");
      EXTRAS[name].forEach((f) => { const p = f.properties; p.attribution = p.attribution || att; p.source_note = WF.PIN_SRC[name][1]; });
      mergeEvents();
    }
    // The extra pin sources ride on the status reply (WF.load asks only for the ones it lists; see below).
    if (name === "status") { listed = v && v.feeds && typeof v.feeds === "object" ? new Set(Object.keys(v.feeds)) : listed; EXTRA.forEach((n) => WF.load(n)); }
  }
  // ---------- which feeds this copy carries (1.7.1; the Classic theme's rule, web/app.js loadExt) ----------
  // api/status lists the feeds a copy runs. The public mirror carries fewer than the server (no news wire, Telegram,
  // power, mobile, web, cloud, cyber, GPS interference, GeoConfirmed or CIR), so a feed is asked for only when the
  // status lists it, and nothing that depends on the status is asked for before the status has answered. The five
  // core replies are always asked for. An endpoint that goes with a feed follows that feed. If the status itself
  // cannot be read, every feed is asked for, as before.
  const ALWAYS = new Set(["events", "summary", "analysis", "alerts", "status"]);
  const WITH = { czib_geo: "czib", outages_geo: "outages", advisories_geo: "advisories" };
  let listed = null;        // the feed names the status lists; null until a status reply is in
  let statusDone = false;   // the first status request has settled (a reply or a failure)
  const HELD = new Set();   // asked for before the status answered
  // true when this copy does not carry `name` (a data name such as "wire" or "czib_geo", or a status feed name such as "pla")
  WF.absent = (name) => { const k = ALWAYS.has(name) ? null : WITH[name] || name; return !!(k && listed && !listed.has(k)); };
  WF.held = () => HELD.size;
  WF.NOC = "Not on this copy.";
  WF.load = (name) => {
    if (!SRC[name] || WF.LOADING.has(name)) return Promise.resolve();
    if (!ALWAYS.has(name)) {
      if (!statusDone) { HELD.add(name); return Promise.resolve(); }  // wait for the status
      if (WF.absent(name)) return Promise.resolve();                   // not on this copy: never asked for
      if (EXTRA.includes(name) && !listed) return Promise.resolve();   // an extra pin source needs the status to name it
    }
    WF.LOADING.add(name);
    const [path, pick] = SRC[name];
    return api(path).then((r) => { take(name, pick(r)); delete WF.ERR[name]; }, (e) => { WF.ERR[name] = e.message || "failed"; })
      .then(() => { WF.LOADING.delete(name);
        if (name === "status" && !statusDone) { statusDone = true; const held = [...HELD]; HELD.clear(); held.forEach((n) => WF.load(n)); }
        if (WF.onData) WF.onData(EXTRA.includes(name) ? "events" : name); WF.renderSoon(); });
  };
  // Pin counts from the merged pins, by the server summary's own rule (a pin with a time, no older than the window).
  let statsOf = null, statsAt = 0, stats = null;
  WF.pinStats = () => {
    const d = WF.D.events, now = Date.now();
    if (!d) return null;
    if (statsOf === d && now - statsAt < 20000) return stats;
    const by = {}; let n24 = 0, n6 = 0, newest = 0;
    (d.features || []).forEach((f) => { const p = f.properties; if (p.kind !== "event" || !p.ts_ms) return;
      const age = now - p.ts_ms; if (!WF.dayOnly(p) && p.ts_ms > newest) newest = p.ts_ms;  // a day-only pin has no clock time to count from
      if (age <= 24 * 3600e3) { n24++; by[p.theatre] = (by[p.theatre] || 0) + 1; }
      if (age <= 6 * 3600e3) n6++; });
    statsOf = d; statsAt = now; stats = { by, n24, n6, newest };
    return stats;
  };
  WF.need = (names) => names.forEach((n) => { if (!(n in WF.D) && !WF.LOADING.has(n)) WF.load(n); });
  // a panel body for data that is not here yet, failed, or is not carried by this copy (that one never loads)
  WF.wait = (names) => {
    if (names.some((n) => WF.absent(n) && !(n in WF.D))) return `<p class="note">${WF.NOC}</p>`;
    const bad = names.filter((n) => WF.ERR[n] && !(n in WF.D));
    if (bad.length) return `<p class="note">Could not load this (${esc(WF.ERR[bad[0]])}). It is tried again every two minutes.</p>`;
    return names.some((n) => !(n in WF.D)) ? `<p class="note">Loading…</p>` : "";
  };

  // ---------- pin glyphs (the drawings from today's page, web/app.js GLYPHS, in a 24-unit box) ----------
  const GLYPHS = (WF.GLYPHS = {
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
  });
  const ICON_GLYPH = { 1830: "megaphone", 1571: "fire", 1504: "plane", 1657: "officer", 1722: "truck", 1812: "gunner", 1569: "ship",
    1864: "wreck", 1556: "skull", 1528: "bridge", 1593: "helicopter", 1716: "train", 1660: "bolt" };
  const CAT_GLYPH = { strike: "fire", energy: "bolt", maritime: "ship", casualty: "skull", aviation: "plane", drone: "plane", forces: "officer" };
  // pins from the other pin sources have no map icon: the clear categories borrow one, the rest stay a plain dot
  WF.glyphOf = (p) => (p.source && p.source !== "map" ? "" : ICON_GLYPH[p.icon] || (GLYPHS[p.glyph] ? p.glyph : "")) || CAT_GLYPH[p.category] || "";
  // A glyph on a canvas: ink colour, optional disc behind it ({fill, ring}); the glyph fills `scale` of the box.
  WF.drawGlyph = (name, px, ink, disc, scale) => {
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
  };

  // ---------- battle fronts (the Classic theme's rule, web/ext/fronts.js build()): lines the source map's curator
  // draws; every pin with a time within 75 km of the line is counted, over the last 24 h and 72 h ----------
  const RAD = Math.PI / 180, NEAR_KM = (WF.NEAR_KM = 75);
  // The same rule as gt/mymaps.py front_kind, for data from a server older than 1.6.0.
  const frontKind = (p, n) => {
    if (p.front_kind) return p.front_kind;
    const col = String(p.stroke || "").toUpperCase(), t = String(p.title || "").toLowerCase();
    if ((col !== "#A52714" && col !== "#FFD600") || ["damage", "bridge", "river", "border", "lane", "airbase"].includes(p.overlay_type)) return null;
    if (col === "#FFD600") return "supposed";
    if (/blockade/.test(t)) return "blockade";
    if (/defen[cs]e (chain|line)|perimeter/.test(t)) return "defense";
    return /front/.test(t) || n >= 3 ? "contact" : null;
  };
  WF.frontKind = (f) => (f.properties.kind === "overlay" && f.geometry && f.geometry.type === "LineString" ? frontKind(f.properties, f.geometry.coordinates.length) : null);
  function segKm(p, a, b) {
    const k = Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32;
    const ax = (a[0] - p[0]) * k, ay = (a[1] - p[1]) * 110.57, bx = (b[0] - p[0]) * k, by = (b[1] - p[1]) * 110.57;
    const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L)) : 0;
    return Math.hypot(ax + t * dx, ay + t * dy);
  }
  const lineKm = (pt, cs) => { let d = Infinity; for (let i = 1; i < cs.length; i++) d = Math.min(d, segKm(pt, cs[i - 1], cs[i])); return d; };
  const ptKm = (a, b) => Math.hypot((b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * RAD) * 111.32, (b[1] - a[1]) * 110.57);
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
  WF.FRONT_KIND = {
    contact: ["Front line", "", "swords", "Line of contact between the two sides, as the source map draws it."],
    supposed: ["Supposed front line", "dash", "swords", "A front line the source map marks as unconfirmed."],
    blockade: ["Blockade line", "dash", "anchor", "A naval blockade line on the source map."],
    defense: ["Defence line", "dot", "shield", "A defensive line or perimeter on the source map."],
  };
  WF.buildFronts = () => {
    const feats = (WF.D.events || {}).features || [], now = Date.now();
    const pins = feats.filter((f) => f.properties.kind === "event" && f.geometry && f.geometry.type === "Point" && f.properties.ts_ms);
    return feats.filter((f) => WF.FRONT_KIND[WF.frontKind(f)]).map((f) => {
      const p = f.properties, cs = f.geometry.coordinates, kind = WF.frontKind(f);
      const near = pins.filter((e) => lineKm(e.geometry.coordinates, cs) <= NEAR_KM).sort((a, b) => b.properties.ts_ms - a.properties.ts_ms);
      const xs = cs.map((c) => c[0]), ys = cs.map((c) => c[1]); let km = 0;
      for (let i = 1; i < cs.length; i++) km += ptKm(cs[i - 1], cs[i]);
      return { id: p.id, kind, name: p.title || WF.FRONT_KIND[kind][0], theatre: p.theatre,
        where: p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name, cs, mid: midPoint(cs), km,
        bbox: [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]],
        n24: near.filter((e) => now - e.properties.ts_ms < 24 * 3600e3).length, n72: near.filter((e) => now - e.properties.ts_ms < 72 * 3600e3).length,
        last: near[0] ? near[0].properties : null };
    }).sort((a, b) => b.n72 - a.n72 || b.km - a.km);
  };
})();
