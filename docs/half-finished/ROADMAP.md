# Roadmap — 未来开发方向

> 记录尚未实现但已完成可行性讨论的功能方向。  
> 已完成的历史路线图见 `docs/README_DEV.md` Section 3（存档）。  
> 具体 Bug / 架构问题见 `docs/TODOS.md`。

---

## R1 — 系统状态 Dashboard ✅ 已完成

**实际实现** (`ui/dashboard.py`, `ui/webview.py`, `dashboard/`, `main.py`):

- Hook: `scheduler.on_tick(scheduler, context, result)` — 每 tick 由调度循环调用
- StateStore: `update(tick_state)` / `read()` with `threading.Lock`
- HTTP server: Bottle-based, binds `127.0.0.1:0`, serves `/api/state` + `/api/health` + static SPA
- Frontend: Vue 3 + TypeScript + Element Plus, 1s polling, zombie detection
- Window: pywebview (WebView2), spawned as subprocess from tray
- TickState: 13 fields including context data (active_window, idle_time, cpu, fullscreen) beyond the original 6

**集成方式：**

- ✅ 托盘菜单「Dashboard」入口 → 独立子进程 + pywebview 窗口
- ✅ 与 History 时间轴合并（R3 已完成）

---

## R2 — 自动播单 Tag 生成（离线脚本）

**动机：** 手工给每个 WE playlist 标注 tag 权重耗时且主观。Workshop 目录 `steamapps/workshop/content/431960/{id}/project.json` 已包含壁纸元数据，可离线批量处理。

**可用元数据（project.json）：**

- `title`, `description` — 文字描述
- `tags` — WE 内置分类标签（如 `"Anime"`, `"Nature"`, `"Abstract"`）
  > 但 WE 标签过于粗糙，且与我们 tag 语义不完全对齐。大部分标签并不包含细粒度语义信息。整体来说利用价值有限。
- 预览图 `preview.gif` / `preview.jpg`
  > 同样，预览图分辨率较低且内容不一定具有代表性，直接用 CLIP 可能效果不佳。
  > 需要考虑解包 .pkg 文件 / 截取视频关键帧来获取更高质量的图像输入。

**三层方案，复杂度递增：**

### 层 1 — WE 内置 tag 静态映射（推荐起点）

维护一张 `WE_TAG → 我们的 tag + 权重` 映射表，纯字典查找，零 ML 依赖。

```python
WE_TAG_MAP = {
    "Nature":   {"#day": 0.6, "#chill": 0.4},
    "Dark":     {"#night": 0.8, "#chill": 0.2},
    "Anime":    {"#chill": 0.5},
    "Abstract": {},  # skip
    ...
}
```

产出：给定 `project.json`，输出可直接粘贴进 `scheduler_config.json` 的 playlist tags 建议。

局限：如上所述，“WE 标签过于粗糙，且与我们 tag 语义不完全对齐。大部分标签并不包含细粒度语义信息。整体来说利用价值有限。”

### 层 2 — 文字嵌入分类（中等）

用 `title + description` 文本 → 本地 sentence-transformers 嵌入 → 与每个我们 tag 的描述文本做余弦相似度。无需视觉，适合有详细描述的壁纸。

### 层 3 — CLIP 视觉分类（最准，有已知局限）

**CLIP 的核心问题：** CLIP 嵌入空间是通用图文对齐空间，不懂我们 tag 的语义边界（`#chill` 对它毫无意义）。

**解法：锚点标定（无需微调）**

1. 为每个 tag 手工选 5–10 张"典型壁纸"作为正例。
2. 取其 CLIP 图像嵌入的均值作为该 tag 的**原型向量**。
3. 新壁纸图像 → CLIP 嵌入 → 与所有原型向量做余弦相似度 → 归一化为权重。

标注成本极低（每 tag 5 张 × N tags），且原型向量可复用。

**实现形式：** 独立离线脚本 `scripts/tag_generator.py`，不集成进调度器主体，产出 JSON 片段供用户手动审核后合并。

**优先级：** 低（先做层 1，按需推进）| 依赖：无

---

## R3 — History 事件日志与消费 ✅ 已完成

**实际实现** (`utils/history_logger.py`, `ui/dashboard.py`, `core/actuator.py`, `dashboard/src/views/HistoryView.vue`):

- `HistoryLogger`: 线程安全、按月分片 (`history-{YYYY}-{MM}.jsonl`)、UTC 秒精度时间戳
- 六种 tagged union 事件: `start` / `stop` / `pause` / `resume` / `playlist_switch` / `wallpaper_cycle`
- `EventType` StrEnum + `EventLogger` Protocol — 消除字符串重复，依赖方向 `utils → core`
- `/api/history?limit=&from=&to=` — 返回 `{segments, events}`，后端计算 Gantt 连续区块
- `HistoryView.vue` — ECharts Gantt 时间线 + 事件列表，含过滤器和自动刷新
- `last_event_id` 单调计数器 — 前端通过 watch 实现增量自动刷新
- 事件携带 top-8 标签快照 + similarity/gap/magnitude 供调优分析

**优先级：** ✅ 已完成

---

## R3.1 — 历史高级消费（层 3：回放与审计）

给定时间戳，重建当时的 `aggregated_tags` 快照，回答"为什么那时切换到了 X"。当前事件已记录 top-8 tags 和 similarity/magnitude 元数据，大部分审计需求已可满足。完整的向量快照回放需要额外的存储/查询支持。

**优先级：** 低 | 依赖：R3

---

## 优先级总览

| ID    | 功能                           | 优先级 | 依赖  |   估计规模    |
| ----- | ------------------------------ | :----: | ----- | :-----------: |
| ~~R1~~ | ~~Dashboard (状态仪表盘)~~     |   ✅   | —     |    已完成    |
| ~~R3~~ | ~~History 事件日志与消费~~      |   ✅   | ~~R1~~ |    已完成    |
| R2-L1 | 自动 tag 生成·层 1（映射表）   |  ★★☆   | —     | 小（~100 行） |
| R2-L2 | 自动 tag 生成·层 2（文字嵌入） |  ★☆☆   | —     |      中       |
| R2-L3 | 自动 tag 生成·层 3（CLIP）     |  ★☆☆   | R2-L1 |      大       |

## R4 - Controller 增强

**基础**：经历 tag 语义化重构后，Policy 返回更多样的结果，同时 MatchResult 返回更多信息。

```python
@dataclass
class MatchResult:
    best_playlist: str
    similarity: float
    aggregated_tags: Dict[str, float] = field(default_factory=dict)
    similarity_gap: float = 0.0        # sim(1st) - sim(2nd); 0 if only one playlist
    max_policy_magnitude: float = 0.0  # max(salience * intensity * weight_scale) across policies
```

Controller 可以利用上述信息进行更智能的决策：

### 1. 动态 cooldown

当前 cooldown 是静态策略。未来，Controller 可以根据 MatchResult 中的信息来判断当前决策的"信心度"。如使用 similarity_gap 、 max_policy_magnitude、甚至特定 tag 的 intensity 或 seliance 来动态调整 cooldown。从而实现高信心时快速响应，低信心时谨慎等待。
