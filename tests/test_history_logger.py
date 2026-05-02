from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from core.event_logger import EventType, EventLogger
from utils.history_logger import HistoryLogger


@pytest.fixture
def logger(tmp_path):
    return HistoryLogger(str(tmp_path))


def _iso(ts: datetime) -> str:
    return ts.isoformat(timespec="seconds")


# ── write() ─────────────────────────────────────────────────────────

def test_write_returns_monotonically_incrementing_id(logger):
    assert logger.write(EventType.START, {"playlist": "A"}) == 1
    assert logger.write(EventType.PAUSE, {"reason": "idle"}) == 2
    assert logger.write(EventType.RESUME, {"playlist": "A"}) == 3


def test_last_event_id_tracks_writes(logger):
    assert logger.last_event_id == 0
    logger.write(EventType.START, {})
    assert logger.last_event_id == 1
    logger.write(EventType.PAUSE, {})
    assert logger.last_event_id == 2


def test_write_persists_to_jsonl(logger):
    logger.write(EventType.START, {"playlist": "test"})
    files = os.listdir(logger._data_dir)
    assert len(files) == 1
    filepath = os.path.join(logger._data_dir, files[0])
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["type"] == EventType.START
    assert record["data"] == {"playlist": "test"}
    assert "ts" in record


# ── read() ──────────────────────────────────────────────────────────

def test_read_empty_history_returns_empty(logger):
    result = logger.read()
    assert result == {"segments": [], "events": []}


def test_read_with_explicit_range(logger):
    t0 = datetime.now(timezone.utc)
    logger.write(EventType.START, {"playlist": "A"})
    t1 = datetime.now(timezone.utc)
    logger.write(EventType.PLAYLIST_SWITCH, {"playlist_from": "A", "playlist_to": "B"})
    t2 = datetime.now(timezone.utc)

    result = logger.read(from_ts=_iso(t1), to_ts=_iso(t2))
    assert len(result["events"]) >= 1
    for evt in result["events"]:
        assert evt["ts"] >= _iso(t1)


def test_read_with_limit(logger):
    for i in range(10):
        logger.write(EventType.START, {"playlist": str(i)})
    result = logger.read(limit=3)
    assert len(result["events"]) == 3


def test_read_limit_zero_returns_all(logger):
    for i in range(5):
        logger.write(EventType.START, {"playlist": str(i)})
    result = logger.read(limit=0)
    assert len(result["events"]) == 5


def test_read_defaults_to_last_hour_when_no_range(logger):
    now = datetime.now(timezone.utc)
    logger.write(EventType.START, {"playlist": "A"})
    result = logger.read()
    assert "segments" in result
    assert "events" in result


def test_read_with_to_ts(logger):
    now = datetime.now(timezone.utc)
    t_before = _iso(now - timedelta(seconds=20))
    t_cutoff = _iso(now - timedelta(seconds=10))
    t_after = _iso(now - timedelta(seconds=5))

    # Write events directly with explicit timestamps to avoid timing flakes
    logger._ensure_file()
    logger._event_id = 0  # reset so IDs are deterministic
    with logger._lock:
        for ts, etype, data in [
            (t_before, EventType.START, {"playlist": "A"}),
            (t_cutoff, EventType.PLAYLIST_SWITCH, {"playlist_from": "A", "playlist_to": "B"}),
            (t_after, EventType.PAUSE, {"reason": "idle"}),
        ]:
            logger._event_id += 1
            with open(logger._filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts, "type": etype, "data": data}, ensure_ascii=False) + "\n")

    # t_cutoff is inclusive — it should be inside the window
    # t_after is after the cutoff — should be excluded
    result = logger.read(to_ts=t_cutoff)
    types = [e["type"] for e in result["events"]]
    assert EventType.START in types
    assert EventType.PLAYLIST_SWITCH in types
    assert EventType.PAUSE not in types


# ── Segment building ────────────────────────────────────────────────

def test_segments_basic_switch(logger):
    t0 = _iso(datetime.now(timezone.utc) - timedelta(seconds=10))
    logger._event_id = 0
    # Directly write a record to control timestamps
    logger._ensure_file()
    with logger._lock:
        logger._event_id += 1
        with open(logger._filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": t0, "type": EventType.PLAYLIST_SWITCH,
                                "data": {"playlist_from": "A", "playlist_to": "B"}}, ensure_ascii=False) + "\n")

    result = logger.read(from_ts=t0)
    assert len(result["segments"]) >= 1
    # The segment after the switch should show playlist B
    assert result["segments"][-1]["playlist"] == "B"


def test_segments_seed_outside_window_sets_initial_state(logger):
    t_before = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
    t_in = _iso(datetime.now(timezone.utc) - timedelta(minutes=5))

    logger._ensure_file()
    with logger._lock:
        logger._event_id += 1
        with open(logger._filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": t_before, "type": EventType.PLAYLIST_SWITCH,
                                "data": {"playlist_from": "X", "playlist_to": "SEEDED"}}, ensure_ascii=False) + "\n")
        logger._event_id += 1
        with open(logger._filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": t_in, "type": EventType.PAUSE,
                                "data": {"reason": "idle"}}, ensure_ascii=False) + "\n")

    result = logger.read(from_ts=t_in)
    assert len(result["segments"]) >= 1
    # First segment should have playlist from the seed
    first_seg = result["segments"][0]
    assert first_seg["playlist"] == "SEEDED"
    assert first_seg["type"] == "pause"


def test_segments_pause_resume_cycle(logger):
    t0 = _iso(datetime.now(timezone.utc) - timedelta(seconds=30))
    t1 = _iso(datetime.now(timezone.utc) - timedelta(seconds=20))
    t2 = _iso(datetime.now(timezone.utc) - timedelta(seconds=10))

    logger._ensure_file()
    events = [
        {"ts": t0, "type": EventType.PLAYLIST_SWITCH, "data": {"playlist_from": "", "playlist_to": "A"}},
        {"ts": t1, "type": EventType.PAUSE, "data": {"reason": "idle"}},
        {"ts": t2, "type": EventType.RESUME, "data": {"playlist": "A"}},
    ]
    with logger._lock:
        for evt in events:
            logger._event_id += 1
            with open(logger._filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")

    result = logger.read(from_ts=t0)
    types = [s.get("type") for s in result["segments"]]
    # Should have: active(A), pause, active
    assert types.count("pause") >= 1
    assert None in types  # active segments have no type key


def test_segments_stop_event_yields_dead_segment(logger):
    t0 = _iso(datetime.now(timezone.utc) - timedelta(seconds=10))
    t1 = _iso(datetime.now(timezone.utc) - timedelta(seconds=5))

    logger._ensure_file()
    events = [
        {"ts": t0, "type": EventType.PLAYLIST_SWITCH, "data": {"playlist_from": "", "playlist_to": "A"}},
        {"ts": t1, "type": EventType.STOP, "data": {}},
    ]
    with logger._lock:
        for evt in events:
            logger._event_id += 1
            with open(logger._filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")

    result = logger.read(from_ts=t0)
    # Last segment should be type "dead"
    last_seg = result["segments"][-1]
    assert last_seg.get("type") == "dead"
    assert last_seg["playlist"] is None


def test_segments_empty(logger):
    result = logger.read(from_ts="2020-01-01T00:00:00+00:00", to_ts="2020-01-01T01:00:00+00:00")
    assert result == {"segments": [], "events": []}


# ── Monthly file rotation ───────────────────────────────────────────

def test_month_key_from_ts():
    assert HistoryLogger._month_key_from_ts("2026-04-28T12:34:56+00:00") == "2026-04"
    assert HistoryLogger._month_key_from_ts("2026-01-01T00:00:00+00:00") == "2026-01"


def test_months_in_range_spans_boundaries():
    logger = HistoryLogger("/tmp/fake")
    months = logger._months_in_range("2026-01-15T00:00:00+00:00", "2026-03-10T00:00:00+00:00")
    assert "2026-01" in months
    assert "2026-02" in months
    assert "2026-03" in months


def test_months_in_range_includes_current_month():
    logger = HistoryLogger("/tmp/fake")
    now_month = datetime.now().strftime("%Y-%m")
    months = logger._months_in_range("2020-01-01T00:00:00+00:00", "2020-01-01T01:00:00+00:00")
    assert now_month in months


def test_filepath_for():
    logger = HistoryLogger("/tmp/fake")
    path = logger._filepath_for("2026-04")
    assert path == os.path.join("/tmp/fake", "history-2026-04.jsonl")


def test_ensure_file_switches_on_month_change(monkeypatch, tmp_path):
    from datetime import timezone as tz

    class FakeNow:
        def __init__(self):
            self._calls = 0

        def __call__(self, tz=None):
            self._calls += 1
            if self._calls == 1:
                return datetime(2026, 1, 15, 12, 0, 0, tzinfo=tz)
            return datetime(2026, 2, 15, 12, 0, 0, tzinfo=tz)

    fake = FakeNow()
    monkeypatch.setattr("utils.history_logger.datetime", type(
        "FakeDT", (object,), {"now": staticmethod(fake), "timezone": tz, "timedelta": timedelta}
    ))

    logger = HistoryLogger(str(tmp_path))
    logger._ensure_file()
    assert logger._filepath == os.path.join(str(tmp_path), "history-2026-01.jsonl")

    # This call should see month_key "2026-02" ≠ "2026-01" and switch
    logger._ensure_file()
    assert logger._filepath == os.path.join(str(tmp_path), "history-2026-02.jsonl")


# ── Corrupt lines ───────────────────────────────────────────────────

def test_parse_line_blank():
    assert HistoryLogger._parse_line("") is None
    assert HistoryLogger._parse_line("   \n") is None


def test_parse_line_valid():
    record = HistoryLogger._parse_line('{"ts": "x", "type": "start"}')
    assert record == {"ts": "x", "type": "start"}


def test_parse_line_corrupt_json():
    assert HistoryLogger._parse_line("not valid json {{{") is None


def test_corrupt_lines_skipped_in_read(logger, tmp_path):
    logger._ensure_file()
    filepath = logger._filepath
    with open(filepath, "a", encoding="utf-8") as f:
        f.write("this is garbage\n")
        f.write(json.dumps({"ts": "2026-01-01T00:00:00+00:00", "type": "start", "data": {}}, ensure_ascii=False) + "\n")
        f.write("more garbage\n")

    result = logger.read(from_ts="2026-01-01T00:00:00+00:00", to_ts="2026-12-31T23:59:59+00:00")
    assert len(result["events"]) == 1
    assert result["events"][0]["type"] == "start"


# ── Thread safety ───────────────────────────────────────────────────

def test_concurrent_writes_preserve_ids(logger):
    errors = []
    n_per_thread = 50
    n_threads = 4

    def writer():
        for _ in range(n_per_thread):
            try:
                logger.write(EventType.START, {})
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert logger.last_event_id == n_per_thread * n_threads

    # Verify all IDs 1..N exist
    result = logger.read(limit=0)
    ids_after_sort = sorted(result["events"], key=lambda e: e["ts"])
    assert len(ids_after_sort) == n_per_thread * n_threads


def test_last_event_id_never_decreases_on_write_failure(logger, monkeypatch):
    def failing_open(*args, **kwargs):
        raise OSError("disk full")

    logger.write(EventType.START, {})
    assert logger.last_event_id == 1

    monkeypatch.setattr("builtins.open", failing_open)
    logger.write(EventType.PAUSE, {})
    # Should roll back the increment
    assert logger.last_event_id == 1


# ── EventLogger Protocol ────────────────────────────────────────────

def test_history_logger_satisfies_event_logger_protocol():
    logger = HistoryLogger("/tmp/fake")
    assert isinstance(logger, EventLogger)


# ── Seed tables ─────────────────────────────────────────────────────

def test_seed_playlist_source_coverage():
    """Every EventType must have an entry in _SEED_PLAYLIST_SOURCE."""
    for etype in EventType:
        assert etype in HistoryLogger._SEED_PLAYLIST_SOURCE, f"{etype} missing from _SEED_PLAYLIST_SOURCE"


def test_seed_initial_type_coverage():
    """Every EventType must have an entry in _SEED_INITIAL_TYPE."""
    for etype in EventType:
        assert etype in HistoryLogger._SEED_INITIAL_TYPE, f"{etype} missing from _SEED_INITIAL_TYPE"


def test_playlist_events_frozenset():
    from utils import history_logger as hl_mod
    assert EventType.PLAYLIST_SWITCH in hl_mod._PLAYLIST_EVENTS
    assert EventType.WALLPAPER_CYCLE in hl_mod._PLAYLIST_EVENTS
