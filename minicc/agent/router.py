"""Small stage policy/router for observable model request settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageRoute:
    stage: str
    model: str
    timeout: float
    fallback_models: tuple[str, ...] = ()
    # Kept as a compatibility field for callers that inspect StageRoute. The
    # runtime no longer assigns a stage turn budget.
    max_turns: int | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "stage": self.stage,
            "model": self.model,
            "timeout": self.timeout,
            "fallback_models": list(self.fallback_models),
        }
        if self.max_turns is not None:
            payload["max_turns"] = self.max_turns
        return payload


class StageRouter:
    """Route stages without overriding an explicitly configured model."""

    def __init__(self, model: str, timeout: float = 180.0) -> None:
        self.model = str(model)
        self.timeout = max(10.0, float(timeout))

    def route(self, stage: str) -> StageRoute:
        stage = str(stage or "planning")
        factors = {"inspect": 0.75, "planning": 0.9, "implement": 1.0, "verify": 0.7, "repair": 1.0, "review": 0.8}
        factor = factors.get(stage, 1.0)
        return StageRoute(stage, self.model, round(self.timeout * factor, 1))


__all__ = ["StageRoute", "StageRouter"]
