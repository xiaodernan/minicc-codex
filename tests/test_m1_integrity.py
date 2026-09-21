"""M1 integrity tests: stream_merge, tool_call ids, finish_reason, envelope."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.llm.envelope import _render_envelope_action, parse_envelope
from minicc.llm.openai_provider import (
    StreamProtocolError,
    _is_stream_retryable,
    _unique_tool_call_id,
)
from minicc.llm.stream_merge import (
    accumulate_attempt_text,
    append_delta,
    merge_retry_snapshot,
)
from minicc.tools import build_registry
from minicc.tools.editor import Editor

def test_m1t1_recovery_required_does_not_loop_on_plain_text(tmp_path: Path) -> None:
    class PlainTextProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            return LLMResponse(content="还在思考，请稍候。")

    traces: list[dict] = []
    provider = PlainTextProvider()
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "做点事"}],
            on_trace=traces.append,
            should_allow=lambda _n, _c: True,
            require_recovery_inspection=True,
        )
    )
    assert provider.calls <= 5, provider.calls
    assert result.error and "恢复" in result.error
    assert any(e.get("code") == "recovery_required_before_finish" for e in traces)
    assert any(e.get("code") == "recovery_guard" for e in traces)


def test_m1t2_tool_call_ids_deduplicated() -> None:
    seen: set[str] = set()
    first = _unique_tool_call_id("", "call-0", seen)
    second = _unique_tool_call_id("", "call-0", seen)
    third = _unique_tool_call_id("dup", "call-1", seen)
    fourth = _unique_tool_call_id("dup", "call-1", seen)
    assert len({first, second, third, fourth}) == 4
    assert first == "call-0"


def test_m1t3_incremental_deltas_concatenated_byte_for_byte() -> None:
    attempt = ""
    for frag in ["line one\n", "\nline two\n", "    indented\n"]:
        attempt, _ = accumulate_attempt_text(attempt, frag)
    assert attempt == "line one\n\nline two\n    indented\n"
    attempt2 = ""
    for frag in ['{"command":"echo hi', 'hi"}']:
        attempt2, _ = accumulate_attempt_text(attempt2, frag)
    assert json.loads(attempt2)["command"] == "echo hihi"
    merged, suffix = accumulate_attempt_text("aa", "aab")
    assert (merged, suffix) == ("aab", "b")
    assert append_delta("hel", "lo") == ("hello", "lo")
    assert merge_retry_snapshot("aa", "aab") == ("aab", "b")
def test_m1t4_nonterminal_finish_reason_never_accepted(tmp_path: Path) -> None:
    class FailedProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(content=None, finish_reason="failed")
            return LLMResponse(content="恢复后完成。", finish_reason="stop")

    traces: list[dict] = []
    result = asyncio.run(
        run_agent(
            FailedProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "做点事"}],
            on_trace=traces.append,
            should_allow=lambda _n, _c: True,
        )
    )
    assert result.error is None
    assert result.answer == "恢复后完成。"
    assert any(e.get("code") == "nonterminal_turn" for e in traces)


def test_m1t4_persistent_nonterminal_fails(tmp_path: Path) -> None:
    class AlwaysLength:
        async def chat(self, messages, tools, on_delta=None):
            return LLMResponse(content="截断", finish_reason="length")

    result = asyncio.run(
        run_agent(
            AlwaysLength(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "做点事"}],
            should_allow=lambda _n, _c: True,
        )
    )
    assert result.error and "length" in result.error


def test_m1t5_stream_without_finish_reason_fails_fast() -> None:
    assert _is_stream_retryable(StreamProtocolError("x")) is False

    class FakeStream:
        def __init__(self, chunks) -> None:
            self.chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def aclose(self) -> None:
            return None

    from minicc.llm.openai_provider import OpenAICompatibleProvider

    chunks = [
        SimpleNamespace(
            model="m", usage=None,
            choices=[SimpleNamespace(
                finish_reason=None,
                delta=SimpleNamespace(content="hi", reasoning_content=None, tool_calls=[]),
            )],
        )
    ]
    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "k", "m",
        protocol="chat_completions", max_retries=4, sdk_client=object(),
    )
    calls = {"n": 0}

    async def fake_create(_kwargs) -> FakeStream:
        calls["n"] += 1
        return FakeStream(chunks)

    provider._create = fake_create  # type: ignore[method-assign]
    try:
        asyncio.run(provider.chat([{"role": "user", "content": "t"}], on_delta=lambda _s: None))
    except StreamProtocolError:
        pass
    else:
        raise AssertionError("expected StreamProtocolError")
    assert calls["n"] == 1


def test_m1t6_and_t7_envelope_roundtrip() -> None:
    first = parse_envelope('{"action": "read_file", "params": {"path": "a.py"}}')
    second = parse_envelope('{"action": "read_file", "params": {"path": "b.py"}}')
    assert first is not None and second is not None
    assert first["id"] != second["id"]
    rendered = _render_envelope_action(first)
    assert json.loads(rendered)["action"] == "read_file"


def test_m2t5_pytest_readonly_gate_denies_dangerous_forms() -> None:
    from minicc.tools.bash import is_readonly_command as readonly

    # Legitimate verification commands must stay allowed.
    assert readonly("pytest -q -p no:cacheprovider") is True
    assert readonly("python -m pytest tests/test_core.py") is True
    assert readonly("pytest -q") is True
    # M2-T5: loader/config/absolute-path forms must be denied.
    assert readonly("pytest -p json") is False
    assert readonly("pytest -c C:/evil/pytest.ini") is False
    assert readonly("pytest C:/other/repo/tests") is False
    assert readonly("pytest --rootdir=/etc") is False
    assert readonly("pytest -q ../outside") is False
    assert readonly("pytest -q && rm -rf /") is False


def test_m2t2_minicc_auth_files_are_not_agent_writable(tmp_path: Path) -> None:
    from minicc.tools.fs import FsTools
    from minicc.tools.registry import ToolError

    tools = FsTools(Editor(tmp_path))
    for path in (".minicc/allowlist.json", ".minicc/web_token.json", ".minicc/worker/w1.config.json"):
        try:
            tools.write_file({"path": path, "content": "{}\n"})
        except ToolError:
            pass
        else:
            raise AssertionError(f"write_file must reject {path}")
        try:
            tools.read_file({"path": path})
        except ToolError:
            pass
        else:
            raise AssertionError(f"read_file must reject {path}")


def test_m2t4_allowlist_redacts_and_matches_redacted_command(tmp_path: Path) -> None:
    from minicc.allowlist import add_session_rule, match_session_allowlist, session_rules

    add_session_rule(tmp_path, "s1", command="echo sk-abcdefgh12345678")
    rules = session_rules(tmp_path, "s1")
    assert rules["commands"], "rule must be persisted"
    stored = rules["commands"][0]
    assert "sk-abcdefgh12345678" not in stored
    assert "[REDACTED" in stored
    # The redacted runtime form must match the persisted redacted rule.
    assert match_session_allowlist(tmp_path, "s1", "bash", {"command": "echo sk-abcdefgh12345678"}) is True


