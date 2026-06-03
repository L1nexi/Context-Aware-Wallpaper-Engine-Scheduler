from __future__ import annotations

from unittest.mock import MagicMock

from core.models.context import ContextManager, WindowData


def test_sense_returns_independent_snapshot():
    """Mutating the live context after sense() must not affect the snapshot."""
    cm = ContextManager()
    sensor = MagicMock()
    sensor.key = "window"
    # First call: return a known value
    sensor.collect.return_value = WindowData(title="before", process="proc")
    cm.register_sensor(sensor)

    snapshot = cm.sense()
    assert snapshot.window.title == "before"

    # Mutate the live context via a subsequent refresh
    sensor.collect.return_value = WindowData(title="after", process="proc")
    cm.refresh()

    # Snapshot must still hold the old value
    assert snapshot.window.title == "before"
