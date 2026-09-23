<script setup lang="ts">
import { TriangleAlertIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale } from "@/api/profile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { COPY, DISTURBANCE_LABELS, RESPONSE_STYLE_LABELS } from "@/setup/copy"
import { detectDisturbancePreset } from "@/setup/model"
import type { ProfileDraft } from "@/setup/model"

const props = defineProps<{
  locale: Locale
  draft: ProfileDraft
  valid: boolean
}>()

const copy = computed(() => COPY[props.locale])
const preset = computed(() => detectDisturbancePreset(props.draft))
const activityRuleCount = computed(() =>
  props.draft.activity.work_processes.length +
  props.draft.activity.leisure_processes.length +
  props.draft.activity.work_title_keywords.length +
  props.draft.activity.leisure_title_keywords.length,
)
const rows = computed(() => [
  [copy.value.review.wallpaper, props.draft.wallpaper_engine_path || copy.value.common.notSet],
  [copy.value.review.weather, props.draft.weather.api_key ? copy.value.review.apiKeySet : copy.value.common.notSet],
  [copy.value.review.location, props.draft.weather.location.name || copy.value.common.notSet],
  [copy.value.review.scenes, copy.value.review.sceneCount(Object.keys(props.draft.scenes).length)],
  [copy.value.review.response, RESPONSE_STYLE_LABELS[props.locale][props.draft.matching.response_style]],
  [copy.value.review.disturbance, preset.value === "custom" ? copy.value.common.custom : DISTURBANCE_LABELS[props.locale][preset.value]],
  [copy.value.review.activity, copy.value.review.activityCount(activityRuleCount.value)],
])
</script>

<template>
  <section class="flex flex-col gap-6">
    <div class="max-w-2xl">
      <h1 class="text-2xl font-semibold tracking-tight">{{ copy.review.title }}</h1>
      <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.review.description }}</p>
    </div>

    <div class="rounded-xl border">
      <div
        v-for="row in rows"
        :key="row[0]"
        class="grid min-w-0 gap-1 border-b px-4 py-3 last:border-b-0 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4"
      >
        <span class="text-sm text-muted-foreground">{{ row[0] }}</span>
        <span class="min-w-0 text-sm font-medium [overflow-wrap:anywhere]">{{ row[1] }}</span>
      </div>
    </div>

    <Alert v-if="!valid" variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription>{{ copy.errors.validation }}</AlertDescription>
    </Alert>
  </section>
</template>
