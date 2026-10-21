"""M8-T352 — 恢复闸门也要挡住「用 bash 做的写」

停滞恢复之后，执行器会挂起一个临时闸门：**在模型重新看过工作区之前，不许再
做投机性的写**。而闸门判的是**声明的风险**：

```python
if recovery_inspection_required and risk == "write":
```

`bash` 声明的是 `exec`——所以 `sed -i 's/a/b/' file.py`、`python -c "open(f,
'w').write(...)"` 这类**确实会改工作区**的命令，声明的风险是 `exec`，闸门**让
它们过去了**。

实测（本门就是这次实测）：三次重复读触发停滞与恢复探针之后，紧接的一轮
`bash("sed -i …")` **没有被拦**，文件被改了——闸门的承诺有一个洞。

仓库其实**早就有**这条规则：`command_may_modify_workspace`（M8-T322 起）知道
`bash` 什么时候会写工作区；只是闸门问的是**风险**，不是这条规则。

本门钉住：恢复闸门挡住用 bash 做的写；控制组——恢复后的**读**照旧（闸门只管
写），bash 的**读命令**照旧；看过新证据之后闸门解除，写照旧放行。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _RepeatsThenBash:
    """Three identical reads (stagnation) and then one bash write."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        if self.calls <= 3:
            return LLMResponse(
                tool_calls=[{
                    "id": f"read-{self.calls}",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": json.dumps({"path": "note.txt"})},
                }],
                finish_reason="tool_calls",
            )
        if self.calls == 4:
            return LLMResponse(
                tool_calls=[{
                    "id": "bash-1",
                    "type": "function",
                    "function": {"name": "bash", "arguments": json.dumps({"command": self.command})},
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True)
    (workspace / "note.txt").write_text("aaa\n", encoding="utf-8")
    return workspace


def _run(tmp_path: Path, command: str) -> list[tuple[str, str, str]]:
    workspace = _workspace(tmp_path)
    seen: list[tuple[str, str, str]] = []

    def on_tool(call: Any, result: Any) -> None:
        seen.append((call.tool, result.status, result.summary or ""))

    asyncio.run(run_agent(
        _RepeatsThenBash(command),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "改一下"}],
        max_turns=8,
        on_tool=on_tool,
        should_allow=lambda _name, _call: True,
        workspace=workspace,
    ))
    return seen


def test_a_write_done_through_bash_is_refused_after_a_recovery(tmp_path: Path) -> None:
    """The guard's promise: no speculative write until the model looks again."""
    seen = _run(tmp_path, "sed -i 's/aaa/bbb/' note.txt")
    bash_calls = [item for item in seen if item[0] == "bash"]
    assert bash_calls, seen
    _tool, status, summary = bash_calls[0]
    assert status == "error", (status, summary)
    assert "RECOVERY_GUARD" in summary, summary


def test_a_read_through_bash_is_still_allowed(tmp_path: Path) -> None:
    """The control: the guard is about writes, not about commands."""
    seen = _run(tmp_path, "cat note.txt")
    bash_calls = [item for item in seen if item[0] == "bash"]
    assert bash_calls, seen
    _tool, status, summary = bash_calls[0]
    assert "RECOVERY_GUARD" not in summary, (status, summary)


def test_the_predictive_predicate_answers_for_bash() -> None:
    """The rule itself, asked one step earlier."""
    from minicc.agent.tool_policy import predicts_workspace_write

    assert predicts_workspace_write("bash", {"command": "sed -i 's/a/b/' f.py"}) is True
    assert predicts_workspace_write("bash", {"command": "cat f.py"}) is False
    assert predicts_workspace_write("write_file", {"path": "a.py"}) is True
    assert predicts_workspace_write("read_file", {"path": "a.py"}) is False
