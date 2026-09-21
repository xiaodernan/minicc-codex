"""Tool registry with a stable, versioned plugin contract (M8-T3).

Kept from the original: strict parameter validation (type / required /
bounds / max_len) with field-naming errors, risk levels that drive the
permission policy, stable [CODE] error prefixes, secret redaction and
head/tail truncation. Dropped: specproof's envelope versioning and budget
cost models (single-user CLI does not need them) — ``api_version`` below is a
*tool* contract, not a message envelope.

Added here: every ``ToolSpec`` carries an ``api_version`` and a
``capabilities`` declaration, ``register()`` validates the whole contract
before a tool becomes callable, and a name conflict never silently replaces
an existing (typically built-in) tool unless the caller says ``override=True``.
See ``docs/PLUGIN_API.md``.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .schemas import HEAD_CHARS, TAIL_CHARS, ToolCall, ToolResult

Handler = Callable[..., ToolResult]

CODE_UNKNOWN_TOOL = "UNKNOWN_TOOL"
CODE_INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
CODE_TOOL_ERROR = "TOOL_ERROR"
CODE_DENIED = "DENIED"

RISK_LEVELS = ("readonly", "write", "exec")

# Stable plugin contract. Bump TOOL_API_VERSION only when a field changes
# meaning; a spec may never assume a *newer* contract than the host runs.
TOOL_API_VERSION = 1
_MIN_TOOL_API_VERSION = 1

RISK_ORDER: dict[str, int] = {"readonly": 0, "write": 1, "exec": 2}

# What a tool declares it can touch. The declaration can only ever *tighten*
# the permission policy (see minicc.audit.authorize_tool); omitting it grants
# nothing extra. Each capability has a minimum risk level, so a tool that
# admits to writing files cannot hide behind risk="readonly".
CAPABILITY_MIN_RISK: dict[str, str] = {
    "fs_read": "readonly",
    "network": "readonly",
    "fs_write": "write",
    "shell": "exec",
}
CAPABILITIES = tuple(CAPABILITY_MIN_RISK)

PARAM_TYPES = ("str", "int", "bool", "list[str]")

# Registry-safe names: what the wire protocol and the MCP bridge
# (``mcp__server__tool``, truncated at 128, disambiguated with ``~hash``)
# actually produce.
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-~]{0,127}$")
_PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_REDACT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Do not match the ``sk-`` substring inside identifiers such as
    # ``task-...``; task ids must remain stable across durable reloads.
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}"), "[REDACTED:llm_api_key]"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "[REDACTED:github_token]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED:github_pat]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws_access_key]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=\-]{8,}"), "Bearer [REDACTED:bearer_token]"),
    (re.compile(r"(?:jdbc:[a-z]+|(?:redis|amqp))://[^\s]+@", re.IGNORECASE), "[REDACTED:url_credentials]"),
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "[REDACTED:jwt]",
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED PRIVATE KEY]",
    ),
)


def redact_text(text: str) -> tuple[str, bool]:
    """Redact suspected secrets (sk-* / Bearer / PEM private keys)."""
    changed = False
    for pattern, replacement in _REDACT_RULES:
        redacted, hits = pattern.subn(replacement, text)
        if hits:
            changed = True
            text = redacted
    return text, changed


def split_output(text: str) -> tuple[str, str, bool]:
    """Honest head/tail split: truncated=True whenever bytes are dropped."""
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        return text, "", False
    return text[:HEAD_CHARS], text[-TAIL_CHARS:], True


class ToolError(RuntimeError):
    """A tool failed; message becomes [TOOL_ERROR] … output (nothing written)."""


class ToolParamError(ToolError):
    """Parameter validation failed (INVALID_ARGUMENTS)."""


class ToolRegistrationError(ValueError):
    """A ToolSpec violated the plugin contract; the tool was not registered."""


def error_result(code: str, message: str) -> ToolResult:
    return ToolResult(
        status="error",
        summary=f"[{code}] {message}",
        security_tags=["untrusted"],
    )


def denied_result(message: str) -> ToolResult:
    return ToolResult(
        status="denied",
        summary=f"[{CODE_DENIED}] {message}",
        security_tags=["untrusted"],
    )


@dataclass(frozen=True)
class Param:
    name: str
    type: str = "str"  # str | int | bool | list[str]
    required: bool = False
    min_value: int | None = None
    max_value: int | None = None
    max_len: int | None = None
    description: str = ""

    def validate(self, value: Any) -> Any:
        if self.type == "str":
            if not isinstance(value, str):
                raise ToolParamError(f"参数 {self.name!r} 必须是字符串")
            if self.max_len is not None and len(value) > self.max_len:
                raise ToolParamError(
                    f"参数 {self.name!r} 超过最大长度 {self.max_len} (收到 {len(value)})"
                )
            return value
        if self.type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ToolParamError(f"参数 {self.name!r} 必须是整数")
            if self.min_value is not None and value < self.min_value:
                raise ToolParamError(f"参数 {self.name!r} 不能小于 {self.min_value}")
            if self.max_value is not None and value > self.max_value:
                raise ToolParamError(f"参数 {self.name!r} 不能大于 {self.max_value}")
            return value
        if self.type == "bool":
            if not isinstance(value, bool):
                raise ToolParamError(f"参数 {self.name!r} 必须是布尔值")
            return value
        if self.type == "list[str]":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ToolParamError(f"参数 {self.name!r} 必须是字符串数组")
            if self.max_len is not None and len(value) > self.max_len:
                raise ToolParamError(
                    f"参数 {self.name!r} 超过最大元素数 {self.max_len} (收到 {len(value)})"
                )
            return value
        raise ToolParamError(f"参数 {self.name!r} 类型未知: {self.type!r}")


@dataclass
class ToolSpec:
    name: str
    description: str
    risk: str  # readonly | write | exec
    params: tuple[Param, ...]
    handler: Handler = field(repr=False)
    visible: bool = True  # False → listed for the model but hidden from /tools detail
    input_schema: dict[str, Any] | None = None
    cancellable: bool = False
    api_version: int = TOOL_API_VERSION
    capabilities: tuple[str, ...] = ()

    def openai_schema(self) -> dict[str, Any]:
        if self.input_schema is not None:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.input_schema,
                },
            }
        properties: dict[str, Any] = {}
        required: list[str] = []
        type_map = {"str": "string", "int": "integer", "bool": "boolean", "list[str]": "array"}
        for param in self.params:
            schema: dict[str, Any] = {"type": type_map[param.type]}
            if param.description:
                schema["description"] = param.description
            if param.type == "list[str]":
                schema["items"] = {"type": "string"}
            properties[param.name] = schema
            if param.required:
                required.append(param.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


def validate_tool_spec(spec: ToolSpec) -> None:
    """Check the stable contract before a tool becomes callable.

    Every message names the offending field, so a plugin author can fix the
    spec without reading this module. Raises :class:`ToolRegistrationError`.
    """
    if not isinstance(spec.name, str) or not _TOOL_NAME_RE.match(spec.name):
        raise ToolRegistrationError(
            f"ToolSpec.name 非法: {spec.name!r}"
            "（需要 1-128 位，以字母或数字开头，只允许字母、数字、_ . - ~）"
        )
    if not isinstance(spec.description, str) or not spec.description.strip():
        raise ToolRegistrationError(f"工具 {spec.name!r} 的 description 必须是非空字符串")
    if spec.risk not in RISK_LEVELS:
        raise ToolRegistrationError(
            f"工具 {spec.name!r} 的 risk 非法: {spec.risk!r}（可选: {', '.join(RISK_LEVELS)}）"
        )
    if isinstance(spec.api_version, bool) or not isinstance(spec.api_version, int):
        raise ToolRegistrationError(
            f"工具 {spec.name!r} 的 api_version 必须是整数，收到 {spec.api_version!r}"
        )
    if spec.api_version > TOOL_API_VERSION:
        raise ToolRegistrationError(
            f"工具 {spec.name!r} 要求工具接口版本 {spec.api_version}，"
            f"当前 minicc 支持到 {TOOL_API_VERSION}；请升级 minicc 或降低 api_version"
        )
    if spec.api_version < _MIN_TOOL_API_VERSION:
        raise ToolRegistrationError(
            f"工具 {spec.name!r} 的工具接口版本 {spec.api_version} 已不再支持"
            f"（当前: {TOOL_API_VERSION}）"
        )
    if not callable(spec.handler):
        raise ToolRegistrationError(
            f"工具 {spec.name!r} 的 handler 必须可调用，收到 {type(spec.handler).__name__}"
        )
    _validate_params(spec)
    _validate_capabilities(spec)
    if spec.input_schema is not None:
        if spec.params:
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 同时声明了 params 与 input_schema，只能选一种"
                "（提供 input_schema 时 params 永远不会生效）"
            )
        _validate_input_schema(spec)


def _validate_params(spec: ToolSpec) -> None:
    params = spec.params
    if isinstance(params, (str, bytes)) or not isinstance(params, (tuple, list)):
        raise ToolRegistrationError(
            f"工具 {spec.name!r} 的 params 必须是 Param 元组，收到 {type(params).__name__}"
        )
    seen: set[str] = set()
    for param in params:
        if not isinstance(param, Param):
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 的 params 含非 Param 项: {param!r}"
            )
        if not _PARAM_NAME_RE.match(str(param.name)):
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 的参数名非法: {param.name!r}"
                "（需要字母或下划线开头，后接字母、数字、下划线）"
            )
        if param.name in seen:
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 的参数 {param.name!r} 重复声明"
            )
        seen.add(param.name)
        if param.type not in PARAM_TYPES:
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 的参数 {param.name!r} 类型非法: {param.type!r}"
                f"（可选: {', '.join(PARAM_TYPES)}）"
            )
        if param.min_value is not None and param.max_value is not None and param.min_value > param.max_value:
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 的参数 {param.name!r} 区间非法: "
                f"min_value={param.min_value} > max_value={param.max_value}"
            )
        if param.max_len is not None and param.max_len < 1:
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 的参数 {param.name!r} max_len 必须 ≥ 1，收到 {param.max_len}"
            )


def _validate_capabilities(spec: ToolSpec) -> None:
    capabilities = spec.capabilities
    if isinstance(capabilities, (str, bytes)) or not isinstance(capabilities, (tuple, list)):
        raise ToolRegistrationError(
            f"工具 {spec.name!r} 的 capabilities 必须是字符串元组，收到 {type(capabilities).__name__}"
        )
    for capability in capabilities:
        if not isinstance(capability, str):
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 的 capabilities 含非字符串项: {capability!r}"
            )
        minimum = CAPABILITY_MIN_RISK.get(capability)
        if minimum is None:
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 声明了未知能力 {capability!r}"
                f"（可选: {', '.join(CAPABILITIES)}）"
            )
        if RISK_ORDER[spec.risk] < RISK_ORDER[minimum]:
            raise ToolRegistrationError(
                f"工具 {spec.name!r} 声明能力 {capability!r} 却使用了 risk={spec.risk!r}"
                f"；该能力至少需要 risk={minimum!r}"
            )


def _validate_input_schema(spec: ToolSpec) -> None:
    schema = spec.input_schema
    name = spec.name
    if not isinstance(schema, dict):
        raise ToolRegistrationError(
            f"工具 {name!r} 的 input_schema 必须是对象，收到 {type(schema).__name__}"
        )
    declared_type = schema.get("type", "object")
    if declared_type != "object":
        raise ToolRegistrationError(
            f"工具 {name!r} 的 input_schema 顶层 type 必须是 \"object\"，收到 {declared_type!r}"
        )
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            raise ToolRegistrationError(
                f"工具 {name!r} 的 input_schema.properties 必须是对象"
            )
        for key, value in properties.items():
            if not isinstance(key, str) or not key:
                raise ToolRegistrationError(
                    f"工具 {name!r} 的 input_schema.properties 含非法属性名: {key!r}"
                )
            if not isinstance(value, dict):
                raise ToolRegistrationError(
                    f"工具 {name!r} 的 input_schema.properties[{key!r}] 必须是对象，"
                    f"收到 {type(value).__name__}"
                )
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise ToolRegistrationError(
            f"工具 {name!r} 的 input_schema.required 必须是字符串数组"
        )
    if isinstance(properties, dict):
        unknown = [item for item in required if item not in properties]
        if unknown:
            raise ToolRegistrationError(
                f"工具 {name!r} 的 input_schema.required 引用了未声明的属性: {unknown}"
            )


class ToolRegistry:
    """Name → ToolSpec with validation, redaction and truncation on execute."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._builtin_names: set[str] = set()
        self._overrides: dict[str, str] = {}

    def declare_builtin(self, names: Iterable[str] | None = None) -> None:
        """Mark *names* (default: everything registered so far) as built-in.

        ``build_registry`` calls this once, before the MCP bridge adds its own
        tools, so a later plugin can be told apart from the shipped toolset.
        """
        self._builtin_names.update(self._specs if names is None else [str(n) for n in names])

    def register(self, spec: ToolSpec, *, override: bool = False) -> None:
        """Validate and add *spec*; a name conflict needs an explicit override.

        Raises :class:`ToolRegistrationError` (a ``ValueError``) with a
        field-naming message when the spec violates the contract, or when it
        reuses a name that is already callable — a late registration must
        never silently shadow a built-in tool.
        """
        validate_tool_spec(spec)
        existing = self._specs.get(spec.name)
        if existing is not None:
            if not override:
                kind = "内置工具" if spec.name in self._builtin_names else "已注册工具"
                raise ToolRegistrationError(
                    f"工具 {spec.name!r} 与{kind}同名，后注册者不会静默替换它；"
                    f"确需替换请显式传入 override=True"
                )
            self._overrides[spec.name] = (
                "builtin" if spec.name in self._builtin_names else "plugin"
            )
        self._specs[spec.name] = spec

    def spec(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def risk_of(self, name: str) -> str | None:
        spec = self._specs.get(name)
        return spec.risk if spec else None

    def capabilities_of(self, name: str) -> tuple[str, ...]:
        spec = self._specs.get(name)
        return spec.capabilities if spec else ()

    def overrides(self) -> dict[str, str]:
        """Names replaced via ``override=True`` → the kind they replaced."""
        return dict(self._overrides)

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [spec.openai_schema() for spec in self._specs.values()]

    def restrict(self, names: Iterable[str]) -> "ToolRegistry":
        """Return a registry exposing only the named tools.

        The existing ``ToolSpec`` instances are reused, so validation,
        redaction, and handlers stay identical while a bounded sub-agent sees
        a smaller schema surface.
        """
        restricted = ToolRegistry()
        for name in names:
            spec = self._specs.get(str(name))
            if spec is not None:
                restricted.register(spec)
                if str(name) in self._builtin_names:
                    restricted.declare_builtin([str(name)])
        return restricted

    def _validate(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        spec = self._specs[name]
        if spec.input_schema is not None:
            return dict(arguments)
        known = {param.name for param in spec.params}
        for key in arguments:
            if key not in known:
                raise ToolParamError(f"工具 {name} 没有参数 {key!r} (可用: {sorted(known)})")
        checked: dict[str, Any] = {}
        for param in spec.params:
            if param.name not in arguments:
                if param.required:
                    raise ToolParamError(f"缺少必填参数 {param.name!r}")
                continue
            checked[param.name] = param.validate(arguments[param.name])
        return checked

    def execute(
        self,
        call: ToolCall,
        *,
        cancel_event: threading.Event | None = None,
    ) -> ToolResult:
        """Run one tool call; every failure becomes a structured ToolResult."""
        spec = self._specs.get(call.tool)
        if spec is None:
            return error_result(
                CODE_UNKNOWN_TOOL,
                f"未知工具 {call.tool!r} (已注册: {self.names()})",
            )
        if cancel_event is not None and cancel_event.is_set():
            return ToolResult(
                status="cancelled",
                summary=f"[CANCELLED] 任务已取消，未执行工具 {call.tool}",
                security_tags=["untrusted", "runtime_guard"],
            )
        started = time.monotonic()
        try:
            if call.parse_error:
                raise ToolParamError(f"[INVALID_TOOL_ARGUMENTS] {call.parse_error}")
            arguments = self._validate(call.tool, call.arguments)
            if spec.cancellable:
                result = spec.handler(arguments, cancel_event=cancel_event)
            else:
                result = spec.handler(arguments)
        except ToolParamError as exc:
            result = error_result(CODE_INVALID_ARGUMENTS, str(exc))
        except ToolError as exc:
            result = error_result(CODE_TOOL_ERROR, str(exc))
        except OSError as exc:
            result = error_result(CODE_TOOL_ERROR, f"系统 IO 错误: {exc}")
        except Exception as exc:  # noqa: BLE001 - a tool failure must not kill the loop
            result = error_result(
                CODE_TOOL_ERROR,
                f"工具 {call.tool!r} 未处理异常: {type(exc).__name__}: {exc}",
            )
        result.duration = time.monotonic() - started
        if not result.security_tags:
            result.security_tags = ["untrusted"]
        self._redact_result(result)
        return result

    @staticmethod
    def _redact_result(result: ToolResult) -> None:
        for attr in ("summary", "output", "head", "tail"):
            value = getattr(result, attr)
            if not value:
                continue
            redacted, changed = redact_text(value)
            if changed:
                setattr(result, attr, redacted)
                if "redacted" not in result.security_tags:
                    result.security_tags.append("redacted")
        result.data = _redact_value(result.data)


def _redact_value(value: Any) -> Any:
    """Apply credential redaction to structured tool metadata as well."""
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    return value


def truncate_to_result(text: str) -> tuple[str, str, bool]:
    return split_output(text)
