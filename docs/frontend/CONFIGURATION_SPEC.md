# Configuration System Spec

本文档定义当前配置系统的产品定位、文件结构、运行时契约和工具边界。它取代冻结的 `CONFIG_EDITOR_*` 文档作为配置方向的最高优先级文档。

## 0. 实施状态（2026-05-15）

当前配置系统已经切到文本配置主线：

- 运行时配置事实源是外部 `config/` 目录中的 6 个固定 YAML 文件。
- `ConfigLoader` 读取 YAML，先做每文件 schema 校验，再做跨文件校验，最后产出 normalized `SchedulerConfig`。
- Dashboard HTTP 层只服务 Diagnostics：`GET /api/health` 和 `GET /api/analysis/window`。
- 配置辅助入口是 `Config Tools.bat` / `WEScheduler.exe config`，不启动 scheduler runtime，也不启动 Dashboard。
- Tray 已提供 `Apply Current Match Now` / `立即应用当前匹配`，用于用户明确请求的一次性手动调度。

## 1. 产品定位

本项目面向高级 Wallpaper Engine 用户。配置体验的目标不是让用户完全不接触配置，而是让用户能用可读、可校验、可分层的文本文件表达复杂调度规则。

正式目标：

- 使用 YAML 降低括号和引号带来的手写成本。
- 使用固定文件拆分降低单文件深层嵌套带来的认知负担。
- 保留高级用户可审阅、可复制、可版本管理的文本工作流。
- 保留 Pydantic 作为 schema、字段默认值、normalize 和错误定位的事实源。
- 让配置重载失败时不破坏当前运行中的有效配置。

非目标：

- 不做完整表单式 Config Editor。
- 不面向纯小白用户设计一键式配置向导。
- 不实现通用 Wallpaper Engine 管理器。
- 不实现 `include` 或任意拆分文件能力。
- 不在 Diagnostics 中放置手动副作用按钮。
- 不把 History 扩展成独立长期分析产品。

## 2. 配置目录结构

推荐配置目录：

```text
config/
  scheduler.yaml
  playlists.yaml
  tags.yaml
  activity.yaml
  context.yaml
  scheduling.yaml
```

运行时固定读取这 6 个文件，缺少任一文件都是 validate error。Release zip 应附带完整 example 配置文件，用户从这些普通文件复制和修改。

`scheduler.yaml` 不承担 `include` 入口。YAML anchors、aliases 和 merge keys 允许作为单文件书写辅助；它们会先由 YAML 解析器展开，再进入同一套 schema 与 cross-file 校验。

## 3. 文件契约

### 3.1 `scheduler.yaml`

入口文件，负责配置版本和 runtime 字段。

```yaml
version: 2

runtime:
  wallpaper_engine_path: null
  language: null
```

规则：

- `version` 必填且必须为 `2`。缺失或不是 `2` 时 validate 失败。
- `runtime.wallpaper_engine_path: null` 表示由应用自动检测 Wallpaper Engine 路径。
- `runtime.wallpaper_engine_path` 如果是非空字符串，必须指向存在的可执行文件；无效路径是 validate error。
- 自动检测成功只影响当前 runtime，不自动写回 `scheduler.yaml`。
- 自动检测失败时启动 / reload 失败。

### 3.2 `playlists.yaml`

定义 Wallpaper Engine 播放列表与 tag vector。

`playlists` 的 key 就是 Wallpaper Engine 播放列表名，也是调度器内部 playlist id。不再使用独立 `name` 或 `we_name` 字段。

```yaml
playlists:
  BRIGHT_FLOW:
    display: 日光流动
    color: amber
    tags:
      focus: 1.0
      day: 0.9
      clear: 0.3

  "Night Focus":
    display: 深夜专注
    color: 2e5f8a
    tags:
      focus: 1.0
      night: 0.9
```

规则：

- `display` 只作为 UI 展示名，不参与 Wallpaper Engine 调用。
- `tags` 表达播放列表和概念的亲和度比例。
- 播放列表名包含空格或特殊字符时，应显式加引号。
- 空 tag vector 允许存在，但只适合占位或逐步配置。

### 3.3 `tags.yaml`

定义完整 tag 词表和 fallback 图。所有被 playlist、activity、time、season、weather 引用或输出的 tag 都必须在这里声明。

```yaml
tags:
  dawn:
    fallback:
      day: 0.7
      chill: 0.3

  storm:
    fallback:
      rain: 1.0
```

tag id 使用无前缀 lower-kebab-case，例如 `focus`、`chill`、`deep-work`。不使用 `#focus` 这种形式。

固定 policy 输出 tag 也必须显式声明：

- TimePolicy：`dawn`、`day`、`sunset`、`night`
- SeasonPolicy：`spring`、`summer`、`autumn`、`winter`
- WeatherPolicy：`clear`、`cloudy`、`rain`、`storm`、`snow`、`fog`

### 3.4 `activity.yaml`

定义前台进程 / 标题到 tag 的映射。`process` 与 `title` 是简写入口，加载后会 normalize 成统一 matcher。

```yaml
activity:
  enabled: true
  weight: 1.2
  smoothing_window: 120

  process:
    Code: focus
    Obsidian: focus
    steam: chill

  title:
    GitHub: focus
    YouTube: chill

  matchers:
    - source: title
      match: regex
      pattern: "^GitHub .* Actions$"
      tag: focus
      case_sensitive: false
```

规则：

- 单条 activity matcher 只输出一个 tag。
- 不支持单规则 weight / confidence；ActivityPolicy 的整体强弱由 `activity.weight` 和 EMA 时序分布承担。
- `process` 简写默认 `match: exact`，并支持 `.exe` 等价：`Code` 可匹配 `Code.exe`。
- `.exe` fallback 只用于 process exact，不用于 contains 或 regex。
- `title` 简写默认 `match: contains`。
- 完整 `matchers` 支持 `source: process | title` 与 `match: exact | regex | contains`。
- matcher 默认大小写不敏感；完整 matcher 可用 `case_sensitive: true` 覆盖。
- 匹配优先级为 source `title > process`。
- 同一 source 内匹配类型优先级为 `exact > regex > contains`。
- literal pattern 同类型多条命中时，更长 pattern 优先；长度相同按配置声明顺序。
- regex 多条命中时按配置声明顺序。

### 3.5 `context.yaml`

定义 time、season、weather 三类上下文策略。

```yaml
time:
  enabled: true
  weight: 0.8
  auto: true
  day_start_hour: 8
  night_start_hour: 20

season:
  enabled: true
  weight: 0.65
  spring_peak: 80
  summer_peak: 172
  autumn_peak: 265
  winter_peak: 355

weather:
  enabled: true
  weight: 1.5
  api_key: ""
  lat: 0.0
  lon: 0.0
  fetch_interval: 600
  warmup_timeout: 3
  request_timeout: 10
```

### 3.6 `scheduling.yaml`

定义动作门控、冷却和运行时调度参数。

```yaml
scheduling:
  startup_delay: 15
  idle_threshold: 20
  switch_cooldown: 150
  cycle_cooldown: 900
  force_after: 3600
  cpu_threshold: 85
  cpu_sample_window: 10
  pause_on_fullscreen: true
```

## 4. 颜色规则

颜色是可选字段，只服务于 Diagnostics / UI 配色，不应成为用户必须配置的字段。

推荐输入：

```yaml
color: amber
```

或无 `#` 十六进制：

```yaml
color: f5c518
```

兼容但不主推：

```yaml
color: "#F5C518"
```

运行时 normalize 为 `#RRGGBB`。如果缺省，则按内置 palette 自动分配。

## 5. Runtime 边界

YAML 配置不是运行时直接消费的模型。运行时消费 normalized `SchedulerConfig`。

配置加载流程：

1. 读取 `scheduler.yaml`。
2. 固定读取其余 5 个 YAML 文件。
3. 每文件通过 Pydantic schema 校验。
4. 执行跨文件校验：WE 路径解析、未知 tag、固定 policy 输出 tag、playlist color 等。
5. 通过 Pydantic runtime schema 产出 normalized `SchedulerConfig`。
6. 校验失败时返回 source file、field path、message 和 code。

Pydantic schema defaults 只用于字段级默认值，例如 policy `enabled`、调度参数或可选字段默认值。它不提供隐藏 playlist、tag、activity rule 或 policy layer。

## 6. Wallpaper Engine 路径解析

`runtime.wallpaper_engine_path` 的语义：

- `null`：配置有效，启动 / reload 时尝试自动检测 Wallpaper Engine 路径。
- 非空字符串：必须指向存在的可执行文件，否则 validate 失败。

自动检测规则：

- 检测成功后，runtime 使用检测到的路径。
- 检测成功不自动写回 YAML。
- 检测失败时启动 / reload 失败。
- 显式路径无效时不 fallback 自动检测，因为这会隐藏用户配置错误。
- Executor 只接收已解析的 exe 路径，并以简单成功 / 失败语义返回执行结果。
- 只有真实执行成功后，Actuator 才能更新 active playlist 和 controller cooldown。

## 7. Reload 行为

Reload 必须 validate before swap。失败时旧 runtime 完全保留。

成功 reload 时全量重建 runtime components，但允许迁移以下状态：

- pause / pause_until。
- current playlist 字符串，即使它已不在新 playlist map 中；下一 tick 按正常调度逻辑切走。
- controller `last_playlist_switch_time` 和 `last_wallpaper_switch_time`。
- ActivityPolicy EMA 压缩状态。

ActivityPolicy EMA 导入规则：

- 新配置中 ActivityPolicy 仍启用时，保留当前 `_dir_ema` / `_mag_ema`。
- 导入时过滤掉新 tag vocabulary 中不存在的 tag。
- `smoothing_window` 变化时，不重置 EMA；新的 alpha 从后续 tick 开始生效。

不迁移：

- 已删除 policy 的 state。
- matcher 派生结果或 playlist score 缓存。
- executor path resolved 状态；reload 后重新 resolve。

Reload Config 是配置操作，不是调度操作。Reload 成功后永不主动 switch 或 cycle；下一次自动 tick 仍受 cooldown、idle、fullscreen、CPU 等 gate 约束。

## 8. 配置辅助工具

`WEScheduler.exe config` 和 `Config Tools.bat` 提供轻量离线 numbered TUI：

```text
1. Validate config
2. Detect Wallpaper Engine
3. Scan Wallpaper Engine playlists
q. Exit
```

工具边界：

- 不创建 `WEScheduler`。
- 不启动调度循环。
- 不启动 Dashboard / Diagnostics。
- 不写回 YAML。
- 不自动修复配置。

菜单行为：

- Validate config：使用与启动 / reload 同一套 `ConfigLoader` 校验。成功时输出 `OK`、config folder path、resolved WE path、playlist count、enabled policies。失败时输出 source file、field path、message、code。
- Detect Wallpaper Engine：显示 configured value、resolved executable path、Wallpaper Engine `config.json` 是否找到。不启动 Wallpaper Engine。
- Scan Wallpaper Engine playlists：从 Wallpaper Engine `config.json` 读取播放列表名，输出纯名称列表和 copy-ready `playlists.yaml` snippet。不自动生成 tag、color 或 display name。

## 9. Diagnostics 与 API 边界

Dashboard / WebView 产品语义是 Diagnostics-only。它负责解释近期调度 tick，不承担配置编辑、配置辅助、长期 History 或手动副作用控制台职责。

当前 Dashboard HTTP API：

- `GET /api/health`
- `GET /api/analysis/window`

如果未来需要在 Diagnostics 中展示配置相关状态，应以只读诊断信息为主，例如当前 config folder path、最近一次 reload 结果或最近错误摘要；不要恢复完整表单编辑器。

## 10. Tray 手动调度入口

Tray 提供 `Apply Current Match Now` / `立即应用当前匹配`。

语义：

- 用户希望“按当前上下文执行一次切换判断”。
- 它是手动调度动作，不是配置 reload 的副作用。
- 只放 tray，不放 Diagnostics。
- 如果 best playlist 与 current playlist 不同，执行 playlist switch。
- 如果 best playlist 与 current playlist 相同，执行 wallpaper cycle。
- 如果 no match，不执行副作用并记录原因。
- 手动 apply 绕过自动调度 gates，包括 cooldown、idle、fullscreen、CPU。
- 手动 apply 仍受硬条件限制，例如 executor command failed。
- Scheduler paused 时允许执行，但不取消 paused。
- 成功后按真实副作用更新 current playlist 和 controller timestamps。

## 11. Release 布局

Release zip / `dist/` 应包含：

```text
WEScheduler.exe
Config Tools.bat
config/
  scheduler.yaml
  playlists.yaml
  tags.yaml
  activity.yaml
  context.yaml
  scheduling.yaml
README.md
```

`config/` 是普通外部文件，不是 exe 内嵌资源。用户可以直接复制、编辑、版本管理这些文件。

## 12. 验收标准

实现完成后至少满足：

1. 用户可以只修改 `playlists.yaml` 或 `activity.yaml`，不需要打开完整配置树。
2. 用户可以使用注释、缩进和无括号的 YAML 常规书写体验。
3. tag 不使用 `#` 前缀。
4. playlist key 直接对应 Wallpaper Engine 播放列表名。
5. 缺省颜色会自动分配；手写颜色可以使用命名色、无 `#` hex 或 `#RRGGBB`。
6. 6 个固定 YAML 文件缺失时能给出明确 validate error。
7. 未声明 tag 在任何引用处都会 validate 失败。
8. ActivityPolicy 支持 process/title 简写和完整 matcher，且匹配优先级可解释。
9. 配置错误能定位到具体 source file 和 field path。
10. reload 失败时，调度器继续使用上一次有效配置。
11. reload 成功后保留 pause、current playlist、controller cooldown 和过滤后的 ActivityPolicy EMA。
12. `wallpaper_engine_path: null` 能触发自动检测；检测失败时启动 / reload 失败。
13. 内部运行时使用 Pydantic normalized `SchedulerConfig`。
14. Release zip 中包含 example config 和 `Config Tools.bat`。
15. Diagnostics 不重新承载 Config Editor、配置辅助面板或独立 History 页面。
