"""M8-T518 — MISSING_TASK_AUTHORIZATIONS 一个键两个家：audit.py 与 web.py"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

MISSING_TASK_AUTHORIZATIONS = frozenset({"missing_task_write", "missing_task_exec"})


def test_the_missing_task_authorizations_exist_in_audit() -> None:
    """The constant exists in audit.py."""
    from minicc.audit import MISSING_TASK_AUTHORIZATIONS as AuditMissing
    assert AuditMissing == MISSING_TASK_AUTHORIZATIONS


def test_web_imports_from_audit() -> None:
    """web.py imports MISSING_TASK_AUTHORIZATIONS from audit."""
    from minicc.web import MISSING_TASK_AUTHORIZATIONS as WebMissing
    assert WebMissing == MISSING_TASK_AUTHORIZATIONS


def test_audit_uses_the_constant() -> None:
    """audit.py uses the constant instead of inline set."""
    audit_path = PACKAGE / "audit.py"
    source = audit_path.read_text(encoding="utf-8")
    # Should reference the constant, not inline set
    assert "MISSING_TASK_AUTHORIZATIONS" in source
    # Should not have inline set at the old location (line ~576)
    # Check that the inline set is not used in the function
    import re
    # The old pattern should not appear in the interpret_authorization_decision function
    func_start = source.find("def interpret_authorization_decision")
    func_end = source.find("\n\n", func_start)
    func_body = source[func_start:func_end] if func_end > 0 else source[func_start:]
    # Should not contain inline set literal in this function
    assert '{"missing_task_write", "missing_task_exec"}' not in func_body


def test_web_uses_the_constant() -> None:
    """web.py uses the imported constant instead of inline set."""
    web_path = PACKAGE / "web.py"
    source = web_path.read_text(encoding="utf-8")
    # Should reference the imported constant
    assert "MISSING_TASK_AUTHORIZATIONS" in source
    # Should not have inline set at the old location (line ~1839)
    # Check the run_agent function
    func_start = source.find("async def run_agent")
    func_end = source.find("\n\n    async def ", func_start)
    if func_end < 0:
        func_end = source.find("\n\n    def ", func_start)
    func_body = source[func_start:func_end] if func_end > 0 else source[func_start:]
    # Should not contain inline set literal in this function
    assert '{"missing_task_write", "missing_task_exec"}' not in func_body


def test_no_inline_missing_task_set_anywhere() -> None:
    """No module has inline {'missing_task_write', 'missing_task_exec'} set."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if elements == MISSING_TASK_AUTHORIZATIONS:
                relative = path.relative_to(REPO).as_posix()
                if relative not in ("minicc/audit.py", "minicc/web.py"):
                    offenders.append(f"{relative}:{node.lineno}")
                # Also check if it's in audit.py or web.py but not the constant definition
                elif relative == "minicc/audit.py":
                    # Check if it's the constant definition line vs usage
                    line = path.read_text(encoding="utf-8").splitlines()[node.lineno - 1]
                    if "MISSING_TASK_AUTHORIZATIONS =" not in line:
                        offenders.append(f"{relative}:{node.lineno} (usage, not definition)")
                elif relative == "minicc/web.py":
                    # In web.py it should be imported, not defined inline
                    line = path.read_text(encoding="utf-8").splitlines()[node.lineno - 1]
                    if "from .audit import" not in line and "MISSING_TASK_AUTHORIZATIONS" not in line:
                        offenders.append(f"{relative}:{node.lineno} (inline set in web.py)")

    assert not offenders, (
        "Inline missing_task authorization sets found outside their home: "
        + ", ".join(offenders)
    )