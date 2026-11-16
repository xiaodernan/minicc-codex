import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.addInitScript(() => {
  try {
    localStorage.clear();
    localStorage.setItem("minicc-locale", "en");
  } catch {}
});
await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
await page.locator('.nav-item[data-view="manual"]').click();
await page.waitForSelector(".manual-shell");
await page.click('.manual-chapter[data-chapter="cache"]');
await page.waitForTimeout(400);
const text = await page.locator("#manualCanvas").innerText();
console.log("=== TEXT (first 1000) ===");
console.log(text.slice(0, 1000));
const cjkLines = text.split("\n").map((l, i) => [i + 1, l]).filter(([i, l]) => /[一-鿿]/.test(l));
console.log("=== CJK LINES ===");
for (const [n, line] of cjkLines) console.log("line", n, ":", line);
console.log("pageerrors:", errors);
await browser.close();
