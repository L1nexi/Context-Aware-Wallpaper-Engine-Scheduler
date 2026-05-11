# Phase 4 Plan: WE Path, Startup Resolve, and Simple Actuation Outcome

本文件是 [CONFIGURATION_PHASE_PLAN.md](./CONFIGURATION_PHASE_PLAN.md) 中阶段 4 的展开计划。

## 1. Goal

阶段 4 的核心不是给 runtime 增加更多降级语义，而是把 Wallpaper Engine 路径问题前移到启动边界：

- 配置加载后，先把 WE path 解析完。
- 如果路径无效或自动检测失败，直接让启动失败。
- 只有在路径已解析的前提下，scheduler 才进入运行态。
- 运行时的 executor 只回答一个问题：这次命令到底成功了没有。

完成后，系统应该形成两个清晰层次：

- 启动 / reload 边界负责保证“可不可以执行”。
- runtime actuation 只负责“这次执行成没成功”。

## 2. Non-goals

- 不保留 diagnostics-only 降级运行模式。
- 不引入 `ExecutorCommandResult` 或多态错误结果对象。
- 不把 executor 失败再拆成 `path_unresolved` / `start_failed` / `command_failed` 等细粒度 taxonomy。
- 不实现 GUI 写回自动检测到的路径。
- 不在每个 tick 前重新扫描 Steam 安装目录。
- 不在本阶段实现 reload 逻辑本身；reload 语义由阶段 5 消费这里的结论。

## 3. Current Facts

- `utils/config_documents.py` 已经把“显式路径无效”视为配置错误。
- `runtime.wallpaper_engine_path: null` 当前在 runtime 中仍会折叠为空字符串。
- `utils/we_path.py` 目前同时承担显式路径命中和自动检测。
- `core/executor.py` 仍在构造期自行自动检测，并在失败时静默 no-op。
- `core/actuator.py` 当前在调用 executor 后会直接提交 switch / cycle 状态，缺少“成功后再提交”的边界。
- `main.py` 的 tray 模式在 `scheduler.initialize()` 失败后仍会继续走后续流程，这和新的文本配置心智不一致。

这些现状说明问题不在于 executor 缺少更复杂的返回值，而在于路径错误还没有被放回正确的启动边界。

## 4. Design

### 4.1 WE path belongs to startup and reload precheck

新的语义固定如下：

- `runtime.wallpaper_engine_path` 是非空字符串时：
  - 它是用户显式指定路径
  - 路径不存在或不可用时，直接视为配置错误
  - 不 fallback 自动检测
- `runtime.wallpaper_engine_path` 是 `null` 时：
  - 在启动阶段做一次自动检测
  - 检测成功后只用于当前 runtime
  - 不写回 YAML
  - 检测失败时启动失败

这意味着：

- unresolved WE path 不再是 runtime 内部状态
- scheduler 不允许带着 unresolved executor 启动
- 后续阶段 5 中的 reload 也要复用同样语义：
  - reload 前 resolve 成功才允许 swap
  - resolve 失败时保留旧 runtime

### 4.2 Resolution helper stays simple

这里不需要引入复杂 resolution object。

建议 `utils/we_path.py` 只提供一个简单 helper，例如：

```python
def resolve_wallpaper_engine_path(configured_path: str) -> str | None:
    ...
```

语义：

- 显式路径有效时返回该路径
- `configured_path == ""` 时尝试自动检测并返回检测结果
- 自动检测失败时返回 `None`

上层调用方负责把 `None` 解释为启动失败或 reload 失败，而不是让 executor 继续兜底。

`find_we_config_json()` 也应改成消费一个已经 resolved 的 exe 路径，而不是再次隐式触发 resolve。

### 4.3 Executor becomes a thin side-effect adapter

`core/executor.py` 的角色收缩为：

- 构造时接收一个已经 resolved 的 `wallpaper64.exe` 路径
- 不做路径探测
- 不做 silent no-op
- 命令方法只返回 `bool`

建议接口保持简单：

```python
class WEExecutor:
    def __init__(self, we_path: str): ...

    def open_playlist(self, playlist_name: str) -> bool: ...
    def next_wallpaper(self) -> bool: ...
```

行为约束：

- 命令真实成功完成时返回 `True`
- 拉起 Wallpaper Engine 或执行 control 命令失败时返回 `False`
- 具体失败细节写日志，不额外扩成复杂结果对象

这样可以保留实现上的可解释性，同时避免把执行层契约做重。

### 4.4 Actuator commits state only on success

`core/actuator.py` 要改成“成功提交”，不是“尝试提交”。

固定规则：

- switch:
  - controller 决定为 `SWITCH`
  - 调用 `executor.open_playlist()`
  - 返回 `True` 时才：
    - 更新 `active_playlist_after`
    - 调用 `controller.notify_playlist_switch()`
    - 写 `playlist_switch`
- cycle:
  - controller 决定为 `CYCLE`
  - 调用 `executor.next_wallpaper()`
  - 返回 `True` 时才：
    - 调用 `controller.notify_wallpaper_cycle()`
    - 写 `wallpaper_cycle`
- 任一命令返回 `False`：
  - 不更新 cooldown
  - 不更新 `active_playlist_after`
  - 不伪装成 executed
  - 记录一个通用执行失败事实

这里的关键是状态提交边界，不是失败类型边界。

### 4.5 Diagnostics and history stay generic

既然 executor 只返回 `bool`，本阶段也不应再为失败原因引入一套复杂 taxonomy。

建议收敛成：

- Diagnostics 继续保留：
  - controller `reason_code`
  - `executed: bool`
- 当 controller 放行但 executor 返回 `False` 时：
  - `reason_code` 仍然保留 controller 结论
  - `executed` 为 `False`

这已经足够表达一个重要事实：

- controller 想切
- 但这次执行没成功

History 对执行失败只引入一个通用事件：

- `actuation_failed`

事件数据只保留高价值字段：

- `operation`
- `reason_code`
- `matched_playlist`
- `active_playlist_before`

不再为失败事件记录更多 executor 细分状态。

### 4.6 Host startup behavior must become fail-fast

除了 core，本阶段还必须修正宿主启动行为。

要求：

- `--no-tray` 模式下，`scheduler.initialize()` 失败时直接退出
- tray 模式下，`scheduler.initialize()` 失败时：
  - 可以弹出错误提示
  - 但之后必须直接退出
  - 不能继续 `scheduler.start()`、HTTP server 或 tray loop

否则“启动失败”语义在宿主层面仍然是假的。

## 5. File Map

- `utils/we_path.py`
  - 简单的 WE path resolve helper
  - `find_we_config_json()` 改为消费 resolved path
- `utils/config_loader.py`
  - 继续保留显式路径 validate 入口
  - 不承担 auto-detect failure 的 runtime 降级语义
- `core/scheduler.py`
  - `initialize()` 中完成 WE path resolve
  - resolve 失败时抛出初始化错误
- `core/executor.py`
  - 删除构造期自动检测和 silent no-op
  - 命令接口收缩为 `bool`
- `core/actuator.py`
  - 只在 `True` 时提交状态
  - 失败时保留原状态并记录 generic failure
- `core/diagnostics.py`
  - 继续以 `executed` 表达最终是否成功
  - 不引入复杂 execution result 类型
- `core/event_logger.py`
  - 新增 `ACTUATION_FAILED`
- `main.py`
  - tray / console 统一 fail-fast 启动语义

## 6. Implementation Tasks

### Task 1: Resolve before runtime

把 WE path 解析前移到 `scheduler.initialize()`。

完成标准：

- 显式无效路径不会进入 runtime
- `null` 自动检测失败不会进入 runtime
- tray / console 启动行为与初始化结果一致

### Task 2: Thin executor and success-only commit

收缩 executor 契约，并同步调整 actuator。

完成标准：

- `WEExecutor` 不再自行检测路径
- `open_playlist()` / `next_wallpaper()` 只返回 `bool`
- actuator 只在成功时更新 controller 和 active playlist

### Task 3: Generic failure surfacing

保留最小必要的可解释性，不引入复杂失败模型。

完成标准：

- runtime command failure 能在日志中看到
- diagnostics 至少能表达“controller 允许了，但 executed 为 false”
- history 只记录一个 generic `actuation_failed` 事件

### Task 4: Cleanup

删除旧 no-op 心智和与之配套的残留逻辑。

完成标准：

- runtime 中不再存在 unresolved executor
- executor 中不再有 silent no-op 分支
- 启动失败后不会继续运行宿主组件

## 7. Validation Strategy

本阶段不追求广撒网测试。大部分直线逻辑可以通过源码 review 保证。

只保留高价值验证：

1. 启动边界
   - 显式无效路径时 initialize 失败
   - `wallpaper_engine_path: null` 自动检测失败时 initialize 失败

2. Actuator 状态提交边界
   - executor 返回 `False` 时，不更新 cooldown，不更新 active playlist
   - executor 返回 `True` 时，才提交状态和成功事件

3. 一次最小手工 smoke
   - 有效配置时能正常启动
   - 无效路径时会明确失败退出

不建议为这些内容补低价值测试：

- 简单 `bool` 透传
- dataclass 字段赋值
- 日志文案细节
- 为了覆盖率而重复验证已有配置 schema 行为

## 8. Assumptions

- 本阶段保持 `SchedulerConfig.wallpaper_engine_path: str` 不变；`null` 继续在 runtime config 中折叠为空字符串。
- auto-detect failure 与显式路径错误一样，都是启动 / reload 前的失败。
- 本阶段不需要复杂 executor result 对象；`bool` 足够。
- 如果后续 tray Manual Apply 需要更强可解释性，可以在那个阶段再扩展失败表达，而不是现在提前设计。
