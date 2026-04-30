import { ref, onMounted, onUnmounted } from "vue";

export interface TickState {
  ts: number;
  current_playlist: string;
  current_playlist_display: string;
  similarity: number;
  similarity_gap: number;
  max_policy_magnitude: number;
  top_tags: { tag: string; weight: number }[];
  paused: boolean;
  pause_until: number;
  active_window: string;
  idle_time: number;
  cpu: number;
  fullscreen: boolean;
  locale: string;
  last_event_id: number;
}

const MAX_FAILURES = 1;
const POLL_INTERVAL = 1000;
const ZOMBIE_COUNTDOWN = 3;

export function useApi() {
  const state = ref<TickState | null>(null);
  const ticks = ref<TickState[]>([]);
  const error = ref<string | null>(null);
  const zombie = ref(false);
  const loading = ref(true);
  const countdown = ref(0);

  let timer: ReturnType<typeof setInterval> | null = null;
  let ticksTimer: ReturnType<typeof setInterval> | null = null;
  let cdTimer: ReturnType<typeof setInterval> | null = null;
  let failures = 0;

  async function fetchState() {
    try {
      const res = await fetch("/api/state");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.value = await res.json();
      failures = 0;
      error.value = null;
      loading.value = false;
    } catch (e) {
      failures++;
      error.value = e instanceof Error ? e.message : String(e);
      if (failures >= MAX_FAILURES) {
        if (cdTimer) return; // already triggered, ignore in-flight requests
        zombie.value = true;
        countdown.value = ZOMBIE_COUNTDOWN;
        if (timer) clearInterval(timer);
        if (ticksTimer) clearInterval(ticksTimer);
        cdTimer = setInterval(() => {
          countdown.value--;
          if (countdown.value <= 0) {
            if (cdTimer) clearInterval(cdTimer);
            const w = window as any;
            if (w.pywebview?.api?.close) {
              w.pywebview.api.close();
            }
          }
        }, 1000);
      }
    }
  }

  async function fetchTicks() {
    try {
      const res = await fetch("/api/ticks?count=120");
      if (!res.ok) return;
      const data: TickState[] = await res.json();
      const prev = ticks.value;
      if (
        prev.length !== data.length ||
        (data.length > 0 && data[0]!.ts !== prev[0]?.ts)
      ) {
        ticks.value = data;
      }
    } catch {
      /* silent — ticks are non-critical */
    }
  }

  onMounted(() => {
    fetchState();
    fetchTicks();
    timer = setInterval(fetchState, POLL_INTERVAL);
    ticksTimer = setInterval(fetchTicks, 5000);
  });

  onUnmounted(() => {
    if (timer) clearInterval(timer);
    if (ticksTimer) clearInterval(ticksTimer);
    if (cdTimer) clearInterval(cdTimer);
  });

  return { state, ticks, error, zombie, loading, countdown };
}
