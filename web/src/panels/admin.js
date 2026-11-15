import { requestJson } from "../core/transport.js";
import { icon, refreshIcons } from "../icons.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";

const esc = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const zh = () => state.locale === "zh";
const compactCount = (value) => {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
};
const pct = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
};
const cssVar = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

export async function openAdmin() {
  const modal = $("#adminStage");
  if (!modal) return;
  modal.setAttribute("aria-hidden", "false");
  const close = $("#adminStageClose");
  if (close) close.onclick = () => modal.setAttribute("aria-hidden", "true");
  refreshIcons();

  const locked = $("#adminLocked");
  const unlocked = $("#adminUnlocked");
  if (locked) locked.removeAttribute("hidden");
  if (unlocked) unlocked.setAttribute("hidden", "");

  const press = $("#adminUnlockBtn");
  const password = $("#adminPassword");
  if (!press || !password) return;

  const attempt = async () => {
    if (password.value === "123") {
      if (locked) locked.setAttribute("hidden", "");
      if (unlocked) unlocked.removeAttribute("hidden");
      password.value = "";
      await loadSummary();
    } else {
      password.setAttribute("aria-invalid", "true");
      password.style.borderColor = "var(--coral)";
      password.value = "";
      window.setTimeout(() => password.removeAttribute("aria-invalid"), 1400);
    }
  };
  press.addEventListener("click", () => { void attempt(); });
  password.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); void attempt(); }
  });

  async function loadSummary() {
    const data = await requestJson("/api/admin/summary", {}, 20000).catch(() => null);
    const totals = data?.totals ?? {};
    const trend = Array.isArray(data?.trend_7d) ? data.trend_7d : [];
    const tasks = Array.isArray(data?.recent_tasks) ? data.recent_tasks : [];
    const recs = Array.isArray(data?.recommendations) ? data.recommendations : [];

    const set = (id, value) => { const el = $(`#${id}`); if (el) el.textContent = String(value); };
    set("adminTotalTasks", totals.tasks ?? "—");
    set("adminCompleted", totals.completed ?? "—");
    set("adminInterrupted", totals.interrupted ?? "—");
    set("adminCacheRate", pct(totals.cache_hit_rate));
    set("adminAuditLines", compactCount(totals.audit_lines ?? 0));
    set("adminSessions", totals.sessions != null ? compactCount(totals.sessions) : "—");

    const canvas = $("#adminTrendCanvas");
    if (canvas && trend.length) {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 360;
      const h = canvas.clientHeight || 140;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      const ctx = canvas.getContext("2d");
      if (ctx) {
        const mint = cssVar("--mint", "#34d399");
        const quiet = cssVar("--quiet", "#94a3b8");
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, w, h);
        const maxV = Math.max(1, ...trend.map((l) => Number(l.events || 0)));
        const slot = (w - 16) / trend.length;
        const barW = Math.max(10, Math.floor(slot * 0.55));
        ctx.font = "9px 'DM Mono', Consolas, monospace";
        trend.forEach((pt, i) => {
          const v = Number(pt.events || 0);
          const bh = Math.max(2, (v / maxV) * (h - 40));
          const x = 8 + i * slot + (slot - barW) / 2;
          const y = h - 18 - bh;
          ctx.fillStyle = v > 0 ? mint : quiet;
          ctx.globalAlpha = v > 0 ? 0.9 : 0.25;
          ctx.fillRect(x, y, barW, bh);
          ctx.globalAlpha = 1;
          ctx.fillStyle = cssVar("--muted", "#94a3b8");
          ctx.fillText(String(v), x + barW / 2 - 4, y - 2);
        });
      }
    }

    const recList = $("#adminRecommendations");
    if (recList) {
      recList.innerHTML = recs.length
        ? recs.map((rec) => `
          <li class="admin-rec admin-rec-${esc(rec.priority || "low")}">
            <strong>${esc(zh() ? rec.title_zh : rec.title_en)}</strong>
            <span>${esc(zh() ? rec.why_zh : rec.why_en)}</span>
          </li>`).join("")
        : `<li class="admin-rec admin-rec-good">${esc(zh() ? "暂无建议 —— 数据看起来不错。" : "No outstanding calls to make on this data — it looks healthy.")}</li>`;
    }

    const taskList = $("#adminRecentTasks");
    if (taskList) {
      taskList.innerHTML = tasks.length
        ? tasks.map((t) => `
          <li class="admin-task">
            <span class="admin-task-id">${esc(t.id ?? "")}</span>
            <span class="admin-task-message">${esc(t.message ?? "")}</span>
            <span class="admin-task-meta">${esc(t.status ?? "")} · ${t.age_hours != null ? `${t.age_hours}h` : "—"}</span>
          </li>`).join("")
        : `<li class="admin-task"><span class="admin-task-message">${esc(zh() ? "没有近期任务记录。" : "No recent tasks.")}</span></li>`;
    }

    refreshIcons();
  }
}
