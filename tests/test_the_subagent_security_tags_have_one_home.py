"""M8-T398 — 子代理结果的安全标签六个家：六条返回路径各写一份 ["untrusted", "subagent"]"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/subagent.py"

TAGS = frozenset({"untrusted", "subagent"})


def test_the_home_exists_in_subagent() -> None:
    """subagent.py owns the two tags every subagent result carries."""
    from minicc.agent.subagent import SUBAGENT_SECURITY_TAGS

    assert set(SUBAGENT_SECURITY_TAGS) == TAGS
    assert isinstance(SUBAGENT_SECURITY_TAGS, tuple), (
        "the home must be immutable: the registry appends to a result's tags"
    )


def test_no_module_inlines_the_tags() -> None:
    """No module spells the two tags as a literal outside the one declaration."""
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
            if len(node.elts) >= 2 and elements == TAGS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the subagent security tags are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_a_successful_subagent_result_still_carries_both_tags(tmp_path: Path) -> None:
    """The ok path spreads the home into a fresh list, both tags present."""
    from minicc.agent.subagent import SUBAGENT_SECURITY_TAGS, build_task_tool_spec
    from minicc.llm.base import LLMResponse
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor

    class _Provider:
        def __init__(self, *args, **kwargs) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
                }])
            return LLMResponse(content="子代理结论：项目是一个本地 coding agent。")

        async def close(self):
            pass

    (tmp_path / "README.md").write_text("# demo project\n", encoding="utf-8")
    spec = build_task_tool_spec(
        provider_factory=_Provider,
        workspace=tmp_path,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=build_registry(Editor(tmp_path)),
    )
    result = spec.handler({"description": "调研项目结构", "prompt": "读取 README.md 并总结项目用途。"})
    assert result.status == "ok"
    assert result.security_tags == list(SUBAGENT_SECURITY_TAGS)
    # A spread copy: appending to the result must not touch the home.
    result.security_tags.append("redacted")
    assert SUBAGENT_SECURITY_TAGS == ("untrusted", "subagent")
