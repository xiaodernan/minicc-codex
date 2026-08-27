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
  sidebarCollapsed: localStorage.getItem("minicc-sidebar-collapsed") === "true",
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
    "inspector.turns": "轮次", "inspector.tools": "工具", "inspector.tokens": "Tokens", "inspector.context": "上下文", "inspector.compactions": "自动压缩", "inspector.cache": "缓存命中", "changes.latest": "最近改动",
    "files.main": "CLI 入口", "files.loop": "工具调用循环", "files.styles": "工作台界面", "files.readme": "项目指南",
    "protected.subtitle": "每个任务单独授权写入", "panel.title": "工作台", "cancel": "取消任务", "working": "执行中", "ready": "就绪",
    "phase.queued": "排队中", "phase.planning": "正在规划", "phase.tool": "正在使用工具", "phase.answering": "正在生成回答", "phase.waiting": "等待模型输出", "phase.merging": "正在合并子任务", "phase.completed": "已完成", "phase.failed": "执行失败", "phase.cancelled": "已取消", "phase.interrupted": "服务重启时中断", "stream.live": "实时回答",
    "tasks.center": "任务中心", "tasks.open": "打开任务", "tasks.resume": "重新运行", "tasks.children": "子任务", "tasks.tokens": "tokens", "tasks.context": "上下文", "tasks.cache": "缓存", "tasks.cacheUnreported": "未统计", "tasks.cacheReported": "已返回", "tasks.compacted": "次压缩", "tasks.allWorkspaces": "所有工作区", "tasks.noHistory": "还没有任务记录", "tasks.jumpLatest": "跳到最新", "tasks.following": "跟随最新输出", "tasks.paused": "已暂停自动滚动", "tasks.runtime": "运行时指标", "tasks.repairs": "修复次数", "tasks.verifications": "验证次数", "tasks.traces": "Trace 事件", "tasks.workflow": "工作流",
    "tool.ok": "完成", "tool.error": "失败", "tool.denied": "已阻止", "tool.searchResults": "搜索来源", "tool.openSource": "打开来源", "tool.round": "工具轮次", "tool.callCount": "次调用", "tool.reasoning": "阶段摘要", "tool.result": "执行结果", "tool.observation": "观察结果", "tool.structured": "结构化证据", "tool.metadata": "执行元数据", "tool.expand": "展开详情", "tool.expandAll": "全部展开", "tool.collapseAll": "全部折叠", "tool.empty": "工具没有返回额外文本", "trace.feedback": "自反馈",
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
    "game.sunflower": "向日葵", "game.wallnut": "坚果墙", "game.attack": "攻击", "game.produce": "产阳光", "game.defense": "防御", "game.firepeashooter": "火焰射手", "game.twinpea": "双发强化", "game.kernelpult": "玉米投手", "game.pumpkin": "南瓜头", "game.spikeweed": "地刺", "game.gloomshroom": "忧郁菇", "game.butter": "黄油定身", "game.armor": "护甲", "game.polevault": "撑杆跳", "game.dancer": "舞王", "game.backup": "伴舞", "game.potatomine": "土豆雷", "game.threepeater": "三线射手", "game.jalapeno": "火爆辣椒", "game.magnetshroom": "磁力菇", "game.garlic": "大蒜", "game.squash": "窝瓜", "game.gatlingpea": "机枪射手", "game.trap": "地雷", "game.utility": "缴械", "game.redirect": "换行", "game.smash": "重击", "game.rapid": "连射", "game.cooldown": "冷却中", "game.newWindow": "新窗口", "game.wideMode": "大屏模式", "game.compactMode": "紧凑模式", "game.fullscreen": "全屏", "game.waveFinal": "终局巨人来袭：用爆发和减速守住最后防线",
    "game.instructions": "点击卡片选择 · 点击草坪种植 · 每行防线小车仅可触发一次", "game.start": "开始游戏", "game.restart": "重开", "game.mowers": "防线", "game.combo": "连击", "game.energy": "战术能量", "game.skillPulse": "寒冰脉冲", "game.skillPulseHint": "冻结并震击全场僵尸", "game.skillSun": "阳光爆发", "game.skillSunHint": "立即获得 100 阳光", "game.skillRally": "战线超载", "game.skillRallyHint": "植物攻速提升 8 秒", "game.skillReady": "可用", "game.skillCooldown": "冷却中", "game.skillNeedEnergy": "能量不足",
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
    "inspector.turns": "Turns", "inspector.tools": "Tools", "inspector.tokens": "Tokens", "inspector.context": "Context", "inspector.compactions": "Compactions", "inspector.cache": "Cache hit", "changes.latest": "Latest changes",
    "files.main": "CLI entrypoint", "files.loop": "Tool calling loop", "files.styles": "Workspace surface", "files.readme": "Project guide",
    "protected.subtitle": "Writes are gated per task", "panel.title": "Workspace", "cancel": "Cancel task", "working": "Working", "ready": "Ready",
    "phase.queued": "Queued", "phase.planning": "Planning", "phase.tool": "Running tools", "phase.answering": "Writing response", "phase.waiting": "Waiting for output", "phase.merging": "Merging subagents", "phase.completed": "Complete", "phase.failed": "Failed", "phase.cancelled": "Cancelled", "phase.interrupted": "Interrupted by restart", "stream.live": "Live response",
    "tasks.center": "Task center", "tasks.open": "Open task", "tasks.resume": "Run again", "tasks.children": "subtasks", "tasks.tokens": "tokens", "tasks.context": "context", "tasks.cache": "cache", "tasks.cacheUnreported": "unreported", "tasks.cacheReported": "reported", "tasks.compacted": "compactions", "tasks.allWorkspaces": "All workspaces", "tasks.noHistory": "No task history yet", "tasks.jumpLatest": "Jump to latest", "tasks.following": "Following latest output", "tasks.paused": "Auto-scroll paused", "tasks.runtime": "Runtime metrics", "tasks.repairs": "Repairs", "tasks.verifications": "Verifications", "tasks.traces": "Trace events", "tasks.workflow": "Workflow",
    "tool.ok": "Done", "tool.error": "Failed", "tool.denied": "Blocked", "tool.searchResults": "Search sources", "tool.openSource": "Open source", "tool.round": "Tool round", "tool.callCount": "calls", "tool.reasoning": "Stage summary", "tool.result": "Execution result", "tool.observation": "Observation", "tool.structured": "Structured evidence", "tool.metadata": "Execution metadata", "tool.expand": "Expand details", "tool.expandAll": "Expand all", "tool.collapseAll": "Collapse all", "tool.empty": "The tool returned no additional text", "trace.feedback": "Self-feedback",
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
    "game.sunflower": "Sunflower", "game.wallnut": "Wall-nut", "game.attack": "attack", "game.produce": "sun", "game.defense": "defense", "game.firepeashooter": "Fire Pea", "game.twinpea": "Twin Pea", "game.kernelpult": "Kernel-pult", "game.pumpkin": "Pumpkin", "game.spikeweed": "Spikeweed", "game.gloomshroom": "Gloom-shroom", "game.butter": "butter stun", "game.armor": "armor", "game.polevault": "Pole Vault", "game.dancer": "Dancer", "game.backup": "backup dancer", "game.potatomine": "Potato Mine", "game.threepeater": "Threepeater", "game.jalapeno": "Jalapeno", "game.magnetshroom": "Magnet-shroom", "game.garlic": "Garlic", "game.squash": "Squash", "game.gatlingpea": "Gatling Pea", "game.trap": "trap", "game.utility": "disarm", "game.redirect": "redirect", "game.smash": "smash", "game.rapid": "rapid fire", "game.cooldown": "recharging", "game.newWindow": "New window", "game.wideMode": "Wide mode", "game.compactMode": "Compact mode", "game.fullscreen": "Fullscreen", "game.waveFinal": "Final wave: use bursts and slows to hold the last line",
    "game.instructions": "Choose a card · click the lawn to plant · each lane has one safety mower", "game.start": "Start game", "game.restart": "Restart", "game.mowers": "Mowers", "game.combo": "Combo", "game.energy": "Tactical energy", "game.skillPulse": "Frost Pulse", "game.skillPulseHint": "Freeze and shock every zombie", "game.skillSun": "Sun Burst", "game.skillSunHint": "Gain 100 sun instantly", "game.skillRally": "Overdrive", "game.skillRallyHint": "Boost plant fire rate for 8 seconds", "game.skillReady": "Ready", "game.skillCooldown": "Cooling", "game.skillNeedEnergy": "Need energy",
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
  renderedTaskListKey = "";
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
const MAX_SESSION_VIEW_CHARS = 180_000;
const MAX_SEEN_EVENT_KEYS = 2048;
const MAX_RENDERED_TIMELINE_EVENTS = 240;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const liveStreamStates = new Map();
const taskEventSources = new Map();
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

const LOCAL_ICON_GLYPHS = {
  "panel-left-close": "‹", plus: "+", search: "⌕", "message-square": "□", "layout-grid": "▦",
  megaphone: "◢", history: "↶", "gamepad-2": "◇", "more-horizontal": "•••", "chevron-right": "›",
  "folder-git-2": "□", "settings-2": "⚙", "panel-left": "‹", "brain-circuit": "✦", sun: "☼",
  maximize: "↗", "panel-right": "›", "arrow-down": "↓", "list-checks": "☷", "chevrons-down": "⇵",
  "chevrons-up": "⇳", "sparkles": "✦", "alert-triangle": "!", "alert-circle": "!", check: "✓",
  lock: "□", "globe-2": "◎", "test-tube-2": "◈", "git-branch": "⑂", "file-search-2": "⌕",
  "layers-3": "▤", "chevron-down": "⌄", "image": "▧", x: "×", "scan-line": "⌁", route: "⌁",
  "scan-search": "⌕", play: "▶", paperclip: "⌇", "wand-sparkles": "✦", square: "■",
  "arrow-up": "↑", "refresh-cw": "↻", activity: "•", radio: "◉", "shield-check": "◇",
  "external-link": "↗", "layout-dashboard": "▦", "book-open": "▤", "maximize-2": "↗",
  "panel-right-close": "›", "file-code-2": "□", "rotate-ccw": "↶",
};

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
  else {
    // The workbench is local-first. Keep controls legible when an optional
    // icon package is unavailable or a browser has no network access.
    document.querySelectorAll("[data-lucide]").forEach((node) => {
      if (node.dataset.iconFallback === "true") return;
      const name = String(node.dataset.lucide || "");
      node.textContent = LOCAL_ICON_GLYPHS[name] || "•";
      node.classList.add("icon-fallback");
      node.dataset.iconFallback = "true";
      node.setAttribute("aria-hidden", "true");
    });
  }
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
  // Keep the latest messages readable while preventing localStorage from
  // becoming a second, unbounded transcript database.
  while (holder.children.length > 2 && holder.innerHTML.length > MAX_SESSION_VIEW_CHARS) {
    holder.firstElementChild?.remove();
  }
  return holder.innerHTML;
}

function persistSessionView(sessionId = state.sessionId, workspacePath = state.workspacePath) {
  const messageList = $("#messageList");
  if (!messageList) return;
  const markup = compactSessionMarkup(messageList.innerHTML);
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
    const markup = compactSessionMarkup(localStorage.getItem(cacheKey));
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
  const execution = executionTrailMarkup(events, preset.events || []);
  return `<article class="message user-message"><div class="message-meta"><span class="avatar user-avatar">Y</span><strong>You</strong><time>now</time></div><div class="message-body"><p>${formatText(preset.user)}</p></div></article><article class="message assistant-message"><div class="message-meta"><span class="avatar agent-avatar">m</span><strong>minicc</strong><span class="agent-label">Agent</span><time>now</time></div><div class="message-body">${execution}<p>${formatText(preset.answer)}</p></div></article>`;
}

function executionTrailMarkup(eventMarkup, events) {
  if (!eventMarkup) return "";
  const expandLabel = t("tool.expandAll");
  const collapseLabel = t("tool.collapseAll");
  return `<section class="execution-trail" data-agent-timeline data-agent-thread="local"><div class="execution-trail-head"><div class="execution-trail-title"><span class="execution-trail-icon">${icon("list-checks")}</span><span><strong>${escapeHtml(state.locale === "zh" ? "执行脉络与证据" : "Execution trail and evidence")}</strong><small>${escapeHtml(eventTimelineSummary(events))}</small></span></div><div class="execution-trail-actions"><button type="button" class="timeline-control" data-timeline-toggle="expand" aria-label="${escapeHtml(expandLabel)}" title="${escapeHtml(expandLabel)}">${icon("chevrons-down")}<span>${escapeHtml(expandLabel)}</span></button><button type="button" class="timeline-control" data-timeline-toggle="collapse" aria-label="${escapeHtml(collapseLabel)}" title="${escapeHtml(collapseLabel)}">${icon("chevrons-up")}<span>${escapeHtml(collapseLabel)}</span></button></div></div><div class="tool-timeline">${eventMarkup}</div></section>`;
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
    Number(task?.stream_length || 0),
    Number(task?.answer_length || 0),
    Number(task?.event_cursor || 0),
    Number(task?.state_version || 0),
    Array.isArray(task?.events) ? task.events.length : Number(task?.event_count || 0),
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
    const load = requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000)
      .then((task) => {
        cacheTaskDetail(task);
        const items = taskHistoryListBySession.get(sessionId) || [];
        const merged = items.map((item) => item.task_id === task.task_id ? task : item);
        if (!merged.some((item) => item.task_id === task.task_id)) merged.unshift(task);
        taskHistoryListBySession.set(sessionId, merged);
        taskHistoryBySession.set(sessionId, task);
        if (state.sessionId === sessionId && !isSessionBusy(sessionId)) renderSession(sessionId);
        return task;
      })
      .finally(() => taskDetailLoads.delete(taskId));
    taskDetailLoads.set(taskId, load);
  }
  return taskDetailLoads.get(taskId);
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
  const markup = history && !history.summary_only
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
  const normalizedTasks = Array.isArray(tasks)
    ? tasks.map((task) => {
        const cached = taskDetailsById.get(task?.task_id);
        return cached ? { ...cached, ...task, summary_only: false } : task;
      })
    : [];
  const nextTaskListKey = normalizedTasks.map((task) => taskHistoryKey(task)).join("|");
  taskHistoryBySession.clear();
  taskHistoryListBySession.clear();
  for (const task of normalizedTasks) {
    const sessionId = String(task.session_id || task.task_id || "web-latest");
    if (!taskHistoryBySession.has(sessionId)) taskHistoryBySession.set(sessionId, task);
    if (!taskHistoryListBySession.has(sessionId)) taskHistoryListBySession.set(sessionId, []);
    taskHistoryListBySession.get(sessionId).push(task);
  }
  const listChanged = renderedTaskListKey !== nextTaskListKey || list.dataset.historyLoaded !== "true";
  if (!normalizedTasks.length) {
    $("#taskNavCount").textContent = "0";
    if (listChanged) list.innerHTML = `<div class="thread-empty">${escapeHtml(t("tasks.noHistory"))}</div>`;
    renderedTaskListKey = nextTaskListKey;
    list.dataset.historyLoaded = "true";
    return;
  }
  const visible = normalizedTasks.slice(0, 30);
  if (listChanged) {
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
  } else {
    $$(".thread-item").forEach((item) => item.classList.toggle("active", item.dataset.session === state.sessionId));
  }
  renderedTaskListKey = nextTaskListKey;
  list.dataset.historyLoaded = "true";
  $("#taskNavCount").textContent = String(normalizedTasks.length);
  // A user-created session is intentionally allowed to have no history yet.
  // Do not replace it with the newest durable task during the 5s refresh loop.
  const currentHistory = taskHistoryBySession.get(state.sessionId);
  if (currentHistory?.summary_only && currentHistory.task_id) {
    hydrateTaskForSession(currentHistory.task_id, state.sessionId).catch(() => {});
  } else if (
    currentHistory
    && !isSessionBusy(state.sessionId)
    && renderedHistoryKeys.get(state.sessionId) !== taskHistoryKey(taskHistoryListBySession.get(state.sessionId) || currentHistory)
  ) {
    renderSession(state.sessionId);
  }
  if (listChanged) {
    refreshIcons();
    window.requestAnimationFrame(() => {
      list.scrollTop = wasAtTop ? 0 : Math.min(previousScrollTop, Math.max(0, list.scrollHeight - list.clientHeight));
    });
  }
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
  if (sessionChanged || !sessionTaskBindings(sessionId).some((binding) => binding.taskId === state.activeTaskId)) {
    const bindings = sessionTaskBindings(sessionId);
    state.activeTaskId = bindings.length
      ? bindings[bindings.length - 1].taskId
      : taskBySession.get(taskSessionKey(sessionId)) || null;
  }
  localStorage.setItem("minicc-session", sessionId);
  $("#topSession").textContent = sessionId;
  $$(".thread-item").forEach((item) => item.classList.toggle("active", item.dataset.session === sessionId));
  renderSession(sessionId, { followLatest: sessionChanged });
  sessionViewReady = true;
}

function taskSessionKey(sessionId, workspacePath = state.workspacePath) {
  const normalizedWorkspace = String(workspacePath || "default").replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase();
  return `${normalizedWorkspace}::${sessionId}`;
}

function sessionTaskBindings(sessionId, workspacePath = state.workspacePath) {
  return [...runningTasks.values()].filter((binding) => (
    binding.sessionId === sessionId
    && taskSessionKey(binding.sessionId, binding.workspacePath) === taskSessionKey(sessionId, workspacePath)
    && !isTerminalTask(binding.data)
  ));
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
  const scopedData = binding
    ? { ...data, session_id: binding.sessionId, workspace_path: binding.workspacePath }
    : data;
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
  }, 1000);
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
  const merged = new Map();
  for (const event of [...(Array.isArray(current) ? current : []), ...(Array.isArray(incoming) ? incoming : [])]) {
    if (!event || typeof event !== "object") continue;
    const key = eventIdentity(event);
    if (key) merged.set(key, { ...event });
  }
  return [...merged.values()]
    .sort((left, right) => eventSequence(left.sequence) - eventSequence(right.sequence))
    .slice(-1024);
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
    next.events = replaceEvents
      ? incoming.events.filter((event) => event && typeof event === "object").map((event) => ({ ...event }))
      : mergeTimelineEvents(previous.events, incoming.events);
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
    seenSequences: new Set(),
    seenEventIds: new Set(),
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
  state.activeTaskId = sessionId === state.sessionId ? task.task_id : state.activeTaskId;
  startTaskTimer(task.task_id);
  return binding;
}

function restoreSessionTask(sessionId) {
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
  }
  if (sessionId === state.sessionId) state.activeTaskId = bindings[bindings.length - 1].taskId;
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
  const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 300000);
  const estimated = data.tokens_used?.estimated || data.usage_by_turn?.some((item) => item.estimated);
  const tokenText = `${estimated ? "~" : ""}${compactNumber(tokens)} ${t("tasks.tokens")}`;
  return `${tokenText} · ${compactNumber(context)}/${compactNumber(limit)} ${t("tasks.context")} · ${t("tasks.cache")} ${cacheMetric(data)}`;
}

function runtimeMetricsMarkup(data) {
  const metrics = data?.metrics;
  if (!metrics || typeof metrics !== "object" || (!metrics.workflow && !metrics.verification_runs && !metrics.trace_events)) return "";
  const budget = metrics.budget && typeof metrics.budget === "object" ? metrics.budget : {};
  const duration = formatDuration(metrics.duration_seconds || 0);
  return `<div><div class="panel-section-title">${escapeHtml(t("tasks.runtime"))}</div><div class="status-grid"><div><span>${escapeHtml(t("tasks.workflow"))}</span><strong>${escapeHtml(String(metrics.workflow || "coding"))}</strong><small>${escapeHtml(String(metrics.phase || data.phase || ""))}</small></div><div><span>${escapeHtml(t("tasks.repairs"))}</span><strong>${escapeHtml(String(metrics.repair_attempts || 0))}</strong><small>${escapeHtml(duration)}</small></div><div><span>${escapeHtml(t("tasks.verifications"))}</span><strong>${escapeHtml(String(metrics.verification_runs || 0))}</strong><small>${escapeHtml(String(metrics.verification_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.cache"))}</span><strong>${escapeHtml(cacheMetric(data))}</strong><small>${escapeHtml(String(metrics.cache_status || ""))}</small></div><div><span>${escapeHtml(t("tasks.traces"))}</span><strong>${escapeHtml(String(metrics.trace_events || 0))}</strong><small>${escapeHtml(`${budget.turns || 0} turns · ${budget.tool_calls || 0} tools`)}</small></div></div></div>`;
}

function updateInspectorMetrics(data) {
  if (!data) return;
  const tokens = Number(data.tokens_used?.total_tokens || 0);
  const context = Number(data.context?.tokens || 0);
  const limit = Number(data.context?.limit_tokens || state.contextWindowTokens || 300000);
  $("#tokenMetric").textContent = compactNumber(tokens);
  $("#contextMetric").textContent = `${compactNumber(context)}/${compactNumber(limit)}`;
  $("#cacheMetric").textContent = cacheMetric(data);
  $("#compactionMetric").textContent = String(data.compaction_events?.length || 0);
  $("#contextCount").textContent = taskMetrics(data);
}

function updateTaskDock(data) {
  if (!data || !isFocusedTask(data)) return;
  if (data.task_id && !state.activeTaskId) state.activeTaskId = data.task_id;
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
        reasoning_configured: "推理强度",
        image_attached: "视觉输入",
        model_decision: "模型决策",
        model_update: "模型行动说明",
        model_update_history: "此前行动说明",
        tool_round_started: "执行计划",
        tool_round_finished: "结果汇总",
        feedback_observed: "自反馈",
        replan: "重新规划",
        stagnation_replan: "停滞纠偏",
        recovery_probe_finished: "恢复诊断",
        recovery_inspection_passed: "解除写入保护",
        recovery_required_before_finish: "恢复保护",
        recovery_guard: "恢复保护",
        task_stagnation_recovery: "错误路径修复",
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
    ? { turn: "轮次", previous_turn: "上一轮", tool_count: "工具", results: "结果", observed: "已观察", observations: "观察", constraints: "约束", failed_tools: "失败", verification_required: "需验证", recovery_inspection_required: "写入保护", assessment: "反馈", trigger: "触发", next_action: "下一步" }
    : { turn: "turn", previous_turn: "previous", tool_count: "tools", results: "results", observed: "observed", observations: "observations", constraints: "constraints", failed_tools: "failed", verification_required: "verify", recovery_inspection_required: "write guard", assessment: "assessment", trigger: "trigger", next_action: "next" };
  const parts = [];
  for (const key of ["turn", "previous_turn", "tool_count", "results", "observed", "observations", "constraints", "failed_tools", "verification_required", "recovery_inspection_required", "assessment", "trigger", "next_action"]) {
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
  const updateIndexes = visible
    .map((event, index) => event?.code === "model_update" ? index : -1)
    .filter((index) => index >= 0);
  if (updateIndexes.length <= 1) return visible;
  const latestIndex = updateIndexes[updateIndexes.length - 1];
  const firstIndex = updateIndexes[0];
  const previousUpdates = updateIndexes
    .slice(0, -1)
    .map((index) => String(visible[index]?.detail?.text || "").trim())
    .filter(Boolean);
  const historyEvent = {
    ...visible[firstIndex],
    code: "model_update_history",
    summary: state.locale === "zh"
      ? `此前行动说明 · ${previousUpdates.length} 条`
      : `Earlier action updates · ${previousUpdates.length}`,
    detail: { count: previousUpdates.length, updates: previousUpdates },
  };
  return visible.filter((_event, index) => !updateIndexes.includes(index) || index === firstIndex || index === latestIndex)
    .map((event, index, compacted) => {
      // The first retained model slot is the folded history entry; the last
      // one remains the only public action block shown at full size.
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
  return state.locale === "zh" ? `${tools} 次操作${alerts ? ` · ${alerts} 项需关注` : ""}` : `${tools} actions${alerts ? ` · ${alerts} alerts` : ""}`;
}

function summarizeRound(items, roundNumber) {
  const tools = items.filter(isToolEvent);
  const failed = tools.some((event) => ["error", "failed", "denied"].includes(String(event.status || "").toLowerCase()));
  const names = [...new Set(tools.map((event) => String(event.name || "tool")).filter(Boolean))];
  const detail = names.slice(0, 4).join(" · ") || (state.locale === "zh" ? "整理执行步骤" : "Organized execution steps");
  return { failed, detail, title: state.locale === "zh" ? `第 ${roundNumber} 组命令 · ${tools.length} 条` : `Command group ${roundNumber} · ${tools.length} commands`, status: failed ? (state.locale === "zh" ? "需处理" : "Needs attention") : (state.locale === "zh" ? "已完成" : "Complete") };
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
    const isModelEvent = String(event.code || "") === "model_update";
    const summary = isModelEvent && event.code === "model_update"
      ? (state.locale === "zh" ? `行动说明 · 第 ${event.detail?.turn || ""} 轮` : `Action · turn ${event.detail?.turn || ""}`)
      : String(event.summary || traceLabel(event));
    const publicMarkup = publicText ? `<div class="trace-public-plan"><span>${escapeHtml(state.locale === "zh" ? "公开行动" : "Public action")}</span><div>${formatText(publicText)}</div></div>` : "";
    const evidence = structuredDetailMarkup(event.detail, state.locale === "zh" ? "查看完整依据" : "View full evidence");
    const detailMarkup = traceEvidenceMarkup(event, detail, evidence);
    const thinkingLabel = state.locale === "zh" ? "思考" : "Thinking";
    const blockClass = isModelEvent ? "thinking-block " : "";
    const historyClass = String(event.code || "") === "model_update_history" ? " thinking-history" : "";
    const traceAnchor = anchor || event.event_id || event.item_id || `${event.code || "stage"}-${event.created_at_epoch || ""}`;
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
  const toolAnchor = anchor || `${name}-${event.created_at_epoch || ""}`;
  return `<details class="tool-event ${stateClass}${animate ? " event-enter" : ""}" data-agent-block="command" data-agent-item="${escapeHtml(event.event_id || event.item_id || toolAnchor)}" data-item-kind="command" data-tool-event="${escapeHtml(toolAnchor)}"${open ? " open" : ""}>
    <summary class="tool-event-summary"><span class="tool-icon ${denied ? "amber-icon" : ""}">${icon(iconName)}</span><span class="tool-event-copy"><span><strong>${escapeHtml(name)}</strong>${pathMarkup}</span><small>${escapeHtml(event.summary || "")}</small></span><span class="tool-check ${denied ? "denied-check" : failed ? "failed-check" : ""}">${icon(stateIcon)}</span><span class="tool-expand">${icon("chevron-down")}</span></summary>
    ${toolResultMarkup(event)}
  </details>`;
}

function eventTimelineMarkup(events, options = {}) {
  if (!Array.isArray(events) || !events.length) return "";
  const sourceEvents = events.length > MAX_RENDERED_TIMELINE_EVENTS
    ? [
        {
          kind: "trace",
          code: "timeline_truncated",
          phase: "planning",
          status: "ok",
          summary: state.locale === "zh"
            ? `较早的 ${events.length - MAX_RENDERED_TIMELINE_EVENTS + 1} 条运行记录已收起`
            : `${events.length - MAX_RENDERED_TIMELINE_EVENTS + 1} earlier runtime records folded`,
          detail: { count: events.length - MAX_RENDERED_TIMELINE_EVENTS + 1 },
        },
        ...events.slice(-(MAX_RENDERED_TIMELINE_EVENTS - 1)),
      ]
    : events;
  const items = compactModelUpdateEvents(sourceEvents).map((event, index) => ({ event, index }));
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
    const commandGroupLabel = state.locale === "zh" ? "命令组" : "Commands";
    return `<details class="agent-round command-group" data-agent-block="commands" data-agent-item="round-${escapeHtml(roundKey)}" data-item-kind="command-group" data-command-group="${roundKey}" data-agent-round="${roundKey}"${open ? " open" : ""}><summary class="agent-round-summary"><span class="agent-round-title"><span class="agent-round-icon">${icon(round.failed ? "alert-circle" : "layers-3")}</span><span class="command-group-copy"><span class="command-group-label">${escapeHtml(commandGroupLabel)}</span><strong>${escapeHtml(round.title)}</strong><small>${escapeHtml(round.detail)}</small></span></span><span class="agent-round-meta">${escapeHtml(round.status)}<span class="agent-round-chevron">${icon("chevron-down")}</span></span></summary><div class="agent-round-events">${itemMarkup}</div></details>`;
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

function timelineDetailKey(detail) {
  if (detail.matches("details.agent-round")) return `round:${detail.dataset.agentRound || ""}`;
  if (detail.matches("details.tool-event")) return `tool:${detail.dataset.toolEvent || ""}`;
  const owner = detail.closest("details.tool-event, details.agent-round, [data-stage-code]");
  if (!owner) return "";
  const ownerKey = owner.matches("details.tool-event")
    ? `tool:${owner.dataset.toolEvent || ""}`
    : owner.matches("details.agent-round")
      ? `round:${owner.dataset.agentRound || ""}`
      : `stage:${owner.dataset.stageCode || ""}`;
  const nestedIndex = [...owner.querySelectorAll("details")].indexOf(detail);
  return `nested:${ownerKey}:${nestedIndex}`;
}

function captureTimelineOpenDetails(timeline) {
  return new Set([...timeline.querySelectorAll("details[open]")].map(timelineDetailKey).filter(Boolean));
}

function restoreTimelineOpenDetails(timeline, openDetails) {
  if (!(openDetails instanceof Set)) return;
  timeline.querySelectorAll("details").forEach((detail) => { detail.open = openDetails.has(timelineDetailKey(detail)); });
}

function setTimelineDetails(timeline, open) {
  if (!timeline) return;
  timeline.querySelectorAll("details").forEach((detail) => { detail.open = open; });
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
  const fingerprint = events.map((event) => [
    eventSequence(event.sequence),
    event.item_id || event.event_id || "",
    event.kind || "",
    event.code || "",
    event.name || "",
    event.status || "",
    event.summary || "",
    typeof event.detail?.text === "string" ? event.detail.text.slice(0, 2400) : "",
  ].join("|")).join("\n");
  if (timeline.dataset.eventFingerprint === fingerprint) return false;
  const position = chatPosition || captureChatPosition();
  const openDetails = timeline.dataset.initialized === "true" ? captureTimelineOpenDetails(timeline) : null;
  timeline.innerHTML = eventTimelineMarkup(events, { animateFrom: previousCount });
  restoreTimelineOpenDetails(timeline, openDetails);
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
  if (isFocusedTask(data)) $("#pulseStatus").textContent = phaseText;
  updateTaskDock(data);
  restoreChatPosition(chatPosition, false);
}

function scheduleChangesRefresh() {
  window.clearTimeout(changeRefreshTimer);
  changeRefreshTimer = window.setTimeout(() => loadChanges(), 220);
}

function applyTaskEvent(taskId, envelope) {
  const binding = runningTasks.get(taskId);
  if (!binding || !envelope || typeof envelope !== "object") return null;
  const sequence = eventSequence(envelope.sequence);
  const eventId = String(envelope.event_id || "");
  const itemId = String(envelope.item_id || "");
  if (
    (sequence && (binding.seenSequences.has(sequence) || sequence <= eventSequence(binding.cursor)))
    || (eventId && binding.seenEventIds.has(eventId))
    || (itemId && binding.seenEventIds.has(`item:${itemId}`))
  ) return null;
  const payload = envelope.payload && typeof envelope.payload === "object" ? envelope.payload : {};
  const data = { ...(binding.data || {}) };
  const kind = String(envelope.kind || "");
  if (kind === "timeline") {
    const timelineEvent = { ...payload };
    if (eventId && !timelineEvent.event_id) timelineEvent.event_id = eventId;
    if (itemId && !timelineEvent.item_id) timelineEvent.item_id = itemId;
    if (sequence && !timelineEvent.sequence) timelineEvent.sequence = sequence;
    data.events = mergeTimelineEvents(data.events, [timelineEvent]);
  } else if (kind === "stream_delta") {
    if (payload.stream_text != null) data.stream_text = String(payload.stream_text || "");
    else if (payload.delta) data.stream_text = `${String(data.stream_text || "")}${String(payload.delta)}`;
    if (payload.stream_length != null) data.stream_length = Number(payload.stream_length) || String(data.stream_text || "").length;
    if (payload.phase) data.phase = String(payload.phase);
  } else if (kind === "state" || kind === "status") {
    if (payload.status) data.status = String(payload.status);
    if (payload.phase) data.phase = String(payload.phase);
    if (payload.finished_at) data.finished_at = payload.finished_at;
    if (payload.error !== undefined) data.error = payload.error;
    if (payload.cancel_reason !== undefined) data.cancel_reason = payload.cancel_reason;
  } else if (kind === "usage") {
    if (payload.tokens_used && typeof payload.tokens_used === "object") data.tokens_used = { ...payload.tokens_used };
    if (payload.metrics && typeof payload.metrics === "object") data.metrics = { ...payload.metrics };
    if (payload.usage && typeof payload.usage === "object") data.usage_by_turn = [...(data.usage_by_turn || []), { ...payload.usage }].slice(-64);
  } else if (kind === "context") {
    if (payload.context && typeof payload.context === "object") data.context = { ...payload.context };
  } else if (kind === "compaction") {
    if (payload.event && typeof payload.event === "object") data.compaction_events = [...(data.compaction_events || []), { ...payload.event }].slice(-64);
  } else if (kind === "result") {
    if (payload.answer !== undefined) data.answer = payload.answer;
    if (payload.error !== undefined) data.error = payload.error;
    data.result = { ...(data.result || {}), answer: data.answer, error: data.error };
  }
  if (payload.state_version != null) data.state_version = Math.max(Number(data.state_version) || 0, Number(payload.state_version) || 0);
  binding.cursor = Math.max(eventSequence(binding.cursor), sequence);
  data.event_cursor = binding.cursor;
  if (sequence) binding.seenSequences.add(sequence);
  if (eventId) binding.seenEventIds.add(eventId);
  binding.data = data;
  updateBoundTask(taskId, data, { skipSnapshotMerge: true });
  return data;
}

function updateBoundTask(taskId, data, options = {}) {
  const binding = runningTasks.get(taskId);
  if (!binding) return;
  const next = options.skipSnapshotMerge
    ? { ...data, session_id: data.session_id || binding.sessionId, workspace_path: data.workspace_path || binding.workspacePath }
    : applyTaskSnapshot(binding, data, { replaceEvents: true });
  binding.data = next;
  if (isCurrentTaskScope(next)) {
    if (!document.getElementById(binding.loadingId)) addLoadingMessage(binding.loadingId, next, { scrollToLatest: false });
    updateLiveTask(binding.loadingId, next);
  }
  if (Array.isArray(next.events) && next.events.some((event) => ["write_file", "edit_file", "move", "delete"].includes(event.name))) scheduleChangesRefresh();
  return next;
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
  cacheTaskDetail(finalData);
  runningTasks.delete(taskId);
  if (taskBySession.get(taskSessionKey(binding.sessionId, binding.workspacePath)) === taskId) taskBySession.delete(taskSessionKey(binding.sessionId, binding.workspacePath));

  const currentScope = isCurrentTaskScope({
    task_id: taskId,
    session_id: binding.sessionId,
    workspace_path: binding.workspacePath,
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
    const pending = holder.querySelector(`#${CSS.escape(binding.loadingId || loadingId)}`);
    if (pending) {
      const replacement = document.createElement("div");
      replacement.innerHTML = assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`);
      pending.replaceWith(replacement.firstElementChild);
    } else {
      holder.insertAdjacentHTML("beforeend", assistantMessageMarkup(finalData, `live-${binding.loadingId || loadingId}`));
    }
    const cacheKey = sessionViewKey(binding.sessionId, binding.workspacePath);
    const compactedMarkup = compactSessionMarkup(holder.innerHTML);
    sessionMarkup.set(cacheKey, compactedMarkup);
    try { localStorage.setItem(cacheKey, compactedMarkup); } catch { /* best effort */ }
  }
  if (finalData.status !== "completed") showToast(finalData.error || (finalData.status === "cancelled" ? "任务已取消" : "任务失败"));
  scheduleChangesRefresh();
  await loadTaskHistory();
  return finalData;
}

async function pollTask(taskId) {
  const binding = runningTasks.get(taskId);
  let delay = 220;
  while (true) {
    try {
      const data = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000);
      updateBoundTask(taskId, data);
      if (isTerminalTask(data)) return completeTask(binding?.loadingId || "", data);
      delay = 220;
    } catch (error) {
      // The task is durable on the server. Keep watching through a short API
      // outage instead of converting a transport blip into a false failure.
      if (!runningTasks.has(taskId)) throw error;
      delay = Math.min(5000, Math.max(500, Math.round(delay * 1.6)));
    }
    await new Promise((resolve) => window.setTimeout(resolve, delay));
  }
}

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
      closeSource();
      pollTask(taskId).then(resolve, reject);
    };

    const finish = async (data) => {
      if (settled || !isTerminalTask(data)) return;
      settled = true;
      closeSource();
      try {
        // The terminal event contains enough state to render immediately, but
        // one final snapshot also carries the complete answer/result payload.
        const latest = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 12000);
        updateBoundTask(taskId, latest);
        resolve(await completeTask(loadingId, latest));
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
        // A malformed frame is ignored; the connection error/retry path still
        // has a chance to recover the task from its durable snapshot.
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
        // The next replay or a polling fallback can still restore the state.
      }
    };

    const checkLatestAfterError = () => requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, {}, 8000)
      .then((latest) => {
        if (settled) return;
        const current = updateBoundTask(taskId, latest);
        if (isTerminalTask(current || latest)) {
          finish(current || latest);
          return;
        }
        scheduleReconnect();
      })
      .catch(() => scheduleReconnect());

    const scheduleReconnect = () => {
      if (settled || fallbackStarted) return;
      closeSource();
      reconnectAttempts += 1;
      if (reconnectAttempts > maxReconnectAttempts) {
        fallback();
        return;
      }
      const delay = Math.min(6000, 500 * (2 ** (reconnectAttempts - 1)));
      reconnectTimer = window.setTimeout(connect, delay);
    };

    function connect() {
      if (settled || fallbackStarted) return;
      const cursor = eventSequence(binding?.cursor || binding?.data?.event_cursor);
      source = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events?after=${cursor}`);
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
  return streamTask(taskId);
}

async function cancelActiveTask() {
  const taskIds = sessionTaskBindings(state.sessionId).map((binding) => binding.taskId);
  const fallback = taskBySession.get(taskSessionKey(state.sessionId)) || null;
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
      taskDetailsById.clear();
      taskDetailLoads.clear();
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
      const active = activeTasks.find((item) => isCurrentTaskScope(item));
      if (active) updateTaskDock(active);
      else {
        $("#taskDock").hidden = true;
        state.lastTask = null;
        state.activeTaskId = null;
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
  const streamSize = Number(task.stream_length || String(task.stream_text || "").length);
  const detail = `${phase} · ${formatDuration(taskDuration(task))} · ${streamSize} chars · ${taskMetrics(task)}`;
  const children = task.child_task_ids?.length ? ` · ${task.child_task_ids.length} ${t("tasks.children")}` : "";
  const workspace = task.workspace_path ? task.workspace_path.split(/[\\/]/).filter(Boolean).pop() : "workspace";
  const details = `<button class="panel-icon-action" data-open-detail="${escapeHtml(task.task_id)}" title="${escapeHtml(t("tasks.detail"))}" aria-label="${escapeHtml(t("tasks.detail"))}">${icon("maximize-2")}</button>`;
  return `<div class="task-row" data-open-task="${escapeHtml(task.task_id)}" tabindex="0"><span class="task-state ${statusClass}"></span><div><strong>${escapeHtml(task.task_kind === "batch" ? `${task.task_id} · ${t("tasks.children")}` : task.task_id)}</strong><small>${escapeHtml(workspace)} · ${escapeHtml(detail)}${children}</small></div><div class="task-row-actions">${details}${resume}${cancel}</div></div>`;
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
    const mergedHistory = historyItems.some((item) => item.task_id === task.task_id)
      ? historyItems.map((item) => item.task_id === task.task_id ? task : item)
      : [task, ...historyItems];
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
    showToast(state.locale === "zh" ? "已打开任务会话" : "Task session opened");
  } catch (error) {
    showToast(error.message);
  }
}

async function openTaskDetail(taskId) {
  try {
    const task = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    const events = Array.isArray(task.events) ? eventTimelineMarkup(task.events) : "";
    const execution = executionTrailMarkup(events, task.events || []);
    const children = Array.isArray(task.child_task_ids) && task.child_task_ids.length
      ? `<div class="task-detail-children">${task.child_task_ids.map((child) => `<button class="panel-session" data-open-task="${escapeHtml(child)}">${escapeHtml(child)}</button>`).join("")}</div>`
      : "";
    const resume = ["failed", "cancelled", "interrupted"].includes(task.status)
      ? `<button class="panel-primary" data-resume-task="${escapeHtml(task.task_id)}">${t("tasks.resume")}</button>`
      : "";
    const attachments = attachmentMarkup(task.attachments || []);
    openPanel(`${t("tasks.open")} · ${task.task_id}`, `<div class="task-detail"><div class="task-detail-status"><span class="task-state ${task.status === "completed" ? "success" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "cancelled" : "running"}"></span><strong>${escapeHtml(phaseLabel(task))}</strong><span>${escapeHtml(taskMetrics(task))}</span></div><div class="task-detail-actions task-detail-top-actions"><button class="panel-secondary" data-open-task="${escapeHtml(task.task_id)}">${icon("arrow-up-right")} ${escapeHtml(t("tasks.openSession"))}</button></div>${runtimeMetricsMarkup(task)}<div class="panel-section-title">${t("workspace.current")}</div><code class="task-detail-path">${escapeHtml(task.workspace_path || "")}</code><div class="panel-section-title">Prompt</div><div class="task-detail-prompt">${formatText(task.prompt || task.preview || "")}</div>${attachments ? `<div class="panel-section-title">Images</div>${attachments}` : ""}<div class="panel-section-title">Response</div><div class="task-detail-answer">${formatText(task.answer || task.stream_text || task.error || "")}</div>${execution ? `<div class="panel-section-title">Tools & stage trace</div>${execution}` : ""}${children}${resume ? `<div class="task-detail-actions">${resume}</div>` : ""}</div>`, { immersive: true });
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

function setGameWideMode(enabled) {
  const wide = Boolean(enabled);
  const modal = $("#gameModal");
  const button = $("#gameWideMode");
  modal.classList.toggle("wide-mode", wide);
  button?.classList.toggle("active", wide);
  button?.setAttribute("aria-pressed", String(wide));
  if (button) {
    button.title = t(wide ? "game.compactMode" : "game.wideMode");
    button.querySelector("span").textContent = t(wide ? "game.compactMode" : "game.wideMode");
  }
  localStorage.setItem("minicc-game-wide-mode", wide ? "on" : "off");
}
function toggleGameWideMode() {
  setGameWideMode(!$("#gameModal").classList.contains("wide-mode"));
}
function openGame() {
  $("#gameModal").classList.add("show");
  $("#gameModal").setAttribute("aria-hidden", "false");
  setGameWideMode(localStorage.getItem("minicc-game-wide-mode") === "on");
  initGame();
}

function openGameWindow() { window.open(location.origin + location.pathname + "?arcade=1", "minicc-arcade", "popup,width=980,height=760"); }
function toggleGameFullscreen() { const card = $("#gameModal .game-card"); if (!document.fullscreenElement) card.requestFullscreen?.(); else document.exitFullscreen?.(); }
function closeGame() {
  const active = document.activeElement;
  if (active instanceof HTMLElement && $("#gameModal").contains(active)) active.blur();
  closeGameCodex();
  $("#gameModal").classList.remove("show");
  $("#gameModal").setAttribute("aria-hidden", "true");
  game.running = false;
  cancelAnimationFrame(game.frame);
  stopGameMusic();
  window.scrollTo(0, 0);
}

const codexState = { tab: "plants", plant: "peashooter", zombie: "walker" };
const codexPlantNames = { peashooter: "豌豆射手", sunflower: "向日葵", wallnut: "坚果墙", repeater: "双发射手", cherrybomb: "樱桃炸弹", icepeashooter: "寒冰射手", firepeashooter: "火焰射手", twinpea: "双发强化", kernelpult: "玉米投手", pumpkin: "南瓜头", spikeweed: "地刺", gloomshroom: "忧郁菇", potatomine: "土豆雷", threepeater: "三线射手", jalapeno: "火爆辣椒", magnetshroom: "磁力菇", garlic: "大蒜", squash: "窝瓜", gatlingpea: "机枪射手" };
const codexZombieNames = { walker: "普通僵尸", backup: "伴舞僵尸", roadblock: "路障僵尸", conehead: "路锥僵尸", imp: "小鬼僵尸", scout: "侦察僵尸", storm: "风暴僵尸", runner: "奔跑僵尸", polevault: "撑杆僵尸", bucket: "铁桶僵尸", football: "橄榄球僵尸", miner: "矿工僵尸", flag: "旗帜僵尸", dancer: "舞王僵尸", newspaper: "报纸僵尸", gargantuar: "巨人僵尸", witch: "女巫僵尸", dragon: "龙僵尸", shield: "护盾僵尸" };
const codexPlantIcons = { peashooter: "🌱", sunflower: "🌻", wallnut: "🥜", repeater: "🌿", cherrybomb: "🍒", icepeashooter: "❄️", firepeashooter: "🔥", twinpea: "🌱", kernelpult: "🌽", pumpkin: "🎃", spikeweed: "🌵", gloomshroom: "🍄", potatomine: "🥔", threepeater: "🌾", jalapeno: "🌶️", magnetshroom: "🧲", garlic: "🧄", squash: "🎃", gatlingpea: "🔫" };
const codexPlantSpecials = { peashooter: "发射普通豌豆，稳定输出。", sunflower: "每隔一段时间生产 25 阳光。", wallnut: "高生命值阻挡，拖延僵尸。", repeater: "每轮发射 2 发豌豆，并可穿透 1 个目标。", cherrybomb: "短延迟后在同一行 145 范围内直接消灭僵尸。", icepeashooter: "命中后减速 3200ms，并可穿透 1 个目标。", firepeashooter: "每发 2 点伤害并施加 2600ms 灼烧，灼烧伤害 3。", twinpea: "每轮发射 2 发强化豌豆，每发 2 点伤害。", kernelpult: "28% 概率用黄油定身，并可穿透 1 个目标。", pumpkin: "为同格植物提供 32 点护罩生命。", spikeweed: "攻击所在格附近 44 范围内的僵尸。", gloomshroom: "近身范围攻击并施加 900ms 减速。", potatomine: "1800ms 后布雷，在同一行 90 范围内爆炸。", threepeater: "同时攻击当前行、上行和下行。", jalapeno: "短延迟后消灭所在行的全部僵尸。", magnetshroom: "周期性吸走僵尸护甲或装备，不直接造成伤害。", garlic: "被咬后将僵尸改道到下一行。", squash: "接近时重击并直接消灭目标。", gatlingpea: "每轮连续发射 4 发豌豆，每发 1 点伤害。" };
const codexZombieSkills = { walker: "无额外技能，接触植物后啃食。", backup: "伴随舞王召唤，沿行啃食。", roadblock: "路障提供额外防护。", conehead: "路锥提供额外护甲。", imp: "快速移动并跳跃植物。", scout: "间歇冲刺并标记、诅咒附近植物。", storm: "周期性使同一行植物短暂失效。", runner: "沿行快速移动并间歇冲刺。", polevault: "遇到第一株植物时撑杆跳过。", bucket: "铁桶提供高额护甲。", football: "高护甲并可冲锋攻击。", miner: "地下潜行，接近防线后出土。", flag: "为同一行盟友提供移动速度加成。", dancer: "周期性召唤伴舞僵尸。", newspaper: "报纸被破坏后进入狂暴状态。", gargantuar: "缓慢推进，接触植物时重击并造成高额伤害。", witch: "标记并诅咒附近植物。", dragon: "喷吐火焰，对植物施加灼烧。", shield: "周期性恢复护盾。" };
function codexPlantInfo(type) {
  const profile = plantProfiles[type] || {};
  const damage = profile.damage ? `${profile.damage} 点/发` : ["cherrybomb", "jalapeno", "potatomine", "squash"].includes(type) ? "特殊/爆发伤害" : "0（功能型）";
  const target = profile.rows || type === "jalapeno" ? "群体" : ["cherrybomb", "potatomine", "squash"].includes(type) ? "范围爆发" : "单体";
  const range = profile.rows ? "当前行及相邻两行" : ["gloomshroom", "spikeweed"].includes(type) ? "近身（约 44）" : ["cherrybomb", "potatomine"].includes(type) ? "同一行范围" : type === "jalapeno" ? "整行" : "所在行直线/所在格";
  const usage = type === "sunflower" ? "放在后排，持续生产阳光。" : type === "wallnut" || type === "pumpkin" ? "放在僵尸路线前吸收伤害。" : `选中卡片后点击草坪格子，消耗 ${plantCost[type]} 阳光。`;
  return { name: codexPlantNames[type], icon: codexPlantIcons[type], health: plantHealth[type], cost: plantCost[type], damage, attack: profile.shots ? `${profile.shots} 发/轮` : type === "threepeater" ? "3 条线路" : "特殊逻辑", target, range, usage, special: codexPlantSpecials[type] || "按当前游戏逻辑发挥作用。", raw: Object.keys(profile).length ? JSON.stringify(profile) : "由独立游戏逻辑处理" };
}
function codexZombieInfo(type) {
  const profile = zombieProfiles[type];
  const movement = profile.burrow ? "地下潜行，接近防线后出土" : profile.vault ? "持杆前进，遇到植物时跳过" : profile.leap ? "快速前进并跳跃植物" : profile.dash ? "沿所在行移动并间歇冲刺" : profile.giant ? "缓慢直线推进" : "沿所在行向左直线移动";
  return { name: codexZombieNames[type], hp: profile.hp, armor: profile.armor || 0, speed: `${profile.speed.toFixed(3)} + 每波 ${profile.growth.toFixed(4)}`, attack: `${profile.attackInterval} ms`, score: profile.score, movement, skills: codexZombieSkills[type] };
}
function codexRows(rows) { return rows.map(([label, value]) => `<div class="codex-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join(""); }
function renderCodex() {
  const plants = codexState.tab === "plants";
  const keys = Object.keys(plants ? plantCost : zombieProfiles);
  const selected = codexState[plants ? "plant" : "zombie"];
  $("#codexPlantCount").textContent = `（${Object.keys(plantCost).length}）`;
  $("#codexZombieCount").textContent = `（${Object.keys(zombieProfiles).length}）`;
  $$(".codex-tab").forEach((tab) => { const active = tab.dataset.codexTab === codexState.tab; tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active)); });
  $("#codexEntryList").innerHTML = keys.map((key) => { const info = plants ? codexPlantInfo(key) : codexZombieInfo(key); return `<button class="codex-entry ${key === selected ? "active" : ""}" type="button" data-codex-entry="${key}"><span class="codex-entry-icon">${info.icon || "🧟"}</span><span>${escapeHtml(info.name)}</span></button>`; }).join("");
  const info = plants ? codexPlantInfo(selected) : codexZombieInfo(selected);
  $("#codexDetail").innerHTML = `<div class="codex-detail-title"><span class="codex-detail-icon">${info.icon || "🧟"}</span><div><span class="game-kicker">${plants ? "植物详情" : "僵尸详情"}</span><h4>${escapeHtml(info.name)}</h4></div></div>${plants ? `<dl class="codex-stats">${codexRows([["阳光消耗", `${info.cost} 阳光`], ["植物生命值", `${info.health} HP`], ["伤害", info.damage], ["攻击频率", info.attack], ["伤害类型", info.target], ["攻击范围", info.range]])}</dl><div class="codex-section"><strong>使用方法</strong><p>${escapeHtml(info.usage)}</p></div><div class="codex-section"><strong>特殊效果</strong><p>${escapeHtml(info.special)}</p></div><div class="codex-section"><strong>实际 profile 参数</strong><code>${escapeHtml(info.raw)}</code></div>` : `<dl class="codex-stats">${codexRows([["基础生命值", `${info.hp} HP`], ["护甲", `${info.armor} 点`], ["移动速度", info.speed], ["攻击间隔", info.attack], ["击退积分", info.score]])}</dl><div class="codex-health-bar" aria-label="僵尸基础生命值"><i style="width: 100%"></i></div><div class="codex-section"><strong>移动方式</strong><p>${escapeHtml(info.movement)}</p></div><div class="codex-section"><strong>特殊技能</strong><p>${escapeHtml(info.skills)}</p></div>`}`;
  $$(".codex-entry").forEach((entry) => entry.addEventListener("click", () => { codexState[plants ? "plant" : "zombie"] = entry.dataset.codexEntry; renderCodex(); }));
}
function openGameCodex(tab = "plants") { codexState.tab = tab; $("#gameCodexPanel").classList.add("show"); $("#gameCodexPanel").setAttribute("aria-hidden", "false"); renderCodex(); window.lucide?.createIcons(); }
function closeGameCodex() { const panel = $("#gameCodexPanel"); if (!panel) return; panel.classList.remove("show"); panel.setAttribute("aria-hidden", "true"); }

const MAX_WAVES = 10;
const GAME_DIFFICULTIES = {
  normal: { hpMultiplier: .9, initialSun: 200, speedMultiplier: .9, spawnDelayMultiplier: 1.16, waveBonus: -1 },
  hard: { hpMultiplier: 1, initialSun: 175, speedMultiplier: 1, spawnDelayMultiplier: 1, waveBonus: 0 },
  nightmare: { hpMultiplier: 1.58, initialSun: 110, speedMultiplier: 1.28, spawnDelayMultiplier: .56, waveBonus: 6 },
};
const savedGameDifficulty = Object.prototype.hasOwnProperty.call(GAME_DIFFICULTIES, localStorage.getItem("minicc-game-difficulty")) ? localStorage.getItem("minicc-game-difficulty") : "hard";
const WAVE_TARGET = (wave, difficulty = savedGameDifficulty) => 7 + wave * 2 + GAME_DIFFICULTIES[difficulty].waveBonus + (difficulty === "nightmare" ? wave + Math.floor((wave + 1) / 2) : 0);
const game = { running: false, paused: false, pauseReasons: new Set(), frame: 0, score: 0, sun: GAME_DIFFICULTIES[savedGameDifficulty].initialSun, wave: 1, waveTarget: WAVE_TARGET(1), waveSpawned: 0, totalSpawned: 0, waveClearTimer: 0, elapsed: 0, selected: null, hoverCell: null, shovel: false, seedCooldowns: {}, skillCooldowns: {}, energy: 60, rallyTimer: 0, plants: [], zombies: [], defeated: [], suns: [], shots: [], particles: [], impacts: [], popups: [], mowers: [], combo: 0, comboTimer: 0, bestCombo: 0, bannerTimer: 0, bannerText: "", bannerColor: "#ffe27c", dangerPulse: 0, last: 0, spawnTimer: 0, skyTimer: 0, dangerTimer: 0, difficulty: savedGameDifficulty, autoSun: localStorage.getItem("minicc-game-auto-sun") !== "off", musicOn: localStorage.getItem("minicc-game-sound") !== "off", volume: Math.max(0, Math.min(100, Number(localStorage.getItem("minicc-game-volume")) || 70)), audio: null, hudAt: 0, flagRows: new Uint8Array(5), renderStats: { frames: 0, fps: 0, lastFrameMs: 0, maxFrameMs: 0, longFrames: 0, frameSamples: [], recentSamples: new Array(60), recentSampleIndex: 0, recentSampleCount: 0, recentLongFrames: 0, windowStartedAt: 0, windowFrames: 0, indexRebuilds: 0, rowQueries: 0, rowCandidates: 0, drawCalls: 0, plantDraws: 0, zombieDraws: 0, animationSwitches: 0 } };
const ZOMBIE_BODY_COLORS = { walker: "#526b5e", roadblock: "#53677d", bucket: "#566273", runner: "#9b5d4f", imp: "#b45d4e", football: "#334b68", miner: "#72574a", polevault: "#57785d", flag: "#754d6c", dancer: "#8d3f68", newspaper: "#806c50", conehead: "#b76b4d", witch: "#563d70", dragon: "#8a453f", gargantuar: "#694450", backup: "#a15c72" };
const gameLayout = { left: 78, top: 72, cellW: 70, cellH: 65, rows: 5, cols: 9 };
const GAME_LOGICAL_WIDTH = 720;
const GAME_LOGICAL_HEIGHT = 420;
const GAME_MAX_PARTICLES = 180;
const GAME_PARTICLE_DRAW_BUDGET = 120;
const GAME_MAX_POPUPS = 48;
const GAME_MOWER_TRIGGER_X = 92;
const GAME_MOWER_SPEED = .62;
const GAME_MOWER_CLEAR_RADIUS = 36;
const GAME_MOWER_EXIT_X = GAME_LOGICAL_WIDTH + 46;
const GAME_COMBO_WINDOW = 1800;
const GAME_SKILLS = {
  pulse: { cost: 25, cooldown: 7000, label: "game.skillPulse", hint: "game.skillPulseHint" },
  sun: { cost: 35, cooldown: 10000, label: "game.skillSun", hint: "game.skillSunHint" },
  rally: { cost: 45, cooldown: 14000, label: "game.skillRally", hint: "game.skillRallyHint" },
};
const gameRows = {
  plants: Array.from({ length: gameLayout.rows }, () => []),
  zombies: Array.from({ length: gameLayout.rows }, () => []),
};
function cacheGameEntityPosition(entity) {
  const row = Number.isInteger(entity?.row) ? entity.row : -1;
  const col = Number.isInteger(entity?.col) ? entity.col : 0;
  const position = gameCellPositions[row]?.[col] || gameCellPositions[row]?.[0];
  if (position) {
    entity.cellX = position.x;
    entity.cellY = position.y;
    if (entity.type && entity.x === undefined) entity.x = position.x;
    if (entity.type && entity.y === undefined) entity.y = position.y;
  }
  return entity;
}
function rebuildGameRows(kind, entities) {
  const rows = gameRows[kind];
  rows.forEach((row) => { row.length = 0; });
  entities.forEach((entity) => {
    cacheGameEntityPosition(entity);
    if (kind === "plants" && entity.underPlant) cacheGameEntityPosition(entity.underPlant);
    const row = Number.isInteger(entity.row) ? entity.row : -1;
    if (row >= 0 && row < gameLayout.rows) rows[row].push(entity);
  });
  return rows;
}
function firstIndexedEntity(kind, predicate) {
  const rows = gameRows[kind];
  for (let row = 0; row < rows.length; row += 1) {
    const entities = rowEntities(kind, row);
    for (let index = 0; index < entities.length; index += 1) {
      if (predicate(entities[index])) return entities[index];
    }
  }
  return null;
}
function anyIndexedEntity(kind, predicate) { return Boolean(firstIndexedEntity(kind, predicate)); }
function rowEntities(kind, row) {
  const entities = gameRows[kind][row] || [];
  game.renderStats.rowQueries += 1;
  game.renderStats.rowCandidates += entities.length;
  return entities;
}
function firstRowEntity(kind, row, predicate) {
 const entities = rowEntities(kind, row);
 for (let index = 0; index < entities.length; index += 1) if (predicate(entities[index])) return entities[index];
 return null;
}
function anyRowEntity(kind, row, predicate) { return Boolean(firstRowEntity(kind, row, predicate)); }
function forEachRowEntity(kind, row, callback) {
 const entities = rowEntities(kind, row);
 for (let index = 0; index < entities.length;) {
  const entity = entities[index];
  callback(entity);
  // A callback may remove the current entity; keep the cursor in place.
  if (entities[index] === entity) index += 1;
 }
}
function trackGameAnimation(entity, state) {
 if (!entity || entity.animationState === state) return;
 entity.animationState = state;
 if (game.renderStats) game.renderStats.animationSwitches = (game.renderStats.animationSwitches || 0) + 1;
}
function removeRowEntity(kind, entity, rowOverride = null) {
 const row = Number.isInteger(rowOverride) ? rowOverride : (Number.isInteger(entity?.row) ? entity.row : -1);
 const entities = rowEntities(kind, row);
 const index = entities.indexOf(entity);
 if (index >= 0) entities.splice(index, 1);
}
function moveRowEntity(kind, entity, previousRow) {
 const nextRow = Number.isInteger(entity?.row) ? entity.row : -1;
 if (previousRow === nextRow) return;
 removeRowEntity(kind, entity, previousRow);
 if (nextRow >= 0 && nextRow < gameLayout.rows) rowEntities(kind, nextRow).push(entity);
}
function rebuildGameIndexes() {
 rebuildGameRows("plants", game.plants);
 rebuildGameRows("zombies", game.zombies);
 game.renderStats.indexRebuilds += 1;
}
const gameCellPositions = Array.from({ length: gameLayout.rows }, (_, row) =>
 Array.from({ length: gameLayout.cols }, (_, col) => ({
   x: gameLayout.left + col * gameLayout.cellW + 35,
   y: gameLayout.top + row * gameLayout.cellH + 31,
 })),
);
const gameRender = { canvas: null, ctx: null, background: null, dpr: 1, effects: "high", deviceProfile: null };
function resizeGameCanvas() {
  const canvas = gameRender.canvas || $("#gameCanvas");
  if (!canvas) return;
  gameRender.canvas = canvas;
  // Keep the logical field sharp without making high-DPR devices rasterize an oversized surface.
  const dpr = Math.min(1.75, Math.max(1, window.devicePixelRatio || 1));
  const width = Math.round(GAME_LOGICAL_WIDTH * dpr);
  const height = Math.round(GAME_LOGICAL_HEIGHT * dpr);
  if (!gameRender.ctx || canvas.width !== width || canvas.height !== height || gameRender.dpr !== dpr) {
    canvas.width = width;
    canvas.height = height;
    gameRender.dpr = dpr;
    gameRender.ctx = canvas.getContext("2d", { alpha: false, desynchronized: true }) || canvas.getContext("2d");
    gameRender.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    gameRender.ctx.imageSmoothingEnabled = true;
    gameRender.ctx.imageSmoothingQuality = "high";
    gameRender.background = null;
  }
  if (!gameRender.background) buildGameBackground();
}
function buildGameBackground() {
  const background = document.createElement("canvas");
  background.width = GAME_LOGICAL_WIDTH;
  background.height = GAME_LOGICAL_HEIGHT;
  const ctx = background.getContext("2d");
  const sky = ctx.createLinearGradient(0, 0, 0, GAME_LOGICAL_HEIGHT);
  sky.addColorStop(0, "#9bd9df"); sky.addColorStop(.35, "#d7e7b2"); sky.addColorStop(.36, "#659b58"); sky.addColorStop(1, "#315744");
  ctx.fillStyle = sky; ctx.fillRect(0, 0, GAME_LOGICAL_WIDTH, GAME_LOGICAL_HEIGHT);
  ctx.fillStyle = "rgba(255,255,255,.18)"; ctx.beginPath(); ctx.arc(605, 42, 29, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#253b45"; ctx.fillRect(0, 0, GAME_LOGICAL_WIDTH, 58);
  ctx.fillStyle = "#eef3cf"; ctx.font = "700 12px Manrope, sans-serif"; ctx.fillText("BACKYARD", 18, 23);
  ctx.fillStyle = "#d9b16e"; ctx.fillRect(48, 28, 17, 23); ctx.fillStyle = "#693f38"; ctx.beginPath(); ctx.moveTo(44, 29); ctx.lineTo(57, 16); ctx.lineTo(70, 29); ctx.fill(); ctx.fillStyle = "#f4d27a"; ctx.fillRect(53, 39, 7, 12);
  for (let row = 0; row < gameLayout.rows; row += 1) for (let col = 0; col < gameLayout.cols; col += 1) { const x = gameLayout.left + col * gameLayout.cellW, y = gameLayout.top + row * gameLayout.cellH; ctx.fillStyle = (row + col) % 2 ? "#75b866" : "#83c573"; roundedRect(ctx, x + 2, y + 2, 66, 61, 8); ctx.fill(); ctx.strokeStyle = "rgba(221, 246, 151, .18)"; ctx.stroke(); }
  const laneGlow = ctx.createLinearGradient(78, 72, 78, 397);
  laneGlow.addColorStop(0, "rgba(255,255,255,.06)"); laneGlow.addColorStop(.5, "rgba(255,255,255,0)"); laneGlow.addColorStop(1, "rgba(12,38,29,.14)");
  ctx.fillStyle = laneGlow; ctx.fillRect(78, 72, 630, 325);
  ctx.strokeStyle = "rgba(232, 250, 176, .14)"; ctx.lineWidth = 1;
  for (let row = 0; row <= gameLayout.rows; row += 1) { const y = gameLayout.top + row * gameLayout.cellH; ctx.beginPath(); ctx.moveTo(gameLayout.left, y); ctx.lineTo(708, y); ctx.stroke(); }
  ctx.fillStyle = "rgba(240, 213, 140, .28)"; ctx.fillRect(674, 60, 3, 360);
  ctx.fillStyle = "rgba(255,255,255,.07)"; ctx.fillRect(678, 60, 1, 360);
  gameRender.background = background;
}
function recordGameFrame(now, startedAt) {
  const stats = game.renderStats;
  const frameMs = Math.max(0, performance.now() - startedAt);
  const sampleIndex = stats.frames % 240;
  stats.frames += 1;
  stats.lastFrameMs = frameMs;
  stats.maxFrameMs = Math.max(stats.maxFrameMs, frameMs);
  if (frameMs > 32) stats.longFrames += 1;
  // Keep the rolling profiler allocation-free; shift() would copy up to 240 entries every frame.
  if (stats.frameSamples.length < 240) stats.frameSamples.push(frameMs);
  else stats.frameSamples[sampleIndex] = frameMs;
  const recentIndex = Number.isInteger(stats.recentSampleIndex) ? stats.recentSampleIndex : 0;
  const previousSample = stats.recentSamples?.[recentIndex];
  if (previousSample > 32) stats.recentLongFrames -= 1;
  if (!stats.recentSamples) stats.recentSamples = new Array(60);
  stats.recentSamples[recentIndex] = frameMs;
  if (frameMs > 32) stats.recentLongFrames += 1;
  stats.recentSampleIndex = (recentIndex + 1) % 60;
  stats.recentSampleCount = Math.min(60, stats.recentSampleCount + 1);
  if (stats.recentSampleCount >= 30 && stats.recentLongFrames >= 6) gameRender.effects = "low";
  else if (gameRender.effects === "low" && stats.recentSampleCount >= 30 && stats.recentLongFrames <= 1) gameRender.effects = "high";
  if (!stats.windowStartedAt) stats.windowStartedAt = now;
  stats.windowFrames += 1;
  if (now - stats.windowStartedAt >= 1000) {
    stats.fps = stats.windowFrames * 1000 / (now - stats.windowStartedAt);
    stats.windowFrames = 0;
    stats.windowStartedAt = now;
    const performanceNode = $("#gamePerformance");
    if (performanceNode) {
      $("#gameFps").textContent = String(Math.round(stats.fps));
      $("#gameFrameMs").textContent = `${stats.lastFrameMs.toFixed(1)}ms`;
      $("#gameLongFrames").textContent = String(stats.longFrames);
      $("#gameObjectCount").textContent = String(game.suns.length + game.plants.length + game.zombies.length + game.shots.length + game.particles.length + game.impacts.length);
      performanceNode.classList.toggle("warning", stats.lastFrameMs > 32 || stats.recentLongFrames > 0);
    }
  }
}
const plantCost = { peashooter: 100, sunflower: 50, wallnut: 50, repeater: 180, cherrybomb: 150, icepeashooter: 175, firepeashooter: 175, twinpea: 225, kernelpult: 100, pumpkin: 125, spikeweed: 100, gloomshroom: 150, potatomine: 25, threepeater: 325, jalapeno: 125, magnetshroom: 100, garlic: 50, squash: 50, gatlingpea: 350 };
const PLANT_TYPES = Object.keys(plantCost);
const plantHealth = { peashooter: 7, sunflower: 6, wallnut: 24, repeater: 8, cherrybomb: 4, icepeashooter: 7, firepeashooter: 7, twinpea: 10, kernelpult: 8, pumpkin: 32, spikeweed: 10, gloomshroom: 9, potatomine: 3, threepeater: 8, jalapeno: 4, magnetshroom: 7, garlic: 8, squash: 6, gatlingpea: 9 };
const plantColor = { peashooter: "#62b5a0", sunflower: "#f6c453", wallnut: "#ad7556", repeater: "#75c77b", cherrybomb: "#dd6d73", icepeashooter: "#8bc9e8", firepeashooter: "#f07855", twinpea: "#8bd15f", kernelpult: "#e8bf65", pumpkin: "#e29b45", spikeweed: "#8dbf62", gloomshroom: "#8563aa", potatomine: "#a9bd72", threepeater: "#72c789", jalapeno: "#ef765f", magnetshroom: "#b187d5", garlic: "#f3e1b4", squash: "#e2a848", gatlingpea: "#4db878" };
const plantCooldown = { peashooter: 250, sunflower: 900, wallnut: 700, repeater: 450, cherrybomb: 900, icepeashooter: 850, firepeashooter: 850, twinpea: 950, kernelpult: 700, pumpkin: 1050, spikeweed: 650, gloomshroom: 1100, potatomine: 650, threepeater: 1100, jalapeno: 1200, magnetshroom: 900, garlic: 800, squash: 800, gatlingpea: 1400 };
const plantProfiles = {
  peashooter: { interval: 1050, shots: 1, damage: 1, slow: 0 },
  repeater: { interval: 1250, shots: 2, damage: 1, slow: 0, pierce: 1 },
  icepeashooter: { interval: 1300, shots: 1, damage: 1, slow: 3200, pierce: 1 },
  firepeashooter: { interval: 1350, shots: 1, damage: 2, slow: 0, fire: true, burn: 2600, burnDamage: 3 },
  twinpea: { interval: 1450, shots: 2, damage: 2, slow: 0, pierce: 1 },
  kernelpult: { interval: 1500, shots: 1, damage: 1, slow: 0, butterChance: .28, pierce: 1 },
  threepeater: { interval: 1450, shots: 1, damage: 1, slow: 0, rows: true, pierce: 1 },
  magnetshroom: { interval: 2600, shots: 0, damage: 0, slow: 0, utility: true },
  gatlingpea: { interval: 1550, shots: 4, damage: 1, slow: 0, pierce: 1 },
  gloomshroom: { interval: 1200, shots: 1, damage: 1, slow: 900, close: true },
};
const zombieProfiles = {
  walker: { hp: 5, speed: .020, growth: .0010, attackInterval: 1000, score: 1 },
  backup: { hp: 4, speed: .025, growth: .0008, attackInterval: 900, score: 1 },
  roadblock: { hp: 12, speed: .013, growth: .00065, attackInterval: 670, score: 3, armor: 5, barricade: true },
  conehead: { hp: 9, speed: .021, growth: .0009, attackInterval: 900, score: 2, armor: 3, cone: true },
  imp: { hp: 3, speed: .044, growth: .0011, attackInterval: 1250, score: 2, dash: true, leap: true },
  scout: { hp: 7, speed: .030, growth: .0009, attackInterval: 820, score: 4, dash: true, mark: true },
  storm: { hp: 11, speed: .016, growth: .0006, attackInterval: 740, score: 7, storm: true },
  runner: { hp: 4, speed: .036, growth: .0008, attackInterval: 1150, score: 2, dash: true },
  polevault: { hp: 10, speed: .025, growth: .0007, attackInterval: 700, score: 5, vault: true },
  bucket: { hp: 21, speed: .011, growth: .00045, attackInterval: 620, score: 5, armor: 8, bucket: true },
  football: { hp: 18, speed: .024, growth: .00055, attackInterval: 430, score: 6, armor: 5, charge: true },
  miner: { hp: 9, speed: .018, growth: .0007, attackInterval: 850, score: 5, burrow: true },
  flag: { hp: 6, speed: .027, growth: .0010, attackInterval: 900, score: 3, banner: true },
  dancer: { hp: 13, speed: .019, growth: .00055, attackInterval: 650, score: 7, summon: true },
  newspaper: { hp: 8, speed: .017, growth: .0008, attackInterval: 760, score: 4, armor: 3, enrage: true },
  gargantuar: { hp: 48, speed: .008, growth: .00035, attackInterval: 360, score: 12, armor: 8, giant: true, smash: true },
  witch: { hp: 16, speed: .014, growth: .0005, attackInterval: 800, score: 9, curse: true },
  dragon: { hp: 26, speed: .010, growth: .00035, attackInterval: 560, score: 10, armor: 2, breath: true },
  shield: { hp: 14, speed: .016, growth: .0006, attackInterval: 720, score: 6, armor: 12, guard: true },
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
  const next = card.dataset.plant;
  if ((game.seedCooldowns[next] || 0) > 0) {
    setGameStatus("game.cooldown");
    return;
  }
  if (game.shovel) {
    game.shovel = false;
    updateShovelButton();
  }
  game.selected = game.selected === next ? null : next;
  $$(".seed-card").forEach((item) => item.classList.toggle("selected", item.dataset.plant === game.selected));
  drawGame();
}
function formatGameTime(value) {
  const total = Math.max(0, Math.floor(value / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
function updateGameHud(force = true) {
  const now = performance.now();
  // HUD text is DOM work; it does not need to be synchronized with every paint.
  if (!force && now - game.hudAt < 100) return;
  game.hudAt = now;
  $("#gameSun").textContent = String(game.sun);
  $("#gameScore").textContent = String(game.score);
  $("#gameWave").textContent = `${Math.min(game.wave, MAX_WAVES)}/${MAX_WAVES}`;
  $("#gameTime").textContent = formatGameTime(game.elapsed);
  const pressure = `${t("game.threat")}: ${game.waveSpawned}/${game.waveTarget}`;
  $("#gameThreat").textContent = pressure;
  $("#gameProgressFill").style.width = `${Math.round((game.waveSpawned / Math.max(1, game.waveTarget)) * 100)}%`;
  $("#gameWaveHint").textContent = t(game.wave >= 9 ? "game.waveFinal" : game.wave >= 7 ? "game.wavePressure" : "game.waveHint");
  $("#gameMowers").textContent = String(game.mowers.filter((mower) => !mower.used).length);
  $("#gameCombo").textContent = String(game.combo || 0);
  $("#gameCombo").parentElement.classList.toggle("hot", (game.combo || 0) >= 3);
  const energy = Math.max(0, Math.min(100, Math.round(game.energy || 0)));
  const energyNode = $("#gameEnergy");
  const energyFill = $("#gameEnergyFill");
  if (energyNode) energyNode.textContent = String(energy);
  if (energyFill) energyFill.style.width = `${energy}%`;
  $$(".game-skill").forEach((button) => {
    const skill = GAME_SKILLS[button.dataset.skill];
    if (!skill) return;
    const remaining = Math.max(0, game.skillCooldowns[button.dataset.skill] || 0);
    const cooling = remaining > 0;
    const unavailable = cooling || energy < skill.cost || !game.running || game.paused;
    button.classList.toggle("cooling", cooling);
    button.classList.toggle("ready", !unavailable);
    button.classList.toggle("unaffordable", energy < skill.cost);
    button.disabled = unavailable;
    button.setAttribute("aria-disabled", String(unavailable));
    button.style.setProperty("--skill-cooldown", `${Math.ceil(remaining / 1000)}s`);
    button.title = cooling ? `${t(skill.label)} · ${Math.ceil(remaining / 1000)}s` : `${t(skill.label)} · ${energy}/${skill.cost}`;
  });
  $$(".seed-card").forEach((card) => {
    const remaining = Math.max(0, game.seedCooldowns[card.dataset.plant] || 0);
    const cooling = remaining > 0;
    const unaffordable = game.sun < (plantCost[card.dataset.plant] || Infinity);
    card.classList.toggle("cooling", cooling);
    card.classList.toggle("unaffordable", unaffordable);
    card.setAttribute("aria-disabled", String(cooling || unaffordable));
    card.style.setProperty("--seed-cooldown", `${Math.ceil(remaining / 1000)}s`);
  });
}
function activateGameSkill(type) {
  if (!game.running || game.paused) return false;
  const skill = GAME_SKILLS[type];
  if (!skill) return false;
  const remaining = Math.max(0, game.skillCooldowns[type] || 0);
  if (remaining > 0) { setGameStatus("game.skillCooldown"); return false; }
  if ((game.energy || 0) < skill.cost) { setGameStatus("game.skillNeedEnergy"); return false; }
  game.energy -= skill.cost;
  game.skillCooldowns[type] = skill.cooldown;
  const center = { x: 390, y: 230 };
  if (type === "pulse") {
    game.skillPulseFlash = 620;
    game.zombies.slice().forEach((zombie) => {
      zombie.slowTimer = Math.max(zombie.slowTimer || 0, 4200);
      zombie.flashTimer = 240;
      zombie.hp -= zombie.armor > 0 ? 2.5 : 4;
      game.impacts.push({ x: zombie.x, y: zombie.y, radius: 34, color: "#bdf8ff", life: 260, maxLife: 260 });
      if (zombie.hp <= 0) defeatZombie(zombie, "skill");
    });
    addGameParticle(center.x, center.y, "#bdf8ff", 48, .34);
    announceGame(state.locale === "zh" ? "寒冰脉冲！" : "FROST PULSE!", "#bdf8ff", 900);
    playGameSound("explode");
  } else if (type === "sun") {
    game.sun += 100;
    addGameParticle(390, 88, "#ffe17b", 34, .26);
    addGamePopup(390, 112, "+100 ☀", "#ffe17b", 1000);
    announceGame(state.locale === "zh" ? "+100 阳光" : "+100 SUN", "#ffe17b", 900);
    playGameSound("collect");
  } else {
    game.rallyTimer = 8000;
    game.skillPulseFlash = 420;
    addGameParticle(390, 230, "#f5c96b", 32, .3);
    announceGame(state.locale === "zh" ? "战线超载！" : "OVERDRIVE!", "#f5c96b", 900);
    playGameSound("wave");
  }
  updateGameHud(true);
  drawGame();
  return true;
}
function cellPosition(row, col) { return gameCellPositions[row]?.[col] || { x: gameLayout.left + col * gameLayout.cellW + 35, y: gameLayout.top + row * gameLayout.cellH + 31 }; }
function cachedCellPosition(entity) {
 const position = gameCellPositions[entity?.row]?.[entity?.col];
 return position || cellPosition(entity?.row, entity?.col);
}
function rowEntitiesWhere(kind, row, predicate) {
 const entities = rowEntities(kind, row);
 const matches = [];
 for (let index = 0; index < entities.length; index += 1) if (predicate(entities[index])) matches.push(entities[index]);
 return matches;
}
function addGameParticle(x, y, color, count = 6, speed = 0.08) {
  for (let i = 0; i < count; i += 1) game.particles.push({ x, y, vx: (Math.random() - .5) * speed, vy: (Math.random() - .7) * speed, life: 420 + Math.random() * 360, maxLife: 780, size: 2 + Math.random() * 3, color });
  if (game.particles.length > GAME_MAX_PARTICLES) game.particles.splice(0, game.particles.length - GAME_MAX_PARTICLES);
}
function addGamePopup(x, y, text, color = "#fff1b0", life = 850) {
  game.popups.push({ x, y, text, color, life, maxLife: life, vy: -.025 });
  if (game.popups.length > GAME_MAX_POPUPS) game.popups.splice(0, game.popups.length - GAME_MAX_POPUPS);
}
function announceGame(text, color = "#ffe27c", duration = 1500) {
  game.bannerText = text;
  game.bannerColor = color;
  game.bannerTimer = duration;
}
function gameWaveBanner(wave) {
  return state.locale === "zh" ? `第 ${wave} 波` : `WAVE ${wave}`;
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
      mower: { notes: [196, 294, 392], type: "sawtooth", duration: .36, step: .07, volume: .13 },
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
  game.seedCooldowns = {};
  game.skillCooldowns = {};
  game.energy = 60;
  game.rallyTimer = 0;
  game.skillPulseFlash = 0;
  game.autoSun = localStorage.getItem("minicc-game-auto-sun") !== "off";
  game.plants = [];
  game.zombies = [];
  game.defeated = [];
  game.suns = [];
  game.shots = [];
  game.particles = [];
  game.impacts = [];
  game.popups = [];
  game.mowers = Array.from({ length: gameLayout.rows }, (_, row) => ({ row, x: 57, active: false, used: false, seed: Math.random() * 1000 }));
  game.combo = 0;
  game.comboTimer = 0;
  game.bestCombo = 0;
  game.bannerTimer = 0;
  game.bannerText = "";
  game.bannerColor = "#ffe27c";
  game.dangerPulse = 0;
  game.hoverCell = null;
  game.last = 0;
  game.hudAt = 0;
  game.renderStats = { frames: 0, fps: 0, lastFrameMs: 0, maxFrameMs: 0, longFrames: 0, frameSamples: [], recentSamples: new Array(60), recentSampleIndex: 0, recentSampleCount: 0, recentLongFrames: 0, windowStartedAt: 0, windowFrames: 0, indexRebuilds: 0, rowQueries: 0, rowCandidates: 0, drawCalls: 0, plantDraws: 0, zombieDraws: 0, animationSwitches: 0 };
  resizeGameCanvas();
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
function drawSun(ctx, sun) { const pulse = 1 + Math.sin(sun.age / 230) * .08; const glow = gameRender.effects === "low" ? 0 : 18; ctx.save(); ctx.translate(sun.x, sun.y); ctx.scale(pulse, pulse); ctx.shadowColor = "rgba(255, 215, 84, .75)"; ctx.shadowBlur = glow; ctx.fillStyle = "#ffd75b"; ctx.beginPath(); ctx.arc(0, 0, 15, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = "#fff3a5"; ctx.lineWidth = 3; for (let i = 0; i < 8; i += 1) { const angle = i * Math.PI / 4; ctx.beginPath(); ctx.moveTo(Math.cos(angle) * 19, Math.sin(angle) * 19); ctx.lineTo(Math.cos(angle) * 25, Math.sin(angle) * 25); ctx.stroke(); } ctx.fillStyle = "#fff4a8"; ctx.beginPath(); ctx.arc(-4, -4, 4, 0, Math.PI * 2); ctx.fill(); ctx.restore(); }
function drawMower(ctx, mower, now) {
  if (!mower || mower.used && !mower.active) return;
  const y = cellPosition(mower.row, 0).y + 22;
  const vibration = mower.active ? Math.sin((now + mower.seed) / 34) * 1.8 : Math.sin((now + mower.seed) / 480) * .6;
  ctx.save();
  ctx.translate(mower.x, y + vibration);
  if (gameRender.effects !== "low" && mower.active) {
    ctx.shadowColor = "rgba(255, 180, 83, .72)";
    ctx.shadowBlur = 13;
  }
  ctx.fillStyle = "#c96545";
  roundedRect(ctx, -18, -13, 34, 18, 4);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = "#e9c06b";
  ctx.fillRect(-11, -25, 5, 14);
  ctx.strokeStyle = "#e9c06b";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(-8, -25);
  ctx.lineTo(6, -34);
  ctx.lineTo(12, -33);
  ctx.stroke();
  ctx.fillStyle = "#202f32";
  ctx.beginPath();
  ctx.arc(-10, 8, 6, 0, Math.PI * 2);
  ctx.arc(11, 8, 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#91a8a0";
  ctx.beginPath();
  ctx.arc(-10, 8, 2, 0, Math.PI * 2);
  ctx.arc(11, 8, 2, 0, Math.PI * 2);
  ctx.fill();
  if (mower.active) {
    ctx.fillStyle = "#ffe28a";
    ctx.beginPath();
    ctx.arc(20, -3, 3 + Math.abs(Math.sin(now / 50)) * 2, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}
function drawPlacementPreview(ctx, now) {
  const cell = game.hoverCell;
  if (!game.running || !cell || (!game.selected && !game.shovel)) return;
  const existing = game.plants.find((plant) => plant.row === cell.row && plant.col === cell.col);
  const covering = game.selected === "pumpkin" && existing && existing.type !== "pumpkin";
  const valid = game.shovel
    ? Boolean(existing)
    : Boolean(game.selected && (!existing || covering) && game.sun >= (plantCost[game.selected] || Infinity) && !(game.seedCooldowns[game.selected] > 0));
  const x = gameLayout.left + cell.col * gameLayout.cellW + 2;
  const y = gameLayout.top + cell.row * gameLayout.cellH + 2;
  ctx.save();
  ctx.fillStyle = valid ? "rgba(184, 245, 170, .18)" : "rgba(244, 120, 100, .2)";
  ctx.strokeStyle = valid ? "rgba(237, 255, 178, .9)" : "rgba(255, 145, 124, .9)";
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  roundedRect(ctx, x, y, 66, 61, 8);
  ctx.fill();
  ctx.stroke();
  ctx.setLineDash([]);
  if (!game.shovel && game.selected && valid) {
    const preview = { type: game.selected, row: cell.row, col: cell.col, hp: plantHealth[game.selected], seed: 1, age: now, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0, armed: game.selected !== "potatomine" };
    ctx.globalAlpha = .46;
    drawPlant(ctx, preview, now);
  }
  ctx.restore();
}
function drawGamePopup(ctx, popup) {
  const alpha = Math.max(0, Math.min(1, popup.life / popup.maxLife));
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.font = "700 11px DM Mono, Consolas, monospace";
  ctx.textAlign = "center";
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(22, 39, 32, .7)";
  ctx.strokeText(popup.text, popup.x, popup.y);
  ctx.fillStyle = popup.color;
  ctx.fillText(popup.text, popup.x, popup.y);
  ctx.restore();
}
function drawPlant(ctx, plant, now) {
  if (plant.type === "pumpkin" && plant.underPlant) drawPlant(ctx, plant.underPlant, now);
  const { x, y } = cellPosition(plant.row, plant.col);
  const breathe = 1 + Math.sin((now + plant.seed) / 620) * .025;
  const bob = Math.sin((now + plant.seed) / 430) * (plant.type === "spikeweed" ? .7 : 1.8);
  const leaf = (lx, ly, angle, color = "#3d9b5c") => { ctx.save(); ctx.translate(lx, ly); ctx.rotate(angle); ctx.fillStyle = color; ctx.beginPath(); ctx.ellipse(0, 0, 12, 5, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore(); };
  const stem = (height = 24, color = "#2f744d") => { ctx.strokeStyle = color; ctx.lineWidth = 5; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(0, 21); ctx.lineTo(0, 21 - height); ctx.stroke(); };
  const peaFace = (color, mouth = 10) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(0, -17, 15, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#193c32"; ctx.beginPath(); ctx.arc(10, -17, mouth, -.45, .45); ctx.fill(); ctx.fillStyle = "#f3f4ca"; ctx.beginPath(); ctx.arc(13, -17, 3, 0, Math.PI * 2); ctx.fill(); };
  ctx.save(); ctx.translate(x, y + bob); ctx.scale(breathe, breathe); ctx.fillStyle = "rgba(17, 51, 32, .3)"; ctx.beginPath(); ctx.ellipse(0, 25, 24, 7, 0, 0, Math.PI * 2); ctx.fill();
  switch (plant.type) {
    case "sunflower": stem(); leaf(-12, 13, -.45); leaf(12, 15, .45); for (let i = 0; i < 10; i += 1) { const a = i * Math.PI / 5; ctx.fillStyle = i % 2 ? "#f4b83f" : "#ffd966"; ctx.beginPath(); ctx.ellipse(Math.cos(a) * 15, -8 + Math.sin(a) * 15, 7, 13, a, 0, Math.PI * 2); ctx.fill(); } ctx.fillStyle = "#75482d"; ctx.beginPath(); ctx.arc(0, -8, 11, 0, Math.PI * 2); ctx.fill(); break;
    case "wallnut": ctx.fillStyle = "#a66a45"; ctx.beginPath(); ctx.ellipse(0, -3, 23, 29, 0, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#70452f"; ctx.lineWidth = 2; ctx.stroke(); ctx.fillStyle = "#1d302c"; ctx.beginPath(); ctx.arc(-7, -11, 2, 0, Math.PI * 2); ctx.arc(7, -11, 2, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#1d302c"; ctx.beginPath(); ctx.arc(0, -2, 8, .15, Math.PI - .15); ctx.stroke(); break;
    case "pumpkin": ctx.fillStyle = "#e27d31"; ctx.beginPath(); ctx.ellipse(0, -4, 24, 27, 0, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#a94f29"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(-9, -4, 9, 25, 0, 0, Math.PI * 2); ctx.ellipse(9, -4, 9, 25, 0, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#28352e"; ctx.beginPath(); ctx.arc(-8, -7, 4, 0, Math.PI * 2); ctx.arc(8, -7, 4, 0, Math.PI * 2); ctx.fill(); ctx.fillRect(-8, 3, 16, 3); break;
    case "cherrybomb": ctx.strokeStyle = "#4a744a"; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(0, -20); ctx.quadraticCurveTo(4, -34, 14, -36); ctx.stroke(); ctx.fillStyle = "#c94556"; ctx.beginPath(); ctx.arc(-10, -7, 14, 0, Math.PI * 2); ctx.arc(10, -7, 14, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#ffb08b"; ctx.beginPath(); ctx.arc(-14, -12, 4, 0, Math.PI * 2); ctx.arc(6, -12, 4, 0, Math.PI * 2); ctx.fill(); break;
    case "potatomine": ctx.fillStyle = "#ad844e"; ctx.beginPath(); ctx.ellipse(0, 5, 23, 16, 0, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#db5a4d"; ctx.beginPath(); ctx.arc(0, -13, 6, Math.PI, 0); ctx.fill(); ctx.fillStyle = "#2d382e"; ctx.beginPath(); ctx.arc(-8, 1, 3, 0, Math.PI * 2); ctx.arc(8, 1, 3, 0, Math.PI * 2); ctx.fill(); break;
    case "spikeweed": ctx.fillStyle = "#4f9c55"; ctx.beginPath(); ctx.moveTo(-25, 19); ctx.lineTo(-15, -6); ctx.lineTo(-7, 17); ctx.lineTo(0, -11); ctx.lineTo(8, 17); ctx.lineTo(17, -6); ctx.lineTo(25, 19); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#d8eb9c"; for (let i = -18; i <= 18; i += 9) { ctx.beginPath(); ctx.arc(i, 13, 2, 0, Math.PI * 2); ctx.fill(); } break;
    case "gloomshroom": stem(23, "#624478"); ctx.fillStyle = "#7750a0"; ctx.beginPath(); ctx.arc(0, -17, 21, Math.PI, Math.PI * 2); ctx.lineTo(17, -9); ctx.quadraticCurveTo(0, -1, -17, -9); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#d4a9ef"; ctx.beginPath(); ctx.arc(-9, -16, 3, 0, Math.PI * 2); ctx.arc(5, -21, 3, 0, Math.PI * 2); ctx.arc(12, -10, 2, 0, Math.PI * 2); ctx.fill(); break;
    case "jalapeno": ctx.fillStyle = "#ef654d"; ctx.beginPath(); ctx.moveTo(-4, 20); ctx.bezierCurveTo(-23, 5, -19, -22, 3, -28); ctx.bezierCurveTo(24, -23, 22, 9, 5, 20); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#3c824d"; ctx.fillRect(-4, -31, 9, 7); ctx.fillStyle = "#fff0b0"; ctx.beginPath(); ctx.arc(-8, -8, 3, 0, Math.PI * 2); ctx.arc(7, -8, 3, 0, Math.PI * 2); ctx.fill(); break;
    case "garlic": ctx.fillStyle = "#f1e5bc"; ctx.beginPath(); ctx.moveTo(0, -30); ctx.bezierCurveTo(-22, -23, -20, 11, 0, 20); ctx.bezierCurveTo(20, 11, 22, -23, 0, -30); ctx.fill(); ctx.strokeStyle = "#c7b886"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(0, -27); ctx.lineTo(0, 15); ctx.moveTo(-2, -22); ctx.quadraticCurveTo(-11, -4, -7, 10); ctx.moveTo(2, -22); ctx.quadraticCurveTo(11, -4, 7, 10); ctx.stroke(); break;
    case "squash": ctx.fillStyle = "#e5ad43"; ctx.beginPath(); ctx.ellipse(0, -1, 25, 17, -.1, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#9a6434"; ctx.lineWidth = 2; ctx.beginPath(); ctx.ellipse(-10, -1, 9, 16, 0, 0, Math.PI * 2); ctx.ellipse(10, -1, 9, 16, 0, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#25382e"; ctx.beginPath(); ctx.arc(-8, -4, 3, 0, Math.PI * 2); ctx.arc(8, -4, 3, 0, Math.PI * 2); ctx.fill(); break;
    case "kernelpult": stem(20); leaf(-13, 13, -.5); leaf(13, 14, .5); ctx.fillStyle = "#e8c54f"; ctx.beginPath(); ctx.ellipse(0, -18, 15, 18, -.2, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#6aa84f"; ctx.fillRect(-7, -35, 13, 5); break;
    case "magnetshroom": stem(21, "#704c80"); ctx.fillStyle = "#bd79b9"; ctx.beginPath(); ctx.arc(0, -14, 20, Math.PI, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#303a4d"; ctx.fillRect(-10, -9, 20, 5); break;
    case "icepeashooter": stem(); leaf(-12, 13, -.45, "#5da6ba"); leaf(12, 14, .45, "#5da6ba"); peaFace("#87d8e9"); ctx.strokeStyle = "#e9ffff"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(0, -17, 19, 0, Math.PI * 2); ctx.stroke(); break;
    case "firepeashooter": stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); peaFace("#e65e49"); ctx.fillStyle = "#ffbf4f"; ctx.beginPath(); ctx.moveTo(-8, -31); ctx.lineTo(0, -43); ctx.lineTo(5, -30); ctx.lineTo(13, -39); ctx.lineTo(11, -22); ctx.closePath(); ctx.fill(); break;
    case "twinpea": stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); ctx.fillStyle = "#7bc65c"; ctx.beginPath(); ctx.arc(-8, -16, 12, 0, Math.PI * 2); ctx.arc(8, -16, 12, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#193c32"; ctx.beginPath(); ctx.arc(-18, -16, 7, -.4, .4); ctx.arc(18, -16, 7, Math.PI - .4, Math.PI + .4); ctx.fill(); break;
    case "repeater": case "threepeater": case "gatlingpea": case "peashooter": stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); peaFace(plant.type === "gatlingpea" ? "#45a86b" : plant.type === "threepeater" ? "#77c979" : plant.type === "repeater" ? "#70c77b" : "#61b59d", plant.type === "gatlingpea" ? 13 : 10); if (plant.type === "threepeater") { ctx.fillStyle = "#74c979"; ctx.beginPath(); ctx.arc(-12, -13, 10, 0, Math.PI * 2); ctx.arc(12, -13, 10, 0, Math.PI * 2); ctx.fill(); } if (plant.type === "gatlingpea") { ctx.fillStyle = "#214c3e"; ctx.fillRect(5, -28, 25, 7); ctx.fillRect(5, -18, 27, 7); ctx.fillRect(5, -8, 23, 7); } break;
    default: stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); peaFace(plantColor[plant.type] || "#62b5a0");
  }
  if (plant.hp < plantHealth[plant.type]) { ctx.fillStyle = "rgba(18, 28, 24, .8)"; ctx.fillRect(-20, 30, 40, 4); ctx.fillStyle = plant.hp / plantHealth[plant.type] > .4 ? "#78d69b" : "#f6a45e"; ctx.fillRect(-20, 30, 40 * Math.max(0, plant.hp / plantHealth[plant.type]), 4); }
  ctx.restore();
}
function drawZombie(ctx, zombie, now) {
  const giant = zombie.type === "gargantuar";
  const cycle = (zombie.age || 0) + zombie.seed;
  const fast = zombie.type === "runner" || zombie.type === "imp";
  const gait = Math.sin(cycle / (fast ? 70 : 145));
  const stride = gait * (fast ? 6 : 4);
  const bob = Math.abs(gait) * (giant ? 2.4 : 1.6);
  const armSwing = Math.sin(cycle / (fast ? 70 : 145) + Math.PI) * (fast ? 8 : 5);
  const actionPulse = zombie.flashTimer > 0 ? Math.sin(now / 18) * 3 : 0;
  const skillPulse = (zombie.breathTimer > 0 && zombie.breathTimer < 520) || (zombie.smashTimer > 0 && zombie.smashTimer < 520) || (zombie.curseTimer > 0 && zombie.curseTimer < 520) || (zombie.stormTimer > 0 && zombie.stormTimer < 520) || (zombie.summonTimer > 0 && zombie.summonTimer < 520);
  const scale = giant ? 1.32 : zombie.type === "imp" ? .78 : 1;
  const body = ZOMBIE_BODY_COLORS[zombie.type] || ZOMBIE_BODY_COLORS.walker;
  ctx.save(); ctx.translate(zombie.x, zombie.y - bob + actionPulse); ctx.scale(scale, scale);
  ctx.fillStyle = "rgba(20, 27, 29, .32)"; ctx.beginPath(); ctx.ellipse(0, 27 + bob, 24 + Math.abs(stride) * .25, 7, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "#26333a"; ctx.lineWidth = 5; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(-7, 14); ctx.lineTo(-12 + stride, 30); ctx.moveTo(7, 14); ctx.lineTo(12 - stride, 30); ctx.stroke();
  ctx.strokeStyle = body; ctx.lineWidth = giant ? 6 : 4; ctx.beginPath(); ctx.moveTo(-13, 3); ctx.lineTo(-23 - armSwing, 15); ctx.moveTo(13, 3); ctx.lineTo(23 + armSwing, 15); ctx.stroke();
  if (skillPulse) { ctx.strokeStyle = zombie.type === "dragon" ? "rgba(255,145,84,.72)" : "rgba(195,168,255,.62)"; ctx.lineWidth = 2; ctx.globalAlpha = .45 + Math.abs(Math.sin(now / 90)) * .4; ctx.beginPath(); ctx.arc(0, -8, 28 + Math.abs(gait) * 4, 0, Math.PI * 2); ctx.stroke(); ctx.globalAlpha = 1; }
  ctx.fillStyle = body; roundedRect(ctx, -16, -1, giant ? 34 : 31, 27, 8); ctx.fill(); ctx.fillStyle = zombie.flashTimer > 0 ? "#fff7d7" : "#b9c7a9"; ctx.beginPath(); ctx.arc(0, -17, giant ? 18 : 15, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#29303d"; ctx.beginPath(); ctx.arc(-5, -18, 3, 0, Math.PI * 2); ctx.arc(6, -18, 3, 0, Math.PI * 2); ctx.fill();
  if (zombie.type === "roadblock") { ctx.fillStyle = "#efbd62"; ctx.fillRect(-20, -33, 40, 7); ctx.fillStyle = "#b95942"; ctx.fillRect(-15, -38, 30, 5); } if (zombie.type === "bucket") { ctx.fillStyle = "#aab4bd"; ctx.fillRect(-18, -34, 36, 16); ctx.fillStyle = "#65717d"; ctx.fillRect(-21, -20, 42, 4); } if (zombie.type === "conehead") { ctx.fillStyle = "#eb873e"; ctx.beginPath(); ctx.moveTo(0, -48); ctx.lineTo(-15, -27); ctx.lineTo(15, -27); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#f4c15f"; ctx.fillRect(-17, -29, 34, 5); } if (zombie.type === "football") { ctx.fillStyle = "#c76c50"; ctx.beginPath(); ctx.ellipse(0, -33, 21, 8, 0, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#dbe4ed"; ctx.fillRect(-14, -35, 28, 3); } if (zombie.type === "miner") { ctx.fillStyle = "#d59c3d"; ctx.beginPath(); ctx.arc(0, -32, 18, Math.PI, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#fff0a0"; ctx.beginPath(); ctx.arc(0, -37, 5, 0, Math.PI * 2); ctx.fill(); } if (zombie.type === "flag") { ctx.strokeStyle = "#e0b26e"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(17, 16); ctx.lineTo(17, -40); ctx.stroke(); ctx.fillStyle = "#ef786c"; ctx.beginPath(); ctx.moveTo(18, -39); ctx.lineTo(36, -32); ctx.lineTo(18, -25); ctx.fill(); } if (zombie.type === "polevault") { ctx.strokeStyle = "#dfad70"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-20, 20); ctx.lineTo(23, -40); ctx.stroke(); } if (zombie.type === "dancer") { ctx.strokeStyle = "#f2c2dd"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-17, 4); ctx.lineTo(-31, -12); ctx.moveTo(17, 4); ctx.lineTo(31, -12); ctx.stroke(); } if (zombie.type === "newspaper") { ctx.fillStyle = "#f4e2b0"; ctx.fillRect(-24, -3, 15, 20); } if (zombie.type === "witch") { ctx.fillStyle = "#30233d"; ctx.beginPath(); ctx.moveTo(-19, -29); ctx.lineTo(0, -53); ctx.lineTo(19, -29); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#dcb5ff"; ctx.beginPath(); ctx.arc(0, -32, 5, 0, Math.PI * 2); ctx.fill(); } if (zombie.type === "dragon") { ctx.fillStyle = "#d49b50"; ctx.beginPath(); ctx.moveTo(-18, -2); ctx.lineTo(-34, -18); ctx.lineTo(-25, 6); ctx.lineTo(-15, 7); ctx.moveTo(18, -2); ctx.lineTo(34, -18); ctx.lineTo(25, 6); ctx.lineTo(15, 7); ctx.fill(); } if (zombie.type === "gargantuar") { ctx.fillStyle = "#b8c4d1"; ctx.fillRect(17, -2, 8, 31); ctx.fillStyle = "#d99a5e"; ctx.beginPath(); ctx.arc(21, 31, 9, 0, Math.PI * 2); ctx.fill(); }
  if (zombie.slowTimer > 0) { ctx.strokeStyle = "#a7e8f3"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(0, -3, 25, 0, Math.PI * 2); ctx.stroke(); } if (zombie.armor > 0) { ctx.strokeStyle = "#e4c36b"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(0, -17, 20, Math.PI, Math.PI * 2); ctx.stroke(); } if (zombie.hp < zombie.maxHp) { ctx.fillStyle = "rgba(25, 33, 26, .8)"; ctx.fillRect(-21, 35, 42, 4); ctx.fillStyle = zombie.armor > 0 ? "#e9c66a" : "#e48374"; ctx.fillRect(-21, 35, 42 * Math.max(0, zombie.hp / zombie.maxHp), 4); }
  ctx.restore();
}
function drawShot(ctx, shot, now) {
  const bob = shot.kind === "kernel" ? Math.sin((now + shot.seed) / 80) * 3 : 0;
  ctx.save();
  ctx.translate(shot.x, shot.y + bob);
  ctx.rotate(shot.angle || 0);
  ctx.globalAlpha = .3;
  ctx.strokeStyle = shot.color;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(-Math.min(30, shot.distance || 12), 0);
  ctx.lineTo(-5, 0);
  ctx.stroke();
  ctx.globalAlpha = 1;
  if (gameRender.effects !== "low") {
    ctx.shadowColor = shot.glow || shot.color;
    ctx.shadowBlur = shot.kind === "fire" ? 18 : 11;
  }
  ctx.fillStyle = shot.color;
  if (shot.kind === "kernel") ctx.fillRect(-7, -5, 13, 10);
  else if (shot.kind === "ice") {
    ctx.beginPath(); ctx.moveTo(8, 0); ctx.lineTo(0, -8); ctx.lineTo(-8, 0); ctx.lineTo(0, 8); ctx.closePath(); ctx.fill();
  } else {
    ctx.beginPath(); ctx.arc(0, 0, shot.kind === "fire" ? 7 : 6, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}
function drawImpact(ctx, impact) { const progress = 1 - impact.life / impact.maxLife; const radius = impact.radius * (.35 + progress * .9); ctx.save(); ctx.globalAlpha = Math.max(0, impact.life / impact.maxLife); ctx.strokeStyle = impact.color; ctx.lineWidth = Math.max(1, 4 - progress * 3); ctx.beginPath(); ctx.arc(impact.x, impact.y, radius, 0, Math.PI * 2); ctx.stroke(); ctx.restore(); }
function drawGame() {
  if (!gameRender.ctx || !gameRender.background) resizeGameCanvas();
  const canvas = gameRender.canvas;
  const ctx = gameRender.ctx;
  if (!canvas || !ctx || !gameRender.background) return;
  const startedAt = performance.now();
  const now = startedAt;
  ctx.drawImage(gameRender.background, 0, 0);
  ctx.fillStyle = "#a8d5a1";
  ctx.font = "10px DM Mono, monospace";
  ctx.fillText(game.running ? "DEFEND THE LAWN" : "READY FOR BATTLE", 18, 42);
  game.suns.forEach((sun) => drawSun(ctx, sun));
  game.plants.forEach((plant) => drawPlant(ctx, plant, now));
  game.shots.forEach((shot) => drawShot(ctx, shot, now));
  game.zombies.forEach((zombie) => drawZombie(ctx, zombie, now));
  // The mower is a foreground lane object, so it visibly passes over zombies.
  game.mowers.forEach((mower) => drawMower(ctx, mower, now));
  game.impacts.forEach((impact) => drawImpact(ctx, impact));
  const particleStride = gameRender.effects === "low" ? 2 : 1;
  for (let index = 0; index < game.particles.length; index += particleStride) {
    const particle = game.particles[index];
    ctx.globalAlpha = Math.max(0, particle.life / particle.maxLife);
    ctx.fillStyle = particle.color;
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  drawPlacementPreview(ctx, now);
  game.popups.forEach((popup) => drawGamePopup(ctx, popup));
  if (game.bannerTimer > 0 && game.bannerText) {
    const alpha = Math.min(1, game.bannerTimer / 260);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(23, 42, 40, .88)";
    roundedRect(ctx, 250, 10, 220, 34, 9);
    ctx.fill();
    ctx.strokeStyle = game.bannerColor;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = game.bannerColor;
    ctx.font = "700 12px DM Mono, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.fillText(game.bannerText, 360, 32);
    ctx.restore();
  }
  if (game.dangerPulse > 0) {
    ctx.save();
    const alpha = .16 + Math.abs(Math.sin(now / 85)) * .18;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "#ef725f";
    ctx.fillRect(0, 60, 65, GAME_LOGICAL_HEIGHT - 60);
    ctx.strokeStyle = "#ff9a77";
    ctx.lineWidth = 3;
    ctx.strokeRect(4, 64, 56, GAME_LOGICAL_HEIGHT - 69);
    ctx.restore();
  }
  if (game.skillPulseFlash > 0) {
    ctx.save();
    const pulseAlpha = Math.min(.34, game.skillPulseFlash / 620 * .34);
    ctx.globalAlpha = pulseAlpha;
    ctx.fillStyle = game.rallyTimer > 0 ? "#f5c96b" : "#bdf8ff";
    ctx.fillRect(68, 58, GAME_LOGICAL_WIDTH - 68, GAME_LOGICAL_HEIGHT - 58);
    ctx.globalAlpha = Math.min(.8, pulseAlpha * 2.4);
    ctx.strokeStyle = game.rallyTimer > 0 ? "#ffe49a" : "#d9fbff";
    ctx.lineWidth = 4;
    ctx.strokeRect(72, 62, GAME_LOGICAL_WIDTH - 78, GAME_LOGICAL_HEIGHT - 68);
    ctx.restore();
  }
  recordGameFrame(now, startedAt);
}
function zombieTypeForWave() {
  const roll = Math.random();
  const pressure = game.difficulty === "nightmare" ? 1.25 : game.difficulty === "normal" ? .82 : 1;
  const nightmare = game.difficulty === "nightmare";
  const choices = [
    [10, Math.min(.18, .07 + (game.wave - 9) * .035) * pressure, "gargantuar"],
    [8, Math.min(.18, (.035 + game.wave * .012) * pressure), "dragon"],
    [7, Math.min(.22, (.04 + game.wave * .014) * pressure), "witch"],
    [6, Math.min(.24, (.05 + game.wave * .016) * pressure), "shield"],
    [3, Math.min(.24, (.04 + game.wave * .012) * pressure), "conehead"],
    [2, Math.min(.28, (.07 + game.wave * .016) * pressure), "imp"],
    [4, Math.min(.18, (.025 + game.wave * .011) * pressure), "scout"],
    [6, Math.min(.16, (.02 + game.wave * .009) * pressure), "storm"],
    [4, Math.min(.20, (.05 + game.wave * .01) * pressure), "newspaper"],
    [7, Math.min(.16, (.025 + game.wave * .01) * pressure), "dancer"],
    [5, Math.min(.30, (.045 + game.wave * .018) * pressure), "football"],
    [4, Math.min(.22, (.04 + game.wave * .014) * pressure), "polevault"],
    [4, Math.min(.25, (.035 + game.wave * .014) * pressure), "miner"],
    [3, Math.min(.22, (.045 + game.wave * .01) * pressure), "flag"],
    [3, Math.min(.38, (.11 + game.wave * .014) * pressure), "bucket"],
    [2, Math.min(.52, (.25 + game.wave * .018) * pressure), "runner"],
    [2, Math.min(.82, (.42 + game.wave * .022) * pressure), "roadblock"],
  ];
  if (nightmare && game.wave >= 6 && game.waveSpawned % 5 === 4) return ["shield", "witch", "dragon", "gargantuar"][game.wave % 4];
  let threshold = 0;
  for (const [minimumWave, chance, type] of choices) {
    if (game.wave < minimumWave) continue;
    threshold += chance;
    if (roll < threshold) return type;
  }
  return "walker";
}
function spawnZombie() {
  if (game.waveSpawned >= game.waveTarget) return;
  const row = Math.floor(Math.random() * gameLayout.rows);
  const type = zombieTypeForWave();
  const profile = zombieProfiles[type];
  const difficulty = gameDifficulty();
  const hpGrowth = type === "gargantuar" ? 2.2 : type === "dragon" ? 1.55 : type === "witch" ? 1.2 : type === "shield" ? 1.25 : type === "football" ? 1.35 : type === "bucket" ? 1.2 : type === "miner" ? 1 : type === "roadblock" ? .85 : .7;
  const nightmareElite = game.difficulty === "nightmare" && game.wave >= 6 && ["dragon", "witch", "shield", "football", "gargantuar"].includes(type);
  const hp = Math.max(1, Math.round((profile.hp + Math.floor(game.wave * hpGrowth)) * difficulty.hpMultiplier * (nightmareElite ? 1.18 : 1)));
  game.zombies.push({
    x: 704,
    y: cellPosition(row, 0).y,
    row,
    hp,
    maxHp: hp,
    armor: profile.armor || 0,
    type,
    speed: (profile.speed + game.wave * profile.growth) * difficulty.speedMultiplier,
    attackInterval: profile.attackInterval,
    slowTimer: 0,
    burrowTimer: profile.burrow ? 1000 : 0,
    seed: Math.random() * 1000,
    age: 0,
    garlicTimer: 0,
    vaultTimer: 0,
    summonTimer: 0,
    flashTimer: 0,
    dashTimer: 0,
    leapTimer: 0,
    chargeTimer: 0,
    curseTimer: 0,
    breathTimer: 0,
    smashTimer: 0,
    armorTimer: 0,
    guardTimer: 0,
    burnTimer: 0,
    burnTickTimer: 0,
    stormTimer: 0,
    markTimer: 0,
    elite: nightmareElite,
  });
  game.waveSpawned += 1;
  game.totalSpawned += 1;
  if (game.wave > 1 && game.waveSpawned === 1) setGameStatus("game.running");
  if (game.waveSpawned === game.waveTarget) {
    playGameSound("wave");
    addGameParticle(360, 60, "#ffe27c", 18, .18);
  }
  updateGameHud(true);
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
  updateGameHud(true);
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
  const position = cachedCellPosition(plant);
  const rows = profile.rows ? [plant.row, plant.row - 1, plant.row + 1].filter((row) => row >= 0 && row < gameLayout.rows) : [plant.row];
  rows.forEach((row) => {
    const shotY = gameCellPositions[row]?.[plant.col]?.y || cellPosition(row, plant.col).y;
    for (let index = 0; index < profile.shots; index += 1) {
      game.shots.push({ x: position.x + 20 + index * 8, y: shotY - 5, row, damage: profile.damage, slow: profile.slow, fire: Boolean(profile.fire), burn: profile.burn || 0, burnDamage: profile.burnDamage || 0, butter: profile.butterChance ? Math.random() < profile.butterChance : false, kind: profile.fire ? "fire" : plant.type === "icepeashooter" ? "ice" : plant.type === "kernelpult" ? "kernel" : "pea", glow: profile.fire ? "#ffb347" : profile.slow ? "#bdf8ff" : "#80ed9a", color: plant.type === "icepeashooter" ? "#c9f6ff" : plant.type === "firepeashooter" ? "#ff815f" : plant.type === "kernelpult" ? "#f3cf63" : "#b5f0a2", angle: profile.fire ? -.12 : 0, seed: Math.random() * 1000, hitsLeft: 1 + (profile.pierce || 0), hitTargets: [], hit: false });
    }
  });
  playGameSound("shoot");
}
function explodeCherryBomb(plant) {
  const position = cachedCellPosition(plant);
  // Bombs can be triggered immediately after a click, before the next frame
  // rebuilds the row index. Read the authoritative array for this one-shot.
  const defeated = game.zombies.filter((zombie) => zombie.row === plant.row && Math.abs(zombie.x - position.x) < 145);
  defeated.forEach((zombie) => defeatZombie(zombie));
  removeGamePlant(plant);
  addGameParticle(position.x, position.y - 5, "#ff8d73", 34, .3);
  playGameSound("explode");
  updateGameHud();
}
function defeatZombie(zombie, source = "combat") {
  if (!zombie || zombie.defeated) return false;
  zombie.defeated = true;
  const index = game.zombies.indexOf(zombie);
  if (index >= 0) {
    removeRowEntity("zombies", zombie);
    game.zombies.splice(index, 1);
  }
  const points = zombieProfiles[zombie.type]?.score || 1;
  game.score += points;
  game.energy = Math.min(100, (game.energy || 0) + (source === "skill" ? 1 : 4));
  game.defeated.push({ type: zombie.type || "walker", points, source, at: game.elapsed });
  if (game.defeated.length > 64) game.defeated.splice(0, game.defeated.length - 64);
  game.combo = game.comboTimer > 0 ? game.combo + 1 : 1;
  game.comboTimer = GAME_COMBO_WINDOW;
  game.bestCombo = Math.max(game.bestCombo, game.combo);
  const x = Number.isFinite(zombie.x) ? zombie.x : cellPosition(zombie.row, 0).x;
  const y = Number.isFinite(zombie.y) ? zombie.y : cellPosition(zombie.row, 0).y;
  const comboText = game.combo > 1
    ? (state.locale === "zh" ? `+${points} · ${game.combo} 连击` : `+${points} · x${game.combo}`)
    : `+${points}`;
  addGamePopup(Math.max(78, Math.min(GAME_LOGICAL_WIDTH - 20, x)), y - 35, comboText, source === "mower" ? "#ffcf70" : "#fff1b0");
  if (source === "mower") addGamePopup(Math.max(78, Math.min(GAME_LOGICAL_WIDTH - 20, x)), y - 52, state.locale === "zh" ? "防线车" : "MOWER", "#ff9b70", 650);
  if (game.combo >= 3 && (game.combo === 3 || game.combo % 5 === 0)) {
    announceGame(state.locale === "zh" ? `${game.combo} 连击` : `${game.combo} COMBO`, "#ffcf70", 900);
  }
  updateGameHud(false);
  return true;
}
function triggerMower(mower) {
  if (!mower || mower.used || mower.active) return false;
  mower.used = true;
  mower.active = true;
  mower.x = 57;
  game.dangerPulse = Math.max(game.dangerPulse, 700);
  announceGame(state.locale === "zh" ? `${mower.row + 1} 行防线车出动` : `LANE ${mower.row + 1} MOWER`, "#ffb16c", 1200);
  addGameParticle(mower.x + 12, cellPosition(mower.row, 0).y + 18, "#ffb16c", 16, .22);
  playGameSound("mower");
  updateGameHud(false);
  return true;
}
function updateMowers(dt) {
  for (const mower of game.mowers) {
    if (!mower || mower.row < 0 || mower.row >= gameLayout.rows) continue;
    if (!mower.used && !mower.active && anyRowEntity("zombies", mower.row, (zombie) => !zombie.defeated && zombie.x < GAME_MOWER_TRIGGER_X)) {
      triggerMower(mower);
    }
    if (!mower.active) continue;
    mower.x += GAME_MOWER_SPEED * dt;
    const caught = rowEntitiesWhere(
      "zombies",
      mower.row,
      (zombie) => !zombie.defeated && zombie.x >= 0 && zombie.x <= mower.x + GAME_MOWER_CLEAR_RADIUS,
    );
    caught.forEach((zombie) => defeatZombie(zombie, "mower"));
    if (mower.x >= GAME_MOWER_EXIT_X) {
      mower.active = false;
      mower.x = GAME_MOWER_EXIT_X;
      addGamePopup(GAME_LOGICAL_WIDTH - 70, cellPosition(mower.row, 0).y - 12, state.locale === "zh" ? "已清场" : "CLEAR", "#9fe0b4", 700);
    }
  }
}
function updateGameEffects(dt) {
  const comboWasActive = game.comboTimer > 0;
  game.comboTimer = Math.max(0, game.comboTimer - dt);
  if (comboWasActive && game.comboTimer === 0) {
    game.combo = 0;
    updateGameHud(false);
  }
  game.bannerTimer = Math.max(0, game.bannerTimer - dt);
  game.dangerPulse = Math.max(0, game.dangerPulse - dt);
  game.skillPulseFlash = Math.max(0, (game.skillPulseFlash || 0) - dt);
  let alive = 0;
  for (const popup of game.popups) {
    popup.life -= dt;
    popup.y += (popup.vy || 0) * dt;
    popup.vy = (popup.vy || 0) - .000015 * dt;
    if (popup.life > 0) game.popups[alive++] = popup;
  }
  game.popups.length = alive;
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
  announceGame(gameWaveBanner(game.wave), "#ffe27c", 1650);
  playGameSound("wave");
  addGameParticle(360, 60, "#ffe27c", 18, .18);
  updateGameHud();
  return false;
}
function plantContainer(plant) {
  const entities = rowEntities("plants", plant?.row);
  for (let index = 0; index < entities.length; index += 1) {
    const candidate = entities[index];
    if (candidate === plant || candidate.underPlant === plant) return candidate;
  }
  // A click may add or replace a plant between animation frames. Fall back to
  // the authoritative list instead of treating that plant as nonexistent.
  return game.plants.find((candidate) => candidate === plant || candidate.underPlant === plant) || null;
}
function removeGamePlant(plant) {
  const container = plantContainer(plant);
  if (!container) return false;
  if (container === plant) {
    const index = game.plants.indexOf(container);
    if (index < 0) return false;
    const replacement = container.underPlant || null;
    removeRowEntity("plants", container);
    if (replacement) {
      game.plants.splice(index, 1, replacement);
      rowEntities("plants", replacement.row).push(replacement);
    } else game.plants.splice(index, 1);
  } else {
    container.underPlant = null;
  }
  return true;
}
function damagePlant(plant, amount, color = "#c78363") {
  const container = plant && plantContainer(plant);
  if (!container) return false;
  const target = container.type === "pumpkin" ? container : plant;
  const effectiveAmount = target.type === "pumpkin" ? amount * .5 : amount;
  target.hp -= effectiveAmount;
  const position = cellPosition(target.row, target.col);
  addGameParticle(position.x, position.y - 8, color, 4, .1);
  if (target.hp > 0) return false;
  removeGamePlant(target);
  addGameParticle(position.x, position.y, color, 12, .16);
  return true;
}
function curseNearestPlant(zombie, duration = 3000) {
  const plants = rowEntities("plants", zombie.row);
  let target = null;
  let targetX = -Infinity;
  for (let index = 0; index < plants.length; index += 1) {
    const plant = plants[index];
    const position = cachedCellPosition(plant);
    if (position.x < zombie.x && position.x > targetX) { target = plant; targetX = position.x; }
  }
  if (!target) return false;
  target.disabledTimer = Math.max(target.disabledTimer || 0, duration);
  const position = cachedCellPosition(target);
  addGameParticle(position.x, position.y - 24, "#c99be8", 14, .14);
  return true;
}
function gameLoop(now = 0) {
  if (!game.running || game.paused) return;
  const dt = Math.min(80, Math.max(8, now - game.last || 16));
  rebuildGameIndexes();
  game.last = now;
  game.elapsed += dt;
  updateGameEffects(dt);
  game.rallyTimer = Math.max(0, (game.rallyTimer || 0) - dt);
  for (const type of Object.keys(GAME_SKILLS)) {
    if (game.skillCooldowns[type] > 0) game.skillCooldowns[type] = Math.max(0, game.skillCooldowns[type] - dt);
  }
  for (const type of PLANT_TYPES) {
    if (game.seedCooldowns[type] > 0) game.seedCooldowns[type] = Math.max(0, game.seedCooldowns[type] - dt);
  }
  updateGameHud(false);
  game.spawnTimer += dt;
  game.skyTimer += dt;
  game.dangerTimer += dt;
  const nearHouse = anyIndexedEntity("zombies", (zombie) => !zombie.defeated && zombie.x < 165);
  if (nearHouse) game.dangerPulse = Math.max(game.dangerPulse, 260);
  if (nearHouse && game.dangerTimer > 850) {
    game.dangerTimer = 0;
    playGameSound("danger");
  } else if (!nearHouse) {
    game.dangerPulse = Math.max(0, game.dangerPulse - dt);
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
  const plantsThisFrame = game._plantsFrame || (game._plantsFrame = []);
  plantsThisFrame.length = 0;
  game.plants.forEach((plant) => {
    plantsThisFrame.push(plant);
    if (plant.underPlant) plantsThisFrame.push(plant.underPlant);
  });
  plantsThisFrame.forEach((plant) => {
    if (!plantContainer(plant)) return;
    plant.age += dt;
    plant.disabledTimer = Math.max(0, (plant.disabledTimer || 0) - dt);
    if (plant.disabledTimer > 0) return;
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
    if (plant.type === "jalapeno") {
      plant.bombTimer += dt;
      if (plant.bombTimer > 850) {
        const position = cachedCellPosition(plant);
        forEachRowEntity("zombies", plant.row, (zombie) => defeatZombie(zombie));
        removeGamePlant(plant);
        addGameParticle(position.x + 180, position.y, "#ff784e", 40, .35);
        playGameSound("explode");
        updateGameHud();
      }
      return;
    }
    if (plant.type === "potatomine") {
      plant.bombTimer += dt;
      if (!plant.armed && plant.bombTimer >= 1800) {
        plant.armed = true;
        addGameParticle(cellPosition(plant.row, plant.col).x, cellPosition(plant.row, plant.col).y - 18, "#e7c875", 8, .08);
      }
      const target = plant.armed && game.zombies.find((zombie) => zombie.row === plant.row && zombie.x < cellPosition(plant.row, plant.col).x + 30);
      if (target) {
        game.zombies.filter((zombie) => zombie.row === plant.row && Math.abs(zombie.x - target.x) < 90).forEach((zombie) => defeatZombie(zombie));
        removeGamePlant(plant);
        addGameParticle(cellPosition(plant.row, plant.col).x, cellPosition(plant.row, plant.col).y, "#e7c875", 26, .25);
        playGameSound("explode");
        updateGameHud();
      }
      return;
    }
    if (plant.type === "spikeweed") {
      plant.shotTimer += dt;
      const position = cellPosition(plant.row, plant.col);
      const target = game.zombies.find((zombie) => zombie.row === plant.row && Math.abs(zombie.x - position.x) < 44);
      if (target) { target.hp -= dt / 720; if (target.hp <= 0) { defeatZombie(target); updateGameHud(); } }
    }
    if (plant.type === "gloomshroom") {
      plant.shotTimer += dt;
      const position = cellPosition(plant.row, plant.col);
      if (plant.shotTimer > 1050) { plant.shotTimer = 0; const targets = game.zombies.filter((zombie) => Math.abs(zombie.row - plant.row) <= 1 && Math.hypot(zombie.x - position.x, (zombie.row - plant.row) * gameLayout.cellH) < 140); targets.forEach((target) => { target.hp -= 1; addGameParticle(target.x, target.y - 12, "#c79be8", 4, .1); if (target.hp <= 0) defeatZombie(target); }); if (targets.length) playGameSound("shoot"); }
      return;
    }
    if (plant.type === "pumpkin") return;
    if (plant.type === "squash") {
      plant.bombTimer += dt;
      const position = cellPosition(plant.row, plant.col);
      const target = game.zombies.find((zombie) => zombie.row === plant.row && zombie.x > position.x - 82 && zombie.x < position.x + 130);
      if (plant.bombTimer > 450 && target) { defeatZombie(target); removeGamePlant(plant); addGameParticle(target.x, target.y, "#f0b653", 28, .28); playGameSound("explode"); updateGameHud(); }
      return;
    }
    const profile = plantProfiles[plant.type];
    if (!profile) return;
    plant.shotTimer += dt;
    const position = cellPosition(plant.row, plant.col);
    const rowThreat = profile.rows
      ? anyRowEntity("zombies", plant.row, (zombie) => zombie.x > position.x)
        || (plant.row > 0 && anyRowEntity("zombies", plant.row - 1, (zombie) => zombie.x > position.x))
        || (plant.row + 1 < gameLayout.rows && anyRowEntity("zombies", plant.row + 1, (zombie) => zombie.x > position.x))
      : anyRowEntity("zombies", plant.row, (zombie) => zombie.x > position.x);
    const fireInterval = profile.interval * (game.rallyTimer > 0 ? .55 : 1);
    if (plant.shotTimer > fireInterval && rowThreat) {
      plant.shotTimer = 0;
      if (profile.utility) {
        const armored = firstRowEntity("zombies", plant.row, (zombie) => zombie.x > position.x && zombie.armor > 0);
        if (armored) {
          armored.armor = 0;
          armored.hp = Math.max(1, armored.hp - 2);
          addGameParticle(armored.x, armored.y - 20, "#dcb7ff", 15, .15);
          playGameSound("hit");
        }
      } else firePlantShots(plant, profile);
    }
  });
  game.flagRows.fill(0);
  game.zombies.forEach((zombie) => { if (zombie.type === "flag") game.flagRows[zombie.row] = 1; });
  const zombiesThisFrame = game._zombiesFrame || (game._zombiesFrame = []);
  zombiesThisFrame.length = 0;
  zombiesThisFrame.push(...game.zombies);
  zombiesThisFrame.forEach((zombie) => {
    zombie.y = cellPosition(zombie.row, 0).y;
    zombie.age = (zombie.age || 0) + dt;
    zombie.slowTimer = Math.max(0, zombie.slowTimer - dt);
    zombie.flashTimer = Math.max(0, (zombie.flashTimer || 0) - dt);
    if (zombie.burrowTimer > 0) zombie.burrowTimer -= dt;
    const burrowed = zombie.type === "miner" && zombie.burrowTimer > 0;
    zombie.garlicTimer = Math.max(0, (zombie.garlicTimer || 0) - dt);
    zombie.dashTimer = Math.max(0, (zombie.dashTimer || 0) - dt);
    zombie.leapTimer = Math.max(0, (zombie.leapTimer || 0) - dt);
    zombie.chargeTimer = Math.max(0, (zombie.chargeTimer || 0) - dt);
    zombie.curseTimer = Math.max(0, (zombie.curseTimer || 0) - dt);
    zombie.breathTimer = Math.max(0, (zombie.breathTimer || 0) - dt);
    zombie.smashTimer = Math.max(0, (zombie.smashTimer || 0) - dt);
    zombie.armorTimer = Math.max(0, (zombie.armorTimer || 0) - dt);
    zombie.guardTimer = Math.max(0, (zombie.guardTimer || 0) - dt);
    zombie.stormTimer = Math.max(0, (zombie.stormTimer || 0) - dt);
    zombie.markTimer = Math.max(0, (zombie.markTimer || 0) - dt);
    zombie.burnTimer = Math.max(0, (zombie.burnTimer || 0) - dt);
    zombie.burnTickTimer = Math.max(0, (zombie.burnTickTimer || 0) - dt);
    if (zombie.burnTimer > 0 && zombie.burnTickTimer <= 0) {
      zombie.burnTickTimer = 500;
      zombie.hp -= Math.max(1, zombie.burnDamage || 1);
      addGameParticle(zombie.x, zombie.y - 18, "#ff815f", 4, .08);
      if (zombie.hp <= 0) { defeatZombie(zombie); updateGameHud(); return; }
    }
    if (["runner", "imp", "scout"].includes(zombie.type) && zombie.dashTimer <= 0 && zombie.x < 650) {
      zombie.dashTimer = zombie.type === "imp" ? 2100 : 3000;
      zombie.x += zombie.type === "imp" ? 38 : 28;
      zombie.flashTimer = 140;
      addGameParticle(zombie.x, zombie.y - 22, zombie.type === "scout" ? "#f5cf63" : "#e57b70", 8, .14);
    }
    if (zombie.type === "football" && zombie.chargeTimer <= 0) {
      zombie.chargeTimer = 3000;
      zombie.flashTimer = 160;
      addGameParticle(zombie.x, zombie.y - 20, "#d56c58", 8, .13);
    }
    if (zombie.type === "witch" && zombie.curseTimer <= 0) {
      zombie.curseTimer = 4300;
      curseNearestPlant(zombie, zombie.elite ? 4200 : 3000);
    }
    if (zombie.type === "dragon" && zombie.breathTimer <= 0) {
      zombie.breathTimer = 3600;
      game.plants.filter((plant) => plant.row === zombie.row && cellPosition(plant.row, plant.col).x < zombie.x + 20).forEach((plant) => damagePlant(plant, zombie.elite ? 3 : 2, "#ff815f"));
      addGameParticle(zombie.x - 34, zombie.y - 12, "#ff9b5f", 18, .22);
    }
    if (zombie.type === "shield" && zombie.armorTimer <= 0) {
      zombie.armorTimer = 4200;
      zombie.armor = Math.min(zombieProfiles.shield.armor, zombie.armor + (zombie.elite ? 5 : 3));
      addGameParticle(zombie.x, zombie.y - 24, "#9bdcf5", 12, .14);
    }
    if (zombie.type === "storm" && zombie.stormTimer <= 0) {
      zombie.stormTimer = 4000;
      game.plants.filter((plant) => plant.row === zombie.row).forEach((plant) => { plant.disabledTimer = Math.max(plant.disabledTimer || 0, 1200); });
      addGameParticle(zombie.x - 24, zombie.y - 28, "#a9c8e8", 20, .2);
    }
    if (zombie.type === "scout" && zombie.markTimer <= 0) {
      zombie.markTimer = 3500;
      curseNearestPlant(zombie, 1400);
    }
    if (zombie.type === "dancer") { zombie.summonTimer += dt; if (zombie.summonTimer > 4200) { zombie.summonTimer = 0; const allyRow = (zombie.row + 1) % gameLayout.rows; const ally = zombieProfiles.backup; game.zombies.push({ x: zombie.x + 34, y: cellPosition(allyRow, 0).y, row: allyRow, hp: ally.hp, maxHp: ally.hp, armor: 0, type: "backup", speed: ally.speed, attackInterval: ally.attackInterval, slowTimer: 0, burrowTimer: 0, seed: Math.random() * 1000, garlicTimer: 0, vaultTimer: 0, summonTimer: 0, flashTimer: 0 }); addGameParticle(zombie.x, zombie.y - 28, "#ef7892", 16, .18); playGameSound("wave"); } }
    const blocker = burrowed ? null : game.plants.find((plant) => plant.type !== "spikeweed" && plant.row === zombie.row && Math.abs(cellPosition(plant.row, plant.col).x - zombie.x) < 30);
    if (zombie.type === "imp" && blocker && zombie.leapTimer <= 0) { zombie.x = cellPosition(blocker.row, blocker.col).x - 44; zombie.leapTimer = 1800; addGameParticle(zombie.x, zombie.y - 25, "#e57b70", 12, .16); return; }
    if (blocker?.type === "spikeweed") { zombie.hp -= dt / 720; if (zombie.hp <= 0) { defeatZombie(zombie); updateGameHud(); return; } }
    if (zombie.type === "polevault" && blocker && !zombie.vaultTimer) { zombie.x = cellPosition(blocker.row, blocker.col).x - 44; zombie.vaultTimer = 1; addGameParticle(zombie.x, zombie.y - 25, "#d5a15e", 12, .16); return; }
    if (blocker?.type === "garlic" && zombie.garlicTimer <= 0) { zombie.row = (zombie.row + 1) % gameLayout.rows; zombie.x += 22; zombie.garlicTimer = 3200; addGameParticle(zombie.x, zombie.y, "#f3e1b4", 14, .16); playGameSound("hit"); return; }
    if (zombie.type === "gargantuar" && blocker && zombie.smashTimer <= 0) {
      zombie.smashTimer = zombie.elite ? 2200 : 3000;
      damagePlant(blocker, zombie.elite ? 10 : 7, "#d99a5e");
      addGameParticle(zombie.x, zombie.y - 20, "#d99a5e", 18, .22);
      playGameSound("explode");
      return;
    }
    if (blocker) {
      if (damagePlant(blocker, dt / zombie.attackInterval)) playGameSound("hit");
    } else {
      const bannerBoost = game.flagRows[zombie.row] ? 1.18 : 1;
      const enragedBoost = zombie.type === "newspaper" && zombie.armor <= 0 ? 1.65 : 1;
      const dashBoost = ["runner", "imp", "scout"].includes(zombie.type) && zombie.dashTimer > 0 ? (zombie.type === "imp" ? 1.45 : 1.3) : 1;
      const chargeBoost = zombie.type === "football" && zombie.chargeTimer > 0 ? 1.85 : 1;
      const giantSlow = zombie.type === "gargantuar" ? .72 : 1;
      zombie.x -= zombie.speed * bannerBoost * enragedBoost * dashBoost * chargeBoost * giantSlow * dt * (zombie.slowTimer > 0 ? .48 : 1);
    }
  });
  // Mowers are a last-resort lane defense. Resolve them after zombie movement
  // but before projectiles and the house breach check.
  updateMowers(dt);
  game.shots.forEach((shot) => {
    shot.x += .34 * dt;
    const hit = game.zombies.find((zombie) => zombie.row === shot.row && zombie.x > shot.x - 12 && zombie.x < shot.x + 23 && !(zombie.type === "miner" && zombie.burrowTimer > 0) && !(shot.hitTargets || []).includes(zombie));
    if (!hit) return;
    shot.hitTargets = shot.hitTargets || [];
    shot.hitTargets.push(hit);
    shot.hitsLeft = Math.max(0, (shot.hitsLeft || 1) - 1);
    shot.hit = shot.hitsLeft <= 0;
    const rawDamage = shot.damage || 1;
    if (hit.armor > 0) {
      hit.armor = Math.max(0, hit.armor - rawDamage);
      hit.hp -= rawDamage * .35;
    } else hit.hp -= rawDamage;
    if (shot.fire && shot.burn) {
      hit.burnTimer = Math.max(hit.burnTimer || 0, shot.burn);
      hit.burnDamage = Math.max(hit.burnDamage || 0, shot.burnDamage || 1);
    }
    if (shot.slow) hit.slowTimer = Math.max(hit.slowTimer, shot.slow);
    if (shot.butter) hit.slowTimer = Math.max(hit.slowTimer, 3200);
    hit.flashTimer = 120;
    game.impacts.push({ x: shot.x, y: shot.y, radius: shot.butter ? 24 : shot.fire ? 20 : 16, color: shot.butter ? "#f4d37d" : shot.color || "#b7f3a0", life: 180, maxLife: 180 });
    addGameParticle(shot.x, shot.y, shot.color || "#b7f3a0", 5, .1);
    playGameSound("hit");
    if (hit.hp <= 0) {
      defeatZombie(hit);
      updateGameHud();
      addGameParticle(hit.x, hit.y, "#f6d681", 18, .2);
    }
  });
  game.shots = game.shots.filter((shot) => !shot.hit && shot.x < 735);
  let alive = 0;
  for (const particle of game.particles) {
    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;
    particle.vy += .00025 * dt;
    particle.life -= dt;
    if (particle.life > 0) game.particles[alive++] = particle;
  }
  game.particles.length = alive;
  alive = 0;
  for (const impact of game.impacts) {
    impact.life -= dt;
    if (impact.life > 0) game.impacts[alive++] = impact;
  }
  game.impacts.length = alive;
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
function canvasPoint(event) { const canvas = gameRender.canvas || $("#gameCanvas"), rect = canvas.getBoundingClientRect(); return { x: (event.clientX - rect.left) * GAME_LOGICAL_WIDTH / rect.width, y: (event.clientY - rect.top) * GAME_LOGICAL_HEIGHT / rect.height }; }
function updateGameHover(event) {
  if (!game.running) return;
  const point = canvasPoint(event);
  const next = gameCellAt(point.x, point.y);
  if (next?.row === game.hoverCell?.row && next?.col === game.hoverCell?.col) return;
  game.hoverCell = next;
  drawGame();
}
function clearGameHover() {
  if (!game.hoverCell) return;
  game.hoverCell = null;
  drawGame();
}
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
    removeGamePlant(existing);
    game.shovel = false;
    updateShovelButton();
    addGameParticle(position.x, position.y, "#e7d7a0", 12, .14);
    playGameSound("hit");
    drawGame();
    return true;
  }
  const type = game.selected;
  const covering = type === "pumpkin" && existing && existing.type !== "pumpkin";
  if (!type || (existing && !covering)) return false;
  const cost = plantCost[type];
  if (game.sun < cost) { setGameStatus("game.noSun"); return false; }
  if ((game.seedCooldowns[type] || 0) > 0) { setGameStatus("game.cooldown"); return false; }
  game.sun -= cost;
  game.seedCooldowns[type] = plantCooldown[type] || 0;
  const planted = { type, hp: plantHealth[type], row: cell.row, col: cell.col, seed: Math.random() * 1000, age: 0, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0, armed: type !== "potatomine" };
  if (covering) game.plants.splice(game.plants.indexOf(existing), 1, { ...planted, underPlant: existing });
  else game.plants.push(planted);
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
  $("#gameNewWindow").addEventListener("click", openGameWindow);
  $("#gameWideMode").addEventListener("click", toggleGameWideMode);
  $("#gameCodex").addEventListener("click", () => openGameCodex("plants"));
  $("#gameCodexClose").addEventListener("click", closeGameCodex);
  $$(".codex-tab").forEach((tab) => tab.addEventListener("click", () => openGameCodex(tab.dataset.codexTab)));
  $("#gameCodexPanel").addEventListener("click", (event) => { if (event.target.id === "gameCodexPanel") closeGameCodex(); });
  $("#gameFullscreen").addEventListener("click", toggleGameFullscreen);
  $("#gameStart").addEventListener("click", startGame);
  $("#gameShovel").addEventListener("click", toggleShovel);
  $$(".game-skill").forEach((button) => button.addEventListener("click", () => activateGameSkill(button.dataset.skill)));
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
  $("#gameCanvas").addEventListener("pointermove", updateGameHover, { passive: true });
  $("#gameCanvas").addEventListener("pointerleave", clearGameHover, { passive: true });
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
    const timelineToggle = event.target.closest("[data-timeline-toggle]");
    if (timelineToggle) {
      const timeline = timelineToggle.closest(".execution-trail");
      setTimelineDetails(timeline, timelineToggle.dataset.timelineToggle === "expand");
      event.preventDefault();
      return;
    }
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
  $("#sidebarOpen").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setSidebarCollapsed(false);
    else { $("#sidebar").classList.add("open"); $("#mobileScrim").classList.add("show"); }
  });
  $("#sidebarClose").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setSidebarCollapsed(true);
    else { $("#sidebar").classList.remove("open"); $("#mobileScrim").classList.remove("show"); }
  });
  $("#mobileScrim").addEventListener("click", () => { $("#sidebar").classList.remove("open"); $("#inspector").classList.remove("open"); $("#mobileScrim").classList.remove("show"); });
  $("#inspectorToggle").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setInspectorCollapsed(!state.inspectorCollapsed);
    else $("#inspector").classList.toggle("open");
  });
  $("#inspectorClose").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setInspectorCollapsed(true);
    else $("#inspector").classList.remove("open");
  });
  window.addEventListener("resize", applyPaneLayout);
  $("#panelBody").addEventListener("change", (event) => {
    if (event.target.id !== "reasoningEffortSelect") return;
    const value = event.target.value;
    if (!["low", "mid", "high", "xhigh", "max"].includes(value)) return;
    state.reasoningEffort = value;
    localStorage.setItem("minicc-reasoning", value);
    updateReasoningControl();
    showToast(state.locale === "zh" ? "新的任务将使用 " + t("reasoning." + value) + " 推理强度" : "New tasks will use " + t("reasoning." + value) + " reasoning effort");
  });
  $("#panelBody").addEventListener("click", async (event) => {
    const timelineToggle = event.target.closest("[data-timeline-toggle]");
    if (timelineToggle) {
      setTimelineDetails(timelineToggle.closest(".execution-trail"), timelineToggle.dataset.timelineToggle === "expand");
      event.preventDefault();
      return;
    }
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
    if (item.dataset.taskId) openTaskInWorkspace(item.dataset.taskId);
    else setSession(item.dataset.session);
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
  applyPaneLayout();
  initialMessageMarkup = $("#messageList").innerHTML;
  setSession(state.sessionId);
  applyLocale();
  refreshIcons();
  loadWorkspace();
  if (new URLSearchParams(location.search).get("arcade") === "1") openGame();
  // Keep tasks created in another session or browser tab visible in the sidebar.
  window.setInterval(() => { if (!document.hidden) loadTaskHistory(); }, 5000);
  window.addEventListener("beforeunload", persistSessionView);
});
