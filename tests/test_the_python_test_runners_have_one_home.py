"""M8-T389 — Python 测试运行器 {pytest, unittest}：身份归一与只读放行两个家"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/check_commands.py"

PYTHON_TEST_RUNNERS = frozenset({"pytest", "unittest"})


def test_the_home_exists_in_check_commands() -> None:
    """check_commands.py owns the two runners."""
    from minicc.agent.check_commands import PYTHON_TEST_RUNNERS as Home

    assert Home == PYTHON_TEST_RUNNERS


def test_verification_plan_asks_the_home() -> None:
    """verification_plan.py uses the same object, not its own spelling."""
    import minicc.agent.check_commands as check_commands
    import minicc.agent.verification_plan as verification_plan

    assert verification_plan.PYTHON_TEST_RUNNERS is check_commands.PYTHON_TEST_RUNNERS


def test_no_module_inlines_the_runners() -> None:
    """No module spells the pair as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == PYTHON_TEST_RUNNERS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the python test runners are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_both_readers_still_behave() -> None:
    """Identity normalization and the read-only short-circuit still work."""
    from minicc.agent.check_commands import verification_identity
    from minicc.agent.verification_plan import safe_verification_command

    assert verification_identity("python -m pytest -q tests/") == ("pytest", "tests/")
    assert verification_identity("python -m unittest discover -v") == ("unittest", "discover")
    assert safe_verification_command("python -m pytest -q tests/") is True
    assert safe_verification_command("python -m unittest discover") is True
