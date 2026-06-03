from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from configurations.runtime_models import BasePolicyConfig, PoliciesConfig
from core.models.context import Context
from core.models.trace import BaseEvaluation

logger = logging.getLogger("WEScheduler.Policy")


def _circular_distance(a: float, b: float, period: float) -> float:
    d = abs(a - b) % period
    return min(d, period - d)


def _hann(d: float, H: float) -> float:
    """Hann window: 0.5*(1 + cos(pi*d/H)) for d < H, else 0."""
    if d >= H:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * d / H))


class Policy(ABC):
    # Config key matching the attribute name on PoliciesConfig.
    # Each concrete subclass must define this as a class-level string.
    config_key: ClassVar[str]
    evaluation_cls: ClassVar[type[BaseEvaluation]]
    fixed_output_tags: ClassVar[tuple[str, ...] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "config_key" not in cls.__dict__:
            return
        valid_keys = set(PoliciesConfig.model_fields.keys())
        if cls.config_key not in valid_keys:
            raise TypeError(
                f"{cls.__name__}.config_key={cls.config_key!r} is not a field "
                f"of PoliciesConfig (valid: {sorted(valid_keys)}). "
                "Update runtime_config.py or the policy class."
            )
        if "fixed_output_tags" in cls.__dict__ and cls.fixed_output_tags is not None:
            if not isinstance(cls.fixed_output_tags, tuple) or any(not isinstance(tag, str) or not tag for tag in cls.fixed_output_tags):
                raise TypeError(f"{cls.__name__}.fixed_output_tags must be a tuple[str, ...] when provided.")

    def __init__(self, config: BasePolicyConfig):
        self.config = config
        self.enabled = config.enabled
        self.weight = config.weight

    def _make_evaluation(
        self,
        *,
        details: object,
        raw_direction: dict[str, float] | None,
        salience: float,
        intensity: float,
    ) -> BaseEvaluation:
        raw_direction = raw_direction or {}
        active = False
        direction: dict[str, float] = {}
        raw_contribution: dict[str, float] = {}
        effective_magnitude = 0.0
        dominant_tag = max(raw_direction, key=raw_direction.get) if raw_direction else None

        if self.enabled and raw_direction and salience > 0 and intensity > 0:
            norm = math.sqrt(sum(weight * weight for weight in raw_direction.values()))
            if norm >= 1e-6:
                active = True
                direction = {tag: weight / norm for tag, weight in raw_direction.items()}
                effective_magnitude = salience * intensity * self.weight
                raw_contribution = {tag: weight * effective_magnitude for tag, weight in direction.items()}

        return self.evaluation_cls(
            policy_id=self.config_key,
            enabled=self.enabled,
            active=active,
            weight=self.weight,
            salience=max(salience, 0.0) if self.enabled else 0.0,
            intensity=max(intensity, 0.0) if self.enabled else 0.0,
            effective_magnitude=effective_magnitude,
            direction=direction,
            raw_contribution=raw_contribution,
            dominant_tag=dominant_tag,
            details=details,
        )

    @abstractmethod
    def evaluate(self, context: Context) -> BaseEvaluation: ...

    def export_state(self) -> dict[str, Any]:
        return {}

    def import_state(self, state: dict[str, Any]) -> None:
        pass
