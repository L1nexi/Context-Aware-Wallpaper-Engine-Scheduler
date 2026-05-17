from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.tray import TrayIcon


class FakeScheduler:
    def __init__(self) -> None:
        self.paused = False
        self.cached_playlist = ""
        self.display_of = {}
        self.last_tick_trace = None
        self.on_auto_resume = None
        self.apply_current_match_now = mock.Mock()

    def get_pause_remaining(self):
        return None


def _trace(
    *,
    effective_playlist_after: str = "",
    best_playlist: str | None = None,
):
    return SimpleNamespace(
        action=SimpleNamespace(effective_playlist_after=effective_playlist_after),
        match=SimpleNamespace(best_playlist=best_playlist),
    )


def test_tray_summary_shows_active_match_and_enabled_apply(monkeypatch):
    monkeypatch.setattr("utils.i18n._current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.cached_playlist = "focus"
    scheduler.display_of = {"focus": "Focus Flow", "rain": "Rain Mood"}
    scheduler.last_tick_trace = _trace(
        effective_playlist_after="focus",
        best_playlist="rain",
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Focus Flow"
    assert tray._get_match_text() == "Match: Rain Mood"
    assert tray._get_apply_match_text() == "Apply Match: Rain Mood"
    assert tray._can_apply_match() is True


def test_tray_summary_disables_apply_when_no_match(monkeypatch):
    monkeypatch.setattr("utils.i18n._current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.cached_playlist = "focus"
    scheduler.display_of = {"focus": "Focus Flow"}
    scheduler.last_tick_trace = _trace(
        effective_playlist_after="focus",
        best_playlist=None,
    )

    tray = TrayIcon(scheduler)

    assert tray._get_match_text() == "Match: No schedulable target found"
    assert tray._get_apply_match_text() == "Apply Match: Unavailable"
    assert tray._can_apply_match() is False


def test_tray_summary_reports_outside_configured_playlists(monkeypatch):
    monkeypatch.setattr("utils.i18n._current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.last_tick_trace = _trace(
        effective_playlist_after="",
        best_playlist="rain",
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Outside configured playlists"


def test_tray_summary_falls_back_to_cached_active_playlist(monkeypatch):
    monkeypatch.setattr("utils.i18n._current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.cached_playlist = "focus"
    scheduler.display_of = {"focus": "Focus Flow"}
    scheduler.last_tick_trace = _trace(
        effective_playlist_after="",
        best_playlist="rain",
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Focus Flow"


def test_tray_summary_uses_cached_active_playlist_while_paused(monkeypatch):
    monkeypatch.setattr("utils.i18n._current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.paused = True
    scheduler.cached_playlist = "focus"
    scheduler.display_of = {"focus": "Focus Flow"}
    scheduler.last_tick_trace = _trace(
        effective_playlist_after="",
        best_playlist="rain",
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Focus Flow"


def test_tray_apply_handler_keeps_calling_manual_apply(monkeypatch):
    monkeypatch.setattr("utils.i18n._current_lang", "en")
    scheduler = FakeScheduler()
    tray = TrayIcon(scheduler)

    class ImmediateThread:
        def __init__(self, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            self._target()

    monkeypatch.setattr("ui.tray.threading.Thread", ImmediateThread)

    tray._on_apply_current_match_now(None, None)

    scheduler.apply_current_match_now.assert_called_once_with()
