import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  DASHBOARD_ANALYSIS_POLL_INTERVAL_MS,
  fetchDashboardAnalysisWindow,
  type TickSnapshot,
} from '@/lib/dashboardAnalysis'

type DashboardMode = 'live' | 'snapshot'
type WorkspaceState = 'loading' | 'error' | 'empty' | 'live'

export const useDashboardAnalysisStore = defineStore('dashboardAnalysis', () => {
  const ticks = ref<TickSnapshot[]>([])
  const liveTickId = ref<number | null>(null)
  const selectedTickId = ref<number | null>(null)
  const hoverTickId = ref<number | null>(null)
  const lockedTickId = ref<number | null>(null)
  const mode = ref<DashboardMode>('live')
  const loading = ref(true)
  const error = ref<string | null>(null)
  const hasLoadedOnce = ref(false)

  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let requestInFlight = false

  function findTickById(tickId: number | null): TickSnapshot | null {
    if (tickId === null) {
      return null
    }

    for (let index = ticks.value.length - 1; index >= 0; index -= 1) {
      const tick = ticks.value[index]
      if (tick?.summary.tickId === tickId) {
        return tick
      }
    }

    return null
  }

  const activeTick = computed<TickSnapshot | null>(() => {
    const preferredTickId =
      lockedTickId.value ??
      hoverTickId.value ??
      selectedTickId.value ??
      liveTickId.value

    return findTickById(preferredTickId) ?? ticks.value[ticks.value.length - 1] ?? null
  })

  const latestTickId = computed<number | null>(
    () => activeTick.value?.summary.tickId ?? liveTickId.value,
  )

  const windowCount = computed(() => ticks.value.length)

  const workspaceState = computed<WorkspaceState>(() => {
    if (loading.value && !hasLoadedOnce.value) {
      return 'loading'
    }

    if (!hasLoadedOnce.value && error.value) {
      return 'error'
    }

    if (hasLoadedOnce.value && ticks.value.length === 0) {
      return 'empty'
    }

    return 'live'
  })

  const isDisconnected = computed(() => hasLoadedOnce.value && error.value !== null)

  async function refresh(): Promise<void> {
    if (requestInFlight) {
      return
    }

    requestInFlight = true

    if (!hasLoadedOnce.value) {
      loading.value = true
      error.value = null
    }

    try {
      const response = await fetchDashboardAnalysisWindow()
      ticks.value = response.ticks
      liveTickId.value = response.liveTickId
      error.value = null
      hasLoadedOnce.value = true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
      loading.value = false
      requestInFlight = false
    }
  }

  function startPolling(): void {
    if (refreshTimer !== null) {
      return
    }

    void refresh()
    refreshTimer = setInterval(() => {
      void refresh()
    }, DASHBOARD_ANALYSIS_POLL_INTERVAL_MS)
  }

  function stopPolling(): void {
    if (refreshTimer !== null) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  function retry(): void {
    void refresh()
  }

  return {
    ticks,
    liveTickId,
    selectedTickId,
    hoverTickId,
    lockedTickId,
    mode,
    loading,
    error,
    activeTick,
    latestTickId,
    windowCount,
    workspaceState,
    isDisconnected,
    refresh,
    retry,
    startPolling,
    stopPolling,
  }
})
