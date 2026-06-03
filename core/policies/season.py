from __future__ import annotations

from configurations.runtime_models import SeasonPolicyConfig
from core.models.context import Context
from core.models.trace import SeasonDetails, SeasonEvaluation
from core.policies.base import Policy, _circular_distance, _hann


class SeasonPolicy(Policy):
    config_key = "season"
    evaluation_cls = SeasonEvaluation
    fixed_output_tags = ("spring", "summer", "autumn", "winter")

    def __init__(self, config: SeasonPolicyConfig):
        super().__init__(config)
        self._peaks = {
            "spring": config.spring_peak,
            "summer": config.summer_peak,
            "autumn": config.autumn_peak,
            "winter": config.winter_peak,
        }
        self._H = 365 / len(self._peaks)

    def evaluate(self, context: Context) -> SeasonEvaluation:
        day_of_year = context.time.tm_yday
        details = SeasonDetails(
            day_of_year=day_of_year,
            peaks=self._peaks.copy(),
        )
        if not self.enabled:
            return self._make_evaluation(
                details=details,
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        raw: dict[str, float] = {}
        best_weight = 0.0
        for tag, peak in self._peaks.items():
            distance = _circular_distance(day_of_year, peak, 365)
            weight = _hann(distance, self._H)
            if weight > 1e-4:
                raw[tag] = weight
                best_weight = max(best_weight, weight)
        return self._make_evaluation(
            details=details,
            raw_direction=raw,
            salience=best_weight,
            intensity=1.0 if raw else 0.0,
        )
