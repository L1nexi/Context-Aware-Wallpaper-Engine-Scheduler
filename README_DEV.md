# Context Aware WE Scheduler - 上下文感知壁纸调度系统

## 1. 软件需求规格说明书 (SRS)

### 1.1 项目背景
Wallpaper Engine (WE) 原生功能仅支持简单的定时轮播或基于单一条件的播放列表。本项目旨在开发一个**中间件（Middleware）**，通过收集用户行为（应用使用、输入活跃度）和环境信息（时间、天气），智能决策并控制 WE 切换到最符合当前“心流”的壁纸配置。

### 1.2 核心功能需求 (Functional Requirements)

*   **FR-01 [数据采集]:** 系统需后台静默运行，定时（如每 60s）采集以下数据：
    *   当前前台进程名称及窗口标题。
    *   用户空闲时间（Last Input Time）。
    *   系统时间与大致时段（早/中/晚/深夜）。
    *   *（可选）* 当地实时天气（需调用 API）。
*   **FR-02 [状态映射]:** 系统需能够将采集到的原始数据（如 `code.exe`）映射为抽象的**“上下文状态” (Context State)**（如 `WORK_MODE`）。
*   **FR-03 [智能决策 - 时段分析]:**
    *   **历史趋势分析 (Trend Analysis):** 系统不应频繁切换，而是基于**上一时间段（如过去 1 小时）**的累积状态进行决策。
    *   **多维上下文融合:** 决策需综合考虑：
        *   **用户行为:** 过去一小时的主导活动（工作/游戏/发呆）。
        *   **全局环境:** 当前时间（清晨/深夜）、季节（冬/夏）、天气（雨/晴）。
*   **FR-04 [执行控制 - 机会主义切换]:**
    *   **无感切换 (Seamless Transition):** 即使决策已生成，也必须等待**最佳时机**执行切换。
    *   **触发条件:** 用户长时间空闲（Idle > 5min）、锁屏/解锁时刻、或从全屏应用退出时。
    *   **避免打扰:** 严禁在用户高强度输入或全屏游戏时切换壁纸（避免 0.5s 卡顿）。
*   **FR-05 [配置管理]:** 支持通过 JSON 文件自定义规则（进程名 -> 状态的映射），避免硬编码。

### 1.3 非功能需求 (Non-Functional Requirements)

*   **NFR-01 [性能]:** CPU 占用率应 < 0.5%，内存占用 < 50MB。
*   **NFR-02 [鲁棒性]:** 若 WE 未启动，脚本应自动等待或重试，不应 Crash。

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
*   **职责:** 它是系统的“眼睛”，只负责吐出原始数据，不负责判断好坏。
*   **接口设计:**
    ```python
    class SensorData:
        active_process: str  # e.g., "chrome.exe"
        window_title: str    # e.g., "bilibili - Chrome"
        idle_seconds: float  # e.g., 45.0
        time_period: str     # e.g., "NIGHT"
    ```

#### B. 核心逻辑层 (Context Manager & Arbiter)
*   **职责:** 它是系统的“大脑”。负责将瞬时意图转化为稳态决策。
*   **趋势分析算法 (EMA):**
    *   系统采用 **指数移动平均 (Exponential Moving Average)** 算法对 Tag 权重进行平滑。
    *   **公式:** `Smoothed_Weight = α * Instant_Weight + (1 - α) * Previous_Smoothed_Weight`
    *   **平滑系数 α:** 由配置项 `smoothing_window` 决定。窗口越大，α 越小，系统越“迟钝”但越稳定。
*   **优势:** 
    *   无需存储大量历史数据。
    *   天然支持“主导状态”判定，自动过滤瞬时干扰（如快速切换窗口）。
    *   支持冷启动：首次采样时 α 默认为 1.0。

#### C. 策略执行层 (Policy Enforcer)
*   **职责:** 它是系统的“守门员”。解决“想切但不能切”的矛盾。
*   **逻辑:**
    *   **Pending Decision:** 当 Context Manager 产生新的 `Final_Theme` 时，并不立即执行，而是存入 `Pending` 槽位。
    *   **Opportunity Detector (机会检测):**
        *   每秒检查一次系统状态：
        *   `Is_Idle > 300s`? -> **GO**
        *   `Session_State_Changed` (刚刚解锁/刚刚开机)? -> **GO**
        *   `Fullscreen_Exited` (刚关掉游戏)? -> **GO**
    *   只有满足上述机会条件，才调用执行层应用 `Pending` 的配置，并清空槽位。

#### D. 执行层 (WE Wrapper)
*   **职责:** 封装 `wallpaper32.exe` 的 CLI 调用。
*   **核心策略:**
    *   **Playlist 模式:** 调度器仅负责切换到指定的 Playlist（如 "WORK", "GAME"）。
    *   **资源管理 (Delegation):**
        *   **不干预暂停/播放:** 充分利用 WE 原生设置（全屏暂停、电池暂停、最大化暂停）。调度器**不发送** `pause/stop` 指令。
        *   **只管内容 (Content Only):** 调度器的唯一任务是确保当用户**看到**桌面时，桌面上显示的是正确的壁纸。
    *   **播放控制 (脚本接管):**
        *   Playlist 设置为 **"从不 (Never)"** 自动切换。
        *   调度器不仅选列表，还负责发送 `nextWallpaper` 指令来实现列表内的切图。
        *   **理由:** 彻底消除卡顿干扰，确保只在用户 Idle 时切图。

---

### 2.3 数据结构设计 (配置与状态)

为了应对未来可能出现的复杂需求（如“心情因子”、“季节覆盖”、“组合爆炸”），我们放弃简单的“规则积分表”，转而采用 **"基于标签的加权仲裁架构" (Tag-based Weighted Arbitration)**。

#### 核心概念
1.  **Policy (策略插件):** 独立的逻辑单元，负责观察特定维度的上下文，并输出带有权重的标签建议。
    *   `ActivityPolicy`: 
        *   **Title Rules (优先):** 标题包含 "GitHub" -> 建议 `#work`。
        *   **Process Rules (兜底):** 进程名为 `code.exe` -> 建议 `#work`。
    *   `SeasonalPolicy`: "现在是冬天" -> 建议 `#winter (0.3)`
    *   `TimePolicy`: "现在是深夜" -> 建议 `#night (0.5)`
    *   `MoodPolicy`: "用户手动选了emo" -> 建议 `#chill (1.0)`
2.  **Arbiter (仲裁者):** 收集所有 Policy 的建议，合并标签权重，并应用 EMA 平滑。
    *   合并结果: `{#work: 0.8, #winter: 0.3, #night: 0.5}`
3.  **Matcher (匹配器):** 负责在配置表中寻找最佳 Playlist。
    *   **匹配算法 (Score Calculation):**
        *   遍历所有 Playlist，计算得分：`Score = Sum(Arbiter_Weight[tag])` (仅当 tag 存在于 Playlist 时)。
        *   **示例:**
            *   Playlist A `[#work]`: Score = 0.8
            *   Playlist B `[#work, #night]`: Score = 0.8 + 0.5 = 1.3 (**Winner**)
            *   Playlist C `[#game]`: Score = 0.0
    *   **执行:** 选中得分最高的 Playlist 名称，调用 `wallpaper64.exe -control openPlaylist -playlist "NAME"`。

#### 配置文件示例 (`scheduler_config.json`)

```json
{
  "playlists": [
    { "name": "WORK_WINTER", "tags": ["#work", "#winter"] },
    { "name": "WORK_DEFAULT", "tags": ["#work"] },
    { "name": "GAME_VIBES", "tags": ["#game"] },
    { "name": "LATE_NIGHT_CHILL", "tags": ["#chill", "#night"] }
  ],
  "policies": {
    "activity": { 
      "enabled": true, 
      "weight_scale": 1.0,
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
  },
  "smoothing_window": 60
}
```

### 2.5 防打扰与调度策略 (Disturbance Control)

为了解决“想看新壁纸”与“不想被卡顿打扰”的矛盾，系统采用 **"连续评估 + 瞬时拦截"** 的调度策略。

#### 核心参数
*   **`idle_threshold` (空闲阈值):** 用户无操作持续多少秒后，被视为“空闲状态”。(Default: 60s)
*   **`min_interval` (最小切换间隔):** 上一次切换后，必须等待多少秒才能再次切换。(Default: 1800s / 30min)
*   **`force_interval` (强制切换间隔):** 如果距离上次切换超过此时间，即使不满足空闲条件（但在非全屏下），也尝试切换。(Default: 14400s / 4h)

#### 调度逻辑 (每分钟执行)
1.  **Sense & Aggregate:** 收集数据，更新滑动窗口统计。
2.  **Think:** 计算当前理想的 Playlist (Target)。
3.  **Check Intent:** 
    *   如果 `Target != Current_Playlist`，产生**切换列表**意图。
    *   如果 `Target == Current_Playlist`，产生**切图 (Next Wallpaper)**。
4.  **Filter (拦截器):**
    *   **冷却检查:** `Time_Since_Last_Switch < min_interval`? -> **拦截**。
    *   **空闲检查:** `User_Idle_Time < idle_threshold`?
        *   是 -> 检查 `Time_Since_Last_Switch > force_interval`?
            *   是 -> **放行** (兜底策略)。
            *   否 -> **拦截**。
        *   否 -> **放行** (用户空闲，最佳时机)。
5.  **Act:** 通过拦截器后，执行切换（打开新列表或重载当前列表以切图）。

---

## 3. 开发路线图 (Roadmap)

作为练手项目，建议分三个迭代（Sprint）完成：

### Phase 1: 骨架与基础 (MVP)
*   **目标:** 程序能跑通，能读取 Config，能控制 WE。
*   **任务:**
    1.  实现 `WE_Wrapper` 类（已完成）。
    2.  实现 `ConfigLoader`，读取 JSON。
    3.  实现简单的 `ProcessDetector`，只通过 `print` 输出当前识别到的状态（不切壁纸）。

### Phase 2: 状态机与防打扰
*   **目标:** 接入真实逻辑，实现“智能且无感”的切换。
*   **任务:**
    1.  实现 `IdleDetector` (ctypes 调用)。
    2.  编写“主循环逻辑”：采样 -> 查表 -> 缓冲 -> 判空闲 -> 切换。
    3.  调试 `browser_keywords` 功能（需要获取浏览器窗口标题）。

### Phase 3: 环境因子 (Add-ons)
*   **目标:** 加入天气和时间维度的融合。
*   **任务:**
    1.  接入 OpenWeatherMap API。
    2.  修改决策逻辑：允许“混合状态”。
        *   例如：逻辑判定是 `WORK`，且 天气是 `RAIN` -> 尝试寻找 `WORK_RAIN` 的 Profile，如果没找到，回退到 `WORK`。

---

### 4. 这里的“坑”在哪？(Risk Analysis)

在开始写代码前，预判一下潜在风险：

1.  **浏览器标题获取:** 现代浏览器有多进程架构，直接用 `GetForegroundWindow` 获取的可能是容器进程，标题可能为空。需要做一些特殊的过滤处理（Win32 API 的坑）。
2.  **全屏游戏干扰:** 有些游戏（特别是独占全屏）极其反感后台切窗口操作，虽然 WE 是底层渲染，但脚本通过 CLI 调用时可能会弹出一个极其短暂的 CMD 黑框（即使 hidden 也有可能抢焦点）。
    *   *解决方案:* 必须确保 `subprocess` 调用时使用 `creationflags=subprocess.CREATE_NO_WINDOW`。
3.  **频繁 I/O:** 别每秒钟都读一次 json 文件。Config 应该在启动时加载进内存，或者监听文件变更。
