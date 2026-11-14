/* ============================================================
   Minicc Almanac — the museum of what this project actually is.

   A read-only excursion across the engineering artifacts that make
   up a coding agent: the spark of desire, the depth of compaction,
   the sentry of verification, the bloom of the workbench, the open
   road ahead. Every number on screen is derived from live sources
   (api/metrics) or taken verbatim from this repository's own records.
   ============================================================ */

import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";
import { escapeHtml } from "../chat/markdown.js";
import { compactNumber } from "../panels/index.js";

const CHAPTERS = [
  { id: "prologue", roman: "序章", title: "The Letter", subtitle: "一封给未来的信" },
  { id: "spark", roman: "第一章", title: "The Spark", subtitle: "意图 → 计划 → 行动 → 证据" },
  { id: "depth", roman: "第二章", title: "The Depth", subtitle: "压缩、保留、再出发" },
  { id: "sentry", roman: "第三章", title: "The Sentry", subtitle: "每一个承诺都要被执行" },
  { id: "bloom", roman: "第四章", title: "The Bloom", subtitle: "工作台本身就是证词" },
  { id: "hand", roman: "第五章", title: "The Open Road", subtitle: "纸上画下的远方" },
  { id: "gate", roman: "卷六", title: "The Gate", subtitle: "每一道门都点了头" },
  { id: "mesh", roman: "卷七", title: "The Mesh", subtitle: "六个服务，一个国家" },
  { id: "witness", roman: "卷八", title: "The Witness", subtitle: "笔录不说话，但不说谎" },
];

function chapterMarkup(chapter) {
  return `<button class="almanac-chapter" data-chapter="${escapeHtml(chapter.id)}" role="tab">
            <span class="almanac-chapter-roman">${escapeHtml(chapter.roman)}</span>
            <span class="almanac-chapter-body">
              <strong>${escapeHtml(chapter.title)}</strong>
              <small>${escapeHtml(chapter.subtitle)}</small>
            </span>
          </button>`;
}

let digestCache = null;
let statsCache = null;
let currentChapter = "prologue";

function witnessMarkup() {
  const s = statsCache;
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s?.sessions?.count === "number" ? String(s.sessions.count) : "—";
  const messages = s?.sessions && typeof s?.sessions?.messages === "number" ? String(s.sessions.messages) : "—";
  const rows = [
    ["provider_retry", "网关的耐心——每一次重试计数都是网关与模型之间的一次握手"],
    ["tool_round_finished", "工具回合的完整签名——参数多少字符，一次都不少"],
    ["completion_assessed", "完成落槌或判定落槌——never 来自静默跳过"],
    ["approval_requested", "越权边缘的停下与等待——你说了算，它停着"],
    ["audit", "被写下来的，都能被读回去——包括这句话本身"],
  ].map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-witness">
      <div class="almanac-kicker">卷八 · Chapter VIII — The Witness</div>
      <h1 class="almanac-title almanac-title-sm">笔录不说话，<br/><span class="almanac-title-accent">但笔录不说谎。</span></h1>
      <div class="almanac-body">
        <p>
          这个项目不信任叙述，它相信笔录。每一次工具调用、每一次重试、每一次完成判定，
          都被写进审计日志——按顺序、带序号、带时间戳。
        </p>
        <p>
          密钥永远不落盘：所有出站内容都经过脱敏才写入日志。
          你能在这里看到的，是动词和路径，从来不是凭据。
        </p>
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">审计行数 · Audit lines</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">会话 · Sessions</div>
          <div class="almanac-instrument-value">${escapeHtml(sessions)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">消息 · Messages</div>
          <div class="almanac-instrument-value">${escapeHtml(messages)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        当你不知道 agent 做过什么，打开审计。它不解释，但它按顺序交出事实。
      </p>
    </div>`;
}

function digestInstrumentMarkup(digest) {
  if (!digest || digest.is_git !== true) return "";
  const date = String(digest.first_commit_at || "").slice(0, 10);
  const dirty = Number(digest.dirty_entries);
  const branch = `${digest.branch ?? "—"}${digest.head_short ? ` @ ${digest.head_short}` : ""}`;
  const cells = [
    { label: "分支 · Branch", value: escapeHtml(branch) },
    { label: "提交总数 · Commits", value: digest.total_commits != null ? String(digest.total_commits) : "—" },
    { label: "第一笔提交 · First", value: date || "—" },
    { label: "批次手稿 · Batches", value: digest.roadmap_batches != null ? `${digest.roadmap_batches} 章` : "—" },
    { label: "跟踪文件 · Tracked files", value: digest.tracked_files != null ? String(digest.tracked_files) : "—" },
    { label: "测试文件 · Tests", value: digest.test_files != null ? String(digest.test_files) : "—" },
  ];
  const grid = cells
    .map((cell) => `<div><div class="almanac-instrument-label">${escapeHtml(cell.label)}</div><div class="almanac-instrument-value">${cell.value}</div></div>`)
    .join("");
  const note = Number.isFinite(dirty) && dirty > 0
    ? `<div class="almanac-sidenote">工作树里还有 ${dirty} 处未提交改动——这个博物馆还在施工中。</div>`
    : "";
  return `<div class="almanac-instrument almanac-instrument-grid">${grid}</div>${note}`;
}

function prologueMarkup(digest) {
  return `
    <div class="almanac-canvas almanac-prologue">
      <div class="almanac-kicker">序章 · Prologue — The Letter</div>
      <h1 class="almanac-title">我希望<br/>有人为我
        <span class="almanac-title-accent">把世界读一遍。</span>
      </h1>
      <div class="almanac-body">
        <p class="almanac-lede">
          2026 年夏天，这个项目开始于一个问题：
          <em>「能不能做一个人愿意每天使用的本地编程智能体？」</em>
        </p>
        <p>
          它不是 ChatGPT 的套壳，也不是 Claude Code 的克隆。
          它接受 <code>MINICC_API_KEY</code>、<code>MINICC_BASE_URL</code>、<code>MINICC_MODEL</code>，
          然后在你的工作区里 <code>read_file</code>、<code>edit_file</code>、<code>run_bash</code>，
          用 <code>verify</code> 证明自己说的话是真的，最后把答案交给你。
        </p>
        <p class="almanac-quote">
          “我不需要一个替我做决定的人；我需要一个把决定做得更稳的人。”
        </p>
        <p class="almanac-sidenote">
          这是给你的产品做的同一个问题，作为坐标。
        </p>
      </div>
      ${digestInstrumentMarkup(digest)}
    </div>`;
}

function sparkMarkup() {
  return `
    <div class="almanac-canvas almanac-spark">
      <div class="almanac-kicker">卷一 · Chapter I — The Spark</div>
      <h1 class="almanac-title almanac-title-sm">一个句子<br/>如何变成<span class="almanac-title-accent">一个任务。</span></h1>
      <div class="almanac-body">
        <p>你在输入框敲下一句话。系统读文件、读 git 状态、读会话内存，把这一句变成一条流水线：</p>
      </div>
      <div class="almanac-chapter-aside">
        <div class="almanac-step"><span class="almanac-step-index">01</span><div><strong>入口</strong><p>用户在 composer 里敲下一句话。系统读文件、读 git 状态、读会话内存。</p></div></div>
        <div class="almanac-step"><span class="almanac-step-index">02</span><div><strong>计划</strong><p>模型在 plan / verify 循环里切分问题。每一步都得到一份证据或一种失败。</p></div></div>
        <div class="almanac-step"><span class="almanac-step-index">03</span><div><strong>行动</strong><p>read_file / edit_file / bash 任一工具被调用，输出被验证后再进入下一轮。</p></div></div>
        <div class="almanac-step"><span class="almanac-step-index">04</span><div><strong>验收</strong><p>completion_assessment 或 verifier 放行答案。未通过则停在原地并报告。</p></div></div>
      </div>
    </div>`;
}

function renderInstrumentValue(metrics) {
  const tokens = metrics?.usage?.total_tokens ?? 0;
  const hitRate = metrics?.llm_cache?.cache_hit_rate ?? 0;
  return { tokens, hitRate };
}

function depthMarkup(metrics) {
  const { tokens, hitRate } = renderInstrumentValue(metrics);
  const hitLabel = hitRate > 0 ? `${Math.round(hitRate * 100)}%` : "—";
  return `
    <div class="almanac-canvas almanac-depth">
      <div class="almanac-kicker">卷二 · Chapter II — The Depth</div>
      <h1 class="almanac-title almanac-title-sm">越深入<br/>越容易<span class="almanac-title-accent">被压缩。</span></h1>
      <div class="almanac-body">
        <p>
          编码会话的代价不在 token，而在<em>注意力</em>。这个项目的上下文压缩
          在接近阈值时保存<em>checkpoint</em>：摘要 + 最近若干轮逐字，其余全部丢弃。
          丢出去的是"这一刻"，留下的是"我在做什么"。
        </p>
        <p>
          缓存命中做的是同一件事：用前缀亲和让模型<em>不重新读一遍</em>你刚写完的上下文。
          没有它，每个请求都要为同一段 system prompt 付费；有它，付一次就行了。
        </p>
      </div>
      <div class="almanac-instrument">
        <div class="almanac-instrument-label">本地数据 · 实时读数</div>
        <div class="almanac-instrument-value">${compactNumber(tokens)} tokens in flight · hit rate ${escapeHtml(hitLabel)}</div>
      </div>
    </div>`;
}

function sentryMarkup(metrics) {
  const taskCount = metrics?.task_count ?? 0;
  const total = metrics?.usage?.total_tokens ?? 0;
  return `
    <div class="almanac-canvas almanac-sentry">
      <div class="almanac-kicker">卷三 · Chapter III — The Sentry</div>
      <h1 class="almanac-title almanac-title-sm">每一个承诺<br/>都是一个<span class="almanac-title-accent">门。</span></h1>
      <div class="almanac-body">
        <p>
          如果 agent 可以在没有命令的情况下自称完成，那么<em>任何</em>复杂
          系统都经不起第三个工具调用。这个项目的答案是一串 <code>tests/</code>——
          每个 change 都必须通过自己没有碰到过的门。
        </p>
        <p>
          完成之后再看：一个 <code>completion_assessed</code> 事件不会来自静默跳过，而是
          来自明确获许或明确判输。
        </p>
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">已完成的任务总数</div>
          <div class="almanac-instrument-value">${escapeHtml(String(taskCount))}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">累计消耗 tokens</div>
          <div class="almanac-instrument-value">${compactNumber(total)}</div>
        </div>
      </div>
    </div>`;
}

function bloomMarkup() {
  return `
    <div class="almanac-canvas almanac-bloom">
      <div class="almanac-kicker">卷四 · Chapter IV — The Bloom</div>
      <h1 class="almanac-title almanac-title-sm">这个<br/>工作台本身<br/>就是<span class="almanac-title-accent">证词。</span></h1>
      <div class="almanac-body">
        <p>
          这里的每一块不仅不只是「界面」。左边「最近任务」不是导航栏；「缓存命中率」不是百分比；
          「任务档案」不是日志——它们一起构成<strong>交付过程本身</strong>。
        </p>
        <p>
          屏幕上每个数值都可以被点击、被展开、被折叠、被复盘。真正在这里跑过的 agent 才配得上
          「已连接」这三个字——而不是给自己戴荣誉。
        </p>
      </div>
    </div>`;
}

function handMarkup() {
  return `
    <div class="almanac-canvas almanac-hand">
      <div class="almanac-kicker">卷五 · Chapter V — The Open Road</div>
      <h1 class="almanac-title almanac-title-sm">还有好多<br/>可以继续<span class="almanac-title-accent">做的事。</span></h1>
      <div class="almanac-body">
        <p>这个项目还在长：</p>
        <ul class="almanac-chapter-list">
          <li><strong>Memory</strong> — 任务从 intake 到 deliver 的每一步，已经可以被回放、被 diff、被复盘。</li>
          <li><strong>Ledger</strong> — 你在这里看到的不是余额，是一笔一笔可被审计的 token。</li>
          <li><strong>Pulse</strong> — 你在任何时候都可以打开「工作区脉搏」，看见这个项目在呼吸。</li>
          <li><strong>Templates</strong> — 8 张经过策划的 prompt，让新手少翻半天文档。</li>
          <li><strong>Spring Cloud plane</strong> — 云侧的服务边界正在变得更真实：注册发现、配置下发、限流。</li>
          <li><strong>MCP &amp; skills</strong> — 你的编辑器里潜藏的能力，可以被接到这条流水线。</li>
        </ul>
        <p class="almanac-quote almanac-quote-end">
          这个产品的未来是你写下每一条指令之后，世界会因此更精确一点点。
        </p>
      </div>
    </div>`;
}

function gateMarkup(digest) {
  const commits = digest && digest.is_git === true && digest.total_commits != null ? String(digest.total_commits) : "—";
  const tests = digest && digest.is_git === true && digest.test_files != null ? String(digest.test_files) : "—";
  const batches = digest && digest.is_git === true && digest.roadmap_batches != null ? `${digest.roadmap_batches} 章` : "—";
  const rows = [
    ["Python 双平台", "ubuntu-latest + windows-latest · 每推送一次全量跑，两个操作系统各自判卷"],
    ["Claim checkers", "doc pointers（悬空证据零容忍）· route coverage · impact floor（每个模块都要被测试够得着）"],
    ["JavaScript syntax", "22 个语法/协议门 · 任一条不过，这扇门就不算过"],
    ["Service plane", "mvn · 7 个 Spring Cloud 模块 · 网关 / 注册 / 配置 / 任务 / 洞察 / 巡检 / 桥接"],
    ["Playwright ×2", "真浏览器 · 含「不可达提供方必须失败」——门本身也被门守着"],
  ].map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-gate">
      <div class="almanac-kicker">卷六 · Chapter VI — The Gate</div>
      <h1 class="almanac-title almanac-title-sm">不是写完了，<br/>是被<span class="almanac-title-accent">全部批准了。</span></h1>
      <div class="almanac-body">
        <p>
          这个项目最安静、也最诚实的角色是 CI。每一次提交都要经过同一排门：
          双平台全量测试、文档门禁、路由覆盖率与模块引用面、22 个 JS 协议门、
          Spring Cloud plane 的 mvn 套件、真浏览器 ×2。
        </p>
        <p>
          任何一道门红了，这扇门就没有意义。它从不说谎，因为它从不被允许说谎：
          断言失败的数字、悬空的证据指针、被漏掉的路由、失踪的引用面——每一个
          都让红灯亮起来，而不是记在心里。
        </p>
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">门放过的提交数</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">门 · 测试文件</div>
          <div class="almanac-instrument-value">${escapeHtml(tests)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">门的文献 · 批次手稿</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        这个项目的完成标准不是「做完了」，而是「所有的门都点了头」。
      </p>
    </div>`;
}

function meshMarkup() {
  return `
    <div class="almanac-canvas almanac-mesh">
      <div class="almanac-kicker">卷七 · Chapter VII — The Mesh</div>
      <h1 class="almanac-title almanac-title-sm">六个服务，<br/><span class="almanac-title-accent">一个国家。</span></h1>
      <div class="almanac-body">
        <p>
          这个仓库有一半在云里。Java 与 Spring Cloud 组成的 plane 有七个模块：
          注册中心、配置中心、网关、洞察、巡检、任务，以及把 Python 引擎翻译成 HTTP 契约的桥接层。
          Eureka 认识它们每一个，网关从不问地址——只问"谁健康"。
        </p>
        <p>
          网关背后有 Redis 铸成的令牌桶（每秒 20 枚回填、40 枚突发），
          也有 Resilience4j 铸成的熔断器——过载时它快速失败，并递出一句
          <em>不冒充空数据</em>的回答。RabbitMQ 在它们之间搬运缓存失效广播，
          让每个实例在一秒内知道"那条缓存已经过期"。
        </p>
        <p>
          2026 年 11 月 14 日，一场实弹演习在这台机器上打响：
          120 个并发请求一次性涌向网关。25 个拿到 200，
          60 个被令牌桶挡回（429），35 个在熔断快开时被诚实拒绝（503）。
          十五秒后，一切恢复闭合，没有一条记录丢失。
        </p>
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">实弹 · 被限流</div>
          <div class="almanac-instrument-value">60 × 429</div>
        </div>
        <div>
          <div class="almanac-instrument-label">实弹 · 熔断快开</div>
          <div class="almanac-instrument-value">31 次</div>
        </div>
        <div>
          <div class="almanac-instrument-label">恢复耗时</div>
          <div class="almanac-instrument-value">≤ 15s</div>
        </div>
      </div>
      <ul class="almanac-gate-list">
        <li><strong>Eureka</strong><span>注册发现 — 网关只向注册中心索取健康实例，从不硬编码地址</span></li>
        <li><strong>Spring Cloud Gateway</strong><span>lb:// 负载均衡 + RequestSize 预拒绝 + 熔断路由</span></li>
        <li><strong>Redis token bucket</strong><span>20 rps 回填 / 40 突发 · 每 IP 计数 · Micrometer 计数 \`gateway.rate_limited{route}\`</span></li>
        <li><strong>Resilience4j</strong><span>滑动窗口 10 · 50% 失败即 open · 半开试探之后自动闭合</span></li>
        <li><strong>RabbitMQ</strong><span>网关缓存失效广播：路由表变更一秒内同步到所有实例</span></li>
      </ul>
      <p class="almanac-quote almanac-quote-end">
        一个国家的边境，不取决于城墙有多高，而取决于每一个关卡都知道自己在守什么。
      </p>
    </div>`;
}

const CHAPTER_RENDERERS = {
  prologue: () => prologueMarkup(digestCache),
  spark: () => sparkMarkup(),
  depth: (metrics) => depthMarkup(metrics),
  sentry: (metrics) => sentryMarkup(metrics),
  bloom: () => bloomMarkup(),
  hand: () => handMarkup(),
  gate: () => gateMarkup(digestCache),
  mesh: () => meshMarkup(),
  witness: () => witnessMarkup(),
};

async function loadChapter(id) {
  const slot = $("#almanacCanvas");
  if (!slot) return;
  const [metrics, digest, stats] = await Promise.all([
    requestJson("/api/metrics").catch(() => null),
    requestJson("/api/digest").catch(() => null),
    requestJson("/api/stats").catch(() => null),
  ]);
  digestCache = digest;
  statsCache = stats;
  const renderer = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = renderer(metrics);
  refreshIcons();
}

export async function openAlmanacPanel() {
  const current = beginPanelRequest(t("almanac.title"));
  try {
    const rail = CHAPTERS.map(chapterMarkup).join("");
    openPanel(t("almanac.title"), `
      <div class="almanac-shell">
        <nav class="almanac-rail" aria-label="Chapters">${rail}</nav>
        <div class="almanac-canvas-shell"><div class="almanac-canvas" id="almanacCanvas">${prologueMarkup(digestCache)}</div></div>
      </div>
    `, { wide: true });
    document.querySelectorAll(".almanac-chapter").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".almanac-chapter").forEach((b) => b.classList.toggle("active", b === button));
        currentChapter = button.getAttribute("data-chapter") || "prologue";
        loadChapter(currentChapter);
      });
    });
    document.querySelector('.almanac-chapter[data-chapter="prologue"]')?.classList.add("active");
    refreshIcons();
    requestJson("/api/digest")
      .then((digest) => {
        digestCache = digest;
        if (currentChapter !== "prologue") return;
        const slot = $("#almanacCanvas");
        if (!slot) return;
        slot.innerHTML = prologueMarkup(digestCache);
        refreshIcons();
      })
      .catch(() => {});
  } catch (error) {
    if (!current()) return;
    openPanel(t("almanac.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
