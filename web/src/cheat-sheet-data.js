// The one source of truth for keyboard shortcuts. The manual chapter
// (chapter 4, "Commands & Shortcuts") and the `?` help panel both render
// from this — they cannot tell different stories about the same key.
// Each row: [zh, en, key]. Groups: [ id, zh, en ].

export const SHORTCUT_GROUPS = [
  {
    id: "compose",
    zh: "撰写",
    en: "Compose",
    rows: [
      ["发送任务", "Send the task", "Enter"],
      ["换行", "New line", "Shift+Enter"],
      ["提及文件", "Mention a file", "@"],
      ["斜杠命令", "Slash command", "/"],
    ],
  },
  {
    id: "navigation",
    zh: "逐行导航",
    en: "Line by line",
    rows: [
      ["上 / 下 / 左 / 右键导航", "Navigate with arrow keys", "← ↑ → ↓"],
      ["展开 / 收起树节点", "Expand or collapse a tree node", "→ / ←"],
      ["首行 / 末行", "First / last row", "Home / End"],
    ],
  },
  {
    id: "global",
    zh: "全局",
    en: "Global",
    rows: [
      ["新任务", "New task", "Ctrl / ⌘ N"],
      ["命令面板", "Command palette", "Ctrl / ⌘ K"],
      ["账本总览", "Ledger overview", "Ctrl / ⌘ L"],
      ["搜索任务", "Search tasks", "/"],
      ["快捷键速查", "Shortcut reference", "?"],
      ["关闭面板 / 小游戏", "Close panel / game", "Esc"],
    ],
  },
  {
    id: "arcade",
    zh: "游戏",
    en: "Arcade",
    rows: [
      ["选植物", "Pick a seed", "1-9"],
      ["暂停 / 继续", "Pause / resume", "P"],
      ["铲子", "Shovel", "E"],
    ],
  },
];

export function shortcutRows() {
  return SHORTCUT_GROUPS.flatMap((group) =>
    group.rows.map((row) => ({ group: group.id, zh: row[0], en: row[1], key: row[2] })));
}
