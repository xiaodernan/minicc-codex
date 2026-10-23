"""M8-T412 — wire 工具调用记录八个家：agent 循环与三个 provider 各手抄一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/base.py"

#: Every module that builds a wire tool call and now asks the home for it.
BUILDERS = (
    "minicc/agent/loop.py",
    "minicc/llm/anthropic_provider.py",
    "minicc/llm/envelope.py",
    "minicc/llm/fake.py",
    "minicc/llm/openai_provider.py",
)


def _wire_tool_call_literals(path: Path) -> list[ast.Dict]:
    """Dict literals that spell the call record: ``id``/``type``/``function``
    with a nested ``name``/``arguments`` pair.

    The fingerprint is exact on purpose.  ``"type": "function"`` alone also
    names three other records that are *not* this fact: the Responses API
    tool definition (flat, with ``description``/``parameters``), the
    streaming accumulator slot (flat, four keys), and the tool spec
    (``function`` carrying ``description``/``parameters``).  A looser census
    would flag those as drift and the gate would be switched off.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            key.value for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        if keys != {"id", "type", "function"}:
            continue
        values = dict(zip(node.keys, node.values))
        type_value = values.get(
            next(key for key in node.keys
                 if isinstance(key, ast.Constant) and key.value == "type")
        )
        if not (isinstance(type_value, ast.Constant) and type_value.value == "function"):
            continue
        function = values.get(
            next(key for key in node.keys
                 if isinstance(key, ast.Constant) and key.value == "function")
        )
        if not isinstance(function, ast.Dict):
            continue
        function_keys = {
            key.value for key in function.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        if function_keys == {"name", "arguments"}:
            found.append(node)
    return found


def test_the_home_builds_the_record() -> None:
    """The constructor owns the three keys and the nested function dict."""
    from minicc.llm.base import tool_call

    assert tool_call("call-1", "tree", "{}") == {
        "id": "call-1",
        "type": "function",
        "function": {"name": "tree", "arguments": "{}"},
    }


def test_every_builder_asks_the_home() -> None:
    """All five emitting modules reference the constructor."""
    for name in BUILDERS:
        source = (PACKAGE / name.removeprefix("minicc/")).read_text(encoding="utf-8")
        assert "tool_call" in source, (
            f"{name} must ask the one home for the wire tool call shape"
        )


def test_the_record_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second wire shape.

    Eight copies existed: the agent loop's recovery call, the fake provider,
    the envelope action, and five parse paths across the two live providers.
    A copy that drops ``type`` or flattens ``name`` out of ``function`` is
    still a dict the readers accept - it just reads as a call with no name.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        for node in _wire_tool_call_literals(path):
            offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the wire tool call record is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
