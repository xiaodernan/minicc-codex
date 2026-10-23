"""The user-cancel stamp on a task result must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.task_manager import _cancelled_result

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_overwrites_the_three_cancel_keys():
    stamped = _cancelled_result({"answer": "partial", "error": "boom", "cancelled": False})
    assert stamped == {
        "answer": "任务已取消。",
        "error": "任务已取消",
        "cancelled": True,
    }


def test_home_keeps_what_the_run_produced():
    stamped = _cancelled_result({"tokens_used": {"total_tokens": 5}})
    assert stamped["tokens_used"] == {"total_tokens": 5}
    assert stamped["cancelled"] is True


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"answer", "cancelled", "error"}
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {
                    key.value
                    for key in node.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
                if keys == target:
                    hits.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(hits) == 1, hits
    path, lineno = hits[0]
    assert path == "minicc/task_manager.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 24):lineno + 4])
    assert "def _cancelled_result" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/task_manager.py").read_text(encoding="utf-8")
    assert source.count("_cancelled_result(") == 3
