// NOTE: 源文件分片（web/src/）。此文件由 `npm run build:web` 按序拼接生成，勿直接编辑。
const state = {
  sessionId: localStorage.getItem("minicc-session") || "interview-1",
  allowChanges: localStorage.getItem("minicc-allow") !== "false",
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
  reasoningEffort: ["low", "mid", "high", "xhigh", "max"].includes(localStorage.getItem("minicc-reasoning")) ? localStorage.getItem("minicc-reasoning") : "high",
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
  turns: 12,
  tools: 9,
};

// Keep only a small client-side detail cache; the durable task index is summary-only.
const taskDetailsById = new Map();
const taskDetailLoads = new Map();

// Token auth: the server may require a bearer token (non-loopback bind).
// EventSource cannot send headers, so the token also travels in the query
// string for SSE endpoints only.
const AUTH_STORAGE_KEY = "minicc-web-token";

function getAuthToken() {
  return (localStorage.getItem(AUTH_STORAGE_KEY) || "").trim();
}
function authHeaders() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function authQuery(url) {
  const token = getAuthToken();
  if (!token || url.includes("token=")) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}
