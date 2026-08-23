"""Versionless tool registry — adapted from specproof craft/tools.py.

Kept from the original: strict parameter validation (type / required /
bounds / max_len) with field-naming errors, risk levels that drive the
permission policy, stable [CODE] error prefixes, secret redaction and
head/tail truncation. Dropped: envelope versioning and budget cost models
(single-user CLI does not need them).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .schemas import HEAD_CHARS, TAIL_CHARS, ToolCall, ToolResult

Handler = Callable[[dict[str, Any]], ToolResult]

CODE_UNKNOWN_TOOL = "UNKNOWN_TOOL"
CODE_INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
CODE_TOOL_ERROR = "TOOL_ERROR"
CODE_DENIED = "DENIED"

RISK_LEVELS = ("readonly", "write", "exec")

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


class ToolRegistry:
    """Name → ToolSpec with validation, redaction and truncation on execute."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.risk not in RISK_LEVELS:
            raise ValueError(f"tool {spec.name!r} risk 非法: {spec.risk!r}")
        if spec.name in self._specs:
            raise ValueError(f"工具重复注册: {spec.name}")
        self._specs[spec.name] = spec

    def spec(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def risk_of(self, name: str) -> str | None:
        spec = self._specs.get(name)
        return spec.risk if spec else None

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [spec.openai_schema() for spec in self._specs.values()]

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

    def execute(self, call: ToolCall) -> ToolResult:
        """Run one tool call; every failure becomes a structured ToolResult."""
        spec = self._specs.get(call.tool)
        if spec is None:
            return error_result(
                CODE_UNKNOWN_TOOL,
                f"未知工具 {call.tool!r} (已注册: {self.names()})",
            )
        started = time.monotonic()
        try:
            arguments = self._validate(call.tool, call.arguments)
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
