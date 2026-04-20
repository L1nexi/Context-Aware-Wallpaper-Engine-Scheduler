import math
import logging
from typing import TYPE_CHECKING, List, Dict, Any, Optional, Tuple

if TYPE_CHECKING:
    from core.policies import Policy

logger = logging.getLogger("WEScheduler.Matcher")

# Minimum cosine similarity to consider a match valid.
# Below this threshold the environment vector is too orthogonal to all
# playlists to produce a meaningful selection.
_MIN_SIMILARITY = 0.001


class Matcher:
    """Owns the full Think pipeline: Sense → per-policy eval → aggregate → cosine match.

    Taking policies in the constructor (rather than in match()) keeps match()
    a clean context-in / result-out interface, and avoids scattering policy
    management across Scheduler and a now-redundant Arbiter layer.
    """

    def __init__(self, playlists: List[Dict[str, Any]], policies: List["Policy"]):
        self.policies = policies

        # 1. Identify the Universe of Tags from all playlists
        self.all_tags: set = set()
        for pl in playlists:
            tags = pl.get("tags", [])
            if isinstance(tags, list):
                self.all_tags.update(tags)
            elif isinstance(tags, dict):
                self.all_tags.update(tags.keys())

        self.all_tags = sorted(list(self.all_tags))
        self.tag_to_index = {tag: i for i, tag in enumerate(self.all_tags)}
        self.dim = len(self.all_tags)

        # Track tags we've already warned about to avoid per-tick spam
        self._warned_tags: set = set()

        # 2. Pre-calculate Normalized Playlist Vectors
        self.playlist_vectors: List[tuple] = []
        for pl in playlists:
            v = [0.0] * self.dim
            tags = pl.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    if tag in self.tag_to_index:
                        v[self.tag_to_index[tag]] = 1.0
            elif isinstance(tags, dict):
                for tag, weight in tags.items():
                    if tag in self.tag_to_index:
                        v[self.tag_to_index[tag]] = weight

            norm = math.sqrt(sum(x * x for x in v))
            if norm > 1e-6:
                v = [x / norm for x in v]
                self.playlist_vectors.append((pl.get("name"), v))
            else:
                logger.warning(f"Playlist '{pl.get('name')}' has no valid tags or zero weights.")

    def match(self, context: Dict[str, Any]) -> Tuple[Dict[str, float], Optional[str]]:
        """Run the full Think pipeline for one tick.

        Steps:
          1. Evaluate each Policy against *context*, collect per-policy dicts.
          2. Sum the raw per-policy dicts into *aggregated_tags* (for logging).
          3. Project each policy's output onto the playlist tag universe;
             apply per-policy norm-preserving rescaling so that dropping an
             unknown tag (e.g. #storm with no matching playlist) only
             compensates the *remaining tags of that policy* (#rain), leaving
             every other policy's contribution completely untouched.
          4. Cosine-similarity match against pre-normalised playlist vectors.
        """
        # ── Step 1 & 2: evaluate policies, build aggregated_tags for logging ──
        per_policy: List[List[Dict[str, float]]] = []
        aggregated_tags: Dict[str, float] = {}
        for policy in self.policies:
            sub_vectors = policy.get_tags(context)
            per_policy.append(sub_vectors)
            for sub in sub_vectors:
                for tag, w in sub.items():
                    aggregated_tags[tag] = aggregated_tags.get(tag, 0.0) + w

        if not self.playlist_vectors:
            return aggregated_tags, None

        # ── Step 3: per-sub-vector projection + norm-preserving compensation ─
        # Each sub-vector is an independent energy source.  Compensation for
        # dropped tags is scoped to the sub-vector it came from, so tags that
        # are semantic opposites (e.g. #cloudy / #clear) can never boost each
        # other when one is absent from all playlists.
        v_env = [0.0] * self.dim
        any_valid = False
        for sub_vectors in per_policy:
            for sub in sub_vectors:
                if not sub:
                    continue

                # Warn once per unknown tag
                for tag in sub:
                    if tag not in self.tag_to_index and tag not in self._warned_tags:
                        logger.info(
                            f"Tag '{tag}' from a Policy is not present in any playlist "
                            f"and will be ignored. Add a playlist using this tag, or "
                            f"check your Policy/config for typos."
                        )
                        self._warned_tags.add(tag)

                # Project onto valid tag set
                valid = {t: w for t, w in sub.items() if t in self.tag_to_index}
                if not valid:
                    continue
                any_valid = True

                # Norm-preserving rescale scoped to this sub-vector only.
                if len(valid) < len(sub):
                    orig_norm_sq = sum(w * w for w in sub.values())
                    valid_norm_sq = sum(w * w for w in valid.values())
                    if valid_norm_sq > 1e-12:
                        scale = math.sqrt(orig_norm_sq / valid_norm_sq)
                        valid = {t: w * scale for t, w in valid.items()}

                for tag, weight in valid.items():
                    v_env[self.tag_to_index[tag]] += weight


        if not any_valid:
            return aggregated_tags, None

        norm_env = math.sqrt(sum(x * x for x in v_env))
        if norm_env < 1e-6:
            return aggregated_tags, None

        v_env = [x / norm_env for x in v_env]

        # ── Step 4: cosine similarity ─────────────────────────────────────────
        best_score = -1.0
        best_playlist = None
        for name, v_pl in self.playlist_vectors:
            similarity = sum(a * b for a, b in zip(v_env, v_pl))
            if similarity > best_score:
                best_score = similarity
                best_playlist = name

        if best_score <= _MIN_SIMILARITY:
            best_playlist = None

        return aggregated_tags, best_playlist

