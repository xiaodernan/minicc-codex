"""Targeted regression coverage for gateway-specific ultra reasoning support."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError

from minicc.config import load_config, normalize_reasoning_effort
from minicc.llm.openai_provider import OpenAICompatibleProvider
from minicc.main import _parser


def test_ultra_configuration_and_cli_preserve_requested_effort(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINICC_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MINICC_REASONING_EFFORT", "ultra")
    config = load_config(api_key="test-key")
    assert config.reasoning_effort == "ultra"
    assert normalize_reasoning_effort("ULTRA") == "ultra"
    assert _parser().parse_args(["--reasoning-effort", "ultra"]).reasoning_effort == "ultra"


def _response(protocol):
    if protocol == "responses":
        return SimpleNamespace(
            model="test-model", status="completed", usage=None,
            output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="done")])],
        )
    return SimpleNamespace(
        model="test-model", usage=None,
        choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]), finish_reason="stop")],
    )


@pytest.mark.parametrize("protocol", ["responses", "chat_completions"])
def test_provider_sends_ultra_without_rewriting(protocol):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return _response(protocol)

    client = SimpleNamespace(
        responses=SimpleNamespace(create=create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )
    provider = OpenAICompatibleProvider(
        "https://example.test/v1", "test-key", "test-model", protocol=protocol,
        reasoning_effort="ultra", sdk_client=client,
    )
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}]))
    assert response.content == "done"
    assert len(calls) == 1
    if protocol == "responses":
        assert calls[0]["reasoning"] == {"effort": "ultra"}
        assert calls[0]["store"] is False
    else:
        assert calls[0]["reasoning_effort"] == "ultra"
    assert provider.reasoning_status() == {
        "requested": "ultra", "active": "ultra", "wire_value": "ultra", "fallback": False,
    }


def test_ultra_can_negotiate_full_fallback_chain_after_explicit_rejections():
    efforts = []

    async def create(**kwargs):
        effort = kwargs.get("reasoning", {}).get("effort")
        efforts.append(effort)
        if effort is not None:
            raise BadRequestError(
                "unsupported reasoning effort", body=None,
                response=httpx.Response(400, request=httpx.Request("POST", "https://example.test/v1/responses")),
            )
        return _response("responses")

    provider = OpenAICompatibleProvider(
        "https://example.test/v1", "test-key", "test-model", protocol="responses",
        reasoning_effort="ultra", sdk_client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}]))
    assert response.content == "done"
    assert efforts == ["ultra", "max", "xhigh", "high", "medium", "low", None]
    assert provider.reasoning_status() == {
        "requested": "ultra", "active": "off", "wire_value": None, "fallback": True,
    }


def test_streaming_preserves_ultra_and_disables_storage():
    calls = []

    async def stream():
        yield SimpleNamespace(type="response.output_text.delta", delta="done")
        yield SimpleNamespace(type="response.completed", response=_response("responses"))

    async def create(**kwargs):
        calls.append(kwargs)
        return stream()

    provider = OpenAICompatibleProvider(
        "https://example.test/v1", "test-key", "test-model", protocol="responses",
        reasoning_effort="ultra", sdk_client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    deltas = []
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}], on_delta=deltas.append))
    assert response.content == "done"
    assert deltas == ["done"]
    assert calls[0]["stream"] is True
    assert calls[0]["reasoning"] == {"effort": "ultra"}
    assert calls[0]["store"] is False
