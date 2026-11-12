"""The typed Git write tools are human-triggered only (M8 boundary).

``git_stage`` / ``git_commit`` are the one pair of tools the roadmap allows the
agent to *propose* but never to run by itself: a task flag (``allow_changes``),
``acceptEdits`` and even ``yolo`` must not pre-authorize them, or the boundary
that says a commit is triggered by a human slides the moment someone runs a
yolo task. The only grant is a per-session allowlist rule, which exists solely
because a human answered the interactive approval prompt with "always".
"""

from __future__ import annotations

import re
from pathlib import Path

from minicc.allowlist import add_session_rule
from minicc.audit import HUMAN_ONLY_TOOLS, authorize_tool
from minicc.tools import build_registry
from minicc.tools.editor import Editor

REPO_ROOT = Path(__file__).resolve().parents[1]
RISK = {"git_stage": "write", "git_commit": "exec"}


def test_every_human_only_name_is_a_registered_tool(tmp_path: Path) -> None:
    registry = build_registry(Editor(tmp_path))
    missing = set(HUMAN_ONLY_TOOLS) - set(registry.names())
    assert not missing, f"HUMAN_ONLY_TOOLS went stale: {sorted(missing)} not registered"


def test_yolo_cannot_preauthorize_the_git_writes() -> None:
    for tool in sorted(HUMAN_ONLY_TOOLS):
        for allow_changes in (False, True):
            decision = authorize_tool(
                tool,
                RISK[tool],
                {},
                allow_changes=allow_changes,
                allow_network=False,
                permission_mode="yolo",
            )
            assert decision.allowed is False, f"{tool} was pre-authorized by yolo"
            assert decision.authorization == "human_only_tool"


def test_accept_edits_and_task_flags_cannot_preauthorize_the_git_writes() -> None:
    for tool in sorted(HUMAN_ONLY_TOOLS):
        decision = authorize_tool(
            tool, RISK[tool], {}, allow_changes=True, allow_network=False, permission_mode="acceptEdits"
        )
        assert decision.allowed is False
        assert decision.authorization == "human_only_tool"


def test_control_yolo_still_preauthorizes_other_write_and_exec_tools() -> None:
    # The gate must be keyed on the tool identity, not on a blanket yolo change.
    for tool, risk, args in (
        ("write_file", "write", {}),
        ("bash", "exec", {"command": "echo hi"}),
    ):
        decision = authorize_tool(
            tool, risk, args, allow_changes=False, allow_network=False, permission_mode="yolo"
        )
        assert decision.allowed is True
        assert decision.authorization == "task_yolo"


def test_control_readonly_git_tools_are_unaffected() -> None:
    for tool in ("git_status", "git_diff", "git_summary", "git_merge_precheck"):
        decision = authorize_tool(tool, "readonly", {}, allow_changes=False, allow_network=False)
        assert decision.allowed is True


def test_a_human_allowlist_rule_is_the_only_door(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", tool="git_commit")
    granted = authorize_tool(
        "git_commit", "exec", {"message": "x"},
        allow_changes=False, allow_network=False, permission_mode="yolo",
        session_id="s1", workspace=tmp_path,
    )
    assert granted.allowed is True
    assert granted.authorization == "session_allowlist"
    # Control: that entry blesses git_commit only, not the whole human-only set.
    other = authorize_tool(
        "git_stage", "write", {"paths": []},
        allow_changes=False, allow_network=False, permission_mode="yolo",
        session_id="s1", workspace=tmp_path,
    )
    assert other.allowed is False
    assert other.authorization == "human_only_tool"


def test_without_a_session_the_git_writes_stay_denied() -> None:
    # No workspace and no session id means no allowlist door, so even a task
    # flag that says "changes allowed" cannot grant a human-only tool.
    decision = authorize_tool(
        "git_commit", "exec", {"message": "x"}, allow_changes=True, allow_network=False
    )
    assert decision.allowed is False
    assert decision.authorization == "human_only_tool"


def test_plan_mode_still_denies_the_git_writes(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", tool="git_commit")
    decision = authorize_tool(
        "git_commit", "exec", {"message": "x"},
        allow_changes=True, allow_network=False, permission_mode="plan",
        session_id="s1", workspace=tmp_path,
    )
    assert decision.allowed is False
    # It must deny as plan mode, not as a human-only tool: the CLI and the web
    # prompt only offer what they recognize, and plan mode must never prompt.
    assert decision.authorization == "plan_mode_exec"


def test_plan_mode_denies_git_stage_as_a_plan_write() -> None:
    decision = authorize_tool(
        "git_stage", "write", {"paths": []}, allow_changes=True, allow_network=False, permission_mode="plan"
    )
    assert decision.allowed is False
    assert decision.authorization == "plan_mode_write"


def test_a_git_write_counts_as_a_workspace_write() -> None:
    # Post-write verification is driven by is_workspace_write. If a commit or a
    # stage read as a no-op the loop would never ask for evidence after one, and
    # since a commit empties the working-tree diff there would be nothing left
    # to inspect either.
    from minicc.agent.tool_policy import is_workspace_write

    assert is_workspace_write("git_commit", {"message": "x"}, "ok") is True
    assert is_workspace_write("git_stage", {"paths": []}, "ok") is True
    # Controls: the readonly git tools are not writes, and a failed call never is.
    assert is_workspace_write("git_status", {}, "ok") is False
    assert is_workspace_write("git_diff", {}, "ok") is False
    assert is_workspace_write("git_commit", {"message": "x"}, "error") is False


def test_the_write_tool_set_has_exactly_one_definition() -> None:
    # loop.py used to carry a second copy of this set that nothing read. A stale
    # copy silently disagrees with the live one and no test could see it, so pin
    # the single defining file rather than the literal contents.
    found = []
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.match(r"\s*WRITE_TOOL_NAMES\s*=", line):
                found.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{number}")
    files = sorted({item.split(":")[0] for item in found})
    assert files == ["minicc/agent/tool_policy.py"], f"WRITE_TOOL_NAMES definitions: {found}"
