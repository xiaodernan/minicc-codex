const state = {
  sessionId: localStorage.getItem("minicc-session") || "interview-1",
  allowChanges: localStorage.getItem("minicc-allow") !== "false",
  allowNetwork: localStorage.getItem("minicc-network") === "true",
  locale: localStorage.getItem("minicc-locale") || "zh",
  theme: ["light", "dark"].includes(localStorage.getItem("minicc-theme"))
    ? localStorage.getItem("minicc-theme")
    : (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark"),
  workspacePath: "",
  workspaceInfo: null,
  contextWindowTokens: 300000,
  reasoningEffort: ["low", "mid", "high", "xhigh", "max"].includes(localStorage.getItem("minicc-reasoning")) ? localStorage.getItem("minicc-reasoning") : "high",
  busy: false,
  submitting: false,
  focusMode: localStorage.getItem("minicc-focus-mode") === "true",
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

const I18N = {
  zh: {
    "brand.caption": "本地智能工作台", "newTask.label": "新任务", "newTask.title": "创建一个新任务",
    "search.placeholder": "搜索任务", "nav.main": "主导航", "nav.tasks": "任务", "nav.workspaces": "工作区", "nav.promo": "宣传页", "nav.activity": "活动", "nav.arcade": "小游戏",
    language: "界面语言", "tasks.more": "更多任务", "workspace.connected": "本地服务已连接", "profile.label": "当前模式",
    "inspector.toggle": "切换检查器", "inspector.close": "关闭检查器", "focus.enter": "专注阅读", "focus.exit": "退出专注阅读", "options.open": "更多选项", "composer.inputLabel": "输入任务",
    "composer.allowChanges": "允许当前任务修改文件或执行命令", "composer.allowNetwork": "允许当前任务联网搜索", "cancel.title": "取消任务", "send.title": "发送任务", "files.refresh": "刷新文件",
    "sidebar.close": "关闭侧栏", "sidebar.open": "打开侧栏", "search.shortcut": "搜索快捷键",
    recentTasks: "最近任务", "profile.mode": "面试模式", "profile.local": "仅本地", workspace: "工作区", agentSession: "智能会话", live: "运行中",
    "connection.connecting": "连接中", "connection.connected": "已连接", "connection.offline": "离线", "mode.localSafe": "本地 / 安全", "mode.localFull": "本地 / 完全访问",
    "composer.workingIn": "工作目录", "context.empty": "0 / 300k 上下文", "context.used": "已使用 tokens", "date.today": "今天",
    "composer.placeholder": "让 minicc 检查、构建或验证...", "composer.attach": "图片", "quick.plan": "计划", "quick.review": "审查", "quick.verify": "验证", "quick.parallel": "并行", "quick.demo": "演示流程",
    "mode.safe": "只读保护", "mode.changes": "完全访问", "composer.fullAccess": "完全访问：Agent 可以读写文件并执行命令。", "composer.readOnly": "只读保护：写入和命令执行会被跳过。",
    "inspector.overview": "概览", "inspector.changes": "改动", "inspector.files": "关注文件", "protected.title": "受保护工作区",
    "inspector.pulse": "项目状态", "inspector.live": "实时", "inspector.ready": "就绪", "inspector.standingBy": "Agent 正在等待",
    "inspector.turns": "轮次", "inspector.tools": "工具", "inspector.tokens": "Tokens", "inspector.context": "上下文", "inspector.compactions": "自动压缩", "changes.latest": "最近改动",
    "files.main": "CLI 入口", "files.loop": "工具调用循环", "files.styles": "工作台界面", "files.readme": "项目指南",
    "protected.subtitle": "每个任务单独授权写入", "panel.title": "工作台", "cancel": "取消任务", "working": "执行中", "ready": "就绪",
    "phase.queued": "排队中", "phase.planning": "正在规划", "phase.tool": "正在使用工具", "phase.answering": "正在生成回答", "phase.waiting": "等待模型输出", "phase.merging": "正在合并子任务", "phase.completed": "已完成", "phase.failed": "执行失败", "phase.cancelled": "已取消", "phase.interrupted": "服务重启时中断", "stream.live": "实时回答",
    "tasks.center": "任务中心", "tasks.open": "打开任务", "tasks.resume": "重新运行", "tasks.children": "子任务", "tasks.tokens": "tokens", "tasks.context": "上下文", "tasks.compacted": "次压缩", "tasks.allWorkspaces": "所有工作区", "tasks.noHistory": "还没有任务记录", "tasks.jumpLatest": "跳到最新", "tasks.following": "跟随最新输出", "tasks.paused": "已暂停自动滚动", "tasks.runtime": "运行时指标", "tasks.repairs": "修复次数", "tasks.verifications": "验证次数", "tasks.traces": "Trace 事件", "tasks.workflow": "工作流",
    "tool.ok": "完成", "tool.error": "失败", "tool.denied": "已阻止", "tool.searchResults": "搜索来源", "tool.openSource": "打开来源", "tool.round": "工具轮次", "tool.callCount": "次调用", "tool.reasoning": "阶段摘要", "tool.result": "执行结果", "tool.observation": "观察结果", "tool.structured": "结构化证据", "tool.metadata": "执行元数据", "tool.expand": "展开详情", "tool.empty": "工具没有返回额外文本", "trace.feedback": "自反馈",
    "workspace.current": "当前工作区", "workspace.path": "文件夹路径", "workspace.open": "打开文件夹", "workspace.recent": "最近打开", "workspace.switching": "正在切换工作区...", "workspace.selectHint": "输入本机文件夹绝对路径，例如 D:\\Projects\\demo",
    "panel.workspaces": "工作区与 Git worktree", "panel.activity": "任务活动", "panel.settings": "设置", "panel.options": "更多选项", "panel.batch": "并行子智能体",
    "panel.file": "文件预览", "panel.noTasks": "还没有后台任务", "panel.refresh": "刷新", "panel.close": "关闭", "tasks.detail": "查看详情", "tasks.openSession": "打开会话",
    "batch.title": "拆分并行任务", "batch.subtitle": "适合独立检查、资料搜集和验证；子任务完成后会自动合并结果。", "batch.task": "子任务", "batch.context": "共享上下文（可选）", "batch.run": "开始并行", "batch.note": "建议每个子任务只负责一个清晰目标。",
    "panel.createWorktree": "创建 worktree", "panel.name": "名称", "panel.branch": "分支（可选）", "panel.create": "创建",
    "panel.sandbox": "执行环境", "panel.mcp": "MCP 工具", "panel.language": "界面语言", "panel.clear": "清空当前会话",
    "panel.export": "导出当前对话", "panel.reload": "刷新工作区状态", "panel.noWorktrees": "当前没有额外 worktree",
    "panel.hostProcess": "宿主机进程", "panel.isolated": "已隔离", "panel.servers": "个服务", "panel.gitWorktrees": "Git worktree", "panel.reasoning": "推理强度", "panel.reasoningNote": "按模型支持传递 low、mid、high、xhigh 或 max；界面显示可审计阶段摘要，不展示模型私有思维链", "reasoning.low": "低", "reasoning.mid": "中", "reasoning.high": "高", "reasoning.xhigh": "极高", "reasoning.max": "最高",
    "game.close": "关闭小游戏", "game.kicker": "MINICC ARCADE · MINI LAWN", "game.title": "植物大战僵尸 · 草坪保卫战",
    "game.subtitle": "10 波高压战役，失败只由僵尸进屋触发；战斗用时仅统计活跃帧，切后台和手动暂停均不消耗进度。", "game.sun": "阳光", "game.score": "击退", "game.wave": "波次",
    "game.ready": "准备就绪", "game.running": "战斗中", "game.paused": "已自动暂停，返回页面后继续", "game.manualPaused": "战局已手动暂停", "game.waveClear": "本波已清场，下一波即将到来", "game.waveIncoming": "强化波次来袭，准备迎战", "game.victory": "草坪守住了！", "game.noSun": "阳光不足", "game.recharging": "卡片冷却中", "game.gameOver": "僵尸进屋了", "game.time": "战斗用时", "game.threat": "威胁", "game.waveHint": "建立防线，下一批僵尸即将抵达", "game.wavePressure": "高压波次：优先布置减速与防线", "game.progress": "战役进度", "game.difficulty": "难度", "game.normal": "标准", "game.hard": "高压", "game.nightmare": "噩梦", "game.pause": "暂停", "game.resume": "继续", "game.pauseHint": "冻结战局", "game.resumeHint": "恢复战局", "game.volume": "音量", "game.shovel": "铲子", "game.shovelHint": "点击植物移除", "game.autoSun": "自动拾取阳光", "game.autoSunHint": "关闭后改为手动点击", "game.repeater": "双发射手", "game.cherrybomb": "爆裂果", "game.icepeashooter": "寒冰射手", "game.burst": "爆发", "game.slow": "减速", "game.peashooter": "豌豆射手", "game.soundOn": "♫ 音效开", "game.soundOff": "♫ 音效关",
    "game.sunflower": "向日葵", "game.wallnut": "坚果墙", "game.attack": "攻击", "game.produce": "产阳光", "game.defense": "防御",
    "game.instructions": "点击草坪种植 · 点击阳光收集", "game.start": "开始游戏", "game.restart": "重开",
    "message.you": "你", "message.now": "现在", "message.agent": "Agent", "game.canvas": "植物大战僵尸迷你游戏画布",
    "changes.agentCore": "Agent 核心", "changes.webWorkspace": "Web 工作台", "changes.specproof": "Specproof 评估", "changes.filesChanged": "修改 6 个文件", "changes.filesAdded": "新增 3 个文件", "changes.assessmentAdded": "已添加评估", "changes.now": "现在", "changes.minute": "1 分钟前", "changes.clean": "等待变更", "changes.cleanHint": "运行任务后会在这里同步", "changes.modified": "已修改", "changes.added": "已新增", "changes.deleted": "已删除", "changes.renamed": "已重命名", "changes.openDiff": "查看 diff",
  },
  en: {
    "brand.caption": "LOCAL AGENT STUDIO", "newTask.label": "New task", "newTask.title": "Create a new task",
    "search.placeholder": "Search tasks", "nav.main": "Main navigation", "nav.tasks": "Tasks", "nav.workspaces": "Workspaces", "nav.promo": "Promo", "nav.activity": "Activity", "nav.arcade": "Arcade",
    language: "Language", "tasks.more": "More tasks", "workspace.connected": "Local service connected", "profile.label": "Current mode",
    "inspector.toggle": "Toggle inspector", "inspector.close": "Close inspector", "focus.enter": "Focus reading", "focus.exit": "Exit focus reading", "options.open": "More options", "composer.inputLabel": "Task input",
    "composer.allowChanges": "Allow this task to modify files or run commands", "composer.allowNetwork": "Allow this task to search the web", "cancel.title": "Cancel task", "send.title": "Send task", "files.refresh": "Refresh files",
    "sidebar.close": "Close sidebar", "sidebar.open": "Open sidebar", "search.shortcut": "Search shortcut",
    recentTasks: "Recent tasks", "profile.mode": "Interview mode", "profile.local": "Local only", workspace: "Workspace", agentSession: "Agent session", live: "Live",
    "connection.connecting": "Connecting", "connection.connected": "Connected", "connection.offline": "Offline", "mode.localSafe": "local / safe", "mode.localFull": "local / full access",
    "composer.workingIn": "Working in", "context.empty": "0 / 300k context", "context.used": "tokens used", "date.today": "Today",
    "composer.placeholder": "Ask minicc to inspect, build, or verify...", "composer.attach": "Image", "quick.plan": "Plan", "quick.review": "Review", "quick.verify": "Verify", "quick.parallel": "Parallel", "quick.demo": "Demo flow",
    "mode.safe": "Read-only", "mode.changes": "Full access", "composer.fullAccess": "Full access: the agent can write files and run commands.", "composer.readOnly": "Read-only: writes and commands are skipped.",
    "inspector.overview": "Overview", "inspector.changes": "Changes", "inspector.files": "Files in focus", "protected.title": "Protected workspace",
    "inspector.pulse": "Project pulse", "inspector.live": "Live", "inspector.ready": "Ready", "inspector.standingBy": "Agent is standing by",
    "inspector.turns": "Turns", "inspector.tools": "Tools", "inspector.tokens": "Tokens", "inspector.context": "Context", "inspector.compactions": "Compactions", "changes.latest": "Latest changes",
    "files.main": "CLI entrypoint", "files.loop": "Tool calling loop", "files.styles": "Workspace surface", "files.readme": "Project guide",
    "protected.subtitle": "Writes are gated per task", "panel.title": "Workspace", "cancel": "Cancel task", "working": "Working", "ready": "Ready",
    "phase.queued": "Queued", "phase.planning": "Planning", "phase.tool": "Running tools", "phase.answering": "Writing response", "phase.waiting": "Waiting for output", "phase.merging": "Merging subagents", "phase.completed": "Complete", "phase.failed": "Failed", "phase.cancelled": "Cancelled", "phase.interrupted": "Interrupted by restart", "stream.live": "Live response",
    "tasks.center": "Task center", "tasks.open": "Open task", "tasks.resume": "Run again", "tasks.children": "subtasks", "tasks.tokens": "tokens", "tasks.context": "context", "tasks.compacted": "compactions", "tasks.allWorkspaces": "All workspaces", "tasks.noHistory": "No task history yet", "tasks.jumpLatest": "Jump to latest", "tasks.following": "Following latest output", "tasks.paused": "Auto-scroll paused", "tasks.runtime": "Runtime metrics", "tasks.repairs": "Repairs", "tasks.verifications": "Verifications", "tasks.traces": "Trace events", "tasks.workflow": "Workflow",
    "tool.ok": "Done", "tool.error": "Failed", "tool.denied": "Blocked", "tool.searchResults": "Search sources", "tool.openSource": "Open source", "tool.round": "Tool round", "tool.callCount": "calls", "tool.reasoning": "Stage summary", "tool.result": "Execution result", "tool.observation": "Observation", "tool.structured": "Structured evidence", "tool.metadata": "Execution metadata", "tool.expand": "Expand details", "tool.empty": "The tool returned no additional text", "trace.feedback": "Self-feedback",
    "workspace.current": "Current workspace", "workspace.path": "Folder path", "workspace.open": "Open folder", "workspace.recent": "Recent folders", "workspace.switching": "Switching workspace...", "workspace.selectHint": "Enter an absolute local path, for example D:\\Projects\\demo",
    "panel.workspaces": "Workspaces & Git worktrees", "panel.activity": "Task activity", "panel.settings": "Settings", "panel.options": "More options", "panel.batch": "Parallel subagents",
    "panel.file": "File preview", "panel.noTasks": "No background tasks yet", "panel.refresh": "Refresh", "panel.close": "Close", "tasks.detail": "Details", "tasks.openSession": "Open session",
    "batch.title": "Split parallel tasks", "batch.subtitle": "Use for independent inspection, research, or verification; results are merged when children finish.", "batch.task": "Subtask", "batch.context": "Shared context (optional)", "batch.run": "Start parallel run", "batch.note": "Give each subtask one clear responsibility.",
    "panel.createWorktree": "Create worktree", "panel.name": "Name", "panel.branch": "Branch (optional)", "panel.create": "Create",
    "panel.sandbox": "Execution", "panel.mcp": "MCP tools", "panel.language": "Interface language", "panel.clear": "Clear current session",
    "panel.export": "Export current chat", "panel.reload": "Refresh workspace status", "panel.noWorktrees": "No extra worktrees",
    "panel.hostProcess": "host process", "panel.isolated": "isolated", "panel.servers": "servers", "panel.gitWorktrees": "Git worktrees", "panel.reasoning": "Reasoning effort", "panel.reasoningNote": "Sends the supported low, mid, high, xhigh, or max level; the UI shows auditable stage summaries, never private chain-of-thought", "reasoning.low": "Low", "reasoning.mid": "Mid", "reasoning.high": "High", "reasoning.xhigh": "XHigh", "reasoning.max": "Max",
    "game.close": "Close game", "game.kicker": "MINICC ARCADE · MINI LAWN", "game.title": "Plants vs. Zombies · Mini lawn",
    "game.subtitle": "10 high-pressure waves. Only a zombie reaching the house ends the campaign; battle time counts active frames only.", "game.sun": "Sun", "game.score": "Defeated", "game.wave": "Wave",
    "game.ready": "Ready", "game.running": "Battle", "game.paused": "Paused while this tab is hidden", "game.manualPaused": "Battle paused", "game.waveIncoming": "Reinforced wave incoming", "game.gameOver": "A zombie reached the house", "game.time": "Battle time", "game.threat": "Threat", "game.waveHint": "Build your line; the next pack is approaching", "game.wavePressure": "High-pressure wave: use slows and defenses", "game.progress": "Campaign progress", "game.difficulty": "Difficulty", "game.normal": "Standard", "game.hard": "High pressure", "game.nightmare": "Nightmare", "game.pause": "Pause", "game.resume": "Resume", "game.pauseHint": "Freeze battle", "game.resumeHint": "Resume battle", "game.volume": "Volume", "game.shovel": "Shovel", "game.shovelHint": "Remove a plant", "game.autoSun": "Auto-collect sun", "game.autoSunHint": "Turn off for manual clicks", "game.repeater": "Repeater", "game.cherrybomb": "Burst berry", "game.icepeashooter": "Ice shooter", "game.burst": "burst", "game.slow": "slow", "game.peashooter": "Peashooter", "game.soundOn": "♫ Sound on", "game.soundOff": "♫ Sound off",
    "game.sunflower": "Sunflower", "game.wallnut": "Wall-nut", "game.attack": "attack", "game.produce": "sun", "game.defense": "defense",
    "game.instructions": "Click the lawn to plant · click sun to collect", "game.start": "Start game", "game.restart": "Restart",
    "message.you": "You", "message.now": "now", "message.agent": "Agent", "game.canvas": "Plants vs. Zombies mini game canvas",
    "changes.agentCore": "Agent core", "changes.webWorkspace": "Web workspace", "changes.specproof": "Specproof review", "changes.filesChanged": "6 files changed", "changes.filesAdded": "3 files added", "changes.assessmentAdded": "assessment added", "changes.now": "now", "changes.minute": "1m", "changes.clean": "Waiting for changes", "changes.cleanHint": "Changes will sync here after a task runs", "changes.modified": "Modified", "changes.added": "Added", "changes.deleted": "Deleted", "changes.renamed": "Renamed", "changes.openDiff": "Open diff",
  },
};

function t(key) {
  return I18N[state.locale]?.[key] || I18N.en[key] || key;
}

function applyLocale() {
  document.documentElement.lang = state.locale === "zh" ? "zh-CN" : "en";
  $$(`[data-i18n]`).forEach((element) => { element.textContent = t(element.dataset.i18n); });
  $$(`[data-i18n-placeholder]`).forEach((element) => { element.placeholder = t(element.dataset.i18nPlaceholder); });
  $$(`[data-i18n-title]`).forEach((element) => { element.title = t(element.dataset.i18nTitle); });
  $$(`[data-i18n-aria]`).forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAria)); });
  $("#localeZh")?.classList.toggle("active", state.locale === "zh");
  $("#localeEn")?.classList.toggle("active", state.locale === "en");
  updateReasoningControl();
  if ($("#messageList") && !isSessionBusy(state.sessionId)) renderSession(state.sessionId);
  updateMode();
  if (state.connection !== null) setConnection(state.connection);
  applyTheme();
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
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

function setTheme(theme) {
  state.theme = theme === "light" ? "light" : "dark";
  localStorage.setItem("minicc-theme", state.theme);
  applyTheme();
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

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const liveStreamStates = new Map();
const taskEventSources = new Map();
const runningTasks = new Map();
const taskBySession = new Map();
const taskTimerHandles = new Map();
const finalizedTaskIds = new Set();
const renderedHistoryKeys = new Map();
let changeRefreshTimer = 0;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatText(value) {
  const codeBlocks = [];
  let formatted = escapeHtml(value).replace(/```([\s\S]*?)```/g, (_match, code) => {
    const token = `__MINICC_CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push(`<pre><code>${code}</code></pre>`);
    return token;
  });
  formatted = formatted
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/^-\s+/gm, "&bull; ")
    .replace(/\n/g, "<br />");
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
    const preview = dataUrl
      ? `<img src="${escapeHtml(dataUrl)}" alt="${escapeHtml(name)}" />`
      : `<span class="attachment-placeholder">${icon("image")}</span>`;
    const remove = item.id ? `<button type="button" class="attachment-remove" data-remove-attachment="${escapeHtml(item.id)}" aria-label="Remove ${escapeHtml(name)}" title="Remove">${icon("x")}</button>` : "";
    return `<div class="image-attachment">${preview}<span class="image-attachment-copy"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(formatBytes(item.size_bytes))}</small></span>${remove}</div>`;
  }).join("")}</div>`;
}

function icon(name) {
  return `<i data-lucide="${name}"></i>`;
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function sessionViewKey(sessionId, workspacePath = state.workspacePath) {
  const workspace = encodeURIComponent(workspacePath || "default");
  return `${SESSION_VIEW_PREFIX}${workspace}:${encodeURIComponent(sessionId)}`;
}

function persistSessionView(sessionId = state.sessionId, workspacePath = state.workspacePath) {
  const messageList = $("#messageList");
  if (!messageList) return;
  const markup = messageList.innerHTML;
  const cacheKey = sessionViewKey(sessionId, workspacePath);
  sessionMarkup.set(cacheKey, markup);
  try {
    localStorage.setItem(cacheKey, markup);
  } catch {
    // Storage quota or privacy mode should not interrupt an agent run.
  }
}

function cachedSessionView(sessionId, workspacePath = state.workspacePath) {
  const cacheKey = sessionViewKey(sessionId, workspacePath);
  if (sessionMarkup.has(cacheKey)) return sessionMarkup.get(cacheKey);
  try {
    const markup = localStorage.getItem(cacheKey);
    if (markup) {
      sessionMarkup.set(cacheKey, markup);
      return markup;
    }
  } catch {
    // Fall back to the in-memory view when storage is unavailable.
  }
  return null;
}

function presetMessageMarkup(sessionId) {
  const preset = SESSION_PRESETS[sessionId];
  if (!preset) {
    return `<article class="message assistant-message"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div><div class="message-body"><p>Ready when you are. I will inspect the workspace before making a plan.</p></div></article>`;
  }
  const events = eventTimelineMarkup(preset.events || []);
  return `<article class="message user-message"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>You</strong><time>now</time></div><div class="message-body"><p>${formatText(preset.user)}</p></div></article><article class="message assistant-message"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div><div class="message-body">${events ? `<div class="tool-timeline">${events}</div>` : ""}<p>${formatText(preset.answer)}</p></div></article>`;
}

function executionTrailMarkup(eventMarkup, events) {
  if (!eventMarkup) return "";
  return `<section class="execution-trail"><div class="execution-trail-head"><span>${escapeHtml(state.locale === "zh" ? "执行脉络与证据" : "Execution trail and evidence")}</span><span>${escapeHtml(eventTimelineSummary(events))}</span></div><div class="tool-timeline">${eventMarkup}</div></section>`;
}

function taskHistoryMarkup(task) {
  const prompt = task.prompt || task.preview || "";
  const answer = task.answer || task.error || "任务没有返回可交付文字。";
  const rawStream = !task.answer && task.stream_text ? rawOutputMarkup(task.stream_text) : "";
  const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
  const taskAnchor = escapeHtml(`task-${task.task_id || task.created_at || prompt.slice(0, 40)}`);
  const attachments = attachmentMarkup(task.attachments || []);
  const batchSummary = task.task_kind === "batch" && Array.isArray(task.children)
    ? `<div class="batch-child-summary"><div class="batch-child-heading"><strong>${escapeHtml(state.locale === "zh" ? "分层并行结果" : "Layered parallel results")}</strong><small>${escapeHtml(state.locale === "zh" ? "只读子任务并行 → 主 Agent 合并与复核" : "Readonly children in parallel -> parent merge and review")}</small></div>${task.children.map((child, index) => {
        const metrics = child.metrics && typeof child.metrics === "object" ? child.metrics : {};
        const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
        const answer = String(child.answer || child.error || child.stream_text || "").replace(/\s+/g, " ").trim();
        const evidence = (Array.isArray(child.events) ? child.events : []).filter((event) => event?.summary).slice(-2).map((event) => event.summary).join("；");
        return `<details class="batch-child"><summary><span class="task-state ${child.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(child.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(`${t("batch.task")} ${index + 1}`)}</strong><small>${escapeHtml(`${phaseLabel(child)} · ${budget.turns || 0} turns · ${budget.tool_calls || 0} tools`)}</small><span class="batch-child-chevron">${icon("chevron-down")}</span></summary><div class="batch-child-detail">${answer ? `<p>${escapeHtml(answer.slice(0, 900))}</p>` : ""}${evidence ? `<small>${escapeHtml(evidence.slice(0, 700))}</small>` : ""}</div></details>`;
      }).join("")}</div>`
    : "";
  const execution = executionTrailMarkup(events, task.events || []);
  return `<article class="message user-message" data-chat-anchor="${taskAnchor}-prompt"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(task.created_at || t("message.now"))}</time></div><div class="message-body"><p>${formatText(prompt)}</p>${attachments}</div></article><article class="message assistant-message" data-chat-anchor="${taskAnchor}-answer"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>${escapeHtml(task.finished_at || task.created_at || t("message.now"))}</time></div><div class="message-body"><div class="history-result-head"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div>${execution}<p class="answer-callout">${formatText(answer)}</p>${batchSummary}${rawStream}</div></article>`;
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
    Array.isArray(task?.events) ? task.events.length : 0,
  ].join(":");
}

function renderSession(sessionId, options = {}) {
  const area = $("#chatArea");
  const chatPosition = captureChatPosition(area);
  if (chatPosition && options.followLatest === true) chatPosition.followLatest = true;
  const preset = SESSION_PRESETS[sessionId];
  const history = taskHistoryBySession.get(sessionId);
  const historyItems = taskHistoryListBySession.get(sessionId);
  const defaultTitle = state.locale === "zh" ? "新任务" : "New task";
  const defaultSubtitle = state.locale === "zh" ? "为下一次修改准备一个干净上下文。" : "A clean context for the next change.";
  $("#sessionTitle").textContent = history ? String(history.preview || history.prompt || defaultTitle).slice(0, 72) : (state.locale === "zh" ? (preset?.titleZh || preset?.title || defaultTitle) : (preset?.title || defaultTitle));
  $("#sessionSubtitle").textContent = history ? phaseLabel(history) : (state.locale === "zh" ? (preset?.subtitleZh || preset?.subtitle || defaultSubtitle) : (preset?.subtitle || defaultSubtitle));
  const markup = history
    ? taskHistoryListMarkup(historyItems?.length ? historyItems : [history])
    : (cachedSessionView(sessionId) || (sessionId === "interview-1" ? initialMessageMarkup : presetMessageMarkup(sessionId)));
  if (markup) $("#messageList").innerHTML = markup;
  updateSessionStatus(history);
  if (history) renderedHistoryKeys.set(sessionId, taskHistoryKey(historyItems?.length ? historyItems : history));
  else renderedHistoryKeys.delete(sessionId);
  refreshIcons();
  // Preserve the visible message across background history refreshes.
  restoreChatPosition(chatPosition);
  window.requestAnimationFrame(() => restoreSessionTask(sessionId));
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
  taskHistoryBySession.clear();
  taskHistoryListBySession.clear();
  for (const task of Array.isArray(tasks) ? tasks : []) {
    const sessionId = String(task.session_id || task.task_id || "web-latest");
    if (!taskHistoryBySession.has(sessionId)) taskHistoryBySession.set(sessionId, task);
    if (!taskHistoryListBySession.has(sessionId)) taskHistoryListBySession.set(sessionId, []);
    taskHistoryListBySession.get(sessionId).push(task);
  }
  if (!Array.isArray(tasks) || !tasks.length) {
    $("#taskNavCount").textContent = "0";
    list.innerHTML = `<div class="thread-empty">${escapeHtml(t("tasks.noHistory"))}</div>`;
    list.dataset.historyLoaded = "true";
    return;
  }
  const visible = tasks.slice(0, 30);
  list.innerHTML = visible.map((task) => {
    const sessionId = String(task.session_id || task.task_id || "web-latest");
    const title = String(task.preview || task.prompt || task.task_id || "Task").replace(/\s+/g, " ").trim();
    const status = phaseLabel(task);
    const detail = `${status} · ${task.task_id || ""}`;
    return `<button class="thread-item ${sessionId === state.sessionId ? "active" : ""}" data-session="${escapeHtml(sessionId)}" data-task-id="${escapeHtml(task.task_id || "")}">
      <span class="thread-dot ${taskDotClass(task.status)}"></span>
      <span class="thread-copy"><strong>${escapeHtml(title.slice(0, 72))}</strong><small>${escapeHtml(detail)}</small></span>
      ${icon("chevron-right")}
    </button>`;
  }).join("");
  list.dataset.historyLoaded = "true";
  $("#taskNavCount").textContent = String(tasks.length);
  // A user-created session is intentionally allowed to have no history yet.
  // Do not replace it with the newest durable task during the 5s refresh loop.
  const currentHistory = taskHistoryBySession.get(state.sessionId);
  if (
    currentHistory
    && !isSessionBusy(state.sessionId)
    && renderedHistoryKeys.get(state.sessionId) !== taskHistoryKey(taskHistoryListBySession.get(state.sessionId) || currentHistory)
  ) {
    renderSession(state.sessionId);
  }
  refreshIcons();
  window.requestAnimationFrame(() => {
    list.scrollTop = wasAtTop ? 0 : Math.min(previousScrollTop, Math.max(0, list.scrollHeight - list.clientHeight));
  });
}

async function loadTaskHistory() {
  try {
    const query = state.workspacePath ? "&workspace=" + encodeURIComponent(state.workspacePath) : "";
    const data = await requestJson("/api/tasks?limit=100" + query);
    if (state.connection === false) setConnection(true);
    renderTaskHistory(data.tasks || []);
  } catch {
    // Static demo sessions remain available when the task index is offline.
  }
}

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
  localStorage.setItem("minicc-session", sessionId);
  $("#topSession").textContent = sessionId;
  $$(".thread-item").forEach((item) => item.classList.toggle("active", item.dataset.session === sessionId));
  renderSession(sessionId, { followLatest: sessionChanged });
  sessionViewReady = true;
}

function taskSessionKey(sessionId, workspacePath = state.workspacePath) {
  return `${workspacePath || "default"}::${sessionId}`;
}

function sessionTaskBindings(sessionId, workspacePath = state.workspacePath) {
  return [...runningTasks.values()].filter((binding) => (
    binding.sessionId === sessionId
    && taskSessionKey(binding.sessionId, binding.workspacePath) === taskSessionKey(sessionId, workspacePath)
    && !isTerminalTask(binding.data)
  ));
}

function isSessionBusy(sessionId) {
  return sessionTaskBindings(sessionId).length > 0 || taskBySession.has(taskSessionKey(sessionId));
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
  if (!binding || binding.sessionId === state.sessionId) {
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

function bindRunningTask(task, loadingId, sessionId = state.sessionId) {
  finalizedTaskIds.delete(task.task_id);
  const binding = { taskId: task.task_id, sessionId, workspacePath: task.workspace_path || state.workspacePath, loadingId, data: task };
  runningTasks.set(task.task_id, binding);
  taskBySession.set(taskSessionKey(sessionId, binding.workspacePath), task.task_id);
  state.activeTaskId = sessionId === state.sessionId ? task.task_id : state.activeTaskId;
  startTaskTimer(task.task_id);
  return binding;
}

function restoreSessionTask(sessionId) {
  const bindings = sessionTaskBindings(sessionId);
  if (!bindings.length) {
    setBusy(false);
    return;
  }
  for (const binding of bindings) {
    if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, binding.data, { scrollToLatest: false });
    updateLiveTask(binding.loadingId, binding.data);
  }
  state.activeTaskId = bindings[bindings.length - 1].taskId;
  setBusy(true);
}

function updateMode() {
  const checkbox = $("#allowChanges");
  checkbox.checked = state.allowChanges;
  const networkCheckbox = $("#allowNetwork");
  if (networkCheckbox) networkCheckbox.checked = state.allowNetwork;
  $("#modeLabel").textContent = state.allowChanges ? t("mode.changes") : t("mode.safe");
  $("#permissionHint").textContent = state.allowChanges ? t("composer.fullAccess") : t("composer.readOnly");
  $("#modeBadge").textContent = state.allowChanges ? t("mode.localFull") : t("mode.localSafe");
}

function addUserMessage(text, attachments = []) {
  $("#messageList").insertAdjacentHTML("beforeend", `
    <article class="message user-message">
      <div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(t("message.now"))}</time></div>
      <div class="message-body"><p>${formatText(text)}</p>${attachmentMarkup(attachments)}</div>
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
  const phase = TERMINAL_TASK_STATUSES.has(status)
    ? status
    : data.phase || (status === "queued" ? "queued" : status);
  const key = {
    queued: "phase.queued",
    planning: "phase.planning",
    tool: "phase.tool",
    answering: "phase.answering",
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
  const value = TERMINAL_TASK_STATUSES.has(status)
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

function taskMetrics(data) {
  const tokens = Number(data.tokens_used?.total_tokens || 0);
  const context = Number(data.context?.tokens || 0);
  const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 300000);
  const estimated = data.tokens_used?.estimated || data.usage_by_turn?.some((item) => item.estimated);
  const tokenText = `${estimated ? "~" : ""}${compactNumber(tokens)} ${t("tasks.tokens")}`;
  return `${tokenText} · ${compactNumber(context)}/${compactNumber(limit)} ${t("tasks.context")}`;
}

function runtimeMetricsMarkup(data) {
  const metrics = data?.metrics;
  if (!metrics || typeof metrics !== "object" || (!metrics.workflow && !metrics.verification_runs && !metrics.trace_events)) return "";
  const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
  const duration = formatDuration(metrics.duration_seconds || 0);
  return `<div><div class="panel-section-title">${escapeHtml(t("tasks.runtime"))}</div><div class="status-grid"><div><span>${escapeHtml(t("tasks.workflow"))}</span><strong>${escapeHtml(String(metrics.workflow || "coding"))}</strong><small>${escapeHtml(String(metrics.phase || data.phase || ""))}</small></div><div><span>${escapeHtml(t("tasks.repairs"))}</span><strong>${escapeHtml(String(metrics.repair_attempts || 0))}</strong><small>${escapeHtml(duration)}</small></div><div><span>${escapeHtml(t("tasks.verifications"))}</span><strong>${escapeHtml(String(metrics.verification_runs || 0))}</strong><small>${escapeHtml(String(metrics.verification_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.traces"))}</span><strong>${escapeHtml(String(metrics.trace_events || 0))}</strong><small>${escapeHtml(`${budget.turns || 0} turns · ${budget.tool_calls || 0} tools`)}</small></div></div></div>`;
}

function updateInspectorMetrics(data) {
  if (!data) return;
  const tokens = Number(data.tokens_used?.total_tokens || 0);
  const context = Number(data.context?.tokens || 0);
  const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 300000);
  $("#tokenMetric").textContent = compactNumber(tokens);
  $("#contextMetric").textContent = `${compactNumber(context)}/${compactNumber(limit)}`;
  $("#compactionMetric").textContent = String(data.compaction_events?.length || 0);
  $("#contextCount").textContent = taskMetrics(data);
}

function updateTaskDock(data) {
  if (!data) return;
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
  badge.dataset.status = terminal ? status : "running";
  badge.classList.toggle("terminal", terminal);
  label.textContent = terminal ? phaseLabel(data) : t("live");
}

function liveTaskMarkup(data) {
  const streamText = String(data.stream_text || "");
  const currentPhase = phaseClass(data);
  const preview = streamText ? formatText(streamTail(streamText)) : `<span class="stream-empty">${escapeHtml(t("phase.waiting"))}</span>`;
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
      <div class="stream-panel-head"><span class="stream-live-dot" aria-hidden="true"></span><span>${escapeHtml(t("stream.live"))}</span><span class="stream-metrics" data-live-metrics>${escapeHtml(taskMetrics(data))}</span><span class="stream-phase" data-live-phase-label>${escapeHtml(phaseLabel(data))}</span></div>
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
        reasoning_configured: "推理预算",
        image_attached: "视觉输入",
        model_decision: "模型决策",
        model_update: "模型行动说明",
        tool_round_started: "执行计划",
        tool_round_finished: "结果汇总",
        feedback_observed: "自反馈",
        replan: "重新规划",
        stagnation_replan: "停滞纠偏",
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
         run_finished: "交付整理",
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
        reasoning_configured: "Reasoning budget",
        image_attached: "Vision input",
        model_decision: "Model decision",
        model_update: "Model update",
        tool_round_started: "Execution plan",
        tool_round_finished: "Results merged",
        feedback_observed: "Self-feedback",
        replan: "Re-plan",
        stagnation_replan: "Stagnation recovery",
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
         run_finished: "Delivery summary",
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
    ? { turn: "轮次", previous_turn: "上一轮", tool_count: "工具", results: "结果", observed: "已观察", observations: "观察", constraints: "约束", failed_tools: "失败", verification_required: "需验证", assessment: "反馈", trigger: "触发", next_action: "下一步" }
    : { turn: "turn", previous_turn: "previous", tool_count: "tools", results: "results", observed: "observed", observations: "observations", constraints: "constraints", failed_tools: "failed", verification_required: "verify", assessment: "assessment", trigger: "trigger", next_action: "next" };
  const parts = [];
  for (const key of ["turn", "previous_turn", "tool_count", "results", "observed", "observations", "constraints", "failed_tools", "verification_required", "assessment", "trigger", "next_action"]) {
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
  return text ? `<details class="raw-output"><summary>${escapeHtml(state.locale === "zh" ? "原始模型输出" : "Raw model output")}</summary><div>${formatText(text)}</div></details>` : "";
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

function visibleAgentEvents(events) {
  const visible = [];
  let previousKey = "";
  for (const event of Array.isArray(events) ? events : []) {
    const key = [event?.kind, event?.code, event?.name, event?.status, shortEventText(event, 90), event?.path || ""].join("|");
    if (key !== previousKey) visible.push(event);
    previousKey = key;
  }
  return visible;
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
  return { failed, detail, title: state.locale === "zh" ? `第 ${roundNumber} 轮 · ${tools.length} 次操作` : `Round ${roundNumber} · ${tools.length} actions`, status: failed ? (state.locale === "zh" ? "需处理" : "Needs attention") : (state.locale === "zh" ? "已完成" : "Complete") };
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
    const tracePhase = event.code === "run_finished" ? "completed" : event.phase;
    const isModelEvent = ["model_update", "replan"].includes(String(event.code || "")) || String(event.code || "").startsWith("completion_");
    const summary = String(event.summary || traceLabel(event));
    const publicMarkup = publicText ? `<div class="trace-public-plan"><span>${escapeHtml(state.locale === "zh" ? "公开行动" : "Public action")}</span><div>${formatText(publicText)}</div></div>` : "";
    const evidence = structuredDetailMarkup(event.detail, state.locale === "zh" ? "查看完整依据" : "View full evidence");
    const detailMarkup = traceEvidenceMarkup(event, detail, evidence);
    return `<div class="trace-event stage-summary ${isModelEvent ? "model-event " : ""}${traceClass}${animate ? " event-enter" : ""}" data-stage-code="${escapeHtml(event.code || "")}"><span class="trace-icon">${icon(status === "error" ? "alert-triangle" : "sparkles")}</span><div class="trace-main"><div class="trace-summary"><span class="trace-code">${escapeHtml(traceLabel(event))}</span><span>${escapeHtml(summary)}</span></div>${publicMarkup}${detailMarkup}</div><span class="trace-phase">${escapeHtml(phaseLabel({ phase: tracePhase }))}</span></div>`;
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
  return `<details class="tool-event ${stateClass}${animate ? " event-enter" : ""}" data-tool-event="${escapeHtml(toolAnchor)}"${open ? " open" : ""}>
    <summary class="tool-event-summary"><span class="tool-icon ${denied ? "amber-icon" : ""}">${icon(iconName)}</span><span class="tool-event-copy"><span><strong>${escapeHtml(name)}</strong>${pathMarkup}</span><small>${escapeHtml(event.summary || "")}</small></span><span class="tool-check ${denied ? "denied-check" : failed ? "failed-check" : ""}">${icon(stateIcon)}</span><span class="tool-expand">${icon("chevron-down")}</span></summary>
    ${toolResultMarkup(event)}
  </details>`;
}

function eventTimelineMarkup(events, options = {}) {
  if (!Array.isArray(events) || !events.length) return "";
  const items = visibleAgentEvents(events).map((event, index) => ({ event, index }));
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
    return `<details class="agent-round" data-agent-round="${roundKey}"${open ? " open" : ""}><summary class="agent-round-summary"><span class="agent-round-title"><span class="agent-round-icon">${icon(round.failed ? "alert-circle" : "layers-3")}</span><strong>${escapeHtml(round.title)}</strong><small>${escapeHtml(round.detail)}</small></span><span class="agent-round-meta">${escapeHtml(round.status)}<span class="agent-round-chevron">${icon("chevron-down")}</span></span></summary><div class="agent-round-events">${itemMarkup}</div></details>`;
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
      <div class="message-body">${execution}<p class="answer-callout">${formatText(answer)}</p>${rawStream}</div>
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

async function requestJson(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，任务仍可在活动面板中查看。");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

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
    stream.preview.innerHTML = `${formatText(streamTail(stream.target))}<span class="stream-caret" aria-hidden="true"></span>`;
  };
  stream.frame = window.setTimeout(paint, 120);
}

function syncLiveEvents(loading, events, chatPosition = null) {
  if (!events.length) return false;
  let timeline = loading.querySelector(".tool-timeline");
  if (!timeline) {
    timeline = document.createElement("div");
    timeline.className = "tool-timeline";
    loading.querySelector(".message-body")?.append(timeline);
  }
  const previousCount = Number(loading.dataset.eventCount || 0);
  const fingerprint = JSON.stringify(events.map((event) => [event.kind, event.code, event.name, event.status, event.summary, event.detail]));
  if (timeline.dataset.eventFingerprint === fingerprint) return false;
  const position = chatPosition || captureChatPosition();
  const openRounds = timeline.dataset.initialized === "true"
    ? new Set([...timeline.querySelectorAll("details.agent-round[open]")].map((item) => item.dataset.agentRound))
    : null;
  const openTools = timeline.dataset.initialized === "true"
    ? new Set([...timeline.querySelectorAll("details.tool-event[open]")].map((item) => item.dataset.toolEvent))
    : null;
  timeline.innerHTML = eventTimelineMarkup(events, { openRounds, openTools, animateFrom: previousCount });
  timeline.dataset.initialized = "true";
  timeline.dataset.eventFingerprint = fingerprint;
  loading.dataset.eventCount = String(events.length);
  refreshIcons();
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
  live.querySelector("[data-live-output-count]")?.replaceChildren(document.createTextNode(streamText ? `${compactNumber(streamText.length)} ${state.locale === "zh" ? "字符（仅显示最近内容）" : "chars (recent content)"}` : ""));
  if (preview) {
    if (streamText) updateLiveStream(loadingId, preview, streamText);
    else preview.innerHTML = `<span class="stream-empty">${escapeHtml(t("phase.waiting"))}</span>`;
  }
  syncLiveEvents(loading, events, chatPosition);
  updateTaskDuration(data, loadingId);
  $("#pulseStatus").textContent = phaseText;
  updateTaskDock(data);
  restoreChatPosition(chatPosition, false);
}

function scheduleChangesRefresh() {
  window.clearTimeout(changeRefreshTimer);
  changeRefreshTimer = window.setTimeout(() => loadChanges(), 220);
}

function updateBoundTask(taskId, data) {
  const binding = runningTasks.get(taskId);
  if (!binding) return;
  binding.data = data;
  if (binding.sessionId === state.sessionId) {
    if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, data, { scrollToLatest: false });
    updateLiveTask(binding.loadingId, data);
  }
  if (Array.isArray(data.events) && data.events.some((event) => ["write_file", "edit_file", "move", "delete"].includes(event.name))) scheduleChangesRefresh();
}

function finishLiveTask(loadingId) {
  const stream = liveStreamStates.get(loadingId);
  if (stream?.frame) window.cancelAnimationFrame(stream.frame);
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
  const finalData = data.status === "completed"
    ? data
    : { ...data, answer: data.answer || data.error || (data.status === "cancelled" ? "任务已取消。" : "任务失败。") };
  runningTasks.delete(taskId);
  if (taskBySession.get(taskSessionKey(binding.sessionId, binding.workspacePath)) === taskId) taskBySession.delete(taskSessionKey(binding.sessionId, binding.workspacePath));

  if (binding.sessionId === state.sessionId && binding.workspacePath === state.workspacePath) {
    addAssistantMessage(finalData, binding.loadingId || loadingId);
    setBusy(false);
  } else {
    const existing = cachedSessionView(binding.sessionId, binding.workspacePath) || presetMessageMarkup(binding.sessionId);
    const holder = document.createElement("div");
    holder.innerHTML = existing;
    const pending = holder.querySelector(`#${CSS.escape(binding.loadingId || loadingId)}`);
    if (pending) {
      const replacement = document.createElement("div");
      replacement.innerHTML = assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`);
      pending.replaceWith(replacement.firstElementChild);
    } else {
      holder.insertAdjacentHTML("beforeend", assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`));
    }
    const cacheKey = sessionViewKey(binding.sessionId, binding.workspacePath);
    sessionMarkup.set(cacheKey, holder.innerHTML);
    try { localStorage.setItem(cacheKey, holder.innerHTML); } catch { /* best effort */ }
  }
  if (finalData.status !== "completed") showToast(finalData.error || (finalData.status === "cancelled" ? "任务已取消" : "任务失败"));
  scheduleChangesRefresh();
  await loadTaskHistory();
  return finalData;
}

async function pollTask(taskId) {
  const binding = runningTasks.get(taskId);
  for (let attempt = 0; attempt < 900; attempt += 1) {
    const data = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000);
    updateBoundTask(taskId, data);
    if (isTerminalTask(data)) return completeTask(binding?.loadingId || "", data);
    await new Promise((resolve) => window.setTimeout(resolve, 220));
  }
  throw new Error("任务运行超过 10 分钟，可在活动面板中取消或查看状态。");
}

function streamTask(taskId) {
  const binding = runningTasks.get(taskId);
  const loadingId = binding?.loadingId || "";
  if (!window.EventSource) return pollTask(taskId);
  return new Promise((resolve, reject) => {
    let source;
    let settled = false;
    let fallbackStarted = false;
    let receivedSnapshot = false;

    const fallback = () => {
      if (settled || fallbackStarted) return;
      fallbackStarted = true;
      source?.close();
      taskEventSources.delete(loadingId);
      pollTask(taskId).then(resolve, reject);
    };

    const finish = (data) => {
      if (settled || !isTerminalTask(data)) return;
      settled = true;
      source?.close();
      taskEventSources.delete(loadingId);
      completeTask(loadingId, data).then(resolve, reject);
    };

    source = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events`);
    taskEventSources.set(loadingId, source);
    source.onmessage = (event) => {
      receivedSnapshot = true;
      try {
        const data = JSON.parse(event.data);
        updateBoundTask(taskId, data);
        finish(data);
      } catch {
        // A malformed event must not strand the task; the fallback remains available.
      }
    };
    source.onerror = fallback;
    window.setTimeout(() => {
      if (!receivedSnapshot) fallback();
    }, 3500);
  });
}

function watchTask(taskId) {
  return streamTask(taskId);
}

async function cancelActiveTask() {
  const taskIds = sessionTaskBindings(state.sessionId).map((binding) => binding.taskId);
  const fallback = taskBySession.get(taskSessionKey(state.sessionId)) || state.activeTaskId;
  if (!taskIds.length && fallback) taskIds.push(fallback);
  if (!taskIds.length) return;
  try {
    await Promise.all(taskIds.map((taskId) => requestJson(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })));
    showToast(state.locale === "zh" ? "已请求取消任务" : "Cancellation requested");
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
    reader.onerror = () => reject(new Error(`无法读取图片：${file.name}`));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
}

async function addImageFiles(fileList) {
  const files = [...(fileList || [])].filter((file) => String(file.type || "").startsWith("image/"));
  if (!files.length) return;
  const remaining = Math.max(0, 4 - state.attachments.length);
  if (!remaining) {
    showToast(state.locale === "zh" ? "最多添加 4 张图片" : "Up to 4 images per task");
    return;
  }
  for (const file of files.slice(0, remaining)) {
    if (file.size > 6 * 1024 * 1024) {
      showToast(state.locale === "zh" ? `${file.name} 超过 6MB` : `${file.name} is larger than 6MB`);
      continue;
    }
    try {
      const dataUrl = await readImageFile(file);
      state.attachments.push({
        id: `image-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        name: file.name,
        mime_type: file.type || "image/png",
        size_bytes: file.size,
        data_url: dataUrl,
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
  const message = input.value.trim() || (queuedAttachments.length ? (state.locale === "zh" ? "请分析我上传的图片。" : "Analyze the images I uploaded.") : "");
  const sessionId = state.sessionId;
  const workspacePath = state.workspacePath;
  if ((!message && !queuedAttachments.length) || state.submitting) return;
  state.submitting = true;
  setBusy(true);
  input.value = "";
  clearAttachments();
  addUserMessage(message, queuedAttachments);
  const loadingId = addLoadingMessage();
  try {
    const task = await requestJson("/api/tasks", {
     method: "POST",
     headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, attachments: queuedAttachments.map(({ name, mime_type, data_url }) => ({ name, mime_type, data_url })), session_id: sessionId, allow_changes: state.allowChanges, allow_network: state.allowNetwork, reasoning_effort: state.reasoningEffort, workspace_path: workspacePath }),
    });
    state.submitting = false;
    bindRunningTask(task, loadingId, sessionId);
    if (state.sessionId === sessionId) state.activeTaskId = task.task_id;
    setBusy(true);
    updateTaskDock(task);
    await loadTaskHistory();
    await watchTask(task.task_id);
  } catch (error) {
    finishLiveTask(loadingId);
    document.getElementById(loadingId)?.remove();
    if (state.sessionId === sessionId) addAssistantMessage({ error: error.message });
    showToast(error.message);
    setConnection(false, "API error");
  } finally {
    state.submitting = false;
    if (!sessionTaskBindings(sessionId, workspacePath).length) state.activeTaskId = null;
    if (state.sessionId === sessionId) setBusy(false);
    input.focus();
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
  showToast(state.locale === "zh" ? "已创建新任务" : "New task created");
}

function runDemoFlow() {
  if (isSessionBusy(state.sessionId)) return;
  const steps = state.locale === "zh"
    ? [
        { phase: "planning", stream: "收到任务：检查一个小功能并给出结果。", event: { kind: "trace", code: "model_update", phase: "planning", summary: "模型给出了本轮可公开的行动说明", detail: { turn: 1, text: "我会先读取 README.md，再定位测试入口并运行针对性验证，最后汇总可确认的结果。" } } },
        { phase: "tool", stream: "read_file · 读取 README.md", event: { name: "read_file", status: "ok", summary: "读取 README.md" } },
        { phase: "tool", stream: "grep · 搜索测试入口", event: { name: "grep", status: "ok", summary: "搜索测试入口" } },
        { phase: "planning", stream: "根据已读取内容调整验证范围", event: { kind: "trace", code: "replan", phase: "planning", summary: "重新规划", detail: { turn: 1, text: "已定位测试入口，下一步只运行与目标功能相关的测试，避免无关耗时。" } } },
        { phase: "tool", stream: "bash · 运行 pytest -q", event: { name: "bash", status: "ok", summary: "运行 pytest -q" } },
        { phase: "answering", stream: "整理验证结果与剩余风险", event: { kind: "trace", code: "tool_round_finished", phase: "answering", summary: "结果汇总：已完成 3 次工具调用，验证通过", detail: { turn: 1, tool_count: 3, tools: ["read_file", "grep", "bash"] } } },
        { phase: "answering", stream: "完成评估：任务目标已满足", event: { kind: "trace", code: "completion_complete", phase: "answering", summary: "完成评估通过", detail: { confidence: "高", evidence: "文档已读取，测试已通过" } } },
      ]
    : [
        { phase: "planning", stream: "Task received: inspect a small feature and report back.", event: { kind: "trace", code: "model_update", phase: "planning", summary: "The model provided a public action update", detail: { turn: 1, text: "I will read README.md, locate the test entry points, run focused validation, then summarize confirmed results." } } },
        { phase: "tool", stream: "read_file · reading README.md", event: { name: "read_file", status: "ok", summary: "Reading README.md" } },
        { phase: "tool", stream: "grep · locating test entry points", event: { name: "grep", status: "ok", summary: "Locating test entry points" } },
        { phase: "planning", stream: "Refining the verification scope", event: { kind: "trace", code: "replan", phase: "planning", summary: "Re-plan", detail: { turn: 1, text: "The relevant tests are located, so I will run focused validation and avoid unrelated work." } } },
        { phase: "tool", stream: "bash · running pytest -q", event: { name: "bash", status: "ok", summary: "Running pytest -q" } },
        { phase: "answering", stream: "Summarizing verification and remaining risks", event: { kind: "trace", code: "tool_round_finished", phase: "answering", summary: "Results merged: 3 tool calls completed and validation passed", detail: { turn: 1, tool_count: 3, tools: ["read_file", "grep", "bash"] } } },
        { phase: "answering", stream: "Completion review: objective is met", event: { kind: "trace", code: "completion_complete", phase: "answering", summary: "Completion accepted", detail: { confidence: "high", evidence: "Documentation read and tests passed" } } },
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
        answer: state.locale === "zh" ? "演示完成：规划 → 工具调用 → 测试验证 → 总结。真实任务会在这里连接本地 API 和模型。" : "Demo complete: plan → tools → tests → summary. Real tasks connect to the local API and model here.",
        events: steps.map((step) => step.event),
        turns: 1, tool_calls_total: 3, tokens_used: { total_tokens: 420 }, context: { tokens: 420, limit_tokens: state.contextWindowTokens },
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
  try {
    const response = await fetch("/api/workspace");
    if (!response.ok) throw new Error("offline");
    const info = await response.json();
    const previousPath = state.workspacePath;
    state.workspaceInfo = info;
   state.workspacePath = info.path || state.workspacePath;
   state.contextWindowTokens = Number(info.context_window_tokens || state.contextWindowTokens || 300000);
    if (!localStorage.getItem("minicc-reasoning") && ["low", "mid", "high", "xhigh", "max"].includes(info.reasoning_effort)) state.reasoningEffort = info.reasoning_effort;
    updateReasoningControl();
    const name = info.name || "workspace";
    $("#workspaceName").textContent = name;
    $("#topWorkspace").textContent = name;
    $("#composerWorkspace").textContent = name;
    $(".inspector-header h2").textContent = name;
    setConnection(true);
    if (previousPath && previousPath !== state.workspacePath) {
      sessionMarkup.clear();
      taskHistoryBySession.clear();
      taskHistoryListBySession.clear();
      renderedHistoryKeys.clear();
      setSession(state.sessionId);
    }
    await loadTaskHistory();
    await loadChanges();
    try {
      const taskData = await requestJson(`/api/tasks?limit=100&workspace=${encodeURIComponent(state.workspacePath)}`);
      const tasks = Array.isArray(taskData.tasks) ? taskData.tasks : [];
      const activeTasks = tasks.filter((item) => ["queued", "running"].includes(item.status));
      for (const task of [...activeTasks].reverse()) {
        if (runningTasks.has(task.task_id)) continue;
        const sessionId = String(task.session_id || task.task_id);
        const loadingId = `loading-${task.task_id}`;
        if (sessionId === state.sessionId) addLoadingMessage(loadingId, task, { scrollToLatest: false });
        bindRunningTask(task, loadingId, sessionId);
        watchTask(task.task_id).catch((error) => showToast(error.message));
      }
      const active = activeTasks.find((item) => item.session_id === state.sessionId) || activeTasks[0];
      if (active) updateTaskDock(active);
      else {
        $("#taskDock").hidden = true;
        state.lastTask = null;
      }
    } catch {
      // The workspace remains usable when the durable task index is unavailable.
    }
  } catch {
    setConnection(false, "Offline");
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
  return `<button class="file-row file-row-${escapeHtml(status)}" data-file="${escapeHtml(path)}" data-open-diff="${escapeHtml(path)}"><span class="file-type ${fileType(path)}">${escapeHtml(fileType(path).toUpperCase())}</span><span><strong>${escapeHtml(path)}</strong><small>${escapeHtml(changeStatusLabel(status))} · <span class="diff-add">+${additions}</span> <span class="diff-del">-${deletions}</span></small></span><i data-lucide="chevron-right"></i></button>`;
}

function renderChanges(data) {
  const files = Array.isArray(data?.files) ? data.files : [];
  const changed = new Map(files.map((item) => [String(item.path), item]));
  const focus = ["minicc/main.py", "minicc/agent/loop.py", "minicc/llm/openai_provider.py", "web/app.js", "web/styles.css", "README.md"];
  const paths = [...new Set([...files.map((item) => String(item.path)), ...focus])].slice(0, 12);
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
    changeList.innerHTML = files.length
      ? files.slice(0, 6).map((item) => `<button class="change-item change-item-button" data-open-diff="${escapeHtml(item.path)}"><span class="change-bar ${item.status === "added" ? "added" : item.status === "deleted" ? "deleted" : "changed"}"></span><span><strong>${escapeHtml(item.path)}</strong><small>${escapeHtml(changeStatusLabel(item.status))} · <span class="diff-add">+${Number(item.additions || 0)}</span> <span class="diff-del">-${Number(item.deletions || 0)}</span></small></span><span class="change-time">${escapeHtml(t("changes.now"))}</span></button>`).join("")
      : `<div class="change-item"><span class="change-bar muted"></span><span><strong>${escapeHtml(t("changes.clean"))}</strong><small>${escapeHtml(t("changes.cleanHint"))}</small></span><span class="change-time">--</span></div>`;
  }
  refreshIcons();
}

async function loadChanges() {
  if (!state.workspacePath) return;
  try {
    const data = await requestJson("/api/changes", {}, 12000);
    state.changes = data;
    renderChanges(data);
  } catch {
    // The chat remains usable when Git is unavailable.
  }
}

function openPanel(title, body, options = {}) {
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
    expand.title = "展开全屏";
    expand.setAttribute("aria-label", "展开全屏");
    expand.innerHTML = icon("maximize-2");
  }
  modal.classList.add("show");
  modal.setAttribute("aria-hidden", "false");
  refreshIcons();
}

function closePanel() {
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
  button.title = fullscreen ? "退出全屏" : "展开全屏";
  button.setAttribute("aria-label", button.title);
  button.innerHTML = icon(fullscreen ? "minimize-2" : "maximize-2");
  refreshIcons();
}

function taskRow(task) {
  const statusClass = task.status === "completed" ? "success" : task.status === "failed" ? "error" : ["cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running";
  const cancel = ["queued", "running"].includes(task.status) ? `<button class="panel-icon-action" data-cancel-task="${escapeHtml(task.task_id)}" title="${t("cancel")}">${icon("square")}</button>` : "";
  const resume = ["failed", "cancelled", "interrupted"].includes(task.status) ? `<button class="panel-icon-action" data-resume-task="${escapeHtml(task.task_id)}" title="${t("tasks.resume")}">${icon("rotate-ccw")}</button>` : "";
  const phase = phaseLabel(task);
  const streamSize = String(task.stream_text || "").length;
  const detail = `${phase} · ${formatDuration(taskDuration(task))} · ${streamSize} chars · ${taskMetrics(task)}`;
  const children = task.child_task_ids?.length ? ` · ${task.child_task_ids.length} ${t("tasks.children")}` : "";
  const workspace = task.workspace_path ? task.workspace_path.split(/[\\/]/).filter(Boolean).pop() : "workspace";
  const details = `<button class="panel-icon-action" data-open-detail="${escapeHtml(task.task_id)}" title="${escapeHtml(t("tasks.detail"))}" aria-label="${escapeHtml(t("tasks.detail"))}">${icon("maximize-2")}</button>`;
  return `<div class="task-row" data-open-task="${escapeHtml(task.task_id)}" tabindex="0"><span class="task-state ${statusClass}"></span><div><strong>${escapeHtml(task.task_kind === "batch" ? `${task.task_id} · ${t("tasks.children")}` : task.task_id)}</strong><small>${escapeHtml(workspace)} · ${escapeHtml(detail)}${children}</small></div><div class="task-row-actions">${details}${resume}${cancel}</div></div>`;
}

async function openTaskInWorkspace(taskId) {
  try {
    const task = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    const targetWorkspace = String(task.workspace_path || "");
    if (targetWorkspace && state.workspacePath && targetWorkspace.replaceAll("\\", "/").toLowerCase() !== state.workspacePath.replaceAll("\\", "/").toLowerCase()) {
      await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: targetWorkspace }) });
      await loadWorkspace();
    }
    const sessionId = String(task.session_id || task.task_id);
    taskHistoryBySession.set(sessionId, task);
    const historyItems = taskHistoryListBySession.get(sessionId) || [];
    if (!historyItems.some((item) => item.task_id === task.task_id)) {
      taskHistoryListBySession.set(sessionId, [task, ...historyItems].sort((left, right) => Number(right.created_at_epoch || 0) - Number(left.created_at_epoch || 0)));
    }
    closePanel();
    setSession(sessionId);
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
    showToast(state.locale === "zh" ? "已打开任务会话" : "Task session opened");
  } catch (error) {
    showToast(error.message);
  }
}

async function openTaskDetail(taskId) {
  try {
    const task = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
    const children = Array.isArray(task.child_task_ids) && task.child_task_ids.length
      ? `<div class="task-detail-children">${task.child_task_ids.map((child) => `<button class="panel-session" data-open-task="${escapeHtml(child)}">${escapeHtml(child)}</button>`).join("")}</div>`
      : "";
    const resume = ["failed", "cancelled", "interrupted"].includes(task.status)
      ? `<button class="panel-primary" data-resume-task="${escapeHtml(task.task_id)}">${t("tasks.resume")}</button>`
      : "";
    const attachments = attachmentMarkup(task.attachments || []);
    openPanel(`${t("tasks.open")} · ${task.task_id}`, `<div class="task-detail"><div class="task-detail-status"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div><div class="task-detail-actions task-detail-top-actions"><button class="panel-secondary" data-open-task="${escapeHtml(task.task_id)}">${icon("arrow-up-right")} ${escapeHtml(t("tasks.openSession"))}</button></div>${runtimeMetricsMarkup(task)}<div class="panel-section-title">${t("workspace.current")}</div><code class="task-detail-path">${escapeHtml(task.workspace_path || "")}</code><div class="panel-section-title">Prompt</div><div class="task-detail-prompt">${formatText(task.prompt || task.preview || "")}</div>${attachments ? `<div class="panel-section-title">Images</div>${attachments}` : ""}<div class="panel-section-title">Response</div><div class="task-detail-answer">${formatText(task.answer || task.stream_text || task.error || "")}</div>${events ? `<div class="panel-section-title">Tools & stage trace</div><div class="task-detail-tools">${events}</div>` : ""}${children}${resume ? `<div class="task-detail-actions">${resume}</div>` : ""}</div>`, { immersive: true });
  } catch (error) {
    showToast(error.message);
  }
}

function openBatchPanel() {
  const taskFields = [1, 2, 3].map((index) => `<label class="batch-field"><span>${escapeHtml(t("batch.task"))} ${index}</span><textarea name="task" rows="3" placeholder="${escapeHtml(state.locale === "zh" ? "例如：检查后端测试并总结风险" : "For example: inspect backend tests and summarize risks")}"></textarea></label>`).join("");
  openPanel(t("panel.batch"), `<form class="batch-form" id="batchForm"><div class="batch-heading"><span class="eyebrow">${escapeHtml(t("batch.title"))}</span><h3>${escapeHtml(t("batch.title"))}</h3><p>${escapeHtml(t("batch.subtitle"))}</p></div><div class="batch-fields">${taskFields}</div><label class="batch-field"><span>${escapeHtml(t("batch.context"))}</span><textarea name="shared_context" rows="3" placeholder="${escapeHtml(t("batch.note"))}"></textarea></label><div class="task-detail-actions"><button class="panel-primary" type="submit">${icon("play")} ${escapeHtml(t("batch.run"))}</button></div></form>`, { wide: true });
}

async function openActivityPanel() {
  try {
    const data = await requestJson("/api/tasks?limit=200");
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    openPanel(t("tasks.center"), `<div class="panel-toolbar"><span>${tasks.length} ${state.locale === "zh" ? "个任务" : "tasks"}</span><button class="panel-text-action" data-panel-action="activity">${t("panel.refresh")}</button></div><div class="task-filters"><span class="filter-chip active">${t("tasks.allWorkspaces")}</span><span class="filter-chip">${escapeHtml(state.workspacePath ? state.workspacePath.split(/[\\/]/).filter(Boolean).pop() : "workspace")}</span></div><div class="task-list">${tasks.length ? tasks.map(taskRow).join("") : `<div class="empty-panel">${t("tasks.noHistory")}</div>`}</div>`);
  } catch (error) {
    openPanel(t("tasks.center"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

async function openWorkspacesPanel() {
  try {
    const info = await requestJson("/api/workspace");
    const worktrees = Array.isArray(info.worktrees) ? info.worktrees : [];
    const sandbox = info.sandbox || {};
    const mcp = info.mcp || {};
    const recent = Array.isArray(info.recent_workspaces) ? info.recent_workspaces : [];
    const recentRows = recent.length ? recent.map((item) => `<button class="workspace-row ${item.path === info.path ? "active" : ""}" data-select-workspace="${escapeHtml(item.path)}"><span class="workspace-row-icon">${icon(item.path === info.path ? "radio" : "folder")}</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.path)}</small></span>${item.path === info.path ? `<em>ACTIVE</em>` : ""}</button>`).join("") : `<div class="empty-panel">${t("panel.noWorktrees")}</div>`;
    const rows = worktrees.map((item) => `<div class="worktree-row"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.branch || "detached")} · ${escapeHtml(item.path)}</small></div>${item.managed ? `<button class="panel-icon-action" data-remove-worktree="${escapeHtml(item.name)}" title="${t("panel.close")}">${icon("trash-2")}</button>` : ""}</div>`).join("");
    const sandboxLabel = sandbox.isolated ? t("panel.isolated") : sandbox.backend === "unavailable" ? t("connection.offline") : t("panel.hostProcess");
    openPanel(t("panel.workspaces"), `<div class="workspace-switcher"><div class="panel-section-title">${t("workspace.current")}</div><code class="workspace-current-path">${escapeHtml(info.path)}</code><form class="workspace-form" id="workspaceSelectForm"><label>${t("workspace.path")}<input id="workspacePathInput" name="path" required value="${escapeHtml(info.path)}" placeholder="${t("workspace.selectHint")}" /></label><button class="panel-primary" type="submit">${t("workspace.open")}</button></form><small class="workspace-hint">${t("workspace.selectHint")}</small><div class="panel-section-title">${t("workspace.recent")}</div><div class="workspace-list">${recentRows}</div></div><div class="status-grid"><div><span>${t("panel.sandbox")}</span><strong>${escapeHtml(String(sandbox.backend || "host"))}</strong><small>${sandboxLabel}</small></div><div><span>${t("panel.mcp")}</span><strong>${escapeHtml(String(mcp.configured || 0))}</strong><small>${t("panel.servers")}</small></div></div><div class="panel-section-title">${t("panel.createWorktree")}</div><form class="worktree-form" id="worktreeForm"><input id="worktreeName" name="name" required maxlength="64" placeholder="${t("panel.name")}" /><input id="worktreeBranch" name="branch" maxlength="128" placeholder="${t("panel.branch")}" /><button class="panel-primary" type="submit">${t("panel.create")}</button></form><div class="panel-section-title">${t("panel.gitWorktrees")}</div><div class="worktree-list">${rows || `<div class="empty-panel">${t("panel.noWorktrees")}</div>`}</div>`);
  } catch (error) {
    openPanel(t("panel.workspaces"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

async function openFilePreview(path) {
  try {
    const diff = await requestJson(`/api/diff?path=${encodeURIComponent(path)}`);
    let data = { content: "" };
    try { data = await requestJson(`/api/file?path=${encodeURIComponent(path)}`); } catch { /* deleted files still have a useful diff */ }
    const diffLines = String(diff.patch || "").split("\n").map((line) => {
      const className = line.startsWith("+++") || line.startsWith("---") ? "diff-file" : line.startsWith("+") ? "diff-add-line" : line.startsWith("-") ? "diff-del-line" : line.startsWith("@@") ? "diff-hunk" : "diff-context";
      return `<span class="${className}">${escapeHtml(line || " ")}</span>`;
    }).join("\n");
    openPanel(`${t("panel.file")} · ${path}`, `<div class="diff-toolbar"><span>${escapeHtml(changeStatusLabel(diff.status || "modified"))} · <span class="diff-add">+${Number(diff.additions || 0)}</span> <span class="diff-del">-${Number(diff.deletions || 0)}</span></span><span class="mono">${escapeHtml(diff.source || "diff")}</span></div><pre class="diff-preview">${diffLines || escapeHtml(state.locale === "zh" ? "当前没有可显示的差异。" : "No diff to display.")}</pre><details class="file-current" open><summary>${escapeHtml(state.locale === "zh" ? "当前文件内容" : "Current file")}</summary><pre class="file-preview">${escapeHtml(data.content || "")}</pre></details>`);
  } catch (error) {
    openPanel(t("panel.file"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

function openSettingsPanel() {
  const current = state.locale === "zh" ? "中文" : "English";
  const effortMarkup = ["low", "mid", "high", "xhigh", "max"].map((effort) => "<option value=\"" + effort + "\" " + (state.reasoningEffort === effort ? "selected" : "") + ">" + escapeHtml(t("reasoning." + effort)) + "</option>").join("");
  const languageButtons = "<div class=\"settings-block\"><span>" + t("panel.language") + "</span><strong>" + current + "</strong><div class=\"settings-locale\"><button class=\"locale-option " + (state.locale === "zh" ? "active" : "") + "\" data-set-locale=\"zh\">中文</button><button class=\"locale-option " + (state.locale === "en" ? "active" : "") + "\" data-set-locale=\"en\">English</button></div></div>";
  const reasoningBlock = "<div class=\"settings-block\"><span>" + t("panel.reasoning") + "</span><div class=\"settings-effort\"><select id=\"reasoningEffortSelect\" aria-label=\"" + escapeHtml(t("panel.reasoning")) + "\">" + effortMarkup + "</select></div><small class=\"settings-note\">" + escapeHtml(t("panel.reasoningNote")) + "</small></div>";
  const sandboxBlock = "<div class=\"settings-block\"><span>" + t("panel.sandbox") + "</span><strong>" + (state.locale === "zh" ? "见工作区面板" : "See Workspaces") + "</strong></div>";
  openPanel(t("panel.settings"), languageButtons + reasoningBlock + sandboxBlock);
}

function openPromoPanel() {
  const promo = state.locale === "zh"
    ? {
        panel: "minicc · Agent 工作台",
        kicker: "LOCAL AGENT / INTERVIEW BUILD",
        title: "从一句话，",
        accent: "到一份可验证的交付。",
        description: "minicc 把规划、工具调用、文件改动和测试验证放在同一条可追溯路径里。你看到的是证据，不是黑盒里的猜测。",
        cta: "开始新任务",
        ctaNote: "LOCAL FIRST · SSE STREAM",
        proofTitle: "从第一行代码到最后一次验证",
        proofBody: "一个工作区 · 一条可追溯路径",
        previewLabel: "agent / live",
        live: "RUNNING",
        taskLabel: "强化版宣传页",
        taskMeta: "workspace · minicc-codex",
        metrics: ["SSE 实时", "00:14", "72% context"],
        phases: [
          ["01", "理解需求", "拆解目标与验收标准", "check", "done"],
          ["02", "修改工作区", "写入前先检查当前 diff", "loader-circle", "active"],
          ["03", "验证交付", "测试结果和剩余风险可复盘", "circle-dashed", ""],
        ],
        diffLabel: "live diff / web/styles.css",
        diff: [["+", "--agent-accent: coral;"], ["+", "--stream-mode: live;"], ["-", "--status: waiting;"], [" ", "/* verified by pytest */"]],
        sectionKicker: "WHY MINICC",
        sectionTitle: "少一点猜测，多一点确定。",
        sectionBody: "为真实的工程协作设计：先收集上下文，再执行动作，最后用验证结果闭环。",
        capabilities: [
          ["scan-search", "看得见过程", "阶段摘要、工具调用、流式回答和上下文用量实时呈现，复杂任务不会突然失去方向。"],
          ["layers-3", "并行而不互相阻塞", "独立会话使用独立任务槽位；批量任务可并行执行，完成后再合并结果。"],
          ["git-compare", "改动可审查", "文件列表和红绿 diff 直接联动，点击文件即可查看变更与当前内容。"],
          ["shield-check", "本地优先", "工作区、权限、取消、重试和审计都由本地 harness 负责，模型只负责判断。"],
        ],
        bottomKicker: "READY WHEN YOU ARE",
        bottomTitle: "下一次提交，",
        bottomAccent: "从一句话开始。",
        bottomBody: "切换中文或 English，打开一个真实工作区，立即体验完整循环。",
        bottomCta: "进入工作台",
      }
    : {
        panel: "minicc · Agent workspace",
        kicker: "LOCAL AGENT / INTERVIEW BUILD",
        title: "From one prompt,",
        accent: "to a delivery you can verify.",
        description: "minicc puts planning, tool calls, file changes, and verification on one traceable path. You see evidence, not a black box guessing in the dark.",
        cta: "Start a new task",
        ctaNote: "LOCAL FIRST · SSE STREAM",
        proofTitle: "From the first line to the final check",
        proofBody: "One workspace · One traceable path",
        previewLabel: "agent / live",
        live: "RUNNING",
        taskLabel: "Harden the promo page",
        taskMeta: "workspace · minicc-codex",
        metrics: ["SSE live", "00:14", "72% context"],
        phases: [
          ["01", "Understand the request", "Turn intent into acceptance criteria", "check", "done"],
          ["02", "Change the workspace", "Inspect the diff before writing", "loader-circle", "active"],
          ["03", "Verify the delivery", "Keep tests and remaining risk visible", "circle-dashed", ""],
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
          ["shield-check", "Local first", "The local harness owns workspace, permissions, cancellation, retries, and audit trails. The model owns judgment."],
        ],
        bottomKicker: "READY WHEN YOU ARE",
        bottomTitle: "Your next commit,",
        bottomAccent: "starts with a sentence.",
        bottomBody: "Switch between Chinese and English, open a real workspace, and run the full loop.",
        bottomCta: "Open workspace",
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
        <div class="promo-proof"><span class="proof-avatars"><b>m</b><b>✓</b><b>⌘</b></span><span><strong>${escapeHtml(promo.proofTitle)}</strong><small>${escapeHtml(promo.proofBody)}</small></span></div>
      </div>
      <div class="promo-hero-preview" aria-label="${escapeHtml(promo.previewLabel)}">
        <div class="promo-preview-head"><span class="terminal-dot coral"></span><span class="terminal-dot amber"></span><span class="terminal-dot mint"></span><span class="mono">${escapeHtml(promo.previewLabel)}</span><span class="console-live"><i></i> ${escapeHtml(promo.live)}</span></div>
        <div class="promo-preview-task"><span class="promo-preview-icon">${icon("sparkles")}</span><span><strong>${escapeHtml(promo.taskLabel)}</strong><small>${escapeHtml(promo.taskMeta)}</small></span><span class="promo-preview-check">${icon("radio")}</span></div>
        <div class="promo-metrics">${metricMarkup}</div>
        <div class="promo-phase-list">${phaseMarkup}</div>
        <div class="promo-diff"><div><span class="mono">${escapeHtml(promo.diffLabel)}</span><span class="promo-diff-state">● LIVE</span></div><pre>${diffMarkup}</pre></div>
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
  showToast(state.locale === "zh" ? "对话已导出" : "Chat exported");
}

function switchInspectorTab(tab) {
  $$(".inspector-tab").forEach((item) => item.classList.toggle("active", item.dataset.inspectorTab === tab));
  $("#overviewSection").hidden = tab !== "overview";
  $("#changesSection").hidden = tab !== "changes";
}

function openGame() {
  $("#gameModal").classList.add("show");
  $("#gameModal").setAttribute("aria-hidden", "false");
  initGame();
}

function closeGame() {
  const active = document.activeElement;
  if (active instanceof HTMLElement && $("#gameModal").contains(active)) active.blur();
  $("#gameModal").classList.remove("show");
  $("#gameModal").setAttribute("aria-hidden", "true");
  game.running = false;
  cancelAnimationFrame(game.frame);
  stopGameMusic();
  window.scrollTo(0, 0);
}

const MAX_WAVES = 10;
const GAME_DIFFICULTIES = {
  normal: { hpMultiplier: .9, initialSun: 200, speedMultiplier: .9, spawnDelayMultiplier: 1.16, waveBonus: -1 },
  hard: { hpMultiplier: 1, initialSun: 175, speedMultiplier: 1, spawnDelayMultiplier: 1, waveBonus: 0 },
  nightmare: { hpMultiplier: 1.28, initialSun: 150, speedMultiplier: 1.16, spawnDelayMultiplier: .8, waveBonus: 2 },
};
const savedGameDifficulty = Object.prototype.hasOwnProperty.call(GAME_DIFFICULTIES, localStorage.getItem("minicc-game-difficulty")) ? localStorage.getItem("minicc-game-difficulty") : "hard";
const WAVE_TARGET = (wave, difficulty = savedGameDifficulty) => 7 + wave * 2 + GAME_DIFFICULTIES[difficulty].waveBonus;
const game = { running: false, paused: false, pauseReasons: new Set(), frame: 0, score: 0, sun: GAME_DIFFICULTIES[savedGameDifficulty].initialSun, wave: 1, waveTarget: WAVE_TARGET(1), waveSpawned: 0, totalSpawned: 0, waveClearTimer: 0, elapsed: 0, selected: null, shovel: false, plants: [], zombies: [], suns: [], shots: [], particles: [], last: 0, spawnTimer: 0, skyTimer: 0, dangerTimer: 0, difficulty: savedGameDifficulty, autoSun: localStorage.getItem("minicc-game-auto-sun") !== "off", musicOn: localStorage.getItem("minicc-game-sound") !== "off", volume: Math.max(0, Math.min(100, Number(localStorage.getItem("minicc-game-volume")) || 70)), audio: null };
const gameLayout = { left: 78, top: 72, cellW: 70, cellH: 65, rows: 5, cols: 9 };
const plantCost = { peashooter: 100, sunflower: 50, wallnut: 50, repeater: 180, cherrybomb: 150, icepeashooter: 175 };
const plantHealth = { peashooter: 7, sunflower: 6, wallnut: 24, repeater: 8, cherrybomb: 4, icepeashooter: 7 };
const plantColor = { peashooter: "#62b5a0", sunflower: "#f6c453", wallnut: "#ad7556", repeater: "#75c77b", cherrybomb: "#dd6d73", icepeashooter: "#8bc9e8" };
const plantProfiles = {
  peashooter: { interval: 1050, shots: 1, damage: 1, slow: 0 },
  repeater: { interval: 1250, shots: 2, damage: 1, slow: 0 },
  icepeashooter: { interval: 1300, shots: 1, damage: 1, slow: 3200 },
};
const zombieProfiles = {
  walker: { hp: 5, speed: .020, growth: .0010, attackInterval: 1000, score: 1 },
  roadblock: { hp: 12, speed: .013, growth: .00065, attackInterval: 670, score: 3 },
  runner: { hp: 4, speed: .036, growth: .0008, attackInterval: 1150, score: 2 },
  bucket: { hp: 21, speed: .011, growth: .00045, attackInterval: 620, score: 5 },
};
function gameDifficulty() { return GAME_DIFFICULTIES[game.difficulty] || GAME_DIFFICULTIES.hard; }
function updatePauseButton() {
  const button = $("#gamePause");
  if (!button) return;
  const paused = game.pauseReasons.has("manual");
  button.classList.toggle("active", paused);
  button.setAttribute("aria-pressed", String(paused));
  button.querySelector("strong").textContent = t(paused ? "game.resume" : "game.pause");
  button.querySelector("small").textContent = t(paused ? "game.resumeHint" : "game.pauseHint");
}
function setGamePauseReason(reason, paused) {
  if (!game.running) return;
  if (paused) game.pauseReasons.add(reason);
  else game.pauseReasons.delete(reason);
  const nextPaused = game.pauseReasons.size > 0;
  if (game.paused === nextPaused) {
    updatePauseButton();
    if (nextPaused) setGameStatus(game.pauseReasons.has("manual") ? "game.manualPaused" : "game.paused");
    return;
  }
  game.paused = nextPaused;
  cancelAnimationFrame(game.frame);
  updatePauseButton();
  if (nextPaused) {
    stopGameMusic();
    setGameStatus(reason === "manual" ? "game.manualPaused" : "game.paused");
    drawGame();
    return;
  }
  game.last = performance.now();
  setGameStatus("game.running");
  startGameMusic();
  game.frame = requestAnimationFrame(gameLoop);
}
function toggleGamePause() { setGamePauseReason("manual", !game.pauseReasons.has("manual")); }
function setGameDifficulty(value) {
  if (game.running || !Object.prototype.hasOwnProperty.call(GAME_DIFFICULTIES, value)) return;
  game.difficulty = value;
  localStorage.setItem("minicc-game-difficulty", value);
  initGame();
}
function updateShovelButton() {
  const button = $("#gameShovel");
  if (!button) return;
  button.classList.toggle("active", game.shovel);
  button.setAttribute("aria-pressed", String(game.shovel));
}
function toggleShovel() {
  game.shovel = !game.shovel;
  if (game.shovel) clearPlantSelection();
  updateShovelButton();
  drawGame();
}
function clearPlantSelection() {
  game.selected = null;
  $$(".seed-card").forEach((card) => card.classList.remove("selected"));
}
function selectPlant(card) {
  if (game.shovel) {
    game.shovel = false;
    updateShovelButton();
  }
  const next = card.dataset.plant;
  game.selected = game.selected === next ? null : next;
  $$(".seed-card").forEach((item) => item.classList.toggle("selected", item.dataset.plant === game.selected));
}
function formatGameTime(value) {
  const total = Math.max(0, Math.floor(value / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
function updateGameHud() {
  $("#gameSun").textContent = String(game.sun);
  $("#gameScore").textContent = String(game.score);
  $("#gameWave").textContent = `${Math.min(game.wave, MAX_WAVES)}/${MAX_WAVES}`;
  $("#gameTime").textContent = formatGameTime(game.elapsed);
  const pressure = `${t("game.threat")}: ${game.waveSpawned}/${game.waveTarget}`;
  $("#gameThreat").textContent = pressure;
  $("#gameProgressFill").style.width = `${Math.round((game.waveSpawned / Math.max(1, game.waveTarget)) * 100)}%`;
  $("#gameWaveHint").textContent = t(game.wave >= 7 ? "game.wavePressure" : "game.waveHint");
}
function cellPosition(row, col) { return { x: gameLayout.left + col * gameLayout.cellW + 35, y: gameLayout.top + row * gameLayout.cellH + 31 }; }
function addGameParticle(x, y, color, count = 6, speed = 0.08) {
  for (let i = 0; i < count; i += 1) game.particles.push({ x, y, vx: (Math.random() - .5) * speed, vy: (Math.random() - .7) * speed, life: 420 + Math.random() * 360, maxLife: 780, size: 2 + Math.random() * 3, color });
}
function gameVolume() { return game.musicOn ? .1 * (game.volume / 100) : .001; }
function playGameSound(kind) {
  if (!game.musicOn || !game.volume) return;
  try {
    if (!game.audio) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext(); const master = ctx.createGain(); master.gain.value = gameVolume(); master.connect(ctx.destination);
      game.audio = { ctx, master, musicTimer: null, step: 0, lastSound: {} };
    }
    const { ctx, master } = game.audio;
    if (ctx.state === "suspended") ctx.resume();
    const sounds = {
      collect: { notes: [660, 880], type: "sine", duration: .16, step: .055, volume: .14 },
      plant: { notes: [330, 494], type: "triangle", duration: .2, step: .07, volume: .14 },
      shoot: { notes: [180, 230], type: "square", duration: .1, step: .035, volume: .08 },
      hit: { notes: [145], type: "square", duration: .08, step: 0, volume: .08 },
      explode: { notes: [130, 92, 58], type: "sawtooth", duration: .34, step: .07, volume: .2 },
      wave: { notes: [392, 523, 659], type: "triangle", duration: .42, step: .1, volume: .16 },
      victory: { notes: [523, 659, 784, 1046], type: "triangle", duration: .7, step: .11, volume: .18 },
      gameover: { notes: [220, 165, 110], type: "sawtooth", duration: .55, step: .13, volume: .16 },
      danger: { notes: [110, 98], type: "square", duration: .18, step: .08, volume: .1 },
    };
    const sound = sounds[kind] || sounds.hit;
    const now = ctx.currentTime;
    const minInterval = { hit: .055, shoot: .08, collect: .04 }[kind] || 0;
    if (minInterval && now - (game.audio.lastSound[kind] || 0) < minInterval) return;
    game.audio.lastSound[kind] = now;
    sound.notes.forEach((frequency, index) => {
      const start = now + index * sound.step;
      const oscillator = ctx.createOscillator(); const gain = ctx.createGain();
      oscillator.type = sound.type; oscillator.frequency.setValueAtTime(frequency, start);
      gain.gain.setValueAtTime(.001, start); gain.gain.linearRampToValueAtTime(sound.volume, start + .012); gain.gain.exponentialRampToValueAtTime(.001, start + sound.duration);
      oscillator.connect(gain); gain.connect(master); oscillator.start(start); oscillator.stop(start + sound.duration + .02);
    });
  } catch { /* Audio is an enhancement, not a gameplay dependency. */ }
}
function startGameMusic() {
  if (!game.musicOn || game.audio?.musicTimer) return;
  playGameSound("plant");
  if (!game.audio) return;
  const melody = [262, 330, 392, 330, 294, 349, 440, 349, 392, 494, 587, 494];
  game.audio.musicTimer = window.setInterval(() => {
    if (!game.running || !game.musicOn || !game.audio) return;
    const { ctx, master } = game.audio; const oscillator = ctx.createOscillator(); const gain = ctx.createGain();
    const start = ctx.currentTime; oscillator.type = "triangle"; oscillator.frequency.setValueAtTime(melody[game.audio.step++ % melody.length], start); gain.gain.setValueAtTime(.001, start); gain.gain.linearRampToValueAtTime(.05, start + .02); gain.gain.exponentialRampToValueAtTime(.001, start + .3); oscillator.connect(gain); gain.connect(master); oscillator.start(start); oscillator.stop(start + .34);
  }, 560);
}
function stopGameMusic() { if (game.audio?.musicTimer) { clearInterval(game.audio.musicTimer); game.audio.musicTimer = null; } }
function updateSoundButton() { const button = $("#gameSoundToggle"); const volume = $("#gameVolume"); if (button) { button.textContent = t(game.musicOn ? "game.soundOn" : "game.soundOff"); button.classList.toggle("muted", !game.musicOn); button.setAttribute("aria-pressed", String(game.musicOn)); } if (volume) volume.value = String(game.volume); }
function setGameVolume(value) { game.volume = Math.max(0, Math.min(100, Number(value) || 0)); localStorage.setItem("minicc-game-volume", String(game.volume)); if (game.audio?.master) game.audio.master.gain.setTargetAtTime(gameVolume(), game.audio.ctx.currentTime, .02); }
function toggleGameSound() { game.musicOn = !game.musicOn; localStorage.setItem("minicc-game-sound", game.musicOn ? "on" : "off"); if (game.audio?.master) game.audio.master.gain.setTargetAtTime(gameVolume(), game.audio.ctx.currentTime, .02); if (game.musicOn && game.volume) { playGameSound("collect"); startGameMusic(); } else stopGameMusic(); updateSoundButton(); }
function setGameStatus(key) { $("#gameStatus").textContent = t(key); }
function setGamePaused(paused) { setGamePauseReason("visibility", paused); }
function finishGame(statusKey) {
  game.running = false;
  stopGameMusic();
  setGameStatus(statusKey);
  if (statusKey === "game.victory") playGameSound("victory");
  else if (statusKey === "game.gameOver") playGameSound("gameover");
  $("#gameStart").textContent = t("game.restart");
  updateGameHud();
  drawGame();
}
function initGame() {
  stopGameMusic();
  game.running = false;
  game.paused = false;
  game.pauseReasons.clear();
  game.score = 0;
  game.sun = gameDifficulty().initialSun;
  game.wave = 1;
  game.waveTarget = WAVE_TARGET(game.wave, game.difficulty);
  game.waveSpawned = 0;
  game.totalSpawned = 0;
  game.waveClearTimer = 0;
  game.elapsed = 0;
  game.shovel = false;
  game.autoSun = localStorage.getItem("minicc-game-auto-sun") !== "off";
  game.plants = [];
  game.zombies = [];
  game.suns = [];
  game.shots = [];
  game.particles = [];
  game.last = 0;
  game.spawnTimer = 0;
  game.skyTimer = 0;
  game.dangerTimer = 0;
  $("#gameAutoSun").checked = game.autoSun;
  $("#gameDifficulty").value = game.difficulty;
  clearPlantSelection();
  updateShovelButton();
  updatePauseButton();
  updateSoundButton();
  updateGameHud();
  setGameStatus("game.ready");
  $("#gameStart").textContent = t("game.start");
  drawGame();
}
function roundedRect(ctx, x, y, width, height, radius) { ctx.beginPath(); ctx.roundRect(x, y, width, height, radius); }
function drawSun(ctx, sun) { const pulse = 1 + Math.sin(sun.age / 230) * .08; ctx.save(); ctx.translate(sun.x, sun.y); ctx.scale(pulse, pulse); ctx.shadowColor = "rgba(255, 215, 84, .75)"; ctx.shadowBlur = 18; ctx.fillStyle = "#ffd75b"; ctx.beginPath(); ctx.arc(0, 0, 15, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = "#fff3a5"; ctx.lineWidth = 3; for (let i = 0; i < 8; i += 1) { const angle = i * Math.PI / 4; ctx.beginPath(); ctx.moveTo(Math.cos(angle) * 19, Math.sin(angle) * 19); ctx.lineTo(Math.cos(angle) * 25, Math.sin(angle) * 25); ctx.stroke(); } ctx.fillStyle = "#fff4a8"; ctx.beginPath(); ctx.arc(-4, -4, 4, 0, Math.PI * 2); ctx.fill(); ctx.restore(); }
function drawPlant(ctx, plant, now) { const bob = Math.sin((now + plant.seed) / 480) * 2; const { x, y } = cellPosition(plant.row, plant.col); ctx.save(); ctx.translate(x, y + bob); ctx.fillStyle = "rgba(22, 59, 42, .24)"; ctx.beginPath(); ctx.ellipse(0, 25, 23, 7, 0, 0, Math.PI * 2); ctx.fill();
  if (plant.type === "sunflower") { for (let i = 0; i < 10; i += 1) { const angle = i * Math.PI / 5; ctx.fillStyle = i % 2 ? "#f4b83f" : "#ffd765"; ctx.beginPath(); ctx.ellipse(Math.cos(angle) * 14, Math.sin(angle) * 14 - 5, 7, 13, angle, 0, Math.PI * 2); ctx.fill(); } ctx.fillStyle = "#75482d"; ctx.beginPath(); ctx.arc(0, -5, 10, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#9c6a35"; ctx.beginPath(); ctx.arc(-3, -8, 2, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#438553"; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(0, 7); ctx.lineTo(0, 22); ctx.stroke(); }
  else if (plant.type === "cherrybomb") { ctx.fillStyle = "#c94f60"; ctx.beginPath(); ctx.arc(-9, -5, 12, 0, Math.PI * 2); ctx.arc(9, -5, 12, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#f49a86"; ctx.beginPath(); ctx.arc(-13, -9, 4, 0, Math.PI * 2); ctx.arc(5, -9, 4, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#5f8d4c"; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(0, -14); ctx.quadraticCurveTo(2, -28, 12, -28); ctx.stroke(); ctx.fillStyle = "#f4d27a"; ctx.beginPath(); ctx.arc(13, -28, 4, 0, Math.PI * 2); ctx.fill(); }
  else if (plant.type === "wallnut") { ctx.fillStyle = "#b87b55"; ctx.strokeStyle = "#6d432f"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(0, 0, 19, 24, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.fillStyle = "#3f2f27"; ctx.beginPath(); ctx.arc(-7, -5, 2.5, 0, Math.PI * 2); ctx.arc(7, -5, 2.5, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#6d432f"; ctx.beginPath(); ctx.arc(0, 5, 8, 0, Math.PI); ctx.stroke(); }
  else { ctx.strokeStyle = "#438553"; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(0, 19); ctx.lineTo(0, -3); ctx.stroke(); ctx.fillStyle = plant.type === "icepeashooter" ? "#9cddf1" : plant.type === "repeater" ? "#70c985" : "#63b98d"; ctx.beginPath(); ctx.ellipse(-12, 12, 13, 6, -.45, 0, Math.PI * 2); ctx.ellipse(11, 14, 13, 6, .45, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = plant.type === "icepeashooter" ? "#b9eff7" : "#74c9a5"; ctx.beginPath(); ctx.arc(0, -14, 14, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = plant.type === "icepeashooter" ? "#4385a2" : "#244a3d"; ctx.beginPath(); ctx.arc(9, -14, 8, -.4, .4); ctx.fill(); ctx.fillStyle = "#d7f4d0"; ctx.beginPath(); ctx.arc(12, -14, 3, 0, Math.PI * 2); ctx.fill(); if (plant.type === "repeater") { ctx.fillStyle = "#244a3d"; ctx.beginPath(); ctx.arc(12, -5, 6, 0, Math.PI * 2); ctx.fill(); } }
  if (plant.hp < plantHealth[plant.type]) { ctx.fillStyle = "rgba(25, 33, 26, .7)"; ctx.fillRect(-18, 29, 36, 4); ctx.fillStyle = plant.hp / plantHealth[plant.type] > .4 ? "#80d6a2" : "#f6b35c"; ctx.fillRect(-18, 29, 36 * Math.max(0, plant.hp / plantHealth[plant.type]), 4); } ctx.restore(); }
function drawZombie(ctx, zombie, now) {
  const walk = Math.sin((now + zombie.seed) / (zombie.type === "runner" ? 100 : 170)) * 3;
  const profile = zombie.type === "bucket" ? { body: "#5d6472", head: "#b8c4aa" } : zombie.type === "roadblock" ? { body: "#485267", head: "#b8c4aa" } : zombie.type === "runner" ? { body: "#7c625d", head: "#c5c7a9" } : { body: "#556b62", head: "#b8c4aa" };
  const y = zombie.y;
  ctx.save();
  ctx.translate(zombie.x, y + walk);
  ctx.fillStyle = "rgba(26, 28, 39, .28)";
  ctx.beginPath();
  ctx.ellipse(0, 25, 23, 7, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#262c39";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(-7, 16);
  ctx.lineTo(-11 + walk, 29);
  ctx.moveTo(7, 16);
  ctx.lineTo(11 - walk, 29);
  ctx.stroke();
  ctx.fillStyle = profile.body;
  roundedRect(ctx, -15, -1, 30, 25, 8);
  ctx.fill();
  ctx.fillStyle = profile.head;
  ctx.beginPath();
  ctx.arc(0, -16, 15, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#29303d";
  ctx.beginPath();
  ctx.arc(-5, -17, 3, 0, Math.PI * 2);
  ctx.arc(6, -17, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#f0a27e";
  ctx.beginPath();
  ctx.arc(-6, -9, 3, 0, Math.PI * 2);
  ctx.arc(6, -9, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#29303d";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(-8, -2);
  ctx.lineTo(8, -2);
  ctx.stroke();
  if (zombie.type === "roadblock") {
    ctx.fillStyle = "#d98258";
    ctx.fillRect(-18, -30, 36, 7);
    ctx.fillStyle = "#f2c05e";
    ctx.fillRect(-12, -34, 24, 4);
  } else if (zombie.type === "bucket") {
    ctx.fillStyle = "#a6adb5";
    ctx.fillRect(-17, -31, 34, 14);
    ctx.fillStyle = "#68717d";
    ctx.fillRect(-20, -20, 40, 4);
  } else if (zombie.type === "runner") {
    ctx.strokeStyle = "#e78366";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(-15, 4);
    ctx.lineTo(-25, -2);
    ctx.moveTo(15, 4);
    ctx.lineTo(25, -2);
    ctx.stroke();
  }
  if (zombie.slowTimer > 0) {
    ctx.strokeStyle = "#a7e8f3";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(0, -3, 22, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (zombie.hp < zombie.maxHp) {
    ctx.fillStyle = "rgba(25, 33, 26, .7)";
    ctx.fillRect(-19, 34, 38, 4);
    ctx.fillStyle = "#e48374";
    ctx.fillRect(-19, 34, 38 * Math.max(0, zombie.hp / zombie.maxHp), 4);
  }
  ctx.restore();
}
function drawGame() { const canvas = $("#gameCanvas"); if (!canvas) return; const ctx = canvas.getContext("2d"); const now = performance.now(); const sky = ctx.createLinearGradient(0, 0, 0, 420); sky.addColorStop(0, "#9bd9df"); sky.addColorStop(.35, "#d7e7b2"); sky.addColorStop(.36, "#659b58"); sky.addColorStop(1, "#315744"); ctx.fillStyle = sky; ctx.fillRect(0, 0, 720, 420); ctx.fillStyle = "rgba(255,255,255,.18)"; ctx.beginPath(); ctx.arc(605, 42, 29, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#253b45"; ctx.fillRect(0, 0, 720, 58); ctx.fillStyle = "#eef3cf"; ctx.font = "700 12px Manrope, sans-serif"; ctx.fillText("BACKYARD", 18, 23); ctx.fillStyle = "#a8d5a1"; ctx.font = "10px DM Mono, monospace"; ctx.fillText(game.running ? "DEFEND THE LAWN" : "READY FOR BATTLE", 18, 42); ctx.fillStyle = "#d9b16e"; ctx.fillRect(48, 28, 17, 23); ctx.fillStyle = "#693f38"; ctx.beginPath(); ctx.moveTo(44, 29); ctx.lineTo(57, 16); ctx.lineTo(70, 29); ctx.fill(); ctx.fillStyle = "#f4d27a"; ctx.fillRect(53, 39, 7, 12);
  for (let row = 0; row < gameLayout.rows; row += 1) for (let col = 0; col < gameLayout.cols; col += 1) { const x = gameLayout.left + col * gameLayout.cellW, y = gameLayout.top + row * gameLayout.cellH; ctx.fillStyle = (row + col) % 2 ? "#75b866" : "#83c573"; roundedRect(ctx, x + 2, y + 2, 66, 61, 8); ctx.fill(); ctx.strokeStyle = "rgba(221, 246, 151, .18)"; ctx.stroke(); }
  ctx.fillStyle = "rgba(240, 213, 140, .28)"; ctx.fillRect(674, 60, 3, 360); game.suns.forEach((sun) => drawSun(ctx, sun)); game.plants.forEach((plant) => drawPlant(ctx, plant, now)); game.shots.forEach((shot) => { ctx.fillStyle = shot.color || "#b5f0a2"; ctx.shadowColor = shot.slow ? "#a7e8f3" : "#80ed9a"; ctx.shadowBlur = 12; ctx.beginPath(); ctx.arc(shot.x, shot.y, 6, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0; }); game.zombies.forEach((zombie) => drawZombie(ctx, zombie, now)); game.particles.forEach((particle) => { ctx.globalAlpha = Math.max(0, particle.life / particle.maxLife); ctx.fillStyle = particle.color; ctx.beginPath(); ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2); ctx.fill(); }); ctx.globalAlpha = 1; }
function zombieTypeForWave() {
  const roll = Math.random();
  const pressure = game.difficulty === "nightmare" ? 1.25 : game.difficulty === "normal" ? .82 : 1;
  const bucketChance = Math.min(.32, (.1 + game.wave * .012) * pressure);
  const runnerChance = Math.min(.46, (.24 + game.wave * .014) * pressure);
  const roadblockChance = Math.min(.78, (.44 + game.wave * .018) * pressure);
  if (game.wave >= 4 && roll < bucketChance) return "bucket";
  if (game.wave >= 3 && roll < runnerChance) return "runner";
  if (game.wave >= 2 && roll < roadblockChance) return "roadblock";
  return "walker";
}
function spawnZombie() {
  if (game.waveSpawned >= game.waveTarget) return;
  const row = Math.floor(Math.random() * gameLayout.rows);
  const type = zombieTypeForWave();
  const profile = zombieProfiles[type];
  const difficulty = gameDifficulty();
  const hpGrowth = type === "bucket" ? 1.2 : type === "roadblock" ? .85 : .7;
  const hp = Math.max(1, Math.round((profile.hp + Math.floor(game.wave * hpGrowth)) * difficulty.hpMultiplier));
  game.zombies.push({
    x: 704,
    y: cellPosition(row, 0).y,
    row,
    hp,
    maxHp: hp,
    type,
    speed: (profile.speed + game.wave * profile.growth) * difficulty.speedMultiplier,
    attackInterval: profile.attackInterval,
    slowTimer: 0,
    seed: Math.random() * 1000,
  });
  game.waveSpawned += 1;
  game.totalSpawned += 1;
  if (game.wave > 1 && game.waveSpawned === 1) setGameStatus("game.running");
  if (game.waveSpawned === game.waveTarget) {
    playGameSound("wave");
    addGameParticle(360, 60, "#ffe27c", 18, .18);
  }
  updateGameHud();
}
function produceSun(plant) {
  const position = cellPosition(plant.row, plant.col);
  game.suns.push({ x: position.x + (Math.random() - .5) * 24, y: position.y - 28, age: 0, targetY: position.y - 5 });
  addGameParticle(position.x, position.y - 22, "#ffe17b", 8, .12);
}
function collectSunAt(index, x, y) {
  if (index < 0 || !game.suns[index]) return false;
  game.suns.splice(index, 1);
  game.sun += 25;
  updateGameHud();
  addGameParticle(x, y, "#ffe17b", 12, .16);
  playGameSound("collect");
  return true;
}
function collectAutomaticSuns() {
  if (!game.autoSun) return;
  for (let index = game.suns.length - 1; index >= 0; index -= 1) {
    const sun = game.suns[index];
    if (sun.age > 650) collectSunAt(index, sun.x, sun.y);
  }
}
function firePlantShots(plant, profile) {
  const position = cellPosition(plant.row, plant.col);
  for (let index = 0; index < profile.shots; index += 1) {
    game.shots.push({ x: position.x + 20 + index * 8, y: position.y - 5, row: plant.row, damage: profile.damage, slow: profile.slow, color: plant.type === "icepeashooter" ? "#c9f6ff" : "#b5f0a2", hit: false });
  }
  playGameSound("shoot");
}
function explodeCherryBomb(plant) {
  const position = cellPosition(plant.row, plant.col);
  const defeated = game.zombies.filter((zombie) => zombie.row === plant.row && Math.abs(zombie.x - position.x) < 145);
  defeated.forEach((zombie) => {
    const index = game.zombies.indexOf(zombie);
    if (index >= 0) game.zombies.splice(index, 1);
    game.score += zombieProfiles[zombie.type]?.score || 1;
  });
  game.plants.splice(game.plants.indexOf(plant), 1);
  addGameParticle(position.x, position.y - 5, "#ff8d73", 34, .3);
  playGameSound("explode");
  updateGameHud();
}
function advanceWave(dt) {
  if (game.waveSpawned < game.waveTarget || game.zombies.length) {
    game.waveClearTimer = 0;
    return false;
  }
  game.waveClearTimer += dt;
  if (game.waveClearTimer < 1400) return false;
  if (game.wave >= MAX_WAVES) {
    finishGame("game.victory");
    return true;
  }
  game.wave += 1;
  game.waveTarget = WAVE_TARGET(game.wave, game.difficulty);
  game.waveSpawned = 0;
  game.waveClearTimer = 0;
  game.spawnTimer = 0;
  setGameStatus("game.waveIncoming");
  playGameSound("wave");
  addGameParticle(360, 60, "#ffe27c", 18, .18);
  updateGameHud();
  return false;
}
function gameLoop(now = 0) {
  if (!game.running || game.paused) return;
  const dt = Math.min(80, Math.max(8, now - game.last || 16));
  game.last = now;
  game.elapsed += dt;
  updateGameHud();
  game.spawnTimer += dt;
  game.skyTimer += dt;
  game.dangerTimer += dt;
  if (game.zombies.some((zombie) => zombie.x < 165) && game.dangerTimer > 850) {
    game.dangerTimer = 0;
    playGameSound("danger");
  }
  const spawnDelay = Math.max(780, (3300 - game.wave * 240) * gameDifficulty().spawnDelayMultiplier);
  if (game.waveSpawned < game.waveTarget && ((game.waveSpawned === 0 && game.spawnTimer > 1800) || game.spawnTimer > spawnDelay)) {
    spawnZombie();
    game.spawnTimer = 0;
  }
  if (game.skyTimer > 4800 && game.suns.length < 10) {
    game.skyTimer = 0;
    game.suns.push({ x: 105 + Math.random() * 535, y: 88 + Math.random() * 270, age: 0, targetY: 80 + Math.random() * 240 });
  }
  game.suns.forEach((sun) => { sun.age += dt; if (sun.y < sun.targetY) sun.y = Math.min(sun.targetY, sun.y + dt * .05); });
  collectAutomaticSuns();
  game.plants.slice().forEach((plant) => {
    plant.age += dt;
    if (plant.type === "sunflower") {
      plant.sunTimer += dt;
      if (plant.sunTimer > 4800 && game.suns.length < 12) { plant.sunTimer = 0; produceSun(plant); }
      return;
    }
    if (plant.type === "cherrybomb") {
      plant.bombTimer += dt;
      if (plant.bombTimer > 950) explodeCherryBomb(plant);
      return;
    }
    const profile = plantProfiles[plant.type];
    if (!profile) return;
    plant.shotTimer += dt;
    const position = cellPosition(plant.row, plant.col);
    if (plant.shotTimer > profile.interval && game.zombies.some((zombie) => zombie.row === plant.row && zombie.x > position.x)) {
      plant.shotTimer = 0;
      firePlantShots(plant, profile);
    }
  });
  game.zombies.slice().forEach((zombie) => {
    zombie.y = cellPosition(zombie.row, 0).y;
    zombie.slowTimer = Math.max(0, zombie.slowTimer - dt);
    const blocker = game.plants.find((plant) => plant.row === zombie.row && Math.abs(cellPosition(plant.row, plant.col).x - zombie.x) < 30);
    if (blocker) {
      blocker.hp -= dt / zombie.attackInterval;
      if (blocker.hp <= 0) {
        const position = cellPosition(blocker.row, blocker.col);
        addGameParticle(position.x, position.y, "#c78363", 14, .18);
        game.plants.splice(game.plants.indexOf(blocker), 1);
        playGameSound("hit");
      }
    } else {
      zombie.x -= zombie.speed * dt * (zombie.slowTimer > 0 ? .48 : 1);
    }
  });
  game.shots.forEach((shot) => {
    shot.x += .34 * dt;
    const hit = game.zombies.find((zombie) => zombie.row === shot.row && zombie.x > shot.x - 12 && zombie.x < shot.x + 23);
    if (!hit) return;
    shot.hit = true;
    hit.hp -= shot.damage || 1;
    if (shot.slow) hit.slowTimer = Math.max(hit.slowTimer, shot.slow);
    addGameParticle(shot.x, shot.y, shot.color || "#b7f3a0", 5, .1);
    playGameSound("hit");
    if (hit.hp <= 0) {
      const index = game.zombies.indexOf(hit);
      if (index >= 0) game.zombies.splice(index, 1);
      game.score += zombieProfiles[hit.type]?.score || 1;
      updateGameHud();
      addGameParticle(hit.x, hit.y, "#f6d681", 18, .2);
    }
  });
  game.shots = game.shots.filter((shot) => !shot.hit && shot.x < 735);
  game.particles.forEach((particle) => { particle.x += particle.vx * dt; particle.y += particle.vy * dt; particle.vy += .00025 * dt; particle.life -= dt; });
  game.particles = game.particles.filter((particle) => particle.life > 0);
  if (game.zombies.some((zombie) => zombie.x < 61)) {
    addGameParticle(55, 180, "#ff9f83", 24, .22);
    finishGame("game.gameOver");
    return;
  }
  if (advanceWave(dt)) return;
  drawGame();
  if (game.running) game.frame = requestAnimationFrame(gameLoop);
}
function startGame() { cancelAnimationFrame(game.frame); initGame(); game.running = true; game.paused = false; game.last = performance.now(); setGameStatus("game.running"); $("#gameStart").textContent = t("game.restart"); startGameMusic(); game.frame = requestAnimationFrame(gameLoop); }
function canvasPoint(event) { const canvas = $("#gameCanvas"), rect = canvas.getBoundingClientRect(); return { x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height }; }
function collectSun(event) { const { x, y } = canvasPoint(event); const hit = game.suns.findIndex((sun) => Math.hypot(sun.x - x, sun.y - y) < 32); if (hit < 0) return false; const sun = game.suns[hit]; collectSunAt(hit, sun.x, sun.y); drawGame(); return true; }
function gameCellAt(x, y) { if (y < gameLayout.top || x < gameLayout.left) return null; const col = Math.floor((x - gameLayout.left) / gameLayout.cellW), row = Math.floor((y - gameLayout.top) / gameLayout.cellH); return col >= 0 && col < gameLayout.cols && row >= 0 && row < gameLayout.rows ? { row, col } : null; }
function plantAt(event) {
  if (!game.running) return false;
  const point = canvasPoint(event);
  const cell = gameCellAt(point.x, point.y);
  if (!cell) return false;
  const existing = game.plants.find((plant) => plant.row === cell.row && plant.col === cell.col);
  if (game.shovel) {
    if (!existing) return false;
    const position = cellPosition(existing.row, existing.col);
    game.plants.splice(game.plants.indexOf(existing), 1);
    game.shovel = false;
    updateShovelButton();
    addGameParticle(position.x, position.y, "#e7d7a0", 12, .14);
    playGameSound("hit");
    drawGame();
    return true;
  }
  if (!game.selected || existing) return false;
  const type = game.selected;
  const cost = plantCost[type];
  if (game.sun < cost) { setGameStatus("game.noSun"); return false; }
  game.sun -= cost;
  game.plants.push({ type, hp: plantHealth[type], row: cell.row, col: cell.col, seed: Math.random() * 1000, age: 0, sunTimer: 0, shotTimer: 0, bombTimer: 0 });
  const position = cellPosition(cell.row, cell.col);
  updateGameHud();
  clearPlantSelection();
  addGameParticle(position.x, position.y, plantColor[type] || "#fff", 12, .12);
  playGameSound("plant");
  drawGame();
  return true;
}
function bindUI() {
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
  $("#gameClose").addEventListener("click", closeGame);
  $("#gameStart").addEventListener("click", startGame);
  $("#gameShovel").addEventListener("click", toggleShovel);
  $("#gamePause").addEventListener("click", toggleGamePause);
  $("#gameDifficulty").addEventListener("change", (event) => setGameDifficulty(event.target.value));
  $("#gameAutoSun").addEventListener("change", (event) => {
    game.autoSun = event.target.checked;
    localStorage.setItem("minicc-game-auto-sun", game.autoSun ? "on" : "off");
  });
  $("#gameSoundToggle").addEventListener("click", toggleGameSound);
  $("#gameVolume").addEventListener("input", (event) => setGameVolume(event.target.value));
  document.addEventListener("visibilitychange", () => setGamePaused(document.hidden));
  $("#gameModal").addEventListener("click", (event) => { if (event.target.id === "gameModal") closeGame(); });
  $("#gameCanvas").addEventListener("click", (event) => {
    if (collectSun(event)) return;
    plantAt(event);
  });
  $$(".seed-card").forEach((card) => card.addEventListener("click", () => selectPlant(card)));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if ($("#gameModal").classList.contains("show") && (game.selected || game.shovel)) { clearPlantSelection(); game.shovel = false; updateShovelButton(); }
      else { closeGame(); closePanel(); }
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") { event.preventDefault(); resetTask(); }
    if (event.key === "/" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "INPUT") { event.preventDefault(); $("#threadSearch").focus(); }
  });
  $("#allowChanges").addEventListener("change", (event) => {
    state.allowChanges = event.target.checked;
    localStorage.setItem("minicc-allow", String(state.allowChanges));
    updateMode();
    showToast(state.allowChanges ? (state.locale === "zh" ? "已允许当前任务修改" : "Changes enabled for new requests") : (state.locale === "zh" ? "已启用安全模式" : "Safe mode enabled"));
  });
  $("#allowNetwork").addEventListener("change", (event) => {
    state.allowNetwork = event.target.checked;
    localStorage.setItem("minicc-network", String(state.allowNetwork));
    showToast(state.allowNetwork ? (state.locale === "zh" ? "已允许当前任务联网搜索" : "Web search enabled for new requests") : (state.locale === "zh" ? "已关闭联网搜索" : "Web search disabled"));
  });
  $("#localeZh").addEventListener("click", () => setLocale("zh"));
  $("#localeEn").addEventListener("click", () => setLocale("en"));
  $("#themeButton").addEventListener("click", () => setTheme(state.theme === "light" ? "dark" : "light"));
  $("#focusToggle").addEventListener("click", () => setFocusMode(!state.focusMode));
  $("#moreOptionsButton").addEventListener("click", openOptionsPanel);
  $("#reasoningButton").addEventListener("click", openSettingsPanel);
  $("#moreTasksButton").addEventListener("click", openTaskListPanel);
  $("#taskDockOpen").addEventListener("click", openActivityPanel);
  $("#batchButton").addEventListener("click", openBatchPanel);
  $("#attachButton").addEventListener("click", () => $("#imageInput").click());
  $("#imageInput").addEventListener("change", (event) => { addImageFiles(event.target.files); });
  $("#attachmentTray").addEventListener("click", (event) => {
    const target = event.target.closest("[data-remove-attachment]");
    if (!target) return;
    state.attachments = state.attachments.filter((item) => item.id !== target.dataset.removeAttachment);
    renderAttachmentTray();
  });
  $("#composerShell").addEventListener("dragover", (event) => { if ([...(event.dataTransfer?.items || [])].some((item) => item.kind === "file")) { event.preventDefault(); $("#composerShell").classList.add("drag-active"); } });
  $("#composerShell").addEventListener("dragleave", () => $("#composerShell").classList.remove("drag-active"));
  $("#composerShell").addEventListener("drop", (event) => { event.preventDefault(); $("#composerShell").classList.remove("drag-active"); addImageFiles(event.dataTransfer?.files); });
  $("#promptInput").addEventListener("paste", (event) => { const images = [...(event.clipboardData?.files || [])].filter((file) => String(file.type || "").startsWith("image/")); if (images.length) { event.preventDefault(); addImageFiles(images); } });
  $("#profileButton").addEventListener("click", openSettingsPanel);
  $("#panelClose").addEventListener("click", closePanel);
  $("#panelExpand").addEventListener("click", togglePanelFullscreen);
  $("#panelModal").addEventListener("click", (event) => { if (event.target.id === "panelModal") closePanel(); });
  $("#refreshFiles").addEventListener("click", () => { loadWorkspace(); showToast(state.locale === "zh" ? "工作区状态已刷新" : "Workspace refreshed"); });
  $$(".inspector-tab").forEach((button) => button.addEventListener("click", () => switchInspectorTab(button.dataset.inspectorTab)));
  $("#fileList").addEventListener("click", (event) => {
    const target = event.target.closest("[data-open-diff]");
    if (target) openFilePreview(target.dataset.openDiff);
  });
  $("#changeList").addEventListener("click", (event) => {
    const target = event.target.closest("[data-open-diff]");
    if (target) openFilePreview(target.dataset.openDiff);
  });
  $("#messageList").addEventListener("click", (event) => {
    const target = event.target.closest("[data-open-diff]");
    if (target) openFilePreview(target.dataset.openDiff);
  });
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => {
    const view = button.dataset.view;
    $$(".nav-item").forEach((item) => item.classList.toggle("active", item === button));
    if (view === "tasks") openActivityPanel();
    else if (view === "workspaces") openWorkspacesPanel();
    else if (view === "promo") openPromoPanel();
    else if (view === "activity") openActivityPanel();
    else if (view === "arcade") openGame();
    else closePanel();
  }));
  $$(".action-chip").forEach((button) => button.addEventListener("click", () => {
    const promptKey = state.locale === "zh" ? "promptZh" : "promptEn";
    $("#promptInput").value = button.dataset[promptKey] || button.dataset.prompt || "";
    $("#promptInput").focus();
  }));
  $("#sidebarOpen").addEventListener("click", () => { $("#sidebar").classList.add("open"); $("#mobileScrim").classList.add("show"); });
  $("#sidebarClose").addEventListener("click", () => { $("#sidebar").classList.remove("open"); $("#mobileScrim").classList.remove("show"); });
  $("#mobileScrim").addEventListener("click", () => { $("#sidebar").classList.remove("open"); $("#mobileScrim").classList.remove("show"); });
  $("#inspectorToggle").addEventListener("click", () => $("#inspector").classList.toggle("open"));
  $("#inspectorClose").addEventListener("click", () => $("#inspector").classList.remove("open"));
  $("#panelBody").addEventListener("change", (event) => {
    if (event.target.id !== "reasoningEffortSelect") return;
    const value = event.target.value;
    if (!["low", "mid", "high", "xhigh", "max"].includes(value)) return;
    state.reasoningEffort = value;
    localStorage.setItem("minicc-reasoning", value);
    updateReasoningControl();
    showToast(state.locale === "zh" ? "新的任务将使用 " + t("reasoning." + value) + " 推理预算" : "New tasks will use " + t("reasoning." + value) + " reasoning");
  });
  $("#panelBody").addEventListener("click", async (event) => {
    const target = event.target.closest("[data-cancel-task], [data-resume-task], [data-open-task], [data-open-detail], [data-select-workspace], [data-remove-worktree], [data-set-locale], [data-switch-session], [data-panel-action]");
    if (!target) return;
    if (target.dataset.openDetail) { openTaskDetail(target.dataset.openDetail); return; }
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
      } catch (error) { showToast(error.message); }
      finally { if (!taskBySession.has(taskSessionKey(state.sessionId))) state.activeTaskId = null; setBusy(false); }
      return;
    }
    if (target.dataset.openTask) { openTaskInWorkspace(target.dataset.openTask); return; }
    if (target.dataset.selectWorkspace) {
      try {
        showToast(t("workspace.switching"));
        await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: target.dataset.selectWorkspace }) });
        await loadWorkspace();
        closePanel();
        showToast(state.locale === "zh" ? "工作区已切换" : "Workspace switched");
      } catch (error) { showToast(error.message); }
      return;
    }
    if (target.dataset.cancelTask) {
      try { await requestJson(`/api/tasks/${encodeURIComponent(target.dataset.cancelTask)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); openActivityPanel(); }
      catch (error) { showToast(error.message); }
      return;
    }
    if (target.dataset.removeWorktree) {
      try { await requestJson("/api/worktrees/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: target.dataset.removeWorktree }) }); openWorkspacesPanel(); }
      catch (error) { showToast(error.message); }
      return;
    }
    if (target.dataset.setLocale) { setLocale(target.dataset.setLocale); openSettingsPanel(); return; }
    if (target.dataset.switchSession) { setSession(target.dataset.switchSession); closePanel(); return; }
    if (target.dataset.panelAction === "activity") { openActivityPanel(); return; }
    if (target.dataset.panelAction === "new-task") { closePanel(); resetTask(); return; }
    if (target.dataset.panelAction === "clear") { sessionMarkup.delete(state.sessionId); localStorage.removeItem(sessionViewKey(state.sessionId)); renderSession(state.sessionId); closePanel(); showToast(state.locale === "zh" ? "当前视图已清空" : "Current view cleared"); return; }
    if (target.dataset.panelAction === "export") { exportChat(); closePanel(); return; }
    if (target.dataset.panelAction === "reload") { loadWorkspace(); closePanel(); return; }
  });
  $("#panelBody").addEventListener("submit", async (event) => {
    if (event.target.id === "batchForm") {
      event.preventDefault();
      const form = event.target;
      const messages = [...form.querySelectorAll("textarea[name=task]")].map((field) => field.value.trim()).filter(Boolean);
      if (messages.length < 2) { showToast(state.locale === "zh" ? "至少填写 2 个子任务" : "Add at least 2 subtasks"); return; }
      try {
        const sharedContext = String(form.elements.namedItem("shared_context")?.value || "").trim();
        const created = await requestJson("/api/tasks/batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages, shared_context: sharedContext, message: state.locale === "zh" ? "并行执行多个独立子任务" : "Run independent subtasks in parallel", session_id: state.sessionId, allow_changes: state.allowChanges, allow_network: state.allowNetwork, reasoning_effort: state.reasoningEffort, workspace_path: state.workspacePath }) });
        const task = await requestJson(`/api/tasks/${encodeURIComponent(created.task_id)}`);
        closePanel();
        addUserMessage(task.message || (state.locale === "zh" ? "并行执行多个独立子任务" : "Run independent subtasks in parallel"));
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
      const form = event.target;
      const path = String(form.elements.namedItem("path")?.value || "").trim();
      try {
        showToast(t("workspace.switching"));
        await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
        await loadWorkspace();
        closePanel();
        showToast(state.locale === "zh" ? "工作区已切换" : "Workspace switched");
      } catch (error) { showToast(error.message); }
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
      await requestJson("/api/worktrees", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, branch: branch || undefined }) });
      showToast(state.locale === "zh" ? "worktree 已创建" : "Worktree created");
      openWorkspacesPanel();
    } catch (error) { showToast(error.message); }
  });
  $("#promptInput").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    sendMessage(event);
  });
  $("#threadList").addEventListener("click", (event) => {
    const item = event.target.closest(".thread-item");
    if (!item) return;
    setSession(item.dataset.session);
    if (item.dataset.taskId) openTaskInWorkspace(item.dataset.taskId);
  });
  $("#threadSearch").addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase();
    $$(".thread-item").forEach((item) => { item.hidden = !item.textContent.toLowerCase().includes(query); });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindUI();
  updateMode();
  applyFocusMode();
  initialMessageMarkup = $("#messageList").innerHTML;
  setSession(state.sessionId);
  applyLocale();
  refreshIcons();
  loadWorkspace();
  // Keep tasks created in another session or browser tab visible in the sidebar.
  window.setInterval(() => { if (!document.hidden) loadTaskHistory(); }, 5000);
  window.addEventListener("beforeunload", persistSessionView);
});
