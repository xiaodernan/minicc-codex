"""M8-T798: minicc/agent/check_commands.py - argv splitting and identity normalization tests.

Tests for:
- command_parts: shell-like argv parsing without shell evaluation
- checker_invocation: executable + arguments extraction
- verification_identity: command identity normalization
- PYTHON_TEST_RUNNERS: frozenset of test runner names
"""

from __future__ import annotations

import pytest

from minicc.agent.check_commands import (
    PYTHON_TEST_RUNNERS,
    checker_invocation,
    command_parts,
    verification_identity,
)


# ============================================================================
# PYTHON_TEST_RUNNERS
# ============================================================================

def test_python_test_runners() -> None:
    assert isinstance(PYTHON_TEST_RUNNERS, frozenset)
    assert "pytest" in PYTHON_TEST_RUNNERS
    assert "unittest" in PYTHON_TEST_RUNNERS


# ============================================================================
# command_parts
# ============================================================================

def test_command_parts_simple() -> None:
    assert command_parts("pytest test_foo.py") == ["pytest", "test_foo.py"]


def test_command_parts_single() -> None:
    assert command_parts("pytest") == ["pytest"]


def test_command_parts_empty() -> None:
    assert command_parts("") == []


def test_command_parts_quoted() -> None:
    assert command_parts('pytest "test file with spaces.py"') == ["pytest", "test file with spaces.py"]


def test_command_parts_mixed_quotes() -> None:
    assert command_parts("pytest 'single' \"double\"") == ["pytest", "single", "double"]


def test_command_parts_unclosed_quote() -> None:
    with pytest.raises(ValueError, match="unclosed"):
        command_parts('pytest "unclosed')


def test_command_parts_escaped_quote() -> None:
    assert command_parts('pytest "escaped \\"quote\\" here"') == ["pytest", 'escaped "quote" here']


def test_command_parts_path_slashes() -> None:
    assert command_parts("pytest path/to/test.py") == ["pytest", "path/to/test.py"]


# ============================================================================
# checker_invocation
# ============================================================================

def test_checker_invocation_pytest() -> None:
    executable, arguments = checker_invocation("pytest -m test_foo.py")
    assert executable == "pytest"
    assert arguments == ["-m", "test_foo.py"]


def test_checker_invocation_python_m() -> None:
    executable, arguments = checker_invocation("python -m pytest test_foo.py")
    assert executable == "pytest"
    assert arguments == ["test_foo.py"]


def test_checker_invocation_python3_m() -> None:
    executable, arguments = checker_invocation("python3 -m unittest test_foo")
    assert executable == "unittest"
    assert arguments == ["test_foo"]


def test_checker_invocation_python_flags_stripped() -> None:
    executable, arguments = checker_invocation("python -B -I -m pytest test_foo.py")
    assert executable == "pytest"
    assert arguments == ["test_foo.py"]


def test_checker_invocation_not_python() -> None:
    executable, arguments = checker_invocation("npm test")
    assert executable == "npm"
    assert arguments == ["test"]


def test_checker_invocation_empty() -> None:
    executable, arguments = checker_invocation("")
    assert executable == ""
    assert arguments == []


def test_checker_invocation_exe_suffix() -> None:
    executable, arguments = checker_invocation("pytest.exe test_foo.py")
    assert executable == "pytest"
    assert arguments == ["test_foo.py"]


# ============================================================================
# verification_identity
# ============================================================================

def test_verification_identity_pytest() -> None:
    result = verification_identity("pytest -q test_foo.py")
    assert result[0] == "pytest"
    assert "-q" not in result
    assert "test_foo.py" in result


def test_verification_identity_pytest_verbose() -> None:
    result = verification_identity("pytest -v --verbose test_foo.py")
    assert result[0] == "pytest"
    assert "-v" not in result
    assert "--verbose" not in result


def test_verification_identity_non_python() -> None:
    result = verification_identity("npm test -- --verbose")
    assert result[0] == "npm"
    assert "test" in result
    assert "--verbose" in result


def test_verification_identity_same_command_different_flags() -> None:
    # Same logical command should produce same identity regardless of verbosity flags
    r1 = verification_identity("pytest test_foo.py")
    r2 = verification_identity("pytest -q test_foo.py")
    r3 = verification_identity("pytest -vvv test_foo.py")
    assert r1 == r2 == r3


def test_verification_identity_path_normalization() -> None:
    result = verification_identity("pytest ./test_foo.py")
    assert "test_foo.py" in result
    assert "./test_foo.py" not in result


# ============================================================================
# Edge cases
# ============================================================================

def test_command_parts_only_spaces() -> None:
    assert command_parts("   ") == []


def test_command_parts_multiple_spaces() -> None:
    assert command_parts("pytest   test_foo.py") == ["pytest", "test_foo.py"]
