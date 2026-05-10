<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '@/composables/useI18n'
import type { TagWeight } from '@/lib/dashboardAnalysis'

import { formatWeight } from './formatting'

const props = withDefaults(
  defineProps<{
    title: string
    items: TagWeight[]
    limit?: number
  }>(),
  {
    limit: 6,
  },
)

const { t, lang } = useI18n()

const visibleItems = computed(() => props.items.slice(0, props.limit))
const hiddenItems = computed(() => props.items.slice(props.limit))
</script>

<template>
  <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="chrome-kicker">{{ title }}</p>
        <p class="mt-2 text-sm text-muted-foreground">
          {{ t('dashboard_vector_summary', { count: items.length }) }}
        </p>
      </div>

      <p class="text-xs text-muted-foreground data-mono">
        {{ t('dashboard_top_n', { count: visibleItems.length }) }}
      </p>
    </div>

    <div v-if="items.length > 0" class="mt-4 flex flex-wrap gap-2">
      <span
        v-for="item in visibleItems"
        :key="`${title}-${item.tag}`"
        class="inline-flex items-center gap-2 rounded-full border border-border/80 bg-muted/70 px-3 py-1.5 text-xs text-foreground"
      >
        <span class="font-medium data-mono">{{ item.tag }}</span>
        <span class="text-muted-foreground data-mono">
          {{ formatWeight(item.weight, lang) }}
        </span>
      </span>
    </div>

    <p v-else class="mt-4 text-sm text-muted-foreground">
      {{ t('dashboard_none') }}
    </p>

    <details
      v-if="hiddenItems.length > 0"
      class="mt-4 rounded-2xl border border-border/70 bg-muted/40 px-4 py-3"
    >
      <summary class="cursor-pointer list-none text-sm font-medium text-foreground">
        {{ t('dashboard_more_items', { count: hiddenItems.length }) }}
      </summary>
      <div class="mt-3 flex flex-wrap gap-2">
        <span
          v-for="item in hiddenItems"
          :key="`${title}-extra-${item.tag}`"
          class="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/80 px-3 py-1.5 text-xs text-foreground"
        >
          <span class="font-medium data-mono">{{ item.tag }}</span>
          <span class="text-muted-foreground data-mono">
            {{ formatWeight(item.weight, lang) }}
          </span>
        </span>
      </div>
    </details>
  </section>
</template>
