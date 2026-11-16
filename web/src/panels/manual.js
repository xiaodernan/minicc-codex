import { markVisited } from "../core/visited.js";
/* ============================================================
   Minicc Manual — the pocket book. Every module, every command,
   every game and every boundary, in one screen you never have
   to leave. Both languages, no half-translations: the zh mode
   says 说明书 in Chinese through and through; the en mode says
   manual in English through and through.
   ============================================================ */

import { $, state } from "../core/state.js";
import { t } from "../core/i18n.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel, beginPanelRequest, closePanel } from "../chat/stream.js";
import { SHORTCUT_GROUPS } from "../cheat-sheet-data.js";

export const CHAPTERS = [
  { id: "start", roman: "一", romanEn: "1", title: "Quick Start", titleZh: "五分钟上手" },
  { id: "workbench", roman: "二", romanEn: "2", title: "The Workbench", titleZh: "工作台导览" },
  { id: "modules", roman: "三", romanEn: "3", title: "The Modules", titleZh: "七个模块，一个世界" },
  { id: "keys", roman: "四", romanEn: "4", title: "Commands & Shortcuts", titleZh: "命令与快捷键" },
  { id: "arcade", roman: "五", romanEn: "5", title: "Playbook", titleZh: "游戏厅教程" },
  { id: "trouble", roman: "六", romanEn: "6", title: "Troubleshooting", titleZh: "排错" },
  { id: "limits", roman: "七", romanEn: "7", title: "Honest Limits", titleZh: "边界与范围" },
  { id: "vault", roman: "八", romanEn: "8", title: "Keys & Vault", titleZh: "密钥与金库" },
  { id: "philosophy", roman: "九", romanEn: "9", title: "The Quiet Room", titleZh: "安静的房间" },
  { id: "askdocs", roman: "十", romanEn: "10", title: "Ask the Repo", titleZh: "问仓库" },
  { id: "load", roman: "十一", romanEn: "11", title: "Load & Capacity", titleZh: "压测与容量" },
  { id: "cloud", roman: "十二", romanEn: "12", title: "Spring Cloud plane", titleZh: "微服务平面" },
  { id: "arch", roman: "十三", romanEn: "13", title: "Full Stack", titleZh: "前后端全景架构" },
  { id: "stategraph", roman: "十四", romanEn: "14", title: "StateGraph", titleZh: "状态图" },
  { id: "cache", roman: "十五", romanEn: "15", title: "Cache Affinity", titleZh: "冷热亲和" },
  { id: "sandbox", roman: "十六", romanEn: "16", title: "Sandbox & Safety", titleZh: "沙盒与安全" },
  { id: "fanout", roman: "十七", romanEn: "17", title: "Parallel Subagents", titleZh: "并行子智能体" },
  { id: "evidence", roman: "十八", romanEn: "18", title: "Evidence & Gates", titleZh: "证词与门禁" },
  { id: "ciwall", roman: "十九", romanEn: "19", title: "The CI Wall", titleZh: "长城" },
];

function zhStart() {
  return `
    <p class="manual-lede">一个本地优先的编程智能体——它接受 <code>MINICC_API_KEY</code>、<code>MINICC_BASE_URL</code>、<code>MINICC_MODEL</code>，然后在你的工作区里真正读写、运行、验证，最后把证据交回给你。</p>
    <ol class="manual-list">
      <li><strong>第一步：配置</strong> 复制 <code>minicc.config.example</code> 为 <code>.env</code>，填入三个环境变量：<code>MINICC_API_KEY</code>、<code>MINICC_BASE_URL</code>、<code>MINICC_MODEL</code>（任何 OpenAI 兼容的网关都可以，包括你的私有代理）。</li>
      <li><strong>第二步：启动</strong> <code>minicc-web --workspace /你的项目路径</code>，打开 <code>http://127.0.0.1:8765/</code>。</li>
      <li><strong>第三步：发第一个任务</strong> 在输入框里说人话——比如「读一下 README.md 并告诉我这个项目是干嘛的」。多任务会自动拆成父子任务。</li>
      <li><strong>第四步：看连接</strong> 底部状态栏出现 <em>已连接</em>、任务流开始滚动，说明模型与本地工具都通了。回答出来后点开任务详情，里面有全部工具调用、逐轮缓存命中率、完成验收记录。</li>
      <li><strong>第五步：回放</strong> 任务详情顶部点「回放整个任务」，按事件顺序重演一次交付过程——像看一场电影，支持暂停、拖拽进度、1×/2×/4× 倍速。</li>
    </ol>
    <div class="manual-callout">
      <strong>不想读字？直接看一遍。</strong>
      <p>点下面这个按钮，工作台会现场演示一次完整 Agent 任务：输入 → 计划 → 工具调用 → 测试验证 → 交付总结——看完你就会用了。</p>
      <button type="button" class="manual-demo-run" data-manual-demo>运行一次完整演示</button>
      <p class="manual-sidenote">第一次打开工作台时右下角会长出一枚「上手演练」按钮：10 步带你把工作台、世界、游戏、管理员门一条条走一遍；⌘K 搜「tour」随时重来。</p>
    </div>
    <p>不想打开浏览器？命令行也能直接用：<code>minicc "读 README 并总结"</code>，或 <code>minicc --stats</code> 看工作区体征。</p>
  `;
}

function enStart() {
  return `
    <p class="manual-lede">A local-first coding agent. Give it <code>MINICC_API_KEY</code>, <code>MINICC_BASE_URL</code> and <code>MINICC_MODEL</code>, and it reads, edits, runs and verifies — then hands you the evidence.</p>
    <ol class="manual-list">
      <li><strong>Step 1 — Configure</strong> copy <code>minicc.config.example</code> to <code>.env</code> and fill three variables: <code>MINICC_API_KEY</code>, <code>MINICC_BASE_URL</code>, <code>MINICC_MODEL</code> (any OpenAI-compatible gateway works, including your private proxy).</li>
      <li><strong>Step 2 — Start</strong> run <code>minicc-web --workspace /path/to/your/project</code>, open <code>http://127.0.0.1:8765/</code>.</li>
      <li><strong>Step 3 — Send your first task</strong> type a sentence in the composer — e.g. “Read README.md and tell me what this project does.” Multi-part sentences are auto-split into parent and child tasks.</li>
      <li><strong>Step 4 — Watch it connect</strong> the status bar shows <em>Connected</em> and the task stream starts scrolling. When the answer arrives, open the task detail to see every tool call, per-turn cache hit rate, and the completion verdict.</li>
      <li><strong>Step 5 — Replay it</strong> from the task detail top, click “Replay the whole task” to replay the delivery event by event — pause, scrub the progress bar, 1×/2×/4× speed.</li>
    </ol>
    <div class="manual-callout">
      <strong>Would rather watch than read?</strong>
      <p>Click the button below and the workbench will run a full agent task for you, live: intake → plan → tool calls → test verification → delivery summary. Watch it once and you know the product.</p>
      <button type="button" class="manual-demo-run" data-manual-demo>Run the live demo</button>
      <p class="manual-sidenote">First time here? A “Start tour” pill grows in the bottom-right corner — ten steps across the workbench, the world map, the arcade, and the shared door. Search “tour” in ⌘K to replay it anytime.</p>
    </div>
    <p>Prefer the CLI? <code>minicc "Read README and summarize it"</code>, or <code>minicc --stats</code> for an operational inventory.</p>
  `;
}

function zhWorkbench() {
  return `
    <p class="manual-lede">三栏布局：<strong>左栏</strong> 是任务导航与分支，<strong>中栏</strong> 是对话与工作流，<strong>右栏</strong> 是验证与审计证据。</p>
    <div class="manual-grid-list">
      <div><strong>输入框</strong><span>直接说人话；多任务会自动编排，一个句子里的多件事会被拆成父子任务。</span></div>
      <div><strong>任务详情</strong><span>点开任意任务：工具调用、逐轮 turn、缓存命中率火花线、逐次调用的系统/消息/工具指纹全部可见。</span></div>
      <div><strong>回放席</strong><span>任务详情顶部「回放整个任务」把一次交付按事件顺序完整重播——像看一场电影。</span></div>
      <div><strong>权限模式</strong><span>普通模式默认写入前询问；yolo 模式全自动，但工具名、路径与命令仍然写入审计日志。</span></div>
      <div><strong>会话视图</strong><span>同一 session 内可以分支、diff、回滚——视图与工作区状态绑定，切换不会误读旧对话。</span></div>
      <div><strong>审计面板</strong><span>每一条工具调用都以 info/notice/warning 落盘并脱敏，api_key 永远不会出现在日志里。</span></div>
    </div>
  `;
}

function enWorkbench() {
  return `
    <p class="manual-lede">Three columns: <strong>left</strong> is the task navigator, <strong>middle</strong> is the conversation and work flow, <strong>right</strong> is the verification and audit evidence.</p>
    <div class="manual-grid-list">
      <div><strong>Composer</strong><span>Just say it. A sentence naming multiple things becomes a parent task with auto-orchestrated children.</span></div>
      <div><strong>Task detail</strong><span>Any task: tool calls, turns, the per-turn cache-hit sparkline, per-call system/messages/tools fingerprints — all inspectable.</span></div>
      <div><strong>Replay</strong><span>“Replay the whole task” from the detail top replays the delivery as an ordered event film — scrub it like a player.</span></div>
      <div><strong>Permissions</strong><span>Default mode asks before writes; yolo mode runs autonomously — tool name, path and command always land in the audit log.</span></div>
      <div><strong>Session views</strong><span>Branch, diff and roll back inside a session; view state is bound to the workspace so you never read a stale conversation.</span></div>
      <div><strong>Audit panel</strong><span>Every tool call is logged with a level and a redacted payload — api_key never appears in the log.</span></div>
    </div>
  `;
}

function zhModules() {
  return `
    <p class="manual-lede">工作台之上有一整套随处可达的模块——它们不是孤岛，而是同一份证据的不同视角。</p>
    <ul class="manual-chapter-list">
      <li><strong>账本 · Ledger</strong> — ⌘L 打开：总 token 金句、缓存命中率圆环（hit/miss/write 拆分）、成本与未定价标注、模型分解表、状态 segmented bar。一切数字来自真实任务快照。</li>
      <li><strong>脉搏 · Pulse</strong> — 三环（命中率/上下文占比/完成率）+ 最近 12 个任务档案 + 逐次调用缓存火花线；实时增长，关了再开也读数。</li>
      <li><strong>诊断 · Doctor</strong> — 侧边栏「诊断」：三件真工具——「上游回声」对配置的 OpenAI 网关实测 <code>GET /models</code> 延迟（不消耗 token，密钥绝不回传）；「负载实验室」最高 24 并发、24 请求锤本机回环端点，直方图画出 MIN/P50/P95/MAX；「工作区自检」直接复用 <code>minicc --doctor</code> 引擎（Python/安装自检/.minicc 可写/审计日志最新行/token 权限/permissions.json/git work tree），数字全部来自当次真实测量。</li>
      <li><strong>船厂 · Dockyard</strong> — 侧边栏「船厂」：把你自己的真实旅程做成展厅——「航海日志」六格全部来自真实任务与 git 元数据（首次提交 / 提交总数 / 完成任务 / 年鉴卷数 / 累计 token / 缓存亲和率，数据直接读 /api/digest、/api/metrics、/api/worldpulse）；「灯塔 · 十一座里程碑」照真实指标逐格解锁（起航 / 领主 1,000 提交 / 卷典者十七卷 / 万点繁星 / 守夜人 80% 亲和率等），未达成的只显示真实进度，不放演示徽章。</li>
      <li><strong>年鉴 · Almanac</strong> — 侧边栏「年鉴」：四十九卷博物馆级叙事，把这个产品的设计决策按章讲述（最新卷：卷四十八《墙立住了》——roll call 于 CI 为自己说话——每次都点亮看起来同样的门），每卷数据全部来自 /api/digest、/api/stats 与 git 自身。</li>
      <li><strong>管理员 · Admin</strong> — 侧边栏「管理」：密码 123 研一道共享门（非登录，只对本地自己人可见）；stats（任务数 / 完成 / 中断 / 缓存亲和率 / 审计行 / 会话数）+ 七日事件 Canvas（requestAnimationFrame 真绘制）+ 最小二乘线性预测（明文标注：这是估计，不是承诺）+ 中断原因自动分桶（这个仓库全部 3 次中断全部是服务重启）+ 顶部工具真实使用直方图（read_file 48% · grep 14% · glob 13% · tree 9% · bash 6% · git_diff 5%，全部从 /api/admin/summary 真实读数，零虚构）；点 4 下之后就能看见所有数字。</li>
      <li><strong>世界地图 · Atlas</strong> — 侧边栏「地图」：一张 canvas 地图（13 座岛屿、86 个真实坐标——18 面板 + 49 年鉴卫星 + 19 说明书卫星）；拖拽平移、滚轮缩放、点击坐标直达对应面板或章节；右侧书架「岛屿志 · 十三岛」实时显示每座岛的勘度（几何每岛几个坐标、勘了几个）+ 每座岛一句属于自己的话；已点亮琥珀色「已探访」，未触及灰色烬；visitedKey 端到端为证明，防止你点亮之后跳走又认不出来；「清除我的足迹」一键清空 localStorage 里的访问记录；<strong>星尘里程碑</strong>（勘完 25%、50%、75%、100% 时星尘自己会说一句话，每档只说一次——清除足迹也清掉它们）；Esc 随时关闭。</li>
      <li><strong>模板库 · Templates</strong> — 8 张策展过的常见任务提示词（项目扫描 / 测试修复 / 安全检查 / README / 翻译 / 依赖 / 现代化 / 冒烟），一键送进对话。</li>
      <li><strong>回放 · Replay</strong> — 任务详情内「回放整个任务」，按事件顺序播放：播放/暂停、scrub 进度条、1×/2×/4× 变速、tokens 旁路累加。</li>
      <li><strong>航行灯 · Running light</strong> — 侧边栏常驻一枚小灯：缓存命中率 × 任务数 × 分支 @ HEAD，四色温；点击直达账本。</li>
      <li><strong>火苗 · The flame</strong> — 连续完成任务的天数：一天 ≥1 次真实任务即点亮一次，金焰色呼吸光晕置于侧边栏；两天没完成就从头计算。全部本地保存，不出网。</li>
      <li><strong>状态图 · StateGraph</strong> — 侧边栏「说明书 → 状态图」：minicc 内部的阶段轴 / 只读 DAG 执行器 / 预算护栏的完整说明——真正把「Agent 如何走」写进了一张你能看见的图里。</li>
    </ul>
  `;
}

function enModules() {
  return `
    <p class="manual-lede">The workbench ships a whole set of always-available modules — not islands, but different views of the same evidence.</p>
    <ul class="manual-chapter-list">
      <li><strong>Ledger</strong> — ⌘L opens it: headline token count, cache-hit donut (hit/miss/write), cost with unpriced-callouts, model breakdown, status segmented bar. Every number comes from real task snapshots.</li>
      <li><strong>Pulse</strong> — three rings (hit rate / context usage / done rate) + last 12 task archive + per-call cache sparkline; live growth, re-opens with fresh numbers.</li>
      <li><strong>Doctor</strong> — sidebar “Doctor”: three honest instruments — “Upstream echo” probes your configured OpenAI gateway with a real <code>GET /models</code> (zero tokens, key never echoed); “Load lab” fires 24 loopback requests at up to 24× concurrency and draws the measured MIN/P50/P95/MAX histogram; “Workspace self-check” reuses the <code>minicc --doctor</code> engine (Python / install self-check / .minicc writable / audit tail parses / token permissions / permissions.json / git work tree) — everything measured on this machine, nothing from the network.</li>
      <li><strong>Dockyard</strong> — sidebar “Dockyard”: your own real journey as a harbour of stakes. “Captain's log” shows six counters pulled straight from real tasks and git metadata (first commit / total commits / tasks completed / yearbook volumes / tokens spent / cache affinity — read in place from /api/digest, /api/metrics, /api/worldpulse); “Lighthouse stakes” — eleven medals unlocked by real metrics (Departure / The Captain 1,000 commits / The Cartographer seventeen volumes / A Thousand Lights / The Night Watch at 80% affinity…). Locked stakes show true progress, never fake badges.</li>
      <li><strong>Almanac</strong> — sidebar entry: a museum-grade narrative in forty-nine chapters (the newest, Chapter XLVIII “The Great Basin” — the week a repo laid twenty-nine worktrees on the bench and walked away with seven, every unique fragment anchored on a rescue branch; every previous chapter still plays), every figure sourced from /api/digest, /api/stats, /api/worldpulse and git itself.</li>
      <li><strong>Admin</strong> — sidebar entry “Admin”: password <code>123</code> unlocks a shared door (not a login — a door for anyone who knows it); stats — tasks / completed / interrupted / cache hit rate / audit lines / sessions; a 7-day events canvas (requestAnimationFrame, real draw); a least-squares linear forecast — labelled“this is an estimate, not a promise”; interruption-cause breakdown routed buckets (all three interruptions on this machine are service restarts); top tool-usage distribution read straight from the task store — read_file 48% · grep 14% · glob 13% · tree 9% · bash 6% · git_diff 5% — not one demo number.</li>
      <li><strong>Atlas</strong> — sidebar entry “Atlas”: a canvas world map — thirteen islands, eighty-six real coordinates — 18 panes + 49 almanac satellites + 19 manual satellites; drag to pan, wheel to zoom, click a coordinate to teleport home; the “Islands, twelve” drawer lists every island with live charted/total counts and one honest line per island; visited nodes glow amber with an amber trail drawn straight across the world; a “clear my trail” button wipes everything; <strong>stardust milestones</strong> fire once each at 25%, 50%, 75%, 100% charted — and clear with the trail; Esc returns you to the desk.</li>
      <li><strong>Templates</strong> — 8 curated prompts for common jobs (project scan / test+fix / safety / README / translation / deps / modernize / smoke), one click into chat.</li>
      <li><strong>Replay</strong> — “Replay this task” from the detail view, plays event-by-event: play/pause, scrubber, 1×/2×/4× speed, side-mounted token counter.</li>
      <li><strong>Running light</strong> — an always-on sidebar dot: cache hit rate × tasks × branch @ HEAD, four tones; click to open the ledger.</li>
      <li><strong>The flame</strong> — days in a row with at least one completed task: one flame per calendar day, breathing gold in the sidebar; two misses restart the count. Local-only, never leaves this machine.</li>
      <li><strong>StateGraph</strong> — manual → “StateGraph” chapter: the phase axis, the readonly-only DAG executor and the budget guardrail — written down as a map you can follow, not a myth you have to infer.</li>
    </ul>
  `;
}

function zhKeys() {
  const rows = SHORTCUT_GROUPS.flatMap((group) =>
    group.rows.map(([zh, _en, key]) => `<div><kbd>${escapeHtml(key)}</kbd><span>${escapeHtml(zh)}</span></div>`)).join("\n      ");
  return `
    <div class="manual-keys">
      ${rows}
    </div>
    <p class="manual-footnote">命令面板里还有更多：切换主题、打开年鉴、打开回放、导出当前对话、恢复任务快照等——全部可以用鼠标或键盘操作。</p>
  `;
}

function enKeys() {
  const rows = SHORTCUT_GROUPS.flatMap((group) =>
    group.rows.map(([_zh, en, key]) => `<div><kbd>${escapeHtml(key)}</kbd><span>${escapeHtml(en)}</span></div>`)).join("\n      ");
  return `
    <div class="manual-keys">
      ${rows}
    </div>
    <p class="manual-footnote">The command palette carries more: theme toggle, open the almanac, open replay, export the conversation, restore a task snapshot — every action keyboard or mouse operable.</p>
  `;
}

function zhArcade() {
  return `
    <p class="manual-lede">「游戏厅」是工作台自带的真·游戏——不是 demo，不是占位符。植物对僵尸，塔防类型，纯前端，离线可玩。</p>
    <div class="manual-arcade">
      <div><span class="arcade-label">怎么进</span><p>侧边栏「小游戏」或者命令面板搜「Arcade/游戏厅」，按 <code>Enter</code> 即玩。随时按 <code>Esc</code> 返回工作台。</p></div>
      <div><span class="arcade-label">核心机制</span><p>种植物抵御僵尸进攻。阳光是资源，种植需要阳光值；每种植物有攻击/防御/特殊能力；僵尸从右向左推进，触碰到你的基地则失败。</p></div>
      <div><span class="arcade-label">四种技能</span><p>Pulse（25 阳光，7 秒冷却）、Sun（35 阳光，立即回能）、Rally（45 阳光，14 秒冷却）、Time Stop（55 阳光，18 秒冷却）——每种技能只对特定局面有效，合理攒阳光比盲目种植更重要。</p></div>
      <div><span class="arcade-label">图鉴</span><p>游戏内置植物/僵尸图鉴——peashooter、sunflower、wall-nut、cherry bomb、gatling pea、jalapeno、magnetshroom……每种植物都有属性与 special 描述；终极关卡是「巨人僵尸」。</p></div>
      <div><span class="arcade-label">数据</span><p>游戏数据全部保存在你的浏览器里；关闭工作台不会丢失进度，清浏览器缓存会重置。</p></div>
      <div><span class="arcade-label">冲关心法（带表）</span><p><strong>五波打法 · 默认「高压」难度</strong>（共 10 波）<br/>第一波 9 只 · 第二波 11 只 · 第三波 13 只 · 第四波 15 只 · 第五波 17 只——前五波只铺向日葵 + 豌豆射手（每行两株）；前几波不放墙，好省阳光攒一炮清场。第四波末：一罐大招（cherry bomb 清路，给 walkers/路障/排水口路障；100 阳光内部爆炸 3×3；积分励志攻蜂+30）。<strong>第六波后</strong>：walker 开始换装路障 conehead/buckethead（两只），考虑 jalapeno 另一行整。第七波偶遇 football 冲刺（堵前）。第十波<strong>必现 gargantuar</strong>——别留手，Time Stop + Rally 连用。<br/><strong>阳光账本</strong>：标准难度初始 200· 硬核级 175· 噩梦级 110。天空每 10 秒飘 25·sunflower/单位 60s 各产 25；双击拾取、「自动拾取」子弹一次扫 25。<br/><strong>防线车</strong>：每行左边各一辆，僵尸进屋即被碾；僵尸全灭时必须保护住这条线。<br/><strong>能量（Energy）</strong>：初始 60，上限 100；每次击杀 +4，技能击杀 +1，自动回能另计——技能少而精。Time Stop 冻住全场 4s——按的是「最近必死关口」。<br/><strong>连击</strong>：击杀僵尸分递增的窗口是 1.8s；连击 ≥3 后的溢出 Combo 奖励毁天灭地。第一行第二行要在一口气里把僵尸清掉。</p></div>
      <div><span class="arcade-label">植物经济学</span><p>阳光每秒 ~2-4 焦点（含自然飘阳光）——算账法：一株火豌豆同时连杀两只值回本；wallnut 顶前线，三到四波都替后面的火力抵掉一整排伤害。撑杆跳只会跳过第一个 plant（不会跳墙），磁力菇能拔路障/桶顶；squash 直取一个僵尸。手法上：朝向永远是右边，先 front 排后 back 排，能不换车尽量不换。</p></div>
      <div><span class="arcade-label">第一局怎么赢（通关路线）</span><p><strong>① 先攒阳光</strong>——开局先放两朵向日葵，边生产边等僵尸靠近；<br/><strong>② 再输出</strong>——至少 3 株豌豆射手位于第一波路线的右侧，跟上升级节奏；<br/><strong>③ 第三波筑墙</strong>——坚果墙顶在僵尸路径正前面，其余输出站后面；<br/><strong>④ 关键清场</strong>——阳光攒够 150，在僵尸至少两个聚到一起时放樱桃炸弹/辣椒；<br/><strong>⑤ 决胜巨人</strong>——第 10 波把 Time Stop + Rally 连用，把路径两侧辅助火力推满。</p></div>
      <div><span class="arcade-label">几个经常忽略但管用的键位</span><p><code>数字键 1-9</code> 选卡 · <code>P</code> 暂停/继续 · <code>E</code> 铲子/取消 · 阳光可手动点击收集（游戏内也有「自动拾取」开关）· 切到其他标签页会自动暂停，回到来继续——战斗用时只按活跃帧统计，不会吃冤枉时长。</p></div>
    </div>
    <p class="manual-footnote">游戏代码在 <code>web/game.js</code>，纯前端，没有任何服务端交互。</p>
  `;
}

function enArcade() {
  return `
    <p class="manual-lede">The Arcade is a real game baked into the workbench — not a demo, not a placeholder. Plants versus Zombies, tower-defense genre, pure frontend, offline-playable.</p>
    <div class="manual-arcade">
      <div><span class="arcade-label">How to open</span><p>Sidebar entry « Arcade » or type “Arcade” in the command palette, then <code>Enter</code>. Plays offline; <code>Esc</code> returns to the workbench.</p></div>
      <div><span class="arcade-label">Core loop</span><p>Plant units on the lawn and hold the line against zombies. Sun is the resource; planting costs sun; every plant has attack/defense/special traits; zombies push from right to left — reaching your base means failure.</p></div>
      <div><span class="arcade-label">Four skills</span><p>Pulse (25 sun, 7s cooldown), Sun (35 sun, instant refill), Rally (45 sun, 14s cooldown), Time Stop (55 sun, 18s cooldown) — each skill is situational, none is generic; hoarding sun beats mindless planting.</p></div>
      <div><span class="arcade-label">The codex</span><p>In-game plant and zombie codex — peashooter, sunflower, wall-nut, cherry bomb, gatling pea, jalapeno, magnetshroom … each with stats and a special. The final wave is the gargantuar.</p></div>
      <div><span class="arcade-label">Data</span><p>All game state lives in your browser; closing the workbench never loses progress, clearing browser cache resets it.</p></div>
      <div><span class="arcade-label">First game walkthrough</span><p><strong>① Sun first</strong> — drop two sunflowers before the first wave arrives and let them bake sun while zombies approach;<br/><strong>② Then damage</strong> — at least 3 peashooters along the threatened lanes; keep them behind the wall;<br/><strong>③ Wall by wave 3</strong> — a wall-nut planted right in front of the attack lanes, absorbing hits while your shooters fire from behind;<br/><strong>④ Clear the clump</strong> — once you have 150 sun, drop a cherry bomb or jalapeno when two or more zombies clump together;<br/><strong>⑤ Close out the gargantuar</strong> — wave 10: chain Time Stop + Rally, and let your full volley land while the giant is stopped.</p></div>
      <div><span class="arcade-label">Wave-by-wave (hard difficulty)</span><p>Wave 1 (9 zombies) · Wave 2 (11) · Wave 3 (13) · Wave 4 (15) · Wave 5 (17) — front half is all walkers; save sun for a cherry-bomb AoE clear at wave 5/6.<br/>Waves 6–9 (19 / 21 / 23 / 25) — first roadblock appearances, coneheads and bucket heads come into play; Jalapeño the lane with the most tank to buy back tempo.<br/>Wave 10 — <strong>Gargantuar</strong> arrives with <em>imps</em> in his bag. Time Stop to freeze him, Rally to halve his pace, then plant everything you have — from both lanes if possible.</p></div>
      <div><span class="arcade-label">Plainspoken economy</span><p>Sun trickles in at roughly 2–4 per second (sky falls + sunflower throughput) — two consecutive peashooter kills pay for themselves. Wall-nuts absorb the entire front lane for 3–4 waves. A polevaulter only jumps the first plant (it won't jump walls); magnet-shroom strips conehead/buckethead gear off any zombie; squash is your exact answer to a priority target.</p></div>
      <div><span class="arcade-label">Keys you will want</span><p><code>1-9</code> pick a card · <code>P</code> pause / resume · <code>E</code> shovel / cancel · click sun drops to collect them yourself (auto-collect toggle exists in-game) · the game pauses itself when the tab loses focus — fight time only counts active frames.</p></div>
    </div>
    <p class="manual-footnote">Game code lives in <code>web/game.js</code> — pure frontend, no server round-trip whatsoever.</p>
  `;
}

function zhVault() {
  return `
    <p class="manual-lede">密钥是整个工作空间唯一不能入库的东西——这一页讲的是它的全部旅程：放哪、怎么验、怎么轮换、怎么省。</p>
    <div class="manual-trouble">
      <div><strong>一、密钥放哪</strong><span><code>.env</code> 已被 git 忽略（仓库根 <code>.gitignore</code>），复制 <code>minicc.config.example</code> 填入 <code>MINICC_API_KEY</code> / <code>MINICC_BASE_URL</code> / <code>MINICC_MODEL</code>；不要提交、不要粘进聊天、不要藏在命令行参数里（<code>ps</code> 看得见）。轮换 = 改文件 + 重启进程，一处修改、全局生效。</span></div>
      <div><strong>二、第一句验连接</strong><span><code>minicc --doctor</code> 会打印网关、协议、密钥裁切与（很重要的）「prefix cache: prompt_cache_key = explicit/derived」一行——两态都算正常，但 <code>derived</code> 意味着你还没固定亲和键；同一网关下换 workspace 仍然稳定。</span></div>
      <div><strong>三、换网关不冷场</strong><span>维护两份配置文件，把 <code>MINICC_PROMPT_CACHE_KEY</code> 设为<em>同值</em>——缓存亲和随 key 迁移，历史身价（90%+ 热命中）不蒸发；换 key 则等于换机器，前缀 KV 缓存重新烧钱。</span></div>
      <div><strong>四、看清了花了多少钱</strong><span><code>minicc --stats</code> 末尾一行 <code>llm cache:</code> 给出命中率（本工作区、含所有任务快照）；<code>[usage]</code> 行每轮打印 <code>cache_hit_pct</code>；「脉搏」面板画的是<em>逐 turn 命中火花线</em>，哪一不在燃烧一目了然；无任务处永远不会有假 0%。</span></div>
      <div><strong>五、成本账目</strong><span><code>/api/metrics</code> 返回 <code>cost_is_partial</code>——未注册单价的模型，其成本按 0 估算且<em>如实</em>标注部分缺字；已定价的任务逐模型分解（<code>by_model</code>），每个数字可被 <code>/api/tasks</code> 快照复核。</span></div>
      <div><strong>六、Anthropic 路径也有缓存</strong><span><code>MINICC_PROVIDER_TYPE=anthropic</code> 时，system 与工具集头顶放置了 cache_control 断点——跨轮命中直接落账本；<code>MINICC_ANTHROPIC_BASE_URL</code> 指向私有/自建网关时，注意网关延迟而非协议差异，缓存计费逻辑一致。</span></div>
      <div><strong>七、归档与重置</strong><span>数据全落在 <code>.minicc/</code>（<code>tasks.sqlite3</code> 任务快照、<code>audit.jsonl</code> 审计线、<code>sessions/</code> 会话、<code>llm_cache</code> 用量）。需要减肥：先 <code>minicc --stats</code> 看占比，再按文件复制备份，删除是你自己的决定——这个目录是仓库的工作区私有数据，不是动态。</span></div>
    </div>
    <p class="manual-footnote">这一章的每一句都能在文档或 CLI 里被验证；写它的人拒绝在账本上虚构任何数字。</p>
  `;
}

function enVault() {
  return `
    <p class="manual-lede">The one thing this workbench can never check into a ledger — the key. Its whole journey: where it lives, how to verify it, how to rotate it, and how to see what it costs.</p>
    <div class="manual-trouble">
      <div><strong>1. Where the key lives</strong><span><code>.env</code> is git-ignored (repo-root <code>.gitignore</code>). Copy <code>minicc.config.example</code> and fill <code>MINICC_API_KEY</code> / <code>MINICC_BASE_URL</code> / <code>MINICC_MODEL</code>; never commit it, never paste it into chat, never pass via argv (that <code>ps</code> wins). Rotating = edit the file + restart the process; change once, effect everywhere.</span></div>
      <div><strong>2. The first reach</strong><span><code>minicc --doctor</code> reports gateway, protocol, key masks and — the line worth watching — <code>prefix cache: prompt_cache_key = explicit/derived</code>. Both modes are healthy, but <code>derived</code> means the affinity key is not pinned yet; it stays stable per workspace across restarts anyway.</span></div>
      <div><strong>3. Switching gateways without going cold</strong><span>Two config files, same <code>MINICC_PROMPT_CACHE_KEY</code> — cache affinity migrates with the key, warm numbers (90%+ hits) survive the move; a fresh key is a fresh machine, prefix KV warms up from zero.</span></div>
      <div><strong>4. See what you actually spent</strong><span><code>minicc --stats</code> ends with <code>llm cache:</code> hit rate (this workspace, across every task snapshot); the <code>[usage]</code> line prints <code>cache_hit_pct</code> per turn; the pulse panel draws a per-turn cache sparkline so a cold streak is unmistakable; fake 0% never happens, missing numbers never fabricate.</span></div>
      <div><strong>5. The bill's fine print</strong><span><code>/api/metrics</code> returns <code>cost_is_partial</code> — unpriced models estimate at 0 and are <em>labelled</em> partial, nothing floats silently; priced tasks split by model (<code>by_model</code>), every number auditable through <code>/api/tasks</code> snapshots.</span></div>
      <div><strong>6. Anthropic path also caches</strong><span>With <code>MINICC_PROVIDER_TYPE=anthropic</code>, system and tool-set headers carry cache_control breakpoints; hits land in the same ledger; a private <code>MINICC_ANTHROPIC_BASE_URL</code> fails on latency, never on protocol — cache accounting behaves.</span></div>
      <div><strong>7. Archive or wipe</strong><span>Everything lives under <code>.minicc/</code> (<code>tasks.sqlite3</code> snapshots, <code>audit.jsonl</code> lines, <code>sessions/</code> ids, cache usage). Before trimming: <code>minicc --stats</code> shows the footprint; <code>cp -a</code> first, deletion is your call — this directory is workspace-private data, nothing else.</span></div>
    </div>
    <p class="manual-footnote">Every sentence here is checkable in the docs or the CLI; the writer refuses to invent a single figure on the books.</p>
  `;
}

function zhPhilosophy() {
  return `
    <p class="manual-lede">这个房间为什么这样被造——</p>
    <div class="manual-arcade">
      <div><span class="arcade-label">这里没有甲方</span><p>如果你期待的是一个每天把你哄进结账页的产品，这个地方不是。minicc 记住自己的本分：<strong>被打开、被使用、被关掉</strong>——下一次再见面时它还是原始的那个你。</p></div>
      <div><span class="arcade-label">这里没有专有算法</span><p>这里没有 model card 来自营销文档，没有 spawned-agent farm 来自媒体稿。每个门类、每个面板、每个提示，都是这个仓库里可以读的代码——你可以读完每一行，你不可以假装它不是这么写的。</p></div>
      <div><span class="arcade-label">这里没有情绪化智能体</span><p>这里的模型不会对你撒谎、不会替你喝彩，也不会推销自己。它会告诉你它完成了什么、它没有完成什么，以及它需要哪份文件来证明自己。</p></div>
      <div><span class="arcade-label">这里没有 "THE PLAN"</span><p>你看到的每一块都被现场验证过：缓存命中率来自 <code>/api/metrics</code>、变更来自 git、提交数来自 git、日志行数来自 <code>audit.jsonl</code>。这里不允许任何一个数字不接地气。</p></div>
      <div><span class="arcade-label">这里的一切都会回来</span><p>当门红了、CI 红了、测试红了——这里不提供安慰，但会递上证据。你永远可以停在门前说：在你说「完成」之前，我看过这份报告。</p></div>
    </div>
    <p class="manual-footnote">《安静的房间》——这是人为挑选的词。这个项目不会大声话，但它会把每件事写下来，包括它自己。</p>
  `;
}

function enPhilosophy() {
  return `
    <p class="manual-lede">Why this room was built this way —</p>
    <div class="manual-arcade">
      <div><span class="arcade-label">No sponsor</span><p>If you are expecting a product that flatters you into the checkout page, this is not it. minicc remembers its one responsibility: be opened, be used, be closed — and be the same repo when we meet again.</p></div>
      <div><span class="arcade-label">No proprietary wisdom</span><p>No model card lifted from a marketing page, no spawned-agent farm from a press release. Every surface here is code that lives in this repository — readable, auditable, and honest about being exactly what it is.</p></div>
      <div><span class="arcade-label">No theatrical agent</span><p>The model will not lie to you, over-sell you, or wave a ribbon in your face. It shows what it finished, what it did not, and which file it would need in order to prove the rest.</p></div>
      <div><span class="arcade-label">No “the plan”</span><p>Every number here answers to reality: cache hit rates from <code>/api/metrics</code>, file counts from git, commits from git, log lines from <code>audit.jsonl</code>. Nothing floats, nothing pretends.</p></div>
      <div><span class="arcade-label">Everything here has receipts</span><p>When the gates go red, this room does not offer comfort — it offers evidence. You can always stop at the door and say: before you said done, I saw the report.</p></div>
    </div>
    <p class="manual-footnote">The Quiet Room — the word is chosen on purpose. This project will not shout, but it will put everything in writing, including itself.</p>
  `;
}
function zhTrouble() {
  return `
    <div class="manual-trouble">
      <div><strong>我看到「未连接」</strong><span>检查 <code>MINICC_API_KEY</code>/<code>MINICC_BASE_URL</code>，或跑 <code>minicc --doctor</code>——其中一项会给你写明是密钥、是网络还是证书。</span></div>
      <div><strong>缓存命中率低</strong><span>先上证据再下结论。2026-11-15 在同一把 key、同一条 ~5.5k-token 前缀上实测（wkapi.pro · gpt-6-sol）：Responses 流式 94.5% → 100%（热）、流式无 key 的 chat/completions <em>永不上报</em> cached_tokens；带 key 后 chat 流式/非流式都报（5376/5509 = 97.5%）。minicc 始终自动派生 <code>prompt_cache_key</code>——浏览器里跑 agentic 任务实测 81~98%。「显示非流」是上次事故后的恢复锁已被移除（M8-T879/897/900）；「命中率低」则是 chat 流式不回 cached_tokens 的显示产物，不是缓存没生效。</span></div>
      <div><strong>任务卡住</strong><span>Ctrl/⌘+C 在终端里，或工作台「重置」按钮。恢复机制会把上下文压缩成 checkpoint，任务可以续上，不会丢失已完成的写入文件。</span></div>
      <div><strong>工作区不可写</strong><span>默认本地沙箱需要写权限。你也可以选 process 或 docker 模式（<code>MINICC_SANDBOX</code>）。</span></div>
      <div><strong>SSE 断开</strong><span>关掉代理里的 request body 缓冲（Spring Cloud plane 里对应 <code>X-Accel-Buffering: no</code>）。本地直连不会遇到。</span></div>
      <div><strong>/api/stats 返回错误</strong><span>真实浏览器里打开控制台；如果 HTTP 状态是 503，<code>minicc --doctor</code> 会告诉你哪个后端掉线。</span></div>
    </div>
  `;
}

function enTrouble() {
  return `
    <div class="manual-trouble">
      <div><strong>I see “Disconnected”</strong><span>Check <code>MINICC_API_KEY</code>/<code>MINICC_BASE_URL</code>, or run <code>minicc --doctor</code> — it tells you whether it is the key, the network or the certificate.</span></div>
      <div><strong>Cache hit rate looks low</strong><span>Evidence first. Measured 2026-11-15 on this gateway (same key, same ~5.5k-token prefix): Responses streaming 94.5% → 100% (warm); chat/completions streaming <em>without</em> a key never reports <code>cached_tokens</code>; with a key both chat modes report it (5376/5509 = 97.5%). minicc always rides an auto-derived <code>prompt_cache_key</code> — agentic tasks measured 81~98%. “Shows non-stream” was the recovery lock, removed in M8-T879/897/900; “low hit rate” is the chat-stream non-report, not a failed cache.</span></div>
      <div><strong>Task appears stuck</strong><span>Ctrl/⌘+C in the terminal, or the Reset button in the workbench. The recovery path compacts a checkpoint — completed writes survive, the context continues.</span></div>
      <div><strong>Workspace not writable</strong><span>The default local sandbox needs write permission. You can also pick process or docker mode (<code>MINICC_SANDBOX</code>).</span></div>
      <div><strong>SSE drops</strong><span>Disable request-body buffering in your proxy (<code>X-Accel-Buffering: no</code> on the Spring Cloud plane). Direct local connections do not hit this.</span></div>
      <div><strong>/api/stats returns an error</strong><span>Open devtools; if you see 503, <code>minicc --doctor</code> tells you which backend fell over.</span></div>
    </div>
  `;
}

function zhLimits() {
  return `
    <p class="manual-lede">诚实的边界——哪些承诺做了、哪些没做，以及为什么。</p>
    <ul class="manual-chapter-list">
      <li><strong>模型选择</strong> — 你可以用任意 OpenAI 兼容的网关（包括 wkapi.pro/v1 与你的私有代理）。Anthropic 也能走（<code>MINICC_PROVIDER_TYPE=anthropic</code>），但 token 计价只有 OpenAI 形状的账本。</li>
      <li><strong>图像</strong> — 附图与图生图可以送给模型，但不能让模型「看」——视觉能力完全取决于你选的模型。</li>
      <li><strong>网络访问</strong> — 默认沙箱不直接操作外网。工具层有常用 HTTP 客户端，但网关级联、长轮询与 websocket 不会自动生效。</li>
      <li><strong>远程工作区</strong> — 本地优先。远程仓库现在只能用 <code>git clone</code> 之后本地打开。</li>
      <li><strong>游戏</strong> — 纯前端（<code>web/game.js</code>），没有云存档；清缓存等于重开。</li>
      <li><strong>插件</strong> — MCP 工具可以挂上来；社区插件市场尚未存在。</li>
    </ul>
  `;
}

function enLimits() {
  return `
    <p class="manual-lede">Honest limits — what is shipped, what is not, and why.</p>
    <ul class="manual-chapter-list">
      <li><strong>Model choice</strong> — any OpenAI-compatible gateway (including wkapi.pro/v1 and your private proxy). Anthropic works too (<code>MINICC_PROVIDER_TYPE=anthropic</code>), but token pricing is only registered for the OpenAI shape.</li>
      <li><strong>Images</strong> — you can attach images, but whether the model can see them depends on the model you pick, not on us.</li>
      <li><strong>Network access</strong> — the default sandbox does not touch the outside world. The tool layer ships a conservative HTTP client; long-polling and websockets do not auto-engage.</li>
      <li><strong>Remote workspaces</strong> — local-first. A remote repo is usable after <code>git clone</code>, then opened locally.</li>
      <li><strong>Arcade</strong> — front-end-only (<code>web/game.js</code>), no cloud save; clearing the browser cache starts over.</li>
      <li><strong>Plugins</strong> — MCP tools can be mounted; there is no community marketplace yet.</li>
    </ul>
  `;
}

function zhAskDocs() {
  return `
    <p class="manual-lede">「问仓库」是把 RAG 真跑给你看的一扇窗：它先用 BM25（Okapi, k1=1.2, b=0.75）从本仓库的 <code>docs/</code>（含 <code>CONTRIBUTING.md</code>）与 <code>README.md</code> 取 top-k 段落，再让你配置好的模型——只读着这些段落回答，不让它凭空编。</p>
    <ol class="manual-list">
      <li><strong>打开</strong> — 侧边栏「问仓库」（档案馆旁边），或按 <code>Ctrl/⌘K</code> 输入「问仓库」。</li>
      <li><strong>提问</strong> — 用中文或英文问一个具体的问题。比如「为什么缓存命中率看起来很低？」「怎么跑压力测试？」选好引用来源数 k（2 / 4 / 6 / 8），按「提问」。</li>
      <li><strong>读答案</strong> — 答案只来自检索到的段落；顶部显示模型名与端点；<strong>引用来源</strong>逐条展开，可见段落文件名、BM25 分数与原文摘录；<strong>用量</strong>条显示网关回传的 prompt / completion / total tokens。</li>
      <li><strong>没答上</strong> — 如果 docs 里没有相关内容，模型会直接说「没有直接答案」，来源列表为空。换个关键词，或先在 docs/ 里确认有没有相应章节。</li>
      <li><strong>没 key</strong> — 检索本身在进程内完成；回答这一步调用你配置好的模型，因此仍需要 <code>MINICC_API_KEY</code> / <code>MINICC_BASE_URL</code> / <code>MINICC_MODEL</code>（与对话同一套 env）。没有 key 时，这里显示真实错误，而不是一段编造的回答。</li>
    </ol>
    <div class="manual-callout">
      <strong>诚实的事</strong>
      <p>BM25 是关键词检索，不是语义召回：它对精确措辞极强（「缓存命中率」一击直中），对同义改写一般。<code>chat/completions</code> 不回传 <code>cached_tokens</code>，所以用量条只显示网关如实给出的字段，不伪造命中率。api_key 不进 prompt、不被回显。</p>
    </div>
  `;
}

function enAskDocs() {
  return `
    <p class="manual-lede">Ask the Repo is RAG actually running, with the receipts shown. It first runs BM25 (Okapi, k1=1.2, b=0.75) over this repo's <code>docs/</code> (including <code>CONTRIBUTING.md</code>) and <code>README.md</code>, takes the top-k passages, then asks your configured model to answer from those passages alone.</p>
    <ol class="manual-list">
      <li><strong>Open</strong> — the “Ask the Docs” sidebar button (next to the Archive), or press <code>Ctrl/⌘K</code> and type “ask”.</li>
      <li><strong>Ask</strong> — type a concrete question in Chinese or English, e.g. “Why does the cache hit rate look so low?” or “How do I run the load test?” Pick k (2 / 4 / 6 / 8) and press Ask.</li>
      <li><strong>Read</strong> — the answer comes only from the retrieved passages; the meta line shows the model and endpoint; each <strong>source</strong> expands to the file name, the BM25 score and the verbatim excerpt; the <strong>usage</strong> pill shows exactly what the gateway reported (prompt / completion / total tokens).</li>
      <li><strong>No answer</strong> — if docs do not cover it, the model says so and the source list is empty. Rephrase, or check docs/ for a chapter first.</li>
      <li><strong>No key</strong> — retrieval runs entirely in-process; the answer step calls your configured model, so it still needs <code>MINICC_API_KEY</code> / <code>MINICC_BASE_URL</code> / <code>MINICC_MODEL</code> (same env as chat). Without one, the real error is shown, not a fabricated answer.</li>
    </ol>
    <div class="manual-callout">
      <strong>The honest part</strong>
      <p>BM25 is lexical, not semantic: it is excellent at exact phrases ("cache hit rate" lands dead-center) and average at paraphrase. <code>chat/completions</code> never carries <code>cached_tokens</code>, so the usage pill reports only the fields the gateway really gives — no invented hit rate. The api_key never enters the prompt nor is echoed.</p>
    </div>
  `;
}

function zhLoad() {
  return `
    <p class="manual-lede">这本书不光会问，它也会扛。这里教你亲手撞一遍：50 个并发、2 秒钟内两千四百多个请求、整机不倒。</p>
    <ol class="manual-list">
      <li><strong>先理解模型</strong> — minicc 是 local-first 工作台，不是多租户云：「用户数」就是你这一台机器，「大数据量」就是这棵文件树。它的吞吐能力写给本地个人用途，不是写给 SaaS。</li>
      <li><strong>怎么压测</strong> — 先起实例 <code>minicc web --workspace .</code>，再跑 <code>node scripts/load-test.mjs http://127.0.0.1:8765 50 15000</code>（20–50 路并发；末参数是压测时长毫秒；mock llm 反而更容易失真，请打真环境）。</li>
      <li><strong>读懂数字</strong> — 六个只读路径：<code>/api/health</code>、<code>/api/metrics</code>、<code>/api/digest</code>、<code>/api/stats</code>、<code>/api/roadmap</code>、<code>/api/workspace</code>。本机实测（2026-11-15）：c=50、20s 内、**2,490 次响应、0 错误**；p50 ≈ 160–200ms。</li>
      <li><strong>为什么没崩</strong> — 三道防线同时生效：启动后台预取（<code>minicc-prefetch</code> 线程，<code>--no-prefetch</code> 可退出）、<code>AgentService._memo_http</code> single-flight 记忆（TTL 边界不再 N 路同时重建，TTL=30s / workspace=10s）、<code>MiniccHTTPServer.request_queue_size=128</code>（内核丢 SYN 的根治）。</li>
      <li><strong>还会崩在哪里</strong> — GIL 还在：50 路以上共鸣时，这是延迟（不是正确性）的主要来源。登记的下一步是 aiohttp / uvloop 或进程池——不伪造承诺。</li>
    </ol>
    <div class="manual-callout">
      <strong>诚实的事</strong>
      <p>「预取」可用 <code>--no-prefetch</code> 关闭；注册发现不到新集群就会看到 503——不要用它当监控面（用 <code>--doctor</code>）。Redis 实时缓存会报 <code>redisLive</code>；代理 shard 亲和性不在客户端射程内。数字会随你的树尺寸变得不同，不要抄我的数。</p>
    </div>
  `;
}

function enLoad() {
  return `
    <p class="manual-lede">This book doesn't only ask, it holds. Here is how to crash the door yourself: 50 concurrent workers, twenty seconds, two thousand round trips — and the house still standing.</p>
    <ol class="manual-list">
      <li><strong>Understand the model first</strong> — minicc is a local-first workbench, not a multi-tenant SaaS: your user count is this machine, your "big data" is this file tree. Its throughput is honest at local-personal scale, not at fleet scale.</li>
      <li><strong>How to load</strong> — start an instance <code>minicc web --workspace .</code>, then run <code>node scripts/load-test.mjs http://127.0.0.1:8765 50 15000</code> (20–50-way concurrency; the last argument is the window in ms).</li>
      <li><strong>Read the numbers</strong> — six read-only paths: <code>/api/health</code>, <code>/api/metrics</code>, <code>/api/digest</code>, <code>/api/stats</code>, <code>/api/roadmap</code>, <code>/api/workspace</code>. Measured on this box (2026-11-15): c=50, 20-second window — **2,490 responses, zero errors**, p50 ≈ 160–200 ms.</li>
      <li><strong>Why it didn't fall</strong> — three defenses working together: boot-time prefetch (<code>minicc-prefetch</code> thread, <code>--no-prefetch</code> to exit), single-flight memoization in <code>AgentService._memo_http</code> (the TTL boundary can no longer stampede N rebuilds; TTL is 30s for packs, 10s for workspace), and <code>MiniccHTTPServer.request_queue_size = 128</code> (the kernel-dropped-SYN root cause).</li>
      <li><strong>Where it still can fall</strong> — the GIL remains: above ~50-way the tax is latency, not correctness. aiohttp/uvloop or a process pool is the recorded next step — no fake promises.</li>
    </ol>
    <div class="manual-callout">
      <strong>The honest part</strong>
      <p>The prefetch is optional (<code>--no-prefetch</code>); Redis reports as live backend when the local LRU joins the pool; proxy shard affinity is outside the client's reach. Numbers differ on your tree — do not copy mine.</p>
    </div>
  `;
}

function zhCloud() {
  return `
    <p class="manual-lede">minicc 的核心是 Python（引擎），而 Spring Cloud plane 是它周围的整套分布式壳——注册发现、边缘路由、配置下发、只读检查器、限流与熔断全栈真跑。这一章就是「怎么在自己机器上拉起整套平面」。</p>
    <ol class="manual-list">
      <li><strong>先理解组件</strong>：registry=配置注册中心、config=配置下发、gateway=边缘网关（lb:// 负载均衡）、inspector=只读工作区检查（Refuses outside）、tasks=只读任务历史（SQLite）、insights=只读聚合洞察（fleet 拓扑成群）、bridge=Python 与 Java 的桥。</li>
      <li><strong>前置：Docker + JDK 21 + Maven</strong>：Java 侧所有服务都跑在自己机器上。如果你只想感受效果，跳到第五步。</li>
      <li><strong>构建并启动</strong>：<code>cd minicc-cloud && mvn -B test</code>，再 <code>mvn -DskipTests package</code>，再 <code>docker compose up -d</code>。</li>
      <li><strong>端口被占用怎么办</strong>：用 <code>MINICC_CLOUD_*_PORT</code> 覆盖，例如 <code>MINICC_CLOUD_GATEWAY_PORT=8090 docker compose up -d</code>。</li>
      <li><strong>验收</strong>：<code>docker compose ps</code> 全部 healthy；<code>curl localhost:8080/api/insights/fleet</code> 看到真实的 registry 拓扑（up/down/instances）；<code>curl localhost:8080/api/insights/summary</code> 看到任务与审计行数。</li>
      <li><strong>限流实测</strong>：<code>SPRING_PROFILES_ACTIVE=ratelimit docker compose up -d</code>，然后用 <code>wrk</code> 或 <code>hey -z 20s -c 120 localhost:8080/api/health</code> 轰——你会看到 <code>429 Too Many Requests</code> 的流量回填，以及 <code>gateway.rate_limited{route}</code> 的 Micrometer 计数递增。</li>
      <li><strong>熔断回环</strong>：关掉 insights（<code>docker compose stop insights</code>）→ 等 30s → <code>curl localhost:8080/api/insights/summary</code> 返回 <em>honest 503 + fallback</em> → 拉起 insights → 再请求 → 200。这是 Resilience4j 半开 → 关闭的完整回环。</li>
      <li><strong>缓存失效</strong>：网关走 RabbitMQ 广播 <code>fanout</code>，inspection 把 Python dict cache 失效——你看不到进程崩溃也看不到 stale data。</li>
    </ol>
    <div class="manual-callout">
      <strong>写在前面的诚实</strong>
      <p>Spring Cloud plane 的所有模块都在本机 <code>mvn test</code> 137+ 个测试全绿（gateway/inspector/tasks/insights 四个关键服务各占一块）。它不是概念性展示——它是可以落地拉起的真实系统。com.minicc.cloud 每个 Java 文件都有自己的单元测试，RabbitMQ/Redis 失效/限流/熔断都是真机回环数据，不是 mock。</p>
    </div>
    <p>查看完整架构：<code>../docs/SERVICE_PLANE_PLAN.md</code>；所有端点与环境变量：<code>../docs/SERVICE_PLANE_OPERATOR.md</code>。</p>
  `;
}

function enCloud() {
  return `
    <p class="manual-lede">minicc's core is Python — but the Spring Cloud plane is the distributed shell around it: discovery, edge routing, config delivery, a read-only inspector, and a load-tested gateway with per-IP rate limits and a Resilience4j circuit breaker, all running on your machine. This chapter is how to actually stand it up yourself.</p>
    <ol class="manual-list">
      <li><strong>Know the parts</strong>: <code>registry</code>=Eureka service discovery, <code>config</code>=Config Server, <code>gateway</code>=Spring Cloud Gateway with <code>lb://</code> load balancing, <code>inspector</code>=read-only workspace change service (refuses paths outside its roots), <code>tasks</code>=read-only task history (SQLite), <code>insights</code>=read-only aggregate summary + fleet topology, <code>bridge</code>=the single seam between Java and Python.</li>
      <li><strong>Prerequisites</strong>: Docker + JDK 21 + Maven. Everything runs on your laptop. If you just want to see it work, skip to step 5.</li>
      <li><strong>Build &amp; launch</strong>: <code>cd minicc-cloud && mvn -B test</code>, then <code>mvn -DskipTests package</code>, then <code>docker compose up -d</code>.</li>
      <li><strong>Port collision?</strong> Override with <code>MINICC_CLOUD_*_PORT</code>, e.g. <code>MINICC_CLOUD_GATEWAY_PORT=8090 docker compose up -d</code>.</li>
      <li><strong>Verify</strong>: <code>docker compose ps</code> all healthy; <code>curl localhost:8080/api/insights/fleet</code> returns the real registry topology (per-service instance count + UP/DOWN); <code>curl localhost:8080/api/insights/summary</code> returns task totals + audit line count — live data from SQLite.</li>
      <li><strong>Rate-limit demo</strong>: <code>SPRING_PROFILES_ACTIVE=ratelimit docker compose up -d</code>, then hammer it with <code>hey -z 20s -c 120 localhost:8080/api/health</code> — you'll see <code>429 Too Many Requests</code> alongside <code>gateway.rate_limited{route}</code> incrementing in Micrometer.</li>
      <li><strong>Circuit-breaker round trip</strong>: <code>docker compose stop insights</code> → wait 30 s → <code>curl localhost:8080/api/insights/summary</code> returns <em>honest 503 + fallback</em> → <code>docker compose start insights</code> → request again → 200. That's the full Resilience4j half-open → closed round trip, measured for real.</li>
      <li><strong>Cache invalidation</strong>: the gateway broadcasts <code>fanout</code> over RabbitMQ to the inspector, which invalidates Python-side cached routes — you never sit on stale data and you never see a Python process crash.</li>
    </ol>
    <div class="manual-callout">
      <strong>Honest footnote</strong>
      <p>Every module in the plane runs its own real test suite; the gateway/inspector/tasks/insights cut has 137+ tests and all of them pass on your machine (<code>mvn test</code>). This is not a conceptual demo — the RabbitMQ round trip, the Redis token bucket, the Resilience4j fallback all have live runs recorded in CHANGELOG; nothing here is a mock.</p>
    </div>
    <p>Full architecture: <code>../docs/SERVICE_PLANE_PLAN.md</code>. Every endpoint + env var: <code>../docs/SERVICE_PLANE_OPERATOR.md</code>.</p>
  `;
}

function zhCiWall() {
  return `
    <p class="manual-lede">这座仓库被 CI 墙挡住了好几次；也正因为它挡住了，这道墙一定 worth reading once。</p>
    <ol class="manual-list">
      <li><strong>10 个门同时亮</strong> — Ubuntu Python · Windows Python · Claim Checkers（doc_pointers + route-coverage + impact floor）· JavaScript syntax · Spring Cloud plane mvn · M1 reliability probe · PR eval gate · Playwright web smoke · Playwright unreachable-provider（must fail）· Nightly eval（real key；不配则 skipped）。一个红，任何合并都过不了。没有任何 pypass 被授权。</li>
      <li><strong>Doc gates 不是碍眼</strong> — <code>test_no_document_quotes_a_content_addressed_bundle.py</code> 是这一规则的典型：文档里不许出现「<code>app.12f515310f8e7b2a.js</code>」这种每次重建就会失效的捆绑包名字，否则对应那段文字会在下一次 build 之后变成死链。那条规则上路之后，帮助自己记录的一行 ROADMAP 立即被它自己绊住——红了一次，改成稳定通道 <code>web/app.js</code>，绿了。</li>
      <li><strong>Tracked bytes 不能含控制字符</strong> — <code>test_tracked_text_files_hold_no_bare_control_bytes</code> 拒绝任何带裸控制字节的 tracked 文本——即使是 <code>.log</code> 文件。我们曾因为一个本地重测残留的 <code>_fail_ci.json</code> 把本地 pytest 打红一整轮；下次启动大概率直接清空、重跑、绿。</li>
      <li><strong>自查先于 push</strong> — 这个仓库自带的 <code>.codex</code> pre-commit 钩子（<code>[codex-global pre-commit] fast checks</code>）在提交前先过一遍快速门禁。钩子红——push 失败（exit 1）。这本书希望钩子永远红得提醒你。</li>
      <li><strong>5,701 tests</strong> — 这个数字不是展示数字。每一个数字后面是一个文件、一个失败案例、一个回归断言。每个单元大约 0.8–1.5 秒。全量拉下来大概 78 分钟。不是所有 tests 都跟 AI 有关——大部分只是确保简单不退步。</li>
      <li><strong>CI 失效怎么排查</strong> — 首先看哪个 job 红了。如果弄的是 document gate — 哪个文件、哪一行。如果是 Python — 读 traceback；大概率是 document 自己引用不到自己。如果是Playwright — 打开 <code>test:smoke</code> 那一步回放，字节序/locale schema。</li>
    </ol>
    <div class="manual-callout">
      <strong>诚实的事</strong>
      <p>本仓库中所有「漂亮话」都是 CI 翻译出来的。没有「我们宣称它稳定了」这种话；只有「它每一轮都跑过一遍」的事实——你读到的每一句 README，都是先被测试读一次然后才敢被你看见的。每一条都不是可信人格故事的产物。</p>
    </div>
  `;
}

function zhEvidence() {
  return `
    <p class="manual-lede">没有任何一条 README 里的承诺是靠相信印上去的。本章把这个仓库自己的“宪法”摊开给你看。</p>
    <ol class="manual-list">
      <li><strong>README 不能随便写</strong> — <code>tests/test_readme_capability_claims.py</code> 就是会"读你自己的 README 然后走红"的那个测试。每一句引用都必须能从仓库里打出来；打不出来，CI 变红。所以你看到的 README 每一行都对应一段 tracked 的证据。</li>
      <li><strong>一条常量一个家</strong> — 命名成 <code>tests/test_the_&lt;name&gt;_have_one_home.py</code> 的 15+ 个测试，每条钉死一个常量必须返回同一个值。不这么写，同名异值问题就会在代码评审时发现不了。本仓库几乎所有 "done" 状态、颜色名、网关状态码、状态枚举、sentinel key——都被钉死了。</li>
      <li><strong>证据 census</strong> — <code>tests/test_tracked_evidence_census.py</code> 统计所有指向测试文件的文字引用、路径存在性、boundary sk- 泄漏格网。每推一次 push，census 重新数一遍。任何一个漂移的数字都在 CI 上下一个红点。</li>
      <li><strong>index 与路由不会自动迷路</strong> — <code>docs/INDEX.md</code> 必须列出 <code>docs/</code> 下每一个文件。不列 = CI 红 = 不能合并进主分支。这不是审美偏好，是纪律。</li>
      <li><strong>你在读的每一件展品都是一次性交付</strong> — 这一句本身也是被 <code>test_doc_pointers.py</code> 盘的；hashed 文件名变了整段就烂，所以 hash 被剔出所有文档；新增活跃 bundle 只能叫 <code>web/app.js</code>、<code>web/game.js</code>、<code>web/styles.css</code>。</li>
      <li><strong>红一次不算事故</strong> — 本质上是一个工程纪律：每个红点都是发现一个裂缝；绿一个立一段墙。本仓库 Ch.44（无眠）比 Ch.39（灯火）多的是一个概念：<strong>醒来之后整夜绿闸</strong>。</li>
    </ol>
    <div class="manual-callout">
      <strong>诚实的事</strong>
      <p>这里没有一条承诺是外包给“信任我”的：所有的数字、路径、接口名——每一条都必须在 git 里寻到，并且满足那一个测试。你看见的任何 claim；如果你找不到对应的那个测试，本仓库就不是来骗你的，就是 bug。</p>
    </div>
  `;
}

function zhFanout() {
  return `
    <p class="manual-lede">「并行子智能体」是你习惯了之后再回来看，才会说：啊，原来这个不是玄学，是纯评分表。 — 见 minicc/agent/orchestration.py。</p>
    <ol class="manual-list">
      <li><strong>核心常量</strong> — <code>AUTO_FANOUT_THRESHOLD = 4</code>（打分多少才派扇出）· <code>AUTO_FANOUT_MAX_CHILDREN = 3</code>（一次最多派多少子任务）。score 从 0 起算，没达到 4 不派，达到后 ≥ 7 或 explicit 就是满 3 个子任务，否则 2 个。</li>
      <li><strong>评分项一：文本长度</strong> — ≥ 260 字 +2；≥ 150 字 +1。150/260 是 P50/P75 的大致分界不是随意猜测。</li>
      <li><strong>评分项二：连续目标 connector</strong> — 正则带 word boundary：<code>and</code> / <code>also</code> / <code>additionally</code> / <code>then</code> / <code>after</code>；≥ 3 个 +2；≥ 1 +1。早期 substring 会让 <code>understanding</code> 触发 <code>and</code>（单次+1 但攒够很恐怖），M8-T290 把这层洗掉了。</li>
      <li><strong>评分项三：意图维度 DIMENSION_PATTERNS</strong> — 五组正则：<code>inspection</code>（检视/review/analy[sz]...）· <code>implementation</code>（实现/implement/build/fix/add/...）· <code>verification</code>（验证/test/verify/benchmark/...）· <code>research</code>（调研/search/web/docs）· <code>presentation</code>（前端/页面/design/landing）。≥ 4 种 +3，≥ 3 种 +2，≥ 2 种 +1。</li>
      <li><strong>评分项四：文件引用数</strong> — <code>_FILE_RE</code> 抽取 path-like tokens（<code>.py/.ts/.json/.md</code> ...）≥ 3 +2，≥ 1 +1。加上用户明说“parallel/并行/multi-agent/subagent”那一类，就让 score 至少到 4。</li>
      <li><strong>opt-out</strong> — “just answer / just respond / 只是回答 …”直接返回 0，用户最不耐烦时就不调度。</li>
      <li><strong>扇出之后会真正走到 execute_dag</strong> — <code>minicc/agent/graph.py::execute_dag</code>，真实 DAG，只读节点先行（readonly / review / merge）并行，write 节点在最后（单线程）。ledger 里每个节点都有自己独立的 timeout bucket（node_budget_from）。</li>
      <li><strong>失败如何被保持住</strong> — M8-T296：子任务跳过/超限写 BudgetExceeded，结果还是会带全部成功节点的 token/latency 回填，<code>aggregate_dag_tokens</code> 一次合上去——父任务能看到真实花费，不会流失。</li>
    </ol>
    <div class="manual-callout">
      <strong>诚实的事</strong>
      <p>评分全系统都是可调参数，写在源代码里，数值来源是仓库里每个任务的真实跑动后测得。你看到的每一条加减都对应落档的 git commit。哪一个子代理不是并行跑的都能从 <code>minicc/web.py</code> 的 <code>/api/audit</code> 自己复核——不做炫技，只做账本。</p>
    </div>
  `;
}

function zhSandbox() {
  return `
    <p class="manual-lede">小册子最后一章：你有一位不信任 Agent 的朋友——他可以，任何人都可以。可是当模型在 workspaces 里横冲直撞，“沙盒”就是你的邻居请你吃饭时穿的围裙：不当证牌，防止锅烧着厨房。</p>
    <p><strong>本章做什么</strong></p>
    <ol class="manual-list">
      <li><strong>SANDBOX_MODE</strong> — 三个合法值：<code>host</code>（直接在本地跑，默认）、<code>docker</code>（强制 Docker 隔离）、<code>auto</code>（有 Docker 就用 Docker，没有就退回 host，而不是拒服务）。如果 Docker 配成 docker 但机器上没有 Docker——这是第四种答复：<code>backend=unavailable</code>，ToolResult 原样标记 <code>sandbox_unavailable</code>，<strong>这是诚实的拒绝，而不是悄悄退 host</strong>。</li>
      <li><strong>Docker 的护城河（每一条都是真实配置，不是隐喻）</strong> — <code>--network none</code>（无网络）、<code>--cap-drop ALL</code>（撤掉所有 capabilities）、<code>--security-opt no-new-privileges</code>（不能获得新特权）、<code>--pids-limit 256</code>（最多 256 个 pid）、<code>--memory 512m</code>（约 512MB，保证 pytest/compileall 能跑起来同时不会失控）、<code>--read-only</code>（只读根文件系统）、<code>--tmpfs /tmp</code>（/tmp 走 tmpfs）、<code>-v <workspace>:/workspace:rw</code>（工作区可写，因为 Agent 要干活）。Linux 上还会加 <code>--user</code> 切到非 root（Windows/macOS 不加，因为 Docker Desktop 会拒）。</li>
      <li><strong>合适的语气</strong> — “火爆”不是一个 bug，是边界声明：这份配置本身就是声明。Agent 在它被编译时知道自己在限制里工作——而你知道它能改你的磁盘只到工作区为止，不改根。</li>
      <li><strong>MINICC_SANDBOX=host 时</strong> — 每个 bash/python 都在你的进程里、你的身份下、真实的系统调用上跑。承诺 = 你对这些调用完全负责，Agent 只是另一个 CLI 客户端。</li>
      <li><strong>MINICC_SANDBOX_IMAGE</strong> — 换个 base：默认 <code>python:3.11-slim</code>。换之前确认你的 toolchain 仍在里面，否则你等最久的不是构建，而是为什么一直 exit 127。</li>
    </ol>
    <div class="manual-callout">
      <strong>诚实的边界</strong>
      <p>沙盒覆盖的是“执行时影响”，不是“参数泄露”，更不是“网络响应体解释”。模型仍然能读工作区里任何文本，包括你的 <code>.env</code>（它按读取优先级找，但这不是拒读）。<code>--network none</code> 挡住网络，但挡不住模型把 key 写到 workspace 里面被你自己复制到外网。沙盒是你挡住 Agent 崩溃的工具，不是你挡住自己好奇心的工具。</p>
    </div>
  `;
}

function zhCacheAffinity() {
  return `
    <p class="manual-lede">「亲和」是这套系统里最便宜、也最难的一类缓存：它不在你的机器上，它在网关里。每一次请求都携带 prefix 的字节指纹——同一 workspace 的系统提示 byte-stable，指纹就一致，网关就命中；prefix 差一个字节，整段前缀从头再付。</p>
    <ol class="manual-list">
      <li><strong>什么决定命中率</strong> — 亲和键由 <code>minicc/cache_keeper.py::_derive_cache_key(base_url, model)</code> 派生：<code>minicc-</code> + sha256(gateway|model) 的前 16 个 hex；显式设置 <code>MINICC_PROMPT_CACHE_KEY</code> 时显式键优先。命中前提：byte-identical prefix（system prompt + tools）+ 处于网关 prefix TTL 之内 + 显式 / 派生键一致。TTL 超时、compaction、换模型、改 tools 任一触发，整段 prefix 重付。</li>
      <li><strong>真实测量</strong> — 历史基线冻结：wkapi.pro · gpt-6-sol（2026-11-15）：warm 热命中 <strong>98.3%</strong>；冷突变 5504/5735 = 96.0%。新 lane（api.aizzz.xyz · gpt-6.1-terra，经本机 Clash Verge Rev 混合端口 127.0.0.1:7897，2026-11-16）：冷启动 4224/5731 = 73.7%；near-identical 后缀请求 5504/5737 = <strong>95.9%</strong>。直连六次探针全部 HTTP 403——地理封锁，代理是唯一通路。</li>
      <li><strong>保活机制（cache_keeper）</strong> — <code>minicc/cache_keeper.py</code> 每 220 秒（可用 <code>MINICC_CACHE_KEEPER_INTERVAL</code> 调，范围 60–900），对同一 prefix 打一枚微型 <code>responses.create</code> warm 请求：约 20 个 output token / 次，无工具调用；失败只计数不抛；每一次 warm 都在 /api/provider-ping 上报；可用 MINICC_CACHE_KEEPER=0 关掉。网关 prefix TTL 目测约 5 分钟——超过这个缺口，下一次全额重付。</li>
      <li><strong>为什么「一直显示非流」</strong> — 早期 lane 存在「流式缓存指标更稳、非流命中更低」的观察；测量脚本（<code>scripts/measure_cache_affinity.py</code>）为此固定 stream=true、temperature=0、复读同一前缀，并把命中统计显式打印。non-stream 行为未伪造任何「流式更快」的叙事——它只是同一套 prefix 纪律下的另一种 wire shape。</li>
      <li><strong>诚实的用量口径</strong> — chat/completions 不回传 cached_tokens；用量条只呈现网关如实给出的三个键（<code>measured_usage</code>：prompt / completion / total），若有 cached_tokens 字段则附加 <code>prompt_cache_hit_tokens</code>——<strong>绝不伪造命中率</strong>；cache_keeper 的 warm 不记入 agent 的 token 账。</li>
      <li><strong>什么最值钱</strong> — prefix 的字节稳定性。system prompt 与 tools 清单不轻变、hint 不乱加空格、cache_key 不在会话间漂移；一次测量的机会成本只有一个 5731-token 的请求。</li>
    </ol>
    <div class="manual-callout">
      <strong>诚实的事</strong>
      <p>Cache Affinity 不是银弹：它救不了换模型、救不了 compaction、救不了五分钟 TTL。这卷说明书写的是测量与机制——数字只有你跑一次测量脚本就能复现。写在这里是为了让下一个人少踩一盏灯。</p>
    </div>
  `;
}

function zhStateGraph() {
  return `
    <p class="manual-lede">minicc 跑起来之后，每个任务先落在一张<strong>受限的状态图</strong>上——这从来不是把一个 <code>if</code> 嵌套叫做 Agent 的包装层，而是真的图。</p>
    <p class="manual-lede">这一章只讲三件事：<strong>阶段轴</strong>（负责记录 trace）、<strong>只读 DAG 执行器</strong>（<code>execute_dag</code>）和<strong>预算护栏</strong>（<code>BudgetExceeded</code>）。</p>
    <div class="manual-grid-list">
      <div><strong>StateGraph 是阶段轴，不是执行器</strong><span>真正跑任务的是 <code>run_agent</code> 工具循环。StateGraph 负责回答「现在到哪一步了」——<code>intake → plan → inspect → implement → verify → repair → summarize</code> 每个节点都在任务开始之前登记好。</span></div>
      <div><strong>阶段顺序（V1 七段）</strong><span>intake 读懂问题 → plan 把路子走完 → inspect 先读再写 → implement 真正动手改 → verify 跑测试 → repair 只有 verify 失败才进来、最多两轮 → summarize 终点。</span></div>
      <div><strong>execute_dag 只跑只读节点</strong><span>DAG 里只许出现 readonly / review / merge——写节点（<code>write</code> / <code>exec</code>）从入口就被拒。这不是「不推荐这样做」，是「写了也不会执行」。</span></div>
      <div><strong>不可缩引的硬限</strong><span>节点数 ≤ 32、深度 ≤ 16、并行 ≤ 4，入口先检测环——带自环的计划根本不会被放出来执行。外加一枚 <code>BudgetExceeded</code>：图最多走 64 步——永远不会让一个烂设计把 token 吃到天荒地老。</span></div>
      <div><strong>固定三个模板</strong><span><code>inspect_summarize</code>：扫一遍 → 写总结。<code>inspect_implement_verify</code>：检 → 写 → 验 → 总结。<code>parallel_inspect</code>：N 个只读扫描并发至 merge 汇聚 → 再进 implement / verify / summarize 管线。同一份白名单，没有任何一份能轻易绕过。</span></div>
    </div>
    <p class="manual-footnote">这不是 LangGraph 的山寨——它是 minicc 专用的仪表轴。真想看别的（durable execution、checkpointing、human-in-the-loop、Send( fanout)、Send==send）请直接读 <code>docs/AGENT_LLM_ROADMAP.md</code> 里的可观测编排层小节；真正落地就在 <code>minicc/agent/graph.py</code>。——三件事的本质是一样的：让每次流转都能被看见。</p>
  `;
}

function enCiWall() {
  return `
    <p class="manual-lede">This repo has been collared by its own CI wall many times — and it exists precisely because every fire it prevented is a fire you'll never notice.</p>
    <ol class="manual-list">
      <li><strong>Ten independent gates light together</strong> — Python on ubuntu-latest × Python on windows-latest × Claim Checkers (doc_pointers + route_coverage + impact_floor) × JavaScript syntax × Spring Cloud plane (mvn) × M1 reliability probe × PR eval gate × Playwright web smoke × Playwright unreachable-provider (must fail) × Nightly eval (real key, skipped when absent). Any red gate blocks the merge. Nobody has an off-switch.</li>
      <li><strong>Doc gates are not decoration</strong> — <code>test_no_document_quotes_a_content_addressed_bundle.py</code>: documentation must never name a hash-tagged bundle. The build closered then fails the gate -- exactly the mistake caught in this very cycle: a referenced hash in ROADMAP broke on the very next rebuild. The no-gate library closed it within the same commit.</li>
      <li><strong>Tracked bytes cannot contain control characters</strong> — <code>test_tracked_text_files_hold_no_bare_control_bytes</code> forbids bare control bytes anywhere tracked; even a stray <code>.log</code> from local output gets caught — the repo was once red on exactly that, turning a routine re-run instantly green.</li>
      <li><strong>Self-check before push</strong> — the <code>.codex/pre-push</code> hook runs <code>[codex-global pre-commit]</code>; if any of that gates — a fast gate — doesn't pass, the push exits non-zero. Reading this is cheaper than seeing it red in GitHub.</li>
      <li><strong>5,701 tests is not a marketing number</strong> — roughly a thousand test files at ~0.8–1.5 seconds each; the whole suite clocks out on this machine at ~78 minutes. The tests don't matter because they all test AI; they matter because each one is a fire someone chose to prevent in advance.</li>
      <li><strong>When CI goes red</strong> — first, find which job is red. Document gate? The line and the file it points at guide the fix. Python? The traceback almost always says exactly which assertion tripped. Playwright? The smoke's failure log lists the first mismatched assertion and the locale prefix it was observed under.</li>
    </ol>
    <div class="manual-callout">
      <strong>Honest limits</strong>
      <p>Every “nice thing” in this repo is the output of the CI passing, not an opinion. Nothing is reliable because somebody says it is; everything you read here got checked in and then checked out and read and scanned before it reached you. No marketing claims anywhere in here outlives its test.</p>
    </div>
  `;
}

function enEvidence() {
  return `
    <p class="manual-lede">Every promise in the README was earned by a gate that actually runs against the checked-out tree. This chapter hands you the constitution.</p>
    <ol class="manual-list">
      <li><strong>READMEs cannot fib</strong> — <code>tests/test_readme_capability_claims.py</code> parses your README on every CI run and refuses any claim the repo cannot back up. If a sentence you wrote cannot be reproduced from the checkout, CI goes red. So every claim you see in the README exists because a test told it to exist.</li>
      <li><strong>One home per constant</strong> — the family of <code>tests/test_the_&lt;name&gt;_have_one_home.py</code> tests enforce that a named constant has exactly one identity across the codebase. Statuses, sentinels, keys, colors, codes all comply. Nobody is allowed to spell the same concept two different ways without a gate noticing.</li>
      <li><strong>Evidence census</strong> — <code>tests/test_tracked_evidence_census.py</code> walks the docs and reconciles every claim with a file: does the path exist? does the number match? does the name appear twice? Every push invalidates every citation until the next clean run confirms it again.</li>
      <li><strong>INDEX.md is part of the contract</strong> — <code>docs/INDEX.md</code> must name every file under <code>docs/</code>; a missing entry fails the gate <code>test_docs_index_enumerates_every_docs_md.py</code> and the push cannot land on <code>main</code>.</li>
      <li><strong>Every beautiful exhibit is one push deep</strong> — even the sentence you're reading is validated by <code>test_doc_pointers.py</code>: document-references must resolve to existing files; hashed bundle names are forbidden in docs because they break on the next rebuild; stable paths are the contract between the writing and the artifact.</li>
      <li><strong>Red gates are not failures of faith</strong> — each red gate is a found crack; each green gate is a wall built in its place. Ch.44 carries more wisdom than Ch.39 because the world learned the difference between "we stopped to fix it" (the storms of Ch 38→39) and "it kept going green for weeks" (starting Ch 41+).</li>
    </ol>
    <div class="manual-callout">
      <strong>Honest limits</strong>
      <p>There is no claim here that requires you to trust the author — every one is backed by a test whose exit status you can inspect in this very checkout. If you cannot find the test for a claim you expected, that is the definition of a bug in this repo, not a fudge.</p>
    </div>
  `;
}

function enFanout() {
  return `
    <p class="manual-lede">Fanout is not magic, it's a scorecard — literally eight constants and a few regexes in <code>minicc/agent/orchestration.py</code>.</p>
    <ol class="manual-list">
      <li><strong>Core constants</strong> — <code>AUTO_FANOUT_THRESHOLD = 4</code> (the score fan-out requires) · <code>AUTO_FANOUT_MAX_CHILDREN = 3</code> (the cap on parallel children). Score starts at 0; below 4 we fan out nothing. At 4+, a score of ≥ 7 or an explicit callout unlocks 3 children, otherwise 2.</li>
      <li><strong>Signal 1 — message length</strong> — ≥ 260 chars scores +2; ≥ 150 chars scores +1. P50/P75 length thresholds, not a guess.</li>
      <li><strong>Signal 2 — connectors</strong> — word-boundary regexes (<code>and</code> / <code>also</code> / <code>additionally</code> / <code>then</code> / <code>after</code>) catch multi-goal requests. ≥ 3 fires +2; any fires +1. <code>understanding</code> no longer raises the score after M8-T290 cleaned up bare-substring matches.</li>
      <li><strong>Signal 3 — intent dimensions</strong> — <code>DIMENSION_PATTERNS</code> maps five names to matching regexes: <code>inspection</code> (review/analy[sz]...) · <code>implementation</code> (implement/build/fix/add/migrat...) · <code>verification</code> (test/verify/benchmark/validat...) · <code>research</code> (search/web/docs) · <code>presentation</code> (frontend/design/landing...). ≥ 4 distinct → +3; ≥ 3 → +2; ≥ 2 → +1.</li>
      <li><strong>Signal 4 — file mentions</strong> — <code>_FILE_RE</code> extracts path-like tokens (<code>.py/.ts/.json/.md</code> …). ≥ 3 → +2; ≥ 1 → +1.</li>
      <li><strong>Explicit opt-in</strong> — "just answer / just respond …" short-circuits to 0. Asking for "parallel / multi-agent / subagent" lifts score to at least the threshold.</li>
      <li><strong>Fan-out actually lands in execute_dag</strong> — <code>minicc/agent/graph.py::execute_dag</code>. Nodes of kind <code>readonly</code>/<code>review</code>/<code>merge</code> run in parallel waves ≤ 4 concurrent; the write node runs alone at the end. Each child picks up a sub-<code>Budget</code> (derive <code>node_budget_from</code>), its own timeout bucket, its own token counter.</li>
      <li><strong>Budget failure is honest</strong> — M8-T296: child hits <code>BudgetExceeded</code>, DAG returns <code>partial</code> with all the tokens every successful sibling honestly spent. <code>aggregate_dag_tokens</code> rolls them into the parent's accounting, never lost.</li>
    </ol>
    <div class="manual-callout">
      <strong>Honest limits</strong>
      <p>Every "should I fan out?" decision in this repo is a deterministic function of the request string. Nothing here calls a model to plan parallelism — so it can't fail silently or drift. Verifiable in the source itself, reproducible with one line of Python: <code>from minicc.agent.orchestration import assess_complexity; assess_complexity("...").snapshot()</code>.</p>
    </div>
  `;
}

function enSandbox() {
  return `
    <p class="manual-lede">A chapter for the friend who does not trust the agent yet — nobody has to, and that is healthy. When a model walks into your workspace with its hands swinging, the sandbox is the apron on the wall: not a certificate you frame, but the thing that keeps the kitchen from catching fire.</p>
    <p><strong>What this chapter covers</strong></p>
    <ol class="manual-list">
      <li><strong>SANDBOX_MODE</strong> — three legal values: <code>host</code> (run on the local machine, the default), <code>docker</code> (force Docker isolation), <code>auto</code> (use Docker if it is available, otherwise fall back to host — never silently refuse). And a fourth honest answer exists: <code>backend=unavailable</code> when Docker is configured but the machine is not able to run it. That answer is <code>ToolResult(status="error", security_tags=["sandbox_unavailable"])</code>, exactly as the code emits. Not a quiet host fallback; an honest refusal.</li>
      <li><strong>The Docker moat — every rule is a real configuration, not a metaphor</strong> — <code>--network none</code> (no network), <code>--cap-drop ALL</code> (every capability dropped), <code>--security-opt no-new-privileges</code>, <code>--pids-limit 256</code> (256 pids max), <code>--memory 512m</code> (~512 MB — enough for pytest/compileall, not enough for you to notice your RAM disappear), <code>--read-only</code> (read-only root filesystem), <code>--tmpfs /tmp</code> (tmpfs-mounted /tmp), <code>-v &lt;workspace&gt;:/workspace:rw</code> (the workspace stays writable, because the agent has work edit to). On Linux it also drops <code>--user</code> to non-root (skipped on Windows/macOS because Docker Desktop refuses).</li>
      <li><strong>The right mental model</strong> — the configuration itself is the contract. The agent was compiled inside a box; you know your files are yours; you know the blast radius stops at the workspace boundary.</li>
      <li><strong>MINICC_SANDBOX=host</strong> — every bash/python call runs in your process, with your identity, on real syscalls of the real host. The promise to keep: you own those calls; the agent is just another CLI client.</li>
      <li><strong>MINICC_SANDBOX_IMAGE</strong> — swap the base image; default is <code>python:3.11-slim</code>. Before swapping, make sure your toolchain still lives inside it, otherwise you spend the wait on why exit 127 keeps happening.</li>
    </ol>
    <div class="manual-callout">
      <strong>Honest limits</strong>
      <p>Sandbox covers execution side effects, not prompt-supplied secrets, and not the way a model narrates what it saw. The model can still read anything readable in the workspace, including your <code>.env</code> (the resolution path finds it whether you like it or not). <code>--network none</code> blocks the wire — it cannot block the model from writing a key into a file you later copy elsewhere. The sandbox contains a swerving agent; it does not contain your own curiosity.</p>
    </div>
  `;
}

function enCacheAffinity() {
  return `
    <p class="manual-lede">“Affinity” is the cheapest, hardest cache in this system: it does not live on your machine, it lives in the gateway. Every request carries a byte fingerprint of its prefix — a byte-stable system prompt for a given workspace means the fingerprint matches and the gateway hits; one stray byte and the whole prefix is re-paid in full.</p>
    <ol class="manual-list">
      <li><strong>What decides a hit</strong> — the affinity key is derived by <code>minicc/cache_keeper.py::_derive_cache_key(base_url, model)</code>: <code>minicc-</code> + the first 16 hex of sha256(gateway|model); an explicit <code>MINICC_PROMPT_CACHE_KEY</code> wins. A hit needs a byte-identical prefix (system prompt + tools), an in-TTL window, and the same explicit or derived key. TTL expiry, compaction, a model switch, or a tools change — any one triggers a full prefix re-pay.</li>
      <li><strong>Measured reality</strong> — frozen historical baseline: wkapi.pro / gpt-6-sol (2026-11-15): warm <strong>98.3%</strong>; the cold-mutation re-hit 5504/5735 = 96.0%. New lane (api.aizzz.xyz / gpt-6.1-terra, via the local Clash Verge Rev mixed port 127.0.0.1:7897, 2026-11-16): cold 4224/5731 = 73.7%; near-identical suffix 5504/5737 = <strong>95.9%</strong>. Six direct probes all returned HTTP 403 — a geographic refusal; the proxy is the only corridor.</li>
      <li><strong>The warm keeper</strong> — <code>minicc/cache_keeper.py</code> fires a tiny warm <code>responses.create</code> every 220 s (tune with <code>MINICC_CACHE_KEEPER_INTERVAL</code>, floor 60, cap 900), costing ~20 output tokens per beat, no tool calls; failures are counted, never raised; every warm reports on /api/provider-ping; MINICC_CACHE_KEEPER=0 disables it. The gateway's prefix TTL is roughly five minutes — exceed that gap and the next turn re-pays the whole prefix.</li>
      <li><strong>Why it always showed "non-stream"</strong> — early lanes showed a steadier cache read-out on stream responses; the measurement script (<code>scripts/measure_cache_affinity.py</code>) therefore pins stream=true and temperature=0 over a byte-same prefix, and prints the hit counters explicitly. No fabricated "stream is faster" story — stream is a different wire shape of the same prefix discipline.</li>
      <li><strong>Honest usage accounting</strong> — chat/completions does not return cached_tokens; the usage bar carries exactly what the gateway gave (<code>measured_usage</code>: prompt / completion / total), with <code>prompt_cache_hit_tokens</code> only when the gateway surfaced it — <strong>never fabricated</strong>; the keeper's warm pings never bill the agent's token ledger.</li>
      <li><strong>What pays best</strong> — prefix byte-stability. Keep the system prompt and tools list calm, don't sprinkle hints with varying spaces, don't let the session key drift; the cost of one measurement is a single 5731-token request.</li>
    </ol>
    <div class="manual-callout">
      <strong>Honest limits</strong>
      <p>Cache affinity is not a silver bullet: it cannot rescue a model switch, compaction, or the five-minute TTL. This page documents measurement and mechanism — run the script once and the numbers reproduce in front of you. Written so the next person loses one less lamp.</p>
    </div>
  `;
}

function enStateGraph() {
  return `
    <p class="manual-lede">A <strong>bounded state graph</strong> sits under every run — this is never decoration around an if-cascade, and never a shortcut around <code>run_agent</code>.</p>
    <p class="manual-lede">Three things in this chapter: the <strong>phase axis</strong> (the recorder), the <strong>readonly DAG executor</strong> (<code>execute_dag</code>) and the <strong>budget guardrail</strong> (<code>BudgetExceeded</code>).</p>
    <div class="manual-grid-list">
      <div><strong>Phase axis, not executor</strong><span>Actual tasks ride <code>run_agent</code>, the tool-calling loop. The graph answers "where am I now": <code>intake → plan → inspect → implement → verify → repair → summarize</code> — every node registered before the task begins.</span></div>
      <div><strong>Seven phases</strong><span>intake reads the brief · plan admits the mapped steps · inspect reads before writing · implement touches the code · verify runs the tests · repair (capped at 2) only admits verify failures · summarize reports at the end.</span></div>
      <div><strong>Readonly DAG only</strong><span><code>execute_dag</code> admits only <code>readonly</code> / <code>review</code> / <code>merge</code> node kinds. Hand it <code>write</code> or <code>exec</code>, and it refuses before the first wave — a hard reject at the entry, not a polite warning.</span></div>
      <div><strong>The four ratios that keep it honest</strong><span>Node count ≤ 32 · plan depth ≤ 16 · concurrent waves ≤ 4 · cycle rejected at plan time — a plan with a self-edge never exists at run time. Plus <code>BudgetExceeded</code>: no loop may live past step 64.</span></div>
      <div><strong>Three fixed templates</strong><span><code>inspect_summarize</code> (scan once → summarize), <code>inspect_implement_verify</code> (inspect → write → check → summarize) and <code>parallel_inspect</code> (N concurrent readonly scans fanning into <code>merge</code> → implement → verify → summarize). All three live in <code>minicc/agent/graph.py</code>; each whitelist is shared.</span></div>
    </div>
    <p class="manual-footnote">This is not a watered-down LangGraph — durable execution, checkpointing, human-in-the-loop and the Send API family all ship inside the upstream project; read <code>docs/AGENT_LLM_ROADMAP.md</code> for the observability-layer chapter where the real overlap lives. In this repository — <code>minicc/agent/graph.py</code> — is where the idea earns its keep.</p>
  `;
}

function zhArch() {
  return `
    <p class="manual-lede">这有一份从上到下、按真实数据排列的架构全景——前端、后端、数据库、缓存、消息队列，每一样都点到。这不是架构图，是你刚才看了十几章、跑过十几轮任务之后该知道的一篇。</p>
    <ol class="manual-list">
      <li><strong>第一层：前端（Python, 单机进程）</strong> — FastAPI / <code>minicc-web</code>、Jinja2 + vanilla JS 直出、不打包不用构建链（node 只用来 <code>check:web</code>）。每个会话都是全本地、零运营团队。</li>
      <li><strong>前端渲染层</strong> — Vanilla ES modules → esbuild 打包成 <code>assets/*.min.js</code> 与 <code>styles.*.css</code>，没有 React 依赖、没有 NPM 包，~750 KB / 767 KB。任意网络打开 <code>127.0.0.1:8765</code> 立刻进入工作台——没有 build step、没有 npm install、没有依赖刷新。</li>
      <li><strong>第二层：本机 Agent 引擎（Python）</strong> — <code>minicc/agent/loop.py</code>、<code>minicc/session.py</code>、<code>minicc/tools/*</code>、<code>minicc/verifier</code>、<code>minicc/compaction</code> 上下文压缩、<code>minicc/llm/openai_provider</code> 把流式/阻塞/Responses API 统一。全部是纯 python，没有容器化那一层。</li>
      <li><strong>执行层</strong> — <code>ThreadPoolExecutor</code> + per-session <code>Lock</code> + <code>TaskStore</code>（SQLite WAL 覆盖索引）；每个任务在独立 asyncio loop 里跑模型→工具→验证循环。端口 8765 不对外，只在本机 loopback 服务。</li>
      <li><strong>第三层：可选的 Spring Cloud plane（Java）</strong> — <code>minicc-cloud/</code>：Eureka 注册发现（8761）、Spring Cloud Config Server（8888，native profile 读 <code>minicc-cloud/config-repo/</code>）、Spring Cloud Gateway（8080：<code>lb://</code> 加 Resilience4j 熔断、Redis 令牌桶限流、<code>IpKeyResolver</code> 每 IP 一桶）、Inspector（8081，Python 只读检查桥）、Tasks（8082，SQLite 只读读历史）、Insights（8087，聚合统计 + Eureka fleet 拓扑）——这一套全在本机 <code>docker compose</code> 启动，完全可独立 mvn 测试（137+ 绿）。</li>
      <li><strong>数据层：SQLite WAL</strong> — <code>.minicc/tasks.db</code>、<code>audit.jsonl</code>（严格 append only，永不 truncate）；所有写入产物带 <code>before_sha256 / after_sha256</code> 摘要，可复盘。</li>
      <li><strong>缓存</strong> — 本地 <code>functools.lru_cache</code> + <code>default_cache</code> 统一访问；配置驱动的本地 LRU 有 size + ttl 两维限制（默认 4096 × 300 s）；Redis 缓存（<code>minicc-cloud</code> 桥经 Redis 做缓存失效，RabbitMQ fanout）——本机 Redis 没启也可以跑（degrade 到本地 LRU 而不会炸）。</li>
      <li><strong>消息队列</strong> — RabbitMQ：<code>minicc-cloud-gateway</code> 把 <code>/api/inspect</code> 系列的缓存失效广播到所有 inspector 实例（fanout exchange），服务彼此不需要真的用它，但能真用它（配合 <code>/actuator/health</code> 做完整回环演示）。</li>
      <li><strong>限流</strong> — Spring Cloud Gateway 的 Redis 令牌桶（默认 20 tocken/s 回填 + 40 burst，每 IP 一桶），<code>SPRING_PROFILES_ACTIVE=ratelimit</code> 才激活。独立实景压测（2026-11-16，本机独立 Redis 7-alpine 容器 · 与用户共享实例零交集）：120 并发瞬时打满——**40 次放行（503 诚实 fallback：上游未注册，桶限制只关心谁放行）** · **80 次 429**；Redis 计数键（<code>request_rate_limiter.{route}.{ip}</code>）已核验（<code>token</code> 与 <code>timestamp</code>）；冷后桶两个完整周期（2.0 s @ 20/s）再次精确落回 40；详测 <code>docs/GATEWAY_RATELIMIT_LIVE.md</code>。</li>
      <li><strong>压测实测数据</strong> — <code>docs/LOAD_TESTING.md</code>：c=50 × 20s、<strong>2,490 次请求零错误</strong>、p50 37s → <strong>4.2ms</strong>（single-flight + 预热后）；<code>minicc/web.py</code> 重新做了 Semaphores 隔离 + 细粒度锁的内存缓存。</li>
      <li><strong>检索</strong> — <code>minicc/rag.py</code>（BM25 真读仓库 docs 然后塞入上下文）；<code>minicc-cloud-bridge</code> 把 Python rag 跑在独立 Java 桥，面板里"问仓库"全部真跑。</li>
    </ol>
    <div class="manual-callout">
      <strong>实践建议</strong>
      <p>先读完这一章，再挑一个模块——比如先跑 Redis + RabbitMQ、再读 <code>docs/SERVICE_PLANE_OPERATOR.md</code>，你很快就能在本机把整套东西拉起来。</p>
    </div>
  `;
}

function enArch() {
  return `
    <p class="manual-lede">A real architecture, front to back, grounded in actual measurements — frontend, backend, database, cache, queue, all named explicitly. Not an architecture diagram: the real things you walked through in the twelve chapters before this.</p>
    <ol class="manual-list">
      <li><strong>Layer 1: Frontend — Python, single machine.</strong> <code>minicc-web</code> / FastAPI, Jinja2 + vanilla JS straight out, no bundler/no build-chain (node only runs <code>check:web</code>). Every session is fully local, no ops team required.</li>
      <li><strong>Rendering layer.</strong> Vanilla ES modules → esbuild into <code>assets/*.min.js</code> + <code>styles.*.css</code>. No React, no npm runtime — ~750 KB / ~767 KB total JS + CSS. Opening <code>127.0.0.1:8765</code> instantly lands you in the workbench: no build step, no npm install, no dependency drift mid-session.</li>
      <li><strong>Layer 2: the local agent engine (Python).</strong> <code>minicc/agent/loop.py</code>, <code>minicc/session.py</code>, <code>minicc/tools/*</code>, <code>minicc/verifier</code>, <code>minicc/compaction</code> context compaction, and <code>minicc/llm/openai_provider</code> normalizing streaming / blocking / Responses wire formats. Pure Python, no container.</li>
      <li><strong>Execution layer.</strong> <code>ThreadPoolExecutor</code> + per-session locks + <code>TaskStore</code> (SQLite with WAL in a covering index). Each task runs the model → tools → verifier loop in its own asyncio loop. Port 8765 stays strictly on loopback; nothing crosses the boundary that isn't you-asked-for.</li>
      <li><strong>Layer 3: the optional Spring Cloud plane (Java under <code>minicc-cloud/</code>).</strong> Eureka (8761), Spring Cloud Config Server (8888, native profile over <code>minicc-cloud/config-repo/</code>), Spring Cloud Gateway (8080 with <code>lb://</code>, Resilience4j circuit breaker, an <code>IpKeyResolver</code>-based Redis token bucket per IP), Inspector (8081, Python read-only bridge), Tasks (8082, read-only SQLite history), Insights (8087, aggregates + Eureka fleet topology). Runs entirely on <code>docker compose</code> locally with <code>mvn test</code> 137+ green.</li>
      <li><strong>Data layer: SQLite WAL.</strong> <code>.minicc/tasks.db</code>, <code>audit.jsonl</code> (strict append-only, never truncated). Every write records <code>before_sha256 / after_sha256</code> — replay + audit included.</li>
      <li><strong>Cache.</strong> Local <code>default_cache</code> with LRU+TTL (default capacity 4096 × 300 s). Live Redis (when <code>minicc-cloud</code> is up); degrade to local LRU without Redis running — nothing breaks. Prefix cache affinity persisted across the gateway, hot prefix warming to 98.3% hit rate.</li>
      <li><strong>Message queue.</strong> RabbitMQ: <code>minicc-cloud-gateway</code> broadcasts <code>fanout</code> to invalidate inspector Python caches when needed. Use <code>/actuator/health</code> for the full round trip.</li>
      <li><strong>Rate limiter.</strong> Spring Cloud Gateway Redis token bucket (default 20 tokens/s refill + 40 burst, one bucket per IP). Opt-in via <code>SPRING_PROFILES_ACTIVE=ratelimit</code>. Independent live test (2026-11-16, isolated Redis 7-alpine container, zero contact with co-tenant instances): 120-concurrent burst → 40 allowed (503 honest fallback — upstream unregistered; the bucket only governs who gets in) / 80×429. Redis counters (request_rate_limiter.{route}.{ip}{.tokens,.timestamp}) verified in the container; after a full two-second cold bucket the next burst lands at exactly 40 again. Full ledger: docs/GATEWAY_RATELIMIT_LIVE.md.</li>
      <li><strong>Load test.</strong> <code>docs/LOAD_TESTING.md</code>: c=50 × 20 s → <strong>2,490 requests, zero errors</strong>; <code>p50</code> 37 s → <strong>4.2 ms</strong> after single-flight + warm-up. See <code>minicc/web.py</code> for the Semaphore isolation and the fine-grained lock cache work.</li>
      <li><strong>Retrieval.</strong> <code>minicc/rag.py</code> — BM25 over the repo's own docs injected into the prompt. <code>minicc-cloud-bridge</code> hosts the Python RAG behind a Java bridge, so the “Ask the repo” panel is all real.</li>
          <li><strong>See it in person</strong> — press <code>⌘K</code> / <code>Ctrl+K</code> and pick “StateGraph · The Axis”: the whole phase axis lays flat on screen; every node you click prints the exact <code>GraphNode(...)</code> call it came from.</li>
    </ol>
    <div class="manual-callout">
      <strong>Practical first step</strong>
      <p>Read this chapter once, then run Redis + RabbitMQ via <code>docker compose up -d</code> in <code>minicc-cloud/</code> and hit <code>curl localhost:8080/api/health</code>. You'll have the whole plane alive on your laptop in under six minutes.</p>
    </div>
  `;
}

const BODIES = {
  start: { zh: zhStart, en: enStart },
  workbench: { zh: zhWorkbench, en: enWorkbench },
  modules: { zh: zhModules, en: enModules },
  keys: { zh: zhKeys, en: enKeys },
  arcade: { zh: zhArcade, en: enArcade },
  trouble: { zh: zhTrouble, en: enTrouble },
  limits: { zh: zhLimits, en: enLimits },
  vault: { zh: zhVault, en: enVault },
  philosophy: { zh: zhPhilosophy, en: enPhilosophy },
  askdocs: { zh: zhAskDocs, en: enAskDocs },
  load: { zh: zhLoad, en: enLoad },
  cloud: { zh: zhCloud, en: enCloud },
  arch: { zh: zhArch, en: enArch },
  stategraph: { zh: zhStateGraph, en: enStateGraph },
  cache: { zh: zhCacheAffinity, en: enCacheAffinity },
  sandbox: { zh: zhSandbox, en: enSandbox },
  fanout: { zh: zhFanout, en: enFanout },
  evidence: { zh: zhEvidence, en: enEvidence },
  ciwall: { zh: zhCiWall, en: enCiWall },
};

function chapterMarkup(chapter) {
  const zh = state.locale === "zh";
  const title = zh ? chapter.titleZh : chapter.title;
  return `<button class="manual-chapter" data-chapter="${escapeHtml(chapter.id)}" role="tab">
            <span class="manual-chapter-roman">${escapeHtml(zh ? chapter.roman : chapter.romanEn)}</span>
            <span class="manual-chapter-body"><strong>${escapeHtml(title)}</strong></span>
          </button>`;
}

function chapterTitle(chapter) {
  return state.locale === "zh" ? chapter.titleZh : chapter.title;
}

function renderChapter(id) {
  const slot = $("#manualCanvas");
  const chapter = CHAPTERS.find((c) => c.id === id) ?? CHAPTERS[0];
  if (!slot) return;
  const zh = state.locale === "zh";
  const body = (zh ? BODIES[chapter.id].zh : BODIES[chapter.id].en)();
  slot.innerHTML = `
    <div class="manual-canvas-inner">
      <div class="manual-kicker">${zh ? `第${chapter.roman}章` : `Chapter ${chapter.romanEn}`} · ${escapeHtml(chapterTitle(chapter))}</div>
      <h1 class="manual-title">${escapeHtml(chapterTitle(chapter))}</h1>
      <div class="manual-body">${body}</div>
    </div>`;
  slot.querySelector("[data-manual-demo]")?.addEventListener("click", () => {
    closePanel();
    document.getElementById("demoFlowButton")?.click();
  });
  refreshIcons();
}

export async function openManualPanel(chapterId) {
  const zh = state.locale === "zh";
  const wanted = chapterId && CHAPTERS.some((c) => c.id === chapterId) ? chapterId : "start";
  const current = beginPanelRequest(t("manual.title"));
  try {
    const rail = CHAPTERS.map(chapterMarkup).join("");
    openPanel(t("manual.title"), `
      <div class="manual-shell">
        <nav class="manual-rail" aria-label="${escapeHtml(t("manual.title"))}">${rail}</nav>
        <div class="manual-canvas-shell"><div class="manual-canvas" id="manualCanvas"></div></div>
      </div>
    `, { wide: true, immersive: true });
    renderChapter(wanted);
    markVisited(`manual:${wanted}`);
    document.querySelectorAll(".manual-chapter").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".manual-chapter").forEach((b) => b.classList.toggle("active", b === button));
        const id = button.getAttribute("data-chapter") || "start";
        renderChapter(id);
        markVisited(`manual:${id}`);
      });
    });
    document.querySelectorAll(".manual-chapter").forEach((b) => b.classList.toggle("active", b.getAttribute("data-chapter") === wanted));
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(t("manual.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
