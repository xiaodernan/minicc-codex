"""M8-T997: 上游回声 —— how far the configured model gateway is from us.

Reads the same environment the llm layer reads (``MINICC_API_KEY`` /
``MINICC_BASE_URL`` / ``MINICC_MODEL``) but **never echoes the key**. The
probe is a plain ``GET {base}/models`` with a tight timeout: one ordinary
OpenAI-compatible discovery call that proves DNS + TCP + TLS + the auth
endpoint answer, at zero token cost and zero message content.

Fail-open: every exception returns an honest payload with ``live: false``;
the doctor panel renders "unreachable" instead of breaking.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from .redis_cache import default_cache
from .llm.fake import FAKE_PROVIDER_ENV, fake_provider_active
from .cache_keeper import keeper_status

_TTL_SECONDS = 10
_CACHE_KEY = "provider-ping:v1"
_USER_AGENT = "minicc-doctor"
_TIMEOUT_SECONDS = 8


def _probe(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    started = time.perf_counter()
    host = urlsplit(base_url).hostname or base_url
    url = base_url.rstrip("/") + "/models"
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", _USER_AGENT)
    request.add_header("Accept", "application/json")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")

    status: int | None = None
    error: str | None = None
    live = False
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            status = int(response.status)
            response.read(256)
        live = 200 <= status < 300
    except urllib.error.HTTPError as exc:
        status = exc.code
        # 401/403/404 still prove the gateway answered on the wire.
        live = exc.code in (401, 403, 404)
        if not live:
            error = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - report honestly, never raise
        error = f"{type(exc).__name__}"

    elapsed = round((time.perf_counter() - started) * 1000, 1)
    return {
        "configured": True,
        "live": live,
        "gateway": host,
        "model": model or "unconfigured",
        "status": status,
        "elapsed_ms": elapsed,
        "error": error,
        "probe": "GET /models",
    }


def fetch_provider_ping(*, force_refresh: bool = False) -> dict[str, Any]:
    if not force_refresh:
        try:
            cached = default_cache.get(_CACHE_KEY)
        except Exception:  # noqa: BLE001 - cache read failure falls back to a fresh probe
            cached = None
        if isinstance(cached, dict) and "elapsed_ms" in cached:
            return cached

    # M8-T1182: .env never exports into os.environ (M8-T1174 exported only the
    # proxy keys), so this doctor read raw env alone reported
    # "MINICC_BASE_URL is not set" on a machine whose .env is perfectly healthy.
    # Env still wins when explicitly set; otherwise the one home for config
    # (load_config) is asked. Under MINICC_FAKE_PROVIDER=1 nothing is probed at
    # all — deterministic offline tests, and zero network from the fake-provider
    # smokes and CI.
    base_url = (os.environ.get("MINICC_BASE_URL") or "").strip()
    api_key = (os.environ.get("MINICC_API_KEY") or "").strip()
    model = (os.environ.get("MINICC_MODEL") or "").strip()
    fake = fake_provider_active()

    if not fake and not base_url:
        try:
            from .config import load_config

            cfg = load_config()
            base_url = (getattr(cfg, "base_url", None) or "").strip()
            api_key = (getattr(cfg, "api_key", None) or "").strip()
            model = (getattr(cfg, "model", None) or "").strip()
        except Exception:
            # the resolver itself is broken; fall through to the honest not-set payload
            pass

    if fake:
        payload = {
            "configured": False,
            "live": False,
            "gateway": None,
            "model": None,
            "status": None,
            "elapsed_ms": 0.0,
            "error": f"{FAKE_PROVIDER_ENV} is set; provider ping skipped",
            "probe": "GET /models",
            "keeper": keeper_status(),
        }
    elif not base_url:
        payload = {
            "configured": False,
            "live": False,
            "gateway": None,
            "model": None,
            "status": None,
            "elapsed_ms": 0.0,
            "error": "MINICC_BASE_URL is not set",
            "probe": "GET /models",
            "keeper": keeper_status(),
        }
    else:
        payload = _probe(base_url, api_key, model)
        payload["keeper"] = keeper_status()

    try:
        default_cache.set(_CACHE_KEY, payload, ttl=_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - cache write failure never breaks the route
        pass
    return payload
