"""The model catalog reply must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc import web

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_two_keys_without_error():
    payload = web._models_payload([{"id": "m1"}], "m1")
    assert payload == {"models": [{"id": "m1"}], "default_model": "m1"}
    assert "error" not in payload


def test_home_adds_error_only_when_present():
    payload = web._models_payload([{"id": "m1"}], "m1", "网关未返回模型列表")
    assert payload["error"] == "网关未返回模型列表"
    empty = web._models_payload([{"id": "m1"}], "m1", "")
    assert "error" not in empty


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"default_model", "models"}
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
                if target <= keys:
                    hits.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(hits) == 1, hits
    path, lineno = hits[0]
    assert path == "minicc/web.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 20):lineno + 4])
    assert "def _models_payload" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/web.py").read_text(encoding="utf-8")
    assert source.count("_models_payload(") == 3
