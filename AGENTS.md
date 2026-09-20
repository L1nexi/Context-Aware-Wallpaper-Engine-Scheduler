# Repository Guidelines

## 工作立场

本项目仍处于 `0.x`，允许 breaking change；当旧接口、旧数据模型或旧页面心智妨碍正确设计时，直接改掉，不要堆兼容层。产品定位是面向高级 Wallpaper Engine 用户的本地上下文调度器，核心价值是无打扰切换、上下文感知。核心哲学是贴合并保持用户心流。

## 项目结构与模块组织

本仓库是 Windows-only Python 桌面应用：托盘宿主进程、本地 HTTP API，以及 Vue 3 Diagnostics 前端。

- `main.py` 是启动 shim，负责 DPI 初始化并委托 `app/main.py`。
- `app/` 放应用入口、应用路径和持久事件日志。
- `configurations/` 放用户 Profile、Profile Compiler、原子持久化以及内部运行时配置模型。
- `core/models/` 放数据模型。
- `core/state/` 放运行时状态。
- `core/runtime/` 放 Scheduler、Engine 及 Profile 运行时应用组件。
- `core/policies/` 放 Policy 基类及具体实现。
- `core/sensors/` 放 Sensor 基类及具体实现。
- `ui/` 放托盘 UI、Bottle API、pywebview 窗口、Tick History 与 DTO 转换、i18n 和图标生成。
- `dashboard/` 是 Vue 3 + Vite + TypeScript 前端工作区，当前主线只聚焦 Diagnostics。
- `frontend/` 是最终替换 `dashboard/` 的 Vue 3 + shadcn-vue 产品界面工作区。
- `config/` 是本机真实运行配置目录，正式用户契约是其中的 `profile.json`；可用于真实运行与手工验证，不要当作 disposable fixture 覆盖或清空。
- `tests/` 放 pytest 测试。
- `docs/` 按规格生命周期管理，索引见 `docs/index.md`。根层文档是 active spec；`half-finished/` 是暂停但仍有价值的规格

### 调度管线（`engine.schedule()`）

```
Sense:    ContextManager.sense()       -> Context snapshot
Match:    Matcher.match()              -> Match
Plan:     plan_actuation()             -> ActPlan
Decide:   Controller.decide_action()   -> Decision
Execute:  Actuator.act()               -> ActionResult
Commit:   SchedulerState.commit()      -> cache persist
```

`Engine.schedule()` 接管完整调度流程：sense、match、plan、decide、execute，并返回 `ScheduleTrace`。`ProfileManager` 负责 Profile 加载、编译、持久化和应用队列，但不持有或代理 Engine；`WEScheduler` 根据配置目录创建并公开其 `profile_manager`，同时持有活动 `engine`，并编排生命周期、tick、暂停恢复、keep_alive、状态提交和 listener 通知。Profile 更新由 `ProfileManager` 入队，并且只由调度线程在两个 tick 之间应用到 Engine，不再通过文件热重载进入运行时。`Actuator` 是纯执行器：接收 `Decision` 做 target selection + CLI 调用。

关键组件：

- `core/runtime/engine.py` — 配置绑定的调度执行对象及候选替换边界
- `core/runtime/profile_manager.py` — Profile 读取、编译、持久化和单写者应用队列
- `app/event_logger.py` — 稀疏运行事件的持久化 JSONL 日志
- `core/state/tick_history.py` — 近期 `TickTrace` 的线程安全有界内存记录
- `ui/tick_history.py` — Tick History 的 HTTP DTO 转换
- `ui/tick_history_export.py` — Tick History 的脱敏、JSON formatter 和文件导出
- `core/runtime/act_plan.py` — WE 状态探测，输出 `ActPlan`
- `core/runtime/controller.py` — 调度决策器，输出 `Decision`
- `core/runtime/actuator.py` — 纯执行器
- `core/runtime/executor.py` — WE CLI 封装，内置 keep_alive 保活
- `core/models/trace.py` — `ScheduleTrace`、`TickTrace`、`Decision`、`ActPlan`、`BlockerEvaluation` 等 dataclass

## 构建、测试与本地开发命令

本项目采用虚拟环境，目录为根目录的 `.venv/`

后端常用命令：

```bash
pip install -r requirements.txt
python main.py
python main.py --no-tray
.\scripts\test.ps1 -q
```

Windows 打包使用 `.\scripts\build.bat`。

Dashboard 联调可避免完整托盘流程：

```bash
python main.py --dashboard-api-port 38417
cd dashboard
npm run dev
```

如需其他端口，保持后端端口与前端 `DASHBOARD_API_PORT=<port>` 一致；默认端口是 `38417`。前端还可运行 `npm run lint`、`npm run type-check`、`npm run build-only`、`npm run format`、`npm run preview`。若组合构建遇到派生进程问题，分开跑 `type-check` 和 `build-only`。

Python 文件修改完毕后，用 Ruff 格式化

```powershell
python -m ruff check . --fix
python -m ruff format .
```

## 编码风格与命名约定

Python 代码使用完整类型注解。代码应尽量自解释；会抛出异常的函数必须用 docstring 说明异常类型和触发条件。

前端遵循现有 Vue SFC、Tailwind token、Pinia store 与 `dashboard/src/components/ui/workbench/*` 原语。不要把 Diagnostics 扩成通用管理后台。除非同一改动同步修改宿主加载方式，否则保持 Vite `base: './'`、hash router、URL query locale 和 pywebview 本地加载。

## 测试规范

pytest 配置以 `pytest.ini` 为准，这是测试隔离契约的一部分：`testpaths = tests`、`norecursedirs = data .pytest_tmp`。优先通过 `.\scripts\test.ps1 -q` 或 `.\scripts\test.ps1 tests/test_foo.py -q` 运行测试；脚本会为每次运行分配 `.pytest_tmp/<run-id>/tmp` 和 `.pytest_tmp/<run-id>/cache`，让多个 pytest 进程可以并行运行且测试产物仍集中在 `.pytest_tmp/`。不要把多个 pytest 进程固定到同一个 basetemp/cache 目录。

新增测试应验证行为、边界条件或非显然回归。测试不是仪式；不要为了简单属性透传、平凡分支或无算法价值的断言写测试。前端改动至少验证 `npm run type-check` 和 `npm run build-only`。

## 配置与架构约束

正式配置入口是 `<config_dir>/profile.json`。`ProfileStore` 负责原子替换，`ProfileCompiler` 负责生成完整的内部 `SchedulerConfig`，`ProfileManager` 是 Profile 读取和应用的唯一入口；不要让 Sensor、Policy、Engine 或 `WEScheduler` 直接读取和操作 Profile，也不要绕过单写者应用队列修改运行时。Profile 不使用 revision 乐观锁；`version` 只表示数据结构版本。打扰档位是 setup 的填值快捷方式，Profile 只保存四个确定时间值。用户从产品预设的 Scene 中选择并绑定 Wallpaper Engine Playlist，不提供自定义 Scene、Tag、权重或通用配置树。测试使用 fixture 或 `.pytest_tmp/`，不要无提示改写真实配置。

Diagnostics 应消费由 `TickHistoryStore` 提供的 `GET /api/tick-history/window` DTO，不要恢复旧 dashboard summary 契约。

Tick History 是密集、近期、仅在内存中有界保留的逐 tick 调度记录；Event Log 是稀疏、持久化的启动、暂停、切换和执行失败事件，不要混用两者的命名。Tick History 导出读取 `TickHistoryStore` 的不可变窗口快照，复用现有 DTO，并由 JSON formatter 负责序列化和敏感字段裁剪。首版只脱敏 API Key 与地理位置，不裁剪活动窗口、进程、playlist 或本机路径。
