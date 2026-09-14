"""Multi-model fallback tests: config parsing, router wiring, rotation event."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.agent.router import StageRouter
from minicc.config import ConfigError, load_config
from minicc.web import AgentService


def test_config_parses_fallback_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINICC_API_KEY", "test-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICC_FALLBACK_MODELS", "model-b, model-c ;model-b,model-d")
    config = load_config()
    assert config.fallback_models == ("model-b", "model-c", "model-d")


def test_config_fallback_empty_and_primary_excluded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINICC_API_KEY", "test-key")
    monkeypatch.setenv("MINICC_MODEL", "primary")
    monkeypatch.setenv("MINICC_FALLBACK_MODELS", "primary,other,")
    config = load_config()
    assert config.fallback_models == ("other",)


def test_router_carries_fallback_models() -> None:
    router = StageRouter("primary", 100.0, fallback_models=("backup-1", "backup-2"))
    route = router.route("implement")
    assert route.fallback_models == ("backup-1", "backup-2")
    payload = route.to_dict()
    assert payload["fallback_models"] == ["backup-1", "backup-2"]


def _service(tmp_path: Path) -> AgentService:
    return AgentService(
        tmp_path,
        SimpleNamespace(
            yolo=False,
            max_concurrent_tasks=2,
            sandbox_mode="host",
            sandbox_image="python:3.11-slim",
            base_url="https://example.test/v1",
            api_key="test-key",
            model="primary",
            timeout=10,
            tool_mode="auto",
            reasoning_effort="high",
            max_turns=4,
            compact_threshold=300_000,
            context_window_tokens=300_000,
            fallback_models=("backup-1", "backup-2"),
        ),
    )


class FailingTwiceProvider:
    """Fails the first two chats, then answers with the model it saw."""

    instances: list["FailingTwiceProvider"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.model = str(kwargs.get("model") or "")
        self.attempts = 0
        FailingTwiceProvider.instances.append(self)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return error is not None

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages, tools, on_delta=None):
        self.attempts += 1
        if self.attempts <= 2:
            raise RuntimeError("gateway exploded")
        from minicc.llm.base import LLMResponse

        return LLMResponse(content=f"answered-by:{self.model}")

    async def close(self):
        return None


def test_recovery_rotates_to_fallback_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    FailingTwiceProvider.instances.clear()
    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FailingTwiceProvider)
    service = _service(tmp_path)
    try:
        result = service._chat_locked(
            {"message": "测试 fallback 轮换", "allow_changes": False, "workspace_path": str(tmp_path)},
            workspace=tmp_path,
        )
        events = result.get("events") or []
        fallback_events = [event for event in events if event.get("code") == "task_model_fallback"]
        assert fallback_events, "expected a task_model_fallback trace event"
        assert fallback_events[0]["detail"]["model"] in {"backup-1", "backup-2"}
    finally:
        service.shutdown()
