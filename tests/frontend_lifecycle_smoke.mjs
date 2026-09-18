import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";
const cacheSource = await readFile("web/src/core/bounded-cache.js", "utf8");
const { BoundedMap, BoundedSet } = await import(`data:text/javascript;base64,${Buffer.from(cacheSource).toString("base64")}`);
const sessions = new BoundedMap(24);
const completed = new BoundedSet(2048);
for (let n = 0; n < 10000; n += 1) { sessions.set(`session-${n}`, "view"); completed.add(`task-${n}`); }
assert.equal(sessions.size, 24);
assert.equal(completed.size, 2048);
assert(sessions.has("session-9999") && !sessions.has("session-0"));

const browser = await chromium.launch({ headless: true });
const errors = [];
const pause = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};
const task = (id, extra = {}) => ({ task_id: id, session_id: "shared", workspace_path: "A", status: "running", phase: "planning", events: [], preview: id, ...extra });
async function fixture(handler) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("minicc-session", "shared");
    window.eventSources = [];
    window.EventSource = class {
      constructor(url) { this.url = url; window.eventSources.push(this); }
      addEventListener() {}
      close() { this.closed = true; }
    };
  });
  await page.route("http://lifecycle.test/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const custom = await handler(path, request);
    if (custom) return route.fulfill(custom);
    if (path === "/api/workspace") return route.fulfill({ json: { path: "A", name: "A" } });
    if (path === "/api/tasks") return route.fulfill({ json: { tasks: [] } });
    if (path === "/api/files") return route.fulfill({ json: { entries: [] } });
    if (path.startsWith("/api/")) return route.fulfill({ json: {} });
    try {
      return route.fulfill({ body: await readFile(`web${path === "/" ? "/index.html" : path}`), contentType: path.endsWith(".js") ? "text/javascript" : path.endsWith(".css") ? "text/css" : "text/html" });
    } catch { return route.fulfill({ status: 404 }); }
  });
  await page.goto("http://lifecycle.test/");
  await page.waitForFunction(() => document.querySelector("#startupSplash").dataset.state === "ready");
  return { page, context };
}

try {
  // A detail request from A completes after B uses the same session id.
  let workspace = "A";
  const detail = pause();
  let detailStarted = false;
  const { page, context } = await fixture(async (path) => {
    if (path === "/api/workspace") return { json: { path: workspace, name: workspace } };
    if (path === "/api/tasks") return { json: { tasks: workspace === "A" ? [task("old", { status: "completed", summary_only: true })] : [] } };
    if (path === "/api/tasks/old") {
      detailStarted = true;
      await detail.promise;
      return { json: task("old", { status: "completed", answer: "OLD_WORKSPACE_ANSWER" }) };
    }
  });
  await page.waitForFunction(() => document.querySelector("#threadList").textContent.includes("old"));
  assert(detailStarted);
  workspace = "B";
  await page.evaluate(() => loadWorkspace());
  detail.resolve();
  await page.waitForTimeout(150);
  assert(!(await page.locator("#messageList").textContent()).includes("OLD_WORKSPACE_ANSWER"), "old hydration must not contaminate B");
  const stored = await page.evaluate(() => {
    window.dispatchEvent(new Event("beforeunload"));
    return Object.keys(localStorage).filter((key) => key.startsWith("minicc-session-view:"));
  });
  assert(stored.some((key) => key.endsWith(":shared")), "unload stores the current session");
  assert(!stored.some((key) => key.includes("Event")), "unload event must not be used as a session id");
  await context.close();

  // The first task finishing must not release a second POST still in flight.
  const secondPost = pause();
  let posts = 0;
  const terminal = task("first", { status: "completed", phase: "completed", answer: "FIRST_DONE" });
  const concurrent = await fixture(async (path, request) => {
    if (path === "/api/tasks" && request.method() === "POST") {
      posts += 1;
      if (posts === 2) await secondPost.promise;
      return { json: task(posts === 1 ? "first" : "second") };
    }
    if (path === "/api/tasks/first") return { json: terminal };
  });
  await concurrent.page.locator("#promptInput").fill("first request");
  await concurrent.page.locator("#sendButton").click();
  await concurrent.page.waitForFunction(() => window.eventSources.length === 1);
  await concurrent.page.locator("#promptInput").fill("second request");
  await concurrent.page.locator("#sendButton").click();
  await concurrent.page.waitForFunction(() => document.querySelector("#sendButton").disabled);
  await concurrent.page.locator("#moreOptionsButton").click();
  await concurrent.page.waitForFunction(() => document.activeElement.id === "panelExpand");
  await concurrent.page.evaluate((value) => window.eventSources[0].onmessage({ data: JSON.stringify(value) }), terminal);
  await concurrent.page.waitForFunction(() => !window.runningTasks.has("first"));
  assert(await concurrent.page.locator("#sendButton").isDisabled(), "first completion cannot unlock second submission");
  assert.equal(await concurrent.page.evaluate(() => document.activeElement.id), "panelExpand", "background completion cannot steal dialog focus");
  assert.equal(posts, 2);
  secondPost.resolve();
  await concurrent.page.waitForFunction(() => window.eventSources.length === 2);
  await concurrent.context.close();

  // A queued POST from A must never select the new workspace's active task.
  workspace = "A";
  const pendingPost = pause();
  let postStarted = false;
  const switched = await fixture(async (path, request) => {
    if (path === "/api/workspace") return { json: { path: workspace, name: workspace } };
    if (path === "/api/tasks" && request.method() === "POST") {
      postStarted = true;
      await pendingPost.promise;
      return { json: task("background-A") };
    }
  });
  await switched.page.locator("#promptInput").fill("A request");
  await switched.page.locator("#sendButton").click();
  assert(postStarted);
  workspace = "B";
  await switched.page.evaluate(() => loadWorkspace());
  pendingPost.resolve();
  await switched.page.waitForFunction(() => window.runningTasks.has("background-A"));
  assert.equal(await switched.page.evaluate(() => window.state.activeTaskId), null);
  assert.equal(await switched.page.evaluate(() => window.state.busy), false);
  assert(await switched.page.locator("#taskDock").isHidden());
  await switched.context.close();

  // A replica/cache snapshot still running cannot undo a terminal SSE frame.
  const lagging = await fixture(async (path, request) => {
    if (path === "/api/tasks" && request.method() === "POST") return { json: task("lagging") };
    if (path === "/api/tasks/lagging") return { json: task("lagging") };
  });
  await lagging.page.locator("#promptInput").fill("terminal request");
  await lagging.page.locator("#sendButton").click();
  await lagging.page.waitForFunction(() => window.eventSources.length === 1);
  await lagging.page.evaluate((value) => window.eventSources[0].onmessage({ data: JSON.stringify(value) }), task("lagging", { status: "completed", phase: "completed", answer: "TERMINAL_ANSWER" }));
  await lagging.page.waitForFunction(() => !window.runningTasks.has("lagging"));
  assert((await lagging.page.locator("#messageList").textContent()).includes("TERMINAL_ANSWER"));
  assert.equal(await lagging.page.evaluate(() => window.state.lastTask.status), "completed");
  assert(await lagging.page.evaluate(() => window.eventSources.every((source) => source.closed)), "terminal closes all SSE connections");
  const requestCount = await lagging.page.evaluate(() => window.eventSources.length);
  await lagging.page.waitForTimeout(3700);
  assert.equal(await lagging.page.evaluate(() => window.eventSources.length), requestCount, "terminal snapshot timeout cannot reopen SSE");
  await lagging.context.close();
  const rewind = await fixture(async (path) => {
    if (path === "/api/workspace/restore") return { json: { restored: ["safe.txt"], conflicts: ["user-edit.py"], skipped: [] } };
  });
  await rewind.page.evaluate(() => {
    const button = document.createElement("button");
    button.dataset.restoreTask = "rewind-task";
    button.textContent = "restore fixture";
    document.querySelector("#messageList").append(button);
  });
  await rewind.page.locator("[data-restore-task]").click();
  await rewind.page.waitForFunction(() => document.querySelector("#toast").textContent.includes("user-edit.py"));
  assert((await rewind.page.locator("#toast").textContent()).includes("user-edit.py"), "rewind must expose preserved conflicting files");
  await rewind.context.close();
  assert.deepEqual(errors, []);
} finally { await browser.close(); }
console.log("lifecycle passed: workspace hydration, concurrent submissions, modal focus, workspace switch during POST, terminal snapshot ordering");
