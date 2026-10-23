"""The HTTP error-code vocabulary must have exactly one home.

Every API failure carries a machine-readable ``code`` (M8-T5) so a client
can branch on it.  ``ERROR_CODES`` held ten of those spellings while six
``_fail`` call sites wrote four of them out again by hand.  Renaming a code
in the table therefore left the routes that pass it explicitly on the old
spelling: a client that learned the new name failed on exactly the routes
it was told were safe.  Half the surface keeps answering, which is the
quietest way for a contract to break.

This door pins:

* every code is spelled once, in ``webserver.py``;
* ``ERROR_CODES`` reads the vocabulary instead of re-spelling it;
* no ``_fail`` call site, and no denial body, spells a code by hand;
* the vocabulary is a bijection - no two names for one code;
* ``error_code_for`` still resolves every exception the table covers.
"""

from __future__ import annotations

import ast
import pathlib

from minicc import webserver
from minicc.webserver import ERROR_CODES, error_code_for

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/webserver.py"

VOCABULARY = {
    "CODE_TASK_NOT_FOUND": "task_not_found",
    "CODE_NOT_FOUND": "not_found",
    "CODE_INVALID_REQUEST": "invalid_request",
    "CODE_SESSION_ERROR": "session_error",
    "CODE_WORKTREE_ERROR": "worktree_error",
    "CODE_SNAPSHOT_ERROR": "snapshot_error",
    "CODE_ALLOWLIST_ERROR": "allowlist_error",
    "CODE_MCP_ERROR": "mcp_error",
    "CODE_CHANGE_ERROR": "change_error",
    "CODE_FORBIDDEN": "forbidden",
    "CODE_UNAUTHORIZED": "unauthorized",
    "CODE_CROSS_ORIGIN_DENIED": "cross_origin_denied",
    "CODE_TOO_MANY_EVENT_STREAMS": "too_many_event_streams",
    "CODE_REQUEST_FAILED": "request_failed",
    "CODE_INTERNAL_ERROR": "internal_error",
}


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _module_constants() -> dict[str, ast.Constant]:
    """Every ``NAME = "literal"`` at module level in the home."""
    found: dict[str, ast.Constant] = {}
    for path, tree in _trees():
        if path.relative_to(REPO).as_posix() != HOME:
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                        found[target.id] = node.value
    return found


def test_the_vocabulary_is_what_the_home_exports():
    constants = _module_constants()
    for name, value in VOCABULARY.items():
        assert name in constants, name
        assert constants[name].value == value, (name, constants[name].value)
        assert getattr(webserver, name) == value, name


def _value_positions(value: str) -> list[str]:
    """Every *value* position in the tree that spells ``value`` out.

    A value position is anywhere a string is produced - a ``return``, a
    ``code=`` keyword, a dict entry's value, a constant definition.  Dict
    *keys* are excluded on purpose: ``web.py``'s status payload carries a
    field named ``"worktree_error"``, which is a JSON field name and not a
    wire error code.  Same spelling, different fact (M8-T457: same shape is
    not the same data), and a census that cannot tell them apart would
    either flag the field or excuse the emitter.
    """
    hits = []
    for path, tree in _trees():
        rel = path.relative_to(REPO).as_posix()
        keys = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys.update(id(key) for key in node.keys if key is not None)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == value and id(node) not in keys:
                hits.append(f"{rel}:{node.lineno}")
    return hits


def test_each_code_is_spelled_in_exactly_one_value_position():
    """One spelling per code, and it is the constant in the home.

    This is the census that killed M8-T474-269: a ``return "request_failed"``
    is a value position like any other, so re-spelling a code outside the
    vocabulary cannot hide in a spot the census forgot to enumerate.
    """
    for name, value in VOCABULARY.items():
        hits = _value_positions(value)
        assert len(hits) == 1, (value, hits)
        assert hits[0].startswith(f"{HOME}:"), (value, hits)
        assert hits[0] == f"{HOME}:{_module_constants()[name].lineno}", (value, hits)


def test_the_vocabulary_is_a_bijection():
    """Two names for one code is the same drift wearing a different hat."""
    values = list(VOCABULARY.values())
    assert len(set(values)) == len(values), values


def test_the_table_reads_the_vocabulary_instead_of_respelling_it():
    constants = _module_constants()
    for path, tree in _trees():
        if path.relative_to(REPO).as_posix() != HOME:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                    and node.target.id == "ERROR_CODES":
                assert isinstance(node.value, ast.Dict), "ERROR_CODES lost its dict"
                for key, value in zip(node.value.keys, node.value.values):
                    assert isinstance(key, ast.Name), ast.dump(key)
                    assert isinstance(value, ast.Name), ast.dump(value)
                    assert value.id in VOCABULARY, value.id
                    assert VOCABULARY[value.id] == _expected_code(key.id), key.id
                return
    raise AssertionError("ERROR_CODES not found")


def _expected_code(exception_name: str) -> str:
    return {
        "KeyError": "task_not_found",
        "PermissionError": "forbidden",
        "FileNotFoundError": "not_found",
        "ValueError": "invalid_request",
        "SessionError": "session_error",
        "WorktreeError": "worktree_error",
        "SnapshotError": "snapshot_error",
        "AllowlistError": "allowlist_error",
        "McpError": "mcp_error",
        "ChangeError": "change_error",
    }[exception_name]


def test_no_fail_call_site_spells_a_code_by_hand():
    """``code=`` must name a constant; a literal here is the drift."""
    strays = []
    for path, tree in _trees():
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "_fail":
                for keyword in node.keywords:
                    if keyword.arg != "code":
                        continue
                    if not isinstance(keyword.value, ast.Name):
                        strays.append((rel, node.lineno, ast.dump(keyword.value)))
                    elif keyword.value.id not in VOCABULARY:
                        strays.append((rel, node.lineno, keyword.value.id))
    assert strays == [], strays


def test_the_denial_bodies_read_the_vocabulary():
    """The two hand-rolled denial bodies are emitters too.

    Scoped to those two functions by name.  ``_fail``'s own payload builds
    ``{"code": resolved}`` from a variable, which is the home working as
    intended; other modules build JSON bodies with a ``code`` key of their
    own (the JSON-RPC envelope, the bash tool's detached refusal) and those
    are separate vocabularies.
    """
    strays = []
    for path, tree in _trees():
        if path.relative_to(REPO).as_posix() != HOME:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name in {"_deny_cross_origin", "_deny_auth"}:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Dict):
                        for key, value in zip(sub.keys, sub.values):
                            if isinstance(key, ast.Constant) and key.value == "code":
                                if not isinstance(value, ast.Name):
                                    strays.append((node.name, value.lineno, ast.dump(value)))
                                elif value.id not in VOCABULARY:
                                    strays.append((node.name, value.lineno, value.id))
    assert strays == [], strays


def test_error_code_for_still_resolves_every_covered_exception():
    assert error_code_for(KeyError("x")) == "task_not_found"
    assert error_code_for(None) == "request_failed"
    assert error_code_for(RuntimeError("x")) == "internal_error"
    for kind, code in ERROR_CODES.items():
        assert error_code_for(kind("x")) == code, (kind, code)
