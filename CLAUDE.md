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
- Each policy's `_compute_output()` returns a `PolicyOutput(direction, salience, intensity)` dataclass. The base `Policy.get_output()` L2-normalizes `direction` before returning.
- Contribution to the env vector: `direction * salience * intensity * weight_scale`
- `ActivityPolicy`: dual EMA tracks — direction EMA (raw un-normalized vector) + scalar magnitude EMA. `intensity = magnitude_ema`; direction is normalized by base class. Transitions between tags (e.g. `#focus` → `#chill`) smooth the direction without norm dip.
- `TimePolicy` / `SeasonPolicy`: Hann window over the 24h / 365d cycle. `salience` = Hann peak value (clarity of current period); `intensity` = 1.0 always.
- `WeatherPolicy`: raw tag vector per OWM code encodes both type and severity. `intensity` = L2 norm of raw vector (T1≈0.25 → T4=1.0); `direction` = normalized; `salience` = 1.0.
- `Matcher` aggregates all `PolicyOutput`s, applies `TagSpec` fallback on unknown tags, then cosine-matches against pre-normalized playlist vectors. Returns `MatchResult`.

**Act** (`core/controller.py` + `core/actuator.py` + `core/executor.py`):
- `SchedulingController` is a gate chain: blocks switching if CPU > threshold, fullscreen app active, or cooldown not elapsed. Receives `MatchResult`; `similarity_gap` and `max_policy_magnitude` are available for future dynamic cooldown logic.
- `Actuator` calls `WEExecutor` which wraps `wallpaper64.exe -control openPlaylist -playlist <name>`
- All events are appended to `history.jsonl`

**Orchestration** (`core/scheduler.py`):
- Manages pause/resume state (timed or indefinite), persisted to `state.json`
- Hot-reloads `scheduler_config.json` on file change; policies/controller export and re-import transient state across reloads
- Exposes `on_auto_resume` hook for tray sync

**Tray UI** (`core/tray.py`): pystray + tkinter dialogs; reads OS locale via `utils/i18n.py` to serve zh/en strings.

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

- **Registry + Factory**: `_SENSOR_REGISTRY` / `_POLICY_REGISTRY` dicts + `create()` classmethods control which sensors/policies are instantiated based on config.
- **State export/import**: Policies and controller implement `export_state()` / `import_state()` so hot-reload preserves EMA accumulators and cooldown timestamps.
- **Gate chain**: `SchedulingController` composes multiple deferral conditions; adding a new gate means adding a method that returns `(allowed: bool, reason: str)`.
- **Tag vector space**: Playlists, policy directions, and fallback edges share one flat tag namespace (e.g. `#focus`, `#rain`). Adding a new signal means defining new tag keys, updating the relevant policy, and optionally adding `TagSpec` fallback entries — no changes to `Matcher`.
- **`config_key` validation**: Each `Policy` subclass declares `config_key: ClassVar[str]` matching an attribute on `PoliciesConfig`. `__init_subclass__` validates this at import time; typos raise `TypeError` before the app starts.

## Runtime Artifacts

| Path | Purpose |
|------|---------|
| `scheduler_config.json` | Main config (hot-reloaded on change) |
| `state.json` | Persisted pause/playlist state |
| `logs/scheduler.log` | Rotating log (5 MB × 3 backups) |
| `history.jsonl` | Append-only event log (top-5 tags per switch) |

Logger hierarchy: root `WEScheduler` → children `WEScheduler.Core`, `.Policy`, `.Sensor`, `.Tray`, etc. (`utils/logger.py`).

## Platform Notes

- Windows-only: uses `win32gui`, `win32process`, `win32api` (pywin32), and DPI awareness APIs in `main.py`.
- `utils/app_context.py` resolves the app root correctly for both source and PyInstaller bundle (`sys._MEIPASS`).
- `misc/` scripts are standalone utilities, not part of the packaged app.
