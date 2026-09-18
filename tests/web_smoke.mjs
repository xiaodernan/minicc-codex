import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const screenshotsDir = "output";

function state(page, expression) {
  return page.evaluate((source) => window.eval(source), expression);
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

    const trailProbe = document.createElement("div");
    trailProbe.innerHTML = assistantMessageMarkup({ answer: "expand-probe", events });
    document.querySelector("#messageList").append(trailProbe.firstElementChild);
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
  assert.equal(result.hiddenTraceData, true, "hidden routine trace data must remain available for audit");
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
  assert.match(result.resultSummary, /命中 3 处|新信息|入口和路由/, "routine result evidence remains available in the task event data");
  assert.match(result.replanSummary, /上一轮工具结果已合并|检查样式|约束/, "re-plan evidence remains available in the task event data");
  assert.match(result.feedbackSummary, /产生了新信息|继续检查路由/, "feedback evidence remains available in the task event data");
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

async function assertEmptyChrome(page) {
  assert.equal(await page.locator(".codex-menu-links button", { hasText: "文件" }).count(), 0, "File menu must be removed");
  assert.equal(await page.locator(".codex-menu-links button", { hasText: "编辑" }).count(), 0, "Edit menu must be removed");
  assert.equal(await page.locator(".codex-menu-links button", { hasText: "视图" }).count(), 0, "View menu must be removed");
  assert.equal(await page.locator(".codex-nav-arrow").count(), 0, "back/forward nav arrows must be removed");
  assert.equal(await page.locator('[aria-label="通知"]').count(), 0, "notification bell must be removed");
  assert.equal(await page.locator("#helpMenuButton").count(), 1, "Help menu should remain");
  const emptyText = await page.locator("#messageList").innerText();
  assert.doesNotMatch(emptyText, /9 passed|initial-pytest/, "empty session must not ship a fake pytest timeline");
  assert.match(emptyText, /发送一条任务开始|Send a task to begin/);
  assert.equal(await page.locator(".brand-name").innerText(), "minicc");
  assert.equal(await page.locator("#turnMetric").innerText(), "0");
  assert.equal(await page.locator("#toolMetric").innerText(), "0");
}

async function runProductPathSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.locator("#newTaskButton").click();
  await assertEmptyChrome(page);
  await page.locator("#promptInput").fill("Inspect the current project and tell me the most valuable next step.");
  await page.locator("#sendButton").click();
  await page.locator("#messageList [data-live-task], #messageList .loading").first().waitFor({ timeout: 20000 });
  assert.deepEqual(consoleErrors, [], `product path browser errors: ${consoleErrors.join(" | ")}`);
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
  const desktopLayout = await page.evaluate(() => ({ viewport: window.innerWidth, width: document.documentElement.scrollWidth, chatWidth: document.querySelector(".chat-inner").getBoundingClientRect().width }));
  assert.ok(desktopLayout.width <= desktopLayout.viewport + 1, `desktop page should not overflow horizontally: ${JSON.stringify(desktopLayout)}`);
  await page.screenshot({ path: `${screenshotsDir}/web-smoke-desktop.png`, fullPage: true });
  assert.deepEqual(consoleErrors, [], `desktop browser errors: ${consoleErrors.join(" | ")}`);
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
  await page.screenshot({ path: `${screenshotsDir}/web-smoke-mobile.png`, fullPage: true });
  assert.deepEqual(consoleErrors, [], `mobile browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

await mkdir(screenshotsDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  await runAgentTimelineSmoke(browser);
  await runProductPathSmoke(browser);
  await runDesktopSmoke(browser);
  await runMobileSmoke(browser);
  console.log("web smoke passed: timeline, product path, desktop, mobile");
} finally {
  await browser.close();
}
