export type DiagnosticAction = 'none' | 'switch' | 'cycle' | 'hold' | 'pause'

export type DiagnosticBlocker = 'cooldown' | 'fullscreen' | 'cpu' | 'idle'
export type DiagnosticPolicyId = 'activity' | 'time' | 'season' | 'weather'

export interface DiagnosticTagWeight {
  tag: string
  weight: number
}

export interface DiagnosticResolvedTagWeight {
  resolvedTag: string
  weight: number
}

export interface DiagnosticPlaylistRef {
  name: string
  display: string
  color: string | null
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

export interface DiagnosticControllerSnapshot {
  evaluation: DiagnosticBlockerEvaluation | null
}

export interface DiagnosticDecisionSnapshot {
  action: DiagnosticAction
  executed: boolean
  activePlaylists: DiagnosticPlaylistRef[]
  targetPlaylists: DiagnosticPlaylistRef[]
  matchedPlaylists: DiagnosticPlaylistRef[]
  targetPlaylist: DiagnosticPlaylistRef | null
}

export interface DiagnosticTopMatch {
  playlist: DiagnosticPlaylistRef
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

export interface DiagnosticThinkSnapshot {
  rawContextVector: DiagnosticTagWeight[]
  resolvedContextVector: DiagnosticTagWeight[]
  fallbackExpansions: Record<string, DiagnosticResolvedTagWeight[]>
  policies: DiagnosticPolicyEvaluation[]
  controller: DiagnosticControllerSnapshot
  decision: DiagnosticDecisionSnapshot
}

export interface DiagnosticActSnapshot {
  topMatches: DiagnosticTopMatch[]
}

export interface DiagnosticTickSummary {
  tickId: number
  ts: number
  similarity: number
  similarityGap: number
  activePlaylists: DiagnosticPlaylistRef[]
  matchedPlaylists: DiagnosticPlaylistRef[]
  action: DiagnosticAction
  paused: boolean
  executed: boolean
  hasEvent: boolean
}

export interface DiagnosticTickSnapshot {
  summary: DiagnosticTickSummary
  sense: DiagnosticSenseSnapshot
  think: DiagnosticThinkSnapshot
  act: DiagnosticActSnapshot
}

export interface DiagnosticWindowResponse {
  liveTickId: number | null
  ticks: DiagnosticTickSnapshot[]
}
