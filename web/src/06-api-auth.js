// NOTE: 源文件分片（web/src/）。此文件由 `npm run build:web` 按序拼接生成，勿直接编辑。
async function requestJson(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && data.auth_required) {
        showAuthModal();
        throw new Error(state.locale === "zh" ? "需要访问 token，请在弹窗中粘贴后重试。" : "Access token required. Paste it in the dialog and retry.");
      }
      throw new Error(data.error || `${response.status} ${response.statusText}`);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，任务仍可在活动面板中查看。");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}
function updateLiveStream(loadingId, preview, target) {
  let stream = liveStreamStates.get(loadingId);
  if (!stream) {
    stream = { rendered: "", target: "", preview, frame: 0, lastPaint: 0 };
    liveStreamStates.set(loadingId, stream);
  }
  stream.preview = preview;
  stream.target = target;
  if (stream.frame) return;
  const paint = () => {
    stream.frame = 0;
    if (!stream.preview?.isConnected) {
      liveStreamStates.delete(loadingId);
      return;
    }
    if (stream.rendered === stream.target) return;
    stream.rendered = stream.target;
    // Streaming stays on the lightweight renderer so the 120ms throttle and
    // caret remain cheap; the finished answer gets the full Markdown pass in
    // addAssistantMessage once the task reaches a terminal state.
    stream.preview.innerHTML = `${formatLightText(streamTail(stream.target))}<span class="stream-caret" aria-hidden="true"></span>`;
  };
  stream.frame = window.setTimeout(paint, 120);
}

function timelineDetailKey(detail) {
  if (detail.matches("details.agent-round")) return `round:${detail.dataset.agentRound || ""}`;
  if (detail.matches("details.tool-event")) return `tool:${detail.dataset.toolEvent || ""}`;
  const owner = detail.closest("details.tool-event, details.agent-round, [data-stage-code]");
  if (!owner) return "";
  const ownerKey = owner.matches("details.tool-event")
    ? `tool:${owner.dataset.toolEvent || ""}`
    : owner.matches("details.agent-round")
      ? `round:${owner.dataset.agentRound || ""}`
      : `stage:${owner.dataset.stageCode || ""}`;
  const nestedIndex = [...owner.querySelectorAll("details")].indexOf(detail);
  return `nested:${ownerKey}:${nestedIndex}`;
}

function captureTimelineOpenDetails(timeline) {
  return new Set([...timeline.querySelectorAll("details[open]")].map(timelineDetailKey).filter(Boolean));
}

function restoreTimelineOpenDetails(timeline, openDetails) {
  if (!(openDetails instanceof Set)) return;
  timeline.querySelectorAll("details").forEach((detail) => { detail.open = openDetails.has(timelineDetailKey(detail)); });
}

function setTimelineDetails(timeline, open) {
  if (!timeline) return;
  timeline.querySelectorAll("details").forEach((detail) => { detail.open = open; });
}

function syncLiveEvents(loading, events, chatPosition = null) {
  if (!events.length) return false;
  let timeline = loading.querySelector(".tool-timeline");
  if (!timeline) {
    timeline = document.createElement("div");
    timeline.className = "tool-timeline";
    loading.querySelector(".message-body")?.append(timeline);
  }
  const previousCount = Number(loading.dataset.eventCount || 0);
  const fingerprint = events.map((event) => [
    eventSequence(event.sequence),
    event.item_id || event.event_id || "",
    event.kind || "",
    event.code || "",
    event.name || "",
    event.status || "",
    event.summary || "",
    typeof event.detail?.text === "string" ? event.detail.text.slice(0, 2400) : "",
  ].join("|")).join("\n");
  if (timeline.dataset.eventFingerprint === fingerprint) return false;
  const position = chatPosition || captureChatPosition();
  const openDetails = timeline.dataset.initialized === "true" ? captureTimelineOpenDetails(timeline) : null;
  timeline.innerHTML = eventTimelineMarkup(events, { animateFrom: previousCount });
  restoreTimelineOpenDetails(timeline, openDetails);
  timeline.dataset.initialized = "true";
  timeline.dataset.eventFingerprint = fingerprint;
  loading.dataset.eventCount = String(events.length);
  refreshIcons();
  if (!chatPosition) restoreChatPosition(position, false);
  return true;
}

function updateLiveTask(loadingId, data) {
  const loading = document.getElementById(loadingId);
  if (!loading) return;
  const chatPosition = captureChatPosition();
  const events = Array.isArray(data.events) ? data.events : [];
  let live = loading.querySelector("[data-live-task]");
  if (!live) {
    loading.querySelector(".message-body").insertAdjacentHTML("afterbegin", liveTaskMarkup(data));
    live = loading.querySelector("[data-live-task]");
  }
  const currentPhase = phaseClass(data);
  const phaseText = phaseLabel(data);
  const phaseClasses = ["queued", "planning", "tool", "answering", "merging", "completed", "failed", "cancelled", "interrupted"];
  live.classList.remove(...phaseClasses.map((phase) => `live-task-${phase}`));
  live.classList.add(`live-task-${currentPhase}`);
  live.dataset.phase = currentPhase;
  const progress = live.querySelector(".task-progress");
  if (progress) progress.dataset.phase = currentPhase;
  live.querySelector("[data-live-phase]")?.replaceChildren(document.createTextNode(phaseText));
  live.querySelector("[data-live-phase-label]")?.replaceChildren(document.createTextNode(phaseText));
  live.querySelector("[data-live-metrics]")?.replaceChildren(document.createTextNode(taskMetrics(data)));
  const preview = live.querySelector("[data-live-preview]");
  const streamText = String(data.stream_text || "");
  live.querySelector("[data-live-output-count]")?.replaceChildren(document.createTextNode(streamText ? `${compactNumber(streamText.length)} ${state.locale === "zh" ? "字符（仅显示最近内容）" : "chars (recent content)"}` : ""));
  if (preview) {
    if (streamText) updateLiveStream(loadingId, preview, streamText);
    else preview.innerHTML = `<span class="stream-empty">${escapeHtml(t("phase.waiting"))}</span>`;
  }
  syncLiveEvents(loading, events, chatPosition);
  updateTaskDuration(data, loadingId);
  if (isFocusedTask(data)) $("#pulseStatus").textContent = phaseText;
  updateTaskDock(data);
  restoreChatPosition(chatPosition, false);
}

function scheduleChangesRefresh() {
  window.clearTimeout(changeRefreshTimer);
  changeRefreshTimer = window.setTimeout(() => loadChanges(), 220);
}

function applyTaskEvent(taskId, envelope) {
  const binding = runningTasks.get(taskId);
  if (!binding || !envelope || typeof envelope !== "object") return null;
  const sequence = eventSequence(envelope.sequence);
  const eventId = String(envelope.event_id || "");
  const itemId = String(envelope.item_id || "");
  if (
    (sequence && (binding.seenSequences.has(sequence) || sequence <= eventSequence(binding.cursor)))
    || (eventId && binding.seenEventIds.has(eventId))
    || (itemId && binding.seenEventIds.has(`item:${itemId}`))
  ) return null;
  const payload = envelope.payload && typeof envelope.payload === "object" ? envelope.payload : {};
  const data = { ...(binding.data || {}) };
  const kind = String(envelope.kind || "");
  if (kind === "timeline") {
    const timelineEvent = { ...payload };
    if (eventId && !timelineEvent.event_id) timelineEvent.event_id = eventId;
    if (itemId && !timelineEvent.item_id) timelineEvent.item_id = itemId;
    if (sequence && !timelineEvent.sequence) timelineEvent.sequence = sequence;
    data.events = mergeTimelineEvents(data.events, [timelineEvent]);
  } else if (kind === "stream_delta") {
    if (payload.stream_text != null) data.stream_text = String(payload.stream_text || "");
    else if (payload.delta) data.stream_text = `${String(data.stream_text || "")}${String(payload.delta)}`;
    if (payload.stream_length != null) data.stream_length = Number(payload.stream_length) || String(data.stream_text || "").length;
    if (payload.phase) data.phase = String(payload.phase);
  } else if (kind === "state" || kind === "status") {
    if (payload.status) data.status = String(payload.status);
    if (payload.phase) data.phase = String(payload.phase);
    if (payload.finished_at) data.finished_at = payload.finished_at;
    if (payload.error !== undefined) data.error = payload.error;
    if (payload.cancel_reason !== undefined) data.cancel_reason = payload.cancel_reason;
  } else if (kind === "usage") {
    if (payload.tokens_used && typeof payload.tokens_used === "object") data.tokens_used = { ...payload.tokens_used };
    if (payload.metrics && typeof payload.metrics === "object") data.metrics = { ...payload.metrics };
    if (payload.usage && typeof payload.usage === "object") data.usage_by_turn = [...(data.usage_by_turn || []), { ...payload.usage }].slice(-64);
  } else if (kind === "context") {
    if (payload.context && typeof payload.context === "object") data.context = { ...payload.context };
  } else if (kind === "compaction") {
    if (payload.event && typeof payload.event === "object") data.compaction_events = [...(data.compaction_events || []), { ...payload.event }].slice(-64);
  } else if (kind === "result") {
    if (payload.answer !== undefined) data.answer = payload.answer;
    if (payload.error !== undefined) data.error = payload.error;
    data.result = { ...(data.result || {}), answer: data.answer, error: data.error };
  }
  if (payload.state_version != null) data.state_version = Math.max(Number(data.state_version) || 0, Number(payload.state_version) || 0);
  binding.cursor = Math.max(eventSequence(binding.cursor), sequence);
  data.event_cursor = binding.cursor;
  if (sequence) binding.seenSequences.add(sequence);
  if (eventId) binding.seenEventIds.add(eventId);
  binding.data = data;
  updateBoundTask(taskId, data, { skipSnapshotMerge: true });
  return data;
}

function updateBoundTask(taskId, data, options = {}) {
  const binding = runningTasks.get(taskId);
  if (!binding) return;
  const next = options.skipSnapshotMerge
    ? { ...data, session_id: data.session_id || binding.sessionId, workspace_path: data.workspace_path || binding.workspacePath }
    : applyTaskSnapshot(binding, data, { replaceEvents: true });
  binding.data = next;
  if (isCurrentTaskScope(next)) {
    syncTodoPanelFromEvents(next.events);
    if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, next, { scrollToLatest: false });
    updateLiveTask(binding.loadingId, next);
  }
  if (Array.isArray(next.events) && next.events.some((event) => ["write_file", "edit_file", "move", "delete"].includes(event.name))) scheduleChangesRefresh();
  return next;
}

function finishLiveTask(loadingId) {
  const stream = liveStreamStates.get(loadingId);
  if (stream?.frame) window.cancelAnimationFrame(stream.frame);
  liveStreamStates.delete(loadingId);
  const source = taskEventSources.get(loadingId);
  source?.close();
  taskEventSources.delete(loadingId);
}

function isTerminalTask(data) {
  return ["completed", "failed", "cancelled", "interrupted"].includes(data?.status);
}

async function completeTask(loadingId, data) {
  const taskId = data.task_id;
  if (finalizedTaskIds.has(taskId)) return data;
  finalizedTaskIds.add(taskId);
  const binding = runningTasks.get(taskId) || { taskId, sessionId: state.sessionId, workspacePath: state.workspacePath, loadingId };
  finishLiveTask(binding.loadingId || loadingId);
  stopTaskTimer(taskId);
  const finalData = data.status === "completed"
    ? data
    : { ...data, answer: data.answer || data.error || (data.status === "cancelled" ? "任务已取消。" : "任务失败。") };
  cacheTaskDetail(finalData);
  runningTasks.delete(taskId);
  if (taskBySession.get(taskSessionKey(binding.sessionId, binding.workspacePath)) === taskId) taskBySession.delete(taskSessionKey(binding.sessionId, binding.workspacePath));

  const currentScope = isCurrentTaskScope({
    task_id: taskId,
    session_id: binding.sessionId,
    workspace_path: binding.workspacePath,
  });
  if (currentScope) {
    addAssistantMessage(finalData, binding.loadingId || loadingId);
    const remaining = sessionTaskBindings(binding.sessionId, binding.workspacePath);
    if (remaining.length) {
      state.activeTaskId = remaining[remaining.length - 1].taskId;
      updateTaskDock(remaining[remaining.length - 1].data);
    } else {
      state.activeTaskId = null;
    }
    setBusy(remaining.length > 0);
  } else {
    const existing = cachedSessionView(binding.sessionId, binding.workspacePath) || presetMessageMarkup(binding.sessionId);
    const holder = document.createElement("div");
    holder.innerHTML = existing;
    const pending = holder.querySelector(`#${CSS.escape(binding.loadingId || loadingId)}`);
    if (pending) {
      const replacement = document.createElement("div");
      replacement.innerHTML = assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`);
      pending.replaceWith(replacement.firstElementChild);
    } else {
      holder.insertAdjacentHTML("beforeend", assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`));
    }
    const cacheKey = sessionViewKey(binding.sessionId, binding.workspacePath);
    const compactedMarkup = compactSessionMarkup(holder.innerHTML);
    sessionMarkup.set(cacheKey, compactedMarkup);
    try { localStorage.setItem(cacheKey, compactedMarkup); } catch { /* best effort */ }
  }
  if (finalData.status !== "completed") showToast(finalData.error || (finalData.status === "cancelled" ? "任务已取消" : "任务失败"));
  scheduleChangesRefresh();
  refreshFileTreeSoon(); // task finished: workspace files may have changed
  await loadTaskHistory();
  return finalData;
}

async function pollTask(taskId) {
  const binding = runningTasks.get(taskId);
  setTaskTransportStatus(taskId, "polling");
  let delay = 220;
  while (true) {
    try {
      const data = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000);
      updateBoundTask(taskId, data);
      if (isTerminalTask(data)) return completeTask(binding?.loadingId || "", data);
      delay = 220;
    } catch (error) {
      // The task is durable on the server. Keep watching through a short API
      // outage instead of converting a transport blip into a false failure.
      if (!runningTasks.has(taskId)) throw error;
      delay = Math.min(5000, Math.max(500, Math.round(delay * 1.6)));
    }
    await new Promise((resolve) => window.setTimeout(resolve, delay));
  }
}
