"""The batch merge path was broken in the product and 982 tests did not see it.

``task_manager._watch_batch`` calls ``service.merge_batch(..., model=parent.model)``
— a task must merge with the model the user picked for it — but
``AgentService.merge_batch`` never accepted ``model``, so *every* parallel batch
whose children all succeeded died at the merge step with
``批任务 watcher 失败: TypeError: merge_batch() got an unexpected keyword argument 'model'``.

The two halves were each tested against a stand-in that does not resemble the
other:

* the batch tests run with a fake service that has **no** ``merge_batch``, so
  the ``hasattr`` guard quietly skipped the whole branch;
* the merge test calls ``AgentService.merge_batch`` unbound with a
  ``SimpleNamespace``, so it never sees the kwargs the real call site passes.

Gates here therefore cover the seam, not either half: the literal call sites in
``task_manager.py`` must bind against the real ``AgentService`` signatures, and
one batch must actually run to completion through ``AgentService``.
"""

from __future__ import annotations

import ast
import inspect
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.task_manager import TERMINAL_TASK_STATUSES
from minicc.task_store import TaskStore
from minicc.web import AgentService

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_MANAGER = REPO_ROOT / "minicc" / "task_manager.py"

#: Anti-vacuity floor: the scanner must find the seams it claims to check.
_MIN_CALL_SITES = 2
_CHECKED_METHODS = {"merge_batch", "_run_chat"}


def _config(**extra: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="Zx9q-not-a-real-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
        auto_resume_on_start=False,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def _service(tmp_path: Path, **extra: Any) -> AgentService:
    return AgentService(tmp_path, _config(**extra), task_store=TaskStore(tmp_path / "tasks.sqlite3"))


def _wait(svc: AgentService, task_id: str, timeout: float = 90.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        snapshot = svc.tasks.get(task_id)
        if str(snapshot.get("status")) in TERMINAL_TASK_STATUSES:
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} stuck in {snapshot.get('status')}")


# ---------------------------------------------------------------------------
# the seam: call site kwargs must bind against the real method
# ---------------------------------------------------------------------------


def _service_call_sites() -> list[dict[str, Any]]:
    """Every ``self.service.<method>(...)`` in task_manager.py, with its kwargs."""
    tree = ast.parse(TASK_MANAGER.read_text(encoding="utf-8"))
    sites: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        receiver = node.func.value
        if not (
            isinstance(receiver, ast.Attribute)
            and receiver.attr == "service"
            and isinstance(receiver.value, ast.Name)
            and receiver.value.id == "self"
        ):
            continue
        sites.append({
            "line": node.lineno,
            "method": node.func.attr,
            "args": len(node.args),
            "kwargs": [kw.arg for kw in node.keywords if kw.arg],
            "dynamic": any(kw.arg is None for kw in node.keywords),
        })
    return sites


def test_the_seam_between_task_manager_and_agent_service_is_actually_scanned() -> None:
    sites = _service_call_sites()
    assert len(sites) >= _MIN_CALL_SITES, f"scanner found {len(sites)} call sites; it is not looking"
    assert {str(item["method"]) for item in sites} >= _CHECKED_METHODS, (
        "the two service seams that matter must be in scope: "
        + ", ".join(sorted(str(item["method"]) for item in sites))
    )


def test_task_manager_call_sites_bind_against_real_agent_service_signatures() -> None:
    problems: list[str] = []
    for site in _service_call_sites():
        name = str(site["method"])
        method = getattr(AgentService, name, None)
        if method is None:
            problems.append(f"task_manager.py:{site['line']} calls self.service.{name}(), AgentService has none")
            continue
        if site["dynamic"]:
            # ``_run_chat`` is called through an inspect.signature probe of its
            # own; that call site cannot be bound statically and says so.
            continue
        try:
            inspect.signature(method).bind(
                None, *([object()] * int(site["args"])), **{str(k): object() for k in site["kwargs"]}
            )
        except TypeError as exc:
            problems.append(
                f"task_manager.py:{site['line']} calls self.service.{name}("
                + ", ".join(str(k) for k in site["kwargs"])
                + f"): {exc}"
            )
    assert not problems, "call site / method signature drift:\n" + "\n".join(problems)


# ---------------------------------------------------------------------------
# the product path: a batch must actually complete, offline provider included
# ---------------------------------------------------------------------------


def test_a_successful_batch_completes_through_the_real_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    service = _service(tmp_path)
    try:
        created = service.tasks.submit_batch({
            "messages": ["批量子任务一", "批量子任务二"],
            "session_id": "batch-merge",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        parent = _wait(service, parent_id)
        # Before the fix this was "failed" with a TypeError from the merge call.
        assert parent["status"] == "completed", f"batch parent ended {parent['status']}: {parent.get('error')}"
        assert "watcher 失败" not in str(parent.get("error") or "")
        assert str(parent.get("answer") or "").strip(), parent
        children = [_wait(service, str(cid)) for cid in created["task_ids"]]
        assert [c["status"] for c in children] == ["completed", "completed"]
        # The merge is one more model call on top of the children, so the
        # parent's usage must be at least the children's sum (never less).
        parent_tokens = int((parent.get("tokens_used") or {}).get("total_tokens") or 0)
        child_tokens = sum(int((c.get("tokens_used") or {}).get("total_tokens") or 0) for c in children)
        assert parent_tokens >= child_tokens > 0
    finally:
        service.shutdown()


def test_merge_batch_uses_the_task_model_and_configured_protocol(tmp_path: Path, monkeypatch) -> None:
    """``model=`` must reach the provider, and an anthropic config must not merge over OpenAI wire format."""
    monkeypatch.delenv("MINICC_FAKE_PROVIDER", raising=False)
    seen: dict[str, dict[str, Any]] = {}

    class RecordingProvider:
        def __init__(self, **kwargs: Any) -> None:
            seen.setdefault(self.__class__.__name__, {}).update(kwargs)

        async def chat(self, **kwargs: Any):  # pragma: no cover - anthropic
            from minicc.llm.base import LLMResponse

            return LLMResponse(content="merged", usage={"total_tokens": 3})

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", RecordingProvider, raising=False)
    monkeypatch.setattr("minicc.web.AnthropicProvider", type(
        "RecordingAnthropic", (RecordingProvider,), {}
    ), raising=False)
    service = _service(tmp_path, provider_type="anthropic")
    try:
        result = AgentService.merge_batch(
            service, [{"status": "completed", "answer": "child"}], model="claude-opus-4-20251101"
        )
        assert result["answer"] == "merged"
        assert seen["RecordingAnthropic"]["model"] == "claude-opus-4-20251101"
    finally:
        service.shutdown()


# ---------------------------------------------------------------------------
# /api/metrics: the aggregate must equal what was really spent, once
# ---------------------------------------------------------------------------


def _metrics_of(service: AgentService) -> dict[str, Any]:
    return service.metrics(limit=500)


def test_metrics_count_batch_usage_once_even_though_the_parent_rolls_children_up(
    tmp_path: Path, monkeypatch
) -> None:
    """A batch parent's snapshot already contains its children's tokens.

    ``metrics()`` sums *rows*, so counting the parent and each subtask row
    again bills the same tokens twice. The single-task snapshot is the
    roadmap's ground truth (M8 criterion 5), so the aggregate must match the
    rolled-up top-level rows, not the raw row sum.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"test-model": {"input": 1.0, "output": 2.0}})
    )
    service = _service(tmp_path)
    try:
        created = service.tasks.submit_batch({
            "messages": ["metrics 子任务一", "metrics 子任务二"],
            "session_id": "batch-metrics",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        parent = _wait(service, parent_id)
        children = [_wait(service, str(cid)) for cid in created["task_ids"]]
        assert parent["status"] == "completed", parent.get("error")

        metrics = _metrics_of(service)
        assert metrics["task_count"] == 1
        # The excluded rows stay countable, so "1 task" cannot read as "1 row".
        assert metrics["subtask_rows"] == len(children)
        # Ground truth: every model call in this process belongs to the parent
        # subtree, and the parent snapshot already rolls the children up.
        assert metrics["usage"]["total_tokens"] == int(
            (parent.get("tokens_used") or {}).get("total_tokens") or 0
        ), (
            "aggregate double-counts subtask rows: "
            + json.dumps({"metrics": metrics["usage"], "parent": parent.get("tokens_used"),
                          "children": [c.get("tokens_used") for c in children]})
        )
        assert metrics["cost_usd"] == pytest.approx(float(parent.get("cost_usd") or 0.0))
        # A nonzero number is the point: a cost assertion against an unpriced
        # model passes no matter what the aggregation does.
        assert metrics["cost_usd"] > 0.0
        assert metrics["priced_tasks"] >= 1 and metrics["unpriced_tasks"] == 0
    finally:
        service.shutdown()
