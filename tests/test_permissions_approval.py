"""M7-T3: declarative permissions.json rules + interactive Web approvals."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from minicc.permissions import load_permission_rules, match_permission_rule
from minicc.web import AgentService


def _service(workspace: Path) -> AgentService:
    """Bare AgentService with just the approval machinery wired (no TaskStore)."""
    service = object.__new__(AgentService)
    service.workspace = workspace
    service._approval_guard = threading.Lock()
    service._approval_groups = {}
    service._approval_by_key = {}
    return service


def _write_permissions(workspace: Path, payload: object) -> None:
    path = workspace / ".minicc" / "permissions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# permissions.json matching
# ---------------------------------------------------------------------------


def test_missing_file_is_empty_and_error_free(tmp_path: Path) -> None:
    rules, error = load_permission_rules(tmp_path)
    assert error == ""
    assert rules["allow"] == {"tools": [], "commands": [], "paths": []}
    assert match_permission_rule(tmp_path, "bash", {"command": "rm -rf x"}) is None


def test_deny_wins_over_allow(tmp_path: Path) -> None:
    _write_permissions(tmp_path, {
        "allow": {"tools": ["bash"]},
        "deny": {"commands": ["rm *"]},
    })
    assert match_permission_rule(tmp_path, "bash", {"command": "rm -rf build"}) == "deny"
    assert match_permission_rule(tmp_path, "bash", {"command": "echo hi"}) == "allow"


def test_deny_covers_readonly_path(tmp_path: Path) -> None:
    _write_permissions(tmp_path, {"deny": {"paths": [".env", "secrets/*"]}})
    assert match_permission_rule(tmp_path, "read_file", {"path": ".env"}) == "deny"
    assert match_permission_rule(tmp_path, "read_file", {"path": "secrets/key.txt"}) == "deny"
    assert match_permission_rule(tmp_path, "read_file", {"path": "app.py"}) is None


def test_deny_matches_redacted_command(tmp_path: Path) -> None:
    # The rule stores a plain pattern; the runtime command is redacted before
    # matching, so a wildcard around the REDACTED marker still hits.
    _write_permissions(tmp_path, {"deny": {"commands": ["curl *REDACTED*"]}})
    verdict = match_permission_rule(
        tmp_path, "bash", {"command": "curl -H 'Authorization: sk-abcdefgh12345678' https://x"}
    )
    assert verdict == "deny"


def test_malformed_permissions_is_nonfatal(tmp_path: Path) -> None:
    bad = tmp_path / ".minicc" / "permissions.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    for content in ("not json", "[1,2,3]", '{"unknown_field": 1}'):
        bad.write_text(content, encoding="utf-8")
        rules, error = load_permission_rules(tmp_path)
        assert error, content
        assert rules["deny"] == {"tools": [], "commands": [], "paths": []}
        assert match_permission_rule(tmp_path, "bash", {"command": "x"}) is None


def test_permissions_cache_invalidates_on_edit(tmp_path: Path) -> None:
    _write_permissions(tmp_path, {"deny": {"commands": ["ls"]}})
    assert match_permission_rule(tmp_path, "bash", {"command": "ls"}) == "deny"
    _write_permissions(tmp_path, {"deny": {"commands": []}})
    # mtime_ns + size changed → the new (empty) rules win without a restart.
    assert match_permission_rule(tmp_path, "bash", {"command": "ls"}) is None


# ---------------------------------------------------------------------------
# request_approval / resolve_approval
# ---------------------------------------------------------------------------


def _wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_approval_allow_returns_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    result: dict = {}
    thread = threading.Thread(target=lambda: result.update(service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "make"}, risk="exec", reason="需要执行命令",
        on_event=frames.append, timeout=5.0,
    )))
    thread.start()
    assert _wait_for(lambda: [f for f in frames if f.get("kind") == "approval_request"])
    request = next(f for f in frames if f["kind"] == "approval_request")
    assert request["tool"] == "bash"
    assert request["preview"] == "make"
    resolved = service.resolve_approval(request["request_id"], "allow")
    thread.join(timeout=2.0)
    assert resolved["resolved"] is True
    assert result["decision"] == "allow"
    assert result["timed_out"] is False
    assert any(f["kind"] == "approval_resolved" and f["decision"] == "allow" for f in frames)


def test_approval_always_marks_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    result: dict = {}
    thread = threading.Thread(target=lambda: result.update(service.request_approval(
        session_id="s1", task_id="t1", tool="write_file",
        arguments={"path": "a.py"}, risk="write", reason="需要写入",
        on_event=frames.append, timeout=5.0,
    )))
    thread.start()
    assert _wait_for(lambda: any(f.get("kind") == "approval_request" for f in frames))
    request = next(f for f in frames if f["kind"] == "approval_request")
    service.resolve_approval(request["request_id"], "always")
    thread.join(timeout=2.0)
    assert result["decision"] == "always"


def test_approval_timeout_auto_denies(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    started = time.monotonic()
    verdict = service.request_approval(
        session_id="s1", task_id="t1", tool="write_file",
        arguments={"path": "a.py"}, risk="write", reason="需要写入",
        on_event=frames.append, timeout=0.3,
    )
    assert verdict["decision"] == "deny"
    assert verdict["timed_out"] is True
    assert 0.2 <= time.monotonic() - started < 3.0
    resolved = next(f for f in frames if f["kind"] == "approval_resolved")
    assert resolved["decision"] == "deny" and resolved["timed_out"] is True


def test_approval_cancel_exits_fast(tmp_path: Path) -> None:
    service = _service(tmp_path)
    cancel = threading.Event()
    frames: list[dict] = []
    box: dict = {}
    thread = threading.Thread(target=lambda: box.update(service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "sleep 5"}, risk="exec", reason="x",
        on_event=frames.append, cancel_event=cancel, timeout=30.0,
    )))
    thread.start()
    time.sleep(0.1)
    cancel.set()
    thread.join(timeout=2.0)
    assert box["decision"] == "deny"
    assert box["cancelled"] is True


def test_similar_inflight_calls_merge_into_one_prompt(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    results: list[dict] = []
    lock = threading.Lock()

    def worker() -> None:
        verdict = service.request_approval(
            session_id="s1", task_id="t1", tool="bash",
            arguments={"command": "make all"}, risk="exec", reason="x",
            on_event=lambda e: frames.append(e), timeout=5.0,
        )
        with lock:
            results.append(verdict)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    # Both threads park on the identical merge_key → exactly one pending group.
    assert _wait_for(lambda: len(service._approval_groups) == 1)
    time.sleep(0.1)  # give the second worker a beat to merge in
    with service._approval_guard:
        assert len(service._approval_groups) == 1, "identical calls must merge"
        request_id = next(iter(service._approval_groups))
        group = service._approval_groups[request_id]
        assert len(group.waiters) >= 1
    service.resolve_approval(request_id, "allow")
    for t in threads:
        t.join(timeout=3.0)
    assert len(results) == 2
    assert all(r["decision"] == "allow" for r in results)
    # Only one prompt was shown to the user for two identical calls.
    assert len([f for f in frames if f["kind"] == "approval_request"]) == 1


def test_resolve_unknown_is_noop(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert service.resolve_approval("missing", "allow")["resolved"] is False


def test_resolve_rejects_bad_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError):
        service.resolve_approval("nope", "maybe")


def test_deny_all_approvals_unblocks_waiters(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    box: dict = {}
    thread = threading.Thread(target=lambda: box.update(service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "make"}, risk="exec", reason="x",
        on_event=frames.append, timeout=30.0,
    )))
    thread.start()
    assert _wait_for(lambda: any(f.get("kind") == "approval_request" for f in frames))
    service._deny_all_approvals()
    thread.join(timeout=2.0)
    assert box["decision"] == "deny"
    assert service._approval_groups == {}


def test_preview_redacts_secrets(tmp_path: Path) -> None:
    service = _service(tmp_path)
    preview = service._approval_preview(
        "bash", {"command": "export MINICC_API_KEY=sk-abcdefgh12345678 && make"}
    )
    assert "sk-abcdefgh12345678" not in preview
    assert "REDACTED" in preview
