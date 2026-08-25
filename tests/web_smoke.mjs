import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const screenshotsDir = "output";

function state(page, expression) {
  return page.evaluate((source) => window.eval(source), expression);
}

async function assertCanvasPainted(page) {
  const paintedPixels = await page.locator("#gameCanvas").evaluate((canvas) => {
    const context = canvas.getContext("2d");
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let index = 3; index < pixels.length; index += 64) count += pixels[index] > 0 ? 1 : 0;
    return count;
  });
  assert.ok(paintedPixels > 100, "game canvas should contain rendered pixels");
}

async function openGame(page) {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const arcadeButton = page.locator("#arcadeButton");
  if ((await page.evaluate(() => window.innerWidth)) <= 780) {
    await page.locator("#sidebarOpen").click();
    await page.locator(".sidebar.open").waitFor();
  }
  await arcadeButton.click();
  await page.locator("#gameModal.show").waitFor();
  await assertCanvasPainted(page);
}

async function runAgentTimelineSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const result = await page.evaluate(async () => {
    const events = [
      { kind: "trace", code: "model_update", phase: "planning", status: "ok", summary: "模型给出了行动说明", detail: { turn: 1, text: "先读取入口文件，再根据证据决定检查路径。" } },
      { kind: "trace", code: "model_decision", phase: "planning", status: "ok", summary: "模型已完成本轮判断", detail: { turn: 1, tool_count: 2, tools: ["read_file", "grep"] } },
      { kind: "trace", code: "tool_round_started", phase: "tool", status: "ok", summary: "开始工具轮次", detail: { turn: 1 } },
      { kind: "tool", name: "read_file", status: "ok", summary: "读取入口文件", path: "src/main.js", output: "读取结果：入口初始化和路由挂载均存在。", data: { digest: "abc123", line_count: 42 }, duration_ms: 12.4, risk: "readonly" },
      { kind: "tool", name: "grep", status: "ok", summary: "搜索路由", path: "src", output: "命中 3 处：src/main.js:4、src/router.js:8、src/router.js:19", data: { files_scanned: 8, matches: 3 }, duration_ms: 18.2, risk: "readonly" },
      { kind: "trace", code: "tool_round_finished", phase: "planning", status: "ok", summary: "工具结果已合并", detail: { turn: 1, tool_count: 2, results: [{ tool: "read_file", status: "ok", observation: "入口和路由均存在" }, { tool: "grep", status: "ok", observation: "命中 3 处" }], new_information: ["read_file: 入口和路由均存在", "grep: 命中 3 处"], failed_tools: [], needs_repair: false, verification_required: false, next_action: "继续检查路由" } },
      { kind: "trace", code: "feedback_observed", phase: "planning", status: "ok", summary: "自反馈已记录", detail: { turn: 1, assessment: "本轮产生了新信息", observations: ["入口和路由均存在"], constraints: [], next_action: "继续检查路由" } },
      { kind: "trace", code: "replan", phase: "planning", status: "ok", summary: "已收到工具结果，正在判断下一步", detail: { turn: 2, previous_turn: 1, trigger: "上一轮工具结果已合并", observed: ["入口和路由均存在"], constraints: ["需要定位布局约束"], next_action: "检查样式并验证移动端" } },
      { kind: "trace", code: "model_update", phase: "planning", status: "ok", summary: "模型给出了行动说明", detail: { turn: 2, text: "证据指向布局层，接下来检查样式约束并验证移动端。" } },
      { kind: "trace", code: "tool_round_started", phase: "tool", status: "ok", summary: "开始工具轮次", detail: { turn: 2 } },
      { kind: "tool", name: "bash", status: "error", summary: "移动端检查失败", command: "npm run test:web" },
      { kind: "trace", code: "tool_round_finished", phase: "planning", status: "error", summary: "工具结果已合并", detail: { turn: 2, tool_count: 1, results: [{ tool: "bash", status: "error", observation: "移动端检查失败" }], new_information: ["bash: 移动端检查失败"], failed_tools: ["bash"], needs_repair: true, verification_required: true, next_action: "修复后重新验证" } },
      { kind: "trace", code: "feedback_observed", phase: "planning", status: "error", summary: "自反馈已记录", detail: { turn: 2, assessment: "本轮产生了新信息", observations: ["移动端检查失败"], constraints: ["需要修复 bash 失败"], next_action: "修复后重新验证" } },
    ];
    const host = document.createElement("div");
    host.innerHTML = eventTimelineMarkup(events);
    document.body.append(host);
    const order = [...host.children].map((node) => node.matches(".stage-summary")
      ? `stage:${node.dataset.stageCode}`
      : `round:${node.dataset.agentRound}`);
    const rounds = [...host.querySelectorAll("details.agent-round")];
    const summaryText = [...host.querySelectorAll('[data-stage-code="model_update"]')].map((node) => node.textContent);
    const firstTool = host.querySelector("details.tool-event");
    const toolInitiallyClosed = firstTool?.open === false;
    const toolDetailsInitiallyClosed = [...(firstTool?.querySelectorAll("details.tool-result-fold") || [])].every((detail) => !detail.open);
    firstTool.open = true;
    const toolResultVisible = firstTool?.textContent.includes("入口初始化") && firstTool?.textContent.includes("abc123");
    const resultSummary = host.querySelector('[data-stage-code="tool_round_finished"]')?.textContent || "";
    const replanSummary = host.querySelector('[data-stage-code="replan"]')?.textContent || "";
    const feedbackSummary = host.querySelector('[data-stage-code="feedback_observed"]')?.textContent || "";
    const resultDetailsInitiallyClosed = host.querySelector('[data-stage-code="tool_round_finished"] details.trace-evidence')?.open === false;
    const replanDetailsInitiallyClosed = host.querySelector('[data-stage-code="replan"] details.trace-evidence')?.open === false;
    const feedbackDetailsInitiallyClosed = host.querySelector('[data-stage-code="feedback_observed"] details.trace-evidence')?.open === false;

    const loading = document.createElement("article");
    loading.className = "message assistant-message loading";
    loading.id = "timeline-scroll-loading";
    loading.innerHTML = '<div class="message-body"></div>';
    document.querySelector("#messageList").append(loading);
    syncLiveEvents(loading, events);
    const liveRound = loading.querySelector("details.agent-round");
    liveRound.open = true;
    const liveTool = loading.querySelector("details.tool-event");
    liveTool.open = true;
    syncLiveEvents(loading, [...events, { kind: "trace", code: "verification_observed", phase: "planning", status: "ok", summary: "已收到验证证据", detail: { turn: 2 } }]);
    const preservedOpen = loading.querySelector("details.agent-round")?.open === true;
    const preservedToolOpen = loading.querySelector("details.tool-event")?.open === true;

    const area = document.querySelector("#chatArea");
    const list = document.querySelector("#messageList");
    area.style.height = "420px";
    area.style.minHeight = "0";
    area.style.overflowY = "auto";
    area.style.scrollBehavior = "auto";
    list.innerHTML = Array.from({ length: 24 }, (_, index) => `<article class="message assistant-message" data-chat-anchor="filler-${index}"><div class="message-body"><p>用于滚动回归的历史消息 ${index}。保持用户正在阅读的内容不被后台刷新推走。</p></div></article>`).join("");
    addLoadingMessage("timeline-scroll-loading", { status: "running", phase: "tool", events }, { scrollToLatest: false });
    area.scrollTop = Math.floor(Math.max(0, area.scrollHeight - area.clientHeight) / 2);
    const beforeUpdate = area.scrollTop;
    updateLiveTask("timeline-scroll-loading", { status: "running", phase: "tool", events, stream_text: "" });
    const afterUpdate = area.scrollTop;
    await new Promise((resolve) => requestAnimationFrame(resolve));
    addAssistantMessage({ status: "completed", answer: "验证完成。", events, turns: 2, tool_calls_total: 3 }, "timeline-scroll-loading");
    const afterComplete = area.scrollTop;
    const finalAnchor = document.querySelector('[data-chat-anchor="live-timeline-scroll-loading"]');
    return {
      order,
      roundCount: rounds.length,
      allRoundsClosed: rounds.every((round) => !round.open),
      failedRoundClosed: rounds.every((round) => !round.open),
      toolInitiallyClosed,
      toolDetailsInitiallyClosed,
      toolResultVisible,
      resultDetailsInitiallyClosed,
      replanDetailsInitiallyClosed,
      feedbackDetailsInitiallyClosed,
      resultSummary,
      replanSummary,
      feedbackSummary,
      modelSummaryVisible: summaryText.some((text) => text.includes("先读取入口文件")) && summaryText.some((text) => text.includes("证据指向布局层")),
      preservedOpen,
      preservedToolOpen,
      scrollDeltaUpdate: Math.abs(afterUpdate - beforeUpdate),
      scrollDeltaComplete: Math.abs(afterComplete - afterUpdate),
      finalAnchor: Boolean(finalAnchor),
    };
  });
  assert.deepEqual(result.order, [
    "stage:model_update", "stage:model_decision", "round:1", "stage:tool_round_finished", "stage:feedback_observed",
    "stage:replan", "stage:model_update", "round:2", "stage:tool_round_finished", "stage:feedback_observed",
  ], `timeline should preserve stage/tool order: ${JSON.stringify(result)}`);
  assert.equal(result.roundCount, 2, "contiguous tool calls should form two collapsed rounds");
  assert.equal(result.allRoundsClosed, true, "tool rounds must start collapsed");
  assert.equal(result.failedRoundClosed, true, "failed tool rounds must not auto-expand");
  assert.equal(result.toolInitiallyClosed, true, "individual tool calls must start collapsed");
  assert.equal(result.toolDetailsInitiallyClosed, true, "large tool result blocks must start collapsed");
  assert.equal(result.toolResultVisible, true, "expanded tool calls should show output and structured data");
  assert.equal(result.resultDetailsInitiallyClosed, true, "merged result details must start collapsed");
  assert.equal(result.replanDetailsInitiallyClosed, true, "re-plan details must start collapsed");
  assert.equal(result.feedbackDetailsInitiallyClosed, true, "self-feedback details must start collapsed");
  assert.match(result.resultSummary, /命中 3 处|新信息|入口和路由/);
  assert.match(result.replanSummary, /上一轮工具结果已合并|检查样式|约束/);
  assert.match(result.feedbackSummary, /产生了新信息|继续检查路由/);
  assert.equal(result.modelSummaryVisible, true, "public model updates should be visible between tool rounds");
  assert.equal(result.preservedOpen, true, "a manually opened tool round should survive live refresh");
  assert.equal(result.preservedToolOpen, true, "a manually opened tool result should survive live refresh");
  assert.ok(result.scrollDeltaUpdate <= 1, `live updates should preserve reading position: ${JSON.stringify(result)}`);
  assert.ok(result.scrollDeltaComplete <= 1, `completion replacement should preserve reading position: ${JSON.stringify(result)}`);
  assert.equal(result.finalAnchor, true, "the final message should retain the live message anchor");
  assert.deepEqual(consoleErrors, [], `timeline browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

async function runDesktopSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const initialTheme = await state(page, "document.documentElement.dataset.theme");
  await page.locator("#themeButton").click();
  const toggledTheme = await state(page, "document.documentElement.dataset.theme");
  assert.notEqual(toggledTheme, initialTheme, "theme control should switch theme");
  assert.equal(await state(page, "localStorage.getItem('minicc-theme')"), toggledTheme, "theme preference should persist");
  if (toggledTheme !== "light") await page.locator("#themeButton").click();
  assert.equal(await state(page, "document.documentElement.dataset.theme"), "light", "theme control should enable light mode");
  assert.match(await page.locator("#themeButton").getAttribute("aria-label"), /暗色|dark/i);
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await state(page, "document.documentElement.dataset.theme"), "light", "light preference should survive reload");
  await page.locator("#focusToggle").click();
  assert.equal(await state(page, "document.documentElement.dataset.focusMode"), "true", "focus mode should hide nonessential navigation");
  assert.equal(await page.locator(".sidebar").evaluate((node) => getComputedStyle(node).display), "none", "focus mode should hide the task sidebar");
  assert.equal(await page.locator(".inspector").evaluate((node) => getComputedStyle(node).display), "none", "focus mode should hide the inspector");
  await page.locator("#focusToggle").click();
  assert.equal(await state(page, "document.documentElement.dataset.focusMode"), "false", "focus mode should be reversible");
  const answerLayout = await page.evaluate(() => {
    const message = document.createElement("article");
    message.className = "message assistant-message";
    message.innerHTML = '<div class="message-body"><p class="answer-callout">已补齐可审计证据：<code>web/app.js</code> 中的 <code>clearPlantSelection()</code> 调用已恢复，随后运行 <code>npm run test:web</code> 通过。最终结果应作为自然段落阅读，而不是逐字挤压成多列。</p></div>';
    document.querySelector("#messageList").append(message);
    const callout = message.querySelector(".answer-callout");
    const code = message.querySelector("code");
    const rect = callout.getBoundingClientRect();
    const result = { width: rect.width, height: rect.height, codeHeight: code.getBoundingClientRect().height };
    message.remove();
    return result;
  });
  assert.ok(answerLayout.width >= 500, "desktop result summary should retain a readable column: " + JSON.stringify(answerLayout));
  assert.ok(answerLayout.height < 180, "Chinese result summary must not collapse into character columns: " + JSON.stringify(answerLayout));
  assert.ok(answerLayout.codeHeight < 32, "inline code must remain inline: " + JSON.stringify(answerLayout));
  const desktopLayout = await page.evaluate(() => ({ viewport: window.innerWidth, width: document.documentElement.scrollWidth, taskWidth: document.querySelector(".message").getBoundingClientRect().width }));
  assert.ok(desktopLayout.width <= desktopLayout.viewport + 1, `desktop page should not overflow horizontally: ${JSON.stringify(desktopLayout)}`);
  await openGame(page);
  await page.locator("#gameDifficulty").selectOption("normal");
  assert.deepEqual(await state(page, "({ difficulty: game.difficulty, sun: game.sun, target: game.waveTarget })"), {
    difficulty: "normal", sun: 200, target: 8,
  });
  await page.locator("#gameDifficulty").selectOption("nightmare");
  assert.deepEqual(await state(page, "({ difficulty: game.difficulty, sun: game.sun, target: game.waveTarget })"), {
    difficulty: "nightmare", sun: 150, target: 11,
  });

  await page.locator("#gameStart").click();
  await page.waitForTimeout(120);
  const audioStarted = await state(page, "({ running: game.running, hasAudio: Boolean(game.audio), audioState: game.audio?.ctx?.state || null })");
  assert.equal(audioStarted.running, true, "start button should begin a battle");
  assert.equal(audioStarted.hasAudio, true, "a user gesture should initialize Web Audio when available");
  assert.ok(["running", "suspended"].includes(audioStarted.audioState), "audio context should be initialized");

  await page.locator("#gameVolume").evaluate((input) => {
    input.value = "35";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.deepEqual(await state(page, "({ volume: game.volume, master: Boolean(game.audio?.master) })"), { volume: 35, master: true });
  await page.locator("#gameSoundToggle").click();
  assert.equal(await state(page, "game.musicOn"), false, "sound toggle should disable sound");
  await page.locator("#gameSoundToggle").click();
  assert.equal(await state(page, "game.musicOn"), true, "sound toggle should re-enable sound");

  await page.locator("#gamePause").click();
  const manualPauseStart = await state(page, "game.elapsed");
  await page.waitForTimeout(140);
  assert.equal(await state(page, "game.elapsed"), manualPauseStart, "manual pause must freeze elapsed time");
  await page.locator("#gamePause").click();
  await page.waitForTimeout(80);
  assert.ok(await state(page, "game.elapsed") > manualPauseStart, "resume should advance elapsed time");

  await state(page, "Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'))");
  const hiddenPauseStart = await state(page, "game.elapsed");
  assert.equal(await state(page, "game.pauseReasons.has('visibility') && game.paused"), true, "visibility change should pause the battle");
  await page.waitForTimeout(140);
  assert.equal(await state(page, "game.elapsed"), hiddenPauseStart, "hidden page must freeze elapsed time");
  await state(page, "Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange'))");
  await page.waitForTimeout(80);
  assert.equal(await state(page, "game.paused"), false, "visible page should resume when no manual pause remains");

  await state(page, "game.elapsed = 3600000; game.zombies = []; game.last = performance.now(); gameLoop(performance.now() + 16); game.paused = true; cancelAnimationFrame(game.frame)");
  assert.equal(await state(page, "game.running"), true, "a long elapsed battle must not fail because time expired");

  await state(page, "game.paused = false; game.last = performance.now(); game.zombies = [{ row: 0, x: 55, y: 0, slowTimer: 0, speed: 0, attackInterval: 1000, hp: 1, maxHp: 1, type: 'basic', seed: 0 }]; gameLoop(performance.now() + 16)");
  assert.deepEqual(await state(page, "({ running: game.running, status: document.querySelector('#gameStatus').textContent })"), {
    running: false, status: "僵尸进屋了",
  });

  await page.screenshot({ path: `${screenshotsDir}/game-smoke-desktop.png`, fullPage: true });
  assert.deepEqual(consoleErrors, [], `desktop browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

async function runAudioFallbackSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(window, "AudioContext", { configurable: true, value: undefined });
    Object.defineProperty(window, "webkitAudioContext", { configurable: true, value: undefined });
  });
  await openGame(page);
  await page.locator("#gameStart").click();
  await page.waitForTimeout(80);
  assert.deepEqual(await state(page, "({ running: game.running, audio: game.audio })"), { running: true, audio: null }, "gameplay must run without Web Audio");
  await assertCanvasPainted(page);
  assert.deepEqual(consoleErrors, [], `audio fallback browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

async function runMobileSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 1 });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const mobileAnswerLayout = await page.evaluate(() => {
    const message = document.createElement("article");
    message.className = "message assistant-message";
    message.innerHTML = '<div class="message-body"><p class="answer-callout">中文最终结果必须保持自然段落；<code>web/app.js</code> 和 <code>npm run test:web</code> 不能挤成竖排。</p></div>';
    document.querySelector("#messageList").append(message);
    const callout = message.querySelector(".answer-callout");
    const rect = callout.getBoundingClientRect();
    const result = { width: rect.width, height: rect.height };
    message.remove();
    return result;
  });
  assert.ok(mobileAnswerLayout.width >= 300, "mobile result summary should use the available reading width: " + JSON.stringify(mobileAnswerLayout));
  assert.ok(mobileAnswerLayout.height < 160, "mobile Chinese result summary must not collapse into character columns: " + JSON.stringify(mobileAnswerLayout));
  const mobileWorkbenchLayout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    composerWidth: document.querySelector("#composerShell").getBoundingClientRect().width,
    chatWidth: document.querySelector(".chat-inner").getBoundingClientRect().width,
  }));
  assert.ok(mobileWorkbenchLayout.documentWidth <= mobileWorkbenchLayout.viewport + 1, `mobile workbench should not overflow horizontally: ${JSON.stringify(mobileWorkbenchLayout)}`);
  assert.ok(mobileWorkbenchLayout.composerWidth <= mobileWorkbenchLayout.chatWidth + 1, `mobile composer should fit the chat column: ${JSON.stringify(mobileWorkbenchLayout)}`);
  await openGame(page);
  await page.locator("#gameStart").click();
  await page.waitForTimeout(80);
  const layout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    modalWidth: document.querySelector("#gameModal .game-card").getBoundingClientRect().width,
    canvasWidth: document.querySelector("#gameCanvas").getBoundingClientRect().width,
  }));
  assert.ok(layout.documentWidth <= layout.viewport + 1, `mobile page should not overflow horizontally: ${JSON.stringify(layout)}`);
  assert.ok(layout.modalWidth <= layout.viewport, `mobile modal should fit viewport: ${JSON.stringify(layout)}`);
  assert.ok(layout.canvasWidth <= layout.modalWidth, `mobile canvas should fit its panel: ${JSON.stringify(layout)}`);
  await page.screenshot({ path: `${screenshotsDir}/game-smoke-mobile.png`, fullPage: true });
  assert.deepEqual(consoleErrors, [], `mobile browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

await mkdir(screenshotsDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  await runAgentTimelineSmoke(browser);
  await runDesktopSmoke(browser);
  await runAudioFallbackSmoke(browser);
  await runMobileSmoke(browser);
  console.log("web smoke passed: desktop, audio fallback, mobile");
} finally {
  await browser.close();
}
