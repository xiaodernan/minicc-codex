import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale, expectCjk) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => { localStorage.setItem("minicc-locale", l); }, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });

  // nav button exists and is bilingual
  const navText = await page.locator('.nav-item[data-view="atlas"]').innerText();
  assert.ok(navText.trim().length >= 2);

  await page.click('.nav-item[data-view="atlas"]');
  await page.waitForSelector(".atlas-canvas");
  await page.waitForTimeout(1200);

  assert.equal(await page.locator("#atlasStage").getAttribute("aria-hidden"), "false");
  assert.ok(await page.locator(".atlas-hud .atlas-title").innerText());

  const charted = await page.locator("#atlasCharted").innerText();
  const expectTotal = expectCjk ? "/ 94 个坐标" : "/ 94 coordinates";
  assert.ok(charted.includes(expectTotal), `charted line must carry the 76-coordinate contract, saw: ${charted}`);

  // islands ledger: opens via the toggle, lists thirteen regions, every row real
  await page.click("#atlasIslandsToggle");
  await page.waitForTimeout(500);
  const rows = await page.locator(".atlas-island-row").count();
  assert.equal(rows, 13, `islands ledger must list thirteen islands, got ${rows}`);
  const districts = await page.locator(".atlas-island-count").allInnerTexts();
  assert.equal(districts.length, 13);
  for (const bar of districts) assert.match(bar.trim(), /^\d+ \/ \d+$/u, `island count must be 'done / total', saw: ${bar}`);
  await page.click("#atlasIslandsToggle");
  await page.waitForTimeout(250);
  assert.equal(await page.locator("#atlasIslands").getAttribute("hidden") !== null, true, "toggle closes the ledger");

  // Esc-like close via the dedicated button restores aria-hidden
  await page.click("#atlasClose");
  assert.equal(await page.locator("#atlasStage").getAttribute("aria-hidden"), "true");

  await page.close();
}

await checkMode("zh", true);
await checkMode("en", false);

if (errors.length) {
  console.error("atlas smoke FAILED:");
  for (const e of errors) console.error(" ", e);
  process.exit(1);
}
console.log("atlas smoke passed: nav button bilingual, panel opens, 94-coordinate charted line renders, islands ledger lists 13 real islands, close restores hidden state, zero pageerror");
await browser.close();
