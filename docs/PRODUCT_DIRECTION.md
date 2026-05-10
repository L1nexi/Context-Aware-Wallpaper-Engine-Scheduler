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

## 3. 阶段 2：配置体验改线

目标：停止推进完整 GUI Config Editor，改为高级用户友好的文本配置工作流，并把配置系统变成后续 Diagnostics 可解释性的事实基础。

正式方向见 [CONFIGURATION_SPEC.md](./frontend/CONFIGURATION_SPEC.md)。阶段 2 细化访谈结论已记录在该文档的“访谈决策记录（2026-05-10）”章节。

范围边界：

- 不提供旧 `scheduler_config.json` 到新 YAML 目录的自动迁移工具。
- 不保留长期 JSON / YAML 双轨加载模型。
- 打包产物直接附带完整 example 配置；旧字段对照只帮助用户手动重建配置。
- 旧 `GET /api/config` / `POST /api/config` 如果暂时保留，只能视为 legacy 或内部调试接口，不能继续牵引完整 GUI Config Editor。
- GUI 只做配置辅助，不承担配置事实源；配置文件才是一等入口。

核心决策：

- 主配置格式转向受限 YAML。
- 配置目录分层：`scheduler.yaml`、`playlists.yaml`、`tags.yaml`、`activity.yaml`、`context.yaml`、`scheduling.yaml`。
- playlist key 直接等于 Wallpaper Engine 播放列表名。
- tag id 去掉 `#` 前缀，使用无前缀 lower-kebab-case。
- 颜色可选，手写时优先支持命名色或无 `#` hex。
- 不做运行时 builtin preset + user override；使用打包 example 配置 + Pydantic schema defaults。
- 阶段 2 不做 `include`；固定读取 6 个必需 YAML 文件，缺失即 validate error。
- `playlists` 在配置和 runtime `AppConfig` 中都使用 map，key 直接等于 Wallpaper Engine 播放列表名。
- tag 必须显式声明；Time / Season / Weather 输出固定 tag 名，也必须在 `tags.yaml` 中声明。
- ActivityPolicy 使用简写入口加完整 matcher：`process` 简写默认 exact，`title` 简写默认 contains，完整 matcher 支持 exact / regex / contains。
- `runtime.wallpaper_engine_path: null` 表示自动检测；显式路径无效时 validate 失败，检测成功不自动写回 YAML。
- 运行时仍消费 Pydantic normalized `AppConfig`。
- reload 必须 validate before swap；失败时继续使用上一份有效配置。
- 配置错误需要携带 source file 与字段路径，便于 GUI 和 Diagnostics 展示。
- tray 后续提供 `Apply Current Match Now`，作为独立手动调度动作；reload 不自动触发切换。

阶段 2 交付面：

1. 新配置目录与 example config
   - 明确默认配置目录位置。
   - 打包附带最小可运行的 6 文件 YAML example 配置。
   - 示例配置必须覆盖 playlist、tag、activity、context、scheduling 的常见路径。

2. YAML loader 与受限解析
   - 只接受受限 YAML 子集，禁止 anchors、aliases、merge keys 等不利于诊断的能力。
   - 不读取 include，固定文件名是阶段 2 的配置契约。
   - 解析结果不得直接进入运行时，必须进入 Pydantic 校验和 normalize。

3. 配置模型 breaking change
   - playlist 从 array 改为 map，并同步修改 runtime 模型。
   - tag 改为无 `#` 前缀的严格声明模型。
   - ActivityPolicy 统一 normalize 为 matcher 列表，匹配优先级为 `title > process`，同 source 内 `exact > regex > contains`。

4. Runtime adapter
   - 将新 YAML 语义转换为当前运行时可消费的 raw dict。
   - 继续以 normalized `AppConfig` 作为 scheduler、policy、executor 的运行时契约。
   - breaking change 要一次性更新调用方、测试、示例配置和打包资源。

5. Validate before swap
   - reload 时先完整读取、转换、校验、normalize。
   - 成功后原子替换当前有效配置，并记录 reload success event。
   - 失败时保留上一份有效配置，并记录 last config error。
   - 错误信息至少包含文件、字段路径、错误类型和面向用户的简短说明。
   - reload 成功后全量重建 runtime components，但迁移 pause、active playlist、controller cooldown 和过滤后的 ActivityPolicy EMA。

6. 配置辅助 API / GUI
   - API 优先服务 `validate`、`reload`、`last error`、`effective config summary`、`config folder path`、`scan playlists`。
   - Dashboard 配置页降级为工具面板，而不是多页表单编辑器。
   - 保留能帮助用户回到文本工作流的入口，不继续扩展完整编辑控件。

GUI 边界：

- 保留 Open Config Folder。
- 保留 Validate Config。
- 保留 Reload Config。
- 保留 Show Last Config Error。
- 保留 Scan Wallpaper Engine Playlists。
- 可保留打开 / 查看打包 example 配置的入口。
- 不做完整表单式 Config Editor。

建议实施顺序：

1. 在 `utils/config_loader.py` 附近建立新 YAML loader 与 source location 错误模型。
2. 建立打包 example 配置和 YAML 示例资源。
3. 完成 playlist map、严格 tag、Activity matcher 到 runtime `AppConfig` 的 adapter。
4. 接入 WE path resolve、executor readiness 和 validate before swap reload。
5. 收缩 dashboard 配置页面为配置辅助工具面板。
6. 后续独立实现 tray `Apply Current Match Now`，不阻塞配置运行时核心落地。
7. 清理旧 Config Editor 牵引的路由、文档引用和测试假设。

第一批实现边界：

- 先完成配置运行时核心：6 文件 YAML loader、playlist runtime map、严格 tag、Activity matcher、新 WE path 语义、validate before swap、example config 与测试。
- tray `Apply Current Match Now` 和 Dashboard 配置辅助收缩可以作为紧随其后的独立任务分步实现。

验收标准：

- 用户可以只改某个配置文件，不需要面对完整配置树。
- 配置错误能定位到具体文件和字段路径。
- 配置 reload 失败不破坏当前运行状态。
- 用户能看出当前 effective config 来自哪个配置目录、最后一次 reload 是否成功。
- 打包 example 配置能通过 validate 并启动调度器。
- 旧 JSON 配置不会被自动迁移；需要手动重建时，文档给出字段对照和最小示例。
- 旧 Config Editor 文档和页面不会继续牵引主线。

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
