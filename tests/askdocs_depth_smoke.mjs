// M8-T1316: the Ask-the-repo wide-context path, driven in a real browser.
// The upstream model account is closed, so /api/rag/query is stubbed at the
// network seam with a real-shaped payload. What is NOT stubbed: the panel's
// depth selector, the budget it appends to the URL, and the DOM it renders.

import assert from "node:assert/strict";
import { chromium } from "playwright";
import { requireHarnessOrExit } from "./web_smoke_suites.mjs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
await requireHarnessOrExit(baseUrl);

const browser = await chromium.launch({ headless: true });
const errors = [];
const calls = [];

const PAYLOAD = {
  query: "cache",
  answer: "The docs describe prefix affinity.",
  model: "stub-model",
  base_url: "https://example.invalid/v1",
  usage: { prompt_tokens: 1200, completion_tokens: 20, total_tokens: 1220, prompt_cache_hit_tokens: 900 },
  context: {
    budget_tokens: 8000,
    estimated_tokens: 1114,
    candidates: 12,
    chunks: 8,
    prefix_fingerprint: "abc123def4567890",
    truncated: true,
    cost_estimate: { usd: 0.1325, prompt_tokens: 1114, max_output_tokens: 700, basis: "upper estimate" },
  },
  sources: [
    { source: "ROADMAP_TO_PRODUCT.md", score: 9.12, chunk: "prefix cache stays byte-stable", start_line: 12, end_line: 30 },
    { source: "README.md", score: 7.4, chunk: "load test at twenty concurrent requests", start_line: 40, end_line: 55 },
  ],
};

for (const locale of ["zh", "en"]) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => {
    localStorage.clear();
    localStorage.setItem("minicc-locale", l);
  }, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(() => document.querySelector("#startupSplash")?.dataset.state === "ready",
    null, { timeout: 45000 });

  await page.route("**/api/rag/query**", async (route) => {
    const url = route.request().url();
    calls.push(url);
    const deep = url.includes("budget=50000");
    const body = {
      ...PAYLOAD,
      context: {
        ...PAYLOAD.context,
        budget_tokens: deep ? 50000 : 8000,
        estimated_tokens: deep ? 48610 : 1114,
        candidates: deep ? 272 : 12,
        fanout: deep ? 48 : 6,
      },
    };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.click('.nav-item[data-view="askdocs"]');
  await page.waitForSelector("#askdocsDepth");
  assert.equal(await page.locator("#askdocsDepth option").count(), 3, "depth selector offers precise + wide + deep");
  await page.fill("#askdocsQuestion", "cache hit rate");
  await page.selectOption("#askdocsDepth", "8000");
  await page.click("#askdocsSubmit");

  await page.waitForSelector(".askdocs-context-evidence", { timeout: 20000 });
  const finalUrl = calls[calls.length - 1];
  assert.ok(finalUrl.includes("budget=8000"), `wide request must carry budget: ${finalUrl}`);

  const grid = (await page.locator(".askdocs-context-grid").textContent()).replace(/\s+/g, " ");
  assert.ok(grid.includes("8000"), "budget shown in evidence");
  assert.ok(grid.includes("1114"), "packed tokens shown in evidence");
  assert.ok(grid.includes("abc123def4567890"), "prefix fingerprint shown in evidence");
  assert.ok(grid.includes("$0.1325"), "cost estimate shown from the shared price table");
  assert.ok(!/NaN|undefined/.test(grid), "evidence must carry no NaN/undefined");

  const meta = await page.locator(".askdocs-meta").innerText();
  assert.ok(locale === "zh" ? meta.includes("宽上下文") : meta.includes("wide context"),
    "meta must mark the wide-context mode in the active locale");

  const anchors = await page.locator(".askdocs-source-file").allInnerTexts();
  assert.ok(anchors.some((s) => s.includes("L12")), "sources must show real line anchors");

  // Deep mode: the budget alone is not enough — recall knobs must go on the
  // wire too, or there is nothing to pack at 50k. The cost warning must show.
  const wideCalls = calls.length;
  await page.selectOption("#askdocsDepth", "50000:48:20");
  await page.click("#askdocsSubmit");
  await page.waitForFunction((n) => {
    const grid = document.querySelector(".askdocs-context-grid");
    return grid && grid.textContent.includes("48610") && n >= 0;
  }, wideCalls, { timeout: 20000 });
  const deepUrl = calls[calls.length - 1];
  assert.ok(deepUrl.includes("budget=50000") && deepUrl.includes("fanout=48") && deepUrl.includes("per=20"),
    `deep mode must carry budget + recall knobs: ${deepUrl}`);
  const deepGrid = (await page.locator(".askdocs-context-grid").textContent()).replace(/\s+/g, " ");
  assert.ok(deepGrid.includes("48610"), "deep packed tokens shown");
  assert.ok(deepGrid.includes("272"), "deep candidate count shown");
  assert.equal(await page.locator(".askdocs-context-warning").count(), 1, "deep mode must warn about cost/no-model");

  // Precise mode: no budget parameter on the wire.
  const before = calls.length;
  await page.selectOption("#askdocsDepth", "");
  await page.click("#askdocsSubmit");
  await page.waitForTimeout(500);
  assert.ok(calls.length > before, "precise ask must still hit the route");
  const preciseUrl = calls[calls.length - 1];
  assert.ok(!preciseUrl.includes("budget="), `precise request must not carry budget: ${preciseUrl}`);

  if (locale === "en") {
    const body = await page.locator(".askdocs-shell").innerText();
    assert.ok(!/[\u4e00-\u9fff]/.test(body), "English panel must render zero CJK");
  }
  await page.close();
}

await browser.close();
assert.deepEqual(errors, [], `page errors: ${errors.join(" | ")}`);
console.log("askdocs depth smoke passed: zh/en wide budget reaches the route, evidence shows real tokens/fingerprint/line anchors, precise mode stays legacy, zero pageerror");
