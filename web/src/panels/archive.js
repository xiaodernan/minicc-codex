/* ============================================================
   Minicc Archive — the ledger as it looks when you walk through it.

   Every batch heading in docs/ROADMAP_TO_PRODUCT.md, parsed once
   per panel open by /api/roadmap, rendered as a museum timeline.
   Search is client-side; nothing is sent back; nothing is
   mutated. Both languages, no mixed chrome.
   ============================================================ */

import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";

const zh = () => state.locale === "zh";

function eraLabel(from, to) {
  return zh() ? `批次 ${from} · ${to}` : `Batches ${from} · ${to}`;
}

function statsLine(total, firstBatch, latestBatch) {
  const isZh = zh();
  return isZh
    ? `${total} 章 · ${firstBatch} 到 ${latestBatch} 号 · 每章都是一次推进`
    : `${total} chapters · ${firstBatch} through ${latestBatch} · every chapter is one push`;
}

function entryRow(entry) {
  const tag = entry.id ? `<span class="archive-tag">${escapeHtml(entry.id)}</span>` : "";
  return `<li class="archive-entry"><span class="archive-batch">#${escapeHtml(String(entry.batch))}</span>${tag}<span class="archive-title">${escapeHtml(entry.title)}</span></li>`;
}

function renderArchive(slot, payload) {
  const isZh = zh();
  const entries = Array.isArray(payload?.entries) ? payload.entries : [];
  const total = payload?.total ?? entries.length;
  const firstBatch = total ? Math.min(...entries.map((e) => e.batch)) : 0;
  const latestBatch = total ? Math.max(...entries.map((e) => e.batch)) : 0;
  const eras = Array.isArray(payload?.eras) ? payload.eras : [];

  const eraSections = eras.map((era) => {
    const inEra = entries.filter((e) => e.batch >= era.from && e.batch <= era.to);
    return `<section class="archive-era">
      <div class="archive-era-head"><span class="archive-era-label">${escapeHtml(eraLabel(era.from, era.to))}</span><span class="archive-era-count">${era.count}</span></div>
      <ul class="archive-timeline">${inEra.map(entryRow).join("")}</ul>
    </section>`;
  }).join("");

  slot.innerHTML = `
    <div class="archive-shell">
      <div class="archive-kicker">${escapeHtml(isZh ? "档案馆 · 记" : "The Archive")}</div>
      <h1 class="archive-title-top">${isZh ? "这个项目的<br/><span class=\"archive-title-accent\">每一步推上去。</span>" : "Every push<br/><span class=\"archive-title-accent\">this project ever took.</span>"}</h1>
      <p class="archive-stats">${escapeHtml(statsLine(total, firstBatch, latestBatch))}</p>
      <p class="archive-sidenote">${escapeHtml(isZh ? "更早的推进不采用本文件的章节格式：本馆从第 601 批还原；历史在前身《实施进度日志》里，不伪造完整度。" : "Earlier pushes did not use this file's chapter format — the archive is restored from batch 601 on; the history of the milestones lives in the predecessor progress log. Nothing is fabricated for completeness.")}</p>
      <input type="search" class="archive-search" placeholder="${escapeHtml(isZh ? "搜索章节、批次号或 M8-Txxxx…" : "Search batch, id or keyword…")}" aria-label="${escapeHtml(isZh ? "搜索档案馆" : "Search the archive")}" />
      <div class="archive-eras">${eraSections || `<div class="archive-empty">${escapeHtml(isZh ? "档案馆空空如也" : "The archive is empty")}</div>`}</div>
    </div>`;

  const search = slot.querySelector(".archive-search");
  const sections = [...slot.querySelectorAll(".archive-era")];
  search?.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    for (const section of sections) {
      let visible = 0;
      section.querySelectorAll(".archive-entry").forEach((row) => {
        const match = !query || row.textContent.toLowerCase().includes(query);
        row.hidden = !match;
        if (match) visible += 1;
      });
      section.hidden = query ? visible === 0 : false;
    }
  });
  search?.focus();
}

export async function openArchivePanel() {
  const current = beginPanelRequest(t("archive.title"));
  try {
    const payload = await requestJson("/api/roadmap").catch(() => null);
    openPanel(t("archive.title"), `<div id="archiveCanvas"><div class="archive-loading">${escapeHtml(zh() ? "正在翻开档案馆…" : "Opening the archive…")}</div></div>`, { wide: true });
    const slot = $("#archiveCanvas");
    if (!slot) return;
    renderArchive(slot, payload);
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(t("archive.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
