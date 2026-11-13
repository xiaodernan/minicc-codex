"""prompt_cache_key: the gateway gets a stable cache-affinity shard.

wkapi.pro-style proxies rotate upstream shards per call, so byte-identical
prefixes land on cold caches. OpenAI's own `prompt_cache_key` parameter exists
to pin a conversation to one shard. minicc now derives one from the
gateway+model pair (or honours MINICC_PROMPT_CACHE_KEY) and forwards it on
both wire families; this file locks that contract in with a fake SDK.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from minicc.config import load_config
from minicc.llm.openai_provider import OpenAICompatibleProvider


def _provider(**kwargs: Any) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url=kwargs.pop("base_url", "https://gateway.test/v1"),
        api_key="test-key",
        model=kwargs.pop("model", "test-model"),
        timeout=10,
        **kwargs,
    )


def test_derived_key_is_stable_opaque_and_model_specific() -> None:
    first = _provider()
    second = _provider()
    assert first._effective_prompt_cache_key() == second._effective_prompt_cache_key()
    key = first._effective_prompt_cache_key()
    assert key.startswith("minicc-")
    # Opaque: no gateway path, no workspace path, no credentials leak into it.
    assert "gateway" not in key
    assert "v1" not in key
    assert key != _provider(model="other-model")._effective_prompt_cache_key()


def test_explicit_key_wins_and_is_capped_at_64_chars() -> None:
    provider = _provider(prompt_cache_key="my-shared-key")
    assert provider._effective_prompt_cache_key() == "my-shared-key"
    long_provider = _provider(prompt_cache_key="x" * 200)
    assert len(long_provider._effective_prompt_cache_key()) == 64


def test_config_picks_up_env_knob(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_PROMPT_CACHE_KEY", "tenant-stable-key")
    monkeypatch.setenv("MINICC_API_KEY", "sk-test")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    config = load_config()
    assert config.prompt_cache_key == "tenant-stable-key"


def test_config_defaults_to_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [k for k in __import__("os").environ if k.startswith("MINICC_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MINICC_API_KEY", "sk-test")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    config = load_config()
    assert config.prompt_cache_key == ""


def test_responses_request_carries_prompt_cache_key() -> None:
    seen: dict[str, Any] = {}

    class FakeResponses:
        async def create(self, **kwargs: Any):
            seen.update(kwargs)
            return SimpleNamespace(
                model="test-model",
                status="completed",
                usage=SimpleNamespace(input_tokens=5, output_tokens=2, total_tokens=7),
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="output_text", text="ok")],
                    ),
                ],
            )

    provider = _provider(
        protocol="responses",
        sdk_client=SimpleNamespace(responses=FakeResponses()),
    )
    import asyncio

    asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))
    assert seen["prompt_cache_key"] == provider._effective_prompt_cache_key()


def test_chat_completions_request_carries_prompt_cache_key() -> None:
    seen: dict[str, Any] = {}

    class FakeChatCompletions:
        async def create(self, **kwargs: Any):
            seen.update(kwargs)
            return SimpleNamespace(
                model="test-model",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="ok", tool_calls=None),
                        finish_reason="stop",
                    ),
                ],
                usage=SimpleNamespace(
                    prompt_tokens=5,
                    completion_tokens=2,
                    total_tokens=7,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=4),
                ),
            )

    provider = _provider(
        protocol="chat_completions",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions())),
    )
    import asyncio

    asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))
    assert seen["prompt_cache_key"] == provider._effective_prompt_cache_key()


def test_cli_usage_line_includes_cache_counters() -> None:
    """The operator-visible [usage] line must show cache efficiency."""
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "minicc" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "cache_hit_tokens=" in text
    assert "cache_miss_tokens=" in text
    assert "cache_hit_pct=" in text
