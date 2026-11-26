/* "Watch Floor" theme: the shell. Top bar (with the version, feed light and theme button), headline strip, the three
   board panels, the news ticker, the log, systems, the side drawer, the phone's bottom bar and the wall tour. */
(() => {
  "use strict";
  const WF = window.WF, { $, esc, nf, D, S } = WF, B = WF.BOARDS;
  // Wall view starts only from the address (?wall, or ?wall=30 for 30 seconds a stop) or the Wall view button, never
  // from the screen's size. ?wall=1 means "on" (the other themes write it that way) and keeps the usual 20 seconds.
  const WALL_N = +new URLSearchParams(location.search).get("wall") || 0;
  const TOUR_S = WALL_N > 1 ? Math.max(8, WALL_N) : 20;
  const narrow = () => window.innerWidth <= 1100;

  // put html into an element only when it changed, and keep keyboard focus on the same control
  const last = new WeakMap();
  function put(el, html) {
    if (last.get(el) === html) return;
    const act = document.activeElement, key = act && el.contains(act) ? act.getAttribute("data-k") : null;
    el.innerHTML = html; last.set(el, html);
    if (key) { const again = el.querySelector(`[data-k="${CSS.escape(key)}"]`); if (again) again.focus({ preventScroll: true }); }
  }

  // ---------- top bar ----------
  function renderTop() {
    put($("boards"), Object.entries(B).map(([k, b]) => `<button type="button" data-board="${k}" data-k="bd-${k}" aria-current="${S.board === k}">${esc(b.name)}</button>`).join(""));
    $("boardPickName").textContent = B[S.board].name;
    const feeds = Object.values((D.status || {}).feeds || {}), bad = feeds.filter((f) => !f.ok).length, stale = feeds.filter((f) => f.ok && f.stale).length;
    // the light is drawn three times: a button in the desk top bar, a plain line in the phone's top bar and in its Systems pane
    // 1.7.3: when the newest status request failed, the light goes amber and says since when; before, the last good
    // count ("41 of 42 feeds fresh") stayed up for as long as the server did not answer
    const lost = feeds.length && WF.ERR.status, seen = WF.ms((D.status || {}).now);
    const lcls = "dot ldot " + (!feeds.length ? "" : lost ? "amber" : bad ? "red" : stale ? "amber" : "green");
    const ltxt = !feeds.length ? (WF.ERR.status ? "Feed status not loaded" : "Checking feeds") : lost ? "No feed status since " + (Number.isFinite(seen) ? WF.fmtT(seen) : "the last check")
      : `${feeds.length - bad - stale} of ${feeds.length} feeds fresh`;
    document.querySelectorAll(".ldot").forEach((e) => { if (e.className !== lcls) e.className = lcls; });
    document.querySelectorAll(".ltxt").forEach((e) => { if (e.textContent !== ltxt) e.textContent = ltxt; });
    $("wallBtn").setAttribute("aria-pressed", String(S.wall));
  }
  function tick() { $("clockT").textContent = WF.fmtT(Date.now(), true); $("clockZ").textContent = WF.zoneAbbr(); }

  // ---------- headline strip: the analyst picture and the figures that answer "how busy is it" ----------
  function renderStrip() {
    const a = D.analysis, su = D.summary || {}, t = a ? a.overall_tension : null, st = WF.levelSt(t);
    const tr = a ? String(a.trend || "") : "", arrow = tr === "rising" ? " ▲" : /eas|fall/.test(tr) ? " ▼" : "";
    const tens = `<div class="tens" title="The analyst's reading of overall tension, 0 to 10">${a ? `<div class="big">${esc(t)}<small>/10</small></div><div class="lab">Tension</div><div class="trend">${esc(tr || "–")}${arrow} · ${esc(WF.levelWord(t))}</div>
      <div class="segs" aria-hidden="true">${Array.from({ length: 10 }, (_, i) => `<i class="${i < t ? "on " + st : ""}"></i>`).join("")}</div>` : `<div class="big dim">–</div><div class="lab">Tension</div><div class="trend">${WF.ERR.analysis ? "not loaded" : "loading"}</div>`}</div>`;
    const gen = a ? WF.ms(a.generated_at) : NaN;
    const pic = `<div class="pic">${a ? `<div class="kick"><b>Analyst picture</b><span>written ${esc(WF.ago(gen))} · confidence ${esc(a.confidence || "–")}</span></div>
      <h1>${esc(WF.zText(a.headline, WF.ms(a.generated_at)))}</h1><p>${esc(WF.zText(a.bluf, WF.ms(a.generated_at)))}</p><button type="button" class="linkbtn picmore" data-act="picture" data-k="pic">Full picture and what changed</button>` : `<div class="kick"><b>Analyst picture</b></div><p>${WF.ERR.analysis ? "Could not load the analyst picture (" + esc(WF.ERR.analysis) + ")." : "Loading…"}</p>`}</div>`;
    const newN = WF.lastSeen ? WF.logAll().filter((i) => i.t > WF.lastSeen).length : null;
    const fig = (b, s) => `<div class="fig"><b>${b}</b><span>${s}</span></div>`;
    // pin figures: counted from the merged pins once they are here (the same pins as the map, the log and the
    // Theatres panel); until then the server's own summary of the source map
    const ps = WF.pinStats(), n24 = ps ? ps.n24 : su.events_24h, n6 = ps ? ps.n6 : su.events_6h;
    const newest = ps ? (ps.newest ? Math.min(ps.newest, Date.now()) : null) : su.newest_event_age_min == null ? null : Date.now() - su.newest_event_age_min * 60000;
    const figs = `<div class="figs">${fig(nf(n24), "pins in 24 h")}${fig(nf(n6), "pins in 6 h")}${fig(newest == null ? "–" : esc(WF.agoShort(newest)), "since the newest pin")}${
      newN == null ? "" : fig(nf(newN), "new since you last looked")}</div>`;
    put($("strip"), tens + pic + figs);
  }

  // ---------- the three board panels ----------
  function renderPanels() {
    const [a, b, c] = B[S.board].panels.map((f) => { try { return f(); } catch (e) { console.error("panel", e); return { title: "Panel", right: "", html: `<p class="note">This panel could not be drawn.</p>` }; } });
    [["pA", a], ["pB", b], ["pC", c]].forEach(([id, p]) => { $(id + "h").textContent = p.title; put($(id + "r"), p.right || ""); put($(id + "b"), p.html); });
  }

  // ---------- map panel head ----------
  function renderMapHead() {
    put($("views"), Object.entries(WF.VIEWS).map(([k, v]) => `<button type="button" data-view="${k}" data-k="vw-${k}" aria-pressed="${S.view === k}">${esc(v.name)}</button>`).join(""));
    put($("mapFocus"), S.theatre === "global" ? "" : `<button type="button" class="chip tag" data-th="global" data-k="mf-clear" title="Back to all theatres">${esc(WF.tname(S.theatre))} ✕</button>`);
    // 1.7.1: a layer whose feed this copy does not carry is named in the key, so an empty map is not read as "nothing there"
    const lost = (WF.VIEWS[S.view].feeds || []).filter(([f]) => WF.absent(f)).map(([, n]) => n);
    put($("legend"), WF.VIEWS[S.view].legend + (lost.length ? `<span class="miss">Not on this copy: ${esc(lost.join(", "))}.</span>` : ""));
  }

  // ---------- the log ----------
  let LOG = [], LOGMAP = new Map();
  WF.logAll = () => B.conflict.log();
  function renderLog() {
    const all = B[S.board].log().filter((i) => S.theatre === "global" || i.theatre === S.theatre);
    const kinds = Object.keys(WF.KIND_NAME).filter((k) => all.some((i) => i.kind === k));
    if (S.src !== "all" && !kinds.includes(S.src)) S.src = "all";
    LOG = all.filter((i) => S.src === "all" || i.kind === S.src).sort((x, y) => y.t - x.t);
    LOGMAP = new Map(LOG.map((i) => [i.id, i]));
    const chips = [["all", "All"], ...kinds.map((k) => [k, WF.KIND_NAME[k]])];
    const lostSrc = (B[S.board].kinds || []).filter((k) => WF.KIND_FEED[k] && WF.absent(WF.KIND_FEED[k])).map((k) => WF.KIND_NAME[k]);
    put($("logbar"), (kinds.length > 1 ? chips.map(([k, n]) => `<button type="button" class="chip" data-src="${k}" data-k="src-${k}" aria-pressed="${S.src === k}">${esc(n)}</button>`).join("") : "") +
      (S.theatre === "global" ? "" : `<button type="button" class="chip tag" data-th="global" data-k="th-clear" title="Show all theatres">${esc(WF.tname(S.theatre))} ✕</button>`) +
      // 1.7.1: a source this copy does not carry has no chip (it has no entries); one line names what is missing
      (lostSrc.length ? `<span class="miss">Not on this copy: ${esc(lostSrc.join(", "))}.</span>` : ""));
    $("logbar").hidden = !$("logbar").innerHTML;
    $("logCount").textContent = LOG.length ? `${nf(LOG.length)} entries` : "";
    const waiting = !LOG.length && (WF.LOADING.size || WF.held() || !D.events);
    if (!LOG.length) { put($("log"), `<li class="note">${waiting ? "Loading…" : "Nothing in this log" + (S.theatre === "global" ? "." : " for this theatre.")}<br>This board's log holds ${esc(B[S.board].what)}.</li>`); return; }
    const rows = [], shown = LOG.slice(0, S.wall ? 14 : S.shown), newN = WF.lastSeen ? LOG.filter((i) => i.t > WF.lastSeen).length : 0;
    let day = "", lined = !newN;
    if (newN) rows.push(`<li class="newline">${nf(newN)} new since you last looked (${esc(WF.fmtDay(WF.lastSeen))}, ${esc(WF.fmtT(WF.lastSeen))})</li>`);
    shown.forEach((i) => {
      if (!lined && i.t <= WF.lastSeen) { lined = true; rows.push(`<li class="day">Seen before</li>`); day = ""; }
      const dk = WF.dayKey(i.t);
      if (dk !== day) { day = dk; rows.push(`<li class="day">${esc(WF.fmtDay(i.t))}</li>`); }
      const u = WF.url(i.url), sv = ["", "Elevated", "Active"][i.sev];
      rows.push(`<li class="le s${i.sev}"><span class="bar" title="${sv || "Routine"}"></span><time title="${esc(i.tip || WF.when(i.t))}">${i.noTime ? "no time" : esc(WF.fmtT(i.t))}</time>
        <div class="tx">${u ? `<a href="${esc(u)}" target="_blank" rel="noopener" data-k="l-${esc(i.id)}">${esc(i.title)}</a>` : `<b>${esc(i.title)}</b>`}
          <span class="meta">${i.tag && i.tag !== "Other" ? `<span class="sv">${esc(i.tag)}</span> · ` : ""}${esc(i.src || "")}${i.theatre && S.theatre === "global" && WF.tname(i.theatre) ? " · " + esc(WF.tname(i.theatre)) : ""}</span>${i.sum ? `<span class="sum">${esc(i.sum)}</span>` : ""}</div>
        ${i.ll ? `<button type="button" class="ibtn go" data-go="${esc(i.id)}" data-k="g-${esc(i.id)}" title="Show on the map">◎<span class="sr">Show on the map</span></button>` : "<span></span>"}</li>`);
    });
    if (LOG.length > shown.length) rows.push(`<li><button type="button" class="more" data-act="more" data-k="more">Show ${nf(Math.min(120, LOG.length - shown.length))} more</button></li>`);
    put($("log"), rows.join(""));
  }

  // ---------- news ticker (1.7.2) ----------
  // The newest timed entries of the Conflict log (map pins, plus news wire and Telegram where this copy carries them),
  // newest first, on every board. Day-only pins are left out: they have no clock time. An entry with a place flies the
  // map to it and opens its popup; one without opens its source. The crawl is driven by a frame clock, not a CSS
  // animation, so new data swaps the entries in place and the crawl carries on from the entry it was showing.
  // It stops under the pointer, on keyboard focus and when paused (remembered in this browser). With reduced motion,
  // or when the entries do not fill the band, it does not move and is a strip to scroll or swipe.
  const TK_N = 30, TK_KEY = "gt-floor-ticker-paused";
  const RM = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  const tk = { x: 0, w: 0, at: 0, hover: false, focus: false, map: new Map(), user: (() => { try { return localStorage.getItem(TK_KEY) === "1"; } catch (e) { return false; } })() };
  const tkItem = (i, copy) => { const u = WF.url(i.url), tag = i.tag && i.tag !== "Other" ? i.tag : WF.KIND_NAME[i.kind] || "", key = copy ? ' tabindex="-1"' : ` data-k="tk-${esc(i.id)}"`;
    const body = `<i class="tk-bar" aria-hidden="true"></i><time title="${esc(WF.when(i.t))}">${esc(WF.agoShort(i.t))}</time>${tag ? `<span class="tk-g">${esc(tag)}</span>` : ""}<span class="tk-t">${esc(i.title)}</span>`;
    return i.ll || !u ? `<button type="button" class="tk-i s${i.sev}" data-tk="${esc(i.id)}"${key}${i.ll ? ' title="Show on the map"' : ""}>${body}</button>`
      : `<a class="tk-i s${i.sev}" href="${esc(u)}" target="_blank" rel="noopener"${key}>${body}</a>`; };
  function tkMeasure() {
    const el = $("ticker"), a = $("tkA"), view = $("tkView");
    el.classList.remove("still"); tk.w = a.offsetWidth;
    const still = RM.matches || !tk.map.size || tk.w <= view.clientWidth;
    el.classList.toggle("still", still);
    if (still) { tk.x = 0; $("tkTrack").style.transform = ""; } else { view.scrollLeft = 0; tk.x %= tk.w; $("tkTrack").style.transform = `translate3d(${-tk.x}px,0,0)`; }
    tk.speed = 3.4 * parseFloat(getComputedStyle(document.documentElement).fontSize);  // 3.4 rem a second: scales with the wall view's type
  }
  function renderTicker() {
    const a = $("tkA"), b = $("tkB");
    const items = D.events ? WF.logAll().filter((i) => !i.noTime && Number.isFinite(i.t) && i.title).sort((x, y) => y.t - x.t).slice(0, TK_N) : [];
    tk.map = new Map(items.map((i) => [i.id, i]));
    if (!items.length) { put(a, `<span class="tk-none">${D.events ? "No timed entries right now." : WF.ERR.events ? "The log could not be loaded." : "Loading…"}</span>`); put(b, ""); tkMeasure(); return; }
    // the entry now at the left edge, so the crawl carries on from it after the swap
    let hold = null;
    if (tk.w) for (const e of a.children) if (e.offsetLeft + e.offsetWidth > tk.x) { hold = [e.getAttribute("data-k"), tk.x - e.offsetLeft]; break; }
    put(a, items.map((i) => tkItem(i, false)).join("")); put(b, items.map((i) => tkItem(i, true)).join(""));
    const again = hold && hold[0] ? a.querySelector(`[data-k="${CSS.escape(hold[0])}"]`) : null;
    if (again) tk.x = again.offsetLeft + hold[1];
    tkMeasure();
  }
  function tkFrame(now) {
    const dt = Math.min(100, now - (tk.at || now)); tk.at = now;
    if (tk.w > 0 && !$("ticker").classList.contains("still") && !((tk.user && !S.wall) || tk.hover || tk.focus)) {
      tk.x = (tk.x + (tk.speed * dt) / 1000) % tk.w; $("tkTrack").style.transform = `translate3d(${-tk.x}px,0,0)`; }
    requestAnimationFrame(tkFrame);
  }
  const tkPauseLabel = () => { const b = $("tkPause"); b.setAttribute("aria-pressed", String(tk.user)); b.textContent = tk.user ? "Play" : "Pause"; };
  function tickerBoot() {
    const view = $("tkView");
    $("tkPause").addEventListener("click", () => { tk.user = !tk.user; try { localStorage.setItem(TK_KEY, tk.user ? "1" : "0"); } catch (e) { /* private window */ } tkPauseLabel(); });
    view.addEventListener("mouseenter", () => { tk.hover = true; }); view.addEventListener("mouseleave", () => { tk.hover = false; });
    view.addEventListener("focusin", (e) => { tk.focus = true; if ($("ticker").classList.contains("still")) return;
      view.scrollLeft = 0;  // the browser scrolls a focused entry into view by itself; the crawl does that instead
      const t = e.target.closest(".tk-i"); if (t && $("tkA").contains(t) && (t.offsetLeft < tk.x || t.offsetLeft + t.offsetWidth > tk.x + view.clientWidth)) { tk.x = Math.max(0, t.offsetLeft - 24); $("tkTrack").style.transform = `translate3d(${-tk.x}px,0,0)`; } });
    view.addEventListener("focusout", () => { tk.focus = false; });
    view.addEventListener("click", (e) => { const t = e.target.closest("[data-tk]"), i = t && tk.map.get(t.getAttribute("data-tk")); if (i && i.ll) { toMap(); WF.focus(i.ll, i.h); } });
    if (RM.addEventListener) RM.addEventListener("change", tkMeasure);
    if (window.ResizeObserver) { const ro = new ResizeObserver(tkMeasure); ro.observe(view); ro.observe($("tkA")); } else window.addEventListener("resize", tkMeasure);
    tkPauseLabel(); requestAnimationFrame(tkFrame);
  }

  // ---------- systems: which feeds are fresh ----------
  const FEED = { mymaps: "Source map pins", wire: "News wire", telegram: "Telegram channels", official: "Official statements", ukmto: "Incidents at sea (UKMTO)", mil: "Military aircraft", ships: "Ships",
    front: "Front area (DeepState)", outages: "Internet outages", quakes: "Earthquakes", hazards: "Disaster alerts", cyber: "Cyber", advisories: "Travel advisories", firms: "Fires seen from space", gpsjam: "GPS interference",
    tfr: "US flight restrictions", portwatch: "Chokepoint traffic", airalerts: "Air-raid alerts (Ukraine, Russia)", tzeva: "Israel sirens", tzevalive: "Israel sirens, live", embassy: "US embassy alerts", czib: "Airspace warnings",
    cables: "Undersea cables", bgp: "Internet routing", cellular: "Mobile networks", cloud: "Cloud and AI services", websites: "Websites and services", power: "Power grids", gdelt: "News events (GDELT)",
    geoconfirmed: "Geolocated footage", cir: "Verified incidents", kinetic: "Kinetic events", losses: "Reported losses", ntas: "US terror advisories", ofac: "Sanctions", pla: "Taiwan: Chinese military activity",
    radiation: "Radiation monitors", squawk: "Aircraft emergency codes", tsunami: "Tsunami warnings", vessellists: "Sanctioned-ship lists", gfw: "Ship traffic by satellite" };
  const span = (s) => (!Number.isFinite(s) ? "–" : s < 90 ? Math.round(s) + " s" : s < 5400 ? Math.round(s / 60) + " min" : s < 172800 ? Math.round(s / 3600) + " h" : Math.round(s / 86400) + " days");
  const feedRows = () => Object.entries((D.status || {}).feeds || {}).map(([k, f]) => ({ k, name: FEED[k] || k, st: !f.ok ? "red" : f.stale ? "amber" : "green", word: !f.ok ? "Failing" : f.stale ? "Stale" : "Fresh", f }))
    .sort((a, b) => ["red", "amber", "green"].indexOf(a.st) - ["red", "amber", "green"].indexOf(b.st) || a.name.localeCompare(b.name));
  const feedTable = (rows) => `<table class="feeds"><thead><tr><th>Feed</th><th>State</th><th>Last update</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.name)}${r.f.error ? `<small>${esc(String(r.f.error).slice(0, 120))}</small>` : ""}</td>
    <td><span class="st"><i class="dot ${r.st}"></i>${r.word}</span></td><td>${esc(span(r.f.age_s))} ago<small>checked every ${esc(span(r.f.every))}</small></td></tr>`).join("")}</tbody></table>${creditsHtml()}`;
  // Credits for the three other pin sources, worded as the Classic theme words them (web/ext/curated.js). Each shows
  // only when this server carries that feed.
  const CREDITS = [["geoconfirmed", "GeoConfirmed", "Verified pins. Research use; not on the public mirror.", "https://geoconfirmed.org"],
    ["cir", "CIR Eyes on Russia", "Verified pins. Research use; not on the public mirror.", "https://eyesonrussia.org"],
    ["kinetic", "S2 Underground's Iran kinetic events map", "Licensed CC BY-NC-SA 4.0; layout changed.", "https://creativecommons.org/licenses/by-nc-sa/4.0/"]];
  function creditsHtml() {
    const have = CREDITS.filter(([k]) => k in ((D.status || {}).feeds || {}));
    return have.length ? WF.ui.sub("Credits for the other map pins") + have.map(([k, n, s, u]) => WF.ui.row({ tag: "a", attrs: `href="${u}" target="_blank" rel="noopener" data-k="cr-${k}"`, cls: "doc cred", wrap: true, name: esc(n) + " ↗", sub: esc(s), val: "" })).join("") : "";
  }
  function renderSys() {
    const rows = feedRows(), ok = rows.filter((r) => r.st === "green").length, off = rows.filter((r) => r.st !== "green");
    if (!rows.length) { put($("sysB"), `<p class="note">${WF.ERR.status ? "Could not load feed status (" + esc(WF.ERR.status) + ")." : "Loading…"}</p>`); return; }
    put($("sysR"), `<button type="button" class="linkbtn hidephone" data-act="systems" data-k="sysall">All feeds</button>`);
    const seen = WF.ms((D.status || {}).now), lostAt = WF.ERR.status ? (Number.isFinite(seen) ? WF.fmtT(seen) : "the last check") : "";  // 1.7.3: said in Systems too, the one place the wall view shows feed health
    const an = D.analysis ? `Analyst picture written ${esc(WF.ago(WF.ms(D.analysis.generated_at)))}.` : "";
    put($("sysB"), `<div class="sysline"><b>${ok}<small> of ${rows.length}</small></b><div class="txt">${lostAt ? `<strong>No feed status since ${esc(lostAt)}: the server is not answering, so everything here may be old.</strong> ` : ""}${off.length ? `<strong>${off.map((r) => esc(r.name) + " (" + r.word.toLowerCase() + ")").join(", ")}.</strong>` : "<strong>Every feed is fresh.</strong>"} ${an}</div></div>
      <div class="sysdots" aria-hidden="true">${rows.map((r) => `<i class="${r.st}" title="${esc(r.name)}: ${r.word}"></i>`).join("")}</div>
      <div class="sysfull">${feedTable(rows)}<div class="logbar" role="group" aria-label="Times on this page">${zoneChips()}</div></div>`);
  }
  const zoneChips = () => `<button type="button" class="chip" data-zone="et" data-k="z-et" aria-pressed="${WF.zone() === "et"}">Eastern time</button><button type="button" class="chip" data-zone="utc" data-k="z-utc" aria-pressed="${WF.zone() === "utc"}">UTC</button>`;

  // ---------- drawer ----------
  let opener = null;
  function openDrawer(title, html) {
    opener = document.activeElement;
    $("drawerH").textContent = title; $("drawerB").innerHTML = html;
    $("drawer").hidden = false; $("scrim").hidden = false; $("drawerX").focus();
  }
  function closeDrawer() { if ($("drawer").hidden) return; $("drawer").hidden = true; $("scrim").hidden = true; if (opener && document.contains(opener)) opener.focus(); opener = null; }
  function pictureHtml() {
    const a = D.analysis; if (!a) return `<p>The analyst picture is not loaded.</p>`;
    const ref = WF.ms(a.generated_at), z = (x) => esc(WF.zText(x, ref));
    const li = (xs) => `<ul>${(xs || []).map((x) => `<li>${z(x)}</li>`).join("")}</ul>`;
    return `<p class="muted">Written ${esc(WF.when(WF.ms(a.generated_at)))} from ${nf(a.events_considered)} events. Confidence ${esc(a.confidence || "–")}. Where the text gives a UTC time, the Eastern time is beside it.</p>
      <p class="lead"><b>${z(a.headline)}</b></p><p>${z(a.bluf)}</p>
      <h3>What changed since the last picture</h3>${li(a.changes_since_last)}
      <h3>Theatre by theatre</h3>${(a.theatres || []).map((t) => `<div class="row"><span class="lead">${WF.ui.lead.lv(t.status, WF.levelSt(t.status))}</span><span class="nm"><b>${esc(WF.tname(t.theatre) || t.theatre)}</b><span>${esc(WF.levelWord(t.status))}, ${esc(t.trend || "")}</span></span><span class="val"></span></div>
        <p>${z(t.summary)}</p>${li(t.key_developments)}${t.watch ? `<p class="muted"><b>Watch:</b> ${esc(Array.isArray(t.watch) ? t.watch.join("; ") : t.watch)}</p>` : ""}`).join("")}
      <h3>Across theatres</h3>${li(a.cross_theatre)}
      <h3>Indicators</h3><ul>${(a.indicators || []).map((i) => `<li><b>${esc(i.indicator)}</b>: ${esc(i.state)}. ${esc(i.note || "")}</li>`).join("")}</ul>
      <h3>What the picture cannot see</h3>${li(a.gaps)}`;
  }
  const boardPickHtml = () => `<div class="blist">${Object.entries(B).map(([k, b]) => `<button type="button" data-board="${k}" aria-current="${S.board === k}">${esc(b.name)}<small>${esc(b.about)}</small></button>`).join("")}</div>
    <h3>Times on this page</h3><div class="logbar">${zoneChips()}</div>`;

  // ---------- actions ----------
  function setBoard(k) {
    if (!B[k]) return;
    unmountView();
    S.board = k; S.src = "all"; S.shown = 120; S.theatre = "global"; document.body.dataset.board = k;
    if (B[k].host) { document.body.setAttribute("data-viewboard", ""); if (S.pane === "map" || S.pane === "log") setPane("board"); } else document.body.removeAttribute("data-viewboard");
    WF.need(B[k].need); WF.setView(B[k].view); if (B[k].host) mountView(B[k]); render();
    const sc = $("scroller"); if (sc) sc.scrollTop = 0;
  }
  // ---------- private views (1.8.0): a view registered by themes/private.js gets one board of its own ----------
  // Generic: the view brings its own title, one-line description and renderer (view.render.floor(host, ctx), which may
  // return a function that stops its timers). This file knows nothing else about it. On the board the usual strip and
  // three panels give way to one host box; the ticker, top bar and Systems stay.
  let viewStop = null;
  function unmountView() {
    if (viewStop) { try { viewStop(); } catch (e) { console.error("private view", e); } viewStop = null; }
    const h = $("viewHost"); if (h) { h.hidden = true; h.textContent = ""; }
  }
  function mountView(b) {
    const h = $("viewHost"); h.hidden = false; h.textContent = ""; h.setAttribute("aria-label", b.name);
    try { const r = b.pv.render.floor(h, window.GTPrivate.ctx); viewStop = typeof r === "function" ? r : typeof b.pv.cleanup === "function" ? b.pv.cleanup : null; }
    catch (e) { console.error("private view", e); h.innerHTML = '<p class="note">This board could not be drawn.</p>'; }
  }
  { const h = document.createElement("section"); h.id = "viewHost"; h.className = "viewhost"; h.hidden = true; $("scroller").appendChild(h); }
  if (window.GTPrivate) window.GTPrivate.onViews((views) => {
    views.forEach((v) => { if (typeof v.render.floor === "function") B["v-" + v.id] = { name: String(v.title || v.id), about: String(v.about || ""), view: "conflict", need: [], panels: [], log: () => [], kinds: [], what: "", host: true, pv: v }; });
    renderTop();
  });
  function setTheatre(k, fly) { S.theatre = WF.THEATRES[k] ? k : "global"; S.shown = 120; if (fly !== false) WF.flyTheatre(S.theatre); render(); }
  function setPane(p) {
    S.pane = p; document.body.dataset.pane = p;
    document.querySelectorAll("#bbar button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.pane === p)));
    if (p === "map" && WF.map) requestAnimationFrame(() => WF.map.resize());
    const sc = $("scroller"); if (sc) sc.scrollTop = 0;
  }
  function setWide(w) { S.wide = S.wide === w ? "" : w; if (S.wide) document.body.dataset.wide = S.wide; else delete document.body.dataset.wide;
    $("wideMap").setAttribute("aria-pressed", String(S.wide === "map")); $("wideLog").setAttribute("aria-pressed", String(S.wide === "log")); }
  function setWall(on) {
    S.wall = on; document.documentElement.classList.toggle("wall", on);
    if (on && window.GTTheme) GTTheme.close();  // the theme button is hidden in wall view; so is its open menu
    if (on && B[S.board].host) setBoard("conflict");  // the wall tours the map: a private board has none
    if (on) { closeDrawer(); if (S.wide) setWide(S.wide); tourStart(); } else tourStop();
    render(); if (WF.map) setTimeout(() => WF.map.resize(), 50);
  }
  const toMap = () => { if (narrow()) setPane("map"); };
  // 1.7.3: the feeds a map view draws. A view picked with the map's own buttons, on a board that does not need those
  // feeds, used to show an empty map (Sea with no ships, chokepoints or incidents; Air with no aircraft), and nothing
  // refreshed them. WF.load skips a name that is not a data name (the air-raid and embassy alerts ride on "alerts").
  const viewFeeds = (v) => ((WF.VIEWS[v] || {}).feeds || []).map(([f]) => f);
  document.addEventListener("click", (e) => {
    const t = e.target.closest ? e.target.closest("[data-board],[data-th],[data-fr],[data-go],[data-view],[data-src],[data-pane],[data-fly],[data-box],[data-act],[data-zone]") : null;
    if (!t || t === document.body) return;  // the body carries data-board / data-pane for the stylesheet only
    const d = t.dataset;
    if (d.board) { closeDrawer(); setBoard(d.board); }
    else if (d.th) { setTheatre(S.theatre === d.th ? "global" : d.th); }
    else if (d.fr) { const f = (WF.FRONTS || []).find((x) => x.id === d.fr); if (f) { toMap(); WF.fitBox(f.bbox); WF.popup(f.mid, WF.frontPop(f)); } }
    else if (d.go) { const i = LOGMAP.get(d.go); if (i && i.ll) { toMap(); WF.focus(i.ll, i.h); } }
    else if (d.view) { WF.need(viewFeeds(d.view)); WF.setView(d.view); renderMapHead(); }  // 1.7.3: load what the view draws
    else if (d.src) { S.src = d.src; S.shown = 120; renderLog(); }
    else if (d.pane) setPane(d.pane);
    else if (d.fly) { const [lon, lat, z] = d.fly.split(",").map(Number); if (![lon, lat, z].every(Number.isFinite)) return;  // 1.7.3: a row with no position does nothing (it used to throw inside the map)
      toMap(); WF.map.flyTo({ center: [lon, lat], zoom: narrow() ? z - 0.8 : z, duration: 1000 }); }
    else if (d.box) { const b = d.box.split(",").map(Number); toMap(); WF.fitBox([[b[0], b[1]], [b[2], b[3]]]); }
    else if (d.zone) { WF.setZone(d.zone); tick(); render(); if (!$("drawer").hidden && $("drawerH").textContent === "Boards") { $("drawerB").innerHTML = boardPickHtml(); const z = $("drawerB").querySelector(`[data-zone="${WF.zone()}"]`); if (z) z.focus(); } }  // 1.7.3: focus stays in the drawer
    else if (d.act === "more") { S.shown += 120; renderLog(); }
    else if (d.act === "classic") { if (window.GTTheme) GTTheme.go("classic"); }  // "Open Classic" in a placeholder box
    else if (d.act === "picture") openDrawer("Analyst picture", pictureHtml());
    else if (d.act === "systems") openDrawer("Systems: every feed", feedTable(feedRows()));
  });
  $("clock").addEventListener("click", () => { WF.setZone(WF.zone() === "utc" ? "et" : "utc"); tick(); render(); });
  $("sysLight").addEventListener("click", () => openDrawer("Systems: every feed", feedTable(feedRows())));
  $("boardPick").addEventListener("click", () => openDrawer("Boards", boardPickHtml()));
  $("wallBtn").addEventListener("click", () => setWall(!S.wall));
  $("wideMap").addEventListener("click", () => setWide("map"));
  $("wideLog").addEventListener("click", () => setWide("log"));
  $("keyBtn").addEventListener("click", () => { const on = document.body.classList.toggle("keyopen"); $("keyBtn").setAttribute("aria-expanded", String(on)); $("keyBtn").textContent = on ? "Hide the key" : "Map key"; });
  document.querySelector(".skip").addEventListener("click", () => { if (narrow()) setPane("log"); });
  $("drawerX").addEventListener("click", closeDrawer);
  $("scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { if (!$("drawer").hidden) closeDrawer(); else if (S.wall) setWall(false); }
    if (e.key === "Tab" && !$("drawer").hidden) {  // keep Tab inside the open drawer
      const f = $("drawer").querySelectorAll("button, a[href]"); if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });

  // ---------- wall tour: the map visits each busy theatre in turn, nothing to press ----------
  let tourTimer = 0, tourList = [], tourI = -1;
  function tourStep() {
    const ps = WF.pinStats() || { by: {}, n24: null }, by = ps.by;  // the same merged pin counts as the Theatres panel
    tourList = ["global", ...Object.keys(WF.THEATRES).filter((k) => k !== "global" && by[k] > 0).sort((a, b) => by[b] - by[a])];
    tourI = (tourI + 1) % tourList.length;
    const k = tourList[tourI], a = ((D.analysis || {}).theatres || []).find((t) => t.theatre === k);
    setTheatre(k);
    $("tour").hidden = false; $("tourName").textContent = WF.tname(k);
    $("tourSub").textContent = `${nf(k === "global" ? ps.n24 : by[k])} pins in 24 h` + (a ? ` · level ${a.status} of 10, ${a.trend}` : "");
    const bar = $("tourBar"); bar.classList.remove("run"); bar.style.setProperty("--tour", TOUR_S + "s"); void bar.offsetWidth; bar.classList.add("run");
  }
  function tourStart() { tourStop(); tourI = -1; tourStep(); tourTimer = setInterval(tourStep, TOUR_S * 1000); }
  function tourStop() { clearInterval(tourTimer); tourTimer = 0; $("tour").hidden = true; if (S.theatre !== "global") setTheatre("global"); }
  WF.tourTo = (i) => { tourI = i - 1; tourStep(); };  // for the screenshots

  // ---------- render and boot ----------
  function render() { flushMap(); renderTop();
    if (B[S.board].host) { renderSys(); renderTicker(); $("viewHost").dispatchEvent(new CustomEvent("gt-render")); return; }  // the view repaints itself (times, zone switch)
    renderStrip(); renderPanels(); renderMapHead(); renderLog(); renderSys(); renderTicker();
  }
  WF.render = render;
  // 1.7.3: map sources are rebuilt once a frame, just before the page is drawn (every reply already asks for that
  // frame). The four pin replies each rebuilt every pin, popup and front count; replies landing together now share one.
  const dirty = new Set();
  WF.onData = (name) => { dirty.add(name); };
  const flushMap = () => { if (!dirty.size) return; const names = [...dirty]; dirty.clear(); names.forEach((n) => WF.mapData(n)); };
  WF.actions = { setBoard, setTheatre, setPane, setWide, setWall };

  // Version and theme button (themes/switch.js): the version beside the feed light, the button directly under them.
  // Drawn once here, in the top bar and in the phone's Systems pane; both are hidden in wall view (floor.css).
  if (window.GTTheme) {
    document.querySelectorAll(".ver").forEach((e) => { e.textContent = "v" + GTTheme.version; });
    GTTheme.mount($("themeTop"));
    GTTheme.mount($("themeSys"));
  }

  const CORE = ["summary", "status", "analysis", "alerts", "events", "front", "wire", "telegram"];
  document.documentElement.classList.toggle("wall", S.wall);
  WF.initMap();
  WF.onMapReady = () => { if (S.wall) tourStart(); };
  CORE.forEach((n) => WF.load(n));
  tick(); setInterval(tick, 1000);
  tickerBoot();
  render();
  setInterval(() => { [...new Set([...CORE, ...B[S.board].need, ...viewFeeds(S.view)])].forEach((n) => WF.load(n)); }, 120000);
  setInterval(() => { renderStrip(); renderSys(); renderTicker(); }, 30000);
})();
