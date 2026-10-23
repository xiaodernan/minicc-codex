"""M8-T435 — 内存附件记录四键两个家：归一器与磁盘读回各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_manager.py"

FIELDS = {"data", "mime_type", "name", "size_bytes"}


def test_the_home_builds_the_record() -> None:
    """The constructor owns the four keys of the in-memory record."""
    from minicc.task_manager import _attachment_record

    record = _attachment_record("a.png", "image/png", 4, b"data")
    assert record == {
        "name": "a.png",
        "mime_type": "image/png",
        "size_bytes": 4,
        "data": b"data",
    }


def test_the_four_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second record shape.

    ``ATTACHMENT_FIELDS`` is a tuple (the payload shape with ``path``),
    not a dict literal, so it cannot collide with this census.
    """
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
        "the in-memory attachment record is spelled by hand outside its "
        "one home: " + ", ".join(offenders)
    )


def test_both_sites_ask_the_home() -> None:
    """The normalizer, the loader, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_attachment_record(") == 3, (
        "the definition plus the normalizer and the loader are the "
        f"only spellings, found {source.count('_attachment_record(')}"
    )
