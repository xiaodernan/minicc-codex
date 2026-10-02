"""The permissions.json deny veto must be asked by the shared consent function.

minicc/permissions.py promises that a deny rule is absolute: it short-circuits before
the interactive approval prompt and cannot be overridden by task flags. That promise
was only true in one of the three places consent is decided. match_permission_rule had
exactly one product reader -- the chat approval callback in minicc/web.py -- while
authorize_tool, the decision every consent path asks, is called from the CLI gate in
minicc/main.py, from that chat callback, and from the plan-node gate in minicc/web.py.
Measured at 3510437 on the CLI's own kwargs, a deny rule over secrets/* returned
allowed=True / default_readonly for read_file and allowed=True / task_yolo for
write_file: two entry points shipped a project refusal nobody asked about.

The controls keep the veto scoped to rules that actually match, so it cannot degrade
into a blanket refusal. The census pins the population of decision sites and requires
each to hand the gate a workspace -- without one no rule can be read, which is exactly
how this gap was made.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from minicc.audit import authorize_tool
from minicc.permissions import match_permission_rule

_DENIED = "secrets/k.txt"
_UNTOUCHED = "notes/todo.md"
_RULES = {"deny": {"paths": ["secrets/*"], "tools": [], "commands": []}}

# Copied from the two callers that never consulted the rule file: _permission_gate in
# minicc/main.py and the node_allow closure in minicc/web.py. They differ from the chat
# shape in exactly the flags a deny rule is promised to outrank.
CLI_SHAPE: dict[str, Any] = {
    "allow_changes": False,
    "allow_network": False,
    "permission_mode": "default",
    "session_id": "s1",
    "capabilities": (),
}
CLI_YOLO_SHAPE: dict[str, Any] = {
    "allow_changes": True,
    "allow_network": True,
    "permission_mode": "yolo",
    "session_id": "",
    "capabilities": (),
}
NODE_SHAPE: dict[str, Any] = {
    "allow_changes": False,
    "allow_network": False,
    "session_id": "node-1",
    "capabilities": (),
}


def _workspace(tmp_path: Path, rules: dict[str, object] | None = _RULES) -> Path:
    (tmp_path / ".minicc").mkdir(parents=True, exist_ok=True)
    if rules is not None:
        (tmp_path / ".minicc" / "permissions.json").write_text(json.dumps(rules), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("shape", [CLI_SHAPE, CLI_YOLO_SHAPE, NODE_SHAPE], ids=["cli", "cli-yolo", "node"])
def test_a_deny_rule_refuses_the_shapes_that_only_ask_authorize_tool(tmp_path, shape) -> None:
    ws = _workspace(tmp_path)
    assert match_permission_rule(ws, "read_file", {"path": _DENIED}) == "deny"
    decision = authorize_tool("read_file", "readonly", {"path": _DENIED}, workspace=ws, **shape)
    assert decision.allowed is False, decision.to_event("read_file")
    assert decision.authorization == "permission_rule_deny"


def test_the_veto_outranks_the_task_flags_that_preceded_it(tmp_path) -> None:
    ws = _workspace(tmp_path)
    decision = authorize_tool("write_file", "write", {"path": _DENIED}, workspace=ws, **CLI_YOLO_SHAPE)
    assert decision.allowed is False, decision.to_event("write_file")
    assert decision.risk == "write"
    assert decision.authorization == "permission_rule_deny"


@pytest.mark.parametrize(
    ("tool", "risk", "shape"),
    [
        ("read_file", "readonly", CLI_SHAPE),
        ("write_file", "write", CLI_SHAPE),
        ("write_file", "write", CLI_YOLO_SHAPE),
        ("read_file", "readonly", NODE_SHAPE),
    ],
)
def test_paths_no_rule_mentions_keep_their_previous_verdicts(tmp_path, tool, risk, shape) -> None:
    ws = _workspace(tmp_path)
    decision = authorize_tool(tool, risk, {"path": _UNTOUCHED}, workspace=ws, **shape)
    if shape is CLI_SHAPE and risk == "write":
        assert (decision.allowed, decision.authorization) == (False, "missing_task_write")
    else:
        assert decision.allowed is True, decision.to_event(tool)
        assert decision.authorization != "permission_rule_deny"


def test_a_workspace_without_a_rule_file_asks_nothing(tmp_path) -> None:
    ws = _workspace(tmp_path, rules=None)
    assert match_permission_rule(ws, "read_file", {"path": _DENIED}) is None
    decision = authorize_tool("read_file", "readonly", {"path": _DENIED}, workspace=ws, **CLI_SHAPE)
    assert (decision.allowed, decision.authorization) == (True, "default_readonly")


def _consent_call_sites(root: Path) -> list[tuple[str, bool]]:
    """Every authorize_tool call in the package, and whether it hands over a workspace."""
    found: list[tuple[str, bool]] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name != "authorize_tool":
                continue
            workspace_kwargs = [k for k in node.keywords if k.arg == "workspace"]
            armed = bool(workspace_kwargs) and not all(
                isinstance(k.value, ast.Constant) and k.value.value is None for k in workspace_kwargs
            )
            found.append((path.relative_to(root).as_posix(), armed))
    return found


def test_every_consent_decision_site_hands_the_gate_a_workspace() -> None:
    """A decision site without a workspace cannot read the project policy at all.

    That is how the CLI gate and the plan node ended up un-armed, so the population is
    pinned instead of re-derived by eye: a new authorize_tool call that drops workspace=
    goes red here, and a site that disappears changes the expected count.
    """
    root = Path(__file__).resolve().parents[1] / "minicc"
    sites = _consent_call_sites(root)
    production = [(f, armed) for f, armed in sites if f != "audit.py"]
    assert sorted({name for name, _ in production}) == ["main.py", "web.py"], production
    assert len(production) == 3, production
    unarmed = [name for name, armed in production if not armed]
    assert not unarmed, "consent sites without a workspace cannot read permissions.json: %s" % unarmed
