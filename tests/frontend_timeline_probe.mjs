// M8-T904 probe: the pulse card's task timeline renders real nodes in a real
// browser. Opens the pulse stage over the live gateway server, screenshots the
// timeline, asserts the strip carries nodes with tone attributes and that the
// data-open-task delegation reaches a task detail from a timeline node.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8899";
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });

  // open the pulse stage the way the UI does (the sidebar pulse button)
  await page.locator("#pulseButton").click();
  await page.waitForFunction(() => document.querySelector("#pulseStage")?.getAttribute("aria-hidden") === "false", { timeout: 15000 });
  await page.waitForFunction(() => {
    const tl = document.querySelector("#pulseTimeline");
    return tl && tl.querySelectorAll(".pulse-timeline-node").length > 0;
  }, { timeout: 15000 });

  const stats = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll("#pulseTimeline .pulse-timeline-node")];
    return {
      count: nodes.length,
      tones: nodes.map((n) => n.dataset.tone),
      heights: nodes.map((n) => n.style.getPropertyValue("--tl-h")),
      openTasks: nodes.map((n) => n.dataset.openTask).filter(Boolean).length,
      axis: Boolean(document.querySelector("#pulseTimeline .pulse-timeline-axis")),
      kicker: document.querySelector("#pulseTimelineCount")?.textContent || "",
    };
  });
  console.log("timeline probe:", JSON.stringify(stats));
  assert.ok(stats.count >= 3, `expected several nodes, got ${stats.count}`);
  assert.ok(stats.openTasks >= stats.count, "every node carries a task id");
  assert.ok(stats.axis, "axis labels render");
  assert.ok(stats.tones.some((t) => t === "mint"), "completed tasks render mint");
  assert.ok(stats.tones.some((t) => t === "amber"), "cancelled tasks render amber");

  // click a node -> existing data-open-task delegation must open the task detail
  await page.locator("#pulseTimeline .pulse-timeline-node").first().click();
  await page.waitForFunction(() => Boolean(document.querySelector("[role='dialog']:not([hidden]), .task-detail, .panel-immersive")), { timeout: 10000 });
  console.log("delegation: node click routed to task detail");

  const shot = page.locator("#pulseStage");
  await page.waitForTimeout(1200); // let the boot spinner fade and lucide icons paint
  await shot.screenshot({ path: "_probe_timeline_pulse.png" });
  console.log("screenshot saved: _probe_timeline_pulse.png");
  console.log("PROBE PASS");
} finally {
  await browser.close();
}
