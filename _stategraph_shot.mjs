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
  // open command palette
  await page.keyboard.press("Control+k");
  await page.waitForSelector("#paletteInput", { timeout: 5000 });
  await page.fill("#paletteInput", locale === "zh" ? "stategraph" : "stategraph");
  await page.waitForSelector(".palette-item", { timeout: 5000 });
  const items = await page.locator(".palette-item").evaluateAll((els) => els.map((e) => e.innerText));
  console.log(locale, "items:", JSON.stringify(items));
  // click the stategraph entry
  const target = page.locator(".palette-item", { hasText: locale === "zh" ? "StateGraph" : "StateGraph" }).first();
  await target.click();
  await page.waitForSelector(".stategraph-shell", { timeout: 8000 });
  await page.waitForTimeout(600);
  const path = `${dir}/stategraph-${locale}.png`;
  await page.screenshot({ path });
  console.log("saved", path);
  // click a node
  const nodes = await page.locator(".stategraph-node").all();
  console.log(locale, "node count:", nodes.length);
  // switch to 'verify' if exists; else click the third
  const verify = page.locator(".stategraph-node[data-node=\"verify\"]");
  if (await verify.count()) {
    await verify.click();
    await page.waitForTimeout(400);
    const path2 = `${dir}/stategraph-verify-${locale}.png`;
    await page.screenshot({ path: path2 });
    console.log("saved", path2);
  }
  await page.close();
}
await browser.close();
console.log("done", dir);
