# Context Aware WE Scheduler

基于上下文感知的 Wallpaper Engine 智能调度器。

## 核心特性

- **多维度感知**：活动窗口、空闲时长、CPU 负载、时段、季节、天气 — 六路 Sensor 实时采集。
- **向量化匹配**：Policy 输出标签向量，Matcher 余弦相似度匹配最佳播放列表。支持 TagSpec fallback 图。
- **平滑过渡**：ActivityPolicy 双 EMA 轨道、Time/Season Hann 窗插值、Weather 四档连续强度 — 告别硬切换。
- **防打扰门控**：空闲阈值 + 全屏检测 + CPU 过载保护 + 播单切换/轮播独立冷却 + 强制超时。
- **系统托盘**：运行/暂停状态图标，支持按时段暂停（预设 30m–1w / 自定义 / 无限期），并提供一次性的当前上下文手动调度。
- **国际化**：托盘 UI 和 Diagnostics 根据系统语言自动切换中文 / 英文。
- **Diagnostics**：Vue 3 SPA 展示近期 tick 的 Sense / Think / Act 诊断、匹配结果、controller 门控和动作结果。
- **文本配置工具**：`Config Tools.bat` / `WEScheduler.exe config` 提供校验、Wallpaper Engine 路径检测和播放列表扫描。
- **热重载**：编辑 `config/` 下的 YAML 文件后自动 validate-before-swap；失败时保留上一份有效运行配置。

## 快速开始

### 1. 获取程序

- 方案 A：可执行文件
  下载最新的 `WEScheduler.exe` 压缩包，解压后双击运行。

- 方案 B：自行构建

```powershell
.\scripts\build.bat
```

构建后在 `dist/` 目录找到 `WEScheduler.exe`。`dist/` 同时包含 `Config Tools.bat` 和一份外部 `config/` example 配置。

- 方案 C：从源码运行

```bash
pip install -r requirements.txt
python main.py              # 托盘模式
python main.py --no-tray    # 控制台模式（调试用）
```

### 2. 配置

当前主配置入口是 exe 同级或源码根目录下的外部 `config/` 目录，固定包含 6 个 YAML 文件：

- `scheduler.yaml`
- `playlists.yaml`
- `tags.yaml`
- `activity.yaml`
- `context.yaml`
- `scheduling.yaml`

运行时只读取这 6 个固定文件，不支持 `include` 或任意拆分文件。

#### `scheduler.yaml`

```yaml
version: 2

runtime:
  wallpaper_engine_path: null
  language: null
```

`wallpaper_engine_path: null` 会让运行时自动检测 Wallpaper Engine 路径。显式填写路径时必须指向存在的可执行文件；显式路径无效不会回退到自动检测。

#### `playlists.yaml`

```yaml
playlists:
  RAINY_MOOD:
    display: 雨天氛围
    color: "#4A90D9"
    tags:
      rain: 1.0
      chill: 0.4
```

- `playlists` 使用 map，key 直接等于 Wallpaper Engine 播放列表名。
- `display` 只用于 Diagnostics / UI 显示。
- `tags` 表达播放列表和概念的亲和度比例。

#### `tags.yaml`

```yaml
tags:
  storm:
    fallback:
      rain: 1.0
```

tag 不再使用 `#` 前缀。所有被 playlist、activity、time、season、weather 引用的 tag 都必须在这里声明。

#### `activity.yaml`

```yaml
activity:
  enabled: true
  weight: 1.2
  smoothing_window: 120
  process:
    Code: focus
    steam: chill
  title:
    GitHub: focus
    YouTube: chill
  matchers: []
```

#### `context.yaml`

```yaml
time:
  enabled: true
  weight: 0.8
  day_start_hour: 8
  night_start_hour: 20

season:
  enabled: true
  weight: 0.65

weather:
  enabled: true
  weight: 1.5
  api_key: ""
  lat: 31.2964
  lon: 121.5036
  fetch_interval: 600
  request_timeout: 10
```

固定 policy 输出的 tag 也是无前缀：

- TimePolicy: `dawn` `day` `sunset` `night`
- SeasonPolicy: `spring` `summer` `autumn` `winter`
- WeatherPolicy: `clear` `cloudy` `rain` `storm` `snow` `fog`

#### `scheduling.yaml`

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

### 3. 配置辅助工具

Release 包中双击 `Config Tools.bat`，或从命令行运行：

```powershell
WEScheduler.exe config
```

源码运行时也可以使用：

```bash
python main.py config
```

配置工具是离线 TUI，不会启动调度循环或 Diagnostics。当前菜单：

```text
1. Validate config
2. Detect Wallpaper Engine
3. Scan Wallpaper Engine playlists
q. Exit
```

- Validate config：使用启动 / 热重载同一套 loader 校验配置；成功后输出配置目录、解析后的 WE 路径、播放列表数量和启用策略。
- Detect Wallpaper Engine：显示配置值、解析后的可执行文件路径，以及 Wallpaper Engine `config.json` 是否找到；不会写回 YAML。
- Scan Wallpaper Engine playlists：读取 Wallpaper Engine `config.json` 中的播放列表名，输出纯名称列表和可复制的 `playlists.yaml` 片段；不会自动生成 tag、颜色或 display 名。

### 4. Reload 与手动应用

保存 `config/` 中任一 YAML 文件后，运行中的调度器会尝试热重载。热重载成功只替换运行配置并保留允许迁移的状态，不会立刻执行 playlist switch 或 wallpaper cycle。下一次自动 tick 仍受 idle、fullscreen、CPU 和 cooldown 等门控影响。

如果想立即按当前上下文执行一次调度，请使用托盘菜单 `Schedule From Current Context Now` / `立即按当前上下文调度`。这个动作绕过自动调度门控，但仍要求 Wallpaper Engine 命令真实执行成功。

## Diagnostics

托盘右键 → Diagnostics 打开独立诊断窗口。

- 决策时间轴：展示近期 tick 的相似度、gap、active playlist 与 matched playlist。
- Sense：展示当前 tick 采集到的窗口、空闲、CPU、全屏、时间和天气输入。
- Think：展示 policy contribution、fallback 展开、上下文向量和 Top Matches。
- Act：展示 controller 评估、阻塞原因、动作结果和最终 active playlist。

Diagnostics 是解释和排错工具，不承担配置编辑、长期 History 分析或手动副作用控制台职责。

## 架构

```plain
Sensors -> Context -> Policies -> Matcher -> Controller -> Actuator -> WEExecutor
                                                           |
                                          SchedulerTickTrace -> AnalysisStore -> HTTP :0 -> Diagnostics SPA
                                                           |
                                      HistoryLogger.write() -> history-{YYYY}-{MM}.jsonl
```

产品方向见 `docs/PRODUCT_DIRECTION.md`，配置契约见 `docs/frontend/CONFIGURATION_SPEC.md`。

## 运行时文件

| 路径                             | 用途                      |
| -------------------------------- | ------------------------- |
| `config/`                        | 主配置目录（热重载）      |
| `data/state.json`                | 持久化暂停/播放列表状态   |
| `data/history-{YYYY}-{MM}.jsonl` | 按月分片事件日志          |
| `logs/scheduler.log`             | 轮转日志（5 MB × 3 备份） |
