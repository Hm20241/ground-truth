// Ground Truth page extension: news wire and Telegram (0.12.0, ext 1.2: 0.13.0 counts untried sources apart; 1.0.0 Brief columns;
// ext 1.3, 1.2.0: both lists also feed the main Feed tab through GTX.stream; ext 1.4, 1.4.0: Feed items carry cc (country)
// for the title bar; ext 1.5, 1.4.2: the news layer starts on, like every layer; ext 1.6, 1.5.0: items the server holds an
// English translation for carry it (title in English, the original kept), with a "translated" badge showing the original).
// A Wire tab with two lists: wire stories (40 RSS feeds and Google News searches, duplicates merged across outlets)
// and posts from 10 public Telegram channels. Both follow the theatre picked in the left rail, with a text filter,
// an "unplaced" toggle and a country filter. A map layer (off by default) puts a bubble on each country sized by
// its stories in the last 24 h; clicking one lists that country's newest stories.
// Feeds: /api/feed/wire, /api/feed/telegram (gt/wire.py, gt/telegram.py); points: /api/news_geo. Private: never on
// the public mirror.
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { esc, fmtT, fmtD, ago, nf, showPopup, THEATRES } = GTX;
  const empty = { type: "FeatureCollection", features: [] };
  const NEWS = "#cbd5e1";
  const ui = { mode: "wire", q: "", unplaced: false, country: null, countryName: "", top: false };
  const F = () => GTX.S.feeds;
  const when = (ms) => (ms ? `${fmtD(ms)} ${fmtT(ms)} · ${ago(ms)}` : "–");
  const link = (u) => (/^https?:\/\//i.test(u || "") ? u : null);  // 1.7.3: only http(s) addresses become links
  const aTag = (u, html) => (link(u) ? `<a href="${esc(link(u))}" target="_blank" rel="noopener">${html}</a>` : html);
  const thCol = (th) => (THEATRES[th] ? THEATRES[th][1] : "var(--dim)");

  GTX.layer({ key: "news", label: "News volume by country (wire + Telegram, 24 h)", feed: "wire", after: "outages",
    ids: ["nw-pt", "nw-label"], click: ["nw-pt"], clickBefore: "adv-fill",
    count: () => Object.keys((F().wire || {}).by_country_24h || {}).length || null,
    legend: `<span><i class="lsw dot" style="background:${NEWS}"></i>size = stories in 24 h; click for headlines</span>` });

  GTX.onMapLoad((map) => {
    map.addSource("news", { type: "geojson", data: empty });
    const vis = { visibility: GTX.layerOn("news") ? "visible" : "none" };
    map.addLayer({ id: "nw-pt", type: "circle", source: "news", layout: vis, filter: [">", ["get", "n24"], 0], paint: {
      "circle-radius": ["interpolate", ["linear"], ["sqrt", ["get", "n24"]], 1, 4, 4, 9, 10, 20],
      "circle-color": NEWS, "circle-opacity": 0.22, "circle-stroke-width": 1, "circle-stroke-color": NEWS, "circle-stroke-opacity": 0.7 } }, GTX.below.events);
    map.addLayer({ id: "nw-label", type: "symbol", source: "news", filter: [">=", ["get", "n24"], 3], layout: Object.assign({}, vis, {
      "text-field": ["to-string", ["get", "n24"]], "text-size": 10, "text-font": ["Open Sans Regular"], "text-allow-overlap": false }),
      paint: { "text-color": "#e5e7eb", "text-halo-color": "#0b0e11", "text-halo-width": 1 } }, GTX.below.events);
  });

  // 1.7.3: the wire and Telegram feeds land together, so one request serves both (it was asked for twice at every load)
  let geoT = null;
  const loadGeo = () => { if (geoT) return; geoT = setTimeout(() => { geoT = null;
    GTX.api("news_geo").then((fc) => { const s = GTX.map.getSource("news"); if (s) s.setData(fc || empty); }).catch(() => {}); }, 1000); };
  const redraw = () => { if (GTX.isOpen("wire")) renderList(); };
  GTX.feed("wire", () => { loadGeo(); redraw(); });
  GTX.feed("telegram", () => { loadGeo(); redraw(); });
  // 1.2.0 (ext 1.3): wire stories and Telegram posts also run in the main Feed tab, with the rail's category filter.
  // 1.4.0 (ext 1.4): cc = the server's countries for the story (ISO-3, strongest first), for the Feed row's title bar
  const toFeed = (x) => ({ id: x.id, ts: x.ts_ms, title: x.title, url: x.url, th: x.theatre || null, cat: x.category, text: x.summary,
    cc: (x.countries || []).length ? x.countries : undefined,
    where: (x.countries || []).slice(0, 3).map((a3) => (GTX.country(a3) || {}).name || a3).join(", "),
    label: x.channel ? "@" + x.channel : x.source_label || x.source, badge: (x.also_in || []).length ? `+${x.also_in.length} more` : "",
    tr: x.translated ? { from: x.translated.from, orig: x.title_orig || "" } : undefined });
  GTX.stream({ key: "wire", group: "wire", label: "Wire", data: () => F().wire, items: (d) => (d.items || []).map(toFeed) });
  GTX.stream({ key: "telegram", group: "telegram", label: "Telegram", data: () => F().telegram, items: (d) => (d.items || []).map(toFeed) });
  GTX.onRender(redraw);  // the rail's theatre changed

  const items = (mode) => ((F()[mode] || {}).items || []);
  // newest 3 wire stories and newest 3 Telegram posts naming the country (both lists are newest first)
  const ofCountry = (a3) => ["wire", "telegram"].flatMap((m) => items(m).filter((x) => (x.countries || []).includes(a3)).slice(0, 3));

  GTX.popup("nw-pt", (f, lngLat) => {
    const p = f.properties, list = ofCountry(p.a3);
    showPopup(lngLat, `<div class="pop"><h5>${esc(p.name)}: news, 24 h</h5>
      <div class="meta">Wire ${nf(p.wire_24h)} stories, Telegram ${nf(p.tg_24h)} posts (48 h: ${nf(p.n48)})</div>
      ${list.map((x) => `<div class="small" style="margin-top:4px">${x.kind === "telegram" ? `<span class="badge">@${esc(x.channel)}</span> ` : ""}${aTag(x.url, esc(x.title))}
        <span class="muted">${x.kind === "telegram" ? "" : esc(x.source_label || "") + " · "}${x.ts_ms ? fmtT(x.ts_ms) : ""}</span></div>`).join("")}
      <div style="margin-top:6px"><button class="chip" data-wirecountry="${esc(p.a3)}" data-wirename="${esc(p.name)}">All ${esc(p.name)} stories in the Wire tab</button></div>
      <div class="muted small" style="margin-top:4px">Placed by country names in the text; a story about a country is not always from it.</div></div>`);
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-wirecountry]");
    if (!b) return;
    e.preventDefault();
    ui.country = b.dataset.wirecountry; ui.countryName = b.dataset.wirename;
    const tab = document.querySelector('#tabs [data-tab="wire"]');
    if (tab) tab.click();
  });

  // ext 1.6: "if a feed item is in another language please translate to english"
  let LANGS = null;
  const langName = (c) => { try { LANGS = LANGS || new Intl.DisplayNames(["en"], { type: "language" }); return LANGS.of(c) || c; } catch (err) { return c; } };
  const trBadge = (x) => (x.translated
    ? ` <span class="badge tr" title="${esc(`Machine translation from ${langName(x.translated.from)}. Original: ${x.title_orig || ""}`)}">EN · from ${esc(langName(x.translated.from))}</span>` : "");
  function wireRow(x) {
    const also = (x.also_in || []).length;
    return `<li style="--c:${thCol(x.theatre)}"><div>${aTag(x.url, esc(x.title))}</div>
      <div class="muted small">${esc(x.source_label || x.source)}${x.via ? ` <span class="badge">via ${esc(x.via)}</span>` : ""}${also ? ` <span class="badge" title="${esc(x.also_in.join(", "))}">+${also} outlet${also > 1 ? "s" : ""}</span>` : ""}
        · ${when(x.ts_ms)}${(x.countries || []).length ? " · " + esc(x.countries.slice(0, 4).join(", ")) : ""}${x.category && x.category !== "other" ? ` · ${esc(x.category)}` : ""}${x.translated ? trBadge(x) : x.lang && x.lang !== "en" ? ` · ${esc(x.lang)}` : ""}</div></li>`;
  }
  function tgRow(x) {
    const extra = x.summary && x.summary !== x.title ? `<div class="small" style="margin-top:2px">${esc(String(x.summary).slice(0, 280))}${String(x.summary).length > 280 ? "…" : ""}</div>` : "";
    return `<li style="--c:${thCol(x.theatre)}"><div><span class="badge">@${esc(x.channel)}</span> ${esc(x.title)}</div>${extra}
      <div class="muted small">${when(x.ts_ms)}${x.views != null ? " · " + nf(x.views) + " views" : ""}${x.has_photo ? " · photo" : ""}${x.has_video ? " · video" : ""}${x.forwarded ? ` · forwarded${x.forwarded_from ? " from " + esc(x.forwarded_from) : ""}` : ""}${x.translated ? trBadge(x) : x.lang && x.lang !== "en" ? ` · ${esc(x.lang)}` : ""}${(x.countries || []).length ? " · " + esc(x.countries.slice(0, 4).join(", ")) : ""}
        ${link(x.url) ? "· " + aTag(x.url, "t.me ↗") : ""}</div></li>`;
  }

  function filtered() {
    const th = GTX.S.theatre, q = ui.q.trim().toLowerCase();
    const out = items(ui.mode).filter((x) => {
      if (ui.country) { if (!(x.countries || []).includes(ui.country)) return false; }
      else if (!x.theatre) { if (!ui.unplaced) return false; }
      else if (th !== "global" && x.theatre !== th) return false;
      if (q && !`${x.title} ${x.summary || ""} ${x.source_label || ""} ${x.channel || ""} ${(x.countries || []).join(" ")}`.toLowerCase().includes(q)) return false;
      return true;
    });
    // "Most covered": stories carried by the most outlets first (a steadier signal than the keyword categories)
    return ui.top && ui.mode === "wire" ? out.sort((a, b) => (b.also_in || []).length - (a.also_in || []).length || b.ts_ms - a.ts_ms) : out;
  }

  function renderList() {
    const el = document.getElementById("tab-wire");
    if (!el || !el.dataset.built) return;
    const w = F().wire, t = F().telegram, d = ui.mode === "wire" ? w : t;
    el.querySelectorAll("[data-wiremode]").forEach((b) => {
      const n = ((F()[b.dataset.wiremode] || {}).items || []).length;
      b.classList.toggle("off", b.dataset.wiremode !== ui.mode);
      b.querySelector(".n").textContent = n ? nf(n) : "";
    });
    el.querySelector("[data-wireunplaced]").classList.toggle("off", !ui.unplaced);
    const tb = el.querySelector("[data-wiretop]");
    tb.classList.toggle("off", !ui.top);
    tb.style.display = ui.mode === "wire" ? "" : "none";
    const cc = el.querySelector("#wirecountry");
    cc.style.display = ui.country ? "" : "none";  // .chip sets display, which would override [hidden]
    cc.innerHTML = ui.country ? `Country: ${esc(ui.countryName || ui.country)} ×` : "";
    const rows = filtered(), th = GTX.S.theatre;
    const scope = ui.country ? esc(ui.countryName || ui.country) : th !== "global" ? esc(THEATRES[th][0]) : "all theatres";
    const srcs = (d || {}).sources || [], bad = srcs.filter((s) => s.ok === false), wait = srcs.filter((s) => s.ok == null);
    el.querySelector("#wirehead").innerHTML = !d ? "No data yet." :
      `${nf(rows.length)} of ${nf((d.items || []).length)} ${ui.mode === "wire" ? "stories" : "posts"} · ${scope} · ${nf(d.total || 0)} in 48 h` +
      ` · ${nf(srcs.length - bad.length - wait.length)}/${nf(srcs.length)} ${ui.mode === "wire" ? "sources" : "channels"} OK` +
      (wait.length ? ` · ${nf(wait.length)} not tried yet` : "") +  // Google searches start a few per call after a restart
      (bad.length ? ` <span title="${esc(bad.map((s) => s.label + ": " + (s.error || "error")).join("\n"))}" class="badge">${nf(bad.length)} failing</span>` : "");
    el.querySelector("#wirelist").innerHTML = rows.slice(0, 200).map(ui.mode === "wire" ? wireRow : tgRow).join("") ||
      `<li class="muted small" style="cursor:default">Nothing matches.</li>`;
    el.querySelector("#wirefoot").innerHTML = ui.mode === "wire"
      ? `Headlines and summaries from the publishers' own RSS feeds; Google News items via its RSS search. The same story from several outlets is merged ("+N outlets"). Countries are placed from the text and can be wrong. Private, non-commercial use.`
      : `Telegram posts are the channels' own unverified claims. Several channels are partisan or a party to the conflict they cover (for example rybar, a Russian military blogger; idfofficial, Israel's military; irna_en, Iran's state news agency; AlMayadeenEnglish, aligned with Hezbollah; and Middle_East_Spectator, an anonymous aggregator). Read the channel name before the post. From Telegram's public web preview (t.me/s).`;
  }

  function renderTab(el) {
    if (!el) return;
    if (!el.dataset.built) {
      el.innerHTML = `<div class="chips" id="wiremodes">
          <button class="chip" data-wiremode="wire">News wire <span class="n"></span></button>
          <button class="chip" data-wiremode="telegram">Telegram <span class="n"></span></button>
          <button class="chip off" data-wiretop="1" title="Sort by the number of outlets carrying the story">Most covered</button>
          <button class="chip off" data-wireunplaced="1" title="Also show items with no country placed">Unplaced</button>
          <button class="chip" id="wirecountry" style="display:none" title="Clear the country filter"></button></div>
        <input class="search" id="wireq" placeholder="Filter headlines, sources, channels…" autocomplete="off" style="margin-top:8px">
        <div class="muted small" id="wirehead" style="margin-top:6px"></div>
        <ul class="feed" id="wirelist"></ul>
        <div class="muted small" id="wirefoot" style="margin-top:8px"></div>`;
      el.dataset.built = "1";
      el.querySelector("#wiremodes").onclick = (e) => {
        const m = e.target.closest("[data-wiremode]"), u = e.target.closest("[data-wireunplaced]"), c = e.target.closest("#wirecountry"),
          t = e.target.closest("[data-wiretop]");
        if (m) ui.mode = m.dataset.wiremode; else if (u) ui.unplaced = !ui.unplaced; else if (t) ui.top = !ui.top;
        else if (c) { ui.country = null; ui.countryName = ""; } else return;
        renderList();
      };
      el.querySelector("#wireq").addEventListener("input", (e) => { ui.q = e.target.value; renderList(); });
      el.querySelector("#wirelist").addEventListener("click", (e) => { if (!e.target.closest("a")) { const a = e.target.closest("li") && e.target.closest("li").querySelector("a"); if (a) window.open(a.href, "_blank", "noopener"); } });
    }
    renderList();
  }
  GTX.tab({ id: "wire", label: "Wire", before: "alerts", render: renderTab });
  // Brief tab, "All sources by theatre" (1.0.0)
  const th48 = (mode) => { const d = F()[mode]; if (!d) return null; const o = Object.assign({}, d.by_theatre || {}); delete o.unplaced; return o; };
  GTX.briefColumn({ label: "Wire 48 h", title: "News wire stories, 48 h, by the theatre of the first country placed", counts: () => th48("wire") });
  GTX.briefColumn({ label: "Telegram 48 h", title: "Telegram posts, 48 h", counts: () => th48("telegram"),
    note: "Wire and Telegram count 48 h by the first country placed; Telegram posts are the channels' own claims." });

  GTX.label("wire", "News wire: 44 RSS feeds + 30 Google News searches");
  GTX.label("telegram", "Telegram: 10 public channels (web preview)");
  GTX.credit(`News wire: headlines from the publishers' RSS feeds (BBC, Al Jazeera, France 24, DW, Kyiv Independent, Times of Israel,
    Middle East Eye, The Diplomat, SCMP, Africanews, allAfrica, The Guardian, Infobae, InSight Crime, The Haitian Times, The War Zone,
    Military Times, US Department of War, UN, Crisis Group) and Google News RSS searches; links go to the publishers.
    Telegram: public channel previews at t.me/s; posts are the channels' own claims.`);
});
