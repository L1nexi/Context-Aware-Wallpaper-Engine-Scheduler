# Changelog

All notable changes to Context-Aware Wallpaper Engine Scheduler are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.4.0] — 2026-04-21

**类型化架构重构 (Typed-Interface Refactor)**

此版本是一次纯工程质量升级，无新功能。重构范围覆盖配置层、策略层、控制层与状态层，消除了所有 `Dict`/`Any` 接口边界，实现全链路强类型。

### Refactored

- **Pydantic v2 全面迁移**：`AppConfig`、`PoliciesConfig`、`SchedulingConfig`、`PlaylistConfig` 等所有配置模型迁移至 Pydantic v2 `BaseModel`，启用 `model_config = ConfigDict(extra="forbid")`，非法字段在启动时立即报错。
- **`SchedulerState(BaseModel)`**：调度器持久化状态从裸 `dict` 升级为 Pydantic 模型，绑定 `load_state()` / `save_state()` 静态方法，消除散落的 JSON 读写逻辑。
- **`Policy.config_key: ClassVar[str]`** + **`__init_subclass__` 验证**：每个 Policy 子类在类定义时校验 `config_key` 是否存在于 `PoliciesConfig.model_fields`，配置键拼写错误在 import 时即抛 `TypeError`，不再等到运行时。
- **`Sensor.key: ClassVar[str]`** + **`register_sensor()` 验证**：`ContextManager.register_sensor()` 校验 `sensor.key` 是否为 `Context` dataclass 的合法字段，`_CONTEXT_FIELD_NAMES` 从 `dataclasses.fields(Context)` 在 import 时推导，`Context` 成为 sensor key 的唯一权威来源。
- **`Policy.__init__` 强类型化**：所有 Policy 子类的 `__init__` 从接受 `dict` 改为直接接受对应的 typed config 模型（`ActivityPolicyConfig`、`TimePolicyConfig` 等），消除内部 `.get()` 访问。
- **`Matcher.__init__(List[PlaylistConfig], List[Policy])`**：去除 `isinstance` 分支，参数类型完全确定。
- **`DisturbanceController` → `SchedulingController`**：类名与配置块名 `scheduling` 保持一致。
- **`context_types.py` 合并**：`WindowData`、`WeatherData`、`Context` 并入 `core/context.py`，删除 `context_types.py`，消除双文件维护负担。
- **`_hot_reload` 清理**：移除 `if self.matcher:` / `if self.actuator:` 多余 None 守卫（热重载仅在 `initialize()` 成功后调用，两者永远非 None）。

### Changed — 配置字段重命名

以下字段均有默认值，**不向后兼容**（旧字段名被 `extra="forbid"` 拒绝）：

| 旧字段名 | 新字段名 | 所在配置块 |
|---|---|---|
| `we_path` | `wallpaper_engine_path` | 顶层 |
| `disturbance` | `scheduling` | 顶层块名 |
| `min_interval` | `switch_cooldown` | `scheduling` |
| `force_interval` | `force_after` | `scheduling` |
| `wallpaper_interval` | `cycle_cooldown` | `scheduling` |
| `cpu_window` | `cpu_sample_window` | `scheduling` |
| `fullscreen_defer` | `pause_on_fullscreen` | `scheduling` |
| `rules` | `process_rules` | `policies.activity` |
| `default_day_start` | `day_start_hour` | `policies.time` |
| `default_night_start` | `night_start_hour` | `policies.time` |
| `interval` | `fetch_interval` | `policies.weather` |

> **迁移方式**：参照 `scheduler_config.example.json` 重命名对应字段，或直接复制 example 后填入自己的值。

---

## [1.3.3] — 2026-04-14

**可维护性与鲁棒性重构**

### Added

- **`TimeSensor`**：将 `time.localtime()` 采集提取为独立 Sensor，写入 `context.time`，与其他 Sensor 一致。

### Refactored

- **传感器注册逻辑**：`ContextManager` 采用注册表驱动，`Sensor.create(config)` 工厂方法替代构造器直接调用；可选传感器（如 `WeatherSensor`）在 API key 未配置时返回 `None`，注册时跳过。
- **`DisturbanceController`**：拆分 CPU 门控与全屏门控为 `CpuGate` / `FullscreenGate` 类，暴露 `should_defer(context) → bool` 接口，Controller 持有 gate 链并线性调用。
- 状态导出/导入接口（`export_state` / `import_state`）添加至 Controller 与 Policy，为热重载状态保持奠定基础。

---

## [1.3.2] — 2026-04-08

**策略语义子向量重构**

### Changed

- **Policy 输出格式统一**：所有 Policy 的 `get_tags()` 返回 `List[Dict[str, float]]`（标签权重对列表），替代原来各 Policy 格式不一致的返回值；Arbiter 统一消费该格式。
- **WeatherPolicy 语义子向量**：OWM 天气码（200–804）映射至 `_ID_TAGS`，强度分 T1–T4 四级（0.2 / 0.5 / 0.8 / 1.0），无 L2 归一化，权重直接反映天气严重性。

---

## [1.3.1] — 2026-03-31

**Arbiter 移除 · TimePolicy 时间扭曲修复**

### Refactored

- **移除 `Arbiter` 层**：`Arbiter` 的加权聚合逻辑内聚至 `Matcher`，主循环简化为 `match(context)` 直接返回 `(aggregated_tags, best_playlist)`，消除冗余中间对象。
- **`TimePolicy` 线性时间扭曲 (Linear Time Warp)**：修复白天/夜晚时长不等时 Hann 窗分布不均匀的问题。引入时间轴扭曲，将非均匀的真实时间映射为均匀虚拟时间后再做插值，再映射回真实时间，确保峰值精确落在 `day_start_hour`/`night_start_hour`。

### Fixed

- `WeatherSensor` 请求失败时（如 401/403）`_cached` 为 `None`，导致每秒重试、忽视 `fetch_interval`。改为以 `_last_fetch` 计时，无论成功与否均严格等满间隔。

### Changed

- 日志格式优化：`[PLAYLIST] process(idle_time) >> tag1 w1 ■■ | tag2 w2 ■` 状态行格式固定，便于终端观察。

---

## [1.3.0] — 2026-03-20

**感知增强与工程化**

### Added

- **A · FullscreenSensor + 全屏门控**：Win32 `SHQueryUserNotificationState` 检测 D3D 独占全屏、PPT 演示模式等场景，期间 defer 所有切换。可通过 `"pause_on_fullscreen": false` 关闭。
- **B · 配置热重载**：调度循环每 tick 检查 `scheduler_config.json` 的 `mtime`，文件保存后自动重建 Policy/Matcher/Controller，无需重启。
- **C · 操作统计 (`history.jsonl`)**：每次实际切换播放列表或轮播壁纸时，追加一条 JSON 记录，包含时间戳、事件类型、播放列表及 Top-5 标签快照。
- **D · WeatherSensor 拆分**：HTTP 请求逻辑从 `WeatherPolicy` 提取为独立 `WeatherSensor`，天气数据（含 `sunrise`/`sunset`）写入 `context.weather`，供多个 Policy 共享，消除重复请求。
- **E · TimePolicy 动态日出日落**：当 `WeatherSensor` 可用时，`TimePolicy` 自动从 OWM `sunrise`/`sunset` 推算本地小时，动态更新 `#dawn`/`#day`/`#sunset`/`#night` 峰值，无需手动配置。

### Refactored

- **Gate 封装 (`CpuGate` / `FullscreenGate`)**：`DisturbanceController` 中的门控 if-chain 提取为独立 Gate 类，暴露 `should_defer(context) → bool` 接口，链式调用，便于单独测试与扩展。

### Changed

- `disturbance` 块新增字段（均有默认值，向后兼容）：`"cpu_threshold": 85`、`"cpu_window": 10`、`"fullscreen_defer": true`
- `weather` 块新增字段：`"request_timeout": 10`
- `policies.time` 字段变更：新增 `auto` 字段；`day_start`/`night_start` 改为 `default_day_start`/`default_night_start`

---

## [1.1.2] — 2026-02-xx

请参阅对应 Git tag 的 commit 记录。

## [1.1.1] — 2026-02-xx

请参阅对应 Git tag 的 commit 记录。

## [1.1.0] — 2026-01-xx

请参阅对应 Git tag 的 commit 记录。

## [1.0.0] — 2026-01-xx

初始发布。

---

[Unreleased]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.3.3...v1.4.0
[1.3.3]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.1.2...v1.3.0
[1.1.2]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/releases/tag/v1.0.0
