/* ============================================================
   Minicc Journal — the repository's diary, written by itself.

   A read-only "today in the workshop" page that composes three
   fact packs that already exist — /api/digest, /api/stats and
   /api/metrics — into one view: vitals, the last twelve commits
   (this session's ledger tags highlighted), and workbench health.

   Nothing here is hardcoded: the day counter, the newest commit,
   the cache hit rate — every number is read live. Both locales,
   zh renders Chinese, en renders English, no mixed chrome.
   ============================================================ */

import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";
import { compactNumber } from "../panels/index.js";

const zh = () => state.locale === "zh";

function daysSince(isoDate) {
  if (!isoDate) return null;
  const started = new Date(String(isoDate).slice(0, 10));
  if (Number.isNaN(started.getTime())) return null;
  const ms = Date.now() - started.getTime();
  return Math.max(0, Math.floor(ms / 86400000));
}

function isToday(isoDate) {
  if (!isoDate) return false;
  const d = new Date(isoDate);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

function statCell(label, value) {
  return `<div class="journal-vital"><div class="journal-vital-label">${escapeHtml(label)}</div><div class="journal-vital-value">${escapeHtml(value)}</div></div>`;
}

function render(digest, stats, metrics) {
  const isZh = zh();
  const totalCommits = digest?.total_commits != null ? String(digest.total_commits) : "—";
  const head = `${digest?.branch ?? "—"}${digest?.head_short ? ` @ ${digest.head_short}` : ""}`;
  const days = daysSince(digest?.first_commit_at);
  const cacheHit = metrics?.llm_cache?.cache_hit_rate;
  const hitLabel = Number.isFinite(cacheHit) ? `${Math.round(cacheHit * 100)}%` : "—";
  const tokens = metrics?.usage?.total_tokens;
  const sessions = stats?.sessions?.count;
  const messages = stats?.sessions?.messages;
  const audit = stats?.audit?.present === true ? String(stats?.audit?.lines ?? "—") : "—";
  const model = metrics?.model || metrics?.provider || "—";

  const vitals = [
    statCell(isZh ? "提交总数" : "Commits", totalCommits),
    statCell(isZh ? "开张天数" : "Days building", days == null ? "—" : String(days)),
    statCell(isZh ? "批次手稿" : "Batch chapters", digest?.roadmap_batches != null ? String(digest.roadmap_batches) : "—"),
    statCell(isZh ? "跟踪文件" : "Tracked files", digest?.tracked_files != null ? String(digest.tracked_files) : "—"),
    statCell(isZh ? "测试文件" : "Test files", digest?.test_files != null ? String(digest.test_files) : "—"),
    statCell(isZh ? "分支" : "Branch", head),
  ].join("");

  const engine = [
    statCell(isZh ? "模型" : "Model", String(model)),
    statCell(isZh ? "会话" : "Sessions", sessions != null ? String(sessions) : "—"),
    statCell(isZh ? "消息" : "Messages", messages != null ? String(messages) : "—"),
    statCell(isZh ? "审计行" : "Audit lines", audit),
    statCell(isZh ? "累计 tokens" : "Tokens", tokens != null ? compactNumber(tokens) : "—"),
    statCell(isZh ? "缓存命中" : "Cache hit", hitLabel),
  ].join("");

  const commits = Array.isArray(digest?.recent_commits) ? digest.recent_commits : [];
  const ledgerHits = commits.filter((c) => /M8-T\d+/.test(c.subject || ""));
  const commitRows = commits.map((commit) => {
    const today = isToday(commit.at);
    const tag = /M8-T\d+/.test(commit.subject || "") ? (commit.subject.match(/M8-T\d+/) || [])[0] : null;
    return `<li class="journal-commit${today ? " journal-commit-today" : ""}"><code class="journal-sha">${escapeHtml(commit.short)}</code><span class="journal-subject">${escapeHtml(commit.subject)}</span>${tag ? `<span class="journal-tag">${escapeHtml(tag)}</span>` : ""}</li>`;
  }).join("");
  const ledgerCount = ledgerHits.length;

  return `
    <div class="journal-canvas">
      <div class="journal-kicker">${isZh ? "工程日志 · 记" : "The Journal"}</div>
      <h1 class="journal-title">${isZh ? "这个仓库自己写给自己的<br/><span class=\"journal-title-accent\">工程日志。</span>" : "The diary this repository<br/><span class=\"journal-title-accent\">writes about itself.</span>"}</h1>
      <div class="journal-body">
        <section class="journal-section">
          <h2 class="journal-section-title">${isZh ? "仓库体素" : "Repository vitals"}</h2>
          <div class="journal-vitals">${vitals}</div>
        </section>

        <section class="journal-section">
          <h2 class="journal-section-title">${isZh ? "工作台体征" : "Workbench vitals"}</h2>
          <div class="journal-vitals">${engine}</div>
        </section>

        <section class="journal-section">
          <h2 class="journal-section-title">${isZh ? `最近 ${commits.length} 次提交${ledgerCount ? `（其中 ${ledgerCount} 次携带批次号）` : ""}` : `Last ${commits.length} commits${ledgerCount ? ` — ${ledgerCount} tagged by the ledger` : ""}`}</h2>
          <p class="journal-section-note">${isZh ? "今天落在" : "Today sits on"} <strong>${escapeHtml(head)}</strong>${isZh ? "。今天新落地的提交会高亮。" : ". Commits shipped today are highlighted."}</p>
          <ul class="journal-commits">${commitRows || `<li class="journal-empty">${escapeHtml(isZh ? "（暂无提交）" : "(no commits yet)")}</li>`}</ul>
        </section>

        <p class="journal-quote">${isZh ? "“这个仓库每次推送，就是一次验收。”" : "“Every push to this repository is a gate the work must walk through.”"}</p>
      </div>
    </div>`;
}

export async function openJournalPanel() {
  const current = beginPanelRequest(t("journal.title"));
  try {
    const [digest, stats, metrics] = await Promise.all([
      requestJson("/api/digest").catch(() => null),
      requestJson("/api/stats").catch(() => null),
      requestJson("/api/metrics").catch(() => null),
    ]);
    openPanel(t("journal.title"), `<div class="journal-shell"><div id="journalCanvas">${render(digest, stats, metrics)}</div></div>`, { wide: true });
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(t("journal.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
