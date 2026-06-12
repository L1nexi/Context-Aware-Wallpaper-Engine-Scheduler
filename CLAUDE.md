# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Windows-only Python 桌面应用，基于用户上下文（活动窗口、空闲时长、CPU 负载、时段、季节、天气）自动切换 Wallpaper Engine 播放列表。通过 PyInstaller 打包为单一 `WEScheduler.exe`。

## 常用命令

### Python 后端

源码位于仓库根目录的 `app/`、`configurations/`、`core/`、`ui/` 包中。

```bash
pip install -r requirements.txt
python main.py              # 托盘模式
python main.py --no-tray    # 控制台模式（调试用）
python main.py config       # 独立配置工具 TUI，不启动调度循环
pytest -q                   # 运行全部测试
pytest tests/test_foo.py    # 运行单个测试文件
```

### 代码检查 / 格式化（Ruff，Python 3.13，行宽 150）

虚拟环境位于 `.venv/`

```powershell
python -m ruff check . --fix
python -m ruff format .
```

### 构建可执行文件

```powershell
.\scripts\build.bat
```

### Dashboard 前端（Vue 3 + Vite + TypeScript）

```bash
cd dashboard
npm run dev           # 开发服务器
npm run build         # 生产构建
npm run type-check    # TypeScript 类型检查
npm run lint          # ESLint + oxlint
npm run format        # Prettier
```

Dashboard 联调（避免完整托盘流程）：

```bash
python main.py --dashboard-api-port 38417
cd dashboard && npm run dev
```

后端端口需与前端 `DASHBOARD_API_PORT=<port>` 保持一致，默认端口 `38417`。

## 架构

**调度管线**（`engine.schedule()`）：

```
Sense:    ContextManager.sense()       -> Context snapshot
Match:    Matcher.match()              -> Match
Plan:     plan_actuation()             -> ActPlan
Decide:   Controller.decide_action()   -> Decision
Execute:  Actuator.act()               -> ActionResult
Commit:   SchedulerState.commit()      -> cache persist

TickTrace -> AnalysisStore -> HTTP :0 -> Diagnostics SPA
                                        HistoryLogger.write() -> history-{YYYY}-{MM}.jsonl
```

`Engine.schedule()` 接管完整调度流程：sense、match、plan、decide、execute，并返回 `ScheduleTrace`。`WEScheduler` 只负责热重载、暂停恢复、keep_alive、添加 tick 元信息、提交状态和通知 listener。Execute 阶段是纯执行（target selection + CLI 调用）。

- **Sensors** (`core/sensors/`)：WindowSensor、IdleSensor、CpuSensor、FullscreenSensor、WeatherSensor、TimeSensor
- **Context** (`core/models/context.py`)：`Context` dataclass，`ContextManager` 每 tick 轮询传感器，`sense()` 返回深拷贝快照
- **Policies** (`core/policies/`)：ActivityPolicy（双 EMA）、TimePolicy（Hann 窗插值）、SeasonPolicy（Hann 窗插值）、WeatherPolicy（四档连续强度）— 各输出归一化标签向量 + salience
- **Matcher** (`core/runtime/`)：上下文向量与播放列表标签向量的余弦相似度匹配；通过 `tags.yaml` 递归展开 fallback
- **ActPlan** (`core/runtime/act_plan.py`)：探测 WE 实际状态，决定 `DecisionMode`（NORMAL/MANUAL/RECOVERY/PAUSE）和 `active_playlists`
- **Controller** (`core/runtime/controller.py`)：纯调度决策器，在 Decide 阶段接收 `ActPlan` + `Match` + `Context`，输出 `Decision`（switch/cycle/hold/pause）。通过语义连续性评分（weighted Jaccard + 衰减）区分 switch vs cycle，通过 CPU/全屏/idle 门控评估 blocker
- **Actuator** (`core/runtime/actuator.py`)：纯执行器，接收 `Decision` 做 target selection + CLI 调用，不持有 controller
- **Executor** (`core/runtime/executor.py`)：Wallpaper Engine CLI 命令（`-control openPlaylist`、`-control nextWallpaper`），内置 keep_alive 保活（每 5 tick 发 `getWallpaper`）
- **Scheduler** (`core/runtime/scheduler.py`)：生命周期编排器，tick 循环中调用 `Engine.schedule()`、添加 tick 元信息、提交状态、通知 listeners，并处理热重载、暂停/恢复、状态持久化
- **Models** (`core/models/trace.py`)：`ScheduleTrace`、`TickTrace`、`ActionResult`、`Decision`、`ActPlan`、`BlockerEvaluation` 等 dataclass 层级，用于调度内省
- **State** (`core/state/`)：`PersistedState`、`SchedulerState`、`ActionHistory` 等运行时状态管理

### UI 层 (`ui/`)

- **Tray**：pystray 系统托盘，支持 i18n（中文/英文）
- **Dashboard HTTP**：Bottle 服务器，`GET /api/analysis/window` 提供 tick 诊断数据
- **Dashboard Analysis**：`AnalysisStore`（最多 1200 条 trace 的 deque），Pydantic DTO（camelCase 别名）
- **Dashboard 前端** (`dashboard/`)：Vue 3 SPA，Pinia + ECharts + Tailwind CSS v4

### 配置层 (`configurations/`)

- 配置加载、校验（Pydantic v2，`extra="forbid"`）、合并 6 个 YAML 配置文件为 `SchedulerConfig`

### 应用层 (`app/`)

- `history_logger`：JSONL 事件日志，按月分片
- `i18n`：根据系统语言自动切换中文/英文

## 配置

运行时配置固定为 `config/` 下 6 个 YAML 文件（通过 mtime 指纹热重载）：
`scheduler.yaml`、`playlists.yaml`、`tags.yaml`、`activity.yaml`、`context.yaml`、`scheduling.yaml`

含默认值文档的示例配置：`config.example/`

## 编码风格与约定

- Python：完整类型注解，`from __future__ import annotations`，使用 Python 3.13 现代特性（StrEnum、dataclasses、Pydantic v2）
- 会抛出异常的函数必须用 docstring 说明异常类型和触发条件
- 项目处于 `0.x` — 允许 breaking change，不要堆兼容层
- 前端：遵循现有 Vue SFC 模式、Tailwind token、Pinia store 和 `dashboard/src/components/ui/workbench/*` 原语。不要把 Diagnostics 扩成通用管理后台
- 保持 Vite `base: './'`、hash router、URL query locale、pywebview 本地加载

## 测试

pytest 配置以 `pytest.ini` 为准，必须在仓库根目录运行。`testpaths = tests`、`basetemp = .pytest_tmp`、`cache_dir = .pytest_tmp/cache`。不要并行启动多个 pytest 进程；固定 `.pytest_tmp` 会让并行进程竞争清理同一目录，尤其在 Windows 上容易触发权限错误。

测试应验证行为、边界条件或非显然回归。不要为简单属性透传、平凡分支写测试。

前端改动至少验证 `npm run type-check` 和 `npm run build`。

## 配置与架构约束

- 真实运行配置读 `config/`；测试或样例用 `config.example/` 或测试 fixture，不要无提示改写真实配置
- 不要新增 include 或隐藏配置层
- Diagnostics 消费基于 `TickTrace` 的 `GET /api/analysis/window` DTO，不要恢复旧 dashboard summary 契约
- `docs/` 按规格生命周期管理，索引见 `docs/index.md`。根层文档是 active spec；`half-finished/` 是暂停但仍有价值的规格
