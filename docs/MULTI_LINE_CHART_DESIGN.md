# Multi-Line Chart 设计文档

## 概述

多折线图是诊断页 Match 可视化的主视图，替代已废弃的堆叠面积图和热力图。展示 10 个播单的分数随时间变化的趋势，帮助用户理解系统过去一段时间的运行情况。

## 目标

- 展示多个播单分数在时间中的变化（PRODUCT 设计原则 #4）
- 展示运行事实，不替用户判定 Winner（PRODUCT 设计原则 #1）
- 支持后续与 Decide、Policy 信息整合

## 非目标

- Winner 排行榜（PRODUCT Anti-reference）
- 运维大屏
- 实时数据（当前阶段使用静态 buckets.json）

## 数据源

复用 `useBuckets` composable，使用 `applyPowerTransform` 做幂变换，不做归一化。Y 轴展示绝对分数值。

## 图表规格

### 库

Unovis（`@unovis/vue` v1.6.5），已有依赖，复用现有 `ChartContainer` 包装器。

### 曲线

- 类型：默认 `natural`，提供 `monotoneX` 切换
- `natural` 视觉流畅，`monotoneX` 保证不超出数据范围
- 使用 ToggleGroup 切换

### 线条层次

10 条线分两层：

| 层级 | 数量 | 颜色 | 线宽 | 透明度 |
|------|------|------|------|--------|
| Top 4 | 4 | 播单原色（`playlists[].color`） | 2px | 1.0 |
| 幽灵线 | 6 | 纯灰（`#888`） | 1px | 可调（滑条，默认 0.2） |

### Top 4 选取逻辑

每个视口（viewport）内，取**末尾值**（最后一个 bucket 的分数）最高的 4 个播单作为 Top 4。窗口滑动时 Top 4 身份自然跟随变化。

- N = `_MAX_CLUSTER_SIZE + 1 = 4`
- 选取基于 `applyPowerTransform` 后的分数，不做归一化

### Y 轴

- 域：`[0, max_score_in_viewport]`（自适应），或固定 `[0, 1]`
- 分数为 cosine similarity，实际范围约 0.1 - 0.7

### X 轴

- 时间轴，使用 `formatAxisTick` 格式化（显示为 elapsed time）
- tick 数量自适应视口大小

## 交互

### Hover

1. 竖线（Crosshair）出现在鼠标最近的有效 x 值位置
2. 竖线与每条线的交点显示小圆圈（circleRadius: 4）
3. 鼠标所在的那条线高亮（线宽增加、其余线淡化）
4. Tooltip 显示当前 hover 到的播单名 + 分数

技术实现：
- `VisCrosshair` 提供竖线 + 交点圆圈
- `Line.selectors.line` 的 `mouseover`/`mouseleave` 事件控制高亮状态
- `VisTooltip` 配合 `Line.selectors.line` trigger 显示单条线信息

### Click-to-Lock

1. Click 某条线 → 锁定选中该播单，高亮状态保持
2. 移动鼠标时，Tooltip 跟随显示该播单在不同 tick 的分数
3. 再次 click 同一条线或点击空白区域 → 取消锁定，回到 hover 模式

状态管理：组件内维护 `selectedLineIndex: ref<number | null>(-1)`。

### Legend

- 点击图例项 → 切换该播单的显示/隐藏
- 图例按分数末尾值排序，Top 4 在前
- Top 4 图例项带原色标识，幽灵线图例项带灰色标识

## 控件

复用现有控件模式（StackedAreaChart.vue）：

| 控件 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| 曲线类型 | ToggleGroup | natural | natural / monotoneX |
| 视窗大小 | ToggleGroup | 30 | 15 / 30 / 60 / 120 / 240 |
| 聚合大小 | ToggleGroup | 1 | 1 / 2 / 3 / 4 / 5 / 8 |
| 幂指数 p | Slider | 1.0 | 0-5, step 0.1 |
| 视窗位置 | Slider | 0 | 0 - maxStart |
| 幽灵线透明度 | Slider | 0.2 | 0-1, step 0.05 |

## 组件结构

```
frontend/src/features/diagnostic/
  MultiLineChart.vue       # 新组件
  StackedAreaChart.vue     # 保留但标记废弃
  MatchHeatmap.vue         # 保留但标记废弃
```

`MultiLineChart.vue` 内部结构：
- `<script setup>`: 调用 `useBuckets()`，计算 Top 4、displayBuckets、颜色/线宽数组
- `<template>`: ChartContainer > VisXYContainer > VisLine + VisAxis + VisCrosshair + VisTooltip
- 控件区域：ToggleGroup + Slider 组合

## 数据流

```
useBuckets()
  → viewport (AggBucket[])
  → applyPowerTransform(bucket.scores, p)
  → displayBuckets: { index, transformedScores }[]
  → computeTop4(displayBuckets) → top4Keys: Set<string>
  → yAccessors: 每个 playlist 一个 accessor
  → colorAccessor: (d, i) => top4Keys.has(key) ? playlist.color : '#888'
  → widthAccessor: (d, i) => top4Keys.has(key) ? 2 : 1
  → opacityAccessor: (d, i) => top4Keys.has(key) ? 1.0 : ghostOpacity
```

## 待定事项

- Y 轴域：自适应 vs 固定 `[0, 1]`（实现时根据视觉效果决定）
- 交点圆圈是否只在 hover 时显示，还是始终显示
- 响应式布局（移动端图例位置）
