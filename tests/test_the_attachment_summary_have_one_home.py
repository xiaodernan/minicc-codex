"""M8-T419 — 传输中的附件记录三个家：run/worker/batch 三个载荷各抄一份投影"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_manager.py"

FIELDS = {"name", "mime_type", "data_url"}
#: The stored shape is a different fact and stays where it is.
STORED_FIELDS = {"name", "mime_type", "size_bytes", "path"}


def test_the_home_builds_the_summary() -> None:
    """The constructor owns the transported shape and its data url."""
    from minicc.task_manager import _attachment_summary

    summary = _attachment_summary({
        "name": "a.png", "mime_type": "image/png",
        "data": b"\x89PNG\r\n\x1a\n",
    })
    assert set(summary) == FIELDS
    assert summary["name"] == "a.png"
    assert summary["mime_type"] == "image/png"
    assert summary["data_url"].startswith("data:image/png;base64,")


def test_the_transported_shape_is_not_the_stored_one() -> None:
    """The control: ATTACHMENT_FIELDS is the stored shape, a different fact."""
    from minicc.task_manager import ATTACHMENT_FIELDS

    assert set(ATTACHMENT_FIELDS) == STORED_FIELDS
    assert FIELDS != STORED_FIELDS, (
        "the transported shape must not be conflated with the stored one"
    )


def test_every_payload_builder_asks_the_home() -> None:
    """All three payload builders call the constructor, not their own dict."""
    source = (PACKAGE / "task_manager.py").read_text(encoding="utf-8")
    assert source.count("_attachment_summary(") == 4, (
        "the helper definition plus the run, worker and batch payloads are "
        f"the only spellings, found {source.count('_attachment_summary(')}"
    )


def test_the_summary_is_spelled_exactly_once_in_the_package() -> None:
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
        "the transported attachment record is spelled by hand outside its "
        "one home: " + ", ".join(offenders)
    )
