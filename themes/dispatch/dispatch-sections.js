/* Ground Truth 1.7.0, theme "Dispatch": the section pages (Conflict, Air, Sea, Outages and cyber,
   Hazards, Official, Analysis, Sources). Each is a plain page of ruled blocks. A block this theme does not fill yet
   says so and offers the Classic theme, which has it. */
(() => {
  "use strict";
  const G = window.GT2, { S, $, esc, nf } = G;
  const link = (u, t) => (G.httpUrl(u) ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${t}</a>` : t);
  const block = (title, body, wide) => `<section class="block${wide ? " wide" : ""}"><h2>${title}</h2>${body}</section>`;
  const rows = (items) => `<ul class="rows">${items.join("")}</ul>`;
  // A block this theme does not fill yet. `feeds` are the feeds the Classic theme fills it from: on a copy that carries
  // none of them the Classic theme has nothing either, so the block says so and offers no button.
  const placeholder = (name, what, ...feeds) => (feeds.length && feeds.every(G.absent) ? `<p class="none">${G.NOT_HERE}</p>` : `<div class="placeholder"><b>${name}</b><span>${what}</span><em>Not in this theme yet. It is in the Classic theme.</em><button type="button" class="btn" data-classic>Open Classic</button></div>`);
  const wait = (name) => `<p class="none">${G.absent(name) ? G.NOT_HERE : S.failed[name] ? "This feed could not be loaded." : "Loading"}</p>`;
  const tm = (iso) => { const ms = G.isoMs(iso); return ms ? `${esc(G.when(ms))} ${G.zlabel()}` : ""; };
  const pill = (txt, cls) => `<span class="pill ${cls}">${esc(txt)}</span>`;
  const D = (d) => esc(G.fmtDate(String(d || "").replace(/\//g, "-")));   // a date with no time, as "22 Nov"
  let regionNames = null; try { regionNames = new Intl.DisplayNames(["en"], { type: "region" }); } catch (e) { /* older browser: the code is shown */ }
  const country = (c) => { try { return (regionNames && regionNames.of(c)) || c; } catch (e) { return c; } };
  const cap = (t) => { t = String(t || ""); return t.charAt(0).toUpperCase() + t.slice(1); };
  const ukText = (t) => String(t || "").replace(/^.*?Incident Time:\s*\d{3,4}\s*UTC\s*/i, "").replace(/^UKMTO (WARNING|ADVISORY)[^-]*-\s*/i, "");
  const cut = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, "") + "…" : s; };

  const PAGES = {
    conflict: { title: "Conflict", stand: "The fighting, theatre by theatre: the analyst’s notes, the front lines on the map and the air-raid alerts in force.", feeds: [] },
    air: { title: "Air", stand: "Military aircraft heard on open receivers, GPS interference and restricted airspace.", feeds: ["mil", "gpsjam", "tfr"] },
    sea: { title: "Sea", stand: "Attacks and incidents at sea, traffic through the chokepoints and the ships being heard.", feeds: ["ukmto", "portwatch", "ships"] },
    outages: { title: "Outages and cyber", stand: "Internet outages in the watched countries and the cyber picture. Power, mobile, web and cable monitors have a place here.", feeds: ["outages", "cyber"] },
    hazards: { title: "Hazards", stand: "Earthquakes, disaster alerts and fires seen from space.", feeds: ["quakes", "hazards"] },
    official: { title: "Official statements", stand: "What governments and militaries have said on the record: statements, embassy security alerts and travel advisories.", feeds: ["official", "advisories"] },
    analysis: { title: "The analyst picture", stand: "The full written picture behind the front-page lead: how tense, what changed, what to watch and what cannot be seen.", feeds: [] },
    sources: { title: "Sources", stand: "Every source the page reads, and whether it is reporting on time.", feeds: [] },
  };

  // ---------- Conflict ----------
  function conflict() {
    const pic = (S.analysis || {}).picture, s = S.summary || {}, by = s.events_24h_by_theatre || {}, al = (S.alerts || {}), reg = al.regions || {}, sm = al.summary || {};
    const ths = pic && pic.theatres ? pic.theatres.map((t) => {
      const n = Number(t.status), li = (a) => (a || []).map((x) => `<li>${esc(x)}</li>`).join("");
      return `<article class="th-block" id="th-${esc(t.theatre)}"><h3>${esc(G.thName(t.theatre) || t.theatre)}</h3>
        <p class="th-lv lv-${G.level(n)}"><b>${esc(n)}</b>/10 <span>${esc(t.trend || "")}</span><em>${G.plural(by[t.theatre] || 0, "event")} pinned in 24 hours</em></p>
        <p class="th-sum">${esc(G.zText(cap(String(t.summary || "").replace(/^Evidence:\s*/, "")), G.isoMs(pic.generated_at)))}</p>
        <div class="th-cols"><div><h4>Key developments</h4><ul>${li(t.key_developments) || "<li>None listed.</li>"}</ul></div><div><h4>Watch for</h4><ul>${li(t.watch) || "<li>Nothing listed.</li>"}</ul></div></div></article>`;
    }).join("") : `<p class="none">${S.failed.analysis ? "The analyst picture could not be loaded." : "Loading"}</p>`;
    const fr = (G.fronts ? G.fronts() : []);
    const fronts = fr.length ? rows(fr.map((f) => `<li><span class="r-n">${G.plural(f.n72, "pin")} nearby in 72 h</span><span class="r-t">${esc(f.name)}</span><span class="r-m">${esc(G.frontKind[f.kind][0])} · ${esc(f.where || "")} · about ${nf(Math.round(f.km))} km · ${nf(f.n24)} in 24 h</span></li>`))
      + `<p class="muted">Lines are drawn by the source map’s curator and move only when redrawn. <a href="#/map?topic=conflict&amp;c=34.5,48.6&amp;z=5.4">See them on the map</a>.</p>`
      : `<p class="none">${S.events ? "No front line is drawn on the source map." : "Loading"}</p>`;
    const lv = (r) => pill(r.level || "alert", r.level === "red" ? "red" : "amber");
    const regs = (reg.regions || []).filter((r) => r.kind === "alert"), ua = regs.filter((r) => r.c === "UA"), ru = regs.filter((r) => r.c === "RU"), il = sm.israel || {};
    const regRows = (list) => rows(list.map((r) => `<li><span class="r-n">${lv(r)}</span><b>${esc(r.en || r.name)}</b> <span class="muted">${r.duration ? "for " + esc(r.duration) : ""}</span></li>`));
    const alerts = S.alerts ? `<p class="lede"><span class="fig-big">${nf(ua.length)}</span>regions of Ukraine under air-raid alert${ru.length ? `, ${nf(ru.length)} in Russia` : ""}.</p>
      <p>${il.sirens_now ? `<b>${nf(il.sirens_now)} sirens are sounding in Israel.</b>` : "No sirens are sounding in Israel."} ${il.last_alert ? "" : "No alert there in the last 24 hours."}</p>
      ${ua.length ? regRows(ua) : ""}${ru.length ? `<p class="muted" style="margin-top:10px">In Russia: ${ru.map((r) => esc(r.en || r.name)).join(", ")}.</p>` : ""}
      <p class="muted">As of ${tm(reg.as_of)}. Not a safety tool: follow official alerts.</p>` : wait("alerts");
    const msgs = (reg.messages || []).slice(0, 6);
    const threats = S.alerts ? (msgs.length ? rows(msgs.map((m) => `<li><span class="r-m">${tm(m.at)}</span>${link(m.url, esc(m.text))}</li>`)) : `<p class="none">No threat messages in the feed now.</p>`) : wait("alerts");
    const nums = S.summary ? rows([
      `<li><span class="r-n">${nf(s.events_24h)}</span>Events pinned in the last 24 hours</li>`, `<li><span class="r-n">${nf(s.events_6h)}</span>In the last 6 hours</li>`,
      `<li><span class="r-n">${nf(S.events ? G.pinStats().total : s.events_total)}</span>On the map in all, from every pin source</li>`, `<li><span class="r-n">${nf(s.thermal_corroborated)}</span>Events with a satellite fire detection nearby</li>`,
      s.ru_losses_personnel_today != null ? `<li><span class="r-n">${nf(s.ru_losses_personnel_today)}</span>Russian personnel losses today, as Ukraine’s General Staff reports them</li>` : "",
      s.latest_event ? `<li><span class="r-m">Newest pin, ${tm(s.latest_event.ts)}</span>${link(s.latest_event.url, esc(s.latest_event.title))} <span class="muted">${esc(s.latest_event.country_name || "")}</span></li>` : ""]) : wait("summary");
    return block("Theatre by theatre", ths, true) + block("Air-raid alerts now", alerts) + block("Latest air-threat messages (Ukraine)", threats) + block("Front lines on the map", fronts) + block("By the numbers", nums);
  }

  // ---------- Air ----------
  const ROLE = { helicopter: "Helicopters", transport: "Transports", tiltrotor: "Tiltrotors", light: "Trainers and light aircraft", isr: "Surveillance aircraft", tanker: "Tankers", other: "Type unknown", jet: "Jets", drone: "Drones", fighter: "Fighters", bomber: "Bombers" };
  const TFR = { SECURITY: "Security", HAZARDS: "Hazards", VIP: "VIP movement", SPECIAL: "Special", "AIR SHOWS/SPORTS": "Air shows and sports", "UAS PUBLIC GATHERING": "Drone limits over public gatherings", "SPACE OPERATIONS": "Space launches" };
  function air() {
    const s = S.summary || {}, F = S.feeds, m = F.mil, j = F.gpsjam, t = F.tfr, pla = s.taiwan_pla;
    const mil = m ? `<p class="lede"><span class="fig-big">${nf(m.count)}</span>military aircraft heard now.</p>` + rows(Object.entries(m.roles || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<li><span class="r-n">${nf(n)}</span>${esc(ROLE[k] || k)}</li>`))
      + `<p class="muted">Open receivers only: an aircraft with its transponder off is not here. <a href="#/map?topic=air">See them on the map</a>.</p>` : wait("mil");
    const notable = (s.mil_aircraft_notable || []).length ? rows(s.mil_aircraft_notable.slice(0, 10).map((a) => `<li><span class="r-t">${esc(a.type || "Type unknown")}</span><span class="r-m">${esc(a.operator || "")} · ${esc(ROLE[a.role] || a.role || "")} · ${esc(G.thName(a.theatre) || "outside the watched theatres")} · ${a.alt_ft === "ground" ? "on the ground" : nf(a.alt_ft) + " ft"}</span></li>`)) : `<p class="none">None flagged now.</p>`;
    const jam = j ? `<p class="lede"><span class="fig-big">${nf((j.levels || {}).high)}</span>areas with high GPS interference on ${D(j.date)}.</p><p>${nf((j.levels || {}).medium)} more had medium interference, out of ${nf(j.hexes_total)} areas with aircraft overhead. Usually jamming or spoofing, but not always.</p>` : wait("gpsjam");
    const tfr = t ? `<p class="lede"><span class="fig-big">${nf((t.by_status || {}).active)}</span>US flight restrictions active, ${nf((t.by_status || {}).upcoming)} upcoming.</p>` + rows(Object.entries(t.by_type || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<li><span class="r-n">${nf(n)}</span>${esc(TFR[k] || cap(k.toLowerCase()))}</li>`))
      + (s.airspace_czib_active != null ? `<p><b>${nf(s.airspace_czib_active)}</b> conflict-zone airspace warnings are in force worldwide.</p>` : "") : wait("tfr");
    const tw = pla ? `<p class="lede"><span class="fig-big">${nf(pla.aircraft)}</span>Chinese military aircraft and ${nf(pla.plan_ships)} navy ships around Taiwan (${D(pla.date)}).</p><p>${nf(pla.entered_adiz)} entered the air defence zone. ${link(pla.url, "Taiwan defence ministry report")}.</p>` : `<p class="none">No daily count in the summary.</p>`;
    return block("Military aircraft", mil) + block("Worth a look", notable) + block("GPS interference", jam) + block("Restricted airspace", tfr) + block("Taiwan Strait", tw)
      + block("Aircraft emergency codes", placeholder("Emergency transponder codes", "Aircraft squawking 7500, 7600 or 7700 will be listed here.", "squawk"));
  }

  // ---------- Sea ----------
  function sea() {
    const s = S.summary || {}, F = S.feeds, u = F.ukmto, p = F.portwatch, sh = F.ships;
    const inc = u ? rows((u.items || []).slice(0, 8).map((i) => `<li><span class="r-n">${pill(i.type || "Notice", /attack|hijack/i.test(i.type) ? "red" : "grey")}</span><span class="r-t">${link(i.url, esc(i.where || "At sea"))}</span><span class="r-m">${D(i.date)}</span>${esc(cut(ukText(i.text), 230))}</li>`))
      + `<p class="muted">${nf(s.ukmto_incidents_7d)} in the last 7 days. <a href="#/map?topic=sea&amp;c=54,24&amp;z=4.4">See them on the map</a>.</p>` : wait("ukmto");
    let choke = wait("portwatch");
    if (p) {
      const list = (p.chokepoints || []).filter((c) => (c.year_ago7 || {}).total >= 3 && (c.change_vs_year_pct || {}).total != null).sort((a, b) => Math.abs(b.change_vs_year_pct.total) - Math.abs(a.change_vs_year_pct.total)).slice(0, 10);
      choke = `<table class="tbl"><thead><tr><th>Chokepoint</th><th class="num">Ships a day, last 7 days</th><th class="num">A year ago</th><th class="num">Change</th></tr></thead><tbody>${list.map((c) => { const ch = (c.change_vs_year_pct || {}).total; return `<tr><td>${esc(c.name)}</td><td class="num">${nf((c.avg7 || {}).total)}</td><td class="num">${nf((c.year_ago7 || {}).total)}</td><td class="num ${ch <= -50 ? "lv-high" : ch <= -20 ? "lv-mid" : ""}"><b>${ch > 0 ? "+" : ""}${nf(ch)}%</b></td></tr>`; }).join("")}</tbody></table>
        <p class="muted">The ten chokepoints furthest from last year’s traffic. IMF PortWatch, counted from satellite, through ${D(p.data_through)}.</p>`;
    }
    let ships = wait("ships");
    if (sh) {
      const a = Object.values(sh.areas || {}).sort((x, y) => (y.ships_1h || 0) - (x.ships_1h || 0)), at = G.shipsAt ? G.shipsAt(sh) : 0;
      ships = !a.length ? `<p class="none">${sh._ok === false ? "The ship feed is failing and has sent no figures." : "No ship figures have arrived yet."}</p>` : `<table class="tbl"><thead><tr><th>Area</th><th class="num">Ships heard</th><th class="num">Under way</th><th class="num">Tankers</th></tr></thead><tbody>${a.map((x) => `<tr><td>${esc(x.label)}${x.no_live_coverage ? ' <span class="muted">(no receivers here)</span>' : ""}</td><td class="num">${nf(x.ships_1h)}</td><td class="num">${nf(x.underway)}</td><td class="num">${nf(x.tankers)}</td></tr>`).join("")}</tbody></table>
        <p class="muted">Heard in the last hour by volunteer receivers. A low count can mean no coverage, not no ships.${sh.count != null ? ` ${nf(sh.count)} ships are on the <a href="#/map?topic=sea">map</a>.` : ""}${at ? ` Newest position heard ${esc(G.when(at))} ${G.zlabel()} (${esc(G.ago(at))}).` : ""}${sh._ok === false ? " The last refresh of this feed failed; these are the figures it had." : ""}</p>`;
    }
    return block("Incidents at sea (UKMTO)", inc) + block("Chokepoint traffic against a year ago", choke) + block("Ships heard, by area", ships, true)
      + block("Listed and sanctioned ships", placeholder("Ships on sanctions and watch lists", "Tankers and cargo ships named on sanctions lists, where they were last heard and where they say they are going.", "vessellists"))
      + block("Ship counts from satellite", placeholder("Satellite ship counts", "Daily vessel counts at the chokepoints from satellite tracking, for the areas with no receivers.", "gfw"));
  }

  // ---------- Outages and cyber ----------
  const CY = { ddos: "DDoS target list", ransom: "ransomware claim", ics: "industrial control advisory", kev: "exploited vulnerability", attack: "reported attack", cisa: "security advisory" };
  function outages() {
    const F = S.feeds, o = F.outages, c = F.cyber;
    let net = wait("outages");
    if (o) {
      const cs = (o.countries || []).filter((x) => x.watched || x.ongoing).sort((a, b) => (b.ongoing - a.ongoing) || (b.watched - a.watched)).slice(0, 10);
      const rg = (o.regions || []).slice().sort((a, b) => (b.ongoing - a.ongoing) || Date.parse(b.start) - Date.parse(a.start)).slice(0, 10);
      net = `<p class="lede"><span class="fig-big">${nf(o.count)}</span>countries with an internet outage in the last ${nf(o.window_h)} hours.</p>`
        + rows(cs.map((x) => `<li><span class="r-n">${x.ongoing ? pill("ongoing", "red") : pill("ended", "grey")}</span><b>${esc(x.name)}</b> <span class="muted">${x.watched ? "watched country · " : ""}last seen ${tm(x.last)}</span></li>`))
        + `<h2 style="margin-top:18px">Regions, newest first</h2>` + rows(rg.map((x) => `<li><span class="r-n">${x.ongoing ? pill("ongoing", "red") : nf(x.hours) + " h"}</span><b>${esc(x.region)}</b>, ${esc(country(x.country))} <span class="muted">from ${tm(x.start)} · ${esc((o.sources || {})[x.source] || x.source || "")}</span></li>`))
        + `<p class="muted">Automatic detections; a drop seen by routing and probing together is the strongest signal.</p>`;
    }
    let cy = wait("cyber");
    if (c) {
      const lvl = (c.infocon || {}).level, items = (c.items || []).filter((i) => i.ci || i.kind !== "ransom").slice(0, 8);
      cy = `<p class="lede">Internet threat level: ${pill(lvl || "unknown", lvl === "green" ? "ok" : lvl === "yellow" ? "amber" : "red")}</p><p>${esc(c.summary || "")}</p>`
        + rows(items.map((i) => `<li><span class="r-m">${tm(i.ts)} · ${esc(CY[i.kind] || i.kind || "")}${i.ci ? " · critical infrastructure" : ""}</span>${link(i.url, esc(cut(i.title, 150)))}</li>`))
        + `<p class="muted">Ransomware entries are claims posted by the gangs, not confirmed breaches.</p>`;
    }
    return block("Internet outages", net) + block("Cyber", cy)
      + block("Power", placeholder("Power grids", "Grid outages and load in the watched countries.", "power")) + block("Mobile networks", placeholder("Mobile networks", "Cellular outages by country and operator.", "cellular"))
      + block("Websites and cloud", placeholder("Website and cloud reachability", "Whether key government, bank and media sites answer, and cloud-region incidents.", "websites", "cloud"))
      + block("Undersea cables", placeholder("Undersea cables", "Cable faults and repairs, with the cables drawn on the map.", "cables"));
  }

  // ---------- Hazards ----------
  function hazards() {
    const s = S.summary || {}, F = S.feeds, q = F.quakes, h = F.hazards;
    let qk = wait("quakes");
    if (q) {
      const fs = ((q.geojson || {}).features || []).map((f) => f.properties).sort((a, b) => (b.watch - a.watch) || b.mag - a.mag).slice(0, 10);
      qk = `<p class="lede"><span class="fig-big">${nf(q.count)}</span>earthquakes of magnitude 4 or more in ${nf(q.window_hours)} hours; ${nf(q.watch_count)} on the watch list.</p>`
        + rows(fs.map((p) => `<li><span class="r-n">M ${esc(p.mag)}</span><span class="r-t">${link(p.url, esc(p.place || ""))}</span><span class="r-m">${tm(p.time)} · ${nf(p.depth_km)} km deep${p.watch ? " · " + esc(p.watch_reason || "on the watch list") : ""}</span></li>`))
        + `<p class="muted">The watch list flags shallow events in watched areas and anything typed as an explosion. <a href="#/map?topic=hazards">See them on the map</a>.</p>`;
    }
    let gd = wait("hazards");
    if (h) {
      const fs = ((h.geojson || {}).features || []).map((f) => f.properties).filter((p) => p.alert && p.alert !== "Green");
      const types = { DR: "Droughts", EQ: "Earthquakes", FL: "Floods", TC: "Tropical cyclones", WF: "Wildfires", VO: "Volcanoes" };
      gd = `<p class="lede"><span class="fig-big">${nf(fs.length)}</span>disaster alerts above green, of ${nf(h.count)} in ${nf(h.window_days)} days.</p>`
        + (fs.length ? rows(fs.map((p) => `<li><span class="r-n">${pill(p.alert, p.alert === "Red" ? "red" : "amber")}</span><span class="r-t">${link(p.url, esc(p.event_name || p.type_label || ""))}</span><span class="r-m">${esc(p.type_label || "")} · ${esc(cut(p.severity, 120))}</span></li>`)) : "")
        + `<p>${Object.entries(h.by_type || {}).map(([k, n]) => `${nf(n)} ${esc((types[k] || k).toLowerCase())}`).join(", ")}.</p><p class="muted">GDACS automatic alerts: the colour is the expected humanitarian impact.</p>`;
    }
    const fires = Object.keys(s.firms_hotspots_by_theatre || {}).length ? `<table class="tbl"><thead><tr><th>Theatre</th><th class="num">Fire detections</th></tr></thead><tbody>${Object.entries(s.firms_hotspots_by_theatre).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<tr><td>${esc(G.thName(k) || k)}</td><td class="num">${nf(n)}</td></tr>`).join("")}</tbody></table><p class="muted">Satellite heat detections in the watched theatres. ${nf(s.thermal_corroborated)} event pins have one nearby.</p>` : `<p class="none">No fire counts in the summary.</p>`;
    return block("Earthquakes", qk) + block("Disaster alerts", gd) + block("Fires seen from space", fires)
      + block("Tsunami warnings", placeholder("Tsunami warnings", "Warnings and watches from the tsunami centres.", "tsunami")) + block("Radiation", placeholder("Radiation monitors", "Readings from public radiation monitoring networks near the watched sites.", "radiation"));
  }

  // ---------- Official ----------
  function official() {
    const s = S.summary || {}, F = S.feeds, o = F.official, a = F.advisories, emb = ((S.alerts || {}).embassy || {}).items;
    const st = o ? rows((o.items || []).slice(0, 12).map((i) => `<li><span class="r-m">${esc(i.source || "")} · ${/T\d{2}:\d{2}/.test(i.date || "") ? tm(i.date) : D(i.date)}</span><span class="r-t">${link(i.url, esc(i.title))}</span></li>`)) : wait("official");
    const em = emb ? (emb.length ? rows(emb.slice(0, 8).map((i) => `<li><span class="r-m">${i.t ? esc(G.when(i.t * 1000)) + " " + G.zlabel() : ""}</span><span class="r-t">${link(i.url, esc(i.title))}</span>${esc(cut(i.event, 200))}</li>`)) : `<p class="none">No embassy alerts in the feed.</p>`) : wait("alerts");
    let adv = wait("advisories");
    if (a) {
      const l4 = (a.items || []).filter((i) => i.level === 4).sort((x, y) => String(y.date).localeCompare(String(x.date)));
      adv = `<p class="lede"><span class="fig-big">${nf(a.level4)}</span>countries at “Do not travel”, ${nf(a.level3)} at “Reconsider travel”.</p>`
        + ((a.changes || []).length ? rows(a.changes.slice(0, 8).map((c) => `<li>${esc(c.country || "")}: level ${esc(c.from ?? "?")} to ${esc(c.to ?? c.level ?? "?")} <span class="muted">${D(c.date)}</span></li>`)) : `<p>No country has changed level since the watch began on ${tm(a.watching_since)}.</p>`)
        + `<h2 style="margin-top:18px">Do not travel, most recently updated</h2>` + rows(l4.slice(0, 10).map((i) => `<li><span class="r-n muted">${D(i.date)}</span>${link(i.url, esc(i.country))}</li>`))
        + `<p class="muted">US State Department advisories.</p>`;
    }
    return block("Statements", st) + block("Embassy security alerts", em) + block("Travel advisories", adv)
      + block("Sanctions and threat bulletins", placeholder("Sanctions notices and US threat bulletins", "New sanctions designations and national terrorism advisory bulletins.", "ofac", "ntas"));
  }

  // ---------- Analysis ----------
  function analysis() {
    const pic = (S.analysis || {}).picture;
    if (!pic) return block("The picture", `<p class="none">${S.failed.analysis ? "The analyst picture could not be loaded." : "Loading"}</p>`, true);
    const li = (a) => rows((a || []).map((x) => `<li>${esc(G.zText(x, G.isoMs(pic.generated_at)))}</li>`));
    const st = (v) => pill(v || "?", v === "present" ? "red" : v === "emerging" ? "amber" : "grey");
    return block("The headline", `<p class="lede" style="font-size:26px;line-height:1.25;font-weight:700">${esc(G.zText(pic.headline, G.isoMs(pic.generated_at)))}</p><p class="lede">${esc(G.zText(pic.bluf, G.isoMs(pic.generated_at)))}</p>
        <p class="muted">Written ${tm(pic.generated_at)} from ${nf(pic.events_considered)} events. Confidence: ${esc(pic.confidence || "not stated")}. A machine-written reading of open sources, not a verified report.</p>`, true)
      + block("How tense", `<div class="tension">${G.tensionHtml(pic)}</div>` + rows((pic.theatres || []).map((t) => `<li><span class="r-n lv-${G.level(t.status)}">${esc(t.status)}/10 ${esc(t.trend || "")}</span><a href="#/conflict?t=${esc(t.theatre)}">${esc(G.thName(t.theatre) || t.theatre)}</a></li>`)))
      + block("What changed since the last picture", li(pic.changes_since_last))
      + block("Warning signs", rows((pic.indicators || []).map((i) => `<li><span class="r-n">${st(i.state)}</span><span class="r-t">${esc(i.indicator)}</span>${esc(i.note || "")}</li>`)))
      + block("Links between theatres", li(pic.cross_theatre))
      + block("What cannot be seen", li(pic.gaps))
      + block("Pressure on markets", rows((pic.market_risk || []).map((m) => `<li><span class="r-n">${esc(m.direction || "")}</span><b>${esc(cap(String(m.theme || "").replace(/_/g, " ")))}</b><span class="r-m">${esc(m.why || "")}</span></li>`)));
  }

  // ---------- Sources ----------
  const FEED = { advisories: "Travel advisories", airalerts: "Air-raid alerts, Ukraine", bgp: "Internet routing", cables: "Undersea cables", cellular: "Mobile networks", cir: "Verified incident maps",
    cloud: "Cloud services", cyber: "Cyber", czib: "Conflict-zone airspace warnings", embassy: "Embassy alerts", firms: "Fires from satellite", front: "Front-line area (DeepState)", gdelt: "World news index",
    geoconfirmed: "Geolocated footage", gfw: "Satellite ship counts", gpsjam: "GPS interference", hazards: "Disaster alerts", kinetic: "Curated strike reports", losses: "Reported losses", mil: "Military aircraft",
    mymaps: "Event map: pins and front lines", ntas: "US threat bulletins", ofac: "Sanctions notices", official: "Official statements", outages: "Internet outages", pla: "Taiwan Strait activity", portwatch: "Chokepoint traffic",
    power: "Power grids", quakes: "Earthquakes", radiation: "Radiation monitors", ships: "Ships", squawk: "Aircraft emergency codes", telegram: "Telegram channels", tfr: "US flight restrictions", tsunami: "Tsunami warnings",
    tzeva: "Israel sirens", tzevalive: "Israel sirens, live", ukmto: "Incidents at sea", vessellists: "Listed ships", websites: "Website reachability", wire: "News wire" };
  const every = (s) => (s >= 86400 ? Math.round(s / 86400) + " d" : s >= 3600 ? Math.round(s / 3600) + " h" : Math.round(s / 60) + " min");
  function sources() {
    const st = S.status;
    if (!st) return block("Source health", `<p class="none">${S.failed.status ? "The status report could not be loaded." : "Loading"}</p>`, true);
    const fs = Object.entries(st.feeds || {}).map(([k, f]) => ({ k, ...f, bad: !f.ok ? 2 : f.stale ? 1 : 0 })).sort((a, b) => b.bad - a.bad || (FEED[a.k] || a.k).localeCompare(FEED[b.k] || b.k));
    const bad = fs.filter((f) => f.bad).length, w = S.feeds.wire, tg = S.feeds.telegram;
    const table = `<table class="tbl"><thead><tr><th>Source</th><th>State</th><th class="num">Last ran</th><th class="num">Runs every</th></tr></thead><tbody>${fs.map((f) => `<tr><td>${esc(FEED[f.k] || f.k)}</td><td>${f.bad === 2 ? pill("failed", "red") : f.bad ? pill("late", "amber") : pill("on time", "ok")}</td><td class="num">${f.at ? esc(G.ago(G.isoMs(f.at))) : "never"}</td><td class="num">${f.every ? every(f.every) : ""}</td></tr>`).join("")}</tbody></table>`;
    // where the pins come from, with the credits as the Classic theme words them (web/ext/curated.js)
    const ps = G.pinStats(), ver = (window.GTTheme || {}).version, out = (u, t) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`;
    const pins = S.events ? rows([`<li><span class="r-n">${nf(ps.by.map || 0)}</span>Source map<span class="r-m">The curated map the pins and the front lines come from</span></li>`,
        ...Object.entries(G.PINSRC).map(([k, v]) => (G.absent(k) ? `<li>${esc(v[0])}<span class="r-m">${G.NOT_HERE}</span></li>` : `<li><span class="r-n">${nf(ps.by[k] || 0)}</span>${esc(v[0])}<span class="r-m">${esc(v[2])}</span></li>`))])
      + `<p class="muted">The source map wins: a pin from another source is left out when the map already has the same post.</p>`
      + `<p class="muted">Verified pins: ${out("https://geoconfirmed.org", "GeoConfirmed")} and ${out("https://eyesonrussia.org", "CIR Eyes on Russia")} (research use; not on the public mirror), and S2 Underground’s Iran kinetic events map (${out("https://creativecommons.org/licenses/by-nc-sa/4.0/", "CC BY-NC-SA 4.0")}, layout changed).</p>`
      : `<p class="none">${S.failed.events ? "The event map could not be loaded." : "Loading"}</p>`;
    const pubs = (d, what, name) => (G.absent(name) ? `<p class="none">${G.NOT_HERE}</p>` : d && d.sources ? `<p class="lede"><span class="fig-big">${nf(d.sources.length)}</span>${what}, ${nf(d.sources.filter((x) => !x.ok).length)} failing now.</p><p>${nf(d.count)} entries held; last fetched ${tm(d.fetched_at)}.</p>` : `<p class="none">Not loaded.</p>`);
    return block("Source health", `<p class="lede"><span class="fig-big">${nf(fs.length - bad)}</span>of ${nf(fs.length)} sources are reporting on time${bad ? `; ${nf(bad)} need a look` : ""}.</p>${table}<p class="muted">Server time ${tm(st.now)}. This page re-reads the data every 3 minutes.</p>`, true)
      + block("News wire", pubs(w, "publishers", "wire")) + block("Telegram", pubs(tg, "channels", "telegram"))
      + block("Time zone", `<p>Every time on the page is shown in <b>${G.zlabel()}</b> time. Change it with the Eastern / UTC switch at the top of any page; the choice is remembered on this device.</p>`)
      + block("Event pins, by source", pins)
      + block("About this page", `<p>Ground Truth${ver ? " " + esc(ver) : ""}, Dispatch theme. It reads the live data and writes nothing. It is not a safety tool: follow official alerts.</p>`);
  }

  const RENDER = { conflict, air, sea, outages, hazards, official, analysis, sources };
  let asked = "", jump = true;
  function render(r) {
    if (r.view !== "section") return;
    const page = PAGES[r.name];
    $("section").innerHTML = `<header class="page-head"><h1>${page.title}</h1><p class="standfirst">${page.stand}</p></header><div class="blocks">${RENDER[r.name]()}</div>`;
    // 1.7.1: any UTC time left in the page's text ("05:38Z", the analyst's own words) gets its Eastern time beside it.
    const pic = (S.analysis || {}).picture, ref = pic ? G.isoMs(pic.generated_at) : NaN, tw = document.createTreeWalker($("section"), NodeFilter.SHOW_TEXT);
    for (let nd = tw.nextNode(); nd; nd = tw.nextNode()) { const v = G.zText(nd.nodeValue, ref); if (v !== nd.nodeValue) nd.nodeValue = v; }
    // A feed this copy lacks is not asked for. 1.7.3: a feed is asked for again once its copy is 2.5 minutes old or its
    // last try failed that long ago (G.due), so an open section follows the 3-minute reload and recovers from one failure.
    const missing = page.feeds.filter(G.due);
    if (missing.length && asked !== r.name) {
      asked = r.name;
      Promise.all(page.feeds.map((f) => G.need(f).catch(() => null))).then(() => { asked = ""; if (S.route.name === r.name) render(S.route); });
    }
    // 1.7.3: the jump to a theatre happens once per visit, not again at every 3-minute reload (it pulled the reader back up)
    if (r.q.t && jump) { const el = document.getElementById("th-" + r.q.t); if (el) { jump = false; el.scrollIntoView({ block: "start" }); } }
  }
  G.on("route", () => { jump = true; });
  G.on("render", render);
  render(S.route);
})();
