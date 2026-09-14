"""TodoWrite-equivalent tool tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.tools.registry import ToolRegistry, ToolSpec
from minicc.tools.todo import TodoTools, normalize_todos
from minicc.tools.editor import Editor


@pytest.fixture()
def todos(tmp_path: Path) -> TodoTools:
    return TodoTools(tmp_path)


def test_write_persists_and_returns_todos(todos: TodoTools, tmp_path: Path) -> None:
    result = todos.write({
        "todos": [
            {"content": "阅读项目结构", "status": "completed"},
            {"content": "实现功能", "status": "in_progress", "priority": "high"},
            {"content": "补测试"},
        ]
    })
    assert result.status == "ok"
    assert len(result.data["todos"]) == 3
    assert result.data["todos"][0]["status"] == "completed"
    assert result.data["todos"][2]["priority"] == "medium"
    assert result.data["todos"][1]["status"] == "in_progress"
    stored = json.loads((tmp_path / ".minicc" / "todos.json").read_text(encoding="utf-8"))
    assert stored["updated_at"].endswith("Z")
    assert len(stored["todos"]) == 3


def test_write_is_full_replacement(todos: TodoTools) -> None:
    todos.write({"todos": [{"content": "a"}, {"content": "b"}]})
    result = todos.write({"todos": [{"content": "c", "status": "in_progress"}]})
    assert [todo["content"] for todo in result.data["todos"]] == ["c"]


def test_read_empty_returns_clean_state(todos: TodoTools) -> None:
    result = todos.read({})
    assert result.status == "ok"
    assert result.data["todos"] == []
    assert "尚无清单" in result.summary


def test_read_survives_corrupted_file(todos: TodoTools) -> None:
    todos.path.parent.mkdir(parents=True, exist_ok=True)
    todos.path.write_text("{not json", encoding="utf-8")
    result = todos.read({})
    assert result.status == "ok"
    assert result.data["todos"] == []


def test_validation_rejects_bad_payloads(todos: TodoTools) -> None:
    with pytest.raises(Exception, match="数组"):
        normalize_todos("nope")
    with pytest.raises(Exception, match="content 不能为空"):
        normalize_todos([{"content": " "}])
    with pytest.raises(Exception, match="status 非法"):
        normalize_todos([{"content": "a", "status": "done"}])
    with pytest.raises(Exception, match="priority 非法"):
        normalize_todos([{"content": "a", "priority": "urgent"}])
    with pytest.raises(Exception, match="in_progress"):
        normalize_todos([
            {"content": "a", "status": "in_progress"},
            {"content": "b", "status": "in_progress"},
        ])
    with pytest.raises(Exception, match="最多 50"):
        normalize_todos([{"content": f"t{i}"} for i in range(51)])
    with pytest.raises(Exception, match="超过 500"):
        normalize_todos([{"content": "x" * 501}])


def test_atomic_write_leaves_no_temp_files(todos: TodoTools) -> None:
    for round_no in range(3):
        todos.write({"todos": [{"content": f"task-{round_no}"}]})
    siblings = [p.name for p in todos.path.parent.iterdir() if p.name != "todos.json"]
    assert siblings == []


def test_registered_with_readonly_risk(tmp_path: Path) -> None:
    editor = Editor(tmp_path)
    from minicc.tools import build_registry

    registry = build_registry(editor)
    assert registry.risk_of("todo_write") == "readonly"
    assert registry.risk_of("todo_read") == "readonly"
    spec = registry.spec("todo_write")
    assert spec is not None
    # Structured schema must accept the documented payload shape.
    schema = spec.openai_schema()["function"]["parameters"]
    assert schema["properties"]["todos"]["type"] == "array"


def test_registered_handler_end_to_end(tmp_path: Path) -> None:
    from minicc.tools import build_registry
    from minicc.tools.registry import ToolCall

    editor = Editor(tmp_path)
    registry = build_registry(editor)
    call = ToolCall(tool="todo_write", arguments={"todos": [{"content": "端到端", "status": "in_progress"}]})
    result = registry.execute(call)
    assert result.status == "ok"
    assert result.data["todos"][0]["content"] == "端到端"
    stored = json.loads((tmp_path / ".minicc" / "todos.json").read_text(encoding="utf-8"))
    assert stored["todos"][0]["status"] == "in_progress"
