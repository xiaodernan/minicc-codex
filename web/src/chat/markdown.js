// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { requestJson } from "../core/transport.js";
import { storeSessionMarkup } from "../core/session-cache.js";
import { captureViewScope, isWorkspaceScopeCurrent, isViewScopeCurrent } from "../core/scope.js";
import { t } from "../core/i18n.js";
import { $, $$, MAX_SESSION_VIEW_CHARS, SESSION_VIEW_PREFIX, renderedHistoryKeys, runtime, sessionMarkup, state, taskDetailLoads, taskDetailsById, taskHistoryBySession, taskHistoryListBySession } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { captureChatPosition, decorateUserRewindButtons, eventTimelineMarkup, eventTimelineSummary, isSessionBusy, latestTodosFromEvents, phaseLabel, rawOutputMarkup, renderTodoPanel, renderVerification, restoreChatPosition, restoreSessionTask, setConnection, taskMetrics, updateSessionStatus } from "../panels/index.js";

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// ---------------------------------------------------------------------------
// Markdown rendering pipeline (vendored marked@12 + highlight.js 11.9, local
// first with no runtime CDN). `formatText` keeps its original name and
// signature; it now renders commercial-grade Markdown (tables, block quotes,
// nested lists, links, fenced code with syntax highlighting).
//
// XSS strategy: `escapeMarkdownSource` escapes every raw `<` (and `&`) before
// marked ever sees the input, so model-produced HTML degrades to visible text
// instead of live markup. `>` is intentionally kept so block quotes still
// parse; a bare `>` outside a tag is inert text in HTML. Renderers escape all
// generated attributes and only allow http/https/mailto/relative URLs.
// ---------------------------------------------------------------------------

export let markdownVendorWarned = false;

export function markdownVendorReady() {
  if (typeof marked !== "undefined") return true;
  if (!markdownVendorWarned) {
    markdownVendorWarned = true;
    console.warn("[minicc] web/vendor marked/highlight.js unavailable; using the lightweight fallback renderer.");
  }
  return false;
}

export function escapeMarkdownSource(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;");
}

// marked receives pre-escaped text, so code token text is entity-encoded;
// decode back to plain text before handing it to highlight.js, which escapes
// its own output. The &amp; replacement must run last to avoid double decoding.
export function decodeMarkdownEntities(value) {
  return String(value ?? "")
    .replaceAll("&#039;", "'")
    .replaceAll("&#39;", "'")
    .replaceAll("&quot;", '"')
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

export function safeMarkdownUrl(href) {
  const value = String(href || "").trim();
  if (!value) return "";
  if (value.startsWith("#")) return value;
  if (!/^[a-z][a-z0-9+.-]*:/i.test(value)) return value; // scheme-less = relative path
  return /^(https?:|mailto:)/i.test(value) ? value : "";
}

export function highlightFencedCode(code, language) {
  const source = decodeMarkdownEntities(code);
  if (typeof hljs !== "undefined") {
    try {
      if (language && hljs.getLanguage(language)) {
        return hljs.highlight(source, { language, ignoreIllegals: true }).value;
      }
      if (!language && source.length <= 20000) {
        return hljs.highlightAuto(source).value;
      }
    } catch {
      // Highlighting is cosmetic; fall through to the escaped plain text.
    }
  }
  return escapeHtml(source);
}

export function configureMarkdownEngine() {
  if (typeof marked === "undefined" || configureMarkdownEngine.ready) return;
  configureMarkdownEngine.ready = true;
  const tokenOf = (value) => (value && typeof value === "object" ? value : null);
  try {
    marked.use({
      gfm: true,
      breaks: true,
      renderer: {
        // marked@12 passes token objects; the legacy signature passes plain
        // arguments, so both shapes are accepted.
        code(tokenOrCode, infostring) {
          const token = tokenOf(tokenOrCode);
          const raw = String(token ? token.text : tokenOrCode ?? "");
          const language = String((token ? token.lang : infostring) || "").trim().split(/\s+/)[0].toLowerCase();
          const highlighted = highlightFencedCode(raw, language);
          const classes = language ? `hljs language-${escapeHtml(language)}` : "hljs";
          return `<pre><code class="${classes}">${highlighted}</code></pre>`;
        },
        link(tokenOrHref, titleOrTitle, text) {
          const token = tokenOf(tokenOrHref);
          const href = safeMarkdownUrl(String(token ? token.href : tokenOrHref || ""));
          const title = token ? token.title : titleOrTitle;
          const label = token
            ? (typeof this?.parser?.parseInline === "function" ? this.parser.parseInline(token.tokens || []) : escapeHtml(token.text || ""))
            : escapeHtml(text ?? "");
          if (!href) return label;
          return `<a href="${escapeHtml(href)}"${title ? ` title="${escapeHtml(title)}"` : ""} target="_blank" rel="noreferrer noopener">${label}</a>`;
        },
        image(tokenOrHref, titleOrTitle, text) {
          const token = tokenOf(tokenOrHref);
          const href = safeMarkdownUrl(String(token ? token.href : tokenOrHref || ""));
          const alt = String(token ? token.text : text ?? "");
          const title = token ? token.title : titleOrTitle;
          if (!href) return escapeHtml(alt);
          return `<img src="${escapeHtml(href)}" alt="${escapeHtml(alt)}"${title ? ` title="${escapeHtml(title)}"` : ""} loading="lazy" />`;
        },
      },
    });
  } catch {
    // A broken engine configuration must never take message rendering down.
  }
}

export function renderMarkdown(source) {
  configureMarkdownEngine();
  return marked.parse(source, { async: false, gfm: true, breaks: true });
}
export function formatText(value) {
  const source = String(value ?? "");
  if (!markdownVendorReady()) return formatLightText(source);
  try {
    // Pre-escaping the whole document is the XSS boundary; marked then parses
    // the sanitized Markdown source (tables, quotes, lists survive intact).
    return renderMarkdown(escapeMarkdownSource(source));
  } catch {
    return formatLightText(source);
  }
}

// Legacy lightweight renderer. Kept for the streaming preview path (it stays
// cheap under the 120ms throttle) and as the vendor-degradation fallback.
export function formatLightText(value) {
  const codeBlocks = [];
  let formatted = escapeHtml(value).replace(/```([\s\S]*?)```/g, (_match, code) => {
    const token = `__MINICC_CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push(`<pre><code>${code}</code></pre>`);
    return token;
  });
  formatted = formatted
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/^-\s+/gm, "&bull; ")
    .replace(/\n/g, "<br />");
  return formatted.replace(/__MINICC_CODE_BLOCK_(\d+)__/g, (_match, index) => codeBlocks[Number(index)]);
}

export function formatBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export function safeImageDataUrl(value) {
  const url = String(value || "");
  return /^data:image\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+$/i.test(url) ? url : "";
}

export function attachmentMarkup(items, className = "message-attachments") {
  if (!Array.isArray(items) || !items.length) return "";
  return `<div class="${className}">${items.map((item, index) => {
    const name = String(item.name || `image-${index + 1}`);
    const dataUrl = safeImageDataUrl(item.data_url);
    const preview = dataUrl
      ? `<img src="${escapeHtml(dataUrl)}" alt="${escapeHtml(name)}" />`
      : `<span class="attachment-placeholder">${icon("image")}</span>`;
    const remove = item.id ? `<button type="button" class="attachment-remove" data-remove-attachment="${escapeHtml(item.id)}" aria-label="Remove ${escapeHtml(name)}" title="Remove">${icon("x")}</button>` : "";
    return `<div class="image-attachment">${preview}<span class="image-attachment-copy"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(formatBytes(item.size_bytes))}</small></span>${remove}</div>`;
  }).join("")}</div>`;
}

export function sessionViewKey(sessionId, workspacePath = state.workspacePath) {
  const workspace = encodeURIComponent(workspacePath || "default");
  return `${SESSION_VIEW_PREFIX}${workspace}:${encodeURIComponent(sessionId)}`;
}

export function compactSessionMarkup(markup) {
  const source = String(markup || "");
  if (source.length <= MAX_SESSION_VIEW_CHARS) return source;
  const holder = document.createElement("div");
  holder.innerHTML = source;
  // Keep the latest messages readable while preventing localStorage from
  // becoming a second, unbounded transcript database.
  let remaining = source.length;
  while (holder.firstChild && remaining > MAX_SESSION_VIEW_CHARS) {
    const node = holder.firstChild;
    remaining -= node.nodeType === 1 ? node.outerHTML.length : (node.textContent || "").length;
    node.remove();
  }
  const compacted = holder.innerHTML;
  // One oversized message is rehydrated from durable history instead of
  // caching malformed HTML or exceeding the browser's storage quota.
  return compacted.length <= MAX_SESSION_VIEW_CHARS ? compacted : "";
}

export function cacheSessionView(sessionId, markup, workspacePath = state.workspacePath) {
  const cacheKey = sessionViewKey(sessionId, workspacePath);
  const compacted = compactSessionMarkup(markup);
  if (compacted) sessionMarkup.set(cacheKey, compacted);
  else sessionMarkup.delete(cacheKey);
  storeSessionMarkup(cacheKey, compacted);
}

export function persistSessionView(sessionId = state.sessionId, workspacePath = state.workspacePath) {
  const messageList = $("#messageList");
  if (!messageList) return;
  cacheSessionView(sessionId, messageList.innerHTML, workspacePath);
}

export function cachedSessionView(sessionId, workspacePath = state.workspacePath) {
  const cacheKey = sessionViewKey(sessionId, workspacePath);
  if (sessionMarkup.has(cacheKey)) return sessionMarkup.get(cacheKey);
  try {
    const markup = compactSessionMarkup(localStorage.getItem(cacheKey));
    if (markup) {
      sessionMarkup.set(cacheKey, markup);
      return markup;
    }
  } catch {
    // Fall back to the in-memory view when storage is unavailable.
  }
  return null;
}

export function emptySessionMarkup() {
  return `<div class="empty-session"><span class="empty-mark" aria-hidden="true">${icon("sparkles")}</span><strong>${escapeHtml(t("session.emptyTitle"))}</strong><span>${escapeHtml(t("session.emptyHint"))}</span><div class="empty-actions">${["explore", "fix", "verify"].map((key) => `<button type="button" data-start-action="${key}"><strong>${escapeHtml(t(`start.${key}`))}</strong><span>${escapeHtml(t(`start.${key}Hint`))}</span>${icon("arrow-up-right")}</button>`).join("")}</div></div>`;
}

export function presetMessageMarkup(sessionId) {
  return emptySessionMarkup();
}

export function executionTrailMarkup(eventMarkup, events) {
  if (!eventMarkup) return "";
  const expandLabel = t("tool.expandAll");
  const collapseLabel = t("tool.collapseAll");
  return `<section class="execution-trail" data-agent-timeline data-agent-thread="local"><div class="execution-trail-head"><div class="execution-trail-title"><span class="execution-trail-icon">${icon("list-checks")}</span><span><strong>${escapeHtml(state.locale === "zh" ? "执行脉络与证据" : "Execution trail and evidence")}</strong><small>${escapeHtml(eventTimelineSummary(events))}</small></span></div><div class="execution-trail-actions"><button type="button" class="timeline-control" data-timeline-toggle="expand" aria-label="${escapeHtml(expandLabel)}" title="${escapeHtml(expandLabel)}">${icon("chevrons-down")}<span>${escapeHtml(expandLabel)}</span></button><button type="button" class="timeline-control" data-timeline-toggle="collapse" aria-label="${escapeHtml(collapseLabel)}" title="${escapeHtml(collapseLabel)}">${icon("chevrons-up")}<span>${escapeHtml(collapseLabel)}</span></button></div></div><div class="tool-timeline">${eventMarkup}</div></section>`;
}

export function taskHistoryMarkup(task) {
  const prompt = task.prompt || task.preview || "";
  const answer = task.answer || task.error || "任务没有返回可交付文字。";
  const rawStream = !task.answer && task.stream_text ? rawOutputMarkup(task.stream_text) : "";
  const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
  const taskAnchor = escapeHtml(`task-${task.task_id || task.created_at || prompt.slice(0, 40)}`);
  const attachments = attachmentMarkup(task.attachments || []);
  const batchSummary = task.task_kind === "batch" && Array.isArray(task.children)
    ? `<div class="batch-child-summary"><div class="batch-child-heading"><strong>${escapeHtml(state.locale === "zh" ? "分层并行结果" : "Layered parallel results")}</strong><small>${escapeHtml(state.locale === "zh" ? "只读子任务并行 → 主 Agent 合并与复核" : "Readonly children in parallel -> parent merge and review")}</small></div>${task.children.map((child, index) => {
        const metrics = child.metrics && typeof child.metrics === "object" ? child.metrics : {};
        const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
        const answer = String(child.answer || child.error || child.stream_text || "").replace(/\s+/g, " ").trim();
        const evidence = (Array.isArray(child.events) ? child.events : []).filter((event) => event?.summary).slice(-2).map((event) => event.summary).join("；");
        return `<details class="batch-child"><summary><span class="task-state ${child.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(child.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(`${t("batch.task")} ${index + 1}`)}</strong><small>${escapeHtml(`${phaseLabel(child)} · ${budget.turns || 0} turns · ${budget.tool_calls || 0} tools`)}</small><span class="batch-child-chevron">${icon("chevron-down")}</span></summary><div class="batch-child-detail">${answer ? `<p>${escapeHtml(answer.slice(0, 900))}</p>` : ""}${evidence ? `<small>${escapeHtml(evidence.slice(0, 700))}</small>` : ""}</div></details>`;
      }).join("")}</div>`
    : "";
  const execution = executionTrailMarkup(events, task.events || []);
  return `<article class="message user-message" data-chat-anchor="${taskAnchor}-prompt"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(task.created_at || t("message.now"))}</time><button type="button" class="rewind-to-here" data-user-index="0">${escapeHtml(t("rewind.toHere"))}</button></div><div class="message-body"><div class="message-text">${formatText(prompt)}</div>${attachments}</div></article><article class="message assistant-message" data-chat-anchor="${taskAnchor}-answer"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>${escapeHtml(task.finished_at || task.created_at || t("message.now"))}</time></div><div class="message-body"><div class="history-result-head"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div>${execution}<div class="answer-callout">${formatText(answer)}</div>${batchSummary}${rawStream}</div></article>`;
}

export function taskHistoryListMarkup(tasks) {
  return (Array.isArray(tasks) ? [...tasks].reverse() : []).map((task) => taskHistoryMarkup(task)).join("");
}

export function taskHistoryKey(task) {
  if (Array.isArray(task)) return task.map((item) => taskHistoryKey(item)).join("|");
  return [
    task?.task_id || "",
    task?.status || "",
    task?.phase || "",
    task?.finished_at || "",
    String(task?.answer || "").length,
    String(task?.stream_text || "").length,
    Number(task?.stream_length || 0),
    Number(task?.answer_length || 0),
    Number(task?.event_cursor || 0),
    Number(task?.state_version || 0),
    Array.isArray(task?.events) ? task.events.length : Number(task?.event_count || 0),
  ].join(":");
}

export function cacheTaskDetail(task) {
  if (!task?.task_id || task.summary_only) return;
  taskDetailsById.delete(task.task_id);
  taskDetailsById.set(task.task_id, task);
  while (taskDetailsById.size > 12) taskDetailsById.delete(taskDetailsById.keys().next().value);
}

export async function hydrateTaskForSession(taskId, sessionId) {
  if (!taskId) return null;
  if (taskDetailsById.has(taskId)) return taskDetailsById.get(taskId);
  if (!taskDetailLoads.has(taskId)) {
    const scope = captureViewScope();
    const load = requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000)
      .then((task) => {
        if (!isWorkspaceScopeCurrent(scope)) return task;
        cacheTaskDetail(task);
        const items = taskHistoryListBySession.get(sessionId) || [];
        const merged = items.map((item) => item.task_id === task.task_id ? task : item);
        if (!merged.some((item) => item.task_id === task.task_id)) merged.unshift(task);
        taskHistoryListBySession.set(sessionId, merged);
        taskHistoryBySession.set(sessionId, task);
        if (state.sessionId === sessionId && !isSessionBusy(sessionId)) renderSession(sessionId);
        return task;
      })
      .finally(() => { if (taskDetailLoads.get(taskId) === load) taskDetailLoads.delete(taskId); });
    taskDetailLoads.set(taskId, load);
  }
  return taskDetailLoads.get(taskId);
}

export function renderSession(sessionId, options = {}) {
  const scope = captureViewScope();
  const area = $("#chatArea");
  const chatPosition = captureChatPosition(area);
  if (chatPosition && options.followLatest === true) chatPosition.followLatest = true;
  const history = taskHistoryBySession.get(sessionId);
  const historyItems = taskHistoryListBySession.get(sessionId);
  const defaultTitle = state.locale === "zh" ? "新任务" : "New task";
  const defaultSubtitle = state.locale === "zh" ? "为下一次修改准备一个干净上下文。" : "A clean context for the next change.";
  $("#sessionTitle").textContent = history ? String(history.preview || history.prompt || defaultTitle).slice(0, 72) : defaultTitle;
  $("#sessionSubtitle").textContent = history ? phaseLabel(history) : defaultSubtitle;
  const markup = history && !history.summary_only
    ? taskHistoryListMarkup(historyItems?.length ? historyItems : [history])
    : (cachedSessionView(sessionId) || emptySessionMarkup());
  if (markup) $("#messageList").innerHTML = markup;
  decorateUserRewindButtons();
  updateSessionStatus(history);
  renderVerification(history || null);
  if (history) renderedHistoryKeys.set(sessionId, taskHistoryKey(historyItems?.length ? historyItems : history));
  else renderedHistoryKeys.delete(sessionId);
  // Restore the task plan from the last todo_write event in this session's
  // durable history; hide the section when no checklist can be recovered.
  const todoSource = historyItems?.length ? [...historyItems].reverse() : (history ? [history] : []);
  runtime.latestTodos = latestTodosFromEvents(todoSource.flatMap((item) => Array.isArray(item?.events) ? item.events : []));
  renderTodoPanel();
  refreshIcons();
  // Preserve the visible message across background history refreshes.
  restoreChatPosition(chatPosition);
  window.requestAnimationFrame(() => { if (isViewScopeCurrent(scope)) restoreSessionTask(sessionId); });
}

export function taskDotClass(status) {
  if (status === "completed") return "mint";
  if (["failed", "cancelled", "interrupted"].includes(status)) return "amber";
  return "coral";
}

export function renderTaskHistory(tasks) {
  const list = $("#threadList");
  if (!list) return;
  const previousScrollTop = list.scrollTop;
  const wasAtTop = previousScrollTop <= 4;
  const normalizedTasks = Array.isArray(tasks)
    ? tasks.map((task) => {
        const cached = taskDetailsById.get(task?.task_id);
        return cached ? { ...cached, ...task, summary_only: false } : task;
      })
    : [];
  const nextTaskListKey = normalizedTasks.map((task) => taskHistoryKey(task)).join("|");
  taskHistoryBySession.clear();
  taskHistoryListBySession.clear();
  for (const task of normalizedTasks) {
    const sessionId = String(task.session_id || task.task_id || "web-latest");
    if (!taskHistoryBySession.has(sessionId)) taskHistoryBySession.set(sessionId, task);
    if (!taskHistoryListBySession.has(sessionId)) taskHistoryListBySession.set(sessionId, []);
    taskHistoryListBySession.get(sessionId).push(task);
  }
  const listChanged = runtime.renderedTaskListKey !== nextTaskListKey || list.dataset.historyLoaded !== "true";
  if (!normalizedTasks.length) {
    $("#taskNavCount").textContent = "0";
    if (listChanged) list.innerHTML = `<div class="thread-empty">${escapeHtml(t("tasks.noHistory"))}</div>`;
    runtime.renderedTaskListKey = nextTaskListKey;
    list.dataset.historyLoaded = "true";
    return;
  }
  const visible = normalizedTasks.slice(0, 30);
  if (listChanged) {
    list.innerHTML = visible.map((task) => {
      const sessionId = String(task.session_id || task.task_id || "web-latest");
      const title = String(task.preview || task.prompt || task.task_id || "Task").replace(/\s+/g, " ").trim();
      const status = phaseLabel(task);
      const detail = `${status} · ${task.task_id || ""}`;
      return `<button class="thread-item ${sessionId === state.sessionId ? "active" : ""}" data-session="${escapeHtml(sessionId)}" data-task-id="${escapeHtml(task.task_id || "")}">
        <span class="thread-dot ${taskDotClass(task.status)}"></span>
        <span class="thread-copy"><strong>${escapeHtml(title.slice(0, 72))}</strong><small>${escapeHtml(detail)}</small></span>
        ${icon("chevron-right")}
      </button>`;
    }).join("");
  } else {
    $$(".thread-item").forEach((item) => item.classList.toggle("active", item.dataset.session === state.sessionId));
  }
  runtime.renderedTaskListKey = nextTaskListKey;
  list.dataset.historyLoaded = "true";
  $("#taskNavCount").textContent = String(normalizedTasks.length);
  // A user-created session is intentionally allowed to have no history yet.
  // Do not replace it with the newest durable task during the 5s refresh loop.
  const currentHistory = taskHistoryBySession.get(state.sessionId);
  if (currentHistory?.summary_only && currentHistory.task_id) {
    hydrateTaskForSession(currentHistory.task_id, state.sessionId).catch(() => {});
  } else if (
    currentHistory
    && !isSessionBusy(state.sessionId)
    && renderedHistoryKeys.get(state.sessionId) !== taskHistoryKey(taskHistoryListBySession.get(state.sessionId) || currentHistory)
  ) {
    renderSession(state.sessionId);
  }
  if (listChanged) {
    refreshIcons();
    window.requestAnimationFrame(() => {
      list.scrollTop = wasAtTop ? 0 : Math.min(previousScrollTop, Math.max(0, list.scrollHeight - list.clientHeight));
    });
  }
}

export function loadTaskHistory() {
  const path = state.workspacePath;
  const version = runtime.workspaceVersion;
  const pending = runtime.historyPending;
  if (pending?.path === path && pending.version === version) return pending.promise;
  const request = runtime.historyRequest = (runtime.historyRequest || 0) + 1;
  const promise = (async () => {
    try {
      const query = path ? "&workspace=" + encodeURIComponent(path) : "";
      const data = await requestJson("/api/tasks?limit=100" + query);
      if (path !== state.workspacePath || version !== runtime.workspaceVersion || request !== runtime.historyRequest) return;
      if (state.connection === false) setConnection(true);
      renderTaskHistory(data.tasks || []);
      return data.tasks || [];
    } catch {
      // Static demo sessions remain available when the task index is offline.
    } finally {
      if (runtime.historyPending?.request === request) runtime.historyPending = null;
    }
  })();
  runtime.historyPending = { path, version, request, promise };
  return promise;
}
