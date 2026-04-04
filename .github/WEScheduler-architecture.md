# Context-Aware Wallpaper Engine Scheduler — Architecture Notes

**Repo:** `e:\github\Context-Aware-Wallpaper-Engine-Scheduler`
**Python:** 3.11+ **Build:** `scripts/build.bat` → `dist/WEScheduler.exe` (PyInstaller 6.18.0)

## Sense-Think-Act Loop

```
Sensors → ContextManager → Arbiter (weighted sum) → Matcher (cosine similarity) → Actuator → WEExecutor
```

## Policy Normalization Table

| Policy         | Normalization     | Notes                                          |
| -------------- | ----------------- | ---------------------------------------------- |
| TimePolicy     | L2 + weight_scale | 4 peaks: dawn/day/sunset/night, H=6h           |
| SeasonPolicy   | L2 + weight_scale | 4 peaks: spring/summer/autumn/winter, H≈91.25d |
| ActivityPolicy | None (EMA decay)  | norm decays with activity level                |
| WeatherPolicy  | None (intensity)  | T1=0.2 / T2=0.5 / T3=0.8 / T4=1.0              |

## Key Module-Level Helpers (core/policies.py)

- `_hann(d, H)` — Hann window weight at distance d from peak, half-width H
- `_circular_distance(a, b, period)` — circular axis distance (e.g. midnight wrap)

## WeatherPolicy

- `_ID_TAGS: dict[int, tuple[str, float]]` — full OWM code 200–804 mapping
- `_MAIN_FALLBACK` — fallback by `main` field for unknown codes
- Returns `{tag: intensity * weight_scale}` (no L2 norm)
- Config: `request_timeout` (was hardcoded `timeout`)

## DisturbanceController Constants (core/controller.py)

```python
_DEFAULT_IDLE_THRESHOLD  = 60    # sec
_DEFAULT_PLAYLIST_MIN    = 1800  # sec
_DEFAULT_PLAYLIST_FORCE  = 14400 # sec
_DEFAULT_WALLPAPER_MIN   = 600   # sec
```

## Matcher (core/matcher.py)

- `_MIN_SIMILARITY = 0.001` — returns None if all playlists below threshold

## Logging Convention

`logging.getLogger("WEScheduler.<SubName>")` — hierarchical naming

## Config Conventions

- `switch_on_start` lives inside `disturbance` block
- All UI text via `utils/i18n.py` `t(key)`
- `scheduler.pause(seconds=None)` — None = indefinite

## Tray ↔ Scheduler Sync

- `scheduler.on_auto_resume = tray._sync_icon` (simple callable hook, not observer)
- Non-menu state changes require manual `icon.update_menu()` (Win32 HMENU cache)
- Menu-item callbacks auto-call `update_menu()` via pystray `_handler` wrapper
