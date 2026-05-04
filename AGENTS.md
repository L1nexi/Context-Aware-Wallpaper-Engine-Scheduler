# AGENTS.md

本文件为在本仓库中工作的编码代理提供协作约束。内容基于 2026-05-04 的代码现状编写。

## 0. 工作立场

- 当前项目仍处于 `0.x`。允许 breaking change；如果旧接口、旧数据模型、旧页面心智已经妨碍正确设计，直接改，不要为了维持错误抽象而堆兼容层。
- 当前处于前端重写期。所有前端工程规范、UI 分层、组件边界、状态管理约定，以 `dashboard-v2/` 为准。
- 做 breaking change 时，优先一次性把调用方、测试、静态资源接线和打包链一起改完，不要留下长期双轨并存的半迁移状态。

## 1. 信息优先级

出现冲突时，按下面顺序判断：

1. 实际代码与测试
2. 本文件 `AGENTS.md`
3. `dashboard-v2/docs/UI_ENGINEERING_SPEC.md`
4. `docs/frontend/DASHBOARD_ANALYSIS_SPEC.md`
5. `docs/frontend/CONFIG_EDITOR_SPEC.md`

## 2. 当前代码现状

- 项目是 Windows-only Python 桌面应用：托盘宿主进程 + 本地 HTTP API + pywebview dashboard 子进程。
- `main.py` 是组合根。托盘模式下会创建 `WEScheduler`、`StateStore`、`DashboardHTTPServer`，并通过 `scheduler.on_tick` 推送实时状态。
- `scheduler.on_tick` 当前接收的是 `SchedulerTickTrace`
- Dashboard 仍然是双进程结构：
  - 托盘宿主维护 scheduler、history logger 和 Bottle HTTP server
  - Dashboard 子进程只负责打开 pywebview 窗口
- `ui/webview.py` 关闭窗口时只退出 dashboard 子进程，不应影响托盘宿主。

### 2.1 `dashboard-v2` 是新的前端基座，但仍处在建设中

`dashboard-v2/` 当前已经具备这些基础：

- Vue 3 + Vite + TypeScript
- Tailwind CSS v4
- shadcn/reka 风格的基础组件层
- `src/components/ui/workbench/*` 桌面壳层原语
- `Pinia` 依赖和 `src/stores/` 目录
- `vue-router` hash 路由
- `base: './'`
- dashboard 应用已基本完成实现
- pywebview 已经接入 `dashboard-v2/dist/` 目录并能正常加载

但它仍然不是功能完成态：

- 路由目前只有 `/`
- History 和 Config Editor 页面还没做

结论：

- `dashboard-v2` 是当前前端开发标准和重写主战场

### 2.2 Dashboard 分析后端重构已完成第一阶段

与 Dashboard 分析页直接相关的 core 重构已经完成第一阶段，当前事实如下：

- `core/diagnostics.py` 已经定义新的中立 tick 诊断模型：
  - `MatchEvaluation`
  - typed `PolicyEvaluation` 变体
  - `ControllerDecision`
  - `ActuationOutcome`
  - `SchedulerTickTrace`
- `core/controller.py` 现在是动作决策唯一来源；`reason_code` 在 controller 内部生成。
- `core/actuator.py` 现在负责：
  - 调用 controller 获取 decision
  - 执行 executor 副作用
  - 在成功执行后回写 controller 冷却状态
  - 产出 `ActuationOutcome`
- `core/scheduler.py` 当前每个活动 tick 都会产出 `SchedulerTickTrace`。

结论：

- Dashboard 分析相关的新后端事实源已经在 `core/*` 中建立完成。

### 2.3 Dashboard DTO 模型已经重构完成

- `GET /api/analysis/window` 已经重构为返回 `TickSnapshot` 列表，每个 `TickSnapshot` 由 `SchedulerTickTrace` 转换而来，具体定义参考 `ui/dashboard_analysis.py`

### 2.4 Dashboard 的前后端联调辅助设施已上线

通过以下命令可以在指定端口启动 http 服务。然后在 [text](dashboard-v2/vite.config.ts) 中配置服务代理即可在本地浏览器中进行开发调试，无需每次用 `python main.py` 启动

```bash
python main.py --dashboard-api-port 38417
cd dashboard-v2
npm run dev
```

## 3. 前端重写准则

- 前端工程规范以 `dashboard-v2/docs/UI_ENGINEERING_SPEC.md` 为准。
- 页面级目标与后端契约目标以这两份文档为准：
  - `docs/frontend/DASHBOARD_ANALYSIS_SPEC.md`
  - `docs/frontend/CONFIG_EDITOR_SPEC.md`
- 如果旧 `/api/state`、`/api/ticks`、裸 `GET /api/config` 契约妨碍新模型，允许直接 redesign。
- 只要 redesign 是为了建立更正确的分析模型或配置模型，就不要因为“怕 breaking change”而退回旧结构。

### 3.1 前端改动的强约束

除非你在同一个改动中连带修改宿主加载方式，否则这些约束应保持不变：

- Vite `base` 保持 `./`
- Router 使用 `createWebHashHistory()`
- Locale 继续通过 dashboard URL query 传入
- pywebview 仍然加载本地 HTTP server 暴露的页面

## 4. 后端与 API 现状

`ui/dashboard.py` 当前提供这些接口：

- `GET /api/health`
- `GET /api/history`
- `GET /api/history/aggregate`
- `GET /api/config`
- `POST /api/config`
- `GET /api/tags/presets`
- `GET /api/playlists/scan`
- `GET /api/we-path`

相关事实：

- `HistoryLogger` 已支持 `read()`、`aggregate()`、月度分片 JSONL 和 `last_event_id`
- `utils/config_loader.py` 当前仍允许 `policies` 下未知 key：`PoliciesConfig.model_config = ConfigDict(extra="allow")`

这意味着：

- 如果你在做 GUI Config 重构，可以按 `docs/frontend/CONFIG_EDITOR_SPEC.md` 把未知 policy key 收紧为禁止，但要同步改后端、前端和测试
- 如果你在做 Dashboard 分析页重构，应直接基于 `SchedulerTickTrace` 新建更正确的分析接口，而不是继续扩展旧 `TickState`

## 5. 目录地图

- `core/`: 调度核心，包含 sensor / policy / matcher / controller / actuator / executor
- `ui/`: 托盘 UI、Bottle dashboard server、pywebview 窗口
- `utils/`: 配置、日志、i18n、路径解析、历史记录
- `dashboard-v2/`: 新前端工作区与工程基座
- `docs/frontend/`: 新前端页面级规格
- `tests/`: Python pytest 测试

## 6. 常用命令

### Python / backend

```bash
pip install -r requirements.txt
python main.py
python main.py --no-tray
pytest -q
```

### `dashboard-v2/` 新前端工作区

```bash
cd dashboard-v2
npm install
npm run lint
npm run type-check
npm run build-only
```

说明：

- 在某些受限代理环境里，`npm run build` 可能因为 `run-p` 派生进程限制报 `spawn EPERM`。
- 遇到这种情况，直接分开跑 `npm run type-check` 和 `npm run build-only`。

## 7. 测试与验证基线

- 当前仓库已经有正式 pytest 测试，不要再假设“测试尚未建立”。
- 2026-05-04 的本地基线：
  - `pytest -q` 通过
  - 结果为 `92 passed`
- ``dashboard-v2/` 能分别通过：
  - `npm run type-check`
  - `npm run build-only`

改动时的最低验证要求：

- 改 `ui/dashboard.py`、`utils/history_logger.py`、`utils/we_path.py`、`utils/config_loader.py` 后，至少跑相关 pytest；能跑全量时优先跑全量
- 改 `dashboard-v2/` 后，至少跑 `npm run type-check`；涉及 UI 结构或资源产物时再跑 `npm run build-only`

## 8. 面向代理的行动建议

- 先判断任务是在修“当前运行时”，还是在推进“前端重写目标”。这两类任务的着力点不同。
- 如果任务属于新前端建设，优先在 `dashboard-v2/`、`docs/frontend/*` 对齐的数据模型和 `ui/dashboard.py` 的新接口上动手。
- 如果任务属于 Dashboard 重写的下一阶段，默认假设 core 诊断链已经完成；除非发现 spec 与实现冲突，否则不要回退去重做 `core/controller.py`、`core/actuator.py`、`core/diagnostics.py` 的基础建模。
- 如果任务需要 breaking change，就连同调用方、测试、静态资源接线一起改，不要把过渡态长期留在主线上。
- 不要把 `dashboard-v2` 的工程规范退化回旧式做法：大段 scoped CSS、页面私有全局类、绕开 token 的硬编码颜色/尺寸、用局部状态假装全局状态。
- 尽量复用 `dashboard-v2/src/components/ui/workbench/*`、现有 token、Tailwind utility 和 Pinia 方向。
