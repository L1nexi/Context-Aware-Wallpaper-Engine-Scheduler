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
  weight: number
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

export type ConfigSection = 'general' | 'scheduling' | 'playlists' | 'tags' | 'policies'
export type ConfigPath = Array<string | number>

export interface ConfigValidationScope {
  kind: 'policy' | 'playlist' | 'tag'
  key?: string
  index?: number
}

export interface ConfigValidationDetail {
  path: ConfigPath
  message: string
  code: string
  section: ConfigSection | null
  scope: ConfigValidationScope | null
}

export interface ConfigDocumentResponse {
  current: AppConfig
  defaults: AppConfig
}

export interface ConfigSaveResult {
  ok: boolean
  status?: number
  error?: string
  details?: ConfigValidationDetail[]
}

export interface WallpaperEnginePathResponse {
  path: string | null
  valid: boolean
}

export type ConfigLoadErrorCode =
  | 'config_not_found'
  | 'invalid_config'
  | 'http_error'
  | 'network_error'
  | 'unknown_error'

export class ConfigDocumentLoadError extends Error {
  code: ConfigLoadErrorCode
  details: string | null
  status: number | null

  constructor(
    message: string,
    options: { code: ConfigLoadErrorCode; details?: string; status?: number },
  ) {
    super(message)
    this.name = 'ConfigDocumentLoadError'
    this.code = options.code
    this.details = options.details ?? null
    this.status = options.status ?? null
  }
}

type ApiErrorPayload = {
  error?: string
  details?: unknown
}

async function readJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T
  } catch {
    return null
  }
}

function stringifyDetails(details: unknown): string | undefined {
  if (typeof details === 'string') {
    return details
  }

  if (details === null || details === undefined) {
    return undefined
  }

  return JSON.stringify(details)
}

export function cloneConfig<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function pathToKey(path: ConfigPath): string {
  return path.map(String).join('.')
}

export async function fetchConfigDocument(): Promise<ConfigDocumentResponse> {
  let response: Response

  try {
    response = await fetch('/api/config')
  } catch (cause) {
    throw new ConfigDocumentLoadError(cause instanceof Error ? cause.message : String(cause), {
      code: 'network_error',
    })
  }

  if (!response.ok) {
    const payload = await readJson<ApiErrorPayload>(response)
    const error = payload?.error ?? `HTTP ${response.status}`
    const code: ConfigLoadErrorCode =
      error === 'config_not_found' || error === 'invalid_config' ? error : 'http_error'

    throw new ConfigDocumentLoadError(error, {
      code,
      details: stringifyDetails(payload?.details),
      status: response.status,
    })
  }

  const document = await readJson<ConfigDocumentResponse>(response)
  if (document === null) {
    throw new ConfigDocumentLoadError('Invalid JSON response', { code: 'unknown_error' })
  }

  return document
}

export async function saveConfigDocument(config: AppConfig): Promise<ConfigSaveResult> {
  const response = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })

  const payload = await readJson<ApiErrorPayload>(response)

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      error: payload?.error ?? `HTTP ${response.status}`,
      details: Array.isArray(payload?.details)
        ? (payload.details as ConfigValidationDetail[])
        : undefined,
    }
  }

  return { ok: true, status: response.status }
}

export async function detectWallpaperEnginePath(): Promise<WallpaperEnginePathResponse> {
  const response = await fetch('/api/we-path')
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const result = await readJson<WallpaperEnginePathResponse>(response)
  if (result === null) {
    throw new Error('Invalid JSON response')
  }

  return result
}
