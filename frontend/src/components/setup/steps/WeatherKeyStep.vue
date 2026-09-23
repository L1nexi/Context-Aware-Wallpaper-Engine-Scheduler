<script setup lang="ts">
import { CloudSunIcon, ExternalLinkIcon, EyeIcon, EyeOffIcon } from "@lucide/vue"
import { computed, ref } from "vue"

import type { Locale } from "@/api/profile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import { COPY } from "@/setup/copy"

const props = defineProps<{
  locale: Locale
  apiKey: string
  invalid: boolean
  errors: string[]
}>()

const emit = defineEmits<{
  "update:apiKey": [value: string]
  openKeyPage: []
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
      <Button variant="outline" @click="emit('openKeyPage')">
        <ExternalLinkIcon data-icon="inline-start" />
        {{ copy.weather.getKey }}
      </Button>
    </div>

    <Alert>
      <CloudSunIcon />
      <AlertDescription>{{ copy.weather.validationOnSubmit }}</AlertDescription>
    </Alert>
  </section>
</template>
