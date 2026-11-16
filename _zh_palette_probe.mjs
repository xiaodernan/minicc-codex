import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => console.log("pageerror:", e.message));
await page.addInitScript(() => {
  try { localStorage.clear(); localStorage.setItem("minicc-locale", "zh"); } catch {}
});
await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
console.log("locale on page:", await page.evaluate(() => localStorage.getItem("minicc-locale")));
await page.keyboard.press("Meta+k");
await page.waitForTimeout(400);
const shown = await page.locator("#paletteModal.show").count();
console.log("show count:", shown);
await page.waitForTimeout(500);
const count = await page.locator(".palette-option").count();
console.log("items:", count);
const texts = await page.locator(".palette-option .palette-label").evaluateAll(els => els.slice(0, 8).map(e => e.textContent));
console.log("first labels:", JSON.stringify(texts));
// try direct fill and see list
await page.fill("#paletteInput", "状态图");
await page.waitForTimeout(300);
const items2 = await page.locator(".palette-option").evaluateAll(els => els.map(e => e.textContent));
console.log("after fill:", JSON.stringify(items2));
await browser.close();
