export type SceneId =
  | "day_work"
  | "day_leisure"
  | "night_work"
  | "night_leisure"
  | "spring"
  | "summer"
  | "autumn"
  | "winter"
  | "sunset"
  | "rain"

export type Locale = "zh" | "en"

export type ResponseStyle =
  | "background"
  | "background_leaning"
  | "balanced"
  | "current_leaning"
  | "current"

export interface WeatherLocationProfile {
  name: string
  latitude: number
  longitude: number
}

export interface Profile {
  version: 1
  setup_complete: true
  wallpaper_engine_path: string
  language: Locale | null
  weather: {
    api_key: string
    location: WeatherLocationProfile
  }
  scenes: Partial<Record<SceneId, string>>
  matching: {
    response_style: ResponseStyle
  }
  disturbance: {
    startup_grace_seconds: number
    idle_before_switch_seconds: number
    maximum_deferral_minutes: number
    cycle_interval_minutes: number
  }
  activity: {
    work_processes: string[]
    leisure_processes: string[]
    work_title_keywords: string[]
    leisure_title_keywords: string[]
  }
}

export interface SceneCatalogItem {
  id: SceneId
}

export interface PlaylistScanResult {
  wallpaper_engine_path: string
  playlists: Array<{
    name: string
    item_count: number
  }>
}

export interface DetectedLocation {
  name: string
  latitude: number
  longitude: number
}

export interface ValidationIssue {
  path: Array<string | number>
  code: string
  message: string
}

export interface ApiErrorPayload {
  error: string
  issues?: ValidationIssue[]
  stage?: "compile" | "prepare" | "persist"
  detail?: string
  reason?: string
  http_status?: number
}

export class ApiError extends Error {
  readonly status: number
  readonly payload: ApiErrorPayload

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.detail || payload.error)
    this.name = "ApiError"
    this.status = status
    this.payload = payload
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const payload = (await response.json()) as T | ApiErrorPayload
  if (!response.ok) {
    throw new ApiError(response.status, payload as ApiErrorPayload)
  }
  return payload as T
}

function jsonRequest(body: object, method: "POST" | "PUT" = "POST"): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }
}

export async function getProfile(): Promise<Profile | null> {
  try {
    const response = await requestJson<{ profile: Profile }>("/api/profile")
    return response.profile
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.payload.error === "profile_not_found") {
      return null
    }
    throw error
  }
}

export async function getSceneCatalog(): Promise<SceneCatalogItem[]> {
  const response = await requestJson<{ scenes: SceneCatalogItem[] }>("/api/scenes")
  return response.scenes
}

export async function detectLocation(): Promise<DetectedLocation> {
  const response = await requestJson<{ location: DetectedLocation }>("/api/location-estimates", { method: "POST" })
  return response.location
}

export async function validateWeatherKey(apiKey: string): Promise<void> {
  await requestJson<{ status: "valid" }>("/api/weather-key-validations", jsonRequest({ api_key: apiKey }))
}

export function scanPlaylists(wallpaperEnginePath: string): Promise<PlaylistScanResult> {
  return requestJson(
    "/api/wallpaper-engine/playlist-scans",
    jsonRequest({ wallpaper_engine_path: wallpaperEnginePath }),
  )
}

export async function createInitialProfile(profile: Profile): Promise<Profile> {
  const response = await requestJson<{ status: "created"; profile: Profile }>(
    "/api/profile",
    jsonRequest(profile),
  )
  return response.profile
}

export async function applyProfile(profile: Profile): Promise<Profile> {
  const response = await requestJson<{ status: "applied"; profile: Profile }>(
    "/api/profile",
    jsonRequest(profile, "PUT"),
  )
  return response.profile
}
