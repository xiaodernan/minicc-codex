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

The file grew a second lease of life in M8-T24: the same subtree-usage fold is
checked on *every* path that finalises a parent (merged / child-failed /
cancelled / crashed), that it happens exactly once, that it survives the
persisted round trip, and that the parent's number is the same number in the
snapshot, the index summary, ``/api/metrics`` and the stored row.
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

from minicc.task_manager import TERMINAL_TASK_STATUSES, TaskManager, TaskRecord
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


def _wait_row(svc: AgentService, task_id: str, timeout: float = 20.0) -> dict[str, Any]:
    """Poll the write-behind store until it carries the fold a restart reads.

    The row is flushed by the watcher's final force-persist, which lands *after*
    the status turns terminal — so a single read at that moment can return a
    pre-fold row, and under a loaded suite the gap is seconds wide. A row that
    never catches up is exactly the failure this poll still reports.
    """
    deadline = time.time() + timeout
    row: dict[str, Any] = {}
    while time.time() < deadline:
        row = svc.tasks.store.get(task_id) or {}
        if row.get("children_rolled_up") and _total((row.get("result") or {}).get("tokens_used")) > 0:
            return row
        time.sleep(0.05)
    raise AssertionError(
        f"persisted row for {task_id} never carried the fold: "
        + json.dumps({"tokens_used": row.get("tokens_used"), "flag": row.get("children_rolled_up")})
    )


def _wait_billed(svc: AgentService, task_id: str, minimum: int, timeout: float = 20.0) -> dict[str, Any]:
    """Poll until the parent's number is above ``minimum``; callers assert the value.

    A cancellation makes the status terminal from *outside* the watcher, so the
    first terminal snapshot a poller sees can predate the watcher's bookkeeping.
    Waiting on status alone would read the record mid-finalisation and fail for
    the wrong reason — the arithmetic below is still what decides the test.
    """
    deadline = time.time() + timeout
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        snapshot = svc.tasks.get(task_id)
        if _total(snapshot.get("tokens_used")) > minimum:
            return snapshot
        time.sleep(0.05)
    raise AssertionError(
        f"task {task_id} never exceeded {minimum} tokens: {snapshot.get('tokens_used')}"
    )


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
        parent_tokens = _total(parent.get("tokens_used"))
        child_tokens = sum(_total(c.get("tokens_used")) for c in children)
        assert parent_tokens >= child_tokens > 0
    finally:
        service.shutdown()


def test_a_failed_batch_still_reports_what_its_children_spent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The root must own the subtree on *every* terminal path, not just success.

    ``metrics()`` bills each subtree at its root, so a parent that fails after
    its children succeeded would otherwise make their real spend disappear from
    the aggregate (the M8-T23 boundary this test closes).
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"test-model": {"input": 1.0, "output": 2.0}})
    )
    service = _service(tmp_path)

    def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("合并器炸了")

    try:
        created = service.tasks.submit_batch({
            "messages": ["失败批量一", "失败批量二"],
            "session_id": "batch-fail",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        monkeypatch.setattr(service, "merge_batch", explode)
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        parent = _wait(service, parent_id)
        children = [_wait(service, str(cid)) for cid in created["task_ids"]]
        assert parent["status"] == "failed", parent
        child_tokens = sum(_total(c.get("tokens_used")) for c in children)
        assert child_tokens > 0
        assert _total(parent.get("tokens_used")) == child_tokens
        metrics = _metrics_of(service)
        assert metrics["subtask_rows"] == len(children)
        assert metrics["usage"]["total_tokens"] == child_tokens
        assert metrics["cost_usd"] > 0.0
    finally:
        service.shutdown()


def test_a_batch_whose_child_fails_still_bills_the_child_that_succeeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The realistic failure shape: one subtask dies, the parent reports error.

    That path never reaches the merge, so it used to be the branch with no fold
    at all — and it is *not* the same branch the watcher's exception handler
    covers, so testing only one of them leaves the other unguarded.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"test-model": {"input": 1.0, "output": 2.0}})
    )
    real_run_chat = AgentService._run_chat

    def flaky(self, payload, **kwargs):
        if "炸" in str(payload.get("message") or ""):
            raise RuntimeError("子任务炸了")
        return real_run_chat(self, payload, **kwargs)

    monkeypatch.setattr(AgentService, "_run_chat", flaky)
    service = _service(tmp_path)
    try:
        created = service.tasks.submit_batch({
            "messages": ["这条会炸", "这条正常完成"],
            "session_id": "batch-child-fails",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        parent = _wait(service, parent_id)
        children = [_wait(service, str(cid)) for cid in created["task_ids"]]
        assert parent["status"] == "failed", parent
        assert "没有成功结束" in str(parent.get("answer") or ""), parent.get("answer")
        assert sorted(c["status"] for c in children) == ["completed", "failed"], children
        spent = sum(
            _total(c.get("tokens_used")) for c in children
        )
        assert spent > 0
        assert _total(parent.get("tokens_used")) == spent
        metrics = _metrics_of(service)
        assert metrics["usage"]["total_tokens"] == spent
        assert metrics["cost_usd"] > 0.0
    finally:
        service.shutdown()


def test_an_auto_parent_that_crashes_after_reconnaissance_still_owns_the_spend(
    tmp_path: Path
) -> None:
    """The other root shape: auto orchestration hands the parent back to ``_run``.

    A manual batch is finalised by ``_watch_batch``; an auto parent resumes in
    ``_run``, whose crash path is a *different* handler with the same
    obligation. If only the watcher folds, every auto parent that dies after its
    reconnaissance silently drops that reconnaissance's cost from the bill.
    """
    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=4, model="test-model")
        workspace = tmp_path

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_usage=None, on_stream=None,
                      on_context=None, on_compaction=None, cancel_event=None):
            message = str(payload["message"])
            if "自动编排证据" in message:
                # The parent's own attempt dies before it reports any usage.
                raise RuntimeError("主 Agent 在侦察之后崩了")
            if on_usage is not None:
                on_usage({"prompt_tokens": 400, "completion_tokens": 100, "total_tokens": 500})
            if on_event is not None:
                on_event({"kind": "trace", "phase": "planning", "status": "ok", "summary": "只读侦察完成"})
            return {"answer": "侦察完成", "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=4)
    try:
        created = manager.submit({
            "message": (
                "请分析前后端现状，修复登录和任务流式输出，同时优化界面，并补充测试，"
                "联网调研最新文档后运行验证。"
            ),
            "session_id": "auto-crash",
            "allow_changes": True,
            "workspace_path": str(tmp_path),
        })
        assert created["orchestration_mode"] == "auto", created
        parent_id = str(created["task_id"])
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if str(manager.get(parent_id)["status"]) in TERMINAL_TASK_STATUSES:
                break
            time.sleep(0.02)
        parent = manager.get(parent_id)
        assert parent["status"] == "failed", parent
        assert "主 Agent 在侦察之后崩了" in str(parent.get("error") or ""), parent.get("error")
        children = [manager.get(cid) for cid in created["child_task_ids"]]
        assert children and all(c["status"] == "completed" for c in children)
        spent = sum(_total(c.get("tokens_used")) for c in children)
        assert spent > 0
        assert _total(parent.get("tokens_used")) == spent
        row = next((item for item in manager.list(limit=50) if item["task_id"] == parent_id), {})
        assert _total(row.get("tokens_used")) == spent
    finally:
        manager.shutdown()


def test_a_cancelled_batch_parent_keeps_the_fold_the_result_gate_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fourth terminal shape, and the reason the fold is not part of the result.

    ``apply_result`` deliberately refuses to touch an already-terminal record,
    so cancelling the parent while its merge runs makes that refusal the last
    thing the subtask fold depends on. Folding *after* the gate keeps the
    subtree visible; folding *inside* the result payload lost all of it.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"test-model": {"input": 1.0, "output": 2.0}})
    )
    service = _service(tmp_path)
    ids: dict[str, str] = {}

    def cancel_during_merge(snapshots, **kwargs):  # noqa: ANN001 - class-level patch
        service.tasks.cancel(ids["parent"])
        return {"answer": "合并期间被取消", "tokens_used": {"total_tokens": 100}}

    try:
        created = service.tasks.submit_batch({
            "messages": ["取消批量一", "取消批量二"],
            "session_id": "batch-cancel",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        ids["parent"] = str(created.get("parent_task_id") or created.get("task_id"))
        monkeypatch.setattr(service, "merge_batch", cancel_during_merge)
        parent = _wait(service, ids["parent"])
        children = [_wait(service, str(cid)) for cid in created["task_ids"]]
        assert parent["status"] == "cancelled", parent
        spent = sum(_total(item.get("tokens_used")) for item in children)
        assert spent > 0
        assert _total(_wait_billed(service, ids["parent"], 0).get("tokens_used")) == spent
        # Boundary this test documents instead of fixing: the merge call's own
        # 100 tokens are not attributed, because the terminal-status gate
        # dropped the whole result payload — the fold only recovers subtasks.
        assert _metrics_of(service)["usage"]["total_tokens"] == spent
    finally:
        service.shutdown()


def test_the_roll_up_happens_once_even_when_the_parent_is_finalised_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotence: a folded parent must not fold again on a later persist."""
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    service = _service(tmp_path)
    try:
        created = service.tasks.submit_batch({
            "messages": ["幂等一", "幂等二"],
            "session_id": "batch-idempotent",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        parent = _wait(service, parent_id)
        children = [_wait(service, str(cid)) for cid in created["task_ids"]]
        first = dict(parent.get("tokens_used") or {})
        record = service.tasks.tasks[parent_id]
        service.tasks._roll_up_tokens(record)
        service.tasks._roll_up_tokens(record)
        assert dict(record.tokens_used) == first
        assert int(first.get("total_tokens") or 0) >= sum(
            _total(c.get("tokens_used")) for c in children
        ) > 0
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


def _total(usage: Any) -> int:
    return int((usage or {}).get("total_tokens") or 0)


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


def test_the_folded_number_is_the_same_number_every_reader_sees(
    tmp_path: Path, monkeypatch
) -> None:
    """One parent, five views — including the two that can silently disagree.

    ``snapshot()`` re-applies the stored result payload *over* the record's own
    ``tokens_used``, so a fold that only updates the record still shows the
    user the unfolded number. And ``metrics()`` reads the index summary, while a
    restart rebuilds the parent from the persisted row: if the row or its
    ``children_rolled_up`` flag loses the fold, the aggregate is correct only
    until the next boot, then double-counts.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"test-model": {"input": 1.0, "output": 2.0}})
    )
    real_merge = AgentService.merge_batch
    merge_own: list[dict[str, Any]] = []

    def spy(self, snapshots, **kwargs):  # noqa: ANN001 - class-level patch
        result = real_merge(self, snapshots, **kwargs)
        # Captured *before* the watcher folds the subtree in, so this is the
        # merge call's own spend.
        merge_own.append(dict(result.get("tokens_used") or {}))
        return result

    monkeypatch.setattr(AgentService, "merge_batch", spy)
    service = _service(tmp_path)
    try:
        created = service.tasks.submit_batch({
            "messages": ["一致一", "一致二"],
            "session_id": "batch-consistency",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        parent = _wait(service, parent_id)
        children = [_wait(service, str(cid)) for cid in created["task_ids"]]
        child_total = sum(_total(item.get("tokens_used")) for item in children)
        assert child_total > 0
        # Ground truth: every model call made in this process belongs to this
        # one subtree — the children's calls plus the merge's own call.
        assert len(merge_own) == 1
        expected = child_total + _total(merge_own[0])
        assert expected > child_total
        row = _wait_row(service, parent_id)
        summary_row = next(
            (item for item in service.tasks.list(limit=500) if item["task_id"] == parent_id), {}
        )
        views = {
            "snapshot": _total(parent.get("tokens_used")),
            "summary": _total(summary_row.get("tokens_used")),
            "metrics": int(_metrics_of(service)["usage"]["total_tokens"]),
            "persisted": _total(row.get("tokens_used")),
            "persisted_result": _total((row.get("result") or {}).get("tokens_used")),
        }
        assert views == {key: expected for key in views}, json.dumps(views, ensure_ascii=False)

        # A restart must not fold a second time: the flag has to survive the
        # round trip, or every boot re-adds the subtasks to their own parent.
        assert row.get("children_rolled_up") is True
        restored = TaskRecord.from_snapshot(row)
        assert _total(restored.tokens_used) == expected
        service.tasks._roll_up_tokens(restored)
        assert _total(restored.tokens_used) == expected
    finally:
        service.shutdown()


def test_a_reconnected_worker_parent_folds_once_even_though_the_mirror_already_did(
    tmp_path: Path
) -> None:
    """The last finalisation path: a parent mirrored back from a worker process.

    M8-T24 documented this one as "not folded". Fixing it naively is worse than
    the gap: ``WorkerSnapshotMirror.result()`` rebuilds ``tokens_used`` from the
    *snapshot*, which for a folded parent already contains the subtree — so
    re-folding there invents spend. The declaration has to travel with the
    payload, which is what this test pins from both sides.
    """
    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = tmp_path

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        child = TaskRecord(
            task_id="mirror-child", session_id="mirror", message="子任务",
            allow_changes=False, workspace_path=str(tmp_path), parent_id="mirror-parent",
        )
        child.update_usage({"prompt_tokens": 300, "completion_tokens": 100, "total_tokens": 400})
        # The fold reads subtasks out of the manager, so an unregistered child
        # would make every assertion below pass for the wrong reason.
        with manager.lock:
            manager.tasks[child.task_id] = child

        def parent(task_id: str) -> TaskRecord:
            record = TaskRecord(
                task_id=task_id, session_id="mirror", message="批任务", allow_changes=False,
                workspace_path=str(tmp_path), child_task_ids=[child.task_id],
                status="running", phase="running",
            )
            with manager.lock:
                manager.tasks[task_id] = record
            return record

        own_only = {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125}
        already_folded = {"prompt_tokens": 400, "completion_tokens": 125, "total_tokens": 525}

        # (a) The worker folded before it died: mirroring must not add again.
        mirrored = parent("mirror-parent-declared")
        assert mirrored.apply_result({
            "answer": "worker 已完成", "tokens_used": dict(already_folded), "children_rolled_up": True,
        }) is True
        manager._roll_up_tokens(mirrored)
        assert _total(mirrored.tokens_used) == 525, mirrored.tokens_used

        # (b) A worker that only ran the parent's own turns still loses the
        #     subtree unless the fold runs here too.
        plain = parent("mirror-parent-plain")
        assert plain.apply_result({"answer": "worker 已完成", "tokens_used": dict(own_only)}) is True
        manager._roll_up_tokens(plain)
        assert _total(plain.tokens_used) == 525, plain.tokens_used

        # (c) The declaration is host billing bookkeeping: it travels from the
        #     snapshot's own field through the mirror, and a produced payload
        #     cannot smuggle it (that would let a model suppress its own bill).
        from minicc.task_contract import TaskResult
        from minicc.task_execution import WorkerSnapshotMirror

        smuggled = TaskResult.from_payload({"tokens_used": dict(own_only), "children_rolled_up": True})
        assert "children_rolled_up" not in smuggled.to_payload()
        mirrored_payload = WorkerSnapshotMirror.result({
            "status": "completed",
            "usage": dict(already_folded),
            "children_rolled_up": True,
            "result": {"answer": "done", "tokens_used": dict(already_folded)},
        })
        assert mirrored_payload["children_rolled_up"] is True
        assert _total(mirrored_payload["tokens_used"]) == 525
        undeclared = WorkerSnapshotMirror.result({
            "status": "completed", "usage": dict(own_only), "result": {"answer": "done"},
        })
        assert "children_rolled_up" not in undeclared
        # A snapshot whose *body* claims the fold but whose host field does not
        # must not be trusted — this is the suppression attempt itself.
        spoofed = WorkerSnapshotMirror.result({
            "status": "completed",
            "usage": dict(already_folded),
            "result": {"answer": "done", "children_rolled_up": True},
        })
        assert "children_rolled_up" not in spoofed
        # ...and feeding an undeclared payload back must fold, because it says nothing.
        again = parent("mirror-parent-mirrored-plain")
        assert again.apply_result(undeclared) is True
        manager._roll_up_tokens(again)
        assert _total(again.tokens_used) == 525

        # (d) And the reconnect path actually calls the fold — testing the
        #     helper alone would leave the call site free to drift.
        tree = ast.parse(TASK_MANAGER.read_text(encoding="utf-8"))
        body = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_reconnect_worker"
        )
        wired = [
            str(node.func.attr)
            for node in ast.walk(body)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ]
        assert "_roll_up_tokens" in wired, wired
    finally:
        manager.shutdown()
