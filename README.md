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
- **热重载**：编辑 `scheduler_config.json` 后自动重载配置，无需重启。

## 快速开始

### 1. 获取程序

- 方案 A：可执行文件
  下载最新的 `WEScheduler.exe` 压缩包，解压后双击运行。

- 方案 B：自行构建

```powershell
.\scripts\build.bat
```

构建后在 `dist/` 目录找到 `WEScheduler.exe`。

- 方案 C：从源码运行

```bash
pip install -r requirements.txt
python main.py              # 托盘模式
python main.py --no-tray    # 控制台模式（调试用）
```

### 2. 配置

完整示例见 `scheduler_config.example.json`。

#### 顶层字段

| 字段                    | 说明                       |
| ----------------------- | -------------------------- |
| `wallpaper_engine_path` | `wallpaper64.exe` 完整路径 |
| `playlists`             | 播放列表数组（见下）       |
| `tags`                  | TagSpec fallback 图        |
| `policies`              | 策略配置                   |
| `scheduling`            | 调度与防打扰参数           |

#### 播放列表 (`playlists`)

```json
{
  "name": "RAINY_MOOD",
  "display": "雨天氛围",
  "tags": { "#rain": 1.0, "#chill": 0.4 }
}
```

| 字段      | 说明                                                   |
| --------- | ------------------------------------------------------ |
| `name`    | 内部标识（需与 WE 播放列表名一致）                     |
| `display` | 可选，UI 显示名（如中文名）                            |
| `tags`    | 画风亲和度（起作用的是各标签之间的**比例**，非绝对值） |

#### 策略 (`policies`)

所有 Policy 支持 `enabled` (bool) 和 `weight_scale` (float)。

| Policy         | 配置键              | 输出标签                                           |
| -------------- | ------------------- | -------------------------------------------------- |
| ActivityPolicy | `policies.activity` | 自定义（由 `process_rules` / `title_rules` 映射）  |
| TimePolicy     | `policies.time`     | `#dawn` `#day` `#sunset` `#night`                  |
| SeasonPolicy   | `policies.season`   | `#spring` `#summer` `#autumn` `#winter`            |
| WeatherPolicy  | `policies.weather`  | `#clear` `#cloudy` `#rain` `#storm` `#snow` `#fog` |

**ActivityPolicy:**

```json
"activity": {
  "enabled": true, "weight_scale": 1.2, "smoothing_window": 120,
  "process_rules": { "Code.exe": "#focus", "steam.exe": "#chill" },
  "title_rules": { "GitHub": "#focus", "YouTube": "#chill" }
}
```

**TimePolicy:**

```json
"time": { "enabled": true, "weight_scale": 0.8, "day_start_hour": 8, "night_start_hour": 20 }
```

当 WeatherSensor 可用时，自动从 OWM `sunrise`/`sunset` 推算动态峰值。

**WeatherPolicy:**

```json
"weather": {
  "enabled": true, "weight_scale": 1.5,
  "api_key": "YOUR_KEY", "lat": "39.9", "lon": "116.4",
  "interval": 600, "request_timeout": 10
}
```

天气强度四档模型：T1≈0.25（薄雾）→ T4=1.0（暴雷雨/晴天）。

#### 调度 (`scheduling`)

```json
"scheduling": {
  "switch_on_start": false,
  "idle_threshold": 60,
  "switch_cooldown": 1800,
  "cycle_cooldown": 600,
  "force_after": 14400,
  "cpu_threshold": 85,
  "cpu_sample_window": 10,
  "pause_on_fullscreen": true
}
```

| 字段                  | 默认值  | 说明                       |
| --------------------- | ------- | -------------------------- |
| `switch_on_start`     | `false` | 启动时是否立即切换         |
| `idle_threshold`      | `60`    | 空闲多少秒后才允许切换     |
| `switch_cooldown`     | `1800`  | 播单切换最小间隔（秒）     |
| `cycle_cooldown`      | `600`   | 播单内轮播间隔（秒）       |
| `force_after`         | `14400` | 强制切换超时（秒）         |
| `cpu_threshold`       | `85`    | CPU 超过此百分比则推迟切换 |
| `pause_on_fullscreen` | `true`  | 全屏/演示模式时暂停切换    |

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
| `scheduler_config.json`          | 主配置（热重载）          |
| `data/state.json`                | 持久化暂停/播放列表状态   |
| `data/history-{YYYY}-{MM}.jsonl` | 按月分片事件日志          |
| `logs/scheduler.log`             | 轮转日志（5 MB × 3 备份） |
