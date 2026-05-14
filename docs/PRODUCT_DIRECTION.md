# Product Direction

本文档记录 2026-05-10 scope reset 后的产品路线。它用于约束后续实现优先级，避免项目继续向通用桌面管理后台扩张。

## 1. 定位

项目定位为面向高级 Wallpaper Engine 用户的本地上下文调度器。

核心价值：

- 自动根据上下文切换 Wallpaper Engine 播放列表。
- 能解释“为什么切了”和“为什么没切”。
- 用高级用户可审阅、可复制、可版本管理的文本配置表达调度规则。

非目标：

- 不做面向纯小白的一键式通用软件。
- 不做完整 Wallpaper Engine 管理器。
- 不做管理后台式 Config Editor。
- 不做长期历史分析产品。
- 不让 Dashboard / History / Config 页面吞掉调度器主线。

## 2. 阶段 1：打包减重 - [DONE]

目标：证明当前 88 MB 级别 exe 不是产品必然成本，先排除打包环境污染和错误依赖收集。

已知判断：

- `dashboard/dist` 约 1 MB，不是 exe 体积主因。
- 主要体积风险来自 PyInstaller 收集到的非必要依赖，例如 Qt、numpy、matplotlib、IPython / Jupyter、tkinter、Pythonwin 等。
- `pywebview` 当前运行时指定 `edgechromium`，不应默认打进 Qt backend。

工作内容：

- 使用干净 venv 构建，只安装运行所需依赖。
- 在 PyInstaller spec / build 脚本中显式排除非运行依赖。
- 确认 pywebview 只收集 Edge Chromium 相关运行组件。
- 重新测量 exe 体积，并记录主要包体归因。

验收标准：

- 能解释 exe 体积来源。
- 若减重后进入约 `35-50 MB` 区间，则暂不为了体积砍业务能力。
- 若仍超过约 `60 MB`，再评估是否把 Diagnostics 做成可选构建或进一步拆分依赖。

更新：

- 通过环境清理和依赖排除，已将 exe 体积从 88 MB 减少到约 25 MB，符合预期范围。

## 3. 阶段 2：配置体验改线 - [DONE]

目标：停止推进完整 GUI Config Editor，改为高级用户友好的文本配置工作流，并把配置系统变成 Diagnostics 可解释性的事实基础。

正式契约见 [CONFIGURATION_SPEC.md](./frontend/CONFIGURATION_SPEC.md)，实施拆分见 [CONFIGURATION_PHASE_PLAN.md](./CONFIGURATION_PHASE_PLAN.md)。

当前事实：

- 主配置入口是外部 `config/` 目录，固定读取 6 个必需 YAML 文件：`scheduler.yaml`、`playlists.yaml`、`tags.yaml`、`activity.yaml`、`context.yaml`、`scheduling.yaml`。
- Release zip 直接附带一份普通 `config/` example 配置和 `Config Tools.bat`；配置文件不内嵌进 exe。
- `playlists` 在配置和 runtime 中都使用 map；key 直接等于 Wallpaper Engine 播放列表名。
- tag id 使用无前缀形式；所有 playlist、activity、fallback 和固定 policy 输出 tag 都必须在 `tags.yaml` 中声明。
- ActivityPolicy 使用 `process` / `title` 简写入口加完整 `matchers[]`，加载后统一 normalize 为 matcher 列表。
- `runtime.wallpaper_engine_path: null` 表示自动检测；显式路径必须有效，且无效时不会回退到自动检测。
- YAML reload 是 validate-before-swap：失败时保留上一份有效 runtime，成功时重建 runtime components 并迁移允许保留的状态。
- Reload Config 是配置操作，不会立刻触发 playlist switch 或 wallpaper cycle。
- Tray 已提供 `Apply Current Match Now` / `立即应用当前匹配`，作为独立的一次性手动调度入口。
- Dashboard HTTP 层已经收敛为 Diagnostics-only，不再承载配置编辑、配置辅助或独立 History 页面。

配置文件边界：

- 不支持 `include` 或任意拆分文件能力；固定文件名就是配置契约。
- YAML anchors、aliases 和 merge keys 允许作为单文件书写辅助，但解析后仍必须通过同一套 schema 与 cross-file 校验。
- Pydantic schema defaults 只用于字段级默认值，不提供隐藏的 playlist、tag、activity rule 或 policy layer。
- 禁用资源或策略使用显式 `enabled: false`。

配置辅助入口：

1. `WEScheduler.exe config` / `python main.py config` 进入 numbered TUI。
2. Validate config 使用启动和热重载同一套 loader 校验，并输出 config folder path、resolved WE path、playlist count、enabled policies。
3. Detect Wallpaper Engine 显示 configured value、resolved executable path 和 Wallpaper Engine `config.json` 状态，不写回 YAML。
4. Scan Wallpaper Engine playlists 输出纯播放列表名和 copy-ready `playlists.yaml` snippet，不自动生成 tag、颜色或 display 名。

验收标准：

- 用户可以只改某个配置文件，不需要面对完整配置树。
- 配置错误能定位到具体 source file 和 field path。
- 配置 reload 失败不破坏当前运行状态。
- Release zip 中包含 example config、`Config Tools.bat` 和 `WEScheduler.exe`。
- Dashboard / Diagnostics 不再被配置编辑或长期 History 方向牵引。

## 4. 阶段 3：Diagnostics，而不是 Dashboard

目标：把 Dashboard 收敛成调度诊断工具，只服务近期解释和排错。

参考历史规格：

- [DASHBOARD_ANALYSIS_SPEC.md](./archived/done/DASHBOARD_ANALYSIS_SPEC.md)
- [DASHBOARD_ANALYSIS_IMPLEMENTATION_SPEC.md](./archived/done/DASHBOARD_ANALYSIS_IMPLEMENTATION_SPEC.md)

核心职责：

- 回答当前为什么是这个播放列表。
- 回答刚才为什么切换。
- 回答刚才为什么没有切换。
- 展示 `Sense -> Think -> Act`。
- 区分 `matchedPlaylist` 与 `activePlaylist`。
- 展示 policy contribution、controller blocker、actuation outcome。

非职责：

- 不做通用 Dashboard。
- 不做长期 History。
- 不做配置主编辑器。
- 不做运营后台式信息架构。

可保留内容：

- 近期 tick window。
- 顶部 timeline / scrub。
- 当前 tick 三栏诊断。
- 最近事件的轻量摘要。
- 当前配置路径、最近 reload 结果、最近配置错误。

验收标准：

- 用户能在一个近期 tick 上直接看出为什么切或为什么没切。
- hover / snapshot 交互不触发逐 tick 请求。
- 页面不会继续膨胀成长期统计或配置中心。

## 5. 阶段 4：History 降级

目标：保留运行证据，停止把 History 扩展成独立产品模块。

冻结的历史方案见 [HISTORY_SPEC.md](./archived/frozen/HISTORY_SPEC.md)。

保留：

- `HistoryLogger`。
- 月度 JSONL 事件日志。
- switch / cycle / pause / resume / config reload / error 等关键事件。
- 简单读取或导出能力。
- Diagnostics 中的轻量 Recent Events。

暂停或删除主线优先级：

- 独立 History 页面。
- 长期趋势图。
- Gantt 时间线。
- 多维筛选器。
- composition / bucket / drilldown 分析。
- 长期画像和统计报表。

验收标准：

- 事件日志继续作为调试和证据来源存在。
- 前端不再把 History 当成独立产品模块推进。
- 需要历史信息时，优先在 Diagnostics 内提供短窗口辅助信息。

## 6. 推荐执行顺序

按风险和收益排序：

1. 打包减重，先去掉错误体积来源。
2. 配置体验改线，建立新配置系统主线。
3. Diagnostics 收敛，保留解释调度的核心 UI。
4. History 降级，避免继续扩展独立历史产品。

这个顺序不是说 Diagnostics 不重要，而是先把体积和配置这两个方向性成本压住，再继续打磨诊断体验。
