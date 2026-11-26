/* Ground Truth 1.7.0, theme "Dispatch": data, routing, the lead and the feed.
   Read-only: GET requests to relative api/ URLs only. Nothing here writes to the server.
   The page is web/dispatch.html; this folder holds only the theme's own CSS and JS. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nf = (n) => (n == null || isNaN(n) ? "–" : Number(n).toLocaleString("en-US"));
  const httpUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);

  // Theatres in plain words: key -> [name, [lon, lat, zoom]]
  const THEATRES = {
    "ukraine-russia": ["Ukraine and Russia", [36.5, 49.2, 4.6]],
    "middle-east": ["Middle East and Gulf", [50.5, 27.5, 4.1]],
    "europe-nato": ["Europe and NATO", [15, 54, 3.4]],
    "americas": ["Americas", [-85, 33, 2.8]],
    "indo-pacific": ["Indo-Pacific", [125, 27, 3.3]],
    "south-asia": ["South and Central Asia", [70, 30, 3.6]],
    "africa": ["Africa", [20, 8, 2.7]],
  };
  // Colour is saved for meaning: five families, not fourteen category colours.
  const FAMILY = {
    violent: ["Attacks", "#b3261e"], military: ["Forces and alerts", "#37474f"], sea: ["At sea", "#1f5f8b"],
    infra: ["Power and networks", "#8a5a00"], words: ["Statements and reports", "#6b7078"],
  };
  const CATS = {
    strike: ["Strike or explosion", "violent"], missile: ["Missile or air defence", "violent"], drone: ["Drone", "violent"],
    casualty: ["Casualties", "violent"], alert: ["Alert or force posture", "military"], forces: ["Forces and equipment", "military"],
    security: ["Security incident", "military"], aviation: ["Aviation", "military"], maritime: ["At sea", "sea"],
    energy: ["Energy and infrastructure", "infra"], cyber: ["Communications or outage", "infra"],
    political: ["Political statement", "words"], report: ["Report", "words"], other: ["Other news", "words"],
  };
  const cat = (k) => CATS[k] || CATS.other;
  const fam = (k) => cat(k)[1];
  const thName = (k) => (THEATRES[k] ? THEATRES[k][0] : "");

  const store = {
    get(k) { try { return localStorage.getItem("gt.dispatch." + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem("gt.dispatch." + k, v); } catch (e) { /* private mode: the page still works */ } },
  };

  const S = { tz: store.get("tz") === "utc" ? "utc" : "et", events: null, eventsBase: null, summary: null, status: null, analysis: null, alerts: null,
    feeds: {}, entries: [], filter: { theatre: "all", src: "all", kind: "all" }, shown: 60, loadedAt: 0, failed: {},
    lastSeen: Number(store.get("seen")) || 0, route: { view: "home", name: "home", q: {} } };

  // ---------- time ----------
  const zone = () => (S.tz === "utc" ? "UTC" : "America/New_York");
  const zlabel = () => (S.tz === "utc" ? "UTC" : "Eastern");
  // 1.7.1: Eastern times read am/pm ("9:05 PM"); UTC, when chosen, stays on the 24-hour clock.
  const fmtTime = (ms) => (S.tz === "utc" ? new Date(ms).toLocaleTimeString("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit" })
    : new Date(ms).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }));
  // The analyst writes times in UTC ("05:38Z"). In Eastern mode each gets its Eastern time beside it (as Classic does).
  const zText = (s, ref) => (S.tz === "utc" || !s ? s || "" : String(s).replace(/(^|[^\d:])([01]\d|2[0-3]):([0-5]\d)Z\b(?! \()/g, (m, pre, h, mi) => {
    const d = new Date(Number.isFinite(ref) ? ref : Date.now());
    return `${pre}${h}:${mi}Z (${fmtTime(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), +h, +mi))})`; }));
  const fmtDay = (ms) => new Date(ms).toLocaleDateString("en-GB", { timeZone: zone(), weekday: "long", day: "numeric", month: "long" });
  const fmtDate = (d) => (/^\d{4}-\d{2}-\d{2}$/.test(d || "") ? new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" }) : String(d || ""));  // a date with no time
  const plural = (n, one, many) => `${nf(n)} ${Number(n) === 1 ? one : many || one + "s"}`;
  const fmtShort = (ms) => new Date(ms).toLocaleDateString("en-GB", { timeZone: zone(), day: "numeric", month: "short" });
  const dayKey = (ms) => new Date(ms).toLocaleDateString("en-CA", { timeZone: zone() });
  const when = (ms) => (dayKey(ms) === dayKey(Date.now()) ? fmtTime(ms) : fmtShort(ms) + ", " + fmtTime(ms));
  // A date-only pin (ts_source "date") names a UTC day and has no clock time. It is shown as a date and sits at the start
  // of that day in the page's zone (dayStart in web/app.js). Where the Classic theme caps that at now, this page caps it
  // an hour back, so a pin with no clock time never sits under "In the last hour". The two "Latest" lists leave these
  // pins out, as the Classic theme's ticker does; the Feed and the map have them.
  function dayStart(ts) {
    const d0 = Math.floor(ts / 864e5) * 864e5;
    if (S.tz === "utc") return d0;
    for (const h of [5, 4]) if (new Date(d0 + h * 36e5).toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) === "00:00") return d0 + h * 36e5;
    return d0 + 5 * 36e5;
  }
  const dayAt = (ts) => Math.min(dayStart(ts), Date.now() - 3600001);
  const dayOnly = (ts) => fmtDate(new Date(ts).toISOString().slice(0, 10));
  const isoMs = (s) => (s ? Date.parse(/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? s.replace(" ", "T") + "Z" : s) : null);
  function ago(ms) {
    const m = Math.max(0, Math.round((Date.now() - ms) / 60000));
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    if (m < 48 * 60) return Math.round(m / 60) + " h ago";
    return Math.round(m / 1440) + " days ago";
  }

  // ---------- data ----------
  const api = (p) => fetch("api/" + p, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(p + " " + r.status))));
  const listeners = {};
  const on = (ev, fn) => (listeners[ev] = listeners[ev] || []).push(fn);
  const emit = (ev, a) => (listeners[ev] || []).forEach((fn) => { try { fn(a); } catch (e) { console.error(e); } });

  // ---------- which feeds this copy carries (1.7.1) ----------
  // api/status lists the feeds a copy carries; the public mirror has fewer than the server. Once status has answered,
  // a feed it does not list is never asked for, and its place on the page says "Not on this copy." (the Classic
  // theme's rule: loadExt in web/app.js). Nothing that depends on the list is asked for before status has answered.
  // If status itself fails, every feed is asked for as before. The core endpoints are always asked for.
  const CORE_KEYS = ["events", "summary", "analysis", "alerts", "status"], NOT_HERE = "Not on this copy.";
  let statusDone; const statusKnown = new Promise((res) => { statusDone = res; });
  const absent = (name) => { const known = (S.status || {}).feeds; return !!known && !CORE_KEYS.includes(name) && !(name in known); };

  // Feeds a section or a map topic needs, fetched on first use and kept for three minutes.
  const feedAt = {}, feedWait = {};
  const need = (name) => statusKnown.then(() => (absent(name) ? Promise.reject(new Error(name + " is not on this copy")) : fetchFeed(name)));
  function fetchFeed(name) {
    if (S.feeds[name] && Date.now() - feedAt[name] < 180000) return Promise.resolve(S.feeds[name]);
    if (feedWait[name]) return feedWait[name];
    feedWait[name] = api("feed/" + name).then((j) => { S.feeds[name] = j.data || {}; S.feeds[name]._ok = j.ok; S.feeds[name]._at = j.at; feedAt[name] = Date.now(); delete feedWait[name]; delete S.failed[name]; return S.feeds[name]; },
      (e) => { delete feedWait[name]; S.failed[name] = true; if (S.feeds[name]) return S.feeds[name]; throw e; });
    return feedWait[name];
  }

  // ---------- one rule for pins, the same as the Classic theme (web/app.js mergeEvents and postKey, web/ext/curated.js) ----------
  // Three more pin sources join the source map's pins. The source map wins: an extra pin is dropped when the map already
  // has its id or the same post. A source the server does not run (the public mirror has none of them) is not asked for.
  // key -> [name, note shown with a pin, credit as web/ext/curated.js words it]
  const PINSRC = {
    geoconfirmed: ["GeoConfirmed", "Geolocated by GeoConfirmed volunteers; the geolocation usually lands days after the event.", "GeoConfirmed verified geolocations (14 days)"],
    cir: ["CIR Eyes on Russia", "CIR publishes about a week after the event, on purpose.", "CIR Eyes on Russia: civilian harm, infrastructure (~1 week lag)"],
    kinetic: ["S2 Underground", "Licensed CC BY-NC-SA 4.0; Ground Truth changed the layout and categories.", "S2 Underground Iran kinetic events (CC BY-NC-SA 4.0)"],
  };
  const extraPins = {};
  const creditText = (a) => (Array.isArray(a) ? a : a ? [{ text: String(a) }] : []).map((x) => (typeof x === "string" ? x : x.text)).filter(Boolean).join("; ");
  const pinSource = (p) => (p.source && p.source !== "map" ? p.source_label || (PINSRC[p.source] || [p.source])[0] : "");   // "" means the source map
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
    const base = S.eventsBase.features || [], seen = new Set(base.map((f) => f.properties.id)), add = [];
    const posts = new Set(base.map((f) => postKey(f.properties.url)).filter(Boolean));
    Object.keys(PINSRC).forEach((name) => (extraPins[name] || []).forEach((f) => {
      const p = f.properties;
      if (seen.has(p.id) || posts.has(postKey(p.url))) return;
      seen.add(p.id); add.push(f);
    }));
    S.events = add.length ? { ...S.eventsBase, features: base.concat(add) } : S.eventsBase;
    const now = Date.now();   // no pin dated after now (pinNotAhead in web/app.js)
    S.events.features.forEach((f) => { const p = f.properties; if (p && p.ts_source !== "date" && Number.isFinite(p.ts_ms) && p.ts_ms > now) { p.ts_ahead = p.ts_ms; p.ts_ms = now; } });
  }
  function loadExtraPins() {
    const known = (S.status || {}).feeds;
    const names = known ? Object.keys(PINSRC).filter((n) => n in known) : [];
    if (!names.length) return Promise.resolve(false);
    return Promise.all(names.map((name) => api("feed/" + name).then((r) => {
      const d = r && r.data; if (!d) return;
      const att = creditText(d.attribution);
      extraPins[name] = ((d.geojson || {}).features || []).filter((f) => f && f.properties && f.properties.kind === "event");
      extraPins[name].forEach((f) => { const p = f.properties; p.attribution = p.attribution || att; p.source_note = PINSRC[name][1]; });
    }).catch(() => { /* a missing or failing extra source leaves the page as it was */ }))).then(() => true);
  }
  // How many event pins the map holds, and from where ("map" is the source map).
  function pinStats() {
    const now = Date.now(), out = { total: 0, h24: 0, by: {} };
    ((S.events || {}).features || []).forEach((f) => {
      const p = f.properties; if (p.kind !== "event") return;
      const k = p.source || "map"; out.total++; out.by[k] = (out.by[k] || 0) + 1;
      if (p.ts_ms && now - p.ts_ms < 864e5) out.h24++;
    });
    return out;
  }

  function buildEntries() {
    const out = [];
    ((S.events || {}).features || []).forEach((f) => {
      const p = f.properties;
      if (p.kind !== "event" || !p.ts_ms) return;
      const day = p.ts_source === "date";
      out.push({ id: "p" + p.id, pid: p.id, ts: day ? dayAt(p.ts_ms) : p.ts_ms, day: day ? p.ts_ms : 0, title: p.title, url: httpUrl(p.url), src: "pin", srcLabel: p.handle ? (/^r\//.test(p.handle) ? "" : "@") + p.handle : pinSource(p) ? "" : "Source map", from: pinSource(p),
        place: p.sea && !["offshore", "open ocean"].includes(p.sea) ? p.sea : p.country_name, theatre: p.theatre, cat: p.category, ll: f.geometry && f.geometry.coordinates });
    });
    [["wire", "w"], ["telegram", "t"]].forEach(([name, k]) => ((S.feeds[name] || {}).items || []).forEach((i) => {
      if (!i.ts_ms || !i.title) return;
      out.push({ id: k + i.id, ts: i.ts_ms, title: i.title, url: httpUrl(i.url), src: name, srcLabel: i.source_label || (name === "wire" ? "News wire" : "Telegram"),
        theatre: i.theatre && THEATRES[i.theatre] ? i.theatre : "", cat: i.category, summary: name === "wire" ? i.summary : "" });
    }));
    out.sort((a, b) => b.ts - a.ts);
    S.entries = out;
  }

  const CORE = [["events", "events"], ["summary", "summary"], ["analysis", "analysis"], ["alerts", "alerts"], ["status", "status"]];
  function loadCore() {
    const jobs = CORE.map(([key, path]) => api(path).then((j) => { S[key === "events" ? "eventsBase" : key] = j; delete S.failed[key]; }, () => { S.failed[key] = true; }));
    // status first: the wire and Telegram are asked for only once this copy is known to carry them
    const status = jobs[CORE.findIndex(([key]) => key === "status")].then(statusDone);
    jobs.push(status.then(() => Promise.all([need("wire").catch(() => {}), need("telegram").catch(() => {})])));
    const show = () => { mergeEvents(); buildEntries(); emit("data"); render(); };
    // The page is drawn from the source map first; the other pin sources join it when they arrive.
    return Promise.all(jobs).then(() => { S.loadedAt = Date.now(); show(); return loadExtraPins(); }).then((got) => { if (got) show(); });
  }

  // ---------- routing ----------
  const NAV = [["home", "Front page"], ["map", "Map"], ["feed", "Feed"], ["conflict", "Conflict"], ["air", "Air"], ["sea", "Sea"],
    ["outages", "Outages and cyber"], ["hazards", "Hazards"], ["official", "Official"], ["analysis", "Analysis"], ["sources", "Sources"], ["wall", "Wall view"]];
  const SECTIONS = ["conflict", "air", "sea", "outages", "hazards", "official", "analysis", "sources"];
  function parseHash() {
    const h = location.hash.replace(/^#\/?/, ""), [name, qs] = h.split("?"), q = {};
    (qs || "").split("&").forEach((kv) => { const [k, v] = kv.split("="); if (k) q[k] = decodeURIComponent(v || ""); });
    let n = name || "";
    if (!n) n = "home";   // the wall view never starts by itself: it opens from #/wall or the "Wall view" link
    if (!NAV.some(([k]) => k === n)) n = "home";
    return { name: n, view: SECTIONS.includes(n) ? "section" : n, q };
  }
  function route() {
    S.route = parseHash();
    const r = S.route;
    document.querySelectorAll(".view").forEach((v) => { v.hidden = v.dataset.view !== r.view; });
    document.body.dataset.view = r.view; document.body.dataset.name = r.name;
    document.querySelectorAll("[data-nav]").forEach((a) => (a.dataset.nav === r.name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    document.querySelectorAll("#tabbar [data-tab]").forEach((a) => (a.dataset.tab === r.name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    closeSheet();
    window.scrollTo(0, 0);
    emit("route", r);
    render();
  }
  function navHtml() {
    const link = ([k, n]) => `<a href="#/${k === "home" ? "" : k}" data-nav="${k}"${k === "wall" ? ' class="aside"' : ""}>${n}</a>`;
    $("nav").innerHTML = NAV.map(link).join("");
    $("sheetlist").innerHTML = NAV.map(([k, n]) => `<a href="#/${k === "home" ? "" : k}" data-nav="${k}">${n}</a>`).join("");
  }
  function closeSheet() { $("sheet").hidden = true; $("tabsections").setAttribute("aria-expanded", "false"); }

  // ---------- pieces of text ----------
  // The first n sentences of a paragraph (the brief's "bottom line in two or three sentences").
  function sentences(text, n) {
    const parts = String(text || "").split(/(?<=[.!?])\s+(?=[A-Z0-9“"])/), out = [];
    for (const p of parts) {
      if (out.length && /(\b[A-Z]\.|\b(?:Gen|Col|Lt|Mr|Ms|Dr|St|No|vs)\.)$/.test(out[out.length - 1])) out[out.length - 1] += " " + p; else out.push(p);
    }
    return { head: out.slice(0, n).join(" "), rest: out.slice(n).join(" ") };
  }
  const level = (n) => (n >= 8 ? "high" : n >= 5 ? "mid" : "low");
  const levelWord = (n) => (n >= 8 ? "Severe" : n >= 6 ? "High" : n >= 4 ? "Elevated" : "Low");
  function tensionHtml(pic) {
    if (!pic || pic.overall_tension == null) return `<p class="none">The tension figure is not available.</p>`;
    const n = Number(pic.overall_tension), cells = Array.from({ length: 10 }, (_, i) => `<i class="${i < n ? "on" : ""}"></i>`).join("");
    return `<div class="t-fig lv-${level(n)}"><span class="t-num">${esc(n)}</span><span class="t-of">of 10</span></div>
      <div class="t-txt"><b>Tension: ${levelWord(n).toLowerCase()}${pic.trend ? ", " + esc(pic.trend) : ""}</b><span class="t-scale lv-${level(n)}" role="img" aria-label="${esc(n)} out of 10">${cells}</span><span class="t-note">The analyst’s reading of all theatres together</span></div>`;
  }

  // ---------- feed ----------
  // An entry "tagged with a topic": an event-map pin, or a wire or Telegram entry the server gave a category.
  // The front page and the wall show only these; the Feed page shows everything unless asked.
  const tagged = (e) => e.src === "pin" || (e.cat && e.cat !== "other");
  const SRC = { pin: "Event map", wire: "News wire", telegram: "Telegram" };
  function groupOf(ts, now) {
    if (ts > now - 3600000) return "In the last hour";
    const d = dayKey(ts);
    if (d === dayKey(now)) return "Earlier today";
    if (d === dayKey(now - 86400000)) return "Yesterday";
    return fmtDay(ts);
  }
  function entryHtml(e, opt) {
    const o = opt || {}, [cname, family] = cat(e.cat), th = thName(e.theatre), isNew = S.lastSeen && e.ts > S.lastSeen;
    const kick = [e.cat && e.cat !== "other" ? cname : "", th].filter(Boolean).join(" · ");
    const text = !o.full && e.title.length > 150 ? e.title.slice(0, 140).replace(/\s+\S*$/, "") + "…" : e.title;   // short lists keep long posts short
    const title = e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : esc(text);
    const from = [e.from, e.srcLabel].filter(Boolean).map(esc).join(" · ");   // a pin from another source names it; none means the source map
    const src = e.src === "pin" ? (o.full ? `Event map${e.place ? ", " + esc(e.place) : ""} · ${from}` : esc(e.place || "Event map") + (e.from ? " · " + esc(e.from) : "")) + (e.day ? " · date only" : "") : `${SRC[e.src]} · ${esc(e.srcLabel)}`;
    const time = e.day ? `<time class="e-time day" datetime="${new Date(e.day).toISOString().slice(0, 10)}">${esc(dayOnly(e.day))}</time>`
      : `<time class="e-time" datetime="${new Date(e.ts).toISOString()}">${o.date && dayKey(e.ts) !== dayKey(Date.now()) ? `<span>${esc(fmtShort(e.ts))}</span> ` : ""}${fmtTime(e.ts)}</time>`;
    return `<article class="entry${isNew ? " isnew" : ""}" data-id="${esc(e.id)}">
      ${time}
      <div class="e-body">
        <p class="e-kick"><i class="dot f-${family}" aria-hidden="true"></i>${esc(kick || SRC[e.src])}${isNew ? ' <span class="newtag">New</span>' : ""}</p>
        <h3 class="e-title">${title}</h3>
        ${o.full && e.summary ? `<p class="e-sum">${esc(e.summary)}</p>` : ""}
        <p class="e-src">${src}${e.ll ? ` · <button type="button" class="linkbtn" data-show="${esc(e.pid)}">Show on the map</button>` : ""}</p>
      </div></article>`;
  }
  function groupedHtml(list, opt) {
    const now = Date.now(); let last = "", html = "";
    list.forEach((e) => {
      const g = groupOf(e.ts, now);
      if (g !== last) { html += `<h3 class="grp"><span>${esc(g)}</span></h3>`; last = g; }
      html += entryHtml(e, opt);
    });
    return html;
  }
  const kindOk = (e) => S.filter.kind === "all" || tagged(e);
  const filtered = () => S.entries.filter((e) => (S.filter.theatre === "all" || e.theatre === S.filter.theatre) && (S.filter.src === "all" || e.src === S.filter.src) && kindOk(e));
  function renderFeed() {
    const all = filtered(), now = Date.now(), list = all.slice(0, S.shown);
    $("feed").innerHTML = list.length ? groupedHtml(list, { full: true }) : `<p class="none">${S.entries.length ? "Nothing matches these filters." : "The feed has not loaded yet."}</p>`;
    $("feedmore").parentNode.hidden = all.length <= S.shown;
    $("feedmore").textContent = `Show older entries (${nf(all.length - list.length)} more)`;
    const bySrc = S.entries.filter((e) => (S.filter.src === "all" || e.src === S.filter.src) && kindOk(e)), day = (e) => e.ts > now - 86400000;
    const n24 = (k) => bySrc.filter((e) => day(e) && (k === "all" || e.theatre === k)).length;
    const ths = [["all", "All theatres"], ...Object.entries(THEATRES).map(([k, v]) => [k, v[0]])];
    $("thchips").innerHTML = ths.map(([k, n]) => `<button type="button" class="chip" data-th="${k}" aria-pressed="${S.filter.theatre === k}"><span>${esc(n)}</span><b>${nf(n24(k))}</b></button>`).join("");
    $("thsel").innerHTML = ths.map(([k, n]) => `<option value="${k}"${S.filter.theatre === k ? " selected" : ""}>${esc(n)} (${nf(n24(k))} in 24 h)</option>`).join("");
    const inTh = S.entries.filter((e) => S.filter.theatre === "all" || e.theatre === S.filter.theatre), byTh = inTh.filter(kindOk);
    const inBoth = inTh.filter((e) => S.filter.src === "all" || e.src === S.filter.src);
    $("kindchips").innerHTML = [["all", "Everything"], ["tagged", "Tagged with a topic"]].map(([k, n]) => `<button type="button" class="chip" data-kind="${k}" aria-pressed="${S.filter.kind === k}"><span>${n}</span><b>${nf(inBoth.filter((e) => day(e) && (k === "all" || tagged(e))).length)}</b></button>`).join("");
    // a source this copy does not carry gets no chip; with the event map alone, the Source and Show filters would change nothing
    const others = ["wire", "telegram"].filter((k) => !absent(k)), gone = ["wire", "telegram"].filter(absent);
    const srcs = [["all", "All sources"], ["pin", "Event map"], ["wire", "News wire"], ["telegram", "Telegram"]].filter(([k]) => !gone.includes(k));
    $("srcchips").parentNode.hidden = $("kindchips").parentNode.hidden = !others.length;
    $("srcchips").innerHTML = srcs.map(([k, n]) => `<button type="button" class="chip" data-src="${k}" aria-pressed="${S.filter.src === k}"><span>${n}</span><b>${nf(byTh.filter((e) => day(e) && (k === "all" || e.src === k)).length)}</b></button>`).join("");
    const miss = ["wire", "telegram"].filter((k) => S.failed[k]).map((k) => SRC[k]);
    const from = ["the event map", ...others.map((k) => (k === "wire" ? "the news wire" : "Telegram"))];
    $("feedstand").textContent = `Every dated entry from ${from.length > 1 ? from.slice(0, -1).join(", ") + " and " + from[from.length - 1] : from[0]}, newest first. Counts are for the last 24 hours. Times are ${zlabel()}.`
      + (gone.length ? ` ${gone.map((k) => SRC[k]).join(" and ")}: not on this copy.` : "") + (miss.length ? ` Could not load: ${miss.join(", ")}.` : "");
  }

  // ---------- front page ----------
  function renderLead() {
    const pic = (S.analysis || {}).picture, sum = S.summary || {};
    if (!pic) {
      $("headline").textContent = S.failed.analysis ? "The analyst picture could not be loaded" : "Loading the picture";
      $("bluf").textContent = S.failed.analysis ? "The map and the feed below still work." : "";
      $("tension").innerHTML = ""; $("changes").innerHTML = ""; return;
    }
    const gen = isoMs(pic.generated_at), b = sentences(zText(pic.bluf, isoMs(pic.generated_at)), 3);
    $("leadmeta").textContent = `The analyst picture, written ${gen ? when(gen) + " " + zlabel() + " (" + ago(gen) + ")" : "at an unknown time"}${pic.confidence ? " · confidence " + pic.confidence : ""}`;
    $("headline").textContent = zText(pic.headline, gen) || "No headline";
    $("bluf").textContent = b.head;
    $("tension").innerHTML = tensionHtml(pic);
    const ch = pic.changes_since_last || [];
    $("changes").innerHTML = ch.length ? ch.slice(0, 4).map((c) => `<li>${esc(zText(c, gen))}</li>`).join("") : `<li class="none">No changes listed in this picture.</li>`;
    const fresh = S.lastSeen ? S.entries.filter((e) => e.ts > S.lastSeen).length : 0;
    $("since").innerHTML = S.lastSeen
      ? `<b>Since you last looked</b> (${esc(ago(S.lastSeen))}): ${fresh ? `<a href="#/feed">${nf(fresh)} new ${fresh === 1 ? "entry" : "entries"}</a>, marked New in the feed.` : "nothing new in the feed."}`
      : `<b>${nf(sum.events_6h)}</b> events pinned in the last 6 hours, <b>${nf(sum.events_24h)}</b> in 24.`;
    // wall view
    $("wheadline").textContent = zText(pic.headline, gen) || "";
    $("wbluf").textContent = sentences(zText(pic.bluf, gen), 2).head;
    $("wtension").innerHTML = tensionHtml(pic);
    const al = sum.regional_alerts || {}, ua = al.ukraine || {}, il = al.israel || {};
    $("wfacts").innerHTML = [
      `<b>${nf(sum.events_24h)}</b> events pinned in 24 hours`,
      ua.n != null ? `<b>${nf(ua.n)}</b> regions of Ukraine under air-raid alert${ua.red ? ` (${nf(ua.red)} red)` : ""}` : "",
      il.sirens_now != null ? (il.sirens_now ? `<b>${nf(il.sirens_now)}</b> sirens sounding in Israel` : "No sirens in Israel now") : "",
    ].filter(Boolean).map((t) => `<li>${t}</li>`).join("");
  }
  function renderLatest() {
    const none = `<p class="none">${S.loadedAt ? "No entries could be loaded." : "Loading"}</p>`;
    const pins = S.entries.filter((e) => e.src === "pin" && !e.day).slice(0, 5), wire = S.entries.filter((e) => e.src !== "pin" && tagged(e)).slice(0, 9);
    $("latestpins").innerHTML = pins.length ? pins.map((e) => entryHtml(e, { date: true })).join("") : none;
    const noWire = absent("wire") && absent("telegram");
    $("latest").innerHTML = noWire ? `<p class="none">${NOT_HERE}</p>` : wire.length ? groupedHtml(wire) : none;
    $("latesthint").hidden = noWire;
    $("wlatest").innerHTML = S.entries.filter((e) => tagged(e) && !e.day).slice(0, 8).map((e) => entryHtml(e)).join("");
    $("wzone").textContent = zlabel();
    // the wall list never shows a half-cut entry: drop the ones that do not fit
    requestAnimationFrame(() => { const box = $("wlatest"), max = box.getBoundingClientRect().bottom; [...box.children].forEach((c) => { c.hidden = c.getBoundingClientRect().bottom > max + 1; }); });
  }
  function renderWorld() {
    const pic = (S.analysis || {}).picture, by = (S.summary || {}).events_24h_by_theatre || {};
    if (!pic || !pic.theatres) { $("world").innerHTML = `<p class="none">Theatre notes come with the analyst picture, which has not loaded.</p>`; return; }
    $("world").innerHTML = pic.theatres.map((t) => {
      const n = Number(t.status), dev = zText((t.key_developments || [])[0] || sentences(String(t.summary || "").replace(/^Evidence:\s*/, ""), 1).head, isoMs(pic.generated_at));
      return `<article class="th"><h3><a href="#/conflict?t=${esc(t.theatre)}">${esc(thName(t.theatre) || t.theatre)}</a></h3>
        <p class="th-lv lv-${level(n)}"><b>${esc(n)}</b>/10 <span>${esc(t.trend || "")}</span><em>${plural(by[t.theatre] || 0, "event")} in 24 h</em></p>
        <p class="th-txt">${esc(dev)}</p></article>`;
    }).join("");
  }
  function renderBriefs() {
    const s = S.summary;
    if (!s) { $("briefs").innerHTML = `<p class="none">The summary has not loaded.</p>`; return; }
    const al = s.regional_alerts || {}, ua = al.ukraine || {}, ru = al.russia || {}, il = al.israel || {}, out = s.internet_outages || {}, adv = s.travel_advisories || {};
    const pw = ((s.chokepoint_transits_portwatch || {}).chokepoints || []), uk = s.ukmto_latest;
    const items = [
      ["conflict", "Air-raid alerts", ua.n != null ? `${nf(ua.n)} regions of Ukraine are under alert${ua.red ? `, ${nf(ua.red)} of them red` : ""}${ru.n ? `; ${nf(ru.n)} in Russia` : ""}. ${il.sirens_now ? nf(il.sirens_now) + " sirens are sounding in Israel." : "No sirens in Israel now."}` : "Alert counts are not in the summary."],
      ["sea", "Sea", `${nf(s.ukmto_incidents_7d)} maritime incidents reported in 7 days${uk ? `; the latest, ${esc(String(uk.type || "").toLowerCase())}, ${esc(uk.where || "")} on ${esc(fmtDate(uk.date))}` : ""}.${pw.length ? " Chokepoint traffic against a year ago is in the Sea section." : ""}`],
      ["air", "Air", `${nf(s.mil_aircraft)} military aircraft are being tracked. ${s.airspace_czib_active != null ? nf(s.airspace_czib_active) + " conflict-zone airspace warnings are in force." : ""}`],
      ["outages", "Outages and cyber", out.countries_with_outages != null ? `${nf(out.countries_with_outages)} countries had internet outages in the last ${nf(out.window_h)} hours${(out.watched_countries || []).filter((c) => c.ongoing).length ? `; ongoing in ${(out.watched_countries || []).filter((c) => c.ongoing).slice(0, 3).map((c) => esc(c.country)).join(", ")}` : ""}.` : "Outage counts are not in the summary."],
      ["hazards", "Hazards", `${Object.values(s.firms_hotspots_by_theatre || {}).length ? nf(Object.values(s.firms_hotspots_by_theatre).reduce((a, b) => a + b, 0)) + " satellite fire detections in the watched theatres. " : ""}Earthquakes and disaster alerts are in the Hazards section.`],
      ["official", "Official", adv.level4 != null ? `${nf(adv.level4)} countries are at “Do not travel”, ${nf(adv.level3)} at “Reconsider travel”${(adv.level_changes || []).length ? `; ${nf(adv.level_changes.length)} level changes since the watch began` : ""}.` : "Advisory counts are not in the summary."],
    ];
    $("briefs").innerHTML = items.map(([k, h, t]) => `<article class="brief"><h3><a href="#/${k}">${h}</a></h3><p>${t}</p></article>`).join("");
  }
  function renderMast() {
    const now = Date.now(), st = S.status;
    $("today").textContent = fmtDay(now);
    $("clock").textContent = fmtTime(now) + " " + (S.tz === "utc" ? "UTC" : "ET");
    $("wclock").textContent = new Date(now).toLocaleDateString("en-GB", { timeZone: zone(), weekday: "short", day: "numeric", month: "short" }) + ", " + fmtTime(now) + " " + (S.tz === "utc" ? "UTC" : "ET");
    document.querySelectorAll(".zone button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tz === S.tz)));
    const live = $("live"); let txt = "Loading", cls = "";
    if (S.loadedAt) {
      const feeds = Object.values((st || {}).feeds || {}), bad = feeds.filter((f) => !f.ok || f.stale).length;
      const failed = Object.keys(S.failed).length;
      if (failed && !S.events) { txt = "Offline"; cls = "down"; }
      else if (failed) { txt = "Partly loaded"; cls = "warn"; }
      else if (feeds.length) { txt = bad ? `Live · ${bad} of ${feeds.length} sources late` : `Live · all ${feeds.length} sources reporting`; cls = bad ? "warn" : "ok"; }
      else { txt = "Live"; cls = "ok"; }
    }
    live.className = "live " + cls; $("livet").textContent = txt;
  }

  function render() {
    renderMast();
    const v = S.route.view;
    if (v === "home" || v === "wall") { renderLead(); renderLatest(); }
    if (v === "home") { renderWorld(); renderBriefs(); }
    if (v === "feed") renderFeed();
    emit("render", S.route);
  }

  // ---------- events ----------
  document.addEventListener("click", (e) => {
    const t = e.target.closest ? e.target : null; if (!t) return;
    const tz = t.closest(".zone button");
    if (tz) { S.tz = tz.dataset.tz; store.set("tz", S.tz); buildEntries(); render(); return; }
    const th = t.closest("[data-th]"); if (th) { S.filter.theatre = th.dataset.th; S.shown = 60; renderFeed(); return; }
    const kd = t.closest("[data-kind]"); if (kd) { S.filter.kind = kd.dataset.kind; S.shown = 60; renderFeed(); return; }
    const sr = t.closest("[data-src]"); if (sr) { S.filter.src = sr.dataset.src; S.shown = 60; renderFeed(); return; }
    const sh = t.closest("[data-show]");
    if (sh) { e.preventDefault(); emit("show", sh.dataset.show); return; }
    if (t.closest("#feedmore")) { S.shown += 80; renderFeed(); return; }
    if (t.closest("#tabsections")) { const open = $("sheet").hidden; $("sheet").hidden = !open; $("tabsections").setAttribute("aria-expanded", String(open)); if (open) $("sheetclose").focus(); return; }
    if (t.closest("#sheetclose")) { closeSheet(); $("tabsections").focus(); return; }
    if (t.closest("[data-classic]")) { if (window.GTTheme) window.GTTheme.go("classic"); else location.href = "index.html?theme=classic"; }
  });
  $("thsel").addEventListener("change", (e) => { S.filter.theatre = e.target.value; S.shown = 60; renderFeed(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("sheet").hidden) { closeSheet(); $("tabsections").focus(); } });
  window.addEventListener("hashchange", route);

  window.GT2 = { S, $, esc, nf, api, need, on, emit, THEATRES, FAMILY, CATS, cat, fam, thName, fmtTime, fmtDay, fmtShort, fmtDate, plural, when, ago, isoMs, zlabel, zText,
    entryHtml, groupedHtml, sentences, level, levelWord, tensionHtml, httpUrl, render, store, absent, statusKnown, NOT_HERE, PINSRC, pinSource, pinStats, dayOnly };

  // The version beside the live light, the theme button directly under it (themes/switch.js draws the button).
  if (window.GTTheme) { $("ver").textContent = window.GTTheme.version ? "v" + window.GTTheme.version : ""; window.GTTheme.mount($("themeslot")); }
  navHtml();
  route();
  loadCore().then(() => {
    // "Since you last looked": remember this visit once the reader has had the page open for a while.
    setTimeout(() => store.set("seen", String(Date.now())), 30000);
  });
  setInterval(() => { if (!document.hidden) loadCore(); }, 180000);
  setInterval(renderMast, 15000);
})();
