<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useColorMode } from '@vueuse/core'
import { Monitor, Moon, Sun } from 'lucide-vue-next'
import { storeToRefs } from 'pinia'

import { Button } from '@/components/ui/button'
import { WorkbenchHeader, WorkbenchMain, WorkbenchPanel } from '@/components/ui/workbench'
import { useI18n } from '@/composables/useI18n'
import ActPanel from '@/features/dashboard-analysis/ActPanel.vue'
import DashboardTimeline from '@/features/dashboard-analysis/DashboardTimeline.vue'
import SensePanel from '@/features/dashboard-analysis/SensePanel.vue'
import ThinkPanel from '@/features/dashboard-analysis/ThinkPanel.vue'
import { cn } from '@/lib/utils'
import { useDashboardAnalysisStore } from '@/stores/dashboardAnalysis'

const { t } = useI18n()
const colorMode = useColorMode({ emitAuto: true })
const dashboardAnalysisStore = useDashboardAnalysisStore()

const {
  activeTick,
  activeTickId,
  error,
  hasUnseenLiveTicks,
  isDisconnected,
  mode,
  newTicksSinceLocked,
  timelineTicks,
  workspaceState,
} = storeToRefs(dashboardAnalysisStore)

onMounted(() => {
  dashboardAnalysisStore.startPolling()
})

onUnmounted(() => {
  dashboardAnalysisStore.stopPolling()
})

const statusLabel = computed(() =>
  isDisconnected.value ? t('dashboard_disconnected_status') : t('dashboard_live_status'),
)

const statusBadgeClass = computed(() =>
  cn(
    'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium data-mono',
    isDisconnected.value
      ? 'border-destructive/20 bg-destructive/10 text-destructive'
      : 'border-primary/20 bg-primary/10 text-primary',
  ),
)

const themeIcon = computed(() => {
  switch (colorMode.value) {
    case 'light':
      return Sun
    case 'dark':
      return Moon
    default:
      return Monitor
  }
})

function cycleTheme(): void {
  colorMode.value =
    colorMode.value === 'light' ? 'dark' : colorMode.value === 'dark' ? 'auto' : 'light'
}
</script>

<template>
  <WorkbenchHeader class="justify-between">
    <div class="min-w-0">
      <div class="flex min-w-0 items-center gap-3">
        <h2 class="truncate text-lg font-semibold tracking-tight">
          {{ t('dashboard_shell_title') }}
        </h2>
        <span :class="statusBadgeClass">
          <span
            :class="cn('size-2 rounded-full', isDisconnected ? 'bg-destructive' : 'bg-primary')"
          />
          {{ statusLabel }}
        </span>
        <span
          v-if="mode === 'snapshot'"
          class="hidden rounded-full border border-border/70 bg-muted/70 px-3 py-1 text-xs font-medium text-muted-foreground md:inline-flex"
        >
          {{ t('dashboard_snapshot_status') }}
        </span>
      </div>
    </div>

    <Button variant="ghost" size="icon" @click="cycleTheme">
      <component :is="themeIcon" class="size-4" />
      <span class="sr-only">{{ t(`theme_${colorMode}`) }}</span>
    </Button>
  </WorkbenchHeader>

  <WorkbenchMain>
    <WorkbenchPanel
      v-if="workspaceState === 'loading'"
      padding="lg"
      class="flex min-h-[28rem] flex-1 flex-col justify-center"
    >
      <div class="mx-auto flex max-w-xl flex-col items-center gap-4 text-center">
        <h3 class="text-2xl font-semibold tracking-tight">
          {{ t('dashboard_loading_title') }}
        </h3>
        <p class="max-w-lg text-sm leading-6 text-muted-foreground">
          {{ t('dashboard_loading_body') }}
        </p>
      </div>
    </WorkbenchPanel>

    <WorkbenchPanel
      v-else-if="workspaceState === 'error'"
      padding="lg"
      class="flex min-h-[28rem] flex-1 flex-col justify-center"
    >
      <div class="mx-auto flex max-w-xl flex-col items-center gap-5 text-center">
        <h3 class="text-2xl font-semibold tracking-tight">
          {{ t('dashboard_error_title') }}
        </h3>
        <p class="max-w-lg text-sm leading-6 text-muted-foreground">
          {{ t('dashboard_error_body') }}
        </p>
        <div
          class="w-full rounded-2xl border border-destructive/15 bg-destructive/6 px-4 py-3 text-left"
        >
          <p class="chrome-kicker text-destructive">
            {{ t('dashboard_last_error') }}
          </p>
          <p class="mt-2 break-all text-sm text-foreground">
            {{ error ?? t('dashboard_metric_unavailable') }}
          </p>
        </div>
        <Button @click="dashboardAnalysisStore.retry()">
          {{ t('dashboard_retry') }}
        </Button>
      </div>
    </WorkbenchPanel>

    <WorkbenchPanel
      v-else-if="workspaceState === 'empty'"
      padding="lg"
      class="flex min-h-[28rem] flex-1 flex-col justify-center"
    >
      <div class="mx-auto flex max-w-xl flex-col items-center gap-4 text-center">
        <h3 class="text-2xl font-semibold tracking-tight">
          {{ t('dashboard_empty_title') }}
        </h3>
        <p class="max-w-lg text-sm leading-6 text-muted-foreground">
          {{ t('dashboard_empty_body') }}
        </p>
      </div>
    </WorkbenchPanel>

    <template v-else-if="activeTick !== null">
      <WorkbenchPanel padding="lg">
        <DashboardTimeline
          :ticks="timelineTicks"
          :active-tick-id="activeTickId"
          :mode="mode"
          :is-disconnected="isDisconnected"
          :new-ticks-since-locked="newTicksSinceLocked"
          :has-unseen-live-ticks="hasUnseenLiveTicks"
          @hover-tick="dashboardAnalysisStore.hoverTick"
          @clear-hover="dashboardAnalysisStore.clearHover"
          @lock-tick="dashboardAnalysisStore.lockTick"
          @unlock-to-live="dashboardAnalysisStore.unlockToLive"
          @step="dashboardAnalysisStore.stepLockedTick"
        />
      </WorkbenchPanel>

      <div class="grid gap-4 xl:grid-cols-[0.95fr_1.1fr_1fr]">
        <WorkbenchPanel padding="lg">
          <SensePanel :tick="activeTick" />
        </WorkbenchPanel>

        <WorkbenchPanel padding="lg">
          <ThinkPanel :tick="activeTick" />
        </WorkbenchPanel>

        <WorkbenchPanel padding="lg">
          <ActPanel :tick="activeTick" />
        </WorkbenchPanel>
      </div>
    </template>
  </WorkbenchMain>
</template>
