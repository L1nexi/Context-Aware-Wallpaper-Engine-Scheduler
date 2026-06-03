from __future__ import annotations

import logging
import time

from configurations.runtime_models import TimePolicyConfig
from core.models.context import Context
from core.models.trace import TimeDetails, TimeEvaluation
from core.policies.base import Policy, _circular_distance, _hann

logger = logging.getLogger("WEScheduler.Policy")


class TimePolicy(Policy):
    config_key = "time"
    evaluation_cls = TimeEvaluation
    fixed_output_tags = ("dawn", "day", "sunset", "night")

    def __init__(self, config: TimePolicyConfig):
        super().__init__(config)
        self._day_start: float = config.day_start_hour
        self._night_start: float = config.night_start_hour
        self.auto: bool = config.auto

        self._peaks: dict[str, float] = {}
        self._H: float = 6.0
        self._recompute_peaks(self._day_start, self._night_start)

    @staticmethod
    def _compute_peaks(ds: float, ns: float) -> dict[str, float]:
        day_span = (ns - ds) % 24
        night_span = 24 - day_span
        return {
            "dawn": ds,
            "day": (ds + day_span / 2) % 24,
            "sunset": ns % 24,
            "night": (ns + night_span / 2) % 24,
        }

    _TAG_ORDER = fixed_output_tags
    _VIRTUAL_PEAKS = [0.0, 6.0, 12.0, 18.0]

    @staticmethod
    def _warp_time(hour: float, peaks: dict[str, float]) -> float:
        real = [peaks[tag] for tag in TimePolicy._TAG_ORDER]
        n = len(real)
        for i in range(n):
            r_a = real[i]
            r_b = real[(i + 1) % n]
            seg = (r_b - r_a) % 24
            pos = (hour - r_a) % 24
            if pos < seg:
                v_a = TimePolicy._VIRTUAL_PEAKS[i]
                return (v_a + pos / seg * 6.0) % 24
        return 0.0

    def _recompute_peaks(self, ds: float, ns: float) -> None:
        self._day_start = ds
        self._night_start = ns
        self._peaks = self._compute_peaks(ds, ns)

    def _update_from_context(self, context: Context) -> None:
        weather = context.weather
        if weather is None or not weather.sunrise or not weather.sunset:
            return
        sunrise = time.localtime(weather.sunrise)
        sunset = time.localtime(weather.sunset)
        ds = sunrise.tm_hour + sunrise.tm_min / 60.0
        ns = sunset.tm_hour + sunset.tm_min / 60.0
        if abs(ds - self._day_start) > 1 / 60 or abs(ns - self._night_start) > 1 / 60:
            self._recompute_peaks(ds, ns)
            logger.debug("TimePolicy peaks updated: day_start=%.2f night_start=%.2f", ds, ns)

    def evaluate(self, context: Context) -> TimeEvaluation:
        current_time = context.time
        if self.auto:
            self._update_from_context(context)
        hour = current_time.tm_hour + current_time.tm_min / 60.0
        t_virtual = self._warp_time(hour, self._peaks)
        details = TimeDetails(
            auto=self.auto,
            hour=round(hour, 4),
            virtual_hour=round(t_virtual, 4),
            day_start_hour=round(self._day_start, 4),
            night_start_hour=round(self._night_start, 4),
            peaks={tag: round(value, 4) for tag, value in self._peaks.items()},
        )
        if not self.enabled:
            return self._make_evaluation(
                details=details,
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        best_weight = 0.0
        raw: dict[str, float] = {}
        for tag, v_peak in zip(self._TAG_ORDER, self._VIRTUAL_PEAKS):
            distance = _circular_distance(t_virtual, v_peak, 24)
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
