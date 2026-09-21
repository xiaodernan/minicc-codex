"""Versioned execution request shared by thread and detached workers.

Transport adapters may add identifiers, but they must not independently decide
permissions or drop inputs when moving a task between executors.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .audit import normalize_permission_mode

TASK_SCHEMA_VERSION = 2


def resolve_task_permissions(payload: Mapping[str, Any], *, yolo: bool = False) -> tuple[bool, bool, str]:
    mode = normalize_permission_mode(payload.get("permission_mode"))
    changes = bool(payload.get("allow_changes")) or yolo
    network = bool(payload.get("allow_network"))
    if mode == "yolo":
        changes = network = True
    elif mode == "plan":
        changes = False
    return changes, network, mode


@dataclass(frozen=True)
class TaskRequest:
    message: str
    task_id: str = ""
    session_id: str = "web-latest"
    workspace_path: str = ""
    allow_changes: bool = False
    allow_network: bool = False
    permission_mode: str = "default"
    reasoning_effort: str = "high"
    task_kind: str = "task"
    resume_from_checkpoint: bool = False
    attachments: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    schema_version: int = TASK_SCHEMA_VERSION

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "TaskRequest":
        version = int(payload.get("schema_version") or TASK_SCHEMA_VERSION)
        if version not in {1, TASK_SCHEMA_VERSION}:
            raise ValueError(f"Unsupported task request schema: {version}")
        changes, network, mode = resolve_task_permissions(payload)
        message = str(payload.get("message") or "")
        if not message.strip():
            raise ValueError("message cannot be empty")
        return cls(
            message=message,
            task_id=str(payload.get("task_id") or ""),
            session_id=str(payload.get("session_id") or "web-latest"),
            workspace_path=str(payload.get("workspace_path") or ""),
            allow_changes=changes,
            allow_network=network,
            permission_mode=mode,
            reasoning_effort=str(payload.get("reasoning_effort") or "high"),
            model=str(payload.get("model") or ""),
            task_kind=str(payload.get("task_kind") or "task"),
            resume_from_checkpoint=bool(payload.get("resume_from_checkpoint")),
            attachments=[dict(item) for item in payload.get("attachments") or [] if isinstance(item, dict)],
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskResult:
    """Stable result fields; provider-specific diagnostics remain additive."""

    answer: str = ""
    error: str = ""
    cancelled: bool = False
    tokens_used: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "TaskResult":
        usage = payload.get("tokens_used")
        return cls(
            answer=str(payload.get("answer") or ""),
            error=str(payload.get("error") or ""),
            cancelled=bool(payload.get("cancelled")),
            tokens_used=dict(usage) if isinstance(usage, dict) else {},
            metadata={key: value for key, value in payload.items() if key not in {"answer", "error", "cancelled", "tokens_used"}},
        )

    def to_payload(self) -> dict[str, Any]:
        return {**self.metadata, "answer": self.answer, "error": self.error, "cancelled": self.cancelled, "tokens_used": dict(self.tokens_used)}
