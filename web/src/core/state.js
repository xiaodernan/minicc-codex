// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { BoundedMap, BoundedSet } from "./bounded-cache.js";
import { SESSION_CACHE_PREFIX } from "./session-cache.js";

// The reasoning-effort vocabulary, one home. The Python backend already owns
// REASONING_EFFORTS (minicc/config.py); this is the same fact for the UI,
// and frontend_reasoning_effort_one_home_smoke.mjs pins both spellings.
export const REASONING_EFFORTS = ["low", "mid", "high", "xhigh", "max", "ultra"];

// The permission-mode vocabulary, one home for the UI. The Python backend
// already owns PERMISSION_MODES (minicc/audit.py); this is the same fact for
// the workbench, and frontend_permission_mode_one_home_smoke.mjs pins both
// spellings (plus the static data-mode buttons in index.html).
export const PERMISSION_MODES = ["default", "plan", "acceptEdits", "yolo"];

export const state = {
  sessionId: localStorage.getItem("minicc-session") || "interview-1",
  allowChanges: localStorage.getItem("minicc-allow") === "true",
  allowNetwork: localStorage.getItem("minicc-network") === "true",
  permissionMode: PERMISSION_MODES.includes(localStorage.getItem("minicc-permission-mode"))
    ? localStorage.getItem("minicc-permission-mode")
    : "default",
  locale: localStorage.getItem("minicc-locale") || "zh",
  theme: ["light", "dark"].includes(localStorage.getItem("minicc-theme"))
    ? localStorage.getItem("minicc-theme")
    : "light",
  workspacePath: "",
  workspaceInfo: null,
  contextWindowTokens: 300000,
  model: localStorage.getItem("minicc-model") || "",
  models: [],
  modelCatalogError: "",
  modelCatalogLoading: false,
  reasoningEffort: REASONING_EFFORTS.includes(localStorage.getItem("minicc-reasoning")) ? localStorage.getItem("minicc-reasoning") : "high",
  busy: false,
  submitting: false,
  focusMode: localStorage.getItem("minicc-focus-mode") === "true",
  sidebarCollapsed: localStorage.getItem("minicc-sidebar-collapsed") === "true",
  // Keep the reference three-pane surface visible by default; the inspector remains reversible.
  inspectorCollapsed: localStorage.getItem("minicc-inspector-collapsed") === "true",
  chatRestoreVersion: 0,
  chatUserScrolledAt: 0,
  activeTaskId: null,
  lastTask: null,
  connection: null,
  chatFollow: true,
  attachments: [],
  turns: 0,
  tools: 0,
};

// Keep only a small client-side detail cache; the durable task index is summary-only.
export const taskDetailsById = new Map();
export const taskDetailLoads = new Map();

// Token auth: the server may require a bearer token (non-loopback bind).
// EventSource cannot send headers, so the token also travels in the query
// string for SSE endpoints only.
export const AUTH_STORAGE_KEY = "minicc-web-token";

export function getAuthToken() {
  return (localStorage.getItem(AUTH_STORAGE_KEY) || "").trim();
}
export function authHeaders() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function authQuery(url) {
  const token = getAuthToken();
  if (!token || url.includes("token=")) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}

// The inspector-tab vocabulary, one home for the UI. The three tab buttons
// in index.html and the validator in chat/stream.js both mean exactly
// these; frontend_inspector_tab_one_home_smoke.mjs pins both spellings.
export const INSPECTOR_TABS = ["changes", "files", "verification"];

export const runtime = {
  workspaceVersion: 0,
  inspectorTab: INSPECTOR_TABS[0],
  initialMessageMarkup: "",
  sessionViewReady: false,
  renderedTaskListKey: "",
  changeRefreshTimer: 0,
  latestTodos: null,
};

export const sessionMarkup = new BoundedMap(24);
export const taskHistoryBySession = new Map();
export const taskHistoryListBySession = new Map();
export const SESSION_VIEW_PREFIX = SESSION_CACHE_PREFIX;
export const TERMINAL_TASK_STATUSES = new Set(["completed", "failed", "cancelled", "interrupted"]);
// M8-T372: the task statuses, mirroring ``TASK_STATUSES`` in
// ``minicc/agent/protocol.py``.  The "still running" question used to be
// written out by hand in five places in this tree as well as seven in the
// backend; it is derived here from the two facts that already have names,
// exactly as the backend derives it.
export const TASK_STATUSES = new Set([
  "queued", "running", "completed", "failed", "cancelled", "interrupted",
]);
export const ACTIVE_TASK_STATUSES = new Set(
  [...TASK_STATUSES].filter((status) => !TERMINAL_TASK_STATUSES.has(status)),
);
// M8-T370: the phases the backend can report.  The backend emits more than
// the four terminal statuses: ``review`` (the review stage), ``verify``,
// ``repair``, ``execution`` and ``permission`` are all real phases, and the
// live-task element carries one CSS class per phase.  The list used to be
// written out by hand in two places, and the two copies had already drifted
// - one knew about ``review`` and the other did not - so a class for a
// phase that was never listed was never removed, and the element kept
// ``live-task-review`` for the rest of the task's life.  One home.
export const TASK_PHASES = new Set([
  "queued", "planning", "intake", "tool", "execution", "answering", "summarize",
  "review", "verify", "repair", "permission", "merging",
  "completed", "failed", "cancelled", "interrupted",
]);
// The phases that mean "the task is still doing something" - the ones the
// live-task element styles as in-flight. Derived from the two facts that
// already have names, exactly as ACTIVE_TASK_STATUSES is derived from
// TASK_STATUSES - so a new in-flight phase is missed nowhere.
export const ACTIVE_TASK_PHASES = new Set(
  [...TASK_PHASES].filter((phase) => !TERMINAL_TASK_STATUSES.has(phase)),
);
// The phases that ended without an answer, so the task can be resumed.
export const RESUMABLE_TASK_PHASES = new Set(["failed", "cancelled", "interrupted"]);
// M8-T384: the todo checklist's vocabularies, mirroring ``TODO_STATUSES`` /
// ``TODO_PRIORITIES`` in ``minicc/tools/todo.py``.  The backend validates
// every entry against those tuples and the tool schema advertises them, so
// the panel's normalizer must agree with them: a status the backend rejects
// must not be rendered as if it were legal.  One home per vocabulary.
export const TODO_STATUSES = new Set(["pending", "in_progress", "completed"]);
export const TODO_PRIORITIES = new Set(["high", "medium", "low"]);
// The session-view and event-retention caps live in their one homes
// (session-cache.js owns the per-view markup cap; bounded-cache.js owns
// the event-identity cap). Re-exported here so existing importers keep
// working - new consumers should import from the homes.
export { MAX_SESSION_VIEW_CHARS } from "./session-cache.js";
export { MAX_SEEN_EVENT_KEYS } from "./bounded-cache.js";
export const MAX_RENDERED_TIMELINE_EVENTS = 240;

export const $ = (selector) => document.querySelector(selector);
export const $$ = (selector) => [...document.querySelectorAll(selector)];
export const liveStreamStates = new Map();
export const taskEventSources = new Map();
export const taskWatchers = new Map();
export const runningTasks = new Map();
export const taskBySession = new Map();
export const taskTimerHandles = new Map();
export const finalizedTaskIds = new BoundedSet(2048);
export const renderedHistoryKeys = new BoundedMap(48);
