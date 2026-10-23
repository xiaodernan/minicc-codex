"""The task-snapshot write-failure log event must have exactly one home.

Three sites log a task snapshot that never landed: the persistence drain
loop, the persistence close drain, and the service shutdown in
``task_manager``.  They shared the event name and the
``task_id=``/``error=`` skeleton, and each spelled them out by hand - so a
rename in one place silently removed that site from the grep an operator
runs to find snapshots that never landed.  Nothing fails; a third of the
evidence just stops existing.

This door pins:

* the event name is spelled once, in ``task_persistence``;
* the builder is defined once and called from exactly the three sites;
* each site passes its own middle field, and nothing else is free-form;
* the composed line is byte-for-byte what it was.
"""

from __future__ import annotations

import ast
import logging
import pathlib

from minicc.task_persistence import (
    TASK_SNAPSHOT_WRITE_FAILED,
    task_snapshot_write_failed_event,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/task_persistence.py"
BUILDER = "task_snapshot_write_failed_event"
EVENT = TASK_SNAPSHOT_WRITE_FAILED

EXPECTED_MIDDLES = {"source=drain_loop", "attempt=%d", "source=shutdown"}


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _carriers(needle: str) -> list[str]:
    """Every string constant carrying the needle - f-string parts included."""
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if needle in node.value:
                    hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return hits


def test_the_event_name_is_one_constant():
    assert EVENT == "task_snapshot_write_failed"


def test_the_builder_is_the_event_name_then_the_skeleton():
    assert task_snapshot_write_failed_event("source=x") == (
        "task_snapshot_write_failed task_id=%s source=x error=%s: %s"
    )


def test_the_event_name_is_spelled_in_exactly_one_place():
    hits = _carriers(EVENT)
    assert len(hits) == 1, hits
    assert hits[0].startswith(f"{HOME}:"), hits


def test_no_other_constant_starts_with_the_event_name():
    """A hand-written copy is exactly this shape: the name, then a middle."""
    strays = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith(EVENT) and node.value != EVENT:
                    strays.append((path.as_posix(), node.lineno, node.value[:60]))
    assert strays == [], strays


def test_the_builder_is_defined_exactly_once():
    definitions = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == BUILDER:
                definitions.append(path.relative_to(REPO).as_posix())
    assert definitions == [HOME], definitions


def test_the_builder_is_called_from_exactly_the_three_sites():
    sites = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == BUILDER:
                sites.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    assert len(sites) == 3, sites
    assert sum(site.startswith(f"{HOME}:") for site in sites) == 2, sites
    assert sum(site.startswith("minicc/task_manager.py:") for site in sites) == 1, sites


def test_only_the_three_known_middles_reach_the_builder():
    """The middle is the live part, and it is a closed set."""
    middles = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == BUILDER:
                first = node.args[0] if node.args else None
                middles.append(first.value if isinstance(first, ast.Constant) else None)
    assert set(middles) == EXPECTED_MIDDLES, middles
    assert all(isinstance(m, str) for m in middles), middles


def test_the_composed_lines_are_byte_for_byte_what_they_were():
    assert task_snapshot_write_failed_event("source=drain_loop") == (
        "task_snapshot_write_failed task_id=%s source=drain_loop error=%s: %s"
    )
    assert task_snapshot_write_failed_event("attempt=%d") == (
        "task_snapshot_write_failed task_id=%s attempt=%d error=%s: %s"
    )
    assert task_snapshot_write_failed_event("source=shutdown") == (
        "task_snapshot_write_failed task_id=%s source=shutdown error=%s: %s"
    )


def test_the_logger_formats_the_line_the_way_the_sites_meant(caplog):
    """A real round trip: the format string still interpolates as before."""
    with caplog.at_level(logging.WARNING, logger="minicc.task"):
        line = task_snapshot_write_failed_event("source=drain_loop")
        caplog.clear()
        logging.getLogger("minicc.task").warning(line, "task-1", "OSError", "disk full")
    record = next(r for r in caplog.records if EVENT in r.getMessage())
    assert "task_snapshot_write_failed task_id=task-1 source=drain_loop" in record.getMessage()
    assert "error=OSError: disk full" in record.getMessage()
