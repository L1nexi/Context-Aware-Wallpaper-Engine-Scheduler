# TODOs & 架构讨论记录

> 基于 v1.3.0 架构深度审查的讨论结果。日期：2026-04-19

---

## 讨论结论

### #1 weight_scale 语义与标签重叠

**原始问题：** `weight_scale` 在 Arbiter 加法聚合 + Matcher 余弦相似度链路下，控制的是多策略向量求和后的方向偏转，而非绝对优先级。多策略若向同一标签贡献权重，会导致该标签被叠加放大。

**讨论结论：** 当前标签集已按策略域自然分离（Activity: `#focus/#game`…, Time: `#dawn/#night`…, Weather: `#rain/#storm`…），重叠仅在用户故意配置时才可能发生。

- **否决前缀方案**（如 `Activity-#focus`）：会使 playlist 配置冗长，破坏共享语义空间（丧失多策略向同一语义方向投票的能力）。
- **采纳方案：** 将「标签应按策略域分离」作为配置约定，在文档中明确说明。

**状态：** 📝 文档化约定 | 优先级 P2

---

### #2 归一化不对称（Activity/Weather 跳过 L2）

**讨论结论：** 已在 `README_DEV.md` 和代码注释中标注为设计决策。无需额外操作。

**状态：** ✅ 无需操作

---

### #3 TimePolicy H 值刚性

**原始问题：** 动态 sunrise/sunset 使 4 个峰不再等距，但 $H = 24/4 = 6\text{h}$ 固定。夏季极端场景下相邻峰间距可能 < H（Hann 窗重叠严重）或 > H（出现零值间隙）。

**讨论结论：** Accept。需要对 H 做自适应，使其随实际峰间距调整。

**修复方向：** 分段线性时间扭曲。建立映射函数将真实峰值映射到虚拟域 0/6/12/18h，在虚拟域应用固定 H=6 的 Hann 窗。等价于每段弧长独立的非对称 Hann 窗，但实现更优雅、扩展性更强。

等价性：分段线性扭曲后，弧 [p_A, p_B]（真实长度 L）映射到虚拟弧长 6，在虚拟域 w(t) = Hann(|t - t_A|/L × 6, 6) = Hann(|t - t_A|, L)，与非对称余弦窗（方案1）数学等价。将 H 的选取逻辑封装在 `_warp_time()` 中，Hann 核本身保持不变。

**状态：** ✅ 已实现 (`core/policies.py` `TimePolicy._warp_time`) | 优先级 P0

---

### #4 Matcher 标签宇宙仅由 Playlist 定义 → 静默丢弃

**原始问题：** Policy 输出的标签若不在任何 Playlist 中则被静默丢弃。例如 WeatherPolicy 输出 `{#storm: 0.89, #rain: 0.45}` 但无 Playlist 含 `#storm` → `#storm` 分量丢失，`#rain` 分量的相对权重也发生变化（模长缩小导致归一化后偏转）。

**关于新增 Playlist 改变已有匹配的担忧：已证伪。** 已有 Playlist 在新维度上分量为 0，cosine 分子不变；环境向量归一化分母虽变，但对所有已有 Playlist 等比缩小，排名不变。

**讨论结论：** 真实问题是多维度信号被截断后导致模长失真。

**采纳方案（两层）：**

1. **加载期 WARNING**：Matcher 对每个不在 playlist 标签宇宙中的 tag，首次出现时打 WARNING（`_warned_tags` 集合去重，避免每 tick 重复）。
2. **Per-policy 保模长补偿**：弃用 `Arbiter` 模块，`Matcher` 接收 `context` 并计算 per-policy 列表，对每个 policy 独立投影 + 保模长缩放后再求和构建环境向量。这样 `#storm` 被丢弃时，仅 `#rain`（同属 WeatherPolicy）被缩放，`#night`（TimePolicy）完全不受影响。Scheduler 在 Think 步骤将 per-policy 列表平铺为 `aggregated_tags` 供日志/状态展示（反映真实 policy 意图，不含补偿）。

**状态：** ✅ 已实现 (`core/arbiter.py`, `core/matcher.py`, `core/scheduler.py`) | 优先级 P1

---

### #5 无法表达排斥语义

**讨论结论：** 否决。系统目标是「匹配最佳场景」，过渡地带全低分是预期行为。不需要负权重机制。

**状态：** ✅ 无需操作

---

### #6 Hot Reload 丢失 EMA 状态

**原始问题：** `_hot_reload()` 重建 ActivityPolicy → `smoothed_tags` 归零 → 前 N tick Activity 信号缺失 → Time/Season 主导 → 可能触发意外 Playlist 切换 → 被冷却锁住。

**讨论结论：** Accept，但目前 hot reload 主要用于测试，优先级后移。未来需要更健壮的初始化方式（序列化/恢复 EMA 状态，或用当前瞬时标签预热）。

**状态：** 📋 待设计 | 优先级 P2

---

### #7 Controller 时间戳在 Hot Reload 时重置

**原始问题：** `_hot_reload()` 创建新 Controller，`last_playlist_switch_time` 重置 → 冷却期失效或异常。

**讨论结论：** Accept，与 #6 同属 hot reload 健壮性问题。统一在 hot reload 改进中解决。

**修复方向：** `_hot_reload()` 从旧 Controller 提取时间戳注入新 Controller，或将 Controller 设计为可更新配置而非重建。

**状态：** 📋 待设计（合并入 #6） | 优先级 P2

---

### #8 Wallpaper Cycle 不受 Gate 约束

**原始问题：** `can_cycle_wallpaper()` 仅检查 cooldown，不经过 Gate 链。全屏游戏时 Playlist 切换被正确 defer，但 Wallpaper 仍然 cycle → D3D exclusive fullscreen 下可能闪屏。

**讨论结论：** 确认为 Bug。

**修复：** 在 `can_cycle_wallpaper()` 中加入 `_any_gate_defers()` 检查。

**状态：** ✅ 已实现（审查发现代码中已包含此检查） | 优先级 P0

---

### #9 ActivityPolicy 单标签限制

**讨论结论：** 否决扩展。当前 title_rules 粒度已足够——不同标题可映射到不同标签，EMA 在时间维度上自然合成多活动向量。加入 weighted_tag（如 `{"#focus": 0.7, "#creative": 0.3}`）会增加配置复杂度且不符合 Activity 的决策语义：ActivityPolicy 描述的是「正在做什么」，而非「什么程度」。

**状态：** ✅ 无需操作

---

### #10 history.jsonl 无界增长

**讨论结论：** Accept，低优先级。日均约 144 条记录（10min cycle），年约 10MB。

**修复方向：** 添加 max-size 检查或按日期/大小 rotation，可复用 `RotatingFileHandler` 思路。

**状态：** 📋 待实现 | 优先级 P3

---

### #11 配置无 Schema 校验

**讨论结论：** Accept。

**采纳方案（两层渐进）：**

1. **即期：轻量 WARNING**：在 `config_loader.load()` 中定义 known keys 集合，遇到未知 key 则 `logger.warning("Unknown config key: %s", key)`。
2. **远期：jsonschema 校验**：适合稳定后做。引入 jsonschema 依赖，提供完整的类型/范围/必填校验。

**状态：** 🔧 待实现 | 优先级 P2

---

## 实施计划

### P0 — Correctness（正确性修复）

| # | 任务 | 工作量 | 关联 |
|---|------|:------:|------|
| P0-A | TimePolicy 自适应 H：per-peak 半宽随实际间距调整 | 小 | #3 | ✅ |
| P0-B | `can_cycle_wallpaper()` 加入 Gate 检查 | 极小 | #8 | ✅ |

### P1 — Robustness（健壮性改善）

| # | 任务 | 工作量 | 关联 |
|---|------|:------:|------|
| P1-A | Matcher 标签宇宙校验 + WARNING 日志 | 小 | #4 | ✅ |
| P1-B | Policy 输出保模长降维（去无效分量保总模长） | 中 | #4 | ✅ |

### P2 — Quality of Life

| # | 任务 | 工作量 | 关联 |
|---|------|:------:|------|
| P2-A | Hot Reload 健壮化：保留 EMA 状态 + Controller 时间戳 | 中 | #6 #7 |
| P2-B | 配置 unknown key WARNING | 极小 | #11 |
| P2-C | 文档化标签域分离约定 | 极小 | #1 |

### P3 — Nice to Have

| # | 任务 | 工作量 | 关联 |
|---|------|:------:|------|
| P3-A | history.jsonl rotation | 小 | #10 |
| P3-B | jsonschema 完整校验 | 中 | #11 |
