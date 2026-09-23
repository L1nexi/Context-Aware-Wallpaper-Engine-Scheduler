---
status: accepted
date: 2026-09-23
---

# 产品化本地服务端与 Profile 编辑器边界

本项目将产品化阶段的本地 HTTP 能力从 `ui/` 移入顶层 `server/`，把 Profile 作为单例 REST 资源，并继续由 `ProfileManager` 独占 Profile 的读取、编译、持久化与运行时应用。本记录同时保存本轮架构评审的上下文、已经确认的决策、当前代码快照、测试评审和实施顺序，供后续模型或开发者接手时使用。

## 阅读规则

- **已确认**表示产品或架构决策已经拍板，可以直接实施。
- **当前状态**表示 2026-09-23、分支 `codex/productization-setup-and-cleanup`、提交 `f93ab1b` 上观察到的代码状态；继续工作前仍应以工作区为准重新核对。
- **待实施**表示方向已经明确，但不能从本记录推断代码已经完成。
- **评审建议**表示本轮已识别的问题和推荐修法，实施时仍应遵守测试先行与小步提交。

## 决策摘要

以下结论已经确认：

1. 顶层目录使用 `server/`，不使用 `backend/server/` 或 `service/`。
2. API 路径使用资源名，去掉只适用于首次引导的 `/api/setup` 命名和 `/create`、`/apply`、`/scan`、`/detect` 等动作词。
3. `POST /api/profile` 创建首份 Profile；`PUT /api/profile` 完整替换现有 Profile，并进入既有的运行时应用流程。当前前端提交完整 Profile，因此暂不提供 `PATCH`。
4. 城市定位首版采用用户主动触发的公网 IP 城市级估算，结果可编辑，不做后台定位或持续定位。
5. `main` 继续作为组合根，但设置窗口的“创建、聚焦、失效后重建”策略应收进一个具体控制器，而不是继续散落在闭包状态中。
6. 本轮新增测试应以公开行为为主，只替换真正的系统边界；现有新增测试还需要按本记录的测试评审补齐。

## 当前代码与产品化进度

### 已经建立的主干能力

- Profile、`ProfileCompiler`、原子持久化和 `ProfileManager` 已经成为正式配置路径。
- `app/main.py` 创建同一个 `ProfileManager`，交给本地 HTTP API、首次启动流程和 `WEScheduler`。
- 运行时 Profile 更新通过单写者队列，在调度线程的安全边界应用；不依赖文件热重载。
- Tick History 导出、旧 Diagnostics 下线、旧六 YAML 用户入口和旧配置 CLI 清理已经完成。
- 首次启动宿主分支、Profile 创建、Scene 目录、Wallpaper Engine Playlist 扫描和初版 Setup GUI 已经建立。
- Setup GUI 已覆盖首次创建与运行时设置两条路径；首次创建成功后窗口主动关闭，宿主等待子进程退出后重新加载 `profile.json`。

### 本轮工作区快照

用户为了便于审查已经重新整理工作区差异。记录生成时有以下未提交路径：

```text
M  app/main.py
M  docs/PRODUCTIZATION_PHASE_PLAN.md
M  tests/test_local_api.py
M  ui/api_server.py
M  ui/webview.py
?? ui/setup_assistance.py
```

这些差异包含本轮正在审查的城市定位、天气设置校验、设置窗口单实例行为和本地 API 改动。它们不是本 ADR 所描述的 `server/` 重构完成态；后续接手者不得因为本文写了目标结构，就误判结构迁移已经落地。

### 2026-09-23 后续实施更新

- 已新增 `ui/settings_window.py`，以具体的 `SettingsWindowController.show()` 收拢设置窗口进程状态以及“首次启动、活动时聚焦、退出后重建”策略。
- `app/main.py` 现在只在组合根创建控制器、注入进程启动与 Windows 聚焦边界，并把 `settings_window.show` 交给托盘。
- 已通过四个逐步红—绿切片覆盖首次启动、活动时聚焦、退出后重建和聚焦失败；聚焦失败时不创建重复窗口，并写入警告日志。
- 本轮新增 HTTP 测试中的 `ProfileStore` 旁路断言和 `pytest.fail` 内部非调用断言已经改成 HTTP 可观察行为；OpenWeatherMap 与 `ipapi.co` 使用各自的外部响应替身。
- 相关 Ruff 检查与完整后端回归通过：`145 passed`。

### 2026-09-23 服务端迁移与验收更新

- `061492b` 完成纯结构迁移：`ui/api_server.py` 拆入 `server/app.py`、`server/host.py`、`server/spa.py` 与 `server/routes/`；URL、方法和载荷保持原样，迁移后 `145 passed`。
- `bfcf777` 单独切换 REST 契约：Profile 使用 `GET`、`POST`、`PUT /api/profile`；Scene、Playlist 扫描、地点估算和 Tick History 改用本记录定义的资源路径，前端调用同步更新，不保留旧接口别名。
- `b0bbed6` 提取 `integrations/openweather.py` 和 `integrations/ip_location.py`；天气提交校验与运行时 Sensor 复用同一请求和观测解析。新增对服务返回 `200` 但天气数据不完整的失败处理。
- 后端完整回归为 `150 passed`；前端类型检查与构建通过。独立目录中的 PyInstaller 单文件构建成功，包内包含 `server`、`integrations` 和前端 `index.html`；冻结包启动后，健康接口、`/setup/` 和缺失 Profile 的 `404` 通过冒烟验证。
- 使用 `.pytest_tmp/manual-setup-browser/` 临时配置和外部响应替身走通浏览器中的首次创建与运行时设置：定位失败提示、定位结果可编辑、天气凭据错误跳转及字段提示、创建成功、天气服务故障期间仅修改 Scene 绑定仍能应用。该验收不覆盖真实 pywebview 窗口聚焦、取消退出，也不能代表 `ipapi.co` 在目标网络的可用性。
- 原生窗口验收发现 pywebview 的可见窗口由设置进程的子进程持有；原聚焦函数只匹配父进程，因此无法选中窗口。经 `SettingsWindowController.show()` 公开接缝的失败测试复现后，聚焦函数已将子进程纳入查找。使用临时本地服务验证了原生窗口关闭、重建以及取消后 Profile 仍不存在；自动化进程调用 `SetForegroundWindow` 仍被 Windows 拒绝，真实托盘点击的前台聚焦需在用户交互环境复核。

## 城市定位方案

### 已确认方案

首版地点辅助采用 `ipapi.co` 根据公网 IP 返回城市级地点估算，约束如下：

- 只有用户明确点击“自动定位”时才发起请求，页面打开时不静默请求。
- 应用不保存公网 IP；外部服务完成定位时必然能看到请求来源 IP，界面文案应如实说明。
- 返回的地点名、经纬度只是表单填充值，用户可以手动修正。
- 手动输入经纬度始终保留为兜底路径。
- Profile 只保存最终地点，不保存“自动定位”开关或定位来源。
- 运行时不持续定位，不根据 IP 变化自动更新地点。
- 提交时由 OpenWeatherMap 对 API Key 与经纬度进行真实请求校验；首次创建必须校验，后续修改仅在天气设置发生变化时重新校验，避免天气服务临时故障阻塞无关设置。

### 权衡记录

考虑过的方案包括手动输入、浏览器 `navigator.geolocation`、Windows `Geolocator`、城市名地理编码和离线 IP 数据库。公网 IP 估算精度有限，但无需额外系统权限、无需引入数据库、可直接落入现有 WebView 表单，而且失败后仍可手动填写，因此适合当前 `0.x` 首版。

如果公网 IP 估算在目标网络下效果不足，优先增加基于 OpenWeather Geocoding 的城市搜索与候选选择，而不是立即接入 Windows 精确定位。验收时需要特别检查中国大陆网络可用性、延迟以及 VPN、代理导致的地点偏差。

## 设置窗口单实例职责

### 重构前状态

`app/main.py` 的 `_run_tray_mode` 通过局部变量 `settings_process` 和闭包 `show_settings()` 实现：

1. 没有活动子进程时创建设置窗口；
2. 子进程仍存活时按 PID 聚焦窗口；
3. 子进程已经退出时重新创建。

`ui.webview.focus_process_window(process_id)` 是 Windows 原生聚焦边界。当前实现还有一个未明确定义的分支：子进程存活但聚焦返回失败时，闭包仍直接返回，不会重新创建或报告失败。

### 评审结论

`main` 作为组合根负责创建对象、连接回调和编排进程生命周期是合理的；问题不是它知道设置窗口，而是它直接承载了一段会继续增长的应用策略和可变状态。

已经实现的目标形态是一个具体的 `SettingsWindowController`，只暴露 `show()`：

```text
TrayIcon --show intent--> SettingsWindowController.show()
                                 |-- process alive --> focus
                                 |-- process exited -> spawn
                                 `-- no process ----> spawn

app/main.py: 创建对象并执行 tray.on_show_settings = settings_window.show
```

约束如下：

- `TrayIcon` 只产生“显示设置”意图，不拥有子进程生命周期。
- 控制器拥有子进程引用以及聚焦失败时的明确策略。
- 测试只替换进程创建和 Windows 窗口聚焦这两个系统边界。
- 当前没有第二类窗口生命周期实现，不建立通用 `WindowManager`、基类或协议。

## 本地服务端目录与依赖边界

### 为什么选择 `server/`

项目中的 `app/`、`core/`、`configurations/` 本来都是 Python 后端代码。只把本地 HTTP 服务放入 `backend/server/` 会错误暗示其他 Python 目录不属于后端；若真正采用 `backend/`，就应连同全部 Python 包整体迁移，范围远超本轮目标。

`service/` 也不采用，因为它无法说明这里是 HTTP 传输边界，容易逐渐变成通用杂物目录，并与已经存在的 `ProfileManager` 应用职责重叠。这里缺少的是清晰的本地服务端适配层，不是新的“服务层”。

因此目录命名选择顺序为：`server/` 优先；`local_api/` 和 `api/` 只作为曾考虑的次选；拒绝局部 `backend/server/` 与模糊的 `service/`。

### 目标结构

```text
server/
├── __init__.py
├── app.py
├── host.py
├── spa.py
└── routes/
    ├── __init__.py
    ├── profile.py
    └── profile_support.py
```

各模块职责：

- `server/host.py`：承载 `APIServer`、线程化 WSGI Server、端口绑定、启动与停止；只依赖标准库、WSGI 与准备好的 Bottle 应用对象，不导入 Profile、Scheduler、Wallpaper Engine、天气或 Tick History。
- `server/app.py`：实现 `build_api_app()`，创建 Bottle 应用并注册路由；它是 HTTP 层的组合根，不包含 Profile 错误翻译细节。健康检查和仍然很小的 Tick History 路由可以暂时留在这里。
- `server/routes/profile.py`：实现单例 Profile 资源，负责 JSON 与媒体类型检查、Pydantic 校验问题映射、天气设置是否变化的判断，以及 `ProfileManager` 异常到 HTTP 响应的翻译；不得直接持久化 Profile，也不得构造或替换 Engine。
- `server/routes/profile_support.py`：实现 Scene 目录、Wallpaper Engine Playlist 扫描和地点估算。它们同时服务首次引导和后续设置，因此模块和 URL 都不使用 `setup` 命名。
- `server/spa.py`：解析开发态与冻结包静态目录，保护路径穿越，并实现 `/setup/` 与根路径的 SPA fallback；它不知道 Profile 或 Scheduler 状态。
- `ui/`：只保留托盘、pywebview、图标、国际化等原生桌面表现职责，不再承载本地 HTTP Server。

依赖方向固定为：

```text
app/main.py -> server.app + server.host
server      -> configurations + core + integrations
ui          -> 原生桌面表现能力

configurations/core 不反向依赖 server
integrations 不依赖 Bottle
```

Bottle 的 `request`、`response` 全局对象可以继续局限在路由适配器内部。当前不建立 `controllers/`、`services/`、`repositories/`、`middlewares/` 多层目录，也不建立基础路由类、通用响应工厂或路由注册框架。只有出现第二个真实变化方向时才继续抽象。

## REST 资源契约

### 已确认的目标接口

| 方法   | 路径                                      | 语义                                               |
| ------ | ----------------------------------------- | -------------------------------------------------- |
| `GET`  | `/api/health`                             | 本地服务健康检查。                                 |
| `GET`  | `/api/profile`                            | 读取当前单例 Profile；不存在时返回 `404`。         |
| `POST` | `/api/profile`                            | 创建首份 Profile；成功返回 `201`，已存在返回 `409`。 |
| `PUT`  | `/api/profile`                            | 完整替换 Profile，并等待运行时应用结果；不存在时返回 `404`。 |
| `GET`  | `/api/scenes`                             | 读取产品内置 Scene 目录。                          |
| `POST` | `/api/wallpaper-engine/playlist-scans`    | 提交 Wallpaper Engine 路径并创建一次扫描结果。     |
| `POST` | `/api/location-estimates`                 | 用户主动请求一次公网 IP 城市级地点估算。           |
| `GET`  | `/api/tick-history?limit=<positive-int>`  | 读取指定上限的近期 Tick History。                  |

选择 `location-estimates` 而不是 `location` 或 `detect`，是为了明确表达结果只是一次粗略估算，同时避免在资源路径中使用动作。Playlist 扫描同理建模为一次新建的扫描资源。

当前前端每次提交完整 Profile，因此 `PUT` 比 `PATCH` 更符合契约，也不应保留 `/api/profile/apply`。应用运行时是替换 Profile 的服务器端结果，不是另一个独立 HTTP 动作。

当前 UI 页面路径 `/setup/` 可以保留；它表达首次引导页面，而不是 API 的长期领域边界。首版不增加 `/api/v1`，因为前端与本地后端随同一桌面发布包部署和升级。

### HTTP 错误语义

目标错误分类如下：

| 状态码 | 使用场景 |
| ------ | -------- |
| `400`  | JSON 语法错误或请求无法解析。 |
| `404`  | 单例 Profile 不存在，或明确请求的本地资源不存在。 |
| `409`  | 创建 Profile 时资源已经存在。 |
| `415`  | 不支持的媒体类型。 |
| `422`  | 请求结构或字段校验失败，或外部服务明确拒绝凭据/地点。 |
| `503`  | 外部定位/天气服务暂不可用，或运行时应用当前不可用/超时。 |
| `500`  | 已进入内部处理但出现未归类的提交失败。 |

### 与当前接口的差异

当前代码仍使用下列接口：

```text
GET  /api/tick-history/window?count=...
GET  /api/setup/scenes
GET  /api/setup/location
POST /api/setup/wallpaper-engine/playlists
POST /api/profile/create
POST /api/profile/apply
```

因此 REST 目标契约属于**待实施的 breaking change**。项目仍处于 `0.x`，不增加兼容别名。为了保持差异可审查，目录迁移和接口改名必须分成两个行为清晰的步骤：先做纯结构移动并保持旧接口与响应不变，再单独修改 URL、方法、状态码、前端调用与测试。

## 外部集成边界

当前 `ui/setup_assistance.py` 与 `core/sensors/weather.py` 都会调用 OpenWeather Current Weather 接口，已经存在两个真实生产调用者。完成 `server/` 结构和 REST 契约后，应单独提取：

```text
integrations/
├── openweather.py
└── ip_location.py
```

- `integrations/openweather.py` 负责请求、响应解析和稳定的异常语义，例如 `InvalidApiKey`、`InvalidLocation`、`QuotaExceeded`、`WeatherUnavailable`。`WeatherSensor` 消费天气结果；Profile 路由为校验而调用并忽略观测值。
- `integrations/ip_location.py` 负责 `ipapi.co` 请求与响应解析。
- 外部适配器不知道 Bottle，不设置 HTTP 状态码；路由负责把稳定异常翻译为 API 响应。

这是已经出现真实复用后的边界收敛，不是为了未来假想需求预先建框架。它仍应作为独立重构，不与目录迁移或 REST 改名混成一次修改。

## 本轮新增测试的 TDD 评审

### 总体结论

本轮新增测试有一部分已经通过公开 WSGI/Bottle 边界验证行为，并只替换外部 HTTP，方向正确；但整个新增过程不完全符合项目采用的 TDD 要求：测试公开接缝未在编写前先确认，也没有完整保留按垂直行为切片的红、绿、重构节奏，而且设置窗口单实例这一新增行为仍缺少测试。

本结论只针对本轮新增测试，不要求借机改写既有测试。

### 后续测试前先确认的公开接缝

1. Bottle/WSGI HTTP 端点；
2. `ProfileManager` 生命周期；
3. `SettingsWindowController.show()`；
4. Setup GUI 中用户可见的提交、步骤跳转和字段错误反馈。

只替换以下系统边界：`ipapi.co` 与 OpenWeatherMap HTTP、子进程创建、Windows 窗口聚焦和临时文件系统。不要替换 `ProfileManager`、`ProfileStore`、路由注册函数或内部校验辅助函数。

### 已识别的具体缺口

- Profile 创建失败后的测试不应通过直接调用 `ProfileStore.load()` 旁路验证；应继续通过 `GET /api/profile` 观察资源仍不存在并得到 `404`。
- “天气未变化不重新校验”的测试不应只用 `pytest.fail` 证明某个内部函数没有被调用。更强的公开行为是：让天气提供方不可用，提交一个只修改 Playlist 等非天气字段的完整 `PUT /api/profile`，仍应成功。
- `validationIssueField()`、`validationIssueStep()` 一类纯函数测试只能作为辅助，不能证明 GUI 会跳到正确步骤并在正确控件展示错误；公开行为稳定后应优先写组件级交互测试。
- `parseNumberInput()`、`isNonNegativeInteger()` 只有在 `frontend/src/setup/model.ts` 被明确视为稳定公开接缝时才值得单测，否则由表单行为覆盖。
- 设置窗口至少需要覆盖首次创建、活动进程聚焦、退出后重建，以及聚焦失败策略。

## 实施顺序

后续工作按以下顺序推进，每一步保持可独立审查：

1. **纯结构迁移**（已完成，`061492b`）：把 `ui/api_server.py` 拆到 `server/`，保持现有 URL、方法、状态码和载荷不变；除导入路径外，既有 HTTP 测试应原样通过。
2. **REST 契约改名**（已完成，`bfcf777`）：切换到资源式 URL、`POST /api/profile` 与 `PUT /api/profile`，同步修改前端和测试，并统一错误状态语义。
3. **外部集成收敛**（已完成，`b0bbed6`）：提取 OpenWeatherMap 与公网 IP 地点适配器，消除 Setup 校验与运行时 Sensor 的重复协议处理。
4. **设置窗口控制器**（已提前完成）：从 `app/main.py` 闭包提取具体控制器，以测试先行覆盖首次启动、活动时聚焦、退出后重建和聚焦失败。
5. **补齐本轮测试**（本轮已完成已识别的后端反模式）：按公开行为替换旁路断言和实现耦合断言，没有扩张到旧测试重写。
6. **人工验收 Setup GUI**（浏览器流程、原生关闭与重建已完成；托盘聚焦和目标网络待验）：使用独立的 `.pytest_tmp/manual-setup-*` 配置目录，不覆盖真实 `config/profile.json`；检查首次创建、设置修改、定位失败、天气校验失败、单窗口聚焦和取消退出。
7. **打包与发布收尾**（独立冻结包验证已完成）：完成冻结包静态资源、启动入口、文档和回归验证。

在上述迁移期间，用户可见 CLI 继续保持删节后的契约：正常运行使用 `python main.py`，公开参数只有 `--config` 与 `--api-port`；`--window`、`--setup`、`--port`、`--locale` 是宿主内部窗口参数，不恢复旧的 `config`、`validate`、`detect`、`scan` 或用户级 `setup` 子命令。

## 架构验收清单

完成后应满足：

- `ui/` 不再包含 HTTP Server 或 Profile API。
- `server/host.py` 不导入领域、配置或外部集成模块。
- `server/app.py` 只组合应用和注册路由，不处理 Profile 的具体异常。
- Profile 路由只通过 `ProfileManager` 操作 Profile，不直接调用 `ProfileStore`，不构建 Engine。
- 外部集成模块不依赖 Bottle。
- SPA catch-all 路由最后注册，路径穿越保护仍然有效。
- `app/main.py` 只从 `server.app` 获取 `build_api_app`，从 `server.host` 获取 `APIServer`。
- HTTP 测试继续从 WSGI/HTTP 公开接缝进入，不直接测试私有辅助函数或路由注册函数。
- 纯结构迁移提交不改 URL；REST 提交不混入外部集成重构。
- 没有新增无真实调用方的通用基类、管理器、仓储层或兼容层。
- 测试和人工验收不改写真实 `config/profile.json`。

## 后果与明确不做的事

这组决策会产生一次有意的 breaking change，需要前后端与测试同步更新，但能让 Setup 与 Settings 共享同一组长期 API，不再把首次引导概念泄露到后续配置编辑中。`server/` 会让 HTTP 适配层从原生桌面 UI 中独立出来，同时保留 `ProfileManager` 的既有所有权，不引入第二套应用服务。

本轮不做以下事情：

- 不把全部 Python 代码迁入新的 `backend/` 根目录。
- 不新增通用 `service` 层、Repository 模式或 Controller 层级。
- 不引入 API 版本前缀、异步任务查询、Profile revision 乐观锁或旧接口兼容层。
- 不把城市定位升级为持续定位、精确定位或运行时自动更新。
- 不在结构重构中顺手改变产品行为。
