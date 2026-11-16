import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const dir = "output/audit-" + Date.now();
mkdirSync(dir, { recursive: true });

const browser = await chromium.launch({ headless: true });
for (const locale of ["en", "zh"]) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("pageerror", (e) => console.log(locale, "pageerror:", e.message));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
  await page.keyboard.press("Meta+k");
  await page.waitForSelector("#paletteModal.show", { timeout: 5000 });
  await page.fill("#paletteInput", locale === "zh" ? "状态图" : "StateGraph");
  await page.waitForSelector(".palette-option", { timeout: 5000 });
  const target = page.locator(".palette-option", { hasText: locale === "zh" ? "打开状态图" : "Open the StateGraph" }).first();
  await target.click();
  await page.waitForSelector(".stategraph-shell", { timeout: 8000 });
  await page.waitForTimeout(600);
  const path1 = `${dir}/stategraph-opening-${locale}.png`;
  await page.screenshot({ path: path1, fullPage: true });
  console.log("saved", path1);
  // Click verify node
  const verify = page.locator(".stategraph-node[data-node=\"verify\"]");
  await verify.click();
  await page.waitForTimeout(300);
  const path2 = `${dir}/stategraph-verify-${locale}.png`;
  await page.screenshot({ path: path2, fullPage: true });
  console.log("saved", path2);
  await page.close();
}
await browser.close();
console.log("done", dir);
