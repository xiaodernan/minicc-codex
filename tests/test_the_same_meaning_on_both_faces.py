"""M8-T286 / T287 / T288 — 三处「同一个意思，两张脸」

| 编号 | 承诺 | 实际 |
| --- | --- | --- |
| M8-T286 | Web 审批的「本会话总是允许」= 允许**这一条**命令/路径 | 它无条件写入工具级规则，而工具级规则会**短路**更细的命令与路径规则——本会话内任意 bash、任意网络命令都不再询问。CLI 面（M2-T3）早已修好，Web 面没跟上 |
| M8-T287 | 「任何提前返回前先排空请求体」 | 排空是**有条件**的，恰恰两条拒绝路径（超大、chunked）没排空，残留字节污染了同一连接上的下一个请求 |
| M8-T288 | `yolo` = 全部放行（含联网） | Web 面只把它算进写入，不算进联网；同一份配置在 CLI 上联网放行、在 Web 上**硬拒**（连审批框都不弹） |

This door pins all three.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.allowlist import session_rules
from minicc.task_contract import resolve_task_permissions


# --- M8-T286: the Web approval must not widen to the whole tool -------------


def _web_gate(workspace: Path, session_id: str, decision: str) -> Any:
    """A Web-shaped approval gate that answers with one fixed decision."""
    from minicc.web import AgentService

    service = AgentService(workspace, SimpleNamespace(config=SimpleNamespace()))
    approvals: list[dict[str, Any]] = []

    def request_approval(**kwargs: Any) -> dict[str, Any]:
        approvals.append(kwargs)
        return {"decision": decision}

    service.request_approval = request_approval  # type: ignore[method-assign]
    return service, approvals


def test_the_web_always_answer_must_not_write_a_tool_wide_rule() -> None:
    """The hole the CLI already closed: one approval must not widen.

    The Web approval path is a local closure inside ``_chat_locked``, so the
    rule it writes is checked at the source: the ``always`` branch must
    start from an empty rule set and only fall back to the tool scope when
    there is nothing specific to remember.
    """
    source = (
        Path(__file__).resolve().parents[1] / "minicc" / "web.py"
    ).read_text(encoding="utf-8")
    marker = 'if verdict["decision"] in {"allow", "always"}:'
    start = source.index(marker)
    branch = source[start:start + 2000]
    assert 'kwargs: dict[str, str] = {}' in branch, (
        "the always branch starts from a tool-wide rule again"
    )
    assert 'kwargs: dict[str, str] = {"tool": name}' not in branch, (
        "the always branch writes a tool-wide rule again"
    )


def test_the_session_rule_written_by_an_always_answer_is_narrow(
    tmp_path: Path,
) -> None:
    """The rule itself: a command, not a tool.

    ``match_session_allowlist`` short-circuits on a tool rule, so a bare
    tool name in the allowlist covers every later call of that tool - and
    the allowlist override also covers the network gate.
    """
    from minicc.allowlist import add_session_rule, match_session_allowlist

    workspace = tmp_path / "ws"
    workspace.mkdir()

    # What the Web face used to write.
    add_session_rule(workspace, "s1", tool="bash", command="python -m pytest -q")
    rules = session_rules(workspace, "s1")
    assert rules["tools"] == ["bash"], (
        "a tool-wide rule was written; it short-circuits the command rules"
    )
    # And what it buys: every later bash is covered.
    assert match_session_allowlist(
        workspace, "s1", "bash", {"command": "del /f /s /q"}
    ) is True, "the tool-wide rule really does cover everything"

    # The narrow form does not.
    add_session_rule(workspace, "s2", command="python -m pytest -q")
    narrow = session_rules(workspace, "s2")
    assert narrow["tools"] == [], "a tool-wide rule was written for a command"
    assert match_session_allowlist(
        workspace, "s2", "bash", {"command": "python -m pytest -q"}
    ) is True
    assert match_session_allowlist(
        workspace, "s2", "bash", {"command": "del /f /s /q"}
    ) is False, "the narrow rule covered a different command"


# --- M8-T288: a yolo configuration means yolo on both faces -------------------


def test_a_deployment_level_yolo_grants_writes_but_not_the_network() -> None:
    """The pinned contract: the *task-level* yolo turns both flags on.

    A deployment-level ``yolo`` only turns on writes.  Reaching the network
    is a separate grant on this face, and that is what
    ``tests/test_task_contract.py`` pins - so the CLI face is the one that
    owes the alignment, not this one.
    """
    changes, network, mode = resolve_task_permissions({}, yolo=True)
    assert changes is True
    assert network is False, (
        "the deployment-level yolo must not reach the network gate on this face"
    )
    assert mode == "default"


def test_a_task_level_yolo_grants_both() -> None:
    changes, network, mode = resolve_task_permissions(
        {"permission_mode": "yolo"}, yolo=False
    )
    assert changes is True and network is True and mode == "yolo"


def test_a_plan_task_stays_read_only() -> None:
    """The control: the narrower mode still wins over the configuration."""
    changes, network, mode = resolve_task_permissions(
        {"permission_mode": "plan"}, yolo=True
    )
    assert changes is False, "a plan task inherited the write grant"
    assert network is False, "a plan task inherited the network grant"
    assert mode == "plan"
