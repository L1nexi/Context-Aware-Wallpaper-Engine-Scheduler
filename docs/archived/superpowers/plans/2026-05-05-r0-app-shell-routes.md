# R0 App Shell / Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the shared `dashboard-v2` App Shell and formal route topology without implementing History or Config business pages.

**Architecture:** `AppShell.vue` owns the global workbench chrome and sidebar. `DashboardView.vue` keeps only Dashboard page behavior and continues to own analysis polling. `/history` and `/config/*` resolve through thin route boundaries that do not call future APIs.

**Tech Stack:** Vue 3, Vue Router hash history, Pinia, Tailwind CSS v4, lucide-vue-next, existing `dashboard-v2/src/components/ui/workbench/*` primitives.

---

## File Structure

- Create: `dashboard-v2/src/layouts/AppShell.vue`
  - Owns `WorkbenchShell`, `WorkbenchSidebar`, `WorkbenchWorkspace`, hierarchical nav config, route active state, and layout `<RouterView />`.
- Create: `dashboard-v2/src/views/RouteBoundaryView.vue`
  - Invisible route target for `/history` and `/config/*` during R0. It contains no API calls and no feature UI.
- Modify: `dashboard-v2/src/router/index.ts`
  - Adds layout route, `/` redirect, `/dashboard`, `/history`, and `/config/*` records.
- Modify: `dashboard-v2/src/views/DashboardView.vue`
  - Removes global shell/sidebar/workspace ownership while preserving Dashboard header, main content, panels, and polling lifecycle.
- Modify: `dashboard-v2/src/i18n/en.json`
  - Adds App Shell and Config General nav labels.
- Modify: `dashboard-v2/src/i18n/zh.json`
  - Adds App Shell and Config General nav labels.

No backend files change in R0.

## Verification Strategy

`dashboard-v2` currently has no frontend unit test runner. Do not add Vitest or another runner for R0. Use:

```bash
cd dashboard-v2
npm run type-check
npm run build-only
```

If a browser smoke check is requested during execution, run the Vite dev server and verify:

- `#/` redirects to `#/dashboard`
- `#/dashboard` shows the existing Dashboard page
- `#/history` resolves with the App Shell
- `#/config/general`, `#/config/scheduling`, `#/config/playlists`, `#/config/tags`, and `#/config/policies` resolve with correct sidebar active state

---

### Task 1: Add Route Topology

**Files:**
- Create: `dashboard-v2/src/views/RouteBoundaryView.vue`
- Modify: `dashboard-v2/src/router/index.ts`

- [ ] **Step 1: Record the current frontend baseline**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: PASS. If it fails before edits, stop and report the pre-existing failure.

- [ ] **Step 2: Create the thin route boundary component**

Create `dashboard-v2/src/views/RouteBoundaryView.vue`:

```vue
<script setup lang="ts">
defineOptions({
  name: 'RouteBoundaryView',
})
</script>

<template>
  <div aria-hidden="true" class="hidden" />
</template>
```

This component is intentionally invisible. It exists only so R0 routes resolve without introducing History or Config feature UI.

- [ ] **Step 3: Replace router records with the R0 route topology**

Replace `dashboard-v2/src/router/index.ts` with:

```ts
import { createRouter, createWebHashHistory } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import DashboardView from '@/views/DashboardView.vue'
import RouteBoundaryView from '@/views/RouteBoundaryView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      component: AppShell,
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: DashboardView,
        },
        {
          path: 'history',
          name: 'history',
          component: RouteBoundaryView,
        },
        {
          path: 'config',
          redirect: '/config/general',
        },
        {
          path: 'config/general',
          name: 'config-general',
          component: RouteBoundaryView,
        },
        {
          path: 'config/scheduling',
          name: 'config-scheduling',
          component: RouteBoundaryView,
        },
        {
          path: 'config/playlists',
          name: 'config-playlists',
          component: RouteBoundaryView,
        },
        {
          path: 'config/tags',
          name: 'config-tags',
          component: RouteBoundaryView,
        },
        {
          path: 'config/policies',
          name: 'config-policies',
          component: RouteBoundaryView,
        },
      ],
    },
  ],
})

export default router
```

- [ ] **Step 4: Run type-check and capture expected first failure**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: FAIL because `@/layouts/AppShell.vue` has not been created yet.

- [ ] **Step 5: Do not commit while type-check is red**

Task 1 intentionally introduces the `AppShell.vue` import before that file exists. Continue directly to Task 2 and commit the route topology with App Shell once type-check is green.

---

### Task 2: Add App Shell Sidebar Navigation

**Files:**
- Create: `dashboard-v2/src/layouts/AppShell.vue`
- Modify: `dashboard-v2/src/i18n/en.json`
- Modify: `dashboard-v2/src/i18n/zh.json`

- [ ] **Step 1: Add App Shell i18n keys**

Add these keys near the existing app/dashboard labels in `dashboard-v2/src/i18n/en.json`:

```json
"app_shell_label": "Workspace",
"app_shell_subtitle": "Local scheduler workbench.",
"config_general": "General",
```

Add these keys near the existing app/dashboard labels in `dashboard-v2/src/i18n/zh.json`:

```json
"app_shell_label": "工作台",
"app_shell_subtitle": "本地调度器工作台。",
"config_general": "通用",
```

Keep valid JSON commas based on the surrounding entries.

- [ ] **Step 2: Create the App Shell layout**

Create `dashboard-v2/src/layouts/AppShell.vue`:

```vue
<script setup lang="ts">
import type { Component } from 'vue'
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { History, LayoutDashboard, Settings } from 'lucide-vue-next'

import {
  WorkbenchShell,
  WorkbenchSidebar,
  WorkbenchWorkspace,
} from '@/components/ui/workbench'
import { useI18n } from '@/composables/useI18n'
import { cn } from '@/lib/utils'

type NavChild = {
  labelKey: string
  to: string
}

type NavItem = {
  labelKey: string
  to: string
  icon: Component
  match: (path: string) => boolean
  children?: NavChild[]
}

const route = useRoute()
const { t } = useI18n()

const navItems: NavItem[] = [
  {
    labelKey: 'dashboard_nav',
    to: '/dashboard',
    icon: LayoutDashboard,
    match: (path) => path === '/dashboard',
  },
  {
    labelKey: 'dashboard_history',
    to: '/history',
    icon: History,
    match: (path) => path === '/history',
  },
  {
    labelKey: 'dashboard_config',
    to: '/config/general',
    icon: Settings,
    match: (path) => path.startsWith('/config/'),
    children: [
      { labelKey: 'config_general', to: '/config/general' },
      { labelKey: 'config_scheduling', to: '/config/scheduling' },
      { labelKey: 'config_playlists', to: '/config/playlists' },
      { labelKey: 'config_tags_tab', to: '/config/tags' },
      { labelKey: 'config_policies', to: '/config/policies' },
    ],
  },
]

const currentPath = computed(() => route.path)

function primaryNavClass(active: boolean): string {
  return cn(
    'flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm font-medium transition-colors',
    active
      ? 'border-sidebar-border/70 bg-sidebar-accent/80 text-sidebar-accent-foreground shadow-sm'
      : 'border-transparent text-sidebar-foreground/72 hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground',
  )
}

function secondaryNavClass(active: boolean): string {
  return cn(
    'flex items-center rounded-xl px-4 py-2 text-sm transition-colors',
    active
      ? 'bg-sidebar-accent/70 font-medium text-sidebar-accent-foreground'
      : 'text-sidebar-foreground/62 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground',
  )
}
</script>

<template>
  <WorkbenchShell>
    <WorkbenchSidebar class="flex flex-col gap-8">
      <div class="flex flex-col gap-3">
        <p class="chrome-kicker">{{ t('app_shell_label') }}</p>
        <div class="space-y-1">
          <h1 class="text-2xl font-semibold tracking-tight text-sidebar-foreground">
            {{ t('appName') }}
          </h1>
          <p class="text-sm leading-6 text-muted-foreground">
            {{ t('app_shell_subtitle') }}
          </p>
        </div>
      </div>

      <nav class="flex flex-col gap-2" aria-label="Primary">
        <div v-for="item in navItems" :key="item.to" class="flex flex-col gap-1">
          <RouterLink :to="item.to" :class="primaryNavClass(item.match(currentPath))">
            <component :is="item.icon" class="size-4 shrink-0" aria-hidden="true" />
            <span>{{ t(item.labelKey) }}</span>
          </RouterLink>

          <div
            v-if="item.children && item.match(currentPath)"
            class="ml-5 flex flex-col gap-1 border-l border-sidebar-border/60 pl-3"
          >
            <RouterLink
              v-for="child in item.children"
              :key="child.to"
              :to="child.to"
              :class="secondaryNavClass(currentPath === child.to)"
            >
              {{ t(child.labelKey) }}
            </RouterLink>
          </div>
        </div>
      </nav>
    </WorkbenchSidebar>

    <WorkbenchWorkspace>
      <RouterView />
    </WorkbenchWorkspace>
  </WorkbenchShell>
</template>
```

- [ ] **Step 3: Run type-check**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: PASS or fail only on issues in the new `AppShell.vue`/i18n edits. Fix any reported type or JSON syntax issue before continuing.

- [ ] **Step 4: Commit App Shell and nav**

Run:

```bash
git add dashboard-v2/src/layouts/AppShell.vue dashboard-v2/src/i18n/en.json dashboard-v2/src/i18n/zh.json dashboard-v2/src/router/index.ts dashboard-v2/src/views/RouteBoundaryView.vue
git commit -m "feat: add dashboard v2 app shell"
```

Skip this commit if Task 1 was already committed cleanly and only commit the files changed in Task 2.

---

### Task 3: Move Dashboard Out Of The Global Shell

**Files:**
- Modify: `dashboard-v2/src/views/DashboardView.vue`

- [ ] **Step 1: Remove shell-only imports from DashboardView**

In `dashboard-v2/src/views/DashboardView.vue`, remove:

```ts
import { RouterLink } from 'vue-router'
```

Change the workbench import from:

```ts
import {
  WorkbenchHeader,
  WorkbenchMain,
  WorkbenchPanel,
  WorkbenchShell,
  WorkbenchSidebar,
  WorkbenchWorkspace,
} from '@/components/ui/workbench'
```

to:

```ts
import { WorkbenchHeader, WorkbenchMain, WorkbenchPanel } from '@/components/ui/workbench'
```

- [ ] **Step 2: Remove the sidebar and workspace wrapper from the template**

Replace the top of the template by deleting the opening `<WorkbenchShell>`, the complete sidebar block, and the opening `<WorkbenchWorkspace>`.

```vue
<template>
  <WorkbenchHeader class="justify-between">
```

The resulting template starts with:

```vue
<template>
  <WorkbenchHeader class="justify-between">
```

Delete every node from the old `<WorkbenchSidebar class="flex flex-col gap-8">` opening tag through its matching `</WorkbenchSidebar>` closing tag.

- [ ] **Step 3: Remove the closing workspace and shell tags**

Replace the bottom of the template:

```vue
      </WorkbenchMain>
    </WorkbenchWorkspace>
  </WorkbenchShell>
</template>
```

with:

```vue
  </WorkbenchMain>
</template>
```

- [ ] **Step 4: Verify Dashboard polling stayed page-scoped**

Confirm these lines still exist in `DashboardView.vue`:

```ts
onMounted(() => {
  dashboardAnalysisStore.startPolling()
})

onUnmounted(() => {
  dashboardAnalysisStore.stopPolling()
})
```

Do not move these calls into `AppShell.vue`.

- [ ] **Step 5: Run type-check**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: PASS. If it fails, fix only issues caused by the R0 shell extraction.

- [ ] **Step 6: Commit Dashboard shell extraction**

Run:

```bash
git add dashboard-v2/src/views/DashboardView.vue
git commit -m "refactor: move dashboard view into app shell"
```

---

### Task 4: Final Build Verification

**Files:**
- No additional source files unless verification exposes a R0 regression.

- [ ] **Step 1: Run frontend type-check**

Run:

```bash
cd dashboard-v2
npm run type-check
```

Expected: PASS.

- [ ] **Step 2: Run frontend production build**

Run:

```bash
cd dashboard-v2
npm run build-only
```

Expected: PASS.

- [ ] **Step 3: Optional browser smoke check**

If running a local browser check, start Vite:

```bash
cd dashboard-v2
npm run dev -- --host 127.0.0.1
```

Open the dev server URL and verify these hash routes:

```text
#/
#/dashboard
#/history
#/config/general
#/config/scheduling
#/config/playlists
#/config/tags
#/config/policies
```

Expected:

- `#/` redirects to `#/dashboard`.
- Dashboard shows the existing Dashboard work area.
- History and Config routes show the App Shell and no feature UI.
- Dashboard, History, Config, and each Config secondary item have correct active nav state.

- [ ] **Step 4: Commit any verification fixes**

If verification required source fixes, commit them:

```bash
git add dashboard-v2/src
git commit -m "fix: verify r0 app shell routes"
```

If no fixes were needed, do not create an empty commit.

---

## Plan Self-Review

Spec coverage:

- Shared App Shell: Task 2.
- Formal routes and `/` redirect: Task 1.
- Dashboard no longer owns global sidebar: Task 3.
- Dashboard polling remains page-scoped: Task 3.
- Sidebar primary and Config secondary active state: Task 2 and Task 4.
- No History or Config API calls: Task 1 creates only `RouteBoundaryView.vue`; no API modules are touched.
- Required verification commands: Task 4.

Completion scan:

- No unfinished sections are used.

Type consistency:

- Route names and paths match the approved design.
- Sidebar labels reuse existing i18n keys except the new `app_shell_label`, `app_shell_subtitle`, and `config_general` keys added in Task 2.
