import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const chapters = ["prologue", "spark", "depth", "sentry", "bloom", "hand", "gate", "mesh", "witness", "craft", "backlog"];
const CHAPTER_MARKERS = {
  prologue: ["序章", "Prologue"],
  spark: ["火种", "The Spark"],
  depth: ["深度", "The Depth"],
  sentry: ["哨兵", "The Sentry"],
  bloom: ["盛放", "The Bloom"],
  hand: ["远行", "The Open Road"],
  gate: ["关卡", "The Gate"],
  mesh: ["星网", "The Mesh"],
  witness: ["证人", "The Witness"],
  craft: ["技艺", "The Craft"],
  backlog: ["未竟", "The Unfinished"],
};
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
    const marker = expectCjk ? CHAPTER_MARKERS[id][0] : CHAPTER_MARKERS[id][1].toLowerCase();
    assert.ok(canvas.toLowerCase().includes(marker), `${locale}/${id}: canvas must render this chapter (looked for ${marker}), first 160 chars: ${canvas.slice(0, 160).replace(/\n/g, " ")}`);
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

console.log("almanac smoke passed: 11 chapters render fully bilingual, chapter switching verified, no mixed-language prose");
process.exit(0);
