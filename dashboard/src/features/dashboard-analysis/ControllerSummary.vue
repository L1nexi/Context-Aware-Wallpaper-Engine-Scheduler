<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '@/composables/useI18n'
import type { ActionDecision, ControllerEvaluation } from '@/lib/dashboardAnalysis'

import { getActionReasonLabel, getControllerSummary, getRelevantControllerFacts } from './presenters'

const props = defineProps<{
  evaluation: ControllerEvaluation | null
  decision: ActionDecision
}>()

const { t, lang } = useI18n()

const summary = computed(() => getControllerSummary(props.evaluation, props.decision, t))
const relevantFacts = computed(() =>
  getRelevantControllerFacts(props.evaluation, props.decision, lang.value, t),
)
const rawFacts = computed(() => {
  if (props.evaluation === null) {
    return []
  }

  return [
    {
      label: t('dashboard_controller_cooldown_remaining'),
      value: String(props.evaluation.cooldownRemaining),
    },
    {
      label: t('dashboard_controller_idle_seconds'),
      value: String(props.evaluation.idleSeconds),
    },
    {
      label: t('dashboard_controller_idle_threshold'),
      value: String(props.evaluation.idleThreshold),
    },
    {
      label: t('dashboard_controller_cpu_percent'),
      value: String(props.evaluation.cpuPercent),
    },
    {
      label: t('dashboard_controller_cpu_threshold'),
      value:
        props.evaluation.cpuThreshold === null
          ? t('dashboard_none')
          : String(props.evaluation.cpuThreshold),
    },
    {
      label: t('dashboard_controller_force_after_remaining'),
      value:
        props.evaluation.forceAfterRemaining === null
          ? t('dashboard_none')
          : String(props.evaluation.forceAfterRemaining),
    },
  ]
})
</script>

<template>
  <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="chrome-kicker">{{ t('dashboard_controller_title') }}</p>
        <h4 class="mt-2 text-base font-semibold tracking-tight">
          {{ summary }}
        </h4>
      </div>

      <span
        class="inline-flex items-center rounded-full border border-border/70 bg-muted/70 px-3 py-1 text-xs font-medium text-muted-foreground"
      >
        {{ getActionReasonLabel(decision.reasonCode, t) }}
      </span>
    </div>

    <dl class="mt-4 grid gap-3">
      <div
        v-for="fact in relevantFacts"
        :key="fact.label"
        class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3"
      >
        <dt class="text-xs text-muted-foreground">{{ fact.label }}</dt>
        <dd class="mt-1 font-medium data-mono">{{ fact.value }}</dd>
      </div>
    </dl>

    <details
      v-if="rawFacts.length > 0"
      class="mt-4 rounded-2xl border border-border/70 bg-muted/35 px-4 py-3"
    >
      <summary class="cursor-pointer list-none text-sm font-medium text-foreground">
        {{ t('dashboard_expand_details') }}
      </summary>
      <dl class="mt-3 grid gap-3 sm:grid-cols-2">
        <div
          v-for="fact in rawFacts"
          :key="`raw-${fact.label}`"
          class="rounded-2xl border border-border/70 bg-background/70 px-3 py-3"
        >
          <dt class="text-xs text-muted-foreground">{{ fact.label }}</dt>
          <dd class="mt-1 font-medium data-mono">{{ fact.value }}</dd>
        </div>
      </dl>
    </details>
  </section>
</template>
