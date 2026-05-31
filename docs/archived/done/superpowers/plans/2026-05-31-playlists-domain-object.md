# Playlists Domain Object Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate playlist domain information leakage by introducing a `Playlists` domain object that encapsulates display, color, item_count, managed status, and target selection.

**Architecture:** Two-layer `Playlists` class — ClassVar `_configs` registry (set once via `configure()`) + instance `_names` (playlist subset). Flows through the core pipeline as a domain type; DTO/persistence boundaries keep `list[str]`.

**Tech Stack:** Python 3.13, Pydantic v2, dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-05-31-playlists-domain-object-design.md`

---

### Task 1: Create `core/playlist.py` — Playlists class

**Files:**
- Create: `core/playlist.py`
- Test: `tests/test_playlist.py`

- [ ] **Step 1: Write tests for Playlists class**

```python
# tests/test_playlist.py
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

    def test_select_target_weighted(self):
        """With enough runs, higher item_count should be selected more often."""
        p = Playlists(["a", "b"])
        results = [p.select_target() for _ in range(1000)]
        a_count = results.count("a")
        # a has item_count=10, b has 5, so a should be ~2x more frequent
        assert a_count > 600  # generous margin

    def test_equality(self):
        assert Playlists(["a", "b"]) == Playlists(["a", "b"])
        assert Playlists(["a", "b"]) != Playlists(["b", "a"])

    def test_equality_not_playlists(self):
        assert Playlists(["a"]).__eq__("not_playlists") is NotImplemented
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_playlist.py -v`
Expected: FAIL (module `core.playlist` not found)

- [ ] **Step 3: Implement Playlists class**

```python
# core/playlist.py
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import ClassVar

from utils.runtime_config import PlaylistConfig


@dataclass(frozen=True)
class PlaylistInfo:
    display: str
    color: str
    item_count: int


class Playlists:
    _configs: ClassVar[dict[str, PlaylistInfo]] = {}

    def __init__(self, names: list[str]):
        self._names = list(names)

    @classmethod
    def configure(cls, configs: dict[str, PlaylistConfig]) -> None:
        cls._configs = {
            name: PlaylistInfo(
                display=config.display or name,
                color=config.color,
                item_count=config.item_count,
            )
            for name, config in configs.items()
        }

    @classmethod
    def managed(cls) -> Playlists:
        return Playlists(list(cls._configs.keys()))

    @classmethod
    def is_managed(cls, name: str) -> bool:
        return name in cls._configs

    def names(self) -> list[str]:
        return list(self._names)

    def displays(self) -> dict[str, str]:
        return {n: self._configs[n].display for n in self._names}

    def colors(self) -> dict[str, str | None]:
        return {n: self._configs[n].color for n in self._names}

    def item_counts(self) -> dict[str, int]:
        return {n: self._configs[n].item_count for n in self._names}

    def select_target(self) -> str:
        weights = [self._configs[n].item_count for n in self._names]
        return random.choices(self._names, weights=weights, k=1)[0]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Playlists):
            return NotImplemented
        return self._names == other._names

    def __hash__(self) -> int:
        return hash(tuple(self._names))

    def __repr__(self) -> str:
        return f"Playlists({self._names!r})"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_playlist.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/playlist.py tests/test_playlist.py
git commit -m "feat: add Playlists domain object with ClassVar registry"
```

---

### Task 2: Migrate `core/playlist_state.py` — remove `managed_playlists` param

**Files:**
- Modify: `core/playlist_state.py`
- Modify: `tests/test_playlist_state.py`

- [ ] **Step 1: Update `resolve_playlist_state` to use `Playlists.is_managed()`**

Current signature:
```python
def resolve_playlist_state(
    factual: FactualPlaylistState,
    cached_playlists: list[str],
    managed_playlists: set[str],
    paused: bool,
) -> PlaylistStateResolution:
```

New implementation:
```python
# core/playlist_state.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.playlist import Playlists
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


class PlaylistRecoveryReason(StrEnum):
    NO_PLAYLIST = "recovery_no_playlist"
    UNMANAGED_PLAYLIST = "recovery_unmanaged_playlist"


@dataclass(frozen=True)
class PlaylistStateResolution:
    effective_playlists: list[str]
    recovery_needed: bool = False
    recovery_reason: PlaylistRecoveryReason | None = None


def resolve_playlist_state(
    factual: FactualPlaylistState,
    cached_playlists: list[str],
    paused: bool,
) -> PlaylistStateResolution:
    if factual.status == FactualPlaylistStatus.PLAYLIST:
        playlist = factual.playlist
        if Playlists.is_managed(playlist):
            return PlaylistStateResolution(
                effective_playlists=[playlist],
            )
        return PlaylistStateResolution(
            effective_playlists=[],
            recovery_needed=not paused,
            recovery_reason=PlaylistRecoveryReason.UNMANAGED_PLAYLIST,
        )

    if factual.status == FactualPlaylistStatus.NO_PLAYLIST:
        return PlaylistStateResolution(
            effective_playlists=[],
            recovery_needed=not paused,
            recovery_reason=PlaylistRecoveryReason.NO_PLAYLIST,
        )

    return PlaylistStateResolution(
        effective_playlists=list(cached_playlists),
    )
```

- [ ] **Step 2: Update tests to remove `managed_playlists` param and use `Playlists.configure()`**

In `tests/test_playlist_state.py`, add a fixture:
```python
from core.playlist import Playlists
from utils.runtime_config import PlaylistConfig

@pytest.fixture(autouse=True)
def _configure_playlists():
    Playlists._configs = {
        "focus": PlaylistInfo(display="Focus", color="#2563EB", item_count=10),
        "rain": PlaylistInfo(display="Rain", color="#0891B2", item_count=5),
    }
    yield
    Playlists._configs = {}
```

Remove `managed_playlists` from all `resolve_playlist_state()` calls.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_playlist_state.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add core/playlist_state.py tests/test_playlist_state.py
git commit -m "refactor: playlist_state uses Playlists.is_managed()"
```

---

### Task 3: Migrate `core/diagnostics.py` — pipeline types to Playlists

**Files:**
- Modify: `core/diagnostics.py`

- [ ] **Step 1: Update `MatchEvaluation.best_playlists` type**

Change:
```python
best_playlists: list[str]
```
To:
```python
best_playlists: list[str]  # kept as list[str] — Matcher produces list, converted to Playlists downstream
```

**Decision:** `MatchEvaluation.best_playlists` stays as `list[str]` because Matcher produces the list. Conversion to `Playlists` happens at the Controller/Actuator boundary. This avoids circular imports (Matcher → Playlists → PlaylistConfig).

Actually, looking more carefully: the spec says `MatchEvaluation.best_playlists` should be `Playlists`. But the Matcher builds the list internally. The cleanest approach is to have the Scheduler convert `match.best_playlists` (list[str]) to `Playlists(match.best_playlists)` before passing to Controller/Actuator.

**Revised approach:** Keep `MatchEvaluation.best_playlists` as `list[str]`. The Scheduler wraps it in `Playlists` before passing to Controller. `ControllerDecision.matched_playlists` and `ActuationOutcome` fields change to `Playlists`.

- [ ] **Step 2: Update `ControllerDecision.matched_playlists` type**

In `core/diagnostics.py`:
```python
from core.playlist import Playlists

@dataclass
class ControllerDecision:
    kind: ActionKind
    reason_code: ActionReasonCode
    matched_playlists: Playlists  # was list[str]
    evaluation: ControllerEvaluation | None = None
```

- [ ] **Step 3: Update `ActuationOutcome` types**

```python
@dataclass
class ActuationOutcome:
    decision: ControllerDecision
    effective_playlists_before: Playlists  # was list[str]
    effective_playlists_after: Playlists   # was list[str]
    target_playlist: str | None = None
    executed: bool = False
    ...
```

- [ ] **Step 4: Verify no import cycles**

Run: `python -c "from core.diagnostics import ControllerDecision"`
Expected: no error

- [ ] **Step 5: Run existing tests (expect failures in dependent modules)**

Run: `pytest tests/test_core_diagnostics.py -v --tb=short 2>&1 | head -30`
Expected: type errors in tests that construct `ControllerDecision`/`ActuationOutcome` with `list[str]`

- [ ] **Step 6: Commit**

```bash
git add core/diagnostics.py
git commit -m "refactor: ControllerDecision and ActuationOutcome use Playlists type"
```

---

### Task 4: Migrate `core/controller.py` — accept and return Playlists

**Files:**
- Modify: `core/controller.py`

- [ ] **Step 1: Update `decide_action` signature and internals**

```python
from core.playlist import Playlists

class SchedulingController:
    def decide_action(
        self,
        context: Context,
        match: MatchEvaluation,
        active_playlists: Playlists,  # was list[str]
    ) -> ControllerDecision:
        matched = Playlists(match.best_playlists)  # wrap list[str] from Matcher

        if not matched.names():
            return ControllerDecision(
                kind=ActionKind.HOLD if active_playlists.names() else ActionKind.NONE,
                reason_code=ActionReasonCode.NO_MATCH,
                matched_playlists=Playlists([]),
            )

        if matched != active_playlists:
            evaluation = self._evaluate_operation(context, operation="switch")
            if evaluation.allowed:
                return ControllerDecision(
                    kind=ActionKind.SWITCH,
                    reason_code=ActionReasonCode.SWITCH_ALLOWED,
                    matched_playlists=matched,
                    evaluation=evaluation,
                )
            return ControllerDecision(
                kind=ActionKind.HOLD,
                reason_code=_blocked_reason(evaluation.blocked_by, operation="switch"),
                matched_playlists=matched,
                evaluation=evaluation,
            )

        evaluation = self._evaluate_operation(context, operation="cycle")
        if evaluation.allowed:
            return ControllerDecision(
                kind=ActionKind.CYCLE,
                reason_code=ActionReasonCode.CYCLE_ALLOWED,
                matched_playlists=matched,
                evaluation=evaluation,
            )
        if evaluation.blocked_by:
            return ControllerDecision(
                kind=ActionKind.HOLD,
                reason_code=_blocked_reason(evaluation.blocked_by, operation="cycle"),
                matched_playlists=matched,
                evaluation=evaluation,
            )
        return ControllerDecision(
            kind=ActionKind.HOLD,
            reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
            matched_playlists=matched,
            evaluation=evaluation,
        )
```

- [ ] **Step 2: Update `decide_manual_action` similarly**

Same pattern: wrap `match.best_playlists` in `Playlists()`, use `.names()` for emptiness checks, return `Playlists([])` for empty.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_controller.py -v`
Expected: all PASS (after test updates if needed)

- [ ] **Step 4: Commit**

```bash
git add core/controller.py
git commit -m "refactor: Controller accepts/returns Playlists"
```

---

### Task 5: Migrate `core/actuator.py` — remove playlists, use matched.select_target()

**Files:**
- Modify: `core/actuator.py`

- [ ] **Step 1: Remove `playlists` param and `_select_target`**

```python
class Actuator:
    def __init__(
        self,
        executor: WEExecutor,
        controller: SchedulingController,
        history_logger: EventLogger,
    ):
        self.executor = executor
        self.controller = controller
        self._history: EventLogger = history_logger
```

- [ ] **Step 2: Update `_act_from_decision` to use `matched.select_target()`**

```python
def _act_from_decision(
    self,
    match: MatchEvaluation,
    effective_playlists: Playlists,
    decision: ControllerDecision,
) -> ActuationOutcome:
    matched = decision.matched_playlists
    if not matched.names():
        return ActuationOutcome(
            decision=decision,
            effective_playlists_before=effective_playlists,
            effective_playlists_after=effective_playlists,
            target_playlist=None,
            executed=False,
        )

    target = matched.select_target()
    effective_playlists_after = effective_playlists
    executed = False

    if decision.kind == ActionKind.SWITCH:
        # ... same logic, but target comes from matched.select_target()
        ...
```

- [ ] **Step 3: Update `act`, `act_manual`, `act_recovery` signatures**

Change `effective_playlists: list[str]` → `effective_playlists: Playlists` in all three methods. In `act_recovery`, construct `Playlists(matched)` from `match.best_playlists` list.

- [ ] **Step 4: Update history logging — extract list[str] for serialization**

In the history write calls, use `effective_playlists.names()` and `[target]` for the playlist_from/playlist_to fields.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_actuator.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add core/actuator.py
git commit -m "refactor: Actuator removes playlists param, uses matched.select_target()"
```

---

### Task 6: Migrate `core/matcher.py` — rename param

**Files:**
- Modify: `core/matcher.py`

- [ ] **Step 1: Rename `playlists` to `playlist_configs`**

```python
class Matcher:
    def __init__(
        self,
        playlist_configs: dict[str, PlaylistConfig],  # was: playlists
        policies: list[Policy],
        tag_specs: dict[str, TagSpec] | None = None,
    ):
        ...
        for playlist in playlist_configs.values():
            all_tags.update(playlist.tags.keys())
        ...
        self._item_counts = {name: cfg.item_count for name, cfg in playlist_configs.items()}
        ...
        for playlist_name, playlist in playlist_configs.items():
            ...
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_matcher.py -v`
Expected: all PASS (tests construct Matcher directly, update param name)

- [ ] **Step 3: Commit**

```bash
git add core/matcher.py
git commit -m "refactor: Matcher param renamed to playlist_configs"
```

---

### Task 7: Migrate `core/scheduler.py` — remove display_of/color_of/managed_playlists

**Files:**
- Modify: `core/scheduler.py`

- [ ] **Step 1: Update `_RuntimeComponents`**

```python
@dataclass(frozen=True)
class _RuntimeComponents:
    executor: WEExecutor
    context_manager: ContextManager
    matcher: Matcher
    actuator: Actuator
    playlist_configs: dict[str, PlaylistConfig]  # for Matcher + Playlists.configure()
    we_config_prober: WEConfigProber
```

Remove `display_of`, `color_of`, `managed_playlists`.

- [ ] **Step 2: Update `_build_runtime_components`**

```python
def _build_runtime_components(self, config: SchedulerConfig) -> _RuntimeComponents:
    executor = WEExecutor(config.wallpaper_engine_path)
    context_manager = ContextManager()
    for sensor_cls in SENSOR_REGISTRY:
        context_manager.register_sensor(sensor_cls.create(config))

    policies = [
        cls(getattr(config.policies, cls.config_key))
        for cls in POLICY_REGISTRY
        if getattr(config.policies, cls.config_key) is not None
    ]

    matcher = Matcher(config.playlists, policies, config.tags)
    actuator = Actuator(
        executor,
        SchedulingController(config.scheduling),
        history_logger=self.history_logger,
    )

    return _RuntimeComponents(
        executor=executor,
        context_manager=context_manager,
        matcher=matcher,
        actuator=actuator,
        playlist_configs=config.playlists,
        we_config_prober=WEConfigProber(config.wallpaper_engine_path),
    )
```

- [ ] **Step 3: Update `_install_runtime_components`**

```python
def _install_runtime_components(self, runtime: _RuntimeComponents) -> None:
    self.executor = runtime.executor
    self.context_manager = runtime.context_manager
    self.matcher = runtime.matcher
    self.actuator = runtime.actuator
    self.we_config_prober = runtime.we_config_prober
    Playlists.configure(runtime.playlist_configs)
```

Remove `self.display_of`, `self.color_of`, `self.managed_playlists`.

- [ ] **Step 4: Update `__init__` — remove managed_playlists field**

```python
class WEScheduler:
    def __init__(self, config_dir: str, history_logger: EventLogger):
        ...
        self.we_config_prober: WEConfigProber | None = None
        # Remove: self.managed_playlists: set[str] = set()
        ...
```

- [ ] **Step 5: Update `_run_tick` — use Playlists for effective_playlists**

```python
def _run_tick(self) -> SchedulerTickTrace:
    live_context = self.context_manager.refresh()
    context_snapshot = copy.deepcopy(live_context)
    match = self.matcher.evaluate(context_snapshot)
    cached_playlists_before = self.cached_playlists
    factual = self.we_config_prober.probe_playlist()
    resolution = resolve_playlist_state(
        factual,
        cached_playlists=cached_playlists_before,
        paused=self.paused,
    )

    effective_playlists = Playlists(resolution.effective_playlists)

    if self.paused:
        action = self._build_paused_actuation_outcome(match, effective_playlists)
    elif resolution.recovery_needed and resolution.recovery_reason is not None:
        action = self.actuator.act_recovery(
            match,
            effective_playlists,
            resolution.recovery_reason,
        )
    else:
        action = self.actuator.act(
            context_snapshot,
            match,
            effective_playlists,
        )

    self.tick_id += 1
    return SchedulerTickTrace(
        tick_id=self.tick_id,
        ts=time.time(),
        paused=self.paused,
        pause_until=self.pause_until,
        context=context_snapshot,
        match=match,
        action=action,
    )
```

- [ ] **Step 6: Update `_build_paused_actuation_outcome`**

```python
def _build_paused_actuation_outcome(
    self,
    match: MatchEvaluation,
    effective_playlists: Playlists,
) -> ActuationOutcome:
    return ActuationOutcome(
        decision=ControllerDecision(
            kind=ActionKind.PAUSE,
            reason_code=ActionReasonCode.SCHEDULER_PAUSED,
            matched_playlists=Playlists(match.best_playlists),
            evaluation=None,
        ),
        effective_playlists_before=effective_playlists,
        effective_playlists_after=effective_playlists,
        executed=False,
    )
```

- [ ] **Step 7: Update `_run_manual_apply_tick`**

```python
def _run_manual_apply_tick(self) -> SchedulerTickTrace:
    live_context = self.context_manager.refresh()
    context_snapshot = copy.deepcopy(live_context)
    match = self.matcher.evaluate(context_snapshot)
    action = self.actuator.act_manual(match, Playlists(self.cached_playlists))
    ...
```

- [ ] **Step 8: Update `_resolve_cached_playlists_after` — Playlists → list[str]**

```python
def _resolve_cached_playlists_after(self, action: ActuationOutcome) -> list[str]:
    if action.kind == ActionKind.SWITCH and action.executed:
        return action.effective_playlists_after.names()
    if action.effective_playlists_before.names():
        return action.effective_playlists_before.names()
    return list(self.cached_playlists)
```

- [ ] **Step 9: Update `_update_status` — use Playlists.managed()**

```python
def _update_status(self, trace: SchedulerTickTrace) -> None:
    ...
    best_playlists = trace.match.best_playlists
    displays = Playlists.managed().displays()

    if best_playlists:
        primary = displays.get(best_playlists[0], best_playlists[0])
        label = f"{primary}(+{len(best_playlists) - 1})" if len(best_playlists) > 1 else primary
    else:
        label = None
    ...
```

- [ ] **Step 10: Update `_hot_reload` — remove managed_playlists/display_of/color_of**

The `_hot_reload` method calls `_build_runtime_components` and `_install_runtime_components`, which are already updated. Remove any direct references to `display_of`/`color_of`/`managed_playlists`.

- [ ] **Step 11: Run full test suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 12: Commit**

```bash
git add core/scheduler.py
git commit -m "refactor: Scheduler removes display_of/color_of/managed_playlists"
```

---

### Task 8: Migrate `ui/tray.py` — use Playlists.managed()

**Files:**
- Modify: `ui/tray.py`

- [ ] **Step 1: Update `_get_active_text`**

```python
from core.playlist import Playlists

def _get_active_text(self) -> str:
    playlists = self.scheduler.cached_playlists
    if not self.scheduler.paused and self.scheduler.last_tick_trace is not None:
        effective = self.scheduler.last_tick_trace.action.effective_playlists_after
        if effective.names():
            playlists = effective.names()

    if playlists:
        displays = Playlists.managed().displays()
        primary = displays.get(playlists[0], playlists[0])
        active = f"{primary}(+{len(playlists) - 1})" if len(playlists) > 1 else primary
    else:
        active = t("tray_outside_configured_playlists")
    return t("tray_active", playlist=active)
```

- [ ] **Step 2: Update `_current_match_display`**

```python
def _current_match_display(self) -> str | None:
    trace = self.scheduler.last_tick_trace
    if trace is None:
        return None
    best_playlists = trace.match.best_playlists
    if not best_playlists:
        return None
    displays = Playlists.managed().displays()
    primary = displays.get(best_playlists[0], best_playlists[0])
    if len(best_playlists) > 1:
        return f"{primary}(+{len(best_playlists) - 1})"
    return primary
```

- [ ] **Step 3: Run type check and build**

Run: `python -m ruff check ui/tray.py`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add ui/tray.py
git commit -m "refactor: Tray uses Playlists.managed() for display names"
```

---

### Task 9: Migrate dashboard layer — remove DashboardRuntimeMetadata

**Files:**
- Modify: `ui/dashboard_analysis.py`
- Modify: `ui/dashboard.py`
- Modify: `main.py`

- [ ] **Step 1: Update `ui/dashboard_analysis.py` — remove metadata, use Playlists.managed()**

Remove `DashboardRuntimeMetadata`, `extract_runtime_metadata`, and the `metadata` parameter from all functions:

```python
from core.playlist import Playlists

def _playlist_ref_from_name(playlist: str) -> PlaylistRefDto:
    managed = Playlists.managed()
    displays = managed.displays()
    colors = managed.colors()
    return PlaylistRefDto(
        name=playlist,
        display=displays.get(playlist, playlist),
        color=colors.get(playlist),
    )

def _playlist_refs(playlists: list[str]) -> list[PlaylistRefDto]:
    return [_playlist_ref_from_name(name) for name in playlists if name]

def _playlist_ref(playlist: str | None) -> PlaylistRefDto | None:
    normalized = _playlist_or_none(playlist)
    if normalized is None:
        return None
    return _playlist_ref_from_name(normalized)

def map_tick_snapshot(trace: SchedulerTickTrace) -> TickSnapshotDto:
    matched_playlist_refs = _playlist_refs(trace.match.best_playlists)
    action_matched_playlist_refs = _playlist_refs(trace.action.decision.matched_playlists.names())
    active_playlists_after_refs = _playlist_refs(trace.action.effective_playlists_after.names())
    active_playlists_before_refs = _playlist_refs(trace.action.effective_playlists_before.names())
    # ... rest unchanged

def build_tick_snapshot(scheduler: WEScheduler, trace: SchedulerTickTrace) -> dict[str, Any]:
    snapshot = map_tick_snapshot(trace)
    return snapshot.model_dump(mode="json", by_alias=True)

def build_tick_window_response(window: AnalysisTraceWindow) -> dict[str, Any]:
    response = TickWindowResponseDto(
        live_tick_id=window.live_tick_id,
        ticks=[map_tick_snapshot(trace) for trace in window.traces],
    )
    return response.model_dump(mode="json", by_alias=True)
```

Delete `DashboardRuntimeMetadata` class and `extract_runtime_metadata` function entirely.

- [ ] **Step 2: Update `ui/dashboard.py` — remove metadata plumbing**

Remove `MetadataProvider`, `_empty_metadata`, and `metadata_provider` parameter:

```python
from ui.dashboard_analysis import (
    AnalysisStore,
    build_tick_window_response,
)

def _build_app(analysis_store: AnalysisStore) -> bottle.Bottle:
    app = bottle.Bottle()

    @app.route("/api/analysis/window")
    def api_analysis_window():
        raw_count = bottle.request.query.get("count", "900")
        try:
            count = _parse_positive_count(raw_count)
        except (TypeError, ValueError):
            bottle.response.status = 400
            bottle.response.content_type = "application/json; charset=utf-8"
            return json.dumps({"error": "invalid_count"})

        window = analysis_store.read_window(count)
        payload = build_tick_window_response(window)
        bottle.response.content_type = "application/json; charset=utf-8"
        return json.dumps(payload)

    # ... rest unchanged

class DashboardHTTPServer:
    def __init__(
        self,
        analysis_store: AnalysisStore,
        requested_port: int = 0,
    ):
        self._analysis_store = analysis_store
        self._requested_port = requested_port
        self._httpd: _ThreadingWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        os.makedirs(_resolve_static_root(), exist_ok=True)
        app = _build_app(self._analysis_store)
        # ... rest unchanged
```

- [ ] **Step 3: Update `main.py` — remove metadata_provider**

```python
# Remove: from ui.dashboard_analysis import AnalysisStore, extract_runtime_metadata
from ui.dashboard_analysis import AnalysisStore

# Change DashboardHTTPServer call:
httpd = DashboardHTTPServer(
    analysis_store,
    requested_port=dashboard_api_port,
)
```

- [ ] **Step 4: Run type check**

Run: `python -m ruff check ui/dashboard_analysis.py ui/dashboard.py main.py`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add ui/dashboard_analysis.py ui/dashboard.py main.py
git commit -m "refactor: Dashboard removes DashboardRuntimeMetadata, uses Playlists.managed()"
```

---

### Task 10: Update tests

**Files:**
- Modify: `tests/test_core_diagnostics.py`
- Modify: `tests/test_actuator.py` (if exists)
- Modify: `tests/test_tray_summary.py`
- Modify: `tests/test_dashboard_api.py`
- Modify: `tests/test_matcher.py`

- [ ] **Step 1: Update `test_core_diagnostics.py`**

Replace all `list[str]` construction for `matched_playlists`, `effective_playlists_before/after` with `Playlists(...)`.

Add fixture:
```python
from core.playlist import Playlists, PlaylistInfo

@pytest.fixture(autouse=True)
def _configure_playlists():
    Playlists._configs = {
        "focus": PlaylistInfo(display="Focus Flow", color="#F5C518", item_count=10),
        "rain": PlaylistInfo(display="Rain", color="#2563EB", item_count=5),
    }
    yield
    Playlists._configs = {}
```

Replace:
- `matched_playlists=["focus"]` → `matched_playlists=Playlists(["focus"])`
- `effective_playlists_before=["focus"]` → `effective_playlists_before=Playlists(["focus"])`
- etc.

- [ ] **Step 2: Update `test_tray_summary.py`**

Remove `scheduler.display_of` assignments. Add `Playlists.configure()` fixture.

- [ ] **Step 3: Update `test_dashboard_api.py`**

Remove `display_of`/`color_of` params from helper functions. Add `Playlists.configure()` fixture. Remove `extract_runtime_metadata` usage.

- [ ] **Step 4: Update any actuator tests**

Remove `playlists` param from `Actuator()` construction.

- [ ] **Step 5: Run full test suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "refactor: update tests for Playlists domain object"
```

---

### Task 11: Lint and final verification

- [ ] **Step 1: Run ruff**

Run: `python -m ruff check . --fix && python -m ruff format .`

- [ ] **Step 2: Run full test suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 3: Verify no stale references**

Run: `grep -rn "display_of\|color_of\|managed_playlists" core/ ui/ --include="*.py"`
Expected: no matches (except comments/docs)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: lint and cleanup for Playlists refactor"
```
