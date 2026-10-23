"""M8-T386 — 多模态部件类型 {image_url, input_image}：context.py 有家却有两处行内拼写"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/context.py"

VISUAL_PART_TYPES = frozenset({"image_url", "input_image"})


def test_the_home_exists_in_context() -> None:
    """context.py owns the visual part types with both members."""
    from minicc.agent.context import VISUAL_PART_TYPES as Home

    assert Home == VISUAL_PART_TYPES


def test_loop_asks_the_home() -> None:
    """loop.py uses the same object, not its own spelling."""
    import minicc.agent.context as context
    import minicc.agent.loop as loop

    assert loop.VISUAL_PART_TYPES is context.VISUAL_PART_TYPES


def test_no_module_inlines_the_visual_part_types() -> None:
    """No module spells the two part types as a literal - the home included."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == VISUAL_PART_TYPES:
                offenders.append(f"{relative}:{node.lineno}")
    # The home may spell it exactly once - its declaration.  Any other file,
    # or a second spelling inside the home, is a drifted copy.
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the visual part types are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_the_readers_still_recognize_visual_parts() -> None:
    """Both readers still answer from the home."""
    from minicc.agent.context import has_visual_content, normalize_vision_context

    messages = [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://x/y.png"}}]},
    ]
    assert has_visual_content(messages) is True
    assert has_visual_content([{"role": "user", "content": "plain"}]) is False
    parts = [
        {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
        {"type": "input_image", "image_url": {"url": "https://x/z.png"}},
        {"type": "text", "text": "not a visual part"},
        {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
    ]
    normalized = normalize_vision_context(parts)
    assert [part["image_url"]["url"] for part in normalized] == [
        "https://x/y.png",
        "https://x/z.png",
    ]
