# Repository Guidelines

## 工作立场

本项目仍处于 `0.x`，允许 breaking change；当旧接口、旧数据模型或旧页面心智妨碍正确设计时，直接改掉，不要堆兼容层。产品定位位于 `README.md`

## 项目结构与模块组织

本仓库是 Windows-only Python 桌面应用：托盘宿主进程、本地 HTTP API，以及可视化前端。

- `main.py` 是启动 shim，负责 DPI 初始化并委托 `app/main.py`。
- `app/` 放应用入口、应用路径、日志和历史记录。
- `configurations/` 放配置加载、校验和配置模型。
- `core/models/` 放数据模型。
- `core/state/` 放运行时状态。
- `core/runtime/` 放 Scheduler 的运行时组件。
- `core/policies/` 放 Policy 基类及具体实现。
- `core/sensors/` 放 Sensor 基类及具体实现。
- `ui/` 放托盘 UI、Bottle API、pywebview 窗口、DTO 转换、i18n 和图标生成。
- `frontend/` 是 Shadcn-vue + Tailwind CSSv4 + Vite + TypeScript 的未完成工作区。
- `config/` 是本机真实运行配置，可用于真实运行与手工验证；不要当作 disposable fixture 覆盖或清空。
- `config.example/` 是发布与示例配置；`tests/` 放 pytest 测试。
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

`Engine.schedule()` 接管完整调度流程：sense、match、plan、decide、execute，并返回 `ScheduleTrace`。`WEScheduler` 负责热重载、暂停恢复、keep_alive、添加 tick 元信息、提交状态和通知 listener。`Actuator` 是纯执行器：接收 `Decision` 做 target selection + CLI 调用。

关键组件：

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
python main.py config
python main.py config --config <config_dir>
.\scripts\test.ps1 -q
```

`python main.py config` 是独立配置工具入口；指定配置目录时参数顺序应为 `python main.py config --config <config_dir>`。Windows 打包使用 `.\scripts\build.bat`。

Frontend 联调可避免完整托盘流程：

```bash
python main.py --dashboard-api-port 38417
cd frontend
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

## 测试规范

pytest 配置以 `pytest.ini` 为准，`testpaths = tests`、`norecursedirs = data .pytest_tmp`。优先通过 `.\scripts\test.ps1 -q` 或 `.\scripts\test.ps1 tests/test_foo.py -q` 运行测试；脚本会为每次运行分配 `.pytest_tmp/<run-id>/tmp` 和 `.pytest_tmp/<run-id>/cache`，让多个 pytest 进程可以并行运行且测试产物仍集中在 `.pytest_tmp/`。

新增测试应验证行为、边界条件或非显然回归。不要为了简单属性透传、平凡分支或无算法价值的断言写测试。前端改动至少验证 `npm run type-check` 和 `npm run build-only`。

## 配置与架构约束

运行时配置固定为 `config/` 下 6 个 YAML 文件：`scheduler.yaml`、`playlists.yaml`、`tags.yaml`、`activity.yaml`、`context.yaml`、`scheduling.yaml`。当任务需要真实配置时，读取 `config/`，不要用 `config.example/` 代替；测试或重写样例时优先使用测试 fixture、`.pytest_tmp/` 或 `config.example/`，不要无提示改写真实配置。不要新增 include 或隐藏配置层。
