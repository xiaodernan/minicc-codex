"""Small stage policy/router for observable model budgets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageRoute:
    stage: str
    model: str
    timeout: float
    fallback_models: tuple[str, ...] = ()
    max_turns: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {"stage": self.stage, "model": self.model, "timeout": self.timeout, "fallback_models": list(self.fallback_models), "max_turns": self.max_turns}


class StageRouter:
    """Route stages without overriding an explicitly configured model."""

    def __init__(self, model: str, timeout: float = 180.0) -> None:
        self.model = str(model)
        self.timeout = max(10.0, float(timeout))

    def route(self, stage: str) -> StageRoute:
        stage = str(stage or "planning")
        limits = {"inspect": (0.75, 8), "planning": (0.9, 6), "implement": (1.0, None), "verify": (0.7, 4), "repair": (1.0, None), "review": (0.8, 4)}
        factor, max_turns = limits.get(stage, (1.0, None))
        return StageRoute(stage, self.model, round(self.timeout * factor, 1), (), max_turns)


__all__ = ["StageRoute", "StageRouter"]
