// Ground Truth 1.7.0: open the theme this browser chose last. index.html (the Classic theme) loads this first.
// Only on a plain visit: a query or a hash means a link to a Classic view, so the page stays on Classic.
// themes/switch.js writes the key when a theme is picked. The URL is relative, so it works under /gt/ and ingress.
(function () {
  try {
    var t = localStorage.getItem("gt.theme");
    if (/^(dispatch|atlas|floor)$/.test(t) && !location.search && !location.hash) location.replace(t + ".html");
  } catch (e) { /* storage blocked: stay on Classic */ }
})();
