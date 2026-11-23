/* ============================================================
   Ask the Repo - RAG over the repository's own docs.

   The server side (minicc/rag.py, /api/rag/query) retrieves the
   top-k BM25 chunks from this very repo's docs (including CONTRIBUTING.md) and README
   and asks the configured chat model to answer only from those
   passages. This panel renders the answer, the sources it leaned
   on, and the exact token usage the gateway reports. The api_key
   never enters the prompt and is never rendered here. If the model
   is unreachable, the server returns an honest error string; we
   show it instead of pretending.
   ============================================================ */

import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel } from "../chat/stream.js";

const zh = () => state.locale === "zh";

function usageLine(usage) {
  if (!usage) return zh() ? "用量未上报（chat/completions 不回传 cached_tokens，这里不伪造）。" : "Usage not reported (chat/completions never carries cached_tokens; we do not invent one).";
  const parts = zh()
    ? [`提示 ${usage.prompt_tokens}`, `补全 ${usage.completion_tokens}`, `合计 ${usage.total_tokens} tokens`]
    : [`prompt ${usage.prompt_tokens}`, `completion ${usage.completion_tokens}`, `total ${usage.total_tokens} tokens`];
  const hit = Number(usage.prompt_cache_hit_tokens);
  if (Number.isFinite(hit) && hit >= 0) {
    const pct = usage.prompt_tokens > 0 ? Math.round((hit / usage.prompt_tokens) * 100) : 0;
    parts.push(zh() ? `缓存命中 ${hit}（${pct}%）` : `cache hit ${hit} (${pct}%)`);
  } else {
    parts.push(zh() ? "缓存命中未上报" : "cache hit unreported");
  }
  return parts.join(" · ");
}

function sourceRow(index, source) {
  const score = typeof source.score === "number" ? source.score : 0;
  const chunk = typeof source.chunk === "string" ? source.chunk : "";
  // M8-T1316: large-context chunks carry real line anchors (Lstart-Lend).
  const anchor = Number.isInteger(source.start_line)
    ? ` : L${source.start_line}–L${source.end_line ?? source.start_line}` : "";
  return `<details class="askdocs-source">
    <summary class="askdocs-source-summary"><span class="askdocs-source-index">${index + 1}</span><span class="askdocs-source-file">${escapeHtml(source.source ?? "?")}${escapeHtml(anchor)}</span><span class="askdocs-source-score">${escapeHtml(score.toFixed(2))}</span></summary>
    <pre class="askdocs-source-chunk">${escapeHtml(chunk)}</pre>
  </details>`;
}

function contextEvidence(context, sources) {
  if (!context) return "";
  const rows = [
    [t("askdocs.contextStat"), `${context.budget_tokens}`],
    [t("askdocs.contextPacked"), `${context.estimated_tokens} tokens`],
    [t("askdocs.contextChunks"), `${sources.length} / ${context.candidates}`],
  ];
  if (Number.isInteger(context.fanout)) {
    rows.push([t("askdocs.contextFanout"), `${context.fanout} / ${context.candidates}`]);
  }
  rows.push([t("askdocs.contextFp"), String(context.prefix_fingerprint || "—")]);
  const cost = context.cost_estimate;
  const costText = cost && Number.isFinite(cost.usd)
    ? `$${Number(cost.usd).toFixed(4)}`
    : t("askdocs.costUnpriced");
  rows.push([t("askdocs.contextCost"), costText]);
  const deep = context.budget_tokens >= 20000;
  return `<details class="askdocs-context-evidence">
    <summary>${icon("layers-3")}<span>${escapeHtml(t("askdocs.contextEvidence"))}</span></summary>
    <div class="askdocs-context-grid">${rows.map(([k, v]) =>
      `<div><span>${escapeHtml(k)}</span><b>${escapeHtml(v)}</b></div>`).join("")}</div>
    <p class="askdocs-context-hint">${escapeHtml(t("askdocs.costBasis"))}</p>
    ${deep ? `<p class="askdocs-context-warning">${icon("alert-triangle")}<span>${escapeHtml(t("askdocs.deepWarning"))}</span></p>` : ""}
    <p class="askdocs-context-hint">${escapeHtml(t("askdocs.deepHint"))}</p>
  </details>`;
}

export async function openAskDocsPanel() {
  const isZh = zh();

  openPanel(t("askdocs.title"), `
    <div class="askdocs-shell">
      <div class="askdocs-kicker">${escapeHtml(isZh ? "问仓库 · RAG 真跑" : "Ask the repo · RAG in flight")}</div>
      <h1 class="askdocs-title">${isZh
        ? "问项目<br/><span class=\"askdocs-accent\">自己的文档。</span>"
        : "Ask the project<br/><span class=\"askdocs-accent\">its own docs.</span>"}</h1>
      <p class="askdocs-sidenote">${escapeHtml(isZh
        ? "BM25 从本仓库 docs/（含 CONTRIBUTING.md）与 README.md 取 top-k 段落，再交给你配置好的模型，只依据这些段落作答。api_key 不进 prompt、不被回显；模型不可达时，这里显示真实错误，而不是编造答案。"
        : "BM25 retrieves top-k passages from this repo's docs (including CONTRIBUTING.md) and README.md, then asks your configured model to answer only from them. The api_key never enters the prompt nor is echoed back; when the model is unreachable, the real error is shown instead of a fabricated answer.")}</p>
      <form class="askdocs-form" id="askdocsForm">
        <label class="askdocs-label" for="askdocsQuestion">${escapeHtml(isZh ? "你的问题" : "Your question")}</label>
        <textarea class="askdocs-question" id="askdocsQuestion" rows="2" required
          placeholder="${escapeHtml(isZh ? "例如：为什么缓存命中率看起来很低？怎么跑压力测试？" : "e.g. Why does the cache hit rate look low? How do I run the load test?")}"></textarea>
        <div class="askdocs-controls">
          <label class="askdocs-kselect-wrap" for="askdocsK">${escapeHtml(isZh ? "引用来源数" : "Sources (k)")}
            <select class="askdocs-kselect" id="askdocsK">
              <option value="2">2</option>
              <option value="4" selected>4</option>
              <option value="6">6</option>
              <option value="8">8</option>
            </select>
          </label>
          <label class="askdocs-kselect-wrap" for="askdocsDepth">${escapeHtml(t("askdocs.depth"))}
            <select class="askdocs-kselect" id="askdocsDepth">
              <option value="" selected>${escapeHtml(t("askdocs.depthPrecise"))}</option>
              <option value="8000">${escapeHtml(t("askdocs.depthWide"))}</option>
              <option value="50000:48:20">${escapeHtml(t("askdocs.depthDeep"))}</option>
            </select>
          </label>
          <button class="askdocs-submit" id="askdocsSubmit" type="submit">${icon("file-search-2")}<span>${escapeHtml(isZh ? "提问" : "Ask")}</span></button>
        </div>
      </form>
      <div class="askdocs-result" id="askdocsResult" hidden></div>
    </div>`, { wide: true });
  refreshIcons();

  const form = $("#askdocsForm");
  const textarea = $("#askdocsQuestion");
  const submit = $("#askdocsSubmit");
  const result = $("#askdocsResult");
  if (!form || !textarea || !submit || !result) return;
  textarea.focus();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = textarea.value.trim();
    if (!question) return;
    const k = Number($("#askdocsK")?.value ?? "4") || 4;
    // M8-T1317: depth encodes "budget:fanout:per". A deep context must raise
    // lexical recall, not just the budget — otherwise there is nothing to pack.
    const depthParts = String($("#askdocsDepth")?.value ?? "").split(":").map(Number);
    const budget = depthParts[0] || 0;
    const fanout = depthParts[1] || 0;
    const perVariant = depthParts[2] || 0;

    submit.disabled = true;
    submit.innerHTML = `${icon("loader-circle")}<span>${escapeHtml(isZh ? "检索中…" : "Retrieving…")}</span>`;
    refreshIcons();
    result.hidden = false;
    result.innerHTML = `<div class="askdocs-working">${icon("loader-circle")}<span>${escapeHtml(isZh
      ? "BM25 正在这本仓库的文档里检索…"
      : "BM25 is searching this repository's docs…")}</span></div>`;

    try {
      const depth = budget > 0
        ? `&budget=${budget}${fanout ? `&fanout=${fanout}` : ""}${perVariant ? `&per=${perVariant}` : ""}`
        : "";
      const payload = await requestJson(`/api/rag/query?q=${encodeURIComponent(question)}&k=${k}${depth}`, {}, 60000);
      const sources = Array.isArray(payload?.sources) ? payload.sources : [];
      const answer = typeof payload?.answer === "string" ? payload.answer.trim() : "";
      const error = payload?.error;
      const model = payload?.model;
      const baseUrl = payload?.base_url;

      const context = payload?.context;
      const metaParts = [model ? escapeHtml(isZh ? `模型 · ${model}` : `model · ${model}`) : "",
        baseUrl ? escapeHtml(isZh ? `端点 · ${baseUrl}` : `endpoint · ${baseUrl}`) : ""];
      if (context) metaParts.push(escapeHtml(t("askdocs.deepMode")));
      const meta = metaParts.filter(Boolean).join("<br/>");

      const answerBlock = answer
        ? `<div class="askdocs-answer">${escapeHtml(answer)}</div>`
        : `<div class="askdocs-answer askdocs-answer-empty">${escapeHtml(isZh
            ? "文档里没有直接答案。换个问法，或先在 docs/ 里确认有没有相关章节。"
            : "No direct answer in the docs. Rephrase, or check docs/ for a related chapter first.")}</div>`;

      const errorBlock = error
        ? `<div class="askdocs-error">${icon("alert-triangle")}<span>${escapeHtml(isZh ? `模型调用失败：${error}` : `Model call failed: ${error}`)}</span></div>`
        : "";

      const sourcesBlock = sources.length
        ? `<div class="askdocs-sources-title">${escapeHtml(isZh ? "引用来源" : "Sources")} <span class="askdocs-sources-count">${sources.length}</span></div>
           <div class="askdocs-sources">${sources.map((source, index) => sourceRow(index, source)).join("")}</div>`
        : "";

      result.innerHTML = `
        <div class="askdocs-meta">${meta}</div>
        ${answerBlock}
        ${errorBlock}
        <div class="askdocs-usage">${escapeHtml(usageLine(payload?.usage))}</div>
        ${contextEvidence(context, sources)}
        ${sourcesBlock}`;
      refreshIcons();
    } catch (error) {
      result.innerHTML = `<div class="askdocs-error">${icon("alert-triangle")}<span>${escapeHtml(error?.message || String(error))}</span></div>`;
      refreshIcons();
    } finally {
      submit.disabled = false;
      submit.innerHTML = `${icon("file-search-2")}<span>${escapeHtml(isZh ? "提问" : "Ask")}</span>`;
      refreshIcons();
    }
  });
}
