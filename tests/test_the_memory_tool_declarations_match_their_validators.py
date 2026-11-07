"""M8-T594 — the memory tools' declared parameters match their validator.

``MemoryTools.list_entries`` clamps ``limit`` to [1, 100] and defaults it to
``DEFAULT_LIST_LIMIT = 20``; ``MemoryTools.write`` rejects content over
``MAX_MEMORY_CHARS = 500`` and truncates source to ``MAX_SOURCE_CHARS = 40``
(it is capped, not rejected, by design). The tool registration in
``tools/__init__.py`` declares the same three limits as ``Param`` caps —
hand-spelled, so today's agreement is an accident, not a fact.

This gate pins:

* ``mem_content_p.max_len == memory.MAX_MEMORY_CHARS`` (= 500);
* ``mem_source_p.max_len == memory.MAX_SOURCE_CHARS`` (= 40);
* ``mem_limit_p`` has ``min_value=1`` and ``max_value=100``, and
  ``memory.DEFAULT_LIST_LIMIT == 20``;
* (boundary: the clamp *expression* in the validator is not pinned — the
  numbers on both faces are).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS_INIT = REPO / "minicc" / "tools" / "__init__.py"


def _param_calls(tree: ast.Module):
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        target = node.targets[0].id
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Param"):
            continue
        kwargs = {kw.arg: kw.value for kw in value.keywords}

        def const(name, kwargs=kwargs):
            node_ = kwargs.get(name)
            return node_.value if isinstance(node_, ast.Constant) else None

        yield target, const


def test_the_memory_tool_declarations_match_their_validator() -> None:
    import minicc.tools.memory as memory_mod

    assert memory_mod.MAX_MEMORY_CHARS == 500
    assert memory_mod.MAX_SOURCE_CHARS == 40
    assert memory_mod.DEFAULT_LIST_LIMIT == 20

    tree = ast.parse(TOOLS_INIT.read_text(encoding="utf-8"), filename=str(TOOLS_INIT))
    params = dict(_param_calls(tree))

    mem_content = params.get("mem_content_p")
    mem_source = params.get("mem_source_p")
    mem_limit = params.get("mem_limit_p")
    assert mem_content is not None and mem_source is not None and mem_limit is not None, (
        "the memory tool Param declarations were not found"
    )

    assert mem_content("max_len") == memory_mod.MAX_MEMORY_CHARS, (
        f"mem_content_p.max_len ({mem_content('max_len')}) drifted from memory.MAX_MEMORY_CHARS ({memory_mod.MAX_MEMORY_CHARS})"
    )
    assert mem_source("max_len") == memory_mod.MAX_SOURCE_CHARS, (
        f"mem_source_p.max_len ({mem_source('max_len')}) drifted from memory.MAX_SOURCE_CHARS ({memory_mod.MAX_SOURCE_CHARS})"
    )
    assert mem_limit("min_value") == 1
    assert mem_limit("max_value") == 100
