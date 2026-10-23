"""The event-arguments reconstruction must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.agent import completion

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_command_and_background_flag():
    args = completion._event_arguments({"command": "pytest -q", "background": True})
    assert args == {"command": "pytest -q", "run_in_background": True}


def test_home_survives_missing_fields():
    assert completion._event_arguments({}) == {"command": "", "run_in_background": False}
    assert completion._event_arguments({"command": None})["command"] == ""


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"command", "run_in_background"}
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
    assert path == "minicc/agent/completion.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 16):lineno + 4])
    assert "def _event_arguments" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/agent/completion.py").read_text(encoding="utf-8")
    assert source.count("_event_arguments(") == 3
