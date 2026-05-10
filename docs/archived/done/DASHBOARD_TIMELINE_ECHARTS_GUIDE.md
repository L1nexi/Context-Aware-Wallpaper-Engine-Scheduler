# Dashboard Timeline ECharts Guide

本文档记录 `dashboard-v2` Dashboard 时间轴实现中已经踩过的 ECharts 交互坑，并给出后续维护指引。

适用范围：

- `dashboard-v2/src/features/dashboard-analysis/DashboardTimeline.vue`
- `dashboard-v2/src/features/dashboard-analysis/timeline.ts`
- ECharts `line` / `custom` series 与 zrender 鼠标事件协作

## 1. 当前推荐架构

Dashboard 时间轴不是普通 ECharts tooltip 图表，而是一个 scrub 工作区。

推荐分层如下：

- ECharts 负责静态图层渲染：
  - `similarity` 折线
  - `similarity_gap` 面积线
  - switch / cycle marker
  - active / matched track custom rect
- zrender 全画布事件负责交互：
  - `mousemove` 统一换算 tick index
  - `click` 统一进入 snapshot lock
  - `globalout` 清理 hover
- Vue 组件负责 scrub UI：
  - 当前 hover guide line
  - hover tooltip overlay
  - 键盘焦点与 step
- Pinia store 负责状态语义：
  - live-following
  - hover-scrubbing
  - snapshot-locked

不要把 scrub 行为拆回每个 ECharts series 自己的 hover/click。那会让同一个鼠标动作同时触发 ECharts 内部 emphasis、tooltip、axisPointer 和 Vue 状态更新，后续很难稳定。

### 生命周期边界

核心判断标准：

- ECharts 是渲染引擎，不是 Dashboard 时间轴的交互状态机。
- Vue / Pinia 是交互状态与 overlay 生命周期的唯一来源。

原因是 Vue 和 ECharts 本质上有两套生命周期。Vue 的响应式更新会重算 props、template 和 Pinia 派生状态；ECharts 的 `setOption`、tooltip、axisPointer、emphasis 和 zrender display list 也会在自己的渲染循环里更新。如果两边同时管理同一个 hover/click 语义，就会出现竞态：

- Vue 刚根据 hover 更新 selected tick，ECharts tooltip 又被 option update 隐藏。
- ECharts emphasis 刚命中某个 series element，Vue 又触发重绘，display style 被重算。
- ECharts 内部 hover 状态和 Vue overlay 状态同时存在，视觉反馈无法稳定归因。

因此当前时间轴的工程原则是：

- ECharts 只接收确定的 option，用于画稳定底图。
- ECharts action 只作为低层辅助或调试工具，不作为正式 scrub UI 的状态来源。
- ECharts series 尽量 `silent` / disable emphasis，避免内部交互状态介入。
- zrender 只提供原始鼠标坐标事件。
- tick 选择、snapshot lock、tooltip、guide line、point marker、keyboard focus 都由 Vue / Pinia 绑定。

如果未来要新增一种交互，优先问一句：这个状态是否会跨 tick、跨刷新、跨页面区域影响 Dashboard 解释语义？如果会，它应该进 Vue / Pinia；ECharts 只提供坐标转换或底层绘制。

## 2. 坑点一：多 grid 下的坐标换算不能只传 `xAxisIndex`

### 症状

hover 或 click 有时没有效果，或者 tick index 一直落不到预期位置。

### 根因

时间轴现在是多 grid / 多 axis 结构。直接调用：

```ts
chart.convertFromPixel({ xAxisIndex: 0 }, [x, y])
```

在当前 ECharts 版本里可能返回 `null` / `NaN`。只给 `xAxisIndex` 不足以稳定 disambiguate 当前坐标系。

### 指引

先用 `containPixel` 判断鼠标处于哪个 grid，再用完整 axis finder 做转换：

```ts
const finder = chart.containPixel({ gridIndex: 0 }, [x, y])
  ? { xAxisIndex: 0, yAxisIndex: 0 }
  : chart.containPixel({ gridIndex: 1 }, [x, y])
    ? { xAxisIndex: 1, yAxisIndex: 2 }
    : null

const result = finder ? chart.convertFromPixel(finder, [x, y]) : null
```

后续如果调整 grid / axis 数量，必须同步检查：

- `grid`
- `xAxis`
- `yAxis`
- `axisPointer.link`
- `resolveTimelineIndexFromPixel`
- 每个 series 的 `xAxisIndex` / `yAxisIndex`

## 3. 坑点二：折线 hover 后消失

### 症状

正常渲染时折线和面积都在；鼠标移上图表后，主线或面积层突然消失。

### 根因

ECharts emphasis 状态会重算 display element 的 style。当前主题 token 使用 OKLCH 色值，在 emphasis 切换时可能导致 line / area display element 的 `stroke` / `fill` 变成缺失值。

### 指引

Dashboard 时间轴不依赖 ECharts series 自带 emphasis 表达 hover，因此 line series 应显式关闭 emphasis：

```ts
{
  type: 'line',
  emphasis: {
    disabled: true,
  },
}
```

hover 反馈由 Vue overlay 和 selected tick 状态表达，不由 ECharts line emphasis 表达。

## 4. 坑点三：Active / Matched 轨道 hover 后闪烁或柱子消失

### 症状

鼠标移到 track rect 上时，某些色块闪烁或消失；移到轨道空白处又不复现。

### 根因

轨道是 ECharts `custom` series 返回的 `rect`。鼠标命中 rect 时，ECharts 会让该 graphic element 进入 `emphasis`。实测进入 emphasis 后，display list 里的 rect 仍存在，但 `style.fill` 可能变成 `undefined`，所以视觉上像柱子消失。

### 指引

track rect 本身不应该参与 ECharts 命中交互。scrub 已经由 zrender 全画布事件统一处理，因此两条 track custom series 必须保持：

```ts
{
  type: 'custom',
  silent: true,
}
```

不要给 custom series 加 `emphasis.disabled` 作为替代。当前 ECharts TypeScript 类型对 custom series 的 `emphasis` 不支持 `disabled`，会破坏 `vue-tsc`。

如果未来必须让 custom rect 自己响应 hover，应改为显式管理 `renderItem` 返回的 `style` / `emphasis` style，并用 Playwright 检查 display list 中 rect 的 `fill` 是否在 hover 后仍存在。

## 5. 坑点四：ECharts tooltip 和 Vue scrub 状态会互相打断

### 症状

手动 `dispatchAction({ type: 'showTip' })` 有时能显示，有时被下一次 Vue 状态更新或 chart option 更新隐藏。

### 根因

hover scrub 会更新 Pinia store，进而触发 Vue re-render 和 ECharts option 更新。ECharts 内部 tooltip 生命周期与这个刷新节奏耦合后，会出现 race condition。

### 指引

Dashboard 时间轴 hover tooltip 使用 Vue overlay，不使用 ECharts tooltip 作为最终交互 UI。

推荐做法：

- ECharts tooltip 可保留为禁用触发或调试辅助，但不要作为 scrub UI 的唯一来源。
- hover 时只记录 `{ index, x, y }`。
- tooltip 文案从 `props.ticks[index]` 读取。
- guide line 和 tooltip 用 `position: absolute` 覆盖在 chart 容器上。

这样 tooltip 生命周期由 Vue 控制，不受 ECharts 内部 tooltip hide/show 影响。

## 6. 坑点五：hover 不应冻结或替换图表窗口

### 症状

hover 期间图表数据突然变短、跳动，或者 click 锁定的窗口与用户看到的窗口不一致。

### 根因

hover-scrubbing 是临时选择，不是 snapshot lock。若 hover 时复制一份 `hoverWindow` 并让图表数据源切过去，会让实时刷新、图表 option 和当前 hover 状态互相干扰。

### 指引

状态边界如下：

- `liveWindow` 始终跟随后端最新窗口。
- hover 只改变 `hoverTickId` / 当前分析对象，不替换图表窗口。
- live refresh 时，如果 `hoverTickId !== null`，不要覆盖 `selectedTickId`。
- click lock 时才创建 `snapshotWindow = liveWindow.slice()`。
- snapshot mode 下 keyboard step 只在 `snapshotWindow` 内移动。

## 7. 坑点六：关闭 ECharts emphasis 后 hover 点位也会消失

### 症状

hover scrub 时 guide line 和 tooltip 都正常，selected tick 也会切换，但主图上不再突出显示当前 x 轴对应的 similarity / gap 点。

### 根因

折线消失问题的修复要求 line series 关闭 ECharts 自带 emphasis。这样做是正确的，但副作用是 ECharts 也不会再帮我们画 hover symbol / point marker。

不要为了恢复点位高亮重新打开 line emphasis。那会把“hover 后 line / area 的 `stroke` / `fill` 丢失”问题带回来。

### 指引

hover point marker 也应属于 Vue scrub overlay，而不是 ECharts series emphasis。

做法：

- hover 时保存 `{ index, x, y }`。
- 用 `chart.convertToPixel({ xAxisIndex: 0, yAxisIndex }, [index, value])` 把曲线数据点转换成 chart 容器内像素坐标。
- similarity 使用 `yAxisIndex: 0`。
- gap 使用 `yAxisIndex: 1`。
- 用绝对定位 overlay 画 marker，样式要足够强，不要只画一个很小的同色圆点。

示例：

```ts
const point = chart.convertToPixel(
  { xAxisIndex: 0, yAxisIndex: 0 },
  [hoverIndex, tick.summary.similarity],
)
```

marker 视觉建议：

- similarity marker 至少 `16px`
- gap marker 至少 `14px`
- 使用线条同色外圈 + 浅色内圈，避免被线条或面积层吞掉
- marker `z-index` 应高于 tooltip guide line

验证时不要只检查 DOM 存在。必须检查：

- marker 的 `getBoundingClientRect()` 有实际尺寸
- `backgroundColor` / `borderColor` / `boxShadow` 已解析
- marker 坐标落在 chart 主图区域内

## 8. 验证清单

每次改时间轴图表或交互后，至少验证这些点：

1. `npm run type-check`
2. `npm run build-only`
3. 浏览器 hover 主图层：
   - similarity line 仍有 `stroke`
   - gap area / line 仍可见
   - similarity hover marker 可见
   - gap hover marker 可见
   - selected tick 切换到 hover tick
4. 浏览器 hover Active / Matched 轨道：
   - track rect 不进入 `emphasis`
   - rect `style.fill` 不丢
   - selected tick 和 Vue tooltip 正常更新
5. click 图表：
   - 进入 snapshot mode
   - `Back to Live` 出现
   - 时间轴容器获得焦点
6. snapshot mode 下按方向键：
   - 左右 step 基于冻结窗口
   - 后台 live 更新不改变当前 snapshot 选择

Playwright 调试时可以读取 ECharts display list：

```ts
const chart = document.querySelector('x-vue-echarts')
  ?.__vueParentComponent
  ?.exposed
  ?.chart
  ?.value

const rects = chart
  .getZr()
  .storage
  .getDisplayList()
  .filter((item) => item.type === 'rect')
  .map((item) => ({
    fill: item.style?.fill,
    currentStates: item.currentStates,
    invisible: item.invisible,
    ignore: item.ignore,
  }))
```

关键断言：

```ts
rects.filter((rect) => rect.currentStates?.includes('emphasis')).length === 0
rects.filter((rect) => !rect.fill).length === 0
```

## 9. 后续维护原则

- 时间轴是一个整体 scrub workspace，不是多张独立交互图。
- 所有鼠标位置到 tick 的映射必须集中在 `resolveTimelineIndexFromPixel`。
- ECharts series 本身尽量保持静态、沉默、可重绘。
- hover/click/keyboard 语义优先落在 Vue + Pinia，而不是 ECharts action。
- 调整 grid / axis 时，先改坐标换算和验证脚本，再调视觉参数。
- 遇到“元素消失但数据还在”的问题，优先检查 display list 的 `style` 和 `currentStates`，不要先猜数据源丢失。
