# Config Editor R5 Spec - General / Scheduling - Frozen

> 2026-05-10 状态：本实施规格已冻结，保留为历史设计记录。当前配置方向以 [CONFIGURATION_SPEC.md](./CONFIGURATION_SPEC.md) 为准。
>
> `/config/general` 与 `/config/scheduling` 已有实现可作为既有事实参考，但完整 GUI Config Editor 不再是当前主线。后续配置体验应收敛为文本配置 + 轻量辅助工具。

本文档收敛 `R5 Config General / Scheduling` 的实施边界、状态模型、UI/UX 决策、风险控制与验收标准。

适用范围：

- `dashboard-v2` Config Editor 前端第一阶段。
- `/config/general`
- `/config/scheduling`
- Config 前端公共编辑状态模型。

不适用范围：

- Playlists / Tags / Policies 具体编辑器。
- 后端 Config contract 重构；该部分已经由 `R4` 完成。
- 文件选择器、完整前端 schema、外部并发编辑检测。

## 0. 当前前提

R5 开始时默认以下事实已经成立：

- App Shell 与 `/config/*` 路由骨架已经存在。
- `/config/general` 与 `/config/scheduling` 当前可替换现有 `RouteBoundaryView` 占位实现。
- `GET /api/config` 返回：

```ts
type ConfigDocumentResponse = {
  current: AppConfig
  defaults: AppConfig
}
```

- `POST /api/config` 接收完整 `AppConfig`，后端负责完整 Pydantic 校验与 canonical save。
- 保存失败时，后端返回结构化 `details`：

```ts
type ConfigValidationDetail = {
  path: Array<string | number>
  message: string
  code: string
  section: "general" | "scheduling" | "playlists" | "tags" | "policies" | null
  scope: ConfigValidationScope | null
}
```

## 1. R5 目标

R5 的目标不是先做完整 Config Editor，而是先把公共编辑模型跑通，并用两个单例 section 验证该模型：

- 建立 Config 前端唯一正式 draft store。
- 实现 `General` section。
- 实现 `Scheduling` section。
- 支持显式保存、脏状态、放弃修改、恢复默认、字段错误展示。
- 建立统一路由离开保护。

R5 完成后，R6-R8 应直接复用同一 store、dirty 模型、错误映射、确认弹窗和基础字段组件。

## 2. 非目标

R5 不做以下内容：

- 不实现 Playlists / Tags / Policies 编辑器。
- 不实现 Wallpaper Engine 原生文件选择器。
- 不复制完整 Pydantic schema 到前端。
- 不实现外部编辑器并发修改检测、mtime 检测或版本冲突处理。
- 不承诺保存 `language` 后立即切换当前 Dashboard 语言。
- 不新增路径校验后端接口；R5 只消费现有 `/api/we-path` 自动检测能力。

## 3. 路由与页面结构

### 3.1 路由

R5 必须将 `/config` 变成父级工作区路由：

```text
/config
  general
  scheduling
  playlists
  tags
  policies
```

实际 URL 保持：

```text
/config/general
/config/scheduling
/config/playlists
/config/tags
/config/policies
```

`/config` 必须 redirect 到 `/config/general`。

`ConfigView.vue` 作为父组件，统一拥有：

- loading / error / ready 状态。
- save / discard。
- dirty indicator。
- server error summary。
- confirm dialog。
- route leave guard。
- child route outlet。

`ConfigGeneralSection.vue` 与 `ConfigSchedulingSection.vue` 只负责渲染和编辑对应 section，不各自实现保存或离开保护。

### 3.2 Section 内切换

从 `/config/general` 切到 `/config/scheduling` 不触发未保存变更提示，因为 draft 不会丢失。

离开 `/config/*` 才触发离开保护。

这里的 `/config/*` 包含 `/config` 本身与所有 `/config/...` 子路径。

## 4. Store 模型

新增 `dashboard-v2/src/stores/configDocument.ts`。

核心状态：

```ts
type ConfigDocumentState = {
  saved: AppConfig | null
  defaults: AppConfig | null
  draft: AppConfig | null
  loading: boolean
  saving: boolean
  loadError: string | null
  saveError: string | null
  serverErrors: ConfigValidationDetail[]
  clientErrors: Record<string, string>
  fieldBuffers: Record<string, string>
}
```

### 4.1 `saved`

`saved` 是最近一次成功 load/save 后的 canonical 后端快照。

它用于：

- dirty 对比。
- discard 回滚。
- 初始字段显示。

### 4.2 `defaults`

`defaults` 来自后端 `GET /api/config`。

它用于：

- section restore defaults。
- 后续 policy restore defaults。

前端不得自行发明另一套默认值。

### 4.3 `draft`

`draft` 是当前可保存草稿，必须始终保持 `AppConfig` 类型。

规则：

- `load()` 时 deep clone `current` 到 `saved` 与 `draft`。
- section 编辑只修改 `draft`。
- `draft` 不承载输入框临时非法态。
- `POST /api/config` 永远提交完整 `draft`。

### 4.4 保存成功后的同步

保存成功后必须重新请求 `GET /api/config`，并用返回的 canonical document 刷新 `saved/defaults/draft`。

即使 R5 不考虑外部编辑器并发修改，也需要以后端 canonical config 为准，避免未来 normalization 与前端 draft 漂移。

### 4.5 不考虑外部并发编辑

R5 不处理用户同时用外部编辑器修改配置文件的情况。

如果用户同时通过 GUI 与外部编辑器改同一份配置，行为视为 undefined behavior。R5 不引入 `Reload from disk`、mtime 检测或 last-writer conflict UI。

## 5. Dirty / Save / Discard

### 5.1 Dirty

dirty 必须由以下条件共同决定：

- `draft` 与 `saved` 的 canonical JSON 不同。
- 或存在字段 buffer。

字段 buffer 只用于保存尚不能写入 `draft` 的输入中间态。输入一旦可解析并通过基础校验，必须立即写入 `draft` 并删除该字段 buffer。

使用 `JSON.stringify()` 对比，因为 `AppConfig` 由后端 canonical JSON 构造，字段顺序稳定。R5 不引入更细粒度 dirty tracking。

### 5.2 Save

保存流程：

1. 如果存在 client errors，阻止 POST，并定位或展示第一个错误。
2. 提交完整 `draft` 到 `POST /api/config`。
3. 如果后端返回 `validation_failed`，写入 `serverErrors`。
4. 如果保存成功，重新 load canonical config。
5. 保存成功后清空 `clientErrors`、`serverErrors`、`fieldBuffers`。

后端仍是完整校验唯一真相源。前端基础校验只用于避免明显不可解析输入进入 POST。

存在 `fieldBuffers` 时一定存在对应 `clientErrors`，因此保存前不会出现“可保存但尚未提交到 `draft` 的合法 buffer”。

### 5.3 Discard

`Discard changes` 只回滚到当前 `saved`，不访问后端。

它必须同时清空：

- `serverErrors`
- `clientErrors`
- `fieldBuffers`

### 5.4 Save 按钮状态

规则：

- loading 时不可用。
- saving 时不可重复点击。
- `draft === null` 时不可用。
- 无 dirty 时 disabled。
- 存在 client errors 时 disabled，并在页面 summary 或字段下展示原因。
- 存在 server errors 但没有 client errors 时，按钮不因 server errors 自动 disabled；用户修正字段后可重新保存。

## 6. 输入中间态隔离

### 6.1 原则

数字输入不得直接把临时非法值写入 `draft`。

原因：

- `draft` 的类型是 `AppConfig`，例如 `draft.scheduling.startup_delay` 应始终是 `number`。
- 用户编辑过程中会出现空字符串、`-`、`.`、`1.` 等临时态。
- Vue 的 number input / `.number` 可能在解析失败时返回原始字符串。
- 如果这些值写入 `draft`，`AppConfig` 类型注解会被污染，后续 dirty、format、restore、save 状态都需要处理 `number | string`。

### 6.2 Buffer 模型

字段组件维护文本 buffer。存在 buffer 时，`draft` 保留最近一次合法值：

```ts
fieldBuffers["scheduling.startup_delay"] = ""
clientErrors["scheduling.startup_delay"] = "Required"
draft.scheduling.startup_delay = 30
```

当输入可解析且满足基础约束时，才写入 `draft`：

```ts
draft.scheduling.startup_delay = parsedNumber
delete fieldBuffers["scheduling.startup_delay"]
delete clientErrors["scheduling.startup_delay"]
```

### 6.3 基础校验范围

R5 前端只做基础输入校验：

- required
- number parse
- min / max
- integer

不复制完整后端 schema，不复制 Pydantic normalization，不做完整业务合法性判断。

## 7. Server Error 映射

store 必须同时提供这些索引：

```ts
errorsByPath: Record<string, ConfigValidationDetail[]>
errorsBySection: Record<ConfigSection, ConfigValidationDetail[]>
globalErrors: ConfigValidationDetail[]
```

路径 key 使用稳定 join 规则：

```ts
["scheduling", "startup_delay"] -> "scheduling.startup_delay"
["playlists", 0, "color"] -> "playlists.0.color"
```

字段展示使用 `errorsByPath`。

section header、Sidebar badge 或页面 summary 使用 `errorsBySection`。

`section === null` 的后端错误进入 `globalErrors`，由 `ConfigView` 顶部 summary 展示。

用户修改某个字段时，只清除对应 path 的 server error，不清空整个 section 的 errors。

## 8. 离开保护与确认弹窗

### 8.1 Router Guard

`ConfigView` 统一实现离开保护。

规则：

- `/config/general` -> `/config/scheduling` 不提示。
- `/config/*` -> 非 `/config/*` 时，如果 dirty，弹出确认。
- 用户确认离开后，先执行 `discard()`，再允许导航。
- 用户取消后，返回 `false` 中止导航。

实现逻辑：

```ts
onBeforeRouteLeave(async (to) => {
  if (to.path === "/config" || to.path.startsWith("/config/")) return true
  if (!configStore.isDirty) return true
  const confirmed = await confirmLeave()
  if (!confirmed) return false
  configStore.discard()
  return true
})
```

### 8.2 Dialog 组件

R5 使用 shadcn 风格 `AlertDialog` 作为 confirmation dialog，不使用 `window.confirm` 作为主交互。

必须新增 `components/ui/alert-dialog/*`，用于：

- 未保存变更离开确认。
- General restore defaults。
- Scheduling restore defaults。
- 后续 R6-R8 的删除、rename 影响确认。

### 8.3 Browser Refresh / Window Close

浏览器刷新、关闭 tab、pywebview 窗口关闭不适合用 shadcn dialog 阻塞。

R5 不实现 `beforeunload` 保护。不要尝试用 shadcn dialog 实现 `beforeunload`。

## 9. Restore Defaults

### 9.1 语义

restore defaults 是 draft 操作，不自动保存。

用户 restore 后仍需点击 `Save`。

这保证 restore 可撤销，也自然纳入 dirty 与 leave guard。

### 9.2 General

General restore 使用：

```ts
draft.wallpaper_engine_path = defaults.wallpaper_engine_path
draft.language = defaults.language
```

当前默认值会清空 `wallpaper_engine_path`，因此必须弹出确认。

R5 不把 General 拆成更细 restore 粒度；字段数量少，section-level restore 足够。

### 9.3 Scheduling

Scheduling restore 使用：

```ts
draft.scheduling = deepClone(defaults.scheduling)
```

Scheduling restore 必须同样弹出确认，但文案比 General 更轻。

### 9.4 Error 清理

restore 某 section 后：

- 清理该 section 的 server errors。
- 清理该 section 的 client errors。
- 清理该 section 的 field buffers。
- 不清理其他 section 的 errors。

## 10. General Section

`General` 是单例编辑页。

字段：

- `wallpaper_engine_path`
- `language`

必须分组为：

- `Runtime`
- `Locale`

### 10.1 Wallpaper Engine Path

控件：

- path text input
- `Detect installed Wallpaper Engine`
- detection result message

现有 `/api/we-path` 语义是：

- 读取当前配置 path。
- 如果该 path 有效则返回。
- 否则通过 Steam library 搜索 Wallpaper Engine。

因此 R5 不应把它包装成“校验任意输入路径”的强校验能力。

行为：

- 点击 detect 后，如果返回 `{ valid: true, path }`，写入 `draft.wallpaper_engine_path`。
- 不自动保存。
- 如果未检测到，展示非阻塞提示。
- detect 会忽略尚未保存的手动输入，因为 `/api/we-path` 读取的是当前配置文件而不是前端 draft。

### 10.2 Language

字段语义：

- `null` 表示 Auto / 默认。
- `"en"` 表示 English。
- `"zh"` 表示中文。

当前 `useI18n()` 从 dashboard URL query `?locale=` 读取语言，且不是响应式。

因此 R5 不承诺保存 `language` 后立即切换当前 Dashboard UI 语言。

必须展示说明文案：

- 保存后下次打开 Dashboard 生效。

## 11. Scheduling Section

`Scheduling` 是单例编辑页。

字段：

- `startup_delay`
- `idle_threshold`
- `switch_cooldown`
- `cycle_cooldown`
- `force_after`
- `cpu_threshold`
- `cpu_sample_window`
- `pause_on_fullscreen`

必须分组为：

- `Startup`
- `Switching`
- `Cycling`
- `Idle`
- `Gates`

### 11.1 单位

后端字段单位保持秒或百分比。

R5 不引入复杂 duration picker。

数字输入必须仍输入原始秒数，并在旁边显示人类可读辅助文案：

```text
1800 s · 30 min
```

### 11.2 数值约束

基础前端校验：

- `startup_delay >= 0`
- `idle_threshold >= 0`
- `switch_cooldown >= 0`
- `cycle_cooldown >= 0`
- `force_after >= 0`
- `cpu_threshold` in `[0, 100]`
- `cpu_sample_window` integer and `>= 1`

其他完整合法性以后端为准。

### 11.3 Boolean

`pause_on_fullscreen` 使用 switch。

该字段不需要 buffer。

## 12. 组件边界

R5 的 feature-level config editor 组件必须放在 `features/config-editor/`，不要放进 `components/ui`。

使用目录与组件拆分：

```text
dashboard-v2/src/features/config-editor/
  ConfigFieldRow.vue
  ConfigNumberField.vue
  ConfigTextField.vue
  ConfigSectionPanel.vue
  ConfigUnsavedChangesDialog.vue
  ConfigRestoreDefaultsDialog.vue
  ConfigGeneralSection.vue
  ConfigSchedulingSection.vue
```

原因：

- 这些组件绑定 config path、server error、buffer、unit hint。
- 它们是业务表单组件，不是基础 UI 原语。

基础 shadcn 组件仍放在 `components/ui/*`。

## 13. UI/UX 要求

Config 页面应保持桌面工作台心智：

- 不做传统整页长表单。
- section 使用 `WorkbenchPanel` 承载页面级表面；panel 内部字段组使用 `Card`。
- 顶部操作区清楚显示 dirty/save/discard 状态。
- 字段说明要解释运行时影响，而不是只重复字段名。
- server error 应靠近字段，同时有 section-level summary。
- loading / invalid config / config not found 都必须有明确状态。

### 13.1 Blocking 状态

`GET /api/config` 失败时：

- `config_not_found`：展示无法加载配置文件的 blocking state。
- `invalid_config`：展示不可编辑状态，提示需要修复原始配置文件。
- 网络或 HTTP 错误：展示 retry。

不要在前端尝试修复 invalid raw JSON。

## 14. i18n

R5 新增文案必须同时写入：

- `dashboard-v2/src/i18n/en.json`
- `dashboard-v2/src/i18n/zh.json`

不要只写英文。

新增文案必须有可读中文翻译，不允许回退到 key。

## 15. 测试与验证

R5 最低验证：

```bash
cd dashboard-v2
npm run type-check
npm run build-only
```

R5 不修改后端 API，因此不要求 Python 测试。如果实现过程中发现必须修改后端，说明任务已经超出 R5，应先更新本 spec 或拆出独立后端切片。

## 16. 验收标准

R5 完成后必须满足：

- `/config/general` 可刷新恢复。
- `/config/scheduling` 可刷新恢复。
- 首次进入 Config 会加载 `current + defaults`。
- 修改 General 或 Scheduling 字段后 dirty state 正确。
- section 间切换不丢失 draft，也不弹离开确认。
- 离开 `/config/*` 时，如有 dirty，弹出确认 dialog。
- `Save` 提交完整 `AppConfig`。
- 保存成功后 dirty 清零，并以后端 canonical config 为准。
- 保存失败后，后端 field errors 映射到具体字段或 section summary。
- `Discard changes` 回滚到 saved snapshot 并清空 errors/buffers。
- `Restore General defaults` 会弹确认，确认后清空 General 到后端 defaults，但不自动保存。
- `Restore Scheduling defaults` 会弹确认，确认后替换 scheduling 到后端 defaults，但不自动保存。
- 数字字段编辑中间态不会污染 `draft: AppConfig` 类型。
- 前端不复制完整 Pydantic schema，只做基础输入校验。
- 保存 `language` 不承诺立即切换当前 UI 语言。

## 17. 实施顺序

1. 新增 `lib/configDocument.ts`，把 Config 类型从 legacy composable 中迁出。
2. 新增 `stores/configDocument.ts`。
3. 将 router 调整为 `ConfigView` 父路由 + section child route。
4. 新增 AlertDialog 基础组件。
5. 实现 `ConfigView.vue` 的 load/save/discard/dirty/guard。
6. 实现 feature-level field components，优先处理 number buffer。
7. 实现 `ConfigGeneralSection.vue`。
8. 实现 `ConfigSchedulingSection.vue`。
9. 补全 i18n 文案。
10. 运行 `npm run type-check` 与 `npm run build-only`。
