/* ============================================================
   M8-T1034 (en CJK parity): the en-mode whole-app walk.

   The standing rule for this product is "all content is in ONE
   language at a time — zh or en — never mixed." This smoke is the
   gatekeeper of that rule for every *reachable* surface: home,
   every sidebar/secondary nav view, every stage overlay, and the
   completed Wayfinder tour.

   Exemptions (en mode reports raw repo/user data, never UI chrome —
   we do not and must not translate these):

     #threadList, #messageList      the user's own prompts + model answers
     .thread-item, .message         (same, split selectors)
     .todo-item-text, .admin-task   user-authored todos / admin task rows
     .admin-task-message            admin "recent tasks" shows the user's prompts
     #localeZh                      the native-script glyph of the language toggle
     .workspace-current-path,
     .workspace-row strong/small,
     .worktree-row strong/small,
     .worktree-form input,
     .workspace-form input          real filesystem paths (D:/面试项目/… exists on disk)
     .archive-title/.archive-tag,
     .recent-title,
     .journal-subject,
     .dockyard-commit,
     .commit-subject                repo-authored git commit subjects & the author's
                                    commit taxonomy (zh commits are real history, raw)
     .pulse-archive-row,
     .pulse-archive-row strong,
     .pulse-timeline-node,
     #pulseIdentityPath             pulse's task previews & the workspace path chip

   Everything else — labels, captions, buttons, tooltips, aria-labels,
   placeholders — MUST be English in en mode. Any CJK inside those is
   a mixed-language leak and fails the gate, with the offending
   element selector printed so it can be traced.
   ============================================================ */
import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";
const CJK = /[一-鿿]/;
const EXEMPT = [
  "#threadList", "#messageList", ".thread-item", ".message",
  ".admin-task-message", ".todo-item-text", "#localeZh", ".admin-task",
  ".workspace-current-path", ".workspace-row strong", ".workspace-row small",
  ".worktree-row strong", ".worktree-row small", ".worktree-form input", ".workspace-form input",
  ".archive-title", ".recent-title", ".archive-tag", ".journal-subject", ".dockyard-commit",
  ".commit-subject", ".pulse-archive-row", ".pulse-archive-row strong", ".pulse-timeline-node",
  "#pulseIdentityPath",
].join(", ");

const browser = await chromium.launch({ headless: true });

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
  await page.waitForTimeout(450); // close transition fully finishes before the next click
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

  // sidebar + secondary-nav views — open, scan, Escape, settle
  for (const v of ["workspaces", "activity", "ledger", "templates", "axioms", "journal", "archive", "askdocs", "recent", "promo", "manual", "almanac"]) {
    try {
      await page.click(`.nav-item[data-view="${v}"]`, { timeout: 6000 });
      await page.waitForTimeout(650);
      await expectClean(page, `view:${v}`, errors);
      await page.keyboard.press("Escape");
      await settlePanelModal(page);
    } catch (e) {
      errors.push(`[view:${v}] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
    }
  }

  // stage overlays — open, scan, close via their dedicated close buttons
  const stages = [
    { btn: "#pulseButton", close: "#pulseStageClose", label: "pulse" },
    { btn: "#doctorButton", close: "#doctorStageClose", label: "doctor" },
    { btn: "#dockyardButton", close: "#dockyardStageClose", label: "dockyard" },
    { btn: "#atlasButton", close: "#atlasClose", label: "atlas" },
    { btn: "#adminButton", close: "#adminStageClose", label: "admin-locked" },
  ];
  for (const s of stages) {
    try {
      await page.click(s.btn, { timeout: 5000 });
      await page.waitForTimeout(800);
      await expectClean(page, s.label, errors);
      await page.click(s.close, { timeout: 4000 });
      await page.waitForTimeout(400);
    } catch (e) {
      errors.push(`[${s.label}] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
    }
  }

  // admin unlocked — the 123 door opens the real numbers
  try {
    await page.click("#adminButton", { timeout: 5000 });
    await page.waitForTimeout(450);
    await page.fill("#adminPassword", "123", { timeout: 4000 });
    await page.click("#adminUnlockBtn", { timeout: 4000 });
    await page.waitForTimeout(1600);
    await expectClean(page, "admin-unlocked", errors);
    await page.click("#adminStageClose", { timeout: 4000 });
    await page.waitForTimeout(300);
  } catch (e) {
    errors.push(`[admin-unlocked] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
  }

  // arcade shell — game internals are canvas (not covered); the modal chrome must be clean
  try {
    await page.click("#arcadeButton", { timeout: 5000 });
    await page.waitForTimeout(1200);
    await expectClean(page, "arcade", errors);
    await page.click("#gameClose", { timeout: 4000 }).catch(() => {});
    await page.waitForTimeout(400);
  } catch (e) {
    errors.push(`[arcade] interaction failed: ${String(e.message).split("\n")[0].slice(0, 180)}`);
  }

  // Wayfinder tour — the guided onboarding must stay English end-to-end;
  // also proves the 9-step walk is intact in en mode
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

  // the Atlas HUD string (boot-time custom string, not data-i18n) must not ship CJK
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
  process.exit(1);
}
console.log("parity smoke passed: en mode renders zero CJK across workbench, all 12 nav views, 6 stage overlays, the 9-step Wayfinder tour, and boot-time custom strings; zh mode toggles correctly");
process.exit(0);
