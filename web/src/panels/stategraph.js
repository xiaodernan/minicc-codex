/* ============================================================
   Minicc StateGraph — the seven-phase axis the agent walks on.

   Replica of minicc/agent/graph.py::build_coding_workflow() in
   ink — the same GraphNode(id, phase, max_retries=...) call.
   Clicking a node swaps the detail pane to that node's verbatim
   call and one paragraph of meaning. Read-only; no network.
   ============================================================ */

import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";

const zh = () => state.locale === "zh";

// Verbatim mirror: minicc/agent/graph.py::build_coding_workflow()
const NODES = [
  { id: "intake", phase: "intake", maxRetries: 0,
    zh: "接收 & 理解请求——这里开始一切；这里也结束你想用哪种语言。",
    en: "Receive & understand the request — where everything begins; where the requested language is honored or ignored." },
  { id: "plan", phase: "planning", maxRetries: 0,
    zh: "读 digest / roadmap / 统计，把大任务拆成不会崩的 DAG——再逐节点写死。",
    en: "Read digest / roadmap / stats, break the big task into a non-imploding DAG, then write each node concretely." },
  { id: "inspect", phase: "inspect", maxRetries: 0,
    zh: "再读一遍文件——读的是真实源码，不是 README 的承诺。",
    en: "Re-read the actual files — the real source, not the README's promises." },
  { id: "implement", phase: "implement", maxRetries: 0,
    zh: "派 subagent / DAG 真正写——不落实现就是没干活。",
    en: "Dispatch subagent / DAG-for-real — not writing means not working." },
  { id: "verify", phase: "verify", maxRetries: 2,
    zh: "测试 / 验证——最多走两次，败了就进 repair 的环。",
    en: "Test / verify — up to two passes, then it falls into the repair arc." },
  { id: "repair", phase: "repair", maxRetries: 2,
    zh: "把 verify 的错误当输入再写一次——重试上限同样是 max_retries=2。",
    en: "Treat verify's failure as input, write again — same cap, max_retries=2." },
  { id: "summarize", phase: "summarize", maxRetries: 0,
    zh: "收口——把这一轮做了什么、验证了什么交出去，不再重建也不道歉。",
    en: "Wind down — hand back what this round did and what it verified; no rebuilds, no apologies." },
];

const EDGES = [
  { from: "intake", to: "plan", on: "ok" },
  { from: "plan", to: "inspect", on: "ok" },
  { from: "inspect", to: "implement", on: "ok" },
  { from: "implement", to: "verify", on: "ok" },
  { from: "verify", to: "summarize", on: "ok" },
  { from: "verify", to: "repair", on: "failed" },
  { from: "repair", to: "verify", on: "ok" },
  { from: "repair", to: "summarize", on: "failed" },
];

function nodeCall(node) {
  return `GraphNode("${node.id}", "${node.phase}", max_retries=${node.maxRetries})`;
}

function renderNode(node, active) {
  return `<button type="button" class="stategraph-node ${active === node.id ? "stategraph-node-active" : ""}" data-node="${escapeHtml(node.id)}">
            <span class="stategraph-node-name">${escapeHtml(node.id)}</span>
            <span class="stategraph-node-phase">${escapeHtml(node.phase)}</span>
            <span class="stategraph-node-retries">${node.maxRetries > 0 ? `max_retries=${node.maxRetries}` : "—"}</span>
          </button>`;
}

function laneMarkup(active) {
  return NODES.map((node) => renderNode(node, active)).join(`<span class="stategraph-lane-arrow">→</span>`);
}

function detailMarkup(id) {
  const node = NODES.find((n) => n.id === id) ?? NODES[0];
  const isZh = zh();
  return `
    <div class="stategraph-body-callout">
      <div class="stategraph-callout-label">${escapeHtml(isZh ? "节点" : "Phase")}</div>
      <div class="stategraph-callout-row"><span class="stategraph-callout-value">${escapeHtml(node.id)}</span><span class="stategraph-callout-sub">${escapeHtml(node.phase)}</span></div>
    </div>
    <div class="stategraph-body-callout">
      <div class="stategraph-callout-label">${escapeHtml(isZh ? "重试上限" : "Max retries")}</div>
      <div class="stategraph-callout-value stategraph-callout-value-inline">${node.maxRetries}</div>
    </div>
    <div class="stategraph-body-callout">
      <div class="stategraph-callout-label">${escapeHtml(isZh ? "源码调用" : "Source call")}</div>
      <code class="stategraph-call">${escapeHtml(nodeCall(node))}</code>
    </div>
    <div class="stategraph-body-callout stategraph-body-callout-wide">${escapeHtml(isZh ? node.zh : node.en)}</div>`;
}

function render() {
  const isZh = zh();
  const activeId = "verify";
  return `
    <div class="stategraph-shell">
      <div class="stategraph-kicker">${escapeHtml(isZh ? "状态图 · 本项目自己的阶段轴" : "StateGraph · this repo's own phase axis")}</div>
      <h1 class="stategraph-title">${isZh
        ? `你眼前这一页不是<br/><span class="stategraph-title-accent">另一份说明。</span>`
        : `You are not reading<br/><span class="stategraph-title-accent">another spec.</span>`}</h1>
      <p class="stategraph-lede">${escapeHtml(isZh
        ? "这是 minicc/agent/graph.py::build_coding_workflow() 返回的 StateGraph 的忠实复刻——点节点，看它在源文件里真正被刻成的样子。"
        : "A faithful replica of the StateGraph that minicc/agent/graph.py::build_coding_workflow() returns — click a node and read the very call the runtime makes.")}</p>

      <div class="stategraph-lane" role="list">${laneMarkup(activeId)}</div>

      <div class="stategraph-body" id="stategraphDetail">${detailMarkup(activeId)}</div>

      <div class="stategraph-edges">
        <div class="stategraph-edges-title">${escapeHtml(isZh ? "边 · on=" : "Edges · on=")}${escapeHtml(isZh ? "条件" : "condition")}</div>
        ${EDGES.map((edge) => `<div class="stategraph-edge-row"><code>${escapeHtml(edge.from)} → ${escapeHtml(edge.to)}</code><span class="stategraph-edge-on">on = ${escapeHtml(edge.on)}</span></div>`).join("")}
      </div>

      <p class="stategraph-foot">${escapeHtml(isZh
        ? "本面板不调任何模型、不走网络——它只把你源仓库里那个编译时常数平铺到你眼前。"
        : "Zero API calls, zero network — this panel only lays flat the compile-time constants living in your repo.")}</p>
    </div>`;
}

export async function openStategraphPanel() {
  const title = zh() ? "状态图 · 阶段轴" : "StateGraph · The Axis";
  const current = beginPanelRequest(title);
  try {
    openPanel(title, render(), { wide: true, immersive: true });
    $("#stategraphDetail").querySelectorAll(".stategraph-node"); // no-op safeguard against orphaned queries
    document.querySelectorAll(".stategraph-node").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.getAttribute("data-node") || "verify";
        document.querySelectorAll(".stategraph-node").forEach((nodeEl) => {
          nodeEl.classList.toggle("stategraph-node-active", nodeEl === button);
        });
        const detail = $("#stategraphDetail");
        if (detail) detail.innerHTML = detailMarkup(id);
      });
    });
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(title, `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
