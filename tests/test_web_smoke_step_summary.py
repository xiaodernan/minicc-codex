"""Harness failures keep their actual coverage on the CI job page."""

from __future__ import annotations

import os
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
LOST_LOG = (
    "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n"
    "SMOKE_FAILURE_CODE=HARNESS_LOST\n"
    "HARNESS_LOST: the server stopped answering mid-suite\n"
)
BROWSER_LOG = (
    "SMOKE_FAILURE_CODE=HARNESS_BROWSER_MISSING\n"
    "HARNESS_BROWSER_MISSING: no browser assertions ran\n"
)
CAUGHT_LOG = "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\nmutation caught\n"
PRODUCT_CODE = "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n"


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
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        timeout=60,
        check=False,
    )
    return result, summary.read_text(encoding="utf-8")


def _run_verdict(tmp_path, log_text: str, exit_code: int = 3):
    log = tmp_path / "verdict.log"
    log.write_text(log_text, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(VERDICT),
            "--exit-code", str(exit_code),
            "--log", str(log),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        timeout=60,
        check=False,
    )


def test_harness_absent_appends_a_marked_block(tmp_path) -> None:
    result, summary = _run(tmp_path, ABSENT_LOG, exit_code=3, step_name="Web smoke")
    assert result.returncode == 0, result.stderr
    assert "# Job summary\n" in summary, "the reporter must append, not overwrite"
    assert "Web smoke: no harness - zero tests ran" in summary
    assert "HARNESS_UNREACHABLE" in summary
    assert "zero suites ran" in summary
    assert "go check" not in summary or "web server" in summary


def test_harness_lost_reports_partial_coverage(tmp_path) -> None:
    result, summary = _run(tmp_path, LOST_LOG, exit_code=3, step_name="Web smoke")
    assert result.returncode == 0, result.stderr
    assert "Web smoke: harness lost - partial coverage" in summary
    assert "HARNESS_LOST" in summary
    assert "partial coverage" in summary
    assert "zero tests ran" not in summary
    assert "restart the web server" in summary


def test_missing_browser_reports_no_browser_assertions(tmp_path) -> None:
    result, summary = _run(tmp_path, BROWSER_LOG, exit_code=3, step_name="Focused frontend")
    assert result.returncode == 0, result.stderr
    assert "Focused frontend: browser missing - no browser assertions ran" in summary
    assert "HARNESS_BROWSER_MISSING" in summary
    assert "no browser assertions ran" in summary
    assert "zero tests ran" not in summary
    assert "npx playwright install chromium" in summary


def test_a_real_failure_does_not_get_the_harness_block(tmp_path) -> None:
    result, summary = _run(tmp_path, CAUGHT_LOG, exit_code=1)
    assert result.returncode == 0
    assert summary == "# Job summary\n", "a step that ran its assertions gets no warning"


def test_missing_log_is_not_fatal(tmp_path) -> None:
    result, summary = _run(tmp_path, None, exit_code=3)
    assert result.returncode == 0, "an always() reporter must not fail the job"
    assert summary == "# Job summary\n"


def test_product_codes_cannot_mask_a_harness_failure(tmp_path) -> None:
    for log_text, heading in (
        (ABSENT_LOG, "no harness - zero tests ran"),
        (LOST_LOG, "harness lost - partial coverage"),
        (BROWSER_LOG, "browser missing - no browser assertions ran"),
    ):
        for combined in (PRODUCT_CODE + log_text, log_text + PRODUCT_CODE):
            result, summary = _run(tmp_path, combined, exit_code=3)
            assert result.returncode == 0, result.stderr
            assert heading in summary, combined


def test_reporter_reuses_the_verdict_detectors() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "from web_smoke_verdict import" in helper
    for name in ("harness_absent", "harness_lost", "harness_browser_missing"):
        assert name in helper
    verdict = VERDICT.read_text(encoding="utf-8")
    for name in ("harness_absent", "harness_lost", "harness_browser_missing"):
        assert f"def {name}(" in verdict


def test_all_three_ci_jobs_wire_the_reporter() -> None:
    ci = CI.read_text(encoding="utf-8")
    js_check = ci.split("  js-check:", 1)[1].split("\n  web-smoke:", 1)[0]
    assert "actions/setup-python@v5" in js_check, "the focused frontend reporter needs Python"
    assert ci.count("scripts/web_smoke_step_summary.py") == 3
    assert ci.count("$GITHUB_STEP_SUMMARY") == 3
    for name in (
        "Report web smoke harness status",
        "Report mutation harness status",
        "Report focused frontend harness status",
    ):
        idx = ci.index(f"name: {name}")
        block = ci[idx:idx + 500]
        assert "if: always()" in block, f"{name} is not an always() step"
    assert 'echo "$rc" > web-smoke.rc' in ci
    assert 'echo "$rc" > web-smoke-mutation.rc' in ci
    assert 'echo "$rc" > frontend-contracts.rc' in ci
    assert "frontend-contracts.log" in ci
    assert "if [ -f frontend-contracts.rc ]" in ci
    assert "(\n            set -e\n            npm run test:optimization" in ci


def test_extraction_matches_each_verdict_sentence(tmp_path) -> None:
    for log_text, sentence in (
        (ABSENT_LOG, "zero suites ran, so this step tested nothing"),
        (LOST_LOG, "the suite ran partway, so this step has partial coverage"),
        (BROWSER_LOG, "no browser assertions ran"),
    ):
        result, summary = _run(tmp_path, log_text, exit_code=3)
        assert result.returncode == 0
        assert sentence in summary


def test_mutation_verdict_keeps_browser_missing_on_the_harness_plane(tmp_path) -> None:
    result = _run_verdict(tmp_path, PRODUCT_CODE + BROWSER_LOG, exit_code=3)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "browser missing" in result.stdout
    assert "no browser assertions ran" in result.stdout
    assert "mutation caught" not in result.stdout
