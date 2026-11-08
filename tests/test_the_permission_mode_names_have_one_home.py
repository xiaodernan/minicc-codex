"""M8-T619 — permission mode name literals have one home.

The permission mode vocabulary (default, plan, acceptEdits, yolo) is owned by
`minicc.audit` (`PERMISSION_MODES` / `normalize_permission_mode`). Comparisons
and set literals that spell those names as bare strings in task routing,
contract resolution, and subagent policy duplicate the same fact.

Scoped to modules that resolve/compare permission modes to avoid conflating
lookalike uses of common words like "plan"/"default" in other domains.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "audit.py"
SCOPED = {
    PACKAGE / "main.py",
    PACKAGE / "task_contract.py",
    PACKAGE / "task_manager.py",
    PACKAGE / "web.py",
    PACKAGE / "agent" / "subagent.py",
}

MODES = {"default", "plan", "acceptEdits", "yolo"}


def test_the_home_defines_individual_mode_constants() -> None:
    import minicc.audit as a

    assert a.PERMISSION_MODE_DEFAULT == "default"
    assert a.PERMISSION_MODE_PLAN == "plan"
    assert a.PERMISSION_MODE_ACCEPT_EDITS == "acceptEdits"
    assert a.PERMISSION_MODE_YOLO == "yolo"
    assert a.PERMISSION_MODES == {
        a.PERMISSION_MODE_DEFAULT,
        a.PERMISSION_MODE_PLAN,
        a.PERMISSION_MODE_ACCEPT_EDITS,
        a.PERMISSION_MODE_YOLO,
    }


def _check_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and node.value in MODES:
        return node.value
    return None


def test_no_bare_permission_mode_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(path))
        except Exception:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for comp in [node.left] + node.comparators:
                    v = _check_value(comp)
                    if v is not None:
                        offenders.append(f"{rel}:{comp.lineno} compares to {v!r}")
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == "permission_mode":
                        val = _check_value(v)
                        if val is not None:
                            offenders.append(f"{rel}:{v.lineno} dict permission_mode {val!r}")
            # set/frozenset literals containing mode names
            if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
                for elt in node.elts:
                    val = _check_value(elt)
                    if val is not None:
                        offenders.append(f"{rel}:{elt.lineno} collection literal {val!r}")
            if isinstance(node, ast.Call):
                func = node.func
                fname = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
                if fname == "frozenset" and node.args:
                    arg = node.args[0]
                    if isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                        for elt in arg.elts:
                            val = _check_value(elt)
                            if val is not None:
                                offenders.append(f"{rel}:{elt.lineno} frozenset literal {val!r}")
    # dedup
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare permission mode literals in scoped modules - ask "
        "PERMISSION_MODE_* from minicc.audit:\n" + "\n".join(offenders)
    )
