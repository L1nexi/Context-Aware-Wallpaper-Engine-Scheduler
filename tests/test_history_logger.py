from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta

import pytest

from app.history_logger import HistoryLogger
from core.models.event import EventLogger, EventType


@pytest.fixture
def logger(tmp_path):
    return HistoryLogger(str(tmp_path))


def test_write_returns_monotonically_incrementing_id(logger):
    assert logger.write(EventType.START, {"playlist": "A"}) == 1
    assert logger.write(EventType.PAUSE, {"reason": "idle"}) == 2
    assert logger.write(EventType.RESUME, {"playlist": "A"}) == 3


def test_write_persists_to_jsonl(logger):
    logger.write(EventType.START, {"playlist": "test"})

    files = os.listdir(logger._data_dir)
    assert len(files) == 1
    filepath = os.path.join(logger._data_dir, files[0])
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["type"] == EventType.START
    assert record["data"] == {"playlist": "test"}
    assert "ts" in record


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
    monkeypatch.setattr(
        "app.history_logger.datetime",
        type("FakeDT", (object,), {"now": staticmethod(fake), "timezone": tz, "timedelta": timedelta}),
    )

    logger = HistoryLogger(str(tmp_path))
    logger._ensure_file()
    assert logger._filepath == os.path.join(str(tmp_path), "history-2026-01.jsonl")

    logger._ensure_file()
    assert logger._filepath == os.path.join(str(tmp_path), "history-2026-02.jsonl")


def test_concurrent_writes_preserve_ids(logger):
    errors = []
    n_per_thread = 50
    n_threads = 4

    def writer():
        for _ in range(n_per_thread):
            try:
                logger.write(EventType.START, {})
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(n_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert logger.write(EventType.STOP, {}) == n_per_thread * n_threads + 1


def test_write_failure_rolls_back_event_id(logger, monkeypatch):
    def failing_open(*args, **kwargs):
        raise OSError("disk full")

    logger.write(EventType.START, {})
    monkeypatch.setattr("builtins.open", failing_open)

    assert logger.write(EventType.PAUSE, {}) == 1


def test_history_logger_satisfies_event_logger_protocol(tmp_path):
    logger = HistoryLogger(str(tmp_path))
    assert isinstance(logger, EventLogger)
