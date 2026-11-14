// M8-T893: the Ctrl/Cmd+K command palette — one search box that reaches every
// surface of the workbench. Commands are data, matching is a scored subsequence
// search, and focus lives in the shared dialog lifecycle (core/dialog.js).
// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { activateDialog, deactivateDialog } from "./dialog.js";
import { t } from "./i18n.js";
import { setFocusMode, setInspectorCollapsed, setLocale, setSidebarCollapsed, setTheme } from "./locale.js";
import { openArcade } from "./arcade.js";
import { exportChat, openActivityPanel, openAlmanacPanel, openArchivePanel, openAxiomsPanel, openJournalPanel, openManualPanel, openBatchPanel, openHelpPanel, openLedgerPanel, openOptionsPanel, openSettingsPanel, openTaskListPanel, openTemplatesPanel, openWorkspacesPanel, resetTask } from "../chat/stream.js";
import { openGlobalSearchPanel, scrollChat, showToast } from "../panels/index.js";
import { $, state } from "./state.js";

let listNode = null;
let inputNode = null;
let activeIndex = 0;
let filtered = [];
let optionBaseId = "paletteOption";

function label(id, fallback) {
  const translated = t(id);
  return translated === id ? fallback : translated;
}

function commands() {
  const zh = state.locale === "zh";
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
    { id: "axioms", glyph: "scroll-text", group: "palette.group.task", run: () => openAxiomsPanel() },
    { id: "journal", glyph: "notebook-pen", group: "palette.group.task", run: () => openJournalPanel() },
    { id: "archive", glyph: "archive", group: "palette.group.task", run: () => openArchivePanel() },
    { id: "batch", glyph: "layers", group: "palette.group.task", run: () => openBatchPanel() },
    { id: "export", glyph: "download", group: "palette.group.task", run: () => exportChat() },
    { id: "settings", glyph: "settings-2", group: "palette.group.surface", run: () => openSettingsPanel() },
    { id: "options", glyph: "more-horizontal", group: "palette.group.surface", run: () => openOptionsPanel() },
    { id: "help", glyph: "circle-help", group: "palette.group.surface", run: () => openHelpPanel() },
    { id: "arcade", glyph: "gamepad-2", group: "palette.group.surface", run: () => openArcade() },
    { id: "theme", glyph: "moon-star", group: "palette.group.surface", labelOverride: themeTarget, run: () => setTheme(state.theme === "dark" ? "light" : "dark") },
    { id: "locale", glyph: "globe-2", group: "palette.group.surface", labelOverride: zh ? "切换到英文" : "Switch to Chinese", run: () => setLocale(zh ? "en" : "zh") },
    { id: "sidebar", glyph: "panel-left", group: "palette.group.surface", run: () => setSidebarCollapsed(!state.sidebarCollapsed) },
    { id: "inspector", glyph: "panel-right", group: "palette.group.surface", run: () => setInspectorCollapsed(!state.inspectorCollapsed) },
    { id: "focus", glyph: "scan-line", group: "palette.group.surface", run: () => setFocusMode(!state.focusMode) },
    { id: "jumpLatest", glyph: "chevrons-down", group: "palette.group.surface", run: () => scrollChat("auto", true) },
  ].map((item) => ({
    ...item,
    label: item.labelOverride || label(`palette.cmd.${item.id}`, item.id),
    hint: label(`palette.group.${item.group.split(".").pop()}`, item.group),
  }));
}

// Scored subsequence search, not naive substring filtering: "wrk" should reach
// "工作区与 Git worktree" only through pinyin-free keyword aliases, so every
// command carries latin keywords; matching prefers word starts and runs.
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
  filtered = query
    ? all.map((command) => ({ command, points: score(query, command) })).filter((entry) => entry.points >= 0)
        .sort((a, b) => b.points - a.points).map((entry) => entry.command)
    : all;
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
  // The local glyph table owns fallback characters; lucide SVGs need a refresh
  // pass the palette renders synchronously, so text glyphs keep zero-latency.
  const glyphs = { plus: "+", "list-checks": "☑", "folder-open": "🗂", search: "⌕", activity: "▥", ledger: "▤", sparkles: "✦", "book-open": "▤", layers: "≡", download: "↓", "settings-2": "⚙", "more-horizontal": "⋯", "circle-help": "?", "gamepad-2": "▶", "moon-star": "☾", "globe-2": "◎", "panel-left": "▤", "panel-right": "▧", "scan-line": "◫", "chevrons-down": "⌄" };
  return glyphs[name] || "›";
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

export function openCommandPalette() {
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
    if (event.key === "ArrowDown") { event.preventDefault(); move(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
    else if (event.key === "Enter") { event.preventDefault(); activate(activeIndex); }
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

export function closeCommandPalette() {
  const modal = $("#paletteModal");
  if (!modal.classList.contains("show")) return;
  deactivateDialog(modal);
  modal.classList.remove("show");
  modal.setAttribute("aria-hidden", "true");
  inputNode?.blur();
}

export function bindCommandPalette() {
  $("#paletteClose").addEventListener("click", closeCommandPalette);
  $("#paletteModal").addEventListener("pointerdown", (event) => {
    if (event.target.id === "paletteModal") closeCommandPalette();
  });
}
