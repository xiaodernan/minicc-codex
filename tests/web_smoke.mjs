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
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
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
    const modelHistory = host.querySelector('[data-stage-code="model_update_history"]');
    const hiddenRoutineTraceCodes = ["tool_round_finished", "feedback_observed", "replan", "model_decision"];
    const hiddenTraceCards = hiddenRoutineTraceCodes.every((code) => !host.querySelector(`[data-stage-code="${code}"]`));
    const firstTool = host.querySelector("details.tool-event");
    const failedTool = [...host.querySelectorAll("details.tool-event.failed")].find((node) => node.textContent.includes("移动端检查失败"));
    const toolInitiallyClosed = firstTool?.open === false;
    const toolDetailsInitiallyClosed = [...(firstTool?.querySelectorAll("details.tool-result-fold") || [])].every((detail) => !detail.open);
    firstTool.open = true;
    const toolResultVisible = firstTool?.textContent.includes("入口初始化") && firstTool?.textContent.includes("abc123");
    const failedToolVisible = Boolean(failedTool);
    const hiddenTraceData = hiddenRoutineTraceCodes.every((code) => events.some((event) => event?.code === code));
    const resultSummary = JSON.stringify(events.find((event) => event?.code === "tool_round_finished")?.detail || "");
    const replanSummary = JSON.stringify(events.find((event) => event?.code === "replan")?.detail || "");
    const feedbackSummary = JSON.stringify(events.find((event) => event?.code === "feedback_observed")?.detail || "");
    const resultDetailsInitiallyClosed = !host.querySelector('[data-stage-code="tool_round_finished"]');
    const replanDetailsInitiallyClosed = !host.querySelector('[data-stage-code="replan"]');
    const feedbackDetailsInitiallyClosed = !host.querySelector('[data-stage-code="feedback_observed"]');
    const nonActionTraceInitiallyClosed = !host.querySelector('[data-stage-code="model_decision"]');
    const actionUpdateVisible = [...host.querySelectorAll('[data-stage-code="model_update"]')].every((node) => !node.matches("details"));
    const modelHistoryInitiallyClosed = modelHistory?.matches("details") && modelHistory.open === false;
    const assistantProbe = document.createElement("div");
    assistantProbe.innerHTML = assistantMessageMarkup({ answer: "语义标记探针", events });
    const threadItem = assistantProbe.querySelector("[data-agent-thread=local]");
    const latestReasoningItem = host.querySelector('[data-item-kind="reasoning"][data-latest-action="true"]');
    const reasoningHistoryItem = host.querySelector('[data-item-kind="reasoning-history"]');
    const commandGroupItem = host.querySelector('[data-item-kind="command-group"]');
    const commandItem = host.querySelector('[data-item-kind="command"]');
    const cumulativeUpdates = visibleAgentEvents([
      { kind: "trace", code: "model_update", detail: { text: "aa" } },
      { kind: "trace", code: "model_update", detail: { text: "aab" } },
      { kind: "trace", code: "model_update", detail: { text: "aabc" } },
    ]).map((event) => event.detail.text);

    const eventProbeId = `event-probe-${Date.now()}`;
    const eventProbeLoadingId = `loading-${eventProbeId}`;
    addLoadingMessage(eventProbeLoadingId, { task_id: eventProbeId, session_id: state.sessionId, workspace_path: state.workspacePath, status: "running", phase: "planning", events: [] }, { scrollToLatest: false });
    bindRunningTask({ task_id: eventProbeId, session_id: state.sessionId, workspace_path: state.workspacePath, status: "running", phase: "planning", event_cursor: 0, events: [] }, eventProbeLoadingId, state.sessionId);
    applyTaskEvent(eventProbeId, { sequence: 1, event_id: "probe-1", kind: "timeline", payload: { kind: "tool", name: "grep", status: "ok", summary: "搜索完成", event_id: "timeline-1" } });
    const duplicateEvent = applyTaskEvent(eventProbeId, { sequence: 1, event_id: "probe-1", kind: "timeline", payload: { kind: "tool", name: "grep", status: "ok", summary: "搜索完成", event_id: "timeline-1" } });
    applyTaskEvent(eventProbeId, { sequence: 2, event_id: "probe-2", kind: "stream_delta", payload: { delta: "新增内容", stream_text: "新增内容", stream_length: 4, phase: "answering" } });
    const eventProbeBinding = runningTasks.get(eventProbeId);
    const eventProbe = {
      timelineCount: eventProbeBinding?.data?.events?.length || 0,
      streamText: eventProbeBinding?.data?.stream_text || "",
      cursor: eventProbeBinding?.cursor || 0,
      duplicateIgnored: duplicateEvent === null,
    };
    stopTaskTimer(eventProbeId);
    runningTasks.delete(eventProbeId);
    document.getElementById(eventProbeLoadingId)?.remove();

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
    const liveResult = liveTool.querySelector("details.tool-result-fold");
    if (liveResult) liveResult.open = true;
    syncLiveEvents(loading, [...events, { kind: "trace", code: "verification_observed", phase: "planning", status: "ok", summary: "已收到验证证据", detail: { turn: 2 } }]);
    const preservedOpen = loading.querySelector("details.agent-round")?.open === true;
    const preservedToolOpen = loading.querySelector("details.tool-event")?.open === true;
    const preservedResultOpen = loading.querySelector("details.tool-result-fold")?.open === true;

    const homeTimeline = document.querySelector("#messageList .execution-trail");
    const expandAll = homeTimeline?.querySelector("[data-timeline-toggle=expand]");
    const collapseAll = homeTimeline?.querySelector("[data-timeline-toggle=collapse]");
    expandAll?.click();
    const allExpanded = homeTimeline ? [...homeTimeline.querySelectorAll("details")].every((detail) => detail.open) : false;
    collapseAll?.click();
    const allCollapsed = homeTimeline ? [...homeTimeline.querySelectorAll("details")].every((detail) => !detail.open) : false;

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
      hiddenTraceCards,
      hiddenTraceData,
      toolInitiallyClosed,
      toolDetailsInitiallyClosed,
      toolResultVisible,
      failedToolVisible,
      resultDetailsInitiallyClosed,
      replanDetailsInitiallyClosed,
      feedbackDetailsInitiallyClosed,
      nonActionTraceInitiallyClosed,
      actionUpdateVisible,
      cumulativeUpdates,
      resultSummary,
      replanSummary,
      feedbackSummary,
      modelSummaryVisible: summaryText.length === 1 && summaryText[0].includes("证据指向布局层") && Boolean(modelHistory),
      modelHistoryInitiallyClosed,
      itemSemantics: {
        thread: Boolean(threadItem),
        latestReasoning: Boolean(latestReasoningItem),
        reasoningHistory: Boolean(reasoningHistoryItem),
        commandGroup: Boolean(commandGroupItem),
        command: Boolean(commandItem),
      },
      eventProbe,
      preservedOpen,
      preservedToolOpen,
      preservedResultOpen,
      allExpanded,
      allCollapsed,
      scrollDeltaUpdate: Math.abs(afterUpdate - beforeUpdate),
      scrollDeltaComplete: Math.abs(afterComplete - afterUpdate),
      finalAnchor: Boolean(finalAnchor),
    };
  });
  assert.deepEqual(result.order, [
    "stage:model_update_history", "round:1", "stage:model_update", "round:2",
  ], `timeline should preserve useful stage/tool order: ${JSON.stringify(result)}`);
  assert.equal(result.hiddenTraceCards, true, "routine result/self-feedback/re-plan/decision cards must not render by default");
  assert.equal(result.roundCount, 2, "contiguous tool calls should form two collapsed rounds");
  assert.equal(result.allRoundsClosed, true, "tool rounds must start collapsed");
  assert.equal(result.failedRoundClosed, true, "failed tool rounds must not auto-expand");
  assert.equal(result.toolInitiallyClosed, true, "individual tool calls must start collapsed");
  assert.equal(result.toolDetailsInitiallyClosed, true, "large tool result blocks must start collapsed");
  assert.equal(result.toolResultVisible, true, "expanded tool calls should show output and structured data");
  assert.equal(result.failedToolVisible, true, "failed tool information must remain visible");
  assert.equal(result.resultDetailsInitiallyClosed, true, "merged result cards must not render by default");
  assert.equal(result.replanDetailsInitiallyClosed, true, "re-plan cards must not render by default");
  assert.equal(result.feedbackDetailsInitiallyClosed, true, "self-feedback cards must not render by default");
  assert.equal(result.nonActionTraceInitiallyClosed, true, "model decision cards must not render by default");
  assert.equal(result.actionUpdateVisible, true, "model action updates should remain visible");
  assert.equal(result.modelHistoryInitiallyClosed, true, "earlier model updates must start collapsed");
  assert.deepEqual(result.itemSemantics, {
    thread: true,
    latestReasoning: true,
    reasoningHistory: true,
    commandGroup: true,
    command: true,
  }, "Codex-style thread/turn/item semantics must remain inspectable");
  assert.deepEqual(result.cumulativeUpdates, ["aa", "b", "c"], "cumulative model updates should render only their new suffix");
  assert.deepEqual(result.eventProbe, { timelineCount: 1, streamText: "新增内容", cursor: 2, duplicateIgnored: true }, "incremental task events should merge once and advance the cursor");
  assert.equal(result.resultSummary, "工具结果已合并", "routine trace evidence remains available in the task event data");
  assert.equal(result.replanSummary, "已收到工具结果，正在判断下一步", "re-plan evidence remains available in the task event data");
  assert.equal(result.feedbackSummary, "自反馈已记录", "feedback evidence remains available in the task event data");
  assert.equal(result.modelSummaryVisible, true, "public model updates should be visible between tool rounds");
  assert.equal(result.preservedOpen, true, "a manually opened tool round should survive live refresh");
  assert.equal(result.preservedToolOpen, true, "a manually opened tool result should survive live refresh");
  assert.equal(result.preservedResultOpen, true, "a manually opened result fold should survive live refresh");
  assert.equal(result.allExpanded, true, "the timeline expand control should open every detail");
  assert.equal(result.allCollapsed, true, "the timeline collapse control should close every detail");
  assert.ok(result.scrollDeltaUpdate <= 1, `live updates should preserve reading position: ${JSON.stringify(result)}`);
  assert.ok(result.scrollDeltaComplete <= 1, `completion replacement should preserve reading position: ${JSON.stringify(result)}`);
  assert.equal(result.finalAnchor, true, "the final message should retain the live message anchor");

  const isolation = await page.evaluate(() => {
    const original = {
      sessionId: state.sessionId,
      workspacePath: state.workspacePath,
      activeTaskId: state.activeTaskId,
      lastTask: state.lastTask,
    };
    state.sessionId = "isolation-a";
    state.workspacePath = "workspace-a";
    state.activeTaskId = "task-a";
    const taskA = { task_id: "task-a", session_id: "isolation-a", workspace_path: "workspace-a", status: "running", phase: "tool", preview: "当前任务", stream_text: "", events: [] };
    const taskB = { task_id: "task-b", session_id: "isolation-b", workspace_path: "workspace-b", status: "running", phase: "planning", preview: "后台任务", stream_text: "", events: [] };
    bindRunningTask(taskA, "isolation-loading-a", "isolation-a");
    bindRunningTask(taskB, "isolation-loading-b", "isolation-b");
    updateTaskDock(taskA);
    const before = {
      title: document.querySelector("#taskDockTitle")?.textContent,
      phase: document.querySelector("#taskDockPhase")?.textContent,
      pulse: document.querySelector("#pulseStatus")?.textContent,
      active: state.activeTaskId,
    };
    updateBoundTask("task-b", { ...taskB, status: "failed", phase: "failed", preview: "后台任务失败" });
    const after = {
      title: document.querySelector("#taskDockTitle")?.textContent,
      phase: document.querySelector("#taskDockPhase")?.textContent,
      pulse: document.querySelector("#pulseStatus")?.textContent,
      active: state.activeTaskId,
      lastTask: state.lastTask?.task_id,
    };
    const tasks = [taskA, taskB];
    renderTaskHistory(tasks);
    const firstItem = document.querySelector("#threadList .thread-item");
    renderTaskHistory(tasks);
    const stableHistoryDom = firstItem === document.querySelector("#threadList .thread-item");
    ["task-a", "task-b"].forEach((taskId) => stopTaskTimer(taskId));
    runningTasks.clear();
    taskBySession.clear();
    document.querySelector("#isolation-loading-a")?.remove();
    document.querySelector("#isolation-loading-b")?.remove();
    state.sessionId = original.sessionId;
    state.workspacePath = original.workspacePath;
    state.activeTaskId = original.activeTaskId;
    state.lastTask = original.lastTask;
    return { before, after, stableHistoryDom };
  });
  assert.deepEqual(isolation.after, { ...isolation.before, lastTask: "task-a" }, `background task must not steal the focused task UI: ${JSON.stringify(isolation)}`);
  assert.equal(isolation.stableHistoryDom, true, "unchanged task history must not replace sidebar DOM");
  assert.deepEqual(consoleErrors, [], `timeline browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

async function runDesktopSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  const initialTheme = await state(page, "document.documentElement.dataset.theme");
  await page.locator("#themeButton").click();
  const toggledTheme = await state(page, "document.documentElement.dataset.theme");
  assert.notEqual(toggledTheme, initialTheme, "theme control should switch theme");
  assert.equal(await state(page, "localStorage.getItem('minicc-theme')"), toggledTheme, "theme preference should persist");
  if (toggledTheme !== "light") await page.locator("#themeButton").click();
  assert.equal(await state(page, "document.documentElement.dataset.theme"), "light", "theme control should enable light mode");
  assert.match(await page.locator("#themeButton").getAttribute("aria-label"), /暗色|dark/i);
  await page.reload({ waitUntil: "domcontentloaded" });
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
    difficulty: "nightmare", sun: 110, target: 17,
  });
  const gameMechanics = await state(page, `(() => {
    const originalRandom = Math.random;
    const stopTick = () => { game.running = false; cancelAnimationFrame(game.frame); };
    const tick = (zombies, plants = [], shots = []) => {
      game.running = true;
      game.paused = false;
      game.plants = plants;
      game.zombies = zombies;
      game.shots = shots;
      game.suns = [];
      game.waveSpawned = game.waveTarget;
      game.spawnTimer = 0;
      game.skyTimer = 0;
      game.dangerTimer = 0;
      game.last = 1000;
      gameLoop(1016);
      stopTick();
    };

    game.suns = [];
    produceSun({ row: 0, col: 0 });
    const sunflower = game.suns.length === 1;

    game.shots = [];
    firePlantShots({ type: "icepeashooter", row: 0, col: 0 }, plantProfiles.icepeashooter);
    const iceShot = game.shots[0];
    game.shots = [];
    firePlantShots({ type: "firepeashooter", row: 0, col: 0 }, plantProfiles.firepeashooter);
    const fireShot = game.shots[0];
    game.shots = [];
    firePlantShots({ type: "threepeater", row: 1, col: 0 }, plantProfiles.threepeater);
    const threepeaterRows = [...new Set(game.shots.map((shot) => shot.row))].sort();

    const cherry = { type: "cherrybomb", row: 0, col: 2 };
    const cherryTarget = { type: "walker", row: 0, x: cellPosition(0, 2).x + 20 };
    game.plants = [cherry];
    game.zombies = [cherryTarget];
    explodeCherryBomb(cherry);
    const cherryBomb = game.plants.length === 0 && game.zombies.length === 0;

    const runner = { type: "runner", row: 0, x: 600, speed: .05, hp: 5, maxHp: 5, slowTimer: 0, dashTimer: 0, chargeTimer: 0 };
    tick([runner]);
    const dash = { triggered: runner.dashTimer > 0, movedWithBoost: runner.x > 625 };

    const football = { type: "football", row: 0, x: 600, speed: .05, hp: 5, maxHp: 5, slowTimer: 0, dashTimer: 0, chargeTimer: 0 };
    tick([football]);
    const charge = { triggered: football.chargeTimer > 0, movedWithBoost: football.x < 599 };

    const giantPlant = { type: "wallnut", row: 0, col: 3, hp: 12, disabledTimer: 0 };
    const giant = { type: "gargantuar", row: 0, x: cellPosition(0, 3).x, speed: 0, hp: 48, maxHp: 48, slowTimer: 0, smashTimer: 0 };
    tick([giant], [giantPlant]);
    const giantSmash = { triggered: giant.smashTimer > 0, damagedPlant: giantPlant.hp === 5 };

    const biteWalker = () => ({ type: "walker", row: 0, x: cellPosition(0, 3).x, speed: 0, hp: 5, maxHp: 5, slowTimer: 0, attackInterval: 1000 });
    const pumpkin = { type: "pumpkin", row: 0, col: 3, hp: 32, disabledTimer: 0 };
    tick([biteWalker()], [pumpkin]);
    const pumpkinDamage = 32 - pumpkin.hp;
    const wallnut = { type: "wallnut", row: 0, col: 3, hp: 24, disabledTimer: 0 };
    tick([biteWalker()], [wallnut]);
    const wallnutDamage = 24 - wallnut.hp;
    const pumpkinDefense = { damaged: pumpkinDamage > 0, halfDamage: Math.abs(pumpkinDamage * 2 - wallnutDamage) < 0.0001 };

    game.running = true;
    game.paused = false;
    game.sun = plantCost.pumpkin;
    game.selected = "pumpkin";
    game.seedCooldowns = {};
    game.shovel = false;
    const coverBase = { type: "sunflower", row: 0, col: 3, hp: 6, maxHp: 6, seed: 1, age: 0, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0, armed: true };
    game.plants = [coverBase];
    const coverCanvas = gameRender.canvas;
    const coverRect = coverCanvas.getBoundingClientRect();
    const coverPosition = cellPosition(0, 3);
    const coverEvent = { clientX: coverRect.left + coverPosition.x * coverRect.width / GAME_LOGICAL_WIDTH, clientY: coverRect.top + coverPosition.y * coverRect.height / GAME_LOGICAL_HEIGHT };
    const plantedPumpkin = plantAt(coverEvent);
    const shell = game.plants[0];
    const pumpkinCover = { planted: plantedPumpkin, oneSlot: game.plants.length === 1, underPlant: shell?.underPlant === coverBase, baseType: shell?.underPlant?.type };
    const baseBeforeShellHit = coverBase.hp;
    damagePlant(shell, 2);
    const pumpkinShell = { shellDamage: shell.hp === plantHealth.pumpkin - 1, baseUntouched: coverBase.hp === baseBeforeShellHit };
    damagePlant(shell, 100);
    const pumpkinRestored = game.plants.length === 1 && game.plants[0] === coverBase && !game.plants[0].underPlant;

    const spikeweed = { type: "spikeweed", row: 0, col: 3, hp: 10, maxHp: 10, seed: 1, age: 0, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0, armed: true };
    const spikeZombie = { type: "walker", row: 0, x: cellPosition(0, 3).x, speed: .05, hp: 5, maxHp: 5, slowTimer: 0, burrowTimer: 0, attackInterval: 1000 };
    const spikeBeforeX = spikeZombie.x;
    tick([spikeZombie], [spikeweed]);
    const spikeweedBehavior = { movedThrough: spikeZombie.x < spikeBeforeX, damagedZombie: spikeZombie.hp < 5, plantUntouched: spikeweed.hp === 10 };

    const miner = { type: "miner", row: 0, x: cellPosition(0, 3).x, speed: 0, hp: 9, maxHp: 9, slowTimer: 0, attackInterval: 850, burrowTimer: 1000 };
    const minerShot = { x: miner.x - 10, y: miner.y, row: 0, damage: 1, hitsLeft: 1, hitTargets: [], hit: false };
    tick([miner], [], [minerShot]);
    const minerBurrow = { hpUnchanged: miner.hp === 9, shotStillFlying: game.shots.length === 1 };

    const impPlant = { type: "wallnut", row: 0, col: 3, hp: 24, disabledTimer: 0 };
    const imp = { type: "imp", row: 0, x: cellPosition(0, 3).x, speed: 0, hp: 3, maxHp: 3, slowTimer: 0, attackInterval: 1250, dashTimer: 1000, leapTimer: 0 };
    tick([imp], [impPlant]);
    const impLeap = { triggered: imp.leapTimer > 0, movedPastBlocker: imp.x < cellPosition(0, 3).x - 30, plantIntact: game.plants.includes(impPlant) };

    const bucket = { type: "bucket", row: 0, x: cellPosition(0, 3).x, speed: 0, hp: 21, maxHp: 21, armor: 8, slowTimer: 0, attackInterval: 620 };
    const bucketShot = { x: bucket.x - 10, y: bucket.y, row: 0, damage: 1, hitsLeft: 1, hitTargets: [], hit: false };
    tick([bucket], [], [bucketShot]);
    const bucketArmor = { armorConsumed: bucket.armor === 7, reducedHp: Math.abs(bucket.hp - 20.65) < 0.0001 };

    const expectedZombieTypes = ["walker", "backup", "roadblock", "conehead", "imp", "scout", "storm", "runner", "polevault", "bucket", "football", "miner", "flag", "dancer", "newspaper", "gargantuar", "witch", "dragon", "shield"];
    const zombieProfilesComplete = expectedZombieTypes.every((type) => zombieProfiles[type] && zombieProfiles[type].hp && zombieProfiles[type].speed && zombieProfiles[type].growth && zombieProfiles[type].attackInterval && zombieProfiles[type].score);
    const waveTargets = [1, 2, 6, 10].map((wave) => WAVE_TARGET(wave, "hard"));
    const nightmareTargets = [1, 2, 6, 10].map((wave) => WAVE_TARGET(wave, "nightmare"));

    game.difficulty = "nightmare";
    game.wave = 6;
    game.waveTarget = WAVE_TARGET(6, "nightmare");
    game.waveSpawned = 4;
    game.zombies = [];
    Math.random = () => .99;
    const forcedType = zombieTypeForWave();
    spawnZombie();
    Math.random = originalRandom;
    const nightmare = { target: game.waveTarget, forcedType, spawnedType: game.zombies[0]?.type, elite: game.zombies[0]?.elite === true };
    game.plants = [];
    game.zombies = [];
    game.shots = [];
    game.suns = [];
    return {
      catalogComplete: Object.keys(plantCost).every((type) => plantHealth[type] && plantColor[type] && plantCooldown[type]),
      sunflower,
      iceShot: Boolean(iceShot?.slow),
      fireShot: Boolean(fireShot?.fire && fireShot?.burn && fireShot?.burnDamage),
      threepeaterRows,
      cherryBomb,
      dash,
      charge,
      giantSmash,
      pumpkinDefense,
      pumpkinCover,
      pumpkinShell,
      pumpkinRestored,
      spikeweedBehavior,
      minerBurrow,
      impLeap,
      bucketArmor,
      zombieProfilesComplete,
      waveTargets,
      nightmareTargets,
      nightmare,
    };
  })()`);
  assert.equal(gameMechanics.catalogComplete, true, "every plant must have cost, health, color, and cooldown data");
  assert.deepEqual(gameMechanics.threepeaterRows, [0, 1, 2], "threepeater must cover its row and adjacent rows");
  assert.deepEqual(gameMechanics, {
    catalogComplete: true,
    sunflower: true,
    iceShot: true,
    fireShot: true,
    threepeaterRows: [0, 1, 2],
    cherryBomb: true,
    dash: { triggered: true, movedWithBoost: true },
    charge: { triggered: true, movedWithBoost: true },
    giantSmash: { triggered: true, damagedPlant: true },
    pumpkinDefense: { damaged: true, halfDamage: true },
    pumpkinCover: { planted: true, oneSlot: true, underPlant: true, baseType: "sunflower" },
    pumpkinShell: { shellDamage: true, baseUntouched: true },
    pumpkinRestored: true,
    spikeweedBehavior: { movedThrough: true, damagedZombie: true, plantUntouched: true },
    minerBurrow: { hpUnchanged: true, shotStillFlying: true },
    impLeap: { triggered: true, movedPastBlocker: true, plantIntact: true },
    bucketArmor: { armorConsumed: true, reducedHp: true },
    zombieProfilesComplete: true,
    waveTargets: [9, 11, 19, 27],
    nightmareTargets: [17, 20, 34, 48],
    nightmare: { target: 34, forcedType: "dragon", spawnedType: "dragon", elite: true },
  }, `game mechanics smoke: ${JSON.stringify(gameMechanics)}`);

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

  await state(page, "game.paused = false; game.mowers.forEach((mower) => { mower.used = true; mower.active = false; }); game.last = performance.now(); game.zombies = [{ row: 0, x: 55, y: 0, slowTimer: 0, speed: 0, attackInterval: 1000, hp: 1, maxHp: 1, type: 'basic', seed: 0 }]; gameLoop(performance.now() + 16)");
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
