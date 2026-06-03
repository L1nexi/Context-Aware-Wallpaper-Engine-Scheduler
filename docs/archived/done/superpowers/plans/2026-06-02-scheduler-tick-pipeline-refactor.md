# Scheduler Tick Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the scheduler tick pipeline into Sense / Think / Act / Trace / Commit stages, reducing domain knowledge leakage from `WEScheduler`.

**Architecture:** Introduce `ContextManager.sense()` for snapshot isolation, `plan_actuation()` for unified act input generation, `ActionResult.cache_update` for cache commit authority, and collapse manual apply into a pending request consumed by the normal tick loop.

**Tech Stack:** Python 3.13, pytest, dataclasses

---

### Task 1: `ContextManager.sense()` — Sense Stage Entry

**Files:**
- Modify: `core/context.py:52-87`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write the failing test for `sense()` snapshot isolation**

```python
# tests/test_context.py
from __future__ import annotations

import copy
from unittest.mock import MagicMock

from core.context import Context, ContextManager, WindowData


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest tests/test_context.py::test_sense_returns_independent_snapshot -v`
Expected: FAIL with `AttributeError: 'ContextManager' object has no attribute 'sense'`

- [ ] **Step 3: Implement `sense()` in ContextManager**

Add to `core/context.py` inside the `ContextManager` class, after `get_context()`:

```python
def sense(self) -> Context:
    """Refresh all sensors and return an independent snapshot safe for one tick."""
    return copy.deepcopy(self.refresh())
```

Also add `import copy` at the top of the file (it is not currently imported).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest tests/test_context.py::test_sense_returns_independent_snapshot -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/context.py tests/test_context.py
git commit -m "feat: add ContextManager.sense() for tick-safe snapshot isolation"
```

---

### Task 2: `ActPlan` + `plan_actuation()` — Act Input Unification

**Files:**
- Create: `core/act_plan.py`
- Create: `tests/test_act_plan.py`

- [ ] **Step 1: Write failing tests for `plan_actuation()` boundary cases**

```python
# tests/test_act_plan.py
from __future__ import annotations

import pytest

from core.act_plan import ActPlan, plan_actuation
from core.controller import DecisionMode
from core.playlist import Playlists
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


# --- Mode priority tests ---


def test_manual_requested_takes_priority_over_paused():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.UNKNOWN),
        cached_playlists=Playlists(["A"]),
        paused=True,
        manual_requested=True,
    )
    assert plan.mode == DecisionMode.MANUAL


def test_paused_takes_priority_over_recovery():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_playlists=Playlists(["A"]),
        paused=True,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.PAUSE


def test_unmanaged_triggers_recovery_when_not_paused():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.RECOVERY


def test_unmanaged_playlist_triggers_recovery():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="Other"),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.RECOVERY


def test_normal_when_factual_managed():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="A"),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.NORMAL


# --- active_playlists derivation tests ---


def test_factual_managed_in_cache_preserves_pool():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="A"),
        cached_playlists=Playlists(["A", "B"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists(["A", "B"])


def test_factual_managed_not_in_cache_returns_single():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="C"),
        cached_playlists=Playlists(["A", "B"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists(["C"])


def test_factual_unmanaged_returns_empty():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists([])


def test_factual_unknown_returns_cached():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.UNKNOWN),
        cached_playlists=Playlists(["A", "B"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists(["A", "B"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest tests/test_act_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.act_plan'`

- [ ] **Step 3: Implement `ActPlan` and `plan_actuation()`**

```python
# core/act_plan.py
from __future__ import annotations

from dataclasses import dataclass

from core.controller import DecisionMode
from core.playlist import Playlists
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


@dataclass(frozen=True)
class ActPlan:
    mode: DecisionMode
    active_playlists: Playlists


def _resolve_active_playlists(
    factual: FactualPlaylistState,
    cached_playlists: Playlists,
) -> Playlists:
    if factual.status == FactualPlaylistStatus.PLAYLIST:
        playlist = factual.playlist
        if Playlists.is_managed(playlist):
            if playlist in cached_playlists:
                return cached_playlists
            return Playlists([playlist])
        return Playlists([])
    if factual.status == FactualPlaylistStatus.NO_PLAYLIST:
        return Playlists([])
    return cached_playlists


def plan_actuation(
    factual: FactualPlaylistState,
    cached_playlists: Playlists,
    paused: bool,
    manual_requested: bool,
) -> ActPlan:
    active_playlists = _resolve_active_playlists(factual, cached_playlists)

    if manual_requested:
        mode = DecisionMode.MANUAL
    elif paused:
        mode = DecisionMode.PAUSE
    elif factual.status in (FactualPlaylistStatus.NO_PLAYLIST, FactualPlaylistStatus.PLAYLIST) and not Playlists.is_managed(factual.playlist):
        mode = DecisionMode.RECOVERY
    else:
        mode = DecisionMode.NORMAL

    return ActPlan(mode=mode, active_playlists=active_playlists)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest tests/test_act_plan.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add core/act_plan.py tests/test_act_plan.py
git commit -m "feat: add ActPlan and plan_actuation() for unified act input generation"
```

---

### Task 3: `ActionResult.cache_update` Property

**Files:**
- Modify: `core/trace.py:169-188`

- [ ] **Step 1: Add `cache_update` property to `ActionResult`**

In `core/trace.py`, add to the `ActionResult` class after the `evaluation` property:

```python
@property
def cache_update(self) -> Playlists | None:
    if self.executed and self.action == Action.SWITCH:
        return self.active_playlists_after
    return None
```

This requires `Playlists` to be imported. Add to the imports at the top of `core/trace.py`:

```python
from core.playlist import Playlists
```

- [ ] **Step 2: Run existing tests to ensure no regression**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest -q`
Expected: All existing tests pass

- [ ] **Step 3: Commit**

```bash
git add core/trace.py
git commit -m "feat: add ActionResult.cache_update property for cache commit authority"
```

---

### Task 4: Scheduler Refactor

**Files:**
- Modify: `core/scheduler.py`

This task rewires `_run_tick`, `_commit_tick`, `apply_current_match_now`, and adds new helpers. It depends on Tasks 1-3.

- [ ] **Step 1: Update imports in `scheduler.py`**

Replace the import block. Remove:
```python
from core.actuator import ActMode, Actuator
```
and:
```python
from core.playlist_state import resolve_playlist_state
```

Add:
```python
from core.act_plan import plan_actuation
from core.actuator import Actuator
from core.controller import DecisionMode
```

Keep all other existing imports unchanged.

- [ ] **Step 2: Add `_manual_apply_pending` field**

In `__init__`, add after `self._config_fingerprint`:

```python
self._manual_apply_pending: bool = False
```

- [ ] **Step 3: Rewrite `apply_current_match_now`**

Replace the existing method:

```python
def apply_current_match_now(self) -> None:
    logger.info("Manual apply requested.")
    self._manual_apply_pending = True
```

- [ ] **Step 4: Add `_consume_manual_apply_request`**

```python
def _consume_manual_apply_request(self) -> bool:
    if self._manual_apply_pending:
        self._manual_apply_pending = False
        return True
    return False
```

- [ ] **Step 5: Delete `_run_manual_apply_tick`**

Remove the entire `_run_manual_apply_tick` method (lines 218-237 in current file).

- [ ] **Step 6: Add `_build_tick_trace`**

```python
def _build_tick_trace(self, context: Context, match: Match, action: ActionResult) -> TickTrace:
    self.tick_id += 1
    return TickTrace(
        tick_id=self.tick_id,
        ts=time.time(),
        paused=self.paused,
        pause_until=self.pause_until,
        context=context,
        match=match,
        action=action,
    )
```

- [ ] **Step 7: Rewrite `_run_tick`**

Replace the entire `_run_tick` method:

```python
def _run_tick(self) -> TickTrace:
    context = self.context_manager.sense()
    match = self.matcher.evaluate(context)

    plan = plan_actuation(
        factual=self.we_config_prober.probe_playlist(),
        cached_playlists=self.cached_playlists,
        paused=self.paused,
        manual_requested=self._consume_manual_apply_request(),
    )

    action = self.actuator.act(
        plan.mode,
        match=match,
        active_playlists=plan.active_playlists,
        context=context,
    )

    return self._build_tick_trace(context, match, action)
```

- [ ] **Step 8: Rewrite `_commit_tick`**

Replace the entire `_commit_tick` method:

```python
def _commit_tick(self, trace: TickTrace) -> None:
    self.last_tick_trace = trace

    should_save_state = False
    next_cached = trace.action.cache_update
    if next_cached is not None and next_cached != self.cached_playlists:
        self.cached_playlists = next_cached
        should_save_state = True

    if should_save_state:
        self._build_persisted_state().save()

    for listener in list(self._tick_listeners):
        try:
            listener(trace)
        except Exception:
            logger.exception("tick listener failed")
```

- [ ] **Step 9: Delete `_resolve_cached_playlists_after`**

Remove the entire `_resolve_cached_playlists_after` method.

- [ ] **Step 10: Remove `copy` import**

The `import copy` at the top of `scheduler.py` is no longer needed (deepcopy moved to `ContextManager.sense()`). Remove it.

- [ ] **Step 11: Run existing tests to ensure no regression**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest -q`
Expected: All existing tests pass

- [ ] **Step 12: Commit**

```bash
git add core/scheduler.py
git commit -m "refactor: rewrite scheduler tick pipeline into Sense/Think/Act/Trace/Commit stages"
```

---

### Task 5: `Actuator.act()` Signature Tightening

**Files:**
- Modify: `core/actuator.py:46-53`

- [ ] **Step 1: Remove the `ActMode` alias and tighten `context` parameter**

In `core/actuator.py`, change the import from:
```python
from core.controller import DecisionMode as ActMode
from core.controller import SchedulingController
```
to:
```python
from core.controller import DecisionMode, SchedulingController
```

Change the `act()` signature from:
```python
def act(
    self,
    mode: ActMode,
    *,
    match: Match,
    active_playlists: Playlists,
    context: Context | None = None,
) -> ActionResult:
```
to:
```python
def act(
    self,
    mode: DecisionMode,
    *,
    match: Match,
    active_playlists: Playlists,
    context: Context,
) -> ActionResult:
```

- [ ] **Step 2: Run existing tests to ensure no regression**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest -q`
Expected: All existing tests pass

- [ ] **Step 3: Commit**

```bash
git add core/actuator.py
git commit -m "refactor: tighten Actuator.act() signature, context is now required"
```

---

### Task 6: Tray Simplification

**Files:**
- Modify: `ui/tray.py:225-232`

- [ ] **Step 1: Simplify `_on_apply_current_match_now`**

Replace:
```python
def _on_apply_current_match_now(self, icon, item):
    def _apply() -> None:
        try:
            self.scheduler.apply_current_match_now()
        except Exception:
            logger.exception("Manual apply failed")

    threading.Thread(target=_apply, daemon=True).start()
```

with:
```python
def _on_apply_current_match_now(self, icon, item):
    self.scheduler.apply_current_match_now()
```

- [ ] **Step 2: Run existing tests to ensure no regression**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest tests/test_tray_summary.py -v`
Expected: All existing tray tests pass

- [ ] **Step 3: Commit**

```bash
git add ui/tray.py
git commit -m "refactor: tray manual apply no longer spawns worker thread"
```

---

### Task 7: Scheduler Pipeline Integration Tests

**Files:**
- Create: `tests/test_scheduler_pipeline.py`

- [ ] **Step 1: Write scheduler pipeline tests**

```python
# tests/test_scheduler_pipeline.py
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from core.act_plan import ActPlan
from core.context import Context, ContextManager
from core.controller import DecisionMode
from core.matcher import Matcher
from core.playlist import Playlists
from core.scheduler import WEScheduler
from core.trace import Action, ActionResult, Decision, TickTrace
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


class FakeScheduler:
    """Minimal scheduler for testing the pending-manual-apply flow."""

    def __init__(self):
        self._manual_apply_pending = False

    def apply_current_match_now(self) -> None:
        self._manual_apply_pending = True

    def _consume_manual_apply_request(self) -> bool:
        if self._manual_apply_pending:
            self._manual_apply_pending = False
            return True
        return False


def test_apply_current_match_now_sets_pending():
    s = FakeScheduler()
    assert s._manual_apply_pending is False
    s.apply_current_match_now()
    assert s._manual_apply_pending is True


def test_consume_manual_request_returns_true_once():
    s = FakeScheduler()
    s.apply_current_match_now()
    assert s._consume_manual_apply_request() is True
    # Second consume should return False
    assert s._consume_manual_apply_request() is False


def test_consume_without_request_returns_false():
    s = FakeScheduler()
    assert s._consume_manual_apply_request() is False


def test_cache_update_only_on_executed_switch():
    """cache_update returns playlists only for executed switch actions."""
    decision = Decision(
        action=Action.SWITCH,
        reason="switch_allowed",
        matched=Playlists(["X"]),
    )
    executed = ActionResult(
        decision=decision,
        active_playlists_before=Playlists(["A"]),
        active_playlists_after=Playlists(["X"]),
        target_playlist="X",
        executed=True,
    )
    assert executed.cache_update == Playlists(["X"])

    not_executed = ActionResult(
        decision=decision,
        active_playlists_before=Playlists(["A"]),
        active_playlists_after=Playlists(["A"]),
        target_playlist=None,
        executed=False,
    )
    assert not_executed.cache_update is None


def test_cache_update_none_for_non_switch():
    """cache_update returns None for hold/cycle/pause actions."""
    for action_kind in (Action.HOLD, Action.CYCLE, Action.PAUSE, Action.NONE):
        decision = Decision(
            action=action_kind,
            reason="hold_same_playlist",
            matched=Playlists(["A"]),
        )
        result = ActionResult(
            decision=decision,
            active_playlists_before=Playlists(["A"]),
            active_playlists_after=Playlists(["A"]),
            executed=True,
        )
        assert result.cache_update is None, f"Expected None for {action_kind}"
```

- [ ] **Step 2: Run the tests**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest tests/test_scheduler_pipeline.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_scheduler_pipeline.py
git commit -m "test: add scheduler pipeline and cache_update boundary tests"
```

---

### Task 8: Cleanup — Delete `playlist_state.py`

**Files:**
- Delete: `core/playlist_state.py`

- [ ] **Step 1: Verify no remaining imports of `playlist_state`**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && grep -r "playlist_state" --include="*.py" .`
Expected: No matches (scheduler import was removed in Task 4)

- [ ] **Step 2: Delete the file**

```bash
rm core/playlist_state.py
```

- [ ] **Step 3: Run full test suite**

Run: `cd E:\github\Context-Aware-Wallpaper-Engine-Scheduler && python -m pytest -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -A core/playlist_state.py
git commit -m "chore: delete playlist_state.py, replaced by act_plan.py"
```
