import type { PlaylistScanResult } from "@/api/profile"
import { activityConflicts, isNonNegativeInteger } from "./model.ts"
import type { ProfileDraft } from "./model.ts"

export const STEP_ORDER = [
  "wallpaper",
  "weather",
  "location",
  "scenes",
  "scheduling",
  "activity",
  "review",
] as const

export type StepId = (typeof STEP_ORDER)[number]
export type EditableStepId = Exclude<StepId, "review">

export interface StepEvaluation {
  validity: Record<EditableStepId, boolean>
  conflicts: string[]
}

export function stepForIssue(path: Array<string | number>): StepId {
  const root = path[0]
  if (root === "wallpaper_engine_path") return "wallpaper"
  if (root === "weather") return path[1] === "location" ? "location" : "weather"
  if (root === "scenes") return "scenes"
  if (root === "matching" || root === "disturbance") return "scheduling"
  if (root === "activity") return "activity"
  return "review"
}

export function evaluateSteps(
  draft: ProfileDraft,
  wallpaperReady: boolean,
  playlists: PlaylistScanResult["playlists"],
): StepEvaluation {
  const location = draft.weather.location
  const locationValid =
    location.name.trim().length > 0 &&
    location.latitude !== null &&
    Number.isFinite(location.latitude) &&
    location.latitude >= -90 &&
    location.latitude <= 90 &&
    location.longitude !== null &&
    Number.isFinite(location.longitude) &&
    location.longitude >= -180 &&
    location.longitude <= 180

  const available = new Set(playlists.map((playlist) => playlist.name))
  const assignments = Object.values(draft.scenes)
  const scenesValid =
    assignments.length > 0 && assignments.every((playlist) => Boolean(playlist && available.has(playlist)))
  const conflicts = activityConflicts(draft)

  return {
    validity: {
      wallpaper: wallpaperReady,
      weather: draft.weather.api_key.trim().length > 0,
      location: locationValid,
      scenes: scenesValid,
      scheduling:
        Object.values(draft.disturbance).every(isNonNegativeInteger) &&
        Boolean(draft.matching.response_style),
      activity: conflicts.length === 0,
    },
    conflicts,
  }
}
