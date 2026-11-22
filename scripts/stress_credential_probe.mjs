#!/usr/bin/env node
/**
 * Credential-stuffing / high-concurrency probe for the local workbench.
 *
 * req #11 asks what happens under "撞库" — a dictionary barrage, not just
 * random bearer noise. `stress_auth_probe.py` already covers forged tokens and
 * random bytes; this probe adds the two things it cannot:
 *
 *   A. a real browser typing a weak-password dictionary into the shared admin
 *      door (123 is public by design — what matters is that no other string
 *      opens it and that repeated wrong attempts never leak dashboard data)
 *   B. a re-open stress: close and reopen the admin stage five times, unlock
 *      once, and count actual /api/admin/summary requests. A panel that stacks
 *      an event listener on every open would quietly turn one click into six
 *      fetches — exactly the kind of "looks fine, melts under use" defect this
 *      scenario exists to catch.
 *   C/D. HTTP dictionary flood on token-gated routes + a concurrent read burst
 *        on the admin summary route, checking zero 5xx and service survival.
 *
 * Everything is loopback-only and uses a fake provider: zero model tokens,
 * zero external calls, no production data touched.
 *
 *   node scripts/stress_credential_probe.mjs
 *   node scripts/stress_credential_probe.mjs --json
 */

import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const jsonMode = process.argv.includes("--json");
const DICTIONARY = [
  "admin", "123456", "password", "000000", "111111", "qwerty", "letmein",
  "1234", "12345", "12345678", "root", "test", "guest", "00123", "321",
  "abc123", "123456789", "iloveyou", "监视", "123123", "a123456", "888888",
];
const CORRECT = "123";

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
    } catch { /* still booting */ }
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error("web server never answered /api/health");
}

async function startServer(port) {
  const python = process.env.MINICC_PYTHON || (process.platform === "win32"
    ? resolve(REPO, ".venv/Scripts/python.exe")
    : "python3");
  const env = {
    ...process.env,
    MINICC_FAKE_PROVIDER: "1",
    MINICC_API_KEY: "credential-probe",
    MINICC_BASE_URL: "https://example.invalid/v1",
  };
  // Bind all interfaces so the token gate is actually armed. On loopback the
  // workbench intentionally trusts the local visitor; a stress probe that
  // thinks it tested auth there would be measuring nothing.
  const child = spawn(python, ["-m", "minicc.web", "--workspace", REPO,
    "--host", "0.0.0.0", "--port", String(port), "--token", "credential-probe-token"],
    { cwd: REPO, env, stdio: "ignore" });
  const url = `http://127.0.0.1:${port}`;
  await waitForHealth(url);
  return { url, stop: () => child.kill("SIGTERM") };
}

function record(results, scenario, detail) {
  results.push({ scenario, ...detail });
}

async function burst(url, path, { headers = {}, n, workers, method = "GET" }) {
  const codes = {};
  const elapsed = [];
  let next = 0;
  async function worker() {
    for (;;) {
      const i = next++;
      if (i >= n) return;
      const started = performance.now();
      try {
        const r = await fetch(url + path, { method, headers, signal: AbortSignal.timeout(8000) });
        codes[r.status] = (codes[r.status] || 0) + 1;
      } catch {
        codes[-1] = (codes[-1] || 0) + 1;
      }
      elapsed.push(performance.now() - started);
    }
  }
  await Promise.all(Array.from({ length: workers }, worker));
  const ordered = [...elapsed].sort((a, b) => a - b);
  const pct = (p) => ordered.length ? ordered[Math.min(ordered.length - 1, Math.floor((ordered.length - 1) * p))] : 0;
  return { codes, n, p50_ms: Math.round(pct(0.5)), p95_ms: Math.round(pct(0.95)), p99_ms: Math.round(pct(0.99)) };
}

async function main() {
  const port = await freePort();
  const server = await startServer(port);
  const url = server.url;
  const browser = await chromium.launch({ headless: true });
  const results = [];
  const pageErrors = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 960 },
      extraHTTPHeaders: { Authorization: "Bearer credential-probe-token" },
    });
    const page = await context.newPage();
    page.on("pageerror", (e) => pageErrors.push(e.message));
    await page.addInitScript(() => { try { localStorage.clear(); } catch {} });
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForFunction(() => document.querySelector("#startupSplash")?.dataset.state === "ready",
      null, { timeout: 30000 });
    await page.waitForTimeout(350);

    // --- A. dictionary stuffing at the shared door
    await page.click('.nav-item[data-view="admin"]');
    await page.waitForSelector("#adminStage");
    let wrongOpened = 0;
    const startedA = performance.now();
    for (const candidate of DICTIONARY) {
      await page.fill("#adminPassword", candidate);
      await page.click("#adminUnlockBtn");
      const opened = await page.evaluate(() =>
        !document.querySelector("#adminUnlocked")?.hasAttribute("hidden"));
      if (opened) wrongOpened += 1;
    }
    record(results, "A. weak-password dictionary at the admin door", {
      attempts: DICTIONARY.length,
      wrong_opened: wrongOpened,
      elapsed_ms: Math.round(performance.now() - startedA),
      pass: wrongOpened === 0,
      note: "the shared door is 123 by design; no other dictionary string may open it",
    });
    await page.fill("#adminPassword", CORRECT);
    await page.click("#adminUnlockBtn");
    await page.waitForFunction(() => {
      const el = document.querySelector("#adminTotalTasks");
      return el && el.innerText.trim() && el.innerText.trim() !== "—";
    }, null, { timeout: 45000 });
    const unlocked = await page.evaluate(() =>
      !document.querySelector("#adminUnlocked")?.hasAttribute("hidden"));
    record(results, "A2. the real shared password still works after the barrage", {
      unlocked, pass: unlocked,
      note: "a stuffing probe must not lock out the legitimate visitor",
    });

    // --- B. reopen five times, unlock once, count real network fetches
    let summaryFetches = 0;
    page.on("request", (req) => {
      if (req.url().includes("/api/admin/summary")) summaryFetches += 1;
    });
    for (let i = 0; i < 5; i += 1) {
      await page.click("#adminStageClose");
      await page.click('.nav-item[data-view="admin"]');
      await page.waitForTimeout(90);
    }
    await page.fill("#adminPassword", CORRECT);
    await page.click("#adminUnlockBtn");
    await page.waitForTimeout(1200);
    record(results, "B. reopen x5 then one unlock — listener accumulation", {
      reopens: 5,
      summary_fetches: summaryFetches,
      pass: summaryFetches === 1,
      note: "one click must mean one read; stacked listeners are a latency and load defect",
    });
    await page.close();

    // --- C. HTTP dictionary flood on token-gated routes
    for (const candidate of ["123", "admin", "password", "000000", "letmein", CORRECT]) {
      const b = await burst(url, "/api/commands", {
        headers: { Authorization: `Bearer ${candidate}` }, n: 60, workers: 24,
      });
      const denied = b.codes[401] || 0;
      record(results, `C. bearer dictionary "${candidate}" x60`, {
        ...b, denied, pass: denied === b.n && !b.codes[-1] && !Object.keys(b.codes).some((c) => Number(c) >= 500),
        note: "weak strings are not credentials; all must be refused as 401",
      });
    }

    // --- D. concurrent admin reads while the barrage is over. Two lanes:
    // the summary tile and the model-free advice tile. The latter builds from
    // the journey log inside a memo; an accidental nested lock there would
    // hang exactly under this burst, so it belongs in the pressure matrix.
    const authHeaders = { Authorization: "Bearer credential-probe-token" };
    const reads = await burst(url, "/api/admin/summary", {
      headers: authHeaders, n: 240, workers: 32,
    });
    const served = reads.codes[200] || 0;
    record(results, "D1. admin summary read burst 240 / c=32", {
      ...reads, served, pass: served === reads.n,
      note: "the shared admin tile must survive many simultaneous readers",
    });
    const advice = await burst(url, "/api/visitor-advice", {
      headers: authHeaders, n: 240, workers: 32,
    });
    const advised = advice.codes[200] || 0;
    record(results, "D2. model-free advice burst 240 / c=32", {
      ...advice, served: advised, pass: advised === advice.n,
      note: "rule-derived advice must not deadlock or 5xx under a concurrent burst",
    });

    // --- E. aftermath
    const health = await fetch(url + "/api/health", { signal: AbortSignal.timeout(5000) });
    const commands = await fetch(url + "/api/commands", {
      headers: { Authorization: "Bearer credential-probe-token" },
      signal: AbortSignal.timeout(5000),
    });
    record(results, "E. aftermath — health and authorized lane", {
      health: health.status, commands: commands.status,
      pass: health.status === 200 && commands.status === 200,
      note: "the service must still be whole after the barrage",
    });
  } finally {
    await browser.close();
    server.stop();
  }

  const pass = results.every((r) => r.pass) && pageErrors.length === 0;
  const report = { pass, results, pageErrors };
  if (jsonMode) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } else {
    for (const r of results) {
      process.stdout.write(`${r.pass ? "PASS" : "FAIL"} ${r.scenario}`);
      if (r.wrong_opened !== undefined) process.stdout.write(` wrong_opened=${r.wrong_opened}`);
      if (r.summary_fetches !== undefined) process.stdout.write(` fetches=${r.summary_fetches}`);
      if (r.codes) process.stdout.write(` codes=${JSON.stringify(r.codes)} p95=${r.p95_ms}ms`);
      if (r.served !== undefined) process.stdout.write(` served=${r.served}`);
      process.stdout.write(`\n     ${r.note}\n`);
    }
    for (const e of pageErrors) process.stdout.write(`FAIL pageerror ${e}\n`);
    process.stdout.write(pass ? "credential probe: PASS\n" : "credential probe: FAIL\n");
  }
  process.exitCode = pass ? 0 : 1;
}

main().catch((error) => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 2;
});
