from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from configurations.runtime_models import ActivityPolicyConfig
from core.models.context import Context
from core.models.trace import ActivityDetails, ActivityEvaluation
from core.policies.base import Policy

_MATCH_SOURCE_PRIORITY = {
    "process": 0,
    "title": 1,
}

_MATCH_TYPE_PRIORITY = {
    "contains": 0,
    "regex": 1,
    "exact": 2,
}


@dataclass(frozen=True)
class CompiledActivityMatcher:
    source: str
    match: str
    pattern: str
    tag: str
    case_sensitive: bool
    declaration_order: int
    regex: re.Pattern[str] | None = None

    @property
    def literal_length(self) -> int:
        if self.match == "regex":
            return 0
        return len(self.pattern)

    @property
    def priority(self) -> tuple[int, int, int, int]:
        return (
            _MATCH_SOURCE_PRIORITY[self.source],
            _MATCH_TYPE_PRIORITY[self.match],
            self.literal_length,
            -self.declaration_order,
        )


class ActivityPolicy(Policy):
    config_key = "activity"
    evaluation_cls = ActivityEvaluation

    def __init__(self, config: ActivityPolicyConfig):
        super().__init__(config)
        self.matchers: list[CompiledActivityMatcher] = []
        for declaration_order, matcher in enumerate(config.matchers):
            compiled_regex = None
            if matcher.match == "regex":
                flags = 0 if matcher.case_sensitive else re.IGNORECASE
                compiled_regex = re.compile(matcher.pattern, flags)
            self.matchers.append(
                CompiledActivityMatcher(
                    source=matcher.source,
                    match=matcher.match,
                    pattern=matcher.pattern,
                    tag=matcher.tag,
                    case_sensitive=matcher.case_sensitive,
                    declaration_order=declaration_order,
                    regex=compiled_regex,
                )
            )

        smoothing_window = config.smoothing_window
        if smoothing_window <= 1:
            self.alpha = 1.0
        else:
            self.alpha = 2.0 / (smoothing_window + 1.0)

        self._dir_ema: dict[str, float] = {}
        self._mag_ema: float = 0.0

    def evaluate(self, context: Context) -> ActivityEvaluation:
        if not self.enabled:
            return self._make_evaluation(
                details=ActivityDetails(
                    window_title=context.window.title,
                    process=context.window.process,
                ),
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        instant_dir, details = self._get_instant_signal(context)

        all_tags = set(self._dir_ema.keys()) | set(instant_dir.keys())
        new_dir_ema: dict[str, float] = {}
        for tag in all_tags:
            cur = instant_dir.get(tag, 0.0)
            prev = self._dir_ema.get(tag, 0.0)
            value = self.alpha * cur + (1.0 - self.alpha) * prev
            if value >= 1e-6:
                new_dir_ema[tag] = value
        self._dir_ema = new_dir_ema

        instant_mag = 1.0 if instant_dir else 0.0
        self._mag_ema = self.alpha * instant_mag + (1.0 - self.alpha) * self._mag_ema

        if not instant_dir:
            details.ema_active = bool(self._dir_ema)

        return self._make_evaluation(
            details=details,
            raw_direction=dict(self._dir_ema),
            salience=1.0 if self._dir_ema else 0.0,
            intensity=self._mag_ema if self._dir_ema else 0.0,
        )

    def _get_instant_signal(
        self,
        context: Context,
    ) -> tuple[dict[str, float], ActivityDetails]:
        details = ActivityDetails(
            window_title=context.window.title,
            process=context.window.process,
        )

        matched = self._select_matcher(context)
        if matched is not None:
            details.match_source = matched.source
            details.matched_rule = matched.pattern
            details.matched_tag = matched.tag
            return {matched.tag: 1.0}, details

        return {}, details

    def _select_matcher(self, context: Context) -> CompiledActivityMatcher | None:
        matched: CompiledActivityMatcher | None = None

        for matcher in self.matchers:
            if not self._matcher_matches(matcher, context):
                continue
            if matched is None or matcher.priority > matched.priority:
                matched = matcher

        return matched

    def _matcher_matches(
        self,
        matcher: CompiledActivityMatcher,
        context: Context,
    ) -> bool:
        observed = context.window.process if matcher.source == "process" else context.window.title
        if matcher.match == "exact":
            return self._matches_exact(matcher, observed)
        if matcher.match == "contains":
            return self._matches_contains(matcher, observed)
        if matcher.regex is None:
            return False
        return matcher.regex.search(observed) is not None

    @staticmethod
    def _matches_exact(
        matcher: CompiledActivityMatcher,
        observed: str,
    ) -> bool:
        pattern = matcher.pattern
        if matcher.source == "process":
            pattern = ActivityPolicy._strip_optional_exe_suffix(pattern, matcher.case_sensitive)
            observed = ActivityPolicy._strip_optional_exe_suffix(observed, matcher.case_sensitive)

        if matcher.case_sensitive:
            return observed == pattern
        return observed.lower() == pattern.lower()

    @staticmethod
    def _matches_contains(
        matcher: CompiledActivityMatcher,
        observed: str,
    ) -> bool:
        if matcher.case_sensitive:
            return matcher.pattern in observed
        return matcher.pattern.lower() in observed.lower()

    @staticmethod
    def _strip_optional_exe_suffix(value: str, case_sensitive: bool) -> str:
        suffix = ".exe"
        if case_sensitive:
            return value[: -len(suffix)] if value.endswith(suffix) else value
        return value[: -len(suffix)] if value.lower().endswith(suffix) else value

    def export_state(self) -> dict[str, Any]:
        return {
            "dir_ema": self._dir_ema.copy(),
            "mag_ema": self._mag_ema,
        }

    def import_state(self, state: dict[str, Any]) -> None:
        allowed_tags = {matcher.tag for matcher in self.matchers}
        self._dir_ema = {tag: float(value) for tag, value in state.get("dir_ema", {}).items() if tag in allowed_tags}
        self._mag_ema = float(state.get("mag_ema", 0.0))
