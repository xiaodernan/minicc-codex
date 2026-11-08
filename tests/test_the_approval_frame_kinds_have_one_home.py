"""M8-T611 — the approval frame kinds have one home.

The interactive approval flow carries two SSE frame kinds across the
Python→JS wire: ``"approval_request"`` (agent is waiting for a human
decision) and ``"approval_resolved"`` (the decision landed).  The values
are the same fact on both faces; spelling them as bare literals in the
emitter and the consumer lets either side drift silently.

The Python home is ``minicc.audit`` (the approval vocabulary module,
which already owns ``APPROVAL_DECISIONS``).  ``minicc.web`` emits the
frames and must ask that home; ``web/src/core/approvals.js`` consumes
them and exports its own named constants, pinned to the Python home by
the frontend smoke.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "audit.py"

KINDS = {"approval_request": "APPROVAL_FRAME_REQUEST_KIND", "approval_resolved": "APPROVAL_FRAME_RESOLVED_KIND"}


def test_the_home_defines_the_frame_kinds() -> None:
    from minicc.audit import APPROVAL_FRAME_REQUEST_KIND, APPROVAL_FRAME_RESOLVED_KIND

    assert APPROVAL_FRAME_REQUEST_KIND == "approval_request"
    assert APPROVAL_FRAME_RESOLVED_KIND == "approval_resolved"


def test_web_emits_the_frame_kinds_from_the_home() -> None:
    """web.py must not spell the frame kind literals as ``kind=`` values."""
    web = (PACKAGE / "web.py").read_text(encoding="utf-8")
    tree = ast.parse(web, filename=str(PACKAGE / "web.py"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        # catch kind="approval_request" / kind="approval_resolved" in calls/dicts
        if isinstance(node, ast.keyword) and node.arg == "kind":
            if isinstance(node.value, ast.Constant) and node.value.value in KINDS:
                offenders.append(f"minicc/web.py:{node.lineno} kind={node.value.value!r}")
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "kind"
                    and isinstance(v, ast.Constant)
                    and v.value in KINDS
                ):
                    offenders.append(f"minicc/web.py:{v.lineno} kind dict {v.value!r}")
    assert offenders == [], (
        "web.py spells approval frame kinds as bare literals - ask "
        "minicc.audit.APPROVAL_FRAME_*_KIND instead:\n" + "\n".join(offenders)
    )


def test_web_imports_the_frame_kinds_from_audit() -> None:
    src = (PACKAGE / "web.py").read_text(encoding="utf-8")
    for name in KINDS.values():
        assert name in src, f"minicc/web.py must reference {name} from the audit home"
