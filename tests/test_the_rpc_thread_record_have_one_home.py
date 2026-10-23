"""M8-T423 — RPC thread 记录六键两个家：认领与启动各铸一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/web.py"

FIELDS = {
    "created_at_epoch", "id", "session_id",
    "task_thread_id", "thread_id", "workspace_path",
}


def test_the_home_builds_the_record() -> None:
    """The constructor owns the six keys; id mirrors thread_id."""
    from minicc.web import _new_thread_record

    record = _new_thread_record(
        thread_id="t-1",
        session_id="s-1",
        workspace_path="/ws",
        task_thread_id="t-0",
        created_at_epoch=123.0,
    )
    assert set(record) == FIELDS
    assert record["id"] == record["thread_id"] == "t-1"
    assert record["task_thread_id"] == "t-0"
    assert record["created_at_epoch"] == 123.0


def test_the_six_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second mint."""
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
        "the RPC thread record is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_mints_ask_the_home() -> None:
    """The adoption site and the start site both call the constructor."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_new_thread_record(") == 3, (
        "the definition plus the two mints are the only spellings, "
        f"found {source.count('_new_thread_record(')}"
    )
