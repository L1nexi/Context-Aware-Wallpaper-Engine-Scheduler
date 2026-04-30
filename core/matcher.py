from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Optional, Tuple

if TYPE_CHECKING:
    from core.policies import Policy

from core.context import Context
from core.policies import PolicyOutput
from utils.config_loader import PlaylistConfig, TagSpec

logger = logging.getLogger("WEScheduler.Matcher")

_MIN_SIMILARITY = 0.001
_MIN_EXPAND_WEIGHT = 0.02


@dataclass
class MatchResult:
    """Output of Matcher.match(): best playlist choice plus diagnostics."""
    best_playlist: str
    similarity: float
    aggregated_tags: Dict[str, float] = field(default_factory=dict)
    similarity_gap: float = 0.0        # sim(1st) - sim(2nd); 0 if only one playlist
    max_policy_magnitude: float = 0.0  # max(salience * intensity * weight_scale) across policies
    top_matches: list[tuple[str, float]] = field(default_factory=list)


class Matcher:
    """Owns the full Think pipeline: per-policy eval → aggregate → cosine match."""

    def __init__(
        self,
        playlists: List[PlaylistConfig],
        policies: List[Policy],
        tag_specs: Optional[Dict[str, TagSpec]] = None,
    ):
        self.policies = policies
        self._tag_specs: Dict[str, TagSpec] = tag_specs or {}

        # Identify the Universe of Tags from all playlists
        all_tags: set = set()
        for pl in playlists:
            all_tags.update(pl.tags.keys())

        self._known_tags: set = set(all_tags)
        self.all_tags = sorted(all_tags)
        self.tag_to_index = {tag: i for i, tag in enumerate(self.all_tags)}
        self.dim = len(self.all_tags)

        self._warned_tags: set = set()

        # Pre-calculate Normalized Playlist Vectors
        self.playlist_vectors: List[Tuple[str, List[float]]] = []
        for pl in playlists:
            v = [0.0] * self.dim
            for tag, weight in pl.tags.items():
                if tag in self.tag_to_index:
                    v[self.tag_to_index[tag]] = weight
            norm = math.sqrt(sum(x * x for x in v))
            if norm > 1e-6:
                v = [x / norm for x in v]
                self.playlist_vectors.append((pl.name, v))
            else:
                logger.warning("Playlist '%s' has no valid tags or zero weights.", pl.name)

    def match(self, context: Context) -> Optional[MatchResult]:
        """Run the full Think pipeline for one tick.

        Aggregates policy contributions as:
            env_vector += direction * salience * intensity * weight_scale
        Applies TagSpec fallback on the aggregated env_vector before cosine match.
        """
        aggregated_tags: Dict[str, float] = {}
        v_env = [0.0] * self.dim
        any_valid = False
        max_magnitude = 0.0

        for policy in self.policies:
            output: Optional[PolicyOutput] = policy.get_output(context)
            if output is None:
                continue

            magnitude = output.salience * output.intensity * policy.weight_scale
            if magnitude > max_magnitude:
                max_magnitude = magnitude

            # Build contribution: direction * salience * intensity * weight_scale
            contrib: Dict[str, float] = {
                t: w * magnitude for t, w in output.direction.items()
            }

            for tag, w in contrib.items():
                aggregated_tags[tag] = aggregated_tags.get(tag, 0.0) + w

            resolved = self._resolve_raw_tags(contrib)
            if resolved:
                any_valid = True
                for tag, weight in resolved.items():
                    v_env[self.tag_to_index[tag]] += weight

        if not self.playlist_vectors or not any_valid:
            return None

        norm_env = math.sqrt(sum(x * x for x in v_env))
        if norm_env < 1e-6:
            return None
        v_env = [x / norm_env for x in v_env]

        # Cosine similarity — collect top-2 for similarity_gap
        scores: List[Tuple[float, str]] = []
        for name, v_pl in self.playlist_vectors:
            sim = sum(a * b for a, b in zip(v_env, v_pl))
            scores.append((sim, name))

        scores.sort(reverse=True)
        best_score, best_playlist = scores[0]

        if best_score <= _MIN_SIMILARITY:
            return None

        gap = best_score - scores[1][0] if len(scores) > 1 else best_score
        top_matches = [(name, round(score, 4)) for score, name in scores[:5]]

        return MatchResult(
            best_playlist=best_playlist,
            similarity=best_score,
            aggregated_tags=aggregated_tags,
            similarity_gap=gap,
            max_policy_magnitude=max_magnitude,
            top_matches=top_matches,
        )

    # ── TagSpec fallback helpers ──────────────────────────────────────────────

    def _resolve_raw_tags(self, sub: Dict[str, float]) -> Dict[str, float]:
        resolved: Dict[str, float] = {}
        for tag, weight in sub.items():
            if tag in self._known_tags:
                resolved[tag] = resolved.get(tag, 0.0) + weight
            else:
                expanded = self._recursive_expand_fallback(tag, weight, frozenset())
                if expanded:
                    for t, w in expanded.items():
                        resolved[t] = resolved.get(t, 0.0) + w
                elif tag not in self._warned_tags:
                    logger.info(
                        "Tag '%s' from a Policy is not present in any playlist "
                        "and has no fallback defined in 'tags' config. Add a "
                        "playlist using this tag, define a fallback, or check "
                        "for typos.", tag,
                    )
                    self._warned_tags.add(tag)
        return resolved

    def _recursive_expand_fallback(
        self, tag: str, weight: float, visited: frozenset
    ) -> Dict[str, float]:
        if tag in self._known_tags:
            return {tag: weight}
        if tag in visited or weight < _MIN_EXPAND_WEIGHT:
            return {}

        spec = self._tag_specs.get(tag)
        if not spec or not spec.fallback:
            return {}

        result: Dict[str, float] = {}
        new_visited = visited | {tag}
        for fb_tag, fb_weight in spec.fallback.items():
            for t, w in self._recursive_expand_fallback(
                fb_tag, weight * fb_weight, new_visited
            ).items():
                result[t] = result.get(t, 0.0) + w
        return result
