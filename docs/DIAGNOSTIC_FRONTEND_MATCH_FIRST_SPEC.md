# 新前端诊断页 Match-first 规格

## Goal

诊断页应以 Playlist Score 的时间变化为绝对重点，帮助用户快速理解最近一段时间多个候选播单的得分结构、实际 Active Playlists 轨迹、调度事件和少量关键 Policy 事实。

用户打开诊断页，不是为了重新判断当前场景的 Winner，也不是为了查看 Policy Controller 的内部细节，而是为了观察系统最近一段时间“看见了什么”和“实际调度到了哪里”。

GPT5.5：本文档中的普通段落按用户想法记录；凡是由我补充的推导、实现建议、风险提示或命名建议，均以 `GPT5.5：` 开头。

## Non-goals

- 不做 Winner 排行榜。
- 不把 similarity / similarity gap 当作核心展示对象。
- 不满屏展示 Raw Tags、Resolved Tags 和内部细节。
- 不恢复旧 dashboard / workbench 心智。
- 不把诊断页扩展成配置编辑器、历史分析产品或调参工具。
- 不引入顶部一句话运行叙事作为核心功能。
- 不把选中 tick 编号、内部索引、Policy Controller 细节展示给用户。

GPT5.5：这些非目标用于保护主图注意力。新前端应让用户先看见时间中的分数结构和实际调度轨迹，而不是被解释卡片分散。

## Current Facts

目前后端每 1 秒更新 tick store，store buffer 大小为 1200，API 默认请求大小为 900。因此按 1 秒一个 tick，目前历史可追溯时长约为 15 分钟。

直接使用 900 个 x 轴点会让渲染和图表阅读都不好看。后续应该通过调整聚合粒度和 x 轴点数量来控制总追溯时长。

追溯时长作为内部心智项，候选包括 1h、2h、3h、6h、12h。当前倾向 1h 或 2h。

暂时不做自适应。先从横向尺寸反推固定 x 轴点数量。120 个横向点是当前原型验证值。

当前讨论已经从“堆叠柱状图 + Top5 + 其余固定底座”推进为“堆叠面积图 + 全量播单固定身份 + Top5 阈值强调 + 非 Top5 压缩显示”。旧的“其余”灰色底座方案不再作为主路线。

GPT5.5：若目标窗口是 2h，则 120 点约等于每点 60 秒；若目标窗口是 1h，则 120 点约等于每点 30 秒。120 点在桌面宽度下能兼顾密度、节奏和 hover 命中。

## Design

页面主结构按优先级排列：

1. Playlist Score 堆叠面积图
2. Active Playlists / Decide Timeline
3. Policy 信息，位于更下方，或在点击某个时间点时展示

状态栏保持极简。它不展示 tick 编号或 selected tick 这类工程细节。用户只关心现实时间感，例如 `hh:mm:ss`，或跨天时 `dd hh:mm`。

GPT5.5：状态栏可保留实时状态、窗口范围和当前指向时间，但不要出现 `tickId`、内部索引、similarity 等工程坐标。

### Match 主图

Playlist Score 堆叠面积图是主图，占据页面绝大部分空间。

主图使用 Unovis Area。默认 `curveType="basis"`，默认面积不透明度暂定 `0.5`，边界线宽 `1px`。悬停时面积不透明度暂定 `0.8`，边界线宽提升到 `2px`。

主图不展示 y 轴。用户需要理解的是分数结构和时间变化，不是读取绝对坐标值。若需要数值，hover 某个 area 时展示该时间桶内对应播单的 score 和排名即可。

Area 的层不代表 `Top1`、`Top2`、`Top3`、`Top4`、`Top5`，而代表具体播单身份。每个播单拥有固定颜色和固定 series。

所有播单按固定顺序展示。当前倾向使用配置顺序。正确做了非 Top5 压缩后，顺序影响会比较小。

每个聚合时间桶内计算播单排名。排名进入 Top5 的播单按正常面积展示；Top5 之外的播单仍保留自己的 series，但分数显示被截断或按比例减小，并降低不透明度，使它们成为细微背景信息。

Top5 阈值暂定为 5。Top5 之外的可视高度应很小，当前想法是按主图高度的 2% 到 3% 量级控制。具体压缩函数和边界值需要通过原型确认。

当某个播单从 Top5 外进入 Top5，它不是突然出现的新颜色，而是从较细、较暗的面积自然变厚、变亮。反之亦然。

不引入额外的显著性权重、滞后或防抖机制。后续已经准备按多 tick 聚合，如果聚合后的桶仍然抖动，那说明用户这一段时间的活动本身就是抖动的，应如实展示。

不原原本本展示全部播单的真实高度。用户配置的播单数量不定，如果数量过多，长尾播单会挤压真正重要的 Top5。

不在界面上解释“Raw”“展示值”“emphasis”这类实现细节。用户关心的是当前分数和变化，不关心内部显示算法的命名。

GPT5.5：图例和 hover 信息应服务“播单身份识别”。如果支持点击锁定播单层，点击应锁定 playlist focus；时间桶选择应由 crosshair 或当前横向位置负责，而不是让 area click 独自承担两种语义。

### Decide Timeline

Decide 不应作为复杂解释面板，而应作为主图下方的 Timeline，展示每个时间段的 Active Playlists 和调度事件。

当前主方案采用 Timeline 的播单池槽位 lane，而不是每个播单一条 lane。

Timeline 固定或按需扩展 `pool-1`、`pool-2`、`pool-3` 等槽位 lane。row 不代表具体播单，只代表播单池槽位；segment 颜色代表播单身份。

Active Pool 有几个播单，就同时点亮几个 lane。当前播单池最大 3 个，因此固定 3 lane 是自然起点；如果后续播单池允许量变化，可以自适应增加 lane。

Timeline 支持同一 row 内不同 segment 使用不同颜色。实现上可使用 `lineRow` 表示槽位，用 `color` 表示播单颜色。

播单池槽位分配不能每个桶单纯按配置顺序重排。应使用延续优先的空位分配器：上一个时间段已经在 lane 内的播单，如果仍在当前 active pool，则保持原 lane；新增播单放入空 lane；不再 active 的播单释放 lane。

例如从 `[D]` 变成 `[B, D]` 时，`D` 应保留原 lane，`B` 进入空 lane，避免视觉上把连续 active 的 `D` 换轨。

SWITCH 不再作为特殊 lane、特殊 overlay 或特殊 item 处理。采用 Timeline 后，SWITCH 自然表现为 active pool segment 的变化。若某个桶内发生 SWITCH，可以按实现便利性归入先前 active 或之后 active，并在聚合语义中明确。

CYCLE 必然发生在连续 Active 内部。处理方式是切分 segment，并在 CYCLE 后的 segment 使用 `lineStartIcon`。这样 CYCLE 作为一个 segment 起点事件出现。

blocker 不改变主视觉，只在 hover 时展示。hover 对应 segment 时展示 blocker 类型和时长，例如冷却、全屏、CPU、空闲分别持续了多久。

Decide Timeline 不再继承旧原型的 52px 高度。Timeline 会自然要求更大的空间，高度按 lane 数量、rowHeight 和是否显示标签决定。

GPT5.5：备选方案 A 是每个播单一条 lane。它更适合查看单个播单生命周期，但高度会随播单数量增长，可能让 Decide 抢走主图注意力。当前记录为备选，不作为主方案。

GPT5.5：延续优先空位分配器建议实现为纯函数，例如 `assignPoolLanes`，输入按时间排序的聚合桶，输出 Timeline segments。它应有独立测试，因为这直接决定 Timeline 是否稳定可读。

### Policy

Policy 应放在更下方，或者在用户点击某一个时间点时展示。它不应抢占主图空间。

字段必须非常克制。首选 Activity，次选 Weather，最后 Season/Time。

Policy 展示重点不是内部工程细节，而是用户真正关心的事实。

如果确实要输出 Policy tag，更建议用四个紧凑的小型柱状图展示，而不是纯文字列表。

GPT5.5：四个小型柱状图可以分别对应 Activity、Weather、Time、Season，作为选中时间点的上下文向量缩略图。它们不应成为页面主叙事。

Activity 关心当前活动向量、具体的匹配情况和时间。用户希望知道某个规则是否正确匹配，以及哪些进程和标题触发了规则。还应能看到规则的累计停留时间。

Weather 关心的是“具体是什么天气”，而不是 `id`、`main`、数据是否新鲜这类内部细节。天气展示应能表达大中小雨、大中小雪、云的程度等具体级别。

Season 和 Time 只关心最显著的点。它们可以淡化，甚至默认不展示，因为用户通常容易直接注意到时间和季节。当 salience 达到某个阈值时，可以加一句文案。例如“黎明将至，东方既白”“夏夜、萤火虫、花火与你”。这些只是设想，重点在于体现显著性，而不是输出工程字段。

GPT5.5：当前数据模型里有 weather id 和 main，足以映射出更细的天气文案。这个映射可以在后端聚合层或前端展示层完成，但展示层不应暴露原始 id。

GPT5.5：数值展示更适合用均值，显著性文案更适合看最大值或峰值，避免短暂但强烈的黎明、黄昏、季节信号被平均掉。

### Warmup

启动后 store 需要收集一定数据才能填满图表。当前选择诚实展示缺失历史，不做持久化历史，不做横向拉伸占满。

总时间窗口和横轴比例保持固定。缺少的数据区域留空，已有数据按真实时间位置渲染。

右侧表示现在，左侧表示过去。warmup 期间数据从右侧开始填充，左侧为空白历史区。

不采用“保持图占满屏幕”的方案。该方案会让横轴比例持续变化，Area 坡度和 Timeline segment 长度也会随数据增加不断重映射，视觉变化不好看，也不利于用户建立时间直觉。

暂不考虑 store 持久化。以后如果做持久化，应单独处理进程断点和交接点，不把离线期间伪装成连续运行。

GPT5.5：warmup 区域可以使用很轻的空白或 muted 背景表达缺历史，不需要大段说明。状态栏可显示“已收集 18 分钟”这类现实时间信息。

## File Map

- `frontend/src/App.vue`：当前粗糙原型入口；后续继续用于验证 120 点、Score Area 和 Decide Timeline 方向。
- `frontend/src/components/ui/chart/`：由 shadcn-vue 生成的 Chart 组件源码。
- `frontend/package.json` / `frontend/package-lock.json`：引入 shadcn-vue Chart 所需的 `@unovis/ts` 和 `@unovis/vue`。
- 后续真实实现位置待定，应优先落到 `frontend/src/features/diagnostic/` 下，而不是长期堆在 `App.vue`。

GPT5.5：当前 `App.vue` 原型不是最终文件边界。进入正式实现时，建议拆出 score area、decide timeline、policy detail 和 mock/adapter 数据模块。

## Contracts

### 聚合桶

后端聚合需要服务图表语义，而不是只压缩数组长度。

Match 聚合：每个桶内，对各播单 score 按调度器 tick 取均值。前端需要拿到所有播单的桶内 score，以便按固定身份 series 展示并在每个桶内计算 Top5 阈值。

Decide 聚合：每个桶应提供 active pool、是否包含 CYCLE、blocker 类型到时长。若桶内出现 SWITCH，可以按实现便利性归入先前 active 或之后 active，但聚合规则必须稳定。

Policy 聚合：Weather 按众数聚合，取时长最长的天气。Activity 对方向和模长取均值，窗口和进程可展示 TopN 时长。Time/Season 按平均数或最大值聚合，具体取决于用途。

GPT5.5：建议后端聚合桶的数据契约至少包括 `scores`、`activePool`、`hasCycle`、`blockers`、`weather`、`activity`、`timeSeason`。如果仍保留 `hasSwitch`，它可用于 hover 说明或调试验证，但不再要求主视觉单独编码 SWITCH。

### 显示规则

- x 轴点数：当前固定 120。
- warmup：固定窗口，缺历史留空，数据右侧对齐现在。
- Match 主图：Unovis Area 堆叠面积图。
- Area 曲线：`basis`。
- Area 默认不透明度：`0.5`。
- Area 悬停不透明度：`0.8`。
- Area 默认线宽：`1px`。
- Area 悬停线宽：`2px`。
- y 轴：不展示。
- 播单 series：按固定配置顺序，全量展示。
- Top5：每个桶内动态计算，正常显示。
- 非 Top5：保留身份，但压缩为细微低透明度面积。
- Decide：Unovis Timeline。
- Decide lane：主方案为播单池槽位 lane，固定或按需扩展。
- lane 分配：延续优先空位分配。
- SWITCH：表现为 Timeline segment 变化，不单独编码。
- CYCLE：切分 segment，CYCLE 后 segment 使用 `lineStartIcon`。
- blocker：hover 时展示类型和时长。

## Tasks

1. 将当前 Score 原型从柱状思路更新为 Area 主图，应用 `basis`、默认不透明度、hover 不透明度和边界线规则。
2. 移除 Match 主图 y 轴。
3. 将 Score 数据 mock 从 Top5 + 其余底座改为全量播单固定身份 + 非 Top5 压缩。
4. 原型验证 Top5 阈值为 5 时，非 Top5 压缩到 2% 到 3% 量级是否足够可读。
5. 用 Timeline 重做 Decide 原型，采用播单池槽位 lane。
6. 实现延续优先空位分配器，验证 `[D] -> [B, D]` 等场景不换轨。
7. 在 Timeline 中验证 CYCLE 后 segment 的 `lineStartIcon` 表达。
8. 验证 blocker hover 信息是否足够，不加入额外主视觉编码。
9. 实现 warmup 空白历史区，验证固定窗口下数据从右侧填充的视觉效果。
10. 将原型从 `App.vue` 移入诊断功能模块，并拆出可维护组件。
11. 加入 Policy 详情区域，只展示 Activity、Weather、Season/Time 的克制信息。

GPT5.5：这份规格本身足以指导下一轮 UI 原型和聚合接口设计；只有到正式接后端聚合时，才需要单独写实现计划。

## Validation

- 前端结构变更后运行 `npm run build`。
- 图表原型必须手工检查 120 个点是否过密、Area Top5 是否一目了然、非 Top5 压缩是否不会抢焦点、Decide Timeline 是否能清楚表达播单池。
- Timeline 必须手工检查播单池变化、CYCLE 起点图标、blocker hover 和 lane 延续。
- warmup 必须手工检查固定窗口、右侧对齐现在、左侧缺历史留空是否符合直觉。
- 后端聚合接入后，需要用真实 tick 数据验证 Active Pool、CYCLE、blocker 时长和 Policy 聚合语义。

GPT5.5：当前阶段的关键验证不是单元测试，而是视觉密度和语义可信度。自动化检查只能证明构建成功，不能证明这个诊断图“读起来对”。

## Risks

- 非 Top5 压缩会让面积高度不再等于真实总分堆叠。界面不应用 y 轴或工程文案诱导用户读绝对高度。
- 播单数量过多时，即使压缩也可能带来颜色噪声，需要通过真实配置验证。
- Timeline 槽位 lane 如果没有延续优先分配，会让连续 active 的播单看起来换轨。
- SWITCH 归前段或归后段必须稳定，否则 Timeline 交接点会显得不可信。
- Policy 一旦展示过多字段，会把页面拉回旧 dashboard / workbench 心智。
- 如果后端不提供聚合桶，前端直接处理大量 tick 会让图表、hover 和语义判断都复杂化。
- Season/Time 文案如果过度发挥，会从显著性提示变成装饰文案。

GPT5.5：最大产品风险是主图被解释层重新稀释。后续所有新增模块都应先问：它是否帮助理解 Match 时间变化和实际调度轨迹？

## Open Questions

- 总追溯时长最终选 1h 还是 2h？
- 非 Top5 压缩函数如何确定？按固定小值截断，还是按比例压缩？
- 非 Top5 可视高度的 2% 到 3% 是按单个播单控制，还是按长尾整体预算控制？
- Timeline lane 是否始终固定为 3，还是读取播单池允许量自适应？
- SWITCH 桶归入先前 active 还是之后 active？
- Policy 详情放在主图下方常驻，还是只在点击时间点时出现？
- Season/Time 显著性文案的阈值和文案风格如何收敛？

GPT5.5：这些是下一轮原型和接口设计的真实开放问题，不需要在当前文档里假装已经决定。
