import { ref, onMounted, onUnmounted } from 'vue'

export interface TickState {
  ts: number
  current_playlist: string
  current_playlist_display: string
  similarity: number
  similarity_gap: number
  max_policy_magnitude: number
  top_tags: { tag: string; weight: number }[]
  paused: boolean
  pause_until: number
  active_window: string
  idle_time: number
  cpu: number
  fullscreen: boolean
  locale: string
  last_event_id: number
}

const MAX_FAILURES = 3
const POLL_INTERVAL = 1000

export function useApi() {
  const state = ref<TickState | null>(null)
  const ticks = ref<TickState[]>([])
  const error = ref<string | null>(null)
  const zombie = ref(false)
  const loading = ref(true)

  let timer: ReturnType<typeof setInterval> | null = null
  let ticksTimer: ReturnType<typeof setInterval> | null = null
  let failures = 0

  async function fetchState() {
    try {
      const res = await fetch('/api/state')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      state.value = await res.json()
      failures = 0
      error.value = null
      loading.value = false
    } catch (e) {
      failures++
      error.value = e instanceof Error ? e.message : String(e)
      if (failures >= MAX_FAILURES) {
        zombie.value = true
        if (timer) clearInterval(timer)
        if (ticksTimer) clearInterval(ticksTimer)
        setTimeout(() => window.close(), 5000)
      }
    }
  }

  async function fetchTicks() {
    try {
      const res = await fetch('/api/ticks?count=120')
      if (res.ok) ticks.value = await res.json()
    } catch { /* silent — ticks are non-critical */ }
  }

  onMounted(() => {
    fetchState()
    fetchTicks()
    timer = setInterval(fetchState, POLL_INTERVAL)
    ticksTimer = setInterval(fetchTicks, 5000)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    if (ticksTimer) clearInterval(ticksTimer)
  })

  return { state, ticks, error, zombie, loading }
}
