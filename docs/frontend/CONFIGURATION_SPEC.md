# Configuration System Spec

本文档定义下一阶段配置系统的产品定位、文件结构、数据模型和工具边界。它取代 `CONFIG_EDITOR_SPEC.md` 作为配置方向的最高优先级文档。

## 0. 实施状态（2026-05-10）

当前配置系统仍以 `scheduler_config.json` 和 Pydantic `AppConfig` 为运行时事实源。`dashboard-v2` 已经存在部分 Config Editor 路由和 General / Scheduling 页面，但产品方向已经收敛：

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

### 3.1 `scheduler.yaml`

入口文件，负责版本、preset、include 和 runtime 字段。

```yaml
version: 2
preset: standard

include:
  - playlists.yaml
  - tags.yaml
  - activity.yaml
  - context.yaml
  - scheduling.yaml

runtime:
  wallpaper_engine_path: C:/Program Files (x86)/Steam/steamapps/common/wallpaper_engine/wallpaper64.exe
  language: zh
```

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

定义 tag fallback 图。

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

定义前台进程 / 标题到 tag 的映射。

```yaml
activity:
  enabled: true
  weight: 1.2
  smoothing_window: 120

  process:
    Code.exe: focus
    Obsidian.exe: focus
    steam.exe: chill

  title:
    GitHub: focus
    YouTube: chill
    直播: chill
```

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
- 内置 tag 与用户 tag 使用同一套命名规则。
- 未知 tag 应默认报错，避免拼写错误静默变成新 tag。

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

## 7. Preset + Override 模型

分层配置和 preset 不冲突。正式模型是：

```text
builtin preset
  + scheduler.yaml
  + included domain files
  -> merged raw config
  -> Pydantic validation
  -> normalized runtime AppConfig
```

Preset 是 base layer，用户文件是 override layer。

### 7.1 Merge 规则

推荐 merge 规则：

- scalar：后层覆盖前层。
- object / map：按 key deep merge。
- playlist / tag / policy：按 id merge。
- list：尽量避免；必须出现时默认整体替换。
- 删除语义不使用隐式 `null`；禁用资源或策略时使用显式 `enabled: false`。

为了让 override 可靠，资源型配置必须优先使用 map，而不是 array。

## 8. Runtime 边界

YAML 配置不是运行时直接消费的模型。运行时继续消费 normalized `AppConfig`。

配置加载流程：

1. 读取 `scheduler.yaml`。
2. 加载并解析 `include` 中的 domain files。
3. 叠加 builtin preset 与用户 override。
4. 将新配置语义转换成 runtime schema 可接受的 raw dict。
5. 通过 Pydantic 校验并 normalize。
6. 校验通过后替换当前运行配置。
7. 校验失败时保留旧配置，并记录 / 展示错误。

## 9. GUI 与工具边界

GUI 不承担完整配置编辑。

应保留或新增的辅助入口：

- Open Config Folder
- Reload Config
- Validate Config
- Show Last Config Error
- Generate Starter Config
- Scan Wallpaper Engine Playlists

正式要求：

- Reload 必须 validate before swap。
- 配置校验失败时不得替换当前有效配置。
- 错误信息必须指向具体文件和路径，例如 `playlists.yaml > playlists.NIGHT_FOCUS.tags.nigth`。
- Diagnostics 可以展示当前配置路径、最后一次 reload 时间和最后一次 reload 结果。

## 10. API 方向

旧 `/api/config` 的完整 GUI 编辑契约不再是当前主线。后续配置相关 API 应优先服务文本配置工作流：

- 获取当前 normalized config，用于 Diagnostics 展示。
- 执行 validate。
- 执行 reload。
- 获取最近一次配置错误。
- 扫描 Wallpaper Engine 播放列表。
- 打开配置目录或返回配置目录路径。

如果保留现有 `GET /api/config` / `POST /api/config`，应明确标记为 legacy editor support 或内部工具接口，不应继续以完整 Config Editor 为产品目标扩展。

## 11. 实施顺序

建议按以下顺序落地：

1. 定义新配置目录结构和 YAML loader。
2. 引入 tag id 与 playlist id breaking change。
3. 将 playlist 从 array 语义改为 map 语义。
4. 建立 builtin preset + user override merge。
5. 将 merged raw config 转换为 runtime `AppConfig`。
6. 接入 validate before swap 的 reload 流程。
7. 更新示例配置和 README。
8. 将 GUI Config Editor 入口降级为配置辅助工具入口。
9. 清理或冻结旧 Config Editor 文档和未完成页面。

## 12. 验收标准

实现完成后至少满足：

1. 用户可以只修改 `playlists.yaml` 或 `activity.yaml`，不需要打开完整配置树。
2. 用户可以使用注释、缩进和无括号的 YAML 常规书写体验。
3. tag 不再使用 `#` 前缀。
4. playlist key 直接对应 Wallpaper Engine 播放列表名。
5. 缺省颜色会自动分配；手写颜色可以使用命名色或无 `#` hex。
6. preset 和用户 override 能稳定合并。
7. 配置错误能定位到具体文件和字段路径。
8. reload 失败时，调度器继续使用上一次有效配置。
9. 内部运行时仍使用 Pydantic normalized `AppConfig`。
