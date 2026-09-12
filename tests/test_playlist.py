from __future__ import annotations

import pytest

from configurations.runtime_models import PlaylistConfig
from core.models.playlist import Playlists


@pytest.fixture(autouse=True)
def _reset_registry():
    Playlists.configure({})
    yield
    Playlists.configure({})


class TestPlaylistsConfigure:
    def test_configure_builds_registry(self):
        configs = {
            "focus": PlaylistConfig(display="Focus", color="#2563EB", tags={"work": 1.0}, item_count=10),
            "chill": PlaylistConfig(display="", color="#0891B2", tags={"relax": 0.8}, item_count=5),
        }
        Playlists.configure(configs)

        managed = Playlists.managed()
        assert managed.names() == ["focus", "chill"]
        assert managed.displays() == {"focus": "Focus", "chill": "chill"}
        assert managed.item_counts() == {"focus": 10, "chill": 5}


class TestPlaylistsInstance:
    @pytest.fixture(autouse=True)
    def _setup(self):
        Playlists.configure(
            {
                "a": PlaylistConfig(display="Alpha", color="#2563EB", item_count=10),
                "b": PlaylistConfig(display="Beta", color="#0891B2", item_count=5),
                "c": PlaylistConfig(display="Gamma", color="#059669", item_count=0),
            }
        )

    def test_names(self):
        p = Playlists(["b", "a"])
        assert p.names() == ["b", "a"]

    def test_colors(self):
        p = Playlists(["a"])
        assert p.colors() == {"a": "#2563EB"}

    def test_is_managed(self):
        assert Playlists.is_managed("a") is True
        assert Playlists.is_managed("unknown") is False

    def test_select_target_ignores_zero_count(self):
        """select_target works even with item_count=0 (uses raw count as weight)."""
        p = Playlists(["c"])
        assert p.select_target() == "c"

    def test_select_target_weighted(self):
        """With enough runs, higher item_count should be selected more often."""
        p = Playlists(["a", "b"])
        results = [p.select_target() for _ in range(10_000)]
        a_count = results.count("a")
        assert a_count > results.count("b")

    def test_equality(self):
        assert Playlists(["a", "b"]) == Playlists(["a", "b"])
        assert Playlists(["a", "b"]) == Playlists(["b", "a"])
