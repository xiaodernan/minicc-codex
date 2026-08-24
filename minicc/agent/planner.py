"""Schema-constrained planning helpers for bounded agent workflows.

The model may propose a plan later, but the runtime remains authoritative:
invalid plans are rejected and replaced with a known fixed template.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .graph import DAGPlan, GraphValidationError, PlanTask, fixed_plan


DEFAULT_ALLOWED_TOOLS = frozenset({
    "read_file", "grep", "git_status", "git_diff", "write_file", "edit_file", "bash",
})
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")


@dataclass(frozen=True)
class PlannerPolicy:
    max_nodes: int = 16
    max_depth: int = 8
    max_concurrency: int = 4
    max_retries: int = 2
    allowed_tools: frozenset[str] = DEFAULT_ALLOWED_TOOLS


@dataclass(frozen=True)
class PlanBuildResult:
    plan: DAGPlan
    source: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "reason": self.reason, "plan": self.plan.to_dict()}


def _decode(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def validate_dynamic_plan(raw: object, *, policy: PlannerPolicy | None = None) -> DAGPlan:
    policy = policy or PlannerPolicy()
    document = _decode(raw)
    if not document or not isinstance(document.get("tasks"), list):
        raise GraphValidationError("动态计划必须是包含 tasks 数组的对象")
    if len(document["tasks"]) > policy.max_nodes:
        raise GraphValidationError(f"动态计划节点数超过上限 {policy.max_nodes}")
    tasks: list[PlanTask] = []
    for item in document["tasks"]:
        if not isinstance(item, dict):
            raise GraphValidationError("动态计划节点必须是对象")
        task_id = str(item.get("id") or "")
        kind = str(item.get("kind") or "readonly")
        if not _ID_RE.fullmatch(task_id):
            raise GraphValidationError(f"动态计划节点 id 非法: {task_id!r}")
        depends = item.get("depends_on") or []
        tools = item.get("allowed_tools") or []
        if not isinstance(depends, list) or not all(isinstance(value, str) for value in depends):
            raise GraphValidationError(f"节点 {task_id} 的 depends_on 非法")
        if not isinstance(tools, list) or not all(isinstance(value, str) for value in tools):
            raise GraphValidationError(f"节点 {task_id} 的 allowed_tools 非法")
        unknown = set(tools) - set(policy.allowed_tools)
        if unknown:
            raise GraphValidationError(f"节点 {task_id} 包含未授权工具: {sorted(unknown)}")
        retries = item.get("max_retries", 0)
        if not isinstance(retries, int) or retries < 0 or retries > policy.max_retries:
            raise GraphValidationError(f"节点 {task_id} 的 max_retries 超出范围")
        payload = item.get("payload") or {}
        if not isinstance(payload, dict) or len(json.dumps(payload, ensure_ascii=False)) > 4000:
            raise GraphValidationError(f"节点 {task_id} 的 payload 过大或非法")
        tasks.append(PlanTask(task_id, kind, tuple(depends), frozenset(tools), retries, dict(payload)))
    plan = DAGPlan(str(document.get("name") or "dynamic"), tuple(tasks))
    plan.validate(max_nodes=policy.max_nodes, max_depth=policy.max_depth)
    waves = _waves(plan)
    if max((len(wave) for wave in waves), default=0) > policy.max_concurrency:
        raise GraphValidationError(f"动态计划并发宽度超过上限 {policy.max_concurrency}")
    return plan


def _waves(plan: DAGPlan) -> list[list[str]]:
    remaining = {task.id: set(task.depends_on) for task in plan.tasks}
    waves: list[list[str]] = []
    while remaining:
        ready = sorted(item for item, deps in remaining.items() if not deps)
        if not ready:
            break
        waves.append(ready)
        for item in ready:
            remaining.pop(item)
        for deps in remaining.values():
            deps.difference_update(ready)
    return waves


def build_plan(raw: object, *, fallback_name: str = "inspect_implement_verify", policy: PlannerPolicy | None = None) -> PlanBuildResult:
    try:
        return PlanBuildResult(validate_dynamic_plan(raw, policy=policy), "dynamic")
    except (GraphValidationError, TypeError, ValueError) as exc:
        fallback = fixed_plan(fallback_name)
        fallback.validate(max_nodes=(policy or PlannerPolicy()).max_nodes)
        return PlanBuildResult(fallback, "fixed_fallback", str(exc))


__all__ = ["PlanBuildResult", "PlannerPolicy", "build_plan", "validate_dynamic_plan"]
