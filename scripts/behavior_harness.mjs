// M8-T1305: the visitor-journey driver is a manual tool that walks a real
// browser through a running workbench. Before this guard, pointing it at a port
// with nothing bound launched Chromium, waited the full --ready-timeout (45s),
// and recorded every persona as a "could-not-drive" bounce - a missing server
// reported as visitor behaviour. The mutation verdict cannot tell that from a
// journey the tool actually measured.
//
// The probe answers in milliseconds, before any browser is launched, and names
// its own failure. Kept side-effect-free and importable so the Python gate can
// drive the emit path with an injected fetch / exit without needing a browser.

export const HARNESS_PROBE_PATH = "/api/health";
export const BEHAVIOR_HARNESS_UNREACHABLE = "BEHAVIOR_HARNESS_UNREACHABLE";
export const BEHAVIOR_HARNESS_UNREACHABLE_EXIT = 3;

// A healthy minicc answers {"ok": true, "service": "minicc"} on /api/health
// without a token (minicc/webserver.py). Anything else - a stranger's 200, a
// 503, non-JSON, or a refused connection - is "no harness here".
export async function probeBehaviorHarness(baseUrl, { fetchImpl = globalThis.fetch, timeoutMs = 4000 } = {}) {
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

export async function requireBehaviorHarness(baseUrl, opts = {}) {
  const {
    announce = (code) => console.error(`SMOKE_FAILURE_CODE=${code}`),
    exitImpl = (code) => process.exit(code),
    ...probeOptions
  } = opts;
  const harness = await probeBehaviorHarness(baseUrl, probeOptions);
  if (harness.ok) return harness;
  announce(BEHAVIOR_HARNESS_UNREACHABLE);
  console.error(
    [
      `${BEHAVIOR_HARNESS_UNREACHABLE}: the visitor-journey driver has no workbench answering at ${harness.probeUrl} (${harness.detail}).`,
      "Start one (python -m minicc.web --workspace . --port <port>) or pass --url pointing at a running instance.",
      `Exiting ${BEHAVIOR_HARNESS_UNREACHABLE_EXIT} without launching Chromium: no journeys were measured, ` +
        "so nothing this run would have recorded says anything about visitor behaviour.",
    ].join(" "),
  );
  return exitImpl(BEHAVIOR_HARNESS_UNREACHABLE_EXIT);
}
