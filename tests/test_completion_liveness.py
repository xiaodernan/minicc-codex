"""Completion-review liveness contracts found by real-API testing.

A read-only question ("what was the codename?") used to burn the whole turn
budget: when the reviewer's own JSON cited an evidence id that did not exist,
``_enforce_completion_evidence`` turned that into a *worker* instruction —
"给出执行证据中真实存在的 event-N 或 verification-N 编号". The worker cannot see
internal packet ids, so it went looking for files named ``event-*`` and ran
``git status`` in a non-git workspace until the budget was gone (observed live:
5 of 6 repair rounds carried that same sentence).

The split that matters: no citable evidence exists -> a real gap the worker can
close (keep asking, in words it can act on); citable evidence exists but the
reviewer mis-cited it -> an evaluator fault (``unknown``, which the caller
already retries once and then stops) instead of an uncloseable worker task.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from openai import APIConnectionError, AuthenticationError, BadRequestError

from minicc.agent.completion import (
    MAX_TRANSCRIPT_CHARS_PER_MESSAGE,
    CompletionDecision,
    _enforce_completion_evidence,
    _evidence_ref_ids,
    _transcript_items,
    build_completion_review_prompt,
    judge_completion,
    parse_completion_decision,
)
from minicc.llm.base import LLMResponse
from minicc.llm.openai_provider import classify_provider_failure
from minicc.task_manager import _completion_followup
from minicc.tools.schemas import ToolCall, ToolResult

TOOL_EVENTS = [
    {"kind": "trace", "name": "agent", "status": "ok", "phase": "planning", "summary": "先读文件"},
    {"kind": "tool", "name": "read_file", "status": "ok", "summary": "读取 CODEBOOK.md", "path": "CODEBOOK.md"},
]

WRITTEN_EVENTS = [
    {"kind": "tool", "name": "write_file", "status": "ok", "write": True, "path": "app.py"},
    {"kind": "tool", "name": "bash", "status": "ok", "command": "python -m pytest test_app.py"},
]


def _decision(evidence: list[str]) -> CompletionDecision:
    return CompletionDecision(
        status="complete",
        confidence=0.9,
        rationale="需求逐项核对完成",
        missing=[],
        next_action="",
        evidence=list(evidence),
    )


def test_citation_spelling_variants_resolve_to_one_packet_id() -> None:
    assert _evidence_ref_ids("event-12") == {"event-12"}
    assert _evidence_ref_ids(" #Event-12 ") == {"event-12"}
    assert _evidence_ref_ids("event 12") == {"event-12"}
    assert _evidence_ref_ids("verification-3") == {"verification-3"}
    # A bare number is ambiguous between the two id namespaces: offer both.
    assert _evidence_ref_ids("7") == {"event-7", "verification-7"}
    assert _evidence_ref_ids("event-1x") == {"event-1x"}


def test_misformatted_but_real_citation_still_certifies_completion() -> None:
    enforced = _enforce_completion_evidence(_decision(["#Event 2"]), WRITTEN_EVENTS, [])
    assert enforced.status == "complete", enforced.missing
    assert enforced.evidence == ["event-2"]


def test_hallucinated_citation_becomes_evaluator_fault_not_worker_task() -> None:
    enforced = _enforce_completion_evidence(_decision(["event-99"]), WRITTEN_EVENTS, [])
    assert enforced.status == "unknown"
    assert enforced.error == "完成评估没有引用可核对的执行证据"
    # The worker must never be told to go and produce internal packet ids.
    assert not any("event-" in text for text in enforced.missing)
    assert "event-" not in _completion_followup(enforced)


def test_empty_citation_with_real_evidence_is_also_evaluator_fault() -> None:
    enforced = _enforce_completion_evidence(_decision([]), TOOL_EVENTS, [])
    assert enforced.status == "unknown"
    assert enforced.evidence == []


def test_zero_tool_run_still_asks_the_worker_for_real_evidence() -> None:
    trace_only = [
        {"kind": "trace", "name": "agent", "status": "ok", "phase": "planning", "summary": "只读任务，直接给结论"}
    ]
    enforced = _enforce_completion_evidence(_decision(["event-1"]), trace_only, [])
    assert enforced.status == "continue", "a trace id must not certify completion"
    followup = _completion_followup(enforced)
    assert "event-" not in followup and "verification-" not in followup


def test_followup_text_drops_the_git_diff_nudge() -> None:
    # "重新检查 diff" made the model run git_status in non-git workspaces.
    decision = CompletionDecision(status="continue", missing=["补充一处测试"], next_action="运行 pytest")
    followup = _completion_followup(decision)
    assert "diff" not in followup
    assert "补充一处测试" in followup and "运行 pytest" in followup


RECALL_MESSAGES: list[dict[str, Any]] = [
    {"role": "system", "content": "system prompt"},
    {"role": "user", "content": "本次实验的基准编号是 KX91，稍后我会问你。"},
    {"role": "assistant", "content": "好的，已记下基准编号 KX91。"},
    {"role": "user", "content": "回看我们的对话：基准编号是什么？"},
]


def test_conversation_is_exposed_as_citable_evidence() -> None:
    items = _transcript_items(RECALL_MESSAGES)
    assert [item["id"] for item in items] == ["message-1", "message-2", "message-3"]
    assert {item["role"] for item in items} == {"user", "assistant"}
    prompt = build_completion_review_prompt(
        task="回看我们的对话：基准编号是什么？",
        answer="基准编号是 KX91",
        events=[],
        verification_results=[],
        allow_changes=False,
        workspace="ws",
        messages=RECALL_MESSAGES,
    )
    assert "conversation" in prompt and "message-1" in prompt


def test_recall_answer_needs_no_tool_evidence() -> None:
    # The reviewer used to demand "a tool that can read the chat history", which
    # no tool is: the transcript itself is the evidence.
    trace_only = [{"kind": "trace", "name": "agent", "status": "ok", "summary": "直接回看对话"}]
    enforced = _enforce_completion_evidence(_decision(["message-1"]), trace_only, [], RECALL_MESSAGES)
    assert enforced.status == "complete", enforced.missing


def test_conversation_citation_cannot_certify_an_unverified_write() -> None:
    events = [{"kind": "tool", "name": "write_file", "status": "ok", "write": True, "path": "app.py"}]
    enforced = _enforce_completion_evidence(_decision(["message-1"]), events, [], RECALL_MESSAGES)
    assert enforced.status == "continue", "citing the chat must not replace a real check"


def test_hallucinated_message_id_is_still_rejected() -> None:
    enforced = _enforce_completion_evidence(_decision(["message-77"]), [], [], RECALL_MESSAGES)
    assert enforced.status == "unknown"


def test_transcript_is_redacted_and_bounded() -> None:
    messages = [
        {"role": "user", "content": "key sk-abcdefgh12345678 " + "x" * 4000} for _ in range(40)
    ]
    items = _transcript_items(messages)
    assert 0 < len(items) < len(messages)
    assert all(len(item["content"]) <= MAX_TRANSCRIPT_CHARS_PER_MESSAGE for item in items)
    prompt = build_completion_review_prompt(
        task="t",
        answer="a",
        events=[],
        verification_results=[],
        allow_changes=False,
        workspace="ws",
        messages=messages,
    )
    assert "sk-abcdefgh12345678" not in prompt
    assert "REDACTED" in prompt


# --- reviewer JSON dialect: null means "none", not "broken" -----------------
# Observed live (M8-T3 real-API E2E): the reviewer returned a correctly cited
# complete verdict with ``"next_action": null``; the strict type check threw
# that verdict away as ``unknown`` and the task only converged because the
# caller happened to retry once. Non-string, non-null types stay faults.

def _complete_payload(**overrides: Any) -> str:
    base: dict[str, Any] = {
        "status": "complete",
        "confidence": 0.95,
        "rationale": "已核对 url_head 的工具结果",
        "missing": [],
        "next_action": "",
        "evidence": ["event-2"],
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


@pytest.mark.parametrize(
    "overrides",
    [{"next_action": None}, {"missing": None}, {"next_action": None, "missing": None}],
)
def test_null_optional_reviewer_fields_still_certify_completion(overrides: dict) -> None:
    decision = parse_completion_decision(_complete_payload(**overrides))
    assert decision.status == "complete", decision.error
    assert decision.next_action == ""
    assert decision.missing == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"next_action": ["做这个"]},
        {"next_action": 7},
        {"missing": "缺少验证"},
        {"missing": [None]},
        {"rationale": None},
    ],
)
def test_structurally_wrong_reviewer_fields_stay_evaluator_faults(overrides: dict) -> None:
    assert parse_completion_decision(_complete_payload(**overrides)).status == "unknown"


class _ScriptedJudge:
    """Stand in for the provider so the real reviewer parsing/enforcement run."""

    def __init__(self, payloads: list[str]) -> None:
        self.payloads = payloads
        self.calls = 0

    async def __call__(self, provider: Any, **kwargs: Any) -> LLMResponse:
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return LLMResponse(content=payload, usage={"prompt_tokens": 10, "completion_tokens": 20})


def _review_json(evidence: list[str]) -> str:
    return json.dumps(
        {
            "status": "complete",
            "confidence": 0.9,
            "rationale": "已核对",
            "missing": [],
            "next_action": "",
            "evidence": evidence,
        }
    )


@pytest.mark.asyncio
async def test_judge_repairs_spelling_of_a_real_id() -> None:
    from minicc.agent import completion as completion_module

    scripted = _ScriptedJudge([_review_json(["#Event 2"])])
    original = completion_module.chat_with_cancellation
    completion_module.chat_with_cancellation = scripted  # type: ignore[assignment]
    try:
        decision = await judge_completion(
            provider=None,
            task="读一下代号",
            answer="代号是 HARBORLAMP-13",
            events=list(TOOL_EVENTS),
            verification_results=[],
            allow_changes=False,
            workspace="ws",
        )
    finally:
        completion_module.chat_with_cancellation = original  # type: ignore[assignment]
    assert decision.status == "complete"
    assert decision.evidence == ["event-2"]


def _service_config() -> Any:
    from minicc.config import Config

    return Config(base_url="https://example.invalid/v1", api_key="test", model="test", sandbox_mode="host")


def test_hallucinating_reviewer_terminates_without_burning_the_budget(tmp_path: Path, monkeypatch) -> None:
    """End-to-end guard: the run must stop in a couple of reviews, not 8 turns."""
    import minicc.web as web_module
    from minicc.agent.loop import TurnResult
    from minicc.task_store import TaskStore

    (tmp_path / "CODEBOOK.md").write_text("代号：HARBORLAMP-13\n", encoding="utf-8")
    loops: list[list[dict[str, Any]]] = []

    async def run(provider: Any, registry: Any, messages: list[dict[str, Any]], **kwargs: Any) -> TurnResult:
        loops.append(list(messages))
        kwargs["on_tool"](
            ToolCall("read_file", {"path": "CODEBOOK.md"}),
            ToolResult(status="ok", summary="读取 CODEBOOK.md", output="代号：HARBORLAMP-13"),
        )
        return TurnResult(answer="代号是 HARBORLAMP-13")

    class Provider:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def close(self) -> None:
            return None

    monkeypatch.setattr(web_module, "run_agent", run)
    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", Provider)
    from minicc.agent import completion as completion_module

    scripted = _ScriptedJudge([_review_json(["event-999"])] * 6)
    monkeypatch.setattr(completion_module, "chat_with_cancellation", scripted)

    service = web_module.AgentService(tmp_path, _service_config(), task_store=TaskStore(tmp_path / "t.sqlite3"))
    try:
        result = service._chat_locked({"message": "CODEBOOK.md 里的代号是什么？", "allow_changes": False}, workspace=tmp_path)
    finally:
        service.shutdown()

    assert scripted.calls <= 3, f"reviewer was asked {scripted.calls} times; loop did not converge"
    assert result["error"], "an unverifiable completion must not be reported as success"
    assert "完成评估" in str(result["error"])
    leaked = [
        str(message.get("content"))
        for message in loops[-1]
        if message.get("role") == "user" and ("event-" in str(message.get("content")))
    ]
    assert not leaked, f"internal evidence ids leaked to the worker: {leaked}"


# --- a rejected review must not cost a second full agent run ----------------
# Observed live (M8-T5 real-API run): the reviewer *request* failed, the caller
# could not tell "the provider refused this text" from "the provider is briefly
# unavailable", and sent the agent off to redo all its work before asking
# again. A deterministic rejection gives the identical answer, so that extra
# run is pure cost; only a transient failure earns the bounded self-check.

def _http_error(cls, message: str):
    import httpx

    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    try:
        return cls(message, body=None, response=httpx.Response(400, request=request))
    except TypeError:  # connection/timeout errors take no response
        return cls(message=message, request=request)


@pytest.mark.parametrize(
    "error,expected",
    [
        (_http_error(BadRequestError, "Error code: 400 - content policy blocked"), False),
        (_http_error(AuthenticationError, "Error code: 401 - invalid api key"), False),
        (_http_error(APIConnectionError, "Connection error."), True),
        (RuntimeError("Anthropic HTTP 451: unavailable"), None),
        (ValueError("boom while building the packet"), None),
    ],
)
def test_only_provider_errors_get_a_retry_verdict(error: BaseException, expected: bool | None) -> None:
    assert classify_provider_failure(error) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,expected",
    [
        (_http_error(BadRequestError, "Error code: 400 - content policy blocked"), False),
        (_http_error(APIConnectionError, "Connection error."), True),
        (RuntimeError("boom"), None),
    ],
)
async def test_reviewer_failure_reports_whether_a_retry_can_help(
    error: BaseException, expected: bool | None
) -> None:
    from minicc.agent import completion as completion_module

    async def failing(provider: Any, **kwargs: Any) -> LLMResponse:
        raise error

    original = completion_module.chat_with_cancellation
    completion_module.chat_with_cancellation = failing  # type: ignore[assignment]
    try:
        decision = await judge_completion(
            provider=None,
            task="读一下代号",
            answer="代号是 HARBORLAMP-13",
            events=list(TOOL_EVENTS),
            verification_results=[],
            allow_changes=False,
            workspace="ws",
        )
    finally:
        completion_module.chat_with_cancellation = original  # type: ignore[assignment]
    assert decision.status == "unknown"
    assert decision.review_transient is expected
    # The verdict is control flow for the caller, not a user-facing field.
    assert "review_transient" not in decision.to_dict()


class _RaisingJudge:
    """A reviewer whose call raises, standing in for a provider failure."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    async def __call__(self, provider: Any, **kwargs: Any) -> LLMResponse:
        self.calls += 1
        raise self.error


def _run_service_with_reviewer(tmp_path: Path, monkeypatch, judge: Any) -> tuple[dict[str, Any], int]:
    """Run one read-only task whose reviewer call is driven by ``judge``.

    Returns the service result plus how many times the agent loop itself ran,
    which is what the whole distinction is about.
    """
    import minicc.web as web_module
    from minicc.agent.loop import TurnResult
    from minicc.task_store import TaskStore

    (tmp_path / "CODEBOOK.md").write_text("代号：HARBORLAMP-13\n", encoding="utf-8")
    agent_runs: list[int] = []

    async def run(provider: Any, registry: Any, messages: list[dict[str, Any]], **kwargs: Any) -> TurnResult:
        agent_runs.append(len(messages))
        kwargs["on_tool"](
            ToolCall("read_file", {"path": "CODEBOOK.md"}),
            ToolResult(status="ok", summary="读取 CODEBOOK.md", output="代号：HARBORLAMP-13"),
        )
        return TurnResult(answer="代号是 HARBORLAMP-13")

    class Provider:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def close(self) -> None:
            return None

    monkeypatch.setattr(web_module, "run_agent", run)
    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", Provider)
    from minicc.agent import completion as completion_module

    monkeypatch.setattr(completion_module, "chat_with_cancellation", judge)
    service = web_module.AgentService(tmp_path, _service_config(), task_store=TaskStore(tmp_path / "t.sqlite3"))
    try:
        result = service._chat_locked(
            {"message": "CODEBOOK.md 里的代号是什么？", "allow_changes": False}, workspace=tmp_path
        )
    finally:
        service.shutdown()
    return result, len(agent_runs)


def test_deterministically_rejected_review_stops_without_a_second_run(
    tmp_path: Path, monkeypatch
) -> None:
    judge = _RaisingJudge(_http_error(BadRequestError, "Error code: 400 - content policy blocked"))
    result, runs = _run_service_with_reviewer(tmp_path, monkeypatch, judge)

    assert runs == 1, "a rejection the agent cannot change must not re-run it"
    assert judge.calls == 1
    assert "完成评估请求被模型端拒绝" in str(result["error"])
    codes = [event.get("code") for event in result["events"] if isinstance(event, dict)]
    assert "completion_judge_rejected" in codes
    assert "completion_judge_retry" not in codes
    assert result["completion"]["status"] == "unknown"


def test_transient_reviewer_failure_keeps_the_bounded_self_check(
    tmp_path: Path, monkeypatch
) -> None:
    judge = _RaisingJudge(_http_error(APIConnectionError, "Connection error."))
    result, runs = _run_service_with_reviewer(tmp_path, monkeypatch, judge)

    # Transient is different: asking again can succeed, so the agent gets its
    # one extra self-check round - exactly one, still bounded.
    assert runs == 2
    assert judge.calls == 2
    codes = [event.get("code") for event in result["events"] if isinstance(event, dict)]
    assert "completion_judge_retry" in codes
    assert "completion_judge_rejected" not in codes
    assert "完成评估" in str(result["error"])
