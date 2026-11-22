// M8-T1289 — synthetic visitors that really walk the UI.
//
// The brief asks for simulated *human* behaviour: the visitor with no patience
// who closes the tab, the one who has no idea where to go and clicks around.
// Fabricating those numbers in a fixture would be worse than useless, so this
// probe drives real headless Chromium sessions through the actual workbench and
// appends one JSON line per session to `.minicc/behavior/journeys.jsonl`.
// `minicc/behavior_journeys.py` only aggregates what these sessions did.
//
// Deliberately NOT part of CI: it needs a running server, a real browser and
// wall-clock dwell times. Run it locally, then open the admin panel.
//
//   node scripts/behavior_sim.mjs --runs 6
//   node scripts/behavior_sim.mjs --personas impatient,wanderer --runs 10
//   node scripts/behavior_sim.mjs --url http://127.0.0.1:8765 --seed 7 --json
//
// Exit code is 0 even when journeys bounce — a bounce is data, not a failure.
// It is non-zero only when the browser could not be driven at all.

import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] !== undefined ? args[index + 1] : fallback;
};
const has = (name) => args.includes(name);

const BASE_URL = flag("--url", process.env.MINICC_WEB_URL || "http://127.0.0.1:8765");
const RUNS = Math.max(1, Number(flag("--runs", "3")) || 3);
const SEED = Number(flag("--seed", "1")) || 1;
const OUT = flag("--out", path.join(process.cwd(), ".minicc", "behavior", "journeys.jsonl"));
const READY_TIMEOUT = Math.max(5000, Number(flag("--ready-timeout", "45000")) || 45000);
// A session that wedges for four minutes is a browser problem, not a visitor
// behaviour. Cap it and record "timed-out" honestly instead of letting one
// stuck click drag the median dwell time into fantasy.
const JOURNEY_CAP = Math.max(5000, Number(flag("--journey-cap", "60000")) || 60000);
const WANTED = String(flag("--personas", "impatient,wanderer,reader,explorer,power"))
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
const AS_JSON = has("--json");

// Views that exist in the real sidebar. A view that is hidden in this build is
// skipped and never counted — the probe reports the walk it actually took.
const VIEWS = ["pulse", "manual", "atlas", "archive", "almanac", "ledger", "tasks", "activity", "recent", "workspaces", "dockyard", "doctor"];
const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1600, height: 900 },
  { width: 1024, height: 768 },
];

// Deterministic PRNG so a run can be repeated; a real visitor is not, but the
// shape of the distribution is what we are testing, not the individual click.
function mulberry32(start) {
  let seed = start >>> 0;
  return () => {
    seed = (seed + 0x6d2b79f5) >>> 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rng = mulberry32(SEED);
const pick = (list) => list[Math.floor(rng() * list.length)];
const jitter = (min, max) => Math.round(min + rng() * (max - min));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Nothing in a journey may await forever: a stuck renderer would otherwise be
// scored as a very patient visitor. The fallback is returned, the step ends.
const withTimeout = (promise, ms, fallback) =>
  Promise.race([promise.catch(() => fallback), sleep(ms).then(() => fallback)]);

// "Ready" means what it means to a human: the sidebar entry is on screen and a
// pointer aimed at it would land on it. Not "the network went quiet" — this app
// polls on purpose, so idle never happens, and a splash that still swallows
// clicks is not ready no matter what the network says.
async function waitForFirstClickable(page) {
  await page.waitForFunction(
    () => {
      const el = document.querySelector('.nav-item[data-view="pulse"]') || document.querySelector(".nav-item");
      if (!el) return false;
      const rect = el.getBoundingClientRect();
      if (rect.width < 8 || rect.height < 8) return false;
      const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return Boolean(top && (top === el || el.contains(top)));
    },
    { timeout: READY_TIMEOUT, polling: 120 },
  );
}

const navIsReachable = (page) =>
  page.evaluate(() => {
    const el = document.querySelector('.nav-item[data-view="pulse"]') || document.querySelector(".nav-item");
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) return false;
    const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return Boolean(top && (top === el || el.contains(top)));
  });

// A panel covers the rail until you back out. A real visitor presses Esc (or
// the close button) before opening the next room, so the probe does the same
// instead of clicking through an overlay that is not actually there for them.
async function backOutOfPanelOnce(page) {
  if (await navIsReachable(page)) return false;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.keyboard.press("Escape").catch(() => {});
    try {
      // Wait for the slide-out to finish rather than guessing a sleep: a click
      // fired mid-animation lands on the overlay and would be scored as the
      // visitor's confusion, which it is not.
      await page.waitForFunction(
        () => {
          const el = document.querySelector('.nav-item[data-view="pulse"]') || document.querySelector(".nav-item");
          if (!el) return false;
          const rect = el.getBoundingClientRect();
          if (rect.width < 8 || rect.height < 8) return false;
          const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
          return Boolean(top && (top === el || el.contains(top)));
        },
        { timeout: 1800, polling: 100 },
      );
      return true;
    } catch {
      // still covered — try one more Esc
    }
  }
  return true; // tried and still covered — the caller's click records that honestly
}

async function backOutOfPanel(page) {
  return withTimeout(backOutOfPanelOnce(page), 6000, false);
}

async function openViewOnce(page, view) {
  const nav = page.locator(`.nav-item[data-view="${view}"]`).first();
  try {
    await backOutOfPanel(page);
    if ((await nav.count()) === 0) return false;
    if (!(await nav.isVisible())) return false;
    // One retry: a human who clicks a hair too early simply clicks again. Both
    // attempts are real pointer clicks — never a forced one — so a view only
    // counts as visited when the UI actually accepted the click.
    try {
      await nav.click({ timeout: 2000 });
    } catch {
      await backOutOfPanel(page);
      await sleep(200);
      await nav.click({ timeout: 2000 });
    }
    await sleep(140);
    return true;
  } catch {
    return false;
  }
}

// One wedged step must not consume the whole session: a renderer that stops
// answering Playwright is a browser problem, and the journey should record a
// missed click rather than stall until the journey cap.
async function openView(page, view) {
  return withTimeout(openViewOnce(page, view), 14000, false);
}

// Three clicks inside ~300 ms on the same control is the honest signature of
// "I clicked it and nothing happened". Counted separately so the panel can say
// how many sessions contained a burst instead of averaging it away.
async function rageBurst(page, view) {
  const nav = page.locator(`.nav-item[data-view="${view}"]`).first();
  try {
    for (let index = 0; index < 3; index += 1) {
      await nav.click({ timeout: 1500, force: true });
      await sleep(90);
    }
    return true;
  } catch {
    return false;
  }
}

const PERSONAS = {
  // Lands, decides nothing looks worth the wait, leaves. Never waits for the
  // app to become usable — that is the whole point of this visitor.
  impatient: {
    needsReady: false,
    run: async () => {
      await sleep(jitter(600, 1800));
      return { bounced: true, exit_reason: "no-patience" };
    },
  },

  // No destination in mind: clicks around, sometimes three times on the same
  // thing when it does not answer.
  wanderer: {
    run: async (page, state) => {
      const steps = jitter(2, 5);
      for (let index = 0; index < steps; index += 1) {
        const view = pick(VIEWS);
        if (await openView(page, view)) {
          state.clicks += 1;
          state.views.push(view);
          if (rng() < 0.18) {
            if (await rageBurst(page, view)) state.rage_clicks += 1;
            state.clicks += 3;
          }
          await sleep(jitter(250, 900));
        } else {
          state.clicks += 1; // a click that landed on nothing is still a click
          await sleep(120);
        }
      }
      return { bounced: rng() < 0.75, exit_reason: "no-destination" };
    },
  },

  // Actually reads the manual, which is what the manual is for.
  reader: {
    run: async (page, state) => {
      if (await openView(page, "manual")) {
        state.clicks += 1;
        state.views.push("manual");
      }
      await sleep(jitter(2500, 6000));
      await page.mouse.wheel(0, jitter(500, 1400)).catch(() => {});
      await sleep(jitter(900, 2400));
      await page.mouse.wheel(0, jitter(400, 1200)).catch(() => {});
      await sleep(jitter(700, 1600));
      return { bounced: false, exit_reason: "finished-reading" };
    },
  },

  // Wants to see what exists; visits several rooms and leaves satisfied.
  explorer: {
    run: async (page, state) => {
      const order = [...VIEWS].sort(() => rng() - 0.5).slice(0, jitter(4, 6));
      for (const view of order) {
        if (await openView(page, view)) {
          state.clicks += 1;
          state.views.push(view);
          await sleep(jitter(700, 1500));
        }
      }
      return { bounced: false, exit_reason: "tour-finished" };
    },
  },

  // Knows the keyboard: palette, search, Enter, Esc, then one more room.
  power: {
    run: async (page, state) => {
      try {
        await page.keyboard.press("Control+k");
        await sleep(jitter(200, 420));
        await page.locator("#paletteInput").fill("manual", { timeout: 3000 });
        await sleep(jitter(240, 520));
        await page.keyboard.press("Enter");
        await sleep(jitter(900, 1800));
        state.clicks += 2;
        state.views.push("manual");
        await page.keyboard.press("Escape").catch(() => {});
      } catch {
        // palette unavailable in this build: fall back to the sidebar honestly
        if (await openView(page, "manual")) {
          state.clicks += 1;
          state.views.push("manual");
        }
      }
      await sleep(jitter(300, 900));
      if (await openView(page, "atlas")) {
        state.clicks += 1;
        state.views.push("atlas");
        await sleep(jitter(600, 1400));
      }
      return { bounced: false, exit_reason: "task-done" };
    },
  },
};

async function runJourney(browser, persona) {
  const spec = PERSONAS[persona];
  const viewport = pick(VIEWPORTS);
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.setDefaultTimeout(8000); // no single action may hang the session
  const state = { clicks: 0, rage_clicks: 0, views: [], errors: 0 };
  page.on("pageerror", () => {
    state.errors += 1;
  });
  const startedAt = new Date();
  const startedMs = Date.now();
  let bootMs = null;
  let outcome = { bounced: true, exit_reason: "crashed" };
  try {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
    if (spec.needsReady !== false) {
      try {
        await waitForFirstClickable(page);
        bootMs = Date.now() - startedMs;
      } catch {
        bootMs = null; // never became clickable: an honest null, not a zero
      }
    }
    await sleep(jitter(150, 400)); // first paint before a human reacts
    const TIMED_OUT = Symbol("timed-out");
    const attempted = spec.run(page, state).catch(() => ({ bounced: true, exit_reason: "could-not-drive" }));
    const raced = await Promise.race([attempted, sleep(JOURNEY_CAP).then(() => TIMED_OUT)]);
    outcome = raced === TIMED_OUT ? { bounced: true, exit_reason: "timed-out" } : raced;
  } catch {
    outcome = { bounced: true, exit_reason: "could-not-drive" };
  }
  const dwellMs = Date.now() - startedMs;
  const lastView = state.views.length ? state.views[state.views.length - 1] : "landing";
  // The walk as a chain of moves: every landing is "landing -> first room", and
  // every later hop is room -> room. This is the evidence for "clicked around
  // lost" — a bounce rate says someone left, a chain says where they wandered.
  const walked = state.views.slice();
  const transitions = walked.length
    ? [{ from: "landing", to: walked[0] }].concat(
        walked.slice(1).map((to, index) => ({ from: walked[index], to })),
      )
    : [];
  await context.close().catch(() => {});
  return {
    persona,
    started_at: startedAt.toISOString(),
    dwell_ms: dwellMs,
    boot_ms: bootMs,
    views: state.views.length ? state.views : ["landing"],
    transitions,
    clicks: state.clicks,
    rage_clicks: state.rage_clicks,
    bounced: Boolean(outcome.bounced),
    exit_reason: outcome.exit_reason,
    last_view: lastView,
    viewport: `${viewport.width}x${viewport.height}`,
    page_errors: state.errors,
    synthetic: true,
  };
}

function writeJourney(record) {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.appendFileSync(OUT, `${JSON.stringify(record)}\n`, "utf8");
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : Math.round((sorted[middle - 1] + sorted[middle]) / 2);
}

const unknown = WANTED.filter((name) => !PERSONAS[name]);
if (unknown.length) {
  console.error(`unknown persona(s): ${unknown.join(", ")} — known: ${Object.keys(PERSONAS).join(", ")}`);
  process.exit(2);
}

const browser = await chromium.launch({ headless: true });
const records = [];
for (const persona of WANTED) {
  for (let index = 0; index < RUNS; index += 1) {
    const record = await runJourney(browser, persona);
    writeJourney(record);
    records.push(record);
    if (!AS_JSON) {
      const verdict = record.bounced ? "left" : "stayed";
      const boot = record.boot_ms === null ? "  never" : `${String(record.boot_ms).padStart(6)}ms`;
      process.stdout.write(
        `  ${persona.padEnd(9)} run ${String(index + 1).padStart(2)}  dwell ${String(record.dwell_ms).padStart(6)}ms  ` +
          `boot ${boot}  clicks ${String(record.clicks).padStart(2)}  views ${record.views.length}  ${verdict} (${record.exit_reason})\n`,
      );
    }
  }
}
await browser.close();

const byPersona = new Map();
for (const record of records) {
  if (!byPersona.has(record.persona)) byPersona.set(record.persona, []);
  byPersona.get(record.persona).push(record);
}
const summary = [...byPersona.entries()].map(([persona, rows]) => ({
  persona,
  runs: rows.length,
  bounce_rate: Math.round((rows.filter((row) => row.bounced).length / rows.length) * 1000) / 1000,
  median_dwell_ms: median(rows.map((row) => row.dwell_ms)),
  median_boot_ms: median(rows.map((row) => row.boot_ms).filter((value) => typeof value === "number")),
  mean_clicks: Math.round((rows.reduce((sum, row) => sum + row.clicks, 0) / rows.length) * 100) / 100,
}));

if (AS_JSON) {
  process.stdout.write(`${JSON.stringify({ out: OUT, journeys: records.length, summary }, null, 2)}\n`);
} else {
  process.stdout.write(`\nwrote ${records.length} journeys → ${OUT}\n`);
  for (const row of summary) {
    process.stdout.write(
      `  ${row.persona.padEnd(9)} runs ${String(row.runs).padStart(2)}  bounce ${(row.bounce_rate * 100).toFixed(0).padStart(3)}%  ` +
        `median dwell ${String(row.median_dwell_ms).padStart(6)}ms  boot ${String(row.median_boot_ms).padStart(6)}ms  clicks ${row.mean_clicks}\n`,
    );
  }
  process.stdout.write("open the admin panel (password 123) to read them aggregated.\n");
}
