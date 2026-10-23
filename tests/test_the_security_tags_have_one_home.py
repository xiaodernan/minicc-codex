"""M8-T400 — 不可信基标签二十五个家：所有产线各写一份 ["untrusted", ...]"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/schemas.py"

PRODUCERS = (
    "minicc.agent.loop",
    "minicc.agent.subagent",
    "minicc.mcp",
    "minicc.tools",
    "minicc.tools.bash",
    "minicc.tools.git",
    "minicc.tools.memory",
    "minicc.tools.registry",
    "minicc.tools.todo",
    "minicc.tools.web",
    "minicc.tools.webfetch",
)


def test_the_home_exists_in_schemas() -> None:
    """schemas.py owns the untrusted base and the one constructor of tag lists."""
    from minicc.tools.schemas import UNTRUSTED_TAG, untrusted_tags

    assert UNTRUSTED_TAG == "untrusted"
    assert untrusted_tags() == ["untrusted"]
    assert untrusted_tags("subagent") == ["untrusted", "subagent"]
    assert untrusted_tags("runtime_guard", "background_shell") == [
        "untrusted", "runtime_guard", "background_shell",
    ]


def test_the_home_hands_out_a_fresh_list_every_call() -> None:
    """The registry appends "redacted" in place; that must never reach the home."""
    from minicc.tools.schemas import untrusted_tags

    first, second = untrusted_tags(), untrusted_tags()
    assert first == second and first is not second
    first.append("redacted")
    assert second == ["untrusted"]
    assert untrusted_tags() == ["untrusted"]


def test_every_producer_imports_the_same_home() -> None:
    """Every module that builds security_tags asks the one home."""
    import importlib

    from minicc.tools import schemas

    for module_name in PRODUCERS:
        module = importlib.import_module(module_name)
        assert getattr(module, "untrusted_tags", None) is schemas.untrusted_tags, (
            f"{module_name} does not import untrusted_tags from the home"
        )


def test_no_module_spells_the_untrusted_base_inline() -> None:
    """No collection literal outside schemas.py carries the untrusted base."""
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
            for element in node.elts:
                if (
                    isinstance(element, ast.Constant)
                    and element.value == "untrusted"
                    and relative != HOME
                ):
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the untrusted base is spelled inline outside its one home: "
        + ", ".join(offenders)
    )


def test_the_registry_still_defaults_and_redacts_without_polluting_the_home(
    tmp_path: Path,
) -> None:
    """End to end: an unmarked result gains the base; redaction appends beside it."""
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor
    from minicc.tools.schemas import ToolCall, untrusted_tags

    (tmp_path / "notes.txt").write_text("token sk-secretvalue123456\n", encoding="utf-8")
    registry = build_registry(Editor(tmp_path))
    result = registry.execute(ToolCall("read_file", {"path": "notes.txt"}))
    assert "untrusted" in result.security_tags
    assert "redacted" in result.security_tags
    assert "sk-secretvalue123456" not in result.output
    assert untrusted_tags() == ["untrusted"], "the home absorbed a result's tags"
