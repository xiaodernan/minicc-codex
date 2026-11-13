// M8-T908 probe: the prefix strip renders inside a real task detail modal.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8899";
const TASK = process.env.PROBE_TASK || "task-104ec81fed2b"; // a T907-fingerprinted real task
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(BASE, { waitUntil: "commit" });
  await page.waitForSelector("#promptInput", { timeout: 20000 });

  // open the task detail through the same body delegation the archive rows use
  await page.evaluate((id) => {
    const btn = document.createElement("button");
    btn.setAttribute("data-open-detail", id);
    btn.style.display = "none";
    (document.querySelector("#panelBody") || document.body).appendChild(btn);
    btn.click();
    btn.remove();
  }, TASK);
  await page.waitForFunction(() => Boolean(document.querySelector(".task-detail")), TASK, { timeout: 15000 });
  // the detail modal opens via data-open-task delegation from the palette row
  await page.waitForFunction(() => Boolean(document.querySelector(".prefix-strip")), { timeout: 10000 });

  const stats = await page.evaluate(() => {
    const rows = [...document.querySelectorAll(".prefix-strip-row")];
    return {
      rows: rows.length,
      tones: rows.map((r) => r.querySelector("b")?.dataset.tone),
      sample: rows[0]?.textContent.replace(/\s+/g, " ").trim().slice(0, 120),
    };
  });
  console.log("prefix strip probe:", JSON.stringify(stats));
  assert.ok(stats.rows >= 2, `expected fingerprint rows from a T907 task, got ${stats.rows}`);
  assert.ok(stats.tones.includes("mint") || stats.tones.includes("rose"), "rates are toned");
  console.log("PROBE PASS");
} finally {
  await browser.close();
}
