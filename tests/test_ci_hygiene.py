"""M4-T8: CI hygiene guards.

These pin the config-level fixes so they cannot silently regress: httpx is a
declared dev dependency (not a transitive lucky pull-in), pytest reports pass
counts + warnings (-ra), the JUnit artifact and `pip check` are wired, both eval
jobs exist (PR fake-provider flow gate + nightly real-key gated run), and every
checked-in Playwright suite — including codex_smoke.mjs, which the roadmap
wrongly flagged for deletion — actually has a runner and executes in CI.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _ci_text() -> str:
    return (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _package_json() -> dict:
    return json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))


def _nightly_gates() -> set[str]:
    """The metrics the nightly job actually thresholds, read out of the workflow.

    Scoped to the ``eval-nightly`` job block rather than the whole file: the PR
    job asserts its flow invariants in an inline python block, not with ``--gate``,
    and a future PR gate must not silently widen what this door reconciles.
    """
    ci = _ci_text()
    start = ci.index("  eval-nightly:")
    rest = ci[start + len("  eval-nightly:"):]
    following = re.search(r"^  \S", rest, re.M)
    block = rest[: following.start()] if following else rest
    return set(re.findall(r"--gate\s+([A-Za-z0-9_]+)", block))


def test_httpx_is_declared_dev_dependency():
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    assert any(entry.split("[")[0].strip().lower().startswith("httpx") for entry in dev), dev


def test_wheel_is_declared_because_packaging_builds_in_process():
    """The packaging tests build a wheel with setuptools' build_meta in-process.

    They therefore need the ``bdist_wheel`` command in the *test* environment,
    and GitHub's Python 3.11 image ships setuptools older than 70.1, which does
    not vendor it - so both CI legs errored with "invalid command 'bdist_wheel'"
    while the development machine passed on an incidentally installed ``wheel``.
    Declared (not relied upon transitively), and pinned by this gate so it cannot
    be dropped again without a red test.
    """
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    assert any(entry.split("[")[0].strip().lower().startswith("wheel") for entry in dev), dev


def test_pytest_addopts_reports_summary_not_quiet():
    addopts = _pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "-ra" in addopts
    assert addopts.strip() != "-q"  # the old value hid the warnings summary


def test_ci_installs_dev_extra_and_runs_pip_check():
    ci = _ci_text()
    assert 'pip install -e ".[dev]"' in ci
    assert "pip check" in ci


def test_ci_captures_junit_artifact():
    ci = _ci_text()
    assert "--junitxml=" in ci
    assert "upload-artifact" in ci
    assert "pytest-junit-" in ci


def test_ci_declares_pr_and_nightly_eval_jobs():
    ci = _ci_text()
    assert "eval-pr:" in ci and "eval-nightly:" in ci
    # nightly is schedule/dispatch only so PRs never burn real API budget
    assert "schedule:" in ci and "workflow_dispatch:" in ci
    assert "secrets.MINICC_API_KEY" in ci
    # PR gate uses the fake provider and gates flow, not accuracy
    assert 'MINICC_FAKE_PROVIDER: "1"' in ci
    assert "--suite behavior --run" in ci
    # nightly applies absolute gates via compare and emits JUnit
    assert "--suite v2 --run" in ci
    assert "benchmarks compare" in ci
    assert "--gate pass_at_1>=" in ci
    assert "--gate grading_coverage>=" in ci
    assert "--gate latency_p95_ms<=" in ci
    assert "--gate false_completion_rate<=" in ci, (
        "batch 181 added this gate because the tracking table's 恒 0 row had no reader "
        "on a real run; dropping it puts that row back to prose"
    )
    assert "--gate grading_refusal_count<=" in ci, (
        "M8-T182: a refusal is never a legitimate outcome, so the nightly floors it at "
        "zero; grading_coverage>=0.9 alone lets up to 10% of a run go unjudged silently"
    )
    assert "--junit-out" in ci


def test_every_gate_metric_declares_who_pins_its_floor():
    """M8-T182: "the nightly job pins its own floors" is now a checked claim.

    For ninety-odd batches the ``GATE_METRICS`` comment in bench_compare promised
    that the nightly job pins floors for the bad-things counts "in the workflow
    file". Measured at batch 210: the nightly pinned four floors - pass_at_1,
    grading_coverage, latency_p95_ms, false_completion_rate - and neither
    ``grading_refusal_count`` nor ``reviewer_false_negative_count`` was one of
    them. A comment that describes the deciding path is a claim about the
    deciding path, so the claim gets a door instead of a reader.

    Two things have to hold: the table covers the vocabulary exactly (a metric
    nobody decided about cannot pass as decided), and every row that names the
    nightly is true of the workflow file. A metric with no floor has to say why,
    because "no floor" is a decision and an undeclared one is how the promise
    drifted in the first place.
    """
    from minicc.bench_compare import GATE_FLOORS, GATE_METRICS

    assert set(GATE_FLOORS) == set(GATE_METRICS), (
        "GATE_FLOORS must carry exactly one row per GATE_METRICS entry; undecided: "
        f"{sorted(set(GATE_METRICS) - set(GATE_FLOORS))}; stale: "
        f"{sorted(set(GATE_FLOORS) - set(GATE_METRICS))}"
    )
    for metric, owner in sorted(GATE_FLOORS.items()):
        assert owner.strip(), f"{metric} names no floor owner at all"
        if not owner.startswith("nightly"):
            assert owner.startswith("unfloored:"), (
                f"{metric} names no nightly floor, so its row must say why "
                f"('unfloored: <reason>'); got {owner!r}"
            )
    # The reconciliation runs both ways. "Table says nightly, workflow has no
    # --gate" is the drift that produced the false comment; "workflow gates it,
    # table says nobody does" is the same lie in the other direction, and a
    # reader consulting the table would plan around a floor that does not exist.
    claimed = {metric for metric, owner in GATE_FLOORS.items() if owner.startswith("nightly")}
    actual = _nightly_gates()
    assert actual == claimed, (
        f"the nightly thresholds {sorted(actual)} but GATE_FLOORS records "
        f"{sorted(claimed)}; promised-but-absent={sorted(claimed - actual)}, "
        f"present-but-undeclared={sorted(actual - claimed)}"
    )


def test_pr_eval_gate_names_false_completion_rate():
    """The tracking table calls false_completion_rate 恒 0 and a named CI metric.

    Measured at batch 180: it was neither. The metric is computed, and two unit cells
    pin its arithmetic (0.5 for a constructed report, None when nothing was gradable),
    but the PR gate asserted only the two adjacent metrics - so a regression in the
    completion judgement had no named CI reader at all.

    The value the PR gate asserts is **1.0**, not 0, and that was measured rather than
    assumed: with the fake provider every task completes and none does the work, so
    every completion is a false one (12/12 on the behaviour suite). My first version
    asserted 0 on the reasoning that the table says 恒 0, and CI went red - the table's
    0 belongs to real runs. In this gate the useful invariant is the other direction:
    if a task were graded as passed with the fake provider having done nothing, the
    grader has gone vacuous and the rate drops below 1.0.
    """
    ci = _ci_text()
    assert 'm["false_completion_rate"] == 1.0' in ci, (
        "the PR eval gate no longer names false_completion_rate with the value this "
        "provider actually produces; the tracking table's row would go back to prose"
    )
    assert '"false_completion_rate"' in ci.split("ok = (")[0], (
        "the gate should print the metric it asserts, otherwise a red run does not say "
        "what the reading was"
    )


def test_every_playwright_suite_has_a_runner_and_runs_in_ci():
    scripts = _package_json()["scripts"]
    # codex_smoke.mjs and zombie_spawn_smoke.mjs previously had no runner.
    assert scripts["test:codex"] == "node tests/codex_smoke.mjs"
    assert scripts["test:zombie"] == "node tests/zombie_spawn_smoke.mjs"
    assert scripts["test:game"] == "node tests/game_upgrade_smoke.mjs"
    arcade = scripts["test:arcade"]
    for suite in ("test:game", "test:codex", "test:zombie"):
        assert suite in arcade
    ci = _ci_text()
    assert "npm run test:arcade" in ci
    assert "node --check tests/codex_smoke.mjs" in ci


def test_codex_smoke_not_deleted():
    # Premise correction: the roadmap claimed codex_smoke.mjs was an orphan
    # referencing a non-existent file and should be deleted. It is a real,
    # passing 101-line Playwright suite, so it is wired into CI instead.
    assert (REPO_ROOT / "tests" / "codex_smoke.mjs").is_file()
    assert (REPO_ROOT / "tests" / "zombie_spawn_smoke.mjs").is_file()
