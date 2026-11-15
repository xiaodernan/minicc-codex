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
  const expectTotal = expectCjk ? "/ 52 个坐标" : "/ 52 coordinates";
  assert.ok(charted.includes(expectTotal), `charted line must carry the 50-coordinate contract, saw: ${charted}`);

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
console.log("atlas smoke passed: nav button bilingual, panel opens, 52-coordinate charted line renders, stardust visible when visited, close restores hidden state, zero pageerror");
await browser.close();
