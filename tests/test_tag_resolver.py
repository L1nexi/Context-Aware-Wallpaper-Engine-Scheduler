from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from configurations.runtime_models import TagSpec
from core.runtime.tag_resolver import resolve_raw_tags


def _specs(definitions: dict[str, dict[str, float]]) -> dict[str, TagSpec]:
    return {tag: TagSpec(fallback=fallback) for tag, fallback in definitions.items()}


class TestResolveRawTags:
    def test_known_tag_passes_through(self) -> None:
        known = {"focus", "chill"}
        resolved, expansions = resolve_raw_tags(
            {"focus": 0.8},
            known_tags=known,
            tag_specs={},
        )
        assert resolved == {"focus": 0.8}
        assert expansions == {}

    def test_unknown_tag_without_fallback_drops(self) -> None:
        resolved, expansions = resolve_raw_tags(
            {"mystery": 0.5},
            known_tags={"focus"},
            tag_specs={},
        )
        assert resolved == {}
        assert expansions == {}

    def test_unknown_tag_with_empty_fallback_drops(self) -> None:
        resolved, expansions = resolve_raw_tags(
            {"mystery": 0.5},
            known_tags={"focus"},
            tag_specs=_specs({"mystery": {}}),
        )
        assert resolved == {}
        assert expansions == {}

    def test_one_level_fallback(self) -> None:
        resolved, expansions = resolve_raw_tags(
            {"coding": 1.0},
            known_tags={"focus"},
            tag_specs=_specs({"coding": {"focus": 1.0}}),
        )
        assert resolved == {"focus": 1.0}
        assert expansions == {"coding": {"focus": 1.0}}

    def test_one_level_fallback_with_weight_scaling(self) -> None:
        resolved, expansions = resolve_raw_tags(
            {"coding": 1.0},
            known_tags={"focus", "chill"},
            tag_specs=_specs({"coding": {"focus": 0.6, "chill": 0.4}}),
        )
        assert resolved["focus"] == pytest.approx(0.6)
        assert resolved["chill"] == pytest.approx(0.4)
        assert expansions == {"coding": {"focus": 0.6, "chill": 0.4}}

    def test_multi_level_fallback(self) -> None:
        specs = _specs(
            {
                "deep_work": {"coding": 1.0},
                "coding": {"focus": 1.0},
            }
        )
        resolved, expansions = resolve_raw_tags(
            {"deep_work": 1.0},
            known_tags={"focus"},
            tag_specs=specs,
        )
        assert resolved == {"focus": 1.0}
        assert expansions == {"deep_work": {"focus": 1.0}}

    def test_cycle_fallback_returns_empty(self) -> None:
        specs = _specs(
            {
                "a": {"b": 1.0},
                "b": {"a": 1.0},
            }
        )
        resolved, expansions = resolve_raw_tags(
            {"a": 1.0},
            known_tags={"focus"},
            tag_specs=specs,
        )
        assert resolved == {}
        assert expansions == {}

    def test_low_weight_cutoff_stops_expansion(self) -> None:
        specs = _specs({"coding": {"focus": 1.0}})
        resolved, expansions = resolve_raw_tags(
            {"coding": 0.01},
            known_tags={"focus"},
            tag_specs=specs,
            min_expand_weight=0.02,
        )
        assert resolved == {}
        assert expansions == {}

    def test_weight_at_threshold_expands(self) -> None:
        specs = _specs({"coding": {"focus": 1.0}})
        resolved, expansions = resolve_raw_tags(
            {"coding": 0.02},
            known_tags={"focus"},
            tag_specs=specs,
            min_expand_weight=0.02,
        )
        assert resolved == {"focus": pytest.approx(0.02)}
        assert expansions == {"coding": {"focus": pytest.approx(0.02)}}

    def test_multiple_raw_tags_accumulate_same_known_tag(self) -> None:
        specs = _specs({"coding": {"focus": 1.0}})
        resolved, expansions = resolve_raw_tags(
            {"focus": 0.3, "coding": 0.5},
            known_tags={"focus"},
            tag_specs=specs,
        )
        assert resolved["focus"] == pytest.approx(0.8)
        assert expansions == {"coding": {"focus": 0.5}}

    def test_multi_level_fallback_accumulates(self) -> None:
        specs = _specs(
            {
                "x": {"focus": 0.5, "chill": 0.5},
                "y": {"focus": 0.3},
            }
        )
        resolved, expansions = resolve_raw_tags(
            {"x": 1.0, "y": 1.0},
            known_tags={"focus", "chill"},
            tag_specs=specs,
        )
        assert resolved["focus"] == pytest.approx(0.8)
        assert resolved["chill"] == pytest.approx(0.5)

    def test_empty_contribution(self) -> None:
        resolved, expansions = resolve_raw_tags(
            {},
            known_tags={"focus"},
            tag_specs={},
        )
        assert resolved == {}
        assert expansions == {}

    def test_self_referencing_tag_cycle(self) -> None:
        specs = _specs({"a": {"a": 1.0}})
        resolved, expansions = resolve_raw_tags(
            {"a": 1.0},
            known_tags=set(),
            tag_specs=specs,
        )
        assert resolved == {}
        assert expansions == {}


class TestConsistencyWithMatcher:
    """Verify that resolve_raw_tags produces identical output to Matcher._resolve_raw_tags."""

    def test_consistency_across_various_contributions(self) -> None:
        from core.runtime.matcher import Matcher

        playlist_configs = {
            "A": MagicMock(tags={"focus": 1.0, "day": 0.8}),
            "B": MagicMock(tags={"chill": 1.0, "night": 0.7}),
        }
        tag_specs = _specs(
            {
                "coding": {"focus": 1.0},
                "deep_work": {"coding": 0.7, "chill": 0.3},
                "a": {"b": 1.0},
                "b": {"a": 1.0},
                "lo": {"focus": 1.0},
                "x": {"focus": 0.5, "chill": 0.5},
            }
        )
        matcher = Matcher(playlist_configs, [], tag_specs)

        contributions = [
            {},
            {"focus": 0.5},
            {"coding": 1.0},
            {"deep_work": 1.0},
            {"focus": 0.3, "coding": 0.5},
            {"a": 1.0},  # cycle
            {"lo": 0.01},  # below min weight
            {"mystery": 0.5},  # no fallback
            {"x": 1.0, "coding": 0.4},
        ]

        for raw in contributions:
            expected = matcher._resolve_raw_tags(raw)
            actual = resolve_raw_tags(
                raw,
                known_tags=matcher._known_tags,
                tag_specs=matcher._tag_specs,
            )
            assert actual == expected, f"Mismatch for {raw!r}: {actual!r} != {expected!r}"
