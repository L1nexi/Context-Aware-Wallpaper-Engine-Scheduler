<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '@/composables/useI18n'
import type { PolicyDiagnostic } from '@/lib/dashboardAnalysis'

import { formatWeight } from './formatting'
import { getPolicySummary, getPolicyTitle } from './presenters'
import VectorList from './VectorList.vue'

const props = defineProps<{
  policy: PolicyDiagnostic
  defaultOpen: boolean
}>()

const { t, lang } = useI18n()

const policyTitle = computed(() => getPolicyTitle(props.policy.policyId, t))
const policySummary = computed(() => getPolicySummary(props.policy, t))
const rawContributionPreview = computed(() => props.policy.rawContribution.slice(0, 3))
const policyDetailPairs = computed(() => {
  switch (props.policy.policyId) {
    case 'activity':
      return [
        {
          label: t('dashboard_policy_detail_match_source'),
          value: props.policy.details.matchSource,
        },
        {
          label: t('dashboard_policy_detail_matched_rule'),
          value: props.policy.details.matchedRule ?? t('dashboard_none'),
        },
        {
          label: t('dashboard_policy_detail_matched_tag'),
          value: props.policy.details.matchedTag ?? t('dashboard_none'),
        },
        {
          label: t('dashboard_policy_detail_ema_active'),
          value: props.policy.details.emaActive ? t('dashboard_yes') : t('dashboard_no'),
        },
      ]
    case 'time':
      return [
        {
          label: t('time_auto'),
          value: props.policy.details.auto ? t('dashboard_yes') : t('dashboard_no'),
        },
        {
          label: t('dashboard_policy_detail_hour'),
          value: String(props.policy.details.hour),
        },
        {
          label: t('dashboard_policy_detail_virtual_hour'),
          value: String(props.policy.details.virtualHour),
        },
        {
          label: t('time_day_start'),
          value: String(props.policy.details.dayStartHour),
        },
        {
          label: t('time_night_start'),
          value: String(props.policy.details.nightStartHour),
        },
      ]
    case 'season':
      return [
        {
          label: t('dashboard_clock_day_of_year'),
          value: String(props.policy.details.dayOfYear),
        },
      ]
    case 'weather':
      return [
        {
          label: t('dashboard_weather_available'),
          value: props.policy.details.available ? t('dashboard_yes') : t('dashboard_no'),
        },
        {
          label: t('dashboard_weather_mapped'),
          value: props.policy.details.mapped ? t('dashboard_yes') : t('dashboard_no'),
        },
        {
          label: t('dashboard_weather_main'),
          value: props.policy.details.weatherMain ?? t('dashboard_none'),
        },
        {
          label: t('dashboard_weather_id'),
          value:
            props.policy.details.weatherId === null
              ? t('dashboard_none')
              : String(props.policy.details.weatherId),
        },
      ]
    default:
      return []
  }
})

const peakPairs = computed(() => {
  if (props.policy.policyId === 'time') {
    return Object.entries(props.policy.details.peaks)
  }

  if (props.policy.policyId === 'season') {
    return Object.entries(props.policy.details.peaks)
  }

  return []
})
</script>

<template>
  <details
    :open="defaultOpen"
    class="rounded-2xl border border-border/70 bg-background/70 shadow-sm"
  >
    <summary class="cursor-pointer list-none px-4 py-4">
      <div class="flex flex-col gap-3">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <p class="chrome-kicker">{{ policyTitle }}</p>
              <span
                class="inline-flex items-center rounded-full border border-border/70 bg-muted/70 px-2 py-1 text-[11px] font-medium text-muted-foreground"
              >
                {{ policy.enabled ? t('dashboard_enabled') : t('dashboard_disabled') }}
              </span>
              <span
                class="inline-flex items-center rounded-full border border-border/70 bg-muted/70 px-2 py-1 text-[11px] font-medium text-muted-foreground"
              >
                {{ policy.active ? t('dashboard_policy_active') : t('dashboard_policy_inactive') }}
              </span>
            </div>
            <h4 class="mt-2 text-base font-semibold tracking-tight">
              {{ policySummary }}
            </h4>
          </div>

          <div class="text-right">
            <p class="text-xs text-muted-foreground">{{ t('magnitude') }}</p>
            <p class="mt-1 text-lg font-semibold tracking-tight data-mono">
              {{ formatWeight(policy.effectiveMagnitude, lang) }}
            </p>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-3">
          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <p class="text-xs text-muted-foreground">{{ t('topTags') }}</p>
            <p class="mt-1 font-medium data-mono">
              {{ policy.dominantTag ?? t('dashboard_none') }}
            </p>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <p class="text-xs text-muted-foreground">{{ t('policy_weight_scale') }}</p>
            <p class="mt-1 font-medium data-mono">
              {{ formatWeight(policy.weight, lang) }}
            </p>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <p class="text-xs text-muted-foreground">{{ t('dashboard_salience_intensity') }}</p>
            <p class="mt-1 font-medium data-mono">
              {{ formatWeight(policy.salience, lang) }} / {{ formatWeight(policy.intensity, lang) }}
            </p>
          </div>
        </div>

        <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
          <div class="flex items-center justify-between gap-3">
            <p class="text-xs text-muted-foreground">
              {{ t('dashboard_policy_raw_contribution') }}
            </p>
            <span class="text-xs text-muted-foreground data-mono">
              {{ t('dashboard_top_n', { count: rawContributionPreview.length }) }}
            </span>
          </div>

          <div v-if="rawContributionPreview.length > 0" class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="item in rawContributionPreview"
              :key="`${policy.policyId}-raw-${item.tag}`"
              class="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/80 px-3 py-1.5 text-xs text-foreground"
            >
              <span class="font-medium data-mono">{{ item.tag }}</span>
              <span class="text-muted-foreground data-mono">
                {{ formatWeight(item.weight, lang) }}
              </span>
            </span>
          </div>

          <p v-else class="mt-3 text-sm text-muted-foreground">
            {{ t('dashboard_none') }}
          </p>
        </div>
      </div>
    </summary>

    <div class="space-y-4 border-t border-border/70 px-4 py-4">
      <div class="grid gap-4 xl:grid-cols-1">
        <VectorList :title="t('dashboard_policy_direction')" :items="policy.direction" :limit="5" />
      </div>

      <section class="rounded-2xl border border-border/70 bg-muted/35 p-4">
        <p class="chrome-kicker">{{ t('dashboard_policy_details') }}</p>

        <dl class="mt-4 grid gap-3 sm:grid-cols-2">
          <div
            v-for="pair in policyDetailPairs"
            :key="`${policy.policyId}-${pair.label}`"
            class="rounded-2xl border border-border/70 bg-background/70 px-3 py-3"
          >
            <dt class="text-xs text-muted-foreground">{{ pair.label }}</dt>
            <dd class="mt-1 font-medium data-mono">{{ pair.value }}</dd>
          </div>
        </dl>

        <div
          v-if="peakPairs.length > 0"
          class="mt-4 rounded-2xl border border-border/70 bg-background/70 p-4"
        >
          <p class="text-xs text-muted-foreground">{{ t('dashboard_policy_peaks') }}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="[name, value] in peakPairs"
              :key="`${policy.policyId}-peak-${name}`"
              class="inline-flex items-center gap-2 rounded-full border border-border/80 bg-muted/70 px-3 py-1.5 text-xs text-foreground"
            >
              <span class="font-medium data-mono">{{ name }}</span>
              <span class="text-muted-foreground data-mono">
                {{ formatWeight(Number(value), lang) }}
              </span>
            </span>
          </div>
        </div>
      </section>
    </div>
  </details>
</template>
