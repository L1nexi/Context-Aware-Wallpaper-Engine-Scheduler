# Config Editor Implementation Spec - R4

本文档收敛 `Config Editor v2` 的 `R4` 实现计划。  
[CONFIG_EDITOR_SPEC.md](./CONFIG_EDITOR_SPEC.md) 继续承担整体目标、信息架构与正式 contract 定义；本文档只负责把 `R4 Config backend contract` 的落地顺序、改动边界、风险控制与验收写清，避免实现时再次回到“先糊前端表单，再补后端模型”的旧路线。

## 0. 当前定位（2026-05-06）

当前代码事实：

- `dashboard-v2` 已完成 App Shell 与正式路由骨架，`/config/*` 路由入口已存在。
- `GET /api/config` 仍返回原始 JSON，而不是 `current + defaults`。
- `POST /api/config` 仍按原始 payload 写回文件，未做 canonical save。
- `utils/config_loader.py` 已收紧 `policies` 的未知 key，但 config document 仍未进入完整 canonical shape。
- `Config Editor` 前端页面尚未实现，因此 `R4` 的主要职责仍是后端 contract 收口，而不是 UI 细化。

`R4` 的目标不是“先让 `/api/config` 多返回一个字段”，而是正式建立 Config Editor 的唯一后端事实源：

- 稀疏 JSON -> 完整 `AppConfig`
- `current + defaults`
- canonical save
- 结构化 validation error

## 1. R4 范围

`R4` 的正式范围：

- 重构 config schema，使 canonical `AppConfig` 可直接作为 editor document 使用
- 重构 `GET /api/config`
- 重构 `POST /api/config`
- 明确 weather 坐标类型
- 建立稳定 field error contract
- 更新相关 pytest

不在 `R4` 范围内的内容：

- `ConfigView.vue` 与 section 页面
- Pinia config draft store
- Playlist / Tag / Policy 具体编辑器控件
- 自动探测 Wallpaper Engine 并注入 `GET /api/config.current`
- 将 rule dict / fallback dict 改写成 UI 专用数组模型

结论：

- `R4` 只解决“编辑器该拿到什么、保存什么、出错时怎么定位”的问题。
- `R5-R8` 再消费该 contract 进入正式 UI。

## 2. 目标状态

`R4` 完成后，后端应满足以下状态：

1. 原始 JSON 允许稀疏。
2. loader/schema 会将其规范化为完整 `AppConfig`。
3. `GET /api/config` 返回：

```ts
type ConfigDocumentResponse = {
  current: AppConfig
  defaults: AppConfig
}
```

4. `defaults` 直接来自 schema defaults；schema defaults 与产品推荐默认值是同一套语义。
5. `POST /api/config` 保存完整 canonical config，而不是保留稀疏文件风格。
6. `POST /api/config` 的错误明细返回 `path/field/message/code/section/scope`。
7. `weather.lat` / `weather.lon` 使用 `float | null` 单一模型。

## 3. 核心实现决策

### 3.1 Canonical Config 模型

`AppConfig` 在 `R4` 后应同时承担：

- runtime config
- config document
- schema defaults 真相源

结论：

- 不单独引入第二套 editor-only config schema。
- `AppConfig.model_validate(raw)` 的结果就是 `current`。
- `AppConfig()` 的结果就是 `defaults`。

### 3.2 稀疏输入与完整输出

保留以下设计：

- 原始 JSON 可省略部分 section 或字段
- schema default 负责补齐缺省字段

但输出与保存遵守以下约束：

- `current` 必须是完整 canonical tree
- GUI 第一次保存后，文件应收敛成完整 canonical config
- 不再为了“保留用户原始手写风格”而压回稀疏结构

### 3.3 Defaults 语义

`defaults` 不再区分：

- parser defaults
- product recommended defaults
- restore defaults

当前阶段这三者视为同一语义：

- 默认值就是推荐值
- 推荐值就是 restore 目标

因此 `R4` 不引入独立 defaults builder 语义层。

### 3.4 Weather 语义

Weather 是重要的上下文策略，默认开启是合理的。

正式要求：

- `weather.enabled = true`
- `weather.api_key = ""`
- `weather.lat = null`
- `weather.lon = null`
- `weather.fetch_interval / request_timeout / warmup_timeout` 保留正式默认值

同时明确：

- “配置结构合法”与“功能已配置完成”是两回事
- weather sensor 是否真正启动，由 runtime gating 决定，而不是由 schema 结构合法性决定

### 3.5 Validation Error 语义

后端错误 contract 采用：

- `path` 作为唯一真相源
- `field` 作为人类可读路径
- `section` / `scope` 作为前端导航辅助

不做：

- UI 分组化错误 payload
- 返回原始输入值
- 用 playlist name 作为错误定位主键

## 4. 文件级改动计划

### 4.1 `utils/config_loader.py`

这是 `R4` 的主改动点。

计划修改：

- 将 `AppConfig.wallpaper_engine_path` 放宽为默认空字符串
- 将 `AppConfig.playlists` 放宽为 `default_factory=list`
- 保留 `tags` / `policies` / `scheduling` 的默认工厂
- 将 `PoliciesConfig` 四个正式 policy 改为稳定完整对象，而不是 `Optional[...] = None`
- 将 `WeatherPolicyConfig.lat/lon` 从 `Union[str, float]` 改为 `float | None`
- 让 `AppConfig()` 可直接构造完整默认配置

预期结果：

- `AppConfig.model_validate(raw)` 可以把稀疏 JSON 规范化
- `AppConfig()` 可直接作为 `defaults`

注意：

- 这里不引入 UI 专用模型转换
- 这里不做自动探测路径写入 defaults

### 4.2 `core/sensors.py`

由于 weather 坐标与 policy shape 变化，需要同步 runtime gating。

计划修改：

- `WeatherSensor.create()` 不再依赖 `weather is None`
- 使用完整 `weather` config 对象
- 将“是否 ready”判断改成：
  - `enabled == true`
  - `api_key` 非空
  - `lat` 非 `None`
  - `lon` 非 `None`

预期结果：

- weather policy 默认存在、默认 enabled，不会误触发 sensor
- 仅在配置完成时真正启动 weather sensor

### 4.3 `ui/dashboard.py`

这是 API contract 主改动点。

计划修改：

- `GET /api/config`
  - 从“读取原文件后原样返回”改为：
    - 读取 raw JSON
    - `AppConfig.model_validate(raw)` 生成 `current`
    - `AppConfig()` 生成 `defaults`
    - 返回 `{ current, defaults }`
- `POST /api/config`
  - 校验通过后，不再直接写入原始 payload
  - 改为写入 canonical `model_dump()` 结果
- `_flatten_errors()`
  - 从 `{field, message}` 扩展为结构化明细

预期结果：

- `/api/config` 成为 Config Editor 的正式唯一入口
- 保存后文件结构稳定

### 4.4 `tests/test_config_loader.py`

计划补充或调整的测试：

- 稀疏 config 会被补齐为完整 canonical `AppConfig`
- `AppConfig()` 可直接构造 defaults
- 空 `wallpaper_engine_path` 合法
- 空 `playlists` 合法
- `weather.lat/lon` 接受 `null`
- `weather.lat/lon` 不再接受字符串
- 未知 policy key 仍返回错误

### 4.5 `tests/test_dashboard_api.py`

计划补充或调整的测试：

- `GET /api/config` 返回 `current + defaults`
- `GET /api/config` 的 `current` 中缺失 section 被 schema 补齐
- `POST /api/config` 保存后文件是 canonical shape
- `POST /api/config` 返回结构化 `details`
- `section` / `scope` 派生规则正确
- 不返回原始输入值

## 5. 实施顺序

推荐按以下顺序落地：

1. 先收口 `utils/config_loader.py` 的 canonical schema。
2. 再同步 `core/sensors.py` 的 weather gating。
3. 然后重构 `ui/dashboard.py` 的 `GET /api/config`。
4. 再重构 `POST /api/config` 与 `_flatten_errors()`。
5. 最后统一更新 pytest。

原因：

- 先稳定 schema，后端 API 才有稳定真相源。
- weather runtime gating 必须和 schema 同步，否则默认 enabled 会带来运行时歧义。
- 先改 API 再改 schema，会导致 contract 和真实 config model 暂时脱节。

## 6. 结构化错误派生规则

`R4` 中 `_flatten_errors()` 应遵守以下约束：

### 6.1 Path

- 直接以 Pydantic `loc` 为基础构造
- 保留字符串与数字层级
- 不在后端把 `path` 折叠回单一字符串

### 6.2 Field

- 继续输出点路径字符串
- 仅供日志、调试、兼容
- 前端不应再解析 `field`

### 6.3 Section

派生规则固定为：

- `wallpaper_engine_path` / `language` -> `general`
- `scheduling.*` -> `scheduling`
- `playlists.*` -> `playlists`
- `tags.*` -> `tags`
- `policies.*` -> `policies`

### 6.4 Scope

派生规则固定为：

- `policies.<policyKey>.*` -> `{ kind: "policy", key: <policyKey> }`
- `playlists.<index>.*` -> `{ kind: "playlist", index: <index> }`
- `tags.<tagKey>.*` -> `{ kind: "tag", key: <tagKey> }`
- `general` / `scheduling` -> `null`

### 6.5 Code

- 直接复用 Pydantic error `type`
- 不在 `R4` 自定义前端专属错误码枚举

## 7. 风险与对策

### 7.1 Canonical Save 会改变用户文件形状

风险：

- 第一次 GUI 保存后，配置文件会从稀疏变为完整

结论：

- 接受这个 breaking change
- 这是 Config Editor 正式化的必要代价

### 7.2 Weather 默认 enabled 但未配置完成

风险：

- 用户可能看到 weather 默认为启用，但 runtime 并不真正运行

对策：

- 将“是否启用”和“是否 ready”拆开
- runtime gating 保持严格
- 后续 `R8` 在 UI 层明确显示配置缺失提示

### 7.3 Playlist / Tag 错误定位

风险：

- playlist rename 时，name 不适合作为稳定错误定位键

对策：

- playlist 使用 index scope
- tag 继续使用 key scope

## 8. 验收标准

`R4` 完成后，至少应满足：

1. `GET /api/config` 返回 `current + defaults`。
2. `current` 是完整 canonical config tree。
3. `defaults` 直接来自 schema defaults，并可用于 section / policy restore。
4. `POST /api/config` 保存后文件为完整 canonical config。
5. `POST /api/config` 的错误明细包含 `path/field/message/code/section/scope`。
6. `weather.lat/lon` 使用 `float | null`，不再接受字符串坐标。
7. 前端不再需要自行补默认值。

## 9. 验证

`R4` 的最低验证要求：

```bash
pytest tests/test_config_loader.py tests/test_dashboard_api.py -q
```

若改动波及 runtime config 行为，优先再补跑：

```bash
pytest -q
```
