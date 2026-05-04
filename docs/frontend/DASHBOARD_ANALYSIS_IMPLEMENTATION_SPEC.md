# Dashboard Analysis Implementation Spec

本文档收敛 `Dashboard Analysis v1` 的具体实现决策。  
[DASHBOARD_ANALYSIS_SPEC.md](./DASHBOARD_ANALYSIS_SPEC.md) 继续承担整体框架、目标和 DTO 契约定义；本文档只负责把当前已经达成共识的交互、状态模型和信息密度规则写死，避免实现阶段反复改方向。

## 0. 当前定位（2026-05-04）

当前代码事实：

- 后端已经提供 `GET /api/analysis/window?count=900`
- `dashboard-v2` 已经接入正式运行时
- 最小 dashboard shell、Pinia analysis store 与正式数据入口已经完成

当前文档目标：

- 收敛 `Dashboard Analysis v1` 的前端实现方案
- 明确哪些决定已经固定，哪些细节可以留给后续迭代

时间轴 ECharts / zrender 交互实现中的已知坑点与维护指引见：

- [DASHBOARD_TIMELINE_ECHARTS_GUIDE.md](./DASHBOARD_TIMELINE_ECHARTS_GUIDE.md)

## 1. v1 范围

`Dashboard Analysis v1` 的正式范围是：

- 顶部时间轴
- 下方 `Sense / Think / Act` 三栏
- `live / snapshot` 双态
- hover scrub / click lock / keyboard step

不在 v1 范围内的内容：

- 新的 detail-only API
- 时间轴上的 gate blocker 区段 overlay
- 显式 `resume marker`
- 手动刷新模式
- 长期历史分析语义

## 2. 时间轴视觉语法

时间轴采用“三层结构”，但应被视为一个整体工作区，而不是三张分离图表。

### 2.1 主图层

主图层承担时间趋势的主体表达。

- 上方主线使用 `similarity`
- 下方独立面积层使用 `similarity_gap`
- 不采用“双主折线”方案

原因：

- `similarity` 是用户最先要看的主信号
- `similarity_gap` 更适合表达“领先程度”而不是第二个并列主角

### 2.2 轨道层

轨道层用于表达 `activePlaylist` 与 `matchedPlaylist` 的时间关系。

- 上轨表达 `activePlaylist`
- 下轨表达 `matchedPlaylist`
- 两条轨道都按 tick 渲染色块
- `paused` 作为连续状态区间表达，使用中性灰或斜线语义

结论：

- 不单独发明 `diff overlay`
- 不把“推荐/实际分歧”再抽成第三条抽象语义带
- 两条轨道上下对齐后，差异会自然可见

### 2.3 事件语法

事件语法附着在轨道层，而不是再做独立大面积事件图层。

- `switch` 事件通过 playlist 色块边界表达
- `switch` 事件允许额外标注文案
- `cycle` 事件保留轻量 marker，但默认不打文案
- `paused` 通过状态区间表达，不单独绘制 `resume marker`

明确不做：

- `resume marker`
- blocker/gate 区段 overlay

原因：

- `resume` 在时间上自然体现在 paused 区间结束后恢复到普通 tick
- blocker 更适合作为当前选中 tick 的精确诊断事实，而不是时间轴主视觉

## 3. 交互与状态机

Dashboard 必须保持自动刷新；不采用“用户手动刷新后再看”的模式。

### 3.1 自动刷新原则

- 前端持续每秒拉取一次 analysis window
- 实时数据流在 `live` 与 `snapshot` 两种模式下都继续更新
- 停止跟随的是“当前视图选择”，不是“后台数据流”

### 3.2 正式状态

前端实现应围绕下面四种状态理解页面行为：

- `live-following`
- `hover-scrubbing`
- `snapshot-locked`
- `disconnected-with-stale-data`

其中：

- `live-following`
  - 时间轴和三栏都跟随 `liveTickId`
- `hover-scrubbing`
  - 未锁定时，hover 某个 tick 临时切换三栏
  - 鼠标离开后回到 live
- `snapshot-locked`
  - click 锁定后，三栏和键盘步进都只基于冻结窗口
- `disconnected-with-stale-data`
  - 后台刷新失败但已有成功窗口时，继续显示旧数据并提示断连

### 3.3 双窗口模型

为保证 snapshot 步进稳定，前端必须同时维护两份窗口：

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

规则：

- `liveWindow` 始终跟随后端最新窗口
- `snapshotWindow` 在 click lock 时由当前 `liveWindow` 冻结得到
- `snapshotWindow` 一旦创建即视为不可变，不在锁定期间被后台刷新覆盖
- keyboard step 只在 `snapshotWindow` 内移动
- `Back to Live` 时丢弃 `snapshotWindow`

### 3.4 不可变约束

`TickSnapshot` 与窗口数组在前端视为不可变数据。

实现约束：

- 不对单个 tick 对象做原地修改
- 冻结 snapshot 时直接复制窗口数组引用顺序即可
- 任何新的后台结果都以整包替换 `liveWindow`

## 4. 下方三栏的信息密度

整体原则：

- 不允许把“为什么切了 / 为什么没切”的核心结论藏进多层折叠
- 允许对高密度支持证据做局部展开
- 不做“整栏摘要卡 + 再点进去看真相”的设计

### 4.1 Sense

`Sense` 整栏默认直接展示，不做整栏折叠。

默认可见内容：

- window title
- process
- idle seconds
- cpu average
- fullscreen
- weather 状态与主要字段
- local time / hour / day-of-year

结论：

- `Sense` 以紧凑信息卡直接展开
- 不做“摘要 + 展开”模式

### 4.2 Think

`Think` 是信息密度最高的一栏，应采用“整体全量、局部折叠”的结构。

#### Context Vectors

- `rawContextVector` 默认显示前 `N` 个高权重 tag
- `resolvedContextVector` 默认显示前 `N` 个高权重 tag
- 剩余项通过 `+N more` 或展开详情查看

#### Fallback Expansions

- 仅在非空时显示
- 默认显示摘要
- 展开后查看完整 fallback 链

#### Policy Diagnostics

- 所有 policy 卡片头默认可见
- 不使用 `active = true` 作为默认展开规则
- 默认展开 `effectiveMagnitude` 最大的前 `1 ~ 2` 个 policy
- 其余 policy 默认折叠，但卡片头仍保留摘要

policy 卡片头应默认显示：

- policy 名称
- enabled / active
- dominantTag
- effectiveMagnitude
- 一句摘要

policy 卡片体展开后再显示：

- direction
- rawContribution
- resolvedContribution
- typed details

### 4.3 Act

`Act` 默认遵循“结论优先、相关证据直出、底层字段折叠”的原则。

#### Top Matches

- 默认显示前 `5` 个候选
- 不折叠

#### Controller Evaluation

默认层只展示与当前结论直接相关的信息：

- operation
- allowed / blocked
- blockedBy
- 一句解释文案
- 与当前 blocker 直接相关的数值

示例：

- cooldown blocker 时显示 `cooldownRemaining`
- idle blocker 时显示 `idleSeconds / idleThreshold`
- cpu blocker 时显示 `cpuPercent / cpuThreshold`
- fullscreen blocker 时显示 `fullscreen = true`
- `forceAfterRemaining` 只在当前 tick 的解释中确有价值时显示

完整字段进入详情区，不在默认层全部平铺。

#### Action Decision

默认层不直接裸露 `activePlaylistBefore / activePlaylistAfter`。

默认层应压缩为结论语句，例如：

- `Switched: A -> B`
- `Stayed on: A`
- `Paused`
- `Cycled within: A`

默认层同时显示：

- `reasonCode`
- `executed`
- `matchedPlaylist`

原始 before / after 字段进入详情区。

## 5. 对后端 API 的约束

当前 `GET /api/analysis/window` 已足够支撑 `Dashboard Analysis v1`。

因此 v1 结论是：

- 不新增 detail-only API
- 不要求额外的 `resume` 事件 DTO
- 不要求后端提供 blocker timeline segments

若后续需要增强时间轴语义，优先评估：

- 是否为 `cycle` 提供更明确的 timeline 表达
- 是否为更高精度的 blocker 统计提供专用聚合层

但这些都不阻塞 v1。

## 6. v1 验收补充

除主 spec 验收项外，`Dashboard Analysis v1` 还应满足以下实现性要求：

1. `live` 模式下，时间轴与三栏持续自动跟随最新 tick。
2. `snapshot` 模式下，后台继续拉新，但当前分析对象不被打断。
3. keyboard step 基于冻结的 `snapshotWindow`，不会因实时刷新导致左右邻居漂移。
4. paused 区间以连续状态区间表达，而不是独立 `resume marker`。
5. blocker 原因在 `Act` 栏被精确解释，而不是在时间轴做粗粒度 overlay。
6. `Think` 栏所有 policy 默认可见卡片头，且默认展开主导的前 `1 ~ 2` 个 policy。
