"""M8-T638 — task_manager runtime phase literals use protocol PHASE_* homes.

Covers phase-field/phase-variable facts in `minicc.task_manager` (including
overlapping values like cancelled/failed/interrupted/queued which are distinct
from TASK_STATUS_* facts). Completion vocabulary like `"complete"` is out of
scope.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {REPO / "minicc" / "task_manager.py"}

PHASE_VALUES = {
    "queued", "planning", "intake", "tool", "execution", "answering",
    "summarize", "review", "verify", "repair", "permission", "merging",
    "completed", "failed", "cancelled", "interrupted",
}
OVERLAP = {"queued", "completed", "failed", "cancelled", "interrupted", "running"}
PHASE_CTX = re.compile(r"(\.phase\b|\bphase\s*[:=])")


def _phase_context(line: str, node: ast.Constant, src: str) -> bool:
    if node.value not in OVERLAP:
        # phase-only values can appear as phase facts; require phase-ish context
        # to avoid flagging unrelated text, but be permissive.
        return PHASE_CTX.search(line) is not None or "set_phase" in line
    # overlapping value: only phase context, and not a pure status assignment line
    if not PHASE_CTX.search(line):
        return False
    if re.search(r"\.status\b|\bstatus\s*[:=]", line) and ".phase" not in line and "phase =" not in line.split("#")[0].replace("status", "", 1):
        # rough: if status is the dominant target and no clear phase target, skip
        pass
    # if line has .phase or `phase =` as a target, treat as phase context
    stripped = line.split("#")[0]
    if ".phase" in stripped or re.search(r"\bphase\s*=", stripped):
        # but exclude cases where it's only status? e.g. "status = TASK...; phase ="
        # both present - a literal on the phase side would be on a line; AST gives lineno.
        return True
    if re.search(r"\bphase\s*:", stripped):
        return True
    return False


def test_no_bare_phase_literals_in_task_manager_phase_contexts() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        rel = path.relative_to(REPO).as_posix()
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in PHASE_VALUES:
                continue
            line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            if node.value == "complete":
                continue
            if _phase_context(line, node, src):
                offenders.append(f"{rel}:{node.lineno}: {line.strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare runtime phase literal in task_manager phase context - use PHASE_* "
        "from minicc.agent.protocol (TASK_STATUS_* is a different fact):\n"
        + "\n".join(offenders)
    )
