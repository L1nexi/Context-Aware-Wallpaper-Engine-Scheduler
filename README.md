# Context Aware WE Scheduler

一个基于上下文感知的 Wallpaper Engine 智能调度器。

## 核心特性

- **智能感知**：根据当前活动窗口、系统时间、季节或实时天气自动切换壁纸。
- **Sense-Think-Act 架构**：清晰的模块化设计，确保决策逻辑与执行逻辑分离。
- **双层防打扰设计**：区分“播单切换”与“播单内轮播”，支持独立冷却时间，仅在用户空闲时执行。
- **平滑过渡**：采用 EMA (指数移动平均) 算法平滑活动状况，避免瞬时窗口切换导致的频繁变动。
- **大小写不敏感**：进程名匹配自动忽略大小写，配置更省心。
- **鲁棒性**：自动监控并恢复 Wallpaper Engine 进程。

## 快速开始

1. **克隆仓库**:

   ```bash
   git clone <your-repo-url>
   cd Context-Aware-WE-Scheduler
   ```

2. **安装依赖**:

   ```bash
   pip install -r requirements.txt
   ```

3. **配置**:

   - 将 `scheduler_config.example.json` 复制并重命名为 `scheduler_config.json`。
   - 修改 `we_path` 为你本地的 Wallpaper Engine 路径。
   - 修改 `playlists` 为你的 wallpaper engine 播放列表名称。目前仅仅在“从不”调度策略上的播放列表上进行过测试。
   - 修改 `policies.activity.rules | title_rules` 以匹配你常用的应用程序和窗口标题（进程名匹配不区分大小写）。
   - 修改 `weight_scale` 以分配各个策略的重要程度。
   - 修改 `disturbance` 参数以控制切换频率及行为（支持播单切换与壁纸轮播独立计时）。
   - (可选) 填入 OpenWeatherMap API Key 以启用天气联动。

4. **运行**:

   ```bash
   python main.py
   ```

## 后台运行与自启动

### 后台运行

- **启动**: 双击运行 `run_bg.bat`。
- **停止**: 双击运行 `stop_bg.bat`。

### 开机自启动

1. 按下 `Win + R`，输入 `shell:startup` 并回车。
2. 将 `run_bg.bat` 的**快捷方式**放入该文件夹即可。

### 监控日志

```powershell
Get-Content -Path "logs/scheduler.log" -Wait -Tail 20
```

## 详细文档

更多设计细节和开发说明请参考 [docs/README_DEV.md](docs/README_DEV.md)。
