from __future__ import annotations

import pytest

from core.playlist import PlaylistInfo, Playlists
from utils.runtime_config import PlaylistConfig


@pytest.fixture(autouse=True)
def _reset_registry():
    """Ensure ClassVar is clean before each test."""
    Playlists._configs = {}
    yield
    Playlists._configs = {}


class TestPlaylistInfo:
    def test_frozen(self):
        info = PlaylistInfo(display="Focus", color="#2563EB", item_count=10)
        with pytest.raises(AttributeError):
            info.display = "Other"  # type: ignore[misc]


class TestPlaylistsConfigure:
    def test_configure_builds_registry(self):
        configs = {
            "focus": PlaylistConfig(display="Focus", color="#2563EB", tags={"work": 1.0}, item_count=10),
            "chill": PlaylistConfig(display="", color="#0891B2", tags={"relax": 0.8}, item_count=5),
        }
        Playlists.configure(configs)
        assert "focus" in Playlists._configs
        assert "chill" in Playlists._configs
        assert Playlists._configs["focus"].display == "Focus"
        assert Playlists._configs["chill"].display == "chill"  # fallback to name
        assert Playlists._configs["focus"].item_count == 10

    def test_configure_excludes_tags(self):
        configs = {"a": PlaylistConfig(display="A", color="#2563EB", tags={"x": 1.0})}
        Playlists.configure(configs)
        info = Playlists._configs["a"]
        assert not hasattr(info, "tags")


class TestPlaylistsInstance:
    @pytest.fixture(autouse=True)
    def _setup(self):
        Playlists._configs = {
            "a": PlaylistInfo(display="Alpha", color="#2563EB", item_count=10),
            "b": PlaylistInfo(display="Beta", color="#0891B2", item_count=5),
            "c": PlaylistInfo(display="Gamma", color="#059669", item_count=0),
        }

    def test_names(self):
        p = Playlists(["b", "a"])
        assert p.names() == ["b", "a"]

    def test_displays(self):
        p = Playlists(["a", "b"])
        assert p.displays() == {"a": "Alpha", "b": "Beta"}

    def test_colors(self):
        p = Playlists(["a"])
        assert p.colors() == {"a": "#2563EB"}

    def test_item_counts(self):
        p = Playlists(["a", "c"])
        assert p.item_counts() == {"a": 10, "c": 0}

    def test_bool_reflects_non_empty_names(self):
        assert bool(Playlists(["a"])) is True
        assert bool(Playlists()) is False

    def test_managed(self):
        p = Playlists.managed()
        assert set(p.names()) == {"a", "b", "c"}

    def test_is_managed(self):
        assert Playlists.is_managed("a") is True
        assert Playlists.is_managed("unknown") is False

    def test_select_target_ignores_zero_count(self):
        """select_target works even with item_count=0 (uses raw count as weight)."""
        p = Playlists(["c"])
        assert p.select_target() == "c"

    def test_select_target_treats_zero_count_as_unknown(self, monkeypatch):
        captured = {}

        def fake_choices(names, weights=None, k=1):
            captured["names"] = names
            captured["weights"] = weights
            captured["k"] = k
            return ["a"]

        monkeypatch.setattr("core.playlist.random.choices", fake_choices)

        Playlists(["a", "c"]).select_target()

        assert captured == {"names": ["a", "c"], "weights": [10, 1], "k": 1}

    def test_select_target_weighted(self):
        """With enough runs, higher item_count should be selected more often."""
        p = Playlists(["a", "b"])
        results = [p.select_target() for _ in range(1000)]
        a_count = results.count("a")
        # a has item_count=10, b has 5, so a should be ~2x more frequent
        assert a_count > 600  # generous margin

    def test_equality(self):
        assert Playlists(["a", "b"]) == Playlists(["a", "b"])
        assert Playlists(["a", "b"]) == Playlists(["b", "a"])

    def test_equality_not_playlists(self):
        assert Playlists(["a"]).__eq__("not_playlists") is NotImplemented
