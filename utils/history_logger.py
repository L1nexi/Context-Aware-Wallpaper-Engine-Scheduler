"""
Thread-safe append-only event log with monthly rotation.

write() is called from multiple threads (scheduler, tray, main) —
all internal state is guarded by a single threading.Lock.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


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
        with self._lock:
            return self._event_id

    def write(self, event_type: str, data: dict) -> int:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {"ts": ts, "type": event_type, "data": data}
        line = json.dumps(record, ensure_ascii=False) + "\n"

        with self._lock:
            self._event_id += 1
            self._ensure_file()
            self._append(line)
            return self._event_id

    def read(
        self,
        limit: int = 100,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
    ) -> dict:
        if from_ts is None and to_ts is None:
            from_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        events: list[dict] = []
        # Collect events from relevant month files
        months = self._months_in_range(from_ts, to_ts)
        for month_key in reversed(months):
            filepath = self._filepath_for(month_key)
            batch = self._read_file(filepath, from_ts, to_ts)
            events.extend(batch)

        events.sort(key=lambda e: e["ts"], reverse=True)
        if limit > 0:
            events = events[:limit]

        seed = self._find_seed(from_ts, months) if from_ts else None
        segments = self._build_segments(seed, list(reversed(events)), from_ts, to_ts)

        return {"segments": segments, "events": events}

    # ── File management ─────────────────────────────────────────────

    def _ensure_file(self) -> None:
        month_key = datetime.now().strftime("%Y-%m")
        if month_key != self._current_month:
            self._current_month = month_key
            self._filepath = self._filepath_for(month_key)

    def _filepath_for(self, month_key: str) -> str:
        return os.path.join(self._data_dir, f"history-{month_key}.jsonl")

    def _append(self, line: str) -> None:
        try:
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass  # silently drop — log infrastructure may not be ready

    # ── Reading helpers ─────────────────────────────────────────────

    def _months_in_range(
        self, from_ts: Optional[str], to_ts: Optional[str]
    ) -> List[str]:
        """Return sorted list of month keys that could contain events in range."""
        months: set[str] = set()
        if from_ts:
            months.add(self._month_key_from_ts(from_ts))
        if to_ts:
            months.add(self._month_key_from_ts(to_ts))
        months.add(datetime.now().strftime("%Y-%m"))
        # Always include current month
        return sorted(months)

    @staticmethod
    def _month_key_from_ts(ts: str) -> str:
        # ts is ISO 8601 like "2026-04-28T00:28:26+08:00" or "2026-04-28T00:28:26Z"
        return ts[:7]

    @staticmethod
    def _parse_ts(ts: str) -> datetime:
        """Parse ISO 8601 timestamp to datetime. Handles Z and +HH:MM offsets."""
        ts = ts.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            # Fallback for older Python
            if "+" in ts or ts.endswith("Z"):
                return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")

    def _read_file(
        self, filepath: str, from_ts: Optional[str], to_ts: Optional[str]
    ) -> list[dict]:
        events: list[dict] = []
        if not os.path.exists(filepath):
            return events
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = record.get("ts", "")
                    if from_ts and ts < from_ts:
                        continue
                    if to_ts and ts > to_ts:
                        continue
                    events.append(record)
        except Exception:
            pass
        return events

    def _find_seed(
        self, from_ts: str, months: List[str]
    ) -> Optional[dict]:
        """Find the most recent event before from_ts."""
        best: Optional[dict] = None
        best_ts: str = ""
        for month_key in months:
            filepath = self._filepath_for(month_key)
            if not os.path.exists(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts = record.get("ts", "")
                        if ts < from_ts and ts > best_ts:
                            best_ts = ts
                            best = record
            except Exception:
                pass
        return best

    # ── Segment building ────────────────────────────────────────────

    def _build_segments(
        self,
        seed: Optional[dict],
        events: list[dict],
        from_ts: Optional[str],
        to_ts: Optional[str],
    ) -> list[dict]:
        """Compute continuous timeline segments from events.

        Events must be sorted oldest-first.
        """
        # Determine initial state from seed
        current_playlist: Optional[str] = None
        current_type: Optional[str] = None  # None=active, "pause", "dead"

        if seed is not None:
            stype = seed["type"]
            if stype == "start":
                current_playlist = None  # started but no playlist yet
                current_type = None
            elif stype == "stop":
                current_playlist = None
                current_type = "dead"
            elif stype == "pause":
                current_playlist = self._active_playlist_before(seed, events)
                current_type = "pause"
            elif stype == "resume":
                current_playlist = self._active_playlist_before(seed, events)
                current_type = None
            elif stype == "playlist_switch":
                current_playlist = seed["data"].get("playlist_to", "")
                current_type = None
            elif stype == "wallpaper_cycle":
                current_playlist = seed["data"].get("playlist", "")
                current_type = None

        # If no seed and no events, return empty
        if seed is None and not events:
            return []

        segment_start = from_ts or (events[0] if events else seed)["ts"]
        segments: list[dict] = []

        def _push_segment(end_ts: str) -> None:
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
            edata = evt.get("data", {})

            if etype == "playlist_switch":
                if ets > segment_start:
                    _push_segment(ets)
                segment_start = ets
                current_playlist = edata.get("playlist_to", "")
                current_type = None
            elif etype == "wallpaper_cycle":
                # No state change — update playlist if not yet known
                if current_playlist is None:
                    current_playlist = edata.get("playlist", "")
            elif etype == "pause":
                if ets > segment_start:
                    _push_segment(ets)
                segment_start = ets
                current_type = "pause"
            elif etype == "resume":
                if ets > segment_start:
                    _push_segment(ets)
                segment_start = ets
                current_type = None
            elif etype == "start":
                if ets > segment_start:
                    _push_segment(ets)
                segment_start = ets
                current_type = None
                current_playlist = None
            elif etype == "stop":
                if ets > segment_start:
                    _push_segment(ets)
                segment_start = ets
                current_type = "dead"
                current_playlist = None

        # Final segment to end of window
        end_ts = to_ts or datetime.now(timezone.utc).isoformat()
        _push_segment(end_ts)

        return segments

    @staticmethod
    def _active_playlist_before(event: dict, events: list[dict]) -> Optional[str]:
        """Walk backwards from the seed/event to find the active playlist."""
        # Search in events first (oldest-first), then fallback to seed
        for e in reversed(events):
            if e["ts"] >= event["ts"]:
                continue
            if e["type"] == "playlist_switch":
                return e["data"].get("playlist_to", "")
            if e["type"] == "wallpaper_cycle":
                return e["data"].get("playlist", "")
        return None
