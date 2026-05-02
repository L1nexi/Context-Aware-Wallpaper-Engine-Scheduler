# dashboard-v2 UI Engineering Spec

本文档是 `dashboard-v2` 的前端 UI 开发规范。目标不是限制页面创作，而是给迁移期提供一致的工程边界，避免再次落回“组件廉价、样式失控、后续难维护”的状态。

## 1. 目标

`dashboard-v2` 的 UI 工程必须同时满足以下目标：

- 以现代桌面应用为默认心智，而不是普通营销站或表单页心智。
- 以 Tailwind utility 组合作为一等表达方式，而不是到处增加自定义类。
- 以 shadcn 为基础交互组件层，而不是重新造一套按钮、表单、弹层体系。
- 以 Vue Router 作为页面与工作区导航的唯一正式入口。
- 以 Pinia 作为正式的跨页面状态管理方案，而不是临时全局单例或隐式共享对象。
- 以 token 作为统一设计参数来源，而不是在页面里散落硬编码颜色、尺寸、阴影。
- 以 lint、format、type-check 作为提交前的强制质量闸门，而不是“有空再整理”。
- 以可长期迁移、可局部替换、可并行协作为目标。

## 2. 基本定义

### 2.1 Token

token 是全局 UI 参数的唯一可信来源，定义在 [src/styles/theme.css](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/dashboard-v2/src/styles/theme.css)。

token 包括但不限于：

- 颜色：`--background`、`--foreground`、`--primary`、`--border`
- surface：`--surface`、`--surface-border`
- 布局：`--layout-sidebar-width`、`--layout-header-height`、`--layout-gutter`
- 字体：`--font-app-sans`、`--font-app-mono`
- 视觉质感：`--shadow-panel`、`--shadow-focus`

规则：

- 允许新增 token。
- 不允许在业务页面直接定义新的全局颜色体系。
- 不允许在页面里硬编码与全局设计直接相关的值来绕过 token。

### 2.2 Workbench

workbench 是桌面应用壳层原语集合，不是业务组件集合。

定义在 [src/components/ui/workbench](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/dashboard-v2/src/components/ui/workbench/index.ts)。

当前包含：

- `WorkbenchShell`
- `WorkbenchSidebar`
- `WorkbenchWorkspace`
- `WorkbenchHeader`
- `WorkbenchMain`
- `WorkbenchPanel`

职责：

- 统一应用外壳结构
- 统一导航区与工作区关系
- 统一 header/main/panel 的 chrome 风格
- 不负责业务内容具体排布

不负责：

- 图表区如何分栏
- 表单区如何对齐
- 某个业务卡片内部如何排版

## 3. 分层规则

### 3.1 样式文件分层

- [src/style.css](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/dashboard-v2/src/style.css)
  - 只做全局样式入口聚合
- [src/styles/theme.css](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/dashboard-v2/src/styles/theme.css)
  - 只放 token、theme 映射、light/dark 变量
- [src/styles/base.css](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/dashboard-v2/src/styles/base.css)
  - 只放全局基础行为，如背景、字体、selection、scrollbar、根节点高度
- [src/styles/workbench.css](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/dashboard-v2/src/styles/workbench.css)
  - 只放真正跨页面复用的桌面壳层原语

禁止：

- 在 `theme.css` 写页面级布局
- 在 `base.css` 写具体业务组件样式
- 在 `workbench.css` 写某一个页面专属结构

### 3.2 组件分层

- `src/components/ui/*`
  - 基础 UI 组件层，优先承接 shadcn 生成内容
- `src/components/ui/workbench/*`
  - 桌面应用 chrome 原语层
- `src/views/*`
  - 路由级页面
- 页面私有复杂块
  - 后续应放到 `src/components/<domain>` 或 `src/features/<domain>`，不要塞进 `ui`

禁止：

- 把业务组件放进 `ui`
- 把应用壳层规则塞进具体页面
- 把局部业务抽象伪装成“通用基础组件”

### 3.3 路由与状态分层

- `src/router/*`
  - 负责页面级导航、工作区路由装配、路由守卫
- `src/stores/*`
  - 负责 Pinia store
- `src/composables/*`
  - 负责可复用逻辑，不负责跨页面共享真状态

规则：

- 页面切换与主导航状态必须围绕 Vue Router 设计。
- 跨页面共享、跨区域共享、需要缓存和回放的状态必须优先进入 Pinia。
- 单页局部状态、单组件临时交互状态应保留在组件或 composable 内，不要无脑升到 Pinia。

禁止：

- 用模块级变量冒充全局状态中心
- 在多个 composable 里偷偷维护彼此耦合的共享状态
- 把一次性表单输入、弹窗开关这类纯局部状态直接塞进 Pinia

## 4. Workbench 的组合规则

workbench 是可选、可组合的，但组合有边界。

### 4.1 推荐的完整组合

```vue
<WorkbenchShell>
  <WorkbenchSidebar />

  <WorkbenchWorkspace>
    <WorkbenchHeader />
    <WorkbenchMain>
      <WorkbenchPanel />
    </WorkbenchMain>
  </WorkbenchWorkspace>
</WorkbenchShell>
```

这是“完整桌面页”的推荐结构。

### 4.2 允许的裁剪方式

允许只使用其中一部分，前提是职责仍然清晰。

示例 1：只有左侧导航 + 右侧工作区

```vue
<WorkbenchShell>
  <WorkbenchSidebar />
  <WorkbenchWorkspace />
</WorkbenchShell>
```

示例 2：右侧工作区单独使用

```vue
<WorkbenchWorkspace class="min-h-dvh">
  <WorkbenchHeader />
  <WorkbenchMain />
</WorkbenchWorkspace>
```

示例 3：只把 `WorkbenchPanel` 当统一 surface 使用

```vue
<WorkbenchPanel tone="muted" padding="lg">
  ...
</WorkbenchPanel>
```

### 4.3 组合边界

- `WorkbenchShell` 负责 sidebar 与 workspace 的整体关系。
- `WorkbenchSidebar` 负责侧栏表面和边界，不负责父级分栏。
- `WorkbenchWorkspace` 负责右侧容器行为，不负责父级是否两栏。
- `WorkbenchHeader` 是 workspace 顶部 chrome，不是业务内容区。
- `WorkbenchMain` 是工作区主滚动容器，不是具体业务网格系统。
- `WorkbenchPanel` 只统一 surface，不定义内部业务布局。

结论：

- 可以只选“左侧导航区域 + 右侧工作区容器”。
- 推荐最小组合是 `WorkbenchShell + WorkbenchSidebar + WorkbenchWorkspace`。
- `Header`、`Main`、`Panel` 都是可选层，不强制每页都上。
- 如果不使用 `WorkbenchShell`，父级容器的分栏与尺寸责任由页面自己承担。

## 5. Tailwind 与抽象边界

### 5.1 默认原则

默认先直接写 Tailwind utility。

只有满足以下条件，才允许抽象出新的基础原语、variant 或全局类：

- 同一结构在至少 3 个页面重复出现
- 结构本身是产品约定，而不是临时业务布局
- 抽象后可以减少 token 漂移、间距漂移、surface 漂移

### 5.2 明确禁止

禁止以下行为：

- 为了少写几个 class 就新增全局类
- 给每个页面都写一套 scoped CSS 来覆盖 shadcn
- 在业务页面硬编码 sidebar 宽度、header 高度、panel 阴影
- 把“局部便利写法”包装成所谓的通用设计系统
- 用大量 `!important` 纠偏

### 5.3 允许的例外

以下情况允许少量局部样式：

- 第三方库 DOM 难以直接 utility 化
- 某个复杂视觉效果难以仅用 utility 表达
- 某个组件存在明确的状态机样式，需要局部样式承接

前提：

- 该样式必须局部化
- 必须说明为什么不能继续走 utility
- 不得污染全局层

## 6. Token 使用规范

### 6.1 应该这样做

- 优先使用 `bg-background`、`text-foreground`、`border-border` 这类 token 映射
- 通过 `--layout-*` 管理桌面壳层尺寸
- 通过 `tone`、`padding` 这类有限变体表达 surface 差异

### 6.2 不应该这样做

- 直接写 `style="width: 288px"`
- 直接写 `#111827`、`rgba(...)` 作为核心主题色
- 在多个页面各自定义“差不多”的 panel 阴影和圆角

### 6.3 新增 token 的门槛

只有以下情况允许新增 token：

- 新值具有跨页面复用意义
- 新值代表稳定语义，而不是一次性视觉偏好
- 现有 token 无法表达该差异

否则先直接用 Tailwind 组合。

## 7. Pinia 使用规范

Pinia 不是“可选增强”，而是本项目正式认可的状态层。

### 7.1 必须使用 Pinia 的场景

- 状态被多个路由页面消费
- 状态同时被 sidebar、header、main 等多个区域消费
- 状态需要在刷新前的一段会话中持续存在
- 状态需要统一的加载、错误、同步、回滚语义
- 状态未来明显会成为产品级领域模型的一部分

典型例子：

- 当前调度配置草稿
- 当前选中的壁纸/规则对象
- 全局筛选条件
- 用户偏好、视图模式、桌面工作台 chrome 偏好

### 7.2 不应使用 Pinia 的场景

- 单个页面独占的临时输入值
- 单个组件内部的展开收起
- 仅用于某一个弹窗生命周期的瞬时状态
- 没有跨组件共享需求的纯派生值

### 7.3 Store 设计约束

- 一个 store 应围绕一个清晰领域建模，不围绕页面文件建模
- store 命名应体现领域语义，不应使用 `usePageStore` 这类弱语义命名
- store 内应优先暴露明确 action，而不是让页面直接任意改写深层状态
- 异步加载、提交、错误态、空态应在 store 层形成稳定约定
- 页面不应把大量业务规则重新散落回组件

### 7.4 推荐目录约定

- `src/stores/<domain>.ts`
- 一个文件一个主 store
- 复杂领域允许在同目录拆 helpers，但不要把 view 专属逻辑沉到底层 store

## 8. Lint / Format / Type-Check 规范

lint 和 format 在本项目不是建议项，而是交付要求。

### 8.1 必跑命令

提交前至少运行：

```sh
npm run lint
npm run type-check
```

需要整理格式或批量修改后，额外运行：

```sh
npm run format
```

### 8.2 执行要求

- 不允许提交明显未经过 lint 的文件
- 不允许长期依赖格式漂移留给后人收尾
- 不允许为了通过 lint 而关闭规则、加大量忽略注释，除非有充分理由
- 新增代码必须遵守现有 ESLint、Oxlint、Prettier 约束

### 8.3 Code Review 判定

以下情况默认视为不合格：

- 提交内容带有明显格式不一致
- 存在本可修复但未修复的 lint 问题
- 用规避方式压过规则，而不是正面修代码
- 类型错误留在分支里等待后续处理

## 9. WorkbenchPanel 与 Card 的边界

- `WorkbenchPanel`
  - 表示工作台表面层
  - 解决外壳语义、整体 surface 质感、页面级块容器一致性
- `Card`
  - 表示局部内容块
  - 解决块级内容容器问题

规则：

- 页面级主要区域优先考虑 `WorkbenchPanel`
- panel 内部的子块优先考虑 `Card`
- 不要让 `Card` 去承担整页桌面 surface 的职责

## 10. 字体与文案规范

- 默认正文、标题使用 `font-sans`
- 数据、时间、编号、路径、状态码优先使用 `font-mono` 或 `.data-mono`
- 小型技术感标签可以使用 `.chrome-kicker`
- `.chrome-kicker` 只用于短标签，不用于正文和长标题

## 11. 页面开发清单

每个新页面在提交前至少自检以下问题：

1. 是否重复硬编码了全局尺寸、颜色、阴影或圆角。
2. 是否把页面私有布局错误抽象成了全局类或 `ui` 组件。
3. 是否应该直接组合 Tailwind，而不是继续增加新的基础层。
4. 是否错误地让 `WorkbenchPanel` 决定了业务内部布局。
5. 是否存在不必要的 scoped CSS。
6. 是否正确使用了 token 映射，而不是直接写颜色值。
7. 是否遵守了 `Workbench` 的职责边界。
8. 是否把真正的跨页面状态沉到了 Pinia，而不是散在 composable 或页面里。
9. 是否运行了 `lint` 与 `type-check`。

## 12. Code Review 判定标准

以下情况默认判定为需要修改：

- 出现明显的主题硬编码
- 页面级重复出现相同壳层结构但没有回收到 workbench
- `ui` 目录混入业务组件
- 抽象过早，新增原语没有稳定复用依据
- 使用 `Card`、`Panel` 职责混乱
- 为了实现布局写了大量不可复用 scoped CSS
- 跨页面共享状态没有进入 Pinia
- 提交缺少基本 lint / type-check 保障

以下情况默认判定为合理：

- 页面内部用 Tailwind 直接组合出业务布局
- 仅把跨页面稳定结构抽象到 workbench
- 局部复杂样式被限制在局部范围内
- 全局主题与桌面尺寸通过 token 管理
- 跨页面领域状态收敛在 Pinia store
- 提交前已完成基本质量检查

## 13. 落地建议

迁移旧页面时，建议顺序如下：

1. 先决定该页面是否属于完整桌面页。
2. 如果是，优先接入 `WorkbenchShell` 及最小必要组合。
3. 先恢复信息架构和交互，再逐步细化业务区块。
4. 同步识别跨页面共享状态，优先规划 Pinia store 边界。
5. 只有当重复结构真正稳定后，再抽象新的原语或变体。

本文档优先级高于 README 中的概述性说明。README 用于快速理解，本文档用于实际开发和 code review。
