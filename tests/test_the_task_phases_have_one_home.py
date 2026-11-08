"""M8-T612 — the task phase vocabulary has one home.

Phase values (``planning``, ``permission``, ``review``, …) are emitted by the
Python runtime as ``phase=`` kwargs and ``"phase"`` dict keys, and recognized
by the web frontend (``state.js:TASK_PHASES``).  Spelling them as bare string
literals at 100+ call sites lets either side drift from the other.

The Python home is ``minicc.agent.protocol`` (``TASK_PHASES`` plus individual
``PHASE_*`` constants).  Production code in ``minicc/`` must ask that home
instead of bare-literal phase values.  The frontend ``TASK_PHASES`` is pinned
to the Python home by value.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"
JS_HOME = REPO / "web" / "src" / "core" / "state.js"


def _known_phases() -> frozenset[str]:
    from minicc.agent.protocol import TASK_PHASES

    return TASK_PHASES


def test_the_home_defines_all_phases() -> None:
    from minicc.agent.protocol import TASK_PHASES

    expected = {
        "queued", "planning", "intake", "tool", "execution", "answering",
        "summarize", "review", "verify", "repair", "permission", "merging",
        "completed", "failed", "cancelled", "interrupted",
    }
    assert set(TASK_PHASES) == expected


def test_no_bare_phase_literals_in_minicc_outside_home() -> None:
    known = _known_phases()
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(path))
        except Exception:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "phase":
                if isinstance(node.value, ast.Constant) and node.value.value in known:
                    offenders.append(f"{rel}:{node.lineno} phase={node.value.value!r}")
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "phase"
                        and isinstance(v, ast.Constant)
                        and v.value in known
                    ):
                        offenders.append(f"{rel}:{v.lineno} dict phase {v.value!r}")
    assert offenders == [], (
        "bare phase literals found outside minicc/agent/protocol.py - ask the "
        "PHASE_* constants / TASK_PHASES home instead:\n" + "\n".join(offenders)
    )


def test_js_task_phases_match_python_home() -> None:
    from minicc.agent.protocol import TASK_PHASES

    js = JS_HOME.read_text(encoding="utf-8")
    m = re.search(r"export const TASK_PHASES = new Set\(\[([\s\S]*?)\]\)", js)
    assert m, "state.js must export TASK_PHASES"
    js_phases = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert js_phases == set(TASK_PHASES), (
        f"JS TASK_PHASES {sorted(js_phases)} != Python TASK_PHASES {sorted(TASK_PHASES)}"
    )
