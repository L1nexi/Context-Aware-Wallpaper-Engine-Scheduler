# Playlist Entity Color Design

## Context

当前 `dashboard-v2` 的 playlist 着色来自前端本地 hash 逻辑，而不是正式配置模型。

现状问题：

- playlist 颜色不是业务定义，而是前端推导结果
- playlist 改名后，颜色会跟着变化
- analysis 页面无法稳定表达 playlist 的实体语义
- 主题色与实体色职责混杂

相关代码现状：

- `dashboard-v2/src/features/dashboard-analysis/playlistColors.ts` 通过 playlist name hash 到主题调色板
- `utils/config_loader.py` 中 `PlaylistConfig` 目前只有 `name / display / tags`
- `dashboard-v2/src/composables/useConfig.ts` 的前端配置类型同样没有 `color`

根据当前 thread 已确认的设计方向：

- `theme color` 与 `entity color` 必须分离
- `playlist.color` 是正式配置字段，不是可选辅助字段
- 本项目处于 `0.x`，允许直接采用 breaking change
- 不引入自动补齐、自动迁移、兼容旧配置的语义

## Goals

- 把 playlist 颜色提升为正式配置模型的一部分
- 明确区分 UI 主题色与 playlist 实体色
- 让 analysis 页面仅依赖正式语义色，而不是前端 hash 推导
- 为后续 Config Editor 中的 playlist 创建流程提供可复用的默认色策略

## Non-Goals

- 不兼容缺失 `playlist.color` 的旧配置文件
- 不做运行时自动补齐、自动回写或迁移脚本
- 不把 tag 颜色系统一并引入本轮设计
- 不接受任意 CSS 颜色字符串作为配置值
- 不保留现有 hash/palette runtime fallback 逻辑

## Chosen Approach

### 1. `playlist.color` 成为必填配置字段

`PlaylistConfig` 结构升级为：

```json
{
  "name": "BRIGHT_FLOW",
  "display": "Bright Flow",
  "color": "#F5C518",
  "tags": {
    "#focus": 1.0
  }
}
```

规则：

- `color` 必填
- 值类型为字符串
- 合法格式限定为 6 位 hex：`#RRGGBB`
- 运行时可接受大小写 hex；Config Editor 保存时应写为大写规范形式

后端校验目标：

- `#F5C518` 合法
- `#f5c518` 合法
- `#FFF` 非法
- `rgb(255,0,0)` 非法
- 空字符串非法

### 2. 主题色与实体色职责分离

主题色继续留在设计系统层：

- `primary`
- `accent`
- `chart-*`
- `destructive`

这些 token 继续服务：

- 按钮
- 面板
- 状态徽标
- 图表中的非实体型语义

playlist 实体色只负责表达“这是哪个 playlist”，用于：

- dashboard timeline 的 active/matched track segment
- top matches 列表中的 playlist dot
- playlist browser 中的 identity swatch
- 未来任何 playlist legend / selector / badge

结论：

- 主题 token 不再承担 playlist 身份表达
- playlist 身份表达只来自配置中的 `playlist.color`

### 3. Analysis API 直接带出颜色元数据

analysis 页面不应再额外请求 `/api/config` 才能正确着色。

本轮设计选择：

- 后端在 `SchedulerTickTrace -> TickSnapshot` 映射阶段引入 playlist presentation metadata
- `TickSnapshot` 直接带出当前需要的颜色字段
- 前端 analysis store 继续只请求 `/api/analysis/window`

这样做的原因：

- analysis 视图保持自洽，不依赖第二个配置请求
- 可以直接删掉前端 hash 着色工具
- 颜色来源仍是 playlist config，而不是前端自算

### 4. 缺失配置命中的 playlist 不再获得伪语义色

如果 analysis DTO 中某个 playlist name 在当前配置里无法解析到颜色：

- 后端返回 `null` color
- 前端统一以中性 `muted` 表达
- 这被视为“配置与运行时引用不一致”的信号，而不是正常业务颜色

结论：

- 不再为未知 playlist 动态生成任何 hash 色
- 不再把“缺失配置”伪装成“有语义的正常颜色”

## API and DTO Design

### `/api/config`

`GET /api/config` 与 `POST /api/config` 的 playlist DTO 统一升级为：

```ts
type PlaylistConfig = {
  name: string
  display?: string
  color: string
  tags: Record<string, number>
}
```

breaking change 规则：

- 旧配置中缺少 `color` 时，`GET /api/config` 校验失败
- `POST /api/config` 提交缺少 `color` 或格式非法时，返回 `422`
- 不增加兼容字段
- 不保留旧 schema 分支

### `/api/analysis/window`

分析 DTO 增加 playlist color presentation fields。

`TopMatch` 升级为：

```ts
type TopMatch = {
  playlist: string
  display: string | null
  score: number
  color: string | null
}
```

`TickSummary` 增加：

```ts
type TickSummary = {
  activePlaylist: string | null
  activePlaylistDisplay: string | null
  activePlaylistColor: string | null
  matchedPlaylist: string | null
  matchedPlaylistDisplay: string | null
  matchedPlaylistColor: string | null
}
```

说明：

- `color` 是 API presentation metadata，不属于 `core/diagnostics.py` 领域事实
- 颜色来自当前 config 中的 playlist 定义
- 颜色不需要写入历史日志
- 如果后续用户修改了 playlist color，analysis 页面会按当前配置重新呈现历史窗口颜色

本轮不新增 response-level playlist palette map，直接在 tick DTO 中携带需要的颜色字段，优先保持实现简单和消费端清晰。

## Frontend Design

### Analysis surfaces

以下位置统一改为消费 DTO/config 中的正式颜色：

- `dashboard-v2/src/features/dashboard-analysis/timeline.ts`
- `dashboard-v2/src/features/dashboard-analysis/ActPanel.vue`
- 未来 playlist browser / playlist detail identity swatch

当前 `dashboard-v2/src/features/dashboard-analysis/playlistColors.ts` 应被删除，而不是保留兜底逻辑。

新的前端规则：

- active / matched track segment 使用 DTO 中的 `activePlaylistColor` / `matchedPlaylistColor`
- top match dot 使用 `match.color`
- `null` color 使用 `muted`

### Config typing

`dashboard-v2/src/composables/useConfig.ts` 的 `PlaylistConfig` 前端类型同步升级为必填 `color`。

这不是 UI 可选字段，而是正式 schema。

## Preset Palette Design

以下 palette 作为业务预置色表，用于：

- 已知 playlist 的正式建议色
- 后续 Config Editor 的创建默认值策略

```python
PLAYLIST_COLOR_PRESETS = {
    "BRIGHT_FLOW": "#F5C518",
    "CASUAL_ANIME": "#5BB8D4",
    "SUNSET_GLOW": "#FF8C00",
    "NIGHT_CHILL": "#7B68EE",
    "NIGHT_FOCUS": "#2E5F8A",
    "RAINY_MOOD": "#4A90D9",
    "WINTER_VIBES": "#ADC8E0",
    "SPRING_BLOOM": "#5CBE5C",
    "SUMMER_GLOW": "#D83820",
    "AUTUMN_DRIFT": "#C07830",
}
```

这些值属于业务预置，不属于主题 token。

### Future Config Editor create behavior

本轮不实现 Config Editor，但先固定创建规则：

1. 新建 playlist 时，必须立即拥有 `color`
2. 如果 playlist name 精确命中 `PLAYLIST_COLOR_PRESETS`，默认填入对应颜色
3. 如果未命中预置表，按预置表声明顺序选取“第一个未被当前配置使用的颜色”
4. 如果预置色已全部用完，则从预置表头部循环
5. UI 必须展示 swatch + hex 输入，并明确告诉用户该颜色可手动调整

说明：

- 这是创建辅助策略，不是运行时实体着色策略
- 真正的播放语义色始终来自最终保存进 config 的 `playlist.color`

## Breaking Change Policy

本设计明确采用 breaking change。

具体含义：

- 旧配置文件如果缺少 `playlist.color`，直接视为非法配置
- 不提供自动升级
- 不提供读取时补齐
- 不保留 hash 颜色逻辑作为过渡层
- 不同时维护“旧 config + 新 config”双轨

这与仓库根 `AGENTS.md` 当前关于 `0.x` 阶段和前端重写期的工作原则一致。

## Affected Files

预计至少涉及：

| File | Change |
| --- | --- |
| `utils/config_loader.py` | `PlaylistConfig` 新增必填 `color` 与 hex 校验 |
| `ui/dashboard.py` | `/api/config` 与 analysis mapper 使用新 schema |
| `ui/dashboard_analysis.py` | analysis DTO 增加 playlist color presentation fields |
| `dashboard-v2/src/composables/useConfig.ts` | 前端配置类型增加必填 `color` |
| `dashboard-v2/src/lib/dashboardAnalysis.ts` | analysis DTO 类型增加 color fields |
| `dashboard-v2/src/features/dashboard-analysis/timeline.ts` | 改为使用 DTO color |
| `dashboard-v2/src/features/dashboard-analysis/ActPanel.vue` | 改为使用 DTO color |
| `dashboard-v2/src/features/dashboard-analysis/playlistColors.ts` | 删除 |
| `tests/test_dashboard_api.py` | 更新 config fixture 和 API 断言 |
| `tests/test_core_diagnostics.py` | 更新 `PlaylistConfig` fixture |
| `tests/test_config_loader.py` | 增加 `color` 缺失 / 非法格式校验用例 |

## Testing and Verification

最低验证要求：

### Backend

```bash
pytest -q tests/test_dashboard_api.py tests/test_config_loader.py tests/test_core_diagnostics.py
```

如无额外阻碍，优先再跑：

```bash
pytest -q
```

### Frontend

```bash
cd dashboard-v2
npm run type-check
```

如 analysis DTO 或构建产物受影响，再跑：

```bash
cd dashboard-v2
npm run build-only
```

## Alternatives Rejected

### 保留前端 hash 配色作为 fallback

拒绝原因：

- 会继续制造“看起来可用、实际上无语义来源”的假稳定性
- 会把配置缺失伪装成正常状态
- 与本次“实体色必须来自正式配置”的目标冲突

### 把颜色作为 playlist 可选字段

拒绝原因：

- 仍然需要 fallback 体系
- 仍然无法确保实体色是正式建模的一部分
- 与本 thread 已确认的决策冲突

### 把颜色挂到 tag 而不是 playlist

拒绝原因：

- 当前需要着色的主对象是 playlist，而不是单个 tag
- dashboard timeline 和 top matches 直接表达的是 playlist 身份
- 把颜色挂到 tag 会引入 playlist 组合语义如何折算颜色的新问题

## Self-Review

- 没有保留兼容层或自动补齐语义
- 主题色与实体色职责已明确分离
- analysis 页面颜色来源已固定为 config -> API DTO，而不是前端 hash
- Config Editor 的未来创建规则已经定清，没有留下 `TBD`
