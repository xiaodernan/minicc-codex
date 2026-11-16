/* ============================================================
   Minicc Tour — two minutes, six steps, zero reading required.
   M8-T989: rewrite of the onboarding for a learning-by-doing
   product: mojibake fixed, actual interactive steps (the tour can
   fill the composer and run the demo flow for the user), correct
   chapter counts, fully bilingual. Esc exits; re-openable any time
   from the palette ("tour"); seen-once choice is per browser.
   ============================================================ */

import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { showToast } from "../panels/index.js";
import { runDemoFlow } from "../chat/stream.js";

const SEEN_KEY = "minicc-tour-v1";
const zh = () => state.locale === "zh";

const STEPS = [
  {
    id: "welcome", anchor: null,
    zh: { kicker: "上手演练 · 第 1 步 / 共 10 步", title: "欢迎来到 minicc", body: "一个本地优先的编程智能体工作台。接下来两分钟内，我会带你走过十个地方，每一站都可以动手。Esc 随时退出；⌘K 搜「tour」随时再来。" },
    en: { kicker: "Start here · Step 1 of 10", title: "Welcome to minicc", body: "The local-first coding workbench. The next two minutes take you past ten places — each one is hands-on. Esc exits anytime; search “tour” in the palette to come back." },
  },
  {
    id: "sidebar", anchor: "#sidebar",
    zh: { kicker: "上手演练 · 第 2 步 / 共 10 步", title: "左侧是这台机器的控台", body: "任务、活动、账本、模板、说明书、年鉴、铁律、日志、档案馆——产品的所有面板都从这里打开，而且中文英文两套版本永远同时有效。" },
    en: { kicker: "Start here · Step 2 of 10", title: "The left rail is the control deck", body: "Tasks, activity, ledger, templates, manual, almanac, axioms, journal, archive — every panel opens from here, in Chinese and English, at parity." },
  },
  {
    id: "composer", anchor: "#promptInput", interact: "composer",
    zh: { kicker: "上手演练 · 第 3 步 / 共 10 步", title: "说人话就行", body: "试试写一次「读一下 README.md 然后告诉我这个项目是干嘛的」——回车发送，它会真的读文件、真的跑工具、把带证据的答案交回给你。" },
    en: { kicker: "Start here · Step 3 of 10", title: "Just say what you want", body: "Try “Read README.md and tell me what this project does” — press Enter. It will really read the files, really run tools, and hand you an evidence-backed answer." },
  },
  {
    id: "demo", anchor: "#demoFlowButton", interact: "demo",
    zh: { kicker: "上手演练 · 第 4 步 / 共 10 步", title: "不想打字？看它现场演一遍", body: "点「演示流程」，60 秒看它完整跑一遍：计划 → 工具调用 → 验证 → 交付总结。亲眼看完，你就会用了。" },
    en: { kicker: "Start here · Step 4 of 10", title: "Prefer to watch?", body: "Hit “Demo flow” and watch a full pass in sixty seconds: plan → tools → verification → delivery. See it once and you know the product." },
  },
  {
    id: "atlas", anchor: "#atlasButton", interact: "atlas",
    zh: { kicker: "上手演练 · 第 5 步 / 共 10 步", title: "把这片世界摊开看一眼", body: "点「地图」，12 座岛屿、72 个坐标——18 个面板 + 39 卷年鉴卫星 + 15 章说明书。拖拽是驾驶，滚轮是缩放，点击是传送。点开过一个，那里就亮起琥珀色——这是你在这个世界里走过的路。" },
    en: { kicker: "Start here · Step 5 of 10", title: "Unfold the world", body: "Press the “Atlas” button: twelve islands, seventy-two real coordinates — 18 panes, 39 almanac satellites, fifteen manual chapters. Drag to navigate, wheel to zoom, click to teleport. Each place you visit glows amber." },
  },
  {
    id: "dockyard", anchor: "#dockyardButton", interact: "dockyard",
    zh: { kicker: "上手演练 · 第 6 步 / 共 10 步", title: "船厂：看看这艘船自己写过的账", body: "侧边栏「船厂」——每一次 git commit、每一份提交次数、每一次 LIVE metrics（首次提交日期、完成任务数、累计缓存亲和率），全部根据 git 元数据与 /api/digest 现场读。" },
    en: { kicker: "Start here · Step 6 of 10", title: "The Dockyard — your own ledger, live", body: "Sidebar “Dockyard”: six counters straight from real git + /api/digest — first-commit date, total commits, completed tasks, almanac chapters, cumulative tokens, cache affinity. Nothing is invented." },
  },
  {
    id: "admin", anchor: "#adminButton", interact: "admin",
    zh: { kicker: "上手演练 · 第 7 步 / 共 10 步", title: "管理员门 · 密码 123", body: "侧边栏最底那个「管理」锁形图标——密码 123。里面有真实统计 / 七日事件柱状图 / 线性预测 / 中断原因自动分桶 / 工具使用直方图，全部基于本工作区真实任务数据。" },
    en: { kicker: "Start here · Step 7 of 10", title: "Admin — password 123", body: "The lock-shaped “Admin” entry at the bottom of the sidebar: password 123. Inside you find live stats, a 7-day events bar chart, a least-squares trend forecast (an estimate, not a promise), interrupt-cause breakdown, and a tool-usage histogram — every number comes from real local tasks." },
  },
  {
    id: "arcade", anchor: "#arcadeButton", interact: "arcade",
    zh: { kicker: "上手演练 · 第 8 步 / 共 10 步", title: "小游戏？进来守一场花园", body: "侧边栏「小游戏」——Plants vs. Zombies 风格的塔防。里面有「教程」按钮（六步专属手册），告诉你先种太阳花再放防线；每一波都实时读你花园的节奏。种子是阳光，不是信仰。" },
    en: { kicker: "Start here · Step 8 of 10", title: "The Arcade, where the lawn bites back", body: "Sidebar “Arcade” — a Plants vs. Zombies tower defense. Inside there's a “Guide” button (a six-step field manual): grow economy first, then plant peashooters behind the wall-nuts. Sun is the currency, not prayers." },
  },
  {
    id: "almanac", anchor: '.nav-item[data-view="almanac"]',
    zh: { kicker: "上手演练 · 第 9 步 / 共 10 步", title: "年鉴：这个项目的博物馆", body: "卷一到卷三十九的博物馆级叙事，每笔数字全部来自真实仓库读数；「说明书」负责怎么玩、怎么排错、边界在哪——两个地方都值得读一遍。" },
    en: { kicker: "Start here · Step 9 of 10", title: "The Almanac — a museum in thirty-nine halls", body: "Thirty-nine chapters of museum-grade narrative; every figure is read live from this repository. The manual covers how to play, how to debug, and where the honest limits are." },
  },
  {
    id: "done", anchor: null,
    zh: { kicker: "上手演练 · 第 10 步 / 共 10 步", title: "好了，你可以出发了", body: "自己发一条任务试试；遇事按「？」看快捷键清单；遇事不会按 ⌘K 搜一切。欢迎来到 minicc。" },
    en: { kicker: "Start here · Step 10 of 10", title: "That's it, you know it now", body: "Send your first real task next. Whenever you get stuck, press “?” for the shortcut reference — or ⌘/Ctrl K to search everything. Welcome to minicc." },
  },
];

const $tour = {};
const $overlayParts = () => ({ overlay: $tour.overlay, spot: $tour.spot, card: $tour.card });

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

function performInteraction(id) {
  if (id === "composer") {
    const input = $("#promptInput");
    if (input) {
      input.value = zh() ? "读一下 README.md，然后告诉我这个项目是干嘛的" : "Read README.md and tell me what this project does";
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      showToast(zh() ? "已帮你填好这句话，回车发送即可" : "Filled it in for you — press Enter to send");
    }
    next();
    return;
  }
  if (id === "demo") {
    showToast(zh() ? "正在为你跑一遍演示…" : "Running the demo for you…");
    Promise.resolve()
      .then(() => runDemoFlow())
      .catch(() => {});
    next();
    return;
  }
  if (id === "atlas") {
    const btn = $("#atlasButton");
    if (btn) btn.click();
    next();
    return;
  }
  if (id === "dockyard") {
    const btn = $("#dockyardButton");
    if (btn) btn.click();
    next();
    return;
  }
  if (id === "admin") {
    const btn = $("#adminButton");
    if (btn) btn.click();
    next();
    return;
  }
  if (id === "arcade") {
    const btn = $("#arcadeButton");
    if (btn) btn.click();
    next();
    return;
  }
}

function renderStep(index) {
  const { overlay, card } = $overlayParts();
  if (!overlay || !card) return;
  const step = STEPS[index];
  const local = zh() ? step.zh : step.en;
  const rect = rectFor(step.anchor);
  positionSpotlight(rect);

  card.querySelector(".tour-step").textContent = local.kicker;
  card.querySelector(".tour-title").textContent = local.title;
  card.querySelector(".tour-body").textContent = local.body;
  const back = card.querySelector(".tour-back");
  const next = card.querySelector(".tour-next");
  const interact = card.querySelector(".tour-interact");
  back.hidden = index === 0;
  back.textContent = zh() ? "上一步" : "Back";
  next.textContent = index === STEPS.length - 1
    ? (zh() ? "开始工作" : "Start building")
    : (zh() ? "下一步" : "Next");
  const skip = card.querySelector(".tour-skip");
  skip.textContent = zh() ? "跳过" : "Skip tour";

  if (step.interact) {
    interact.hidden = false;
    const interactLabels = {
      composer: zh() ? "帮我填好这句话" : "Fill it in for me",
      demo: zh() ? "立即跑演示" : "Run the demo now",
      atlas: zh() ? "展开世界地图" : "Unfold the map",
      arcade: zh() ? "打开小游戏" : "Open the Arcade",
      dockyard: zh() ? "打开船厂" : "Open the dockyard",
      admin: zh() ? "打开管理员面板" : "Open admin panel",
    };
    interact.textContent = interactLabels[step.interact] ?? (zh() ? "继续" : "Continue");
  } else {
    interact.hidden = true;
  }
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
          <button type="button" class="tour-interact"></button>
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
  overlay.querySelector(".tour-interact").addEventListener("click", () => {
    performInteraction(STEPS[$tour.currentStep]?.id);
  });
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

export { STEPS };
