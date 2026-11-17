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
    const streak = data?.completion_streak;
    set("adminStreak", streak && typeof streak.current === "number" ? String(streak.current) : "—");
    renderRatelimit(data?.ratelimit ?? null, false);

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

    // forecast line from a real 7-day linear projection
    const forecast = data?.forecast;
    const fcWrap = $("#adminForecast");
    if (fcWrap) {
      if (forecast && typeof forecast === "object") {
        fcWrap.removeAttribute("hidden");
        const dir = forecast.direction === "down" ? t("admin.forecastFading") : forecast.direction === "up" ? t("admin.forecastRising") : t("admin.forecastFlat");
        const headline = $("#adminForecastHeadline");
        const note = $("#adminForecastNote");
        if (headline) headline.textContent = `${t("admin.forecastLine").replace("{n}", String(forecast.last_2_avg ?? "—")).replace("{slope}", String(forecast.slope_per_day >= 0 ? `+${forecast.slope_per_day}` : forecast.slope_per_day))} · ${dir}`;
        if (note) note.textContent = t("admin.forecastNote").replace("{lines}", String(totals.audit_lines ?? "—"));
      } else {
        fcWrap.setAttribute("hidden", "");
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

    // M8-T1062/M8-T1063: live mainline health — fire-and-forget after the summary render
    // closes; the tile fills in when GitHub answers. The admin unlock never waits on it.
    const ciPromise = requestJson("/api/ci_status", {}, 20000).catch(() => null);
    ciPromise.then((ci) => {
    try {
    const ciEl = (id) => $(`#${id}`);
    const recent = ci && typeof ci === "object" && Array.isArray(ci.recent) ? ci.recent : [];
    const conclusion = recent.length ? String(recent[0]?.conclusion || recent[0]?.status || "").toLowerCase() : "";
    const ciClass = conclusion === "success" ? "ci-up" : (conclusion === "failure" || conclusion === "cancelled" || conclusion === "timed_out") ? "ci-down" : "ci-unknown";
    if (ciEl("adminCiConclusion")) {
      ciEl("adminCiConclusion").classList.remove("ci-up", "ci-down", "ci-unknown");
      ciEl("adminCiConclusion").classList.add(ciClass);
      ciEl("adminCiConclusion").textContent = conclusion ? conclusion.toUpperCase() : String(t("admin.ciUnavailable"));
    }
    if (ciEl("adminCiWorkflow")) {
      ciEl("adminCiWorkflow").textContent = recent.length
        ? `${recent[0]?.workflow ?? "CI"} · ${String(recent[0]?.head_sha ?? "")}`
        : String(t("admin.ciUnavailable"));
    }
    if (ciEl("adminCiMeta")) {
      ciEl("adminCiMeta").textContent = recent.length
        ? `${String(recent[0]?.created_at ?? "").replace("T", " ").replace("Z", " UTC")}`
        : String(t("admin.ciUnavailable"));
    }
    if (ciEl("adminCiIssues")) ciEl("adminCiIssues").textContent = ci && typeof ci === "object" && ci.open_issues != null ? String(ci.open_issues) : "—";
    if (ciEl("adminCiPulls")) ciEl("adminCiPulls").textContent = ci && typeof ci === "object" && ci.open_prs != null ? String(ci.open_prs) : "—";
    const dotsEl = ciEl("adminCiDots");
    if (dotsEl) {
      const dotOf = (conclusion) => {
        const c = String(conclusion || "").toLowerCase();
        if (c === "success") return "admin-ci-dot-up";
        if (c === "failure" || c === "cancelled" || c === "timed_out") return "admin-ci-dot-down";
        return "admin-ci-dot-unknown";
      };
      dotsEl.innerHTML = recent.length
        ? recent.slice(0, 3).map((r) => `
          <li class="admin-ci-dot ${dotOf(r?.conclusion)}" title="${esc(String(r?.workflow ?? "") + " · " + String(r?.created_at ?? "") + " · " + String(r?.head_sha ?? ""))}">
            <small>${esc(String(r?.created_at ?? "").slice(0, 16))}</small>
            <strong>${esc(String(r?.conclusion || r?.status || "unknown"))} · ${esc(String(r?.head_sha ?? ""))}</strong>
          </li>`).join("")
        : `<li class="admin-ci-dot admin-ci-dot-unknown" title="${esc(String(t("admin.ciUnavailable")))}"><small>—</small><strong>${esc(String(t("admin.ciUnavailable")))}</strong></li>`;
    }
    } catch { /* the tile is best-effort; the panel never depends on it */ }
    });

    // M8-T1160: the drift sentinel — model-free oracle for repo self-consistency.
    // fire-and-forget, like the CI tile; the unlock never waits on it.
    function renderDrift(drift, refreshed) {
      const headEl = $("#adminDriftHead");
      const crlfEl = $("#adminDriftCrlf");
      const docsEl = $("#adminDriftDocs");
      const metaEl = $("#adminDriftMeta");
      const stampEl = $("#adminDriftStamp");
      if (!headEl || !crlfEl || !docsEl) return;
      if (stampEl) stampEl.textContent = drift && drift.generated_at ? String(drift.generated_at).replace("T", " ").replace("Z", " UTC") : "";
      if (!drift || !drift.live) {
        [headEl, crlfEl, docsEl].forEach((el) => { el.textContent = "—"; el.classList.remove("ok", "bad"); });
        if (metaEl) metaEl.textContent = zh()
          ? (drift?.error ? `error: ${String(drift.error).slice(0, 160)}` : "")
          : "the live drift wire is unreadable — see the log";
        return;
      }
      const aheadRaw = drift.commits_ahead;
      const verdict = aheadRaw == null ? (zh() ? "未知（浅克隆）" : "unknown (shallow clone)")
        : zh()
          ? (drift.in_sync
            ? `${drift.head_live} · 同步（事实包领先 ${aheadRaw} 个）`
            : `${drift.head_live} · 领先事实包 ${aheadRaw} 个（fact ${drift.fact_pack?.head}）`)
          : (drift.in_sync
            ? `${drift.head_live} · synced (pack +${aheadRaw})`
            : `${drift.head_live} · ${aheadRaw} ahead of fact pack (${drift.fact_pack?.head})`);
      headEl.textContent = aheadRaw == null ? `${drift.head_live} · ${verdict}` : verdict;
      if (aheadRaw == null) {
        headEl.classList.remove("ok", "bad");
      } else {
        headEl.classList.toggle("ok", Boolean(drift.in_sync));
        headEl.classList.toggle("bad", !drift.in_sync);
      }
      const idx = drift.crlf_pins?.index_html;
      const i18n = drift.crlf_pins?.i18n_js;
      crlfEl.textContent = drift.crlf_ok
        ? `✓ ${idx?.crlf}/0 · ${i18n?.crlf}/0`
        : `✗ ${idx?.crlf}/${idx?.lf_only} · ${i18n?.crlf}/${i18n?.lf_only}`;
      crlfEl.classList.toggle("ok", Boolean(drift.crlf_ok));
      crlfEl.classList.toggle("bad", !drift.crlf_ok);
      const doc = drift.doc_pointers || {};
      docsEl.textContent = doc.status === "running" ? "…" : (doc.rc == null ? "—" : (doc.ok ? "rc=0 ✓" : `rc=${doc.rc}`));
      docsEl.classList.toggle("ok", doc.ok === true);
      docsEl.classList.toggle("bad", doc.rc != null && doc.ok === false);
      if (metaEl) {
        const limit = (drift.honest_limits?.[0] ?? "").replace(/\s+/g, " ");
        metaEl.textContent = `${refreshed ? (zh() ? "已重新核验 · " : "re-verified · ") : ""}${limit}`;
      }
    }
    const driftPromise = requestJson("/api/admin/drift", {}, 60000).catch(() => null);
    driftPromise.then((drift) => { try { renderDrift(drift, false); } catch { /* panel never depends on it */ } });
    const driftRefresh = $("#adminDriftRefresh");
    if (driftRefresh) {
      driftRefresh.addEventListener("click", () => {
        requestJson("/api/admin/drift?fresh=1", {}, 300000).then((drift) => renderDrift(drift, true)).catch(() => {});
      });
    }

    // Live workspace brief — the model on duty for this workspace:
    // fire-and-forget, like the CI tile. The unlock never waits on it.
    function renderBrief(brief, refreshed) {
      const bodyEl = $("#adminBriefBody");
      const usageEl = $("#adminBriefUsage");
      const byEl = $("#adminBriefModel");
      if (byEl && brief && brief.model) byEl.textContent = brief.model;
      else if (byEl) byEl.textContent = zh() ? "由模型现扫" : "read live by the model";
      if (!brief || !brief.live) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.briefOutage"))}</p>`;
        if (usageEl) usageEl.textContent = brief?.error ? `error: ${String(brief.error).slice(0, 140)}` : "";
        return;
      }
      const text = zh() ? brief.zh : brief.en;
      if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-text">${esc(text || (zh() ? brief.en : brief.zh))}</p>`;
      if (usageEl) {
        const u = brief.usage || {};
        const cached = u.cached_tokens != null ? (zh() ? ` · 缓存命中 ${u.cached_tokens}` : ` · cached ${u.cached_tokens}`) : "";
        usageEl.textContent = zh()
          ? `tokens：prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · 已重新生成" : ""}`
          : `tokens: prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · regenerated" : ""}`;
      }
    }
    const briefRefresh = $("#adminBriefRefresh");
    if (briefRefresh) {
      briefRefresh.addEventListener("click", () => {
        const bodyEl = $("#adminBriefBody");
        const usageEl = $("#adminBriefUsage");
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.briefPending"))}</p>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/oracle-brief?fresh=1", {}, 30000).catch(() => null).then((brief) => renderBrief(brief, true));
      });
    }
    const briefPromise = requestJson("/api/oracle-brief", {}, 30000).catch(() => null);
    briefPromise.then((brief) => renderBrief(brief, false));

    // Live workspace diagnosis — same pattern, pointed at the triage snapshot.
    function renderDiagnosis(diagnosis, refreshed) {
      const bodyEl = $("#adminDiagnosisBody");
      const usageEl = $("#adminDiagnosisUsage");
      const byEl = $("#adminDiagnosisModel");
      if (byEl && diagnosis && diagnosis.model) byEl.textContent = diagnosis.model;
      else if (byEl) byEl.textContent = zh() ? "由模型现扫" : "read live by the model";
      if (!diagnosis || !diagnosis.live) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.diagnosisOutage"))}</p>`;
        if (usageEl) usageEl.textContent = diagnosis?.error ? `error: ${String(diagnosis.error).slice(0, 140)}` : "";
        return;
      }
      const text = zh() ? diagnosis.zh : diagnosis.en;
      if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-text">${esc(text || (zh() ? diagnosis.en : diagnosis.zh))}</p>`;
      if (usageEl) {
        const u = diagnosis.usage || {};
        const cached = u.cached_tokens != null ? (zh() ? ` · 缓存命中 ${u.cached_tokens}` : ` · cached ${u.cached_tokens}`) : "";
        usageEl.textContent = zh()
          ? `tokens：prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · 已重新生成" : ""}`
          : `tokens: prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · regenerated" : ""}`;
      }
    }
    const diagnosisRefresh = $("#adminDiagnosisRefresh");
    if (diagnosisRefresh) {
      diagnosisRefresh.addEventListener("click", () => {
        const bodyEl = $("#adminDiagnosisBody");
        const usageEl = $("#adminDiagnosisUsage");
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.diagnosisPending"))}</p>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/oracle-diagnosis?fresh=1", {}, 30000).catch(() => null).then((diagnosis) => renderDiagnosis(diagnosis, true));
      });
    }
    const diagnosisPromise = requestJson("/api/oracle-diagnosis", {}, 30000).catch(() => null);
    diagnosisPromise.then((diagnosis) => renderDiagnosis(diagnosis, false));

    // First three moves — the model orders the workspace's priorities.
    function renderPlan(plan, refreshed) {
      const listEl = $("#adminPlanList");
      const usageEl = $("#adminPlanUsage");
      const byEl = $("#adminPlanModel");
      if (byEl && plan && plan.model) byEl.textContent = plan.model;
      else if (byEl) byEl.textContent = zh() ? "由模型现扫" : "read live by the model";
      if (!plan || !plan.live) {
        if (listEl) listEl.innerHTML = `<li class="admin-plan-empty"><em class="admin-brief-pending">${esc(t("admin.planOutage"))}</em></li>`;
        if (usageEl) usageEl.textContent = plan?.error ? `error: ${String(plan.error).slice(0, 140)}` : "";
        return;
      }
      const items = zh() ? (plan.zh || []) : (plan.en || []);
      const list = items.length ? items : (zh() ? plan.en : plan.zh) || [];
      if (listEl) listEl.innerHTML = list.slice(0, 3).map((item, index) => `<li class="admin-plan-item"><strong class="admin-plan-rank">${index + 1}</strong><span>${esc(String(item))}</span></li>`).join("");
      if (usageEl) {
        const u = plan.usage || {};
        const cached = u.cached_tokens != null ? (zh() ? ` · 缓存命中 ${u.cached_tokens}` : ` · cached ${u.cached_tokens}`) : "";
        usageEl.textContent = zh()
          ? `tokens：prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · 已重新生成" : ""}`
          : `tokens: prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · regenerated" : ""}`;
      }
    }
    const planRefresh = $("#adminPlanRefresh");
    if (planRefresh) {
      planRefresh.addEventListener("click", () => {
        const listEl = $("#adminPlanList");
        const usageEl = $("#adminPlanUsage");
        if (listEl) listEl.innerHTML = `<li class="admin-plan-empty"><em class="admin-brief-pending">${esc(t("admin.planPending"))}</em></li>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/oracle-plan?fresh=1", {}, 30000).catch(() => null).then((plan) => renderPlan(plan, true));
      });
    }
    const planPromise = requestJson("/api/oracle-plan", {}, 30000).catch(() => null);
    planPromise.then((plan) => renderPlan(plan, false));

    // Live code review — model as reviewer of this repo's latest diff.
    function renderReview(review, refreshed) {
      const bodyEl = $("#adminReviewBody");
      const usageEl = $("#adminReviewUsage");
      const byEl = $("#adminReviewModel");
      if (byEl && review && review.model) byEl.textContent = review.model;
      else if (byEl) byEl.textContent = zh() ? "由模型现扫" : "read live by the model";
      if (!review || !review.live) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.reviewOutage"))}</p>`;
        if (usageEl) usageEl.textContent = review?.error ? `error: ${String(review.error).slice(0, 140)}` : "";
        return;
      }
      const text = zh() ? review.zh : review.en;
      if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-text">${esc(text || (zh() ? review.en : review.zh))}</p>`;
      if (usageEl) {
        const u = review.usage || {};
        const cached = u.cached_tokens != null ? (zh() ? ` · 缓存命中 ${u.cached_tokens}` : ` · cached ${u.cached_tokens}`) : "";
        usageEl.textContent = zh()
          ? `tokens：prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · 已重新生成" : ""}`
          : `tokens: prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · regenerated" : ""}`;
      }
    }
    const reviewRefresh = $("#adminReviewRefresh");
    if (reviewRefresh) {
      reviewRefresh.addEventListener("click", () => {
        const bodyEl = $("#adminReviewBody");
        const usageEl = $("#adminReviewUsage");
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.reviewPending"))}</p>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/oracle-review?fresh=1", {}, 30000).catch(() => null).then((review) => renderReview(review, true));
      });
    }
    const reviewPromise = requestJson("/api/oracle-review", {}, 30000).catch(() => null);
    reviewPromise.then((review) => renderReview(review, false));

    // The retrospective — judge the plausibility of the last "completed" task.
    function renderRetrospective(retrospective, refreshed) {
      const bodyEl = $("#adminRetrospectiveBody");
      const usageEl = $("#adminRetrospectiveUsage");
      const byEl = $("#adminRetrospectiveModel");
      if (byEl && retrospective && retrospective.model) byEl.textContent = retrospective.model;
      else if (byEl) byEl.textContent = zh() ? "由模型现扫" : "read live by the model";
      if (!retrospective || !retrospective.live) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.retrospectiveOutage"))}</p>`;
        if (usageEl) usageEl.textContent = retrospective?.error ? `error: ${String(retrospective.error).slice(0, 140)}` : "";
        return;
      }
      const text = zh() ? retrospective.zh : retrospective.en;
      if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-text">${esc(text || (zh() ? retrospective.en : retrospective.zh))}</p>`;
      if (usageEl) {
        const u = retrospective.usage || {};
        const cached = u.cached_tokens != null ? (zh() ? ` · 缓存命中 ${u.cached_tokens}` : ` · cached ${u.cached_tokens}`) : "";
        usageEl.textContent = zh()
          ? `tokens：prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · 已重新生成" : ""}`
          : `tokens: prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · regenerated" : ""}`;
      }
    }
    const retrospectiveRefresh = $("#adminRetrospectiveRefresh");
    if (retrospectiveRefresh) {
      retrospectiveRefresh.addEventListener("click", () => {
        const bodyEl = $("#adminRetrospectiveBody");
        const usageEl = $("#adminRetrospectiveUsage");
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.retrospectivePending"))}</p>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/oracle-retrospective?fresh=1", {}, 30000).catch(() => null).then((retrospective) => renderRetrospective(retrospective, true));
      });
    }
    const retrospectivePromise = requestJson("/api/oracle-retrospective", {}, 30000).catch(() => null);
    retrospectivePromise.then((retrospective) => renderRetrospective(retrospective, false));

    // CI red attribution — the model reads the real GitHub wire and says which
    // failure family the latest mainline red belongs to, or honestly says there is none.
    function renderCiDx(cidx, refreshed) {
      const bodyEl = $("#adminCiDxBody");
      const usageEl = $("#adminCiDxUsage");
      const byEl = $("#adminCiDxModel");
      if (byEl && cidx && cidx.model) byEl.textContent = cidx.model;
      else if (byEl) byEl.textContent = zh() ? "由模型现判" : "read live by the model";
      if (!cidx || !cidx.live) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.ciDxOutage"))}</p>`;
        if (usageEl) {
          const line = zh() ? (cidx?.zh_error ?? cidx?.error) : (cidx?.en_error ?? cidx?.error);
          usageEl.textContent = line ? String(line).slice(0, 160) : "";
        }
        return;
      }
      const text = zh() ? cidx.zh : cidx.en;
      if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-text">${esc(text || (zh() ? cidx.en : cidx.zh))}</p>`;
      if (usageEl) {
        if (cidx.verdict === "no-current-failure") {
          usageEl.textContent = zh() ? "当前 main 绿 · 0 tokens · 模型未被调用" : "main is green · 0 tokens · model not called";
        } else {
          const u = cidx.usage || {};
          const cached = u.cached_tokens != null ? (zh() ? ` · 缓存命中 ${u.cached_tokens}` : ` · cached ${u.cached_tokens}`) : "";
          usageEl.textContent = zh()
            ? `tokens：prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · 已重新生成" : ""}`
            : `tokens: prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${refreshed ? " · regenerated" : ""}`;
        }
      }
    }
    const ciDxRefresh = $("#adminCiDxRefresh");
    if (ciDxRefresh) {
      ciDxRefresh.addEventListener("click", () => {
        const bodyEl = $("#adminCiDxBody");
        const usageEl = $("#adminCiDxUsage");
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.ciDxPending"))}</p>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/oracle-ci-diagnosis?fresh=1", {}, 30000).catch(() => null).then((cidx) => renderCiDx(cidx, true));
      });
    }
    const ciDxPromise = requestJson("/api/oracle-ci-diagnosis", {}, 30000).catch(() => null);
    ciDxPromise.then((cidx) => renderCiDx(cidx, false));
    // Audit story — the model reads the last slice of audit.jsonl aloud.
    function renderAudit(story, refreshed) {
      const bodyEl = $("#adminAuditBody");
      const usageEl = $("#adminAuditUsage");
      const byEl = $("#adminAuditModel");
      if (byEl && story && story.model) byEl.textContent = story.model;
      else if (byEl) byEl.textContent = zh() ? "由模型现读" : "read live by the model";
      if (!story || !story.live) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.auditOutage"))}</p>`;
        if (usageEl) usageEl.textContent = story?.error ? `error: ${String(story.error).slice(0, 140)}` : "";
        return;
      }
      if (story.verdict === "no-audit") {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-text">${esc(zh() ? story.zh : story.en)}</p>`;
        if (usageEl) usageEl.textContent = zh() ? "0 tokens · 模型未被调用" : "0 tokens · model not called";
        return;
      }
      const text = zh() ? story.zh : story.en;
      if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-text">${esc(text || (zh() ? story.en : story.zh))}</p>`;
      if (usageEl) {
        const u = story.usage || {};
        const cached = u.cached_tokens != null ? (zh() ? ` · 缓存命中 ${u.cached_tokens}` : ` · cached ${u.cached_tokens}`) : "";
        const lines = story.total_lines != null
          ? (zh() ? ` · 读取记录 ${story.window_size ?? "?"}/${story.total_lines} 条` : ` · read ${story.window_size ?? "?"}/${story.total_lines} lines`)
          : "";
        usageEl.textContent = zh()
          ? `tokens：prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${lines}${refreshed ? " · 已重读" : ""}`
          : `tokens: prompt ${u.prompt_tokens ?? "—"} · completion ${u.completion_tokens ?? "—"}${cached}${lines}${refreshed ? " · re-read" : ""}`;
      }
    }
    const auditRefresh = $("#adminAuditRefresh");
    if (auditRefresh) {
      auditRefresh.addEventListener("click", () => {
        const bodyEl = $("#adminAuditBody");
        const usageEl = $("#adminAuditUsage");
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.auditPending"))}</p>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/oracle-audit-story?fresh=1", {}, 30000).catch(() => null).then((story) => renderAudit(story, true));
      });
    }
    const auditPromise = requestJson("/api/oracle-audit-story", {}, 30000).catch(() => null);
    auditPromise.then((story) => renderAudit(story, false));
    // Gateway budget — how close the shared 60s / 20-per-client token bucket is
    // to refusing the panel's own model calls; reads what the gate keeps.
    function renderRatelimit(stats, refreshed) {
      const bodyEl = $("#adminRatelimitBody");
      const usageEl = $("#adminRatelimitUsage");
      if (!stats || stats.error) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.ratelimitOutage"))}</p>`;
        if (usageEl) usageEl.textContent = stats?.error ? `error: ${String(stats.error).slice(0, 140)}` : "";
        return;
      }
      const allowedRedis = Number(stats?.decisions?.allowed_redis ?? 0);
      const allowedLocal = Number(stats?.decisions?.allowed_local ?? 0);
      const denied = Number(stats?.decisions?.denied ?? 0);
      const degraded = Number(stats?.decisions?.degraded_open ?? 0);
      const allowed = allowedRedis + allowedLocal;
      const limit = Number(stats.limit ?? 20);
      const windowS = Number(stats.window_seconds ?? 60);
      if (bodyEl) {
        bodyEl.innerHTML = `<ul class="admin-ratelimit-list">
          <li><strong>${zh() ? "每客户端每窗口" : "Per client, per window"}</strong><span>${esc(`${limit} / ${windowS}s`)}</span></li>
          <li><strong>${zh() ? "放行" : "Allowed"}</strong><span>${esc(`${allowed} (redis ${allowedRedis} · ${zh() ? "本地" : "local"} ${allowedLocal})`)}</span></li>
          <li><strong>${zh() ? "拒绝" : "Denied"}</strong><span>${esc(String(denied))}</span></li>
          <li><strong>${zh() ? "降级放行（Redis 断→照常服务并计数）" : "Degraded-open (Redis down → serve anyway, counted)"}</strong><span>${esc(String(degraded))}</span></li>
          <li><strong>${zh() ? "本地窗口占用" : "Local windows held"}</strong><span>${esc(String(stats.remaining_local_windows ?? 0))}</span></li>
        </ul>`;
      }
      if (usageEl) {
        usageEl.textContent = zh()
          ? `共享闸门 · Redis ${allowedRedis ? "在线" : "未配置/不可用"}${refreshed ? " · 已重读" : ""}`
          : `Shared bucket · Redis ${allowedRedis ? "serving" : "unconfigured / unavailable"}${refreshed ? " · re-read" : ""}`;
      }
    }


    // tool usage — top 6 tools called by the local agent, counted from real events
    const toolUsage = Array.isArray(data?.tool_usage) ? data.tool_usage : [];
    const toolList = $("#adminToolUsage");
    if (toolList) {
      const maxCount = Math.max(1, ...toolUsage.map((t) => Number(t.count || 0)));
      toolList.innerHTML = toolUsage.length
        ? toolUsage.map((t) => `
          <li class="admin-toolusage-item">
            <span class="admin-toolusage-name">${esc(t.name ?? "")}</span>
            <span class="admin-toolusage-bar"><span class="admin-toolusage-fill" style="width:${Math.min(100, Math.round((Number(t.count || 0) / maxCount) * 100))}%"></span></span>
            <span class="admin-toolusage-count">${compactCount(t.count ?? 0)} · ${Number(t.pct ?? 0).toFixed(0)}%</span>
          </li>`).join("")
        : `<li class="admin-toolusage-name">${esc(zh() ? "没有工具事件记录。" : "No tool events recorded.")}</li>`;
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
