// Ground Truth private views loader (1.8.0, private 1.0). Shared by every theme page; generic and public.
// A server may carry extra pages' code in web/private/ (kept out of the public GitHub copy). Its /api/status lists
// them in "private_web"; this file loads exactly those scripts, one after another, in name order, then tells the
// theme which views exist. Where status has no such list (the public copy, an older server) it does nothing: no
// request, no error, no nav entry.
//
// For a private script:
//   var v = GTPrivate.view("econ");          // the view object for this id (created on first use)
//   v.title = "Economics"; v.order = 10;
//   v.render.dispatch = function (host, ctx) {...};   // one renderer per theme id: classic dispatch atlas floor
// A theme asks GTPrivate.onViews(function (views) {...}); it gets only views that have a renderer for its id.
// ctx = { theme, esc, nf, pct, when, get(feed, maxAgeS), api(path), analysis() }.
(function () {
  "use strict";
  var theme = document.documentElement.getAttribute("data-gt-theme") || "classic";
  var views = {}, subs = [], G = window.GTPrivate = { theme: theme, ready: false };
  var cache = {};
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function nf(n, d) { n = Number(n); return Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits: d == null ? 2 : d, minimumFractionDigits: d == null ? 0 : d }) : "–"; }
  function pct(n) { n = Number(n); return Number.isFinite(n) ? (n > 0 ? "+" : "") + n.toFixed(2) + "%" : "–"; }
  function zone() { try { return localStorage.getItem("gt-tz") === "utc" ? "UTC" : "America/New_York"; } catch (e) { return "America/New_York"; } }
  // a moment as "Wed 9:05 PM EST" (Eastern am/pm by default, like every page; UTC when the page is set to it)
  function when(ms) {
    if (!Number.isFinite(Number(ms))) return "–";
    var z = zone(), f = new Intl.DateTimeFormat("en-US", { timeZone: z, weekday: "short", hour: "numeric", minute: "2-digit", hour12: z !== "UTC", timeZoneName: "short" });
    return f.format(new Date(Number(ms)));
  }
  function api(path) { return fetch(path, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); }); }
  // a feed's reply {ok, at, data, error}, reused for maxAgeS seconds (default 20) so several panels share one request
  function get(feed, maxAgeS) {
    var c = cache[feed], now = Date.now();
    if (c && now - c.t < (maxAgeS == null ? 20 : maxAgeS) * 1000) return c.p;
    var p = api("api/feed/" + feed);
    cache[feed] = { t: now, p: p }; p.catch(function () { if (cache[feed] && cache[feed].p === p) delete cache[feed]; });
    return p;
  }
  G.view = function (id) { return views[id] || (views[id] = { id: id, title: id, order: 50, render: {} }); };
  G.views = function () { return Object.keys(views).map(function (k) { return views[k]; }).filter(function (v) { return typeof v.render[theme] === "function"; }).sort(function (a, b) { return a.order - b.order || (a.id < b.id ? -1 : 1); }); };
  G.onViews = function (cb) { subs.push(cb); if (G.ready) cb(G.views()); };
  G.ctx = { theme: theme, esc: esc, nf: nf, pct: pct, when: when, get: get, api: api, analysis: function (id) { return api("api/private/" + (id || "econ") + "/analysis"); } };
  function done() { G.ready = true; subs.forEach(function (cb) { try { cb(G.views()); } catch (e) { console.error("private view", e); } }); }
  function loadNext(list, i, v) {
    if (i >= list.length) return done();
    var s = document.createElement("script");
    s.src = "private/" + list[i] + "?v=" + encodeURIComponent(v);
    s.onload = s.onerror = function () { loadNext(list, i + 1, v); };
    document.head.appendChild(s);
  }
  G.start = function () {
    api("api/status").then(function (j) {
      var others = ["classic", "dispatch", "atlas", "floor"].filter(function (t) { return t !== theme; });
      // a file named <name>-<theme id>.js belongs to that theme only: this page skips the other themes' files
      var list = Array.isArray(j && j.private_web) ? j.private_web.filter(function (n) {
        return /^[A-Za-z0-9_-]+\.js$/.test(n) && !others.some(function (t) { return n.slice(-(t.length + 4)) === "-" + t + ".js"; });
      }) : [];
      if (!list.length) return;  // nothing private here: stay silent
      loadNext(list, 0, (j && j.version) || "");
    }).catch(function () { /* no status: nothing to load */ });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", G.start); else G.start();
})();
