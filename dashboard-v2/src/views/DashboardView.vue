<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { RouterLink } from 'vue-router'
import { Button } from '@/components/ui/button'
import {
  WorkbenchHeader,
  WorkbenchMain,
  WorkbenchPanel,
  WorkbenchShell,
  WorkbenchSidebar,
  WorkbenchWorkspace,
} from '@/components/ui/workbench'
import { cn } from '@/lib/utils'
import { useI18n } from '@/composables/useI18n'
import { useDashboardAnalysisStore } from '@/stores/dashboardAnalysis'

const { t, lang } = useI18n()
const dashboardAnalysisStore = useDashboardAnalysisStore()

const {
  activeTick,
  error,
  isDisconnected,
  latestTickId,
  windowCount,
  workspaceState,
} = storeToRefs(dashboardAnalysisStore)

onMounted(() => {
  dashboardAnalysisStore.startPolling()
})

onUnmounted(() => {
  dashboardAnalysisStore.stopPolling()
})

const timestampFormatter = computed(
  () =>
    new Intl.DateTimeFormat(lang.value, {
      dateStyle: 'medium',
      timeStyle: 'medium',
    }),
)

const latestTimestamp = computed(() => {
  const timestamp = activeTick.value?.summary.ts
  if (timestamp === undefined) {
    return t('dashboard_metric_unavailable')
  }

  return timestampFormatter.value.format(new Date(timestamp * 1000))
})

const latestTickIdLabel = computed(() => {
  if (latestTickId.value === null) {
    return t('dashboard_metric_unavailable')
  }

  return String(latestTickId.value)
})

const windowCountLabel = computed(() => String(windowCount.value))

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
</script>

<template>
  <WorkbenchShell>
    <WorkbenchSidebar class="flex flex-col gap-8">
      <div class="flex flex-col gap-3">
        <p class="chrome-kicker">{{ t('dashboard_shell_label') }}</p>
        <div class="space-y-1">
          <h1 class="text-2xl font-semibold tracking-tight text-sidebar-foreground">
            {{ t('appName') }}
          </h1>
          <p class="text-sm leading-6 text-muted-foreground">
            {{ t('dashboard_shell_subtitle') }}
          </p>
        </div>
      </div>

      <nav class="flex flex-col gap-2">
        <RouterLink
          to="/"
          class="flex items-center gap-3 rounded-2xl border border-sidebar-border/70 bg-sidebar-accent/80 px-4 py-3 text-sm font-medium text-sidebar-accent-foreground shadow-sm transition-colors hover:bg-sidebar-accent"
        >
          <span class="inline-flex size-2.5 rounded-full bg-sidebar-primary" />
          <span>{{ t('dashboard_nav') }}</span>
        </RouterLink>
      </nav>
    </WorkbenchSidebar>

    <WorkbenchWorkspace>
      <WorkbenchHeader class="justify-between">
        <div class="min-w-0">
          <p class="chrome-kicker">{{ t('dashboard_shell_label') }}</p>
          <div class="mt-1 flex min-w-0 items-center gap-3">
            <h2 class="truncate text-lg font-semibold tracking-tight">
              {{ t('dashboard_shell_title') }}
            </h2>
            <span :class="statusBadgeClass">
              <span
                :class="
                  cn(
                    'size-2 rounded-full',
                    isDisconnected ? 'bg-destructive' : 'bg-primary',
                  )
                "
              />
              {{ statusLabel }}
            </span>
          </div>
        </div>

        <p class="hidden text-sm text-muted-foreground md:block">
          {{
            isDisconnected
              ? t('dashboard_disconnect_notice')
              : t('dashboard_live_hint')
          }}
        </p>
      </WorkbenchHeader>

      <WorkbenchMain>
        <WorkbenchPanel
          padding="lg"
          class="flex min-h-[28rem] flex-1 flex-col justify-center"
        >
          <div
            v-if="workspaceState === 'loading'"
            class="mx-auto flex max-w-xl flex-col items-center gap-4 text-center"
          >
            <div class="chrome-kicker">{{ t('dashboard_shell_title') }}</div>
            <h3 class="text-2xl font-semibold tracking-tight">
              {{ t('dashboard_loading_title') }}
            </h3>
            <p class="max-w-lg text-sm leading-6 text-muted-foreground">
              {{ t('dashboard_loading_body') }}
            </p>
          </div>

          <div
            v-else-if="workspaceState === 'error'"
            class="mx-auto flex max-w-xl flex-col items-center gap-5 text-center"
          >
            <div class="chrome-kicker">{{ t('dashboard_shell_title') }}</div>
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

          <div
            v-else-if="workspaceState === 'empty'"
            class="mx-auto flex max-w-xl flex-col items-center gap-4 text-center"
          >
            <div class="chrome-kicker">{{ t('dashboard_shell_title') }}</div>
            <h3 class="text-2xl font-semibold tracking-tight">
              {{ t('dashboard_empty_title') }}
            </h3>
            <p class="max-w-lg text-sm leading-6 text-muted-foreground">
              {{ t('dashboard_empty_body') }}
            </p>
          </div>

          <div v-else class="flex flex-col gap-6">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div class="space-y-2">
                <p class="chrome-kicker">{{ t('dashboard_shell_title') }}</p>
                <h3 class="text-2xl font-semibold tracking-tight">
                  {{ t('dashboard_live_title') }}
                </h3>
                <p class="max-w-2xl text-sm leading-6 text-muted-foreground">
                  {{ t('dashboard_live_body') }}
                </p>
              </div>

              <div
                v-if="isDisconnected"
                class="rounded-2xl border border-destructive/15 bg-destructive/6 px-4 py-3 text-sm text-foreground"
              >
                {{ t('dashboard_disconnect_notice') }}
              </div>
            </div>

            <div class="grid gap-4 md:grid-cols-3">
              <section
                class="rounded-3xl border border-border/70 bg-background/70 p-5 shadow-sm"
              >
                <p class="chrome-kicker">{{ t('dashboard_metric_latest_tick') }}</p>
                <p class="mt-3 text-3xl font-semibold tracking-tight data-mono">
                  {{ latestTickIdLabel }}
                </p>
              </section>

              <section
                class="rounded-3xl border border-border/70 bg-background/70 p-5 shadow-sm"
              >
                <p class="chrome-kicker">{{ t('dashboard_metric_latest_timestamp') }}</p>
                <p class="mt-3 text-lg font-medium tracking-tight data-mono">
                  {{ latestTimestamp }}
                </p>
              </section>

              <section
                class="rounded-3xl border border-border/70 bg-background/70 p-5 shadow-sm"
              >
                <p class="chrome-kicker">{{ t('dashboard_metric_window_count') }}</p>
                <p class="mt-3 text-3xl font-semibold tracking-tight data-mono">
                  {{ windowCountLabel }}
                </p>
              </section>
            </div>
          </div>
        </WorkbenchPanel>
      </WorkbenchMain>
    </WorkbenchWorkspace>
  </WorkbenchShell>
</template>
