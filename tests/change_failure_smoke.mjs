// M8-T1307 — a failed /api/changes read must fail honestly on EVERY surface of
// the fact. Before this guard the catch repainted #changeList with "unavailable"
// while #fileList (the Files tab) kept the last successful rows - or stayed
// blank on a first-read failure - and the tab badge / +/- summary went on
// advertising the numbers of the last read that did answer. One question, two
// contradictory answers. This suite aborts the read in a real browser and checks
// both surfaces agree, in both locales, with no stale counters and no CJK in EN.

import assert from "node:assert/strict";
import { chromium } from "playwright";
import { requireHarnessOrExit } from "./web_smoke_suites.mjs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
await requireHarnessOrExit(baseUrl);

const CJK = /[\u4e00-\u9fff]/;
const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  // A real network failure on the change read - the exact shape the product's
  // catch sees. Everything else comes from the real server.
  await page.route("**/api/changes", (route) => route.abort("failed"));
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(
    () => document.querySelector("#startupSplash")?.dataset.state === "ready",
    { timeout: 60000 },
  );
  await page.waitForFunction(
    () => !!document.querySelector('#changeList [data-change-status="unavailable"]'),
    { timeout: 20000 },
  );

  for (const selector of ["#changeList", "#fileList"]) {
    const cell = page.locator(`${selector} .file-tree-status[data-change-status="unavailable"]`);
    assert.equal(await cell.count(), 1, `${locale}: ${selector} must carry the failure status`);
    const text = (await cell.innerText()).trim();
    assert.ok(text.length > 0, `${locale}: ${selector} failure cell must have words`);
    if (locale === "en") {
      assert.ok(!CJK.test(text), `${locale}: ${selector} failure copy leaked CJK: ${text}`);
    }
  }

  const badge = (await page.locator("#changeTabCount").innerText()).trim();
  const summary = (await page.locator("#changeSummary").innerText()).trim();
  assert.ok(!/\d/.test(badge), `${locale}: tab badge still advertises a count after a failed read: ${badge}`);
  assert.ok(!/[+\-]\s*\d/.test(summary), `${locale}: summary still advertises a count: ${summary}`);
  await page.close();
}

// A well-formed 200 can still be an error: the permission gate answers
// {"status":"error","summary":...} with no files. The raw summary is Chinese;
// it must travel in data-change-error (not a visible text node) so EN stays
// CJK-free, while the on-screen copy comes from the dictionary.
const DENIED_SUMMARY = "permissions.json deny 规则拒绝了此差异视图";

async function checkDenied(locale) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}/denied: ${e.message}`));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.route("**/api/changes", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ status: "error", summary: DENIED_SUMMARY, files: [] }),
  }));
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(
    () => document.querySelector("#startupSplash")?.dataset.state === "ready",
    { timeout: 60000 },
  );
  await page.waitForFunction(
    () => !!document.querySelector('#changeList [data-change-status="denied"]'),
    { timeout: 20000 },
  );

  for (const selector of ["#changeList", "#fileList"]) {
    const cell = page.locator(`${selector} .file-tree-status[data-change-status="denied"]`);
    assert.equal(await cell.count(), 1, `${locale}/denied: ${selector} must carry the denied status`);
    assert.equal(await cell.getAttribute("data-change-error"), DENIED_SUMMARY,
      `${locale}/denied: ${selector} must keep the raw reason machine-readable`);
    const text = (await cell.innerText()).trim();
    assert.ok(text.length > 0, `${locale}/denied: ${selector} must have localized words`);
    if (locale === "en") {
      assert.ok(!CJK.test(text), `${locale}/denied: ${selector} visible copy leaked CJK: ${text}`);
      assert.ok(/refused by an access rule/i.test(text), `${locale}/denied: expected localized denial copy, saw: ${text}`);
    }
  }

  const badge = (await page.locator("#changeTabCount").innerText()).trim();
  const summary = (await page.locator("#changeSummary").innerText()).trim();
  assert.ok(!/\d/.test(badge), `${locale}/denied: tab badge still advertises a count: ${badge}`);
  assert.ok(!/[+\-]\s*\d/.test(summary), `${locale}/denied: summary still advertises a count: ${summary}`);
  await page.close();
}

try {
  await checkMode("zh");
  await checkMode("en");
  await checkDenied("zh");
  await checkDenied("en");
  assert.deepEqual(errors, [], `no page errors: ${errors.join(" | ")}`);
  console.log("change-failure smoke passed: transport failure + 200/status:error denial both fail on both surfaces in zh/en, raw reason kept machine-readable, visible copy CJK-free in EN, no stale counts, zero pageerror");
} finally {
  await browser.close();
}
