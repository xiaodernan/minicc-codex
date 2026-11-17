# -*- coding: utf-8 -*-
"""M8-T1192 — scripts/stress_auth_probe.py is on the floor of impacted_tests.

Loads the module by its shipped path (scripts/stress_auth_probe.py — the literal is
what the floor reads; keep it) and pins its real invariants end-to-end:
percentiles math against a known population, a dead port fails instead of
silently passing, and the required-auth instance actually answers 200 with no
credentials leaking into the wrong scenario.
"""

from __future__ import annotations

import importlib.util
import socket
import threading
import http.server
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stress_auth_probe.py"


def _load():
    assert str(SCRIPT).replace("\\", "/").endswith("scripts/stress_auth_probe.py")
    spec = importlib.util.spec_from_file_location("scripts.stress_auth_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_percentiles_are_correct_on_a_known_population():
    mod = _load()
    assert mod._percentiles([1.0, 2.0, 3.0, 4.0]) == pytest.approx((2.5, 3.85, 3.97), abs=0.01)
    assert mod._percentiles([10.0]) == (10.0, 10.0, 10.0)
    assert mod._percentiles([]) == (0.0, 0.0, 0.0)


def test_the_server_never_answers_200_with_a_wrong_bearer():
    """The probe's own minimum moral test: a required-auth server refuses wrong bearers."""
    mod = _load()

    class _Req(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.headers.get("Authorization") == "Bearer probe-token":
                self.send_response(200)
            else:
                self.send_response(401)
            self.end_headers()

        def log_message(self, fmt, *args):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Req)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        good = mod._request(url, "/api/anything", headers={"Authorization": "Bearer probe-token"})
        bad = mod._request(url, "/api/anything", headers={"Authorization": "Bearer not-the-token"})
        assert good[0] == 200 and bad[0] == 401
    finally:
        server.shutdown()
        server.server_close()


def test_burst_counts_credentials_exactly():
    """_burst reports exactly what the server said, mapped through to the histogram."""
    mod = _load()
    responses = [(401, 1.5), (401, 1.0), (200, 3.0)]
    calls = {"n": 0}

    def fake_request(url, path, headers=None, body=None, method="get", timeout=5.0):
        record = responses[calls["n"] % len(responses)]
        calls["n"] += 1
        return record

    mod._request = fake_request  # type: ignore[assignment]
    batch = mod._burst("http://x", "/api/demo", n=6, workers=1)
    assert batch["status_codes"] == {401: 4, 200: 2}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
