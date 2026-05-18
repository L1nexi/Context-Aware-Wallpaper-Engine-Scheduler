# Wallpaper-Aware Scheduling 访谈记录

日期：2026-05-18

本文记录一次关于后续后端方向的产品 / 架构访谈。它不是正式实施方案，也不是已批准路线图。当前结论更接近：保留 `playlist-base` 主线的成熟成果，同时认真评估 `wallpaper-aware` 能力是否值得作为下一阶段演进方向。

## 1. 背景

项目最初选择的是 `playlist-base + 手工 tag 标注调参` 的 scheduler：

- 用户在 Wallpaper Engine 中手工维护 playlist。
- 项目配置中对 playlist 做 `tag: weight` 标注。
- Policy 根据 context 输出 tag 向量。
- Matcher 在 playlist 向量中做匹配。
- Controller 决定是否切换 playlist 或在当前 playlist 内轮播。
- Wallpaper Engine 自己负责 playlist 内部的随机 / 顺序 / delay 逻辑。

这条路线的优势是可控、可解释、工程边界清楚。当前主线已经基本成熟：YAML 配置系统、Diagnostics、热重载、controller 诊断、factual playlist recovery 和配置辅助工具都已经打通。

新的问题是：是否值得从 playlist 粒度下沉到 wallpaper 粒度，让 scheduler 直接选择具体 wallpaper。

## 2. 现场事实

本次讨论参考了以下事实源：

- `docs/archived/reference/WE_CLI.md`
- `docs/archived/reference/WE_CLI_POC.md`
- 当前机器上的 Wallpaper Engine `config.json`
- 现有代码结构：`core/`、`utils/`、`ui/dashboard_analysis.py`
- git 历史中的项目推进节奏和大改规模

从当前 WE `config.json` 中观察到：

- 顶层包含安装目录和用户 entry。
- 用户 entry 中包含 `general`、`version`、`wproperties`。
- 当前有 10 个 playlist，基本对应项目 example 配置中的语义 playlist。
- playlist 的 `items` 是实际 wallpaper 路径列表。
- playlist 的 `settings` 包含 `delay`、`mode`、`order`、`transition`、`transitiontime`、`updateonpause`、`videosequence`。
- 去重 playlist item 数量为 160。
- 160 个 item 都能找到对应 `project.json`。
- 类型分布大致为：`scene 130`、`video 24`、`web 5`、`application 1`。
- WE 原生 tag 主要集中在 `Anime`、`Landscape`、`Relaxing`、`Game`、`Nature`。
- `project.json` 包含 `title`、`description`、`type`、`tags`、`preview`、`file`、`workshopid`、`general.properties` 等信息。
- `wproperties` 保存用户对具体 wallpaper 的本地属性覆盖。
- 项目属性类型中 `schemecolor` 覆盖面很高，另有大量 `bool`、`slider`、`color`、`combo`、`text` 类属性。

WE CLI 文档中可用能力包括：

- `openPlaylist`
- `nextWallpaper`
- `openWallpaper -file ...`
- `getWallpaper`
- `openProfile`
- `applyProperties`
- `pause` / `play` / `mute` / `unmute`
- `hideIcons` / `showIcons`
- per-monitor / location 参数

当前项目主要使用的是 `openPlaylist` 和 `nextWallpaper`，还没有充分利用 `getWallpaper`、`openWallpaper` 和 per-wallpaper metadata。

## 3. 产品哲学分叉

这次讨论中形成的核心判断：

> `wallpaper-base scheduler` 不只是更细粒度的 playlist scheduler，而是受 context 驱动的本地推荐系统。

如果调度单元从 playlist 变成 wallpaper，项目的核心问题会从：

> 用户如何用文本配置表达调度规则？

转向：

> 软件如何理解本地 wallpaper library，并持续选出更符合用户当前状态的 wallpaper？

这个转向会带来明显上限，也会引入推荐系统的典型问题：

- 冷启动。
- 用户语义和模型语义不一致。
- 个性化反馈。
- 探索 / 利用权衡。
- 排序稳定性。
- 长期偏好漂移。
- 可解释性与可纠偏性。

讨论中明确区分了两个概念：

- **可解释性**：能否解释每个 embedding 或每个分数为何如此。
- **可纠偏性 / 可控制性**：用户能否表达“不要这样选”“这张适合这里”“这类少出现”。

结论倾向是：不必执着于完全解释模型内部，但不能丢掉 inspectability 和 controllability。

## 4. Full Wallpaper-Base 的收益

完整 `wallpaper-base` 的主要好处：

### 4.1 更细致的 scheduling

playlist-base 的 controller 只能决定：

- 是否切换 playlist。
- 是否让 WE 在当前 playlist 中轮播下一张。

wallpaper-base 后，controller 可以直接控制：

- 当前 wallpaper 是否仍值得保留。
- 候选 wallpaper 是否比当前明显更合适。
- 是否应探索新的候选。
- 最近是否已经看过类似 wallpaper。
- 同 context 下是否需要多样性。
- 不同 wallpaper 类型是否应按 CPU / fullscreen / idle 状态调整权重。

这会释放 controller 能力，但也会让 controller 从 gatekeeper 变成 scheduler + ranker + diversity controller。

### 4.2 更细致的 matching

当前 playlist tag 向量本质是人工把一组 wallpaper 压缩为一个稀疏向量。信息损失很大。

wallpaper-base 可以让每张 wallpaper 拥有自己的语义位置。匹配也可以从少量 playlist 分类转向候选排序：

- top-k candidate generation
- softmax / temperature sampling
- recency penalty
- diversity penalty
- user bias
- transition cost

### 4.3 真正开箱即用的可能性

如果软件能扫描 WE library 并自动理解 wallpaper，用户理论上只需配置 Policy 优先级和 scheduling 参数，不再需要手工给 playlist 标注 tag。

但这会把配置负担转化为信任负担：

- 为什么它觉得这张适合工作？
- 为什么夜晚选择这张？
- 为什么某些收藏永远不出现？
- 为什么它选了一张我不喜欢的图？

因此开箱即用必须配套反馈和纠偏机制。

## 5. Full Wallpaper-Base 的代价

### 5.1 模型不可避免

一旦候选从 10 个 playlist 变成上百 / 上千张 wallpaper，人工 `tag: weight` 基本不可持续。

完整 wallpaper-base 很可能需要：

- metadata-based feature extraction
- text embedding
- image embedding
- keyframe extraction
- preview analysis
- clustering
- ranking model 或 bias layer

这会带来：

- 模型依赖。
- 包体和运行环境压力。
- 首次索引耗时。
- 模型版本导致排序漂移。
- 测试从确定性断言转向质量评估。

### 5.2 用户语义 gap

模型能识别图像内容，但不等于理解用户偏好。

同一张 wallpaper 对模型可能是：

- night city
- anime character
- rainy window
- blue color palette

但对用户可能是：

- 适合工作，因为熟悉且不分心。
- 不适合工作，因为主体太抢眼。
- 虽然是雨夜，但让人心情低落。
- 因为作品偏好，所以任何时候都加分。

这个 gap 不是更强模型就能完全解决的问题，需要 personalization layer。

### 5.3 产品边界变大

wallpaper-base 很容易把项目从 scheduler 拉向完整 WE 管理器 / 推荐器 / 配置训练系统。需要警惕恢复大型管理后台式产品形态。

## 6. 人工 Tag Space 方案

一种中间路线是保留现有 Context / Policy 输出，但将每张 wallpaper 映射到人工 tag space。

现有 tag space 大致是：

- `focus`
- `chill`
- `day` / `night` / `dawn` / `sunset`
- `spring` / `summer` / `autumn` / `winter`
- `clear` / `cloudy` / `rain` / `storm` / `snow` / `fog`

这些足够区分当前 10 个 playlist，但不足以稳定区分大量 wallpaper。

如果保留人工 tag space，可能需要扩展新的调度语义维度：

- 氛围：calm、energetic、melancholy、cozy、epic、minimal。
- 视觉密度：clean、detailed、busy、dark、bright。
- 主体：landscape、city、room、character、abstract、space、nature。
- 动态强度：ambient、motion-heavy、static-ish。
- 干扰程度：low-distraction、attention-grabbing。
- 使用场景：deep-work、casual-browse、sleep、gaming、presentation。
- 色彩 / 亮度：warm、cool、neon、monochrome、high-contrast。

这个 ontology 一旦定义好，长期收益很高；但定义和调优本身是一项产品设计工作。tag 太少表达力不足，tag 太多又难以配置和调试。

一个较稳的原则是：只定义会影响 scheduling 的维度，不试图完整描述 wallpaper 内容。

## 7. 端到端方案

端到端路线是：

```text
Context + History + Wallpaper Features -> Learned Ranker -> Next Wallpaper
```

它的上限最高，但当前不适合作为近期路线：

- 单用户初期反馈数据不足。
- 隐式反馈很脏。
- 训练和测试成本高。
- 解释和回归控制困难。
- 会显著改变项目工程形态。

结论：端到端可以作为远期形态，不应作为下一步主线。

## 8. 反馈机制

讨论中认为反馈机制非常关键，因为它是解决“模型语义 != 用户语义”的主要手段。

反馈不必一开始训练模型，可以分层：

### 8.1 硬规则

- 永不展示这张 wallpaper。
- 这个 context 不展示这张。
- 这张只在 night 展示。
- 这张不要用于 focus。
- 这个 playlist / cluster 降权。

### 8.2 Ranking bias

- 用户手动保留或应用某张，给 wallpaper-context pair 加分。
- 用户跳过某张，给它或它的 cluster 降分。
- 某张在某 context 下停留很久，加一点偏置。
- 反馈可随时间衰减，防止永久污染。

### 8.3 Learned personalization

- 学用户偏好的 embedding offset。
- 学 context-wallpaper pair 的 reranker。
- 使用 pairwise preference 做轻量排序模型。

这可以很晚再做。

## 9. 工作量评估

本次讨论用 git 历史校准了项目推进效率。

参考规模：

- `v0.4.0..v0.5.0`：16 commits，45 files，约 `+1495/-849`。语义输出和调度核心的中型重构。
- `v0.5.0..v0.6.2`：34 commits，196 files，约 `+23418/-1414`。Dashboard / Config GUI 相关阶段。
- `v0.6.2..v0.7.0`：45 commits，259 files，约 `+14174/-13294`。完整产品路线收敛和配置系统重构。
- `v0.7.0..v0.7.1`：7 commits，31 files，约 `+1583/-453`。健壮性补强。

估计：

- wallpaper-base 技术原型：约 3-5 个活跃开发日。
- 实验性 MVP：约 10-15 个活跃开发日。
- 可替代 playlist-base 的 v0.8 实验版本：约 3-5 周活跃时间。
- 带模型自动语义标注 / embedding 的产品版本：约 6-10 周以上。

判断：

- 不应现在放弃成熟的 playlist-base。
- 应先发布当前 playlist-base stable。
- 如要探索 wallpaper-base，应开长期 branch，而不是在主线直接 pivot。

## 10. 发散方案记录

讨论中提出过多种方向。以下只保留偏算法 / 后端内核的方案，去掉工具向和配置助手向方案。

### 10.1 Smart Cycle Only

保留 playlist-base 主调度，只替换当前 playlist 内部的 `nextWallpaper`。

```text
matched playlist 不变
cycle cooldown 到了
-> 在当前 playlist.items 里选择下一张
-> openWallpaper(file)
```

算法重点：

- recent penalty
- failure penalty
- same-cluster penalty
- context-conditioned weight
- gap / temperature sampling

### 10.2 Playlist-First Wallpaper Rerank

一级仍然选 playlist，二级在 matched playlist 内 rerank wallpaper。

```text
Context -> PlaylistScore
Playlist -> WallpaperCandidates
Context + WallpaperMetadata -> WallpaperScore
```

playlist 是 hard constraint。wallpaper 只在目标 playlist 内排序。

### 10.3 Playlist as Prior

playlist 不再是 hard constraint，而是 prior。

```text
score(wallpaper) =
  playlist_score(playlist_of_wallpaper) * alpha
  + wallpaper_match_score * beta
  + state_penalties
```

优点是哲学上优雅，能平滑过渡到 wallpaper-base。缺点是边界会松，产品心智更接近推荐系统。

### 10.4 Cluster Scheduler

先把 wallpaper 聚类，再调度 cluster。

```text
wallpapers -> clusters
Context -> cluster
cluster -> wallpaper sample
```

cluster 可以降低候选复杂度，也有利于防重复和多样性控制。但它不能直接解决用户语义 gap。

### 10.5 User Preference Bias Layer

不训练大模型，只在 ranking 层维护个人偏置。

```text
score += user_bias(wallpaper, context_bucket)
score += cluster_bias(cluster, context_bucket)
score -= block_penalty
```

这是解决用户语义 gap 的后端层。

### 10.6 Anchor-Based Personalization

每个 context 由少量 anchor wallpaper 代表。运行时按“离 anchor 的相似度”排序。

```text
context -> anchors
wallpaper_score = max similarity to anchors
```

这个方向自然，但会引入额外交互，暂时可往后推。

## 11. 当前倾向

经过讨论，当前最有工程胜率的折中方向是：

> Playlist-Based Scheduler + Wallpaper-Aware Actuation

也可以称为：

> playlist-first / playlist-internal wallpaper rerank

它不是完整 wallpaper-base，也不是纯 playlist-base。

一级语义仍然是 playlist：

```text
Context -> Policy -> Matcher -> matched playlist
```

二级执行变得更聪明：

```text
matched playlist -> wallpaper candidates -> select wallpaper -> openWallpaper
```

核心原因：

- 用户语义 gap 先由 playlist 边界兜住。
- 不需要立即解决全库推荐。
- 不需要立即引入重模型。
- 不需要推翻现有 Config / Policy / Matcher / Diagnostics 主线。
- 失败时可以 fallback 到 `openPlaylist` 或 `nextWallpaper`。
- 可以逐步演进到 `Playlist as Prior`。

## 12. 推荐演进顺序

### Phase A: Playlist-Base Stable Release

先发布当前成熟主线，不把稳定成果和实验路线混在一起。

### Phase B: Wallpaper Identity / Inventory

建立后端事实层：

- 读取 WE playlist items。
- 读取 `project.json`。
- 建立 wallpaper identity。
- 读取当前 wallpaper。
- 记录 active playlist + active wallpaper。

这一步本身不改变调度行为。

### Phase C: Smart Cycle Only

只替换同 playlist 内 cycle 逻辑：

- 近期不重复。
- 失败路径 blacklist。
- 类型风险降权。
- metadata 简单加权。
- fallback 到 `nextWallpaper`。

### Phase D: Playlist-First Wallpaper Rerank

playlist switch 时也在目标 playlist 内选择具体 wallpaper，再 `openWallpaper`。

### Phase E: Playlist as Prior

等 playlist-internal 路线稳定后，再允许 soft boundary：

- 从相邻 playlist 借候选。
- 按 playlist score 作为 prior。
- 在低频探索 lane 中越界。

## 13. 非目标

近期不建议做：

- 完整 wallpaper-base pivot。
- 端到端 learned ranker。
- 大型 feedback / training UI。
- 通用 WE 管理器。
- 完整 Wallpaper Library 管理后台。
- 将模型作为 runtime 必需依赖。
- 直接写回 WE config 生成或修改 playlist。

## 14. 仍需验证的问题

- `openWallpaper -file` 后 WE `config.json` 中 selected wallpaper 的 `playlist` 字段是否保留。
- `getWallpaper` 与 `config.json` probing 哪个更适合作为当前 wallpaper 事实源。
- `openWallpaper` 打开 playlist item 后，`nextWallpaper` 的语义是否仍然可靠。
- per-monitor `location` 是否需要进入早期设计。
- web / application 类型是否应默认降权或禁用。
- `wproperties` 是否应作为推荐信号、属性应用信号，还是只用于 Diagnostics。
- wallpaper identity 应优先使用 path、workshopid、project directory，还是组合 key。
- 当前 state.json 是否需要迁移到 active playlist + active wallpaper。
- Diagnostics 是否只展示 current wallpaper，还是要展示候选 ranking。

## 15. 一句话结论

当前不建议放弃 playlist-base。更稳的路线是：

> 先发布 playlist-base stable，再在分支中推进 playlist-first wallpaper-aware scheduling。让 playlist 继续表达用户语义，让后端在 playlist 内部变聪明。等这个能力稳定后，再考虑 playlist as prior 和更完整的 wallpaper-base 推荐系统。
