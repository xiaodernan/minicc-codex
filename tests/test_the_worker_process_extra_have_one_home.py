"""M8-T421 — worker 进程日志的结构化字段六个家：五条生命周期日志各抄一份"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_manager.py"

FIELDS = {"task_id", "pid"}


def test_the_home_builds_the_two_fields() -> None:
    """The constructor ties a log line to its task and its child process."""
    from minicc.task_manager import TaskManager

    extra = TaskManager._worker_process_extra("task-1", SimpleNamespace(pid=42))
    assert extra == {"task_id": "task-1", "pid": 42}
    # A process handle without a pid attribute must not raise.
    extra = TaskManager._worker_process_extra("task-1", SimpleNamespace())
    assert extra == {"task_id": "task-1", "pid": None}


def test_the_two_fields_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second projection."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the worker-process log fields are spelled by hand outside their "
        "one home: " + ", ".join(offenders)
    )


def test_no_site_spells_the_pid_fetch_itself() -> None:
    """Even the abort event's three-key spread must not re-fetch the pid.

    The abort event adds ``returncode``; if it went back to writing
    ``{"task_id": ..., "pid": getattr(process, "pid", None), ...}`` by
    hand, the two-field shape would silently have a second home.  The
    home definition is the only place that spells the getattr.
    """
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count('"pid": getattr(process, "pid", None)') == 1, (
        "the pid fetch must be spelled exactly once, inside the home"
    )


def test_every_lifecycle_event_asks_the_home() -> None:
    """Five call sites plus the abort spread, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_worker_process_extra(") == 7, (
        "the definition, the five two-field call sites and the abort "
        f"spread are the only spellings, found {source.count('_worker_process_extra(')}"
    )
