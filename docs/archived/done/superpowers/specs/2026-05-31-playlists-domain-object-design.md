# Playlists Domain Object Design

## Problem

Playlist 领域信息（display name、color、item_count、managed 集合）散落在多个组件中：

- **Actuator** 持有 `dict[str, PlaylistConfig]`，仅用于 `_select_target` 的 weighted random
- **Scheduler** 派生并持有 `display_of`、`color_of`、`managed_playlists`
- **Tray** 直接读 `scheduler.display_of`
- **Dashboard** 读 `scheduler.display_of` / `scheduler.color_of`
- **Matcher** 接收 `dict[str, PlaylistConfig]`
- **playlist_state.py** 接收 `managed_playlists: set[str]` 参数

这些是 Playlist 领域知识的泄露。应由专门的领域对象收拢。

## Solution

引入 `Playlists` 领域对象，两层设计：

- **类级**：`_configs: ClassVar[dict[str, PlaylistInfo]]` — 全量 registry，`configure()` 设置一次
- **实例级**：`_names: list[str]` — 持有特定 playlist 子集，保序

### Core API

```python
@dataclass(frozen=True)
class PlaylistInfo:
    display: str
    color: str
    item_count: int


class Playlists:
    _configs: ClassVar[dict[str, PlaylistInfo]] = {}

    def __init__(self, names: list[str]):
        self._names = list(names)

    @classmethod
    def configure(cls, configs: dict[str, PlaylistConfig]) -> None:
        """从 SchedulerConfig.playlists 构建 registry（不含 tags）。"""
        cls._configs = {
            name: PlaylistInfo(
                display=config.display or name,
                color=config.color,
                item_count=config.item_count,
            )
            for name, config in configs.items()
        }

    # 子集构造：Playlists(["A", "B"]) — 直接用构造器即可

    @classmethod
    def managed(cls) -> Playlists:
        """返回持有全部已配置 playlist 的实例。"""
        return Playlists(list(cls._configs.keys()))

    # 批量查询（实例持有的全部信息）
    def names(self) -> list[str]
    def displays(self) -> dict[str, str]
    def colors(self) -> dict[str, str | None]
    def item_counts(self) -> dict[str, int]

    @classmethod
    def is_managed(cls, name: str) -> bool:
        """name 是否在已配置的 playlist 中。"""
        return name in cls._configs

    # 选择逻辑：从 _names 中 weighted random by item_count
    def select_target(self) -> str
```

### Pipeline Type Flow

`Playlists` 作为领域对象贯穿核心管线：

```
Matcher.evaluate() → MatchEvaluation.best_playlists: Playlists
    → Controller.decide_action() → ControllerDecision.matched_playlists: Playlists
        → Actuator._act_from_decision() → matched.select_target()
```

各环节类型变更：

| 字段                                                | 原类型      | 新类型      |
| --------------------------------------------------- | ----------- | ----------- |
| `MatchEvaluation.best_playlists`                    | `list[str]` | `Playlists` |
| `ControllerDecision.matched_playlists`              | `list[str]` | `Playlists` |
| `ActuationOutcome.effective_playlists_before/after` | `list[str]` | `Playlists` |
| `PlaylistStateResolution.effective_playlists`       | `list[str]` | `Playlists` |
| `Actuator.act(effective_playlists)`                 | `list[str]` | `Playlists` |

DTO 和持久化层保留 `list[str]`（标识符），在管线边界处做 `Playlists ↔ list[str]` 转换。

### Component Migration

#### Scheduler (`core/scheduler.py`)

- `_RuntimeComponents`：移除 `display_of`、`color_of`、`managed_playlists`；保留 `playlist_configs: dict[str, PlaylistConfig]`（给 Matcher 和 configure）
- `_build_runtime_components`：Actuator 不再传 playlists；Matcher 仍用 `playlist_configs`
- `_install_runtime_components`：调用 `Playlists.configure(config.playlists)`；Scheduler 不持有 `self.playlists` / `self.managed_playlists`
- `_run_tick`：移除 `managed_playlists` 参数传递，`resolve_playlist_state` 内部直接用 `Playlists.is_managed()`
- `_update_status`：`self.display_of.get(...)` → `Playlists.managed().displays().get(...)`
- `SchedulerState.cached_playlists` 保留 `list[str]`（持久化）
- `_resolve_cached_playlists_after`：边界处 `Playlists → list[str]` 转换

#### Actuator (`core/actuator.py`)

- 构造函数移除 `playlists` 参数
- `_select_target` 方法删除
- `_act_from_decision`：`target = self._select_target(matched)` → `target = matched.select_target()`

#### Matcher (`core/matcher.py`)

- 构造函数改为接收 `playlist_configs: dict[str, PlaylistConfig]`（仍需要 tags）
- 内部逻辑不变

#### playlist_state.py

- 移除 `managed_playlists: set[str]` 参数
- `if playlist in managed_playlists` → `if Playlists.is_managed(playlist)`

#### Tray (`ui/tray.py`)

- `self.scheduler.display_of.get(...)` → `Playlists.managed().displays().get(...)`

#### Dashboard (`ui/dashboard_analysis.py`)

- `DashboardRuntimeMetadata` 移除 `display_of`/`color_of`
- `extract_runtime_metadata` 改为从 `Playlists.managed().displays()` / `Playlists.managed().colors()` 获取
- 或直接在 DTO 构建时调用

#### Diagnostics (`core/diagnostics.py`)

- `ActuationOutcome` 的 `effective_playlists_before/after` 改为 `Playlists`
- DTO 序列化时转为 `list[str]`

### File Changes Summary

| File                       | Action                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------- |
| `core/playlist.py`         | **新建** — `Playlists` 类 + `PlaylistInfo`                                                  |
| `core/scheduler.py`        | 移除 `display_of`/`color_of`/`managed_playlists`，`_install` 中调用 `Playlists.configure()` |
| `core/actuator.py`         | 移除 `playlists` 参数和 `_select_target`                                                    |
| `core/matcher.py`          | 参数重命名为 `playlist_configs`                                                             |
| `core/playlist_state.py`   | `managed_playlists` → `Playlists.managed()`                                                 |
| `core/diagnostics.py`      | `ActuationOutcome` 字段类型改为 `Playlists`                                                 |
| `ui/tray.py`               | 通过 `Playlists.managed()` 查询                                                             |
| `ui/dashboard_analysis.py` | 移除 `DashboardRuntimeMetadata`，改用 `Playlists.managed()`                                 |
| `tests/`                   | 更新所有涉及 `display_of`/`color_of`/`managed_playlists` 的测试                             |
