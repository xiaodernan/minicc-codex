"""Benchmark runner tests: fixture integrity + execution against a fake provider."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.benchmarks import load_tasks, main, run_benchmark


def _fake_provider_factory(monkeypatch: pytest.MonkeyPatch, answer: str = "评测任务已完成。") -> None:
    """Patch the web service provider so no real model is contacted."""
    from minicc import web as web_module

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            import json as _json
            if tools is None:
                decision = _json.dumps({
                    "status": "complete", "confidence": 0.9, "rationale": "fake",
                    "missing": [], "next_action": "", "evidence": ["fake"],
                }, ensure_ascii=False)
                return SimpleNamespace(text=decision, usage={"total_tokens": 8}, reasoning_content=None, tool_calls=[], finish_reason="stop", model="fake")
            return SimpleNamespace(text=answer, usage={"total_tokens": 42}, reasoning_content=None, tool_calls=[], finish_reason="stop", model="fake")

        async def close(self):
            return None

    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", FakeProvider)


def _service_config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )


def test_fixtures_have_prompts_and_only_readonly_verify() -> None:
    tasks = load_tasks()
    assert len(tasks) == 30
    for task in tasks:
        assert task.get("prompt"), f"task {task['id']} missing prompt"
        command = task.get("verify_command")
        if command:
            lowered = str(command).lower()
            for forbidden in (">", "rm ", "del ", "git commit", "pip install", "npm install"):
                assert forbidden not in lowered, f"task {task['id']} verify_command mutates: {command}"


def test_run_benchmark_executes_and_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_provider_factory(monkeypatch)
    from minicc.web import AgentService

    original_init = AgentService.__init__

    def patched_init(self, workspace, config, *args, **kwargs):
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)
    results_path = tmp_path / "results.json"
    tasks = load_tasks()
    results = run_benchmark(tasks[:2], workspace=tmp_path, max_tasks=None, results_path=results_path)
    assert len(results) == 2
    first = results[0]
    assert first["status"] == "completed"
    assert "latency_ms" in first
    assert first["passed"] is None  # first two fixtures carry no verify command
    assert results_path.is_file()  # incremental flush
    assert len(json.loads(results_path.read_text(encoding="utf-8"))) == 2


def test_run_benchmark_grades_verify_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_provider_factory(monkeypatch)
    from minicc.web import AgentService

    original_init = AgentService.__init__

    def patched_init(self, workspace, config, *args, **kwargs):
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)
    tasks = [{"id": "echo-check", "category": "verify", "prompt": "回答任意内容。", "verify_command": "python -c \"print('ok')\""}]
    results = run_benchmark(tasks, workspace=tmp_path)
    assert results[0]["passed"] is True


def test_run_benchmark_survives_single_task_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_provider_factory(monkeypatch)
    from minicc.web import AgentService

    original_chat_locked = AgentService._chat_locked
    calls = {"count": 0}

    def flaky_chat_locked(self, payload, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return original_chat_locked(self, payload, **kwargs)

    monkeypatch.setattr(AgentService, "_chat_locked", flaky_chat_locked)

    original_init = AgentService.__init__

    def patched_init(self, workspace, config, *args, **kwargs):
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)
    tasks = load_tasks()[:2]
    results = run_benchmark(tasks, workspace=tmp_path)
    assert len(results) == 2
    assert results[0]["status"] == "failed"
    assert "boom" in results[0]["error"]
    assert results[1]["status"] == "completed"


def test_main_without_run_never_calls_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding_run(*args, **kwargs):
        raise AssertionError("run_benchmark must not be called without --run")

    monkeypatch.setattr("minicc.benchmarks.run_benchmark", exploding_run)
    exit_code = main([
        "--json-out", str(tmp_path / "eval.json"),
        "--markdown-out", str(tmp_path / "eval.md"),
    ])
    assert exit_code == 0
    assert (tmp_path / "eval.json").is_file()
