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

// A read that answered but saw only part of the data is still an answer — the
// rows and counts are real — but must not pose as complete. The backend reasons
// can be Chinese, so they travel in data-change-error while the visible copy
// comes from the dictionary. Counts remain on screen for a partial read.
const PARTIAL_REASON = "git 状态读取失败";

// M8-T1328: an honest warning that renders as raw, unstyled text is still a
// visual defect. Pin the shipped theme tokens rather than trusting the class.
async function assertWarnStyled(page, selector, label) {
  const info = await page.locator(selector).evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      background: style.backgroundColor,
      border: style.borderLeftWidth,
      display: style.display,
    };
  });
  assert.notEqual(info.background, "rgba(0, 0, 0, 0)", `${label}: warning needs a themed background`);
  assert.ok(parseFloat(info.border) >= 2, `${label}: warning needs an accent border: ${info.border}`);
  assert.ok(info.display !== "inline", `${label}: warning needs its own block layout`);
}

async function checkPartial(locale) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}/partial: ${e.message}`));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.route("**/api/changes", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      files: [{ path: "web/src/chat/stream.js", status: "modified", additions: 10, deletions: 2 }],
      additions: 10, deletions: 2,
      status_read_error: PARTIAL_REASON,
    }),
  }));
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(
    () => document.querySelector("#startupSplash")?.dataset.state === "ready",
    { timeout: 60000 },
  );
  await page.waitForFunction(
    () => !!document.querySelector('#changeList [data-change-status="partial"]'),
    { timeout: 20000 },
  );

  for (const selector of ["#changeList", "#fileList"]) {
    const warn = page.locator(`${selector} .change-partial-warn[data-change-status="partial"]`);
    assert.equal(await warn.count(), 1, `${locale}/partial: ${selector} must carry the partial marker`);
    assert.equal(await warn.getAttribute("data-change-error"), PARTIAL_REASON,
      `${locale}/partial: ${selector} must keep the raw Chinese reason machine-readable`);
    const text = (await warn.innerText()).trim();
    if (locale === "en") {
      assert.ok(!CJK.test(text), `${locale}/partial: ${selector} visible copy leaked CJK: ${text}`);
      assert.ok(/totals may be incomplete/i.test(text), `${locale}/partial: expected localized partial copy, saw: ${text}`);
    }
    await assertWarnStyled(page, `${selector} .change-partial-warn[data-change-status="partial"]`,
      `${locale}/partial ${selector}`);
  }
  // A partial read still shows its real numbers (unlike a failed read).
  const badge = (await page.locator("#changeTabCount").innerText()).trim();
  assert.equal(badge, "1", `${locale}/partial: real row count must remain on screen`);
  await page.close();
}

// The backend caps the row list at 120 but ships the real count in total_files.
// With 2 rows and total_files=5, the tab badge must say 5 (the truth), not 2
// (the displayed slice), and both surfaces must disclose the truncation.
async function checkTruncated(locale) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}/truncated: ${e.message}`));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.route("**/api/changes", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      files: [
        { path: "a.js", status: "modified", additions: 6, deletions: 1 },
        { path: "b.js", status: "added", additions: 4, deletions: 1 },
      ],
      total_files: 5,
      truncated: true,
      audit_window_truncated: true,
      additions: 10, deletions: 2,
    }),
  }));
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(
    () => document.querySelector("#startupSplash")?.dataset.state === "ready",
    { timeout: 60000 },
  );
  await page.waitForFunction(
    () => !!document.querySelector('#changeList [data-change-status="truncated"]'),
    { timeout: 20000 },
  );

  const badge = (await page.locator("#changeTabCount").innerText()).trim();
  assert.equal(badge, "5", `${locale}/truncated: badge must show the real total_files=5, not the 2 displayed rows`);

  for (const selector of ["#changeList", "#fileList"]) {
    const warn = page.locator(`${selector} .change-partial-warn[data-change-status="truncated"]`);
    assert.equal(await warn.count(), 1, `${locale}/truncated: ${selector} must disclose list truncation`);
    const text = (await warn.innerText()).trim();
    assert.ok(text.includes("2") && text.includes("5"), `${locale}/truncated: ${selector} must name shown/total: ${text}`);
    if (locale === "en") {
      assert.ok(!CJK.test(text), `${locale}/truncated: ${selector} visible copy leaked CJK: ${text}`);
      assert.ok(/Showing the first 2 of 5/.test(text), `${locale}/truncated: expected interpolated copy: ${text}`);
    }
    assert.equal(await page.locator(`${selector} .change-partial-warn[data-change-status="audit-truncated"]`).count(), 1,
      `${locale}/truncated: ${selector} must disclose audit-window truncation`);
    await assertWarnStyled(page, `${selector} .change-partial-warn[data-change-status="truncated"]`,
      `${locale}/truncated ${selector}`);
  }
  await page.close();
}

// M8-T1312: the honest-failure work must not let the normal path drift. Pin
// the three readings of one fact together: badge = total_files, the two rows
// lists = the delivered slice, summary +/- = the backend totals. A second
// variant has unreadable totals, where the summary must say "not counted"
// rather than inventing a zero, while the real row count stays on screen.
async function checkConsistent(locale, uncounted) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}/consistent: ${e.message}`));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.route("**/api/changes", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      files: [
        { path: "a.js", status: "modified", additions: 6, deletions: 1 },
        { path: "b.js", status: "added", additions: 4, deletions: 2 },
      ],
      total_files: 2,
      truncated: false,
      additions: uncounted ? null : 10,
      deletions: uncounted ? null : 3,
    }),
  }));
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(
    () => document.querySelector("#startupSplash")?.dataset.state === "ready",
    { timeout: 60000 },
  );
  await page.waitForFunction(
    () => document.querySelectorAll("#changeList .change-item-button").length === 2,
    { timeout: 20000 },
  );

  const badge = (await page.locator("#changeTabCount").innerText()).trim();
  assert.equal(badge, "2", `${locale}/consistent: badge must equal total_files=2`);
  assert.equal(await page.locator("#changeList .change-item-button").count(), 2, "change list row count");
  assert.equal(await page.locator("#fileList .file-row").count(), 2, "files tab row count");
  const summary = (await page.locator("#changeSummary").innerText()).trim();
  if (uncounted) {
    assert.ok(!/[+\-]\s*\d/.test(summary), `${locale}/consistent: unreadable totals must not become a count: ${summary}`);
    if (locale === "en") assert.ok(/not counted/i.test(summary), `${locale}/consistent: expected localized uncounted: ${summary}`);
  } else {
    assert.ok(/[+]\s*10/.test(summary) && /-\s*3/.test(summary), `${locale}/consistent: summary must show the real totals: ${summary}`);
  }
  // A complete, countable read carries none of the warning markers.
  for (const marker of ["unavailable", "denied", "partial", "truncated", "audit-truncated"]) {
    assert.equal(await page.locator(`[data-change-status="${marker}"]`).count(), 0,
      `${locale}/consistent: no ${marker} marker on a clean read`);
  }
  await page.close();
}

try {
  await checkConsistent("zh", false);
  await checkConsistent("en", false);
  await checkConsistent("zh", true);
  await checkConsistent("en", true);
  await checkMode("zh");
  await checkMode("en");
  await checkDenied("zh");
  await checkDenied("en");
  await checkPartial("zh");
  await checkPartial("en");
  await checkTruncated("zh");
  await checkTruncated("en");
  assert.deepEqual(errors, [], `no page errors: ${errors.join(" | ")}`);
  console.log("change-failure smoke passed: normal reads keep badge/rows/summary in agreement (uncounted stays uncounted); transport failure + denial fail on both surfaces; partial reads and truncation warn without hiding real counts; raw reasons machine-readable, visible copy CJK-free in EN, zero pageerror");
} finally {
  await browser.close();
}
