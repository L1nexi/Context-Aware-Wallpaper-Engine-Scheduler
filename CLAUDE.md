# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Context-Aware Wallpaper Engine Scheduler — a Windows-only Python app (packaged as `.exe`) that runs in the system tray and switches Wallpaper Engine playlists based on environmental signals (active window, idle time, CPU load, time of day, season, weather).

## Commands

```bash
# Python dependencies
pip install -r requirements.txt

# Run from source
python main.py                 # tray host: scheduler + HTTP server + tray entrypoint
python main.py --no-tray       # console-only scheduler loop for debugging
python main.py --config path/to/config.json

# Frontend (dashboard/)
cd dashboard && npm install
cd dashboard && npm run dev        # Vite dev server for SPA-only iteration
cd dashboard && npm run type-check
cd dashboard && npm run build      # runs type-check, outputs dashboard/dist/
cd dashboard && npm run preview

# Packaging (Windows only)
.\scripts\build.bat              # PyInstaller bundle; embeds dashboard/dist/

# Manual validation / simulation
python misc/sim_match.py
python misc/vis_explore.py

# Testing (pytest)
pip install pytest
pytest tests/ -v                          # all tests
pytest tests/test_dashboard_api.py -v     # HTTP server / API endpoint tests
```

There is no formal Python test suite yet (tests directory exists but no test source files are committed). For backend validation, run `python main.py --no-tray`; for matcher behavior, use `python misc/sim_match.py`.

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

### FRONTEND REWRITE — 推倒重写

**The current Vue 3 + Element Plus + ECharts frontend (`dashboard/`) is being completely rewritten from scratch.** The existing SPA code is deprecated. Do NOT spend time fixing or polishing it — the rewrite will replace everything.

What IS stable and must NOT be broken:

- **`ui/dashboard.py` HTTP API** — the contract between backend and any future frontend. All `/api/*` endpoints, response schemas, and `TickState` shape are the authoritative interface.
- **Production build path** — whatever SPA is built into `dashboard/dist/` must be served by Bottle (`ui/dashboard.py`) and run inside pywebview (`ui/webview.py`).
- **`vite.config.ts`** must keep `base: './'` (files served from a local host process, not a CDN).
- **Router** must use hash history (`createWebHashHistory`) — no server-side route awareness.
- **Locale** comes from the dashboard URL query (`?locale=`) set by the host process before spawning the window.
- **Three user-facing surfaces** must still be covered: live tick view, history timeline, config editor.

Two-process architecture (unchanged):

```
Tray host process                     Dashboard process
  scheduler.on_tick ───────┐          pywebview (Edge/WebView2)
                            v                 │
  StateStore -> Bottle /api/* -> http://127.0.0.1:{port}?locale=xx
```

- `main.py` tray mode is the composition root: creates `WEScheduler`, `StateStore`, wires `scheduler.on_tick = state_store.update(build_tick_state(...))`, starts `DashboardHTTPServer`, passes the port to the dashboard subprocess.
- `ui/dashboard.py` exposes `/api/state`, `/api/ticks`, `/api/history`, `/api/config`, `/api/tags/presets`, `/api/playlists/scan`, `/api/we-path`. `TickState` is the live-state schema. `last_event_id` triggers history auto-refresh.
- `ui/webview.py` creates a pywebview window pointing at the local HTTP server; closing the window exits only the dashboard process.

**Tray UI** (`ui/tray.py`): pystray + tkinter dialogs; reads OS locale via `utils/i18n.py` for zh/en strings. Menu callbacks use direct attribute assignment.

## Testing (Backend)

The scheduler core (`core/scheduler.py`, `core/policies.py`, `core/matcher.py`) is considered stable — tests for it follow later. First priority is the HTTP/data backend, which must stay reliable during the frontend rewrite.

### Test framework

pytest. No plugins required. Tests live in `tests/`.

### `ui/dashboard.py` — HTTP API routes

`_build_app(state_store, history_logger, config_path)` is the pure injection point: it returns a fully wired `bottle.Bottle` instance. Test routes directly via WSGI (`bottle.Bottle` is a WSGI callable) without starting a real server.

| Route | What to test |
|-------|-------------|
| `GET /api/state` | Populate `StateStore`, assert JSON matches `dataclasses.asdict(TickState)` fields |
| `GET /api/health` | Assert `{"ok": true}` |
| `GET /api/ticks?count=N` | Write N+1 ticks, assert ring buffer caps at `count` |
| `GET /api/history?limit=N&from=ts&to=ts` | Pass mock `EventLogger` or `HistoryLogger(tmp_path)`; assert segments + events shape |
| `GET /api/config` | Temp config file → assert returned JSON; missing file → 404 |
| `POST /api/config` | Valid payload → 200 + atomic write to file. Invalid payload → 422 with `_flatten_errors` details. No body → 400 |
| `GET /api/tags/presets` | Assert returns `KNOWN_TAGS` list from `core.policies` |
| `GET /api/playlists/scan` | Mock `we_path.find_we_config_json` → temp WE config.json; assert playlist names extracted by username |
| `GET /api/we-path` | Mock `we_path.find_wallpaper_engine`; assert `{"path": ..., "valid": ...}` |
| Static files | Assert `index.html` served at `/`, SPA fallback for unknown paths, 403 for path traversal attempts |

`StateStore` needs no mocking — it's a plain thread-safe wrapper, use it directly.

### `utils/history_logger.py` — `HistoryLogger`

Pass `tmp_path` as `data_dir`. Key behaviors to test:

- `write(type, data)` → returns monotonically incrementing int; `last_event_id` matches
- `read(limit, from_ts, to_ts)` → `{"segments": [...], "events": [...]}`
- Segment building: seed events correctly resolve pre-window playlist state for all 6 `EventType` seeds (verify `_SEED_PLAYLIST_SOURCE` / `_SEED_INITIAL_TYPE` tables)
- Monthly file rotation: `_months_in_range` covers month boundaries; `_ensure_file` switches filepath on month change
- Edge cases: empty history → empty result; corrupt JSONL lines → silently skipped; `from_ts`/`to_ts` both `None` → defaults to last 1 hour; no matching month files → empty result; event exactly at boundary timestamps
- Thread safety: concurrent `write()` calls from multiple threads → correct IDs, no data loss

### `utils/we_path.py` — `find_wallpaper_engine` / `find_we_config_json`

- 3-tier resolution: configured path (exists) → Steam registry search → `None`
- `_steam_install_path()`: non-Windows → `None`; Windows → reads `winreg` HKLM / HKCU
- `_parse_library_folders()`: parses `libraryfolders.vdf` `"path"` entries
- Mock `winreg` and `os.path.isfile` for cross-platform testability; on Windows, integration-test against real registry

### `utils/config_loader.py` — Pydantic validation

- Valid minimal config (1 playlist, 1 tag) → `AppConfig.model_validate()` succeeds
- `extra="forbid"` on `AppConfig`: unknown top-level key → `ValidationError`
- `extra="allow"` on `PoliciesConfig`: unknown policy name → silently accepted
- `ConfigLoader.load()`: file not found → `FileNotFoundError`; invalid JSON → `ValueError`

### `core/event_logger.py` — Protocol conformance

- `EventType` enum has exactly 6 members matching the tagged union
- `HistoryLogger` structurally satisfies `EventLogger` Protocol (`isinstance(h, EventLogger)`)

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
- **Hooks via direct attribute assignment**: `scheduler.on_auto_resume`, `scheduler.on_tick`, `tray.on_show_dashboard` — callbacks set externally by the host, called from within. No getters/setters.
- **Services via constructor injection**: `history_logger: EventLogger` is passed to `WEScheduler.__init__`. Services differ from hooks — they are required dependencies, not optional observers. `EventLogger` is a Protocol in `core/event_logger.py`; `HistoryLogger` (in `utils/`) implements it. Dependency direction: `utils → core`.
- **State export/import**: Policies and controller implement `export_state()` / `import_state()` so hot-reload preserves EMA accumulators and cooldown timestamps.
- **Gate chain**: `SchedulingController` composes multiple deferral conditions (CPU gate, Fullscreen gate). Each gate is a class with `should_defer(context) -> bool`.
- **Tag vector space**: Playlists, policy directions, and fallback edges share one flat tag namespace (e.g. `#focus`, `#rain`). Adding a new signal means defining new tag keys, updating the relevant policy, and optionally adding `TagSpec` fallback entries — no changes to `Matcher`.
- **`config_key` validation**: Each `Policy` subclass declares `config_key: ClassVar[str]` matching an attribute on `PoliciesConfig`. `__init_subclass__` validates this at import time; typos raise `TypeError` before the app starts.
- **HistoryLogger wiring**: `HistoryLogger(get_data_dir())` is created in `main.py` and passed to `WEScheduler(config_path, history_logger)`. The scheduler passes it through to `Actuator` in `_build_runtime_components()`, and `main.py` passes it to `DashboardHTTPServer`.
- **Tagged union events**: Six event types — `playlist_switch`, `wallpaper_cycle`, `pause`, `resume`, `start`, `stop`. Each carries type-specific `data` dict. Timestamps are UTC ISO 8601 at second precision (`timespec="seconds"`) for lexicographic ordering.
- **Segment building**: `_SEED_PLAYLIST_SOURCE` and `_SEED_INITIAL_TYPE` lookup tables resolve pre-window state from seed events. `_build_segments()` replays events oldest-first to produce continuous timeline blocks for the history timeline.

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
