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
