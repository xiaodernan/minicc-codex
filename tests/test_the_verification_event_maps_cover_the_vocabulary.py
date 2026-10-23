"""M8-T408 — 验证事件的两张逐状态表必须覆盖整个词表：缺一个状态就落进通用兜底"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = "minicc/agent/verifier.py"


def _to_event_maps() -> list[dict[str, ast.Dict]]:
    """The per-status dict literals inside ``VerificationResult.to_event``."""
    tree = ast.parse((REPO / HOME).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "VerificationResult":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "to_event":
                    maps: list[dict[str, ast.Dict]] = []
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Dict):
                            keys = {
                                key.value
                                for key in sub.keys
                                if isinstance(key, ast.Constant)
                                and isinstance(key.value, str)
                            }
                            maps.append({"node": sub, "keys": keys})
                    return maps
    raise AssertionError("VerificationResult.to_event not found")


def test_every_status_has_its_own_code_and_summary() -> None:
    """Both per-status maps cover the whole vocabulary.

    A status the maps miss does not fail loudly - ``.get(status, default)``
    quietly hands back the generic ``verification_finished`` / ``验证结束``.
    A new verification status would then look, on the event stream, exactly
    like an old generic finish: no code, no tailored summary, no hint.
    """
    from minicc.agent.verifier import VERIFICATION_STATUSES

    maps = _to_event_maps()
    covering = [item for item in maps if item["keys"] == set(VERIFICATION_STATUSES)]
    assert len(covering) == 2, (
        "to_event must carry exactly two per-status maps (code and summary), "
        f"both covering {sorted(VERIFICATION_STATUSES)}; found "
        f"{[sorted(item['keys']) for item in maps]}"
    )


def test_each_status_still_gets_its_specific_code() -> None:
    """Behavior unchanged: every status keeps its own code and summary."""
    from minicc.agent.verifier import VERIFICATION_STATUSES, VerificationResult

    for status in sorted(VERIFICATION_STATUSES):
        event = VerificationResult(status=status, command="pytest -q").to_event()
        assert event["code"] == f"verification_{status}", (
            f"{status} fell back to the generic code {event['code']!r}"
        )
        assert event["code"] != "verification_finished"
        assert event["summary"] != f"验证结束: pytest -q", event["summary"]
