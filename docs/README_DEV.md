# Context Aware WE Scheduler - 上下文感知壁纸调度系统

## 1. 软件需求规格说明书 (SRS)

### 1.1 项目背景

Wallpaper Engine (WE) 原生功能仅支持简单的定时轮播或基于单一条件的播放列表。本项目旨在开发一个**中间件（Middleware）**，通过收集用户行为（应用使用、输入活跃度）和环境信息（时间、天气），智能决策并控制 WE 切换到最符合当前“心流”的壁纸配置。

### 1.2 核心功能需求 (Functional Requirements)

- **FR-01 [数据采集]:** 系统需后台静默运行，定时（如每 60s）采集以下数据：
  - 当前前台进程名称及窗口标题。
  - 用户空闲时间（Last Input Time）。
  - 系统时间与大致时段（早/中/晚/深夜）。
  - _（可选）_ 当地实时天气（需调用 API）。
- **FR-02 [状态映射]:** 系统需能够将采集到的原始数据（如 `code.exe`）映射为抽象的**“上下文状态” (Context State)**（如 `WORK_MODE`）。
- **FR-03 [智能决策 - 时段分析]:**
  - **历史趋势分析 (Trend Analysis):** 系统不应频繁切换，而是基于**上一时间段（如过去 1 小时）**的累积状态进行决策。
  - **多维上下文融合:** 决策需综合考虑：
    - **用户行为:** 过去一小时的主导活动（工作/游戏/发呆）。
    - **全局环境:** 当前时间（清晨/深夜）、季节（冬/夏）、天气（雨/晴）。
- **FR-04 [执行控制 - 择机切换]:**
  - **无感切换 (Seamless Transition):** 即使决策已生成，也必须等待**最佳时机**执行切换。
  - **触发条件:** 用户长时间空闲（Idle > Idel_Threshold ）、锁屏/解锁时刻、或从全屏应用退出时。
  - **避免打扰:** 严禁在用户高强度输入或全屏游戏时切换壁纸（避免小卡顿）。
- **FR-05 [配置管理]:** 支持通过 JSON 文件自定义规则（进程名 -> 状态的映射），避免硬编码。

### 1.3 非功能需求 (Non-Functional Requirements)

- **NFR-01 [性能]:** CPU 占用率应 < 0.5%。
- **NFR-02 [鲁棒性]:** 若 WE 未启动，脚本应自动等待或重试，不应 Crash。

### 1.4 构建与发布

- **打包工具:** 使用 `PyInstaller` 将 Python 脚本打包为独立的可执行文件 (`.exe`)。
- **构建脚本:** 运行 `build.bat` 即可自动安装依赖并生成 `dist/WEScheduler.exe`。
- **发布内容:** `dist/` 目录包含可执行文件、默认配置文件及说明文档。

---

## 2. 系统设计文档 (SDD)

### 2.1 总体架构 (Architecture)

采用 **"感知-决策-执行" (Sense-Think-Act)** 循环架构，配合 **配置文件** 驱动。

```mermaid
(概念图)
[Sensors] --> [Context Manager (State Machine)] --> [Policy Enforcer] --> [WE Wrapper]
     ^                  ^
     |                  |
[OS API]          [Config.json]
```

### 2.2 模块详细设计

#### A. 感知层 (Sensor Module)

- **职责:** 它是系统的“眼睛”，只负责吐出原始数据，不负责判断好坏。
- **接口设计:**

  ```python
  class Sensor(ABC):
      @abstractmethod
      def collect(self) -> Any:
          """Collects data from the sensor."""
          pass
  ```

#### B. 核心逻辑层 (Context Manager & Arbiter)

- **职责:** 它是系统的“大脑”。负责将瞬时意图转化为稳态决策。
- **向量化与归一化 (Vectorization & Normalization):**

  各 Policy 的归一化策略不同，体现了"适合的才是最好的"原则：

  | Policy         | 归一化方式                      | 理由                                     |
  | -------------- | ------------------------------- | ---------------------------------------- |
  | TimePolicy     | L2 归一化 + `weight_scale` 缩放 | 全天恒定激活，需统一向量模长             |
  | SeasonPolicy   | L2 归一化 + `weight_scale` 缩放 | 全年恒定激活，同 TimePolicy              |
  | ActivityPolicy | 无归一化，EMA 平滑原始权重      | 向量模长随活跃度自然衰减，体现"忙碌程度" |
  | WeatherPolicy  | 无归一化，使用强度模型          | 向量模长随天气严重性变化，体现"恶劣程度" |
  - **Hann 窗插值 (TimePolicy & SeasonPolicy):**
    - 时间/季节不再是离散状态，而是连续向量。在两个峰值之间，系统使用 **Hann 窗** 对相邻标签同时赋权，实现平滑过渡。
    - 模块级 helper: `_hann(d, H)` 计算距峰值距离 `d` 处的 Hann 窗权重（半宽 `H`），`_circular_distance(a, b, period)` 处理循环时间轴（如午夜跨越）。
    - TimePolicy: 4 个峰值 (dawn/day/sunset/night)，半宽 `H=6h`。
    - SeasonPolicy: 4 个峰值 (spring/summer/autumn/winter)，半宽 `H≈91.25d`。
  - **WeatherPolicy 强度模型:**
    - 完整的 OWM 天气代码映射（200–804）写入 `_ID_TAGS`，`_MAIN_FALLBACK` 处理未知代码。
    - 强度分 4 个等级 (T1–T4)，权重分别为 0.2 / 0.5 / 0.8 / 1.0，直接体现天气严重性，无 L2 归一化。
  - **趋势分析算法 (EMA - ActivityPolicy 专属):**
    - 系统仅对 **ActivityPolicy** (高频波动源) 采用 **指数移动平均 (Exponential Moving Average)** 算法对 Tag 权重进行平滑。
    - **公式:** `Smoothed_Weight = α * Instant_Weight + (1 - α) * Previous_Smoothed_Weight`
    - **平滑系数 α:** 由 `ActivityPolicy` 配置项 `smoothing_window` 决定。

- **Arbiter (仲裁者):**
  - 作为纯粹的 **加权聚合器 (Weighted Aggregator)**。
  - 它将各 Policy 输出的向量乘以各自的 `weight_scale` 后进行叠加。

#### C. 执行层 (Actuator & WE Wrapper)

- **Actuator (执行器):**
  - **职责:** 系统的“手”，负责执行最终的决策。
  - **逻辑:**
    - 接收 `Matcher` 选出的最佳播放列表。
    - 咨询 `DisturbanceController` 是否允许操作。
    - 如果目标播放列表与当前不同，且允许切换 -> 切换播放列表。
    - 如果目标播放列表与当前相同，且允许轮播 -> 轮播下一张壁纸。
- **WE Wrapper (WEExecutor):**
  - **职责:** 封装 `wallpaper64.exe` 的 CLI 调用。
- **核心策略:**
  - **Playlist 模式:** 调度器仅负责切换到指定的 Playlist（如 "WORK", "GAME"）。
  - **资源管理 (Delegation):**
    - **不干预暂停/播放:** 充分利用 WE 原生设置（全屏暂停、电池暂停、最大化暂停）。调度器**不发送** `pause/stop` 指令。
    - **只管内容 (Content Only):** 调度器的唯一任务是确保当用户**看到**桌面时，桌面上显示的是正确的壁纸。
  - **播放控制 (脚本接管):**
    - Playlist 设置为 **"从不 (Never)"** 自动切换。
    - 调度器不仅选列表，还负责发送 `nextWallpaper` 指令来实现列表内的切图。
    - **理由:** 彻底消除卡顿干扰，确保只在用户 Idle 时切图。

#### D. 辅助模块 (Utilities)

- **日志系统 (Logger):**
  - 采用 `RotatingFileHandler`，限制日志文件大小（5MB）并保留历史备份，防止磁盘空间溢出。
  - 区分 `INFO` (关键事件) 和 `DEBUG` (详细采样数据)。
- **异常恢复 (Recovery):**
  - **进程监控:** `WEExecutor` 每次执行指令前都会检查 `wallpaper32/64.exe` 是否存活。
  - **自动拉起:** 若检测到 WE 进程缺失，系统会尝试根据配置路径自动重新启动 WE，实现无人值守运行。

---

### 2.3 数据结构设计 (配置与状态)

为了应对未来可能出现的复杂需求（如“心情因子”、“季节覆盖”、“组合爆炸”），我们放弃简单的“规则积分表”，转而采用 **"基于标签的加权仲裁架构" (Tag-based Weighted Arbitration)**。

#### 核心概念

1. **Policy (策略插件):** 独立的逻辑单元，负责观察特定维度的上下文，并输出带有权重的标签建议。
   - `ActivityPolicy`:
     - **Title Rules (优先):** 标题包含 "GitHub" -> 建议 `#work`。
     - **Process Rules (兜底):** 进程名为 `code.exe` -> 建议 `#work`。
   - `SeasonalPolicy`: "现在是冬天" -> 建议 `#winter`
   - `TimePolicy`: "现在是深夜" -> 建议 `#night`
   - `MoodPolicy`: "用户手动选了 emo" -> 建议 `#chill` [待实现]
2. **Arbiter (仲裁者):** 收集所有 Policy 的建议，合并标签权重。
   - 合并结果: `{#work: 0.8, #winter: 0.3, #night: 0.5}`
3. **Matcher (匹配器):** 负责在配置表中寻找最佳 Playlist。
   - **匹配算法 (Cosine Similarity):**
     - 系统将当前环境标签和播放列表标签均视为**高维向量**。
     - 计算环境向量与各播放列表向量之间的**余弦相似度 (Cosine Similarity)**。
     - **公式:** $Sim = \frac{V_{env} \cdot V_{pl}}{\|V_{env}\| \|V_{pl}\|}$
     - **核心数学性质:**
       - **长度归一化 (Length Normalization):** 惩罚“杂讯”。如果一个播放列表虽然包含了当前需要的标签，但还夹杂了大量无关标签，其模长变大，导致相似度下降。这保证了系统优先选择“纯度”更高的列表。
       - **方向一致性 (Scale Invariance):** 权重比例决定方向。`{#work: 10, #night: 10}` 与 `{#work: 1, #night: 1}` 在向量空间中是重合的。这降低了用户配置权重时的心智负担。
       - **正交性 (Orthogonality):** 无关即零。如果两个向量没有共同的非零维度，相似度为 0。
   - **执行:** 选中相似度最高的 Playlist 名称，调用 `wallpaper64.exe -control openPlaylist -playlist "NAME"`。
   - **权重支持:** 播放列表的 `tags` 现在支持字典格式（如 `{"#work": 1.0, "#night": 0.5}`），允许用户定义不同标签在列表中的重要程度。

#### 配置文件示例 (`scheduler_config.json`)

```json
{
  "playlists": [
    { "name": "WORK_WINTER", "tags": { "#work": 1.0, "#winter": 1.0 } },
    { "name": "WORK_DEFAULT", "tags": { "#work": 1.0 } },
    { "name": "GAME_VIBES", "tags": { "#game": 1.0 } },
    { "name": "LATE_NIGHT_CHILL", "tags": { "#chill": 1.0, "#night": 1.0 } }
  ],
  "policies": {
    "activity": {
      "enabled": true,
      "weight_scale": 1.0,
      "smoothing_window": 60,
      "rules": { "Code.exe": "#work" },
      "title_rules": { "GitHub": "#work", "Bilibili": "#chill" }
    },
    "season": { "enabled": true, "weight_scale": 0.5 },
    "mood": { "enabled": true, "weight_scale": 2.0 }
  },
  "disturbance": {
    "idle_threshold": 60,
    "min_interval": 1800,
    "force_interval": 14400
  }
}
```

### 2.5 防打扰与调度策略 (Disturbance Control)

为了解决“想看新壁纸”与“不想被卡顿打扰”的矛盾，系统采用 **"连续评估 + 瞬时拦截"** 的调度策略。

#### 核心参数

- **`idle_threshold` (空闲阈值):** 用户无操作持续多少秒后，被视为“空闲状态”。(Default: 60s)
- **`min_interval` (最小切换间隔):** 上一次切换后，必须等待多少秒才能再次切换。(Default: 1800s / 30min)
- **`force_interval` (强制切换间隔):** 如果距离上次切换超过此时间，即使不满足空闲条件（但在非全屏下），也尝试切换。(Default: 14400s / 4h)

#### 调度逻辑 (每分钟执行)

1. **Sense & Aggregate:** 收集数据，更新滑动窗口统计。
2. **Think:** 计算当前理想的 Playlist (Target)。
3. **Check Intent:**
   - 如果 `Target != Current_Playlist`，产生**切换列表**意图。
   - 如果 `Target == Current_Playlist`，产生**切换到下一壁纸**意图。
4. **Filter (拦截器):**
   - **冷却检查:** `Time_Since_Last_Switch < min_interval`? -> **拦截**。
   - **空闲检查:** `User_Idle_Time < idle_threshold`?
     - 是 -> 检查 `Time_Since_Last_Switch > force_interval`?
       - 是 -> **放行** (兜底策略)。
       - 否 -> **拦截**。
     - 否 -> **放行** (用户空闲，最佳时机)。
5. **Act:** 通过拦截器后，执行切换（打开新列表或重载当前列表以切图）。

---

## 3. 开发路线图 (Roadmap)

### Phase 1: 骨架与基础 (MVP) - [DONE]

- **任务:**
  1. 实现 `WE_Wrapper` 类。
  2. 实现 `ConfigLoader`，读取 JSON。
  3. 实现基础 `ProcessDetector`。

### Phase 2: 状态机与防打扰 - [DONE]

- **任务:**
  1. 实现 `IdleDetector` (Win32 API)。
  2. 实现 **EMA 趋势分析** 算法。
  3. 实现 **Disturbance Controller** (冷却时间与空闲检测)。
  4. 实现 **NumPy 余弦相似度** 匹配算法。

### Phase 3: 环境因子与工程化 - [DONE]

- **任务:**
  1. 接入 **OpenWeatherMap API** (天气因子)。
  2. 实现 **SeasonPolicy** (季节因子)。
  3. 集成 **Rotating Logging** 系统。
  4. 实现 **WE 进程自动恢复** 机制。

### Phase 4.1: 易用性与轻量化 - [DONE]

- **目标:** 降低用户部署门槛，提供更友好的交互体验。
- **任务:**
  1. **移除 NumPy 依赖:**
     - 目前 `numpy` 仅用于简单的向量点积和模长计算。
     - 计划使用原生 Python 实现，以减少打包体积。
  2. **系统托盘图标 (System Tray):**
     - 引入 `pystray` 库。
     - 提供可视化的状态指示（运行中/暂停）。
     - 提供右键菜单：`Pause`, `Resume`, `Open Config`, `Exit`。
  3. **一键安装包:**
     - 使用 `PyInstaller` 打包为单文件 `.exe`。
     - 配合 Inno Setup 制作安装程序，自动处理开机启动项。

### Phase 4.2: 交付与优化 - [DONE]

- **任务:**
  1. ✅ PyInstaller 打包为 `dist/WEScheduler.exe`（PyInstaller 6.18.0）。
  2. ✅ 移除 `if __name__ == "__main__"` 测试代码块（`sensors.py`）。
  3. ✅ 将 magic numbers 提取为具名常量（`controller.py`: `_DEFAULT_IDLE_THRESHOLD` 等；`matcher.py`: `_MIN_SIMILARITY`）。
  4. ✅ `config_loader.py` 添加加载日志（`logger.info("Config loaded from: %s", ...)`）。
  5. ✅ `logger.py` 补全 `-> logging.Logger` 返回类型注解。
  6. ✅ `icon_generator.py` 清理无效 `"bg"` 颜色键。
  7. ✅ `scheduler.py` 简化 `sys.stdout` 判断逻辑。
  8. ✅ WeatherPolicy: `timeout` → `request_timeout`（可配置）；`status_code == 200` → `response.ok`。
  9. ✅ 补全开发文档（README_DEV.md）Hann 窗归一化策略表 + 代码质量约定章节。

---

## 4. 托盘 UI 与调度器交互设计

### 4.1 系统托盘模块 (`core/tray.py`)

- **技术栈:** pystray(Win32 Shell_NotifyIcon) + tkinter (自定义弹窗) + PIL (图标生成)
- **国际化:** `utils/i18n.py` 提供 `t(key)` 函数，基于 `locale.getdefaultlocale()` 自动选择 zh/en。
- **菜单动态性:**
  - 状态文本、Resume 可见性等使用 pystray callable 属性。
  - **注意 (Win32 陷阱):** pystray Win32 后端缓存 HMENU——callable 仅在菜单**构建**时求值一次，每次右键**不会**重新求值。因此任何非菜单回调引起的状态变更必须手动调用 `icon.update_menu()` 以重建 HMENU。
- **暂停功能:**
  - 支持预设时长(30m / 2h / 12h / 24h / 48h / 1w)、无限期暂停、自定义时长(tkinter 弹窗)。
  - 统一 API: `scheduler.pause(seconds=None)`，`None` 表示无限期。
- **`switch_on_start` 配置:** 位于 `disturbance` 配置块中，控制启动时是否立即切换壁纸。`False` 时通过初始化 `last_playlist_switch_time = time.time()` 利用冷却期阻止首次切换。

### 4.2 Tray ↔ Scheduler 状态同步

状态同步通过 `TrayIcon._sync_icon()` 实现，该方法同时刷新图标图片和 Win32 HMENU。

**同步触发路径:**

| 场景                    | 触发方         | 机制                                             |
| ----------------------- | -------------- | ------------------------------------------------ |
| 菜单点击 Pause / Resume | pystray 线程   | handler 内直接调用 `_sync_icon()`                |
| 自定义弹窗确认暂停      | tkinter 线程   | `on_confirm` 回调中直接调用 `_sync_icon()`       |
| 定时暂停自动到期        | scheduler 线程 | `scheduler.on_auto_resume` hook → `_sync_icon()` |

> **设计备注:** `on_auto_resume` 是 WEScheduler 上的一个简单 callable 属性 (hook)，由 TrayIcon 在 `__init__` 中赋值。此处**未采用标准观察者模式** (即未实现 `add_listener/remove_listener` 列表)——因为当前只有一个观察者 (TrayIcon)，引入完整的观察者基础设施属于过度设计。如果未来出现第二个订阅者，应迁移为标准观察者或 Event 机制。

---

## 5. 代码质量约定

### 5.1 Policy 归一化策略一览

| Policy         | 文件               | 归一化         | 关键配置项                         |
| -------------- | ------------------ | -------------- | ---------------------------------- |
| TimePolicy     | `core/policies.py` | L2 + scale     | `weight_scale`, peaks in `_PEAKS`  |
| SeasonPolicy   | `core/policies.py` | L2 + scale     | `weight_scale`, `H ≈ 91.25d`       |
| ActivityPolicy | `core/policies.py` | 无（EMA衰减）  | `smoothing_window`, `weight_scale` |
| WeatherPolicy  | `core/policies.py` | 无（强度模型） | `weight_scale`, `request_timeout`  |

### 5.2 Hann 窗 Helper 使用规范

```python
# 模块级 helper，在 core/policies.py 顶部定义
def _hann(d: float, H: float) -> float:
    """Hann 窗权重，d=与峰值距离，H=半宽（超出返回0）"""

def _circular_distance(a: float, b: float, period: float) -> float:
    """循环轴上两点距离（如时间轴跨午夜、日历年跨岁末）"""
```

新增需要"平滑峰值"的时间/季节类 Policy 时，直接调用这两个 helper，不要重新实现。

### 5.3 WeatherPolicy 扩展指南

- OWM 条件码映射在 `_ID_TAGS: dict[int, tuple[str, float]]` 中维护，格式 `{code: (tag, intensity)}`。
- 强度等级约定: T1=轻微(0.2) / T2=中等(0.5) / T3=较强(0.8) / T4=极端(1.0)。
- 未知天气码通过 `_MAIN_FALLBACK: dict[str, tuple[str, float]]` 按 `main` 字段降级处理。
- 返回值: `{tag: intensity * self.weight_scale}`（**不做 L2 归一化**）。

### 5.4 DisturbanceController 默认常量

定义于 `core/controller.py` 顶部，修改默认行为时在此处调整：

```python
_DEFAULT_IDLE_THRESHOLD  = 60    # 秒，用户空闲判定阈值
_DEFAULT_PLAYLIST_MIN    = 1800  # 秒，播放列表最小切换间隔
_DEFAULT_PLAYLIST_FORCE  = 14400 # 秒，强制切换超时
_DEFAULT_WALLPAPER_MIN   = 600   # 秒，壁纸最小切换间隔
```

### 5.5 Matcher 相似度阈值

`core/matcher.py` 中的 `_MIN_SIMILARITY = 0.001` 防止零向量命中。若无任何播放列表的余弦相似度超过此阈值，Matcher 返回 `None`，Actuator 跳过本轮切换。

### 5.6 日志命名惯例

所有模块使用 `logging.getLogger("WEScheduler.<SubName>")` 层级命名，例如：

- `WEScheduler.Scheduler` — 主调度循环
- `WEScheduler.Config` — 配置加载器
- `WEScheduler.Tray` — 系统托盘
- `WEScheduler.Policies` — 各 Policy 插件
