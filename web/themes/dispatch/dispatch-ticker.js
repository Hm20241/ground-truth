/* Ground Truth 1.7.2, theme "Dispatch": the "Latest" strip under the masthead, on every page and in the wall view.
   The newest timed entries from the list the page already builds (event pins, plus the news wire and Telegram where
   this copy carries them), newest first. It asks the server for nothing of its own. Date-only pins are left out, as in
   the "Latest" lists. A pin opens on the map; a wire or Telegram entry opens its source in a new tab.
   It holds while the pointer or keyboard focus is on it, has a pause button (remembered in this browser), and with
   reduced motion it does not move: it is a strip to scroll or swipe. Behaviour follows the Classic theme's ticker
   (web/app.js); the look is this theme's own. */
(() => {
  "use strict";
  const G = window.GT2, { S, $, esc } = G;
  const view = $("tickview"), track = $("ticktrack"), btn = $("tickpause");
  if (!view || !track) return;
  const REDUCED = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const MAX = 30, PX = 46;   // items shown, and the speed in px a second at desk size
  const SRC = { pin: "Event map", wire: "News wire", telegram: "Telegram" };
  const tk = { key: "", x: 0, w: 0, last: 0, hold: 0, paused: G.store.get("tickpaused") === "1" };
  const onWall = () => document.body.dataset.view === "wall";
  if (REDUCED) view.classList.add("still");

  function item(e, copy) {
    const [cname, family] = G.cat(e.cat), tag = e.cat && e.cat !== "other" ? cname : SRC[e.src] || "";
    const text = e.title.length > 120 ? e.title.slice(0, 110).replace(/\s+\S*$/, "") + "…" : e.title;
    const inner = `<span class="tick-ago" data-ts="${e.ts}">${esc(G.ago(e.ts))}</span><span class="tick-tag"><i class="dot f-${family}" aria-hidden="true"></i>${esc(tag)}</span><span class="tick-t">${esc(text)}</span>`;
    const ti = copy ? ' tabindex="-1"' : "";
    if (e.src === "pin" && e.ll) return `<button type="button" class="tick-i" data-show="${esc(e.pid)}" title="Show on the map"${ti}>${inner}</button>`;
    if (e.url) return `<a class="tick-i" href="${esc(e.url)}" target="_blank" rel="noopener noreferrer" title="Open the source in a new tab"${ti}>${inner}</a>`;
    return `<span class="tick-i">${inner}</span>`;
  }
  function build() {
    const list = S.entries.filter((e) => !e.day).slice(0, MAX);
    const key = list.map((e) => e.id + "@" + e.ts).join(",") || (S.loadedAt ? "none" : "loading");
    if (key === tk.key) return;   // nothing new: the strip keeps moving where it was
    tk.key = key;
    if (!list.length) {
      track.innerHTML = `<span class="tick-empty">${S.loadedAt ? "No timed entries right now." : "Loading"}</span>`;
      tk.w = 0; tk.x = 0; track.style.transform = ""; return;
    }
    // two copies make the loop seamless; the second is hidden from screen readers and from the tab order
    const run = (copy) => `<div class="tick-run"${copy ? ' aria-hidden="true"' : ""}>${list.map((e) => item(e, copy)).join("")}</div>`;
    track.innerHTML = run(false) + (REDUCED ? "" : run(true));
    measure();
  }
  function measure() {
    track.style.setProperty("--tick-vw", view.clientWidth + "px");   // a short list still fills the strip, so the loop has no gap
    const first = track.firstElementChild;
    tk.w = first && first.classList.contains("tick-run") ? first.offsetWidth : 0;
    paint();
  }
  // the offset always stays in (-w, 0]
  function paint() { if (!tk.w || REDUCED) return; tk.x = -(((-tk.x % tk.w) + tk.w) % tk.w); track.style.transform = `translate3d(${tk.x.toFixed(1)}px,0,0)`; }
  function frame(t) {
    const dt = tk.last ? Math.min(0.1, (t - tk.last) / 1000) : 0; tk.last = t;
    // the wall view has no controls: it always runs, at a speed that suits its larger type
    if (tk.w && !tk.hold && (onWall() || !tk.paused)) { tk.x -= PX * (onWall() ? Math.max(1, window.innerWidth / 1200) : 1) * dt; paint(); }
    requestAnimationFrame(frame);
  }
  function ctl() {
    if (!btn) return;
    btn.hidden = REDUCED;   // nothing moves, so there is nothing to pause
    btn.textContent = tk.paused ? "Play" : "Pause";
    btn.setAttribute("aria-pressed", String(tk.paused));
    btn.setAttribute("aria-label", tk.paused ? "Play the Latest strip" : "Pause the Latest strip");
  }
  function agoTick() { const txt = (el) => { el.textContent = G.ago(+el.dataset.ts); }; track.querySelectorAll(".tick-ago").forEach(txt); }

  const hold = (on) => { tk.hold = Math.max(0, tk.hold + (on ? 1 : -1)); };
  view.addEventListener("mouseenter", () => hold(true));
  view.addEventListener("mouseleave", () => hold(false));
  view.addEventListener("focusin", (e) => {
    hold(true);
    // bring an item reached by keyboard into the strip
    const it = e.target.closest ? e.target.closest(".tick-i") : null;
    view.scrollTop = 0;
    if (!it || REDUCED || !tk.w) return;
    view.scrollLeft = 0;
    const a = it.getBoundingClientRect(), b = view.getBoundingClientRect();
    if (a.left < b.left || a.right > b.right) { tk.x -= a.left - b.left - 12; paint(); }
  });
  view.addEventListener("focusout", () => hold(false));
  // touch: a finger on the strip holds it, and it moves on a little after the finger lifts
  view.addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse") { hold(true); setTimeout(() => hold(false), 2500); } });
  if (btn) btn.addEventListener("click", () => { tk.paused = !tk.paused; G.store.set("tickpaused", tk.paused ? "1" : "0"); ctl(); });

  G.on("data", build);
  G.on("route", () => requestAnimationFrame(measure));   // the wall view sets its own type size
  if (window.ResizeObserver) new ResizeObserver(measure).observe(view);
  setInterval(agoTick, 20000);
  ctl(); build();
  if (!REDUCED) requestAnimationFrame(frame);
})();
