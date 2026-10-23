"""The pre-finish verification guard's verdict must have one home.

The loop publishes the guard's error; the web fold reads it back as an
*equality key*.  That is the whole contract, and it is invisible to every
check that only looks at one side: the fold would keep matching against a
sentence the loop no longer says, and the only symptom is a provisional
``任务未完成：...`` leaking into a successful answer - or a repair loop
the fold abandons before the verifier gets to speak.
"""

from __future__ import annotations

import ast
import pathlib

import minicc.web
from minicc.agent import loop as loop_module
from minicc.agent import protocol

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/agent/protocol.py"

GUARD_ERROR = "Agent 在修改工作区后没有完成验证"
GUARD_ANSWER = "修改工作区后没有完成验证，已停止提前交付。"
MARKER = "模型最后输出："

VERDICTS = (GUARD_ERROR, GUARD_ANSWER, MARKER)
CONSTANTS = ("VERIFICATION_GUARD_ERROR", "VERIFICATION_GUARD_ANSWER", "MODEL_LAST_OUTPUT_MARKER")


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _carriers(needle: str) -> list[str]:
    """Every string constant that carries the needle - f-string parts included.

    ``ast.walk`` descends into ``JoinedStr.values``, so a literal baked
    into an f-string is a ``Constant`` here too.  Matching by equality
    alone misses it: the append site spells ``f"\\n\\n模型最后输出：{x}"``,
    whose constant part is ``"\\n\\n模型最后输出："`` and equals nothing.
    """
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if needle in node.value:
                    hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return hits


def _bindings(name: str) -> list[str]:
    """Every place outside the home where the name becomes a binding."""
    hits = []
    for path, tree in _trees():
        rel = path.relative_to(REPO).as_posix()
        if rel == HOME:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name:
                hits.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.arg) and node.arg == name:
                hits.append(f"{rel}:{node.lineno}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                hits.append(f"{rel}:{node.lineno}")
    return hits


def _imported_names(rel: str) -> set[str]:
    for path, tree in _trees():
        if path.relative_to(REPO).as_posix() != rel:
            continue
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.update(alias.name for alias in node.names)
        return names
    raise AssertionError(f"{rel} not found")


def test_the_guard_verdict_is_one_sentence():
    assert protocol.VERIFICATION_GUARD_ERROR == GUARD_ERROR
    assert protocol.VERIFICATION_GUARD_ANSWER == GUARD_ANSWER
    assert protocol.MODEL_LAST_OUTPUT_MARKER == MARKER


def test_each_verdict_is_spelled_in_exactly_one_place():
    for needle in VERDICTS:
        hits = _carriers(needle)
        assert len(hits) == 1, (needle, hits)
        assert hits[0].startswith(f"{HOME}:"), (needle, hits)


def test_the_guard_vocabulary_is_defined_once():
    for name in CONSTANTS:
        definitions = []
        for path, tree in _trees():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                    definitions.append(path.relative_to(REPO).as_posix())
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == name:
                            definitions.append(path.relative_to(REPO).as_posix())
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                    definitions.append(path.relative_to(REPO).as_posix())
        assert definitions == [HOME], (name, definitions)


def test_no_other_module_re_binds_the_guard_vocabulary():
    """A local copy is the drift: it looks shared and compares unequal."""
    for name in CONSTANTS:
        assert _bindings(name) == [], (name, _bindings(name))


def test_the_home_exports_what_it_defines():
    for name in CONSTANTS:
        assert name in protocol.__all__, name


def test_the_loop_reads_the_guard_vocabulary_from_the_home():
    names = _imported_names("minicc/agent/loop.py")
    for name in CONSTANTS:
        assert name in names, name


def test_the_web_fold_reads_the_guard_vocabulary_from_the_home():
    names = _imported_names("minicc/web.py")
    assert "VERIFICATION_GUARD_ERROR" in names
    assert "MODEL_LAST_OUTPUT_MARKER" in names


def test_the_marker_survives_the_append_then_split_round_trip():
    """The fold cuts the tail the loop appended - with the same marker."""
    raw = "I edited three files and stopped."
    appended = f"\n\n{protocol.MODEL_LAST_OUTPUT_MARKER}{raw}"
    assert appended.endswith(raw)
    assert appended.rsplit(protocol.MODEL_LAST_OUTPUT_MARKER, 1)[-1].strip() == raw


def test_the_two_sides_of_the_guard_verdict_are_the_same_object():
    """The loop's error and the fold's equality key must be one string."""
    assert minicc.web.VERIFICATION_GUARD_ERROR is loop_module.VERIFICATION_GUARD_ERROR
    assert minicc.web.VERIFICATION_GUARD_ERROR is protocol.VERIFICATION_GUARD_ERROR


def test_the_guard_verdict_wraps_into_the_failed_run_answer():
    """The answer the guard publishes names the error it publishes."""
    assert protocol.incomplete_answer(protocol.VERIFICATION_GUARD_ANSWER) == (
        "任务未完成：" + GUARD_ANSWER
    )
