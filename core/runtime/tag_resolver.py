from __future__ import annotations

from configurations.runtime_models import TagSpec

_MIN_EXPAND_WEIGHT = 0.02


def resolve_raw_tags(
    raw_contribution: dict[str, float],
    *,
    known_tags: set[str] | frozenset[str],
    tag_specs: dict[str, TagSpec],
    min_expand_weight: float = _MIN_EXPAND_WEIGHT,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    resolved: dict[str, float] = {}
    expansions: dict[str, dict[str, float]] = {}
    for tag, weight in raw_contribution.items():
        if tag in known_tags:
            resolved[tag] = resolved.get(tag, 0.0) + weight
            continue

        expanded, tag_expansions = _recursive_expand_fallback(
            tag=tag,
            weight=weight,
            visited=frozenset(),
            known_tags=known_tags,
            tag_specs=tag_specs,
            min_expand_weight=min_expand_weight,
        )
        if expanded:
            for resolved_tag, resolved_weight in expanded.items():
                resolved[resolved_tag] = resolved.get(resolved_tag, 0.0) + resolved_weight
            bucket = expansions.setdefault(tag, {})
            for resolved_tag, resolved_weight in tag_expansions.items():
                bucket[resolved_tag] = bucket.get(resolved_tag, 0.0) + resolved_weight
    return resolved, expansions


def _recursive_expand_fallback(
    *,
    tag: str,
    weight: float,
    visited: frozenset[str],
    known_tags: set[str] | frozenset[str],
    tag_specs: dict[str, TagSpec],
    min_expand_weight: float,
) -> tuple[dict[str, float], dict[str, float]]:
    if tag in known_tags:
        return {tag: weight}, {tag: weight}
    if tag in visited or weight < min_expand_weight:
        return {}, {}

    spec = tag_specs.get(tag)
    if not spec or not spec.fallback:
        return {}, {}

    result: dict[str, float] = {}
    expansions: dict[str, float] = {}
    new_visited = visited | {tag}
    for fallback_tag, fallback_weight in spec.fallback.items():
        child_resolved, child_expansions = _recursive_expand_fallback(
            tag=fallback_tag,
            weight=weight * fallback_weight,
            visited=new_visited,
            known_tags=known_tags,
            tag_specs=tag_specs,
            min_expand_weight=min_expand_weight,
        )
        for resolved_tag, resolved_weight in child_resolved.items():
            result[resolved_tag] = result.get(resolved_tag, 0.0) + resolved_weight
        for resolved_tag, resolved_weight in child_expansions.items():
            expansions[resolved_tag] = expansions.get(resolved_tag, 0.0) + resolved_weight
    return result, expansions
