# 上下文感知壁纸调度

本上下文统一描述 Scheduler 如何根据用户处境形成壁纸语义，并控制 Wallpaper Engine 播单。这里只记录本项目中特有且容易混淆的概念。

## 调度

**Scheduler**:
持续推进 Tick、持有 Scheduler Memory，并协调完整调度生命周期的主体。Scheduler 是 Orchestrator 主体，不了解下层实现。
_可接受别名_: 调度器
_避免使用_: Engine

**Engine**:
绑定当前运行时配置、承载单个 Tick 调度管线的核心运行时对象。
_避免使用_: Scheduler

**Tick**:
Scheduler 的逻辑时间单位；它表示一个调度时间间隔。
_避免使用_: TickTrace、Action

## 语义

**Context**:
一个 Tick 中用于形成壁纸语义和控制判断的观测集合。

**Policy**:
从 Context 到标签空间贡献的语义映射。
_避免使用_: Blocker、Control Directive

**Tag Direction**:
Policy 当前倾向的各标签之间的相对比例，只表达语义方向，不表达总体影响大小。

**Salience**:
显著性，信号与当前 Tag Direction 的感官相似程度。
_避免使用_: Intensity

**Intensity**:
强度，即被观测现象自身的强度，与信号归属是否清晰相互独立。
_避免使用_: Salience

## 播单

**Playlists**:
Scheduler 内部唯一的播单领域值，由零个、一个或多个 Wallpaper Engine Playlist 身份组成。
_可接受别名_: 播单集合、播单池；上下文清楚时可简称为播单
_避免使用_: Playlist

**FactualPlaylistStatus**:
从 Wallpaper Engine 得到的外部播单事实类别：`PLAYLIST`、`NO_PLAYLIST`、`UNKNOWN` 或 `AMBIGUOUS`。它是推导 Active Playlists 的依据之一，不等于 Scheduler 对当前状态的认知。
_避免使用_: Active Playlists

**Cached Playlists**:
lowering 前 Playlists 的跨 Tick Scheduler Memory，使 Scheduler 能从 Wallpaper Engine 暴露的单个 Playlist 恢复原来的集合身份。
_可接受别名_: cached\*playlists、Scheduler Memory
_避免使用_: Active Playlists、Current Playlist

**Active Playlists**:
当前 Tick 中 Scheduler 认为实际在 Wallpaper Engine 内部活跃的 Playlists，由外部播单事实与 Cached Playlists 共同确定。
_可接受别名_: active\*playlists
\_避免使用\_: Cached Playlists、FactualPlaylistStatus

**Playlist**:
系统与 Wallpaper Engine 交互边界上的单个具名播单，是外部观测结果或 lowering 目标。
_可接受别名_: 播单
_避免使用_: Playlists

## 诊断记录

**Tick History**:
近期、密集、仅在内存中有界保留的逐 Tick 调度记录，用于解释 Scheduler 的近期判断。
_避免使用_: Event Log

**Event Log**:
持久化保存启动、暂停、播单变化和执行失败等稀疏运行事件的记录，不包含每个 Tick 的完整过程。
_避免使用_: Tick History
