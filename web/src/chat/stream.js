import { requestJson } from "../core/transport.js";
import { activateDialog, deactivateDialog } from "../core/dialog.js";
import { openArcade } from "../core/arcade.js";
import { captureViewScope, isViewScopeCurrent } from "../core/scope.js";
// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { attachmentMarkup, cacheTaskDetail, escapeHtml, executionTrailMarkup, formatText, loadTaskHistory, persistSessionView, renderSession, sessionViewKey } from "./markdown.js";
import { applyTaskEvent, completeTask, finishLiveTask, isTerminalTask, pollTask, updateBoundTask, updateLiveTask } from "../core/api.js";
import { t } from "../core/i18n.js";
import { $, $$, authHeaders, authQuery, renderedHistoryKeys, runtime, runningTasks, sessionMarkup, state, taskBySession, taskDetailLoads, taskDetailsById, taskEventSources, taskHistoryBySession, taskHistoryListBySession, taskWatchers } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { addAssistantMessage, addLoadingMessage, addUserMessage, bindRunningTask, closeMentionPopover, compactNumber, effectiveTaskPermissions, eventSequence, eventTimelineMarkup, formatDuration, isCurrentTaskScope, isSessionBusy, phaseLabel, refreshFileTree, refreshFileTreeSoon, runtimeMetricsMarkup, sessionTaskBindings, setBusy, setConnection, setSession, setTaskTransportStatus, showAuthModal, showToast, taskDuration, taskMetrics, taskSessionKey, updateReasoningControl, updateTaskDock } from "../panels/index.js";

export function streamTask(taskId) {
  const binding = runningTasks.get(taskId);
  const loadingId = binding?.loadingId || "";
  if (!window.EventSource) return pollTask(taskId);
  return new Promise((resolve, reject) => {
    let source = null;
    let settled = false;
    let fallbackStarted = false;
    let receivedSnapshot = false;
    let reconnectAttempts = 0;
    let reconnectTimer = 0;
    let snapshotTimer = 0;
    const sourceKey = loadingId || taskId;
    const maxReconnectAttempts = 6;
    setTaskTransportStatus(taskId, "connecting");

    const closeSource = () => {
      if (source) source.close();
      source = null;
      taskEventSources.delete(sourceKey);
      window.clearTimeout(reconnectTimer);
      window.clearTimeout(snapshotTimer);
    };

    const fallback = () => {
      if (settled || fallbackStarted) return;
      fallbackStarted = true;
      setTaskTransportStatus(taskId, "polling");
      closeSource();
      pollTask(taskId).then(resolve, reject);
    };

    const finish = async (data) => {
      if (settled || !isTerminalTask(data)) return;
      settled = true;
      closeSource();
      try {
        // The terminal event contains enough state to render immediately, but
        // one final snapshot also carries the complete answer/result payload.
        const latest = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000);
        // A lagging snapshot must not regress the terminal event to running.
        const terminal = isTerminalTask(latest) ? latest : data;
        updateBoundTask(taskId, terminal);
        resolve(await completeTask(loadingId, terminal));
      } catch {
        resolve(await completeTask(loadingId, data));
      }
    };

    const handleSnapshot = (event) => {
      try {
        const data = JSON.parse(event.data);
        receivedSnapshot = true;
        reconnectAttempts = 0;
        const latest = updateBoundTask(taskId, data);
        if (isTerminalTask(latest || data)) finish(latest || data);
      } catch {
        // A malformed frame is ignored; the connection error/retry path still
        // has a chance to recover the task from its durable snapshot.
      }
    };

    const handleTaskEvent = (event) => {
      try {
        const data = applyTaskEvent(taskId, JSON.parse(event.data));
        if (data) {
          reconnectAttempts = 0;
          if (isTerminalTask(data)) finish(data);
        }
      } catch {
        // The next replay or a polling fallback can still restore the state.
      }
    };

    const checkLatestAfterError = () => {
      if (settled || fallbackStarted) return;
      closeSource();
      requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 8000)
        .then((latest) => {
          if (settled) return;
          const current = updateBoundTask(taskId, latest);
          if (isTerminalTask(current || latest)) {
            finish(current || latest);
            return;
          }
          scheduleReconnect();
        })
        .catch(() => scheduleReconnect());
    };

    const scheduleReconnect = () => {
      if (settled || fallbackStarted) return;
      closeSource();
      setTaskTransportStatus(taskId, "reconnecting");
      reconnectAttempts += 1;
      if (reconnectAttempts > maxReconnectAttempts) {
        fallback();
        return;
      }
      const delay = Math.min(6000, 500 * (2 ** (reconnectAttempts - 1)));
      reconnectTimer = window.setTimeout(connect, delay);
    };

    function connect() {
      if (settled || fallbackStarted) return;
      const cursor = eventSequence(binding?.cursor || binding?.data?.event_cursor);
      source = new EventSource(authQuery(`/api/tasks/${encodeURIComponent(taskId)}/events?after=${cursor}`));
      taskEventSources.set(sourceKey, source);
      source.onmessage = handleSnapshot;
      source.addEventListener("task_event", handleTaskEvent);
      source.addEventListener("resync", handleSnapshot);
      source.onerror = checkLatestAfterError;
      window.clearTimeout(snapshotTimer);
      if (!receivedSnapshot && cursor === 0) {
        snapshotTimer = window.setTimeout(() => {
          if (!receivedSnapshot) scheduleReconnect();
        }, 3500);
      }
    }

    connect();
  });
}

export function watchTask(taskId) {
  const existing = taskWatchers.get(taskId);
  if (existing) return existing;
  const watcher = streamTask(taskId);
  taskWatchers.set(taskId, watcher);
  watcher.then(
    () => { if (taskWatchers.get(taskId) === watcher) taskWatchers.delete(taskId); },
    () => { if (taskWatchers.get(taskId) === watcher) taskWatchers.delete(taskId); },
  );
  return watcher;
}

export async function cancelActiveTask() {
  const taskIds = sessionTaskBindings(state.sessionId).map((binding) => binding.taskId);
  const fallback = taskBySession.get(taskSessionKey(state.sessionId)) || null;
  if (!taskIds.length && fallback) taskIds.push(fallback);
  if (!taskIds.length) return;
  try {
    await Promise.all(taskIds.map((taskId) => requestJson(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })));
    showToast(state.locale === "zh" ? "已请求取消任务" : "Cancellation requested");
  } catch (error) {
    showToast(error.message);
  }
}

export function renderAttachmentTray() {
  const tray = $("#attachmentTray");
  if (!tray) return;
  tray.hidden = state.attachments.length === 0;
  tray.innerHTML = attachmentMarkup(state.attachments, "attachment-tray-items");
  refreshIcons();
}

export function readImageFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`无法读取图片：${file.name}`));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
}

export async function addImageFiles(fileList) {
  const files = [...(fileList || [])].filter((file) => String(file.type || "").startsWith("image/"));
  if (!files.length) return;
  const remaining = Math.max(0, 4 - state.attachments.length);
  if (!remaining) {
    showToast(state.locale === "zh" ? "最多添加 4 张图片" : "Up to 4 images per task");
    return;
  }
  for (const file of files.slice(0, remaining)) {
    if (file.size > 6 * 1024 * 1024) {
      showToast(state.locale === "zh" ? `${file.name} 超过 6MB` : `${file.name} is larger than 6MB`);
      continue;
    }
    try {
      const dataUrl = await readImageFile(file);
      state.attachments.push({
        id: `image-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        name: file.name,
        mime_type: file.type || "image/png",
        size_bytes: file.size,
        data_url: dataUrl,
      });
    } catch (error) {
      showToast(error.message);
    }
  }
  renderAttachmentTray();
}

export function clearAttachments() {
  state.attachments = [];
  const input = $("#imageInput");
  if (input) input.value = "";
  renderAttachmentTray();
}

export async function sendMessage(event) {
  event?.preventDefault();
  const input = $("#promptInput");
  const queuedAttachments = state.attachments.map((item) => ({ ...item }));
  const message = input.value.trim() || (queuedAttachments.length ? (state.locale === "zh" ? "请分析我上传的图片。" : "Analyze the images I uploaded.") : "");
  const sessionId = state.sessionId;
  const workspacePath = state.workspacePath;
  if ((!message && !queuedAttachments.length) || state.submitting) return;
  const submission = {};
  runtime.submission = submission;
  const releaseSubmission = () => {
    if (runtime.submission !== submission) return;
    runtime.submission = null;
    state.submitting = false;
    setBusy(isSessionBusy(state.sessionId));
  };
  const isCurrentScope = () => state.sessionId === sessionId && state.workspacePath === workspacePath;
  state.submitting = true;
  setBusy(true);
  input.value = "";
  closeMentionPopover();
  clearAttachments();
  addUserMessage(message, queuedAttachments);
  const loadingId = addLoadingMessage();
  const permissions = effectiveTaskPermissions();
  try {
    const task = await requestJson("/api/tasks", {
     method: "POST",
     headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, attachments: queuedAttachments.map(({ name, mime_type, data_url }) => ({ name, mime_type, data_url })), session_id: sessionId, permission_mode: permissions.mode, allow_changes: permissions.allowChanges, allow_network: permissions.allowNetwork, reasoning_effort: state.reasoningEffort, workspace_path: workspacePath }),
    });
    bindRunningTask(task, loadingId, sessionId);
    releaseSubmission();
    if (isCurrentScope()) state.activeTaskId = task.task_id;
    updateTaskDock(task);
    await loadTaskHistory();
    await watchTask(task.task_id);
  } catch (error) {
    finishLiveTask(loadingId);
    document.getElementById(loadingId)?.remove();
    if (isCurrentScope()) addAssistantMessage({ error: error.message });
    showToast(error.message);
    setConnection(false, "API error");
  } finally {
    releaseSubmission();
    if (isCurrentScope()) {
      if (!sessionTaskBindings(sessionId, workspacePath).length) state.activeTaskId = null;
      setBusy(isSessionBusy(state.sessionId));
    }
  }
}

export function resetTask() {
  const next = `task-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  state.activeTaskId = null;
  state.lastTask = null;
  taskHistoryBySession.delete(next);
  taskHistoryListBySession.delete(next);
  renderedHistoryKeys.delete(next);
  setSession(next);
  const dock = $("#taskDock");
  if (dock) {
    dock.hidden = true;
    dock.removeAttribute("data-status");
  }
  showToast(state.locale === "zh" ? "已创建新任务" : "New task created");
}

export function runDemoFlow() {
  if (isSessionBusy(state.sessionId)) return;
  const steps = state.locale === "zh"
    ? [
        { phase: "planning", stream: "收到任务：检查一个小功能并给出结果。", event: { kind: "trace", code: "model_update", phase: "planning", summary: "模型给出了本轮可公开的行动说明", detail: { turn: 1, text: "我会先读取 README.md，再定位测试入口并运行针对性验证，最后汇总可确认的结果。" } } },
        { phase: "tool", stream: "read_file · 读取 README.md", event: { name: "read_file", status: "ok", summary: "读取 README.md" } },
        { phase: "tool", stream: "grep · 搜索测试入口", event: { name: "grep", status: "ok", summary: "搜索测试入口" } },
        { phase: "planning", stream: "根据已读取内容调整验证范围", event: { kind: "trace", code: "replan", phase: "planning", summary: "重新规划", detail: { turn: 1, text: "已定位测试入口，下一步只运行与目标功能相关的测试，避免无关耗时。" } } },
        { phase: "tool", stream: "bash · 运行 pytest -q", event: { name: "bash", status: "ok", summary: "运行 pytest -q" } },
        { phase: "answering", stream: "整理验证结果与剩余风险", event: { kind: "trace", code: "tool_round_finished", phase: "answering", summary: "结果汇总：已完成 3 次工具调用，验证通过", detail: { turn: 1, tool_count: 3, tools: ["read_file", "grep", "bash"] } } },
        { phase: "answering", stream: "完成评估：任务目标已满足", event: { kind: "trace", code: "completion_complete", phase: "answering", summary: "完成评估通过", detail: { confidence: "高", evidence: "文档已读取，测试已通过" } } },
      ]
    : [
        { phase: "planning", stream: "Task received: inspect a small feature and report back.", event: { kind: "trace", code: "model_update", phase: "planning", summary: "The model provided a public action update", detail: { turn: 1, text: "I will read README.md, locate the test entry points, run focused validation, then summarize confirmed results." } } },
        { phase: "tool", stream: "read_file · reading README.md", event: { name: "read_file", status: "ok", summary: "Reading README.md" } },
        { phase: "tool", stream: "grep · locating test entry points", event: { name: "grep", status: "ok", summary: "Locating test entry points" } },
        { phase: "planning", stream: "Refining the verification scope", event: { kind: "trace", code: "replan", phase: "planning", summary: "Re-plan", detail: { turn: 1, text: "The relevant tests are located, so I will run focused validation and avoid unrelated work." } } },
        { phase: "tool", stream: "bash · running pytest -q", event: { name: "bash", status: "ok", summary: "Running pytest -q" } },
        { phase: "answering", stream: "Summarizing verification and remaining risks", event: { kind: "trace", code: "tool_round_finished", phase: "answering", summary: "Results merged: 3 tool calls completed and validation passed", detail: { turn: 1, tool_count: 3, tools: ["read_file", "grep", "bash"] } } },
        { phase: "answering", stream: "Completion review: objective is met", event: { kind: "trace", code: "completion_complete", phase: "answering", summary: "Completion accepted", detail: { confidence: "high", evidence: "Documentation read and tests passed" } } },
      ];
  const loadingId = addLoadingMessage();
  setBusy(true);
  let index = 0;
  const tick = () => {
    const item = steps[index];
    if (!item) {
      finishLiveTask(loadingId);
      const loading = document.getElementById(loadingId);
      loading?.remove();
      addAssistantMessage({
        answer: state.locale === "zh" ? "演示完成：规划 → 工具调用 → 测试验证 → 总结。真实任务会在这里连接本地 API 和模型。" : "Demo complete: plan → tools → tests → summary. Real tasks connect to the local API and model here.",
        events: steps.map((step) => step.event),
        turns: 1, tool_calls_total: 3, tokens_used: { total_tokens: 420 }, context: { tokens: 420, limit_tokens: state.contextWindowTokens },
      });
      setBusy(false);
      return;
    }
    updateLiveTask(loadingId, { status: "running", phase: item.phase, stream_text: item.stream, events: steps.slice(0, index + 1).map((step) => step.event) });
    index += 1;
    window.setTimeout(tick, 850);
  };
  tick();
}

export async function loadWorkspace() {
  const version = ++runtime.workspaceVersion;
  try {
    const info = await requestJson("/api/workspace", {}, 10000);
    if (version !== runtime.workspaceVersion) return false;
    const previousPath = state.workspacePath;
    if (previousPath && info.path && previousPath !== info.path) persistSessionView();
    state.workspaceInfo = info;
   state.workspacePath = info.path || state.workspacePath;
   state.contextWindowTokens = Number(info.context_window_tokens || state.contextWindowTokens || 300000);
    if (!localStorage.getItem("minicc-reasoning") && ["low", "mid", "high", "xhigh", "max", "ultra"].includes(info.reasoning_effort)) state.reasoningEffort = info.reasoning_effort;
    updateReasoningControl();
    const name = info.name || "workspace";
    $("#workspaceName").textContent = name;
    $("#topWorkspace").textContent = name;
    $("#composerWorkspace").textContent = name;
    $(".inspector-header h2").textContent = name;
    setConnection(true);
    if (previousPath && previousPath !== state.workspacePath) {
      sessionMarkup.clear();
      taskDetailsById.clear();
      taskDetailLoads.clear();
      taskHistoryBySession.clear();
      taskHistoryListBySession.clear();
      renderedHistoryKeys.clear();
      setSession(state.sessionId);
    }
    // Only metadata belongs to startup. Panels settle independently.
    const historyReady = loadTaskHistory();
    void loadChanges();
    // The file tree is workspace-scoped: reload it on the initial load, on
    // workspace switches, and whenever the workspace view is refreshed.
    refreshFileTree();
    void (async () => { try {
      const workspacePath = state.workspacePath;
      const loadedTasks = await historyReady;
      if (version !== runtime.workspaceVersion || workspacePath !== state.workspacePath) return;
      const tasks = Array.isArray(loadedTasks) ? loadedTasks : [];
      const activeTasks = tasks.filter((item) => ["queued", "running"].includes(item.status));
      for (const task of [...activeTasks].reverse()) {
        if (runningTasks.has(task.task_id)) continue;
        const sessionId = String(task.session_id || task.task_id);
        const loadingId = `loading-${task.task_id}`;
        if (sessionId === state.sessionId) addLoadingMessage(loadingId, task, { scrollToLatest: false });
        bindRunningTask(task, loadingId, sessionId);
        watchTask(task.task_id).catch((error) => showToast(error.message));
      }
      const active = activeTasks.find((item) => isCurrentTaskScope(item));
      if (active) updateTaskDock(active);
      else {
        $("#taskDock").hidden = true;
        state.lastTask = null;
        state.activeTaskId = null;
      }
    } catch {
      // The workspace remains usable when the durable task index is unavailable.
    } })();
    return true;
  } catch {
    if (version !== runtime.workspaceVersion) return false;
    setConnection(false, "Offline");
    return false;
  }
}

export function fileType(path) {
  const extension = String(path).split(".").pop()?.toLowerCase();
  if (extension === "py") return "py";
  if (["css", "scss"].includes(extension)) return "css";
  if (["md", "txt"].includes(extension)) return "md";
  if (["js", "ts", "tsx", "jsx"].includes(extension)) return "js";
  return "file";
}

export function changeStatusLabel(status) {
  return t(`changes.${status}`) || status;
}

export function changeFileRow(item) {
  const path = String(item.path || "");
  const status = String(item.status || "clean");
  const additions = Number(item.additions || 0);
  const deletions = Number(item.deletions || 0);
  return `<button class="file-row file-row-${escapeHtml(status)}" data-file="${escapeHtml(path)}" data-open-diff="${escapeHtml(path)}"><span class="file-type ${fileType(path)}">${escapeHtml(fileType(path).toUpperCase())}</span><span><strong>${escapeHtml(path)}</strong><small>${escapeHtml(changeStatusLabel(status))} · <span class="diff-add">+${additions}</span> <span class="diff-del">-${deletions}</span></small></span><i data-lucide="chevron-right"></i></button>`;
}

export function renderChanges(data) {
  const files = Array.isArray(data?.files) ? data.files : [];
  const changed = new Map(files.map((item) => [String(item.path), item]));
  const paths = files.map((item) => String(item.path));
  const fileList = $("#fileList");
  if (fileList) {
    fileList.innerHTML = paths.map((path) => changeFileRow(changed.get(path) || { path, status: "clean" })).join("");
  }
  const summary = $("#changeSummary");
  if (summary) summary.innerHTML = `<span class="diff-add">+ ${compactNumber(data?.additions || 0)}</span><span class="diff-del">- ${compactNumber(data?.deletions || 0)}</span>`;
  const tabCount = $("#changeTabCount");
  if (tabCount) tabCount.textContent = String(files.length);
  const changeList = $("#changeList");
  if (changeList) {
    changeList.innerHTML = files.length
      ? files.map((item) => `<button class="change-item change-item-button" data-open-diff="${escapeHtml(item.path)}"><span class="change-bar ${item.status === "added" ? "added" : item.status === "deleted" ? "deleted" : "changed"}"></span><span><strong>${escapeHtml(item.path)}</strong><small>${escapeHtml(changeStatusLabel(item.status))} · <span class="diff-add">+${Number(item.additions || 0)}</span> <span class="diff-del">-${Number(item.deletions || 0)}</span></small></span><span class="change-time">${escapeHtml(t("changes.now"))}</span></button>`).join("")
      : `<div class="change-item"><span class="change-bar muted"></span><span><strong>${escapeHtml(t("changes.clean"))}</strong><small>${escapeHtml(t("changes.cleanHint"))}</small></span><span class="change-time">--</span></div>`;
  }
  refreshIcons();
}

export async function loadChanges() {
  if (!state.workspacePath) return;
  const request = runtime.changesRequest = (runtime.changesRequest || 0) + 1;
  const path = state.workspacePath;
  const version = runtime.workspaceVersion;
  $("#changesSection")?.setAttribute("aria-busy", "true");
  try {
    const data = await requestJson("/api/changes", {}, 12000);
    if (path !== state.workspacePath || version !== runtime.workspaceVersion || request !== runtime.changesRequest) return;
    state.changes = data;
    renderChanges(data);
  } catch {
    if (path !== state.workspacePath || version !== runtime.workspaceVersion || request !== runtime.changesRequest) return;
    $("#changeList").innerHTML = `<div class="file-tree-status">${escapeHtml(state.locale === "zh" ? "暂时无法读取变更。可在更多选项中刷新工作区。" : "Changes are unavailable. Refresh the workspace from More options.")}</div>`;
  } finally {
    if (path === state.workspacePath && version === runtime.workspaceVersion && request === runtime.changesRequest) $("#changesSection")?.setAttribute("aria-busy", "false");
  }
}

export function openPanel(title, body, options = {}) {
  runtime.panelVersion = (runtime.panelVersion || 0) + 1;
  $("#panelTitle").textContent = title;
  $("#panelBody").innerHTML = body;
  const modal = $("#panelModal");
  modal.classList.toggle("promo-modal", body.includes("promo-page"));
  modal.classList.toggle("immersive-modal", Boolean(options.immersive));
  modal.classList.toggle("wide-modal", Boolean(options.wide));
  modal.classList.remove("fullscreen");
  const expand = $("#panelExpand");
  if (expand) {
    expand.hidden = false;
    expand.title = "展开全屏";
    expand.setAttribute("aria-label", "展开全屏");
    expand.innerHTML = icon("maximize-2");
  }
  modal.classList.add("show");
  modal.setAttribute("aria-hidden", "false");
  refreshIcons();
  activateDialog(modal, { onEscape: closePanel });
}

export function beginPanelRequest(title) {
  openPanel(title, `<div class="empty-panel" role="status">${escapeHtml(state.locale === "zh" ? "正在加载…" : "Loading…")}</div>`);
  const version = runtime.panelVersion;
  return () => version === runtime.panelVersion && $("#panelModal").classList.contains("show");
}

export function closePanel() {
  runtime.panelVersion = (runtime.panelVersion || 0) + 1;
  deactivateDialog($("#panelModal"));
  const active = document.activeElement;
  if (active instanceof HTMLElement && $("#panelModal").contains(active)) active.blur();
  $("#panelModal").classList.remove("show");
  $("#panelModal").classList.remove("promo-modal");
  $("#panelModal").classList.remove("immersive-modal", "wide-modal", "fullscreen");
  $("#panelModal").setAttribute("aria-hidden", "true");
  window.scrollTo(0, 0);
}

export function togglePanelFullscreen() {
  const modal = $("#panelModal");
  const fullscreen = modal.classList.toggle("fullscreen");
  const button = $("#panelExpand");
  if (!button) return;
  button.title = fullscreen ? "退出全屏" : "展开全屏";
  button.setAttribute("aria-label", button.title);
  button.innerHTML = icon(fullscreen ? "minimize-2" : "maximize-2");
  refreshIcons();
}

export function taskRow(task) {
  const statusClass = task.status === "completed" ? "success" : task.status === "failed" ? "error" : ["cancelled", "interrupted"].includes(task.status) ? "cancelled" : task.status === "queued" ? "queued" : "running";
  const cancel = ["queued", "running"].includes(task.status) ? `<button class="panel-icon-action" data-cancel-task="${escapeHtml(task.task_id)}" title="${t("cancel")}">${icon("square")}</button>` : "";
  const resume = ["failed", "cancelled", "interrupted"].includes(task.status) ? `<button class="panel-icon-action" data-resume-task="${escapeHtml(task.task_id)}" title="${t("tasks.resume")}">${icon("rotate-ccw")}</button>` : "";
  const phase = phaseLabel(task);
  const streamSize = Number(task.stream_length || String(task.stream_text || "").length);
  const detail = `${phase} · ${formatDuration(taskDuration(task))} · ${streamSize} chars · ${taskMetrics(task)}`;
  const children = task.child_task_ids?.length ? ` · ${task.child_task_ids.length} ${t("tasks.children")}` : "";
  const workspace = task.workspace_path ? task.workspace_path.split(/[\\/]/).filter(Boolean).pop() : "workspace";
  const details = `<button class="panel-icon-action" data-open-detail="${escapeHtml(task.task_id)}" title="${escapeHtml(t("tasks.detail"))}" aria-label="${escapeHtml(t("tasks.detail"))}">${icon("maximize-2")}</button>`;
  const restore = task.task_id ? `<button class="panel-icon-action" data-restore-task="${escapeHtml(task.task_id)}" title="${escapeHtml(t("restore.action"))}" aria-label="${escapeHtml(t("restore.action"))}">${icon("rotate-ccw")}</button>` : "";
  return `<div class="task-row" data-open-task="${escapeHtml(task.task_id)}" tabindex="0"><span class="task-state ${statusClass}"></span><div><strong>${escapeHtml(task.task_kind === "batch" ? `${task.task_id} · ${t("tasks.children")}` : task.task_id)}</strong><small>${escapeHtml(workspace)} · ${escapeHtml(detail)}${children}</small></div><div class="task-row-actions">${details}${restore}${resume}${cancel}</div></div>`;
}

export async function openTaskInWorkspace(taskId) {
  try {
    const task = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    cacheTaskDetail(task);
    const targetWorkspace = String(task.workspace_path || "");
    if (targetWorkspace && state.workspacePath && targetWorkspace.replaceAll("\\", "/").toLowerCase() !== state.workspacePath.replaceAll("\\", "/").toLowerCase()) {
      await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: targetWorkspace }) });
      await loadWorkspace();
    }
    const sessionId = String(task.session_id || task.task_id);
    taskHistoryBySession.set(sessionId, task);
    const historyItems = taskHistoryListBySession.get(sessionId) || [];
    const mergedHistory = historyItems.some((item) => item.task_id === task.task_id)
      ? historyItems.map((item) => item.task_id === task.task_id ? task : item)
      : [task, ...historyItems];
    taskHistoryListBySession.set(sessionId, mergedHistory.sort((left, right) => Number(right.created_at_epoch || 0) - Number(left.created_at_epoch || 0)));
    closePanel();
    setSession(sessionId);
    state.activeTaskId = task.task_id;
    updateTaskDock(task);
    if (isTerminalTask(task)) {
      state.activeTaskId = null;
      setBusy(false);
    } else if (!runningTasks.has(task.task_id)) {
      const loadingId = `loading-${task.task_id}`;
      addLoadingMessage(loadingId, task);
      bindRunningTask(task, loadingId, sessionId);
      setBusy(true);
      watchTask(task.task_id).catch((error) => showToast(error.message));
    } else {
      const binding = runningTasks.get(task.task_id);
      if (binding && !document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, binding.data);
      setBusy(true);
    }
    showToast(state.locale === "zh" ? "已打开任务会话" : "Task session opened");
  } catch (error) {
    showToast(error.message);
  }
}

export async function openTaskDetail(taskId) {
  const current = beginPanelRequest(t("tasks.open"));
  try {
    const task = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    if (!current()) return;
    const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
    const execution = executionTrailMarkup(events, task.events || []);
    const children = Array.isArray(task.child_task_ids) && task.child_task_ids.length
      ? `<div class="task-detail-children">${task.child_task_ids.map((child) => `<button class="panel-session" data-open-task="${escapeHtml(child)}">${escapeHtml(child)}</button>`).join("")}</div>`
      : "";
    const resume = ["failed", "cancelled", "interrupted"].includes(task.status)
      ? `<button class="panel-primary" data-resume-task="${escapeHtml(task.task_id)}">${t("tasks.resume")}</button>`
      : "";
    const restore = `<button class="panel-secondary" data-restore-task="${escapeHtml(task.task_id)}">${icon("rotate-ccw")} ${escapeHtml(t("restore.action"))}</button>`;
    const attachments = attachmentMarkup(task.attachments || []);
    openPanel(`${t("tasks.open")} · ${task.task_id}`, `<div class="task-detail"><div class="task-detail-status"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div><div class="task-detail-actions task-detail-top-actions"><button class="panel-secondary" data-open-task="${escapeHtml(task.task_id)}">${icon("arrow-up-right")} ${escapeHtml(t("tasks.openSession"))}</button>${restore}</div>${runtimeMetricsMarkup(task)}<div class="panel-section-title">${t("workspace.current")}</div><code class="task-detail-path">${escapeHtml(task.workspace_path || "")}</code><div class="panel-section-title">Prompt</div><div class="task-detail-prompt">${formatText(task.prompt || task.preview || "")}</div>${attachments ? `<div class="panel-section-title">Images</div>${attachments}` : ""}<div class="panel-section-title">Response</div><div class="task-detail-answer">${formatText(task.answer || task.stream_text || task.error || "")}</div>${execution ? `<div class="panel-section-title">Tools & stage trace</div>${execution}` : ""}${children}${resume ? `<div class="task-detail-actions">${resume}</div>` : ""}</div>`, { immersive: true });
  } catch (error) {
    if (!current()) return;
    openPanel(t("tasks.open"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

export function openBatchPanel() {
  const taskFields = [1, 2, 3].map((index) => `<label class="batch-field"><span>${escapeHtml(t("batch.task"))} ${index}</span><textarea name="task" rows="3" placeholder="${escapeHtml(state.locale === "zh" ? "例如：检查后端测试并总结风险" : "For example: inspect backend tests and summarize risks")}"></textarea></label>`).join("");
  openPanel(t("panel.batch"), `<form class="batch-form" id="batchForm"><div class="batch-heading"><span class="eyebrow">${escapeHtml(t("batch.title"))}</span><h3>${escapeHtml(t("batch.title"))}</h3><p>${escapeHtml(t("batch.subtitle"))}</p></div><div class="batch-fields">${taskFields}</div><label class="batch-field"><span>${escapeHtml(t("batch.context"))}</span><textarea name="shared_context" rows="3" placeholder="${escapeHtml(t("batch.note"))}"></textarea></label><div class="task-detail-actions"><button class="panel-primary" type="submit">${icon("play")} ${escapeHtml(t("batch.run"))}</button></div></form>`, { wide: true });
}

export async function openActivityPanel() {
  const current = beginPanelRequest(t("tasks.center"));
  try {
    const data = await requestJson("/api/tasks?limit=200");
    if (!current()) return;
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    openPanel(t("tasks.center"), `<div class="panel-toolbar"><span>${tasks.length} ${state.locale === "zh" ? "个任务" : "tasks"}</span><button class="panel-text-action" data-panel-action="activity">${t("panel.refresh")}</button></div><div class="task-filters"><span class="filter-chip active">${t("tasks.allWorkspaces")}</span><span class="filter-chip">${escapeHtml(state.workspacePath ? state.workspacePath.split(/[\\/]/).filter(Boolean).pop() : "workspace")}</span></div><div class="task-list">${tasks.length ? tasks.map(taskRow).join("") : `<div class="empty-panel">${t("tasks.noHistory")}</div>`}</div>`);
  } catch (error) {
    if (!current()) return;
    openPanel(t("tasks.center"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

export async function openWorkspacesPanel() {
  const current = beginPanelRequest(t("panel.workspaces"));
  try {
    const info = await requestJson("/api/workspace");
    if (!current()) return;
    const worktrees = Array.isArray(info.worktrees) ? info.worktrees : [];
    const sandbox = info.sandbox || {};
    const mcp = info.mcp || {};
    const recent = Array.isArray(info.recent_workspaces) ? info.recent_workspaces : [];
    const recentRows = recent.length ? recent.map((item) => `<button class="workspace-row ${item.path === info.path ? "active" : ""}" data-select-workspace="${escapeHtml(item.path)}"><span class="workspace-row-icon">${icon(item.path === info.path ? "radio" : "folder")}</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.path)}</small></span>${item.path === info.path ? `<em>ACTIVE</em>` : ""}</button>`).join("") : `<div class="empty-panel">${t("panel.noWorktrees")}</div>`;
    const rows = worktrees.map((item) => `<div class="worktree-row"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.branch || "detached")} · ${escapeHtml(item.path)}</small></div>${item.managed ? `<button class="panel-icon-action" data-remove-worktree="${escapeHtml(item.name)}" title="${t("panel.close")}">${icon("trash-2")}</button>` : ""}</div>`).join("");
    const sandboxLabel = sandbox.isolated ? t("panel.isolated") : sandbox.backend === "unavailable" ? t("connection.offline") : t("panel.hostProcess");
    openPanel(t("panel.workspaces"), `<div class="workspace-switcher"><div class="panel-section-title">${t("workspace.current")}</div><code class="workspace-current-path">${escapeHtml(info.path)}</code><form class="workspace-form" id="workspaceSelectForm"><label>${t("workspace.path")}<input id="workspacePathInput" name="path" required value="${escapeHtml(info.path)}" placeholder="${t("workspace.selectHint")}" /></label><button class="panel-primary" type="submit">${t("workspace.open")}</button></form><small class="workspace-hint">${t("workspace.selectHint")}</small><div class="panel-section-title">${t("workspace.recent")}</div><div class="workspace-list">${recentRows}</div></div><div class="status-grid"><div><span>${t("panel.sandbox")}</span><strong>${escapeHtml(String(sandbox.backend || "host"))}</strong><small>${sandboxLabel}</small></div><div><span>${t("panel.mcp")}</span><strong>${escapeHtml(String(mcp.configured || 0))}</strong><small>${t("panel.servers")}</small></div></div><div class="panel-section-title">${t("panel.createWorktree")}</div><form class="worktree-form" id="worktreeForm"><input id="worktreeName" name="name" required maxlength="64" placeholder="${t("panel.name")}" /><input id="worktreeBranch" name="branch" maxlength="128" placeholder="${t("panel.branch")}" /><button class="panel-primary" type="submit">${t("panel.create")}</button></form><div class="panel-section-title">${t("panel.gitWorktrees")}</div><div class="worktree-list">${rows || `<div class="empty-panel">${t("panel.noWorktrees")}</div>`}</div>`);
  } catch (error) {
    if (!current()) return;
    openPanel(t("panel.workspaces"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

export function openSettingsPanel() {
  const current = state.locale === "zh" ? "中文" : "English";
  const effortMarkup = ["low", "mid", "high", "xhigh", "max", "ultra"].map((effort) => "<option value=\"" + effort + "\" " + (state.reasoningEffort === effort ? "selected" : "") + ">" + escapeHtml(t("reasoning." + effort)) + "</option>").join("");
  const languageButtons = "<div class=\"settings-block\"><span>" + t("panel.language") + "</span><strong>" + current + "</strong><div class=\"settings-locale\"><button class=\"locale-option " + (state.locale === "zh" ? "active" : "") + "\" data-set-locale=\"zh\">中文</button><button class=\"locale-option " + (state.locale === "en" ? "active" : "") + "\" data-set-locale=\"en\">English</button></div></div>";
  const reasoningBlock = "<div class=\"settings-block\"><span>" + t("panel.reasoning") + "</span><div class=\"settings-effort\"><select id=\"reasoningEffortSelect\" aria-label=\"" + escapeHtml(t("panel.reasoning")) + "\">" + effortMarkup + "</select></div><small class=\"settings-note\">" + escapeHtml(t("panel.reasoningNote")) + "</small></div>";
  const sandboxBlock = "<div class=\"settings-block\"><span>" + t("panel.sandbox") + "</span><strong>" + (state.locale === "zh" ? "见工作区面板" : "See Workspaces") + "</strong></div>";
  const rewindBlock = "<div class=\"settings-block settings-rewind\"><span>" + escapeHtml(t("rewind.advanced")) + "</span><form id=\"rewindForm\" class=\"rewind-form\"><label class=\"rewind-label\"><span>" + escapeHtml(t("rewind.keepLabel")) + "</span><input id=\"rewindKeep\" type=\"number\" min=\"1\" value=\"3\" required aria-label=\"" + escapeHtml(t("rewind.keepLabel")) + "\" /></label><button class=\"send-button rewind-button\" type=\"submit\">" + escapeHtml(t("rewind.action")) + "</button></form><small class=\"settings-note\">" + escapeHtml(t("rewind.hint")) + "</small></div>";
  const allowlistBlock = "<div class=\"settings-block\" id=\"allowlistEditor\"><span>" + escapeHtml(t("allowlist.title")) + "</span><small class=\"settings-note\">" + escapeHtml(t("allowlist.hint")) + "</small><form id=\"allowlistForm\" class=\"allowlist-form\"><label><span>" + escapeHtml(t("allowlist.commands")) + "</span><textarea id=\"allowlistCommands\" rows=\"3\"></textarea></label><label><span>" + escapeHtml(t("allowlist.paths")) + "</span><textarea id=\"allowlistPaths\" rows=\"3\"></textarea></label><label><span>" + escapeHtml(t("allowlist.tools")) + "</span><textarea id=\"allowlistTools\" rows=\"2\"></textarea></label><button class=\"send-button\" type=\"submit\">" + escapeHtml(t("allowlist.save")) + "</button></form></div>";
  openPanel(t("panel.settings"), languageButtons + reasoningBlock + sandboxBlock + rewindBlock + allowlistBlock);
  bindAllowlistEditor();
  const rewindForm = $("#rewindForm");
  if (rewindForm) {
    rewindForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const keepInput = $("#rewindKeep");
      if (!(keepInput instanceof HTMLInputElement)) return;
      const keepMessages = Number(keepInput.value || 0);
      if (!Number.isFinite(keepMessages) || keepMessages < 1) {
        showToast(t("rewind.fail"));
        return;
      }
      try {
        const outcome = await requestJson("/api/sessions/rewind", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: state.sessionId, keep_messages: keepMessages }),
        }, 20000);
        closePanel();
        showToast(`${t("rewind.done")} -${outcome.removed || 0}`);
        setSession(state.sessionId);
      } catch (error) {
        showToast(`${t("rewind.fail")}: ${error.message}`);
      }
    });
  }
}

export function openPromoPanel() {
  const promo = state.locale === "zh"
    ? {
        panel: "minicc · Agent 工作台",
        kicker: "LOCAL AGENT / INTERVIEW BUILD",
        title: "从一句话，",
        accent: "到一份可验证的交付。",
        description: "minicc 把规划、工具调用、文件改动和测试验证放在同一条可追溯路径里。你看到的是证据，不是黑盒里的猜测。",
        cta: "开始新任务",
        ctaNote: "LOCAL FIRST · SSE STREAM",
        proofTitle: "从第一行代码到最后一次验证",
        proofBody: "一个工作区 · 一条可追溯路径",
        previewLabel: "agent / live",
        live: "RUNNING",
        taskLabel: "强化版宣传页",
        taskMeta: "workspace · minicc-codex",
        metrics: ["SSE 实时", "00:14", "72% context"],
        phases: [
          ["01", "理解需求", "拆解目标与验收标准", "check", "done"],
          ["02", "修改工作区", "写入前先检查当前 diff", "loader-circle", "active"],
          ["03", "验证交付", "测试结果和剩余风险可复盘", "circle-dashed", ""],
        ],
        diffLabel: "live diff / web/styles.css",
        diff: [["+", "--agent-accent: coral;"], ["+", "--stream-mode: live;"], ["-", "--status: waiting;"], [" ", "/* verified by pytest */"]],
        sectionKicker: "WHY MINICC",
        sectionTitle: "少一点猜测，多一点确定。",
        sectionBody: "为真实的工程协作设计：先收集上下文，再执行动作，最后用验证结果闭环。",
        capabilities: [
          ["scan-search", "看得见过程", "阶段摘要、工具调用、流式回答和上下文用量实时呈现，复杂任务不会突然失去方向。"],
          ["layers-3", "并行而不互相阻塞", "独立会话使用独立任务槽位；批量任务可并行执行，完成后再合并结果。"],
          ["git-compare", "改动可审查", "文件列表和红绿 diff 直接联动，点击文件即可查看变更与当前内容。"],
          ["shield-check", "本地优先", "工作区、权限、取消、重试和审计都由本地 harness 负责，模型只负责判断。"],
        ],
        bottomKicker: "READY WHEN YOU ARE",
        bottomTitle: "下一次提交，",
        bottomAccent: "从一句话开始。",
        bottomBody: "切换中文或 English，打开一个真实工作区，立即体验完整循环。",
        bottomCta: "进入工作台",
      }
    : {
        panel: "minicc · Agent workspace",
        kicker: "LOCAL AGENT / INTERVIEW BUILD",
        title: "From one prompt,",
        accent: "to a delivery you can verify.",
        description: "minicc puts planning, tool calls, file changes, and verification on one traceable path. You see evidence, not a black box guessing in the dark.",
        cta: "Start a new task",
        ctaNote: "LOCAL FIRST · SSE STREAM",
        proofTitle: "From the first line to the final check",
        proofBody: "One workspace · One traceable path",
        previewLabel: "agent / live",
        live: "RUNNING",
        taskLabel: "Harden the promo page",
        taskMeta: "workspace · minicc-codex",
        metrics: ["SSE live", "00:14", "72% context"],
        phases: [
          ["01", "Understand the request", "Turn intent into acceptance criteria", "check", "done"],
          ["02", "Change the workspace", "Inspect the diff before writing", "loader-circle", "active"],
          ["03", "Verify the delivery", "Keep tests and remaining risk visible", "circle-dashed", ""],
        ],
        diffLabel: "live diff / web/styles.css",
        diff: [["+", "--agent-accent: coral;"], ["+", "--stream-mode: live;"], ["-", "--status: waiting;"], [" ", "/* verified by pytest */"]],
        sectionKicker: "WHY MINICC",
        sectionTitle: "Less guessing. More certainty.",
        sectionBody: "Built for real engineering work: gather context, take action, then close the loop with verification.",
        capabilities: [
          ["scan-search", "See the work", "Phase summaries, tool calls, streamed answers, and context usage stay visible through long tasks."],
          ["layers-3", "Parallel without blocking", "Independent sessions get independent task slots; batch work runs in parallel and merges at the end."],
          ["git-compare", "Review every change", "The file list and red-green diff stay linked. Open a file to inspect its patch and current content."],
          ["shield-check", "Local first", "The local harness owns workspace, permissions, cancellation, retries, and audit trails. The model owns judgment."],
        ],
        bottomKicker: "READY WHEN YOU ARE",
        bottomTitle: "Your next commit,",
        bottomAccent: "starts with a sentence.",
        bottomBody: "Switch between Chinese and English, open a real workspace, and run the full loop.",
        bottomCta: "Open workspace",
      };
  const phaseMarkup = promo.phases.map(([number, title, detail, iconName, status]) => `<div class="promo-phase ${status}"><span>${escapeHtml(number)}</span><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(detail)}</small></div><i data-lucide="${iconName}"></i></div>`).join("");
  const capabilityMarkup = promo.capabilities.map(([iconName, title, detail], index) => `<article class="promo-card"><span class="promo-number">0${index + 1}</span><i data-lucide="${iconName}"></i><strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span></article>`).join("");
  const metricMarkup = promo.metrics.map((metric) => `<span>${escapeHtml(metric)}</span>`).join("");
  const diffMarkup = promo.diff.map(([marker, line]) => `<span class="promo-diff-line ${marker === "+" ? "add" : marker === "-" ? "del" : "context"}"><b>${escapeHtml(marker)}</b>${escapeHtml(line)}</span>`).join("");
  openPanel(promo.panel, `<article class="promo-page">
    <section class="promo-hero">
      <div class="promo-hero-copy">
        <span class="promo-kicker"><span class="eyebrow-line"></span>${escapeHtml(promo.kicker)}</span>
        <h3>${escapeHtml(promo.title)}<br><em>${escapeHtml(promo.accent)}</em></h3>
        <p>${escapeHtml(promo.description)}</p>
        <div class="promo-actions"><button class="panel-primary promo-cta" data-panel-action="new-task">${escapeHtml(promo.cta)} ${icon("arrow-up-right")}</button><span class="mono">${escapeHtml(promo.ctaNote)}</span></div>
        <div class="promo-proof"><span class="proof-avatars"><b>m</b><b>✓</b><b>⌘</b></span><span><strong>${escapeHtml(promo.proofTitle)}</strong><small>${escapeHtml(promo.proofBody)}</small></span></div>
      </div>
      <div class="promo-hero-preview" aria-label="${escapeHtml(promo.previewLabel)}">
        <div class="promo-preview-head"><span class="terminal-dot coral"></span><span class="terminal-dot amber"></span><span class="terminal-dot mint"></span><span class="mono">${escapeHtml(promo.previewLabel)}</span><span class="console-live"><i></i> ${escapeHtml(promo.live)}</span></div>
        <div class="promo-preview-task"><span class="promo-preview-icon">${icon("sparkles")}</span><span><strong>${escapeHtml(promo.taskLabel)}</strong><small>${escapeHtml(promo.taskMeta)}</small></span><span class="promo-preview-check">${icon("radio")}</span></div>
        <div class="promo-metrics">${metricMarkup}</div>
        <div class="promo-phase-list">${phaseMarkup}</div>
        <div class="promo-diff"><div><span class="mono">${escapeHtml(promo.diffLabel)}</span><span class="promo-diff-state">● LIVE</span></div><pre>${diffMarkup}</pre></div>
      </div>
    </section>
    <section class="promo-section">
      <div class="promo-section-head"><span class="promo-kicker">${escapeHtml(promo.sectionKicker)}</span><h4>${escapeHtml(promo.sectionTitle)}</h4><p>${escapeHtml(promo.sectionBody)}</p></div>
      <div class="promo-grid">${capabilityMarkup}</div>
    </section>
    <section class="promo-bottom"><div><span class="promo-kicker">${escapeHtml(promo.bottomKicker)}</span><h4>${escapeHtml(promo.bottomTitle)} <em>${escapeHtml(promo.bottomAccent)}</em></h4><p>${escapeHtml(promo.bottomBody)}</p></div><button class="panel-secondary promo-cta" data-panel-action="new-task">${escapeHtml(promo.bottomCta)} ${icon("arrow-right")}</button></section>
  </article>`);
}

export function openOptionsPanel() {
  openPanel(t("panel.options"), `<div class="options-list"><button class="panel-command" data-panel-action="clear"><span>${icon("eraser")}</span>${t("panel.clear")}</button><button class="panel-command" data-panel-action="export"><span>${icon("download")}</span>${t("panel.export")}</button><button class="panel-command" data-panel-action="reload"><span>${icon("refresh-cw")}</span>${t("panel.reload")}</button></div>`);
}

export function openTaskListPanel() {
  const items = $$(".thread-item").map((item) => `<button class="panel-session" data-switch-session="${escapeHtml(item.dataset.session)}"><strong>${escapeHtml(item.querySelector("strong")?.textContent || item.dataset.session)}</strong><small>${escapeHtml(item.querySelector("small")?.textContent || "")}</small></button>`).join("");
  openPanel(t("recentTasks"), `<div class="panel-session-list">${items}</div>`);
}

export function exportChat() {
  const text = $("#messageList").innerText;
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.sessionId}.txt`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast(state.locale === "zh" ? "对话已导出" : "Chat exported");
}

export function switchInspectorTab(tab) {
  runtime.inspectorTab = ["changes", "files", "verification"].includes(tab) ? tab : "changes";
  $$(".inspector-tab").forEach((item) => {
    const active = item.dataset.inspectorTab === runtime.inspectorTab;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", String(active));
    item.tabIndex = active ? 0 : -1;
  });
  $("#overviewSection").hidden = runtime.inspectorTab !== "verification";
  $("#changesSection").hidden = runtime.inspectorTab !== "changes";
  $("#fileTreeSection").hidden = runtime.inspectorTab !== "files";
  $("#filesSection").hidden = true;
  $("#verificationSection").hidden = runtime.inspectorTab !== "verification";
}

export async function rewindToUserIndex(userIndex) {
  const index = Number(userIndex);
  if (!Number.isFinite(index) || index < 1) {
    showToast(t("rewind.fail"));
    return;
  }
  const scope = captureViewScope();
  try {
    const outcome = await requestJson("/api/sessions/rewind", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: scope.sessionId, user_index: index }),
    }, 20000);
    showToast(`${t("rewind.done")} #${outcome.user_index || index}`);
    const cacheKey = sessionViewKey(scope.sessionId, scope.workspacePath);
    sessionMarkup.delete(cacheKey);
    try { localStorage.removeItem(cacheKey); } catch { /* ignore quota */ }
    if (isViewScopeCurrent(scope)) {
      await loadTaskHistory();
      if (isViewScopeCurrent(scope)) renderSession(scope.sessionId);
    }
  } catch (error) {
    showToast(`${t("rewind.fail")}: ${error.message}`);
  }
}

export async function restoreTaskSnapshot(taskId) {
  if (!taskId) return;
  try {
    const result = await requestJson("/api/workspace/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId }),
    }, 20000);
    const unresolved = [...(result.conflicts || []), ...(result.skipped || [])];
    showToast(unresolved.length ? `${t("restore.partial")}: ${unresolved.slice(0, 3).join(", ")}${unresolved.length > 3 ? "…" : ""}` : t("restore.done"));
    loadChanges();
    refreshFileTreeSoon();
  } catch (error) {
    showToast(`${t("restore.fail")}: ${error.message}`);
  }
}

export function parseAllowlistLines(value) {
  return String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

export async function bindAllowlistEditor() {
  const host = $("#allowlistEditor");
  const form = $("#allowlistForm");
  if (!host || !form) return;
  const fill = (id, items) => {
    const field = document.getElementById(id);
    if (field) field.value = (Array.isArray(items) ? items : []).join("\n");
  };
  try {
    const data = await requestJson(`/api/allowlist?session_id=${encodeURIComponent(state.sessionId)}`);
    fill("allowlistCommands", data.commands);
    fill("allowlistPaths", data.paths);
    fill("allowlistTools", data.tools);
  } catch (error) {
    const message = String(error.message || "");
    if (/404|not found/i.test(message)) {
      host.innerHTML = `<span>${escapeHtml(t("allowlist.title"))}</span><small class="settings-note">${escapeHtml(t("allowlist.soon"))}</small>`;
      return;
    }
    host.insertAdjacentHTML("beforeend", `<small class="settings-note">${escapeHtml(message)}</small>`);
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await requestJson("/api/allowlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          commands: parseAllowlistLines($("#allowlistCommands")?.value),
          paths: parseAllowlistLines($("#allowlistPaths")?.value),
          tools: parseAllowlistLines($("#allowlistTools")?.value),
        }),
      });
      showToast(state.locale === "zh" ? "允许列表已保存" : "Allowlist saved");
    } catch (error) {
      showToast(error.message);
    }
  });
}

export function openHelpPanel() {
  const rows = state.locale === "zh"
    ? [["发送任务", "Enter"], ["换行", "Shift+Enter"], ["新任务", "Ctrl/⌘ N"], ["搜索任务", "/"], ["关闭面板 / 小游戏", "Esc"]]
    : [["Send task", "Enter"], ["Newline", "Shift+Enter"], ["New task", "Ctrl/⌘ N"], ["Search tasks", "/"], ["Close panel / game", "Esc"]];
  const list = rows.map(([label, key]) => `<div class="help-shortcut"><span>${escapeHtml(label)}</span><kbd>${escapeHtml(key)}</kbd></div>`).join("");
  openPanel(t("help.title"), `<div class="help-panel"><div class="panel-section-title">${escapeHtml(t("help.shortcuts"))}</div>${list}<div class="panel-section-title">${escapeHtml(t("help.arcade"))}</div><button type="button" class="panel-command" id="helpArcadeButton"><span>${icon("gamepad-2")}</span>${escapeHtml(t("help.arcade"))}</button></div>`);
  $("#helpArcadeButton")?.addEventListener("click", () => {
    closePanel();
    openArcade().catch((error) => showToast(error.message));
  });
}
