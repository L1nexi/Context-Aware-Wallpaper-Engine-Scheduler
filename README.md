# Context Aware WE Scheduler

基于上下文感知的 Wallpaper Engine 智能调度器。

## 核心特性

- **多维度感知**：活动窗口、空闲时长、CPU 负载、时段、季节、天气 — 六路 Sensor 实时采集。
- **向量化匹配**：Policy 输出标签向量，Matcher 余弦相似度匹配最佳播放列表。支持 TagSpec fallback 图。
- **平滑过渡**：ActivityPolicy 双 EMA 轨道、Time/Season Hann 窗插值、Weather 四档连续强度 — 告别硬切换。
- **防打扰门控**：空闲阈值 + 全屏检测 + CPU 过载保护 + 播单切换/轮播独立冷却 + 强制超时。
- **系统托盘**：运行/暂停状态图标，支持按时段暂停（预设 30m–48h / 自定义 / 无限期）。`switch_on_start` 选项。
- **国际化**：托盘 UI 根据系统语言自动切换中文 / 英文。
- **实时仪表盘**：Vue 3 SPA，Live 标签页显示相似度/标签/上下文，History 标签页显示 Gantt 时间线 + 事件历史。
- **热重载**：编辑 `config/` 下的 YAML 文件后自动重载配置，无需重启。

## 快速开始

### 1. 获取程序

- 方案 A：可执行文件
  下载最新的 `WEScheduler.exe` 压缩包，解压后双击运行。

- 方案 B：自行构建

```powershell
.\scripts\build.bat
```

构建后在 `dist/` 目录找到 `WEScheduler.exe`。
配置目录不会随 exe 一起打包；运行前请在 exe 同级放置 `config/`。

- 方案 C：从源码运行

```bash
pip install -r requirements.txt
python main.py              # 托盘模式
python main.py --no-tray    # 控制台模式（调试用）
```

### 2. 配置

当前主配置入口是外部 `config/` 目录，固定包含 6 个 YAML 文件：

- `scheduler.yaml`
- `playlists.yaml`
- `tags.yaml`
- `activity.yaml`
- `context.yaml`
- `scheduling.yaml`

不再读取 `scheduler_config.json`，也不支持 `include`、anchors、aliases、merge keys。

#### `scheduler.yaml`

```yaml
version: 2

runtime:
  wallpaper_engine_path: null
  language: null
```

`wallpaper_engine_path: null` 会让运行时自动检测 Wallpaper Engine 路径。

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
  process_rules:
    Code.exe: focus
    steam.exe: chill
  title_rules:
    GitHub: focus
    YouTube: chill
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

## 仪表盘 (Dashboard)

托盘右键 → Dashboard 打开独立窗口。

**Live 标签页:**

- 当前播放列表（含 display 名）
- 相似度、gap、magnitude 实时数值 + sparkline 趋势
- Top-8 标签权重图
- 上下文数据（活跃窗口、空闲时长、CPU、全屏状态）

**History 标签页:**

- ECharts Gantt 时间线 — 各播放列表/暂停/停止的连续区间
- 事件列表 — 按时间倒序，含图标、描述、标签快照
- 过滤器 — 1h / 6h / 24h / 7d 预设 + 自定义日期范围
- 自动刷新 — 新事件产生时保留当前过滤范围自动更新

## 架构

```plain
Sensors → Context → Policies → Matcher → Controller → Actuator → WEExecutor
                                                          │
                                                    on_tick(s, ctx, res) → StateStore → HTTP :0 → Dashboard SPA
                                                          │
                                                    HistoryLogger.write() → history-{YYYY}-{MM}.jsonl
```

详细架构说明见 `CLAUDE.md`，路线图见 `docs/ROADMAP.md`。

## 运行时文件

| 路径                             | 用途                      |
| -------------------------------- | ------------------------- |
| `config/`                        | 主配置目录（热重载）      |
| `data/state.json`                | 持久化暂停/播放列表状态   |
| `data/history-{YYYY}-{MM}.jsonl` | 按月分片事件日志          |
| `logs/scheduler.log`             | 轮转日志（5 MB × 3 备份） |
