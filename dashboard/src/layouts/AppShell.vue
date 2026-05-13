<script setup lang="ts">
import type { Component } from 'vue'
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { History, LayoutDashboard, Settings } from 'lucide-vue-next'

import { WorkbenchShell, WorkbenchSidebar, WorkbenchWorkspace } from '@/components/ui/workbench'
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
