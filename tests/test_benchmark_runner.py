"""Benchmark runner tests: fixture integrity + execution against a fake provider."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.benchmarks import _write_results, load_tasks, main, run_benchmark


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
                    "missing": [], "next_action": "", "evidence": re.findall(r'"id":"((?:event|verification)-\d+)"', str(messages))[-1:],
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


def test_targeted_suite_selection_and_unknown_ids(tmp_path, monkeypatch):
    recorded = {}

    def run(tasks, **kwargs):
        recorded.update(tasks=tasks, options=kwargs)
        return []

    monkeypatch.setattr("minicc.benchmarks.run_benchmark", run)
    assert main(["--suite", "behavior", "--task-id", "behavior-median", "--run", "--no-resume",
                 "--json-out", str(tmp_path / "report.json"), "--markdown-out", str(tmp_path / "report.md")]) == 0
    assert [task["id"] for task in recorded["tasks"]] == ["behavior-median"]
    assert recorded["options"]["resume"] is False
    with pytest.raises(SystemExit):
        main(["--suite", "behavior", "--task-id", "does-not-exist"])


def test_atomic_results_keep_previous_checkpoint_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "results.json"
    _write_results(path, [{"task_id": "first"}])

    def interrupted(*args):
        raise OSError("interrupted")

    monkeypatch.setattr("minicc.benchmarks.os.replace", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        _write_results(path, [{"task_id": "second"}])
    assert json.loads(path.read_text()) == [{"task_id": "first"}]
    assert list(tmp_path.iterdir()) == [path]


def test_resume_drops_old_configuration_rows_and_reuses_current_rows(tmp_path, monkeypatch):
    calls = []
    config = _service_config()

    class Service:
        def __init__(self, *args, **kwargs):
            pass

        def _chat_locked(self, payload, **kwargs):
            calls.append(payload["message"])
            return {"answer": "done", "completion": {"status": "complete"}}

        def shutdown(self):
            pass

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", lambda: config)
    tasks = [{"id": "a", "prompt": "a"}, {"id": "b", "prompt": "b"}]
    path = tmp_path / "results.json"
    run_benchmark(tasks, workspace=tmp_path, results_path=path)
    assert calls == ["a", "b"]
    run_benchmark(tasks, workspace=tmp_path, results_path=path)
    assert calls == ["a", "b"]
    config.base_url = "https://different-provider.test/v1"
    results = run_benchmark(tasks, workspace=tmp_path, results_path=path, max_tasks=1)
    assert calls == ["a", "b", "a"]
    assert [item["task_id"] for item in results] == ["a"]
    assert "different-provider" not in path.read_text()


def test_fixture_setup_failure_is_recorded_and_next_task_runs(tmp_path, monkeypatch):
    class Service:
        def __init__(self, *args, **kwargs):
            pass

        def _chat_locked(self, payload, **kwargs):
            return {"answer": "ok"}

        def shutdown(self):
            pass

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    tasks = [{"id": "unsafe-fixture", "prompt": "x", "fixture": {"../escape.py": "x"}}, {"id": "next", "prompt": "ok"}]
    results = run_benchmark(tasks, workspace=tmp_path)
    assert results[0]["status"] == "failed"
    assert "escapes workspace" in results[0]["error"]
    assert results[1]["status"] == "completed"


@pytest.mark.parametrize("outcome, status", [
    ({"answer": "cancelled", "cancelled": True}, "cancelled"),
    ({"answer": "partial", "completion": {"status": "continue"}}, "incomplete"),
    ({"answer": "blocked", "completion": {"status": "blocked"}}, "incomplete"),
])
def test_cancelled_and_partial_outcomes_are_not_graded_as_complete(tmp_path, monkeypatch, outcome, status):
    class Service:
        def __init__(self, *args, **kwargs): pass
        def _chat_locked(self, *args, **kwargs): return outcome
        def shutdown(self): pass
    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    monkeypatch.setattr("minicc.benchmarks.grade_behavior", lambda *args: (_ for _ in ()).throw(AssertionError("must not grade")))
    tasks=[{"id": "case", "prompt": "x", "grader": {"type": "answer_rubric"}}]
    results=run_benchmark(tasks,workspace=tmp_path)
    assert results[0]["status"] == status
    assert results[0]["passed"] is False
    assert results[0]["claimed_complete"] is False


def test_subminute_deadline_cancels_worker(tmp_path, monkeypatch):
    import time

    class Service:
        def __init__(self, *args, **kwargs):
            pass

        def _chat_locked(self, payload, cancel_event, **kwargs):
            cancel_event.wait(3)
            return {"answer": "cancelled"}

        def shutdown(self):
            pass

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    started = time.monotonic()
    results = run_benchmark([{"id": "timeout", "prompt": "wait"}], workspace=tmp_path, task_timeout_seconds=0.05)
    assert time.monotonic() - started < 2
    assert results[0]["status"] == "failed"
    assert "timeout" in results[0]["error"]


def test_unresponsive_worker_stops_run_without_shutting_down_its_service(tmp_path, monkeypatch):
    calls = []
    worker_threads = []
    cleanup_threads = []
    shutdown = []

    class Service:
        def __init__(self, *args, **kwargs):
            pass

        def _chat_locked(self, payload, **kwargs):
            calls.append(payload["message"])

        def shutdown(self):
            shutdown.append(True)

    class Thread:
        def __init__(self, target, name, **kwargs):
            self.target = target
            self.name = name
            self.timeouts = []
            (cleanup_threads if name == "bench-cleanup" else worker_threads).append(self)

        def start(self):
            pass

        def join(self, timeout=None):
            self.timeouts.append(timeout)

        def is_alive(self):
            return True

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    monkeypatch.setattr("minicc.benchmarks.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout="revision"))
    monkeypatch.setattr("minicc.benchmarks.threading.Thread", Thread)
    results = run_benchmark([{"id": "first", "prompt": "wait"}, {"id": "second", "prompt": "next"}],
                            workspace=tmp_path, task_timeout_seconds=0.01)
    assert len(results) == 1
    assert worker_threads[0].timeouts == [0.01, 5]
    assert not shutdown
    assert len(cleanup_threads) == 1
    cleanup_threads[0].target()
    assert shutdown == [True]


def test_interruption_saves_completed_rows_and_current_cancellation(tmp_path, monkeypatch):
    shutdown = []

    class Service:
        def __init__(self, *args, **kwargs):
            pass

        def _chat_locked(self, payload, **kwargs):
            if payload["message"] == "stop":
                raise KeyboardInterrupt()
            return {"answer": "done"}

        def shutdown(self):
            shutdown.append(True)

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    path = tmp_path / "results.json"
    with pytest.raises(KeyboardInterrupt):
        run_benchmark([{"id": "done", "prompt": "done"}, {"id": "stop", "prompt": "stop"}],
                      workspace=tmp_path, results_path=path)
    results = json.loads(path.read_text())
    assert [item["status"] for item in results] == ["completed", "interrupted"]
    assert shutdown == [True]
