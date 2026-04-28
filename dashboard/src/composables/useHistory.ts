import { ref, watch, type Ref } from 'vue'

export interface Segment {
  playlist: string | null
  type?: 'pause' | 'dead'
  start: string
  end: string
}

export interface HistoryEvent {
  ts: string
  type: 'playlist_switch' | 'wallpaper_cycle' | 'pause' | 'resume' | 'start' | 'stop'
  data: Record<string, any>
}

export function useHistory(state: Ref<{ last_event_id: number } | null>) {
  const segments = ref<Segment[]>([])
  const events = ref<HistoryEvent[]>([])
  const loading = ref(true)
  const currentParams = ref<Record<string, string>>({})

  async function fetchHistory(params?: Record<string, string>, showLoading = true) {
    if (showLoading) loading.value = true
    if (params) currentParams.value = { ...params }
    const query = new URLSearchParams(currentParams.value).toString()
    try {
      const res = await fetch(`/api/history?${query}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const body = await res.json()
      segments.value = body.segments
      events.value = body.events
    } catch {
      // Auto-refresh failures are silent (keep stale data visible).
      // Manual requests show empty state on error.
      if (showLoading) {
        segments.value = []
        events.value = []
      }
    } finally {
      if (showLoading) loading.value = false
    }
  }

  // Auto-refresh on any new event — preserves current filter params
  watch(
    () => state.value?.last_event_id,
    (newId, oldId) => {
      if (newId && newId !== oldId) fetchHistory(undefined, false)
    },
  )

  return { segments, events, loading, fetchHistory, currentParams }
}
