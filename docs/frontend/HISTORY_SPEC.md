# History Spec

本文档定义 `dashboard-v2` 中 `History` 页的正式产品定位、时间粒度模型、页面结构与后端数据契约。

`History` 不再被定义为“事件时间线页”，而被定义为“回顾、画像、趋势”页面。它的主语义是长期输出结果的分布与变化，而不是逐条审计某一刻为什么切换。

## 1. 目标

`History` 页必须满足以下目标：

- 支持用户从 `24h` 到 `180d+` 的多粒度回顾。
- 以 playlist 占比和趋势为核心事实，而不是以事件序列为核心事实。
- 让用户能看见“系统长期偏向了什么风格”。
- 支持用户从粗粒度视图逐步下钻到更细粒度视图。
- 与 `Dashboard`、`Simulator` 建立清晰边界，避免职责混杂。

## 2. 核心用户故事

### 2.1 故事 A：季节性变化

用户使用调度器半年后，进入夏季，壁纸不知不觉切到了夏日主题。用户打开 `History`，在 `90d` 或 `180d` 视图中看到：

- 夏日主题 playlist 的占比逐渐上升。
- 春季主题 playlist 的占比逐渐下降。

这类故事的关键不是某一次切换事件，而是长期比例变化。

### 2.2 故事 B：天气阶段影响

过去一周上海连绵多雨，用户打开 `7d` 视图，看到：

- `RAINY_MOOD` 或类似雨景 playlist 的占比明显偏高。
- 同期晴天/日常主题的占比下降。

这类故事同样依赖聚合结果，而不是单次时间线事件。

## 3. Breaking Change 立场

当前项目仍处于 `0.x`，允许对旧 `History` 模型进行彻底替换。

正式结论：

- `segments` 应直接弃用。
- 旧的“Gantt 时间线 + 事件列表”不再是 `History` 的主信息架构。
- 旧 `/api/history` 若只服务于 `segments` 视图，应允许删除或降级为辅助接口。
- `/api/history/aggregate` 的思想应升级为 `History` 的正式主数据模型。

原因：

- `segments` 只适合极短时间窗。
- 时间窗一旦变粗，`segments` 会退化为低信息密度横条。
- 长期回顾的核心事实是 `bucketed playlist ratio`，不是连续区段。

## 4. 产品定位

### 4.1 History 的正式职责

`History` 的主职责是：

- 回顾
- 画像
- 趋势

它回答的问题是：

- 这段时间系统整体更偏向哪些 playlist。
- 某个主题是否正在逐渐上升或下降。
- 某段时间的输出风格是什么。

### 4.2 Dashboard 的职责

`Dashboard` 的主职责是：

- 实时诊断
- 近时段解释

它回答的问题是：

- 为什么刚才没切。
- 为什么刚才切了。
- 当前 tick 的 `Sense -> Think -> Act` 是什么。

### 4.3 Simulator 的职责

`Simulator` 的主职责是：

- 调优
- 测试
- what-if 分析

它回答的问题是：

- 如果修改 policy 参数会发生什么。
- 如果修改 playlist tags，哪些场景会改变获胜者。
- 某个策略数学是否符合预期。

## 5. 核心模型

### 5.1 Output-Centric History

`History` 的主语义是实际输出结果，而不是内部推理状态。

正式主数据：

- playlist 占用时长
- playlist 占比
- 切换次数
- cycle 次数
- pause 时长

不是主数据的内容：

- 每个 policy 的 direction / salience / intensity
- 每 tick 的阻塞原因
- 逐 tick 的诊断快照

这些内容属于 `Dashboard` 或 `Simulator`。

### 5.2 Ambient / Event 只是解释框架，不是 v1 主模型

可以用以下框架帮助用户理解长期历史：

- `Ambient`
  - `Time`
  - `Season`
- `Event`
  - `Weather`
  - `Activity`

但 `History v1` 不应承诺长期范围下的精确因果归因。

原因：

- 当前持久化历史主要记录动作和输出，而不是长期保存的完整 policy 诊断。
- 在 `30d / 180d` 范围上强行做细粒度因果解释，容易产生伪解释。

因此：

- `History v1` 保持 output-centric。
- `Ambient / Event` 作为概念框架保留。
- 更深的策略解释与调优迁移到 `Simulator`。

## 6. 时间范围与粒度模型

### 6.1 预设范围优先

`History` 的主入口使用预设时间范围：

- `24h`
- `7d`
- `30d`
- `90d`
- `180d`
- 未来可扩展 `365d`

原因：

- 用户最常见的问题是“过去一周 / 一个月 / 半年怎么样”。
- 预设范围能覆盖绝大多数真实使用场景。

### 6.2 支持自定义范围，但不是一等入口

`History` 应支持高级用户自定义 `from / to`。

但正式要求：

- 自定义范围是高级入口，不是默认主入口。
- 前端不暴露手动 bucket 配置。
- 系统自动选择 granularity。

用户输入的是“看多久”，不是“每几个小时聚合一次”。

### 6.3 自动粒度

granularity 由系统自动推导。

正式要求：

- 前端不直接让用户选 `bucket_minutes`。
- 后端根据时间跨度自动选择 bucket size。
- 目标是让图上 bucket 数保持在合理区间，不致于过密或过 sparse。

建议范围：

- 目标 bucket 数约 `24 ~ 120`

示例策略：

- `24h` -> `30m` 或 `1h`
- `7d` -> `6h`
- `30d` -> `1d`
- `90d` -> `1w`
- `180d` -> `1w` 或 `2w`

具体阈值可由实现阶段微调，但前端不持有这套规则。

## 7. 页面结构

`History` 页采用三段式结构：

1. 顶部控制区
2. 主图区
3. 辅助洞察区

### 7.1 顶部控制区

顶部控制区包含：

- range presets
- custom range 入口
- 当前 granularity 显示
- drilldown / reset view 控件

说明：

- 如果用户选择自定义范围，顶部仍应显示系统自动选择的 granularity。
- granularity 是反馈信息，不是主控制项。

### 7.2 主图区

主图区统一使用 `playlist composition over time` 语义。

正式主图：

- `stacked area chart`

该图承担以下职责：

- 展示 playlist 占比随时间变化
- 支持不同时间范围下的统一阅读方式
- 支持点击 bucket 进行 drilldown

实现细节允许：

- 当 bucket 数很少时，渲染层可以退化为 `stacked bar`
- 但产品语义保持不变，仍然是 composition chart family

### 7.3 辅助洞察区

辅助洞察区用于承接非主图信息。

建议包含：

- `Top Playlists`
- `Switch Count`
- `Cycle Count`
- `Pause Time`
- `Dominant Buckets`

这些信息帮助用户快速形成画像，而不打断主图阅读。

### 7.4 Drilldown

`History` 必须支持 drilldown。

正式规则：

- 用户可点击某个 bucket，下钻到更细时间范围。
- 下钻后，主图仍然保持 composition 语义。
- 不要求始终下钻到 timeline；可以继续下钻为更细 bucket composition。

例如：

- `180d` -> 点击某周 -> `7d`
- `30d` -> 点击某日 -> `24h`

## 8. 视图规则

### 8.1 不再使用 segments

正式废弃：

- `segments` 作为主视图
- Gantt 风格 playlist timeline 作为默认信息架构

原因：

- 在长期范围上失去意义
- 会让页面主视图在不同时间范围之间切换过于剧烈

### 8.2 主图语义统一

无论是 `24h`、`7d` 还是 `180d`，主图都应尽量保持同一语义：

- 横轴：时间
- 纵向堆叠：playlist 占比

这样用户不用在不同 range 下重新学习图表语法。

### 8.3 事件只能作为辅助信息

历史事件并未完全失去价值，但其地位应降级。

正式要求：

- event 不是 `History` 的主视图
- notable events 只能作为辅助标记或 drilldown 信息
- event list 若保留，只能作为短时间范围下的次级面板

## 9. 数据契约

### 9.1 主接口

推荐主接口：

- `GET /api/history/composition?preset=7d`
- `GET /api/history/composition?from=<ISO>&to=<ISO>`

正式要求：

- 前端不直接传 `bucket_minutes`
- 后端返回实际采用的 granularity

### 9.2 HistoryBucket

建议结构：

```ts
type HistoryBucket = {
  bucketId: string
  start: string
  end: string
  playlistSeconds: Record<string, number>
  playlistRatio: Record<string, number>
  switchCount: number
  cycleCount: number
  pauseSeconds: number
}
```

说明：

- `playlistRatio` 是主图的主要数据来源。
- `playlistSeconds` 用于 tooltip 和统计。

### 9.3 HistoryCompositionResponse

建议结构：

```ts
type HistoryCompositionResponse = {
  range: {
    from: string
    to: string
    preset: "24h" | "7d" | "30d" | "90d" | "180d" | string | null
  }
  granularity: {
    bucketSeconds: number
    label: string
    bucketCount: number
  }
  seriesOrder: string[]
  buckets: HistoryBucket[]
  totals: {
    playlistSeconds: Record<string, number>
    playlistRatio: Record<string, number>
    switchCount: number
    cycleCount: number
    pauseSeconds: number
  }
}
```

说明：

- `seriesOrder` 用于前端稳定配色和堆叠顺序。
- `totals.playlistRatio` 用于概览卡和排行。

### 9.4 辅助事件接口

如果实现辅助事件视图，可使用单独接口：

- `GET /api/history/events?from=<ISO>&to=<ISO>`

正式要求：

- 事件接口不是 `History` 首页主数据接口。
- 事件接口只服务于短时段 drilldown 或辅助面板。

## 10. 前端状态模型

建议使用 Pinia 管理 `History` 页面状态。

建议 store：

```ts
type HistoryStore = {
  mode: "preset" | "custom"
  preset: "24h" | "7d" | "30d" | "90d" | "180d"
  customRange: {
    from: string | null
    to: string | null
  }
  response: HistoryCompositionResponse | null
  selectedBucketId: string | null
  loading: boolean
  error: string | null
}
```

说明：

- `selectedBucketId` 用于 drilldown 与高亮。
- `response` 承载统一的 composition 数据。

## 11. 与 Simulator 的边界

以下能力不应继续堆在 `History` 中：

- policy 数学细节
- scenario matrix
- old/new config compare
- solver
- parameter sweep
- sensitivity analysis
- heatmap 调优工具

这些能力应迁移到 `Simulator`。

可参考的现有脚本来源：

- [misc/sim_match.py](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/misc/sim_match.py)
- [misc/vis_common.py](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/misc/vis_common.py)

正式要求：

- `History` 不承担调参工具职责。
- `Simulator` 承担 what-if、策略验证、场景测试职责。

## 12. 实施顺序

建议按以下顺序实现：

1. 正式废弃 `segments` 作为 `History` 主模型。
2. 将现有聚合能力提升为主接口 `history/composition`。
3. 建立 preset-first + custom-range 的 range 交互。
4. 实现统一的 stacked area 主图。
5. 接入 totals 与 top playlists 辅助洞察。
6. 增加 bucket drilldown。
7. 如有必要，再补短时段辅助 event 面板。

## 13. 验收标准

实现完成后，`History` 页至少应满足以下条件：

1. 用户能在 `7d / 30d / 180d` 视图中直接看出 playlist 占比变化。
2. `History` 的主图不再依赖 `segments`。
3. 用户可使用 presets，并可使用高级自定义时间范围。
4. 用户无需理解 bucket 概念即可完成范围浏览。
5. `History` 主图在不同 range 下保持统一语义。
6. 用户可以从粗粒度视图 drilldown 到更细范围。
7. `History` 不再承担调优和策略验证主职责。
