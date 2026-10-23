"""The channel status snapshot must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.llm.usage import channel_status_payload

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_three_keys():
    payload = channel_status_payload("paid", True, {"paid": {"requests": 1, "total_tokens": 2}})
    assert payload == {
        "active": "paid",
        "plan_available": True,
        "usage": {"paid": {"requests": 1, "total_tokens": 2}},
    }


def test_home_copies_counters_so_readers_cannot_mutate_live_state():
    live = {"paid": {"requests": 1, "total_tokens": 2}}
    snapshot = channel_status_payload("paid", False, live)
    snapshot["usage"]["paid"]["requests"] = 999
    assert live["paid"]["requests"] == 1


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"active", "plan_available", "usage"}
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
    assert path == "minicc/llm/usage.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 18):lineno + 6])
    assert "def channel_status_payload" in window, window


def test_call_sites_use_the_home():
    count = 0
    for path in sorted((REPO / "minicc").rglob("*.py")):
        count += path.read_text(encoding="utf-8").count("channel_status_payload(")
    assert count == 3, count
