# Config Editor Spec

本文档定义 `dashboard-v2` 中 Config 页的导航模型、页面骨架、编辑器布局与后端契约。

Config 页的目标不是“把 `scheduler_config.json` 可视化”，而是让用户在不理解 JSON 嵌套结构的前提下，完成对调度器的正式配置。

## 1. 目标

Config 页必须满足以下目标：

- 用户不需要编辑 JSON 文件。
- 用户不需要理解原始对象嵌套路径。
- 支持多类配置对象：
  - 单例配置
  - 集合型资源
  - 策略型配置
- 配置导航与编辑区职责清晰，不出现无限嵌套侧栏。
- 适配桌面软件式工作台，而不是传统网页表单页。

## 2. 核心结论

本页采用以下设计结论：

1. 不使用 `Rail + Config 专属宽侧栏` 双侧栏方案。
2. 全局只保留一个 `WorkbenchSidebar`。
3. `WorkbenchSidebar` 本身支持一二级层级导航，通过强调和缩进组织。
4. `Config` 的章节导航直接作为全局 Sidebar 中 `Config` 节点下的子项出现。
5. `Config` 工作区内部不再出现“二级导航侧栏”；内部出现的是资源浏览器或编辑器，而不是新的导航层。
6. `Policies` 使用顶部 selector，不使用左侧资源列表。

这套方案的优点是：

- `Dashboard / History` 依然可以保持扁平导航。
- `Config` 可以拥有二级章节，而不需要额外生成一块只在 Config 出现的宽导航侧栏。
- 未来若 `History` 或其他页面出现子章节，也可复用同一导航模型。

## 3. Sidebar 导航模型

### 3.1 全局 Sidebar 的职责

全局 Sidebar 负责应用级路由与章节级路由的统一承载。

一级项：

- `Dashboard`
- `Config`
- `History`

二级项：

- 仅在某个一级项具备子章节时出现。
- 当前阶段只有 `Config` 有二级项。

`Config` 的二级项：

- `General`
- `Playlists`
- `Tags`
- `Policies`
- `Scheduling`

### 3.2 为什么不用第二块专属 Config Sidebar

不采用 “App Rail + Config Navigator” 的原因如下：

- 当前只有 `Config` 有稳定二级章节，单独为它引入第二块持久侧栏会造成壳层不均衡。
- `Dashboard` 和 `History` 没有对应的第二块导航，切页面时整体版式会突然改变。
- 在工作区内部还需要 `Playlists / Tags` 的资源浏览器；如果外面再多一块专属导航侧栏，左侧层级会显得过重。

因此，最合适的方案是：

- 用一个统一的 Sidebar 承载层级导航。
- 用视觉层级，而不是额外的版面列，区分一级与二级。

### 3.3 层级导航的视觉规则

全局 Sidebar 中，一二级导航必须明确区分。

一级导航应具备：

- 图标
- 更高强调度
- 更大的点击块
- 可代表全局路由切换

二级导航应具备：

- 明显缩进
- 较弱的视觉权重
- 可选无图标
- 只在父级项展开时出现

可参考类似 Codex 的信息组织方式：

- 一级项承担“模块”语义
- 二级项承担“当前模块内章节”语义

### 3.4 Sidebar 必须是可组合的

`WorkbenchSidebar` 必须支持混合导航深度。

也就是说，同一套侧栏结构应允许：

- `Dashboard` 只有一级项
- `History` 只有一级项
- `Config` 拥有一级项 + 二级子项

这是正式设计要求，不是临时例外。

## 4. 路由模型

Config 页不应继续用本地 tab 状态充当真实导航。

推荐路由：

```text
/dashboard
/config/general
/config/playlists
/config/tags
/config/policies
/config/scheduling
/history
```

说明：

- 章节切换由 Vue Router 驱动，而不是局部组件状态驱动。
- Sidebar 的二级项直接对应这些 section route。
- 页面刷新后应能恢复到当前 section。

### 4.1 资源选择状态

对于集合型 section，可在 query 中保存当前选中对象：

```text
/config/playlists?name=BRIGHT_FLOW
/config/tags?tag=%23dawn
/config/policies?policy=activity
```

其中：

- `Playlists` 与 `Tags` 建议使用 query 持久化当前选中对象。
- `Policies` 虽然使用顶部 selector，但仍可把当前 policy 写进 query，保证可刷新恢复。

## 5. Config 页面骨架

Config 工作区只分为两类布局：

1. 单例编辑页
2. 资源编辑工作台

### 5.1 单例编辑页

用于：

- `General`
- `Scheduling`

特征：

- 单一对象
- 不需要对象列表
- 直接全宽或中宽表单
- 可在页面头部提供 `Restore defaults`

### 5.2 资源编辑工作台

用于：

- `Playlists`
- `Tags`
- `Policies`

特征：

- 包含对象选择与对象编辑
- 编辑器驻留在工作区内部
- 不再通过 modal 承担主要编辑流程

## 6. 各 Section 布局模式

### 6.1 General

`General` 是单例编辑页。

包含字段：

- `wallpaper_engine_path`
- `language`

建议分组：

- `Runtime`
  - `wallpaper_engine_path`
- `Locale`
  - `language`

建议操作：

- `Auto Detect Wallpaper Engine`
- `Validate Path`
- `Restore defaults`

### 6.2 Scheduling

`Scheduling` 是单例编辑页。

包含字段：

- `startup_delay`
- `idle_threshold`
- `switch_cooldown`
- `cycle_cooldown`
- `force_after`
- `cpu_threshold`
- `cpu_sample_window`
- `pause_on_fullscreen`

建议分组：

- `Startup`
- `Switching`
- `Cycling`
- `Idle`
- `Gates`

### 6.3 Playlists

`Playlists` 使用 `browser + detail` 布局。

工作区结构：

- 左：Playlist Browser
- 右：Playlist Detail Editor

#### Playlist Browser

它是资源浏览器，不是导航侧栏。

必须具备：

- 搜索
- 列表计数
- `Create playlist`
- 选中态
- 可显示 display name / internal name

可以显示的摘要信息：

- `display`
- `name`
- 主要 tag 数量
- 最近是否有未保存修改

#### Playlist Detail Editor

详情区分两组：

- `Identity`
  - `name`
  - `display`
- `Tag Vector`
  - tags 列表
  - tag 权重编辑
  - 批量添加

设计要求：

- 旧的 modal 主编辑模式应废弃。
- 主编辑流程应在工作区内完成。

### 6.4 Tags

`Tags` 使用 `browser + detail` 布局。

工作区结构：

- 左：Tag Browser
- 右：Tag Detail Editor

#### Tag Browser

显示：

- tag 名称
- 是否有 fallback
- fallback 边数量

#### Tag Detail Editor

详情区分两组：

- `Identity`
  - 当前 tag 名称
- `Fallback`
  - fallback target 列表
  - 每条 edge 的权重

设计要求：

- `tags` 不应以原始 JSON key-value 形式暴露。
- fallback 应被视为边列表，而不是嵌套对象。

### 6.5 Policies

`Policies` 使用“顶部 selector + 下方详情编辑器”。

不使用左侧资源浏览器，原因：

- policy 类型数量固定且很少。
- 它们更像模式切换，而不是大量对象集合。
- 单独为 4 个正式策略保留一块浏览器栏位，空间利用率偏低。

工作区结构：

- 顶部：Policy Selector
- 下方：Policy Detail Editor

正式支持的 policy：

- `activity`
- `time`
- `season`
- `weather`

#### Policy Selector

Policy Selector 可使用：

- segmented control
- tabs-like selector
- pill list

但它必须满足：

- 横向切换
- 清晰显示当前 policy
- 不承担字段编辑，只承担 policy 切换

#### Policy Detail Editor

所有 policy 详情区都遵守统一结构：

1. 通用头部
2. 该 policy 的专属字段组

通用头部：

- `enabled`
- `weight_scale`
- `Restore policy defaults`

各 policy 详情：

`Activity`

- `Matching`
  - `process_rules`
  - `title_rules`
- `Behavior`
  - `smoothing_window`

`Time`

- `Mode`
  - `auto`
- `Boundaries`
  - `day_start_hour`
  - `night_start_hour`

`Season`

- `Peaks`
  - `spring_peak`
  - `summer_peak`
  - `autumn_peak`
  - `winter_peak`

`Weather`

- `Provider`
  - `api_key`
- `Location`
  - `lat`
  - `lon`
- `Fetch`
  - `fetch_interval`
  - `request_timeout`
  - `warmup_timeout`

## 7. 资源浏览器与 Sidebar 的区分

`Playlists` 和 `Tags` 的左侧浏览器虽然也出现在左边，但它们不是导航。

必须和 Sidebar 做出明确视觉区分。

Sidebar 的特征：

- 跨页面存在
- 承担 route 切换
- 视觉更像 chrome

资源浏览器的特征：

- 只存在于当前 section 的工作区
- 承担对象选择，不承担页面导航
- 视觉更像 panel / list / inspector
- 应具有搜索、计数、创建等资源管理工具

这是必须严格遵守的职责边界。

## 8. 数据模型与 API 契约

### 8.1 返回 normalized config

`GET /api/config` 不应继续返回“用户写了什么就原样返回什么”的裸 JSON。

后端应返回 normalize 后的完整配置对象。

原因：

- 默认值属于后端 schema 语义，不应由前端手动补全。
- 前端只应编辑完整模型，不应推测缺省字段。

### 8.2 同时返回 defaults

为了支持“恢复默认”，后端需要同时返回默认值树。

建议响应结构：

```ts
type ConfigDocumentResponse = {
  current: AppConfig
  defaults: AppConfig
  capabilities: {
    supportedPolicies: Array<"activity" | "time" | "season" | "weather">
  }
}
```

说明：

- `current` 是 normalize 后的当前配置。
- `defaults` 是同 schema 下的默认值树。
- `capabilities.supportedPolicies` 用于前端显式渲染正式支持的策略。

### 8.3 Restore Defaults 语义

恢复默认不是“删除字段”，而是“用 defaults 中对应节点替换 current 节点”。

例如：

- 恢复 `Season` policy 默认值：
  - `current.policies.season = defaults.policies.season`
- 恢复 `Scheduling` 默认值：
  - `current.scheduling = defaults.scheduling`

第一版至少支持以下粒度：

- section 级 restore
- policy 级 restore

字段级 restore 不是首版必需。

## 9. Schema 约束

### 9.1 Policies 禁止未知 key

`policies` 不再允许未知策略类型混入。

正式要求：

- 后端 schema 对 `policies` 使用 `extra="forbid"`
- 未知 policy key 在保存时直接报错
- 前端只渲染正式支持的 policy 类型

原因：

- “静默接受但运行时忽略”不适合 GUI 配置系统
- UI 驱动配置必须保证每个策略都有明确语义和编辑器

### 9.2 前端不得自行发明默认值

前端不应：

- 手动补默认值
- 通过字段缺失推断语义
- 用局部 fallback 代替正式 schema 默认值

## 10. 编辑交互原则

Config 页遵守以下交互原则：

- 主编辑流程必须驻留在工作区，不以 modal 为主。
- 路由切换与对象选择必须尽量可恢复。
- 保存前允许本地脏状态存在。
- `Save` 应是显式操作，不在每次编辑时自动提交后端。
- 删除、重置、覆盖默认值属于危险或不可逆操作，应有明确确认。

## 11. 建议状态模型

建议使用 Pinia 管理 Config 编辑状态。

可拆分为：

- `configDocumentStore`
  - `current`
  - `defaults`
  - `loading`
  - `saving`
  - `dirty`
  - `fieldErrors`
- `configUiStore`
  - `activeSection`
  - `selectedPlaylistName`
  - `selectedTag`
  - `selectedPolicy`
  - `searchQuery`

## 12. 实施顺序

建议按以下顺序实现：

1. 收紧后端 schema，禁止 `policies` 未知 key。
2. 重构 `/api/config`，返回 `current + defaults + capabilities`。
3. 在 router 中引入 `config/<section>` 路由模型。
4. 在 `WorkbenchSidebar` 中支持层级导航与缩进规则。
5. 先实现 `General` 与 `Scheduling` 单例页。
6. 实现 `Playlists` 的 `browser + detail`。
7. 实现 `Tags` 的 `browser + detail`。
8. 实现 `Policies` 的顶部 selector + detail editor。

## 13. 验收标准

实现完成后，Config 页至少应满足以下条件：

1. 用户可以在不接触 JSON 的前提下完成全部正式配置。
2. `Config` 的章节切换由 Router 驱动，而不是局部 tab 状态驱动。
3. Sidebar 能同时承载一级导航和 `Config` 的二级章节导航。
4. `Playlists` 与 `Tags` 的对象选择在工作区内完成，而不是通过 modal 主导。
5. `Policies` 使用顶部 selector，而不是左侧对象列表。
6. 前端不再手动补默认值。
7. 用户可以恢复 `Scheduling` 或某个 policy 的默认值。
8. 未知 policy key 无法通过保存校验。
