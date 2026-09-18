import pytest
from minicc.agent.tool_policy import is_verification_evidence


@pytest.mark.parametrize("command", [
    "python -B -m unittest -v test_solution",
    "python -I -B -m pytest tests/test_solution.py -q",
    "py -u -m unittest discover",
])
def test_real_interpreter_checks_count(command):
    assert is_verification_evidence("bash", {"command": command}, "ok")


@pytest.mark.parametrize("command", [
    'python -B -c "print(\'pytest\')"',
    "python -B -m pytest --collect-only",
    "echo python -m pytest",
    "pytest --collect-only=true",
    "tsc --showConfig",
    "ruff format app.py",
    "ruff check --show-settings",
])
def test_non_execution_does_not_count(command):
    assert not is_verification_evidence("bash", {"command": command}, "ok")
