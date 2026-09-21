# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## 项目概述

本项目是 Windows-only Python 桌面应用，根据用户上下文自动选择产品预设 Scene，并在执行边界控制 Wallpaper Engine Playlist。项目处于 `0.x`，允许 breaking change，不为已删除的旧配置路径增加兼容层。

## 常用命令

```powershell
pip install -r requirements.txt
python main.py
.\scripts\test.ps1 -q
.\.venv\Scripts\python.exe -m ruff check . --fix
.\.venv\Scripts\python.exe -m ruff format .
```

当前 Diagnostics 前端：

```powershell
python main.py --dashboard-api-port 38417
cd dashboard
npm run type-check
npm run build-only
```

Windows 打包使用 `.\scripts\build.bat`。

## 调度管线

```text
Sense:    ContextManager.sense()       -> Context snapshot
Match:    Matcher.match()              -> Match
Plan:     plan_actuation()             -> ActPlan
Decide:   Controller.decide_action()   -> Decision
Execute:  Actuator.act()               -> ActionResult
Commit:   SchedulerState.commit()      -> cache persist
```

`Engine.schedule()` 接管完整调度流程。`WEScheduler` 持有活动 Engine，负责编排生命周期、tick、安全点应用、暂停恢复、keep_alive、状态提交和 listener 通知。

- `ProfileManager` 独占 Profile 的加载、编译、持久化和单写者应用队列，但不持有或代理 Engine。
- `Matcher` 比较上下文向量和产品预设 Scene 的标签向量。
- `Controller` 对 Scenes 做语义连续性与防打扰决策。
- `Actuator` 是纯执行器，只在执行边界把 Scenes 降级为具体 Playlist 并调用 Wallpaper Engine CLI。
- `FactualPlaylistStatus`、Playlist 扫描、`target_playlist` 和 `openPlaylist` 属于 Wallpaper Engine 边界，不应改名为 Scene。

## 配置模型

正式用户契约只有 `<config_dir>/profile.json`：

- 用户从固定 `SceneId` 中选择场景并绑定 Wallpaper Engine Playlist。
- 多个 Scene 可以绑定同一个 Playlist；未绑定的 Scene 不进入运行时。
- Scene 标签、权重、fallback、Policy 和内部阈值由 `ProfileCompiler` 持有。
- 不提供自定义 Scene、Tag、Policy 开关或通用配置树。
- Profile 更新只能经 `ProfileManager` 的单写者队列在两个 tick 之间应用。

旧六 YAML loader、配置 CLI、示例配置和旧 tuning 工具已经删除，不要恢复。

## 目录

- `configurations/`：Profile、Profile Compiler、原子持久化和内部运行时配置模型。
- `core/models/`：领域模型与 trace。
- `core/runtime/`：Engine、Scheduler、ProfileManager、Matcher、Controller、Actuator 和 Wallpaper Engine 边界。
- `core/state/`：Scheduler 状态、Tick History 与 Action Event 写入。
- `ui/`：托盘、Bottle API、pywebview、Tick History DTO 与导出。
- `dashboard/`：待删除的 Vue 3 Diagnostics 前端。
- `frontend/`：最终替换 `dashboard/` 的 Vue 3 + shadcn-vue 产品界面。
- `config/`：本机真实配置目录，不得作为 disposable fixture 覆盖或清空。
- `tests/`：pytest 行为测试。

## 测试与约束

- 优先使用 `.\scripts\test.ps1`；脚本为每次运行分配独立 `.pytest_tmp` 目录。
- 测试验证公开行为，系统边界才使用 mock。
- 不要让 Sensor、Policy、Engine 或 `WEScheduler` 直接读取 Profile。
- 不要绕过 ProfileManager 队列修改运行时。
- Tick History 是密集、近期、内存有界的逐 tick 记录；Event Log 是稀疏、持久化的运行事件。
- 当前 Diagnostics 消费 `GET /api/tick-history/window`，不要恢复旧 summary 契约。
- 前端改动至少验证 `npm run type-check` 和 `npm run build-only`。
