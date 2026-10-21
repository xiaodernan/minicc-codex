"""M8-T348 — 视觉上下文只有一个归一化，agent 与复核者看到的图片必须是同一批

`minicc/agent/loop.py` 与 `minicc/agent/completion.py` 各有一份
`_normalize_vision_context`（同名、同职责），而两份**不一样**：

* loop 的那份**查重**：同一张图在历史里只出现一次；
* completion 的那份**不查重**：同一张图在复核者的证据包里出现**两次**。

于是同一份视觉上下文，两个读者给出两种答案：agent 的历史里一张，复核者的
提示里两张——多出来的图既浪费 token，也让"复核者看到的证据"与"agent 看到的
证据"不是同一份。

本门钉住：两个读者问**同一个**函数（家放在 `minicc/agent/context.py`）；重复的
图在复核者的提示里也只出现一次；控制组——一张图照旧出现。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from minicc.agent import completion as completion_module
from minicc.agent import loop as loop_module
from minicc.agent.context import normalize_vision_context


def _part(url: str) -> dict[str, object]:
    return {"type": "image_url", "image_url": {"url": url}}


def _module_defines(module: object, name: str) -> bool:
    source = Path(str(inspect.getsourcefile(module))).read_text(encoding="utf-8")
    tree = ast.parse(source)
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


def test_both_readers_ask_the_same_function() -> None:
    """One home: the completion gate does not keep its own copy."""
    assert completion_module.normalize_vision_context is normalize_vision_context
    assert loop_module.normalize_vision_context is normalize_vision_context


def test_neither_module_defines_its_own_copy() -> None:
    """The identity check alone cannot see a second, unused copy."""
    assert not _module_defines(completion_module, "_normalize_vision_context"), (
        "the completion gate kept its own vision normalizer"
    )
    assert not _module_defines(loop_module, "_normalize_vision_context"), (
        "the agent loop kept its own vision normalizer"
    )


def test_a_repeated_image_reaches_the_reviewer_once() -> None:
    parts = [_part("data:image/png;base64,AAA"), _part("data:image/png;base64,AAA")]
    normalized = completion_module.normalize_vision_context(parts)
    urls = [
        str((item.get("image_url") or {}).get("url") or "")
        for item in normalized
        if isinstance(item.get("image_url"), dict)
    ]
    assert urls == ["data:image/png;base64,AAA"], urls


def test_one_image_still_reaches_the_reviewer() -> None:
    """The control: the ordinary case is untouched."""
    parts = [_part("data:image/png;base64,AAA")]
    normalized = completion_module.normalize_vision_context(parts)
    assert len(normalized) == 1, normalized
    assert normalized[0]["type"] == "image_url", normalized
