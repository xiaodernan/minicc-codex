import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const dir = "output/audit-" + Date.now();
mkdirSync(dir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => console.log("pageerror:", e.message));
await page.addInitScript(() => {
  try { localStorage.clear(); localStorage.setItem("minicc-locale", "en"); } catch {}
});
await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
await page.keyboard.press("Meta+k");
await page.waitForSelector("#paletteModal.show", { timeout: 5000 });
await page.fill("#paletteInput", "StateGraph");
await page.waitForSelector(".palette-option", { timeout: 5000 });
await page.locator(".palette-option", { hasText: "Open the StateGraph" }).click();
await page.waitForSelector(".stategraph-shell", { timeout: 8000 });
await page.waitForTimeout(400);
const chipVisible = await page.locator(".tour-offer").count();
console.log("tour-offer chip count while immersive panel is open:", chipVisible);
const path = `${dir}/stategraph-after-hide.png`;
await page.screenshot({ path, fullPage: true });
console.log("saved", path);
await browser.close();
