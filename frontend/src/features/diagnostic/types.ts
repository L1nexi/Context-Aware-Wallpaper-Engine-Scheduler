export type DiagnosticAction = 'none' | 'switch' | 'cycle' | 'hold' | 'pause'
export type DiagnosticDecisionMode = 'normal' | 'manual' | 'recovery' | 'pause'

export type DiagnosticBlocker = 'cooldown' | 'fullscreen' | 'cpu' | 'idle'
export type DiagnosticPolicyId = 'activity' | 'time' | 'season' | 'weather'

export interface DiagnosticPlaylistCatalogItem {
  name: string
  display: string
  color: string | null
  itemCount: number
}

export interface DiagnosticCatalog {
  playlists: DiagnosticPlaylistCatalogItem[]
}

export interface DiagnosticTagWeight {
  tag: string
  weight: number
}

export interface DiagnosticResolvedTagWeight {
  resolvedTag: string
  weight: number
}

export interface DiagnosticWindowSnapshot {
  process: string
  title: string
}

export interface DiagnosticIdleSnapshot {
  seconds: number
}

export interface DiagnosticCpuSnapshot {
  averagePercent: number
}

export interface DiagnosticWeatherSnapshot {
  available: boolean
  stale: boolean
  id: number | null
  main: string | null
  sunrise: number | null
  sunset: number | null
}

export interface DiagnosticClockSnapshot {
  localTs: number
  hour: number
  dayOfYear: number
}

export interface DiagnosticActivityDetails {
  matchSource: 'title' | 'process' | 'none'
  matchedRule: string | null
  matchedTag: string | null
  windowTitle: string
  process: string
  emaActive: boolean
}

export interface DiagnosticTimeDetails {
  auto: boolean
  hour: number
  virtualHour: number
  dayStartHour: number
  nightStartHour: number
  peaks: Record<string, number>
}

export interface DiagnosticSeasonDetails {
  dayOfYear: number
  peaks: Record<string, number>
}

export interface DiagnosticWeatherDetails {
  weatherId: number | null
  weatherMain: string | null
  available: boolean
  mapped: boolean
}

export interface DiagnosticBasePolicyEvaluation {
  policyId: DiagnosticPolicyId
  enabled: boolean
  active: boolean
  weight: number
  salience: number
  intensity: number
  effectiveMagnitude: number
  direction: DiagnosticTagWeight[]
  rawContribution: DiagnosticTagWeight[]
  resolvedContribution: DiagnosticTagWeight[]
  dominantTag: string | null
}

export interface DiagnosticActivityEvaluation extends DiagnosticBasePolicyEvaluation {
  policyId: 'activity'
  details: DiagnosticActivityDetails
}

export interface DiagnosticTimeEvaluation extends DiagnosticBasePolicyEvaluation {
  policyId: 'time'
  details: DiagnosticTimeDetails
}

export interface DiagnosticSeasonEvaluation extends DiagnosticBasePolicyEvaluation {
  policyId: 'season'
  details: DiagnosticSeasonDetails
}

export interface DiagnosticWeatherEvaluation extends DiagnosticBasePolicyEvaluation {
  policyId: 'weather'
  details: DiagnosticWeatherDetails
}

export type DiagnosticPolicyEvaluation =
  | DiagnosticActivityEvaluation
  | DiagnosticTimeEvaluation
  | DiagnosticSeasonEvaluation
  | DiagnosticWeatherEvaluation

export interface DiagnosticBlockerEvaluation {
  allowed: boolean
  blockedBy: DiagnosticBlocker[]
  cooldownRemaining: number
  idleSeconds: number
  idleThreshold: number
  cpuPercent: number
  cpuThreshold: number | null
  fullscreen: boolean
  forceAfterRemaining: number | null
}

export interface DiagnosticTopMatch {
  playlist: string
  score: number
}

export interface DiagnosticSenseSnapshot {
  window: DiagnosticWindowSnapshot
  idle: DiagnosticIdleSnapshot
  cpu: DiagnosticCpuSnapshot
  fullscreen: boolean
  weather: DiagnosticWeatherSnapshot
  clock: DiagnosticClockSnapshot
}

export interface DiagnosticMatchSnapshot {
  bestPlaylists: string[]
  topMatches: DiagnosticTopMatch[]
  rawContextVector: DiagnosticTagWeight[]
  resolvedContextVector: DiagnosticTagWeight[]
  fallbackExpansions: Record<string, DiagnosticResolvedTagWeight[]>
  policies: DiagnosticPolicyEvaluation[]
  maxPolicyMagnitude: number
  similarity: number
  similarityGap: number
}

export interface DiagnosticPlanSnapshot {
  mode: DiagnosticDecisionMode
  activePlaylists: string[]
}

export interface DiagnosticDecideSnapshot {
  action: DiagnosticAction
  targetPlaylists: string[]
  semanticContinuity: boolean
  evaluation: DiagnosticBlockerEvaluation | null
}

export interface DiagnosticActSnapshot {
  targetPlaylist: string | null
  executed: boolean
}

export interface DiagnosticTickSummary {
  tickId: number
  ts: number
  pauseUntil: number
  similarity: number
  similarityGap: number
  activePlaylists: string[]
  matchedPlaylists: string[]
  action: DiagnosticAction
  paused: boolean
  executed: boolean
  hasEvent: boolean
}

export interface DiagnosticTickSnapshot {
  summary: DiagnosticTickSummary
  sense: DiagnosticSenseSnapshot
  match: DiagnosticMatchSnapshot
  plan: DiagnosticPlanSnapshot
  decide: DiagnosticDecideSnapshot
  act: DiagnosticActSnapshot
}

export interface DiagnosticWindowResponse {
  liveTickId: number | null
  catalog: DiagnosticCatalog
  ticks: DiagnosticTickSnapshot[]
}
