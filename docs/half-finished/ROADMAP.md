# Roadmap — 未来开发方向

---

## R1 — 自动播单 Tag 生成（离线脚本）

> 状态：已废弃。替代方案 R6

**动机：** 手工给每个 WE playWlist 标注 tag 权重耗时且主观。Workshop 目录 `steamapps/workshop/content/431960/{id}/project.json` 已包含壁纸元数据，可离线批量处理。

**可用元数据（project.json）：**

- `title`, `description` — 文字描述
- `tags` — WE 内置分类标签（如 `"Anime"`, `"Nature"`, `"Abstract"`）
  > 但 WE 标签过于粗糙，且与我们 tag 语义不完全对齐。大部分标签并不包含细粒度语义信息。整体来说利用价值有限。
- 预览图 `preview.gif` / `preview.jpg`
  > 同样，预览图分辨率较低且内容不一定具有代表性，直接用 CLIP 可能效果不佳。
  > 需要考虑解包 .pkg 文件 / 截取视频关键帧来获取更高质量的图像输入。

**三层方案，复杂度递增：**

### 层 1 — WE 内置 tag 静态映射（推荐起点）

### 层 2 — 文字嵌入分类（中等）

### 层 3 — CLIP 视觉分类（最准，有已知局限）

## R2 — Wallpaper-Aware Cycle（折中路线）

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

## R3 —— 匹配算法修改/增强

**前置：R4**

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

## R4 —— 匹配调参设施优化

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
