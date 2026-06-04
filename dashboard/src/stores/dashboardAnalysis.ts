import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  DASHBOARD_ANALYSIS_POLL_INTERVAL_MS,
  fetchDashboardAnalysisWindow,
  type TickSnapshot,
} from '@/lib/dashboardAnalysis'

const DASHBOARD_ANALYSIS_ERROR_POLL_INTERVAL_MS = 5000

type DashboardMode = 'live' | 'snapshot'
type WorkspaceState = 'loading' | 'error' | 'empty' | 'live'

function getLatestTickId(window: TickSnapshot[]): number | null {
  return window[window.length - 1]?.summary.tickId ?? null
}

function findTickById(window: TickSnapshot[], tickId: number | null): TickSnapshot | null {
  if (tickId === null) {
    return null
  }

  for (let index = window.length - 1; index >= 0; index -= 1) {
    const tick = window[index]
    if (tick?.summary.tickId === tickId) {
      return tick
    }
  }

  return null
}

export const useDashboardAnalysisStore = defineStore('dashboardAnalysis', () => {
  const liveWindow = ref<TickSnapshot[]>([])
  const snapshotWindow = ref<TickSnapshot[] | null>(null)
  const liveTickId = ref<number | null>(null)
  const selectedTickId = ref<number | null>(null)
  const hoverTickId = ref<number | null>(null)
  const lockedTickId = ref<number | null>(null)
  const mode = ref<DashboardMode>('live')
  const loading = ref(true)
  const error = ref<string | null>(null)
  const newTicksSinceLocked = ref(0)
  const hasLoadedOnce = ref(false)

  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let currentInterval = DASHBOARD_ANALYSIS_POLL_INTERVAL_MS
  let requestInFlight = false
  let abortController: AbortController | null = null
  let snapshotLiveBaselineTickId: number | null = null

  const activeWindow = computed<TickSnapshot[]>(() => {
    if (mode.value === 'snapshot' && snapshotWindow.value !== null) {
      return snapshotWindow.value
    }

    return liveWindow.value
  })

  const activeTick = computed<TickSnapshot | null>(() => {
    const preferredTickId =
      mode.value === 'live'
        ? hoverTickId.value ?? selectedTickId.value ?? liveTickId.value
        : selectedTickId.value ?? lockedTickId.value

    return (
      findTickById(activeWindow.value, preferredTickId) ??
      activeWindow.value[activeWindow.value.length - 1] ??
      null
    )
  })

  const activeTickId = computed<number | null>(() => activeTick.value?.summary.tickId ?? null)

  const latestTickId = computed<number | null>(() => getLatestTickId(liveWindow.value))
  const windowCount = computed(() => activeWindow.value.length)
  const isLocked = computed(() => mode.value === 'snapshot' && lockedTickId.value !== null)
  const hasUnseenLiveTicks = computed(() => isLocked.value && newTicksSinceLocked.value > 0)
  const isDisconnected = computed(() => hasLoadedOnce.value && error.value !== null)
  const timelineTicks = computed(() => activeWindow.value)

  const workspaceState = computed<WorkspaceState>(() => {
    if (loading.value && !hasLoadedOnce.value) {
      return 'loading'
    }

    if (!hasLoadedOnce.value && error.value) {
      return 'error'
    }

    if (hasLoadedOnce.value && liveWindow.value.length === 0) {
      return 'empty'
    }

    return 'live'
  })

  function syncLiveSelection(nextLiveTickId: number | null, nextLiveWindow: TickSnapshot[]): void {
    if (mode.value !== 'live') {
      return
    }

    if (hoverTickId.value !== null) {
      return
    }

    selectedTickId.value = nextLiveTickId ?? getLatestTickId(nextLiveWindow)
  }

  async function refresh(): Promise<void> {
    if (requestInFlight) {
      return
    }

    requestInFlight = true
    abortController?.abort()
    abortController = new AbortController()
    const signal = abortController.signal

    if (!hasLoadedOnce.value) {
      loading.value = true
      error.value = null
    }

    try {
      const response = await fetchDashboardAnalysisWindow(signal)
      const nextLiveTickId = response.liveTickId ?? getLatestTickId(response.ticks)

      liveWindow.value = response.ticks
      liveTickId.value = nextLiveTickId
      error.value = null
      hasLoadedOnce.value = true

      if (isLocked.value) {
        const baseline = snapshotLiveBaselineTickId ?? lockedTickId.value
        newTicksSinceLocked.value =
          baseline === null || nextLiveTickId === null
            ? 0
            : Math.max(0, nextLiveTickId - baseline)
      } else {
        newTicksSinceLocked.value = 0
      }

      syncLiveSelection(nextLiveTickId, response.ticks)
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') {
        return
      }
      error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
      loading.value = false
      requestInFlight = false

      const nextInterval = error.value !== null
        ? DASHBOARD_ANALYSIS_ERROR_POLL_INTERVAL_MS
        : DASHBOARD_ANALYSIS_POLL_INTERVAL_MS
      if (refreshTimer !== null && nextInterval !== currentInterval) {
        currentInterval = nextInterval
        clearInterval(refreshTimer)
        refreshTimer = setInterval(() => {
          void refresh()
        }, currentInterval)
      }
    }
  }

  function hoverTick(tickId: number): void {
    if (mode.value !== 'live') {
      return
    }

    if (findTickById(liveWindow.value, tickId) !== null) {
      hoverTickId.value = tickId
    }
  }

  function clearHover(): void {
    if (mode.value !== 'live') {
      return
    }

    hoverTickId.value = null
    selectedTickId.value = liveTickId.value ?? getLatestTickId(liveWindow.value)
  }

  function lockTick(tickId: number): void {
    if (mode.value !== 'live') {
      return
    }

    if (findTickById(liveWindow.value, tickId) === null) {
      return
    }

    snapshotWindow.value = liveWindow.value.slice()
    lockedTickId.value = tickId
    selectedTickId.value = tickId
    hoverTickId.value = null
    mode.value = 'snapshot'
    snapshotLiveBaselineTickId = liveTickId.value ?? getLatestTickId(liveWindow.value)
    newTicksSinceLocked.value = 0
  }

  function unlockToLive(): void {
    mode.value = 'live'
    snapshotWindow.value = null
    lockedTickId.value = null
    hoverTickId.value = null
    selectedTickId.value = liveTickId.value ?? getLatestTickId(liveWindow.value)
    snapshotLiveBaselineTickId = null
    newTicksSinceLocked.value = 0
  }

  function stepLockedTick(delta: number): void {
    if (!isLocked.value || snapshotWindow.value === null || lockedTickId.value === null) {
      return
    }

    const currentTickId = selectedTickId.value ?? lockedTickId.value
    const currentIndex = snapshotWindow.value.findIndex(
      (tick) => tick.summary.tickId === currentTickId,
    )

    if (currentIndex === -1) {
      selectedTickId.value = lockedTickId.value
      return
    }

    const nextIndex = Math.min(
      Math.max(currentIndex + delta, 0),
      snapshotWindow.value.length - 1,
    )

    selectedTickId.value = snapshotWindow.value[nextIndex]?.summary.tickId ?? currentTickId
  }

  function startPolling(): void {
    if (refreshTimer !== null) {
      return
    }

    currentInterval = DASHBOARD_ANALYSIS_POLL_INTERVAL_MS
    void refresh()
    refreshTimer = setInterval(() => {
      void refresh()
    }, currentInterval)
  }

  function stopPolling(): void {
    if (refreshTimer !== null) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }

    abortController?.abort()
    abortController = null
    currentInterval = DASHBOARD_ANALYSIS_POLL_INTERVAL_MS
  }

  function retry(): void {
    void refresh()
  }

  return {
    liveWindow,
    snapshotWindow,
    liveTickId,
    selectedTickId,
    hoverTickId,
    lockedTickId,
    mode,
    loading,
    error,
    newTicksSinceLocked,
    activeWindow,
    activeTick,
    activeTickId,
    latestTickId,
    windowCount,
    workspaceState,
    isLocked,
    isDisconnected,
    hasUnseenLiveTicks,
    timelineTicks,
    refresh,
    retry,
    hoverTick,
    clearHover,
    lockTick,
    unlockToLive,
    stepLockedTick,
    startPolling,
    stopPolling,
  }
})
