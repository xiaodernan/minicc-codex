"""Live mainline health for THIS repository (minicc-codex).

Same honesty contract as :mod:`minicc.worldpulse`: every number here is either
read from the GitHub REST API or explicitly marked unavailable — never a demo
figure. Network down, rate limit exhausted, repository moved: the honest shape
is ``live=False`` and the cache decides whether we keep serving the last honest
answer or fail open. The admin panel's "mainline health" tile reads this route on
panel open.

Cache: shares ``minicc.redis_cache.default_cache`` (Redis when live, LRU
otherwise), 5-minute TTL — a health answer a UI can poll without burning the
rate budget.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from .redis_cache import default_cache

_CACHE_KEY = "minicc:ci_health:runs"
_TTL_SECONDS = 300.0
_HEADERS = {"User-Agent": "minicc-ci-health", "Accept": "application/vnd.github+json"}
_RUNS_URL = "https://api.github.com/repos/xiaodernan/minicc-codex/actions/runs?branch=main&per_page=3"
_PRS_URL = "https://api.github.com/repos/xiaodernan/minicc-codex/pulls?state=open&per_page=100"
_ISSUES_URL = "https://api.github.com/repos/xiaodernan/minicc-codex/issues?state=open&per_page=100"


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 - public, read-only, documented
        return json.loads(resp.read().decode("utf-8"))


def _run_row(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(run, dict):
        return None
    sha = str(run.get("head_sha") or "")
    return {
        "conclusion": run.get("conclusion"),
        "status": run.get("status"),
        "workflow": run.get("name"),
        "created_at": run.get("created_at"),
        "head_sha": sha[:7],
        "html_url": run.get("html_url"),
    }


def fetch_ci_health(*, force_refresh: bool = False) -> dict[str, Any]:
    cached = None
    if not force_refresh:
        try:
            cached = default_cache.get(_CACHE_KEY)
        except Exception:  # noqa: BLE001 - cache read failure falls back honestly
            cached = None
    if isinstance(cached, dict) and cached.get("live"):
        return cached

    runs: list[Any] = []
    open_prs: int | None = None
    open_issues: int | None = None
    own_errors: list[str] = []
    try:
        payload = _get_json(_RUNS_URL)
        runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    except Exception as exc:  # noqa: BLE001
        own_errors.append(f"runs: {type(exc).__name__}")

    try:
        prs = _get_json(_PRS_URL)
        open_prs = len(prs) if isinstance(prs, list) else None
    except Exception as exc:  # noqa: BLE001
        own_errors.append(f"prs: {type(exc).__name__}")

    try:
        issues = _get_json(_ISSUES_URL)
        if isinstance(issues, list):
            open_issues = len([i for i in issues if isinstance(i, dict) and "pull_request" not in i])
    except Exception as exc:  # noqa: BLE001
        own_errors.append(f"issues: {type(exc).__name__}")

    latest = runs[0] if runs else None
    payload = {
        "live": bool(runs),
        "generated_at": round(time.time(), 3),
        "latest_run": _run_row(latest),
        "recent": [_run_row(r) for r in runs[:3] if isinstance(r, dict)],
        "open_prs": open_prs,
        "open_issues": open_issues,
        "errors": own_errors or None,
    }
    try:
        default_cache.set(_CACHE_KEY, payload, ttl=_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - cache write failures never take the lane down
        pass
    return payload
