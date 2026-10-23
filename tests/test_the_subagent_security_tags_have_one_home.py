"""M8-T398 — 子代理结果的标签跟着安全标签的家走（T400 起家迁至 schemas.py）

T398 曾在 subagent.py 立 `SUBAGENT_SECURITY_TAGS`；T400 把「不可信基标签」
这一个事实收拢到 `minicc/tools/schemas.py` 的 `untrusted_tags` 之后，子代理
六条返回路径改问那个家。本门保留 T398 的行为断言：一次真实子代理跑通的
ok 路径，标签正是「不可信基 + subagent」，且往结果上追加标签不会污染家。
全包扫描与家的存在性由 tests/test_the_security_tags_have_one_home.py 负责。
"""

from __future__ import annotations

from pathlib import Path


def test_a_successful_subagent_result_still_carries_both_tags(tmp_path: Path) -> None:
    """The ok path builds its tags from the family home, both tags present."""
    from minicc.agent.subagent import build_task_tool_spec
    from minicc.llm.base import LLMResponse
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor
    from minicc.tools.schemas import untrusted_tags

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
    assert result.security_tags == untrusted_tags("subagent")
    # A fresh list every call: appending to the result must not touch the home.
    result.security_tags.append("redacted")
    assert untrusted_tags("subagent") == ["untrusted", "subagent"]
