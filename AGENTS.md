# AGENTS.md

本文件为在本仓库中工作的编码代理提供协作约束。

## 0. 工作立场

- 当前项目仍处于 `0.x`。允许 breaking change；如果旧接口、旧数据模型、旧页面心智已经妨碍正确设计，直接改，不要为了维持错误抽象而堆兼容层。
- 产品定位为面向高级 Wallpaper Engine 用户的本地上下文调度器。核心价值是自动调度、可解释诊断和可配置文本工作流，不是通用桌面管理后台。
- 当前前端基座以 `dashboard/` 为准，完整 Config Editor 与完整 History 页面已经暂停；不要继续把项目扩成管理后台。
- 做 breaking change 时，应该根据改动面大小决定是一次打通还是多次迭代。对于涉及大量改动的 breaking change，不应强求这一论工作中完全适配。

## 1. 信息优先级

出现冲突时，按下面顺序判断：

1. 实际代码与测试
2. 本文件 `AGENTS.md`
3. `docs/PRODUCT_DIRECTION.md`
4. `docs\CONFIGURATION_PHASE_PLAN.md`
5. `dashboard/docs/UI_ENGINEERING_SPEC.md`
6. `docs/frontend/CONFIGURATION_SPEC.md`

## 2. 当前代码现状

- 项目是 Windows-only Python 桌面应用：托盘宿主进程 + 本地 HTTP API + pywebview dashboard 子进程。
- `main.py` 是组合根。托盘模式下会创建 `WEScheduler`、`StateStore`、`DashboardHTTPServer`，并通过 `scheduler.on_tick` 推送实时状态。
- `scheduler.on_tick` 当前接收的是 `SchedulerTickTrace`
- Diagnostics 仍然是双进程结构：
  - 托盘宿主维护 scheduler、history logger 和 Bottle HTTP server
  - Diagnostics 子进程只负责打开 pywebview 窗口
- `ui/webview.py` 关闭窗口时只退出 diagnostics 子进程，不应影响托盘宿主。

### 2.1 `dashboard` 是新的前端基座，但仍处在建设中

`dashboard/` 当前已经具备这些基础：

- Vue 3 + Vite + TypeScript
- Tailwind CSS v4
- shadcn/reka 风格的基础组件层
- `src/components/ui/workbench/*` 桌面壳层原语
- `Pinia` 依赖和 `src/stores/` 目录
- `vue-router` hash 路由
- `base: './'`
- dashboard 应用已基本完成实现
- pywebview 已经接入 `dashboard/dist/` 目录并能正常加载

当前事实：

- 路由已经包含 `/dashboard`
  > 后续应统一改名为 diagnostics
- `/dashboard` 是正式诊断入口

总结：

- `dashboard` 是当前前端开发标准
- 近期前端主线应聚焦 Diagnostics 与轻量配置辅助，不应继续扩展完整管理后台式页面

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

- Dashboard / Diagnostics 分析相关的新后端事实源已经在 `core/*` 中建立完成。

### 2.3 Dashboard DTO 模型已经重构完成

- `GET /api/analysis/window` 已经重构为返回 `TickSnapshot` 列表，每个 `TickSnapshot` 由 `SchedulerTickTrace` 转换而来，具体定义参考 `ui/dashboard_analysis.py`
- 产品语义上该页面应视为 `Diagnostics`，不是通用 Dashboard。

### 2.4 Dashboard 的前后端联调辅助设施已上线

通过以下命令可以在指定端口启动 http 服务。然后在 [text](dashboard/vite.config.ts) 中配置服务代理即可在本地浏览器中进行开发调试，无需每次用 `python main.py` 启动

```bash
python main.py --dashboard-api-port 38417
cd dashboard
npm run dev
```

## 3. 前端重写准则

- 产品路线以 `docs/PRODUCT_DIRECTION.md` 为准。
- 前端工程规范以 `dashboard/docs/UI_ENGINEERING_SPEC.md` 为准。
- 配置系统目标与契约以 `docs/frontend/CONFIGURATION_SPEC.md` 为准。
- Diagnostics 细节可参考 `docs/archived/done/DASHBOARD_ANALYSIS_SPEC.md` 与同目录 implementation spec。
- `docs/archived/frozen/CONFIG_EDITOR_SPEC.md`、`CONFIG_EDITOR_IMPLEMENTATION_SPEC.md`、`CONFIG_EDITOR_R5_SPEC.md` 已冻结，只作历史设计记录。
- `docs/archived/frozen/HISTORY_SPEC.md` 已冻结，完整 History 页面不再是当前主线。

### 3.1 前端改动的强约束

除非你在同一个改动中连带修改宿主加载方式，否则这些约束应保持不变：

- Vite `base` 保持 `./`
- Router 使用 `createWebHashHistory()`
- Locale 继续通过 dashboard URL query 传入
- pywebview 仍然加载本地 HTTP server 暴露的页面

## 4. 后端与 API 现状

`ui/dashboard.py` 当前提供这些接口：

- `GET /api/health`
- `GET /api/analysis/window`

相关事实：

- `HistoryLogger` 已支持 `read()`、`aggregate()`、月度分片 JSONL 和 `last_event_id`
- `utils/config_loader.py` 当前已收紧 `policies` 下未知 key：`PoliciesConfig.model_config = ConfigDict(extra="forbid")`

这意味着：

- 如果你在做配置系统重构，应优先参考 `docs/frontend/CONFIGURATION_SPEC.md`，推进固定 6 文件 YAML、Release zip 分发的 example 配置、严格 tag、playlist runtime map、Activity matcher、validate before swap 和配置辅助工具；不要实现运行时 builtin preset + override 或 include
- 如果你在做 Dashboard 分析页重构，应直接基于 `SchedulerTickTrace` 新建更正确的分析接口，而不是继续扩展旧 `TickState`
-

## 5. 目录地图

- `core/`: 调度核心，包含 sensor / policy / matcher / controller / actuator / executor
- `ui/`: 托盘 UI、Bottle dashboard server、pywebview 窗口
- `utils/`: 配置、日志、i18n、路径解析、历史记录
- `dashboard/`: 新前端工作区与工程基座
- `docs/PRODUCT_DIRECTION.md`: 当前产品路线与阶段优先级
- `docs/frontend/`: 当前仍活跃的前端 / 配置规格
- `docs/archived/done/`: 已完成的历史规格和参考设计
- `docs/archived/frozen/`: 已冻结、不再作为主线推进的历史规格
- `tests/`: Python pytest 测试

## 6. 常用命令

项目已经启用了虚拟环境，位于 `venv313/`.

### Python / backend

```bash
pip install -r requirements.txt
python main.py
python main.py --no-tray
pytest -q
```

### `dashboard/` 新前端工作区

```bash
cd dashboard
npm install
npm run lint
npm run type-check
npm run build-only
```

说明：

- 在某些受限代理环境里，`npm run build` 可能因为 `run-p` 派生进程限制报 `spawn EPERM`。
- 遇到这种情况，直接分开跑 `npm run type-check` 和 `npm run build-only`。

## 7. 测试与验证基线

- 当前仓库已经有正式 pytest 测试。根据改动范围进行决定。对于小范围改动不进行相关测试，由人工进行 review 验证；对于中等范围改动，跑相关测试；对于大范围改动跑全量测试。

- `dashboard/` 能分别通过：
  - `npm run type-check`
  - `npm run build-only`

## 8. 面向代理的行动建议

- 如果任务属于新前端建设，优先在 `dashboard/`、`docs/frontend/*` 对齐的数据模型和 `ui/dashboard.py` 的新接口上动手。
- 如果任务属于配置体验，默认走文本配置工作流：固定 6 文件 YAML、Release zip 分发的 example 配置、Pydantic normalized runtime config、validate before swap。GUI 只做打开、验证、重载、错误展示、扫描播放列表等辅助能力；tray 的 `Apply Current Match Now` 是独立手动调度入口，不应和 reload 混在一起。
- 如果任务需要 breaking change，需要评估改动量，如果改动面偏小，就连同调用方、测试、静态资源接线一起改，不要把过渡态长期留在主线上；如果改动面大，则允许迭代适配。迭代过程中也并不强求集成测试通过。
- 不要把 `dashboard` 的工程规范退化回旧式做法：大段 scoped CSS、页面私有全局类、绕开 token 的硬编码颜色/尺寸、用局部状态假装全局状态。
- 尽量复用 `dashboard/src/components/ui/workbench/*`、现有 token、Tailwind utility 和 Pinia 方向。
- **IMPORTANT** 测试不是一种仪式。测试的目的是用来验证逻辑。如果对于简单直接的逻辑，你应该做的是正面验证逻辑的完全性。对于复杂的逻辑，你应该做的是覆盖边界条件和潜在的误用场景。
- **IMPORTANT**不要把测试滥用为“为了测试而测试”。如果你发现自己在写一个测试用例只是为了简单的做属性透传、分支检测，而不是复杂的边界条件、算法结果，那么它很可能就是不必要的。你 **必须** 丢弃无用的测试。

## 9. 编码规范

- 完整类型注解
- 允许代码自文档化，减少不必要的 docs-string。但对于抛出异常的函数，必须 docstring 说明异常类型和触发条件。
