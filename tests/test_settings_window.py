from __future__ import annotations

import logging
import os
import subprocess
import sys
from types import SimpleNamespace

from ui.settings_window import SettingsWindowController
from ui.webview import focus_process_window


class FakeWindowProcess:
    def __init__(self, process_id: int, exit_code: int | None = None):
        self.pid = process_id
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


def test_show_starts_settings_window_when_none_exists():
    process = FakeWindowProcess(42)
    spawned: list[FakeWindowProcess] = []
    controller = SettingsWindowController(
        spawn=lambda: spawned.append(process) or process,
        focus=lambda _process_id: True,
    )

    controller.show()

    assert spawned == [process]


def test_show_focuses_existing_settings_window_without_starting_another():
    process = FakeWindowProcess(42)
    spawned: list[FakeWindowProcess] = []
    focused: list[int] = []
    controller = SettingsWindowController(
        spawn=lambda: spawned.append(process) or process,
        focus=lambda process_id: focused.append(process_id) or True,
    )

    controller.show()
    controller.show()

    assert spawned == [process]
    assert focused == [42]


def test_show_restarts_settings_window_after_previous_process_exits():
    first = FakeWindowProcess(42)
    replacement = FakeWindowProcess(84)
    pending = iter((first, replacement))
    spawned: list[FakeWindowProcess] = []
    focused: list[int] = []

    def spawn() -> FakeWindowProcess:
        process = next(pending)
        spawned.append(process)
        return process

    controller = SettingsWindowController(
        spawn=spawn,
        focus=lambda process_id: focused.append(process_id) or True,
    )

    controller.show()
    first.exit_code = 0
    controller.show()

    assert spawned == [first, replacement]
    assert focused == []


def test_show_reports_focus_failure_without_starting_duplicate(caplog):
    process = FakeWindowProcess(42)
    spawned: list[FakeWindowProcess] = []
    controller = SettingsWindowController(
        spawn=lambda: spawned.append(process) or process,
        focus=lambda _process_id: False,
    )

    controller.show()
    with caplog.at_level(logging.WARNING, logger="WEScheduler.SettingsWindow"):
        controller.show()

    assert spawned == [process]
    assert "Failed to focus settings window process 42" in caplog.text


def test_show_focuses_window_owned_by_settings_child_process(monkeypatch):
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    class WindowsBoundary:
        def __init__(self):
            self.foreground_windows: list[int] = []

        def EnumWindows(self, callback, _param):
            callback(101, 0)

        def GetWindowThreadProcessId(self, _window, owner_process):
            owner_process._obj.value = child.pid

        def IsWindowVisible(self, _window):
            return True

        def ShowWindow(self, _window, _command):
            return True

        def SetForegroundWindow(self, window):
            self.foreground_windows.append(window)
            return True

    boundary = WindowsBoundary()
    monkeypatch.setattr("ui.webview.ctypes.windll", SimpleNamespace(user32=boundary))
    spawned: list[FakeWindowProcess] = []
    controller = SettingsWindowController(
        spawn=lambda: spawned.append(FakeWindowProcess(os.getpid())) or spawned[-1],
        focus=focus_process_window,
    )

    try:
        controller.show()
        controller.show()
        assert len(spawned) == 1
        assert boundary.foreground_windows == [101]
    finally:
        child.terminate()
        child.wait(timeout=5)
