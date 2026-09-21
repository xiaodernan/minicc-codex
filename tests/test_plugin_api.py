"""M8-T3: the plugin contract is only real if the docs run and the gate bites.

Two halves:

1. ``docs/PLUGIN_API.md`` is executable — every ```python block is exec'd
   verbatim, so a stale example fails CI instead of misleading a reader.
2. Registration-time validation, conflict/override semantics and the
   ``network`` capability's route into the permission policy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from minicc.audit import authorize_tool, tool_requires_authorization
from minicc.tools import (
    CAPABILITIES,
    TOOL_API_VERSION,
    Editor,
    Param,
    ToolCall,
    ToolRegistrationError,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    build_registry,
    validate_tool_spec,
)

DOC = Path(__file__).resolve().parents[1] / "docs" / "PLUGIN_API.md"
_BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)
_SKIP = "# doc-test: skip"


def _blocks() -> list[str]:
    text = DOC.read_text(encoding="utf-8")
    return [block for block in _BLOCK_RE.findall(text) if _SKIP not in block]


def _good(**overrides: object) -> ToolSpec:
    fields: dict[str, object] = {
        "name": "my_tool",
        "description": "一个合法插件。",
        "risk": "readonly",
        "params": (Param("path", "str", required=True, max_len=64),),
        "handler": lambda args: ToolResult(status="ok", summary="ok"),
    }
    fields.update(overrides)
    return ToolSpec(**fields)  # type: ignore[arg-type]


# --- 1. the documentation is executable -------------------------------------

def test_plugin_api_doc_exists_with_runnable_examples() -> None:
    assert DOC.is_file()
    blocks = _blocks()
    assert len(blocks) >= 3, "文档示例太少，起不到契约作用"
    assert any("registry.register" in block for block in blocks)


@pytest.mark.parametrize("block", _blocks(), ids=lambda block: block.splitlines()[0][:48])
def test_every_doc_example_runs_verbatim(block: str) -> None:
    exec(compile(block, str(DOC), "exec"), {"__name__": "doc_example"})  # noqa: S102


# --- 2. registration-time validation ---------------------------------------

def test_a_valid_spec_registers_and_is_callable() -> None:
    registry = ToolRegistry()
    registry.register(_good())
    assert registry.names() == ["my_tool"]
    result = registry.execute(ToolCall("my_tool", {"path": "a.txt"}))
    assert result.status == "ok"
    assert result.security_tags == ["untrusted"]


def test_illegal_schema_is_rejected_with_a_field_naming_error() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolRegistrationError) as excinfo:
        registry.register(_good(input_schema={"type": "object", "properties": {}}))
    # params + input_schema 同时声明 = params 永远不会生效，属于契约错误
    assert "params" in str(excinfo.value)


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"name": "Bad Name"}, "name"),
        ({"name": ""}, "name"),
        ({"name": "x" * 129}, "name"),
        ({"description": "   "}, "description"),
        ({"risk": "dangerous"}, "risk"),
        ({"risk": ""}, "risk"),
        ({"api_version": TOOL_API_VERSION + 1}, "api_version"),
        ({"api_version": "1"}, "api_version"),
        ({"handler": None}, "handler"),
        ({"params": (Param("a", "str"), Param("a", "int"))}, "重复"),
        ({"params": (Param("a", "float"),)}, "类型非法"),
        ({"params": (Param("9bad", "str"),)}, "参数名非法"),
        ({"params": ("not-a-param",)}, "Param"),
        ({"params": (Param("a", "int", min_value=9, max_value=1),)}, "区间非法"),
        ({"params": (Param("a", "str", max_len=0),)}, "max_len"),
        ({"capabilities": ("telepathy",)}, "未知能力"),
        ({"capabilities": "network"}, "capabilities"),
        ({"capabilities": ("fs_write",)}, "fs_write"),
        ({"capabilities": ("shell",)}, "shell"),
    ],
)
def test_invalid_specs_are_rejected(kwargs: dict, needle: str) -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolRegistrationError) as excinfo:
        registry.register(_good(**kwargs))
    message = str(excinfo.value)
    assert needle in message, message
    # 可读性：必须点名是哪个工具
    assert "my_tool" in message or "ToolSpec.name" in message
    assert registry.names() == [], "被拒的插件不能留下半成品注册项"


@pytest.mark.parametrize("schema", [
    {"type": "string"},
    {"type": "object", "properties": ["a"]},
    {"type": "object", "properties": {"a": "string"}},
    {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["b"]},
    {"type": "object", "properties": {"a": {"type": "string"}}, "required": "a"},
])
def test_broken_input_schemas_never_reach_the_provider(schema: dict) -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolRegistrationError):
        registry.register(_good(params=(), input_schema=schema))


def test_input_schema_without_params_is_accepted_and_passed_through() -> None:
    registry = ToolRegistry()
    registry.register(_good(
        params=(),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ))
    assert registry.execute(ToolCall("my_tool", {"anything": 1})).status == "ok"


def test_validate_tool_spec_checks_without_registering() -> None:
    spec = _good(risk="nonsense")
    with pytest.raises(ToolRegistrationError):
        validate_tool_spec(spec)
    assert ToolRegistry().names() == []


def test_api_version_below_supported_floor_is_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="不再支持"):
        ToolRegistry().register(_good(api_version=0))


# --- 3. conflict and override semantics ------------------------------------

def test_late_registration_never_silently_replaces_a_builtin(tmp_path) -> None:
    registry = build_registry(Editor(tmp_path))
    before = registry.spec("read_file")
    assert before is not None
    with pytest.raises(ToolRegistrationError) as excinfo:
        registry.register(_good(name="read_file"))
    message = str(excinfo.value)
    assert "内置工具" in message and "override=True" in message
    assert registry.spec("read_file") is before, "被拒的注册不能改动原工具"
    assert registry.overrides() == {}


def test_override_is_explicit_and_leaves_an_audit_trail(tmp_path) -> None:
    registry = build_registry(Editor(tmp_path))
    replacement = _good(
        name="read_file", params=(),
        handler=lambda args: ToolResult(status="ok", summary="插件版"),
    )
    registry.register(replacement, override=True)
    assert registry.spec("read_file") is replacement
    assert registry.overrides() == {"read_file": "builtin"}
    assert registry.execute(ToolCall("read_file", {})).summary == "插件版"


def test_plugin_versus_plugin_conflict_says_registered_not_builtin() -> None:
    registry = ToolRegistry()
    registry.register(_good())
    with pytest.raises(ToolRegistrationError) as excinfo:
        registry.register(_good())
    assert "已注册工具" in str(excinfo.value)
    registry.register(_good(), override=True)
    assert registry.overrides() == {"my_tool": "plugin"}


def test_builtins_registered_before_the_mcp_bridge_are_the_builtin_set(tmp_path) -> None:
    registry = build_registry(Editor(tmp_path))
    for name in registry.names():
        assert registry.spec(name) is not None
    # 内置集合可被 restrict 传递，子代理看到的边界不因此改变
    restricted = registry.restrict(["read_file", "my_tool"])
    assert restricted.names() == ["read_file"]
    assert restricted.execute(ToolCall("read_file", {"path": "nope.txt"})).status == "error"


# --- 4. capabilities tighten the permission policy --------------------------

def test_declared_network_capability_requires_the_network_grant() -> None:
    registry = ToolRegistry()
    registry.register(_good(
        capabilities=("network",),
        handler=lambda args: ToolResult(status="error", summary="不该被调用"),
    ))
    name, risk = "my_tool", registry.risk_of("my_tool")
    caps = registry.capabilities_of(name)
    assert caps == ("network",)
    assert tool_requires_authorization(name, risk, caps) is True
    assert tool_requires_authorization(name, risk) is False, "不声明能力的旧行为不变"
    denied = authorize_tool(name, risk, {}, allow_changes=True, allow_network=False, capabilities=caps)
    assert denied.allowed is False
    assert denied.authorization == "missing_task_network"
    granted = authorize_tool(name, risk, {}, allow_changes=True, allow_network=True, capabilities=caps)
    assert granted.allowed is True


def test_network_capability_cannot_bypass_write_or_plan_authorization() -> None:
    caps = ("network", "fs_write")
    plan = authorize_tool(
        "my_tool", "write", {}, allow_changes=True, allow_network=True,
        permission_mode="plan", capabilities=caps,
    )
    assert plan.allowed is False and plan.authorization == "plan_mode_write"
    no_network = authorize_tool(
        "my_tool", "write", {}, allow_changes=True, allow_network=False, capabilities=caps,
    )
    assert no_network.allowed is False
    assert no_network.authorization == "missing_task_network"
    both = authorize_tool(
        "my_tool", "write", {}, allow_changes=True, allow_network=True, capabilities=caps,
    )
    assert both.allowed is True


def test_unknown_risk_is_still_denied_even_with_capabilities() -> None:
    decision = authorize_tool(
        "my_tool", None, {}, allow_changes=True, allow_network=True,
        capabilities=("network",),
    )
    assert decision.allowed is False
    assert decision.authorization == "unknown_risk"


def test_yolo_mode_still_short_circuits() -> None:
    decision = authorize_tool(
        "my_tool", "readonly", {}, allow_changes=True, allow_network=False,
        permission_mode="yolo", capabilities=("network",),
    )
    assert decision.allowed is True


def test_capabilities_are_declared_values_only() -> None:
    assert set(CAPABILITIES) == {"fs_read", "network", "fs_write", "shell"}
    registry = ToolRegistry()
    assert registry.capabilities_of("absent") == ()


# --- 5. the shipped toolset satisfies its own contract ---------------------

def test_every_builtin_tool_passes_the_public_validator(tmp_path) -> None:
    registry = build_registry(Editor(tmp_path))
    assert len(registry.names()) >= 20
    for name in registry.names():
        spec = registry.spec(name)
        assert spec is not None
        validate_tool_spec(spec)
        assert spec.api_version == TOOL_API_VERSION
        # 内置联网工具仍由名字白名单把关，未声明能力时行为不变
        assert set(spec.capabilities) <= set(CAPABILITIES)


def test_tool_listing_shows_risk_and_capabilities() -> None:
    from minicc.main import _describe_tool

    registry = ToolRegistry()
    registry.register(_good(capabilities=("network", "fs_read")))
    line = _describe_tool(registry, "my_tool")
    assert line.startswith("my_tool [readonly")
    assert "network" in line and "fs_read" in line
    assert _describe_tool(registry, "absent") == "absent"
