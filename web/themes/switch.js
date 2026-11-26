// Ground Truth theme switcher (1.7.0, switch 1.0). Shared by every theme page.
//
// A theme is one page at the web root (index.html, dispatch.html, atlas.html, floor.html) plus its own folder
// under themes/. Each page sets <html data-gt-theme="id"> and loads this file. The button is drawn where the page
// asks: give this script tag data-mount="#selector", or call GTTheme.mount(element).
// The choice is kept in this browser (localStorage "gt.theme"). index.html reads it and opens the chosen theme on a
// plain visit (no query, no hash). Every URL here is relative, so it works under /gt/ and Home Assistant ingress.
//
// Colours come from CSS variables a theme sets on :root (all optional):
//   --gtt-font --gtt-size --gtt-h --gtt-radius --gtt-bg --gtt-fg --gtt-line --gtt-accent
//   --gtt-menu-bg --gtt-menu-fg --gtt-menu-line --gtt-hover
(function () {
  "use strict";
  var THEMES = [
    { id: "classic", name: "Classic", href: "index.html", note: "Every layer and tab on one screen" },
    { id: "dispatch", name: "Dispatch", href: "dispatch.html", note: "A light page that reads like a newspaper" },
    { id: "atlas", name: "Atlas", href: "atlas.html", note: "Full-screen map with one panel" },
    { id: "floor", name: "Watch Floor", href: "floor.html", note: "A status board around the map" },
  ];
  var KEY = "gt.theme";
  var me = document.currentScript;
  var version = (((me && me.getAttribute("src")) || "").split("v=")[1] || "").split("&")[0];
  var current = document.documentElement.getAttribute("data-gt-theme") || "classic";
  var uid = 0, openMenu = null;

  // The browser tab names the copy being looked at (asked for 2026-11-25): the Mac's own run, the server, or the
  // public mirror. Home Assistant shows the server's copy, so it reads "Server" there too.
  function copyOf(host) {
    host = String(host || "").toLowerCase();
    if (/\.github\.io$/.test(host)) return "GitHub";
    if (host === "" || host === "localhost" || host === "127.0.0.1" || host === "[::1]" || host === "::1" || /\.localhost$/.test(host)) return "Local";
    return "Server";
  }
  var copy = copyOf(location.hostname);
  document.title = "Ground Truth: " + copy;

  function byId(id) { for (var i = 0; i < THEMES.length; i++) if (THEMES[i].id === id) return THEMES[i]; return null; }
  function saved() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function remember(id) { try { localStorage.setItem(KEY, id); } catch (e) { /* private window: the link still works */ } }
  function go(id) {
    var t = byId(id);
    if (!t) return false;
    remember(id);
    if (id !== current) location.href = t.href;
    return true;
  }

  var CSS = [
    ".gtt{position:relative;display:inline-block;font:var(--gtt-font,inherit);font-size:var(--gtt-size,14px);line-height:1.2}",
    ".gtt-btn{display:inline-flex;align-items:center;gap:.4em;min-height:var(--gtt-h,28px);margin:0;padding:0 .75em;border:1px solid var(--gtt-line,currentColor);border-radius:var(--gtt-radius,6px);background:var(--gtt-bg,transparent);color:var(--gtt-fg,inherit);font:inherit;letter-spacing:0;text-transform:none;white-space:nowrap;cursor:pointer}",
    ".gtt-btn:hover,.gtt-btn[aria-expanded=true]{border-color:var(--gtt-accent,currentColor)}",
    ".gtt-btn:focus-visible,.gtt-item:focus-visible{outline:2px solid var(--gtt-accent,currentColor);outline-offset:2px}",
    ".gtt-k{opacity:.72}.gtt-n{font-weight:600}.gtt-c{font-size:.72em;opacity:.72;transform:translateY(.05em)}",
    ".gtt-menu{position:fixed;z-index:2147483000;box-sizing:border-box;width:min(19em,calc(100vw - 16px));margin:0;padding:6px;border:1px solid var(--gtt-menu-line,rgba(128,128,128,.45));border-radius:10px;background:var(--gtt-menu-bg,#fff);color:var(--gtt-menu-fg,#14171c);font:var(--gtt-font,inherit);font-size:max(14px,var(--gtt-size,14px));line-height:1.3;box-shadow:0 12px 32px rgba(0,0,0,.38)}",
    ".gtt-menu[hidden]{display:none}",
    ".gtt-item{display:grid;grid-template-columns:1.1em 1fr;column-gap:.55em;align-items:start;box-sizing:border-box;width:100%;min-height:44px;margin:0;padding:.5em .6em;border:0;border-radius:6px;background:none;color:inherit;font:inherit;text-align:left;letter-spacing:0;text-transform:none;cursor:pointer}",
    ".gtt-item:hover,.gtt-item:focus-visible{background:var(--gtt-hover,rgba(128,128,128,.2))}",
    ".gtt-item b{font-weight:600}.gtt-item small{grid-column:2;font-size:1em;opacity:.78}",
    ".gtt-tick{grid-row:1 / span 2;font-weight:700}",
    ".gtt-foot{margin:4px 0 0;padding:.5em .6em .25em;border-top:1px solid var(--gtt-menu-line,rgba(128,128,128,.35));font-size:1em;opacity:.78}",
  ].join("\n");

  function addCss() {
    if (document.getElementById("gtt-css")) return;
    var s = document.createElement("style");
    s.id = "gtt-css"; s.textContent = CSS;
    document.head.appendChild(s);
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function close(focusBtn) {
    if (!openMenu) return;
    var m = openMenu; openMenu = null;
    m.menu.hidden = true;
    m.btn.setAttribute("aria-expanded", "false");
    if (focusBtn) m.btn.focus();
  }
  function place(m) {
    var r = m.btn.getBoundingClientRect(), menu = m.menu, vw = window.innerWidth, vh = window.innerHeight;
    menu.style.left = "0px"; menu.style.top = "0px";
    var w = menu.offsetWidth, h = menu.offsetHeight;
    var left = Math.max(8, Math.min(r.left, vw - w - 8));
    var below = r.bottom + 6, top = below + h <= vh - 8 || r.top - 6 - h < 8 ? below : r.top - 6 - h;
    menu.style.left = left + "px";
    menu.style.top = Math.max(8, Math.min(top, vh - h - 8)) + "px";
  }
  function open(m) {
    close(false);
    openMenu = m;
    m.menu.hidden = false;
    m.btn.setAttribute("aria-expanded", "true");
    place(m);
    var sel = m.menu.querySelector('[aria-checked="true"]') || m.menu.querySelector(".gtt-item");
    if (sel) sel.focus();
  }

  document.addEventListener("pointerdown", function (e) {
    if (openMenu && !openMenu.menu.contains(e.target) && !openMenu.btn.contains(e.target)) close(false);
  }, true);
  document.addEventListener("keydown", function (e) { if (openMenu && e.key === "Escape") { e.stopPropagation(); close(true); } }, true);
  window.addEventListener("resize", function () { if (openMenu) place(openMenu); });

  // Draw the button in `target` (an element or a selector). opts.label === false leaves out the word "Theme".
  function mount(target, opts) {
    var el = typeof target === "string" ? document.querySelector(target) : target;
    if (!el) return null;
    opts = opts || {};
    addCss();
    var cur = byId(current) || THEMES[0], id = "gtt-menu-" + (++uid);
    var wrap = document.createElement("span");
    wrap.className = "gtt";
    wrap.innerHTML = '<button type="button" class="gtt-btn" aria-haspopup="menu" aria-expanded="false" aria-controls="' + id + '"' +
      ' aria-label="Theme: ' + esc(cur.name) + '. Change the theme" title="Change how this page looks. The data is the same in every theme.">' +
      (opts.label === false ? "" : '<span class="gtt-k">Theme</span>') + '<span class="gtt-n">' + esc(cur.name) + '</span><span class="gtt-c" aria-hidden="true">▾</span></button>';
    var btn = wrap.firstChild;
    var menu = document.createElement("div");
    menu.className = "gtt-menu"; menu.id = id; menu.hidden = true;
    menu.setAttribute("role", "menu"); menu.setAttribute("aria-label", "Theme");
    menu.innerHTML = THEMES.map(function (t) {
      var on = t.id === current;
      return '<button type="button" class="gtt-item" role="menuitemradio" aria-checked="' + on + '" data-theme="' + t.id + '">' +
        '<span class="gtt-tick" aria-hidden="true">' + (on ? "✓" : "") + "</span><b>" + esc(t.name) + "</b><small>" + esc(t.note) + "</small></button>";
    }).join("") + '<div class="gtt-foot">Same live data in every theme. This device remembers the choice.' + (version ? " v" + esc(version) : "") + "</div>";
    document.body.appendChild(menu);
    var m = { btn: btn, menu: menu };
    btn.addEventListener("click", function () { if (openMenu === m) close(false); else open(m); });
    btn.addEventListener("keydown", function (e) { if (e.key === "ArrowDown") { e.preventDefault(); open(m); } });
    menu.addEventListener("click", function (e) {
      var it = e.target.closest ? e.target.closest(".gtt-item") : null;
      if (!it) return;
      var idv = it.getAttribute("data-theme");
      close(true);
      go(idv);
    });
    menu.addEventListener("keydown", function (e) {
      var items = Array.prototype.slice.call(menu.querySelectorAll(".gtt-item")), i = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus(); }
      else if (e.key === "Home") { e.preventDefault(); items[0].focus(); }
      else if (e.key === "End") { e.preventDefault(); items[items.length - 1].focus(); }
      else if (e.key === "Tab") close(false);
    });
    el.appendChild(wrap);
    return wrap;
  }

  window.GTTheme = { THEMES: THEMES, current: current, version: version, copy: copy, copyOf: copyOf, saved: saved, go: go, mount: mount, close: function () { close(false); } };

  var sel = me && me.getAttribute("data-mount");
  if (sel) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { mount(sel); });
    else mount(sel);
  }
})();
