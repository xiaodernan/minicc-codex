"""M8-T635 — hook event name vocabulary has one home.

Hook event identities `PreToolUse`/`PostToolUse`/`UserPromptSubmit`/`Stop` are
produced/checked in `minicc.hooks` and consumed in `minicc.agent.loop`. Bare
literals duplicate the same hook-event fact. The one home is `minicc.hooks`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "hooks.py"
SCOPED = {HOME, PACKAGE / "agent" / "loop.py"}

EVENTS = {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"}
CONST_NAMES = {
    "HOOK_EVENT_PRE_TOOL_USE",
    "HOOK_EVENT_POST_TOOL_USE",
    "HOOK_EVENT_USER_PROMPT_SUBMIT",
    "HOOK_EVENT_STOP",
}


def test_the_home_defines_hook_event_constants() -> None:
    import minicc.hooks as h

    assert h.HOOK_EVENT_PRE_TOOL_USE == "PreToolUse"
    assert h.HOOK_EVENT_POST_TOOL_USE == "PostToolUse"
    assert h.HOOK_EVENT_USER_PROMPT_SUBMIT == "UserPromptSubmit"
    assert h.HOOK_EVENT_STOP == "Stop"
    assert h.HOOK_EVENTS == ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop")


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()

    def mark(body: list[ast.stmt]) -> None:
        if not body:
            return
        node = body[0]
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            ids.add(id(node.value))

    if isinstance(tree, ast.Module):
        mark(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mark(node.body)
    return ids


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def test_no_bare_hook_event_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        docs = _docstring_ids(tree)
        rel = path.relative_to(REPO).as_posix()
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in EVENTS:
                continue
            if id(node) in docs:
                continue
            if path == HOME and _allowed(node, parents):
                continue
            offenders.append(f"{rel}:{node.lineno}: {lines[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare hook event literal - ask HOOK_EVENT_* from minicc.hooks:\n"
        + "\n".join(offenders)
    )
