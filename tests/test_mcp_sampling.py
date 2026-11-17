"""M12 — MCP sampling: a server may ask the client for one completion, guarded and audited.

Two gates must both be open before a sampling/createMessage from an MCP
server is answered: the server entry's own ``sampling_enabled`` (in
``.minicc/mcp.json``) and the deployment's global ``MINICC_SAMPLING_ENABLED``
(the web layer only wires a provider factory then). Either closed → the
server gets a JSON-RPC error, never silence. Every request goes through
``SamplingGuard`` — rate limit, token ceiling, model allowlist — and every
decision is audited to ``.minicc/mcp_sampling_audit.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import minicc.mcp as mcp_mod
from minicc.mcp import (
    McpManager,
    McpServerConfig,
    SamplingGuard,
    SamplingRequest,
    load_mcp_config,
    McpError,
)


# ---------------------------------------------------------------- config loader

def _write_mcp_json(workspace: Path, servers: dict[str, Any]) -> Path:
    directory = workspace / ".minicc"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "mcp.json"
    path.write_text(json.dumps({"servers": servers}), encoding="utf-8")
    return path


def test_sampling_fields_parse_from_mcp_json(tmp_path: Path) -> None:
    _write_mcp_json(tmp_path, {
        "helper": {"command": "node", "args": ["srv.js"], "sampling_enabled": True},
    })
    configs = load_mcp_config(tmp_path)
    assert configs[0].sampling_enabled is True


def test_sampling_defaults_to_off(tmp_path: Path) -> None:
    _write_mcp_json(tmp_path, {"helper": {"command": "node"}})
    configs = load_mcp_config(tmp_path)
    assert configs[0].sampling_enabled is False


def test_sampling_enabled_requires_a_json_bool(tmp_path: Path) -> None:
    # A string "true" is exactly the read_only trap (M8-T238): truthy str, not JSON bool.
    _write_mcp_json(tmp_path, {"helper": {"command": "node", "sampling_enabled": "true"}})
    with pytest.raises(McpError):
        load_mcp_config(tmp_path)


# ---------------------------------------------------------------- the guard

def _request(max_tokens: int = 100, model: str | None = None) -> SamplingRequest:
    prefs = {"hints": [{"name": model}]} if model else None
    return SamplingRequest(messages=[{"role": "user", "content": "hi"}],
                           model_preferences=prefs, max_tokens=max_tokens)


def test_guard_rate_limits_per_server(tmp_path: Path) -> None:
    guard = SamplingGuard(tmp_path, max_requests_per_minute=2)
    assert guard.check_request("a", _request())[0] is True
    assert guard.check_request("a", _request())[0] is True
    allowed, reason = guard.check_request("a", _request())
    assert allowed is False and "Rate limit" in reason
    # a different server is unaffected
    assert guard.check_request("b", _request())[0] is True


def test_guard_enforces_the_token_ceiling(tmp_path: Path) -> None:
    guard = SamplingGuard(tmp_path, max_tokens_per_request=64)
    allowed, reason = guard.check_request("a", _request(max_tokens=128))
    assert allowed is False and "Max tokens" in reason


def test_guard_enforces_the_model_allowlist(tmp_path: Path) -> None:
    guard = SamplingGuard(tmp_path, allowed_models=("gpt-6.1-terra",))
    assert guard.check_request("a", _request(model="gpt-6.1-terra"))[0] is True
    allowed, reason = guard.check_request("a", _request(model="something-else"))
    assert allowed is False and "not in allowed list" in reason
    # no hint at all is not a violation - the name gate only fires on hints
    assert guard.check_request("a", _request())[0] is True


def test_guard_audits_every_decision(tmp_path: Path) -> None:
    guard = SamplingGuard(tmp_path, max_requests_per_minute=1)
    guard.check_request("a", _request(max_tokens=1))
    guard.audit_log("a", _request(max_tokens=1), True, "OK")
    guard.check_request("a", _request(max_tokens=1))
    guard.audit_log("a", _request(max_tokens=1), False, "Rate limit exceeded: 1 req/min")
    lines = (tmp_path / ".minicc" / "mcp_sampling_audit.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    assert [entry["allowed"] for entry in entries] == [True, False]
    assert entries[0]["server"] == "a"


# ---------------------------------------------------------------- the handler

class _FakeClient:
    def __init__(self) -> None:
        self.responses: list[tuple[int, Any, Any]] = []

    def _respond(self, msg_id: Any, *, result: Any = None, error: Any = None) -> None:
        self.responses.append((msg_id, result, error))


class _FakeProvider:
    def __init__(self, text: str = "sampling says hi", model: str = "gpt-6.1-terra") -> None:
        self._text = text
        self._model = model
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(self, messages: list[dict[str, Any]], tools: Any = None, on_delta: Any = None):
        self.calls.append(list(messages))
        return SimpleNamespace(text=self._text, model=self._model)


class _ExplodingProvider:
    async def chat(self, messages: list[dict[str, Any]], tools: Any = None, on_delta: Any = None):
        raise RuntimeError("provider exploded")


def _manager(tmp_path: Path, client: Any | None, *, factory: Any = None, models: tuple[str, ...] = ()) -> McpManager:
    manager = McpManager(tmp_path, sampling_provider_factory=factory, sampling_allowed_models=models)
    if client is not None:
        manager.clients["srv"] = client
    return manager


_PARAMS = {
    "messages": [{"role": "user", "content": "say hi"}],
    "maxTokens": 64,
    "systemPrompt": "be terse",
}


def test_handler_refuses_a_server_without_sampling_enabled(tmp_path: Path) -> None:
    # _handle_sampling_request is what the reader thread calls; its disabled branch is honest.
    config = McpServerConfig("srv", command="node", sampling_enabled=False)
    client = mcp_mod.McpStdioClient.__new__(mcp_mod.McpStdioClient)  # no spawn just for this branch
    client.config = config
    client.workspace = tmp_path
    client._sampling_handler = lambda msg_id, params: (_ for _ in ()).throw(AssertionError("not called"))
    client._responses = __import__("queue").Queue()
    # respond straight into the recorder instead of the write path
    recorded = []
    client._respond = lambda msg_id, *, result=None, error=None: recorded.append((msg_id, result, error))
    client._handle_sampling_request(7, {"params": {}})
    assert recorded[0][2]["code"] == -32601


def test_handler_refuses_an_unconfigured_handler(tmp_path: Path) -> None:
    config = McpServerConfig("srv", command="node", sampling_enabled=True)
    client = mcp_mod.McpStdioClient.__new__(mcp_mod.McpStdioClient)
    client.config = config
    client.workspace = tmp_path
    client._sampling_handler = None
    recorded = []
    client._respond = lambda msg_id, *, result=None, error=None: recorded.append((msg_id, result, error))
    client._handle_sampling_request(9, {"params": {}})
    assert recorded[0][2]["code"] == -32603
    assert "not configured" in recorded[0][2]["message"]


def test_handler_completes_and_answers_end_turn(tmp_path: Path) -> None:
    client = _FakeClient()
    provider = _FakeProvider()
    manager = _manager(tmp_path, client, factory=lambda: provider)
    manager._handle_sampling(11, dict(_PARAMS), "srv")
    assert len(client.responses) == 1
    msg_id, result, error = client.responses[0]
    assert msg_id == 11 and error is None
    assert result["role"] == "assistant"
    assert result["stopReason"] == "endTurn"
    assert result["content"] == {"type": "text", "text": "sampling says hi"}
    assert result["model"] == "gpt-6.1-terra"
    # the system prompt reached the provider
    assert provider.calls[0][0] == {"role": "system", "content": "be terse"}
    # and the decision was audited
    lines = (tmp_path / ".minicc" / "mcp_sampling_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["allowed"] is True


def test_handler_refuses_a_disallowed_model_hint(tmp_path: Path) -> None:
    client = _FakeClient()
    manager = _manager(tmp_path, client, factory=lambda: _FakeProvider(), models=("gpt-6.1-terra",))
    params = dict(_PARAMS)
    params["modelPreferences"] = {"hints": [{"name": "other-model"}]}
    manager._handle_sampling(12, params, "srv")
    _, result, error = client.responses[0]
    assert result is None and "Sampling denied" in error["message"]
    # audited as denied, provider never called
    lines = (tmp_path / ".minicc" / "mcp_sampling_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["allowed"] is False


def test_handler_without_a_provider_factory_is_an_error(tmp_path: Path) -> None:
    client = _FakeClient()
    manager = _manager(tmp_path, client, factory=None)
    manager._handle_sampling(13, dict(_PARAMS), "srv")
    _, result, error = client.responses[0]
    assert result is None
    assert error["code"] == -32603
    assert "No provider configured" in error["message"]


def test_handler_sanitizes_bad_params(tmp_path: Path) -> None:
    client = _FakeClient()
    manager = _manager(tmp_path, client, factory=lambda: _FakeProvider())
    manager._handle_sampling(14, {"messages": []}, "srv")
    assert client.responses[0][2]["code"] == -32602
    manager._handle_sampling(15, {"messages": [{"role": "user"}]}, "srv")
    assert client.responses[1][2]["code"] == -32602
    manager._handle_sampling(16, {"messages": [{"role": "user", "content": "x"}], "maxTokens": "nope"}, "srv")
    assert client.responses[2][2]["code"] == -32602


def test_handler_survives_a_provider_explosion(tmp_path: Path) -> None:
    client = _FakeClient()
    manager = _manager(tmp_path, client, factory=lambda: _ExplodingProvider())
    manager._handle_sampling(17, dict(_PARAMS), "srv")
    _, result, error = client.responses[0]
    assert result is None and "Sampling failed" in error["message"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
