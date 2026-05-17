# WE Factual Playlist Recovery Spec

状态：Draft

## 1. 目标

让调度器把 Wallpaper Engine `config.json` 中的当前 playlist 视为当前壁纸状态的事实信源，并在 WE 崩溃、休眠恢复、播单加载失败、用户手动切到非托管状态后，自动恢复到当前上下文匹配的 managed playlist。

本设计同时约束 tray 极简摘要和后续 manual apply 的语义，但第一优先级是提高自动调度可靠性。

## 2. 非目标

- 不恢复 Dashboard 里的 Config Editor 或 History 页面。
- 不在 Diagnostics 或 tray 暴露复杂 blocker 解释。
- 不实现完整多显示器调度模型。
- 不做 command-level pending verify 或短轮询事务。
- 不把 recovery 混入 normal controller gates。
- 不把 WE `config.json` 的完整结构建模为长期运行模型。

## 3. 当前事实

- `core/scheduler.py` 持有当前运行缓存 `current_playlist`，后续应逐步改名为 `cached_playlist`。
- `core/controller.py` 是 normal scheduling gates 和 reason code 的来源。
- `core/actuator.py` 负责执行 switch / cycle 副作用，并且只有执行成功后才更新 controller cooldown。
- `core/executor.py` 已经具备 `ensure_we_running()`，必要时会尝试启动 Wallpaper Engine。
- `utils/config_tools.py` 目前直接读取 WE `config.json` 做 playlist scan，这个读取逻辑应抽到新的 WE config probe 能力中。
- 当前产品仍按单显示器调度假设运行，多显示器只需要保守留口。

## 4. 术语

- `configured_playlist`
  - `config.playlists` 的 key。
  - 该 key 直接等于 Wallpaper Engine playlist name。

- `managed_playlist`
  - 调度器认识并允许调度的 playlist。
  - 等价于 `configured_playlist` 在运行时的集合语义。

- `factual_playlist`
  - 从 Wallpaper Engine `config.json` 读取到的当前真实 playlist。
  - 它只描述 WE 事实，不判断是否 managed。

- `cached_playlist`
  - 调度器内存和 `state.json` 里的上次已知 playlist。
  - 它可能因为 WE 崩溃、休眠、用户手动操作或命令异常而漂移。

- `effective_playlist`
  - 本 tick 进入 controller / actuator 判断时采用的当前 playlist。
  - 如果事实可信且 managed，则来自 `factual_playlist`。
  - 如果事实未知，则 fallback 到 `cached_playlist`。

- `matched_playlist`
  - Matcher 根据当前 context 算出的目标候选。
  - 它不是当前状态。

- `target_playlist`
  - Actuator 本次准备执行切换的目标 playlist。
  - Normal scheduling、manual apply、recovery 都可以产生 target。

## 5. WE Config Prober

新增只读能力，建议路径为 `utils/we_config.py` 或 `core/we_config.py`，实现时按依赖方向决定。第一版接口保持窄：

```python
class WEConfigProber:
    def __init__(self, we_exe_path: str): ...
    def probe_playlist(self) -> FactualPlaylistState: ...
    def scan_playlist_names(self) -> list[str]: ...
```

`probe_playlist()` 不接收 managed playlist 参数。它只回答 Wallpaper Engine 当前事实。

推荐数据形状：

```python
class FactualPlaylistStatus(StrEnum):
    PLAYLIST = "playlist"
    NO_PLAYLIST = "no_playlist"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"

@dataclass(frozen=True)
class FactualPlaylistState:
    status: FactualPlaylistStatus
    playlist: str | None = None
    source: str | None = None
    issue: str | None = None
```

状态语义：

- `PLAYLIST`
  - WE `config.json` 中存在 playlist name。
  - `playlist` 保存该 name。
- `NO_PLAYLIST`
  - 当前是单壁纸，或没有任何 playlist 字段。
  - `playlist` 为 `None`。
- `UNKNOWN`
  - WE 进程无法启动、`config.json` 缺失、不可读或结构无法识别。
  - 本 tick 不做事实校正。
- `AMBIGUOUS`
  - 多显示器读到不同 playlist。
  - 第一版按 unknown 处理，不触发 recovery。

WE 正常运行是事实可信前提。调用方需要在 probe 前或 probe 内通过 executor/prober 确保 WE 正在运行；如果启动失败，返回 `UNKNOWN`，不引入 stale 语义。

## 6. Playlist State Helper

第一版不引入长期服务对象。新增纯函数 helper，建议放在 `core/playlist_state.py`：

```python
def resolve_playlist_state(
    factual: FactualPlaylistState,
    cached_playlist: str,
    managed_playlists: set[str],
    paused: bool,
) -> PlaylistStateResolution: ...
```

推荐数据形状：

```python
class PlaylistRecoveryReason(StrEnum):
    NO_PLAYLIST = "recovery_no_playlist"
    UNMANAGED_PLAYLIST = "recovery_unmanaged_playlist"

@dataclass(frozen=True)
class PlaylistStateResolution:
    effective_playlist: str
    next_cached_playlist: str
    recovery_needed: bool = False
    recovery_reason: PlaylistRecoveryReason | None = None
```

解析规则：

1. `factual.status == PLAYLIST` 且 `factual.playlist in managed_playlists`
   - 事实状态胜出。
   - `effective_playlist = factual.playlist`
   - `next_cached_playlist = factual.playlist`
   - `recovery_needed = False`

2. `factual.status == PLAYLIST` 且 `factual.playlist not in managed_playlists`
   - WE 当前在 unmanaged playlist。
   - Running 时这是 broken state。
   - `effective_playlist = ""`
   - `next_cached_playlist = cached_playlist`
   - `recovery_needed = not paused`
   - `recovery_reason = UNMANAGED_PLAYLIST`

3. `factual.status == NO_PLAYLIST`
   - WE 当前是单壁纸或无 playlist。
   - Running 时这是 broken state。
   - `effective_playlist = ""`
   - `next_cached_playlist = cached_playlist`
   - `recovery_needed = not paused`
   - `recovery_reason = NO_PLAYLIST`

4. `factual.status in {UNKNOWN, AMBIGUOUS}`
   - 不做事实校正，也不 recovery。
   - `effective_playlist = cached_playlist`
   - `next_cached_playlist = cached_playlist`
   - `recovery_needed = False`

Paused 期间不做 recovery，也不向用户层泄漏 unmanaged / no playlist 状态。

## 7. Tick 行为

推荐 tick 顺序：

```text
sense
match
probe factual playlist
resolve playlist state
update cached_playlist if resolution says factual managed

if paused:
  build paused outcome
elif recovery_needed:
  actuator.act_recovery(match, effective_playlist, recovery_reason)
else:
  actuator.act(context, match, effective_playlist)

commit tick
```

Recovery 和 normal scheduling 在同一个 tick 内互斥。

理由：

- Broken state 下 normal switch / cycle 的当前 playlist 前提不成立。
- Recovery 的职责是先把 WE 恢复到 managed state。
- Recovery 成功后，下一个 tick 再做正常调度更可解释。

`UNKNOWN` / `AMBIGUOUS` 不触发 recovery，因为没有足够事实证明 WE 处于 broken state。

## 8. Recovery 行为

Recovery 是一种独立 actuation mode。它与 manual apply 一样绕过 normal controller gates，但语义不同：

- `manual`
  - 用户明确要求按当前上下文执行一次。
- `recovery`
  - 调度器发现 WE 当前不在 managed state，主动恢复到当前匹配目标。

Cooldown 规则：

- Recovery 执行前绕过 cooldown、idle、fullscreen、CPU 等 normal gates。
- Recovery 成功后调用 `notify_playlist_switch()`，等价于一次真实 playlist switch。
- Recovery 失败不更新 cooldown，也不更新 cached playlist。

原因：

- Broken state 恢复不应被 cooldown 阻挡。
- Recovery 本身仍会改变用户看到的壁纸状态，成功后应抑制下一次普通自动切换，避免连续抖动。

当 `match.best_playlist is None` 时，recovery 不执行副作用。后续实现可以新增 reason code，例如 `recovery_no_match`，用于 Diagnostics / history 区分普通 no match。

## 9. 组件归属

### `WEConfigProber`

职责：

- 读取 WE `config.json`。
- 从 `$USER.general.wallpaperconfig.wallpaper` 中抽取当前 playlist。
- 为 config tool 提供 playlist scan。

不负责：

- 判断 playlist 是否 managed。
- 决定是否 recovery。
- 更新 scheduler state。
- 执行 Wallpaper Engine 命令。

### `PlaylistStateHelper`

职责：

- 将 `factual_playlist + cached_playlist + managed_playlists + paused` 解释为 `effective_playlist` 和 recovery intent。
- 保持纯函数，方便测试。

不负责：

- 读取文件。
- 调用 executor。
- 写 `state.json`。
- 记录 history。

### `Scheduler`

职责：

- 持有 `cached_playlist`。
- 编排 tick 生命周期。
- 调用 prober 和 playlist state helper。
- 根据 resolution 选择 paused / normal / recovery 路径。
- 在 commit tick 时持久化状态。

Scheduler 可以先保留现有结构，不为本 feature 做大重构。若后续继续膨胀，再考虑拆出 `RuntimeComponents` / `SchedulerRuntimeState`。

### `Controller`

职责保持不变：

- 只负责 normal scheduling gates 和 normal reason code。
- 不处理 recovery。

### `Actuator`

职责：

- 提供 `act()` 处理 normal scheduling。
- 提供 `act_manual()` 处理用户主动 apply。
- 新增 `act_recovery()` 处理系统自愈。
- 三者内部复用 `_act_from_decision()`，避免重复执行逻辑。

`act_recovery()` 应产生独立 reason code 和 history data，不能伪装成 manual apply。

## 10. Tray 极简摘要

Tray 只展示用户需要快速理解的最少状态：

```text
Status: Running | Paused
Active: <effective/cached playlist display>
Match: <latest matched playlist display>
```

约束：

- 不展示 blocker。
- 不展示 unmanaged / no playlist 诊断细节。
- Paused 时不泄漏 WE broken state。
- `Apply Current Match Now` 只表达用户意图，后续执行仍走 Actuator 的 manual 路径。
- 点击 Apply Now 时重新采集 context 和 match，不复用 tray 上显示的旧 match。
- `Apply Current Match Now` 文案应对应修改为 `Apply Now: <Match>`

## 11. 实施阶段

### Phase 1: WE config probe

文件范围：

- 新增 `utils/we_config.py` 或 `core/we_config.py`
- 修改 `utils/config_tools.py`
- 修改 `tests/test_we_path.py` 或新增 `tests/test_we_config.py`

任务：

- 实现 `probe_playlist()`。
- 实现 `scan_playlist_names()`。
- 将现有 Config Tools scan 逻辑改为复用 prober。
- 覆盖单壁纸、播单、无 wallpaperconfig、不可读 JSON、多显示器相同 playlist、多显示器不同 playlist。

验证：

```bash
venv313\Scripts\python.exe -m pytest tests/test_we_config.py tests/test_we_path.py tests/test_config_loader.py -q
```

### Phase 2: Tick-level factual correction and recovery

文件范围：

- 新增 `core/playlist_state.py`
- 修改 `core/scheduler.py`
- 修改 `core/diagnostics.py`
- 修改 `core/actuator.py`
- 修改 `tests/test_core_diagnostics.py`

任务：

- 引入 `factual_playlist` / `effective_playlist` / `cached_playlist` 术语。
- 在 tick 中 probe factual playlist。
- managed factual playlist 校正 cached playlist。
- no playlist / unmanaged playlist 在 running 状态触发 recovery。
- recovery 与 normal scheduling 互斥。
- recovery 成功后进入 switch cooldown。

本阶段不进行测试

### Phase 3: Tray summary

文件范围：

- 修改 `ui/tray.py`
- 可能修改 `utils/i18n.py`
- 可能修改 `core/scheduler.py` 暴露摘要属性

任务：

- 增加 `Status / Active / Match` 极简摘要。
- 不展示 blocker 或 broken state 细节。
- 确保 manual apply 仍重新采集 context。

验证：

- 由用户手动测试

### Phase 4: Diagnostics polish

文件范围：

- 修改 `ui/dashboard_analysis.py`
- 修改 `dashboard/src/lib/dashboardAnalysis.ts`
- 修改 `dashboard/src/features/dashboard-analysis/*`

任务：

- 如果 recovery reason 已进入 tick trace，在 Diagnostics 中展示为独立 action reason。与 Cycle/Switch 事件同级表现在折线图上
- 不新增配置编辑或手动副作用按钮。

本阶段无需测试

## 12. 风险与边界

- WE `config.json` 结构不是本项目控制的公开 API。Prober 必须保守解析，失败时返回 `UNKNOWN`，不能抛出导致调度循环中断。
- 多显示器第一版只做保守识别，不支持按显示器独立调度。
- Recovery 绕过 normal gates，但成功后写入 cooldown，避免恢复后马上普通切换。
- Paused 是用户明确停止自动干预的状态。Paused 期间不 recovery，也不把 broken state 展示到 tray。
- 如果 `factual_playlist` 是 managed，应让事实胜出并更新 cached playlist，避免调度器覆盖用户在 WE 中手动切到另一个已配置 playlist 的行为。

## 13. Open Questions

- `WEConfigProber` 放在 `utils/` 还是 `core/`：如果它只读文件并服务 Config Tools，倾向 `utils/we_config.py`；如果它需要直接依赖 executor 保证 WE running，倾向拆成 core 层编排。
- 是否在第一版新增 `recovery_no_match` reason code：建议新增，但可以随 Phase 2 具体 DTO 改动一起确定。
