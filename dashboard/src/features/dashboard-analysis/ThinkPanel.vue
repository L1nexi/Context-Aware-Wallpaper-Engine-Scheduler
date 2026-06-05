<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '@/composables/useI18n'
import type { TickSnapshot } from '@/lib/dashboardAnalysis'

import FallbackSummary from './FallbackSummary.vue'
import PolicyEvaluationCard from './PolicyEvaluationCard.vue'
import VectorList from './VectorList.vue'
import { getDefaultExpandedPolicyIds, getPoliciesSortedByMagnitude } from './presenters'

const props = defineProps<{
  tick: TickSnapshot
}>()

const { t } = useI18n()
const sortedPolicies = computed(() => getPoliciesSortedByMagnitude(props.tick.think.policies))
const expandedPolicyIds = computed(() => getDefaultExpandedPolicyIds(sortedPolicies.value))

const hasFallbacks = computed(() => Object.keys(props.tick.think.fallbackExpansions).length > 0)
</script>

<template>
  <section class="flex flex-col gap-4">
    <div>
      <h3 class="text-xl font-semibold tracking-tight">
        {{ t('dashboard_think_heading') }}
      </h3>
    </div>

    <div class="grid gap-4">
      <VectorList
        :title="t('dashboard_vector_resolved')"
        :items="tick.think.resolvedContextVector"
        :limit="5"
      />

      <details class="rounded-2xl border border-border/70 bg-muted/35 px-4 py-4">
        <summary class="cursor-pointer list-none text-sm font-medium text-foreground">
          {{ t('dashboard_expand_details') }}
        </summary>

        <div class="mt-4 grid gap-4">
          <VectorList
            :title="t('dashboard_vector_raw')"
            :items="tick.think.rawContextVector"
            :limit="tick.think.rawContextVector.length"
          />

          <FallbackSummary v-if="hasFallbacks" :expansions="tick.think.fallbackExpansions" />
        </div>
      </details>

      <div class="space-y-4">
        <PolicyEvaluationCard
          v-for="policy in sortedPolicies"
          :key="policy.policyId"
          :policy="policy"
          :default-open="expandedPolicyIds.has(policy.policyId)"
        />
      </div>
    </div>
  </section>
</template>
