// M8-T537: every suite that runs before the product path names itself when it
// fails. The mutation verdict accepts only the product-path completion code, so
// a timeline/desktop/mobile assertion failure must reach the log as a named
// code instead of "the smoke exited 1 without naming a failure code".
//
// This module exists so a node child can exercise the emit path without
// launching Chromium: tests/test_the_other_suites_name_themselves_too.py
// imports it and drives both directions (a throwing run prints one code, a
// passing run prints none).

import { get as httpRequest } from "node:http";

function announce(code) {
  console.error(`SMOKE_FAILURE_CODE=${code}`);
}

// The announcement and the exit are not the same instruction: on a redirected
// stderr a write is queued, and a process.exit taken in the same turn can end the
// process before the line the step exists to report reaches the log. So the code
// is published first and taken one turn later. (This is not what stopped the
// libuv abort measured in M8-T1321 - deferring the exit did nothing for it, since
// it was the probe's own open socket, not the timing; see
// closedSocketHealthCall.)
export function deferredExit(code) {
  process.exitCode = code;
  setTimeout(() => process.exit(code), 0);
}

// M8-T1304: a suite whose own server is not running has executed zero
// assertions, but it reported that as a product failure. Playwright raises
// "page.goto: net::ERR_CONNECTION_REFUSED" a few seconds after launching a
// browser, and the failure that reaches the log is the suite's own: measured
// against a port with nothing bound, web_smoke.mjs exited 1 naming
// TIMELINE_SUITE_FAILED - a product suite that never ran - while admin, orbit,
// en_cjk and manual each exited 1 naming nothing at all. The probe answers in
// milliseconds, before any browser is launched, and names itself, so "the
// harness was not there" is a sentence the log can tell apart from "the product
// path did not complete".
export const HARNESS_PROBE_PATH = "/api/health";
export const HARNESS_UNREACHABLE_CODE = "HARNESS_UNREACHABLE";
export const HARNESS_UNREACHABLE_EXIT = 3;
export const HEALTH_PROBE_TIMEOUT_MS = 4000;

// The probe asks a question of a process that is about to die, so it has to put
// nothing back. Measured here, on this box: `globalThis.fetch` answers through
// undici and keeps its pooled socket for seconds afterwards (4.17s of held event
// loop after one health call, against 0.91s for the call below), and a
// `process.exit` taken with that handle mid-close does not exit at all - it aborts
// in libuv ("Assertion failed: !(handle->flags & UV_HANDLE_CLOSING),
// src\win\async.c", 0xC0000409) three runs out of three. A step that died asking
// its own question would be the second version of the defect this batch is about:
// the harness failing in a way the log cannot tell from a product failure. So this
// transport is a one-shot GET - no agent, `connection: close` - that resolves only
// once its socket has actually closed, with a guard timer so a socket that never
// closes is an answer ("never saw its socket close") rather than a hang.
export function closedSocketHealthCall(url, { timeoutMs = HEALTH_PROBE_TIMEOUT_MS } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let guard;
    const settle = (deliver) => {
      if (settled) return;
      settled = true;
      clearTimeout(guard);
      deliver();
    };
    const request = httpRequest(
      url,
      { agent: false, headers: { connection: "close" }, timeout: timeoutMs },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => {
          response.destroy();
          const answer = {
            ok: response.statusCode >= 200 && response.statusCode < 300,
            status: response.statusCode,
            json: async () => JSON.parse(body),
          };
          request.on("close", () => settle(() => resolve(answer)));
        });
        response.on("error", (error) => settle(() => reject(error)));
      },
    );
    request.on("error", (error) => settle(() => reject(error)));
    request.on("timeout", () => request.destroy(new Error(`health probe got no answer in ${timeoutMs}ms`)));
    guard = setTimeout(
      () =>
        settle(() =>
          reject(new Error(`health probe never saw its socket close (asked ${timeoutMs}ms ago)`)),
        ),
      timeoutMs + 1000,
    );
  });
}

export async function requireHarness(
  baseUrl,
  { fetchImpl = closedSocketHealthCall, timeoutMs = HEALTH_PROBE_TIMEOUT_MS } = {},
) {
  const probeUrl = new URL(HARNESS_PROBE_PATH, baseUrl).href;
  let response;
  try {
    response = await fetchImpl(probeUrl, { timeoutMs });
  } catch (error) {
    const kind = error?.code || error?.cause?.code || error?.name || "Error";
    const reason = error?.cause?.message || error?.message || "no detail";
    return { ok: false, probeUrl, detail: `${kind}: ${reason}` };
  }
  if (!response?.ok) {
    return { ok: false, probeUrl, detail: `answered HTTP ${response?.status ?? "no response"}` };
  }
  const payload = await response.json().catch(() => null);
  if (payload?.ok !== true || payload?.service !== "minicc") {
    return {
      ok: false,
      probeUrl,
      detail: `answered ${JSON.stringify(payload)} where the minicc health payload was expected`,
    };
  }
  return { ok: true, probeUrl };
}

export async function requireHarnessOrExit(
  baseUrl,
  { exitImpl = deferredExit, ...probeOptions } = {},
) {
  const harness = await requireHarness(baseUrl, probeOptions);
  if (harness.ok) {
    // M8-T1321: the probe proved the server was there when the suite started. A
    // server that goes away mid-suite used to leave only whatever Playwright
    // happened to raise - measured with the same port killed 4s in, admin named
    // its own context-tile assertion, stategraph and orbit each died with a bare
    // Playwright stack, and none of the three named a code. From here on the
    // process answers for that itself.
    watchHarnessLoss(baseUrl, { exitImpl });
    return harness;
  }
  announce(HARNESS_UNREACHABLE_CODE);
  console.error(
    [
      `${HARNESS_UNREACHABLE_CODE}: the server this smoke drives is not answering at ${harness.probeUrl} (${harness.detail}).`,
      "Start one (python -m minicc.web --workspace . --port <port>) or point MINICC_WEB_URL at one that is already running.",
      `The suite is exiting ${HARNESS_UNREACHABLE_EXIT} without launching a browser: no suite ran, so nothing this step ` +
        "reports says anything about the product.",
    ].join(" "),
  );
  return exitImpl(HARNESS_UNREACHABLE_EXIT);
}

// M8-T1321: the shapes only a missing server can produce. A product assertion
// cannot write any of them, which is why an error outside this list is left to
// Node exactly as it is: the suite's own failure stays the suite's own verdict.
export const HARNESS_LOST_CODE = "HARNESS_LOST";
export const HARNESS_LOST_EXIT = 3;
export const HARNESS_LOSS_SHAPES = [
  "net::ERR_CONNECTION_REFUSED",
  "net::ERR_CONNECTION_RESET",
  "net::ERR_CONNECTION_ABORTED",
  "net::ERR_NETWORK_CHANGED",
  "net::ERR_INTERNET_DISCONNECTED",
  "net::ERR_ADDRESS_UNREACHABLE",
  "ECONNREFUSED",
  "ECONNRESET",
  "ECONNABORTED",
  "EHOSTUNREACH",
  "ENETUNREACH",
  "socket hang up",
  "Target page, context or browser has been closed",
];

export function isHarnessLossShape(error) {
  const text = [error?.message, error?.name, error?.code, error?.cause?.code, error?.cause?.message]
    .filter((part) => typeof part === "string")
    .join(" ");
  return HARNESS_LOSS_SHAPES.some((shape) => text.includes(shape));
}

// The one place that decides "the server went away" and says it. Suites reach it
// from the process-level hook below, or from their own collected-error exit when
// they swallow their failures instead of throwing them.
export async function exitIfHarnessLost(
  baseUrl,
  {
    exitImpl = deferredExit,
    probe = () => requireHarness(baseUrl),
    writeImpl = (line) => console.error(line),
    lastWords = "",
    contextNote = "",
  } = {},
) {
  const harness = await probe();
  if (harness.ok) return false;
  announce(HARNESS_LOST_CODE);
  writeImpl(
    [
      `${HARNESS_LOST_CODE}: this smoke drove ${baseUrl}, whose server stopped answering while the suite was running`,
      `(${harness.detail ?? "the probe could not reach it"}${contextNote ? `; ${contextNote}` : ""}).`,
      `The suite had run partway, so this step has partial coverage and no product verdict: it names neither a caught`,
      `mutation nor a missed one. It is exiting ${HARNESS_LOST_EXIT}; restart the server and re-run for the answer.`,
      // The suite's own words stay in the log: a server that died because the
      // product crashed it is still evidence of the crash, not of the harness.
      lastWords ? `The suite's last words were: ${lastWords.split("\n")[0].slice(0, 200)}` : "",
    ]
      .filter(Boolean)
      .join(" "),
  );
  exitImpl(HARNESS_LOST_EXIT);
  return true;
}

let harnessLossWatch = null;

export function watchHarnessLoss(
  baseUrl,
  { exitImpl = deferredExit, probe, writeImpl = (line) => console.error(line) } = {},
) {
  if (harnessLossWatch) return harnessLossWatch;
  const state = { baseUrl, answered: false, listeners: 0, probed: 0 };
  const handler = async (error) => {
    if (state.answered) return;
    state.answered = true;
    // Measured on this repository: with the server killed a few seconds into a
    // run, the suite's own last words were a connection error (orbit), a
    // "Failed to fetch" (stategraph), a product assertion about the panel's
    // context tile (admin) and, worst of all, a real PRODUCT_PATH_* code (web).
    // The shape of the failure therefore cannot be the judge - an assertion that
    // quotes Playwright's own sentence would convict the product for a dead
    // server, and a suite that hangs would acquit one. The server answers that
    // question directly, so it is asked, and only it decides.
    state.probed += 1;
    const lost = await exitIfHarnessLost(baseUrl, {
      exitImpl,
      writeImpl,
      probe,
      lastWords: String(error?.message ?? error),
      contextNote: isHarnessLossShape(error) ? "the failure named a connection error too" : "",
    });
    if (lost) return;
    // The server answers and the suite still failed: that is the product's, and
    // it keeps exactly the stack Node would have printed on its own.
    writeImpl(error?.stack ?? String(error));
    exitImpl(1);
  };
  process.on("uncaughtException", handler);
  process.on("unhandledRejection", handler);
  state.listeners =
    process.listenerCount("uncaughtException") + process.listenerCount("unhandledRejection");
  harnessLossWatch = state;
  return state;
}

export async function runNamedSuite(code, run) {
  try {
    return await run();
  } catch (error) {
    // The product path names its own (finer) code; an outer wrapper must not
    // print a second code that would shadow it, because the verdict keeps the
    // last code in the log.
    if (!error?.smokeCodeNamed) announce(code);
    throw error;
  }
}

export function failProductPath(code, message) {
  announce(code);
  const error = new Error(message);
  error.smokeCodeNamed = true;
  throw error;
}
