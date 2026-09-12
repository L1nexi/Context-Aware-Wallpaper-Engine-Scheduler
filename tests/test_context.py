from __future__ import annotations

from core.models.context import ContextManager, WindowData
from core.sensors import Sensor


class SequenceWindowSensor(Sensor):
    key = "window"

    def __init__(self) -> None:
        self._titles = iter(("before", "after"))

    def collect(self) -> WindowData:
        return WindowData(title=next(self._titles), process="proc")

    @classmethod
    def create(cls, _config):
        return cls()


def test_sense_returns_independent_snapshot():
    """Mutating the live context after sense() must not affect the snapshot."""
    cm = ContextManager()
    cm.register_sensor(SequenceWindowSensor())

    snapshot = cm.sense()
    assert snapshot.window.title == "before"

    cm.refresh()
    assert snapshot.window.title == "before"
