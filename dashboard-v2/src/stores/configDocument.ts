import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  ConfigDocumentLoadError,
  cloneConfig,
  fetchConfigDocument,
  pathToKey,
  saveConfigDocument,
  type AppConfig,
  type ConfigSection,
  type ConfigValidationDetail,
  type SchedulingConfig,
} from '@/lib/configDocument'

export type SchedulingNumberKey = Exclude<keyof SchedulingConfig, 'pause_on_fullscreen'>

const SECTION_KEYS: ConfigSection[] = ['general', 'scheduling', 'playlists', 'tags', 'policies']

function emptySectionErrors(): Record<ConfigSection, ConfigValidationDetail[]> {
  return {
    general: [],
    scheduling: [],
    playlists: [],
    tags: [],
    policies: [],
  }
}

function keyBelongsToSection(key: string, section: ConfigSection): boolean {
  if (section === 'general') {
    return key === 'wallpaper_engine_path' || key === 'language'
  }

  return key === section || key.startsWith(`${section}.`)
}

function withoutKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record }
  delete next[key]
  return next
}

function withoutSection<T>(record: Record<string, T>, section: ConfigSection): Record<string, T> {
  return Object.fromEntries(
    Object.entries(record).filter(([key]) => !keyBelongsToSection(key, section)),
  )
}

export const useConfigDocumentStore = defineStore('configDocument', () => {
  const saved = ref<AppConfig | null>(null)
  const defaults = ref<AppConfig | null>(null)
  const draft = ref<AppConfig | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const loadError = ref<string | null>(null)
  const loadErrorCode = ref<string | null>(null)
  const loadErrorDetails = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const serverErrors = ref<ConfigValidationDetail[]>([])
  const clientErrors = ref<Record<string, string>>({})
  const fieldBuffers = ref<Record<string, string>>({})

  const errorsByPath = computed<Record<string, ConfigValidationDetail[]>>(() => {
    const index: Record<string, ConfigValidationDetail[]> = {}

    for (const error of serverErrors.value) {
      const key = pathToKey(error.path)
      index[key] = [...(index[key] ?? []), error]
    }

    return index
  })

  const errorsBySection = computed<Record<ConfigSection, ConfigValidationDetail[]>>(() => {
    const index = emptySectionErrors()

    for (const error of serverErrors.value) {
      if (error.section !== null) {
        index[error.section].push(error)
      }
    }

    return index
  })

  const globalErrors = computed(() => serverErrors.value.filter((error) => error.section === null))

  const isDirty = computed(() => {
    if (saved.value === null || draft.value === null) {
      return false
    }

    return (
      JSON.stringify(saved.value) !== JSON.stringify(draft.value) ||
      Object.keys(fieldBuffers.value).length > 0
    )
  })

  const hasClientErrors = computed(() => Object.keys(clientErrors.value).length > 0)
  const hasServerErrors = computed(() => serverErrors.value.length > 0)
  const firstClientError = computed(() => Object.values(clientErrors.value)[0] ?? null)
  const canSave = computed(
    () =>
      draft.value !== null &&
      !loading.value &&
      !saving.value &&
      isDirty.value &&
      !hasClientErrors.value,
  )

  function clearAllTransientState(): void {
    saveError.value = null
    serverErrors.value = []
    clientErrors.value = {}
    fieldBuffers.value = {}
  }

  function replaceDocument(document: { current: AppConfig; defaults: AppConfig }): void {
    saved.value = cloneConfig(document.current)
    defaults.value = cloneConfig(document.defaults)
    draft.value = cloneConfig(document.current)
    loadError.value = null
    loadErrorCode.value = null
    loadErrorDetails.value = null
    clearAllTransientState()
  }

  async function load(): Promise<void> {
    loading.value = true
    loadError.value = null
    loadErrorCode.value = null
    loadErrorDetails.value = null

    try {
      replaceDocument(await fetchConfigDocument())
    } catch (cause) {
      saved.value = null
      defaults.value = null
      draft.value = null

      if (cause instanceof ConfigDocumentLoadError) {
        loadError.value = cause.message
        loadErrorCode.value = cause.code
        loadErrorDetails.value = cause.details
      } else {
        loadError.value = cause instanceof Error ? cause.message : String(cause)
        loadErrorCode.value = 'unknown_error'
      }
    } finally {
      loading.value = false
    }
  }

  async function save(): Promise<boolean> {
    if (draft.value === null) {
      return false
    }

    if (hasClientErrors.value) {
      saveError.value = 'client_errors'
      return false
    }

    saving.value = true
    saveError.value = null

    try {
      const result = await saveConfigDocument(draft.value)

      if (!result.ok) {
        serverErrors.value = result.details ?? []
        saveError.value = result.error ?? 'save_failed'
        return false
      }

      await load()
      return true
    } catch (cause) {
      saveError.value = cause instanceof Error ? cause.message : String(cause)
      return false
    } finally {
      saving.value = false
    }
  }

  function discard(): void {
    if (saved.value !== null) {
      draft.value = cloneConfig(saved.value)
    }

    clearAllTransientState()
  }

  function clearServerErrorForPath(pathKey: string): void {
    serverErrors.value = serverErrors.value.filter((error) => pathToKey(error.path) !== pathKey)
  }

  function clearFieldBuffer(pathKey: string): void {
    fieldBuffers.value = withoutKey(fieldBuffers.value, pathKey)
    clientErrors.value = withoutKey(clientErrors.value, pathKey)
  }

  function commitField(pathKey: string): void {
    clearFieldBuffer(pathKey)
    clearServerErrorForPath(pathKey)
  }

  function setFieldBuffer(pathKey: string, value: string, message: string): void {
    fieldBuffers.value = { ...fieldBuffers.value, [pathKey]: value }
    clientErrors.value = { ...clientErrors.value, [pathKey]: message }
    clearServerErrorForPath(pathKey)
  }

  function clearSectionState(section: ConfigSection): void {
    serverErrors.value = serverErrors.value.filter((error) => error.section !== section)
    clientErrors.value = withoutSection(clientErrors.value, section)
    fieldBuffers.value = withoutSection(fieldBuffers.value, section)
  }

  function updateWallpaperEnginePath(value: string): void {
    if (draft.value === null) {
      return
    }

    draft.value.wallpaper_engine_path = value
    commitField('wallpaper_engine_path')
  }

  function updateLanguage(value: string | null): void {
    if (draft.value === null) {
      return
    }

    draft.value.language = value
    commitField('language')
  }

  function updateSchedulingNumber(key: SchedulingNumberKey, value: number): void {
    if (draft.value === null) {
      return
    }

    draft.value.scheduling[key] = value
    commitField(`scheduling.${key}`)
  }

  function updatePauseOnFullscreen(value: boolean): void {
    if (draft.value === null) {
      return
    }

    draft.value.scheduling.pause_on_fullscreen = value
    commitField('scheduling.pause_on_fullscreen')
  }

  function restoreGeneralDefaults(): void {
    if (draft.value === null || defaults.value === null) {
      return
    }

    draft.value.wallpaper_engine_path = defaults.value.wallpaper_engine_path
    draft.value.language = defaults.value.language
    clearSectionState('general')
  }

  function restoreSchedulingDefaults(): void {
    if (draft.value === null || defaults.value === null) {
      return
    }

    draft.value.scheduling = cloneConfig(defaults.value.scheduling)
    clearSectionState('scheduling')
  }

  function fieldMessages(pathKey: string): string[] {
    return [
      ...(clientErrors.value[pathKey] ? [clientErrors.value[pathKey]] : []),
      ...(errorsByPath.value[pathKey]?.map((error) => error.message) ?? []),
    ]
  }

  function sectionMessages(section: ConfigSection): string[] {
    return errorsBySection.value[section].map((error) => error.message)
  }

  return {
    saved,
    defaults,
    draft,
    loading,
    saving,
    loadError,
    loadErrorCode,
    loadErrorDetails,
    saveError,
    serverErrors,
    clientErrors,
    fieldBuffers,
    errorsByPath,
    errorsBySection,
    globalErrors,
    isDirty,
    hasClientErrors,
    hasServerErrors,
    firstClientError,
    canSave,
    sectionKeys: SECTION_KEYS,
    load,
    save,
    discard,
    setFieldBuffer,
    clearFieldBuffer,
    clearSectionState,
    updateWallpaperEnginePath,
    updateLanguage,
    updateSchedulingNumber,
    updatePauseOnFullscreen,
    restoreGeneralDefaults,
    restoreSchedulingDefaults,
    fieldMessages,
    sectionMessages,
  }
})
