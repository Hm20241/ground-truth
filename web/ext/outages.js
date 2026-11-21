// Ground Truth page extension: outage layers (1.5.4, ext 1.1; 1.1 labels Cloudflare Radar API links). Asked for: four separate map layers for power
// outages, website / online-service disruptions, AI / cloud / datacenter disruptions and cell / mobile network
// disruptions. Feeds: /api/feed/power and /api/feed/cellular (gt/disruption.py), /api/feed/websites and
// /api/feed/cloud (gt/services.py). Each layer draws its feed's own GeoJSON (one point per item and place), every
// item runs in the Feed tab (cellular's "internet" posts in the existing Internet group), and an Outages tab holds
// the grid status, the services board, Russia's mobile shutdowns and everything active now.
// The page loads a feed only when /api/status lists it. Where these feeds do not run (the public copy) the layer
// rows are hidden, the Feed gets no chips, the header no tiles, and the tab says so. Private: never on the mirror.
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { esc, isoMs, nf, showPopup } = GTX;
  const empty = { type: "FeatureCollection", features: [] };
  const when = (v, rel) => GTX.when(v, rel);  // the page's zone (Eastern or UTC) and the time since
  // key = feed name = layer key; group = the Feed tab's source group (FG in app.js); cat = a CATS key (the rail's
  // category filter and the Feed row's colour)
  const CFG = [
    { key: "power", after: "outages", color: "#f59e0b", group: "power", short: "Power", cat: "energy",
      label: "Power outages (US counties via ODIN, Ukraine, grid alerts, NetBlocks)",
      src: "Power outages: ODIN US counties, Ukraine, grid operators, NetBlocks",
      credit: "Power outages: ODIN outage data (US Department of Energy), Ukraine's grid operator and energy ministry, Taipower, Eskom, CAISO and NetBlocks; each item links to its source." },
    { key: "cellular", after: "power", color: "#4ade80", group: "cell", short: "Cell", cat: "cyber",
      label: "Cell / mobile networks (NetBlocks, Cloudflare Radar, Russia's shutdown map)",
      src: "Cell / mobile networks: NetBlocks, Cloudflare Radar, Russia's shutdown map",
      credit: "Cell networks: NetBlocks, Cloudflare Radar and a public map of Russia's regional mobile-internet shutdowns; each item links to its source." },
    { key: "websites", after: "cellular", color: "#a78bfa", group: "web", short: "Web", cat: "cyber",
      label: "Websites / online services (official status pages)",
      src: "Websites / online services: official status pages",
      credit: "Websites and online services: the services' own official status pages, linked from each item." },
    { key: "cloud", after: "websites", color: "#f472b6", group: "cloud", short: "AI / cloud", cat: "cyber",
      label: "AI / cloud / datacenters (status pages, Cloudflare PoPs, DC news)",
      src: "AI / cloud / datacenters: status pages, Cloudflare PoPs, DC news",
      credit: "AI, cloud and datacenters: the providers' official status pages, Cloudflare's data-centre status list and datacenter news; each item links to its source." },
  ];
  const KEYS = CFG.map((c) => c.key), BY = {};
  CFG.forEach((c) => { BY[c.key] = c; });
  // severity: name, colour (badges), map radius; rank orders the dots (active and worse on top)
  const SEV = { critical: ["critical", "#f05252", 9], major: ["major", "#f2853d", 7.5], minor: ["minor", "#f2b33d", 6],
    maintenance: ["maintenance", "#60a5fa", 5], info: ["info", "#9aa4ae", 5] };
  const RANK = { critical: 4, major: 3, minor: 2, maintenance: 1, info: 0 };
  const BOARD = { operational: ["operational", "#3ecf8e"], degraded: ["degraded", "#f2b33d"], partial: ["partial outage", "#f2853d"],
    major: ["major outage", "#f05252"], maintenance: ["maintenance", "#60a5fa"], unknown: ["unknown", "#5d656e"] };
  const DEGRADED = new Set(["degraded", "partial", "major"]);  // "Services degraded": not maintenance, not unknown (no answer)
  const LIGHT = { G: ["Green", "#3ecf8e", "supply ample"], Y: ["Yellow", "#fde047", "supply tight"], O: ["Orange", "#f2853d", "supply alert"],
    R: ["Red", "#f05252", "rationing warning"], B: ["Black", "#9aa4ae", "rationing"] };
  const ZOOM = { hq: 3, country: 4, region: 5, subject: 5, oblast: 6, pop: 7, county: 7 };
  const PLACE = { hq: "map point: the company's headquarters", region: "map point: the provider region's city", pop: "map point: the data centre's city",
    country: "map point: the country's centre", county: "map point: the county", oblast: "map point: the oblast's centre", subject: "map point: the region's centre" };
  const VM = '<button type="button" class="vm" title="Fly the map here and open the item">◎ View on map</button>';

  const D = (k) => GTX.S.feeds[k] || null;
  const arr = (v) => (Array.isArray(v) ? v : []);
  const llOk = (v) => (Array.isArray(v) && v.length === 2 && v.every((x) => Number.isFinite(x)) && Math.abs(v[0]) <= 180 && Math.abs(v[1]) <= 90 ? v : null);
  const tsOf = (it) => it.ts_ms || isoMs(it.ts) || 0;
  const link = (u) => (/^https?:\/\//i.test(u || "") ? u : null);
  const cut = (s, n) => { const t = String(s || ""); return t.length > n ? t.slice(0, n - 1).trimEnd() + "…" : t; };
  const badge = (t, c) => `<span class="badge"${c ? ` style="border-color:${c};color:${c}"` : ""}>${esc(t)}</span>`;
  const sevOf = (it) => SEV[it.severity] || SEV.info;
  // The Feed's "EN · from Ukrainian" tag (app.js keeps its own trTag private; Feed rows get it from the item's tr)
  let LN = null;
  const langName = (c) => { if (!c) return "another language"; try { LN = LN || new Intl.DisplayNames(["en"], { type: "language" }); return LN.of(c) || c; } catch (err) { return c; } };
  const trTag = (it) => (it.translated ? `<span class="badge tr" title="${esc(`Machine translation from ${langName(it.translated.from || it.lang)}. Original: ${it.title_orig || ""}`)}">EN · from ${esc(langName(it.translated.from || it.lang))}</span>` : "");
  // map label: "provider: short title", the provider left out when the title already opens with it
  const mapLabel = (it) => { const p = String(it.provider || ""), t = String(it.title || "");
    return p && !t.toLowerCase().startsWith(p.toLowerCase()) ? `${p}: ${cut(t, 36)}` : cut(t, 44); };

  // ---------- layers ----------
  const ids = (k) => ["ou-" + k].concat(k === "cellular" ? ["ou-cellular-ring"] : []);
  const legend = (c) => {
    const dot = (z, op) => `<i class="lsw dot" style="background:${c.color};width:${z}px;height:${z}px${op ? ";opacity:" + op : ""}"></i>`;
    return `<span title="Dot size by severity">${dot(12)}${dot(10)}${dot(8)}${dot(6)}critical → info</span><span>${dot(9)}active</span><span>${dot(5, 0.35)}resolved</span>`
      + (c.key === "power" ? "<span>US counties: size = customers out</span>" : "")
      + (c.key === "cellular" ? `<span><i class="lsw ring" style="border-color:${c.color}"></i>RU regional shutdown</span><span><i class="lsw ring" style="border-color:${c.color};background:${c.color}73"></i>whitelists only</span>` : "");
  };
  CFG.forEach((c) => GTX.layer({ key: c.key, label: c.label, feed: c.key, after: c.after,
    ids: ids(c.key).concat(["ou-" + c.key + "-lbl"]), click: ids(c.key), clickBefore: "th-pt",
    count: () => { const d = D(c.key); return d ? arr(d.items).filter((i) => i && i.active).length : null; }, legend: legend(c) }));

  const act = ["get", "active"];
  // radius: resolved 4; a US county with customers out by ln(customers) (100 → 5, 10,000 → 9, 1,000,000 → 15); else by severity
  const RADIUS = ["case", ["!", act], 4,
    [">", ["get", "cust"], 0], ["interpolate", ["linear"], ["ln", ["+", 1, ["get", "cust"]]], 4.6, 5, 9.2, 9, 13.8, 15],
    ["match", ["get", "sev"], "critical", SEV.critical[2], "major", SEV.major[2], "minor", SEV.minor[2], SEV.info[2]]];
  const FC = {};  // the drawn collections, kept so a feed that lands before the map's load event is still drawn
  GTX.onMapLoad((map) => {
    CFG.forEach((c) => {
      const k = c.key, src = "ou-" + k, vis = { visibility: GTX.layerOn(k) ? "visible" : "none" };
      const ring = k === "cellular" ? ["==", ["get", "kind"], "shutdown"] : null;
      map.addSource(src, { type: "geojson", data: FC[k] || empty });
      map.addLayer(Object.assign({ id: src, type: "circle", source: src, layout: Object.assign({ "circle-sort-key": ["get", "rank"] }, vis), paint: {
        "circle-radius": RADIUS, "circle-color": c.color, "circle-opacity": ["case", act, 0.9, 0.35],
        "circle-stroke-width": ["case", act, 1, 0], "circle-stroke-color": "#0b0e11" } }, ring ? { filter: ["!", ring] } : {}), GTX.below.events);
      // Russia's regional mobile shutdowns (one point per federal subject): a ring, filled where only whitelisted sites work
      if (ring) map.addLayer({ id: "ou-cellular-ring", type: "circle", source: src, filter: ring, layout: Object.assign({ "circle-sort-key": ["get", "rank"] }, vis), paint: {
        "circle-radius": ["case", act, 8, 5], "circle-color": c.color, "circle-opacity": ["case", act, ["case", ["get", "wl"], 0.45, 0.12], 0.04],
        "circle-stroke-width": ["case", act, 2.2, 1.2], "circle-stroke-color": c.color, "circle-stroke-opacity": ["case", act, 0.95, 0.35] } }, GTX.below.events);
      // labels: active items only, one per item (an item over several oblasts is named once), from zoom 3.5
      map.addLayer({ id: src + "-lbl", type: "symbol", source: src, minzoom: 3.5, filter: ["all", ["==", act, true], ["==", ["get", "first"], true]],
        layout: Object.assign({ "text-field": ["get", "lbl"], "text-size": 10.5, "text-offset": [0, 1.1], "text-anchor": "top", "text-max-width": 14,
          "text-optional": true, "text-font": ["Open Sans Regular"] }, vis),
        paint: { "text-color": c.color, "text-halo-color": "#0b0e11", "text-halo-width": 1.2 } }, GTX.below.events);
    });
  });

  // ---------- data ----------
  // IT: feed -> Map(item id -> item). The server keeps summary and metric out of the GeoJSON, and translations are
  // applied to the items only, so popups, labels and sizes read the item (the feature's pid is its id).
  const IT = {};
  const find = (pid) => { for (const k of KEYS) { const m = IT[k]; if (m && m.has(pid)) return [k, m.get(pid)]; } return null; };
  function features(k, d) {
    const items = IT[k], seen = new Set();
    return arr((d.geojson || {}).features).filter((f) => f && f.properties && f.geometry && f.geometry.type === "Point" && llOk(f.geometry.coordinates)).map((f) => {
      const p = f.properties, pid = String(p.pid || p.id || "");
      if (!items.has(pid)) items.set(pid, p);  // an item the caps left out of the list: the popup uses the point's own fields
      const it = items.get(pid), sev = SEV[it.severity] ? it.severity : "info";
      // a numeric `customers` on the point wins (if the server adds one); else the item's metric
      const cust = k === "power" ? Number(p.customers != null ? p.customers : (it.metric || {}).customers) || 0 : 0;
      const first = !seen.has(pid);
      seen.add(pid);
      // a point's own region (an item over several oblasts or federal subjects) and Russia's whitelist flag, when sent
      return { type: "Feature", geometry: { type: "Point", coordinates: f.geometry.coordinates }, properties: {
        pid, active: !!it.active, sev, rank: (it.active ? 10 : 0) + RANK[sev], kind: String(it.kind || ""), cust: cust > 0 ? cust : 0, lbl: mapLabel(it), first,
        rg: String(p.region_name || p.region || ""), wl: p.whitelist === true } };
    });
  }
  CFG.forEach((c) => GTX.feed(c.key, (d) => {
    const m = new Map();
    arr(d.items).forEach((it) => { if (it && it.id) m.set(String(it.id), it); });
    IT[c.key] = m;
    FC[c.key] = { type: "FeatureCollection", features: features(c.key, d) };
    const s = GTX.map.getSource("ou-" + c.key);
    if (s) s.setData(FC[c.key]);
    streams(); rows();
    if (GTX.isOpen("outages")) renderTab(document.getElementById("tab-outages"));
  }));

  // ---------- Feed tab ----------
  function feedItem(c, it, short) {
    const cc = arr(it.cc).filter((x) => typeof x === "string" && x);
    const th = cc.map((x) => (GTX.country(x) || {}).th).filter((t, n, a) => t && a.indexOf(t) === n);
    const ll = llOk(it.ll);
    return { id: "ou:" + it.id, ts: tsOf(it), day: false, title: it.title, url: it.url, where: it.where || "", th, ll, zoom: ZOOM[it.place] || 4,
      cc: cc.length ? cc : undefined, cat: c.cat, badge: it.active ? sevOf(it)[0] : "resolved", label: `${short} · ${it.provider || it.source || "?"}`,
      text: [it.summary, arr(it.regions).join(" "), it.provider].filter(Boolean).join(" "),
      tr: it.translated ? { from: it.translated.from || it.lang || "", orig: it.title_orig || "" } : undefined,
      pop: ll ? () => openItem(c.key, it) : undefined };
  }
  // A feed's stream (and its Feed chip) is registered once the server runs that feed, so a page without these feeds
  // gets no empty chips. The order stays fixed: power, cell, web, cloud, as the status reply lists them.
  const REG = new Set();
  function streams() {
    const st = GTX.S.status || {};
    CFG.forEach((c) => {
      if (REG.has(c.key) || !(c.key in st || D(c.key))) return;
      REG.add(c.key);
      GTX.stream({ key: c.key, group: c.group, label: c.short, data: () => D(c.key), items: (d) => arr(d.items).filter((i) => i && i.id).map((i) => feedItem(c, i, c.short)) });
      // NetBlocks / Cloudflare Radar internet disruptions that are neither power nor mobile: the Internet group
      if (c.key === "cellular") GTX.stream({ key: "cellnet", group: "internet", label: "Internet", data: () => D("cellular"),
        items: (d) => arr(d.internet).filter((i) => i && i.id).map((i) => feedItem(c, i, "Internet")) });
    });
  }
  // Layer rows for feeds this page does not have (the public copy) are hidden once the status reply is in.
  function rows() {
    const st = GTX.S.status || {};
    if (!Object.keys(st).length) return;
    CFG.forEach((c) => {
      const inp = document.querySelector(`#layers input[data-layer="${c.key}"]`), lab = inp && inp.closest("label");
      if (!lab) return;
      const off = !(c.key in st) && !D(c.key), lg = lab.nextElementSibling;
      lab.style.display = off ? "none" : "";
      if (lg && lg.classList.contains("aclegend")) lg.style.display = off ? "none" : "";
    });
  }
  GTX.onRender(() => { streams(); rows(); });

  // ---------- popups ----------
  function regionHtml(k, it) {
    const regs = arr(it.regions).filter(Boolean);
    if (!regs.length) return "";
    const ru = {};
    if (k === "cellular") arr((D("cellular") || {}).russia && D("cellular").russia.regions).forEach((r) => { if (r && r.code) ru[r.code] = r; });
    const names = regs.slice(0, 12).map((code) => { const r = ru[code];
      return r ? `${esc(r.name || code)} <span class="muted">(${[r.shutdown ? "shutdown" : "", r.whitelist ? "whitelist" : ""].filter(Boolean).join(", ") || "listed"})</span>` : esc(code); });
    if (regs.length === 1 && !ru[regs[0]] && String(it.where || "").includes(regs[0])) return "";
    return `<div class="small">${regs.length === 1 ? "Region" : "Regions"}: ${names.join(", ")}${regs.length > 12 ? ` +${regs.length - 12} more` : ""}</div>`;
  }
  const linkText = (it) => {
    const u = String(it.url || "");
    if (String(it.source || "").startsWith("radar_"))   // Cloudflare Radar API records (1.5.4)
      return u.includes("radar.cloudflare.com/outage-center") ? "Radar Outage Center"
        : u.includes("radar.cloudflare.com/traffic/") ? "Radar traffic page" : "Cloudflare's post";
    return it.kind === "post" ? "Post" : it.kind === "news" ? "Article" : "Official status";
  };
  function itemHtml(k, it, here) {
    const c = BY[k], d = D(k) || {}, sv = sevOf(it), u = link(it.url), ts = tsOf(it);
    const srcRow = arr(d.sources).find((s) => s && s.name === it.source);
    const cust = Number((it.metric || {}).customers) || 0;
    const times = [it.start_ms ? `Started ${when(it.start_ms)}` : "", ts ? `Updated ${when(ts)}` : "",
      it.end_ms ? `${it.end_ms > Date.now() ? "Ends" : "Ended"} ${when(it.end_ms)}` : ""].filter(Boolean);
    const note = [`Source: ${(srcRow && srcRow.label) || it.source || c.short}`,
      (k === "websites" || k === "cloud") && it.kind === "status" ? "the provider's own report" : "",
      PLACE[it.place] && llOk(it.ll) ? PLACE[it.place] : llOk(it.ll) ? "" : "not on the map"].filter(Boolean).join(" · ");
    return `<h5>${esc(it.title || "Outage")}</h5>
      <div class="meta"><span style="color:${c.color}">●</span> ${esc(c.short)} · ${esc(it.provider || it.source || "")}</div>
      <div class="ou-b">${badge(sv[0], sv[1])}${it.active ? badge(it.status || "active") : badge("resolved", "#3ecf8e")}${trTag(it)}</div>
      ${times.length ? `<div class="small">${times.join("<br>")}</div>` : ""}
      ${it.where ? `<div>${esc(it.where)}</div>` : ""}${here ? `<div class="small">Here: <b>${esc(here)}</b></div>` : ""}${regionHtml(k, it)}
      ${cust ? `<div>Customers out: <b>${nf(cust)}</b></div>` : ""}
      ${it.summary ? `<div class="post"${it.summary_orig ? ` title="${esc("Original: " + it.summary_orig)}"` : ""}>${esc(it.summary)}</div>` : ""}
      ${u ? `<div><a href="${esc(u)}" target="_blank" rel="noopener">${linkText(it)} ↗</a></div>` : ""}
      <div class="muted small">${esc(note)}</div>`;
  }
  function alsoHtml(k, it) {
    const u = link(it.url), sv = sevOf(it);
    return `<div class="ou-also"><div>${u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(it.title || "Outage")}</a>` : esc(it.title || "Outage")}</div>
      <div class="muted small"><span style="color:${BY[k].color}">●</span> ${esc(BY[k].short)} · ${esc(it.provider || "")} · ${it.active ? badge(sv[0], sv[1]) : badge("resolved", "#3ecf8e")} · ${when(tsOf(it))}</div></div>`;
  }
  // On phones a tall popup scrolls, and MapLibre focuses its first link (near the bottom here) as it opens, which
  // scrolled the title out of view: start at the top.
  const show = (ll, html) => { const p = showPopup(ll, html); try { const el = p.getElement().querySelector(".pop"); if (el) el.scrollTop = 0; } catch (err) { /* no popup */ } };
  function openItem(k, it) {
    const ll = llOk(it.ll);
    if (ll) show(ll, `<div class="pop">${itemHtml(k, it)}</div>`);
  }
  const CLICK = [].concat(...KEYS.map(ids));
  // One popup per pin: the features of one item (several oblasts) share its pid and show once; other items drawn
  // at the same spot (a cloud region and a Cloudflare PoP in one city) are listed under it.
  function popupAt(f, lngLat) {
    const map = GTX.map;
    let hits = [];
    try { hits = map.queryRenderedFeatures(map.project(lngLat), { layers: CLICK.filter((l) => map.getLayer(l) && map.getLayoutProperty(l, "visibility") !== "none") }); } catch (err) { hits = []; }
    const pids = [f.properties.pid].concat(hits.map((h) => h.properties && h.properties.pid)).map((p) => String(p || "")).filter((p, n, a) => p && a.indexOf(p) === n);
    const own = find(pids[0]), found = pids.map(find).filter(Boolean);
    if (!found.length) return;
    const [k, it] = found[0], more = found.slice(1, 4), rest = found.length - 1 - more.length;
    const here = own && arr(it.regions).length > 1 ? f.properties.rg : "";  // which of the item's regions was clicked
    show(lngLat, `<div class="pop">${itemHtml(k, it, here)}${more.length ? `<div class="sub">Also here</div>${more.map(([k2, i2]) => alsoHtml(k2, i2)).join("")}` : ""}${rest > 0 ? `<div class="muted small">+${rest} more at this spot</div>` : ""}</div>`);
  }
  CLICK.forEach((id) => GTX.popup(id, popupAt));

  // ---------- Outages tab ----------
  const card = (title, body, summary) => `<div class="card"><h4>${esc(title)}</h4>${summary ? `<div class="small">${esc(summary)}</div>` : ""}${body}</div>`;
  const quiet = (t) => `<div class="muted small">${esc(t)}</div>`;
  const kv = (name, html, t) => `<div class="ou-r"><div class="ou-k">${esc(name)}</div><div>${html}${t ? ` <span class="muted small">· ${when(t)}</span>` : ""}</div></div>`;
  function gridCard() {
    const d = D("power");
    if (!d) return card("Grid", quiet("No power data yet."));
    const g = d.grid || {}, us = d.us, out = [];
    const tp = g.taipower, es = g.eskom, ca = g.caiso;
    if (tp) { const L = LIGHT[tp.light] || [tp.light || "?", "#9aa4ae", ""];
      out.push(kv("Taiwan (Taipower)", `${badge(L[0] + " light", L[1])} ${esc(L[2])}${tp.reserve_pct != null ? ` · reserve <b>${esc(tp.reserve_pct)}%</b>` : ""}${tp.load_mw != null ? ` · load ${nf(tp.load_mw)} MW` : ""}`, tp.t)); }
    if (es) out.push(kv("South Africa (Eskom)", es.stage ? `<b style="color:#f2853d">Load shedding stage ${esc(es.stage)}</b>` : "No load shedding", es.t));
    if (ca) out.push(kv("California (CAISO)", ca.events ? `<b style="color:#f2b33d">${nf(ca.events)} grid event${ca.events === 1 ? "" : "s"}</b>${arr(ca.names).length ? ": " + esc(arr(ca.names).slice(0, 4).join(", ")) : ""}` : "No grid emergency", ca.t));
    if (us) out.push(kv("United States (ODIN)", `<b>${nf(us.meters_out)}</b> customers out · ${nf(us.counties)} counties at or over the threshold · ${nf(us.utilities)} utilities reporting`, us.t));
    return card("Grid", out.length ? `<div class="ou-kv">${out.join("")}</div>` : quiet("No grid data yet."), d.summary);
  }
  function boardHtml(name, d) {
    if (!d) return "";
    const chips = arr(d.board).filter(Boolean).map((r) => {
      const [t, col] = BOARD[r.status] || BOARD.unknown, u = link(r.url);
      const tip = `${r.provider || r.source}: ${t}${r.active ? `, ${r.active} active` : ""}`;
      const inner = `<i style="background:${col}"></i>${esc(r.provider || r.source)}${r.status !== "operational" ? ` <span class="muted">${esc(t)}</span>` : ""}`;
      return u ? `<a class="chip" href="${esc(u)}" target="_blank" rel="noopener" title="${esc(tip + ". Open the status page")}" style="border-color:${col}">${inner}</a>`
        : `<span class="chip" title="${esc(tip)}" style="border-color:${col}">${inner}</span>`;
    }).join("");
    return `<div class="sub">${esc(name)}</div><div class="chips ou-board">${chips || quiet("No status pages yet.")}</div>`;
  }
  function servicesCard() {
    const w = D("websites"), c = D("cloud");
    if (!w && !c) return card("Online services", quiet("No status-page data yet."));
    const p = c && c.pops;
    const pops = p ? `<div class="small ou-pops">Cloudflare data centres (PoPs): <b>${nf(p.total)}</b> · partial outage <b>${nf(p.partial_outage || 0)}</b> · maintenance ${nf(p.under_maintenance || 0)}`
      + `${arr(p.named).length ? ` · in active incidents: ${esc(arr(p.named).slice(0, 20).join(", "))}` : ""}</div>` : "";
    return card("Online services", boardHtml("Websites / online services", w) + boardHtml("AI / cloud / datacenters", c) + pops, [w && w.summary, c && c.summary].filter(Boolean).join(" "));
  }
  function russiaCard() {
    const d = D("cellular");
    if (!d) return card("Russia: mobile internet shutdowns", quiet("No cell-network data yet."));
    const r = d.russia;
    if (!r) return card("Russia: mobile internet shutdowns", quiet("No shutdown map data yet."), d.summary);
    const regs = arr(r.regions).filter(Boolean);
    return card("Russia: mobile internet shutdowns", `<div class="row"><span>Map date <b>${when(r.date, false)}</b></span><span>Shutdown regions <b>${nf(r.shutdown_regions)}</b></span><span>Whitelist regions <b>${nf(r.whitelist_regions)}</b></span></div>`
      + (regs.length ? `<div class="chips ou-regs">${regs.map((x) => `<span class="chip" title="${esc(`${x.code || ""}: ${[x.shutdown ? "mobile internet shut down" : "", x.whitelist ? "whitelist only" : ""].filter(Boolean).join(", ") || "listed"}`)}">`
        + `<i style="${x.shutdown ? "background:#4ade80" : "border:1px solid #4ade80;box-sizing:border-box"}"></i>${esc(x.name || x.code)}${x.whitelist ? ' <span class="muted">whitelist</span>' : ""}</span>`).join("")}</div>`
        : quiet("No regions listed on the latest map.")), d.summary);
  }
  function activeCard() {
    const all = [];
    KEYS.forEach((k) => arr((D(k) || {}).items).forEach((it) => { if (it && it.active && it.id) all.push([k, it]); }));
    all.sort((a, b) => tsOf(b[1]) - tsOf(a[1]));
    const shown = all.slice(0, 80);
    if (!shown.length) return card("Active now", quiet("Nothing active in these feeds."));
    return card(`Active now: ${nf(all.length)}`, `<ul class="feed ou-act">${shown.map(([k, it]) => {
      const c = BY[k], sv = sevOf(it), u = link(it.url), ll = llOk(it.ll);
      return `<li data-oupid="${esc(it.id)}" class="${ll ? "" : "nl"}" style="--c:${c.color}"><div class="t">${u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(it.title)}</a>` : esc(it.title)}</div>`
        + `<div class="m"><span class="time">${when(tsOf(it))}</span>${badge(c.short, c.color)}${badge(sv[0], sv[1])}<span>${esc(it.provider || it.source || "")}</span>${it.where ? `<span>${esc(it.where)}</span>` : ""}${trTag(it)}${ll ? VM : ""}</div></li>`;
    }).join("")}</ul>${all.length > shown.length ? quiet(`${nf(all.length - shown.length)} more not shown; the Feed tab lists them all.`) : ""}`);
  }
  function notesHtml() {
    const have = CFG.filter((c) => D(c.key));
    const attr = have.map((c) => D(c.key).attribution).filter(Boolean);
    const notes = have.map((c) => { const d = D(c.key);
      const src = arr(d.sources).filter(Boolean).map((s) => `<span${s.ok === false ? ` style="color:var(--bad)" title="${esc(String(s.error || "failing").slice(0, 200))}"` : ""}>${esc(s.label || s.name)}${s.ok === false ? " (failing)" : ""}</span>`).join(" · ");
      return `<div class="sub">${esc(c.label)}</div>${d.note ? `<div class="small">${esc(d.note)}</div>` : ""}`
        + `<div class="muted small">${d.fetched_at ? "Updated " + when(d.fetched_at) : ""}${d.trimmed ? ` · ${nf(d.trimmed)} older items trimmed` : ""}${src ? " · Sources: " + src : ""}</div>`; }).join("");
    return `<div class="card"><details><summary>How these feeds are built, and their sources</summary>${notes}</details>`
      + `${attr.length ? `<div class="muted small" style="margin-top:6px">${attr.map(esc).join(" ")}</div>` : ""}`
      + `<div class="muted small" style="margin-top:6px">Status pages are the providers' own reports: an outage a provider does not post does not show. Positions are approximate (headquarters, region city, country centre). Personal, non-commercial use.</div></div>`;
  }
  function renderTab(el) {
    if (!el) return;
    const st = GTX.S.status || {};
    if (!KEYS.some((k) => D(k))) {
      const absent = Object.keys(st).length && !KEYS.some((k) => k in st);
      el.innerHTML = card("Outages", quiet(absent ? "Not on this copy: the outage feeds (power, cell networks, websites, AI / cloud) run on the self-hosted page only."
        : "No outage data yet."));
      return;
    }
    el.innerHTML = gridCard() + servicesCard() + russiaCard() + activeCard() + notesHtml();
    el.onclick = (e) => {
      const li = e.target.closest("li[data-oupid]");
      if (!li || (e.target.closest("a") && !e.target.closest(".vm"))) return;  // the title opens the source
      const r = find(li.dataset.oupid), ll = r && llOk(r[1].ll);
      if (!ll) return;
      GTX.map.flyTo({ center: ll, zoom: Math.max(GTX.map.getZoom(), ZOOM[r[1].place] || 4), speed: 1.6 });
      openItem(r[0], r[1]);
      if (window.innerWidth <= 900) window.scrollTo(0, 0);
    };
  }
  GTX.tab({ id: "outages", label: "Outages", before: "sources", render: renderTab });

  // ---------- header tiles, Sources tab ----------
  GTX.kpi(() => {
    const out = [], w = D("websites"), c = D("cloud"), p = D("power"), cl = D("cellular");
    const bad = arr(w && w.board).concat(arr(c && c.board)).filter((r) => r && DEGRADED.has(r.status));
    if (bad.length) out.push([nf(bad.length), "Services degraded", bad.some((r) => r.status === "major") ? "bad" : true]);
    const us = p && p.us;
    if (us && us.meters_out >= 10000) out.push([nf(us.meters_out), "US customers out (ODIN)", us.meters_out >= 250000]);
    const ru = cl && cl.russia;
    if (ru && ru.shutdown_regions > 0) out.push([nf(ru.shutdown_regions), "RU mobile shutdown regions", true]);
    return out;
  });
  CFG.forEach((c) => { GTX.label(c.key, c.src); GTX.credit(c.credit); });
});
