from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from configurations.runtime_models import SceneConfig, TagSpec
from core.models.context import Context
from core.models.scene import SceneId, Scenes
from core.models.trace import Match, PolicyEvaluation
from core.runtime.tag_resolver import resolve_raw_tags

if TYPE_CHECKING:
    from core.policies import Policy

logger = logging.getLogger("WEScheduler.Matcher")

_MIN_SIMILARITY = 0.001
_CLUSTER_GAP_THRESHOLD = 0.02
_MAX_CLUSTER_SIZE = 3


class Matcher:
    def __init__(
        self,
        scene_configs: dict[SceneId, SceneConfig],
        policies: list[Policy],
        tag_specs: dict[str, TagSpec] | None = None,
    ):
        self.policies = policies
        self._tag_specs: dict[str, TagSpec] = tag_specs or {}
        self._item_counts: dict[SceneId, int] = {scene_id: config.item_count for scene_id, config in scene_configs.items()}

        all_tags: set[str] = set()
        for scene in scene_configs.values():
            all_tags.update(scene.tags.keys())

        self._known_tags: set[str] = set(all_tags)
        self.all_tags = sorted(all_tags)
        self.tag_to_index = {tag: i for i, tag in enumerate(self.all_tags)}
        self.dim = len(self.all_tags)

        self._warned_tags: set[str] = set()

        self.scene_vectors: list[tuple[SceneId, list[float]]] = []
        for scene_id, scene in scene_configs.items():
            vector = [0.0] * self.dim
            for tag, weight in scene.tags.items():
                if tag in self.tag_to_index:
                    vector[self.tag_to_index[tag]] = weight
            norm = math.sqrt(sum(x * x for x in vector))
            if norm > 1e-6:
                vector = [x / norm for x in vector]
                self.scene_vectors.append((scene_id, vector))
            else:
                logger.warning("Scene '%s' has no valid tags or zero weights.", scene_id)

    def match(self, context: Context) -> Match:
        raw_context_vector: dict[str, float] = {}
        resolved_context_vector: dict[str, float] = {}
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

        best_scene_ids: list[SceneId] = []
        scene_matches: list[tuple[SceneId, float]] = []

        if self.scene_vectors and resolved_context_vector:
            env_vector = [0.0] * self.dim
            for tag, weight in resolved_context_vector.items():
                if tag in self.tag_to_index:
                    env_vector[self.tag_to_index[tag]] += weight

            norm_env = math.sqrt(sum(value * value for value in env_vector))
            if norm_env >= 1e-6:
                env_vector = [value / norm_env for value in env_vector]
                raw_scores: list[tuple[float, SceneId]] = []
                for scene_id, scene_vector in self.scene_vectors:
                    sim = sum(a * b for a, b in zip(env_vector, scene_vector))
                    raw_scores.append((sim, scene_id))

                raw_scores.sort(reverse=True)
                scene_matches = [(scene_id, score) for score, scene_id in raw_scores]

                # Gap-based clustering
                for i, (score, scene_id) in enumerate(raw_scores):
                    if score < _MIN_SIMILARITY:
                        break
                    if i >= _MAX_CLUSTER_SIZE:
                        break
                    if i > 0 and raw_scores[i - 1][0] - score > _CLUSTER_GAP_THRESHOLD:
                        break
                    best_scene_ids.append(scene_id)

        best_scenes = Scenes(best_scene_ids)
        # Compute similarity: weighted average of best_scenes scores by item_count
        similarity = 0.0
        if best_scenes and scene_matches:
            score_lookup = dict(scene_matches)
            weights = self._item_counts
            weighted_sum = 0.0
            total_weight = 0.0
            for scene_id in best_scenes.ids():
                score = score_lookup.get(scene_id, 0.0)
                weight = weights.get(scene_id, 0)
                if weight > 0:
                    weighted_sum += score * weight
                    total_weight += weight
                else:
                    weighted_sum += score
                    total_weight += 1
            similarity = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Compute similarity_gap: top-1 vs top-2 score difference
        similarity_gap = 0.0
        if scene_matches:
            if len(scene_matches) >= 2:
                similarity_gap = scene_matches[0][1] - scene_matches[1][1]
            else:
                similarity_gap = scene_matches[0][1]

        return Match(
            best_scenes=best_scenes,
            scene_matches=scene_matches,
            raw_context_vector=raw_context_vector,
            resolved_context_vector=resolved_context_vector,
            fallback_expansions=fallback_expansions,
            policy_evaluations=policy_evaluations,
            max_policy_magnitude=max_policy_magnitude,
            similarity=similarity,
            similarity_gap=similarity_gap,
        )

    def _resolve_raw_tags(
        self,
        raw_contribution: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        resolved, expansions = resolve_raw_tags(
            raw_contribution,
            known_tags=self._known_tags,
            tag_specs=self._tag_specs,
        )
        for tag in raw_contribution:
            if tag not in self._known_tags and tag not in expansions and tag not in self._warned_tags:
                logger.info(
                    "Built-in Policy tag '%s' has no matching Scene preset or fallback; check product preset consistency.",
                    tag,
                )
                self._warned_tags.add(tag)
        return resolved, expansions

    def export_state(self) -> dict[str, dict[str, Any]]:
        return {type(policy).__name__: policy.export_state() for policy in self.policies}

    def import_state(self, state: dict[str, dict[str, Any]]) -> None:
        for policy in self.policies:
            saved = state.get(type(policy).__name__)
            if saved:
                policy.import_state(saved)
