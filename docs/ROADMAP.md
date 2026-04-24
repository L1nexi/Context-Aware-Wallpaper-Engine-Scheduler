# Roadmap — 未来开发方向

> 记录尚未实现但已完成可行性讨论的功能方向。  
> 已完成的历史路线图见 `docs/README_DEV.md` Section 3（存档）。  
> 具体 Bug / 架构问题见 `docs/TODOS.md`。

---

## R1 — 系统状态 Dashboard

**动机：** 用户无法直接观察调度器内部状态（当前聚合 tag、各 Policy 贡献、匹配相似度），只能靠日志排查。Dashboard 是用户理解系统"正在想什么"的直接界面。

**可用数据（调度循环每 tick 已产生）：**

- `aggregated_tags: Dict[str, float]` — 按权重排序的 Top-N 标签
- `similarity: float` — 当前环境向量与最佳 playlist 的余弦相似度
- `current_playlist: str` — 当前播放列表
- `last_switch_time` — 上次切换时间戳
- 调度器暂停状态及剩余时间

**实现方案：Observer hook**

在 `WEScheduler` 上增加 `on_tick_state` callable 属性（与 `on_auto_resume` 同模式），调度循环每 tick 推送一个轻量快照 `TickState`。Dashboard 窗口注册此 hook，仅在窗口可见时消费（否则 no-op）。

```python
@dataclass
class TickState:
    ts: float
    current_playlist: str
    similarity: float
    top_tags: List[Tuple[str, float]]   # top 8, sorted by weight
    paused: bool
    pause_until: Optional[float]
```

**集成方式：**

- Phase 1：托盘菜单增加「状态...」(`open_dashboard`) 入口，弹出 tkinter 轻量窗口，1s 刷新。
- Phase 2：与 history.jsonl 时间轴合并（见 R3）。

**与现有代码的影响面：** 仅在 `scheduler.py` 的 `_run_loop` 末尾添加 hook 调用；不影响任何现有逻辑。

**优先级：** 中 | 依赖：无

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

## R3 — history.jsonl 消费

**动机：** `data/history.jsonl` 记录了每次播放列表切换和壁纸循环事件，是调优和理解系统行为的宝贵数据，当前完全未被消费。

**三层价值：**

### 层 1 — 时间轴可视化

将切换事件渲染为时间轴，直观显示：

- 哪个时间段系统频繁切换（可能说明配置 threshold 太低）
- 各 playlist 的实际占用时长分布

实现：轻量 HTML 输出（纯 Python 生成，无前端构建依赖）或直接集成进 Dashboard（R1）。

### 层 2 — 调优辅助

- 标注每次切换时的 `similarity` 值——持续低相似度 → playlist 标签需要调整
- 显示 top tags 演变曲线 → 理解 Policy 贡献趋势

### 层 3 — 回放与审计

给定时间戳，重建当时的 `aggregated_tags` 快照，回答"为什么那时切换到了 X"。需要在 history.jsonl 中记录更完整的快照（当前只记录 top5 tags）。

**集成建议：** 层 1+2 合并进 Dashboard（R1）的"历史"标签页，共用 `on_tick_state` 数据流；层 3 按需单独实现。

**优先级：** 中（依赖 R1 先行）| 与 R1 共用 UI 入口

---

## 优先级总览

| ID    | 功能                           | 优先级 | 依赖  |   估计规模    |
| ----- | ------------------------------ | :----: | ----- | :-----------: |
| R1    | Dashboard (状态仪表盘)         |  ★★★   | —     | 中（~300 行） |
| R3    | history 时间轴（集成进 R1）    |  ★★☆   | R1    |      小       |
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
