# Wallpaper-Aware Cycle 短版实现说明

日期：2026-05-18

这是 `WALLPAPER_AWARE_CYCLE_IMPL_SPEC.md` 的短版阅读稿。完整规格负责存放数学细节、DTO、测试和任务拆分；这份只解释第一版到底要做什么。

## 1. 要解决的问题

现在调度器已经能判断“当前应该用哪个 playlist”。但当结果还是当前 playlist，只需要 cycle 时，实际换哪张 wallpaper 仍交给 Wallpaper Engine 的 `nextWallpaper()`。

这次要做的是：

```text
playlist 仍由现有调度器选择
只有同 playlist 内 cycle 时，改成由我们选择具体 wallpaper
```

成功路径：

```text
matched_playlist == active_playlist
controller 允许 cycle
-> rank 当前 playlist 内的 wallpapers
-> 从 top-k 里选一张
-> openWallpaper(selected path)
```

失败或不可用时回退：

```text
nextWallpaper()
```

## 2. 第一版只做什么

第一版只处理“当前 playlist 内换一张图”。

不做这些：

- 不接管 playlist switch，切 playlist 仍走 `openPlaylist()`。
- 不跨 playlist 选图。
- 不让 wallpaper bias 影响一级 playlist matching。
- 不做真实图文模型推理。
- 不新增公开 YAML 配置。
- 不改 Diagnostics 前端。
- 不写回 Wallpaper Engine `config.json`。

开关是内部实验环境变量：

```text
WESCHEDULER_EXPERIMENTAL_WALLPAPER_CYCLE=1
```

## 3. 核心思路

playlist 是硬边界。用户手写的 playlist vector 仍是语义中心，模型或缓存分数只能在这个中心附近做轻微扰动。

不要直接相信模型绝对分数。第一版只看：

```text
这张 wallpaper 在当前 playlist 内，
相对其它 wallpaper 更偏向哪些 tag？
```

所以 ranking 只在同一个 playlist 内比较，不把一个 playlist 里的 wallpaper 拿去和另一个 playlist 比。

## 4. 选图流程

输入：

- 当前 context vector
- 当前 playlist vector
- `data/wallpaper-bias.json`
- 当前 playlist 的 wallpaper 列表
- 最近出现过的 wallpaper 记录

流程：

```text
1. 取当前 playlist 内候选
2. 按 tag 计算 playlist 内相对排名
3. 用相对排名轻微扰动 playlist vector
4. 根据当前 context 打语义分
5. 对最近出现过的图扣分
6. 排序后只在 top-k 内采样
```

默认参数：

```text
beta = 0.2
top_k = min(5, candidate_count)
temperature = 0.2
recent_window = 20
recency_weight = 0.25
```

直觉：

- `beta` 低一点，避免模型抢走用户配置的主导权。
- `top_k` 让结果有变化，不永远选第一名。
- `recency_weight` 避免刚出现过的图反复出现。

## 5. 先做 POC

实现 runtime 接线前，必须验证 Wallpaper Engine CLI：

```text
openWallpaper(path)
getWallpaper
nextWallpaper
```

要确认：

- `openWallpaper(path)` 不破坏 selected playlist 状态。
- `openWallpaper(path)` 后再 `nextWallpaper()`，仍按当前 playlist 轮播。
- `.pkg`、`.mp4`、`.html` 都至少验证一个样本。

如果 POC 不稳定，就不要把 `openWallpaper()` 接进自动 cycle。

## 6. 主要文件

新增：

- `core/wallpaper_index.py`：从 WE `config.json` 建立 playlist -> wallpaper 索引，读取可用的 `project.json`。
- `core/wallpaper_ranker.py`：读取 bias cache，计算分数，做 recency penalty 和 top-k sampling。

修改：

- `utils/we_config.py`：增加读取 playlist items 的能力。
- `core/executor.py`：增加 `open_wallpaper(file_path)`。
- `core/actuator.py`：在 cycle 分支尝试 smart cycle，失败时 fallback。
- `core/scheduler.py`：根据环境变量构建 optional ranker。
- `core/diagnostics.py`：增加 wallpaper selection trace。
- `ui/dashboard_analysis.py`：把 trace 映射到 API DTO。

## 7. Runtime 行为

switch 分支不变：

```text
matched_playlist != active_playlist
-> openPlaylist(matched_playlist)
```

cycle 分支变成：

```text
ranker 可用
-> select wallpaper
-> openWallpaper(selected path)
-> 成功后记录 recency 和 trace
```

任意失败：

```text
fallback nextWallpaper()
```

ranker 构建失败、bias cache 缺失、候选不足、`openWallpaper()` 失败，都不能影响 scheduler 启动或正常 cycle。

## 8. Trace 必须能解释

第一版不做 UI，但 API trace 要能回答：

- 是否启用了 smart cycle？
- 候选数量是多少？
- 选中了哪张 wallpaper？
- top candidates 分数是多少？
- semantic score 和 recency penalty 分别是多少？
- 是否 fallback？
- fallback 原因是什么？

## 9. 实现顺序

1. POC：确认 `openWallpaper()` 行为安全。
2. `utils/we_config.py`：读 playlist items。
3. `core/wallpaper_index.py`：建立索引。
4. `core/wallpaper_ranker.py`：实现 ranking。
5. `core/executor.py` / `core/actuator.py`：接入 cycle 分支。
6. `core/scheduler.py`：按环境变量构建 ranker。
7. `core/diagnostics.py` / `ui/dashboard_analysis.py`：补 trace 和 DTO。
8. 跑相关 pytest。

## 10. 最该测什么

- `scan_playlist_names()` 旧行为不变。
- playlist item 顺序保留，playlist 内去重。
- off-support tag 不进入 ranking vector。
- 相同 raw score 产生 zero residual。
- 最近出现过的高分图会被 recency penalty 压下去。
- top-k sampling 只从 top-k 中选。
- 没有 ranker 时 cycle 仍走 `nextWallpaper()`。
- smart cycle 成功时调用 `open_wallpaper()`。
- `open_wallpaper()` 失败时 fallback 到 `nextWallpaper()`。
- switch 分支仍调用 `open_playlist()`。

## 11. 最大风险

最大风险是 WE CLI，不是 ranking：

```text
如果 openWallpaper() 会破坏 selected playlist 状态，
第一版就不能接入 runtime。
```

第二个风险是 bias 过强。第一版通过低 `beta`、playlist 内比较和 top-k/recency 控制它。

第三个风险是不可解释。所以 trace 必须把候选、分数和 fallback 原因带出来。

## 12. 第一版完成标准

第一版完成时应该满足：

- playlist switch 行为不变。
- 同 playlist cycle 可以由 scheduler 选具体 wallpaper。
- 所有失败情况都能回退到 `nextWallpaper()`。
- trace 能解释为什么选中、为什么 fallback。
- 不引入公开配置，不扩大产品面。
