# Context Aware WE Scheduler

一个基于上下文感知的 Wallpaper Engine 智能调度器。

## 核心特性
- **智能感知**：根据当前活动窗口、系统时间、季节甚至实时天气自动切换壁纸。
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
   - (可选) 填入 OpenWeatherMap API Key 以启用天气联动。

4. **运行**:
   ```bash
   python main.py
   ```

## 详细文档
更多设计细节和开发说明请参考 [docs/README_DEV.md](docs/README_DEV.md)。
