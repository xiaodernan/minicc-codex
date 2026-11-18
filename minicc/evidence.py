# -*- coding: utf-8 -*-
"""M8-T1206 - read-only bridge to the evidence gate (minicc-cloud-evidence).

The Java service on 8088 captures one foreign GitHub Actions run's truth:
``?latest=1`` for the freshest captured run, or a per-run-id backfill. The mini
web page must never call it directly (CORS, availability, loopback binding),
so this module fetches same-origin ``/api/evidence`` from the Python side and
hinges everything on one rule: **an absent, hanging, or broken backend yields an
honest ``present:false`` payload, never a 5xx.**

Token material never passes through here - the Java service reads its own
environment; the Python bridge asks for facts only.
"""

from __future__ import annotations

import json
import os
import urllib.request

_DEFAULT_URL = "http://127.0.0.1:8088"
_ENV_URL = "MINICC_EVIDENCE_URL"
_TIMEOUT_SECONDS = 4.0
_MAX_BYTES = 1024 * 512


def _url() -> str:
    raw = os.environ.get(_ENV_URL, "").strip() or _DEFAULT_URL
    return raw.rstrip("/")


def _honest_absent(reason: str) -> dict:
    return {
        "present": False,
        "reason": reason,
        "count": 0,
        "entries": [],
        "source": "minicc-cloud-evidence",
    }


def latest(workspace: object | None = None) -> dict:
    """Fetch the freshest captured CI run from the evidence gate.

    ``workspace`` is accepted for signature parity with the other memoized
    read paths; the evidence cache is workspace-independent.
    """
    target = _url() + "/api/evidence?latest=1"
    try:
        with urllib.request.urlopen(target, timeout=_TIMEOUT_SECONDS) as response:
            body = response.read(_MAX_BYTES)
    except Exception as exc:  # noqa: BLE001 - an unreachable gate is a fact, not a crash
        return _honest_absent(
            f"evidence gate unreachable ({type(exc).__name__}); is minicc-cloud-evidence on {_url()}?"
        )
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        return _honest_absent(f"evidence gate returned invalid JSON ({type(exc).__name__})")
    if not isinstance(payload, dict):
        return _honest_absent("evidence gate returned non-object JSON")
    # The Java service always writes the envelope keys; adopt them verbatim,
    # adding the source tag and normalising present to a real boolean.
    if not isinstance(payload.get("present"), bool):
        payload["present"] = bool(payload.get("entries"))
    payload.setdefault("entries", [])
    payload.setdefault("count", len(payload.get("entries") or []))
    payload.setdefault("generated_at", None)
    payload["source"] = "minicc-cloud-evidence"
    return payload
