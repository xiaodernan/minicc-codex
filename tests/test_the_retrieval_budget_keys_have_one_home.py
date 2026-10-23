"""M8-T405 — 检索预算键两个家：校验器与提取器各写一份 ("max_files", "max_directories")"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/benchmarks.py"

KEYS = ("max_files", "max_directories")


def test_the_home_exists_in_benchmarks() -> None:
    """benchmarks.py owns the retrieval budget's keys."""
    from minicc.benchmarks import RETRIEVAL_BUDGET_KEYS

    assert RETRIEVAL_BUDGET_KEYS == KEYS


def test_no_module_inlines_the_budget_keys() -> None:
    """No module spells the key tuple as a literal outside the declaration."""
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
            elements = tuple(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and sorted(elements) == sorted(KEYS):
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the retrieval budget keys are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_a_budget_key_survives_validation_and_extraction(tmp_path: Path) -> None:
    """Behavior unchanged: a stated budget key is validated and passed through."""
    from minicc.benchmarks import load_retrieval_cases

    def _write(data: dict) -> Path:
        path = tmp_path / "cases.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    good_case = {"id": "c1", "query": "read_file", "targets": ["minicc/tools/registry.py"]}
    loaded = load_retrieval_cases(_write({
        "cases": [good_case], "ks": [5], "max_files": 40, "max_directories": 12,
    }))
    assert loaded["max_files"] == 40
    assert loaded["max_directories"] == 12

    with pytest.raises(ValueError, match="max_files"):
        load_retrieval_cases(_write({"cases": [good_case], "ks": [1], "max_files": 0}))
    with pytest.raises(ValueError, match="max_files"):
        load_retrieval_cases(_write({"cases": [good_case], "ks": [1], "max_files": True}))
