# History System — Implementation Spec

## Overview

R3: 消费 history.jsonl 数据，提供时间轴可视化和调优辅助。
Dashboard 新增 "History" tab（el-tabs 切换），现有 ConfidencePanel 嵌入 similarity sparkline。

---

## Part A: Backend

### A1. HistoryLogger (`utils/history_logger.py`) — New file

**Event format — Tagged Union:**

```json
{"ts": "2026-04-28T00:28:26+08:00", "type": "playlist_switch", "data": {...}}
{"ts": "2026-04-28T00:28:26+08:00", "type": "wallpaper_cycle", "data": {...}}
{"ts": "2026-04-28T01:00:00+08:00", "type": "pause", "data": {"duration": 3600}}
{"ts": "2026-04-28T01:00:00+08:00", "type": "pause", "data": {"duration": null}}
{"ts": "2026-04-28T02:00:00+08:00", "type": "resume", "data": {}}
{"ts": "2026-04-28T00:28:26+08:00", "type": "start", "data": {}}
{"ts": "2026-04-28T23:00:00+08:00", "type": "stop", "data": {}}
```

Data schemas:

| type | data fields |
|------|-------------|
| `playlist_switch` | `playlist_from`, `playlist_to`, `tags: {tag: weight}`, `similarity`, `similarity_gap`, `max_policy_magnitude` |
| `wallpaper_cycle` | `playlist`, `tags: {tag: weight}` |
| `pause` | `duration: int \| null` (seconds, null = indefinite) |
| `resume` | `{}` |
| `start` | `{}` |
| `stop` | `{}` |

ts format: ISO 8601 with timezone (`datetime.now(timezone.utc).isoformat()`).

**Monthly rotation:**

文件名 `history-{YYYY}-{MM}.jsonl`。写入时检测月份变化，自动切新文件。

**Public API:**

```python
class HistoryLogger:
    """Thread-safe append-only event log with monthly rotation.

    write() is called from multiple threads (scheduler, tray, main) —
    all internal state is guarded by a single threading.Lock.
    """
    def __init__(self, data_dir: str) -> None: ...
    def write(self, event_type: str, data: dict) -> int: ...
    def read(self, limit: int = 100,
             from_ts: str | None = None,
             to_ts: str | None = None) -> dict: ...
```

**Thread safety**: `write()` 持锁完成: event_id 递增 → 月份检测/轮转 → 文件 append。`read()` 持锁读取。

`write()`: 写入一条事件，返回递增的 `event_id`（从 1 开始，受同一把锁保护，严格单调）。

`read()`: 返回 `{"segments": [...], "events": [...]}`。

- **默认时间窗**: `from_ts` 和 `to_ts` 都为空时，默认返回最近 1 小时的数据。这是后端契约，不是前端约定。

- **segments**: 后端计算的连续时间轴段落。内部逻辑：取 `[from_ts, to_ts]` 范围内的所有事件 + 时间窗之前最近的一条 "seed" 事件 → 推断每个时间段的 playlist 状态 → 输出段落列表。段落格式：

```json
{"playlist": "NIGHT_CHILL", "start": "...", "end": "..."}
{"playlist": null, "type": "pause", "start": "...", "end": "..."}
{"playlist": null, "type": "dead", "start": "...", "end": "..."}
```

`type` 可选值：`"active"`（省略）、`"pause"`、`"dead"`（stop 到下一个 start 之间）。

- **events**: 原始事件列表，最新在前，受 `limit` 约束。供下方事件列表渲染。

### A2. TickState: `last_event_id` (`ui/dashboard.py`)

TickState 新增字段：

```python
last_event_id: int = 0
```

`build_tick_state()` 从 `scheduler.history_logger.last_event_id` 读取当前值。每次 history write 后该值递增。前端 watch 此字段即可捕获所有事件类型（包括 `wallpaper_cycle`）。

### A3. StateStore ring buffer (`ui/dashboard.py`)

在现有 StateStore 上扩展，不新建类：

```python
from collections import deque

class StateStore:
    def __init__(self, tick_history: int = 300):
        self._lock = threading.Lock()
        self._state = TickState()
        self._tick_log: deque[TickState] = deque(maxlen=tick_history)

    def update(self, state: TickState) -> None:
        with self._lock:
            self._state = state
            self._tick_log.append(state)

    def read(self) -> TickState: ...  # unchanged

    def read_recent(self, count: int | None = None) -> list[dict]:
        with self._lock:
            items = list(self._tick_log)
        if count is not None:
            items = items[-count:]
        return [dataclasses.asdict(s) for s in items]
```

### A4. DashboardHTTPServer changes (`ui/dashboard.py`)

```python
class DashboardHTTPServer:
    def __init__(self, state_store: StateStore, history_logger: HistoryLogger):
        self._state_store = state_store
        self._history = history_logger
        ...
```

`_build_app(state_store, history_logger)` — 新增两个端点:

`GET /api/ticks?count=300`:
```python
@app.route('/api/ticks')
def api_ticks():
    count = int(bottle.request.query.get('count', 300))
    bottle.response.content_type = 'application/json; charset=utf-8'
    return json.dumps(state_store.read_recent(count))
```

`GET /api/history?limit=100&from=<ISO>&to=<ISO>`:
```python
@app.route('/api/history')
def api_history():
    limit = int(bottle.request.query.get('limit', 100))
    from_ts = bottle.request.query.get('from')
    to_ts = bottle.request.query.get('to')
    bottle.response.content_type = 'application/json; charset=utf-8'
    return json.dumps(history_logger.read(limit=limit, from_ts=from_ts, to_ts=to_ts))
```

响应格式: `{"segments": [...], "events": [...]}`。前端直接用 segments 渲染 Gantt，用 events 渲染列表。

### A5. Scheduler changes (`core/scheduler.py`)

```python
self.history_logger: HistoryLogger | None = None  # set by main.py BEFORE initialize()
```

**关键约束**: `history_logger` 必须在 `scheduler.initialize()` 之前设置，因为 `initialize()` → `_build_runtime_components()` 会构造 Actuator，而 Actuator 需要拿到非 None 的 logger。

Event writes:

| Method | Call |
|--------|------|
| `start()` | `self.history_logger.write("start", {})` |
| `stop()` | `self.history_logger.write("stop", {})` |
| `pause(seconds)` | `self.history_logger.write("pause", {"duration": seconds})` |
| `resume()` | `self.history_logger.write("resume", {})` |

`_build_runtime_components()` passes `self.history_logger` to `Actuator(...)`.

TickState hook: `build_tick_state()` 从 `scheduler.history_logger.last_event_id` 读取当前 event_id 写入 TickState。

### A5. Actuator changes (`core/actuator.py`)

```python
def __init__(self, executor, controller, history_logger=None):
    self.executor = executor
    self.controller = controller
    self._history = history_logger
```

Replace `_write_history()` static method with `self._history.write(...)`.

switch event data:
```python
{"playlist_from": ..., "playlist_to": ..., "tags": {...},
 "similarity": ..., "similarity_gap": ..., "max_policy_magnitude": ...}
```

cycle event data:
```python
{"playlist": ..., "tags": {...}}
```

tags truncated to top-8, weights rounded to 4 decimal places.

Remove `_HISTORY_FILE` constant and `_write_history` static method.

### A6. main.py wiring (`main.py`)

History 是 scheduler 层能力，不是 tray 层能力。两种模式都创建 HistoryLogger。

```python
def _run_console_mode(config_path, logger):
    ...
    from utils.history_logger import HistoryLogger
    history_logger = HistoryLogger(get_data_dir())

    scheduler = WEScheduler(config_path)
    scheduler.history_logger = history_logger  # must precede initialize()
    ...
    scheduler.start()
    ...

def _run_tray_mode(config_path, logger):
    ...
    from utils.history_logger import HistoryLogger
    history_logger = HistoryLogger(get_data_dir())

    scheduler = WEScheduler(config_path)
    scheduler.history_logger = history_logger  # must precede initialize()
    ...
    scheduler.start()

    state_store = StateStore(tick_history=300)
    scheduler.on_tick = lambda s, ctx, res: state_store.update(build_tick_state(s, ctx, res))

    httpd = DashboardHTTPServer(state_store, history_logger)
    httpd.start()
    ...
```

---

## Part B: Frontend

### B1. Dependencies

```bash
cd dashboard && npm install echarts vue-echarts
```

### B2. New composable: `useHistory.ts`

```typescript
// Watches state.value.last_event_id; when it increments, fetches /api/history.
// Covers all event types (switch, cycle, pause, resume, start, stop).

export function useHistory() {
  const segments = ref<Segment[]>([])
  const events = ref<HistoryEvent[]>([])
  const loading = ref(true)
  const lastId = ref(0)

  async function fetchHistory(params?: { from?: string; to?: string; limit?: number }) {
    const query = new URLSearchParams({ limit: '100', ...params }).toString()
    const res = await fetch(`/api/history?${query}`)
    const body = await res.json()
    segments.value = body.segments
    events.value = body.events
  }

  // Watch last_event_id — triggers on ANY event type including wallpaper_cycle
  watch(() => state.value?.last_event_id, (newId, oldId) => {
    if (newId && newId !== oldId) fetchHistory({ limit: 5 })
  })

  return { segments, events, loading, fetchHistory }
}
```

`Segment` type:
```typescript
interface Segment {
  playlist: string | null
  type?: 'pause' | 'dead'
  start: string
  end: string
}
```

`HistoryEvent` type mirrors the tagged union from backend:
```typescript
interface HistoryEvent {
  ts: string
  type: 'playlist_switch' | 'wallpaper_cycle' | 'pause' | 'resume' | 'start' | 'stop'
  data: Record<string, any>
}
```

### B3. Modified composable: `useApi.ts`

现有 1s poll 不变。新增 `useTicks()` 或直接在 `useApi` 中加 5s 间隔的 `/api/ticks` fetch:

```typescript
const ticks = ref<TickState[]>([])

// Poll every 5s for sparkline data
setInterval(async () => {
  const res = await fetch('/api/ticks?count=120')
  ticks.value = await res.json()
}, 5000)
```

### B4. Tabs structure: `DashboardView.vue`

用 `el-tabs` 包裹现有内容：

```html
<el-tabs v-model="activeTab">
  <el-tab-pane label="Live" name="live">
    <!-- 现有 2×2 grid layout -->
  </el-tab-pane>
  <el-tab-pane label="History" name="history">
    <HistoryView />
  </el-tab-pane>
</el-tabs>
```

Provide/inject: `events`, `fetchHistory`, `ticks` 注入到子组件。

### B5. History tab layout: `HistoryView.vue`

上下两段式：

```
┌──────────────────────────────────────────┐
│  [预设: 1h | 6h | 24h | 7d]  [from] [to] │  ← 时间筛选栏
├──────────────────────────────────────────┤
│  Gantt chart (ECharts)                   │  ← 上半：色块时间轴
│  ┌──────┬──────┬────┬────────┐           │
│  │NIGHT │PAUSE │DAY │NIGHT   │           │
│  │CHILL │(30m) │FCS │CHILL   │           │
│  └──────┴──────┴────┴────────┘           │
├──────────────────────────────────────────┤
│  Event list                              │  ← 下半：事件列表
│  ● 00:28  Switch  NIGHT_CHILL→NIGHT_FOCUS│
│     #night 0.77  #clear 0.75             │
│  ● 01:00  Pause  30m                     │
│  ● 01:30  Resume                         │
│  ● 02:15  Cycle  NIGHT_FOCUS             │
│  ...                                     │
└──────────────────────────────────────────┘
```

**Gantt chart (ECharts):**
- X 轴：时间（自适应分辨率：1h 视图显示分钟，24h 视图显示小时）
- Y 轴：单行色块（所有 playlist 共享同一行）
- 颜色：每个 playlist 分配固定颜色（ECharts 调色板 + 固定映射），Pause 区间灰色
- stop → 下一个 start 之间用灰色虚线连接（表示应用未运行）
- Hover tooltip：显示 playlist 名 + 精确时间范围

**Event list:**
- 图标区分事件类型（switch=交换箭头，cycle=刷新，pause=暂停，resume=播放，start/stop=电源）
- 每条显示：时间 + 事件描述 + tags（如有）
- switch 事件展开显示 from→to + top-3 tags

### B6. Sparkline: `ConfidencePanel.vue`

在 similarity 数值下方嵌入 ECharts 迷你折线（sparkline）：

```
┌──────────────────┐
│ Similarity       │
│    0.87          │
│  ╱╲  ╱╲╲╲╲╲    │  ← sparkline (120 data points, ~2 min)
│ ╱  ╲╱      ╲   │
│                  │
│ Gap  0.12        │
│ Magnitude 0.75   │
└──────────────────┘
```

- 高度 ~60px，无坐标轴、无标签（纯 sparkline）
- 数据源：`useApi` 的 `ticks` ref，每 5s 更新
- 颜色：Element Plus 主题色
- 空状态：数据不足 2 点时显示虚线占位

### B7. Polling strategy

1. **History tab 自动刷新**: watch `state.last_event_id` → 变化时沿用当前 `from`/`to`/`preset` 参数重新 fetch。不强制重置为 limit=5 或默认窗口。
2. **初始加载**: tab 激活时 `fetchHistory()` 不带参数，后端返回最近 1h。
3. **手动筛选**: 用户改时间范围 → `fetchHistory({ from, to, limit })`，覆盖当前视图。
4. **Ticks polling**: 与 History 无关，始终 5s poll `/api/ticks?count=120` 给 sparkline。
5. **Live tab**: 保持 1s poll `/api/state`（不变）。

关键约束：**自动刷新永远带上当前的 from/to 参数，不会冲掉用户的手动筛选。**

### B8. Playlist color mapping

Playlists 是动态配置的，颜色需要自动分配：

```typescript
// ECharts 默认调色板循环分配
const PALETTE = ['#5470c6','#91cc75','#fac858','#ee6666','#73c0de','#3ba272','#fc8452','#9a60b4']

function playlistColor(name: string): string {
  // 首次遇到新 playlist 时分配下一个颜色，缓存在 map 中
  if (!colorMap.has(name)) {
    colorMap.set(name, PALETTE[colorMap.size % PALETTE.length])
  }
  return colorMap.get(name)!
}
```

Pause 固定 `#909399`（Element Plus 灰色），stop gap 固定 `#C0C4CC` 虚线。

### B9. Files summary

| File | Action |
|------|--------|
| `utils/history_logger.py` | **New** |
| `core/scheduler.py` | Modify — history_logger attr + event writes |
| `core/actuator.py` | Modify — HistoryLogger injection, remove _write_history |
| `ui/dashboard.py` | Modify — StateStore ring buffer, DashboardHTTPServer params, /api/ticks, /api/history |
| `main.py` | Modify — create + wire HistoryLogger |
| `dashboard/` | |
| `package.json` | Modify — add echarts, vue-echarts |
| `src/composables/useHistory.ts` | **New** — state-change-driven history fetching |
| `src/composables/useApi.ts` | Modify — add /api/ticks polling |
| `src/views/DashboardView.vue` | Modify — el-tabs wrapper |
| `src/views/HistoryView.vue` | **New** — Gantt + event list |
| `src/components/ConfidencePanel.vue` | Modify — add sparkline |
| `src/composables/useApi.ts` | Modify — TickState interface + current_playlist_display |

### B10. Verification

```bash
# ── Console mode (history file only, no HTTP) ──
python main.py --no-tray
cat data/history-2026-04.jsonl          # 应有 start 事件

# ── Tray mode (full HTTP API) ──
python main.py                          # 启动后记下 port
curl http://127.0.0.1:{port}/api/ticks?count=10
curl http://127.0.0.1:{port}/api/history?limit=5
curl "http://127.0.0.1:{port}/api/history?from=2026-04-28T00:00:00&to=2026-04-28T23:59:59"

# ── Frontend ──
cd dashboard && npm run type-check && npm run build
python main.py
# 1. Live tab 正常，ConfidencePanel 有 sparkline
# 2. 切换到 History tab → 时间轴 + 事件列表渲染
# 3. Pause/resume → 事件自动出现（last_event_id 驱动）
# 4. 用户手动选了 7d 范围 → 新事件出现时不冲掉筛选
# 5. stop → start 灰色虚线
```
