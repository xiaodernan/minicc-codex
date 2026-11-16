import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => console.log("pageerror:", e.message));
await page.addInitScript(() => {
  try { localStorage.clear(); localStorage.setItem("minicc-locale", "en"); } catch {}
});
await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
// try Meta+k
await page.keyboard.press("Meta+k");
await page.waitForTimeout(300);
let visible = await page.locator("#paletteModal.show").count();
console.log("Meta+k -> show count:", visible);
if (!visible) {
  // try clicking... call openCommandPalette via the page hook — but it's not on window; dispatch keyboard
  await page.evaluate(() => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
  });
  await page.waitForTimeout(300);
  visible = await page.locator("#paletteModal.show").count();
  console.log("Document ctrl+k -> show count:", visible);
}
const items = await page.locator(".palette-option").count();
console.log("items rendered:", items);
const texts = await page.locator(".palette-option .palette-label").evaluateAll(els => els.slice(0, 20).map(e => e.textContent));
console.log("labels:", JSON.stringify(texts));
await browser.close();
