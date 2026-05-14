"""
Thread-safe append-only event log with monthly rotation.

Public
------
write(type, data)       — append an event, return its incrementing id.
read(limit, from, to)   — return {"events": [...], "has_more": bool}
aggregate(from, to, bucket) — return {"buckets": [...], "total_seconds": int}

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
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from core.event_logger import EventType

logger = logging.getLogger("WEScheduler.History")


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

        Useful for lightweight consumers that need to detect newly written
        events without scanning monthly JSONL files.
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
                self._event_id -= 1
                logger.warning("Failed to write history event", exc_info=True)
            return self._event_id

    def read(
        self,
        limit: int = 100,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
    ) -> dict:
        """Return events in [from_ts, to_ts], newest first.

        When *from_ts* and *to_ts* are both None, defaults to the last hour.
        Returns ``{"events": [...], "has_more": bool}``.

        *has_more* is True when there are more events before the oldest
        returned event — the client can pass ``to=<oldest_ts>`` to page
        further back.
        """
        with self._lock:
            if from_ts is None and to_ts is None:
                from_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")

        all_events, _, _ = self._collect_events(from_ts, to_ts)
        all_events.sort(key=lambda e: e["ts"], reverse=True)

        has_more = limit > 0 and len(all_events) > limit
        returned = all_events[:limit] if limit > 0 else all_events

        return {"events": returned, "has_more": has_more}

    # ── File helpers ────────────────────────────────────────────────

    def _ensure_file(self) -> None:
        """Switch to a new month file when the calendar month changes."""
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
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
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        record = self._parse_line(line)
                        if record is None:
                            continue
                        if "ts" not in record or "type" not in record:
                            continue
                        ts = record["ts"]

                        # Before the window — track as potential seeds
                        if from_ts and ts < from_ts:
                            if ts >= best_seed_ts:
                                best_seed_ts = ts
                                best_seed = record
                            if record["type"] in (EventType.PLAYLIST_SWITCH, EventType.WALLPAPER_CYCLE) and ts >= best_pl_ts:
                                best_pl_ts = ts
                                best_pl_seed = record
                        # After the window — remaining events are also past it
                        elif to_ts and ts > to_ts:
                            break
                        # Inside the window
                        else:
                            events.append(record)
            except FileNotFoundError:
                pass  # normal — no events written for this month yet
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

    # ── Aggregation ───────────────────────────────────────────────────

    @staticmethod
    def _parse_ts(ts: str) -> float:
        """Parse ISO 8601 UTC timestamp to Unix seconds."""
        return datetime.fromisoformat(ts).timestamp()

    @staticmethod
    def _pl_from(event: dict) -> str:
        """Extract the active playlist from a switch or cycle event."""
        if event["type"] == EventType.PLAYLIST_SWITCH:
            return event["data"].get("playlist_to", "")
        return event["data"].get("playlist", "")

    def aggregate(
        self,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        bucket_minutes: int = 60,
    ) -> dict:
        """Aggregate playlist duration ratios per time bucket.

        Replays events within the window to compute per-playlist seconds
        in each bucket.  Seed resolution (determining the initial state
        from the last event before the window) is inlined here — this
        does NOT reuse any old segment-building logic.

        Returns::

          {"buckets": [{"start": ts, "end": ts,
                        "playlists": {"Name": seconds, ...},
                        "playlists_ratio": {"Name": ratio, ...}}, ...],
           "total_seconds": int}
        """
        with self._lock:
            if from_ts is None and to_ts is None:
                to_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                from_ts = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
            elif to_ts is None:
                to_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            elif from_ts is None:
                from_ts = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")

        all_events, seed, pl_seed = self._collect_events(from_ts, to_ts)
        all_events.sort(key=lambda e: e["ts"])  # oldest first

        # ── Resolve initial state from seed ──
        current_playlist: Optional[str] = None
        # current_type not stored — we only need to know whether a playlist
        # is active.  pause/dead → current_playlist is None.

        if seed is not None:
            st = seed["type"]
            if st == EventType.PLAYLIST_SWITCH:
                current_playlist = seed["data"].get("playlist_to", "")
            elif st == EventType.WALLPAPER_CYCLE:
                current_playlist = seed["data"].get("playlist", "")
            elif st == EventType.PAUSE:
                current_playlist = None  # paused → no active playlist
            elif st == EventType.RESUME:
                if pl_seed is not None:
                    current_playlist = self._pl_from(pl_seed)
            elif st in (EventType.START, EventType.STOP):
                current_playlist = None

        f_sec = self._parse_ts(from_ts)
        t_sec = self._parse_ts(to_ts)
        bucket_seconds = bucket_minutes * 60
        first_bucket = f_sec - (f_sec % bucket_seconds)

        # ── Build bucket list with precomputed second boundaries ──
        buckets: list[dict] = []
        b_sec_list: list[tuple[float, float]] = []  # (start_sec, end_sec)
        pos = first_bucket
        while pos < t_sec:
            b_end = min(pos + bucket_seconds, t_sec)
            buckets.append({
                "start": datetime.fromtimestamp(pos, tz=timezone.utc).isoformat(
                    timespec="seconds"),
                "end": datetime.fromtimestamp(b_end, tz=timezone.utc).isoformat(
                    timespec="seconds"),
                "playlists": {},
            })
            b_sec_list.append((pos, b_end))
            pos += bucket_seconds

        # ── Walk events, tracking state and distributing durations ──
        seg_start = f_sec
        paused_playlist: Optional[str] = None
        # Preserved playlist across a pause/resume pair.  When PAUSE
        # fires, we save the current playlist here; when RESUME fires
        # we restore it, so the gap between resume and the next switch
        # is correctly attributed.

        for evt in all_events:
            ets = evt["ts"]
            etype = evt["type"]
            e_sec = self._parse_ts(ets)

            _STATE_CHANGE = (
                EventType.PLAYLIST_SWITCH, EventType.PAUSE,
                EventType.RESUME, EventType.START, EventType.STOP,
            )
            if etype in _STATE_CHANGE:
                if e_sec > seg_start and current_playlist:
                    self._fill_buckets(
                        buckets, b_sec_list, seg_start, e_sec, current_playlist,
                    )
                seg_start = e_sec

                if etype == EventType.PLAYLIST_SWITCH:
                    current_playlist = evt["data"].get("playlist_to", "")
                    paused_playlist = None
                elif etype == EventType.PAUSE:
                    paused_playlist = current_playlist
                    current_playlist = None
                elif etype == EventType.RESUME:
                    current_playlist = paused_playlist
                    paused_playlist = None
                elif etype == EventType.START:
                    current_playlist = None
                    paused_playlist = None
                elif etype == EventType.STOP:
                    current_playlist = None
                    paused_playlist = None

        # ── Final segment ──
        if t_sec > seg_start and current_playlist:
            self._fill_buckets(
                buckets, b_sec_list, seg_start, t_sec, current_playlist,
            )

        # ── Compute ratios ──
        for i, bucket in enumerate(buckets):
            b_dur = b_sec_list[i][1] - b_sec_list[i][0]
            pl = bucket["playlists"]
            bucket["playlists_ratio"] = {
                k: round(v / b_dur, 6) for k, v in pl.items()
            } if b_dur > 0 else {}

        return {"buckets": buckets, "total_seconds": int(t_sec - f_sec)}

    @staticmethod
    def _fill_buckets(
        buckets: list[dict],
        b_sec_list: list[tuple[float, float]],
        seg_start: float,
        seg_end: float,
        playlist: str,
    ) -> None:
        """Add segment duration to overlapping buckets."""
        for i, (b_start, b_end) in enumerate(b_sec_list):
            if seg_end <= b_start or seg_start >= b_end:
                continue
            overlap = min(seg_end, b_end) - max(seg_start, b_start)
            if overlap > 0:
                buckets[i]["playlists"][playlist] = (
                    buckets[i]["playlists"].get(playlist, 0.0) + overlap
                )
