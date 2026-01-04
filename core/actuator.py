import logging
from typing import Dict, Any, Optional
from core.executor import WEExecutor
from core.controller import DisturbanceController

logger = logging.getLogger("WEScheduler.Actuator")

class Actuator:
    """
    The 'Act' component of the Sense-Think-Act loop.
    Responsible for executing changes in Wallpaper Engine based on the decision
    from the Matcher and the constraints from the DisturbanceController.
    """
    def __init__(self, executor: WEExecutor, controller: DisturbanceController):
        self.executor = executor
        self.controller = controller

    def act(self, context: Dict[str, Any], aggregated_tags: Dict[str, float], best_playlist: Optional[str], current_playlist: str) -> str:
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
            else:
                # Blocked by wallpaper cooling down
                pass

        return current_playlist
