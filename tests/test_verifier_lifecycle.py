"""Verification must honor current inputs, current commands and cancellation."""
from pathlib import Path
import threading
import time

from minicc.agent.verification_plan import build_verification_plan, VerificationCommand
from minicc.agent.verifier import Verifier
from minicc.tools.schemas import ToolResult


def test_changed_command_and_stale_plan_cannot_reuse_success(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    (tmp_path / "test_app.py").write_text("def test_one(): pass\n")
    plan = build_verification_plan(tmp_path, ["app.py"])
    executed = []
    def run(command, *_):
        executed.append(command)
        return ToolResult(status="ok", exit_code=0)
    verifier = Verifier(run)
    assert verifier.run(tmp_path, plan=plan).passed
    assert verifier.run(tmp_path, plan=plan).cached
    assert not verifier.run(tmp_path, [VerificationCommand("node --check other.js")], plan=plan).cached
    source.write_text("value = 2\n")
    assert not verifier.run(tmp_path, plan=plan).cached
    assert len(executed) == 3


def test_inputs_changed_during_check_do_not_get_cached_or_passed(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("a = 1\n")
    (tmp_path / "test_app.py").write_text("def test_app(): pass\n")
    plan = build_verification_plan(tmp_path, ["app.py"])
    def execute(*_):
        path.write_text("a = 2\n")
        return ToolResult(status="ok", exit_code=0)
    result = Verifier(execute).run(tmp_path, plan=plan)
    assert result.status == "failed" and "发生变化" in result.actionable_hint
    assert not result.fingerprint


def test_cancel_is_forwarded_and_stops_subsequent_checks(tmp_path):
    cancel = threading.Event()
    calls = []
    def execute(command, root, timeout, cancel_event=None):
        calls.append(command)
        assert cancel_event is cancel
        cancel.set()
        return ToolResult(status="cancelled")
    result = Verifier(execute).run(tmp_path, [VerificationCommand("python -m pytest a.py"), VerificationCommand("python -m pytest b.py")], cancel_event=cancel)
    assert result.status == "cancelled" and len(calls) == 1
    assert result.to_event()["status"] == "cancelled"


def test_real_check_process_is_cancelled_promptly(tmp_path, suite_python_bin):
    # The check leaves evidence 3s in. Cancelling at 1s therefore has an observable
    # consequence - "the marker never appears" - instead of only a shorter wall clock.
    (tmp_path / "test_wait.py").write_text(
        "import time\n"
        "\n"
        "\n"
        "def test_wait():\n"
        "    time.sleep(3)\n"
        "    open('check_outlived_the_cancel', 'w').close()\n"
    )
    cancel = threading.Event()
    timer = threading.Timer(1, cancel.set)
    started = time.monotonic()
    timer.start()
    try:
        result = Verifier().run(tmp_path, [VerificationCommand(f"{suite_python_bin} -m pytest test_wait.py -q", timeout=40)], cancel_event=cancel)
    finally:
        timer.cancel()
    assert result.status == "cancelled"
    # M8-T63: `elapsed < 8` used to stand in for "the check process was stopped", but a
    # process abandoned at 1s satisfies it just as well as one killed at 1s, and one
    # killed at 9s fails it for the wrong reason. The grace wait only has to outlast the
    # check's own 3s sleep - it is setup, not the judgement.
    time.sleep(4.0)
    assert not (tmp_path / "check_outlived_the_cancel").exists(), (
        "the cancelled check was abandoned rather than stopped: it finished its sleep "
        "and wrote its marker"
    )
    assert time.monotonic() - started < 30, "the verifier never came back at all"


def test_invalid_rule_is_clear_and_large_dependency_disables_reuse(tmp_path):
    import json
    import pytest
    (tmp_path / ".minicc").mkdir()
    config = tmp_path / ".minicc/verification.json"
    config.write_text(json.dumps({"rules": [{"paths": "web/**", "commands": ["npm run check:web"]}]}))
    with pytest.raises(ValueError, match="paths"):
        build_verification_plan(tmp_path, ["web/src/app.js"])
    config.unlink()
    (tmp_path / "test_app.py").write_text("def test_one(): pass\n")
    (tmp_path / "large.txt").write_text("x" * 2_000_001)
    assert build_verification_plan(tmp_path, ["test_app.py"]).fingerprint == ""


def test_configured_collection_or_help_cannot_pass_as_validation(tmp_path):
    calls = []
    def execute(command, *_):
        calls.append(command)
        return ToolResult(status="ok", exit_code=0)
    for command in ("python -m pytest --collect-only", "python -m pytest --help"):
        assert Verifier(execute).run(tmp_path, [VerificationCommand(command)]).status == "blocked"
    assert not calls
    assert Verifier(execute).run(tmp_path, [VerificationCommand("python -B -m unittest test_one")]).passed


def test_verification_output_is_redacted_before_evidence_storage(tmp_path):
    result = Verifier(lambda *_: ToolResult(status="ok", exit_code=0, output="sk-abcdef0123456789" )).run(tmp_path, [VerificationCommand("python -m pytest test_one.py")])
    assert "sk-abcdef" not in str(result.to_dict())
    assert "REDACTED" in result.output


def test_hidden_configs_invalidate_and_secret_environment_disables_reuse(tmp_path):
    (tmp_path / "test_app.py").write_text("def test_one(): pass\n")
    config = tmp_path / ".coveragerc"
    config.write_text("[run]\nbranch=False\n")
    first = build_verification_plan(tmp_path, ["test_app.py"])
    config.write_text("[run]\nbranch=True\n")
    assert first.fingerprint != build_verification_plan(tmp_path, ["test_app.py"]).fingerprint
    (tmp_path / ".env").write_text("EXAMPLE_TEST_MODE=one\n")
    assert build_verification_plan(tmp_path, ["test_app.py"]).fingerprint == ""


def test_service_cancellation_during_auto_verification_does_not_call_reviewer(tmp_path, monkeypatch):
    import json
    import minicc.web as web
    from minicc.config import Config
    from minicc.agent.loop import TurnResult
    from minicc.tools.schemas import ToolCall
    from minicc.task_store import TaskStore
    cancel = threading.Event()
    (tmp_path / "app.py").write_text("value=1\n")
    (tmp_path / "test_app.py").write_text("def test_ok(): pass\n")
    async def run(*args, **kwargs):
        kwargs["on_tool"](ToolCall("write_file", {"path": "app.py"}), ToolResult(status="ok", exit_code=0))
        return TurnResult(answer="written")
    class Provider:
        def __init__(self, **kwargs): pass
        async def close(self): pass
    def verify(self, workspace, **kwargs):
        assert kwargs["cancel_event"] is cancel
        cancel.set()
        return web.VerificationResult(status="cancelled")
    async def judge(*args, **kwargs):
        raise AssertionError("cancelled task must not invoke completion review")
    monkeypatch.setattr(web, "run_agent", run)
    monkeypatch.setattr(web, "OpenAICompatibleProvider", Provider)
    monkeypatch.setattr(web.Verifier, "run", verify)
    monkeypatch.setattr(web, "judge_completion", judge)
    config = Config(base_url="https://example.invalid/v1", api_key="test", model="test", sandbox_mode="host")
    service = web.AgentService(tmp_path, config, task_store=TaskStore(tmp_path / "task.sqlite3"))
    try:
        result = service._chat_locked({"message": "edit app.py", "allow_changes": True}, workspace=tmp_path, cancel_event=cancel)
    finally:
        service.shutdown()
    assert result["cancelled"] is True
    assert result["error"] is None
    assert any(event.get("code") == "verification_cancelled" for event in result["events"])
