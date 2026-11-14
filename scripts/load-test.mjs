// Dependency-free concurrent HTTP stress probe for the minicc web plane.
// Fires N concurrent workers at the given paths, measures latency, errors, and
// throughput across the duration. Exit code reflects failure threshold (any
// non-2xx = fail).
import { setImmediate } from "node:timers/promises";

const DEFAULT_PATHS = [
  "/api/health",
  "/api/metrics",
  "/api/digest",
  "/api/stats",
  "/api/roadmap",
  "/api/workspace",
];
const DEFAULT_CONCURRENCY = 50;
const DEFAULT_DURATION_SECONDS = 20;
const BASE = process.argv[2] ?? "http://127.0.0.1:8765";
const CONCURRENCY = Number(process.argv[3] ?? DEFAULT_CONCURRENCY);
const DURATION_MS = Number(process.argv[4] ?? DEFAULT_DURATION_SECONDS * 1000);

const stats = new Map(); // path -> { count, errors, latencies[], statusHistogram }

function initStats(path) {
  if (!stats.has(path)) stats.set(path, { count: 0, errors: 0, latencies: [], statuses: new Map() });
  return stats.get(path);
}

async function fetchWorker(workerId, paths, deadline) {
  while (Date.now() < deadline) {
    for (const path of paths) {
      const started = process.hrtime.bigint();
      try {
        const response = await fetch(BASE + path);
        const elapsed = Number(process.hrtime.bigint() - started) / 1e6;
        const entry = initStats(path);
        entry.count += 1;
        entry.latencies.push(elapsed);
        entry.statuses.set(response.status, (entry.statuses.get(response.status) ?? 0) + 1);
        if (!response.ok) entry.errors += 1;
        // drain body to avoid connection pile-up
        await response.arrayBuffer();
      } catch (error) {
        const elapsed = Number(process.hrtime.bigint() - started) / 1e6;
        const entry = initStats(path);
        entry.count += 1;
        entry.errors += 1;
        entry.latencies.push(elapsed);
      }
    }
    // Yield occasionally so many workers can co-exist on the event loop
    if (Date.now() % 7 < 3) await setImmediate(() => {});
  }
}

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = (sorted.length - 1) * p;
  const lower = Math.floor(idx);
  const frac = idx - lower;
  return lower + 1 < sorted.length ? sorted[lower] + frac * (sorted[lower + 1] - sorted[lower]) : sorted[lower];
}

const deadline = Date.now() + DURATION_MS;
const workers = Array.from({ length: CONCURRENCY }, (_, i) => fetchWorker(i, DEFAULT_PATHS, deadline));
await Promise.all(workers);

console.log("paths", `concurrency=${CONCURRENCY} duration_ms=${DURATION_MS}`);
let allErrors = 0;
for (const path of DEFAULT_PATHS) {
  const entry = stats.get(path);
  if (!entry) continue;
  allErrors += entry.errors;
  const p50 = percentile(entry.latencies, 0.5).toFixed(2);
  const p95 = percentile(entry.latencies, 0.95).toFixed(2);
  const p99 = percentile(entry.latencies, 0.99).toFixed(2);
  const min = Math.min(...entry.latencies).toFixed(2);
  const max = Math.max(...entry.latencies).toFixed(2);
  const statuses = [...entry.statuses.entries()].map(([k, v]) => `${k}:${v}`).join(" ");
  console.log(
    "  ".padEnd(18) + path.padEnd(16),
    "n=" + String(entry.count).padStart(6),
    "errors=" + String(entry.errors).padStart(4),
    "min=" + min.padEnd(7),
    "p50=" + p50.padEnd(7),
    "p95=" + p95.padEnd(7),
    "p99=" + p99.padEnd(7),
    "max=" + max.padEnd(8),
    `[${statuses}]`,
  );
}
process.exit(allErrors > 0 ? 1 : 0);
