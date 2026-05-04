# Dashboard Analysis Spec -[DONE]

本文档定义 `dashboard-v2` 中 Dashboard 页的目标、信息架构、交互模型与后端数据契约。

该页面不是传统运营看板，而是一个面向“为什么切了 / 为什么没切”的时间分析台。用户打开它时，默认已经带着疑问而来；页面必须优先回答调度决策链，而不是只展示当前状态。

## 0. 实施状态（2026-05-04）

本 spec 继续定义 Dashboard Analysis 的整体框架，但实现已经进入 `dashboard-v2` 正式运行时阶段。

已完成：

- Dashboard 分析后端重构第一阶段已经完成。
- `core/diagnostics.py` 已定义中立 tick 诊断事实模型：
  - `MatchEvaluation`
  - typed `PolicyEvaluation` 变体
  - `ControllerDecision`
  - `ActuationOutcome`
  - `SchedulerTickTrace`
- `WEScheduler.on_tick` 当前直接产出 `SchedulerTickTrace`。
- `GET /api/analysis/window` 已经实现，返回 `TickSnapshot` 列表。
- `dashboard-v2` 已经接入正式运行时，当前 pywebview 加载的是 `dashboard-v2/dist`
- `dashboard-v2` 已经有最小 dashboard shell、Pinia analysis store 与正式 analysis 数据入口
- 旧 `/api/state`、`/api/ticks` 与 legacy `TickState` 页面状态建模已经退出新 Dashboard 路径

尚未完成：

- 顶部正式时间轴
- `live / snapshot` 双态与冻结窗口步进
- 完整的 `Sense / Think / Act` 三栏分析页

具体的 v1 交互、时间轴语法、双窗口状态模型与信息密度决策，见：

- [DASHBOARD_ANALYSIS_IMPLEMENTATION_SPEC.md](./DASHBOARD_ANALYSIS_IMPLEMENTATION_SPEC.md)

因此，后续 thread 若继续推进 Dashboard，应默认：

- core 数据事实已经准备好；
- 正式运行时接线已经完成；
- 下一步重点是 `dashboard-v2` 中的时间轴与分析页实现。

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

- 旧的 `TickState` 作为正式分析契约应当删去，不应继续扩展。
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
- `activePlaylist` / `matchedPlaylist` 的时间关系
- 切换事件 marker
- cycle 事件 marker
- paused 区间

说明：

- `resume marker` 不是 v1 必需语义；paused 区间结束后自然回到普通 tick。
- gate blocker 在 v1 中继续作为当前 tick 的精确诊断事实，而不是时间轴主视觉 overlay。

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

补充约束：

- `snapshot` 模式冻结的是前端当前窗口，而不是后端数据流。
- 锁定期间后台仍持续拉取最新 analysis window。
- keyboard step 应基于冻结窗口进行，而不是直接在实时 ring buffer 上步进。

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

注意：

- 这一节定义的是前端 analysis DTO，不是 core 领域对象。
- 当前 core 已经产出的是 `SchedulerTickTrace` 及其内嵌的中立诊断类型。
- API 层的职责是把 `SchedulerTickTrace` 映射成这里定义的 DTO，而不是继续从 `TickState` 反推。
- DTO mapper 可以接收少量显式运行时元信息，例如播放列表 display 映射；但这类 metadata 是后端实现输入，不属于前端返回契约。

### 6.1 TickSummary

`TickSummary` 用于顶部时间轴。

职责：

- 提供时间轴绘图所需最小数据。
- 表示该 tick 的结果摘要。
- 允许前端快速渲染 marker、状态色和曲线辅助信息。

建议结构：

```ts
type TickSummary = {
  tickId: number;
  ts: number;
  similarity: number;
  similarityGap: number;
  activePlaylist: string | null;
  activePlaylistDisplay: string | null;
  matchedPlaylist: string | null;
  matchedPlaylistDisplay: string | null;
  actionKind: "none" | "switch" | "cycle" | "hold" | "pause";
  reasonCode:
    | "no_match"
    | "hold_same_playlist"
    | "switch_allowed"
    | "switch_blocked_cooldown"
    | "switch_blocked_fullscreen"
    | "switch_blocked_cpu"
    | "switch_blocked_not_idle"
    | "cycle_allowed"
    | "cycle_blocked_cooldown"
    | "cycle_blocked_fullscreen"
    | "cycle_blocked_cpu"
    | "cycle_blocked_not_idle"
    | "scheduler_paused";
  paused: boolean;
  executed: boolean;
  hasEvent: boolean;
};
```

说明：

- `activePlaylist` 是该 tick 开始或结束时实际处于播放状态的列表。
- `matchedPlaylist` 是 matcher 在该 tick 给出的最优候选。
- 二者必须并存，不能再混成一个 `currentPlaylist` 字段。
- `hasEvent` 用于时间轴 marker，而不是简单等价于 `paused`。
- 第一版中，`hasEvent` 应优先用于 `switch` / `cycle` 等动作事件；暂停中的稳态 tick 不应因为每秒都处于 `pause` 而整段都变成事件 marker。

### 6.2 TickSnapshot

`TickSnapshot` 用于当前选中的完整分析视图。

职责：

- 承载当前 tick 的 `Sense -> Think -> Act` 全链路诊断。
- 作为下方三栏的唯一数据来源。

建议结构：

```ts
type TickSnapshot = {
  summary: TickSummary;
  sense: {
    window: {
      process: string;
      title: string;
    };
    idle: {
      seconds: number;
    };
    cpu: {
      averagePercent: number;
    };
    fullscreen: boolean;
    weather: {
      available: boolean;
      stale: boolean;
      id: number | null;
      main: string | null;
      sunrise: number | null;
      sunset: number | null;
    };
    clock: {
      localTs: number;
      hour: number;
      dayOfYear: number;
    };
  };
  think: {
    rawContextVector: Array<{ tag: string; weight: number }>;
    resolvedContextVector: Array<{ tag: string; weight: number }>;
    fallbackExpansions: Record<
      string,
      Array<{
        resolvedTag: string;
        weight: number;
      }>
    >;
    policies: PolicyDiagnostic[];
  };
  act: {
    topMatches: Array<{
      playlist: string;
      display: string;
      score: number;
    }>;
    controller: ControllerDiagnostic;
    decision: ActionDecision;
  };
};
```

### 6.3 PolicyDiagnostic

`PolicyDiagnostic` 表示某一个 policy 在当前 tick 的诊断结果。

职责：

- 表明该 policy 是否启用、是否活跃、贡献了什么。
- 把“这个 tag 为什么出现”解释成可读信息。
- 同时暴露 raw contribution 与 resolved contribution。

建议结构：

```ts
type BasePolicyDiagnostic = {
  enabled: boolean;
  active: boolean;
  weightScale: number;
  salience: number;
  intensity: number;
  effectiveMagnitude: number;
  direction: Array<{ tag: string; weight: number }>;
  rawContribution: Array<{ tag: string; weight: number }>;
  resolvedContribution: Array<{ tag: string; weight: number }>;
  dominantTag: string | null;
};

type PolicyDiagnostic =
  | (BasePolicyDiagnostic & {
      policyId: "activity";
      details: {
        matchSource: "title" | "process" | "none";
        matchedRule: string | null;
        matchedTag: string | null;
        windowTitle: string;
        process: string;
        emaActive: boolean;
      };
    })
  | (BasePolicyDiagnostic & {
      policyId: "time";
      details: {
        auto: boolean;
        hour: number;
        virtualHour: number;
        dayStartHour: number;
        nightStartHour: number;
        peaks: Record<string, number>;
      };
    })
  | (BasePolicyDiagnostic & {
      policyId: "season";
      details: {
        dayOfYear: number;
        peaks: Record<string, number>;
      };
    })
  | (BasePolicyDiagnostic & {
      policyId: "weather";
      details: {
        weatherId: number | null;
        weatherMain: string | null;
        available: boolean;
        mapped: boolean;
      };
    })
  | (BasePolicyDiagnostic & {
      policyId: string;
      details: Record<string, unknown>;
    });
```

说明：

- 当前 core 已经采用“每个 policy 自己携带 typed details”的方式，而不是通用 `explanation.kind + details` 魔法协议。
- 前端 DTO 应优先延续这套 typed details 思路，而不是再退回弱类型解释对象。
- `ActivityPolicy` 需要暴露究竟命中了 `process_rules` 还是 `title_rules`。
- `TimePolicy` 需要暴露当前 hour，以及是否走了 sunrise/sunset 自动模式。
- `WeatherPolicy` 需要暴露天气 `id` 与 `main`，否则 UI 无法解释天气贡献。

### 6.4 ControllerDiagnostic

`ControllerDiagnostic` 表示控制器对动作的判定过程。

职责：

- 暴露 controller 在本 tick 实际走到的那一路径评估。
- 回答“为什么这次没切 / 为什么这次没轮播”。
- 同时保留完整 blocker 事实，而不是只保留主因摘要。

建议结构：

```ts
type ControllerDiagnostic = {
  evaluation: {
    operation: "switch" | "cycle";
    allowed: boolean;
    blockedBy: Array<"cooldown" | "fullscreen" | "cpu" | "idle">;
    cooldownRemaining: number;
    idleSeconds: number;
    idleThreshold: number;
    cpuPercent: number;
    cpuThreshold: number | null;
    fullscreen: boolean;
    forceAfterRemaining: number | null;
  } | null;
};
```

说明：

- 不再同时暴露 `switchEval` / `cycleEval` 两份评估。
- `evaluation` 只表示当前 tick 实际走到的动作路径。
- `blockedBy` 必须保留全部 blocker；`ActionDecision.reasonCode` 只保留按优先级压缩后的主因。

### 6.5 ActionDecision

`ActionDecision` 表示该 tick 的最终动作语义。

职责：

- 为 `Act` 栏和时间轴 marker 提供统一动作结论。
- 将“推荐结果”和“真实执行结果”联系起来。
- 明确区分 controller 的“允许/阻止结论”和 actuator 的“是否真的执行成功”。

建议结构：

```ts
type ActionDecision = {
  kind: "none" | "switch" | "cycle" | "hold" | "pause";
  reasonCode:
    | "no_match"
    | "hold_same_playlist"
    | "switch_allowed"
    | "switch_blocked_cooldown"
    | "switch_blocked_fullscreen"
    | "switch_blocked_cpu"
    | "switch_blocked_not_idle"
    | "cycle_allowed"
    | "cycle_blocked_cooldown"
    | "cycle_blocked_fullscreen"
    | "cycle_blocked_cpu"
    | "cycle_blocked_not_idle"
    | "scheduler_paused";
  executed: boolean;
  activePlaylistBefore: string | null;
  activePlaylistAfter: string | null;
  matchedPlaylist: string | null;
};
```

说明：

- `reasonCode` 当前应表达 controller 的决策结论，例如 `switch_allowed`，而不是假装动作已经执行完成。
- actuator 是否真的执行成功，使用独立的 `executed` 字段表达。

### 6.6 当前 core 映射来源

后续 analysis API 实现时，建议按下面的关系做映射：

```text
SchedulerTickTrace
  -> TickSummary
  -> TickSnapshot
     -> PolicyDiagnostic[]
     -> ControllerDiagnostic
     -> ActionDecision
```

说明：

- `TickSummary / TickSnapshot` 是前端 DTO。
- `SchedulerTickTrace` 是当前已经落地的后端中立事实模型。
- legacy `TickState` 不应再作为分析页 DTO 的中间模型。

### 6.7 API mapper 的运行时元信息边界

Analysis DTO 的输入可以包含 `SchedulerTickTrace` 之外的少量运行时元信息，但边界应保持明确。

推荐约束：

- 运行时元信息应显式传入 mapper，而不是让 DTO 层直接依赖整个 `scheduler` 实例。
- 典型例子是播放列表 id 到 display name 的映射；这类信息不在 `SchedulerTickTrace` 内，但需要进入最终 DTO。
- 任何会被配置热重载改写的展示字段，都应在 snapshot 映射时冻结，而不是在 API 读取时临时回填。
- 这类 metadata 属于后端实现输入，不属于前端 wire contract。

## 7. Weather 的可用性 / 过期语义

“传感器不仅要给值，还要给是否可用/是否过期”这一要求，当前只对 `Weather` 是刚性需求。

结论：

- 第一版仅为 `weather` 建立 `available / stale` 语义。
- `window / idle / cpu / fullscreen / time` 暂不增加统一的可用性壳层。

原因：

- 这些本地传感器当前没有明显的缓存过期问题。
- `WeatherSensor` 是唯一带异步拉取、缓存、失败回退、冷启动等待的输入源。
- 把所有传感器一律包成 availability envelope，会增加复杂度但没有实际收益。

`weather.available = false` 的含义应收敛为“当前没有可用天气读数”，包括但不限于：

- weather policy 未启用
- API key 未配置或配置错误
- 远程抓取失败
- 冷启动阶段尚未拿到首个结果

若 UI 需要判断 weather policy 是否启用，应查看 `think.policies` 中 `policyId = "weather"` 的诊断，而不是在 `sense.weather` 重复暴露 `enabled`。

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
  liveTickId: number | null;
  ticks: Array<TickSnapshot>;
};
```

建议接口：

- `GET /api/analysis/window?count=900`

说明：

- `count=900` 对应最近约 15 分钟，按 1 秒 1 tick 计算。
- 若后续需要更长窗口，可继续放大 ring buffer。
- 第一版不需要 `GET /api/analysis/ticks/:id` 这类 detail-only 接口。
- `ticks` 表示“最近一段时间窗口”，但返回顺序应保持时间正序，即 `oldest -> newest`，以便前端直接驱动时间轴。
- `liveTickId` 指向服务端当前已知的最新 tick；在非空窗口中，通常对应 `ticks` 的最后一个元素。
- 服务端可以维护比 `count` 更大的内存 ring buffer，但具体容量属于实现细节，不在本 spec 中写死。

当前实现说明：

- 新 analysis API 的输入源应为 `SchedulerTickTrace`。
- 当前正式分析页路径只依赖 `/api/analysis/window`。
- 后续 thread 不应继续把 `TickState` 当作分析 API 的中间模型。

## 9. 前端状态模型

Dashboard 页应使用 Pinia 管理页面状态，不继续用旧的 `useApi()` 局部轮询状态作为长期方案。

建议 store：

```ts
type DashboardAnalysisStore = {
  liveWindow: TickSnapshot[];
  snapshotWindow: TickSnapshot[] | null;
  liveTickId: number | null;
  selectedTickId: number | null;
  hoverTickId: number | null;
  lockedTickId: number | null;
  mode: "live" | "snapshot";
  loading: boolean;
  error: string | null;
  newTicksSinceLocked: number;
};
```

派生规则：

- `liveWindow` 始终跟随后端最新窗口。
- `snapshotWindow` 在 click lock 时由当前 `liveWindow` 冻结得到，并在锁定期间保持不可变。
- `mode = "snapshot"` 时，keyboard step 只在 `snapshotWindow` 中移动。
- 未锁定时，`hoverTickId` 优先于 `liveTickId`。
- `TickSnapshot` 已经内含 `summary`，store 不应再把 summary/detail 重复拆成两份并排缓存。

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
- 默认展开策略不应简单依赖 `active` 布尔值；应优先展开当前 tick 中 `effectiveMagnitude` 最主导的前 `1 ~ 2` 个 policy。

### 10.3 Act 栏

展示候选、控制器结论和最终动作。

推荐内容：

- Top 5 候选播放列表
- 当前推荐第一名
- 当前实际播放列表
- `ControllerDiagnostic`
- `ActionDecision`

说明：

- `Act` 栏默认应优先展示当前决策结论与相关 blocker 证据，不要求把所有 evaluation 字段平铺在默认层。

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

1. 后端先定义新的 tick 诊断快照模型。已完成（core phase 1）。
2. 后端增加新的 analysis window 接口。已完成。
3. 前端建立 Pinia store、类型定义与正式运行时接线。已完成。
4. 前端接入顶部时间轴与三栏分析页。
5. 时间轴与三栏稳定后，清理仍只服务旧 Dashboard 的残余实现。

## 12. 验收标准

实现完成后，Dashboard 页至少应满足以下验收条件：

1. 用户能在任意可见 tick 上看出 `matchedPlaylist` 与 `activePlaylist` 是否一致。
2. 用户能在“没切换”的 tick 上直接看到阻塞原因，而不是只看到一个布尔结果。
3. 用户能在 `Think` 栏看出各个 policy 的贡献来源。
4. 用户能区分 `rawContextVector` 与 `resolvedContextVector`。
5. 用户能在天气不可用时看出“未参与决策”而不是误读为“天气贡献为 0”。
6. hover scrub 不触发逐 tick 网络请求。
7. `snapshot` 锁定后，keyboard step 基于冻结窗口稳定工作，不会被实时刷新打断。
8. 页面不再依赖旧 `TickState`。
