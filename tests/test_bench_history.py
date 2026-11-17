# -*- coding: utf-8 -*-
"""M8-T1199 — bench history: the two truths the file can tell, tested."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import minicc.bench_history as bh


def _selftest_entry(ts: str = "2026-11-17T10:00:00Z", score: float = 0.9, elapsed_ms: int = 1200) -> dict:
    return {"ts": ts, "suite": "v2", "kind": "file_contract", "task_id": "sum_two_numbers",
            "score": score, "elapsed_ms": elapsed_ms, "provider": "fake-provider",
            "deterministic": True}


def test_absent_file_reports_no_history_yet(tmp_path: Path) -> None:
    out = bh.read_history(tmp_path)
    assert out["present"] is False
    assert out["count"] == 0
    assert "v2" in out["reason"]


def test_empty_file_reports_no_history(tmp_path: Path) -> None:
    target = tmp_path / ".minicc" / "bench_history.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text("", encoding="utf-8")
    out = bh.read_history(tmp_path)
    assert out["present"] is False
    assert out["count"] == 0


def test_append_then_read_reports_count_and_mean(tmp_path: Path) -> None:
    entries = [_selftest_entry("2026-11-17T10:00:00Z", 0.8, 900),
               _selftest_entry("2026-11-17T11:00:00Z", 1.0, 300),
               _selftest_entry("2026-11-17T12:00:00Z", 0.6, 1500)]
    for e in entries:
        bh.append_entry(tmp_path, e, allow_changes=True)
    out = bh.read_history(tmp_path)
    assert out["present"] is True
    assert out["count"] == 3
    assert out["total_lines_matched"] == 3
    assert out["mean_score"] == pytest.approx(0.8, abs=0.001)
    assert out["mean_elapsed_ms"] == pytest.approx(900.0)


def test_unparsable_lines_are_skipped_not_fatal(tmp_path: Path) -> None:
    target = tmp_path / ".minicc" / "bench_history.jsonl"
    target.parent.mkdir(parents=True)
    good = json.dumps(_selftest_entry(), ensure_ascii=False)
    target.write_text("\nnope\n" + good + "\n{not json}\n" + good + "\n", encoding="utf-8")
    out = bh.read_history(tmp_path)
    assert out["present"] is True
    assert out["count"] == 2
    assert out["skipped_lines"] >= 2


def test_limit_defaults_but_is_overridable(tmp_path: Path) -> None:
    for i in range(5):
        bh.append_entry(tmp_path, _selftest_entry(ts=f"2026-11-{10 + i:02d}T10:00:00Z", score=float(i)),
                        allow_changes=True)
    out = bh.read_history(tmp_path, limit=2)
    assert out["count"] == 2
    assert out["total_lines_matched"] == 5


def test_append_respects_allow_changes(tmp_path: Path) -> None:
    out = bh.append_entry(tmp_path, _selftest_entry(), allow_changes=False)
    assert out["recorded"] is False
    assert not (tmp_path / ".minicc" / "bench_history.jsonl").exists()


def test_append_refuses_missing_required_keys(tmp_path: Path) -> None:
    out = bh.append_entry(tmp_path, {"ts": "x", "suite": "v2"}, allow_changes=True)
    assert out["recorded"] is False
    assert "missing" in out["reason"]


def test_cli_append_and_show(tmp_path: Path) -> None:
    entry = json.dumps(_selftest_entry())
    for line in [entry, json.dumps(_selftest_entry("2026-11-17T09:00:00Z", 0.5, 500))]:
        proc = __import__("subprocess").run(
            [sys.executable, "-m", "minicc.bench_history", "--workspace", str(tmp_path),
             "--append", line, "--allow-changes"],
            capture_output=True, check=False,
        )
        assert proc.returncode in (0, 1)
    out = bh.read_history(tmp_path)
    assert out["count"] == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))

def test_ingest_absent_report_is_honest_not_fatal(tmp_path: Path) -> None:
    out = bh.ingest_report(tmp_path, tmp_path / "no-such-report.json", allow_changes=True)
    assert out["recorded"] is False
    assert "not found" in out["reason"]


def test_ingest_translates_suite_run_and_task_rows(tmp_path: Path) -> None:
    report = {
        "suite_version": "v2-1",
        "metrics": {"pass_at_1": 0.5, "latency_p50_ms": 800},
        "results": [
            {"task_id": "a", "grader_type": "file_contract", "passed": True,  "latency_ms": 600},
            {"task_id": "b", "grader_type": "file_contract", "passed": False, "latency_ms": 1000},
            {"task_id": "c", "grader_type": "command_contract", "passed": None, "latency_ms": 200},
        ],
    }
    report_path = tmp_path / "evaluation.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    out = bh.ingest_report(tmp_path, report_path, allow_changes=True)
    assert out["recorded"] is True
    assert out["entries"] == 4
    history = bh.read_history(tmp_path)
    assert history["count"] == 4
    scores = [e["score"] for e in history["entries"]]
    assert 1.0 in scores and 0.0 in scores
