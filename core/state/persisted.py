from __future__ import annotations

import json
import logging
import os

from pydantic import BaseModel

from app.context import get_data_dir

logger = logging.getLogger("WEScheduler.State")

_STATE_FILE = os.path.join(get_data_dir(), "state.json")


class PersistedState(BaseModel):
    """Snapshot of scheduler state that persists across process restarts."""

    paused: bool = False
    pause_until: float = 0.0
    cached_playlists: list[str] = []

    @classmethod
    def load(cls, path: str = _STATE_FILE) -> PersistedState:
        try:
            with open(path, encoding="utf-8") as f:
                return cls.model_validate(json.load(f))
        except FileNotFoundError:
            logger.info("state.json not found, starting with default state.")
            return cls()
        except json.JSONDecodeError:
            logger.warning("Invalid state.json", exc_info=True)
            return cls()
        except OSError:
            logger.warning("Failed to read state.json", exc_info=True)
            return cls()
        except Exception:
            logger.warning("Invalid state.json", exc_info=True)
            return cls()

    def save(self, path: str = _STATE_FILE) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.model_dump_json(indent=2))
        except Exception:
            logger.warning("Failed to write state.json", exc_info=True)
