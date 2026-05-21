# Repository Guidelines

## 工作立场

本项目仍处于 `0.x`，允许 breaking change；当旧接口、旧数据模型或旧页面心智妨碍正确设计时，直接改掉，不要堆兼容层。产品定位是面向高级 Wallpaper Engine 用户的本地上下文调度器，核心价值是无打扰切换、上下文感知。核心哲学是贴合并保持用户心流。

## 项目结构与模块组织

本仓库是 Windows-only Python 桌面应用：托盘宿主进程、本地 HTTP API，以及 Vue 3 Diagnostics 前端。

- `main.py` 是组合根，负责托盘模式、scheduler、history logger 与 dashboard API 接线。
- `core/` 放调度核心：sensor、policy、matcher、controller、actuator、executor 与 diagnostics 模型。
- `ui/` 放托盘 UI、Bottle API、pywebview 窗口和 Diagnostics DTO 转换。
- `utils/` 放配置加载、校验、日志、i18n、历史记录和 Wallpaper Engine 路径工具。
- `dashboard/` 是 Vue 3 + Vite + TypeScript 前端工作区，当前主线只聚焦 Diagnostics。
- `config/` 是本机真实运行配置，可用于真实运行与手工验证；不要当作 disposable fixture 覆盖或清空。
- `config.example/` 是发布与示例配置；`tests/` 放 pytest 测试。
- `docs/archived/done/` 是当前仍引用的规格；`docs/archived/deprecated/` 只作历史记录。

## 构建、测试与本地开发命令

本项目采用虚拟环境，目录为根目录的 `venv313/`

后端常用命令：

```bash
pip install -r requirements.txt
python main.py
python main.py --no-tray
python main.py config
python main.py config --config <config_dir>
pytest -q
```

`python main.py config` 是独立配置工具入口；指定配置目录时参数顺序应为 `python main.py config --config <config_dir>`。Windows 打包使用 `.\scripts\build.bat`。

Dashboard 联调可避免完整托盘流程：

```bash
python main.py --dashboard-api-port 38417
cd dashboard
npm run dev
```

如需其他端口，保持后端端口与前端 `DASHBOARD_API_PORT=<port>` 一致；默认端口是 `38417`。前端还可运行 `npm run lint`、`npm run type-check`、`npm run build-only`、`npm run format`、`npm run preview`。若组合构建遇到派生进程问题，分开跑 `type-check` 和 `build-only`。

## 编码风格与命名约定

Python 代码使用完整类型注解。代码应尽量自解释；会抛出异常的函数必须用 docstring 说明异常类型和触发条件。

前端遵循现有 Vue SFC、Tailwind token、Pinia store 与 `dashboard/src/components/ui/workbench/*` 原语。不要把 Diagnostics 扩成通用管理后台。除非同一改动同步修改宿主加载方式，否则保持 Vite `base: './'`、hash router、URL query locale 和 pywebview 本地加载。

## 测试规范

pytest 配置以 `pytest.ini` 为准，这是测试隔离契约的一部分：`testpaths = tests`、`addopts = --basetemp=.pytest_tmp`、`cache_dir = .pytest_tmp/cache`、`norecursedirs = data .pytest_tmp`。优先在仓库根目录运行 `pytest -q` 或指定目标测试；不要绕过 `pytest.ini`，也不要发明新的 basetemp/cache 目录。

新增测试应验证行为、边界条件或非显然回归。测试不是仪式；不要为了简单属性透传、平凡分支或无算法价值的断言写测试。前端改动至少验证 `npm run type-check` 和 `npm run build-only`。

## 配置与架构约束

运行时配置固定为 `config/` 下 6 个 YAML 文件：`scheduler.yaml`、`playlists.yaml`、`tags.yaml`、`activity.yaml`、`context.yaml`、`scheduling.yaml`。当任务需要真实配置时，读取 `config/`，不要用 `config.example/` 代替；测试或重写样例时优先使用测试 fixture、`.pytest_tmp/` 或 `config.example/`，不要无提示改写真实配置。不要新增 include 或隐藏配置层。

Diagnostics 应消费基于 `SchedulerTickTrace` 的 `GET /api/analysis/window` DTO，不要恢复旧 dashboard summary 契约。
