"""The scan warning shape and its cap must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc import impact

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_appends_the_two_key_shape():
    warnings: list[dict[str, str]] = []
    impact._append_warning(warnings, "a.py", "boom")
    assert warnings == [{"path": "a.py", "reason": "boom"}]


def test_home_caps_the_list():
    warnings: list[dict[str, str]] = [{"path": "x", "reason": "y"}] * impact._MAX_WARNINGS
    impact._append_warning(warnings, "late.py", "too many")
    assert len(warnings) == impact._MAX_WARNINGS


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"path", "reason"}
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
    assert path == "minicc/impact.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 16):lineno + 4])
    assert "def _append_warning" in window, window


def test_call_sites_and_cap_use_the_home():
    source = (REPO / "minicc/impact.py").read_text(encoding="utf-8")
    assert source.count("_append_warning(") == 5
    assert source.count("_MAX_WARNINGS") == 2
    assert "len(warnings) < 100" not in source
