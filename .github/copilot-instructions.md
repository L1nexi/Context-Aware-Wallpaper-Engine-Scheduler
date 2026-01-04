# Context Aware WE Scheduler AI Instructions

## Big Picture Architecture

This project is a middleware for Wallpaper Engine (WE) that uses a **Sense-Think-Act** loop to switch wallpapers based on system context.

- **Sensors** ([core/sensors.py](core/sensors.py)): Collect raw data (active window, idle time).
- **ContextManager** ([core/context.py](core/context.py)): Orchestrates sensors and provides a unified context dictionary.
- **Policies** ([core/policies.py](core/policies.py)): Map context to tag weights (e.g., `#focus`, `#chill`).
  - `ActivityPolicy`: Uses **EMA (Exponential Moving Average)** to smooth high-frequency window changes.
  - Other policies (Time, Season, Weather): Use **L2 Normalization** to ensure fair weighting.
- **Arbiter** ([core/arbiter.py](core/arbiter.py)): Aggregates all policy outputs into a single weighted tag vector.
- **Matcher** ([core/matcher.py](core/matcher.py)): Uses **Cosine Similarity** (dot product of normalized vectors) to find the best matching playlist from `scheduler_config.json`.
- **DisturbanceController** ([core/controller.py](core/controller.py)): Implements **Opportunistic Switching**. It only allows switching when the user is idle or a minimum interval has passed to avoid interruptions.
- **WEExecutor** ([core/executor.py](core/executor.py)): Communicates with Wallpaper Engine via its CLI (`-control` commands).

## Critical Workflows

- **Configuration**: All rules and playlists are defined in [scheduler_config.json](scheduler_config.json). Use [scheduler_config.example.json](scheduler_config.example.json) as a template.
- **Execution**:
  - Foreground: `python main.py`
  - Background (Windows): `run_bg.bat` (uses `pythonw.exe`)
- **Testing**: Run tests using `pytest` or `python tests/test_core.py`.
- **Logging**: Logs are stored in `logs/scheduler.log` using a rotating file handler.

## Project Conventions

- **Tags**: Always start with `#` (e.g., `#focus`, `#night`).
- **Normalization**: Most policies should call `self._normalize_and_scale()` to ensure their output vector has a magnitude equal to `weight_scale`.
- **EMA**: `ActivityPolicy` is the exception; it does NOT use L2 normalization so that weights can decay to zero when no rules match.
- **Windows Specifics**: The project relies on Windows-specific APIs (via `psutil` and `pywin32` for window sensing) and Wallpaper Engine's Windows executable.

## Integration Points

- **Wallpaper Engine**: Controlled via `subprocess` calls to `wallpaper64.exe -control`.
- **OpenWeatherMap**: Used by `WeatherPolicy` if an API key is provided in the config.
