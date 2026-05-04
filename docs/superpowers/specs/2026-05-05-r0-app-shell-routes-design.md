# R0 App Shell / Routes Design

## Goal

R0 establishes the shared `dashboard-v2` application shell and route topology for the next Dashboard V2 phases. It does not implement History or Config business pages.

## Scope

R0 includes:

- Extract the global workbench chrome out of `DashboardView.vue`.
- Add a shared App Shell layout for sidebar, workspace, and route rendering.
- Establish the formal hash-router paths for Dashboard, History, and Config sections.
- Render a hierarchical sidebar with Dashboard, History, and Config section links.
- Preserve Dashboard analysis behavior and polling lifecycle.

R0 excludes:

- History composition API or chart work.
- Config Editor API contract changes.
- Config form state, draft state, validation, save, or restore behavior.
- Visible stub pages that imply History or Config feature completion.

## Route Model

The router remains based on `createWebHashHistory()`.

Formal routes:

```text
/
/dashboard
/history
/config/general
/config/scheduling
/config/playlists
/config/tags
/config/policies
```

`/` redirects to `/dashboard`.

`/dashboard` renders the existing Dashboard analysis page body.

`/history` and `/config/*` are registered so refresh and sidebar active state work, but they stay as thin route boundaries in R0. They must not start calling History or Config APIs.

## Layout Architecture

Add `dashboard-v2/src/layouts/AppShell.vue`.

`AppShell.vue` owns:

- `WorkbenchShell`
- `WorkbenchSidebar`
- `WorkbenchWorkspace`
- sidebar navigation config
- route-driven active state
- the layout-level `<RouterView />`

`AppShell.vue` does not own:

- Dashboard polling
- Dashboard analysis selection state
- History data loading
- Config draft or save state

This keeps global chrome separate from page domain behavior.

## Dashboard Boundary

`dashboard-v2/src/views/DashboardView.vue` should stop owning the global sidebar and shell. It keeps:

- Dashboard header content
- loading, error, empty, and live workbench panels
- timeline and `Sense / Think / Act` content
- `onMounted(() => dashboardAnalysisStore.startPolling())`
- `onUnmounted(() => dashboardAnalysisStore.stopPolling())`

The polling lifecycle remains page-scoped. Navigating away from `/dashboard` stops Dashboard analysis polling.

## Sidebar Model

The sidebar uses one global hierarchy.

Primary links:

- Dashboard -> `/dashboard`
- History -> `/history`
- Config -> parent group for `/config/*`

Config secondary links:

- General -> `/config/general`
- Scheduling -> `/config/scheduling`
- Playlists -> `/config/playlists`
- Tags -> `/config/tags`
- Policies -> `/config/policies`

Active state comes from `useRoute()`:

- Dashboard is active on `/dashboard`.
- History is active on `/history`.
- Config parent is active for any path starting with `/config/`.
- A Config child is active only on its exact route.

The secondary navigation is a sidebar hierarchy, not a second Config sidebar.

## Visual And Engineering Constraints

R0 follows `dashboard-v2/docs/UI_ENGINEERING_SPEC.md`.

Constraints:

- Keep `base: './'`.
- Keep `createWebHashHistory()`.
- Keep locale delivery through dashboard URL query.
- Keep pywebview loading the local HTTP server page.
- Reuse `src/components/ui/workbench/*`.
- Prefer Tailwind utilities and existing tokens.
- Do not add page-specific scoped CSS for shell behavior.
- Do not move business components into `src/components/ui`.

## Acceptance Criteria

R0 is complete when:

- `#/` redirects to `#/dashboard`.
- `#/dashboard` preserves existing Dashboard behavior.
- `#/history` resolves as a route.
- `#/config/general`, `#/config/scheduling`, `#/config/playlists`, `#/config/tags`, and `#/config/policies` resolve as routes.
- Sidebar primary active state works for Dashboard, History, and Config.
- Sidebar Config secondary active state works for each Config section.
- Dashboard polling still starts only while `DashboardView.vue` is mounted.
- History and Config routes do not call their future APIs.

## Verification

Run from `dashboard-v2/`:

```bash
npm run type-check
npm run build-only
```
