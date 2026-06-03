from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from core.models.playlist import PlaylistInfo, Playlists
from ui.tray import TrayIcon


@pytest.fixture(autouse=True)
def _configure_playlists():
    Playlists._configs = {
        "focus": PlaylistInfo(display="Focus Flow", color="#F5C518", item_count=10),
        "rain": PlaylistInfo(display="Rain Mood", color="#2563EB", item_count=5),
    }
    yield
    Playlists._configs = {}


class FakeScheduler:
    def __init__(self) -> None:
        self.state = SimpleNamespace(
            paused=False,
            cached_playlists=Playlists(),
            last_tick_trace=None,
        )
        self.on_auto_resume = None
        self.apply_current_match_now = mock.Mock()

    @property
    def paused(self) -> bool:
        return self.state.paused

    @property
    def cached_playlists(self) -> Playlists:
        return self.state.cached_playlists

    @property
    def last_tick_trace(self):
        return self.state.last_tick_trace

    def get_pause_remaining(self):
        return None


def _trace(
    *,
    active_playlists_after: list[str] | None = None,
    best_playlists: list[str] | None = None,
):
    return SimpleNamespace(
        action=SimpleNamespace(active_playlists_after=Playlists(active_playlists_after or [])),
        match=SimpleNamespace(best_playlists=Playlists(best_playlists or [])),
    )


def test_tray_summary_shows_active_match_and_enabled_apply(monkeypatch):
    monkeypatch.setattr("ui.i18n.current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.state.cached_playlists = Playlists(["focus"])
    scheduler.state.last_tick_trace = _trace(
        active_playlists_after=["focus"],
        best_playlists=["rain"],
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Focus Flow"
    assert tray._get_match_text() == "Match: Rain Mood"
    assert tray._get_apply_match_text() == "Apply Match: Rain Mood"
    assert tray._can_apply_match() is True


def test_tray_summary_disables_apply_when_no_match(monkeypatch):
    monkeypatch.setattr("ui.i18n.current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.state.cached_playlists = Playlists(["focus"])
    scheduler.state.last_tick_trace = _trace(
        active_playlists_after=["focus"],
        best_playlists=[],
    )

    tray = TrayIcon(scheduler)

    assert tray._get_match_text() == "Match: No schedulable target found"
    assert tray._get_apply_match_text() == "Apply Match: Unavailable"
    assert tray._can_apply_match() is False


def test_tray_summary_reports_outside_configured_playlists(monkeypatch):
    monkeypatch.setattr("ui.i18n.current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.state.last_tick_trace = _trace(
        active_playlists_after=[],
        best_playlists=["rain"],
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Outside configured playlists"


def test_tray_summary_falls_back_to_cached_active_playlist(monkeypatch):
    monkeypatch.setattr("ui.i18n.current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.state.cached_playlists = Playlists(["focus"])
    scheduler.state.last_tick_trace = _trace(
        active_playlists_after=[],
        best_playlists=["rain"],
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Focus Flow"


def test_tray_summary_uses_cached_active_playlist_while_paused(monkeypatch):
    monkeypatch.setattr("ui.i18n.current_lang", "en")
    scheduler = FakeScheduler()
    scheduler.state.paused = True
    scheduler.state.cached_playlists = Playlists(["focus"])
    scheduler.state.last_tick_trace = _trace(
        active_playlists_after=[],
        best_playlists=["rain"],
    )

    tray = TrayIcon(scheduler)

    assert tray._get_active_text() == "Active: Focus Flow"


def test_tray_apply_handler_keeps_calling_manual_apply(monkeypatch):
    monkeypatch.setattr("ui.i18n.current_lang", "en")
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
