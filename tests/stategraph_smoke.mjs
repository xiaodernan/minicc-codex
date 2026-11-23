import assert from "node:assert/strict";
import { chromium } from "playwright";
import { exitIfHarnessLost, requireHarnessOrExit } from "./web_smoke_suites.mjs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8899";

await requireHarnessOrExit(baseUrl);

const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale) {
  const isZh = locale === "zh";
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => { localStorage.setItem("minicc-locale", l); }, locale);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });

  // Palette-first: the StateGraph is reached through Ctrl/Cmd+K, not the nav.
  await page.keyboard.press("Control+k");
  await page.waitForSelector("#paletteInput", { timeout: 8000 });
  await page.fill("#paletteInput", isZh ? "状态图" : "stategraph");
  await page.keyboard.press("Enter");

  await page.waitForSelector(".stategraph-lane .stategraph-node", { timeout: 15000 });
  await page.waitForTimeout(1200); // two-phase swap: replica paints, live wires in

  const count = await page.locator(".stategraph-node").count();
  assert.equal(count, 7, `expected seven nodes, saw ${count}`);

  // The badge must flip from replica to live once /api/stategraph answers.
  const badge = await page.locator("#stategraphBadge").innerText();
  assert.ok(
    isZh ? badge.includes("实时") : badge.toLowerCase().includes("live"),
    `badge must say live after the wire answers, saw: ${badge}`,
  );

  // Guards strip: live signature defaults, not hand-typed numbers.
  const guards = (await page.locator("#stategraphGuards .stategraph-guard-value").allInnerTexts()).map((s) => s.trim());
  assert.deepEqual(guards, ["32", "16", "4", "64"], `guards must be 32/16/4/64, saw ${guards}`);

  // Routing strip carries the five routed stages.
  const routeRows = await page.locator("#stategraphRouting .stategraph-routing-row").count();
  assert.ok(routeRows >= 5, `routing strip must list five stages, saw ${routeRows}`);

  // The payload behind the panel, verified at its own boundary.
  const payload = await page.evaluate(async () => {
    const res = await fetch("/api/stategraph", { cache: "no-store" });
    return res.json();
  });
  assert.equal(payload.name, "coding");
  assert.equal(payload.entry, "intake");
  assert.equal(payload.nodes.length, 7);
  assert.equal(payload.edges.length, 8);
  assert.deepEqual(payload.guards, { max_nodes: 32, max_depth: 16, max_parallel: 4, max_steps: 64 });
  assert.ok(Array.isArray(payload.routing.stages));
  assert.equal(payload.routing.stages.length, 5);
  assert.ok(payload.routing.stages.every((s) => typeof s.model === "string" && s.model.length > 0));

  // Click a node and drive the detail pane to it.
  await page.click('.stategraph-node[data-node="repair"]');
  const detail = await page.locator("#stategraphDetail").innerText();
  assert.ok(detail.includes("repair"), `detail must show repair, saw: ${detail.slice(0, 120)}`);

  await page.close();
}

await checkMode("zh");
await checkMode("en");

if (errors.length) {
  console.error("stategraph smoke FAILED:");
  for (const e of errors) console.error(" ", e);
  await exitIfHarnessLost(baseUrl);
  process.exit(1);
}
console.log("stategraph smoke passed: palette opens panel, live badge flips, guards 32/16/4/64 from the runtime, routing strip lists five stages, seven nodes render bilingual, zero pageerror");
await browser.close();
