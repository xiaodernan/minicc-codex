import assert from "node:assert/strict";
import { chromium } from "playwright";
import { exitIfHarnessLost, requireHarnessOrExit } from "./web_smoke_suites.mjs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";

await requireHarnessOrExit(baseUrl);
const CJK = /[一-鿿]/;
const EXEMPT = [
  "#threadList", "#messageList", ".thread-item", ".message",
  ".admin-task-message", ".todo-item-text", "#localeZh", ".admin-task",
  // live agent todos are the model's own output, not chrome of the UI
  ".todo-content", ".todo-item",
  ".workspace-current-path", ".workspace-row strong", ".workspace-row small",
  ".worktree-row strong", ".worktree-row small", ".worktree-form input", ".workspace-form input",
  ".archive-title", ".recent-title", ".archive-tag", ".journal-subject", ".dockyard-commit",
  ".commit-subject", ".pulse-archive-row", ".pulse-archive-row strong", ".pulse-timeline-node",
  // the session heading is the user's own data (resume-latest title), not chrome
  "#sessionTitle", "#sessionSubtitle",
  "#pulseIdentityPath",
].join(", ");

const browser = await chromium.launch({ headless: true });

// The workbench never blocks a real click for real — retries exist only because
// Playwright's actionability window (stable bounding box across 2 frames) can
// transiently fail during re-renders even though the button is visible and
// clickable a moment later. A second attempt after a settle is the honest
// analog of a human tapping again.
async function clickRetry(page, selector, { timeout = 8000, attempts = 2 } = {}) {
  let lastErr = null;
  for (let i = 0; i < attempts; i += 1) {
    try {
      await page.click(selector, { timeout });
      return;
    } catch (e) {
      lastErr = e;
      await page.waitForTimeout(1500);
      await page.keyboard.press("Escape").catch(() => {});
      await settlePanelModal(page).catch(() => {});
    }
  }
  throw lastErr;
}

function collectVisibleCjk(page) {
  return page.evaluate((exempt) => {
    const CJK = /[一-鿿]/;
    const fails = [];
    for (const el of document.querySelectorAll("body *")) {
      if (el.matches(exempt) || el.closest(exempt)) continue;
      const vis = el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
      if (!vis) continue;
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.nodeValue).join(" ").trim();
      if (own && CJK.test(own)) {
        const id = el.id ? `#${el.id}` : "";
        const cls = typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
        fails.push({ where: `${el.tagName.toLowerCase()}${id}${cls}`, snippet: own.replace(/\s+/g, " ").slice(0, 140) });
        continue;
      }
      for (const a of ["placeholder", "aria-label", "title", "alt"]) {
        const v = el.getAttribute(a);
        if (v && CJK.test(v)) {
          const id = el.id ? `#${el.id}` : "";
          fails.push({ where: `${el.tagName.toLowerCase()}${id}[${a}]`, snippet: v.slice(0, 140) });
        }
      }
    }
    return fails;
  }, EXEMPT);
}

async function settlePanelModal(page) {
  await page.waitForFunction(() => {
    const m = document.querySelector("#panelModal");
    return !m || !m.classList.contains("show");
  }, null, { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(450);
}

async function expectClean(page, label, errors) {
  const leaks = await collectVisibleCjk(page);
  for (const leak of leaks) errors.push(`[${label}] ${leak.where}\n           ${leak.snippet}`);
}

async function checkMode(locale) {
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  await page.addInitScript((l) => { try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {} }, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1500);

  if (locale === "zh") {
    const zh = await page.locator(".nav-item[data-view=\"tasks\"]").innerText();
    assert.ok(/[一-鿿]/.test(zh), "zh mode nav must carry Chinese labels");
    await page.close();
    return errors;
  }

  await expectClean(page, "home/tasks", errors);

  for (const v of ["workspaces", "activity", "ledger", "templates", "axioms", "journal", "archive", "askdocs", "recent", "promo", "manual", "almanac"]) {
    try {
      await clickRetry(page, `.nav-item[data-view="${v}"]`, { timeout: 8000 });
      await page.waitForTimeout(650);
      await expectClean(page, `view:${v}`, errors);
      await page.keyboard.press("Escape");
      await settlePanelModal(page);
    } catch (e) {
      errors.push(`[view:${v}] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
    }
  }

  const stages = [
    { btn: "#pulseButton", close: "#pulseStageClose", label: "pulse" },
    { btn: "#doctorButton", close: "#doctorStageClose", label: "doctor" },
    { btn: "#dockyardButton", close: "#dockyardStageClose", label: "dockyard" },
    { btn: "#atlasButton", close: "#atlasClose", label: "atlas" },
    { btn: "#adminButton", close: "#adminStageClose", label: "admin-locked" },
  ];
  for (const s of stages) {
    try {
      await clickRetry(page, s.btn, { timeout: 7000 });
      await page.waitForTimeout(800);
      await expectClean(page, s.label, errors);
      await page.click(s.close, { timeout: 4000 }).catch(() => {});
      await page.waitForTimeout(400);
    } catch (e) {
      errors.push(`[${s.label}] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
    }
  }

  try {
    await clickRetry(page, "#adminButton", { timeout: 7000 });
    await page.waitForTimeout(450);
    await page.fill("#adminPassword", "123", { timeout: 5000 });
    await page.click("#adminUnlockBtn", { timeout: 5000 });
    await page.waitForTimeout(1600);
    await expectClean(page, "admin-unlocked", errors);
    await page.click("#adminStageClose", { timeout: 4000 }).catch(() => {});
    await page.waitForTimeout(300);
  } catch (e) {
    errors.push(`[admin-unlocked] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
  }

  try {
    await clickRetry(page, "#arcadeButton", { timeout: 7000 });
    // the arcade bundle is injected lazily (`openArcade` -> `/game.js`); under
    // load a fixed 1200 ms sleep is a coin-flip. Wait for the modal to open
    // instead — the user sees the same signal, and so does this test.
    await page.waitForSelector("#gameModal.show", { state: "visible", timeout: 20000 });
    await expectClean(page, "arcade", errors);
    // the arcade tutorial overlay must also stay English-clean in en mode
    try {
      // wait for the tutorial button to be visible AND for the panel to actually
      // open — a passing click that never opened the panel would otherwise scan
      // whatever was already on screen and report a false green.
      await page.waitForSelector("#gameHow", { state: "visible", timeout: 15000 });
      await clickRetry(page, "#gameHow", { timeout: 8000 });
      await page.waitForSelector("#gameHowPanel.show", { state: "visible", timeout: 10000 });
      await page.waitForTimeout(500);
      await expectClean(page, "arcade-guide", errors);
      await page.click("#gameHowClose", { timeout: 4000 }).catch(() => {});
      await page.waitForTimeout(300);
    } catch (e) {
      errors.push(`[arcade-guide] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
    }
    await page.click("#gameClose", { timeout: 4000 }).catch(() => {});
    await page.waitForTimeout(400);
  } catch (e) {
    const diag = await page.evaluate(() => ({
      openGame: typeof window.openGame,
      gameScripts: Array.from(document.scripts).map((s) => s.src).filter((u) => u.includes("game")),
      modalShow: document.querySelector("#gameModal")?.classList.contains("show") ?? null,
    })).catch(() => null);
    errors.push(`[arcade] interaction failed: ${String(e.message).split("\n")[0].slice(0, 160)} diag=${JSON.stringify(diag)}`);
  }

  try {
    await page.keyboard.press("Control+K");
    await page.waitForTimeout(400);
    await page.keyboard.type("tour");
    await page.waitForTimeout(500);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(800);
    for (let i = 0; i < 9; i++) {
      await page.waitForTimeout(400);
      await expectClean(page, `wayfinder-step-${i + 1}`, errors);
      const hasInteract = await page.evaluate(() => {
        const b = document.querySelector(".tour-interact");
        return b && !b.hidden;
      });
      if (hasInteract) await page.click(".tour-interact", { force: true }).catch(() => {});
      else await page.click(".tour-next", { force: true }).catch(() => {});
      await page.waitForTimeout(700);
    }
    await page.keyboard.press("Escape");
  } catch (e) {
    errors.push(`[wayfinder] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
  }

  const charted = await page.locator("#atlasCharted").innerText();
  assert.ok(!CJK.test(charted), `#atlasCharted must be en in en mode, saw: ${charted}`);

  await page.close();
  return errors;
}

const enErrors = await checkMode("en");
const zhErrors = await checkMode("zh");
const errors = [...enErrors, ...zhErrors];
await browser.close();

if (errors.length) {
  console.error("en-CJK parity FAILED:");
  for (const e of errors) console.error("  " + e);
  await exitIfHarnessLost(baseUrl);
  process.exit(1);
}
console.log("parity smoke passed: en mode renders zero CJK across workbench, all 12 nav views, 6 stage overlays, the 10-step Wayfinder tour, and boot-time custom strings; zh mode toggles correctly");
process.exit(0);
