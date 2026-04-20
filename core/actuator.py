import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from core.executor import WEExecutor
from core.controller import DisturbanceController
from core.context_types import Context
from utils.app_context import get_app_root

logger = logging.getLogger("WEScheduler.Actuator")

_HISTORY_FILE = os.path.join(get_app_root(), "history.jsonl")

class Actuator:
    """
    The 'Act' component of the Sense-Think-Act loop.
    Responsible for executing changes in Wallpaper Engine based on the decision
    from the Matcher and the constraints from the DisturbanceController.
    """
    def __init__(self, executor: WEExecutor, controller: DisturbanceController):
        self.executor = executor
        self.controller = controller

    def act(self, context: Context, aggregated_tags: Dict[str, float], best_playlist: Optional[str], current_playlist: str) -> str:
        """
        Decides and executes the appropriate action.
        Returns the new (or unchanged) current_playlist.
        """
        if not best_playlist:
            return current_playlist

        # Helper to format tags for logging
        def log_tags():
            sorted_tags = sorted(aggregated_tags.items(), key=lambda x: x[1], reverse=True)
            tag_str = ", ".join([f"{k}:{v:.2f}" for k, v in sorted_tags])
            logger.info(f"Trigger Context: [{tag_str}]")

        # Case A: Context suggests a different playlist
        if best_playlist != current_playlist:
            if self.controller.can_switch_playlist(context):
                logger.info(f"[Action] Switching Playlist from '{current_playlist}' to '{best_playlist}'")
                log_tags()
                self.executor.open_playlist(best_playlist)
                self.controller.notify_playlist_switch()
                self._write_history("playlist_switch", aggregated_tags,
                                    playlist_from=current_playlist,
                                    playlist_to=best_playlist)
                return best_playlist
            else:
                # Intent detected but blocked by controller (cooling down or not idle)
                pass
        
        # Case B: Context suggests the same playlist (Stable context)
        else:
            # We might still want to cycle the wallpaper to keep it fresh
            if self.controller.can_cycle_wallpaper(context):
                logger.info(f"[Action] Cycling Wallpaper in '{current_playlist}'")
                self.executor.next_wallpaper()
                self.controller.notify_wallpaper_cycle()
                self._write_history("wallpaper_cycle", aggregated_tags,
                                    playlist=current_playlist)
            else:
                # Blocked by wallpaper cooling down
                pass

        return current_playlist

    @staticmethod
    def _write_history(event: str, tags: Dict[str, float], **extra: Any) -> None:
        """Append a single JSON line to history.jsonl."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "tags": {k: round(v, 3) for k, v in
                     sorted(tags.items(), key=lambda x: x[1], reverse=True)[:5]},
            **extra,
        }
        try:
            with open(_HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("Failed to write history", exc_info=True)
