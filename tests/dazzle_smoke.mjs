// M8-T1066: the "dazzle" — real-user simulation at click-macro speed.
// Three walks per locale (en+zh), zero browser errors tolerated:
//   A) impatient — open the page, don't read a word, leave (sub-second attention)
//   B) lost-user — open every view the sidebar offers, linger briefly, bounce back
//   C) dazzle — 34 randomly selected clicks on live buttons, with Esc to dismiss
//      any overlay that pops up (the user who mashes everything, knows nothing)
// All walks assert console.error === 0 and pageerror === 0.
import { chromium } from "playwright";
import assert from "node:assert/strict";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";

// deterministic seeded PRNG (mulberry32) — same walk every CI, no flake budget
function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

async function newPageWithErrors(browser, locale, viewport = { width: 1400, height: 1100 }) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text().slice(0, 240)}`); });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message.slice(0, 240)}`));
  await page.addInitScript((l) => { localStorage.clear(); localStorage.setItem("minicc-locale", l); }, locale);
  return { page, errors };
}

async function impatientWalk(browser, locale) {
  const { page, errors } = await newPageWithErrors(browser, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1500);                       // user stares past it — no reading
  assert.deepEqual(errors, [], `${locale}: impatient walk emitted browser errors:\n${errors.join("\n")}`);
  await page.close();
  console.log(locale, "impatient walk: clean");
}

async function lostUserWalk(browser, locale) {
  const { page, errors } = await newPageWithErrors(browser, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1500);
  // open every nav destination the sidebar offers; never read anything before closing
  const views = await page.evaluate(() =>
    [...document.querySelectorAll('.nav-item[data-view]')].map((b) => b.dataset.view));
  assert(views.length >= 12, `${locale}: nav rail collapsed — expected at least twelve views, got ${views.length}`);
  for (const view of views) {
    await page.click(`.nav-item[data-view="${view}"]`, { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(500);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(160);
  }
  assert.deepEqual(errors, [], `${locale}: lost-user walk emitted browser errors:\n${errors.join("\n")}`);
  await page.close();
  console.log(locale, "lost-user walk: clean");
}

async function dazzleWalk(browser, locale) {
  const { page, errors } = await newPageWithErrors(browser, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1500);
  const rand = rng(0x1eca5d0ab1e_2026);
  const deadline = Date.now() + 52000;
  const budget = 34;
  let clicked = 0;
  while (Date.now() < deadline && clicked < budget) {
    const count = await page.locator("button:visible:not([aria-disabled='true'])").count();
    if (count === 0) break;
    const idx = Math.floor(rand() * count);
    const el = page.locator("button:visible:not([aria-disabled='true'])").nth(idx);
    try {
      const meta = await el.evaluate((n) => ({ tag: n.tagName, id: n.id || "", text: (n.textContent || "").trim().slice(0, 40) }));
      if (meta.tag === "CANVAS") { clicked++; continue; }
      await el.click({ timeout: 1200, force: true }).catch((e) => { console.log("    (dazzle swallowed stale-node click):", String(e.message).split("\n")[0].slice(0, 80)); });
      // An overlay opened? close it the way a panic user would
      const overlayOpen = await page.locator('[role="dialog"][aria-hidden="false"], .stage-overlay[aria-hidden="false"], .panel-modal.show').count();
      if (overlayOpen) {
        await page.keyboard.press("Escape");
        await page.waitForTimeout(120);
      }
      // side-scroll the main column occasionally — heavy users thrash scroll too
      if (Math.floor(rand() * 5) === 0 && Math.floor(rand() * 2) === 0) {
        await page.evaluate(() => { const c = document.querySelector(".chat-area, .main-column, .chat-scroll"); if (c) c.scrollTo(0, Math.max(0, (Math.random() - 0.3) * 4000)); }).catch(() => {});
      }
      await page.waitForTimeout(220);
    } catch (e) {
      console.log("    (dazzle swallow corrupt-node click):", String(e.message).slice(0, 80));
    }
    clicked++;
  }
  for (let i = 0; i < 5; i++) await page.keyboard.press("Escape");   // polite broom
  assert.deepEqual(errors, [], `${locale}: dazzle walk emitted browser errors:\n${errors.join("\n")}`);
  await page.close();
  console.log(locale, `dazzle walk: clean (${clicked} clicks)`);
}

const browser = await chromium.launch({ headless: true });
for (const locale of ["en", "zh"]) {
  await impatientWalk(browser, locale);
  await lostUserWalk(browser, locale);
  await dazzleWalk(browser, locale);
}
await browser.close();
console.log("dazzle smoke passed: impatient / lost-user / dazzle walks in en+zh — zero browser errors");
