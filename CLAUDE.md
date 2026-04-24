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

# Manual algorithm testing
python misc/sim_match.py    # matching algorithm simulator
python misc/vis_explore.py  # visualization tool
```

No formal test framework exists. Use `--no-tray` mode and `misc/sim_match.py` for manual validation.

## Architecture: Sense-Think-Act Loop

The scheduler runs a 1-second tick loop in a background thread:

```
Sensors → Context → Policies → Matcher → Controller → Actuator → WEExecutor
```

**Sense** (`core/sensors.py`): Each sensor implements `read() -> dict`. Sensors are registered in `_SENSOR_REGISTRY` and instantiated via `create()` class methods (conditional on config).

**Think** (`core/policies.py` + `core/matcher.py`):
- Each policy converts the context snapshot into a tag weight vector (e.g., `{"#focus": 0.8, "#day": 0.5}`)
- `ActivityPolicy` uses EMA smoothing over process/window title rules
- `TimePolicy` and `SeasonPolicy` use Hann window interpolation for smooth transitions between discrete states
- `WeatherPolicy` uses a 4-tier intensity model (T1=0.2 → T4=1.0) mapped from OWM weather codes
- `Matcher` aggregates all policy vectors and selects the best playlist via cosine similarity

**Act** (`core/controller.py` + `core/actuator.py` + `core/executor.py`):
- `SchedulingController` is a gate chain: blocks switching if CPU > threshold, fullscreen app active, or cooldown not elapsed
- `Actuator` calls `WEExecutor` which wraps `wallpaper64.exe -control openPlaylist -playlist <name>`
- All events are appended to `history.jsonl`

**Orchestration** (`core/scheduler.py`):
- Manages pause/resume state (timed or indefinite), persisted to `state.json`
- Hot-reloads `scheduler_config.json` on file change; policies/controller export and re-import transient state across reloads
- Exposes `on_auto_resume` hook for tray sync

**Tray UI** (`core/tray.py`): pystray + tkinter dialogs; reads OS locale via `utils/i18n.py` to serve zh/en strings.

## Configuration

Config is validated by Pydantic models in `utils/config_loader.py`. See `scheduler_config.example.json` for a full reference. Key sections:

- `wallpaper_engine_path`: path to `wallpaper64.exe`
- `playlists[].tags`: tag weight dict that the matcher scores against (e.g., `{"#focus": 1.0, "#day": 0.9}`)
- `policies.activity.rules`: list of `{process, title, tags}` match rules
- `policies.weather.api_key` / `lat` / `lon`: OpenWeatherMap credentials
- `scheduling`: `idle_threshold`, `switch_cooldown`, `cycle_cooldown`, `force_after`, `cpu_threshold`, `pause_on_fullscreen`

## Key Design Patterns

- **Registry + Factory**: `_SENSOR_REGISTRY` / `_POLICY_REGISTRY` dicts + `create()` classmethods control which sensors/policies are instantiated based on config.
- **State export/import**: Policies and controller implement `export_state()` / `import_state()` so hot-reload preserves EMA accumulators and cooldown timestamps.
- **Gate chain**: `SchedulingController` composes multiple deferral conditions; adding a new gate means adding a method that returns `(allowed: bool, reason: str)`.
- **Tag vector space**: All playlists and policy outputs live in the same sparse tag space. Adding a new signal means defining new tag keys and updating the relevant policy — no changes to `Matcher`.

## Runtime Artifacts

| Path | Purpose |
|------|---------|
| `scheduler_config.json` | Main config (hot-reloaded on change) |
| `state.json` | Persisted pause/playlist state |
| `logs/scheduler.log` | Rotating log (5 MB × 3 backups) |
| `history.jsonl` | Append-only event log |

Logger hierarchy: root `WEScheduler` → children `WEScheduler.Core`, `.Policy`, `.Sensor`, `.Tray`, etc. (`utils/logger.py`).

## Platform Notes

- Windows-only: uses `win32gui`, `win32process`, `win32api` (pywin32), and DPI awareness APIs in `main.py`.
- `utils/app_context.py` resolves the app root correctly for both source and PyInstaller bundle (`sys._MEIPASS`).
- `misc/` scripts are standalone utilities, not part of the packaged app.
