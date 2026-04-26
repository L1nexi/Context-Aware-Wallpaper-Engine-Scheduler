# Changelog

All notable changes to Context-Aware Wallpaper Engine Scheduler are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.5.0] - 2026-04-26

**数值语义化重构**

此版本对 `tag : value` 的 `value` 进行了全面的语义分解，提供了更明确的标签语义，控制隐式语义的使用，降低开发者心智负担。

### Refactored

- 对于 `playlists` 的的 `tag:value` 配置，明确 `value` 语义为 "亲和度"。
- 引入 `PolicyOutput` 数据类，用于封装包含方向、显著性和强度的策略输出。每个策略输出三个层面的信息：方向（`direction`）、显著性（`salience`）和强度（`intensity`）
- 更新 `Policy` 类方法，改为计算并返回 `PolicyOutput` 对象而非原始标签。
- 重构 `ActivityPolicy`、`TimePolicy`、`SeasonPolicy` 和 `WeatherPolicy` 以适配新的输出结构。
- 增强 `get_output` 方法，实现方向归一化及强度处理的优化。
- 调整 `WEScheduler` 的日志记录，在状态输出中包含相似度差距。
- 清理策略类中未使用的方法和注释，提升代码可读性。

### Added

- `docs/SEMANTIC-REFACTOR-SPEC.md`：新增语义重构设计文档，详细说明了数值语义化处理的设计原则。

### Changed

- `ActivityPolicy` 的行为改变：`ActivityPolicy` 的旧行为是对 `tag:value` 直接做 EMA 平滑。语义重构后，`ActivityPolicy` 对方向 `direction` 和强度 `intensity` 分别应用平滑。具体区别在于，从 `#focus` 应用转到 `#chill` 应用时，旧行为会导致范数经历波谷，而新行为下范数保持不变，方向由 EMA 平滑。

## [0.4.1] - 2026-04-24

### Refactored

- `Matcher` 返回 `MatchResult`， `Actuator` 和 `Scheduler` 接受 `MatchResult` ，增强类型安全。同时为 `Controller` 扩展保留空间。
- `TagSpec`：新增 `TagSpec` 数据类，替代原来 `Dict[str, float]` 的标签权重对。 `TagSpec` 目前额外携带 `Fallback` 链。
- `Tag` 的 `Fallback` 处理：放弃语义子向量处理，改为递归解析 `TagSpec.fallback` 链，直到找到一个在播放列表标签中存在的标签或能量消散。
- 启动错误逻辑由 `main` 移入 `tray`。

## [0.4.0] — 2026-04-21

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

| 旧字段名              | 新字段名                | 所在配置块          |
| --------------------- | ----------------------- | ------------------- |
| `we_path`             | `wallpaper_engine_path` | 顶层                |
| `disturbance`         | `scheduling`            | 顶层块名            |
| `min_interval`        | `switch_cooldown`       | `scheduling`        |
| `force_interval`      | `force_after`           | `scheduling`        |
| `wallpaper_interval`  | `cycle_cooldown`        | `scheduling`        |
| `cpu_window`          | `cpu_sample_window`     | `scheduling`        |
| `fullscreen_defer`    | `pause_on_fullscreen`   | `scheduling`        |
| `rules`               | `process_rules`         | `policies.activity` |
| `default_day_start`   | `day_start_hour`        | `policies.time`     |
| `default_night_start` | `night_start_hour`      | `policies.time`     |
| `interval`            | `fetch_interval`        | `policies.weather`  |

> **迁移方式**：参照 `scheduler_config.example.json` 重命名对应字段，或直接复制 example 后填入自己的值。

---

## [0.3.3] — 2026-04-20

**可维护性与鲁棒性重构**

### Added

- **`TimeSensor`**：将 `time.localtime()` 采集提取为独立 Sensor，写入 `context.time`，与其他 Sensor 一致。

### Refactored

- **传感器注册逻辑**：`ContextManager` 采用注册表驱动，`Sensor.create(config)` 工厂方法替代构造器直接调用；可选传感器（如 `WeatherSensor`）在 API key 未配置时返回 `None`，注册时跳过。
- **`DisturbanceController`**：拆分 CPU 门控与全屏门控为 `CpuGate` / `FullscreenGate` 类，暴露 `should_defer(context) → bool` 接口，Controller 持有 gate 链并线性调用。
- 状态导出/导入接口（`export_state` / `import_state`）添加至 Controller 与 Policy，为热重载状态保持奠定基础。

---

## [0.3.2] — 2026-04-20

**策略语义子向量重构**

### Changed

- **Policy 输出格式统一**：所有 Policy 的 `get_tags()` 返回 `List[Dict[str, float]]`（标签权重对列表），替代原来各 Policy 格式不一致的返回值；Arbiter 统一消费该格式。
- **WeatherPolicy 语义子向量**：OWM 天气码（200–804）映射至 `_ID_TAGS`，强度分 T1–T4 四级（0.2 / 0.5 / 0.8 / 1.0），无 L2 归一化，权重直接反映天气严重性。

---

## [0.3.1] — 2026-04-20

**Arbiter 移除 · TimePolicy 时间扭曲修复**

### Refactored

- **移除 `Arbiter` 层**：`Arbiter` 的加权聚合逻辑内聚至 `Matcher`，主循环简化为 `match(context)` 直接返回 `(aggregated_tags, best_playlist)`，消除冗余中间对象。
- **`TimePolicy` 线性时间扭曲 (Linear Time Warp)**：修复白天/夜晚时长不等时 Hann 窗分布不均匀的问题。引入时间轴扭曲，将非均匀的真实时间映射为均匀虚拟时间后再做插值，再映射回真实时间，确保峰值精确落在 `day_start_hour`/`night_start_hour`。

### Fixed

- `WeatherSensor` 请求失败时（如 401/403）`_cached` 为 `None`，导致每秒重试、忽视 `fetch_interval`。改为以 `_last_fetch` 计时，无论成功与否均严格等满间隔。

### Changed

- 日志格式优化：`[PLAYLIST] process(idle_time) >> tag1 w1 ■■ | tag2 w2 ■` 状态行格式固定，便于终端观察。

---

## [0.3.0] — 2026-04-09

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

## [0.2.2] — 2026-04-07

**misc/ 可视化与调优工具增强**

### Added

- `misc/` 新增过渡期热力图脚本，可视化 Policy 输出在一天/一年中的分布。
- `misc/` 可视化与调优工具整体优化，支持更灵活的参数输入。
- 更新 `scheduler_config.example.json`，与当前字段保持同步。

---

## [0.2.1] — 2026-04-06

**WeatherPolicy 调优 · misc/ 调试工具**

### Added

- `misc/` 新增 Policy 匹配情况模拟器与余弦相似度可视化脚本，用于离线调优播放列表标签权重。

### Changed

- 优化 `WeatherPolicy` 中 `#clear` 标签的强度曲线以及风暴标签权重，使晴天/恶劣天气的对比更明显。

---

## [0.2.0] — 2026-04-05

**系统托盘增强 · 国际化 · Policy 插值重构**

### Added

- **国际化 (i18n)**：支持简体中文 / English 双语，基于 `locale.getdefaultlocale()` 自动切换，所有 UI 文本通过 `t(key)` 查找。
- **启动时切换选项** (`switch_on_start`)：控制程序启动后是否立即执行一次壁纸切换。
- **按时段暂停**：托盘菜单支持预设时长暂停（30m / 2h / 12h / 24h / 48h）及自定义时长（tkinter 弹窗输入）。
- **自动恢复 hook** (`on_auto_resume`)：暂停到期后通过回调通知托盘图标刷新状态，支持亚分钟级状态显示更新。

### Changed

- **Policy 插值升级**：从线性插值改为 raised-cosine 插值（后续版本进一步改进为 Hann 窗），时段/季节标签过渡更平滑。
- **WeatherPolicy 细化**：更精细地利用 OWM 天气代码，区分细雨/中雨/暴雨等强度级别。
- `WeatherPolicy` 新增 `warmup_timeout`：首次请求使用短超时，避免冷启动阻塞。

### Fixed

- 托盘菜单文本（状态、Resume 可见性）在非菜单回调触发的状态变更后未刷新，现通过手动调用 `update_menu()` 修复。

### Refactored

- 清理 magic numbers，提取为具名常量；补全 `logging` 调用；归一化策略统一；补全类型注解。

---

## [0.1.0] — 2026-01-17

**初始发布**

### Added

- **Sense-Think-Act 调度循环**（1 s tick）：`ContextManager` 聚合多路 Sensor，`Matcher` 余弦相似度选 Playlist，`Actuator` 调用 WE CLI。
- **Sensor 感知层**：`WindowSensor`（前台进程/标题）、`IdleSensor`（Win32 鼠标/键盘空闲时长）、`CpuSensor`（滑动均值）、`WeatherSensor`（OWM 2.5 API）。
- **Policy 策略层**：`ActivityPolicy`（进程/标题 → 标签，EMA 平滑）、`TimePolicy`（Hann 窗时段插值）、`SeasonPolicy`（Hann 窗季节插值）、`WeatherPolicy`（OWM 天气码强度模型）。
- **DisturbanceController**：冷却时间 + 空闲检测 + 强制切换兜底，避免打扰用户。
- **系统托盘 (pystray)**：运行状态图标、右键菜单（Pause / Resume / Exit）。
- **WEExecutor**：封装 `wallpaper64.exe -control` CLI，支持 `openPlaylist` / `nextWallpaper`，进程存活检测与自动拉起。
- **JSON 配置驱动**：`scheduler_config.json` 定义播放列表标签权重与所有策略参数。
- **PyInstaller 打包**：`scripts/build.bat` 生成 `dist/WEScheduler.exe`。

---

[Unreleased]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/releases/tag/v0.1.0
