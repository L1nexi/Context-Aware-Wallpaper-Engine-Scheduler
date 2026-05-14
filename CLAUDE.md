# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

Windows-only Python desktop application (0.x, breaking changes allowed). Context-aware Wallpaper Engine scheduler: six sensors feed context into four policies, which produce tag vectors matched via cosine similarity to playlists. A controller applies gating (idle, cooldown, fullscreen, CPU), and an actuator executes via WE CLI. The scheduler runs in a system tray with a Vue 3 diagnostics dashboard served over local HTTP.

**Product scope constraint**: Core value is automated scheduling + explainable diagnostics + text-based config workflow. This is NOT a general-purpose management dashboard. The full Config Editor and History pages are frozen — diagnostics is the active dashboard focus. See `AGENTS.md` for the authoritative collaboration constraints.

## Common Commands

```bash
# Virtual environment
venv313\Scripts\activate

# Run (tray mode)
python main.py

# Run (console mode, debug)
python main.py --no-tray

# Run with dashboard API on fixed port + Vite dev server for frontend dev
python main.py --dashboard-api-port 38417
cd dashboard && npm run dev

# Tests
pytest -q                          # all tests
pytest -q tests/test_config_loader.py   # single file

# Config tools
python main.py config

# Build executable
.\scripts\build.bat

# Dashboard (Vue 3 + Vite + TypeScript)
cd dashboard
npm install
npm run lint
npm run type-check
npm run build-only
```

## Architecture

```
Sensors -> Context -> Policies -> Matcher -> Controller -> Actuator -> WEExecutor
                                                               |
                                      SchedulerTickTrace -> AnalysisStore -> HTTP :0 -> Diagnostics SPA
                                                               |
                                  HistoryLogger.write() -> history-{YYYY}-{MM}.jsonl
```

### Sense-Think-Act pipeline (1 Hz tick)

Each tick produces a `SchedulerTickTrace` dataclass containing the full diagnostic snapshot:

1. **Sense** — `ContextManager.refresh()` polls all registered sensors. Each sensor has a `key` class attribute matching a `Context` dataclass field. `core/sensors.py` defines six sensors: Window, Idle, CPU, Fullscreen, Weather, Time. The `SENSOR_REGISTRY` list controls which sensors are instantiated.

2. **Think** — `Matcher.evaluate()` runs each `Policy` and aggregates their tag contributions into a context vector, resolves unknown tags through recursive fallback (from `config/tags.yaml`), normalizes, and scores all playlist vectors via cosine similarity.

3. **Act** — `Actuator.act()` calls `SchedulingController.decide_action()` which gates the match decision through: cooldown (switch/cycle), fullscreen pause, CPU threshold, and idle threshold. The actuator then executes via `WEExecutor` (which shells out to Wallpaper Engine's CLI).

### Key modules

| Directory    | Purpose                                                                                                                            |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `core/`      | Scheduler, policies, matcher, controller, actuator, executor, sensors, context, diagnostics types                                  |
| `ui/`        | Tray icon (`tray.py`), Bottle HTTP server (`dashboard.py`), DTO mapping (`dashboard_analysis.py`), pywebview window (`webview.py`) |
| `utils/`     | Config loading, Pydantic runtime config models, i18n, logging, history logger, WE path detection                                   |
| `dashboard/` | Vue 3 + Vite + TypeScript frontend (Tailwind v4, Pinia, vue-router hash mode, shadcn/reka components)                              |
| `tests/`     | pytest tests                                                                                                                       |

### Dual-process dashboard

The tray host process runs a Bottle HTTP server (`ui/dashboard.py`). The dashboard frontend is a separate pywebview subprocess spawned on demand. This ensures closing the dashboard window never kills the scheduler. The `AnalysisStore` (thread-safe deque, max 1200 ticks) bridges the gap — `scheduler.on_tick` pushes traces, API endpoints read them.

API endpoints: `GET /api/health`, `GET /api/analysis/window?count=N`

### Config system

Six fixed YAML files in `config/`: `scheduler.yaml`, `playlists.yaml`, `tags.yaml`, `activity.yaml`, `context.yaml`, `scheduling.yaml`. Hot-reload via fingerprint (mtime). The loader validates each file against a Pydantic model, then produces a single `SchedulerConfig` via `ConfigFiles.to_verified_scheduler_config()`. `PoliciesConfig` uses `extra="forbid"` — unknown policy keys are rejected.

YAML anchors, aliases, and merge keys are allowed as single-file YAML authoring conveniences; the expanded document still goes through the same schema and cross-file validation.

## Key Conventions

- Full type annotations throughout. Docstrings only for functions that raise exceptions (must document exception types and conditions).
- Dataclasses for diagnostics/cross-cutting types; Pydantic for config and API DTOs.
- Don't build backwards-compatibility shims — 0.x allows breaking changes.
- Don't write tests that merely verify attribute passthrough or trivial branching; tests must cover algorithmic correctness and boundary conditions.
- Dashboard frontend: `base: './'`, `createWebHashHistory()`, locale via dashboard URL query param. Do not regress to scoped CSS, page-private global classes, or hardcoded colors outside the token system.
- pywebview loads the dashboard from a local HTTP server; the SPA is served from `dashboard/dist/`.
- Config UX: text-based YAML is the primary workflow; `Config Tools.bat` / `WEScheduler.exe config` is the auxiliary validate/detect/scan entry. Dashboard remains Diagnostics-only.
