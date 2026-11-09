"""M8-T674 — the six stage names have one home, product included.

``minicc/config.py`` is the gated home: ``STAGE_INSPECT`` / ``STAGE_PLANNING`` /
``STAGE_IMPLEMENT`` / ``STAGE_VERIFY`` / ``STAGE_REPAIR`` / ``STAGE_REVIEW``,
and ``STAGE_NAMES`` as their frozenset.  The test suite already pins that home
(``tests/test_the_stage_names_have_one_home_in_the_tests_too.py``); this gate
pins it on the product side: after the batch ran, ``minicc`` spells none of the
six words as a bare string outside the home, outside prose, and outside the
``PHASE_*`` assignments in ``protocol.py`` (those keep those spellings on the
phase axis — same words, different fact — exactly like everywhere else).

Narrow exceptions, each with a reason in the batch notes (批次 674):
``CHANGE_INTENT_MARKERS`` — the substring change-intent matcher in
``task_manager.py`` carries ``implement`` as an English intent keyword, not as
a stage name (its author kept the behavior byte-identical; removing the word
would change behavior).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME_PATH = REPO / "minicc" / "config.py"
PROTOCOL_PATH = REPO / "minicc" / "agent" / "protocol.py"
STAGE_NAMES = set("inspect planning implement verify repair review".split())
PHASE_TARGETS = {"PHASE_PLANNING", "PHASE_REVIEW", "PHASE_VERIFY", "PHASE_REPAIR"}
#: The DAG kind vocabulary owns its own spellings (see 批次 674):
#: ``readonly`` / ``write`` / ``exec`` / ``review`` / ``merge`` kinds -
#: same letters, different fact.
KIND_TARGETS = {"DAG_KIND_REVIEW", "DAG_KIND_READONLY", "DAG_KIND_WRITE", "DAG_KIND_EXEC", "DAG_KIND_MERGE"}
GRANDFATHER_ASSIGNMENTS = {"CHANGE_INTENT_MARKERS"}


def _prose_nodes(tree: ast.Module) -> set[int]:
    prose: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            for child in ast.walk(node):
                prose.add(id(child))
    return prose


def _parents(tree: ast.Module) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _assign_target_id(node: ast.AST, parents: dict[int, ast.AST]) -> str | None:
    current = parents.get(id(node))
    while current is not None:
        if (
            isinstance(current, ast.Assign)
            and len(current.targets) == 1
            and isinstance(current.targets[0], ast.Name)
        ):
            return current.targets[0].id
        current = parents.get(id(current))
    return None


def test_the_home_defines_the_six_stages() -> None:
    from minicc import config

    assert {getattr(config, "STAGE_" + name.upper()) for name in STAGE_NAMES} == STAGE_NAMES
    assert config.STAGE_NAMES == frozenset(STAGE_NAMES)


def test_no_minicc_module_spells_a_stage_name_as_a_bare_literal_outside_the_home() -> None:
    offenders: list[str] = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if path == HOME_PATH:
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        prose = _prose_nodes(tree)
        parents = _parents(tree)

        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in STAGE_NAMES:
                continue
            if id(node) in prose:
                continue
            target = _assign_target_id(node, parents)
            if path == PROTOCOL_PATH and target in PHASE_TARGETS:
                continue
            if target in GRANDFATHER_ASSIGNMENTS or target in KIND_TARGETS:
                continue
            line = src.splitlines()[node.lineno - 1]
            offenders.append(f"{relative}:{node.lineno}: {line.strip()[:170]}")
    assert offenders == [], (
        "bare stage literal - use STAGE_* from minicc/config.py:\n" + "\n".join(offenders)
    )
