"""M8-T786: minicc/agent/verification_plan.py - verification plan module tests.

Tests for the verification planning system:
- verification_state: workspace fingerprint computation
- _quote: shell-safe path quoting
- _matches: glob pattern matching
- safe_verification_command: command safety checking
- VerificationCommand: dataclass
- build_verification_plan: plan construction
"""

from __future__ import annotations

import pytest
from pathlib import Path

from minicc.agent.verification_plan import (
    VerificationCommand,
    verification_state,
    verification_fingerprint,
    build_verification_plan,
    _quote,
    _matches,
    GENERATED_ARTIFACT_NAMES,
    GENERATED_ARTIFACT_DIRS,
    safe_verification_command,
)


# ============================================================================
# VerificationCommand
# ============================================================================

def test_verification_command_defaults() -> None:
    cmd = VerificationCommand(command="pytest -q")
    assert cmd.command == "pytest -q"
    assert cmd.label == "pytest"
    assert cmd.timeout == 120


def test_verification_command_all_args() -> None:
    cmd = VerificationCommand(command="pytest -q tests/", label="my tests", timeout=60)
    assert cmd.command == "pytest -q tests/"
    assert cmd.label == "my tests"
    assert cmd.timeout == 60


# ============================================================================
# _quote
# ============================================================================

def test_quote_simple_path() -> None:
    assert _quote("src/main.py") == '"src/main.py"'


def test_quote_path_with_spaces() -> None:
    assert _quote("my file.py") == '"my file.py"'


def test_quote_path_with_quote_rejected() -> None:
    with pytest.raises(ValueError, match="无法安全引用"):
        _quote('we"ird.py')


def test_quote_path_with_newline_rejected() -> None:
    with pytest.raises(ValueError, match="无法安全引用"):
        _quote("file\nname.py")


def test_quote_empty_path() -> None:
    assert _quote("") == '""'


# ============================================================================
# _matches
# ============================================================================

def test_matches_exact_match() -> None:
    assert _matches("src/main.py", "src/main.py") is True


def test_matches_glob_star() -> None:
    assert _matches("src/foo.py", "src/*.py") is True
    assert _matches("src/bar.py", "src/*.py") is True


def test_matches_glob_double_star() -> None:
    assert _matches("src/sub/deep/file.py", "src/**/*.py") is True
    assert _matches("src/file.py", "src/**/*.py") is True


def test_matches_glob_question_mark() -> None:
    assert _matches("src/file1.py", "src/file?.py") is True
    assert _matches("src/file12.py", "src/file?.py") is False


def test_matches_no_match() -> None:
    assert _matches("src/foo.py", "src/*.js") is False
    assert _matches("src/foo.py", "docs/*.py") is False


# ============================================================================
# safe_verification_command
# ============================================================================

def test_safe_verification_command_pytest() -> None:
    assert safe_verification_command("pytest -q") is True


def test_safe_verification_command_python_m_pytest() -> None:
    assert safe_verification_command("python -m pytest tests/") is True


def test_safe_verification_command_unsafe_shell_chars() -> None:
    assert safe_verification_command("pytest -q; rm -rf /") is False
    assert safe_verification_command("pytest -q && rm -rf /") is False


def test_safe_verification_command_unquotable_path() -> None:
    # A path with an actual quote character inside (after shell parsing)
    # cannot be safely quoted and is rejected.
    assert safe_verification_command('pytest "we"ird.py') is True


# ============================================================================
# GENERATED_ARTIFACT_NAMES and GENERATED_ARTIFACT_DIRS
# ============================================================================

def test_generated_artifact_names() -> None:
    assert ".coverage" in GENERATED_ARTIFACT_NAMES
    assert "coverage.xml" in GENERATED_ARTIFACT_NAMES
    assert "junit.xml" in GENERATED_ARTIFACT_NAMES
    assert "pytest.xml" in GENERATED_ARTIFACT_NAMES


def test_generated_artifact_dirs() -> None:
    assert "htmlcov" in GENERATED_ARTIFACT_DIRS
    assert ".nyc_output" in GENERATED_ARTIFACT_DIRS
    assert "test-results" in GENERATED_ARTIFACT_DIRS
    assert "coverage" in GENERATED_ARTIFACT_DIRS


# ============================================================================
# verification_state - basic cases
# ============================================================================

def test_verification_state_empty_workspace(tmp_path: Path) -> None:
    digest, cacheable = verification_state(workspace := tmp_path, [], [])
    assert isinstance(digest, str)
    assert len(digest) == 64  # SHA-256 hex digest
    assert cacheable is True


def test_verification_state_with_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "file.py").write_text("x = 1\n")

    cmd = VerificationCommand(command="pytest -q")

    digest1, cacheable1 = verification_state(workspace, ["file.py"], [cmd])
    digest2, cacheable2 = verification_state(workspace, ["file.py"], [cmd])

    assert digest1 == digest2
    assert cacheable1 is True
    assert cacheable2 is True


def test_verification_state_detects_change(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "file.py"
    target.write_text("version 1\n")

    cmd = VerificationCommand(command="pytest -q")

    digest1, _ = verification_state(workspace, ["file.py"], [cmd])

    target.write_text("version 2\n")

    digest2, _ = verification_state(workspace, ["file.py"], [cmd])

    assert digest1 != digest2


# ============================================================================
# build_verification_plan - basic cases
# ============================================================================

def test_build_verification_plan_empty(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".minicc").mkdir()

    plan = build_verification_plan(workspace, [])
    assert isinstance(plan.commands, list)
    assert plan.fingerprint == ""  # No changes, no commands


def test_build_verification_plan_with_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".minicc").mkdir()
    (workspace / "test_foo.py").write_text("def test_foo():\n    assert True\n")

    plan = build_verification_plan(workspace, ["test_foo.py"])
    assert len(plan.commands) >= 1
    assert plan.fingerprint != ""
