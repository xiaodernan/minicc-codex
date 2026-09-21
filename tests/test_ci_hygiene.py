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


def test_httpx_is_declared_dev_dependency():
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    assert any(entry.split("[")[0].strip().lower().startswith("httpx") for entry in dev), dev


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
    assert "--junit-out" in ci


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
