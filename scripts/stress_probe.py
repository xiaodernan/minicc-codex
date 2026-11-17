# -*- coding: utf-8 -*-
"""Concurrent read-pressure probe for the minicc web service.

Hits **read-only, model-free** GET endpoints from a configurable number of
worker threads and reports per-endpoint throughput and latency percentiles.
It exists so the repository can state, honestly and with a repeatable command,
how the service behaves under bursty concurrent read traffic on one machine.

Deliberately NOT part of CI: the numbers depend on the machine, the working
set, and even disk cache. Run it locally, copy the summary into the ledger
with the observations attached.

Not a model load test: `/api/oracle-*` endpoints call the provider unless
memoized, so they are excluded by design — with one deliberate exception,
`/api/oracle-audit-story`, included as the hot path the admin panel polls.
Its in-process memo has a short TTL, so measured latency there is a *mix*
of memo hits and provider round-trips (with `MINICC_FAKE_PROVIDER=1` these
are fake round-trips, not the real gateway); never quote those numbers as
the real model path. Treat the audit endpoint similarly: it streams the
workspace's real `.minicc/audit.jsonl`.

Usage:

    python scripts/stress_probe.py --url http://127.0.0.1:8765 \
        --requests 200 --concurrency 1,8,32,64 \
        --endpoints "/api/health,/api/stategraph,/api/stats,/api/roadmap,/api/audit?limit=64,/api/oracle-audit-story"
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

DEFAULT_ENDPOINTS = [
    "/api/health",
    "/api/stategraph",
    "/api/stats",
    "/api/roadmap",
    "/api/audit?limit=64",
    "/api/oracle-audit-story",
]


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def probe(url: str, endpoint: str, n_requests: int, concurrency: int, warmup: int = 15) -> dict[str, Any]:
    base = url.rstrip("/")

    # keep-alive clients per thread, prepared once per (endpoint, concurrency) cell
    class Worker:
        def __init__(self) -> None:
            self.client = httpx.Client(base_url=base, timeout=10.0, follow_redirects=False)
            self.times: list[float] = []
            self.statuses: dict[int, int] = {}

        def fire(self, ep: str) -> None:
            t0 = time.perf_counter()
            try:
                resp = self.client.get(ep)
                elapsed = time.perf_counter() - t0
                self.times.append(elapsed * 1000.0)
                self.statuses[resp.status_code] = self.statuses.get(resp.status_code, 0) + 1
            except Exception as exc:  # noqa: BLE001 - the probe records, never crashes
                elapsed = time.perf_counter() - t0
                self.times.append(elapsed * 1000.0)
                self.statuses[-1] = self.statuses.get(-1, 0) + 1

        def close(self) -> None:
            self.client.close()

    # Warm the working set (memo, caches, page tables) before measuring.
    warm = Worker()
    for _ in range(warmup):
        warm.fire(endpoint)
    warm.close()

    workers = [Worker() for _ in range(concurrency)]
    barrier = threading.Barrier(concurrency + 1)

    def run_worker(w: Worker) -> None:
        barrier.wait()
        for _ in range(n_requests // concurrency):
            w.fire(endpoint)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run_worker, w) for w in workers]
        barrier.wait()
        for f in futures:
            f.result()
    wall = time.perf_counter() - t0

    times = sorted(x for w in workers for x in w.times)
    statuses: dict[int, int] = {}
    for w in workers:
        for code, count in w.statuses.items():
            statuses[code] = statuses.get(code, 0) + count
        w.close()

    ok = statuses.get(200, 0)
    body_errors = sum(c for code, c in statuses.items() if code != 200 and code != -1)
    transport_errors = statuses.get(-1, 0)
    return {
        "endpoint": endpoint,
        "concurrency": concurrency,
        "requests": len(times),
        "wall_s": round(wall, 3),
        "rps": round(len(times) / wall, 1) if wall else 0.0,
        "p50_ms": round(statistics.median(times), 1),
        "p95_ms": round(_percentile(times, 0.95), 1),
        "p99_ms": round(_percentile(times, 0.99), 1),
        "max_ms": round(max(times), 1) if times else 0.0,
        "ok_200": ok,
        "non_200": body_errors,
        "transport_errors": transport_errors,
        "status_histogram": statuses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent read-pressure probe for minicc web.")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", default="1,8,32,64")
    parser.add_argument("--endpoints", default=",".join(DEFAULT_ENDPOINTS))
    parser.add_argument("--json", action="store_true", help="emit a JSON summary instead of a table")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    endpoints = [e.strip() for e in args.endpoints.split(",") if e.strip()]
    levels = [int(x) for x in args.concurrency.split(",") if x.strip()]

    probe_client = httpx.Client(base_url=url, timeout=10.0)
    try:
        resp = probe_client.get("/api/health")
        print("pre-flight /api/health ->", resp.status_code)
        if resp.status_code != 200:
            print("server is not healthy; refusing to measure", file=sys.stderr)
            return 2
    except Exception as exc:
        print(f"server unreachable at {url}: {exc}", file=sys.stderr)
        return 2
    finally:
        probe_client.close()

    results: list[dict[str, Any]] = []
    for endpoint in endpoints:
        for level in levels:
            result = probe(url, endpoint, args.requests, level)
            results.append(result)
            print(
                f"c={level:<3} {endpoint:<32} rps={result['rps']:<8} "
                f"p50={result['p50_ms']:<7} p95={result['p95_ms']:<7} p99={result['p99_ms']:<7} "
                f"max={result['max_ms']:<7} ok={result['ok_200']} non200={result['non_200']} "
                f"transport={result['transport_errors']}",
                flush=True,
            )

    if args.json:
        print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
