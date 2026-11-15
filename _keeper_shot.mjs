import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 }, deviceScaleFactor: 1.25 });
await page.goto("http://127.0.0.1:8765/", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.evaluate(() => { try { localStorage.setItem("minicc-locale", "zh"); } catch {} });
await page.reload({ waitUntil: "networkidle", timeout: 60000 });
await page.waitForTimeout(900);
await page.click('#doctorButton');
await page.waitForTimeout(2200);
const keeper = await page.evaluate(() => ({ box: document.querySelector("#doctorKeeper")?.textContent ?? null, tone: document.querySelector("#doctorKeeperDot")?.getAttribute("data-tone") }));
console.log(JSON.stringify(keeper));
await page.screenshot({ path: "output/doctor_keeper.png" });
await browser.close();
