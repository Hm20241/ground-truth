// Ground Truth page extension: curated event sources (0.11.0, ext 1.1: 1.0.0 Brief columns).
// GeoConfirmed (verified geolocations), CIR Eyes on Russia (civilian harm, published ~1 week late) and
// S2 Underground Iran kinetic events join the event layer next to the source map's pins. The page drops a pin
// when the source map already carries the same post (see mergeEvents in app.js), so each event shows once.
// Feeds: /api/feed/geoconfirmed, /api/feed/cir, /api/feed/kinetic (gt/geoconfirmed.py, gt/curated.py).
(window.GTXQ = window.GTXQ || []).push((GTX) => {
  const NOTES = {
    geoconfirmed: "Geolocated by GeoConfirmed volunteers; the geolocation usually lands days after the event.",
    cir: "CIR publishes about a week after the event, on purpose.",
    kinetic: "Licensed CC BY-NC-SA 4.0; Ground Truth changed the layout and categories.",
  };
  const credit = (a) => (Array.isArray(a) ? a : a ? [{ text: String(a) }] : [])
    .map((x) => (typeof x === "string" ? x : x.text)).filter(Boolean).join("; ");

  Object.keys(NOTES).forEach((name) => {
    GTX.eventSource(name, (data) => {
      const att = credit(data.attribution);
      ((data.geojson || {}).features || []).forEach((f) => {
        const p = f.properties;
        p.attribution = p.attribution || att;
        p.source_note = NOTES[name];
      });
    });
  });

  // Brief tab, "All sources by theatre" (1.0.0): verified pins dated in the last 48 h, CIR over its whole window.
  const byTheatre = (name, hours) => {
    const d = GTX.S.feeds[name];
    if (!d) return null;
    const cut = hours ? Date.now() - hours * 3600e3 : 0, out = {};
    ((d.geojson || {}).features || []).forEach((f) => { const p = f.properties || {}; if (p.theatre && (p.ts_ms || 0) >= cut) out[p.theatre] = (out[p.theatre] || 0) + 1; });
    return out;
  };
  GTX.briefColumn({ label: "GeoConf. 48 h", title: "GeoConfirmed pins dated in the last 48 h", counts: () => byTheatre("geoconfirmed", 48),
    note: "GeoConfirmed counts pins dated in the last 48 h (geolocations land days late)." });
  GTX.briefColumn({ label: "CIR", title: "CIR Eyes on Russia entries in its window (~2 weeks, published a week late)", counts: () => byTheatre("cir", 0) });

  // Per-source counts under the "Curated events" layer row.
  const SRC = [["map", "Source map"], ["geoconfirmed", "GeoConfirmed"], ["cir", "CIR"], ["kinetic", "S2 Iran"]];
  GTX.legend("events", SRC.map(([k, t]) => `<span>${t} <b id="evsrc-${k}">–</b></span>`).join(""));
  GTX.onRender(() => {
    const n = {};
    ((GTX.S.events || {}).features || []).forEach((f) => {
      if (f.properties.kind !== "event") return;
      const k = f.properties.source || "map"; n[k] = (n[k] || 0) + 1;
    });
    SRC.forEach(([k]) => { const el = document.getElementById("evsrc-" + k); if (el) el.textContent = GTX.nf(n[k] || 0); });
  });

  GTX.label("geoconfirmed", "GeoConfirmed verified geolocations (14 days)");
  GTX.label("cir", "CIR Eyes on Russia: civilian harm, infrastructure (~1 week lag)");
  GTX.label("kinetic", "S2 Underground Iran kinetic events (CC BY-NC-SA 4.0)");
  GTX.credit(`Verified pins: <a href="https://geoconfirmed.org" target="_blank" rel="noopener">GeoConfirmed</a> and
    <a href="https://eyesonrussia.org" target="_blank" rel="noopener">CIR Eyes on Russia</a> (research use; not on the public mirror),
    and S2 Underground's Iran kinetic events map (<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener">CC BY-NC-SA 4.0</a>, layout changed).`);
});
