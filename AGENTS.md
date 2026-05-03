# AGENTS.md

本文件为在本仓库中工作的编码代理提供协作约束。内容基于 2026-05-04 的代码现状编写，用于补齐并更新 `CLAUDE.md` 中已经过时的部分。

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
6. `CLAUDE.md`

说明：

- `CLAUDE.md` 仍有不少高价值背景信息，但其中“测试尚不存在”“前端现状”等描述已经部分过时。

## 2. 当前代码现状

- 项目是 Windows-only Python 桌面应用：托盘宿主进程 + 本地 HTTP API + pywebview dashboard 子进程。
- `main.py` 是组合根。托盘模式下会创建 `WEScheduler`、`StateStore`、`DashboardHTTPServer`，并通过 `scheduler.on_tick` 推送实时状态。
- `scheduler.on_tick` 当前接收的是 `SchedulerTickTrace`，不是旧的 `(scheduler, context, result)` 风格回调。
- Dashboard 仍然是双进程结构：
  - 托盘宿主维护 scheduler、history logger 和 Bottle HTTP server
  - Dashboard 子进程只负责打开 pywebview 窗口
- `ui/webview.py` 关闭窗口时只退出 dashboard 子进程，不应影响托盘宿主。

### 2.1 当前运行时仍然使用 legacy dashboard

以下代码说明“今天真正跑起来的前端”仍是 `dashboard/`，不是 `dashboard-v2/`：

- `ui/dashboard.py::_resolve_static_root()` 指向 `dashboard/dist`
- `scripts/build.bat` 用 `--add-data "dashboard\\dist;dashboard\\dist"` 打包静态资源
- `WEScheduler.spec` 只嵌入 `dashboard\\dist`

结论：

- 你在 `dashboard-v2/` 中做的修改，默认不会自动进入当前运行时或最终打包产物。
- 如果任务目标是“让新前端真正跑起来”，不能只改 `dashboard-v2/`，还要同步改运行时接线和打包输入。

### 2.2 `dashboard-v2` 是新的前端基座，但还没有接线完成

`dashboard-v2/` 当前已经具备这些基础：

- Vue 3 + Vite + TypeScript
- Tailwind CSS v4
- shadcn/reka 风格的基础组件层
- `src/components/ui/workbench/*` 桌面壳层原语
- `Pinia` 依赖和 `src/stores/` 目录
- `vue-router` hash 路由
- `base: './'`

但它仍然不是功能完成态：

- 路由目前只有 `/`
- `src/views/DashboardView.vue` 仍是占位页
- `src/stores/` 目前为空
- `src/composables/useApi.ts` 仍沿用旧 `TickState` + `/api/state` `/api/ticks` 的临时轮询模型

结论：

- `dashboard-v2` 是当前前端开发标准和重写主战场
- 但它还没有完成对旧前端的功能替换，也没有接入正式运行时

### 2.3 旧 `dashboard/` 仍是现实入口，但不是未来标准

- `dashboard/` 依然是当前 pywebview 实际加载的 SPA
- 它是 legacy 前端，不应再作为新的工程标准来源
- 不要在这里做大规模体验打磨，除非：
  - 这是修复当前运行时必需的问题
  - 或者这是把 `dashboard-v2` 接入正式运行时之前的过渡改动

### 2.4 Dashboard 分析后端重构已完成第一阶段

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
- `ui/dashboard.py::build_tick_state()` 当前只是把 `SchedulerTickTrace` 适配成 legacy `TickState`，用于旧 `/api/state` 与 `/api/ticks` 路径。

结论：

- Dashboard 分析相关的新后端事实源已经在 `core/*` 中建立完成。
- 下一步如果继续推进 Dashboard 重写，优先从 `SchedulerTickTrace -> analysis API -> dashboard-v2` 这条链往前走，不要再回到 `TickState` 上补字段。

## 3. 前端重写准则

- 前端工程规范以 `dashboard-v2/docs/UI_ENGINEERING_SPEC.md` 为准。
- 页面级目标与后端契约目标以这两份文档为准：
  - `docs/frontend/DASHBOARD_ANALYSIS_SPEC.md`
  - `docs/frontend/CONFIG_EDITOR_SPEC.md`
- 新前端优先围绕正确模型重建，不要继续被旧 `TickState` 页面心智绑住。
- 如果旧 `/api/state`、`/api/ticks`、裸 `GET /api/config` 契约妨碍新模型，允许直接 redesign。
- 只要 redesign 是为了建立更正确的分析模型或配置模型，就不要因为“怕 breaking change”而退回旧结构。

### 3.1 前端改动的强约束

除非你在同一个改动中连带修改宿主加载方式，否则这些约束应保持不变：

- Vite `base` 保持 `./`
- Router 使用 `createWebHashHistory()`
- Locale 继续通过 dashboard URL query 传入
- pywebview 仍然加载本地 HTTP server 暴露的页面

### 3.2 如果你要让 `dashboard-v2` 接管正式运行时

至少同步检查这些位置：

- `ui/dashboard.py`
- `ui/webview.py`
- `scripts/build.bat`
- `WEScheduler.spec`
- 新旧 `dist/` 目录的来源与目标
- 当前 URL / hash 路由 / `?locale=` 假设

## 4. 后端与 API 现状

`ui/dashboard.py` 当前提供这些接口：

- `GET /api/state`
- `GET /api/health`
- `GET /api/ticks`
- `GET /api/history`
- `GET /api/history/aggregate`
- `GET /api/config`
- `POST /api/config`
- `GET /api/tags/presets`
- `GET /api/playlists/scan`
- `GET /api/we-path`

相关事实：

- `TickState`、`StateStore`、Bottle app 注入点 `_build_app()` 都在 `ui/dashboard.py`
- `build_tick_state()` 当前把 `SchedulerTickTrace` 映射成 legacy `TickState`
- `HistoryLogger` 已支持 `read()`、`aggregate()`、月度分片 JSONL 和 `last_event_id`
- `utils/config_loader.py` 当前仍允许 `policies` 下未知 key：`PoliciesConfig.model_config = ConfigDict(extra="allow")`

这意味着：

- 如果你在做 GUI Config 重构，可以按 `docs/frontend/CONFIG_EDITOR_SPEC.md` 把未知 policy key 收紧为禁止，但要同步改后端、前端和测试
- 如果你在做 Dashboard 分析页重构，应直接基于 `SchedulerTickTrace` 新建更正确的分析接口，而不是继续扩展旧 `TickState`

## 5. 目录地图

- `core/`: 调度核心，包含 sensor / policy / matcher / controller / actuator / executor
- `ui/`: 托盘 UI、Bottle dashboard server、pywebview 窗口
- `utils/`: 配置、日志、i18n、路径解析、历史记录
- `dashboard/`: 当前接入正式运行时的 legacy Vue 前端
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

### `dashboard/` 当前运行时前端

```bash
cd dashboard
npm install
npm run type-check
npm run build-only
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
- `dashboard/` 与 `dashboard-v2/` 当前都能分别通过：
  - `npm run type-check`
  - `npm run build-only`

改动时的最低验证要求：

- 改 `ui/dashboard.py`、`utils/history_logger.py`、`utils/we_path.py`、`utils/config_loader.py` 后，至少跑相关 pytest；能跑全量时优先跑全量
- 改 `dashboard-v2/` 后，至少跑 `npm run type-check`；涉及 UI 结构或资源产物时再跑 `npm run build-only`
- 改 `dashboard/` 后，至少确保 `npm run build-only` 仍能产出 `dashboard/dist`

## 8. 面向代理的行动建议

- 先判断任务是在修“当前运行时”，还是在推进“前端重写目标”。这两类任务的着力点不同。
- 如果任务属于新前端建设，优先在 `dashboard-v2/`、`docs/frontend/*` 对齐的数据模型和 `ui/dashboard.py` 的新接口上动手，而不是继续堆旧页面状态。
- 如果任务属于 Dashboard 重写的下一阶段，默认假设 core 诊断链已经完成；除非发现 spec 与实现冲突，否则不要回退去重做 `core/controller.py`、`core/actuator.py`、`core/diagnostics.py` 的基础建模。
- 如果任务需要 breaking change，就连同调用方、测试、静态资源接线一起改，不要把过渡态长期留在主线上。
- 不要把 `dashboard-v2` 的工程规范退化回旧式做法：大段 scoped CSS、页面私有全局类、绕开 token 的硬编码颜色/尺寸、用局部状态假装全局状态。
- 尽量复用 `dashboard-v2/src/components/ui/workbench/*`、现有 token、Tailwind utility 和 Pinia 方向，而不是回到 `dashboard/` 的 Element Plus 心智。

## 9. 何时参考 `CLAUDE.md`

以下内容仍建议参考 `CLAUDE.md`：

- 调度架构总览
- sensor / policy / matcher / controller 的设计说明
- runtime artifact 说明
- Windows-only 平台背景

但在以下问题上，应以当前代码和本文件为准，而不是直接照抄 `CLAUDE.md`：

- 前端现状
- 测试覆盖现状
- 需要不需要维持旧 dashboard 契约
