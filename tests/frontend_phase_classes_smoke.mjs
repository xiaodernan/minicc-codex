// M8-T370: the live-task element carries one CSS class per phase, and the
// class of a phase the task has left must not survive.
//
// The list of phases used to be written out by hand in two places, and the
// two copies had already drifted: one knew about the ``review`` phase and
// the other did not.  A phase that was not on the list was never removed,
// so the element kept ``live-task-review`` (and ``live-task-verify``) for
// the rest of the task's life - two mutually exclusive styles fighting over
// the same property, and the winner decided by the stylesheet's order
// rather than by the task's state.
//
// This gate drives the **real** module: it loads ``core/api.js`` in the
// page and calls the real ``updateLiveTask``, so a hand-written list is
// caught where it actually lives.  (A gate that only read the shared
// collection would have stayed green while the hand-written copy came
// back - which is exactly what the first version of this gate did.)

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

// The phases the backend emits.  Read from **every** module under minicc/
// so this list cannot drift away from it either - and so a phase that only
// some module emits is still covered.
const backendPhases = new Set();
async function walkBackend(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walkBackend(full);
    } else if (entry.name.endsWith(".py")) {
      const source = await readFile(full, "utf8");
      for (const match of source.matchAll(/"phase":\s*"([a-z_]+)"/g)) backendPhases.add(match[1]);
      for (const match of source.matchAll(/\bphase\s*=\s*"([a-z_]+)"/g)) backendPhases.add(match[1]);
    }
  }
}
await walkBackend("minicc");
const emittedPhases = backendPhases;
for (const phase of ["review", "verify", "repair", "execution", "permission", "intake", "summarize"]) {
  assert(emittedPhases.has(phase), `the backend is expected to emit the ${phase} phase`);
}

const browser = await chromium.launch({ headless: true });
const errors = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("minicc-session", "shared");
  });
  await page.route("http://phase.test/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/workspace") return route.fulfill({ json: { path: "A", name: "A" } });
    if (path === "/api/tasks") return route.fulfill({ json: { tasks: [] } });
    if (path.startsWith("/api/")) return route.fulfill({ json: {} });
    try {
      return route.fulfill({
        body: await readFile(`web${path === "/" ? "/index.html" : path}`),
        contentType: path.endsWith(".js") ? "text/javascript" : path.endsWith(".css") ? "text/css" : "text/html",
      });
    } catch {
      return route.fulfill({ status: 404 });
    }
  });
  await page.goto("http://phase.test/");
  await page.waitForFunction(() => document.querySelector("#startupSplash").dataset.state === "ready");

  // Walk the real page's live-task element through the phases the backend
  // actually emits, using the page's own updateLiveTask.
  const outcome = await page.evaluate(async (phases) => {
    const { updateLiveTask } = await import("/src/core/api.js");
    const holder = document.createElement("div");
    holder.id = "phase-probe";
    holder.innerHTML = '<div class="message-body"><div data-live-task class="live-task"></div></div>';
    document.body.append(holder);
    const live = holder.querySelector("[data-live-task]");
    const leftovers = [];
    for (const phase of phases) {
      updateLiveTask("phase-probe", { status: "running", phase, task_id: "probe" });
      const classes = [...live.classList].filter((c) => c.startsWith("live-task-") && c !== "live-task");
      if (classes.length !== 1) leftovers.push([phase, classes]);
    }
    holder.remove();
    return leftovers;
  }, [...emittedPhases].filter((p) => !["completed", "failed", "cancelled", "interrupted"].includes(p)));

  assert.deepEqual(
    outcome,
    [],
    `the live-task element kept a stale phase class: ${JSON.stringify(outcome)}`,
  );

  // The other half of the same defect: a phase the frontend cannot name
  // does not leave a stale class behind - it is *normalised away* to
  // "planning", and its label falls back to the generic "working".  The
  // user watching a task in the "verify" or "summarize" phase therefore
  // sees neither the phase nor its name.
  const labels = await page.evaluate(async (phases) => {
    const { phaseLabel, phaseClass } = await import("/src/panels/index.js");
    return phases.map((phase) => ({
      phase,
      label: phaseLabel({ status: "running", phase }),
      className: phaseClass({ status: "running", phase }),
    }));
  }, [...emittedPhases].filter((p) => !["completed", "failed", "cancelled", "interrupted"].includes(p)));

  const unnamed = labels.filter((entry) => entry.label === "Working" || entry.label === "执行中");
  assert.deepEqual(
    unnamed,
    [],
    `these phases fall back to the generic "working" label, so the user never sees them: ${JSON.stringify(unnamed)}`,
  );
  const mislabelled = labels.filter((entry) => entry.className !== entry.phase);
  assert.deepEqual(
    mislabelled,
    [],
    `these phases are normalised to another phase's class, so the live task shows the wrong state: ${JSON.stringify(mislabelled)}`,
  );
} finally {
  await browser.close();
}

assert.deepEqual(errors, [], `the page raised errors: ${errors.join("; ")}`);
console.log("M8-T370 ok: the live-task element keeps exactly one phase class");
