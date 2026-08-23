const state = {
  sessionId: localStorage.getItem("minicc-session") || "interview-1",
  allowChanges: localStorage.getItem("minicc-allow") !== "false",
  locale: localStorage.getItem("minicc-locale") || "zh",
  workspacePath: "",
  workspaceInfo: null,
  contextWindowTokens: 300000,
  reasoningEffort: ["standard", "high", "max"].includes(localStorage.getItem("minicc-reasoning")) ? localStorage.getItem("minicc-reasoning") : "high",
  busy: false,
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
    "inspector.toggle": "切换检查器", "inspector.close": "关闭检查器", "options.open": "更多选项", "composer.inputLabel": "输入任务",
    "composer.allowChanges": "允许当前任务修改文件或执行命令", "cancel.title": "取消任务", "send.title": "发送任务", "files.refresh": "刷新文件",
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
    "tool.ok": "完成", "tool.error": "失败", "tool.denied": "已阻止", "tool.searchResults": "搜索来源", "tool.openSource": "打开来源", "tool.round": "工具轮次", "tool.callCount": "次调用", "tool.reasoning": "阶段摘要",
    "workspace.current": "当前工作区", "workspace.path": "文件夹路径", "workspace.open": "打开文件夹", "workspace.recent": "最近打开", "workspace.switching": "正在切换工作区...", "workspace.selectHint": "输入本机文件夹绝对路径，例如 D:\\Projects\\demo",
    "panel.workspaces": "工作区与 Git worktree", "panel.activity": "任务活动", "panel.settings": "设置", "panel.options": "更多选项", "panel.batch": "并行子智能体",
    "panel.file": "文件预览", "panel.noTasks": "还没有后台任务", "panel.refresh": "刷新", "panel.close": "关闭", "tasks.detail": "查看详情", "tasks.openSession": "打开会话",
    "batch.title": "拆分并行任务", "batch.subtitle": "适合独立检查、资料搜集和验证；子任务完成后会自动合并结果。", "batch.task": "子任务", "batch.context": "共享上下文（可选）", "batch.run": "开始并行", "batch.note": "建议每个子任务只负责一个清晰目标。",
    "panel.createWorktree": "创建 worktree", "panel.name": "名称", "panel.branch": "分支（可选）", "panel.create": "创建",
    "panel.sandbox": "执行环境", "panel.mcp": "MCP 工具", "panel.language": "界面语言", "panel.clear": "清空当前会话",
    "panel.export": "导出当前对话", "panel.reload": "刷新工作区状态", "panel.noWorktrees": "当前没有额外 worktree",
    "panel.hostProcess": "宿主机进程", "panel.isolated": "已隔离", "panel.servers": "个服务", "panel.gitWorktrees": "Git worktree", "panel.reasoning": "推理强度", "panel.reasoningNote": "只传递预算档位；界面显示可审计阶段摘要，不展示模型私有思维链", "reasoning.standard": "标准", "reasoning.high": "高", "reasoning.max": "最高",
    "game.close": "关闭小游戏", "game.kicker": "MINICC ARCADE · MINI LAWN", "game.title": "植物大战僵尸 · 草坪保卫战",
    "game.subtitle": "收集阳光，选中卡片后点击空草格种植；再次点击卡片或按 Esc 可取消。", "game.sun": "阳光", "game.score": "击退", "game.wave": "波次",
    "game.ready": "准备就绪", "game.running": "战斗中", "game.waveClear": "本波已清场，下一波即将到来", "game.victory": "草坪守住了！", "game.noSun": "阳光不足", "game.recharging": "卡片冷却中", "game.gameOver": "僵尸进屋了", "game.peashooter": "豌豆射手",
    "game.sunflower": "向日葵", "game.wallnut": "坚果墙", "game.attack": "攻击", "game.produce": "产阳光", "game.defense": "防御",
    "game.instructions": "点击草坪种植 · 点击阳光收集", "game.start": "开始游戏", "game.restart": "重开",
    "message.you": "你", "message.now": "现在", "message.agent": "Agent", "game.canvas": "植物大战僵尸迷你游戏画布",
    "changes.agentCore": "Agent 核心", "changes.webWorkspace": "Web 工作台", "changes.specproof": "Specproof 评估", "changes.filesChanged": "修改 6 个文件", "changes.filesAdded": "新增 3 个文件", "changes.assessmentAdded": "已添加评估", "changes.now": "现在", "changes.minute": "1 分钟前", "changes.clean": "等待变更", "changes.cleanHint": "运行任务后会在这里同步", "changes.modified": "已修改", "changes.added": "已新增", "changes.deleted": "已删除", "changes.renamed": "已重命名", "changes.openDiff": "查看 diff",
  },
  en: {
    "brand.caption": "LOCAL AGENT STUDIO", "newTask.label": "New task", "newTask.title": "Create a new task",
    "search.placeholder": "Search tasks", "nav.main": "Main navigation", "nav.tasks": "Tasks", "nav.workspaces": "Workspaces", "nav.promo": "Promo", "nav.activity": "Activity", "nav.arcade": "Arcade",
    language: "Language", "tasks.more": "More tasks", "workspace.connected": "Local service connected", "profile.label": "Current mode",
    "inspector.toggle": "Toggle inspector", "inspector.close": "Close inspector", "options.open": "More options", "composer.inputLabel": "Task input",
    "composer.allowChanges": "Allow this task to modify files or run commands", "cancel.title": "Cancel task", "send.title": "Send task", "files.refresh": "Refresh files",
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
    "tool.ok": "Done", "tool.error": "Failed", "tool.denied": "Blocked", "tool.searchResults": "Search sources", "tool.openSource": "Open source", "tool.round": "Tool round", "tool.callCount": "calls", "tool.reasoning": "Stage summary",
    "workspace.current": "Current workspace", "workspace.path": "Folder path", "workspace.open": "Open folder", "workspace.recent": "Recent folders", "workspace.switching": "Switching workspace...", "workspace.selectHint": "Enter an absolute local path, for example D:\\Projects\\demo",
    "panel.workspaces": "Workspaces & Git worktrees", "panel.activity": "Task activity", "panel.settings": "Settings", "panel.options": "More options", "panel.batch": "Parallel subagents",
    "panel.file": "File preview", "panel.noTasks": "No background tasks yet", "panel.refresh": "Refresh", "panel.close": "Close", "tasks.detail": "Details", "tasks.openSession": "Open session",
    "batch.title": "Split parallel tasks", "batch.subtitle": "Use for independent inspection, research, or verification; results are merged when children finish.", "batch.task": "Subtask", "batch.context": "Shared context (optional)", "batch.run": "Start parallel run", "batch.note": "Give each subtask one clear responsibility.",
    "panel.createWorktree": "Create worktree", "panel.name": "Name", "panel.branch": "Branch (optional)", "panel.create": "Create",
    "panel.sandbox": "Execution", "panel.mcp": "MCP tools", "panel.language": "Interface language", "panel.clear": "Clear current session",
    "panel.export": "Export current chat", "panel.reload": "Refresh workspace status", "panel.noWorktrees": "No extra worktrees",
    "panel.hostProcess": "host process", "panel.isolated": "isolated", "panel.servers": "servers", "panel.gitWorktrees": "Git worktrees", "panel.reasoning": "Reasoning effort", "panel.reasoningNote": "Only the budget level is sent; the UI shows auditable stage summaries, never private chain-of-thought", "reasoning.standard": "Standard", "reasoning.high": "High", "reasoning.max": "Max",
    "game.close": "Close game", "game.kicker": "MINICC ARCADE · MINI LAWN", "game.title": "Plants vs. Zombies · Mini lawn",
    "game.subtitle": "Collect sun, select a card, then click an empty tile; click the card again or press Esc to cancel.", "game.sun": "Sun", "game.score": "Defeated", "game.wave": "Wave",
    "game.ready": "Ready", "game.running": "Battle", "game.gameOver": "A zombie reached the house", "game.peashooter": "Peashooter",
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
  return `<article class="message user-message"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>You</strong><time>now</time></div><div class="message-body"><p>${formatText(preset.user)}</p></div></article><article class="message assistant-message"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div><div class="message-body"><p>${formatText(preset.answer)}</p>${events ? `<div class="tool-timeline">${events}</div>` : ""}</div></article>`;
}

function taskHistoryMarkup(task) {
  const prompt = task.prompt || task.preview || "";
  const answer = task.answer || task.stream_text || task.error || "任务没有返回文字。";
  const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
  const attachments = attachmentMarkup(task.attachments || []);
  const batchSummary = task.task_kind === "batch" && Array.isArray(task.children)
    ? `<div class="batch-child-summary">${task.children.map((child, index) => `<div class="batch-child"><span class="task-state ${child.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(child.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(`${t("batch.task")} ${index + 1}`)}</strong><small>${escapeHtml(phaseLabel(child))}</small></div>`).join("")}</div>`
    : "";
  return `<article class="message user-message"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>${escapeHtml(t("message.you"))}</strong><time>${escapeHtml(task.created_at || t("message.now"))}</time></div><div class="message-body"><p>${formatText(prompt)}</p>${attachments}</div></article><article class="message assistant-message"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>${escapeHtml(task.finished_at || task.created_at || t("message.now"))}</time></div><div class="message-body"><div class="history-result-head"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div><p>${formatText(answer)}</p>${batchSummary}${events ? `<div class="tool-timeline">${events}</div>` : ""}</div></article>`;
}

function taskHistoryKey(task) {
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

function renderSession(sessionId) {
  const preset = SESSION_PRESETS[sessionId];
  const history = taskHistoryBySession.get(sessionId);
  const defaultTitle = state.locale === "zh" ? "新任务" : "New task";
  const defaultSubtitle = state.locale === "zh" ? "为下一次修改准备一个干净上下文。" : "A clean context for the next change.";
  $("#sessionTitle").textContent = history ? String(history.preview || history.prompt || defaultTitle).slice(0, 72) : (state.locale === "zh" ? (preset?.titleZh || preset?.title || defaultTitle) : (preset?.title || defaultTitle));
  $("#sessionSubtitle").textContent = history ? phaseLabel(history) : (state.locale === "zh" ? (preset?.subtitleZh || preset?.subtitle || defaultSubtitle) : (preset?.subtitle || defaultSubtitle));
  const markup = history ? taskHistoryMarkup(history) : (cachedSessionView(sessionId) || (sessionId === "interview-1" ? initialMessageMarkup : presetMessageMarkup(sessionId)));
  if (markup) $("#messageList").innerHTML = markup;
  updateSessionStatus(history);
  if (history) renderedHistoryKeys.set(sessionId, taskHistoryKey(history));
  else renderedHistoryKeys.delete(sessionId);
  refreshIcons();
  window.requestAnimationFrame(() => scrollChat("auto", true));
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
  for (const task of Array.isArray(tasks) ? tasks : []) {
    const sessionId = String(task.session_id || task.task_id || "web-latest");
    if (!taskHistoryBySession.has(sessionId)) taskHistoryBySession.set(sessionId, task);
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
    && renderedHistoryKeys.get(state.sessionId) !== taskHistoryKey(currentHistory)
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

function scrollChat(behavior = "auto", force = false) {
  const area = $("#chatArea");
  if (!area || (!force && state.chatFollow === false)) {
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
  $("#sendButton").disabled = sessionBusy;
  $("#cancelTaskButton").hidden = !sessionBusy;
  $("#pulseStatus").textContent = sessionBusy ? t("working") : t("ready");
  $("#pulseStatus").style.color = sessionBusy ? "var(--coral)" : "var(--mint)";
  $("#sendButton").innerHTML = sessionBusy ? icon("loader-circle") : icon("arrow-up");
  if (sessionBusy) $("#sendButton").firstElementChild.classList.add("spin");
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
  if (sessionViewReady && state.sessionId !== sessionId) {
    persistSessionView();
  }
  state.sessionId = sessionId;
  localStorage.setItem("minicc-session", sessionId);
  $("#topSession").textContent = sessionId;
  $$(".thread-item").forEach((item) => item.classList.toggle("active", item.dataset.session === sessionId));
  renderSession(sessionId);
  sessionViewReady = true;
}

function taskSessionKey(sessionId, workspacePath = state.workspacePath) {
  return `${workspacePath || "default"}::${sessionId}`;
}

function isSessionBusy(sessionId) {
  return taskBySession.has(taskSessionKey(sessionId));
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
  const taskId = taskBySession.get(taskSessionKey(sessionId));
  if (!taskId) {
    setBusy(false);
    return;
  }
  const binding = runningTasks.get(taskId);
  if (!binding) {
    taskBySession.delete(taskSessionKey(sessionId));
    setBusy(false);
    return;
  }
  if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, binding.data);
  state.activeTaskId = taskId;
  updateLiveTask(binding.loadingId, binding.data);
  setBusy(true);
}

function updateMode() {
  const checkbox = $("#allowChanges");
  checkbox.checked = state.allowChanges;
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

function addLoadingMessage(id = `loading-${Date.now()}`, data = { status: "running", phase: "planning", stream_text: "" }) {
  $("#messageList").insertAdjacentHTML("beforeend", `
    <article class="message assistant-message loading" id="${id}">
      <div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span></div>
      <div class="message-body">${liveTaskMarkup(data)}</div>
    </article>`);
  scrollChat("auto", true);
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
  return ["queued", "planning", "tool", "answering", "merging", "completed", "failed", "cancelled", "interrupted"].includes(value) ? value : "planning";
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
  const mascotLabel = state.locale === "zh" ? "Agent 正在工作" : "Agent working";
  const preview = streamText
    ? `${formatText(streamText)}<span class="stream-caret" aria-hidden="true"></span>`
    : `<span class="stream-empty">${escapeHtml(t("phase.waiting"))}</span>`;
  return `<div class="live-task live-task-${currentPhase}" data-live-task data-phase="${currentPhase}">
    <div class="live-task-stage">
      <div class="agent-mascot" role="img" aria-label="${escapeHtml(mascotLabel)}">
        <span class="mascot-shadow" aria-hidden="true"></span>
        <span class="mascot-figure" aria-hidden="true">
          <span class="mascot-antenna"></span><span class="mascot-head"></span><span class="mascot-body"></span>
          <span class="mascot-arm mascot-arm-left"></span><span class="mascot-arm mascot-arm-right"></span>
          <span class="mascot-leg mascot-leg-left"></span><span class="mascot-leg mascot-leg-right"></span>
        </span>
      </div>
      <div class="task-progress" data-phase="${currentPhase}" role="status">
        <span class="phase-indicator" aria-hidden="true"><span></span><span></span><span></span></span>
        <span class="phase-label" data-live-phase>${escapeHtml(phaseLabel(data))}</span>
        <span class="phase-line" aria-hidden="true"></span>
      </div>
    </div>
    <div class="stream-panel">
      <div class="stream-panel-head"><span class="stream-live-dot" aria-hidden="true"></span><span>${escapeHtml(t("stream.live"))}</span><span class="stream-metrics" data-live-metrics>${escapeHtml(taskMetrics(data))}</span><span class="stream-phase" data-live-phase-label>${escapeHtml(phaseLabel(data))}</span><span class="stream-duration" data-live-duration>${escapeHtml(formatDuration(taskDuration(data)))}</span></div>
      <div class="stream-preview" data-live-preview aria-live="polite">${preview}</div>
    </div>
  </div>`;
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
        reasoning_configured: "推理预算",
        image_attached: "视觉输入",
        model_decision: "模型决策",
        tool_round_started: "执行计划",
        tool_round_finished: "结果汇总",
        replan: "重新规划",
        stagnation_replan: "停滞纠偏",
        verification_required: "验证门禁",
        verification_observed: "验证证据",
        context_compacted: "上下文压缩",
        provider_retry: "传输重试",
        reasoning_fallback: "参数降级",
        search_circuit_open: "搜索熔断",
        provider_stream_error: "模型流错误",
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
        reasoning_configured: "Reasoning budget",
        image_attached: "Vision input",
        model_decision: "Model decision",
        tool_round_started: "Execution plan",
        tool_round_finished: "Results merged",
        replan: "Re-plan",
        stagnation_replan: "Stagnation recovery",
        verification_required: "Verification gate",
        verification_observed: "Verification evidence",
        context_compacted: "Context compaction",
        provider_retry: "Transport retry",
        reasoning_fallback: "Parameter fallback",
        search_circuit_open: "Search circuit breaker",
        provider_stream_error: "Provider stream error",
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

function traceDetail(event) {
  const detail = event?.detail;
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => String(item)).join(", ");
  if (typeof detail !== "object") return String(detail);
  const parts = [];
  const labels = state.locale === "zh"
    ? { turn: "轮次", tool_count: "工具数", tools: "工具", answer_chars: "回答字符", duration_ms: "耗时", count: "数量", names: "名称", statuses: "状态", max_turns: "轮次上限", child_count: "子任务数", child: "子任务", failed: "失败数", retry: "重试", retry_limit: "重试上限", partial_chars: "已输出字符", error_type: "错误类型", requested: "请求", active: "实际", wire_value: "请求值", task_id: "任务", tokens: "tokens", automatic: "自动", complexity_score: "复杂度", complexity_threshold: "触发线", complexity_reasons: "触发原因" }
    : { turn: "turn", tool_count: "tools", tools: "tools", answer_chars: "answer chars", duration_ms: "duration", count: "count", names: "names", statuses: "statuses", max_turns: "turn limit", child_count: "children", child: "child", failed: "failed", retry: "retry", retry_limit: "retry limit", partial_chars: "partial chars", error_type: "error type", requested: "requested", active: "active", wire_value: "wire", task_id: "task", tokens: "tokens", automatic: "automatic", complexity_score: "complexity", complexity_threshold: "threshold", complexity_reasons: "reasons" };
  for (const key of ["turn", "tool_count", "tools", "answer_chars", "duration_ms", "count", "names", "statuses", "max_turns", "child_count", "child", "failed", "retry", "retry_limit", "partial_chars", "error_type", "requested", "active", "wire_value", "task_id", "tokens", "automatic", "complexity_score", "complexity_threshold", "complexity_reasons"]) {
    if (detail[key] == null) continue;
    const value = Array.isArray(detail[key]) ? detail[key].join(", ") : String(detail[key]);
    parts.push(`${labels[key] || key}: ${value}`);
  }
  return parts.join(" · ");
}

function toolEventHtml(event, animate = false) {
  const name = String(event.name || "tool");
  const status = String(event.status || "ok");
  if (event.kind === "trace") {
    const traceClass = status === "error" ? "trace-error" : "trace-ok";
    const detail = traceDetail(event);
    const tracePhase = event.code === "run_finished" ? "completed" : event.phase;
    return `<div class="trace-event ${traceClass}${animate ? " event-enter" : ""}"><span class="trace-icon">${icon(status === "error" ? "alert-triangle" : "sparkles")}</span><div class="trace-main"><div class="trace-summary"><span class="trace-code">${escapeHtml(traceLabel(event))}</span><span>${escapeHtml(event.summary || "")}</span></div>${detail ? `<small class="trace-detail">${escapeHtml(detail)}</small>` : ""}</div><span class="trace-phase">${escapeHtml(phaseLabel({ phase: tracePhase }))}</span></div>`;
  }
  const denied = status === "denied";
  const failed = ["error", "failed"].includes(status);
  const lowerName = name.toLowerCase();
  const iconName = denied ? "lock" : failed ? "alert-circle" : name === "web_search" ? "globe-2" : lowerName.includes("test") || name === "bash" ? "test-tube-2" : lowerName.includes("git") ? "git-branch" : "file-search-2";
  const stateClass = denied ? "denied" : failed ? "failed" : "completed";
  const stateIcon = denied ? "lock" : failed ? "alert-circle" : "check";
  const results = name === "web_search" && Array.isArray(event.data?.results) ? event.data.results : [];
  const resultMarkup = results.length ? `<div class="web-results"><div class="web-results-heading">${icon("globe-2")}<span>${escapeHtml(t("tool.searchResults"))}</span></div>${results.map((result) => {
    const href = safeExternalUrl(result.url);
    return href ? `<a class="web-result" href="${escapeHtml(href)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(result.title || result.url)}</strong><small>${escapeHtml(result.snippet || result.url)}</small><span>${escapeHtml(t("tool.openSource"))} ↗</span></a>` : "";
  }).join("")}</div>` : "";
  const path = String(event.path || "");
  const pathMarkup = path ? `<button class="tool-path-button" data-open-diff="${escapeHtml(path)}" type="button">${escapeHtml(path)}</button>` : `<span class="tool-path">${escapeHtml(toolStatusLabel(status))}</span>`;
  return `<div class="tool-event ${stateClass}${animate ? " event-enter" : ""}">
    <div class="tool-icon ${denied ? "amber-icon" : ""}">${icon(iconName)}</div>
    <div class="tool-event-copy"><div><strong>${escapeHtml(name)}</strong>${pathMarkup}</div><small>${escapeHtml(event.summary || "")}</small>${resultMarkup}</div>
    <span class="tool-check ${denied ? "denied-check" : failed ? "failed-check" : ""}">${icon(stateIcon)}</span>
  </div>`;
}

 function eventTimelineMarkup(events, options = {}) {
   if (!Array.isArray(events) || !events.length) return "";
   const groups = [];
   let current = null;
   const isStart = (event) => event?.kind === "trace" && event.code === "tool_round_started";
   const isEnd = (event) => event?.kind === "trace" && event.code === "tool_round_finished";
   const isTool = (event) => event?.kind === "tool" || (event?.name && event?.kind !== "trace");
   const pushCurrent = () => { if (current) { groups.push(current); current = null; } };
   events.forEach((event, index) => {
     if (isStart(event)) { pushCurrent(); current = { round: true, items: [] }; }
     else if (current?.implicit && !isTool(event) && !isEnd(event)) pushCurrent();
     if (!current && isTool(event)) current = { round: true, implicit: true, items: [] };
     if (current) {
       current.items.push({ event, index });
       if (isEnd(event)) pushCurrent();
     } else groups.push({ round: false, items: [{ event, index }] });
  });
  pushCurrent();
  const roundTotal = groups.filter((group) => group.round).length;
  let roundIndex = 0;
   return groups.map((group) => {
     if (!group.round) return group.items.map(({ event, index }) => toolEventHtml(event, index >= Number(options.animateFrom ?? events.length))).join("");
     const currentRound = roundIndex++;
     const toolCount = group.items.filter(({ event }) => event.kind === "tool" || (event.name && event.kind !== "trace")).length;
     const start = group.items.find(({ event }) => isStart(event));
     const title = start?.event?.summary || t("tool.reasoning");
     const openRounds = options.openRounds;
     const open = openRounds instanceof Set ? openRounds.has(String(currentRound)) : currentRound === roundTotal - 1;
     const itemMarkup = group.items.map(({ event, index }) => toolEventHtml(event, index >= Number(options.animateFrom ?? events.length))).join("");
     return "<details class=\"tool-round\" data-tool-round=\"" + currentRound + "\"" + (open ? " open" : "") + "><summary class=\"tool-round-summary\"><span class=\"tool-round-title\"><span class=\"tool-round-icon\">" + icon("layers-3") + "</span><strong>" + escapeHtml(t("tool.round")) + " " + (currentRound + 1) + "</strong><small>" + escapeHtml(title) + "</small></span><span class=\"tool-round-meta\">" + toolCount + " " + escapeHtml(t("tool.callCount")) + "<span class=\"tool-round-chevron\">" + icon("chevron-down") + "</span></span></summary><div class=\"tool-round-events\">" + itemMarkup + "</div></details>";
   }).join("");
 }

 function assistantMessageMarkup(data) {
   const events = Array.isArray(data.events) ? data.events : [];
   const eventMarkup = eventTimelineMarkup(events);
  const answer = data.answer || data.stream_text || data.error || "模型没有返回文字。";
  return `
    <article class="message assistant-message">
      <div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div>
      <div class="message-body"><p>${formatText(answer)}</p>${eventMarkup ? `<div class="tool-timeline">${eventMarkup}</div>` : ""}</div>
    </article>`;
}

function addAssistantMessage(data) {
  $("#messageList").insertAdjacentHTML("beforeend", assistantMessageMarkup(data));
  state.turns += Number(data.turns || 0);
  state.tools += Number(data.tool_calls_total || 0);
  $("#turnMetric").textContent = state.turns;
  $("#toolMetric").textContent = state.tools;
  updateTaskDock(data);
  refreshIcons();
  persistSessionView();
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
    stream = { rendered: "", target: "", preview, frame: 0 };
    liveStreamStates.set(loadingId, stream);
  }
  stream.preview = preview;
  if (target.length < stream.rendered.length) stream.rendered = "";
  stream.target = target;
  if (stream.frame) return;
  const paint = () => {
    stream.frame = 0;
    if (!stream.preview?.isConnected) {
      liveStreamStates.delete(loadingId);
      return;
    }
    if (stream.rendered.length >= stream.target.length) return;
    const remaining = stream.target.length - stream.rendered.length;
    const step = Math.max(1, Math.min(12, Math.ceil(remaining / 5)));
    stream.rendered = stream.target.slice(0, stream.rendered.length + step);
    stream.preview.innerHTML = `${formatText(stream.rendered)}<span class="stream-caret" aria-hidden="true"></span>`;
    stream.frame = window.requestAnimationFrame(paint);
  };
  stream.frame = window.requestAnimationFrame(paint);
}

function syncLiveEvents(loading, events) {
  if (!events.length) return;
  let timeline = loading.querySelector(".tool-timeline");
  if (!timeline) {
    timeline = document.createElement("div");
    timeline.className = "tool-timeline";
    loading.querySelector(".message-body")?.append(timeline);
  }
  const previousCount = Number(loading.dataset.eventCount || 0);
  const openRounds = timeline.dataset.initialized === "true"
    ? new Set([...timeline.querySelectorAll("details[open]")].map((item) => item.dataset.toolRound))
    : null;
  timeline.innerHTML = eventTimelineMarkup(events, { openRounds, animateFrom: previousCount });
  timeline.dataset.initialized = "true";
  loading.dataset.eventCount = String(events.length);
  refreshIcons();
}

function updateLiveTask(loadingId, data) {
  const loading = document.getElementById(loadingId);
  if (!loading) return;
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
  if (preview) {
    if (streamText) updateLiveStream(loadingId, preview, streamText);
    else preview.innerHTML = `<span class="stream-empty">${escapeHtml(t("phase.waiting"))}</span>`;
  }
  syncLiveEvents(loading, events);
  updateTaskDuration(data, loadingId);
  $("#pulseStatus").textContent = phaseText;
  updateTaskDock(data);
  scrollChat("auto");
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
    if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, data);
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
    document.getElementById(binding.loadingId || loadingId)?.remove();
    addAssistantMessage(finalData);
    setBusy(false);
  } else {
    const existing = cachedSessionView(binding.sessionId, binding.workspacePath) || presetMessageMarkup(binding.sessionId);
    const holder = document.createElement("div");
    holder.innerHTML = existing;
    holder.querySelector(`#${CSS.escape(binding.loadingId || loadingId)}`)?.remove();
    holder.insertAdjacentHTML("beforeend", assistantMessageMarkup(finalData));
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
  const taskId = taskBySession.get(taskSessionKey(state.sessionId)) || state.activeTaskId;
  if (!taskId) return;
  try {
    await requestJson(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
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
  if ((!message && !queuedAttachments.length) || isSessionBusy(sessionId)) return;
  input.value = "";
  clearAttachments();
  addUserMessage(message, queuedAttachments);
  const loadingId = addLoadingMessage();
  setBusy(true);
  try {
    const task = await requestJson("/api/tasks", {
     method: "POST",
     headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, attachments: queuedAttachments.map(({ name, mime_type, data_url }) => ({ name, mime_type, data_url })), session_id: sessionId, allow_changes: state.allowChanges, reasoning_effort: state.reasoningEffort, workspace_path: workspacePath }),
    });
    bindRunningTask(task, loadingId, sessionId);
    if (state.sessionId === sessionId) state.activeTaskId = task.task_id;
    updateTaskDock(task);
    await loadTaskHistory();
    await watchTask(task.task_id);
    scrollChat();
  } catch (error) {
    finishLiveTask(loadingId);
    document.getElementById(loadingId)?.remove();
    if (state.sessionId === sessionId) addAssistantMessage({ error: error.message });
    showToast(error.message);
    setConnection(false, "API error");
  } finally {
    if (!taskBySession.has(taskSessionKey(sessionId, workspacePath))) state.activeTaskId = null;
    if (state.sessionId === sessionId) setBusy(false);
    input.focus();
  }
}

function resetTask() {
  const next = `task-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  state.activeTaskId = null;
  state.lastTask = null;
  taskHistoryBySession.delete(next);
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
        ["planning", "收到任务：检查一个小功能并给出结果。"],
        ["tool", "read_file · 读取 README.md"],
        ["tool", "grep · 搜索测试入口"],
        ["tool", "bash · 运行 pytest -q"],
        ["answering", "整理验证结果与剩余风险"],
      ]
    : [
        ["planning", "Task received: inspect a small feature and report back."],
        ["tool", "read_file · reading README.md"],
        ["tool", "grep · locating test entry points"],
        ["tool", "bash · running pytest -q"],
        ["answering", "Summarizing verification and remaining risks"],
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
        events: steps.slice(1, 4).map(([name, summary]) => ({ name, status: "ok", summary })),
        turns: 1, tool_calls_total: 3, tokens_used: { total_tokens: 420 }, context: { tokens: 420, limit_tokens: state.contextWindowTokens },
      });
      setBusy(false);
      return;
    }
    updateLiveTask(loadingId, { status: "running", phase: item[0], stream_text: item[1], events: steps.slice(1, index).map(([name, summary]) => ({ name, status: "ok", summary })) });
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
    if (!localStorage.getItem("minicc-reasoning") && ["standard", "high", "max"].includes(info.reasoning_effort)) state.reasoningEffort = info.reasoning_effort;
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
      renderedHistoryKeys.clear();
      setSession(state.sessionId);
    }
    await loadTaskHistory();
    await loadChanges();
    try {
      const taskData = await requestJson(`/api/tasks?limit=100&workspace=${encodeURIComponent(state.workspacePath)}`);
      const tasks = Array.isArray(taskData.tasks) ? taskData.tasks : [];
      const active = tasks.find((item) => ["queued", "running"].includes(item.status));
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
  const effortMarkup = ["standard", "high", "max"].map((effort) => "<option value=\"" + effort + "\" " + (state.reasoningEffort === effort ? "selected" : "") + ">" + escapeHtml(t("reasoning." + effort)) + "</option>").join("");
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
  window.scrollTo(0, 0);
}

const game = { running: false, frame: 0, score: 0, sun: 150, wave: 1, selected: null, plants: [], zombies: [], suns: [], shots: [], particles: [], last: 0, spawnTimer: 0, spawned: 0, skyTimer: 0, musicOn: localStorage.getItem("minicc-game-sound") !== "off", audio: null };
const gameLayout = { left: 78, top: 72, cellW: 70, cellH: 65, rows: 5, cols: 9 };
const plantCost = { peashooter: 100, sunflower: 50, wallnut: 50 };
const plantHealth = { peashooter: 7, sunflower: 6, wallnut: 24 };
const plantColor = { peashooter: "#62b5a0", sunflower: "#f6c453", wallnut: "#ad7556" };
function clearPlantSelection() {
  game.selected = null;
  $$(".seed-card").forEach((item) => item.classList.remove("selected"));
}
function selectPlant(card) {
  const next = card.dataset.plant;
  game.selected = game.selected === next ? null : next;
  $$(".seed-card").forEach((item) => item.classList.toggle("selected", item.dataset.plant === game.selected));
}
function updateGameHud() {
  $("#gameSun").textContent = String(game.sun);
  $("#gameScore").textContent = String(game.score);
  $("#gameWave").textContent = String(game.wave);
}
function cellPosition(row, col) { return { x: gameLayout.left + col * gameLayout.cellW + 35, y: gameLayout.top + row * gameLayout.cellH + 31 }; }
function addGameParticle(x, y, color, count = 6, speed = 0.08) {
  for (let i = 0; i < count; i += 1) game.particles.push({ x, y, vx: (Math.random() - .5) * speed, vy: (Math.random() - .7) * speed, life: 420 + Math.random() * 360, maxLife: 780, size: 2 + Math.random() * 3, color });
}
function playGameSound(kind) {
  if (!game.musicOn) return;
  try {
    if (!game.audio) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext(); const master = ctx.createGain(); master.gain.value = .045; master.connect(ctx.destination);
      game.audio = { ctx, master, musicTimer: null, step: 0 };
    }
    const { ctx, master } = game.audio;
    if (ctx.state === "suspended") ctx.resume();
    const notes = { collect: 660, plant: 330, shoot: 220, hit: 145, wave: 520, gameover: 90 };
    const oscillator = ctx.createOscillator(); const gain = ctx.createGain(); oscillator.type = kind === "hit" ? "square" : "sine"; oscillator.frequency.value = notes[kind] || 280;
    gain.gain.setValueAtTime(kind === "shoot" ? .08 : .16, ctx.currentTime); gain.gain.exponentialRampToValueAtTime(.001, ctx.currentTime + (kind === "gameover" ? .42 : .16)); oscillator.connect(gain); gain.connect(master); oscillator.start(); oscillator.stop(ctx.currentTime + .45);
  } catch { /* Audio is an enhancement, not a gameplay dependency. */ }
}
function startGameMusic() {
  if (!game.musicOn || game.audio?.musicTimer) return;
  playGameSound("plant");
  if (!game.audio) return;
  const melody = [262, 330, 392, 330, 294, 349, 440, 349];
  game.audio.musicTimer = window.setInterval(() => {
    if (!game.running || !game.musicOn || !game.audio) return;
    const { ctx, master } = game.audio; const oscillator = ctx.createOscillator(); const gain = ctx.createGain();
    oscillator.type = "triangle"; oscillator.frequency.value = melody[game.audio.step++ % melody.length]; gain.gain.setValueAtTime(.045, ctx.currentTime); gain.gain.exponentialRampToValueAtTime(.001, ctx.currentTime + .3); oscillator.connect(gain); gain.connect(master); oscillator.start(); oscillator.stop(ctx.currentTime + .34);
  }, 620);
}
function stopGameMusic() { if (game.audio?.musicTimer) { clearInterval(game.audio.musicTimer); game.audio.musicTimer = null; } }
function updateSoundButton() { const button = $("#gameSoundToggle"); if (button) { button.textContent = game.musicOn ? "♫ 音效开" : "♫ 音效关"; button.classList.toggle("muted", !game.musicOn); } }
function toggleGameSound() { game.musicOn = !game.musicOn; localStorage.setItem("minicc-game-sound", game.musicOn ? "on" : "off"); if (game.musicOn) { playGameSound("collect"); startGameMusic(); } else stopGameMusic(); updateSoundButton(); }
function initGame() { stopGameMusic(); game.running = false; game.score = 0; game.sun = 150; game.wave = 1; game.spawned = 0; game.plants = []; game.zombies = []; game.suns = []; game.shots = []; game.particles = []; game.last = 0; game.spawnTimer = 0; game.skyTimer = 0; clearPlantSelection(); updateSoundButton(); updateGameHud(); $("#gameStatus").textContent = t("game.ready"); $("#gameStart").textContent = t("game.start"); drawGame(); }
function roundedRect(ctx, x, y, width, height, radius) { ctx.beginPath(); ctx.roundRect(x, y, width, height, radius); }
function drawSun(ctx, sun) { const pulse = 1 + Math.sin(sun.age / 230) * .08; ctx.save(); ctx.translate(sun.x, sun.y); ctx.scale(pulse, pulse); ctx.shadowColor = "rgba(255, 215, 84, .75)"; ctx.shadowBlur = 18; ctx.fillStyle = "#ffd75b"; ctx.beginPath(); ctx.arc(0, 0, 15, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = "#fff3a5"; ctx.lineWidth = 3; for (let i = 0; i < 8; i += 1) { const angle = i * Math.PI / 4; ctx.beginPath(); ctx.moveTo(Math.cos(angle) * 19, Math.sin(angle) * 19); ctx.lineTo(Math.cos(angle) * 25, Math.sin(angle) * 25); ctx.stroke(); } ctx.fillStyle = "#fff4a8"; ctx.beginPath(); ctx.arc(-4, -4, 4, 0, Math.PI * 2); ctx.fill(); ctx.restore(); }
function drawPlant(ctx, plant, now) { const bob = Math.sin((now + plant.seed) / 480) * 2; const { x, y } = cellPosition(plant.row, plant.col); ctx.save(); ctx.translate(x, y + bob); ctx.fillStyle = "rgba(22, 59, 42, .24)"; ctx.beginPath(); ctx.ellipse(0, 25, 23, 7, 0, 0, Math.PI * 2); ctx.fill();
  if (plant.type === "sunflower") { for (let i = 0; i < 10; i += 1) { const angle = i * Math.PI / 5; ctx.fillStyle = i % 2 ? "#f4b83f" : "#ffd765"; ctx.beginPath(); ctx.ellipse(Math.cos(angle) * 14, Math.sin(angle) * 14 - 5, 7, 13, angle, 0, Math.PI * 2); ctx.fill(); } ctx.fillStyle = "#75482d"; ctx.beginPath(); ctx.arc(0, -5, 10, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#9c6a35"; ctx.beginPath(); ctx.arc(-3, -8, 2, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#438553"; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(0, 7); ctx.lineTo(0, 22); ctx.stroke(); }
  else if (plant.type === "wallnut") { ctx.fillStyle = "#b87b55"; ctx.strokeStyle = "#6d432f"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(0, 0, 19, 24, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.fillStyle = "#3f2f27"; ctx.beginPath(); ctx.arc(-7, -5, 2.5, 0, Math.PI * 2); ctx.arc(7, -5, 2.5, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#6d432f"; ctx.beginPath(); ctx.arc(0, 5, 8, 0, Math.PI); ctx.stroke(); }
  else { ctx.strokeStyle = "#438553"; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(0, 19); ctx.lineTo(0, -3); ctx.stroke(); ctx.fillStyle = "#63b98d"; ctx.beginPath(); ctx.ellipse(-12, 12, 13, 6, -.45, 0, Math.PI * 2); ctx.ellipse(11, 14, 13, 6, .45, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#74c9a5"; ctx.beginPath(); ctx.arc(0, -14, 14, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#244a3d"; ctx.beginPath(); ctx.arc(9, -14, 8, -.4, .4); ctx.fill(); ctx.fillStyle = "#d7f4d0"; ctx.beginPath(); ctx.arc(12, -14, 3, 0, Math.PI * 2); ctx.fill(); }
  if (plant.hp < plantHealth[plant.type]) { ctx.fillStyle = "rgba(25, 33, 26, .7)"; ctx.fillRect(-18, 29, 36, 4); ctx.fillStyle = plant.hp / plantHealth[plant.type] > .4 ? "#80d6a2" : "#f6b35c"; ctx.fillRect(-18, 29, 36 * Math.max(0, plant.hp / plantHealth[plant.type]), 4); } ctx.restore(); }
function drawZombie(ctx, zombie, now) { const walk = Math.sin((now + zombie.seed) / 170) * 3; const y = zombie.y; ctx.save(); ctx.translate(zombie.x, y + walk); ctx.fillStyle = "rgba(26, 28, 39, .28)"; ctx.beginPath(); ctx.ellipse(0, 25, 23, 7, 0, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#262c39"; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(-7, 16); ctx.lineTo(-11 + walk, 29); ctx.moveTo(7, 16); ctx.lineTo(11 - walk, 29); ctx.stroke(); ctx.fillStyle = zombie.type === "roadblock" ? "#485267" : "#556b62"; roundedRect(ctx, -15, -1, 30, 25, 8); ctx.fill(); ctx.fillStyle = "#b8c4aa"; ctx.beginPath(); ctx.arc(0, -16, 15, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#29303d"; ctx.beginPath(); ctx.arc(-5, -17, 3, 0, Math.PI * 2); ctx.arc(6, -17, 3, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#f0a27e"; ctx.beginPath(); ctx.arc(-6, -9, 3, 0, Math.PI * 2); ctx.arc(6, -9, 3, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#29303d"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(-8, -2); ctx.lineTo(8, -2); ctx.stroke(); if (zombie.type === "roadblock") { ctx.fillStyle = "#d98258"; ctx.fillRect(-18, -30, 36, 7); ctx.fillStyle = "#f2c05e"; ctx.fillRect(-12, -34, 24, 4); } if (zombie.hp < zombie.maxHp) { ctx.fillStyle = "rgba(25, 33, 26, .7)"; ctx.fillRect(-19, 34, 38, 4); ctx.fillStyle = "#e48374"; ctx.fillRect(-19, 34, 38 * Math.max(0, zombie.hp / zombie.maxHp), 4); } ctx.restore(); }
function drawGame() { const canvas = $("#gameCanvas"); if (!canvas) return; const ctx = canvas.getContext("2d"); const now = performance.now(); const sky = ctx.createLinearGradient(0, 0, 0, 420); sky.addColorStop(0, "#9bd9df"); sky.addColorStop(.35, "#d7e7b2"); sky.addColorStop(.36, "#659b58"); sky.addColorStop(1, "#315744"); ctx.fillStyle = sky; ctx.fillRect(0, 0, 720, 420); ctx.fillStyle = "rgba(255,255,255,.18)"; ctx.beginPath(); ctx.arc(605, 42, 29, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#253b45"; ctx.fillRect(0, 0, 720, 58); ctx.fillStyle = "#eef3cf"; ctx.font = "700 12px Manrope, sans-serif"; ctx.fillText("BACKYARD", 18, 23); ctx.fillStyle = "#a8d5a1"; ctx.font = "10px DM Mono, monospace"; ctx.fillText(game.running ? "DEFEND THE LAWN" : "READY FOR BATTLE", 18, 42); ctx.fillStyle = "#d9b16e"; ctx.fillRect(48, 28, 17, 23); ctx.fillStyle = "#693f38"; ctx.beginPath(); ctx.moveTo(44, 29); ctx.lineTo(57, 16); ctx.lineTo(70, 29); ctx.fill(); ctx.fillStyle = "#f4d27a"; ctx.fillRect(53, 39, 7, 12);
  for (let row = 0; row < gameLayout.rows; row += 1) for (let col = 0; col < gameLayout.cols; col += 1) { const x = gameLayout.left + col * gameLayout.cellW, y = gameLayout.top + row * gameLayout.cellH; ctx.fillStyle = (row + col) % 2 ? "#75b866" : "#83c573"; roundedRect(ctx, x + 2, y + 2, 66, 61, 8); ctx.fill(); ctx.strokeStyle = "rgba(221, 246, 151, .18)"; ctx.stroke(); }
  ctx.fillStyle = "rgba(240, 213, 140, .28)"; ctx.fillRect(674, 60, 3, 360); game.suns.forEach((sun) => drawSun(ctx, sun)); game.plants.forEach((plant) => drawPlant(ctx, plant, now)); game.shots.forEach((shot) => { ctx.fillStyle = "#b5f0a2"; ctx.shadowColor = "#80ed9a"; ctx.shadowBlur = 12; ctx.beginPath(); ctx.arc(shot.x, shot.y, 6, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0; }); game.zombies.forEach((zombie) => drawZombie(ctx, zombie, now)); game.particles.forEach((particle) => { ctx.globalAlpha = Math.max(0, particle.life / particle.maxLife); ctx.fillStyle = particle.color; ctx.beginPath(); ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2); ctx.fill(); }); ctx.globalAlpha = 1; }
function spawnZombie() { const row = Math.floor(Math.random() * gameLayout.rows); const roadblock = game.wave >= 2 && Math.random() < .18; const hp = roadblock ? 11 + game.wave : 4 + Math.floor(game.wave * .6); game.zombies.push({ x: 704, y: cellPosition(row, 0).y, row, hp, maxHp: hp, type: roadblock ? "roadblock" : "walker", speed: roadblock ? .011 + game.wave * .0005 : .019 + game.wave * .0009, seed: Math.random() * 1000 }); game.spawned += 1; if (game.spawned % 7 === 0) { game.wave = 1 + Math.floor(game.spawned / 7); $("#gameWave").textContent = game.wave; playGameSound("wave"); addGameParticle(360, 60, "#ffe27c", 18, .18); } }
function produceSun(plant) { const position = cellPosition(plant.row, plant.col); game.suns.push({ x: position.x + (Math.random() - .5) * 24, y: position.y - 28, age: 0, targetY: position.y - 5 }); addGameParticle(position.x, position.y - 22, "#ffe17b", 8, .12); playGameSound("collect"); }
function gameLoop(now = 0) { if (!game.running) return; const dt = Math.min(40, Math.max(8, now - game.last || 16)); game.last = now; game.spawnTimer += dt; game.skyTimer += dt; if (game.spawned === 0 && game.spawnTimer > 2500) { spawnZombie(); game.spawnTimer = 0; } else if (game.spawnTimer > Math.max(1850, 4100 - game.wave * 190)) { spawnZombie(); game.spawnTimer = 0; } if (game.skyTimer > 5200 && game.suns.length < 9) { game.skyTimer = 0; game.suns.push({ x: 105 + Math.random() * 535, y: 88 + Math.random() * 270, age: 0, targetY: 80 + Math.random() * 240 }); }
  game.suns.forEach((sun) => { sun.age += dt; if (sun.y < sun.targetY) sun.y = Math.min(sun.targetY, sun.y + dt * .05); });
  game.plants.forEach((plant) => { plant.age += dt; if (plant.type === "sunflower") { plant.sunTimer += dt; if (plant.sunTimer > 4800 && game.suns.length < 12) { plant.sunTimer = 0; produceSun(plant); } } if (plant.type === "peashooter") { plant.shotTimer += dt; if (plant.shotTimer > 1050 && game.zombies.some((z) => z.row === plant.row && z.x > cellPosition(plant.row, plant.col).x)) { plant.shotTimer = 0; const position = cellPosition(plant.row, plant.col); game.shots.push({ x: position.x + 20, y: position.y - 5, row: plant.row, hit: false }); playGameSound("shoot"); } } });
  game.zombies.forEach((zombie) => { zombie.y = cellPosition(zombie.row, 0).y; const blocker = game.plants.find((plant) => plant.row === zombie.row && Math.abs(cellPosition(plant.row, plant.col).x - zombie.x) < 30); if (blocker) { blocker.hp -= dt / (zombie.type === "roadblock" ? 700 : 1050); if (blocker.hp <= 0) { const position = cellPosition(blocker.row, blocker.col); addGameParticle(position.x, position.y, "#c78363", 14, .18); game.plants.splice(game.plants.indexOf(blocker), 1); playGameSound("hit"); } } else zombie.x -= zombie.speed * dt; });
  game.shots.forEach((shot) => { shot.x += .34 * dt; const hit = game.zombies.find((zombie) => zombie.row === shot.row && zombie.x > shot.x - 12 && zombie.x < shot.x + 23); if (hit) { shot.hit = true; hit.hp -= 1; addGameParticle(shot.x, shot.y, "#b7f3a0", 5, .1); playGameSound("hit"); if (hit.hp <= 0) { const index = game.zombies.indexOf(hit); if (index >= 0) game.zombies.splice(index, 1); game.score += hit.type === "roadblock" ? 3 : 1; updateGameHud(); addGameParticle(hit.x, hit.y, "#f6d681", 18, .2); } } }); game.shots = game.shots.filter((shot) => !shot.hit && shot.x < 735);
  game.particles.forEach((particle) => { particle.x += particle.vx * dt; particle.y += particle.vy * dt; particle.vy += .00025 * dt; particle.life -= dt; }); game.particles = game.particles.filter((particle) => particle.life > 0); if (game.zombies.some((zombie) => zombie.x < 61)) { game.running = false; stopGameMusic(); $("#gameStatus").textContent = t("game.gameOver"); playGameSound("gameover"); addGameParticle(55, 180, "#ff9f83", 24, .22); } drawGame(); if (game.running) game.frame = requestAnimationFrame(gameLoop); }
function startGame() { cancelAnimationFrame(game.frame); initGame(); game.running = true; $("#gameStatus").textContent = t("game.running"); $("#gameStart").textContent = t("game.restart"); startGameMusic(); game.frame = requestAnimationFrame(gameLoop); }
function canvasPoint(event) { const canvas = $("#gameCanvas"), rect = canvas.getBoundingClientRect(); return { x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height }; }
function collectSun(event) { const { x, y } = canvasPoint(event); const hit = game.suns.findIndex((sun) => Math.hypot(sun.x - x, sun.y - y) < 32); if (hit < 0) return false; game.suns.splice(hit, 1); game.sun += 25; updateGameHud(); addGameParticle(x, y, "#ffe17b", 12, .16); playGameSound("collect"); drawGame(); return true; }
function plantAt(event) { if (!game.running || !game.selected) return false; const { x, y } = canvasPoint(event); if (y < gameLayout.top || x < gameLayout.left) return false; const col = Math.floor((x - gameLayout.left) / gameLayout.cellW), row = Math.floor((y - gameLayout.top) / gameLayout.cellH); if (col < 0 || col >= gameLayout.cols || row < 0 || row >= gameLayout.rows || game.plants.some((plant) => plant.row === row && plant.col === col)) return false; const cost = plantCost[game.selected]; if (game.sun < cost) return false; game.sun -= cost; game.plants.push({ type: game.selected, hp: plantHealth[game.selected], row, col, seed: Math.random() * 1000, age: 0, sunTimer: 0, shotTimer: 0 }); updateGameHud(); clearPlantSelection(); addGameParticle(cellPosition(row, col).x, cellPosition(row, col).y, plantColor[game.selected] || "#fff", 12, .12); playGameSound("plant"); drawGame(); return true; }
function bindUI() {
  $("#chatForm").addEventListener("submit", sendMessage);
  $("#chatArea").addEventListener("scroll", updateChatFollowState, { passive: true });
  $("#jumpLatestButton").addEventListener("click", () => scrollChat("auto", true));
  $("#newTaskButton").addEventListener("click", resetTask);
  $("#demoFlowButton").addEventListener("click", runDemoFlow);
  $("#cancelTaskButton").addEventListener("click", cancelActiveTask);
  $("#gameClose").addEventListener("click", closeGame);
  $("#gameStart").addEventListener("click", startGame);
  $("#gameModal").addEventListener("click", (event) => { if (event.target.id === "gameModal") closeGame(); });
  $("#gameCanvas").addEventListener("click", (event) => {
    if (collectSun(event)) return;
    plantAt(event);
  });
  $$(".seed-card").forEach((card) => card.addEventListener("click", () => selectPlant(card)));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (game.selected && $("#gameModal").classList.contains("show")) clearPlantSelection();
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
  $("#localeZh").addEventListener("click", () => setLocale("zh"));
  $("#localeEn").addEventListener("click", () => setLocale("en"));
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
    if (!["standard", "high", "max"].includes(value)) return;
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
        const created = await requestJson("/api/tasks/batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages, shared_context: sharedContext, message: state.locale === "zh" ? "并行执行多个独立子任务" : "Run independent subtasks in parallel", session_id: state.sessionId, allow_changes: state.allowChanges, reasoning_effort: state.reasoningEffort, workspace_path: state.workspacePath }) });
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
  initialMessageMarkup = $("#messageList").innerHTML;
  setSession(state.sessionId);
  applyLocale();
  refreshIcons();
  loadWorkspace();
  // Keep tasks created in another session or browser tab visible in the sidebar.
  window.setInterval(() => { if (!document.hidden) loadTaskHistory(); }, 5000);
  window.addEventListener("beforeunload", persistSessionView);
});
