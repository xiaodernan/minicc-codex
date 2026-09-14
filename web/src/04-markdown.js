// NOTE: 源文件分片（web/src/）。此文件由 `npm run build:web` 按序拼接生成，勿直接编辑。
function renderMarkdown(source) {
  configureMarkdownEngine();
  return marked.parse(source, { async: false, gfm: true, breaks: true });
}
function formatText(value) {
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
function formatLightText(value) {
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

function formatBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function safeImageDataUrl(value) {
  const url = String(value || "");
  return /^data:image\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+$/i.test(url) ? url : "";
}

function attachmentMarkup(items, className = "message-attachments") {
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

function icon(name) {
  return `<i data-lucide="${name}"></i>`;
}

const LOCAL_ICON_GLYPHS = {
  "panel-left-close": "‹", plus: "+", search: "⌕", "message-square": "□", "layout-grid": "▦",
  megaphone: "◢", history: "↶", "gamepad-2": "◇", "more-horizontal": "•••", "chevron-right": "›",
  "folder-git-2": "□", "settings-2": "⚙", "panel-left": "‹", "brain-circuit": "✦", sun: "☼",
  maximize: "↗", "panel-right": "›", "arrow-down": "↓", "list-checks": "☷", "chevrons-down": "⇵",
  "chevrons-up": "⇳", "sparkles": "✦", "alert-triangle": "!", "alert-circle": "!", check: "✓",
  lock: "□", "globe-2": "◎", "test-tube-2": "◈", "git-branch": "⑂", "file-search-2": "⌕",
  "layers-3": "▤", "chevron-down": "⌄", "image": "▧", x: "×", "scan-line": "⌁", route: "⌁",
  "scan-search": "⌕", play: "▶", paperclip: "⌇", "wand-sparkles": "✦", square: "■",
  "arrow-up": "↑", "refresh-cw": "↻", activity: "•", radio: "◉", "shield-check": "◇",
  "external-link": "↗", "layout-dashboard": "▦", "book-open": "▤", "maximize-2": "↗",
  "panel-right-close": "›", "file-code-2": "□", "rotate-ccw": "↶", folder: "▤", "folder-open": "▦", file: "▪",
};

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
  else {
    // The workbench is local-first. Keep controls legible when an optional
    // icon package is unavailable or a browser has no network access.
    document.querySelectorAll("[data-lucide]").forEach((node) => {
      if (node.dataset.iconFallback === "true") return;
      const name = String(node.dataset.lucide || "");
      node.textContent = LOCAL_ICON_GLYPHS[name] || "•";
      node.classList.add("icon-fallback");
      node.dataset.iconFallback = "true";
      node.setAttribute("aria-hidden", "true");
    });
  }
}

function sessionViewKey(sessionId, workspacePath = state.workspacePath) {
  const workspace = encodeURIComponent(workspacePath || "default");
  return `${SESSION_VIEW_PREFIX}${workspace}:${encodeURIComponent(sessionId)}`;
}

function compactSessionMarkup(markup) {
  const source = String(markup || "");
  if (source.length <= MAX_SESSION_VIEW_CHARS) return source;
  const holder = document.createElement("div");
  holder.innerHTML = source;
  // Keep the latest messages readable while preventing localStorage from
  // becoming a second, unbounded transcript database.
  while (holder.children.length > 2 && holder.innerHTML.length > MAX_SESSION_VIEW_CHARS) {
    holder.firstElementChild?.remove();
  }
  return holder.innerHTML;
}

function persistSessionView(sessionId = state.sessionId, workspacePath = state.workspacePath) {
  const messageList = $("#messageList");
  if (!messageList) return;
  const markup = compactSessionMarkup(messageList.innerHTML);
  const cacheKey = sessionViewKey(sessionId, workspacePath);
  sessionMarkup.set(cacheKey, markup);
  try {
    localStorage.setItem(cacheKey, markup);
  } catch {
    // Storage quota or privacy mode should not interrupt an agent run.
  }
}

function cachedSessionView(sessionId, workspacePath = state.workspacePath) {
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

function presetMessageMarkup(sessionId) {
  const preset = SESSION_PRESETS[sessionId];
  if (!preset) {
    return `<article class="message assistant-message"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div><div class="message-body"><p>Ready when you are. I will inspect the workspace before making a plan.</p></div></article>`;
  }
  const events = eventTimelineMarkup(preset.events || []);
  const execution = executionTrailMarkup(events, preset.events || []);
  return `<article class="message user-message"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>You</strong><time>now</time></div><div class="message-body"><div class="message-text">${formatText(preset.user)}</div></div></article><article class="message assistant-message"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div><div class="message-body">${execution}<div class="message-text">${formatText(preset.answer)}</div></div></article>`;
}

function executionTrailMarkup(eventMarkup, events) {
  if (!eventMarkup) return "";
  const expandLabel = t("tool.expandAll");
  const collapseLabel = t("tool.collapseAll");
  return `<section class="execution-trail" data-agent-timeline data-agent-thread="local"><div class="execution-trail-head"><div class="execution-trail-title"><span class="execution-trail-icon">${icon("list-checks")}</span><span><strong>${escapeHtml(state.locale === "zh" ? "执行脉络与证据" : "Execution trail and evidence")}</strong><small>${escapeHtml(eventTimelineSummary(events))}</small></span></div><div class="execution-trail-actions"><button type="button" class="timeline-control" data-timeline-toggle="expand" aria-label="${escapeHtml(expandLabel)}" title="${escapeHtml(expandLabel)}">${icon("chevrons-down")}<span>${escapeHtml(expandLabel)}</span></button><button type="button" class="timeline-control" data-timeline-toggle="collapse" aria-label="${escapeHtml(collapseLabel)}" title="${escapeHtml(collapseLabel)}">${icon("chevrons-up")}<span>${escapeHtml(collapseLabel)}</span></button></div></div><div class="tool-timeline">${eventMarkup}</div></section>`;
}

function taskHistoryMarkup(task) {
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
  return `<article class="message user-message" data-chat-anchor="${taskAnchor}-prompt"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(task.created_at || t("message.now"))}</time></div><div class="message-body"><div class="message-text">${formatText(prompt)}</div>${attachments}</div></article><article class="message assistant-message" data-chat-anchor="${taskAnchor}-answer"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>${escapeHtml(task.finished_at || task.created_at || t("message.now"))}</time></div><div class="message-body"><div class="history-result-head"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div>${execution}<div class="answer-callout">${formatText(answer)}</div>${batchSummary}${rawStream}</div></article>`;
}

function taskHistoryListMarkup(tasks) {
  return (Array.isArray(tasks) ? [...tasks].reverse() : []).map((task) => taskHistoryMarkup(task)).join("");
}

function taskHistoryKey(task) {
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

function cacheTaskDetail(task) {
  if (!task?.task_id || task.summary_only) return;
  taskDetailsById.delete(task.task_id);
  taskDetailsById.set(task.task_id, task);
  while (taskDetailsById.size > 12) taskDetailsById.delete(taskDetailsById.keys().next().value);
}

async function hydrateTaskForSession(taskId, sessionId) {
  if (!taskId) return null;
  if (taskDetailsById.has(taskId)) return taskDetailsById.get(taskId);
  if (!taskDetailLoads.has(taskId)) {
    const load = requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000)
      .then((task) => {
        cacheTaskDetail(task);
        const items = taskHistoryListBySession.get(sessionId) || [];
        const merged = items.map((item) => item.task_id === task.task_id ? task : item);
        if (!merged.some((item) => item.task_id === task.task_id)) merged.unshift(task);
        taskHistoryListBySession.set(sessionId, merged);
        taskHistoryBySession.set(sessionId, task);
        if (state.sessionId === sessionId && !isSessionBusy(sessionId)) renderSession(sessionId);
        return task;
      })
      .finally(() => taskDetailLoads.delete(taskId));
    taskDetailLoads.set(taskId, load);
  }
  return taskDetailLoads.get(taskId);
}

function renderSession(sessionId, options = {}) {
  const area = $("#chatArea");
  const chatPosition = captureChatPosition(area);
  if (chatPosition && options.followLatest === true) chatPosition.followLatest = true;
  const preset = SESSION_PRESETS[sessionId];
  const history = taskHistoryBySession.get(sessionId);
  const historyItems = taskHistoryListBySession.get(sessionId);
  const defaultTitle = state.locale === "zh" ? "新任务" : "New task";
  const defaultSubtitle = state.locale === "zh" ? "为下一次修改准备一个干净上下文。" : "A clean context for the next change.";
  $("#sessionTitle").textContent = history ? String(history.preview || history.prompt || defaultTitle).slice(0, 72) : (state.locale === "zh" ? (preset?.titleZh || preset?.title || defaultTitle) : (preset?.title || defaultTitle));
  $("#sessionSubtitle").textContent = history ? phaseLabel(history) : (state.locale === "zh" ? (preset?.subtitleZh || preset?.subtitle || defaultSubtitle) : (preset?.subtitle || defaultSubtitle));
  const markup = history && !history.summary_only
    ? taskHistoryListMarkup(historyItems?.length ? historyItems : [history])
    : (cachedSessionView(sessionId) || (sessionId === "interview-1" ? initialMessageMarkup : presetMessageMarkup(sessionId)));
  if (markup) $("#messageList").innerHTML = markup;
  updateSessionStatus(history);
  if (history) renderedHistoryKeys.set(sessionId, taskHistoryKey(historyItems?.length ? historyItems : history));
  else renderedHistoryKeys.delete(sessionId);
  // Restore the task plan from the last todo_write event in this session's
  // durable history; hide the section when no checklist can be recovered.
  const todoSource = historyItems?.length ? [...historyItems].reverse() : (history ? [history] : []);
  latestTodos = latestTodosFromEvents(todoSource.flatMap((item) => Array.isArray(item?.events) ? item.events : []));
  renderTodoPanel();
  refreshIcons();
  // Preserve the visible message across background history refreshes.
  restoreChatPosition(chatPosition);
  window.requestAnimationFrame(() => restoreSessionTask(sessionId));
}

function taskDotClass(status) {
  if (status === "completed") return "mint";
  if (["failed", "cancelled", "interrupted"].includes(status)) return "amber";
  return "coral";
}

function renderTaskHistory(tasks) {
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
  const listChanged = renderedTaskListKey !== nextTaskListKey || list.dataset.historyLoaded !== "true";
  if (!normalizedTasks.length) {
    $("#taskNavCount").textContent = "0";
    if (listChanged) list.innerHTML = `<div class="thread-empty">${escapeHtml(t("tasks.noHistory"))}</div>`;
    renderedTaskListKey = nextTaskListKey;
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
  renderedTaskListKey = nextTaskListKey;
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

async function loadTaskHistory() {
  try {
    const query = state.workspacePath ? "&workspace=" + encodeURIComponent(state.workspacePath) : "";
    const data = await requestJson("/api/tasks?limit=100" + query);
    if (state.connection === false) setConnection(true);
    renderTaskHistory(data.tasks || []);
  } catch {
    // Static demo sessions remain available when the task index is offline.
  }
}
