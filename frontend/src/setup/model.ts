import type { Locale, Profile, ResponseStyle, SceneId } from "@/api/profile"

export interface ProfileDraft {
  version: 1
  setup_complete: true
  wallpaper_engine_path: string
  language: Locale | null
  weather: {
    api_key: string
    location: {
      name: string
      latitude: number | null
      longitude: number | null
    }
  }
  scenes: Partial<Record<SceneId, string>>
  matching: {
    response_style: ResponseStyle
  }
  disturbance: {
    startup_grace_seconds: number | null
    idle_before_switch_seconds: number | null
    maximum_deferral_minutes: number | null
    cycle_interval_minutes: number | null
  }
  activity: {
    work_processes: string[]
    leisure_processes: string[]
    work_title_keywords: string[]
    leisure_title_keywords: string[]
  }
}

export const DISTURBANCE_PRESETS = {
  eager: {
    startup_grace_seconds: 5,
    idle_before_switch_seconds: 10,
    maximum_deferral_minutes: 30,
    cycle_interval_minutes: 5,
  },
  responsive: {
    startup_grace_seconds: 15,
    idle_before_switch_seconds: 15,
    maximum_deferral_minutes: 45,
    cycle_interval_minutes: 10,
  },
  balanced: {
    startup_grace_seconds: 15,
    idle_before_switch_seconds: 20,
    maximum_deferral_minutes: 60,
    cycle_interval_minutes: 15,
  },
  quiet: {
    startup_grace_seconds: 30,
    idle_before_switch_seconds: 60,
    maximum_deferral_minutes: 180,
    cycle_interval_minutes: 30,
  },
  minimal: {
    startup_grace_seconds: 60,
    idle_before_switch_seconds: 120,
    maximum_deferral_minutes: 300,
    cycle_interval_minutes: 60,
  },
} as const

export type DisturbancePreset = keyof typeof DISTURBANCE_PRESETS

export function parseNumberInput(value: string | number): number | null {
  if (value === "") return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function isNonNegativeInteger(value: number | null): value is number {
  return value !== null && Number.isInteger(value) && value >= 0
}

export function validationIssueField(path: Array<string | number>): string {
  const root = typeof path[0] === "string" ? path[0] : "profile"
  if (root === "activity" || root === "scenes") return root
  if (root === "weather" && path[1] === "location") {
    return typeof path[2] === "string" ? `weather.location.${path[2]}` : "weather.location"
  }
  if (["weather", "disturbance", "matching"].includes(root) && typeof path[1] === "string") {
    return `${root}.${path[1]}`
  }
  return root
}

function requireNonNegativeInteger(value: number | null): number {
  if (!isNonNegativeInteger(value)) throw new Error("non_negative_integer_required")
  return value
}

export function createProfileDraft(profile: Profile | null, locale: Locale): ProfileDraft {
  if (profile !== null) {
    return {
      version: 1,
      setup_complete: true,
      wallpaper_engine_path: profile.wallpaper_engine_path,
      language: profile.language,
      weather: {
        api_key: profile.weather.api_key,
        location: { ...profile.weather.location },
      },
      scenes: { ...profile.scenes },
      matching: { ...profile.matching },
      disturbance: { ...profile.disturbance },
      activity: {
        work_processes: [...profile.activity.work_processes],
        leisure_processes: [...profile.activity.leisure_processes],
        work_title_keywords: [...profile.activity.work_title_keywords],
        leisure_title_keywords: [...profile.activity.leisure_title_keywords],
      },
    }
  }

  return {
    version: 1,
    setup_complete: true,
    wallpaper_engine_path: "",
    language: locale,
    weather: {
      api_key: "",
      location: {
        name: "",
        latitude: null,
        longitude: null,
      },
    },
    scenes: {},
    matching: {
      response_style: "balanced",
    },
    disturbance: { ...DISTURBANCE_PRESETS.balanced },
    activity: {
      work_processes: [],
      leisure_processes: [],
      work_title_keywords: [],
      leisure_title_keywords: [],
    },
  }
}

export function buildProfile(draft: ProfileDraft): Profile {
  const latitude = draft.weather.location.latitude
  const longitude = draft.weather.location.longitude
  if (latitude === null || longitude === null) {
    throw new Error("location_coordinates_required")
  }

  return {
    version: 1,
    setup_complete: true,
    wallpaper_engine_path: draft.wallpaper_engine_path,
    language: draft.language,
    weather: {
      api_key: draft.weather.api_key,
      location: {
        name: draft.weather.location.name,
        latitude,
        longitude,
      },
    },
    scenes: { ...draft.scenes },
    matching: { ...draft.matching },
    disturbance: {
      startup_grace_seconds: requireNonNegativeInteger(draft.disturbance.startup_grace_seconds),
      idle_before_switch_seconds: requireNonNegativeInteger(draft.disturbance.idle_before_switch_seconds),
      maximum_deferral_minutes: requireNonNegativeInteger(draft.disturbance.maximum_deferral_minutes),
      cycle_interval_minutes: requireNonNegativeInteger(draft.disturbance.cycle_interval_minutes),
    },
    activity: {
      work_processes: [...draft.activity.work_processes],
      leisure_processes: [...draft.activity.leisure_processes],
      work_title_keywords: [...draft.activity.work_title_keywords],
      leisure_title_keywords: [...draft.activity.leisure_title_keywords],
    },
  }
}

export function detectDisturbancePreset(draft: Pick<ProfileDraft, "disturbance">): DisturbancePreset | "custom" {
  const match = Object.entries(DISTURBANCE_PRESETS).find(([, values]) =>
    Object.entries(values).every(
      ([key, value]) => draft.disturbance[key as keyof ProfileDraft["disturbance"]] === value,
    ),
  )
  return (match?.[0] as DisturbancePreset | undefined) ?? "custom"
}

function normalizeProcess(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\.exe$/i, "")
}

function normalizeTitle(value: string): string {
  return value.trim().toLocaleLowerCase()
}

export function activityConflicts(draft: ProfileDraft): string[] {
  const workProcesses = new Set(draft.activity.work_processes.map(normalizeProcess))
  const leisureProcesses = new Set(draft.activity.leisure_processes.map(normalizeProcess))
  const workTitles = new Set(draft.activity.work_title_keywords.map(normalizeTitle))
  const leisureTitles = new Set(draft.activity.leisure_title_keywords.map(normalizeTitle))

  return [
    ...[...workProcesses].filter((value) => leisureProcesses.has(value)),
    ...[...workTitles].filter((value) => leisureTitles.has(value)),
  ].filter(Boolean)
}

export function profileFingerprint(draft: ProfileDraft): string {
  return JSON.stringify(draft)
}
