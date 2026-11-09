"""M8-T686 — /api/health carries the doctor report alongside liveness."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from minicc.webauth import WebAuth
from minicc.web import AgentService, MiniccHTTPServer


def _config(tmp_path: Path):
    """A synthetic pass-through-config SimpleNamespace like the web tests use."""
    import types

    base = {
        "model": "fake-model",
        "base_url": "https://fake.example.com/v1",
        "api_key": "fake-key",
        "reasoning_effort": "low",
        "tool_mode": "native",
        "output_style": "concise",
        "compact_threshold": 300_000,
        "context_window_tokens": 300_000,
        "yolo": False,
        "sandbox_mode": "host",
        "sandbox_image": "python:3.11-slim",
        "task_queue_limit": 4,
        "max_repair_attempts": 2,
        "fallback_models": (),
        "stage_routing": {},
        "task_executor": "thread",
        "auto_resume_on_start": "",
        "skills": {},
        "host": "127.0.0.1",
        "port": 0,
        "max_upload_bytes": 1_000_000,
        "history_max_age_days": 30,
        "history_limit": 20,
        "snapshot_ttl_seconds": 3600,
        "allow_network": False,
        "allow_changes": False,
        "permission_mode": "plan",
        "default_permission_mode": "plan",
    }
    return types.SimpleNamespace(**base)


class _Server:
    def __init__(self, tmp_path: Path) -> None:
        self.service = AgentService(
            tmp_path,
            _config(tmp_path),
            task_store=None,
        )
        self.server = MiniccHTTPServer(("127.0.0.1", 0), self.service, auth=WebAuth("tok", required=False))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture()
def workspace_server(tmp_path):
    server = _Server(tmp_path)
    try:
        yield server
    finally:
        server.shutdown()


def test_health_carries_doctor_report(workspace_server):
    with urllib.request.urlopen(f"{workspace_server.url}/api/health", timeout=5) as resp:
        payload = json.loads(resp.read())

    assert payload["ok"] is True
    assert payload["service"] == "minicc"
    doctor = payload["doctor"]
    assert isinstance(doctor, dict)
    assert set(doctor) == {"ok", "warn", "fatal", "checks"}
    assert isinstance(doctor["checks"], list)
    assert any(c.get("name") == "python_version" for c in doctor["checks"])
