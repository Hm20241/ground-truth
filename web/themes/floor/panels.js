/* "Watch Floor" theme: the boards. Every board uses the same grammar: a list panel (A), a second list panel (B),
   a row of figure tiles under the map (C), one map view, and the log filtered to the board's subject.
   A destination this theme does not show yet says so in a dashed box and offers the Classic theme, which has it;
   no figure on the page is made up. */
(() => {
  "use strict";
  const WF = window.WF, { esc, nf, D } = WF;
  const SEV = WF.SEV;
  // ---------- the panel grammar ----------
  const lead = { lv: (n, st, title) => `<span class="lv ${st}" title="${esc(title || "")}">${esc(n)}</span>`, mark: (st) => `<span class="mark2 ${st || ""}"></span>`, line: (cls) => `<span class="lnk ${cls || ""}"></span>`, none: () => "" };
  // one row: {tag, attrs, lead, name, sub, val, small, wrap}
  const row = (r) => { const tag = r.tag || "div";
    return `<${tag} class="row${r.cls ? " " + r.cls : ""}"${tag === "button" ? ' type="button"' : ""}${r.attrs ? " " + r.attrs : ""}><span class="lead">${r.lead || ""}</span><span class="nm${r.wrap ? " wrap" : ""}"><b>${r.name}</b>${r.sub ? `<span>${r.sub}</span>` : ""}</span><span class="val${r.two ? " two" : ""}">${r.val == null ? "" : r.val}${r.small ? `<small>${r.small}</small>` : ""}</span></${tag}>`; };
  const colhead = (a, b, c) => `<div class="colhead"><span>${a}</span><span>${b}</span><span>${c}</span></div>`;
  const tile = (t) => { const tag = t.tag || "div";
    return `<${tag} class="tile"${tag === "button" ? ' type="button"' : ""}${t.attrs ? " " + t.attrs : ""}><span class="k">${t.st ? `<i class="dot ${t.st}"></i>` : ""}${esc(t.k)}</span><b>${t.b}${t.unit ? ` <small>${esc(t.unit)}</small>` : ""}</b><span class="s">${t.s || ""}</span></${tag}>`; };
  const tiles = (list) => `<div class="tiles">${list.map(tile).join("")}</div>`;
  // the button's data-act="classic" calls GTTheme.go("classic") (board.js)
  // `feeds`: the status feeds Classic draws it from. When this copy carries none of them, Classic has nothing to
  // show either, so the box says "Not on this copy." and offers no button (1.7.1).
  const placeholder = (name, what, feeds) => ((feeds || []).length && feeds.every((f) => WF.absent(f)) ? `<div class="ph0"><b>${esc(name)}</b>${WF.NOC}</div>`
    : `<div class="ph0"><b>${esc(name)}</b>${esc(what)} <em>Not in this theme yet. It is in the Classic theme.</em> <button type="button" class="linkbtn" data-act="classic" data-k="classic-${esc(name)}">Open Classic</button></div>`);
  const note = (t) => `<p class="note">${t}</p>`;
  const NOC = WF.NOC, gone = (f) => WF.absent(f);  // 1.7.1: a feed this copy does not carry shows one plain line, never "Loading…" or an error
  const goneRow = (name) => row({ lead: lead.mark(), name, sub: NOC, val: "" });
  const sub = (t) => `<div class="sub">${esc(t)}</div>`;
  const fly = (ll, z, key) => `data-fly="${+ll[0]},${+ll[1]},${+z || 5}" data-k="${esc(key)}"`;  // 1.7.3: numbers only, so feed text can never reach the attribute
  WF.ui = { row, tile, tiles, colhead, placeholder, note, sub, lead };

  const levelSt = (n) => (n == null ? "none" : n >= 7 ? "red" : n >= 4 ? "amber" : "green");
  const levelWord = (n) => (n == null ? "no analyst reading" : n >= 7 ? "active" : n >= 4 ? "elevated" : "normal");
  WF.levelSt = levelSt; WF.levelWord = levelWord;
  const pins = () => ((D.events || {}).features || []).filter((f) => f.properties.kind === "event").map((f) => f);

  // ---------- log entries: one shape for every source ----------
  // {id, t, title, url, kind, cat, sev, src, theatre, ll, sum, noTime, h}
  const catSev = (c) => (WF.CATS[c] || WF.CATS.other)[1], catName = (c) => (WF.CATS[c] || WF.CATS.other)[0];
  const dateOnly = (d) => /^\d{4}-\d{2}-\d{2}$/.test(String(d || ""));
  const dayT = (d) => Math.min((dateOnly(d) ? Date.parse(d + "T00:00:00Z") : Date.parse(d)) || 0, Date.now());
  const dateText = (d) => (dateOnly(d) ? d : Number.isFinite(Date.parse(d)) ? `${WF.fmtDay(Date.parse(d))}, ${WF.fmtT(Date.parse(d))}` : String(d || ""));
  const MAKE = {
    pin: () => pins().map((f) => { const p = f.properties, day = WF.dayOnly(p); return { id: "p" + p.id, t: WF.pinT(p), noTime: day, tip: day ? `${WF.dayText(p.ts_ms)}. Date only: the day as the source gives it.` : "",
      title: p.title || "Untitled pin", url: p.url, kind: "pin", tag: catName(p.category), sev: catSev(p.category), cat: p.category,
      src: WF.pinSrc(p) + (p.handle ? " · @" + p.handle : ""), theatre: p.theatre, ll: f.geometry && f.geometry.coordinates, h: WF.eventPop(p) }; }),
    wire: () => ((D.wire || {}).items || []).map((i) => ({ id: "w" + i.id, t: i.ts_ms, title: i.title, url: i.url, kind: "wire", tag: catName(i.category), sev: catSev(i.category), cat: i.category, src: i.source_label || i.source, theatre: i.theatre, sum: i.summary })),
    tg: () => ((D.telegram || {}).items || []).map((i) => ({ id: "t" + i.id, t: i.ts_ms, title: i.title, url: i.url, kind: "tg", tag: catName(i.category), sev: catSev(i.category), cat: i.category, src: "Telegram " + (i.source_label || ""), theatre: i.theatre, sum: i.summary })),
    ukmto: () => ((D.ukmto || {}).items || []).map((i) => { const sev = /attack|hijack/i.test(i.type) ? 2 : /suspicious/i.test(i.type) ? 1 : 0;
      return { id: "u" + i.num, t: dayT(i.date), noTime: true, title: `${i.type}: ${i.where || "at sea"} (UKMTO #${i.num})`, url: i.url, kind: "ukmto", tag: i.type, sev, src: "UKMTO", ll: i.coord, sum: String(i.text || "").slice(0, 400),
        h: i.coord ? WF.popHtml(`${i.type}: ${i.where || "at sea"}`, `Maritime incident (UKMTO) #${esc(i.num)} · ${esc(i.date || "")}`, esc(String(i.text || "").slice(0, 320)), i.url, "Open the UKMTO notice") : "" }; }),
    cyber: () => ((D.cyber || {}).items || []).map((i) => ({ id: "c" + i.id, t: i.ts_ms, title: i.title, url: i.url, kind: "cyber", tag: { ransom: "Ransomware claim", attack: "Reported attack", ics: "Industrial-control advisory", kev: "Exploited flaw", ddos: "DDoS target", cisa: "CISA advisory" }[i.kind] || "Cyber",
      sev: i.ci ? 1 : 0, src: i.sector ? "Sector: " + i.sector : "Cyber feed" })),
    quake: () => (((D.quakes || {}).geojson || {}).features || []).map((f) => { const p = f.properties; return { id: "q" + p.id, t: Date.parse(p.time), title: `M${Number(p.mag).toFixed(1)} · ${p.place || ""}`, url: p.url, kind: "quake", tag: p.watch ? "Earthquake on watch" : "Earthquake", sev: p.mag >= 6.5 ? 2 : p.watch ? 1 : 0,
      src: p.source, theatre: p.theatre, ll: f.geometry.coordinates, sum: p.watch_reason || "", h: WF.popHtml(`M${p.mag} · ${p.place || ""}`, `${nf(p.depth_km)} km deep · ${esc(WF.when(Date.parse(p.time)))}`, esc(p.watch_reason || ""), p.url) }; }),
    hazard: () => (((D.hazards || {}).geojson || {}).features || []).filter((f) => f.properties.type !== "EQ").map((f) => { const p = f.properties; return { id: "h" + p.id, t: Math.min(Date.parse(p.modified || p.from), Date.now()), title: `${p.type_label}: ${p.country_name || p.gdacs_country || ""}`, url: p.url, kind: "hazard",
      tag: p.alert + " alert", sev: p.alert === "Red" ? 2 : p.alert === "Orange" ? 1 : 0, src: "GDACS", theatre: p.theatre, ll: f.geometry.coordinates, sum: p.severity || "", h: WF.popHtml(`${p.type_label}: ${p.country_name || ""}`, `Disaster alert (GDACS) · ${esc(p.alert)}`, esc(p.severity || ""), p.url, "Open the GDACS report") }; }),
    official: () => ((D.official || {}).items || []).map((i, n) => ({ id: "o" + n + i.date, t: dayT(i.date), noTime: dateOnly(i.date), title: i.title, url: i.url, kind: "official", tag: "Statement", sev: 0, src: i.source })),
    embassy: () => (((D.alerts || {}).embassy || {}).items || []).map((i) => ({ id: "e" + i.id, t: i.t * 1000, title: i.title, url: i.url, kind: "embassy", tag: "Embassy alert", sev: 1, src: "US Embassy", sum: i.event || "" })),
  };
  ["power", "cellular", "websites", "cloud"].forEach((n) => { MAKE[n] = () => ((D[n] || {}).items || []).map((i) => ({ id: n + i.id, t: i.ts_ms, title: i.title, url: i.url, kind: n, tag: (i.active ? "Active" : "Resolved") + (i.severity ? ", " + i.severity : ""),
    sev: !i.active ? 0 : /major|critical/i.test(i.severity || "") ? 2 : 1, src: i.provider || "", ll: i.ll, sum: i.summary || "", h: i.ll ? WF.popHtml(i.title, `${esc(i.provider || "")} · ${esc(i.status || "")}`, esc(String(i.summary || "").slice(0, 260)), i.url) : "" })); });
  WF.KIND_NAME = { pin: "Map pins", wire: "News wire", tg: "Telegram", ukmto: "Incidents at sea", power: "Power", cellular: "Mobile", websites: "Web", cloud: "Cloud and AI", cyber: "Cyber", quake: "Earthquakes", hazard: "Disaster alerts", official: "Statements", embassy: "Embassy alerts" };
  // the status feed behind each kind of log entry (map pins ride on the core replies)
  WF.KIND_FEED = { wire: "wire", tg: "telegram", ukmto: "ukmto", power: "power", cellular: "cellular", websites: "websites", cloud: "cloud", cyber: "cyber", quake: "quakes", hazard: "hazards", official: "official", embassy: "embassy" };
  const cache = {};
  const make = (kind, dataKey) => { const d = D[dataKey]; if (!cache[kind] || cache[kind].d !== d) cache[kind] = { d, items: d ? MAKE[kind]().filter((i) => Number.isFinite(i.t) && i.title) : [] }; return cache[kind].items; };
  const news = (cats) => [...make("pin", "events"), ...make("wire", "wire"), ...make("tg", "telegram")].filter((i) => !cats || cats.includes(i.cat));

  // ---------- Conflict ----------
  function theatres() {
    // counts and newest pin come from the merged pins (the source map's and the three other pin sources')
    const ps = WF.pinStats() || { by: {} }, by = ps.by, an = {}, newest = {}, at = {};
    ((D.analysis || {}).theatres || []).forEach((t) => { an[t.theatre] = t; });
    // newest pin: the newest with a clock time; a theatre with only day-only pins shows the newest of those, by its day
    pins().forEach((f) => { const p = f.properties, t = (p.ts_ms || 0) - (WF.dayOnly(p) ? 1e14 : 0); if (!newest[p.theatre] || t > at[p.theatre]) { newest[p.theatre] = p; at[p.theatre] = t; } });
    const keys = Object.keys(WF.THEATRES).filter((k) => k !== "global").sort((a, b) => ((an[b] || {}).status || 0) - ((an[a] || {}).status || 0) || (by[b] || 0) - (by[a] || 0));
    const one = (k) => { const a = an[k], n = newest[k], lvl = a ? a.status : null, tr = a ? a.trend : "";
      return row({ tag: "button", attrs: `data-th="${k}" data-k="th-${k}" aria-pressed="${WF.S.theatre === k}" aria-label="${esc(WF.tname(k))}: level ${lvl == null ? "not given" : lvl + " of 10, " + levelWord(lvl)}${tr ? ", " + esc(tr) : ""}; ${nf(by[k] || 0)} pins in 24 hours"`,
        lead: lead.lv(lvl == null ? "–" : lvl, levelSt(lvl), lvl == null ? "No analyst reading" : `Analyst level ${lvl} of 10: ${levelWord(lvl)}`),
        name: esc(WF.tname(k)) + (tr === "rising" ? ' <span class="muted" title="rising">▲</span>' : /eas|fall/.test(tr) ? ' <span class="muted" title="easing">▼</span>' : ""),
        sub: n ? `${esc(WF.dayOnly(n) ? WF.dayText(n.ts_ms) : WF.agoShort(n.ts_ms))} · ${esc(n.title)}` : "No pin in this theatre", val: nf(by[k] || 0) }); };
    return { title: "Theatres", right: `<button type="button" class="chip" data-th="global" data-k="th-global" aria-pressed="${WF.S.theatre === "global"}" title="Show every theatre on the map and in the log">All theatres${D.events ? " · " + nf(ps.n24) : ""}</button>`,
      html: WF.wait(["events"]) || colhead(`<span title="The analyst's 0 to 10 reading: 7 and up active, 4 to 6 elevated, under 4 normal">Level</span>`, "Theatre, newest pin", "Pins 24 h") + keys.map(one).join("") };
  }
  function fronts() {
    const all = (WF.FRONTS || []).filter((f) => WF.S.theatre === "global" || f.theatre === WF.S.theatre), list = all.slice(0, WF.S.wall ? 3 : 99);
    return { title: "Fronts", right: list.length < all.length ? `${list.length} busiest of ${all.length}` : `pins within ${WF.NEAR_KM} km`,
      html: WF.wait(["events"]) || (list.length ? colhead("", "Line, place", `<span class="val two" style="font:inherit"><span>24 h</span><span>72 h</span></span>`) + list.map((f) => { const k = WF.FRONT_KIND[f.kind];
        return row({ tag: "button", attrs: `data-fr="${esc(f.id)}" data-k="fr-${esc(f.id)}" title="${esc(k[0])}. Show it on the map."`, cls: "one", lead: lead.line(k[1]), name: esc(f.name), sub: esc(f.where || ""), two: true,
          val: `<span class="${f.n24 ? "" : "dim"}">${nf(f.n24)}</span><span class="${f.n72 ? "" : "dim"}">${nf(f.n72)}</span>` }); }).join("") : note(`No front line on the source map${WF.S.theatre === "global" ? "" : " in this theatre"}.`)) };
  }
  function alerts() {
    const a = D.alerts || {}, s = a.summary || {}, uk = s.ukraine || {}, ru = s.russia || {}, il = s.israel || {}, em = s.us_embassies || {};
    const st = (o) => (o.red ? "red" : o.n ? "amber" : "green");
    const latest = (em.latest || [])[0];
    return { title: "Alerts in force", right: s.as_of ? `as of ${esc(WF.fmtT(WF.ms(s.as_of)))} ${esc(WF.zoneAbbr())}` : "",
      html: WF.wait(["alerts"]) || tiles([
        gone("airalerts") ? { k: "Ukraine", b: "–", s: NOC } : { tag: "button", attrs: fly([32, 49], 4.6, "al-ua"), st: st(uk), k: "Ukraine", b: nf(uk.n), unit: uk.n === 1 ? "region" : "regions", s: uk.n ? `under air-raid alert: ${nf(uk.red)} red, ${nf(uk.yellow)} yellow` : "No air-raid alert in force" },
        gone("airalerts") ? { k: "Russia", b: "–", s: NOC } : { tag: "button", attrs: fly([42, 52], 3.8, "al-ru"), st: st(ru), k: "Russia", b: nf(ru.n), unit: ru.n === 1 ? "region" : "regions", s: ru.n ? `under air-raid alert: ${nf(ru.red)} red, ${nf(ru.yellow)} yellow` : "No air-raid alert in force" },
        gone("tzeva") && gone("tzevalive") ? { k: "Israel", b: "–", s: NOC } : { tag: "button", attrs: fly([35, 31.5], 6.2, "al-il"), st: il.sirens_now ? "red" : il.in_shelter_window || il.early_warnings_30min ? "amber" : "green", k: "Israel", b: nf(il.sirens_now), unit: il.sirens_now === 1 ? "city" : "cities",
          s: "with sirens now. " + (il.last_alert ? `Last alert ${esc(WF.ago(WF.ms(typeof il.last_alert === "number" ? il.last_alert * 1000 : il.last_alert)))}` : "None in the last 24 h") },
        gone("embassy") ? { k: "US embassies", b: "–", s: NOC } : { st: em.alerts_24h ? "amber" : "green", k: "US embassies", b: nf(em.alerts_24h), unit: em.alerts_24h === 1 ? "alert" : "alerts", s: "in 24 h" + (latest ? ". Latest: " + esc(latest.title || latest.n || "") : "") },
      ]) };
  }

  // ---------- Air ----------
  function airA() {
    const su = D.summary || {}, notable = (su.mil_aircraft_notable || []).slice(0, WF.S.wall ? 7 : 14);
    return { title: "Aircraft worth a look", right: D.summary && !gone("mil") ? `of ${nf(su.mil_aircraft)} in the air` : "",
      html: WF.wait(["summary"]) || (gone("mil") ? note(NOC) : notable.length ? colhead("", "Type, kind, operator", "Height") + notable.map((a, i) => row({ tag: "button", attrs: fly([a.lon, a.lat], 5.5, "ac-" + i), lead: lead.mark(), name: esc(a.type || "Aircraft"),
        sub: `${esc(WF.roleName(a.role))} · ${esc(a.operator || "operator not known")}`, val: "", small: a.alt_ft === "ground" ? "on the ground" : nf(a.alt_ft) + " ft" })).join("") : note("The feed marks no aircraft as notable right now.")) };
  }
  function airB() {
    const su = D.summary || {}, tf = (D.tfr || {}).by_status || {}, pla = su.taiwan_pla || {}, g = D.gpsjam || {}, lv = g.levels || {};
    const soon = (name, key) => row({ lead: lead.mark(), name, sub: gone(key) ? NOC : WF.ERR[key] ? "Could not load" : "Loading…", val: "" });
    return { title: "Airspace", right: "",
      html: WF.wait(["summary"]) || (gone("czib") ? goneRow("Warnings over conflict zones") : row({ lead: lead.mark(su.airspace_czib_active ? "amber" : "green"), name: "Warnings over conflict zones", sub: "European safety bulletins in force", val: nf(su.airspace_czib_active) })) +
        (D.gpsjam ? row({ lead: lead.mark(lv.high ? "red" : lv.medium ? "amber" : "green"), name: "GPS interference, high", sub: `${nf(lv.medium)} more areas at medium · ${esc(g.date || "")}`, val: nf(lv.high), small: "areas" }) : soon("GPS interference", "gpsjam")) +
        (D.tfr ? row({ lead: lead.mark(), name: "US flight restrictions", sub: `${nf(tf.upcoming)} more coming up`, val: nf(tf.active), small: "active" }) : soon("US flight restrictions", "tfr")) +
        (gone("pla") ? goneRow("Taiwan: Chinese military activity") : row({ lead: lead.mark(pla.entered_adiz ? "amber" : "green"), name: "Taiwan: Chinese military activity", sub: `${esc(pla.date || "")} · ${nf(pla.plan_ships)} navy ships · ${nf(pla.entered_adiz)} in the defence zone`, val: nf(pla.aircraft), small: "aircraft" })) +
        placeholder("Aircraft emergency codes", "Aircraft squawking an emergency.", ["squawk"]) };
  }
  function airC() {
    const su = D.summary || {}, roles = Object.entries(su.mil_aircraft_by_role || {}).sort((a, b) => b[1] - a[1]), top = roles.slice(0, 4), rest = roles.slice(4).reduce((n, r) => n + r[1], 0);
    return { title: "Military aircraft in the air", right: "by kind, now",
      html: WF.wait(["summary"]) || (gone("mil") ? note(NOC) : tiles([...top.map(([r, n]) => ({ k: WF.roleShort(r), b: nf(n), s: "" })), ...(rest ? [{ k: "The rest", b: nf(rest), s: "" }] : [])])) };
  }

  // ---------- Sea ----------
  function seaA() {
    const cs = ((D.portwatch || {}).chokepoints || []).slice().sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || ((a.change_vs_year_pct || {}).total ?? 0) - ((b.change_vs_year_pct || {}).total ?? 0)).slice(0, WF.S.wall ? 6 : 10);
    return { title: "Chokepoints", right: D.portwatch ? `through ${esc(D.portwatch.data_through || "")}` : "",
      html: WF.wait(["portwatch"]) || colhead("", "Ships a day, 7-day average", "Now") + cs.map((c, i) => { const ch = (c.change_vs_year_pct || {}).total, st = ch == null ? "" : ch <= -50 ? "red" : ch <= -20 ? "amber" : "green";
        return row({ tag: "button", attrs: fly([c.lon, c.lat], 5.5, "cp-" + i), lead: lead.mark(st), name: esc(c.name), sub: `${nf((c.year_ago7 || {}).total)} a year ago · tankers ${nf((c.avg7 || {}).tanker)}`, val: nf((c.avg7 || {}).total), small: ch == null ? "no base" : `${ch > 0 ? "+" : ""}${nf(ch)}%` }); }).join("") +
        note("Counted by IMF PortWatch from satellite ship signals, about three days behind.") };
  }
  function seaB() {
    const su = D.summary || {}, its = ((D.ukmto || {}).items || []).slice(0, WF.S.wall ? 3 : 4);
    return { title: "Incidents at sea", right: D.summary && !gone("ukmto") ? `${nf(su.ukmto_incidents_7d)} in 7 days` : "",
      html: WF.wait(["ukmto"]) || its.map((i) => row({ tag: i.coord ? "button" : "div", attrs: i.coord ? fly(i.coord, 6, "uk-" + i.num) : "", lead: lead.mark(/attack|hijack/i.test(i.type) ? "red" : /suspicious/i.test(i.type) ? "amber" : ""), name: `${esc(i.type)}: ${esc(i.where || "at sea")}`, sub: `UKMTO #${esc(i.num)} · ${esc(i.date || "")}`, val: "" })).join("") +
        placeholder("Ship traffic by satellite", "Daily ship counts per sea area from Global Fishing Watch.", ["gfw"]) };
  }
  function seaC() {
    const short = { hormuz: "Hormuz area", red_sea: "Red Sea", black_sea: "Black Sea", baltic: "Baltic", taiwan: "Taiwan Strait" }, all = (D.ships || {}).areas || {};
    const ar = Object.keys(short).filter((k) => all[k]).map((k) => ({ ...all[k], short: short[k] }));
    // 1.7.3: when the status says the ship feed's last run failed or is overdue, the panel says so; before, old counts
    // stood under "heard in the last hour" with nothing to mark them
    const fs = ((D.status || {}).feeds || {}).ships, old = fs && (!fs.ok || fs.stale);
    return { title: "Ships heard in the last hour", right: D.ships ? `${nf((D.ships || {}).count)} on the map` : "",
      html: WF.wait(["ships"]) || (old ? note(`The ship feed ${fs.ok ? "is overdue" : "failed at its last run"}. These are the ships from its last good run${Number.isFinite(+fs.age_s) ? ", " + esc(WF.ago(Date.now() - fs.age_s * 1000)) : ""}.`) : "") +
        tiles(ar.map((a, i) => ({ tag: a.bbox ? "button" : "div", attrs: a.bbox ? `data-box="${a.bbox.map(Number).join(",")}" data-k="sa-${i}"` : "", st: a.no_live_coverage ? "" : a.listed ? "amber" : "green", k: a.short, b: nf(a.ships_1h),
        s: a.no_live_coverage ? `<span title="Volunteer receivers do not reach this sea, so a low count is not an empty sea">No receivers here</span>` : `<span title="Watch lists: sanctions lists and shadow-fleet lists">${nf(a.tankers)} tankers, ${nf(a.listed)} on watch lists</span>` }))) };
  }

  // ---------- Outages and cyber ----------
  function outA() {
    const io = (D.summary || {}).internet_outages || {}, w = io.watched_countries || [], el = io.largest_elsewhere || [];
    const one = (c) => row({ lead: lead.mark(c.ongoing ? "red" : ""), name: esc(c.country), sub: `${c.ongoing ? "Ongoing" : "Ended"} · last seen ${esc(WF.ago(WF.ms(c.last)))}`, val: "" });
    return { title: "Internet outages", right: D.summary && !gone("outages") ? `${nf(io.countries_with_outages)} countries in ${nf(io.window_h)} h` : "",
      html: WF.wait(["summary"]) || (gone("outages") ? note(NOC) : sub("Watched countries") + (w.length ? w.map(one).join("") : note("None of the watched countries has an outage.")) + (el.length ? sub("Largest elsewhere") + el.map(one).join("") : "")) +
        placeholder("Undersea cables and routing", "Cable faults and routing drops.", ["cables", "bgp"]) };
  }
  function outB() {
    const c = D.cyber || {}, n = {}; (c.items || []).forEach((i) => { n[i.kind] = (n[i.kind] || 0) + 1; });
    const wd = c.windows_days || {}, lvl = (c.infocon || {}).level;
    const r = (k, name, days) => row({ lead: lead.mark(), name, sub: days ? `last ${nf(days)} days` : "now", val: nf(n[k] || 0) });
    return { title: "Cyber", right: lvl ? `threat level: ${esc(lvl)}` : "",
      html: WF.wait(["cyber"]) || row({ lead: lead.mark(lvl === "green" ? "green" : lvl === "yellow" ? "amber" : lvl ? "red" : ""), name: "Internet threat level", sub: "SANS Internet Storm Center", val: `<span style="font-size:1rem">${esc(lvl || "–")}</span>` }) +
        r("ransom", "Ransomware claims", wd.ransom) + r("attack", "Attacks reported in the press", wd.attack) + r("kev", "Flaws now being exploited", wd.kev) + r("ics", "Industrial-control advisories", wd.cisa) + r("ddos", "DDoS targets listed", 0) +
        note("Ransomware entries are gangs' own claims, not confirmed breaches.") };
  }
  function outC() {
    const one = (n, k) => { const d = D[n]; if (!d) return { k, b: "–", s: gone(n) ? NOC : WF.ERR[n] ? "Could not load" : "Loading…" };
      const act = (d.items || []).filter((i) => i.active), big = act.some((i) => /major|critical/i.test(i.severity || ""));
      const top = act.slice().sort((x, y) => (/critical/i.test(y.severity) ? 2 : /major/i.test(y.severity) ? 1 : 0) - (/critical/i.test(x.severity) ? 2 : /major/i.test(x.severity) ? 1 : 0))[0];
      return { st: big ? "red" : act.length ? "amber" : "green", k, b: nf(act.length), unit: "open", s: top ? esc((top.provider ? top.provider + ": " : "") + top.title) : "None open" }; };
    return { title: "Services", right: "incidents open now",
      html: tiles([one("power", "Power grids"), one("cellular", "Mobile networks"), one("websites", "Websites"), one("cloud", "Cloud and AI")]) };
  }

  // ---------- Hazards ----------
  function hazA() {
    const fs = (((D.quakes || {}).geojson || {}).features || []).map((f) => f).sort((a, b) => (b.properties.watch ? 1 : 0) - (a.properties.watch ? 1 : 0) || b.properties.mag - a.properties.mag).slice(0, WF.S.wall ? 7 : 12);
    return { title: "Earthquakes", right: D.quakes ? `${nf(D.quakes.count)} in ${nf(D.quakes.window_hours)} h, ${nf(D.quakes.watch_count)} on watch` : "",
      html: WF.wait(["quakes"]) || colhead("", "Where", "Size") + fs.map((f, i) => { const p = f.properties;
        return row({ tag: "button", attrs: fly(f.geometry.coordinates, 5.5, "qk-" + i), lead: lead.mark(p.mag >= 6.5 ? "red" : p.watch ? "amber" : ""), name: esc(p.place || "Unknown place"), sub: `${esc(WF.ago(Date.parse(p.time)))}${p.watch ? " · on watch: " + esc(p.watch_reason || "") : " · " + nf(p.depth_km) + " km deep"}`, val: "M" + esc(Number(p.mag).toFixed(1)) }); }).join("") };
  }
  function hazB() {
    const fs = (((D.hazards || {}).geojson || {}).features || []).filter((f) => f.properties.alert !== "Green" && f.properties.type !== "EQ").sort((a, b) => (b.properties.alert_score || 0) - (a.properties.alert_score || 0)).slice(0, 6);
    return { title: "Disaster alerts", right: D.hazards ? `orange or red, ${nf(D.hazards.window_days)} days` : "",
      html: WF.wait(["hazards"]) || (fs.length ? fs.map((f, i) => { const p = f.properties;
        return row({ tag: "button", attrs: fly(f.geometry.coordinates, 4.5, "hz-" + i), lead: lead.mark(p.alert === "Red" ? "red" : "amber"), name: `${esc(p.type_label)}: ${esc(p.country_name || "")}`, sub: esc(p.severity || ""), val: "", small: esc(p.alert) }); }).join("") : note("No orange or red alert.")) +
        placeholder("Fires seen from space, radiation, tsunami warnings", "Satellite fire detections and the radiation and tsunami monitors.", ["firms", "radiation", "tsunami"]) };
  }
  function hazC() {
    const bt = (D.hazards || {}).by_type || {}, names = { DR: "Droughts", EQ: "Earthquakes", FL: "Floods", TC: "Cyclones", WF: "Wildfires", VO: "Volcanoes" };
    return { title: "Alerts by kind", right: D.hazards ? `GDACS, last ${nf(D.hazards.window_days)} days` : "",
      html: WF.wait(["hazards"]) || tiles(Object.entries(bt).map(([k, n]) => ({ k: names[k] || k, b: nf(n), s: "" }))) };
  }

  // ---------- Official ----------
  function offA() {
    const its = ((D.official || {}).items || []).slice().sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, WF.S.wall ? 6 : 14);
    return { title: "Official statements", right: D.official ? `${nf((D.official.items || []).length)} newest` : "",
      html: WF.wait(["official"]) || its.map((i) => row({ tag: WF.url(i.url) ? "a" : "div", attrs: WF.url(i.url) ? `href="${esc(WF.url(i.url))}" target="_blank" rel="noopener"` : "", cls: "doc", lead: "", wrap: true, name: esc(i.title), sub: `${esc(i.source)} · ${esc(dateText(i.date))}`, val: "" })).join("") };
  }
  function offB() {
    const ta = (D.summary || {}).travel_advisories || {}, up = ta.updated_14d_level3plus || [], ch = ta.level_changes || [];
    return { title: "Travel advisories", right: "US State Department",
      html: WF.wait(["summary"]) || (gone("advisories") ? note(NOC) : "") || row({ lead: lead.mark("red"), name: "Do not travel", sub: "Level 4", val: nf(ta.level4), small: "countries" }) + row({ lead: lead.mark("amber"), name: "Reconsider travel", sub: "Level 3", val: nf(ta.level3), small: "countries" }) +
        row({ lead: lead.mark(ch.length ? "amber" : ""), name: "Level changes", sub: ta.watching_since ? `since ${esc(WF.fmtDay(WF.ms(ta.watching_since)))}` : "", val: nf(ch.length) }) +
        (up.length ? sub("Updated in 14 days, level 3 or 4") + up.map((u) => row({ lead: lead.mark(u.level === 4 ? "red" : "amber"), name: esc(u.country), sub: esc(u.date || ""), val: "", small: "level " + esc(u.level) })).join("") : "") +
        placeholder("Sanctions and US terror advisories", "New sanctions designations and the US terror-advisory bulletin.", ["ofac", "ntas"]) };
  }
  function offC() {
    const em = (D.alerts || {}).embassy || {}, c = em.counts || {}, its = (em.items || []).slice().sort((a, b) => b.t - a.t).slice(0, 2);
    return { title: "US embassy alerts", right: "",
      html: WF.wait(["alerts"]) || (gone("embassy") ? note(NOC) : "") || tiles([{ st: c["24h"] ? "amber" : "green", k: "Last 24 h", b: nf(c["24h"]), s: "" }, { k: "Last 72 h", b: nf(c["72h"]), s: "" },
        ...its.map((i) => ({ tag: WF.url(i.url) ? "a" : "div", attrs: WF.url(i.url) ? `href="${esc(WF.url(i.url))}" target="_blank" rel="noopener" style="text-decoration:none"` : "", k: WF.ago(i.t * 1000), b: `<span style="font-size:1rem;line-height:1.3;display:block">${esc(i.title)}</span>`, s: "" }))]) };
  }

  WF.BOARDS = {
    conflict: { name: "Conflict", about: "Theatres, fronts, alerts in force", view: "conflict", need: [], panels: [theatres, fronts, alerts], log: () => news(null), kinds: ["pin", "wire", "tg"], what: "pins, news wire and Telegram" },
    air: { name: "Air", about: "Military aircraft, airspace, GPS interference", view: "air", need: ["mil", "czib_geo", "tfr", "gpsjam"], panels: [airA, airB, airC], log: () => news(["aviation", "missile", "drone", "alert"]), kinds: ["pin", "wire", "tg"], what: "entries filed under aviation, missile, drone or alert" },
    sea: { name: "Sea", about: "Chokepoints, incidents at sea, ships", view: "sea", need: ["ships", "ukmto", "portwatch"], panels: [seaA, seaB, seaC], log: () => [...news(["maritime"]), ...make("ukmto", "ukmto")], kinds: ["pin", "wire", "tg", "ukmto"], what: "maritime entries and UKMTO incidents" },
    outages: { name: "Outages and cyber", about: "Internet, power, mobile, web, cloud", view: "outages", need: ["outages_geo", "power", "cloud", "cellular", "websites", "cyber"], panels: [outA, outB, outC],
      log: () => [...make("power", "power"), ...make("cellular", "cellular"), ...make("websites", "websites"), ...make("cloud", "cloud"), ...make("cyber", "cyber"), ...news(["cyber", "energy"])], kinds: ["power", "cellular", "websites", "cloud", "cyber", "pin", "wire", "tg"], what: "service incidents, cyber items and outage news" },
    hazards: { name: "Hazards", about: "Earthquakes and disaster alerts", view: "hazards", need: ["quakes", "hazards"], panels: [hazA, hazB, hazC], log: () => [...make("quake", "quakes"), ...make("hazard", "hazards")], kinds: ["quake", "hazard"], what: "earthquakes and disaster alerts" },
    official: { name: "Official", about: "Statements, travel advisories, embassies", view: "advisories", need: ["official", "advisories_geo"], panels: [offA, offB, offC], log: () => [...make("official", "official"), ...make("embassy", "alerts")], kinds: ["official", "embassy"], what: "official statements and embassy alerts" },
  };
})();
