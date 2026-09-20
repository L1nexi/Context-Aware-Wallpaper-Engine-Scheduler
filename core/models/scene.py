from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from configurations.runtime_models import SceneConfig


class SceneId(StrEnum):
    DAY_WORK = "day_work"
    DAY_LEISURE = "day_leisure"
    NIGHT_WORK = "night_work"
    NIGHT_LEISURE = "night_leisure"
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"
    SUNSET = "sunset"
    RAIN = "rain"


@dataclass(frozen=True)
class SceneInfo:
    playlist: str
    item_count: int


class Scenes:
    _configs: ClassVar[dict[SceneId, SceneInfo]] = {}

    def __init__(self, ids: list[SceneId] | None = None):
        self._ids = list(dict.fromkeys(ids or []))

    @classmethod
    def configure(cls, configs: Mapping[SceneId, SceneConfig]) -> None:
        cls._configs = {
            scene_id: SceneInfo(
                playlist=config.playlist,
                item_count=config.item_count,
            )
            for scene_id, config in configs.items()
        }

    @classmethod
    def managed(cls) -> Scenes:
        return Scenes(list(cls._configs))

    @classmethod
    def manages_playlist(cls, playlist: str) -> bool:
        return any(config.playlist == playlist for config in cls._configs.values())

    @classmethod
    def for_playlist(cls, playlist: str) -> Scenes:
        return Scenes([scene_id for scene_id, config in cls._configs.items() if config.playlist == playlist])

    def targets_playlist(self, playlist: str) -> bool:
        return any((config := self._configs.get(scene_id)) is not None and config.playlist == playlist for scene_id in self._ids)

    def managed_subset(self) -> Scenes:
        return Scenes([scene_id for scene_id in self._ids if scene_id in self._configs])

    def ids(self) -> list[SceneId]:
        return list(self._ids)

    def item_counts(self) -> dict[SceneId, int]:
        return {scene_id: self._configs[scene_id].item_count for scene_id in self._ids}

    def select_target_playlist(self) -> str:
        weights: list[int] = []
        for scene_id in self._ids:
            item_count = self._configs[scene_id].item_count
            weights.append(item_count if item_count > 0 else 1)
        selected_scene = random.choices(self._ids, weights=weights, k=1)[0]
        return self._configs[selected_scene].playlist

    def __len__(self) -> int:
        return len(self._ids)

    def __bool__(self) -> bool:
        return bool(self._ids)

    def __getitem__(self, index: int) -> SceneId:
        return self._ids[index]

    def __contains__(self, scene_id: object) -> bool:
        return scene_id in self._ids

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Scenes):
            return NotImplemented
        return set(self._ids) == set(other._ids)

    def __hash__(self) -> int:
        return hash(frozenset(self._ids))

    def __repr__(self) -> str:
        return f"Scenes({self._ids!r})"
