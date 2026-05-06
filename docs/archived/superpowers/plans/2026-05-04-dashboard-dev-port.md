# Dashboard Dev Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit host-side dashboard API port option for development while keeping production default behavior dynamic and letting `dashboard-v2` use `npm run dev` through a same-origin `/api` proxy.

**Architecture:** The host process gains a public `--dashboard-api-port` option that is passed into `DashboardHTTPServer`, while the existing hidden `--port` argument remains reserved for the dashboard subprocess. The frontend keeps relative `/api` fetches and relies on a Vite dev proxy so browser automation can target the dev page without CORS changes.

**Tech Stack:** Python 3, Bottle/wsgiref, pytest, Vite, Vue 3, TypeScript

---

### Task 1: Lock backend port behavior with tests

**Files:**
- Modify: `tests/test_dashboard_api.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing tests for explicit dashboard server ports**
- [ ] **Step 2: Run the targeted pytest selection and verify failure**
- [ ] **Step 3: Implement the minimum backend changes for configurable binding**
- [ ] **Step 4: Re-run targeted pytest selection and verify green**

### Task 2: Expose host CLI and wire the requested port through startup

**Files:**
- Modify: `main.py`
- Modify: `ui/dashboard.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Add a failing CLI parser test only if lightweight; otherwise cover the behavior through focused runtime tests**
- [ ] **Step 2: Implement `--dashboard-api-port` with default `0` and pass it into `DashboardHTTPServer`**
- [ ] **Step 3: Preserve the hidden internal `--port` subprocess argument unchanged**
- [ ] **Step 4: Re-run the affected pytest selection**

### Task 3: Add frontend dev proxy support

**Files:**
- Modify: `dashboard-v2/vite.config.ts`

- [ ] **Step 1: Add a Vite `/api` dev proxy targeting the fixed local development port**
- [ ] **Step 2: Keep the proxy development-only and leave build output behavior unchanged**
- [ ] **Step 3: Run `npm run type-check` in `dashboard-v2`**
- [ ] **Step 4: Run `npm run build-only` in `dashboard-v2`**

### Task 4: Verify the integrated flow

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-dashboard-dev-port-design.md` only if implementation reveals a necessary clarification

- [ ] **Step 1: Run `pytest -q tests/test_dashboard_api.py`**
- [ ] **Step 2: Run `cd dashboard-v2 && npm run type-check`**
- [ ] **Step 3: Run `cd dashboard-v2 && npm run build-only`**
- [ ] **Step 4: Summarize the exact behavior change and any remaining manual verification**
