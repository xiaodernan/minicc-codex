import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale, expectCjk) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => { localStorage.setItem("minicc-locale", l); localStorage.clear(); localStorage.setItem("minicc-locale", l); }, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });

  // nav button exists and is bilingual
  const navText = await page.locator('.nav-item[data-view="admin"]').innerText();
  assert.ok(navText.trim().length >= 1);

  // locked state is shown first (123 shared door)
  await page.click('.nav-item[data-view="admin"]');
  await page.waitForSelector("#adminStage");
  await page.waitForTimeout(400);
  assert.equal(await page.locator("#adminStage").getAttribute("aria-hidden"), "false");
  assert.ok(await page.locator("#adminLocked").isVisible(), "locked state must be default");

  // unlock with 123
  await page.fill("#adminPassword", "123");
  await page.click("#adminUnlockBtn");
  await page.waitForTimeout(1400);

  // unlocked state must be visible
  assert.ok(await page.locator("#adminUnlocked").isVisible(), "unlocked dashboard must render");

  // pick up real numbers from /api/admin/summary — never assert hardcoded counts, only shape
  const totals = await page.evaluate(() => ({
    tasks: document.querySelector("#adminTotalTasks")?.innerText,
    completed: document.querySelector("#adminCompleted")?.innerText,
    interrupted: document.querySelector("#adminInterrupted")?.innerText,
    cacheRate: document.querySelector("#adminCacheRate")?.innerText,
    audit: document.querySelector("#adminAuditLines")?.innerText,
    sessions: document.querySelector("#adminSessions")?.innerText,
    tools: document.querySelectorAll("#adminToolUsage li").length,
    recs: document.querySelectorAll("#adminRecommendations li").length,
    recent: document.querySelectorAll("#adminRecentTasks li").length,
    canvas: document.querySelector("#adminTrendCanvas")?.width ?? 0,
  }));
  assert.ok(Number(totals.tasks) > 0, "tasks total must be a live number");
  assert.ok(Number(totals.completed) >= 0, "completed must be a number");
  assert.ok(Number(totals.interrupted) >= 0, "interrupted must be a number");
  assert.match(totals.cacheRate, /%|—/, "cache rate must carry % or em dash");
  assert.ok((totals.audit ?? "").length > 0, "audit lines must be rendered");
  assert.ok(totals.sessions.length > 0, "sessions must be rendered");
  assert.ok(totals.tools >= 1, "tool usage list must render at least one bar");
  assert.ok(totals.recs >= 1, "recommendations must render at least one");
  assert.ok(totals.recent >= 1, "recent tasks must render at least one");
  assert.ok(totals.canvas > 0, "trend canvas must be drawn");

  // zh/en expectations
  if (expectCjk) {
    assert.ok(/[\u4e00-\u9fff]/.test(await page.locator(".admin-tagline").innerText()), "zh mode must render CJK tagline");
    assert.ok(await page.locator("#adminUnlockBtn").innerText().then(t => /[\u4e00-\u9fff]/.test(t)), "zh unlock button must be Chinese");
  } else {
    const tagline = await page.locator(".admin-tagline").innerText();
    assert.ok(!/[\u4e00-\u9fff]/.test(tagline), "en mode must not leak CJK in tagline");
    const btn = await page.locator("#adminUnlockBtn").innerText();
    assert.ok(!/[\u4e00-\u9fff]/.test(btn), "en unlock button must be English");
  }

  // close and verify aria-hidden restored
  await page.click("#adminStageClose");
  assert.equal(await page.locator("#adminStage").getAttribute("aria-hidden"), "true");

  await page.close();
}

await checkMode("zh", true);
await checkMode("en", false);

if (errors.length) {
  console.error("admin smoke FAILED:");
  for (const e of errors) console.error(" ", e);
  process.exit(1);
}
console.log("admin smoke passed: 123 unlocked, totals live, tool-usage bars, recs, canvas trend, close restores hidden state, zero pageerror");
await browser.close();
