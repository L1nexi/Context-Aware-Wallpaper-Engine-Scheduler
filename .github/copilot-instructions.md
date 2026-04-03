# Project Guidelines

## Architecture

采用 **"感知-决策-执行" (Sense-Think-Act)** 循环架构，配合 JSON 配置文件驱动。

```
Sensors → ContextManager → Arbiter (weighted aggregation) → Matcher (cosine similarity) → Actuator → WEExecutor
```

- `core/sensors.py` — 感知层: WindowSensor, IdleSensor
- `core/policies.py` — 策略插件: ActivityPolicy (EMA), TimePolicy (插值), SeasonPolicy, WeatherPolicy
- `core/arbiter.py` — 仲裁器: 加权聚合各 Policy 的归一化标签向量
- `core/matcher.py` — 匹配器: 余弦相似度选择最佳 Playlist
- `core/controller.py` — DisturbanceController: 空闲/冷却/强制切换门控
- `core/actuator.py` — 执行器: 咨询 Controller 后调用 WEExecutor
- `core/executor.py` — WE CLI 封装 (`wallpaper64.exe -control`)
- `core/scheduler.py` — 主调度循环 (后台线程), 暂停/恢复, `on_auto_resume` hook
- `core/tray.py` — 系统托盘 UI (pystray + tkinter 弹窗)
- `utils/i18n.py` — 轻量 i18n (`t(key)`, zh/en)
- `utils/config_loader.py` — JSON 配置加载
- `utils/icon_generator.py` — PIL 托盘图标生成
- `utils/logger.py` — RotatingFileHandler 日志

详细设计见 `docs/README_DEV.md`。

## Code Style

- Python 3.11+, 类型注解优先
- 日志使用 `logging.getLogger("WEScheduler.XXX")` 命名层级
- 面向接口: Sensor 基类 ABC, Policy 基类 ABC

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
python main.py --mode console           # 仅控制台
scripts/build.bat                       # PyInstaller 打包
```

## Conventions

- 配置项 `switch_on_start` 位于 `disturbance` 块内
- 所有 UI 文本通过 `utils/i18n.py` 的 `t(key)` 查找, 不硬编码
- 暂停统一 API: `scheduler.pause(seconds=None)`, `None` = 无限期
