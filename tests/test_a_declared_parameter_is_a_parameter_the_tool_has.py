"""M8-T346 — 声明出来的参数必须是工具真有的参数

工具的 schema 是模型看得到的契约：模型看到 `glob` 有 `max_entries`，就以为
**调小它能少拿几条**。而 `minicc/tools/fs.py` 的 `glob` **从不读这个参数**——
它只用自己的常量 `MAX_GLOB_RESULTS`（200）：

* 模型要 5 条 → 工具回 200 条 → 模型的上下文被自己没要的东西塞满；
* 模型要 2000 条 → 工具回 200 条（上限是工具的，这条是对的）。

全仓普查（每个已注册工具的每个已声明参数，handler 是否真的读了它）只有**这一
处**不符：`glob.max_entries`。

本门钉住：

* **普查**：每个已声明的参数都被它的 handler 读到了（下一个"声明了却不用"的
  旋钮会在同一批里被抓住）；
* **行为**：`glob` 尊重模型调小的请求；
* **上限**：请求**超过**上限时按 `grep` 的既有约定被**拒**（不是静默截断）。
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Any

from minicc.tools import build_registry
from minicc.tools.fs import MAX_GLOB_RESULTS, Editor


def _registry(tmp_path: Path):
    return build_registry(Editor(tmp_path))


def _handler_reads(handler: Any, key: str) -> bool:
    """Whether the handler reads ``key`` out of its arguments."""
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):  # pragma: no cover - a C-level handler
        return True
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "pop"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == key
        ):
            return True
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            base = node.value
            if (
                isinstance(base, ast.Name)
                and "arg" in base.id
                and node.slice.value == key
            ):
                return True
    return False


def test_every_declared_parameter_is_read_by_its_handler(tmp_path: Path) -> None:
    """The census: a declared knob that nobody reads is a promise nobody keeps."""
    registry = _registry(tmp_path)
    unread: list[str] = []
    for name in sorted(registry.names()):
        spec = registry.spec(name)
        for param in spec.params:
            if not _handler_reads(spec.handler, param.name):
                unread.append(f"{name}.{param.name}")
    assert not unread, f"these declared parameters are never read: {unread}"


def test_glob_honours_a_smaller_request(tmp_path: Path) -> None:
    """The model asked for fewer results; it gets fewer results."""
    for index in range(12):
        (tmp_path / f"f{index:02d}.txt").write_text("x\n", encoding="utf-8")
    registry = _registry(tmp_path)
    from minicc.tools.schemas import ToolCall

    result = registry.execute(ToolCall("glob", {"pattern": "*.txt", "max_entries": 5}))
    assert result.status == "ok", result.summary
    # M8-T346: the file tools put their text in head/tail and leave
    # ``output`` empty - a gate that only read ``output`` would pass on an
    # empty string (the same blind spot the M8-T290 gate had).
    body = (result.head or "") + (result.tail or "") + (result.output or "")
    listed = [line for line in body.splitlines() if line.strip()]
    assert listed, "the glob returned nothing to count"
    assert len(listed) <= 5, listed


def test_a_request_above_the_ceiling_is_refused(tmp_path: Path) -> None:
    """The ceiling belongs to the tool: a bigger request is refused, not capped.

    This is the contract ``grep`` already has (its ``max_matches`` above the
    schema's ceiling is an ``INVALID_ARGUMENTS`` error, not a silent cap).
    """
    registry = _registry(tmp_path)
    from minicc.tools.schemas import ToolCall

    result = registry.execute(ToolCall("glob", {"pattern": "*.txt", "max_entries": 5000}))
    assert result.status == "error", result.summary
    assert "max_entries" in result.summary or "不能超过" in result.summary, result.summary
