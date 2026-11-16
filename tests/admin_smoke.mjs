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
  // wait for the summary to hydrate rather than sleep a fixed window —
  // the numbers are genuinely fetched from disk and may take a beat
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminTotalTasks");
    return el && el.innerText.trim() && el.innerText.trim() !== "—";
  }, null, { timeout: 45000 });

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
    streak: document.querySelector("#adminStreak")?.innerText,
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
  assert.ok((totals.streak ?? "").trim().length > 0, "completion streak must render");
  assert.ok(totals.tools >= 1, "tool usage list must render at least one bar");
  assert.ok(totals.recs >= 1, "recommendations must render at least one");
  assert.ok(totals.recent >= 1, "recent tasks must render at least one");
  assert.ok(totals.canvas > 0, "trend canvas must be drawn");

  // workspace brief: either the live model wrote something, or the honest outage line —
  // but never an empty or ambiguous tile. The dummy provider cannot answer, so the
  // honest expectation on CI is the unavailable line.
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminBriefBody");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    return text.length > 0 && !text.includes("正在读取") && !text.includes("Reading the");
  }, null, { timeout: 45000 });
  const briefText = await page.locator("#adminBriefBody").innerText();
  assert.ok(briefText.trim().length > 0, "brief tile must carry either a live brief or the honest outage line");
  const briefOutage = await page.evaluate(() => {
    const el = document.querySelector("#adminBriefBody");
    return el ? (el.innerText || "").trim() : "";
  });
  assert.ok(
    /缓存|主线|main|模型|分支|Outage|unreachable|model|记录|记录|审计|cache|task|提交/i.test(briefOutage) || briefOutage.length >= 12,
    "brief text should be substantive or the honest outage sentence",
  );
  const briefUsage = await page.locator("#adminBriefUsage").innerText();
  // when the model answered, the usage footer must carry the token accounting;
  // when the wire is down the footer carries the error instead
  assert.ok(
    /prompt|error/i.test(briefUsage) || briefUsage.trim().length === 0,
    "usage footer must carry token accounting or an error, never a fabricated number",
  );

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
