"""M8-T513 — hook denied 默认判词三个家：hook 拒绝而不解释时说的那句话

一个 hook 拒绝工具调用却什么都没说时，用户看到的是默认判词
``hook denied``。这句话有三个手拼家：`HookOutcome.denial_reason` 的每
条目回退（有 deny 条目但 reason 为空）、它的「什么都没拒」回退、以及
runner 里 deny 退出码且无输出的分支。三处漂移的后果是同一事件在不同路
径上给出不同解释——按消息匹配的上层（和人）对不上账。

家安在 `minicc/hooks.py` 模块常量区，`HOOK_DENY_EXIT` 旁边：默认判词
和触发它的退出码是同一事实的两半。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from minicc.hooks import DEFAULT_DENY_REASON, HookOutcome, HookRunner

REPO = Path(__file__).resolve().parents[1]
HOME = "minicc/hooks.py"
PAYLOAD: dict[str, Any] = {
    "event": "PreToolUse",
    "tool": "write_file",
    "arguments": {"path": "notes.md"},
}
DENY_COMMAND = "exit 2"  # HOOK_DENY_EXIT; cmd.exe / sh both leave errorlevel 2


def test_the_home_pins_the_default() -> None:
    assert DEFAULT_DENY_REASON == "hook denied"


def test_the_default_is_spelled_exactly_once() -> None:
    hits: list[tuple[str, int]] = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == DEFAULT_DENY_REASON:
                hits.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(hits) == 1 and hits[0][0] == HOME, hits


def test_the_reason_reader_asks_the_home() -> None:
    # The per-entry fallback: a deny entry whose reason is empty.
    empty_reason = HookOutcome(
        decision="deny", outputs=[{"decision": "deny", "reason": ""}]
    )
    assert empty_reason.denial_reason() == "hook denied"
    # The nothing-denied fallback.
    assert HookOutcome(decision="deny", outputs=[]).denial_reason() == "hook denied"
    # The control: a reason that exists travels unchanged - the default is a
    # fallback, not an override.
    with_reason = HookOutcome(
        decision="deny", outputs=[{"decision": "deny", "reason": "no secrets"}]
    )
    assert with_reason.denial_reason() == "no secrets"


def test_the_runner_asks_the_home(tmp_path: Path) -> None:
    runner = HookRunner(
        tmp_path,
        config={"hooks": {"PreToolUse": [{"command": DENY_COMMAND}]}},
    )
    outcome = runner.run("PreToolUse", PAYLOAD)
    assert outcome.denied, outcome.outputs
    entry = outcome.outputs[0]
    assert entry["decision"] == "deny", entry
    # A deny exit with no stdout and no stderr falls back to the one default.
    assert entry["reason"] == "hook denied", entry
    assert outcome.denial_reason() == "hook denied", entry
