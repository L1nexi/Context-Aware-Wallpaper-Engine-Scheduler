# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Windows-only Python 桌面应用，基于用户上下文（活动窗口、空闲时长、CPU 负载、时段、季节、天气）自动切换 Wallpaper Engine 播放列表。通过 PyInstaller 打包为单一 `WEScheduler.exe`。

## 常用命令

### Python 后端

```bash
pip install -r requirements.txt
python main.py              # 托盘模式
python main.py --no-tray    # 控制台模式（调试用）
python main.py config       # 独立配置工具 TUI，不启动调度循环
pytest -q                   # 运行全部测试
pytest tests/test_foo.py    # 运行单个测试文件
```

### 代码检查 / 格式化（Ruff，Python 3.13，行宽 150）

虚拟环境位于 `venv313/`

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

**Sense-Think-Act-Trace-Commit 管线**（`WEScheduler` 1 秒 tick 循环）：

```
Sense:    ContextManager.sense()       -> Context snapshot
Think:    Matcher.evaluate()           -> Match (policy evaluations + playlist ranking)
Act:      plan_actuation() + Actuator  -> ActionResult (decision + execution)
Trace:    _build_tick_trace()          -> TickTrace (full tick record)
Commit:   _commit_tick()               -> cache persist, tick listeners, HistoryLogger

TickTrace -> AnalysisStore -> HTTP :0 -> Diagnostics SPA
                                        HistoryLogger.write() -> history-{YYYY}-{MM}.jsonl
```

- **Sensors** (`core/sensors.py`)：WindowSensor、IdleSensor、CpuSensor、FullscreenSensor、WeatherSensor、TimeSensor
- **Context** (`core/context.py`)：`Context` dataclass，`ContextManager` 每 tick 轮询传感器，`sense()` 返回深拷贝快照
- **Policies** (`core/policies.py`)：ActivityPolicy（双 EMA）、TimePolicy（Hann 窗插值）、SeasonPolicy（Hann 窗插值）、WeatherPolicy（四档连续强度）— 各输出归一化标签向量 + salience
- **Matcher** (`core/matcher.py`)：上下文向量与播放列表标签向量的余弦相似度匹配；通过 `tags.yaml` 递归展开 fallback
- **Actuator** (`core/actuator.py`)：将 matcher 结果与 actuation plan 桥接为 `ActionResult`，`ActionResult.cache_update` 是播放列表缓存的唯一写入权威
- **Executor** (`core/executor.py`)：Wallpaper Engine CLI 命令（`-control openPlaylist`、`-control nextWallpaper`）
- **Scheduler** (`core/scheduler.py`)：主编排器，tick 循环（Sense -> Think -> Act -> Trace -> Commit）、热重载、暂停/恢复、状态持久化
- **Trace** (`core/trace.py`)：`TickTrace`、`ActionResult`、`Decision` 等 dataclass 层级，用于 tick 内省

### UI 层

- **Tray** (`ui/tray.py`)：pystray 系统托盘，支持 i18n（中文/英文）
- **Dashboard HTTP** (`ui/dashboard.py`)：Bottle 服务器，`GET /api/analysis/window` 提供 tick 诊断数据
- **Dashboard Analysis** (`ui/dashboard_analysis.py`)：`AnalysisStore`（最多 1200 条 trace 的 deque），Pydantic DTO（camelCase 别名）
- **Dashboard 前端** (`dashboard/`)：Vue 3 SPA，Pinia + ECharts + Tailwind CSS v4

### Utils 层

- `config_loader.py` / `config_documents.py` / `runtime_config.py`：加载、校验（Pydantic v2，`extra="forbid"`）、合并 6 个 YAML 配置文件为 `SchedulerConfig`
- `history_logger.py`：JSONL 事件日志，按月分片
- `i18n.py`：根据系统语言自动切换中文/英文

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

pytest 配置以 `pytest.ini` 为准，必须在仓库根目录运行。`testpaths = tests`、`basetemp = .pytest_tmp`、`cache_dir = .pytest_tmp/cache`。

测试应验证行为、边界条件或非显然回归。不要为简单属性透传、平凡分支写测试。

前端改动至少验证 `npm run type-check` 和 `npm run build`。

## 配置与架构约束

- 真实运行配置读 `config/`；测试或样例用 `config.example/` 或测试 fixture，不要无提示改写真实配置
- 不要新增 include 或隐藏配置层
- Diagnostics 消费基于 `TickTrace` 的 `GET /api/analysis/window` DTO，不要恢复旧 dashboard summary 契约
- `docs/archived/done/` 是当前仍引用的规格；`docs/archived/deprecated/` 只作历史记录
