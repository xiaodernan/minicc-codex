"""Deterministic complexity routing for bounded automatic subagents.

The model remains responsible for the actual coding decisions. This module
only decides when a task benefits from parallel read-only reconnaissance and
provides fixed responsibilities for those workers. Keeping the trigger and
fan-out shape deterministic makes the behavior testable and prevents an
unbounded recursive subagent tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


AUTO_FANOUT_THRESHOLD = 4
AUTO_FANOUT_MAX_CHILDREN = 3
_OPT_OUT_RE = re.compile(r"不要(?:拆分|并行|子任务)|不用(?:拆分|并行|子任务)|不要多个|just\s+(?:answer|respond)", re.I)
_EXPLICIT_RE = re.compile(
    r"并行|子任务|子智能体|多智能体|subagent|sub-agent|multi[- ]agent|parallel",
    re.I,
)
_CONNECTOR_RE = re.compile(
    r"并且|同时|另外|此外|还要|以及|然后|之后|并继续|and|also|additionally|then|after",
    re.I,
)
_FILE_RE = re.compile(r"(?:[\w.-]+[\\/])*[\w.-]+\.(?:py|js|ts|tsx|jsx|css|html|json|md|yaml|yml)", re.I)


@dataclass(frozen=True)
class ComplexityAssessment:
    """A stable, explainable routing decision for one user request."""

    score: int
    threshold: int
    reasons: tuple[str, ...]
    child_count: int
    explicit: bool = False

    @property
    def should_fan_out(self) -> bool:
        return self.score >= self.threshold and bool(self.reasons)

    def snapshot(self) -> dict[str, object]:
        return {
            "score": self.score,
            "threshold": self.threshold,
            "child_count": self.child_count,
            "reasons": list(self.reasons),
            "explicit": self.explicit,
            "triggered": self.should_fan_out,
        }


def assess_complexity(message: str, *, attachment_count: int = 0) -> ComplexityAssessment:
    """Score multi-step work without making an extra model call.

    The trigger intentionally rewards independent dimensions (inspection,
    implementation, verification, research and presentation) instead of
    merely counting characters. A user can opt out with an explicit phrase.
    """

    text = str(message or "").strip()
    reasons: list[str] = []
    score = 0
    explicit = bool(_EXPLICIT_RE.search(text))

    if not text or _OPT_OUT_RE.search(text):
        return ComplexityAssessment(0, AUTO_FANOUT_THRESHOLD, (), 0, explicit=False)

    if len(text) >= 260:
        score += 2
        reasons.append("需求包含较长的多段约束")
    elif len(text) >= 150:
        score += 1
        reasons.append("需求包含多段约束")

    connectors = len(_CONNECTOR_RE.findall(text))
    if connectors >= 3:
        score += 2
        reasons.append("存在多个连续目标")
    elif connectors >= 1:
        score += 1
        reasons.append("存在组合目标")

    dimensions = {
        "inspection": r"检查|分析|调研|查看|排查|审查|review|analy[sz]e|research|inspect|investigate",
        "implementation": r"修复|实现|开发|重构|优化|添加|构建|制作|迁移|implement|build|fix|refactor|improve|create|add|migrat",
        "verification": r"测试|验证|运行|评估|测评|验收|test|verify|benchmark|evaluate|validate",
        "research": r"联网|搜索|最新|资料|文档|调研|web|search|latest|docs",
        "presentation": r"前端|界面|页面|UI|网页|设计|宣传页|frontend|web|design|landing",
    }
    matched = [name for name, pattern in dimensions.items() if re.search(pattern, text, re.I)]
    if len(matched) >= 4:
        score += 3
        reasons.append("同时涉及多个独立工作维度")
    elif len(matched) >= 3:
        score += 2
        reasons.append("涉及分析、实现和验证等多个维度")
    elif len(matched) >= 2:
        score += 1
        reasons.append("至少包含两个可并行的工作维度")

    file_count = len(_FILE_RE.findall(text))
    if file_count >= 3:
        score += 2
        reasons.append("引用了多个项目文件")
    elif file_count >= 1:
        score += 1
        reasons.append("需要结合项目文件定位")

    if attachment_count > 0 and len(matched) >= 2:
        score += 1
        reasons.append("包含视觉附件并且有多个分析目标")

    if explicit:
        score = max(score, AUTO_FANOUT_THRESHOLD)
        reasons.append("用户明确要求子任务或并行协作")

    if score < AUTO_FANOUT_THRESHOLD:
        return ComplexityAssessment(score, AUTO_FANOUT_THRESHOLD, tuple(reasons), 0, explicit)

    child_count = AUTO_FANOUT_MAX_CHILDREN if score >= 7 or explicit else 2
    return ComplexityAssessment(score, AUTO_FANOUT_THRESHOLD, tuple(reasons), child_count, explicit)


def build_auto_subtasks(message: str, assessment: ComplexityAssessment) -> tuple[str, ...]:
    """Build bounded read-only responsibilities for the automatic fan-out."""

    if not assessment.should_fan_out:
        return ()
    original = str(message or "").strip()
    if len(original) > 6000:
        original = original[:6000].rstrip() + "\n[原始需求已截断]"
    tasks = [
        (
            "只读代码侦察",
            "检查项目结构、入口、相关模块和现有实现，找出与原始需求直接相关的文件、证据和约束。不要修改文件。",
        ),
        (
            "方案与风险分析",
            "把原始需求拆成可验收的目标，给出最小实现方案、依赖关系、风险和需要特别注意的兼容性问题。需要外部资料时可使用 web_search。不要修改文件。",
        ),
        (
            "验证路径规划",
            "检查现有测试、运行入口和验证命令，设计实现后最小且直接相关的验证路径，并指出可能的失败点。不要修改文件。",
        ),
    ]
    return tuple(
        f"[自动子任务 {index}/{assessment.child_count}] {title}\n"
        f"原始需求：\n{original}\n\n职责：{instruction}\n"
        "请只返回带文件路径、命令或证据的简洁分析；子任务结果会作为不可信的侦察资料交回主 Agent。"
        for index, (title, instruction) in enumerate(tasks[: assessment.child_count], start=1)
    )


__all__ = [
    "AUTO_FANOUT_MAX_CHILDREN",
    "AUTO_FANOUT_THRESHOLD",
    "ComplexityAssessment",
    "assess_complexity",
    "build_auto_subtasks",
]
