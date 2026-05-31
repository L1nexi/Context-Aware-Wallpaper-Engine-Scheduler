from __future__ import annotations

import random
from dataclasses import dataclass
from typing import ClassVar

from utils.runtime_config import PlaylistConfig


@dataclass(frozen=True)
class PlaylistInfo:
    display: str
    color: str
    item_count: int


class Playlists:
    _configs: ClassVar[dict[str, PlaylistInfo]] = {}

    def __init__(self, names: list[str]):
        unique_names: list[str] = []
        for name in names:
            if name not in unique_names:
                unique_names.append(name)
        self._names = unique_names

    @classmethod
    def configure(cls, configs: dict[str, PlaylistConfig]) -> None:
        cls._configs = {
            name: PlaylistInfo(
                display=config.display or name,
                color=config.color,
                item_count=config.item_count,
            )
            for name, config in configs.items()
        }

    @classmethod
    def managed(cls) -> Playlists:
        return Playlists(list(cls._configs.keys()))

    @classmethod
    def is_managed(cls, name: str) -> bool:
        return name in cls._configs

    def names(self) -> list[str]:
        return list(self._names)

    def displays(self) -> dict[str, str]:
        return {n: self._configs[n].display for n in self._names}

    def colors(self) -> dict[str, str]:
        return {n: self._configs[n].color for n in self._names}

    def item_counts(self) -> dict[str, int]:
        return {n: self._configs[n].item_count for n in self._names}

    def select_target(self) -> str:
        weights: list[int] = []
        for name in self._names:
            item_count = self._configs[name].item_count
            weights.append(item_count if item_count > 0 else 1)
        return random.choices(self._names, weights=weights, k=1)[0]

    def __len__(self) -> int:
        return len(self._names)

    def __bool__(self) -> bool:
        return bool(self._names)

    def __getitem__(self, index: int) -> str:
        return self._names[index]

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Playlists):
            return NotImplemented
        return set(self._names) == set(other._names)

    def __hash__(self) -> int:
        return hash(frozenset(self._names))

    def __repr__(self) -> str:
        return f"Playlists({self._names!r})"
