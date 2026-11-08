"""M8-T562 — the "no signal for the fingerprint" set has one home.

``minicc/tools/fs.py`` hides a directory from the agent's tools; the
verification fingerprint should descend nowhere the tools refuse to look
either - or a hidden directory would move the digest, and the "the inputs
did not change" claim becomes true exactly up to what the tools can see.
The two enumerations were spelled independently and had already drifted
(the fingerprint kept walking ``.hg``/``.idea``/``target``/``.graders``
while the tools knew better).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/fs.py"

CORE = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules",
    ".minicc", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist",
    "build", ".idea", ".vscode", "target", ".graders",
})

#: A module that spells this many shared names inline is keeping its own copy.
INLINE_SAMPLE = 8


def test_the_home_carries_the_shared_policy() -> None:
    from minicc.tools.fs import SKIP_DIRS

    missing = CORE - SKIP_DIRS
    assert not missing, (
        f"the tools' hidden-entry policy lost names the fingerprint relies on: "
        f"{sorted(missing)}"
    )


def test_the_fingerprint_asks_the_home() -> None:
    source = (PACKAGE / "agent" / "verification_plan.py").read_text(encoding="utf-8")
    assert "from ..tools.fs import SKIP_DIRS" in source, (
        "minicc/agent/verification_plan.py must ask the one home "
        "(minicc/tools/fs.py) for the hidden-entry policy"
    )


def test_no_module_spells_the_policy_inline() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(elements & CORE) >= INLINE_SAMPLE and relative != HOME:
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        f"a hidden-entry enumeration is spelled inline outside its one home "
        f"({HOME}): " + ", ".join(offenders)
    )


def test_hidden_directories_do_not_move_the_digest(tmp_path: Path) -> None:
    """The fingerprint ignores what the tools hide - a .graders tree inside
    the workspace must not change it, or any grader run self-poisons the
    'inputs unchanged' reuse path."""
    from minicc.agent.verification_plan import verification_fingerprint

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("x = 1\n", encoding="utf-8")
    before = verification_fingerprint(ws, ["a.py"], [])

    (ws / ".graders").mkdir()
    (ws / ".graders" / "driver.py").write_text("hidden grader bytes\n", encoding="utf-8")
    (ws / "target").mkdir()
    (ws / "target" / "out.bin").write_text("build artifact\n", encoding="utf-8")
    after = verification_fingerprint(ws, ["a.py"], [])

    assert before == after, "a hidden directory moved the fingerprint"
