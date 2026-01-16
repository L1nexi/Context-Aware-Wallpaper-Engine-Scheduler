# Context Aware WE Scheduler

一个基于上下文感知的 Wallpaper Engine 智能调度器。

## 核心特性

- **智能感知**：根据当前活动窗口、系统时间、季节或实时天气自动切换壁纸。
- **防打扰**：仅在用户空闲时切换壁纸，区分“播单切换”与“播单内轮播”，支持独立冷却时间。
- **平滑过渡**：采用指数移动平均算法平滑活动状况，避免瞬时窗口切换导致的频繁变动。
- **向量化搜素及配置**：使用基于向量相似度的推荐策略，并支持对歌单进行向量化配置。

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

### 2. 配置

无论使用哪种方式，你都需要进行以下配置：

1. **准备配置文件**:
   - 将 `scheduler_config.example.json` 复制并重命名为 `scheduler_config.json`（如果是使用 `build.bat` 或下载的发布包，通常已自动生成）。
2. **修改关键参数**:
   - `we_path`: 指向你本地的 Wallpaper Engine 路径（例如 `...\\wallpaper64.exe`）。
   - `playlists`: 填入你在 WE 中定义的播放列表名称。
     - `tags`: 为每个播放列表定义触发标签及其权重。
   - `policies`: 根据你的使用习惯调整进程匹配规则（不区分大小写）。
     - `weight_scale`: 调整策略的重要程度。
     - `ActivityPolicy.smoothing_window`: 调整活动窗口平滑时间（秒）。
   - `disturbance`: 调整切换频率（支持“播单切换”与“壁纸轮播”独立计时）。
     - `idle_threshold`: 空闲多少秒后允许切换壁纸。
     - `min_interval`: 播单切换的最小间隔（秒）。
     - `wallpaper_interval`: 播单内轮播的间隔（秒）。
     - `force_interval`: 强制切换的最大间隔（秒）。
   - (推荐) 填入 OpenWeatherMap API Key 以启用天气策略。

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

## 详细文档

更多设计细节和开发说明请参考 [docs/README_DEV.md](docs/README_DEV.md)。
