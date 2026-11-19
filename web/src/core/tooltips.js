/**
 * Curated bilingual teaching tooltips for the main surface.
 *
 * M8-T1053 already auto-derives a title for every rendered button from its
 * own text - honest, but tautological ("任务" saying "任务" teaches nothing).
 * This module is the other half of the contract: the ~40 controls a first
 * time visitor actually needs to decode get a *teaching* hint - what it does,
 * not what it is called. Buttons without an entry keep the M8-T1053 echo.
 *
 * Hints are inline bilingual per repo convention; no i18n keys are added.
 * Re-applied on `minicc:locale-changed` so zh and en stay honest per mode.
 */
const HINTS = [
  // ── sidebar nav: the 19 panes ────────────────────────────────────────────
  ['.nav-item[data-view="tasks"]', '查看/继续所有任务，复用工作区', 'View, resume and reuse every task workspace'],
  ['.nav-item[data-view="workspaces"]', '切换工作区，浏览它的文件树和 Git', 'Switch workspace; browse its file tree and git'],
  ['.nav-item[data-view="activity"]', '每一次工具调用的真实流水，可搜索', 'A true, searchable log of every tool call'],
  ['.nav-item[data-view="ledger"]', 'Tokens / 缓存命中率 / 成本的账本', 'Tokens, cache hit rate and cost, per call'],
  ['.nav-item[data-view="templates"]', '复用提示词与任务模板库', 'Reusable prompts and task templates'],
  ['.nav-item[data-view="manual"]', '打开 20 章中文使用说明书', 'Open the 20-chapter user manual'],
  ['.nav-item[data-view="almanac"]', '年鉴：70 卷双语世界叙事', 'Almanac: 70 bilingual volumes of the world'],
  ['.nav-item[data-view="axioms"]', '这个仓库的铁律（不可协商）', 'The non-negotiable axioms of this repo'],
  ['.nav-item[data-view="journal"]', 'Git 提交写成的船长日志', 'Your git commits, drawn as a captain’s log'],
  ['.nav-item[data-view="archive"]', '所有历史任务的档案馆', 'Searchable archive of past tasks'],
  ['.nav-item[data-view="askdocs"]', 'BM25 检索本仓库，模型只读作答（真跑）', 'BM25 retrieval over this repo; the model answers quote-only'],
  ['.nav-item[data-view="doctor"]', '逐项诊断工作区的问题', 'One-by-one workspace diagnostics'],
  ['.nav-item[data-view="dockyard"]', '你的专属旅程统计与船灯里程碑', 'Your own voyage ledger and harbour milestones'],
  ['.nav-item[data-view="atlas"]', '世界地图：13 座岛 · 110 个真实坐标', 'World map: 13 islands, 110 real coordinates'],
  ['.nav-item[data-view="admin"]', '管理员：密码 123 的共享门，真·统计', 'Admin: the shared door, password 123, real stats'],
  ['.nav-item[data-view="recent"]', '最近 ship 了什么', 'What shipped lately'],
  ['.nav-item[data-view="pulse"]', '缓存命中 · 上下文 · 完成率一屏看完', 'Hit rate, context usage and done rate in one ring'],
  ['.nav-item[data-view="promo"]', '生成公开宣传页（带真实验力）', 'Generate the public promo page with real proof'],
  ['.nav-item[data-view="arcade"]', '彩虹岛塔防：新手教程游戏', 'Rainbow-Island tower defence: the tutorial game'],
  // ── top bar / sidebar chrome ─────────────────────────────────────────────
  ['#helpMenuButton', '快捷键与帮助面板（?）', 'Shortcuts and help panel (?)'],
  ['.profile-row', '个人资料与模型/风格设置', 'Profile, model and output-style settings'],
  ['#localeZh', '切换到中文界面', 'Switch the UI to Chinese'],
  ['#localeEn', '切换到英文界面', 'Switch the UI to English'],
  ['#threadSearch', '全局搜索全部会话历史（⌘K）', 'Search every task in this workspace (⌘K)'],
  ['#task-dock-open', '展开 / 收起最近任务抽屉', 'Toggle the recent-task dock'],
  // ── inspector tabs ───────────────────────────────────────────────────────
  ['#tabChanges', '本次任务每处 diff，逐条可审', 'Every diff this task produced, change by change'],
  ['#tabFiles', '本次任务产出的成品文件', 'The finished files this task produced'],
  ['#tabVerification', '客观验证（测试 / 检查）的真实结果', 'The honest result of objective verification'],
  ['#todoSectionToggle', '展开或收起模型的工作计划清单', 'Show or hide the agent’s plan checklist'],
  // ── doctor / admin / composer / arcade ───────────────────────────────────
  ['.doctor-action', '立即运行这项诊断', 'Run this diagnosis now'],
  ['#admin-unlock-btn', '输入 123 解锁管理员面板', 'Type 123 to unlock the admin panel'],
  ['#sendButton', '发送任务（⌘/Ctrl + Enter）', 'Send the task (⌘/Ctrl + Enter)'],
  ['.codex-tab', '会话标签：切换当前对话线程', 'Thread tab: switch the active conversation'],
  ['.game-sound', '游戏音效开关', 'Toggle game sound'],
  ['.game-skill', '释放植物技能', 'Play a plant skill'],
  ['.game-how-ready', '准备好了，开始第一波', 'Ready — start the first wave'],
  ['.seed-card', '求生卡片：自己排除那个选项', 'Survivor cards: rule out the impossible'],
];

function currentLocale() {
  try {
    return (localStorage.getItem('minicc-locale') || 'zh') === 'en' ? 'en' : 'zh';
  } catch {
    return 'zh';
  }
}

let applied = false;

export function applyTooltips(root = document) {
  const en = currentLocale() === 'en';
  for (const [selector, zh, enHint] of HINTS) {
    for (const el of root.querySelectorAll(selector)) {
      const hint = en ? enHint : zh;
      if (!hint) continue;
      el.setAttribute('title', hint);
      el.setAttribute('aria-label', hint);
    }
  }
  applied = true;
}

export function tooltipsReady() {
  return applied;
}
