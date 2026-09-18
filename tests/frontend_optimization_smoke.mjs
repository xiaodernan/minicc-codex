import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";
const importSource = async (path) => import(`data:text/javascript;base64,${Buffer.from(await readFile(path)).toString("base64")}`);
const { reduceTaskEvent } = await importSource("web/src/core/task-reducer.js");
const original = { data: { stream_text: "", events: [] }, cursor: 0, seenEventIds: new Set(), seenSequences: new Set() };
let binding = reduceTaskEvent(original, { sequence: 1, event_id: "one", kind: "timeline", payload: { kind: "tool", name: "grep", item_id: "tool", status: "running" } });
assert.equal(original.data.events.length, 0, "reducer must not mutate input");
assert.equal(reduceTaskEvent(binding, { sequence: 1, event_id: "one" }), null);
binding = reduceTaskEvent(binding, { sequence: 2, event_id: "two", kind: "timeline", payload: { kind: "tool", name: "grep", item_id: "tool", status: "ok" } });
assert.equal(binding.data.events.length, 1);
assert.equal(binding.data.events[0].status, "ok");
binding = reduceTaskEvent(binding, { sequence: 3, kind: "stream_delta", payload: { stream_text: "x".repeat(16000), stream_length: 40000 } });
binding = reduceTaskEvent(binding, { sequence: 4, kind: "stream_delta", payload: { delta: "tail", stream_length: 40004 } });
assert.equal(binding.data.stream_length, 40004);
assert(binding.data.stream_text.endsWith("tail"));
binding = reduceTaskEvent(binding, { sequence: 5, kind: "stream_delta", payload: { stream_text: "old", stream_length: 100 } });
assert(binding.data.stream_text.endsWith("tail"), "old snapshot must not erase newer text");

await mkdir("output/playwright", { recursive: true });
const browser = await chromium.launch({ headless: true });
const metrics = [];
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      const errors = [];
      let workspace = "A";
      let gameRequests = 0;
      let changesComplete = false;
      const tasks = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript((theme) => { localStorage.setItem("minicc-theme", theme); localStorage.setItem("minicc-locale", "zh"); }, theme);
      await page.route("http://workbench.test/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === "/api/workspace") return route.fulfill({ json: { path: workspace, name: `Project ${workspace}`, context_window_tokens: 300000 } });
        if (path === "/api/changes") {
          const requestWorkspace = workspace;
          await new Promise((resolve) => setTimeout(resolve, requestWorkspace === "A" ? 1000 : 30));
          changesComplete = true;
          return route.fulfill({ json: { files: [{ path: `${requestWorkspace}/入口.js`, status: "modified", additions: 3, deletions: 1 }], additions: 3, deletions: 1 } });
        }
        if (path === "/api/files") return route.fulfill({ json: { entries: [{ path: "src", name: "src", type: "dir" }, { path: "src/main.js", name: "main.js", type: "file", size: 345 }] } });
        if (path === "/api/tasks") return route.fulfill({ json: { tasks } });
        if (path === "/api/diff" || path === "/api/file") {
          await new Promise((resolve) => setTimeout(resolve, 140));
          if (path === "/api/file") return route.fulfill({ status: 404, json: { error: "File unavailable" } });
          return route.fulfill({ json: { patch: "", status: "deleted" } });
        }
        if (path.startsWith("/api/")) return route.fulfill({ json: {} });
        if (path.includes("game.") || path === "/game.js") gameRequests += 1;
        try {
          const body = await readFile(`web${path === "/" ? "/index.html" : path}`);
          const contentType = path.endsWith(".css") ? "text/css" : path.endsWith(".js") ? "text/javascript" : path.endsWith(".svg") ? "image/svg+xml" : "text/html";
          return route.fulfill({ body, contentType });
        } catch { return route.fulfill({ status: 404 }); }
      });
      const start = Date.now();
      await page.goto("http://workbench.test/", { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#startupSplash").dataset.state === "ready");
      const readyMs = Date.now() - start;
      assert.equal(changesComplete, false, "slow Git request must not block startup");
      assert.equal(gameRequests, 0, "home must not download arcade");
      await page.locator('[data-start-action="explore"]').click();
      assert((await page.locator("#promptInput").inputValue()).includes("架构"));
      const geometry = await page.evaluate(() => {
        const send = document.querySelector("#sendButton").getBoundingClientRect();
        const controls = document.querySelector("#allowNetwork").closest("label").getBoundingClientRect();
        return { sendBottom: send.bottom, sendRight: send.right, viewportHeight: innerHeight, viewportWidth: innerWidth, networkWidth: controls.width, overflow: document.body.scrollWidth > innerWidth };
      });
      assert(geometry.sendBottom <= viewport.height, `send clipped: ${JSON.stringify(geometry)}`);
      assert(geometry.sendRight <= viewport.width);
      assert(geometry.networkWidth > 40, "network capability and its label must be visible");
      const contrast = await page.evaluate(() => {
        const luminance = (color) => {
          const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map((n) => { const v = n / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
          return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
        };
        const root = getComputedStyle(document.documentElement);
        const samples = [["--text", "--surface"], ["--muted", "--surface"], ["--quiet", "--sidebar"]];
        return samples.map(([fg, bg]) => {
          const probe = document.createElement("span"); document.body.append(probe);
          probe.style.color = root.getPropertyValue(fg); const f = luminance(getComputedStyle(probe).color);
          probe.style.color = root.getPropertyValue(bg); const b = luminance(getComputedStyle(probe).color); probe.remove();
          return (Math.max(f, b) + 0.05) / (Math.min(f, b) + 0.05);
        });
      });
      assert(contrast.every((ratio) => ratio >= 4.5), `text contrast ${contrast}`);
      assert.equal(geometry.overflow, false);
      await page.locator('[data-mode="acceptEdits"]').click();
      assert((await page.locator("#permissionSummary").textContent()).includes("文件：可写"));
      if (viewport.width < 1181) await page.locator("#inspectorToggle").click();
      await page.locator('[data-inspector-tab="files"]').click();
      await page.locator("#fileTree").getByRole("treeitem", { name: "src" }).click();
      await page.locator('[data-open-diff="src/main.js"]').waitFor({ state: "visible" });
      assert.equal(await page.evaluate(() => document.activeElement.dataset.treeDir), "src", "tree expansion keeps focus");
      await page.keyboard.press("ArrowRight");
      assert.equal(await page.evaluate(() => document.activeElement.dataset.openDiff), "src/main.js", "right arrow enters folder");
      await page.keyboard.press("ArrowLeft");
      assert.equal(await page.evaluate(() => document.activeElement.dataset.treeDir), "src");
      assert.equal(await page.locator('#fileTree [role="treeitem"][tabindex="0"]').count(), 1);
      await page.locator('[data-inspector-tab="verification"]').click();
      assert(await page.locator("#verificationSection").isVisible());
      await page.locator('[data-inspector-tab="changes"]').click();
      if (viewport.width < 1181) await page.locator("#inspectorClose").click();
      await page.locator("#moreOptionsButton").click();
      await page.waitForFunction(() => document.activeElement.id === "panelExpand");
      assert.equal(await page.locator(".app-shell").evaluate((node) => node.inert), true, "modal isolates background");
      await page.keyboard.press("Shift+Tab");
      assert.equal(await page.evaluate(() => document.activeElement.dataset.panelAction), "reload", "tab wraps within dialog");
      await page.keyboard.press("Tab");
      assert.equal(await page.evaluate(() => document.activeElement.id), "panelExpand");
      await page.keyboard.press("Escape");
      assert.equal(await page.evaluate(() => document.activeElement.id), "moreOptionsButton", "closing returns focus");
      assert.equal(await page.locator(".app-shell").evaluate((node) => node.inert), false);
      await page.evaluate(() => { window.openFilePreview("slow.py"); });
      await page.keyboard.press("Escape");
      await page.waitForTimeout(220);
      assert.equal(await page.locator("#panelModal").getAttribute("aria-hidden"), "true", "late response must not reopen closed preview");
      await page.evaluate(() => { window.openFilePreview("slow.py"); window.openHelpPanel(); });
      const helpTitle = await page.locator("#panelTitle").textContent();
      await page.waitForTimeout(220);
      assert.equal(await page.locator("#panelTitle").textContent(), helpTitle, "late preview must not replace newer panel");
      await page.keyboard.press("Escape");
      await page.evaluate(() => window.openFilePreview("deleted.py"));
      assert((await page.locator("#panelBody").textContent()).includes("文件已删除"), "deleted file has explicit state");
      await page.keyboard.press("Escape");
      // An old workspace response finishing last must not overwrite the new one.
      workspace = "B";
      await page.evaluate(() => window.loadWorkspace());
      await page.waitForTimeout(1150);
      assert((await page.locator("#changeList").textContent()).includes("B/入口.js"));
      const identity = await page.evaluate(() => {
        const loading = document.createElement("article");
        loading.innerHTML = '<div class="message-body"></div>';
        document.querySelector("#messageList").append(loading);
        const events = [{ kind: "trace", code: "tool_round_started", detail: { turn: 1 } }, { kind: "tool", name: "grep", event_id: "stable-tool", status: "ok", summary: "Read entry", output: "evidence", detail: { turn: 1 } }];
        syncLiveEvents(loading, events);
        const tool = loading.querySelector("details.tool-event");
        const round = loading.querySelector("details.agent-round");
        tool.open = true; round.open = true;
        syncLiveEvents(loading, [...events, { kind: "trace", code: "verification_observed", event_id: "verified", status: "ok", summary: "Checked", detail: { turn: 1 } }]);
        const result = { sameTool: tool === loading.querySelector("details.tool-event"), sameRound: round === loading.querySelector("details.agent-round"), open: tool.open && round.open };
        loading.remove();
        return result;
      });
      assert.deepEqual(identity, { sameTool: true, sameRound: true, open: true });
      await page.locator("#promptInput").fill("");
      await page.locator("#promptInput").blur();
      await page.waitForFunction(() => !document.querySelector("#toast").classList.contains("show"));
      await page.screenshot({ path: `output/playwright/optimized-${viewport.width}-${theme}.png` });
      if (viewport.width < 780) {
        await page.setViewportSize({ width: 390, height: 430 });
        await page.locator("#promptInput").focus();
        await page.waitForTimeout(80);
        assert(await page.locator("#sendButton").evaluate((node) => node.getBoundingClientRect().bottom <= innerHeight), "send remains visible with keyboard viewport");
      }
      await page.evaluate(() => window.openArcade());
      assert.equal(gameRequests, 1, "arcade loads once after explicit action");
      assert.equal(errors.length, 0, errors.join("\n"));
      metrics.push({ theme, viewport, readyMs, textContrast: contrast, ...geometry });
      await context.close();
    }
  }
} finally { await browser.close(); }
await writeFile("output/playwright/frontend-optimization-metrics.json", JSON.stringify(metrics, null, 2));
console.log(JSON.stringify({ checks: "reducer, fast startup, lazy arcade, stale responses, responsive controls, permissions, tabs, timeline identity, modal keyboard and focus, tree keyboard, preview races and errors", metrics }, null, 2));
