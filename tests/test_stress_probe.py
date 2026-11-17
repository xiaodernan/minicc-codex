# -*- coding: utf-8 -*-
"""M8-T1183 — scripts/stress_probe.py is on the floor of impacted_tests.

Loads the module by its shipped path (scripts/stress_probe.py — the literal is
what the floor reads; keep it) and exercises the real machinery end-to-end:
percentile math against a known population, a live burst against a throwaway
ThreadingHTTPServer, and main() refusing to measure a dead service.
It never opens the user's port 8765; every counter below is created here.
"""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stress_probe.py"


def _load():
    import importlib.util

    assert str(SCRIPT).replace("\\", "/").endswith("scripts/stress_probe.py")
    spec = importlib.util.spec_from_file_location("scripts.stress_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_percentile_is_correct_on_a_known_population():
    mod = _load()
    assert mod._percentile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert mod._percentile([10.0], 0.99) == 10.0
    assert mod._percentile([], 0.5) == 0.0


class _Handler(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):  # noqa: N802 - http.server API
        type(self).hits += 1
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # keep the suite quiet
        return


def test_the_probe_heats_a_real_server_and_reports_honestly():
    mod = _load()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        result = mod.probe(url, "/api/health", n_requests=120, concurrency=4, warmup=2)
        assert result["endpoint"] == "/api/health"
        assert result["concurrency"] == 4
        assert result["requests"] == 120
        assert result["status_histogram"].get(200) == 120
        assert result["non_200"] == 0
        assert result["transport_errors"] == 0
        assert result["p50_ms"] <= result["p99_ms"] <= result["max_ms"]
        assert result["rps"] > 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_probe_refuses_to_measure_a_dead_server(monkeypatch):
    mod = _load()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(
        "sys.argv",
        ["stress_probe", "--url", f"http://127.0.0.1:{port}", "--requests", "8", "--concurrency", "2"],
    )
    assert mod.main() == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
