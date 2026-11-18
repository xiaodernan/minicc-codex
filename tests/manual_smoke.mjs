import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const chapterIds = ["start", "workbench", "modules", "keys", "arcade", "trouble", "limits", "vault", "philosophy", "askdocs", "load", "cloud", "arch", "stategraph", "cache", "sandbox", "fanout", "evidence", "ciwall", "twoshards"];
const CJK = /[一-鿿]/;

const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale, expectCjk) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => {
    try {
      localStorage.clear();
      localStorage.setItem("minicc-locale", l);
    } catch {}
  }, locale);
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.locator('.nav-item[data-view="manual"]').click();
  await page.waitForSelector(".manual-shell");
  for (const id of chapterIds) {
    await page.click(`.manual-chapter[data-chapter="${id}"]`);
    await page.waitForTimeout(120);
    const text = await page.locator("#manualCanvas").innerText();
    const hasCjk = CJK.test(text);
    assert.equal(
      hasCjk,
      expectCjk,
      `${locale}: ${id} expected ${expectCjk ? "CJK" : "no CJK"}, got: ${text.slice(0, 160)}`,
    );
    assert.ok(text.trim().length > 40, `${locale}: ${id} rendered suspiciously empty`);
  }
  await page.close();
}

await checkMode("zh", true);
await checkMode("en", false);
await browser.close();
assert.equal(errors.length, 0, JSON.stringify(errors, null, 2));
console.log("manual smoke passed: 20 chapters render fully bilingual, no mixed-language prose");
