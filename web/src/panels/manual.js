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

const CHAPTERS = [
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
      <p class="manual-sidenote">第一次打开工作台时右下角会长出一枚「上手演练」按钮：6 步带你把工作台走一遍；⌘K 搜「tour」随时重来。</p>
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
      <p class="manual-sidenote">First time here? A “Start tour” pill grows in the bottom-right corner — six steps, two minutes. Search “tour” in ⌘K to replay it anytime.</p>
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
      <li><strong>年鉴 · Almanac</strong> — 侧边栏「年鉴」：十七卷博物馆级叙事，把这个产品的设计决策按章讲述（最新卷：卷十六《高烧》，讲的是这个仓库差点没撑过去的每一个晚上——37s 的 p50 怎么被压到 4.2ms、两个 U+FFFD 怎么让账本对 grep 隐形、push 取消 CI 怎么让两个冒烟红了三周没人看见、诊断中心怎么抓住冷缓存惊群），每卷数据全部来自 /api/digest、/api/stats 与 git 自身。</li>
      <li><strong>模板库 · Templates</strong> — 8 张策展过的常见任务提示词（项目扫描 / 测试修复 / 安全检查 / README / 翻译 / 依赖 / 现代化 / 冒烟），一键送进对话。</li>
      <li><strong>回放 · Replay</strong> — 任务详情内「回放整个任务」，按事件顺序播放：播放/暂停、scrub 进度条、1×/2×/4× 变速、tokens 旁路累加。</li>
      <li><strong>航行灯 · Running light</strong> — 侧边栏常驻一枚小灯：缓存命中率 × 任务数 × 分支 @ HEAD，四色温；点击直达账本。</li>
      <li><strong>火苗 · The flame</strong> — 连续完成任务的天数：一天 ≥1 次真实任务即点亮一次，金焰色呼吸光晕置于侧边栏；两天没完成就从头计算。全部本地保存，不出网。</li>
      <li><strong>小游戏 · Arcade</strong> — 侧边栏「小游戏」进入塔防植物大战僵尸系列；build 在 <code>web/game.js</code>，纯离线，离线也能玩。</li>
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
      <li><strong>Almanac</strong> — sidebar entry: a museum-grade narrative in seventeen chapters (the newest, Chapter XVI “The Fever” — the nights this repository nearly didn't make it: the 37s p50 pressed down to 4.2ms, two U+FFFD codepoints silencing the ledger against grep, push-cancelled CI hiding two red smokes for three weeks, the Doctor panel catching a cold-cache thundering herd), every figure sourced from /api/digest, /api/stats, /api/worldpulse and git itself.</li>
      <li><strong>Templates</strong> — 8 curated prompts for common jobs (project scan / test+fix / safety / README / translation / deps / modernize / smoke), one click into chat.</li>
      <li><strong>Replay</strong> — “Replay this task” from the detail view, plays event-by-event: play/pause, scrubber, 1×/2×/4× speed, side-mounted token counter.</li>
      <li><strong>Running light</strong> — an always-on sidebar dot: cache hit rate × tasks × branch @ HEAD, four tones; click to open the ledger.</li>
      <li><strong>The flame</strong> — days in a row with at least one completed task: one flame per calendar day, breathing gold in the sidebar; two misses restart the count. Local-only, never leaves this machine.</li>
      <li><strong>Arcade</strong> — sidebar entry “Arcade” opens a Plants-vs-Zombies-style tower defense; pure offline, playable with the network down.</li>
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

export async function openManualPanel() {
  const zh = state.locale === "zh";
  const current = beginPanelRequest(t("manual.title"));
  try {
    const rail = CHAPTERS.map(chapterMarkup).join("");
    openPanel(t("manual.title"), `
      <div class="manual-shell">
        <nav class="manual-rail" aria-label="${escapeHtml(t("manual.title"))}">${rail}</nav>
        <div class="manual-canvas-shell"><div class="manual-canvas" id="manualCanvas"></div></div>
      </div>
    `, { wide: true, immersive: true });
    renderChapter("start");
    document.querySelectorAll(".manual-chapter").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".manual-chapter").forEach((b) => b.classList.toggle("active", b === button));
        renderChapter(button.getAttribute("data-chapter") || "start");
      });
    });
    document.querySelector('.manual-chapter[data-chapter="start"]')?.classList.add("active");
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(t("manual.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
