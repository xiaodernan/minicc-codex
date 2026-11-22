#!/usr/bin/env node
/**
 * Frontend layout and copy audit — a real browser looks at what a real visitor sees.
 *
 * The unit tests can prove a dictionary has 922 keys; they cannot prove a Chinese
 * label was clipped by a fixed-width sidebar at 1280px, that an English chip grew
 * past the topbar at 390px, or that a metric rendered the literal "NaN". This
 * probe does exactly that, in both locales, at three viewports, on a live server.
 *
 * It is deliberately *read-only*: no screenshots to eyeball, no hand-written
 * expectations of pixel positions. It measures honest DOM facts:
 *   - document horizontal overflow (the page is wider than the viewport)
 *   - text clipped inside its own box (scrollWidth > clientWidth with hidden overflow)
 *   - garbage literals (NaN / undefined / [object Object] / unresolved i18n keys)
 *   - avatar glyphs cropped or overflowing their badge
 *   - visible JS exceptions
 *
 * A rule that never has anything to look at is not a rule, so the audit also
 * runs one **fixture pass**: a throwaway git repository is built in the system
 * temp dir, dirtied deterministically, and served by a second throwaway server.
 * That is the only way the change-list rules (a file name welded into the next
 * word) have a witness on a clean checkout, where the real workspace's
 * `git status` is empty. Nothing is written inside the audited repository.
 *
 * Run standalone (starts a throwaway fake-provider server):
 *   node scripts/layout_audit.mjs
 * Run against an existing server:
 *   MINICC_WEB_URL=http://127.0.0.1:8899 node scripts/layout_audit.mjs
 * Machine-readable:
 *   node scripts/layout_audit.mjs --json
 */

import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const jsonMode = process.argv.includes("--json");

function freePort() {
  return new Promise((ok, fail) => {
    const s = createServer();
    s.once("error", fail);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => ok(port));
    });
  });
}

async function waitForHealth(url, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url + "/api/health", { signal: AbortSignal.timeout(1500) });
      if (r.ok) return;
    } catch {
      // child still booting — a failed poll is a wait, not a verdict
    }
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error("web server never answered /api/health");
}

async function startServer(workspace = REPO) {
  const port = await freePort();
  const python = process.env.MINICC_PYTHON || (process.platform === "win32"
    ? resolve(REPO, ".venv/Scripts/python.exe")
    : "python3");
  const env = {
    ...process.env,
    MINICC_FAKE_PROVIDER: "1",
    MINICC_API_KEY: "layout-audit",
    MINICC_BASE_URL: "https://example.invalid/v1",
  };
  const child = spawn(python, ["-m", "minicc.web", "--workspace", workspace,
    "--host", "127.0.0.1", "--port", String(port), "--token", "layout-audit-token"],
    { cwd: REPO, env, stdio: "ignore" });
  const url = `http://127.0.0.1:${port}`;
  await waitForHealth(url);
  return { url, stop: () => child.kill("SIGTERM") };
}

// --- the fixture workspace -------------------------------------------------
//
// Two paths the change list will render: one tracked and edited (a `modified`
// row with a real +/- count), one new and untracked (an `added` row whose counts
// the reader cannot know, which is the state the panel used to print as +0).
// Both names carry a `/` and a `.js`/`.md` extension, because the rule under
// test is about an extension running straight into the next word.
const FIXTURE_MODIFIED = join("web", "src", "panels", "changes_fixture.js");
const FIXTURE_ADDED = join("docs", "fixture_guide.md");
// Two more, for the other question: is a dotted thing a file name or a leaked
// dictionary key? They are the two shapes the answer has to cover. `changes.py` is a
// whole path whose last segment *is* the dotted name; `web/src/composer.send` is a
// dotted name the row shows as the tail of a longer path. Neither tail is a known
// extension, so the extension table cannot save either one - the row's own path can.
const FIXTURE_ROOT_PY = "changes.py";
const FIXTURE_KEY_LIKE = join("web", "src", "composer.send");
// Every row the fixture promises to render, by basename. Rule 6 requires the whole
// roster on screen: a witness that quietly stopped showing up is not a clean sheet.
const FIXTURE_ROSTER = ["changes_fixture.js", "fixture_guide.md", "changes.py", "composer.send"];
const FIXTURE_BASELINE = "export const rows = [\n  'alpha',\n  'beta',\n  'gamma',\n];\n";
const FIXTURE_EDITED = "export const rows = [\n  'alpha',\n  'beta renamed',\n  'gamma',\n];\nexport const total = rows.length;\n";

function git(cwd, args) {
  const run = spawnSync("git", args, { cwd, encoding: "utf-8" });
  if (run.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed (${run.status}): ${run.stderr || run.stdout}`);
  }
  return run.stdout;
}

function makeFixtureWorkspace() {
  const root = mkdtempSync(join(tmpdir(), "minicc-layout-fixture-"));
  git(root, ["init", "-q"]);
  git(root, ["config", "user.email", "layout-audit@example.invalid"]);
  git(root, ["config", "user.name", "layout audit"]);
  git(root, ["config", "commit.gpgsign", "false"]);
  mkdirSync(dirname(join(root, FIXTURE_MODIFIED)), { recursive: true });
  mkdirSync(dirname(join(root, FIXTURE_ADDED)), { recursive: true });
  writeFileSync(join(root, FIXTURE_MODIFIED), FIXTURE_BASELINE, "utf-8");
  writeFileSync(join(root, FIXTURE_ROOT_PY), "VERSION = 1\n", "utf-8");
  git(root, ["add", "-A"]);
  git(root, ["commit", "-q", "-m", "layout audit fixture baseline"]);
  writeFileSync(join(root, FIXTURE_MODIFIED), FIXTURE_EDITED, "utf-8");
  writeFileSync(join(root, FIXTURE_ROOT_PY), "VERSION = 2\n", "utf-8");
  writeFileSync(join(root, FIXTURE_ADDED), "# fixture guide\n\nA row the workspace never committed.\n", "utf-8");
  writeFileSync(join(root, FIXTURE_KEY_LIKE), "composer send\n", "utf-8");
  return root;
}

function removeFixtureWorkspace(root) {
  try {
    rmSync(root, { recursive: true, force: true });
    return "removed";
  } catch (error) {
    // A temp dir the OS would not give back is not a layout defect, but it must
    // not be reported as cleaned either.
    return `left behind: ${error.message}`;
  }
}

// The extensions `welded` (rule 2b) claims to know, measured against this repository:
// 1182 tracked files have 18 distinct tails and 15 of them are listed here. A tail that
// is not listed — `kernel.pyx`, `data.parquet` — is not claimed, and the rule says so
// by staying quiet instead of guessing that a word is an extension.
const FILE_EXTENSIONS = [
  "js", "mjs", "cjs", "json", "jsonl", "css", "md", "py", "rb", "ts", "tsx", "jsx",
  "yml", "yaml", "html", "txt", "sh", "go", "rs", "java", "csv", "toml", "ini",
  "sql", "svg", "png", "jpg", "jpeg", "gif", "ico", "webp", "woff", "woff2", "ttf",
  "xml", "log", "lock", "patch", "ps1", "bat", "gradle", "jar",
];

// The namespaces the dictionary actually ships. This rule used to carry six of them
// by hand while the dictionary had 71, so a raw key leaking under any other namespace
// was invisible to the very gate named after it.
function dictionaryNamespaces() {
  const source = readFileSync(resolve(REPO, "web", "src", "core", "i18n.js"), "utf-8");
  const names = new Set();
  for (const match of source.matchAll(/["']([a-z][a-z0-9]*)\.[A-Za-z0-9_.]+["']\s*:/g)) names.add(match[1]);
  if (names.size < 40) {
    throw new Error(`the dictionary yielded ${names.size} namespaces - the reader went blind, `
      + "and a rule that matches nothing passes by construction");
  }
  return [...names].sort();
}

const NAMESPACES = dictionaryNamespaces();

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 960 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "mobile", width: 390, height: 844 },
];
const LOCALES = ["zh", "en"];

// Real scroll containers and user-authored content: clipping there is by design,
// not a layout defect. The chrome of the app (nav, topbar, tiles, buttons, cards)
// is the surface a visitor cannot escape and therefore must never be clipped.
const SCROLL_EXEMPT = [
  ".thread-list", ".message", ".message-text", ".chat-area", ".chat-inner",
  ".session-heading", "#panelBody", "#panelModal", ".panel-stage", "pre", "code",
  "textarea", "input", "canvas", ".manual-body", ".almanac-body", ".atlas-body",
  ".admin-task-message", ".todo-content", ".recent-copy", ".promo-body",
];

async function auditPage(page, locale, viewport, { fixture = false } = {}) {
  return page.evaluate(({ locale, viewport, SCROLL_EXEMPT, fixture, NAMESPACES, FILE_EXTENSIONS, FIXTURE_ROSTER }) => {
    const findings = [];
    const label = `${locale}/${viewport}`;
    const bad = (kind, where, snippet, detail = "") =>
      findings.push({ label, kind, where, snippet: String(snippet).replace(/\s+/g, " ").slice(0, 160), detail });

    const visible = (el) => {
      try {
        return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
      } catch {
        const s = getComputedStyle(el);
        return s.display !== "none" && s.visibility !== "hidden" && el.getClientRects().length > 0;
      }
    };
    const describe = (el) => {
      const id = el.id ? `#${el.id}` : "";
      const cls = typeof el.className === "string" && el.className.trim()
        ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
      return `${el.tagName.toLowerCase()}${id}${cls}`;
    };

    // 1. The page itself must fit. A horizontal scrollbar on a phone means
    //    the visitor loses half the interface with no way to discover it.
    const docOverflow = document.documentElement.scrollWidth - window.innerWidth;
    if (docOverflow > 2) {
      bad("page-overflow", "document", `scrollWidth=${document.documentElement.scrollWidth} viewport=${window.innerWidth}`,
        `${docOverflow}px wider than viewport`);
    }

    // 2. Garbage literals and unresolved keys in visible chrome.
    const garbage = /NaN|undefined|\[object Object\]|\bnull\b/;
    const EXT = FILE_EXTENSIONS.join("|");
    // 2a. A dictionary key that reached the screen as itself: a namespace the shipped
    //     dictionary knows, a dot, then a word. The namespace list is derived from
    //     web/src/core/i18n.js; it used to be six names copied into this file while the
    //     dictionary carried 71, so a leak under any other namespace was invisible to
    //     the very gate named after it.
    //
    //     The widened list immediately disagreed with the product about
    //     `web/src/composer.send`, which proves the exemption cannot be a token test:
    //     a change row shows its path split into runs (`web/` `src/` `composer.send`),
    //     so the run holding the file name has no slash in it and `send` is not a known
    //     extension. What does know it is a file name is the DOM — the app only sets
    //     `data-open-diff` / `data-file` on a row it built from a git path — so the
    //     exemption is scope: the row carries the path it was built from, and only a
    //     token that is one of that path's own segments counts as a file name. Scope
    //     has to be per segment, not per row, because the same row also renders
    //     `changes.now` — a real key, in a real path's neighbourhood, which an
    //     amnesty for the whole row would have hidden.
    const leakedKey = new RegExp("\\b(" + NAMESPACES.join("|") + ")\\.[a-zA-Z][\\w.]*", "g");
    const pathSegments = (el) => {
      const row = el.closest("[data-open-diff], [data-file]");
      if (!row) return [];
      const path = row.getAttribute("data-open-diff") || row.getAttribute("data-file") || "";
      return path.split(/[\\/]/);
    };
    // 2b. A file name welded into the next word — "web/src/panels/admin.jsModified" is
    //     not a sentence. Shape question: no known extension may run straight into a
    //     capital letter or a CJK glyph without a separator between them.
    const welded = new RegExp("\\.(" + EXT + ")(?=[A-Z\u4e00-\u9fff])");
    const scan = (text, where, kinds, el) => {
      if (!text) return;
      if (garbage.test(text)) bad(kinds.garbage, where, text);
      if (welded.test(text)) bad("welded-filename-label", where, text);
      const segments = pathSegments(el);
      for (const match of text.matchAll(leakedKey)) {
        if (segments.includes(match[0])) continue;
        bad(kinds.unresolved, where, text, `a dictionary key printed as itself: ${match[0]}`);
      }
    };
    for (const el of document.querySelectorAll("body *")) {
      if (!visible(el)) continue;
      if (el.matches(SCROLL_EXEMPT) || el.closest(SCROLL_EXEMPT)) continue;
      for (const node of el.childNodes) {
        if (node.nodeType !== 3) continue;
        scan((node.nodeValue || "").trim(), describe(el),
          { garbage: "garbage-literal", unresolved: "unresolved-i18n" }, el);
      }
      for (const attr of ["placeholder", "title", "aria-label", "alt"]) {
        const value = el.getAttribute(attr);
        if (!value) continue;
        scan(value.trim(), `${describe(el)}[${attr}]`,
          { garbage: "garbage-attribute", unresolved: "unresolved-i18n-attribute" }, el);
      }
    }
    // 3. Text clipped inside its own box. Only leaf-ish chrome elements are
    //    measured: a wrapper intentionally clipping an animated stage is not a
    //    clipped label. Hidden overflow + real horizontal loss + text = defect.
    for (const el of document.querySelectorAll(
      ".nav-item, .nav-item span, .topbar button, .topbar span, .sidebar button, " +
      ".sidebar span, .chip, .stat-value, .stat-label, .badge, .btn, .btn-primary, " +
      ".brand-name, .brand-caption, .profile-copy, .running-light-text, .section-label")) {
      if (!visible(el)) continue;
      if (el.matches(SCROLL_EXEMPT) || el.closest(SCROLL_EXEMPT)) continue;
      const style = getComputedStyle(el);
      if (style.overflowX === "visible" || style.overflowX === "auto" || style.overflowX === "scroll") continue;
      const loss = el.scrollWidth - el.clientWidth;
      if (el.clientWidth > 0 && loss > 2 && (el.innerText || "").trim()) {
        // An ellipsis is a deliberate, discoverable truncation — but only when
        // the full string is reachable, e.g. through a native tooltip.
        if (style.textOverflow === "ellipsis" && el.getAttribute("title")) continue;
        bad("clipped-text", describe(el), el.innerText, `${loss}px clipped`);
      }
    }

    // 4. Avatar glyphs: the badge is a fixed circle, the initial must be centred
    //    and wholly inside it.
    for (const el of document.querySelectorAll(".avatar, .brand-mark, .proof-avatars b")) {
      if (!visible(el)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 8 || rect.height < 8) {
        bad("avatar-collapsed", describe(el), el.innerText, `${Math.round(rect.width)}x${Math.round(rect.height)}px`);
        continue;
      }
      // Measure the actual glyphs, not pseudo-elements: the rotating glow
      // inside .brand-mark is *meant* to be clipped by overflow:hidden.
      const range = document.createRange();
      range.selectNodeContents(el);
      const glyph = range.getBoundingClientRect();
      const box = el.getBoundingClientRect();
      const lossX = Math.max(0, box.left - glyph.left) + Math.max(0, glyph.right - box.right);
      const lossY = Math.max(0, box.top - glyph.top) + Math.max(0, glyph.bottom - box.bottom);
      if (lossX > 3 || lossY > 3) {
        bad("avatar-clipped", describe(el), el.innerText,
          `glyph ${Math.round(glyph.width)}x${Math.round(glyph.height)} in ${Math.round(box.width)}x${Math.round(box.height)} (${Math.round(lossX)}x${Math.round(lossY)} outside)`);
      }
    }

    // 5. Topbar controls must not sit on top of one another. Nested spans are
    //    excluded; only sibling controls in the same row are compared.
    const controls = [...document.querySelectorAll(".topbar-left > *, .topbar-right > *")]
      .filter((el) => visible(el) && getComputedStyle(el).position !== "absolute");
    const rects = controls.map((el) => ({ el, r: el.getBoundingClientRect() }));
    for (let i = 0; i < rects.length; i += 1) {
      for (let j = i + 1; j < rects.length; j += 1) {
        const a = rects[i], b = rects[j];
        if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const ox = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const oy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        if (ox > 4 && oy > 4) {
          bad("topbar-overlap", `${describe(a.el)} × ${describe(b.el)}`,
            `${Math.round(ox)}x${Math.round(oy)}px overlap`);
        }
      }
    }

    // 6. Fixture pass only: the witness has to be in the room. Every rule above
    //    measures what happens to be on screen, so a pass that rendered no change
    //    rows would report a clean sheet for having looked at nothing. The fixture
    //    exists to make that impossible: each of its files must be on screen, and the
    //    app must have auto-titled the row that carries them.
    //
    //    The roster is not one row but four, because rule 2's two exemptions each need
    //    their own witness: `changes.py` only survives the namespace sweep through the
    //    shared extension table, and `web/src/composer.send` only survives it through
    //    the path test. If either witness stops rendering, the corresponding exemption
    //    becomes a rule that matches nothing — so a missing roster entry is reported as
    //    the ruler's own failure, never as a clean sheet.
    if (fixture) {
      const rows = [...document.querySelectorAll("#changeList .change-item-button, #fileList .file-row")]
        .filter(visible);
      const named = rows.map((el) => el.getAttribute("data-open-diff") || el.getAttribute("data-file") || "");
      const seen = new Set(named.map((path) => path.split(/[\\/]/).pop()));
      for (const want of FIXTURE_ROSTER) {
        if (!seen.has(want)) {
          bad("fixture-row-missing", "#changeList", named.join(" ") || "(no rows)",
            `the fixture file ${want} never rendered, so the change-list rule it witnesses measured nothing`);
        }
      }
      const titled = rows.filter((el) => el.getAttribute("data-auto-title") === "true"
        && (el.getAttribute("title") || "").trim());
      if (rows.length > 0 && titled.length === 0) {
        bad("fixture-tooltip-absent", "#changeList", describe(rows[0]),
          `${rows.length} change row(s) rendered without a derived tooltip`);
      }
    }

    return findings;
  }, { locale, viewport, SCROLL_EXEMPT, fixture, NAMESPACES, FILE_EXTENSIONS, FIXTURE_ROSTER });
}

async function openApp(browser, url, locale, viewport, onPageError) {
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
  page.on("pageerror", onPageError);
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  // The splash is a real overlay: until it says "ready" every DOM
  // measurement below would describe the loading screen, not the app.
  await page.waitForFunction(() =>
    document.querySelector("#startupSplash")?.dataset.state === "ready",
    null, { timeout: 30000 });
  await page.waitForTimeout(450);
  return page;
}

async function main() {
  const server = process.env.MINICC_WEB_URL
    ? { url: process.env.MINICC_WEB_URL, stop: () => {} }
    : await startServer();
  const browser = await chromium.launch({ headless: true });
  const report = { url: server.url, viewports: [], findings: [], jsErrors: [], fixture: null };
  try {
    for (const locale of LOCALES) {
      for (const viewport of VIEWPORTS) {
        const page = await openApp(browser, server.url, locale, viewport,
          (e) => report.jsErrors.push(`${locale}/${viewport.name}: ${e.message}`));
        const findings = await auditPage(page, locale, viewport.name);
        report.viewports.push(`${locale}/${viewport.name}`);
        report.findings.push(...findings);
        await page.close();
      }
    }

    // The fixture pass: a workspace that is *guaranteed* to have change rows, so
    // the change-list rules have a witness on a clean checkout. It runs on its
    // own server over a throwaway repository; the audited workspace is untouched.
    const fixtureRoot = makeFixtureWorkspace();
    let fixtureServer = null;
    try {
      fixtureServer = await startServer(fixtureRoot);
      for (const locale of LOCALES) {
        // Desktop and laptop: the change list scrolls on a phone but is fully on
        // screen above 800px, and a witness is only a witness where the rule reads it.
        for (const viewport of [VIEWPORTS[0], VIEWPORTS[1]]) {
          const page = await openApp(browser, fixtureServer.url, locale, viewport,
            (e) => report.jsErrors.push(`${locale}/${viewport.name}/fixture: ${e.message}`));
          // The rows come from /api/changes, which shells out to git; wait for every
          // fixture file by name rather than a fixed sleep, then for the observer that
          // titles newly rendered buttons (it debounces at 200ms).
          await page.waitForFunction((roster) => {
            const seen = new Set([...document.querySelectorAll("#changeList [data-open-diff], #fileList [data-file]")]
              .map((el) => (el.getAttribute("data-open-diff") || el.getAttribute("data-file") || "").split(/[\\/]/).pop()));
            return roster.every((want) => seen.has(want));
          }, FIXTURE_ROSTER, { timeout: 30000 }).catch(() => { /* rule 6 reports the absence */ });
          await page.waitForTimeout(600);
          const findings = await auditPage(page, locale, `${viewport.name}/fixture`, { fixture: true });
          const rows = await page.evaluate(() => [...document.querySelectorAll("#changeList .change-item-button")]
            .map((el) => el.getAttribute("data-open-diff")).filter(Boolean));
          report.viewports.push(`${locale}/${viewport.name}/fixture`);
          report.findings.push(...findings);
          report.fixture = { workspace: fixtureRoot, rows, cleanup: null };
          await page.close();
        }
      }
    } finally {
      if (fixtureServer) fixtureServer.stop();
      report.fixture = { ...(report.fixture || { workspace: fixtureRoot }), cleanup: removeFixtureWorkspace(fixtureRoot) };
    }
  } finally {
    await browser.close();
    server.stop();
  }

  report.ok = report.findings.length === 0 && report.jsErrors.length === 0;
  if (jsonMode) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } else {
    process.stdout.write(`layout audit: ${report.viewports.join(", ")}\n`);
    if (report.fixture) {
      process.stdout.write(`  fixture: ${report.fixture.rows.length} change row(s), workspace ${report.fixture.cleanup}\n`);
    }
    for (const f of report.findings) {
      process.stdout.write(`  FAIL ${f.kind} ${f.where}: ${f.snippet}${f.detail ? ` (${f.detail})` : ""}\n`);
    }
    for (const e of report.jsErrors) process.stdout.write(`  FAIL pageerror ${e}\n`);
    process.stdout.write(report.ok ? "layout audit: PASS\n" : `layout audit: ${report.findings.length + report.jsErrors.length} finding(s)\n`);
  }
  process.exitCode = report.ok ? 0 : 1;
}

main().catch((error) => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 2;
});
