import { ref, computed } from 'vue'

export interface PlaylistConfig {
  name: string
  display: string
  color: string
  tags: Record<string, number>
}

export interface TagSpec {
  fallback: Record<string, number>
}

export interface BasePolicyConfig {
  enabled: boolean
  weight_scale: number
}

export interface ActivityPolicyConfig extends BasePolicyConfig {
  smoothing_window: number
  process_rules: Record<string, string>
  title_rules: Record<string, string>
}

export interface TimePolicyConfig extends BasePolicyConfig {
  auto: boolean
  day_start_hour: number
  night_start_hour: number
}

export interface SeasonPolicyConfig extends BasePolicyConfig {
  spring_peak: number
  summer_peak: number
  autumn_peak: number
  winter_peak: number
}

export interface WeatherPolicyConfig extends BasePolicyConfig {
  api_key: string
  lat: number | null
  lon: number | null
  fetch_interval: number
  request_timeout: number
  warmup_timeout: number
}

export interface PoliciesConfig {
  activity: ActivityPolicyConfig
  time: TimePolicyConfig
  season: SeasonPolicyConfig
  weather: WeatherPolicyConfig
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
  language: string | null
  playlists: PlaylistConfig[]
  tags: Record<string, TagSpec>
  policies: PoliciesConfig
  scheduling: SchedulingConfig
}

export interface ConfigValidationScope {
  kind: 'policy' | 'playlist' | 'tag'
  key?: string
  index?: number
}

export interface ConfigValidationDetail {
  path: Array<string | number>
  message: string
  code: string
  section: 'general' | 'scheduling' | 'playlists' | 'tags' | 'policies' | null
  scope: ConfigValidationScope | null
}

export interface ConfigDocumentResponse {
  current: AppConfig
  defaults: AppConfig
}

export interface SaveResult {
  ok: boolean
  errors?: ConfigValidationDetail[]
  message?: string
}

export interface ScanResult {
  playlists: string[]
  error?: string
}

export function useConfig() {
  const document = ref<ConfigDocumentResponse | null>(null)
  const loading = ref(false)
  const saveError = ref<string | null>(null)
  const saving = ref(false)
  const tagPresets = ref<string[]>([])
  const wePlaylists = ref<string[]>([])

  let savedSnapshot = ''
  const config = computed(() => document.value?.current ?? null)
  const defaults = computed(() => document.value?.defaults ?? null)

  const isDirty = computed(() => {
    if (!document.value) return false
    return JSON.stringify(config.value) !== savedSnapshot
  })

  async function fetchConfig(): Promise<void> {
    loading.value = true
    try {
      const res = await fetch('/api/config')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      document.value = (await res.json()) as ConfigDocumentResponse
      savedSnapshot = JSON.stringify(document.value.current)
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
      await fetchConfig()
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
    document, config, defaults, loading, saveError, saving, isDirty,
    tagPresets, wePlaylists,
    fetchConfig, saveConfig, fetchTagPresets, scanPlaylists,
  }
}
