# Configuration System Spec

本文档定义下一阶段配置系统的产品定位、文件结构、数据模型和工具边界。它取代 `CONFIG_EDITOR_SPEC.md` 作为配置方向的最高优先级文档。

## 0. 实施状态（2026-05-10）

当前配置系统仍以 `scheduler_config.json` 和 Pydantic `AppConfig` 为运行时事实源。`dashboard` 已经存在部分 Config Editor 路由和 General / Scheduling 页面，但产品方向已经收敛：

- 配置文件是一等入口。
- 完整 GUI Config Editor 暂停，不再作为当前主线。
- GUI 只保留配置辅助能力，例如打开配置、验证配置、重载配置、展示错误和扫描播放列表。
- 允许 breaking change，不以兼容旧 JSON 形状为目标。

若本文档与旧 `CONFIG_EDITOR_*` 文档冲突，以本文档为准。

## 1. 产品定位

本项目面向高级 Wallpaper Engine 用户。配置体验的目标不是让用户完全不接触配置，而是让用户能用可读、可校验、可分层的文本配置表达复杂调度规则。

正式目标：

- 降低 JSON 语法带来的出错概率。
- 降低单文件深层嵌套带来的认知负担。
- 保留高级用户可审阅、可复制、可版本管理的文本工作流。
- 保留 Pydantic 作为 schema、默认值、normalize 和错误定位的事实源。
- 让配置重载失败时不破坏当前运行中的有效配置。

非目标：

- 不做完整表单式 Config Editor。
- 不面向纯小白用户设计一键式配置向导。
- 不实现通用 Wallpaper Engine 管理器。
- 不为了兼容旧 JSON 结构保留长期双轨模型。
- 不提供旧 `scheduler_config.json` 到新 YAML 目录的自动迁移工具。
- 不做运行时 builtin preset + user override 模型。
- 阶段 2 不做 `include` 或任意拆分文件能力。

## 2. 格式选择

目标配置格式为受限 YAML。

采用 YAML 的原因：

- 支持注释。
- 少括号、少引号，更适合人手写。
- 与分层配置文件配合后，单个文件可以保持较短。

必须限制的 YAML 能力：

- 不支持 anchors、aliases、merge keys。
- 不鼓励复杂多行字符串。
- tag id 不使用 `#` 前缀，避免与 YAML 注释冲突。
- 解析后必须进入 Pydantic schema，不能把 YAML 解析结果直接当运行时配置。

## 3. 配置目录结构

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

阶段 2 固定读取这 6 个文件。打包产物应附带完整 example 配置，用户从 example 手动建立自己的配置目录。缺少任一文件都是 validate error；不因为文件缺失自动补齐，也不从旧 JSON 自动迁移。

### 3.1 `scheduler.yaml`

入口文件，负责配置版本和 runtime 字段。阶段 2 固定读取 6 个配置文件，不支持 `include`。

```yaml
version: 2

runtime:
  wallpaper_engine_path: null
  language: zh
```

规则：

- `version` 必填且必须为 `2`。缺失或不是 `2` 时 validate 失败。
- `runtime.wallpaper_engine_path: null` 表示由应用自动检测 Wallpaper Engine 路径。
- `runtime.wallpaper_engine_path` 如果是非空字符串，必须指向存在的可执行文件；无效路径是 validate error。
- 自动检测成功只影响当前 runtime，不自动写回 `scheduler.yaml`。
- 自动检测失败时配置本身仍可 valid，但 actuation disabled，Diagnostics / 配置辅助入口应显示 path unresolved。

### 3.2 `playlists.yaml`

定义 Wallpaper Engine 播放列表与 tag vector。

`playlists` 的 key 就是 Wallpaper Engine 播放列表名，也是调度器内部 playlist id。不再使用 `name` 或 `we_name` 字段。

```yaml
playlists:
  BRIGHT_FLOW:
    display: 日光流动
    color: amber
    tags:
      focus: 1.0
      day: 0.9
      dawn: 0.3
      clear: 0.3

  NIGHT_FOCUS:
    display: 深夜专注
    color: 2e5f8a
    tags:
      focus: 1.0
      night: 0.9
      clear: 0.2
```

如果 Wallpaper Engine 播放列表名包含空格或特殊字符，应显式加引号：

```yaml
playlists:
  "Night Focus":
    display: 深夜专注
    tags:
      focus: 1.0
      night: 0.9
```

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
    直播: chill

  matchers:
    - source: title
      match: regex
      pattern: "^GitHub .* Actions$"
      tag: work
      case_sensitive: false

    - source: process
      match: exact
      pattern: "Code - Insiders"
      tag: focus
```

规则：

- 单条 activity matcher 只输出一个 tag，不支持一条规则输出多个 tag。
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

weather:
  enabled: true
  weight: 1.5
  api_key: YOUR_OPENWEATHERMAP_API_KEY
  lat: null
  lon: null
  fetch_interval: 600
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

## 4. 旧字段到新文件的划分

本表只用于说明新模型如何承接旧概念，帮助用户手动重建配置；它不是自动迁移工具的实现承诺。

| 当前 JSON 字段 | 新配置位置 |
| --- | --- |
| `wallpaper_engine_path` | `scheduler.yaml` 的 `runtime.wallpaper_engine_path` |
| `language` | `scheduler.yaml` 的 `runtime.language` |
| `playlists[]` | `playlists.yaml` 的 `playlists.<WE playlist name>` |
| `tags` | `tags.yaml` |
| `policies.activity` | `activity.yaml` |
| `policies.time` | `context.yaml` 的 `time` |
| `policies.season` | `context.yaml` 的 `season` |
| `policies.weather` | `context.yaml` 的 `weather` |
| `scheduling` | `scheduling.yaml` |

## 5. 标识符规则

### 5.1 Playlist id

Playlist id 等于 Wallpaper Engine 播放列表名。

规则：

- 不再保留独立 `name` 字段。
- 不再引入 `we_name` 字段。
- `display` 只作为 UI 显示名，不参与 Wallpaper Engine 调用。
- 允许大小写、空格和下划线，因为这些来自 Wallpaper Engine 的真实播放列表名。
- 配置层和 runtime `AppConfig.playlists` 都使用 map；不要在 adapter 内长期转换回旧 list 事实源。

### 5.2 Tag id

Tag id 使用无前缀的 lower-kebab-case。

示例：

- `focus`
- `chill`
- `night`
- `rain`
- `deep-work`

正式规则：

- 不使用 `#focus` 这种前缀形式。
- 不做隐藏 builtin tag 词表；打包 example 可以提供推荐 tag 覆盖。
- 未知 tag 一律 validate 失败，避免拼写错误静默变成新 tag。
- playlist tag vector、activity matcher、tag fallback 都只能引用已声明 tag。
- Time / Season / Weather 输出固定 tag 名；这些固定 tag 也必须在 `tags.yaml` 中显式声明。

阶段 2 固定 policy 输出：

- TimePolicy：`dawn`、`day`、`sunset`、`night`
- SeasonPolicy：`spring`、`summer`、`autumn`、`winter`
- WeatherPolicy：`clear`、`cloudy`、`rain`、`storm`、`snow`、`fog`

## 6. 颜色规则

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

运行时应 normalize 为 `#RRGGBB`。如果缺省，则按内置 palette 自动分配。

## 7. Example Config + Schema Defaults

阶段 2 不做运行时 builtin preset + user override。正式模型是：

```text
packaged example config
  -> user copies / edits YAML files
  -> load fixed 6 files
  -> Pydantic validation
  -> normalized runtime AppConfig
```

打包 example 是分发和文档资源，不是隐藏运行时 layer。用户运行时看到的 YAML 文件就是配置语义本身。

Pydantic schema defaults 仍然存在，但只用于字段级默认值，例如 policy `enabled`、调度参数默认值或可选字段默认值。它不提供隐藏 playlist、tag、activity rule 或 policy preset。

设计约束：

- 运行时只读取用户配置目录中的固定 6 个 YAML 文件。
- 不读取 packaged example 作为 fallback。
- 不读取旧 `scheduler_config.json`。
- 不做 include、deep merge、override 删除语义等配置层能力。
- 禁用资源或策略使用显式 `enabled: false`。

## 8. Runtime 边界

YAML 配置不是运行时直接消费的模型。运行时继续消费 normalized `AppConfig`。

配置加载流程：

1. 读取 `scheduler.yaml`。
2. 固定读取 `playlists.yaml`、`tags.yaml`、`activity.yaml`、`context.yaml`、`scheduling.yaml`。
3. 将 YAML domain model 转换成 runtime schema 可接受的 raw dict。
4. 通过 Pydantic 校验并 normalize。
5. 校验通过后替换当前运行配置。
6. 校验失败时保留旧配置，并记录 / 展示错误。

### 8.1 Wallpaper Engine 路径解析

`runtime.wallpaper_engine_path` 的语义：

- `null`：配置有效，启动 / reload 时尝试自动检测 Wallpaper Engine 路径。
- 非空字符串：必须指向存在的可执行文件，否则 validate 失败。

自动检测规则：

- 检测成功后，runtime 使用检测到的路径。
- 检测成功不自动写回 YAML。
- 检测失败不应导致托盘宿主退出，但 actuation disabled。
- 执行器不应静默 no-op；执行命令必须返回明确结果，例如 success、path unresolved、start failed、command failed。
- 只有真实执行成功后，Actuator 才能更新 active playlist 和 controller cooldown。

### 8.2 Reload 状态迁移

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

## 9. GUI 与工具边界

GUI 不承担完整配置编辑。

应保留或新增的辅助入口：

- Open Config Folder
- Reload Config
- Validate Config
- Show Last Config Error
- Open / View Example Config
- Scan Wallpaper Engine Playlists

正式要求：

- Reload 必须 validate before swap。
- 配置校验失败时不得替换当前有效配置。
- 错误信息必须指向具体文件和路径，例如 `playlists.yaml > playlists.NIGHT_FOCUS.tags.nigth`。
- Diagnostics 可以展示当前配置路径、最后一次 reload 时间和最后一次 reload 结果。
- Reload 成功后不自动触发 playlist switch 或 cycle。

### 9.1 Tray 手动调度入口

Tray 后续应提供 `Apply Current Match Now` / `立即应用当前匹配`。

语义：

- 这是用户明确请求“按当前上下文执行一次调度判断”。
- 只放 tray，不放 Diagnostics，避免 Diagnostics 变成副作用控制台。
- 如果 best playlist 与 current playlist 不同，执行 playlist switch。
- 如果 best playlist 与 current playlist 相同，执行 cycle。
- 如果 no match、WE path unresolved 或 executor command failed，则不伪装成功。
- 手动 apply 绕过所有 controller gates，包括 cooldown、idle、fullscreen、CPU。
- 手动 apply 在 scheduler paused 时允许执行，但不取消 paused。
- 手动 apply 成功后按真实副作用更新状态：switch 更新 playlist / wallpaper timestamps，cycle 更新 wallpaper timestamp。
- Reload Config 永不自动触发 manual apply。

## 10. API 方向

旧 `/api/config` 的完整 GUI 编辑契约不再是当前主线。后续配置相关 API 应优先服务文本配置工作流：

- 获取当前 normalized config，用于 Diagnostics 展示。
- 执行 validate。
- 执行 reload。
- 获取最近一次配置错误。
- 扫描 Wallpaper Engine 播放列表。
- 检测 Wallpaper Engine 路径，并返回来源和错误状态。
- 打开配置目录或返回配置目录路径。

如果保留现有 `GET /api/config` / `POST /api/config`，应明确标记为 legacy editor support 或内部工具接口，不应继续以完整 Config Editor 为产品目标扩展。

## 11. 实施顺序

配置运行时核心建议先落地：

1. 定义固定 6 文件 YAML loader 和 source location 错误模型。
2. 引入 tag id 与 playlist id breaking change。
3. 将 playlist 从 array 语义改为 config + runtime map 语义。
4. 将 ActivityPolicy 改为简写入口 + normalized matcher 模型。
5. 将固定 YAML domain model 转换为 runtime `AppConfig`。
6. 接入 WE path resolve、executor readiness 和 actuation outcome。
7. 接入 validate before swap reload，并迁移允许保留的 runtime state。
8. 更新打包 example 配置、README 和测试。

后续可分步落地：

1. 将 GUI Config Editor 入口降级为配置辅助工具入口。
2. 实现 tray `Apply Current Match Now`。
3. 清理或冻结旧 Config Editor 文档和未完成页面。

## 12. 验收标准

实现完成后至少满足：

1. 用户可以只修改 `playlists.yaml` 或 `activity.yaml`，不需要打开完整配置树。
2. 用户可以使用注释、缩进和无括号的 YAML 常规书写体验。
3. tag 不再使用 `#` 前缀。
4. playlist key 直接对应 Wallpaper Engine 播放列表名。
5. 缺省颜色会自动分配；手写颜色可以使用命名色或无 `#` hex。
6. 6 个固定 YAML 文件缺失时能给出明确 validate error。
7. 未声明 tag 在任何引用处都会 validate 失败。
8. ActivityPolicy 支持 process/title 简写和完整 matcher，且匹配优先级可解释。
9. 配置错误能定位到具体文件和字段路径。
10. reload 失败时，调度器继续使用上一次有效配置。
11. reload 成功后保留 pause、current playlist、controller cooldown 和过滤后的 ActivityPolicy EMA。
12. `wallpaper_engine_path: null` 能触发自动检测；检测失败时 actuation disabled 但宿主不退出。
13. 内部运行时仍使用 Pydantic normalized `AppConfig`。
14. 打包 example 配置能通过 validate 并启动调度器。

## 13. 访谈决策记录（2026-05-10）

本节记录阶段 2 细化讨论中已经定下的实现取舍。后续实现、拆任务或代码审查时，优先按这些结论执行，避免重复讨论已收敛的问题。

### 13.1 分发、旧配置和第一批实现边界

- 不提供旧 `scheduler_config.json` 到新 YAML 目录的自动迁移工具。
- 旧 JSON 不参与运行时加载、不参与自动转换、不作为 fallback。
- 旧字段对照表只帮助用户手动重建配置，不是迁移工具承诺。
- 打包产物直接附带完整 example 配置。用户从 example 复制和修改，建立自己的配置目录。
- 不需要在启动时根据旧 JSON 生成 starter config。
- 阶段 2 可以分步实现。第一批先完成配置运行时核心：
  - 固定 6 文件 YAML loader。
  - playlist config + runtime map。
  - 严格 tag 声明。
  - Activity matcher 新模型。
  - `wallpaper_engine_path: null` 自动检测语义。
  - validate before swap reload。
  - example config 与测试。
- Tray `Apply Current Match Now` 和 Dashboard 配置辅助收缩是后续独立任务，不阻塞第一批配置运行时核心落地。

### 13.2 配置加载契约

- 阶段 2 固定读取 6 个必需文件：
  - `scheduler.yaml`
  - `playlists.yaml`
  - `tags.yaml`
  - `activity.yaml`
  - `context.yaml`
  - `scheduling.yaml`
- 缺少任一文件都是 validate error。
- 不做 `include`。`scheduler.yaml` 不再承担 include 入口。
- 不做任意拆分文件能力。未来如确有需求，再单独设计 advanced include。
- `scheduler.yaml > version` 必填且必须为 `2`。
- 缺失 `version` 时 validate 失败。
- `version != 2` 时 validate 失败，并提示当前应用只支持 config version 2。
- 受限 YAML 必须禁止 anchors、aliases、merge keys。
- YAML 解析结果不能直接作为 runtime config，必须进入 Pydantic validation 和 normalization。

### 13.3 Runtime model、defaults 和来源追踪

- 不做运行时 builtin preset + user override 模型。
- Pydantic schema defaults 只用于字段默认值，例如 `enabled`、调度参数或可选字段。
- Pydantic defaults 不提供隐藏 playlist、tag、activity rule 或 policy preset。
- 成功加载后不保留字段级或 entity 级 provenance。
- Diagnostics 不需要解释“这个字段来自哪个配置文件”。它只需要展示当前配置目录、reload 状态和运行结果。
- Validate error 必须尽量带 source file 与字段路径，例如 `activity.yaml > activity.matchers[0].tag`。
- 没有成功态 provenance 的前提下，validate 阶段必须严格拦截未知 tag、无效路径、缺文件和 schema 错误。

### 13.4 Playlist 模型

- `playlists.yaml` 使用 map。
- Runtime `AppConfig.playlists` 也改为 map。
- map key 就是 Wallpaper Engine 播放列表名，也是 playlist id。
- 不再保留独立 `name` 字段作为事实源。
- 不引入 `we_name` 字段。
- `display` 只用于 UI 展示，不参与 Wallpaper Engine 调用。
- 配置与 runtime 不应长期保留 “YAML map -> runtime list” 的双模型。
- 如果 reload 后 `current_playlist` 已不在新 playlist map 中，仍保留当前字符串，不额外标记 orphan。下一 tick 按正常调度逻辑切走。

### 13.5 Tag 模型和固定 policy 输出

- 所有 tag 必须显式声明在 `tags.yaml` 中。
- 未声明 tag 在任何引用处都 validate 失败。
- playlist tag vector、activity matcher、tag fallback 都只能引用已声明 tag。
- 不允许在 playlist 或 activity 中隐式创建 tag。
- 不做隐藏 builtin tag 词表。
- 打包 example 应提供完整推荐 tag 覆盖，降低用户新增 tag 的负担。
- `tags.yaml` 是完整 tag 词表和 fallback 图。
- tag fallback 是重要自定义扩展点，必须支持用户自定义。
- Time / Season / Weather 在阶段 2 输出固定 tag 名，不做 signal-to-tag mapping。
- 固定 policy 输出 tag 也必须在 `tags.yaml` 中声明：
  - TimePolicy：`dawn`、`day`、`sunset`、`night`
  - SeasonPolicy：`spring`、`summer`、`autumn`、`winter`
  - WeatherPolicy：`clear`、`cloudy`、`rain`、`storm`、`snow`、`fog`

### 13.6 ActivityPolicy 配置语法

ActivityPolicy 是主要自定义入口。它采用简写入口 + 完整 matcher 的组合：

```yaml
activity:
  enabled: true
  weight: 1.2
  smoothing_window: 120

  process:
    Code: focus
    Obsidian: focus

  title:
    GitHub: focus
    "GitHub Actions": work

  matchers:
    - source: title
      match: regex
      pattern: "^GitHub .* Actions$"
      tag: work
      case_sensitive: false
```

决策：

- `process` 和 `title` 是简写入口。
- `matchers` 是完整匹配行为入口。
- 加载后，简写入口和完整 matcher 必须 normalize 成统一内部 matcher 列表。
- Runtime 匹配逻辑只基于 normalized matcher，不基于配置项写在哪个块里。
- 单条 activity matcher 只输出一个 tag。
- 不支持单条规则输出多个 tag。
- 不支持单规则 `weight` 或 `confidence`。
- 单条规则只做当前 observation 的分类；状态分布由 ActivityPolicy EMA 负责压缩时序信息。
- ActivityPolicy 的整体贡献强弱由 `activity.weight` 和 EMA 结果决定。

### 13.7 ActivityPolicy 匹配语义

简写默认：

- `process` 简写默认 `match: exact`。
- `title` 简写默认 `match: contains`。
- `process` exact 支持 `.exe` 等价。配置 `Code` 可匹配 `Code.exe`。
- `.exe` fallback 只用于 process exact，不用于 contains 或 regex。

完整 matcher：

- `source` 支持 `process`、`title`。
- `match` 支持 `exact`、`regex`、`contains`。
- 默认大小写不敏感。
- 完整 matcher 可用 `case_sensitive: true` 开启大小写敏感。

冲突处理：

- source 优先级：`title > process`。
- 同一 source 内 match 类型优先级：`exact > regex > contains`。
- regex 高于 contains，因为使用 regex 的用户被视为明确表达高级匹配意图。
- literal pattern 同 source、同 match 类型多条命中时，更长 pattern 优先。
- literal pattern 长度相同时，按配置声明顺序。
- regex 多条命中时，按配置声明顺序。
- “声明顺序”只用于 tie-break，不应覆盖 source 和 match 类型优先级。

### 13.8 Wallpaper Engine 路径和 executor readiness

`runtime.wallpaper_engine_path` 使用两种清楚模式：

- `null`：请应用自动检测。
- 非空字符串：用户显式指定路径。

行为：

- `null` 是 example 配置的默认推荐值。
- 自动检测在启动、reload 和配置辅助检测操作时发生。
- 不在每个 tick 前反复全盘检测。
- 自动检测成功后，runtime 使用检测到的路径。
- 自动检测成功不自动写回 YAML。
- 后续可以提供复制检测路径或明确写入配置的手动入口，但阶段 2 不要求。
- 自动检测失败时，配置本身仍可 valid，托盘宿主不退出，scheduler 可以继续 Sense / Think / Diagnostics。
- 自动检测失败时 actuation disabled，动作结果应说明 `wallpaper_engine_path_unresolved` 或等价原因。
- 显式路径必须存在且可执行。显式路径无效是 validate error。
- 显式路径无效时不 fallback 自动检测，因为这会隐藏用户配置错误。
- Executor 不应自行静默 no-op。
- Executor 应接收已解析的执行状态，并为命令返回明确结果。
- Actuator 只有在真实执行成功后，才能更新 active playlist 和 controller cooldown。

### 13.9 Reload 行为和状态迁移

- Reload Config 是配置操作，不是调度操作。
- Reload 成功后永不自动 switch 或 cycle。
- 用户想立即应用新配置，应使用 tray 的 `Apply Current Match Now`。
- Reload 必须 validate before swap。
- Reload 失败时旧 runtime 完全保留。
- Reload 成功时全量重建 runtime components。
- Reload 成功后迁移以下状态：
  - pause / pause_until
  - current playlist 字符串
  - controller `last_playlist_switch_time`
  - controller `last_wallpaper_switch_time`
  - ActivityPolicy EMA 压缩状态
- ActivityPolicy EMA reload 后保留当前压缩状态，新 `smoothing_window` 从后续 tick 开始生效。
- ActivityPolicy EMA 导入时必须过滤新 tag vocabulary 中不存在的 tag。
- 不迁移已删除 policy 的 state。
- 不迁移 matcher 派生结果或 playlist score 缓存。
- 不迁移 executor path resolved 状态。Reload 后重新 resolve。
- Reload 成功后不清空 cooldown。
- Reload 成功后不绕过 idle / fullscreen / CPU gate。

### 13.10 Tray `Apply Current Match Now`

Tray 后续提供 `Apply Current Match Now` / `立即应用当前匹配`。

产品语义：

- 用户希望“按当前上下文执行一次切换判断”。
- 它是手动调度动作，不是配置 reload 的副作用。
- 只放 tray，不放 Diagnostics。
- 不提供 `Next Wallpaper`，因为 Wallpaper Engine 本身已有类似能力。
- 不提供 `Clear Cooldown`，因为这是 controller 内部机制，不是用户意图。

执行语义：

- 立即采集当前上下文。
- 计算当前 best playlist。
- 如果 best playlist 与 current playlist 不同，执行 playlist switch。
- 如果 best playlist 与 current playlist 相同，按现有自动调度语义执行 cycle。
- 如果 no match，不执行副作用并记录原因。
- 手动 apply 绕过所有 controller gates，包括 cooldown、idle、fullscreen、CPU。
- 手动 apply 仍受硬条件限制，例如 WE path unresolved、executor command failed。
- Scheduler paused 时允许手动 apply，但不取消 paused。
- 手动 apply 成功后按真实副作用更新状态：
  - switch 成功：更新 current playlist、last playlist switch time、last wallpaper switch time。
  - cycle 成功：更新 last wallpaper switch time。
- 手动 apply 应进入 history / diagnostics reason，例如 `manual_apply_requested` 或等价 reason code。

### 13.11 UI / UX 边界

- GUI 不承担完整配置编辑。
- Dashboard / Diagnostics 保持诊断工具，不放手动副作用按钮。
- 配置页面降级为配置辅助工具面板。
- 保留 Open Config Folder。
- 保留 Validate Config。
- 保留 Reload Config。
- 保留 Show Last Config Error。
- 保留 Scan Wallpaper Engine Playlists。
- 可保留打开 / 查看打包 example 配置的入口。
- 不继续扩展多页表单式 Config Editor。
- 不把 History 扩展成独立长期分析产品。
