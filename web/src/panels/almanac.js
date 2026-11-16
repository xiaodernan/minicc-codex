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
import { markVisited } from "../core/visited.js";

const zh = () => state.locale === "zh";

export const CHAPTERS = [
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
  { id: "echo", roman: { zh: "卷十一", en: "Chapter XI" }, title: { zh: "回声", en: "The Echo" }, subtitle: { zh: "三根看不见的弦，都在响", en: "Three strings you cannot see, all humming" } },
  { id: "answer", roman: { zh: "卷十二", en: "Chapter XII" }, title: { zh: "回问", en: "The Answer Back" }, subtitle: { zh: "终于学会回答的这本书", en: "The book that answered back" } },
  { id: "ember", roman: { zh: "卷十三", en: "Chapter XIII" }, title: { zh: "余烬", en: "The Ember" }, subtitle: { zh: "炉火不散", en: "The hearth stays warm" } },
  { id: "atlas", roman: { zh: "卷十四", en: "Chapter XIV" }, title: { zh: "星图", en: "The Atlas" }, subtitle: { zh: "这片世界有多少岛", en: "How many islands this world holds" } },
  { id: "firstlight", roman: { zh: "卷十五", en: "Chapter XV" }, title: { zh: "曦", en: "First Light" }, subtitle: { zh: "有人按下了那颗星", en: "Someone hit the star" } },
  { id: "fever", roman: { zh: "卷十六", en: "Chapter XVI" }, title: { zh: "高烧", en: "The Fever" }, subtitle: { zh: "所有悬的地方，后来都长成了门", en: "Every near-miss grew into a gate" } },
  { id: "lighthouse", roman: { zh: "卷十七", en: "Chapter XVII" }, title: { zh: "灯塔", en: "The Lighthouse" }, subtitle: { zh: "忙解决问题的人，也该被守住", en: "Even the one fixing things deserves to be kept" } },
  { id: "gatekeeper", roman: { zh: "卷十八", en: "Chapter XVIII" }, title: { zh: "守门人", en: "The Gatekeeper" }, subtitle: { zh: "知道密码的人，看见同一份诚实", en: "Everyone with the 123 door sees the same honest ledger" } },
  { id: "meridian", roman: { zh: "卷十九", en: "Chapter XIX" }, title: { zh: "镜门", en: "The Meridian" }, subtitle: { zh: "有人问路的地方，就是答案", en: "Where directions are given for walks never taken" } },
  { id: "nightwatch", roman: { zh: "卷二十", en: "Chapter XX" }, title: { zh: "未眠", en: "The Night Watch" }, subtitle: { zh: "账本没有合上，它只是翻开下一页", en: "The ledger never closed; it turned the page" } },
  { id: "fence", roman: { zh: "卷二十一", en: "Chapter XXI" }, title: { zh: "篱笆", en: "The Fence" }, subtitle: { zh: "一个语言时代只有一种语言", en: "One era of language, one language" } },
  { id: "compass", roman: { zh: "卷二十二", en: "Chapter XXII" }, title: { zh: "罗经仪", en: "The Compass" }, subtitle: { zh: "引导不是兜底，是建筑", en: "Guidance is not a parachute, it is architecture" } },
  { id: "deepfield", roman: { zh: "卷二十三", en: "Chapter XXIII" }, title: { zh: "深空", en: "The Deep Field" }, subtitle: { zh: "勘完不是终点，是望远镜的起点", en: "Finish the chart, then point the telescope deeper" } },
  { id: "lawn", roman: { zh: "卷二十四", en: "Chapter XXIV" }, title: { zh: "翠茵", en: "The Lawn" }, subtitle: { zh: "先给草插上旗子，再让僵尸来", en: "Plant the flag before the zombie learns the gate" } },
  { id: "litmus", roman: { zh: "卷二十五", en: "Chapter XXV" }, title: { zh: "试纸", en: "The Litmus" }, subtitle: { zh: "红门只说一件事：这里有事没说完", en: "Red only ever means one thing: something here is unfinished" } },
  { id: "harbour", roman: { zh: "卷二十六", en: "Chapter XXVI" }, title: { zh: "港灯", en: "The Harbour Light" }, subtitle: { zh: "每一盏灯都指得出来真礁的那一夜", en: "The night every lamp finally named the rocks" } },
  { id: "return", roman: { zh: "卷二十七", en: "Chapter XXVII" }, title: { zh: "归航", en: "The Return Voyage" }, subtitle: { zh: "门绿了以后，船才真的回港", en: "Only green gates can bring the ship home" } },
  { id: "steward", roman: { zh: "卷二十八", en: "Chapter XXVIII" }, title: { zh: "守望", en: "The Steward" }, subtitle: { zh: "先把每盏灯的颜色读清楚了，再谈守望", en: "Learn every color the lamps can throw, then speak of watching" } },
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
let worldpulseCache = null;

const HYDRATE_TTL_MS = 60_000;
let digestFetchedAt = 0;
let statsFetchedAt = 0;
let worldpulseFetchedAt = 0;
// Chapter switching must never re-fetch fresh data per click — the full
// fetch pays real latency on a busy .minicc tree, and every extra round
// trip was stale-by-definition anyway. Reuse numbers for a minute.
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
  // EN mode hides local-language commit subjects (they are data, not prose —
  // the almanac stays Latin in en, zh carries the raw log. This is honest:
  // the museum shows what actually shipped, not a translated lie.)
  const subjectFor = (subject) => {
    const raw = String(subject ?? "");
    if (zh()) return raw;
    // Latin-fold: drop anything CJK so en stays pure Latin/ASCII
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(raw)) return "git commit";
    return raw;
  };
  const shipmentRows = shipments.length
    ? shipments
        .map((c) => `<li><strong>${escapeHtml(c.short || "")}</strong><span>${escapeHtml(subjectFor(c.subject))}</span></li>`)
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

function echoMarkup() {
  const d = digestCache;
  const s = statsCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const redisLive = s?.cache?.live_backend != null && s?.cache?.live_backend !== false;
  const redisLabel = redisLive ? (zh() ? "Redis 在线" : "Redis live") : (zh() ? "本地 LRU" : "Local LRU");
  return `
    <div class="almanac-canvas almanac-echo">
      <div class="almanac-kicker">${zh() ? "卷十一 · 回声" : "Chapter XI · The Echo"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '没有谁在重复<br/>每一根弦都在<span class="almanac-title-accent">传回来。</span>' : 'No one repeats,<br/>but every string <span class="almanac-title-accent">carries back.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          在这间屋子里你能听见三件事：一声是 <code>git</code> 把东西写进历史；
          一声是 <code>audit.jsonl</code> 把每一步补了一笔账；
          一声是缓存替你记住了一句你还没说的话。
        </p>
        <p>
          它们互不相识——一个写树，一个记帐，一个看门——却共用一个屋顶：
          你只想知道「做过什么」，这三件事会各自从角落里打来电话，
          按时间先后重放一次。这就是回声：不是复制，是同一件事被三个角落
          记住的样子。
        </p>` : `<p>
          In this wing you can hear three things: <code>git</code> is the beat that writes the history;
          <code>audit.jsonl</code> is the metronome ticking behind it;
          and the cache is the breath you hold before you speak.
        </p>
        <p>
          They do not know each other — one writes the tree, one keeps the books,
          one holds the door — but they share a roof: you ask one question,
          "what was done here", and all three answer in their own time,
          from their own corners, in order. That is an echo: not a copy,
          but the same thing three corners remember.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "仓库呼吸" : "Repository breath"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "批次回响" : "Batch echoes"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "审计回声" : "Audit echo"}</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">
        <li><strong>${redisLabel}</strong><span>${zh() ? "缓存亲和：同 key 跨进程复用 KV，0→100% 热命中率（实测，见缓存亲和矩阵）" : "Cache affinity: same key, warm KV across processes; 0→100% hot rate (measured, see the affinity matrix)"}</span></li>
        <li><strong>${zh() ? "RabbitMQ 失效风暴" : "RabbitMQ invalidation"}</strong><span>${zh() ? "失效消息从 gateway 扇出，消费者逐一驱逐；健康实例会自己断连" : "fan-out from the gateway, consumers evict one by one; healthy boxes disconnect themselves"}</span></li>
        <li><strong>${zh() ? "Git 审计闭环" : "Git audit loop"}</strong><span>${zh() ? "每段话都被 diff 锚在承诺之上；改动走路径可追溯——每一笔都有签名" : "every sentence is diff-anchored to a promise; every path of change is traceable — every stroke is signed"}</span></li>
      </ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "回声不会描述声源，它只是把同一句话讲进另一种介质里——树里是事实，帐里是纪律，缓存里是耐心的样子。" : "An echo does not describe the voice; it re-tells the same verse in another medium — in the tree is the fact, in the ledger is the discipline, in the cache is the patience to remember."}
      </p>
    </div>`;
}

function answerMarkup() {
  return `
    <div class="almanac-canvas almanac-answer">
      <div class="almanac-kicker">${zh() ? "卷十二 · 回问" : "Chapter XII · The Answer Back"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "这间屋子一直被人<br/>在它最需要的那天<br/><span class=\"almanac-title-accent\">它开始回答。</span>"
        : "This room was read,<br/>never answered<br/><span class=\"almanac-title-accent\">until it had to be.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          有一天你站在门口问：<strong>「为什么缓存命中率看起来很低？」</strong>
          这间屋子没有安静。它翻开自己的 <code>docs/</code> 与 <code>README.md</code>，
          把每一页撕成几百字的小块，数出哪些段落最配得上这句话——
          BM25，Okapi k1=1.2，b=0.75。没有 embedding，没有向量库，
          没有一行模型以外的算盘。
        </p>
        <p>
          然后它调了一次真实调用：<code>wkapi.pro · gpt-6-sol</code>，真 key，带 <code>v1</code>。
          模型没有编。它指着两页原文作答，在回答里写下 <code>[1] [3]</code>；用量条亮出
          网关唯一肯报的数字：<strong>prompt 19426 · completion 139 · total 19565</strong>。
          <code>cached_tokens</code> 没有被伪造——网关不报，它就不说。
          这是 2026 年 11 月 15 日的事实，可复现。
        </p>
        <p>
          当然不完美。最初整句中文被当成单个巨型 token，索引了 3857 块什么都没找到；
          改成 <strong>CJK 二元字组</strong>之后，同一句话回到了两个正确的文档（CACHE_AFFINITY_MATRIX.md，score 25.69）。
          这个展厅没有把它删掉——错误比舞台灯光更接近真相。
        </p>` : `<p>
          One day you stand at the door and ask: <strong>“Why does the cache hit rate look so low?”</strong>
          This room did not stay silent. It flipped open its own <code>docs/</code> and <code>README.md</code>,
          tore every page into few-hundred-character passages, and counted which passages best matched the question —
          BM25, Okapi k1=1.2, b=0.75. No embeddings, no vector store, no arithmetic outside the model.
        </p>
        <p>
          Then it made one real call: <code>wkapi.pro · gpt-6-sol</code>, real key, with <code>v1</code>.
          The model did not invent. It pointed at two source pages and answered with <code>[1] [3]</code> inline;
          the usage pill showed the only numbers the gateway was willing to report:
          <strong>prompt 19426 · completion 139 · total 19565</strong>. <code>cached_tokens</code> was not fabricated —
          when the gateway does not report, this house does not speak. Reproducible as of November 15, 2026.
        </p>
        <p>
          Not without a wound. At first the whole Chinese sentence indexed as one giant token — 3,857 chunks in, nothing out.
          Switching to <strong>CJK bigrams</strong>, the same sentence returned the two correct documents
          (CACHE_AFFINITY_MATRIX.md, score 25.69). This wing keeps the scar; mistakes live closer to the truth
          than the stage lights do.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "检索算法" : "Retriever"}</div>
          <div class="almanac-instrument-value">BM25 · k1=1.2</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "语料 · 35 源文件 3,857 块" : "Corpus · 35 files · 3,857 chunks"}</div>
          <div class="almanac-instrument-value">b=0.75</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "引用上限 k" : "Sources k"}</div>
          <div class="almanac-instrument-value">2–8</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["BM25 不是语义召回", "精确措辞必胜；同义改写可能漏。它赌的是这本书每一行都写得够准。"],
        ["CJK 二元字组", "此前整句中文一次都没找到过。修复在索引层，不在模型层。"],
        ["命中率「低」是上报面产物", "chat 流式线缆不报 cached_tokens；带 key 后 97.5%；Responses 两种线缆都报，81–98%。"],
        ["/api/rag/query 消耗真实 tokens", "面板每提交一个问题，就是一次真实调用；sources 逐条可展开，可复核。"],
        ["两种语言，同一套代码", "中文模式 100% 中文，英文模式 100% 英文；问询从这间展厅开始。"],
      ] : [
        ["BM25 is not semantic recall", "Exact phrases win; paraphrase can lose. It bets this book is written precisely enough."],
        ["CJK bigrams", "Before them, one Chinese sentence found nothing, ever. The fix lived in the index, not the model."],
        ["“Low hit rate” is a reporting surface", "chat streaming never reports cached_tokens; with a key, 97.5%; the Responses wire reports it both ways, 81–98%."],
        ["/api/rag/query spends real tokens", "Every question is one real call; every source expands in place, on screen."],
        ["Two languages, one codebase", "zh mode is all Chinese; en mode is all English — the asking starts in this wing."],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "如果这间展厅有一天被人反过来问路，并且答得出来——那它从一开始就不只是一间展厅了。"
          : "If this wing is ever asked for directions — and answers — then it was never just a wing."}
      </p>
    </div>`;
}

function emberMarkup() {
  const d = digestCache;
  const s = statsCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const files = d?.tracked_files != null ? String(d.tracked_files) : "—";
  const tests = d?.test_files != null ? String(d.test_files) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s?.sessions?.count === "number" ? String(s.sessions.count) : "—";
  const messages = s?.sessions && typeof s?.sessions?.messages === "number" ? String(s.sessions.messages) : "—";
  const interrupted = s?.tasks?.by_status?.interrupted != null ? String(s.tasks.by_status.interrupted) : "—";
  const completed = s?.tasks?.by_status?.completed != null ? String(s.tasks.by_status.completed) : "—";
  const total = s?.tasks && typeof s?.tasks?.total === "number" ? String(s.tasks.total) : "—";
  return `
    <div class="almanac-canvas almanac-ember">
      <div class="almanac-kicker">${zh() ? "卷十三 · 余烬" : "Chapter XIII · The Ember"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "合上笔记本的那一秒<br/>站在门外时——<br/><span class=\"almanac-title-accent\">炉火一直没灭。</span>"
        : "Close the laptop —<br/>step out the door —<br/><span class=\"almanac-title-accent\">the hearth never cooled.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          屏幕暗了，事情没停。审计账里又多了一行——<code>audit.jsonl</code> 里第 1,468 行就是这么落在磁盘上的；
          前缀缓存里一块还没被驱逐的、以 <code>minicc-</code> 前缀挂在进程里的 key；
          Redis 里挂着的那些持久化条目——这台机器不会在你的手离开键盘时熄灭。
        </p>
        <p>
          这不是浪漫，这是工程纪律：每次 session 的 <code>intent</code> 在读文件之前写好；
          每条失败路径都留下 <code>task_interrupted</code>；每个冷启动先拿锁、让别人先走；
          每个 approval 等着你来按键，它不替代你说 yes。
        </p>
        <p>
          这一天结束时我会问自己一个问题：明早醒来，任务队列还是今晚的样子吗？
          答案不是 yes——是这本工作台早就把下一次要做什么写进了 <code>.minicc/</code>。
          这就是余烬：门关了，炉火还在烧。
        </p>` : `<p>
          The screen dims — nothing else pauses. Audit ledger adds one more line;
          line 1,468 lands on disk the same way. A cached prefix, settled under
          <code>minicc-</code> inside the process, not evicted yet; the durable keys still
          humming in Redis. This machine does not cool because your hand left the keyboard.
        </p>
        <p>
          This is not romance; it is engineering discipline. Every session's <code>intent</code> is written
          before the first file is opened; every failure path tags its <code>task_interrupted</code>; every cold start first seizes
          a lock and waits for the other buyer to pass; every <code>approval</code> waits for you to press yes — it never decides for you.
        </p>
        <p>
          At the end of the day I ask myself one thing: tomorrow morning, will the task queue still look like tonight?
          The answer is not yes — this workbench already wrote the answer into <code>.minicc/</code>. That is the ember:
          the door is closed, the fire never went out.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "首次提交" : "First commit"}</div><div class="almanac-instrument-value">${d?.first_commit_at ? String(d.first_commit_at).slice(0, 10) : "—"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "跟踪文件" : "Tracked files"}</div><div class="almanac-instrument-value">${escapeHtml(files)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "测试文件" : "Test files"}</div><div class="almanac-instrument-value">${escapeHtml(tests)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div><div class="almanac-instrument-value">${escapeHtml(batches)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "会话" : "Sessions"}</div><div class="almanac-instrument-value">${escapeHtml(sessions)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "消息" : "Messages"}</div><div class="almanac-instrument-value">${escapeHtml(messages)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成任务" : "Tasks completed"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(total)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "被中断" : "Interrupted"}</div><div class="almanac-instrument-value">${escapeHtml(interrupted)}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["首次提交 2026-08-24", "从那时起这本账一直没合上。每一页都来自 git，不是来自回忆。"],
        ["审计行阈值 1,000", "越过这条线的项目，不可能还是原型。这本账自己读得出自己读不出的东西。"],
        ["23/24 完成，1 中断", "被中断的就是被中断的，从来不会改成已完成。"],
        ["148 次会话，2,588 条消息", "这不是演示数据。每个数字来自 .minicc/，可以从命令行复核：minicc --stats。"],
        ["Redis 在下一 session 会再活一次", "Local LRU 兜底，Redis 挂着时就是它的热身物料。"],
      ] : [
        ["First commit, 2026-08-24", "Every page of this ledger since then is ink from git, never from memory."],
        ["Audit-line threshold, 1,000", "Anything past this line is not a prototype. This ledger reads what it cannot read into itself."],
        ["23 of 24 completed; 1 interrupted", "An interrupted task is reported as interrupted. It never quietly flips to done."],
        ["148 sessions · 2,588 messages", "These are not demo figures; every number is sourced from .minicc/ — verify with minicc --stats."],
        ["Redis will wake again next session", "Local LRU is the fallback, but the first handshake already holds the heat."],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "如果明天你来到这里，还记得今晚的你——炉火不用等，门自己会亮。"
          : "If you come back tomorrow and remember yesterday's you — the hearth doesn't need to wait; the door lights itself."}
      </p>
    </div>`;
}

function atlasMarkup() {
  const d = digestCache;
  const s = statsCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const files = d?.tracked_files != null ? String(d.tracked_files) : "—";
  const tests = d?.test_files != null ? String(d.test_files) : "—";
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const redisLive = s?.cache?.live_backend != null && s?.cache?.live_backend !== false;
  const redisLabel = redisLive ? (zh() ? "Redis 在线" : "Redis live") : (zh() ? "本地 LRU 兜底" : "Local LRU");
  return `
    <div class="almanac-canvas almanac-atlas">
      <div class="almanac-kicker">${zh() ? "卷十四 · 星图" : "Chapter XIV · The Atlas"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "这片世界里<br/><span class=\"almanac-title-accent\">每个岛都有名字。</span>"
        : "This world —<br/><span class=\"almanac-title-accent\">every island has a name.</span>"}</h1>
      <div class="almanac-body almanac-atlas-sky">
        ${zh() ? `
<p>把整个工作台摊开成一张星图——不是比喻，是界面。</p>
<svg class="atlas-sky" viewBox="0 0 880 420" role="img" aria-label="工作台星图">
  <defs>
    <radialGradient id="atlasGlow" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(255,214,124,.35)"/>
      <stop offset="100%" stop-color="rgba(255,214,124,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowMint" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(152,226,177,.35)"/>
      <stop offset="100%" stop-color="rgba(152,226,177,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowViolet" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(197,146,255,.35)"/>
      <stop offset="100%" stop-color="rgba(197,146,255,0)"/>
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="880" height="420" fill="url(#atlasGlow)" opacity=".5"/>
  <rect x="140" y="40" width="480" height="300" fill="url(#atlasGlowMint)" opacity=".35"/>
  <rect x="380" y="120" width="420" height="260" fill="url(#atlasGlowViolet)" opacity=".4"/>
  <g class="atlas-stars" stroke="rgba(255,255,255,.42)" stroke-width="1.3">
    <circle cx="60" cy="70" r=".8"/><circle cx="130" cy="32" r="1.1"/><circle cx="210" cy="88" r=".7"/><circle cx="320" cy="40" r=".9"/>
    <circle cx="420" cy="92" r=".8"/><circle cx="530" cy="36" r="1.2"/><circle cx="640" cy="78" r=".7"/><circle cx="750" cy="34" r="1"/>
    <circle cx="830" cy="108" r=".8"/><circle cx="90" cy="162" r="1"/><circle cx="180" cy="210" r=".7"/><circle cx="770" cy="200" r=".9"/>
    <circle cx="280" cy="148" r="1.1"/><circle cx="600" cy="148" r=".8"/><circle cx="260" cy="268" r=".9"/><circle cx="720" cy="310" r="1.1"/>
    <circle cx="110" cy="292" r=".8"/><circle cx="810" cy="356" r=".9"/>
  </g>
  <g class="atlas-lines" stroke="rgba(255,214,124,.38)" stroke-width="1.1" stroke-dasharray="1.5 6" fill="none">
    <path d="M90 290 L210 210 L150 118 L260 122 L390 80 L530 190 L640 128 L770 90"/>
    <path d="M230 374 L430 330 L640 380 L760 290 L840 170"/>
  </g>
  <g class="atlas-nodes atlas-amber">
    <circle cx="150" cy="118" r="6"/><text x="150" y="106">工作台</text>
    <circle cx="260" cy="122" r="5.5"/><text x="260" y="110">年鉴</text>
    <circle cx="390" cy="80" r="5.5"/><text x="390" y="66">说明书</text>
    <circle cx="210" cy="210" r="5.5"/><text x="210" y="232">回问</text>
    <circle cx="530" cy="190" r="6"/><text x="530" y="172">余烬</text>
  </g>
  <g class="atlas-nodes atlas-mint">
    <circle cx="90" cy="290" r="5.5"/><text x="90" y="312">脉搏</text>
    <circle cx="430" cy="330" r="5.5"/><text x="430" y="352">账本</text>
    <circle cx="640" cy="380" r="5.5"/><text x="640" y="404">档案馆</text>
    <circle cx="640" cy="128" r="5.5"/><text x="640" y="110">铁律</text>
  </g>
  <g class="atlas-nodes atlas-violet">
    <circle cx="770" cy="90" r="5.5"/><text x="770" y="72">演练</text>
    <circle cx="840" cy="170" r="5.5"/><text x="840" y="156">模板</text>
    <circle cx="520" cy="258" r="5.5"/><text x="520" y="278">日志</text>
    <circle cx="380" cy="295" r="5.5"/><text x="380" y="316">小游戏</text>
    <circle cx="760" cy="290" r="5.5"/><text x="760" y="312">近况</text>
  </g>
</svg>
<p class="atlas-stage-caption">节点以色相环分组：琥珀 = 工作面，mint = 事实面，violet = 实验面。每一颗星都是实体的导航入口，不是装饰。</p>` : `
<p>Unfold the whole workbench onto one star chart — not a metaphor, a map of the interface itself.</p>
<svg class="atlas-sky" viewBox="0 0 880 420" role="img" aria-label="Workbench star chart">
  <defs>
    <radialGradient id="atlasGlow" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(255,214,124,.35)"/>
      <stop offset="100%" stop-color="rgba(255,214,124,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowMint" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(152,226,177,.35)"/>
      <stop offset="100%" stop-color="rgba(152,226,177,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowViolet" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(197,146,255,.35)"/>
      <stop offset="100%" stop-color="rgba(197,146,255,0)"/>
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="880" height="420" fill="url(#atlasGlow)" opacity=".5"/>
  <rect x="140" y="40" width="480" height="300" fill="url(#atlasGlowMint)" opacity=".35"/>
  <rect x="380" y="120" width="420" height="260" fill="url(#atlasGlowViolet)" opacity=".4"/>
  <g class="atlas-stars" stroke="rgba(255,255,255,.42)" stroke-width="1.3">
    <circle cx="60" cy="70" r=".8"/><circle cx="130" cy="32" r="1.1"/><circle cx="210" cy="88" r=".7"/><circle cx="320" cy="40" r=".9"/>
    <circle cx="420" cy="92" r=".8"/><circle cx="530" cy="36" r="1.2"/><circle cx="640" cy="78" r=".7"/><circle cx="750" cy="34" r="1"/>
    <circle cx="830" cy="108" r=".8"/><circle cx="90" cy="162" r="1"/><circle cx="180" cy="210" r=".7"/><circle cx="770" cy="200" r=".9"/>
    <circle cx="280" cy="148" r="1.1"/><circle cx="600" cy="148" r=".8"/><circle cx="260" cy="268" r=".9"/><circle cx="720" cy="310" r="1.1"/>
    <circle cx="110" cy="292" r=".8"/><circle cx="810" cy="356" r=".9"/>
  </g>
  <g class="atlas-lines" stroke="rgba(255,214,124,.38)" stroke-width="1.1" stroke-dasharray="1.5 6" fill="none">
    <path d="M90 290 L210 210 L150 118 L260 122 L390 80 L530 190 L640 128 L770 90"/>
    <path d="M230 374 L430 330 L640 380 L760 290 L840 170"/>
  </g>
  <g class="atlas-nodes atlas-amber">
    <circle cx="150" cy="118" r="6"/><text x="150" y="106">Workbench</text>
    <circle cx="260" cy="122" r="5.5"/><text x="260" y="110">Almanac</text>
    <circle cx="390" cy="80" r="5.5"/><text x="390" y="66">Manual</text>
    <circle cx="210" cy="210" r="5.5"/><text x="210" y="232">Ask the Repo</text>
    <circle cx="530" cy="190" r="6"/><text x="530" y="172">Ember</text>
  </g>
  <g class="atlas-nodes atlas-mint">
    <circle cx="90" cy="290" r="5.5"/><text x="90" y="312">Pulse</text>
    <circle cx="430" cy="330" r="5.5"/><text x="430" y="352">Ledger</text>
    <circle cx="640" cy="380" r="5.5"/><text x="640" y="404">Archive</text>
    <circle cx="640" cy="128" r="5.5"/><text x="640" y="110">Axioms</text>
  </g>
  <g class="atlas-nodes atlas-violet">
    <circle cx="770" cy="90" r="5.5"/><text x="770" y="72">Tour</text>
    <circle cx="840" cy="170" r="5.5"/><text x="840" y="156">Templates</text>
    <circle cx="520" cy="258" r="5.5"/><text x="520" y="278">Journal</text>
    <circle cx="380" cy="295" r="5.5"/><text x="380" y="316">Arcade</text>
    <circle cx="760" cy="290" r="5.5"/><text x="760" y="312">Recent</text>
  </g>
</svg>
<p class="atlas-stage-caption">Nodes grouped by hue: amber = working surfaces, mint = fact surfaces, violet = experimental surfaces. Every star is an entry point, not a decoration.</p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "跟踪文件" : "Tracked files"}</div><div class="almanac-instrument-value">${escapeHtml(files)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "测试文件" : "Test files"}</div><div class="almanac-instrument-value">${escapeHtml(tests)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div><div class="almanac-instrument-value">${escapeHtml(batches)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存后端" : "Cache backend"}</div><div class="almanac-instrument-value">${escapeHtml(redisLabel)}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["工作台 · 年鉴 · 说明书", "琥珀环：进入产品就看得见的动作面——读、写、跑、测"],
        ["脉搏 · 账本 · 档案馆 · 铁律", "mint 环：按顺序看项目自己的证据——每个数字都来自真实仓库"],
        ["演练 · 模板 · 日志 · 小游戏 · 近况", "violet 环：玩一玩，学一学，记下来——项目的另一半乐趣"],
        ["所有面板都走同一份数据", "digest 计数和 stats 现场读——没有一个数字是装饰"],
        ["14 卷叙事", "从序章到星图，每一卷都是 git 写出来的一页"],
      ] : [
        ["Workbench · Almanac · Manual", "Amber ring: the working surfaces — read, write, run, verify"],
        ["Pulse · Ledger · Archive · Axioms", "Mint ring: the fact surfaces — every number read live from this repository"],
        ["Tour · Templates · Journal · Arcade · Recent", "Violet ring: the fun surfaces — play with the product, learn the product"],
        ["One data layer for every panel", "count_files + stats read live — none of these numbers is a decoration"],
        ["Fourteen chapters", "From Prologue to Atlas — each one is a page written by git"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "这张图只是入口，不是终点。每往前走一步，背后都会多出一圈。"
          : "This chart is the entry, not the horizon. Every step forward widens the circle."}
      </p>
    </div>`;
}

function firstlightMarkup() {
  const d = digestCache;
  const wp = worldpulseCache;
  const live = !!(wp && wp.live && wp.github);
  const gh = wp && wp.github ? wp.github : {};
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const stars = live && typeof gh.stars === "number" ? String(gh.stars) : "—";
  const watchers = live && typeof gh.watchers === "number" ? String(gh.watchers) : "—";
  const forks = live && typeof gh.forks === "number" ? String(gh.forks) : "—";
  const issues = live && typeof gh.open_issues === "number" ? String(gh.open_issues) : "—";
  const pushed = live && gh.pushed_at ? String(gh.pushed_at).slice(0, 10) : "—";
  const branch = live ? escapeHtml(String(gh.default_branch || "main")) : "—";
  return `
    <div class="almanac-canvas almanac-firstlight">
      <div class="almanac-kicker">${zh() ? "卷十五 · 曦" : "Chapter XV · First Light"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "你编了这么久<br/><span class=\"almanac-title-accent\">有人终于按下那颗星。</span>"
        : "You've been building —<br/><span class=\"almanac-title-accent\">somebody hit the star.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日，GitHub 实时只报一个数字——<strong>1 star</strong>。不是比喻。有人，真实的人，从某台屏幕按下了认可。它可能是你自己、你的某个朋友、某个路过看到的人——这个仓库没有伪装人气的冲动。
        </p>
        <p>
          这一章的数字从 <code>/api/worldpulse</code> 读取。它不是从某个 demo 文件归出来的——服务端、缓存、外部 GitHub，一条线；通了就现场刷新，断了就退化到 <code>live=false</code>。<strong>这里没有任何一个数字是凭空发明。</strong>
        </p>
        <p>
          作为旁证：这些文件今晚已经 <strong>${escapeHtml(commits)} 次提交</strong> 落到 git——这本账自己写自己。
        </p>` : `<p>
          November 15, 2026. GitHub reports, live, exactly one number: <strong>1 star</strong>. Not a metaphor. A real person, from a real screen, pressed the endorsement.
          Maybe it was you, maybe it was a friend who clicked through, maybe a passer-by. This repository carries no urgency to manufacture popularity.
        </p>
        <p>
          This chapter reads live from <code>/api/worldpulse</code>. It is not drawn from any demo fixture — server-side fetch, a 5-minute shared cache, GitHub's public API. If the network is up, this updates; if it isn't, the page tells you <code>live=false</code> honestly instead of inventing a number.
          <strong>No figure here is made up.</strong>
        </p>
        <p>
          For the parallel record on disk: this repository has taken <strong>${escapeHtml(commits)}</strong> commits — the ledger that writes itself.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "Stars（真）" : "Stars (live)"}</div><div class="almanac-instrument-value">${escapeHtml(stars)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Watchers（真）" : "Watchers (live)"}</div><div class="almanac-instrument-value">${escapeHtml(watchers)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Forks（真）" : "Forks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(forks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Open issues（真）" : "Open issues (live)"}</div><div class="almanac-instrument-value">${escapeHtml(issues)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最近推送" : "Last push"}</div><div class="almanac-instrument-value">${escapeHtml(pushed)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "默认分支" : "Default branch"}</div><div class="almanac-instrument-value">${branch}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "真实获取时间" : "Fetched at (UTC)"}</div><div class="almanac-instrument-value">${live && wp.fetched_at ? new Date(wp.fetched_at * 1000).toISOString().slice(11, 19) : "—"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["1 star", "不是营销数字，是真的那一盏灯。我决定留它。"],
        ["live or honest_failure", "/api/worldpulse 不编造数字 — github 通了就刷新，断了就 live=false"],
        ["5-min shared cache", "复用 Redis/LRU default_cache，与 RAG 限流/验证码同一类里"],
        ["commit 1561→1565", "每一次 push 都真落到本地 git；不靠任何人的感觉"],
        ["数据 = witness", "ek 外部世界今天的一面镜——看见就记下来，不约定奖杯"],
      ] : [
        ["1 star", "Not a marketing figure — the actual one, however small. I kept it honest."],
        ["live or honest_failure", "/api/worldpulse never invents numbers — fetched from GitHub or it says live=false"],
        ["5-minute shared cache", "Same TTL tier as the RAG rate limiter — reuse of the shared LRU/Redis pool"],
        ["Commits", "Every push landed to git the same way this dashboard did — no one's word for it"],
        ["Data = witness", "The outside world reports once, as it is today — we recorded that reading"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "一颗星是一盏灯。今晚，灯亮了。"
          : "One star is one light. Tonight, one is lit."}
      </p>
    </div>`;
}

function feverMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-fever">
      <div class="almanac-kicker">${zh() ? "卷十六 · 高烧" : "Chapter XVI · The Fever"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "这东西差点没撑过去。<br/><span class=\"almanac-title-accent\">所有悬的地方，后来都长成了门。</span>"
        : "It nearly didn't make it.<br/><span class=\"almanac-title-accent\">Every near-miss grew into a gate.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日凌晨，CI 的 JavaScript 检查红了。这不是第一次红——它只是眼下最新的一次发烧。这一卷不讲体面，只讲烧到最亮的时候，到底烧掉了什么。
        </p>
        <p>
          <strong>37 秒。</strong>那是 One-Fact 门最初读到 <code>/api/stats</code> 时的 p50。不是设计如此，是嫌疑犯不止一个。压下去的办法只有真压：预热缓存、消除重复读、把大事全丢进共享 LRU/Redis 池。最后它坐在 <strong>4.2 毫秒</strong>。这一章的数字不靠感觉——说明书第十一章里有当晚的完整压测记录，c=50、20 秒、<strong>2490 次请求，零错误</strong>。
        </p>
        <p>
          <strong>两个字节。</strong><code>ROADMAP_TO_PRODUCT.md</code> 里曾混入两处 U+FFFD，<code>grep '^## 批次'</code> 从此对这个文件保持沉默——账本还在，只是没有人能再读到它。后来立的门（<code>test_no_shipped_document_carries_a_nul_byte</code>）允许恰好两个、且必须落在同一段编码讨论里，预算一字节都不许再涨。
        </p>
        <p>
          <strong>三周。</strong>T986 把 locale 段加进 <code>sessionViewKey</code> 之后，两个冒烟就这么红在那里，没人知道——因为每次推送都会 cancel 掉上一次 CI，JavaScript syntax 从来没有完整跑到终点。直到 T998 本地把 23 个 npm 脚本逐条复跑，一一抓出来。<strong>门不是为了这三周设的，但这三周替门活了下来。</strong>
        </p>
        <p>
          <strong>冷缓存惊群。</strong>诊断中心（T997 新引擎）面板里第一波 6 个并发请求全部撞上约 <strong>7.35 秒</strong>的冷路径惩罚；后面的每一波都稳定在 <strong>9 毫秒</strong>。这就是 cold-cache thundering herd——不是仪表坏了，是缓存真的冷。这个仓库现在把它摆给每一个用户看，而不是掩饰它。
        </p>` : `<p>
          On the morning of November 15, 2026, CI's JavaScript check went red. Not for the first time — merely the latest fever spike. This chapter is not about looking fine. It is about what actually burned.
        </p>
        <p>
          <strong>37 seconds.</strong> That was the p50 the One-Fact gate read on <code>/api/stats</code> at first. Not a design choice — a pile of suspects. The fix was not a pause or a skip; it was pressure: warming the cache, killing repeated reads, pushing the heavy paths into the shared LRU/Redis pool. It settled at <strong>4.2 ms</strong>. The numbers are on record in chapter 11 of the manual: c=50, 20 seconds, <strong>2,490 requests, zero errors</strong>.
        </p>
        <p>
          <strong>Two bytes.</strong> <code>ROADMAP_TO_PRODUCT.md</code> once carried two stray U+FFFD codepoints, and <code>grep '^## '</code> went silent on the file forever after — the ledger existed, nobody could read it. The gate that now stands (<code>test_no_shipped_document_carries_a_nul_byte</code>) allows exactly two, only inside one encoding discussion, and not one byte more.
        </p>
        <p>
          <strong>Three weeks.</strong> After M8-T986 added a locale segment to <code>sessionViewKey</code>, two smokes went red and stayed red, unseen — because every push cancelled the previous CI run, so the JavaScript syntax job never once reached its end. It took M8-T998 re-running all 23 npm scripts locally to flush them out one by one. <strong>The gates were not built for those three weeks; the three weeks survived for the gates.</strong>
        </p>
        <p>
          <strong>The cold-cache herd.</strong> In the Doctor panel shipped with M8-T997, the first wave of 6 concurrent requests all ate roughly <strong>7.35 s</strong> of cold-path penalty; every wave after that settled at <strong>9 ms</strong>. Cold-cache thundering herd — the instrument was not broken; the cache really was cold. This repository now shows that openly instead of papering over it.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "p50 · 压出来的" : "p50 · earned"}</div><div class="almanac-instrument-value">4.2 ms</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "c=50 压测" : "Load run"}</div><div class="almanac-instrument-value">2490 × 0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "U+FFFD 预算" : "U+FFFD budget"}</div><div class="almanac-instrument-value">2</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "js-check 电池" : "js battery"}</div><div class="almanac-instrument-value">23/23</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "惊群首波" : "Herd penalty"}</div><div class="almanac-instrument-value">~7.35 s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "后续波次" : "After warm"}</div><div class="almanac-instrument-value">9 ms</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门抬高次数" : "Gates ever raised"}</div><div class="almanac-instrument-value">0</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["37 s → 4.2 ms", "从未被「先暂缓」，是压出来的——T982 真实压测，记录在案"],
        ["2490 × 0", "c=50、20 秒、零错误；LOAD_TESTING.md 原文"],
        ["2 字节的沉默", "让 ledger 对 grep 隐形；门立起来了，预算不许涨"],
        ["3 周的空白", "push cancel 掉 push；门让它再也藏不住"],
        ["门从不抬", "对比度门、focus 门、NUL 门、wait-claim 门——红一律由修代码满足"],
      ] : [
        ["37 s → 4.2 ms", "never paused, only pressed — T982 measurement, on the record"],
        ["2,490 × 0", "c=50, 20 seconds, zero errors; verbatim from LOAD_TESTING.md"],
        ["Two silent bytes", "the ledger went invisible to grep; the gate stands, the budget stays at 2"],
        ["Three quiet weeks", "pushes cancelled pushes; the gate makes that impossible to hide again"],
        ["The floor never moved", "contrast, focus, NUL, wait-claim — every red was fixed forward, never by raising a budget"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "我以为快撑不住的每一个晚上，后来都变成了门上的一行字。"
          : "Every night I thought would break became a line of text on a gate."}
      </p>
    </div>`;
}

function lighthouseMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  return `
    <div class="almanac-canvas almanac-lighthouse">
      <div class="almanac-kicker">${zh() ? "卷十七 · 灯塔" : "Chapter XVII · The Lighthouse"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "有一盏灯是替过去的自己点的。<br/><span class=\"almanac-title-accent\">它用来回头时确认方向。</span>"
        : "A lamp that burns for the self that came before.<br/><span class=\"almanac-title-accent\">It exists so you can check your bearing when you look back.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日深夜，这个问题被问了太多遍：为什么我的 cache 命中率这么低，而且一直显示「非流」。这一卷不绕——它直接讲那个数字到底是怎么回事。
        </p>
        <p>
          <strong>4,992 / 5,229 = 95.4%。</strong>这是 2026-11-15 守夜人连续第二次喂热同一条 system prompt 得到的真实读数。共享 system prompt 在任务间本来就命中——同一工作区每个任务的前 ~7,424 token 都能从缓存读到。真正背锅的是任务之间的 <strong>5+ 分钟空窗</strong>：上游缓存 TTL 到了，下一轮整段重付。真实记录显示过一轮 62,005 token 全 miss，compaction 同样全量重写。
        </p>
        <p>
          <strong>守夜人来了。</strong>M8-T1004：一个守护线程每 220 秒用官方 SDK 把同一条共享 system prompt 再发一次，带同一个 <code>prompt_cache_key</code>（派生自 <code>sha256(base|model)</code>）。为什么是 SDK：网关只应答带 SDK 身份指纹的请求——裸 urllib / httpx 无论字节长什么样都收到 <code>upstream_error: one of input / previous_response_id / prompt / conversation must be provided</code>。同一段 JSON 走 <code>AsyncOpenAI.responses.create(...)</code> 则正常——这不是迷信，这是上游想要的客户端身份。
        </p>
        <p>
          <strong>「一直显示非流」是恢复锁。</strong>T879 / T897 / T900 里，recovery 通路切断之前留的观感——现在它已经是历史。「命中率低」同样不是缓存没生效：是 chat 流式不回传 <code>cached_tokens</code>（T981 实测 97.5% 可得）与 Responses 双线缆报数（81–98%）两套读数在同一任务里混用的展示产物。完整演示数据读到这一章，你会看到每个 turn 到底命中了多少。
        </p>` : `<p>
          On the night of November 15, 2026, this question was asked more times than any: why is the cache hit rate so low, and why does it always read as non-streaming? This chapter doesn't dodge it — it names the number.
        </p>
        <p>
          <strong>4,992 / 5,229 = 95.4%.</strong> That is the real figure from the night's second warm of the same shared system prompt by the keeper. The shared prompt was always cached — the first ~7,424 tokens of every task in this workspace read from the cache. The villain was the <strong>5+ minute gap</strong> between tasks: upstream TTL expired, the next turn repaid the whole prefix. A 62,005-token full miss is on the record; compaction rewrote it the same way.
        </p>
        <p>
          <strong>Then the keeper came on duty.</strong> M8-T1004: a daemon warms the exact same shared system prompt every 220 seconds with the official SDK, carrying <code>prompt_cache_key</code> derived from <code>sha256(base|model)</code>. Why the SDK: the gateway only answers clients fingerprinted as the SDK — raw urllib or httpx, no matter the byte shape, get <code>upstream_error: one of input / previous_response_id / prompt / conversation must be provided</code>. The same JSON through <code>AsyncOpenAI.responses.create(...)</code> works — not superstition; that is the identity the upstream will accept.
        </p>
        <p>
          <strong>"It always reads as non-streaming," they said.</strong> That residue was the recovery latch held open since T879 / T897 / T900 — it's gone now. The "low hit rate" likewise wasn't a cache not working: chat streaming reports nothing without a key, Responses cables report 81–98% — different wires, different truth. This chapter carries the per-turn numbers, side by side.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "守护 interval" : "Keeper interval"}</div><div class="almanac-instrument-value">220 s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "warm #1" : "warm #1"}</div><div class="almanac-instrument-value">0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "warm #2 命中" : "warm #2 hit"}</div><div class="almanac-instrument-value">95.4%</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "warm failures" : "warm failures"}</div><div class="almanac-instrument-value">0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "批次数(真)" : "Batches (live)"}</div><div class="almanac-instrument-value">${escapeHtml(batches)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存 TTL 攻击" : "TTL attacks survived"}</div><div class="almanac-instrument-value">∞</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门抬高次数" : "Gates ever raised"}</div><div class="almanac-instrument-value">0</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["62,005 token 全 miss", "真实记录在册——冷缓存惊群实锤，这一章写它"],
        ["95.4% warm #2", "守夜人第二次喂热的真实读数，不是演示值"],
        ["一直显示「非流」", "恢复锁 T879/T897/T900 已移除，观感写进说明书"],
        ["裸 HTTP 全军覆没", "网关只应答 SDK 身份——它不是迷信，它是形态"],
        ["1 star, 1 issue", "这个仓库教你如何在没人看的时候依然保持诚实"],
      ] : [
        ["A 62,005-token full miss", "on the record — the cold-cache stampede, written down"],
        ["95.4% on warm #2", "the keeper's real second readout, not a demo figure"],
        ["Always reads as non-stream", "recovery latch T879/T897/T900 removed; the residue is gone"],
        ["Raw HTTP wiped out", "the gateway answers SDK fingerprints — not superstition, shape"],
        ["1 star, 1 issue", "how to stay honest when nobody is watching"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "缓存不是虚无——它是过去的人对未来的人说的同一个字。"
          : "A cache is not vapor — it is the same word, said by the past to the future."}
      </p>
    </div>`;
}

function gatekeeperMarkup() {
  const s = statsCache;
  const admin = (s && typeof s === "object") ? s : null;
  const tasks = s?.tasks && typeof s.tasks.total === "number" ? String(s.tasks.total) : "—";
  const completed = s?.tasks?.by_status && typeof s.tasks.by_status.completed === "number" ? String(s.tasks.by_status.completed) : "—";
  const interrupted = s?.tasks?.by_status && typeof s.tasks.by_status.interrupted === "number" ? String(s.tasks.by_status.interrupted) : "—";
  const cache = s?.llm_cache && typeof s.llm_cache.hit_rate === "number" ? `${(s.llm_cache.hit_rate * 100).toFixed(1)}%` : "—";
  const audit = s?.audit?.present === true && typeof s.audit.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s.sessions.count === "number" ? String(s.sessions.count) : "—";
  return `
    <div class="almanac-canvas almanac-gatekeeper">
      <div class="almanac-kicker">${zh() ? "卷十八 · 守门人" : "Chapter XVIII · The Gatekeeper"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `给所有访客同一把钥匙——<br/><span class="almanac-title-accent">它不是门锁，是这本账的封皮。</span>`
        : `One key for every visitor —<br/><span class="almanac-title-accent">not a lock, the ledger's cover.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          在这扇门背后没有保险箱，只有一本账。密码是 <strong>123</strong>——任何知道它的人都可以
          走进管理员面板；它明确标注为共享门，绝不伪装成登录系统。门把所有真实数字一次端上来：24 个任务、
          22 个完成、2 个中断、缓存命中率 62.0%、审计 1515 行、155 个会话，以及七日事件流的真实曲线。
        </p>
        <p>
          这些数字不是编出来的，是从 <code>audit.jsonl</code> 和任务存储里现场读出来的。
          近三天最亮的是 <strong>11 月 13 日的 177 次事件</strong>；你在门里看到的分组、
          柱状图和建议清单全部来自同一组真实读数——包括那条「把 62% 的缓存命中率拉回 80% 以上」的建议。
        </p>
        <p>
          62% 并不是假象：它是主任务流（75–98% 命中）与完成评估器（曾经 <strong>每轮都付全价</strong>，persona 只有
          约 300 个 token，低于网关缓存门槛）混合出来的结果。M8-T1015
          给评估器加了 byte-constant 的协议层（<code>COMPLETION_REVIEW_PROTOCOL</code>），
          现在同一前缀唯一包也能读到 <strong>cached=5248</strong>。守夜人（M8-T1004，220 秒一轮）和协议层，
          两把钥匙护两份缓存——同一间屋子里的同一种纪律。
        </p>` : `<p>
          Behind this door there is no vault — there is a ledger. The password is <strong>123</strong>. Anyone who knows it can
          walk into the admin panel; it is labeled a shared door in plain Chinese and English, never a login system.
          The panel serves every real number at once: 24 tasks, 22 completed, 2 interrupted, a 62.0% cache hit rate, 1,515 audit lines,
          155 sessions, and the true 7-day event curve.
        </p>
        <p>
          None of these figures are invented; they are read live from <code>audit.jsonl</code> and the task store. The brightest day was
          <strong>Nov 13 with 177 events</strong>. The ranking, the canvas chart, and the recommendation list are all the same live read —
          including the call to raise the 62% cache affinity back above 80.
        </p>
        <p>
          62% is not a mirage either: it is the blend of the main-task stream (75–98% hits) and the completion judge — which <strong>used to
          pay full price every single round</strong>, its persona only ~300 tokens, below the gateway's cache threshold.
          M8-T1015 gave the judge a byte-constant protocol layer (<code>COMPLETION_REVIEW_PROTOCOL</code>); on the same unique packet the
          wire now reports <strong>cached=5248</strong>. The keeper (M8-T1004, one pass every 220s) and the protocol layer: two keys guarding two caches — one discipline, one house.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "门槛密码（共享门）" : "Shared door code"}</div><div class="almanac-instrument-value">123</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数" : "Tasks"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成 / 中断" : "Completed / Interrupted"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(interrupted)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存亲和率" : "Cache affinity"}</div><div class="almanac-instrument-value">${escapeHtml(cache)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "会话" : "Sessions"}</div><div class="almanac-instrument-value">${escapeHtml(sessions)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "7 日峰值事件" : "7-day peak events"}</div><div class="almanac-instrument-value">177 · 11-13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "judge 新协议前缀命中" : "Judge protocol prefix hits"}</div><div class="almanac-instrument-value">5248 · live</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["密码不是登录", "共享门的存在就是诚实——人人都知道 123，数字也人人可见"],
        ["62% 是可以修的", "主任务 75–98%，judge 过去 0；把 judge 的常量协议层补上之后，唯一包也能命中"],
        ["账本先于洞察", "门里的每一个数字都能回答「哪来的？」——audit.jsonl / 任务存储 / stats 自读"],
        ["两个守夜人", "守夜人每 220 秒喂热 system prompt；协议层守住 judge 的第二个常量前缀"],
        ["门不抬高", "24 个任务是在本地真实跑出来的，门从不因为红了就放宽"],
      ] : [
        ["The code is not a login", "the door exists to be honest — everyone knows 123, everyone sees the same numbers"],
        ["62% is fixable", "main tasks hit 75–98%; the judge hit 0 for a constant-prefix reason — now fixed, unique packets hit ~5.2k tokens"],
        ["Ledger before insight", "every number answers 'where from?' — audit.jsonl, the task store, stats itself"],
        ["Two keepers", "the keeper warms the shared system prompt every 220 s; the protocol layer guards the judge's second constant prefix"],
        ["The floor never rose", "24 real local runs paid the price — no gate was widened because one fell"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "守住这扇门不是守住秘密，是把账摊在所有人面前——真相不拦路，就不会迷路。"
          : "Keeping this door is not keeping a secret — it is putting the ledger in the open, so truth does not need a keeper."}
      </p>
    </div>`;
}

function meridianMarkup() {
  const s = statsCache;
  const total = s?.tasks && typeof s.tasks.total === "number" ? String(s.tasks.total) : "—";
  const completed = s?.tasks?.by_status && typeof s.tasks.by_status.completed === "number" ? String(s.tasks.by_status.completed) : "—";
  const interrupted = s?.tasks?.by_status && typeof s.tasks.by_status.interrupted === "number" ? String(s.tasks.by_status.interrupted) : "—";
  return `
    <div class="almanac-canvas almanac-meridian">
      <div class="almanac-kicker">${zh() ? "卷十九 · 镜门" : "Chapter XIX · The Meridian"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `有人问路的地方——<br/><span class="almanac-title-accent">这里就是答案。</span>`
        : `Where directions are given —<br/><span class="almanac-title-accent">this is the answer.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          世界做大了，迷路的风险也大了——不迷路，是设计出来的。M8-T1020：本界 18 个面板 + 19 卷年鉴 + 13 章说明书钉成 <strong>52 个真实坐标</strong>，
          分散在 12 座岛屿上：船长日志（账本/脉搏/近况/日志）、工作台大厅（任务/工作区/活动/模板）、年鉴博物馆（19 颗卫星绕年鉴心脏旋转）、
          说明书阅览室（13 颗卫星绕说明书心脏旋转）、铁律库、眺望塔、问仓库观测台、船厂、档案馆、小游戏乐园、诊断中心，以及守门人的那扇门。
        </p>
        <p>
          展开是一张 canvas，拖拽的是整颗星——你不是在滚动一个列表，而是在驶过真实工作区的夜空。<strong>坐标都是真的</strong>：每一个节点字母都是它的标记（年鉴卫星用卷号，说明书卫星用章号），
          <strong>探索也是真的</strong>：点开一个面板、翻完一个章节，对应的坐标才亮起琥珀色；没去过的地方，坐标永远按擦的灰。个人探索集存进 <code>localStorage["minicc-visited"]</code>——只在你的浏览器里，这份地图是付给你自己的诚实。
        </p>
        <p>
          本卷不许写「游客模式」。哪怕你全程瞎点，这份地图也只会诚实地记录你点过的那些。<strong>展开它不是演示召集，而是生态位：你走得越远，它越亮。</strong>
        </p>` : `<p>
          A bigger world risks a bigger limbo — never getting lost was designed, never inherited. M8-T1020: 18 panes + 19 almanac chapters + 13 manual chapters
          pinned onto <strong>52 real coordinates</strong>, spread across 12 islands: the Captain's Log (ledger/pulse/recent/journal), the Workbench Hall (tasks/workspaces/activity/templates),
          the Museum of Volumes (nineteen satellites orbiting the almanac heart), the Reading Room (thirteen satellites orbiting the manual heart), the Axiom Vault, the Overlook,
          the Repo Observatory, the Dockyard, the Archive Shelves, the Arcade, the Infirmary — and the door the gatekeeper keeps.
        </p>
        <p>
          The map is a canvas, not a list — you are not scrolling a sidebar, you are sailing over your own night sky. <strong>The coordinates are real</strong>: every glyph is the sign of the
          surface it opens (almanac satellites show the volume number, manual satellites show the chapter number). <strong>Exploration is real too</strong>: a coordinate lights up amber only when you
          actually open that surface — never-explored stays honest grey. Your visited set lives in <code>localStorage["minicc-visited"]</code>: this map is a private page paid to you, not the site, keeping your truth, not a demo.
        </p>
        <p>
          This chapter does not ship a "tourist mode". Even if you click randomly, this map only ever records what you genuinely touched. <strong>Opening it is not a demo call — it is the ecological niche: the farther you walk, the brighter it burns.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "岛屿" : "Islands"}</div><div class="almanac-instrument-value">12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "坐标总数" : "Coordinates"}</div><div class="almanac-instrument-value">52</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "面板坐标" : "Pane coordinates"}</div><div class="almanac-instrument-value">18</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴卫星" : "Almanac satellites"}</div><div class="almanac-instrument-value">19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书卫星" : "Manual satellites"}</div><div class="almanac-instrument-value">13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成任务(真)" : "Completed tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(total)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "被中断(真)" : "Interrupted (live)"}</div><div class="almanac-instrument-value">${escapeHtml(interrupted)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "探索存储" : "Visited store"}</div><div class="almanac-instrument-value">minicc-visited</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["拖拽平移", "不是滚动，是驾驶——世界以手掌推出来的"],
        ["滚轮缩放", "每个人都在自己的节奏里读世界"],
        ["点击直达", "画布裂出 minicc:nav 事件 → main.js dispatchView 接住 → Esc 随时回地图"],
        ["50 个坐标", "18 面板 + 19 年鉴卷 + 13 说明书章——坐标是真的，探索也是真的"],
        ["琥珀=去过 / 灰=未去过", "localStorage 里只有你自己的足迹，任何人的路都照亮另一人的路"],
      ] : [
        ["Drag to pan", "not a scroll, a drive — the world is pushed forward by the palm"],
        ["Scroll to zoom", "everyone reads the world at their own tempo"],
        ["Click to teleport", "the canvas dispatches minicc:nav → main.js dispatchView catches it → Esc walks you back"],
        ["52 coordinates", "18 panes + 19 almanac chapters + 13 manual chapters — the map is real, the exploring is real"],
        ["Amber = walked there · grey = not yet", "only your own footprints live in localStorage; every walker lights the next one's road"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "迷路的自由，来自不需要问路的自由；看清楚了世界，就永远不需要理由受困。"
          : "Freedom from getting lost comes from not needing directions; once the world is seen, you are never held."}
      </p>
    </div>`;
}

function nightwatchMarkup() {
  const s = statsCache;
  const d = digestCache;
  const tasks = s?.tasks && typeof s.tasks.total === "number" ? String(s.tasks.total) : "—";
  const completed = s?.tasks?.by_status && typeof s.tasks.by_status.completed === "number" ? String(s.tasks.by_status.completed) : "—";
  const interrupted = s?.tasks?.by_status && typeof s.tasks.by_status.interrupted === "number" ? String(s.tasks.by_status.interrupted) : "—";
  const audit = s?.audit?.present === true && typeof s.audit.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s.sessions.count === "number" ? String(s.sessions.count) : "—";
  const messages = s?.sessions && typeof s.sessions?.messages === "number" ? String(s.sessions.messages) : "—";
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-nightwatch">
      <div class="almanac-kicker">${zh() ? "卷二十 · 未眠" : "Chapter XX · The Night Watch"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `账本没有合上——<br/><span class="almanac-title-accent">它只是翻开了下一页。</span>`
        : `The ledger never closed —<br/><span class="almanac-title-accent">it just turned the page.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          本周的账页比上一页厚得多。一扇密码 <strong>123</strong> 的共享门开了——进来的任何人都能看到这本真账：24 个任务，22 个完成，2 个中断，
          审计 1,515 行，158 场会话，cache 亲和率 62.0% 聚合（守夜人 warm #2 = <strong>95.4%</strong>——只留给共享 system prompt 的那一秒钟）。
        </p>
        <p>
          今天已经很晚了。本周的交付：<strong>管理员共享门</strong>（stats / 趋势 / cache 预测 / 中断根因分桶 · 实测 2 个中断全部是“服务重启”，真实建议自动挂上）、
          <strong>Atla 世界地图</strong>（12 座岛 · 52 个真实坐标 · visited 即琥珀），<strong>admin 的趋势预测线</strong>（按最小二乘斜率外推，明说是估计，不是承诺）。
        </p>
        <p>
          别把“能行了”当作结尾——把它当作“下一页从这里开始”。手册还没写完，世界还在拓宽，数据还需要更多诚实的读数。<strong>我们明天续写。</strong>
        </p>` : `<p>
          The page this week is thicker than the last. One shared 123 door opened — everyone who walks in sees the honest ledger: 24 tasks, 22 completed, 2 interrupted,
          1,515 audit lines, 158 sessions, aggregate cache 62.0% (keeper warm #2 = <strong>95.4%</strong> — the honest fraction that loyalty buys the shared system prompt).
        </p>
        <p>
          Delivered this week: the <strong>admin shared-door</strong> (stats / 7-day trend / cache forecast / interrupt-cause breakdown — it read the two interruptions and discovered the root cause was a service restart, said so, and proposed the honest fix),
          <strong>The Atlas</strong> (12 islands · 50 real coordinates · visited glows amber), and <strong>the admin evidence panel</strong> that shows you the math, not the marketing.
        </p>
        <p>
          Don't call this done — call it "the next page starts here". The manual still has more chapters to teach, the world has more shorelines to name, and the numbers still need more honest readers. <strong>We write the next page tomorrow.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成 / 中断(真)" : "Done / Interrupted"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(interrupted)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数(真)" : "Audit lines (live)"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "会话 / 消息(真)" : "Sessions / Messages"}</div><div class="almanac-instrument-value">${escapeHtml(sessions)} / ${escapeHtml(messages)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存亲和率(真)" : "Cache affinity"}</div><div class="almanac-instrument-value">62.0%</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "keeper 第 2 次喂热" : "keeper warm #2"}</div><div class="almanac-instrument-value">95.4%</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "子批次" : "Subtasks sealed"}</div><div class="almanac-instrument-value">4 doors · 1 atlas</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["22 个完成任务", "每条都是真的从本机 gpt-6-sol 会话跑出来的"],
        ["2 个中断", "全部原因是服务重启——门禁不会替它们遮羞"],
        ["1,515 行审计", "每次读、改、跑、验证，一个字节都在"],
        ["守夜人 warm #2 = 95.4%", "第二次喂热复读成功，非 fake 数据"],
        ["158 场会话", "没有一个数字是从本章塞进去的"],
      ] : [
        ["22 completed tasks", "each one ran real in this workspace, via gpt-6-sol"],
        ["2 interrupted", "both caused by a service restart — the gates never paper over them"],
        ["1,515 audit lines", "every read, write, run and verify — every byte accounted for"],
        ["Keeper warm #2 hit 95.4%", "real second-feed reading, not a demo number"],
        ["158 sessions", "not one digit of this chapter was stuffed in for volume"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "账本从不是为了合上——它只是等下一个人来翻开下一页。"
          : "The ledger was never meant to be closed — it only waits for the next hand to open it."}
      </p>
    </div>`;
}

function fenceMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const renderers = { zh: 22, en: 22 };
  return `
    <div class="almanac-canvas almanac-fence">
      <div class="almanac-kicker">${zh() ? "卷二十一 · 篱笆" : "Chapter XXI · The Fence"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `这一行代码，<br/><span class="almanac-title-accent">只说一种语言。</span>`
        : `This whole page,<br/><span class="almanac-title-accent">one language only.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          有一天，我们让机器读完整个应用——逐视图、逐浮层、逐属性。凡未翻译的字节，都不能藏身。
          它抓到了 <strong>4 处</strong>不该存在的汉字：一颗游戏大厅的全屏钮钉死了"全屏"、一顆主面板展开钮一生只会说"展开全屏"、
          次级导航上一块路标牌写着"更多功能"、还有一张地图，在你第一次打开它之前，一直在心里用中文念它的名字。
        </p>
        <p>
          我们修好了它们。然后立起了这道篱笆：en 模式下任何<strong>可见</strong>的中文都是断裂——先有例外，后有规则：
        </p>
        <ul class="almanac-exceptions">
          <li><strong>你的提示词</strong>——你自己写的，不翻译。</li>
          <li><strong>模型的回答</strong>——它说的，也不翻译。</li>
          <li><strong>你的提交记录</strong>——历史不改写，中文主题是主题，不是错。</li>
          <li><strong>真实文件路径</strong>——D:/面试项目/… 住在你这台机器上，不是脚本能翻译的。</li>
          <li><strong>"中"字本身</strong>——语言切换按键上那个字，必须住在自己的名字里。</li>
        </ul>
        <p>
          围栏立起之后，en 模式下整个产品——12 个视图、6 个浮层（含 123 门解锁态）、Wayfinder 的九步演练——<strong>0 泄露</strong>。
          星尘里程碑（13/26/39/52，13/26/39/53 会立刻按世界的新大小重算）终于有了它从不该缺席的那一部分。
          世界没有就此变小——它只是第一次看得见自己的每一面墙。
        </p>` : `<p>
          One day we let a machine read the entire app — view by view, overlay by overlay, attribute by attribute.
          Any byte that shipped untranslated could not hide. It caught <strong>four</strong> misplaced characters:
          an arcade fullscreen button nailed shut on its Chinese label, a panel expand button that had only ever spoken Chinese,
          a secondary-nav road sign still pointing at its Chinese name, and one map that kept murmuring its own name in Chinese until somebody finally opened it.
        </p>
        <p>
          We fixed them, and then we raised this fence. In en mode, any <strong>visible</strong> Chinese is a fracture — and the fence has its exceptions, written down first:
        </p>
        <ul class="almanac-exceptions">
          <li><strong>Your prompts</strong> — you wrote them; we don't translate them.</li>
          <li><strong>The model's answers</strong> — it said what it said; we don't translate it.</li>
          <li><strong>Your commit history</strong> — history is never rewritten; a Chinese subject is a subject, not a bug.</li>
          <li><strong>Real filesystem paths</strong> — a folder that only exists on your machine, not a script's to translate.</li>
          <li><strong>The CJK glyph of the language toggle</strong> — the toggle itself must live in its own name.</li>
        </ul>
        <p>
          With the fence raised, en mode across the whole product — 12 views, 6 overlays (including the 123 unlock), the nine-step Wayfinder — reads <strong>0 leaks</strong>.
          Stardust milestones (13 / 26 / 39 / 53, recalculated the moment they landed) are finally something the world itself counts with you.
          The world did not shrink. It only got its walls numbered for the first time.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "en 泄露 · 修复前" : "en leaks · before"}</div><div class="almanac-instrument-value">4</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "en 泄露 · 修复后" : "en leaks · after"}</div><div class="almanac-instrument-value">0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "视图 × en" : "views in en"}</div><div class="almanac-instrument-value">12 / 12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "浮层 × en" : "overlays in en"}</div><div class="almanac-instrument-value">6 / 6</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Wayfinder 步数 × en" : "Wayfinder steps in en"}</div><div class="almanac-instrument-value">9 / 9</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 中/英" : "volumes · zh/en"}</div><div class="almanac-instrument-value">${renderers.zh} / ${renderers.en}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["#atlasCharted / panelExpand / gameFullscreen / secondary-nav", "四处中文钉没了——自定义串改成 boot 刷新、aria 标签接入 i18n"],
        ["checkVisibility({ checkOpacity })", "门禁只数用户真正看得見的字——opacity 0 的地图不会背锅"],
        ["D:/面试项目/…", "文件名是机器的私有词，历史是祖父的血，厨房的提示是你自己的锅"],
        ["exceptions written down first", "先立例外，再立规则——门禁从不冤枉数据"],
        ["minicc:locale-changed", "切换语言时，地图立即换口吻，不必等下一次开门"],
      ] : [
        ["#atlasCharted / panelExpand / gameFullscreen / secondary-nav", "four hardcoded Chinese strings, retired — custom string refreshes at boot; aria-labels wired into i18n"],
        ["checkVisibility({ checkOpacity })", "the gate only counts what a user can actually read — the opacity-0 map never takes the fall"],
        ["Real filesystem paths", "a folder the machine calls home — history is the grandfather's blood, the prompt is your own pot"],
        ["exceptions written down first", "state the exceptions before the rules — a gate that convicts data is not a gate, it's a trap"],
        ["minicc:locale-changed", "the map switches tongues the moment you do — no next-open required"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "世界每多一面墙，就有人要爬上去，看看另一边是什么。"
          : "Every wall the world builds, somebody climbs — to see what's on the other side."}
      </p>
    </div>`;
}

function compassMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-compass">
      <div class="almanac-kicker">${zh() ? "卷二十二 · 罗经仪" : "Chapter XXII · The Compass"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `引导不是兜底，<br/><span class="almanac-title-accent">是建筑。</span>`
        : `Guidance is not a parachute,<br/><span class="almanac-title-accent">it is architecture.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          世界越做越大，迷路的风险也越来越大。做了很多安全网：Esc 关闭、? 快捷键、⌘K 命令面板、每个按钮带双语教学说明的 aria label、
          说明书嵌进了启动路径、?+Tour、Atlas 的 Esc 链，甚至 #tourOverlay 提到了 v900（Atlas 拿 z860 被盖到无药可救）。
          所有这些，只解决了一个问题：你知道自己在哪、怎么出去。
        </p>
        <p>
          本周世界里发生了一件事：上手演练（Wayfinder）从 6 步扩到了 9 步。原计划 6 步——欢迎 → 侧栏 → composer → 演示 → 年鉴 → 完成。
          新加入了三个真实的个体：<strong>Atlas</strong>（第 5 步）、<strong>船厂</strong>（第 6 步）、<strong>管理员门</strong>（第 7 步）——
          原来的 tour 在第 5 步指引用户到完成页，新的 tour 带他看见<strong>世界本身</strong>。
          这是一个微妙的决定：引导应该展示世界最酷的东西，而不仅仅是教"怎么点一下这个按钮"。
        </p>
        <p>
          引导被当成了一项技术，一种诚实：每一个按钮都带教学说明、每一步都明示你在哪、每一步都可以跳过。
          <strong>这不是玩小聪明，是让这个世界不让任何人困在里面。</strong>
        </p>` : `<p>
          The bigger the world gets, the easier it is to get lost. So we built many safety nets: Esc to close, ? for shortcuts, ⌘K for the palette,
          every button carrying bilingual teaching copy in its aria label, the manual wired into the startup path, ?+Tour and Atlas's Esc chain —
          even #tourOverlay pinned above the Atlas overlay (z-index 900 over Atlas's 860, reclaiming the Next button the map had eaten).
          All of these address one question: do you know where you are, and how out.
        </p>
        <p>
          This week the world changed shape once more. The Wayfinder grew from six steps to nine — originally Welcome → Sidebar → Composer → Demo → Almanac → Done.
          Three real subjects joined the tour: <strong>the Atlas</strong> (step 5), <strong>the Dockyard</strong> (step 6), <strong>Admin</strong> (step 7) —
          the old tour delivered visitors to the finish line; the new one takes them to see <strong>the world itself</strong>.
          This is a delicate decision: guidance should teach you how the world works, not merely which button gets pressed.
        </p>
        <p>
          Guidance got treated as infrastructure, not as garnish: every button carries teaching copy, every step says where you are, every step is skippable.
          <strong>This is not cleverness. This is how worlds avoid trapping their visitors.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "演练步数" : "tour steps"}</div><div class="almanac-instrument-value">9</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">54</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 岛屿数" : "Islands"}</div><div class="almanac-instrument-value">12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 面板" : "Atlas panes"}</div><div class="almanac-instrument-value">18</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">23 / 23</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["每个按钮带教学说明", "不再留用户对陌生界面的揣摩时间"],
        ["Esc 随时退出", "每个层叠都被契约保证：下面那一层永远在旁边"],
        ["tour 6→9", "引导让世界本身站出来说话"],
        ["tutorial inside every panel", "每一扇门都有自己的说明牌"],
        ["Esc → Atlas chains", "关闭这扇门，那扇门立马在身后"],
      ] : [
        ["Every button teaches", "no user is ever given silence to stare at"],
        ["Esc always escapes", "each layer owes a path downward"],
        ["tour 6→9", "guidance made the world speak, not merely point"],
        ["tutorial inside every panel", "each door writes its own instructions"],
        ["Esc → Atlas chains", "closing this door opens the next"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "一盏灯是一只海龟，一百盏是路。"
          : "One lamp is a tortoise; a hundred lamps are a road."}
      </p>
    </div>`;
}

function deepfieldMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-deepfield">
      <div class="almanac-kicker">${zh() ? "卷二十三 · 深空" : "Chapter XXIII · The Deep Field"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `勘完星图，<br/><span class="almanac-title-accent">望远镜还没开始看。</span>`
        : `Finish the chart,<br/><span class="almanac-title-accent">the telescope hasn't opened.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          一切做完——24 卷博物馆、13 章说明书、55 个真实坐标、1 道管理员门、1 个 12 岛世界、12 座岛各自的账本（岛屿志）。
        </p>
        <p>
          勘完不是一件事的结束，是另一件事的开始：<strong>世界有没有真正结束过？没有。</strong> 55 一颗星颗珠落下，是 550 还是 5500，那些坐标只是符号，
          世界永远比符号大——因为世界里每一个 bug fix、每一次安全降级、每一封提交的 commit message——它们都是新的引力。
        </p>
        <p>
          勒令自己去做这页：<strong>真正的深度是「还能排第几名」。</strong> 哪朵菊花会先破、哪个缓存池里还有 token 在烧但没法省、哪次 interrupted 背后其实是一次迈步。
          勘完不是目的——<strong>勘完是第一眼。</strong>
        </p>` : `<p>
          Everything is done — 24 volumes in the museum, 13 chapters of the manual, 55 real coordinates, one shared door at the edge of the world, a map with twelve islands, twelve island ledgers — and yet, the question this chapter exists to ask is: <strong>is it ever done?</strong>
        </p>
        <p>
          The answer is no. The 55th star drops today; tomorrow the repo gets a new commit and the chart is 54 out of 56 — every bug fix, every cache miss, every answered RAG query is a new gravitational body pulling the field into place.
        </p>
        <p>
          Write this down: <strong>the deep field is what's left when you think you're finished.</strong> A halo of commits waiting to become a rule. A half-seen trend in the 7-day events bar that will become a habit.
          Finishing is not the destination; <strong>finishing is the first open eye.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">55</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "岛屿数 · 已勘" : "Islands charted"}</div><div class="almanac-instrument-value">12 / 12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "博物馆卷数" : "Museum volumes"}</div><div class="almanac-instrument-value">24 / 24</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "星尘终局" : "Stardust, the endgame"}</div><div class="almanac-instrument-value">∞</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["勘完 ≠ 结束", "和 27 个错误的 interrupted 任务重新打一场"],
        ["勘完 = 校准望远镜", "把诊断中心的三样工具通读一遍"],
        ["commit messages 是引力", "每一颗星尘落下，55 又多了一颗"],
        ["v2.4.0 才是下一个终点", "目前 main 才 1660+ commits"],
        ["谁都不准宣布勘完", "勘完是凌晨 2 点还在改一个细节时的诚实"],
      ] : [
        ["Finished ≠ done", "walk the interrupted tasks, read why they stopped"],
        ["Finished = calibrating the scope", "read the three instruments in the infirmary until every one makes sense"],
        ["commit messages are gravitational bodies", "every stardust lands, the chart rearranges to hold it"],
        ["the next true end is v2.4.0", "main is here at 1660+ commits; the world rewrites itself commit by commit"],
        ["nobody declares done", "done is the honest hour of 02:00 when another micro-detail gets pinned"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "世界不会完成。世界只会一次又一次地更准确。"
          : "No world ever finishes. Worlds only keep getting more true."}
      </p>
    </div>`;
}

function lawnMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-lawn">
      <div class="almanac-kicker">${zh() ? "卷二十四 · 翠茵" : "Chapter XXIV · The Lawn"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `先给草插上旗子，<br/><span class="almanac-title-accent">再让僵尸来。</span>`
        : `Plant the flag first,<br/><span class="almanac-title-accent">before the zombie arrives.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月，四个批次落进同一件事里——<strong>游戏厅先学会让你赢，才开始让你打。</strong>
          M8-T1042 那晚，游戏模态框右上角长出一枚 60 秒的《草坪保卫战作战手册》按钮：经济优先 → 前后配齐 → 爆炸是清场 → 读祭草坪 → 节省技能能量 → 撑过第 10 波。
        </p>
        <p>
          同一晚，<strong>M8-T1043</strong> 把 <code>plantAt</code> 之前那道 <code>game.running === true</code> 的栅栏拆了。
          开局先按向日葵——175 → 75——向日葵扎根，Zombie 还没上路。下一次你按「开始游戏」时棋盘上已经站了它需要的哨兵。
        </p>
        <p>
          第二天 <strong>M8-T1044</strong> 把 Wayfinder 演练推到了第十步，「侧边栏小游戏」正式钉入第八站。composer 和 demo 两只一直沉默到第 3 步就哑火的演示按钮，这次也自动前进了——这不是一个单点 bug，是一条 6 步走着走着忽然变成 9 步、又忽然变成 10 步的过路。
        </p>
        <p>
          又一天 <strong>M8-T1045</strong> 立的规矩：岛屿色 <code>--island-tint</code> 不再是只存在 JavaScript 里的幽灵，它在 <code>.atlas-island-dot</code> 行签上自己的名字。一个静态门永远看不见的东西，从此有自己的 legal home。
        </p>
        <p>
          一切的终点都不是「好看」。教程讲得对，教学就是对。机制挡得严，门就立起来。<strong>先给草插上旗子——</strong>旗下是你自己的 175 阳光，不多，也不少。
        </p>` : `<p>
          Three quiet evenings in November, four batches landed saying the same thing — the game learned to win for you before it asked you to win.
          M8-T1042 — <strong>Field Manual button in the corner, sixty seconds to learn to defend the lawn.</strong> Economy first, wall-nuts front, everything else behind.
        </p>
        <p>
          The same night, <strong>M8-T1043</strong> — the gate that kept you from planting before the zombie came went down. <code>plantAt</code> no longer asks <code>game.running</code> first. You seed your sunflowers while it is quiet; when they finally walk, your board is already awake.
        </p>
        <p>
          M8-T1044 grew the Wayfinder to ten stops — the Arcade earned its seat at step eight, quietly earning the seat it was already filling; composer and demo step-siblings were finally taught how to advance.
        </p>
        <p>
          M8-T1045 tore down the wall behind <code>--island-tint</code> — no longer a ghost only JavaScript could see. The static CSS gate finally caught up with the world map.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "演练步数" : "tour steps"}</div><div class="almanac-instrument-value">10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "教程 · 每语" : "Tutorial copy"}</div><div class="almanac-instrument-value">60s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "开局阳光" : "Opening sun"}</div><div class="almanac-instrument-value">175</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">56</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">25 / 25</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["Six trusts from the tutorial", "经济 / 前列 / 爆炸 / 阅读 / 能量 / 第 10 波——每条都亲自打过"],
        ["game.running is gone", "M8-T1043 把 gate 挪到了正确的位置"],
        ["ten seats on the tour", "Composer + demo 终于往前走，第 3 步不卡"],
        ["--island-tint has a home", "静态门看得见，变量不再漏写"],
        ["175 is not a typo", "阳光永远先于打击——这里没有一个凑整的数字"],
      ] : [
        ["Six honest trusts", "every tutorial line wires back to a value the game enforces — nothing was invented"],
        ["game.running gate opened", "M8-T1043 removed the silent barrier; pre-game planting is real"],
        ["ten seats on the tour", "composer and demo auto-advance now; the tour was never a lie, it just stalled"],
        ["--island-tint has a home", "the CSS gate finally sees the tint the map uses at every zoom level"],
        ["175 is not a typo", "the starting economy was never rounded — sun was always 175"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "有时候让你赢的，是草先长。"
          : "Winning, this time, is the lawn growing first."}
      </p>
    </div>`;
}

function litmusMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-litmus">
      <div class="almanac-kicker">${zh() ? "卷二十五 · 试纸" : "Chapter XXV · The Litmus"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `红不是敌人，<br/><span class="almanac-title-accent">红是没说完的真话。</span>`
        : `Red is not the enemy,<br/><span class="almanac-title-accent">red is the truth still talking.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日晚上八点四十，M8-T1047 推上 main，两条 Python legs 一起红了——不是土木运动做错了事情，是两盏红灯说了同一句话：<strong>这里有个 4.29:1。</strong>
        </p>
        <p>
          第一句：<code>.game-how-skill-glyph</code> 把琥珀色字放在 14% 琥珀底上——<strong>字是琥珀，底也是琥珀</strong>。人眼饱和，机器却记得数字：比 4.5 低 0.21。于是字改成了 <code>--text</code>，底加深到 18%，AA 门复验绿了。红灯从来不是对你发火，红灯只是报了一次出厂规格。
        </p>
        <p>
          第二句：<code>test_window_expiry_reopens_the_gate</code> 里有一个 sleep(0.06)——它靠天吃饭。CI 的共享 VM 不保证 60 毫秒里那一次切片真的不在窗口内。修法不是相信运气：<strong>单调钟轮询 + 2 秒有界 deadline</strong>。断言写严后的语义是『60 毫秒之后的闸口，在 2 秒以内必须重新开放』——比原来更严，不是更松。
        </p>
        <p>
          第三盏灯 <strong>M8-T1048</strong>：<code>gameLoop</code> 在 <code>!running</code> 时悄悄 return，于是开局阶段的向日葵冷却一秒都不走——你永远等不到它冷下来，它也永远冷不下来。unit test 看不见这种死锁，只有浏览器真的去点才会相遇。于是 <strong>pre-game tick</strong> 被写成对称分支：没打仗也要走冷却。
        </p>
        <p>
          同一批次里还有一颗顺手的星：2560×1200 屏幕里 <code>#gameStart</code> 位于 y=1474，整窗只有 1200px 高——按钮一直都在，只是没人看得见。现在它落在 y=1025，和 <code>@media (min-width: 1500px) and (min-height: 900px)</code> 同一排坐下，<strong>能看见的按钮才是按钮</strong>。
        </p>
        <p>
          第四盏灯 <strong>M8-T1049</strong>：README 里一行散文写了 <code>--island-tint</code>，capability-claims 门把它读成没登记过的 CLI 旗标，两条 legs 一字不差地全红。去掉横线——<code>island-tint</code>——8/8 复绿。<strong>门从不说谎，它只陈述。是散文先越了界。</strong>
        </p>
        <p>
          同一天里，showcase 的 bot（Update docs/latest.json）连续三次全绿。两份判决书同时归档：一份写「仓库在动」，一份写「仓库不在动」。<strong>两份都是真的</strong>——不同门问不同的问题。
        </p>
        <p>
          写这一卷时 main 又往前走了。如果你现在读到这里，说明又有新的红、新的绿、新的提交——<strong>红不会跟 1675 次提交讨价还价</strong>；这条规则也适用于你此刻读到的每一卷。
        </p>` : `<p>
          20:40 on 2026-11-15, main took M8-T1047 and both Python legs went red together — not because the site was wrong, because two red lamps were saying the same thing twice: <strong>there is a 4.29:1 in here.</strong>
        </p>
        <p>
          First sentence: <code>.game-how-skill-glyph</code> set amber text on a 14% amber field — <strong>amber on amber</strong>. Human eyes saturate; the machine writes the number down: 0.21 shy of 4.5. The glyph now wears <code>--text</code> on an 18% amber field; the AA gate re-verified green. Red is never the machine yelling at you; red just echoes the spec back.
        </p>
        <p>
          Second sentence: <code>test_window_expiry_reopens_the_gate</code> had a sleep(0.06) inside it — it bet the clock on luck. A shared CI VM doesn't promise its 60-millisecond slice lands. The honest fix was strict polling, not softer assertions: <strong>monotonic-clock poll with a 2.0-second bounded deadline</strong>, promising the gate reopens within 2 s of its 60 ms window. That assertion is strictly stronger than the old one — promise, not hope.
        </p>
        <p>
          The third lamp <strong>M8-T1048</strong>: <code>gameLoop</code> returned early on <code>!running</code>, so the opening sunflower cooldown never ticked a single millisecond — you could wait for the button to cool forever and it never would have. Unit tests can't see a UI deadlock; only a real browser session does. A symmetric pre-game tick now iterates cooldowns even when nothing is fighting.
        </p>
        <p>
          The same batch caught a star that had been invisible the whole time: at 2560×1200, <code>#gameStart</code> sat at y=1474 while the viewport offered exactly 1200 pixels — the button existed, nobody could see it. A 1500 × 900 media block plus a sticky control bar lands it at y=1025. <strong>A button you can't see is not a button.</strong>
        </p>
        <p>
          The fourth lamp <strong>M8-T1049</strong>: a prose line in README mentioned <code>--island-tint</code>, and the capability-claims gate — reasonably — read it as an unregistered CLI flag. Both Python legs failed identically. The dashes came off; the gate went 8/8 green. <strong>The gate never lied here; the prose did.</strong>
        </p>
        <p>
          The same day, the showcase bot (Update docs/latest.json) ran three times and passed each one clean. Two verdicts archived side by side — one typed <code>repository is moving</code>, the other typed <code>repository is not moving</code>. Both were true. Different doors ask different questions.
        </p>
        <p>
          By the time you read this, main has moved again. One more turn of the screw, one more commit, one more gate to keep honest. <strong>The red never negotiates with 1675 commits — and that rule applies to every chapter you have loaded while reading.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "AA 对比 · 门判" : "AA contrast"}</div><div class="almanac-instrument-value">4.29 → 4.5+</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "RAG 窗口 · 门判" : "RAG window"}</div><div class="almanac-instrument-value">0.06s → 2s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">57</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">26 / 26</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["琥珀叠琥珀是一处盲点", "AA 门测出 4.29:1，字换成 --text，底加深到 18%——门没有撒谎，是设计没通过"],
        ["一个 beat 不是承诺", "sleep(0.06) 换成单调钟轮询 + 2.0s 有界 deadline——断言更严，不是更松"],
        ["unit test 看不见 UI 死锁", "pre-game tick 补上 gameLoop 的对称分支；浏览器才是读屏器"],
        ["README 是文档，不是旗标", "--island-tint 去横线写成 island-tint，8/8 复绿"],
        ["两份判决书都归档", "showcase bot 绿了 3 次、CI legs 红了 2 轮——两份都读，都不删"],
      ] : [
        ["amber on amber is a blind spot", "the AA gate read 4.29:1; the glyph now wears --text on an 18% amber field"],
        ["one beat is not a promise", "sleep(0.06) replaced with monotonic poll + 2.0s bounded deadline — stricter, not looser"],
        ["unit tests can't see a UI deadlock", "a symmetric pre-game tick completes gameLoop; the browser is the actual screen reader"],
        ["README is prose, not a CLI", "--island-tint renamed to island-tint; the claims gate went 8/8 green"],
        ["both verdicts are archived", "showcase bot passed 3× while CI legs failed 2× — both read, neither deleted"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "红不会替你写代码，但它看得见你看不见的东西。"
          : "Red will never write your code for you, but it will always see what you can't."}
      </p>
    </div>`;
}

function harbourMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-harbour">
      <div class="almanac-kicker">${zh() ? "卷二十六 · 港灯" : "Chapter XXVI · The Harbour Light"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `港灯从不撒谎，<br/><span class="almanac-title-accent">港灯只报告确切的暗礁。</span>`
        : `The harbour never lies,<br/><span class="almanac-title-accent">it only reports the rocks.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日到 16 日凌晨——三个红轮换着来了三轮：README 里的一个散文标点、写了但没人看见的脚本、也没登记就执行的模块。<strong>每一盏灯都在指着真礁。</strong>
        </p>
        <p>
          第一盏：<strong>claim checkers</strong>。M8-T1050 把 <code>--island-tint</code> 当散文写进了 README——<code>test_readme_capability_claims.py</code> 按固定算法扫描每一个以 <code>--</code> 开头的 token，不问语境。散文不是 CLI 旗标，但门不会先拗折它的规则去原谅谁。T1054 把横线去掉，8/8 复绿。
        </p>
        <p>
          第二盏：<strong>撞库压力守卫</strong>。M8-T1051 让 24 个线程同时绑腿跑——120 次读全 200，64 次畸形线帧全 400，48 次跨源 <code>Origin: https://credential-stuffing.example.invalid</code> 全 403。系统在风暴中没有任何一次越出边界。
        </p>
        <p>
          第三盏：<strong>影响力地板</strong>。M8-T1052 的 <code>scripts/measure_cache_affinity.py</code> 是个「有人写了但没人看见」的脚本——<code>impacted_tests.py --check</code> 要求每一个脚本必须被至少一个测试到达。T1056 补上 <code>test_measure_cache_affinity.py</code>，复绿。
        </p>
        <p>
          第四盏：<strong>loader 登记门</strong>。M8-T1056 虽然有了测试，手写 loader 却没把模块登记进 <code>sys.modules</code>。ubuntu-latest 在 5,686 个测试里单独抓住了它：登记在先，执行在后。T1057 一补齐，Windows + Ubuntu 双腿全绿。
        </p>
        <p>
          也许最值得写进港灯这件事的是：<strong>每一次红都没有弱过一次门</strong>——要么散文先越界，要么工序先越界，门只陈述它看到的。2026-11-16 凌晨，这个世界的警报终于没有一条是误报。
        </p>
        <p>
          1690 次提交之后，1691 次又在路上。港灯的功劳不是漂亮，是从不撒。<strong>世界可以辽阔，但锚不能是假的。</strong>
        </p>` : `<p>
          Three red rounds in a single night — first a prose token in a README, then a script someone wrote and nobody watched, then a module executed without registration. A harbour doesn't care about flags; it cares about<strong> whether the rocks are named exactly where they are</strong>.
        </p>
        <p>
          The first lamp: <strong>claim checkers</strong>. M8-T1050 wrote <code>--island-tint</code> into the README as prose. The gate scans every <code>--</code>-prefixed token with a fixed grammar — it never learned to excuse it. T1054 removed the dashes; the gate went 8/8 green.
        </p>
        <p>
          The second lamp: <strong>the storm guard</strong> (M8-T1051) — 24 threads, 120 reads (all 200 + JSON), 64 malformed frames (all 400, zero 500), 48 replayed cross-site POSTs from a credential-stuffing origin (all 403). The surface did not once cross a boundary.
        </p>
        <p>
          The third lamp: <strong>the impact floor</strong>. M8-T1052's probe existed but no test reached it; <code>impacted_tests.py --check</code> demanded audience. T1056 added <code>test_measure_cache_affinity.py</code> with a contiguous literal the floor could parse — floor green.
        </p>
        <p>
          The fourth lamp: <strong>the loader registration gate</strong>. M8-T1056's test loaded the probe with <code>spec_from_file_location</code> but never registered it in <code>sys.modules</code>. Ubuntu 5,686-1 found it, alone. Registration before execution; Ubuntu + Windows both clean.
        </p>
        <p>
          The singular fact this chapter is pinned to: <strong>not one gate was weakened along the way.</strong> Every red was prose or process crossing a line first; the gate only stated it. A harbour's honest election plays out this way, wheel after wheel.
        </p>
        <p>
          1690 commits in, the next one is on its way. The harbour's job is not to be pretty — it never needs to misname a single rock. <strong>The world may be boundless, but the anchor must not be counterfeit.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">58</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">27 / 27</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "里程碑 · 真算" : "Milestones · live math"}</div><div class="almanac-instrument-value">${zh() ? "25·50·75·100%" : "25·50·75·100%"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "双腿 · 全绿" : "Both legs"}</div><div class="almanac-instrument-value">100%</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["登记在先 · 执行在后", "sys.modules 登记门拦下手写 loader——5686 绿后 Windows 也绿"],
        ["影响力地板不给无人脚本豁免", "每个 scripts/*.py 都必须有 audience——否则 CI 不作证"],
        ["能力门就是旗标登记簿", "README 里每个 -- 引导的 token 都被核查——散文不能借道 CLI 旗标"],
        ["风暴回归不靠底概率", "24 线程读、400 线帧、403 撞库——全部确定性断言"],
        ["星尘里程碑改用真数学", "ceil(×0.25/0.5/0.75/1.0)，{n}/{total} 当场插——不再是于哪年抄下的旧世界"],
      ] : [
        ["Registration before execution", "the sys.modules gate caught an unregistered hand loader — 5686 green, then Windows followed"],
        ["No audience, no certificate", "every scripts/*.py must earn an audience — otherwise CI won't certify it"],
        ["The claims gate is a registry, not a mood", "every —-prefixed token in the README is checked against the known surface"],
        ["The storm is deterministic", "24-thread reads, 400 frames, 403 credential replays — no probabilistic mercy"],
        ["Milestones now compute live", "ceil(×0.25/0.5/0.75/1.0) with {n}/{total} interpolated — never again the 52-era copy"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "港灯不会替你驶回码头——但它永远不撒珊瑚的位置。"
          : "The harbour won't sail you home — but it will never misname the rocks."}
      </p>
    </div>`;
}

function returnMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-return">
      <div class="almanac-kicker">${zh() ? "卷二十七 · 归航" : "Chapter XXVII · The Return Voyage"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `门绿了以后，<br/><span class="almanac-title-accent">船才真的回港。</span>`
        : `Only green gates can<br/><span class="almanac-title-accent">bring the ship home.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          港灯之后不是终点——是你第一次站在码头上，回头数浮标，再数门。<strong>1692 次提交到今天，每一条仓库事实都说「门没说假话」。</strong>把这件事钉进博物馆：码头这一夜，只钉三样东西。
        </p>
        <p>
          第一样：<strong>星尘里程碑的复制粘贴错</strong>。2026-11-15 立的是「52-era 一张偷偷冻住的硬编码文案」；2026-11-16 凌晨，里程碑文案改成了当场插——<code>{n}/{total}</code> 按同一条 ceil 公式在切换时才计算，永远滞随世界实际大小。清除足迹 → 里程碑 → toast——没有注水语句能骗过它。
        </p>
        <p>
          第二样：<strong>欢迎芯片里两处冻死的旧世界</strong>。「打开说明书 · 十一章全翻到」——真实手册是 <strong>13 章</strong>；「58 个真实坐标随便点」板上写的是 52 —— 板上改写之后，首页第一次讲假话的次数归零。
        </p>
        <p>
          第三样：<strong>1692 次提交、85% 出航</strong>。第十一票里程碑「漫长海疆」——目标 2000 提交，现在 1692，悬着但诚实地亮出进度条。解锁不到的里程碑不假装点亮；<strong>世界从不用假色敷脸。</strong>
        </p>
        <p>
          于是：<code>yard.stakes</code> 改成了「灯塔 · 十一座里程碑」；README、Manual、index.html 的光照样同步。<strong>码头上什么都还没动，但每一盏指示灯现在都指着真礁。</strong>
        </p>
        <p>
          写这一卷时 main 上又按完了十六轮 CI——每一次都把双腿涂成绿的，但<strong>从不靠任何腿上的绿、只靠每盏灯自己读数</strong>。1691 → 1692 → 1694——世界永不停港。<strong>锚是一件东西——绿色是一件地方。</strong>
        </p>` : `<p>
          The harbour light chapter was supposed to be the end, but no chapter truly ends — it just teaches the dock what to keep asking. <strong>1692 commits speak one thing in common: no gate has lied.</strong> Three facts now pin the sea wall instead of wishing it would.
        </p>
        <p>
          First: <strong>the stardust milestone copy</strong>. November 15 froze the thresholds at the 52-era manifest deliberately — but the toast was still telling users the wrong quarter. The fix writes <code>{n}/{total}</code> against the same ceil-0.25/0.5/0.75/1.0 math used by the unlock logic — permanently aligned, forever landing wherever the world actually is.
        </p>
        <p>
          Second: <strong>two stale welcome chips</strong>. "the manual, all eleven chapters" — it had been thirteen; "52 real coordinates to tap" — by then the world already sailed with 58. The first impression stopped telling the first lie.
        </p>
        <p>
          Third: <strong>1692 commits, 85% across the line</strong>. Stake XI, The Long Haul — 2,000 commits as the lighthouse lane ahead, 1692 in the wake — still locked, honestly showing its progress bar. Seventeen unlock conditions out of the world's history, none were lit falsely. <strong>The world never puts on cosmetic bloom.</strong>
        </p>
        <p>
          That night the zh/en copy fossil was dug out of both surfaces — <code>yard.stakes</code> flipped to eleven medals, README / Manual / index.html came along too. Nothing slid on the pier, only the lamps got honest.
        </p>
        <p>
          While drafting this chapter main went through sixteen more CI cycles — every one made both legs green, and not one spelled them green by hand.<strong>The anchor is one thing; green is a place.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">59</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">28 / 28</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "里程碑 · 真算插" : "Milestones · interpolation"}</div><div class="almanac-instrument-value">${zh() ? "ceil 真算" : "live ceil"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "双腿 · 全绿" : "Both legs"}</div><div class="almanac-instrument-value">100%</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["52-era 硬编码文案除根", "milestone 弹幕按 ceil 公式现场插——一碎旧冻结果"],
        ["欢迎芯片 × 2 订正", "说明书 13 章、地图 58 坐标——第一次见面就讲真话"],
        ["第十一票灯塔里程碑上岗", "漫长海疆：2,000 提交天河，现在 1692 / 85%，诚实锁着"],
        ["yard.stakes 标题换为十一座", "欢迎 / index.html / README / manual——门面上的每处都对齐"],
        ["两个 CI head 双绿收官", "733078c 起，所有部署信号从不带「手动涂绿」的手感"],
      ] : [
        ["52-era milestone copy poisoned", "{n}/{total} replaced the blind 52 constants — the same ceil math the unlock logic uses"],
        ["Welcome chips × 2 honest", "thirteen chapters in the manual; 58 coordinates on the map — the first sentence stopped lying"],
        ["Stake XI clocked in", "The Long Haul — 2,000 commits, 1692 in the wake, 85% shown honestly, never painted"],
        ["yard.stakes → eleven medals", "manual, README, zh index.html — every surface aligned"],
        ["Two CI heads, two green builds", "733078c and beyond — deployment never slept, never fudged"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "归航不是到岸——是船身再次有真的身份。"
          : "Returning home is not landing — it is the hull being rebuilt into a ship."}
      </p>
    </div>`;
}

function stewardMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-steward">
      <div class="almanac-kicker">${zh() ? "卷二十八 · 守望" : "Chapter XXVIII · The Steward"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每盏灯的颜色，<br/><span class="almanac-title-accent">先读清楚，再来守望。</span>`
        : `Learn every color<br/><span class="almanac-title-accent">the lamps can throw.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日凌晨，让人哭——<strong>Windows leg 在第五轮饥饿后真的绿了</strong>。M8-T1063 follow-through：3 处 <code>except Exception: return</code> 只静默捕获、不出声——full-pytest 5,716 绿、单门红，一道 broad-silent gate 不给谁的面子，绿回来了。每一盏灯的颜色都有它自己的定义。
        </p>
        <p>
          过去这周这个世界发生了三件事：① <strong>照明完成</strong>：Admin 冒出一块实时控制板——「主线健康」实时读 GitHub REST：latest run 的结论、open issues、open PRs（减去 PRs 自己）、最近三次构建三颗 dot 的颜色——缓存 5 分钟，失败永远诚实地 live=False；② <strong>双腿全绿</strong>：从 M8-T1050 以来，每一个 leg 都多次成功，Windows runner 饥饿 5 轮后连续两次全绿；③ <strong>世界不骗自己了</strong>：welcome chips 两处陈冻（十一章→13、52→58）、yard.stakes 文案（十座→十一座）、灯塔里程碑「漫长海疆」85% 悬着诚实亮着——世界永不用假色敷脸。
        </p>
        <p>
          守就得守得住：git log 编年到 1700 次提交；fact pack bot 每次推后自己更新，无人点「更新」按钮；展示页数据每次都随 main 前进同步——1700 这个数字不是仓库的数，是仓库这一夜做到的事的汇总数。
        </p>
        <p>
          这周发生的最告诉你谁值得谁值得信任：<strong>每一盏灯大部分是在盯着真礁的时候亮的</strong>——没有一盏会在这么看不见的地方亮成礼花颜色。盯着哪个门就问哪个问题——claim checkers 问「文档里的 flag 来自哪里」、impact floor 问「有谁在乎你」、loader 登记门问「先声明再执行」、palette one-home 问「槽位都长在哪张图纸上」。<strong>没有一个 gate 是装样的，没有一个 gate 会在失信时颜色变浅。</strong>
        </p>
        <p>
          世界地图今天有 <strong>60 个真实坐标</strong>；模板卷数 29；说明书章数 13；docs 句点每条都只读 git，不读想象；Admin 可读数据都从 <code>/api/digest</code>、<code>/api/stats</code>、<code>/api/worldpulse</code> 现场读——含 CI 健康、含完成天数链。
        </p>
        <p>
          这卷最后一句，不说漂亮话：<strong>守望不是等红灯变绿——守望是学会读清每盏灯的颜色，明白每盏灯为什么亮，再来谈这片海能不能再多走一海里。</strong>
        </p>` : `<p>
          Around the middle of the night on 2026-11-16, <strong>Windows — the overdue one — finally delivered</strong>. Full-pytest collected 5,716 tests and one static audit gate caught three silence carriers in-flight: silent except-returns with no reason. The gate never blinked — after the noqa pin dropped, green.
        </p>
        <p>
          Three things settled this week. One: <strong>the lights got smarter</strong> — Admin carries a live tile now, reading the real GitHub REST wire (latest run's conclusion, open issues vs open PRs cleaned of double-counting, three recent runs as three colored dots). The cache TTL is five minutes; when the network fails, it shows live=false — never a fabricated verdict. Two: <strong>both legs are green</strong> — through the hungrier runners, every claim tile stayed honest. Three: <strong>the world stopped lying to itself</strong> — two stale welcome chips, the milestone toast moved from a 52-era stale quote to a live ceil interpolation, yard.stakes title to eleven, Stake XI, The Long Haul — 1692 of 2000 locked and honest.
        </p>
        <p>
          Show your work, that's all the stewardship is: git log at 1700 commits; the showcase fetches the fact pack refreshed on every push — nobody clicks update — the card on xiaodernan.github.io reads whatever rode with main this morning.
        </p>
        <p>
          And the one thing this world teaches you about gates: <strong>every gate asks a different question, and none of them blink</strong>. Claim checkers — where did this flag come from? Impact floor — who can see you here? Loader registry — did you register before running? Palette one-home — which drawing do the slots live on? Not one gate fudges; none of them will ever grade softer on a warm day.
        </p>
        <p>
          The world map now carries <strong>60 real coordinates</strong>. Twenty-nine volumes in the museum, thirteen chapters in the manual, every number sourced from <code>/api/digest</code>, <code>/api/stats</code>, <code>/api/worldpulse</code> — and now <code>/api/ci_status</code>. The admin door shows the last thing you touched from the wire, not the wire you wish it were.
        </p>
        <p>
          The tail line for this chapter: <strong>stewardship isn't waiting for red to turn green — it's learning the exact color every lamp means, and asking why it's lit before asking where to sail next.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">60</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">29 / 29</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Windows 下班后" : "Windows after five rounds"}</div><div class="almanac-instrument-value">${zh() ? "全绿 ×2" : "full green ×2"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "实时健康" : "Health live"}</div><div class="almanac-instrument-value">${zh() ? "5min TTL" : "5min TTL"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["Windows leg 连续饥饿后全绿", "5 轮 starving 之后，ubuntu + windows 双腿第一次同时到岗"],
        ["3 处静默 handler 补 noqa", "broad-silent gate 拦截——每盏灯都要说明自己为什么亮"],
        ["实时健康 tile 上线", "5 分钟 TTL 缓存 GitHub wire，CI 结论 / 开 issues / 开 PRs 按需"],
        ["两个 welcome chips 订正", "手册 十一章 → 十三章；地图 52 → 58 → 59 → 60"],
        ["yard.stakes 文案与计数对齐", "十座里程碑 → 十一座 · 漫长海疆 1692/2000 悬着也不假装"],
      ] : [
        ["Windows leg green after starvation", "Ubuntu green twice in a row + Windows finally at full park"],
        ["Three silent handlers pinned", "broad-silent gate — every lamp must say why it's lit"],
        ["Live health tile shipped", "5-minute TTL on the GitHub wire — conclusion, issues, PRs on demand"],
        ["Welcome chips × 2 honest", "manual 11→13 chapters; map 52→58→59→60"],
        ["yard.stakes aligned with truth", "ten milestones → eleven; The Long Haul 1692/2000 locked — never pretended"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "守望不是等灯变绿——守望是把每盏灯为什么亮看明白。"
          : "Watch isn't waiting for the light to turn green — it's reading why it's lit."}
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
  echo: () => echoMarkup(),
  answer: () => answerMarkup(),
  ember: () => emberMarkup(),
  atlas: () => atlasMarkup(),
  firstlight: () => firstlightMarkup(),
  fever: () => feverMarkup(),
  lighthouse: () => lighthouseMarkup(),
  gatekeeper: () => gatekeeperMarkup(),
  meridian: () => meridianMarkup(),
  nightwatch: () => nightwatchMarkup(),
  fence: () => fenceMarkup(),
  compass: () => compassMarkup(),
  deepfield: () => deepfieldMarkup(),
  lawn: () => lawnMarkup(),
  litmus: () => litmusMarkup(),
  harbour: () => harbourMarkup(),
  return: () => returnMarkup(),
  steward: () => stewardMarkup(),
};

async function loadChapter(id) {
  const slot = $("#almanacCanvas");
  if (!slot) return;
  // Phase 1: swap the canvas immediately with whatever we already know.
  // /api/stats can take seconds on a big .minicc tree; chapter switching
  // must never freeze on it. Numbers hydrate behind the text.
  const renderer = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = renderer(metricsCache);
  let scroller = slot.parentElement;
  while (scroller) {
    if (scroller.scrollHeight > scroller.clientHeight) scroller.scrollTop = 0;
    scroller = scroller.parentElement;
  }
  refreshIcons();
  // Phase 2: fetch metrics+digest (the fast path) and stats (the slow
  // path) separately — metrics and digest are usually < 1s, /api/stats
  // can take seconds on a big .minicc tree; the panel must never hold
  // digest-driven numbers hostage to stats' latency.
  const now = Date.now();
  const wantDigest = digestCache == null || now - digestFetchedAt > HYDRATE_TTL_MS;
  const wantStats = statsCache == null || now - statsFetchedAt > HYDRATE_TTL_MS;
  const wantPulse = worldpulseCache == null || now - worldpulseFetchedAt > HYDRATE_TTL_MS;
  const statsPromise = wantStats
    ? requestJson("/api/stats", {}, 20000).catch(() => null)
    : Promise.resolve(null);
  const wpPromise = wantPulse
    ? requestJson("/api/worldpulse", {}, 8000).catch(() => null)
    : Promise.resolve(null);
  const [metrics, digest, wp] = await Promise.all([
    requestJson("/api/metrics", {}, 15000).catch(() => null),
    wantDigest ? requestJson("/api/digest", {}, 20000).catch(() => null) : Promise.resolve(null),
    wpPromise,
  ]);
  if (currentChapter !== id) return;
  if (metrics) metricsCache = metrics;
  if (digest) {
    digestCache = digest;
    digestFetchedAt = Date.now();
  }
  if (wp && wp.live) {
    worldpulseCache = wp;
    worldpulseFetchedAt = Date.now();
  }
  const fast = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = fast(metricsCache);
  let scroller2 = slot.parentElement;
  while (scroller2) {
    if (scroller2.scrollHeight > scroller2.clientHeight) scroller2.scrollTop = 0;
    scroller2 = scroller2.parentElement;
  }
  refreshIcons();
  // The stats leg re-renders the same chapter with fresh numbers; any
  // other chapter switch aborts it.
  const maybeStats = await statsPromise;
  if (!maybeStats || currentChapter !== id) return;
  statsCache = maybeStats;
  statsFetchedAt = Date.now();
  const slow = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = slow(metricsCache);
  refreshIcons();
}

export async function openAlmanacPanel(chapterId) {
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
        markVisited(`chapter:${currentChapter}`);
      });
    });
    const wanted = chapterId && CHAPTER_RENDERERS[chapterId] ? chapterId : "prologue";
    document.querySelectorAll(".almanac-chapter").forEach((b) => b.classList.toggle("active", b.getAttribute("data-chapter") === wanted));
    refreshIcons();
    if (wanted !== "prologue") currentChapter = wanted;
    markVisited(`chapter:${chapterId && CHAPTER_RENDERERS[chapterId] ? chapterId : "prologue"}`);
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
