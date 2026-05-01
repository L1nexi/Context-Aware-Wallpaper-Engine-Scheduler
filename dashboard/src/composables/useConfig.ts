import { ref, computed } from 'vue'

export interface PlaylistConfig {
  name: string
  display?: string
  tags: Record<string, number>
}

export interface SchedulingConfig {
  startup_delay: number
  idle_threshold: number
  switch_cooldown: number
  cycle_cooldown: number
  force_after: number
  cpu_threshold: number
  cpu_sample_window: number
  pause_on_fullscreen: boolean
}

export interface AppConfig {
  wallpaper_engine_path: string
  language?: string | null
  playlists: PlaylistConfig[]
  tags: Record<string, { fallback: Record<string, number> }>
  policies: Record<string, unknown>
  scheduling: SchedulingConfig
}

export interface FieldError {
  field: string
  message: string
}

export interface SaveResult {
  ok: boolean
  errors?: FieldError[]
  message?: string
}

export interface ScanResult {
  playlists: string[]
  error?: string
}

export function useConfig() {
  const config = ref<AppConfig | null>(null)
  const loading = ref(false)
  const saveError = ref<string | null>(null)
  const saving = ref(false)
  const tagPresets = ref<string[]>([])
  const wePlaylists = ref<string[]>([])

  let savedSnapshot = ''

  const isDirty = computed(() => {
    if (!config.value) return false
    return JSON.stringify(config.value) !== savedSnapshot
  })

  async function fetchConfig(): Promise<void> {
    loading.value = true
    try {
      const res = await fetch('/api/config')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      config.value = await res.json()
      savedSnapshot = JSON.stringify(config.value)
    } catch (e) {
      saveError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function saveConfig(data: AppConfig): Promise<SaveResult> {
    saving.value = true
    saveError.value = null
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      const result = await res.json()
      if (!res.ok) {
        saveError.value = result.details?.[0]?.message || result.error || 'Unknown error'
        return { ok: false, errors: result.details, message: result.error }
      }
      config.value = data
      savedSnapshot = JSON.stringify(data)
      return { ok: true }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      saveError.value = msg
      return { ok: false, message: msg }
    } finally {
      saving.value = false
    }
  }

  async function fetchTagPresets(): Promise<void> {
    try {
      const res = await fetch('/api/tags/presets')
      if (res.ok) tagPresets.value = await res.json()
    } catch {
      // Presets are optional; failure is non-critical.
    }
  }

  async function scanPlaylists(): Promise<void> {
    try {
      const res = await fetch('/api/playlists/scan')
      if (res.ok) {
        const data: ScanResult = await res.json()
        wePlaylists.value = data.playlists || []
      }
    } catch {
      // Scan is best-effort; failure is non-critical.
    }
  }

  return {
    config, loading, saveError, saving, isDirty,
    tagPresets, wePlaylists,
    fetchConfig, saveConfig, fetchTagPresets, scanPlaylists,
  }
}
