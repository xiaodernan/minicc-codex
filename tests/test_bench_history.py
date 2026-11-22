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


def test_filters_narrow_the_rollup_without_rewriting_the_file(tmp_path: Path) -> None:
    rows = [
        {"ts": "2026-11-17T10:00:00Z", "suite": "v2", "kind": "task", "task_id": "a", "score": 0.5, "elapsed_ms": 100},
        {"ts": "2026-11-18T10:00:00Z", "suite": "v2", "kind": "suite_run", "task_id": "*", "score": 0.9, "elapsed_ms": 900},
        {"ts": "2026-11-19T10:00:00Z", "suite": "behavior", "kind": "task", "task_id": "b", "score": 1.0, "elapsed_ms": 300},
    ]
    for row in rows:
        bh.append_entry(tmp_path, row, allow_changes=True)

    by_suite = bh.read_history(tmp_path, suite="behavior")
    assert by_suite["count"] == 1
    assert by_suite["total_lines_matched"] == 1
    assert by_suite["entries"][0]["task_id"] == "b"
    assert by_suite["filters"] == {"suite": "behavior", "kind": None, "window_days": None}

    by_kind = bh.read_history(tmp_path, kind="suite_run")
    assert by_kind["count"] == 1
    assert by_kind["mean_score"] == pytest.approx(0.9)

    from datetime import datetime, timezone

    recent = bh.read_history(
        tmp_path,
        window_days=2,
        now=datetime(2026, 11, 21, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert recent["count"] == 1
    assert [item["task_id"] for item in recent["entries"]] == ["b"]

    everything = bh.read_history(tmp_path)
    assert everything["count"] == 3


def test_parse_window_days_accepts_the_blueprint_spellings() -> None:
    assert bh.parse_window_days("last-30d") == 30
    assert bh.parse_window_days("30d") == 30
    assert bh.parse_window_days("30") == 30
    assert bh.parse_window_days("LAST-7D") == 7
    assert bh.parse_window_days("") is None
    assert bh.parse_window_days("garbage") is None
    assert bh.parse_window_days(None) is None


def test_a_window_spelling_outside_ascii_digits_degrades_instead_of_raising() -> None:
    """`"²".isdigit()` is true and `int("²")` raises, and `?window=` is a query parameter."""
    for raw in ("²", "³", "₁₂₃", "１２３", "٣", "①", "3 0", "-1", "3.0", "0x10", "  ", "٣٠"):
        assert bh.parse_window_days(raw) is None, raw
    assert bh.parse_window_days("0") == 0
    assert bh.parse_window_days(" last-90d ") == 90
    out = bh.read_history(Path("."), window_days=bh.parse_window_days("²"))
    assert out["state"] in {"present", "absent", "empty", "unreadable", "filtered_empty", "capped"}
    assert out["filters"]["window_days"] is None


# --- M8-T1299: one value was doing five jobs -------------------------------
#
# `read_history` used to answer `present: bool(window)`. That single boolean
# merged five different facts — the file is not there, the file could not be
# read, the file is there but empty, the file has rows and the filter kept none
# of them, and the file has rows and the cap kept none — so a caller that only
# reads `present` cannot tell "run the suite" from "widen the window", and the
# two absent/unreadable branches did not even return the same keys as `present`.


def _three_rows(workspace: Path) -> None:
    stamps = ("2026-11-17T10:00:00Z", "2026-11-17T11:00:00Z", "2026-11-17T12:00:00Z")
    for offset, stamp in enumerate(stamps):
        bh.append_entry(workspace, _selftest_entry(stamp, 0.5 + offset / 10, 900 + offset),
                        allow_changes=True)


def _history_file(workspace: Path) -> Path:
    target = workspace / ".minicc" / "bench_history.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def test_a_missing_file_says_absent(tmp_path: Path) -> None:
    out = bh.read_history(tmp_path)
    assert out["state"] == "absent"
    assert out["present"] is False
    assert out["total_lines"] == 0
    assert out["reason"].strip()


def test_an_empty_file_is_not_called_absent(tmp_path: Path) -> None:
    _history_file(tmp_path).write_text("", encoding="utf-8")
    out = bh.read_history(tmp_path)
    assert out["state"] == "empty"
    assert out["present"] is False
    assert out["total_lines"] == 0
    assert out["reason"].strip()


def test_a_filter_that_kept_nothing_still_reports_the_rows_the_file_has(tmp_path: Path) -> None:
    _three_rows(tmp_path)
    out = bh.read_history(tmp_path, kind="never_recorded")
    assert out["state"] == "filtered_empty"
    assert out["present"] is False
    assert out["count"] == 0
    # the fact the panel needs, and the one `present` used to destroy:
    assert out["total_lines"] == 3
    assert out["filters"] == {"suite": None, "kind": "never_recorded", "window_days": None}
    assert out["reason"].strip()


def test_a_cap_of_zero_rows_is_not_a_present_history(tmp_path: Path) -> None:
    _three_rows(tmp_path)
    out = bh.read_history(tmp_path, limit=0)
    assert out["state"] == "capped"
    assert out["present"] is False
    assert out["count"] == 0
    assert out["total_lines"] == 3
    assert out["total_lines_matched"] == 3
    assert out["reason"].strip()


def test_a_file_that_cannot_be_read_says_so_instead_of_saying_it_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _three_rows(tmp_path)
    real = Path.read_text

    def refuse(self, *args, **kwargs):  # noqa: ANN002, ANN003 - stand-in for a disk fault
        raise OSError("simulated disk fault")

    monkeypatch.setattr(Path, "read_text", refuse)
    try:
        out = bh.read_history(tmp_path)
    finally:
        monkeypatch.setattr(Path, "read_text", real)
    assert out["state"] == "unreadable"
    assert out["present"] is False
    # an unreadable file is not an empty one: the row count stays unknown, never 0-by-accident
    assert out["total_lines"] is None
    assert "simulated disk fault" in out["reason"]


def test_a_window_of_real_rows_is_present_and_carries_no_reason(tmp_path: Path) -> None:
    _three_rows(tmp_path)
    out = bh.read_history(tmp_path)
    assert out["state"] == "present"
    assert out["present"] is True
    assert out["count"] == 3
    assert out["total_lines"] == 3
    assert out["reason"] == ""


def test_all_five_states_answer_with_the_same_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers: dict[str, dict] = {"absent": bh.read_history(tmp_path)}
    _history_file(tmp_path).write_text("", encoding="utf-8")
    answers["empty"] = bh.read_history(tmp_path)
    _three_rows(tmp_path)
    answers["present"] = bh.read_history(tmp_path)
    answers["filtered_empty"] = bh.read_history(tmp_path, kind="never_recorded")
    answers["capped"] = bh.read_history(tmp_path, limit=0)
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text",
                        lambda self, *a, **k: (_ for _ in ()).throw(OSError("simulated disk fault")))
    try:
        answers["unreadable"] = bh.read_history(tmp_path)
    finally:
        monkeypatch.setattr(Path, "read_text", real)

    shape = frozenset(answers["present"])
    drift = {name: sorted(shape ^ frozenset(answer)) for name, answer in answers.items()
             if frozenset(answer) != shape}
    assert not drift, f"states that answer with a different key set: {drift}"
    for name in ("absent", "empty", "filtered_empty", "capped", "unreadable"):
        assert answers[name]["state"] == name
        assert answers[name]["present"] is False
        assert answers[name]["entries"] == []
        assert answers[name]["mean_score"] is None
        assert answers[name]["mean_elapsed_ms"] is None
        assert answers[name]["window_from"] is None
        assert answers[name]["window_to"] is None
        assert answers[name]["reason"].strip(), f"{name} must say why"

