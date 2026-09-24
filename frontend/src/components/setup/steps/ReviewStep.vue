<script setup lang="ts">
import { GaugeIcon, TriangleAlertIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale } from "@/api/profile"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { COPY, DISTURBANCE_LABELS, RESPONSE_STYLE_LABELS } from "@/setup/copy"
import type { StepId } from "@/setup/flow"
import { detectDisturbancePreset } from "@/setup/model"
import type { ProfileDraft } from "@/setup/model"

const props = defineProps<{
  locale: Locale
  draft: ProfileDraft
  valid: boolean
  missingSteps: Array<{ id: StepId, title: string }>
  weatherStatus: "idle" | "success" | "error"
  weatherError: string
  validatingWeather: boolean
}>()

const emit = defineEmits<{
  validateWeather: []
  openStep: [id: StepId]
}>()

const copy = computed(() => COPY[props.locale])
const preset = computed(() => detectDisturbancePreset(props.draft))
const locationSummary = computed(() => {
  const location = props.draft.weather.location
  if (location.latitude === null || location.longitude === null) return copy.value.common.notSet
  return copy.value.review.coordinates(location.latitude, location.longitude)
})
const weatherSummary = computed(() => {
  if (props.weatherStatus === "success") return copy.value.review.weatherPassed
  if (props.weatherStatus === "error") return copy.value.review.weatherFailed
  return copy.value.review.weatherUntested
})
const rows = computed(() => [
  { id: "wallpaper", label: copy.value.review.wallpaper, value: props.draft.wallpaper_engine_path || copy.value.common.notSet },
  { id: "weather", label: copy.value.review.weather, value: weatherSummary.value },
  { id: "location", label: copy.value.review.location, value: locationSummary.value },
  { id: "scenes", label: copy.value.review.scenes, value: copy.value.review.sceneCount(Object.keys(props.draft.scenes).length) },
  { id: "response", label: copy.value.review.response, value: RESPONSE_STYLE_LABELS[props.locale][props.draft.matching.response_style] },
  { id: "disturbance", label: copy.value.review.disturbance, value: preset.value === "custom" ? copy.value.common.custom : DISTURBANCE_LABELS[props.locale][preset.value] },
  { id: "activity", label: copy.value.review.activity, value: copy.value.review.activityCount(
    props.draft.activity.work_title_keywords.length + props.draft.activity.leisure_title_keywords.length,
    props.draft.activity.work_processes.length + props.draft.activity.leisure_processes.length,
  ) },
])
</script>

<template>
  <section class="flex flex-col gap-6">
    <dl class="rounded-xl border">
      <div
        v-for="row in rows"
        :key="row.id"
        class="grid min-w-0 gap-1 border-b px-4 py-3 last:border-b-0 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4"
      >
        <dt class="text-sm text-muted-foreground">{{ row.label }}</dt>
        <dd class="min-w-0">
          <div v-if="row.id === 'weather'" class="flex min-w-0 flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-sm font-medium" role="status">{{ row.value }}</p>
              <p v-if="weatherError" class="mt-1 text-sm" :class="weatherStatus === 'error' ? 'text-destructive' : 'text-muted-foreground'">{{ weatherError }}</p>
              <p v-if="copy.review.weatherNote" class="mt-1 text-xs text-muted-foreground">{{ copy.review.weatherNote }}</p>
            </div>
            <Button size="sm" variant="outline" :disabled="validatingWeather || !draft.weather.api_key.trim()" @click="emit('validateWeather')">
              <Spinner v-if="validatingWeather" data-icon="inline-start" />
              <GaugeIcon v-else data-icon="inline-start" />
              {{ validatingWeather ? copy.weather.validating : copy.weather.validate }}
            </Button>
          </div>
          <span v-else class="text-sm font-medium [overflow-wrap:anywhere]">{{ row.value }}</span>
        </dd>
      </div>
    </dl>

    <Alert v-if="!valid" variant="destructive">
      <TriangleAlertIcon />
      <AlertTitle>{{ copy.review.missingTitle }}</AlertTitle>
      <AlertDescription class="flex flex-col gap-3">
        <span>{{ copy.review.missingDescription }}</span>
        <span class="flex flex-wrap gap-2">
          <Button v-for="step in missingSteps" :key="step.id" size="sm" variant="outline" @click="emit('openStep', step.id)">{{ step.title }}</Button>
        </span>
      </AlertDescription>
    </Alert>
  </section>
</template>
