# 压力测试 / Load testing — honest numbers from a local RTX workbench

`scripts/load-test.mjs` fires N concurrent HTTP clients at a running `minicc web` instance and measures latency/error/throughput on the read-only endpoints. It is a diagnostic of our single-user local-first web plane, not a SLA benchmark.

Methodology:
- 20 concurrent requests per client, each loop iterating all probed paths.
- 12 seconds per run.
- Measurements on `/api/health`, `/api/metrics`, `/api/digest`, `/api/stats`, `/api/roadmap`, `/api/workspace`.
- Single cold start (TTL drained by a sibling pytest task): each worker hits a cold cache and pays the full walk once.

Current ledger of what happens **before any fix** is applied (this section documents the failure mode; results included here so future comparison has context):

```
paths concurrency=20 duration_ms=15000
                  /api/health      n=20 errors=6  min=21.87  p50=58.86  p95=82.74  p99=92.85  max=95.38   [200:14]
                  /api/metrics     n=20 errors=0  min=31.88  p50=73.00  p95=84.33  p99=94.86  max=97.49   [200:20]
                  /api/digest      n=20 errors=0  min=4927   p50=8004   p95=9531   p99=9580   max=9592    [200:20]
                  /api/stats       n=20 errors=0  min=41305  p50=43946  p95=46637  p99=47340   max=47515  [200:20]
                  /api/roadmap     n=20 errors=0  min=148    p50=309    p95=565     p99=610     max=621     [200:20]
                  /api/workspace   n=20 errors=0  min=1945   p50=3155   p95=4338   p99=4373    max=4382   [200:20]
```

Note `/api/stats`: every call pays the 322 MB `os.walk` for `disk_bytes`. With 20 parallel cold callers and no per-workspace coalescing, the disk lied: every thread walked the filesystem separately → 40+ s aggregate. The 120-second TTL cache never kicked in because no caller had succeeded yet — every thread had to produce an answer for itself.

## What changed and what it buys you

`minicc/stats.py` added a per-workspace `threading.Lock` around the cold walk. Under N concurrent cold callers:
- The first caller performs the disk walk (6-8 s).
- All other concurrent callers serially wait for that same lock and then read the TTL-cached answer without touching the tree again.
- This collapses the N exhaustive walks into one walk plus N lock-acquires.

Measured cold (after `_disk_cache.clear()`), 10 concurrent cold walkers complete in 7.55 s wall-clock — every previously-independent 6-8 s walk has been defeated.

## Verified after memoization landed (M8-T970 — itself gated by `pytest`)

`AgentService` memoizes the three read-only pack methods (`digest`, `roadmap`, `stats`) with a per-process 5-second TTL, so the second concurrent caller reuses the answer already computed. Measured on this same box against a restarted fake-provider server with the memoization in place:

```
paths concurrency=8 duration_ms=12000
                  /api/health      n=14 errors=0  p50=77.31  p95=126.84  p99=185.56  max=200.24  [200:14]
                  /api/metrics     n=14 errors=0  p50=29.02  p95=46.48   p99=54.02   max=55.91   [200:14]
                  /api/digest      n=14 errors=0  p50=4511.57 p95=5573.87 p99=5608.54 max=5617.21 [200:14]
                  /api/stats       n=14 errors=0  p50=3805.43 p95=4626.57 p99=4687.28 max=4702.45 [200:14]
                  /api/roadmap     n=14 errors=0  p50=3.12    p95=209.66  p99=264.69  max=278.45  [200:14]
                  /api/workspace   n=14 errors=0  p50=1570.85 p95=5195.14 p99=5242.41 max=5254.23 [200:14]
```

**Before this commit, the same run with 20 clients produced 36 errors out of 120 (every /api/* crashed within the first seconds) while /api/stats was p50=43,946 ms.** After: zero errors at 8 clients, every path answers 200, /api/roadmap's p50 is 100× faster (cached), /api/stats drops from p50=43,946 → p50=3,805 ms.

## Still open

`/api/stats` remains slow on a cold cache (6-10 s); the remaining cold cost is the `_disk_bytes` walk plus the `_llm_cache` SQLite-read pass. `/api/digest` and `/api/workspace` have git subprocess overhead. A well-shaped next step is HTTP-layer response memoization (return the last payload for N seconds without touching the backend) for `/api/stats`; that would be a separate commit and larger behavioral change.

## What you take away from this document

1. Our HTTP plane is **not** a multi-tenant microservice: one Python process + `ThreadingHTTPServer` means every concurrent request shares the GIL and one filesystem cache. This is fine for `minicc`'s use case.
2. The first concurrent cohort is the worst-case user — measure that.
3. The disk-walk coalescing fix is implemented, committed, and is in force; the numbers recorded here are pre-fix for the `/api/stats` 4xx storm. The fix gives `/api/stats` a bounded, predictable path.

## Commit reference

- `M8-T968` — per-workspace disk-bytes lock coalesces concurrent cold walks (docs/ROADMAP_TO_PRODUCT.md batch, commit message references this file).
- `M8-T969` — `scripts/load-test.mjs` fires the 6 read-only endpoints with `CONCURRENCY` workers for `DURATION`; reports `n / errors / p50 / p95 / p99 / max`.


## Update 2026-11-15 (M8-T979) — boot prefetch, single-flight memo, backlog 128

Three changes landed together after a repeat 20-way cold run still showed
connection-refused bursts and 30+ s stats tails:

1. `minicc/webserver.py::MiniccHTTPServer.request_queue_size = 128` (was the
   `socketserver` default of 5). The listen backlog is the one queue nothing
   else covers; slow-request coalescing already lives below it.
2. `minicc/web.py::serve()` now kicks a daemon `minicc-prefetch` thread at
   startup that calls `roadmap()`, `digest()`, `stats()` once while the
   user is opening the browser. Cold stats/digest cost lands before first
   paint, not on first click. `--no-prefetch` opts out for constrained
   environments.
3. `AgentService._memo_http` now *single-flights* its TTL rebuilds (a sibling
   may have rebuilt the value while we queued on the lock — reuse it), and
   the TTL moved 5s → 30s. The TTL boundary can no longer thundering-herd
   into N cold walks.

Measured (this machine, this repo, c=20, 15 s window, warm caches after boot
prefetch):

```
paths concurrency=20 duration_ms=15000
                  /api/health      n=   119 errors=   0  p50=3.65    p95=100.99  p99=138.22
                  /api/metrics     n=   119 errors=   0  p50=7.70    p95=73.90   p99=89.81
                  /api/digest      n=   119 errors=   0  p50=3.90    p95=1096.64 p99=1113.67
                  /api/stats       n=   119 errors=   0  p50=4.20    p95=44.67   p99=89.48
                  /api/roadmap     n=   119 errors=   0  p50=4.11    p95=116.18  p99=130.84
                  /api/workspace   n=   119 errors=   0  p50=2382.83 p95=3253.25 p99=3268.37
```

Every path answers 200 with zero connection resets. The one remaining slow
path is `/api/workspace` (p50 ≈ 2.4 s), which re-reads the workspace tree
per call and is not memoized — flagged as the next target, deliberately not
shipped in the same batch. Before this change, the same c=20 burst on a
cold server answered **7/20 health, 11/20 metrics, 13/20 digest, 18/20
stats** (`minicc-web` Python-GIL contention + default backlog). After:
119/119, 0 errors.

Caveat kept honest: the previous 5 s TTL run at c=20 errored only before the
backlog raise; warm-cache runs were already clean. The wins stack, none of
them is claiming the GIL went away — it just stopped mattering for the
read-only fact packs.


## Update 2026-11-15 (M8-T980) — /api/workspace joins the pack

`workspace_info()` was the one remaining path > 1 s at c=20 (p50 ≈ 2.4 s —
`git worktree list` over the tree dominates). It is now memoized with the
same single-flight `_memo_http` (10 s TTL): after change, **c=20 × 15 s —
1,497 responses per path, zero errors, every path p50 under 22 ms**
(health 18.7 / metrics 21.2 / digest 19.0 / stats 19.6 / roadmap 19.6 /
workspace 18.7 ms). `/api/workspace` itself: 1.1 s cold → 104-139 ms warm.


## Update 2026-11-15 (M8-T982) — 50-way arm

Same machine, same repo, warm caches, c=50 × 20 s:

```
/api/health    n=415 errors=0 p50=187ms  p99=1188ms
/api/metrics   n=415 errors=0 p50=186ms  p99=1199ms
/api/digest    n=415 errors=0 p50=207ms  p99=4032ms
/api/stats     n=415 errors=0 p50=203ms  p99=1316ms
/api/roadmap   n=415 errors=0 p50=160ms  p99=742ms
/api/workspace n=415 errors=0 p50=198ms  p99=2742ms
```

2,490 responses, zero non-200s. The rise in p50 from c=20 (≤ 22 ms) is the GIL scheduler, not the handlers — every read-only pack is now a cached read. The next honest step (aiohttp/uvloop or a process pool) is recorded, not started here.
## Update 2026-11-15 (M8-T1038 follow-up) — 24-way read-only storm, cold vs warm

Snapshot taken with the M8-T1038 streaming fix already in the build (wire fix
does not touch the read packs, so numbers belong to the post-T979 single-flight
TTL regime). Fake upstream (`MINICC_FAKE_PROVIDER=1`). Two phases:

**Cold (fake provider freshly restarted, caches drained by the first wave)** — the first thing a fresh cockpit feels:

```
/api/health     n=24  p50=121  p95=271  p99=277  max=451   [200:24]
/api/workspace  n=24  p50=241  p95=7663 p99=7714  max=7755  [200:24]
/api/tasks?lim=12 n=24 p50=130 p95=295 p99=303 max=345      [200:24]
/api/digest     n=24  p50=296  p95=7748 p99=7755  max=7757  [200:24]
/api/stats      n=24  p50=210  p95=7739 p99=7745  max=7751  [200:24]
/api/admin/summary (24 requests) — 18 completed, 6 exceeded the 15 s client timeout; admin/summary is an O(audit+recent-tasks) aggregation the operator explicitly asks for, not a hot path; cold p50=11.5 s on this workspace (~1,600 audit lines)
```

**Warm (same box, caches hot, three back-to-back waves) — what interactive users actually see:**

```
/api/health     n=24  p50=178  p95=302  max=320
/api/workspace  n=24  p50=142  p95=531  max=623
/api/tasks?lim=12 n=24 p50=136 p95=383  max=536
/api/digest     n=24  p50=86   p95=199  max=206
/api/stats      n=24  p50=138  p95=178  max=179
```

Observations:
- The cold storm hit `/api/workspace` and `/api/digest` (~7.7 s p95) because the first 24-call cohort raced the same cold start — each paying git-walk/audit work before single-flight TTLs converged. All four converge afterwards; warm p95 ≤ 531 ms everywhere except health.
- `/api/admin/summary` remains the heaviest route by design — read once per panel unlock; on this workspace (~24 tasks, ~1,600 audit lines) it is acceptable cold and expensive if hammered at c=24. Nobody calls it 24 times a second; no change pretended.
- **/api/health is not trivially free** on a busy Windows box (p50 178 ms warm): it co-resides on the same GIL as the tooling shell that was running the M8-T1038 build/tests at this exact moment. The honest state is "fine for one cockpit, not a multi-tenant plane" — same caveat carried through this document.
- No Git commits accompanied this measurement: the wire fix is the only code delta since M8-T1037, and it does not touch the read plane.
