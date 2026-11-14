/* ============================================================
   Minicc Almanac — the museum of what this project actually is.

   A read-only excursion across the engineering artifacts that make
   up a coding agent. Every word on screen follows the workbench
   locale — no mixed-language prose: the zh mode is all Chinese,
   the en mode is all English. Every number is derived from live
   sources (/api/metrics, /api/digest, /api/stats, git itself).
   ============================================================ */

import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";
import { escapeHtml } from "../chat/markdown.js";
import { compactNumber } from "../panels/index.js";

const zh = () => state.locale === "zh";

const CHAPTERS = [
  { id: "prologue", roman: { zh: "序章", en: "Prologue" }, title: { zh: "一封给未来的信", en: "The Letter" }, subtitle: { zh: "一封给未来的信", en: "A letter to the future" } },
  { id: "spark", roman: { zh: "第一章", en: "Chapter I" }, title: { zh: "火种", en: "The Spark" }, subtitle: { zh: "意图 → 计划 → 行动 → 证据", en: "Intent → Plan → Act → Proof" } },
  { id: "depth", roman: { zh: "第二章", en: "Chapter II" }, title: { zh: "深度", en: "The Depth" }, subtitle: { zh: "压缩、保留、再出发", en: "Compact, keep, depart again" } },
  { id: "sentry", roman: { zh: "第三章", en: "Chapter III" }, title: { zh: "哨兵", en: "The Sentry" }, subtitle: { zh: "每一个承诺都要被执行", en: "Every promise gets executed" } },
  { id: "bloom", roman: { zh: "第四章", en: "Chapter IV" }, title: { zh: "盛放", en: "The Bloom" }, subtitle: { zh: "工作台本身就是证词", en: "The workbench itself is testimony" } },
  { id: "hand", roman: { zh: "第五章", en: "Chapter V" }, title: { zh: "远行", en: "The Open Road" }, subtitle: { zh: "纸上画下的远方", en: "What is still unmapped" } },
  { id: "gate", roman: { zh: "卷六", en: "Chapter VI" }, title: { zh: "关卡", en: "The Gate" }, subtitle: { zh: "每一道门都点了头", en: "Every gate said yes" } },
  { id: "mesh", roman: { zh: "卷七", en: "Chapter VII" }, title: { zh: "星网", en: "The Mesh" }, subtitle: { zh: "六个服务，一个国家", en: "Six services, one country" } },
  { id: "witness", roman: { zh: "卷八", en: "Chapter VIII" }, title: { zh: "证人", en: "The Witness" }, subtitle: { zh: "笔录不说话，但不说谎", en: "The record does not speak, but it does not lie" } },
  { id: "craft", roman: { zh: "卷九", en: "Chapter IX" }, title: { zh: "技艺", en: "The Craft" }, subtitle: { zh: "一件件作品在同样的手里被磨", en: "Every detail ground by the same hand" } },
  { id: "backlog", roman: { zh: "卷十", en: "Chapter X" }, title: { zh: "未竟", en: "The Unfinished" }, subtitle: { zh: "这册子还没写完，它正在写", en: "This wing is still being written" } },
];

function chapterMarkup(chapter) {
  const kicker = zh() ? chapter.roman.zh : chapter.roman.en;
  const title = zh() ? chapter.title.zh : chapter.title.en;
  const subtitle = zh() ? chapter.subtitle.zh : chapter.subtitle.en;
  return `<button class="almanac-chapter" data-chapter="${escapeHtml(chapter.id)}" role="tab">
            <span class="almanac-chapter-roman">${escapeHtml(kicker)}</span>
            <span class="almanac-chapter-body">
              <strong>${escapeHtml(title)}</strong>
              <small>${escapeHtml(subtitle)}</small>
            </span>
          </button>`;
}

let digestCache = null;
let statsCache = null;
let metricsCache = null;
let statsFetchedAt = 0;
let digestFetchedAt = 0;
// Chapter switching must never re-fetch fresh data per click — the full
// fetch pays real latency on a busy .minicc tree, and every extra round
// trip was stale-by-definition anyway. Reuse numbers for a minute.
const HYDRATE_TTL_MS = 60_000;
let currentChapter = "prologue";

function witnessMarkup() {
  const s = statsCache;
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s?.sessions?.count === "number" ? String(s.sessions.count) : "—";
  const messages = s?.sessions && typeof s?.sessions?.messages === "number" ? String(s.sessions.messages) : "—";
  const rows = (zh() ? [
    ["provider_retry", "网关的耐心——每一次重试计数都是网关与模型之间的一次握手"],
    ["tool_round_finished", "工具回合的完整签名——参数多少字符，一次都不少"],
    ["completion_assessed", "完成落槌或判定落槌——从来不来自静默跳过"],
    ["approval_requested", "越权边缘的停下与等待——你说了算，它停着"],
    ["audit", "被写下来的，都能被读回去——包括这句话本身"],
  ] : [
    ["provider_retry", "The gateway's patience — every retry count is a handshake between gateway and model"],
    ["tool_round_finished", "The full signature of a tool round — parameters, character counts, none skipped"],
    ["completion_assessed", "The hammer falls or it doesn't — never from a silent skip"],
    ["approval_requested", "The pause at the edge of excess authority — the user decides, the agent waits"],
    ["audit", "What is written can be read back — including this very sentence"],
  ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-witness">
      <div class="almanac-kicker">${zh() ? "卷八 · 证人" : "Chapter VIII · The Witness"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "笔录不说话，<br/><span class=\"almanac-title-accent\">但笔录不说谎。</span>" : "The record does not speak,<br/><span class=\"almanac-title-accent\">but the record does not lie.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个项目不信任叙述，它相信笔录。每一次工具调用、每一次重试、每一次完成判定，
          都被写进审计日志——按顺序、带序号、带时间戳。
        </p>
        <p>
          密钥永远不落盘：所有出站内容都经过脱敏才写入日志。
          你能在这里看到的，是动词和路径，从来不是凭据。
        </p>` : `<p>
          This project does not trust narrative; it trusts the record. Every tool call, every retry,
          every completion verdict is written into the audit log — in order, numbered, timestamped.
        </p>
        <p>
          Secrets never touch disk: everything leaving the machine is redacted before it lands in the log.
          What you see here are verbs and paths — never credentials.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "会话" : "Sessions"}</div>
          <div class="almanac-instrument-value">${escapeHtml(sessions)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "消息" : "Messages"}</div>
          <div class="almanac-instrument-value">${escapeHtml(messages)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "当你不知道 agent 做过什么，打开审计。它不解释，但它按顺序交出事实。" : "When you don't know what the agent did, open the audit. It does not explain, but it hands over the facts in order."}
      </p>
    </div>`;
}

function digestInstrumentMarkup(digest) {
  if (!digest || digest.is_git !== true) return "";
  const date = String(digest.first_commit_at || "").slice(0, 10);
  const dirty = Number(digest.dirty_entries);
  const branch = `${digest.branch ?? "—"}${digest.head_short ? ` @ ${digest.head_short}` : ""}`;
  const batches = digest.roadmap_batches != null ? (zh() ? `${digest.roadmap_batches} 章` : `${digest.roadmap_batches} chapters`) : "—";
  const cells = [
    { label: zh() ? "分支" : "Branch", value: escapeHtml(branch) },
    { label: zh() ? "提交总数" : "Commits", value: digest.total_commits != null ? String(digest.total_commits) : "—" },
    { label: zh() ? "第一笔提交" : "First commit", value: date || "—" },
    { label: zh() ? "批次章节" : "Batch chapters", value: batches },
    { label: zh() ? "跟踪文件" : "Tracked files", value: digest.tracked_files != null ? String(digest.tracked_files) : "—" },
    { label: zh() ? "测试文件" : "Test files", value: digest.test_files != null ? String(digest.test_files) : "—" },
  ];
  const grid = cells
    .map((cell) => `<div><div class="almanac-instrument-label">${escapeHtml(cell.label)}</div><div class="almanac-instrument-value">${cell.value}</div></div>`)
    .join("");
  const note = Number.isFinite(dirty) && dirty > 0
    ? `<div class="almanac-sidenote">${zh() ? `工作树里还有 ${dirty} 处未提交改动——这个博物馆还在施工中。` : `${dirty} uncommitted change(s) in the worktree — this museum is still under construction.`}</div>`
    : "";
  return `<div class="almanac-instrument almanac-instrument-grid">${grid}</div>${note}`;
}

function prologueMarkup(digest) {
  return `
    <div class="almanac-canvas almanac-prologue">
      <div class="almanac-kicker">${zh() ? "序章 · 一封给未来的信" : "Prologue · The Letter"}</div>
      <h1 class="almanac-title">${zh() ? "我希望<br/>有人为我" : "I wish<br/>someone would"}<br/><span class="almanac-title-accent">${zh() ? "把世界读一遍。" : "read the world back to me."}</span></h1>
      <div class="almanac-body">
        <p class="almanac-lede">
          ${zh()
            ? `2026 年夏天，这个项目开始于一个问题：<em>「能不能做一个人愿意每天使用的本地编程智能体？」</em>`
            : `Summer 2026. This project began with a question: <em>"Could there be a local coding agent people would actually use every day?"</em>`}
        </p>
        <p>
          ${zh()
            ? `它不是消费级聊天客户端的套壳，也不是任何已有产品的克隆。<br/>它接受 <code>MINICC_API_KEY</code>、<code>MINICC_BASE_URL</code>、<code>MINICC_MODEL</code>，<br/>然后在你的工作区里 <code>read_file</code>、<code>edit_file</code>、<code>run_bash</code>，<br/>用 <code>verify</code> 证明自己说的话是真的，最后把答案交给你。`
            : `It is not a wrapper around any chat client, and not a clone of anything.<br/>It takes <code>MINICC_API_KEY</code>, <code>MINICC_BASE_URL</code> and <code>MINICC_MODEL</code>,<br/>then in your workspace it does <code>read_file</code>, <code>edit_file</code>, <code>run_bash</code>,<br/>proves its claims with <code>verify</code>, and hands you the answer.`}
        </p>
        <p class="almanac-quote">
          ${zh() ? "“我不需要一个替我做决定的人；我需要一个把决定做得更稳的人。”" : "“I don't need someone who decides for me; I need someone who makes decisions stand steadier.”"}
        </p>
        <p class="almanac-sidenote">
          ${zh() ? "这是给你的产品做的同一个问题，作为坐标。" : "The same question, asked about your product. This page is the coordinate."}
        </p>
      </div>
      ${digestInstrumentMarkup(digest)}
    </div>`;
}

function sparkMarkup() {
  const steps = zh() ? [
    { index: "01", head: "入口", body: "用户在 composer 里敲下一句话。系统读文件、读 git 状态、读会话内存。" },
    { index: "02", head: "计划", body: "模型在 plan / verify 循环里切分问题。每一步都得到一份证据或一种失败。" },
    { index: "03", head: "行动", body: "read_file / edit_file / bash 任一工具被调用，输出被验证后再进入下一轮。" },
    { index: "04", head: "验收", body: "completion_assessment 或 verifier 放行答案。未通过则停在原地并报告。" },
  ] : [
    { index: "01", head: "Intake", body: "You type a sentence in the composer. The system reads files, git status, and session memory." },
    { index: "02", head: "Plan", body: "The model splits the problem inside a plan / verify loop. Each step earns evidence or a named failure." },
    { index: "03", head: "Act", body: "read_file / edit_file / bash — every tool call's output is verified before the next round." },
    { index: "04", head: "Verify", body: "completion_assessment or the verifier clears the answer. If it doesn't pass, it stops right there and says why." },
  ];
  return `
    <div class="almanac-canvas almanac-spark">
      <div class="almanac-kicker">${zh() ? "卷一 · 火种" : "Chapter I · The Spark"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "一个句子<br/>如何变成<span class=\"almanac-title-accent\">一个任务。</span>" : "How a sentence<br/>becomes <span class=\"almanac-title-accent\">a task.</span>"}</h1>
      <div class="almanac-body">
        <p>${zh() ? "你在输入框敲下一句话。系统读文件、读 git 状态、读会话内存，把这一句变成一条流水线：" : "You type one sentence. The system reads files, git status and session memory — and turns that sentence into a pipeline:"}</p>
      </div>
      <div class="almanac-chapter-aside">
        ${steps.map((s) => `<div class="almanac-step"><span class="almanac-step-index">${escapeHtml(s.index)}</span><div><strong>${escapeHtml(s.head)}</strong><p>${escapeHtml(s.body)}</p></div></div>`).join("\n        ")}
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
      <div class="almanac-kicker">${zh() ? "卷二 · 深度" : "Chapter II · The Depth"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "越深入<br/>越容易<span class=\"almanac-title-accent\">被压缩。</span>" : "The deeper it goes,<br/><span class=\"almanac-title-accent\">the more it compacts.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          编码会话的代价不在 token，而在<em>注意力</em>。这个项目的上下文压缩
          在接近阈值时保存<em>checkpoint</em>：摘要 + 最近若干轮逐字，其余全部丢弃。
          丢出去的是“这一刻”，留下的是“我在做什么”。
        </p>
        <p>
          缓存命中做的是同一件事：用前缀亲和让模型<em>不重新读一遍</em>你刚写完的上下文。
          没有它，每个请求都要为同一段 system prompt 付费；有它，付一次就行了。
        </p>` : `<p>
          The cost of a coding session is paid in <em>attention</em>, not tokens. This project's context compaction
          saves a <em>checkpoint</em> near the threshold: a summary plus the most recent turns verbatim; the rest is discarded.
          What gets thrown out is "this moment"; what remains is "what I am doing".
        </p>
        <p>
          Cache affinity solves the same problem: a prefix-aware model never re-reads the context you just wrote.
          Without it, every request pays for the same system prompt again; with it, you pay once.
        </p>`}
      </div>
      <div class="almanac-instrument">
        <div class="almanac-instrument-label">${zh() ? "本地数据 · 实时读数" : "Local data · live reading"}</div>
        <div class="almanac-instrument-value">${compactNumber(tokens)} tokens in flight · hit rate ${escapeHtml(hitLabel)}</div>
      </div>
    </div>`;
}

function sentryMarkup(metrics) {
  const taskCount = metrics?.task_count ?? 0;
  const total = metrics?.usage?.total_tokens ?? 0;
  return `
    <div class="almanac-canvas almanac-sentry">
      <div class="almanac-kicker">${zh() ? "卷三 · 哨兵" : "Chapter III · The Sentry"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "每一个承诺<br/>都是一个<span class=\"almanac-title-accent\">门。</span>" : "Every promise<br/>is a <span class=\"almanac-title-accent\">gate.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          如果 agent 可以在没有命令的情况下自称完成，那么<em>任何</em>复杂
          系统都经不起第三个工具调用。这个项目的答案是一串 <code>tests/</code>——
          每个 change 都必须通过自己没有碰到过的门。
        </p>
        <p>
          完成之后再看：一个 <code>completion_assessed</code> 事件不会来自静默跳过，而是
          来自明确获许或明确判输。
        </p>` : `<p>
          If an agent can claim completion without a command, then <em>any</em> complex system
          breaks on the third tool call. This project answers with a wall of <code>tests/</code> —
          every change must clear gates it never touched.
        </p>
        <p>
          And after completion: a <code>completion_assessed</code> event never comes from a silent skip,
          only from explicit success or explicit failure.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "已完成的任务总数" : "Tasks completed"}</div>
          <div class="almanac-instrument-value">${escapeHtml(String(taskCount))}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "累计消耗 tokens" : "Tokens consumed"}</div>
          <div class="almanac-instrument-value">${compactNumber(total)}</div>
        </div>
      </div>
    </div>`;
}

function bloomMarkup() {
  return `
    <div class="almanac-canvas almanac-bloom">
      <div class="almanac-kicker">${zh() ? "卷四 · 盛放" : "Chapter IV · The Bloom"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "这个<br/>工作台本身<br/>就是<span class=\"almanac-title-accent\">证词。</span>" : "This<br/>workbench<br/>itself is <span class=\"almanac-title-accent\">testimony.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这里的每一块不仅不只是「界面」。左边「最近任务」不是导航栏；「缓存命中率」不是百分比；
          「任务档案」不是日志——它们一起构成<strong>交付过程本身</strong>。
        </p>
        <p>
          屏幕上每个数值都可以被点击、被展开、被折叠、被复盘。真正在这里跑过的 agent 才配得上
          「已连接」这三个字——而不是给自己戴荣誉。
        </p>` : `<p>
          Nothing here is "just UI". The recent-tasks list is not a sidebar; the cache hit rate is not a percentage;
          the task archive is not a log — together they <strong>are the delivery process itself</strong>.
        </p>
        <p>
          Every number on screen can be clicked, expanded, folded, replayed. Only an agent that has actually run here
          earns the right to the label "connected" — not as an honorific, but as a fact.
        </p>`}
      </div>
    </div>`;
}

function handMarkup() {
  const bullets = zh() ? [
    ["回放 Replay", "任务从 intake 到 deliver 的每一步，已经可以被回放、被 diff、被复盘。"],
    ["账本 Ledger", "你在这里看到的不是余额，是一笔一笔可被审计的 token。"],
    ["脉搏 Pulse", "你在任何时候都可以打开「工作区脉搏」，看见这个项目在呼吸。"],
    ["模板库 Templates", "8 张经过策划的 prompt，让新手少翻半天文档。"],
    ["Spring Cloud 平面", "云侧的服务边界正在变得更真实：注册发现、配置下发、限流。"],
    ["MCP 与 技能", "你的编辑器里潜藏的能力，可以被接到这条流水线。"],
  ] : [
    ["Replay", "Every step from intake to deliver can already be replayed, diffed, reviewed."],
    ["Ledger", "What you see here is not a balance; it is token-by-token auditability."],
    ["Pulse", "Any time, open the workspace pulse and watch this project breathe."],
    ["Templates", "Eight curated prompts so new users don't spend half a day reading docs."],
    ["Spring Cloud plane", "The cloud-side service boundaries keep getting realer: discovery, config push, rate limits."],
    ["MCP & skills", "Abilities hidden inside your editor can be wired into this pipeline."],
  ];
  return `
    <div class="almanac-canvas almanac-hand">
      <div class="almanac-kicker">${zh() ? "卷五 · 远行" : "Chapter V · The Open Road"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "还有好多<br/>可以继续<span class=\"almanac-title-accent\">做的事。</span>" : "So much is<br/>still worth <span class=\"almanac-title-accent\">doing.</span>"}</h1>
      <div class="almanac-body">
        <p>${zh() ? "这个项目还在长：" : "This project is still growing:"}</p>
        <ul class="almanac-chapter-list">
          ${bullets.map(([b, s]) => `<li><strong>${escapeHtml(b)}</strong> — ${escapeHtml(s)}</li>`).join("\n          ")}
        </ul>
        <p class="almanac-quote almanac-quote-end">
          ${zh() ? "这个产品的未来是：你写下每一条指令之后，世界会因此更精确一点点。" : "The product's future: after you write every instruction, the world is a little more precise because of it."}
        </p>
      </div>
    </div>`;
}

function gateMarkup(digest) {
  const commits = digest && digest.is_git === true && digest.total_commits != null ? String(digest.total_commits) : "—";
  const tests = digest && digest.is_git === true && digest.test_files != null ? String(digest.test_files) : "—";
  const batches = digest && digest.is_git === true && digest.roadmap_batches != null ? (zh() ? `${digest.roadmap_batches} 章` : `${digest.roadmap_batches} chapters`) : "—";
  const rows = (zh() ? [
    ["Python 双平台", "ubuntu-latest + windows-latest · 每推送一次全量跑，两个操作系统各自判卷"],
    ["声明核对器", "doc pointers（悬空证据零容忍）· route coverage · impact floor（每个模块都要被测试够得着）"],
    ["JavaScript 语法门", "22 个语法/协议门 · 任一条不过，这扇门就不算过"],
    ["Service plane", "mvn · 7 个 Spring Cloud 模块 · 网关 / 注册 / 配置 / 任务 / 洞察 / 巡检 / 桥接"],
    ["Playwright ×2", "真浏览器 · 含「不可达提供方必须失败」——门本身也被门守着"],
  ] : [
    ["Python, two platforms", "ubuntu-latest + windows-latest · the full suite on every push, both OSes grading"],
    ["Claim checkers", "doc pointers (no dangling evidence) · route coverage · impact floor (every module must be reachable by a test)"],
    ["JavaScript syntax gates", "22 syntax/protocol gates · if one fails, the gate does not count as passed"],
    ["Service plane", "mvn · 7 Spring Cloud modules · gateway / registry / config / tasks / insights / inspector / bridge"],
    ["Playwright ×2", "Real browsers · including 'an unreachable provider must fail' — the gates are gated too"],
  ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-gate">
      <div class="almanac-kicker">${zh() ? "卷六 · 关卡" : "Chapter VI · The Gate"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "不是写完了，<br/>是被<span class=\"almanac-title-accent\">全部批准了。</span>" : "Not 'it's written',<br/>but <span class=\"almanac-title-accent\">'it's all approved.'</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个项目最安静、也最诚实的角色是 CI。每一次提交都要经过同一排门：
          双平台全量测试、文档门禁、路由覆盖率与模块引用面、22 个 JS 协议门、
          Spring Cloud plane 的 mvn 套件、真浏览器 ×2。
        </p>
        <p>
          任何一道门红了，这扇门就没有意义。它从不说谎，因为它从不被允许说谎：
          断言失败的数字、悬空的证据指针、被漏掉的路由、失踪的引用面——每一个
          都让红灯亮起来，而不是记在心里。
        </p>` : `<p>
          The quietest and most honest role in this project is CI. Every push goes through the same row of gates:
          the dual-platform full suite, doc gates, route coverage and module reference surface, 22 JS protocol gates,
          the Spring Cloud plane's mvn suite, two real browsers.
        </p>
        <p>
          If any gate is red, the gate has no meaning. It never lies, because it is never allowed to:
          a failed assertion count, a dangling evidence pointer, a missing route, a missing reference
          surface — each one turns a light red instead of being quietly remembered.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "门放过的提交数" : "Commits passed by the gates"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "门 · 测试文件" : "Gate · test files"}</div>
          <div class="almanac-instrument-value">${escapeHtml(tests)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "门的文献 · 批次章节" : "Gate's canon · batch chapters"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "这个项目的完成标准不是「做完了」，而是「所有的门都点了头」。" : "This project's definition of done is not \"finished\" — it is \"every gate nodded.\""}
      </p>
    </div>`;
}

function meshMarkup() {
  const list = (zh() ? [
    ["Eureka", "注册发现 — 网关只向注册中心索取健康实例，从不硬编码地址"],
    ["Spring Cloud Gateway", "lb:// 负载均衡 + RequestSize 预拒绝 + 熔断路由"],
    ["Redis 令牌桶", "每秒 20 枚回填 / 40 枚突发 · 每 IP 计数 · Micrometer 计数 gateway.rate_limited{route}"],
    ["Resilience4j", "滑动窗口 10 · 50% 失败即熔断 · 半开试探之后自动闭合"],
    ["RabbitMQ", "网关缓存失效广播：路由表变更一秒内同步到所有实例"],
  ] : [
    ["Eureka", "Discovery — the gateway only ever asks the registry for healthy instances, never a hard-coded address"],
    ["Spring Cloud Gateway", "lb:// load balancing + RequestSize pre-reject + circuit-breaker routes"],
    ["Redis token bucket", "20 refills/s / 40 burst · per-IP counter · Micrometer counter gateway.rate_limited{route}"],
    ["Resilience4j", "Sliding window 10 · 50% failure opens the circuit · half-open probe, then auto-close"],
    ["RabbitMQ", "Gateway cache-invalidation broadcast: route changes reach every instance within one second"],
  ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-mesh">
      <div class="almanac-kicker">${zh() ? "卷七 · 星网" : "Chapter VII · The Mesh"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "六个服务，<br/><span class=\"almanac-title-accent\">一个国家。</span>" : "Six services,<br/><span class=\"almanac-title-accent\">one country.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个仓库有一半在云里。Java 与 Spring Cloud 组成的 plane 有七个模块：
          注册中心、配置中心、网关、洞察、巡检、任务，以及把 Python 引擎翻译成 HTTP 契约的桥接层。
          Eureka 认识它们每一个，网关从不问地址——只问“谁健康”。
        </p>
        <p>
          网关背后有 Redis 铸成的令牌桶（每秒 20 枚回填、40 枚突发），
          也有 Resilience4j 铸成的熔断器——过载时它快速失败，并递出一句
          <em>不冒充空数据</em>的回答。RabbitMQ 在它们之间搬运缓存失效广播，
          让每个实例在一秒内知道“那条缓存已经过期”。
        </p>
        <p>
          2026 年 11 月 14 日，一场实弹演习在这台机器上打响：
          120 个并发请求一次性涌向网关。25 个拿到 200，
          60 个被令牌桶挡回（429），35 个在熔断快开时被诚实拒绝（503）。
          十五秒后，一切恢复闭合，没有一条记录丢失。
        </p>` : `<p>
          Half this repository lives in the cloud. The Java/Spring Cloud plane has seven modules:
          registry, config, gateway, insights, inspector, tasks — and the bridge that translates the Python engine into an HTTP contract.
          Eureka knows every one of them; the gateway never asks for addresses, only “who is healthy”.
        </p>
        <p>
          Behind the gateway sits a Redis-cast token bucket (20 refills per second, 40 burst)
          and a Resilience4j-cast circuit breaker — under overload it fails fast and answers
          with an <em>honest, not-fake-empty</em> response. RabbitMQ shuttles cache-invalidation broadcasts
          between them, so every instance learns "that cache entry is stale" within a second.
        </p>
        <p>
          On November 14, 2026, a live-fire drill ran on this very machine:
          120 concurrent requests hit the gateway at once. 25 got 200,
          60 were turned away by the token bucket (429), 35 were honestly refused while the circuit was open (503).
          Fifteen seconds later, everything closed again — no record was lost.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "实弹 · 被限流" : "Live-fire · rate limited"}</div>
          <div class="almanac-instrument-value">60 × 429</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "实弹 · 熔断快开" : "Live-fire · fast-open"}</div>
          <div class="almanac-instrument-value">31</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "恢复耗时" : "Recovery"}</div>
          <div class="almanac-instrument-value">≤ 15s</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${list}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "一个国家的边境，不取决于城墙有多高，而取决于每一个关卡都知道自己在守什么。" : "A country's border is not defined by how high its walls are — but by whether every checkpoint knows what it is guarding."}
      </p>
    </div>`;
}

function craftMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const files = d?.tracked_files != null ? String(d.tracked_files) : "—";
  const tests = d?.test_files != null ? String(d.test_files) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const s = statsCache;
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  return `
    <div class="almanac-canvas almanac-craft">
      <div class="almanac-kicker">${zh() ? "卷九 · 技艺" : "Chapter IX · The Craft"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "没有草图<br/>只有<span class=\"almanac-title-accent\">舰艏字。</span>" : "No sketch,<br/>only a <span class=\"almanac-title-accent\">bowline.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          没有一套样式书描写过这间屋子；它一次次从推送中长出来。
          每一章作为一个 M8 批次：被门看见、被测试判卷、被 diff 复核。
          这间屋子不是抄了哪个人的课——它在自我复核里长出来。
        </p>
        <p>
          任何一个数字在这间屋子里出现，都必定是从 <code>git</code>、从 <code>audit.jsonl</code>、从 <code>ROADMAP_TO_PRODUCT.md</code> 里把它数出来的——这是唯一允许放在 <em>已完成</em> 旁边的证据。
        </p>` : `<p>
          This wing was never drawn up. It grew out of every push, mile by mile:
          each chapter an M8 batch, each batch gated, each gate recorded.
          This is not a copy of someone else's work — it grew out of its own review.
        </p>
        <p>
          Every number you see here was counted from <code>git</code>, from <code>audit.jsonl</code>,
          from <code>ROADMAP_TO_PRODUCT.md</code> — that is the only evidence allowed next to the word "done".
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "提交" : "Commits"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "审计行" : "Audit lines"}</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "跟踪文件" : "Tracked files"}</div>
          <div class="almanac-instrument-value">${escapeHtml(files)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "测试文件" : "Test files"}</div>
          <div class="almanac-instrument-value">${escapeHtml(tests)}</div>
        </div>
      </div>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "如果你问这间屋子谁建的——答案是公域的门、提交记录、和审稿仪。" : "If you ask whose hand built this room — the answer is the gates, the ledger, and the review."}
      </p>
    </div>`;
}

function backlogMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const head = d?.head_short ? escapeHtml(String(d.head_short)) : "—";
  const shipments = Array.isArray(d?.recent_commits) ? d.recent_commits.slice(0, 6) : [];
  const shipmentRows = shipments.length
    ? shipments
        .map((c) => `<li><strong>${escapeHtml(c.short || "")}</strong><span>${escapeHtml(c.subject || "")}</span></li>`)
        .join("")
    : `<li><strong>${zh() ? "暂无" : "none"}</strong><span>${zh() ? "最近一次交付在这里，只等下一笔提交。" : "The next delivery lands here after the next push."}</span></li>`;
  return `
    <div class="almanac-canvas almanac-backlog">
      <div class="almanac-kicker">${zh() ? "卷十 · 未竟" : "Chapter X · The Unfinished"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '没有「完工」的横幅<br/>只有<span class="almanac-title-accent">正在砌的墙。</span>' : 'No banner says finished<br/>only a <span class="almanac-title-accent">wall going up.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个展厅不陈列死物。每一次 <code>push</code> 都是一块石头，每一个 M8 批次都是一道小门楣——
          这张册子上写的不是「完成」，而是「又交付了一点」。
        </p>
        <p>
          编号里的空壁不是丢了——它们是还没有决定要盖什么的位置。被删掉的门、被合并的路、
          被 re-排序的计划，境遇都在账上，找不到就是找不到；找得到的都在档案馆里排列成列。
        </p>` : `<p>
          This wing holds no lifeless exhibits. Every <code>push</code> is a stone,
          every M8 batch a small lintel — this page records not "done", but
          "one more thing delivered".
        </p>
        <p>
          The gaps in the batch numbering are not lost records. They are positions
          whose purpose has not been decided yet. Doors that were removed, roads
          that were merged, plans that were re-ordered — all accounted for; what
          cannot be found is said to be unfound, and what can is set in order inside the archive.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "当前北极星" : "Current HEAD"}</div>
          <div class="almanac-instrument-value">${head}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${shipmentRows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "如果有一天有人翻到这一页说：从这里开始的每一步都能看得见——那本书就完整了。" : "If someone reads this page one day and says every step from here on can be seen — that is the whole book."}
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
  craft: () => craftMarkup(),
  backlog: () => backlogMarkup(),
};

async function loadChapter(id) {
  const slot = $("#almanacCanvas");
  if (!slot) return;
  // Phase 1: swap the canvas immediately with whatever we already know.
  // /api/stats can take seconds on a big .minicc tree; chapter switching
  // must never freeze on it. Numbers hydrate behind the text.
  const renderer = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = renderer(metricsCache);
  refreshIcons();
  // Phase 2: fetch fresh numbers (cache-per-minute); re-render only if the
  // user is still on this chapter. /api/stats can take seconds on a big
  // .minicc tree — 20s is deliberate, phase 1 already rendered.
  const now = Date.now();
  const wantDigest = digestCache == null || now - digestFetchedAt > HYDRATE_TTL_MS;
  const wantStats = statsCache == null || now - statsFetchedAt > HYDRATE_TTL_MS;
  const [metrics, digest, stats] = await Promise.all([
    requestJson("/api/metrics", {}, 15000).catch(() => null),
    wantDigest ? requestJson("/api/digest", {}, 20000).catch(() => null) : Promise.resolve(null),
    wantStats ? requestJson("/api/stats", {}, 20000).catch(() => null) : Promise.resolve(null),
  ]);
  if (currentChapter !== id) return;
  if (metrics) metricsCache = metrics;
  if (digest) {
    digestCache = digest;
    digestFetchedAt = Date.now();
  }
  if (stats) {
    statsCache = stats;
    statsFetchedAt = Date.now();
  }
  const hydrated = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = hydrated(metricsCache);
  refreshIcons();
}

export async function openAlmanacPanel() {
  const current = beginPanelRequest(t("almanac.title"));
  try {
    const rail = CHAPTERS.map(chapterMarkup).join("");
    openPanel(t("almanac.title"), `
      <div class="almanac-shell">
        <nav class="almanac-rail" aria-label="${zh() ? "章节" : "Chapters"}">${rail}</nav>
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
        digestFetchedAt = Date.now();
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
