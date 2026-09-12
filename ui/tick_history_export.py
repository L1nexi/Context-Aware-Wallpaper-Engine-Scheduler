from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.state.tick_history import TickHistoryStore, TickHistoryWindow
from ui.tick_history import build_tick_window_response

_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "lat",
    "latitude",
    "location",
    "lon",
    "longitude",
}


class TickHistoryJsonFormatter:
    @staticmethod
    def format(window: TickHistoryWindow) -> str:
        """Format one Tick History window as JSON.

        Raises:
            TypeError: If a trace contains an unsupported value.
        """

        payload = build_tick_window_response(window)
        redacted = redact_tick_history_payload(payload)
        return json.dumps(redacted, ensure_ascii=False, indent=2) + "\n"


def redact_tick_history_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with credentials and geographic location removed."""

    return _redact_value(payload)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _REDACTED if key.casefold() in _SENSITIVE_KEYS else _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def export_tick_history(
    store: TickHistoryStore,
    output_dir: str,
    *,
    now: datetime | None = None,
) -> str:
    """Write all currently retained ticks to a timestamped file.

    Raises:
        OSError: If the output directory or dump file cannot be written.
        TypeError: If a trace cannot be represented by the formatter.
    """

    exported_at = (now or datetime.now(UTC)).astimezone(UTC)
    filename = f"tick-history-{exported_at.strftime('%Y%m%dT%H%M%S.%fZ')}.json"
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(
        TickHistoryJsonFormatter.format(store.read_window()),
        encoding="utf-8",
        newline="\n",
    )
    return str(path)
