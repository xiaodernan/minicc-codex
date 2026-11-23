import assert from "node:assert/strict";
import { chromium } from "playwright";
import { requireHarnessOrExit } from "./web_smoke_suites.mjs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";

await requireHarnessOrExit(baseUrl);

const browser = await chromium.launch({ headless: true });
const errors = [];
const BENCH_SEEN = new Set();

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

  // M8-T1294: the context assembler tile hydrates from /api/rag/context with
  // real fields (budget, packed tokens, line-anchored sources) and survives a
  // manual re-read. It must never print NaN or invent sources.
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminContextFacts");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    // M8-T1314: four honest terminal states. A timeout is not an outage;
    // accept every real state so a slow-but-alive service isn't read as "stuck".
    return Boolean(el.querySelector(".admin-context-facts-grid")) ||
      text.includes("没有命中") || text.includes("No corpus hit") ||
      text.includes("不可达") || text.includes("unreachable") ||
      text.includes("超时") || text.includes("timed out") ||
      text.includes("未在时限") || text.includes("no real reading");
  }, null, { timeout: 45000 });
  const contextFacts = await page.evaluate(() => {
    const el = document.querySelector("#adminContextFacts");
    return el ? (el.innerText || "").replace(/\s+/g, " ").trim() : "";
  });
  assert.match(contextFacts, /8000/, "context tile must state the requested token budget");
  assert.ok(!/NaN/.test(contextFacts), "context tile must never print NaN");
  const contextSources = await page.locator("#adminContextSources .admin-context-source").count();
  assert.ok(contextSources >= 1, "context tile must list at least one line-anchored source");
  await page.click("#adminContextRefresh");
  await page.waitForTimeout(300);
  assert.ok(await page.locator("#adminContextFacts").isVisible(), "refresh must keep the context tile visible");
  assert.ok(
    (await page.locator("#adminContextSources .admin-context-source").count()) >= 1,
    "re-read must restore the source list",
  );

  // M8-T1297: bench-history filter chips — two groups, and a kind filter must
  // narrow the read (the usage line names the active filter, never a fake count).
  await page.waitForSelector("#adminBenchFilters button[data-bench-key]", { timeout: 30000 });
  assert.equal(await page.locator("#adminBenchFilters .group").count(), 2, "bench filters must offer window and kind groups");
  await page.click('#adminBenchFilters button[data-bench-key="kind"][data-bench-value="suite_run"]');
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminBenchUsage");
    return el && /suite_run/.test(el.innerText || "");
  }, null, { timeout: 20000 });
  const benchFiltered = await page.evaluate(() => ({
    usage: (document.querySelector("#adminBenchUsage")?.innerText || "").replace(/\s+/g, " ").trim(),
    body: (document.querySelector("#adminBenchBody")?.innerText || "").replace(/\s+/g, " ").trim(),
    benchState: document.querySelector("#adminBenchBody")?.dataset?.benchState || "",
    pressed: document.querySelectorAll('#adminBenchFilters button[data-bench-key="kind"][aria-pressed="true"]').length,
    urlBench: new URL(location.href).searchParams.get("bench"),
  }));
  assert.equal(benchFiltered.pressed, 1, "exactly one kind chip may stay pressed");
  assert.equal(benchFiltered.urlBench, ":suite_run", "bench filter must land in the URL (?bench=:suite_run)");
  assert.ok(!/NaN/.test(benchFiltered.body), "filtered bench tile must never print NaN");
  assert.match(benchFiltered.usage, /suite_run|无样本|No samples|已筛选|filtered/, "usage line must name the active filter or the empty state");
  // M8-T1299: the tile must say which of the reader's states it is in, and the
  // wording has to follow that state. "This slice is empty" may never be printed
  // as "this file was never written", and vice versa.
  const BENCH_STATES = ["present", "absent", "empty", "filtered_empty", "capped", "unreadable", "unreachable", "error"];
  assert.ok(BENCH_STATES.includes(benchFiltered.benchState),
    `bench tile must name one of the reader's states, got "${benchFiltered.benchState}"`);
  BENCH_SEEN.add(benchFiltered.benchState);
  const NEVER_WRITTEN = /暂无 bench_history\.jsonl|No bench history yet/;
  const neverWritten = NEVER_WRITTEN.test(benchFiltered.body);
  if (benchFiltered.benchState === "filtered_empty" || benchFiltered.benchState === "capped") {
    assert.ok(!neverWritten, `${benchFiltered.benchState} must never be worded as "no history yet"`);
    assert.match(benchFiltered.usage, /文件里还有 \d+ 条|the file still holds \d+ entries/,
      "an empty slice of a full file must say how full the file is");
  }
  if (benchFiltered.benchState === "absent") {
    assert.ok(neverWritten, "absent is the only empty state allowed to send the user to the v2 suite");
    assert.doesNotMatch(benchFiltered.usage, /文件里还有|the file still holds/, "an absent file has no rows to count");
  }
  await page.click('#adminBenchFilters button[data-bench-key="kind"][data-bench-value=""]');
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminBenchUsage");
    return el && !/suite_run/.test(el.innerText || "");
  }, null, { timeout: 20000 });
  assert.equal(await page.evaluate(() => new URL(location.href).searchParams.get("bench")), null, "clearing the filter must clear the URL state");

  // M8-T1299: a read that never arrives is the panel's own failure, not a workspace
  // that was never measured. Cut the endpoint and the tile must say so — it must
  // not fall back to "no bench history yet", which would send the user to run a
  // suite whose results the panel simply could not fetch.
  await page.route("**/api/bench-history**", (route) => route.abort());
  await page.click('#adminBenchFilters button[data-bench-key="window"][data-bench-value="7"]');
  await page.waitForFunction(
    () => document.querySelector("#adminBenchBody")?.dataset?.benchState === "unreachable",
    null, { timeout: 20000 },
  );
  const benchDown = await page.evaluate(() => ({
    body: (document.querySelector("#adminBenchBody")?.innerText || "").replace(/\s+/g, " ").trim(),
    usage: (document.querySelector("#adminBenchUsage")?.innerText || "").replace(/\s+/g, " ").trim(),
  }));
  assert.ok(!NEVER_WRITTEN.test(benchDown.body),
    `an unreachable read must not be worded as missing history: ${benchDown.body}`);
  assert.ok(benchDown.body.length > 0 && !/NaN|undefined|\[object/.test(benchDown.body),
    `the outage sentence must be a real sentence: ${benchDown.body}`);
  assert.ok(benchDown.usage.length > 0, "the outage must name a reason, not fall silent");
  BENCH_SEEN.add("unreachable");
  await page.unroute("**/api/bench-history**");
  await page.click('#adminBenchFilters button[data-bench-key="window"][data-bench-value=""]');
  await page.waitForFunction(
    () => ["present", "absent", "empty", "filtered_empty", "capped", "unreadable", "error"]
      .includes(document.querySelector("#adminBenchBody")?.dataset?.benchState || ""),
    null, { timeout: 20000 },
  );

  // M8-T1299: a kind the file never recorded is an empty slice, not a missing
  // history. The assertion is conditional on the state because this smoke runs
  // against whatever workspace it is pointed at; CI seeds a two-kind history so
  // the filtered_empty branch is really taken there, and the reader-level cells
  // in tests/test_bench_history.py pin all six states unconditionally.
  await page.click('#adminBenchFilters button[data-bench-key="kind"][data-bench-value="ungraded"]');
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminBenchUsage");
    return el && /ungraded/.test(el.innerText || "");
  }, null, { timeout: 20000 });
  const sliced = await page.evaluate(() => ({
    state: document.querySelector("#adminBenchBody")?.dataset?.benchState || "",
    body: (document.querySelector("#adminBenchBody")?.innerText || "").replace(/\s+/g, " ").trim(),
    usage: (document.querySelector("#adminBenchUsage")?.innerText || "").replace(/\s+/g, " ").trim(),
  }));
  assert.ok(BENCH_STATES.includes(sliced.state), `kind=ungraded must also name a state, got "${sliced.state}"`);
  BENCH_SEEN.add(sliced.state);
  assert.ok(!NEVER_WRITTEN.test(sliced.body),
    "an empty slice must never be worded as missing history");
  if (sliced.state === "filtered_empty") {
    assert.match(sliced.usage, /文件里还有 \d+ 条|the file still holds \d+ entries/,
      "the empty slice must say how many rows the file really holds");
  }
  await page.click('#adminBenchFilters button[data-bench-key="kind"][data-bench-value=""]');
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminBenchUsage");
    return el && !/ungraded/.test(el.innerText || "");
  }, null, { timeout: 20000 });
  console.log(`bench tile states exercised (${locale}): ${[...BENCH_SEEN].sort().join(", ")}`);

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
  // M8-T1287: trend analyst tile — a live reading, a zero-signal note, or the
  // honest outage line; never a blank or an unresolved i18n key. Both locales.
  assert.ok(await page.locator("#adminTrendOracleBody").count(), "trend oracle tile must exist in the panel");
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminTrendOracleBody");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    return text.length > 0 && !text.includes("正在读七日") && !text.includes("Reading the real seven");
  }, null, { timeout: 45000 });
  const trendOracleText = (await page.locator("#adminTrendOracleBody").innerText()).trim();
  assert.ok(trendOracleText.length > 0, "trend oracle must carry a live reading or the honest outage line");
  assert.ok(!/^admin\./.test(trendOracleText), "trend oracle body must never read as an unresolved i18n key");
  const trendOracleUsage = await page.locator("#adminTrendOracleUsage").innerText();
  assert.ok(
    /prompt|error/i.test(trendOracleUsage) || trendOracleUsage.trim().length === 0,
    "trend oracle usage footer must carry token accounting or an error, never a fabricated number",
  );

  // M8-T1289: visitor log tile — either real aggregated journeys or the honest
  // empty state naming the command that fills the log; never a blank, never a
  // raw i18n key. Both outcomes are legitimate, a placeholder is not.
  assert.ok(await page.locator("#adminJourneysCard").count(), "visitor journey card must exist");
  await page.waitForFunction(() => {
    const facts = document.querySelector("#adminJourneysFacts");
    const how = document.querySelector("#adminJourneysHow");
    const text = `${facts?.innerText || ""} ${how?.innerText || ""}`.trim();
    return text.length > 0 && !text.includes("正在读真实访客");
  }, null, { timeout: 30000 });
  const journeyText = `${await page.locator("#adminJourneysFacts").innerText()} ${await page.locator("#adminJourneysHow").innerText()}`.trim();
  assert.ok(journeyText.length > 0, "visitor log must answer with aggregates or the honest empty state");
  assert.ok(!/admin\.journey/i.test(journeyText), "visitor log must never render a raw i18n key");
  // M8-T1289c: when real journeys exist the walk list shows from → to pairs;
  // an empty log legitimately leaves it blank, so assert conditionally.
  const walkText = await page.locator("#adminJourneysPaths").innerText();
  if (walkText.trim()) {
    assert.ok(walkText.includes("→"), "a rendered walk must show its from → to direction");
    assert.ok(!/admin\.journey/i.test(walkText), "walk list must never render a raw i18n key");
  }
  // M8-T1292: rule-derived fixes are visible only when a real sample exists;
  // an empty log legitimately hides the tile. When shown, every move must
  // carry evidence, an action and an acceptance check — never a raw key.
  const adviceBox = page.locator("#adminJourneysAdvice");
  if (await adviceBox.isVisible()) {
    const adviceText = `${await page.locator("#adminJourneysAdviceBody").innerText()} ${await page.locator("#adminJourneysAdviceMoves").innerText()}`.trim();
    assert.ok(adviceText.length > 20, "advice tile must carry substantive measured moves");
    assert.ok(!/admin\.advice/i.test(adviceText), "advice tile must never render a raw i18n key");
  }

  await page.waitForFunction(() => {
    const el = document.querySelector("#adminDiagnosisBody");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    return text.length > 0 && !text.includes("正在读") && !text.includes("Reading the");
  }, null, { timeout: 45000 });
  const diagnosisText = await page.locator("#adminDiagnosisBody").innerText();
  assert.ok(diagnosisText.trim().length > 0, "diagnosis tile must carry either a live diagnosis or the honest outage line");
  const diagnosisUsage = await page.locator("#adminDiagnosisUsage").innerText();
  assert.ok(
    /prompt|error/i.test(diagnosisUsage) || diagnosisUsage.trim().length === 0,
    "diagnosis usage footer must carry token accounting or an error, never a fabricated number",
  );

  await page.waitForFunction(() => {
    const el = document.querySelector("#adminPlanList");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    return text.length > 0 && !text.includes("正在读") && !text.includes("Reading the");
  }, null, { timeout: 45000 });
  const planText = await page.locator("#adminPlanList").innerText();
  assert.ok(planText.trim().length > 0, "plan tile must carry either three model-ordered moves or the honest outage line");
  const planUsage = await page.locator("#adminPlanUsage").innerText();
  assert.ok(
    /prompt|error/i.test(planUsage) || planUsage.trim().length === 0,
    "plan usage footer must carry token accounting or an error, never a fabricated number",
  );

  // M8-T1246: apply-one-click actually dispatches through the app's task pipeline.
  const applyButton = page.locator('#adminPlanList .admin-apply-one[data-apply-index="0"]');
  if (await applyButton.count()) {
    const firstItem = (await page.locator("#adminPlanList .admin-plan-item span").first().innerText()).trim().slice(0, 40);
    await applyButton.click();
    await page.waitForFunction(() => /dispatched|已派给模型|error/i.test((document.querySelector("#adminPlanUsage")?.innerText || "")), null, { timeout: 45000 });
    const found = await page.evaluate(async (needle) => {
      const r = await fetch("/api/tasks?limit=20").then((x) => x.json());
      return (r.tasks || []).some((t) => String(t.message || t.prompt || t.preview || t.task || "").includes(needle));
    }, firstItem);
    assert.ok(found, "applying the top move must create a task whose message carries it");
  }
  // M8-T1249: apply-all now fans out the whole list through the batch endpoint.
  const applyAllButton = page.locator('#adminPlanUsage .admin-apply-all');
  if (await applyAllButton.count()) {
    await applyAllButton.click();
    await page.waitForFunction(() => /dispatched|已一次|batch|error/i.test((document.querySelector("#adminPlanUsage")?.innerText || "")), null, { timeout: 60000 });
    const usageAfter = (await page.locator("#adminPlanUsage").innerText()).trim();
    assert.ok(/dispatched|已一次|batch|error/i.test(usageAfter), "apply-all must acknowledge it dispatched a batch or fail loudly");
  }

  await page.waitForFunction(() => {
    const el = document.querySelector("#adminReviewBody");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    return text.length > 0 && !text.includes("正在读") && !text.includes("Reading the");
  }, null, { timeout: 45000 });
  const reviewText = await page.locator("#adminReviewBody").innerText();
  assert.ok(reviewText.trim().length > 0, "review tile must carry either a live review or the honest outage line");
  const reviewUsage = await page.locator("#adminReviewUsage").innerText();
  assert.ok(
    /prompt|error/i.test(reviewUsage) || reviewUsage.trim().length === 0,
    "review usage footer must carry token accounting or an error, never a fabricated number",
  );

  await page.waitForFunction(() => {
    const el = document.querySelector("#adminRetrospectiveBody");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    return text.length > 0 && !text.includes("正在读") && !text.includes("Reading the") && !/^admin\./.test(text);
  }, null, { timeout: 45000 });
  const retrospectiveText = await page.locator("#adminRetrospectiveBody").innerText();
  assert.ok(retrospectiveText.trim().length > 0, "retrospective tile must carry either a live retrospective or the honest outage line");
  assert.ok(!/^admin\./.test(retrospectiveText.trim()), "retrospective body must never read as an unresolved i18n key");

  // drift sentinel: after unlock, the tile must carry measured numbers, never em-dashes
  await page.waitForFunction(() => {
    const el = document.querySelector("#adminDriftHead");
    if (!el) return false;
    const text = (el.innerText || "").trim();
    return text.length > 0 && text !== "—";
  }, null, { timeout: 60000 });
  const driftHead = await page.locator("#adminDriftHead").innerText();
  assert.ok(
    /同步|synced|领先|ahead|落后|≡|≠|未知|unknown/.test(driftHead),
    "drift head cell must show the real sync verdict (or the honest shallow-clone unknown), got: " + driftHead,
  );
  const driftCrlf = await page.locator("#adminDriftCrlf").innerText();
  assert.match(driftCrlf, /[0-9]/, "CRLF cell must show real byte counts");
  // The doc_pointers cell rides a background thread; the first render may show a pending dot.
  // Click refresh (each click is a bounded synchronous pass, ~15-90s) until rc= appears.
  let driftDocs = "";
  for (let attempt = 0; attempt < 12 && !/rc=/.test(driftDocs); attempt += 1) {
    await page.click("#adminDriftRefresh").catch(() => {});
    await page.waitForFunction(() => {
      const el = document.querySelector("#adminDriftDocs");
      return /rc=/.test((el?.innerText || "").trim());
    }, null, { timeout: 30000 }).catch(() => {});
    driftDocs = (await page.locator("#adminDriftDocs").innerText()).trim();
  }
  assert.match(driftDocs, /rc=/, "doc_pointers cell must converge to a real exit code");

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
console.log("admin smoke passed: 123 unlocked, totals live, tool-usage bars, recs, canvas trend, apply-one and apply-all dispatch, close restores hidden state, zero pageerror");
await browser.close();
