"""Permission mode tests: normalize, authorize_tool modes, task submit wiring."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from minicc.audit import authorize_tool, normalize_permission_mode
from minicc.web import AgentService, _resolve_task_permissions
from minicc.webauth import WebAuth


# ---------------------------------------------------------------------------
# normalize_permission_mode
# ---------------------------------------------------------------------------


def test_normalize_permission_mode_aliases_and_errors() -> None:
    assert normalize_permission_mode(None) == "default"
    assert normalize_permission_mode("") == "default"
    assert normalize_permission_mode("normal") == "default"
    assert normalize_permission_mode("PLAN") == "plan"
    assert normalize_permission_mode("acceptEdits") == "acceptEdits"
    assert normalize_permission_mode("yolo") == "yolo"
    with pytest.raises(ValueError, match="permission_mode"):
        normalize_permission_mode("danger")


# ---------------------------------------------------------------------------
# authorize_tool mode semantics
# ---------------------------------------------------------------------------


def test_plan_mode_denies_write_and_exec_but_allows_readonly() -> None:
    write = authorize_tool(
        "write_file", "write", {}, allow_changes=True, allow_network=True, permission_mode="plan"
    )
    assert write.allowed is False
    assert write.authorization == "plan_mode_write"
    run = authorize_tool(
        "bash", "exec", {"command": "python -m pytest -q"}, allow_changes=True, allow_network=True, permission_mode="plan"
    )
    assert run.allowed is False
    read = authorize_tool(
        "read_file", "readonly", {}, allow_changes=False, allow_network=False, permission_mode="plan"
    )
    assert read.allowed is True


def test_plan_mode_still_allows_authorized_network_research() -> None:
    search = authorize_tool(
        "web_search", "readonly", {}, allow_changes=False, allow_network=True, permission_mode="plan"
    )
    assert search.allowed is True
    denied = authorize_tool(
        "web_search", "readonly", {}, allow_changes=False, allow_network=False, permission_mode="plan"
    )
    assert denied.allowed is False


def test_accept_edits_auto_allows_writes_but_not_exec() -> None:
    write = authorize_tool(
        "write_file", "write", {}, allow_changes=False, allow_network=False, permission_mode="acceptEdits"
    )
    assert write.allowed is True
    # Non-whitelisted exec still requires explicit write authorization, even
    # in acceptEdits; the read-only pytest whitelist stays available because
    # it is verification, not mutation.
    run = authorize_tool(
        "bash", "exec", {"command": "node scripts/build.js"}, allow_changes=False, allow_network=False, permission_mode="acceptEdits"
    )
    assert run.allowed is False
    safe_run = authorize_tool(
        "bash", "exec", {"command": "python -m pytest -q"}, allow_changes=False, allow_network=False, permission_mode="acceptEdits"
    )
    assert safe_run.allowed is True
    other_exec = authorize_tool(
        "bash", "exec", {"command": "node scripts/build.js"}, allow_changes=True, allow_network=False, permission_mode="acceptEdits"
    )
    assert other_exec.allowed is True


def test_yolo_mode_allows_everything() -> None:
    for tool, risk, args in (
        ("write_file", "write", {}),
        ("bash", "exec", {"command": "curl https://example.test"}),
        ("web_search", "readonly", {"query": "x"}),
    ):
        decision = authorize_tool(tool, risk, args, allow_changes=False, allow_network=False, permission_mode="yolo")
        assert decision.allowed is True
        assert decision.authorization == "task_yolo"


def test_default_mode_backward_compatible() -> None:
    assert authorize_tool("write_file", "write", {}, allow_changes=False, allow_network=False).allowed is False
    assert authorize_tool("write_file", "write", {}, allow_changes=True, allow_network=False).allowed is True
    assert authorize_tool("bash", "exec", {"command": "python -m pytest -q"}, allow_changes=False, allow_network=False).allowed is True


# ---------------------------------------------------------------------------
# task submit wiring
# ---------------------------------------------------------------------------


def _service(tmp_path: Path) -> AgentService:
    config = types.SimpleNamespace(
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
    return AgentService(tmp_path, config)


def test_resolve_task_permissions_modes(tmp_path: Path) -> None:
    changes, network, mode = _resolve_task_permissions({"allow_changes": True}, yolo=False)
    assert (changes, network, mode) == (True, False, "default")

    changes, network, mode = _resolve_task_permissions({"permission_mode": "yolo"}, yolo=False)
    assert (changes, network, mode) == (True, True, "yolo")

    changes, network, mode = _resolve_task_permissions(
        {"permission_mode": "plan", "allow_changes": True}, yolo=False
    )
    # plan keeps the raw flag; authorize_tool combines mode + flags, so the
    # raw flag staying True is safe (write is still denied by mode).
    assert (changes, network, mode) == (True, False, "plan")

    with pytest.raises(ValueError, match="permission_mode"):
        _resolve_task_permissions({"permission_mode": "chaos"}, yolo=False)


def test_snapshot_round_trip_preserves_permission_mode(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        submitted = service.tasks.submit(
            {"message": "只做规划", "permission_mode": "plan", "allow_changes": True}
        )
        task_id = submitted["task_id"]
        snapshot = service.tasks.get(task_id)
        assert snapshot["permission_mode"] == "plan"
        assert snapshot["allow_changes"] is True  # raw flag preserved

        submitted_yolo = service.tasks.submit(
            {"message": "全自动", "permission_mode": "yolo"}
        )
        yolo_snapshot = service.tasks.get(submitted_yolo["task_id"])
        assert yolo_snapshot["permission_mode"] == "yolo"
        assert yolo_snapshot["allow_changes"] is True
        assert yolo_snapshot["allow_network"] is True
    finally:
        service.shutdown()


def test_submit_rejects_invalid_permission_mode(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        with pytest.raises(ValueError, match="permission_mode"):
            service.tasks.submit({"message": "x", "permission_mode": "chaos"})
    finally:
        service.shutdown()


def test_plan_mode_injects_system_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan mode tells the model up front that writes are unavailable."""
    import copy

    from minicc.llm.base import LLMResponse
    from minicc.web import AgentService as _AS

    seen_requests: list[list[dict]] = []

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            seen_requests.append(copy.deepcopy(messages))
            return LLMResponse(content="计划模式调研结论。")

        async def close(self):
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    service = _service(tmp_path)
    try:
        service._chat_locked(
            {"message": "调研并输出计划", "permission_mode": "plan", "workspace_path": str(tmp_path)},
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    first_request = seen_requests[0]
    assert any(
        "计划模式" in str(message.get("content") or "") for message in first_request
    )
