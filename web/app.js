(() => {
  // web/src/core/bounded-cache.js
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
  var MAX_ENTRIES = 24;
  var MAX_TOTAL_CHARS = 12e5;
  var MAX_ENTRY_CHARS = 18e4;
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
      if (!source || source.length > MAX_ENTRY_CHARS) storage.removeItem(key);
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
  var state = {
    sessionId: localStorage.getItem("minicc-session") || "interview-1",
    allowChanges: localStorage.getItem("minicc-allow") === "true",
    allowNetwork: localStorage.getItem("minicc-network") === "true",
    permissionMode: ["default", "plan", "acceptEdits", "yolo"].includes(localStorage.getItem("minicc-permission-mode")) ? localStorage.getItem("minicc-permission-mode") : "default",
    locale: localStorage.getItem("minicc-locale") || "zh",
    theme: ["light", "dark"].includes(localStorage.getItem("minicc-theme")) ? localStorage.getItem("minicc-theme") : "light",
    workspacePath: "",
    workspaceInfo: null,
    contextWindowTokens: 3e5,
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
  var runtime = {
    workspaceVersion: 0,
    inspectorTab: "changes",
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
  var MAX_SESSION_VIEW_CHARS = 18e4;
  var MAX_SEEN_EVENT_KEYS = 2048;
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
      "at.hint": "\u2191\u2193 \u9009\u62E9 \xB7 Enter \u8865\u5168 \xB7 Esc \u5173\u95ED",
      "protected.subtitle": "\u6BCF\u4E2A\u4EFB\u52A1\u5355\u72EC\u6388\u6743\u5199\u5165",
      "panel.title": "\u5DE5\u4F5C\u53F0",
      "cancel": "\u53D6\u6D88\u4EFB\u52A1",
      "working": "\u6267\u884C\u4E2D",
      "ready": "\u5C31\u7EEA",
      "phase.queued": "\u6392\u961F\u4E2D",
      "phase.planning": "\u6B63\u5728\u89C4\u5212",
      "phase.tool": "\u6B63\u5728\u4F7F\u7528\u5DE5\u5177",
      "phase.answering": "\u6B63\u5728\u751F\u6210\u56DE\u7B54",
      "phase.waiting": "\u7B49\u5F85\u6A21\u578B\u8F93\u51FA",
      "phase.review": "\u9A8C\u6536\u4E2D",
      "phase.merging": "\u6B63\u5728\u5408\u5E76\u5B50\u4EFB\u52A1",
      "phase.completed": "\u5DF2\u5B8C\u6210",
      "phase.failed": "\u6267\u884C\u5931\u8D25",
      "phase.cancelled": "\u5DF2\u53D6\u6D88",
      "phase.interrupted": "\u670D\u52A1\u91CD\u542F\u65F6\u4E2D\u65AD",
      "stream.live": "\u5B9E\u65F6\u56DE\u7B54",
      "stream.connected": "\u5B9E\u65F6\u8FDE\u63A5",
      "stream.reconnecting": "\u5B9E\u65F6\u8FDE\u63A5\u4E2D\u65AD\uFF0C\u6B63\u5728\u91CD\u8FDE",
      "stream.polling": "\u5B9E\u65F6\u8FDE\u63A5\u4E0D\u53EF\u7528\uFF0C\u6B63\u5728\u8F6E\u8BE2",
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
      "auth.title": "\u8BBF\u95EE\u9A8C\u8BC1",
      "auth.hint": "\u6B64\u670D\u52A1\u5DF2\u542F\u7528 token \u8BA4\u8BC1\u3002\u8BF7\u8F93\u5165 minicc-web \u542F\u52A8\u65F6\u663E\u793A\u3001\u6216\u4FDD\u5B58\u5728\u5DE5\u4F5C\u533A .minicc/web_token.json \u4E2D\u7684\u8BBF\u95EE token\u3002",
      "auth.tokenLabel": "\u8BBF\u95EE token",
      "auth.submit": "\u4FDD\u5B58\u5E76\u91CD\u8BD5",
      "diff.empty": "\u5F53\u524D\u6CA1\u6709\u53EF\u663E\u793A\u7684\u5DEE\u5F02\u3002",
      "diff.previewAria": "\u7EDF\u4E00\u5DEE\u5F02\u89C6\u56FE",
      "diff.oldLine": "\u65E7\u884C\u53F7",
      "diff.newLine": "\u65B0\u884C\u53F7"
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
      "at.hint": "Up/Down to choose \xB7 Enter to insert \xB7 Esc to close",
      "protected.subtitle": "Writes are gated per task",
      "panel.title": "Workspace",
      "cancel": "Cancel task",
      "working": "Working",
      "ready": "Ready",
      "phase.queued": "Queued",
      "phase.planning": "Planning",
      "phase.tool": "Running tools",
      "phase.answering": "Writing response",
      "phase.waiting": "Waiting for output",
      "phase.review": "Pending review",
      "phase.merging": "Merging subagents",
      "phase.completed": "Complete",
      "phase.failed": "Failed",
      "phase.cancelled": "Cancelled",
      "phase.interrupted": "Interrupted by restart",
      "stream.live": "Live response",
      "stream.connected": "Live connection",
      "stream.reconnecting": "Live connection interrupted, reconnecting",
      "stream.polling": "Live connection unavailable, polling",
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
      "auth.title": "Access verification",
      "auth.hint": "This service requires a token. Paste the token printed by minicc-web on startup, or stored in .minicc/web_token.json.",
      "auth.tokenLabel": "Access token",
      "auth.submit": "Save and retry",
      "diff.empty": "No diff to display.",
      "diff.previewAria": "Unified diff view",
      "diff.oldLine": "Old line",
      "diff.newLine": "New line"
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

  // web/src/core/task-reducer.js
  var LIMIT = 2048;
  var sequenceOf = (value) => Math.max(0, Number(value) || 0);
  var boundedAdd = (previous, value) => {
    const next = new Set(previous || []);
    if (value) next.add(value);
    while (next.size > LIMIT) next.delete(next.values().next().value);
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
        data.events = events.slice(-2048);
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
    return ["completed", "failed", "cancelled", "interrupted"].includes(data?.status);
  }
  async function completeTask(loadingId, data) {
    const taskId = data.task_id;
    if (finalizedTaskIds.has(taskId)) return data;
    finalizedTaskIds.add(taskId);
    const binding = runningTasks.get(taskId) || { taskId, sessionId: state.sessionId, workspacePath: state.workspacePath, loadingId };
    finishLiveTask(binding.loadingId || loadingId);
    stopTaskTimer(taskId);
    const finalData = data.status === "completed" ? data : { ...data, answer: data.answer || data.error || (data.status === "cancelled" ? "\u4EFB\u52A1\u5DF2\u53D6\u6D88\u3002" : "\u4EFB\u52A1\u5931\u8D25\u3002") };
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
      const pending2 = holder.querySelector(`#${CSS.escape(binding.loadingId || loadingId)}`);
      if (pending2) {
        const replacement = document.createElement("div");
        replacement.innerHTML = assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`);
        pending2.replaceWith(replacement.firstElementChild);
      } else {
        holder.insertAdjacentHTML("beforeend", assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`));
      }
      cacheSessionView(binding.sessionId, holder.innerHTML, binding.workspacePath);
    }
    if (finalData.status !== "completed") showToast(finalData.error || (finalData.status === "cancelled" ? "\u4EFB\u52A1\u5DF2\u53D6\u6D88" : "\u4EFB\u52A1\u5931\u8D25"));
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
      reader.onerror = () => reject(new Error(`\u65E0\u6CD5\u8BFB\u53D6\u56FE\u7247\uFF1A${file.name}`));
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
    try {
      const task = await requestJson("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, model: state.model, attachments: queuedAttachments.map(({ name, mime_type, data_url }) => ({ name, mime_type, data_url })), session_id: sessionId, permission_mode: permissions.mode, allow_changes: permissions.allowChanges, allow_network: permissions.allowNetwork, reasoning_effort: state.reasoningEffort, workspace_path: workspacePath })
      });
      bindRunningTask(task, loadingId, sessionId);
      releaseSubmission();
      if (isCurrentScope()) state.activeTaskId = task.task_id;
      updateTaskDock(task);
      await loadTaskHistory();
      await watchTask(task.task_id);
    } catch (error) {
      finishLiveTask(loadingId);
      document.getElementById(loadingId)?.remove();
      if (isCurrentScope()) addAssistantMessage({ error: error.message });
      showToast(error.message);
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
    const tick = () => {
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
      window.setTimeout(tick, 850);
    };
    tick();
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
      if (!localStorage.getItem("minicc-reasoning") && ["low", "mid", "high", "xhigh", "max", "ultra"].includes(info.reasoning_effort)) state.reasoningEffort = info.reasoning_effort;
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
  function changeFileRow(item) {
    const path = String(item.path || "");
    const status = String(item.status || "clean");
    const additions = Number(item.additions || 0);
    const deletions = Number(item.deletions || 0);
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
    if (summary) summary.innerHTML = `<span class="diff-add">+ ${compactNumber(data?.additions || 0)}</span><span class="diff-del">- ${compactNumber(data?.deletions || 0)}</span>`;
    const tabCount = $("#changeTabCount");
    if (tabCount) tabCount.textContent = String(files.length);
    const changeList = $("#changeList");
    if (changeList) {
      changeList.innerHTML = files.length ? files.map((item) => `<button class="change-item change-item-button" data-open-diff="${escapeHtml(item.path)}"><span class="change-bar ${item.status === "added" ? "added" : item.status === "deleted" ? "deleted" : "changed"}"></span><span><strong>${escapeHtml(item.path)}</strong><small>${escapeHtml(changeStatusLabel(item.status))} \xB7 <span class="diff-add">+${Number(item.additions || 0)}</span> <span class="diff-del">-${Number(item.deletions || 0)}</span></small></span><span class="change-time">${escapeHtml(t("changes.now"))}</span></button>`).join("") : `<div class="change-item"><span class="change-bar muted"></span><span><strong>${escapeHtml(t("changes.clean"))}</strong><small>${escapeHtml(t("changes.cleanHint"))}</small></span><span class="change-time">--</span></div>`;
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
      expand.title = "\u5C55\u5F00\u5168\u5C4F";
      expand.setAttribute("aria-label", "\u5C55\u5F00\u5168\u5C4F");
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
    button.title = fullscreen ? "\u9000\u51FA\u5168\u5C4F" : "\u5C55\u5F00\u5168\u5C4F";
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
      const resume = ["failed", "cancelled", "interrupted"].includes(task.status) ? `<button class="panel-primary" data-resume-task="${escapeHtml(task.task_id)}">${t("tasks.resume")}</button>` : "";
      const restore = `<button class="panel-secondary" data-restore-task="${escapeHtml(task.task_id)}">${icon("rotate-ccw")} ${escapeHtml(t("restore.action"))}</button>`;
      const attachments = attachmentMarkup(task.attachments || []);
      openPanel(`${t("tasks.open")} \xB7 ${task.task_id}`, `<div class="task-detail"><div class="task-detail-status"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div><div class="task-detail-actions task-detail-top-actions"><button class="panel-secondary" data-open-task="${escapeHtml(task.task_id)}">${icon("arrow-up-right")} ${escapeHtml(t("tasks.openSession"))}</button>${restore}</div>${runtimeMetricsMarkup(task)}<div class="panel-section-title">${t("workspace.current")}</div><code class="task-detail-path">${escapeHtml(task.workspace_path || "")}</code><div class="panel-section-title">Prompt</div><div class="task-detail-prompt">${formatText(task.prompt || task.preview || "")}</div>${attachments ? `<div class="panel-section-title">Images</div>${attachments}` : ""}<div class="panel-section-title">Response</div><div class="task-detail-answer">${formatText(task.answer || task.stream_text || task.error || "")}</div>${execution ? `<div class="panel-section-title">Tools & stage trace</div>${execution}` : ""}${children}${resume ? `<div class="task-detail-actions">${resume}</div>` : ""}</div>`, { immersive: true });
    } catch (error) {
      if (!current()) return;
      openPanel(t("tasks.open"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
    }
  }
  function openBatchPanel() {
    const taskFields = [1, 2, 3].map((index) => `<label class="batch-field"><span>${escapeHtml(t("batch.task"))} ${index}</span><textarea name="task" rows="3" placeholder="${escapeHtml(state.locale === "zh" ? "\u4F8B\u5982\uFF1A\u68C0\u67E5\u540E\u7AEF\u6D4B\u8BD5\u5E76\u603B\u7ED3\u98CE\u9669" : "For example: inspect backend tests and summarize risks")}"></textarea></label>`).join("");
    openPanel(t("panel.batch"), `<form class="batch-form" id="batchForm"><div class="batch-heading"><span class="eyebrow">${escapeHtml(t("batch.title"))}</span><h3>${escapeHtml(t("batch.title"))}</h3><p>${escapeHtml(t("batch.subtitle"))}</p></div><div class="batch-fields">${taskFields}</div><label class="batch-field"><span>${escapeHtml(t("batch.context"))}</span><textarea name="shared_context" rows="3" placeholder="${escapeHtml(t("batch.note"))}"></textarea></label><div class="task-detail-actions"><button class="panel-primary" type="submit">${icon("play")} ${escapeHtml(t("batch.run"))}</button></div></form>`, { wide: true });
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
    const effortMarkup = ["low", "mid", "high", "xhigh", "max", "ultra"].map((effort) => '<option value="' + effort + '" ' + (state.reasoningEffort === effort ? "selected" : "") + ">" + escapeHtml(t("reasoning." + effort)) + "</option>").join("");
    const languageButtons = '<div class="settings-block"><span>' + t("panel.language") + "</span><strong>" + current + '</strong><div class="settings-locale"><button class="locale-option ' + (state.locale === "zh" ? "active" : "") + '" data-set-locale="zh">\u4E2D\u6587</button><button class="locale-option ' + (state.locale === "en" ? "active" : "") + '" data-set-locale="en">English</button></div></div>';
    const modelNote = state.modelCatalogError || (state.locale === "zh" ? "\u4ECE\u5F53\u524D\u7F51\u5173\u8BFB\u53D6\u53EF\u7528\u6A21\u578B\uFF1B\u65B0\u7684\u4EFB\u52A1\u4F1A\u4F7F\u7528\u6B64\u9009\u62E9\u3002" : "Loads models from the configured gateway; new tasks use this choice.");
    const modelBlock = `<div class="settings-block"><span>${t("panel.model")}</span><div class="settings-model"><select id="modelSelect" aria-label="${escapeHtml(t("panel.model"))}">${modelOptionsMarkup()}</select><button type="button" class="panel-secondary model-refresh" id="refreshModelCatalog" title="${escapeHtml(t("panel.modelRefresh"))}">\u21BB</button></div><small class="settings-note">${escapeHtml(modelNote)}</small></div>`;
    const reasoningBlock = '<div class="settings-block"><span>' + t("panel.reasoning") + '</span><div class="settings-effort"><select id="reasoningEffortSelect" aria-label="' + escapeHtml(t("panel.reasoning")) + '">' + effortMarkup + '</select></div><small class="settings-note">' + escapeHtml(t("panel.reasoningNote")) + "</small></div>";
    const sandboxBlock = '<div class="settings-block"><span>' + t("panel.sandbox") + "</span><strong>" + (state.locale === "zh" ? "\u89C1\u5DE5\u4F5C\u533A\u9762\u677F" : "See Workspaces") + "</strong></div>";
    const rewindBlock = '<div class="settings-block settings-rewind"><span>' + escapeHtml(t("rewind.advanced")) + '</span><form id="rewindForm" class="rewind-form"><label class="rewind-label"><span>' + escapeHtml(t("rewind.keepLabel")) + '</span><input id="rewindKeep" type="number" min="1" value="3" required aria-label="' + escapeHtml(t("rewind.keepLabel")) + '" /></label><button class="send-button rewind-button" type="submit">' + escapeHtml(t("rewind.action")) + '</button></form><small class="settings-note">' + escapeHtml(t("rewind.hint")) + "</small></div>";
    const allowlistBlock = '<div class="settings-block" id="allowlistEditor"><span>' + escapeHtml(t("allowlist.title")) + '</span><small class="settings-note">' + escapeHtml(t("allowlist.hint")) + '</small><form id="allowlistForm" class="allowlist-form"><label><span>' + escapeHtml(t("allowlist.commands")) + '</span><textarea id="allowlistCommands" rows="3"></textarea></label><label><span>' + escapeHtml(t("allowlist.paths")) + '</span><textarea id="allowlistPaths" rows="3"></textarea></label><label><span>' + escapeHtml(t("allowlist.tools")) + '</span><textarea id="allowlistTools" rows="2"></textarea></label><button class="send-button" type="submit">' + escapeHtml(t("allowlist.save")) + "</button></form></div>";
    openPanel(t("panel.settings"), languageButtons + modelBlock + reasoningBlock + sandboxBlock + rewindBlock + allowlistBlock);
    bindAllowlistEditor();
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
    runtime.inspectorTab = ["changes", "files", "verification"].includes(tab) ? tab : "changes";
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
    const rows = state.locale === "zh" ? [["\u53D1\u9001\u4EFB\u52A1", "Enter"], ["\u6362\u884C", "Shift+Enter"], ["\u65B0\u4EFB\u52A1", "Ctrl/\u2318 N"], ["\u641C\u7D22\u4EFB\u52A1", "/"], ["\u5173\u95ED\u9762\u677F / \u5C0F\u6E38\u620F", "Esc"]] : [["Send task", "Enter"], ["Newline", "Shift+Enter"], ["New task", "Ctrl/\u2318 N"], ["Search tasks", "/"], ["Close panel / game", "Esc"]];
    const list = rows.map(([label, key]) => `<div class="help-shortcut"><span>${escapeHtml(label)}</span><kbd>${escapeHtml(key)}</kbd></div>`).join("");
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
      const label = t("panel.reasoning") + ": " + t("reasoning." + state.reasoningEffort);
      button.title = label;
      button.setAttribute("aria-label", label);
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
    if (data?.started_at && ["queued", "running"].includes(data.status)) {
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
  var PERMISSION_MODES = ["default", "plan", "acceptEdits", "yolo"];
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
    const zh = state.locale === "zh";
    const write = effective.mode === "acceptEdits" || effective.allowChanges;
    const command = effective.allowChanges;
    const label = $("#modeLabel");
    if (label) label.textContent = t("capability.executeToggle");
    const summary = zh ? `\u6587\u4EF6\uFF1A${write ? "\u53EF\u5199" : "\u53EA\u8BFB"} \xB7 \u547D\u4EE4\uFF1A${command ? "\u5141\u8BB8" : "\u4EC5\u5B89\u5168\u68C0\u67E5"} \xB7 \u8054\u7F51\uFF1A${effective.allowNetwork ? "\u5141\u8BB8" : "\u5173\u95ED"}` : `Files: ${write ? "write" : "read"} \xB7 Commands: ${command ? "enabled" : "safe checks"} \xB7 Network: ${effective.allowNetwork ? "on" : "off"}`;
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
      status: ["pending", "in_progress", "completed"].includes(String(todo.status)) ? String(todo.status) : "pending",
      priority: ["high", "medium", "low"].includes(String(todo.priority)) ? String(todo.priority) : "medium"
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
    fileTreeState.requestToken += 1;
    fileTreeState.loaded = false;
    fileTreeState.pending.clear();
    fileTreeState.children.clear();
    fileTreeState.fileIndex = [];
    fileTreeState.rootEntries = [];
    loadFileTree();
  }
  var MENTION_MAX_OPTIONS = 8;
  var mentionState = { open: false, options: [], active: 0, matchStart: -1 };
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
    const body = options.length ? options.map((item, index) => `<button type="button" class="mention-option${index === mentionState.active ? " active" : ""}" role="option" aria-selected="${index === mentionState.active ? "true" : "false"}" data-mention-index="${index}" aria-label="${escapeHtml(item.path)}"><span class="mention-path">${escapeHtml(item.path)}</span><small class="mention-size">${escapeHtml(formatBytes(item.size))}</small></button>`).join("") : `<div class="mention-empty">${escapeHtml(t("at.empty"))}</div>`;
    popover.innerHTML = `${body}<div class="mention-hint" aria-hidden="true">${escapeHtml(t("at.hint"))}</div>`;
    popover.hidden = false;
    popover.querySelector(`[data-mention-index="${mentionState.active}"]`)?.scrollIntoView({ block: "nearest" });
  }
  function updateMentionPopover() {
    const input = $("#promptInput");
    if (!input) return;
    ensureMentionIndex();
    const token = mentionTokenAt(input.value, input.selectionStart ?? input.value.length);
    if (!token) {
      closeMentionPopover();
      return;
    }
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
    if (!option || !input) {
      closeMentionPopover();
      return;
    }
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
    const zh = state.locale === "zh";
    if (seconds < 60) return zh ? "\u521A\u521A" : "just now";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return zh ? `${minutes} \u5206\u949F\u524D` : `${minutes}m ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return zh ? `${hours} \u5C0F\u65F6\u524D` : `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days < 30) return zh ? `${days} \u5929\u524D` : `${days}d ago`;
    return new Date(epoch).toLocaleDateString(zh ? "zh-CN" : "en-US");
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
      tool: "phase.tool",
      answering: "phase.answering",
      review: "phase.review",
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
    return ["queued", "planning", "tool", "answering", "review", "merging", "completed", "failed", "cancelled", "interrupted"].includes(value) ? value : "planning";
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
    const zh = state.locale === "zh";
    if (!events.length) {
      target.innerHTML = `<div class="verification-empty">${icon("shield-check")}<strong>${zh ? "\u5C1A\u65E0\u9A8C\u8BC1\u8BC1\u636E" : "No verification evidence yet"}</strong><span>${zh ? "\u4EFB\u52A1\u6267\u884C\u7684\u68C0\u67E5\u548C\u5B8C\u6210\u8BC4\u4F30\u4F1A\u663E\u793A\u5728\u8FD9\u91CC\u3002" : "Checks and completion assessments will appear here."}</span></div>`;
      return;
    }
    target.innerHTML = events.slice(-12).reverse().map((event) => `<details class="verification-card" data-status="${escapeHtml(event.status || "pending")}"><summary>${icon(event.status === "error" ? "alert-circle" : "list-checks")}<span>${escapeHtml(event.summary || traceLabel(event))}</span></summary><pre>${escapeHtml(JSON.stringify(event.detail || {}, null, 2))}</pre></details>`).join("");
  }
  function runtimeMetricsMarkup(data) {
    const metrics = data?.metrics;
    if (!metrics || typeof metrics !== "object" || !metrics.workflow && !metrics.verification_runs && !metrics.trace_events) return "";
    const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
    const duration = formatDuration(metrics.duration_seconds || 0);
    return `<div><div class="panel-section-title">${escapeHtml(t("tasks.runtime"))}</div><div class="status-grid"><div><span>${escapeHtml(t("tasks.workflow"))}</span><strong>${escapeHtml(String(metrics.workflow || "coding"))}</strong><small>${escapeHtml(String(metrics.phase || data.phase || ""))}</small></div><div><span>${escapeHtml(t("tasks.repairs"))}</span><strong>${escapeHtml(String(metrics.repair_attempts || 0))}</strong><small>${escapeHtml(duration)}</small></div><div><span>${escapeHtml(t("tasks.verifications"))}</span><strong>${escapeHtml(String(metrics.verification_runs || 0))}</strong><small>${escapeHtml(String(metrics.verification_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.cache"))}</span><strong>${escapeHtml(cacheMetric(data))}</strong><small>${escapeHtml(String(metrics.cache_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.traces"))}</span><strong>${escapeHtml(String(metrics.trace_events || 0))}</strong><small>${escapeHtml(`${budget.turns || 0} turns \xB7 ${budget.tool_calls || 0} tools`)}</small></div></div></div>`;
  }
  function updateInspectorMetrics(data) {
    if (!data) return;
    const tokens = Number(data.tokens_used?.total_tokens || 0);
    const context = Number(data.context?.tokens || 0);
    const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 3e5);
    $("#tokenMetric").textContent = compactNumber(tokens);
    $("#contextMetric").textContent = `${compactNumber(context)}/${compactNumber(limit)}`;
    $("#cacheMetric").textContent = cacheMetric(data);
    $("#compactionMetric").textContent = String(data.compaction_events?.length || 0);
    $("#contextCount").textContent = taskMetrics(data);
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
    badge.hidden = !data;
    if (!data) {
      label.textContent = t("inspector.ready");
      return;
    }
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
  function structuredDetailMarkup(detail, label = state.locale === "zh" ? "\u67E5\u770B\u7ED3\u6784\u5316\u4F9D\u636E" : "View structured evidence") {
    if (detail == null || typeof detail === "object" && !Object.keys(detail).length) return "";
    const raw = detailJson(detail);
    return `<details class="event-detail"><summary>${escapeHtml(label)}<small>${escapeHtml(state.locale === "zh" ? "\u70B9\u51FB\u5C55\u5F00" : "click to expand")}</small></summary><pre>${escapeHtml(raw)}</pre></details>`;
  }
  function traceDetailPreview(event) {
    const detail = event?.detail;
    if (detail == null) return "";
    if (typeof detail !== "object" || Array.isArray(detail)) return detailValueText(detail, 96);
    const labels = state.locale === "zh" ? { turn: "\u8F6E\u6B21", previous_turn: "\u4E0A\u4E00\u8F6E", tool_count: "\u5DE5\u5177", results: "\u7ED3\u679C", observed: "\u5DF2\u89C2\u5BDF", observations: "\u89C2\u5BDF", constraints: "\u7EA6\u675F", failed_tools: "\u5931\u8D25", verification_required: "\u9700\u9A8C\u8BC1", recovery_inspection_required: "\u5199\u5165\u4FDD\u62A4", assessment: "\u53CD\u9988", trigger: "\u89E6\u53D1", next_action: "\u4E0B\u4E00\u6B65" } : { turn: "turn", previous_turn: "previous", tool_count: "tools", results: "results", observed: "observed", observations: "observations", constraints: "constraints", failed_tools: "failed", verification_required: "verify", recovery_inspection_required: "write guard", assessment: "assessment", trigger: "trigger", next_action: "next" };
    const parts = [];
    for (const key of ["turn", "previous_turn", "tool_count", "results", "observed", "observations", "constraints", "failed_tools", "verification_required", "recovery_inspection_required", "assessment", "trigger", "next_action"]) {
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
    const label = labels[String(event?.code || "")] || (state.locale === "zh" ? "\u67E5\u770B\u9636\u6BB5\u8BE6\u60C5" : "View stage details");
    const preview = traceDetailPreview(event);
    const readable = detailText ? `<div class="trace-detail">${escapeHtml(detailText)}</div>` : "";
    return `<details class="trace-evidence"><summary><span>${escapeHtml(label)}</span><small>${escapeHtml(preview)}</small><span class="trace-evidence-chevron">${icon("chevron-down")}</span></summary><div class="trace-evidence-body">${readable}${evidenceMarkup || ""}</div></details>`;
  }
  function toolResultFoldMarkup(label, content) {
    return `<details class="tool-result-fold"><summary><span>${escapeHtml(label)}</span><small>${escapeHtml(state.locale === "zh" ? "\u70B9\u51FB\u5C55\u5F00" : "click to expand")}</small><span class="tool-result-fold-chevron">${icon("chevron-down")}</span></summary><div class="tool-result-fold-body">${content}</div></details>`;
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
    const keys = ["turn", "previous_turn", "tool_count", "tools", "answer_chars", "duration_ms", "duration_seconds", "count", "names", "statuses", "max_turns", "turn_policy", "child_count", "child", "failed", "retry", "retry_limit", "partial_chars", "error_type", "requested", "active", "wire_value", "task_id", "tokens", "automatic", "complexity_score", "complexity_threshold", "complexity_reasons", "attempt", "confidence", "rationale", "missing", "next_action", "evidence", "error", "trigger", "observed", "observations", "constraints", "basis", "public_plan", "results", "structured_data", "new_information", "failed_tools", "needs_repair", "verification_required", "assessment", "replan_trigger", "parallel_mode", "max_concurrency", "dependency_shape", "merge_strategy", "parallel_results", "merge_basis", "result_summary", "turns", "tool_calls"];
    for (const key of keys) {
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
      const tracePhase = event.code === "run_finished" ? "review" : event.phase;
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
    const answer = data.answer || data.error || "\u6A21\u578B\u6CA1\u6709\u8FD4\u56DE\u53EF\u4EA4\u4ED8\u6587\u5B57\u3002";
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
            const label = token ? typeof this?.parser?.parseInline === "function" ? this.parser.parseInline(token.tokens || []) : escapeHtml(token.text || "") : escapeHtml(text ?? "");
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
    const answer = task.answer || task.error || "\u4EFB\u52A1\u6CA1\u6709\u8FD4\u56DE\u53EF\u4EA4\u4ED8\u6587\u5B57\u3002";
    const rawStream = !task.answer && task.stream_text ? rawOutputMarkup(task.stream_text) : "";
    const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
    const taskAnchor = escapeHtml(`task-${task.task_id || task.created_at || prompt.slice(0, 40)}`);
    const attachments = attachmentMarkup(task.attachments || []);
    const batchSummary = task.task_kind === "batch" && Array.isArray(task.children) ? `<div class="batch-child-summary"><div class="batch-child-heading"><strong>${escapeHtml(state.locale === "zh" ? "\u5206\u5C42\u5E76\u884C\u7ED3\u679C" : "Layered parallel results")}</strong><small>${escapeHtml(state.locale === "zh" ? "\u53EA\u8BFB\u5B50\u4EFB\u52A1\u5E76\u884C \u2192 \u4E3B Agent \u5408\u5E76\u4E0E\u590D\u6838" : "Readonly children in parallel -> parent merge and review")}</small></div>${task.children.map((child, index) => {
      const metrics = child.metrics && typeof child.metrics === "object" ? child.metrics : {};
      const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
      const answer2 = String(child.answer || child.error || child.stream_text || "").replace(/\s+/g, " ").trim();
      const evidence = (Array.isArray(child.events) ? child.events : []).filter((event) => event?.summary).slice(-2).map((event) => event.summary).join("\uFF1B");
      return `<details class="batch-child"><summary><span class="task-state ${child.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(child.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(`${t("batch.task")} ${index + 1}`)}</strong><small>${escapeHtml(`${phaseLabel(child)} \xB7 ${budget.turns || 0} turns \xB7 ${budget.tool_calls || 0} tools`)}</small><span class="batch-child-chevron">${icon("chevron-down")}</span></summary><div class="batch-child-detail">${answer2 ? `<p>${escapeHtml(answer2.slice(0, 900))}</p>` : ""}${evidence ? `<small>${escapeHtml(evidence.slice(0, 700))}</small>` : ""}</div></details>`;
    }).join("")}</div>` : "";
    const execution = executionTrailMarkup(events, task.events || []);
    return `<article class="message user-message" data-chat-anchor="${taskAnchor}-prompt"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(task.created_at || t("message.now"))}</time><button type="button" class="rewind-to-here" data-user-index="0">${escapeHtml(t("rewind.toHere"))}</button></div><div class="message-body"><div class="message-text">${formatText(prompt)}</div>${attachments}</div></article><article class="message assistant-message" data-chat-anchor="${taskAnchor}-answer"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>${escapeHtml(task.finished_at || task.created_at || t("message.now"))}</time></div><div class="message-body"><div class="history-result-head"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div>${execution}<div class="answer-callout">${formatText(answer)}</div>${batchSummary}${rawStream}</div></article>`;
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
    if (["failed", "cancelled", "interrupted"].includes(status)) return "amber";
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
    const pending2 = runtime.historyPending;
    if (pending2?.path === path && pending2.version === version) return pending2.promise;
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
    if (meta) meta.content = state.theme === "light" ? "#f6f7f9" : "#111214";
    const button = $("#themeButton");
    if (!button) return;
    const isLight = state.theme === "light";
    const label = isLight ? state.locale === "zh" ? "\u5207\u6362\u5230\u6697\u8272\u6A21\u5F0F" : "Switch to dark mode" : state.locale === "zh" ? "\u5207\u6362\u5230\u4EAE\u8272\u6A21\u5F0F" : "Switch to light mode";
    button.setAttribute("aria-label", label);
    button.title = label;
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
      sidebarButton.setAttribute("aria-label", state.sidebarCollapsed ? "\u6253\u5F00\u4FA7\u680F" : "\u6536\u8D77\u4FA7\u680F");
      sidebarButton.title = state.sidebarCollapsed ? "\u6253\u5F00\u4FA7\u680F" : "\u6536\u8D77\u4FA7\u680F";
      sidebarButton.innerHTML = icon(state.sidebarCollapsed ? "panel-left-open" : "panel-left-close");
    }
    if (inspectorButton && desktop) {
      inspectorButton.setAttribute("aria-label", state.inspectorCollapsed ? "\u6253\u5F00\u68C0\u67E5\u5668" : "\u6536\u8D77\u68C0\u67E5\u5668");
      inspectorButton.title = state.inspectorCollapsed ? "\u6253\u5F00\u68C0\u67E5\u5668" : "\u6536\u8D77\u68C0\u67E5\u5668";
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
      const additions = Number(diff.additions || 0);
      const deletions = Number(diff.deletions || 0);
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
    $("#gameCanvas")?.addEventListener("click", (event) => {
      if (window.collectSun?.(event)) return;
      window.plantAt?.(event);
    });
    $("#gameCanvas")?.addEventListener("pointermove", (event) => window.updateGameHover?.(event), { passive: true });
    $("#gameCanvas")?.addEventListener("pointerleave", () => window.clearGameHover?.(), { passive: true });
    document.querySelectorAll(".seed-card").forEach((card) => card.addEventListener("click", () => window.selectPlant?.(card)));
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
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
      if (event.key === "/" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "INPUT") {
        event.preventDefault();
        $("#threadSearch").focus();
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
      if (!["low", "mid", "high", "xhigh", "max", "ultra"].includes(value)) return;
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
      const target = event.target.closest("[data-cancel-task], [data-resume-task], [data-open-task], [data-open-detail], [data-select-workspace], [data-remove-worktree], [data-set-locale], [data-switch-session], [data-panel-action]");
      if (!target) return;
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
