<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '@/composables/useI18n'
import type { ResolvedTagWeight } from '@/lib/dashboardAnalysis'

import { formatWeight } from './formatting'

const props = defineProps<{
  expansions: Record<string, ResolvedTagWeight[]>
}>()

const { t, lang } = useI18n()

const entries = computed(() => Object.entries(props.expansions))
</script>

<template>
  <details
    class="rounded-2xl border border-border/70 bg-background/70 px-4 py-4 shadow-sm"
  >
    <summary class="cursor-pointer list-none">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="chrome-kicker">{{ t('dashboard_fallbacks_title') }}</p>
          <h4 class="mt-2 text-base font-semibold tracking-tight">
            {{ t('dashboard_fallbacks_summary', { count: entries.length }) }}
          </h4>
        </div>

        <p class="text-xs text-muted-foreground data-mono">
          {{ t('dashboard_expand_details') }}
        </p>
      </div>
    </summary>

    <div class="mt-4 space-y-4">
      <section
        v-for="[sourceTag, targets] in entries"
        :key="sourceTag"
        class="rounded-2xl border border-border/70 bg-muted/35 p-4"
      >
        <div class="flex items-center justify-between gap-3">
          <p class="font-medium data-mono">{{ sourceTag }}</p>
          <p class="text-xs text-muted-foreground data-mono">
            {{ t('dashboard_top_n', { count: targets.length }) }}
          </p>
        </div>

        <div class="mt-3 flex flex-wrap gap-2">
          <span
            v-for="target in targets"
            :key="`${sourceTag}-${target.resolvedTag}`"
            class="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/80 px-3 py-1.5 text-xs text-foreground"
          >
            <span class="font-medium data-mono">{{ target.resolvedTag }}</span>
            <span class="text-muted-foreground data-mono">
              {{ formatWeight(target.weight, lang) }}
            </span>
          </span>
        </div>
      </section>
    </div>
  </details>
</template>
