from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime, timedelta

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
        with self._lock:
            return self._event_id

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

    def read(
        self,
        limit: int = 100,
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> dict:
        with self._lock:
            if from_ts is None and to_ts is None:
                from_ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds")

        all_events, _, _ = self._collect_events(from_ts, to_ts)
        all_events.sort(key=lambda e: e["ts"], reverse=True)

        has_more = limit > 0 and len(all_events) > limit
        returned = all_events[:limit] if limit > 0 else all_events

        return {"events": returned, "has_more": has_more}

    def _ensure_file(self) -> None:
        month_key = datetime.now(UTC).strftime("%Y-%m")
        if month_key != self._current_month:
            self._current_month = month_key
            self._filepath = self._filepath_for(month_key)

    def _filepath_for(self, month_key: str) -> str:
        return os.path.join(self._data_dir, f"history-{month_key}.jsonl")

    def _months_in_range(self, from_ts: str | None, to_ts: str | None) -> list[str]:
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
        return ts[:7]

    def _collect_events(self, from_ts: str | None, to_ts: str | None) -> tuple[list[dict], dict | None, dict | None]:
        events: list[dict] = []
        best_seed: dict | None = None
        best_seed_ts: str = ""
        best_pl_seed: dict | None = None
        best_pl_ts: str = ""

        months = self._months_in_range(from_ts, to_ts)
        for month_key in reversed(months):
            filepath = self._filepath_for(month_key)
            try:
                with open(filepath, encoding="utf-8") as f:
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
    def _parse_line(line: str) -> dict | None:
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _parse_ts(ts: str) -> float:
        return datetime.fromisoformat(ts).timestamp()

    @staticmethod
    def _pl_from(event: dict) -> str:
        if event["type"] == EventType.PLAYLIST_SWITCH:
            return event["data"].get("playlist_to", "")
        return event["data"].get("playlist", "")

    def aggregate(
        self,
        from_ts: str | None = None,
        to_ts: str | None = None,
        bucket_minutes: int = 60,
    ) -> dict:
        with self._lock:
            if from_ts is None and to_ts is None:
                to_ts = datetime.now(UTC).isoformat(timespec="seconds")
                from_ts = (datetime.now(UTC) - timedelta(hours=24)).isoformat(timespec="seconds")
            elif to_ts is None:
                to_ts = datetime.now(UTC).isoformat(timespec="seconds")
            elif from_ts is None:
                from_ts = (datetime.now(UTC) - timedelta(hours=24)).isoformat(timespec="seconds")

        all_events, seed, pl_seed = self._collect_events(from_ts, to_ts)
        all_events.sort(key=lambda e: e["ts"])  # oldest first

        # ── Resolve initial state from seed ──
        current_playlist: str | None = None
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
            buckets.append(
                {
                    "start": datetime.fromtimestamp(pos, tz=UTC).isoformat(timespec="seconds"),
                    "end": datetime.fromtimestamp(b_end, tz=UTC).isoformat(timespec="seconds"),
                    "playlists": {},
                }
            )
            b_sec_list.append((pos, b_end))
            pos += bucket_seconds

        # ── Walk events, tracking state and distributing durations ──
        seg_start = f_sec
        paused_playlist: str | None = None

        for evt in all_events:
            ets = evt["ts"]
            etype = evt["type"]
            e_sec = self._parse_ts(ets)

            _STATE_CHANGE = (
                EventType.PLAYLIST_SWITCH,
                EventType.PAUSE,
                EventType.RESUME,
                EventType.START,
                EventType.STOP,
            )
            if etype in _STATE_CHANGE:
                if e_sec > seg_start and current_playlist:
                    self._fill_buckets(
                        buckets,
                        b_sec_list,
                        seg_start,
                        e_sec,
                        current_playlist,
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
                buckets,
                b_sec_list,
                seg_start,
                t_sec,
                current_playlist,
            )

        # ── Compute ratios ──
        for i, bucket in enumerate(buckets):
            b_dur = b_sec_list[i][1] - b_sec_list[i][0]
            pl = bucket["playlists"]
            bucket["playlists_ratio"] = {k: round(v / b_dur, 6) for k, v in pl.items()} if b_dur > 0 else {}

        return {"buckets": buckets, "total_seconds": int(t_sec - f_sec)}

    @staticmethod
    def _fill_buckets(
        buckets: list[dict],
        b_sec_list: list[tuple[float, float]],
        seg_start: float,
        seg_end: float,
        playlist: str,
    ) -> None:
        for i, (b_start, b_end) in enumerate(b_sec_list):
            if seg_end <= b_start or seg_start >= b_end:
                continue
            overlap = min(seg_end, b_end) - max(seg_start, b_start)
            if overlap > 0:
                buckets[i]["playlists"][playlist] = buckets[i]["playlists"].get(playlist, 0.0) + overlap
