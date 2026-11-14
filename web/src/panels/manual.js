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

const CHAPTERS = [
  { id: "start", roman: "一", romanEn: "1", title: "Quick Start", titleZh: "五分钟上手" },
  { id: "workbench", roman: "二", romanEn: "2", title: "The Workbench", titleZh: "工作台导览" },
  { id: "modules", roman: "三", romanEn: "3", title: "The Modules", titleZh: "七个模块，一个世界" },
  { id: "keys", roman: "四", romanEn: "4", title: "Commands & Shortcuts", titleZh: "命令与快捷键" },
  { id: "arcade", roman: "五", romanEn: "5", title: "Playbook", titleZh: "游戏厅教程" },
  { id: "trouble", roman: "六", romanEn: "6", title: "Troubleshooting", titleZh: "排错" },
  { id: "limits", roman: "七", romanEn: "7", title: "Honest Limits", titleZh: "边界与范围" },
  { id: "philosophy", roman: "八", romanEn: "8", title: "The Quiet Room", titleZh: "安静的房间" },
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
      <li><strong>年鉴 · Almanac</strong> — 侧边栏「年鉴」：九卷博物馆级叙事，把这个产品的设计决策按章讲述，每卷数据全部来自 /api/digest、/api/stats 与 git 自身。</li>
      <li><strong>模板库 · Templates</strong> — 8 张策展过的常见任务提示词（项目扫描 / 测试修复 / 安全检查 / README / 翻译 / 依赖 / 现代化 / 冒烟），一键送进对话。</li>
      <li><strong>回放 · Replay</strong> — 任务详情内「回放整个任务」，按事件顺序播放：播放/暂停、scrub 进度条、1×/2×/4× 变速、tokens 旁路累加。</li>
      <li><strong>航行灯 · Running light</strong> — 侧边栏常驻一枚小灯：缓存命中率 × 任务数 × 分支 @ HEAD，四色温；点击直达账本。</li>
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
      <li><strong>Almanac</strong> — sidebar entry: a museum-grade narrative in nine chapters, every figure sourced from /api/digest, /api/stats and git itself.</li>
      <li><strong>Templates</strong> — 8 curated prompts for common jobs (project scan / test+fix / safety / README / translation / deps / modernize / smoke), one click into chat.</li>
      <li><strong>Replay</strong> — “Replay this task” from the detail view, plays event-by-event: play/pause, scrubber, 1×/2×/4× speed, side-mounted token counter.</li>
      <li><strong>Running light</strong> — an always-on sidebar dot: cache hit rate × tasks × branch @ HEAD, four tones; click to open the ledger.</li>
      <li><strong>Arcade</strong> — sidebar entry “Arcade” opens a Plants-vs-Zombies-style tower defense; pure offline, playable with the network down.</li>
    </ul>
  `;
}

function zhKeys() {
  return `
    <div class="manual-keys">
      <div><kbd>Enter</kbd><span>发送任务</span></div>
      <div><kbd>Shift+Enter</kbd><span>换行</span></div>
      <div><kbd>Ctrl / ⌘ N</kbd><span>新任务</span></div>
      <div><kbd>Ctrl / ⌘ K</kbd><span>命令面板</span></div>
      <div><kbd>Ctrl / ⌘ L</kbd><span>账本总览</span></div>
      <div><kbd>/</kbd><span>搜索任务</span></div>
      <div><kbd>?</kbd><span>快捷键速查</span></div>
      <div><kbd>Esc</kbd><span>关闭面板 / 小游戏</span></div>
      <div><kbd>1-9</kbd><span>选植物（游戏打开时）</span></div>
      <div><kbd>P</kbd><span>暂停 / 继续（游戏）</span></div>
      <div><kbd>E</kbd><span>铲子（游戏）</span></div>
    </div>
    <p class="manual-footnote">命令面板里还有更多：切换主题、打开年鉴、打开回放、导出当前对话、恢复任务快照等——全部可以用鼠标或键盘操作。</p>
  `;
}

function enKeys() {
  return `
    <div class="manual-keys">
      <div><kbd>Enter</kbd><span>Send the task</span></div>
      <div><kbd>Shift+Enter</kbd><span>New line</span></div>
      <div><kbd>Ctrl / ⌘ N</kbd><span>New task</span></div>
      <div><kbd>Ctrl / ⌘ K</kbd><span>Command palette</span></div>
      <div><kbd>Ctrl / ⌘ L</kbd><span>Ledger overview</span></div>
      <div><kbd>/</kbd><span>Search tasks</span></div>
      <div><kbd>?</kbd><span>Shortcut reference</span></div>
      <div><kbd>Esc</kbd><span>Close panel / game</span></div>
      <div><kbd>1-9</kbd><span>Pick seed (game open)</span></div>
      <div><kbd>P</kbd><span>Pause / resume (game)</span></div>
      <div><kbd>E</kbd><span>Shovel (game)</span></div>
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
      <div><span class="arcade-label">Keys you will want</span><p><code>1-9</code> pick a card · <code>P</code> pause / resume · <code>E</code> shovel / cancel · click sun drops to collect them yourself (auto-collect toggle exists in-game) · the game pauses itself when the tab loses focus — fight time only counts active frames.</p></div>
    </div>
    <p class="manual-footnote">Game code lives in <code>web/game.js</code> — pure frontend, no server round-trip whatsoever.</p>
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
      <div><strong>缓存命中率低</strong><span>不是 bug，是前缀亲和：带上 <code>MINICC_PROMPT_CACHE_KEY</code>（或让自动派生生效）就能拿到 90%+ 的热命中率。显示流/非流都有缓存；注意非流线 (chat/completions) 在部分网关不上报 <code>cached_tokens</code>。</span></div>
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
      <div><strong>Cache hit rate looks low</strong><span>Not a bug — prefix affinity. Set <code>MINICC_PROMPT_CACHE_KEY</code> (or let the auto-derived key ride) and you will see 90%+ warm hits. Streaming or not does not matter; note chat/completions on some gateways never reports <code>cached_tokens</code>.</span></div>
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

const BODIES = {
  start: { zh: zhStart, en: enStart },
  workbench: { zh: zhWorkbench, en: enWorkbench },
  modules: { zh: zhModules, en: enModules },
  keys: { zh: zhKeys, en: enKeys },
  arcade: { zh: zhArcade, en: enArcade },
  trouble: { zh: zhTrouble, en: enTrouble },
  limits: { zh: zhLimits, en: enLimits },
  philosophy: { zh: zhPhilosophy, en: enPhilosophy },
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
      <div class="manual-kicker">${zh ? `第${chapter.roman}章` : `Chapter ${chapter.romanEn}`} · ${escapeHtml(chapter.title)}</div>
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
