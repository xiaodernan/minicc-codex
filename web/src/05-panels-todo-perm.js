// NOTE: 源文件分片（web/src/）。此文件由 `npm run build:web` 按序拼接生成，勿直接编辑。
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}
function chatIsNearBottom(area = $("#chatArea"), threshold = 32) {
  if (!area) return true;
  return area.scrollHeight - area.clientHeight - area.scrollTop <= threshold;
}

function updateChatFollowState() {
  const area = $("#chatArea");
  if (!area) return;
  state.chatFollow = chatIsNearBottom(area);
  const button = $("#jumpLatestButton");
  if (button) {
    button.hidden = state.chatFollow;
    button.title = state.chatFollow ? t("tasks.following") : t("tasks.jumpLatest");
    button.setAttribute("aria-label", state.chatFollow ? t("tasks.following") : t("tasks.jumpLatest"));
  }
}

function captureChatPosition(area = $("#chatArea")) {
  if (!area) return null;
  const areaRect = area.getBoundingClientRect();
  const anchorElements = [...area.querySelectorAll(".message[data-chat-anchor]")];
  const anchor = (anchorElements.length ? anchorElements : [...area.querySelectorAll(".message")])
    .map((element) => ({ element, rect: element.getBoundingClientRect() }))
    .filter(({ rect }) => rect.bottom > areaRect.top + 2 && rect.top < areaRect.bottom - 2)
    .sort((left, right) => Math.max(left.rect.top, areaRect.top) - Math.max(right.rect.top, areaRect.top))[0];
  return {
    area, top: area.scrollTop, left: area.scrollLeft, followLatest: chatIsNearBottom(area),
    anchorElement: anchor?.element || null,
    anchorKey: anchor?.element?.dataset?.chatAnchor || "",
    anchorOffset: anchor ? anchor.rect.top - areaRect.top : 0,
  };
}

function restoreChatPosition(position, schedule = true) {
  if (!position?.area?.isConnected) return;
  const restoreVersion = ++state.chatRestoreVersion;
  const restore = () => {
    if (!position.area.isConnected || restoreVersion !== state.chatRestoreVersion) return;
    if (position.followLatest) {
      position.area.scrollTop = Math.max(0, position.area.scrollHeight - position.area.clientHeight);
    } else {
      const anchor = position.anchorElement?.isConnected
        ? position.anchorElement
        : [...position.area.querySelectorAll(".message[data-chat-anchor]")].find((element) => element.dataset.chatAnchor === position.anchorKey);
      if (anchor) {
        const currentOffset = anchor.getBoundingClientRect().top - position.area.getBoundingClientRect().top;
        position.area.scrollTop += currentOffset - position.anchorOffset;
      } else {
        position.area.scrollTop = position.top;
      }
    }
    position.area.scrollLeft = position.left;
    state.chatFollow = Boolean(position.followLatest);
    const button = $("#jumpLatestButton");
    if (button) {
      button.hidden = state.chatFollow;
      button.title = state.chatFollow ? t("tasks.following") : t("tasks.jumpLatest");
      button.setAttribute("aria-label", state.chatFollow ? t("tasks.following") : t("tasks.jumpLatest"));
    }
  };
  restore();
  if (schedule) window.requestAnimationFrame(restore);
}

function scrollChat(behavior = "auto", force = false) {
  const area = $("#chatArea");
  if (!area || !force) {
    updateChatFollowState();
    return;
  }
  if (force) state.chatFollow = true;
  area.scrollTo({ top: area.scrollHeight, behavior });
  window.requestAnimationFrame(updateChatFollowState);
}

function setConnection(connected, label = connected ? "Connected" : "Offline") {
  state.connection = connected;
  const status = $("#connectionStatus");
  status.classList.toggle("offline", !connected);
  const translated = label === "Connected" ? t("connection.connected") : label === "Offline" ? t("connection.offline") : label;
  status.innerHTML = `<span class="status-pulse"></span><span>${escapeHtml(translated)}</span>`;
}

function setTaskTransportStatus(taskId, mode) {
  const binding = runningTasks.get(taskId);
  if (!binding) return;
  binding.transport = mode;
  binding.data = { ...(binding.data || {}), transport: mode };
  const loading = document.getElementById(binding.loadingId);
  const transport = loading?.querySelector("[data-live-transport]");
  if (!transport) return;
  const key = mode === "polling" ? "stream.polling" : mode === "reconnecting" ? "stream.reconnecting" : mode === "connecting" ? "connection.connecting" : "stream.connected";
  transport.textContent = t(key);
  transport.dataset.transport = mode;
}

function setBusy(value) {
  state.busy = Boolean(value);
  const sessionBusy = state.busy || isSessionBusy(state.sessionId);
  $("#sendButton").disabled = Boolean(state.submitting);
  $("#cancelTaskButton").hidden = !sessionBusy;
  $("#pulseStatus").textContent = sessionBusy ? t("working") : t("ready");
  $("#pulseStatus").style.color = sessionBusy ? "var(--coral)" : "var(--mint)";
  $("#sendButton").innerHTML = state.submitting ? icon("loader-circle") : icon("arrow-up");
  if (state.submitting) $("#sendButton").firstElementChild.classList.add("spin");
  refreshIcons();
}

function updateReasoningControl() {
  const value = $("#reasoningButtonValue");
  if (value) value.textContent = t("reasoning." + state.reasoningEffort);
  const button = $("#reasoningButton");
  if (button) {
    const label = t("panel.reasoning") + ": " + t("reasoning." + state.reasoningEffort);
    button.title = label;
    button.setAttribute("aria-label", label);
  }
}

function setSession(sessionId) {
  const sessionChanged = state.sessionId !== sessionId;
  if (sessionViewReady && sessionChanged) {
    persistSessionView();
  }
  state.sessionId = sessionId;
  if (sessionChanged || !sessionTaskBindings(sessionId).some((binding) => binding.taskId === state.activeTaskId)) {
    const bindings = sessionTaskBindings(sessionId);
    state.activeTaskId = bindings.length
      ? bindings[bindings.length - 1].taskId
      : taskBySession.get(taskSessionKey(sessionId)) || null;
  }
  localStorage.setItem("minicc-session", sessionId);
  $("#topSession").textContent = sessionId;
  $$(".thread-item").forEach((item) => item.classList.toggle("active", item.dataset.session === sessionId));
  renderSession(sessionId, { followLatest: sessionChanged });
  sessionViewReady = true;
}

function taskSessionKey(sessionId, workspacePath = state.workspacePath) {
  const normalizedWorkspace = String(workspacePath || "default").replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase();
  return `${normalizedWorkspace}::${sessionId}`;
}

function sessionTaskBindings(sessionId, workspacePath = state.workspacePath) {
  return [...runningTasks.values()].filter((binding) => (
    binding.sessionId === sessionId
    && taskSessionKey(binding.sessionId, binding.workspacePath) === taskSessionKey(sessionId, workspacePath)
    && !isTerminalTask(binding.data)
  ));
}

function isSessionBusy(sessionId) {
  if (sessionTaskBindings(sessionId).length > 0) return true;
  const taskId = taskBySession.get(taskSessionKey(sessionId));
  const binding = taskId ? runningTasks.get(taskId) : null;
  return Boolean(binding && !isTerminalTask(binding.data));
}

function formatDuration(value) {
  const total = Math.max(0, Math.floor(Number(value) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function taskDuration(data) {
  const stored = Number(data?.duration_seconds);
  if (data?.started_at && ["queued", "running"].includes(data.status)) {
    const started = Date.parse(data.started_at);
    if (Number.isFinite(started)) return Math.max(0, (Date.now() - started) / 1000);
  }
  return Number.isFinite(stored) ? stored : 0;
}

function updateTaskDuration(data, loadingId = "") {
  const duration = formatDuration(taskDuration(data));
  if (loadingId) document.getElementById(loadingId)?.querySelectorAll("[data-live-duration]").forEach((item) => { item.textContent = duration; });
  const binding = data?.task_id ? runningTasks.get(data.task_id) : null;
  const scopedData = binding
    ? { ...data, session_id: binding.sessionId, workspace_path: binding.workspacePath }
    : data;
  if (isFocusedTask(scopedData)) {
    const dockTimer = $("#taskDockTimer");
    if (dockTimer && (!state.lastTask || state.lastTask.task_id === data?.task_id)) dockTimer.textContent = duration;
  }
}

function startTaskTimer(taskId) {
  if (taskTimerHandles.has(taskId)) return;
  const handle = window.setInterval(() => {
    const binding = runningTasks.get(taskId);
    if (!binding) {
      window.clearInterval(handle);
      taskTimerHandles.delete(taskId);
      return;
    }
    updateTaskDuration(binding.data, binding.loadingId);
  }, 1000);
  taskTimerHandles.set(taskId, handle);
}

function stopTaskTimer(taskId) {
  const handle = taskTimerHandles.get(taskId);
  if (handle) window.clearInterval(handle);
  taskTimerHandles.delete(taskId);
}

function eventSequence(value) {
  const sequence = Number(value);
  return Number.isFinite(sequence) && sequence > 0 ? Math.floor(sequence) : 0;
}

function eventIdentity(event) {
  if (!event || typeof event !== "object") return "";
  if (event.item_id) return `item:${event.item_id}`;
  if (event.event_id) return `id:${event.event_id}`;
  const sequence = eventSequence(event.sequence);
  if (sequence) return `seq:${sequence}`;
  return `fallback:${[event.kind, event.code, event.name, event.status, event.summary, event.path].map((item) => String(item || "")).join("|")}`;
}

function mergeTimelineEvents(current, incoming) {
  const merged = new Map();
  for (const event of [...(Array.isArray(current) ? current : []), ...(Array.isArray(incoming) ? incoming : [])]) {
    if (!event || typeof event !== "object") continue;
    const key = eventIdentity(event);
    if (key) merged.set(key, { ...event });
  }
  return [...merged.values()]
    .sort((left, right) => eventSequence(left.sequence) - eventSequence(right.sequence))
    .slice(-1024);
}

function markBindingEvents(binding, events) {
  const remember = (set, value) => {
    if (!value) return;
    set.delete(value);
    set.add(value);
    while (set.size > MAX_SEEN_EVENT_KEYS) set.delete(set.values().next().value);
  };
  for (const event of Array.isArray(events) ? events : []) {
    if (!event || typeof event !== "object") continue;
    const sequence = eventSequence(event.sequence);
    if (sequence) remember(binding.seenSequences, sequence);
    if (event.event_id) remember(binding.seenEventIds, String(event.event_id));
    if (event.item_id) remember(binding.seenEventIds, `item:${event.item_id}`);
  }
}

function applyTaskSnapshot(binding, snapshot, { replaceEvents = true } = {}) {
  const incoming = snapshot && typeof snapshot === "object" ? snapshot : {};
  const previous = binding.data && typeof binding.data === "object" ? binding.data : {};
  const previousCursor = eventSequence(binding.cursor || previous.event_cursor);
  const incomingCursor = eventSequence(incoming.event_cursor);
  if (previousCursor && incomingCursor && incomingCursor < previousCursor) return previous;
  const next = { ...previous, ...incoming };
  if (Array.isArray(incoming.events)) {
    next.events = replaceEvents
      ? incoming.events.filter((event) => event && typeof event === "object").map((event) => ({ ...event }))
      : mergeTimelineEvents(previous.events, incoming.events);
  }
  binding.cursor = Math.max(previousCursor, incomingCursor);
  next.event_cursor = binding.cursor;
  next.session_id = next.session_id || binding.sessionId;
  next.workspace_path = next.workspace_path || binding.workspacePath;
  binding.data = next;
  markBindingEvents(binding, next.events);
  return next;
}

function bindRunningTask(task, loadingId, sessionId = state.sessionId) {
  if (!task?.task_id) return null;
  finalizedTaskIds.delete(task.task_id);
  const previous = runningTasks.get(task.task_id);
  const binding = previous || {
    taskId: task.task_id,
    sessionId,
    workspacePath: task.workspace_path || state.workspacePath,
    loadingId,
    data: task,
    cursor: 0,
    seenSequences: new Set(),
    seenEventIds: new Set(),
  };
  binding.sessionId = sessionId || binding.sessionId || state.sessionId;
  binding.workspacePath = task.workspace_path || binding.workspacePath || state.workspacePath;
  binding.loadingId = loadingId || binding.loadingId || `loading-${task.task_id}`;
  if (previous) applyTaskSnapshot(binding, task, { replaceEvents: true });
  else {
    binding.data = task;
    binding.cursor = eventSequence(task.event_cursor);
    markBindingEvents(binding, task.events);
  }
  runningTasks.set(task.task_id, binding);
  const scopeKey = taskSessionKey(sessionId, binding.workspacePath);
  const previousId = taskBySession.get(scopeKey);
  const previousScoped = previousId ? runningTasks.get(previousId) : null;
  if (!previousScoped || Number(task.created_at_epoch || 0) >= Number(previousScoped.data?.created_at_epoch || 0)) {
    taskBySession.set(scopeKey, task.task_id);
  }
  state.activeTaskId = sessionId === state.sessionId ? task.task_id : state.activeTaskId;
  startTaskTimer(task.task_id);
  return binding;
}

function restoreSessionTask(sessionId) {
  const bindings = sessionTaskBindings(sessionId);
  if (!bindings.length) {
    if (sessionId === state.sessionId) state.activeTaskId = null;
    setBusy(false);
    return;
  }
  if (sessionId === state.sessionId) state.activeTaskId = bindings[bindings.length - 1].taskId;
  for (const binding of bindings) {
    if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, binding.data, { scrollToLatest: false });
    updateLiveTask(binding.loadingId, binding.data);
    syncTodoPanelFromEvents(binding.data?.events);
  }
  if (sessionId === state.sessionId) state.activeTaskId = bindings[bindings.length - 1].taskId;
  setBusy(true);
}

const PERMISSION_MODES = ["default", "plan", "acceptEdits", "yolo"];

// Effective per-task permission flags for the selected mode. `plan` forces the
// read-only flags, `yolo` implies both; `default`/`acceptEdits` honor the
// user's manual toggles (matching the backend _resolve_task_permissions).
function effectiveTaskPermissions() {
  const mode = state.permissionMode;
  return {
    mode,
    allowChanges: mode === "plan" ? false : mode === "yolo" ? true : state.allowChanges,
    allowNetwork: mode === "yolo" ? true : state.allowNetwork,
  };
}

function updateMode() {
  const effective = effectiveTaskPermissions();
  const checkbox = $("#allowChanges");
  const networkCheckbox = $("#allowNetwork");
  if (checkbox) {
    checkbox.checked = effective.allowChanges;
    checkbox.disabled = state.permissionMode === "plan" || state.permissionMode === "yolo";
    checkbox.closest(".safe-toggle")?.classList.toggle("locked", checkbox.disabled);
  }
  if (networkCheckbox) {
    networkCheckbox.checked = effective.allowNetwork;
    networkCheckbox.disabled = state.permissionMode === "yolo";
    networkCheckbox.closest(".safe-toggle")?.classList.toggle("locked", networkCheckbox.disabled);
  }
  const modeLabelText = state.permissionMode === "default"
    ? (effective.allowChanges ? t("mode.changes") : t("mode.safe"))
    : t(`perm.${state.permissionMode}`);
  const modeLabel = $("#modeLabel");
  if (modeLabel) modeLabel.textContent = modeLabelText;
  const hint = state.permissionMode === "default"
    ? (effective.allowChanges ? t("composer.fullAccess") : t("composer.readOnly"))
    : t(`perm.${state.permissionMode}Hint`);
  $("#permissionHint").textContent = hint;
  $("#modeBadge").textContent = effective.allowChanges ? t("mode.localFull") : t("mode.localSafe");
  renderPermissionSegments();
}

function renderPermissionSegments() {
  const group = $("#permModeGroup");
  if (group) {
    [...group.querySelectorAll(".perm-mode-option")].forEach((option) => {
      const active = option.dataset.mode === state.permissionMode;
      option.classList.toggle("active", active);
      option.setAttribute("aria-checked", String(active));
      option.tabIndex = active ? 0 : -1;
    });
  }
  const hint = $("#permModeHint");
  if (hint) hint.textContent = t(`perm.${state.permissionMode}Hint`);
}

function setPermissionMode(mode) {
  const next = PERMISSION_MODES.includes(mode) ? mode : "default";
  const changed = next !== state.permissionMode;
  state.permissionMode = next;
  localStorage.setItem("minicc-permission-mode", next);
  updateMode();
  if (changed) {
    showToast(state.locale === "zh" ? `权限模式：${t(`perm.${next}`)}` : `Permission mode: ${t(`perm.${next}`)}`);
  }
}

// --- Task plan panel (Inspector) -------------------------------------------
// The checklist comes from todo_write / todo_read ToolResult.data payloads that
// travel inside timeline tool events. The latest list wins; the section stays
// hidden until a plan exists.

let latestTodos = null;

function normalizeTodoEntries(rawTodos) {
  if (!Array.isArray(rawTodos)) return null;
  return rawTodos
    .filter((todo) => todo && typeof todo === "object" && String(todo.content || "").trim())
    .map((todo) => ({
      content: String(todo.content).trim().slice(0, 500),
      status: ["pending", "in_progress", "completed"].includes(String(todo.status)) ? String(todo.status) : "pending",
      priority: ["high", "medium", "low"].includes(String(todo.priority)) ? String(todo.priority) : "medium",
    }))
    .slice(0, 50);
}

function todosFromToolEvent(event) {
  if (!event || typeof event !== "object" || event.kind === "trace") return null;
  const name = String(event.name || "");
  if (name !== "todo_write" && name !== "todo_read") return null;
  const data = event.data && typeof event.data === "object" ? event.data : null;
  return normalizeTodoEntries(data?.todos);
}

function latestTodosFromEvents(events) {
  let found = null;
  for (const event of Array.isArray(events) ? events : []) {
    const todos = todosFromToolEvent(event);
    if (todos) found = todos;
  }
  return found;
}

function syncTodoPanelFromEvents(events) {
  const todos = latestTodosFromEvents(events);
  if (todos) latestTodos = todos;
  renderTodoPanel();
}

function renderTodoPanel() {
  const section = $("#todoSection");
  if (!section) return;
  const hasTodos = Array.isArray(latestTodos) && latestTodos.length > 0;
  section.hidden = !hasTodos;
  if (!hasTodos) return;
  const completed = latestTodos.filter((todo) => todo.status === "completed").length;
  const progress = $("#todoProgressCount");
  if (progress) {
    progress.textContent = `${completed}/${latestTodos.length}`;
    progress.setAttribute("aria-label", `${t("todo.progressAria")}: ${completed}/${latestTodos.length}`);
  }
  const list = $("#todoListBody");
  if (!list) return;
  const statusLabels = { pending: t("todo.pending"), in_progress: t("todo.inProgress"), completed: t("todo.completed") };
  list.innerHTML = latestTodos.map((todo) => `
    <li class="todo-item todo-${escapeHtml(todo.status)}" aria-label="${escapeHtml(`${todo.content} · ${statusLabels[todo.status] || todo.status}`)}">
      <span class="todo-status-mark" aria-hidden="true">${todo.status === "completed" ? icon("check") : ""}</span>
      <span class="todo-priority-dot todo-priority-${escapeHtml(todo.priority)}" aria-hidden="true"></span>
      <span class="todo-copy"><span class="todo-content">${escapeHtml(todo.content)}</span><small class="todo-status-label">${escapeHtml(statusLabels[todo.status] || todo.status)}</small></span>
    </li>`).join("");
  refreshIcons();
}

function toggleTodoSection(force) {
  const section = $("#todoSection");
  if (!section) return;
  const collapsed = typeof force === "boolean" ? force : section.dataset.collapsed !== "true";
  section.dataset.collapsed = collapsed ? "true" : "false";
  const body = $("#todoListBody");
  if (body) body.hidden = collapsed;
  const toggle = $("#todoSectionToggle");
  if (toggle) toggle.setAttribute("aria-expanded", String(!collapsed));
}

// --- File tree (Inspector) --------------------------------------------------
// Lazy workspace tree backed by GET /api/files. The endpoint returns one flat
// entries array (root-relative paths, dirs filtered server-side), so each
// request fetches FILE_TREE_DEPTH levels: direct children are rendered and any
// deeper directories delivered by the same response are pre-seeded into the
// per-directory cache, so expanding them costs no extra request. Cached file
// entries also feed the @-mention index in the composer.

const FILE_TREE_DEPTH = 2;             // levels fetched per /api/files request
const FILE_TREE_RENDER_LIMIT = 800;    // rows rendered per level before truncation
const FILE_TREE_REFRESH_DELAY = 200;   // coalesce workspace-switch/completion triggers

const fileTreeState = {
  loaded: false,
  loading: false,
  rootEntries: [],
  rootTruncated: false,
  rootError: "",
  children: new Map(),  // dirPath -> { entries, truncated }
  expanded: new Set(),
  pending: new Set(),
  fileIndex: [],        // [{path, size}] for @-mentions
  requestToken: 0,
  refreshTimer: 0,
};

function fileTreeParentOf(path) {
  const value = String(path || "");
  const index = value.lastIndexOf("/");
  return index < 0 ? "" : value.slice(0, index);
}

function fileTreeSort(entries) {
  return [...entries].sort((left, right) => {
    const dirDelta = (left?.type === "dir" ? 0 : 1) - (right?.type === "dir" ? 0 : 1);
    if (dirDelta) return dirDelta;
    return String(left?.name || left?.path || "").localeCompare(String(right?.name || right?.path || ""), undefined, { sensitivity: "base", numeric: true });
  });
}

function fileTreeIndexFiles(entries) {
  for (const entry of Array.isArray(entries) ? entries : []) {
    if (!entry || entry.type !== "file" || !entry.path) continue;
    if (fileTreeState.fileIndex.some((item) => item.path === entry.path)) continue;
    fileTreeState.fileIndex.push({ path: String(entry.path), size: Number(entry.size || 0) });
  }
  if (fileTreeState.fileIndex.length > 4000) fileTreeState.fileIndex.length = 4000;
}

// Cache the direct children of dirPath delivered by a flat listing. An empty
// result is intentionally not cached: the directory is either genuinely empty
// or was cut off, and a later expand re-fetches to stay correct.
function fileTreeSeedChildren(dirPath, entries) {
  const children = [];
  for (const entry of Array.isArray(entries) ? entries : []) {
    if (entry?.path && fileTreeParentOf(entry.path) === dirPath) children.push(entry);
  }
  fileTreeIndexFiles(children);
  if (!children.length) return;
  fileTreeState.children.set(dirPath, { entries: children });
}

async function fileTreeFetch(dirPath) {
  const data = await requestJson(`/api/files?path=${encodeURIComponent(dirPath || "")}&depth=${FILE_TREE_DEPTH}`, {}, 12000);
  return { entries: Array.isArray(data.entries) ? data.entries : [], truncated: Boolean(data.truncated) };
}

async function loadFileTree() {
  if (!state.workspacePath) return;
  const token = ++fileTreeState.requestToken;
  fileTreeState.loading = true;
  fileTreeState.rootError = "";
  renderFileTree();
  try {
    const result = await fileTreeFetch("");
    if (token !== fileTreeState.requestToken) return;
    fileTreeState.rootEntries = fileTreeSort(result.entries.filter((entry) => entry?.path && fileTreeParentOf(entry.path) === ""));
    fileTreeState.rootTruncated = result.truncated;
    fileTreeState.children = new Map();
    fileTreeState.expanded = new Set();
    fileTreeState.fileIndex = [];
    fileTreeState.loaded = true;
    fileTreeIndexFiles(fileTreeState.rootEntries);
    // Pre-seed level-1 folders from the same depth=2 response.
    for (const entry of fileTreeState.rootEntries) {
      if (entry.type === "dir") fileTreeSeedChildren(entry.path, result.entries);
    }
  } catch (error) {
    if (token !== fileTreeState.requestToken) return;
    fileTreeState.rootError = String(error?.message || "error");
    fileTreeState.loaded = true;
  } finally {
    if (token === fileTreeState.requestToken) {
      fileTreeState.loading = false;
      renderFileTree();
      if (mentionState.open) updateMentionPopover();
    }
  }
}

async function toggleFileDir(dirPath) {
  if (fileTreeState.expanded.has(dirPath)) {
    fileTreeState.expanded.delete(dirPath);
    renderFileTree();
    return;
  }
  fileTreeState.expanded.add(dirPath);
  if (!fileTreeState.children.has(dirPath) && !fileTreeState.pending.has(dirPath)) {
    fileTreeState.pending.add(dirPath);
    renderFileTree();
    try {
      const result = await fileTreeFetch(dirPath);
      fileTreeSeedChildren(dirPath, result.entries);
      // Also pre-seed the direct subfolders delivered by this response.
      for (const entry of result.entries) {
        if (entry?.type === "dir" && fileTreeParentOf(entry.path) === dirPath) fileTreeSeedChildren(entry.path, result.entries);
      }
    } catch (error) {
      fileTreeState.children.set(dirPath, { entries: [], error: String(error?.message || "error") });
    } finally {
      fileTreeState.pending.delete(dirPath);
    }
  }
  renderFileTree();
  if (mentionState.open) updateMentionPopover();
}

function fileTreeRowMarkup(entry, level) {
  const indent = `padding-left:${6 + Math.min(level, 8) * 13}px`;
  if (entry.type === "dir") {
    const expanded = fileTreeState.expanded.has(entry.path);
    return `<button type="button" class="file-tree-row" role="treeitem" aria-expanded="${expanded ? "true" : "false"}" data-tree-dir="${escapeHtml(entry.path)}" style="${indent}" aria-label="${escapeHtml(entry.name)}"><span class="file-tree-chevron" aria-hidden="true">${icon(expanded ? "chevron-down" : "chevron-right")}</span><span class="file-tree-icon" aria-hidden="true">${icon(expanded ? "folder-open" : "folder")}</span><span class="file-tree-name">${escapeHtml(entry.name || entry.path)}</span></button>`;
  }
  const size = Number(entry.size || 0);
  return `<button type="button" class="file-tree-row" role="treeitem" data-open-diff="${escapeHtml(entry.path)}" style="${indent}" aria-label="${escapeHtml(`${entry.name || entry.path} ${formatBytes(size)}`)}"><span class="file-tree-chevron" aria-hidden="true"></span><span class="file-tree-icon" aria-hidden="true">${icon("file-code-2")}</span><span class="file-tree-name">${escapeHtml(entry.name || entry.path)}</span><span class="file-tree-size">${escapeHtml(formatBytes(size))}</span></button>`;
}

function renderFileTree() {
  const tree = $("#fileTree");
  if (!tree) return;
  if (fileTreeState.loading && !fileTreeState.loaded) {
    tree.innerHTML = `<div class="file-tree-status">${escapeHtml(t("files.loading"))}</div>`;
    return;
  }
  if (fileTreeState.rootError) {
    tree.innerHTML = `<div class="file-tree-status file-tree-error"><span>${escapeHtml(t("files.loadError"))}</span><small>${escapeHtml(fileTreeState.rootError)}</small></div>`;
    return;
  }
  const rows = [];
  const notes = new Set();
  let remaining = FILE_TREE_RENDER_LIMIT;
  const walk = (entries, level, dirPath) => {
    for (const entry of entries) {
      if (remaining <= 0) { notes.add(t("files.truncated")); return; }
      remaining -= 1;
      rows.push(fileTreeRowMarkup(entry, level));
      if (entry.type !== "dir" || !fileTreeState.expanded.has(entry.path)) continue;
      const cached = fileTreeState.children.get(entry.path);
      const childIndent = `padding-left:${6 + Math.min(level + 1, 8) * 13}px`;
      if (cached?.error) rows.push(`<div class="file-tree-status" style="${childIndent}">${escapeHtml(cached.error)}</div>`);
      else if (!cached) {
        // First expansion is still in flight (toggleFileDir triggered the fetch).
        if (fileTreeState.pending.has(entry.path)) rows.push(`<div class="file-tree-status" style="${childIndent}">${escapeHtml(t("files.loading"))}</div>`);
      } else {
        walk(fileTreeSort(cached.entries), level + 1, entry.path);
        if (cached.truncated) notes.add(t("files.truncated"));
      }
    }
    if (dirPath === "" && fileTreeState.rootTruncated) notes.add(t("files.truncated"));
  };
  walk(fileTreeState.rootEntries, 0, "");
  if (!rows.length) {
    tree.innerHTML = `<div class="file-tree-status">${escapeHtml(t("files.empty"))}</div>`;
    return;
  }
  const list = `<div class="file-tree-list" role="tree" aria-label="${escapeHtml(t("files.tree"))}">${rows.join("")}</div>`;
  const noteMarkup = notes.size ? `<div class="file-tree-note">${icon("alert-triangle")}<span>${escapeHtml([...notes].join(" "))}</span></div>` : "";
  tree.innerHTML = `${list}${noteMarkup}`;
  refreshIcons();
}

function refreshFileTreeSoon() {
  window.clearTimeout(fileTreeState.refreshTimer);
  fileTreeState.refreshTimer = window.setTimeout(() => { loadFileTree(); }, FILE_TREE_REFRESH_DELAY);
}

function refreshFileTree() {
  fileTreeState.requestToken += 1; // discard in-flight loads from the stale workspace
  fileTreeState.loaded = false;
  loadFileTree();
}

// --- @-file mention popover (composer) --------------------------------------
// Typing "@" opens a listbox fed by the file tree's cached /api/files index.
// The token spans from the "@" to the caret; options are filtered by prefix
// (basename matches first) and keyboard navigation never sends the message.

const MENTION_MAX_OPTIONS = 8;
const mentionState = { open: false, options: [], active: 0, matchStart: -1 };

function mentionTokenAt(text, caret) {
  const before = String(text || "").slice(0, Math.max(0, caret));
  const match = /(^|\s)@([^\s@]*)$/.exec(before);
  if (!match) return null;
  return { fragment: match[2], start: before.length - match[2].length - 1 };
}

function mentionCandidates(fragment) {
  const needle = String(fragment || "").toLowerCase();
  const starts = [];
  const contains = [];
  for (const item of fileTreeState.fileIndex) {
    const path = item.path.toLowerCase();
    const name = path.slice(path.lastIndexOf("/") + 1);
    if (!needle || name.startsWith(needle)) starts.push(item);
    else if (path.startsWith(needle) || path.includes(needle)) contains.push(item);
    if (starts.length >= MENTION_MAX_OPTIONS) break;
  }
  return [...starts, ...contains].slice(0, MENTION_MAX_OPTIONS);
}

function ensureMentionIndex() {
  if (fileTreeState.fileIndex.length || fileTreeState.loading) return;
  loadFileTree();
}

function positionMentionPopover() {
  const shell = $("#composerShell");
  const input = $("#promptInput");
  const popover = $("#mentionPopover");
  if (!shell || !input || !popover) return;
  const shellRect = shell.getBoundingClientRect();
  const inputRect = input.getBoundingClientRect();
  popover.style.left = `${Math.max(10, Math.round(inputRect.left - shellRect.left + 10))}px`;
  popover.style.top = `${Math.round(inputRect.bottom - shellRect.top + 4)}px`;
}

function renderMentionPopover() {
  const popover = $("#mentionPopover");
  if (!popover) return;
  const options = mentionState.options;
  const body = options.length
    ? options.map((item, index) => `<button type="button" class="mention-option${index === mentionState.active ? " active" : ""}" role="option" aria-selected="${index === mentionState.active ? "true" : "false"}" data-mention-index="${index}" aria-label="${escapeHtml(item.path)}"><span class="mention-path">${escapeHtml(item.path)}</span><small class="mention-size">${escapeHtml(formatBytes(item.size))}</small></button>`).join("")
    : `<div class="mention-empty">${escapeHtml(t("at.empty"))}</div>`;
  popover.innerHTML = `${body}<div class="mention-hint" aria-hidden="true">${escapeHtml(t("at.hint"))}</div>`;
  popover.hidden = false;
  popover.querySelector(`[data-mention-index="${mentionState.active}"]`)?.scrollIntoView({ block: "nearest" });
}

function updateMentionPopover() {
  const input = $("#promptInput");
  if (!input) return;
  ensureMentionIndex();
  const token = mentionTokenAt(input.value, input.selectionStart ?? input.value.length);
  if (!token) { closeMentionPopover(); return; }
  mentionState.open = true;
  mentionState.matchStart = token.start;
  mentionState.options = mentionCandidates(token.fragment);
  mentionState.active = Math.min(mentionState.active, Math.max(0, mentionState.options.length - 1));
  renderMentionPopover();
  positionMentionPopover();
}

function closeMentionPopover() {
  mentionState.open = false;
  mentionState.options = [];
  mentionState.active = 0;
  mentionState.matchStart = -1;
  const popover = $("#mentionPopover");
  if (popover) {
    popover.hidden = true;
    popover.innerHTML = "";
  }
}

function applyMentionOption(index = mentionState.active) {
  const option = mentionState.options[index];
  const input = $("#promptInput");
  if (!option || !input) { closeMentionPopover(); return; }
  const value = String(input.value || "");
  const caret = input.selectionStart ?? value.length;
  const insert = `@${option.path} `;
  const next = value.slice(0, mentionState.matchStart) + insert + value.slice(caret);
  input.value = next;
  const nextCaret = mentionState.matchStart + insert.length;
  input.setSelectionRange(nextCaret, nextCaret);
  closeMentionPopover();
  input.focus();
}

// Returns true when the key press was consumed by the mention popover so the
// composer's own Enter-to-send behavior stays out of the way.
function handleMentionKeydown(event) {
  if (!mentionState.open || event.isComposing) return false;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const count = Math.max(1, mentionState.options.length);
    mentionState.active = (mentionState.active + (event.key === "ArrowDown" ? 1 : -1) + count) % count;
    renderMentionPopover();
    return true;
  }
  if (event.key === "Enter" || event.key === "Tab") {
    if (!mentionState.options.length) { closeMentionPopover(); return false; }
    event.preventDefault();
    applyMentionOption();
    return true;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation(); // keep the window-level Esc from closing the panel
    closeMentionPopover();
    return true;
  }
  return false;
}

// --- Global session history search ------------------------------------------
// A panel that queries GET /api/history/search with a 300ms debounce. Result
// rows reuse the panelBody data-open-task delegation, which routes the click
// through openTaskInWorkspace (switching workspace when needed).

const GLOBAL_SEARCH_DEBOUNCE = 300;
let globalSearchTimer = 0;
let globalSearchToken = 0;

function relativeTimeFrom(value) {
  const epoch = Date.parse(String(value || ""));
  if (!Number.isFinite(epoch)) return "--";
  const seconds = Math.max(0, Math.round((Date.now() - epoch) / 1000));
  const zh = state.locale === "zh";
  if (seconds < 60) return zh ? "刚刚" : "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return zh ? `${minutes} 分钟前` : `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return zh ? `${hours} 小时前` : `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return zh ? `${days} 天前` : `${days}d ago`;
  return new Date(epoch).toLocaleDateString(zh ? "zh-CN" : "en-US");
}

// Snippet text is escaped first; the query is regex-escaped so special
// characters degrade to "no highlight" instead of throwing.
function highlightSearchText(text, query) {
  const escaped = escapeHtml(String(text || ""));
  if (!query) return escaped;
  try {
    const pattern = new RegExp(String(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    return escaped.replace(pattern, (match) => `<mark>${match}</mark>`);
  } catch {
    return escaped;
  }
}

function globalSearchResultMarkup(item, query) {
  const taskLabel = String(item.prompt_preview || "").split("\n")[0].trim().slice(0, 90) || String(item.task_id || "");
  const workspaceName = String(item.workspace_path || "").split(/[\\/]/).filter(Boolean).pop() || "workspace";
  const matchCount = Number(item.match_count || 0);
  return `<button type="button" class="global-search-result" data-open-task="${escapeHtml(item.task_id || "")}">
    <span class="global-search-result-head"><strong>${escapeHtml(taskLabel)}</strong>${matchCount ? `<span class="global-search-matches">${matchCount} ${escapeHtml(t("search.matches"))}</span>` : ""}</span>
    <pre class="global-search-snippet">${highlightSearchText(String(item.snippet || item.prompt_preview || ""), query)}</pre>
    <span class="global-search-result-meta"><span>${escapeHtml(workspaceName)}</span><span>${escapeHtml(String(item.status || ""))}</span><span>${escapeHtml(relativeTimeFrom(item.finished_at || item.created_at))}</span></span>
  </button>`;
}

function renderGlobalSearchStatus(kind, detail = "") {
  const box = $("#globalSearchResults");
  if (!box) return;
  if (kind === "hint") box.innerHTML = `<div class="empty-panel">${escapeHtml(t("search.hint"))}</div>`;
  else if (kind === "searching") box.innerHTML = `<div class="empty-panel">${escapeHtml(t("search.searching"))}</div>`;
  else if (kind === "noResults") box.innerHTML = `<div class="empty-panel">${escapeHtml(t("search.noResults"))}</div>`;
  else if (kind === "error") box.innerHTML = `<div class="error-panel">${escapeHtml(detail)}</div>`;
}

async function runGlobalSearch(query) {
  const token = ++globalSearchToken;
  renderGlobalSearchStatus("searching");
  try {
    const data = await requestJson(`/api/history/search?q=${encodeURIComponent(query)}&limit=30`, {}, 15000);
    if (token !== globalSearchToken) return;
    const results = Array.isArray(data.results) ? data.results : [];
    const box = $("#globalSearchResults");
    if (!box) return;
    box.innerHTML = results.length ? results.map((item) => globalSearchResultMarkup(item, query)).join("") : "";
    if (!results.length) renderGlobalSearchStatus("noResults");
    else refreshIcons();
  } catch (error) {
    if (token !== globalSearchToken) return;
    renderGlobalSearchStatus("error", error.message);
  }
}

function scheduleGlobalSearch() {
  const input = $("#globalSearchInput");
  if (!input) return;
  window.clearTimeout(globalSearchTimer);
  const query = input.value.trim();
  if (!query) {
    globalSearchToken += 1; // invalidate any in-flight request
    renderGlobalSearchStatus("hint");
    return;
  }
  globalSearchTimer = window.setTimeout(() => runGlobalSearch(query), GLOBAL_SEARCH_DEBOUNCE);
}

function openGlobalSearchPanel() {
  openPanel(t("search.global"), `<div class="global-search-panel"><div class="global-search-box">${icon("search")}<input id="globalSearchInput" type="search" placeholder="${escapeHtml(t("search.globalPlaceholder"))}" aria-label="${escapeHtml(t("search.global"))}" autocomplete="off" /></div><div class="global-search-results" id="globalSearchResults" aria-live="polite"><div class="empty-panel">${escapeHtml(t("search.hint"))}</div></div></div>`);
  const input = $("#globalSearchInput");
  input?.addEventListener("input", scheduleGlobalSearch);
  input?.focus();
}

function addUserMessage(text, attachments = []) {
  $("#messageList").insertAdjacentHTML("beforeend", `
    <article class="message user-message">
      <div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(t("message.now"))}</time></div>
      <div class="message-body"><div class="message-text">${formatText(text)}</div>${attachmentMarkup(attachments)}</div>
    </article>`);
  persistSessionView();
  scrollChat("auto", true);
}

function addLoadingMessage(id = `loading-${Date.now()}`, data = { status: "running", phase: "planning", stream_text: "" }, options = {}) {
  $("#messageList").insertAdjacentHTML("beforeend", `
    <article class="message assistant-message loading" id="${id}" data-chat-anchor="live-${escapeHtml(id)}">
      <div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span></div>
      <div class="message-body">${liveTaskMarkup(data)}</div>
    </article>`);
  if (options.scrollToLatest !== false) scrollChat("auto", true);
  return id;
}

function phaseLabel(data) {
  const status = String(data?.status || "").toLowerCase();
  const phase = TERMINAL_TASK_STATUSES.has(status) || status === "queued"
    ? status
    : data.phase || status;
  const key = {
    queued: "phase.queued",
    planning: "phase.planning",
    tool: "phase.tool",
    answering: "phase.answering",
    review: "phase.review",
    merging: "phase.merging",
    completed: "phase.completed",
    failed: "phase.failed",
    cancelled: "phase.cancelled",
    interrupted: "phase.interrupted",
  }[phase] || "working";
  return t(key);
}

function phaseClass(data) {
  const status = String(data?.status || "").toLowerCase();
  const value = TERMINAL_TASK_STATUSES.has(status) || status === "queued"
    ? status
    : String(data?.phase || data?.status || "planning").toLowerCase();
  return ["queued", "planning", "tool", "answering", "review", "merging", "completed", "failed", "cancelled", "interrupted"].includes(value) ? value : "planning";
}

function compactNumber(value) {
  const number = Number(value || 0);
  if (number >= 1000000) return `${(number / 1000000).toFixed(number >= 10000000 ? 0 : 1)}m`;
  if (number >= 1000) return `${(number / 1000).toFixed(number >= 10000 ? 0 : 1)}k`;
  return String(Math.round(number));
}

function cacheMetric(data) {
  const metrics = data?.metrics && typeof data.metrics === "object" ? data.metrics : {};
  const tokens = data?.tokens_used && typeof data.tokens_used === "object" ? data.tokens_used : {};
  const status = String(metrics.cache_status || "");
  let rate = typeof metrics.cache_hit_rate === "number" ? metrics.cache_hit_rate : NaN;
  if (!Number.isFinite(rate)) {
    const hit = Number(tokens.prompt_cache_hit_tokens);
    const miss = Number(tokens.prompt_cache_miss_tokens);
    if (Number.isFinite(hit) && Number.isFinite(miss) && hit + miss > 0) rate = hit / (hit + miss);
  }
  if (Number.isFinite(rate)) return `${Math.round(rate * 100)}%`;
  if (status === "reported" || status === "reported_zero") return t("tasks.cacheReported");
  return t("tasks.cacheUnreported");
}

function isCurrentTaskScope(data) {
  if (!data?.task_id) return true;
  if (String(data.session_id || "") !== String(state.sessionId || "")) return false;
  if (data.workspace_path && state.workspacePath) {
    return taskSessionKey(data.session_id, data.workspace_path) === taskSessionKey(state.sessionId, state.workspacePath);
  }
  return true;
}

function isFocusedTask(data) {
  if (!isCurrentTaskScope(data)) return false;
  return !data?.task_id || !state.activeTaskId || String(data.task_id) === String(state.activeTaskId);
}

function taskMetrics(data) {
  const tokens = Number(data.tokens_used?.total_tokens || 0);
  const context = Number(data.context?.tokens || 0);
  const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 300000);
  const estimated = data.tokens_used?.estimated || data.usage_by_turn?.some((item) => item.estimated);
  const tokenText = `${estimated ? "~" : ""}${compactNumber(tokens)} ${t("tasks.tokens")}`;
  return `${tokenText} · ${compactNumber(context)}/${compactNumber(limit)} ${t("tasks.context")} · ${t("tasks.cache")} ${cacheMetric(data)}`;
}

function runtimeMetricsMarkup(data) {
  const metrics = data?.metrics;
  if (!metrics || typeof metrics !== "object" || (!metrics.workflow && !metrics.verification_runs && !metrics.trace_events)) return "";
  const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
  const duration = formatDuration(metrics.duration_seconds || 0);
  return `<div><div class="panel-section-title">${escapeHtml(t("tasks.runtime"))}</div><div class="status-grid"><div><span>${escapeHtml(t("tasks.workflow"))}</span><strong>${escapeHtml(String(metrics.workflow || "coding"))}</strong><small>${escapeHtml(String(metrics.phase || data.phase || ""))}</small></div><div><span>${escapeHtml(t("tasks.repairs"))}</span><strong>${escapeHtml(String(metrics.repair_attempts || 0))}</strong><small>${escapeHtml(duration)}</small></div><div><span>${escapeHtml(t("tasks.verifications"))}</span><strong>${escapeHtml(String(metrics.verification_runs || 0))}</strong><small>${escapeHtml(String(metrics.verification_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.cache"))}</span><strong>${escapeHtml(cacheMetric(data))}</strong><small>${escapeHtml(String(metrics.cache_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.traces"))}</span><strong>${escapeHtml(String(metrics.trace_events || 0))}</strong><small>${escapeHtml(`${budget.turns || 0} turns · ${budget.tool_calls || 0} tools`)}</small></div></div></div>`;
}

function updateInspectorMetrics(data) {
  if (!data) return;
  const tokens = Number(data.tokens_used?.total_tokens || 0);
  const context = Number(data.context?.tokens || 0);
  const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 300000);
  $("#tokenMetric").textContent = compactNumber(tokens);
  $("#contextMetric").textContent = `${compactNumber(context)}/${compactNumber(limit)}`;
  $("#cacheMetric").textContent = cacheMetric(data);
  $("#compactionMetric").textContent = String(data.compaction_events?.length || 0);
  $("#contextCount").textContent = taskMetrics(data);
}

function updateTaskDock(data) {
  if (!data || !isFocusedTask(data)) return;
  if (data.task_id && !state.activeTaskId) state.activeTaskId = data.task_id;
  state.lastTask = data;
  const dock = $("#taskDock");
  if (!dock) return;
  dock.hidden = false;
  dock.dataset.status = data.status || "running";
  $("#taskDockTitle").textContent = data.task_kind === "batch" ? (data.message || t("tasks.center")) : (data.preview || data.prompt || t("tasks.center"));
  $("#taskDockPhase").textContent = phaseLabel(data);
  $("#taskDockMetrics").textContent = taskMetrics(data);
  $("#taskDockCompactions").textContent = `${data.compaction_events?.length || 0} ${t("tasks.compacted")}`;
  $("#taskDockTimer").textContent = formatDuration(taskDuration(data));
  updateInspectorMetrics(data);
  if (String(data.session_id || "") === state.sessionId && (!data.workspace_path || !state.workspacePath || taskSessionKey(data.session_id, data.workspace_path) === taskSessionKey(state.sessionId, state.workspacePath))) {
    updateSessionStatus(data);
  }
  if (["queued", "running"].includes(data.status) && data.task_id) startTaskTimer(data.task_id);
}

function updateSessionStatus(data) {
  const badge = $("#sessionLiveBadge");
  const label = $("#sessionLiveLabel");
  if (!badge || !label) return;
  const status = String(data?.status || "running").toLowerCase();
  const terminal = TERMINAL_TASK_STATUSES.has(status);
  badge.dataset.status = terminal ? status : ["queued", "running"].includes(status) ? status : "running";
  badge.classList.toggle("terminal", terminal);
  badge.classList.toggle("queued", status === "queued");
  label.textContent = terminal || status === "queued" ? phaseLabel(data) : t("live");
}

function liveTaskMarkup(data) {
  const streamText = String(data.stream_text || "");
  const currentPhase = phaseClass(data);
  const transport = data.transport || (data.status === "queued" ? "connecting" : "connected");
  const transportLabel = transport === "polling" ? t("stream.polling") : transport === "reconnecting" ? t("stream.reconnecting") : transport === "connecting" ? t("connection.connecting") : t("stream.connected");
  const preview = streamText ? formatLightText(streamTail(streamText)) : `<span class="stream-empty">${escapeHtml(t("phase.waiting"))}</span>`;
  return `<div class="live-task live-task-${currentPhase}" data-live-task data-phase="${currentPhase}">
    <div class="live-task-stage">
      <div class="task-progress" data-phase="${currentPhase}" role="status">
        <span class="phase-indicator" aria-hidden="true"><span></span></span>
        <span class="phase-label" data-live-phase>${escapeHtml(phaseLabel(data))}</span>
        <span class="phase-line" aria-hidden="true"></span>
        <span class="live-task-duration" data-live-duration>${escapeHtml(formatDuration(taskDuration(data)))}</span>
      </div>
    </div>
    <div class="stream-panel">
      <div class="stream-panel-head"><span class="stream-live-dot" aria-hidden="true"></span><span>${escapeHtml(t("stream.live"))}</span><span class="stream-transport" data-live-transport data-transport="${escapeHtml(transport)}">${escapeHtml(transportLabel)}</span><span class="stream-metrics" data-live-metrics>${escapeHtml(taskMetrics(data))}</span><span class="stream-phase" data-live-phase-label>${escapeHtml(phaseLabel(data))}</span></div>
      <details class="live-output"><summary><span>${escapeHtml(state.locale === "zh" ? "查看实时输出" : "Live output")}</span><small data-live-output-count>${escapeHtml(streamText ? `${compactNumber(streamText.length)} ${state.locale === "zh" ? "字符（仅显示最近内容）" : "chars (recent content)"}` : "")}</small><span class="live-output-chevron">${icon("chevron-down")}</span></summary><div class="stream-preview" data-live-preview aria-live="polite">${preview}</div></details>
    </div>
  </div>`;
}

function streamTail(text, limit = 800) {
  const value = String(text || "");
  if (value.length <= limit) return value;
  return `${state.locale === "zh" ? "…仅显示最近内容…\n" : "…recent content only…\n"}${value.slice(-limit)}`;
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function toolStatusLabel(status) {
  if (status === "denied") return t("tool.denied");
  if (["error", "failed"].includes(status)) return t("tool.error");
  return t("tool.ok");
}

function traceLabel(event) {
  const labels = state.locale === "zh"
    ? {
        run_started: "范围界定",
        node_entered: "运行节点",
        stage_route: "阶段路由",
        local_evidence_index: "本地证据",
        reasoning_configured: "推理强度",
        image_attached: "视觉输入",
        model_decision: "模型决策",
        model_update: "模型行动说明",
        model_update_history: "此前行动说明",
        tool_round_started: "执行计划",
        tool_round_finished: "结果汇总",
        feedback_observed: "自反馈",
        replan: "重新规划",
        stagnation_replan: "停滞纠偏",
        recovery_probe_finished: "恢复诊断",
        recovery_inspection_passed: "解除写入保护",
        recovery_required_before_finish: "恢复保护",
        recovery_guard: "恢复保护",
        task_stagnation_recovery: "错误路径修复",
        verification_required: "验证门禁",
        verification_observed: "验证证据",
        context_compacted: "上下文压缩",
        provider_retry: "传输重试",
        provider_protocol: "调用协议",
        provider_protocol_fallback: "协议自动回退",
        task_provider_recovery: "任务恢复",
        reasoning_fallback: "参数降级",
         search_circuit_open: "搜索熔断",
         provider_stream_error: "模型流错误",
         completion_complete: "完成评估通过",
         completion_continue: "完成评估继续",
         completion_blocked: "完成评估阻塞",
        completion_unknown: "完成评估不可用",
        verification_passed: "验证通过",
        verification_failed: "验证失败",
        verification_skipped: "验证跳过",
        verification_blocked: "验证阻塞",
        reinspect_required: "重新检查",
         completion_judge_retry: "完成评估复查",
         run_finished: "执行结束",
        stagnation_guard: "循环保护",
        max_turns: "轮次上限",
        batch_started: "并行编排",
        auto_orchestration_triggered: "自动编排",
        orchestration_parent_resumed: "主 Agent 接管",
        subagent_finished: "子任务完成",
        batch_merge_started: "结果合并",
        batch_finished: "批量交付",
      }
    : {
        run_started: "Scope",
        node_entered: "Runtime node",
        stage_route: "Stage route",
        local_evidence_index: "Local evidence",
        reasoning_configured: "Reasoning effort",
        image_attached: "Vision input",
        model_decision: "Model decision",
        model_update: "Model update",
        model_update_history: "Earlier updates",
        tool_round_started: "Execution plan",
        tool_round_finished: "Results merged",
        feedback_observed: "Self-feedback",
        replan: "Re-plan",
        stagnation_replan: "Stagnation recovery",
        recovery_probe_finished: "Recovery probe",
        recovery_inspection_passed: "Write guard released",
        recovery_required_before_finish: "Recovery guard",
        recovery_guard: "Recovery guard",
        task_stagnation_recovery: "Task error recovery",
        verification_required: "Verification gate",
        verification_observed: "Verification evidence",
        context_compacted: "Context compaction",
        provider_retry: "Transport retry",
        provider_protocol: "Protocol",
        provider_protocol_fallback: "Protocol fallback",
        task_provider_recovery: "Task recovery",
        reasoning_fallback: "Parameter fallback",
         search_circuit_open: "Search circuit breaker",
         provider_stream_error: "Provider stream error",
         completion_complete: "Completion accepted",
         completion_continue: "Completion needs work",
         completion_blocked: "Completion blocked",
        completion_unknown: "Completion unavailable",
        verification_passed: "Verification passed",
        verification_failed: "Verification failed",
        verification_skipped: "Verification skipped",
        verification_blocked: "Verification blocked",
        reinspect_required: "Re-inspection",
         completion_judge_retry: "Completion retry",
         run_finished: "Execution finished",
        stagnation_guard: "Loop guard",
        max_turns: "Turn limit",
        batch_started: "Parallel orchestration",
        auto_orchestration_triggered: "Auto orchestration",
        orchestration_parent_resumed: "Parent agent resumed",
        subagent_finished: "Subtask finished",
        batch_merge_started: "Result merge",
        batch_finished: "Batch delivery",
      };
  return labels[String(event?.code || "")] || (state.locale === "zh" ? "阶段事件" : "Stage event");
}

function detailValueText(value, limit = 360) {
  if (value == null) return "";
  if (Array.isArray(value)) {
    if (!value.length) return state.locale === "zh" ? "0 项" : "0 items";
    if (value.every((item) => item == null || ["string", "number", "boolean"].includes(typeof item))) {
      return value.map((item) => String(item ?? "")).join(", ");
    }
    return state.locale === "zh" ? `${value.length} 项结构化记录` : `${value.length} structured items`;
  }
  if (typeof value === "object") {
    const pairs = Object.entries(value).slice(0, 3).map(([key, item]) => `${key}: ${detailValueText(item, 80)}`);
    return `{ ${pairs.join("; ")}${Object.keys(value).length > 3 ? "; …" : ""} }`;
  }
  const text = String(value).replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}

function detailJson(value, limit = 12000) {
  let raw;
  try {
    raw = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  } catch {
    raw = String(value ?? "");
  }
  raw = String(raw || "");
  return raw.length > limit ? `${raw.slice(0, limit).trimEnd()}\n… ${state.locale === "zh" ? "详情已截断" : "details truncated"} …` : raw;
}

function structuredDetailMarkup(detail, label = (state.locale === "zh" ? "查看结构化依据" : "View structured evidence")) {
  if (detail == null || (typeof detail === "object" && !Object.keys(detail).length)) return "";
  const raw = detailJson(detail);
  return `<details class="event-detail"><summary>${escapeHtml(label)}<small>${escapeHtml(state.locale === "zh" ? "点击展开" : "click to expand")}</small></summary><pre>${escapeHtml(raw)}</pre></details>`;
}

function traceDetailPreview(event) {
  const detail = event?.detail;
  if (detail == null) return "";
  if (typeof detail !== "object" || Array.isArray(detail)) return detailValueText(detail, 96);
  const labels = state.locale === "zh"
    ? { turn: "轮次", previous_turn: "上一轮", tool_count: "工具", results: "结果", observed: "已观察", observations: "观察", constraints: "约束", failed_tools: "失败", verification_required: "需验证", recovery_inspection_required: "写入保护", assessment: "反馈", trigger: "触发", next_action: "下一步" }
    : { turn: "turn", previous_turn: "previous", tool_count: "tools", results: "results", observed: "observed", observations: "observations", constraints: "constraints", failed_tools: "failed", verification_required: "verify", recovery_inspection_required: "write guard", assessment: "assessment", trigger: "trigger", next_action: "next" };
  const parts = [];
  for (const key of ["turn", "previous_turn", "tool_count", "results", "observed", "observations", "constraints", "failed_tools", "verification_required", "recovery_inspection_required", "assessment", "trigger", "next_action"]) {
    const value = detail[key];
    if (value == null || value === "") continue;
    const compact = Array.isArray(value)
      ? (state.locale === "zh" ? `${value.length} 项` : `${value.length} items`)
      : detailValueText(value, 96);
    if (compact) parts.push(`${labels[key] || key}: ${compact}`);
  }
  return parts.slice(0, 4).join(" · ");
}

function traceEvidenceMarkup(event, detailText, evidenceMarkup) {
  if (detailText == null && !evidenceMarkup) return "";
  const labels = state.locale === "zh"
    ? { feedback_observed: "查看自反馈详情", tool_round_finished: "查看结果汇总详情", replan: "查看重新规划详情", model_decision: "查看模型决策详情" }
    : { feedback_observed: "View self-feedback", tool_round_finished: "View merged results", replan: "View re-plan", model_decision: "View model decision" };
  const label = labels[String(event?.code || "")] || (state.locale === "zh" ? "查看阶段详情" : "View stage details");
  const preview = traceDetailPreview(event);
  const readable = detailText ? `<div class="trace-detail">${escapeHtml(detailText)}</div>` : "";
  return `<details class="trace-evidence"><summary><span>${escapeHtml(label)}</span><small>${escapeHtml(preview)}</small><span class="trace-evidence-chevron">${icon("chevron-down")}</span></summary><div class="trace-evidence-body">${readable}${evidenceMarkup || ""}</div></details>`;
}

function toolResultFoldMarkup(label, content) {
  return `<details class="tool-result-fold"><summary><span>${escapeHtml(label)}</span><small>${escapeHtml(state.locale === "zh" ? "点击展开" : "click to expand")}</small><span class="tool-result-fold-chevron">${icon("chevron-down")}</span></summary><div class="tool-result-fold-body">${content}</div></details>`;
}

function traceDetail(event, options = {}) {
  const detail = event?.detail;
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detailValueText(detail);
  if (typeof detail !== "object") return String(detail);
  const parts = [];
  if (!options.omitText && typeof detail.text === "string" && detail.text) parts.push(detail.text);
  const labels = state.locale === "zh"
    ? {
        turn: "轮次", previous_turn: "上一轮", tool_count: "工具数", tools: "工具", answer_chars: "回答字符", duration_ms: "耗时", duration_seconds: "耗时", count: "数量", names: "名称", statuses: "状态", max_turns: "轮次上限", turn_policy: "轮次策略", child_count: "子任务数", child: "子任务", failed: "失败数", retry: "重试", retry_limit: "重试上限", partial_chars: "已输出字符", error_type: "错误类型", requested: "请求", active: "实际", wire_value: "请求值", task_id: "任务", tokens: "tokens", automatic: "自动", complexity_score: "复杂度", complexity_threshold: "触发线", complexity_reasons: "触发原因", attempt: "评估次数", confidence: "置信度", rationale: "依据", missing: "缺失", next_action: "下一步", evidence: "证据", error: "错误", trigger: "触发原因", observed: "已观察", observations: "观察结果", constraints: "当前约束", basis: "判断依据", public_plan: "公开计划", results: "工具结果", structured_data: "结构化结果", new_information: "新信息", failed_tools: "失败工具", needs_repair: "需要修复", verification_required: "需要验证", assessment: "反馈判断", replan_trigger: "重规划触发", parallel_mode: "并行模式", max_concurrency: "并发度", dependency_shape: "依赖结构", merge_strategy: "合并策略", parallel_results: "并行结果", merge_basis: "合并依据", result_summary: "结果摘要", turns: "轮次", tool_calls: "工具调用"
      }
    : {
        turn: "turn", previous_turn: "previous turn", tool_count: "tools", tools: "tools", answer_chars: "answer chars", duration_ms: "duration", duration_seconds: "duration", count: "count", names: "names", statuses: "statuses", max_turns: "turn limit", turn_policy: "turn policy", child_count: "children", child: "child", failed: "failed", retry: "retry", retry_limit: "retry limit", partial_chars: "partial chars", error_type: "error type", requested: "requested", active: "active", wire_value: "wire", task_id: "task", tokens: "tokens", automatic: "automatic", complexity_score: "complexity", complexity_threshold: "threshold", complexity_reasons: "reasons", attempt: "review attempt", confidence: "confidence", rationale: "rationale", missing: "missing", next_action: "next action", evidence: "evidence", error: "error", trigger: "trigger", observed: "observed", observations: "observations", constraints: "constraints", basis: "basis", public_plan: "public plan", results: "tool results", structured_data: "structured evidence", new_information: "new information", failed_tools: "failed tools", needs_repair: "needs repair", verification_required: "verification required", assessment: "assessment", replan_trigger: "re-plan trigger", parallel_mode: "parallel mode", max_concurrency: "concurrency", dependency_shape: "dependency shape", merge_strategy: "merge strategy", parallel_results: "parallel results", merge_basis: "merge basis", result_summary: "result summary", turns: "turns", tool_calls: "tool calls"
      };
  const keys = ["turn", "previous_turn", "tool_count", "tools", "answer_chars", "duration_ms", "duration_seconds", "count", "names", "statuses", "max_turns", "turn_policy", "child_count", "child", "failed", "retry", "retry_limit", "partial_chars", "error_type", "requested", "active", "wire_value", "task_id", "tokens", "automatic", "complexity_score", "complexity_threshold", "complexity_reasons", "attempt", "confidence", "rationale", "missing", "next_action", "evidence", "error", "trigger", "observed", "observations", "constraints", "basis", "public_plan", "results", "structured_data", "new_information", "failed_tools", "needs_repair", "verification_required", "assessment", "replan_trigger", "parallel_mode", "max_concurrency", "dependency_shape", "merge_strategy", "parallel_results", "merge_basis", "result_summary", "turns", "tool_calls"];
  for (const key of keys) {
    if (detail[key] == null) continue;
    parts.push(`${labels[key] || key}: ${detailValueText(detail[key])}`);
  }
  return parts.join(" · ");
}

function shortEventText(event, limit = 150) {
  const publicUpdate = event?.code === "model_update" && typeof event?.detail?.text === "string"
    ? event.detail.text
    : "";
  const text = String(publicUpdate || event?.summary || traceDetail(event) || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}

function rawOutputMarkup(streamText) {
  const text = streamTail(String(streamText || ""), 1200);
  // The raw stream dump must read as literal text; the light renderer keeps
  // partial/broken Markdown from being re-parsed into misleading blocks.
  return text ? `<details class="raw-output"><summary>${escapeHtml(state.locale === "zh" ? "原始模型输出" : "Raw model output")}</summary><div>${formatLightText(text)}</div></details>` : "";
}

function isToolEvent(event) {
  return event?.kind === "tool" || (event?.name && event?.kind !== "trace");
}

function eventImportance(event) {
  const code = String(event?.code || "");
  const status = String(event?.status || "").toLowerCase();
  if (["error", "failed", "denied", "cancelled", "interrupted"].includes(status) || /error|failed|denied|blocked|recovery|retry|fallback|max_turns|stagnation/.test(code)) return "high";
  if (/model_update|replan|verification|completion_|run_finished|batch_/.test(code)) return "medium";
  return "low";
}

function normalizeModelUpdateEvents(events) {
  const normalized = [];
  let previous = "";
  for (const source of Array.isArray(events) ? events : []) {
    if (source?.code !== "model_update" || typeof source?.detail?.text !== "string") {
      normalized.push(source);
      continue;
    }
    const current = source.detail.text.trim();
    if (!current) continue;
    let delta = current;
    if (previous && current.startsWith(previous)) delta = current.slice(previous.length);
    else if (previous && previous.startsWith(current)) delta = "";
    previous = current.length >= previous.length || !current.startsWith(previous) ? current : previous;
    if (!delta) continue;
    normalized.push({ ...source, detail: { ...source.detail, text: delta } });
  }
  return normalized;
}

function visibleAgentEvents(events) {
  const visible = [];
  let previousKey = "";
  for (const event of normalizeModelUpdateEvents(events)) {
    const key = [event?.kind, event?.code, event?.name, event?.status, shortEventText(event, 90), event?.path || ""].join("|");
    if (key !== previousKey) visible.push(event);
    previousKey = key;
  }
  return visible;
}

function compactModelUpdateEvents(events) {
  const visible = visibleAgentEvents(events);
  const updateIndexes = visible
    .map((event, index) => event?.code === "model_update" ? index : -1)
    .filter((index) => index >= 0);
  if (updateIndexes.length <= 1) return visible;
  const latestIndex = updateIndexes[updateIndexes.length - 1];
  const firstIndex = updateIndexes[0];
  const previousUpdates = updateIndexes
    .slice(0, -1)
    .map((index) => String(visible[index]?.detail?.text || "").trim())
    .filter(Boolean);
  const historyEvent = {
    ...visible[firstIndex],
    code: "model_update_history",
    summary: state.locale === "zh"
      ? `此前行动说明 · ${previousUpdates.length} 条`
      : `Earlier action updates · ${previousUpdates.length}`,
    detail: { count: previousUpdates.length, updates: previousUpdates },
  };
  return visible.filter((_event, index) => !updateIndexes.includes(index) || index === firstIndex || index === latestIndex)
    .map((event, index, compacted) => {
      // The first retained model slot is the folded history entry; the last
      // one remains the only public action block shown at full size.
      if (event?.code === "model_update" && event !== visible[latestIndex]) {
        return historyEvent;
      }
      return event;
    });
}

function eventTimelineSummary(events) {
  const visible = visibleAgentEvents(events);
  const tools = visible.filter(isToolEvent).length;
  const alerts = visible.filter((event) => eventImportance(event) === "high").length;
  return state.locale === "zh" ? `${tools} 次操作${alerts ? ` · ${alerts} 项需关注` : ""}` : `${tools} actions${alerts ? ` · ${alerts} alerts` : ""}`;
}

function summarizeRound(items, roundNumber) {
  const tools = items.filter(isToolEvent);
  const failed = tools.some((event) => ["error", "failed", "denied"].includes(String(event.status || "").toLowerCase()));
  const names = [...new Set(tools.map((event) => String(event.name || "tool")).filter(Boolean))];
  const detail = names.slice(0, 4).join(" · ") || (state.locale === "zh" ? "整理执行步骤" : "Organized execution steps");
  return { failed, detail, title: state.locale === "zh" ? `第 ${roundNumber} 组命令 · ${tools.length} 条` : `Command group ${roundNumber} · ${tools.length} commands`, status: failed ? (state.locale === "zh" ? "需处理" : "Needs attention") : (state.locale === "zh" ? "已完成" : "Complete") };
}

function toolResultMarkup(event) {
  const output = String(event.output || "").trim();
  const observation = String(event.observation || "").trim();
  const data = event.data && typeof event.data === "object" ? event.data : null;
  const metadata = [
    event.risk ? `${state.locale === "zh" ? "风险" : "risk"}: ${event.risk}` : "",
    event.exit_code != null ? `exit ${event.exit_code}` : "",
    event.duration_ms != null ? `${Number(event.duration_ms).toFixed(1)} ms` : "",
    event.truncated ? (state.locale === "zh" ? "输出已截断" : "output truncated") : "",
    event.write ? (state.locale === "zh" ? "已写入工作区" : "workspace write") : "",
    Array.isArray(event.security_tags) && event.security_tags.length ? event.security_tags.join(", ") : "",
  ].filter(Boolean);
  const metadataMarkup = metadata.length
    ? `<div class="tool-result-meta">${metadata.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`
    : "";
  const observationMarkup = observation
    ? toolResultFoldMarkup(t("tool.observation"), `<div class="tool-result-observation">${formatText(observation)}</div>`)
    : "";
  const outputMarkup = output
    ? toolResultFoldMarkup(t("tool.result"), `<div class="tool-result-output">${formatText(output)}</div>`)
    : `<div class="tool-result-empty">${escapeHtml(t("tool.empty"))}</div>`;
  const commandMarkup = event.command
    ? toolResultFoldMarkup(state.locale === "zh" ? "执行命令" : "Command", `<code class="tool-command">${escapeHtml(event.command)}</code>`)
    : "";
  const dataMarkup = data && Object.keys(data).length
    ? toolResultFoldMarkup(t("tool.structured"), `<pre class="tool-result-json">${escapeHtml(detailJson(data, 10000))}</pre>`)
    : "";
  const results = Array.isArray(data?.results) ? data.results : [];
  const resultMarkup = results.length ? toolResultFoldMarkup(t("tool.searchResults"), `<div class="web-results">${results.map((result) => {
    const href = safeExternalUrl(result.url);
    return href ? `<a class="web-result" href="${escapeHtml(href)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(result.title || result.url)}</strong><small>${escapeHtml(result.snippet || result.url)}</small><span>${escapeHtml(t("tool.openSource"))} ↗</span></a>` : "";
  }).join("")}</div>`) : "";
  return `<div class="tool-event-details">${metadataMarkup}${observationMarkup}${outputMarkup}${commandMarkup}${dataMarkup}${resultMarkup}</div>`;
}

function toolEventHtml(event, animate = false, anchor = "", open = false) {
  const name = String(event.name || "tool");
  const status = String(event.status || "ok");
  if (event.kind === "trace" || event.kind === "state") {
    const traceClass = status === "error" ? "trace-error" : "trace-ok";
    const detail = traceDetail(event, { omitText: event.code === "model_update" });
    const publicText = event.code === "model_update" && typeof event.detail?.text === "string" ? event.detail.text : "";
    const tracePhase = event.code === "run_finished" ? "review" : event.phase;
    const isModelEvent = String(event.code || "") === "model_update";
    const summary = isModelEvent && event.code === "model_update"
      ? (state.locale === "zh" ? `行动说明 · 第 ${event.detail?.turn || ""} 轮` : `Action · turn ${event.detail?.turn || ""}`)
      : String(event.summary || traceLabel(event));
    const publicMarkup = publicText ? `<div class="trace-public-plan"><span>${escapeHtml(state.locale === "zh" ? "公开行动" : "Public action")}</span><div>${formatText(publicText)}</div></div>` : "";
    const evidence = structuredDetailMarkup(event.detail, state.locale === "zh" ? "查看完整依据" : "View full evidence");
    const detailMarkup = traceEvidenceMarkup(event, detail, evidence);
    const thinkingLabel = state.locale === "zh" ? "思考" : "Thinking";
    const blockClass = isModelEvent ? "thinking-block " : "";
    const historyClass = String(event.code || "") === "model_update_history" ? " thinking-history" : "";
    const traceAnchor = anchor || event.event_id || event.item_id || `${event.code || "stage"}-${event.created_at_epoch || ""}`;
    const thinkingMarkup = isModelEvent ? `<span class="thinking-label">${escapeHtml(thinkingLabel)}</span>` : "";
    const summaryMarkup = `<div class="trace-summary">${thinkingMarkup}<span class="trace-code">${escapeHtml(traceLabel(event))}</span><span>${escapeHtml(summary)}</span>${!isModelEvent && traceDetailPreview(event) ? `<small class="trace-fold-preview">${escapeHtml(traceDetailPreview(event))}</small>` : ""}</div>`;
    const iconMarkup = `<span class="trace-icon">${icon(status === "error" ? "alert-triangle" : "sparkles")}</span>`;
    if (!isModelEvent) {
      const itemKind = String(event.code || "") === "model_update_history" ? "reasoning-history" : "stage";
      return `<details class="trace-fold trace-event stage-summary${historyClass} ${traceClass}${animate ? " event-enter" : ""}" data-agent-block="${itemKind === "reasoning-history" ? "thinking-history" : "stage"}" data-agent-item="${escapeHtml(traceAnchor)}" data-item-kind="${itemKind}" data-latest-action="false" data-stage-code="${escapeHtml(event.code || "")}"><summary class="trace-fold-summary">${iconMarkup}<span class="trace-main">${summaryMarkup}</span><span class="trace-phase">${escapeHtml(phaseLabel({ phase: tracePhase }))}</span><span class="trace-fold-chevron">${icon("chevron-down")}</span></summary><div class="trace-fold-body">${publicMarkup}${detailMarkup}</div></details>`;
    }
    const latestAction = event.code === "model_update" && !event.detail?.history;
    return `<div class="trace-event stage-summary ${blockClass}model-event ${traceClass}${animate ? " event-enter" : ""}" data-agent-block="thinking" data-agent-item="${escapeHtml(traceAnchor)}" data-item-kind="reasoning" data-latest-action="${latestAction ? "true" : "false"}" data-stage-code="${escapeHtml(event.code || "")}">${iconMarkup}<div class="trace-main">${summaryMarkup}${publicMarkup}${detailMarkup}</div><span class="trace-phase">${escapeHtml(phaseLabel({ phase: tracePhase }))}</span></div>`;
  }
  const denied = status === "denied";
  const failed = ["error", "failed"].includes(status);
  const lowerName = name.toLowerCase();
  const iconName = denied ? "lock" : failed ? "alert-circle" : name === "web_search" ? "globe-2" : lowerName.includes("test") || name === "bash" ? "test-tube-2" : lowerName.includes("git") ? "git-branch" : "file-search-2";
  const stateClass = denied ? "denied" : failed ? "failed" : "completed";
  const stateIcon = denied ? "lock" : failed ? "alert-circle" : "check";
  const path = String(event.path || "");
  const pathMarkup = path ? `<span class="tool-path tool-path-button" data-open-diff="${escapeHtml(path)}">${escapeHtml(path)}</span>` : `<span class="tool-path">${escapeHtml(toolStatusLabel(status))}</span>`;
  const toolAnchor = anchor || `${name}-${event.created_at_epoch || ""}`;
  return `<details class="tool-event ${stateClass}${animate ? " event-enter" : ""}" data-agent-block="command" data-agent-item="${escapeHtml(event.event_id || event.item_id || toolAnchor)}" data-item-kind="command" data-tool-event="${escapeHtml(toolAnchor)}"${open ? " open" : ""}>
    <summary class="tool-event-summary"><span class="tool-icon ${denied ? "amber-icon" : ""}">${icon(iconName)}</span><span class="tool-event-copy"><span><strong>${escapeHtml(name)}</strong>${pathMarkup}</span><small>${escapeHtml(event.summary || "")}</small></span><span class="tool-check ${denied ? "denied-check" : failed ? "failed-check" : ""}">${icon(stateIcon)}</span><span class="tool-expand">${icon("chevron-down")}</span></summary>
    ${toolResultMarkup(event)}
  </details>`;
}

function eventTimelineMarkup(events, options = {}) {
  if (!Array.isArray(events) || !events.length) return "";
  const sourceEvents = events.length > MAX_RENDERED_TIMELINE_EVENTS
    ? [
        {
          kind: "trace",
          code: "timeline_truncated",
          phase: "planning",
          status: "ok",
          summary: state.locale === "zh"
            ? `较早的 ${events.length - MAX_RENDERED_TIMELINE_EVENTS + 1} 条运行记录已收起`
            : `${events.length - MAX_RENDERED_TIMELINE_EVENTS + 1} earlier runtime records folded`,
          detail: { count: events.length - MAX_RENDERED_TIMELINE_EVENTS + 1 },
        },
        ...events.slice(-(MAX_RENDERED_TIMELINE_EVENTS - 1)),
      ]
    : events;
  // Keep routine lifecycle traces in the task data for audit/replay, but keep
  // the human-facing transcript focused on the latest public action update.
  const hiddenRoutineTraceCodes = new Set(["model_decision", "tool_round_finished", "feedback_observed", "replan"]);
  const items = compactModelUpdateEvents(sourceEvents)
    .filter((event) => !hiddenRoutineTraceCodes.has(String(event?.code || "")))
    .map((event, index) => ({ event, index }));
  const groups = [];
  let currentRound = null;
  let fallbackRound = 0;
  let pendingRound = 0;
  const closeRound = () => { if (currentRound) { groups.push(currentRound); currentRound = null; } };
  const roundNumber = (event) => Number(event?.detail?.turn || pendingRound || currentRound?.turn || ++fallbackRound);
  const startRound = (event) => {
    const normalizedTurn = roundNumber(event);
    if (!currentRound || currentRound.turn !== normalizedTurn) {
      closeRound();
      currentRound = { round: true, turn: normalizedTurn, items: [] };
    }
    return currentRound;
  };
  for (const item of items) {
    const { event } = item;
    const code = String(event?.code || "");
    if (code === "tool_round_started") {
      closeRound();
      pendingRound = Number(event?.detail?.turn || ++fallbackRound);
      continue;
    }
    if (isToolEvent(event)) {
      startRound(event);
      currentRound.items.push(item);
      continue;
    }
    if (code === "tool_round_finished") {
      closeRound();
      groups.push({ round: false, item });
      pendingRound = 0;
      continue;
    }
    closeRound();
    groups.push({ round: false, item });
    pendingRound = 0;
  }
  closeRound();
  return groups.map((group, groupIndex) => {
    if (!group.round) return toolEventHtml(group.item.event, group.item.index >= Number(options.animateFrom ?? events.length), `event-${group.item.index}`);
    const roundKey = String(group.turn || groupIndex + 1);
    const round = summarizeRound(group.items.map(({ event }) => event), roundKey);
    const open = options.openRounds instanceof Set && options.openRounds.has(roundKey);
    const itemMarkup = group.items.map(({ event, index }) => toolEventHtml(event, index >= Number(options.animateFrom ?? events.length), `event-${index}`, options.openTools instanceof Set && options.openTools.has(`event-${index}`))).join("");
    const commandGroupLabel = state.locale === "zh" ? "命令组" : "Commands";
    return `<details class="agent-round command-group" data-agent-block="commands" data-agent-item="round-${escapeHtml(roundKey)}" data-item-kind="command-group" data-command-group="${roundKey}" data-agent-round="${roundKey}"${open ? " open" : ""}><summary class="agent-round-summary"><span class="agent-round-title"><span class="agent-round-icon">${icon(round.failed ? "alert-circle" : "layers-3")}</span><span class="command-group-copy"><span class="command-group-label">${escapeHtml(commandGroupLabel)}</span><strong>${escapeHtml(round.title)}</strong><small>${escapeHtml(round.detail)}</small></span></span><span class="agent-round-meta">${escapeHtml(round.status)}<span class="agent-round-chevron">${icon("chevron-down")}</span></span></summary><div class="agent-round-events">${itemMarkup}</div></details>`;
  }).join("");
}

function assistantMessageMarkup(data, anchor = "") {
  const events = Array.isArray(data.events) ? data.events : [];
  const eventMarkup = eventTimelineMarkup(events);
  const answer = data.answer || data.error || "模型没有返回可交付文字。";
  const rawStream = !data.answer && data.stream_text ? rawOutputMarkup(data.stream_text) : "";
  const execution = executionTrailMarkup(eventMarkup, events);
  const anchorMarkup = anchor ? ` data-chat-anchor="${escapeHtml(anchor)}"` : "";
  return `
    <article class="message assistant-message"${anchorMarkup}>
      <div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div>
      <div class="message-body">${execution}<div class="answer-callout">${formatText(answer)}</div>${rawStream}</div>
    </article>`;
}

function addAssistantMessage(data, loadingId = "") {
  const chatPosition = captureChatPosition();
  const loading = loadingId ? document.getElementById(loadingId) : null;
  const anchor = loadingId ? `live-${loadingId}` : "";
  if (loading) {
    const replacement = document.createElement("div");
    replacement.innerHTML = assistantMessageMarkup(data, anchor);
    loading.replaceWith(replacement.firstElementChild);
  } else {
    $("#messageList").insertAdjacentHTML("beforeend", assistantMessageMarkup(data, anchor));
  }
  state.turns += Number(data.turns || 0);
  state.tools += Number(data.tool_calls_total || 0);
  $("#turnMetric").textContent = state.turns;
  $("#toolMetric").textContent = state.tools;
  updateTaskDock(data);
  refreshIcons();
  persistSessionView();
  restoreChatPosition(chatPosition, false);
}

function showAuthModal(message) {
  const modal = $("#authModal");
  if (!modal) return;
  modal.classList.add("show");
  modal.setAttribute("aria-hidden", "false");
  const errorSlot = $("#authError");
  if (errorSlot) {
    errorSlot.hidden = !message;
    errorSlot.textContent = message || "";
  }
  const input = $("#authTokenInput");
  if (input instanceof HTMLInputElement) {
    window.setTimeout(() => input.focus(), 30);
  }
}

function hideAuthModal() {
  const modal = $("#authModal");
  if (!modal) return;
  modal.classList.remove("show");
  modal.setAttribute("aria-hidden", "true");
}

async function submitAuthToken(event) {
  event.preventDefault();
  const input = $("#authTokenInput");
  if (!(input instanceof HTMLInputElement)) return;
  const token = input.value.trim();
  if (!token) {
    showAuthModal(state.locale === "zh" ? "请粘贴 minicc-web 启动时显示的 token。" : "Paste the token printed by minicc-web.");
    return;
  }
  localStorage.setItem(AUTH_STORAGE_KEY, token);
  // Verify against a guarded route; /api/health is intentionally open.
  const check = await fetch("/api/workspace", {
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => null);
  if (!check || !check.ok) {
    showAuthModal(state.locale === "zh" ? "Token 已保存但验证未通过，请检查后重新粘贴。" : "Token saved but rejected. Check it and retry.");
    return;
  }
  hideAuthModal();
  location.reload();
}
