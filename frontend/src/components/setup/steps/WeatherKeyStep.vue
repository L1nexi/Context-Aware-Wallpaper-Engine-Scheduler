<script setup lang="ts">
import { CheckCircle2Icon, CloudSunIcon, ExternalLinkIcon, EyeIcon, EyeOffIcon, FlaskConicalIcon, TriangleAlertIcon } from "@lucide/vue"
import { computed, ref } from "vue"

import type { Locale } from "@/api/profile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import { Spinner } from "@/components/ui/spinner"
import { COPY } from "@/setup/copy"

const props = defineProps<{
  locale: Locale
  apiKey: string
  invalid: boolean
  errors: string[]
  validating: boolean
  validationStatus: "idle" | "success" | "error"
  validationError: string
}>()

const emit = defineEmits<{
  "update:apiKey": [value: string]
  openKeyPage: []
  validate: []
}>()

const copy = computed(() => COPY[props.locale])
const showApiKey = ref(false)
</script>

<template>
  <section class="flex flex-col gap-6">
    <div class="max-w-2xl">
      <h1 class="text-2xl font-semibold tracking-tight">{{ copy.weather.title }}</h1>
      <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.weather.description }}</p>
    </div>

    <FieldGroup>
      <Field :data-invalid="invalid || errors.length > 0">
        <FieldLabel for="weather-api-key">{{ copy.weather.keyLabel }}</FieldLabel>
        <InputGroup>
          <InputGroupInput
            id="weather-api-key"
            :model-value="apiKey"
            :type="showApiKey ? 'text' : 'password'"
            :placeholder="copy.weather.keyPlaceholder"
            autocomplete="off"
            :aria-invalid="invalid || errors.length > 0"
            @update:model-value="(value: string | number) => emit('update:apiKey', String(value))"
          />
          <InputGroupAddon align="inline-end">
            <InputGroupButton :aria-label="showApiKey ? copy.common.hide : copy.common.show" @click="showApiKey = !showApiKey">
              <EyeOffIcon v-if="showApiKey" />
              <EyeIcon v-else />
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
        <FieldDescription>{{ copy.weather.keyDescription }}</FieldDescription>
        <FieldError v-if="errors.length" :errors="errors" />
      </Field>
    </FieldGroup>

    <div class="flex flex-wrap gap-2">
      <Button :disabled="validating || !apiKey.trim()" @click="emit('validate')">
        <Spinner v-if="validating" data-icon="inline-start" />
        <FlaskConicalIcon v-else data-icon="inline-start" />
        {{ validating ? copy.weather.validating : copy.weather.validate }}
      </Button>
      <Button variant="outline" @click="emit('openKeyPage')">
        <ExternalLinkIcon data-icon="inline-start" />
        {{ copy.weather.getKey }}
      </Button>
    </div>

    <Alert v-if="validationStatus === 'success'">
      <CheckCircle2Icon />
      <AlertDescription>{{ copy.weather.validationSuccess }}</AlertDescription>
    </Alert>
    <Alert v-else-if="validationStatus === 'error'" variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription>{{ validationError }}</AlertDescription>
    </Alert>

    <div class="max-w-2xl rounded-lg border bg-muted/30 p-4">
      <h2 class="font-medium">{{ copy.weather.guideTitle }}</h2>
      <ol class="mt-3 space-y-4 text-sm leading-relaxed">
        <li v-for="(step, index) in copy.weather.guideSteps" :key="step.title" class="flex gap-3">
          <span class="flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-secondary-foreground">{{ index + 1 }}</span>
          <div class="min-w-0 space-y-1">
            <p class="font-medium">{{ step.title }}</p>
            <p class="text-muted-foreground">{{ step.action }}</p>
            <p class="text-muted-foreground">{{ step.expected }}</p>
            <p class="text-muted-foreground">{{ step.fallback }}</p>
          </div>
        </li>
      </ol>
    </div>

    <Alert>
      <CloudSunIcon />
      <AlertDescription>{{ copy.weather.validationOnSubmit }}</AlertDescription>
    </Alert>
  </section>
</template>
