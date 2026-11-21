// Ground Truth Feed tab check 1.2 (1.3.0, 2026-11-20; 1.1 lets the page's one version reload happen; 1.2 reads row times from
// data-ts and checks the time zone: Eastern by default, the rail's UTC chip, kept over a reload, no row left in the other zone,
// and the order a reader sees, date-only rows included, over an expanded Feed): headless Chromium against a running page.
//   node tools/feed_check.js [base-url] [width ...]
// base-url defaults to http://127.0.0.1:8793/ (tools/live_proxy.py); http://<host>/gt/ checks a deployed site.
// Screenshots go to tools/feed-shots/ (git-ignored: live data). Exit 1 on any failed check or console error.
const { chromium } = require(process.env.PLAYWRIGHT || "playwright");
const fs = require("fs"), path = require("path");
const args = process.argv.slice(2);
const BASE = (args.find((a) => /^https?:/.test(a)) || "http://127.0.0.1:8793/").replace(/\/?$/, "/");
const widths = args.filter((a) => /^\d+$/.test(a)).map(Number);
const OUT = path.join(__dirname, "feed-shots"); fs.mkdirSync(OUT, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  let failed = false;
  for (const w of widths.length ? widths : [1440, 390]) {
    const phone = w < 800;
    const ctx = await browser.newContext({ viewport: { width: w, height: phone ? 844 : 1000 }, deviceScaleFactor: phone ? 2 : 1, colorScheme: "dark" });
    // Against tools/live_proxy.py the server's version can differ from the page's, and the page then reloads itself
    // exactly once (its own sessionStorage guard); the wait below rides through that reload.
    const page = await ctx.newPage();
    const errs = [];
    page.on("pageerror", (e) => errs.push(e.message.slice(0, 200)));
    page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 200)); });
    const waitReady = async () => {
      let ok = false;
      for (let i = 0; i < 90 && !ok; i++) {
        await page.waitForTimeout(500);
        ok = await page.evaluate(() => !!(window.GTX && GTX.S.events && GTX.S.feeds.wire && GTX.S.alerts && document.querySelectorAll("#feed > li").length > 50)).catch(() => false);
      }
      await page.waitForTimeout(1500);
      return ok;
    };
    await page.goto(BASE, { waitUntil: "domcontentloaded" });
    const ready = await waitReady();
    const read = () => page.evaluate(() => {
      const rows = [...document.querySelectorAll("#feed > li")].filter((l) => !l.classList.contains("more"));
      const by = {};
      rows.forEach((l) => { const k = l.dataset.id ? "map pin" : (l.querySelector(".badge.src") || {}).textContent || "?"; by[k] = (by[k] || 0) + 1; });
      return { count: document.getElementById("feedcount").textContent, rows: rows.length, by,
        chips: [...document.querySelectorAll("#feedsrc [data-fg]")].map((b) => b.dataset.fg + (b.classList.contains("off") ? ":off" : "") + " " + b.querySelector(".muted").textContent),
        more: !!document.getElementById("feedmore"),
        newest: rows.slice(0, 5).map((l) => ((l.querySelector(".t") || {}).textContent || "").slice(0, 80) + " | " + ((l.querySelector(".badge.src") || {}).textContent || "pin") + " | " + ((l.querySelector(".time") || {}).textContent || "")),
      };
    });
    const r0 = await read();
    // sorted newest first: every row's time (data-ts, ms) must not increase down the list
    const order = await page.evaluate(() => {
      const t = [...document.querySelectorAll("#feed > li .time[data-ts]")].map((e) => Number(e.dataset.ts));
      let bad = 0; for (let i = 1; i < t.length; i++) if (t[i] > t[i - 1] + 60000) bad++;
      return { bad, future: t.filter((x) => x > Date.now() + 10 * 60000).length, n: t.length };
    });
    // hide Wire, then show it again; a stream row's title links out; Show more grows the list
    const wireBefore = r0.by.Wire || 0;
    await page.click('#feedsrc [data-fg="wire"]').catch(() => {});
    await page.waitForTimeout(300);
    const r1 = await read();
    await page.click('#feedsrc [data-fg="wire"]').catch(() => {});
    await page.waitForTimeout(300);
    const link = await page.evaluate(() => { const a = document.querySelector("#feed li.sx .t a"); return a ? { target: a.target, rel: a.rel, http: /^https?:/.test(a.href) } : null; });
    const rowsBefore = (await read()).rows;
    if (await page.$("#feedmore")) { await page.click("#feedmore"); await page.waitForTimeout(400); }
    const rowsAfter = (await read()).rows;
    // theatre filter: Ukraine - Russia narrows both the pins and the other sources
    const top = () => page.evaluate(() => { const c = document.getElementById("feedsrc"); if (c) c.scrollIntoView({ block: "start" }); });
    await page.evaluate(() => { const b = [...document.querySelectorAll("#theatres [data-th]")].find((x) => /Ukraine/.test(x.textContent)); if (b) b.click(); });
    await page.waitForTimeout(700);
    const th = await read();
    await top(); await page.mouse.move(0, 0);
    await page.screenshot({ path: path.join(OUT, `feed-${w}-ukraine.png`) });
    await page.evaluate(() => { const b = [...document.querySelectorAll("#theatres [data-th]")].find((x) => /Global/.test(x.textContent)); if (b) b.click(); });
    await page.waitForTimeout(500);
    await top();
    await page.screenshot({ path: path.join(OUT, `feed-${w}.png`) });
    // 1.3.0: Eastern by default; the rail's UTC chip switches every time on the page, the choice survives a reload,
    // and the Eastern chip switches back. (The chips are clicked in the page: on phones the rail is behind the menu.)
    const zoneRead = () => page.evaluate(() => ({ zone: GTX.zone(), clock: (document.getElementById("clockz") || {}).textContent || "",
      row: ((document.querySelector("#feed > li .time[data-ts]:not([data-day])") || {}).textContent || "").trim(),
      pressed: (document.querySelector('#tzchips [aria-pressed="true"]') || {}).dataset?.tz || "",
      // rows whose details line (time, place, spans such as TFR "from ... to ...") still shows the other zone
      other: [...document.querySelectorAll("#feed > li .m")].filter((m) => (GTX.zone() === "utc" ? /\d{1,2}:\d\d [AP]M/ : /\b\d\d:\d\dZ\b/).test(m.textContent)).length }));
    const z0 = await zoneRead();
    await page.evaluate(() => document.querySelector('#tzchips [data-tz="utc"]').click());
    await page.waitForTimeout(600);
    const z1 = await zoneRead();
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitReady();
    const z2 = await zoneRead();
    await page.evaluate(() => document.querySelector('#tzchips [data-tz="et"]').click());
    await page.waitForTimeout(600);
    const z3 = await zoneRead();
    // the order a reader sees: expand the Feed (date-only rows appear further down), then every visible date and time must
    // not increase down the list; a date-only row ("11/20") counts as the start of its day
    for (let i = 0; i < 8 && await page.$("#feedmore"); i++) { await page.click("#feedmore").catch(() => {}); await page.waitForTimeout(300); }
    const seen = await page.evaluate(() => {
      const cm = new Date().getUTCMonth() + 1;
      const key = (s) => { const m = s.match(/^(\d{2})\/(\d{2})(?: (\d{1,2}):(\d{2})(?: ([AP]M)|Z))?$/); if (!m) return null;
        let mo = +m[1]; if (mo > cm + 1) mo -= 12;
        let h = m[3] ? +m[3] : 0; if (m[5]) h = (h % 12) + (m[5] === "PM" ? 12 : 0);
        return ((mo * 31 + +m[2]) * 24 + h) * 60 + (m[4] ? +m[4] : 0); };
      const rows = [...document.querySelectorAll("#feed > li .time")].map((e) => e.textContent.trim()), k = rows.map(key);
      const bad = []; for (let i = 1; i < k.length; i++) if (k[i] != null && k[i - 1] != null && k[i] > k[i - 1]) bad.push(rows[i - 1] + " > " + rows[i]);
      return { n: rows.length, days: document.querySelectorAll("#feed > li .time[data-day]").length, unparsed: k.filter((x) => x == null).length, bad: bad.slice(0, 3), nbad: bad.length };
    });
    const zoneOk = z0.other === 0 && z1.other === 0 && z3.other === 0 && z0.zone === "et" && z0.pressed === "et" && /^E[SD]T · \d\d:\d\dZ$/.test(z0.clock) && /\d{1,2}:\d\d [AP]M$/.test(z0.row)
      && z1.zone === "utc" && z1.pressed === "utc" && /^UTC · \d{1,2}:\d\d [AP]M E[SD]T$/.test(z1.clock) && /\d\d:\d\dZ$/.test(z1.row)
      && z2.zone === "utc" && /\d\d:\d\dZ$/.test(z2.row) && z3.zone === "et" && /[AP]M$/.test(z3.row);
    if (phone) { await page.click("#btnRail").catch(() => {}); await page.waitForTimeout(500); await page.screenshot({ path: path.join(OUT, `feed-${w}-rail.png`) }); }
    else await page.screenshot({ path: path.join(OUT, `feed-${w}-top.png`), clip: { x: 0, y: 0, width: w, height: 260 } });
    const n = (s) => Number((s.match(/^([\d,]+) items/) || [0, "0"])[1].replace(/,/g, ""));
    const narrowed = n(th.count) > 0 && n(th.count) < n(r0.count);
    const checks = {
      ready, sorted: order.bad === 0, noFuture: order.future === 0, sources: r0.chips.length >= 8,
      wireHides: wireBefore > 0 ? !(r1.by.Wire) : true, link: !!(link && link.target === "_blank" && /noopener/.test(link.rel) && link.http),
      showMore: r0.more ? rowsAfter > rowsBefore : true, theatre: /Ukraine/.test(th.count) && narrowed, zone: zoneOk, rowsTimed: order.n > 50,
      readerOrder: seen.nbad === 0 && seen.unparsed <= 1 && seen.n > 1000, noErrors: !errs.length,
    };
    const ok = Object.values(checks).every(Boolean);
    failed = failed || !ok;
    console.log(`w=${w}`, ok ? "PASS" : "FAIL", JSON.stringify(checks));
    console.log("  global:", r0.count, "| rows", r0.rows, "| by", JSON.stringify(r0.by));
    console.log("  chips:", r0.chips.join(", "));
    console.log("  newest:", JSON.stringify(r0.newest, null, 0));
    console.log("  ukraine:", th.count, "| by", JSON.stringify(th.by), "| order", JSON.stringify(order), "| errors", errs.slice(0, 3));
    console.log("  zone:", JSON.stringify([z0, z1, z2, z3].map((z) => [z.zone, z.pressed, z.clock, z.row, z.other])));
    console.log("  reader order:", JSON.stringify(seen));
    await ctx.close();
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error("FAIL", e.message); process.exit(1); });
