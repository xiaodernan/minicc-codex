/* ============================================================
   Minicc Recent — the project's own release feed, in itself.

   A slim, honest panel: the last fifteen batch chapters this
   repository shipped, read live from /api/roadmap. Every entry
   is verbatim from the ledger. The footer deep-links into the
   Archive for the full timeline. Both languages; the ledger
   prose is user data and stays verbatim (not translated).
   ============================================================ */

import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";
import { openArchivePanel } from "./archive.js";
import { showToast } from "../panels/index.js";

const zh = () => state.locale === "zh";
const LIMIT = 15;

function entryRow(entry, index) {
  const tag = entry.id ? `<span class="recent-tag">${escapeHtml(entry.id)}</span>` : "";
  const fresh = index === 0 ? " recent-entry-fresh" : "";
  return `<li class="recent-entry${fresh}"><span class="recent-batch">#${escapeHtml(String(entry.batch))}</span>${tag}<span class="recent-title">${escapeHtml(entry.title)}</span></li>`;
}

function render(digest, roadmap) {
  const isZh = zh();
  const entries = Array.isArray(roadmap?.entries) ? roadmap.entries : [];
  const newest = [...entries]
    .sort((a, b) => (b.batch || 0) - (a.batch || 0))
    .slice(0, LIMIT);
  const total = roadmap?.total ?? entries.length;
  const tests = digest?.test_files != null ? String(digest.test_files) : "—";
  const head = digest?.head_short ? `main @ ${digest.head_short}` : "main";
  const branch = digest?.branch ? `${digest.branch}${digest.head_short ? ` @ ${digest.head_short}` : ""}` : "—";

  const rows = newest.map((entry, index) => entryRow(entry, index)).join("");

  return `
    <div class="recent-canvas">
      <div class="recent-kicker">${escapeHtml(isZh ? "近况 · 最近交付" : "Recent deliveries")}</div>
      <h1 class="recent-title-top">${isZh ? "最新" : "The last"}<span class="recent-title-accent"> ${escapeHtml(String(newest.length))} ${isZh ? "批" : "batches"}</span>${isZh ? "，现场读取" : ", read live"}</h1>
      <div class="recent-meta">
        <span class="recent-meta-item"><strong>${escapeHtml(String(total))}</strong> ${escapeHtml(isZh ? "批次" : "batches")}</span>
        <span class="recent-meta-item"><strong>${escapeHtml(tests)}</strong> ${escapeHtml(isZh ? "个测试文件" : "test files")}</span>
        <span class="recent-meta-item"><strong>${escapeHtml(branch)}</strong></span>
      </div>
      <ol class="recent-list">${rows || `<li class="recent-empty">${escapeHtml(isZh ? "（档案馆空空如也）" : "(the archive is empty)")}</li>`}</ol>
      <div class="recent-foot">
        <p>${escapeHtml(isZh ? "章节原文 /api/roadmap 现读取，内容不加改造。" : "Chapter titles are verbatim from /api/roadmap — never rewritten.")}</p>
        <button type="button" class="recent-footer-button" id="recentOpenArchive">${escapeHtml(isZh ? `打开档案馆，看全部 ${total} 章 →` : `Open the Archive, all ${total} chapters →`)}</button>
      </div>
    </div>`;
}

export async function openRecentPanel() {
  const current = beginPanelRequest(t("recent.title"));
  try {
    const [digest, roadmap] = await Promise.all([
      requestJson("/api/digest").catch(() => null),
      requestJson("/api/roadmap").catch(() => null),
    ]);
    openPanel(t("recent.title"), render(digest, roadmap), { wide: true });
    $("#recentOpenArchive")?.addEventListener("click", () => openArchivePanel());
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(t("recent.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
