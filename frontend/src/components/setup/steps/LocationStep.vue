<script setup lang="ts">
import { MapPinIcon, MapPinSearchIcon, TriangleAlertIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale } from "@/api/profile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { COPY } from "@/setup/copy"
import type { ProfileDraft } from "@/setup/model"

type Location = ProfileDraft["weather"]["location"]
type Coordinate = "latitude" | "longitude"

const props = defineProps<{
  locale: Locale
  location: Location
  locating: boolean
  detectionStatus: "idle" | "success" | "error"
  detectionError: string
  detectionCity: string | null
  attempted: boolean
  errors: Record<string, string[]>
}>()

const emit = defineEmits<{
  "update:location": [value: Location]
  detect: []
}>()

const copy = computed(() => COPY[props.locale])
const latitudeInvalid = computed(() =>
  props.location.latitude === null || !Number.isFinite(props.location.latitude) ||
  props.location.latitude < -90 || props.location.latitude > 90,
)
const longitudeInvalid = computed(() =>
  props.location.longitude === null || !Number.isFinite(props.location.longitude) ||
  props.location.longitude < -180 || props.location.longitude > 180,
)

function messages(...fields: string[]): string[] {
  return fields.flatMap((field) => props.errors[field] ?? [])
}

function setCoordinate(field: Coordinate, value: string | number): void {
  const parsed = value === "" ? null : Number(value)
  emit("update:location", {
    ...props.location,
    [field]: parsed !== null && Number.isFinite(parsed) ? parsed : null,
  })
}
</script>

<template>
  <section class="flex flex-col gap-6">
    <div class="flex flex-col items-start gap-2">
      <Button variant="outline" :disabled="locating" @click="emit('detect')">
        <Spinner v-if="locating" data-icon="inline-start" />
        <MapPinSearchIcon v-else data-icon="inline-start" />
        {{ locating ? copy.location.detecting : copy.location.detect }}
      </Button>
      <p class="text-sm text-muted-foreground">{{ copy.location.detectHint }}</p>
    </div>

    <Alert v-if="detectionStatus === 'success'">
      <MapPinIcon />
      <AlertDescription>{{ copy.location.detected(detectionCity) }}</AlertDescription>
    </Alert>
    <Alert v-else-if="detectionStatus === 'error'" variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription>{{ detectionError }} {{ copy.location.detectionUnavailable }}</AlertDescription>
    </Alert>

    <FieldGroup>
      <div class="grid gap-5 sm:grid-cols-2">
        <Field :data-invalid="(attempted && latitudeInvalid) || messages('weather.location', 'weather.location.latitude').length > 0">
          <FieldLabel for="latitude">{{ copy.location.latitudeLabel }}</FieldLabel>
          <Input
            id="latitude"
            :model-value="location.latitude ?? ''"
            type="number"
            min="-90"
            max="90"
            step="0.0001"
            :placeholder="copy.location.latitudePlaceholder"
            :aria-invalid="(attempted && latitudeInvalid) || messages('weather.location', 'weather.location.latitude').length > 0"
            @update:model-value="(value: string | number) => setCoordinate('latitude', value)"
          />
          <FieldError v-if="attempted && latitudeInvalid" :errors="[copy.location.invalidLatitude]" />
          <FieldError v-if="messages('weather.location.latitude').length" :errors="messages('weather.location.latitude')" />
        </Field>
        <Field :data-invalid="(attempted && longitudeInvalid) || messages('weather.location', 'weather.location.longitude').length > 0">
          <FieldLabel for="longitude">{{ copy.location.longitudeLabel }}</FieldLabel>
          <Input
            id="longitude"
            :model-value="location.longitude ?? ''"
            type="number"
            min="-180"
            max="180"
            step="0.0001"
            :placeholder="copy.location.longitudePlaceholder"
            :aria-invalid="(attempted && longitudeInvalid) || messages('weather.location', 'weather.location.longitude').length > 0"
            @update:model-value="(value: string | number) => setCoordinate('longitude', value)"
          />
          <FieldError v-if="attempted && longitudeInvalid" :errors="[copy.location.invalidLongitude]" />
          <FieldError v-if="messages('weather.location.longitude').length" :errors="messages('weather.location.longitude')" />
        </Field>
      </div>
      <FieldError v-if="messages('weather.location').length" :errors="messages('weather.location')" />
    </FieldGroup>
  </section>
</template>
