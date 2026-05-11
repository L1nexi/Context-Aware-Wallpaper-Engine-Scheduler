from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from core.context import Context
from core.diagnostics import MatchEvaluation, PolicyEvaluation
from utils.runtime_config import PlaylistConfig, TagSpec

if TYPE_CHECKING:
    from core.policies import Policy

logger = logging.getLogger("WEScheduler.Matcher")

_MIN_SIMILARITY = 0.001
_MIN_EXPAND_WEIGHT = 0.02


class Matcher:
    """Owns the full Think pipeline: per-policy eval -> aggregate -> cosine match."""

    def __init__(
        self,
        playlists: Dict[str, PlaylistConfig],
        policies: List[Policy],
        tag_specs: Optional[Dict[str, TagSpec]] = None,
    ):
        self.policies = policies
        self._tag_specs: Dict[str, TagSpec] = tag_specs or {}

        all_tags: set[str] = set()
        for playlist in playlists.values():
            all_tags.update(playlist.tags.keys())

        self._known_tags: set[str] = set(all_tags)
        self.all_tags = sorted(all_tags)
        self.tag_to_index = {tag: i for i, tag in enumerate(self.all_tags)}
        self.dim = len(self.all_tags)

        self._warned_tags: set[str] = set()

        self.playlist_vectors: List[Tuple[str, List[float]]] = []
        for playlist_name, playlist in playlists.items():
            vector = [0.0] * self.dim
            for tag, weight in playlist.tags.items():
                if tag in self.tag_to_index:
                    vector[self.tag_to_index[tag]] = weight
            norm = math.sqrt(sum(x * x for x in vector))
            if norm > 1e-6:
                vector = [x / norm for x in vector]
                self.playlist_vectors.append((playlist_name, vector))
            else:
                logger.warning("Playlist '%s' has no valid tags or zero weights.", playlist_name)

    def evaluate(self, context: Context) -> MatchEvaluation:
        raw_context_vector: Dict[str, float] = {}
        resolved_context_vector: Dict[str, float] = {}
        fallback_expansions: dict[str, dict[str, float]] = {}
        policy_evaluations: list[PolicyEvaluation] = []
        max_policy_magnitude = 0.0

        for policy in self.policies:
            evaluation = policy.evaluate(context)
            policy_evaluations.append(evaluation)
            if evaluation.effective_magnitude > max_policy_magnitude:
                max_policy_magnitude = evaluation.effective_magnitude

            for tag, weight in evaluation.raw_contribution.items():
                raw_context_vector[tag] = raw_context_vector.get(tag, 0.0) + weight

            resolved, expansions = self._resolve_raw_tags(evaluation.raw_contribution)
            evaluation.resolved_contribution = resolved
            for tag, weight in resolved.items():
                resolved_context_vector[tag] = resolved_context_vector.get(tag, 0.0) + weight
            for source_tag, resolved_tags in expansions.items():
                bucket = fallback_expansions.setdefault(source_tag, {})
                for resolved_tag, resolved_weight in resolved_tags.items():
                    bucket[resolved_tag] = bucket.get(resolved_tag, 0.0) + resolved_weight

        best_playlist: Optional[str] = None
        playlist_matches: list[tuple[str, float]] = []

        if self.playlist_vectors and resolved_context_vector:
            env_vector = [0.0] * self.dim
            for tag, weight in resolved_context_vector.items():
                if tag in self.tag_to_index:
                    env_vector[self.tag_to_index[tag]] += weight

            norm_env = math.sqrt(sum(value * value for value in env_vector))
            if norm_env >= 1e-6:
                env_vector = [value / norm_env for value in env_vector]
                scores: List[Tuple[float, str]] = []
                for name, playlist_vector in self.playlist_vectors:
                    sim = sum(a * b for a, b in zip(env_vector, playlist_vector))
                    scores.append((sim, name))

                scores.sort(reverse=True)
                candidate_score, candidate = scores[0]
                playlist_matches = [(name, score) for score, name in scores]
                if candidate_score > _MIN_SIMILARITY:
                    best_playlist = candidate

        return MatchEvaluation(
            best_playlist=best_playlist,
            playlist_matches=playlist_matches,
            raw_context_vector=raw_context_vector,
            resolved_context_vector=resolved_context_vector,
            fallback_expansions=fallback_expansions,
            policy_evaluations=policy_evaluations,
            max_policy_magnitude=max_policy_magnitude,
        )

    def _resolve_raw_tags(
        self,
        raw_contribution: Dict[str, float],
    ) -> tuple[Dict[str, float], dict[str, dict[str, float]]]:
        resolved: Dict[str, float] = {}
        expansions: dict[str, dict[str, float]] = {}
        for tag, weight in raw_contribution.items():
            if tag in self._known_tags:
                resolved[tag] = resolved.get(tag, 0.0) + weight
                continue

            expanded, tag_expansions = self._recursive_expand_fallback(
                tag=tag,
                weight=weight,
                visited=frozenset(),
            )
            if expanded:
                for resolved_tag, resolved_weight in expanded.items():
                    resolved[resolved_tag] = resolved.get(resolved_tag, 0.0) + resolved_weight
                bucket = expansions.setdefault(tag, {})
                for resolved_tag, resolved_weight in tag_expansions.items():
                    bucket[resolved_tag] = bucket.get(resolved_tag, 0.0) + resolved_weight
            elif tag not in self._warned_tags:
                logger.info(
                    "Tag '%s' from a Policy is not present in any playlist "
                    "and has no fallback defined in 'tags' config. Add a "
                    "playlist using this tag, define a fallback, or check "
                    "for typos.",
                    tag,
                )
                self._warned_tags.add(tag)
        return resolved, expansions

    def _recursive_expand_fallback(
        self,
        *,
        tag: str,
        weight: float,
        visited: frozenset[str],
    ) -> tuple[Dict[str, float], dict[str, float]]:
        if tag in self._known_tags:
            return {tag: weight}, {tag: weight}
        if tag in visited or weight < _MIN_EXPAND_WEIGHT:
            return {}, {}

        spec = self._tag_specs.get(tag)
        if not spec or not spec.fallback:
            return {}, {}

        result: Dict[str, float] = {}
        expansions: dict[str, float] = {}
        new_visited = visited | {tag}
        for fallback_tag, fallback_weight in spec.fallback.items():
            child_resolved, child_expansions = self._recursive_expand_fallback(
                tag=fallback_tag,
                weight=weight * fallback_weight,
                visited=new_visited,
            )
            for resolved_tag, resolved_weight in child_resolved.items():
                result[resolved_tag] = result.get(resolved_tag, 0.0) + resolved_weight
            for resolved_tag, resolved_weight in child_expansions.items():
                expansions[resolved_tag] = expansions.get(resolved_tag, 0.0) + resolved_weight
        return result, expansions
