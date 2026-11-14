import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const chapters = ["prologue", "spark", "depth", "sentry", "bloom", "hand", "gate", "mesh", "witness"];
const CJK = /[\u4e00-\u9fff]/;

const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale, expectCjk) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => localStorage.setItem("minicc-locale", l), locale);
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.locator('.nav-item[data-view="almanac"]').click();
  await page.waitForSelector(".almanac-shell");
  for (const id of chapters) {
    await page.locator(`.almanac-chapter[data-chapter="${id}"]`).click();
    await page.waitForTimeout(150);
    const canvas = await page.locator("#almanacCanvas").innerText();
    const rail = await page.locator(".almanac-rail").innerText();
    const hit = CJK.test(`${canvas}\n${rail}`);
    if (expectCjk) {
      assert.ok(hit, `${id}: zh mode should render Chinese prose`);
    } else {
      assert.ok(!hit, `${id}: en mode rendered CJK, first 140 chars: ${canvas.slice(0, 140).replace(/\n/g, " ")}`);
    }
  }
  await page.close();
}

await checkMode("en", false);
await checkMode("zh", true);
assert.deepEqual(errors, [], `browser page errors: ${errors.join(" | ")}`);

console.log("almanac smoke passed: 9 chapters render fully bilingual, no mixed-language prose");
process.exit(0);
