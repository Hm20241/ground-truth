/* Ground Truth 1.7.0, Atlas theme, the interface: search, topic pills, the one sheet (Now, Feed, Topics, More), the detail
   card and the wall display. Three layouts from one page: desk (side panel), phone (bottom sheet + tab bar), wall (nothing
   to touch). The wall display never starts by itself: only ?wall=1 in the address or the More setting turns it on.
   1.7.1: where a feed this copy does not carry would show (A.has in core.js), the screen says "Not on this copy." */
(() => {
  "use strict";
  const A = window.ATLAS, { $, esc, nf, LS, S, ico, COL } = A;
  const NAV = [["now", "Now", "now"], ["feed", "Feed", "feed"], ["topics", "Topics", "topics"], ["more", "More", "more"]];
  const body = $("body"), sheet = $("sheet"), root = document.documentElement;
  const UI = { mode: "desk", sheet: "half", limit: 60, filterOpen: false, detail: false, panelW: Math.min(640, Math.max(340, +LS.get("panel", 420) || 420)), collapsed: LS.get("collapsed", "0") === "1", wallI: -1 };
  document.querySelectorAll("[data-ico]").forEach((el) => { el.innerHTML = ico(el.dataset.ico); });

  // ---------- layout mode ----------
  // On or Off, Off unless asked for: ?wall=1 / ?wall=0 in the address, else the More setting (a stored "auto" from the design draft counts as Off).
  const wallPref = () => { const u = new URLSearchParams(location.search).get("wall"); return u === "1" ? "on" : u === "0" ? "off" : LS.get("wall", "off") === "on" ? "on" : "off"; };
  const modeNow = () => (wallPref() === "on" ? "wall" : innerWidth <= 700 ? "phone" : "desk");
  const TAB_H = 62;
  const sheetPx = (st) => { const H = innerHeight; return st === "peek" ? 138 : st === "full" ? Math.max(260, H - TAB_H - 66) : Math.round(H * 0.5); };
  function setSheet(st, px) {
    UI.sheet = st; sheet.classList.toggle("peek", st === "peek" && px == null); root.classList.toggle("sheet-full", st === "full");
    root.style.setProperty("--sheet-h", (px == null ? sheetPx(st) : px) + "px");
    $("grab").setAttribute("aria-label", "Sheet height: " + (st === "peek" ? "low" : st === "full" ? "full" : "half") + ". Activate to change it.");
  }
  A.pad = () => {
    if (UI.mode === "wall") return { left: 690, right: 590, top: 60, bottom: 60 };
    if (UI.mode === "phone") return { top: 120, bottom: Math.min(sheetPx(UI.sheet), sheetPx("half")) + TAB_H, left: 0, right: 0 };
    return { left: UI.collapsed ? 0 : UI.panelW + 24, right: S.sel ? 400 : 0, top: 110, bottom: 0 };
  };
  function layout() {
    const m = modeNow(), was = UI.mode; UI.mode = m;
    root.classList.toggle("wall", m === "wall"); root.classList.toggle("collapsed", m === "desk" && UI.collapsed);
    root.style.setProperty("--panel-w", UI.panelW + "px");
    $("wall").hidden = m !== "wall"; $("reopen").hidden = !(m === "desk" && UI.collapsed);
    if (m === "phone") setSheet(UI.sheet);
    if (m !== was) { UI.detail = m === "phone" && !!S.sel; render(); renderDetail(); if (m === "wall") startWall(); else { stopWall(); if (was === "wall") A.map.jumpTo({ center: [30, 34], zoom: m === "phone" ? 1.6 : 2.4, padding: A.pad() }); } }
  }
  addEventListener("resize", layout);

  // ---------- small builders ----------
  const toneCol = (t) => (t === "red" ? "var(--red)" : t === "amber" ? "var(--amber)" : t === "blue" ? "var(--blue)" : "");
  const disc = (e) => (e.c ? `<span class="disc" style="--c:${e.c}">${ico(e.glyph)}</span>` : `<span class="disc plain"${toneCol(e.tone) ? ` style="color:${toneCol(e.tone)}"` : ""}>${ico(e.glyph || "dot")}</span>`);
  const metaOf = (e) => (e.group === "pins" ? [e.label, e.place, A.whenShort(e)] : [e.src || e.kind, e.place, A.whenShort(e)]).filter(Boolean).map(esc).join(" · ");
  const row = (e) => `<li><button type="button" class="row${S.sel && S.sel.id === e.id ? " on" : ""}" data-act="sel" data-id="${esc(e.id)}">${disc(e)}<span class="r-main"><span class="r-title">${esc(e.title)}</span><span class="r-meta">${metaOf(e)}</span></span></button></li>`;
  const chip = (act, v, label, on) => `<button type="button" class="chip" data-act="${act}" data-v="${esc(v)}" aria-pressed="${on ? "true" : "false"}">${esc(label)}</button>`;
  const openClassic = `<button type="button" class="link" data-act="classic">Open Classic${ico("right")}</button>`;
  const NA = "Not on this copy.";
  const stub = (name, what, feeds) => (feeds && !A.hasAny(feeds) ? `<div class="stub"><b>${esc(name)}</b>${esc(what)} ${NA}</div>`
    : `<div class="stub"><b>${esc(name)}</b>${esc(what)} Not in this theme yet. It is in the Classic theme.<br>${openClassic}</div>`);
  // a figure whose feed this copy does not carry keeps its place and says so
  const tile = (n, label, feeds) => (feeds && !A.hasAny(feeds) ? `<div class="tile"><span style="color:var(--text)">${esc(label.charAt(0).toUpperCase() + label.slice(1))}</span><span>${NA}</span></div>`
    : `<div class="tile"><b>${esc(n)}</b><span>${esc(label)}</span></div>`);
  const loading = (name) => (!A.has(name) ? `<div class="empty">${NA}</div>` : S.failed.has(name) ? `<div class="empty">The server did not answer for this part. It will be tried again.</div>` : `<div class="empty">Loading…</div>`);
  const tcol = (n) => (n >= 8 ? "var(--red)" : n >= 5 ? "var(--amber)" : "var(--text)");
  const pic = () => (S.d.analysis || {}).picture || null;
  const tensionHtml = (p) => `<div class="tension" style="--tc:${tcol(p.overall_tension)}"><div class="t-num" aria-hidden="true">${esc(p.overall_tension)}<span>/10</span></div>
    <div class="t-side"><div class="t-label">Tension ${esc(p.overall_tension)} of 10<span>, ${esc(p.trend || "steady")}</span></div>
    <div class="t-bar" aria-hidden="true">${Array.from({ length: 10 }, (_, i) => `<i${i < p.overall_tension ? ' class="on"' : ""}></i>`).join("")}</div></div></div>`;
  const netWord = () => ({ ok: "Up to date", partial: "Some sources did not answer", offline: "Cannot reach the server", loading: "Loading" }[S.net]);

  // ---------- Now ----------
  const NEW_WORD = { pins: ["map pin", "map pins"], wire: ["from the news wire", "from the news wire"], telegram: ["from Telegram", "from Telegram"], official: ["official statement", "official statements"],
    alerts: ["alert", "alerts"], sea: ["sea incident", "sea incidents"], air: ["air notice", "air notices"], outages: ["outage", "outages"], cyber: ["cyber record", "cyber records"], hazards: ["hazard", "hazards"] };
  function alertRows() {
    const s = (S.d.alerts || {}).summary; if (!s) return null;
    const rows = [], quiet = [];
    const reg = (key, name, r) => { if (!r) return; if (!r.n) { quiet.push(`No air-raid alerts in ${name}`); return; }
      rows.push({ act: "alertsat", v: key, glyph: "megaphone", tone: r.red ? "red" : "amber", title: `${name}: ${r.n} region${r.n === 1 ? "" : "s"} under air-raid alert`,
        meta: [r.red ? r.red + " red" : "", r.yellow ? r.yellow + " yellow" : ""].filter(Boolean).join(", ") || (r.regions || []).slice(0, 3).join(", ") }); };
    reg("ukraine-russia", "Ukraine", s.ukraine); reg("russia", "Russia", s.russia); reg("europe-nato", "Poland", s.poland);
    const il = s.israel || {};
    if (il.sirens_now) rows.unshift({ act: "alertsat", v: "israel", glyph: "megaphone", tone: "red", title: `Israel: ${il.sirens_now} siren${il.sirens_now === 1 ? "" : "s"} sounding now`, meta: il.in_shelter_window ? il.in_shelter_window + " places still in the shelter window" : "" });
    else quiet.push("No sirens sounding in Israel");
    const em = s.us_embassies || {};
    if (em.alerts_24h) rows.push({ act: "topicgo", v: "official", glyph: "officer", tone: "amber", title: `${em.alerts_24h} US embassy alert${em.alerts_24h === 1 ? "" : "s"} in the last 24 hours`, meta: ((em.latest || [])[0] || {}).title || "" });
    return { rows, quiet };
  }
  function viewNow() {
    const p = pic(), sum = S.d.summary || {}, now = Date.now();
    let h = "";
    if (!p) h += S.loaded.has("analysis") || S.failed.has("analysis") ? `<div class="empty">The analyst picture is not available right now.</div>` : loading("analysis");
    else {
      const at = A.isoMs(p.generated_at);
      h += tensionHtml(p) + `<h1 class="head">${esc(A.zText(p.headline, at))}</h1><p class="lede${UI.ledeOpen ? "" : " clamp"}" id="lede">${esc(A.zText(p.bluf, at))}</p>
        <button type="button" class="link" data-act="lede" aria-expanded="${!!UI.ledeOpen}" aria-controls="lede">${UI.ledeOpen ? "Show less" : "Read the whole bottom line"}</button>
        <p class="muted small">Analyst picture written ${esc(A.ago(at))}, confidence ${esc(p.confidence || "not stated")}. ${esc(A.fmtDate(now))}, ${esc(A.fmtT(now))}${S.zone === "utc" ? "" : " " + esc(A.zoneAbbr())}. ${esc(netWord())}.</p>
        <button type="button" class="link" data-act="page" data-v="analyst">Read the full analyst picture ${ico("right")}</button>`;
    }
    // since you last looked
    const fresh = S.lastSeen ? A.feed({ topic: "all", noFilter: true }).filter((e) => e.ts > S.lastSeen) : [];
    if (S.lastSeen) {
      const by = {}; fresh.forEach((e) => { by[e.group] = (by[e.group] || 0) + 1; });
      h += `<section class="sec"><h2>Since you last looked <small>${esc(A.ago(S.lastSeen))}</small></h2>` + (fresh.length
        ? `<div class="rows"><button type="button" class="row" data-act="nav" data-v="feed"><span class="disc" style="--c:var(--accent)">${ico("feed")}</span><span class="r-main"><span class="r-title">${nf(fresh.length)} new entr${fresh.length === 1 ? "y" : "ies"} in the feed</span>
          <span class="r-meta">${esc(Object.entries(by).sort((a, b) => b[1] - a[1]).map(([g, n]) => `${n} ${(NEW_WORD[g] || ["entry", "entries"])[n === 1 ? 0 : 1]}`).join(", "))}</span></span><span class="r-end">${ico("right")}</span></button></div>`
        : `<p class="muted">Nothing new in the feed.</p>`) + `</section>`;
    }
    const ar = alertRows();
    h += `<section class="sec"><h2>Alerts in force</h2>` + (!ar ? loading("alerts") : (ar.rows.length ? `<div class="rows">` + ar.rows.map((r) => `<button type="button" class="row" data-act="${r.act}" data-v="${r.v}">
      <span class="disc plain" style="color:${toneCol(r.tone)}">${ico(r.glyph)}</span><span class="r-main"><span class="r-title">${esc(r.title)}</span>${r.meta ? `<span class="r-meta">${esc(r.meta)}</span>` : ""}</span><span class="r-end">${ico("right")}</span></button>`).join("") + `</div>` : "") +
      (ar.quiet.length ? `<p class="muted small" style="margin-top:6px">${esc(ar.quiet.join(". "))}.</p>` : "")) + `</section>`;
    h += `<section class="sec"><h2>Busiest fronts <small>pins nearby, 72 hours</small></h2>` + (!S.loaded.has("events") ? loading("events") : S.fronts.length
      ? `<div class="rows">` + S.fronts.slice(0, 4).map((f) => `<button type="button" class="row" data-act="sel" data-id="${f.id}"><span class="disc" style="--c:${COL.red}">${ico(f.glyph)}</span>
        <span class="r-main"><span class="r-title">${esc(f.title)}</span><span class="r-meta">${esc([f.kind, f.place, "about " + nf(Math.round(f.km)) + " km"].filter(Boolean).join(" · "))}</span></span><span class="r-end"><b>${f.n72}</b></span></button>`).join("") + `</div>`
      : `<p class="muted">The source map draws no front line right now.</p>`) + `</section>`;
    if (p && (p.changes_since_last || []).length) h += `<section class="sec"><h2>What changed <small>since the last picture</small></h2><ul class="changes">${p.changes_since_last.map((c) => `<li>${esc(A.zText(c, A.isoMs(p.generated_at)))}</li>`).join("")}</ul></section>`;
    if (p && (p.theatres || []).length) {
      const n24 = sum.events_24h_by_theatre || {};
      h += `<section class="sec"><h2>Regions <small>analyst rating</small></h2><div class="rows">` + p.theatres.slice().sort((a, b) => b.status - a.status).map((t) => `<button type="button" class="row" data-act="page" data-v="region:${esc(t.theatre)}">
        <span class="disc plain" style="color:${tcol(t.status)}">${esc(t.status)}</span><span class="r-main"><span class="r-title">${esc(A.regionName(t.theatre) || t.theatre)}</span>
        <span class="r-meta">${esc(t.trend || "steady")} · ${nf(n24[t.theatre] || 0)} map pin${n24[t.theatre] === 1 ? "" : "s"} in 24 hours</span></span><span class="r-end">${ico("right")}</span></button>`).join("") + `</div></section>`;
    }
    return h;
  }

  // ---------- Feed ----------
  function listHtml(list, limit, markNew) {
    let h = "", day = "", marked = !markNew || !S.lastSeen || !list.length || list[0].ts <= S.lastSeen;
    list.slice(0, limit).forEach((e) => {
      if (!marked && e.ts <= S.lastSeen) { marked = true; h += `</ol><div class="newmark">New above, since ${esc(A.fmtT(S.lastSeen))}</div><ol class="rows">`; }
      const d = A.dayLabel(e.ts); if (d !== day) { day = d; h += `</ol><div class="day">${esc(d)}</div><ol class="rows">`; }
      h += row(e);
    });
    return `<ol class="rows">${h}</ol>` + (list.length > limit ? `<div style="margin-top:12px"><button type="button" class="btn" data-act="morerows">Show ${Math.min(60, list.length - limit)} more</button></div>` : "");
  }
  function viewFeed() {
    const list = A.feed(), topic = A.TOPICS.find((t) => t.k === S.topic), nActive = (S.region !== "all") + (S.hours ? 1 : 0) + (S.topic === "all" && (S.groups.size !== A.DEFAULT_GROUPS.length || A.DEFAULT_GROUPS.some((g) => !S.groups.has(g))) ? 1 : 0);
    let h = `<div class="view-top"><h2 class="view-h">Feed<small>${nf(list.length)} entr${list.length === 1 ? "y" : "ies"}, newest first</small></h2>
      <button type="button" class="btn" data-act="filter" aria-expanded="${UI.filterOpen}" aria-controls="filterbox">${ico("filter")}Filter${nActive ? `<span class="badge">${nActive}</span>` : ""}</button></div>`;
    if (S.topic !== "all") h += `<div class="topicnote">${ico(topic.icon)}<span>Showing the <b>${esc(topic.name)}</b> topic, the same as the map.</span><button type="button" data-act="topic" data-v="all">Show all</button></div>`;
    if (UI.filterOpen) {
      h += `<div class="filter" id="filterbox"><h3>Region</h3><div class="chips">${chip("region", "all", "Everywhere", S.region === "all")}${Object.entries(A.REGIONS).map(([k, v]) => chip("region", k, v[0], S.region === k)).join("")}</div>
        <h3>Time</h3><div class="chips">${[[0, "Any time"], [6, "Last 6 hours"], [24, "Last 24 hours"], [72, "Last 3 days"]].map(([v, l]) => chip("hours", v, l, S.hours === v)).join("")}</div>
        <h3>Sources${S.topic !== "all" ? " (follow the topic while one is picked)" : ""}</h3><div class="chips">${Object.entries(A.GROUPS).filter(([k]) => A.groupOn(k)).map(([k, l]) => `<button type="button" class="chip" data-act="group" data-v="${k}" aria-pressed="${S.topic === "all" ? S.groups.has(k) : false}"${S.topic !== "all" ? " disabled" : ""}>${esc(l)}</button>`).join("")}</div>
        ${Object.keys(A.GROUPS).some((k) => !A.groupOn(k)) ? `<p class="muted small" style="margin-top:10px">Left out: ${esc(Object.entries(A.GROUPS).filter(([k]) => !A.groupOn(k)).map(([, l]) => l).join(", "))}. ${NA}</p>` : ""}
        <p class="muted small" style="margin-top:10px">The time filter also applies to the pins on the map.</p></div>`;
    }
    if (!S.loaded.has("events") && !S.loaded.has("wire")) return h + loading("events");
    return h + (list.length ? listHtml(list, UI.limit, S.topic === "all") : `<div class="empty">Nothing matches these filters.</div>`);
  }

  // ---------- Topics ----------
  const statOf = {
    all: () => `${nf((S.d.summary || {}).events_24h)} map pins in 24 hours`,
    conflict: () => `${nf((S.d.summary || {}).events_24h)} pins in 24 hours, ${S.fronts.length} front line${S.fronts.length === 1 ? "" : "s"}`,
    alerts: () => { const s = (S.d.alerts || {}).summary; return s ? `${(s.ukraine || {}).n || 0} regions in Ukraine, ${(s.russia || {}).n || 0} in Russia, ${(s.israel || {}).sirens_now || 0} sirens in Israel` : "Loading"; },
    air: () => `${nf((S.d.summary || {}).mil_aircraft)} military aircraft heard`,
    sea: () => `${nf((S.d.summary || {}).ukmto_incidents_7d)} incidents at sea in 7 days`,
    outages: () => { const o = (S.d.summary || {}).internet_outages; return o ? `${o.countries_with_outages} countries with internet outages in ${o.window_h} hours` : "Loading"; },
    cyber: () => (S.d.cyber ? `${nf(S.entries.filter((e) => e.group === "cyber" && Date.now() - e.ts < 86400000).length)} new records in 24 hours` : "Opens when picked"),
    hazards: () => (S.d.hazards ? `${nf(((S.d.hazards.by_alert || {}).Orange || 0) + ((S.d.hazards.by_alert || {}).Red || 0))} orange or red alerts, ${nf((S.d.quakes || {}).count)} earthquakes` : "Opens when picked"),
    official: () => { const t = (S.d.summary || {}).travel_advisories; return t ? `${t.level4} countries at "Do not travel"` : "Loading"; },
  };
  // the feed behind each row's figure; a topic with none of its feeds on this copy is a plain line, not a button
  const FIG_FEED = { air: ["mil"], sea: ["ukmto"], outages: ["outages"], cyber: ["cyber"], hazards: ["hazards", "quakes"], official: ["advisories"] };
  function viewTopics() {
    return `<div class="view-top"><h2 class="view-h">Topics<small>Pick one: the map and the feed follow it</small></h2></div><div class="rows">` + A.TOPICS.map((t) => {
      const inner = `<span class="disc plain">${ico(t.icon)}</span><span class="r-main"><span class="r-title">${esc(t.name)}</span><span class="r-meta">${esc(t.blurb)}</span><span class="r-meta" style="color:var(--text)">${esc(FIG_FEED[t.k] && !A.hasAny(FIG_FEED[t.k]) ? NA : statOf[t.k]())}</span></span>`;
      return A.topicOn(t.k) ? `<button type="button" class="row${S.topic === t.k ? " on" : ""}" data-act="topicpage" data-v="${t.k}">${inner}<span class="r-end">${ico("right")}</span></button>` : `<div class="row">${inner}</div>`; }).join("") + `</div>`;
  }
  const LEGEND = {
    all: [["dot", "red", "Fighting: strikes, drones, missiles, forces"], ["dot", "blue", "At sea"], ["dot", "amber", "Energy and infrastructure"], ["dot", "slate", "Statements and reports"], ["line", "red", "Battle fronts"], ["area", "red", "Air-raid alert, red"], ["area", "amber", "Air-raid alert, yellow"], ["ring", "blue", "Incident at sea", ["ukmto"]]],
    conflict: [["dot", "red", "Fighting: strikes, drones, missiles, forces"], ["dot", "blue", "At sea"], ["dot", "amber", "Energy and infrastructure"], ["dot", "slate", "Statements and reports"], ["line", "red", "Front line (solid), blockade or defence line (dashed)"], ["area", "red", "Occupied area in Ukraine (DeepState)", ["front"]], ["area", "slate", "Status unknown, and other areas drawn on the source map"]],
    alerts: [["area", "red", "Air-raid alert, red"], ["area", "amber", "Air-raid alert, yellow"], ["area", "slate", "Standing warning"], ["dot", "red", "Siren in Israel, last 10 minutes"], ["dot", "slate", "Siren in Israel, last 24 hours"], ["ring", "amber", "US embassy alert, last 3 days"]],
    air: [["dot", "slate", "Military aircraft (red when it reports an emergency)", ["mil"]], ["area", "blue", "US flight restriction", ["tfr"]], ["ring", "red", "Emergency code being sent now", ["squawk"]], ["ring", "slate", "Emergency code, ended", ["squawk"]]],
    sea: [["ring", "red", "Attack at sea", ["ukmto"]], ["ring", "blue", "Other incident or advisory at sea", ["ukmto"]], ["dot", "red", "Chokepoint, traffic down by half or more", ["portwatch"]], ["dot", "amber", "Chokepoint, down by a fifth or more", ["portwatch"]], ["dot", "blue", "Chokepoint, near normal, and merchant ships", ["portwatch", "ships"]], ["dot", "amber", "Tankers", ["ships"]]],
    outages: [["area", "amber", "Internet outage (stronger when ongoing)", ["outages"]], ["dot", "amber", "Power, mobile, website or cloud outage, active", ["power", "cellular", "websites", "cloud"]], ["dot", "slate", "The same, ended", ["power", "cellular", "websites", "cloud"]], ["line", "slate", "Undersea cables", ["cables"]]],
    cyber: [["area", "amber", "Ransomware claims and reported attacks, 7 days (stronger with more)", ["cyber"]]],
    hazards: [["ring", "amber", "Earthquake in a watched area", ["quakes"]], ["ring", "slate", "Other earthquake, magnitude 4 or more", ["quakes"]], ["dot", "amber", "Disaster alert, orange", ["hazards"]], ["dot", "red", "Disaster alert, red, and fires seen from space", ["hazards", "firms"]], ["dot", "slate", "Disaster alert, green", ["hazards"]]],
    official: [["area", "red", "US travel advisory: do not travel", ["advisories"]], ["area", "amber", "US travel advisory: reconsider travel", ["advisories"]], ["ring", "amber", "US embassy alert, last 3 days"]],
  };
  function topicExtra(k) {
    const d = S.d, s = d.summary || {};
    if (k === "conflict") return `<div class="tiles">${tile(nf(s.events_24h), "map pins in 24 hours")}${tile(nf(s.events_6h), "in 6 hours")}${tile(S.fronts.length, "front lines drawn")}${tile(nf(s.thermal_corroborated), "pins matched by a satellite fire")}</div>` +
      stub("Russian losses and Taiwan daily counts", "Daily official tallies will sit here as two small charts.", ["losses", "pla"]) + stub("Analyst note on each pin", "The analyst's reading of a single event will show in its card.");
    if (k === "alerts") { const a = (d.alerts || {}).summary || {}, r = (d.alerts || {}).regions || {};
      return `<div class="tiles">${tile((a.ukraine || {}).n ?? "–", "regions in Ukraine")}${tile((a.russia || {}).n ?? "–", "regions in Russia")}${tile((a.israel || {}).sirens_now ?? "–", "sirens in Israel now")}${tile((a.us_embassies || {}).alerts_24h ?? "–", "US embassy alerts, 24 hours")}</div>` +
        ((r.threats || []).length ? `<section class="sec"><h2>Threats being tracked <small>alerts.in.ua</small></h2><ul class="changes">${r.threats.slice(0, 6).map((t) => `<li>${esc(t.msg || t.what)} <span class="muted">(${esc(A.ago(A.isoMs(t.at)))})</span></li>`).join("")}</ul></section>` : "") +
        stub("Shelter countdowns and early warnings in Israel", "Each alerted town's time to shelter and the all-clear will show here and on the map.", ["tzeva", "tzevalive"]) + `<p class="muted small" style="margin-top:10px">Not a safety service. If you are in an alerted area, follow the official alerts.</p>`; }
    if (k === "air") { const t = d.tfr || {}, q = d.squawk || {}, roles = s.mil_aircraft_by_role || {};
      return `<div class="tiles">${tile(nf(s.mil_aircraft), "military aircraft heard", ["mil"])}${tile(nf((t.by_status || {}).active), "US flight restrictions active", ["tfr"])}${tile(nf(q.count), "emergency codes now", ["squawk"])}${tile(nf(s.airspace_czib_active), "conflict-zone airspace warnings", ["czib"])}</div>` +
        (Object.keys(roles).length ? `<p class="muted small" style="margin-top:10px">By role: ${esc(Object.entries(roles).sort((a, b) => b[1] - a[1]).map(([r, n]) => `${n} ${r}`).join(", "))}.</p>` : "") +
        stub("GPS jamming", "A map of where aircraft reported degraded GPS over the last day.", ["gpsjam"]) + stub("Conflict-zone airspace warnings on the map", "The areas regulators warn airlines away from, as shapes.", ["czib"]) + stub("Aircraft photos and types legend", "A photo of the airframe and a colour per role.", ["mil"]); }
    if (k === "sea") { const cps = ((d.portwatch || {}).chokepoints || []).filter((c) => c.pinned || (c.avg7 || {}).total >= 20).slice(0, 8), st = (d.status || {}).feeds || {};
      return `<div class="tiles">${tile(nf(s.ukmto_incidents_7d), "incidents at sea, 7 days", ["ukmto"])}${tile(nf((d.ships || {}).count), "ships heard", ["ships"])}${tile(nf((s.listed_ships_heard || {}).heard_1h), "ships on a sanctions or watch list, last hour", ["ships"])}</div>` +
        (st.ships && !st.ships.ok ? `<div class="empty">The ship feed reported an error at its last run, so ship positions may be old.</div>` : "") +
        `<section class="sec"><h2>Chokepoints <small>ships a day, IMF PortWatch</small></h2>` + (cps.length ? `<table class="table"><thead><tr><th>Passage</th><th class="n">7-day average</th><th class="n">Against last year</th></tr></thead><tbody>${cps.map((c) => { const g = (c.change_vs_year_pct || {}).total;
          return `<tr><td>${esc(c.name)}</td><td class="n">${esc(c.avg7.total)}</td><td class="n">${g == null ? "–" : `<span class="state${g <= -50 ? " hot" : g <= -20 ? " warm" : ""}">${g > 0 ? "+" : ""}${g}%</span>`}</td></tr>`; }).join("")}</tbody></table>` : loading("portwatch")) + `</section>` +
        stub("Ship tracks, sanctions rings and satellite ship counts", "Tanker tracks, a ring on listed ships and the satellite count for seas with no receivers.", ["ships", "vessellists", "gfw"]); }
    if (k === "outages") { const o = s.internet_outages || {}, act = (n) => S.entries.filter((e) => e.sub === n && e.active).length;
      return `<div class="tiles">${tile(o.countries_with_outages ?? "–", "countries with internet outages", ["outages"])}${tile(d.power ? act("power") : "–", "power outages active", ["power"])}${tile(d.cellular ? act("cellular") : "–", "mobile network cuts active", ["cellular"])}${tile((d.cloud || !A.has("cloud")) && (d.websites || !A.has("websites")) ? act("cloud") + act("websites") : "–", "cloud and website incidents active", ["cloud", "websites"])}</div>` +
        stub("Internet routing drops", "Countries whose share of reachable networks fell sharply.", ["bgp"]); }
    if (k === "cyber") return (d.cyber ? `<p class="lede" style="margin-top:12px;font-size:15px">${esc(d.cyber.summary || "")}</p>` : loading("cyber")) + stub("Routing drops and denial-of-service detail", "Per-country routing losses and the list of sites being flooded.", ["bgp", "cyber"]);
    if (k === "hazards") { const h = d.hazards || {}, b = h.by_alert || {};
      return `<div class="tiles">${tile(d.quakes ? nf(d.quakes.count) : "–", "earthquakes, 48 hours", ["quakes"])}${tile(d.quakes ? nf(d.quakes.watch_count) : "–", "in watched areas", ["quakes"])}${tile(d.hazards ? nf((b.Orange || 0) + (b.Red || 0)) : "–", "orange or red disaster alerts", ["hazards"])}${tile(d.firms ? nf(d.firms.count) : "–", "fires seen from space", ["firms"])}</div>` +
        stub("Tsunami warnings and radiation readings", "Warning-centre bulletins and the radiation monitor network.", ["tsunami", "radiation"]); }
    if (k === "official") { const t = s.travel_advisories || {}, l4 = ((d.advisories || {}).items || []).filter((i) => i.level === 4).sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 6);
      return `<div class="tiles">${tile(t.level4 ?? "–", "countries: do not travel", ["advisories"])}${tile(t.level3 ?? "–", "countries: reconsider travel", ["advisories"])}${tile((((S.d.alerts || {}).summary || {}).us_embassies || {}).alerts_24h ?? "–", "US embassy alerts, 24 hours")}</div>` +
        (l4.length ? `<section class="sec"><h2>Do not travel <small>most recently updated</small></h2><table class="table"><tbody>${l4.map((i) => `<tr><td>${A.safeUrl(i.url) ? `<a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.country)}</a>` : esc(i.country)}</td><td class="n">${esc(i.date)}</td></tr>`).join("")}</tbody></table></section>` : "") +
        stub("US terror advisories and sanctions updates", "The national terrorism advisory bulletin and new sanctions listings.", ["ntas", "ofac"]); }
    return "";
  }
  function viewTopic(k) {
    const t = A.TOPICS.find((x) => x.k === k) || A.TOPICS[0], list = A.feed({ topic: k, noFilter: true, allGroups: false });
    const top = `<div class="view-top"><button type="button" class="btn back" data-act="page" data-v="">${ico("left")}Topics</button></div>
      <h1 class="head" style="margin-top:4px">${esc(t.name)}</h1><p class="muted">${esc(t.blurb)}</p>`;
    if (!A.topicOn(k)) return top + `<div class="empty">${NA}</div>`;
    return `${top}${topicExtra(k)}
      <section class="sec"><h2>On the map</h2><ul class="legend">${LEGEND[k].map(([shape, tone, label, feeds]) => (feeds && !A.hasAny(feeds) ? `<li class="off"><span class="sw ${shape}" style="--c:${COL.slate};opacity:0.35"></span>${esc(label)}. ${NA}</li>` : `<li><span class="sw ${shape}" style="--c:${COL[tone]}"></span>${esc(label)}</li>`)).join("")}</ul></section>
      <section class="sec"><h2>Latest <small>${nf(list.length)} entr${list.length === 1 ? "y" : "ies"}</small></h2>${list.length ? listHtml(list, 15, false).replace(/data-act="morerows">[^<]*</, 'data-act="nav" data-v="feed">Open in the feed<') : `<p class="muted">${(A.TOPIC_NEEDS[k] || []).some((n) => A.has(n) && !S.loaded.has(n) && !S.failed.has(n)) ? "Loading…" : "No dated entries for this topic."}</p>`}</section>`;
  }

  // ---------- More ----------
  const FEED_NAMES = { mymaps: "Source map (event pins)", wire: "News wire", telegram: "Telegram channels", official: "Official statements", ukmto: "Incidents at sea (UKMTO)", mil: "Military aircraft", ships: "Ships",
    front: "Front area in Ukraine (DeepState)", outages: "Internet outages", airalerts: "Air-raid alerts (Ukraine, Russia, Poland)", tzeva: "Sirens in Israel", tzevalive: "Sirens in Israel, live", embassy: "US embassy alerts",
    advisories: "US travel advisories", firms: "Fires seen from space", quakes: "Earthquakes", hazards: "Disaster alerts", cyber: "Cyber records", bgp: "Internet routing", cables: "Undersea cables", cellular: "Mobile networks",
    cloud: "Cloud services", websites: "Websites and apps", power: "Power outages", gpsjam: "GPS jamming", tfr: "US flight restrictions", squawk: "Aircraft emergency codes", portwatch: "Chokepoint traffic", gfw: "Satellite ship counts",
    czib: "Conflict-zone airspace warnings", gdelt: "World news index", geoconfirmed: "Geolocated footage (GeoConfirmed)", cir: "Verified incidents (CIR)", kinetic: "Iran strike reports (S2 Underground)", losses: "Russian losses", pla: "Taiwan daily counts",
    ntas: "US terror advisories", ofac: "US sanctions updates", radiation: "Radiation readings", tsunami: "Tsunami warnings", vessellists: "Ship watch lists" };
  function viewMore() {
    const st = (S.d.status || {}).feeds, wp = wallPref(), T = window.GTTheme;
    return `<div class="view-top"><h2 class="view-h">More</h2></div><div class="rows">
      <button type="button" class="row" data-act="page" data-v="analyst"><span class="disc plain">${ico("news")}</span><span class="r-main"><span class="r-title">Analyst picture</span><span class="r-meta">The full written picture: every region, indicators, risks and gaps</span></span><span class="r-end">${ico("right")}</span></button>
      <button type="button" class="row" data-act="page" data-v="sources"><span class="disc plain">${ico("signal")}</span><span class="r-main"><span class="r-title">Sources and their health</span><span class="r-meta">${st ? `${Object.values(st).filter((f) => f.ok && !f.stale).length} of ${Object.keys(st).length} sources working` : "How fresh each source is"}</span></span><span class="r-end">${ico("right")}</span></button></div>
      <section class="sec"><h2>Settings</h2>
        <div class="setting"><div><b>Times</b><p>Every time on the page, in one zone.</p></div><div class="segc" role="group" aria-label="Time zone"><button type="button" data-act="tz" data-v="et" aria-pressed="${S.zone === "et"}">Eastern</button><button type="button" data-act="tz" data-v="utc" aria-pressed="${S.zone === "utc"}">UTC</button></div></div>
        <div class="setting"><div><b>Wall display</b><p>Map, summary and newest entries, nothing to touch. It starts only when you turn it on here, or with ?wall=1 at the end of the address.</p></div><div class="segc" role="group" aria-label="Wall display">${[["on", "On"], ["off", "Off"]].map(([v, l]) => `<button type="button" data-act="wallpref" data-v="${v}" aria-pressed="${wp === v}">${l}</button>`).join("")}</div></div>
        ${T ? `<div class="setting"><div><b>Theme</b><p>How this page looks. The data is the same in every theme, and this device remembers the choice.</p></div><div class="chips" role="group" aria-label="Theme">${T.THEMES.map((t) => chip("theme", t.id, t.name, t.id === T.current)).join("")}</div></div>` : ""}
      </section>
      <section class="sec"><h2>About</h2><p class="muted">Ground Truth is a private watch floor built from open sources. This is the Atlas theme${T && T.version ? ", version " + esc(T.version) : ""}: a full-screen map with one panel. It reads the same live data as every other theme and does not change anything.</p></section>`;
  }
  function viewAnalyst() {
    const p = pic(); if (!p) return `<div class="view-top"><button type="button" class="btn back" data-act="page" data-v="">${ico("left")}More</button></div>` + loading("analysis");
    const at = A.isoMs(p.generated_at), z = (s) => esc(A.zText(s, at)), cls = (v) => (/present|up|high|rising/i.test(v) ? " warm" : "");
    return `<div class="view-top"><button type="button" class="btn back" data-act="page" data-v="">${ico("left")}More</button></div>
      <p class="eyebrow">Analyst picture, written ${esc(A.fmtDate(at))}, ${esc(A.fmtT(at))} (${esc(A.ago(at))}) from ${nf(p.events_considered)} events. Confidence: ${esc(p.confidence || "not stated")}. Written by a language model from the sources on this page; check anything that matters.</p>
      ${tensionHtml(p)}<h1 class="head">${z(p.headline)}</h1><p class="lede">${z(p.bluf)}</p>
      <section class="sec"><h2>Region by region</h2><div class="rows">${(p.theatres || []).map((t) => `<button type="button" class="row" data-act="page" data-v="region:${esc(t.theatre)}"><span class="disc plain" style="color:${tcol(t.status)}">${esc(t.status)}</span>
        <span class="r-main"><span class="r-title">${esc(A.regionName(t.theatre) || t.theatre)}</span><span class="r-meta">${esc(t.trend)}</span></span><span class="r-end">${ico("right")}</span></button>`).join("")}</div></section>
      ${(p.cross_theatre || []).length ? `<section class="sec"><h2>Links between regions</h2><ul class="changes">${p.cross_theatre.map((c) => `<li>${z(c)}</li>`).join("")}</ul></section>` : ""}
      ${(p.indicators || []).length ? `<section class="sec"><h2>Warning signs</h2><table class="table"><tbody>${p.indicators.map((i) => `<tr><td><b>${esc(i.indicator)}</b><div class="muted small">${z(i.note)}</div></td><td class="n"><span class="state${cls(i.state)}">${esc(i.state)}</span></td></tr>`).join("")}</tbody></table></section>` : ""}
      ${(p.market_risk || []).length ? `<section class="sec"><h2>Market risks</h2><table class="table"><tbody>${p.market_risk.map((m) => `<tr><td><b>${esc(String(m.theme).replace(/_/g, " "))}</b><div class="muted small">${z(m.why)}</div></td><td class="n"><span class="state${cls(m.direction)}">${esc(m.direction)}</span></td></tr>`).join("")}</tbody></table></section>` : ""}
      ${(p.changes_since_last || []).length ? `<section class="sec"><h2>What changed</h2><ul class="changes">${p.changes_since_last.map((c) => `<li>${z(c)}</li>`).join("")}</ul></section>` : ""}
      ${(p.gaps || []).length ? `<section class="sec"><h2>What we cannot see</h2><ul class="changes">${p.gaps.map((c) => `<li>${z(c)}</li>`).join("")}</ul></section>` : ""}`;
  }
  function viewRegion(k) {
    const p = pic(), t = p && (p.theatres || []).find((x) => x.theatre === k), at = p ? A.isoMs(p.generated_at) : NaN, z = (s) => esc(A.zText(s, at));
    const list = A.feed({ topic: "all", noFilter: true }).filter((e) => e.region === k), n24 = ((S.d.summary || {}).events_24h_by_theatre || {})[k] || 0;
    return `<div class="view-top"><button type="button" class="btn back" data-act="back">${ico("left")}Back</button></div><h1 class="head" style="margin-top:4px">${esc(A.regionName(k) || k)}</h1>` +
      (t ? `<div class="tension" style="--tc:${tcol(t.status)}"><div class="t-num" aria-hidden="true">${esc(t.status)}<span>/10</span></div><div class="t-side"><div class="t-label">Analyst rating ${esc(t.status)} of 10<span>, ${esc(t.trend)}</span></div><div class="muted small">${nf(n24)} map pin${n24 === 1 ? "" : "s"} in 24 hours</div></div></div>
        <p class="lede" style="margin-top:12px">${z(t.summary)}</p>
        ${(t.key_developments || []).length ? `<section class="sec"><h2>Key developments</h2><ul class="changes">${t.key_developments.map((c) => `<li>${z(c)}</li>`).join("")}</ul></section>` : ""}
        ${(t.watch || []).length ? `<section class="sec"><h2>What to watch for</h2><ul class="changes">${t.watch.map((c) => `<li>${z(c)}</li>`).join("")}</ul></section>` : ""}` : `<p class="muted">The analyst picture has no note for this region.</p>`) +
      `<section class="sec"><h2>Latest here <small>${nf(list.length)} entr${list.length === 1 ? "y" : "ies"}</small></h2>${list.length ? listHtml(list, 20, false).replace(/data-act="morerows">[^<]*</, `data-act="regionfeed" data-v="${esc(k)}">Open in the feed<`) : `<p class="muted">No entries placed in this region.</p>`}</section>`;
  }
  function viewSources() {
    const st = (S.d.status || {}).feeds, s = S.d.summary || {};
    let h = `<div class="view-top"><button type="button" class="btn back" data-act="page" data-v="">${ico("left")}More</button></div><h1 class="head" style="margin-top:4px">Sources and their health</h1>`;
    if (!st) return h + loading("status");
    const list = Object.entries(st).map(([k, f]) => ({ k, f, rank: !f.ok ? 0 : f.stale ? 1 : 2, name: FEED_NAMES[k] || k })).sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
    const bad = list.filter((x) => x.rank === 0).length, stale = list.filter((x) => x.rank === 1).length;
    h += `<p class="lede">${list.length - bad - stale} of ${list.length} sources are working${bad ? `, ${bad} reported an error` : ""}${stale ? `, ${stale} ${stale === 1 ? "is" : "are"} late` : ""}.</p>
      <table class="table" style="margin-top:12px"><thead><tr><th>Source</th><th class="n">Last run</th></tr></thead><tbody>${list.map(({ f, rank, name }) => `<tr><td><span class="lvl" style="--c:${rank === 0 ? "var(--red)" : rank === 1 ? "var(--amber)" : "#7fe3a8"}"></span>${esc(name)}
        ${rank === 0 ? `<div class="muted small">Error at its last run${f.error ? ": " + esc(String(f.error).slice(0, 120)) : ""}</div>` : rank === 1 ? `<div class="muted small">Late: it normally runs every ${esc(Math.round((f.every || 0) / 60))} min</div>` : ""}</td><td class="n">${f.at ? esc(A.ago(A.isoMs(f.at))) : "never"}</td></tr>`).join("")}</tbody></table>`;
    const ext = (u, t) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`;
    return h + `<section class="sec"><h2>Credits</h2><p class="muted small">Verified pins: ${ext("https://geoconfirmed.org", "GeoConfirmed")} and ${ext("https://eyesonrussia.org", "CIR Eyes on Russia")} (research use; not on the public mirror),
      and S2 Underground's Iran kinetic events map (${ext("https://creativecommons.org/licenses/by-nc-sa/4.0/", "CC BY-NC-SA 4.0")}, layout changed).</p>
      <p class="muted small" style="margin-top:8px">The credits and licences of the other sources are not in this theme yet. They are in the Classic theme.</p>${openClassic}</section>
      ${s.version ? `<p class="muted small" style="margin-top:12px">Server version ${esc(s.version)}.</p>` : ""}`;
  }

  // ---------- search ----------
  function viewSearch() {
    const q = S.q.trim().toLowerCase(), places = [];
    Object.entries(A.REGIONS).forEach(([k, v]) => { if (v[0].toLowerCase().includes(q)) places.push({ act: "page", v: "region:" + k, title: v[0], meta: "Region" }); });
    S.fronts.forEach((f) => { if ((f.title + " " + f.place).toLowerCase().includes(q)) places.push({ act: "sel", id: f.id, title: f.title, meta: f.kind + (f.place ? " · " + f.place : "") }); });
    ((S.d.portwatch || {}).chokepoints || []).forEach((c) => { if (c.name.toLowerCase().includes(q)) places.push({ act: "place", v: `${c.lon},${c.lat},5`, title: c.name, meta: "Chokepoint" }); });
    S.cc.forEach((c) => { if (c.name.toLowerCase().includes(q)) places.push({ act: "place", v: `${c.ll[0]},${c.ll[1]},4.6`, title: c.name, meta: "Country" }); });
    const list = A.feed({ topic: "all", allGroups: true, noFilter: true, q });
    return `<div class="view-top"><h2 class="view-h">Results for “${esc(S.q.trim())}”<small>${places.length} place${places.length === 1 ? "" : "s"}, ${nf(list.length)} entr${list.length === 1 ? "y" : "ies"} across every source loaded</small></h2><button type="button" class="btn" data-act="clearq">Clear</button></div>` +
      (places.length ? `<section class="sec" style="margin-top:10px"><h2>Places</h2><div class="rows">${places.slice(0, 6).map((p) => `<button type="button" class="row" data-act="${p.act}" ${p.id ? `data-id="${p.id}"` : `data-v="${esc(p.v)}"`}><span class="disc plain">${ico("pin")}</span><span class="r-main"><span class="r-title">${esc(p.title)}</span><span class="r-meta">${esc(p.meta)}</span></span></button>`).join("")}</div></section>` : "") +
      `<section class="sec"><h2>Entries</h2>${list.length ? listHtml(list, UI.limit, false) : `<p class="muted">No entry matches. Sources for a topic load when that topic is first picked.</p>`}</section>`;
  }

  // ---------- detail ----------
  function detailHtml(c, back) {
    const ll = c.ll || (S.cc.get(c.cc) || {}).ll, url = A.safeUrl(c.url);
    return `<div class="d-top">${disc(c)}<div style="min-width:0;flex:1"><div class="d-kind">${esc(c.label || c.kind)}</div><h2 class="d-title" id="dtitle" tabindex="-1">${esc(c.title)}</h2></div>
      ${back ? "" : `<button type="button" class="d-close" data-act="close" aria-label="Close this card">${ico("close")}</button>`}</div>
      <p class="d-meta">${[c.place ? `<b>${esc(c.place)}</b>` : "", c.src ? esc(c.src) : ""].filter(Boolean).join(" · ")}${c.ts ? `${c.place || c.src ? "<br>" : ""}${esc(A.when(c))}` : ""}</p>
      ${c.summary ? `<p class="d-sum">${esc(String(c.summary).slice(0, 700))}${String(c.summary).length > 700 ? "…" : ""}</p>` : ""}
      ${(c.facts || []).length ? `<dl class="d-facts">${c.facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>` : ""}
      ${!c.ll && ll ? `<p class="d-note">Placed by country from its text, not at an exact spot: the dashed ring marks ${esc(A.ccName(c.cc))}.</p>` : !ll ? `<p class="d-note">${c.cc && !A.has("news_geo") ? "The place is not known on this copy, so the map does not move." : "This entry names no place, so the map does not move."}</p>` : ""}
      ${c.note ? `<p class="d-note">${esc(c.note)}</p>` : ""}
      <div class="d-acts">${url ? `<a class="btn primary" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(c.urlLabel || "Open the source")}${ico("out")}</a>` : ""}
        ${ll ? `<button type="button" class="btn" data-act="showmap">${ico("pin")}Show on the map</button>` : ""}${c.region && !c.front ? `<button type="button" class="btn" data-act="page" data-v="region:${esc(c.region)}">${esc(A.regionName(c.region))}</button>` : ""}${c.classic ? `<button type="button" class="btn" data-act="classic">Open Classic</button>` : ""}</div>`;
  }
  function renderDetail() {
    const el = $("detail");
    if (UI.mode !== "desk" || !S.sel) { el.hidden = true; el.innerHTML = ""; return; }
    el.hidden = false; el.innerHTML = detailHtml(S.sel);
  }
  A.select = (card, opt) => {
    const o = opt || {}; S.sel = card;
    const ll = A.mark(card);
    if (UI.mode === "wall") return;
    if (UI.mode === "phone") { UI.detail = true; if (UI.sheet !== "half") setSheet("half"); }
    if (ll && o.fromMap && UI.mode === "desk") { const pt = A.map.project(ll); if (pt.x > innerWidth - 420 && pt.y > 110) A.map.panBy([pt.x - (innerWidth - 470), 0], { duration: A.REDUCED ? 0 : 400 }); }
    else if (ll) { if (card.front && !o.fromMap) A.fit(card.bbox, 7.2); else A.flyTo(ll, o.fromMap ? A.map.getZoom() : card.ll ? Math.max(A.map.getZoom(), 5.4) : Math.max(Math.min(A.map.getZoom(), 5), 3.8)); }
    render(); renderDetail();
    if (o.fromMap || UI.mode === "phone") { const t = $("dtitle"); if (t) t.focus({ preventScroll: true }); }
  };
  function closeDetail() { S.sel = null; UI.detail = false; A.mark(null); render(); renderDetail(); }

  // ---------- render the sheet ----------
  let lastKey = "";
  function render() {
    if (UI.mode === "wall") { renderWall(); return; }
    const searching = S.q.trim().length >= 2;
    const key = UI.detail && S.sel ? "detail:" + S.sel.id : searching ? "search" : S.dest + ":" + (S.page || "");
    const act = document.activeElement, fk = act && body.contains(act) ? (act.dataset.act || "") + "|" + (act.dataset.id || act.dataset.v || "") : null, top = body.scrollTop;
    let h;
    if (UI.detail && S.sel) h = `<div class="view-top"><button type="button" class="btn back" data-act="close">${ico("left")}Back</button></div>` + detailHtml(S.sel, true);
    else if (searching) h = viewSearch();
    else if (S.page && S.page.startsWith("region:")) h = viewRegion(S.page.slice(7));
    else if (S.dest === "now") h = viewNow();
    else if (S.dest === "feed") h = viewFeed();
    else if (S.dest === "topics") h = S.page ? viewTopic(S.page) : viewTopics();
    else h = S.page === "analyst" ? viewAnalyst() : S.page === "sources" ? viewSources() : viewMore();
    body.innerHTML = h;
    body.scrollTop = key === lastKey ? top : 0; lastKey = key;
    if (fk) { const [a, v] = fk.split("|"); const el = [...body.querySelectorAll(`[data-act="${a}"]`)].find((x) => (x.dataset.id || x.dataset.v || "") === v); if (el) el.focus({ preventScroll: true }); }
    const fresh = S.lastSeen ? A.feed({ topic: "all", noFilter: true }).filter((e) => e.ts > S.lastSeen).length : 0;
    const navHtml = (withIcon) => NAV.map(([k, name, ic]) => `<button type="button" data-act="nav" data-v="${k}"${S.dest === k && !searching ? ' aria-current="page"' : ""}>${withIcon ? ico(ic) : ""}<span>${name}</span>${k === "feed" && fresh && S.dest !== "feed" ? `<span class="badge" aria-label="${fresh} new">${fresh > 99 ? "99+" : fresh}</span>` : ""}</button>`).join("");
    $("seg").innerHTML = navHtml(false); $("tabbar").innerHTML = navHtml(true);
    $("pills").innerHTML = A.TOPICS.filter((t) => A.topicOn(t.k)).map((t) => `<button type="button" class="pill" data-act="topic" data-v="${t.k}" aria-pressed="${S.topic === t.k}">${t.k === "all" ? "" : ico(t.icon)}${esc(t.name)}</button>`).join("");
    $("live").className = "b-live " + (S.net === "ok" ? "ok" : S.net === "loading" ? "" : "bad"); $("livet").textContent = netWord();
    $("qclear").hidden = !S.q;
  }
  let rt = null;
  const renderSoon = () => { clearTimeout(rt); rt = setTimeout(() => { render(); if (S.sel && S.byId.has(S.sel.id)) S.sel = S.byId.get(S.sel.id); }, 80); };
  A.on("data", renderSoon);
  A.on("zone", () => { tick(); render(); renderDetail(); });

  function setTopic(k) {
    S.topic = k; UI.limit = 60; A.need(A.TOPIC_NEEDS[k]); A.emit("view"); render();
    const pill = document.querySelector(`.pill[data-v="${k}"]`); if (pill && pill.scrollIntoView) pill.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  const pageStack = [];
  function go(dest, page) { if (S.page && page && page !== S.page) pageStack.push([S.dest, S.page]); S.dest = dest; S.page = page || null; UI.detail = false; UI.limit = 60; render(); body.scrollTop = 0; }

  // ---------- actions ----------
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest && ev.target.closest("[data-act]"); if (!b || b.disabled) return;
    const act = b.dataset.act, v = b.dataset.v;
    if (act === "nav") { if (S.q) { S.q = ""; $("q").value = ""; } if (UI.mode === "phone" && (UI.sheet === "peek" || (S.dest === v && !S.page && !UI.detail))) setSheet(UI.sheet === "half" && S.dest === v ? "full" : "half"); pageStack.length = 0; go(v, null); }
    else if (act === "topic") setTopic(v);
    else if (act === "topicpage") { setTopic(v); go("topics", v); }
    else if (act === "topicgo") { setTopic(v); go("topics", v); }
    else if (act === "alertsat") { setTopic("alerts"); go("topics", "alerts"); if (v === "israel") A.flyTo([35, 31.6], 6.3); else if (v === "russia") A.flyTo([42, 50], 4.2); else A.region(v); }
    else if (act === "sel") { const c = S.byId.get(b.dataset.id); if (c) A.select(c); }
    else if (act === "page") { if (v && v.startsWith("region:")) { const k = v.slice(7); pageStack.push([S.dest, S.page]); S.page = v; UI.detail = false; if (S.sel) { S.sel = null; A.mark(null); renderDetail(); } if (S.q) { S.q = ""; $("q").value = ""; } A.region(k); render(); body.scrollTop = 0; }
      else { pageStack.length = 0; go(v === "analyst" || v === "sources" ? "more" : S.dest, v || null); } }
    else if (act === "back") { const p = pageStack.pop() || [S.dest === "now" ? "now" : S.dest, null]; S.dest = p[0]; S.page = p[1]; render(); body.scrollTop = 0; }
    else if (act === "regionfeed") { S.region = v; S.topic = "all"; A.emit("view"); UI.filterOpen = true; pageStack.length = 0; go("feed", null); }
    else if (act === "filter") { UI.filterOpen = !UI.filterOpen; render(); }
    else if (act === "region") { S.region = v; UI.limit = 60; if (v !== "all") A.region(v); render(); }
    else if (act === "hours") { S.hours = +v; UI.limit = 60; A.emit("view"); render(); }
    else if (act === "group") { if (S.groups.has(v)) S.groups.delete(v); else { S.groups.add(v); A.need({ air: A.TOPIC_NEEDS.air, outages: ["power", "cellular", "websites", "cloud", "outages", "outages_geo"], cyber: ["cyber"], hazards: ["quakes", "hazards"] }[v]); } UI.limit = 60; render(); }
    else if (act === "morerows") { UI.limit += 60; render(); }
    else if (act === "lede") { UI.ledeOpen = !UI.ledeOpen; render(); }
    else if (act === "tz") A.setZone(v);
    else if (act === "theme" || act === "classic") { if (window.GTTheme) GTTheme.go(act === "classic" ? "classic" : v); }
    else if (act === "wallpref") { LS.set("wall", v === "on" ? "on" : "off"); if (new URLSearchParams(location.search).has("wall")) history.replaceState(null, "", location.pathname); layout(); render(); }
    else if (act === "close") closeDetail();
    else if (act === "showmap") { const c = S.sel, ll = c && (c.ll || (S.cc.get(c.cc) || {}).ll); if (UI.mode === "phone") setSheet("peek"); if (ll) { if (c.front) A.fit(c.bbox, 7.2); else A.flyTo(ll, c.ll ? Math.max(A.map.getZoom(), 6.2) : 4.2); } }
    else if (act === "place") { const [x, y, z] = v.split(",").map(Number); A.flyTo([x, y], z); if (UI.mode === "phone") setSheet("peek"); }
    else if (act === "clearq") { S.q = ""; $("q").value = ""; render(); }
    else if (act === "exitwall") { LS.set("wall", "off"); history.replaceState(null, "", location.pathname); layout(); }
  });
  $("q").addEventListener("input", (e) => { S.q = e.target.value; UI.limit = 60; if (UI.mode === "phone" && UI.sheet === "peek" && S.q.trim().length >= 2) setSheet("half"); if (UI.mode === "desk" && UI.collapsed && S.q.trim().length >= 2) collapse(false); UI.detail = false; render(); });
  $("searchform").addEventListener("submit", (e) => { e.preventDefault(); $("q").blur(); });
  $("qclear").addEventListener("click", () => { S.q = ""; $("q").value = ""; render(); $("q").focus(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { if (S.sel) closeDetail(); else if (S.q) { S.q = ""; $("q").value = ""; render(); } }
    else if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) { e.preventDefault(); $("q").focus(); }
  });

  // ---------- desk: resize and collapse the panel ----------
  function collapse(on) { UI.collapsed = on; LS.set("collapsed", on ? "1" : "0"); layout(); sheet.inert = on; A.map.easeTo({ padding: A.pad(), duration: A.REDUCED ? 0 : 300 }); (on ? $("reopen") : $("collapse")).focus(); }
  $("collapse").addEventListener("click", () => collapse(true)); $("reopen").addEventListener("click", () => collapse(false));
  const setW = (w) => { UI.panelW = Math.min(640, Math.max(340, Math.round(w))); root.style.setProperty("--panel-w", UI.panelW + "px"); LS.set("panel", UI.panelW); $("resize").setAttribute("aria-valuenow", UI.panelW); };
  const rz = $("resize"); rz.setAttribute("aria-valuemin", 340); rz.setAttribute("aria-valuemax", 640); rz.setAttribute("aria-valuenow", UI.panelW);
  rz.addEventListener("pointerdown", (e) => { rz.setPointerCapture(e.pointerId); root.classList.add("resizing"); const move = (m) => setW(m.clientX - 12);
    const up = () => { rz.removeEventListener("pointermove", move); rz.removeEventListener("pointerup", up); root.classList.remove("resizing"); }; rz.addEventListener("pointermove", move); rz.addEventListener("pointerup", up); });
  rz.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft") setW(UI.panelW - 20); else if (e.key === "ArrowRight") setW(UI.panelW + 20); });
  rz.addEventListener("dblclick", () => setW(420));

  // ---------- phone: drag the sheet between three heights ----------
  const grab = $("grab"); let drag = null;
  grab.addEventListener("pointerdown", (e) => { drag = { y: e.clientY, h: sheet.getBoundingClientRect().height, moved: false }; grab.setPointerCapture(e.pointerId); });
  grab.addEventListener("pointermove", (e) => { if (!drag) return; const dy = drag.y - e.clientY; if (Math.abs(dy) > 6) drag.moved = true; if (!drag.moved) return;
    sheet.classList.add("dragging"); drag.now = Math.max(96, Math.min(sheetPx("full"), drag.h + dy)); root.style.setProperty("--sheet-h", drag.now + "px"); sheet.classList.remove("peek"); });
  const endDrag = () => { if (!drag) return; sheet.classList.remove("dragging");
    if (drag.moved) { const h = drag.now, near = ["peek", "half", "full"].sort((a, b) => Math.abs(sheetPx(a) - h) - Math.abs(sheetPx(b) - h))[0]; setSheet(near); grab.dataset.dragged = "1"; setTimeout(() => { delete grab.dataset.dragged; }, 50); } drag = null; };
  grab.addEventListener("pointerup", endDrag); grab.addEventListener("pointercancel", endDrag);
  grab.addEventListener("click", () => { if (grab.dataset.dragged) return; setSheet(UI.sheet === "peek" ? "half" : UI.sheet === "half" ? "full" : "half"); });
  grab.addEventListener("keydown", (e) => { const o = ["peek", "half", "full"], i = o.indexOf(UI.sheet); if (e.key === "ArrowUp" && i < 2) setSheet(o[i + 1]); else if (e.key === "ArrowDown" && i > 0) setSheet(o[i - 1]); });

  // ---------- clock ----------
  function tick() { const n = Date.now(); $("clock").textContent = A.fmtT(n) + (S.zone === "utc" ? "" : " " + A.zoneAbbr()); if (UI.mode === "wall") { const c = $("wclock"); if (c) c.innerHTML = wallClock(); } }
  $("clock").addEventListener("click", () => A.setZone(S.zone === "utc" ? "et" : "utc"));
  setInterval(tick, 15000);

  // ---------- wall ----------
  const wallClock = () => { const n = Date.now(); return `<span>${esc(A.fmtDate(n))}</span><b>${esc(A.fmtT(n))}${S.zone === "utc" ? "" : " " + esc(A.zoneAbbr())}</b>`; };
  // the wall lists what bears on conflict: map pins, sea incidents, official statements, and wire items the server filed under a conflict, sea, air, outage or cyber category
  const wallList = () => S.entries.filter((e) => e.group === "pins" || e.group === "official" || e.group === "sea" || (e.group === "wire" && e.topics.length)).slice(0, 5);
  function renderWall() {
    const p = pic(), ar = alertRows(), list = wallList(), s = ((S.d.alerts || {}).summary) || {};
    $("wnow").innerHTML = `<div class="w-clock" id="wclock">${wallClock()}</div>` + (p ? tensionHtml(p) + `<h1 class="w-head">${esc(A.zText(p.headline, A.isoMs(p.generated_at)))}</h1><p class="w-bluf">${esc(A.zText(p.bluf, A.isoMs(p.generated_at)))}</p>` : `<p class="w-bluf">${S.failed.has("analysis") ? "The analyst picture is not available right now." : "Loading…"}</p>`) +
      (ar ? `<div class="w-alerts">${[[(s.ukraine || {}).n, "regions in Ukraine under air-raid alert", (s.ukraine || {}).red ? "var(--red)" : "var(--amber)"], [(s.russia || {}).n, "regions in Russia under air-raid alert", "var(--amber)"], [(s.israel || {}).sirens_now, "sirens sounding in Israel", "var(--red)"], [(s.us_embassies || {}).alerts_24h, "US embassy alerts in 24 hours", "var(--amber)"]]
        .map(([n, l, c]) => `<div class="w-alert" style="--c:${n ? c : "var(--text-2)"}"><b>${n == null ? "–" : nf(n)}</b><span>${l}</span></div>`).join("")}</div>` : "");
    $("wlist").innerHTML = `<h2><span>Newest</span><span>${esc(netWord())}</span></h2>` + (list.length ? list.map((e, i) => `<div class="w-item${i === UI.wallI ? " on" : ""}" data-w="${i}">${disc(e)}<div class="r-main"><div class="r-title">${esc(e.title)}</div><div class="r-meta">${metaOf(e)}</div></div></div>`).join("") : `<p class="w-foot">Loading…</p>`) +
      (S.fronts[0] ? `<p class="w-foot">Busiest front: ${esc(S.fronts[0].title)}, ${S.fronts[0].n72} pins nearby in 72 hours.</p>` : "");
    // the bottom line takes the room that is left, in whole lines
    const b = $("wnow").querySelector(".w-bluf"); if (b) { b.style.webkitLineClamp = "unset"; const lh = parseFloat(getComputedStyle(b).lineHeight) || 36; b.style.webkitLineClamp = String(Math.max(2, Math.floor(b.clientHeight / lh))); b.style.maxHeight = Math.max(2, Math.floor(b.clientHeight / lh)) * lh + "px"; }
  }
  let wt = null;
  function wallStep() {
    const list = wallList(); if (!list.length) return;
    UI.wallI = (UI.wallI + 1) % (list.length + 1);
    document.querySelectorAll(".w-item").forEach((el, i) => el.classList.toggle("on", i === UI.wallI));
    if (UI.wallI === list.length) { A.mark(null); if (!A.REDUCED) A.map.easeTo({ center: [30, 30], zoom: 1.9, padding: A.pad(), duration: 3000 }); return; }  // one beat on the whole world
    const e = list[UI.wallI], ll = A.mark(e);
    if (ll && !A.REDUCED) A.map.easeTo({ center: ll, zoom: e.ll ? 4.6 : 3.4, padding: A.pad(), duration: 3000 });
  }
  function startWall() { stopWall(); UI.wallI = -1; A.map.jumpTo({ center: [30, 30], zoom: 1.9, padding: A.pad() }); wt = setInterval(wallStep, 9000); setTimeout(wallStep, 2500); }
  function stopWall() { clearInterval(wt); wt = null; A.mark(null); const x = $("exitwall"); if (x) x.remove(); }
  // A wall has no touch; a desk user who lands here gets a way out after any click or key.
  const offerExit = () => { if (UI.mode !== "wall" || $("exitwall")) return; const b = document.createElement("button"); b.id = "exitwall"; b.type = "button"; b.className = "btn primary"; b.dataset.act = "exitwall"; b.textContent = "Leave the wall display";
    b.style.cssText = "position:fixed;z-index:20;left:50%;bottom:28px;transform:translateX(-50%);font-size:20px;padding:0 24px;min-height:56px"; document.body.appendChild(b); setTimeout(() => b.remove(), 8000); };
  document.addEventListener("pointerdown", offerExit); document.addEventListener("keydown", offerExit);

  // ---------- last seen ----------
  const stamp = () => LS.set("seen", Date.now());
  addEventListener("pagehide", stamp); document.addEventListener("visibilitychange", () => { if (document.hidden) stamp(); });

  // ---------- version and theme button (themes/switch.js): beside and under the status light ----------
  if (window.GTTheme) { $("ver").textContent = GTTheme.version ? "v" + GTTheme.version : ""; GTTheme.mount($("themebtn")); }

  // ---------- go ----------
  UI.mode = modeNow(); if (UI.mode === "phone") setSheet("half");
  layout(); tick(); render(); if (UI.mode === "wall") startWall(); else A.map.jumpTo({ center: [30, 34], zoom: UI.mode === "phone" ? 1.6 : 2.4, padding: A.pad() });
  sheet.inert = UI.mode === "desk" && UI.collapsed;
  A.UI = UI; A.setSheet = setSheet; A.render = render; A.go = go; A.setTopic = setTopic;
  A.start(UI.mode === "wall");
})();
