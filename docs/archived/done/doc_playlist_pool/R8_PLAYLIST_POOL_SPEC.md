# R8 — Multi-Playlist Matching

## 目标

将 Matcher 从输出单一 `best_playlist: str | None` 改为输出 `best_playlists: list[str]`。
当多个 playlist 的 cosine 相似度落入同一簇时，它们共同构成当前 context 的最佳匹配。

## 核心范式

playlists 是一等公民。整条管线（Matcher → Controller → Scheduler）中 playlist 都是 `list[str]`。
单个 playlist 的概念只存在于 Actuator 的执行层——从 list 中选 target，执行 `openPlaylist` 或 `nextWallpaper`。

---

## 1. 常量（Matcher 内部，不暴露为配置项）

```python
CLUSTER_GAP_THRESHOLD = 0.02   # 相邻 score gap 超过此值时断开聚类
MAX_CLUSTER_SIZE = 4           # best_playlists 最大长度
```

## 2. PlaylistConfig 扩展

`utils/runtime_config.py` — `PlaylistConfig` 新增字段：

```python
item_count: int = 0   # 壁纸数量，用于执行层加权选择。0 = 未知（退化为 uniform）
```

来源：WE config.json playlist items 扫描。初始化时填充，热重载时刷新。
扫描失败时降级为 0。

## 3. MatchEvaluation 变更

`core/diagnostics.py`：

```python
@dataclass
class MatchEvaluation:
    best_playlists: list[str]                          # 替代 best_playlist
    playlist_matches: list[tuple[str, float]] = ...    # 保留，全量排名（score desc）
    scores: dict[str, float] = ...                     # best_playlists 中每个的 score
    raw_context_vector: dict[str, float] = ...
    resolved_context_vector: dict[str, float] = ...
    fallback_expansions: dict[str, dict[str, float]] = ...
    policy_evaluations: list[PolicyEvaluation] = ...
    max_policy_magnitude: float = 0.0

    @property
    def similarity(self) -> float:
        """best_playlists 的壁纸数加权平均 score。空时返回 0。"""

    @property
    def similarity_gap(self) -> float:
        """top-1 与 top-2 的 score 差。不足 2 个时返回 top-1 score。
        注意：这不是内部 gap，是全局 top-2 gap。"""
```

`best_playlists` 为空 list 等价于旧 `best_playlist = None`。

## 4. Matcher 聚类逻辑

`core/matcher.py` — `evaluate()` 末尾：

```
scores = [(sim, name), ...] 按 sim 降序
best = []
for i, (score, name) in enumerate(scores):
    if score < _MIN_SIMILARITY: break
    if i >= MAX_CLUSTER_SIZE: break
    if i > 0 and scores[i-1][0] - score > CLUSTER_GAP_THRESHOLD: break
    best.append(name)
```

当一二名 gap 大于阈值时 best 长度为 1，退化为现有行为。
`best_playlists` 为空 list 时 `scores` 也为空 dict。

## 5. ControllerDecision 变更

`core/diagnostics.py`：

```python
@dataclass
class ControllerDecision:
    kind: ActionKind
    reason_code: ActionReasonCode
    matched_playlists: list[str]       # 替代 matched_playlist
    evaluation: ControllerEvaluation | None = None
```

Controller 只决定 SWITCH/CYCLE/HOLD，不选择 target。target 选择是 Actuator 的职责。

## 6. active_playlists 全链路

`active_playlist: str` → `active_playlists: list[str]`。涉及：

| 层                         | 类型变更                                                                               |
| -------------------------- | -------------------------------------------------------------------------------------- |
| `PlaylistStateResolution`  | `effective_playlist: str` → `effective_playlists: list[str]`                           |
| `Controller.decide_action` | `active_playlist: str` → `active_playlists: list[str]`                                 |
| `Actuator.act`             | `effective_playlist: str` → `effective_playlists: list[str]`                           |
| `ActuationOutcome`         | `effective_playlist_before/after: str` → `effective_playlists_before/after: list[str]` |
| `SchedulerState`           | `cached_playlist: str` → `cached_playlists: list[str]`                                 |

WE factual state 是单 playlist，`resolve_playlist_state` 内部完成包装。

## 7. Controller 逻辑

`core/controller.py` — Controller 无状态，纯函数式判断。

```python
def decide_action(self, context, match, active_playlists):
    matched = match.best_playlists

    if not matched:
        return Decision(kind=HOLD if active_playlists else NONE,
                        reason_code=NO_MATCH, matched_playlists=[])

    if matched != active_playlists:
        # playlists 变了 → switch
        evaluation = self._evaluate_operation(context, operation="switch")
        if evaluation.allowed:
            return Decision(kind=SWITCH, matched_playlists=matched)
        return Decision(kind=HOLD, ...)

    # matched == active_playlists → cycle
    evaluation = self._evaluate_operation(context, operation="cycle")
    if evaluation.allowed:
        return Decision(kind=CYCLE, matched_playlists=matched)
    return Decision(kind=HOLD, ...)
```

`matched != active_playlists` 是 list 比较。list identity 是整体——list 变了就 switch。
Gate 逻辑不变：两路径都检查 warmup + CPU + fullscreen。switch 额外检查 idle + force_after（无 cooldown）；cycle 额外检查 idle + cycle_cooldown。

`decide_manual_action()` 同理改签名。

## 8. Cooldown 统一

R4 已移除 `switch_cooldown`。当前 Controller 仍有双时间戳：

- `last_playlist_switch_time`：仅 playlist switch 时更新，用于 `force_after`
- `last_wallpaper_switch_time`：switch 和 cycle 都更新，用于 `cycle_cooldown`

双时间戳在 R8 下变得多余：cycle 语义扩展后可能执行 `openPlaylist`，
此时 `notify_playlist_switch` vs `notify_wallpaper_cycle` 的区分没有意义。

统一为：

- `last_action_time: float`，替代两个时间戳
- `notify_action()` 方法，替代 `notify_playlist_switch()` 和 `notify_wallpaper_cycle()`
- `_evaluate_operation` 统一 cooldown：switch 路径无 cooldown（仅 force_after），cycle 路径用 `cycle_cooldown`
- `force_after` 基于 `last_action_time`——cycle 也会重置 force_after 计时器
- `SchedulerState` 旧字段读取时取两者较大值做兼容迁移

## 9. Actuator 逻辑

`core/actuator.py`：

Actuator 是唯一从 `list[str]` 回退到单个 playlist 的层。
构造时注入 `playlists: dict[str, PlaylistConfig]`（从 config 传入）。

```python
def _select_target(self, best_playlists: list[str]) -> str:
    """从 best_playlists 中按壁纸数量加权随机选一个。"""
    weights = []
    for name in best_playlists:
        cfg = self.playlists.get(name)
        w = cfg.item_count if cfg and cfg.item_count > 0 else 1
        weights.append(w)
    return random.choices(best_playlists, weights=weights, k=1)[0]

def _act_from_decision(self, match, effective_playlists, decision):
    matched = decision.matched_playlists
    if not matched:
        return ...

    target = self._select_target(matched)    # list → 单个 target

    if decision.kind == ActionKind.SWITCH:
        if self.executor.open_playlist(target):
            self.controller.notify_action()
            effective_playlists_after = [target]
            executed = True

    elif decision.kind == ActionKind.CYCLE:
        if [target] == effective_playlists:
            if self.executor.next_wallpaper():
                self.controller.notify_action()
                executed = True
        else:
            if self.executor.open_playlist(target):
                self.controller.notify_action()
                effective_playlists_after = [target]
                executed = True
```

`ActuationOutcome.target_playlist` 记录实际执行的 target（结果，非输入）。
`act_manual()` 和 `act_recovery()` 同理。

## 10. Recovery

```python
def act_recovery(self, match, effective_playlists, recovery_reason):
    matched = match.best_playlists
    if not matched:
        decision = ControllerDecision(kind=NONE if not effective_playlists else HOLD,
                                      reason_code=RECOVERY_NO_MATCH, matched_playlists=[])
        return self._act_from_decision(match, effective_playlists, decision)

    reason_code = (RECOVERY_NO_PLAYLIST if ... else RECOVERY_UNMANAGED_PLAYLIST)
    decision = ControllerDecision(kind=SWITCH, reason_code=reason_code,
                                  matched_playlists=matched)
    return self._act_from_decision(match, effective_playlists, decision)
```

## 11. PlaylistStateResolution

`core/playlist_state.py`：

```python
@dataclass(frozen=True)
class PlaylistStateResolution:
    effective_playlists: list[str]          # 替代 effective_playlist: str
    recovery_needed: bool = False
    recovery_reason: PlaylistRecoveryReason | None = None
```

`resolve_playlist_state` 内部完成单值 → list 包装：

- factual 有 managed playlist → `effective_playlists = [playlist]`
- factual 无 playlist 或 unmanaged → `effective_playlists = []` + recovery
- factual ambiguous → `effective_playlists = [cached_playlist]` if cached else `[]`

Scheduler 不感知包装逻辑。

## 12. History 事件

事件类型不变。语义变化：

| 事件              | 触发条件                                 | 含义                                                         |
| ----------------- | ---------------------------------------- | ------------------------------------------------------------ |
| `playlist_switch` | `matched != active_playlists`，gate 通过 | playlists 变了，切到新的匹配集合                             |
| `wallpaper_cycle` | `matched == active_playlists`，gate 通过 | 在当前匹配范围内操作（可能是 nextWallpaper 或 openPlaylist） |

事件 payload 不变。`best_playlists` 和 `scores` 通过 trace 可查。

## 13. Scheduler 适配

- `cached_playlist: str` → `cached_playlists: list[str]`
- `_resolve_cached_playlist_after` 适配：`effective_playlist_after: str` → `effective_playlists_after: list[str]`，返回 `list`
- `_update_status` 展示 `best_playlists`：`[NIGHT_CHILL(+2)]` 表示 3 个匹配
- `_build_paused_actuation_outcome` 中 `matched_playlist` → `matched_playlists`，`effective_playlist` → `effective_playlists`
- `_build_runtime_components` 构造 Actuator 时传入 `config.playlists`
- `SchedulerState` 旧 `cached_playlist` 读取时包装为 `[cached_playlist]`

## 14. WEConfigProber item_count 扫描

在 scheduler 初始化时（`_build_runtime_components`），扫描 WE config.json 的 playlist items，
填充 `PlaylistConfig.item_count`。热重载时重新扫描。

实现位置：`WEConfigProber` 新增 `probe_item_counts() -> dict[str, int]`。
失败时发出 warning 日志。

## 15. Diagnostics / Dashboard DTO

`ui/dashboard_analysis.py` 扩展：

```python
# MatchEvaluationDTO
bestPlaylists: list[str]
scores: dict[str, float]

# TickSummaryDto / TickActDecisionDto
matchedPlaylists: list[str]           # 替代 matchedPlaylist
activePlaylists: list[str]            # 替代 activePlaylist
```

前端适配新字段名和 list 语义。

## 16. 文件变更清单

| 文件                                                      | 变更                                                                                                                                                                        |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `utils/runtime_config.py`                                 | `PlaylistConfig` 加 `item_count`                                                                                                                                            |
| `core/diagnostics.py`                                     | `MatchEvaluation` 改 `best_playlists` + `scores`；`ControllerDecision` 改 `matched_playlists`；`ActuationOutcome` 改 `effective_playlists_before/after` + `target_playlist` |
| `core/matcher.py`                                         | `evaluate()` 加 gap-based 聚类                                                                                                                                              |
| `core/controller.py`                                      | `decide_action` 签名改 `active_playlists: list[str]`；list 比较判断；cooldown 统一为 `last_action_time`                                                                     |
| `core/actuator.py`                                        | `_select_target` 加权选择；注入 `playlists`；参数改 `effective_playlists: list[str]`；cycle 语义扩展                                                                        |
| `core/playlist_state.py`                                  | `effective_playlist` → `effective_playlists: list[str]`                                                                                                                     |
| `core/scheduler.py`                                       | `cached_playlists: list[str]`；适配全链路 list 语义；传 `config.playlists` 给 Actuator                                                                                      |
| `ui/tray.py`                                              | `best_playlist` → `best_playlists`                                                                                                                                          |
| `tools/tuning/models.py`                                  | `best_playlist` → `best_playlists`；tuning 聚类逻辑同步                                                                                                                     |
| `core/executor.py`                                        | 不变                                                                                                                                                                        |
| `core/event_logger.py`                                    | 不变                                                                                                                                                                        |
| `ui/dashboard_analysis.py`                                | DTO 字段改 `matchedPlaylists` / `activePlaylists`；构建逻辑适配                                                                                                             |
| `dashboard/src/lib/dashboardAnalysis.ts`                  | `matchedPlaylist` → `matchedPlaylists`；`activePlaylist` → `activePlaylists`                                                                                                |
| `dashboard/src/features/dashboard-analysis/ActPanel.vue`  | 展示 playlists 列表                                                                                                                                                         |
| `dashboard/src/features/dashboard-analysis/presenters.ts` | 适配新字段                                                                                                                                                                  |
| `dashboard/src/features/dashboard-analysis/timeline.ts`   | 适配新字段                                                                                                                                                                  |
| `dashboard/src/i18n/{en,zh}.json`                         | i18n key 更新                                                                                                                                                               |
| `tests/test_core_diagnostics.py`                          | 全链路 `str` → `list[str]` 适配；新增聚类测试                                                                                                                               |
| `tests/test_dashboard_api.py`                             | 适配新字段                                                                                                                                                                  |
| `tests/test_tray_summary.py`                              | 适配新字段                                                                                                                                                                  |

## 17. 边界行为

**matched != active_playlists**：switch。不管 active 是否还在新 list 里。

**matched == active_playlists**：cycle。选中哪个 playlist 是加权随机的结果，都是正确行为。

**matched 为空 list**：系统保持当前状态（HOLD/NONE）。

**单 playlist 场景**：`best_playlists` 长度为 1，`active_playlists` 长度为 1，行为与改动前完全一致。

**item_count = 0**：加权随机退化为 uniform random。
