import type {
  ActionDecision,
  ActionReasonCode,
  ControllerBlocker,
  ControllerEvaluation,
  PlaylistRef,
  PolicyDiagnostic,
  PolicyId,
  TopMatch,
  TickSnapshot,
} from '@/lib/dashboardAnalysis'

import { formatPercent, formatSeconds } from './formatting'

type Translate = (key: string, params?: Record<string, string | number>) => string

export interface SummaryField {
  label: string
  value: string
}

function formatPlaylistRef(
  playlist: PlaylistRef | null | undefined,
  t: Translate,
): string {
  return playlist?.display ?? playlist?.name ?? t('dashboard_none')
}

export function getTopMatchName(match: TopMatch, t: Translate): string {
  return formatPlaylistRef(match.playlist, t)
}

export function getTickPlaylistLabel(
  tick: TickSnapshot,
  type: 'active' | 'matched',
  t: Translate,
): string {
  return formatPlaylistRef(
    type === 'active' ? tick.summary.activePlaylist : tick.summary.matchedPlaylist,
    t,
  )
}

export function getPolicyTitle(policyId: PolicyId, t: Translate): string {
  return t(`policy_${policyId}`)
}

export function getPolicySummary(
  policy: PolicyDiagnostic,
  t: Translate,
): string {
  switch (policy.policyId) {
    case 'activity':
      if (policy.details.matchedTag && policy.details.matchedRule) {
        return t('dashboard_policy_summary_activity_match', {
          source: policy.details.matchSource,
          rule: policy.details.matchedRule,
          tag: policy.details.matchedTag,
        })
      }
      return t('dashboard_policy_summary_activity_none')
    case 'time':
      return t('dashboard_policy_summary_time', {
        hour: policy.details.virtualHour,
        tag: policy.dominantTag ?? t('dashboard_none'),
      })
    case 'season':
      return t('dashboard_policy_summary_season', {
        dayOfYear: policy.details.dayOfYear,
        tag: policy.dominantTag ?? t('dashboard_none'),
      })
    case 'weather':
      if (!policy.details.available) {
        return t('dashboard_policy_summary_weather_unavailable')
      }
      if (policy.details.mapped && policy.dominantTag) {
        return t('dashboard_policy_summary_weather_match', {
          weather: policy.details.weatherMain ?? t('dashboard_none'),
          tag: policy.dominantTag,
        })
      }
      return t('dashboard_policy_summary_weather_unmapped', {
        weather: policy.details.weatherMain ?? t('dashboard_none'),
      })
  }
}

export function getDefaultExpandedPolicyIds(policies: PolicyDiagnostic[]): Set<PolicyId> {
  if (policies.length === 0) {
    return new Set<PolicyId>()
  }

  const sorted = getPoliciesSortedByMagnitude(policies)

  return new Set(sorted.slice(0, 1).map((policy) => policy.policyId))
}

export function getPoliciesSortedByMagnitude(
  policies: PolicyDiagnostic[],
): PolicyDiagnostic[] {
  return [...policies].sort((left, right) => {
    return right.effectiveMagnitude - left.effectiveMagnitude
  })
}

export function getActionReasonLabel(reasonCode: ActionReasonCode, t: Translate): string {
  return t(`dashboard_reason_${reasonCode}`)
}

function getPrimaryBlocker(evaluation: ControllerEvaluation): ControllerBlocker | null {
  return evaluation.blockedBy[0] ?? null
}

export function getControllerSummary(
  evaluation: ControllerEvaluation | null,
  decision: ActionDecision,
  t: Translate,
): string {
  if (evaluation === null) {
    return decision.kind === 'pause'
      ? t('dashboard_controller_summary_paused')
      : t('dashboard_controller_summary_no_evaluation')
  }

  if (evaluation.allowed) {
    return t('dashboard_controller_summary_allowed', {
      operation: t(`dashboard_operation_${evaluation.operation}`),
    })
  }

  const blocker = getPrimaryBlocker(evaluation)
  if (blocker === null) {
    return t('dashboard_controller_summary_blocked_generic')
  }

  return t(`dashboard_controller_summary_blocked_${blocker}`)
}

export function getRelevantControllerFacts(
  evaluation: ControllerEvaluation | null,
  decision: ActionDecision,
  locale: string,
  t: Translate,
): SummaryField[] {
  if (evaluation === null) {
    return [
      {
        label: t('dashboard_action_reason'),
        value: getActionReasonLabel(decision.reasonCode, t),
      },
    ]
  }

  const fields: SummaryField[] = [
    {
      label: t('dashboard_controller_operation'),
      value: t(`dashboard_operation_${evaluation.operation}`),
    },
    {
      label: t('dashboard_controller_status'),
      value: evaluation.allowed ? t('dashboard_allowed') : t('dashboard_blocked'),
    },
  ]

  if (evaluation.blockedBy.length > 0) {
    fields.push({
      label: t('dashboard_controller_blockers'),
      value: evaluation.blockedBy
        .map((blocker) => t(`dashboard_blocker_${blocker}`))
        .join(', '),
    })
  }

  for (const blocker of evaluation.blockedBy) {
    switch (blocker) {
      case 'cooldown':
        fields.push({
          label: t('dashboard_controller_cooldown_remaining'),
          value: `${formatSeconds(evaluation.cooldownRemaining, locale)}s`,
        })
        break
      case 'idle':
        fields.push({
          label: t('dashboard_controller_idle_window'),
          value: `${formatSeconds(evaluation.idleSeconds, locale)}s / ${formatSeconds(evaluation.idleThreshold, locale)}s`,
        })
        break
      case 'cpu':
        fields.push({
          label: t('dashboard_controller_cpu_window'),
          value: `${formatPercent(evaluation.cpuPercent, locale)}% / ${evaluation.cpuThreshold === null ? t('dashboard_none') : `${formatPercent(evaluation.cpuThreshold, locale)}%`}`,
        })
        break
      case 'fullscreen':
        fields.push({
          label: t('dashboard_controller_fullscreen_state'),
          value: evaluation.fullscreen ? t('dashboard_yes') : t('dashboard_no'),
        })
        break
    }
  }

  if (evaluation.allowed && evaluation.forceAfterRemaining !== null) {
    fields.push({
      label: t('dashboard_controller_force_after_remaining'),
      value: `${formatSeconds(evaluation.forceAfterRemaining, locale)}s`,
    })
  }

  return fields
}

export function getDecisionSummary(
  decision: ActionDecision,
  tick: TickSnapshot,
  t: Translate,
): string {
  const activeBefore = formatPlaylistRef(decision.activePlaylistBefore, t)
  const activeAfter = formatPlaylistRef(decision.activePlaylistAfter, t)

  switch (decision.kind) {
    case 'switch':
      return t('dashboard_decision_switch', {
        from: activeBefore,
        to: activeAfter,
      })
    case 'cycle':
      return t('dashboard_decision_cycle', {
        playlist: activeAfter,
      })
    case 'pause':
      return t('dashboard_decision_pause')
    case 'hold':
      return t('dashboard_decision_hold', {
        playlist: activeAfter,
      })
    case 'none':
      return t('dashboard_decision_none')
    default:
      return activeAfter
  }
}
