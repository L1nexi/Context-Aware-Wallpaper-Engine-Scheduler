# Docs Index

`docs/` 按规格生命周期管理，不按 `current` / `legacy` 二分。代码、测试、运行配置和正在推进的 active spec 才是当前实现依据；已完成规格进入归档后，保留为项目记忆和设计背景。

## 生命周期

| 路径                   | 定位                                        | 管理规则                                                                                                      |
| ---------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `docs/*.md`            | 当前或近期正在推进的 active spec            | 完成后移入 `archived/done/`；废弃后移入 `archived/deprecated/` 或 `archived/outdated/`。                      |
| `half-finished/`       | 暂停的规格、研究记录、访谈和未来方向        | 想法仍有价值但不在当前实现路径上时保留在这里。                                                                |
| `superpowers/`         | 本地 agent 工作过程记录                     | 作为 scratch / work-in-progress 使用，默认不推远端；有长期价值的完成记录归档到 `archived/done/superpowers/`。 |
| `archived/done/`       | 已完成规格和实施记录                        | 完成态历史记录。可以解释当前行为，但不作为持续维护的 current contract。                                       |
| `archived/deprecated/` | 明确放弃的产品或架构路线                    | 只用于说明为什么不应按原路线继续。                                                                            |
| `archived/outdated/`   | 已不匹配当前项目的大文档或旧入口            | 仅作历史背景，不作为实现依据。                                                                                |
| `archived/reference/`  | 事实参考、POC、外部行为记录或推迟的架构备忘 | 可作为背景材料引用，不等同于 active task plan。                                                               |

## Active Specs

| 文档                      | 作用                                                   | 状态   |
| ------------------------- | ------------------------------------------------------ | ------ |
| `TUNING-SIMPLIFY-SPEC.md` | 简化 tuning 输出，让 `tools/tuning` 更容易使用和维护。 | Active |

## Half-Finished

| 文档                                                    | 作用                                          |
| ------------------------------------------------------- | --------------------------------------------- |
| `half-finished/ROADMAP.md`                              | 旧未来方向记录；文档自身已标注废弃。          |
| `half-finished/WALLPAPER_AWARE_CYCLE_SPEC.md`           | Wallpaper-aware cycle 的产品级设计。          |
| `half-finished/WALLPAPER_AWARE_CYCLE_IMPL_SPEC.md`      | Wallpaper-aware cycle 的实现规格。            |
| `half-finished/WALLPAPER_AWARE_CYCLE_IMPL_BRIEF.md`     | Wallpaper-aware cycle 的短版实现说明。        |
| `half-finished/WALLPAPER_AWARE_SCHEDULING_INTERVIEW.md` | Wallpaper-aware scheduling 的访谈和研究记录。 |

## Archived: Done

| 领域                           | 文档                                                                                                                                                                                                 |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Configuration                  | `archived/done/doc_configuration/CONFIGURATION_SPEC.md`, `archived/done/doc_configuration/CONFIGURATION_PHASE_PLAN.md`                                                                               |
| Diagnostics                    | `archived/done/doc_dashboard/DASHBOARD_ANALYSIS_SPEC.md`, `archived/done/doc_dashboard/DASHBOARD_ANALYSIS_IMPLEMENTATION_SPEC.md`, `archived/done/doc_dashboard/DASHBOARD_TIMELINE_ECHARTS_GUIDE.md` |
| Playlist matching              | `archived/done/doc_playlist_pool/R8_PLAYLIST_POOL_SPEC.md`                                                                                                                                           |
| History                        | `archived/done/HISTORY_SYSTEM_SPEC.md`                                                                                                                                                               |
| Product direction              | `archived/done/PRODUCT_DIRECTION.md`                                                                                                                                                                 |
| Wallpaper Engine factual state | `archived/done/WE_FACTUAL_PLAYLIST_RECOVERY_SPEC.md`                                                                                                                                                 |
| Agent work records             | `archived/done/superpowers/`                                                                                                                                                                         |

## Archived: Deprecated

这些是已经冻结且不应作为主线恢复的设计路线：

- `archived/deprecated/CONFIG_EDITOR_SPEC.md`
- `archived/deprecated/CONFIG_EDITOR_IMPLEMENTATION_SPEC.md`
- `archived/deprecated/CONFIG_EDITOR_R5_SPEC.md`
- `archived/deprecated/HISTORY_SPEC.md`

## Archived: Outdated

- `archived/outdated/README_DEV.md`

## Archived: Reference

这些文档记录背景事实、POC 和推迟的架构方向：

- `archived/reference/WE_CLI.md`
- `archived/reference/WE_CLI_POC.md`
- `archived/reference/SEMANTIC-REFACTOR-SPEC.md`
- `archived/reference/config.json`

## 维护规则

- `README.md` 面向用户和发布包读者；实现规格、产品规格和研究记录放在 `docs/`。
- 不新建 `current/` 桶。规格完成后应进入 `archived/done/`，即使对应实现仍然是当前行为。
- active spec 完成后，移动到 `archived/done/` 并同步更新本索引。
- 路线明确放弃后，移动到 `archived/deprecated/`；如果文档内缺少状态说明，补一段短说明。
- 大型旧文档不再匹配当前代码时，移动到 `archived/outdated/`。
