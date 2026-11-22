// M8-T537: every suite that runs before the product path names itself when it
// fails. The mutation verdict accepts only the product-path completion code, so
// a timeline/desktop/mobile assertion failure must reach the log as a named
// code instead of "the smoke exited 1 without naming a failure code".
//
// This module exists so a node child can exercise the emit path without
// launching Chromium: tests/test_the_other_suites_name_themselves_too.py
// imports it and drives both directions (a throwing run prints one code, a
// passing run prints none).

function announce(code) {
  console.error(`SMOKE_FAILURE_CODE=${code}`);
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

export async function requireHarness(baseUrl, { fetchImpl = globalThis.fetch, timeoutMs = 4000 } = {}) {
  const probeUrl = new URL(HARNESS_PROBE_PATH, baseUrl).href;
  let response;
  try {
    response = await fetchImpl(probeUrl, { signal: AbortSignal.timeout(timeoutMs) });
  } catch (error) {
    const kind = error?.cause?.code || error?.name || "Error";
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
  { exitImpl = (code) => process.exit(code), ...probeOptions } = {},
) {
  const harness = await requireHarness(baseUrl, probeOptions);
  if (harness.ok) return harness;
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
