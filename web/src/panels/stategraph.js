/* ============================================================
   Minicc StateGraph — the seven-phase axis the agent walks on.

   The panel renders the runtime's own objects when the live wire is
   up: nodes, edges and guard limits come from GET /api/stategraph
   (serialized straight off minicc/agent/graph.py by
   minicc/stategraph_payload.py), and the per-stage routing strip is
   resolved by the same StageRouter a real run builds.

   When the wire is down the panel falls back to an embedded ink
   replica of minicc/agent/graph.py::build_coding_workflow() — same
   GraphNode(id, phase, max_retries=...) calls, no network, honestly
   labelled as a replica. Clicking a node swaps the detail pane.
   ============================================================ */

import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel } from "../chat/stream.js";

const zh = () => state.locale === "zh";

// Verbatim mirror (fallback only): minicc/agent/graph.py::build_coding_workflow()
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

function nodeBlurb(node) {
  const match = NODES.find((n) => n.id === node.id);
  return zh() ? (match?.zh ?? "") : (match?.en ?? "");
}

function renderNode(node, active) {
  return `<button type="button" class="stategraph-node ${active === node.id ? "stategraph-node-active" : ""}" data-node="${escapeHtml(node.id)}">
            <span class="stategraph-node-name">${escapeHtml(node.id)}</span>
            <span class="stategraph-node-phase">${escapeHtml(node.phase)}</span>
            <span class="stategraph-node-retries">${node.maxRetries > 0 ? `max_retries=${node.maxRetries}` : "—"}</span>
          </button>`;
}

function laneMarkup(nodes, active) {
  return nodes.map((node) => renderNode(node, active)).join(`<span class="stategraph-lane-arrow">→</span>`);
}

function detailMarkup(nodes, id) {
  const node = nodes.find((n) => n.id === id) ?? nodes[0];
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
    <div class="stategraph-body-callout stategraph-body-callout-wide">${escapeHtml(nodeBlurb(node))}</div>`;
}

function guardsMarkup(guards) {
  const isZh = zh();
  const cells = [
    [isZh ? "节点 ≤" : "nodes ≤", guards.max_nodes],
    [isZh ? "深度 ≤" : "depth ≤", guards.max_depth],
    [isZh ? "并发 ≤" : "parallel ≤", guards.max_parallel],
    [isZh ? "步数 ≤" : "steps ≤", guards.max_steps],
  ];
  return `<div class="stategraph-guards" id="stategraphGuards">
    ${cells.map(([label, value]) => `<div class="stategraph-guard"><div class="stategraph-guard-label">${escapeHtml(String(label))}</div><div class="stategraph-guard-value">${escapeHtml(String(value))}</div></div>`).join("")}
  </div>`;
}

function routingMarkup(routing) {
  const isZh = zh();
  const enabled = routing?.enabled === true;
  const rows = (routing?.stages ?? []).map((stage) => {
    const detail = [
      `<span class="stategraph-routing-model">${escapeHtml(stage.model)}</span>`,
      `<span class="stategraph-routing-tier">${escapeHtml(stage.tier)}</span>`,
      stage.reasoning_effort ? `<span class="stategraph-routing-effort">${escapeHtml(stage.reasoning_effort)}</span>` : "",
      stage.max_cost_usd != null ? `<span class="stategraph-routing-cost">≤$${escapeHtml(String(stage.max_cost_usd))}</span>` : "",
    ].filter(Boolean).join("");
    return `<div class="stategraph-routing-row"><code>${escapeHtml(stage.stage)}</code>${detail}</div>`;
  }).join("");
  const note = enabled
    ? (isZh ? "stage_routing 已启用——按阶段分派模型（本页与每次任务同一 StageRouter）" : "stage_routing on — models dispatched per stage (the same StageRouter a live run builds)")
    : (isZh ? `stage_routing 未启用——所有阶段共用默认模型 ${routing?.default_model ?? ""}` : `stage_routing off — every stage rides the default model ${routing?.default_model ?? ""}`);
  return `<div class="stategraph-routing" id="stategraphRouting">
    <div class="stategraph-edges-title">${escapeHtml(isZh ? "阶段路由 · stage_routing" : "Stage routing")}</div>
    <p class="stategraph-routing-note">${escapeHtml(note)}</p>
    <div class="stategraph-routing-rows">${rows || `<div class="stategraph-routing-row"><em>${escapeHtml(isZh ? "（暂无阶段数据）" : "(no stage data)")}</em></div>`}</div>
  </div>`;
}

function edgesMarkup(edges) {
  return edges.map((edge) => `<div class="stategraph-edge-row"><code>${escapeHtml(edge.from)} → ${escapeHtml(edge.to)}</code><span class="stategraph-edge-on">on = ${escapeHtml(edge.on)}</span></div>`).join("");
}

function renderShell() {
  const isZh = zh();
  const activeId = "verify";
  return `
    <div class="stategraph-shell">
      <div class="stategraph-kicker">${escapeHtml(isZh ? "状态图 · 本项目自己的阶段轴" : "StateGraph · this repo's own phase axis")}<span class="stategraph-badge stategraph-badge-replica" id="stategraphBadge">${escapeHtml(isZh ? "离线复刻 · 内嵌副本" : "replica · embedded copy")}</span></div>
      <h1 class="stategraph-title">${isZh
        ? `你眼前这一页不是<br/><span class="stategraph-title-accent">另一份说明。</span>`
        : `You are not reading<br/><span class="stategraph-title-accent">another spec.</span>`}</h1>
      <p class="stategraph-lede" id="stategraphLede">${escapeHtml(isZh
        ? "内嵌副本：minicc/agent/graph.py::build_coding_workflow() 的手刻镜像——正在问实时链路……"
        : "Embedded replica: a hand mirror of minicc/agent/graph.py::build_coding_workflow() — asking the live wire…")}</p>

      <div class="stategraph-lane" id="stategraphLane" role="list">${laneMarkup(NODES, activeId)}</div>

      <div class="stategraph-body" id="stategraphDetail">${detailMarkup(NODES, activeId)}</div>

      <div class="stategraph-edges">
        <div class="stategraph-edges-title">${escapeHtml(isZh ? "边 · on=" : "Edges · on=")}${escapeHtml(isZh ? "条件" : "condition")}</div>
        <div id="stategraphEdges">${edgesMarkup(EDGES)}</div>
      </div>

      <p class="stategraph-foot">${escapeHtml(isZh
        ? "内嵌副本不调任何模型——实时模式由 minicc/stategraph_payload.py 在每次打开时现读 minicc/agent/graph.py。"
        : "The embedded replica calls nothing — live mode reads minicc/agent/graph.py through minicc/stategraph_payload.py on every open.")}</p>
    </div>`;
}

async function fetchStategraph() {
  try {
    const res = await fetch("/api/stategraph", { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges) || data.error) return null;
    return data;
  } catch {
    return null; // live wire down — embedded replica remains on screen, honestly labelled
  }
}

export async function openStategraphPanel() {
  const title = zh() ? "状态图 · 阶段轴" : "StateGraph · The Axis";
  const isZh = zh();
  try {
    openPanel(title, renderShell(), { wide: true, immersive: true });
    // Two-phase: the embedded replica paints first; the live wire swaps in next.
    const live = await fetchStategraph();
    if (!$("#stategraphBadge")) return; // panel was replaced or closed meanwhile
    if (live) {
      const activeId = live.nodes.some((n) => n.id === "verify") ? "verify" : live.nodes[0].id;
      const lane = $("#stategraphLane");
      if (lane) lane.innerHTML = laneMarkup(live.nodes, activeId);
      const edges = $("#stategraphEdges");
      if (edges) edges.innerHTML = edgesMarkup(live.edges);
      const detail = $("#stategraphDetail");
      if (detail) detail.innerHTML = detailMarkup(live.nodes, activeId);
      const badge = $("#stategraphBadge");
      if (badge) {
        badge.textContent = isZh ? "实时 · 来自 minicc/agent/graph.py" : "live · from minicc/agent/graph.py";
        badge.classList.remove("stategraph-badge-replica");
        badge.classList.add("stategraph-badge-live");
      }
      const lede = $("#stategraphLede");
      if (lede) lede.textContent = isZh
        ? "实时模式：节点、边、护栏与阶段路由全部现读自 minicc/agent/graph.py 与 StageRouter——不是另一份说明。"
        : "Live mode: nodes, edges, guards and stage routing are all read straight out of minicc/agent/graph.py and StageRouter — not another spec.";
      // Guards + routing strip, injected once around the edges block.
      const edgesBlock = document.querySelector(".stategraph-edges");
      if (edgesBlock && !$("#stategraphGuards")) {
        edgesBlock.insertAdjacentHTML("beforebegin", guardsMarkup(live.guards ?? {}));
        edgesBlock.insertAdjacentHTML("afterend", routingMarkup(live.routing));
      }
    }

    document.querySelectorAll(".stategraph-node").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.getAttribute("data-node") || "verify";
        document.querySelectorAll(".stategraph-node").forEach((nodeEl) => {
          nodeEl.classList.toggle("stategraph-node-active", nodeEl === button);
        });
        const detail = $("#stategraphDetail");
        if (detail) {
          const liveNodes = live?.nodes ?? NODES;
          detail.innerHTML = detailMarkup(liveNodes, id);
        }
      });
    });
    refreshIcons();
  } catch (error) {
    openPanel(title, `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
