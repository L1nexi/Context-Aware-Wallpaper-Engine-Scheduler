from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime

logger = logging.getLogger("WEScheduler.History")


class HistoryLogger:
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._event_id: int = 0
        self._current_month: str = ""
        self._filepath: str = ""

    def write(self, event_type: str, data: dict) -> int:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "type": event_type,
            "data": data,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"

        with self._lock:
            self._event_id += 1
            self._ensure_file()
            try:
                with open(self._filepath, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError:
                self._event_id -= 1
                logger.warning("Failed to write history event", exc_info=True)
            return self._event_id

    def _ensure_file(self) -> None:
        month_key = datetime.now(UTC).strftime("%Y-%m")
        if month_key != self._current_month:
            self._current_month = month_key
            self._filepath = os.path.join(self._data_dir, f"history-{month_key}.jsonl")
