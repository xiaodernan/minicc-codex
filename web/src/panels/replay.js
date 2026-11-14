/* ============================================================
   Minicc Replay — 任务级"影片回放"。

   把一次已完成任务（intake → deliver）按事件顺序重新演一遍：
   事件逐行出现、tokens 累加动画、进度可拖拽、速度可调，
   让定稿的代码代理交付过程像角色一样被看见。纯前端渲染，
   数据来自 /api/tasks/<id>；没有事件的任务诚实地显示空态。
   ============================================================ */

import { compactModelUpdateEvents, compactNumber } from "./index.js";
import { escapeHtml } from "../chat/markdown.js";
import { t } from "../core/i18n.js";
import { icon, refreshIcons } from "../icons.js";
import { requestJson } from "../core/transport.js";

const MAX_ROWS = 60;
const DELAYS = { 1: 650, 2: 320, 4: 160 };

function tokenTotalOf(task) {
  const total = Number(task?.tokens_used?.total_tokens ?? task?.metrics?.budget?.tokens ?? 0);
  return Number.isFinite(total) ? Math.max(0, total) : 0;
}

function eventRow(event, index) {
  const code = String(event?.code ?? "") || String(event?.kind ?? "") || "event";
  const summary = String(event?.summary ?? event?.detail?.text ?? "").trim();
  const kind = String(event?.kind ?? "");
  const tone = kind === "status" || kind === "result" ? "status" : kind === "usage" ? "usage" : "step";
  return `<li class="replay-row replay-row-${tone}" style="--row-index:${index}"><span class="replay-row-index">#${String(index + 1).padStart(2, "0")}</span><code class="replay-row-code">${escapeHtml(code)}</code><span class="replay-row-text">${escapeHtml(summary)}</span></li>`;
}

export function openReplayView(task, onBack) {
  const events = compactModelUpdateEvents(Array.isArray(task.events) ? task.events : []);
  const totalTokens = tokenTotalOf(task);
  const capped = events.length > MAX_ROWS ? events.slice(-MAX_ROWS) : events;
  const rows = capped.length
    ? capped.map((event, index) => eventRow(event, index)).join("")
    : `<li class="replay-row replay-row-empty"><span class="replay-row-text">${escapeHtml(t("replay.empty"))}</span></li>`;
  const title = String(task.preview || task.prompt || task.task_id || "").slice(0, 90);
  const total = capped.length;

  const overlay = document.createElement("div");
  overlay.className = "replay-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", t("replay.aria"));
  overlay.innerHTML = `
    <header class="replay-head">
      <div class="replay-head-copy">
        <span class="replay-kicker">REPLAY · ${escapeHtml(String(task.task_id ?? ""))}</span>
        <h2 class="replay-title">${escapeHtml(title)}</h2>
        <div class="replay-sub">${compactNumber(totalTokens)} ${escapeHtml(t("replay.tokens"))} · ${escapeHtml(t("replay.rows"))}: ${total}</div>
      </div>
      <div class="replay-head-actions">
        <button type="button" class="panel-secondary" data-replay-action="back">${icon("arrow-left")} ${escapeHtml(t("replay.back"))}</button>
        <button type="button" class="icon-button" aria-label="${escapeHtml(t("replay.close"))}" data-replay-action="close">${icon("x")}</button>
      </div>
    </header>
    <div class="replay-stage">
      <ol class="replay-log" id="replayLog">${rows}</ol>
      <aside class="replay-side" aria-hidden="true">
        <div class="replay-big" id="replayTokens">0</div>
        <div class="replay-label">${escapeHtml(t("replay.tokensLive"))}</div>
        <div class="replay-turn"><span id="replayStep">0</span><span class="replay-turn-total">/ ${total}</span></div>
        <div class="replay-label">${escapeHtml(t("replay.progress"))}</div>
        <div class="replay-stamp" id="replayStamp" hidden>${icon("check-circle-2")} ${escapeHtml(t("replay.done"))}</div>
      </aside>
    </div>
    <footer class="replay-foot">
      <button type="button" class="replay-play" id="replayPlayButton" data-replay-action="toggle" aria-label="${escapeHtml(t("replay.toggle"))}">${icon("play")}</button>
      <input type="range" class="replay-scrub" id="replayScrub" min="0" max="${total}" value="0" step="1" aria-label="${escapeHtml(t("replay.scrub"))}">
      <button type="button" class="replay-speed" data-replay-action="speed" id="replaySpeed">1×</button>
      <div class="replay-count"><span id="replayCount">0</span> / ${total}</div>
    </footer>
  `;
  document.body.appendChild(overlay);
  refreshIcons();

  const log = overlay.querySelector("#replayLog");
  const rowsEl = [...log.querySelectorAll(".replay-row")];
  const tokensEl = overlay.querySelector("#replayTokens");
  const stepEl = overlay.querySelector("#replayStep");
  const countEl = overlay.querySelector("#replayCount");
  const stampEl = overlay.querySelector("#replayStamp");
  const scrubEl = overlay.querySelector("#replayScrub");
  const playButton = overlay.querySelector("#replayPlayButton");
  const speedButton = overlay.querySelector("#replaySpeed");

  let index = 0;
  let playing = true;
  let speed = 1;
  let timer = null;

  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

  function paint(through) {
    rowsEl.forEach((row, rowIndex) => {
      row.classList.toggle("replay-row-visible", rowIndex < through);
    });
    const fraction = total > 0 ? through / total : 0;
    tokensEl.textContent = compactNumber(Math.round(totalTokens * fraction));
    stepEl.textContent = String(through);
    countEl.textContent = String(through);
    scrubEl.value = String(through);
    if (through >= total) stampEl.hidden = false;
    else stampEl.hidden = true;
    const last = log.querySelector(".replay-row-visible:last-child");
    if (last && !reducedMotion) last.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function clearTimer() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function setPlaying(next) {
    playing = next;
    playButton.innerHTML = playing ? icon("pause") : icon("play");
    refreshIcons();
    clearTimer();
    if (!playing) return;
    timer = setInterval(() => {
      if (index >= total) {
        clearTimer();
        playButton.innerHTML = icon("rotate-ccw");
        refreshIcons();
        playing = false;
        return;
      }
      index += 1;
      paint(index);
    }, DELAYS[speed]);
  }

  function close() {
    clearTimer();
    document.removeEventListener("keydown", onKeydown, true);
    overlay.remove();
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  }
  document.addEventListener("keydown", onKeydown, true);

  overlay.addEventListener("click", (event) => {
    const target = event.target.closest("[data-replay-action]");
    if (!target) return;
    const action = target.getAttribute("data-replay-action");
    if (action === "close") close();
    else if (action === "back") {
      close();
      if (typeof onBack === "function") onBack();
    } else if (action === "toggle") {
      if (index >= total && !playing) {
        index = 0;
        paint(0);
        setPlaying(true);
        return;
      }
      setPlaying(!playing);
    } else if (action === "speed") {
      speed = speed === 1 ? 2 : speed === 2 ? 4 : 1;
      speedButton.textContent = `${speed}×`;
      if (playing) setPlaying(true);
    }
  });

  scrubEl.addEventListener("input", () => {
    clearTimer();
    playing = false;
    playButton.innerHTML = icon("play");
    refreshIcons();
    index = Number(scrubEl.value) || 0;
    paint(index);
  });

  paint(0);
  setPlaying(total > 0);
  playButton.focus({ preventScroll: true });
}

/** Detail-modal entry point: fetch the task and open the replay overlay. */
export async function openReplayForTask(taskId, onBack) {
  const task = await requestJson(`/api/tasks/${encodeURIComponent(String(taskId ?? ""))}`);
  openReplayView(task, onBack);
}
