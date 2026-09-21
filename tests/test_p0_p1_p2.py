"""M1 provider/loop integrity tests (ROADMAP_TO_PRODUCT M1-T1..T7).

Each test pins one fixed defect; where the defect was an always-green
assertion, the test asserts the corrected behavior (prompt/total/miss
values, dedup ids, terminal finish_reason handling).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from minicc.agent.loop import run_agent
from minicc.agent.state import Budget
from minicc.agent.tool_policy import is_verification_evidence, tool_requires_authorization
from minicc.audit import authorize_tool
from minicc.config import load_config
from minicc.llm.base import LLMResponse
from minicc.session import SessionError, SessionStore
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolCall, ToolResult
from minicc.web import AgentService, MiniccHTTPServer, TaskRecord
from minicc.webauth import WebAuth


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "id": f"call-{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


class ScriptedProvider:
    def __init__(self, script: list[LLMResponse]) -> None:
        self.script = script
        self.calls = 0

    async def chat(self, messages, tools, on_delta=None):
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        response = self.script[index]
        if on_delta is not None and response.content:
            on_delta(response.content)
        return response

    async def close(self) -> None:
        return None


class FakeSandbox:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, command, workspace, timeout=120, cancel_event=None):
        self.commands.append(str(command))
        return ToolResult(status="ok", summary="command ok", output="ok")


def _service_config(**extra) -> types.SimpleNamespace:
    base = dict(
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
    base.update(extra)
    return types.SimpleNamespace(**base)


def test_webfetch_requires_authorization_even_when_readonly() -> None:
    assert tool_requires_authorization("webfetch", "readonly") is True
    assert tool_requires_authorization("web_search", "readonly") is True
    assert tool_requires_authorization("read_file", "readonly") is False
    assert tool_requires_authorization("write_file", "write") is True
    denied = authorize_tool(
        "webfetch",
        "readonly",
        {"url": "https://example.com/page"},
        allow_changes=False,
        allow_network=False,
    )
    assert denied.allowed is False
    assert denied.authorization == "missing_task_network"


def test_git_status_is_not_verification_evidence() -> None:
    assert is_verification_evidence("git_status", {}, "ok") is False
    assert is_verification_evidence("read_file", {"path": "a.py"}, "ok") is False
    assert is_verification_evidence("grep", {"pattern": "x"}, "ok") is False
    assert is_verification_evidence("bash", {"command": "git status"}, "ok") is False
    assert is_verification_evidence("bash", {"command": "python -m pytest -q"}, "ok") is True
    assert is_verification_evidence("bash", {"command": "npm test"}, "ok") is True
    assert is_verification_evidence("bash", {"command": "python -m pytest -q"}, "error") is False


def test_run_agent_denies_webfetch_without_network_and_does_not_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hits: list[str] = []

    def boom(*_args, **_kwargs):
        hits.append("http")
        raise AssertionError("webfetch must not send HTTP when denied")

    import importlib

    webfetch_mod = importlib.import_module("minicc.tools.webfetch")
    monkeypatch.setattr(webfetch_mod, "fetch_url_text", boom)
    registry = build_registry(Editor(tmp_path))

    def should_allow(name: str, call: ToolCall) -> bool:
        return authorize_tool(
            name,
            registry.risk_of(name),
            call.arguments,
            allow_changes=False,
            allow_network=False,
        ).allowed

    provider = ScriptedProvider([
        LLMResponse(tool_calls=[_tool_call("webfetch", {"url": "https://example.com/secret"})]),
        LLMResponse(content="联网被拒绝后改为只读结论。"),
    ])
    traces: list[dict] = []
    result = asyncio.run(
        run_agent(
            provider,
            registry,
            [{"role": "user", "content": "抓取 https://example.com/secret"}],
            should_allow=should_allow,
            on_trace=traces.append,
            max_turns=4,
        )
    )
    assert hits == []
    assert "webfetch" in result.denied_tools
    assert any(event.get("status") == "denied" for event in traces) or result.denied_tools


def test_git_status_does_not_clear_post_write_verification(tmp_path: Path) -> None:
    provider = ScriptedProvider([
        LLMResponse(tool_calls=[_tool_call("write_file", {"path": "changed.txt", "content": "changed\n"})]),
        LLMResponse(tool_calls=[_tool_call("git_status", {})]),
        LLMResponse(content="已经完成修改。"),
        LLMResponse(content="仍然结束。"),
    ])
    traces: list[dict] = []
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "修改 changed.txt 并完成验证"}],
            should_allow=lambda _name, _call: True,
            on_trace=traces.append,
            max_turns=8,
        )
    )
    assert (tmp_path / "changed.txt").read_text(encoding="utf-8") == "changed\n"
    assert result.error == "Agent 在修改工作区后没有完成验证"
    assert any(event.get("code") == "verification_required_before_finish" for event in traces)
    assert not any(event.get("code") == "verification_observed" for event in traces)


def test_pytest_command_clears_post_write_verification(tmp_path: Path) -> None:
    sandbox = FakeSandbox()
    provider = ScriptedProvider([
        LLMResponse(tool_calls=[_tool_call("write_file", {"path": "changed.txt", "content": "changed\n"})]),
        LLMResponse(tool_calls=[_tool_call("bash", {"command": "python -m pytest -q"})]),
        LLMResponse(content="测试已通过，修改完成。"),
    ])
    traces: list[dict] = []
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path), sandbox=sandbox),
            [{"role": "user", "content": "修改 changed.txt 并完成验证"}],
            should_allow=lambda _name, _call: True,
            on_trace=traces.append,
            max_turns=8,
        )
    )
    assert result.error is None
    assert "测试已通过" in (result.answer or "")
    assert any(event.get("code") == "verification_observed" for event in traces)
    assert sandbox.commands and "pytest" in sandbox.commands[0]


def test_soft_budget_wraps_up_then_stops(tmp_path: Path) -> None:
    provider = ScriptedProvider([
        LLMResponse(content="还在继续。", usage={"total_tokens": 80}),
        LLMResponse(content="这是收束摘要。", usage={"total_tokens": 20}),
        LLMResponse(content="不应该再来一轮。", usage={"total_tokens": 20}),
    ])
    traces: list[dict] = []
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "写一份很长的分析"}],
            budget=Budget(soft_max_tokens=50, max_turns=8),
            on_trace=traces.append,
            max_turns=8,
        )
    )
    codes = [event.get("code") for event in traces]
    assert "soft_budget_wrap_up" in codes
    assert "soft_budget_stopped" in codes
    assert "BudgetExceeded" not in (result.error or "")
    assert "不应该再来一轮" not in (result.answer or "")


def test_sandbox_defaults_to_auto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-config")
    monkeypatch.delenv("MINICC_SANDBOX", raising=False)
    monkeypatch.chdir(tmp_path)
    assert load_config().sandbox_mode == "auto"


def test_worker_command_keeps_api_key_out_of_argv(tmp_path: Path) -> None:
    service = AgentService(tmp_path, _service_config())
    try:
        task = TaskRecord(
            task_id="t-secret",
            session_id="s",
            message="hi",
            allow_changes=False,
            workspace_path=str(tmp_path),
        )
        # M3-T6: the config (incl. api_key) now travels over stdin, so the
        # command must never embed it in argv nor point at a plaintext file.
        command = service.tasks._worker_command(
            task,
            tmp_path,
            tmp_path / "tasks.sqlite3",
            tmp_path / "cancel.flag",
            True,
        )
        joined = " ".join(command)
        assert "api_key" not in joined
        assert "test-key" not in joined
        assert "--config-json" not in command
        assert "--config-file" not in command
        assert "--config-stdin" in command
    finally:
        service.shutdown()


def test_sweep_stale_worker_configs_removes_plaintext_residue(tmp_path: Path) -> None:
    """M3-T6: residue config.json files (with api_key) are swept before spawn."""
    service = AgentService(tmp_path, _service_config())
    try:
        worker_dir = tmp_path / ".minicc" / "worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        stale = worker_dir / "old-task.config.json"
        stale.write_text(json.dumps({"api_key": "leaked-secret"}), encoding="utf-8")
        keep = worker_dir / "task.request.json"
        keep.write_text("{}", encoding="utf-8")

        service.tasks._sweep_stale_worker_configs(tmp_path)

        assert not stale.exists()
        assert keep.exists()  # only *.config.json is swept
        assert not list(worker_dir.glob("*.config.json"))
    finally:
        service.shutdown()


def test_config_from_stdin_reads_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """M3-T6: the worker reconstructs its config from stdin (no disk file)."""
    import io

    from minicc.task_worker import _config_from_stdin

    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"api_key": "stdin-secret", "model": "m"}))
    )
    config = _config_from_stdin()
    assert config is not None
    assert config.api_key == "stdin-secret"
    assert config.model == "m"


def test_worker_config_file_is_deleted_after_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from minicc.task_worker import _config_from_file

    path = tmp_path / "worker.config.json"
    path.write_text(json.dumps({"api_key": "secret", "model": "m"}), encoding="utf-8")
    monkeypatch.delenv("MINICC_KEEP_WORKER_CONFIG", raising=False)
    config = _config_from_file(str(path))
    assert config.api_key == "secret"
    assert not path.exists()


def test_rewind_to_user_index_keeps_through_nth_user(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "rewind-users")
    store.save([
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "第一个问题"},
        {"role": "assistant", "content": "第一个回答"},
        {"role": "user", "content": "第二个问题"},
        {"role": "assistant", "content": "第二个回答"},
        {"role": "user", "content": "第三个问题"},
    ])
    result = store.rewind_to_user_index(2)
    assert result["user_index"] == 2
    assert result["kept"] == 4
    messages = store.load("system prompt")
    assert [item["content"] for item in messages if item["role"] != "system"] == [
        "第一个问题",
        "第一个回答",
        "第二个问题",
    ]
    with pytest.raises(SessionError, match="第 9 条"):
        store.rewind_to_user_index(9)


def test_rewind_http_accepts_user_index(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "rewind-http")
    store.save([
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "第一个问题"},
        {"role": "assistant", "content": "第一个回答"},
        {"role": "user", "content": "第二个问题"},
        {"role": "assistant", "content": "第二个回答"},
    ])
    service = AgentService(tmp_path, _service_config())
    server = MiniccHTTPServer(("127.0.0.1", 0), service, auth=WebAuth("t", required=False))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = urllib.request.Request(
            f"{url}/api/sessions/rewind",
            data=json.dumps({"session_id": "rewind-http", "user_index": 1}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["user_index"] == 1
        assert payload["kept"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        service.shutdown()


def test_cli_parser_exposes_allow_network() -> None:
    from minicc.main import _parser

    args = _parser().parse_args(["--allow-network", "hello"])
    assert args.allow_network is True
    assert args.prompt == ["hello"]


def test_cli_permission_gate_uses_authorize_tool(tmp_path: Path) -> None:
    from minicc.main import _permission_gate

    registry = build_registry(Editor(tmp_path))
    config = types.SimpleNamespace(yolo=False)
    denied = _permission_gate(config, registry, "default", allow_network=False)
    allowed = _permission_gate(config, registry, "default", allow_network=True)
    planned = _permission_gate(config, registry, "plan", allow_network=True)
    fetch = ToolCall(tool="webfetch", arguments={"url": "https://example.com"})
    write = ToolCall(tool="write_file", arguments={"path": "a.py", "content": "x\n"})
    assert denied("webfetch", fetch) is False
    assert allowed("webfetch", fetch) is True
    assert planned("write_file", write) is False


def test_game_bundle_stays_out_of_app_js() -> None:
    root = Path(__file__).resolve().parents[1]
    app = (root / "web" / "app.js").read_text(encoding="utf-8")
    game = (root / "web" / "game.js").read_text(encoding="utf-8")
    assert "window.__zombieProbe" not in app
    assert "window.__gameUpgradeProbe" not in app
    assert "window.__zombieProbe" in game
    assert "window.__gameUpgradeProbe" in game
    assert 'allowChanges: localStorage.getItem("minicc-allow") === "true"' in app
    assert 'allowChanges: localStorage.getItem("minicc-allow") !== "false"' not in app
    # `$` is querySelector (one node). NodeList loops must not use it or bindUI
    # throws before the workbench click handlers (timeline expand, rewind) attach.
    assert '$(".codex-tab").forEach' not in app
    assert '$(".action-chip").forEach' not in app
    assert "document.querySelectorAll(\".codex-tab\").forEach" in app
