# Tuning Output Simplification Spec

## Goal

将 tuning 工具从“完整实验归档”改成“调参决策面板”。

默认输出只保留真正有助于判断匹配算法好坏的信息：

1. Scenario 验收结果
2. Winner heatmaps
3. Sweep 极简指标总结或参数图

默认不再输出长篇 diagnostics、完整 rankings、完整 compare、manifest、机器阅读型数据文件。

---

## Non-goals

默认输出不追求完整复现。

默认输出不追求机器二次分析。

默认输出不保留每个 policy 的完整 contribution。

默认输出不保留 raw context、fallback expansion、逐 cell 数据、完整 CSV 明细。

这些内容应该直接弃用，不保留为 debug 能力

---

## Default Output

一次 tuning run 默认只输出：

runs/<run-name>/
report.md
heatmaps/
\*.png
sweep.png 或 report.md 内的极简 Sweep Summary

其中：

report.md 是唯一文字入口。

heatmaps/ 只放 winner map。

sweep 如果暂时不画图，则只在 report.md 里输出极简文字摘要。

---

## report.md 内容

report.md 只包含三部分。

### 1. Scenario Results

核心表格字段：

Scenario
Category
Expected
Winner
Status
Gap
Top3
Resolved Tags Top

字段说明：

Scenario:
场景名称。

Category:
场景分类，例如 core、nice_to_have、boundary、observed。

Expected:
期望 winner。没有 expected 的场景显示 observed。

Winner:
实际 winner。

Status:
pass / fail / observed

Gap:
top1_score - top2_score。

Top3:
只显示前三名 playlist 和分数。

Resolved Tags Top:
只显示 resolved context 中权重最高的若干 tag。
默认显示 top 5。
不显示 raw context。
不显示 policy contribution。
不显示 fallback expansion。

示例展示形态：

Scenario: day focus clear
Category: core
Expected: BRIGHT_FLOW
Winner: BRIGHT_FLOW
Status: pass
Gap: 0.143
Top3: BRIGHT_FLOW 0.812, SUMMER_GLOW 0.669, CASUAL_ANIME 0.641
Resolved: focus 1.20, day 0.72, clear 0.45, spring 0.18

实际输出时应该输出为二维表格形式

---

### 2. Coverage Summary

按 category 汇总，而不是只给一个总 pass rate。

至少输出：

Overall expected pass:
pass count

By category:
每个 category 的 pass / fail / observed

Ambiguous failures:
只列 fail 且 gap 低于 ambiguous_failure 阈值的 scenario

Confident failures:
只列 fail 且 gap 高于 confident_failure 阈值的 scenario

说明：

低 gap fail 可能只是边界问题。

高 gap fail 代表模型非常坚定地选错，关注度更高。

---

### 3. Sweep Summary

Sweep 默认不输出完整表格。

只输出能帮助选择参数的极简指标。

必须包含：

Baseline:
current 的 pass rate、avg gap、confident fail count

Best pass-rate candidate:
pass rate 最高的候选

Best low-churn candidate:
在 pass rate 接近的前提下（可以以通过率为阈值），winner 变化最少的候选

Sweep 指标口径：

核心排序只使用 expected scenarios。

observed scenarios 不参与 pass rate。

observed scenarios 可以参与边界观察，但不能影响默认推荐。

必须拆分：

pass_rate_expected
avg_gap_expected
churn_rate_expected
confident_fail_count_expected

可选展示：

avg_gap_all
churn_rate_all

但 all 口径不能作为默认推荐的主排序依据。

---

## Heatmap Output

默认只输出 winner heatmaps。

删除输出 margin heatmaps 的分支

原因：

margin map 的主要信息通常只是 winner 边界附近 gap 小、色块内部 gap 大。
这类信息大多可从 winner map 推断，默认输出价值不足。

---

## Heatmap Coverage

Heatmap 从 mode-based 改为 case-based。

每张图由以下概念定义：

case name
mode
fixed conditions

其中 mode 仍表示二维扫描轴，例如：

act-hour
act-doy(需新增)
wx-hour
wx-act
wx-doy(需新增)
hour-doy

fixed conditions 表示其他维度的固定值，例如：

doy
weather
hour
activity

默认 heatmap cases 应参考 `misc\vis_explore.py` `DEFAULT_PANELS` 中的场景定义。

`misc/vis_explore.py` 的 `DEFAULT_PANELS` 仅作为语义来源。

迁移时执行命名映射：

wx-season -> wx-doy
act-season -> act-doy
hr-doy -> hour-doy

## Heatmap Naming

图片名称必须能直接表达 case。

推荐命名语义：

<profile>-<case-name>.png

采用简短的名称以控制图片名长度，保证能够快速阅读。

推荐：

```plain
weather: wx
hour: hr
activity: act
season: doy
```

```plain
current: cur
candidate: p<gamma value>c<gamma value>
示例：
gamma_playlist=1.25, gamma_context=1.20
=> p125c120
```

如果存在候选 profile，也使用同样 case 命名。

---

## Margin Policy

Margin 图默认删除。

不作为默认产物。

比 margin 更有价值的后续方向：

runner-up map。即绘制亚军图。

在输出策略上，可以考虑与胜者图并列输出。

但这些不是当前默认输出的必要项。

---

## Scenario Grouping and Weight

Scenario 应支持分组。

Category 用于解释覆盖范围。

默认 category 建议：

core:
高频、必须正确的核心场景。

nice_to_have:
涉及重要事件的场景。例如大雨，四季 peak

boundary:
观察边界，不一定有 expected。

observed:
纯观察场景，不参与 pass rate。

---

## Status Definition

pass:
expected 存在，且 winner == expected。

fail:
expected 存在，且 winner != expected。

observed:
expected 不存在，仅展示 winner、gap、top3、resolved tags。

---

## Sweep Recommendation Rules

Sweep 的默认推荐不应该只看 pass rate。

推荐候选应考虑：
pass_rate_expected
avg_gap_expected
churn_rate_expected
confident_fail_count_expected
core category regression

推荐逻辑的产品语义：

1. 不能牺牲 core category。
2. pass rate 提升优先。
3. confident fail 越少越好。
4. 在 pass rate 接近时，低 churn 优先。
5. gap 只作为稳定性辅助，不奖励自信地错。

---

## What Should Be Removed From Default Output

默认不输出：

rankings.csv
compare.csv
sweep.csv
manifest.json
diagnostics.md
raw context
resolved context full list
fallback expansions
policy contribution list
per-policy diagnostics
full scenario × profile matrix
margin heatmaps

这些内容默认都不进入 run 目录。

---

## Final Product Shape

默认 tuning run 应该像这样：

```plain
runs/<run-name>/
report.md
heatmaps/
\*.png
sweep.png
```

若 sweep 内嵌 report 输出，则为：

```plain
runs/<run-name>/
report.md
heatmaps/
\*.png
```
