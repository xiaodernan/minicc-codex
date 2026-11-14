(() => {
  // web/src/core/bounded-cache.js
  var MAX_SEEN_EVENT_KEYS = 2048;
  var BoundedMap = class extends Map {
    constructor(limit) {
      super();
      this.limit = limit;
    }
    set(key, value) {
      if (this.has(key)) this.delete(key);
      super.set(key, value);
      while (this.size > this.limit) this.delete(this.keys().next().value);
      return this;
    }
  };
  var BoundedSet = class extends Set {
    constructor(limit) {
      super();
      this.limit = limit;
    }
    add(value) {
      if (this.has(value)) this.delete(value);
      super.add(value);
      while (this.size > this.limit) this.delete(this.values().next().value);
      return this;
    }
  };

  // web/src/core/session-cache.js
  var SESSION_CACHE_PREFIX = "minicc-session-view:";
  var INDEX_KEY = "minicc-session-cache-index-v1";
  var MAX_SESSION_VIEW_CHARS = 18e4;
  var MAX_ENTRIES = 24;
  var MAX_TOTAL_CHARS = 12e5;
  function storeSessionMarkup(key, markup) {
    try {
      const storage = window.localStorage;
      let order;
      try {
        order = JSON.parse(storage.getItem(INDEX_KEY) || "[]");
      } catch {
        order = [];
      }
      const existing = Object.keys(storage).filter((item) => item.startsWith(SESSION_CACHE_PREFIX) && item !== key);
      const available = new Set(existing);
      order = [...new Set((Array.isArray(order) ? order : []).filter((item) => available.has(item)).concat(existing))];
      const sizes = new Map(order.map((item) => [item, (storage.getItem(item) || "").length]));
      let total = [...sizes.values()].reduce((sum, size) => sum + size, 0);
      const evict = () => {
        const oldest = order.shift();
        if (oldest === void 0) return false;
        total -= sizes.get(oldest) || 0;
        storage.removeItem(oldest);
        return true;
      };
      const source = String(markup || "");
      if (!source || source.length > MAX_SESSION_VIEW_CHARS) storage.removeItem(key);
      else {
        while (order.length >= MAX_ENTRIES || total + source.length > MAX_TOTAL_CHARS) if (!evict()) break;
        while (true) {
          try {
            storage.setItem(key, source);
            order.push(key);
            break;
          } catch {
            if (!evict()) {
              storage.removeItem(key);
              break;
            }
          }
        }
      }
      storage.setItem(INDEX_KEY, JSON.stringify(order));
    } catch {
    }
  }

  // web/src/core/state.js
  var REASONING_EFFORTS = ["low", "mid", "high", "xhigh", "max", "ultra"];
  var PERMISSION_MODES = ["default", "plan", "acceptEdits", "yolo"];
  var state = {
    sessionId: localStorage.getItem("minicc-session") || "interview-1",
    allowChanges: localStorage.getItem("minicc-allow") === "true",
    allowNetwork: localStorage.getItem("minicc-network") === "true",
    permissionMode: PERMISSION_MODES.includes(localStorage.getItem("minicc-permission-mode")) ? localStorage.getItem("minicc-permission-mode") : "default",
    locale: localStorage.getItem("minicc-locale") || "zh",
    theme: ["light", "dark"].includes(localStorage.getItem("minicc-theme")) ? localStorage.getItem("minicc-theme") : "light",
    workspacePath: "",
    workspaceInfo: null,
    contextWindowTokens: 3e5,
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
    tools: 0
  };
  var taskDetailsById = /* @__PURE__ */ new Map();
  var taskDetailLoads = /* @__PURE__ */ new Map();
  var AUTH_STORAGE_KEY = "minicc-web-token";
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
  var INSPECTOR_TABS = ["changes", "files", "verification"];
  var runtime = {
    workspaceVersion: 0,
    inspectorTab: INSPECTOR_TABS[0],
    initialMessageMarkup: "",
    sessionViewReady: false,
    renderedTaskListKey: "",
    changeRefreshTimer: 0,
    latestTodos: null
  };
  var sessionMarkup = new BoundedMap(24);
  var taskHistoryBySession = /* @__PURE__ */ new Map();
  var taskHistoryListBySession = /* @__PURE__ */ new Map();
  var SESSION_VIEW_PREFIX = SESSION_CACHE_PREFIX;
  var TERMINAL_TASK_STATUSES = /* @__PURE__ */ new Set(["completed", "failed", "cancelled", "interrupted"]);
  var TASK_STATUSES = /* @__PURE__ */ new Set([
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted"
  ]);
  var ACTIVE_TASK_STATUSES = new Set(
    [...TASK_STATUSES].filter((status) => !TERMINAL_TASK_STATUSES.has(status))
  );
  var TASK_PHASES = /* @__PURE__ */ new Set([
    "queued",
    "planning",
    "intake",
    "tool",
    "execution",
    "answering",
    "summarize",
    "review",
    "verify",
    "repair",
    "permission",
    "merging",
    "completed",
    "failed",
    "cancelled",
    "interrupted"
  ]);
  var ACTIVE_TASK_PHASES = new Set(
    [...TASK_PHASES].filter((phase) => !TERMINAL_TASK_STATUSES.has(phase))
  );
  var RESUMABLE_TASK_PHASES = /* @__PURE__ */ new Set(["failed", "cancelled", "interrupted"]);
  var TODO_STATUSES = /* @__PURE__ */ new Set(["pending", "in_progress", "completed"]);
  var TODO_PRIORITIES = /* @__PURE__ */ new Set(["high", "medium", "low"]);
  var MAX_RENDERED_TIMELINE_EVENTS = 240;
  var $ = (selector) => document.querySelector(selector);
  var $$ = (selector) => [...document.querySelectorAll(selector)];
  var liveStreamStates = /* @__PURE__ */ new Map();
  var taskEventSources = /* @__PURE__ */ new Map();
  var taskWatchers = /* @__PURE__ */ new Map();
  var runningTasks = /* @__PURE__ */ new Map();
  var taskBySession = /* @__PURE__ */ new Map();
  var taskTimerHandles = /* @__PURE__ */ new Map();
  var finalizedTaskIds = new BoundedSet(2048);
  var renderedHistoryKeys = new BoundedMap(48);

  // web/src/core/transport.js
  async function requestJson(url, options = {}, timeoutMs = 15e3) {
    const controller = new AbortController();
    let timedOut = false;
    const cancel = () => controller.abort(options.signal?.reason);
    if (options.signal?.aborted) cancel();
    else options.signal?.addEventListener("abort", cancel, { once: true });
    const timer = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    try {
      const headers = new Headers(authHeaders());
      new Headers(options.headers || {}).forEach((value, key) => headers.set(key, value));
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal
      });
      const data = response.status === 204 ? {} : await response.json().catch((error) => {
        if (controller.signal.aborted) throw controller.signal.reason || error;
        if (response.ok) throw new Error(state.locale === "zh" ? "\u670D\u52A1\u5668\u8FD4\u56DE\u4E86\u65E0\u6548\u6570\u636E\uFF0C\u8BF7\u91CD\u8BD5\u3002" : "The server returned invalid data. Please retry.");
        return {};
      });
      if (!response.ok) {
        if (response.status === 401 && data.auth_required) {
          window.dispatchEvent(new CustomEvent("minicc-auth-required"));
          throw new Error(state.locale === "zh" ? "\u9700\u8981\u8BBF\u95EE token\uFF0C\u8BF7\u5728\u5F39\u7A97\u4E2D\u7C98\u8D34\u540E\u91CD\u8BD5\u3002" : "Access token required. Paste it in the dialog and retry.");
        }
        throw new Error(data.error || `${response.status} ${response.statusText}`);
      }
      return data;
    } catch (error) {
      if (timedOut) throw new Error(state.locale === "zh" ? "\u8BF7\u6C42\u8D85\u65F6\uFF0C\u53EF\u5237\u65B0\u5DE5\u4F5C\u533A\u91CD\u8BD5\uFF1B\u8FD0\u884C\u4E2D\u7684\u4EFB\u52A1\u4ECD\u4F1A\u7EE7\u7EED\u3002" : "Request timed out. Refresh to retry; running tasks continue.");
      throw error;
    } finally {
      window.clearTimeout(timer);
      options.signal?.removeEventListener("abort", cancel);
    }
  }

  // web/src/core/arcade.js
  var pending;
  async function openArcade() {
    if (!window.openGame) {
      pending || (pending = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = document.querySelector('meta[name="minicc-game-asset"]')?.content || "/game.js";
        script.onload = resolve;
        script.onerror = () => {
          script.remove();
          pending = null;
          reject(new Error("Unable to load arcade"));
        };
        document.head.append(script);
      }));
      await pending;
    }
    window.openGame?.();
  }

  // web/src/core/scope.js
  function captureViewScope() {
    return { workspacePath: state.workspacePath, sessionId: state.sessionId, workspaceVersion: runtime.workspaceVersion };
  }
  function isWorkspaceScopeCurrent(scope) {
    return scope.workspacePath === state.workspacePath && scope.workspaceVersion === runtime.workspaceVersion;
  }
  function isViewScopeCurrent(scope) {
    return isWorkspaceScopeCurrent(scope) && scope.sessionId === state.sessionId;
  }

  // web/src/core/i18n.js
  var I18N = {
    zh: {
      "restore.partial": "\u5DF2\u6062\u590D\u53EF\u5B89\u5168\u6062\u590D\u7684\u6587\u4EF6\uFF0C\u4EE5\u4E0B\u6587\u4EF6\u6709\u540E\u7EED\u4FEE\u6539\u6216\u65E0\u6CD5\u6062\u590D\uFF0C\u5DF2\u4FDD\u7559",
      "tasks.historyLoading": "\u6B63\u5728\u52A0\u8F7D\u4EFB\u52A1\u2026",
      "inspector.filesTab": "\u6587\u4EF6",
      "inspector.verification": "\u9A8C\u8BC1",
      "capability.executeToggle": "\u5199\u5165\u4E0E\u547D\u4EE4",
      "capability.network": "\u8054\u7F51",
      "start.explore": "\u4E86\u89E3\u9879\u76EE",
      "start.exploreHint": "\u5B9A\u4F4D\u5165\u53E3\u3001\u7ED3\u6784\u548C\u5173\u952E\u6D41\u7A0B",
      "start.fix": "\u68C0\u67E5\u53D8\u66F4",
      "start.fixHint": "\u627E\u51FA\u6F5C\u5728\u56DE\u5F52\u548C\u6539\u8FDB\u673A\u4F1A",
      "start.verify": "\u9A8C\u8BC1\u7ED3\u679C",
      "start.verifyHint": "\u5BF9\u6700\u8FD1\u6539\u52A8\u8FD0\u884C\u5B9A\u5411\u68C0\u67E5",
      "start.explorePrompt": "\u5148\u9605\u8BFB\u5F53\u524D\u9879\u76EE\uFF0C\u8BF4\u660E\u5165\u53E3\u3001\u67B6\u6784\u548C\u5173\u952E\u4E1A\u52A1\u6D41\u7A0B\uFF0C\u4E0D\u4FEE\u6539\u6587\u4EF6\u3002",
      "start.fixPrompt": "\u5BA1\u67E5\u6700\u8FD1\u7684\u4EE3\u7801\u53D8\u66F4\uFF0C\u5B9A\u4F4D\u6F5C\u5728\u56DE\u5F52\u5E76\u7ED9\u51FA\u6709\u4EE3\u7801\u4F9D\u636E\u7684\u6539\u8FDB\u5EFA\u8BAE\u3002",
      "start.verifyPrompt": "\u9488\u5BF9\u6700\u8FD1\u53D8\u66F4\u9009\u62E9\u5FC5\u8981\u7684\u5B9A\u5411\u68C0\u67E5\uFF0C\u6267\u884C\u5E76\u8BF4\u660E\u7ED3\u679C\uFF0C\u4E0D\u9ED8\u8BA4\u8FD0\u884C\u5168\u91CF\u6D4B\u8BD5\u3002",
      "brand.caption": "\u672C\u5730\u667A\u80FD\u5DE5\u4F5C\u53F0",
      "newTask.label": "\u65B0\u4EFB\u52A1",
      "newTask.title": "\u521B\u5EFA\u4E00\u4E2A\u65B0\u4EFB\u52A1",
      "search.placeholder": "\u641C\u7D22\u4EFB\u52A1",
      "search.global": "\u5168\u5C40\u641C\u7D22",
      "search.globalPlaceholder": "\u641C\u7D22\u5168\u90E8\u4F1A\u8BDD\u5386\u53F2\u2026",
      "search.hint": "\u8F93\u5165\u5173\u952E\u8BCD\uFF0C\u5728\u6240\u6709\u5DE5\u4F5C\u533A\u7684\u4EFB\u52A1\u5386\u53F2\u4E2D\u67E5\u627E\u3002",
      "search.searching": "\u641C\u7D22\u4E2D\u2026",
      "search.noResults": "\u6CA1\u6709\u5339\u914D\u7684\u5386\u53F2\u8BB0\u5F55",
      "search.matches": "\u5904\u5339\u914D",
      "nav.main": "\u4E3B\u5BFC\u822A",
      "nav.tasks": "\u4EFB\u52A1",
      "nav.workspaces": "\u5DE5\u4F5C\u533A",
      "nav.promo": "\u5BA3\u4F20\u9875",
      "nav.activity": "\u6D3B\u52A8",
      "nav.ledger": "\u8D26\u672C",
      "nav.arcade": "\u5C0F\u6E38\u620F",
      language: "\u754C\u9762\u8BED\u8A00",
      "tasks.more": "\u66F4\u591A\u4EFB\u52A1",
      "workspace.connected": "\u672C\u5730\u670D\u52A1\u5DF2\u8FDE\u63A5",
      "profile.label": "\u5F53\u524D\u6A21\u5F0F",
      "inspector.toggle": "\u5207\u6362\u68C0\u67E5\u5668",
      "inspector.close": "\u5173\u95ED\u68C0\u67E5\u5668",
      "focus.enter": "\u4E13\u6CE8\u9605\u8BFB",
      "focus.exit": "\u9000\u51FA\u4E13\u6CE8\u9605\u8BFB",
      "options.open": "\u66F4\u591A\u9009\u9879",
      "composer.inputLabel": "\u8F93\u5165\u4EFB\u52A1",
      "composer.allowChanges": "\u5141\u8BB8\u5F53\u524D\u4EFB\u52A1\u4FEE\u6539\u6587\u4EF6\u6216\u6267\u884C\u547D\u4EE4",
      "composer.allowNetwork": "\u5141\u8BB8\u5F53\u524D\u4EFB\u52A1\u8054\u7F51\u641C\u7D22",
      "cancel.title": "\u53D6\u6D88\u4EFB\u52A1",
      "send.title": "\u53D1\u9001\u4EFB\u52A1",
      "files.refresh": "\u5237\u65B0\u6587\u4EF6",
      "sidebar.close": "\u5173\u95ED\u4FA7\u680F",
      "sidebar.open": "\u6253\u5F00\u4FA7\u680F",
      "search.shortcut": "\u641C\u7D22\u5FEB\u6377\u952E",
      recentTasks: "\u6700\u8FD1\u4EFB\u52A1",
      "profile.mode": "\u5DE5\u4F5C\u53F0\u8BBE\u7F6E",
      "profile.local": "\u4EC5\u672C\u5730",
      workspace: "\u5DE5\u4F5C\u533A",
      agentSession: "\u667A\u80FD\u4F1A\u8BDD",
      live: "\u8FD0\u884C\u4E2D",
      "connection.connecting": "\u8FDE\u63A5\u4E2D",
      "connection.connected": "\u5DF2\u8FDE\u63A5",
      "connection.offline": "\u79BB\u7EBF",
      "mode.localSafe": "\u672C\u5730 / \u5B89\u5168",
      "mode.localFull": "\u672C\u5730 / \u5B8C\u5168\u8BBF\u95EE",
      "composer.workingIn": "\u5DE5\u4F5C\u76EE\u5F55",
      "context.empty": "0 / 300k \u4E0A\u4E0B\u6587",
      "context.used": "\u5DF2\u4F7F\u7528 tokens",
      "date.today": "\u4ECA\u5929",
      "composer.placeholder": "\u8BA9 minicc \u68C0\u67E5\u3001\u6784\u5EFA\u6216\u9A8C\u8BC1...",
      "composer.attach": "\u56FE\u7247",
      "quick.plan": "\u8BA1\u5212",
      "quick.review": "\u5BA1\u67E5",
      "quick.verify": "\u9A8C\u8BC1",
      "quick.parallel": "\u5E76\u884C",
      "quick.demo": "\u6F14\u793A\u6D41\u7A0B",
      "mode.safe": "\u5B89\u5168\u6A21\u5F0F",
      "mode.changes": "\u5B8C\u5168\u8BBF\u95EE",
      "composer.fullAccess": "\u5B8C\u5168\u8BBF\u95EE\uFF1AAgent \u53EF\u4EE5\u8BFB\u5199\u6587\u4EF6\u5E76\u6267\u884C\u547D\u4EE4\u3002",
      "composer.readOnly": "\u53D7\u4FDD\u62A4\u5DE5\u4F5C\u533A\uFF1A\u5199\u5165\u548C\u547D\u4EE4\u6267\u884C\u4F1A\u88AB\u8DF3\u8FC7\uFF0C\u9664\u975E\u4F60\u5141\u8BB8\u5F53\u524D\u4EFB\u52A1\u4FEE\u6539\u3002",
      "perm.mode": "\u6743\u9650\u6A21\u5F0F",
      "perm.default": "\u9ED8\u8BA4",
      "perm.plan": "\u8BA1\u5212",
      "perm.acceptEdits": "\u81EA\u52A8\u5199",
      "perm.yolo": "\u5168\u81EA\u52A8",
      "perm.defaultHint": "\u9ED8\u8BA4\uFF1A\u6587\u4EF6\u5199\u5165\u4E0E\u547D\u4EE4\u6267\u884C\u8DDF\u968F\u4E0B\u65B9\u5F00\u5173\u3002",
      "perm.planHint": "\u8BA1\u5212\u6A21\u5F0F\uFF1A\u53EA\u8BFB\u89C4\u5212\uFF0C\u5199\u5165\u4E0E\u547D\u4EE4\u4F1A\u88AB\u62D2\u7EDD\u3002",
      "perm.acceptEditsHint": "\u81EA\u52A8\u5199\uFF1A\u81EA\u52A8\u63A5\u53D7\u6587\u4EF6\u5199\u5165\uFF0C\u547D\u4EE4\u4ECD\u9700\u6388\u6743\u3002",
      "perm.yoloHint": "\u5168\u81EA\u52A8\uFF1A\u5199\u5165\u3001\u547D\u4EE4\u4E0E\u8054\u7F51\u5168\u90E8\u653E\u884C\u3002",
      "todo.title": "\u4EFB\u52A1\u8BA1\u5212",
      "todo.empty": "\u6682\u65E0\u4EFB\u52A1\u8BA1\u5212",
      "todo.toggle": "\u5C55\u5F00\u6216\u6536\u8D77\u4EFB\u52A1\u8BA1\u5212",
      "todo.progressAria": "\u8BA1\u5212\u8FDB\u5EA6",
      "todo.completed": "\u5DF2\u5B8C\u6210",
      "todo.inProgress": "\u8FDB\u884C\u4E2D",
      "todo.pending": "\u5F85\u529E",
      "inspector.overview": "\u6982\u89C8",
      "inspector.changes": "\u6539\u52A8",
      "inspector.files": "\u5173\u6CE8\u6587\u4EF6",
      "protected.title": "\u53D7\u4FDD\u62A4\u5DE5\u4F5C\u533A",
      "inspector.pulse": "\u9879\u76EE\u72B6\u6001",
      "inspector.live": "\u5B9E\u65F6",
      "inspector.ready": "\u5C31\u7EEA",
      "inspector.standingBy": "Agent \u6B63\u5728\u7B49\u5F85",
      "inspector.turns": "\u8F6E\u6B21",
      "inspector.tools": "\u5DE5\u5177",
      "inspector.tokens": "Tokens",
      "inspector.context": "\u4E0A\u4E0B\u6587",
      "inspector.compactions": "\u81EA\u52A8\u538B\u7F29",
      "inspector.cache": "\u7F13\u5B58\u547D\u4E2D",
      "changes.latest": "\u6700\u8FD1\u6539\u52A8",
      "files.main": "CLI \u5165\u53E3",
      "files.loop": "\u5DE5\u5177\u8C03\u7528\u5FAA\u73AF",
      "files.styles": "\u5DE5\u4F5C\u53F0\u754C\u9762",
      "files.readme": "\u9879\u76EE\u6307\u5357",
      "files.tree": "\u6587\u4EF6\u6811",
      "files.loading": "\u6B63\u5728\u52A0\u8F7D\u2026",
      "files.empty": "\u6B64\u76EE\u5F55\u4E3A\u7A7A",
      "files.truncated": "\u6761\u76EE\u8FC7\u591A\uFF0C\u4EC5\u663E\u793A\u90E8\u5206\u5185\u5BB9",
      "files.loadError": "\u6587\u4EF6\u6811\u52A0\u8F7D\u5931\u8D25",
      "at.title": "\u6587\u4EF6\u5F15\u7528",
      "at.empty": "\u6CA1\u6709\u5339\u914D\u7684\u6587\u4EF6",
      "at.commandEmpty": "\u6CA1\u6709\u5339\u914D\u7684\u81EA\u5B9A\u4E49\u547D\u4EE4\uFF08\u653E\u5230 .minicc/commands/*.md\uFF09",
      "at.hint": "\u2191\u2193 \u9009\u62E9 \xB7 Enter \u8865\u5168 \xB7 Esc \u5173\u95ED",
      "approval.title": "\u9700\u8981\u4F60\u7684\u6279\u51C6",
      "approval.allow": "\u5141\u8BB8\u4E00\u6B21",
      "approval.always": "\u672C\u4F1A\u8BDD\u603B\u662F\u5141\u8BB8",
      "approval.deny": "\u62D2\u7EDD",
      "approval.expire": "\u79D2\u540E\u81EA\u52A8\u62D2\u7EDD",
      "approval.reason": "\u539F\u56E0",
      "approval.tool": "\u5DE5\u5177",
      "approval.countdown": "\u5BA1\u6279\u5012\u8BA1\u65F6",
      "protected.subtitle": "\u6BCF\u4E2A\u4EFB\u52A1\u5355\u72EC\u6388\u6743\u5199\u5165",
      "panel.title": "\u5DE5\u4F5C\u53F0",
      "cancel": "\u53D6\u6D88\u4EFB\u52A1",
      "working": "\u6267\u884C\u4E2D",
      "ready": "\u5C31\u7EEA",
      "phase.queued": "\u6392\u961F\u4E2D",
      "phase.planning": "\u6B63\u5728\u89C4\u5212",
      "phase.intake": "\u6B63\u5728\u63A5\u6536\u4EFB\u52A1",
      "phase.summarize": "\u6B63\u5728\u603B\u7ED3",
      "phase.tool": "\u6B63\u5728\u4F7F\u7528\u5DE5\u5177",
      "phase.answering": "\u6B63\u5728\u751F\u6210\u56DE\u7B54",
      "phase.waiting": "\u7B49\u5F85\u6A21\u578B\u8F93\u51FA",
      "phase.review": "\u9A8C\u6536\u4E2D",
      "phase.verify": "\u6B63\u5728\u9A8C\u8BC1",
      "phase.repair": "\u6B63\u5728\u4FEE\u590D",
      "phase.permission": "\u7B49\u5F85\u6388\u6743",
      "phase.execution": "\u6B63\u5728\u6267\u884C",
      "phase.merging": "\u6B63\u5728\u5408\u5E76\u5B50\u4EFB\u52A1",
      "phase.completed": "\u5DF2\u5B8C\u6210",
      "phase.failed": "\u6267\u884C\u5931\u8D25",
      "phase.cancelled": "\u5DF2\u53D6\u6D88",
      "phase.interrupted": "\u670D\u52A1\u91CD\u542F\u65F6\u4E2D\u65AD",
      "stream.live": "\u5B9E\u65F6\u56DE\u7B54",
      "stream.connected": "\u5B9E\u65F6\u8FDE\u63A5",
      "stream.reconnecting": "\u5B9E\u65F6\u8FDE\u63A5\u4E2D\u65AD\uFF0C\u6B63\u5728\u91CD\u8FDE",
      "stream.polling": "\u5B9E\u65F6\u8FDE\u63A5\u4E0D\u53EF\u7528\uFF0C\u6B63\u5728\u8F6E\u8BE2",
      "stream.toolForming": "\u751F\u6210\u4E2D",
      "stream.reasoningForming": "\u63A8\u7406\u4E2D",
      "stream.charsUnit": "\u5B57\u7B26",
      "tasks.center": "\u4EFB\u52A1\u4E2D\u5FC3",
      "tasks.open": "\u6253\u5F00\u4EFB\u52A1",
      "tasks.resume": "\u91CD\u65B0\u8FD0\u884C",
      "tasks.children": "\u5B50\u4EFB\u52A1",
      "tasks.tokens": "tokens",
      "tasks.context": "\u4E0A\u4E0B\u6587",
      "tasks.cache": "\u7F13\u5B58",
      "tasks.cacheUnreported": "\u672A\u7EDF\u8BA1",
      "tasks.cacheReported": "\u5DF2\u8FD4\u56DE",
      "tasks.compacted": "\u6B21\u538B\u7F29",
      "tasks.allWorkspaces": "\u6240\u6709\u5DE5\u4F5C\u533A",
      "tasks.noHistory": "\u8FD8\u6CA1\u6709\u4EFB\u52A1\u8BB0\u5F55",
      "tasks.jumpLatest": "\u8DF3\u5230\u6700\u65B0",
      "tasks.following": "\u8DDF\u968F\u6700\u65B0\u8F93\u51FA",
      "tasks.paused": "\u5DF2\u6682\u505C\u81EA\u52A8\u6EDA\u52A8",
      "tasks.runtime": "\u8FD0\u884C\u65F6\u6307\u6807",
      "tasks.repairs": "\u4FEE\u590D\u6B21\u6570",
      "tasks.verifications": "\u9A8C\u8BC1\u6B21\u6570",
      "tasks.traces": "Trace \u4E8B\u4EF6",
      "tasks.workflow": "\u5DE5\u4F5C\u6D41",
      "tool.ok": "\u5B8C\u6210",
      "tool.error": "\u5931\u8D25",
      "tool.denied": "\u5DF2\u963B\u6B62",
      "tool.searchResults": "\u641C\u7D22\u6765\u6E90",
      "tool.openSource": "\u6253\u5F00\u6765\u6E90",
      "tool.round": "\u5DE5\u5177\u8F6E\u6B21",
      "tool.callCount": "\u6B21\u8C03\u7528",
      "tool.reasoning": "\u9636\u6BB5\u6458\u8981",
      "tool.result": "\u6267\u884C\u7ED3\u679C",
      "tool.observation": "\u89C2\u5BDF\u7ED3\u679C",
      "tool.structured": "\u7ED3\u6784\u5316\u8BC1\u636E",
      "tool.metadata": "\u6267\u884C\u5143\u6570\u636E",
      "tool.expand": "\u5C55\u5F00\u8BE6\u60C5",
      "tool.expandAll": "\u5168\u90E8\u5C55\u5F00",
      "tool.collapseAll": "\u5168\u90E8\u6298\u53E0",
      "tool.empty": "\u5DE5\u5177\u6CA1\u6709\u8FD4\u56DE\u989D\u5916\u6587\u672C",
      "trace.feedback": "\u81EA\u53CD\u9988",
      "workspace.current": "\u5F53\u524D\u5DE5\u4F5C\u533A",
      "workspace.path": "\u6587\u4EF6\u5939\u8DEF\u5F84",
      "workspace.open": "\u6253\u5F00\u6587\u4EF6\u5939",
      "workspace.recent": "\u6700\u8FD1\u6253\u5F00",
      "workspace.switching": "\u6B63\u5728\u5207\u6362\u5DE5\u4F5C\u533A...",
      "workspace.selectHint": "\u8F93\u5165\u672C\u673A\u6587\u4EF6\u5939\u7EDD\u5BF9\u8DEF\u5F84\uFF0C\u4F8B\u5982 D:\\Projects\\demo",
      "panel.workspaces": "\u5DE5\u4F5C\u533A\u4E0E Git worktree",
      "panel.activity": "\u4EFB\u52A1\u6D3B\u52A8",
      "panel.settings": "\u8BBE\u7F6E",
      "panel.options": "\u66F4\u591A\u9009\u9879",
      "panel.batch": "\u5E76\u884C\u5B50\u667A\u80FD\u4F53",
      "panel.file": "\u6587\u4EF6\u9884\u89C8",
      "panel.noTasks": "\u8FD8\u6CA1\u6709\u540E\u53F0\u4EFB\u52A1",
      "panel.refresh": "\u5237\u65B0",
      "panel.close": "\u5173\u95ED",
      "tasks.detail": "\u67E5\u770B\u8BE6\u60C5",
      "tasks.openSession": "\u6253\u5F00\u4F1A\u8BDD",
      "batch.title": "\u62C6\u5206\u5E76\u884C\u4EFB\u52A1",
      "batch.subtitle": "\u9002\u5408\u72EC\u7ACB\u68C0\u67E5\u3001\u8D44\u6599\u641C\u96C6\u548C\u9A8C\u8BC1\uFF1B\u5B50\u4EFB\u52A1\u5B8C\u6210\u540E\u4F1A\u81EA\u52A8\u5408\u5E76\u7ED3\u679C\u3002",
      "batch.task": "\u5B50\u4EFB\u52A1",
      "batch.context": "\u5171\u4EAB\u4E0A\u4E0B\u6587\uFF08\u53EF\u9009\uFF09",
      "batch.run": "\u5F00\u59CB\u5E76\u884C",
      "batch.note": "\u5EFA\u8BAE\u6BCF\u4E2A\u5B50\u4EFB\u52A1\u53EA\u8D1F\u8D23\u4E00\u4E2A\u6E05\u6670\u76EE\u6807\u3002",
      "panel.createWorktree": "\u521B\u5EFA worktree",
      "panel.name": "\u540D\u79F0",
      "panel.branch": "\u5206\u652F\uFF08\u53EF\u9009\uFF09",
      "panel.create": "\u521B\u5EFA",
      "panel.sandbox": "\u6267\u884C\u73AF\u5883",
      "panel.mcp": "MCP \u5DE5\u5177",
      "panel.language": "\u754C\u9762\u8BED\u8A00",
      "panel.clear": "\u6E05\u7A7A\u5F53\u524D\u4F1A\u8BDD",
      "panel.export": "\u5BFC\u51FA\u5F53\u524D\u5BF9\u8BDD",
      "panel.reload": "\u5237\u65B0\u5DE5\u4F5C\u533A\u72B6\u6001",
      "panel.noWorktrees": "\u5F53\u524D\u6CA1\u6709\u989D\u5916 worktree",
      "panel.model": "\u6A21\u578B",
      "panel.modelRefresh": "\u5237\u65B0\u6A21\u578B\u5217\u8868",
      "panel.hostProcess": "\u5BBF\u4E3B\u673A\u8FDB\u7A0B",
      "panel.isolated": "\u5DF2\u9694\u79BB",
      "panel.servers": "\u4E2A\u670D\u52A1",
      "panel.gitWorktrees": "Git worktree",
      "panel.reasoning": "\u63A8\u7406\u5F3A\u5EA6",
      "panel.reasoningNote": "\u6309\u6A21\u578B\u652F\u6301\u4F20\u9012 low\u3001medium\u3001high \u7B49\u6863\u4F4D\uFF08\u754C\u9762\u5185\u90E8\u7528 mid \u8868\u793A medium\uFF09\uFF1B\u4E0D\u652F\u6301\u65F6\u4F1A\u81EA\u52A8\u964D\u6863\uFF0C\u754C\u9762\u663E\u793A\u53EF\u5BA1\u8BA1\u9636\u6BB5\u6458\u8981\uFF0C\u4E0D\u5C55\u793A\u6A21\u578B\u79C1\u6709\u601D\u7EF4\u94FE",
      "reasoning.low": "\u4F4E",
      "reasoning.mid": "\u4E2D",
      "reasoning.high": "\u9AD8",
      "reasoning.xhigh": "\u6781\u9AD8",
      "reasoning.max": "\u6700\u9AD8",
      "reasoning.ultra": "Ultra",
      "rewind.title": "\u4F1A\u8BDD\u56DE\u9000",
      "rewind.keepLabel": "\u4FDD\u7559\u5230\u7B2C N \u6761\u6D88\u606F",
      "rewind.hint": "\u628A\u5F53\u524D\u4F1A\u8BDD\u622A\u65AD\u5230\u6307\u5B9A\u6D88\u606F\u6570\u540E\u53EF\u91CD\u65B0\u63D0\u95EE\uFF1B\u56DE\u9000\u524D\u4F1A\u81EA\u52A8\u751F\u6210\u5907\u4EFD\u6587\u4EF6\u3002",
      "rewind.action": "\u6267\u884C\u56DE\u9000",
      "rewind.done": "\u5DF2\u56DE\u9000",
      "rewind.fail": "\u56DE\u9000\u5931\u8D25",
      "rewind.toHere": "\u56DE\u9000\u5230\u6B64",
      "rewind.advanced": "\u9AD8\u7EA7\uFF1A\u6309\u6D88\u606F\u6761\u6570\u56DE\u9000",
      "session.emptyTitle": "\u53D1\u9001\u4E00\u6761\u4EFB\u52A1\u5F00\u59CB",
      "session.emptyHint": "\u5728\u4E0B\u65B9\u8F93\u5165\u4EFB\u52A1\uFF0Cminicc \u4F1A\u68C0\u67E5\u5DE5\u4F5C\u533A\u5E76\u7ED9\u51FA\u53EF\u9A8C\u8BC1\u7684\u7ED3\u679C\u3002",
      "help.title": "\u5E2E\u52A9",
      "help.shortcuts": "\u5FEB\u6377\u952E",
      "help.arcade": "\u5C0F\u6E38\u620F",
      "allowlist.title": "\u4F1A\u8BDD\u5141\u8BB8\u5217\u8868",
      "allowlist.commands": "\u547D\u4EE4\u89C4\u5219",
      "allowlist.paths": "\u8DEF\u5F84\u89C4\u5219",
      "allowlist.tools": "\u5DE5\u5177\u89C4\u5219",
      "allowlist.save": "\u4FDD\u5B58\u5141\u8BB8\u5217\u8868",
      "allowlist.soon": "\u5373\u5C06\u53EF\u7528",
      "allowlist.hint": "\u6BCF\u884C\u4E00\u6761 glob \u6216\u5DE5\u5177\u540D\uFF1B\u547D\u4E2D\u540E\u672C\u4F1A\u8BDD\u81EA\u52A8\u653E\u884C\u3002",
      "restore.action": "\u6062\u590D\u6B64\u4EFB\u52A1\u5F00\u59CB\u524D\u7684\u6587\u4EF6",
      "restore.done": "\u5DF2\u6062\u590D\u4EFB\u52A1\u5F00\u59CB\u524D\u7684\u6587\u4EF6",
      "restore.fail": "\u6062\u590D\u5931\u8D25",
      "file.copy": "\u590D\u5236",
      "file.copied": "\u5DF2\u590D\u5236\u6587\u4EF6\u5185\u5BB9",
      "file.current": "\u5F53\u524D\u6587\u4EF6\u5185\u5BB9",
      "game.close": "\u5173\u95ED\u5C0F\u6E38\u620F",
      "game.kicker": "MINICC ARCADE \xB7 MINI LAWN",
      "game.title": "\u690D\u7269\u5927\u6218\u50F5\u5C38 \xB7 \u8349\u576A\u4FDD\u536B\u6218",
      "game.subtitle": "10 \u6CE2\u9AD8\u538B\u6218\u5F79\uFF0C\u5931\u8D25\u53EA\u7531\u50F5\u5C38\u8FDB\u5C4B\u89E6\u53D1\uFF1B\u6218\u6597\u7528\u65F6\u4EC5\u7EDF\u8BA1\u6D3B\u8DC3\u5E27\uFF0C\u5207\u540E\u53F0\u548C\u624B\u52A8\u6682\u505C\u5747\u4E0D\u6D88\u8017\u8FDB\u5EA6\u3002",
      "game.sun": "\u9633\u5149",
      "game.score": "\u51FB\u9000",
      "game.wave": "\u6CE2\u6B21",
      "game.ready": "\u51C6\u5907\u5C31\u7EEA",
      "game.running": "\u6218\u6597\u4E2D",
      "game.paused": "\u5DF2\u81EA\u52A8\u6682\u505C\uFF0C\u8FD4\u56DE\u9875\u9762\u540E\u7EE7\u7EED",
      "game.manualPaused": "\u6218\u5C40\u5DF2\u624B\u52A8\u6682\u505C",
      "game.waveClear": "\u672C\u6CE2\u5DF2\u6E05\u573A\uFF0C\u4E0B\u4E00\u6CE2\u5373\u5C06\u5230\u6765",
      "game.waveIncoming": "\u5F3A\u5316\u6CE2\u6B21\u6765\u88AD\uFF0C\u51C6\u5907\u8FCE\u6218",
      "game.victory": "\u8349\u576A\u5B88\u4F4F\u4E86\uFF01",
      "game.noSun": "\u9633\u5149\u4E0D\u8DB3",
      "game.recharging": "\u5361\u7247\u51B7\u5374\u4E2D",
      "game.gameOver": "\u50F5\u5C38\u8FDB\u5C4B\u4E86",
      "game.time": "\u6218\u6597\u7528\u65F6",
      "game.threat": "\u5A01\u80C1",
      "game.waveHint": "\u5EFA\u7ACB\u9632\u7EBF\uFF0C\u4E0B\u4E00\u6279\u50F5\u5C38\u5373\u5C06\u62B5\u8FBE",
      "game.wavePressure": "\u9AD8\u538B\u6CE2\u6B21\uFF1A\u4F18\u5148\u5E03\u7F6E\u51CF\u901F\u4E0E\u9632\u7EBF",
      "game.progress": "\u6218\u5F79\u8FDB\u5EA6",
      "game.difficulty": "\u96BE\u5EA6",
      "game.normal": "\u6807\u51C6",
      "game.hard": "\u9AD8\u538B",
      "game.nightmare": "\u5669\u68A6",
      "game.pause": "\u6682\u505C",
      "game.resume": "\u7EE7\u7EED",
      "game.pauseHint": "\u51BB\u7ED3\u6218\u5C40",
      "game.resumeHint": "\u6062\u590D\u6218\u5C40",
      "game.volume": "\u97F3\u91CF",
      "game.shovel": "\u94F2\u5B50",
      "game.shovelHint": "\u70B9\u51FB\u690D\u7269\u79FB\u9664",
      "game.autoSun": "\u81EA\u52A8\u62FE\u53D6\u9633\u5149",
      "game.autoSunHint": "\u5173\u95ED\u540E\u6539\u4E3A\u624B\u52A8\u70B9\u51FB",
      "game.repeater": "\u53CC\u53D1\u5C04\u624B",
      "game.cherrybomb": "\u7206\u88C2\u679C",
      "game.icepeashooter": "\u5BD2\u51B0\u5C04\u624B",
      "game.burst": "\u7206\u53D1",
      "game.slow": "\u51CF\u901F",
      "game.peashooter": "\u8C4C\u8C46\u5C04\u624B",
      "game.soundOn": "\u266B \u97F3\u6548\u5F00",
      "game.soundOff": "\u266B \u97F3\u6548\u5173",
      "game.sunflower": "\u5411\u65E5\u8475",
      "game.wallnut": "\u575A\u679C\u5899",
      "game.attack": "\u653B\u51FB",
      "game.produce": "\u4EA7\u9633\u5149",
      "game.defense": "\u9632\u5FA1",
      "game.firepeashooter": "\u706B\u7130\u5C04\u624B",
      "game.twinpea": "\u53CC\u53D1\u5F3A\u5316",
      "game.kernelpult": "\u7389\u7C73\u6295\u624B",
      "game.pumpkin": "\u5357\u74DC\u5934",
      "game.spikeweed": "\u5730\u523A",
      "game.gloomshroom": "\u5FE7\u90C1\u83C7",
      "game.butter": "\u9EC4\u6CB9\u5B9A\u8EAB",
      "game.armor": "\u62A4\u7532",
      "game.polevault": "\u6491\u6746\u8DF3",
      "game.dancer": "\u821E\u738B",
      "game.backup": "\u4F34\u821E",
      "game.potatomine": "\u571F\u8C46\u96F7",
      "game.threepeater": "\u4E09\u7EBF\u5C04\u624B",
      "game.jalapeno": "\u706B\u7206\u8FA3\u6912",
      "game.magnetshroom": "\u78C1\u529B\u83C7",
      "game.garlic": "\u5927\u849C",
      "game.squash": "\u7A9D\u74DC",
      "game.gatlingpea": "\u673A\u67AA\u5C04\u624B",
      "game.trap": "\u5730\u96F7",
      "game.utility": "\u7F34\u68B0",
      "game.redirect": "\u6362\u884C",
      "game.smash": "\u91CD\u51FB",
      "game.rapid": "\u8FDE\u5C04",
      "game.cooldown": "\u51B7\u5374\u4E2D",
      "game.newWindow": "\u65B0\u7A97\u53E3",
      "game.wideMode": "\u5927\u5C4F\u6A21\u5F0F",
      "game.compactMode": "\u7D27\u51D1\u6A21\u5F0F",
      "game.fullscreen": "\u5168\u5C4F",
      "game.waveFinal": "\u7EC8\u5C40\u5DE8\u4EBA\u6765\u88AD\uFF1A\u7528\u7206\u53D1\u548C\u51CF\u901F\u5B88\u4F4F\u6700\u540E\u9632\u7EBF",
      "game.instructions": "\u70B9\u51FB\u5361\u7247\u9009\u62E9 \xB7 \u70B9\u51FB\u8349\u576A\u79CD\u690D \xB7 \u6BCF\u884C\u9632\u7EBF\u5C0F\u8F66\u4EC5\u53EF\u89E6\u53D1\u4E00\u6B21",
      "game.start": "\u5F00\u59CB\u6E38\u620F",
      "game.restart": "\u91CD\u5F00",
      "game.mowers": "\u9632\u7EBF",
      "game.combo": "\u8FDE\u51FB",
      "game.energy": "\u6218\u672F\u80FD\u91CF",
      "game.skillPulse": "\u5BD2\u51B0\u8109\u51B2",
      "game.skillPulseHint": "\u51BB\u7ED3\u5E76\u9707\u51FB\u5168\u573A\u50F5\u5C38",
      "game.skillSun": "\u9633\u5149\u7206\u53D1",
      "game.skillSunHint": "\u7ACB\u5373\u83B7\u5F97 100 \u9633\u5149",
      "game.skillRally": "\u6218\u7EBF\u8D85\u8F7D",
      "game.skillRallyHint": "\u690D\u7269\u653B\u901F\u63D0\u5347 8 \u79D2",
      "game.skillTimeStop": "\u65F6\u505C\u9886\u57DF",
      "game.skillTimeStopHint": "\u51BB\u7ED3\u50F5\u5C38 4 \u79D2",
      "game.skillReady": "\u53EF\u7528",
      "game.skillCooldown": "\u51B7\u5374\u4E2D",
      "game.skillNeedEnergy": "\u80FD\u91CF\u4E0D\u8DB3",
      "message.you": "\u4F60",
      "message.now": "\u73B0\u5728",
      "message.agent": "Agent",
      "game.canvas": "\u690D\u7269\u5927\u6218\u50F5\u5C38\u8FF7\u4F60\u6E38\u620F\u753B\u5E03",
      "changes.agentCore": "Agent \u6838\u5FC3",
      "changes.webWorkspace": "Web \u5DE5\u4F5C\u53F0",
      "changes.specproof": "Specproof \u8BC4\u4F30",
      "changes.filesChanged": "\u4FEE\u6539 6 \u4E2A\u6587\u4EF6",
      "changes.filesAdded": "\u65B0\u589E 3 \u4E2A\u6587\u4EF6",
      "changes.assessmentAdded": "\u5DF2\u6DFB\u52A0\u8BC4\u4F30",
      "changes.now": "\u73B0\u5728",
      "changes.minute": "1 \u5206\u949F\u524D",
      "changes.clean": "\u7B49\u5F85\u53D8\u66F4",
      "changes.cleanHint": "\u8FD0\u884C\u4EFB\u52A1\u540E\u4F1A\u5728\u8FD9\u91CC\u540C\u6B65",
      "changes.modified": "\u5DF2\u4FEE\u6539",
      "changes.added": "\u5DF2\u65B0\u589E",
      "changes.deleted": "\u5DF2\u5220\u9664",
      "changes.renamed": "\u5DF2\u91CD\u547D\u540D",
      "changes.openDiff": "\u67E5\u770B diff",
      "changes.uncounted": "\u6570\u4E0D\u51FA",
      "auth.title": "\u8BBF\u95EE\u9A8C\u8BC1",
      "auth.hint": "\u6B64\u670D\u52A1\u5DF2\u542F\u7528 token \u8BA4\u8BC1\u3002\u8BF7\u8F93\u5165 minicc-web \u542F\u52A8\u65F6\u663E\u793A\u3001\u6216\u4FDD\u5B58\u5728\u5DE5\u4F5C\u533A .minicc/web_token.json \u4E2D\u7684\u8BBF\u95EE token\u3002",
      "auth.tokenLabel": "\u8BBF\u95EE token",
      "auth.submit": "\u4FDD\u5B58\u5E76\u91CD\u8BD5",
      "diff.empty": "\u5F53\u524D\u6CA1\u6709\u53EF\u663E\u793A\u7684\u5DEE\u5F02\u3002",
      "diff.previewAria": "\u7EDF\u4E00\u5DEE\u5F02\u89C6\u56FE",
      "diff.oldLine": "\u65E7\u884C\u53F7",
      "diff.newLine": "\u65B0\u884C\u53F7",
      "palette.title": "\u547D\u4EE4\u9762\u677F",
      "palette.placeholder": "\u641C\u7D22\u547D\u4EE4\u2026",
      "palette.hint": "\u2191\u2193 \u9009\u62E9 \xB7 Enter \u6267\u884C \xB7 Esc \u5173\u95ED",
      "palette.empty": "\u6CA1\u6709\u5339\u914D\u7684\u547D\u4EE4",
      "palette.group.task": "\u4EFB\u52A1",
      "palette.group.surface": "\u754C\u9762",
      "palette.cmd.newTask": "\u65B0\u4EFB\u52A1",
      "palette.cmd.taskCenter": "\u6253\u5F00\u4EFB\u52A1\u4E2D\u5FC3",
      "palette.cmd.workspaces": "\u6253\u5F00\u5DE5\u4F5C\u533A",
      "palette.cmd.globalSearch": "\u5168\u5C40\u641C\u7D22",
      "palette.cmd.activity": "\u4EFB\u52A1\u6D3B\u52A8",
      "palette.cmd.templates": "\u63D0\u793A\u8BCD\u6A21\u677F",
      "palette.cmd.almanac": "\u6253\u5F00\u5E74\u9274",
      "palette.cmd.manual": "\u6253\u5F00\u8BF4\u660E\u4E66",
      "palette.cmd.ledger": "\u6253\u5F00\u8D26\u672C",
      "palette.cmd.batch": "\u5E76\u884C\u5B50\u667A\u80FD\u4F53",
      "palette.cmd.export": "\u5BFC\u51FA\u5F53\u524D\u5BF9\u8BDD",
      "palette.cmd.settings": "\u8BBE\u7F6E",
      "palette.cmd.options": "\u66F4\u591A\u9009\u9879",
      "palette.cmd.help": "\u5E2E\u52A9",
      "palette.cmd.arcade": "\u5C0F\u6E38\u620F",
      "palette.cmd.sidebar": "\u6536\u8D77\u6216\u5C55\u5F00\u4FA7\u680F",
      "palette.cmd.inspector": "\u6536\u8D77\u6216\u5C55\u5F00\u68C0\u67E5\u5668",
      "palette.cmd.focus": "\u4E13\u6CE8\u9605\u8BFB",
      "palette.cmd.jumpLatest": "\u8DF3\u5230\u6700\u65B0\u8F93\u51FA",
      "palette.toDark": "\u5207\u6362\u5230\u6DF1\u8272\u4E3B\u9898",
      "palette.toLight": "\u5207\u6362\u5230\u6D45\u8272\u4E3B\u9898",
      "notify.enable": "\u684C\u9762\u901A\u77E5",
      "notify.enableHint": "\u4EFB\u52A1\u7ED3\u675F\u65F6\u5373\u4F7F\u6D4F\u89C8\u5668\u5728\u540E\u53F0\u4E5F\u63D0\u9192\u4F60\uFF08\u9700\u6388\u6743\u901A\u77E5\u6743\u9650\uFF09\u3002",
      "notify.on": "\u5DF2\u5F00\u542F",
      "notify.off": "\u5DF2\u5173\u95ED",
      "notify.denied": "\u6D4F\u89C8\u5668\u5DF2\u62D2\u7EDD\u901A\u77E5\u6743\u9650\uFF0C\u8BF7\u5728\u7AD9\u70B9\u8BBE\u7F6E\u91CC\u653E\u884C",
      "notify.unsupported": "\u6B64\u6D4F\u89C8\u5668\u4E0D\u652F\u6301\u684C\u9762\u901A\u77E5",
      "notify.completed": "\u4EFB\u52A1\u5B8C\u6210",
      "notify.failed": "\u4EFB\u52A1\u5931\u8D25",
      "notify.cancelled": "\u4EFB\u52A1\u5DF2\u53D6\u6D88",
      "notify.clickToOpen": "\u70B9\u51FB\u67E5\u770B\u4EFB\u52A1",
      "ledger.overview": "\u603B\u89C8",
      "ledger.tokens": "Tokens",
      "ledger.hitRate": "\u7F13\u5B58\u547D\u4E2D\u7387",
      "ledger.cost": "\u4F30\u7B97\u603B\u6210\u672C",
      "ledger.savings": "\u672C\u5468\u671F\u7F13\u5B58\u8282\u7701",
      "ledger.models": "\u6A21\u578B\u5206\u89E3",
      "ledger.status": "\u72B6\u6001\u5206\u5E03",
      "ledger.channel": "\u901A\u9053\u5206\u5E03",
      "ledger.tasks": "\u4EFB\u52A1\u6570",
      "ledger.noMetrics": "\u8FD9\u4E2A\u5DE5\u4F5C\u533A\u8FD8\u6CA1\u6709\u53EF\u6D4B\u91CF\u7684\u4EFB\u52A1",
      "ledger.unpriced": "\u6A21\u578B\u5355\u4EF7\u672A\u6CE8\u518C\uFF0C\u6210\u672C\u6309 0 \u4F30\u7B97",
      "ledger.cacheHits": "\u547D\u4E2D",
      "ledger.cacheMiss": "\u672A\u547D\u4E2D",
      "ledger.cacheWrite": "\u5199\u7F13\u5B58",
      "ledger.redisTitle": "\u7F13\u5B58\u540E\u7AEF",
      "ledger.redisLocal": "\u672C\u5730 LRU\uFF08Redis \u672A\u542F\u7528\uFF09",
      "ledger.redisLive": "Redis \u5B9E\u65F6\u540E\u7AEF",
      "ledger.perCallTitle": "\u9010\u6B21\u8C03\u7528\u7F13\u5B58\u547D\u4E2D",
      "ledger.costPartial": "\u90E8\u5206\u6A21\u578B\u672A\u5B9A\u4EF7\uFF0C\u603B\u989D\u6309 0 \u4F30\u7B97",
      "pulse.title": "\u5DE5\u4F5C\u533A\u8109\u640F",
      "pulse.subtitle": "\u5B9E\u65F6\u8BFB\u6570 \xB7 \u6BCF\u4E2A\u6570\u5B57\u6765\u81EA\u771F\u5B9E\u4EFB\u52A1",
      "pulse.archive": "\u4EFB\u52A1\u6863\u6848",
      "pulse.hitRing": "\u547D\u4E2D\u7387",
      "pulse.ctxRing": "\u4E0A\u4E0B\u6587\u5360\u6BD4",
      "pulse.doneRing": "\u5B8C\u6210\u7387",
      "pulse.identity": "\u5DE5\u4F5C\u533A\u8EAB\u4EFD\u8BC1",
      "pulse.model": "\u6A21\u578B",
      "pulse.gateway": "\u7F51\u5173",
      "pulse.effort": "\u63A8\u7406\u5F3A\u5EA6",
      "pulse.turns": "\u8F6E\u6B21",
      "pulse.cost": "\u6210\u672C",
      "pulse.memory": "\u4F1A\u8BDD\u6570",
      "pulse.messages": "\u6D88\u606F",
      "pulse.audit": "\u5BA1\u8BA1\u884C",
      "pulse.hit": "\u7F13\u5B58\u547D\u4E2D",
      "pulse.miss": "\u7F13\u5B58\u672A\u547D\u4E2D",
      "pulse.total": "\u603B Tokens",
      "pulse.connected": "\u5DF2\u8FDE\u63A5",
      "pulse.disconnected": "\u672A\u8FDE\u63A5",
      "pulse.epoch": "\u4EFB\u52A1\u65F6\u95F4\u8F74",
      "templates.title": "\u6A21\u677F\u5E93",
      "templates.subtitle": "\u7CBE\u9009\u5E38\u89C1\u4EFB\u52A1\u7684\u63D0\u793A\u8BCD\uFF0C\u4E00\u952E\u9001\u8FDB\u5BF9\u8BDD",
      "almanac.title": "\u5E74\u9274",
      "nav.almanac": "\u5E74\u9274",
      "manual.title": "\u8BF4\u660E\u4E66",
      "nav.manual": "\u8BF4\u660E\u4E66",
      "panel.canvas": "\u8FD4\u56DE",
      "send": "\u53D1\u9001",
      "light.title": "\u822A\u884C\u706F \xB7 \u70B9\u51FB\u6253\u5F00\u8D26\u672C",
      "light.cache": "\u7F13\u5B58",
      "light.tasks": "\u4EFB\u52A1",
      "replay.action": "\u56DE\u653E\u6574\u4E2A\u4EFB\u52A1",
      "replay.back": "\u8FD4\u56DE\u8BE6\u60C5",
      "replay.close": "\u5173\u95ED\u56DE\u653E",
      "replay.tokens": "tokens",
      "replay.rows": "\u4E8B\u4EF6",
      "replay.tokensLive": "\u7D2F\u8BA1 tokens",
      "replay.progress": "\u64AD\u653E\u8FDB\u5EA6",
      "replay.done": "\u56DE\u653E\u5B8C\u6210",
      "replay.empty": "\u8FD9\u4E2A\u4EFB\u52A1\u6CA1\u6709\u53EF\u56DE\u653E\u7684\u4E8B\u4EF6\u8BB0\u5F55\u3002",
      "replay.toggle": "\u64AD\u653E / \u6682\u505C",
      "replay.scrub": "\u62D6\u62FD\u8FDB\u5EA6",
      "replay.aria": "\u4EFB\u52A1\u56DE\u653E",
      "pulse.timelineOld": "\u8F83\u65E9",
      "pulse.timelineNew": "\u6700\u65B0",
      "pulse.timelineEmpty": "\u8FD8\u6CA1\u6709\u53EF\u753B\u7684\u65F6\u95F4\u8F74",
      "startup.status": "\u6B63\u5728\u542F\u52A8\u672C\u5730\u5DE5\u4F5C\u53F0",
      "nav.appMenu": "\u5E94\u7528\u83DC\u5355",
      "sidebar.toggle": "\u5207\u6362\u4FA7\u680F",
      "nav.mainMenu": "\u4E3B\u83DC\u5355",
      "menu.help": "\u5E2E\u52A9",
      "brand.workspace": "\u5207\u6362\u5DE5\u4F5C\u533A",
      "brand.search": "\u641C\u7D22",
      "theme.toggle": "\u5207\u6362\u5230\u4EAE\u8272\u6A21\u5F0F",
      "inspector.tabs": "\u5DE5\u4F5C\u533A\u68C0\u67E5\u5668",
      "files.refreshWorkspace": "\u5237\u65B0\u5DE5\u4F5C\u533A",
      "pulse.close": "\u5173\u95ED\u8109\u640F",
      "palette.commands": "\u547D\u4EE4",
      "permission.hint": "\u5B8C\u5168\u8BBF\u95EE\uFF1AAgent \u53EF\u4EE5\u8BFB\u5199\u6587\u4EF6\u5E76\u6267\u884C\u547D\u4EE4\u3002",
      "game.codex": "\u56FE\u9274",
      "game.codexOpen": "\u6253\u5F00\u56FE\u9274",
      "game.codexTitle": "\u690D\u7269\u4E0E\u50F5\u5C38\u56FE\u9274",
      "game.codexSubtitle": "\u5F53\u524D\u5C0F\u6E38\u620F\u5B9E\u9645\u4F7F\u7528\u7684\u6570\u503C\u3001\u6280\u80FD\u4E0E\u6218\u6597\u884C\u4E3A\u3002",
      "game.codexClose": "\u5173\u95ED\u56FE\u9274",
      "game.codexTabs": "\u56FE\u9274\u5206\u7C7B",
      "game.codexPlants": "\u690D\u7269\u56FE\u9274",
      "game.codexZombies": "\u50F5\u5C38\u56FE\u9274",
      "game.codexEntries": "\u56FE\u9274\u6761\u76EE",
      "game.codexPlantDetail": "\u690D\u7269\u8BE6\u60C5",
      "game.codexZombieDetail": "\u50F5\u5C38\u8BE6\u60C5",
      "game.codexSunCost": "\u9633\u5149\u6D88\u8017",
      "game.codexPlantHp": "\u690D\u7269\u751F\u547D\u503C",
      "game.codexDamage": "\u4F24\u5BB3",
      "game.codexAttackRate": "\u653B\u51FB\u9891\u7387",
      "game.codexDamageType": "\u4F24\u5BB3\u7C7B\u578B",
      "game.codexRange": "\u653B\u51FB\u8303\u56F4",
      "game.codexUsage": "\u4F7F\u7528\u65B9\u6CD5",
      "game.codexSpecial": "\u7279\u6B8A\u6548\u679C",
      "game.codexProfile": "\u5B9E\u9645 profile \u53C2\u6570",
      "game.codexBaseHp": "\u57FA\u7840\u751F\u547D\u503C",
      "game.codexArmor": "\u62A4\u7532",
      "game.codexMoveSpeed": "\u79FB\u52A8\u901F\u5EA6",
      "game.codexAttackInterval": "\u653B\u51FB\u95F4\u9694",
      "game.codexScore": "\u51FB\u9000\u79EF\u5206",
      "game.codexMovement": "\u79FB\u52A8\u65B9\u5F0F",
      "game.codexSkills": "\u7279\u6B8A\u6280\u80FD",
      "game.codexEmptyProfile": "\uFF08\u65E0 profile \u6570\u636E\uFF09",
      "game.codexDamagePerSec": "\u6B21/\u79D2",
      "game.codexOneShot": "\u4E00\u6B21\u6027",
      "game.codexThreeLanes": "\u4E09\u884C\u7FA4\u4F53",
      "game.codexSingleTarget": "\u5355\u4E2A\u76EE\u6807",
      "game.codexLineTargets": "\u76F4\u7EBF\u76EE\u6807",
      "game.codexRowPlusNeighbors": "\u5F53\u524D\u884C\u53CA\u76F8\u90BB\u4E24\u884C",
      "game.codexSelfRadius": "\u81EA\u8EAB\u5468\u56F4",
      "game.codexTouchRange": "\u89E6\u78B0\u8303\u56F4",
      "game.codexWholeLane": "\u6574\u6761\u884C",
      "game.codexBackRowSun": "\u653E\u5728\u540E\u6392\uFF0C\u6301\u7EED\u751F\u4EA7\u9633\u5149",
      "game.codexFrontRowWall": "\u653E\u5728\u524D\u6392\uFF0C\u66FF\u690D\u7269\u62B5\u6321\u50F5\u5C38",
      "game.codexEmergencyClear": "\u4F5C\u4E3A\u6E05\u573A/\u6551\u573A\u624B\u6BB5",
      "game.codexFrontLine": "\u6CBF\u524D\u950B\u7EBF\u63A8\u8FDB\u653E\u7F6E",
      "game.codexBurst": "\u8FDE\u53D1",
      "game.codexTripleBurst": "3 \u8FDE\u53D1",
      "game.codexSingleShot": "\u5355\u53D1",
      "game.codexPerWave": "+ \u6BCF\u6CE2",
      "game.codexBurrow": "\u5730\u4E0B\u6F5C\u884C\uFF0C\u63A5\u8FD1\u9632\u7EBF\u540E\u51FA\u571F",
      "game.codexVault": "\u6301\u6746\u524D\u8FDB\uFF0C\u9047\u5230\u690D\u7269\u524D\u8DF3\u8FC7",
      "game.codexLeap": "\u8DC3\u5411\u524D\u65B9\u8D8A\u8FC7\u690D\u7269",
      "game.codexDash": "\u671D\u524D\u51B2\u950B\u8D8A\u8FC7\u690D\u7269",
      "game.codexGiant": "\u4F53\u578B\u5DE8\u5927\uFF0C\u901F\u5EA6\u6781\u6162",
      "game.codexMarch": "\u6301\u7EED\u671D\u524D\u63A8\u8FDB",
      "game.perf": "\u6E32\u67D3\u6027\u80FD",
      "game.fps": "FPS",
      "game.frame": "\u5E27",
      "game.longFrame": "\u957F\u5E27",
      "game.objects": "\u5BF9\u8C61"
    },
    en: {
      "restore.partial": "Restored safe files; kept later edits or unavailable files",
      "tasks.historyLoading": "Loading tasks\u2026",
      "inspector.filesTab": "Files",
      "inspector.verification": "Checks",
      "capability.executeToggle": "Write & commands",
      "capability.network": "Network",
      "start.explore": "Explore project",
      "start.exploreHint": "Find entry points and key flows",
      "start.fix": "Review changes",
      "start.fixHint": "Find regressions and improvements",
      "start.verify": "Verify results",
      "start.verifyHint": "Run focused checks on recent changes",
      "start.explorePrompt": "Read this project and explain its entry points, architecture, and key flows without changing files.",
      "start.fixPrompt": "Review recent changes, find potential regressions, and suggest improvements grounded in the code.",
      "start.verifyPrompt": "Select and run focused checks for recent changes. Explain the results; do not run the full suite by default.",
      "brand.caption": "LOCAL AGENT STUDIO",
      "newTask.label": "New task",
      "newTask.title": "Create a new task",
      "search.placeholder": "Search tasks",
      "search.global": "Global search",
      "search.globalPlaceholder": "Search all session history...",
      "search.hint": "Type a keyword to search task history across workspaces.",
      "search.searching": "Searching...",
      "search.noResults": "No matching history",
      "search.matches": "matches",
      "nav.main": "Main navigation",
      "nav.tasks": "Tasks",
      "nav.workspaces": "Workspaces",
      "nav.promo": "Promo",
      "nav.activity": "Activity",
      "nav.ledger": "Ledger",
      "nav.arcade": "Arcade",
      language: "Language",
      "tasks.more": "More tasks",
      "workspace.connected": "Local service connected",
      "profile.label": "Current mode",
      "inspector.toggle": "Toggle inspector",
      "inspector.close": "Close inspector",
      "focus.enter": "Focus reading",
      "focus.exit": "Exit focus reading",
      "options.open": "More options",
      "composer.inputLabel": "Task input",
      "composer.allowChanges": "Allow this task to modify files or run commands",
      "composer.allowNetwork": "Allow this task to search the web",
      "cancel.title": "Cancel task",
      "send.title": "Send task",
      "files.refresh": "Refresh files",
      "sidebar.close": "Close sidebar",
      "sidebar.open": "Open sidebar",
      "search.shortcut": "Search shortcut",
      recentTasks: "Recent tasks",
      "profile.mode": "Interview mode",
      "profile.local": "Local only",
      workspace: "Workspace",
      agentSession: "Agent session",
      live: "Live",
      "connection.connecting": "Connecting",
      "connection.connected": "Connected",
      "connection.offline": "Offline",
      "mode.localSafe": "local / safe",
      "mode.localFull": "local / full access",
      "composer.workingIn": "Working in",
      "context.empty": "0 / 300k context",
      "context.used": "tokens used",
      "date.today": "Today",
      "composer.placeholder": "Ask minicc to inspect, build, or verify...",
      "composer.attach": "Image",
      "quick.plan": "Plan",
      "quick.review": "Review",
      "quick.verify": "Verify",
      "quick.parallel": "Parallel",
      "quick.demo": "Demo flow",
      "mode.safe": "Safe mode",
      "mode.changes": "Full access",
      "composer.fullAccess": "Full access: the agent can write files and run commands.",
      "composer.readOnly": "Protected workspace: writes and commands are skipped unless you allow changes for this task.",
      "perm.mode": "Permission mode",
      "perm.default": "Default",
      "perm.plan": "Plan",
      "perm.acceptEdits": "Auto-write",
      "perm.yolo": "Full auto",
      "perm.defaultHint": "Default: writes and commands follow the full-access switch.",
      "perm.planHint": "Plan mode: read-only planning; writes and commands are rejected.",
      "perm.acceptEditsHint": "Auto-write: file writes are accepted automatically; commands still need approval.",
      "perm.yoloHint": "Full auto: writes, commands, and web access are all allowed.",
      "todo.title": "Task plan",
      "todo.empty": "No task plan yet",
      "todo.toggle": "Expand or collapse the task plan",
      "todo.progressAria": "Plan progress",
      "todo.completed": "Completed",
      "todo.inProgress": "In progress",
      "todo.pending": "Pending",
      "inspector.overview": "Overview",
      "inspector.changes": "Changes",
      "inspector.files": "Files in focus",
      "protected.title": "Protected workspace",
      "inspector.pulse": "Project pulse",
      "inspector.live": "Live",
      "inspector.ready": "Ready",
      "inspector.standingBy": "Agent is standing by",
      "inspector.turns": "Turns",
      "inspector.tools": "Tools",
      "inspector.tokens": "Tokens",
      "inspector.context": "Context",
      "inspector.compactions": "Compactions",
      "inspector.cache": "Cache hit",
      "changes.latest": "Latest changes",
      "files.main": "CLI entrypoint",
      "files.loop": "Tool calling loop",
      "files.styles": "Workspace surface",
      "files.readme": "Project guide",
      "files.tree": "File tree",
      "files.loading": "Loading...",
      "files.empty": "This folder is empty",
      "files.truncated": "Too many entries; showing a partial list",
      "files.loadError": "Failed to load the file tree",
      "at.title": "File mentions",
      "at.empty": "No matching files",
      "at.commandEmpty": "No custom commands (add .minicc/commands/*.md)",
      "at.hint": "Up/Down to choose \xB7 Enter to insert \xB7 Esc to close",
      "approval.title": "Approval required",
      "approval.allow": "Allow once",
      "approval.always": "Always allow (session)",
      "approval.deny": "Deny",
      "approval.expire": "s until auto-deny",
      "approval.reason": "Reason",
      "approval.tool": "Tool",
      "approval.countdown": "Approval countdown",
      "protected.subtitle": "Writes are gated per task",
      "panel.title": "Workspace",
      "cancel": "Cancel task",
      "working": "Working",
      "ready": "Ready",
      "phase.queued": "Queued",
      "phase.planning": "Planning",
      "phase.intake": "Accepting task",
      "phase.summarize": "Summarizing",
      "phase.tool": "Running tools",
      "phase.answering": "Writing response",
      "phase.waiting": "Waiting for output",
      "phase.review": "Pending review",
      "phase.verify": "Verifying",
      "phase.repair": "Repairing",
      "phase.permission": "Waiting for approval",
      "phase.execution": "Executing",
      "phase.merging": "Merging subagents",
      "phase.completed": "Complete",
      "phase.failed": "Failed",
      "phase.cancelled": "Cancelled",
      "phase.interrupted": "Interrupted by restart",
      "stream.live": "Live response",
      "stream.connected": "Live connection",
      "stream.reconnecting": "Live connection interrupted, reconnecting",
      "stream.polling": "Live connection unavailable, polling",
      "stream.toolForming": "forming",
      "stream.reasoningForming": "reasoning",
      "stream.charsUnit": "chars",
      "tasks.center": "Task center",
      "tasks.open": "Open task",
      "tasks.resume": "Run again",
      "tasks.children": "subtasks",
      "tasks.tokens": "tokens",
      "tasks.context": "context",
      "tasks.cache": "cache",
      "tasks.cacheUnreported": "unreported",
      "tasks.cacheReported": "reported",
      "tasks.compacted": "compactions",
      "tasks.allWorkspaces": "All workspaces",
      "tasks.noHistory": "No task history yet",
      "tasks.jumpLatest": "Jump to latest",
      "tasks.following": "Following latest output",
      "tasks.paused": "Auto-scroll paused",
      "tasks.runtime": "Runtime metrics",
      "tasks.repairs": "Repairs",
      "tasks.verifications": "Verifications",
      "tasks.traces": "Trace events",
      "tasks.workflow": "Workflow",
      "tool.ok": "Done",
      "tool.error": "Failed",
      "tool.denied": "Blocked",
      "tool.searchResults": "Search sources",
      "tool.openSource": "Open source",
      "tool.round": "Tool round",
      "tool.callCount": "calls",
      "tool.reasoning": "Stage summary",
      "tool.result": "Execution result",
      "tool.observation": "Observation",
      "tool.structured": "Structured evidence",
      "tool.metadata": "Execution metadata",
      "tool.expand": "Expand details",
      "tool.expandAll": "Expand all",
      "tool.collapseAll": "Collapse all",
      "tool.empty": "The tool returned no additional text",
      "trace.feedback": "Self-feedback",
      "workspace.current": "Current workspace",
      "workspace.path": "Folder path",
      "workspace.open": "Open folder",
      "workspace.recent": "Recent folders",
      "workspace.switching": "Switching workspace...",
      "workspace.selectHint": "Enter an absolute local path, for example D:\\Projects\\demo",
      "panel.workspaces": "Workspaces & Git worktrees",
      "panel.activity": "Task activity",
      "panel.settings": "Settings",
      "panel.options": "More options",
      "panel.batch": "Parallel subagents",
      "panel.file": "File preview",
      "panel.noTasks": "No background tasks yet",
      "panel.refresh": "Refresh",
      "panel.close": "Close",
      "tasks.detail": "Details",
      "tasks.openSession": "Open session",
      "batch.title": "Split parallel tasks",
      "batch.subtitle": "Use for independent inspection, research, or verification; results are merged when children finish.",
      "batch.task": "Subtask",
      "batch.context": "Shared context (optional)",
      "batch.run": "Start parallel run",
      "batch.note": "Give each subtask one clear responsibility.",
      "panel.createWorktree": "Create worktree",
      "panel.name": "Name",
      "panel.branch": "Branch (optional)",
      "panel.create": "Create",
      "panel.sandbox": "Execution",
      "panel.mcp": "MCP tools",
      "panel.language": "Interface language",
      "panel.clear": "Clear current session",
      "panel.export": "Export current chat",
      "panel.reload": "Refresh workspace status",
      "panel.noWorktrees": "No extra worktrees",
      "panel.model": "Model",
      "panel.modelRefresh": "Refresh model list",
      "panel.hostProcess": "host process",
      "panel.isolated": "isolated",
      "panel.servers": "servers",
      "panel.gitWorktrees": "Git worktrees",
      "panel.reasoning": "Reasoning effort",
      "panel.reasoningNote": "Uses low, medium, high and any supported higher level (the UI uses mid as the internal label for medium); unsupported levels fall back automatically. The UI shows auditable stage summaries, never private chain-of-thought",
      "reasoning.low": "Low",
      "reasoning.mid": "Mid",
      "reasoning.high": "High",
      "reasoning.xhigh": "XHigh",
      "reasoning.max": "Max",
      "reasoning.ultra": "Ultra",
      "rewind.title": "Rewind session",
      "rewind.keepLabel": "Keep first N messages",
      "rewind.hint": "Truncates the session to N messages so you can re-ask; a backup is written first.",
      "rewind.action": "Rewind",
      "rewind.done": "Rewound",
      "rewind.fail": "Rewind failed",
      "rewind.toHere": "Rewind to here",
      "rewind.advanced": "Advanced: keep first N messages",
      "session.emptyTitle": "Send a task to begin",
      "session.emptyHint": "Type a task below to inspect, build, or verify this workspace.",
      "help.title": "Help",
      "help.shortcuts": "Shortcuts",
      "help.arcade": "Arcade",
      "allowlist.title": "Session allowlist",
      "allowlist.commands": "Command rules",
      "allowlist.paths": "Path rules",
      "allowlist.tools": "Tool rules",
      "allowlist.save": "Save allowlist",
      "allowlist.soon": "Coming soon",
      "allowlist.hint": "One glob or tool name per line. Matches are auto-allowed for this session.",
      "restore.action": "Restore files from before this task",
      "restore.done": "Restored files from before this task",
      "restore.fail": "Restore failed",
      "file.copy": "Copy",
      "file.copied": "File content copied",
      "file.current": "Current file",
      "game.close": "Close game",
      "game.kicker": "MINICC ARCADE \xB7 MINI LAWN",
      "game.title": "Plants vs. Zombies \xB7 Mini lawn",
      "game.subtitle": "10 high-pressure waves. Only a zombie reaching the house ends the campaign; battle time counts active frames only.",
      "game.sun": "Sun",
      "game.score": "Defeated",
      "game.wave": "Wave",
      "game.ready": "Ready",
      "game.running": "Battle",
      "game.paused": "Paused while this tab is hidden",
      "game.manualPaused": "Battle paused",
      "game.waveClear": "Wave cleared, next incoming",
      "game.victory": "The lawn is held!",
      "game.noSun": "Not enough sun",
      "game.recharging": "Card is recharging",
      "game.waveIncoming": "Reinforced wave incoming",
      "game.gameOver": "A zombie reached the house",
      "game.time": "Battle time",
      "game.threat": "Threat",
      "game.waveHint": "Build your line; the next pack is approaching",
      "game.wavePressure": "High-pressure wave: use slows and defenses",
      "game.progress": "Campaign progress",
      "game.difficulty": "Difficulty",
      "game.normal": "Standard",
      "game.hard": "High pressure",
      "game.nightmare": "Nightmare",
      "game.pause": "Pause",
      "game.resume": "Resume",
      "game.pauseHint": "Freeze battle",
      "game.resumeHint": "Resume battle",
      "game.volume": "Volume",
      "game.shovel": "Shovel",
      "game.shovelHint": "Remove a plant",
      "game.autoSun": "Auto-collect sun",
      "game.autoSunHint": "Turn off for manual clicks",
      "game.repeater": "Repeater",
      "game.cherrybomb": "Burst berry",
      "game.icepeashooter": "Ice shooter",
      "game.burst": "burst",
      "game.slow": "slow",
      "game.peashooter": "Peashooter",
      "game.soundOn": "\u266B Sound on",
      "game.soundOff": "\u266B Sound off",
      "game.sunflower": "Sunflower",
      "game.wallnut": "Wall-nut",
      "game.attack": "attack",
      "game.produce": "sun",
      "game.defense": "defense",
      "game.firepeashooter": "Fire Pea",
      "game.twinpea": "Twin Pea",
      "game.kernelpult": "Kernel-pult",
      "game.pumpkin": "Pumpkin",
      "game.spikeweed": "Spikeweed",
      "game.gloomshroom": "Gloom-shroom",
      "game.butter": "butter stun",
      "game.armor": "armor",
      "game.polevault": "Pole Vault",
      "game.dancer": "Dancer",
      "game.backup": "backup dancer",
      "game.potatomine": "Potato Mine",
      "game.threepeater": "Threepeater",
      "game.jalapeno": "Jalapeno",
      "game.magnetshroom": "Magnet-shroom",
      "game.garlic": "Garlic",
      "game.squash": "Squash",
      "game.gatlingpea": "Gatling Pea",
      "game.trap": "trap",
      "game.utility": "disarm",
      "game.redirect": "redirect",
      "game.smash": "smash",
      "game.rapid": "rapid fire",
      "game.cooldown": "recharging",
      "game.newWindow": "New window",
      "game.wideMode": "Wide mode",
      "game.compactMode": "Compact mode",
      "game.fullscreen": "Fullscreen",
      "game.waveFinal": "Final wave: use bursts and slows to hold the last line",
      "game.instructions": "Choose a card \xB7 click the lawn to plant \xB7 each lane has one safety mower",
      "game.start": "Start game",
      "game.restart": "Restart",
      "game.mowers": "Mowers",
      "game.combo": "Combo",
      "game.energy": "Tactical energy",
      "game.skillPulse": "Frost Pulse",
      "game.skillPulseHint": "Freeze and shock every zombie",
      "game.skillSun": "Sun Burst",
      "game.skillSunHint": "Gain 100 sun instantly",
      "game.skillRally": "Overdrive",
      "game.skillRallyHint": "Boost plant fire rate for 8 seconds",
      "game.skillTimeStop": "Time Lock",
      "game.skillTimeStopHint": "Freeze zombies for 4 seconds",
      "game.skillReady": "Ready",
      "game.skillCooldown": "Cooling",
      "game.skillNeedEnergy": "Need energy",
      "message.you": "You",
      "message.now": "now",
      "message.agent": "Agent",
      "game.canvas": "Plants vs. Zombies mini game canvas",
      "changes.agentCore": "Agent core",
      "changes.webWorkspace": "Web workspace",
      "changes.specproof": "Specproof review",
      "changes.filesChanged": "6 files changed",
      "changes.filesAdded": "3 files added",
      "changes.assessmentAdded": "assessment added",
      "changes.now": "now",
      "changes.minute": "1m",
      "changes.clean": "Waiting for changes",
      "changes.cleanHint": "Changes will sync here after a task runs",
      "changes.modified": "Modified",
      "changes.added": "Added",
      "changes.deleted": "Deleted",
      "changes.renamed": "Renamed",
      "changes.openDiff": "Open diff",
      "changes.uncounted": "not counted",
      "auth.title": "Access verification",
      "auth.hint": "This service requires a token. Paste the token printed by minicc-web on startup, or stored in .minicc/web_token.json.",
      "auth.tokenLabel": "Access token",
      "auth.submit": "Save and retry",
      "diff.empty": "No diff to display.",
      "diff.previewAria": "Unified diff view",
      "diff.oldLine": "Old line",
      "diff.newLine": "New line",
      "palette.title": "Command palette",
      "palette.placeholder": "Type a command\u2026",
      "palette.hint": "\u2191\u2193 navigate \xB7 Enter run \xB7 Esc close",
      "palette.empty": "No matching command",
      "palette.group.task": "Tasks",
      "palette.group.surface": "Surface",
      "palette.cmd.newTask": "New task",
      "palette.cmd.taskCenter": "Open task center",
      "palette.cmd.workspaces": "Open workspaces",
      "palette.cmd.globalSearch": "Global search",
      "palette.cmd.activity": "Task activity",
      "palette.cmd.templates": "Prompt templates",
      "palette.cmd.almanac": "Open the almanac",
      "palette.cmd.manual": "Open the manual",
      "palette.cmd.ledger": "Open the ledger",
      "palette.cmd.batch": "Parallel subagents",
      "palette.cmd.export": "Export this chat",
      "palette.cmd.settings": "Settings",
      "palette.cmd.options": "More options",
      "palette.cmd.help": "Help",
      "palette.cmd.arcade": "Arcade",
      "palette.cmd.sidebar": "Toggle sidebar",
      "palette.cmd.inspector": "Toggle inspector",
      "palette.cmd.focus": "Focus reading",
      "palette.cmd.jumpLatest": "Jump to latest output",
      "palette.toDark": "Switch to dark theme",
      "palette.toLight": "Switch to light theme",
      "notify.enable": "Desktop notifications",
      "notify.enableHint": "Get notified when a task finishes, even with the tab in the background (requires permission).",
      "notify.on": "On",
      "notify.off": "Off",
      "notify.denied": "Notification permission was denied; allow it in site settings",
      "notify.unsupported": "This browser does not support notifications",
      "notify.completed": "Task completed",
      "notify.failed": "Task failed",
      "notify.cancelled": "Task cancelled",
      "notify.clickToOpen": "Click to open the task",
      "ledger.overview": "Overview",
      "ledger.tokens": "Tokens",
      "ledger.hitRate": "Cache hit rate",
      "ledger.cost": "Estimated total cost",
      "ledger.savings": "Cache savings this cycle",
      "ledger.models": "Model split",
      "ledger.status": "Status split",
      "ledger.channel": "Channel split",
      "ledger.tasks": "Tasks",
      "ledger.noMetrics": "No measurable tasks yet",
      "ledger.unpriced": "Model pricing not registered; cost estimated at 0",
      "ledger.cacheHits": "hits",
      "ledger.cacheMiss": "misses",
      "ledger.cacheWrite": "writes",
      "ledger.redisTitle": "Cache backend",
      "ledger.redisLocal": "Local LRU (Redis not live)",
      "ledger.redisLive": "Redis live backend",
      "ledger.perCallTitle": "Per-call cache hits",
      "ledger.costPartial": "Some models unpriced; estimate is a floor",
      "pulse.title": "Workspace pulse",
      "pulse.subtitle": "Live counters \xB7 every number from real tasks",
      "pulse.archive": "Task archive",
      "pulse.hitRing": "Hit rate",
      "pulse.ctxRing": "Context usage",
      "pulse.doneRing": "Completion rate",
      "pulse.identity": "Workspace card",
      "pulse.model": "Model",
      "pulse.gateway": "Gateway",
      "pulse.effort": "Reasoning effort",
      "pulse.turns": "Turns",
      "pulse.cost": "Cost",
      "pulse.memory": "Sessions",
      "pulse.messages": "Messages",
      "pulse.audit": "Audit lines",
      "pulse.hit": "cache hit",
      "pulse.miss": "cache miss",
      "pulse.total": "Total tokens",
      "pulse.connected": "connected",
      "pulse.disconnected": "disconnected",
      "pulse.epoch": "Task timeline",
      "templates.title": "Task templates",
      "templates.subtitle": "Curated prompts for common jobs, one click into chat",
      "almanac.title": "Almanac",
      "nav.almanac": "Almanac",
      "manual.title": "Manual",
      "nav.manual": "Manual",
      "panel.canvas": "Back",
      "send": "Send",
      "light.title": "Running light \xB7 open the ledger",
      "light.cache": "cache",
      "light.tasks": "tasks",
      "replay.action": "Replay the run",
      "replay.back": "Back to task",
      "replay.close": "Close replay",
      "replay.tokens": "tokens",
      "replay.rows": "events",
      "replay.tokensLive": "Accumulated tokens",
      "replay.progress": "Progress",
      "replay.done": "Replay complete",
      "replay.empty": "No replayable event history for this task.",
      "replay.toggle": "Play / pause",
      "replay.scrub": "Seek",
      "replay.aria": "Task replay",
      "pulse.timelineOld": "older",
      "pulse.timelineNew": "latest",
      "pulse.timelineEmpty": "No timeline yet",
      "startup.status": "Starting the local workbench",
      "nav.appMenu": "Application menu",
      "sidebar.toggle": "Toggle sidebar",
      "nav.mainMenu": "Main menu",
      "menu.help": "Help",
      "brand.workspace": "Switch workspace",
      "brand.search": "Search",
      "theme.toggle": "Switch to light mode",
      "inspector.tabs": "Workspace inspector",
      "files.refreshWorkspace": "Refresh workspace",
      "pulse.close": "Close pulse",
      "palette.commands": "Commands",
      "permission.hint": "Full access: the agent can edit files and run commands.",
      "game.codex": "Codex",
      "game.codexOpen": "Open the codex",
      "game.codexTitle": "Plant & zombie codex",
      "game.codexSubtitle": "The real numbers, skills and combat behaviour the arcade uses.",
      "game.codexClose": "Close the codex",
      "game.codexTabs": "Codex categories",
      "game.codexPlants": "Plant codex",
      "game.codexZombies": "Zombie codex",
      "game.codexEntries": "Codex entries",
      "game.codexPlantDetail": "Plant detail",
      "game.codexZombieDetail": "Zombie detail",
      "game.codexSunCost": "Sun cost",
      "game.codexPlantHp": "Plant HP",
      "game.codexDamage": "Damage",
      "game.codexAttackRate": "Attack rate",
      "game.codexDamageType": "Damage type",
      "game.codexRange": "Range",
      "game.codexUsage": "How to use",
      "game.codexSpecial": "Special effect",
      "game.codexProfile": "Raw profile parameters",
      "game.codexBaseHp": "Base HP",
      "game.codexArmor": "Armor",
      "game.codexMoveSpeed": "Move speed",
      "game.codexAttackInterval": "Attack interval",
      "game.codexScore": "Repel score",
      "game.codexMovement": "Movement",
      "game.codexSkills": "Special skills",
      "game.codexEmptyProfile": "(no profile data)",
      "game.codexDamagePerSec": "hits/s",
      "game.codexOneShot": "one-shot",
      "game.codexThreeLanes": "3 lanes",
      "game.codexSingleTarget": "single target",
      "game.codexLineTargets": "line targets",
      "game.codexRowPlusNeighbors": "own lane plus the two neighbours",
      "game.codexSelfRadius": "around itself",
      "game.codexTouchRange": "touch range",
      "game.codexWholeLane": "the whole lane",
      "game.codexBackRowSun": "back row, keeps producing sun",
      "game.codexFrontRowWall": "front row, tanks the horde",
      "game.codexEmergencyClear": "emergency lane clear",
      "game.codexFrontLine": "place along the advance line",
      "game.codexBurst": "burst",
      "game.codexTripleBurst": "3-lane volley",
      "game.codexSingleShot": "single shot",
      "game.codexPerWave": "+ per wave",
      "game.codexBurrow": "digs underground, surfaces at the plants",
      "game.codexVault": "keeps a pole, vaults the first plant",
      "game.codexLeap": "leaps forward over plants",
      "game.codexDash": "charges forward through plants",
      "game.codexGiant": "huge frame, crawls forward",
      "game.codexMarch": "marches steadily forward",
      "game.perf": "Rendering performance",
      "game.fps": "FPS",
      "game.frame": "frame",
      "game.longFrame": "long frames",
      "game.objects": "objects"
    }
  };
  function t(key) {
    return I18N[state.locale]?.[key] || I18N.en[key] || key;
  }

  // web/src/icons.js
  var LOCAL_ICON_GLYPHS = {
    "panel-left-close": "\u2039",
    plus: "+",
    search: "\u2315",
    "message-square": "\u25A1",
    "layout-grid": "\u25A6",
    megaphone: "\u25E2",
    history: "\u21B6",
    "gamepad-2": "\u25C7",
    "more-horizontal": "\u2022\u2022\u2022",
    "chevron-right": "\u203A",
    "folder-git-2": "\u25A1",
    "settings-2": "\u2699",
    "panel-left": "\u2039",
    "brain-circuit": "\u2726",
    sun: "\u263C",
    maximize: "\u2197",
    "panel-right": "\u203A",
    "arrow-down": "\u2193",
    "list-checks": "\u2637",
    "chevrons-down": "\u21F5",
    "chevrons-up": "\u21F3",
    sparkles: "\u2726",
    "alert-triangle": "!",
    "alert-circle": "!",
    check: "\u2713",
    lock: "\u25A1",
    "globe-2": "\u25CE",
    "test-tube-2": "\u25C8",
    "git-branch": "\u2442",
    "file-search-2": "\u2315",
    "layers-3": "\u25A4",
    "chevron-down": "\u2304",
    image: "\u25A7",
    x: "\xD7",
    "scan-line": "\u2301",
    route: "\u2301",
    command: "\u2318",
    "scan-search": "\u2315",
    play: "\u25B6",
    paperclip: "\u2307",
    "wand-sparkles": "\u2726",
    square: "\u25A0",
    "arrow-up": "\u2191",
    "refresh-cw": "\u21BB",
    activity: "\u2022",
    radio: "\u25C9",
    "shield-check": "\u25C7",
    "external-link": "\u2197",
    "layout-dashboard": "\u25A6",
    "book-open": "\u25A4",
    "maximize-2": "\u2197",
    "panel-right-close": "\u203A",
    "file-code-2": "\u25A1",
    "rotate-ccw": "\u21B6",
    folder: "\u25A4",
    "folder-open": "\u25A6",
    file: "\u25AA",
    copy: "\u29C9",
    moon: "\u263E",
    minimize: "\u2199",
    "panel-left-open": "\u203A",
    "panel-right-open": "\u2039",
    "loader-circle": "\u25CC",
    "arrow-up-right": "\u2197",
    "arrow-right": "\u2192",
    "arrow-left": "\u2190",
    "trash-2": "\u{1F5D1}",
    eraser: "\u232B",
    download: "\u2193",
    "minimize-2": "\u2199",
    bell: "\u{1F514}"
  };
  var ICONS = {
    "panel-left": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
    "panel-left-close": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>',
    "panel-left-open": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>',
    "panel-right": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/>',
    "panel-right-close": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/><path d="m8 9 3 3-3 3"/>',
    "panel-right-open": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/><path d="m10 15-3-3 3-3"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "file-search-2": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><circle cx="11.5" cy="14.5" r="2.5"/><path d="m13.3 16.3 1.3 1.3"/>',
    "message-square": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "layout-grid": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    megaphone: '<path d="m3 11 18-5v12L3 13v-2z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "gamepad-2": '<line x1="6" x2="10" y1="11" y2="11"/><line x1="8" x2="8" y1="9" y2="13"/><line x1="15" x2="15.01" y1="12" y2="12"/><line x1="18" x2="18.01" y1="10" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"/>',
    "more-horizontal": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "folder-git-2": '<path d="M9 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v5"/><circle cx="13" cy="15" r="2"/><path d="M18 17c-2.8 0-4.5-.9-5.5-2"/><circle cx="20" cy="20" r="2"/>',
    "settings-2": '<path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
    "brain-circuit": '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><circle cx="12" cy="13" r="1"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    maximize: '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "maximize-2": '<polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/>',
    minimize: '<path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/>',
    "minimize-2": '<polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" x2="21" y1="10" y2="3"/><line x1="3" x2="10" y1="21" y2="14"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "arrow-up": '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    "arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "arrow-up-right": '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
    "list-checks": '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
    "chevrons-down": '<path d="m7 13 5 5 5-5"/><path d="m7 6 5 5 5-5"/>',
    "chevrons-up": '<path d="m17 11-5-5-5 5"/><path d="m17 18-5-5-5 5"/>',
    sparkles: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
    ledger: '<path d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M9 7h6"/><path d="M9 12h6"/><path d="M9 17h4"/>',
    "alert-triangle": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "alert-circle": '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "globe-2": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "test-tube-2": '<path d="M21 7 6.82 21.18a2.83 2.83 0 0 1-3.99-.01v0a2.83 2.83 0 0 1 0-4L17 3"/><path d="m16 2 6 6"/><path d="M12 16H4"/>',
    "git-branch": '<line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    "layers-3": '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 12.6-8.57 3.91a2 2 0 0 1-1.66 0L3.2 12.6"/><path d="m22 17.6-8.57 3.91a2 2 0 0 1-1.66 0L3.2 17.6"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    command: '<path d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3"/>',
    "scan-line": '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
    route: '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
    "scan-search": '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/><path d="m16 16-1.9-1.9"/>',
    play: '<polygon points="6 3 20 12 6 21 6 3"/>',
    paperclip: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
    "wand-sparkles": '<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72Z"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/>',
    square: '<rect x="3" y="3" width="18" height="18" rx="2"/>',
    "refresh-cw": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    radio: '<circle cx="12" cy="12" r="2"/><path d="M4.93 19.07a10 10 0 0 1 0-14.14"/><path d="M7.76 16.24a6 6 0 0 1 0-8.48"/><path d="M16.24 7.76a6 6 0 0 1 0 8.48"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-8 10-4.5-2.5-8-5-8-10V6l8-3 8 3Z"/><path d="m9 12 2 2 4-4"/>',
    "external-link": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "layout-dashboard": '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>',
    "book-open": '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
    "file-code-2": '<path d="M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m5 12-3 3 3 3"/><path d="m9 18 3-3-3-3"/>',
    "rotate-ccw": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "folder-open": '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "loader-circle": '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
    "trash-2": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
    eraser: '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
    download: '<path d="M12 3v12"/><path d="m8 11 4 4 4-4"/><path d="M4 19h16"/>',
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01"/><path d="M10 10h.01"/><path d="M14 10h.01"/><path d="M18 10h.01"/><path d="M6 14h.01"/><path d="M18 14h.01"/><path d="M10 14h4"/>',
    "circle-dashed": '<path d="M10.1 2.18a9.93 9.93 0 0 1 3.8 0"/><path d="M17.6 3.71a10 10 0 0 1 2.69 2.7"/><path d="M21.82 10.1a9.93 9.93 0 0 1 0 3.8"/><path d="M20.29 17.6a10 10 0 0 1-2.7 2.69"/><path d="M13.9 21.82a9.94 9.94 0 0 1-3.8 0"/><path d="M6.4 20.29a10 10 0 0 1-2.69-2.7"/><path d="M2.18 13.9a9.93 9.93 0 0 1 0-3.8"/><path d="M3.71 6.4a10 10 0 0 1 2.7-2.69"/>',
    "git-compare": '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><path d="M11 18H8a2 2 0 0 1-2-2V9"/>',
    help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>'
  };
  function svgFor(name) {
    const inner = ICONS[name];
    if (!inner) return "";
    return `<svg class="minicc-icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
  }
  function icon(name) {
    return svgFor(name) || `<span class="icon-fallback" aria-hidden="true">${LOCAL_ICON_GLYPHS[name] || "\u2022"}</span>`;
  }
  function applyIcons(root = document) {
    const scope = root?.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-lucide]").forEach((node) => {
      if (node.dataset.iconApplied === "true") return;
      const rendered = icon(String(node.dataset.lucide || ""));
      const holder = document.createElement("span");
      holder.innerHTML = rendered;
      const replacement = holder.firstElementChild;
      if (!replacement) return;
      replacement.dataset.iconApplied = "true";
      if (node.className) replacement.classList.add(...node.className.split(/\s+/).filter(Boolean));
      node.replaceWith(replacement);
    });
  }
  function refreshIcons(root = document) {
    applyIcons(root);
  }

  // web/src/core/cache-series.js
  var CAP = 24;
  function cacheTurnSeries(usageByTurn, cap = CAP) {
    const rows = Array.isArray(usageByTurn) ? usageByTurn : [];
    const parsed = [];
    for (const row of rows) {
      if (!row || typeof row !== "object") continue;
      const prompt = Number(row.prompt_tokens) || 0;
      if (prompt <= 0) continue;
      const hit = Number(row.prompt_cache_hit_tokens) || 0;
      const miss = Number(row.prompt_cache_miss_tokens) || 0;
      const write = Number(row.prompt_cache_write_tokens) || 0;
      const base = hit + miss > 0 ? hit + miss : 0;
      const rate = base > 0 ? Math.min(1, hit / base) : null;
      parsed.push({
        kind: String(row.kind || "agent"),
        prompt,
        hit,
        miss,
        write,
        rate
      });
    }
    return parsed.slice(-cap);
  }
  function cacheTurnTone(rate) {
    if (rate == null || !Number.isFinite(rate)) return "quiet";
    if (rate >= 0.7) return "mint";
    if (rate >= 0.4) return "amber";
    return "rose";
  }

  // web/src/core/prefix-strip.js
  var CAP2 = 12;
  function short(value) {
    const s = String(value || "");
    return s ? s.slice(0, 8) : null;
  }
  function prefixRows(usageByTurn, cap = CAP2) {
    const rows = Array.isArray(usageByTurn) ? usageByTurn : [];
    const out = [];
    for (const row of rows) {
      if (!row || typeof row !== "object") continue;
      const sys = short(row.system_fp);
      const msgs = short(row.msgs_fp);
      const tools = short(row.tools_fp);
      if (!sys && !msgs && !tools) continue;
      out.push({
        sys,
        msgs,
        tools,
        hit: Number(row.prompt_cache_hit_tokens) || 0,
        prompt: Number(row.prompt_tokens) || 0
      });
    }
    return out.slice(-cap);
  }
  function prefixStripMarkup(rows, labels) {
    const lb = labels && typeof labels === "object" ? labels : {};
    if (!Array.isArray(rows) || !rows.length) return "";
    const cells = rows.map((row, index) => {
      const rate = row.prompt > 0 ? Math.round(row.hit / row.prompt * 100) : null;
      const tone = rate == null ? "quiet" : rate >= 70 ? "mint" : rate >= 40 ? "amber" : "rose";
      const fields = [
        `<i>sys</i>${row.sys || "\u2014"}`,
        `<i>msgs</i>${row.msgs || "\u2014"}`,
        `<i>tools</i>${row.tools || "\u2014"}`,
        `<i>${String(lb.hitLabel || "hit")}</i><b data-tone="${tone}">${rate == null ? "\u2014" : `${rate}%`}</b>`
      ].join("");
      return `<div class="prefix-strip-row"><span class="prefix-strip-n">#${index + 1}</span>${fields}</div>`;
    }).join("");
    return `<div class="prefix-strip">${cells}</div>`;
  }

  // web/src/core/dialog.js
  var dialogs = [];
  var background = /* @__PURE__ */ new Map();
  var focusable = "button, input, textarea, select, a[href], summary, [tabindex]";
  var listening = false;
  function controls(modal) {
    return [...modal.querySelectorAll(focusable)].filter((node) => !node.disabled && node.tabIndex >= 0 && !node.closest("[hidden], [inert]") && node.getClientRects().length);
  }
  function focusDialog(entry) {
    const preferred = entry.initialFocus && entry.modal.querySelector(entry.initialFocus);
    const target = preferred || controls(entry.modal)[0] || entry.modal.querySelector('[role="dialog"]');
    if (target) {
      if (target.tabIndex < 0) target.setAttribute("tabindex", "-1");
      target.focus({ preventScroll: true });
    }
  }
  function syncBackground() {
    for (const [node, inert] of background) node.inert = inert;
    background.clear();
    const entry = dialogs.at(-1);
    if (!entry) return;
    for (const node of document.body.children) {
      if (node.contains(entry.modal) || ["SCRIPT", "STYLE", "LINK"].includes(node.tagName)) continue;
      background.set(node, node.inert);
      node.inert = true;
    }
  }
  function activateDialog(modal, options = {}) {
    let entry = dialogs.find((item) => item.modal === modal);
    if (!entry) {
      entry = { modal, previousFocus: document.activeElement, ...options };
      dialogs.push(entry);
    } else Object.assign(entry, options);
    const previous = document.activeElement;
    if (previous instanceof HTMLElement && !modal.contains(previous)) previous.blur();
    if (!listening) {
      listening = true;
      document.addEventListener("keydown", (event) => {
        const active = dialogs.at(-1);
        if (!active) return;
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          active.onEscape?.();
        } else if (event.key === "Tab") {
          const nodes = controls(active.modal);
          const index = nodes.indexOf(document.activeElement);
          if (!nodes.length || index < 0 || event.shiftKey && index === 0 || !event.shiftKey && index === nodes.length - 1) {
            event.preventDefault();
            if (!nodes.length) focusDialog(active);
            else nodes[event.shiftKey ? nodes.length - 1 : 0].focus({ preventScroll: true });
          }
        }
      }, true);
      document.addEventListener("focusin", (event) => {
        const active = dialogs.at(-1);
        if (active && !active.modal.contains(event.target)) focusDialog(active);
      });
    }
    syncBackground();
    if (dialogs.at(-1) === entry && !modal.contains(document.activeElement)) focusDialog(entry);
    requestAnimationFrame(() => {
      if (dialogs.at(-1) === entry && !modal.contains(document.activeElement)) focusDialog(entry);
    });
    window.setTimeout(() => {
      if (dialogs.at(-1) === entry && !modal.contains(document.activeElement)) focusDialog(entry);
    }, 220);
  }
  function deactivateDialog(modal) {
    const index = dialogs.findIndex((item) => item.modal === modal);
    if (index < 0) return;
    const [entry] = dialogs.splice(index, 1);
    syncBackground();
    if (index !== dialogs.length) return;
    const active = dialogs.at(-1);
    if (entry.previousFocus?.isConnected && !entry.previousFocus.closest("[inert]")) entry.previousFocus.focus({ preventScroll: true });
    else if (active) focusDialog(active);
  }

  // web/src/core/notify.js
  var TOGGLE_KEY = "minicc-notifications";
  var TERMINAL_TITLES = { completed: "notify.completed", failed: "notify.failed", cancelled: "notify.cancelled", interrupted: "notify.cancelled" };
  function supported() {
    return typeof window.Notification === "function";
  }
  function notificationsEnabled() {
    return localStorage.getItem(TOGGLE_KEY) === "true";
  }
  function notificationsBlocked() {
    return supported() && window.Notification.permission === "denied";
  }
  async function setNotificationsEnabled(enabled) {
    localStorage.setItem(TOGGLE_KEY, enabled ? "true" : "false");
    if (!enabled) return true;
    if (!supported()) return false;
    if (window.Notification.permission === "granted") return true;
    if (window.Notification.permission === "denied") return false;
    try {
      const permission = await window.Notification.requestPermission();
      if (permission === "granted") return true;
    } catch {
    }
    return false;
  }
  function notifyTaskFinished(task) {
    if (!notificationsEnabled() || !document.hidden || !supported()) return;
    if (window.Notification.permission !== "granted") return;
    const status = String(task?.status || "");
    const titleKey = TERMINAL_TITLES[status];
    if (!titleKey) return;
    const title = `minicc \xB7 ${t(titleKey)}`;
    const body = String(task?.prompt || task?.preview || task?.task_id || "").slice(0, 160);
    try {
      const notice = new window.Notification(title, { body, tag: `minicc-task-${task?.task_id || ""}`, silent: false });
      notice.onclick = () => {
        window.focus();
        if (task?.task_id) window.dispatchEvent(new CustomEvent("minicc-open-task", { detail: { taskId: task.task_id } }));
        notice.close();
      };
      window.setTimeout(() => notice.close(), 12e3);
    } catch {
    }
  }

  // web/src/core/timeline-series.js
  function taskTimelineTone(status) {
    const s = String(status || "");
    if (s === "completed") return "mint";
    if (s === "failed") return "rose";
    if (s === "cancelled" || s === "interrupted") return "amber";
    if (s) return "pulse";
    return "quiet";
  }
  function taskTimelineHeight(tokens, maxTokens) {
    const t2 = Number(tokens) || 0;
    const max = Number(maxTokens) || 0;
    if (max <= 0) return 0;
    if (t2 <= 0) return 8;
    const ratio = Math.log1p(t2) / Math.log1p(max);
    return Math.round((0.12 + 0.88 * Math.max(0, Math.min(1, ratio))) * 100);
  }
  function compactTokens(value) {
    const n = Number(value) || 0;
    if (n <= 0) return "0";
    if (n >= 1e6) return `${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1).replace(/\.0$/, "")}k`;
    return String(n);
  }
  function taskTimelineSeries(tasks, cap = 12) {
    const rows = Array.isArray(tasks) ? tasks : [];
    const parsed = [];
    for (const task of rows) {
      if (!task || typeof task !== "object") continue;
      const tokens = Number(task?.tokens_used?.total_tokens ?? task?.metrics?.budget?.tokens ?? 0) || 0;
      parsed.push({
        id: String(task.task_id || ""),
        status: String(task.status || ""),
        tone: taskTimelineTone(task.status),
        tokens,
        cost: Number(task.cost_usd) || 0,
        duration: Number(task.duration_seconds) || 0,
        preview: String(task.preview || task.task_id || "").slice(0, 60),
        created: Number(task.created_at_epoch) || 0
      });
    }
    const capped = parsed.slice(0, cap).reverse();
    const maxTokens = capped.reduce((acc, item) => Math.max(acc, item.tokens), 0);
    return capped.map((item) => ({ ...item, height: taskTimelineHeight(item.tokens, maxTokens) }));
  }
  function taskTimelineMarkup(series, labels) {
    const lb = labels && typeof labels === "object" ? labels : {};
    const empty = String(lb.empty || "");
    if (!Array.isArray(series) || !series.length) {
      return empty ? `<div class="pulse-timeline-empty">${empty}</div>` : "";
    }
    const nodes = series.map((item) => {
      const tipTitle = item.preview.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const tokensLabel = item.tokens > 0 ? `${compactTokens(item.tokens)} ${String(lb.tokensUnit || "tokens")}` : String(lb.noTokens || "");
      const tip = [tipTitle, tokensLabel].filter(Boolean).join(" \xB7 ");
      const created = item.created > 0 ? ` title="${new Date(item.created * 1e3).toISOString()}"` : "";
      const taskId = item.id.replace(/"/g, "&quot;");
      return `<button type="button" class="pulse-timeline-node" data-tone="${item.tone}" data-open-task="${taskId}" style="--tl-h:${item.height}%"${created} aria-label="${tip}"><span class="pulse-timeline-bar"></span><span class="pulse-timeline-tip">${tip}</span></button>`;
    }).join("");
    const axis = lb.old || lb.new ? `<div class="pulse-timeline-axis"><span>${String(lb.old || "")}</span><span>${String(lb.new || "")}</span></div>` : "";
    return `<div class="pulse-timeline-track">${nodes}</div>${axis}`;
  }

  // web/src/core/task-reducer.js
  var sequenceOf = (value) => Math.max(0, Number(value) || 0);
  var boundedAdd = (previous, value) => {
    const next = new Set(previous || []);
    if (value) next.add(value);
    while (next.size > MAX_SEEN_EVENT_KEYS) next.delete(next.values().next().value);
    return next;
  };
  function reduceTaskEvent(binding, envelope) {
    if (!binding || !envelope || typeof envelope !== "object") return null;
    const sequence = sequenceOf(envelope.sequence);
    const eventId = String(envelope.event_id || "");
    const itemId = String(envelope.item_id || "");
    if (sequence && sequence <= sequenceOf(binding.cursor) || sequence && binding.seenSequences?.has(sequence) || eventId && binding.seenEventIds?.has(eventId) || !sequence && !eventId && itemId && binding.seenEventIds?.has(`item:${itemId}`)) return null;
    const payload = envelope.payload && typeof envelope.payload === "object" ? envelope.payload : {};
    const data = { ...binding.data || {} };
    switch (envelope.kind) {
      case "timeline": {
        const event = { ...payload, event_id: payload.event_id || eventId, item_id: payload.item_id || itemId, sequence: payload.sequence || sequence };
        const events = [...data.events || []];
        const existing = events.findIndex((item) => event.event_id && item.event_id === event.event_id || event.item_id && item.item_id === event.item_id);
        if (existing < 0) events.push(event);
        else events[existing] = { ...events[existing], ...event };
        data.events = events.slice(-MAX_SEEN_EVENT_KEYS);
        break;
      }
      case "stream_delta": {
        const length = sequenceOf(payload.stream_length);
        if (length && length < sequenceOf(data.stream_length)) break;
        if (payload.stream_text != null) data.stream_text = String(payload.stream_text || "");
        else if (payload.delta) data.stream_text = `${data.stream_text || ""}${payload.delta}`.slice(-32e3);
        data.stream_length = length || Math.max(sequenceOf(data.stream_length), String(data.stream_text || "").length);
        if (payload.phase) data.phase = String(payload.phase);
        break;
      }
      case "state":
      case "status":
        for (const key of ["status", "phase", "finished_at", "error", "cancel_reason"]) if (payload[key] !== void 0) data[key] = payload[key];
        break;
      case "usage":
        for (const key of ["tokens_used", "metrics"]) if (payload[key] && typeof payload[key] === "object") data[key] = { ...payload[key] };
        if (payload.usage) data.usage_by_turn = [...data.usage_by_turn || [], { ...payload.usage }].slice(-64);
        break;
      case "context":
        if (payload.context) data.context = { ...payload.context };
        break;
      case "compaction":
        if (payload.event) data.compaction_events = [...data.compaction_events || [], { ...payload.event }].slice(-64);
        break;
      case "result":
        for (const key of ["answer", "error"]) if (payload[key] !== void 0) data[key] = payload[key];
        data.result = { ...data.result || {}, answer: data.answer, error: data.error };
        break;
    }
    if (payload.state_version != null) data.state_version = Math.max(sequenceOf(data.state_version), sequenceOf(payload.state_version));
    const cursor = Math.max(sequenceOf(binding.cursor), sequence);
    data.event_cursor = cursor;
    let seenEventIds = boundedAdd(binding.seenEventIds, eventId);
    if (!sequence && !eventId && itemId) seenEventIds = boundedAdd(seenEventIds, `item:${itemId}`);
    return { data, cursor, seenSequences: boundedAdd(binding.seenSequences, sequence), seenEventIds };
  }

  // web/src/core/approvals.js
  var APPROVAL_TIMEOUT_SECONDS = 60;
  var APPROVAL_FRAME_REQUEST_KIND = "approval_request";
  var APPROVAL_FRAME_RESOLVED_KIND = "approval_resolved";
  var APPROVAL_DECISIONS = ["allow", "always", "deny"];
  var pending2 = /* @__PURE__ */ new Map();
  var ticker = 0;
  function ensureLayer() {
    let layer = document.getElementById("approvalLayer");
    if (!layer) {
      layer = document.createElement("div");
      layer.id = "approvalLayer";
      layer.className = "approval-layer";
      layer.setAttribute("aria-live", "polite");
      document.body.append(layer);
    }
    return layer;
  }
  function removeCard(requestId) {
    const entry = pending2.get(requestId);
    if (!entry) return;
    pending2.delete(requestId);
    entry.node.remove();
    if (!pending2.size && ticker) {
      window.clearInterval(ticker);
      ticker = 0;
    }
  }
  function tick() {
    const now = Date.now();
    for (const [requestId, entry] of pending2) {
      if (entry.busy) continue;
      if (now >= entry.deadline) {
        removeCard(requestId);
        continue;
      }
      const label2 = entry.node.querySelector("[data-approval-count]");
      if (label2) label2.textContent = `${Math.ceil((entry.deadline - now) / 1e3)}${t("approval.expire")}`;
    }
    if (!pending2.size && ticker) {
      window.clearInterval(ticker);
      ticker = 0;
    }
  }
  async function decide(requestId, decision) {
    const entry = pending2.get(requestId);
    if (!entry || entry.busy) return;
    entry.busy = true;
    entry.node.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
    try {
      await requestJson("/api/approval", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, decision })
      }, 8e3);
    } catch (error) {
    }
    removeCard(requestId);
  }
  function addCard(event) {
    const layer = ensureLayer();
    const node = document.createElement("div");
    node.className = "approval-card";
    node.setAttribute("role", "alertdialog");
    node.setAttribute("aria-label", t("approval.title"));
    const timeoutSeconds = Number(event.timeout_seconds) || APPROVAL_TIMEOUT_SECONDS;
    const buttons = APPROVAL_DECISIONS.map(
      (decision) => `<button type="button"${decision === "deny" ? ' class="approval-deny"' : ""} data-decision="${decision}">${escapeHtml(t(`approval.${decision}`))}</button>`
    ).join("");
    node.innerHTML = `
    <div class="approval-card-head"><strong>${escapeHtml(t("approval.title"))}</strong><span data-approval-count></span></div>
    <div class="approval-card-body"><b>${escapeHtml(String(event.tool || event.name || ""))}</b><code>${escapeHtml(String(event.preview || "").slice(0, 300))}</code><small>${escapeHtml(t("approval.reason"))}\uFF1A${escapeHtml(String(event.reason || event.summary || ""))}</small></div>
    <div class="approval-card-actions">
      ${buttons}
    </div>`;
    node.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => decide(event.request_id, button.dataset.decision));
    });
    const entry = {
      node,
      deadline: Date.now() + timeoutSeconds * 1e3,
      busy: false
    };
    pending2.set(event.request_id, entry);
    layer.append(node);
    node.querySelector("[data-approval-count]").textContent = `${timeoutSeconds}${t("approval.expire")}`;
    if (!ticker) ticker = window.setInterval(tick, 250);
  }
  function syncApprovalRequests(events) {
    if (!Array.isArray(events)) return;
    const resolved = new Set(
      events.filter((event) => event?.kind === APPROVAL_FRAME_RESOLVED_KIND && event.request_id).map((event) => event.request_id)
    );
    for (const requestId of [...pending2.keys()]) {
      if (resolved.has(requestId)) removeCard(requestId);
    }
    for (const event of events) {
      if (!event || event.kind !== APPROVAL_FRAME_REQUEST_KIND || !event.request_id) continue;
      if (resolved.has(event.request_id) || pending2.has(event.request_id)) continue;
      if (event.stale === true) continue;
      addCard(event);
    }
  }

  // web/src/chat/timeline-dom.js
  var keyOf = (node) => node.nodeType === 1 ? [node.tagName, node.dataset.agentRound || node.dataset.agentItem || node.dataset.toolEvent || node.dataset.stageCode || ""].join(":") : "";
  function patchNode(current, next) {
    if (current.nodeType !== next.nodeType || current.nodeName !== next.nodeName) {
      current.replaceWith(next);
      return next;
    }
    if (current.nodeType !== 1) {
      if (current.nodeValue !== next.nodeValue) current.nodeValue = next.nodeValue;
      return current;
    }
    for (const attr of [...current.attributes]) if (attr.name !== "open" && !next.hasAttribute(attr.name)) current.removeAttribute(attr.name);
    for (const attr of next.attributes) if (attr.name !== "open" && current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
    patchChildren(current, next);
    return current;
  }
  function patchChildren(parent, nextParent) {
    const keyed = new Map([...parent.children].map((node) => [keyOf(node), node]).filter(([key]) => key && !key.endsWith(":")));
    let position = parent.firstChild;
    for (const next of [...nextParent.childNodes]) {
      const key = keyOf(next);
      let current = key && !key.endsWith(":") ? keyed.get(key) : position;
      if (!current || key && !key.endsWith(":") && keyOf(current) !== key) {
        parent.insertBefore(next, position);
        continue;
      }
      if (current !== position) parent.insertBefore(current, position);
      const updated = patchNode(current, next);
      position = updated.nextSibling;
    }
    while (position) {
      const next = position.nextSibling;
      position.remove();
      position = next;
    }
  }
  function reconcileTimeline(timeline, markup) {
    const template = timeline.ownerDocument.createElement("template");
    template.innerHTML = markup;
    patchChildren(timeline, template.content);
  }

  // web/src/core/api.js
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
      stream.preview.innerHTML = `${formatLightText(streamTail(stream.target))}<span class="stream-caret" aria-hidden="true"></span>`;
    };
    stream.frame = window.setTimeout(paint, 120);
  }
  function timelineDetailKey(detail) {
    if (detail.matches("details.agent-round")) return `round:${detail.dataset.agentRound || ""}`;
    if (detail.matches("details.tool-event")) return `tool:${detail.dataset.toolEvent || ""}`;
    const owner = detail.closest("details.tool-event, details.agent-round, [data-stage-code]");
    if (!owner) return "";
    const ownerKey = owner.matches("details.tool-event") ? `tool:${owner.dataset.toolEvent || ""}` : owner.matches("details.agent-round") ? `round:${owner.dataset.agentRound || ""}` : `stage:${owner.dataset.agentItem || owner.dataset.stageCode || ""}`;
    const nestedIndex = [...owner.querySelectorAll("details")].indexOf(detail);
    return `nested:${ownerKey}:${nestedIndex}`;
  }
  function captureTimelineOpenDetails(timeline) {
    return new Set([...timeline.querySelectorAll("details[open]")].map(timelineDetailKey).filter(Boolean));
  }
  function restoreTimelineOpenDetails(timeline, openDetails) {
    if (!(openDetails instanceof Set)) return;
    timeline.querySelectorAll("details").forEach((detail) => {
      detail.open = openDetails.has(timelineDetailKey(detail));
    });
  }
  function setTimelineDetails(timeline, open) {
    if (!timeline) return;
    timeline.querySelectorAll("details").forEach((detail) => {
      detail.open = open;
    });
  }
  var timelineRenderState = /* @__PURE__ */ new WeakMap();
  function syncLiveEvents(loading, events, chatPosition = null) {
    if (!events.length) return false;
    let timeline = loading.querySelector(".tool-timeline");
    if (!timeline) {
      timeline = document.createElement("div");
      timeline.className = "tool-timeline";
      loading.querySelector(".message-body")?.append(timeline);
    }
    const previous = timelineRenderState.get(timeline);
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
    live.classList.remove(...[...TASK_PHASES].map((phase) => `live-task-${phase}`));
    live.classList.add(`live-task-${currentPhase}`);
    live.dataset.phase = currentPhase;
    const progress = live.querySelector(".task-progress");
    if (progress) progress.dataset.phase = currentPhase;
    live.querySelector("[data-live-phase]")?.replaceChildren(document.createTextNode(phaseText));
    live.querySelector("[data-live-phase-label]")?.replaceChildren(document.createTextNode(phaseText));
    live.querySelector("[data-live-metrics]")?.replaceChildren(document.createTextNode(taskMetrics(data)));
    const preview = live.querySelector("[data-live-preview]");
    const streamText = String(data.stream_text || "");
    live.querySelector("[data-live-output-count]")?.replaceChildren(document.createTextNode(streamText ? `${compactNumber(streamText.length)} ${state.locale === "zh" ? "\u5B57\u7B26\uFF08\u4EC5\u663E\u793A\u6700\u8FD1\u5185\u5BB9\uFF09" : "chars (recent content)"}` : ""));
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
    window.clearTimeout(runtime.changeRefreshTimer);
    runtime.changeRefreshTimer = window.setTimeout(() => loadChanges(), 220);
  }
  function applyTaskEvent(taskId, envelope) {
    const binding = runningTasks.get(taskId);
    if (!binding || !envelope || typeof envelope !== "object") return null;
    const next = reduceTaskEvent(binding, envelope);
    if (!next) return null;
    Object.assign(binding, next);
    const data = next.data;
    updateBoundTask(taskId, data, { skipSnapshotMerge: true });
    return data;
  }
  function updateBoundTask(taskId, data, options = {}) {
    const binding = runningTasks.get(taskId);
    if (!binding) return;
    const next = options.skipSnapshotMerge ? { ...data, session_id: data.session_id || binding.sessionId, workspace_path: data.workspace_path || binding.workspacePath } : applyTaskSnapshot(binding, data, { replaceEvents: true });
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
  function finishLiveTask(loadingId) {
    const stream = liveStreamStates.get(loadingId);
    if (stream?.frame) window.clearTimeout(stream.frame);
    liveStreamStates.delete(loadingId);
    const source = taskEventSources.get(loadingId);
    source?.close();
    taskEventSources.delete(loadingId);
  }
  function isTerminalTask(data) {
    return TERMINAL_TASK_STATUSES.has(String(data?.status || ""));
  }
  async function completeTask(loadingId, data) {
    const taskId = data.task_id;
    if (finalizedTaskIds.has(taskId)) return data;
    finalizedTaskIds.add(taskId);
    const binding = runningTasks.get(taskId) || { taskId, sessionId: state.sessionId, workspacePath: state.workspacePath, loadingId };
    finishLiveTask(binding.loadingId || loadingId);
    stopTaskTimer(taskId);
    const zh2 = state.locale === "zh";
    const finalData = data.status === "completed" ? data : { ...data, answer: data.answer || data.error || (data.status === "cancelled" ? zh2 ? "\u4EFB\u52A1\u5DF2\u53D6\u6D88\u3002" : "Task cancelled." : zh2 ? "\u4EFB\u52A1\u5931\u8D25\u3002" : "Task failed.") };
    cacheTaskDetail(finalData);
    runningTasks.delete(taskId);
    if (taskBySession.get(taskSessionKey(binding.sessionId, binding.workspacePath)) === taskId) taskBySession.delete(taskSessionKey(binding.sessionId, binding.workspacePath));
    const currentScope = isCurrentTaskScope({
      task_id: taskId,
      session_id: binding.sessionId,
      workspace_path: binding.workspacePath
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
      const pending3 = holder.querySelector(`#${CSS.escape(binding.loadingId || loadingId)}`);
      if (pending3) {
        const replacement = document.createElement("div");
        replacement.innerHTML = assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`);
        pending3.replaceWith(replacement.firstElementChild);
      } else {
        holder.insertAdjacentHTML("beforeend", assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`));
      }
      cacheSessionView(binding.sessionId, holder.innerHTML, binding.workspacePath);
    }
    if (finalData.status !== "completed") showToast(finalData.error || (finalData.status === "cancelled" ? state.locale === "zh" ? "\u4EFB\u52A1\u5DF2\u53D6\u6D88" : "Task cancelled" : state.locale === "zh" ? "\u4EFB\u52A1\u5931\u8D25" : "Task failed"));
    notifyTaskFinished(finalData);
    scheduleChangesRefresh();
    refreshFileTreeSoon();
    await loadTaskHistory();
    return finalData;
  }
  async function pollTask(taskId) {
    const binding = runningTasks.get(taskId);
    setTaskTransportStatus(taskId, "polling");
    let delay = 220;
    while (true) {
      if (!runningTasks.has(taskId)) return null;
      try {
        const data = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12e3);
        updateBoundTask(taskId, data);
        if (isTerminalTask(data)) return completeTask(binding?.loadingId || "", data);
        delay = 220;
      } catch (error) {
        if (!runningTasks.has(taskId)) throw error;
        delay = Math.min(5e3, Math.max(500, Math.round(delay * 1.6)));
      }
      await new Promise((resolve) => window.setTimeout(resolve, delay));
    }
  }

  // web/src/panels/almanac.js
  var zh = () => state.locale === "zh";
  var CHAPTERS = [
    { id: "prologue", roman: { zh: "\u5E8F\u7AE0", en: "Prologue" }, title: { zh: "\u4E00\u5C01\u7ED9\u672A\u6765\u7684\u4FE1", en: "The Letter" }, subtitle: { zh: "\u4E00\u5C01\u7ED9\u672A\u6765\u7684\u4FE1", en: "A letter to the future" } },
    { id: "spark", roman: { zh: "\u7B2C\u4E00\u7AE0", en: "Chapter I" }, title: { zh: "\u706B\u79CD", en: "The Spark" }, subtitle: { zh: "\u610F\u56FE \u2192 \u8BA1\u5212 \u2192 \u884C\u52A8 \u2192 \u8BC1\u636E", en: "Intent \u2192 Plan \u2192 Act \u2192 Proof" } },
    { id: "depth", roman: { zh: "\u7B2C\u4E8C\u7AE0", en: "Chapter II" }, title: { zh: "\u6DF1\u5EA6", en: "The Depth" }, subtitle: { zh: "\u538B\u7F29\u3001\u4FDD\u7559\u3001\u518D\u51FA\u53D1", en: "Compact, keep, depart again" } },
    { id: "sentry", roman: { zh: "\u7B2C\u4E09\u7AE0", en: "Chapter III" }, title: { zh: "\u54E8\u5175", en: "The Sentry" }, subtitle: { zh: "\u6BCF\u4E00\u4E2A\u627F\u8BFA\u90FD\u8981\u88AB\u6267\u884C", en: "Every promise gets executed" } },
    { id: "bloom", roman: { zh: "\u7B2C\u56DB\u7AE0", en: "Chapter IV" }, title: { zh: "\u76DB\u653E", en: "The Bloom" }, subtitle: { zh: "\u5DE5\u4F5C\u53F0\u672C\u8EAB\u5C31\u662F\u8BC1\u8BCD", en: "The workbench itself is testimony" } },
    { id: "hand", roman: { zh: "\u7B2C\u4E94\u7AE0", en: "Chapter V" }, title: { zh: "\u8FDC\u884C", en: "The Open Road" }, subtitle: { zh: "\u7EB8\u4E0A\u753B\u4E0B\u7684\u8FDC\u65B9", en: "What is still unmapped" } },
    { id: "gate", roman: { zh: "\u5377\u516D", en: "Chapter VI" }, title: { zh: "\u5173\u5361", en: "The Gate" }, subtitle: { zh: "\u6BCF\u4E00\u9053\u95E8\u90FD\u70B9\u4E86\u5934", en: "Every gate said yes" } },
    { id: "mesh", roman: { zh: "\u5377\u4E03", en: "Chapter VII" }, title: { zh: "\u661F\u7F51", en: "The Mesh" }, subtitle: { zh: "\u516D\u4E2A\u670D\u52A1\uFF0C\u4E00\u4E2A\u56FD\u5BB6", en: "Six services, one country" } },
    { id: "witness", roman: { zh: "\u5377\u516B", en: "Chapter VIII" }, title: { zh: "\u8BC1\u4EBA", en: "The Witness" }, subtitle: { zh: "\u7B14\u5F55\u4E0D\u8BF4\u8BDD\uFF0C\u4F46\u4E0D\u8BF4\u8C0E", en: "The record does not speak, but it does not lie" } }
  ];
  function chapterMarkup(chapter) {
    const kicker = zh() ? chapter.roman.zh : chapter.roman.en;
    const title = zh() ? chapter.title.zh : chapter.title.en;
    const subtitle = zh() ? chapter.subtitle.zh : chapter.subtitle.en;
    return `<button class="almanac-chapter" data-chapter="${escapeHtml(chapter.id)}" role="tab">
            <span class="almanac-chapter-roman">${escapeHtml(kicker)}</span>
            <span class="almanac-chapter-body">
              <strong>${escapeHtml(title)}</strong>
              <small>${escapeHtml(subtitle)}</small>
            </span>
          </button>`;
  }
  var digestCache = null;
  var statsCache = null;
  var currentChapter = "prologue";
  function witnessMarkup() {
    const s = statsCache;
    const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "\u2014";
    const sessions = s?.sessions && typeof s?.sessions?.count === "number" ? String(s.sessions.count) : "\u2014";
    const messages = s?.sessions && typeof s?.sessions?.messages === "number" ? String(s.sessions.messages) : "\u2014";
    const rows = (zh() ? [
      ["provider_retry", "\u7F51\u5173\u7684\u8010\u5FC3\u2014\u2014\u6BCF\u4E00\u6B21\u91CD\u8BD5\u8BA1\u6570\u90FD\u662F\u7F51\u5173\u4E0E\u6A21\u578B\u4E4B\u95F4\u7684\u4E00\u6B21\u63E1\u624B"],
      ["tool_round_finished", "\u5DE5\u5177\u56DE\u5408\u7684\u5B8C\u6574\u7B7E\u540D\u2014\u2014\u53C2\u6570\u591A\u5C11\u5B57\u7B26\uFF0C\u4E00\u6B21\u90FD\u4E0D\u5C11"],
      ["completion_assessed", "\u5B8C\u6210\u843D\u69CC\u6216\u5224\u5B9A\u843D\u69CC\u2014\u2014\u4ECE\u6765\u4E0D\u6765\u81EA\u9759\u9ED8\u8DF3\u8FC7"],
      ["approval_requested", "\u8D8A\u6743\u8FB9\u7F18\u7684\u505C\u4E0B\u4E0E\u7B49\u5F85\u2014\u2014\u4F60\u8BF4\u4E86\u7B97\uFF0C\u5B83\u505C\u7740"],
      ["audit", "\u88AB\u5199\u4E0B\u6765\u7684\uFF0C\u90FD\u80FD\u88AB\u8BFB\u56DE\u53BB\u2014\u2014\u5305\u62EC\u8FD9\u53E5\u8BDD\u672C\u8EAB"]
    ] : [
      ["provider_retry", "The gateway's patience \u2014 every retry count is a handshake between gateway and model"],
      ["tool_round_finished", "The full signature of a tool round \u2014 parameters, character counts, none skipped"],
      ["completion_assessed", "The hammer falls or it doesn't \u2014 never from a silent skip"],
      ["approval_requested", "The pause at the edge of excess authority \u2014 the user decides, the agent waits"],
      ["audit", "What is written can be read back \u2014 including this very sentence"]
    ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
    return `
    <div class="almanac-canvas almanac-witness">
      <div class="almanac-kicker">${zh() ? "\u5377\u516B \xB7 \u8BC1\u4EBA" : "Chapter VIII \xB7 The Witness"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u7B14\u5F55\u4E0D\u8BF4\u8BDD\uFF0C<br/><span class="almanac-title-accent">\u4F46\u7B14\u5F55\u4E0D\u8BF4\u8C0E\u3002</span>' : 'The record does not speak,<br/><span class="almanac-title-accent">but the record does not lie.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          \u8FD9\u4E2A\u9879\u76EE\u4E0D\u4FE1\u4EFB\u53D9\u8FF0\uFF0C\u5B83\u76F8\u4FE1\u7B14\u5F55\u3002\u6BCF\u4E00\u6B21\u5DE5\u5177\u8C03\u7528\u3001\u6BCF\u4E00\u6B21\u91CD\u8BD5\u3001\u6BCF\u4E00\u6B21\u5B8C\u6210\u5224\u5B9A\uFF0C
          \u90FD\u88AB\u5199\u8FDB\u5BA1\u8BA1\u65E5\u5FD7\u2014\u2014\u6309\u987A\u5E8F\u3001\u5E26\u5E8F\u53F7\u3001\u5E26\u65F6\u95F4\u6233\u3002
        </p>
        <p>
          \u5BC6\u94A5\u6C38\u8FDC\u4E0D\u843D\u76D8\uFF1A\u6240\u6709\u51FA\u7AD9\u5185\u5BB9\u90FD\u7ECF\u8FC7\u8131\u654F\u624D\u5199\u5165\u65E5\u5FD7\u3002
          \u4F60\u80FD\u5728\u8FD9\u91CC\u770B\u5230\u7684\uFF0C\u662F\u52A8\u8BCD\u548C\u8DEF\u5F84\uFF0C\u4ECE\u6765\u4E0D\u662F\u51ED\u636E\u3002
        </p>` : `<p>
          This project does not trust narrative; it trusts the record. Every tool call, every retry,
          every completion verdict is written into the audit log \u2014 in order, numbered, timestamped.
        </p>
        <p>
          Secrets never touch disk: everything leaving the machine is redacted before it lands in the log.
          What you see here are verbs and paths \u2014 never credentials.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u5BA1\u8BA1\u884C\u6570" : "Audit lines"}</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u4F1A\u8BDD" : "Sessions"}</div>
          <div class="almanac-instrument-value">${escapeHtml(sessions)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u6D88\u606F" : "Messages"}</div>
          <div class="almanac-instrument-value">${escapeHtml(messages)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "\u5F53\u4F60\u4E0D\u77E5\u9053 agent \u505A\u8FC7\u4EC0\u4E48\uFF0C\u6253\u5F00\u5BA1\u8BA1\u3002\u5B83\u4E0D\u89E3\u91CA\uFF0C\u4F46\u5B83\u6309\u987A\u5E8F\u4EA4\u51FA\u4E8B\u5B9E\u3002" : "When you don't know what the agent did, open the audit. It does not explain, but it hands over the facts in order."}
      </p>
    </div>`;
  }
  function digestInstrumentMarkup(digest) {
    if (!digest || digest.is_git !== true) return "";
    const date = String(digest.first_commit_at || "").slice(0, 10);
    const dirty = Number(digest.dirty_entries);
    const branch = `${digest.branch ?? "\u2014"}${digest.head_short ? ` @ ${digest.head_short}` : ""}`;
    const batches = digest.roadmap_batches != null ? zh() ? `${digest.roadmap_batches} \u7AE0` : `${digest.roadmap_batches} chapters` : "\u2014";
    const cells = [
      { label: zh() ? "\u5206\u652F" : "Branch", value: escapeHtml(branch) },
      { label: zh() ? "\u63D0\u4EA4\u603B\u6570" : "Commits", value: digest.total_commits != null ? String(digest.total_commits) : "\u2014" },
      { label: zh() ? "\u7B2C\u4E00\u7B14\u63D0\u4EA4" : "First commit", value: date || "\u2014" },
      { label: zh() ? "\u6279\u6B21\u7AE0\u8282" : "Batch chapters", value: batches },
      { label: zh() ? "\u8DDF\u8E2A\u6587\u4EF6" : "Tracked files", value: digest.tracked_files != null ? String(digest.tracked_files) : "\u2014" },
      { label: zh() ? "\u6D4B\u8BD5\u6587\u4EF6" : "Test files", value: digest.test_files != null ? String(digest.test_files) : "\u2014" }
    ];
    const grid = cells.map((cell) => `<div><div class="almanac-instrument-label">${escapeHtml(cell.label)}</div><div class="almanac-instrument-value">${cell.value}</div></div>`).join("");
    const note = Number.isFinite(dirty) && dirty > 0 ? `<div class="almanac-sidenote">${zh() ? `\u5DE5\u4F5C\u6811\u91CC\u8FD8\u6709 ${dirty} \u5904\u672A\u63D0\u4EA4\u6539\u52A8\u2014\u2014\u8FD9\u4E2A\u535A\u7269\u9986\u8FD8\u5728\u65BD\u5DE5\u4E2D\u3002` : `${dirty} uncommitted change(s) in the worktree \u2014 this museum is still under construction.`}</div>` : "";
    return `<div class="almanac-instrument almanac-instrument-grid">${grid}</div>${note}`;
  }
  function prologueMarkup(digest) {
    return `
    <div class="almanac-canvas almanac-prologue">
      <div class="almanac-kicker">${zh() ? "\u5E8F\u7AE0 \xB7 \u4E00\u5C01\u7ED9\u672A\u6765\u7684\u4FE1" : "Prologue \xB7 The Letter"}</div>
      <h1 class="almanac-title">${zh() ? "\u6211\u5E0C\u671B<br/>\u6709\u4EBA\u4E3A\u6211" : "I wish<br/>someone would"}<br/><span class="almanac-title-accent">${zh() ? "\u628A\u4E16\u754C\u8BFB\u4E00\u904D\u3002" : "read the world back to me."}</span></h1>
      <div class="almanac-body">
        <p class="almanac-lede">
          ${zh() ? `2026 \u5E74\u590F\u5929\uFF0C\u8FD9\u4E2A\u9879\u76EE\u5F00\u59CB\u4E8E\u4E00\u4E2A\u95EE\u9898\uFF1A<em>\u300C\u80FD\u4E0D\u80FD\u505A\u4E00\u4E2A\u4EBA\u613F\u610F\u6BCF\u5929\u4F7F\u7528\u7684\u672C\u5730\u7F16\u7A0B\u667A\u80FD\u4F53\uFF1F\u300D</em>` : `Summer 2026. This project began with a question: <em>"Could there be a local coding agent people would actually use every day?"</em>`}
        </p>
        <p>
          ${zh() ? `\u5B83\u4E0D\u662F\u6D88\u8D39\u7EA7\u804A\u5929\u5BA2\u6237\u7AEF\u7684\u5957\u58F3\uFF0C\u4E5F\u4E0D\u662F\u4EFB\u4F55\u5DF2\u6709\u4EA7\u54C1\u7684\u514B\u9686\u3002<br/>\u5B83\u63A5\u53D7 <code>MINICC_API_KEY</code>\u3001<code>MINICC_BASE_URL</code>\u3001<code>MINICC_MODEL</code>\uFF0C<br/>\u7136\u540E\u5728\u4F60\u7684\u5DE5\u4F5C\u533A\u91CC <code>read_file</code>\u3001<code>edit_file</code>\u3001<code>run_bash</code>\uFF0C<br/>\u7528 <code>verify</code> \u8BC1\u660E\u81EA\u5DF1\u8BF4\u7684\u8BDD\u662F\u771F\u7684\uFF0C\u6700\u540E\u628A\u7B54\u6848\u4EA4\u7ED9\u4F60\u3002` : `It is not a wrapper around any chat client, and not a clone of anything.<br/>It takes <code>MINICC_API_KEY</code>, <code>MINICC_BASE_URL</code> and <code>MINICC_MODEL</code>,<br/>then in your workspace it does <code>read_file</code>, <code>edit_file</code>, <code>run_bash</code>,<br/>proves its claims with <code>verify</code>, and hands you the answer.`}
        </p>
        <p class="almanac-quote">
          ${zh() ? "\u201C\u6211\u4E0D\u9700\u8981\u4E00\u4E2A\u66FF\u6211\u505A\u51B3\u5B9A\u7684\u4EBA\uFF1B\u6211\u9700\u8981\u4E00\u4E2A\u628A\u51B3\u5B9A\u505A\u5F97\u66F4\u7A33\u7684\u4EBA\u3002\u201D" : "\u201CI don't need someone who decides for me; I need someone who makes decisions stand steadier.\u201D"}
        </p>
        <p class="almanac-sidenote">
          ${zh() ? "\u8FD9\u662F\u7ED9\u4F60\u7684\u4EA7\u54C1\u505A\u7684\u540C\u4E00\u4E2A\u95EE\u9898\uFF0C\u4F5C\u4E3A\u5750\u6807\u3002" : "The same question, asked about your product. This page is the coordinate."}
        </p>
      </div>
      ${digestInstrumentMarkup(digest)}
    </div>`;
  }
  function sparkMarkup() {
    const steps = zh() ? [
      { index: "01", head: "\u5165\u53E3", body: "\u7528\u6237\u5728 composer \u91CC\u6572\u4E0B\u4E00\u53E5\u8BDD\u3002\u7CFB\u7EDF\u8BFB\u6587\u4EF6\u3001\u8BFB git \u72B6\u6001\u3001\u8BFB\u4F1A\u8BDD\u5185\u5B58\u3002" },
      { index: "02", head: "\u8BA1\u5212", body: "\u6A21\u578B\u5728 plan / verify \u5FAA\u73AF\u91CC\u5207\u5206\u95EE\u9898\u3002\u6BCF\u4E00\u6B65\u90FD\u5F97\u5230\u4E00\u4EFD\u8BC1\u636E\u6216\u4E00\u79CD\u5931\u8D25\u3002" },
      { index: "03", head: "\u884C\u52A8", body: "read_file / edit_file / bash \u4EFB\u4E00\u5DE5\u5177\u88AB\u8C03\u7528\uFF0C\u8F93\u51FA\u88AB\u9A8C\u8BC1\u540E\u518D\u8FDB\u5165\u4E0B\u4E00\u8F6E\u3002" },
      { index: "04", head: "\u9A8C\u6536", body: "completion_assessment \u6216 verifier \u653E\u884C\u7B54\u6848\u3002\u672A\u901A\u8FC7\u5219\u505C\u5728\u539F\u5730\u5E76\u62A5\u544A\u3002" }
    ] : [
      { index: "01", head: "Intake", body: "You type a sentence in the composer. The system reads files, git status, and session memory." },
      { index: "02", head: "Plan", body: "The model splits the problem inside a plan / verify loop. Each step earns evidence or a named failure." },
      { index: "03", head: "Act", body: "read_file / edit_file / bash \u2014 every tool call's output is verified before the next round." },
      { index: "04", head: "Verify", body: "completion_assessment or the verifier clears the answer. If it doesn't pass, it stops right there and says why." }
    ];
    return `
    <div class="almanac-canvas almanac-spark">
      <div class="almanac-kicker">${zh() ? "\u5377\u4E00 \xB7 \u706B\u79CD" : "Chapter I \xB7 The Spark"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u4E00\u4E2A\u53E5\u5B50<br/>\u5982\u4F55\u53D8\u6210<span class="almanac-title-accent">\u4E00\u4E2A\u4EFB\u52A1\u3002</span>' : 'How a sentence<br/>becomes <span class="almanac-title-accent">a task.</span>'}</h1>
      <div class="almanac-body">
        <p>${zh() ? "\u4F60\u5728\u8F93\u5165\u6846\u6572\u4E0B\u4E00\u53E5\u8BDD\u3002\u7CFB\u7EDF\u8BFB\u6587\u4EF6\u3001\u8BFB git \u72B6\u6001\u3001\u8BFB\u4F1A\u8BDD\u5185\u5B58\uFF0C\u628A\u8FD9\u4E00\u53E5\u53D8\u6210\u4E00\u6761\u6D41\u6C34\u7EBF\uFF1A" : "You type one sentence. The system reads files, git status and session memory \u2014 and turns that sentence into a pipeline:"}</p>
      </div>
      <div class="almanac-chapter-aside">
        ${steps.map((s) => `<div class="almanac-step"><span class="almanac-step-index">${escapeHtml(s.index)}</span><div><strong>${escapeHtml(s.head)}</strong><p>${escapeHtml(s.body)}</p></div></div>`).join("\n        ")}
      </div>
    </div>`;
  }
  function renderInstrumentValue(metrics) {
    const tokens = metrics?.usage?.total_tokens ?? 0;
    const hitRate = metrics?.llm_cache?.cache_hit_rate ?? 0;
    return { tokens, hitRate };
  }
  function depthMarkup(metrics) {
    const { tokens, hitRate } = renderInstrumentValue(metrics);
    const hitLabel = hitRate > 0 ? `${Math.round(hitRate * 100)}%` : "\u2014";
    return `
    <div class="almanac-canvas almanac-depth">
      <div class="almanac-kicker">${zh() ? "\u5377\u4E8C \xB7 \u6DF1\u5EA6" : "Chapter II \xB7 The Depth"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u8D8A\u6DF1\u5165<br/>\u8D8A\u5BB9\u6613<span class="almanac-title-accent">\u88AB\u538B\u7F29\u3002</span>' : 'The deeper it goes,<br/><span class="almanac-title-accent">the more it compacts.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          \u7F16\u7801\u4F1A\u8BDD\u7684\u4EE3\u4EF7\u4E0D\u5728 token\uFF0C\u800C\u5728<em>\u6CE8\u610F\u529B</em>\u3002\u8FD9\u4E2A\u9879\u76EE\u7684\u4E0A\u4E0B\u6587\u538B\u7F29
          \u5728\u63A5\u8FD1\u9608\u503C\u65F6\u4FDD\u5B58<em>checkpoint</em>\uFF1A\u6458\u8981 + \u6700\u8FD1\u82E5\u5E72\u8F6E\u9010\u5B57\uFF0C\u5176\u4F59\u5168\u90E8\u4E22\u5F03\u3002
          \u4E22\u51FA\u53BB\u7684\u662F\u201C\u8FD9\u4E00\u523B\u201D\uFF0C\u7559\u4E0B\u7684\u662F\u201C\u6211\u5728\u505A\u4EC0\u4E48\u201D\u3002
        </p>
        <p>
          \u7F13\u5B58\u547D\u4E2D\u505A\u7684\u662F\u540C\u4E00\u4EF6\u4E8B\uFF1A\u7528\u524D\u7F00\u4EB2\u548C\u8BA9\u6A21\u578B<em>\u4E0D\u91CD\u65B0\u8BFB\u4E00\u904D</em>\u4F60\u521A\u5199\u5B8C\u7684\u4E0A\u4E0B\u6587\u3002
          \u6CA1\u6709\u5B83\uFF0C\u6BCF\u4E2A\u8BF7\u6C42\u90FD\u8981\u4E3A\u540C\u4E00\u6BB5 system prompt \u4ED8\u8D39\uFF1B\u6709\u5B83\uFF0C\u4ED8\u4E00\u6B21\u5C31\u884C\u4E86\u3002
        </p>` : `<p>
          The cost of a coding session is paid in <em>attention</em>, not tokens. This project's context compaction
          saves a <em>checkpoint</em> near the threshold: a summary plus the most recent turns verbatim; the rest is discarded.
          What gets thrown out is "this moment"; what remains is "what I am doing".
        </p>
        <p>
          Cache affinity solves the same problem: a prefix-aware model never re-reads the context you just wrote.
          Without it, every request pays for the same system prompt again; with it, you pay once.
        </p>`}
      </div>
      <div class="almanac-instrument">
        <div class="almanac-instrument-label">${zh() ? "\u672C\u5730\u6570\u636E \xB7 \u5B9E\u65F6\u8BFB\u6570" : "Local data \xB7 live reading"}</div>
        <div class="almanac-instrument-value">${compactNumber(tokens)} tokens in flight \xB7 hit rate ${escapeHtml(hitLabel)}</div>
      </div>
    </div>`;
  }
  function sentryMarkup(metrics) {
    const taskCount = metrics?.task_count ?? 0;
    const total = metrics?.usage?.total_tokens ?? 0;
    return `
    <div class="almanac-canvas almanac-sentry">
      <div class="almanac-kicker">${zh() ? "\u5377\u4E09 \xB7 \u54E8\u5175" : "Chapter III \xB7 The Sentry"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u6BCF\u4E00\u4E2A\u627F\u8BFA<br/>\u90FD\u662F\u4E00\u4E2A<span class="almanac-title-accent">\u95E8\u3002</span>' : 'Every promise<br/>is a <span class="almanac-title-accent">gate.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          \u5982\u679C agent \u53EF\u4EE5\u5728\u6CA1\u6709\u547D\u4EE4\u7684\u60C5\u51B5\u4E0B\u81EA\u79F0\u5B8C\u6210\uFF0C\u90A3\u4E48<em>\u4EFB\u4F55</em>\u590D\u6742
          \u7CFB\u7EDF\u90FD\u7ECF\u4E0D\u8D77\u7B2C\u4E09\u4E2A\u5DE5\u5177\u8C03\u7528\u3002\u8FD9\u4E2A\u9879\u76EE\u7684\u7B54\u6848\u662F\u4E00\u4E32 <code>tests/</code>\u2014\u2014
          \u6BCF\u4E2A change \u90FD\u5FC5\u987B\u901A\u8FC7\u81EA\u5DF1\u6CA1\u6709\u78B0\u5230\u8FC7\u7684\u95E8\u3002
        </p>
        <p>
          \u5B8C\u6210\u4E4B\u540E\u518D\u770B\uFF1A\u4E00\u4E2A <code>completion_assessed</code> \u4E8B\u4EF6\u4E0D\u4F1A\u6765\u81EA\u9759\u9ED8\u8DF3\u8FC7\uFF0C\u800C\u662F
          \u6765\u81EA\u660E\u786E\u83B7\u8BB8\u6216\u660E\u786E\u5224\u8F93\u3002
        </p>` : `<p>
          If an agent can claim completion without a command, then <em>any</em> complex system
          breaks on the third tool call. This project answers with a wall of <code>tests/</code> \u2014
          every change must clear gates it never touched.
        </p>
        <p>
          And after completion: a <code>completion_assessed</code> event never comes from a silent skip,
          only from explicit success or explicit failure.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u5DF2\u5B8C\u6210\u7684\u4EFB\u52A1\u603B\u6570" : "Tasks completed"}</div>
          <div class="almanac-instrument-value">${escapeHtml(String(taskCount))}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u7D2F\u8BA1\u6D88\u8017 tokens" : "Tokens consumed"}</div>
          <div class="almanac-instrument-value">${compactNumber(total)}</div>
        </div>
      </div>
    </div>`;
  }
  function bloomMarkup() {
    return `
    <div class="almanac-canvas almanac-bloom">
      <div class="almanac-kicker">${zh() ? "\u5377\u56DB \xB7 \u76DB\u653E" : "Chapter IV \xB7 The Bloom"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u8FD9\u4E2A<br/>\u5DE5\u4F5C\u53F0\u672C\u8EAB<br/>\u5C31\u662F<span class="almanac-title-accent">\u8BC1\u8BCD\u3002</span>' : 'This<br/>workbench<br/>itself is <span class="almanac-title-accent">testimony.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          \u8FD9\u91CC\u7684\u6BCF\u4E00\u5757\u4E0D\u4EC5\u4E0D\u53EA\u662F\u300C\u754C\u9762\u300D\u3002\u5DE6\u8FB9\u300C\u6700\u8FD1\u4EFB\u52A1\u300D\u4E0D\u662F\u5BFC\u822A\u680F\uFF1B\u300C\u7F13\u5B58\u547D\u4E2D\u7387\u300D\u4E0D\u662F\u767E\u5206\u6BD4\uFF1B
          \u300C\u4EFB\u52A1\u6863\u6848\u300D\u4E0D\u662F\u65E5\u5FD7\u2014\u2014\u5B83\u4EEC\u4E00\u8D77\u6784\u6210<strong>\u4EA4\u4ED8\u8FC7\u7A0B\u672C\u8EAB</strong>\u3002
        </p>
        <p>
          \u5C4F\u5E55\u4E0A\u6BCF\u4E2A\u6570\u503C\u90FD\u53EF\u4EE5\u88AB\u70B9\u51FB\u3001\u88AB\u5C55\u5F00\u3001\u88AB\u6298\u53E0\u3001\u88AB\u590D\u76D8\u3002\u771F\u6B63\u5728\u8FD9\u91CC\u8DD1\u8FC7\u7684 agent \u624D\u914D\u5F97\u4E0A
          \u300C\u5DF2\u8FDE\u63A5\u300D\u8FD9\u4E09\u4E2A\u5B57\u2014\u2014\u800C\u4E0D\u662F\u7ED9\u81EA\u5DF1\u6234\u8363\u8A89\u3002
        </p>` : `<p>
          Nothing here is "just UI". The recent-tasks list is not a sidebar; the cache hit rate is not a percentage;
          the task archive is not a log \u2014 together they <strong>are the delivery process itself</strong>.
        </p>
        <p>
          Every number on screen can be clicked, expanded, folded, replayed. Only an agent that has actually run here
          earns the right to the label "connected" \u2014 not as an honorific, but as a fact.
        </p>`}
      </div>
    </div>`;
  }
  function handMarkup() {
    const bullets = zh() ? [
      ["\u56DE\u653E Replay", "\u4EFB\u52A1\u4ECE intake \u5230 deliver \u7684\u6BCF\u4E00\u6B65\uFF0C\u5DF2\u7ECF\u53EF\u4EE5\u88AB\u56DE\u653E\u3001\u88AB diff\u3001\u88AB\u590D\u76D8\u3002"],
      ["\u8D26\u672C Ledger", "\u4F60\u5728\u8FD9\u91CC\u770B\u5230\u7684\u4E0D\u662F\u4F59\u989D\uFF0C\u662F\u4E00\u7B14\u4E00\u7B14\u53EF\u88AB\u5BA1\u8BA1\u7684 token\u3002"],
      ["\u8109\u640F Pulse", "\u4F60\u5728\u4EFB\u4F55\u65F6\u5019\u90FD\u53EF\u4EE5\u6253\u5F00\u300C\u5DE5\u4F5C\u533A\u8109\u640F\u300D\uFF0C\u770B\u89C1\u8FD9\u4E2A\u9879\u76EE\u5728\u547C\u5438\u3002"],
      ["\u6A21\u677F\u5E93 Templates", "8 \u5F20\u7ECF\u8FC7\u7B56\u5212\u7684 prompt\uFF0C\u8BA9\u65B0\u624B\u5C11\u7FFB\u534A\u5929\u6587\u6863\u3002"],
      ["Spring Cloud \u5E73\u9762", "\u4E91\u4FA7\u7684\u670D\u52A1\u8FB9\u754C\u6B63\u5728\u53D8\u5F97\u66F4\u771F\u5B9E\uFF1A\u6CE8\u518C\u53D1\u73B0\u3001\u914D\u7F6E\u4E0B\u53D1\u3001\u9650\u6D41\u3002"],
      ["MCP \u4E0E \u6280\u80FD", "\u4F60\u7684\u7F16\u8F91\u5668\u91CC\u6F5C\u85CF\u7684\u80FD\u529B\uFF0C\u53EF\u4EE5\u88AB\u63A5\u5230\u8FD9\u6761\u6D41\u6C34\u7EBF\u3002"]
    ] : [
      ["Replay", "Every step from intake to deliver can already be replayed, diffed, reviewed."],
      ["Ledger", "What you see here is not a balance; it is token-by-token auditability."],
      ["Pulse", "Any time, open the workspace pulse and watch this project breathe."],
      ["Templates", "Eight curated prompts so new users don't spend half a day reading docs."],
      ["Spring Cloud plane", "The cloud-side service boundaries keep getting realer: discovery, config push, rate limits."],
      ["MCP & skills", "Abilities hidden inside your editor can be wired into this pipeline."]
    ];
    return `
    <div class="almanac-canvas almanac-hand">
      <div class="almanac-kicker">${zh() ? "\u5377\u4E94 \xB7 \u8FDC\u884C" : "Chapter V \xB7 The Open Road"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u8FD8\u6709\u597D\u591A<br/>\u53EF\u4EE5\u7EE7\u7EED<span class="almanac-title-accent">\u505A\u7684\u4E8B\u3002</span>' : 'So much is<br/>still worth <span class="almanac-title-accent">doing.</span>'}</h1>
      <div class="almanac-body">
        <p>${zh() ? "\u8FD9\u4E2A\u9879\u76EE\u8FD8\u5728\u957F\uFF1A" : "This project is still growing:"}</p>
        <ul class="almanac-chapter-list">
          ${bullets.map(([b, s]) => `<li><strong>${escapeHtml(b)}</strong> \u2014 ${escapeHtml(s)}</li>`).join("\n          ")}
        </ul>
        <p class="almanac-quote almanac-quote-end">
          ${zh() ? "\u8FD9\u4E2A\u4EA7\u54C1\u7684\u672A\u6765\u662F\uFF1A\u4F60\u5199\u4E0B\u6BCF\u4E00\u6761\u6307\u4EE4\u4E4B\u540E\uFF0C\u4E16\u754C\u4F1A\u56E0\u6B64\u66F4\u7CBE\u786E\u4E00\u70B9\u70B9\u3002" : "The product's future: after you write every instruction, the world is a little more precise because of it."}
        </p>
      </div>
    </div>`;
  }
  function gateMarkup(digest) {
    const commits = digest && digest.is_git === true && digest.total_commits != null ? String(digest.total_commits) : "\u2014";
    const tests = digest && digest.is_git === true && digest.test_files != null ? String(digest.test_files) : "\u2014";
    const batches = digest && digest.is_git === true && digest.roadmap_batches != null ? zh() ? `${digest.roadmap_batches} \u7AE0` : `${digest.roadmap_batches} chapters` : "\u2014";
    const rows = (zh() ? [
      ["Python \u53CC\u5E73\u53F0", "ubuntu-latest + windows-latest \xB7 \u6BCF\u63A8\u9001\u4E00\u6B21\u5168\u91CF\u8DD1\uFF0C\u4E24\u4E2A\u64CD\u4F5C\u7CFB\u7EDF\u5404\u81EA\u5224\u5377"],
      ["\u58F0\u660E\u6838\u5BF9\u5668", "doc pointers\uFF08\u60AC\u7A7A\u8BC1\u636E\u96F6\u5BB9\u5FCD\uFF09\xB7 route coverage \xB7 impact floor\uFF08\u6BCF\u4E2A\u6A21\u5757\u90FD\u8981\u88AB\u6D4B\u8BD5\u591F\u5F97\u7740\uFF09"],
      ["JavaScript \u8BED\u6CD5\u95E8", "22 \u4E2A\u8BED\u6CD5/\u534F\u8BAE\u95E8 \xB7 \u4EFB\u4E00\u6761\u4E0D\u8FC7\uFF0C\u8FD9\u6247\u95E8\u5C31\u4E0D\u7B97\u8FC7"],
      ["Service plane", "mvn \xB7 7 \u4E2A Spring Cloud \u6A21\u5757 \xB7 \u7F51\u5173 / \u6CE8\u518C / \u914D\u7F6E / \u4EFB\u52A1 / \u6D1E\u5BDF / \u5DE1\u68C0 / \u6865\u63A5"],
      ["Playwright \xD72", "\u771F\u6D4F\u89C8\u5668 \xB7 \u542B\u300C\u4E0D\u53EF\u8FBE\u63D0\u4F9B\u65B9\u5FC5\u987B\u5931\u8D25\u300D\u2014\u2014\u95E8\u672C\u8EAB\u4E5F\u88AB\u95E8\u5B88\u7740"]
    ] : [
      ["Python, two platforms", "ubuntu-latest + windows-latest \xB7 the full suite on every push, both OSes grading"],
      ["Claim checkers", "doc pointers (no dangling evidence) \xB7 route coverage \xB7 impact floor (every module must be reachable by a test)"],
      ["JavaScript syntax gates", "22 syntax/protocol gates \xB7 if one fails, the gate does not count as passed"],
      ["Service plane", "mvn \xB7 7 Spring Cloud modules \xB7 gateway / registry / config / tasks / insights / inspector / bridge"],
      ["Playwright \xD72", "Real browsers \xB7 including 'an unreachable provider must fail' \u2014 the gates are gated too"]
    ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
    return `
    <div class="almanac-canvas almanac-gate">
      <div class="almanac-kicker">${zh() ? "\u5377\u516D \xB7 \u5173\u5361" : "Chapter VI \xB7 The Gate"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u4E0D\u662F\u5199\u5B8C\u4E86\uFF0C<br/>\u662F\u88AB<span class="almanac-title-accent">\u5168\u90E8\u6279\u51C6\u4E86\u3002</span>' : `Not 'it's written',<br/>but <span class="almanac-title-accent">'it's all approved.'</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          \u8FD9\u4E2A\u9879\u76EE\u6700\u5B89\u9759\u3001\u4E5F\u6700\u8BDA\u5B9E\u7684\u89D2\u8272\u662F CI\u3002\u6BCF\u4E00\u6B21\u63D0\u4EA4\u90FD\u8981\u7ECF\u8FC7\u540C\u4E00\u6392\u95E8\uFF1A
          \u53CC\u5E73\u53F0\u5168\u91CF\u6D4B\u8BD5\u3001\u6587\u6863\u95E8\u7981\u3001\u8DEF\u7531\u8986\u76D6\u7387\u4E0E\u6A21\u5757\u5F15\u7528\u9762\u300122 \u4E2A JS \u534F\u8BAE\u95E8\u3001
          Spring Cloud plane \u7684 mvn \u5957\u4EF6\u3001\u771F\u6D4F\u89C8\u5668 \xD72\u3002
        </p>
        <p>
          \u4EFB\u4F55\u4E00\u9053\u95E8\u7EA2\u4E86\uFF0C\u8FD9\u6247\u95E8\u5C31\u6CA1\u6709\u610F\u4E49\u3002\u5B83\u4ECE\u4E0D\u8BF4\u8C0E\uFF0C\u56E0\u4E3A\u5B83\u4ECE\u4E0D\u88AB\u5141\u8BB8\u8BF4\u8C0E\uFF1A
          \u65AD\u8A00\u5931\u8D25\u7684\u6570\u5B57\u3001\u60AC\u7A7A\u7684\u8BC1\u636E\u6307\u9488\u3001\u88AB\u6F0F\u6389\u7684\u8DEF\u7531\u3001\u5931\u8E2A\u7684\u5F15\u7528\u9762\u2014\u2014\u6BCF\u4E00\u4E2A
          \u90FD\u8BA9\u7EA2\u706F\u4EAE\u8D77\u6765\uFF0C\u800C\u4E0D\u662F\u8BB0\u5728\u5FC3\u91CC\u3002
        </p>` : `<p>
          The quietest and most honest role in this project is CI. Every push goes through the same row of gates:
          the dual-platform full suite, doc gates, route coverage and module reference surface, 22 JS protocol gates,
          the Spring Cloud plane's mvn suite, two real browsers.
        </p>
        <p>
          If any gate is red, the gate has no meaning. It never lies, because it is never allowed to:
          a failed assertion count, a dangling evidence pointer, a missing route, a missing reference
          surface \u2014 each one turns a light red instead of being quietly remembered.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u95E8\u653E\u8FC7\u7684\u63D0\u4EA4\u6570" : "Commits passed by the gates"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u95E8 \xB7 \u6D4B\u8BD5\u6587\u4EF6" : "Gate \xB7 test files"}</div>
          <div class="almanac-instrument-value">${escapeHtml(tests)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u95E8\u7684\u6587\u732E \xB7 \u6279\u6B21\u7AE0\u8282" : "Gate's canon \xB7 batch chapters"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "\u8FD9\u4E2A\u9879\u76EE\u7684\u5B8C\u6210\u6807\u51C6\u4E0D\u662F\u300C\u505A\u5B8C\u4E86\u300D\uFF0C\u800C\u662F\u300C\u6240\u6709\u7684\u95E8\u90FD\u70B9\u4E86\u5934\u300D\u3002" : `This project's definition of done is not "finished" \u2014 it is "every gate nodded."`}
      </p>
    </div>`;
  }
  function meshMarkup() {
    const list = (zh() ? [
      ["Eureka", "\u6CE8\u518C\u53D1\u73B0 \u2014 \u7F51\u5173\u53EA\u5411\u6CE8\u518C\u4E2D\u5FC3\u7D22\u53D6\u5065\u5EB7\u5B9E\u4F8B\uFF0C\u4ECE\u4E0D\u786C\u7F16\u7801\u5730\u5740"],
      ["Spring Cloud Gateway", "lb:// \u8D1F\u8F7D\u5747\u8861 + RequestSize \u9884\u62D2\u7EDD + \u7194\u65AD\u8DEF\u7531"],
      ["Redis \u4EE4\u724C\u6876", "\u6BCF\u79D2 20 \u679A\u56DE\u586B / 40 \u679A\u7A81\u53D1 \xB7 \u6BCF IP \u8BA1\u6570 \xB7 Micrometer \u8BA1\u6570 gateway.rate_limited{route}"],
      ["Resilience4j", "\u6ED1\u52A8\u7A97\u53E3 10 \xB7 50% \u5931\u8D25\u5373\u7194\u65AD \xB7 \u534A\u5F00\u8BD5\u63A2\u4E4B\u540E\u81EA\u52A8\u95ED\u5408"],
      ["RabbitMQ", "\u7F51\u5173\u7F13\u5B58\u5931\u6548\u5E7F\u64AD\uFF1A\u8DEF\u7531\u8868\u53D8\u66F4\u4E00\u79D2\u5185\u540C\u6B65\u5230\u6240\u6709\u5B9E\u4F8B"]
    ] : [
      ["Eureka", "Discovery \u2014 the gateway only ever asks the registry for healthy instances, never a hard-coded address"],
      ["Spring Cloud Gateway", "lb:// load balancing + RequestSize pre-reject + circuit-breaker routes"],
      ["Redis token bucket", "20 refills/s / 40 burst \xB7 per-IP counter \xB7 Micrometer counter gateway.rate_limited{route}"],
      ["Resilience4j", "Sliding window 10 \xB7 50% failure opens the circuit \xB7 half-open probe, then auto-close"],
      ["RabbitMQ", "Gateway cache-invalidation broadcast: route changes reach every instance within one second"]
    ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
    return `
    <div class="almanac-canvas almanac-mesh">
      <div class="almanac-kicker">${zh() ? "\u5377\u4E03 \xB7 \u661F\u7F51" : "Chapter VII \xB7 The Mesh"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '\u516D\u4E2A\u670D\u52A1\uFF0C<br/><span class="almanac-title-accent">\u4E00\u4E2A\u56FD\u5BB6\u3002</span>' : 'Six services,<br/><span class="almanac-title-accent">one country.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          \u8FD9\u4E2A\u4ED3\u5E93\u6709\u4E00\u534A\u5728\u4E91\u91CC\u3002Java \u4E0E Spring Cloud \u7EC4\u6210\u7684 plane \u6709\u4E03\u4E2A\u6A21\u5757\uFF1A
          \u6CE8\u518C\u4E2D\u5FC3\u3001\u914D\u7F6E\u4E2D\u5FC3\u3001\u7F51\u5173\u3001\u6D1E\u5BDF\u3001\u5DE1\u68C0\u3001\u4EFB\u52A1\uFF0C\u4EE5\u53CA\u628A Python \u5F15\u64CE\u7FFB\u8BD1\u6210 HTTP \u5951\u7EA6\u7684\u6865\u63A5\u5C42\u3002
          Eureka \u8BA4\u8BC6\u5B83\u4EEC\u6BCF\u4E00\u4E2A\uFF0C\u7F51\u5173\u4ECE\u4E0D\u95EE\u5730\u5740\u2014\u2014\u53EA\u95EE\u201C\u8C01\u5065\u5EB7\u201D\u3002
        </p>
        <p>
          \u7F51\u5173\u80CC\u540E\u6709 Redis \u94F8\u6210\u7684\u4EE4\u724C\u6876\uFF08\u6BCF\u79D2 20 \u679A\u56DE\u586B\u300140 \u679A\u7A81\u53D1\uFF09\uFF0C
          \u4E5F\u6709 Resilience4j \u94F8\u6210\u7684\u7194\u65AD\u5668\u2014\u2014\u8FC7\u8F7D\u65F6\u5B83\u5FEB\u901F\u5931\u8D25\uFF0C\u5E76\u9012\u51FA\u4E00\u53E5
          <em>\u4E0D\u5192\u5145\u7A7A\u6570\u636E</em>\u7684\u56DE\u7B54\u3002RabbitMQ \u5728\u5B83\u4EEC\u4E4B\u95F4\u642C\u8FD0\u7F13\u5B58\u5931\u6548\u5E7F\u64AD\uFF0C
          \u8BA9\u6BCF\u4E2A\u5B9E\u4F8B\u5728\u4E00\u79D2\u5185\u77E5\u9053\u201C\u90A3\u6761\u7F13\u5B58\u5DF2\u7ECF\u8FC7\u671F\u201D\u3002
        </p>
        <p>
          2026 \u5E74 11 \u6708 14 \u65E5\uFF0C\u4E00\u573A\u5B9E\u5F39\u6F14\u4E60\u5728\u8FD9\u53F0\u673A\u5668\u4E0A\u6253\u54CD\uFF1A
          120 \u4E2A\u5E76\u53D1\u8BF7\u6C42\u4E00\u6B21\u6027\u6D8C\u5411\u7F51\u5173\u300225 \u4E2A\u62FF\u5230 200\uFF0C
          60 \u4E2A\u88AB\u4EE4\u724C\u6876\u6321\u56DE\uFF08429\uFF09\uFF0C35 \u4E2A\u5728\u7194\u65AD\u5FEB\u5F00\u65F6\u88AB\u8BDA\u5B9E\u62D2\u7EDD\uFF08503\uFF09\u3002
          \u5341\u4E94\u79D2\u540E\uFF0C\u4E00\u5207\u6062\u590D\u95ED\u5408\uFF0C\u6CA1\u6709\u4E00\u6761\u8BB0\u5F55\u4E22\u5931\u3002
        </p>` : `<p>
          Half this repository lives in the cloud. The Java/Spring Cloud plane has seven modules:
          registry, config, gateway, insights, inspector, tasks \u2014 and the bridge that translates the Python engine into an HTTP contract.
          Eureka knows every one of them; the gateway never asks for addresses, only \u201Cwho is healthy\u201D.
        </p>
        <p>
          Behind the gateway sits a Redis-cast token bucket (20 refills per second, 40 burst)
          and a Resilience4j-cast circuit breaker \u2014 under overload it fails fast and answers
          with an <em>honest, not-fake-empty</em> response. RabbitMQ shuttles cache-invalidation broadcasts
          between them, so every instance learns "that cache entry is stale" within a second.
        </p>
        <p>
          On November 14, 2026, a live-fire drill ran on this very machine:
          120 concurrent requests hit the gateway at once. 25 got 200,
          60 were turned away by the token bucket (429), 35 were honestly refused while the circuit was open (503).
          Fifteen seconds later, everything closed again \u2014 no record was lost.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u5B9E\u5F39 \xB7 \u88AB\u9650\u6D41" : "Live-fire \xB7 rate limited"}</div>
          <div class="almanac-instrument-value">60 \xD7 429</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u5B9E\u5F39 \xB7 \u7194\u65AD\u5FEB\u5F00" : "Live-fire \xB7 fast-open"}</div>
          <div class="almanac-instrument-value">31</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "\u6062\u590D\u8017\u65F6" : "Recovery"}</div>
          <div class="almanac-instrument-value">\u2264 15s</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${list}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "\u4E00\u4E2A\u56FD\u5BB6\u7684\u8FB9\u5883\uFF0C\u4E0D\u53D6\u51B3\u4E8E\u57CE\u5899\u6709\u591A\u9AD8\uFF0C\u800C\u53D6\u51B3\u4E8E\u6BCF\u4E00\u4E2A\u5173\u5361\u90FD\u77E5\u9053\u81EA\u5DF1\u5728\u5B88\u4EC0\u4E48\u3002" : "A country's border is not defined by how high its walls are \u2014 but by whether every checkpoint knows what it is guarding."}
      </p>
    </div>`;
  }
  var CHAPTER_RENDERERS = {
    prologue: () => prologueMarkup(digestCache),
    spark: () => sparkMarkup(),
    depth: (metrics) => depthMarkup(metrics),
    sentry: (metrics) => sentryMarkup(metrics),
    bloom: () => bloomMarkup(),
    hand: () => handMarkup(),
    gate: () => gateMarkup(digestCache),
    mesh: () => meshMarkup(),
    witness: () => witnessMarkup()
  };
  async function loadChapter(id) {
    const slot = $("#almanacCanvas");
    if (!slot) return;
    const [metrics, digest, stats] = await Promise.all([
      requestJson("/api/metrics").catch(() => null),
      requestJson("/api/digest").catch(() => null),
      requestJson("/api/stats").catch(() => null)
    ]);
    digestCache = digest;
    statsCache = stats;
    const renderer = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
    slot.innerHTML = renderer(metrics);
    refreshIcons();
  }
  async function openAlmanacPanel() {
    const current = beginPanelRequest(t("almanac.title"));
    try {
      const rail = CHAPTERS.map(chapterMarkup).join("");
      openPanel(t("almanac.title"), `
      <div class="almanac-shell">
        <nav class="almanac-rail" aria-label="${zh() ? "\u7AE0\u8282" : "Chapters"}">${rail}</nav>
        <div class="almanac-canvas-shell"><div class="almanac-canvas" id="almanacCanvas">${prologueMarkup(digestCache)}</div></div>
      </div>
    `, { wide: true });
      document.querySelectorAll(".almanac-chapter").forEach((button) => {
        button.addEventListener("click", () => {
          document.querySelectorAll(".almanac-chapter").forEach((b) => b.classList.toggle("active", b === button));
          currentChapter = button.getAttribute("data-chapter") || "prologue";
          loadChapter(currentChapter);
        });
      });
      document.querySelector('.almanac-chapter[data-chapter="prologue"]')?.classList.add("active");
      refreshIcons();
      requestJson("/api/digest").then((digest) => {
        digestCache = digest;
        if (currentChapter !== "prologue") return;
        const slot = $("#almanacCanvas");
        if (!slot) return;
        slot.innerHTML = prologueMarkup(digestCache);
        refreshIcons();
      }).catch(() => {
      });
    } catch (error) {
      if (!current()) return;
      openPanel(t("almanac.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }

  // web/src/panels/manual.js
  var CHAPTERS2 = [
    { id: "start", roman: "\u4E00", romanEn: "1", title: "Quick Start", titleZh: "\u4E94\u5206\u949F\u4E0A\u624B" },
    { id: "workbench", roman: "\u4E8C", romanEn: "2", title: "The Workbench", titleZh: "\u5DE5\u4F5C\u53F0\u5BFC\u89C8" },
    { id: "modules", roman: "\u4E09", romanEn: "3", title: "The Modules", titleZh: "\u4E03\u4E2A\u6A21\u5757\uFF0C\u4E00\u4E2A\u4E16\u754C" },
    { id: "keys", roman: "\u56DB", romanEn: "4", title: "Commands & Shortcuts", titleZh: "\u547D\u4EE4\u4E0E\u5FEB\u6377\u952E" },
    { id: "arcade", roman: "\u4E94", romanEn: "5", title: "Playbook", titleZh: "\u6E38\u620F\u5385\u6559\u7A0B" },
    { id: "trouble", roman: "\u516D", romanEn: "6", title: "Troubleshooting", titleZh: "\u6392\u9519" },
    { id: "limits", roman: "\u4E03", romanEn: "7", title: "Honest Limits", titleZh: "\u8FB9\u754C\u4E0E\u8303\u56F4" }
  ];
  function zhStart() {
    return `
    <p class="manual-lede">\u4E00\u4E2A\u672C\u5730\u4F18\u5148\u7684\u7F16\u7A0B\u667A\u80FD\u4F53\u2014\u2014\u5B83\u63A5\u53D7 <code>MINICC_API_KEY</code>\u3001<code>MINICC_BASE_URL</code>\u3001<code>MINICC_MODEL</code>\uFF0C\u7136\u540E\u5728\u4F60\u7684\u5DE5\u4F5C\u533A\u91CC\u771F\u6B63\u8BFB\u5199\u3001\u8FD0\u884C\u3001\u9A8C\u8BC1\uFF0C\u6700\u540E\u628A\u8BC1\u636E\u4EA4\u56DE\u7ED9\u4F60\u3002</p>
    <ol class="manual-list">
      <li><strong>\u7B2C\u4E00\u6B65\uFF1A\u914D\u7F6E</strong> \u590D\u5236 <code>minicc.config.example</code> \u4E3A <code>.env</code>\uFF0C\u586B\u5165\u4E09\u4E2A\u73AF\u5883\u53D8\u91CF\uFF1A<code>MINICC_API_KEY</code>\u3001<code>MINICC_BASE_URL</code>\u3001<code>MINICC_MODEL</code>\uFF08\u4EFB\u4F55 OpenAI \u517C\u5BB9\u7684\u7F51\u5173\u90FD\u53EF\u4EE5\uFF0C\u5305\u62EC\u4F60\u7684\u79C1\u6709\u4EE3\u7406\uFF09\u3002</li>
      <li><strong>\u7B2C\u4E8C\u6B65\uFF1A\u542F\u52A8</strong> <code>minicc-web --workspace /\u4F60\u7684\u9879\u76EE\u8DEF\u5F84</code>\uFF0C\u6253\u5F00 <code>http://127.0.0.1:8765/</code>\u3002</li>
      <li><strong>\u7B2C\u4E09\u6B65\uFF1A\u53D1\u7B2C\u4E00\u4E2A\u4EFB\u52A1</strong> \u5728\u8F93\u5165\u6846\u91CC\u8BF4\u4EBA\u8BDD\u2014\u2014\u6BD4\u5982\u300C\u8BFB\u4E00\u4E0B README.md \u5E76\u544A\u8BC9\u6211\u8FD9\u4E2A\u9879\u76EE\u662F\u5E72\u561B\u7684\u300D\u3002\u591A\u4EFB\u52A1\u4F1A\u81EA\u52A8\u62C6\u6210\u7236\u5B50\u4EFB\u52A1\u3002</li>
      <li><strong>\u7B2C\u56DB\u6B65\uFF1A\u770B\u8FDE\u63A5</strong> \u5E95\u90E8\u72B6\u6001\u680F\u51FA\u73B0 <em>\u5DF2\u8FDE\u63A5</em>\u3001\u4EFB\u52A1\u6D41\u5F00\u59CB\u6EDA\u52A8\uFF0C\u8BF4\u660E\u6A21\u578B\u4E0E\u672C\u5730\u5DE5\u5177\u90FD\u901A\u4E86\u3002\u56DE\u7B54\u51FA\u6765\u540E\u70B9\u5F00\u4EFB\u52A1\u8BE6\u60C5\uFF0C\u91CC\u9762\u6709\u5168\u90E8\u5DE5\u5177\u8C03\u7528\u3001\u9010\u8F6E\u7F13\u5B58\u547D\u4E2D\u7387\u3001\u5B8C\u6210\u9A8C\u6536\u8BB0\u5F55\u3002</li>
      <li><strong>\u7B2C\u4E94\u6B65\uFF1A\u56DE\u653E</strong> \u4EFB\u52A1\u8BE6\u60C5\u9876\u90E8\u70B9\u300C\u56DE\u653E\u6574\u4E2A\u4EFB\u52A1\u300D\uFF0C\u6309\u4E8B\u4EF6\u987A\u5E8F\u91CD\u6F14\u4E00\u6B21\u4EA4\u4ED8\u8FC7\u7A0B\u2014\u2014\u50CF\u770B\u4E00\u573A\u7535\u5F71\uFF0C\u652F\u6301\u6682\u505C\u3001\u62D6\u62FD\u8FDB\u5EA6\u30011\xD7/2\xD7/4\xD7 \u500D\u901F\u3002</li>
    </ol>
    <div class="manual-callout">
      <strong>\u4E0D\u60F3\u8BFB\u5B57\uFF1F\u76F4\u63A5\u770B\u4E00\u904D\u3002</strong>
      <p>\u70B9\u4E0B\u9762\u8FD9\u4E2A\u6309\u94AE\uFF0C\u5DE5\u4F5C\u53F0\u4F1A\u73B0\u573A\u6F14\u793A\u4E00\u6B21\u5B8C\u6574 Agent \u4EFB\u52A1\uFF1A\u8F93\u5165 \u2192 \u8BA1\u5212 \u2192 \u5DE5\u5177\u8C03\u7528 \u2192 \u6D4B\u8BD5\u9A8C\u8BC1 \u2192 \u4EA4\u4ED8\u603B\u7ED3\u2014\u2014\u770B\u5B8C\u4F60\u5C31\u4F1A\u7528\u4E86\u3002</p>
      <button type="button" class="manual-demo-run" data-manual-demo>\u8FD0\u884C\u4E00\u6B21\u5B8C\u6574\u6F14\u793A</button>
    </div>
    <p>\u4E0D\u60F3\u6253\u5F00\u6D4F\u89C8\u5668\uFF1F\u547D\u4EE4\u884C\u4E5F\u80FD\u76F4\u63A5\u7528\uFF1A<code>minicc "\u8BFB README \u5E76\u603B\u7ED3"</code>\uFF0C\u6216 <code>minicc --stats</code> \u770B\u5DE5\u4F5C\u533A\u4F53\u5F81\u3002</p>
  `;
  }
  function enStart() {
    return `
    <p class="manual-lede">A local-first coding agent. Give it <code>MINICC_API_KEY</code>, <code>MINICC_BASE_URL</code> and <code>MINICC_MODEL</code>, and it reads, edits, runs and verifies \u2014 then hands you the evidence.</p>
    <ol class="manual-list">
      <li><strong>Step 1 \u2014 Configure</strong> copy <code>minicc.config.example</code> to <code>.env</code> and fill three variables: <code>MINICC_API_KEY</code>, <code>MINICC_BASE_URL</code>, <code>MINICC_MODEL</code> (any OpenAI-compatible gateway works, including your private proxy).</li>
      <li><strong>Step 2 \u2014 Start</strong> run <code>minicc-web --workspace /path/to/your/project</code>, open <code>http://127.0.0.1:8765/</code>.</li>
      <li><strong>Step 3 \u2014 Send your first task</strong> type a sentence in the composer \u2014 e.g. \u201CRead README.md and tell me what this project does.\u201D Multi-part sentences are auto-split into parent and child tasks.</li>
      <li><strong>Step 4 \u2014 Watch it connect</strong> the status bar shows <em>Connected</em> and the task stream starts scrolling. When the answer arrives, open the task detail to see every tool call, per-turn cache hit rate, and the completion verdict.</li>
      <li><strong>Step 5 \u2014 Replay it</strong> from the task detail top, click \u201CReplay the whole task\u201D to replay the delivery event by event \u2014 pause, scrub the progress bar, 1\xD7/2\xD7/4\xD7 speed.</li>
    </ol>
    <div class="manual-callout">
      <strong>Would rather watch than read?</strong>
      <p>Click the button below and the workbench will run a full agent task for you, live: intake \u2192 plan \u2192 tool calls \u2192 test verification \u2192 delivery summary. Watch it once and you know the product.</p>
      <button type="button" class="manual-demo-run" data-manual-demo>Run the live demo</button>
    </div>
    <p>Prefer the CLI? <code>minicc "Read README and summarize it"</code>, or <code>minicc --stats</code> for an operational inventory.</p>
  `;
  }
  function zhWorkbench() {
    return `
    <p class="manual-lede">\u4E09\u680F\u5E03\u5C40\uFF1A<strong>\u5DE6\u680F</strong> \u662F\u4EFB\u52A1\u5BFC\u822A\u4E0E\u5206\u652F\uFF0C<strong>\u4E2D\u680F</strong> \u662F\u5BF9\u8BDD\u4E0E\u5DE5\u4F5C\u6D41\uFF0C<strong>\u53F3\u680F</strong> \u662F\u9A8C\u8BC1\u4E0E\u5BA1\u8BA1\u8BC1\u636E\u3002</p>
    <div class="manual-grid-list">
      <div><strong>\u8F93\u5165\u6846</strong><span>\u76F4\u63A5\u8BF4\u4EBA\u8BDD\uFF1B\u591A\u4EFB\u52A1\u4F1A\u81EA\u52A8\u7F16\u6392\uFF0C\u4E00\u4E2A\u53E5\u5B50\u91CC\u7684\u591A\u4EF6\u4E8B\u4F1A\u88AB\u62C6\u6210\u7236\u5B50\u4EFB\u52A1\u3002</span></div>
      <div><strong>\u4EFB\u52A1\u8BE6\u60C5</strong><span>\u70B9\u5F00\u4EFB\u610F\u4EFB\u52A1\uFF1A\u5DE5\u5177\u8C03\u7528\u3001\u9010\u8F6E turn\u3001\u7F13\u5B58\u547D\u4E2D\u7387\u706B\u82B1\u7EBF\u3001\u9010\u6B21\u8C03\u7528\u7684\u7CFB\u7EDF/\u6D88\u606F/\u5DE5\u5177\u6307\u7EB9\u5168\u90E8\u53EF\u89C1\u3002</span></div>
      <div><strong>\u56DE\u653E\u5E2D</strong><span>\u4EFB\u52A1\u8BE6\u60C5\u9876\u90E8\u300C\u56DE\u653E\u6574\u4E2A\u4EFB\u52A1\u300D\u628A\u4E00\u6B21\u4EA4\u4ED8\u6309\u4E8B\u4EF6\u987A\u5E8F\u5B8C\u6574\u91CD\u64AD\u2014\u2014\u50CF\u770B\u4E00\u573A\u7535\u5F71\u3002</span></div>
      <div><strong>\u6743\u9650\u6A21\u5F0F</strong><span>\u666E\u901A\u6A21\u5F0F\u9ED8\u8BA4\u5199\u5165\u524D\u8BE2\u95EE\uFF1Byolo \u6A21\u5F0F\u5168\u81EA\u52A8\uFF0C\u4F46\u5DE5\u5177\u540D\u3001\u8DEF\u5F84\u4E0E\u547D\u4EE4\u4ECD\u7136\u5199\u5165\u5BA1\u8BA1\u65E5\u5FD7\u3002</span></div>
      <div><strong>\u4F1A\u8BDD\u89C6\u56FE</strong><span>\u540C\u4E00 session \u5185\u53EF\u4EE5\u5206\u652F\u3001diff\u3001\u56DE\u6EDA\u2014\u2014\u89C6\u56FE\u4E0E\u5DE5\u4F5C\u533A\u72B6\u6001\u7ED1\u5B9A\uFF0C\u5207\u6362\u4E0D\u4F1A\u8BEF\u8BFB\u65E7\u5BF9\u8BDD\u3002</span></div>
      <div><strong>\u5BA1\u8BA1\u9762\u677F</strong><span>\u6BCF\u4E00\u6761\u5DE5\u5177\u8C03\u7528\u90FD\u4EE5 info/notice/warning \u843D\u76D8\u5E76\u8131\u654F\uFF0Capi_key \u6C38\u8FDC\u4E0D\u4F1A\u51FA\u73B0\u5728\u65E5\u5FD7\u91CC\u3002</span></div>
    </div>
  `;
  }
  function enWorkbench() {
    return `
    <p class="manual-lede">Three columns: <strong>left</strong> is the task navigator, <strong>middle</strong> is the conversation and work flow, <strong>right</strong> is the verification and audit evidence.</p>
    <div class="manual-grid-list">
      <div><strong>Composer</strong><span>Just say it. A sentence naming multiple things becomes a parent task with auto-orchestrated children.</span></div>
      <div><strong>Task detail</strong><span>Any task: tool calls, turns, the per-turn cache-hit sparkline, per-call system/messages/tools fingerprints \u2014 all inspectable.</span></div>
      <div><strong>Replay</strong><span>\u201CReplay the whole task\u201D from the detail top replays the delivery as an ordered event film \u2014 scrub it like a player.</span></div>
      <div><strong>Permissions</strong><span>Default mode asks before writes; yolo mode runs autonomously \u2014 tool name, path and command always land in the audit log.</span></div>
      <div><strong>Session views</strong><span>Branch, diff and roll back inside a session; view state is bound to the workspace so you never read a stale conversation.</span></div>
      <div><strong>Audit panel</strong><span>Every tool call is logged with a level and a redacted payload \u2014 api_key never appears in the log.</span></div>
    </div>
  `;
  }
  function zhModules() {
    return `
    <p class="manual-lede">\u5DE5\u4F5C\u53F0\u4E4B\u4E0A\u6709\u4E00\u6574\u5957\u968F\u5904\u53EF\u8FBE\u7684\u6A21\u5757\u2014\u2014\u5B83\u4EEC\u4E0D\u662F\u5B64\u5C9B\uFF0C\u800C\u662F\u540C\u4E00\u4EFD\u8BC1\u636E\u7684\u4E0D\u540C\u89C6\u89D2\u3002</p>
    <ul class="manual-chapter-list">
      <li><strong>\u8D26\u672C \xB7 Ledger</strong> \u2014 \u2318L \u6253\u5F00\uFF1A\u603B token \u91D1\u53E5\u3001\u7F13\u5B58\u547D\u4E2D\u7387\u5706\u73AF\uFF08hit/miss/write \u62C6\u5206\uFF09\u3001\u6210\u672C\u4E0E\u672A\u5B9A\u4EF7\u6807\u6CE8\u3001\u6A21\u578B\u5206\u89E3\u8868\u3001\u72B6\u6001 segmented bar\u3002\u4E00\u5207\u6570\u5B57\u6765\u81EA\u771F\u5B9E\u4EFB\u52A1\u5FEB\u7167\u3002</li>
      <li><strong>\u8109\u640F \xB7 Pulse</strong> \u2014 \u4E09\u73AF\uFF08\u547D\u4E2D\u7387/\u4E0A\u4E0B\u6587\u5360\u6BD4/\u5B8C\u6210\u7387\uFF09+ \u6700\u8FD1 12 \u4E2A\u4EFB\u52A1\u6863\u6848 + \u9010\u6B21\u8C03\u7528\u7F13\u5B58\u706B\u82B1\u7EBF\uFF1B\u5B9E\u65F6\u589E\u957F\uFF0C\u5173\u4E86\u518D\u5F00\u4E5F\u8BFB\u6570\u3002</li>
      <li><strong>\u5E74\u9274 \xB7 Almanac</strong> \u2014 \u4FA7\u8FB9\u680F\u300C\u5E74\u9274\u300D\uFF1A\u4E5D\u5377\u535A\u7269\u9986\u7EA7\u53D9\u4E8B\uFF0C\u628A\u8FD9\u4E2A\u4EA7\u54C1\u7684\u8BBE\u8BA1\u51B3\u7B56\u6309\u7AE0\u8BB2\u8FF0\uFF0C\u6BCF\u5377\u6570\u636E\u5168\u90E8\u6765\u81EA /api/digest\u3001/api/stats \u4E0E git \u81EA\u8EAB\u3002</li>
      <li><strong>\u6A21\u677F\u5E93 \xB7 Templates</strong> \u2014 8 \u5F20\u7B56\u5C55\u8FC7\u7684\u5E38\u89C1\u4EFB\u52A1\u63D0\u793A\u8BCD\uFF08\u9879\u76EE\u626B\u63CF / \u6D4B\u8BD5\u4FEE\u590D / \u5B89\u5168\u68C0\u67E5 / README / \u7FFB\u8BD1 / \u4F9D\u8D56 / \u73B0\u4EE3\u5316 / \u5192\u70DF\uFF09\uFF0C\u4E00\u952E\u9001\u8FDB\u5BF9\u8BDD\u3002</li>
      <li><strong>\u56DE\u653E \xB7 Replay</strong> \u2014 \u4EFB\u52A1\u8BE6\u60C5\u5185\u300C\u56DE\u653E\u6574\u4E2A\u4EFB\u52A1\u300D\uFF0C\u6309\u4E8B\u4EF6\u987A\u5E8F\u64AD\u653E\uFF1A\u64AD\u653E/\u6682\u505C\u3001scrub \u8FDB\u5EA6\u6761\u30011\xD7/2\xD7/4\xD7 \u53D8\u901F\u3001tokens \u65C1\u8DEF\u7D2F\u52A0\u3002</li>
      <li><strong>\u822A\u884C\u706F \xB7 Running light</strong> \u2014 \u4FA7\u8FB9\u680F\u5E38\u9A7B\u4E00\u679A\u5C0F\u706F\uFF1A\u7F13\u5B58\u547D\u4E2D\u7387 \xD7 \u4EFB\u52A1\u6570 \xD7 \u5206\u652F @ HEAD\uFF0C\u56DB\u8272\u6E29\uFF1B\u70B9\u51FB\u76F4\u8FBE\u8D26\u672C\u3002</li>
      <li><strong>\u5C0F\u6E38\u620F \xB7 Arcade</strong> \u2014 \u4FA7\u8FB9\u680F\u300C\u5C0F\u6E38\u620F\u300D\u8FDB\u5165\u5854\u9632\u690D\u7269\u5927\u6218\u50F5\u5C38\u7CFB\u5217\uFF1Bbuild \u5728 <code>web/game.js</code>\uFF0C\u7EAF\u79BB\u7EBF\uFF0C\u79BB\u7EBF\u4E5F\u80FD\u73A9\u3002</li>
    </ul>
  `;
  }
  function enModules() {
    return `
    <p class="manual-lede">The workbench ships a whole set of always-available modules \u2014 not islands, but different views of the same evidence.</p>
    <ul class="manual-chapter-list">
      <li><strong>Ledger</strong> \u2014 \u2318L opens it: headline token count, cache-hit donut (hit/miss/write), cost with unpriced-callouts, model breakdown, status segmented bar. Every number comes from real task snapshots.</li>
      <li><strong>Pulse</strong> \u2014 three rings (hit rate / context usage / done rate) + last 12 task archive + per-call cache sparkline; live growth, re-opens with fresh numbers.</li>
      <li><strong>Almanac</strong> \u2014 sidebar entry: a museum-grade narrative in nine chapters, every figure sourced from /api/digest, /api/stats and git itself.</li>
      <li><strong>Templates</strong> \u2014 8 curated prompts for common jobs (project scan / test+fix / safety / README / translation / deps / modernize / smoke), one click into chat.</li>
      <li><strong>Replay</strong> \u2014 \u201CReplay this task\u201D from the detail view, plays event-by-event: play/pause, scrubber, 1\xD7/2\xD7/4\xD7 speed, side-mounted token counter.</li>
      <li><strong>Running light</strong> \u2014 an always-on sidebar dot: cache hit rate \xD7 tasks \xD7 branch @ HEAD, four tones; click to open the ledger.</li>
      <li><strong>Arcade</strong> \u2014 sidebar entry \u201CArcade\u201D opens a Plants-vs-Zombies-style tower defense; pure offline, playable with the network down.</li>
    </ul>
  `;
  }
  function zhKeys() {
    return `
    <div class="manual-keys">
      <div><kbd>Enter</kbd><span>\u53D1\u9001\u4EFB\u52A1</span></div>
      <div><kbd>Shift+Enter</kbd><span>\u6362\u884C</span></div>
      <div><kbd>Ctrl / \u2318 N</kbd><span>\u65B0\u4EFB\u52A1</span></div>
      <div><kbd>Ctrl / \u2318 K</kbd><span>\u547D\u4EE4\u9762\u677F</span></div>
      <div><kbd>Ctrl / \u2318 L</kbd><span>\u8D26\u672C\u603B\u89C8</span></div>
      <div><kbd>/</kbd><span>\u641C\u7D22\u4EFB\u52A1</span></div>
      <div><kbd>?</kbd><span>\u5FEB\u6377\u952E\u901F\u67E5</span></div>
      <div><kbd>Esc</kbd><span>\u5173\u95ED\u9762\u677F / \u5C0F\u6E38\u620F</span></div>
      <div><kbd>1-9</kbd><span>\u9009\u690D\u7269\uFF08\u6E38\u620F\u6253\u5F00\u65F6\uFF09</span></div>
      <div><kbd>P</kbd><span>\u6682\u505C / \u7EE7\u7EED\uFF08\u6E38\u620F\uFF09</span></div>
      <div><kbd>E</kbd><span>\u94F2\u5B50\uFF08\u6E38\u620F\uFF09</span></div>
    </div>
    <p class="manual-footnote">\u547D\u4EE4\u9762\u677F\u91CC\u8FD8\u6709\u66F4\u591A\uFF1A\u5207\u6362\u4E3B\u9898\u3001\u6253\u5F00\u5E74\u9274\u3001\u6253\u5F00\u56DE\u653E\u3001\u5BFC\u51FA\u5F53\u524D\u5BF9\u8BDD\u3001\u6062\u590D\u4EFB\u52A1\u5FEB\u7167\u7B49\u2014\u2014\u5168\u90E8\u53EF\u4EE5\u7528\u9F20\u6807\u6216\u952E\u76D8\u64CD\u4F5C\u3002</p>
  `;
  }
  function enKeys() {
    return `
    <div class="manual-keys">
      <div><kbd>Enter</kbd><span>Send the task</span></div>
      <div><kbd>Shift+Enter</kbd><span>New line</span></div>
      <div><kbd>Ctrl / \u2318 N</kbd><span>New task</span></div>
      <div><kbd>Ctrl / \u2318 K</kbd><span>Command palette</span></div>
      <div><kbd>Ctrl / \u2318 L</kbd><span>Ledger overview</span></div>
      <div><kbd>/</kbd><span>Search tasks</span></div>
      <div><kbd>?</kbd><span>Shortcut reference</span></div>
      <div><kbd>Esc</kbd><span>Close panel / game</span></div>
      <div><kbd>1-9</kbd><span>Pick seed (game open)</span></div>
      <div><kbd>P</kbd><span>Pause / resume (game)</span></div>
      <div><kbd>E</kbd><span>Shovel (game)</span></div>
    </div>
    <p class="manual-footnote">The command palette carries more: theme toggle, open the almanac, open replay, export the conversation, restore a task snapshot \u2014 every action keyboard or mouse operable.</p>
  `;
  }
  function zhArcade() {
    return `
    <p class="manual-lede">\u300C\u6E38\u620F\u5385\u300D\u662F\u5DE5\u4F5C\u53F0\u81EA\u5E26\u7684\u771F\xB7\u6E38\u620F\u2014\u2014\u4E0D\u662F demo\uFF0C\u4E0D\u662F\u5360\u4F4D\u7B26\u3002\u690D\u7269\u5BF9\u50F5\u5C38\uFF0C\u5854\u9632\u7C7B\u578B\uFF0C\u7EAF\u524D\u7AEF\uFF0C\u79BB\u7EBF\u53EF\u73A9\u3002</p>
    <div class="manual-arcade">
      <div><span class="arcade-label">\u600E\u4E48\u8FDB</span><p>\u4FA7\u8FB9\u680F\u300C\u5C0F\u6E38\u620F\u300D\u6216\u8005\u547D\u4EE4\u9762\u677F\u641C\u300CArcade/\u6E38\u620F\u5385\u300D\uFF0C\u6309 <code>Enter</code> \u5373\u73A9\u3002\u968F\u65F6\u6309 <code>Esc</code> \u8FD4\u56DE\u5DE5\u4F5C\u53F0\u3002</p></div>
      <div><span class="arcade-label">\u6838\u5FC3\u673A\u5236</span><p>\u79CD\u690D\u7269\u62B5\u5FA1\u50F5\u5C38\u8FDB\u653B\u3002\u9633\u5149\u662F\u8D44\u6E90\uFF0C\u79CD\u690D\u9700\u8981\u9633\u5149\u503C\uFF1B\u6BCF\u79CD\u690D\u7269\u6709\u653B\u51FB/\u9632\u5FA1/\u7279\u6B8A\u80FD\u529B\uFF1B\u50F5\u5C38\u4ECE\u53F3\u5411\u5DE6\u63A8\u8FDB\uFF0C\u89E6\u78B0\u5230\u4F60\u7684\u57FA\u5730\u5219\u5931\u8D25\u3002</p></div>
      <div><span class="arcade-label">\u56DB\u79CD\u6280\u80FD</span><p>Pulse\uFF0825 \u9633\u5149\uFF0C7 \u79D2\u51B7\u5374\uFF09\u3001Sun\uFF0835 \u9633\u5149\uFF0C\u7ACB\u5373\u56DE\u80FD\uFF09\u3001Rally\uFF0845 \u9633\u5149\uFF0C14 \u79D2\u51B7\u5374\uFF09\u3001Time Stop\uFF0855 \u9633\u5149\uFF0C18 \u79D2\u51B7\u5374\uFF09\u2014\u2014\u6BCF\u79CD\u6280\u80FD\u53EA\u5BF9\u7279\u5B9A\u5C40\u9762\u6709\u6548\uFF0C\u5408\u7406\u6512\u9633\u5149\u6BD4\u76F2\u76EE\u79CD\u690D\u66F4\u91CD\u8981\u3002</p></div>
      <div><span class="arcade-label">\u56FE\u9274</span><p>\u6E38\u620F\u5185\u7F6E\u690D\u7269/\u50F5\u5C38\u56FE\u9274\u2014\u2014peashooter\u3001sunflower\u3001wall-nut\u3001cherry bomb\u3001gatling pea\u3001jalapeno\u3001magnetshroom\u2026\u2026\u6BCF\u79CD\u690D\u7269\u90FD\u6709\u5C5E\u6027\u4E0E special \u63CF\u8FF0\uFF1B\u7EC8\u6781\u5173\u5361\u662F\u300C\u5DE8\u4EBA\u50F5\u5C38\u300D\u3002</p></div>
      <div><span class="arcade-label">\u6570\u636E</span><p>\u6E38\u620F\u6570\u636E\u5168\u90E8\u4FDD\u5B58\u5728\u4F60\u7684\u6D4F\u89C8\u5668\u91CC\uFF1B\u5173\u95ED\u5DE5\u4F5C\u53F0\u4E0D\u4F1A\u4E22\u5931\u8FDB\u5EA6\uFF0C\u6E05\u6D4F\u89C8\u5668\u7F13\u5B58\u4F1A\u91CD\u7F6E\u3002</p></div>
      <div><span class="arcade-label">\u7B2C\u4E00\u5C40\u600E\u4E48\u8D62\uFF08\u901A\u5173\u8DEF\u7EBF\uFF09</span><p><strong>\u2460 \u5148\u6512\u9633\u5149</strong>\u2014\u2014\u5F00\u5C40\u5148\u653E\u4E24\u6735\u5411\u65E5\u8475\uFF0C\u8FB9\u751F\u4EA7\u8FB9\u7B49\u50F5\u5C38\u9760\u8FD1\uFF1B<br/><strong>\u2461 \u518D\u8F93\u51FA</strong>\u2014\u2014\u81F3\u5C11 3 \u682A\u8C4C\u8C46\u5C04\u624B\u4F4D\u4E8E\u7B2C\u4E00\u6CE2\u8DEF\u7EBF\u7684\u53F3\u4FA7\uFF0C\u8DDF\u4E0A\u5347\u7EA7\u8282\u594F\uFF1B<br/><strong>\u2462 \u7B2C\u4E09\u6CE2\u7B51\u5899</strong>\u2014\u2014\u575A\u679C\u5899\u9876\u5728\u50F5\u5C38\u8DEF\u5F84\u6B63\u524D\u9762\uFF0C\u5176\u4F59\u8F93\u51FA\u7AD9\u540E\u9762\uFF1B<br/><strong>\u2463 \u5173\u952E\u6E05\u573A</strong>\u2014\u2014\u9633\u5149\u6512\u591F 150\uFF0C\u5728\u50F5\u5C38\u81F3\u5C11\u4E24\u4E2A\u805A\u5230\u4E00\u8D77\u65F6\u653E\u6A31\u6843\u70B8\u5F39/\u8FA3\u6912\uFF1B<br/><strong>\u2464 \u51B3\u80DC\u5DE8\u4EBA</strong>\u2014\u2014\u7B2C 10 \u6CE2\u628A Time Stop + Rally \u8FDE\u7528\uFF0C\u628A\u8DEF\u5F84\u4E24\u4FA7\u8F85\u52A9\u706B\u529B\u63A8\u6EE1\u3002</p></div>
      <div><span class="arcade-label">\u51E0\u4E2A\u7ECF\u5E38\u5FFD\u7565\u4F46\u7BA1\u7528\u7684\u952E\u4F4D</span><p><code>\u6570\u5B57\u952E 1-9</code> \u9009\u5361 \xB7 <code>P</code> \u6682\u505C/\u7EE7\u7EED \xB7 <code>E</code> \u94F2\u5B50/\u53D6\u6D88 \xB7 \u9633\u5149\u53EF\u624B\u52A8\u70B9\u51FB\u6536\u96C6\uFF08\u6E38\u620F\u5185\u4E5F\u6709\u300C\u81EA\u52A8\u62FE\u53D6\u300D\u5F00\u5173\uFF09\xB7 \u5207\u5230\u5176\u4ED6\u6807\u7B7E\u9875\u4F1A\u81EA\u52A8\u6682\u505C\uFF0C\u56DE\u5230\u6765\u7EE7\u7EED\u2014\u2014\u6218\u6597\u7528\u65F6\u53EA\u6309\u6D3B\u8DC3\u5E27\u7EDF\u8BA1\uFF0C\u4E0D\u4F1A\u5403\u51A4\u6789\u65F6\u957F\u3002</p></div>
    </div>
    <p class="manual-footnote">\u6E38\u620F\u4EE3\u7801\u5728 <code>web/game.js</code>\uFF0C\u7EAF\u524D\u7AEF\uFF0C\u6CA1\u6709\u4EFB\u4F55\u670D\u52A1\u7AEF\u4EA4\u4E92\u3002</p>
  `;
  }
  function enArcade() {
    return `
    <p class="manual-lede">The Arcade is a real game baked into the workbench \u2014 not a demo, not a placeholder. Plants versus Zombies, tower-defense genre, pure frontend, offline-playable.</p>
    <div class="manual-arcade">
      <div><span class="arcade-label">How to open</span><p>Sidebar entry \xAB Arcade \xBB or type \u201CArcade\u201D in the command palette, then <code>Enter</code>. Plays offline; <code>Esc</code> returns to the workbench.</p></div>
      <div><span class="arcade-label">Core loop</span><p>Plant units on the lawn and hold the line against zombies. Sun is the resource; planting costs sun; every plant has attack/defense/special traits; zombies push from right to left \u2014 reaching your base means failure.</p></div>
      <div><span class="arcade-label">Four skills</span><p>Pulse (25 sun, 7s cooldown), Sun (35 sun, instant refill), Rally (45 sun, 14s cooldown), Time Stop (55 sun, 18s cooldown) \u2014 each skill is situational, none is generic; hoarding sun beats mindless planting.</p></div>
      <div><span class="arcade-label">The codex</span><p>In-game plant and zombie codex \u2014 peashooter, sunflower, wall-nut, cherry bomb, gatling pea, jalapeno, magnetshroom \u2026 each with stats and a special. The final wave is the gargantuar.</p></div>
      <div><span class="arcade-label">Data</span><p>All game state lives in your browser; closing the workbench never loses progress, clearing browser cache resets it.</p></div>
      <div><span class="arcade-label">First game walkthrough</span><p><strong>\u2460 Sun first</strong> \u2014 drop two sunflowers before the first wave arrives and let them bake sun while zombies approach;<br/><strong>\u2461 Then damage</strong> \u2014 at least 3 peashooters along the threatened lanes; keep them behind the wall;<br/><strong>\u2462 Wall by wave 3</strong> \u2014 a wall-nut planted right in front of the attack lanes, absorbing hits while your shooters fire from behind;<br/><strong>\u2463 Clear the clump</strong> \u2014 once you have 150 sun, drop a cherry bomb or jalapeno when two or more zombies clump together;<br/><strong>\u2464 Close out the gargantuar</strong> \u2014 wave 10: chain Time Stop + Rally, and let your full volley land while the giant is stopped.</p></div>
      <div><span class="arcade-label">Keys you will want</span><p><code>1-9</code> pick a card \xB7 <code>P</code> pause / resume \xB7 <code>E</code> shovel / cancel \xB7 click sun drops to collect them yourself (auto-collect toggle exists in-game) \xB7 the game pauses itself when the tab loses focus \u2014 fight time only counts active frames.</p></div>
    </div>
    <p class="manual-footnote">Game code lives in <code>web/game.js</code> \u2014 pure frontend, no server round-trip whatsoever.</p>
  `;
  }
  function zhTrouble() {
    return `
    <div class="manual-trouble">
      <div><strong>\u6211\u770B\u5230\u300C\u672A\u8FDE\u63A5\u300D</strong><span>\u68C0\u67E5 <code>MINICC_API_KEY</code>/<code>MINICC_BASE_URL</code>\uFF0C\u6216\u8DD1 <code>minicc --doctor</code>\u2014\u2014\u5176\u4E2D\u4E00\u9879\u4F1A\u7ED9\u4F60\u5199\u660E\u662F\u5BC6\u94A5\u3001\u662F\u7F51\u7EDC\u8FD8\u662F\u8BC1\u4E66\u3002</span></div>
      <div><strong>\u7F13\u5B58\u547D\u4E2D\u7387\u4F4E</strong><span>\u4E0D\u662F bug\uFF0C\u662F\u524D\u7F00\u4EB2\u548C\uFF1A\u5E26\u4E0A <code>MINICC_PROMPT_CACHE_KEY</code>\uFF08\u6216\u8BA9\u81EA\u52A8\u6D3E\u751F\u751F\u6548\uFF09\u5C31\u80FD\u62FF\u5230 90%+ \u7684\u70ED\u547D\u4E2D\u7387\u3002\u663E\u793A\u6D41/\u975E\u6D41\u90FD\u6709\u7F13\u5B58\uFF1B\u6CE8\u610F\u975E\u6D41\u7EBF (chat/completions) \u5728\u90E8\u5206\u7F51\u5173\u4E0D\u4E0A\u62A5 <code>cached_tokens</code>\u3002</span></div>
      <div><strong>\u4EFB\u52A1\u5361\u4F4F</strong><span>Ctrl/\u2318+C \u5728\u7EC8\u7AEF\u91CC\uFF0C\u6216\u5DE5\u4F5C\u53F0\u300C\u91CD\u7F6E\u300D\u6309\u94AE\u3002\u6062\u590D\u673A\u5236\u4F1A\u628A\u4E0A\u4E0B\u6587\u538B\u7F29\u6210 checkpoint\uFF0C\u4EFB\u52A1\u53EF\u4EE5\u7EED\u4E0A\uFF0C\u4E0D\u4F1A\u4E22\u5931\u5DF2\u5B8C\u6210\u7684\u5199\u5165\u6587\u4EF6\u3002</span></div>
      <div><strong>\u5DE5\u4F5C\u533A\u4E0D\u53EF\u5199</strong><span>\u9ED8\u8BA4\u672C\u5730\u6C99\u7BB1\u9700\u8981\u5199\u6743\u9650\u3002\u4F60\u4E5F\u53EF\u4EE5\u9009 process \u6216 docker \u6A21\u5F0F\uFF08<code>MINICC_SANDBOX</code>\uFF09\u3002</span></div>
      <div><strong>SSE \u65AD\u5F00</strong><span>\u5173\u6389\u4EE3\u7406\u91CC\u7684 request body \u7F13\u51B2\uFF08Spring Cloud plane \u91CC\u5BF9\u5E94 <code>X-Accel-Buffering: no</code>\uFF09\u3002\u672C\u5730\u76F4\u8FDE\u4E0D\u4F1A\u9047\u5230\u3002</span></div>
      <div><strong>/api/stats \u8FD4\u56DE\u9519\u8BEF</strong><span>\u771F\u5B9E\u6D4F\u89C8\u5668\u91CC\u6253\u5F00\u63A7\u5236\u53F0\uFF1B\u5982\u679C HTTP \u72B6\u6001\u662F 503\uFF0C<code>minicc --doctor</code> \u4F1A\u544A\u8BC9\u4F60\u54EA\u4E2A\u540E\u7AEF\u6389\u7EBF\u3002</span></div>
    </div>
  `;
  }
  function enTrouble() {
    return `
    <div class="manual-trouble">
      <div><strong>I see \u201CDisconnected\u201D</strong><span>Check <code>MINICC_API_KEY</code>/<code>MINICC_BASE_URL</code>, or run <code>minicc --doctor</code> \u2014 it tells you whether it is the key, the network or the certificate.</span></div>
      <div><strong>Cache hit rate looks low</strong><span>Not a bug \u2014 prefix affinity. Set <code>MINICC_PROMPT_CACHE_KEY</code> (or let the auto-derived key ride) and you will see 90%+ warm hits. Streaming or not does not matter; note chat/completions on some gateways never reports <code>cached_tokens</code>.</span></div>
      <div><strong>Task appears stuck</strong><span>Ctrl/\u2318+C in the terminal, or the Reset button in the workbench. The recovery path compacts a checkpoint \u2014 completed writes survive, the context continues.</span></div>
      <div><strong>Workspace not writable</strong><span>The default local sandbox needs write permission. You can also pick process or docker mode (<code>MINICC_SANDBOX</code>).</span></div>
      <div><strong>SSE drops</strong><span>Disable request-body buffering in your proxy (<code>X-Accel-Buffering: no</code> on the Spring Cloud plane). Direct local connections do not hit this.</span></div>
      <div><strong>/api/stats returns an error</strong><span>Open devtools; if you see 503, <code>minicc --doctor</code> tells you which backend fell over.</span></div>
    </div>
  `;
  }
  function zhLimits() {
    return `
    <p class="manual-lede">\u8BDA\u5B9E\u7684\u8FB9\u754C\u2014\u2014\u54EA\u4E9B\u627F\u8BFA\u505A\u4E86\u3001\u54EA\u4E9B\u6CA1\u505A\uFF0C\u4EE5\u53CA\u4E3A\u4EC0\u4E48\u3002</p>
    <ul class="manual-chapter-list">
      <li><strong>\u6A21\u578B\u9009\u62E9</strong> \u2014 \u4F60\u53EF\u4EE5\u7528\u4EFB\u610F OpenAI \u517C\u5BB9\u7684\u7F51\u5173\uFF08\u5305\u62EC wkapi.pro/v1 \u4E0E\u4F60\u7684\u79C1\u6709\u4EE3\u7406\uFF09\u3002Anthropic \u4E5F\u80FD\u8D70\uFF08<code>MINICC_PROVIDER_TYPE=anthropic</code>\uFF09\uFF0C\u4F46 token \u8BA1\u4EF7\u53EA\u6709 OpenAI \u5F62\u72B6\u7684\u8D26\u672C\u3002</li>
      <li><strong>\u56FE\u50CF</strong> \u2014 \u9644\u56FE\u4E0E\u56FE\u751F\u56FE\u53EF\u4EE5\u9001\u7ED9\u6A21\u578B\uFF0C\u4F46\u4E0D\u80FD\u8BA9\u6A21\u578B\u300C\u770B\u300D\u2014\u2014\u89C6\u89C9\u80FD\u529B\u5B8C\u5168\u53D6\u51B3\u4E8E\u4F60\u9009\u7684\u6A21\u578B\u3002</li>
      <li><strong>\u7F51\u7EDC\u8BBF\u95EE</strong> \u2014 \u9ED8\u8BA4\u6C99\u7BB1\u4E0D\u76F4\u63A5\u64CD\u4F5C\u5916\u7F51\u3002\u5DE5\u5177\u5C42\u6709\u5E38\u7528 HTTP \u5BA2\u6237\u7AEF\uFF0C\u4F46\u7F51\u5173\u7EA7\u8054\u3001\u957F\u8F6E\u8BE2\u4E0E websocket \u4E0D\u4F1A\u81EA\u52A8\u751F\u6548\u3002</li>
      <li><strong>\u8FDC\u7A0B\u5DE5\u4F5C\u533A</strong> \u2014 \u672C\u5730\u4F18\u5148\u3002\u8FDC\u7A0B\u4ED3\u5E93\u73B0\u5728\u53EA\u80FD\u7528 <code>git clone</code> \u4E4B\u540E\u672C\u5730\u6253\u5F00\u3002</li>
      <li><strong>\u6E38\u620F</strong> \u2014 \u7EAF\u524D\u7AEF\uFF08<code>web/game.js</code>\uFF09\uFF0C\u6CA1\u6709\u4E91\u5B58\u6863\uFF1B\u6E05\u7F13\u5B58\u7B49\u4E8E\u91CD\u5F00\u3002</li>
      <li><strong>\u63D2\u4EF6</strong> \u2014 MCP \u5DE5\u5177\u53EF\u4EE5\u6302\u4E0A\u6765\uFF1B\u793E\u533A\u63D2\u4EF6\u5E02\u573A\u5C1A\u672A\u5B58\u5728\u3002</li>
    </ul>
  `;
  }
  function enLimits() {
    return `
    <p class="manual-lede">Honest limits \u2014 what is shipped, what is not, and why.</p>
    <ul class="manual-chapter-list">
      <li><strong>Model choice</strong> \u2014 any OpenAI-compatible gateway (including wkapi.pro/v1 and your private proxy). Anthropic works too (<code>MINICC_PROVIDER_TYPE=anthropic</code>), but token pricing is only registered for the OpenAI shape.</li>
      <li><strong>Images</strong> \u2014 you can attach images, but whether the model can see them depends on the model you pick, not on us.</li>
      <li><strong>Network access</strong> \u2014 the default sandbox does not touch the outside world. The tool layer ships a conservative HTTP client; long-polling and websockets do not auto-engage.</li>
      <li><strong>Remote workspaces</strong> \u2014 local-first. A remote repo is usable after <code>git clone</code>, then opened locally.</li>
      <li><strong>Arcade</strong> \u2014 front-end-only (<code>web/game.js</code>), no cloud save; clearing the browser cache starts over.</li>
      <li><strong>Plugins</strong> \u2014 MCP tools can be mounted; there is no community marketplace yet.</li>
    </ul>
  `;
  }
  var BODIES = {
    start: { zh: zhStart, en: enStart },
    workbench: { zh: zhWorkbench, en: enWorkbench },
    modules: { zh: zhModules, en: enModules },
    keys: { zh: zhKeys, en: enKeys },
    arcade: { zh: zhArcade, en: enArcade },
    trouble: { zh: zhTrouble, en: enTrouble },
    limits: { zh: zhLimits, en: enLimits }
  };
  function chapterMarkup2(chapter) {
    const zh2 = state.locale === "zh";
    const title = zh2 ? chapter.titleZh : chapter.title;
    return `<button class="manual-chapter" data-chapter="${escapeHtml(chapter.id)}" role="tab">
            <span class="manual-chapter-roman">${escapeHtml(zh2 ? chapter.roman : chapter.romanEn)}</span>
            <span class="manual-chapter-body"><strong>${escapeHtml(title)}</strong></span>
          </button>`;
  }
  function chapterTitle(chapter) {
    return state.locale === "zh" ? chapter.titleZh : chapter.title;
  }
  function renderChapter(id) {
    const slot = $("#manualCanvas");
    const chapter = CHAPTERS2.find((c) => c.id === id) ?? CHAPTERS2[0];
    if (!slot) return;
    const zh2 = state.locale === "zh";
    const body = (zh2 ? BODIES[chapter.id].zh : BODIES[chapter.id].en)();
    slot.innerHTML = `
    <div class="manual-canvas-inner">
      <div class="manual-kicker">${zh2 ? `\u7B2C${chapter.roman}\u7AE0` : `Chapter ${chapter.romanEn}`} \xB7 ${escapeHtml(chapter.title)}</div>
      <h1 class="manual-title">${escapeHtml(chapterTitle(chapter))}</h1>
      <div class="manual-body">${body}</div>
    </div>`;
    slot.querySelector("[data-manual-demo]")?.addEventListener("click", () => {
      closePanel();
      document.getElementById("demoFlowButton")?.click();
    });
    refreshIcons();
  }
  async function openManualPanel() {
    const zh2 = state.locale === "zh";
    const current = beginPanelRequest(t("manual.title"));
    try {
      const rail = CHAPTERS2.map(chapterMarkup2).join("");
      openPanel(t("manual.title"), `
      <div class="manual-shell">
        <nav class="manual-rail" aria-label="${escapeHtml(t("manual.title"))}">${rail}</nav>
        <div class="manual-canvas-shell"><div class="manual-canvas" id="manualCanvas"></div></div>
      </div>
    `, { wide: true, immersive: true });
      renderChapter("start");
      document.querySelectorAll(".manual-chapter").forEach((button) => {
        button.addEventListener("click", () => {
          document.querySelectorAll(".manual-chapter").forEach((b) => b.classList.toggle("active", b === button));
          renderChapter(button.getAttribute("data-chapter") || "start");
        });
      });
      document.querySelector('.manual-chapter[data-chapter="start"]')?.classList.add("active");
      refreshIcons();
    } catch (error) {
      if (!current()) return;
      openPanel(t("manual.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }

  // web/src/chat/stream.js
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
          const latest = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12e3);
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
        }
      };
      const checkLatestAfterError = () => {
        if (settled || fallbackStarted) return;
        closeSource();
        requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 8e3).then((latest) => {
          if (settled) return;
          const current = updateBoundTask(taskId, latest);
          if (isTerminalTask(current || latest)) {
            finish(current || latest);
            return;
          }
          scheduleReconnect();
        }).catch(() => scheduleReconnect());
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
        const delay = Math.min(6e3, 500 * 2 ** (reconnectAttempts - 1));
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
      () => {
        if (taskWatchers.get(taskId) === watcher) taskWatchers.delete(taskId);
      },
      () => {
        if (taskWatchers.get(taskId) === watcher) taskWatchers.delete(taskId);
      }
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
      showToast(state.locale === "zh" ? "\u5DF2\u8BF7\u6C42\u53D6\u6D88\u4EFB\u52A1" : "Cancellation requested");
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
      reader.onerror = () => reject(new Error(state.locale === "zh" ? `\u8BFB\u53D6\u5931\u8D25: ${file.name}` : `Failed to read: ${file.name}`));
      reader.onload = () => resolve(String(reader.result || ""));
      reader.readAsDataURL(file);
    });
  }
  async function addImageFiles(fileList) {
    const files = [...fileList || []].filter((file) => String(file.type || "").startsWith("image/"));
    if (!files.length) return;
    const remaining = Math.max(0, 4 - state.attachments.length);
    if (!remaining) {
      showToast(state.locale === "zh" ? "\u6700\u591A\u6DFB\u52A0 4 \u5F20\u56FE\u7247" : "Up to 4 images per task");
      return;
    }
    for (const file of files.slice(0, remaining)) {
      if (file.size > 6 * 1024 * 1024) {
        showToast(state.locale === "zh" ? `${file.name} \u8D85\u8FC7 6MB` : `${file.name} is larger than 6MB`);
        continue;
      }
      try {
        const dataUrl = await readImageFile(file);
        state.attachments.push({
          id: `image-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          name: file.name,
          mime_type: file.type || "image/png",
          size_bytes: file.size,
          data_url: dataUrl
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
    const message = input.value.trim() || (queuedAttachments.length ? state.locale === "zh" ? "\u8BF7\u5206\u6790\u6211\u4E0A\u4F20\u7684\u56FE\u7247\u3002" : "Analyze the images I uploaded." : "");
    const sessionId = state.sessionId;
    const workspacePath = state.workspacePath;
    if (!message && !queuedAttachments.length || state.submitting) return;
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
    let taskCreated = false;
    try {
      const task = await requestJson("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, model: state.model, attachments: queuedAttachments.map(({ name, mime_type, data_url }) => ({ name, mime_type, data_url })), session_id: sessionId, permission_mode: permissions.mode, allow_changes: permissions.allowChanges, allow_network: permissions.allowNetwork, reasoning_effort: state.reasoningEffort, workspace_path: workspacePath })
      });
      taskCreated = true;
      bindRunningTask(task, loadingId, sessionId);
      releaseSubmission();
      if (isCurrentScope()) state.activeTaskId = task.task_id;
      updateTaskDock(task);
      await loadTaskHistory();
      await watchTask(task.task_id);
    } catch (error) {
      finishLiveTask(loadingId);
      document.getElementById(loadingId)?.remove();
      if (isCurrentScope()) {
        addAssistantMessage({ error: error.message });
        if (!taskCreated) {
          if (input && !input.value.trim()) input.value = message;
          if (!state.attachments.length && queuedAttachments.length) state.attachments = queuedAttachments;
          renderAttachmentTray();
          const restoreHint = state.locale === "zh" ? "\uFF08\u8F93\u5165\u4E0E\u9644\u4EF6\u5DF2\u6062\u590D\u5230\u7F16\u8F91\u5668\uFF09" : " (your text and attachments were restored)";
          showToast(`${error.message}${restoreHint}`);
        } else {
          showToast(error.message);
        }
      }
      setConnection(false, "API error");
    } finally {
      releaseSubmission();
      if (isCurrentScope()) {
        if (!sessionTaskBindings(sessionId, workspacePath).length) state.activeTaskId = null;
        setBusy(isSessionBusy(state.sessionId));
      }
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
    showToast(state.locale === "zh" ? "\u5DF2\u521B\u5EFA\u65B0\u4EFB\u52A1" : "New task created");
  }
  function runDemoFlow() {
    if (isSessionBusy(state.sessionId)) return;
    const steps = state.locale === "zh" ? [
      { phase: "planning", stream: "\u6536\u5230\u4EFB\u52A1\uFF1A\u68C0\u67E5\u4E00\u4E2A\u5C0F\u529F\u80FD\u5E76\u7ED9\u51FA\u7ED3\u679C\u3002", event: { kind: "trace", code: "model_update", phase: "planning", summary: "\u6A21\u578B\u7ED9\u51FA\u4E86\u672C\u8F6E\u53EF\u516C\u5F00\u7684\u884C\u52A8\u8BF4\u660E", detail: { turn: 1, text: "\u6211\u4F1A\u5148\u8BFB\u53D6 README.md\uFF0C\u518D\u5B9A\u4F4D\u6D4B\u8BD5\u5165\u53E3\u5E76\u8FD0\u884C\u9488\u5BF9\u6027\u9A8C\u8BC1\uFF0C\u6700\u540E\u6C47\u603B\u53EF\u786E\u8BA4\u7684\u7ED3\u679C\u3002" } } },
      { phase: "tool", stream: "read_file \xB7 \u8BFB\u53D6 README.md", event: { name: "read_file", status: "ok", summary: "\u8BFB\u53D6 README.md" } },
      { phase: "tool", stream: "grep \xB7 \u641C\u7D22\u6D4B\u8BD5\u5165\u53E3", event: { name: "grep", status: "ok", summary: "\u641C\u7D22\u6D4B\u8BD5\u5165\u53E3" } },
      { phase: "planning", stream: "\u6839\u636E\u5DF2\u8BFB\u53D6\u5185\u5BB9\u8C03\u6574\u9A8C\u8BC1\u8303\u56F4", event: { kind: "trace", code: "replan", phase: "planning", summary: "\u91CD\u65B0\u89C4\u5212", detail: { turn: 1, text: "\u5DF2\u5B9A\u4F4D\u6D4B\u8BD5\u5165\u53E3\uFF0C\u4E0B\u4E00\u6B65\u53EA\u8FD0\u884C\u4E0E\u76EE\u6807\u529F\u80FD\u76F8\u5173\u7684\u6D4B\u8BD5\uFF0C\u907F\u514D\u65E0\u5173\u8017\u65F6\u3002" } } },
      { phase: "tool", stream: "bash \xB7 \u8FD0\u884C pytest -q", event: { name: "bash", status: "ok", summary: "\u8FD0\u884C pytest -q" } },
      { phase: "answering", stream: "\u6574\u7406\u9A8C\u8BC1\u7ED3\u679C\u4E0E\u5269\u4F59\u98CE\u9669", event: { kind: "trace", code: "tool_round_finished", phase: "answering", summary: "\u7ED3\u679C\u6C47\u603B\uFF1A\u5DF2\u5B8C\u6210 3 \u6B21\u5DE5\u5177\u8C03\u7528\uFF0C\u9A8C\u8BC1\u901A\u8FC7", detail: { turn: 1, tool_count: 3, tools: ["read_file", "grep", "bash"] } } },
      { phase: "answering", stream: "\u5B8C\u6210\u8BC4\u4F30\uFF1A\u4EFB\u52A1\u76EE\u6807\u5DF2\u6EE1\u8DB3", event: { kind: "trace", code: "completion_complete", phase: "answering", summary: "\u5B8C\u6210\u8BC4\u4F30\u901A\u8FC7", detail: { confidence: "\u9AD8", evidence: "\u6587\u6863\u5DF2\u8BFB\u53D6\uFF0C\u6D4B\u8BD5\u5DF2\u901A\u8FC7" } } }
    ] : [
      { phase: "planning", stream: "Task received: inspect a small feature and report back.", event: { kind: "trace", code: "model_update", phase: "planning", summary: "The model provided a public action update", detail: { turn: 1, text: "I will read README.md, locate the test entry points, run focused validation, then summarize confirmed results." } } },
      { phase: "tool", stream: "read_file \xB7 reading README.md", event: { name: "read_file", status: "ok", summary: "Reading README.md" } },
      { phase: "tool", stream: "grep \xB7 locating test entry points", event: { name: "grep", status: "ok", summary: "Locating test entry points" } },
      { phase: "planning", stream: "Refining the verification scope", event: { kind: "trace", code: "replan", phase: "planning", summary: "Re-plan", detail: { turn: 1, text: "The relevant tests are located, so I will run focused validation and avoid unrelated work." } } },
      { phase: "tool", stream: "bash \xB7 running pytest -q", event: { name: "bash", status: "ok", summary: "Running pytest -q" } },
      { phase: "answering", stream: "Summarizing verification and remaining risks", event: { kind: "trace", code: "tool_round_finished", phase: "answering", summary: "Results merged: 3 tool calls completed and validation passed", detail: { turn: 1, tool_count: 3, tools: ["read_file", "grep", "bash"] } } },
      { phase: "answering", stream: "Completion review: objective is met", event: { kind: "trace", code: "completion_complete", phase: "answering", summary: "Completion accepted", detail: { confidence: "high", evidence: "Documentation read and tests passed" } } }
    ];
    const loadingId = addLoadingMessage();
    setBusy(true);
    let index = 0;
    const tick2 = () => {
      const item = steps[index];
      if (!item) {
        finishLiveTask(loadingId);
        const loading = document.getElementById(loadingId);
        loading?.remove();
        addAssistantMessage({
          answer: state.locale === "zh" ? "\u6F14\u793A\u5B8C\u6210\uFF1A\u89C4\u5212 \u2192 \u5DE5\u5177\u8C03\u7528 \u2192 \u6D4B\u8BD5\u9A8C\u8BC1 \u2192 \u603B\u7ED3\u3002\u771F\u5B9E\u4EFB\u52A1\u4F1A\u5728\u8FD9\u91CC\u8FDE\u63A5\u672C\u5730 API \u548C\u6A21\u578B\u3002" : "Demo complete: plan \u2192 tools \u2192 tests \u2192 summary. Real tasks connect to the local API and model here.",
          events: steps.map((step) => step.event),
          turns: 1,
          tool_calls_total: 3,
          tokens_used: { total_tokens: 420 },
          context: { tokens: 420, limit_tokens: state.contextWindowTokens }
        });
        setBusy(false);
        return;
      }
      updateLiveTask(loadingId, { status: "running", phase: item.phase, stream_text: item.stream, events: steps.slice(0, index + 1).map((step) => step.event) });
      index += 1;
      window.setTimeout(tick2, 850);
    };
    tick2();
  }
  async function loadWorkspace() {
    const version = ++runtime.workspaceVersion;
    try {
      const info = await requestJson("/api/workspace", {}, 1e4);
      if (version !== runtime.workspaceVersion) return false;
      const previousPath = state.workspacePath;
      if (previousPath && info.path && previousPath !== info.path) persistSessionView();
      state.workspaceInfo = info;
      state.workspacePath = info.path || state.workspacePath;
      state.contextWindowTokens = Number(info.context_window_tokens || state.contextWindowTokens || 3e5);
      if (!localStorage.getItem("minicc-model") && info.model) state.model = String(info.model);
      void loadModelCatalog({ quiet: true });
      if (!localStorage.getItem("minicc-reasoning") && REASONING_EFFORTS.includes(info.reasoning_effort)) state.reasoningEffort = info.reasoning_effort;
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
      const historyReady = loadTaskHistory();
      void loadChanges();
      refreshFileTree();
      void (async () => {
        try {
          const workspacePath = state.workspacePath;
          const loadedTasks = await historyReady;
          if (version !== runtime.workspaceVersion || workspacePath !== state.workspacePath) return;
          const tasks = Array.isArray(loadedTasks) ? loadedTasks : [];
          const activeTasks = tasks.filter((item) => ACTIVE_TASK_STATUSES.has(item.status));
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
        }
      })();
      return true;
    } catch {
      if (version !== runtime.workspaceVersion) return false;
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
  function countLabel(value, compact = false) {
    if (!Number.isFinite(value)) return t("changes.uncounted");
    return compact ? compactNumber(value) : String(value);
  }
  function changeFileRow(item) {
    const path = String(item.path || "");
    const status = String(item.status || "clean");
    const additions = countLabel(item.additions);
    const deletions = countLabel(item.deletions);
    return `<button class="file-row file-row-${escapeHtml(status)}" data-file="${escapeHtml(path)}" data-open-diff="${escapeHtml(path)}"><span class="file-type ${fileType(path)}">${escapeHtml(fileType(path).toUpperCase())}</span><span><strong>${escapeHtml(path)}</strong><small>${escapeHtml(changeStatusLabel(status))} \xB7 <span class="diff-add">+${additions}</span> <span class="diff-del">-${deletions}</span></small></span><i data-lucide="chevron-right"></i></button>`;
  }
  function renderChanges(data) {
    const files = Array.isArray(data?.files) ? data.files : [];
    const changed = new Map(files.map((item) => [String(item.path), item]));
    const paths = files.map((item) => String(item.path));
    const fileList = $("#fileList");
    if (fileList) {
      fileList.innerHTML = paths.map((path) => changeFileRow(changed.get(path) || { path, status: "clean" })).join("");
    }
    const summary = $("#changeSummary");
    if (summary) summary.innerHTML = `<span class="diff-add">+ ${countLabel(data?.additions, true)}</span><span class="diff-del">- ${countLabel(data?.deletions, true)}</span>`;
    const tabCount = $("#changeTabCount");
    if (tabCount) tabCount.textContent = String(files.length);
    const changeList = $("#changeList");
    if (changeList) {
      changeList.innerHTML = files.length ? files.map((item) => `<button class="change-item change-item-button" data-open-diff="${escapeHtml(item.path)}"><span class="change-bar ${item.status === "added" ? "added" : item.status === "deleted" ? "deleted" : "changed"}"></span><span><strong>${escapeHtml(item.path)}</strong><small>${escapeHtml(changeStatusLabel(item.status))} \xB7 <span class="diff-add">+${countLabel(item.additions)}</span> <span class="diff-del">-${countLabel(item.deletions)}</span></small></span><span class="change-time">${escapeHtml(t("changes.now"))}</span></button>`).join("") : `<div class="change-item"><span class="change-bar muted"></span><span><strong>${escapeHtml(t("changes.clean"))}</strong><small>${escapeHtml(t("changes.cleanHint"))}</small></span><span class="change-time">--</span></div>`;
    }
    refreshIcons();
  }
  async function loadChanges() {
    if (!state.workspacePath) return;
    const request = runtime.changesRequest = (runtime.changesRequest || 0) + 1;
    const path = state.workspacePath;
    const version = runtime.workspaceVersion;
    $("#changesSection")?.setAttribute("aria-busy", "true");
    try {
      const data = await requestJson("/api/changes", {}, 12e3);
      if (path !== state.workspacePath || version !== runtime.workspaceVersion || request !== runtime.changesRequest) return;
      state.changes = data;
      renderChanges(data);
    } catch {
      if (path !== state.workspacePath || version !== runtime.workspaceVersion || request !== runtime.changesRequest) return;
      $("#changeList").innerHTML = `<div class="file-tree-status">${escapeHtml(state.locale === "zh" ? "\u6682\u65F6\u65E0\u6CD5\u8BFB\u53D6\u53D8\u66F4\u3002\u53EF\u5728\u66F4\u591A\u9009\u9879\u4E2D\u5237\u65B0\u5DE5\u4F5C\u533A\u3002" : "Changes are unavailable. Refresh the workspace from More options.")}</div>`;
    } finally {
      if (path === state.workspacePath && version === runtime.workspaceVersion && request === runtime.changesRequest) $("#changesSection")?.setAttribute("aria-busy", "false");
    }
  }
  function openPanel(title, body, options = {}) {
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
      expand.title = state.locale === "zh" ? "\u5C55\u5F00\u5168\u5C4F" : "Expand fullscreen";
      expand.setAttribute("aria-label", state.locale === "zh" ? "\u5C55\u5F00\u5168\u5C4F" : "Expand fullscreen");
      expand.innerHTML = icon("maximize-2");
    }
    modal.classList.add("show");
    modal.setAttribute("aria-hidden", "false");
    refreshIcons();
    activateDialog(modal, { onEscape: closePanel });
  }
  function beginPanelRequest(title) {
    openPanel(title, `<div class="empty-panel" role="status">${escapeHtml(state.locale === "zh" ? "\u6B63\u5728\u52A0\u8F7D\u2026" : "Loading\u2026")}</div>`);
    const version = runtime.panelVersion;
    return () => version === runtime.panelVersion && $("#panelModal").classList.contains("show");
  }
  function closePanel() {
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
  function togglePanelFullscreen() {
    const modal = $("#panelModal");
    const fullscreen = modal.classList.toggle("fullscreen");
    const button = $("#panelExpand");
    if (!button) return;
    button.title = fullscreen ? state.locale === "zh" ? "\u9000\u51FA\u5168\u5C4F" : "Collapse fullscreen" : state.locale === "zh" ? "\u5C55\u5F00\u5168\u5C4F" : "Expand fullscreen";
    button.setAttribute("aria-label", button.title);
    button.innerHTML = icon(fullscreen ? "minimize-2" : "maximize-2");
    refreshIcons();
  }
  function taskRow(task) {
    const statusClass = task.status === "completed" ? "success" : task.status === "failed" ? "error" : ["cancelled", "interrupted"].includes(task.status) ? "cancelled" : task.status === "queued" ? "queued" : "running";
    const cancel = ACTIVE_TASK_STATUSES.has(task.status) ? `<button class="panel-icon-action" data-cancel-task="${escapeHtml(task.task_id)}" title="${t("cancel")}">${icon("square")}</button>` : "";
    const resume = RESUMABLE_TASK_PHASES.has(task.status) ? `<button class="panel-icon-action" data-resume-task="${escapeHtml(task.task_id)}" title="${t("tasks.resume")}">${icon("rotate-ccw")}</button>` : "";
    const phase = phaseLabel(task);
    const streamSize = Number(task.stream_length || String(task.stream_text || "").length);
    const detail = `${phase} \xB7 ${formatDuration(taskDuration(task))} \xB7 ${streamSize} chars \xB7 ${taskMetrics(task)}`;
    const children = task.child_task_ids?.length ? ` \xB7 ${task.child_task_ids.length} ${t("tasks.children")}` : "";
    const workspace = task.workspace_path ? task.workspace_path.split(/[\\/]/).filter(Boolean).pop() : "workspace";
    const details = `<button class="panel-icon-action" data-open-detail="${escapeHtml(task.task_id)}" title="${escapeHtml(t("tasks.detail"))}" aria-label="${escapeHtml(t("tasks.detail"))}">${icon("maximize-2")}</button>`;
    const restore = task.task_id ? `<button class="panel-icon-action" data-restore-task="${escapeHtml(task.task_id)}" title="${escapeHtml(t("restore.action"))}" aria-label="${escapeHtml(t("restore.action"))}">${icon("rotate-ccw")}</button>` : "";
    return `<div class="task-row" data-open-task="${escapeHtml(task.task_id)}" tabindex="0"><span class="task-state ${statusClass}"></span><div><strong>${escapeHtml(task.task_kind === "batch" ? `${task.task_id} \xB7 ${t("tasks.children")}` : task.task_id)}</strong><small>${escapeHtml(workspace)} \xB7 ${escapeHtml(detail)}${children}</small></div><div class="task-row-actions">${details}${restore}${resume}${cancel}</div></div>`;
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
      const mergedHistory = historyItems.some((item) => item.task_id === task.task_id) ? historyItems.map((item) => item.task_id === task.task_id ? task : item) : [task, ...historyItems];
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
      showToast(state.locale === "zh" ? "\u5DF2\u6253\u5F00\u4EFB\u52A1\u4F1A\u8BDD" : "Task session opened");
    } catch (error) {
      showToast(error.message);
    }
  }
  async function openTaskDetail(taskId) {
    const current = beginPanelRequest(t("tasks.open"));
    try {
      const task = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
      if (!current()) return;
      const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
      const execution = executionTrailMarkup(events, task.events || []);
      const children = Array.isArray(task.child_task_ids) && task.child_task_ids.length ? `<div class="task-detail-children">${task.child_task_ids.map((child) => `<button class="panel-session" data-open-task="${escapeHtml(child)}">${escapeHtml(child)}</button>`).join("")}</div>` : "";
      const resume = RESUMABLE_TASK_PHASES.has(task.status) ? `<button class="panel-primary" data-resume-task="${escapeHtml(task.task_id)}">${t("tasks.resume")}</button>` : "";
      const restore = `<button class="panel-secondary" data-restore-task="${escapeHtml(task.task_id)}">${icon("rotate-ccw")} ${escapeHtml(t("restore.action"))}</button>`;
      const attachments = attachmentMarkup(task.attachments || []);
      openPanel(`${t("tasks.open")} \xB7 ${task.task_id}`, `<div class="task-detail"><div class="task-detail-status"><span class="task-state ${task.status === "completed" ? "success" : RESUMABLE_TASK_PHASES.has(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div><div class="task-detail-actions task-detail-top-actions"><button class="panel-secondary" data-open-task="${escapeHtml(task.task_id)}">${icon("arrow-up-right")} ${escapeHtml(t("tasks.openSession"))}</button><button class="panel-secondary" data-replay-task="${escapeHtml(task.task_id)}">${icon("play")} ${escapeHtml(t("replay.action"))}</button>${restore}</div>${runtimeMetricsMarkup(task)}<div class="panel-section-title">${t("workspace.current")}</div><code class="task-detail-path">${escapeHtml(task.workspace_path || "")}</code><div class="panel-section-title">Prompt</div><div class="task-detail-prompt">${formatText(task.prompt || task.preview || "")}</div>${attachments ? `<div class="panel-section-title">Images</div>${attachments}` : ""}<div class="panel-section-title">Response</div><div class="task-detail-answer">${formatText(task.answer || task.stream_text || task.error || "")}</div>${execution ? `<div class="panel-section-title">Tools & stage trace</div>${execution}` : ""}${children}${resume ? `<div class="task-detail-actions">${resume}</div>` : ""}</div>`, { immersive: true });
    } catch (error) {
      if (!current()) return;
      openPanel(t("tasks.open"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }
  function openBatchPanel() {
    const taskFields = [1, 2, 3].map((index) => `<label class="batch-field"><span>${escapeHtml(t("batch.task"))} ${index}</span><textarea name="task" rows="3" placeholder="${escapeHtml(state.locale === "zh" ? "\u4F8B\u5982\uFF1A\u68C0\u67E5\u540E\u7AEF\u6D4B\u8BD5\u5E76\u603B\u7ED3\u98CE\u9669" : "For example: inspect backend tests and summarize risks")}"></textarea></label>`).join("");
    openPanel(t("panel.batch"), `<form class="batch-form" id="batchForm"><div class="batch-heading"><span class="eyebrow">${escapeHtml(t("batch.title"))}</span><h3>${escapeHtml(t("batch.title"))}</h3><p>${escapeHtml(t("batch.subtitle"))}</p></div><div class="batch-fields">${taskFields}</div><label class="batch-field"><span>${escapeHtml(t("batch.context"))}</span><textarea name="shared_context" rows="3" placeholder="${escapeHtml(t("batch.note"))}"></textarea></label><div class="task-detail-actions"><button class="panel-primary" type="submit">${icon("play")} ${escapeHtml(t("batch.run"))}</button></div></form>`, { wide: true });
  }
  async function openLedgerPanel() {
    const current = beginPanelRequest(t("ledger.overview"));
    try {
      const data = await requestJson("/api/metrics");
      if (!current()) return;
      const usage = data && typeof data.usage === "object" && data.usage || {};
      const llm = data && typeof data.llm_cache === "object" && data.llm_cache || {};
      const models = data && typeof data.by_model === "object" && data.by_model || {};
      const statusMap = data && typeof data.tasks_by_status === "object" && data.tasks_by_status || {};
      const priced = Number(data?.priced_tasks || 0);
      const unpriced = Number(data?.unpriced_tasks || 0);
      const cost = typeof data?.cost_usd === "number" ? data.cost_usd : NaN;
      const hit = Number(usage.prompt_cache_hit_tokens || 0);
      const miss = Number(usage.prompt_cache_miss_tokens || 0);
      const writes = Number(usage.prompt_cache_write_tokens || 0);
      const totalTokens = Number(usage.total_tokens || 0);
      const hitRatePct = hit + miss > 0 ? Math.round(hit / (hit + miss) * 100) : null;
      const donutData = {
        tokens_used: { prompt_cache_hit_tokens: hit, prompt_cache_miss_tokens: miss },
        metrics: { cache_status: llm.cache_status || "unreported" }
      };
      const statusRows = [
        ["completed", t("phase.completed"), "var(--mint)"],
        ["failed", t("phase.failed"), "var(--rose)"],
        ["interrupted", t("phase.interrupted"), "var(--amber)"],
        ["cancelled", t("phase.cancelled"), "var(--muted)"]
      ].filter(([key]) => Number(statusMap[key] || 0) > 0);
      const maxStatus = Math.max(1, ...statusRows.map(([key]) => Number(statusMap[key] || 0)));
      const modelRows = Object.entries(models).sort((a, b) => Number(b[1]?.tasks || 0) - Number(a[1]?.tasks || 0)).map(([name, bucket]) => {
        const bt = bucket?.tokens || {};
        const tokens = Number(bt.total_tokens || 0);
        const costStr = typeof bucket?.cost_usd === "number" ? `$${Number(bucket.cost_usd).toFixed(4)}` : '<span class="led-unpriced">\u2014</span>';
        return `<tr><td><code>${escapeHtml(name)}</code></td><td class="led-num">${compactNumber(tokens)}</td><td class="led-num">${compactNumber(Number(bt.prompt_cache_hit_tokens || 0))} / ${compactNumber(Number(bt.prompt_cache_miss_tokens || 0))}</td><td class="led-num">${escapeHtml(String(bucket.tasks || 0))}</td><td class="led-num">${costStr}</td></tr>`;
      }).join("");
      const hasModels = Object.keys(models).length > 0;
      const totalRow = `<tr class="led-total-row"><td>${t("ledger.overview")}</td><td class="led-num">${compactNumber(totalTokens)}</td><td class="led-num">${compactNumber(hit)} / ${compactNumber(miss)}</td><td class="led-num"></td><td class="led-num">${Number.isFinite(cost) ? `$${cost.toFixed(4)}` : `<span class="led-unpriced">${t("ledger.unpriced")}</span>`}</td></tr>`;
      const redisLabel = data?.redis_cache?.live_backend ? t("ledger.redisLive") : t("ledger.redisLocal");
      const redisClass = data?.redis_cache?.live_backend ? "led-redis-live" : "led-redis-local";
      const body = `<div class="ledger-view">

      <div class="led-hero"><div class="led-hero-number">${compactNumber(totalTokens)}</div><div class="led-hero-label">${t("ledger.tokens")}</div></div>

      <div class="led-stat-row">

        <div class="led-stat"><div class="led-stat-label">${t("ledger.hitRate")}</div><div class="led-stat-donut">${cacheDonut(donutData, 52)}</div><div class="led-stat-sub">${hitRatePct !== null ? `${hitRatePct}%` : t("tasks.cacheUnreported")} \xB7 ${t("ledger.cacheHits")} ${compactNumber(hit)} \xB7 ${t("ledger.cacheMiss")} ${compactNumber(miss)} \xB7 ${t("ledger.cacheWrite")} ${compactNumber(writes)}</div></div>

        <div class="led-stat"><div class="led-stat-label">${t("ledger.cost")}</div><div class="led-stat-big">${Number.isFinite(cost) ? `$${cost.toFixed(4)}` : '<span class="led-unpriced">$\u2014</span>'}</div><div class="led-stat-sub">${unpriced}/${priced + unpriced} ${state.locale === "zh" ? "\u4E2A\u4EFB\u52A1\u5B9A\u4EF7" : "tasks priced"} \xB7 ${llm.cache_status || ""}</div></div>

        <div class="led-stat"><div class="led-stat-label">${t("ledger.redisTitle")}</div><div class="led-stat-big ${redisClass}">${redisLabel}</div><div class="led-stat-sub">${data?.redis_cache ? `gets ${data.redis_cache.gets || 0} \xB7 sets ${data.redis_cache.sets || 0} \xB7 local ${data.redis_cache.local_units || 0}/${data.redis_cache.local_capacity || 0}` : "\u2014"}</div></div>

      </div>

      ${statusRows.length ? `<div class="led-section"><div class="panel-section-title">${t("ledger.status")}</div><div class="led-status-bar">${statusRows.map(([key, label2, color]) => `<div class="led-status-seg" style="flex:${Number(statusMap[key] || 0)} 1 0;background:${color};" title="${escapeHtml(label2)}: ${escapeHtml(String(statusMap[key]))}">${escapeHtml(String(statusMap[key]))}</div>`).join("")}</div><div class="led-status-legend">${statusRows.map(([key, label2]) => `<span class="led-status-dot" style="--status-dot:${statusRows.find((r) => r[0] === key)[2]}"></span>${escapeHtml(label2)} <strong>${escapeHtml(String(statusMap[key]))}</strong>`).join("")}</div></div>` : ""}

      ${hasModels ? `<div class="led-section"><div class="panel-section-title">${t("ledger.models")}</div><table class="led-table"><thead><tr><th>model</th><th class="led-num">tokens</th><th class="led-num">hit/miss</th><th class="led-num">${t("ledger.tasks")}</th><th class="led-num">$</th></tr></thead><tbody>${modelRows}${totalRow}</tbody></table></div>` : `<div class="empty-panel">${t("ledger.noMetrics")}</div>`}

    </div>`;
      openPanel(t("ledger.overview"), body, { wide: true });
    } catch (error) {
      if (!current()) return;
      openPanel(t("ledger.overview"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }
  async function openPulseStage() {
    const modal = $("#pulseStage");
    if (!modal) return;
    modal.setAttribute("aria-hidden", "false");
    const close = $("#pulseStageClose");
    if (close) close.onclick = () => {
      modal.setAttribute("aria-hidden", "true");
    };
    const fetchAll = async () => {
      try {
        const [metrics, tasksData, stats] = await Promise.all([
          requestJson("/api/metrics"),
          requestJson("/api/tasks?limit=12").catch(() => ({ tasks: [] })),
          requestJson("/api/stats").catch(() => null)
        ]);
        const usage = metrics && typeof metrics.usage === "object" && metrics.usage || {};
        const llm = metrics && typeof metrics.llm_cache === "object" && metrics.llm_cache || {};
        const models = metrics && typeof metrics.by_model === "object" && metrics.by_model || {};
        const statusMap = metrics && typeof metrics.tasks_by_status === "object" && metrics.tasks_by_status || {};
        const tasks = Array.isArray(tasksData?.tasks) ? tasksData.tasks : [];
        const workspacePath = state.workspacePath || String(metrics?.workspace_path || "");
        const memoryCount = Number(stats?.sessions?.count ?? stats?.llm_cache?.tasks_with_usage ?? 0);
        const auditLines = Number(stats?.audit?.lines ?? 0);
        const messages = Number(stats?.sessions?.messages ?? 0);
        const modelTokens = Object.values(models).reduce((acc, b) => acc + Number(b?.tokens?.total_tokens || 0), 0);
        const totalTokens = Number(usage.total_tokens || modelTokens || 0);
        const hit = Number(usage.prompt_cache_hit_tokens || 0);
        const miss = Number(usage.prompt_cache_miss_tokens || 0);
        const hitRate = hit + miss > 0 ? Math.round(hit / (hit + miss) * 100) : null;
        const completed = Number(statusMap.completed || 0);
        const interrupted = Number(statusMap.interrupted || 0);
        const failed = Number(statusMap.failed || 0);
        const cancelled = Number(statusMap.cancelled || 0);
        const totalTasks = completed + interrupted + failed + cancelled;
        const doneRate = totalTasks > 0 ? Math.round(completed / totalTasks * 100) : null;
        const topModel = Object.entries(models).sort((a, b) => Number(b[1]?.tasks || 0) - Number(a[1]?.tasks || 0))[0]?.[0] || "\u2014";
        const latestCtx = tasks.length ? tasks[0] : null;
        const ctxLimit = Number(latestCtx?.context?.limit_tokens || state.contextWindowTokens || 3e5);
        const ctxTokens = Number(latestCtx?.context?.tokens || 0);
        const ctxRate = ctxLimit > 0 ? Math.min(100, Math.round(ctxTokens / ctxLimit * 100)) : null;
        $("#pulseIdentityPath").textContent = workspacePath || "\u2014";
        $("#pulseModel").textContent = topModel;
        $("#pulseGateway").textContent = String(usedModelConfig()?.gateway || "wkapi.pro");
        $("#pulseEffort").textContent = String(state.reasoningEffort || "high");
        $("#pulseMemory").textContent = String(memoryCount || 0);
        $("#pulseAudit").textContent = String(auditLines || 0);
        $("#pulseTurns").textContent = String(messages || 0);
        $("#pulseCost").textContent = typeof metrics?.cost_usd === "number" && Number.isFinite(metrics.cost_usd) ? `$${metrics.cost_usd.toFixed(4)}` : state.locale === "zh" ? "\u672A\u8BA1\u4EF7" : "unpriced";
        const setRing = (selector, pct, caption) => {
          const arc = document.querySelector(`.${selector}`);
          const valueEl = document.querySelector(`#${selector === "pulse-ring-hit" ? "pulseHitValue" : selector === "pulse-ring-ctx" ? "pulseCtxValue" : "pulseDoneValue"}`);
          const captionEl = document.querySelector(`#${selector === "pulse-ring-hit" ? "pulseHitCaption" : selector === "pulse-ring-ctx" ? "pulseCtxCaption" : "pulseDoneCaption"}`);
          const circumference = 2 * Math.PI * 50;
          const offset = circumference - Math.max(0, Math.min(100, Number(pct || 0))) / 100 * circumference;
          if (arc) arc.setAttribute("stroke-dashoffset", String(offset));
          if (valueEl) valueEl.textContent = pct == null ? "\u2014" : `${pct}%`;
          if (captionEl) captionEl.textContent = caption;
        };
        setRing("pulse-ring-hit", hitRate, hitRate == null ? state.locale === "zh" ? "\u672A\u8FD4\u56DE\u7F13\u5B58\u8BA1\u6570" : "no cache counters yet" : `${compactNumber(hit)} / ${compactNumber(hit + miss)} ${state.locale === "zh" ? "\u547D\u4E2D" : "hits"}`);
        setRing("pulse-ring-ctx", ctxRate, ctxRate == null ? "\u2014" : `${compactNumber(ctxTokens)} / ${compactNumber(ctxLimit)} ${state.locale === "zh" ? "tokens" : "tokens"}`);
        setRing("pulse-ring-done", doneRate, `${completed} ${state.locale === "zh" ? "\u5DF2\u5B8C\u6210" : "done"} \xB7 ${failed} ${state.locale === "zh" ? "\u5931\u8D25" : "failed"} \xB7 ${cancelled + interrupted} ${state.locale === "zh" ? "\u4E2D\u65AD/\u53D6\u6D88" : "interrupted"}`);
        const timeline = $("#pulseTimeline");
        const timelineCount = $("#pulseTimelineCount");
        if (timeline) {
          const series = taskTimelineSeries(tasks, 12);
          timeline.innerHTML = taskTimelineMarkup(series, {
            empty: t("pulse.timelineEmpty"),
            old: t("pulse.timelineOld"),
            new: t("pulse.timelineNew"),
            tokensUnit: "tokens",
            noTokens: state.locale === "zh" ? "\u672A\u8BB0\u5F55 tokens" : "no tokens recorded"
          });
        }
        if (timelineCount) timelineCount.textContent = String(tasks.length);
        const archive = $("#pulseArchiveList");
        const countEl = $("#pulseArchiveCount");
        if (archive) {
          if (!tasks.length) {
            archive.innerHTML = `<div class="pulse-archive-empty">${escapeHtml(state.locale === "zh" ? "\u8FD8\u6CA1\u6709\u4EFB\u52A1\u8BB0\u5F55" : "No tasks yet")}</div>`;
          } else {
            archive.innerHTML = tasks.map((task) => {
              const tokens = Number(task?.tokens_used?.total_tokens || task?.metrics?.budget?.tokens || 0);
              const st = String(task?.status || "");
              const id = String(task?.task_id || "");
              return `<button type="button" class="pulse-archive-row" data-open-task="${escapeHtml(id)}" data-status="${escapeHtml(st)}"><span class="pulse-archive-status"></span><strong>${escapeHtml(String(task?.preview || task?.prompt || id).slice(0, 72))}</strong><small>${escapeHtml(st)}</small><span class="pulse-archive-tokens">${compactNumber(tokens)}</span></button>`;
            }).join("");
          }
        }
        if (countEl) countEl.textContent = String(tasks.length);
        const pill = $("#pulseStatusPill");
        if (pill) {
          pill.classList.remove("offline");
          $("#pulseStatusLabel").textContent = state.locale === "zh" ? "\u5DF2\u8FDE\u63A5" : "connected";
        }
      } catch (error) {
        const pill = $("#pulseStatusPill");
        if (pill) {
          pill.classList.add("offline");
          $("#pulseStatusLabel").textContent = state.locale === "zh" ? "\u672A\u8FDE\u63A5" : "offline";
        }
        const archive = $("#pulseArchiveList");
        if (archive) archive.innerHTML = `<div class="pulse-archive-empty">${escapeHtml(state.locale === "zh" ? "\u8BFB\u53D6\u5931\u8D25\uFF1A" : "Failed to load: ")}${escapeHtml(error.message)}</div>`;
      }
    };
    fetchAll();
  }
  function usedModelConfig() {
    if (typeof state.modelCatalog === "object" && state.modelCatalog) {
      return state.modelCatalog;
    }
    return { gateway: "wkapi.pro" };
  }
  function openTemplatesPanel() {
    const zh2 = state.locale === "zh";
    const cards = [
      {
        icon: "file-search-2",
        title: zh2 ? "\u9879\u76EE\u626B\u63CF" : "Project Scan",
        subtitle: zh2 ? "\u8BFB\u5165\u53E3\u6587\u6863\u3001\u67B6\u6784\u4E0E\u547D\u4EE4\uFF0C\u8F93\u51FA\u4E00\u9875\u9879\u76EE\u6982\u89C8" : "Read entrypoint docs, architecture, and commands for a one-page overview",
        prompt: zh2 ? "\u8BF7\u9605\u8BFB\u5F53\u524D\u5DE5\u4F5C\u533A\u7684 README\u3001package.json \u6216 pyproject.toml\u3001AGENTS.md / CLAUDE.md / MINICC.md \u4EE5\u53CA\u4E3B\u8981\u7684\u6784\u5EFA\u811A\u672C\uFF0C\u7136\u540E\u8F93\u51FA\u4E00\u9875\u9879\u76EE\u6982\u89C8\uFF1A\u8FD9\u4E2A\u4ED3\u5E93\u505A\u4EC0\u4E48\u3001\u6280\u672F\u6808\u662F\u4EC0\u4E48\u3001\u600E\u4E48\u6784\u5EFA\u3001\u600E\u4E48\u6D4B\u8BD5\u3001\u4ECE\u54EA\u91CC\u5F00\u59CB\u8BFB\u8D77\u3002\u4E0D\u8981\u7528\u5DE5\u5177\u4FEE\u6539\u4EFB\u4F55\u6587\u4EF6\u3002" : "Read the workspace's README, package.json or pyproject.toml, AGENTS.md / CLAUDE.md / MINICC.md, and the main build scripts. Then output a one-page project overview: what this repo does, its tech stack, how to build, how to test, and where to start reading. Do not edit any files."
      },
      {
        icon: "shield-check",
        title: zh2 ? "\u8DD1\u6D4B\u8BD5\u5E76\u4FEE\u597D" : "Run tests & fix",
        subtitle: zh2 ? "\u81EA\u52A8\u53D1\u73B0\u6D4B\u8BD5\u547D\u4EE4\uFF0C\u8FD0\u884C\u5E76\u4FEE\u590D\u5931\u8D25\uFF0C\u9A8C\u8BC1\u901A\u8FC7" : "Discover the test runner, run it, fix failures, verify green",
        prompt: zh2 ? "\u8BF7\u53D1\u73B0\u5F53\u524D\u4ED3\u5E93\u7684\u6D4B\u8BD5\u547D\u4EE4\uFF08\u53C2\u8003 package.json / pyproject.toml / Makefile \u4E2D\u7684 test \u6BB5\uFF0C\u4E0D\u8981\u4FEE\u6539\u5B83\u4EEC\uFF09\uFF0C\u8FD0\u884C\u6D4B\u8BD5\uFF0C\u5206\u6790\u5931\u8D25\u539F\u56E0\uFF0C\u9010\u4E00\u4FEE\u590D\u76F4\u5230\u5168\u90E8\u901A\u8FC7\u3002\u5982\u679C\u53D1\u73B0\u6D4B\u8BD5\u672C\u8EAB\u6709\u95EE\u9898\uFF0C\u4E5F\u4FEE\u597D\u6D4B\u8BD5\uFF1B\u4E0D\u8981\u8DF3\u8FC7\u4EFB\u4F55\u65AD\u8A00\u3002\u6700\u540E\u6C47\u62A5\u672C\u6B21\u6539\u52A8\u6D89\u53CA\u7684\u6BCF\u4E2A\u6587\u4EF6\u3001\u6BCF\u4E2A\u5931\u8D25\u4EE5\u53CA\u4FEE\u590D\u65B9\u5F0F\u3002" : "Discover the test command for this repo (look at the test section of package.json / pyproject.toml / Makefile; do not edit those files). Run the tests, analyze the failures, fix them one by one until green. If a test itself is wrong, fix the test too; don't skip any assertion. Report each file involved, each failure, and how you fixed it."
      },
      {
        icon: "git-compare",
        title: zh2 ? "\u5B89\u5168\u5BA1\u67E5\u53D8\u66F4" : "Review Diff Safely",
        subtitle: zh2 ? "\u5BA1\u67E5\u5F53\u524D\u672A\u63D0\u4EA4\u6539\u52A8\uFF1A\u56DE\u5F52\u98CE\u9669\u3001\u6F0F\u6539\u3001\u8FB9\u754C\u6761\u4EF6" : "Review uncommitted changes: regression risk, missing edits, edge cases",
        prompt: zh2 ? "\u8BF7\u4F7F\u7528 git diff \u5BA1\u67E5\u5F53\u524D\u672A\u63D0\u4EA4\u7684\u6539\u52A8\uFF0C\u91CD\u70B9\u5173\u6CE8\uFF1A\u2460 \u662F\u5426\u7834\u574F\u73B0\u6709 API / \u7C7B\u578B\u7B7E\u540D / \u5E8F\u5217\u5316\u683C\u5F0F\uFF1B\u2461 \u662F\u5426\u9057\u6F0F\u4E86\u5E94\u8BE5\u540C\u6B65\u66F4\u65B0\u7684\u8C03\u7528\u5904\uFF1B\u2462 \u8FB9\u754C\u6761\u4EF6\uFF08\u7A7A\u503C\u3001\u8D1F\u6570\u3001\u8D85\u5927\u8F93\u5165\uFF09\u662F\u5426\u8986\u76D6\uFF1B\u2463 \u6D4B\u8BD5\u662F\u5426\u540C\u6B65\u52A0\u4E86\u3002\u8F93\u51FA\u5BA1\u67E5\u7ED3\u8BBA\uFF1A\u901A\u8FC7 / \u9700\u4FEE\u6539\uFF08\u9644\u6587\u4EF6+\u884C\u53F7\uFF09/ \u98CE\u9669\u63A5\u53D7\u3002" : "Review the current uncommitted diff with git diff. Focus on: (1) whether it breaks existing APIs, type signatures, or serialization formats; (2) call sites that should be updated but weren't; (3) boundary conditions (null, negative, very large input); (4) tests that were added/updated. Output a verdict: approve / needs changes (with file+line) / risk-accepted."
      },
      {
        icon: "book-open",
        title: zh2 ? "\u751F\u6210 README" : "Write README",
        subtitle: zh2 ? "\u6309\u4ED3\u5E93\u7ED3\u6784\u5199\u51FA\u6E05\u6670\u7684\u65B0 READMOR" : "Write a clear README from this repo's structure",
        prompt: zh2 ? "\u8BF7\u6839\u636E\u5F53\u524D\u4ED3\u5E93\u7684\u76EE\u5F55\u7ED3\u6784\u3001\u6E90\u7801\u6CE8\u91CA\u3001\u6784\u5EFA/\u6D4B\u8BD5\u5165\u53E3\u548C\u4F9D\u8D56\u6E05\u5355\uFF0C\u751F\u6210\u4E00\u4EFD\u9762\u5411\u65B0\u8D21\u732E\u8005\u7684 README\uFF1A\u2460 \u8FD9\u4E2A\u9879\u76EE\u662F\u4EC0\u4E48\u3001\u89E3\u51B3\u4EC0\u4E48\u95EE\u9898\uFF1B\u2461 \u73AF\u5883\u8981\u6C42\uFF1B\u2462 \u5FEB\u901F\u5F00\u59CB\uFF08\u5B89\u88C5\u3001\u6784\u5EFA\u3001\u6D4B\u8BD5\uFF09\uFF1B\u2463 \u9879\u76EE\u7ED3\u6784\u5730\u56FE\uFF08\u76EE\u5F55 \u2192 \u7528\u9014 + \u5173\u952E\u6587\u4EF6\uFF09\uFF1B\u2464 \u5E38\u89C1\u4EFB\u52A1\uFF08\u793A\u4F8B\uFF1A\u65B0\u589E\u529F\u80FD\u3001\u8DD1\u5355\u6D4B\uFF09\u3002\u53EA\u8BFB\u53D6\u6587\u4EF6\u3001\u4E0D\u8981\u4FEE\u6539\u4EFB\u4F55\u4E1C\u897F\u3002" : "Based on the repo's directory structure, source-code docstrings, build/test entry points, and dependency manifest, generate a README for new contributors: (1) what this project is and what problem it solves, (2) prerequisites, (3) quickstart (install, build, test), (4) structure map (directory \u2192 purpose + key files), (5) common tasks (example: add a feature, run the focused test). Read only, do not edit files."
      },
      {
        icon: "globe-2",
        title: zh2 ? "\u4E2D\u6587\u6CE8\u91CA\u82F1\u6587\u5316" : "Translate Comments EN",
        subtitle: zh2 ? "\u628A\u6E90\u7801\u4E2D\u7684\u4E2D\u6587\u6CE8\u91CA / \u6587\u6863\u5B57\u7B26\u4E32\u7FFB\u8BD1\u4E3A\u82F1\u6587" : "Translate Chinese comments / docstrings to English",
        prompt: zh2 ? "\u8BF7\u626B\u63CF\u5F53\u524D\u4ED3\u5E93\u4E2D\u6240\u6709\u6E90\u6587\u4EF6\uFF0C\u628A\u6240\u6709\u4E2D\u6587\u6CE8\u91CA\uFF08\u542B\u6587\u6863\u5B57\u7B26\u4E32\u4E0E\u884C\u5C3E\u6CE8\u91CA\uFF09\u7FFB\u8BD1\u6210\u5730\u9053\u82F1\u6587\uFF0C\u53EA\u6539\u6CE8\u91CA\u4E0D\u6539\u4EE3\u7801\u903B\u8F91\u4E0E\u5B57\u7B26\u4E32\u3002\u4E0D\u8981\u7FFB\u8BD1\u7528\u6237\u754C\u9762\u6587\u6848\uFF08\u90A3\u4E9B\u5DF2\u7ECF\u662F\u53CC\u8BED\u4E86\uFF09\u3002\u7FFB\u8BD1\u540E\u4FDD\u6301\u6587\u4EF6\u683C\u5F0F\u4E0D\u53D8\uFF0C\u5E76\u6C47\u62A5\u6539\u52A8\u7684\u6587\u4EF6\u6E05\u5355\u548C\u7FFB\u8BD1\u6761\u6570\u3002" : "Scan every source file in the workspace; translate every Chinese comment (including docstrings and end-of-line comments) into fluent English. Change only comments \u2014 never code logic or string literals. Do not translate UI strings (those are already bilingual). Preserve file formatting and report the files changed and number of comments translated."
      },
      {
        icon: "refresh-cw",
        title: zh2 ? "\u4F9D\u8D56\u5347\u7EA7\u4F53\u68C0" : "Dependency Check",
        subtitle: zh2 ? "\u5217\u51FA\u8FC7\u671F\u4F9D\u8D56\u3001\u5B89\u5168\u63D0\u9192\u3001\u5347\u7EA7\u5F71\u54CD\u8BC4\u4F30" : "List outdated deps, security notes, and upgrade impact",
        prompt: zh2 ? "\u8BF7\u68C0\u67E5\u5F53\u524D\u4ED3\u5E93\u7684\u4F9D\u8D56\u6E05\u5355\uFF0C\u5217\u51FA\uFF1A\u2460 \u8FC7\u671F\u7684\u4F9D\u8D56\uFF08\u533A\u5206 major / minor / patch\uFF09\uFF1B\u2461 \u5DF2\u77E5\u5B89\u5168\u6F0F\u6D1E\u6216\u5F03\u7528\u8B66\u544A\uFF1B\u2462 \u5EFA\u8BAE\u5347\u7EA7\u987A\u5E8F\uFF08\u54EA\u4E9B\u5148\u5347\u3001\u54EA\u4E9B\u53EF\u4EE5\u5EF6\u540E\uFF09\u3002\u4E0D\u8981\u5B9E\u9645\u4FEE\u6539\u6E05\u5355\u3002\u6700\u540E\u8F93\u51FA\u4E00\u4EFD\u300C\u4F9D\u8D56\u4F53\u68C0\u300D\u62A5\u544A\u3002" : "Check this repo's dependency manifest and report: (1) outdated dependencies, by major/minor/patch, (2) known security advisories or deprecation warnings, (3) a recommended upgrade order (which go first and which can wait). Do not modify the manifest. Output a dependency health-check report."
      },
      {
        icon: "sparkles",
        title: zh2 ? "\u4EE3\u7801\u73B0\u4EE3\u5316\u5EFA\u8BAE" : "Modernize Code",
        subtitle: zh2 ? "\u53D1\u73B0\u53EF\u4EE5\u7CBE\u7B80 / \u73B0\u4EE3\u5316\u7684\u4EE3\u7801\u7247\u6BB5" : "Find code that can be tightened or modernized",
        prompt: zh2 ? "\u8BF7\u901A\u8BFB\u5F53\u524D\u4ED3\u5E93\u7684\u6838\u5FC3\u6A21\u5757\uFF0C\u627E\u51FA\uFF081\uFF09\u91CD\u590D\u4EE3\u7801\u3001\uFF082\uFF09\u53EF\u88AB\u73B0\u4EE3\u8BED\u8A00\u7279\u6027\u53D6\u4EE3\u7684\u5199\u6CD5\uFF08\u6BD4\u5982 3 \u5143\u94FE / \u8001\u5F0F\u5B57\u7B26\u4E32\u62FC\u63A5\uFF09\u3001\uFF083\uFF09\u672A\u4F7F\u7528\u7684\u5BFC\u5165\u3001\uFF084\uFF09\u53EF\u4EE5\u63D0\u53D6\u6210\u51FD\u6570\u7684\u957F\u51FD\u6570\u4F53\u3001\uFF085\uFF09\u7C7B\u578B\u53EF\u4EE5\u66F4\u7CBE\u786E\u7684\u5730\u65B9\u3002\u5217\u51FA\u6BCF\u4E2A\u53D1\u73B0\u7684\u6587\u4EF6+\u884C\u53F7+\u7B80\u8981\u5EFA\u8BAE\u3002\u4E0D\u8981\u76F4\u63A5\u6539\u52A8\u4EE3\u7801\uFF0C\u5148\u7ED9\u6211\u8BC4\u4F30\u62A5\u544A\u3002" : "Read the core modules of this repo and find: (1) duplicated code, (2) constructs replaceable by modern language features (ternary chains, legacy string building), (3) unused imports, (4) long function bodies that can be extracted, (5) spots where types could be narrower. List each finding with file+line+brief suggestion. Do not edit code yet; give me an assessment first."
      },
      {
        icon: "list-checks",
        title: zh2 ? "\u8FD0\u884C\u5173\u952E\u8DEF\u5F84\u5192\u70DF" : "Smoke Key Path",
        subtitle: zh2 ? "\u9A8C\u8BC1\u4E3B\u6D41\u7A0B\u80FD\u8DD1\u901A\uFF1A\u7F16\u8F91 \u2192 \u4FDD\u5B58 \u2192 \u9A8C\u8BC1" : "Smoke the golden path: edit \u2192 save \u2192 verify",
        prompt: zh2 ? "\u8BF7\u4E0D\u8981\u6539\u4EFB\u4F55\u6587\u4EF6\u3002\u5E2E\u6211\u6267\u884C\u300C\u53EF\u7528\u6027\u5192\u70DF\u68C0\u67E5\u300D\uFF1A\u6309\u987A\u5E8F\u786E\u8BA4 (a) \u4ED3\u5E93\u7ED3\u6784\u5065\u5168\uFF08package.json / pyproject.toml / \u6784\u5EFA\u914D\u7F6E\u5B58\u5728\uFF09\uFF1B(b) \u80FD import / require \u6838\u5FC3\u5305\uFF1B(c) \u6D4B\u8BD5\u547D\u4EE4\u80FD\u88AB\u53D1\u73B0\u4E14\u53EF\u6267\u884C\uFF1B(d) \u6784\u5EFA\u4EA7\u7269\u53EF\u590D\u73B0\u3002\u6700\u540E\u8F93\u51FA\u4E00\u9875\u5192\u70DF\u68C0\u67E5\u6E05\u5355\u548C\u300C\u4E0B\u4E00\u6B65\u5EFA\u8BAE\u300D\u3002" : "Do not edit any files. Run a usability smoke check: (a) repo layout is sane (manifests/build configs exist), (b) the core package imports cleanly, (c) the test runner is discoverable and executable, (d) the build is reproducible. Output a one-page checklist and a 'next steps' recommendation."
      }
    ];
    const zhCards = cards;
    const paletteMarkup = `<div class="templates-grid">${zhCards.map((card, idx) => `<button class="template-card" data-template-index="${idx}" type="button"><span class="template-icon">${icon(card.icon)}</span><strong>${escapeHtml(card.title)}</strong><span class="template-sub">${escapeHtml(card.subtitle)}</span></button>`).join("")}</div><div class="templates-detail" id="templatesDetail" hidden></div>`;
    openPanel(t("templates.title"), paletteMarkup);
    const buttons = document.querySelectorAll("[data-template-index]");
    buttons.forEach((btn) => btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.templateIndex);
      if (!Number.isFinite(idx) || !cards[idx]) return;
      const card = cards[idx];
      const detail = document.querySelector("#templatesDetail");
      if (!detail) return;
      detail.innerHTML = `<div class="template-detail-header"><button class="panel-text-action" id="templatesBackToGrid">${icon("arrow-left")} ${t("panel.canvas") || (state.locale === "zh" ? "\u8FD4\u56DE" : "Back")}</button><div class="template-detail-body"><div class="template-detail-kicker">${escapeHtml(card.title)}</div><h4>${escapeHtml(card.subtitle)}</h4><pre class="template-prompt">${escapeHtml(card.prompt)}</pre><button class="panel-primary" id="templatesUsePrompt">${icon("send")} ${t("send")}</button></div></div>`;
      detail.hidden = false;
      detail.querySelector("#templatesBackToGrid")?.addEventListener("click", () => {
        detail.hidden = true;
      });
      detail.querySelector("#templatesUsePrompt")?.addEventListener("click", () => {
        const input = $("#promptInput");
        if (input) {
          input.value = card.prompt;
          input.focus();
          input.dispatchEvent(new Event("input", { bubbles: true }));
          closePanel();
        }
      });
    }));
  }
  async function openActivityPanel() {
    const current = beginPanelRequest(t("tasks.center"));
    try {
      const data = await requestJson("/api/tasks?limit=200");
      if (!current()) return;
      const tasks = Array.isArray(data.tasks) ? data.tasks : [];
      openPanel(t("tasks.center"), `<div class="panel-toolbar"><span>${tasks.length} ${state.locale === "zh" ? "\u4E2A\u4EFB\u52A1" : "tasks"}</span><button class="panel-text-action" data-panel-action="activity">${t("panel.refresh")}</button></div><div class="task-filters"><span class="filter-chip active">${t("tasks.allWorkspaces")}</span><span class="filter-chip">${escapeHtml(state.workspacePath ? state.workspacePath.split(/[\\/]/).filter(Boolean).pop() : "workspace")}</span></div><div class="task-list">${tasks.length ? tasks.map(taskRow).join("") : `<div class="empty-panel">${t("tasks.noHistory")}</div>`}</div>`);
    } catch (error) {
      if (!current()) return;
      openPanel(t("tasks.center"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }
  async function openWorkspacesPanel() {
    const current = beginPanelRequest(t("panel.workspaces"));
    try {
      const info = await requestJson("/api/workspace");
      if (!current()) return;
      const worktrees = Array.isArray(info.worktrees) ? info.worktrees : [];
      const sandbox = info.sandbox || {};
      const mcp = info.mcp || {};
      const recent = Array.isArray(info.recent_workspaces) ? info.recent_workspaces : [];
      const recentRows = recent.length ? recent.map((item) => `<button class="workspace-row ${item.path === info.path ? "active" : ""}" data-select-workspace="${escapeHtml(item.path)}"><span class="workspace-row-icon">${icon(item.path === info.path ? "radio" : "folder")}</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.path)}</small></span>${item.path === info.path ? `<em>ACTIVE</em>` : ""}</button>`).join("") : `<div class="empty-panel">${t("panel.noWorktrees")}</div>`;
      const rows = worktrees.map((item) => `<div class="worktree-row"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.branch || "detached")} \xB7 ${escapeHtml(item.path)}</small></div>${item.managed ? `<button class="panel-icon-action" data-remove-worktree="${escapeHtml(item.name)}" title="${t("panel.close")}">${icon("trash-2")}</button>` : ""}</div>`).join("");
      const sandboxLabel = sandbox.isolated ? t("panel.isolated") : sandbox.backend === "unavailable" ? t("connection.offline") : t("panel.hostProcess");
      openPanel(t("panel.workspaces"), `<div class="workspace-switcher"><div class="panel-section-title">${t("workspace.current")}</div><code class="workspace-current-path">${escapeHtml(info.path)}</code><form class="workspace-form" id="workspaceSelectForm"><label>${t("workspace.path")}<input id="workspacePathInput" name="path" required value="${escapeHtml(info.path)}" placeholder="${t("workspace.selectHint")}" /></label><button class="panel-primary" type="submit">${t("workspace.open")}</button></form><small class="workspace-hint">${t("workspace.selectHint")}</small><div class="panel-section-title">${t("workspace.recent")}</div><div class="workspace-list">${recentRows}</div></div><div class="status-grid"><div><span>${t("panel.sandbox")}</span><strong>${escapeHtml(String(sandbox.backend || "host"))}</strong><small>${sandboxLabel}</small></div><div><span>${t("panel.mcp")}</span><strong>${escapeHtml(String(mcp.configured || 0))}</strong><small>${t("panel.servers")}</small></div></div><div class="panel-section-title">${t("panel.createWorktree")}</div><form class="worktree-form" id="worktreeForm"><input id="worktreeName" name="name" required maxlength="64" placeholder="${t("panel.name")}" /><input id="worktreeBranch" name="branch" maxlength="128" placeholder="${t("panel.branch")}" /><button class="panel-primary" type="submit">${t("panel.create")}</button></form><div class="panel-section-title">${t("panel.gitWorktrees")}</div><div class="worktree-list">${rows || `<div class="empty-panel">${t("panel.noWorktrees")}</div>`}</div>`);
    } catch (error) {
      if (!current()) return;
      openPanel(t("panel.workspaces"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }
  function modelOptionsMarkup() {
    const current = state.model || "";
    const models = Array.isArray(state.models) ? [...state.models] : [];
    if (current && !models.some((item) => String(item?.id || "") === current)) models.unshift({ id: current });
    if (!models.length) return `<option value="${escapeHtml(current)}">${escapeHtml(current || (state.locale === "zh" ? "\u672A\u52A0\u8F7D\u6A21\u578B" : "No model loaded"))}</option>`;
    models.sort((left, right) => {
      const a = String(left?.id || "");
      const b = String(right?.id || "");
      return a === current ? -1 : b === current ? 1 : a.localeCompare(b);
    });
    return models.map((item) => {
      const id = String(item?.id || "");
      const context = item?.context_length ? ` \xB7 ${item.context_length.toLocaleString()} ctx` : "";
      return `<option value="${escapeHtml(id)}" ${id === current ? "selected" : ""}>${escapeHtml(id + context)}</option>`;
    }).join("");
  }
  async function loadModelCatalog({ quiet = false } = {}) {
    state.modelCatalogLoading = true;
    try {
      const data = await requestJson("/api/models", {}, 2e4);
      const models = Array.isArray(data.models) ? data.models.filter((item) => item && item.id).map((item) => typeof item === "string" ? { id: item } : item) : [];
      state.models = models;
      state.modelCatalogError = String(data.error || "");
      if (!localStorage.getItem("minicc-model") && data.default_model) state.model = String(data.default_model);
      const select = $("#modelSelect");
      if (select) {
        select.innerHTML = modelOptionsMarkup();
        select.value = state.model;
      }
      if (!quiet && state.modelCatalogError) showToast(state.modelCatalogError);
      return data;
    } catch (error) {
      state.modelCatalogError = error.message;
      if (!quiet) showToast(error.message);
      return null;
    } finally {
      state.modelCatalogLoading = false;
    }
  }
  function openSettingsPanel() {
    const current = state.locale === "zh" ? "\u4E2D\u6587" : "English";
    const effortMarkup = REASONING_EFFORTS.map((effort) => '<option value="' + effort + '" ' + (state.reasoningEffort === effort ? "selected" : "") + ">" + escapeHtml(t("reasoning." + effort)) + "</option>").join("");
    const languageButtons = '<div class="settings-block"><span>' + t("panel.language") + "</span><strong>" + current + '</strong><div class="settings-locale"><button class="locale-option ' + (state.locale === "zh" ? "active" : "") + '" data-set-locale="zh">\u4E2D\u6587</button><button class="locale-option ' + (state.locale === "en" ? "active" : "") + '" data-set-locale="en">English</button></div></div>';
    const modelNote = state.modelCatalogError || (state.locale === "zh" ? "\u4ECE\u5F53\u524D\u7F51\u5173\u8BFB\u53D6\u53EF\u7528\u6A21\u578B\uFF1B\u65B0\u7684\u4EFB\u52A1\u4F1A\u4F7F\u7528\u6B64\u9009\u62E9\u3002" : "Loads models from the configured gateway; new tasks use this choice.");
    const modelBlock = `<div class="settings-block"><span>${t("panel.model")}</span><div class="settings-model"><select id="modelSelect" aria-label="${escapeHtml(t("panel.model"))}">${modelOptionsMarkup()}</select><button type="button" class="panel-secondary model-refresh" id="refreshModelCatalog" title="${escapeHtml(t("panel.modelRefresh"))}">\u21BB</button></div><small class="settings-note">${escapeHtml(modelNote)}</small></div>`;
    const reasoningBlock = '<div class="settings-block"><span>' + t("panel.reasoning") + '</span><div class="settings-effort"><select id="reasoningEffortSelect" aria-label="' + escapeHtml(t("panel.reasoning")) + '">' + effortMarkup + '</select></div><small class="settings-note">' + escapeHtml(t("panel.reasoningNote")) + "</small></div>";
    const sandboxBlock = '<div class="settings-block"><span>' + t("panel.sandbox") + "</span><strong>" + (state.locale === "zh" ? "\u89C1\u5DE5\u4F5C\u533A\u9762\u677F" : "See Workspaces") + "</strong></div>";
    const notifyOn = notificationsEnabled();
    const notifyBlock = '<div class="settings-block"><span>' + t("notify.enable") + '</span><div class="settings-locale"><button class="locale-option notify-toggle ' + (notifyOn ? "active" : "") + '" data-notify="on" type="button">' + t("notify.on") + '</button><button class="locale-option notify-toggle ' + (notifyOn ? "" : "active") + '" data-notify="off" type="button">' + t("notify.off") + '</button></div><small class="settings-note">' + escapeHtml(t("notify.enableHint")) + "</small></div>";
    const rewindBlock = '<div class="settings-block settings-rewind"><span>' + escapeHtml(t("rewind.advanced")) + '</span><form id="rewindForm" class="rewind-form"><label class="rewind-label"><span>' + escapeHtml(t("rewind.keepLabel")) + '</span><input id="rewindKeep" type="number" min="1" value="3" required aria-label="' + escapeHtml(t("rewind.keepLabel")) + '" /></label><button class="send-button rewind-button" type="submit">' + escapeHtml(t("rewind.action")) + '</button></form><small class="settings-note">' + escapeHtml(t("rewind.hint")) + "</small></div>";
    const allowlistBlock = '<div class="settings-block" id="allowlistEditor"><span>' + escapeHtml(t("allowlist.title")) + '</span><small class="settings-note">' + escapeHtml(t("allowlist.hint")) + '</small><form id="allowlistForm" class="allowlist-form"><label><span>' + escapeHtml(t("allowlist.commands")) + '</span><textarea id="allowlistCommands" rows="3"></textarea></label><label><span>' + escapeHtml(t("allowlist.paths")) + '</span><textarea id="allowlistPaths" rows="3"></textarea></label><label><span>' + escapeHtml(t("allowlist.tools")) + '</span><textarea id="allowlistTools" rows="2"></textarea></label><button class="send-button" type="submit">' + escapeHtml(t("allowlist.save")) + "</button></form></div>";
    openPanel(t("panel.settings"), languageButtons + modelBlock + reasoningBlock + sandboxBlock + notifyBlock + rewindBlock + allowlistBlock);
    bindAllowlistEditor();
    document.querySelectorAll(".notify-toggle").forEach((button) => {
      button.addEventListener("click", async () => {
        const want = button.dataset.notify === "on";
        const ok = await setNotificationsEnabled(want);
        const active = want && ok;
        if (want && !ok) showToast(notificationsBlocked() ? t("notify.denied") : t("notify.unsupported"));
        document.querySelectorAll(".notify-toggle").forEach((node) => node.classList.toggle("active", node.dataset.notify === "on" === active));
      });
    });
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
            body: JSON.stringify({ session_id: state.sessionId, keep_messages: keepMessages })
          }, 2e4);
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
    const promo = state.locale === "zh" ? {
      panel: "minicc \xB7 Agent \u5DE5\u4F5C\u53F0",
      kicker: "LOCAL AGENT / INTERVIEW BUILD",
      title: "\u4ECE\u4E00\u53E5\u8BDD\uFF0C",
      accent: "\u5230\u4E00\u4EFD\u53EF\u9A8C\u8BC1\u7684\u4EA4\u4ED8\u3002",
      description: "minicc \u628A\u89C4\u5212\u3001\u5DE5\u5177\u8C03\u7528\u3001\u6587\u4EF6\u6539\u52A8\u548C\u6D4B\u8BD5\u9A8C\u8BC1\u653E\u5728\u540C\u4E00\u6761\u53EF\u8FFD\u6EAF\u8DEF\u5F84\u91CC\u3002\u4F60\u770B\u5230\u7684\u662F\u8BC1\u636E\uFF0C\u4E0D\u662F\u9ED1\u76D2\u91CC\u7684\u731C\u6D4B\u3002",
      cta: "\u5F00\u59CB\u65B0\u4EFB\u52A1",
      ctaNote: "LOCAL FIRST \xB7 SSE STREAM",
      proofTitle: "\u4ECE\u7B2C\u4E00\u884C\u4EE3\u7801\u5230\u6700\u540E\u4E00\u6B21\u9A8C\u8BC1",
      proofBody: "\u4E00\u4E2A\u5DE5\u4F5C\u533A \xB7 \u4E00\u6761\u53EF\u8FFD\u6EAF\u8DEF\u5F84",
      previewLabel: "agent / live",
      live: "RUNNING",
      taskLabel: "\u5F3A\u5316\u7248\u5BA3\u4F20\u9875",
      taskMeta: "workspace \xB7 minicc-codex",
      metrics: ["SSE \u5B9E\u65F6", "00:14", "72% context"],
      phases: [
        ["01", "\u7406\u89E3\u9700\u6C42", "\u62C6\u89E3\u76EE\u6807\u4E0E\u9A8C\u6536\u6807\u51C6", "check", "done"],
        ["02", "\u4FEE\u6539\u5DE5\u4F5C\u533A", "\u5199\u5165\u524D\u5148\u68C0\u67E5\u5F53\u524D diff", "loader-circle", "active"],
        ["03", "\u9A8C\u8BC1\u4EA4\u4ED8", "\u6D4B\u8BD5\u7ED3\u679C\u548C\u5269\u4F59\u98CE\u9669\u53EF\u590D\u76D8", "circle-dashed", ""]
      ],
      diffLabel: "live diff / web/styles.css",
      diff: [["+", "--agent-accent: coral;"], ["+", "--stream-mode: live;"], ["-", "--status: waiting;"], [" ", "/* verified by pytest */"]],
      sectionKicker: "WHY MINICC",
      sectionTitle: "\u5C11\u4E00\u70B9\u731C\u6D4B\uFF0C\u591A\u4E00\u70B9\u786E\u5B9A\u3002",
      sectionBody: "\u4E3A\u771F\u5B9E\u7684\u5DE5\u7A0B\u534F\u4F5C\u8BBE\u8BA1\uFF1A\u5148\u6536\u96C6\u4E0A\u4E0B\u6587\uFF0C\u518D\u6267\u884C\u52A8\u4F5C\uFF0C\u6700\u540E\u7528\u9A8C\u8BC1\u7ED3\u679C\u95ED\u73AF\u3002",
      capabilities: [
        ["scan-search", "\u770B\u5F97\u89C1\u8FC7\u7A0B", "\u9636\u6BB5\u6458\u8981\u3001\u5DE5\u5177\u8C03\u7528\u3001\u6D41\u5F0F\u56DE\u7B54\u548C\u4E0A\u4E0B\u6587\u7528\u91CF\u5B9E\u65F6\u5448\u73B0\uFF0C\u590D\u6742\u4EFB\u52A1\u4E0D\u4F1A\u7A81\u7136\u5931\u53BB\u65B9\u5411\u3002"],
        ["layers-3", "\u5E76\u884C\u800C\u4E0D\u4E92\u76F8\u963B\u585E", "\u72EC\u7ACB\u4F1A\u8BDD\u4F7F\u7528\u72EC\u7ACB\u4EFB\u52A1\u69FD\u4F4D\uFF1B\u6279\u91CF\u4EFB\u52A1\u53EF\u5E76\u884C\u6267\u884C\uFF0C\u5B8C\u6210\u540E\u518D\u5408\u5E76\u7ED3\u679C\u3002"],
        ["git-compare", "\u6539\u52A8\u53EF\u5BA1\u67E5", "\u6587\u4EF6\u5217\u8868\u548C\u7EA2\u7EFF diff \u76F4\u63A5\u8054\u52A8\uFF0C\u70B9\u51FB\u6587\u4EF6\u5373\u53EF\u67E5\u770B\u53D8\u66F4\u4E0E\u5F53\u524D\u5185\u5BB9\u3002"],
        ["shield-check", "\u672C\u5730\u4F18\u5148", "\u5DE5\u4F5C\u533A\u3001\u6743\u9650\u3001\u53D6\u6D88\u3001\u91CD\u8BD5\u548C\u5BA1\u8BA1\u90FD\u7531\u672C\u5730 harness \u8D1F\u8D23\uFF0C\u6A21\u578B\u53EA\u8D1F\u8D23\u5224\u65AD\u3002"]
      ],
      bottomKicker: "READY WHEN YOU ARE",
      bottomTitle: "\u4E0B\u4E00\u6B21\u63D0\u4EA4\uFF0C",
      bottomAccent: "\u4ECE\u4E00\u53E5\u8BDD\u5F00\u59CB\u3002",
      bottomBody: "\u5207\u6362\u4E2D\u6587\u6216 English\uFF0C\u6253\u5F00\u4E00\u4E2A\u771F\u5B9E\u5DE5\u4F5C\u533A\uFF0C\u7ACB\u5373\u4F53\u9A8C\u5B8C\u6574\u5FAA\u73AF\u3002",
      bottomCta: "\u8FDB\u5165\u5DE5\u4F5C\u53F0"
    } : {
      panel: "minicc \xB7 Agent workspace",
      kicker: "LOCAL AGENT / INTERVIEW BUILD",
      title: "From one prompt,",
      accent: "to a delivery you can verify.",
      description: "minicc puts planning, tool calls, file changes, and verification on one traceable path. You see evidence, not a black box guessing in the dark.",
      cta: "Start a new task",
      ctaNote: "LOCAL FIRST \xB7 SSE STREAM",
      proofTitle: "From the first line to the final check",
      proofBody: "One workspace \xB7 One traceable path",
      previewLabel: "agent / live",
      live: "RUNNING",
      taskLabel: "Harden the promo page",
      taskMeta: "workspace \xB7 minicc-codex",
      metrics: ["SSE live", "00:14", "72% context"],
      phases: [
        ["01", "Understand the request", "Turn intent into acceptance criteria", "check", "done"],
        ["02", "Change the workspace", "Inspect the diff before writing", "loader-circle", "active"],
        ["03", "Verify the delivery", "Keep tests and remaining risk visible", "circle-dashed", ""]
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
        ["shield-check", "Local first", "The local harness owns workspace, permissions, cancellation, retries, and audit trails. The model owns judgment."]
      ],
      bottomKicker: "READY WHEN YOU ARE",
      bottomTitle: "Your next commit,",
      bottomAccent: "starts with a sentence.",
      bottomBody: "Switch between Chinese and English, open a real workspace, and run the full loop.",
      bottomCta: "Open workspace"
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

        <div class="promo-proof"><span class="proof-avatars"><b>m</b><b>\u2713</b><b>\u2318</b></span><span><strong>${escapeHtml(promo.proofTitle)}</strong><small>${escapeHtml(promo.proofBody)}</small></span></div>

      </div>

      <div class="promo-hero-preview" aria-label="${escapeHtml(promo.previewLabel)}">

        <div class="promo-preview-head"><span class="terminal-dot coral"></span><span class="terminal-dot amber"></span><span class="terminal-dot mint"></span><span class="mono">${escapeHtml(promo.previewLabel)}</span><span class="console-live"><i></i> ${escapeHtml(promo.live)}</span></div>

        <div class="promo-preview-task"><span class="promo-preview-icon">${icon("sparkles")}</span><span><strong>${escapeHtml(promo.taskLabel)}</strong><small>${escapeHtml(promo.taskMeta)}</small></span><span class="promo-preview-check">${icon("radio")}</span></div>

        <div class="promo-metrics">${metricMarkup}</div>

        <div class="promo-phase-list">${phaseMarkup}</div>

        <div class="promo-diff"><div><span class="mono">${escapeHtml(promo.diffLabel)}</span><span class="promo-diff-state">\u25CF LIVE</span></div><pre>${diffMarkup}</pre></div>

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
    showToast(state.locale === "zh" ? "\u5BF9\u8BDD\u5DF2\u5BFC\u51FA" : "Chat exported");
  }
  function switchInspectorTab(tab) {
    runtime.inspectorTab = INSPECTOR_TABS.includes(tab) ? tab : INSPECTOR_TABS[0];
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
  async function rewindToUserIndex(userIndex) {
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
        body: JSON.stringify({ session_id: scope.sessionId, user_index: index })
      }, 2e4);
      showToast(`${t("rewind.done")} #${outcome.user_index || index}`);
      const cacheKey = sessionViewKey(scope.sessionId, scope.workspacePath);
      sessionMarkup.delete(cacheKey);
      try {
        localStorage.removeItem(cacheKey);
      } catch {
      }
      if (isViewScopeCurrent(scope)) {
        await loadTaskHistory();
        if (isViewScopeCurrent(scope)) renderSession(scope.sessionId);
      }
    } catch (error) {
      showToast(`${t("rewind.fail")}: ${error.message}`);
    }
  }
  async function restoreTaskSnapshot(taskId) {
    if (!taskId) return;
    try {
      const result = await requestJson("/api/workspace/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId })
      }, 2e4);
      const unresolved = [...result.conflicts || [], ...result.skipped || []];
      showToast(unresolved.length ? `${t("restore.partial")}: ${unresolved.slice(0, 3).join(", ")}${unresolved.length > 3 ? "\u2026" : ""}` : t("restore.done"));
      loadChanges();
      refreshFileTreeSoon();
    } catch (error) {
      showToast(`${t("restore.fail")}: ${error.message}`);
    }
  }
  function parseAllowlistLines(value) {
    return String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  }
  async function bindAllowlistEditor() {
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
            tools: parseAllowlistLines($("#allowlistTools")?.value)
          })
        });
        showToast(state.locale === "zh" ? "\u5141\u8BB8\u5217\u8868\u5DF2\u4FDD\u5B58" : "Allowlist saved");
      } catch (error) {
        showToast(error.message);
      }
    });
  }
  function openHelpPanel() {
    const rows = state.locale === "zh" ? [["\u53D1\u9001\u4EFB\u52A1", "Enter"], ["\u6362\u884C", "Shift+Enter"], ["\u65B0\u4EFB\u52A1", "Ctrl/\u2318 N"], ["\u547D\u4EE4\u9762\u677F", "Ctrl/\u2318 K"], ["\u8D26\u672C\u603B\u89C8", "Ctrl/\u2318 L"], ["\u641C\u7D22\u4EFB\u52A1", "/"], ["\u5FEB\u6377\u952E\u901F\u67E5", "?"], ["\u5173\u95ED\u9762\u677F / \u5C0F\u6E38\u620F", "Esc"], ["\u9009\u690D\u7269\uFF08\u6E38\u620F\u6253\u5F00\uFF09", "1-9"], ["\u6682\u505C / \u7EE7\u7EED", "P"], ["\u94F2\u5B50", "E"]] : [["Send task", "Enter"], ["Newline", "Shift+Enter"], ["New task", "Ctrl/\u2318 N"], ["Command palette", "Ctrl/\u2318 K"], ["Ledger overview", "Ctrl/\u2318 L"], ["Search tasks", "/"], ["Shortcut reference", "?"], ["Close panel / game", "Esc"], ["Pick seed (game)", "1-9"], ["Pause / resume", "P"], ["Shovel", "E"]];
    const list = rows.map(([label2, key]) => `<div class="help-shortcut"><span>${escapeHtml(label2)}</span><kbd>${escapeHtml(key)}</kbd></div>`).join("");
    openPanel(t("help.title"), `<div class="help-panel"><div class="panel-section-title">${escapeHtml(t("help.shortcuts"))}</div>${list}<div class="panel-section-title">${escapeHtml(t("help.arcade"))}</div><button type="button" class="panel-command" id="helpArcadeButton"><span>${icon("gamepad-2")}</span>${escapeHtml(t("help.arcade"))}</button></div>`);
    $("#helpArcadeButton")?.addEventListener("click", () => {
      closePanel();
      openArcade().catch((error) => showToast(error.message));
    });
  }

  // web/src/panels/index.js
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
    const anchor = (anchorElements.length ? anchorElements : [...area.querySelectorAll(".message")]).map((element) => ({ element, rect: element.getBoundingClientRect() })).filter(({ rect }) => rect.bottom > areaRect.top + 2 && rect.top < areaRect.bottom - 2).sort((left, right) => Math.max(left.rect.top, areaRect.top) - Math.max(right.rect.top, areaRect.top))[0];
    return {
      area,
      top: area.scrollTop,
      left: area.scrollLeft,
      followLatest: chatIsNearBottom(area),
      anchorElement: anchor?.element || null,
      anchorKey: anchor?.element?.dataset?.chatAnchor || "",
      anchorOffset: anchor ? anchor.rect.top - areaRect.top : 0
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
        const anchor = position.anchorElement?.isConnected ? position.anchorElement : [...position.area.querySelectorAll(".message[data-chat-anchor]")].find((element) => element.dataset.chatAnchor === position.anchorKey);
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
  function setConnection(connected, label2 = connected ? "Connected" : "Offline") {
    state.connection = connected;
    const status = $("#connectionStatus");
    status.classList.toggle("offline", !connected);
    const translated = label2 === "Connected" ? t("connection.connected") : label2 === "Offline" ? t("connection.offline") : label2;
    status.innerHTML = `<span class="status-pulse"></span><span>${escapeHtml(translated)}</span>`;
  }
  function setTaskTransportStatus(taskId, mode) {
    const binding = runningTasks.get(taskId);
    if (!binding) return;
    binding.transport = mode;
    binding.data = { ...binding.data || {}, transport: mode };
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
      const label2 = t("panel.reasoning") + ": " + t("reasoning." + state.reasoningEffort);
      button.title = label2;
      button.setAttribute("aria-label", label2);
    }
  }
  function setSession(sessionId) {
    const sessionChanged = state.sessionId !== sessionId;
    if (runtime.sessionViewReady && sessionChanged) {
      persistSessionView();
    }
    state.sessionId = sessionId;
    if (sessionChanged || !sessionTaskBindings(sessionId).some((binding) => binding.taskId === state.activeTaskId)) {
      const bindings = sessionTaskBindings(sessionId);
      state.activeTaskId = bindings.length ? bindings[bindings.length - 1].taskId : taskBySession.get(taskSessionKey(sessionId)) || null;
    }
    localStorage.setItem("minicc-session", sessionId);
    $("#topSession").textContent = sessionId;
    $$(".thread-item").forEach((item) => item.classList.toggle("active", item.dataset.session === sessionId));
    renderSession(sessionId, { followLatest: sessionChanged });
    runtime.sessionViewReady = true;
  }
  function taskSessionKey(sessionId, workspacePath = state.workspacePath) {
    const normalizedWorkspace = String(workspacePath || "default").replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase();
    return `${normalizedWorkspace}::${sessionId}`;
  }
  function sessionTaskBindings(sessionId, workspacePath = state.workspacePath) {
    return [...runningTasks.values()].filter((binding) => binding.sessionId === sessionId && taskSessionKey(binding.sessionId, binding.workspacePath) === taskSessionKey(sessionId, workspacePath) && !isTerminalTask(binding.data));
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
    const minutes = Math.floor(total % 3600 / 60);
    const seconds = total % 60;
    if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  function taskDuration(data) {
    const stored = Number(data?.duration_seconds);
    if (data?.started_at && ACTIVE_TASK_STATUSES.has(data.status)) {
      const started = Date.parse(data.started_at);
      if (Number.isFinite(started)) return Math.max(0, (Date.now() - started) / 1e3);
    }
    return Number.isFinite(stored) ? stored : 0;
  }
  function updateTaskDuration(data, loadingId = "") {
    const duration = formatDuration(taskDuration(data));
    if (loadingId) document.getElementById(loadingId)?.querySelectorAll("[data-live-duration]").forEach((item) => {
      item.textContent = duration;
    });
    const binding = data?.task_id ? runningTasks.get(data.task_id) : null;
    const scopedData = binding ? { ...data, session_id: binding.sessionId, workspace_path: binding.workspacePath } : data;
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
    }, 1e3);
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
    const merged = /* @__PURE__ */ new Map();
    for (const event of [...Array.isArray(current) ? current : [], ...Array.isArray(incoming) ? incoming : []]) {
      if (!event || typeof event !== "object") continue;
      const key = eventIdentity(event);
      if (key) merged.set(key, { ...event });
    }
    return [...merged.values()].sort((left, right) => eventSequence(left.sequence) - eventSequence(right.sequence)).slice(-1024);
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
      next.events = replaceEvents ? incoming.events.filter((event) => event && typeof event === "object").map((event) => ({ ...event })) : mergeTimelineEvents(previous.events, incoming.events);
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
      seenSequences: /* @__PURE__ */ new Set(),
      seenEventIds: /* @__PURE__ */ new Set()
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
    if (isCurrentTaskScope({ ...task, session_id: binding.sessionId, workspace_path: binding.workspacePath })) state.activeTaskId = task.task_id;
    startTaskTimer(task.task_id);
    return binding;
  }
  function restoreSessionTask(sessionId) {
    if (sessionId !== state.sessionId) return;
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
  function effectiveTaskPermissions() {
    const mode = state.permissionMode;
    return {
      mode,
      allowChanges: mode === "plan" ? false : mode === "yolo" ? true : state.allowChanges,
      allowNetwork: mode === "yolo" ? true : state.allowNetwork
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
    const zh2 = state.locale === "zh";
    const write = effective.mode === "acceptEdits" || effective.allowChanges;
    const command = effective.allowChanges;
    const label2 = $("#modeLabel");
    if (label2) label2.textContent = t("capability.executeToggle");
    const summary = zh2 ? `\u6587\u4EF6\uFF1A${write ? "\u53EF\u5199" : "\u53EA\u8BFB"} \xB7 \u547D\u4EE4\uFF1A${command ? "\u5141\u8BB8" : "\u4EC5\u5B89\u5168\u68C0\u67E5"} \xB7 \u8054\u7F51\uFF1A${effective.allowNetwork ? "\u5141\u8BB8" : "\u5173\u95ED"}` : `Files: ${write ? "write" : "read"} \xB7 Commands: ${command ? "enabled" : "safe checks"} \xB7 Network: ${effective.allowNetwork ? "on" : "off"}`;
    $("#permissionHint").textContent = summary;
    $("#permissionSummary").textContent = summary;
    $("#modeBadge").textContent = t(`perm.${effective.mode}`);
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
      showToast(state.locale === "zh" ? `\u6743\u9650\u6A21\u5F0F\uFF1A${t(`perm.${next}`)}` : `Permission mode: ${t(`perm.${next}`)}`);
    }
  }
  function normalizeTodoEntries(rawTodos) {
    if (!Array.isArray(rawTodos)) return null;
    return rawTodos.filter((todo) => todo && typeof todo === "object" && String(todo.content || "").trim()).map((todo) => ({
      content: String(todo.content).trim().slice(0, 500),
      status: TODO_STATUSES.has(String(todo.status)) ? String(todo.status) : "pending",
      priority: TODO_PRIORITIES.has(String(todo.priority)) ? String(todo.priority) : "medium"
    })).slice(0, 50);
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
    if (todos) runtime.latestTodos = todos;
    renderTodoPanel();
  }
  function renderTodoPanel() {
    const section = $("#todoSection");
    if (!section) return;
    const hasTodos = Array.isArray(runtime.latestTodos) && runtime.latestTodos.length > 0;
    section.hidden = !hasTodos;
    if (!hasTodos) return;
    const completed = runtime.latestTodos.filter((todo) => todo.status === "completed").length;
    const progress = $("#todoProgressCount");
    if (progress) {
      progress.textContent = `${completed}/${runtime.latestTodos.length}`;
      progress.setAttribute("aria-label", `${t("todo.progressAria")}: ${completed}/${runtime.latestTodos.length}`);
    }
    const list = $("#todoListBody");
    if (!list) return;
    const statusLabels = { pending: t("todo.pending"), in_progress: t("todo.inProgress"), completed: t("todo.completed") };
    list.innerHTML = runtime.latestTodos.map((todo) => `
    <li class="todo-item todo-${escapeHtml(todo.status)}" aria-label="${escapeHtml(`${todo.content} \xB7 ${statusLabels[todo.status] || todo.status}`)}">
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
  var FILE_TREE_DEPTH = 2;
  var FILE_TREE_RENDER_LIMIT = 800;
  var FILE_TREE_REFRESH_DELAY = 200;
  var fileTreeState = {
    loaded: false,
    loading: false,
    rootEntries: [],
    rootTruncated: false,
    rootError: "",
    children: /* @__PURE__ */ new Map(),
    // dirPath -> { entries, truncated }
    expanded: /* @__PURE__ */ new Set(),
    pending: /* @__PURE__ */ new Set(),
    fileIndex: [],
    // [{path, size}] for @-mentions
    requestToken: 0,
    refreshTimer: 0
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
      return String(left?.name || left?.path || "").localeCompare(String(right?.name || right?.path || ""), void 0, { sensitivity: "base", numeric: true });
    });
  }
  function fileTreeIndexFiles(entries) {
    const indexed = new Set(fileTreeState.fileIndex.map((item) => item.path));
    for (const entry of Array.isArray(entries) ? entries : []) {
      if (!entry || entry.type !== "file" || !entry.path) continue;
      if (indexed.has(entry.path)) continue;
      fileTreeState.fileIndex.push({ path: String(entry.path), size: Number(entry.size || 0) });
      indexed.add(entry.path);
    }
    if (fileTreeState.fileIndex.length > 4e3) fileTreeState.fileIndex.length = 4e3;
  }
  function fileTreeSeedChildren(dirPath, entries, truncated = false) {
    const children = [];
    for (const entry of Array.isArray(entries) ? entries : []) {
      if (entry?.path && fileTreeParentOf(entry.path) === dirPath) children.push(entry);
    }
    fileTreeIndexFiles(children);
    if (!children.length) return;
    fileTreeState.children.set(dirPath, { entries: children, truncated });
  }
  async function fileTreeFetch(dirPath) {
    const data = await requestJson(`/api/files?path=${encodeURIComponent(dirPath || "")}&depth=${FILE_TREE_DEPTH}`, {}, 12e3);
    return { entries: Array.isArray(data.entries) ? data.entries : [], truncated: Boolean(data.truncated) };
  }
  async function loadFileTree() {
    if (!state.workspacePath) return;
    const token = ++fileTreeState.requestToken;
    fileTreeState.pending.clear();
    const workspacePath = state.workspacePath;
    fileTreeState.loading = true;
    fileTreeState.rootError = "";
    renderFileTree();
    try {
      const result = await fileTreeFetch("");
      if (token !== fileTreeState.requestToken || workspacePath !== state.workspacePath) return;
      fileTreeState.rootEntries = fileTreeSort(result.entries.filter((entry) => entry?.path && fileTreeParentOf(entry.path) === ""));
      fileTreeState.rootTruncated = result.truncated;
      fileTreeState.children = /* @__PURE__ */ new Map();
      fileTreeState.expanded = /* @__PURE__ */ new Set();
      fileTreeState.fileIndex = [];
      fileTreeState.loaded = true;
      fileTreeIndexFiles(fileTreeState.rootEntries);
      for (const entry of fileTreeState.rootEntries) {
        if (entry.type === "dir") fileTreeSeedChildren(entry.path, result.entries, result.truncated);
      }
    } catch (error) {
      if (token !== fileTreeState.requestToken || workspacePath !== state.workspacePath) return;
      fileTreeState.rootError = String(error?.message || "error");
      fileTreeState.loaded = true;
    } finally {
      if (token === fileTreeState.requestToken && workspacePath === state.workspacePath) {
        fileTreeState.loading = false;
        renderFileTree();
        if (mentionState.open) updateMentionPopover();
      }
    }
  }
  async function toggleFileDir(dirPath) {
    const token = fileTreeState.requestToken;
    const workspacePath = state.workspacePath;
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
        if (token !== fileTreeState.requestToken || workspacePath !== state.workspacePath) return;
        fileTreeSeedChildren(dirPath, result.entries, result.truncated);
        for (const entry of result.entries) {
          if (entry?.type === "dir" && fileTreeParentOf(entry.path) === dirPath) fileTreeSeedChildren(entry.path, result.entries, result.truncated);
        }
      } catch (error) {
        if (token !== fileTreeState.requestToken || workspacePath !== state.workspacePath) return;
        fileTreeState.children.set(dirPath, { entries: [], error: String(error?.message || "error") });
      } finally {
        if (token === fileTreeState.requestToken && workspacePath === state.workspacePath) fileTreeState.pending.delete(dirPath);
      }
    }
    renderFileTree();
    if (mentionState.open) updateMentionPopover();
  }
  function fileTreeRowMarkup(entry, level) {
    const indent = `padding-left:${6 + Math.min(level, 8) * 13}px`;
    if (entry.type === "dir") {
      const expanded = fileTreeState.expanded.has(entry.path);
      return `<button type="button" class="file-tree-row" role="treeitem" tabindex="-1" aria-level="${level + 1}" aria-expanded="${expanded ? "true" : "false"}" data-tree-dir="${escapeHtml(entry.path)}" style="${indent}" aria-label="${escapeHtml(entry.name)}"><span class="file-tree-chevron" aria-hidden="true">${icon(expanded ? "chevron-down" : "chevron-right")}</span><span class="file-tree-icon" aria-hidden="true">${icon(expanded ? "folder-open" : "folder")}</span><span class="file-tree-name">${escapeHtml(entry.name || entry.path)}</span></button>`;
    }
    const size = Number(entry.size || 0);
    return `<button type="button" class="file-tree-row" role="treeitem" tabindex="-1" aria-level="${level + 1}" data-open-diff="${escapeHtml(entry.path)}" style="${indent}" aria-label="${escapeHtml(`${entry.name || entry.path} ${formatBytes(size)}`)}"><span class="file-tree-chevron" aria-hidden="true"></span><span class="file-tree-icon" aria-hidden="true">${icon("file-code-2")}</span><span class="file-tree-name">${escapeHtml(entry.name || entry.path)}</span><span class="file-tree-size">${escapeHtml(formatBytes(size))}</span></button>`;
  }
  function renderFileTree() {
    const tree = $("#fileTree");
    if (!tree) return;
    const focused = tree.contains(document.activeElement) ? document.activeElement : null;
    const focusPath = focused?.dataset.treeDir || focused?.dataset.openDiff;
    const previousStop = tree.querySelector('[role="treeitem"][tabindex="0"]');
    const stopPath = focusPath || previousStop?.dataset.treeDir || previousStop?.dataset.openDiff;
    if (fileTreeState.loading && !fileTreeState.loaded) {
      tree.innerHTML = `<div class="file-tree-status">${escapeHtml(t("files.loading"))}</div>`;
      return;
    }
    if (fileTreeState.rootError) {
      tree.innerHTML = `<div class="file-tree-status file-tree-error"><span>${escapeHtml(t("files.loadError"))}</span><small>${escapeHtml(fileTreeState.rootError)}</small></div>`;
      return;
    }
    const rows = [];
    const notes = /* @__PURE__ */ new Set();
    let remaining = FILE_TREE_RENDER_LIMIT;
    const walk = (entries, level, dirPath) => {
      for (const entry of entries) {
        if (remaining <= 0) {
          notes.add(t("files.truncated"));
          return;
        }
        remaining -= 1;
        rows.push(fileTreeRowMarkup(entry, level));
        if (entry.type !== "dir" || !fileTreeState.expanded.has(entry.path)) continue;
        const cached = fileTreeState.children.get(entry.path);
        const childIndent = `padding-left:${6 + Math.min(level + 1, 8) * 13}px`;
        if (cached?.error) rows.push(`<div class="file-tree-status" style="${childIndent}">${escapeHtml(cached.error)}</div>`);
        else if (!cached) {
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
    const items = [...tree.querySelectorAll('[role="treeitem"]')];
    const active = items.find((item) => (item.dataset.treeDir || item.dataset.openDiff) === stopPath) || items[0];
    items.forEach((item) => {
      item.tabIndex = item === active ? 0 : -1;
    });
    if (active && focused) active.focus({ preventScroll: true });
    refreshIcons();
  }
  async function handleFileTreeKeydown(event) {
    const tree = $("#fileTree");
    const row = event.target.closest('[role="treeitem"]');
    if (!row || !["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const rows = [...tree.querySelectorAll('[role="treeitem"]')];
    const index = rows.indexOf(row);
    let target;
    if (event.key === "Home") target = rows[0];
    else if (event.key === "End") target = rows.at(-1);
    else if (event.key === "ArrowDown") target = rows[Math.min(rows.length - 1, index + 1)];
    else if (event.key === "ArrowUp") target = rows[Math.max(0, index - 1)];
    else if (event.key === "ArrowRight" && row.dataset.treeDir && row.getAttribute("aria-expanded") === "false") {
      await toggleFileDir(row.dataset.treeDir);
      return;
    } else if (event.key === "ArrowRight" && row.dataset.treeDir && Number(rows[index + 1]?.getAttribute("aria-level")) > Number(row.getAttribute("aria-level"))) target = rows[index + 1];
    else if (event.key === "ArrowLeft") {
      if (row.dataset.treeDir && row.getAttribute("aria-expanded") === "true") {
        await toggleFileDir(row.dataset.treeDir);
        return;
      }
      const parent = fileTreeParentOf(row.dataset.treeDir || row.dataset.openDiff);
      target = rows.find((item) => item.dataset.treeDir === parent);
    }
    if (target) {
      rows.forEach((item) => {
        item.tabIndex = item === target ? 0 : -1;
      });
      target.focus();
    }
  }
  function refreshFileTreeSoon() {
    window.clearTimeout(fileTreeState.refreshTimer);
    fileTreeState.refreshTimer = window.setTimeout(() => {
      loadFileTree();
    }, FILE_TREE_REFRESH_DELAY);
  }
  function refreshFileTree() {
    refreshCommandCatalog();
    fileTreeState.requestToken += 1;
    fileTreeState.loaded = false;
    fileTreeState.pending.clear();
    fileTreeState.children.clear();
    fileTreeState.fileIndex = [];
    fileTreeState.rootEntries = [];
    loadFileTree();
  }
  var MENTION_MAX_OPTIONS = 8;
  var mentionState = { open: false, options: [], active: 0, matchStart: -1, mode: "file" };
  var commandCatalog = { items: [] };
  async function refreshCommandCatalog() {
    try {
      const data = await requestJson("/api/commands", {}, 1e4);
      commandCatalog.items = Array.isArray(data?.commands) ? data.commands.filter((item) => item && item.name) : [];
    } catch {
      commandCatalog.items = [];
    }
  }
  function commandTokenAt(text, caret) {
    const before = String(text || "").slice(0, Math.max(0, caret));
    const match = /^\/([^\s/]*)$/.exec(before);
    if (!match) return null;
    return { fragment: match[1], start: 0 };
  }
  function commandCandidates(fragment) {
    const needle = String(fragment || "").toLowerCase();
    return commandCatalog.items.filter((item) => !needle || String(item.name).toLowerCase().startsWith(needle)).slice(0, MENTION_MAX_OPTIONS);
  }
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
    const isCommand = mentionState.mode === "command";
    const body = options.length ? options.map((item, index) => {
      const label2 = isCommand ? `/${item.name}` : item.path;
      const detail = isCommand ? `${item.description || ""}${item.scope === "project" ? " \xB7 project" : ""}` : formatBytes(item.size);
      return `<button type="button" class="mention-option${index === mentionState.active ? " active" : ""}" role="option" aria-selected="${index === mentionState.active ? "true" : "false"}" data-mention-index="${index}" aria-label="${escapeHtml(label2)}"><span class="mention-path">${escapeHtml(label2)}</span><small class="mention-size">${escapeHtml(detail)}</small></button>`;
    }).join("") : `<div class="mention-empty">${escapeHtml(isCommand ? t("at.commandEmpty") : t("at.empty"))}</div>`;
    popover.innerHTML = `${body}<div class="mention-hint" aria-hidden="true">${escapeHtml(t("at.hint"))}</div>`;
    popover.hidden = false;
    popover.querySelector(`[data-mention-index="${mentionState.active}"]`)?.scrollIntoView({ block: "nearest" });
  }
  function updateMentionPopover() {
    const input = $("#promptInput");
    if (!input) return;
    const caret = input.selectionStart ?? input.value.length;
    const token = mentionTokenAt(input.value, caret);
    if (token) {
      ensureMentionIndex();
      mentionState.open = true;
      mentionState.mode = "file";
      mentionState.matchStart = token.start;
      mentionState.options = mentionCandidates(token.fragment);
    } else {
      const slash = commandTokenAt(input.value, caret);
      if (!slash) {
        closeMentionPopover();
        return;
      }
      mentionState.open = true;
      mentionState.mode = "command";
      mentionState.matchStart = slash.start;
      mentionState.options = commandCandidates(slash.fragment);
    }
    mentionState.active = Math.min(mentionState.active, Math.max(0, mentionState.options.length - 1));
    renderMentionPopover();
    positionMentionPopover();
  }
  function closeMentionPopover() {
    mentionState.open = false;
    mentionState.options = [];
    mentionState.active = 0;
    mentionState.matchStart = -1;
    mentionState.mode = "file";
    const popover = $("#mentionPopover");
    if (popover) {
      popover.hidden = true;
      popover.innerHTML = "";
    }
  }
  function applyMentionOption(index = mentionState.active) {
    const option = mentionState.options[index];
    const input = $("#promptInput");
    if (!option || !input) {
      closeMentionPopover();
      return;
    }
    const value = String(input.value || "");
    const caret = input.selectionStart ?? value.length;
    const insert = mentionState.mode === "command" ? `/${option.name} ` : `@${option.path} `;
    const next = value.slice(0, mentionState.matchStart) + insert + value.slice(caret);
    input.value = next;
    const nextCaret = mentionState.matchStart + insert.length;
    input.setSelectionRange(nextCaret, nextCaret);
    closeMentionPopover();
    input.focus();
  }
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
      if (!mentionState.options.length) {
        closeMentionPopover();
        return false;
      }
      event.preventDefault();
      applyMentionOption();
      return true;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeMentionPopover();
      return true;
    }
    return false;
  }
  var GLOBAL_SEARCH_DEBOUNCE = 300;
  var globalSearchTimer = 0;
  var globalSearchToken = 0;
  function relativeTimeFrom(value) {
    const epoch = Date.parse(String(value || ""));
    if (!Number.isFinite(epoch)) return "--";
    const seconds = Math.max(0, Math.round((Date.now() - epoch) / 1e3));
    const zh2 = state.locale === "zh";
    if (seconds < 60) return zh2 ? "\u521A\u521A" : "just now";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return zh2 ? `${minutes} \u5206\u949F\u524D` : `${minutes}m ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return zh2 ? `${hours} \u5C0F\u65F6\u524D` : `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days < 30) return zh2 ? `${days} \u5929\u524D` : `${days}d ago`;
    return new Date(epoch).toLocaleDateString(zh2 ? "zh-CN" : "en-US");
  }
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
    const resultsNode = $("#globalSearchResults");
    const current = () => token === globalSearchToken && resultsNode === $("#globalSearchResults") && $("#panelModal").classList.contains("show");
    renderGlobalSearchStatus("searching");
    try {
      const data = await requestJson(`/api/history/search?q=${encodeURIComponent(query)}&limit=30`, {}, 15e3);
      if (!current()) return;
      const results = Array.isArray(data.results) ? data.results : [];
      const box = $("#globalSearchResults");
      if (!box) return;
      box.innerHTML = results.length ? results.map((item) => globalSearchResultMarkup(item, query)).join("") : "";
      if (!results.length) renderGlobalSearchStatus("noResults");
      else refreshIcons();
    } catch (error) {
      if (!current()) return;
      renderGlobalSearchStatus("error", error.message);
    }
  }
  function scheduleGlobalSearch() {
    const input = $("#globalSearchInput");
    if (!input) return;
    window.clearTimeout(globalSearchTimer);
    globalSearchToken += 1;
    const query = input.value.trim();
    if (!query) {
      renderGlobalSearchStatus("hint");
      return;
    }
    globalSearchTimer = window.setTimeout(() => runGlobalSearch(query), GLOBAL_SEARCH_DEBOUNCE);
  }
  function openGlobalSearchPanel() {
    window.clearTimeout(globalSearchTimer);
    globalSearchToken += 1;
    openPanel(t("search.global"), `<div class="global-search-panel"><div class="global-search-box">${icon("search")}<input id="globalSearchInput" type="search" placeholder="${escapeHtml(t("search.globalPlaceholder"))}" aria-label="${escapeHtml(t("search.global"))}" autocomplete="off" /></div><div class="global-search-results" id="globalSearchResults" aria-live="polite"><div class="empty-panel">${escapeHtml(t("search.hint"))}</div></div></div>`);
    const input = $("#globalSearchInput");
    input?.addEventListener("input", scheduleGlobalSearch);
    input?.focus();
  }
  function userRewindButton(index = 0) {
    return `<button type="button" class="rewind-to-here" data-user-index="${Number(index) || 0}">${escapeHtml(t("rewind.toHere"))}</button>`;
  }
  function decorateUserRewindButtons(root = $("#messageList")) {
    if (!root) return;
    [...root.querySelectorAll(".user-message")].forEach((node, index) => {
      const userIndex = index + 1;
      node.dataset.userIndex = String(userIndex);
      let button = node.querySelector(".rewind-to-here");
      if (!button) {
        const meta = node.querySelector(".message-meta") || node;
        meta.insertAdjacentHTML("beforeend", userRewindButton(userIndex));
        button = meta.querySelector(".rewind-to-here");
      }
      if (button) button.dataset.userIndex = String(userIndex);
    });
  }
  function addUserMessage(text, attachments = []) {
    const empty = $("#messageList .empty-session");
    empty?.remove();
    $("#messageList").insertAdjacentHTML("beforeend", `
    <article class="message user-message">
      <div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(t("message.now"))}</time>${userRewindButton(0)}</div>
      <div class="message-body"><div class="message-text">${formatText(text)}</div>${attachmentMarkup(attachments)}</div>
    </article>`);
    decorateUserRewindButtons();
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
    const phase = TERMINAL_TASK_STATUSES.has(status) || status === "queued" ? status : data.phase || status;
    const key = {
      queued: "phase.queued",
      planning: "phase.planning",
      intake: "phase.intake",
      tool: "phase.tool",
      execution: "phase.execution",
      answering: "phase.answering",
      summarize: "phase.summarize",
      review: "phase.review",
      verify: "phase.verify",
      repair: "phase.repair",
      permission: "phase.permission",
      merging: "phase.merging",
      completed: "phase.completed",
      failed: "phase.failed",
      cancelled: "phase.cancelled",
      interrupted: "phase.interrupted"
    }[phase] || "working";
    return t(key);
  }
  function phaseClass(data) {
    const status = String(data?.status || "").toLowerCase();
    const value = TERMINAL_TASK_STATUSES.has(status) || status === "queued" ? status : String(data?.phase || data?.status || "planning").toLowerCase();
    return TASK_PHASES.has(value) ? value : "planning";
  }
  function compactNumber(value) {
    const number = Number(value || 0);
    if (number >= 1e6) return `${(number / 1e6).toFixed(number >= 1e7 ? 0 : 1)}m`;
    if (number >= 1e3) return `${(number / 1e3).toFixed(number >= 1e4 ? 0 : 1)}k`;
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
  function cacheDonut(data, px = 34) {
    const metrics = data?.metrics && typeof data.metrics === "object" ? data.metrics : {};
    const tokens = data?.tokens_used && typeof data.tokens_used === "object" ? data.tokens_used : {};
    let rate = typeof metrics.cache_hit_rate === "number" ? metrics.cache_hit_rate : NaN;
    if (!Number.isFinite(rate)) {
      const hit = Number(tokens.prompt_cache_hit_tokens);
      const miss = Number(tokens.prompt_cache_miss_tokens);
      if (Number.isFinite(hit) && Number.isFinite(miss) && hit + miss > 0) rate = hit / (hit + miss);
    }
    const style = px !== 34 ? ` style="--donut:${px}px"` : "";
    if (!Number.isFinite(rate)) {
      return `<span class="cache-donut cache-donut-unreported" role="img" aria-label="${escapeHtml(t("tasks.cache"))}"${style}><svg viewBox="0 0 42 42" aria-hidden="true"><circle class="cache-donut-track" cx="21" cy="21" r="15.9155" pathLength="100" /></svg><em>${escapeHtml(t("tasks.cacheUnreported"))}</em></span>`;
    }
    const pct = Math.max(0, Math.min(100, Math.round(rate * 100)));
    const tone = rate >= 0.7 ? "good" : rate >= 0.4 ? "mid" : "low";
    return `<span class="cache-donut cache-donut-${tone}" role="img" aria-label="${escapeHtml(t("tasks.cache"))} ${pct}%"${style}><svg viewBox="0 0 42 42" aria-hidden="true"><circle class="cache-donut-track" cx="21" cy="21" r="15.9155" pathLength="100" /><circle class="cache-donut-arc" cx="21" cy="21" r="15.9155" pathLength="100" stroke-dasharray="${pct} 100" /></svg><b>${pct}%</b></span>`;
  }
  function cacheTurnSparkline(usageByTurn) {
    const series = cacheTurnSeries(usageByTurn);
    if (!series.length) return "";
    const W = 12;
    const GAP = 3;
    const H = 34;
    const bars = series.map((point, i) => {
      const tone = cacheTurnTone(point.rate);
      const height = point.rate == null ? 3 : Math.max(3, Math.round(point.rate * H));
      const x = i * (W + GAP);
      const y = H - height;
      const pct = point.rate == null ? "\u2014" : `${Math.round(point.rate * 100)}%`;
      const title = `#${i + 1} ${point.kind} \xB7 ${pct} \xB7 ${compactNumber(point.hit)}/${compactNumber(point.miss)}`;
      return `<rect x="${x}" y="${y}" width="${W}" height="${height}" rx="2" class="cache-series-bar cache-series-${tone}"><title>${escapeHtml(title)}</title></rect>`;
    }).join("");
    const width = series.length * (W + GAP) - GAP;
    return `<div class="cache-series"><span class="cache-series-label">${escapeHtml(t("ledger.perCallTitle"))}</span><svg viewBox="0 0 ${width} ${H}" role="img" aria-label="${escapeHtml(t("ledger.perCallTitle"))}">${bars}</svg></div>`;
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
    const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 3e5);
    const estimated = data.tokens_used?.estimated || data.usage_by_turn?.some((item) => item.estimated);
    const tokenText = `${estimated ? "~" : ""}${compactNumber(tokens)} ${t("tasks.tokens")}`;
    const cost = typeof data.cost_usd === "number" ? data.cost_usd : NaN;
    const costText = Number.isFinite(cost) ? ` \xB7 $${cost.toFixed(cost < 0.01 ? 4 : 2)}` : "";
    return `${tokenText}${costText} \xB7 ${compactNumber(context)}/${compactNumber(limit)} ${t("tasks.context")} \xB7 ${t("tasks.cache")} ${cacheMetric(data)}`;
  }
  function renderVerification(data = state.lastTask) {
    const target = $("#verificationList");
    if (!target) return;
    const events = (data?.events || []).filter((event) => /verification_|completion_assessed/.test(event.code || ""));
    const zh2 = state.locale === "zh";
    if (!events.length) {
      target.innerHTML = `<div class="verification-empty">${icon("shield-check")}<strong>${zh2 ? "\u5C1A\u65E0\u9A8C\u8BC1\u8BC1\u636E" : "No verification evidence yet"}</strong><span>${zh2 ? "\u4EFB\u52A1\u6267\u884C\u7684\u68C0\u67E5\u548C\u5B8C\u6210\u8BC4\u4F30\u4F1A\u663E\u793A\u5728\u8FD9\u91CC\u3002" : "Checks and completion assessments will appear here."}</span></div>`;
      return;
    }
    target.innerHTML = events.slice(-12).reverse().map((event) => `<details class="verification-card" data-status="${escapeHtml(event.status || "pending")}"><summary>${icon(event.status === "error" ? "alert-circle" : "list-checks")}<span>${escapeHtml(event.summary || traceLabel(event))}</span></summary><pre>${escapeHtml(JSON.stringify(event.detail || {}, null, 2))}</pre></details>`).join("");
  }
  function runtimeMetricsMarkup(data) {
    const metrics = data?.metrics;
    if (!metrics || typeof metrics !== "object" || !metrics.workflow && !metrics.verification_runs && !metrics.trace_events) return "";
    const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
    const duration = formatDuration(metrics.duration_seconds || 0);
    const series = cacheTurnSparkline(data?.usage_by_turn);
    const fingerprints = prefixStripMarkup(prefixRows(data?.usage_by_turn), { hitLabel: t("ledger.cacheHits") });
    return `<div><div class="panel-section-title">${escapeHtml(t("tasks.runtime"))}</div><div class="status-grid"><div><span>${escapeHtml(t("tasks.workflow"))}</span><strong>${escapeHtml(String(metrics.workflow || "coding"))}</strong><small>${escapeHtml(String(metrics.phase || data.phase || ""))}</small></div><div><span>${escapeHtml(t("tasks.repairs"))}</span><strong>${escapeHtml(String(metrics.repair_attempts || 0))}</strong><small>${escapeHtml(duration)}</small></div><div><span>${escapeHtml(t("tasks.verifications"))}</span><strong>${escapeHtml(String(metrics.verification_runs || 0))}</strong><small>${escapeHtml(String(metrics.verification_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.cache"))}</span><strong>${cacheDonut(data)}</strong><small>${escapeHtml(String(metrics.cache_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.traces"))}</span><strong>${escapeHtml(String(metrics.trace_events || 0))}</strong><small>${escapeHtml(`${budget.turns || 0} turns \xB7 ${budget.tool_calls || 0} tools`)}</small></div></div>${series}${fingerprints}</div>`;
  }
  function updateInspectorMetrics(data) {
    if (!data) return;
    const tokens = Number(data.tokens_used?.total_tokens || 0);
    const context = Number(data.context?.tokens || 0);
    const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 3e5);
    $("#tokenMetric").textContent = compactNumber(tokens);
    $("#contextMetric").textContent = `${compactNumber(context)}/${compactNumber(limit)}`;
    $("#cacheMetric").innerHTML = cacheDonut(data, 26);
    $("#compactionMetric").textContent = String(data.compaction_events?.length || 0);
    $("#contextCount").textContent = taskMetrics(data);
    const slot = $("#pulseCacheSeries");
    if (slot) {
      const markup = cacheTurnSparkline(data.usage_by_turn);
      if (slot.innerHTML !== markup) {
        slot.innerHTML = markup;
        slot.hidden = !markup;
      }
    }
  }
  async function updateRunningLight() {
    const root = $("#runningLight");
    if (!root) return;
    try {
      const data = await requestJson("/api/metrics");
      const hit = data?.llm_cache?.cache_hit_rate;
      const finite = typeof hit === "number" && Number.isFinite(hit);
      const hitText = finite ? `${Math.round(hit * 1e3) / 10}%` : "\u2014";
      const tasksEl = $("#runningLightTasks");
      const cacheEl = $("#runningLightCache");
      if (cacheEl) cacheEl.textContent = hitText;
      if (tasksEl) tasksEl.textContent = String(Number(data?.task_count ?? 0));
      root.dataset.tone = !finite ? "quiet" : hit >= 0.7 ? "high" : hit >= 0.4 ? "mid" : "low";
    } catch {
    }
  }
  async function updateRunningLightDigest() {
    const branch = $("#runningLightBranch");
    if (!branch) return;
    try {
      const digest = await requestJson("/api/digest");
      const isGit = digest?.is_git === true;
      branch.textContent = isGit && digest.branch ? `${digest.branch}${digest.head_short ? ` @ ${digest.head_short}` : ""}` : "\u2014";
      branch.title = isGit && digest.total_commits != null ? `${digest.total_commits} commits \xB7 ${digest.roadmap_batches ?? "\u2014"} batches` : "";
    } catch {
      branch.textContent = "\u2014";
    }
  }
  var TOOL_STREAM_CODES = /^(provider_tool_call_start|provider_tool_call_progress|provider_reasoning_progress)$/;
  function latestToolStreamEvent(data) {
    if (!ACTIVE_TASK_STATUSES.has(String(data?.status || ""))) return null;
    const events = Array.isArray(data?.events) ? data.events : [];
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const ev = events[i];
      if (TOOL_STREAM_CODES.test(String(ev?.code || ""))) return ev;
    }
    return null;
  }
  function updateToolStreamChip(data) {
    const chip = $("#taskDockToolStream");
    if (!chip) return;
    const ev = latestToolStreamEvent(data);
    if (!ev) {
      chip.hidden = true;
      chip.removeAttribute("data-done");
      return;
    }
    const detail = ev.detail && typeof ev.detail === "object" ? ev.detail : {};
    const chars = Number(detail.chars) || 0;
    const unit = escapeHtml(t("stream.charsUnit"));
    if (String(ev.code) === "provider_reasoning_progress") {
      chip.hidden = false;
      chip.removeAttribute("data-done");
      chip.innerHTML = `${icon("sparkles")}<span>${escapeHtml(t("stream.reasoningForming"))} \xB7 ${chars} ${unit}</span>`;
      return;
    }
    const tool = escapeHtml(String(detail.tool || t("stream.toolForming")));
    const done = Boolean(detail.done);
    chip.hidden = false;
    if (done) chip.setAttribute("data-done", "");
    else chip.removeAttribute("data-done");
    chip.innerHTML = `${icon(done ? "check" : "loader-circle")}<span>${tool} \xB7 ${chars} ${unit}</span>`;
  }
  function updateTaskDock(data) {
    if (!data || !isFocusedTask(data)) return;
    renderVerification(data);
    if (data.task_id && !state.activeTaskId) state.activeTaskId = data.task_id;
    state.lastTask = data;
    const dock = $("#taskDock");
    if (!dock) return;
    dock.hidden = false;
    dock.dataset.status = data.status || "running";
    $("#taskDockTitle").textContent = data.task_kind === "batch" ? data.message || t("tasks.center") : data.preview || data.prompt || t("tasks.center");
    $("#taskDockPhase").textContent = phaseLabel(data);
    $("#taskDockMetrics").textContent = taskMetrics(data);
    $("#taskDockCompactions").textContent = `${data.compaction_events?.length || 0} ${t("tasks.compacted")}`;
    $("#taskDockTimer").textContent = formatDuration(taskDuration(data));
    updateToolStreamChip(data);
    updateInspectorMetrics(data);
    if (String(data.session_id || "") === state.sessionId && (!data.workspace_path || !state.workspacePath || taskSessionKey(data.session_id, data.workspace_path) === taskSessionKey(state.sessionId, state.workspacePath))) {
      updateSessionStatus(data);
    }
    if (ACTIVE_TASK_STATUSES.has(data.status) && data.task_id) startTaskTimer(data.task_id);
  }
  function updateSessionStatus(data) {
    const badge = $("#sessionLiveBadge");
    const label2 = $("#sessionLiveLabel");
    if (!badge || !label2) return;
    badge.hidden = !data;
    if (!data) {
      label2.textContent = t("inspector.ready");
      return;
    }
    const status = String(data?.status || "running").toLowerCase();
    const terminal = TERMINAL_TASK_STATUSES.has(status);
    badge.dataset.status = terminal ? status : ACTIVE_TASK_STATUSES.has(status) ? status : "running";
    badge.classList.toggle("terminal", terminal);
    badge.classList.toggle("queued", status === "queued");
    label2.textContent = terminal || status === "queued" ? phaseLabel(data) : t("live");
  }
  function liveTaskMarkup(data) {
    const streamText = String(data.stream_text || "");
    const currentPhase = phaseClass(data);
    const transport = data.transport || (data.status === "queued" ? "connecting" : "connected");
    const transportLabel = transport === "polling" ? t("stream.polling") : transport === "reconnecting" ? t("stream.reconnecting") : transport === "connecting" ? t("connection.connecting") : t("stream.connected");
    const preview = streamText ? formatLightText(streamTail(streamText)) : `<span class="stream-empty">${escapeHtml(t("phase.waiting"))}</span>`;
    const restore = data.task_id ? `<button type="button" class="live-restore" data-restore-task="${escapeHtml(data.task_id)}">${escapeHtml(t("restore.action"))}</button>` : "";
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
      ${restore}<details class="live-output"><summary><span>${escapeHtml(state.locale === "zh" ? "\u67E5\u770B\u5B9E\u65F6\u8F93\u51FA" : "Live output")}</span><small data-live-output-count>${escapeHtml(streamText ? `${compactNumber(streamText.length)} ${state.locale === "zh" ? "\u5B57\u7B26\uFF08\u4EC5\u663E\u793A\u6700\u8FD1\u5185\u5BB9\uFF09" : "chars (recent content)"}` : "")}</small><span class="live-output-chevron">${icon("chevron-down")}</span></summary><div class="stream-preview" data-live-preview aria-live="polite">${preview}</div></details>
    </div>
  </div>`;
  }
  function streamTail(text, limit = 800) {
    const value = String(text || "");
    if (value.length <= limit) return value;
    return `${state.locale === "zh" ? "\u2026\u4EC5\u663E\u793A\u6700\u8FD1\u5185\u5BB9\u2026\n" : "\u2026recent content only\u2026\n"}${value.slice(-limit)}`;
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
    const labels = state.locale === "zh" ? {
      run_started: "\u8303\u56F4\u754C\u5B9A",
      node_entered: "\u8FD0\u884C\u8282\u70B9",
      stage_route: "\u9636\u6BB5\u8DEF\u7531",
      local_evidence_index: "\u672C\u5730\u8BC1\u636E",
      reasoning_configured: "\u63A8\u7406\u5F3A\u5EA6",
      image_attached: "\u89C6\u89C9\u8F93\u5165",
      model_decision: "\u6A21\u578B\u51B3\u7B56",
      model_update: "\u6A21\u578B\u884C\u52A8\u8BF4\u660E",
      model_update_history: "\u6B64\u524D\u884C\u52A8\u8BF4\u660E",
      tool_round_started: "\u6267\u884C\u8BA1\u5212",
      tool_round_finished: "\u7ED3\u679C\u6C47\u603B",
      feedback_observed: "\u81EA\u53CD\u9988",
      replan: "\u91CD\u65B0\u89C4\u5212",
      stagnation_replan: "\u505C\u6EDE\u7EA0\u504F",
      recovery_probe_finished: "\u6062\u590D\u8BCA\u65AD",
      recovery_inspection_passed: "\u89E3\u9664\u5199\u5165\u4FDD\u62A4",
      recovery_required_before_finish: "\u6062\u590D\u4FDD\u62A4",
      recovery_guard: "\u6062\u590D\u4FDD\u62A4",
      task_stagnation_recovery: "\u9519\u8BEF\u8DEF\u5F84\u4FEE\u590D",
      verification_required: "\u9A8C\u8BC1\u95E8\u7981",
      verification_observed: "\u9A8C\u8BC1\u8BC1\u636E",
      context_compacted: "\u4E0A\u4E0B\u6587\u538B\u7F29",
      provider_retry: "\u4F20\u8F93\u91CD\u8BD5",
      provider_protocol: "\u8C03\u7528\u534F\u8BAE",
      provider_protocol_fallback: "\u534F\u8BAE\u81EA\u52A8\u56DE\u9000",
      task_provider_recovery: "\u4EFB\u52A1\u6062\u590D",
      reasoning_fallback: "\u53C2\u6570\u964D\u7EA7",
      search_circuit_open: "\u641C\u7D22\u7194\u65AD",
      provider_stream_error: "\u6A21\u578B\u6D41\u9519\u8BEF",
      completion_complete: "\u5B8C\u6210\u8BC4\u4F30\u901A\u8FC7",
      completion_continue: "\u5B8C\u6210\u8BC4\u4F30\u7EE7\u7EED",
      completion_blocked: "\u5B8C\u6210\u8BC4\u4F30\u963B\u585E",
      completion_unknown: "\u5B8C\u6210\u8BC4\u4F30\u4E0D\u53EF\u7528",
      verification_passed: "\u9A8C\u8BC1\u901A\u8FC7",
      verification_failed: "\u9A8C\u8BC1\u5931\u8D25",
      verification_skipped: "\u9A8C\u8BC1\u8DF3\u8FC7",
      verification_blocked: "\u9A8C\u8BC1\u963B\u585E",
      reinspect_required: "\u91CD\u65B0\u68C0\u67E5",
      completion_judge_retry: "\u5B8C\u6210\u8BC4\u4F30\u590D\u67E5",
      run_finished: "\u6267\u884C\u7ED3\u675F",
      stagnation_guard: "\u5FAA\u73AF\u4FDD\u62A4",
      max_turns: "\u8F6E\u6B21\u4E0A\u9650",
      // M8-T556: every code the backend can mint has a name here or the
      // timeline chip reads as "阶段事件". Pinned by
      // tests/frontend_trace_code_one_home_smoke.mjs.
      approval_requested: "\u9700\u8981\u6279\u51C6",
      approval_resolved: "\u6279\u51C6\u5DF2\u88C1\u51B3",
      background_limit_reached: "\u540E\u53F0\u4EFB\u52A1\u5DF2\u8FBE\u4E0A\u9650",
      batch_resume: "\u6279\u91CF\u6062\u590D",
      budget_exceeded: "\u9884\u7B97\u8D85\u9650",
      cancel_requested: "\u5DF2\u8BF7\u6C42\u53D6\u6D88",
      cancelled: "\u5DF2\u53D6\u6D88",
      completion_continue_capped: "\u5B8C\u6210\u8BC4\u4F30\u7EED\u8DD1\u5DF2\u8FBE\u4E0A\u9650",
      completion_judge_rejected: "\u5B8C\u6210\u8BC4\u4F30\u88AB\u9A73\u56DE",
      completion_verdict_repeated: "\u5B8C\u6210\u8BC4\u4F30\u5224\u65AD\u91CD\u590D",
      dependency_aware_repair_scope: "\u4F9D\u8D56\u611F\u77E5\u7684\u4FEE\u590D\u8303\u56F4",
      detached_process_blocked: "\u540E\u53F0\u8FDB\u7A0B\u88AB\u62E6\u622A",
      empty_answer: "\u7A7A\u7B54\u6848",
      hook_blocked_user_prompt: "\u94A9\u5B50\u62E6\u622A\u4E86\u8F93\u5165",
      hook_executed: "\u94A9\u5B50\u5DF2\u6267\u884C",
      mentions_resolved: "\u63D0\u53CA\u5DF2\u89E3\u6790",
      nonterminal_turn: "\u672A\u7EC8\u7ED3\u8F6E\u6B21",
      nonterminal_turn_limit: "\u672A\u7EC8\u7ED3\u8F6E\u6B21\u4E0A\u9650",
      planner_dynamic_ready: "\u52A8\u6001\u89C4\u5212\u5C31\u7EEA",
      planner_execution_finished: "\u89C4\u5212\u6267\u884C\u5B8C\u6210",
      planner_execution_skipped: "\u89C4\u5212\u6267\u884C\u5DF2\u8DF3\u8FC7",
      planner_execution_started: "\u89C4\u5212\u6267\u884C\u5F00\u59CB",
      planner_fixed_fallback: "\u56FA\u5B9A\u89C4\u5212\u56DE\u9000",
      planner_node_finished: "\u89C4\u5212\u8282\u70B9\u5B8C\u6210",
      planner_node_provider_status: "\u89C4\u5212\u8282\u70B9\u6A21\u578B\u72B6\u6001",
      planner_node_started: "\u89C4\u5212\u8282\u70B9\u5F00\u59CB",
      planner_preflight_fallback: "\u89C4\u5212\u9884\u68C0\u56DE\u9000",
      planner_started: "\u89C4\u5212\u5F00\u59CB",
      planner_tool_out_of_scope: "\u89C4\u5212\u5DE5\u5177\u8D8A\u754C",
      protocol_guard: "\u534F\u8BAE\u4FDD\u62A4",
      protocol_repair: "\u534F\u8BAE\u4FEE\u590D",
      provider_reasoning_progress: "\u63A8\u7406\u8FDB\u884C\u4E2D",
      provider_request_retry: "\u8BF7\u6C42\u91CD\u8BD5",
      provider_tool_call_progress: "\u5DE5\u5177\u53C2\u6570\u6D41\u5F0F",
      provider_tool_call_start: "\u5DE5\u5177\u8C03\u7528\u751F\u6210",
      provider_transport_fallback: "\u4F20\u8F93\u56DE\u9000",
      repair_stage_provider: "\u4FEE\u590D\u9636\u6BB5\u6A21\u578B",
      safe_readonly_checkpoint: "\u53EA\u8BFB\u68C0\u67E5\u70B9\u6062\u590D",
      session_checkpoint: "\u4F1A\u8BDD\u68C0\u67E5\u70B9",
      soft_budget_stopped: "\u8F6F\u9884\u7B97\u505C\u6B62",
      soft_budget_wrap_up: "\u8F6F\u9884\u7B97\u6536\u5C3E",
      task_model_fallback: "\u4EFB\u52A1\u6A21\u578B\u56DE\u9000",
      tool_authorized: "\u5DE5\u5177\u5DF2\u6388\u6743",
      tool_history_recovered: "\u5DE5\u5177\u5386\u53F2\u5DF2\u6062\u590D",
      verification_guard: "\u9A8C\u8BC1\u4FDD\u62A4",
      verification_required_before_finish: "\u6536\u5C3E\u524D\u9700\u5148\u9A8C\u8BC1",
      verification_satisfied_by_inspection: "\u68C0\u67E5\u5373\u89C6\u4E3A\u5DF2\u5B8C\u6210\u9A8C\u8BC1",
      verification_waiver_refused_by_failed_read: "\u8C41\u514D\u88AB\u62D2\uFF08\u8BFB\u53D6\u5931\u8D25\uFF09",
      vision_context_restored: "\u89C6\u89C9\u4E0A\u4E0B\u6587\u5DF2\u6062\u590D",
      batch_started: "\u5E76\u884C\u7F16\u6392",
      auto_orchestration_triggered: "\u81EA\u52A8\u7F16\u6392",
      orchestration_parent_resumed: "\u4E3B Agent \u63A5\u7BA1",
      subagent_finished: "\u5B50\u4EFB\u52A1\u5B8C\u6210",
      batch_merge_started: "\u7ED3\u679C\u5408\u5E76",
      batch_finished: "\u6279\u91CF\u4EA4\u4ED8"
    } : {
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
      // M8-T556: every code the backend can mint has a name here or the
      // timeline chip reads as "Stage event". Pinned by
      // tests/frontend_trace_code_one_home_smoke.mjs.
      approval_requested: "Approval needed",
      approval_resolved: "Approval resolved",
      background_limit_reached: "Background task limit",
      batch_resume: "Batch resume",
      budget_exceeded: "Budget exceeded",
      cancel_requested: "Cancel requested",
      cancelled: "Cancelled",
      completion_continue_capped: "Continue capped",
      completion_judge_rejected: "Completion rejected",
      completion_verdict_repeated: "Verdict repeated",
      dependency_aware_repair_scope: "Dependency-aware repair scope",
      detached_process_blocked: "Detached process blocked",
      empty_answer: "Empty answer",
      hook_blocked_user_prompt: "Hook blocked prompt",
      hook_executed: "Hook executed",
      mentions_resolved: "Mentions resolved",
      nonterminal_turn: "Nonterminal turn",
      nonterminal_turn_limit: "Nonterminal turn limit",
      planner_dynamic_ready: "Planner ready",
      planner_execution_finished: "Plan execution finished",
      planner_execution_skipped: "Plan execution skipped",
      planner_execution_started: "Plan execution started",
      planner_fixed_fallback: "Fixed plan fallback",
      planner_node_finished: "Plan node finished",
      planner_node_provider_status: "Plan node status",
      planner_node_started: "Plan node started",
      planner_preflight_fallback: "Preflight fallback",
      planner_started: "Planner started",
      planner_tool_out_of_scope: "Plan tool out of scope",
      protocol_guard: "Protocol guard",
      protocol_repair: "Protocol repair",
      provider_reasoning_progress: "Reasoning in progress",
      provider_request_retry: "Request retry",
      provider_tool_call_progress: "Tool args streaming",
      provider_tool_call_start: "Tool call forming",
      provider_transport_fallback: "Transport fallback",
      repair_stage_provider: "Repair stage provider",
      safe_readonly_checkpoint: "Read-only checkpoint",
      session_checkpoint: "Session checkpoint",
      soft_budget_stopped: "Soft budget stopped",
      soft_budget_wrap_up: "Soft budget wrap up",
      task_model_fallback: "Task model fallback",
      tool_authorized: "Tool authorized",
      tool_history_recovered: "Tool history recovered",
      verification_guard: "Verification guard",
      verification_required_before_finish: "Verify before finish",
      verification_satisfied_by_inspection: "Verified by inspection",
      verification_waiver_refused_by_failed_read: "Waiver refused",
      vision_context_restored: "Vision context restored",
      batch_started: "Parallel orchestration",
      auto_orchestration_triggered: "Auto orchestration",
      orchestration_parent_resumed: "Parent agent resumed",
      subagent_finished: "Subtask finished",
      batch_merge_started: "Result merge",
      batch_finished: "Batch delivery"
    };
    return labels[String(event?.code || "")] || (state.locale === "zh" ? "\u9636\u6BB5\u4E8B\u4EF6" : "Stage event");
  }
  function detailValueText(value, limit = 360) {
    if (value == null) return "";
    if (Array.isArray(value)) {
      if (!value.length) return state.locale === "zh" ? "0 \u9879" : "0 items";
      if (value.every((item) => item == null || ["string", "number", "boolean"].includes(typeof item))) {
        return value.map((item) => String(item ?? "")).join(", ");
      }
      return state.locale === "zh" ? `${value.length} \u9879\u7ED3\u6784\u5316\u8BB0\u5F55` : `${value.length} structured items`;
    }
    if (typeof value === "object") {
      const pairs = Object.entries(value).slice(0, 3).map(([key, item]) => `${key}: ${detailValueText(item, 80)}`);
      return `{ ${pairs.join("; ")}${Object.keys(value).length > 3 ? "; \u2026" : ""} }`;
    }
    const text = String(value).replace(/\s+/g, " ").trim();
    return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}\u2026` : text;
  }
  function detailJson(value, limit = 12e3) {
    let raw;
    try {
      raw = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    } catch {
      raw = String(value ?? "");
    }
    raw = String(raw || "");
    return raw.length > limit ? `${raw.slice(0, limit).trimEnd()}
\u2026 ${state.locale === "zh" ? "\u8BE6\u60C5\u5DF2\u622A\u65AD" : "details truncated"} \u2026` : raw;
  }
  function structuredDetailMarkup(detail, label2 = state.locale === "zh" ? "\u67E5\u770B\u7ED3\u6784\u5316\u4F9D\u636E" : "View structured evidence") {
    if (detail == null || typeof detail === "object" && !Object.keys(detail).length) return "";
    const raw = detailJson(detail);
    return `<details class="event-detail"><summary>${escapeHtml(label2)}<small>${escapeHtml(state.locale === "zh" ? "\u70B9\u51FB\u5C55\u5F00" : "click to expand")}</small></summary><pre>${escapeHtml(raw)}</pre></details>`;
  }
  function traceDetailPreview(event) {
    const detail = event?.detail;
    if (detail == null) return "";
    if (typeof detail !== "object" || Array.isArray(detail)) return detailValueText(detail, 96);
    const labels = state.locale === "zh" ? { turn: "\u8F6E\u6B21", previous_turn: "\u4E0A\u4E00\u8F6E", tool_count: "\u5DE5\u5177", results: "\u7ED3\u679C", observed: "\u5DF2\u89C2\u5BDF", observations: "\u89C2\u5BDF", constraints: "\u7EA6\u675F", failed_tools: "\u5931\u8D25", verification_required: "\u9700\u9A8C\u8BC1", recovery_inspection_required: "\u5199\u5165\u4FDD\u62A4", assessment: "\u53CD\u9988", trigger: "\u89E6\u53D1", next_action: "\u4E0B\u4E00\u6B65" } : { turn: "turn", previous_turn: "previous", tool_count: "tools", results: "results", observed: "observed", observations: "observations", constraints: "constraints", failed_tools: "failed", verification_required: "verify", recovery_inspection_required: "write guard", assessment: "assessment", trigger: "trigger", next_action: "next" };
    const parts = [];
    for (const key of Object.keys(labels)) {
      const value = detail[key];
      if (value == null || value === "") continue;
      const compact = Array.isArray(value) ? state.locale === "zh" ? `${value.length} \u9879` : `${value.length} items` : detailValueText(value, 96);
      if (compact) parts.push(`${labels[key] || key}: ${compact}`);
    }
    return parts.slice(0, 4).join(" \xB7 ");
  }
  function traceEvidenceMarkup(event, detailText, evidenceMarkup) {
    if (detailText == null && !evidenceMarkup) return "";
    const labels = state.locale === "zh" ? { feedback_observed: "\u67E5\u770B\u81EA\u53CD\u9988\u8BE6\u60C5", tool_round_finished: "\u67E5\u770B\u7ED3\u679C\u6C47\u603B\u8BE6\u60C5", replan: "\u67E5\u770B\u91CD\u65B0\u89C4\u5212\u8BE6\u60C5", model_decision: "\u67E5\u770B\u6A21\u578B\u51B3\u7B56\u8BE6\u60C5" } : { feedback_observed: "View self-feedback", tool_round_finished: "View merged results", replan: "View re-plan", model_decision: "View model decision" };
    const label2 = labels[String(event?.code || "")] || (state.locale === "zh" ? "\u67E5\u770B\u9636\u6BB5\u8BE6\u60C5" : "View stage details");
    const preview = traceDetailPreview(event);
    const readable = detailText ? `<div class="trace-detail">${escapeHtml(detailText)}</div>` : "";
    return `<details class="trace-evidence"><summary><span>${escapeHtml(label2)}</span><small>${escapeHtml(preview)}</small><span class="trace-evidence-chevron">${icon("chevron-down")}</span></summary><div class="trace-evidence-body">${readable}${evidenceMarkup || ""}</div></details>`;
  }
  function toolResultFoldMarkup(label2, content) {
    return `<details class="tool-result-fold"><summary><span>${escapeHtml(label2)}</span><small>${escapeHtml(state.locale === "zh" ? "\u70B9\u51FB\u5C55\u5F00" : "click to expand")}</small><span class="tool-result-fold-chevron">${icon("chevron-down")}</span></summary><div class="tool-result-fold-body">${content}</div></details>`;
  }
  function traceDetail(event, options = {}) {
    const detail = event?.detail;
    if (detail == null) return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detailValueText(detail);
    if (typeof detail !== "object") return String(detail);
    const parts = [];
    if (!options.omitText && typeof detail.text === "string" && detail.text) parts.push(detail.text);
    const labels = state.locale === "zh" ? {
      turn: "\u8F6E\u6B21",
      previous_turn: "\u4E0A\u4E00\u8F6E",
      tool_count: "\u5DE5\u5177\u6570",
      tools: "\u5DE5\u5177",
      answer_chars: "\u56DE\u7B54\u5B57\u7B26",
      duration_ms: "\u8017\u65F6",
      duration_seconds: "\u8017\u65F6",
      count: "\u6570\u91CF",
      names: "\u540D\u79F0",
      statuses: "\u72B6\u6001",
      max_turns: "\u8F6E\u6B21\u4E0A\u9650",
      turn_policy: "\u8F6E\u6B21\u7B56\u7565",
      child_count: "\u5B50\u4EFB\u52A1\u6570",
      child: "\u5B50\u4EFB\u52A1",
      failed: "\u5931\u8D25\u6570",
      retry: "\u91CD\u8BD5",
      retry_limit: "\u91CD\u8BD5\u4E0A\u9650",
      partial_chars: "\u5DF2\u8F93\u51FA\u5B57\u7B26",
      error_type: "\u9519\u8BEF\u7C7B\u578B",
      requested: "\u8BF7\u6C42",
      active: "\u5B9E\u9645",
      wire_value: "\u8BF7\u6C42\u503C",
      task_id: "\u4EFB\u52A1",
      tokens: "tokens",
      automatic: "\u81EA\u52A8",
      complexity_score: "\u590D\u6742\u5EA6",
      complexity_threshold: "\u89E6\u53D1\u7EBF",
      complexity_reasons: "\u89E6\u53D1\u539F\u56E0",
      attempt: "\u8BC4\u4F30\u6B21\u6570",
      confidence: "\u7F6E\u4FE1\u5EA6",
      rationale: "\u4F9D\u636E",
      missing: "\u7F3A\u5931",
      next_action: "\u4E0B\u4E00\u6B65",
      evidence: "\u8BC1\u636E",
      error: "\u9519\u8BEF",
      trigger: "\u89E6\u53D1\u539F\u56E0",
      observed: "\u5DF2\u89C2\u5BDF",
      observations: "\u89C2\u5BDF\u7ED3\u679C",
      constraints: "\u5F53\u524D\u7EA6\u675F",
      basis: "\u5224\u65AD\u4F9D\u636E",
      public_plan: "\u516C\u5F00\u8BA1\u5212",
      results: "\u5DE5\u5177\u7ED3\u679C",
      structured_data: "\u7ED3\u6784\u5316\u7ED3\u679C",
      new_information: "\u65B0\u4FE1\u606F",
      failed_tools: "\u5931\u8D25\u5DE5\u5177",
      needs_repair: "\u9700\u8981\u4FEE\u590D",
      verification_required: "\u9700\u8981\u9A8C\u8BC1",
      recovery_inspection_required: "\u5199\u5165\u4FDD\u62A4",
      assessment: "\u53CD\u9988\u5224\u65AD",
      replan_trigger: "\u91CD\u89C4\u5212\u89E6\u53D1",
      parallel_mode: "\u5E76\u884C\u6A21\u5F0F",
      max_concurrency: "\u5E76\u53D1\u5EA6",
      dependency_shape: "\u4F9D\u8D56\u7ED3\u6784",
      merge_strategy: "\u5408\u5E76\u7B56\u7565",
      parallel_results: "\u5E76\u884C\u7ED3\u679C",
      merge_basis: "\u5408\u5E76\u4F9D\u636E",
      result_summary: "\u7ED3\u679C\u6458\u8981",
      turns: "\u8F6E\u6B21",
      tool_calls: "\u5DE5\u5177\u8C03\u7528"
    } : {
      turn: "turn",
      previous_turn: "previous turn",
      tool_count: "tools",
      tools: "tools",
      answer_chars: "answer chars",
      duration_ms: "duration",
      duration_seconds: "duration",
      count: "count",
      names: "names",
      statuses: "statuses",
      max_turns: "turn limit",
      turn_policy: "turn policy",
      child_count: "children",
      child: "child",
      failed: "failed",
      retry: "retry",
      retry_limit: "retry limit",
      partial_chars: "partial chars",
      error_type: "error type",
      requested: "requested",
      active: "active",
      wire_value: "wire",
      task_id: "task",
      tokens: "tokens",
      automatic: "automatic",
      complexity_score: "complexity",
      complexity_threshold: "threshold",
      complexity_reasons: "reasons",
      attempt: "review attempt",
      confidence: "confidence",
      rationale: "rationale",
      missing: "missing",
      next_action: "next action",
      evidence: "evidence",
      error: "error",
      trigger: "trigger",
      observed: "observed",
      observations: "observations",
      constraints: "constraints",
      basis: "basis",
      public_plan: "public plan",
      results: "tool results",
      structured_data: "structured evidence",
      new_information: "new information",
      failed_tools: "failed tools",
      needs_repair: "needs repair",
      verification_required: "verification required",
      recovery_inspection_required: "write guard",
      assessment: "assessment",
      replan_trigger: "re-plan trigger",
      parallel_mode: "parallel mode",
      max_concurrency: "concurrency",
      dependency_shape: "dependency shape",
      merge_strategy: "merge strategy",
      parallel_results: "parallel results",
      merge_basis: "merge basis",
      result_summary: "result summary",
      turns: "turns",
      tool_calls: "tool calls"
    };
    for (const key of Object.keys(labels)) {
      if (detail[key] == null) continue;
      parts.push(`${labels[key] || key}: ${detailValueText(detail[key])}`);
    }
    return parts.join(" \xB7 ");
  }
  function shortEventText(event, limit = 150) {
    const publicUpdate = event?.code === "model_update" && typeof event?.detail?.text === "string" ? event.detail.text : "";
    const text = String(publicUpdate || event?.summary || traceDetail(event) || "").replace(/\s+/g, " ").trim();
    return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}\u2026` : text;
  }
  function rawOutputMarkup(streamText) {
    const text = streamTail(String(streamText || ""), 1200);
    return text ? `<details class="raw-output"><summary>${escapeHtml(state.locale === "zh" ? "\u539F\u59CB\u6A21\u578B\u8F93\u51FA" : "Raw model output")}</summary><div>${formatLightText(text)}</div></details>` : "";
  }
  function isToolEvent(event) {
    return event?.kind === "tool" || event?.name && event?.kind !== "trace";
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
    const updateIndexes = visible.map((event, index) => event?.code === "model_update" ? index : -1).filter((index) => index >= 0);
    if (updateIndexes.length <= 1) return visible;
    const latestIndex = updateIndexes[updateIndexes.length - 1];
    const firstIndex = updateIndexes[0];
    const previousUpdates = updateIndexes.slice(0, -1).map((index) => String(visible[index]?.detail?.text || "").trim()).filter(Boolean);
    const historyEvent = {
      ...visible[firstIndex],
      code: "model_update_history",
      summary: state.locale === "zh" ? `\u6B64\u524D\u884C\u52A8\u8BF4\u660E \xB7 ${previousUpdates.length} \u6761` : `Earlier action updates \xB7 ${previousUpdates.length}`,
      detail: { count: previousUpdates.length, updates: previousUpdates }
    };
    return visible.filter((_event, index) => !updateIndexes.includes(index) || index === firstIndex || index === latestIndex).map((event, index, compacted) => {
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
    return state.locale === "zh" ? `${tools} \u6B21\u64CD\u4F5C${alerts ? ` \xB7 ${alerts} \u9879\u9700\u5173\u6CE8` : ""}` : `${tools} actions${alerts ? ` \xB7 ${alerts} alerts` : ""}`;
  }
  function summarizeRound(items, roundNumber) {
    const tools = items.filter(isToolEvent);
    const failed = tools.some((event) => ["error", "failed", "denied"].includes(String(event.status || "").toLowerCase()));
    const names = [...new Set(tools.map((event) => String(event.name || "tool")).filter(Boolean))];
    const detail = names.slice(0, 4).join(" \xB7 ") || (state.locale === "zh" ? "\u6574\u7406\u6267\u884C\u6B65\u9AA4" : "Organized execution steps");
    return { failed, detail, title: state.locale === "zh" ? `\u7B2C ${roundNumber} \u7EC4\u547D\u4EE4 \xB7 ${tools.length} \u6761` : `Command group ${roundNumber} \xB7 ${tools.length} commands`, status: failed ? state.locale === "zh" ? "\u9700\u5904\u7406" : "Needs attention" : state.locale === "zh" ? "\u5DF2\u5B8C\u6210" : "Complete" };
  }
  function toolResultMarkup(event) {
    const output = String(event.output || "").trim();
    const observation = String(event.observation || "").trim();
    const data = event.data && typeof event.data === "object" ? event.data : null;
    const metadata = [
      event.risk ? `${state.locale === "zh" ? "\u98CE\u9669" : "risk"}: ${event.risk}` : "",
      event.exit_code != null ? `exit ${event.exit_code}` : "",
      event.duration_ms != null ? `${Number(event.duration_ms).toFixed(1)} ms` : "",
      event.truncated ? state.locale === "zh" ? "\u8F93\u51FA\u5DF2\u622A\u65AD" : "output truncated" : "",
      event.write ? state.locale === "zh" ? "\u5DF2\u5199\u5165\u5DE5\u4F5C\u533A" : "workspace write" : "",
      Array.isArray(event.security_tags) && event.security_tags.length ? event.security_tags.join(", ") : ""
    ].filter(Boolean);
    const metadataMarkup = metadata.length ? `<div class="tool-result-meta">${metadata.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : "";
    const observationMarkup = observation ? toolResultFoldMarkup(t("tool.observation"), `<div class="tool-result-observation">${formatText(observation)}</div>`) : "";
    const outputMarkup = output ? toolResultFoldMarkup(t("tool.result"), `<div class="tool-result-output">${formatText(output)}</div>`) : `<div class="tool-result-empty">${escapeHtml(t("tool.empty"))}</div>`;
    const commandMarkup = event.command ? toolResultFoldMarkup(state.locale === "zh" ? "\u6267\u884C\u547D\u4EE4" : "Command", `<code class="tool-command">${escapeHtml(event.command)}</code>`) : "";
    const dataMarkup = data && Object.keys(data).length ? toolResultFoldMarkup(t("tool.structured"), `<pre class="tool-result-json">${escapeHtml(detailJson(data, 1e4))}</pre>`) : "";
    const results = Array.isArray(data?.results) ? data.results : [];
    const resultMarkup = results.length ? toolResultFoldMarkup(t("tool.searchResults"), `<div class="web-results">${results.map((result) => {
      const href = safeExternalUrl(result.url);
      return href ? `<a class="web-result" href="${escapeHtml(href)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(result.title || result.url)}</strong><small>${escapeHtml(result.snippet || result.url)}</small><span>${escapeHtml(t("tool.openSource"))} \u2197</span></a>` : "";
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
      const tracePhase = event.phase;
      const isModelEvent = String(event.code || "") === "model_update";
      const summary = isModelEvent && event.code === "model_update" ? state.locale === "zh" ? `\u884C\u52A8\u8BF4\u660E \xB7 \u7B2C ${event.detail?.turn || ""} \u8F6E` : `Action \xB7 turn ${event.detail?.turn || ""}` : String(event.summary || traceLabel(event));
      const publicMarkup = publicText ? `<div class="trace-public-plan"><span>${escapeHtml(state.locale === "zh" ? "\u516C\u5F00\u884C\u52A8" : "Public action")}</span><div>${formatText(publicText)}</div></div>` : "";
      const evidence = structuredDetailMarkup(event.detail, state.locale === "zh" ? "\u67E5\u770B\u5B8C\u6574\u4F9D\u636E" : "View full evidence");
      const detailMarkup = traceEvidenceMarkup(event, detail, evidence);
      const thinkingLabel = state.locale === "zh" ? "\u601D\u8003" : "Thinking";
      const blockClass = isModelEvent ? "thinking-block " : "";
      const historyClass = String(event.code || "") === "model_update_history" ? " thinking-history" : "";
      const traceAnchor = event.item_id || event.event_id || (event.sequence ? `sequence-${event.sequence}` : "") || anchor || `${event.code || "stage"}-${event.created_at_epoch || ""}`;
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
    const toolAnchor = event.item_id || event.event_id || (event.sequence ? `sequence-${event.sequence}` : "") || anchor || `${name}-${event.created_at_epoch || ""}`;
    return `<details class="tool-event ${stateClass}${animate ? " event-enter" : ""}" data-agent-block="command" data-agent-item="${escapeHtml(toolAnchor)}" data-item-kind="command" data-tool-event="${escapeHtml(toolAnchor)}"${open ? " open" : ""}>
    <summary class="tool-event-summary"><span class="tool-icon ${denied ? "amber-icon" : ""}">${icon(iconName)}</span><span class="tool-event-copy"><span><strong>${escapeHtml(name)}</strong>${pathMarkup}</span><small>${escapeHtml(event.summary || "")}</small></span><span class="tool-check ${denied ? "denied-check" : failed ? "failed-check" : ""}">${icon(stateIcon)}</span><span class="tool-expand">${icon("chevron-down")}</span></summary>
    ${toolResultMarkup(event)}
  </details>`;
  }
  function eventTimelineMarkup(events, options = {}) {
    if (!Array.isArray(events) || !events.length) return "";
    const sourceEvents = events.length > MAX_RENDERED_TIMELINE_EVENTS ? [
      {
        kind: "trace",
        code: "timeline_truncated",
        phase: "planning",
        status: "ok",
        summary: state.locale === "zh" ? `\u8F83\u65E9\u7684 ${events.length - MAX_RENDERED_TIMELINE_EVENTS + 1} \u6761\u8FD0\u884C\u8BB0\u5F55\u5DF2\u6536\u8D77` : `${events.length - MAX_RENDERED_TIMELINE_EVENTS + 1} earlier runtime records folded`,
        detail: { count: events.length - MAX_RENDERED_TIMELINE_EVENTS + 1 }
      },
      ...events.slice(-(MAX_RENDERED_TIMELINE_EVENTS - 1))
    ] : events;
    const hiddenRoutineTraceCodes = /* @__PURE__ */ new Set(["model_decision", "tool_round_finished", "feedback_observed", "replan"]);
    const items = compactModelUpdateEvents(sourceEvents).filter((event) => !hiddenRoutineTraceCodes.has(String(event?.code || ""))).map((event, index) => ({ event, index }));
    const groups = [];
    let currentRound = null;
    let fallbackRound = 0;
    let pendingRound = 0;
    const closeRound = () => {
      if (currentRound) {
        groups.push(currentRound);
        currentRound = null;
      }
    };
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
      const commandGroupLabel = state.locale === "zh" ? "\u547D\u4EE4\u7EC4" : "Commands";
      return `<details class="agent-round command-group" data-agent-block="commands" data-agent-item="round-${escapeHtml(roundKey)}" data-item-kind="command-group" data-command-group="${roundKey}" data-agent-round="${roundKey}"${open ? " open" : ""}><summary class="agent-round-summary"><span class="agent-round-title"><span class="agent-round-icon">${icon(round.failed ? "alert-circle" : "layers-3")}</span><span class="command-group-copy"><span class="command-group-label">${escapeHtml(commandGroupLabel)}</span><strong>${escapeHtml(round.title)}</strong><small>${escapeHtml(round.detail)}</small></span></span><span class="agent-round-meta">${escapeHtml(round.status)}<span class="agent-round-chevron">${icon("chevron-down")}</span></span></summary><div class="agent-round-events">${itemMarkup}</div></details>`;
    }).join("");
  }
  function assistantMessageMarkup(data, anchor = "") {
    const events = Array.isArray(data.events) ? data.events : [];
    const eventMarkup = eventTimelineMarkup(events);
    const answer = data.answer || data.error || (state.locale === "zh" ? "\u6A21\u578B\u6CA1\u6709\u8FD4\u56DE\u53EF\u4EA4\u4ED8\u6587\u5B57\u3002" : "The model returned no deliverable text.");
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
      activateDialog(modal, { initialFocus: "#authTokenInput" });
    }
  }
  function hideAuthModal() {
    const modal = $("#authModal");
    if (!modal) return;
    deactivateDialog(modal);
    modal.classList.remove("show");
    modal.setAttribute("aria-hidden", "true");
  }
  async function submitAuthToken(event) {
    event.preventDefault();
    const input = $("#authTokenInput");
    if (!(input instanceof HTMLInputElement)) return;
    const token = input.value.trim();
    if (!token) {
      showAuthModal(state.locale === "zh" ? "\u8BF7\u7C98\u8D34 minicc-web \u542F\u52A8\u65F6\u663E\u793A\u7684 token\u3002" : "Paste the token printed by minicc-web.");
      return;
    }
    localStorage.setItem(AUTH_STORAGE_KEY, token);
    const check = await fetch("/api/workspace", {
      headers: { Authorization: `Bearer ${token}` }
    }).catch(() => null);
    if (!check || !check.ok) {
      showAuthModal(state.locale === "zh" ? "Token \u5DF2\u4FDD\u5B58\u4F46\u9A8C\u8BC1\u672A\u901A\u8FC7\uFF0C\u8BF7\u68C0\u67E5\u540E\u91CD\u65B0\u7C98\u8D34\u3002" : "Token saved but rejected. Check it and retry.");
      return;
    }
    hideAuthModal();
    location.reload();
  }

  // web/src/chat/markdown.js
  function escapeHtml(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }
  var markdownVendorWarned = false;
  function markdownVendorReady() {
    if (typeof marked !== "undefined") return true;
    if (!markdownVendorWarned) {
      markdownVendorWarned = true;
      console.warn("[minicc] web/vendor marked/highlight.js unavailable; using the lightweight fallback renderer.");
    }
    return false;
  }
  function escapeMarkdownSource(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;");
  }
  function decodeMarkdownEntities(value) {
    return String(value ?? "").replaceAll("&#039;", "'").replaceAll("&#39;", "'").replaceAll("&quot;", '"').replaceAll("&lt;", "<").replaceAll("&gt;", ">").replaceAll("&amp;", "&");
  }
  function safeMarkdownUrl(href) {
    const value = String(href || "").trim();
    if (!value) return "";
    if (value.startsWith("#")) return value;
    if (!/^[a-z][a-z0-9+.-]*:/i.test(value)) return value;
    return /^(https?:|mailto:)/i.test(value) ? value : "";
  }
  function highlightFencedCode(code, language) {
    const source = decodeMarkdownEntities(code);
    if (typeof hljs !== "undefined") {
      try {
        if (language && hljs.getLanguage(language)) {
          return hljs.highlight(source, { language, ignoreIllegals: true }).value;
        }
        if (!language && source.length <= 2e4) {
          return hljs.highlightAuto(source).value;
        }
      } catch {
      }
    }
    return escapeHtml(source);
  }
  function configureMarkdownEngine() {
    if (typeof marked === "undefined" || configureMarkdownEngine.ready) return;
    configureMarkdownEngine.ready = true;
    const tokenOf = (value) => value && typeof value === "object" ? value : null;
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
            const label2 = token ? typeof this?.parser?.parseInline === "function" ? this.parser.parseInline(token.tokens || []) : escapeHtml(token.text || "") : escapeHtml(text ?? "");
            if (!href) return label2;
            return `<a href="${escapeHtml(href)}"${title ? ` title="${escapeHtml(title)}"` : ""} target="_blank" rel="noreferrer noopener">${label2}</a>`;
          },
          image(tokenOrHref, titleOrTitle, text) {
            const token = tokenOf(tokenOrHref);
            const href = safeMarkdownUrl(String(token ? token.href : tokenOrHref || ""));
            const alt = String(token ? token.text : text ?? "");
            const title = token ? token.title : titleOrTitle;
            if (!href) return escapeHtml(alt);
            return `<img src="${escapeHtml(href)}" alt="${escapeHtml(alt)}"${title ? ` title="${escapeHtml(title)}"` : ""} loading="lazy" />`;
          }
        }
      });
    } catch {
    }
  }
  function renderMarkdown(source) {
    configureMarkdownEngine();
    return marked.parse(source, { async: false, gfm: true, breaks: true });
  }
  function formatText(value) {
    const source = String(value ?? "");
    if (!markdownVendorReady()) return formatLightText(source);
    try {
      return renderMarkdown(escapeMarkdownSource(source));
    } catch {
      return formatLightText(source);
    }
  }
  function formatLightText(value) {
    const codeBlocks = [];
    let formatted = escapeHtml(value).replace(/```([\s\S]*?)```/g, (_match, code) => {
      const token = `__MINICC_CODE_BLOCK_${codeBlocks.length}__`;
      codeBlocks.push(`<pre><code>${code}</code></pre>`);
      return token;
    });
    formatted = formatted.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/^-\s+/gm, "&bull; ").replace(/\n/g, "<br />");
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
      const preview = dataUrl ? `<img src="${escapeHtml(dataUrl)}" alt="${escapeHtml(name)}" />` : `<span class="attachment-placeholder">${icon("image")}</span>`;
      const remove = item.id ? `<button type="button" class="attachment-remove" data-remove-attachment="${escapeHtml(item.id)}" aria-label="Remove ${escapeHtml(name)}" title="Remove">${icon("x")}</button>` : "";
      return `<div class="image-attachment">${preview}<span class="image-attachment-copy"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(formatBytes(item.size_bytes))}</small></span>${remove}</div>`;
    }).join("")}</div>`;
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
    let remaining = source.length;
    while (holder.firstChild && remaining > MAX_SESSION_VIEW_CHARS) {
      const node = holder.firstChild;
      remaining -= node.nodeType === 1 ? node.outerHTML.length : (node.textContent || "").length;
      node.remove();
    }
    const compacted = holder.innerHTML;
    return compacted.length <= MAX_SESSION_VIEW_CHARS ? compacted : "";
  }
  function cacheSessionView(sessionId, markup, workspacePath = state.workspacePath) {
    const cacheKey = sessionViewKey(sessionId, workspacePath);
    const compacted = compactSessionMarkup(markup);
    if (compacted) sessionMarkup.set(cacheKey, compacted);
    else sessionMarkup.delete(cacheKey);
    storeSessionMarkup(cacheKey, compacted);
  }
  function persistSessionView(sessionId = state.sessionId, workspacePath = state.workspacePath) {
    const messageList = $("#messageList");
    if (!messageList) return;
    cacheSessionView(sessionId, messageList.innerHTML, workspacePath);
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
    }
    return null;
  }
  function emptySessionMarkup() {
    return `<div class="empty-session"><span class="empty-mark" aria-hidden="true">${icon("sparkles")}</span><strong>${escapeHtml(t("session.emptyTitle"))}</strong><span>${escapeHtml(t("session.emptyHint"))}</span><div class="empty-actions">${["explore", "fix", "verify"].map((key) => `<button type="button" data-start-action="${key}"><strong>${escapeHtml(t(`start.${key}`))}</strong><span>${escapeHtml(t(`start.${key}Hint`))}</span>${icon("arrow-up-right")}</button>`).join("")}</div></div>`;
  }
  function presetMessageMarkup(sessionId) {
    return emptySessionMarkup();
  }
  function executionTrailMarkup(eventMarkup, events) {
    if (!eventMarkup) return "";
    const expandLabel = t("tool.expandAll");
    const collapseLabel = t("tool.collapseAll");
    return `<section class="execution-trail" data-agent-timeline data-agent-thread="local"><div class="execution-trail-head"><div class="execution-trail-title"><span class="execution-trail-icon">${icon("list-checks")}</span><span><strong>${escapeHtml(state.locale === "zh" ? "\u6267\u884C\u8109\u7EDC\u4E0E\u8BC1\u636E" : "Execution trail and evidence")}</strong><small>${escapeHtml(eventTimelineSummary(events))}</small></span></div><div class="execution-trail-actions"><button type="button" class="timeline-control" data-timeline-toggle="expand" aria-label="${escapeHtml(expandLabel)}" title="${escapeHtml(expandLabel)}">${icon("chevrons-down")}<span>${escapeHtml(expandLabel)}</span></button><button type="button" class="timeline-control" data-timeline-toggle="collapse" aria-label="${escapeHtml(collapseLabel)}" title="${escapeHtml(collapseLabel)}">${icon("chevrons-up")}<span>${escapeHtml(collapseLabel)}</span></button></div></div><div class="tool-timeline">${eventMarkup}</div></section>`;
  }
  function taskHistoryMarkup(task) {
    const prompt = task.prompt || task.preview || "";
    const answer = task.answer || task.error || (state.locale === "zh" ? "\u4EFB\u52A1\u6CA1\u6709\u8FD4\u56DE\u53EF\u4EA4\u4ED8\u6587\u5B57\u3002" : "No answer yet, waiting for model response.");
    const rawStream = !task.answer && task.stream_text ? rawOutputMarkup(task.stream_text) : "";
    const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
    const taskAnchor = escapeHtml(`task-${task.task_id || task.created_at || prompt.slice(0, 40)}`);
    const attachments = attachmentMarkup(task.attachments || []);
    const batchSummary = task.task_kind === "batch" && Array.isArray(task.children) ? `<div class="batch-child-summary"><div class="batch-child-heading"><strong>${escapeHtml(state.locale === "zh" ? "\u5206\u5C42\u5E76\u884C\u7ED3\u679C" : "Layered parallel results")}</strong><small>${escapeHtml(state.locale === "zh" ? "\u53EA\u8BFB\u5B50\u4EFB\u52A1\u5E76\u884C \u2192 \u4E3B Agent \u5408\u5E76\u4E0E\u590D\u6838" : "Readonly children in parallel -> parent merge and review")}</small></div>${task.children.map((child, index) => {
      const metrics = child.metrics && typeof child.metrics === "object" ? child.metrics : {};
      const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
      const answer2 = String(child.answer || child.error || child.stream_text || "").replace(/\s+/g, " ").trim();
      const evidence = (Array.isArray(child.events) ? child.events : []).filter((event) => event?.summary).slice(-2).map((event) => event.summary).join("\uFF1B");
      return `<details class="batch-child"><summary><span class="task-state ${child.status === "completed" ? "success" : RESUMABLE_TASK_PHASES.has(child.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(`${t("batch.task")} ${index + 1}`)}</strong><small>${escapeHtml(`${phaseLabel(child)} \xB7 ${budget.turns || 0} turns \xB7 ${budget.tool_calls || 0} tools`)}</small><span class="batch-child-chevron">${icon("chevron-down")}</span></summary><div class="batch-child-detail">${answer2 ? `<p>${escapeHtml(answer2.slice(0, 900))}</p>` : ""}${evidence ? `<small>${escapeHtml(evidence.slice(0, 700))}</small>` : ""}</div></details>`;
    }).join("")}</div>` : "";
    const execution = executionTrailMarkup(events, task.events || []);
    return `<article class="message user-message" data-chat-anchor="${taskAnchor}-prompt"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(task.created_at || t("message.now"))}</time><button type="button" class="rewind-to-here" data-user-index="0">${escapeHtml(t("rewind.toHere"))}</button></div><div class="message-body"><div class="message-text">${formatText(prompt)}</div>${attachments}</div></article><article class="message assistant-message" data-chat-anchor="${taskAnchor}-answer"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>${escapeHtml(task.finished_at || task.created_at || t("message.now"))}</time></div><div class="message-body"><div class="history-result-head"><span class="task-state ${task.status === "completed" ? "success" : RESUMABLE_TASK_PHASES.has(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div>${execution}<div class="answer-callout">${formatText(answer)}</div>${batchSummary}${rawStream}</div></article>`;
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
      Array.isArray(task?.events) ? task.events.length : Number(task?.event_count || 0)
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
      const scope = captureViewScope();
      const load = requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12e3).then((task) => {
        if (!isWorkspaceScopeCurrent(scope)) return task;
        cacheTaskDetail(task);
        const items = taskHistoryListBySession.get(sessionId) || [];
        const merged = items.map((item) => item.task_id === task.task_id ? task : item);
        if (!merged.some((item) => item.task_id === task.task_id)) merged.unshift(task);
        taskHistoryListBySession.set(sessionId, merged);
        taskHistoryBySession.set(sessionId, task);
        if (state.sessionId === sessionId && !isSessionBusy(sessionId)) renderSession(sessionId);
        return task;
      }).finally(() => {
        if (taskDetailLoads.get(taskId) === load) taskDetailLoads.delete(taskId);
      });
      taskDetailLoads.set(taskId, load);
    }
    return taskDetailLoads.get(taskId);
  }
  function renderSession(sessionId, options = {}) {
    const scope = captureViewScope();
    const area = $("#chatArea");
    const chatPosition = captureChatPosition(area);
    if (chatPosition && options.followLatest === true) chatPosition.followLatest = true;
    const history = taskHistoryBySession.get(sessionId);
    const historyItems = taskHistoryListBySession.get(sessionId);
    const defaultTitle = state.locale === "zh" ? "\u65B0\u4EFB\u52A1" : "New task";
    const defaultSubtitle = state.locale === "zh" ? "\u4E3A\u4E0B\u4E00\u6B21\u4FEE\u6539\u51C6\u5907\u4E00\u4E2A\u5E72\u51C0\u4E0A\u4E0B\u6587\u3002" : "A clean context for the next change.";
    $("#sessionTitle").textContent = history ? String(history.preview || history.prompt || defaultTitle).slice(0, 72) : defaultTitle;
    $("#sessionSubtitle").textContent = history ? phaseLabel(history) : defaultSubtitle;
    const markup = history && !history.summary_only ? taskHistoryListMarkup(historyItems?.length ? historyItems : [history]) : cachedSessionView(sessionId) || emptySessionMarkup();
    if (markup) $("#messageList").innerHTML = markup;
    decorateUserRewindButtons();
    updateSessionStatus(history);
    renderVerification(history || null);
    if (history) renderedHistoryKeys.set(sessionId, taskHistoryKey(historyItems?.length ? historyItems : history));
    else renderedHistoryKeys.delete(sessionId);
    const todoSource = historyItems?.length ? [...historyItems].reverse() : history ? [history] : [];
    runtime.latestTodos = latestTodosFromEvents(todoSource.flatMap((item) => Array.isArray(item?.events) ? item.events : []));
    renderTodoPanel();
    refreshIcons();
    restoreChatPosition(chatPosition);
    window.requestAnimationFrame(() => {
      if (isViewScopeCurrent(scope)) restoreSessionTask(sessionId);
    });
  }
  function taskDotClass(status) {
    if (status === "completed") return "mint";
    if (RESUMABLE_TASK_PHASES.has(status)) return "amber";
    return "coral";
  }
  function renderTaskHistory(tasks) {
    const list = $("#threadList");
    if (!list) return;
    const previousScrollTop = list.scrollTop;
    const wasAtTop = previousScrollTop <= 4;
    const normalizedTasks = Array.isArray(tasks) ? tasks.map((task) => {
      const cached = taskDetailsById.get(task?.task_id);
      return cached ? { ...cached, ...task, summary_only: false } : task;
    }) : [];
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
        const detail = `${status} \xB7 ${task.task_id || ""}`;
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
    const currentHistory = taskHistoryBySession.get(state.sessionId);
    if (currentHistory?.summary_only && currentHistory.task_id) {
      hydrateTaskForSession(currentHistory.task_id, state.sessionId).catch(() => {
      });
    } else if (currentHistory && !isSessionBusy(state.sessionId) && renderedHistoryKeys.get(state.sessionId) !== taskHistoryKey(taskHistoryListBySession.get(state.sessionId) || currentHistory)) {
      renderSession(state.sessionId);
    }
    if (listChanged) {
      refreshIcons();
      window.requestAnimationFrame(() => {
        list.scrollTop = wasAtTop ? 0 : Math.min(previousScrollTop, Math.max(0, list.scrollHeight - list.clientHeight));
      });
    }
  }
  function loadTaskHistory() {
    const path = state.workspacePath;
    const version = runtime.workspaceVersion;
    const pending3 = runtime.historyPending;
    if (pending3?.path === path && pending3.version === version) return pending3.promise;
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
      } finally {
        if (runtime.historyPending?.request === request) runtime.historyPending = null;
      }
    })();
    runtime.historyPending = { path, version, request, promise };
    return promise;
  }

  // web/src/core/locale.js
  function applyLocale() {
    document.documentElement.lang = state.locale === "zh" ? "zh-CN" : "en";
    $$(`[data-i18n]`).forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    $$(`[data-i18n-placeholder]`).forEach((element) => {
      element.placeholder = t(element.dataset.i18nPlaceholder);
    });
    $$(`[data-i18n-title]`).forEach((element) => {
      element.title = t(element.dataset.i18nTitle);
    });
    $$(`[data-i18n-aria]`).forEach((element) => {
      element.setAttribute("aria-label", t(element.dataset.i18nAria));
    });
    $("#localeZh")?.classList.toggle("active", state.locale === "zh");
    $("#localeEn")?.classList.toggle("active", state.locale === "en");
    runtime.renderedTaskListKey = "";
    updateReasoningControl();
    if ($("#messageList") && !isSessionBusy(state.sessionId)) renderSession(state.sessionId);
    updateMode();
    renderTodoPanel();
    renderVerification();
    if (state.connection !== null) setConnection(state.connection);
    applyTheme();
  }
  function applyTheme() {
    document.documentElement.dataset.theme = state.theme;
    syncHljsTheme();
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      const themeColor = state.theme === "light" ? "#f6f7f9" : "#111214";
      document.querySelectorAll('meta[name="theme-color"]').forEach((tag) => {
        tag.setAttribute("content", themeColor);
      });
    }
    const button = $("#themeButton");
    if (!button) return;
    const isLight = state.theme === "light";
    const label2 = isLight ? state.locale === "zh" ? "\u5207\u6362\u5230\u6697\u8272\u6A21\u5F0F" : "Switch to dark mode" : state.locale === "zh" ? "\u5207\u6362\u5230\u4EAE\u8272\u6A21\u5F0F" : "Switch to light mode";
    button.setAttribute("aria-label", label2);
    button.title = label2;
    button.innerHTML = icon(isLight ? "moon" : "sun");
    refreshIcons();
  }
  function applyFocusMode() {
    document.documentElement.dataset.focusMode = state.focusMode ? "true" : "false";
    const button = $("#focusToggle");
    if (!button) return;
    const key = state.focusMode ? "focus.exit" : "focus.enter";
    button.title = t(key);
    button.setAttribute("aria-label", t(key));
    button.setAttribute("aria-pressed", String(state.focusMode));
    button.innerHTML = icon(state.focusMode ? "minimize" : "maximize");
    refreshIcons();
  }
  function setFocusMode(enabled) {
    state.focusMode = Boolean(enabled);
    localStorage.setItem("minicc-focus-mode", String(state.focusMode));
    applyFocusMode();
  }
  function applyPaneLayout() {
    const root = document.documentElement;
    root.dataset.sidebarCollapsed = state.sidebarCollapsed ? "true" : "false";
    root.dataset.inspectorCollapsed = state.inspectorCollapsed ? "true" : "false";
    const desktop = window.matchMedia?.("(min-width: 1181px)").matches;
    const sidebarButton = $("#sidebarOpen");
    const inspectorButton = $("#inspectorToggle");
    if (sidebarButton && desktop) {
      const zh2 = state.locale === "zh";
      sidebarButton.setAttribute("aria-label", state.sidebarCollapsed ? zh2 ? "\u6253\u5F00\u4FA7\u680F" : "Open sidebar" : zh2 ? "\u6536\u8D77\u4FA7\u680F" : "Collapse sidebar");
      sidebarButton.title = state.sidebarCollapsed ? zh2 ? "\u6253\u5F00\u4FA7\u680F" : "Open sidebar" : zh2 ? "\u6536\u8D77\u4FA7\u680F" : "Collapse sidebar";
      sidebarButton.innerHTML = icon(state.sidebarCollapsed ? "panel-left-open" : "panel-left-close");
    }
    if (inspectorButton && desktop) {
      const zh2 = state.locale === "zh";
      inspectorButton.setAttribute("aria-label", state.inspectorCollapsed ? zh2 ? "\u6253\u5F00\u68C0\u67E5\u5668" : "Open inspector" : zh2 ? "\u6536\u8D77\u68C0\u67E5\u5668" : "Collapse inspector");
      inspectorButton.title = state.inspectorCollapsed ? zh2 ? "\u6253\u5F00\u68C0\u67E5\u5668" : "Open inspector" : zh2 ? "\u6536\u8D77\u68C0\u67E5\u5668" : "Collapse inspector";
      inspectorButton.innerHTML = icon(state.inspectorCollapsed ? "panel-right-open" : "panel-right-close");
    }
    refreshIcons();
  }
  function setSidebarCollapsed(collapsed) {
    state.sidebarCollapsed = Boolean(collapsed);
    localStorage.setItem("minicc-sidebar-collapsed", String(state.sidebarCollapsed));
    applyPaneLayout();
  }
  function setInspectorCollapsed(collapsed) {
    state.inspectorCollapsed = Boolean(collapsed);
    localStorage.setItem("minicc-inspector-collapsed", String(state.inspectorCollapsed));
    applyPaneLayout();
  }
  function prepareStartupSplash() {
    const splash = $("#startupSplash");
    if (!splash) return;
    splash.dataset.state = "loading";
    splash.setAttribute("aria-busy", "true");
    splash.setAttribute("aria-hidden", "false");
    const status = $("#startupStatus");
    if (status) status.textContent = state.locale === "zh" ? "\u6B63\u5728\u542F\u52A8\u672C\u5730\u5DE5\u4F5C\u53F0" : "Starting local workbench";
  }
  function setStartupSplashError() {
    const splash = $("#startupSplash");
    if (!splash) return;
    splash.dataset.state = "error";
    splash.setAttribute("aria-busy", "false");
    const status = $("#startupStatus");
    if (status) status.textContent = state.locale === "zh" ? "\u79BB\u7EBF\u6A21\u5F0F\uFF0C\u6B63\u5728\u8FDB\u5165\u5DE5\u4F5C\u53F0" : "Offline mode \xB7 entering workbench";
  }
  function finishStartupSplash() {
    const splash = $("#startupSplash");
    if (!splash) return;
    splash.dataset.state = "ready";
    splash.setAttribute("aria-busy", "false");
    splash.setAttribute("aria-hidden", "true");
  }
  function setTheme(theme) {
    state.theme = theme === "light" ? "light" : "dark";
    localStorage.setItem("minicc-theme", state.theme);
    applyTheme();
  }
  function syncHljsTheme() {
    const light = document.getElementById("hljsThemeLight");
    const dark = document.getElementById("hljsThemeDark");
    if (light instanceof HTMLLinkElement) light.disabled = state.theme !== "light";
    if (dark instanceof HTMLLinkElement) dark.disabled = state.theme !== "dark";
  }
  function setLocale(locale) {
    state.locale = locale === "en" ? "en" : "zh";
    localStorage.setItem("minicc-locale", state.locale);
    applyLocale();
    showToast(state.locale === "zh" ? "\u5DF2\u5207\u6362\u4E2D\u6587" : "Switched to English");
  }

  // web/src/files/preview.js
  function fileTypeFromPath(path) {
    const extension = String(path || "").split(".").pop()?.toLowerCase();
    const map = {
      py: "python",
      js: "javascript",
      mjs: "javascript",
      cjs: "javascript",
      ts: "typescript",
      tsx: "typescript",
      jsx: "javascript",
      css: "css",
      scss: "scss",
      html: "xml",
      htm: "xml",
      md: "markdown",
      json: "json",
      sh: "bash",
      bash: "bash",
      yml: "yaml",
      yaml: "yaml",
      xml: "xml",
      svg: "xml",
      rs: "rust",
      go: "go",
      java: "java",
      kt: "kotlin"
    };
    return map[extension] || "";
  }
  function looksLikeWorkspacePath(value) {
    const text = String(value || "").trim();
    if (!text || text.length > 260) return false;
    if (/^(ok|error|denied|completed|failed|blocked|done)$/i.test(text)) return false;
    if (/\s/.test(text) && !/[\\/]/.test(text)) return false;
    return /[\\/]/.test(text) || /\.[A-Za-z0-9]{1,8}$/.test(text);
  }
  function highlightFileContent(content, language) {
    const source = String(content ?? "");
    const highlighter = typeof hljs !== "undefined" ? hljs : window.hljs;
    if (highlighter) {
      try {
        if (language && highlighter.getLanguage?.(language)) {
          return highlighter.highlight(source, { language, ignoreIllegals: true }).value;
        }
        if (!language && source.length <= 2e4 && highlighter.highlightAuto) {
          return highlighter.highlightAuto(source).value;
        }
      } catch {
      }
    }
    return escapeHtml(source);
  }
  function fileEditorMarkup(path, content) {
    const source = String(content ?? "");
    const lines = source.length ? source.split("\n") : [""];
    const language = fileTypeFromPath(path);
    const highlighted = highlightFileContent(source, language);
    const gutter = lines.map((_, index) => `<span class="file-editor-ln">${index + 1}</span>`).join("");
    const classes = language ? `hljs language-${escapeHtml(language)}` : "hljs";
    return `<div class="file-editor">
    <div class="file-editor-toolbar"><span>${escapeHtml(t("file.current"))}</span><button type="button" class="file-copy-button" data-copy-file>${icon("copy")}<span>${escapeHtml(t("file.copy"))}</span></button></div>
    <textarea class="file-editor-source" hidden readonly>${escapeHtml(source)}</textarea>
    <div class="file-editor-body">
      <div class="file-editor-gutter" aria-hidden="true">${gutter}</div>
      <pre class="file-editor-code"><code class="${classes}">${highlighted || "&nbsp;"}</code></pre>
    </div>
  </div>`;
  }
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
        rows.push(diffRowMarkup("diff-context", " ", oldLine, newLine, line.startsWith(" ") ? line.slice(1) : line));
        oldLine += 1;
        newLine += 1;
      }
    }
    return rows.join("");
  }
  var previewRequest = 0;
  async function openFilePreview(path) {
    const current = beginPanelRequest(`${t("panel.file")} \xB7 ${path}`);
    const request = ++previewRequest;
    const version = runtime.workspaceVersion;
    const workspace = state.workspacePath;
    const stale = () => !current() || request !== previewRequest || version !== runtime.workspaceVersion || workspace !== state.workspacePath;
    try {
      const [diff, data] = await Promise.all([
        requestJson(`/api/diff?path=${encodeURIComponent(path)}`),
        requestJson(`/api/file?path=${encodeURIComponent(path)}`).catch((error) => ({ content: "", error: error.message }))
      ]);
      if (stale()) return;
      const additions = countLabel(diff.additions);
      const deletions = countLabel(diff.deletions);
      const diffRows = renderUnifiedDiffRows(diff.patch);
      const diffBody = diffRows || `<span class="diff-row diff-empty"><span class="diff-code">${escapeHtml(t("diff.empty"))}</span></span>`;
      const fileHead = `<div class="diff-file-head"><span class="diff-file-path">${icon("file-code-2")}<strong>${escapeHtml(path)}</strong></span><span class="diff-file-badges"><span class="diff-badge diff-badge-status">${escapeHtml(changeStatusLabel(diff.status || "modified"))}</span><span class="diff-badge diff-badge-add">+${additions}</span><span class="diff-badge diff-badge-del">-${deletions}</span></span></div>`;
      const currentContent = data.error ? `<div class="file-tree-status" role="status">${escapeHtml(diff.status === "deleted" ? state.locale === "zh" ? "\u6587\u4EF6\u5DF2\u5220\u9664\uFF1B\u4E0A\u65B9\u663E\u793A\u5220\u9664\u524D\u7684\u5DEE\u5F02\u3002" : "File deleted; the diff above shows its previous content." : data.error)}</div>` : fileEditorMarkup(path, data.content || "");
      openPanel(`${t("panel.file")} \xB7 ${path}`, `<div class="diff-toolbar"><span>${escapeHtml(t("diff.previewAria"))}</span><span class="mono">${escapeHtml(diff.source || "diff")}</span></div>${fileHead}<pre class="diff-preview" aria-label="${escapeHtml(`${t("diff.previewAria")} \xB7 ${t("diff.oldLine")} / ${t("diff.newLine")}`)}">${diffBody}</pre><details class="file-current" open><summary>${escapeHtml(t("file.current"))}</summary>${currentContent}</details>`);
    } catch (error) {
      if (stale()) return;
      openPanel(t("panel.file"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }
  async function copyFilePreviewContent() {
    const source = $("#panelBody .file-editor-source");
    const text = source instanceof HTMLTextAreaElement ? source.value : source?.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      showToast(t("file.copied"));
    } catch {
      showToast(state.locale === "zh" ? "\u590D\u5236\u5931\u8D25\uFF0C\u8BF7\u5728\u9884\u89C8\u4E2D\u624B\u52A8\u9009\u62E9\u6587\u672C\u3002" : "Copy failed. Select the preview text to copy manually.");
    }
  }

  // web/src/core/command-palette.js
  var listNode = null;
  var inputNode = null;
  var activeIndex = 0;
  var filtered = [];
  var optionBaseId = "paletteOption";
  function label(id, fallback) {
    const translated = t(id);
    return translated === id ? fallback : translated;
  }
  function commands() {
    const zh2 = state.locale === "zh";
    const themeTarget = state.theme === "dark" ? label("palette.toLight", "Switch to light theme") : label("palette.toDark", "Switch to dark theme");
    return [
      { id: "newTask", glyph: "plus", group: "palette.group.task", run: () => resetTask() },
      { id: "taskCenter", glyph: "list-checks", group: "palette.group.task", run: () => openTaskListPanel() },
      { id: "workspaces", glyph: "folder-open", group: "palette.group.task", run: () => openWorkspacesPanel() },
      { id: "globalSearch", glyph: "search", group: "palette.group.task", run: () => openGlobalSearchPanel() },
      { id: "activity", glyph: "activity", group: "palette.group.task", run: () => openActivityPanel() },
      { id: "ledger", glyph: "ledger", group: "palette.group.task", run: () => openLedgerPanel() },
      { id: "templates", glyph: "sparkles", group: "palette.group.task", run: () => openTemplatesPanel() },
      { id: "almanac", glyph: "book-open", group: "palette.group.task", run: () => openAlmanacPanel() },
      { id: "manual", glyph: "book-open-text", group: "palette.group.task", run: () => openManualPanel() },
      { id: "batch", glyph: "layers", group: "palette.group.task", run: () => openBatchPanel() },
      { id: "export", glyph: "download", group: "palette.group.task", run: () => exportChat() },
      { id: "settings", glyph: "settings-2", group: "palette.group.surface", run: () => openSettingsPanel() },
      { id: "options", glyph: "more-horizontal", group: "palette.group.surface", run: () => openOptionsPanel() },
      { id: "help", glyph: "circle-help", group: "palette.group.surface", run: () => openHelpPanel() },
      { id: "arcade", glyph: "gamepad-2", group: "palette.group.surface", run: () => openArcade() },
      { id: "theme", glyph: "moon-star", group: "palette.group.surface", labelOverride: themeTarget, run: () => setTheme(state.theme === "dark" ? "light" : "dark") },
      { id: "locale", glyph: "globe-2", group: "palette.group.surface", labelOverride: zh2 ? "\u5207\u6362\u5230\u82F1\u6587" : "Switch to Chinese", run: () => setLocale(zh2 ? "en" : "zh") },
      { id: "sidebar", glyph: "panel-left", group: "palette.group.surface", run: () => setSidebarCollapsed(!state.sidebarCollapsed) },
      { id: "inspector", glyph: "panel-right", group: "palette.group.surface", run: () => setInspectorCollapsed(!state.inspectorCollapsed) },
      { id: "focus", glyph: "scan-line", group: "palette.group.surface", run: () => setFocusMode(!state.focusMode) },
      { id: "jumpLatest", glyph: "chevrons-down", group: "palette.group.surface", run: () => scrollChat("auto", true) }
    ].map((item) => ({
      ...item,
      label: item.labelOverride || label(`palette.cmd.${item.id}`, item.id),
      hint: label(`palette.group.${item.group.split(".").pop()}`, item.group)
    }));
  }
  function score(query, command) {
    const haystack = `${command.label} ${command.hint}`.toLowerCase();
    const needle = query.toLowerCase();
    const direct = haystack.indexOf(needle);
    if (direct >= 0) {
      const wordStart = direct === 0 || /\s/.test(haystack[direct - 1]);
      return 100 - direct * 0.5 + (wordStart ? 20 : 0);
    }
    let index = -1;
    let runs = 0;
    let consecutive = 0;
    for (const char of needle) {
      const found = haystack.indexOf(char, index + 1);
      if (found < 0) return -1;
      consecutive = found === index + 1 ? consecutive + 1 : 0;
      runs += consecutive;
      index = found;
    }
    return 60 - index * 0.2 + runs * 2;
  }
  function render() {
    const query = inputNode.value.trim();
    const all = commands();
    filtered = query ? all.map((command) => ({ command, points: score(query, command) })).filter((entry) => entry.points >= 0).sort((a, b) => b.points - a.points).map((entry) => entry.command) : all;
    listNode.innerHTML = "";
    if (!filtered.length) {
      const empty = document.createElement("li");
      empty.className = "palette-empty";
      empty.textContent = t("palette.empty");
      listNode.append(empty);
      return;
    }
    activeIndex = Math.min(activeIndex, filtered.length - 1);
    filtered.forEach((command, index) => {
      const item = document.createElement("li");
      item.id = `${optionBaseId}-${index}`;
      item.className = "palette-option";
      item.setAttribute("role", "option");
      item.dataset.index = String(index);
      const mark = document.createElement("span");
      mark.className = "palette-glyph";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = iconGlyph(command.glyph);
      const text = document.createElement("span");
      text.className = "palette-label";
      text.textContent = command.label;
      const group = document.createElement("span");
      group.className = "palette-group";
      group.textContent = command.hint;
      item.append(mark, text, group);
      if (index === activeIndex) item.setAttribute("aria-selected", "true");
      listNode.append(item);
    });
  }
  function iconGlyph(name) {
    const glyphs = { plus: "+", "list-checks": "\u2611", "folder-open": "\u{1F5C2}", search: "\u2315", activity: "\u25A5", ledger: "\u25A4", sparkles: "\u2726", "book-open": "\u25A4", layers: "\u2261", download: "\u2193", "settings-2": "\u2699", "more-horizontal": "\u22EF", "circle-help": "?", "gamepad-2": "\u25B6", "moon-star": "\u263E", "globe-2": "\u25CE", "panel-left": "\u25A4", "panel-right": "\u25A7", "scan-line": "\u25EB", "chevrons-down": "\u2304" };
    return glyphs[name] || "\u203A";
  }
  function move(delta) {
    if (!filtered.length) return;
    const next = (activeIndex + delta + filtered.length) % filtered.length;
    setActive(next);
  }
  function setActive(index) {
    activeIndex = index;
    for (const node of listNode.children) {
      if (node.getAttribute("role") !== "option") continue;
      const current = Number(node.dataset.index) === index;
      node.classList.toggle("active", current);
      if (current) {
        node.setAttribute("aria-selected", "true");
        node.scrollIntoView({ block: "nearest" });
        inputNode.setAttribute("aria-activedescendant", node.id);
      } else node.removeAttribute("aria-selected");
    }
  }
  function activate(index) {
    const command = filtered[index];
    if (!command) return;
    closeCommandPalette();
    try {
      command.run();
    } catch (error) {
      showToast(error?.message || String(error));
    }
  }
  function openCommandPalette() {
    const modal = $("#paletteModal");
    inputNode = $("#paletteInput");
    listNode = $("#paletteList");
    activeIndex = 0;
    inputNode.value = "";
    modal.classList.add("show");
    modal.setAttribute("aria-hidden", "false");
    render();
    setActive(activeIndex);
    activateDialog(modal, { initialFocus: "#paletteInput", onEscape: closeCommandPalette });
    inputNode.focus({ preventScroll: true });
    inputNode.oninput = () => {
      activeIndex = 0;
      render();
      setActive(activeIndex);
    };
    inputNode.onkeydown = (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        move(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        move(-1);
      } else if (event.key === "Enter") {
        event.preventDefault();
        activate(activeIndex);
      }
    };
    listNode.onclick = (event) => {
      const option = event.target.closest('[role="option"]');
      if (option) activate(Number(option.dataset.index));
    };
    listNode.onpointermove = (event) => {
      const option = event.target.closest('[role="option"]');
      if (option && Number(option.dataset.index) !== activeIndex) setActive(Number(option.dataset.index));
    };
  }
  function closeCommandPalette() {
    const modal = $("#paletteModal");
    if (!modal.classList.contains("show")) return;
    deactivateDialog(modal);
    modal.classList.remove("show");
    modal.setAttribute("aria-hidden", "true");
    inputNode?.blur();
  }
  function bindCommandPalette() {
    $("#paletteClose").addEventListener("click", closeCommandPalette);
    $("#paletteModal").addEventListener("pointerdown", (event) => {
      if (event.target.id === "paletteModal") closeCommandPalette();
    });
  }

  // web/src/panels/replay.js
  var MAX_ROWS = 60;
  var DELAYS = { 1: 650, 2: 320, 4: 160 };
  function tokenTotalOf(task) {
    const total = Number(task?.tokens_used?.total_tokens ?? task?.metrics?.budget?.tokens ?? 0);
    return Number.isFinite(total) ? Math.max(0, total) : 0;
  }
  function eventRow(event, index) {
    const code = String(event?.code ?? "") || String(event?.kind ?? "") || "event";
    const summary = String(event?.summary ?? event?.detail?.text ?? "").trim();
    const kind = String(event?.kind ?? "");
    const tone = kind === "status" || kind === "result" ? "status" : kind === "usage" ? "usage" : "step";
    return `<li class="replay-row replay-row-${tone}" style="--row-index:${index}"><span class="replay-row-index">#${String(index + 1).padStart(2, "0")}</span><code class="replay-row-code">${escapeHtml(code)}</code><span class="replay-row-text">${escapeHtml(summary)}</span></li>`;
  }
  function openReplayView(task, onBack) {
    const events = compactModelUpdateEvents(Array.isArray(task.events) ? task.events : []);
    const totalTokens = tokenTotalOf(task);
    const capped = events.length > MAX_ROWS ? events.slice(-MAX_ROWS) : events;
    const rows = capped.length ? capped.map((event, index2) => eventRow(event, index2)).join("") : `<li class="replay-row replay-row-empty"><span class="replay-row-text">${escapeHtml(t("replay.empty"))}</span></li>`;
    const title = String(task.preview || task.prompt || task.task_id || "").slice(0, 90);
    const total = capped.length;
    const overlay = document.createElement("div");
    overlay.className = "replay-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", t("replay.aria"));
    overlay.innerHTML = `
    <header class="replay-head">
      <div class="replay-head-copy">
        <span class="replay-kicker">REPLAY \xB7 ${escapeHtml(String(task.task_id ?? ""))}</span>
        <h2 class="replay-title">${escapeHtml(title)}</h2>
        <div class="replay-sub">${compactNumber(totalTokens)} ${escapeHtml(t("replay.tokens"))} \xB7 ${escapeHtml(t("replay.rows"))}: ${total}</div>
      </div>
      <div class="replay-head-actions">
        <button type="button" class="panel-secondary" data-replay-action="back">${icon("arrow-left")} ${escapeHtml(t("replay.back"))}</button>
        <button type="button" class="icon-button" aria-label="${escapeHtml(t("replay.close"))}" data-replay-action="close">${icon("x")}</button>
      </div>
    </header>
    <div class="replay-stage">
      <ol class="replay-log" id="replayLog">${rows}</ol>
      <aside class="replay-side" aria-hidden="true">
        <div class="replay-big" id="replayTokens">0</div>
        <div class="replay-label">${escapeHtml(t("replay.tokensLive"))}</div>
        <div class="replay-turn"><span id="replayStep">0</span><span class="replay-turn-total">/ ${total}</span></div>
        <div class="replay-label">${escapeHtml(t("replay.progress"))}</div>
        <div class="replay-stamp" id="replayStamp" hidden>${icon("check-circle-2")} ${escapeHtml(t("replay.done"))}</div>
      </aside>
    </div>
    <footer class="replay-foot">
      <button type="button" class="replay-play" id="replayPlayButton" data-replay-action="toggle" aria-label="${escapeHtml(t("replay.toggle"))}">${icon("play")}</button>
      <input type="range" class="replay-scrub" id="replayScrub" min="0" max="${total}" value="0" step="1" aria-label="${escapeHtml(t("replay.scrub"))}">
      <button type="button" class="replay-speed" data-replay-action="speed" id="replaySpeed">1\xD7</button>
      <div class="replay-count"><span id="replayCount">0</span> / ${total}</div>
    </footer>
  `;
    document.body.appendChild(overlay);
    refreshIcons();
    const log = overlay.querySelector("#replayLog");
    const rowsEl = [...log.querySelectorAll(".replay-row")];
    const tokensEl = overlay.querySelector("#replayTokens");
    const stepEl = overlay.querySelector("#replayStep");
    const countEl = overlay.querySelector("#replayCount");
    const stampEl = overlay.querySelector("#replayStamp");
    const scrubEl = overlay.querySelector("#replayScrub");
    const playButton = overlay.querySelector("#replayPlayButton");
    const speedButton = overlay.querySelector("#replaySpeed");
    let index = 0;
    let playing = true;
    let speed = 1;
    let timer = null;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    function paint(through) {
      rowsEl.forEach((row, rowIndex) => {
        row.classList.toggle("replay-row-visible", rowIndex < through);
      });
      const fraction = total > 0 ? through / total : 0;
      tokensEl.textContent = compactNumber(Math.round(totalTokens * fraction));
      stepEl.textContent = String(through);
      countEl.textContent = String(through);
      scrubEl.value = String(through);
      if (through >= total) stampEl.hidden = false;
      else stampEl.hidden = true;
      const last = log.querySelector(".replay-row-visible:last-child");
      if (last && !reducedMotion) last.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    function clearTimer() {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    }
    function setPlaying(next) {
      playing = next;
      playButton.innerHTML = playing ? icon("pause") : icon("play");
      refreshIcons();
      clearTimer();
      if (!playing) return;
      timer = setInterval(() => {
        if (index >= total) {
          clearTimer();
          playButton.innerHTML = icon("rotate-ccw");
          refreshIcons();
          playing = false;
          return;
        }
        index += 1;
        paint(index);
      }, DELAYS[speed]);
    }
    function close() {
      clearTimer();
      document.removeEventListener("keydown", onKeydown, true);
      overlay.remove();
    }
    function onKeydown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    }
    document.addEventListener("keydown", onKeydown, true);
    overlay.addEventListener("click", (event) => {
      const target = event.target.closest("[data-replay-action]");
      if (!target) return;
      const action = target.getAttribute("data-replay-action");
      if (action === "close") close();
      else if (action === "back") {
        close();
        if (typeof onBack === "function") onBack();
      } else if (action === "toggle") {
        if (index >= total && !playing) {
          index = 0;
          paint(0);
          setPlaying(true);
          return;
        }
        setPlaying(!playing);
      } else if (action === "speed") {
        speed = speed === 1 ? 2 : speed === 2 ? 4 : 1;
        speedButton.textContent = `${speed}\xD7`;
        if (playing) setPlaying(true);
      }
    });
    scrubEl.addEventListener("input", () => {
      clearTimer();
      playing = false;
      playButton.innerHTML = icon("play");
      refreshIcons();
      index = Number(scrubEl.value) || 0;
      paint(index);
    });
    paint(0);
    setPlaying(total > 0);
    playButton.focus({ preventScroll: true });
  }
  async function openReplayForTask(taskId, onBack) {
    const task = await requestJson(`/api/tasks/${encodeURIComponent(String(taskId ?? ""))}`);
    openReplayView(task, onBack);
  }

  // web/src/main.js
  function bindUI() {
    window.addEventListener("minicc-auth-required", showAuthModal);
    $("#chatForm").addEventListener("submit", sendMessage);
    $("#chatArea").addEventListener("scroll", () => {
      state.chatRestoreVersion += 1;
      state.chatUserScrolledAt = performance.now();
      updateChatFollowState();
    }, { passive: true });
    $("#jumpLatestButton").addEventListener("click", () => scrollChat("auto", true));
    $("#newTaskButton").addEventListener("click", resetTask);
    $("#demoFlowButton").addEventListener("click", runDemoFlow);
    $("#cancelTaskButton").addEventListener("click", cancelActiveTask);
    $("#gameClose")?.addEventListener("click", () => window.closeGame?.());
    $("#gameNewWindow")?.addEventListener("click", () => window.openGameWindow?.());
    $("#gameWideMode")?.addEventListener("click", () => window.toggleGameWideMode?.());
    $("#gameCodex")?.addEventListener("click", () => window.openGameCodex?.("plants"));
    $("#gameCodexClose")?.addEventListener("click", () => window.closeGameCodex?.());
    document.querySelectorAll(".codex-tab").forEach((tab) => tab.addEventListener("click", () => window.openGameCodex?.(tab.dataset.codexTab)));
    $("#gameCodexPanel")?.addEventListener("click", (event) => {
      if (event.target.id === "gameCodexPanel") window.closeGameCodex?.();
    });
    $("#gameFullscreen")?.addEventListener("click", () => window.toggleGameFullscreen?.());
    $("#gameStart")?.addEventListener("click", () => window.startGame?.());
    $("#gameShovel")?.addEventListener("click", () => window.toggleShovel?.());
    document.querySelectorAll(".game-skill").forEach((button) => button.addEventListener("click", () => window.activateGameSkill?.(button.dataset.skill)));
    $("#gamePause")?.addEventListener("click", () => window.toggleGamePause?.());
    $("#gameDifficulty")?.addEventListener("change", (event) => window.setGameDifficulty?.(event.target.value));
    $("#gameAutoSun")?.addEventListener("change", (event) => {
      if (window.game) window.game.autoSun = event.target.checked;
      localStorage.setItem("minicc-game-auto-sun", event.target.checked ? "on" : "off");
    });
    $("#gameSoundToggle")?.addEventListener("click", () => window.toggleGameSound?.());
    $("#gameVolume")?.addEventListener("input", (event) => window.setGameVolume?.(event.target.value));
    document.addEventListener("visibilitychange", () => window.setGamePaused?.(document.hidden));
    $("#gameModal")?.addEventListener("click", (event) => {
      if (event.target.id === "gameModal") window.closeGame?.();
    });
    bindCommandPalette();
    window.addEventListener("minicc-open-task", (event) => {
      const taskId = event.detail?.taskId;
      if (taskId) openTaskInWorkspace(taskId).catch((error) => showToast(error.message));
    });
    $("#gameCanvas")?.addEventListener("click", (event) => {
      if (window.collectSun?.(event)) return;
      window.plantAt?.(event);
    });
    $("#gameCanvas")?.addEventListener("pointermove", (event) => window.updateGameHover?.(event), { passive: true });
    $("#gameCanvas")?.addEventListener("pointerleave", () => window.clearGameHover?.(), { passive: true });
    document.querySelectorAll(".seed-card").forEach((card) => card.addEventListener("click", () => window.selectPlant?.(card)));
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if ($("#pulseStage")?.getAttribute("aria-hidden") === "false") {
          $("#pulseStage").setAttribute("aria-hidden", "true");
          return;
        }
        const arcade = window.game;
        if ($("#gameModal")?.classList.contains("show") && (arcade?.selected || arcade?.shovel)) {
          window.clearPlantSelection?.();
          if (arcade) arcade.shovel = false;
          window.updateShovelButton?.();
        } else {
          window.closeGame?.();
          closePanel();
        }
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        resetTask();
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if ($("#paletteModal")?.classList.contains("show")) closeCommandPalette();
        else openCommandPalette();
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "l") {
        event.preventDefault();
        openLedgerPanel();
      }
      if (event.key === "/" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "INPUT") {
        event.preventDefault();
        $("#threadSearch").focus();
      }
      if (event.key === "?" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "INPUT") {
        event.preventDefault();
        openHelpPanel();
      }
    });
    $("#allowChanges").addEventListener("change", (event) => {
      state.allowChanges = event.target.checked;
      localStorage.setItem("minicc-allow", String(state.allowChanges));
      updateMode();
      showToast(state.allowChanges ? state.locale === "zh" ? "\u5DF2\u5141\u8BB8\u5F53\u524D\u4EFB\u52A1\u4FEE\u6539" : "Changes enabled for new requests" : state.locale === "zh" ? "\u5DF2\u542F\u7528\u5B89\u5168\u6A21\u5F0F" : "Safe mode enabled");
    });
    $("#allowNetwork").addEventListener("change", (event) => {
      state.allowNetwork = event.target.checked;
      updateMode();
      localStorage.setItem("minicc-network", String(state.allowNetwork));
      showToast(state.allowNetwork ? state.locale === "zh" ? "\u5DF2\u5141\u8BB8\u5F53\u524D\u4EFB\u52A1\u8054\u7F51\u641C\u7D22" : "Web search enabled for new requests" : state.locale === "zh" ? "\u5DF2\u5173\u95ED\u8054\u7F51\u641C\u7D22" : "Web search disabled");
    });
    $("#permModeGroup").addEventListener("click", (event) => {
      const option = event.target.closest(".perm-mode-option[data-mode]");
      if (option) setPermissionMode(option.dataset.mode);
    });
    $("#permModeGroup").addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const index = PERMISSION_MODES.indexOf(state.permissionMode);
      const delta = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
      setPermissionMode(PERMISSION_MODES[(index + delta + PERMISSION_MODES.length) % PERMISSION_MODES.length]);
      $("#permModeGroup .perm-mode-option.active")?.focus();
    });
    $("#todoSectionToggle").addEventListener("click", () => toggleTodoSection());
    $("#localeZh").addEventListener("click", () => setLocale("zh"));
    $("#localeEn").addEventListener("click", () => setLocale("en"));
    $("#themeButton").addEventListener("click", () => setTheme(state.theme === "light" ? "dark" : "light"));
    $("#focusToggle").addEventListener("click", () => setFocusMode(!state.focusMode));
    $("#moreOptionsButton").addEventListener("click", openOptionsPanel);
    $("#reasoningButton").addEventListener("click", openSettingsPanel);
    $("#moreTasksButton").addEventListener("click", openTaskListPanel);
    $("#globalSearchButton").addEventListener("click", openGlobalSearchPanel);
    $("#taskDockOpen").addEventListener("click", openActivityPanel);
    $("#batchButton").addEventListener("click", openBatchPanel);
    $("#attachButton").addEventListener("click", () => $("#imageInput").click());
    $("#imageInput").addEventListener("change", (event) => {
      addImageFiles(event.target.files);
    });
    $("#attachmentTray").addEventListener("click", (event) => {
      const target = event.target.closest("[data-remove-attachment]");
      if (!target) return;
      state.attachments = state.attachments.filter((item) => item.id !== target.dataset.removeAttachment);
      renderAttachmentTray();
    });
    $("#composerShell").addEventListener("dragover", (event) => {
      if ([...event.dataTransfer?.items || []].some((item) => item.kind === "file")) {
        event.preventDefault();
        $("#composerShell").classList.add("drag-active");
      }
    });
    $("#composerShell").addEventListener("dragleave", () => $("#composerShell").classList.remove("drag-active"));
    $("#composerShell").addEventListener("drop", (event) => {
      event.preventDefault();
      $("#composerShell").classList.remove("drag-active");
      addImageFiles(event.dataTransfer?.files);
    });
    $("#promptInput").addEventListener("paste", (event) => {
      const images = [...event.clipboardData?.files || []].filter((file) => String(file.type || "").startsWith("image/"));
      if (images.length) {
        event.preventDefault();
        addImageFiles(images);
      }
    });
    $("#profileButton").addEventListener("click", openSettingsPanel);
    $("#panelClose").addEventListener("click", closePanel);
    $("#panelExpand").addEventListener("click", togglePanelFullscreen);
    $("#panelModal").addEventListener("click", (event) => {
      if (event.target.id === "panelModal") closePanel();
    });
    $("#refreshFiles").addEventListener("click", () => {
      loadWorkspace();
      showToast(state.locale === "zh" ? "\u5DE5\u4F5C\u533A\u72B6\u6001\u5DF2\u5237\u65B0" : "Workspace refreshed");
    });
    $("#refreshFileTree").addEventListener("click", refreshFileTree);
    $("#fileTree").addEventListener("click", (event) => {
      const dirRow = event.target.closest("[data-tree-dir]");
      if (dirRow) {
        toggleFileDir(dirRow.dataset.treeDir);
        return;
      }
      const fileRow = event.target.closest("[data-open-diff]");
      if (fileRow) openFilePreview(fileRow.dataset.openDiff);
    });
    document.querySelectorAll(".inspector-tab").forEach((button) => button.addEventListener("click", () => switchInspectorTab(button.dataset.inspectorTab)));
    $("#fileTree").addEventListener("keydown", handleFileTreeKeydown);
    $("#fileTree").addEventListener("focusin", (event) => {
      const row = event.target.closest('[role="treeitem"]');
      if (row) $("#fileTree").querySelectorAll('[role="treeitem"]').forEach((item) => {
        item.tabIndex = item === row ? 0 : -1;
      });
    });
    $(".inspector-tabs").addEventListener("keydown", (event) => {
      const tabs = $$(".inspector-tab");
      const index = tabs.indexOf(document.activeElement);
      if (index < 0 || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowLeft" ? -1 : 1) + tabs.length) % tabs.length;
      tabs[next].click();
      tabs[next].focus();
    });
    $("#fileList").addEventListener("click", (event) => {
      const target = event.target.closest("[data-open-diff]");
      if (target) openFilePreview(target.dataset.openDiff);
    });
    $("#changeList").addEventListener("click", (event) => {
      const target = event.target.closest("[data-open-diff]");
      if (target) openFilePreview(target.dataset.openDiff);
    });
    $("#messageList").addEventListener("click", (event) => {
      const start = event.target.closest("[data-start-action]");
      if (start) {
        $("#promptInput").value = t(`start.${start.dataset.startAction}Prompt`);
        $("#promptInput").focus();
        $("#promptInput").dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
      const timelineToggle = event.target.closest("[data-timeline-toggle]");
      if (timelineToggle) {
        const timeline = timelineToggle.closest(".execution-trail");
        setTimelineDetails(timeline, timelineToggle.dataset.timelineToggle === "expand");
        event.preventDefault();
        return;
      }
      const rewind = event.target.closest(".rewind-to-here");
      if (rewind) {
        event.preventDefault();
        rewindToUserIndex(rewind.dataset.userIndex);
        return;
      }
      const restore = event.target.closest("[data-restore-task]");
      if (restore) {
        event.preventDefault();
        restoreTaskSnapshot(restore.dataset.restoreTask);
        return;
      }
      const target = event.target.closest("[data-open-diff]");
      if (target) {
        openFilePreview(target.dataset.openDiff);
        return;
      }
      const pathNode = event.target.closest(".tool-path");
      if (pathNode && looksLikeWorkspacePath(pathNode.textContent)) openFilePreview(pathNode.textContent.trim());
    });
    document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => {
      const view = button.dataset.view;
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item === button));
      if (view === "tasks") {
        closePanel();
      } else if (view === "workspaces") openWorkspacesPanel();
      else if (view === "promo") openPromoPanel();
      else if (view === "activity") openActivityPanel();
      else if (view === "pulse") openPulseStage();
      else if (view === "templates") openTemplatesPanel();
      else if (view === "almanac") openAlmanacPanel();
      else if (view === "manual") openManualPanel();
      else if (view === "ledger") openLedgerPanel();
      else if (view === "arcade") openArcade().catch((error) => showToast(error.message));
      else closePanel();
    }));
    document.querySelectorAll(".action-chip").forEach((button) => button.addEventListener("click", () => {
      const prompt = state.locale === "zh" ? button.dataset.promptZh : button.dataset.promptEn;
      if (!prompt && !button.dataset.prompt) return;
      $("#promptInput").value = prompt || button.dataset.prompt || "";
      $("#promptInput").focus();
    }));
    $("#brandWorkspaceButton")?.addEventListener("click", openWorkspacesPanel);
    $("#brandSearchButton")?.addEventListener("click", openGlobalSearchPanel);
    $("#helpMenuButton")?.addEventListener("click", openHelpPanel);
    $("#sidebarOpen").addEventListener("click", () => {
      if (window.matchMedia?.("(min-width: 1181px)").matches) setSidebarCollapsed(false);
      else {
        $("#sidebar").classList.add("open");
        $("#mobileScrim").classList.add("show");
      }
    });
    $("#codexMenuToggle")?.addEventListener("click", () => $("#sidebarOpen")?.click());
    $("#sidebarClose").addEventListener("click", () => {
      if (window.matchMedia?.("(min-width: 1181px)").matches) setSidebarCollapsed(true);
      else {
        $("#sidebar").classList.remove("open");
        $("#mobileScrim").classList.remove("show");
      }
    });
    $("#mobileScrim").addEventListener("click", () => {
      $("#sidebar").classList.remove("open");
      $("#inspector").classList.remove("open");
      $("#mobileScrim").classList.remove("show");
    });
    $("#inspectorToggle").addEventListener("click", () => {
      if (window.matchMedia?.("(min-width: 1181px)").matches) setInspectorCollapsed(!state.inspectorCollapsed);
      else $("#inspector").classList.toggle("open");
    });
    $("#inspectorClose").addEventListener("click", () => {
      if (window.matchMedia?.("(min-width: 1181px)").matches) setInspectorCollapsed(true);
      else $("#inspector").classList.remove("open");
    });
    window.addEventListener("resize", applyPaneLayout);
    $("#panelBody").addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && event.target.matches(".task-row[data-open-task]")) {
        event.preventDefault();
        event.target.click();
      }
    });
    $("#panelBody").addEventListener("change", (event) => {
      if (event.target.id === "modelSelect") {
        const value2 = String(event.target.value || "").trim();
        if (!value2) return;
        state.model = value2;
        localStorage.setItem("minicc-model", value2);
        showToast(state.locale === "zh" ? "\u65B0\u7684\u4EFB\u52A1\u5C06\u4F7F\u7528 " + value2 : "New tasks will use " + value2);
        return;
      }
      if (event.target.id !== "reasoningEffortSelect") return;
      const value = event.target.value;
      if (!REASONING_EFFORTS.includes(value)) return;
      state.reasoningEffort = value;
      localStorage.setItem("minicc-reasoning", value);
      updateReasoningControl();
      showToast(state.locale === "zh" ? "\u65B0\u7684\u4EFB\u52A1\u5C06\u4F7F\u7528 " + t("reasoning." + value) + " \u63A8\u7406\u5F3A\u5EA6" : "New tasks will use " + t("reasoning." + value) + " reasoning effort");
    });
    $("#panelBody").addEventListener("click", async (event) => {
      if (event.target.closest("#refreshModelCatalog")) {
        event.preventDefault();
        await loadModelCatalog();
        openSettingsPanel();
        return;
      }
      const timelineToggle = event.target.closest("[data-timeline-toggle]");
      if (timelineToggle) {
        setTimelineDetails(timelineToggle.closest(".execution-trail"), timelineToggle.dataset.timelineToggle === "expand");
        event.preventDefault();
        return;
      }
      if (event.target.closest("[data-copy-file]")) {
        event.preventDefault();
        copyFilePreviewContent();
        return;
      }
      const rewind = event.target.closest(".rewind-to-here");
      if (rewind) {
        event.preventDefault();
        rewindToUserIndex(rewind.dataset.userIndex);
        return;
      }
      const restore = event.target.closest("[data-restore-task]");
      if (restore) {
        event.preventDefault();
        restoreTaskSnapshot(restore.dataset.restoreTask);
        return;
      }
      const fileTarget = event.target.closest("[data-open-diff]");
      if (fileTarget) {
        openFilePreview(fileTarget.dataset.openDiff);
        return;
      }
      const pathNode = event.target.closest(".tool-path");
      if (pathNode && looksLikeWorkspacePath(pathNode.textContent)) {
        openFilePreview(pathNode.textContent.trim());
        return;
      }
      const target = event.target.closest("[data-cancel-task], [data-resume-task], [data-open-task], [data-open-detail], [data-replay-task], [data-select-workspace], [data-remove-worktree], [data-set-locale], [data-switch-session], [data-panel-action]");
      if (!target) return;
      if (target.dataset.replayTask) {
        try {
          await openReplayForTask(target.dataset.replayTask, () => openTaskDetail(target.dataset.replayTask));
        } catch (error) {
          showToast(error.message);
        }
        return;
      }
      if (target.dataset.openDetail) {
        openTaskDetail(target.dataset.openDetail);
        return;
      }
      if (target.dataset.resumeTask) {
        try {
          const task = await requestJson(`/api/tasks/${encodeURIComponent(target.dataset.resumeTask)}/resume`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
          closePanel();
          setSession(task.session_id || state.sessionId);
          const loadingId = addLoadingMessage();
          bindRunningTask(task, loadingId, task.session_id || state.sessionId);
          state.activeTaskId = task.task_id;
          setBusy(true);
          updateTaskDock(task);
          await loadTaskHistory();
          await watchTask(task.task_id);
        } catch (error) {
          showToast(error.message);
        } finally {
          if (!taskBySession.has(taskSessionKey(state.sessionId))) state.activeTaskId = null;
          setBusy(false);
        }
        return;
      }
      if (target.dataset.openTask) {
        openTaskInWorkspace(target.dataset.openTask);
        return;
      }
      if (target.dataset.selectWorkspace) {
        try {
          showToast(t("workspace.switching"));
          await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: target.dataset.selectWorkspace }) });
          await loadWorkspace();
          closePanel();
          showToast(state.locale === "zh" ? "\u5DE5\u4F5C\u533A\u5DF2\u5207\u6362" : "Workspace switched");
        } catch (error) {
          showToast(error.message);
        }
        return;
      }
      if (target.dataset.cancelTask) {
        try {
          await requestJson(`/api/tasks/${encodeURIComponent(target.dataset.cancelTask)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
          openActivityPanel();
        } catch (error) {
          showToast(error.message);
        }
        return;
      }
      if (target.dataset.removeWorktree) {
        try {
          await requestJson("/api/worktrees/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: target.dataset.removeWorktree }) });
          openWorkspacesPanel();
        } catch (error) {
          showToast(error.message);
        }
        return;
      }
      if (target.dataset.setLocale) {
        setLocale(target.dataset.setLocale);
        openSettingsPanel();
        return;
      }
      if (target.dataset.switchSession) {
        setSession(target.dataset.switchSession);
        closePanel();
        return;
      }
      if (target.dataset.panelAction === "activity") {
        openActivityPanel();
        return;
      }
      if (target.dataset.panelAction === "new-task") {
        closePanel();
        resetTask();
        return;
      }
      if (target.dataset.panelAction === "clear") {
        const key = sessionViewKey(state.sessionId);
        sessionMarkup.delete(key);
        localStorage.removeItem(key);
        renderSession(state.sessionId);
        closePanel();
        showToast(state.locale === "zh" ? "\u5F53\u524D\u89C6\u56FE\u5DF2\u6E05\u7A7A" : "Current view cleared");
        return;
      }
      if (target.dataset.panelAction === "export") {
        exportChat();
        closePanel();
        return;
      }
      if (target.dataset.panelAction === "reload") {
        loadWorkspace();
        closePanel();
        return;
      }
    });
    $("#panelBody").addEventListener("submit", async (event) => {
      if (event.target.id === "batchForm") {
        event.preventDefault();
        const form2 = event.target;
        const messages = [...form2.querySelectorAll("textarea[name=task]")].map((field) => field.value.trim()).filter(Boolean);
        if (messages.length < 2) {
          showToast(state.locale === "zh" ? "\u81F3\u5C11\u586B\u5199 2 \u4E2A\u5B50\u4EFB\u52A1" : "Add at least 2 subtasks");
          return;
        }
        try {
          const sharedContext = String(form2.elements.namedItem("shared_context")?.value || "").trim();
          const permissions = effectiveTaskPermissions();
          const created = await requestJson("/api/tasks/batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages, model: state.model, shared_context: sharedContext, message: state.locale === "zh" ? "\u5E76\u884C\u6267\u884C\u591A\u4E2A\u72EC\u7ACB\u5B50\u4EFB\u52A1" : "Run independent subtasks in parallel", session_id: state.sessionId, permission_mode: permissions.mode, allow_changes: permissions.allowChanges, allow_network: permissions.allowNetwork, reasoning_effort: state.reasoningEffort, workspace_path: state.workspacePath }) });
          const task = await requestJson(`/api/tasks/${encodeURIComponent(created.task_id)}`);
          closePanel();
          addUserMessage(task.message || (state.locale === "zh" ? "\u5E76\u884C\u6267\u884C\u591A\u4E2A\u72EC\u7ACB\u5B50\u4EFB\u52A1" : "Run independent subtasks in parallel"));
          const loadingId = addLoadingMessage();
          bindRunningTask(task, loadingId, task.session_id || state.sessionId);
          state.activeTaskId = task.task_id;
          setBusy(true);
          updateTaskDock(task);
          await loadTaskHistory();
          await watchTask(task.task_id);
        } catch (error) {
          showToast(error.message);
        } finally {
          setBusy(false);
        }
        return;
      }
      if (event.target.id === "workspaceSelectForm") {
        event.preventDefault();
        const form2 = event.target;
        const path = String(form2.elements.namedItem("path")?.value || "").trim();
        try {
          showToast(t("workspace.switching"));
          await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
          await loadWorkspace();
          closePanel();
          showToast(state.locale === "zh" ? "\u5DE5\u4F5C\u533A\u5DF2\u5207\u6362" : "Workspace switched");
        } catch (error) {
          showToast(error.message);
        }
        return;
      }
      if (event.target.id !== "worktreeForm") return;
      event.preventDefault();
      const form = event.target;
      const nameField = form.elements.namedItem("name");
      const branchField = form.elements.namedItem("branch");
      const name = String(nameField?.value || "").trim();
      const branch = String(branchField?.value || "").trim();
      try {
        await requestJson("/api/worktrees", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, branch: branch || void 0 }) });
        showToast(state.locale === "zh" ? "worktree \u5DF2\u521B\u5EFA" : "Worktree created");
        openWorkspacesPanel();
      } catch (error) {
        showToast(error.message);
      }
    });
    $("#promptInput").addEventListener("keydown", (event) => {
      if (handleMentionKeydown(event)) return;
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      sendMessage(event);
    });
    $("#promptInput").addEventListener("input", updateMentionPopover);
    $("#promptInput").addEventListener("keyup", (event) => {
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) updateMentionPopover();
    });
    $("#mentionPopover").addEventListener("mousedown", (event) => event.preventDefault());
    $("#mentionPopover").addEventListener("click", (event) => {
      const option = event.target.closest("[data-mention-index]");
      if (option) applyMentionOption(Number(option.dataset.mentionIndex));
    });
    document.addEventListener("click", (event) => {
      if (!mentionState.open) return;
      if (event.target === $("#promptInput") || $("#mentionPopover")?.contains(event.target)) return;
      closeMentionPopover();
    });
    $("#threadList").addEventListener("click", (event) => {
      const item = event.target.closest(".thread-item");
      if (!item) return;
      if (item.dataset.taskId) openTaskInWorkspace(item.dataset.taskId);
      else setSession(item.dataset.session);
    });
    $("#threadSearch").addEventListener("input", (event) => {
      const query = event.target.value.toLowerCase();
      document.querySelectorAll(".thread-item").forEach((item) => {
        item.hidden = !item.textContent.toLowerCase().includes(query);
      });
    });
    const authForm = $("#authForm");
    if (authForm) authForm.addEventListener("submit", submitAuthToken);
  }
  if (typeof location !== "undefined" && new URLSearchParams(location.search).get("arcade") === "1") {
    document.documentElement.dataset.arcade = "1";
  }
  document.addEventListener("DOMContentLoaded", () => {
    bindUI();
    updateMode();
    applyFocusMode();
    applyPaneLayout();
    switchInspectorTab(runtime.inspectorTab);
    const resizeViewport = () => {
      document.documentElement.style.setProperty("--app-height", `${window.visualViewport?.height || window.innerHeight}px`);
      document.documentElement.style.setProperty("--viewport-top", `${window.visualViewport?.offsetTop || 0}px`);
    };
    resizeViewport();
    window.visualViewport?.addEventListener("resize", resizeViewport, { passive: true });
    window.visualViewport?.addEventListener("scroll", resizeViewport, { passive: true });
    window.addEventListener("resize", resizeViewport, { passive: true });
    runtime.initialMessageMarkup = $("#messageList").innerHTML;
    setSession(state.sessionId);
    applyLocale();
    refreshIcons();
    prepareStartupSplash();
    loadWorkspace().then((online) => {
      if (online) {
        finishStartupSplash();
        return;
      }
      setStartupSplashError();
      window.setTimeout(finishStartupSplash, 420);
    }).catch(() => {
      setStartupSplashError();
      window.setTimeout(finishStartupSplash, 420);
    });
    if (document.documentElement.dataset.arcade === "1") openArcade().catch((error) => showToast(error.message));
    updateRunningLight();
    updateRunningLightDigest();
    window.setInterval(() => {
      if (!document.hidden) updateRunningLight();
    }, 45e3);
    window.setInterval(() => {
      if (!document.hidden) updateRunningLightDigest();
    }, 6e4);
    $("#runningLight")?.addEventListener("click", () => openLedgerPanel());
    window.setInterval(() => {
      if (!document.hidden) loadTaskHistory();
    }, 5e3);
    window.addEventListener("beforeunload", () => persistSessionView());
  });
  function exposeWorkbenchGlobals() {
    Object.assign(window, {
      $,
      $$,
      t,
      state,
      icon,
      refreshIcons,
      applyIcons,
      showToast,
      openPanel,
      closePanel,
      escapeHtml,
      eventTimelineMarkup,
      assistantMessageMarkup,
      visibleAgentEvents,
      addLoadingMessage,
      bindRunningTask,
      loadWorkspace,
      openArcade,
      applyTaskEvent,
      runningTasks,
      taskBySession,
      stopTaskTimer,
      updateLiveTask,
      syncLiveEvents,
      addAssistantMessage,
      updateTaskDock,
      renderTaskHistory,
      updateBoundTask,
      openFilePreview,
      openHelpPanel,
      setTimelineDetails
    });
  }
  exposeWorkbenchGlobals();
})();
