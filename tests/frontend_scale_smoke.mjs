import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("http://scale.test/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/workspace") return route.fulfill({ json: { path: "scale-workspace", name: "Scale fixture" } });
    if (path === "/api/tasks") return route.fulfill({ json: { tasks: [] } });
    if (path === "/api/files") return route.fulfill({ json: { entries: [] } });
    if (path.startsWith("/api/")) return route.fulfill({ json: {} });
    try {
      return route.fulfill({ body: await readFile(`web${path === "/" ? "/index.html" : path}`), contentType: path.endsWith(".js") ? "text/javascript" : path.endsWith(".css") ? "text/css" : "text/html" });
    } catch { return route.fulfill({ status: 404 }); }
  });
  await page.goto("http://scale.test/");
  await page.waitForFunction(() => document.querySelector("#startupSplash").dataset.state === "ready");
  const timeline = await page.evaluate(() => {
    const loading = document.createElement("article");
    loading.innerHTML = '<div class="message-body"></div>';
    document.querySelector("#messageList").append(loading);
    const makeEvent = (n) => ({ kind: "tool", item_id: `tool-${n}`, event_id: `event-${n}`, name: "read_file", status: "ok", summary: `File ${n}`, output: "evidence ".repeat(10), detail: { turn: 1 } });
    const events = Array.from({ length: 260 }, (_, n) => makeEvent(n));
    syncLiveEvents(loading, events);
    const tool = loading.querySelector('[data-tool-event="tool-255"]');
    const round = tool.closest("details.agent-round");
    tool.open = true;
    round.open = true;
    const fold = tool.querySelector("details.tool-result-fold");
    fold.open = true;
    const next = [...events, makeEvent(260)];
    syncLiveEvents(loading, next);
    const stableAfterTrim = tool === loading.querySelector('[data-tool-event="tool-255"]') && tool.open && round.open && fold.open;
    const updated = next.map((event) => event.item_id === "tool-255" ? { ...event, event_id: "finished-255", output: "Updated evidence" } : event);
    syncLiveEvents(loading, updated);
    const stableAfterUpdate = tool === loading.querySelector('[data-tool-event="tool-255"]') && tool.open && fold.open && tool.textContent.includes("Updated evidence");
    const originalStringify = JSON.stringify;
    let serializations = 0;
    JSON.stringify = function(value, ...args) { if (Array.isArray(value)) serializations += 1; return originalStringify(value, ...args); };
    const start = performance.now();
    try { for (let n = 0; n < 1000; n += 1) syncLiveEvents(loading, updated); }
    finally { JSON.stringify = originalStringify; }
    const repeatedMs = performance.now() - start;
    const largeStart = performance.now();
    syncLiveEvents(loading, Array.from({ length: 10000 }, (_, n) => makeEvent(n)));
    const largeRenderMs = performance.now() - largeStart;
    const result = { stableAfterTrim, stableAfterUpdate, serializations, repeatedMs, largeRenderMs, renderedTools: loading.querySelectorAll("details.tool-event").length, fingerprintAttributeBytes: loading.querySelector(".tool-timeline").getAttribute("data-event-fingerprint")?.length || 0 };
    loading.remove();
    return result;
  });
  assert(timeline.stableAfterTrim, "rolling timeline retains expanded node and nested evidence identity");
  assert(timeline.stableAfterUpdate, "updated tool uses logical item identity despite a different event envelope");
  assert.equal(timeline.serializations, 0, "unchanged events do not serialize on each stream delta");
  assert(timeline.renderedTools <= 239);
  assert.equal(timeline.fingerprintAttributeBytes, 0, "tool outputs must not be copied into DOM attributes");

  const storage = await page.evaluate(() => {
    const prefix = "minicc-session-view:";
    localStorage.setItem("minicc-web-token", "fixture-token");
    localStorage.setItem("minicc-theme", "dark");
    for (let n = 0; n < 35; n += 1) localStorage.setItem(`${prefix}old:${n}`, `<article>${"a".repeat(50000)}</article>`);
    const messageList = document.querySelector("#messageList");
    state.sessionId = "thousand-message-history";
    messageList.innerHTML = Array.from({length: 1000}, (_, index) => `<article>history-${index}:${"text ".repeat(100)}</article>`).join("");
    window.dispatchEvent(new Event("beforeunload"));
    const history = Object.keys(localStorage).filter((key) => key.startsWith(prefix) && key.includes("thousand-message-history")).map((key) => localStorage.getItem(key))[0];
    if (!history?.includes("history-999:") || history.length > 180000) throw new Error("long history must preserve latest complete message within limit");
    for (let n = 0; n < 30; n += 1) {
      state.sessionId = `scale-${n}`;
      messageList.innerHTML = `<article>${"b".repeat(100000)}</article>`;
      window.dispatchEvent(new Event("beforeunload"));
    }
    const keys = Object.keys(localStorage).filter((key) => key.startsWith(prefix));
    const chars = keys.reduce((sum, key) => sum + localStorage.getItem(key).length, 0);
    state.sessionId = "oversized";
    messageList.innerHTML = `<article>${"c".repeat(220000)}</article><article>LATEST_MESSAGE</article>`;
    window.dispatchEvent(new Event("beforeunload"));
    const bounded = localStorage.getItem(`${prefix}scale-workspace:oversized`);
    state.sessionId = "retry";
    messageList.innerHTML = "<article>QUOTA_RETRY</article>";
    const originalSet = Storage.prototype.setItem;
    let retries = 0;
    Storage.prototype.setItem = function(key, value) {
      if (key === `${prefix}scale-workspace:retry` && retries++ === 0) throw new DOMException("fixture quota", "QuotaExceededError");
      return originalSet.call(this, key, value);
    };
    try { window.dispatchEvent(new Event("beforeunload")); }
    finally { Storage.prototype.setItem = originalSet; }
    return { entries: keys.length, chars, newest: keys.includes(`${prefix}scale-workspace:scale-29`), noLegacy: keys.every((key) => !key.startsWith(`${prefix}old:`)), bounded, retry: localStorage.getItem(`${prefix}scale-workspace:retry`), retries, token: localStorage.getItem("minicc-web-token"), theme: localStorage.getItem("minicc-theme") };
  });
  assert(storage.entries <= 24 && storage.chars <= 1_200_000);
  assert(storage.newest && storage.noLegacy);
  assert.equal(storage.bounded, "<article>LATEST_MESSAGE</article>");
  assert.equal(storage.retry, "<article>QUOTA_RETRY</article>");
  assert.equal(storage.retries, 2);
  assert.equal(storage.token, "fixture-token");
  assert.equal(storage.theme, "dark");
  assert.equal(errors.length, 0, errors.join("\n"));
  const metrics = { checks: "rolling timeline identity, nested expanded evidence, streaming serialization, bounded DOM, persistent cache eviction, quota retry, preservation of preferences", timeline, storage };
  await mkdir("output/playwright", { recursive: true });
  await writeFile("output/playwright/frontend-scale-metrics.json", JSON.stringify(metrics, null, 2));
  console.log(JSON.stringify(metrics, null, 2));
} finally { await browser.close(); }
