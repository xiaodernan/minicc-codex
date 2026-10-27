"""M8-T526: a policy that cannot be read is not a policy that allows.

``minicc/audit.py`` says a deny rule "is an absolute veto, not a question".
``minicc/permissions.py`` already computed the reason a rules file could not be
evaluated - and every caller threw that reason away and kept the **empty**
rules.  Empty rules means "nothing is denied", which is an ALLOW.

``permissions.json`` is user-authored: the repository never writes it.  So the
way to reach that state is a typo - one missing brace, one stray comma - and
the result is that the user's deny rule on ``secrets/*`` silently stops
existing, on the read path and on the write path alike, with the only signal
being an error string in a status panel nobody is watching.

Measured before the fix (this file's own probe, on the shipped code):

  rules file fine            -> denied=True
  rules file malformed       -> denied=False    <-- the veto had vanished
  rules file missing         -> denied=False    (correct: no policy, no rules)

What this does NOT change: the low-level question keeps its own contract.
``match_permission_rule`` still answers ``None`` for a file it cannot parse -
that is "the rules say nothing about this call", which is a true statement
about the *rules*.  The question this file is about is a different one: *may
this call proceed?*  and for that question an unknown policy has exactly one
safe answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.audit import (
    authorize_tool,
    deny_rule_names_paths,
    path_rule_denies_call,
    path_rule_refusal_reason,
    policy_evaluation_error,
    tool_denied_by_rule,
)
from minicc.permissions import match_permission_rule

DENIED = "secrets/k.txt"
UNTOUCHED = "notes/todo.md"
RULES = {"deny": {"paths": ["secrets/*"], "tools": [], "commands": []}}


def _workspace(tmp_path: Path, body: str | None) -> Path:
    (tmp_path / "secrets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "secrets" / "k.txt").write_text("secret\n", encoding="utf-8")
    (tmp_path / "notes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes" / "todo.md").write_text("todo\n", encoding="utf-8")
    if body is not None:
        (tmp_path / ".minicc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".minicc" / "permissions.json").write_text(body, encoding="utf-8")
    return tmp_path


def _valid(tmp_path: Path) -> Path:
    return _workspace(tmp_path, json.dumps(RULES))


def _broken(tmp_path: Path) -> Path:
    return _workspace(tmp_path, "{not json")


def _missing(tmp_path: Path) -> Path:
    return _workspace(tmp_path, None)


# --- the veto holds ---------------------------------------------------------


def test_a_malformed_policy_still_refuses_the_path_it_denied(tmp_path: Path) -> None:
    """The headline: a broken rules file must not turn the veto off."""
    workspace = _broken(tmp_path)
    assert tool_denied_by_rule(workspace, "read_file", {"path": DENIED}) is True
    assert path_rule_denies_call(workspace, "read_file", {"path": DENIED}) is True


def test_a_malformed_policy_refuses_the_workspace_wide_read(tmp_path: Path) -> None:
    """A workspace-wide read carries the content of every path."""
    workspace = _broken(tmp_path)
    assert deny_rule_names_paths(workspace) is True
    for tool in ("git_diff", "grep", "glob", "tree"):
        assert path_rule_denies_call(workspace, tool, {}) is True, tool


def test_a_malformed_policy_refuses_at_the_shared_consent_decision(tmp_path: Path) -> None:
    """The write/exec/network path refuses too - with its own code."""
    workspace = _broken(tmp_path)
    decision = authorize_tool(
        "write_file",
        "write",
        {"path": "notes/todo.md"},
        allow_changes=True,
        allow_network=True,
        permission_mode="yolo",
        workspace=workspace,
    )
    assert decision.allowed is False, decision
    assert decision.authorization == "permission_policy_unreadable", decision


def test_a_missing_policy_still_allows(tmp_path: Path) -> None:
    """The normal case must not change: no policy, no rules, no refusal."""
    workspace = _missing(tmp_path)
    assert tool_denied_by_rule(workspace, "read_file", {"path": DENIED}) is False
    assert deny_rule_names_paths(workspace) is False
    assert path_rule_denies_call(workspace, "read_file", {"path": DENIED}) is False
    decision = authorize_tool(
        "write_file",
        "write",
        {"path": "notes/todo.md"},
        allow_changes=True,
        allow_network=True,
        permission_mode="yolo",
        workspace=workspace,
    )
    assert decision.allowed is True, decision


def test_a_valid_policy_still_denies_only_what_it_denied(tmp_path: Path) -> None:
    """Control: the rule still draws its own line."""
    workspace = _valid(tmp_path)
    assert tool_denied_by_rule(workspace, "read_file", {"path": DENIED}) is True
    assert tool_denied_by_rule(workspace, "read_file", {"path": UNTOUCHED}) is False


# --- the reason is the real one --------------------------------------------


def test_the_refusal_names_the_policy_that_could_not_be_read(tmp_path: Path) -> None:
    """A refusal that names the wrong cause sends the reader the wrong place."""
    workspace = _broken(tmp_path)
    reason = path_rule_refusal_reason(workspace, "read_file")
    assert "permissions.json" in reason, reason
    assert "读不出来" in reason, reason
    assert "deny 规则拒绝" not in reason, reason
    assert policy_evaluation_error(workspace), policy_evaluation_error(workspace)


def test_the_decision_reason_names_the_policy_too(tmp_path: Path) -> None:
    workspace = _broken(tmp_path)
    decision = authorize_tool(
        "write_file",
        "write",
        {"path": "notes/todo.md"},
        allow_changes=True,
        allow_network=True,
        permission_mode="yolo",
        workspace=workspace,
    )
    assert "permissions.json" in decision.reason, decision
    assert "deny 规则拒绝" not in decision.reason, decision


def test_a_valid_policy_still_names_the_rule_as_the_cause(tmp_path: Path) -> None:
    workspace = _valid(tmp_path)
    reason = path_rule_refusal_reason(workspace, "read_file")
    assert "deny 规则拒绝" in reason, reason


# --- the boundary did not move ----------------------------------------------


def test_the_low_level_contract_did_not_move(tmp_path: Path) -> None:
    """``match_permission_rule`` keeps saying "the rules say nothing".

    That is a true statement about the *rules*; the gate's question is a
    different one.  This case is here so the fix cannot quietly widen the
    low-level function into a refusal.
    """
    workspace = _broken(tmp_path)
    assert match_permission_rule(workspace, "read_file", {"path": DENIED}) is None


# --- every reader of the gate inherits the refusal --------------------------


def test_every_reader_of_the_gate_inherits_the_refusal(tmp_path: Path) -> None:
    """The gate has one home, so every face that asks it inherits the fix.

    The mention injection, the evidence index and the snapshot copy are three
    other readers of ``tool_denied_by_rule``; they must all refuse when the
    policy is broken, not just the one the agent's own calls go through.
    """
    workspace = _broken(tmp_path)
    from minicc.agent.retrieval import _is_denied_by_rules
    from minicc.snapshots import _is_denied_by_rules as _snapshot_denied

    assert _is_denied_by_rules(workspace, DENIED) is True
    assert _snapshot_denied(workspace, DENIED) is True


def test_the_agent_asks_the_same_home_for_the_reason(tmp_path: Path) -> None:
    """The sentence the model sees comes from the one home, not from a copy.

    Importing the home is not enough - the loop could import it and then spell
    the sentence out again, which is exactly the shape the ``one home`` gate
    for the deny veto was written against.  So this checks the **call site**:
    the sentence must not appear in the loop's own bytes at all.
    """
    workspace = _broken(tmp_path)
    from minicc.agent.loop import path_rule_refusal_reason as loop_reason

    assert loop_reason is path_rule_refusal_reason
    assert "读不出来" in loop_reason(workspace, "read_file")

    loop_source = (
        Path(__file__).resolve().parents[1] / "minicc" / "agent" / "loop.py"
    ).read_text(encoding="utf-8")
    assert "permissions.json deny 规则拒绝了此操作" not in loop_source, (
        "the loop spells the refusal sentence itself; the one home has it"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
