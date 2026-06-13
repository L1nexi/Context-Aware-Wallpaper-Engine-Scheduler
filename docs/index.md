# Docs Index

`docs/` 按规格生命周期管理。代码、测试、运行配置和正在推进的 active spec 才是当前实现依据；已完成规格进入归档后，保留为项目记忆和设计背景。

## 生命周期

| 路径                   | 定位                                        | 管理规则                                                                                                      |
| ---------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `docs/*.md`            | 当前或近期正在推进的 active spec            | 完成后移入 `archived/done/`；废弃后移入 `archived/deprecated/` 或 `archived/outdated/`。                      |
| `half-finished/`       | 暂停的规格、研究记录、访谈和未来方向        | 想法仍有价值但不在当前实现路径上时保留在这里。                                                                |
| `superpowers/`         | 本地 agent 工作过程记录                     | 作为 scratch / work-in-progress 使用，默认不推远端；有长期价值的完成记录归档到 `archived/done/superpowers/`。 |
| `archived/done/`       | 已完成规格和实施记录                        | 完成态历史记录。                                                                                              |
| `archived/deprecated/` | 明确放弃的产品或架构路线                    | 用于说明为什么不应按原路线继续。                                                                              |
| `archived/reference/`  | 事实参考、POC、外部行为记录或推迟的架构备忘 | 可作为背景材料引用                                                                                            |

## Active Specs

| 文档                                      | 作用                                             |
| ----------------------------------------- | ------------------------------------------------ |
| `DIAGNOSTIC_FRONTEND_MATCH_FIRST_SPEC.md` | 新前端诊断页 Match-first 信息架构与图表语义规格。 |

## Half-Finished

| 文档                                                    | 作用                                          |
| ------------------------------------------------------- | --------------------------------------------- |
| `half-finished/ROADMAP.md`                              | 旧未来方向记录；文档自身已标注废弃。          |
| `half-finished/WALLPAPER_AWARE_CYCLE_SPEC.md`           | Wallpaper-aware cycle 的产品级设计。          |
| `half-finished/WALLPAPER_AWARE_CYCLE_IMPL_SPEC.md`      | Wallpaper-aware cycle 的实现规格。            |
| `half-finished/WALLPAPER_AWARE_CYCLE_IMPL_BRIEF.md`     | Wallpaper-aware cycle 的短版实现说明。        |
| `half-finished/WALLPAPER_AWARE_SCHEDULING_INTERVIEW.md` | Wallpaper-aware scheduling 的访谈和研究记录。 |

## Archived: Reference

这些文档记录背景事实、POC 和推迟的架构方向：

- `archived/reference/WE_CLI.md`
- `archived/reference/WE_CLI_POC.md`
- `archived/reference/SEMANTIC-REFACTOR-SPEC.md`
- `archived/reference/config.json`

## 维护规则

- `README.md` 面向用户和发布包读者；实现规格、产品规格和研究记录放在 `docs/`。
- active spec 完成后，移动到 `archived/done/` 并同步更新本索引。
- 路线明确放弃后，移动到 `archived/deprecated/`；如果文档内缺少状态说明，补一段短说明。
- 大型旧文档不再匹配当前代码时，移动到 `archived/outdated/`。
