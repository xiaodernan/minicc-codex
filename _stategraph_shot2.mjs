import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const dir = "output/audit-" + Date.now();
mkdirSync(dir, { recursive: true });

const browser = await chromium.launch({ headless: true });
for (const locale of ["zh", "en"]) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("pageerror", (e) => console.log(locale, "pageerror:", e.message));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
  await page.keyboard.press("Control+k");
  await page.waitForSelector("#paletteInput", { timeout: 5000 });
  await page.fill("#paletteInput", locale === "zh" ? "状态图" : "StateGraph");
  await page.waitForSelector(".palette-option", { timeout: 5000 });
  const items = await page.locator(".palette-option").evaluateAll((els) => els.map((e) => e.innerText.split("\n")[0]));
  console.log(locale, "items:", JSON.stringify(items));
  const target = page.locator(".palette-option", { hasText: locale === "zh" ? "打开状态图" : "Open the StateGraph" }).first();
  if ((await target.count()) === 0) {
    console.log(locale, "did not find stategraph option, trying id-based click");
    const opt = page.locator(".palette-option").filter({ hasText: "stategraph" }).first();
    await opt.click();
  } else {
    await target.click();
  }
  await page.waitForSelector(".stategraph-shell", { timeout: 8000 });
  await page.waitForTimeout(500);
  const path = `${dir}/stategraph-${locale}.png`;
  await page.screenshot({ path, fullPage: true });
  console.log("saved", path);
  const nodes = await page.locator(".stategraph-node").all();
  console.log(locale, "nodes on screen:", nodes.length);
  await page.close();
}
await browser.close();
console.log("done", dir);
