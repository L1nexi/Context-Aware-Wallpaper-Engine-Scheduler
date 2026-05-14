# Configuration Phase Plan

本文档把配置体验改线拆成可实施、可验证、可分步合并的阶段。目标是避免一次性吞下完整配置系统重构，同时不留下长期双轨模型。

详细产品与行为契约见：

- [PRODUCT_DIRECTION.md](./PRODUCT_DIRECTION.md)
- [CONFIGURATION_SPEC.md](./frontend/CONFIGURATION_SPEC.md)

## 0. 总体策略

阶段 2 的完整范围较大，包含配置格式、runtime model、ActivityPolicy、WE path、reload、GUI 辅助和 tray 手动调度。实施时不要把这些绑成一个不可审查的大改动。

推荐切法：

1. 先实现配置运行时核心。
2. 再收缩 GUI 配置辅助入口。
3. 最后实现 tray `Apply Current Match Now`。

配置运行时核心仍然较大，因此继续拆成下面的阶段。每个阶段都应能通过自己的 focused tests；跨阶段临时代码可以存在，但必须在阶段说明里写明删除点，不能变成长期兼容层。

## 1. 非目标

- 不提供旧 `scheduler_config.json` 到 YAML 的迁移工具。
- 不实现运行时 builtin preset + user override。
- 不实现 `include` 或任意拆分文件能力。
- 不保留长期 JSON / YAML 双轨加载模型。
- 不继续扩展完整 GUI Config Editor。
- 不在 Diagnostics 中加入手动副作用按钮。

## 2. 阶段 0：基线保护与切入点整理 [SKIPPED]

目标：在重构前固定现有行为和风险边界，减少后续大改时的盲区。

文件范围：

- `utils/config_loader.py`
- `tests/test_config_loader.py`
- `core/matcher.py`
- `core/policies.py`
- `core/scheduler.py`
- `core/actuator.py`
- `core/executor.py`
- `tests/test_core_diagnostics.py`
- `tests/test_dashboard_api.py`

工作内容：

- 补充或整理当前 JSON loader、playlist list、ActivityPolicy、hot reload、executor no-op 行为的 characterization tests。
- 明确哪些测试是旧模型保护，后续阶段会删除或改写。
- 在测试命名里标出 legacy 行为，避免误以为它们是新方向长期契约。
- 不做产品行为改变。

验证：

```bash
pytest tests/test_config_loader.py tests/test_core_diagnostics.py tests/test_dashboard_api.py -q
```

完成标准：

- 现有相关测试通过。
- 后续要替换的 legacy 测试边界明确。

## 3. 阶段 1：YAML 目录 loader 与 example 配置 [DONE]

目标：建立固定 6 文件 YAML 的解析、错误定位和 GitHub Release zip 分发用 example 配置，但暂不切换 scheduler 主运行入口。

文件范围：

- 新增或重构 `utils/config_loader.py` 附近的 YAML domain loader。
- 新增 Release zip 分发用 config 配置目录，作为 exe 旁边的普通文件进入发布压缩包。
- `tests/test_config_loader.py` 或新增配置 loader 测试文件。
- Release 打包脚本中压缩包文件布局配置。

工作内容：

- 固定读取：
  - `scheduler.yaml`
  - `playlists.yaml`
  - `tags.yaml`
  - `activity.yaml`
  - `context.yaml`
  - `scheduling.yaml`
- 缺任一文件时报 validate error。
- `scheduler.yaml > version` 必填且必须为 `2`。
- 不禁止 anchors、aliases、merge keys。
- 不支持 `include`。
- 不读取旧 JSON。
- 产出中间 YAML domain model 或 raw dict。
- 错误至少包含 source file 和字段路径。
- 提供完整 example 配置，默认 `runtime.wallpaper_engine_path: null`。

阶段边界：

- 这一阶段可以只测试 loader，不要求 scheduler 立即消费 YAML。
- 不引入 runtime preset / override。
- 不实现 GUI 和 tray。

验证：

```bash
pytest tests/test_config_loader.py -q
```

重点测试：

- 6 文件缺失报错。
- version 缺失 / 不等于 2 报错。
- config 配置能被解析。
- source file + field path 出现在错误中。

完成标准：

- YAML 文件契约可测试。
- config 配置作为 Release zip 中的普通文件存在，不内嵌到 exe。
- 旧 JSON 不参与 YAML loader。

## 4. 阶段 2：Runtime 配置模型切换 [DONE]

目标：把运行时事实源切到新模型，消除 playlist list、`#tag` 等旧心智。

文件范围：

- `utils/config_loader.py`
- `core/matcher.py`
- `core/policies.py`
- `core/diagnostics.py`
- `ui/dashboard_analysis.py`
- `tests/test_config_loader.py`
- `tests/test_core_diagnostics.py`
- `tests/test_dashboard_api.py`

工作内容：

- `AppConfig.playlists` 改为 map。
- playlist key 即 Wallpaper Engine 播放列表名。
- 删除或停止依赖 `PlaylistConfig.name` 作为事实源。
- tag id 改为无 `#` 前缀。
- 所有引用 tag 必须在 `tags.yaml` 声明。
- Time / Season / Weather 输出固定无前缀 tag：
  - Time：`dawn`、`day`、`sunset`、`night`
  - Season：`spring`、`summer`、`autumn`、`winter`
  - Weather：`clear`、`cloudy`、`rain`、`storm`、`snow`、`fog`
- Matcher、Diagnostics DTO、Dashboard metadata 适配 playlist map。

阶段边界：

- 这是 breaking phase，应一次性更新调用方和测试。
- 不保留 “YAML map -> runtime list” 的长期 adapter。
- 可以保留短期局部转换用于测试夹具，但不能作为正式 runtime 事实源。

验证：

```bash
pytest tests/test_config_loader.py tests/test_core_diagnostics.py tests/test_dashboard_api.py -q
```

重点测试：

- playlist map 正常匹配。
- 未声明 tag 报错。
- policy 固定输出 tag 需要在 `tags.yaml` 声明。
- Diagnostics 能展示 playlist display / color。
- 旧 `#tag` 测试被替换为无前缀 tag。

完成标准：

- Runtime 只消费新 playlist map 和无前缀 tag。
- 相关 Python 测试更新并通过。

## 5. 阶段 3：ActivityPolicy matcher 新模型 [DONE]

目标：把 ActivityPolicy 改成简写入口 + normalized matcher，解决 exact / regex / contains、`.exe` fallback 和冲突优先级。

文件范围：

- `utils/config_loader.py`
- `core/policies.py`
- `core/diagnostics.py`
- `ui/dashboard_analysis.py`

- 工作内容：

- 支持 `activity.process` 简写，默认 `match: exact`。
- 支持 process exact 的 `.exe` 等价。
- 支持 `activity.title` 简写，默认 `match: contains`。
- 支持完整 `activity.matchers[]`：
  - `source: process | title`
  - `match: exact | regex | contains`
  - `pattern`
  - `tag`
  - `case_sensitive`
- 默认大小写不敏感。
- 单 matcher 只输出一个 tag。
- loader normalize 后 runtime 只看统一 matcher 列表。
- 匹配优先级：
  - source：`title > process`
  - match：`exact > regex > contains`
  - literal 同类更长 pattern 优先
  - regex 同类按声明顺序

阶段边界：

- 不引入多 tag rule。
- 不引入 per-rule priority。
- 不引入 per-rule weight / confidence。

验证：

> 无集成测试要求

完成标准：

- ActivityPolicy runtime 不再直接依赖旧 `process_rules` / `title_rules` map。
- Diagnostics 能解释 matched source、rule、tag。

## 6. 阶段 4：WE path、启动期 resolve 与 actuation outcome [DONE]

目标：把 Wallpaper Engine 路径问题从 executor 隐式 no-op 改成启动 / reload 前的硬校验，并把执行层收缩成简单的成功 / 失败语义。

文件范围：

- `main.py`
- `utils/we_path.py`
- `utils/config_loader.py`
- `core/executor.py`
- `core/actuator.py`
- `core/diagnostics.py`
- `core/event_logger.py`
- `core/scheduler.py`

工作内容：

- `runtime.wallpaper_engine_path: null` 表示自动检测。
- 显式路径必须存在且可执行；无效时报 validate error。
- 显式路径无效时不 fallback 自动检测。
- 自动检测成功不写回 YAML。
- 自动检测失败时启动失败；scheduler 不进入运行态。
- Executor 不再静默 no-op。
- Scheduler 在 initialize / reload 前完成 WE path resolve。
- Executor 只接收已解析的 exe 路径，命令接口只返回 `bool` 表示是否执行成功。
- Actuator 只有在真实执行成功后更新 controller cooldown 和 active playlist。
- 运行时命令失败只记录通用执行失败事实，不引入细粒度 executor result taxonomy。
- tray / console 在 initialize 失败后直接退出，不继续以降级模式运行。

阶段边界：

- 不实现 GUI 写回检测路径。
- 不在每个 tick 前反复全盘检测。
- 不实现 tray Manual Apply。

验证：

- 默认以源码 review 和启动边界手工验证为主。
- 如果补自动化验证，只保留高价值边界：
  - 显式无效路径不会 fallback 自动检测
  - `wallpaper_engine_path: null` 自动检测失败会导致 initialize 失败
  - Actuator 只有在 Executor 返回 `True` 时才提交状态

完成标准：

- unresolved WE path 不再进入 runtime。
- Executor 不再把失败隐藏成普通 no-op。

## 7. 阶段 5：Validate before swap reload [DONE]

目标：让 YAML reload 成为可靠的运行时替换边界，失败不破坏当前运行状态，成功迁移允许保留的 state。

文件范围：

- `utils/config_loader.py`
- `core/scheduler.py`
- `core/policies.py`
- `core/controller.py`
- `core/event_logger.py`
- `utils/history_logger.py`
- `tests/test_config_loader.py`
- `tests/test_core_diagnostics.py`
- 可能新增 scheduler reload focused tests。

工作内容：

- Reload 先完整读取、转换、校验、normalize。
- Reload 阶段同样完成 WE path resolve；显式无效路径或 `null` 自动检测失败都视为 reload failure。
- 成功后原子替换 runtime components。
- 失败时旧 runtime 完全保留。
- 成功 reload 后迁移：
  - pause / pause_until
  - current playlist 字符串
  - controller cooldown timestamps
  - 过滤后的 ActivityPolicy EMA
- ActivityPolicy EMA 保留当前压缩状态，新 `smoothing_window` 从后续 tick 生效。
- EMA 导入时过滤新 tag vocabulary 中不存在的 tag。
- Reload 成功后不自动 switch / cycle。
- Reload 成功后不清空 cooldown。
- Reload 成功后重新 resolve WE path。
- Reload 失败时告警用户并保留上一份有效 Runtime Config
- Reload 成功时应清除先前的 Reload Failure

阶段边界：

- 不做“apply after reload”。
- 不把 reload 和 tray Manual Apply 混在一起。

本阶段无需验证。

- 配置 reload 边界稳定。
- 运行状态迁移规则可测试。

## 8. 阶段 6：Diagnostics-only 收口 [DONE]

目标：将 Dashboard / WebView 收敛为 Diagnostics-only 界面。配置编辑、配置辅助和 History 产品面退出 Dashboard，不再以 WebView 页面或 dashboard HTTP API 作为默认入口。

文件范围：

- `ui/dashboard.py`
- `dashboard/src/**`
- `tests/test_dashboard_api.py`
- Dashboard type-check / build 相关文件

工作内容：

- 清理旧 `GET /api/config` / `POST /api/config` 接口及其前端消费者。
- 清理旧 History 相关 WebView 入口与 dashboard HTTP 暴露：
  - `/history` 路由与导航
  - `GET /api/history`
  - `GET /api/history/aggregate`
- 清理前端配置页、配置路由、配置导航、配置 store、配置文案和相关组件。
- 清理仅服务旧 WebView 配置面的 dashboard API 暴露，例如：
  - `GET /api/tags/presets`
  - `GET /api/playlists/scan`
  - `GET /api/we-path`
- 审查现有配置辅助能力：
  - `validate`
  - `reload`
  - `last error`
  - `effective config summary`
  - `config folder path`
  - `scan playlists`
  - `detect WE path`
- 上述能力不承诺在本阶段提供新的 WebView 承载形式；如后续仍需保留，可由 tray、本地工具或独立辅助入口承接。
- Dashboard 只保留 Diagnostics 所需页面与接口。

阶段边界：

- 不实现新的 WebView 配置工具面板。
- 不实现新的 GUI Config Editor。
- 不要求在本阶段把所有配置辅助能力重新挂到 tray。
- 不要求删除 `HistoryLogger` 等内部运行能力；本阶段清理的是 WebView 与 dashboard HTTP 暴露。
- 不在本阶段扩展独立 History 页面。

本阶段无需验证

完成标准：

- WebView 中不存在配置编辑、配置辅助或 History 入口。
- 旧 `/api/config` 契约及其调用链被清理。
- 旧 `/api/history` / `/api/history/aggregate` 及其前端消费者被清理。
- Dashboard 运行时只服务 Diagnostics。
- 配置辅助能力若仍保留，不再以 Dashboard 为默认承载面。

## 9. 阶段 7：文本配置辅助入口 - [DONE]

目标：为文本配置工作流提供一个轻量、离线、可双击的配置辅助入口。该入口不依赖 Dashboard , 不启动 `WEScheduler` runtime；它只复用底层配置解析、WE 路径探测和播放列表扫描能力。

发布布局：

- `WEScheduler.exe`
- `Config Tools.bat`
- `config/`

文件范围：

- `main.py`
- 新增 `utils/config_tools.py`
- 可能新增 `ui/config_cli.py` 或 `utils/config_cli.py`
- `utils/config_loader.py`
- `utils/we_path.py`
- `scripts/build.bat`

工作内容：

- 新增 `WEScheduler.exe config` 子命令，默认进入简单 numbered TUI。
- `config` 子命令必须在创建 scheduler、tray、dashboard server 之前分流。
- `config` 子命令不创建 `WEScheduler`，不启动调度循环，不启动 Dashboard。
- 对 windowed / no-console 构建，在 `config` 子命令下主动 attach parent console；没有 parent console 时 allocate console。
- Release zip 附带 `Config Tools.bat`，内容只包装 `WEScheduler.exe config`：

  @echo off
  cd /d "%~dp0"
  WEScheduler.exe config
  echo.
  pause

```bash
`WEScheduler.exe config` numbered TUI：

    1. Validate config
    2. Detect Wallpaper Engine
    3. Scan Wallpaper Engine playlists
    q. Exit
```

- validate config：
  - 使用与启动 / reload 同一套 `ConfigLoader` 校验。
  - 成功时输出 `OK`。
  - 成功后输出极简 summary：config folder path、resolved WE path、playlist count、enabled policies。
  - 失败时输出 source file、field path、message、code。
  - 不启动 scheduler，不执行 reload，不写回配置文件。

- detect WE path：
  - 显示 configured value。
  - 显示 resolved executable path。
  - 显示 Wallpaper Engine `config.json` 是否找到。
  - 不写回 `scheduler.yaml`。
  - 不启动 Wallpaper Engine。

- scan playlists：
  - 从 Wallpaper Engine `config.json` 读取播放列表名。
  - 输出纯播放列表名列表。
  - 输出 copy-ready `playlists.yaml` snippet。
  - 不写回 YAML。
  - 不自动生成 tag。
  - 不自动生成 color。
  - 不猜测 display name。

阶段边界：

- 不实现 `Show last config error`。
- 不实现 `last_config_error.json` 持久化。
- 不实现独立的 `effective config summary` 菜单项。
- 不实现 YAML 写回、自动修复、自动生成 tag、自动生成 playlist 配色。
- 不实现 `WEScheduler.exe config validate` / `detect` / `scan` 等直接子命令；本阶段只要求 interactive TUI，后续需要时再补。

完成标准：

- 用户可以双击 `Config Tools.bat` 进入配置辅助 TUI。
- 高级用户仍可直接运行 `WEScheduler.exe config`。
- Validate / Detect / Scan 都不依赖 Dashboard。
- 主程序双击无黑框启动。
- 配置辅助入口不会重新牵引完整 GUI Config Editor。

## 10. 阶段 8：Tray Manual Apply

目标：提供一个明确的手动调度入口，让用户“按当前上下文执行一次切换”。

文件范围：

- `ui/tray.py`
- `core/scheduler.py`
- `core/controller.py`
- `core/actuator.py`
- `core/diagnostics.py`
- `core/event_logger.py`
- `utils/i18n.py` 或相关翻译资源

工作内容：

- Tray 新增 `Apply Current Match Now` / `立即应用当前匹配`。
- 手动 apply 立即采集上下文并计算 best playlist。
- best playlist 不同于 current playlist 时 switch。
- best playlist 等于 current playlist 时 cycle。
- > 也即执行标准的切换语义
- no match 时不执行副作用并记录原因。
- 手动 apply 绕过所有 controller gates：
  - cooldown
  - idle
  - fullscreen
  - CPU
- 手动 apply 仍受硬条件限制：
  - executor command failed
- paused 时允许手动 apply，但不取消 paused。
- 成功后按真实副作用更新 current playlist 和 controller timestamps。
- 记录 history / diagnostics reason，例如 `manual_apply_requested`。

阶段边界：

本阶段无需验证

完成标准：

- 用户有明确的一次性手动调度入口。
- 自动调度 gate 与手动调度语义分离。

## 11. 阶段 9：清理、文档和发布检查

目标：删除阶段性临时代码，更新用户文档，确认没有旧 Config Editor / History 方向重新牵引主线。

文件范围：

- `README.md`
- `AGENTS.md`
- `docs/PRODUCT_DIRECTION.md`
- `docs/frontend/CONFIGURATION_SPEC.md`
- `docs/archived/frozen/*` 如需加冻结说明
- 示例配置与 Release zip 文件布局
- 测试夹具

工作内容：

- 更新 README 中配置路径、YAML 文件、example 配置、validate / reload 流程。
- 确认旧 JSON 迁移相关措辞不存在。
- 确认 runtime preset / override 相关措辞不存在。
- 确认 include 相关措辞只作为“不支持”出现。
- 删除临时 adapter、legacy test fixture 或 dead route。
- Release zip 包含 example 配置文件。
- 文档说明 reload 不会立即切换，tray Manual Apply 才是手动应用入口。

验证：

```bash
pytest -q
cd dashboard
npm run type-check
npm run build-only
```

完成标准：

- 测试和前端检查通过。
- 文档与实现一致。
- 没有长期双轨模型残留。

## 12. 建议合并节奏

推荐按下面节奏合并：

1. 阶段 0 + 阶段 1 可以合并为一个 preparatory PR。
2. 阶段 2 单独合并，因为 playlist map / tag id 是最大 breaking change。
3. 阶段 3 单独合并，因为 ActivityPolicy 规则语义需要独立审查。
4. 阶段 4 + 阶段 5 可以分开，若改动过大则必须分开。
5. 阶段 6 阶段 7 和阶段8 分别作为 UI / tray 后续任务。
6. 阶段 9 作为收尾 PR。

不要把阶段 2、3、4、5、6、7、8合成一个 PR。那会导致测试失败定位困难，也会让产品语义审查失去焦点。

## 13. 总体验证基线

配置运行时核心完成后至少运行：

```bash
pytest tests/test_config_loader.py tests/test_core_diagnostics.py tests/test_dashboard_api.py -q
```
