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

function prologueMarkup() {
  return `
    <div class="almanac-canvas almanac-prologue">
      <div class="almanac-kicker">序章 · Prologue — The Letter</div>
      <h1 class="almanac-title">我希望<br/>有人为我
        <span class="almanac-title-accent">把世界读一遍。</span>
      </h1>
      <div class="almanac-body">
        <p class="almanac-lede">
          2026 年春天，这个项目开始于一个问题：
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
          这是给你看的，也是给未来的我自己看的。
        </p>
      </div>
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
        <div class="almanac-step"><span class="almanac-step-index">02</span><div><strong>计划</strong><p>模型在 zen plan / verify 循环里切分问题。每一步都得到一份证据或一种失败。</p></div></div>
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

const CHAPTER_RENDERERS = {
  prologue: () => prologueMarkup(),
  spark: () => sparkMarkup(),
  depth: (metrics) => depthMarkup(metrics),
  sentry: (metrics) => sentryMarkup(metrics),
  bloom: () => bloomMarkup(),
  hand: () => handMarkup(),
};

async function loadChapter(id) {
  const slot = $("#almanacCanvas");
  if (!slot) return;
  let metrics = null;
  try {
    metrics = await requestJson("/api/metrics");
  } catch {
    metrics = null;
  }
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
        <div class="almanac-canvas-shell"><div class="almanac-canvas" id="almanacCanvas">${prologueMarkup()}</div></div>
      </div>
    `, { wide: true });
    document.querySelectorAll(".almanac-chapter").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".almanac-chapter").forEach((b) => b.classList.toggle("active", b === button));
        loadChapter(button.getAttribute("data-chapter") || "prologue");
      });
    });
    document.querySelector('.almanac-chapter[data-chapter="prologue"]')?.classList.add("active");
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(t("almanac.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
