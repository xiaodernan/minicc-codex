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


def _result_field_values() -> dict[str, str]:
    """Resolve the contract constant names to their values (one source: task_contract)."""
    from minicc import task_contract

    return {
        value_name: getattr(task_contract, value_name)
        for value_name in dir(task_contract)
        if value_name.startswith("RESULT_FIELD_")
    }


def _resolve_dict_keys(node: ast.Dict, names: dict[str, str]) -> set[str]:
    """The dict's key vocabulary, with contract constants resolved to their values.

    M8-T672: the literal-only census missed the home the moment the home itself
    switched to ``RESULT_FIELD_*`` constants - exactly the drift the contract
    batch was built to cause and probe for.  The census asks the same question
    of both spellings: which files spell the cancel-result three-key shape by
    hand.  A contract-constant spelling counts the same.
    """
    values = set(names.values())
    keys: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
        elif isinstance(key, ast.Name) and key.id in names:
            keys.add(names[key.id])
        elif isinstance(key, ast.Attribute) and key.attr in names:
            keys.add(names[key.attr])
    return keys


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"answer", "cancelled", "error"}
    names = _result_field_values()
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = _resolve_dict_keys(node, names)
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
