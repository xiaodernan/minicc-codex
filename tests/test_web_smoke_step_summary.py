"""M8-T1306: a smoke step that ran nothing says so on the CI job page.

The verdict (M8-T1304) can tell ``HARNESS_UNREACHABLE`` from a caught or missed
mutation, but it only printed into the log; CI showed a red step. This gate
checks the ``if: always()`` reporter appends one marked block to the GitHub job
summary, never changes the job's outcome, and reuses the verdict's detector
instead of growing a second copy that could drift.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "web_smoke_step_summary.py"
VERDICT = REPO_ROOT / "scripts" / "web_smoke_verdict.py"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"

ABSENT_LOG = (
    "some preamble\n"
    "SMOKE_FAILURE_CODE=HARNESS_UNREACHABLE\n"
    "HARNESS_UNREACHABLE: the server this smoke drives is not answering\n"
)
CAUGHT_LOG = "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\nmutation caught\n"


def _run(tmp_path, log_text: str | None, exit_code: int = 3, step_name: str = "Web smoke"):
    log = tmp_path / "smoke.log"
    if log_text is not None:
        log.write_text(log_text, encoding="utf-8")
    summary = tmp_path / "summary.md"
    summary.write_text("# Job summary\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "--exit-code", str(exit_code),
            "--log", str(log),
            "--summary", str(summary),
            "--step-name", step_name,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        timeout=60,
        check=False,
    )
    return result, summary.read_text(encoding="utf-8")


def test_harness_absent_appends_a_marked_block(tmp_path) -> None:
    result, summary = _run(tmp_path, ABSENT_LOG, exit_code=3, step_name="Web smoke")
    assert result.returncode == 0, result.stderr
    assert "# Job summary\n" in summary, "the reporter must append, not overwrite"
    assert "Web smoke: no harness - zero tests ran" in summary
    assert "HARNESS_UNREACHABLE" in summary
    assert "zero suites ran" in summary
    assert "go check" not in summary or "web server" in summary


def test_a_real_failure_does_not_get_the_harness_block(tmp_path) -> None:
    result, summary = _run(tmp_path, CAUGHT_LOG, exit_code=1)
    assert result.returncode == 0
    assert summary == "# Job summary\n", "a step that ran its assertions gets no warning"


def test_missing_log_is_not_fatal(tmp_path) -> None:
    result, summary = _run(tmp_path, None, exit_code=3)
    assert result.returncode == 0, "an always() reporter must not fail the job"
    assert summary == "# Job summary\n"


def test_reporter_reuses_the_verdict_detector() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "from web_smoke_verdict import" in helper
    assert "harness_absent" in helper
    assert "HARNESS_CODE" in helper
    verdict = VERDICT.read_text(encoding="utf-8")
    assert "def harness_absent(" in verdict


def test_both_ci_smoke_jobs_wire_the_reporter() -> None:
    ci = CI.read_text(encoding="utf-8")
    # The helper is called from both smoke jobs, each as an always() step writing
    # to GITHUB_STEP_SUMMARY, with the rc persisted from the preceding run step.
    assert ci.count("scripts/web_smoke_step_summary.py") == 2
    assert ci.count("Report web smoke harness status") == 1
    assert ci.count("Report mutation harness status") == 1
    assert ci.count("$GITHUB_STEP_SUMMARY") == 2
    assert "echo \"$rc\" > web-smoke.rc" in ci
    assert "echo \"$rc\" > web-smoke-mutation.rc" in ci
    # Both reporters must be guarded by always(), or a failed smoke step skips them.
    for name in ("Report web smoke harness status", "Report mutation harness status"):
        idx = ci.index(f"name: {name}")
        block = ci[idx:idx + 300]
        assert "if: always()" in block, f"{name} is not an always() step"


def test_extraction_matches_the_verdict_sentence(tmp_path) -> None:
    # The block quotes the verdict's own sentence; if the verdict's wording
    # changes, the job summary still carries the machine-readable core.
    result, summary = _run(tmp_path, ABSENT_LOG, exit_code=3)
    assert result.returncode == 0
    assert "zero suites ran, so this step tested nothing" in summary
