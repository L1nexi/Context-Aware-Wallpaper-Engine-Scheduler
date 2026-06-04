# Context Aware WE Scheduler

> 具备多维上下文感知能力、防打扰调度策略的 Wallpaper Engine 调度器。
> A Scheduler that maintains your flow.

你是否坐拥几十上百张壁纸收藏，却发现 Wallpaper Engine 内置的调度策略难堪大用：现有的定时切换、日内时段切换或星期内切换，要么切换频率过高导致频繁卡顿，要么频率过低而无法充分利用壁纸库？

你是否会凝望着窗外的淅沥小雨、盛夏骄阳或是冬雪皑皑，希望自己的桌面也能展出一张符合当下氛围的壁纸？

你是否希望在工作时看到安静深邃的桌面，而在闲暇摸鱼之时看到自己的二次元老婆？

本项目的宗旨便是弥补 Wallpaper Engine 原生调度能力的对上述场景支持的不足，尝试提供一个能读懂时间、时令、天气以及你的活动，并可以聪明地处理调度时机，以维持用户心流的 Wallpaper Engine 调度器。

## 核心特性

- 多维上下文感知：探测日内时间、全年季节、天气状况、窗口活动等信息用于上下文标签向量生成。
- 内置四项典型标签策略：内置日内时间、全年季节、天气状况及窗口活动作为内置策略，提供 14+ 可用标签。
- 可自定义的播单配置：设想一个典型的播单场景，为其配置标签权重，随后便可用于上下文标签匹配。还可以调节不同策略的优先级。
- 防打扰调度策略：内置多项防打扰调度机制，在 CPU 高负载、全屏状态或空闲时间未达阈值时推迟壁纸切换。
- 平滑过渡：多数策略采用平滑处理，在上下文变化时自然过渡。同时采用播单池策略和语义连续性检测算法，在播单得分差距有限的场景下提供更平稳的切换决定。

## 快速开始

config/ 提供预设配置

1. 查看 `playlists.yaml` 并保留所需配置。预设配置包含九个典型场景，分为四个日内活动情况播单，四个季节特色播单，以及一个雨天播单。按自己的使用场景保留播单配置。
2. 打开 Wallpaper Engine，根据保留播单的 Wallpaper Engine 播单名（如 `BRIGHT_FLOW`）创建播放列表。在“配置”选项内，将“更换壁纸”、“播放顺序”和“显示壁纸过渡”配置为“从不”、“随机”和“无（减少闪烁）”。
3. 根据播单的使用场景，在 Wallpaper Engine 添加符合个人喜好的壁纸。
4. （推荐）配置 OpenWeatherMap 以启用天气感知。免费获取方法：注册 OpenWeatherMap -> 右上角用户名 -> My API Keys -> 填入 Key 名称后 Generate -> 将 Key 复制到 `context.yaml` 的 api_key 中。
5. （可选）根据个人活动情况，调整 `activity.yaml` 的匹配规则。
6. （可选）将调度器加入开机自动。Win + R，输入 `shell:startup`，添加调度器的快捷方式

## 调度器配置及使用

配置入口是 `config/` 目录，包含 6 个 YAML 文件：

- `scheduler.yaml`：配置 WPE 路径以及 UI 语言
- `playlists.yaml`：配置播单展示名、代表色以及标签
- `tags.yaml`：配置可见标签以及标签回退选项
- `activity.yaml`：配置窗口活动策略。可配置策略权重、匹配规则以及平滑窗口大小
- `context.yaml`：配置时间、季节和天气策略
- `scheduling.yaml`：配置调度策略

### 通用配置

- `scheduler.yaml`

```yaml
version: 2

runtime:
  wallpaper_engine_path: null
  language: null
```

`wallpaper_engine_path`： Wallpaper Engine 路径。值为 `null` 时调度器会尝试自动检测，也支持显式填写路径。
`language`：UI 界面语言。目前支持简体中文与英语。

### 播单标签配置

这是你需要配置的主要文件

- `playlists.yaml`

示例：

```yaml
playlists:
  BRIGHT_FLOW:
    display: 日光流动
    color: "#F5C518"
    tags:
      focus: 1.0
      day: 0.9
      dawn: 0.3
      clear: 0.3
```

- `BRIGHT_FLOW`：对应于 WPE 的播单名称。由于 WPE 限制，推荐使用纯英文字符。
- `display`：用于 UI 的显示名称。
- `color`：用于 UI 的播单代表色。
- `tags` 表达该播单与某个场景的亲和度或相似度。例如，示例的标签值的含义是，“该播单期望出现的场景，和 focus 标签的亲和度是 1，和 day 标签的亲和度是 0.9，和 dawn 以及 clear 标签的亲和度是 0.3。”

> 请注意，在匹配中，真正起作用的是标签值的相对比例而非绝对大小。

- `tags.yaml`

```yaml
tags:
  storm:
    fallback:
      rain: 1.0
```

- `storm` storm 标签。 `tags` 下的全部标签即为当前调度器输出的可用标签
- `fallback`：用于指定标签的回退路径。当上下文中出现的标签没有被 `playlists.yaml` 中配置的播单标签使用时，调度器会尝试将原始标签，如 storm，转化为回退标签，如 rain，以参与匹配。

### 策略配置

不同策略共享的配置字段为：

- `enabled`：控制策略是否启用并输出
- `weight`：控制策略的权重

- 窗口活动策略：

```yaml
# activity.yaml
activity:
  ...
  smoothing_window: 120
  process:
    Code: focus
    steam: chill
  title:
    GitHub: focus
    YouTube: chill
```

- `smoothing_window`：检测到的活动在多大的时间窗口内平滑，单位为秒。
- `process`：进程规则。key 为进程名，值为要映射的标签
- `title`：进程名规则，优先级高于进程规则。

- 天气策略：

```yaml
weather:
  ...
  api_key: ""
  lat: 0.0
  lon: 0.0
  fetch_interval: 600
  warmup_timeout: 3
  request_timeout: 10
```

- `api_key`：OpenWeatherMap 的 API-KEY，用于开启天气探测。
- `lat`, `lon`：所在地经纬度。

- 日内时间策略：

```yaml
time:
  ...
  auto: true
  day_start_hour: 8
  night_start_hour: 20
```

- `auto`：自动根据 OpenWeatherMap 的日落日出时间设置日落日出时间。为 true 时覆盖手动设置。

- 季节策略：

```yaml
season:
  ...
  spring_peak: 80
  summer_peak: 172
  autumn_peak: 265
  winter_peak: 355
```

用于指定各个季节的标签在那一天达到峰值。

### 调度配置

- `scheduling.yaml`

各时间配置的单位均为秒

```yaml
scheduling:
  startup_delay: 15
  idle_threshold: 20
  cycle_cooldown: 900
  force_after: 3600
  cpu_threshold: 85
  cpu_sample_window: 10
  pause_on_fullscreen: true
```

- `pause_on_fullscreen`：为 true 时启用全屏暂停机制。全屏状态下阻止切换
- `idle_threshold`：空闲阈值，多少秒后判定为空闲。非空闲下阻止切换
- `cpu_threshold`：CPU 负载阈值，平均负载高于阈值时阻止切换
- `force_after`：强制切换，超过阈值后使空闲阈值失效。
- `startup_delay`：启动延迟，调度器首次调度前至少需等待的时间
- `cycle_cooldown`：轮播冷却，当播单保持稳定时，经过多长时间在播单内部轮播

### 配置工具

运行 `Config Tools.bat`，可见菜单：

```text
1. 验证配置
2. 检测 Wallpaper Engine
3. 扫描 Wallpaper Engine 播放列表
q. 退出
```

- 验证配置：检验配置是否完整。成功后输出配置目录、解析后的 WE 路径、播放列表数量和启用策略。
- 检测 Wallpaper Engine：显示配置路径、解析后的可执行文件路径，以及是否可以找到 Wallpaper Engine 的配置文件 `config.json`。
- 扫描 Wallpaper Engine 播放列表：读取 Wallpaper Engine `config.json` 中的播放列表名，输出纯名称列表和可复制的 `playlists.yaml` 片段。

### 配置热重载

调度器支持配置热重载。无需重启即可应用新的配置文件。请注意，热重载不会重置调度策略的各项冷却以及防打扰控制机制。

## 托盘使用

托盘展示当前匹配、当前实际播单。

- 暂停：按预设值或自定义时长暂停调度器。暂停期间调度器不进行实际调度，但仍然进行上下文检测和匹配决策。
- 立刻应用当前匹配：无视防打扰策略，立刻按当前上下文执行一次播单切换。该选项在暂停时仍然有效
- 诊断：打开独立诊断窗口，展示决策时间轴、当前感知、匹配和调度行为详情。
