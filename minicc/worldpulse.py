"""Live pulse from the outside world.

Every number on the almanac's instrument floor and the Status footer must
come from somewhere that can be checked, not from a demo fixture. This module
fetches minicc-codex's own public facts from the GitHub REST API — the
honest wire, the same endpoint any curious visitor would hit. Network down,
rate limit exhausted, repo moved: the honest shape is ``live=False`` and the
cache decides whether we keep the last honest answer or fail open.

Cache: shares ``minicc.redis_cache.default_cache`` (Redis when live, LRU
otherwise), 5-minute TTL — this answers a UI that opens several times per
minute.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from .redis_cache import default_cache

_CACHE_KEY = "minicc:worldpulse:github"
_TTL_SECONDS = 300.0
_API_URL = "https://api.github.com/repos/xiaodernan/minicc-codex"


def _fetch_github() -> dict[str, Any]:
    req = urllib.request.Request(_API_URL, headers={"User-Agent": "minicc/worldpulse", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 - public, read-only, documented
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "name": data.get("name"),
        "private": bool(data.get("private")),
        "stars": int(data.get("stargazers_count") or 0),
        "watchers": int(data.get("watchers_count") or 0),
        "forks": int(data.get("forks_count") or 0),
        "open_issues": int(data.get("open_issues_count") or 0),
        "default_branch": data.get("default_branch"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "pushed_at": data.get("pushed_at"),
        "html_url": data.get("html_url"),
        "description": data.get("description"),
    }


def fetch_worldpulse(*, force_refresh: bool = False) -> dict[str, Any]:
    cached = None
    if not force_refresh:
        try:
            cached = default_cache.get(_CACHE_KEY)
        except Exception:  # noqa: BLE001 - cache read failure falls back honestly
            cached = None
    if isinstance(cached, dict) and cached.get("live"):
        return cached
    try:
        fresh = _fetch_github()
        payload = {"live": True, "fetched_at": round(time.time(), 3), "github": fresh}
        try:
            default_cache.set(_CACHE_KEY, payload, ttl=_TTL_SECONDS)
        except Exception:  # noqa: BLE001 - cache write failures never take the lane down
            pass
        return payload
    except Exception as exc:  # noqa: BLE001 - every failure mode reports honestly
        return {
            "live": False,
            "fetched_at": round(time.time(), 3),
            "github": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
