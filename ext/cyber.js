// Ground Truth page extension: cyber and internet infrastructure (0.13.0, ext 1.0; ext 1.1, 1.2.0: Feed-tab streams;
// ext 1.2, 1.3.0: times in the page's zone with the time since; ext 1.3, 1.4.0: Feed items carry cc (country) for the title bar;
// ext 1.4, 1.4.2: the layer starts on, like every layer).
// A country layer (ransomware claims, critical-infrastructure claims or DDoS targets, 7 days; red outline where
// RIPE routing shows a drop) and a Cyber tab: SANS ISC infocon, CISA KEV / ICS / alerts, ransomware claims (no
// victim names are stored), press-reported attacks, DDoSia target lists and the 19-country routing table.
// Feeds: /api/feed/cyber, /api/feed/bgp (gt/cyber.py); shapes: /api/cyber_geo. Private: never on the public mirror.
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const { esc, fmtT, fmtD, isoMs, nf, ago, showPopup } = GTX;
  const empty = { type: "FeatureCollection", features: [] };
  // one teal (the page's "Comms / outage" colour) for every metric: one metric shows at a time, and teal keeps clear of
  // the violet outage fill and the red/orange advisory fill
  const CY = "#2dd4bf";
  const METRICS = { ransom_7d: "Ransomware claims", ransom_ci_7d: "Critical infrastructure", ddos_7d: "DDoS targets" };
  const BGP = { drop: "#f05252", dip: "#f2b33d" };
  const KINDS = { kev: "KEV", ics: "ICS", cisa: "CISA", ransom: "Ransomware", attack: "Press", ddos: "DDoS" };
  const RWL = `<a href="https://www.ransomware.live" target="_blank" rel="noopener">Source: Ransomware.live</a>`;
  const ui = { metric: "ransom_7d", kinds: new Set(Object.keys(KINDS)), ci: false };
  const F = () => GTX.S.feeds;
  const when = (v, rel) => GTX.when(v, rel);  // 1.3.0: the page's zone (Eastern or UTC) and the time since
  const link = (u) => (/^https?:\/\//i.test(u || "") ? u : null);  // 1.7.3: only http(s) addresses become links
  const pct = (v) => (v == null ? "–" : (v > 0 ? "+" : "") + (Math.round(v * 10) / 10) + "%");

  GTX.layer({ key: "cyber", label: "Cyber: ransomware, DDoS targets, routing drops (7 d)", feed: "cyber", after: "outages",
    ids: ["cy-fill", "cy-bgp"], click: ["cy-fill"], clickBefore: "adv-fill",
    count: () => Object.keys((F().cyber || {}).by_country || {}).length || null,
    legend: Object.entries(METRICS).map(([k, t]) => `<button class="chip${k === ui.metric ? "" : " off"}" data-cymetric="${k}" title="Shade countries by ${t.toLowerCase()}"><i style="background:${CY}"></i>${t}</button>`).join("") +
      `<span><i class="lsw ring" style="border-color:${BGP.drop}"></i>routing drop</span><span><i class="lsw ring" style="border-color:${BGP.dip}"></i>dip</span>` });

  function fillColor() {
    return ["case", [">", ["coalesce", ["get", ui.metric], 0], 0], CY, "rgba(0,0,0,0)"];
  }
  function fillOpacity() {  // log scale: 1 claim faint, ~100 strong
    return ["interpolate", ["linear"], ["ln", ["+", 1, ["coalesce", ["get", ui.metric], 0]]], 0, 0, 0.7, 0.1, 4.6, 0.42];
  }
  GTX.onMapLoad((map) => {
    map.addSource("cyber", { type: "geojson", data: empty });
    const vis = { visibility: GTX.layerOn("cyber") ? "visible" : "none" };
    map.addLayer({ id: "cy-fill", type: "fill", source: "cyber", layout: vis, paint: { "fill-color": fillColor(), "fill-opacity": fillOpacity() } }, "out-fill");
    map.addLayer({ id: "cy-bgp", type: "line", source: "cyber", layout: vis, filter: ["in", ["get", "bgp"], ["literal", ["drop", "dip"]]],
      paint: { "line-color": ["match", ["get", "bgp"], "drop", BGP.drop, BGP.dip], "line-width": 2.5, "line-opacity": 0.9 } }, "out-fill");
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-cymetric]");
    if (!b) return;
    e.preventDefault();
    ui.metric = b.dataset.cymetric;
    document.querySelectorAll("[data-cymetric]").forEach((x) => x.classList.toggle("off", x !== b));
    const m = GTX.map;
    if (m.getLayer("cy-fill")) { m.setPaintProperty("cy-fill", "fill-color", fillColor()); m.setPaintProperty("cy-fill", "fill-opacity", fillOpacity()); }
  });

  // 1.7.3: the cyber and routing feeds land together, so one request serves both (it was asked for twice at every load)
  let geoT = null;
  const loadGeo = () => { if (geoT) return; geoT = setTimeout(() => { geoT = null;
    GTX.api("cyber_geo").then((fc) => { const s = GTX.map.getSource("cyber"); if (s) s.setData(fc || empty); }).catch(() => {}); }, 1000); };
  const redraw = () => { if (GTX.isOpen("cyber")) renderTab(document.getElementById("tab-cyber")); };
  GTX.feed("cyber", () => { loadGeo(); redraw(); });
  GTX.feed("bgp", () => { loadGeo(); redraw(); });
  // 1.2.0 (ext 1.1): incidents and RIPE routing drops / dips also run in the main Feed tab, placed by country.
  const ths = (cs) => (cs || []).map((c) => (GTX.country(c) || {}).th).filter(Boolean);
  const firstLl = (cs) => { for (const c of cs || []) { const k = GTX.country(c); if (k && k.ll) return k.ll; } return null; };
  // 1.3.0: CISA KEV entries and press-reported attacks carry a date only (sent as UTC midnight); they show as that day
  const dayOnly = (i) => (i.kind === "kev" || i.kind === "attack") && (i.ts_ms || isoMs(i.ts)) % 86400000 === 0;
  // 1.4.0 (ext 1.3): cc = the incident's countries (ISO-3) or the routing row's country, for the Feed row's title bar
  GTX.stream({ key: "cyber", group: "cyber", label: "Cyber", data: () => F().cyber, items: (d) => (d.items || []).map((i) => ({
    id: "cy:" + i.id, ts: i.ts_ms || isoMs(i.ts), day: dayOnly(i), title: i.title, url: i.url, label: "Cyber · " + (i.kind || "incident"),
    where: (i.countries || []).slice(0, 3).map((c) => (GTX.country(c) || {}).name || c).join(", "), badge: i.ci ? "critical infra" : i.sector || "",
    text: (i.tags || []).join(" "), th: ths(i.countries), ll: firstLl(i.countries), zoom: 4, cc: (i.countries || []).length ? i.countries : undefined })) });
  GTX.stream({ key: "bgp", group: "internet", label: "RIPE routing", data: () => F().bgp, items: (d) => (d.countries || []).filter((r) => r.level === "drop" || r.level === "dip").map((r) => ({
    id: "bgp:" + r.a3 + r.latest, ts: isoMs(r.latest), title: `Routing ${r.level}: ${r.name}`, url: r.url, text: (r.reasons || []).join(", "),
    where: (r.reasons || []).slice(0, 2).join(", "), th: r.theatre || null, ll: firstLl([r.a3]), zoom: 4, cc: r.a3 || undefined })) });

  GTX.popup("cy-fill", (f, lngLat) => {
    const p = f.properties;
    const rows = [
      p.ransom_7d ? `<div>Ransomware claims, 7 d: <b>${nf(p.ransom_7d)}</b> (${nf(p.ransom_ci_7d || 0)} critical infrastructure, ${nf(p.ransom_24h || 0)} in 24 h)</div>` : "",
      p.sectors ? `<div class="muted small">CI sectors: ${esc(p.sectors)}</div>` : "",
      p.groups ? `<div class="muted small">Groups: ${esc(p.groups)}</div>` : "",
      p.attacks_7d ? `<div>Press-reported attacks, 7 d: <b>${nf(p.attacks_7d)}</b></div>` : "",
      p.ddos_7d ? `<div>DDoSia target hosts, 7 d: <b>${nf(p.ddos_7d)}</b>${p.ddos_now ? ` (${nf(p.ddos_now)} on today's list)` : ""}</div>` : "",
      p.bgp ? `<div>${p.bgp === "drop" || p.bgp === "dip" ? `<span class="badge" style="border-color:${BGP[p.bgp]};color:${BGP[p.bgp]}">routing ${esc(p.bgp)}</span> ` : ""}Routing (RIPE): IPv4 prefixes ${pct(p.bgp_v4)}, ASNs ${pct(p.bgp_asns)} vs 7-day baseline${p.bgp_reasons ? `<div class="muted small">${esc(p.bgp_reasons)}</div>` : ""}
        <div><a href="https://stat.ripe.net/${esc(p.bgp_a2 || "")}" target="_blank" rel="noopener">RIPEstat ↗</a> · <a href="https://ioda.inetintel.cc.gatech.edu/country/${esc(p.bgp_a2 || "")}" target="_blank" rel="noopener">IODA ↗</a></div></div>` : "",
    ].join("");
    showPopup(lngLat, `<div class="pop"><h5>${esc(p.name)}: cyber, 7 days</h5>${rows || `<div class="muted">Nothing in the window.</div>`}
      <div class="muted small" style="margin-top:6px">Ransomware entries are the groups' own leak-site claims, not confirmed. ${RWL}. DDoSia: witha.name. Routing: RIPE RIS via RIPEstat.</div></div>`);
  });

  function renderTab(el) {
    if (!el) return;
    const c = F().cyber, b = F().bgp;
    if (!c && !b) { el.innerHTML = `<div class="muted small">No cyber data yet.</div>`; return; }
    const info = (c || {}).infocon || {};
    // up to 30 per kind, so the many ransomware claims do not push KEV, ICS and CISA items out (the feed is newest first)
    const per = {}, items = ((c || {}).items || []).filter((i) => ui.kinds.has(i.kind) && (!ui.ci || i.ci) && (per[i.kind] = (per[i.kind] || 0) + 1) <= 30);
    const bgpRows = ((b || {}).countries || []).map((r) => `<tr><td>${esc(r.name)}</td>
      <td style="color:${BGP[r.level] || "var(--muted)"}">${esc(r.level)}</td><td>${pct((r.pct || {}).v4)}</td><td>${pct((r.pct || {}).asns)}</td>
      <td>${link(r.url) ? `<a href="${esc(link(r.url))}" target="_blank" rel="noopener">RIPE</a>` : ""}</td></tr>`).join("");
    el.innerHTML = `<div class="card"><h4>Threat level <span class="badge" style="color:${info.level === "green" ? "var(--ok)" : "var(--accent)"}">SANS ISC ${esc(info.level || "?")}</span></h4>
        <div class="small">${esc((c || {}).summary || "")}</div></div>
      <div class="card"><h4>Internet routing, 19 watched countries</h4><div class="small">${esc((b || {}).summary || "No routing data yet.")}</div>
        <table class="src"><tr><th>Country</th><th>Level</th><th>IPv4</th><th>ASNs</th><th></th></tr>${bgpRows}</table></div>
      <div class="chips" id="cykinds">${Object.entries(KINDS).map(([k, t]) => `<button class="chip${ui.kinds.has(k) ? "" : " off"}" data-cykind="${k}">${t}</button>`).join("")}
        <button class="chip${ui.ci ? "" : " off"}" data-cyci="1">Critical infrastructure only</button></div>
      <ul class="feed">${items.map((i) => `<li style="--c:${i.ci ? CY : "var(--dim)"}"><div>${link(i.url) ? `<a href="${esc(link(i.url))}" target="_blank" rel="noopener">${esc(i.title)}</a>` : esc(i.title)}</div>
        <div class="muted small"><span class="badge">${esc(KINDS[i.kind] || i.kind)}</span> ${dayOnly(i) ? GTX.fmtDay(i.ts_ms || i.ts) : when(i.ts)}${(i.countries || []).length ? " · " + esc(i.countries.join(", ")) : ""}${i.sector ? " · " + esc(String(i.sector).slice(0, 60)) : ""}${i.cvss ? " · CVSS " + esc(i.cvss) : ""}</div></li>`).join("")}</ul>
      <div class="muted small">Ransomware claims are the groups' own leak-site posts, not confirmed; victim names are not stored. ${RWL} (non-commercial).
        CISA: public domain / CC0. SANS ISC (CC BY-NC-SA). DDoSia target lists: witha.name. Routing: RIPEstat (no redistribution).</div>`;
    el.querySelector("#cykinds").onclick = (e) => {
      const k = e.target.closest("[data-cykind]"), ci = e.target.closest("[data-cyci]");
      if (k) { ui.kinds.has(k.dataset.cykind) ? ui.kinds.delete(k.dataset.cykind) : ui.kinds.add(k.dataset.cykind); }
      else if (ci) ui.ci = !ui.ci; else return;
      renderTab(el);
    };
  }
  GTX.tab({ id: "cyber", label: "Cyber", before: "sources", render: renderTab });

  GTX.kpi(() => {
    const b = F().bgp, out = [];
    if (b && (b.drops || []).length) out.push([nf(b.drops.length), "Routing drops (RIPE)", true]);
    return out;
  });
  GTX.label("cyber", "Cyber: CISA, Ransomware.live, SANS ISC, DDoSia");
  GTX.label("bgp", "Internet routing per country (RIPEstat)");
  GTX.credit(`Cyber: CISA (public domain / CC0), ${RWL} (non-commercial), SANS Internet Storm Center, witha.name DDoSia lists,
    and RIPE NCC RIPEstat routing data.`);
});
