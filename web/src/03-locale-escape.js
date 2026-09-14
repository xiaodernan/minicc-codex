// NOTE: 源文件分片（web/src/）。此文件由 `npm run build:web` 按序拼接生成，勿直接编辑。
function applyLocale() {
  document.documentElement.lang = state.locale === "zh" ? "zh-CN" : "en";
  $$(`[data-i18n]`).forEach((element) => { element.textContent = t(element.dataset.i18n); });
  $$(`[data-i18n-placeholder]`).forEach((element) => { element.placeholder = t(element.dataset.i18nPlaceholder); });
  $$(`[data-i18n-title]`).forEach((element) => { element.title = t(element.dataset.i18nTitle); });
  $$(`[data-i18n-aria]`).forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAria)); });
  $("#localeZh")?.classList.toggle("active", state.locale === "zh");
  $("#localeEn")?.classList.toggle("active", state.locale === "en");
  renderedTaskListKey = "";
  updateReasoningControl();
  if ($("#messageList") && !isSessionBusy(state.sessionId)) renderSession(state.sessionId);
  updateMode();
  renderTodoPanel();
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
  const label = isLight
    ? (state.locale === "zh" ? "切换到暗色模式" : "Switch to dark mode")
    : (state.locale === "zh" ? "切换到亮色模式" : "Switch to light mode");
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
    sidebarButton.setAttribute("aria-label", state.sidebarCollapsed ? "打开侧栏" : "收起侧栏");
    sidebarButton.title = state.sidebarCollapsed ? "打开侧栏" : "收起侧栏";
    sidebarButton.innerHTML = icon(state.sidebarCollapsed ? "panel-left-open" : "panel-left-close");
  }
  if (inspectorButton && desktop) {
    inspectorButton.setAttribute("aria-label", state.inspectorCollapsed ? "打开检查器" : "收起检查器");
    inspectorButton.title = state.inspectorCollapsed ? "打开检查器" : "收起检查器";
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
  if (status) status.textContent = state.locale === "zh" ? "正在启动本地工作台" : "Starting local workbench";
}

function setStartupSplashError() {
  const splash = $("#startupSplash");
  if (!splash) return;
  splash.dataset.state = "error";
  splash.setAttribute("aria-busy", "false");
  const status = $("#startupStatus");
  if (status) status.textContent = state.locale === "zh" ? "离线模式，正在进入工作台" : "Offline mode · entering workbench";
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

// Keep the vendored highlight.js color sheets in sync with the workbench
// theme. Both ship locally in web/vendor/; the inactive one is disabled so
// token colors always match the active data-theme.
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
  showToast(state.locale === "zh" ? "已切换中文" : "Switched to English");
}

const SESSION_PRESETS = {
  "interview-1": {
    title: "Ship the agent UI",
    titleZh: "打造 Agent 工作台",
    subtitle: "Build, inspect, and verify inside one focused workspace.",
    subtitleZh: "在一个专注的工作区里构建、检查并验证。",
  },
  "specproof-review": {
    title: "Review specproof",
    titleZh: "审查 specproof",
    subtitle: "Trace the reference repo and keep the useful parts.",
    subtitleZh: "追踪参考仓库，只保留真正有价值的部分。",
    user: "评估 specproof 这个参考项目，判断哪些代码值得迁移。",
    answer: "我已经把参考项目拆成 CLI、工具协议和 Web 工作台三部分。保留工具调用和安全边界，UI 与会话层按当前项目重新组织。",
    events: [
      { name: "tree", status: "completed", summary: "Inspected 42 files · 0.31s" },
      { name: "read_file", status: "completed", summary: "Read README.md · 0.18s" },
    ],
  },
  "editor-hardening": {
    title: "Harden the editor",
    titleZh: "加固编辑器",
    subtitle: "Protect workspace edits with explicit, reviewable boundaries.",
    subtitleZh: "用明确、可审查的边界保护工作区修改。",
    user: "检查编辑器的路径保护、备份和过期 diff 防护。",
    answer: "编辑器已经限制在工作区内，写入采用原子替换并生成备份；edit_file 还会校验旧内容摘要，避免覆盖并发修改。",
    events: [
      { name: "grep", status: "completed", summary: "Checked editor guards · 0.22s" },
      { name: "git_diff", status: "completed", summary: "Reviewed pending changes · 0.16s" },
    ],
  },
  "provider-check": {
    title: "Provider smoke test",
    titleZh: "接口冒烟测试",
    subtitle: "Confirm the OpenAI-compatible transport before the interview.",
    subtitleZh: "面试前确认 OpenAI 兼容传输链路。",
    user: "验证自定义 OpenAI 兼容接口、工具调用和错误重试。",
    answer: "Provider smoke test 已通过：能读取项目结构、运行测试并返回中文总结；请求失败时会保留可读错误，不会泄露认证信息。",
    events: [
      { name: "read_file", status: "completed", summary: "Read provider contract · 0.12s" },
      { name: "pytest", status: "completed", summary: "9 passed · 1.42s" },
    ],
  },
};

const sessionMarkup = new Map();
const taskHistoryBySession = new Map();
const taskHistoryListBySession = new Map();
let initialMessageMarkup = "";
let sessionViewReady = false;
const SESSION_VIEW_PREFIX = "minicc-session-view:";
const TERMINAL_TASK_STATUSES = new Set(["completed", "failed", "cancelled", "interrupted"]);
const MAX_SESSION_VIEW_CHARS = 180_000;
const MAX_SEEN_EVENT_KEYS = 2048;
const MAX_RENDERED_TIMELINE_EVENTS = 240;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const liveStreamStates = new Map();
const taskEventSources = new Map();
const taskWatchers = new Map();
const runningTasks = new Map();
const taskBySession = new Map();
const taskTimerHandles = new Map();
const finalizedTaskIds = new Set();
const renderedHistoryKeys = new Map();
let renderedTaskListKey = "";
let changeRefreshTimer = 0;

function escapeHtml(value) {
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

let markdownVendorWarned = false;

function markdownVendorReady() {
  if (typeof marked !== "undefined") return true;
  if (!markdownVendorWarned) {
    markdownVendorWarned = true;
    console.warn("[minicc] web/vendor marked/highlight.js unavailable; using the lightweight fallback renderer.");
  }
  return false;
}

function escapeMarkdownSource(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;");
}

// marked receives pre-escaped text, so code token text is entity-encoded;
// decode back to plain text before handing it to highlight.js, which escapes
// its own output. The &amp; replacement must run last to avoid double decoding.
function decodeMarkdownEntities(value) {
  return String(value ?? "")
    .replaceAll("&#039;", "'")
    .replaceAll("&#39;", "'")
    .replaceAll("&quot;", '"')
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

function safeMarkdownUrl(href) {
  const value = String(href || "").trim();
  if (!value) return "";
  if (value.startsWith("#")) return value;
  if (!/^[a-z][a-z0-9+.-]*:/i.test(value)) return value; // scheme-less = relative path
  return /^(https?:|mailto:)/i.test(value) ? value : "";
}

function highlightFencedCode(code, language) {
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

function configureMarkdownEngine() {
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
