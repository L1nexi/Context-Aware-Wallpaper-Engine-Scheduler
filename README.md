# Context Aware WE Scheduler

一个基于上下文感知的 Wallpaper Engine 智能调度器。

## 核心特性

- **智能感知**：根据当前活动窗口、系统时间、季节或实时天气自动切换壁纸。
- **防打扰设计**：仅在用户空闲或特定时机执行切换，避免在工作或游戏时造成卡顿。
- **平滑过渡**：采用 EMA (指数移动平均) 算法平滑状态切换，防止壁纸频繁闪烁。
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
   - 修改 `policies.activity.rules | title_rules` 已匹配你常用的应用程序和窗口标题。
   - 修改 `weight_scale` 以分配各个策略的重要程度
   - 修改 `disturbance` 参数以控制切换频率及行为。
   - (可选) 填入 OpenWeatherMap API Key 以启用天气联动。

4. **运行**:

   ```bash
   python main.py
   ```

## 后台运行

```bat
run_bg.bat
```

监控日志：

```bash
Get-Content -Path "logs/scheduler.log" -Wait -Tail 20
```

杀死进程：

```pwsh
taskkill /F /IM pythonw.exe
```

## 详细文档

更多设计细节和开发说明请参考 [docs/README_DEV.md](docs/README_DEV.md)。

```

```
