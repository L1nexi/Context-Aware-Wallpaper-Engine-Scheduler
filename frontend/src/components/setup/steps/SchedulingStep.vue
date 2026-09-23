<script setup lang="ts">
import { SlidersHorizontalIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale, ResponseStyle } from "@/api/profile"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { COPY, DISTURBANCE_LABELS, RESPONSE_STYLE_LABELS } from "@/setup/copy"
import { detectDisturbancePreset, DISTURBANCE_PRESETS, isNonNegativeInteger, parseNumberInput } from "@/setup/model"
import type { DisturbancePreset, ProfileDraft } from "@/setup/model"

type Matching = ProfileDraft["matching"]
type Disturbance = ProfileDraft["disturbance"]
type DisturbanceKey = keyof Disturbance

const props = defineProps<{
  locale: Locale
  matching: Matching
  disturbance: Disturbance
  timingOpen: boolean
  errors: Record<string, string[]>
}>()

const emit = defineEmits<{
  "update:matching": [value: Matching]
  "update:disturbance": [value: Disturbance]
  "update:timingOpen": [value: boolean]
}>()

const copy = computed(() => COPY[props.locale])
const preset = computed(() => detectDisturbancePreset({ disturbance: props.disturbance }))
const timingFields = computed(() => [
  ["startup_grace_seconds", copy.value.preferences.startupGrace, copy.value.preferences.seconds],
  ["idle_before_switch_seconds", copy.value.preferences.idleBeforeSwitch, copy.value.preferences.seconds],
  ["maximum_deferral_minutes", copy.value.preferences.maximumDeferral, copy.value.preferences.minutes],
  ["cycle_interval_minutes", copy.value.preferences.cycleInterval, copy.value.preferences.minutes],
] as const)

function messages(...fields: string[]): string[] {
  return fields.flatMap((field) => props.errors[field] ?? [])
}

function setResponseStyle(value: unknown): void {
  if (typeof value === "string" && value) {
    emit("update:matching", { response_style: value as ResponseStyle })
  }
}

function setPreset(value: unknown): void {
  if (typeof value !== "string" || !(value in DISTURBANCE_PRESETS)) return
  emit("update:disturbance", { ...DISTURBANCE_PRESETS[value as DisturbancePreset] })
}

function setTiming(field: DisturbanceKey, value: string | number): void {
  emit("update:disturbance", { ...props.disturbance, [field]: parseNumberInput(value) })
}
</script>

<template>
  <section class="flex flex-col gap-8">
    <div class="max-w-2xl">
      <h1 class="text-2xl font-semibold tracking-tight">{{ copy.preferences.title }}</h1>
      <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.preferences.description }}</p>
    </div>

    <FieldSet :data-invalid="messages('matching.response_style').length > 0">
      <FieldLegend>{{ copy.preferences.responseTitle }}</FieldLegend>
      <FieldDescription>{{ copy.preferences.responseDescription }}</FieldDescription>
      <ToggleGroup
        type="single"
        variant="outline"
        :spacing="2"
        class="w-full flex-wrap"
        :model-value="matching.response_style"
        @update:model-value="setResponseStyle"
      >
        <ToggleGroupItem
          v-for="style in (Object.keys(RESPONSE_STYLE_LABELS[locale]) as ResponseStyle[])"
          :key="style"
          :value="style"
          class="min-w-28 flex-1"
        >
          {{ RESPONSE_STYLE_LABELS[locale][style] }}
        </ToggleGroupItem>
      </ToggleGroup>
      <FieldError v-if="messages('matching.response_style').length" :errors="messages('matching.response_style')" />
    </FieldSet>

    <FieldSet>
      <FieldLegend>{{ copy.preferences.disturbanceTitle }}</FieldLegend>
      <FieldDescription>{{ copy.preferences.disturbanceDescription }}</FieldDescription>
      <ToggleGroup
        type="single"
        variant="outline"
        :spacing="2"
        class="w-full flex-wrap"
        :model-value="preset === 'custom' ? undefined : preset"
        @update:model-value="setPreset"
      >
        <ToggleGroupItem
          v-for="choice in (Object.keys(DISTURBANCE_PRESETS) as DisturbancePreset[])"
          :key="choice"
          :value="choice"
          class="min-w-24 flex-1"
        >
          {{ DISTURBANCE_LABELS[locale][choice] }}
        </ToggleGroupItem>
      </ToggleGroup>
      <Badge v-if="preset === 'custom'" variant="outline">{{ copy.common.custom }}</Badge>
    </FieldSet>

    <Collapsible :open="timingOpen" @update:open="(value: boolean) => emit('update:timingOpen', value)">
      <CollapsibleTrigger as-child>
        <Button variant="ghost">
          <SlidersHorizontalIcon data-icon="inline-start" />
          {{ copy.preferences.fineTune }}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent class="pt-4">
        <FieldGroup>
          <div class="grid gap-5 sm:grid-cols-2">
            <Field
              v-for="field in timingFields"
              :key="field[0]"
              :data-invalid="!isNonNegativeInteger(disturbance[field[0]]) || messages('disturbance', `disturbance.${field[0]}`).length > 0"
            >
              <FieldLabel :for="field[0]">{{ field[1] }}</FieldLabel>
              <InputGroup>
                <InputGroupInput
                  :id="field[0]"
                  :model-value="disturbance[field[0]] ?? ''"
                  type="number"
                  min="0"
                  step="1"
                  :aria-invalid="!isNonNegativeInteger(disturbance[field[0]]) || messages('disturbance', `disturbance.${field[0]}`).length > 0"
                  @update:model-value="(value: string | number) => setTiming(field[0], value)"
                />
                <InputGroupAddon align="inline-end">{{ field[2] }}</InputGroupAddon>
              </InputGroup>
              <FieldError v-if="!isNonNegativeInteger(disturbance[field[0]])" :errors="[copy.preferences.nonNegative]" />
              <FieldError
                v-if="messages('disturbance', `disturbance.${field[0]}`).length"
                :errors="messages('disturbance', `disturbance.${field[0]}`)"
              />
            </Field>
          </div>
        </FieldGroup>
      </CollapsibleContent>
    </Collapsible>
  </section>
</template>
