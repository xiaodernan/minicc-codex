"""M8-T424 — chat wire 的图片 part 两个家：归一器与附件投影各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/base.py"
SITES = ("minicc/agent/context.py", "minicc/task_manager.py")


def _chat_image_parts(tree: ast.AST) -> list[int]:
    """Line numbers of dict literals that spell the chat-wire image part.

    The fingerprint is exact: ``type`` must be the constant
    ``"image_url"`` - the Responses wire spells ``input_image`` and
    carries the url as a bare string, a different fact with the same
    two key names.  Key names alone would catch both wires.
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "type"
                and isinstance(value, ast.Constant)
                and value.value == "image_url"
            ):
                lines.append(node.lineno)
                break
    return lines


def test_the_home_builds_the_part() -> None:
    """The constructor owns the shape; detail is optional."""
    from minicc.llm.base import image_part

    part = image_part("data:image/png;base64,QUJD")
    assert part == {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
    detailed = image_part("u", "high")
    assert detailed["image_url"] == {"url": "u", "detail": "high"}
    assert image_part("u", "")["image_url"] == {"url": "u"}


def test_the_chat_image_part_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second projection."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for lineno in _chat_image_parts(tree):
            offenders.append(f"{relative}:{lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the chat-wire image part is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_every_builder_asks_the_home() -> None:
    """The context normalizer and the attachment projector both call it."""
    for site in SITES:
        source = (REPO / site).read_text(encoding="utf-8")
        assert source.count("image_part(") == 1, (
            f"{site} must call the home exactly once, found "
            f"{source.count('image_part(')}"
        )
