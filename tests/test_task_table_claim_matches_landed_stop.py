"""The task table's M8-T19 row claimed a stop strategy that had already landed.

M8-T53 (commit 0185533) replaced the observe-only repeated-verdict event with
an early stop and shipped the false-positive guard with it. Three batches
later the roadmap's task-status table still said 「观测已落地，停止策略未动」
and named ``max_completion_continues`` as the place where stopping happened.
Code, tests and batch records all agreed with each other; only the table
disagreed — and the table had no reader, so nothing went red.

This gate binds that row to the code it describes, in both directions:

* the row must be ✅ and must name the landing batch and commit — a 🟡 row
  describing shipped behaviour is exactly the drift this catches;
* the behaviour the row leans on must still exist: the repeated-verdict
  trace carries ``action="stop"``, and both the stop and its false-positive
  guard still exist as named tests in the file the row points at;
* no row in the table may still claim the strategy is 「未动」.

Deliberately narrow: batch 188 rejected a permanent file:line/identifier
census over these rows because historical line numbers drift by design. This
checks one claim against one behaviour, not the table's spelling.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"
WEB_SOURCE = REPO_ROOT / "minicc" / "web.py"
CORE_AGENT_TESTS = REPO_ROOT / "tests" / "test_core_agent.py"

ROW_ID = "M8-T19"
LANDED_BATCH = "M8-T53"
LANDED_COMMIT = "0185533"
STOP_TEST = "test_a_repeated_verdict_with_no_new_activity_stops_before_burning_the_cap"
GUARD_TEST = "test_a_repeated_verdict_that_came_with_new_tool_activity_is_not_a_stall"
STALE_CLAIM = "停止策略未动"


def _table_rows() -> list[list[str]]:
    """The task-status table's rows, as cells (first milestone table excluded)."""
    rows: list[list[str]] = []
    for line in ROADMAP.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("| M"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 3 and cells[0].split(" ")[0].startswith("M"):
            rows.append(cells)
    return rows


def _row(task_id: str) -> list[str]:
    for cells in _table_rows():
        if cells[0].split(" ")[0] == task_id:
            return cells
    raise AssertionError(f"roadmap task table has no row for {task_id}")


def test_the_stop_policy_row_names_the_batch_that_landed_it() -> None:
    row = _row(ROW_ID)
    status, body = row[1], " ".join(row[2:])
    assert status == "✅", f"{ROW_ID} is still {status!r}: the early stop landed in {LANDED_BATCH}"
    assert LANDED_BATCH in body, f"{ROW_ID} row must name the landing batch {LANDED_BATCH}"
    assert LANDED_COMMIT in body, f"{ROW_ID} row must name the landing commit {LANDED_COMMIT}"
    assert "test_core_agent.py" in body, f"{ROW_ID} row must name the test file that guards the stop"


def test_no_row_still_claims_the_stop_strategy_is_unchanged() -> None:
    stale = [cells[0].split(" ")[0] for cells in _table_rows() if STALE_CLAIM in "".join(cells)]
    assert not stale, f"rows still claiming the strategy is unchanged: {stale}"


def test_the_repeated_verdict_trace_still_carries_the_stop_action() -> None:
    source = WEB_SOURCE.read_text(encoding="utf-8")
    assert "completion_verdict_repeated" in source, "the repeated-verdict event is gone from web.py"
    assert '"action": "stop"' in source, (
        "the repeated-verdict event no longer carries action=stop — the row's claim is stale again"
    )


def test_the_stop_and_its_false_positive_guard_still_exist_as_named_tests() -> None:
    source = CORE_AGENT_TESTS.read_text(encoding="utf-8")
    for name in (STOP_TEST, GUARD_TEST):
        assert f"def {name}(" in source, f"{name} vanished from {CORE_AGENT_TESTS.name}"


def test_the_commit_the_row_names_exists_in_this_repository() -> None:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-t", LANDED_COMMIT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0 and proc.stdout.strip() == "commit", (
        f"{ROW_ID} row names {LANDED_COMMIT}, which is not a commit in this repository"
    )
