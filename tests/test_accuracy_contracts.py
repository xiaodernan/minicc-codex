"""Regression cases for retrieval coverage, tool protocol and completion evidence."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from minicc.agent.completion import MAX_EVIDENCE_CHARS, _evidence_packet, judge_completion, parse_completion_decision
from minicc.agent.context import compact_with_checkpoint, repair_interrupted_tool_rounds, validate_tool_protocol
from minicc.agent.loop import chat_with_cancellation
from minicc.agent.tool_policy import is_verification_evidence
import pytest
from minicc.agent.retrieval import LocalEvidenceIndex, get_evidence_index
from minicc.llm.base import LLMResponse


def test_later_failed_or_cancelled_check_prevents_complete():
    from minicc.agent.completion import CompletionDecision, _enforce_completion_evidence
    events = [
        {"kind": "tool", "name": "write_file", "path": "app.py", "write": True, "status": "ok"},
        {"kind": "tool", "name": "bash", "command": "python -m pytest test_app.py", "status": "ok"},
        {"kind": "tool", "name": "bash", "command": "python -m pytest test_app.py", "status": "error"},
    ]
    def decision(): return CompletionDecision(status="complete", rationale="checked", evidence=["event-2"])
    assert _enforce_completion_evidence(decision(), events, []).status == "continue"
    events.append({"kind": "tool", "name": "bash", "command": "python -m pytest test_app.py", "status": "ok"})
    assert _enforce_completion_evidence(decision(), events, []).status == "complete"
    assert _enforce_completion_evidence(decision(), events, [{"status": "cancelled"}]).status == "continue"


def test_retrieval_prunes_caches_before_budget_and_never_returns_unrelated_files(tmp_path: Path) -> None:
    cache = tmp_path / ".playwright-cli"
    cache.mkdir()
    for number in range(4100):
        (cache / f"snapshot-{number}.json").write_text("run_agent", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.py").write_text("def run_agent():\n    return 1\n", encoding="utf-8")
    (tmp_path / "other.md").write_text("unrelated", encoding="utf-8")
    index = LocalEvidenceIndex(tmp_path, max_files=5)
    assert index.stats()["files_indexed"] == 2
    assert [hit.path for hit in index.search("run_agent")] == ["src/agent.py"]
    assert index.search("no_such_symbol") == []


def test_retrieval_incrementally_refreshes_creates_edits_deletes(tmp_path: Path) -> None:
    path = tmp_path / "app.py"
    path.write_text("def before(): pass\n", encoding="utf-8")
    index = get_evidence_index(tmp_path)
    assert index.search("before")
    assert get_evidence_index(tmp_path) is index
    path.write_text("def after_edit(): pass\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("def another(): pass\n", encoding="utf-8")
    assert index.refresh()["files_rebuilt"] == 2
    assert not index.search("before")
    assert index.search("after_edit")[0].path == "app.py"
    assert index.refresh()["files_rebuilt"] == 0
    path.unlink()
    index.refresh()
    assert not index.search("after_edit")


def test_retrieval_prioritizes_late_symbol_definition_over_mentions(tmp_path: Path) -> None:
    (tmp_path / "mentions.py").write_text("# needle_handler failed as an example\n", encoding="utf-8")
    (tmp_path / "implementation.py").write_text("\n".join(f"def helper_{number}(): pass" for number in range(30)) + "\ndef needle_handler(): pass\n", encoding="utf-8")
    hits = LocalEvidenceIndex(tmp_path).search("needle_handler")
    assert hits[0].path == "implementation.py"
    assert "needle_handler" in hits[0].symbols
    assert hits[1].test_failures == ()


def test_compaction_retains_whole_parallel_tool_round() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "original " * 100},
        {"role": "assistant", "tool_calls": [
            {"id": "read1", "function": {"name": "read_file", "arguments": "{}"}},
            {"id": "read2", "function": {"name": "read_file", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "read1", "content": "one"},
        {"role": "tool", "tool_call_id": "read2", "content": "two"},
        {"role": "assistant", "content": "done"},
    ]
    compacted, checkpoint = compact_with_checkpoint(messages, threshold=100, keep_recent=2)
    assert checkpoint is not None
    ids = {call["id"] for message in compacted for call in message.get("tool_calls", [])}
    assert ids == {"read1", "read2"}
    assert {message.get("tool_call_id") for message in compacted if message.get("role") == "tool"} == ids


def test_compaction_keeps_original_and_latest_user_corrections_across_rounds() -> None:
    messages = [{"role": "user", "content": f"必须 requirement-{number} " + "x" * 100} for number in range(18)]
    compacted, checkpoint = compact_with_checkpoint(messages, threshold=100, keep_recent=1)
    assert checkpoint is not None
    assert "requirement-0 " in checkpoint["objectives"][0]
    assert "requirement-16 " in checkpoint["objectives"][-1]
    assert any("requirement-16 " in requirement for requirement in checkpoint["requirements"])
    compacted.append({"role": "user", "content": "必须 latest correction " + "y" * 100})
    _, second = compact_with_checkpoint(compacted, threshold=100, keep_recent=1)
    assert second is not None
    assert "requirement-0 " in second["objectives"][0]
    assert "requirement-17 " in second["objectives"][-1]


def test_completion_refuses_empty_or_contradictory_complete_decisions() -> None:
    assert parse_completion_decision('{"status":"complete"}').status == "unknown"
    decision = parse_completion_decision(json.dumps({"status": "complete", "confidence": 1, "rationale": "done", "missing": ["mobile validation"], "next_action": "", "evidence": ["event-1"]}))
    assert decision.status == "continue"
    assert decision.next_action == "mobile validation"


def test_evidence_packet_is_bounded_valid_json_and_keeps_important_early_writes() -> None:
    events = [{"kind": "tool", "name": "write_file", "path": "src/app.py", "write": True, "status": "ok", "output": "written"}]
    events.extend({"kind": "trace", "status": "ok", "summary": "noise", "output": "x" * 5000, "detail": {"nested": ["y" * 5000] * 30}} for _ in range(100))
    raw = _evidence_packet(events, [{"status": "passed", "command": "pytest tests/test_app.py", "output": "passed"}])
    assert len(raw) <= MAX_EVIDENCE_CHARS
    packet = json.loads(raw)
    assert any(item.get("path") == "src/app.py" for item in packet["events"])
    assert packet["verification_results"][0]["status"] == "passed"


def test_model_complete_cannot_override_failed_verification() -> None:
    class Provider:
        async def chat(self, **kwargs):
            return LLMResponse(content=json.dumps({"status": "complete", "confidence": 1, "rationale": "done", "missing": [], "next_action": "", "evidence": ["verification-1"]}))

    decision = asyncio.run(judge_completion(Provider(), task="fix parser", answer="done", events=[], verification_results=[{"status": "failed"}], allow_changes=True, workspace="workspace"))
    assert decision.status == "continue"
    assert decision.missing


def test_protocol_guard_rejects_orphaned_incomplete_and_duplicate_results_before_network() -> None:
    class Provider:
        async def chat(self, **kwargs):
            pytest.fail("invalid history reached the provider")

    call = {"role": "assistant", "tool_calls": [{"id": "one"}, {"id": "two"}]}
    one = {"role": "tool", "tool_call_id": "one", "content": "ok"}
    two = {"role": "tool", "tool_call_id": "two", "content": "ok"}
    for messages in ([one], [call, one], [call, one, one], [call, one, {"role": "user", "content": "continue"}, two]):
        with pytest.raises(ValueError, match="工具上下文协议无效"):
            asyncio.run(chat_with_cancellation(Provider(), messages=messages, tools=None, on_delta=None, cancel_event=None))
    validate_tool_protocol([call, two, one, {"role": "user", "content": "continue"}])


def test_interrupted_parallel_history_keeps_success_and_marks_only_unknown_results() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "write-one"}, {"id": "write-two"}]},
        {"role": "tool", "tool_call_id": "write-one", "content": "written"},
        {"role": "user", "content": "continue"},
    ]
    assert repair_interrupted_tool_rounds(messages) == 1
    validate_tool_protocol(messages)
    assert messages[1]["content"] == "written"
    assert messages[2]["tool_call_id"] == "write-two"
    assert "INTERRUPTED_TOOL_RESULT" in messages[2]["content"]
    assert repair_interrupted_tool_rounds(messages) == 0


@pytest.mark.parametrize("command", ["echo pytest", "python -m pytest --collect-only", "pytest --co", "npm test --help", "node --check app.js && echo done", "python -c 'print(\"pytest\")'"])
def test_nonexecuted_checks_do_not_count_as_verification(command: str) -> None:
    assert not is_verification_evidence("bash", {"command": command}, "ok")


def _complete(events, verifications=None, evidence=None):
    class Provider:
        async def chat(self, **kwargs):
            return LLMResponse(content=json.dumps({"status": "complete", "confidence": 1, "rationale": "done", "missing": [], "next_action": "", "evidence": evidence or ["event-1"]}))
    return asyncio.run(judge_completion(Provider(), task="fix app", answer="done", events=events, verification_results=verifications or [], allow_changes=True, workspace="workspace"))


def test_completion_requires_real_evidence_and_check_after_latest_code_write() -> None:
    write = {"name": "write_file", "path": "app.py", "write": True, "status": "ok"}
    read = {"name": "read_file", "path": "app.py", "status": "ok"}
    check = {"name": "bash", "command": "python -m pytest tests/test_app.py", "status": "ok"}
    assert _complete([write, check], evidence=["event-999"]).status == "continue"
    assert _complete([write, read]).status == "continue"
    assert _complete([check, write], [{"status": "passed"}]).status == "continue"
    assert _complete([write, check]).status == "complete"
    assert _complete([write, check], [{"status": "failed"}, {"status": "skipped"}]).status == "continue"


@pytest.mark.parametrize("confidence", [True, "100%", float("nan"), float("inf")])
def test_completion_rejects_invalid_confidence(confidence) -> None:
    assert parse_completion_decision(json.dumps({"status": "complete", "confidence": confidence, "rationale": "done", "missing": [], "next_action": "", "evidence": ["event-1"]})).status == "unknown"


@pytest.mark.parametrize("path", ["package.json", "pyproject.toml", "Dockerfile", ".env", "src/app.kt", "setup.cfg", "requirements.txt", "CMakeLists.txt"])
def test_runtime_configuration_and_unlisted_source_need_execution(path):
    events = [{"name": "write_file", "path": path, "write": True, "status": "ok"}, {"name": "read_file", "path": path, "status": "ok"}]
    assert _complete(events).status == "continue"


def test_unrelated_verification_pass_does_not_hide_a_failed_check():
    events = [{"name": "read_file", "path": "app.py", "status": "ok"}]
    checks = [{"command": "pytest test_a.py", "status": "failed"}, {"command": "pytest test_b.py", "status": "passed"}]
    assert _complete(events, checks).status == "continue"
    assert _complete(events, checks + [{"command": "pytest test_a.py", "status": "passed"}]).status == "complete"


def test_malformed_verification_detail_does_not_crash_review():
    events = [{"name": "write_file", "path": "app.py", "write": True, "status": "ok"}, {"kind": "verification", "status": "ok", "detail": "invalid"}]
    assert _complete(events).status == "continue"
