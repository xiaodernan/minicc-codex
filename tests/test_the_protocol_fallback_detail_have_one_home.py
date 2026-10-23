"""The protocol fallback trace detail must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.llm import openai_provider

REPO = pathlib.Path(__file__).resolve().parents[1]


def _dict_literals_with_keys(target: set[str]) -> list[tuple[str, int]]:
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
    return hits


def test_home_passes_both_keys_through():
    detail = openai_provider.protocol_fallback_detail(ValueError("boom"))
    assert detail == {"protocol": "chat_completions", "error_type": "ValueError"}


def test_census_exactly_one_literal_and_it_is_the_home():
    hits = _dict_literals_with_keys({"protocol", "error_type"})
    assert len(hits) == 1, hits
    path, lineno = hits[0]
    assert path == "minicc/llm/openai_provider.py"
    source = pathlib.Path(REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 14):lineno + 3])
    assert "def protocol_fallback_detail" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/llm/openai_provider.py").read_text(encoding="utf-8")
    assert source.count("protocol_fallback_detail(") == 3
