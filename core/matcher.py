from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Optional

if TYPE_CHECKING:
    from core.policies import Policy

from core.context import Context
from utils.config_loader import PlaylistConfig, TagSpec

logger = logging.getLogger("WEScheduler.Matcher")

# Minimum cosine similarity to consider a match valid.
# Below this threshold the environment vector is too orthogonal to all
# playlists to produce a meaningful selection.
_MIN_SIMILARITY = 0.001
_MIN_EXPAND_WEIGHT = 0.02  # stop recursing when contribution drops below this


@dataclass
class MatchResult:
    """Output of Matcher.match(): the best playlist choice plus diagnostics."""
    best_playlist: str
    similarity: float
    aggregated_tags: Dict[str, float] = field(default_factory=dict)


class Matcher:
    """Owns the full Think pipeline: Sense → per-policy eval → aggregate → cosine match.

    Taking policies in the constructor (rather than in match()) keeps match()
    a clean context-in / result-out interface, and avoids scattering policy
    management across Scheduler and a now-redundant Arbiter layer.
    """

    def __init__(
        self,
        playlists: List[PlaylistConfig],
        policies: List[Policy],
        tag_specs: Optional[Dict[str, TagSpec]] = None,
    ):
        self.policies = policies
        self._tag_specs: Dict[str, TagSpec] = tag_specs or {}

        # 1. Identify the Universe of Tags from all playlists
        all_tags: set = set()
        for pl in playlists:
            all_tags.update(pl.tags.keys())

        self._known_tags: set = set(all_tags) # O(1) membership tests
        self.all_tags = sorted(all_tags)
        self.tag_to_index = {tag: i for i, tag in enumerate(self.all_tags)}
        self.dim = len(self.all_tags)

        # Track tags we've already warned about to avoid per-tick spam
        self._warned_tags: set = set()

        # 2. Pre-calculate Normalized Playlist Vectors
        self.playlist_vectors: List[tuple] = []
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
                logger.warning(f"Playlist '{pl.name}' has no valid tags or zero weights.")

    def match(self, context: Context) -> Optional[MatchResult]:
        """Run the full Think pipeline for one tick.

        Returns a :class:`MatchResult` when a valid playlist is found, or
        ``None`` when the environment vector is zero / below the similarity
        threshold (i.e. no policy is producing meaningful output).

        Steps:
          1. Evaluate each Policy against *context*, collect per-policy dicts.
          2. Sum the raw per-policy dicts into *aggregated_tags* (for logging).
          3. Resolve each sub-vector via TagSpec fallback: unknown tags are
             redistributed to playlist-known tags according to their fallback
             chains; tags with no fallback lose their weight (logged once).
          4. Cosine-similarity match against pre-normalised playlist vectors.
        """
        # ── Steps 1–3: evaluate policies, aggregate for logging, resolve + project ──
        aggregated_tags: Dict[str, float] = {}
        v_env = [0.0] * self.dim
        any_valid = False

        for policy in self.policies:
            tags = policy.get_tags(context)
            for tag, w in tags.items():
                aggregated_tags[tag] = aggregated_tags.get(tag, 0.0) + w

            resolved = self._resolve_raw_tags(tags)
            if resolved:
                any_valid = True
                for tag, weight in resolved.items():
                    v_env[self.tag_to_index[tag]] += weight

        if not self.playlist_vectors:
            return None


        if not any_valid:
            return None

        norm_env = math.sqrt(sum(x * x for x in v_env))
        if norm_env < 1e-6:
            return None

        v_env = [x / norm_env for x in v_env]

        # ── Step 4: cosine similarity ─────────────────────────────────────────
        best_score = -1.0
        best_playlist = None
        for name, v_pl in self.playlist_vectors:
            similarity = sum(a * b for a, b in zip(v_env, v_pl))
            if similarity > best_score:
                best_score = similarity
                best_playlist = name

        if best_score <= _MIN_SIMILARITY or best_playlist is None:
            return None

        return MatchResult(
            best_playlist=best_playlist,
            similarity=best_score,
            aggregated_tags=aggregated_tags,
        )

    # ── TagSpec fallback helpers ──────────────────────────────────────────────

    def _resolve_raw_tags(self, sub: Dict[str, float]) -> Dict[str, float]:
        """Project a policy raw tags onto the playlist tag universe.

        Known tags pass through unchanged.  Unknown tags are expanded
        recursively via their :class:`TagSpec` fallback chains.  Unknown
        tags with no fallback lose their weight and are logged once.
        """
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
                        f"Tag '{tag}' from a Policy is not present in any playlist "
                        f"and has no fallback defined in 'tags' config. Add a "
                        f"playlist using this tag, define a fallback, or check "
                        f"for typos."
                    )
                    self._warned_tags.add(tag)
        return resolved

    def _recursive_expand_fallback(
        self, tag: str, weight: float, visited: frozenset
    ) -> Dict[str, float]:
        """Recursively expand one tag via its TagSpec fallback chain.

        Returns ``{known_tag: contributed_weight}`` for all reachable
        known tags.  Returns an empty dict when no known tag is reachable
        (no spec, empty fallback, or all branches cycle/unknown).
        """
        if tag in self._known_tags:
            return {tag: weight}
        if tag in visited or weight < _MIN_EXPAND_WEIGHT:
            return {}  # cycle or contribution too small — stop

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

