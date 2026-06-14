# Wallpaper-Aware Cycle Spec

日期：2026-05-18

本文记录一个折中的后端演进方向：保留 `playlist-base` 作为一级调度主线，只在同 playlist 内的 wallpaper cycle 阶段引入 wallpaper-aware ranking。

## 1. 目标

在不放弃当前成熟 `playlist-base` 架构的前提下，让 `cycle_cooldown` 触发的“当前 playlist 内换一张壁纸”从 Wallpaper Engine 原生随机 / 顺序行为，升级为由调度器控制的 top-k wallpaper selection。

核心边界：

```text
Context / Policy / Matcher -> matched playlist
matched playlist == active playlist && cycle allowed
-> rank wallpapers inside this playlist
-> openWallpaper(selected file)
```

## 2. 非目标

近期不做：

- 不接管 playlist switch。`matched playlist != active playlist` 仍走现有 `openPlaylist`。
- 不做 full wallpaper-base scheduler。
- 不让 wallpaper bias 参与一级 playlist matching。
- 不做跨 playlist 候选池。
- 不做 cluster / similarity dedupe，只作为未来展望。
- 不做 Diagnostics UI 改版；一期只扩展后端 trace。
- 不把 WE config 健康检查做成核心产品能力。
- 不写回 WE config。
- 不把模型作为 runtime 必需依赖。

## 3. 当前事实

现有主线事实：

- 运行时配置仍以 playlist 为调度单元。
- `playlists.yaml` 中的 playlist vector 是用户手工定义的语义中心。
- Policy 输出 context vector，Matcher 在 playlist vectors 中选择 matched playlist。
- Controller 当前区分 playlist switch 与 wallpaper cycle。
- Actuator 当前在 cycle 分支调用 `WEExecutor.next_wallpaper()`。

WE config / project metadata 事实：

- 当前机器上的 WE `config.json` 有 10 个 playlist。
- 去重 playlist item 数量为 160。
- 160 个 item 都有 `project.json` 和 preview。
- wallpaper 类型大致为 `scene 130`、`video 24`、`web 5`、`application 1`。
- WE tag 只有 16 种，且 `156/160` 个 item 只有 1 个 WE tag。
- WE tag 主要集中在 `Anime`、`Landscape`、`Relaxing`、`Game`、`Nature`。
- `project.json` 的 `title` / `description` / `tags` / `properties` 可作为弱信号，但语义粒度不足，不应承担核心调度判断。
- `preview.gif` / `preview.jpg` 是后续模型 bias 的主要输入候选。

产品判断：

- 信任 WE config 作为 playlist items 的事实源。
- 不把空 playlist、重复 item、丢失 item 当成 ranking 主体问题。
- WE CLI 运行错误率预期较低，不做复杂 failure history。
- `openWallpaper` 失败时允许做简单 fallback。

## 4. 核心设计

一级调度保持不变：

```text
context_vector c
playlist_vector p_j
matched_playlist = argmax sim(c, p_j)
```

二级 cycle 只在当前 playlist 内工作：

```text
candidate_wallpapers = items(matched_playlist)
selected_wallpaper = sample_top_k(rank(candidate_wallpapers, c, p_matched))
```

这意味着 playlist 仍然是 hard boundary：

- playlist 表达用户语义边界。
- wallpaper ranking 只表达该 playlist 内的相对偏移。
- 模型 bias 只能在 playlist center 附近扰动，不得推翻 playlist 语义。

## 5. 数学模型

### 5.1 Playlist Vector as Center

手工 playlist vector 不只是“客观平均值”，更是用户给这个 playlist 定义的调度意图中心：

```text
p = manual_playlist_vector
```

单张 wallpaper 的语义不直接使用模型的绝对输出，而使用 playlist-local residual。

### 5.2 Raw Model Scores

离线模型对每张 wallpaper 产出当前 scheduler tag space 上的 raw score：

```text
a_i,t = model_score(wallpaper_i, tag_t)
```

其中 `a_i,t` 未经过充分校准，不能直接当成真实 tag weight。

### 5.3 Playlist-Local Percentile Residual

对同一个 playlist `P` 内的 wallpaper，按 tag 计算局部 percentile：

```text
r_i,t = percentile_rank(a_i,t among wallpapers in playlist P)
b_i,t = 2 * (r_i,t - 0.5)
```

于是：

```text
b_i,t in [-1, 1]
```

语义为：

> 这张 wallpaper 在当前 playlist 内，相对其他 wallpaper 更偏向 tag_t 还是更不偏向 tag_t。

这样避免依赖模型绝对分数校准。

### 5.4 Hard Support Mask

一期不允许模型把 off-support tag 引入主 ranking vector。

```text
support_t = 1 if p_t > 0 else 0
```

语义：

```text
playlist vector 定义用户语义边界；
模型 bias 只能在这个边界内移动 wallpaper 的相对位置。
```

这意味着 `p_t == 0` 的 tag 不参与 wallpaper vector，也不参与 cycle ranking。未来如果需要探索 off-support discovery，应作为单独实验字段进入 trace，而不是混入主向量。

### 5.5 Wallpaper Vector

单张 wallpaper 的实际 ranking vector 是以 playlist vector 为中心的乘法扰动：

```text
v_i,t = p_t * exp(beta * b_i,t)   if p_t > 0
v_i,t = 0                         if p_t == 0
```

其中：

- `beta` 控制模型 bias 强度。
- `b_i,t > 0` 表示该 wallpaper 在当前 playlist 内相对更偏向 tag `t`。
- `b_i,t < 0` 表示该 wallpaper 在当前 playlist 内相对更不偏向 tag `t`。
- 乘法扰动让强 playlist tag 获得更大的绝对偏置，这是刻意行为：用户声明的主语义应比弱语义更能影响 playlist 内选择。
- 一期不对 `v_i` 再做归一化。playlist 间 matching 需要归一化来降低用户配置心智负担；playlist 内候选共享同一个 center，`v_i` 的 norm 可以表达 wallpaper 相对 playlist center 的核心 / 边缘程度。

建议初始值：

```text
beta = 0.15 ~ 0.25
```

第一版用较低 `beta` 控制扰动幅度，不引入 clamp。若后续观察到某些 wallpaper 由于模型 bias 过强长期霸榜，再考虑增加 `scale_t = clamp(exp(beta * b_i,t), min_scale, max_scale)` 或 center-similarity guard。

### 5.6 Cycle Ranking Score

语义分：

```text
c_hat = normalize_positive(context_vector)
semantic_score_i = dot(c_hat, v_i)
```

这里 `c_hat` 只表达当前 context 的 tag 方向 / 比例，避免 context 总强度影响 top-k sampling 的 score scale。`v_i` 不归一化，因此保留 wallpaper 在 playlist center 附近的局部强弱。

最初阶段最终分：

```text
score_i =
  semantic_score_i
- recency_penalty_i
```

一期只要求：

- `semantic_score_i`
- minimal `recency_penalty_i`
- top-k sampling noise

`user_bias_i` 可保留为未来字段。

如果某个 wallpaper vector 在所有 active tag 上都支配另一个 vector，那么它会在纯语义排名中长期压制后者。这是可接受的：语义层认为前者更贴近当前 playlist / context。被压制样本是否仍有曝光机会，应由 recency penalty、top-k sampling 或未来 exploration 处理，而不是扭曲语义公式。

### 5.7 Top-K Sampling （可选）

先排序，再在 top-k 内采样：

```text
top = take_k(sort_by_score(candidates), k)
prob_i = softmax(score_i / temperature)
selected = sample(top, prob_i)
```

建议：

```text
k = min(5, candidate_count)
temperature = 0.15 ~ 0.30
```

第一版可以固定 temperature。后续再根据 playlist gap / wallpaper score gap 调整。

## 6. Offline Bias

一期的核心价值不是 recency，而是验证模型 bias 是否能让 playlist 内 cycle 明显优于 WE 原生随机。

离线 bias 约束：

- 只在离线索引或配置工具中生成。
- runtime 只读取缓存，不执行模型推理。
- bias 直接落到 scheduler tag space。
- 原始模型分数必须经过 playlist-local residual 后才进入 ranking。

可接受输入：

- `project.json` 的 `title`、`description`、WE tag。
- `preview.gif` / `preview.jpg`。
- video / scene 的关键帧提取作为未来增强。

缓存建议：

```text
data/wallpaper-index.json
data/wallpaper-bias.json
```

实际路径可在实现时根据现有 `utils.app_context.get_data_dir()` 决定。

## 7. Runtime 行为

### 7.1 Switch 分支

保持现状：

```text
if matched_playlist != active_playlist:
    openPlaylist(matched_playlist)
```

不在 switch 时选择具体 wallpaper。

### 7.2 Cycle 分支

新行为：

```text
if matched_playlist == active_playlist and cycle allowed:
    selected = wallpaper_ranker.select(
        playlist=active_playlist,
        context_vector=trace.match.resolved_context_vector,
    )
    openWallpaper(selected.path)
```

如果 ranker 不可用、没有 bias、没有 candidate 或 feature flag 关闭，则保持现有：

```text
nextWallpaper()
```

### 7.3 Fallback

只处理 `openWallpaper` 失败：

首选 fallback：

```text
nextWallpaper()
```

原因：

- 当前分支语义是 cycle，不是 playlist switch。
- `nextWallpaper` 最接近原有行为。
- 不需要复杂 failure history。

可选备用 fallback：

```text
openPlaylist(active_playlist)
```

但这比 `nextWallpaper` 更重，应后置评估。

## 8. POC 任务

实现前必须先验证 WE 行为：

1. 执行：

```powershell
wallpaper64.exe -control openWallpaper -file "<playlist item path>"
```

2. 观察 WE `config.json`：

- `selectedwallpapers.*.file` 是否更新为该 item。
- `selectedwallpapers.*.playlist.name` 是否仍保留。
- `playlist.items` 是否不变。

3. 执行：

```powershell
wallpaper64.exe -control getWallpaper
```

确认输出是否稳定指向当前 wallpaper。

4. 在 `openWallpaper` 后再执行：

```powershell
wallpaper64.exe -control nextWallpaper
```

确认 `nextWallpaper` 是否仍具有当前 playlist 内轮播语义。

POC 结果会决定 active wallpaper / active playlist factual state 如何设计。

## 9. Trace Contract

一期不做 Diagnostics UI，但必须在后端 trace 中保留可调试事实。

建议新增结构：

```python
@dataclass
class WallpaperSelectionTrace:
    mode: str                  # off | fallback_next_wallpaper | smart_cycle
    selected_path: str | None
    candidate_count: int
    top_candidates: list[WallpaperCandidateScore]
    fallback_used: bool = False
    fallback_reason: str | None = None

@dataclass
class WallpaperCandidateScore:
    path: str
    score: float
    semantic_score: float
    recency_penalty: float
```

挂载位置可以是：

```python
ActuationOutcome.wallpaper_selection
```

或作为 cycle-specific action details。具体实现时应优先保持 `SchedulerTickTrace` 的 Sense / Think / Act 结构清晰。

## 10. File Map

可能新增：

- `core/wallpaper_index.py`
  - 从 WE config 读取 playlist items。
  - 解析 `project.json`。
  - 产出 wallpaper identity / metadata。

- `core/wallpaper_ranker.py`
  - 读取 wallpaper bias。
  - 执行 playlist-local vector ranking。
  - top-k sampling。

- `core/wallpaper_bias.py`
  - 定义 bias 数据结构。
  - 执行 playlist-local percentile residual、hard support mask 和乘法 wallpaper vector 构造。
  - 具体是否独立成文件可在实现时决定。

可能修改：

- `core/executor.py`
  - 增加 `open_wallpaper(file_path: str) -> bool`。

- `core/actuator.py`
  - cycle 分支接入 wallpaper ranker。
  - `openWallpaper` 失败时 fallback 到 `nextWallpaper`。

- `core/diagnostics.py`
  - 增加 trace 数据结构。

- `core/scheduler.py`
  - 构建 runtime components 时注入 wallpaper index/ranker。
  - 维护 active wallpaper state 的最小字段。

- `utils/we_config.py`
  - POC 后决定是否扩展当前 wallpaper probing。

- `utils/runtime_config.py` / `utils/config_documents.py`
  - 后续如需正式配置开关再修改。
  - 一期实验可以先不进入正式 config contract。

- `tests/test_core_diagnostics.py`
  - cycle trace / fallback / ranking 边界。

可能不动：

- `ui/http_server.py`
- `frontend/`

一期不做 UI。

## 11. 配置策略

一期建议使用内部实验开关，不急于进入正式 6 文件 YAML 契约。

后续如果行为稳定，再考虑：

```yaml
scheduling:
  wallpaper_cycle: smart # off | next_wallpaper | smart
```

或独立文件 / 配置块：

```yaml
wallpapers:
  cycle:
    enabled: true
    mode: smart
    beta: 0.2
    top_k: 5
    temperature: 0.2
```

正式配置前需要确认这不是一次性实验。

## 12. Validation

POC 验证：

- 手动验证 `openWallpaper`、`getWallpaper`、`nextWallpaper` 互相作用。

单元测试：

- playlist-local percentile residual 不依赖模型绝对尺度。
- `v_i,t = p_t * exp(beta * b_i,t)` 在 support 内做乘法扰动。
- off-support tag 在主 wallpaper vector 和 ranking 中被 hard mask。
- 未归一化 `v_i` 保留核心 / 边缘样本的幅度差异。
- recency penalty 能让最近播放过的高分 wallpaper 暂时让位。
- top-k sampling 只从 top-k 候选中选择。
- ranker 不可用时回退 `nextWallpaper`。
- `openWallpaper` 失败时回退 `nextWallpaper`。

回归测试：

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

如触及 frontend 前端，再补：

```bash
cd frontend
npm run build
```

## 13. 风险

- `openWallpaper` 可能破坏 WE 对当前 playlist 的内部状态，需要 POC 验证。
- 模型 raw score 未校准，必须只作为 playlist-local residual 使用。
- `beta` 过大会让 cycle 行为接近 full wallpaper-base；一期用低 `beta`，必要时再加 scale clamp 或 center-similarity guard。
- 不归一化 `v_i` 会让某些语义强样本长期支配弱样本；一期通过 recency penalty 和 top-k sampling 控制曝光，而不是扭曲语义向量。
- 如果不记录 trace，ranking 行为很难调试。
- 如果过早暴露复杂配置，会把项目重新推向管理后台式体验。

## 14. 未来展望

后续可探索：

- 根据 playlist match gap / wallpaper score gap 动态调整 temperature。
- cluster-level recency，避免视觉相似 wallpaper 连续出现。
- 用户反馈 bias：skip / prefer / block / pin。
- switch 分支中接管 wallpaper 选择。
- playlist as prior：允许低频跨 playlist 探索。
- richer model bias：关键帧、caption、vision-language direct scoring。

## 15. 当前结论

当前建议推进的第一 slice 是：

> Cycle Only + Playlist-Centered Offline Bias + Top-K Sampling + Trace Only

它保留 playlist-base 的产品心智，不直接进入 full wallpaper-base；同时能验证 wallpaper-aware ranking 是否真的改善当前 playlist 内轮播体验。
