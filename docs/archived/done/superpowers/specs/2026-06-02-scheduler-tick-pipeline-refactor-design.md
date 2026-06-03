# Scheduler Tick Pipeline Refactor

**Date:** 2026-06-02
**Status:** Draft
**Scope:** `core/scheduler.py`, `core/context.py`, `core/actuator.py`, `core/act_plan.py` (new), `core/playlist_state.py` (delete), `ui/tray.py`, focused tests

## Goal

Refactor the scheduler tick pipeline into clear Sense / Think / Act / Trace / Commit stages. Reduce domain knowledge leakage from `WEScheduler` into properly bounded components.

## Non-Goals

- Changing the 1-second tick loop cadence
- Modifying `SchedulingController` gate logic
- Altering `Matcher.evaluate()` behavior
- Redesigning scheduler threading or hot-reload synchronization
- Touching dashboard or tray beyond the manual apply callback wiring

## Current Problems

1. `WEScheduler` knows that `ContextManager.refresh()` returns a live object and needs `copy.deepcopy`
2. Scheduler understands WE playlist factual interpretation, cache semantics, and pause/recovery/manual priority
3. `_run_manual_apply_tick()` duplicates context refresh, match evaluate, trace construction, and commit logic
4. `_resolve_cached_playlists_after()` makes scheduler understand `Action.SWITCH` / `executed` domain details
5. `TickTrace` is constructed in two separate code paths

## Design

### 1. `ContextManager.sense()` — Sense Stage Entry

**File:** `core/context.py`

New method that refreshes all sensors and returns an independent snapshot:

```python
def sense(self) -> Context:
    return copy.deepcopy(self.refresh())
```

`refresh()` remains unchanged (returns live context reference). Scheduler only calls `sense()`.

### 2. `ActPlan` + `plan_actuation()` — Act Input Unification

**New file:** `core/act_plan.py` (replaces `core/playlist_state.py`)

```python
@dataclass(frozen=True)
class ActPlan:
    mode: DecisionMode
    active_playlists: Playlists


def plan_actuation(
    factual: FactualPlaylistState,
    cached_playlists: Playlists,
    paused: bool,
    manual_requested: bool,
) -> ActPlan:
```

**Mode priority:**

1. `manual_requested` -> `DecisionMode.MANUAL`
2. `paused` -> `DecisionMode.PAUSE`
3. factual is unmanaged/no_playlist and not paused -> `DecisionMode.RECOVERY`
4. Otherwise -> `DecisionMode.NORMAL`

**`active_playlists` derivation (all modes, same factual logic):**

- factual is managed playlist AND in cached pool -> `cached_playlists`
- factual is managed playlist BUT not in cached pool -> `Playlists([playlist])`
- factual is unmanaged / no playlist -> `Playlists([])`
- factual unknown -> `cached_playlists`

`core/playlist_state.py` is deleted. `resolve_playlist_state` logic is absorbed into `plan_actuation`.

`cached_playlists` remains scheduler-owned tick-to-tick memory. It represents the last playlist pool the scheduler successfully switched into, and is used as a fallback when factual probing is unknown. Factual managed/unmanaged observation only affects this tick's `active_playlists`; observation alone does not rewrite scheduler cache.

### 3. Manual Apply as Pending Request

**File:** `core/scheduler.py`

```python
# New field
self._manual_apply_pending: bool = False

# Tray calls this (no longer runs a tick immediately)
def apply_current_match_now(self) -> None:
    logger.info("Manual apply requested.")
    self._manual_apply_pending = True

# Consumed by _run_tick
def _consume_manual_apply_request(self) -> bool:
    if self._manual_apply_pending:
        self._manual_apply_pending = False
        return True
    return False
```

`apply_current_match_now()` remains the public UI entry point. It no longer runs a tick or returns `TickTrace`; it only records a pending manual apply request for the next scheduler tick.

`_run_manual_apply_tick()` is deleted. Tray's `_on_apply_current_match_now` no longer needs to spawn a worker thread because `apply_current_match_now()` is a fast enqueue operation. Tray should still call the public wrapper; it should not reach into scheduler private fields.

The existing `_runtime_lock` policy is not redesigned in this refactor. `_run_loop` may continue to guard hot reload, auto resume, tick execution, and commit as it does today. The pending manual flag itself does not require a dedicated worker thread; if locking remains around `_run_tick`, `_consume_manual_apply_request()` is consumed inside that existing tick critical section.

### 4. `Actuator.act()` Signature Tightening

**File:** `core/actuator.py`

```python
def act(
    self,
    mode: DecisionMode,
    *,
    match: Match,
    active_playlists: Playlists,
    context: Context,  # required
) -> ActionResult:
```

Controller internally routes by mode: NORMAL uses context for gate decisions; PAUSE/RECOVERY/MANUAL receive but do not use context.

### 5. Unified `_build_tick_trace`

**File:** `core/scheduler.py`

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

Both `_run_tick` and the deleted `_run_manual_apply_tick` paths collapse into this single construction point.

### 6. Cache Commit Simplification

**File:** `core/scheduler.py`

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

`_resolve_cached_playlists_after` is deleted. `ActionResult.cache_update` is a computed property that tells scheduler whether the tick produced a cache update:

```python
@property
def cache_update(self) -> Playlists | None:
    if self.executed and self.action == Action.SWITCH:
        return self.active_playlists_after
    return None
```

This intentionally drops factual managed observation as a cache write path. If probing sees a managed playlist, that playlist can influence the current tick through `active_playlists_before`, but cache is only updated after the scheduler successfully executes a switch. If factual probing reports unmanaged/no playlist and recovery fails, cache is preserved so future unknown probes can still fall back to the last successfully managed pool.

### 7. Final `_run_tick` Shape

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

## Testing

Test the new boundary in two layers.

`plan_actuation()` boundary cases:

- `manual_requested` takes priority over `paused`
- `paused` takes priority over recovery
- factual unmanaged -> `DecisionMode.RECOVERY` + empty playlists
- factual managed in cache -> preserves cached pool
- factual managed not in cache -> single-element playlists
- factual unknown -> cached fallback

Scheduler pipeline behavior:

- `apply_current_match_now()` only enqueues a pending manual request; the next `_run_tick()` uses `DecisionMode.MANUAL`
- pending manual apply is consumed once; the following tick returns to the normal mode selection rules
- `_commit_tick()` updates `cached_playlists` only when `trace.action.cache_update` returns a playlist pool
- factual managed observation affects `active_playlists_before` for the current tick but does not update cache by itself
- factual unmanaged/no playlist with failed recovery does not clear cache
- `ContextManager.sense()` returns an independent snapshot, so later live context mutation does not mutate the returned tick context

Happy path NORMAL controller gate logic does not need new tests beyond existing coverage.

## Files Changed

| File                     | Action                                                                                                                                                                                                                            |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/context.py`        | Add `sense()` method                                                                                                                                                                                                              |
| `core/act_plan.py`       | New file: `ActPlan`, `plan_actuation()`; depends on `DecisionMode`, not actuator-specific aliases                                                                                                                                 |
| `core/playlist_state.py` | Delete                                                                                                                                                                                                                            |
| `core/scheduler.py`      | Rewrite `_run_tick`, `_commit_tick`; add `_build_tick_trace`, `_consume_manual_apply_request`; delete `_run_manual_apply_tick`, `_resolve_cached_playlists_after`; keep `apply_current_match_now()` as enqueue wrapper            |
| `core/actuator.py`       | Tighten `act()` signature: `context: Context` required; accept `DecisionMode`                                                                                                                                                     |
| `ui/tray.py`             | `_on_apply_current_match_now` calls scheduler wrapper directly; no worker thread needed                                                                                                                                           |
| tests                    | Add focused `plan_actuation`, scheduler pipeline, commit cache, and `ContextManager.sense()` tests                                                                                                                                |
