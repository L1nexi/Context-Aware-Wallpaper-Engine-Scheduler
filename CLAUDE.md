# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Context-Aware Wallpaper Engine Scheduler — a Windows-only Python app (packaged as `.exe`) that runs in the system tray and switches Wallpaper Engine playlists based on environmental signals (active window, idle time, CPU load, time of day, season, weather).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run from source
python main.py              # tray mode
python main.py --no-tray    # console mode (useful for debugging)
python main.py --config path/to/config.json

# Build executable (Windows only)
.\scripts\build.bat         # outputs dist/WEScheduler.exe

# Frontend (dashboard/)
cd dashboard && npm run build   # build SPA to dashboard/dist/
cd dashboard && npm run type-check

# Manual algorithm testing
python misc/sim_match.py    # matching algorithm simulator
python misc/vis_explore.py  # visualization tool
```

No formal test framework exists. Use `--no-tray` mode and `misc/sim_match.py` for manual validation.

## Directory Layout

```
core/       Business logic — scheduler, policies, sensors, matcher, controller, actuator, executor
ui/         User interface — tray icon, dashboard HTTP server, webview window
utils/      Infrastructure — config loading, logging, i18n, icon generation, path resolution
dashboard/  Vue 3 SPA frontend (built to dashboard/dist/, committed to git)
main.py     Entry point — mode dispatch (dashboard subprocess / console / tray)
```

## Architecture: Sense-Think-Act Loop

The scheduler runs a 1-second tick loop in a background thread:

```
Sensors → Context → Policies → Matcher → Controller → Actuator → WEExecutor
                                                       │
                                                  on_tick(scheduler, context, result)  ← hook
```

**Sense** (`core/sensors.py`): Each sensor has a `key` class attribute matching a field on `Context`. Sensors are registered in `_SENSOR_REGISTRY` and instantiated via `create()` class methods (returns `None` to skip registration).

**Think** (`core/policies.py` + `core/matcher.py`):
- Each policy's `_compute_output()` returns a `PolicyOutput(direction, salience, intensity)` dataclass. The base `Policy.get_output()` L2-normalizes `direction` before returning.
- Contribution to the env vector: `direction * salience * intensity * weight_scale`
- `ActivityPolicy`: dual EMA tracks — direction EMA (raw un-normalized vector) + scalar magnitude EMA. `intensity = magnitude_ema`; direction is normalized by base class. Transitions between tags (e.g. `#focus` → `#chill`) smooth the direction without norm dip.
- `TimePolicy` / `SeasonPolicy`: Hann window over the 24h / 365d cycle. `salience` = Hann peak value (clarity of current period); `intensity` = 1.0 always.
- `WeatherPolicy`: raw tag vector per OWM code encodes both type and severity. `intensity` = L2 norm of raw vector (T1≈0.25 → T4=1.0); `direction` = normalized; `salience` = 1.0.
- `Matcher` aggregates all `PolicyOutput`s, applies `TagSpec` fallback on unknown tags, then cosine-matches against pre-normalized playlist vectors. Returns `MatchResult`.

**Act** (`core/controller.py` + `core/actuator.py` + `core/executor.py`):
- `SchedulingController` is a gate chain: blocks switching if CPU > threshold, fullscreen app active, or cooldown not elapsed. `similarity_gap` and `max_policy_magnitude` are available for future dynamic cooldown logic.
- `Actuator` calls `WEExecutor` which wraps `wallpaper64.exe -control openPlaylist -playlist <name>`
- Events are written to month-partitioned `history-{YYYY}-{MM}.jsonl` via `HistoryLogger.write()`

**Orchestration** (`core/scheduler.py`):
- Manages pause/resume state (timed or indefinite), persisted to `state.json`
- Hot-reloads `scheduler_config.json` on file change; policies/controller export and re-import transient state across reloads
- Exposes hooks set externally: `on_auto_resume` (tray icon sync), `on_tick(scheduler, context, result)` (dashboard push)

## Dashboard

Two-process architecture: Tray Host (scheduler + HTTP server) spawns Dashboard Window (pywebview loading Vue SPA) on demand.

```
Tray Host process                    Dashboard process
  Bottle HTTP :0  ──HTTP/1s polling──→  pywebview (WebView2)
  StateStore     ←──on_tick hook────    Vue 3 + Element Plus
```

- `ui/dashboard.py`: TickState dataclass, StateStore (thread-safe with `threading.Lock`), `build_tick_state()`, Bottle-based HTTP server (`/api/state`, `/api/health`, `/api/ticks?count=N`, `/api/history?limit=N&from=ISO&to=ISO`, static SPA with hash-route fallback), binds `127.0.0.1:0` (OS-assigned port)
  - `last_event_id` on TickState: monotonic counter incremented per `write()`, frontend watches for auto-refresh.
  - `display_of` dict (built in `_build_runtime_components()`) maps playlist name → display name for CJK-friendly UI labels.
- `ui/webview.py`: Thin pywebview wrapper, `create_and_block()`, window close = process exit
- `dashboard/`: Vue 3 + TypeScript + Element Plus SPA, 1s state polling + 5s ticks polling, zombie detection (3 failures → 5s countdown → `window.close()`), `?locale=` URL param for i18n
  - `src/composables/useHistory.ts` — `segments`, `events`, `fetchHistory(params?)`, auto-refresh via `watch(state.last_event_id)`.
  - `src/views/HistoryView.vue` — ECharts Gantt (segments) + event list with filter bar (presets + date pickers).
  - `src/components/ConfidencePanel.vue` — ECharts sparkline from `/api/ticks` data.
  - `src/views/DashboardView.vue` — `el-tabs` wrapping Live tab (existing grid) and History tab (HistoryView).

**Wiring** (in `main.py` tray mode):
```python
state_store = StateStore()
scheduler.on_tick = lambda s, ctx, res: state_store.update(build_tick_state(s, ctx, res))
httpd = DashboardHTTPServer(state_store)
httpd.start()
tray = TrayIcon(scheduler)
tray.on_show_dashboard = lambda: _spawn_dashboard_subprocess(httpd.port)
```

Scheduler does NOT hold `StateStore` — it only calls `on_tick()`. The host (main.py) owns the wiring.

**Tray UI** (`ui/tray.py`): pystray + tkinter dialogs; reads OS locale via `utils/i18n.py` for zh/en strings. Menu callbacks use direct attribute assignment (same pattern as scheduler hooks).

## Tag Semantics (v0.5.0)

The `tag: value` system has three distinct semantic roles:

| Context | `value` meaning |
|---|---|
| `playlists[].tags` | **Affinity** — aesthetic fit of this playlist for the concept. Only relative ratios matter (vectors are L2-normalized before matching). |
| `PolicyOutput.direction` | **Direction** — unit L2-normalized; encodes *what kind* of signal, not how strong. |
| `PolicyOutput.salience` | **Salience** — clarity of category membership [0,1]; e.g. Hann window value for time/season. |
| `PolicyOutput.intensity` | **Intensity** — physical/behavioral magnitude [0,1]; e.g. weather severity T1–T4. |
| `tags[tag].fallback` | **Fallback edges** — when a policy emits a tag not in any playlist, energy cascades along fallback edges (weight-attenuated) until a known tag is reached. |

`weight_scale` (per policy) is a **priority multiplier** orthogonal to intensity: "how important is this signal type globally."

## Configuration

Config is validated by Pydantic models in `utils/config_loader.py`. See `scheduler_config.example.json` for a full reference. Key sections:

- `wallpaper_engine_path`: path to `wallpaper64.exe`
- `tags`: `TagSpec` fallback graph — defines how policy-emitted tags cascade to playlist tags when there's no direct match (e.g. `"#dawn": {"fallback": {"#day": 0.7, "#chill": 0.3}}`)
- `playlists[].tags`: affinity weight dict (values are relative; system normalizes)
- `policies.activity.process_rules` / `title_rules`: `{process_name: "#tag"}` / `{keyword: "#tag"}` match rules
- `policies.weather.api_key` / `lat` / `lon`: OpenWeatherMap credentials
- `scheduling`: `idle_threshold`, `switch_cooldown`, `cycle_cooldown`, `force_after`, `cpu_threshold`, `pause_on_fullscreen`

`extra="forbid"` on all Pydantic models means unknown config keys raise a `ValidationError` at startup. `PoliciesConfig` uses `extra="allow"` so unknown policy names are silently ignored (enables future/experimental policies without crashing).

## Key Design Patterns

- **Registry + Factory**: `_SENSOR_REGISTRY` / `_POLICY_REGISTRY` + `create()` classmethods control which sensors/policies are instantiated based on config.
- **Hooks via direct attribute assignment**: `scheduler.on_auto_resume`, `scheduler.on_tick`, `tray.on_show_dashboard` — set externally by the host, called from within. No getters/setters, no constructor injection. Same simple pattern everywhere.
- **State export/import**: Policies and controller implement `export_state()` / `import_state()` so hot-reload preserves EMA accumulators and cooldown timestamps.
- **Gate chain**: `SchedulingController` composes multiple deferral conditions (CPU gate, Fullscreen gate). Each gate is a class with `should_defer(context) -> bool`.
- **Tag vector space**: Playlists, policy directions, and fallback edges share one flat tag namespace (e.g. `#focus`, `#rain`). Adding a new signal means defining new tag keys, updating the relevant policy, and optionally adding `TagSpec` fallback entries — no changes to `Matcher`.
- **`config_key` validation**: Each `Policy` subclass declares `config_key: ClassVar[str]` matching an attribute on `PoliciesConfig`. `__init_subclass__` validates this at import time; typos raise `TypeError` before the app starts.
- **HistoryLogger injection**: `scheduler.history_logger = HistoryLogger(...)` must be set BEFORE `scheduler.initialize()`. The logger is passed through to `Actuator` in `_build_runtime_components()` and to `DashboardHTTPServer` constructor.
- **Tagged union events**: Six event types — `playlist_switch`, `wallpaper_cycle`, `pause`, `resume`, `start`, `stop`. Each carries type-specific `data` dict. Timestamps are UTC ISO 8601 at second precision (`timespec="seconds"`) for lexicographic ordering.
- **Segment building**: `_SEED_PLAYLIST_SOURCE` and `_SEED_INITIAL_TYPE` lookup tables resolve pre-window state from seed events. `_build_segments()` replays events oldest-first to produce continuous timeline blocks for the Gantt chart.

## Runtime Artifacts

| Path | Purpose |
|------|---------|
| `scheduler_config.json` | Main config (hot-reloaded on change) |
| `data/state.json` | Persisted pause/playlist state |
| `logs/scheduler.log` | Rotating log (5 MB × 3 backups) |
| `data/history-{YYYY}-{MM}.jsonl` | Append-only event log with monthly rotation (top-8 tags per switch) |

Logger hierarchy: root `WEScheduler` → children `WEScheduler.Core`, `.Policy`, `.Sensor`, `.Tray`, `.Dashboard`, `.WebView`, `.Config`, `.I18n`, `.Matcher`, `.Controller`, `.Actuator`, `.Executor`, `.Context` (`utils/logger.py`).

## Platform Notes

- Windows-only: uses `win32gui`, `win32process`, `win32api` (pywin32), and DPI awareness APIs in `main.py`.
- `utils/app_context.py` resolves the app root correctly for both source and PyInstaller bundle (`sys._MEIPASS`).
- `misc/` scripts are standalone utilities, not part of the packaged app.
- Dashboard frontend: `dashboard/dist/` is committed to git; `npm run build` is a dev step, not needed at packaging time.
