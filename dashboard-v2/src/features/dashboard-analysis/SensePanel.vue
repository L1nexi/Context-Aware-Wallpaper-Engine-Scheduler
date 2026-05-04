<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '@/composables/useI18n'
import type { TickSnapshot } from '@/lib/dashboardAnalysis'

import { formatPercent, formatSeconds, formatTimestamp } from './formatting'

const props = defineProps<{
  tick: TickSnapshot
}>()

const { t, lang } = useI18n()

const weatherStatus = computed(() => {
  if (!props.tick.sense.weather.available) {
    return t('dashboard_weather_unavailable')
  }

  return props.tick.sense.weather.stale
    ? t('dashboard_weather_stale')
    : t('dashboard_weather_fresh')
})
</script>

<template>
  <section class="flex flex-col gap-4">
    <div>
      <p class="chrome-kicker">{{ t('dashboard_sense_title') }}</p>
      <h3 class="mt-2 text-xl font-semibold tracking-tight">
        {{ t('dashboard_sense_heading') }}
      </h3>
      <p class="mt-2 text-sm leading-6 text-muted-foreground">
        {{ t('dashboard_sense_body') }}
      </p>
    </div>

    <div class="grid gap-4">
      <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
        <p class="chrome-kicker">{{ t('activeWindow') }}</p>
        <h4 class="mt-2 text-base font-semibold tracking-tight">
          {{ tick.sense.window.title || t('dashboard_none') }}
        </h4>
        <p class="mt-2 text-sm text-muted-foreground data-mono">
          {{ tick.sense.window.process || t('dashboard_none') }}
        </p>
      </section>

      <div class="grid gap-4 sm:grid-cols-3">
        <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
          <p class="chrome-kicker">{{ t('idle') }}</p>
          <p class="mt-2 text-2xl font-semibold tracking-tight data-mono">
            {{ formatSeconds(tick.sense.idle.seconds, lang) }}s
          </p>
        </section>

        <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
          <p class="chrome-kicker">{{ t('cpu') }}</p>
          <p class="mt-2 text-2xl font-semibold tracking-tight data-mono">
            {{ formatPercent(tick.sense.cpu.averagePercent, lang) }}%
          </p>
        </section>

        <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
          <p class="chrome-kicker">{{ t('fullscreen') }}</p>
          <p class="mt-2 text-2xl font-semibold tracking-tight data-mono">
            {{ tick.sense.fullscreen ? t('dashboard_yes') : t('dashboard_no') }}
          </p>
        </section>
      </div>

      <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="chrome-kicker">{{ t('policy_weather') }}</p>
            <h4 class="mt-2 text-base font-semibold tracking-tight">
              {{ weatherStatus }}
            </h4>
          </div>

          <span class="text-xs text-muted-foreground data-mono">
            {{ tick.sense.weather.main ?? t('dashboard_none') }}
          </span>
        </div>

        <dl class="mt-4 grid gap-3 sm:grid-cols-2">
          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_weather_id') }}</dt>
            <dd class="mt-1 font-medium data-mono">
              {{
                tick.sense.weather.id === null
                  ? t('dashboard_none')
                  : String(tick.sense.weather.id)
              }}
            </dd>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_weather_main') }}</dt>
            <dd class="mt-1 font-medium data-mono">
              {{ tick.sense.weather.main ?? t('dashboard_none') }}
            </dd>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_weather_sunrise') }}</dt>
            <dd class="mt-1 font-medium data-mono">
              {{ formatTimestamp(tick.sense.weather.sunrise, lang, { timeStyle: 'short' }) }}
            </dd>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_weather_sunset') }}</dt>
            <dd class="mt-1 font-medium data-mono">
              {{ formatTimestamp(tick.sense.weather.sunset, lang, { timeStyle: 'short' }) }}
            </dd>
          </div>
        </dl>
      </section>

      <section class="rounded-2xl border border-border/70 bg-background/70 p-4 shadow-sm">
        <p class="chrome-kicker">{{ t('dashboard_clock_title') }}</p>
        <dl class="mt-4 grid gap-3 sm:grid-cols-3">
          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_clock_local') }}</dt>
            <dd class="mt-1 font-medium data-mono">
              {{ formatTimestamp(tick.sense.clock.localTs, lang, { timeStyle: 'medium' }) }}
            </dd>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_clock_hour') }}</dt>
            <dd class="mt-1 font-medium data-mono">{{ tick.sense.clock.hour }}</dd>
          </div>

          <div class="rounded-2xl border border-border/70 bg-muted/35 px-3 py-3">
            <dt class="text-xs text-muted-foreground">{{ t('dashboard_clock_day_of_year') }}</dt>
            <dd class="mt-1 font-medium data-mono">{{ tick.sense.clock.dayOfYear }}</dd>
          </div>
        </dl>
      </section>
    </div>
  </section>
</template>
