"""The permissions.json deny veto must have exactly one home.

A deny rule is the one consent verdict no task flag can override, so every face
of the product has to reach it.  ``audit.authorize_tool`` is the shared
decision function every consent path asks, and it asks the rule first -
whatever the tool's risk, so denying a path like ``.env`` blocks reads too.

The chat face in ``minicc/web.py`` used to re-decide that veto by hand before
calling the shared function: it hand-built the ``AuthorizationDecision``,
spelled the reason sentence out a second time, and repeated the
``permission_rule_deny`` authorization code.  Two homes for one verdict.  A
rename in the shared decision then reached only the faces that went through
it, while the web face kept emitting the old wording for a refusal the CLI
face had stopped naming - the operator greps one phrase and finds half the
refusals.  The hand-built copy also reported the *effective* risk while the
shared decision reports the risk it was handed, so two faces of one refusal
could disagree about how dangerous the refused call was.

This door pins:

* the reason sentence and the authorization code each have one carrier inside
  a decision, and it is in ``audit``;
* nothing else inside a decision starts with either of them;
* the only decision carrying that code is built inside ``authorize_tool``;
* the shared decision still refuses, still outranks the task flags, and still
  reaches read-only tools;
* the risk it reports is the risk it was handed - the drift the second home
  had already grown.

The census is deliberately scoped to ``AuthorizationDecision(...)`` calls.
``permissions.json deny 规则拒绝`` is the *prefix of a whole family* of longer
messages (``...规则拒绝了此操作``, ``...规则拒绝了此路径``, ``...规则拒绝了这个
文件树视图``) that are different facts about different targets, so a tree-wide
prefix census would swallow them (M8-T472/T475).  The verdict is what lives in
a decision; the family members never do.
"""

from __future__ import annotations

import ast
import json
import pathlib
from typing import Any

import pytest

from minicc.audit import authorize_tool
from minicc.permissions import match_permission_rule

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/audit.py"
REASON = "permissions.json deny 规则拒绝"
CODE = "permission_rule_deny"

_DENIED = "secrets/k.txt"
_UNTOUCHED = "notes/todo.md"
_RULES: dict[str, Any] = {"deny": {"paths": ["secrets/*"], "tools": [], "commands": []}}


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _is_dict_key(node: ast.AST, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    return isinstance(parent, ast.Dict) and node in parent.keys


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _enclosing_function(tree: ast.AST, target: ast.AST) -> str | None:
    parents = _parents(tree)
    names: list[str] = []
    node: ast.AST | None = target
    while node is not None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        node = parents.get(id(node))
    return ".".join(reversed(names)) if names else None


def _decision_strings() -> list[tuple[str, int, str]]:
    """Every string constant inside an ``AuthorizationDecision(...)`` call."""
    found = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name != "AuthorizationDecision":
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    found.append((path.relative_to(REPO).as_posix(), sub.lineno, sub.value))
    return found


def _decision_builders(code: str) -> list[tuple[str, str | None]]:
    """Every ``AuthorizationDecision(...)`` carrying ``code``, and its function."""
    found = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name != "AuthorizationDecision":
                continue
            texts = [a.value for a in node.args if isinstance(a, ast.Constant)]
            texts += [k.value.value for k in node.keywords
                      if k.arg == "authorization" and isinstance(k.value, ast.Constant)]
            if code in texts:
                found.append((path.relative_to(REPO).as_posix(), _enclosing_function(tree, node)))
    return found


def _workspace(tmp_path: pathlib.Path, rules: dict[str, Any] | None = _RULES) -> pathlib.Path:
    (tmp_path / "secrets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "secrets" / "k.txt").write_text("secret\n", encoding="utf-8")
    (tmp_path / "notes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes" / "todo.md").write_text("todo\n", encoding="utf-8")
    if rules is not None:
        (tmp_path / ".minicc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".minicc" / "permissions.json").write_text(
            json.dumps(rules), encoding="utf-8"
        )
    return tmp_path


# --- one home for the words ---------------------------------------------------


def test_the_reason_sentence_has_exactly_one_carrier_inside_a_decision():
    hits = [hit for hit in _decision_strings() if hit[2] == REASON]
    assert len(hits) == 1, hits
    assert hits[0][0] == HOME, hits


def test_the_authorization_code_has_exactly_one_carrier_inside_a_decision():
    hits = [hit for hit in _decision_strings() if hit[2] == CODE]
    assert len(hits) == 1, hits
    assert hits[0][0] == HOME, hits


def test_nothing_else_inside_a_decision_starts_with_the_reason_sentence():
    """A hand-written copy is exactly this shape: the sentence, then more."""
    strays = [hit for hit in _decision_strings()
              if hit[2].startswith(REASON) and hit[2] != REASON]
    assert strays == [], strays


def test_nothing_else_inside_a_decision_starts_with_the_authorization_code():
    strays = [hit for hit in _decision_strings()
              if hit[2].startswith(CODE) and hit[2] != CODE]
    assert strays == [], strays


def test_the_deny_decision_is_built_inside_exactly_one_function():
    assert _decision_builders(CODE) == [(HOME, "authorize_tool")]


# --- the home still decides ---------------------------------------------------


def test_the_shared_decision_refuses_with_that_reason_and_code(tmp_path):
    ws = _workspace(tmp_path)
    decision = authorize_tool(
        "read_file", "readonly", {"path": _DENIED},
        allow_changes=False, allow_network=False,
        permission_mode="default", session_id="s1", workspace=ws,
    )
    assert decision.allowed is False
    assert decision.reason == REASON
    assert decision.authorization == CODE


def test_the_veto_outranks_the_task_flags(tmp_path):
    ws = _workspace(tmp_path)
    decision = authorize_tool(
        "write_file", "write", {"path": _DENIED},
        allow_changes=True, allow_network=True,
        permission_mode="yolo", session_id="", workspace=ws,
    )
    assert decision.allowed is False, decision.to_event("write_file")
    assert decision.authorization == CODE


def test_the_veto_reaches_a_read_only_tool(tmp_path):
    """Denying a path like ``.env`` has to block the read too."""
    ws = _workspace(tmp_path)
    assert match_permission_rule(ws, "read_file", {"path": _DENIED}) == "deny"
    decision = authorize_tool(
        "read_file", "readonly", {"path": _DENIED},
        allow_changes=False, allow_network=False,
        permission_mode="default", session_id="s1", workspace=ws,
    )
    assert decision.allowed is False, decision.to_event("read_file")


def test_a_path_no_rule_mentions_keeps_its_previous_verdict(tmp_path):
    ws = _workspace(tmp_path)
    decision = authorize_tool(
        "read_file", "readonly", {"path": _UNTOUCHED},
        allow_changes=False, allow_network=False,
        permission_mode="default", session_id="s1", workspace=ws,
    )
    assert (decision.allowed, decision.authorization) == (True, "default_readonly")


def test_a_workspace_without_a_rule_file_asks_nothing(tmp_path):
    ws = _workspace(tmp_path, rules=None)
    decision = authorize_tool(
        "read_file", "readonly", {"path": _DENIED},
        allow_changes=False, allow_network=False,
        permission_mode="default", session_id="s1", workspace=ws,
    )
    assert (decision.allowed, decision.authorization) == (True, "default_readonly")


@pytest.mark.parametrize("handed", ["readonly", "write"])
def test_the_risk_reported_is_the_risk_the_decision_was_handed(tmp_path, handed):
    """The drift the second home had grown: it reported the *effective* risk.

    ``memory_write`` with ``scope=user`` writes outside the workspace, so its
    effective risk is ``write`` whatever the tool declares.  The shared decision
    reports the risk it was handed; the web copy reported the effective one, so
    the two faces of one refusal disagreed about how dangerous it was.
    """
    ws = _workspace(tmp_path)
    decision = authorize_tool(
        "memory_write", handed, {"scope": "user", "path": _DENIED},
        allow_changes=False, allow_network=False,
        permission_mode="default", session_id="s1", workspace=ws,
    )
    assert decision.allowed is False
    assert decision.authorization == CODE
    assert decision.risk == handed, decision.to_event("memory_write")
    assert decision.reason == REASON
