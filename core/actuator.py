from __future__ import annotations

import logging
from typing import Optional

from core.event_logger import EventLogger, EventType

from core.executor import WEExecutor
from core.controller import SchedulingController
from core.context import Context
from core.matcher import MatchResult

logger = logging.getLogger("WEScheduler.Actuator")


def _sorted_tags(tags: dict, top: int = 8):
    return sorted(tags.items(), key=lambda x: x[1], reverse=True)[:top]


def _tag_dict(tags: dict, top: int = 8):
    return {k: round(v, 4) for k, v in _sorted_tags(tags, top)}


def _log_tags(tags: dict):
    tag_str = ", ".join([f"{k}:{v:.2f}" for k, v in _sorted_tags(tags)])
    logger.info(f"Trigger Context: [{tag_str}]")


class Actuator:
    def __init__(self, executor: WEExecutor, controller: SchedulingController,
                 history_logger: EventLogger):
        self.executor = executor
        self.controller = controller
        self._history: EventLogger = history_logger

    def act(self, context: Context, result: Optional[MatchResult], current_playlist: str) -> str:
        if result is None:
            return current_playlist

        best_playlist = result.best_playlist
        tags = result.aggregated_tags

        # Case A: Context suggests a different playlist
        if best_playlist != current_playlist:
            if self.controller.can_switch_playlist(context):
                logger.info(f"[Action] Switching Playlist from '{current_playlist}' to '{best_playlist}'")
                _log_tags(tags)
                self.executor.open_playlist(best_playlist)
                self.controller.notify_playlist_switch()
                self._history.write(EventType.PLAYLIST_SWITCH, {
                    "playlist_from": current_playlist,
                    "playlist_to": best_playlist,
                    "tags": _tag_dict(tags),
                    "similarity": round(result.similarity, 4),
                    "similarity_gap": round(result.similarity_gap, 4),
                    "max_policy_magnitude": round(result.max_policy_magnitude, 4),
                })
                return best_playlist

        # Case B: Context suggests the same playlist (Stable context)
        else:
            if self.controller.can_cycle_wallpaper(context):
                logger.info(f"[Action] Cycling Wallpaper in '{current_playlist}'")
                self.executor.next_wallpaper()
                self.controller.notify_wallpaper_cycle()
                self._history.write(EventType.WALLPAPER_CYCLE, {
                    "playlist": current_playlist,
                    "tags": _tag_dict(tags),
                })

        return current_playlist
