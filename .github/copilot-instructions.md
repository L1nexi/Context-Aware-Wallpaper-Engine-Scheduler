# Project Guidelines

## Architecture

采用 **"感知-决策-执行" (Sense-Think-Act)** 循环架构 (1s tick)，配合 JSON 配置文件驱动。

```
Sensors → ContextManager → [Policies] → Matcher (TagSpec fallback + cosine similarity) → Actuator → WEExecutor
                                                        ↑
                                              SchedulingController
                                              [CpuGate, FullscreenGate]
```

- `core/sensors.py` — 感知层: `WindowSensor`, `IdleSensor`, `CpuSensor`, `FullscreenSensor`, `WeatherSensor`
- `core/policies.py` — 策略插件: `ActivityPolicy` (EMA), `TimePolicy` (Hann 插值 + 动态日出日落), `SeasonPolicy`, `WeatherPolicy`
- `core/matcher.py` — 匹配器: TagSpec fallback 解析 + 余弦相似度选择最佳 Playlist
- `core/controller.py` — `SchedulingController` + `CpuGate` / `FullscreenGate`: 门控链
- `core/actuator.py` — 执行器: 咨询 Controller 后调用 WEExecutor；写 `history.jsonl`
- `core/executor.py` — WE CLI 封装 (`wallpaper64.exe -control`)
- `core/scheduler.py` — 主调度循环 (后台线程), 暂停/恢复, `on_auto_resume` hook, 配置热重载
- `core/tray.py` — 系统托盘 UI (pystray + tkinter 弹窗)
- `utils/i18n.py` — 轻量 i18n (`t(key)`, zh/en)
- `utils/config_loader.py` — JSON 配置加载 (Pydantic v2)
- `utils/icon_generator.py` — PIL 托盘图标生成
- `utils/logger.py` — RotatingFileHandler 日志 (根 logger `WEScheduler` 装 handler，子 logger propagate)

详细设计见 `docs/README_DEV.md`。

## Policy 接口

- `Policy.get_tags(context) -> Dict[str, float]` — 统一公开接口，返回单一 dict
- `Policy._compute_tags(context) -> Dict[str, float]` — 子类实现
- `WeatherPolicy._compute_tags` 返回单一 dict（不再是 `List[Dict]`）；`_ID_TAGS`/`_MAIN_FALLBACK` 均为 `Dict[int/str, Dict[str, float]]`
- **No Arbiter layer** — Matcher 直接持有 policies，`match()` 内统一 evaluate

## TagSpec Fallback 系统

```python
# config_loader.py
class TagSpec(BaseModel):
    fallback: Dict[str, float] = {}   # tag → weight (可以不归一化；余量视为"静默衰减")
```

- `AppConfig.tags: Dict[str, TagSpec]` — 顶层 `"tags"` 块，key 为标签名
- Matcher 在 `__init__` 接收 `tag_specs`，`_fallback_expand(tag, weight, visited)` 递归展开
- 截断条件：循环（visited 集合）或 `weight < _MIN_EXPAND_WEIGHT = 0.02`
- 合并：同 key 贡献简单相加（线性叠加，与下游 L2 归一化配合正确）
- **Policy 不做 fallback**——仅输出物理语义标签（如 `#fog`、`#storm`），fallback 完全由 Matcher 处理

## Sensor → Context 映射

| context key    | Sensor           | 类型                                |
| -------------- | ---------------- | ----------------------------------- |
| `"window"`     | WindowSensor     | `{title, process}`                  |
| `"idle"`       | IdleSensor       | `float` (秒)                        |
| `"cpu"`        | CpuSensor        | `float` 滑动均值 0–100              |
| `"fullscreen"` | FullscreenSensor | `bool`                              |
| `"weather"`    | WeatherSensor    | `{id, main, sunrise, sunset}` (OWM) |
| `"time"`       | ContextManager   | `time.struct_time`                  |

## Gate 链 (SchedulingController)

```
cooldown → [CpuGate.should_defer(), FullscreenGate.should_defer()] → idle/force
```

- Gate 是 **defer**（不重置计时器），force_interval 仍在计时，条件消失后照常触发。
- `cpu_threshold=0` 禁用 CpuGate；`pause_on_fullscreen=false` 禁用 FullscreenGate。

## WeatherSensor 与数据共享

- WeatherSensor 调用 OWM 2.5 `/weather`，结果写入 `context.weather`。
- WeatherPolicy 和 TimePolicy 均从 `context.weather` 读取，不各自发 HTTP 请求。
- WeatherSensor 节流：`_last_fetch > 0` 时才比较 interval（失败也计时，防止每秒重试）。
- TimePolicy：若 `context.weather` 包含 `sunrise`/`sunset`，动态更新 `day_start`/`night_start` 峰值。

## 配置热重载

- Scheduler `_run_loop` 每 tick 检查 `os.path.getmtime(config_path)`，变化则调用 `_hot_reload()`。
- `_hot_reload()` 重建 Sensors/Policies/Matcher/Controller，保留 `current_playlist` 和暂停状态。

## 统计记录

- `Actuator._write_history()` 在 `playlist_switch` / `wallpaper_cycle` 时追加写 `history.jsonl`。
- 格式: `{ts, event, tags(top5), playlist_from/to 或 playlist}`。

## pystray 注意事项 (Win32)

- **HMENU 缓存:** Win32 后端缓存 HMENU, callable menu 属性 (text, visible, enabled) 仅在菜单**构建**时求值一次, 右键弹出不会重新求值。非菜单回调引起的状态变更**必须**手动调用 `icon.update_menu()` 重建 HMENU。
- **`_handler` 包装器:** pystray 在菜单项回调执行后自动调用 `update_menu()`, 所以菜单项点击触发的状态变更无需手动刷新。
- **跨线程安全:** `Shell_NotifyIcon` 和 Win32 菜单 API 无线程亲和性要求, `_sync_icon()` 可从任意线程调用。

## Scheduler ↔ Tray 同步

- Tray 通过 `scheduler.on_auto_resume = self._sync_icon` 注册 hook
- `_sync_icon()` 既刷新图标图片 (`IconGenerator.generate`) 又重建菜单 (`update_menu()`)
- `on_auto_resume` 是简单 callable 属性 (非观察者模式), 若未来需要多个订阅者应迁移为标准观察者

## Build & Run

```bash
pip install -r requirements.txt
python main.py                          # 前台运行 (含系统托盘)
python main.py --no-tray               # 仅控制台
scripts/build.bat                       # PyInstaller 打包
```

## Conventions

- 所有 UI 文本通过 `utils/i18n.py` 的 `t(key)` 查找, 不硬编码
- 暂停统一 API: `scheduler.pause(seconds=None)`, `None` = 无限期
- `scheduling` 块字段: `cpu_threshold`(默认85), `cpu_sample_window`(默认10), `pause_on_fullscreen`(默认true)
- `weather` 块字段: `request_timeout`(默认10), `warmup_timeout`(默认3)
- 配置顶层新增 `tags` 块: `Dict[str, TagSpec]`，定义标签 fallback 链
