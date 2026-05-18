# Wallpaper-Aware Cycle 实现规格

日期：2026-05-18

本文把 wallpaper-aware cycle 从方向设计细化为第一轮可实施规格。它不是完整的 wallpaper-base scheduler；它保留 `playlist-base` 作为一级调度，只在 `matched_playlist == active_playlist` 且 controller 允许 cycle 时，用 playlist 内 wallpaper ranking 替代 Wallpaper Engine 原生随机 / 顺序 cycle。

第一 slice：

```text
Cycle Only + Playlist-Centered Cached Bias + Top-K Sampling + Backend Trace
```

## 1. 目标

让 `cycle_cooldown` 触发的“当前 playlist 内换一张 wallpaper”由调度器选择具体 wallpaper：

```text
Context / Policy / Matcher -> matched playlist
matched playlist == active playlist && cycle allowed
-> rank wallpapers inside this playlist
-> openWallpaper(selected file)
```

验收含义：

- playlist switch 行为不变。
- cycle 分支可以在同 playlist 内选择具体 wallpaper。
- ranker 不可用、缓存缺失、候选不足或执行失败时可以回退到当前 `nextWallpaper()` 行为。
- trace 中能看出候选、分数、是否 fallback 和 fallback 原因。

## 2. 非目标

近期不做：

- 不接管 playlist switch。`matched_playlist != active_playlist` 仍走 `openPlaylist`。
- 不做完整的 wallpaper-base scheduler。
- 不让 wallpaper bias 参与一级 playlist matching。
- 不做跨 playlist 候选池。
- 不做 cluster / similarity dedupe。
- 不做真实图文模型 pipeline。第一 slice 只消费缓存 bias。
- 不把模型作为 runtime 必需依赖。
- 不做 Diagnostics UI 改版；只扩展后端 trace / DTO。
- 不写回 WE `config.json`。
- 不把 WE config 健康检查扩展成核心产品能力。
- 不进入正式 6 文件 YAML 配置契约；第一 slice 用内部实验开关。

## 3. 当前事实

现有主线事实：

- 运行时配置仍以 playlist 为调度单元。
- `playlists.yaml` 中的 playlist vector 是用户手工定义的语义中心。
- Policy 输出 context vector，Matcher 在 playlist vectors 中选择 matched playlist。
- Controller 当前区分 playlist switch 与 wallpaper cycle。
- Actuator 当前在 cycle 分支调用 `WEExecutor.next_wallpaper()`。
- Dashboard / Diagnostics 的事实源是 `SchedulerTickTrace`，不是长期 History 产品。

WE config / project metadata 事实：

- 当前机器上的 WE `config.json` 有 10 个 playlist。
- 去重 playlist item 数量为 160。
- 160 个 item 都有 `project.json` 和 preview。
- wallpaper 类型大致为 `scene 130`、`video 24`、`web 5`、`application 1`。
- WE tag 只有 16 种，且 `156/160` 个 item 只有 1 个 WE tag。
- WE tag 主要集中在 `Anime`、`Landscape`、`Relaxing`、`Game`、`Nature`。
- `project.json` 的 `title` / `description` / `tags` / `properties` 可作为弱信号，但语义粒度不足，不承担核心调度判断。
- `preview.gif` / `preview.jpg` 是后续模型 bias 的主要输入候选。

## 4. POC 门禁

实现 runtime 接线前必须先手动验证 WE CLI 行为。POC 结果写入本文件或相邻 POC notes 后再进入实现。

### 4.1 命令

选择一个当前 active playlist 内的 item：

```powershell
E:\SteamLibrary\steamapps\common\wallpaper_engine\wallpaper64.exe -control openWallpaper -file "<playlist item path>"
```

然后执行：

```powershell
E:\SteamLibrary\steamapps\common\wallpaper_engine\wallpaper64.exe -control getWallpaper
```

再执行：

```powershell
E:\SteamLibrary\steamapps\common\wallpaper_engine\wallpaper64.exe -control nextWallpaper
```

### 4.2 观察项

必须记录：

- `selectedwallpapers.*.file` 是否更新为 `openWallpaper` 的 item。
- `selectedwallpapers.*.playlist.name` 是否仍保留当前 playlist。
- `playlist.items` 是否保持不变。
- `getWallpaper` 是否稳定输出当前 wallpaper path。
- `openWallpaper` 后的 `nextWallpaper` 是否仍按当前 playlist 轮播。
- `.pkg`、`.mp4`、`.html` 至少各验证一个样本；`.exe` 可后置。

### 4.3 POC 决策

如果 `openWallpaper` 后 playlist 状态仍稳定：

- 第一 slice 使用 `openWallpaper(selected.path)` 执行 smart cycle。
- `nextWallpaper()` 作为 unavailable / failed fallback。

如果 `openWallpaper` 破坏 playlist 状态：

- 暂停 runtime 接线。
- 先重写 factual playlist / active wallpaper state 设计。
- 不把 `openWallpaper` 接进自动 cycle。

## 5. 运行时设计

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

playlist 是 hard boundary：

- playlist 表达用户语义边界。
- wallpaper ranking 只表达该 playlist 内的相对偏移。
- 模型 bias 只能在 playlist center 附近扰动，不得推翻 playlist 语义。

## 6. 数学契约

### 6.1 将 Playlist Vector 作为中心

手工 playlist vector 是用户给 playlist 定义的调度意图中心：

```text
p = manual_playlist_vector
```

单张 wallpaper 不直接使用模型绝对输出，而使用 playlist-local residual。

### 6.2 原始模型分数

离线模型或手工 fixture 对每张 wallpaper 产出当前 scheduler tag space 上的 raw score：

```text
a_i,t = model_score(wallpaper_i, tag_t)
```

`a_i,t` 未经过充分校准，不能直接当成真实 tag weight。

### 6.3 Playlist 内局部百分位残差

对同一个 playlist `P` 内的 wallpaper，按 tag 计算局部 percentile：

```text
r_i,t = percentile_rank(a_i,t among wallpapers in playlist P)
b_i,t = 2 * (r_i,t - 0.5)
```

于是：

```text
b_i,t in [-1, 1]
```

实现细节：

- `candidate_count < 2` 时，该 playlist 不做 semantic ranking，回退 `nextWallpaper()`。
- 某 tag 的可用 raw score 数量 `< 2` 时，该 tag 的 residual 全部视为 `0.0`。
- ties 使用 average rank。
- 若某 tag 所有 raw score 相同，residual 全部为 `0.0`。
- 缺失 raw score 不当成 `0.0`；该 wallpaper 在该 tag 上不参与 percentile。

语义：

> 这张 wallpaper 在当前 playlist 内，相对其他 wallpaper 更偏向 tag_t 还是更不偏向 tag_t。

### 6.4 硬支持掩码

一期不允许模型把 off-support tag 引入主 ranking vector：

```text
support_t = 1 if p_t > 0 else 0
```

`p_t == 0` 的 tag 不参与 wallpaper vector，也不参与 cycle ranking。未来如果需要探索 off-support discovery，应作为单独实验字段进入 trace，而不是混入主向量。

### 6.5 以中心扰动得到的 Wallpaper Vector

单张 wallpaper 的 ranking vector 是以 playlist vector 为中心的乘法扰动：

```text
v_i,t = p_t * exp(beta * b_i,t)   if p_t > 0
v_i,t = 0                         if p_t == 0
```

其中：

- `beta` 控制模型 bias 强度。
- `b_i,t > 0` 表示该 wallpaper 在当前 playlist 内相对更偏向 tag `t`。
- `b_i,t < 0` 表示该 wallpaper 在当前 playlist 内相对更不偏向 tag `t`。
- 乘法扰动让强 playlist tag 获得更大的绝对偏置，这是刻意行为：用户声明的主语义应比弱语义更能影响 playlist 内选择。
- 一期不对 `v_i` 再做归一化。playlist 间 matching 需要归一化来降低用户配置心智负担；playlist 内候选共享同一个 center，`v_i` 的 norm 表达 wallpaper 相对 playlist center 的核心 / 边缘程度。

第一 slice 默认：

```text
beta = 0.2
```

允许实现常量：

```text
MIN_BETA = 0.0
MAX_BETA = 0.5
```

第一 slice 不引入 clamp。若后续观察到某些 wallpaper 因模型 bias 过强长期霸榜，再考虑：

```text
scale_t = clamp(exp(beta * b_i,t), min_scale, max_scale)
```

或 center-similarity guard。

### 6.6 Cycle 排名分数

语义分：

```text
c_hat = normalize_positive(context_vector)
semantic_score_i = dot(c_hat, v_i)
```

`normalize_positive` 定义：

```text
positive_t = max(context_vector_t, 0)
c_hat = positive / l2_norm(positive)
```

如果 `context_vector` 没有正向 tag，fallback：

```text
c_hat = normalize_positive(p)
```

最终分：

```text
score_i =
  semantic_score_i
- recency_penalty_i
```

被支配样本说明：

- 如果某个 wallpaper vector 在所有 active tag 上都支配另一个 vector，它会在纯语义排名中长期压制后者。
- 这是可接受的：语义层认为前者更贴近当前 playlist / context。
- 被压制样本是否仍有曝光机会，由 recency penalty、top-k sampling 或未来 exploration 处理。

### 6.7 近期惩罚

第一 slice 使用 in-memory recency，不持久化到 `state.json`。

第一 slice 实现：

```text
recent_paths = deque(maxlen=20)
```

若 path 最近出现过：

```text
age_rank = 0 for most recent, 1 for previous, ...
recency_penalty = recency_weight * (1 - age_rank / recent_window)
```

否则：

```text
recency_penalty = 0
```

默认：

```text
recent_window = 20
recency_weight = 0.25
```

只有成功执行 primary `openWallpaper` 或 fallback `nextWallpaper` 后才更新 recency；如果 primary 失败且 fallback 也失败，不更新。

### 6.8 Top-K 采样

先排序，再在 top-k 内采样：

```text
top = take_k(sort_by_score(candidates), k)
prob_i = softmax(score_i / temperature)
selected = sample(top, prob_i)
```

默认：

```text
k = min(5, candidate_count)
temperature = 0.2
```

实现约束：

- `temperature <= 0` 时退化为 top-1。
- ranker 接收可注入 RNG，测试中使用固定 seed。
- trace 记录排序后的 top candidates，不记录全量候选。

## 7. 数据契约

### 7.1 Wallpaper 索引

新增 `core/wallpaper_index.py`。

核心 dataclasses：

```python
@dataclass(frozen=True)
class WallpaperMetadata:
    path: str
    project_json: str | None
    project_dir: str | None
    file_name: str
    wallpaper_type: str
    title: str
    description: str
    we_tags: tuple[str, ...]
    preview_path: str | None
    workshop_id: str | None

@dataclass(frozen=True)
class PlaylistWallpaperIndex:
    playlist_items: dict[str, tuple[str, ...]]
    wallpapers: dict[str, WallpaperMetadata]
```

路径规则：

- 使用归一化后的绝对路径字符串作为 key。
- 接受带 `/` 的 WE config path；只在文件系统边界归一化为当前 OS 的路径分隔符。
- 如果 POC 显示 WE 接受任一形式，则保留原始 path string 给 CLI；否则单独存储 `cli_path`。

索引构建器行为：

- 从 WE `config.json` 读取 playlist names 和 item paths。
- 限制在 runtime config 管理的 playlists 内。
- 保留 WE config 中的 item 顺序。
- 在一个 playlist 内去重 items，并保留第一次出现的位置。
- 一个 wallpaper 可以属于多个 playlists。
- 第一 slice 中排除缺失的 item paths，并将其计为 trace/logging 用的 index issues。
- 允许缺失 `project.json`；metadata fields fallback 到 empty / unknown。

### 7.2 WE Config Reader 扩展

修改 `utils/we_config.py`。

新增公开 dataclasses：

```python
@dataclass(frozen=True)
class WEPlaylistDefinition:
    name: str
    items: tuple[str, ...]
    settings: dict[str, object]
```

新增公开方法：

```python
def scan_playlists(self) -> list[WEPlaylistDefinition]:
    """从 WE config 返回 playlist names、item paths 和 settings。

    Raises:
        WEConfigReadError: 当 config.json 缺失、不可读或不是 JSON object 时。
    """
```

现有 `scan_playlist_names()` 可以委托给 `scan_playlists()`。

不要把 private `_load_config()` 暴露到 `utils/we_config.py` 之外。

### 7.3 Bias 缓存

第一 slice 消费一个 cache file。它不生成 model scores。

默认路径：

```text
data/wallpaper-bias.json
```

JSON 形状：

```json
{
  "version": 1,
  "tag_space": ["focus", "chill", "day", "night"],
  "source": {
    "kind": "fixture",
    "generated_at": "2026-05-18T00:00:00+00:00"
  },
  "wallpapers": {
    "E:/SteamLibrary/steamapps/workshop/content/431960/123/scene.pkg": {
      "scores": {
        "focus": 0.12,
        "chill": 0.78,
        "night": 0.64
      }
    }
  }
}
```

规则：

- `version` 必须为 `1`。
- Unknown tags 会被忽略，除非它们存在于 runtime `config.tags`。
- Scores 是 raw model / fixture scores，不是校准后的 tag weights。
- 缺失 wallpaper scores 表示该 wallpaper 仍可保留为 candidate，但所有 tag 的 residual 都为 `0.0`。
- Cache load failure 会禁用 smart cycle 并回退到 `nextWallpaper()`；它不会导致 scheduler startup 失败。

### 7.4 Ranker API

新增 `core/wallpaper_ranker.py`。

核心 dataclasses：

```python
@dataclass(frozen=True)
class WallpaperCandidateScore:
    path: str
    score: float
    semantic_score: float
    recency_penalty: float
    vector: dict[str, float]
    residual: dict[str, float]

@dataclass(frozen=True)
class WallpaperSelection:
    selected_path: str | None
    mode: str
    candidate_count: int
    top_candidates: tuple[WallpaperCandidateScore, ...]
    fallback_reason: str | None = None
```

Ranker class：

```python
class WallpaperRanker:
    def select(
        self,
        *,
        playlist: str,
        playlist_vector: dict[str, float],
        context_vector: dict[str, float],
        now: float,
    ) -> WallpaperSelection:
        ...
```

Mode 取值：

- `disabled`
- `missing_index`
- `missing_bias`
- `no_playlist_items`
- `insufficient_candidates`
- `smart_cycle`

实现说明：

- Constructor 接收 `PlaylistWallpaperIndex`、bias cache、`beta`、`top_k`、`temperature`、RNG。
- `select()` 除读取 in-memory recency 用于 penalty 外，没有副作用。
- 增加 `record_success(path: str)`，在成功执行后更新 recency。
- 不要在 `select()` 内更新 recency，因为执行可能失败。

### 7.5 Trace 契约

修改 `core/diagnostics.py`。

新增：

```python
@dataclass
class WallpaperCandidateTrace:
    path: str
    score: float
    semantic_score: float
    recency_penalty: float
    vector: dict[str, float] = field(default_factory=dict)
    residual: dict[str, float] = field(default_factory=dict)

@dataclass
class WallpaperSelectionTrace:
    mode: str = "off"
    selected_path: str | None = None
    candidate_count: int = 0
    top_candidates: list[WallpaperCandidateTrace] = field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str | None = None
```

扩展：

```python
@dataclass
class ActuationOutcome:
    ...
    wallpaper_selection: WallpaperSelectionTrace | None = None
```

`ui/dashboard_analysis.py` 中的 DTO mapping 将其包含在 `act.wallpaperSelection` 下。第一 slice 通过 API 暴露它，但不渲染专门的前端 UI。

### 7.6 History 事件数据

现有 event type 保持为 `wallpaper_cycle`。

当 smart cycle 成功时，追加可选字段：

```json
{
  "playlist": "NIGHT_CHILL",
  "wallpaper_path": "E:/...",
  "selection_mode": "smart_cycle",
  "tags": {},
  "reason_code": "cycle_allowed"
}
```

当 fallback `nextWallpaper()` 成功时：

```json
{
  "playlist": "NIGHT_CHILL",
  "selection_mode": "fallback_next_wallpaper",
  "fallback_reason": "open_wallpaper_failed"
}
```

第一 slice 不新增 event type。

## 8. 运行时流程

### 8.1 启动 / 运行时构建

修改 `core/scheduler.py` 中的 `_RuntimeComponents`：

```python
wallpaper_ranker: WallpaperRanker | None
```

构建行为：

1. 像今天一样构造 existing executor/context/matcher/controller/actuator。
2. 如果 internal experiment flag 关闭，设置 `wallpaper_ranker=None`。
3. 如果 flag 开启：
   - 使用 `WEConfigProber.scan_playlists()` 构建 `PlaylistWallpaperIndex`；
   - 加载 `data/wallpaper-bias.json`；
   - 构造 `WallpaperRanker`；
   - 如果任一步失败，记录 warning 并设置 `wallpaper_ranker=None`。
4. 将 ranker 注入 `Actuator`。

内部实验开关：

```text
WESCHEDULER_EXPERIMENTAL_WALLPAPER_CYCLE=1
```

这不是公开配置契约。

### 8.2 Switch 分支

不变：

```text
if matched_playlist != active_playlist:
    openPlaylist(matched_playlist)
```

switch 时不要选择具体 wallpaper。

### 8.3 Cycle 分支

在 `Actuator._act_from_decision()` 中：

```text
if decision.kind == CYCLE:
    if ranker is available:
        selection = ranker.select(...)
        if selection.selected_path:
            if executor.open_wallpaper(selection.selected_path):
                ranker.record_success(selection.selected_path)
                notify_wallpaper_cycle()
                executed = True
            else:
                fallback nextWallpaper()
        else:
            fallback nextWallpaper()
    else:
        nextWallpaper()
```

Fallback 行为：

- 如果 ranker unavailable / no selection：fallback reason 是 ranker mode。
- 如果 `open_wallpaper()` 返回 false：fallback reason 是 `open_wallpaper_failed`。
- 如果 fallback `nextWallpaper()` 成功，`executed=True`、`fallback_used=True`；除非能从 `getWallpaper` 可靠读取当前 wallpaper path，否则不调用 `ranker.record_success()`。
- 如果 fallback 也失败，`executed=False` 并走现有 `actuation_failed` 路径。

### 8.4 手动应用

Manual apply 当前会绕过 gates 来选择 switch vs cycle。

第一 slice 行为：

- 如果 manual apply 解析为 cycle 且 experiment flag 开启，可以使用 smart cycle。
- 这是可接受的，因为 manual apply 本来就请求基于当前 context 立即调度。
- Trace 仍必须记录 `reason_code=manual_apply_requested`。

### 8.5 Hot Reload

第一 slice 行为：

- Config reload 重建 runtime components。
- Wallpaper ranker 从当前 WE config 和 bias cache 重建。
- Recency memory 不跨 reload 迁移。
- ranker 重建失败不应拒绝 config reload。

## 9. 文件地图

### 9.1 新文件

`core/wallpaper_index.py`

- 拥有 `WallpaperMetadata`、`PlaylistWallpaperIndex`。
- 从 `WEPlaylistDefinition` 构建 managed playlist item index。
- 读取可选的 `project.json`。
- 不执行 WE CLI。
- 不写文件。

`core/wallpaper_ranker.py`

- 拥有 `WallpaperBiasCache`、`WallpaperRanker`、`WallpaperSelection`、`WallpaperCandidateScore`。
- 加载并验证 `data/wallpaper-bias.json`。
- 计算 percentile residual、centered wallpaper vectors、scores、recency penalty、top-k sampling。
- 通过注入 RNG 获得确定性测试。

### 9.2 修改文件

`utils/we_config.py`

- 增加 `WEPlaylistDefinition`。
- 增加 `scan_playlists()`。
- 保持 `scan_playlist_names()` 行为兼容。

`core/executor.py`

- 增加：

```python
def open_wallpaper(self, file_path: str) -> bool:
    return self._run_command(["openWallpaper", "-file", file_path])
```

- POC 后可选增加：

```python
def get_wallpaper(self) -> str | None:
    ...
```

`core/diagnostics.py`

- 增加 wallpaper selection trace dataclasses。
- 扩展 `ActuationOutcome`。

`core/actuator.py`

- 接收 `wallpaper_ranker: WallpaperRanker | None = None`。
- 只在 cycle 分支使用 ranker。
- Fallback 到 `nextWallpaper()`。
- 写入扩展后的 `wallpaper_cycle` event data。

`core/scheduler.py`

- 向 `_RuntimeComponents` 增加 `wallpaper_ranker`。
- 在 env flag 下构建可选 ranker。
- 将 ranker 注入 `Actuator`。

`ui/dashboard_analysis.py`

- 增加 wallpaper selection trace 的 DTO。
- 映射 `ActuationOutcome.wallpaper_selection`。
- 不需要 UI 变化。

`tests/test_we_config.py`

- 覆盖 playlist item extraction 和 `scan_playlist_names()` 的兼容性。

`tests/test_core_diagnostics.py`

- 覆盖 actuator smart cycle success / fallback trace。

新的聚焦测试：

- `tests/test_wallpaper_index.py`
- `tests/test_wallpaper_ranker.py`

### 9.3 第一 slice 中不变

- `dashboard/src/**`
- `ui/dashboard.py`
- `utils/runtime_config.py`
- `utils/config_documents.py`
- Release config examples。

## 10. 实现任务

### Task 0：POC 记录

文件：

- `docs/half-finished/WALLPAPER_AWARE_CYCLE_SPEC.md`
- optional `docs/half-finished/WALLPAPER_AWARE_CYCLE_POC.md`

行为：

- 运行第 4 节中的命令。
- 记录 pass/fail 和 decision。

验证：

- 手动证据：观察到的 `config.json`、`getWallpaper`、`nextWallpaper`。

依赖：

- 无。

### Task 1：WE Playlist 清单

文件：

- `utils/we_config.py`
- `tests/test_we_config.py`

行为：

- 增加 `WEPlaylistDefinition`。
- 增加 `scan_playlists()`。
- 让 `scan_playlist_names()` 委托给 `scan_playlists()`。
- 忽略 malformed playlist entries；保留 valid names 和 items。

验证：

```bash
.\venv313\Scripts\python.exe -m pytest tests/test_we_config.py -q
```

依赖：

- Task 0 POC 可以提前或并行执行；本任务不改变 runtime behavior。

### Task 2：Wallpaper 索引

文件：

- `core/wallpaper_index.py`
- `tests/test_wallpaper_index.py`

行为：

- 从 managed playlists 和 `WEPlaylistDefinition` 构建 `PlaylistWallpaperIndex`。
- 归一化 path keys。
- 存在 `project.json` 时解析它。
- 保留 playlist item order，并在 playlist 内去重。

验证：

```bash
.\venv313\Scripts\python.exe -m pytest tests/test_wallpaper_index.py -q
```

依赖：

- Task 1。

### Task 3：Bias 缓存与 Ranker

文件：

- `core/wallpaper_ranker.py`
- `tests/test_wallpaper_ranker.py`

行为：

- 加载 `data/wallpaper-bias.json` version 1。
- 安全忽略 unknown tags 和 missing scores。
- 计算 playlist-local percentile residual，并处理 tie。
- 计算 `v_i,t = p_t * exp(beta * b_i,t)`。
- 计算 `semantic_score_i = dot(c_hat, v_i)`。
- 应用 recency penalty。
- 使用 injectable RNG 进行 top-k sample。
- 返回 `WallpaperSelection`。

验证：

```bash
.\venv313\Scripts\python.exe -m pytest tests/test_wallpaper_ranker.py -q
```

必需测试：

- Raw score affine scaling 不改变 percentile residual ordering。
- Off-support raw score 永远不进入 `v_i`。
- Equal raw scores 产生 zero residual。
- Unnormalized vector 让 all-positive residual sample 保持更大 norm。
- Recent high-score item 可以被 recency penalty 挤下去。
- Sampling 只从 top-k 中选择。

依赖：

- Task 2。

### Task 4：Executor 与 Actuator 接线

文件：

- `core/executor.py`
- `core/actuator.py`
- `tests/test_core_diagnostics.py`

行为：

- 增加 `WEExecutor.open_wallpaper()`。
- 向 `Actuator` 注入 optional `WallpaperRanker`。
- 仅当 decision kind 为 `CYCLE` 时使用 smart cycle。
- 在 ranker unavailable、no selection 或 `openWallpaper` 失败时 fallback 到 `nextWallpaper()`。
- 保持现有 switch behavior。
- 保持现有 controller notification semantics：只有 primary 或 fallback side effect 成功后才 notify cycle。

验证：

```bash
.\venv313\Scripts\python.exe -m pytest tests/test_core_diagnostics.py -q
```

必需测试：

- Switch branch 仍调用 `open_playlist`。
- Cycle without ranker 仍调用 `next_wallpaper`。
- Smart cycle success 调用 `open_wallpaper` 并记录 trace。
- Smart cycle primary failure 调用 `next_wallpaper` fallback。
- Primary 和 fallback failure 写入 actuation failed。

依赖：

- Task 3。

### Task 5：Scheduler 运行时构建

文件：

- `core/scheduler.py`
- `tests/test_core_diagnostics.py`

行为：

- 向 `_RuntimeComponents` 增加 optional `wallpaper_ranker`。
- 仅在 `WESCHEDULER_EXPERIMENTAL_WALLPAPER_CYCLE=1` 时构建 ranker。
- Ranker build failure 记录 warning 并禁用 smart cycle；它不导致 scheduler initialization 或 config reload 失败。
- Hot reload 重建 ranker，且不迁移 recency。

验证：

```bash
.\venv313\Scripts\python.exe -m pytest tests/test_core_diagnostics.py -q
```

依赖：

- Task 4。

### Task 6：Trace 与 API DTO

文件：

- `core/diagnostics.py`
- `ui/dashboard_analysis.py`
- `tests/test_dashboard_api.py`
- `tests/test_core_diagnostics.py`

行为：

- 增加 wallpaper selection trace dataclasses。
- 扩展 `ActuationOutcome`。
- 将 trace 映射进 `TickSnapshot`。
- 如果 field absent 或 null，保持 frontend compatible。

验证：

```bash
.\venv313\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_core_diagnostics.py -q
```

依赖：

- Task 4 可先于 DTO mapping 进行；最终 trace validation 依赖两者。

### Task 7：端到端后端回归

文件：

- 所有 touched backend files。

行为：

- 确认没有 unrelated Dashboard / config editor behavior changes。

验证：

```bash
.\venv313\Scripts\python.exe -m pytest -q
```

如果 dashboard TypeScript types 被修改：

```bash
cd dashboard
npm run type-check
npm run build-only
```

依赖：

- Tasks 1-6。

## 11. 发布与配置策略

第一 slice 使用 internal env flag：

```text
WESCHEDULER_EXPERIMENTAL_WALLPAPER_CYCLE=1
```

第一 slice 不新增 public YAML fields。

如果行为证明稳定，后续 public config 可以是：

```yaml
wallpapers:
  cycle:
    enabled: true
    mode: smart
    beta: 0.2
    top_k: 5
    temperature: 0.2
    recency_window: 20
    recency_weight: 0.25
```

公开配置需要单独更新 spec，因为它会改变固定 6-file YAML contract。

## 12. 验证矩阵

POC：

- 手动 `openWallpaper` / `getWallpaper` / `nextWallpaper` 交互。

单元：

- `tests/test_we_config.py`
- `tests/test_wallpaper_index.py`
- `tests/test_wallpaper_ranker.py`
- focused `tests/test_core_diagnostics.py`
- focused `tests/test_dashboard_api.py`

回归：

```bash
.\venv313\Scripts\python.exe -m pytest -q
```

手动运行时冒烟：

```powershell
$env:WESCHEDULER_EXPERIMENTAL_WALLPAPER_CYCLE="1"
.\venv313\Scripts\python.exe main.py --no-tray
```

手动冒烟预期：

- 即使 `data/wallpaper-bias.json` 缺失，startup 也成功；
- 当 bias 存在且 active playlist 有候选时，cycle trace 报告 `smart_cycle`；
- `openWallpaper` 失败时 fallback 到 `nextWallpaper`；
- switch 分支仍使用 playlist switch。

## 13. 风险

- `openWallpaper` 可能破坏 WE 的 selected playlist state。如果发生，POC gate 会阻止 runtime work。
- Model raw scores 未校准；只有 playlist-local residual 可以进入 ranking。
- `beta` 过高会让 cycle 行为接近完整 wallpaper-base。第一 slice 使用较低默认值，且不开放 public config。
- 未归一化的 `v_i` 会让强语义样本占优。第一 slice 用 recency penalty 和 top-k sampling 控制曝光，而不是扭曲向量。
- Bias cache load failure 绝不能破坏 scheduler startup 或 hot reload。
- 如果 trace 过薄，ranking 会很难调试；top candidates 必须包含 score components。
- 过早引入 public config 会把产品重新拉向 management-dashboard complexity。

## 14. 开放问题

实现前真正的 blocker：

- POC：`openWallpaper` 是否保留 selected playlist state 和 `nextWallpaper` semantics？
- POC：`openWallpaper` 后，`getWallpaper` 是否会为 `.pkg`、`.mp4` 和 `.html` 返回 stable paths？

非阻塞 follow-ups：

- fallback 成功时是否通过 `getWallpaper` 记录当前 wallpaper path。
- recency 是否跨重启持久化。
- 模型发现的 off-support tags 是否值得一个 separate trace-only channel。
- 未来 config 属于 `scheduling.yaml` 还是新的 `wallpapers` block。

## 15. 未来工作

- 基于 preview / keyframes 的离线 model bias generator。
- Cluster-level recency，避免视觉相近的 wallpaper 连续出现。
- User feedback bias：skip / prefer / block / pin。
- playlist switch 后在 switch 分支选择具体 wallpaper。
- 以 playlist 作为 prior 的 cross-playlist exploration。
- wallpaper-aware cycle trace 的 Diagnostics UI。

## 16. 实现规模估算

第一 slice 估算：

- 8-14 commits。
- 12-25 files。
- `+1200` 到 `+2500` lines，`-200` 到 `-600` lines。
- 如果 WE POC 干净，需要 3-6 个聚焦工作日。
- 如果 POC 和 trace 细节需要迭代，需要 1-2 周。

如果包含真实 model inference / bias generation，应把它视为单独 milestone。
