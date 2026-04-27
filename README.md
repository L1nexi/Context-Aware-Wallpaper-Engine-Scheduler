# Context Aware WE Scheduler

一个基于上下文感知的 Wallpaper Engine 智能调度器。

## 核心特性

- **智能感知**：根据当前活动窗口、系统时间、季节或实时天气自动切换壁纸。
- **防打扰**：仅在用户空闲时切换壁纸，区分"播单切换"与"播单内轮播"，支持独立冷却时间与强制切换超时。
- **平滑过渡**：EMA 平滑活动状态；Time/Season 策略使用 Hann 窗插值；天气强度连续变化，告别硬切换。
- **向量化匹配**：使用余弦相似度在所有播放列表中找到最贴近当前上下文的一个，支持对播放列表进行向量化配置。
- **系统托盘**：最小化到托盘运行，实时显示运行/暂停状态，支持按时段暂停（预设时长、自定义或无限期）。
- **国际化**：托盘 UI 根据系统语言自动切换中文 / 英文。

## 快速开始

### 1. 获取程序

你可以通过以下三种方式之一获取并运行程序：

#### 方案 A：直接使用可执行文件

1. 下载最新的含已编译 `WEScheduler.exe` 的压缩包并解压。

#### 方案 B：自行构建

1. 克隆仓库并进入目录。
2. 运行构建脚本：

   ```powershell
   .\scripts\build.bat
   ```

3. 构建完成后，在 `dist/` 目录下即可找到 `WEScheduler.exe`。

#### 方案 C：从 Python 源码启动

1. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 直接运行：

   ```bash
   python main.py
   ```

### 2.配置参数详解

#### 顶层字段

| 字段                    | 说明                                                              |
| ----------------------- | ----------------------------------------------------------------- |
| `wallpaper_engine_path` | Wallpaper Engine 可执行文件的完整路径（通常为 `wallpaper64.exe`） |

---

#### 播放列表 (`playlists`)

```json
{ "name": "RAINY_MOOD", "tags": { "#rain": 1.0, "#chill": 0.4, "#focus": 0.3 } }
```

每个播放列表通过 `tags` 字段描述其"画风"。调度器将各 Policy 输出的标签向量与所有播放列表进行**余弦相似度**匹配，选出最贴近当前上下文的列表。

> **注意：** 起作用的是各标签之间的**比例**，而非绝对数值大小。`{ "#focus": 0.9, "#chill": 0.2 }` 与 `{ "#focus": 9, "#chill": 2 }` 效果完全相同。

**内置标签速查表** — 各 Policy 自动输出以下标签，可直接在 `tags` 中引用：

| 标签       | 来源 Policy    | 触发条件                                             |
| ---------- | -------------- | ---------------------------------------------------- |
| `#dawn`    | TimePolicy     | 黎明时段（`day_start_hour` 附近，Hann 窗平滑过渡）   |
| `#day`     | TimePolicy     | 白天时段                                             |
| `#sunset`  | TimePolicy     | 日落时段（`night_start_hour` 附近）                  |
| `#night`   | TimePolicy     | 夜间时段                                             |
| `#spring`  | SeasonPolicy   | 春季（3–5 月，Hann 窗平滑过渡）                      |
| `#summer`  | SeasonPolicy   | 夏季（6–8 月）                                       |
| `#autumn`  | SeasonPolicy   | 秋季（9–11 月）                                      |
| `#winter`  | SeasonPolicy   | 冬季（12–2 月）                                      |
| `#clear`   | WeatherPolicy  | 晴天                                                 |
| `#cloudy`  | WeatherPolicy  | 多云 / 阴天                                          |
| `#rain`    | WeatherPolicy  | 雨（毛毛雨→暴雨，强度连续变化）                      |
| `#storm`   | WeatherPolicy  | 雷暴 / 大风 / 龙卷                                   |
| `#snow`    | WeatherPolicy  | 降雪 / 雨夹雪 / 雪粒                                 |
| `#fog`     | WeatherPolicy  | 雾 / 霾 / 烟 / 扬尘                                  |
| 自定义标签 | ActivityPolicy | 由 `policies.activity.rules` 中的进程 / 标题映射决定 |

---

#### 策略 (`policies`)

所有 Policy 均支持 `enabled`（bool）和 `weight_scale`（float，影响权重倍数）字段。

#### ActivityPolicy — 活动窗口感知

```json
"activity": {
  "enabled": true,
  "weight_scale": 1.2,
  "smoothing_window": 120,
  "process_rules": { "Code.exe": "#focus", "steam.exe": "#chill" },
  "title_rules": { "GitHub": "#focus", "YouTube": "#chill" }
}
```

| 字段               | 默认值 | 说明                                                                    |
| ------------------ | ------ | ----------------------------------------------------------------------- |
| `weight_scale`     | `1.0`  | 该策略的影响权重倍数                                                    |
| `smoothing_window` | `120`  | EMA 平滑窗口（秒）。值越大对活动切换的响应越迟钝、越稳定                |
| `process_rules`    | `{}`   | 进程名 → 标签的映射，**不区分大小写**，匹配当前前台窗口的 `.exe` 文件名 |
| `title_rules`      | `{}`   | 窗口标题关键词 → 标签的映射（子字符串匹配，不区分大小写）               |

#### TimePolicy — 时段感知

```json
"time": { "enabled": true, "weight_scale": 0.8, "day_start_hour": 8, "night_start_hour": 20 }
```

| 字段               | 默认值 | 说明                                                             |
| ------------------ | ------ | ---------------------------------------------------------------- |
| `weight_scale`     | `1.0`  | 该策略的影响权重倍数                                             |
| `day_start_hour`   | `8`    | 白天开始时刻（24 小时制整数小时），同时也是 `#dawn` 峰值所在时刻 |
| `night_start_hour` | `20`   | 夜晚开始时刻，同时也是 `#sunset` 峰值所在时刻                    |

时段标签采用 **Hann 窗平滑插值**（半宽约 6 小时），相邻时段之间连续过渡，不会突变。

#### SeasonPolicy — 季节感知

```json
"season": { "enabled": true, "weight_scale": 0.6 }
```

无需额外字段，自动根据系统日期输出季节标签，采用 Hann 窗平滑（半宽约 45 天）。

#### WeatherPolicy — 天气感知

```json
"weather": {
  "enabled": true,
  "weight_scale": 1.5,
  "api_key": "YOUR_OPENWEATHERMAP_API_KEY",
  "lat": "39.9",
  "lon": "116.4",
  "interval": 600,
  "request_timeout": 10
}
```

| 字段              | 默认值 | 说明                                                                              |
| ----------------- | ------ | --------------------------------------------------------------------------------- |
| `weight_scale`    | `1.0`  | 天气策略影响权重上限（轻微天气时远低于此值，极端天气时达到上限）                  |
| `api_key`         | `""`   | [OpenWeatherMap](https://openweathermap.org/api) 免费 API Key，留空则禁用天气策略 |
| `lat` / `lon`     | `""`   | 所在位置的纬度 / 经度（十进制度数字符串，如 `"39.9"` / `"116.4"`）                |
| `interval`        | `600`  | 向 OWM 接口请求数据的间隔（秒），建议不低于 `300`                                 |
| `request_timeout` | `10`   | HTTP 请求超时时间（秒）                                                           |

天气强度采用**四档模型**，轻微天气不过度干预壁纸选择：

| 等级 | 强度系数 | 代表天气                 |
| ---- | -------- | ------------------------ |
| T1   | 0.2      | 薄雾、轻霾、毛毛雨       |
| T2   | 0.5      | 一般降雨、零星小雪、多云 |
| T3   | 0.8      | 中等雷暴、大雨、大雪     |
| T4   | 1.0      | 暴雷雨、暴雪、龙卷、晴天 |

---

#### 防打扰 (`disturbance`)

```json
"disturbance": {
  "switch_on_start": false,
  "idle_threshold": 20,
  "min_interval": 150,
  "wallpaper_interval": 900,
  "force_interval": 3600
}
```

| 字段                 | 默认值  | 说明                                                                                     |
| -------------------- | ------- | ---------------------------------------------------------------------------------------- |
| `switch_on_start`    | `false` | 程序启动时是否**立即**切换到匹配的播放列表。`false` 时等待 `min_interval` 冷却期后再切换 |
| `idle_threshold`     | `60`    | 用户连续空闲多少秒后才允许切换，防止在使用电脑时壁纸突变，单位秒                         |
| `min_interval`       | `1800`  | **播单切换**（切换到不同播放列表）的最短冷却时间，单位秒                                 |
| `wallpaper_interval` | `600`   | **播单内轮播**（同一列表内切换下一张壁纸）的间隔，单位秒                                 |
| `force_interval`     | `14400` | 强制切换超时（秒）：超过此时间未执行任何切换，则忽略 `idle_threshold` 强制执行一次       |

---

## 后台运行与自启动

### 后台运行

- **使用 EXE**: 直接双击运行 `WEScheduler.exe` 即可，它会自动最小化到系统托盘。
- **使用脚本**:
  - 启动: 双击运行 `scripts\run_bg.bat`。
  - 停止: 双击运行 `scripts\stop_bg.bat`。

### 开机自启动

1. 按下 `Win + R`，输入 `shell:startup` 并回车。
2. 将 `WEScheduler.exe` (或 `run_bg.bat`) 的**快捷方式**放入该文件夹即可。

### 监控日志

查看 `logs/scheduler.log` 以获取详细的运行日志。

## 更多文档

- `tag : value` 语义化规范参见：[SEMANTIC-REFACTOR-SPEC](docs/SEMANTIC-REFACTOR-SPEC.md)
- 未来功能路线图参见：[ROADMAP](docs/ROADMAP.md)
