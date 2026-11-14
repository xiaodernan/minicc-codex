/* ============================================================
   Minicc Tour — two minutes, six steps, zero reading required.

   A first-run product tour for the workbench. Spotlight what each
   area is for, explain it in one sentence, finish. Skippable at
   any point with Esc; re-openable any time from the command
   palette ("tour") — the seen-once choice is remembered per
   browser. Fully bilingual.
   ============================================================ */

import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { showToast } from "../panels/index.js";

const SEEN_KEY = "minicc-tour-v1";
const zh = () => state.locale === "zh";

const STEPS = [
  {
    id: "welcome", anchor: null,
    zh: { kicker: "上手演练 · 第 1 / 6 步", title: "欢迎来到 minicc", body: "本地优先的编程智能体工作台。接下来两分钟我会带你看六个地方。Esc 可随时退出；⌘K 里搜「tour」可随时再来。" },
    en: { kicker: "Start here · Step 1 of 6", title: "Welcome to minicc", body: "The local-first coding workbench. The next two minutes take you past six places worth knowing. Esc exits anytime; search “tour” in the palette to come back." },
  },
  {
    id: "sidebar", anchor: "#sidebar",
    zh: { kicker: "上手演练 · 第 2 / 6 步", title: "左侧是这台机器的控台", body: "任务、活动、账本、模板、说明书、年鉴、铁律、日志、档案馆——产品的全部面板都从这里打开，中文英文两套版本永远同时有效。" },
    en: { kicker: "Start here · Step 2 of 6", title: "The left rail is the control deck", body: "Tasks, activity, ledger, templates, manual, almanac, axioms, journal, archive — every panel of the product opens from here, in Chinese or English, always in parity." },
  },
  {
    id: "composer", anchor: "#promptInput",
    zh: { kicker: "上手演练 · 第 3 / 6 步", title: "说人话就行", body: "试试写一次「读一下 README.md 然后告诉我这个项目是干嘛的」——回车发送。它会真的读文件、真的跑工具、把带证据的答案交回给你。" },
    en: { kicker: "Start here · Step 3 of 6", title: "Just say what you want", body: "Try typing “Read README.md and tell me what this project does” and press Enter. It will actually read the files, actually run the tools, and hand you an evidence-backed answer." },
  },
  {
    id: "demo", anchor: "#demoFlowButton",
    zh: { kicker: "上手演练 · 第 4 / 6 步", title: "不想打字？看它现场演一次", body: "点「演示流程」，60 秒看它完整跑一遍：计划 → 工具调用 → 验证 → 交付总结。亲眼看完，你就会用了。" },
    en: { kicker: "Start here · Step 4 of 6", title: "Prefer to watch?", body: "Hit “Demo flow” and watch a full pass in sixty seconds: plan → tools → verification → delivery. See it once and you know the product." },
  },
  {
    id: "almanac", anchor: ".nav-item[data-view=\"almanac\"]",
    zh: { kicker: "上手演练 · 第 5 / 6 步", title: "年鉴：这个项目的博物馆", body: "卷一到卷九的博物馆级叙事，数字全部来自真实仓库读数；「说明书」则负责怎么玩、怎么排错、边界在哪——两个地方都值得读一遍。" },
    en: { kicker: "Start here · Step 5 of 6", title: "The Almanac — a museum in nine halls", body: "Nine chapters of museum-grade narrative, every figure read live from this repository. The Manual covers how to play, how to debug, and where the honest limits are." },
  },
  {
    id: "done", anchor: null,
    zh: { kicker: "上手演练 · 第 6 / 6 步", title: "好了，你可以了", body: "自己发一条任务试试；遇事按「？」看快捷键；遇事不会按⌘K 搜一切。欢迎来到 minicc。" },
    en: { kicker: "Start here · Step 6 of 6", title: "That's it, you know it now", body: "Send your first real task next. Whenever you're stuck, press “?” for the shortcut reference — or “⌘/Ctrl K” to search everything. Welcome to minicc." },
  },
];

const L = (key) => (zh() ? STEPS_BY_ID(key).zh : STEPS_BY_ID(key).en);

function STEPS_BY_ID(id) {
  return STEPS.find((step) => step.id === id);
}

function stepIndex(step) {
  return STEPS.findIndex((s) => s.id === step);
}

const $tour = {};
const $overlayParts = () => ({
  overlay: $tour.overlay,
  spot: $tour.spot,
  card: $tour.card,
});

function rectFor(selector) {
  const node = selector ? document.querySelector(selector) : null;
  if (!node) return null;
  const rect = node.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return null;
  return rect;
}

function positionSpotlight(rect) {
  const { spot } = $overlayParts();
  if (!spot) return;
  if (!rect) {
    spot.hidden = true;
    return;
  }
  spot.hidden = false;
  const pad = 10;
  spot.style.left = `${Math.max(0, rect.left - pad)}px`;
  spot.style.top = `${Math.max(0, rect.top - pad)}px`;
  spot.style.width = `${rect.width + pad * 2}px`;
  spot.style.height = `${rect.height + pad * 2}px`;
}

function renderStep(index) {
  const { overlay, card } = $overlayParts();
  const step = STEPS[index];
  const local = zh() ? step.zh : step.en;
  const rect = rectFor(step.anchor);
  positionSpotlight(rect);

  card.querySelector(".tour-step").textContent = local.kicker;
  card.querySelector(".tour-title").textContent = local.title;
  card.querySelector(".tour-body").textContent = local.body;
  const back = card.querySelector(".tour-back");
  const next = card.querySelector(".tour-next");
  back.hidden = index === 0;
  back.textContent = zh() ? "上一步" : "Back";
  next.textContent = index === STEPS.length - 1
    ? (zh() ? "开始干活" : "Start building")
    : (zh() ? "下一步" : "Next");
  const skip = card.querySelector(".tour-skip");
  skip.textContent = zh() ? "跳过" : "Skip tour";
  refreshIcons();
}

function teardown(outcome) {
  const { overlay } = $overlayParts();
  if (!overlay) return;
  overlay.remove();
  $tour.overlay = null;
  $tour.spot = null;
  $tour.card = null;
  $tour.currentStep = null;
  if (outcome === "done") {
    try { localStorage.setItem(SEEN_KEY, "done"); } catch {}
    showToast(zh() ? "辛苦了——去做点真事吧" : "You're ready — go build something real");
  } else if (outcome === "skipped") {
    try { localStorage.setItem(SEEN_KEY, "skipped"); } catch {}
  }
  window.removeEventListener("resize", reposition, true);
  window.removeEventListener("keydown", onKeydown, true);
}

function reposition() {
  if ($tour.currentStep == null) return;
  positionSpotlight(rectFor(STEPS[$tour.currentStep].anchor));
}

function finish() {
  teardown("done");
}

function next() {
  $tour.currentStep += 1;
  if ($tour.currentStep >= STEPS.length) {
    finish();
    return;
  }
  renderStep($tour.currentStep);
}

function back() {
  if ($tour.currentStep <= 0) return;
  $tour.currentStep -= 1;
  renderStep($tour.currentStep);
}

function onKeydown(event) {
  if (event.key === "Escape") {
    event.preventDefault();
    teardown("skipped");
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    next();
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    back();
  }
}

export function startTour() {
  if ($("#tourOverlay")) return;
  const overlay = document.createElement("div");
  overlay.id = "tourOverlay";
  overlay.setAttribute("role", "presentation");
  overlay.innerHTML = `
    <div class="tour-dim"></div>
    <div class="tour-spot" hidden></div>
    <div class="tour-card" role="dialog" aria-modal="true" aria-label="${escapeHtmlAttr(zh() ? "上手演练" : "Product tour")}">
      <div class="tour-step"></div>
      <h3 class="tour-title"></h3>
      <p class="tour-body"></p>
      <div class="tour-actions">
        <button type="button" class="tour-skip"></button>
        <div class="tour-nav">
          <button type="button" class="tour-back"></button>
          <button type="button" class="tour-next"></button>
        </div>
      </div>
    </div>`;
  document.body.append(overlay);
  $tour.overlay = overlay;
  $tour.spot = overlay.querySelector(".tour-spot");
  $tour.card = overlay.querySelector(".tour-card");
  $tour.currentStep = 0;

  overlay.querySelector(".tour-skip").addEventListener("click", () => teardown("skipped"));
  overlay.querySelector(".tour-back").addEventListener("click", back);
  overlay.querySelector(".tour-next").addEventListener("click", next);
  window.addEventListener("resize", reposition, true);
  window.addEventListener("keydown", onKeydown, true);
  renderStep(0);
}

function escapeHtmlAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

export function maybeOfferTour() {
  if (localStorage.getItem(SEEN_KEY)) return;
  if ($("#tourOffer")) return;
  if (window.innerWidth < 900) return;
  const button = document.createElement("button");
  button.type = "button";
  button.id = "tourOffer";
  button.className = "tour-offer";
  button.innerHTML = `<i data-lucide="sparkles"></i><span>${escapeHtmlAttr(zh() ? "第一次来？2 分钟带你过一遍" : "First visit? Two minutes, I've got you")}</span>`;
  document.body.append(button);
  button.addEventListener("click", () => {
    button.remove();
    startTour();
  });
  refreshIcons();
}
