"""M8-T709 -- `minicc --stats` read-only operational inventory."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from minicc.main import main
from minicc.stats import gather
from minicc.task_store import TaskStore


def _snap(task_id: str, status: str) -> dict:
    return {
        "task_id": task_id,
        "session_id": "s",
        "created_at_epoch": time.time(),
        "created_at": "2026-11-09T00:00:00Z",
        "workspace_path": "/tmp/ws",
        "status": status,
        "prompt": "probe",
        "preview": "probe",
        "allow_changes": False,
        "allow_network": False,
        "stream_text": "",
        "events": [],
    }


def test_stats_on_empty_workspace(tmp_path: Path) -> None:
    report = gather(tmp_path)
    assert report["state_dir_present"] is False
    assert report["disk_bytes"] == 0
    assert report["audit"]["present"] is False
    assert report["tasks"]["present"] is False
    assert sum(report["tasks"]["by_status"].values()) == 0
    assert report["sessions"]["count"] == 0
    assert report["sessions"]["messages"] == 0


def test_stats_audit_lines_and_last_event(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    (state / "audit.jsonl").write_text(
        '{"event": "tool_call", "tool": "read_file"}\n{"event": "task_done", "task_id": "t"}\n',
        encoding="utf-8",
    )
    report = gather(tmp_path)
    assert report["audit"]["present"] is True
    assert report["audit"]["lines"] == 2
    assert report["audit"]["last_event"] == "task_done"
    assert report["disk_bytes"] > 0


def test_stats_audit_corrupt_last_line(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    (state / "audit.jsonl").write_text(
        '{"event": "tool_call"}\nnot-json\n', encoding="utf-8"
    )
    report = gather(tmp_path)
    assert report["audit"]["present"] is True
    assert report["audit"]["lines"] == 2
    assert report["audit"]["last_event"] == "<unparseable audit line>"


def test_stats_task_counts(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    store = TaskStore(state / "tasks.sqlite3")
    store.upsert(_snap("t1", "queued"))
    store.upsert(_snap("t2", "queued"))
    store.upsert(_snap("t3", "failed"))
    report = gather(tmp_path)
    tasks = report["tasks"]
    assert tasks["present"] is True
    assert tasks["total"] == 3
    assert tasks["by_status"]["queued"] == 2
    assert tasks["by_status"]["failed"] == 1
    assert tasks["by_status"]["completed"] == 0
    assert tasks["other"] == 0


def test_stats_cli_json_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    rc = main(["--stats", "--json", "--workspace", str(tmp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "workspace",
        "state_dir_present",
        "audit",
        "tasks",
        "sessions",
        "disk_bytes",
    }
    assert payload["state_dir_present"] is False


def test_json_without_stats_or_doctor_is_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    rc = main(["--json", "--workspace", str(tmp_path)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "--json" in out
