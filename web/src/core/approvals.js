// M7-T3 interactive approvals: surface approval_request frames from the task
// event stream as answerable cards. The agent thread blocks server-side until
// the user decides or the timeout auto-denies, so the card mirrors that
// deadline locally and drops itself once an approval_resolved frame arrives.
import { requestJson } from "./transport.js";
import { t } from "./i18n.js";
import { escapeHtml } from "../chat/markdown.js";

const pending = new Map();
let ticker = 0;

function ensureLayer() {
  let layer = document.getElementById("approvalLayer");
  if (!layer) {
    layer = document.createElement("div");
    layer.id = "approvalLayer";
    layer.className = "approval-layer";
    layer.setAttribute("aria-live", "polite");
    document.body.append(layer);
  }
  return layer;
}

function removeCard(requestId) {
  const entry = pending.get(requestId);
  if (!entry) return;
  pending.delete(requestId);
  entry.node.remove();
  if (!pending.size && ticker) {
    window.clearInterval(ticker);
    ticker = 0;
  }
}

function tick() {
  const now = Date.now();
  for (const [requestId, entry] of pending) {
    if (entry.busy) continue;
    if (now >= entry.deadline) {
      // The server auto-denies at the deadline; the resolved frame removes
      // other stragglers, but the user left, so drop the stale card locally.
      removeCard(requestId);
      continue;
    }
    const label = entry.node.querySelector("[data-approval-count]");
    if (label) label.textContent = `${Math.ceil((entry.deadline - now) / 1000)}${t("approval.expire")}`;
  }
  if (!pending.size && ticker) {
    window.clearInterval(ticker);
    ticker = 0;
  }
}

async function decide(requestId, decision) {
  const entry = pending.get(requestId);
  if (!entry || entry.busy) return;
  entry.busy = true;
  entry.node.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  try {
    await requestJson("/api/approval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId, decision }),
    }, 8000);
  } catch (error) {
    // The agent-side timeout is the backstop; a failed POST must not leave a
    // permanently stuck card.
  }
  removeCard(requestId);
}

function addCard(event) {
  const layer = ensureLayer();
  const node = document.createElement("div");
  node.className = "approval-card";
  node.setAttribute("role", "alertdialog");
  node.setAttribute("aria-label", t("approval.title"));
  const timeoutSeconds = Number(event.timeout_seconds || 60) || 60;
  node.innerHTML = `
    <div class="approval-card-head"><strong>${escapeHtml(t("approval.title"))}</strong><span data-approval-count></span></div>
    <div class="approval-card-body"><b>${escapeHtml(String(event.tool || event.name || ""))}</b><code>${escapeHtml(String(event.preview || "").slice(0, 300))}</code><small>${escapeHtml(t("approval.reason"))}：${escapeHtml(String(event.reason || event.summary || ""))}</small></div>
    <div class="approval-card-actions">
      <button type="button" data-decision="allow">${escapeHtml(t("approval.allow"))}</button>
      <button type="button" data-decision="always">${escapeHtml(t("approval.always"))}</button>
      <button type="button" class="approval-deny" data-decision="deny">${escapeHtml(t("approval.deny"))}</button>
    </div>`;
  node.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => decide(event.request_id, button.dataset.decision));
  });
  const entry = {
    node,
    deadline: Date.now() + timeoutSeconds * 1000,
    busy: false,
  };
  pending.set(event.request_id, entry);
  layer.append(node);
  node.querySelector("[data-approval-count]").textContent = `${timeoutSeconds}${t("approval.expire")}`;
  if (!ticker) ticker = window.setInterval(tick, 250);
}

export function syncApprovalRequests(events) {
  if (!Array.isArray(events)) return;
  const resolved = new Set(
    events.filter((event) => event?.kind === "approval_resolved" && event.request_id)
      .map((event) => event.request_id),
  );
  for (const requestId of [...pending.keys()]) {
    if (resolved.has(requestId)) removeCard(requestId);
  }
  for (const event of events) {
    if (!event || event.kind !== "approval_request" || !event.request_id) continue;
    if (resolved.has(event.request_id) || pending.has(event.request_id)) continue;
    // Events replay from the task log; only surface prompts that could still
    // be waiting on the server side (the frame carries no emit timestamp, so
    // treat a task that already resolved everything else as historical).
    if (event.stale === true) continue;
    addCard(event);
  }
}

export function clearApprovalCards() {
  for (const requestId of [...pending.keys()]) removeCard(requestId);
}
