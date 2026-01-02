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

#### B. 核心逻辑层 (Context Manager)
*   **职责:** 它是系统的“大脑”。维护一个**时间桶 (Time Bucket)**，进行长周期的状态积分。
*   **核心算法 (时段加权积分法):**
    *   **采样:** 每分钟记录一次当前瞬间状态（如 `Coding`, `Gaming`, `Browsing`）。
    *   **积分:** 在一个决策周期（如 60 分钟）内，统计各状态的占比。
        *   Example: 40mins `Coding` + 10mins `Browsing` + 10mins `Idle` -> **Dominant State = WORK**.
    *   **上下文融合 (Context Fusion):**
        *   将 `Dominant State` 与 `Global Context` 结合。
        *   公式: `Final_Theme = f(Activity_State, Time_of_Day, Weather, Season)`
        *   Example: `WORK` + `NIGHT` + `RAIN` -> 查找标签为 `[Quiet, Dark, Rain]` 的壁纸配置。

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

这是解决“硬编码”问题的关键。我们需要设计一个 `scheduler_config.json`，让用户定义模式（Mode）及其触发规则。

```json
{
  "settings": {
    "decision_interval": 60,      // 决策周期(秒)
    "history_window_size": 60,    // 历史窗口大小(分钟)
    "switch_cooldown": 300        // 切换冷却时间(秒)
  },
  "modes": {
    "WORK": { "playlist": "WORK", "priority": 10 },
    "GAME": { "playlist": "GAME", "priority": 20 },
    "CHILL": { "playlist": "列表4", "priority": 5 }
  },
  "rules": [
    // 进程规则: 发现特定进程运行时，给对应模式加分
    { "type": "process", "keyword": "code.exe", "target_mode": "WORK", "weight": 1.0 },
    { "type": "process", "keyword": "steam.exe", "target_mode": "GAME", "weight": 0.5 },
    // 时间规则: 在特定时间段，给对应模式加基础分
    { "type": "time", "start": "09:00", "end": "18:00", "target_mode": "WORK", "weight": 0.3 },
    { "type": "time", "start": "22:00", "end": "02:00", "target_mode": "CHILL", "weight": 0.8 }
  ]
}
```

**决策逻辑 (Score Calculation):**
1.  **动态计算:** 每一分钟，遍历所有规则。
2.  **加权累积:** `Score(Mode) = Sum(Rule.Weight * Active_Duration)`.
3.  **胜者为王:** 在决策周期结束时，得分最高的 Mode 胜出。
4.  **优先级覆盖:** 如果检测到高优先级 Mode (如 GAME) 的关键进程（如 CSGO.exe），可直接无视积分强制锁定。

### 2.4 典型用户故事 (User Scenario)

> **场景:** 用户周六上午的活动流。

1.  **09:00 - 10:00 (起床/早餐):**
    *   **行为:** 电脑开着，偶尔动一下鼠标，大部分时间空闲或浏览网页。
    *   **判定:** `Activity=CHILL`, `Time=MORNING`.
    *   **结果:** 壁纸切换为 **"Fantasy Landscape (Day)"** (闲适/幻想风格)。
2.  **10:00 - 11:00 (进入工作):**
    *   **行为:** 打开 VS Code，开始高频输入，持续 45 分钟。
    *   **判定:** `Activity=WORK`, `Time=MORNING`.
    *   **决策:** 下一小时应切换为 **"Minimalist Abstract"** (安静/专注风格)。
    *   **执行:** 11:05 分，用户去倒水（Idle > 5min），系统检测到机会，静默切换壁纸。
3.  **11:05 - 12:00 (工作继续):**
    *   **行为:** 用户回到电脑前，壁纸已变成安静风格，契合当前心流。

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
