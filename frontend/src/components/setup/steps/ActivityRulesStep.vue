<script setup lang="ts">
import { TriangleAlertIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale } from "@/api/profile"
import ActivityListInput from "@/components/setup/ActivityListInput.vue"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field"
import { COPY } from "@/setup/copy"
import type { ProfileDraft } from "@/setup/model"

type Activity = ProfileDraft["activity"]

const props = defineProps<{
  locale: Locale
  activity: Activity
  conflicts: string[]
  errors: string[]
}>()

const emit = defineEmits<{ "update:activity": [value: Activity] }>()

const copy = computed(() => COPY[props.locale])
const groups = computed(() => [
  {
    id: "work",
    title: copy.value.activity.workTitle,
    processKey: "work_processes" as const,
    titleKey: "work_title_keywords" as const,
  },
  {
    id: "leisure",
    title: copy.value.activity.leisureTitle,
    processKey: "leisure_processes" as const,
    titleKey: "leisure_title_keywords" as const,
  },
])

function setList(field: keyof Activity, values: string[]): void {
  emit("update:activity", { ...props.activity, [field]: values })
}
</script>

<template>
  <section class="flex flex-col gap-6">
    <div class="max-w-2xl">
      <h1 class="text-2xl font-semibold tracking-tight">{{ copy.activity.title }}</h1>
      <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.activity.description }}</p>
    </div>

    <Alert v-if="conflicts.length" variant="destructive">
      <TriangleAlertIcon />
      <AlertTitle>{{ copy.activity.conflictTitle }}</AlertTitle>
      <AlertDescription>{{ copy.activity.conflictDescription(conflicts.join(", ")) }}</AlertDescription>
    </Alert>

    <Alert v-if="errors.length" variant="destructive">
      <TriangleAlertIcon />
      <AlertTitle>{{ copy.common.needsAttention }}</AlertTitle>
      <AlertDescription>{{ errors.join('; ') }}</AlertDescription>
    </Alert>

    <div class="grid gap-6 lg:grid-cols-2">
      <FieldSet v-for="group in groups" :key="group.id" class="rounded-xl border p-4">
        <FieldLegend>{{ group.title }}</FieldLegend>
        <FieldGroup>
          <Field>
            <FieldLabel :for="`${group.id}-processes`">{{ copy.activity.processLabel }}</FieldLabel>
            <ActivityListInput
              :id="`${group.id}-processes`"
              :model-value="activity[group.processKey]"
              :placeholder="copy.activity.processPlaceholder"
              :add-label="copy.activity.add"
              :remove-label="copy.common.remove"
              :empty-label="copy.activity.empty"
              @update:model-value="(values: string[]) => setList(group.processKey, values)"
            />
          </Field>
          <Field>
            <FieldLabel :for="`${group.id}-title-keywords`">{{ copy.activity.titleKeywordLabel }}</FieldLabel>
            <ActivityListInput
              :id="`${group.id}-title-keywords`"
              :model-value="activity[group.titleKey]"
              :placeholder="copy.activity.keywordPlaceholder"
              :add-label="copy.activity.add"
              :remove-label="copy.common.remove"
              :empty-label="copy.activity.empty"
              @update:model-value="(values: string[]) => setList(group.titleKey, values)"
            />
          </Field>
        </FieldGroup>
      </FieldSet>
    </div>
  </section>
</template>
