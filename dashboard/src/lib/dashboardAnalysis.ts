export const DASHBOARD_ANALYSIS_WINDOW_COUNT = 900
export const DASHBOARD_ANALYSIS_POLL_INTERVAL_MS = 1000

export type ActionKind = 'none' | 'switch' | 'cycle' | 'hold' | 'pause'

export type ActionReasonCode =
  | 'no_match'
  | 'hold_same_playlist'
  | 'switch_allowed'
  | 'switch_blocked_cooldown'
  | 'switch_blocked_fullscreen'
  | 'switch_blocked_cpu'
  | 'switch_blocked_not_idle'
  | 'cycle_allowed'
  | 'cycle_blocked_cooldown'
  | 'cycle_blocked_fullscreen'
  | 'cycle_blocked_cpu'
  | 'cycle_blocked_not_idle'
  | 'scheduler_paused'
  | 'manual_apply_requested'

export type ControllerBlocker = 'cooldown' | 'fullscreen' | 'cpu' | 'idle'
export type ControllerOperation = 'switch' | 'cycle'
export type PolicyId = 'activity' | 'time' | 'season' | 'weather'

export interface TagWeight {
  tag: string
  weight: number
}

export interface ResolvedTagWeight {
  resolvedTag: string
  weight: number
}

export interface WindowSnapshot {
  process: string
  title: string
}

export interface IdleSnapshot {
  seconds: number
}

export interface CpuSnapshot {
  averagePercent: number
}

export interface WeatherSnapshot {
  available: boolean
  stale: boolean
  id: number | null
  main: string | null
  sunrise: number | null
  sunset: number | null
}

export interface ClockSnapshot {
  localTs: number
  hour: number
  dayOfYear: number
}

export interface ActivityPolicyDetails {
  matchSource: 'title' | 'process' | 'none'
  matchedRule: string | null
  matchedTag: string | null
  windowTitle: string
  process: string
  emaActive: boolean
}

export interface TimePolicyDetails {
  auto: boolean
  hour: number
  virtualHour: number
  dayStartHour: number
  nightStartHour: number
  peaks: Record<string, number>
}

export interface SeasonPolicyDetails {
  dayOfYear: number
  peaks: Record<string, number>
}

export interface WeatherPolicyDetails {
  weatherId: number | null
  weatherMain: string | null
  available: boolean
  mapped: boolean
}

export interface BasePolicyDiagnostic {
  policyId: PolicyId
  enabled: boolean
  active: boolean
  weight: number
  salience: number
  intensity: number
  effectiveMagnitude: number
  direction: TagWeight[]
  rawContribution: TagWeight[]
  resolvedContribution: TagWeight[]
  dominantTag: string | null
}

export interface ActivityPolicyDiagnostic extends BasePolicyDiagnostic {
  policyId: 'activity'
  details: ActivityPolicyDetails
}

export interface TimePolicyDiagnostic extends BasePolicyDiagnostic {
  policyId: 'time'
  details: TimePolicyDetails
}

export interface SeasonPolicyDiagnostic extends BasePolicyDiagnostic {
  policyId: 'season'
  details: SeasonPolicyDetails
}

export interface WeatherPolicyDiagnostic extends BasePolicyDiagnostic {
  policyId: 'weather'
  details: WeatherPolicyDetails
}

export type PolicyDiagnostic =
  | ActivityPolicyDiagnostic
  | TimePolicyDiagnostic
  | SeasonPolicyDiagnostic
  | WeatherPolicyDiagnostic

export interface ControllerEvaluation {
  operation: ControllerOperation
  allowed: boolean
  blockedBy: ControllerBlocker[]
  cooldownRemaining: number
  idleSeconds: number
  idleThreshold: number
  cpuPercent: number
  cpuThreshold: number | null
  fullscreen: boolean
  forceAfterRemaining: number | null
}

export interface ControllerDiagnostic {
  evaluation: ControllerEvaluation | null
}

export interface PlaylistRef {
  name: string
  display: string
  color: string
}

export interface ActionDecision {
  kind: ActionKind
  reasonCode: ActionReasonCode
  executed: boolean
  activePlaylistBefore: PlaylistRef | null
  activePlaylistAfter: PlaylistRef | null
  matchedPlaylist: PlaylistRef | null
}

export interface TopMatch {
  playlist: PlaylistRef
  score: number
}

export interface SenseSnapshot {
  window: WindowSnapshot
  idle: IdleSnapshot
  cpu: CpuSnapshot
  fullscreen: boolean
  weather: WeatherSnapshot
  clock: ClockSnapshot
}

export interface ThinkSnapshot {
  rawContextVector: TagWeight[]
  resolvedContextVector: TagWeight[]
  fallbackExpansions: Record<string, ResolvedTagWeight[]>
  policies: PolicyDiagnostic[]
}

export interface ActSnapshot {
  topMatches: TopMatch[]
  controller: ControllerDiagnostic
  decision: ActionDecision
}

export interface TickSummary {
  tickId: number
  ts: number
  similarity: number
  similarityGap: number
  activePlaylist: PlaylistRef | null
  matchedPlaylist: PlaylistRef | null
  actionKind: ActionKind
  reasonCode: ActionReasonCode
  paused: boolean
  executed: boolean
  hasEvent: boolean
}

export interface TickSnapshot {
  summary: TickSummary
  sense: SenseSnapshot
  think: ThinkSnapshot
  act: ActSnapshot
}

export interface TickWindowResponse {
  liveTickId: number | null
  ticks: TickSnapshot[]
}

function resolveApiUrl(path: string): string {
  const baseUrl = import.meta.env.VITE_DASHBOARD_API_BASE_URL?.trim()
  if (!baseUrl) {
    return path
  }

  const normalizedBaseUrl = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
  return new URL(path, normalizedBaseUrl).toString()
}

export async function fetchDashboardAnalysisWindow(
  signal?: AbortSignal,
): Promise<TickWindowResponse> {
  const response = await fetch(
    resolveApiUrl(`/api/analysis/window?count=${DASHBOARD_ANALYSIS_WINDOW_COUNT}`),
    {
      headers: {
        Accept: 'application/json',
      },
      signal,
    },
  )

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  return (await response.json()) as TickWindowResponse
}
