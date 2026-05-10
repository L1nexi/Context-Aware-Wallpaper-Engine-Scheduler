# dashboard-v2

`dashboard-v2` 是新的前端工作台，目标不是机械复刻旧版 Element Plus 页面，而是先建立一套可长期维护的 Tailwind + shadcn 桌面应用 UI 基座。

## 当前设计方向

- 桌面软件优先：默认采用左侧导航 + 右侧工作区的 workbench 结构。
- Tailwind 组合优先：业务页面直接组合 utility class，避免重新发明一套庞大的语义类系统。
- shadcn 负责基础交互组件：按钮、表单、弹层、表格等继续复用现有 `src/components/ui/*`。
- Vue Router 负责页面与工作区导航，Pinia 负责正式的跨页面状态管理。
- ESLint / Oxlint / Prettier / vue-tsc 属于必用质量工具，不是可选补充。
- workbench 原语负责应用壳层：导航、工作区、页头、主内容区、surface/panel 由独立原语承接。
- 视觉倾向偏 geek：冷色中性色板、轻玻璃质感、网格背景、适度 mono 字体，但不把暗色主题写死到业务里。

## 基础约定

详细开发规范见 [docs/UI_ENGINEERING_SPEC.md](/E:/github/Context-Aware-Wallpaper-Engine-Scheduler/dashboard-v2/docs/UI_ENGINEERING_SPEC.md)。README 只保留概述，具体执行以规范文档为准。

### 样式分层

- `src/styles/theme.css`
  - 只放 token 和 theme 映射。
  - 颜色、半径、阴影、shell 尺寸都从这里统一管理。
- `src/styles/base.css`
  - 只放全局基础行为。
  - 包括背景、字体、selection、scrollbar、根节点高度。
- `src/styles/workbench.css`
  - 只放真正跨页面复用的桌面 shell 原语。
  - 不放某个页面私有布局。

### 组件分层

- `src/components/ui/*`
  - shadcn 基础组件层。
- `src/components/ui/workbench/*`
  - 桌面应用壳层原语。
  - 目前包含 `WorkbenchShell`、`WorkbenchSidebar`、`WorkbenchWorkspace`、`WorkbenchHeader`、`WorkbenchMain`、`WorkbenchPanel`。

### Workbench 组合说明

`workbench` 是可选、可组合的桌面壳层原语，不是强绑定模板。

推荐完整结构如下：

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

允许裁剪使用，例如：

- 只用 `WorkbenchShell + WorkbenchSidebar + WorkbenchWorkspace`
- 只用 `WorkbenchWorkspace + WorkbenchHeader + WorkbenchMain`
- 只用 `WorkbenchPanel` 作为统一 surface

约束如下：

- shell 级布局只能使用 `Workbench*` 原语，不在页面里手写一堆重复 sidebar/header 容器。
- 页面内部的业务排列仍然直接用 Tailwind utilities 组合。
- `WorkbenchPanel` 只负责统一 surface，不决定业务内容如何分栏、如何排表单、如何排图表。
- 如果不使用 `WorkbenchShell`，父级分栏与尺寸由页面自己负责。

## 编码原则

- 优先使用 token，而不是直接写 `#hex`、`rgb()`、固定阴影值。
- 优先用 Tailwind utilities 描述页面布局；只有“跨页面复用且语义稳定”的结构才抽象成原语。
- 跨页面共享状态优先进入 Pinia，不用模块变量或隐式共享 composable 代替。
- 不在业务页面重复写 sidebar 宽度、header 高度、panel 间距，统一走 `--layout-*` token。
- 不为了省几行 class 就新增页面专属全局类。
- 能用 utility 解决的布局，不写 scoped CSS。
- `Card` 用于局部内容块，`WorkbenchPanel` 用于工作台 surface；不要把两者混成同一种职责。
- 标题和正文默认 `font-sans`，数据标签、编号、状态码、时间戳优先 `font-mono` / `.data-mono`。
- 小型技术感标签使用 `.chrome-kicker`，但只用于 chrome 文案，不用于大段正文。

## 什么时候抽象

只有满足下面任一条件，才允许新增新的基础原语或变体：

- 同一结构在至少 3 个页面重复出现。
- 结构本身是产品级约定，而不是某个业务块的偶然布局。
- 该抽象能减少 token 漂移、spacing 漂移或 surface 风格漂移。

否则先直接写 Tailwind。

## 开发命令

```sh
npm install
npm run dev
npm run lint
npm run type-check
npm run build
```
