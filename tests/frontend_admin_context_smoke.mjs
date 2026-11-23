import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  CONTEXT_TIMEOUT_FALLBACK_MS,
  contextFailure,
  contextPackState,
  createContextInspector,
  deriveContextTimeout,
} from "../web/src/panels/admin-context.js";

const element = () => ({ dataset: {}, innerHTML: "", addEventListener() {} });
const copy = (key, params = {}) => key === "admin.contextTiming"
  ? `timing ${params.elapsed} ${params.timeout} ${params.samples}` : key;
const fixture = (request, options = {}) => {
  const factsEl = element();
  const sourcesEl = element();
  const inspector = createContextInspector({
    factsEl,
    sourcesEl,
    refreshEl: element(),
    request,
    t: copy,
    question: () => "cache hit rate context",
    autostart: false,
    ...options,
  });
  return { factsEl, sourcesEl, inspector };
};
const pack = (extra = {}) => ({
  ok: true,
  budget_tokens: 8000,
  estimated_tokens: 120,
  candidates: 2,
  prefix_fingerprint: "abcdef1234567890",
  chunks: [{ source: "docs/context.md", start_line: 4, end_line: 8, tokens: 120 }],
  ...extra,
});

assert.equal(CONTEXT_TIMEOUT_FALLBACK_MS, 30_000);
assert.equal(deriveContextTimeout([]), CONTEXT_TIMEOUT_FALLBACK_MS);
assert.equal(deriveContextTimeout([1_200]), 5_000);
assert.equal(deriveContextTimeout([...Array(19).fill(1_000), 20_000]), 5_000);
assert.equal(deriveContextTimeout([...Array(18).fill(1_000), 20_000]), 61_000);
assert.equal(deriveContextTimeout([200_000]), 120_000);
assert.equal(deriveContextTimeout([Number.NaN, -1, "bad"]), CONTEXT_TIMEOUT_FALLBACK_MS);

for (const [code, state, key] of [
  ["timeout", "timeout", "admin.contextTimeout"],
  ["network", "unreachable", "admin.contextOutage"],
  ["server-error", "server-error", "admin.contextServerError"],
  ["http-error", "rejected", "admin.contextRejected"],
  ["auth-required", "rejected", "admin.contextRejected"],
  [undefined, "unreachable", "admin.contextOutage"],
]) {
  assert.deepEqual(contextFailure({ code }), [state, key]);
}
assert.deepEqual(contextPackState(null), ["unreachable", "admin.contextOutage"]);
assert.deepEqual(contextPackState({ ok: false }), ["backend-error", "admin.contextSlow"]);
assert.deepEqual(contextPackState(pack({ chunks: [] })), ["empty", "admin.contextEmpty"]);
assert.deepEqual(contextPackState(pack()), ["present", ""]);

for (const [code, state, key] of [
  ["timeout", "timeout", "admin.contextTimeout"],
  ["network", "unreachable", "admin.contextOutage"],
]) {
  const calls = [];
  const { factsEl, sourcesEl, inspector } = fixture(async (...args) => {
    calls.push(args);
    throw Object.assign(new Error(code), { code });
  });
  await inspector.read();
  assert.equal(calls[0][2], CONTEXT_TIMEOUT_FALLBACK_MS);
  assert.equal(factsEl.dataset.contextState, state);
  assert.equal(sourcesEl.dataset.contextState, state);
  assert.equal(factsEl.dataset.contextTimeoutMs, String(CONTEXT_TIMEOUT_FALLBACK_MS));
  assert.ok(factsEl.innerHTML.includes(key));
  assert.equal(sourcesEl.innerHTML, "");
}

const empty = fixture(async () => pack({ chunks: [], candidates: 0, estimated_tokens: 0 }));
await empty.inspector.read();
assert.equal(empty.factsEl.dataset.contextState, "empty");
assert.ok(empty.factsEl.innerHTML.includes("admin.contextEmpty"));

const backendError = fixture(async () => ({ ok: false, error: "IndexUnavailable: fixture" }));
await backendError.inspector.read();
assert.equal(backendError.factsEl.dataset.contextState, "backend-error");
assert.ok(backendError.factsEl.innerHTML.includes("IndexUnavailable: fixture"));

let clock = 0;
const timeouts = [];
const observedSamples = [];
const measured = fixture(async (_url, _options, timeout) => {
  timeouts.push(timeout);
  clock += 1_200;
  return pack();
}, { now: () => clock, onSamples: (samples) => observedSamples.push(samples) });
await measured.inspector.read();
assert.equal(measured.factsEl.dataset.contextState, "present");
assert.equal(measured.factsEl.dataset.contextElapsedMs, "1200");
assert.equal(measured.factsEl.dataset.contextTimeoutMs, "5000");
assert.ok(measured.factsEl.innerHTML.includes("timing 1200 5000 1"));
assert.ok(measured.sourcesEl.innerHTML.includes("docs/context.md:4–8"));
await measured.inspector.read();
assert.deepEqual(timeouts, [CONTEXT_TIMEOUT_FALLBACK_MS, 5_000]);
assert.equal(measured.factsEl.dataset.contextTimeoutMs, "5000");
assert.ok(measured.factsEl.innerHTML.includes("timing 1200 5000 2"));
assert.deepEqual(observedSamples, [[1200], [1200, 1200]]);

const restored = fixture(async (_url, _options, timeout) => {
  timeouts.push(timeout);
  return pack();
}, { initialSamples: [1_200] });
await restored.inspector.read();
assert.equal(timeouts.at(-1), 5_000, "a remount must reuse the measured budget");

const storageFailure = fixture(async () => pack(), { onSamples: () => { throw new Error("quota"); } });
await storageFailure.inspector.read();
assert.equal(storageFailure.factsEl.dataset.contextState, "present", "a sample-cache failure cannot erase a real reading");

const admin = await readFile("web/src/panels/admin.js", "utf8");
assert.ok(admin.includes('import { createContextInspector } from "./admin-context.js"'));
assert.ok(admin.includes("createContextInspector({"));
assert.ok(admin.includes("initialSamples: contextSamples"));
assert.ok(admin.includes("sessionStorage.setItem(contextSampleKey"));
assert.ok(!admin.includes("/api/rag/context"), "the context request has one home");
const adminContext = await readFile("web/src/panels/admin-context.js", "utf8");
assert.ok(!adminContext.includes("20000"), "the hand-tuned 20-second timeout must stay gone");

console.log("admin context passed: timeout/unreachable/empty are distinct DOM states; p95 timing drives the next request budget");
