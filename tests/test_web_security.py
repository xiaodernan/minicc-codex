"""Web authentication, CORS origin policy, and workspace whitelist tests."""

from __future__ import annotations

import json
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from minicc.config import Config
from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import (
    WebAuth,
    cors_origin,
    generate_token,
    is_loopback_host,
    load_or_create_token,
    origin_allowed,
)


# ---------------------------------------------------------------------------
# webauth unit tests
# ---------------------------------------------------------------------------


def test_loopback_host_detection() -> None:
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert is_loopback_host("::1")
    assert is_loopback_host("[::1]")
    assert is_loopback_host("localhost.local")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("192.168.1.8")
    assert not is_loopback_host("")


def test_webauth_required_rejects_missing_and_wrong_token() -> None:
    auth = WebAuth("secret-token", required=True)
    assert not auth.check(None)
    assert not auth.check("")
    assert not auth.check("wrong")
    assert auth.check("secret-token")


def test_webauth_optional_accepts_everything() -> None:
    auth = WebAuth("secret-token", required=False)
    assert auth.check(None)
    assert auth.check("whatever")


def test_webauth_accepts_bearer_header_and_query_fallback() -> None:
    auth = WebAuth("secret-token", required=True)

    class _Headers:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self, name: str, default: str | None = None) -> str:
            if name == "Authorization":
                return self._value
            return default or ""

    assert auth.check_headers(_Headers("Bearer secret-token"))
    assert auth.check_headers(_Headers("bearer secret-token"))
    assert auth.check_headers(_Headers(""), query_token="secret-token")
    assert not auth.check_headers(_Headers(""), query_token="bad")
    assert not auth.check_headers(_Headers(""))


def test_origin_policy_allows_loopback_only() -> None:
    assert not origin_allowed(None)  # no Origin header: no CORS headers needed
    assert origin_allowed("http://localhost:8765")
    assert origin_allowed("http://127.0.0.1:3000")
    assert not origin_allowed("https://evil.example.com")
    assert not origin_allowed("file:///etc/passwd")
    assert cors_origin("http://127.0.0.1:8765") == "http://127.0.0.1:8765"
    assert cors_origin("https://evil.example.com") is None


def test_load_or_create_token_persists_and_reuses(tmp_path: Path) -> None:
    token_a, created_a = load_or_create_token(tmp_path, None)
    token_b, created_b = load_or_create_token(tmp_path, None)
    assert created_a
    assert not created_b
    assert token_a == token_b
    assert len(token_a) >= 32
    store = tmp_path / ".minicc" / "web_token.json"
    assert json.loads(store.read_text(encoding="utf-8"))["token"] == token_a


def test_load_or_create_token_prefers_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MINICC_WEB_TOKEN", "env-token")
    token, created = load_or_create_token(tmp_path, "cli-token")
    assert token == "cli-token"
    assert not created
    token_env, _ = load_or_create_token(tmp_path / "unused", None)
    assert token_env == "env-token"


def test_generate_token_unique() -> None:
    assert generate_token() != generate_token()


# ---------------------------------------------------------------------------
# HTTP integration tests against a live server on an ephemeral port
# ---------------------------------------------------------------------------


def _service_stub() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        config=types.SimpleNamespace(max_concurrent_tasks=1),
        workspace_info=lambda: {"name": "stub", "path": "/tmp"},
    )


class _Server:
    """Boot the real HTTP handler stack with a stub service."""

    def __init__(self, auth: WebAuth) -> None:
        self.server = MiniccHTTPServer(("127.0.0.1", 0), _service_stub(), auth=auth)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _get(url: str, *, headers: dict[str, str] | None = None, method: str = "GET"):
    request = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_health_open_but_api_requires_token() -> None:
    server = _Server(WebAuth("tok-123", required=True))
    try:
        status, _, _ = _get(f"{server.url}/api/health")
        assert status == 200
        status, _, body = _get(f"{server.url}/api/workspace")
        assert status == 401
        assert json.loads(body)["auth_required"] is True
    finally:
        server.shutdown()


def test_token_accepted_via_header_and_query() -> None:
    server = _Server(WebAuth("tok-123", required=True))
    try:
        status, _, _ = _get(
            f"{server.url}/api/workspace",
            headers={"Authorization": "Bearer tok-123"},
        )
        assert status == 200
        status, _, _ = _get(f"{server.url}/api/workspace?token=tok-123")
        assert status == 200
        status, _, _ = _get(f"{server.url}/api/workspace?token=wrong")
        assert status == 401
    finally:
        server.shutdown()


def test_cors_origin_echoed_only_for_loopback() -> None:
    server = _Server(WebAuth("tok-123", required=True))
    try:
        status, headers, _ = _get(
            f"{server.url}/api/health",
            headers={"Origin": "https://evil.example.com"},
        )
        assert status == 200
        assert "Access-Control-Allow-Origin" not in headers

        status, headers, _ = _get(
            f"{server.url}/api/health",
            headers={"Origin": "http://localhost:4173"},
        )
        assert status == 200
        assert headers.get("Access-Control-Allow-Origin") == "http://localhost:4173"

        # Preflight from loopback lists Authorization as allowed.
        request = urllib.request.Request(f"{server.url}/api/health", method="OPTIONS")
        request.add_header("Origin", "http://localhost:4173")
        request.add_header("Access-Control-Request-Method", "POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            preflight_headers = dict(response.headers)
        assert preflight_headers.get("Access-Control-Allow-Origin") == "http://localhost:4173"
        assert "Authorization" in preflight_headers.get("Access-Control-Allow-Headers", "")
    finally:
        server.shutdown()


def test_open_loopback_auth_not_required() -> None:
    server = _Server(WebAuth("tok-123", required=False))
    try:
        status, _, _ = _get(f"{server.url}/api/workspace")
        assert status == 200
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# workspace whitelist
# ---------------------------------------------------------------------------


def _service_config(tmp_path: Path, roots: tuple[Path, ...]) -> Config:
    return Config(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        workspace_roots=roots,
    )


def test_switch_workspace_outside_whitelist_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "projects"
    allowed.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    service = AgentService(tmp_path, _service_config(tmp_path, (allowed,)))
    try:
        service.switch_workspace(str(allowed))
        assert service.workspace.resolve() == allowed.resolve()
        with pytest.raises(ValueError, match="白名单"):
            service.switch_workspace(str(outside))
        assert service.workspace.resolve() == allowed.resolve()
    finally:
        service.shutdown()


def test_switch_workspace_allows_subdirectory_of_root(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    child = root / "demo"
    child.mkdir(parents=True)
    service = AgentService(tmp_path, _service_config(tmp_path, (root,)))
    try:
        service.switch_workspace(str(child))
        assert service.workspace.resolve() == child.resolve()
    finally:
        service.shutdown()


def test_switch_workspace_empty_roots_keeps_open_behavior(tmp_path: Path) -> None:
    other = tmp_path / "open-access"
    other.mkdir()
    service = AgentService(tmp_path, _service_config(tmp_path, ()))
    try:
        service.switch_workspace(str(other))
        assert service.workspace.resolve() == other.resolve()
    finally:
        service.shutdown()
