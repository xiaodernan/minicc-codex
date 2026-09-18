// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { renderSession } from "../chat/markdown.js";
import { t } from "./i18n.js";
import { $, $$, runtime, state } from "./state.js";
import { icon, refreshIcons } from "../icons.js";
import { isSessionBusy, renderTodoPanel, renderVerification, setConnection, showToast, updateMode, updateReasoningControl } from "../panels/index.js";

export function applyLocale() {
  document.documentElement.lang = state.locale === "zh" ? "zh-CN" : "en";
  $$(`[data-i18n]`).forEach((element) => { element.textContent = t(element.dataset.i18n); });
  $$(`[data-i18n-placeholder]`).forEach((element) => { element.placeholder = t(element.dataset.i18nPlaceholder); });
  $$(`[data-i18n-title]`).forEach((element) => { element.title = t(element.dataset.i18nTitle); });
  $$(`[data-i18n-aria]`).forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAria)); });
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
export function applyTheme() {
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
export function applyFocusMode() {
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
export function setFocusMode(enabled) {
  state.focusMode = Boolean(enabled);
  localStorage.setItem("minicc-focus-mode", String(state.focusMode));
  applyFocusMode();
}

export function applyPaneLayout() {
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

export function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = Boolean(collapsed);
  localStorage.setItem("minicc-sidebar-collapsed", String(state.sidebarCollapsed));
  applyPaneLayout();
}

export function setInspectorCollapsed(collapsed) {
  state.inspectorCollapsed = Boolean(collapsed);
  localStorage.setItem("minicc-inspector-collapsed", String(state.inspectorCollapsed));
  applyPaneLayout();
}

export function prepareStartupSplash() {
  const splash = $("#startupSplash");
  if (!splash) return;
  splash.dataset.state = "loading";
  splash.setAttribute("aria-busy", "true");
  splash.setAttribute("aria-hidden", "false");
  const status = $("#startupStatus");
  if (status) status.textContent = state.locale === "zh" ? "正在启动本地工作台" : "Starting local workbench";
}

export function setStartupSplashError() {
  const splash = $("#startupSplash");
  if (!splash) return;
  splash.dataset.state = "error";
  splash.setAttribute("aria-busy", "false");
  const status = $("#startupStatus");
  if (status) status.textContent = state.locale === "zh" ? "离线模式，正在进入工作台" : "Offline mode · entering workbench";
}

export function finishStartupSplash() {
  const splash = $("#startupSplash");
  if (!splash) return;
  splash.dataset.state = "ready";
  splash.setAttribute("aria-busy", "false");
  splash.setAttribute("aria-hidden", "true");
}

export function setTheme(theme) {
  state.theme = theme === "light" ? "light" : "dark";
  localStorage.setItem("minicc-theme", state.theme);
  applyTheme();
}

// Keep the vendored highlight.js color sheets in sync with the workbench
// theme. Both ship locally in web/vendor/; the inactive one is disabled so
// token colors always match the active data-theme.
export function syncHljsTheme() {
  const light = document.getElementById("hljsThemeLight");
  const dark = document.getElementById("hljsThemeDark");
  if (light instanceof HTMLLinkElement) light.disabled = state.theme !== "light";
  if (dark instanceof HTMLLinkElement) dark.disabled = state.theme !== "dark";
}

export function setLocale(locale) {
  state.locale = locale === "en" ? "en" : "zh";
  localStorage.setItem("minicc-locale", state.locale);
  applyLocale();
  showToast(state.locale === "zh" ? "已切换中文" : "Switched to English");
}
// Keep this module's public helpers grouped at the end of the bundle.
