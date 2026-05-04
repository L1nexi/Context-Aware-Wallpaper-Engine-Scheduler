<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '@/composables/useI18n'
import type { TickSnapshot } from '@/lib/dashboardAnalysis'

import { getPlaylistColor } from './playlistColors'
import ControllerSummary from './ControllerSummary.vue'
import { formatWeight } from './formatting'
import {
  getActionReasonLabel,
  getDecisionSummary,
  getTickPlaylistLabel,
  getTopMatchName,
} from './presenters'

const props = defineProps<{
  tick: TickSnapshot
}>()

const { t, lang } = useI18n()

const topMatches = computed(() => props.tick.act.topMatches.slice(0, 5))
const decisionSummary = computed(() => getDecisionSummary(props.tick.act.decision, props.tick, t))
const matchedPlaylistLabel = computed(() => getTickPlaylistLabel(props.tick, 'matched', t))
</script>

<template>
  <section class="flex flex-col gap-4">
    <div>
      <p class="chrome-kicker">{{ t('dashboard_act_title') }}</p>
      <h3 class="mt-2 text-xl font-semibold tracking-tight">
        {{ t('dashboard_act_heading') }}
      </h3>
      <p class="mt-2 text-sm leading-6 text-muted-foreground">
        {{ t('dashboard_act_body') }}
      </p>
    </div>

    <div class="grid gap-4">
      <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
        <div class="flex items-center justify-between gap-4">
          <div>
            <p class="chrome-kicker">{{ t('dashboard_top_matches_title') }}</p>
            <h4 class="mt-2 text-base font-semibold tracking-tight">
              {{ t('dashboard_top_matches_heading') }}
            </h4>
          </div>

          <span class="text-xs text-muted-foreground data-mono">Top 5</span>
        </div>

        <div v-if="topMatches.length > 0" class="mt-4 space-y-3">
          <div
            v-for="match in topMatches"
            :key="match.playlist"
            class="flex items-center justify-between gap-4 rounded-2xl border border-border/70 bg-muted/35 px-3 py-3"
          >
            <div class="flex min-w-0 items-center gap-3">
              <span
                class="size-3 rounded-full border border-background/70"
                :style="{ backgroundColor: getPlaylistColor(match.playlist) }"
              />
              <span class="truncate font-medium">
                {{ getTopMatchName(match, t) }}
              </span>
            </div>

            <span class="text-sm text-muted-foreground data-mono">
              {{ formatWeight(match.score, lang) }}
            </span>
          </div>
        </div>

        <p v-else class="mt-4 text-sm text-muted-foreground">
          {{ t('dashboard_none') }}
        </p>
      </section>

      <ControllerSummary
        :evaluation="tick.act.controller.evaluation"
        :decision="tick.act.decision"
      />

      <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="chrome-kicker">{{ t('dashboard_action_title') }}</p>
            <h4 class="mt-2 text-base font-semibold tracking-tight">
              {{ decisionSummary }}
            </h4>
          </div>

          <span
            class="inline-flex items-center rounded-full border border-border/70 bg-muted/70 px-3 py-1 text-xs font-medium text-muted-foreground"
          >
            {{ tick.act.decision.executed ? t('dashboard_executed') : t('dashboard_not_executed') }}
          </span>
        </div>

        <dl class="mt-4 grid gap-3 sm:grid-cols-2">
          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_action_reason') }}</dt>
            <dd class="mt-1 font-medium">
              {{ getActionReasonLabel(tick.act.decision.reasonCode, t) }}
            </dd>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_matched_playlist') }}</dt>
            <dd class="mt-1 font-medium">
              {{ matchedPlaylistLabel }}
            </dd>
          </div>
        </dl>

        <details class="mt-4 rounded-2xl border border-border/70 bg-muted/35 px-4 py-3">
          <summary class="cursor-pointer list-none text-sm font-medium text-foreground">
            {{ t('dashboard_expand_details') }}
          </summary>
          <dl class="mt-3 grid gap-3 sm:grid-cols-2">
            <div class="rounded-2xl border border-border/70 bg-background/70 px-3 py-3">
              <dt class="text-xs text-muted-foreground">{{ t('dashboard_active_before') }}</dt>
              <dd class="mt-1 font-medium data-mono">
                {{ tick.act.decision.activePlaylistBefore ?? t('dashboard_none') }}
              </dd>
            </div>

            <div class="rounded-2xl border border-border/70 bg-background/70 px-3 py-3">
              <dt class="text-xs text-muted-foreground">{{ t('dashboard_active_after') }}</dt>
              <dd class="mt-1 font-medium data-mono">
                {{ tick.act.decision.activePlaylistAfter ?? t('dashboard_none') }}
              </dd>
            </div>
          </dl>
        </details>
      </section>
    </div>
  </section>
</template>
