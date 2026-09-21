# Context Aware WE Scheduler

> 具备上下文感知与防打扰能力的 Wallpaper Engine 本地调度器。
> A Scheduler that maintains your flow.

WEScheduler 根据时段、季节、天气和当前活动判断适合的预设场景，并在不打断用户心流的时机控制 Wallpaper Engine。

## 产品模型

- 应用提供一组固定 Scene，例如日间工作、夜间休闲、四季、黄昏和雨天。
- 用户只负责启用需要的 Scene，并为它绑定一个 Wallpaper Engine Playlist。
- 多个 Scene 可以绑定同一个 Playlist；没有绑定的 Scene 不参与调度。
- Scene 的标签、权重、fallback、Policy 和内部阈值由产品维护，不作为用户配置暴露。
- 调度器完成语义匹配和控制决策后，才在执行边界把 Scene 集合降级为具体 Playlist。

## 核心能力

- 感知活动窗口、空闲时间、CPU、全屏状态、时段、季节和天气。
- 通过预设 Scene 表达产品语义，不要求用户理解标签向量。
- 在启动预热、用户活跃、高负载或全屏时延后切换。
- 使用语义连续性降低相近上下文之间的无谓切换。
- 通过 Tick History 导出近期调度事实，用于定位匹配和执行问题。

## 当前开发状态

项目处于 `0.x` 产品化迁移阶段。

- 正式持久化契约是 `config/profile.json`。
- 旧六 YAML 配置、配置 CLI 和用户自定义 Playlist 标签模型已经退出后端。
- 新的首次启动与设置界面正在 `frontend/` 中建设。
- 首次启动宿主已能在缺少 `profile.json` 时打开 setup，并在创建成功后启动调度器。
- `dashboard/` 仍暂时承载 Diagnostics，之后将由 `frontend/` 替换并删除。

## 开发运行

项目仅支持 Windows，使用仓库根目录的 `.venv/`。

```powershell
pip install -r requirements.txt
python main.py
.\scripts\test.ps1 -q
```

当前 Diagnostics 联调：

```powershell
python main.py --dashboard-api-port 38417
cd dashboard
npm run dev
```

当前 setup 前端联调：

```powershell
python main.py --dashboard-api-port 38417
cd frontend
npm run dev
```

后端格式化与检查：

```powershell
.\.venv\Scripts\python.exe -m ruff check . --fix
.\.venv\Scripts\python.exe -m ruff format .
```

## 配置与数据

- `config/profile.json`：唯一正式用户配置。
- `data/state.json`：Scheduler 跨进程状态。
- `data/events-YYYY-MM.jsonl`：稀疏运行事件。
- `data/tick-history/`：用户显式导出的近期调度记录。

不要手工构造内部 `SchedulerConfig`；Profile 的加载、编译、持久化和运行时应用统一由 `ProfileManager` 管理。
