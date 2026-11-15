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
const compact = (value) => {
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
const firstCommitDay = (iso) => {
  if (!iso || typeof iso !== "string") return "—";
  return iso.slice(0, 10);
};

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

function buildStakes(digest, metrics, pulse) {
  const isGit = !!digest?.is_git;
  const total = Number(digest?.total_commits ?? 0);
  const chapters = Number(digest?.almanac_chapters ?? 0);
  const tracked = Number(digest?.tracked_files ?? 0);
  const tests = Number(digest?.test_files ?? 0);
  const done = Number(metrics?.tasks_by_status?.completed ?? 0);
  const interrupted = Number(metrics?.tasks_by_status?.interrupted ?? 0);
  const tokens = Number(metrics?.usage?.total_tokens ?? 0);
  const cacheRate = Number(metrics?.llm_cache?.cache_hit_rate ?? 0);
  const stars = pulse?.live && pulse?.github ? Number(pulse.github.stars ?? 0) : null;

  const stake = (index, nameKey, hintKey, iconName, current, target, fmt) => {
    const ratio = target > 0 ? Math.max(0, Math.min(1, current / target)) : 0;
    return {
      index,
      nameKey,
      hintKey,
      iconName,
      current,
      target,
      ratio,
      fmt,
      unlocked: ratio >= 1 || current >= target,
    };
  };

  return [
    stake(1, "yard.stake1", "yard.stake1Hint", "compass", isGit && total > 0 ? 1 : 0, 1, () => "✓"),
    stake(2, "yard.stake2", "yard.stake2Hint", "anchor", total, 1000, (v) => String(Math.floor(v))),
    stake(3, "yard.stake3", "yard.stake3Hint", "map-scroll", chapters, 17, (v) => String(Math.floor(v))),
    stake(4, "yard.stake4", "yard.stake4Hint", "star", tracked, 1000, (v) => String(Math.floor(v))),
    stake(5, "yard.stake5", "yard.stake5Hint", "lighthouse", stars ?? 0, 1, (v) => (stars === null ? "—" : String(Math.floor(v)))),
    stake(6, "yard.stake6", "yard.stake6Hint", "shield-check", tests, 700, (v) => String(Math.floor(v))),
    stake(7, "yard.stake7", "yard.stake7Hint", "zap", cacheRate, 0.8, (v) => pct(v)),
    stake(8, "yard.stake8", "yard.stake8Hint", "timer", tokens, 1_000_000, (v) => compact(v)),
    stake(9, "yard.stake9", "yard.stake9Hint", "flame", interrupted, 1, (v) => String(Math.floor(v))),
    stake(10, "yard.stake10", "yard.stake10Hint", "anchor", 1, 1, () => "✓"),
  ];
}

function stakeMarkup(s, zhMode) {
  const unlocked = s.unlocked;
  const ratioPct = Math.round(s.ratio * 100);
  const bar = unlocked ? 100 : ratioPct;
  const valueText = s.fmt(s.current);
  const statusText = unlocked ? t("yard.unlocked") : t("yard.locked");
  return `
    <li class="dockyard-stake ${unlocked ? "unlocked" : "locked"}">
      <span class="dockyard-stake-roman">${ROMAN[s.index - 1]}</span>
      <span class="dockyard-stake-icon" aria-hidden="true">${icon(s.iconName)}</span>
      <span class="dockyard-stake-body">
        <span class="dockyard-stake-name">${esc(t(s.nameKey))}</span>
        <span class="dockyard-stake-hint">${esc(t(s.hintKey))}</span>
        <span class="dockyard-stake-bar" aria-hidden="true"><i style="width:${bar}%"></i></span>
      </span>
      <span class="dockyard-stake-side">
        <strong>${esc(valueText)}</strong>
        <small>${esc(statusText)}</small>
      </span>
    </li>
  `;
}

export async function openDockyard() {
  const modal = $("#dockyardStage");
  if (!modal) return;
  modal.setAttribute("aria-hidden", "false");
  const close = $("#dockyardStageClose");
  if (close) close.onclick = () => modal.setAttribute("aria-hidden", "true");
  refreshIcons();

  const [digest, metrics, pulse] = await Promise.all([
    requestJson("/api/digest", {}, 20000).catch(() => null),
    requestJson("/api/metrics", {}, 15000).catch(() => null),
    requestJson("/api/worldpulse", {}, 8000).catch(() => null),
  ]);

  const firstCommit = $("#yardFirstCommit");
  const totalCommits = $("#yardTotalCommits");
  const tasksDone = $("#yardTasksDone");
  const chapters = $("#yardChapters");
  const totalTokens = $("#yardTotalTokens");
  const cacheRate = $("#yardCacheRate");

  if (firstCommit) firstCommit.textContent = firstCommitDay(digest?.first_commit_at);
  if (totalCommits) totalCommits.textContent = digest?.total_commits != null ? String(digest.total_commits) : "—";
  const done = Number(metrics?.tasks_by_status?.completed ?? 0);
  const totalTasks = Number(metrics?.task_count ?? 0);
  if (tasksDone) tasksDone.textContent = totalTasks > 0 ? `${done} / ${totalTasks}` : String(done || "—");
  if (chapters) chapters.textContent = digest?.almanac_chapters != null ? String(digest.almanac_chapters) : "—";
  if (totalTokens) totalTokens.textContent = metrics?.usage?.total_tokens != null ? compact(metrics.usage.total_tokens) : "—";
  if (cacheRate) cacheRate.textContent = pct(metrics?.llm_cache?.cache_hit_rate);

  const stakes = buildStakes(digest, metrics, pulse);
  const list = $("#dockyardStakes");
  if (list) {
    list.innerHTML = stakes.map((stake) => stakeMarkup(stake, zh())).join("");
  }
  refreshIcons();
}
