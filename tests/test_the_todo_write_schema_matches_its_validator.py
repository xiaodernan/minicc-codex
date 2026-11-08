"""M8-T593 — the todo_write tool's declared schema matches its validator.

``minicc/tools/__init__.py`` declares ``todo_write``'s input schema inline
(maxItems 50, content maxLength 500, enums, required fields). The validator
behind it — ``minicc/tools/todo.py`` — enforces the same limits from its own
constants (``MAX_TODOS``, ``MAX_CONTENT_CHARS``) and its own enum tuples. Two
declarations of one contract, kept in step by hand; a bump to either without
the other is a silent lie in the tool's advertisement to the model.

This gate pins, by parsing the schema's AST literal:

* ``maxItems == MAX_TODOS`` (and both equal 50);
* ``content``'s ``minLength == 1`` (validator: non-empty after strip) and
  ``maxLength == MAX_CONTENT_CHARS`` (and both equal 500);
* ``status``'s enum is spelled ``list(TODO_STATUSES)`` and its members are
  exactly the tuple the normalizer validates against;
* ``priority``'s enum likewise with ``TODO_PRIORITIES``;
* ``items.required == ["content"]`` and ``schema.required == ["todos"]``;
* ``items.properties``' keys are exactly the normalizer's return shape
  (``content``, ``status``, ``priority``).

Scope: todo_write only. Other ToolSpecs carry inline schemas too and are a
separate audit (see the ledger).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS_INIT = REPO / "minicc" / "tools" / "__init__.py"
TODO = REPO / "minicc" / "tools" / "todo.py"


def _dict_get(node: ast.Dict, key: str):
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    return None


def _constant(node) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _list_of_names(node) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    return [elt.id for elt in node.elts if isinstance(elt, ast.Name)]


def _todo_write_schema(tree: ast.Module):
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ToolSpec"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "todo_write"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "input_schema" and isinstance(keyword.value, ast.Dict):
                return keyword.value
        return None
    return None


def test_the_todo_write_schema_matches_its_validator() -> None:
    from minicc.tools import todo as todo_mod

    assert todo_mod.MAX_TODOS == 50
    assert todo_mod.MAX_CONTENT_CHARS == 500
    assert todo_mod.TODO_STATUSES == ("pending", "in_progress", "completed")
    assert todo_mod.TODO_PRIORITIES == ("high", "medium", "low")

    tree = ast.parse(TOOLS_INIT.read_text(encoding="utf-8"), filename=str(TOOLS_INIT))
    schema = _todo_write_schema(tree)
    assert schema is not None, "todo_write's ToolSpec with an input_schema dict was not found"

    properties = _dict_get(schema, "properties")
    assert properties is not None, "the schema declares no properties"
    todos = _dict_get(properties, "todos")
    assert isinstance(todos, ast.Dict), "properties.todos must be an object"
    max_items = _constant(_dict_get(todos, "maxItems"))
    assert max_items == todo_mod.MAX_TODOS, (
        f"schema maxItems ({max_items}) drifted from todo.MAX_TODOS ({todo_mod.MAX_TODOS})"
    )

    items = _dict_get(todos, "items")
    assert isinstance(items, ast.Dict), "todos.items must be an object"
    item_props = _dict_get(items, "properties")
    assert isinstance(item_props, ast.Dict), "todos.items.properties must be an object"
    prop_keys = [k.value for k in item_props.keys if isinstance(k, ast.Constant)]
    assert set(prop_keys) == {"content", "status", "priority"}, (
        f"the schema's entry shape {prop_keys} drifted from the validator's return shape"
    )

    content = _dict_get(item_props, "content")
    assert isinstance(content, ast.Dict)
    assert _constant(_dict_get(content, "minLength")) == 1
    assert _constant(_dict_get(content, "maxLength")) == todo_mod.MAX_CONTENT_CHARS, (
        f"schema content.maxLength drifted from todo.MAX_CONTENT_CHARS ({todo_mod.MAX_CONTENT_CHARS})"
    )

    def enum_members(prop):
        enum_call = _dict_get(prop, "enum")
        assert isinstance(enum_call, ast.Call), "the enum must be spelled list(...)"
        (inner,) = enum_call.args
        return inner.id if isinstance(inner, ast.Name) else None

    status = _dict_get(item_props, "status")
    priority = _dict_get(item_props, "priority")
    assert enum_members(status) == "TODO_STATUSES"
    assert enum_members(priority) == "TODO_PRIORITIES"

    items_required = _dict_get(items, "required")
    assert _constant(items_required) is None  # a list, not a scalar
    assert [elt.value for elt in items_required.elts] == ["content"], (
        "items.required must demand exactly content (the validator's required key)"
    )
    schema_required = _dict_get(schema, "required")
    assert [elt.value for elt in schema_required.elts] == ["todos"], (
        "schema.required must demand exactly todos"
    )
