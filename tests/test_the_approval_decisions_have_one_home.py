"""M8-T394 — 审批裁决三值两个家：web.py 两处放行子集 + 一处全集校验"""

from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/audit.py"

DECISIONS = frozenset({"allow", "always", "deny"})
PERMITTING = frozenset({"allow", "always"})


def test_the_home_exists_in_audit() -> None:
    """audit.py owns the decision vocabulary and its permitting subset."""
    from minicc.audit import APPROVAL_DECISIONS, PERMITTING_APPROVAL_DECISIONS

    assert APPROVAL_DECISIONS == DECISIONS
    assert PERMITTING_APPROVAL_DECISIONS == PERMITTING
    assert PERMITTING_APPROVAL_DECISIONS < APPROVAL_DECISIONS, (
        "the permitting subset must not grow to cover a deny"
    )


def test_web_consumes_the_same_objects() -> None:
    """web.py asks the home, not a copy of it."""
    from minicc import audit, web

    assert web.APPROVAL_DECISIONS is audit.APPROVAL_DECISIONS
    assert web.PERMITTING_APPROVAL_DECISIONS is audit.PERMITTING_APPROVAL_DECISIONS


def test_no_module_inlines_the_decisions() -> None:
    """No module spells either set as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) < 2:
                continue
            if elements == DECISIONS:
                offenders.append(f"{relative}:{node.lineno} spells APPROVAL_DECISIONS")
            if elements == PERMITTING:
                offenders.append(f"{relative}:{node.lineno} spells PERMITTING_APPROVAL_DECISIONS")
    # Exactly the two home declarations in audit.py: the full vocabulary and
    # its permitting subset.  A third spelling anywhere - even inside audit.py
    # itself - is drift.
    assert len(offenders) == 2 and all(item.startswith(HOME + ":") for item in offenders), (
        "the approval decisions are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def _config() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )


def test_the_gate_still_rejects_an_unknown_decision(tmp_path: Path) -> None:
    """resolve_approval validates against the home before touching state."""
    from minicc.web import AgentService

    service = AgentService(tmp_path, _config())
    with pytest.raises(ValueError, match="allow\\|always\\|deny"):
        service.resolve_approval("no-such-request", "sometimes")
