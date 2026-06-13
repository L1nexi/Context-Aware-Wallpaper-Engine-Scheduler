import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  DIAGNOSTIC_POLL_INTERVAL_MS,
  fetchDiagnosticWindow,
} from '@/features/diagnostic/api'
import type { DiagnosticTickSnapshot } from '@/features/diagnostic/types'

const DIAGNOSTIC_ERROR_POLL_INTERVAL_MS = 5000

export type DiagnosticViewMode = 'live' | 'snapshot'
export type DiagnosticWorkspaceState = 'loading' | 'error' | 'empty' | 'live'

function getLatestTickId(ticks: DiagnosticTickSnapshot[]): number | null {
  return ticks[ticks.length - 1]?.summary.tickId ?? null
}

function findTickById(
  ticks: DiagnosticTickSnapshot[],
  tickId: number | null,
): DiagnosticTickSnapshot | null {
  if (tickId === null) {
    return null
  }

  for (let index = ticks.length - 1; index >= 0; index -= 1) {
    const tick = ticks[index]
    if (tick?.summary.tickId === tickId) {
      return tick
    }
  }

  return null
}

export const useDiagnosticStore = defineStore('diagnostic', () => {
  const liveTicks = ref<DiagnosticTickSnapshot[]>([])
  const snapshotTicks = ref<DiagnosticTickSnapshot[] | null>(null)
  const liveTickId = ref<number | null>(null)
  const selectedTickId = ref<number | null>(null)
  const hoverTickId = ref<number | null>(null)
  const lockedTickId = ref<number | null>(null)
  const mode = ref<DiagnosticViewMode>('live')
  const loading = ref(true)
  const error = ref<string | null>(null)
  const newTicksSinceLocked = ref(0)
  const hasLoadedOnce = ref(false)

  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let currentInterval = DIAGNOSTIC_POLL_INTERVAL_MS
  let requestInFlight = false
  let abortController: AbortController | null = null
  let snapshotLiveBaselineTickId: number | null = null

  const activeTicks = computed<DiagnosticTickSnapshot[]>(() => {
    if (mode.value === 'snapshot' && snapshotTicks.value !== null) {
      return snapshotTicks.value
    }

    return liveTicks.value
  })

  const activeTick = computed<DiagnosticTickSnapshot | null>(() => {
    const preferredTickId =
      mode.value === 'live'
        ? (hoverTickId.value ?? selectedTickId.value ?? liveTickId.value)
        : (selectedTickId.value ?? lockedTickId.value)

    return (
      findTickById(activeTicks.value, preferredTickId) ??
      activeTicks.value[activeTicks.value.length - 1] ??
      null
    )
  })

  const activeTickId = computed<number | null>(() => activeTick.value?.summary.tickId ?? null)
  const latestTickId = computed<number | null>(() => getLatestTickId(liveTicks.value))
  const tickCount = computed(() => activeTicks.value.length)
  const isLocked = computed(() => mode.value === 'snapshot' && lockedTickId.value !== null)
  const hasUnseenLiveTicks = computed(() => isLocked.value && newTicksSinceLocked.value > 0)
  const isDisconnected = computed(() => hasLoadedOnce.value && error.value !== null)

  const workspaceState = computed<DiagnosticWorkspaceState>(() => {
    if (loading.value && !hasLoadedOnce.value) {
      return 'loading'
    }

    if (!hasLoadedOnce.value && error.value) {
      return 'error'
    }

    if (hasLoadedOnce.value && liveTicks.value.length === 0) {
      return 'empty'
    }

    return 'live'
  })

  function syncLiveSelection(
    nextLiveTickId: number | null,
    nextLiveTicks: DiagnosticTickSnapshot[],
  ): void {
    if (mode.value !== 'live' || hoverTickId.value !== null) {
      return
    }

    selectedTickId.value = nextLiveTickId ?? getLatestTickId(nextLiveTicks)
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
      const response = await fetchDiagnosticWindow(signal)
      const nextLiveTickId = response.liveTickId ?? getLatestTickId(response.ticks)

      liveTicks.value = response.ticks
      liveTickId.value = nextLiveTickId
      error.value = null
      hasLoadedOnce.value = true

      if (isLocked.value) {
        const baseline = snapshotLiveBaselineTickId ?? lockedTickId.value
        newTicksSinceLocked.value =
          baseline === null || nextLiveTickId === null ? 0 : Math.max(0, nextLiveTickId - baseline)
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

      const nextInterval =
        error.value !== null
          ? DIAGNOSTIC_ERROR_POLL_INTERVAL_MS
          : DIAGNOSTIC_POLL_INTERVAL_MS
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

    if (findTickById(liveTicks.value, tickId) !== null) {
      hoverTickId.value = tickId
    }
  }

  function clearHover(): void {
    if (mode.value !== 'live') {
      return
    }

    hoverTickId.value = null
    selectedTickId.value = liveTickId.value ?? getLatestTickId(liveTicks.value)
  }

  function lockTick(tickId: number): void {
    if (mode.value !== 'live') {
      return
    }

    if (findTickById(liveTicks.value, tickId) === null) {
      return
    }

    snapshotTicks.value = liveTicks.value.slice()
    lockedTickId.value = tickId
    selectedTickId.value = tickId
    hoverTickId.value = null
    mode.value = 'snapshot'
    snapshotLiveBaselineTickId = liveTickId.value ?? getLatestTickId(liveTicks.value)
    newTicksSinceLocked.value = 0
  }

  function unlockToLive(): void {
    mode.value = 'live'
    snapshotTicks.value = null
    lockedTickId.value = null
    hoverTickId.value = null
    selectedTickId.value = liveTickId.value ?? getLatestTickId(liveTicks.value)
    snapshotLiveBaselineTickId = null
    newTicksSinceLocked.value = 0
  }

  function stepLockedTick(delta: number): void {
    if (!isLocked.value || snapshotTicks.value === null || lockedTickId.value === null) {
      return
    }

    const currentTickId = selectedTickId.value ?? lockedTickId.value
    const currentIndex = snapshotTicks.value.findIndex(
      (tick) => tick.summary.tickId === currentTickId,
    )

    if (currentIndex === -1) {
      selectedTickId.value = lockedTickId.value
      return
    }

    const nextIndex = Math.min(Math.max(currentIndex + delta, 0), snapshotTicks.value.length - 1)
    selectedTickId.value = snapshotTicks.value[nextIndex]?.summary.tickId ?? currentTickId
  }

  function startPolling(): void {
    if (refreshTimer !== null) {
      return
    }

    currentInterval = DIAGNOSTIC_POLL_INTERVAL_MS
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
    currentInterval = DIAGNOSTIC_POLL_INTERVAL_MS
  }

  function retry(): void {
    void refresh()
  }

  return {
    liveTicks,
    snapshotTicks,
    liveTickId,
    selectedTickId,
    hoverTickId,
    lockedTickId,
    mode,
    loading,
    error,
    newTicksSinceLocked,
    activeTicks,
    activeTick,
    activeTickId,
    latestTickId,
    tickCount,
    workspaceState,
    isLocked,
    isDisconnected,
    hasUnseenLiveTicks,
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
