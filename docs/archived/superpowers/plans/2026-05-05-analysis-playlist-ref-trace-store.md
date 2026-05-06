# Analysis Playlist Ref Trace Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor dashboard analysis so playlist presentation data is self-contained in a `PlaylistRef` DTO and `AnalysisStore` stores raw `SchedulerTickTrace` values instead of already-projected snapshots.

**Architecture:** `core` continues to emit playlist names only. `AnalysisStore` becomes a ring buffer of `SchedulerTickTrace` diagnostic facts, and `/api/analysis/window` projects those traces into public `TickSnapshot` DTOs using current runtime playlist metadata. The public analysis API uses one playlist reference shape everywhere a playlist appears.

**Tech Stack:** Python 3, Pydantic DTOs, Bottle API, pytest, Vue 3, TypeScript, Pinia, Vite.

---

## File Structure

- Modify `ui/dashboard_analysis.py`
  - Add `PlaylistRefDto`.
  - Replace flattened playlist fields in `TickSummaryDto`, `TopMatchDto`, and `ActionDecisionDto`.
  - Add trace-window read model for `AnalysisStore`.
  - Add a response builder that maps a trace window plus current `DashboardRuntimeMetadata` into `TickWindowResponseDto`.

- Modify `ui/dashboard.py`
  - Add a metadata provider dependency to `_build_app()` and `DashboardHTTPServer`.
  - Project trace windows at `/api/analysis/window` request time.

- Modify `main.py`
  - Store raw traces in `AnalysisStore`.
  - Pass `lambda: extract_runtime_metadata(scheduler)` into `DashboardHTTPServer`.

- Modify `tests/test_dashboard_api.py`
  - Update mapper assertions to the new playlist reference shape.
  - Update `AnalysisStore` tests for raw traces.
  - Add endpoint coverage proving current metadata is used during response projection.

- Modify `dashboard-v2/src/lib/dashboardAnalysis.ts`
  - Add `PlaylistRef`.
  - Replace flattened playlist fields in analysis DTO types.

- Modify `dashboard-v2/src/features/dashboard-analysis/presenters.ts`
  - Centralize playlist display formatting around `PlaylistRef | null`.

- Modify `dashboard-v2/src/features/dashboard-analysis/timeline.ts`
  - Read playlist identity and color from `PlaylistRef`.

- Modify `dashboard-v2/src/features/dashboard-analysis/ActPanel.vue`
  - Read top-match identity and color from `PlaylistRef`.

---

## Task 1: Backend DTO Regression Tests

**Files:**
- Modify: `tests/test_dashboard_api.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Import the runtime metadata DTO**

Add `DashboardRuntimeMetadata` to the existing `ui.dashboard_analysis` import in `tests/test_dashboard_api.py`:

```python
from ui.dashboard_analysis import (
    AnalysisStore,
    DashboardRuntimeMetadata,
    build_tick_snapshot,
)
```

- [ ] **Step 2: Update `test_build_tick_snapshot_maps_analysis_fields` assertions**

Replace the playlist-related assertions after `snapshot = build_tick_snapshot(scheduler, trace)` with this exact block:

```python
    assert snapshot["summary"]["tickId"] == 7
    assert snapshot["summary"]["activePlaylist"] == {
        "name": "idle",
        "display": "idle",
        "color": "#2E5F8A",
    }
    assert snapshot["summary"]["matchedPlaylist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }
    assert "activePlaylistDisplay" not in snapshot["summary"]
    assert "activePlaylistColor" not in snapshot["summary"]
    assert "matchedPlaylistDisplay" not in snapshot["summary"]
    assert "matchedPlaylistColor" not in snapshot["summary"]
    assert "enabled" not in snapshot["sense"]["weather"]
    assert snapshot["sense"]["weather"]["available"] is True
    assert snapshot["sense"]["weather"]["stale"] is True
    assert snapshot["think"]["fallbackExpansions"]["#storm"][0]["resolvedTag"] == "#rain"
    assert snapshot["think"]["policies"][0]["policyId"] == "activity"
    assert snapshot["think"]["policies"][1]["details"]["mapped"] is True
    assert snapshot["act"]["topMatches"][0]["playlist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }
    assert snapshot["act"]["topMatches"][0]["score"] == 0.91
    assert snapshot["act"]["topMatches"][1]["playlist"] == {
        "name": "rainy",
        "display": "Rainy Mood",
        "color": "#4A90D9",
    }
    assert snapshot["act"]["controller"]["evaluation"]["operation"] == "switch"
    assert snapshot["act"]["decision"]["reasonCode"] == "switch_blocked_cooldown"
    assert snapshot["act"]["decision"]["activePlaylistBefore"] == {
        "name": "idle",
        "display": "idle",
        "color": "#2E5F8A",
    }
    assert snapshot["act"]["decision"]["activePlaylistAfter"] == {
        "name": "idle",
        "display": "idle",
        "color": "#2E5F8A",
    }
    assert snapshot["act"]["decision"]["matchedPlaylist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }
```

- [ ] **Step 3: Update `test_build_tick_snapshot_maps_paused_tick` assertions**

Replace the playlist-related assertions in `test_build_tick_snapshot_maps_paused_tick` with this exact block:

```python
    assert snapshot["summary"]["actionKind"] == "pause"
    assert snapshot["summary"]["paused"] is True
    assert snapshot["summary"]["hasEvent"] is False
    assert snapshot["summary"]["activePlaylist"] == {
        "name": "focus",
        "display": "focus",
        "color": "#F5C518",
    }
    assert snapshot["summary"]["matchedPlaylist"] == {
        "name": "rainy",
        "display": "rainy",
        "color": "#4A90D9",
    }
    assert snapshot["sense"]["weather"]["available"] is False
    assert snapshot["act"]["controller"]["evaluation"] is None
    assert snapshot["act"]["decision"]["activePlaylistAfter"] == {
        "name": "focus",
        "display": "focus",
        "color": "#F5C518",
    }
    assert snapshot["act"]["decision"]["matchedPlaylist"] == {
        "name": "rainy",
        "display": "rainy",
        "color": "#4A90D9",
    }
```

- [ ] **Step 4: Add explicit unknown playlist reference coverage**

Add this test after `test_build_tick_snapshot_maps_paused_tick`:

```python
def test_build_tick_snapshot_maps_unknown_playlist_ref_with_null_color():
    scheduler = _make_scheduler()
    trace = _make_trace(
        tick_id=9,
        active_playlist_before="",
        active_playlist_after="unknown_active",
        matched_playlist="unknown_match",
        executed=False,
        action_kind=ActionKind.HOLD,
        reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
        evaluation=None,
        weather=None,
    )

    snapshot = build_tick_snapshot(scheduler, trace)

    assert snapshot["summary"]["activePlaylist"] == {
        "name": "unknown_active",
        "display": "unknown_active",
        "color": None,
    }
    assert snapshot["summary"]["matchedPlaylist"] == {
        "name": "unknown_match",
        "display": "unknown_match",
        "color": None,
    }
    assert snapshot["act"]["decision"]["activePlaylistBefore"] is None
```

- [ ] **Step 5: Run backend mapper tests and confirm they fail**

Run:

```bash
pytest -q tests/test_dashboard_api.py::test_build_tick_snapshot_maps_analysis_fields tests/test_dashboard_api.py::test_build_tick_snapshot_maps_paused_tick tests/test_dashboard_api.py::test_build_tick_snapshot_maps_unknown_playlist_ref_with_null_color
```

Expected: at least one assertion fails because the implementation still returns flattened fields such as `activePlaylistDisplay` and top matches still expose `display` and `color` beside `playlist`.

---

## Task 2: Implement `PlaylistRefDto` in the Analysis Mapper

**Files:**
- Modify: `ui/dashboard_analysis.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Add the playlist reference DTO**

In `ui/dashboard_analysis.py`, add this DTO after `ActionDecisionDto` dependencies and before `TopMatchDto`:

```python
class PlaylistRefDto(ApiDto):
    name: str
    display: str
    color: str | None
```

- [ ] **Step 2: Replace playlist fields in DTO classes**

Update these DTO classes in `ui/dashboard_analysis.py`:

```python
class ActionDecisionDto(ApiDto):
    kind: ActionKind
    reason_code: ActionReasonCode
    executed: bool
    active_playlist_before: PlaylistRefDto | None
    active_playlist_after: PlaylistRefDto | None
    matched_playlist: PlaylistRefDto | None


class TopMatchDto(ApiDto):
    playlist: PlaylistRefDto
    score: float
```

Replace the playlist portion of `TickSummaryDto` with this shape:

```python
class TickSummaryDto(ApiDto):
    tick_id: int
    ts: float
    similarity: float
    similarity_gap: float
    active_playlist: PlaylistRefDto | None
    matched_playlist: PlaylistRefDto | None
    action_kind: ActionKind
    reason_code: ActionReasonCode
    paused: bool
    executed: bool
    has_event: bool
```

- [ ] **Step 3: Replace display and color helpers with playlist reference helpers**

Remove `_playlist_display()` and `_playlist_color()` from `ui/dashboard_analysis.py`. Add these helpers after `DashboardRuntimeMetadata`:

```python
def _playlist_ref_from_name(
    playlist: str,
    metadata: DashboardRuntimeMetadata,
) -> PlaylistRefDto:
    return PlaylistRefDto(
        name=playlist,
        display=metadata.display_of.get(playlist, playlist),
        color=metadata.color_of.get(playlist),
    )


def _playlist_ref(
    playlist: str | None,
    metadata: DashboardRuntimeMetadata,
) -> PlaylistRefDto | None:
    normalized_playlist = _playlist_or_none(playlist)
    if normalized_playlist is None:
        return None
    return _playlist_ref_from_name(normalized_playlist, metadata)
```

- [ ] **Step 4: Update `map_tick_snapshot()` to build playlist references**

At the start of `map_tick_snapshot()`, keep the normalized names, then add references:

```python
    matched_playlist = _playlist_or_none(trace.match.best_playlist)
    action_matched_playlist = _playlist_or_none(trace.action.matched_playlist)
    active_playlist_after = _playlist_or_none(trace.action.active_playlist_after)
    active_playlist_before = _playlist_or_none(trace.action.active_playlist_before)
    matched_playlist_ref = _playlist_ref(matched_playlist, metadata)
    action_matched_playlist_ref = _playlist_ref(action_matched_playlist, metadata)
    active_playlist_after_ref = _playlist_ref(active_playlist_after, metadata)
    active_playlist_before_ref = _playlist_ref(active_playlist_before, metadata)
    has_event = trace.action.kind in {ActionKind.SWITCH, ActionKind.CYCLE}
```

Then update the `TickSummaryDto` construction to use only the references:

```python
        summary=TickSummaryDto(
            tick_id=trace.tick_id,
            ts=trace.ts,
            similarity=_round_float(trace.match.similarity),
            similarity_gap=_round_float(trace.match.similarity_gap),
            active_playlist=active_playlist_after_ref,
            matched_playlist=matched_playlist_ref,
            action_kind=trace.action.kind,
            reason_code=trace.action.reason_code,
            paused=trace.paused,
            executed=trace.action.executed,
            has_event=has_event,
        ),
```

Update top matches:

```python
            top_matches=[
                TopMatchDto(
                    playlist=_playlist_ref_from_name(playlist, metadata),
                    score=_round_float(score),
                )
                for playlist, score in trace.match.playlist_matches[:5]
            ],
```

Update the decision DTO:

```python
            decision=ActionDecisionDto(
                kind=trace.action.kind,
                reason_code=trace.action.reason_code,
                executed=trace.action.executed,
                active_playlist_before=active_playlist_before_ref,
                active_playlist_after=active_playlist_after_ref,
                matched_playlist=action_matched_playlist_ref,
            ),
```

- [ ] **Step 5: Run mapper tests and confirm they pass**

Run:

```bash
pytest -q tests/test_dashboard_api.py::test_build_tick_snapshot_maps_analysis_fields tests/test_dashboard_api.py::test_build_tick_snapshot_maps_paused_tick tests/test_dashboard_api.py::test_build_tick_snapshot_maps_unknown_playlist_ref_with_null_color
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit DTO mapper changes**

Run:

```bash
git add ui/dashboard_analysis.py tests/test_dashboard_api.py
git commit -m "refactor: wrap analysis playlist references"
```

Expected: commit succeeds with only the DTO mapper and associated tests staged.

---

## Task 3: Write Trace Store and Endpoint Projection Tests

**Files:**
- Modify: `tests/test_dashboard_api.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Update `test_analysis_store_read_window_empty`**

Replace the test body with:

```python
    window = analysis_store.read_window()

    assert window.live_tick_id is None
    assert window.traces == []
```

- [ ] **Step 2: Update `test_analysis_store_read_window_returns_recent`**

Replace the test body with:

```python
    for tick_id in range(1, 6):
        analysis_store.update(_make_trace(tick_id=tick_id))

    window = analysis_store.read_window(2)

    assert window.live_tick_id == 5
    assert [trace.tick_id for trace in window.traces] == [4, 5]
```

- [ ] **Step 3: Update `test_api_analysis_window_returns_recent`**

Replace the loop body in `test_api_analysis_window_returns_recent` with:

```python
    for tick_id in range(1, 5):
        analysis_store.update(_make_trace(tick_id=tick_id))
```

Keep the response assertions:

```python
    assert body["liveTickId"] == 4
    assert [tick["summary"]["tickId"] for tick in body["ticks"]] == [3, 4]
```

- [ ] **Step 4: Replace current color projection endpoint test**

Replace `test_api_analysis_window_applies_current_playlist_colors` with:

```python
def test_api_analysis_window_projects_traces_with_current_playlist_metadata(
    analysis_store,
    history_logger,
    config_path,
):
    metadata = DashboardRuntimeMetadata(
        display_of={"test_pl": "Test Playlist"},
        color_of={"test_pl": "#5BB8D4"},
    )
    app = _build_app(
        analysis_store,
        history_logger,
        config_path,
        metadata_provider=lambda: metadata,
    )
    analysis_store.update(
        _make_trace(
            tick_id=1,
            active_playlist_before="test_pl",
            active_playlist_after="test_pl",
            matched_playlist="missing_playlist",
            executed=False,
            action_kind=ActionKind.HOLD,
            reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
        )
    )

    status, body = wsgi_get(app, "/api/analysis/window")

    assert "200" in status
    tick = body["ticks"][0]
    assert tick["summary"]["activePlaylist"] == {
        "name": "test_pl",
        "display": "Test Playlist",
        "color": "#5BB8D4",
    }
    assert tick["summary"]["matchedPlaylist"] == {
        "name": "missing_playlist",
        "display": "missing_playlist",
        "color": None,
    }
    assert tick["act"]["topMatches"][0]["playlist"] == {
        "name": "focus",
        "display": "focus",
        "color": None,
    }
```

- [ ] **Step 5: Run trace store and endpoint tests and confirm they fail**

Run:

```bash
pytest -q tests/test_dashboard_api.py::test_analysis_store_read_window_empty tests/test_dashboard_api.py::test_analysis_store_read_window_returns_recent tests/test_dashboard_api.py::test_api_analysis_window_returns_recent tests/test_dashboard_api.py::test_api_analysis_window_projects_traces_with_current_playlist_metadata
```

Expected: failures show that `AnalysisStore` still stores dict snapshots and `_build_app()` does not yet accept `metadata_provider`.

---

## Task 4: Implement Raw Trace Storage and Request-Time Projection

**Files:**
- Modify: `ui/dashboard_analysis.py`
- Modify: `ui/dashboard.py`
- Modify: `main.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Add a trace window read model**

In `ui/dashboard_analysis.py`, add this dataclass after `DashboardRuntimeMetadata`:

```python
@dataclass(frozen=True)
class AnalysisTraceWindow:
    live_tick_id: int | None
    traces: list[SchedulerTickTrace]
```

- [ ] **Step 2: Change `AnalysisStore` to store traces**

Replace the current `AnalysisStore` implementation with:

```python
class AnalysisStore:
    def __init__(self, tick_history: int = 1200):
        self._lock = threading.Lock()
        self._ticks: deque[SchedulerTickTrace] = deque(maxlen=tick_history)
        self._live_tick_id: int | None = None

    def update(self, trace: SchedulerTickTrace) -> None:
        with self._lock:
            self._ticks.append(trace)
            self._live_tick_id = trace.tick_id

    def read_window(self, count: int | None = None) -> AnalysisTraceWindow:
        with self._lock:
            items = list(self._ticks)
            live_tick_id = self._live_tick_id
            if count is not None:
                items = items[-count:]
        return AnalysisTraceWindow(live_tick_id=live_tick_id, traces=items)
```

- [ ] **Step 3: Add a public response builder**

Add this function near `build_tick_snapshot()` in `ui/dashboard_analysis.py`:

```python
def build_tick_window_response(
    window: AnalysisTraceWindow,
    metadata: DashboardRuntimeMetadata,
) -> dict[str, Any]:
    response = TickWindowResponseDto(
        live_tick_id=window.live_tick_id,
        ticks=[map_tick_snapshot(trace, metadata) for trace in window.traces],
    )
    return response.model_dump(mode="json", by_alias=True)
```

- [ ] **Step 4: Update dashboard imports and metadata provider type**

In `ui/dashboard.py`, update imports:

```python
from collections.abc import Callable
```

Replace the `ui.dashboard_analysis` import with:

```python
from ui.dashboard_analysis import (
    AnalysisStore,
    DashboardRuntimeMetadata,
    build_tick_window_response,
)
```

Add this type and helper near `_parse_positive_count()`:

```python
MetadataProvider = Callable[[], DashboardRuntimeMetadata]


def _empty_metadata() -> DashboardRuntimeMetadata:
    return DashboardRuntimeMetadata(display_of={}, color_of={})
```

- [ ] **Step 5: Add metadata provider to `_build_app()`**

Change `_build_app()` signature in `ui/dashboard.py` to:

```python
def _build_app(
    analysis_store: AnalysisStore,
    history_logger: EventLogger | None = None,
    config_path: str = "",
    metadata_provider: MetadataProvider | None = None,
) -> bottle.Bottle:
```

Add this line immediately after `app = bottle.Bottle()`:

```python
    resolve_metadata = metadata_provider or _empty_metadata
```

- [ ] **Step 6: Project analysis traces in the endpoint**

Replace the success branch of `api_analysis_window()` with:

```python
        window = analysis_store.read_window(count)
        payload = build_tick_window_response(window, resolve_metadata())
        bottle.response.content_type = "application/json; charset=utf-8"
        return json.dumps(payload)
```

Keep the invalid count branch unchanged.

- [ ] **Step 7: Thread metadata provider through `DashboardHTTPServer`**

Update `DashboardHTTPServer.__init__()` signature:

```python
    def __init__(
        self,
        analysis_store: AnalysisStore,
        history_logger: EventLogger | None = None,
        config_path: str = "",
        requested_port: int = 0,
        metadata_provider: MetadataProvider | None = None,
    ):
```

Store it:

```python
        self._metadata_provider = metadata_provider
```

Update `start()`:

```python
        app = _build_app(
            self._analysis_store,
            self._history,
            self._config_path,
            self._metadata_provider,
        )
```

- [ ] **Step 8: Update tray mode wiring**

In `main.py`, replace the tray-mode analysis import with:

```python
    from ui.dashboard_analysis import AnalysisStore, extract_runtime_metadata
```

Replace `_handle_tick()` with:

```python
    def _handle_tick(trace: SchedulerTickTrace) -> None:
        analysis_store.update(trace)
```

Pass the metadata provider into `DashboardHTTPServer`:

```python
    httpd = DashboardHTTPServer(
        analysis_store,
        scheduler.history_logger,
        config_path,
        requested_port=dashboard_api_port,
        metadata_provider=lambda: extract_runtime_metadata(scheduler),
    )
```

- [ ] **Step 9: Run trace store and endpoint tests**

Run:

```bash
pytest -q tests/test_dashboard_api.py::test_analysis_store_read_window_empty tests/test_dashboard_api.py::test_analysis_store_read_window_returns_recent tests/test_dashboard_api.py::test_api_analysis_window_empty tests/test_dashboard_api.py::test_api_analysis_window_returns_recent tests/test_dashboard_api.py::test_api_analysis_window_projects_traces_with_current_playlist_metadata
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit trace store changes**

Run:

```bash
git add ui/dashboard_analysis.py ui/dashboard.py main.py tests/test_dashboard_api.py
git commit -m "refactor: project analysis traces at request time"
```

Expected: commit succeeds with raw trace storage and endpoint projection changes.

---

## Task 5: Update Frontend Analysis DTO Types

**Files:**
- Modify: `dashboard-v2/src/lib/dashboardAnalysis.ts`
- Test: `dashboard-v2`

- [ ] **Step 1: Add `PlaylistRef` and update related interfaces**

In `dashboard-v2/src/lib/dashboardAnalysis.ts`, add this interface before `ActionDecision`:

```ts
export interface PlaylistRef {
  name: string
  display: string
  color: string | null
}
```

Replace `ActionDecision`, `TopMatch`, and the playlist portion of `TickSummary` with:

```ts
export interface ActionDecision {
  kind: ActionKind
  reasonCode: ActionReasonCode
  executed: boolean
  activePlaylistBefore: PlaylistRef | null
  activePlaylistAfter: PlaylistRef | null
  matchedPlaylist: PlaylistRef | null
}

export interface TopMatch {
  playlist: PlaylistRef
  score: number
}
```

```ts
export interface TickSummary {
  tickId: number
  ts: number
  similarity: number
  similarityGap: number
  activePlaylist: PlaylistRef | null
  matchedPlaylist: PlaylistRef | null
  actionKind: ActionKind
  reasonCode: ActionReasonCode
  paused: boolean
  executed: boolean
  hasEvent: boolean
}
```

- [ ] **Step 2: Run type-check and confirm consumer failures**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: TypeScript fails in analysis consumers that still read `activePlaylistColor`, `activePlaylistDisplay`, top-match `display`, or top-match `color`.

---

## Task 6: Update Frontend Consumers for `PlaylistRef`

**Files:**
- Modify: `dashboard-v2/src/features/dashboard-analysis/presenters.ts`
- Modify: `dashboard-v2/src/features/dashboard-analysis/timeline.ts`
- Modify: `dashboard-v2/src/features/dashboard-analysis/ActPanel.vue`
- Test: `dashboard-v2`

- [ ] **Step 1: Update presenter imports**

In `presenters.ts`, include `PlaylistRef` in the type import:

```ts
import type {
  ActionDecision,
  ActionReasonCode,
  ControllerBlocker,
  ControllerEvaluation,
  PlaylistRef,
  PolicyDiagnostic,
  PolicyId,
  TopMatch,
  TickSnapshot,
} from '@/lib/dashboardAnalysis'
```

- [ ] **Step 2: Replace playlist name formatter**

Replace `formatPlaylistName()` with:

```ts
function formatPlaylistRef(
  playlist: PlaylistRef | null | undefined,
  t: Translate,
): string {
  return playlist?.display ?? playlist?.name ?? t('dashboard_none')
}
```

- [ ] **Step 3: Update top match and tick label presenters**

Replace `getTopMatchName()` and `getTickPlaylistLabel()` with:

```ts
export function getTopMatchName(match: TopMatch, t: Translate): string {
  return formatPlaylistRef(match.playlist, t)
}

export function getTickPlaylistLabel(
  tick: TickSnapshot,
  type: 'active' | 'matched',
  t: Translate,
): string {
  return formatPlaylistRef(
    type === 'active' ? tick.summary.activePlaylist : tick.summary.matchedPlaylist,
    t,
  )
}
```

- [ ] **Step 4: Update decision summary presenter**

Replace the first lines of `getDecisionSummary()` with:

```ts
  const activeBefore = formatPlaylistRef(decision.activePlaylistBefore, t)
  const activeAfter = formatPlaylistRef(decision.activePlaylistAfter, t)
```

Keep the existing switch body unchanged.

- [ ] **Step 5: Update timeline segment construction**

In `timeline.ts`, replace the playlist/color extraction inside `ticks.forEach()` with:

```ts
    const playlist =
      type === 'active' ? tick.summary.activePlaylist : tick.summary.matchedPlaylist
    const paused = tick.summary.paused
    const key = paused ? '__paused__' : playlist?.name ?? '__none__'
    const color = paused ? mutedColor : playlist?.color ?? mutedColor
```

- [ ] **Step 6: Update top match rendering**

In `ActPanel.vue`, replace the top match key and color binding:

```vue
            :key="match.playlist.name"
```

```vue
                :style="{ backgroundColor: match.playlist.color ?? mutedPlaylistColor }"
```

- [ ] **Step 7: Search for removed flattened fields**

Run:

```bash
rg -n "activePlaylistDisplay|activePlaylistColor|matchedPlaylistDisplay|matchedPlaylistColor|match\\.display|match\\.color" dashboard-v2/src
```

Expected: no matches.

- [ ] **Step 8: Run frontend type-check**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: type-check passes.

- [ ] **Step 9: Commit frontend consumer changes**

Run:

```bash
git add dashboard-v2/src/lib/dashboardAnalysis.ts dashboard-v2/src/features/dashboard-analysis/presenters.ts dashboard-v2/src/features/dashboard-analysis/timeline.ts dashboard-v2/src/features/dashboard-analysis/ActPanel.vue
git commit -m "refactor: consume playlist references in analysis UI"
```

Expected: commit succeeds with only frontend analysis DTO and consumer changes staged.

---

## Task 7: Final Verification

**Files:**
- Verify: `tests/test_dashboard_api.py`
- Verify: `dashboard-v2`

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
pytest -q tests/test_dashboard_api.py
```

Expected: all tests in `tests/test_dashboard_api.py` pass.

- [ ] **Step 2: Run full backend test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend type-check**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: type-check passes.

- [ ] **Step 4: Run frontend build-only**

Run:

```bash
cd dashboard-v2
npm run build-only
```

Expected: Vite build completes successfully.

- [ ] **Step 5: Run final removed-field search**

Run:

```bash
rg -n "activePlaylistDisplay|activePlaylistColor|matchedPlaylistDisplay|matchedPlaylistColor|active_playlist_display|active_playlist_color|matched_playlist_display|matched_playlist_color" ui dashboard-v2/src
```

Expected: no matches.

- [ ] **Step 6: Commit verification cleanup if files changed**

If verification required code or test fixes, run:

```bash
git add ui/dashboard_analysis.py ui/dashboard.py main.py tests/test_dashboard_api.py dashboard-v2/src/lib/dashboardAnalysis.ts dashboard-v2/src/features/dashboard-analysis/presenters.ts dashboard-v2/src/features/dashboard-analysis/timeline.ts dashboard-v2/src/features/dashboard-analysis/ActPanel.vue
git commit -m "test: verify analysis playlist trace projection"
```

Expected: either a small final commit is created, or `git status --short` shows no remaining files from this work.

---

## Self-Review

- Spec coverage: covers both requested aspects, `PlaylistRef` DTO and raw trace `AnalysisStore`.
- Store boundary: `AnalysisStore` stores diagnostic facts; Bottle endpoint performs current-metadata projection.
- Type consistency: Python uses `PlaylistRefDto`; TypeScript uses `PlaylistRef`; both expose `name`, `display`, and `color`.
- API consistency: `TickSummary`, `TopMatch`, and `ActionDecision` all use the same playlist reference shape.
- Verification coverage: backend mapper tests, endpoint projection tests, frontend type-check, frontend build, and removed-field search are included.
