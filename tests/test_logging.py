"""M8-T5: structured logging, redaction, /api/metrics and error codes.

Contract under test (docs/ROADMAP_TO_PRODUCT.md M8-T5):

* a fake-provider task run leaves ``provider_retry``, ``tool_round_finished``
  and ``run_finished`` in the log file;
* neither the api key nor the web token can be echoed into a log line, even
  when a code path passes them straight into a logger call;
* ``/api/metrics`` agrees with the per-task snapshots it aggregates;
* ``/api/audit`` filters by level;
* failure paths answer with a structured ``code`` instead of a bare 500 JSON;
* the package no longer writes to stdout through ``print`` (only ``cli_io``).

Note on the print gate: the roadmap measures it with
``git grep -c 'print(' minicc/``. That substring also matches ``fingerprint(``
and the ``print`` calls embedded in the *subprocess grader scripts* in
``bench_tasks.py`` / ``behavior_bench.py`` (which are not minicc's own stdout),
so the real baseline was 73 — not the 55 the roadmap recorded — and it can
never reach 5 by converting our own calls. The honest gate below is an AST
count of actual ``print`` calls, which the substring count cannot game.
"""

from __future__ import annotations

import ast
import json
import asyncio
import logging
import sys
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

import pytest

from minicc import logging_setup
from minicc.logging_setup import (
    REDACTED,
    configure_logging,
    describe_event,
    redact,
    register_secret,
    resolve_level,
)
from minicc.task_manager import TERMINAL_TASK_STATUSES
from minicc.task_store import TaskStore
from minicc.tools.editor import Editor, audit_level
from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import WebAuth

# Deliberately *not* matching any known secret shape (no ``sk-``, no
# ``Bearer``, no JWT): if these strings are absent from the log, it is
# because register_secret() masked them, not because a pattern rule caught them.
API_KEY = "Zx9q-local-provider-key-not-a-pattern-4242"
WEB_TOKEN = "Wt7k-local-web-token-not-a-pattern-9182"

#: Split so the concatenated value is a genuine PEM banner at runtime while this
#: file keeps no literal copy — the repo's global pre-commit hook greps for that
#: banner in staged diffs and a test fixture must not look like a leaked key.
PEM_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


def _config(**extra: Any) -> types.SimpleNamespace:
    base: dict[str, Any] = dict(
        yolo=False,
        max_concurrent_tasks=4,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key=API_KEY,
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


def _service(workspace: Path) -> AgentService:
    return AgentService(
        workspace, _config(), task_store=TaskStore(workspace / "tasks.sqlite3")
    )


def _run_task(
    service: AgentService, workspace: Path, message: str = "hello", model: str | None = None
) -> dict[str, Any]:
    """Submit one fake-provider task and wait for its terminal snapshot."""
    submitted = service.tasks.submit(
        {
            "message": message,
            "session_id": "s-logging",
            "workspace_path": str(workspace),
            "allow_changes": False,
            "_skip_auto_orchestration": True,
            **({"model": model} if model else {}),
        }
    )
    task_id = str(submitted["task_id"])
    deadline = time.time() + 90.0
    snapshot: dict[str, Any] = submitted
    while time.time() < deadline:
        snapshot = service.tasks.get(task_id)
        if str(snapshot.get("status")) in TERMINAL_TASK_STATUSES:
            break
        time.sleep(0.05)
    assert str(snapshot.get("status")) in TERMINAL_TASK_STATUSES, f"task stuck: {snapshot.get('status')}"
    return snapshot


class _LiveServer:
    """Real HTTP surface over a real AgentService (fake provider, no network)."""

    def __init__(self, workspace: Path) -> None:
        self.service = _service(workspace)
        self.server = MiniccHTTPServer(
            ("127.0.0.1", 0), self.service, auth=WebAuth(WEB_TOKEN, required=False)
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def get(self, path: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return _request(f"{self.url}{path}", headers=headers)

    def post(self, path: str, payload: Any):
        body = json.dumps(payload).encode("utf-8")
        return _request(
            f"{self.url}{path}",
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
        )

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.service.shutdown()


def _request(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")


@pytest.fixture(autouse=True)
def _credentials_registered() -> None:
    """Production registers both values at startup; do it explicitly here.

    Otherwise the redaction tests would depend on which earlier test happened
    to construct an AgentService.
    """
    register_secret(API_KEY)
    register_secret(WEB_TOKEN)


@pytest.fixture
def log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """DEBUG-to-file logging for one test, restored to the default after."""
    path = tmp_path / "minicc.log"
    monkeypatch.setenv("MINICC_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MINICC_LOG_FILE", str(path))
    configure_logging(force=True)
    try:
        yield path
    finally:
        # Leaving a DEBUG file handler attached would leak both the log volume
        # and a dead temp path into every later test module.
        monkeypatch.delenv("MINICC_LOG_LEVEL", raising=False)
        monkeypatch.delenv("MINICC_LOG_FILE", raising=False)
        configure_logging(force=True)


# ---------------------------------------------------------------------------
# the acceptance run: three event codes, no credentials
# ---------------------------------------------------------------------------


def test_task_run_logs_required_events_and_redacts_credentials(
    tmp_path: Path,
    log_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The fake provider's documented fault-injection hook (see llm/fake.py):
    # it emits the real stream-retry trace shape without touching the network.
    monkeypatch.setenv("MINICC_FAKE_PROVIDER_FAULTS", "2")
    service = _service(tmp_path)
    try:
        snapshot = _run_task(service, tmp_path)
        assert snapshot["status"] == "completed", snapshot.get("error")
    finally:
        service.shutdown()

    # A probe line proves the file handler's redaction filter runs on real
    # record content, not merely on code paths that happen not to log secrets.
    logging_setup.get_logger("probe").error(
        "probe api_key=%s authorization=Bearer %s", API_KEY, WEB_TOKEN
    )
    for handler in logging.getLogger(logging_setup.ROOT_NAME).handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")

    for code in ("provider_retry", "tool_round_finished", "run_finished"):
        assert code in content, f"missing {code} in log"
    assert "code=provider_retry" in content
    assert content.count("task_finished task_id=") == 1
    assert "task_event task_id=task-" in content
    assert "task_finished task_id=task-" in content
    assert API_KEY not in content
    assert WEB_TOKEN not in content
    assert REDACTED in content


def test_sync_chat_path_logs_the_same_vocabulary_as_the_task_path(
    tmp_path: Path,
    log_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``/api/chat`` runs no TaskManager, so it used to log nothing about the run.

    The workbench UI submits tasks and gets one DEBUG line per event; a script
    or integration calling the synchronous endpoint saw only HTTP access lines,
    which is exactly the blind spot M8-T5 was meant to close.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER_FAULTS", "2")
    service = _service(tmp_path)
    try:
        result = service.chat(
            {"message": "hello", "session_id": "s-chat", "allow_changes": False}
        )
        assert not result.get("error"), result.get("error")
    finally:
        service.shutdown()

    for handler in logging.getLogger(logging_setup.ROOT_NAME).handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")

    for code in ("provider_retry", "tool_round_finished", "run_finished"):
        assert code in content, f"missing {code} in sync-path log"
    assert "task_event task_id=s-chat" in content
    assert API_KEY not in content
    assert WEB_TOKEN not in content


def test_metrics_endpoint_reconciles_with_task_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Without a price the whole cost half of this test compares 0.0 with 0.0 and
    # passes no matter what the aggregation does.
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"test-model": {"input": 1.0, "output": 2.0}})
    )
    live = _LiveServer(tmp_path)
    try:
        first = _run_task(live.service, tmp_path, "first prompt")
        second = _run_task(live.service, tmp_path, "second prompt")
        status, payload = live.get("/api/metrics")
        assert status == 200
        assert payload["schema_version"] == "minicc.metrics.v1"
        assert payload["task_count"] == 2
        assert payload["subtask_rows"] == 0

        # The reconciliation the roadmap asks for: aggregate == sum of the
        # single-task snapshots, key by key.
        per_task_tokens: dict[str, int] = {}
        per_task_cost = 0.0
        for snapshot in (first, second):
            for key, value in (snapshot["tokens_used"] or {}).items():
                per_task_tokens[key] = per_task_tokens.get(key, 0) + int(value)
            per_task_cost += float(snapshot["cost_usd"] or 0.0)
        assert payload["usage"] == per_task_tokens
        assert payload["cost_usd"] == pytest.approx(per_task_cost)
        assert per_task_cost > 0.0
        assert payload["priced_tasks"] == 2
        assert payload["unpriced_tasks"] == 0

        bucket = payload["by_model"]["test-model"]
        assert bucket["tasks"] == 2
        assert bucket["tokens"] == per_task_tokens
        assert payload["tasks_by_status"]["completed"] == 2
    finally:
        live.shutdown()


def test_metrics_answers_unknown_cost_as_unknown_in_every_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One payload may not say ``null`` and ``0.0`` about the same fact.

    ``by_model`` already answered ``cost_usd: None`` for an unpriced model, but
    the total kept ``0.0`` — and a per-task snapshot for that same model said
    ``None`` too. ``0.0`` reads as "this cost nothing" when the truth is
    "nothing in the price table covers it", which is the M8-T23 ``workspace_path``
    failure mode one field over.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"priced-model": {"input": 1.0, "output": 2.0}})
    )
    service = _service(tmp_path)
    try:
        # (a) Nothing priced: no number at all, but the tokens are still real.
        _run_task(service, tmp_path, "没有价格的一条")
        metrics = service.metrics(limit=100)
        assert (metrics["priced_tasks"], metrics["unpriced_tasks"]) == (0, 1)
        assert metrics["cost_usd"] is None
        assert metrics["cost_is_partial"] is False
        assert int(metrics["usage"]["total_tokens"]) > 0
        assert metrics["by_model"]["test-model"]["cost_usd"] is None

        # (b) Half priced: the number is a floor, and it has to say so.
        priced = _run_task(service, tmp_path, "有价格的一条", model="priced-model")
        metrics = service.metrics(limit=100)
        assert (metrics["priced_tasks"], metrics["unpriced_tasks"]) == (1, 1)
        assert metrics["cost_usd"] is not None
        assert float(metrics["cost_usd"]) == pytest.approx(float(priced["cost_usd"]))
        assert metrics["cost_usd"] > 0.0
        assert metrics["cost_is_partial"] is True
        assert metrics["by_model"]["test-model"]["cost_usd"] is None
        assert metrics["by_model"]["priced-model"]["cost_usd"] == pytest.approx(metrics["cost_usd"])
        # Tokens are never withheld because a price is missing.
        assert int(metrics["usage"]["total_tokens"]) > int(
            metrics["by_model"]["priced-model"]["tokens"]["total_tokens"]
        )

        # (c) Every field agrees once nothing is unpriced anymore.
        filtered = service.metrics(limit=100, workspace_path=str(tmp_path / "elsewhere"))
        assert filtered["task_count"] == 0
        assert filtered["cost_usd"] is None
        assert filtered["cost_is_partial"] is False
        # An empty scope must be empty in every breakdown, not just in the
        # total — otherwise "0 tasks, 3 models" reads as a working aggregator.
        assert filtered["by_model"] == {}
        assert filtered["tasks_by_status"] == {}
        assert filtered["usage"] == {}
        assert filtered["subtask_rows"] == 0
    finally:
        service.shutdown()


def test_metrics_breakdowns_add_up_to_the_totals_they_are_shown_next_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The payload's own parts must agree with each other, not only with the rows.

    ``/api/metrics`` answers five aggregates over the same rows — ``usage``,
    ``cost_usd``, ``by_model``, ``tasks_by_status``, ``subtask_rows`` — and a
    reader compares them side by side ("which model spent this?"). M8-T23 caught
    the total disagreeing with the per-task snapshots; nothing here checked that
    the *breakdowns* sum to the total they decorate, or that the batch fold is
    counted once in both. Measured first: it holds today, so this is a fence,
    not a fix.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"priced-model": {"input": 1.0, "output": 2.0}})
    )
    service = _service(tmp_path)
    try:
        def terminal(task_id: str) -> dict[str, Any]:
            deadline = time.time() + 90.0
            while time.time() < deadline:
                snapshot = service.tasks.get(task_id)
                if str(snapshot.get("status")) in TERMINAL_TASK_STATUSES:
                    return snapshot
                time.sleep(0.05)
            raise AssertionError(f"task {task_id} never finished")

        _run_task(service, tmp_path, "未计价的根任务")
        _run_task(service, tmp_path, "有计价的根任务", model="priced-model")
        created = service.tasks.submit_batch({
            "messages": ["分解一", "分解二"],
            "session_id": "breakdown",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        parent = terminal(parent_id)
        children = [terminal(str(cid)) for cid in created["task_ids"]]
        assert parent["status"] == "completed", parent.get("error")

        metrics = service.metrics(limit=500, workspace_path=str(tmp_path))
        rows = service.tasks.list(limit=500, workspace_path=str(tmp_path))
        usage = metrics["usage"]
        by_model = metrics["by_model"]

        # The shape has to be non-trivial before any of this means anything.
        assert metrics["task_count"] == 3
        assert set(by_model) == {"test-model", "priced-model"}, sorted(by_model)
        assert metrics["unpriced_tasks"] == 2 and metrics["priced_tasks"] == 1
        assert int(usage["total_tokens"]) > 0

        # 1. every token counter: sum over models == the top-level total
        for key, value in usage.items():
            assert sum(int((bucket["tokens"].get(key) or 0)) for bucket in by_model.values()) == int(
                value
            ), f"{key} does not add up across by_model"
        # 2. one row per root task, in exactly one model bucket
        assert sum(int(bucket["tasks"]) for bucket in by_model.values()) == metrics["task_count"]
        # 3. cost: the total is the sum of the buckets that have a number, and
        #    the buckets without one are the reason cost_is_partial is true.
        assert metrics["cost_usd"] == pytest.approx(
            sum(float(b["cost_usd"]) for b in by_model.values() if b["cost_usd"] is not None)
        )
        assert metrics["cost_usd"] > 0.0
        assert metrics["cost_is_partial"] is True
        assert by_model["test-model"]["cost_usd"] is None
        # 4. status counts cover the same rows the totals cover...
        assert sum(metrics["tasks_by_status"].values()) == metrics["task_count"]
        # 5. ...and the excluded subtask rows stay countable, so "3 tasks" cannot
        #    be read as "3 rows in the index".
        assert metrics["task_count"] + metrics["subtask_rows"] == len(rows)
        assert metrics["subtask_rows"] == len(children)
        # 6. the folded parent is billed once, in both the total and its bucket.
        parent_tokens = int((parent.get("tokens_used") or {})["total_tokens"])
        assert parent_tokens > 0
        bucket_total = sum(
            int((bucket["tokens"].get("total_tokens") or 0))
            for name, bucket in by_model.items()
            if name == str(parent.get("model"))
        )
        assert bucket_total >= parent_tokens
        child_total = sum(int((c.get("tokens_used") or {}).get("total_tokens") or 0) for c in children)
        assert int(usage["total_tokens"]) >= parent_tokens + child_total
    finally:
        service.shutdown()


def test_metrics_limit_and_workspace_filter(tmp_path: Path) -> None:
    live = _LiveServer(tmp_path)
    try:
        _run_task(live.service, tmp_path)
        _, all_rows = live.get("/api/metrics")
        other = str(tmp_path / "elsewhere")
        _, none_rows = live.get("/api/metrics?workspace=" + urllib.parse.quote(other))
        _, first_row = live.get("/api/metrics?limit=1")
        assert all_rows["task_count"] == 1
        assert none_rows["task_count"] == 0
        assert none_rows["usage"] == {}
        assert first_row["task_count"] == 1
        # An unfiltered total spans every workspace in the shared task store,
        # so it must not come back labelled with one workspace's path.
        assert all_rows["scope"] == "all_workspaces"
        assert all_rows["workspace_path"] is None
        assert none_rows["scope"] == other
        assert none_rows["workspace_path"] == other
    finally:
        live.shutdown()


# ---------------------------------------------------------------------------
# /api/audit level filter
# ---------------------------------------------------------------------------


def _write_audit(workspace: Path, entries: list[dict[str, Any]]) -> Path:
    path = workspace / ".minicc" / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def test_audit_levels_are_derived_from_action_and_refusal() -> None:
    assert audit_level("read") == "info"
    assert audit_level("write", "created 3 lines") == "notice"
    assert audit_level("delete", "拒绝：路径越界") == "warning"
    assert audit_level("edit", "refused: stale digest") == "warning"
    # delete/move legitimately have no after-digest but are not refusals.
    assert audit_level("move", "moved a.txt -> b.txt") == "notice"


def test_editor_writes_level_into_audit_file(tmp_path: Path) -> None:
    audit_path = tmp_path / ".minicc" / "audit.jsonl"
    editor = Editor(tmp_path, audit_path=audit_path)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    editor.write_file("a.txt", "two\n")
    editor.read_file("a.txt")
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    levels = {row["action"]: row["level"] for row in rows}
    assert levels["write"] == "notice"
    assert levels["read"] == "info"


def test_audit_export_filters_by_level(tmp_path: Path) -> None:
    _write_audit(
        tmp_path,
        [
            {"timestamp": "t1", "action": "read", "path": "a", "detail": "", "level": "info"},
            {"timestamp": "t2", "action": "write", "path": "a", "detail": "ok", "level": "notice"},
            {
                "timestamp": "t3",
                "action": "edit",
                "path": "a",
                "detail": "拒绝：并发修改",
                "before_digest": "d",
                "level": "warning",
            },
            # Legacy line written before M8-T5: no level field at all.
            {"timestamp": "t4", "action": "delete", "path": "b", "detail": "refused: in use"},
        ],
    )
    service = _service(tmp_path)
    try:
        everything = service.audit_export()
        assert everything["count"] == 4
        assert [entry["level"] for entry in everything["entries"]] == [
            "info",
            "notice",
            "warning",
            "warning",
        ]
        warnings_only = service.audit_export(levels=["warning"])
        assert [entry["timestamp"] for entry in warnings_only["entries"]] == ["t3", "t4"]
        assert warnings_only["total"] == 2
        floor = service.audit_export(min_level="notice")
        assert [entry["timestamp"] for entry in floor["entries"]] == ["t2", "t3", "t4"]
        both = service.audit_export(levels=["info", "warning"], min_level="warning")
        assert [entry["timestamp"] for entry in both["entries"]] == ["t3", "t4"]
        with pytest.raises(ValueError, match="未知审计级别"):
            service.audit_export(levels=["trace"])
        with pytest.raises(ValueError, match="未知审计级别"):
            service.audit_export(min_level="fatal")
    finally:
        service.shutdown()


def test_audit_endpoint_exposes_level_filter(tmp_path: Path) -> None:
    _write_audit(
        tmp_path,
        [
            {"timestamp": "t1", "action": "read", "path": "a", "detail": "", "level": "info"},
            {"timestamp": "t2", "action": "edit", "path": "a", "detail": "denied", "level": "warning"},
        ],
    )
    live = _LiveServer(tmp_path)
    try:
        status, payload = live.get("/api/audit?min_level=warning")
        assert status == 200
        assert [entry["timestamp"] for entry in payload["entries"]] == ["t2"]
        status, payload = live.get("/api/audit?level=info")
        assert [entry["timestamp"] for entry in payload["entries"]] == ["t1"]
        status, payload = live.get("/api/audit?level=nonsense")
        assert status == 400
        assert payload["code"] == "invalid_request"
    finally:
        live.shutdown()


# ---------------------------------------------------------------------------
# structured error codes
# ---------------------------------------------------------------------------


def test_failure_paths_return_structured_error_codes(tmp_path: Path) -> None:
    live = _LiveServer(tmp_path)
    try:
        status, payload = live.get("/api/tasks/task-does-not-exist")
        assert status == 404
        assert payload["code"] == "task_not_found"
        assert payload["error"]

        status, payload = live.post("/api/tasks", {"session_id": "s1"})
        assert status == 400
        assert payload["code"] == "invalid_request"

        def explode(payload: dict[str, Any]) -> dict[str, Any]:
            raise PermissionError("not allowed here")

        live.service.chat = explode  # type: ignore[method-assign]
        status, payload = live.post("/api/chat", {"message": "boom"})
        assert status == 500
        assert payload["code"] == "forbidden"
        assert payload["error_type"] == "PermissionError"
        assert payload["retryable"] is True
    finally:
        live.shutdown()


def test_5xx_failures_are_logged_with_their_code(tmp_path: Path, log_file: Path) -> None:
    live = _LiveServer(tmp_path)
    try:
        def explode(payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("provider exploded")

        live.service.chat = explode  # type: ignore[method-assign]
        status, payload = live.post("/api/chat", {"message": "boom"})
        assert status == 500
        assert payload["code"] == "internal_error"
        for handler in logging.getLogger(logging_setup.ROOT_NAME).handlers:
            handler.flush()
        content = log_file.read_text(encoding="utf-8")
        assert "request_failed" in content
        assert "code=internal_error" in content
        assert "provider exploded" in content
    finally:
        live.shutdown()


# ---------------------------------------------------------------------------
# logger configuration defaults
# ---------------------------------------------------------------------------


def test_default_level_is_warning_on_stderr_never_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MINICC_LOG_LEVEL", raising=False)
    monkeypatch.delenv("MINICC_LOG_FILE", raising=False)
    logger = configure_logging(force=True)
    try:
        assert logger.level == logging.WARNING
        assert logger.propagate is False
        assert logger.handlers, "expected at least one handler"
        assert all(handler.stream is not sys.stdout for handler in logger.handlers)
        assert any(handler.stream is sys.stderr for handler in logger.handlers)
    finally:
        monkeypatch.setenv("MINICC_LOG_LEVEL", "WARNING")
        configure_logging(force=True)


def test_resolve_level_accepts_names_and_numbers() -> None:
    assert resolve_level("DEBUG") == logging.DEBUG
    assert resolve_level("warning") == logging.WARNING
    assert resolve_level("10") == logging.DEBUG
    assert resolve_level("garbage") == logging.WARNING
    assert resolve_level(None) == logging.WARNING


def test_configure_logging_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "twice.log"
    monkeypatch.setenv("MINICC_LOG_FILE", str(path))
    first = configure_logging(force=True)
    count = len(first.handlers)
    configure_logging()
    configure_logging()
    assert len(first.handlers) == count
    monkeypatch.delenv("MINICC_LOG_FILE", raising=False)
    configure_logging(force=True)


# ---------------------------------------------------------------------------
# redaction primitives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        (f"Authorization: Bearer {WEB_TOKEN}", WEB_TOKEN),
        (f'{{"api_key": "{API_KEY}"}}', API_KEY),
        (f"?token={WEB_TOKEN}&x=1", WEB_TOKEN),
        (f"header key={API_KEY} other", API_KEY),
        (f"{PEM_BEGIN}\n{API_KEY}\n-----END-----", API_KEY),
    ],
)
def test_redact_masks_labeled_and_registered_secrets(raw: str, needle: str) -> None:
    masked = redact(raw)
    assert needle not in masked
    assert REDACTED in masked
    # Redaction must be stable: masking a masked line cannot corrupt it further.
    assert redact(masked) == masked


def test_redact_leaves_ordinary_text_alone() -> None:
    text = "request body rejected: message 不能为空 (task-abc123)"
    assert redact(text) == text


def test_word_shaped_secret_cannot_corrupt_existing_markers() -> None:
    # Regression: another suite registers api_key="secret". Masking that value
    # inside an upstream ``[REDACTED:…]`` marker re-grew the line on every pass.
    register_secret("secret")
    line = "detail=拒绝泄露 secret；上游已脱敏 [REDACTED:llm_api_key]"
    once = redact(line)
    assert "[REDACTED:llm_api_key]" in once
    assert "]]" not in once
    assert "secret" not in once
    assert redact(once) == once

def test_registered_short_values_are_ignored() -> None:
    register_secret("abc")
    assert "abc" not in {value for value in logging_setup._secrets}  # noqa: SLF001


def test_describe_event_renders_stable_pairs() -> None:
    line = describe_event(
        {
            "kind": "trace",
            "code": "provider_retry",
            "name": "provider",
            "status": "error",
            "phase": "planning",
            "detail": {"attempt": 2},
            "summary": "模型流中断",
        }
    )
    assert "kind=trace" in line
    assert "code=provider_retry" in line
    assert "attempt=2" in line
    assert "summary='模型流中断'" in line
    assert describe_event(None) == "kind=unknown code=- name=- status=- phase=-"


# ---------------------------------------------------------------------------
# the print gate
# ---------------------------------------------------------------------------


def _print_calls() -> dict[str, int]:
    """Count real ``print(...)`` call sites in the package (AST, not grep)."""
    counts: dict[str, int] = {}
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                key = path.relative_to(REPO_ROOT).as_posix()
                counts[key] = counts.get(key, 0) + 1
    return counts


def test_only_cli_io_writes_stdout_through_print() -> None:
    counts = _print_calls()
    # cli_out() itself is the single stdout choke point; everything else must
    # go through it (or a logger, which writes to stderr).
    assert counts == {"minicc/cli_io.py": 1}, counts
    assert sum(counts.values()) <= 5


_LEAKED_GENERATORS: list = []


def test_loop_teardown_noise_goes_to_the_log_not_the_terminal(
    log_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Upstream bug, our stderr: a correct answer must not end in a traceback.

    httpcore2's response-body iterator does not stop on ``athrow()``, so asyncio
    reports it while shutting the loop down. We cannot patch the transport, so
    the event is routed to the log - and everything else still reaches the
    default handler, which this test also proves.
    """

    async def scenario() -> None:
        logging_setup.quiet_loop_teardown()

        async def stubborn():
            try:
                yield 1
            except GeneratorExit:
                raise RuntimeError("generator didn't stop after athrow()") from None

        # Held where the loop cannot forget it before shutdown, the way httpx
        # holds its response body iterator: a generator that dies with the
        # coroutine is finalised without ever reporting to this loop.
        _LEAKED_GENERATORS.append(stubborn().__aiter__())
        await _LEAKED_GENERATORS[-1].__anext__()

    asyncio.run(scenario())
    for handler in logging.getLogger(logging_setup.ROOT_NAME).handlers:
        handler.flush()

    assert "closing of asynchronous generator" not in capsys.readouterr().err
    content = log_file.read_text(encoding="utf-8")
    assert "loop_teardown" in content
    assert "RuntimeError" in content
