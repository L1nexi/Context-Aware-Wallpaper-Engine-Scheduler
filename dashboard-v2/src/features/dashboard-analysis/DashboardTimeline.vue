<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import VChart from 'vue-echarts'

import { Button } from '@/components/ui/button'
import { useI18n } from '@/composables/useI18n'
import type { TickSnapshot } from '@/lib/dashboardAnalysis'

import { formatTimestamp } from './formatting'
import { buildTimelineOption, resolveTimelineIndexFromPixel } from './timeline'

type DashboardMode = 'live' | 'snapshot'

const props = defineProps<{
  ticks: TickSnapshot[]
  activeTickId: number | null
  mode: DashboardMode
  isDisconnected: boolean
  newTicksSinceLocked: number
  hasUnseenLiveTicks: boolean
}>()

const emit = defineEmits<{
  hoverTick: [tickId: number]
  clearHover: []
  lockTick: [tickId: number]
  unlockToLive: []
  step: [delta: number]
}>()

const { t, lang } = useI18n()

const chartRef = ref<InstanceType<typeof VChart> | null>(null)
const isFocused = ref(false)
let detachHandlers: (() => void) | null = null

function getChartInstance() {
  return chartRef.value?.chart
}

const currentTick = computed(() => {
  if (props.activeTickId === null) {
    return props.ticks[props.ticks.length - 1] ?? null
  }

  return (
    props.ticks.find((tick) => tick.summary.tickId === props.activeTickId) ??
    props.ticks[props.ticks.length - 1] ??
    null
  )
})

const option = computed(() =>
  buildTimelineOption(
    props.ticks,
    lang.value,
    {
      activeTrack: t('dashboard_timeline_active_track'),
      matchedTrack: t('dashboard_timeline_matched_track'),
      switch: t('dashboard_timeline_switch_marker'),
      cycle: t('dashboard_timeline_cycle_marker'),
      similarity: t('similarity'),
      gap: t('gap'),
    },
    t,
  ),
)

const statusLabel = computed(() =>
  props.mode === 'snapshot'
    ? t('dashboard_snapshot_status')
    : t('dashboard_live_following_status'),
)

const selectedTimestamp = computed(() =>
  formatTimestamp(currentTick.value?.summary.ts, lang.value, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }),
)

function clearProgrammaticTooltip(): void {
  const chart = chartRef.value
  if (!chart) {
    return
  }

  chart.dispatchAction({ type: 'hideTip' })
}

function bindChartHandlers(): void {
  const chart = chartRef.value
  const chartInstance = getChartInstance()
  if (!chart || !chartInstance) {
    return
  }

  const zr = chartInstance.getZr()

  const handleMove = (event: { offsetX: number; offsetY: number }) => {
    if (props.mode === 'snapshot') {
      return
    }

    const index = resolveTimelineIndexFromPixel(
      event.offsetX,
      event.offsetY,
      props.ticks,
      chart,
    )
    if (index === null) {
      return
    }

    const tick = props.ticks[index]
    if (tick) {
      emit('hoverTick', tick.summary.tickId)
    }
  }

  const handleClick = (event: { offsetX: number; offsetY: number }) => {
    if (props.mode === 'snapshot') {
      return
    }

    const index = resolveTimelineIndexFromPixel(
      event.offsetX,
      event.offsetY,
      props.ticks,
      chart,
    )
    if (index === null) {
      return
    }

    const tick = props.ticks[index]
    if (tick) {
      emit('lockTick', tick.summary.tickId)
    }
  }

  const handleOut = () => {
    if (props.mode === 'live') {
      emit('clearHover')
    }
  }

  zr.on('mousemove', handleMove)
  zr.on('click', handleClick)
  zr.on('globalout', handleOut)

  detachHandlers = () => {
    zr.off('mousemove', handleMove)
    zr.off('click', handleClick)
    zr.off('globalout', handleOut)
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (props.mode !== 'snapshot') {
    return
  }

  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    emit('step', -1)
  }

  if (event.key === 'ArrowRight') {
    event.preventDefault()
    emit('step', 1)
  }
}

watch(
  () => chartRef.value?.chart,
  async (chart) => {
    detachHandlers?.()
    detachHandlers = null

    if (!chart) {
      return
    }

    await nextTick()
    bindChartHandlers()
    clearProgrammaticTooltip()
  },
  { immediate: true },
)

watch(
  () => [props.activeTickId, props.ticks, props.mode],
  async () => {
    await nextTick()
    clearProgrammaticTooltip()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  detachHandlers?.()
  detachHandlers = null
})
</script>

<template>
  <section class="flex flex-col gap-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p class="chrome-kicker">{{ t('dashboard_timeline_title') }}</p>
        <div class="mt-2 flex flex-wrap items-center gap-3">
          <h3 class="text-xl font-semibold tracking-tight">
            {{ t('dashboard_timeline_heading') }}
          </h3>
          <span
            class="inline-flex items-center rounded-full border border-border/70 bg-muted/70 px-3 py-1 text-xs font-medium text-muted-foreground"
          >
            {{ statusLabel }}
          </span>
          <span
            v-if="isDisconnected"
            class="inline-flex items-center rounded-full border border-destructive/20 bg-destructive/10 px-3 py-1 text-xs font-medium text-destructive"
          >
            {{ t('dashboard_disconnected_status') }}
          </span>
        </div>
        <p class="mt-2 text-sm leading-6 text-muted-foreground">
          {{ t('dashboard_timeline_body') }}
        </p>
      </div>

      <div class="flex flex-col items-start gap-3 sm:items-end">
        <div class="flex flex-wrap items-center gap-2 sm:justify-end">
          <span
            class="inline-flex items-center gap-2 rounded-full border border-border/70 bg-muted/70 px-3 py-1 text-xs font-medium text-muted-foreground"
          >
            <span>{{ t('dashboard_metric_selected_tick') }}</span>
            <span class="data-mono text-foreground">
              {{ activeTickId ?? '—' }}
            </span>
          </span>
          <p class="text-sm text-muted-foreground data-mono">
            {{ selectedTimestamp }}
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <span
            v-if="hasUnseenLiveTicks"
            class="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
          >
            {{ t('dashboard_live_delta', { count: newTicksSinceLocked }) }}
          </span>
          <Button
            v-if="mode === 'snapshot'"
            variant="outline"
            size="sm"
            @click="emit('unlockToLive')"
          >
            {{ t('dashboard_back_to_live') }}
          </Button>
        </div>
      </div>
    </div>

    <div class="flex flex-wrap gap-2 text-xs text-muted-foreground">
      <span class="inline-flex items-center gap-2 rounded-full border border-border/70 bg-muted/45 px-3 py-1.5">
        <span class="size-2.5 rounded-full bg-primary" />
        {{ t('dashboard_timeline_active_track') }}
      </span>
      <span class="inline-flex items-center gap-2 rounded-full border border-border/70 bg-muted/45 px-3 py-1.5">
        <span class="size-2.5 rounded-full bg-[var(--color-chart-2)]" />
        {{ t('dashboard_timeline_matched_track') }}
      </span>
      <span class="inline-flex items-center gap-2 rounded-full border border-border/70 bg-muted/45 px-3 py-1.5">
        <span class="size-2.5 rotate-45 bg-primary" />
        {{ t('dashboard_timeline_switch_marker') }}
      </span>
      <span class="inline-flex items-center gap-2 rounded-full border border-border/70 bg-muted/45 px-3 py-1.5">
        <span class="size-2.5 rounded-full bg-muted-foreground/65" />
        {{ t('paused') }}
      </span>
    </div>

    <div
      class="rounded-3xl border border-border/70 bg-background/70 p-3 shadow-sm outline-none transition-shadow focus-visible:ring-4 focus-visible:ring-ring/15"
      :class="isFocused ? 'shadow-[var(--shadow-focus)]' : ''"
      tabindex="0"
      :aria-label="t('dashboard_timeline_focus_label')"
      @blur="isFocused = false"
      @focus="isFocused = true"
      @keydown="handleKeydown"
    >
      <VChart
        ref="chartRef"
        class="h-[24.5rem] w-full"
        :option="option"
        autoresize
      />
    </div>

    <p class="text-xs leading-5 text-muted-foreground">
      {{
        mode === 'snapshot'
          ? t('dashboard_timeline_snapshot_hint')
          : t('dashboard_timeline_live_hint')
      }}
    </p>
  </section>
</template>
