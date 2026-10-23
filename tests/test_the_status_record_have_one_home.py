"""The changed-file status record must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.changes import _status_record

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_three_keys():
    record = _status_record("a.py", "M", " M a.py")
    assert record == {"path": "a.py", "status": "M", "raw": " M a.py"}


def test_home_marks_audit_provenance():
    record = _status_record("b.md", "modified", "audit")
    assert record["raw"] == "audit"
    assert not record["raw"].startswith("??")


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"path", "raw", "status"}
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
    assert path == "minicc/changes.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 12):lineno + 3])
    assert "def _status_record" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/changes.py").read_text(encoding="utf-8")
    assert source.count("_status_record(") == 3
