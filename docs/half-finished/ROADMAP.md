# Roadmap — 未来开发方向

> 记录尚未实现但已完成可行性讨论的功能方向。  
> 已完成的历史路线图见 `docs/README_DEV.md` Section 3（存档）。  
> 具体 Bug / 架构问题见 `docs/TODOS.md`。

---

## R1 — 系统状态 Dashboard ✅ 已完成

**实际实现** (`ui/dashboard.py`, `ui/webview.py`, `dashboard/`, `main.py`):

- Hook: `scheduler.on_tick(scheduler, context, result)` — 每 tick 由调度循环调用
- StateStore: `update(tick_state)` / `read()` with `threading.Lock`
- HTTP server: Bottle-based, binds `127.0.0.1:0`, serves `/api/state` + `/api/health` + static SPA
- Frontend: Vue 3 + TypeScript + Element Plus, 1s polling, zombie detection
- Window: pywebview (WebView2), spawned as subprocess from tray
- TickState: 13 fields including context data (active_window, idle_time, cpu, fullscreen) beyond the original 6

**集成方式：**

- ✅ 托盘菜单「Dashboard」入口 → 独立子进程 + pywebview 窗口
- ✅ 与 History 时间轴合并（R3 已完成）

---

## R2 — 自动播单 Tag 生成（离线脚本）

> 状态：已废弃。替代方案 R6

**动机：** 手工给每个 WE playlist 标注 tag 权重耗时且主观。Workshop 目录 `steamapps/workshop/content/431960/{id}/project.json` 已包含壁纸元数据，可离线批量处理。

**可用元数据（project.json）：**

- `title`, `description` — 文字描述
- `tags` — WE 内置分类标签（如 `"Anime"`, `"Nature"`, `"Abstract"`）
  > 但 WE 标签过于粗糙，且与我们 tag 语义不完全对齐。大部分标签并不包含细粒度语义信息。整体来说利用价值有限。
- 预览图 `preview.gif` / `preview.jpg`
  > 同样，预览图分辨率较低且内容不一定具有代表性，直接用 CLIP 可能效果不佳。
  > 需要考虑解包 .pkg 文件 / 截取视频关键帧来获取更高质量的图像输入。

**三层方案，复杂度递增：**

### 层 1 — WE 内置 tag 静态映射（推荐起点）

维护一张 `WE_TAG → 我们的 tag + 权重` 映射表，纯字典查找，零 ML 依赖。

```python
WE_TAG_MAP = {
    "Nature":   {"#day": 0.6, "#chill": 0.4},
    "Dark":     {"#night": 0.8, "#chill": 0.2},
    "Anime":    {"#chill": 0.5},
    "Abstract": {},  # skip
    ...
}
```

产出：给定 `project.json`，输出可直接粘贴进 `scheduler_config.json` 的 playlist tags 建议。

局限：如上所述，“WE 标签过于粗糙，且与我们 tag 语义不完全对齐。大部分标签并不包含细粒度语义信息。整体来说利用价值有限。”

### 层 2 — 文字嵌入分类（中等）

用 `title + description` 文本 → 本地 sentence-transformers 嵌入 → 与每个我们 tag 的描述文本做余弦相似度。无需视觉，适合有详细描述的壁纸。

### 层 3 — CLIP 视觉分类（最准，有已知局限）

**CLIP 的核心问题：** CLIP 嵌入空间是通用图文对齐空间，不懂我们 tag 的语义边界（`#chill` 对它毫无意义）。

**解法：锚点标定（无需微调）**

1. 为每个 tag 手工选 5–10 张"典型壁纸"作为正例。
2. 取其 CLIP 图像嵌入的均值作为该 tag 的**原型向量**。
3. 新壁纸图像 → CLIP 嵌入 → 与所有原型向量做余弦相似度 → 归一化为权重。

标注成本极低（每 tag 5 张 × N tags），且原型向量可复用。

**实现形式：** 独立离线脚本 `scripts/tag_generator.py`，不集成进调度器主体，产出 JSON 片段供用户手动审核后合并。

**优先级：** 低（先做层 1，按需推进）| 依赖：无

---

## R3 — History 事件日志与消费 ✅ 已完成

**实际实现** (`utils/history_logger.py`, `ui/dashboard.py`, `core/actuator.py`, `dashboard/src/views/HistoryView.vue`):

- `HistoryLogger`: 线程安全、按月分片 (`history-{YYYY}-{MM}.jsonl`)、UTC 秒精度时间戳
- 六种 tagged union 事件: `start` / `stop` / `pause` / `resume` / `playlist_switch` / `wallpaper_cycle`
- `EventType` StrEnum + `EventLogger` Protocol — 消除字符串重复，依赖方向 `utils → core`
- `/api/history?limit=&from=&to=` — 返回 `{segments, events}`，后端计算 Gantt 连续区块
- `HistoryView.vue` — ECharts Gantt 时间线 + 事件列表，含过滤器和自动刷新
- `last_event_id` 单调计数器 — 前端通过 watch 实现增量自动刷新
- 事件携带 top-8 标签快照 + similarity/gap/magnitude 供调优分析

**优先级：** ✅ 已完成

---

## R3.1 — 历史高级消费（层 3：回放与审计）

> 状态：已否决。与产品哲学不符。

给定时间戳，重建当时的 `aggregated_tags` 快照，回答"为什么那时切换到了 X"。当前事件已记录 top-8 tags 和 similarity/magnitude 元数据，大部分审计需求已可满足。完整的向量快照回放需要额外的存储/查询支持。

**优先级：** 低 | 依赖：R3

---

## R4 — 移除 switch_cooldown

**决策**：移除 `scheduling.switch_cooldown` 参数及对应的 Controller gate。

**理由**：

`switch_cooldown` 的设计意图是防止频繁切换（两次 switch 间的最短间隔）。但在当前架构下，`idle_threshold` 本质上把 switch_cooldown 的活抢了：

- 能触发切换的 context 变化主要来自活动策略。用户在操作时（活动信号变化），idle gate 会阻止切换；用户空闲时（idle gate 通过），活动信号已稳定，context 不会在 cooldown 期间反转。
- 时间/季节/天气策略本身变化缓慢，不会在分钟级别引起胜者跳动。
- cooldown 期间 context 反转的概率极低：能触发 switch 的 context 变化是用户行为驱动的，而用户行为变化被 idle gate 挡住了。被 cooldown 拦截的"切完立刻又想切"场景在实践中几乎不存在。

分析 switch_cooldown 在 cooldown 期间的两种情况：

1. **context 持续强化**：胜者不变，cooldown 对结果无影响。
2. **context 反转**：需要进一步拆解——
   - **2a：反转回原 playlist**——说明第一次切换是短暂波动，cooldown 避免了一次来回。但这种"idle 状态下 context 自行反转"的场景本身就罕见（活动信号不变，时间/季节/天气不会分钟级跳动）。
   - **2b：反转到第三个 playlist**——cooldown 纯粹延迟了跟随，是负面效果。

结论：switch_cooldown 的理论价值（防抖动）在实践中被 idle gate 自然消解。它是一个用时间维度约束替代置信度判断的粗糙机制。

移除后的调度语义更加干净：

```
传感器 → Context → Matcher(1Hz 跟随) → [idle / fullscreen / cpu gate] → 执行
```

- Matcher 负责每秒检测最佳 playlist 并跟随
- Gate 层只做"环境条件不满足就不动"，不再混入时间维度的间接约束
- `cycle_cooldown` 保留——它控制的是同播放列表内的壁纸轮换节奏，语义不同

---

## R5 — Wallpaper-Aware Cycle（折中路线）

参考规格：[WALLPAPER_AWARE_CYCLE_SPEC.md](./WALLPAPER_AWARE_CYCLE_SPEC.md)

**定位：** 不放弃成熟的 playlist-base 主线，只在同 playlist 内的 cycle 分支引入 wallpaper-aware ranking。

核心边界：

- playlist switch 仍走现有 `openPlaylist`，不接管 switch。
- 只有 `matched playlist == active playlist` 且 cycle allowed 时，才在当前 playlist 的 `items` 中选择具体 wallpaper。
- 通过 `openWallpaper(file)` 执行 selected wallpaper。
- ranking 使用 playlist vector 作为用户语义中心，离线模型 bias 只作为 playlist 内相对偏移。
- 一期只扩展后端 trace，不做 Diagnostics UI 改版。

数学模型简述：

```text
p = manual playlist vector
a_i,t = raw model score for wallpaper i and tag t
b_i,t = 2 * (percentile_rank_P(a_i,t) - 0.5)
v_i = normalize_positive(p + alpha * support_shrink(t, p) * b_i)
score_i = cosine(context_vector, v_i) + recency + user_bias + noise
```

近期 POC：

- 验证 `openWallpaper -file` 后 WE `config.json` 是否保留 selected playlist。
- 验证 `getWallpaper` 是否稳定返回当前 wallpaper。
- 验证 `openWallpaper` 后 `nextWallpaper` 是否仍具有当前 playlist 内轮播语义。

**优先级：** 中。它不是当前 stable release 的阻塞项，适合作为 playlist-base 发布后的实验分支。

## R6 —— 匹配算法修改/增强

**前置：R7**

**背景**：当前匹配算法流程实际等价于

$$
score = dot(context, playlist) / (||context|| * ||playlist||)
$$

对同一个 tick 来说，$ ||context|| $ 对所有 playlist 都一样，所以排名本质上是：

$$
score_for_ranking = dot(context, playlist) / ||playlist||
$$

也就是说，当前的排名里面，分数被 ||playlist|| 做了强归一化

**目标** 对算法进行进一步打磨。

### 产品前置哲学：

1. playlist 的标签数值，是“形状”还是“力量”？

这里，按照 playlist 作为亲和度的原则，统一认为是“形状”。力量可以引入新的参数来表示，如 `magnitude` 或者 `strength`

2. playlist 是“语义中心”，还是“语义覆盖区”？

这是区分 AND 和 OR 匹配的关键点。我认为，这里更好的产品哲学是 AND-ish。用户配置多个自己设想的细致场景，调度器负责匹配和平滑过渡。

3. 算法应该奖励“专精”，还是奖励“兼容”。

这里与 2 相似，我认为应该奖励专精。 AND 可以覆盖很多场景，但一个太强的 OR 会直接霸占屏幕。

### 可能的路线：将 playlist 处理看作多个过程。

```python
playlists = pre_process_playlist(playlists)
context = pre_process_context(context)
evidence = aggregate(playlists, context)
score = post_process(evidence[p], playlists[p])
```

1. `pre_process_playlist`

可考虑的处理：

- 标签锐化：$\text{tag} = \text{tag} ^ \gamma$。 这里的一大作用是更加贴近用户配置直觉。当用户写一个小标签时，他们通常会低估这个标签的影响。
- soft norm: $\frac{\text{c · p}}{||c|| · ||p||^\alpha}$。 我们对 playlist 做方向 & 模长分解后用处低。
- 特异性奖励：$ p_i = p_i \cdot idf(tag) $，$idf(tag) = log((N + 1) / (df(tag) + 1)) + 1$。可能有用，但副作用明显。一个改动会影响全局

2. `pre_process_context`

可考虑的处理：

- 锐化： $c_i = c_i ** beta$。将策略的变化率变为 $\gamma p^(\gamma - 1)$。也就是大时变化快，小时变化慢，可能是很好的动态对比增强。
- 特异性：如果 Playlist 侧做了 idf，Context 侧也推荐做

3. `aggregate`

可考虑的处理：

- soft cosine:

$$
evidence = dot(c, p)
penalty = norm(c) * norm(p) ** alpha
score = evidence / penalty
$$

如上所述，我们对 playlist 做方向 & 模长分解后用处低。

- weighted cosine with tag specificity

$$
evidence = sum(idf_i * c_i * p_i) \\
 \text{or} \\
 evidence = dot(c_{idf}, p_{idf})
$$

和 idf 配套。

- mismatch penalty。但是这个可能会有大面积误伤

4. `post_process`

可考虑的处理：

- over-broad penalty :

$$
effective_dims = (sum(p_i) ** 2) / sum(p_i ** 2)
score -= lambda * log(effective_dims)
$$

- saturation

但是上面两个都有点复杂，解释性也一般

### 初版公式

```python
p = playlist.portion
c = resolved_context

p_dir = normalize(pow_each(p, gamma_p))
c_dir = normalize(pow_each(c, gamma_c))

score = dot(c_dir, p_dir) * playlist_weight ** beta
```

参数暂定：

```python
gamma_p = 1.25
gamma_c = 1.2
playlist_weight = 1.0
beta = 0.25
```

## R7 —— 匹配调参设施优化

**背景**： 在 R6 这种涉及匹配算法的调整过程中，需要一个模拟器来确认改动行为的影响。老旧的 `/misc` 只吸收思想，不继续扩展。

**目标**：开发内部调参基础设施。它不是公开用户功能，优先服务 R6。

### 目录

第一版放在：

```text
tools/tuning/
  tune.py
  scenarios_r6.py
  models.py
  runs/.gitkeep
```

- `tune.py` 负责加载配置、运行场景、profile 对比和输出报告。
- `scenarios_r6.py` 负责定义 R6 调参场景。
- `models.py` 放少量数据结构和 helper，不按每个模型拆文件。
- `runs/` 放运行产物，不进 git。

### P0

1. 真实配置加载
   直接用当前已有配置文件流。不维护第二套 playlist/tag 定义。
2. Python 场景矩阵 + expected winner
   不使用 YAML。场景是内部实验代码，需要 helper、组合生成、注释和临时观察场景。
   场景描述 Context 向量的驱动外界因素：`hour`、`day_of_year`、`weather`、`activity` 和期望 playlist。`expected` 可以为空。
3. 无副作用模拟执行
   构造 Context，跑 Policy + Matcher，不使用真实传感器、不操作 Wallpaper Engine Executor。
   ActivityPolicy 默认由 `ActivitySignal(direction, intensity, salience)` 完全指定，不跑真实 EMA / window matcher。Time / Season / Weather 按输入生成。
4. 单场景排名报告
   输出 winner、expected、top3、score、gap、raw/resolved context、policy contribution。
5. 算法 profile 对比
   至少支持 `current` vs `candidate`。profile 可以先是 Python 对象，如 `MatchProfile(name, gamma_playlist, gamma_context)`。
   输出 winner 改变、expected pass/fail 改变、gap 变化和 observed 场景变化。

### P1

1. 参数扫描
   扫 `gamma_playlist` / `gamma_context` 等参数，输出 pass rate、平均 gap、churn rate。第一版直接做小网格枚举，不做复杂优化器。
2. 决策空间热力图：winner map
   支持 `hour × doy`、`weather × hour`、`activity × hour`、`weather × activity` 等关键视图。
3. 决策空间热力图：margin map
   不只看赢家，还看边界稳定性。

### 输出

第一版输出：`manifest.json`、`rankings.csv`、`compare.csv`、`summary.md`。

后续加入热力图后，再输出 `figures/*.png`。

建议后续加入 gitignore：

```gitignore
# Internal tuning tool outputs
tools/tuning/runs/*
!tools/tuning/runs/.gitkeep
```

### 暂不做

- YAML scenario 格式。
- 用户界面。
- 自动 low-margin 汇总。低 margin 不是天然错误，有些边界场景本来就应该 subtle。
- 反向建议器。
- 自动写配置。

## R8 — 候选池调度（Pool-Based Scheduling）

**前置：R4（移除 switch_cooldown）**

**动机**：

当前 Matcher 每 tick 输出单一 `best_playlist`，所有 playlist 被同等对待——要么赢，要么输。这在典型场景下没有问题（gap 明显，胜者清晰），但在过渡场景下存在设计张力：

- 季节交替、天气过渡、时段切换时，多个 playlist 的 cosine 相似度可能非常接近（0.01 级别差距）。
- 系统在这些噪声级别的差异上做强制选择，但这个选择本身没有意义——多个 playlist 同样适合当前 context。
- 从 flow 角度，用户不会注意壁纸是哪个 playlist 的，但会注意到壁纸变了。在低 gap 区间内的微小 context 波动可能导致 best_playlist 跳动。

**核心思路**：

将 `best_playlist: str | None` 重构为 `best_playlists: set[str]`。单个 playlist 是候选池的退化情况（singleton set）。

当 top-N playlist 的 cosine 相似度落入同一簇时，将它们合并为一个候选池。matcher 返回的不再是单一胜者，而是一个语义等价的 playlist 集合。

**设计要点**：

### 1. 术语与命名

- `best_playlist` → `best_playlists`（复数，`set[str]`）
- identity 侧对应 `active_playlists: set[str]`
- pool 是 set（无序、去重）
- switch/cycle 的语义统一基于 playlists 池。

### 2. 聚类逻辑

- 典型场景下 gap 明显，聚类退化为 singleton，行为与现有逻辑一致
- 过渡场景下多个 playlist 落入同一簇，形成候选池

### 3. 执行逻辑

**Switch**：按壁纸数量加权随机选一个 playlist，执行 `openPlaylist`。

这里，按壁纸数量加权是为了保持“所有壁纸同等重要”的语义。另外，我们允许一个壁纸出现在多个 playlist 中。这个壁纸的出现概率上升，而这是合理的。

**Cycle**：按壁纸数量加权随机选一个 playlist：

- 选中的就是当前 playlist → `nextWallpaper()`（WE 原生轮播）
- 选中的是另一个 playlist → `openPlaylist`（切换到该 playlist）

**需要新增的数据**：

- 每个 playlist 的壁纸数量（用于 switch/cycle 时的加权随机）。来源：WE config.json 的 playlist items 扫描。可在初始化时扫描一次缓存。

---
