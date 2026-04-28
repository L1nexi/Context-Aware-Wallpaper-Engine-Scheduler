"""
Thread-safe append-only event log with monthly rotation.

Public
------
write(type, data)  — append an event, return its incrementing id.
read(limit, from, to) — return {"segments": [...], "events": [...]}
                         for the dashboard History tab.

Concurrency
-----------
write() is called from scheduler thread, tray thread, and main thread.
All shared state (_event_id, _current_month, _filepath) is guarded by
a single ``threading.Lock``.

Timestamp convention
--------------------
All timestamps are UTC with +00:00 suffix, e.g.
"2026-04-28T12:34:56+00:00".  ISO 8601 strings in this format are
lexicographically ordered, so ``ts < from_ts`` works as a string
comparison and avoids datetime-parse overhead during file scans.

Event format (tagged union)
---------------------------
{"ts": "<ISO 8601>", "type": "...", "data": {...}}

See SPEC.md §1.1 for the per-type data schemas.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger("WEScheduler.History")


# Events that carry playlist affinity — used to resolve the active
# playlist when the primary seed is a pause/resume/start event.
_PLAYLIST_EVENTS = frozenset({"playlist_switch", "wallpaper_cycle"})


class HistoryLogger:
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._event_id: int = 0
        self._current_month: str = ""
        self._filepath: str = ""

    # ── Public API ──────────────────────────────────────────────────

    @property
    def last_event_id(self) -> int:
        """Monotonically increasing counter, updated on every write().

        Read by the scheduler tick to populate TickState.last_event_id,
        which the frontend watches for auto-refresh.
        """
        with self._lock:
            return self._event_id

    def write(self, event_type: str, data: dict) -> int:
        """Append one event.  Thread-safe.  Returns the new event id."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
                logger.warning("Failed to write history event", exc_info=True)
            return self._event_id

    def read(
        self,
        limit: int = 100,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
    ) -> dict:
        """Return {"segments": [...], "events": [...]} for a time window.

        When *from_ts* and *to_ts* are both None, defaults to the last hour.
        Segments are continuous time blocks computed by replaying events,
        so the frontend Gantt chart receives ready-to-render data.
        """
        if from_ts is None and to_ts is None:
            from_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        all_events, best_seed, best_pl_seed = self._collect_events(from_ts, to_ts)

        all_events.sort(key=lambda e: e["ts"], reverse=True)

        # Build segments from the full event list (oldest-first), then
        # apply the limit only to the returned event array so the Gantt
        # chart is always correct regardless of how many events exist.
        segments = self._build_segments(
            best_seed, best_pl_seed, list(reversed(all_events)), from_ts, to_ts,
        )

        if limit > 0:
            returned_events = all_events[:limit]
        else:
            returned_events = all_events

        return {"segments": segments, "events": returned_events}

    # ── File helpers ────────────────────────────────────────────────

    def _ensure_file(self) -> None:
        """Switch to a new month file when the calendar month changes."""
        month_key = datetime.now().strftime("%Y-%m")
        if month_key != self._current_month:
            self._current_month = month_key
            self._filepath = self._filepath_for(month_key)

    def _filepath_for(self, month_key: str) -> str:
        return os.path.join(self._data_dir, f"history-{month_key}.jsonl")

    # ── Event collection ────────────────────────────────────────────

    def _months_in_range(
        self, from_ts: Optional[str], to_ts: Optional[str]
    ) -> List[str]:
        """Sorted list of every month key that could intersect [from_ts, to_ts].

        Always includes the current month so brand-new files aren't missed.
        """
        months: set[str] = set()
        months.add(datetime.now().strftime("%Y-%m"))
        if from_ts:
            months.add(self._month_key_from_ts(from_ts))
        if to_ts:
            to_month = self._month_key_from_ts(to_ts)
            months.add(to_month)
            if from_ts:
                from_month = self._month_key_from_ts(from_ts)
                y, m = int(from_month[:4]), int(from_month[5:])
                key = f"{y:04d}-{m:02d}"
                while key < to_month:
                    m += 1
                    if m > 12:
                        m = 1
                        y += 1
                    key = f"{y:04d}-{m:02d}"
                    months.add(key)
        return sorted(months)

    @staticmethod
    def _month_key_from_ts(ts: str) -> str:
        """Extract 'YYYY-MM' from an ISO 8601 timestamp string."""
        return ts[:7]

    def _collect_events(
        self, from_ts: Optional[str], to_ts: Optional[str]
    ) -> tuple[list[dict], Optional[dict], Optional[dict]]:
        """Scan relevant month files once each.

        Returns:
            events      — records whose ts falls in [from_ts, to_ts].
            seed        — the most recent record *before* from_ts (any type).
            pl_seed     — the most recent switch/cycle *before* from_ts;
                          used to know which playlist was active when the
                          seed is a pause/resume outside the window.
        """
        events: list[dict] = []
        best_seed: Optional[dict] = None
        best_seed_ts: str = ""
        best_pl_seed: Optional[dict] = None
        best_pl_ts: str = ""

        months = self._months_in_range(from_ts, to_ts)
        for month_key in reversed(months):
            filepath = self._filepath_for(month_key)
            if not os.path.exists(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        record = self._parse_line(line)
                        if record is None:
                            continue
                        ts = record["ts"]

                        # Before the window — track as potential seeds
                        if from_ts and ts < from_ts:
                            if ts >= best_seed_ts:
                                best_seed_ts = ts
                                best_seed = record
                            if record["type"] in _PLAYLIST_EVENTS and ts >= best_pl_ts:
                                best_pl_ts = ts
                                best_pl_seed = record
                        # After the window — stop (events are written chronologically)
                        elif to_ts and ts > to_ts:
                            continue
                        # Inside the window
                        else:
                            events.append(record)
            except OSError:
                logger.warning("Failed to read history file %s", filepath, exc_info=True)

        return events, best_seed, best_pl_seed

    @staticmethod
    def _parse_line(line: str) -> Optional[dict]:
        """Parse one JSONL line.  Returns None for blank or corrupt lines."""
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    # ── Segment builder ─────────────────────────────────────────────

    # How each seed-event type determines the state at the start of the
    # query window: (where_to_find_playlist, initial_type).
    #
    # "self"   — the seed event itself carries the playlist.
    # "pl_seed" — look at *playlist_seed* (the last switch/cycle before the window).
    # ""       — no playlist known yet.
    _SEED_PLAYLIST_SOURCE: dict[str, str] = {
        "playlist_switch": "self",
        "wallpaper_cycle": "self",
        "pause":           "pl_seed",
        "resume":          "pl_seed",
        "start":           "",
        "stop":            "",
    }

    _SEED_INITIAL_TYPE: dict[str, Optional[str]] = {
        "playlist_switch": None,
        "wallpaper_cycle": None,
        "pause":           "pause",
        "resume":          None,
        "start":           None,
        "stop":            "dead",
    }

    def _build_segments(
        self,
        seed: Optional[dict],
        playlist_seed: Optional[dict],
        events: list[dict],          # oldest-first
        from_ts: Optional[str],
        to_ts: Optional[str],
    ) -> list[dict]:
        """Replay events to produce contiguous timeline blocks.

        Each block = {"playlist": <str|null>, "start": ts, "end": ts}
        plus an optional "type": "pause" | "dead".
        """
        current_playlist: Optional[str] = None
        current_type: Optional[str] = None            # None → "active"

        if seed is not None:
            stype = seed["type"]
            source = self._SEED_PLAYLIST_SOURCE.get(stype, "")
            current_type = self._SEED_INITIAL_TYPE.get(stype)
            if source == "self":
                current_playlist = self._playlist_from_event(seed)
            elif source == "pl_seed" and playlist_seed is not None:
                current_playlist = self._playlist_from_event(playlist_seed)

        if seed is None and not events:
            return []

        segment_start = from_ts or (events[0] if events else seed)["ts"]
        segments: list[dict] = []

        def _push(end_ts: str) -> None:
            seg: dict = {
                "playlist": current_playlist,
                "start": segment_start,
                "end": end_ts,
            }
            if current_type:
                seg["type"] = current_type
            segments.append(seg)

        for evt in events:
            ets = evt["ts"]
            etype = evt["type"]

            # State-changing events: finalise current block, then update state.
            if etype in ("playlist_switch", "pause", "resume", "start", "stop"):
                if ets > segment_start:
                    _push(ets)
                segment_start = ets

            if etype == "playlist_switch":
                current_playlist = evt["data"].get("playlist_to", "")
                current_type = None
            elif etype == "wallpaper_cycle":
                if current_playlist is None:
                    current_playlist = evt["data"].get("playlist", "")
            elif etype == "pause":
                current_type = "pause"
            elif etype == "resume":
                current_type = None
            elif etype == "start":
                current_type = None
                current_playlist = None
            elif etype == "stop":
                current_type = "dead"
                current_playlist = None

        # Final block to the end of the window (or "now" if unbounded).
        end_ts = to_ts or datetime.now(timezone.utc).isoformat()
        _push(end_ts)

        return segments

    @staticmethod
    def _playlist_from_event(event: dict) -> str:
        """Extract the active playlist name from a switch or cycle event."""
        if event["type"] == "playlist_switch":
            return event["data"].get("playlist_to", "")
        return event["data"].get("playlist", "")
