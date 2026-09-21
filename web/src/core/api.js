import { requestJson } from "./transport.js";
export { requestJson } from "./transport.js";
import { reduceTaskEvent } from "./task-reducer.js";
import { syncApprovalRequests } from "./approvals.js";
import { reconcileTimeline } from "../chat/timeline-dom.js";
// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { cacheTaskDetail, cacheSessionView, cachedSessionView, escapeHtml, formatLightText, loadTaskHistory, presetMessageMarkup } from "../chat/markdown.js";
import { loadChanges } from "../chat/stream.js";
import { t } from "./i18n.js";
import { $, MAX_RENDERED_TIMELINE_EVENTS, finalizedTaskIds, liveStreamStates, runningTasks, runtime, state, taskBySession, taskEventSources } from "./state.js";
import { refreshIcons } from "../icons.js";
import { addAssistantMessage, addLoadingMessage, applyTaskSnapshot, assistantMessageMarkup, captureChatPosition, compactNumber, eventTimelineMarkup, isCurrentTaskScope, isFocusedTask, liveTaskMarkup, phaseClass, phaseLabel, refreshFileTreeSoon, restoreChatPosition, sessionTaskBindings, setBusy, setTaskTransportStatus, showToast, stopTaskTimer, streamTail, syncTodoPanelFromEvents, taskMetrics, taskSessionKey, updateTaskDock, updateTaskDuration } from "../panels/index.js";

export function updateLiveStream(loadingId, preview, target) {
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

export function timelineDetailKey(detail) {
  if (detail.matches("details.agent-round")) return `round:${detail.dataset.agentRound || ""}`;
  if (detail.matches("details.tool-event")) return `tool:${detail.dataset.toolEvent || ""}`;
  const owner = detail.closest("details.tool-event, details.agent-round, [data-stage-code]");
  if (!owner) return "";
  const ownerKey = owner.matches("details.tool-event")
    ? `tool:${owner.dataset.toolEvent || ""}`
    : owner.matches("details.agent-round")
      ? `round:${owner.dataset.agentRound || ""}`
      : `stage:${owner.dataset.agentItem || owner.dataset.stageCode || ""}`;
  const nestedIndex = [...owner.querySelectorAll("details")].indexOf(detail);
  return `nested:${ownerKey}:${nestedIndex}`;
}

export function captureTimelineOpenDetails(timeline) {
  return new Set([...timeline.querySelectorAll("details[open]")].map(timelineDetailKey).filter(Boolean));
}

export function restoreTimelineOpenDetails(timeline, openDetails) {
  if (!(openDetails instanceof Set)) return;
  timeline.querySelectorAll("details").forEach((detail) => { detail.open = openDetails.has(timelineDetailKey(detail)); });
}

export function setTimelineDetails(timeline, open) {
  if (!timeline) return;
  timeline.querySelectorAll("details").forEach((detail) => { detail.open = open; });
}

const timelineRenderState = new WeakMap();
export function syncLiveEvents(loading, events, chatPosition = null) {
  if (!events.length) return false;
  let timeline = loading.querySelector(".tool-timeline");
  if (!timeline) {
    timeline = document.createElement("div");
    timeline.className = "tool-timeline";
    loading.querySelector(".message-body")?.append(timeline);
  }
  const previous = timelineRenderState.get(timeline);
  // Reducers replace the events array only for timeline changes. Token and
  // usage deltas must not serialize the entire tool history on every update.
  if (previous?.events === events && previous.locale === state.locale) return false;
  const previousCount = Number(loading.dataset.eventCount || 0);
  const fingerprint = `${state.locale}:${events.length}:${JSON.stringify(events.slice(-MAX_RENDERED_TIMELINE_EVENTS))}`;
  timelineRenderState.set(timeline, { events, locale: state.locale, fingerprint });
  if (previous?.fingerprint === fingerprint) return false;
  const position = chatPosition || captureChatPosition();
  const openDetails = timeline.dataset.initialized === "true" ? captureTimelineOpenDetails(timeline) : null;
  reconcileTimeline(timeline, eventTimelineMarkup(events, { animateFrom: previousCount }));
  restoreTimelineOpenDetails(timeline, openDetails);
  timeline.dataset.initialized = "true";
  loading.dataset.eventCount = String(events.length);
  refreshIcons(timeline);
  if (!chatPosition) restoreChatPosition(position, false);
  return true;
}

export function updateLiveTask(loadingId, data) {
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

export function scheduleChangesRefresh() {
  window.clearTimeout(runtime.changeRefreshTimer);
  runtime.changeRefreshTimer = window.setTimeout(() => loadChanges(), 220);
}

export function applyTaskEvent(taskId, envelope) {
  const binding = runningTasks.get(taskId);
  if (!binding || !envelope || typeof envelope !== "object") return null;
  const next = reduceTaskEvent(binding, envelope);
  if (!next) return null;
  Object.assign(binding, next);
  const data = next.data;
  updateBoundTask(taskId, data, { skipSnapshotMerge: true });
  return data;
}

export function updateBoundTask(taskId, data, options = {}) {
  const binding = runningTasks.get(taskId);
  if (!binding) return;
  const next = options.skipSnapshotMerge
    ? { ...data, session_id: data.session_id || binding.sessionId, workspace_path: data.workspace_path || binding.workspacePath }
    : applyTaskSnapshot(binding, data, { replaceEvents: true });
  binding.data = next;
  syncApprovalRequests(next.events);
  if (isCurrentTaskScope(next)) {
    syncTodoPanelFromEvents(next.events);
    if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, next, { scrollToLatest: false });
    updateLiveTask(binding.loadingId, next);
  }
  if (Array.isArray(next.events) && next.events.some((event) => ["write_file", "edit_file", "move", "delete"].includes(event.name))) scheduleChangesRefresh();
  return next;
}

export function finishLiveTask(loadingId) {
  const stream = liveStreamStates.get(loadingId);
  if (stream?.frame) window.clearTimeout(stream.frame);
  liveStreamStates.delete(loadingId);
  const source = taskEventSources.get(loadingId);
  source?.close();
  taskEventSources.delete(loadingId);
}

export function isTerminalTask(data) {
  return ["completed", "failed", "cancelled", "interrupted"].includes(data?.status);
}

export async function completeTask(loadingId, data) {
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
    cacheSessionView(binding.sessionId, holder.innerHTML, binding.workspacePath);
  }
  if (finalData.status !== "completed") showToast(finalData.error || (finalData.status === "cancelled" ? "任务已取消" : "任务失败"));
  scheduleChangesRefresh();
  refreshFileTreeSoon(); // task finished: workspace files may have changed
  await loadTaskHistory();
  return finalData;
}

export async function pollTask(taskId) {
  const binding = runningTasks.get(taskId);
  setTaskTransportStatus(taskId, "polling");
  let delay = 220;
  while (true) {
    if (!runningTasks.has(taskId)) return null;
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
