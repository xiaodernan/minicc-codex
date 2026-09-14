// NOTE: 源文件分片（web/src/）。此文件由 `npm run build:web` 按序拼接生成，勿直接编辑。
function streamTask(taskId) {
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
        updateBoundTask(taskId, latest);
        resolve(await completeTask(loadingId, latest));
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

function watchTask(taskId) {
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

async function cancelActiveTask() {
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

function renderAttachmentTray() {
  const tray = $("#attachmentTray");
  if (!tray) return;
  tray.hidden = state.attachments.length === 0;
  tray.innerHTML = attachmentMarkup(state.attachments, "attachment-tray-items");
  refreshIcons();
}

function readImageFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`无法读取图片：${file.name}`));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
}

async function addImageFiles(fileList) {
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

function clearAttachments() {
  state.attachments = [];
  const input = $("#imageInput");
  if (input) input.value = "";
  renderAttachmentTray();
}

async function sendMessage(event) {
  event?.preventDefault();
  const input = $("#promptInput");
  const queuedAttachments = state.attachments.map((item) => ({ ...item }));
  const message = input.value.trim() || (queuedAttachments.length ? (state.locale === "zh" ? "请分析我上传的图片。" : "Analyze the images I uploaded.") : "");
  const sessionId = state.sessionId;
  const workspacePath = state.workspacePath;
  if ((!message && !queuedAttachments.length) || state.submitting) return;
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
    state.submitting = false;
    bindRunningTask(task, loadingId, sessionId);
    if (state.sessionId === sessionId) state.activeTaskId = task.task_id;
    setBusy(true);
    updateTaskDock(task);
    await loadTaskHistory();
    await watchTask(task.task_id);
  } catch (error) {
    finishLiveTask(loadingId);
    document.getElementById(loadingId)?.remove();
    if (state.sessionId === sessionId) addAssistantMessage({ error: error.message });
    showToast(error.message);
    setConnection(false, "API error");
  } finally {
    state.submitting = false;
    if (!sessionTaskBindings(sessionId, workspacePath).length) state.activeTaskId = null;
    if (state.sessionId === sessionId) setBusy(false);
    input.focus();
  }
}

function resetTask() {
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

function runDemoFlow() {
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

async function loadWorkspace() {
  try {
    const response = await fetch("/api/workspace", { headers: authHeaders() });
    if (response.status === 401) {
      const payload = await response.json().catch(() => ({}));
      if (payload.auth_required) showAuthModal();
      throw new Error("unauthorized");
    }
    if (!response.ok) throw new Error("offline");
    const info = await response.json();
    const previousPath = state.workspacePath;
    state.workspaceInfo = info;
   state.workspacePath = info.path || state.workspacePath;
   state.contextWindowTokens = Number(info.context_window_tokens || state.contextWindowTokens || 300000);
    if (!localStorage.getItem("minicc-reasoning") && ["low", "mid", "high", "xhigh", "max"].includes(info.reasoning_effort)) state.reasoningEffort = info.reasoning_effort;
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
    await loadTaskHistory();
    await loadChanges();
    // The file tree is workspace-scoped: reload it on the initial load, on
    // workspace switches, and whenever the workspace view is refreshed.
    refreshFileTreeSoon();
    try {
      const taskData = await requestJson(`/api/tasks?limit=100&workspace=${encodeURIComponent(state.workspacePath)}`);
      const tasks = Array.isArray(taskData.tasks) ? taskData.tasks : [];
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
    }
    return true;
  } catch {
    setConnection(false, "Offline");
    return false;
  }
}

function fileType(path) {
  const extension = String(path).split(".").pop()?.toLowerCase();
  if (extension === "py") return "py";
  if (["css", "scss"].includes(extension)) return "css";
  if (["md", "txt"].includes(extension)) return "md";
  if (["js", "ts", "tsx", "jsx"].includes(extension)) return "js";
  return "file";
}

function changeStatusLabel(status) {
  return t(`changes.${status}`) || status;
}

function changeFileRow(item) {
  const path = String(item.path || "");
  const status = String(item.status || "clean");
  const additions = Number(item.additions || 0);
  const deletions = Number(item.deletions || 0);
  return `<button class="file-row file-row-${escapeHtml(status)}" data-file="${escapeHtml(path)}" data-open-diff="${escapeHtml(path)}"><span class="file-type ${fileType(path)}">${escapeHtml(fileType(path).toUpperCase())}</span><span><strong>${escapeHtml(path)}</strong><small>${escapeHtml(changeStatusLabel(status))} · <span class="diff-add">+${additions}</span> <span class="diff-del">-${deletions}</span></small></span><i data-lucide="chevron-right"></i></button>`;
}

function renderChanges(data) {
  const files = Array.isArray(data?.files) ? data.files : [];
  const changed = new Map(files.map((item) => [String(item.path), item]));
  const focus = ["minicc/main.py", "minicc/agent/loop.py", "minicc/llm/openai_provider.py", "web/app.js", "web/styles.css", "README.md"];
  const paths = [...new Set([...files.map((item) => String(item.path)), ...focus])].slice(0, 12);
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
      ? files.slice(0, 6).map((item) => `<button class="change-item change-item-button" data-open-diff="${escapeHtml(item.path)}"><span class="change-bar ${item.status === "added" ? "added" : item.status === "deleted" ? "deleted" : "changed"}"></span><span><strong>${escapeHtml(item.path)}</strong><small>${escapeHtml(changeStatusLabel(item.status))} · <span class="diff-add">+${Number(item.additions || 0)}</span> <span class="diff-del">-${Number(item.deletions || 0)}</span></small></span><span class="change-time">${escapeHtml(t("changes.now"))}</span></button>`).join("")
      : `<div class="change-item"><span class="change-bar muted"></span><span><strong>${escapeHtml(t("changes.clean"))}</strong><small>${escapeHtml(t("changes.cleanHint"))}</small></span><span class="change-time">--</span></div>`;
  }
  refreshIcons();
}

async function loadChanges() {
  if (!state.workspacePath) return;
  try {
    const data = await requestJson("/api/changes", {}, 12000);
    state.changes = data;
    renderChanges(data);
  } catch {
    // The chat remains usable when Git is unavailable.
  }
}

function openPanel(title, body, options = {}) {
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
}

function closePanel() {
  const active = document.activeElement;
  if (active instanceof HTMLElement && $("#panelModal").contains(active)) active.blur();
  $("#panelModal").classList.remove("show");
  $("#panelModal").classList.remove("promo-modal");
  $("#panelModal").classList.remove("immersive-modal", "wide-modal", "fullscreen");
  $("#panelModal").setAttribute("aria-hidden", "true");
  window.scrollTo(0, 0);
}

function togglePanelFullscreen() {
  const modal = $("#panelModal");
  const fullscreen = modal.classList.toggle("fullscreen");
  const button = $("#panelExpand");
  if (!button) return;
  button.title = fullscreen ? "退出全屏" : "展开全屏";
  button.setAttribute("aria-label", button.title);
  button.innerHTML = icon(fullscreen ? "minimize-2" : "maximize-2");
  refreshIcons();
}

function taskRow(task) {
  const statusClass = task.status === "completed" ? "success" : task.status === "failed" ? "error" : ["cancelled", "interrupted"].includes(task.status) ? "cancelled" : task.status === "queued" ? "queued" : "running";
  const cancel = ["queued", "running"].includes(task.status) ? `<button class="panel-icon-action" data-cancel-task="${escapeHtml(task.task_id)}" title="${t("cancel")}">${icon("square")}</button>` : "";
  const resume = ["failed", "cancelled", "interrupted"].includes(task.status) ? `<button class="panel-icon-action" data-resume-task="${escapeHtml(task.task_id)}" title="${t("tasks.resume")}">${icon("rotate-ccw")}</button>` : "";
  const phase = phaseLabel(task);
  const streamSize = Number(task.stream_length || String(task.stream_text || "").length);
  const detail = `${phase} · ${formatDuration(taskDuration(task))} · ${streamSize} chars · ${taskMetrics(task)}`;
  const children = task.child_task_ids?.length ? ` · ${task.child_task_ids.length} ${t("tasks.children")}` : "";
  const workspace = task.workspace_path ? task.workspace_path.split(/[\\/]/).filter(Boolean).pop() : "workspace";
  const details = `<button class="panel-icon-action" data-open-detail="${escapeHtml(task.task_id)}" title="${escapeHtml(t("tasks.detail"))}" aria-label="${escapeHtml(t("tasks.detail"))}">${icon("maximize-2")}</button>`;
  return `<div class="task-row" data-open-task="${escapeHtml(task.task_id)}" tabindex="0"><span class="task-state ${statusClass}"></span><div><strong>${escapeHtml(task.task_kind === "batch" ? `${task.task_id} · ${t("tasks.children")}` : task.task_id)}</strong><small>${escapeHtml(workspace)} · ${escapeHtml(detail)}${children}</small></div><div class="task-row-actions">${details}${resume}${cancel}</div></div>`;
}

async function openTaskInWorkspace(taskId) {
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

async function openTaskDetail(taskId) {
  try {
    const task = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
    const execution = executionTrailMarkup(events, task.events || []);
    const children = Array.isArray(task.child_task_ids) && task.child_task_ids.length
      ? `<div class="task-detail-children">${task.child_task_ids.map((child) => `<button class="panel-session" data-open-task="${escapeHtml(child)}">${escapeHtml(child)}</button>`).join("")}</div>`
      : "";
    const resume = ["failed", "cancelled", "interrupted"].includes(task.status)
      ? `<button class="panel-primary" data-resume-task="${escapeHtml(task.task_id)}">${t("tasks.resume")}</button>`
      : "";
    const attachments = attachmentMarkup(task.attachments || []);
    openPanel(`${t("tasks.open")} · ${task.task_id}`, `<div class="task-detail"><div class="task-detail-status"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div><div class="task-detail-actions task-detail-top-actions"><button class="panel-secondary" data-open-task="${escapeHtml(task.task_id)}">${icon("arrow-up-right")} ${escapeHtml(t("tasks.openSession"))}</button></div>${runtimeMetricsMarkup(task)}<div class="panel-section-title">${t("workspace.current")}</div><code class="task-detail-path">${escapeHtml(task.workspace_path || "")}</code><div class="panel-section-title">Prompt</div><div class="task-detail-prompt">${formatText(task.prompt || task.preview || "")}</div>${attachments ? `<div class="panel-section-title">Images</div>${attachments}` : ""}<div class="panel-section-title">Response</div><div class="task-detail-answer">${formatText(task.answer || task.stream_text || task.error || "")}</div>${execution ? `<div class="panel-section-title">Tools & stage trace</div>${execution}` : ""}${children}${resume ? `<div class="task-detail-actions">${resume}</div>` : ""}</div>`, { immersive: true });
  } catch (error) {
    showToast(error.message);
  }
}

function openBatchPanel() {
  const taskFields = [1, 2, 3].map((index) => `<label class="batch-field"><span>${escapeHtml(t("batch.task"))} ${index}</span><textarea name="task" rows="3" placeholder="${escapeHtml(state.locale === "zh" ? "例如：检查后端测试并总结风险" : "For example: inspect backend tests and summarize risks")}"></textarea></label>`).join("");
  openPanel(t("panel.batch"), `<form class="batch-form" id="batchForm"><div class="batch-heading"><span class="eyebrow">${escapeHtml(t("batch.title"))}</span><h3>${escapeHtml(t("batch.title"))}</h3><p>${escapeHtml(t("batch.subtitle"))}</p></div><div class="batch-fields">${taskFields}</div><label class="batch-field"><span>${escapeHtml(t("batch.context"))}</span><textarea name="shared_context" rows="3" placeholder="${escapeHtml(t("batch.note"))}"></textarea></label><div class="task-detail-actions"><button class="panel-primary" type="submit">${icon("play")} ${escapeHtml(t("batch.run"))}</button></div></form>`, { wide: true });
}

async function openActivityPanel() {
  try {
    const data = await requestJson("/api/tasks?limit=200");
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    openPanel(t("tasks.center"), `<div class="panel-toolbar"><span>${tasks.length} ${state.locale === "zh" ? "个任务" : "tasks"}</span><button class="panel-text-action" data-panel-action="activity">${t("panel.refresh")}</button></div><div class="task-filters"><span class="filter-chip active">${t("tasks.allWorkspaces")}</span><span class="filter-chip">${escapeHtml(state.workspacePath ? state.workspacePath.split(/[\\/]/).filter(Boolean).pop() : "workspace")}</span></div><div class="task-list">${tasks.length ? tasks.map(taskRow).join("") : `<div class="empty-panel">${t("tasks.noHistory")}</div>`}</div>`);
  } catch (error) {
    openPanel(t("tasks.center"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

async function openWorkspacesPanel() {
  try {
    const info = await requestJson("/api/workspace");
    const worktrees = Array.isArray(info.worktrees) ? info.worktrees : [];
    const sandbox = info.sandbox || {};
    const mcp = info.mcp || {};
    const recent = Array.isArray(info.recent_workspaces) ? info.recent_workspaces : [];
    const recentRows = recent.length ? recent.map((item) => `<button class="workspace-row ${item.path === info.path ? "active" : ""}" data-select-workspace="${escapeHtml(item.path)}"><span class="workspace-row-icon">${icon(item.path === info.path ? "radio" : "folder")}</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.path)}</small></span>${item.path === info.path ? `<em>ACTIVE</em>` : ""}</button>`).join("") : `<div class="empty-panel">${t("panel.noWorktrees")}</div>`;
    const rows = worktrees.map((item) => `<div class="worktree-row"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.branch || "detached")} · ${escapeHtml(item.path)}</small></div>${item.managed ? `<button class="panel-icon-action" data-remove-worktree="${escapeHtml(item.name)}" title="${t("panel.close")}">${icon("trash-2")}</button>` : ""}</div>`).join("");
    const sandboxLabel = sandbox.isolated ? t("panel.isolated") : sandbox.backend === "unavailable" ? t("connection.offline") : t("panel.hostProcess");
    openPanel(t("panel.workspaces"), `<div class="workspace-switcher"><div class="panel-section-title">${t("workspace.current")}</div><code class="workspace-current-path">${escapeHtml(info.path)}</code><form class="workspace-form" id="workspaceSelectForm"><label>${t("workspace.path")}<input id="workspacePathInput" name="path" required value="${escapeHtml(info.path)}" placeholder="${t("workspace.selectHint")}" /></label><button class="panel-primary" type="submit">${t("workspace.open")}</button></form><small class="workspace-hint">${t("workspace.selectHint")}</small><div class="panel-section-title">${t("workspace.recent")}</div><div class="workspace-list">${recentRows}</div></div><div class="status-grid"><div><span>${t("panel.sandbox")}</span><strong>${escapeHtml(String(sandbox.backend || "host"))}</strong><small>${sandboxLabel}</small></div><div><span>${t("panel.mcp")}</span><strong>${escapeHtml(String(mcp.configured || 0))}</strong><small>${t("panel.servers")}</small></div></div><div class="panel-section-title">${t("panel.createWorktree")}</div><form class="worktree-form" id="worktreeForm"><input id="worktreeName" name="name" required maxlength="64" placeholder="${t("panel.name")}" /><input id="worktreeBranch" name="branch" maxlength="128" placeholder="${t("panel.branch")}" /><button class="panel-primary" type="submit">${t("panel.create")}</button></form><div class="panel-section-title">${t("panel.gitWorktrees")}</div><div class="worktree-list">${rows || `<div class="empty-panel">${t("panel.noWorktrees")}</div>`}</div>`);
  } catch (error) {
    openPanel(t("panel.workspaces"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

// Commercial unified-diff rendering: one grid row per diff line with an
// old/new line-number gutter, a sign column, and the code cell. Legacy classes
// (diff-add-line / diff-del-line / diff-hunk / diff-file / diff-context) are
// preserved on the row element for CSS and smoke-test compatibility.
function diffRowMarkup(kind, sign, oldLine, newLine, code) {
  const oldCell = oldLine ? `<span class="diff-ln diff-ln-old">${oldLine}</span>` : `<span class="diff-ln diff-ln-old"></span>`;
  const newCell = newLine ? `<span class="diff-ln diff-ln-new">${newLine}</span>` : `<span class="diff-ln diff-ln-new"></span>`;
  return `<span class="diff-row ${kind}">${oldCell}${newCell}<span class="diff-sign">${escapeHtml(sign || " ")}</span><span class="diff-code">${escapeHtml(code.length ? code : " ")}</span></span>`;
}

function renderUnifiedDiffRows(patch) {
  const rows = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const line of String(patch || "").split("\n")) {
    if (line.startsWith("@@")) {
      const header = /@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
      if (header) {
        oldLine = Number(header[1]);
        newLine = Number(header[2]);
        inHunk = true;
      }
      rows.push(`<span class="diff-row diff-hunk"><span class="diff-code">${escapeHtml(line || " ")}</span></span>`);
      continue;
    }
    if (line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("--- ") || line.startsWith("+++ ") || line.startsWith("old mode") || line.startsWith("new mode") || line.startsWith("similarity ") || line.startsWith("rename ")) {
      rows.push(`<span class="diff-row diff-file"><span class="diff-code">${escapeHtml(line || " ")}</span></span>`);
      continue;
    }
    if (line.startsWith("\\")) {
      rows.push(`<span class="diff-row diff-meta"><span class="diff-code">${escapeHtml(line)}</span></span>`);
      continue;
    }
    if (!inHunk) {
      // Preamble text before the first hunk (raw patches without @@ headers).
      if (line) rows.push(`<span class="diff-row diff-file"><span class="diff-code">${escapeHtml(line)}</span></span>`);
      continue;
    }
    if (line.startsWith("+")) {
      rows.push(diffRowMarkup("diff-add-line", "+", 0, newLine, line.slice(1)));
      newLine += 1;
    } else if (line.startsWith("-")) {
      rows.push(diffRowMarkup("diff-del-line", "-", oldLine, 0, line.slice(1)));
      oldLine += 1;
    } else if (line) {
      // Context lines start with a space; a bare "" is the trailing-newline
      // artifact of split("\n") and is skipped.
      rows.push(diffRowMarkup("diff-context", " ", oldLine, newLine, line.startsWith(" ") ? line.slice(1) : line));
      oldLine += 1;
      newLine += 1;
    }
  }
  return rows.join("");
}

async function openFilePreview(path) {
  try {
    const diff = await requestJson(`/api/diff?path=${encodeURIComponent(path)}`);
    let data = { content: "" };
    try { data = await requestJson(`/api/file?path=${encodeURIComponent(path)}`); } catch { /* deleted files still have a useful diff */ }
    const additions = Number(diff.additions || 0);
    const deletions = Number(diff.deletions || 0);
    const diffRows = renderUnifiedDiffRows(diff.patch);
    const diffBody = diffRows || `<span class="diff-row diff-empty"><span class="diff-code">${escapeHtml(t("diff.empty"))}</span></span>`;
    const fileHead = `<div class="diff-file-head"><span class="diff-file-path">${icon("file-code-2")}<strong>${escapeHtml(path)}</strong></span><span class="diff-file-badges"><span class="diff-badge diff-badge-status">${escapeHtml(changeStatusLabel(diff.status || "modified"))}</span><span class="diff-badge diff-badge-add">+${additions}</span><span class="diff-badge diff-badge-del">-${deletions}</span></span></div>`;
    openPanel(`${t("panel.file")} · ${path}`, `<div class="diff-toolbar"><span>${escapeHtml(t("diff.previewAria"))}</span><span class="mono">${escapeHtml(diff.source || "diff")}</span></div>${fileHead}<pre class="diff-preview" aria-label="${escapeHtml(`${t("diff.previewAria")} · ${t("diff.oldLine")} / ${t("diff.newLine")}`)}">${diffBody}</pre><details class="file-current" open><summary>${escapeHtml(state.locale === "zh" ? "当前文件内容" : "Current file")}</summary><pre class="file-preview">${escapeHtml(data.content || "")}</pre></details>`);
  } catch (error) {
    openPanel(t("panel.file"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

function openSettingsPanel() {
  const current = state.locale === "zh" ? "中文" : "English";
  const effortMarkup = ["low", "mid", "high", "xhigh", "max"].map((effort) => "<option value=\"" + effort + "\" " + (state.reasoningEffort === effort ? "selected" : "") + ">" + escapeHtml(t("reasoning." + effort)) + "</option>").join("");
  const languageButtons = "<div class=\"settings-block\"><span>" + t("panel.language") + "</span><strong>" + current + "</strong><div class=\"settings-locale\"><button class=\"locale-option " + (state.locale === "zh" ? "active" : "") + "\" data-set-locale=\"zh\">中文</button><button class=\"locale-option " + (state.locale === "en" ? "active" : "") + "\" data-set-locale=\"en\">English</button></div></div>";
  const reasoningBlock = "<div class=\"settings-block\"><span>" + t("panel.reasoning") + "</span><div class=\"settings-effort\"><select id=\"reasoningEffortSelect\" aria-label=\"" + escapeHtml(t("panel.reasoning")) + "\">" + effortMarkup + "</select></div><small class=\"settings-note\">" + escapeHtml(t("panel.reasoningNote")) + "</small></div>";
  const sandboxBlock = "<div class=\"settings-block\"><span>" + t("panel.sandbox") + "</span><strong>" + (state.locale === "zh" ? "见工作区面板" : "See Workspaces") + "</strong></div>";
  const rewindBlock = "<div class=\"settings-block settings-rewind\"><span>" + escapeHtml(t("rewind.title")) + "</span><form id=\"rewindForm\" class=\"rewind-form\"><label class=\"rewind-label\"><span>" + escapeHtml(t("rewind.keepLabel")) + "</span><input id=\"rewindKeep\" type=\"number\" min=\"1\" value=\"3\" required aria-label=\"" + escapeHtml(t("rewind.keepLabel")) + "\" /></label><button class=\"send-button rewind-button\" type=\"submit\">" + escapeHtml(t("rewind.action")) + "</button></form><small class=\"settings-note\">" + escapeHtml(t("rewind.hint")) + "</small></div>";
  openPanel(t("panel.settings"), languageButtons + reasoningBlock + sandboxBlock + rewindBlock);
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

function openPromoPanel() {
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

function openOptionsPanel() {
  openPanel(t("panel.options"), `<div class="options-list"><button class="panel-command" data-panel-action="clear"><span>${icon("eraser")}</span>${t("panel.clear")}</button><button class="panel-command" data-panel-action="export"><span>${icon("download")}</span>${t("panel.export")}</button><button class="panel-command" data-panel-action="reload"><span>${icon("refresh-cw")}</span>${t("panel.reload")}</button></div>`);
}

function openTaskListPanel() {
  const items = $$(".thread-item").map((item) => `<button class="panel-session" data-switch-session="${escapeHtml(item.dataset.session)}"><strong>${escapeHtml(item.querySelector("strong")?.textContent || item.dataset.session)}</strong><small>${escapeHtml(item.querySelector("small")?.textContent || "")}</small></button>`).join("");
  openPanel(t("recentTasks"), `<div class="panel-session-list">${items}</div>`);
}

function exportChat() {
  const text = $("#messageList").innerText;
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.sessionId}.txt`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast(state.locale === "zh" ? "对话已导出" : "Chat exported");
}

function switchInspectorTab(tab) {
  $$(".inspector-tab").forEach((item) => item.classList.toggle("active", item.dataset.inspectorTab === tab));
  $("#overviewSection").hidden = tab !== "overview";
  $("#changesSection").hidden = tab !== "changes";
}

function setGameWideMode(enabled) {
  const wide = Boolean(enabled);
  const modal = $("#gameModal");
  const button = $("#gameWideMode");
  modal.classList.toggle("wide-mode", wide);
  button?.classList.toggle("active", wide);
  button?.setAttribute("aria-pressed", String(wide));
  if (button) {
    button.title = t(wide ? "game.compactMode" : "game.wideMode");
    button.querySelector("span").textContent = t(wide ? "game.compactMode" : "game.wideMode");
  }
  localStorage.setItem("minicc-game-wide-mode", wide ? "on" : "off");
}
function toggleGameWideMode() {
  setGameWideMode(!$("#gameModal").classList.contains("wide-mode"));
}
function openGame() {
  $("#gameModal").classList.add("show");
  $("#gameModal").setAttribute("aria-hidden", "false");
  setGameWideMode(localStorage.getItem("minicc-game-wide-mode") === "on");
  initGame();
}

function openGameWindow() { window.open(location.origin + location.pathname + "?arcade=1", "minicc-arcade", "popup,width=980,height=760"); }
function toggleGameFullscreen() { const card = $("#gameModal .game-card"); if (!document.fullscreenElement) card.requestFullscreen?.(); else document.exitFullscreen?.(); }
function closeGame() {
  const active = document.activeElement;
  if (active instanceof HTMLElement && $("#gameModal").contains(active)) active.blur();
  closeGameCodex();
  $("#gameModal").classList.remove("show");
  $("#gameModal").setAttribute("aria-hidden", "true");
  game.running = false;
  cancelAnimationFrame(game.frame);
  stopGameMusic();
  window.scrollTo(0, 0);
}

const codexState = { tab: "plants", plant: "peashooter", zombie: "walker" };
const codexPlantNames = { peashooter: "豌豆射手", sunflower: "向日葵", wallnut: "坚果墙", repeater: "双发射手", cherrybomb: "樱桃炸弹", icepeashooter: "寒冰射手", firepeashooter: "火焰射手", twinpea: "双发强化", kernelpult: "玉米投手", pumpkin: "南瓜头", spikeweed: "地刺", gloomshroom: "忧郁菇", potatomine: "土豆雷", threepeater: "三线射手", jalapeno: "火爆辣椒", magnetshroom: "磁力菇", garlic: "大蒜", squash: "窝瓜", gatlingpea: "机枪射手" };
const codexZombieNames = { walker: "普通僵尸", backup: "伴舞僵尸", roadblock: "路障僵尸", conehead: "路锥僵尸", imp: "小鬼僵尸", scout: "侦察僵尸", storm: "风暴僵尸", runner: "奔跑僵尸", polevault: "撑杆僵尸", bucket: "铁桶僵尸", football: "橄榄球僵尸", miner: "矿工僵尸", flag: "旗帜僵尸", dancer: "舞王僵尸", newspaper: "报纸僵尸", gargantuar: "巨人僵尸", witch: "女巫僵尸", dragon: "龙僵尸", shield: "护盾僵尸" };
const codexPlantIcons = { peashooter: "🌱", sunflower: "🌻", wallnut: "🥜", repeater: "🌿", cherrybomb: "🍒", icepeashooter: "❄️", firepeashooter: "🔥", twinpea: "🌱", kernelpult: "🌽", pumpkin: "🎃", spikeweed: "🌵", gloomshroom: "🍄", potatomine: "🥔", threepeater: "🌾", jalapeno: "🌶️", magnetshroom: "🧲", garlic: "🧄", squash: "🎃", gatlingpea: "🔫" };
const codexPlantSpecials = { peashooter: "发射普通豌豆，稳定输出。", sunflower: "每隔一段时间生产 25 阳光。", wallnut: "高生命值阻挡，拖延僵尸。", repeater: "每轮发射 2 发豌豆，并可穿透 1 个目标。", cherrybomb: "短延迟后在同一行 145 范围内直接消灭僵尸。", icepeashooter: "命中后减速 3200ms，并可穿透 1 个目标。", firepeashooter: "每发 2 点伤害并施加 2600ms 灼烧，灼烧伤害 3。", twinpea: "每轮发射 2 发强化豌豆，每发 2 点伤害。", kernelpult: "28% 概率用黄油定身，并可穿透 1 个目标。", pumpkin: "为同格植物提供 32 点护罩生命。", spikeweed: "攻击所在格附近 44 范围内的僵尸。", gloomshroom: "近身范围攻击并施加 900ms 减速。", potatomine: "1800ms 后布雷，在同一行 90 范围内爆炸。", threepeater: "同时攻击当前行、上行和下行。", jalapeno: "短延迟后消灭所在行的全部僵尸。", magnetshroom: "周期性吸走僵尸护甲或装备，不直接造成伤害。", garlic: "被咬后将僵尸改道到下一行。", squash: "接近时重击并直接消灭目标。", gatlingpea: "每轮连续发射 4 发豌豆，每发 1 点伤害。" };
const codexZombieSkills = { walker: "无额外技能，接触植物后啃食。", backup: "伴随舞王召唤，沿行啃食。", roadblock: "路障提供额外防护。", conehead: "路锥提供额外护甲。", imp: "快速移动并跳跃植物。", scout: "间歇冲刺并标记、诅咒附近植物。", storm: "周期性使同一行植物短暂失效。", runner: "沿行快速移动并间歇冲刺。", polevault: "遇到第一株植物时撑杆跳过。", bucket: "铁桶提供高额护甲。", football: "高护甲并可冲锋攻击。", miner: "地下潜行，接近防线后出土。", flag: "为同一行盟友提供移动速度加成。", dancer: "周期性召唤伴舞僵尸。", newspaper: "报纸被破坏后进入狂暴状态。", gargantuar: "缓慢推进，接触植物时重击并造成高额伤害。", witch: "标记并诅咒附近植物。", dragon: "喷吐火焰，对植物施加灼烧。", shield: "周期性恢复护盾。" };
function codexPlantInfo(type) {
  const profile = plantProfiles[type] || {};
  const damage = profile.damage ? `${profile.damage} 点/发` : ["cherrybomb", "jalapeno", "potatomine", "squash"].includes(type) ? "特殊/爆发伤害" : "0（功能型）";
  const target = profile.rows || type === "jalapeno" ? "群体" : ["cherrybomb", "potatomine", "squash"].includes(type) ? "范围爆发" : "单体";
  const range = profile.rows ? "当前行及相邻两行" : ["gloomshroom", "spikeweed"].includes(type) ? "近身（约 44）" : ["cherrybomb", "potatomine"].includes(type) ? "同一行范围" : type === "jalapeno" ? "整行" : "所在行直线/所在格";
  const usage = type === "sunflower" ? "放在后排，持续生产阳光。" : type === "wallnut" || type === "pumpkin" ? "放在僵尸路线前吸收伤害。" : `选中卡片后点击草坪格子，消耗 ${plantCost[type]} 阳光。`;
  return { name: codexPlantNames[type], icon: codexPlantIcons[type], health: plantHealth[type], cost: plantCost[type], damage, attack: profile.shots ? `${profile.shots} 发/轮` : type === "threepeater" ? "3 条线路" : "特殊逻辑", target, range, usage, special: codexPlantSpecials[type] || "按当前游戏逻辑发挥作用。", raw: Object.keys(profile).length ? JSON.stringify(profile) : "由独立游戏逻辑处理" };
}
function codexZombieInfo(type) {
  const profile = zombieProfiles[type];
  const movement = profile.burrow ? "地下潜行，接近防线后出土" : profile.vault ? "持杆前进，遇到植物时跳过" : profile.leap ? "快速前进并跳跃植物" : profile.dash ? "沿所在行移动并间歇冲刺" : profile.giant ? "缓慢直线推进" : "沿所在行向左直线移动";
  return { name: codexZombieNames[type], hp: profile.hp, armor: profile.armor || 0, speed: `${profile.speed.toFixed(3)} + 每波 ${profile.growth.toFixed(4)}`, attack: `${profile.attackInterval} ms`, score: profile.score, movement, skills: codexZombieSkills[type] };
}
function codexRows(rows) { return rows.map(([label, value]) => `<div class="codex-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join(""); }
function renderCodex() {
  const plants = codexState.tab === "plants";
  const keys = Object.keys(plants ? plantCost : zombieProfiles);
  const selected = codexState[plants ? "plant" : "zombie"];
  $("#codexPlantCount").textContent = `（${Object.keys(plantCost).length}）`;
  $("#codexZombieCount").textContent = `（${Object.keys(zombieProfiles).length}）`;
  $$(".codex-tab").forEach((tab) => { const active = tab.dataset.codexTab === codexState.tab; tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active)); });
  $("#codexEntryList").innerHTML = keys.map((key) => { const info = plants ? codexPlantInfo(key) : codexZombieInfo(key); return `<button class="codex-entry ${key === selected ? "active" : ""}" type="button" data-codex-entry="${key}"><span class="codex-entry-icon">${info.icon || "🧟"}</span><span>${escapeHtml(info.name)}</span></button>`; }).join("");
  const info = plants ? codexPlantInfo(selected) : codexZombieInfo(selected);
  $("#codexDetail").innerHTML = `<div class="codex-detail-title"><span class="codex-detail-icon">${info.icon || "🧟"}</span><div><span class="game-kicker">${plants ? "植物详情" : "僵尸详情"}</span><h4>${escapeHtml(info.name)}</h4></div></div>${plants ? `<dl class="codex-stats">${codexRows([["阳光消耗", `${info.cost} 阳光`], ["植物生命值", `${info.health} HP`], ["伤害", info.damage], ["攻击频率", info.attack], ["伤害类型", info.target], ["攻击范围", info.range]])}</dl><div class="codex-section"><strong>使用方法</strong><p>${escapeHtml(info.usage)}</p></div><div class="codex-section"><strong>特殊效果</strong><p>${escapeHtml(info.special)}</p></div><div class="codex-section"><strong>实际 profile 参数</strong><code>${escapeHtml(info.raw)}</code></div>` : `<dl class="codex-stats">${codexRows([["基础生命值", `${info.hp} HP`], ["护甲", `${info.armor} 点`], ["移动速度", info.speed], ["攻击间隔", info.attack], ["击退积分", info.score]])}</dl><div class="codex-health-bar" aria-label="僵尸基础生命值"><i style="width: 100%"></i></div><div class="codex-section"><strong>移动方式</strong><p>${escapeHtml(info.movement)}</p></div><div class="codex-section"><strong>特殊技能</strong><p>${escapeHtml(info.skills)}</p></div>`}`;
  $$(".codex-entry").forEach((entry) => entry.addEventListener("click", () => { codexState[plants ? "plant" : "zombie"] = entry.dataset.codexEntry; renderCodex(); }));
}
function openGameCodex(tab = "plants") { codexState.tab = tab; $("#gameCodexPanel").classList.add("show"); $("#gameCodexPanel").setAttribute("aria-hidden", "false"); renderCodex(); window.lucide?.createIcons(); }
function closeGameCodex() { const panel = $("#gameCodexPanel"); if (!panel) return; panel.classList.remove("show"); panel.setAttribute("aria-hidden", "true"); }

const MAX_WAVES = 10;
