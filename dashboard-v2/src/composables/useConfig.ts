import { ref, computed } from 'vue'

import type {
  AppConfig,
  ConfigDocumentResponse,
  ConfigValidationDetail,
} from '@/lib/configDocument'

export type {
  ActivityPolicyConfig,
  AppConfig,
  BasePolicyConfig,
  ConfigDocumentResponse,
  ConfigValidationDetail,
  ConfigValidationScope,
  PlaylistConfig,
  PoliciesConfig,
  SchedulingConfig,
  SeasonPolicyConfig,
  TagSpec,
  TimePolicyConfig,
  WeatherPolicyConfig,
} from '@/lib/configDocument'

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
    document,
    config,
    defaults,
    loading,
    saveError,
    saving,
    isDirty,
    tagPresets,
    wePlaylists,
    fetchConfig,
    saveConfig,
    fetchTagPresets,
    scanPlaylists,
  }
}
