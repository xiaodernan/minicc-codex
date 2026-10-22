// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { BoundedMap, BoundedSet } from "./bounded-cache.js";
import { SESSION_CACHE_PREFIX } from "./session-cache.js";

export const state = {
  sessionId: localStorage.getItem("minicc-session") || "interview-1",
  allowChanges: localStorage.getItem("minicc-allow") === "true",
  allowNetwork: localStorage.getItem("minicc-network") === "true",
  permissionMode: ["default", "plan", "acceptEdits", "yolo"].includes(localStorage.getItem("minicc-permission-mode"))
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
  reasoningEffort: ["low", "mid", "high", "xhigh", "max", "ultra"].includes(localStorage.getItem("minicc-reasoning")) ? localStorage.getItem("minicc-reasoning") : "high",
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

export const runtime = {
  workspaceVersion: 0,
  inspectorTab: "changes",
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
// live-task element styles as in-flight.
export const ACTIVE_TASK_PHASES = new Set([
  "queued", "planning", "intake", "tool", "execution", "answering", "summarize",
  "review", "verify", "repair", "permission", "merging",
]);
// The phases that ended without an answer, so the task can be resumed.
export const RESUMABLE_TASK_PHASES = new Set(["failed", "cancelled", "interrupted"]);
export const MAX_SESSION_VIEW_CHARS = 180_000;
export const MAX_SEEN_EVENT_KEYS = 2048;
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
