# Changelog

All notable changes to Context-Aware Wallpaper Engine Scheduler are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.6.0] — 2026-04-29

**History R3 + DIP Architecture**

此版本实现了完整的历史事件日志系统与 Dashboard History 标签页，并对核心架构进行了依赖注入重构。

### Added

- **`HistoryLogger`** (`utils/history_logger.py`): 线程安全的追加型事件日志，按月分片为 `history-{YYYY}-{MM}.jsonl`。UTC 时间戳、秒精度、字典序可比较。六种事件类型 tagged union：`start` / `stop` / `pause` / `resume` / `playlist_switch` / `wallpaper_cycle`。
- **`/api/history`** 端点: 返回 `{segments, events}`，后端计算连续时间线区块（Gantt-ready）。支持 `limit` / `from` / `to` 查询参数。
- **`/api/ticks`** 端点: 返回最近 N 个 `TickState` 快照的环形缓冲区（默认 300，5s 轮询）。
- **`HistoryView.vue`**: ECharts Gantt 时间线 + 事件列表，支持预设时长过滤（1h/6h/24h/7d）与自定义日期范围。自动刷新通过 `last_event_id` 驱动。
- **`ConfidencePanel.vue`** 新增 sparkline: 基于 `/api/ticks` 数据的 48px 趋势线。
- **`DashboardView.vue`**: `el-tabs` 切换 Live / History 标签页。
- **`EventLogger` Protocol** (`core/event_logger.py`): 定义 `write()` / `read()` / `last_event_id` 接口，方向 `utils → core`。
- **`EventType` StrEnum**: `PLAYLIST_SWITCH` / `WALLPAPER_CYCLE` / `START` / `STOP` / `PAUSE` / `RESUME` — 全链路共享的事件类型枚举，消除 5 处字符串重复。
- **`display` 字段**: `PlaylistConfig` 新增可选 `display` 名（用于 CJK 显示名），scheduler 通过 `display_of` dict 解析。

### Changed

- **`WEScheduler.__init__`** 接受 `history_logger: EventLogger`（构造器注入替代属性赋值），消除 "set BEFORE initialize()" 时序依赖。
- **Registry 提取**: `POLICY_REGISTRY` 移至 `core/policies.py`，`SENSOR_REGISTRY` 移至 `core/sensors.py`。scheduler.py 不再持有注册表。
- **`Actuator`** 接受必需的 `history_logger`，inner functions (`_sorted_tags` / `_tag_dict`) 提升为模块级函数。
- **ECharts 注册**集中至 `src/plugins/echarts.ts`，消除组件间重复 `use()` 调用。
- **`read_recent()`** 使用 `itertools.islice(reversed(deque))` 实现 O(count) 拷贝。
- **`_months_in_range`** 生成区间内所有月份，修复跨月查询数据丢失。
- **`_build_segments`** 使用完整事件列表构建 Gantt 区块，limit 仅作用于返回数组。
- **`StateStore`** 支持 `read_recent(count)` 环形缓冲区读取。

### Fixed

- Gantt 图 `renderItem` 坐标提取错误（字符串索引 → 完整时间戳）。
- `evt.data.tags` 为 Object 而非 Array 导致的 `.slice()` TypeError。
- History 加载状态未在 HTTP 错误时重置（添加 `finally` 块）。
- `_ensure_file` 使用本地时间而非 UTC 计算月份。
- `fetchTicks` 无条件赋值导致不必要的 Vue 重渲染（添加变更检测）。
- `last_event_id` 自动刷新时的骨架屏闪烁（跳过 `showLoading`）。

---

## [0.5.1] — 2026-04-28

**Dashboard R1 完成**

### Added

- **Dashboard HTTP 服务器** (`ui/dashboard.py`): Bottle-based, `127.0.0.1:0`。端点: `/api/state` / `/api/health` / 静态 SPA。
- **Vue 3 SPA 前端** (`dashboard/`): TypeScript + Element Plus，1s 状态轮询，僵尸检测（3 次失败 → 5s 倒计时关闭），`?locale=` i18n 参数。
- **pywebview 窗口** (`ui/webview.py`): 从托盘独立子进程启动，WebView2 渲染。
- **`on_tick` hook**: `scheduler.on_tick(scheduler, context, result)` — 由 main.py 设置，每 tick 推送 `TickState` 至 `StateStore`。
- **`StateStore`**: 线程安全（`threading.Lock`），`update()` / `read()` API。
- **`TickState`** 数据类: 17 字段实时快照（playlist, similarity, gap, magnitude, top_tags, context 数据）。
- **`display` 名解析**: `display_of` dict 映射 playlist name → display name。
- **`last_event_id`**: TickState 携带的单调递增事件计数器，前端据此自动刷新。

### Changed

- **Tray refactor**: `on_show_dashboard` 回调通过属性赋值（无构造器注入）。
- 导入清理、目录结构整理、文档同步。

---

## [0.5.0] - 2026-04-26

**数值语义化重构 (Semantic Value Decomposition)**

此版本对 `tag: value` 中的 `value` 进行了全面的语义分解。此前，强度、显著性、方向权重三个不同维度的信息被混淆在单一浮点数中，导致隐式归一化契约、开发者认知负担高、以及信号强度信息在余弦相似度匹配中被丢弃等问题。

核心设计：将每个策略输出拆分为三个正交语义维度：

| 维度 | 类型 | 范围 | 含义 |
|---|---|---|---|
| `direction` | `Dict[str, float]` | L2 范数 = 1 | 信号的**种类**（是什么） |
| `salience` | `float` | [0, 1] | 类别归属的**清晰程度**（确定吗） |
| `intensity` | `float` | [0, 1] | 现象的**强烈程度**（有多强） |

策略对环境向量的贡献：`direction × salience × intensity × weight_scale`

### Added

- **`PolicyOutput` 数据类** (`core/policies.py`): 封装 direction / salience / intensity 三个正交维度，替代原来各策略返回的裸 `Dict[str, float]`。
- **`MatchResult` 新增字段** (`core/matcher.py`):
  - `similarity_gap: float` — 最优与次优播放列表的余弦相似度之差，衡量匹配的"决断力"。差距小时说明两个候选接近，控制器可据此采取更保守的策略。
  - `max_policy_magnitude: float` — 所有策略中最大的 `salience × intensity × weight_scale`，反映最强信号的整体强度。
- **`docs/SEMANTIC-REFACTOR-SPEC.md`**：完整的语义重构设计文档，包含语义模型定义、各策略映射表、12 项决策记录及迁移指南。
- **`docs/ROADMAP.md` R4 章节**：Controller 增强路线图，规划基于 `similarity_gap` 和 `max_policy_magnitude` 的动态 cooldown 机制。

### Changed

- **`Policy` 基类重构**：`_compute_tags()` → `_compute_output()`，子类返回 `PolicyOutput`；基类 `get_output()` 统一对 `direction` 做 L2 归一化，消除各策略自行决定是否归一化的隐式契约。
- **`ActivityPolicy` 双 EMA 轨道**：方向 EMA（对原始未归一化向量平滑后每 tick 重归一化） + 标量幅度 EMA（有匹配=1.0，无匹配→衰减至 0）。`intensity = magnitude_ema`。解决了旧行为从 `#focus` 切换到 `#chill` 时向量范数经历波谷的问题——新行为下范数保持稳定，方向平滑过渡。
- **`TimePolicy` / `SeasonPolicy` 语义映射**：`direction` = Hann 窗权重的 L2 归一化向量；`salience` = Hann 窗峰值（时段中心=1.0，过渡边界→0）；`intensity` = 1.0（时间信号始终存在，只有清晰度变化）。
- **`WeatherPolicy` 语义映射**：`direction` = 天气类型标签的 L2 归一化向量；`salience` = 1.0（天气代码含义明确）；`intensity` = 原始向量的 L2 范数（T1≈0.25 ~ T4≈1.0，直接反映物理严重程度）。
- **`Matcher` 聚合逻辑**：从简单的 `sum(weight_scale × raw_tags)` 改为 `sum(direction × salience × intensity × weight_scale)`。Fallback 解析在聚合后的 env_vector 上统一执行。
- **日志输出增强** (`core/scheduler.py`)：状态行新增 `gap=` 字段显示相似度差距；标签权重显示精度从 1 位提升至 2 位小数。
- **可视化工具同步更新** (`misc/sim_match.py`, `misc/vis_common.py`)：引入 `SimPolicyOutput` 和 `_contribute()` 函数，与生产代码语义保持一致。
- **配置参数微调**：`season.weight_scale` 0.6 → 0.65；`startup_delay` 30 → 15 秒。

### Removed

- **`docs/TODOS.md`**：已删除。其中的路线内容已合并至 `docs/ROADMAP.md`。

### Design Decisions

详见 `docs/SEMANTIC-REFACTOR-SPEC.md` 第 8 节，共 14 项决策记录，涵盖：播放列表值=亲和度、ActivityPolicy 双 EMA 设计、Fallback 强度传输、保留 `weight_scale` 作为策略优先级、方向由基类统一 L2 归一化、`similarity_gap` 与 `max_policy_magnitude` 传递给 Controller 供未来使用等。

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

[Unreleased]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.5.0...v0.5.1
[0.4.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/L1nexi/Context-Aware-Wallpaper-Engine-Scheduler/releases/tag/v0.1.0
