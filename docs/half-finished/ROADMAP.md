# Roadmap — 未来开发方向

---

## R1 — Wallpaper-Aware Cycle（折中路线）

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

## R2 —— 匹配算法修改/增强

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
