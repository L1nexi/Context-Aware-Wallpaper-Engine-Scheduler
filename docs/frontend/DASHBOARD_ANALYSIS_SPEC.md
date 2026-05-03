# Dashboard Analysis Spec

本文档定义 `dashboard-v2` 中 Dashboard 页的目标、信息架构、交互模型与后端数据契约。

该页面不是传统运营看板，而是一个面向“为什么切了 / 为什么没切”的时间分析台。用户打开它时，默认已经带着疑问而来；页面必须优先回答调度决策链，而不是只展示当前状态。

## 1. 目标

Dashboard 页必须满足以下目标：

- 以时间为主轴，而不是以卡片拼盘为主轴。
- 让用户能沿着 `Sense -> Think -> Act` 追溯某一个 tick 的完整决策。
- 同时回答两类问题：
  - 为什么切了。
  - 为什么没切。
- 能分清算法“想切到谁”和系统“实际正在播谁”。
- 对 hover / scrub / 锁定快照的交互足够顺滑，适配本地 WebView 场景。

## 2. 非目标

当前版本不追求以下目标：

- 不做跨天、跨周的长期取证系统。
- 不把完整 tick 诊断历史落盘为长期审计数据库。
- 不继续兼容旧 Element Plus Dashboard 的状态模型。
- 不为旧 `TickState` 做增量补丁。

## 3. Breaking Change 立场

当前项目仍处于 `0.x`，允许为建立正确模型进行 breaking change。

结论：

- 旧的 `TickState` 应当删去，不应继续扩展。
- 旧的 `/api/state` 与 `/api/ticks` 若只服务于旧 Dashboard，应在迁移后删除或改造成新分析接口。
- 新 Dashboard 不应围绕“当前状态摘要”建模，而应围绕“tick 诊断快照”建模。

原因：

- 旧 `TickState` 混淆了“匹配结果”和“真实播放状态”。
- 旧 `TickState` 只能支持“发生了什么”，不能稳定回答“为什么没发生”。
- 继续在旧结构上堆字段，会把前端和后端都拖入过渡态。

## 4. 页面骨架

页面采用两级结构：

1. 顶部全宽时间轴区
2. 下方三栏分析区

### 4.1 顶部时间轴区

顶部区域是页面主角，不是附属图表。

职责：

- 以时间序列展示相似度曲线。
- 展示调度事件 marker。
- 展示“推荐播放列表”和“实际播放列表”的分歧区间。
- 作为 scrub / hover / lock 的主交互入口。

建议显示的信息：

- `similarity`
- `similarity_gap`
- 切换事件 marker
- cycle 事件 marker
- pause / resume marker
- 被 gate 阻塞的区段标记

### 4.2 下方三栏分析区

下方固定为三栏，不把 `Policy` 单独拆成第四栏。

- 左栏：`Sense`
- 中栏：`Think`
- 右栏：`Act`

原因：

- 它与调度架构一致。
- 它天然形成“输入 -> 解释 -> 决策”的阅读顺序。
- `Policy` 本质属于 `Think`，因为它是在解释上下文如何转化为决策，而不是独立终点。

## 5. 交互模型

### 5.1 时间轴行为

时间轴采用 `hover scrub + click lock` 组合。

- `hover`
  - 直接切换下方三栏到对应 tick 的快照。
  - 该切换应是本地内存级切换，不再向后端逐 tick 请求。
- `click`
  - 锁定当前 tick。
  - 锁定后，新的 hover 不再覆盖当前分析目标，直到用户解除锁定或切回 live。
- `leave`
  - 未锁定时，回到 live tick。
- `keyboard`
  - 支持左右步进相邻 tick。

### 5.2 Live / Snapshot 双态

页面需要明确区分：

- `live`
  - 始终跟随最新 tick。
- `snapshot`
  - 固定查看某个历史 tick。

状态切换规则：

- 默认进入 `live`。
- hover 时间轴时进入临时 scrub。
- click 后进入锁定 `snapshot`。
- 点击“回到实时”后恢复 `live`。

### 5.3 本地 WebView 场景假设

前端运行在本地 WebView 中，后端 API 也在本地环回地址上。

因此：

- 没有必要把时间轴 summary 和 tick detail 强行拆成两套请求。
- 直接拉取“最近一段时间的完整 tick 诊断快照”是合理的。
- 前端应以本地内存切换为主，避免 hover 期间频繁触发请求。

## 6. 核心数据模型

本页面的核心数据模型分为五个主类型：

- `TickSummary`
- `TickSnapshot`
- `PolicyDiagnostic`
- `ControllerDiagnostic`
- `ActionDecision`

### 6.1 TickSummary

`TickSummary` 用于顶部时间轴。

职责：

- 提供时间轴绘图所需最小数据。
- 表示该 tick 的结果摘要。
- 允许前端快速渲染 marker、状态色和曲线辅助信息。

建议结构：

```ts
type TickSummary = {
  tickId: number
  ts: number
  similarity: number
  similarityGap: number
  activePlaylist: string | null
  activePlaylistDisplay: string | null
  matchedPlaylist: string | null
  matchedPlaylistDisplay: string | null
  actionKind: "none" | "switch" | "cycle" | "hold" | "pause"
  reasonCode:
    | "no_match"
    | "hold_same_playlist"
    | "switch_executed"
    | "switch_blocked_cooldown"
    | "switch_blocked_fullscreen"
    | "switch_blocked_cpu"
    | "switch_blocked_not_idle"
    | "cycle_executed"
    | "cycle_blocked_cooldown"
    | "cycle_blocked_fullscreen"
    | "cycle_blocked_cpu"
    | "cycle_blocked_not_idle"
    | "scheduler_paused"
  paused: boolean
  hasEvent: boolean
}
```

说明：

- `activePlaylist` 是该 tick 开始或结束时实际处于播放状态的列表。
- `matchedPlaylist` 是 matcher 在该 tick 给出的最优候选。
- 二者必须并存，不能再混成一个 `currentPlaylist` 字段。

### 6.2 TickSnapshot

`TickSnapshot` 用于当前选中的完整分析视图。

职责：

- 承载当前 tick 的 `Sense -> Think -> Act` 全链路诊断。
- 作为下方三栏的唯一数据来源。

建议结构：

```ts
type TickSnapshot = {
  summary: TickSummary
  sense: {
    window: {
      process: string
      title: string
    }
    idle: {
      seconds: number
    }
    cpu: {
      averagePercent: number
    }
    fullscreen: boolean
    weather: {
      enabled: boolean
      available: boolean
      stale: boolean
      id: number | null
      main: string | null
      sunrise: number | null
      sunset: number | null
    }
    clock: {
      localTs: number
      hour: number
      dayOfYear: number
    }
  }
  think: {
    rawContextVector: Array<{ tag: string; weight: number }>
    resolvedContextVector: Array<{ tag: string; weight: number }>
    fallbackExpansions: Array<{
      sourceTag: string
      resolvedTag: string
      weight: number
    }>
    policies: PolicyDiagnostic[]
  }
  act: {
    topMatches: Array<{
      playlist: string
      display: string
      score: number
    }>
    controller: ControllerDiagnostic
    decision: ActionDecision
  }
}
```

### 6.3 PolicyDiagnostic

`PolicyDiagnostic` 表示某一个 policy 在当前 tick 的诊断结果。

职责：

- 表明该 policy 是否启用、是否活跃、贡献了什么。
- 把“这个 tag 为什么出现”解释成可读信息。
- 同时暴露 raw contribution 与 resolved contribution。

建议结构：

```ts
type PolicyDiagnostic = {
  policyId: "activity" | "time" | "season" | "weather" | string
  enabled: boolean
  active: boolean
  weightScale: number
  salience: number
  intensity: number
  effectiveMagnitude: number
  direction: Array<{ tag: string; weight: number }>
  rawContribution: Array<{ tag: string; weight: number }>
  resolvedContribution: Array<{ tag: string; weight: number }>
  dominantTag: string | null
  explanation: {
    kind:
      | "activity_process_rule"
      | "activity_title_rule"
      | "time_window"
      | "season_window"
      | "weather_code"
      | "inactive"
    label: string
    details: Record<string, string | number | boolean | null>
  }
}
```

说明：

- `ActivityPolicy` 需要暴露究竟命中了 `process_rules` 还是 `title_rules`。
- `TimePolicy` 需要暴露当前 hour、dominant tag，以及是否走了 sunrise/sunset 自动模式。
- `WeatherPolicy` 需要暴露天气 `id` 与 `main`，否则 UI 无法解释天气贡献。

### 6.4 ControllerDiagnostic

`ControllerDiagnostic` 表示控制器对动作的判定过程。

职责：

- 把布尔 `can_switch` / `can_cycle` 还原为有原因的决策。
- 回答“为什么这次没切”。

建议结构：

```ts
type ControllerDiagnostic = {
  switchEval: {
    allowed: boolean
    blockedBy: Array<"cooldown" | "fullscreen" | "cpu" | "idle" | "paused">
    cooldownRemaining: number
    idleSeconds: number
    idleThreshold: number
    cpuPercent: number
    cpuThreshold: number | null
    fullscreen: boolean
    forceAfterRemaining: number | null
  }
  cycleEval: {
    allowed: boolean
    blockedBy: Array<"cooldown" | "fullscreen" | "cpu" | "idle" | "paused">
    cooldownRemaining: number
    idleSeconds: number
    idleThreshold: number
    cpuPercent: number
    cpuThreshold: number | null
    fullscreen: boolean
  }
}
```

### 6.5 ActionDecision

`ActionDecision` 表示该 tick 的最终动作语义。

职责：

- 为 `Act` 栏和时间轴 marker 提供统一动作结论。
- 将“推荐结果”和“真实执行结果”联系起来。

建议结构：

```ts
type ActionDecision = {
  kind: "none" | "switch" | "cycle" | "hold" | "pause"
  reasonCode:
    | "no_match"
    | "hold_same_playlist"
    | "switch_executed"
    | "switch_blocked_cooldown"
    | "switch_blocked_fullscreen"
    | "switch_blocked_cpu"
    | "switch_blocked_not_idle"
    | "cycle_executed"
    | "cycle_blocked_cooldown"
    | "cycle_blocked_fullscreen"
    | "cycle_blocked_cpu"
    | "cycle_blocked_not_idle"
    | "scheduler_paused"
  summary: string
  activePlaylistBefore: string | null
  activePlaylistAfter: string | null
  matchedPlaylist: string | null
}
```

## 7. Weather 的可用性 / 过期语义

“传感器不仅要给值，还要给是否可用/是否过期”这一要求，当前只对 `Weather` 是刚性需求。

结论：

- 第一版仅为 `weather` 建立 `enabled / available / stale` 语义。
- `window / idle / cpu / fullscreen / time` 暂不增加统一的可用性壳层。

原因：

- 这些本地传感器当前没有明显的缓存过期问题。
- `WeatherSensor` 是唯一带异步拉取、缓存、失败回退、冷启动等待的输入源。
- 把所有传感器一律包成 availability envelope，会增加复杂度但没有实际收益。

未来若新增远程或缓存型传感器，再考虑推广为统一模型。

## 8. 后端传输契约

本页面在概念上区分 `TickSummary` 和 `TickSnapshot`，但在 API 传输上不做 summary/detail 拆分。

原因：

- 前端运行在本地 WebView，不是公网高延迟页面。
- 用户需要 hover scrub。
- summary/detail 拆分会把交互变成大量二次请求，收益很低。

建议提供单一窗口接口：

```ts
type TickWindowResponse = {
  liveTickId: number | null
  ticks: Array<{
    summary: TickSummary
    snapshot: TickSnapshot
  }>
}
```

建议接口：

- `GET /api/analysis/window?count=900`

说明：

- `count=900` 对应最近约 15 分钟，按 1 秒 1 tick 计算。
- 若后续需要更长窗口，可继续放大 ring buffer。
- 第一版不需要 `GET /api/analysis/ticks/:id` 这类 detail-only 接口。

## 9. 前端状态模型

Dashboard 页应使用 Pinia 管理页面状态，不继续用旧的 `useApi()` 局部轮询状态作为长期方案。

建议 store：

```ts
type DashboardAnalysisStore = {
  ticks: Array<{
    summary: TickSummary
    snapshot: TickSnapshot
  }>
  liveTickId: number | null
  selectedTickId: number | null
  hoverTickId: number | null
  lockedTickId: number | null
  mode: "live" | "snapshot"
  loading: boolean
  error: string | null
}
```

派生规则：

- `lockedTickId !== null` 时，优先显示 locked tick。
- 否则 `hoverTickId !== null` 时，显示 hover tick。
- 否则显示 `liveTickId`。

## 10. 页面区块职责

### 10.1 Sense 栏

展示传感器输入本身，而不是策略结果。

推荐内容：

- 前台进程
- 前台窗口标题
- idle 秒数
- CPU 平滑值
- fullscreen 状态
- weather 状态与数据
- 本地时间 / day-of-year

### 10.2 Think 栏

展示从传感器到上下文向量的解释层。

推荐内容：

- `rawContextVector`
- `resolvedContextVector`
- fallback 展开链
- 各 `PolicyDiagnostic`

说明：

- `Policy` 在此栏是解释器，不是独立终局。

### 10.3 Act 栏

展示候选、控制器结论和最终动作。

推荐内容：

- Top 5 候选播放列表
- 当前推荐第一名
- 当前实际播放列表
- `ControllerDiagnostic`
- `ActionDecision`

## 11. 迁移要求

### 11.1 必须删除的旧模型

迁移到新 Dashboard 时，以下旧模型不应保留为正式契约：

- 旧 `TickState`
- 旧前端 `TickState` TypeScript 接口
- 旧 `useApi.ts` 中围绕 `/api/state` 与 `/api/ticks` 的页面状态建模

### 11.2 必须保留的后端事实

迁移时必须保留并重新组织以下事实：

- 当前 tick 的 matcher 结果
- 当前 tick 的 controller 评估
- 当前 tick 的 actuator 决策
- 当前 tick 的真实 active playlist
- 当前 tick 的 top matches
- 当前 tick 的 policy 级贡献

### 11.3 实施顺序

建议按以下顺序落地：

1. 后端先定义新的 tick 诊断快照模型。
2. 后端增加新的 analysis window 接口。
3. 前端建立 Pinia store 与类型定义。
4. 前端接入顶部时间轴与三栏分析页。
5. 新 Dashboard 可用后，删除旧 `TickState` 与旧状态接口。

## 12. 验收标准

实现完成后，Dashboard 页至少应满足以下验收条件：

1. 用户能在任意可见 tick 上看出 `matchedPlaylist` 与 `activePlaylist` 是否一致。
2. 用户能在“没切换”的 tick 上直接看到阻塞原因，而不是只看到一个布尔结果。
3. 用户能在 `Think` 栏看出各个 policy 的贡献来源。
4. 用户能区分 `rawContextVector` 与 `resolvedContextVector`。
5. 用户能在天气不可用时看出“未参与决策”而不是误读为“天气贡献为 0”。
6. hover scrub 不触发逐 tick 网络请求。
7. 页面不再依赖旧 `TickState`。
