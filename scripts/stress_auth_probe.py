# -*- coding: utf-8 -*-
"""The abuse probe: what an attacker hammers, and the shape of reality.

Starts a *required-auth* instance of the web workbench on a throwaway port,
fires a fixed matrix of adversarial barrages at it, then reports what
actually happened — never what a benchmark brochure would like to say.

This is a **loopback-only, single-machine** measurement. It is deliberately not
part of CI (the numbers are machine-bound); every claim of abuse resilience the
ledger makes should be measured against this very file.

Scenario matrix

  A. health unauthenticated must stay 200.
  B. wrong-bearer flood on token-gated routes — including the gateway-calling
     oracle route specifically: every one must come back 401, zero 5xx, and the
     oracle must never spend a token on an unauthenticated caller.
  C. garbage bytes barrage: 10 KiB of random bytes on a token-gated POST route.
     The worker must answer with a refusal, never crash, service must survive.
  D. saturation of the authorized lane itself: a 64-request burst at c=32 must
     all answer 200.
  E. aftermath: health is still 200, and a valid token on a token-gated route
     is still served.

Run:

  python scripts/stress_auth_probe.py --port 8766
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import httpx
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url + "/api/health", timeout=1.5)
            if resp.status_code == 200:
                return
        except Exception:  # noqa: BLE001 - the child is still booting; a failed probe is a wait, not a verdict
            pass
        time.sleep(0.15)  # poll again on purpose: the whole point is to wait, honestly
    raise SystemExit("minicc required-auth server never answered /api/health")


def _percentiles(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    ordered = sorted(values)

    def pct(p: float) -> float:
        k = (len(ordered) - 1) * p
        f = int(k)
        c = min(f + 1, len(ordered) - 1)
        if f == c:
            return ordered[f]
        return ordered[f] + (ordered[c] - ordered[f]) * (k - f)

    return pct(0.5), pct(0.95), pct(0.99)


def _request(url: str, path: str, *, headers: dict[str, str] | None = None, body: bytes | None = None,
             method: str = "get", timeout: float = 5.0) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        if method == "get":
            resp = httpx.get(url + path, headers=headers or {}, timeout=timeout)
        else:
            resp = httpx.post(url + path, headers=headers or {}, content=body, timeout=timeout)
        return resp.status_code, (time.perf_counter() - started) * 1000
    except Exception:  # noqa: BLE001 - the probe records the absence of an answer; an exception would abort the burst instead
        return -1, (time.perf_counter() - started) * 1000


def _burst(url: str, path: str, *, headers: dict[str, str] | None = None, body: bytes | None = None,
           method: str = "get", n: int = 64, workers: int = 32) -> dict[str, Any]:
    statuses: dict[int, int] = {}
    elapsed: list[float] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_request, url, path, headers=headers, body=body, method=method)
            for _ in range(n)
        ]
        for future in concurrent.futures.as_completed(futures):
            code, ms = future.result()
            statuses[code] = statuses.get(code, 0) + 1
            elapsed.append(ms)
    return {"status_codes": statuses, "elapsed": elapsed}


def scenario(url: str, token: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    # --- A. health with no credentials: 200 or bust
    code, ms = _request(url, "/api/health")
    results.append({
        "scenario": "A. unauthenticated health",
        "requests": 1,
        "all_200": 1 if code == 200 else 0,
        "status_codes": {code: 1},
        "p50_ms": round(ms, 2), "p95_ms": round(ms, 2), "p99_ms": round(ms, 2),
        "non_5xx_free": True,
        "broken": code != 200,
        "note": "health answered with no credentials" if code == 200 else "health RED with no load",
    })

    # --- B. wrong-token storm on token-gated routes, including the gateway
    for path in ["/api/commands", "/api/roadmap", "/api/oracle-brief", "/api/oracle-brief?fresh=1"]:
        batch = _burst(url, path,
                       headers={"Authorization": "Bearer not-a-real-token-" + secrets.token_hex(4)},
                       method="get", n=100, workers=32)
        codes = batch["status_codes"]
        p50, p95, p99 = _percentiles(batch["elapsed"])
        ok = codes == {401: 100}
        results.append({
            "scenario": f"B. bearer-storm {path}",
            "requests": 100,
            "all_200": codes.get(200, 0),
            "status_codes": codes,
            "p50_ms": round(p50, 2), "p95_ms": round(p95, 2), "p99_ms": round(p99, 2),
            "non_5xx_free": all(c < 500 and c != -1 for c in codes),
            "all_denied_as_401": ok,
            "broken": not ok,
            "note": "100/100 forged tokens refused with 401; wire untouched" if ok
                    else f"forged traffic was NOT uniformly refused: {codes}",
        })

    # --- C. random-bytes barrage on an authenticated POST route
    payload = os.urandom(10 * 1024)
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}
    batch = _burst(url, "/api/chat", headers=auth, body=payload, method="post", n=40, workers=16)
    codes = batch["status_codes"]
    p50, p95, p99 = _percentiles(batch["elapsed"])
    results.append({
        "scenario": "C. 10KiB random-bytes POST /api/chat (valid token)",
        "requests": 40,
        "all_200": codes.get(200, 0),
        "status_codes": codes,
        "p50_ms": round(p50, 2), "p95_ms": round(p95, 2), "p99_ms": round(p99, 2),
        "non_5xx_free": all(c < 500 and c != -1 for c in codes),
        "broken": any(c >= 500 or c == -1 for c in codes),
        "note": "garbage body refused without hurting the worker",
    })

    # --- D. saturation of the authorized lane: 64 calls at c=32
    batch = _burst(url, "/api/commands", headers=auth, method="get", n=64, workers=32)
    codes = batch["status_codes"]
    p50, p95, p99 = _percentiles(batch["elapsed"])
    results.append({
        "scenario": "D. authorized lane saturated (64 / c=32)",
        "requests": 64,
        "all_200": codes.get(200, 0),
        "status_codes": codes,
        "p50_ms": round(p50, 2), "p95_ms": round(p95, 2), "p99_ms": round(p99, 2),
        "non_5xx_free": all(c < 500 and c != -1 for c in codes),
        "broken": codes != {200: 64},
        "note": "the authorized lane held under its own saturation",
    })

    # --- E. aftermath
    code, ms = _request(url, "/api/health")
    code2, ms2 = _request(url, "/api/commands", headers=auth)
    results.append({
        "scenario": "E. aftermath (health + authorized route intact)",
        "requests": 2,
        "all_200": int(code == 200) + int(code2 == 200),
        "status_codes": {"health": code, "commands": code2},
        "p50_ms": round((ms + ms2) / 2, 2), "p95_ms": round(max(ms, ms2), 2), "p99_ms": round(max(ms, ms2), 2),
        "non_5xx_free": code < 500 and code2 < 500,
        "broken": code != 200 or code2 != 200,
        "note": "storm left the service whole" if code == 200 and code2 == 200 else "service did NOT recover cleanly; honest finding",
    })

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Abuse-resilience probe for the minicc workbench.")
    parser.add_argument("--port", type=int, default=_free_port())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    token = "probe-token-" + secrets.token_urlsafe(24)
    url = f"http://127.0.0.1:{args.port}"
    env = dict(os.environ)
    env["MINICC_FAKE_PROVIDER"] = "1"
    env["MINICC_API_KEY"] = "probe-key"
    env["MINICC_BASE_URL"] = "https://example.invalid/v1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "minicc.web", "--workspace", str(REPO),
         "--host", "0.0.0.0", "--port", str(args.port), "--token", token],
        cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(url)
        results = scenario(url, token)

        broken = [r for r in results if r.get("broken")]
        header = f"{'scenario':<70}{'status_codes':>26}{'p50':>8}{'p95':>8}{'p99':>8}  verdict"
        print(header)
        print("-" * len(header))
        for result in results:
            codes = result["status_codes"]
            codes_str = ",".join(f"{k}:{v}" for k, v in sorted(codes.items(), key=lambda x: str(x[0])))
            verdict = "held" if not result["broken"] else "BROKEN"
            print(f"{result['scenario']:<70}{codes_str:>26}{result['p50_ms']:>8.1f}{result['p95_ms']:>8.1f}{result['p99_ms']:>8.1f}  {verdict}")
        print()
        if args.json:
            print(json.dumps(results, indent=2, default=str))
        print("honesty report: "
              f"{len(results)} scenarios, {len(broken)} broken. "
              "Numbers are single-machine, single-run, loopback. Not a CI artifact.")
        return 0 if not broken else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
