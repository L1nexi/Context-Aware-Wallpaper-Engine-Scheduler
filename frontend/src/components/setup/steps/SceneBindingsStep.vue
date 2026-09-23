<script setup lang="ts">
import { LightbulbIcon, TriangleAlertIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale, PlaylistScanResult, SceneCatalogItem, SceneId } from "@/api/profile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Field, FieldContent, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { COPY, SCENE_LABELS } from "@/setup/copy"
import type { ProfileDraft } from "@/setup/model"

type Scenes = ProfileDraft["scenes"]

const props = defineProps<{
  locale: Locale
  mode: "setup" | "settings"
  scenes: Scenes
  catalog: SceneCatalogItem[]
  playlists: PlaylistScanResult["playlists"]
  catalogError: string
  valid: boolean
  attempted: boolean
  errors: string[]
}>()

const emit = defineEmits<{
  "update:scenes": [value: Scenes]
  retryCatalog: []
}>()

const copy = computed(() => COPY[props.locale])
const supportedScenes = computed(() => new Set(props.catalog.map((scene) => scene.id)))
const availablePlaylists = computed(() => new Set(props.playlists.map((playlist) => playlist.name)))
const sceneGroups = computed(() => [
  {
    id: "context",
    title: copy.value.scenes.groups.context,
    scenes: ["day_work", "day_leisure", "night_work", "night_leisure"] as SceneId[],
  },
  {
    id: "season",
    title: copy.value.scenes.groups.season,
    scenes: ["spring", "summer", "autumn", "winter"] as SceneId[],
  },
  {
    id: "weather",
    title: copy.value.scenes.groups.weather,
    scenes: ["sunset", "rain"] as SceneId[],
  },
])

function toggleScene(sceneId: SceneId, enabled: boolean | "indeterminate"): void {
  const updated = { ...props.scenes }
  if (enabled === true) {
    updated[sceneId] ??= props.playlists[0]?.name ?? ""
  } else {
    delete updated[sceneId]
  }
  emit("update:scenes", updated)
}

function setPlaylist(sceneId: SceneId, value: unknown): void {
  if (typeof value === "string") emit("update:scenes", { ...props.scenes, [sceneId]: value })
}

function assignmentInvalid(sceneId: SceneId): boolean {
  return sceneId in props.scenes && !availablePlaylists.value.has(props.scenes[sceneId] ?? "")
}
</script>

<template>
  <section class="flex flex-col gap-6">
    <Alert v-if="mode === 'setup'">
      <LightbulbIcon />
      <AlertDescription>{{ copy.scenes.defaultHint }}</AlertDescription>
    </Alert>

    <Alert v-if="catalogError" variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription>{{ catalogError }}</AlertDescription>
      <Button variant="outline" size="sm" @click="emit('retryCatalog')">{{ copy.common.retry }}</Button>
    </Alert>

    <Alert v-if="playlists.length === 0" variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription>{{ copy.scenes.unavailable }}</AlertDescription>
    </Alert>

    <FieldSet v-for="group in sceneGroups" :key="group.id">
      <FieldLegend>{{ group.title }}</FieldLegend>
      <FieldGroup class="gap-2">
        <Field
          v-for="sceneId in group.scenes.filter((id) => supportedScenes.has(id))"
          :key="sceneId"
          orientation="responsive"
          :data-invalid="attempted && assignmentInvalid(sceneId)"
          class="min-w-0 rounded-lg border p-3"
        >
          <div class="flex min-w-44 items-center gap-3">
            <Checkbox
              :id="`scene-${sceneId}`"
              :model-value="sceneId in scenes"
              :disabled="playlists.length === 0"
              @update:model-value="(value) => toggleScene(sceneId, value)"
            />
            <FieldLabel :for="`scene-${sceneId}`" class="font-normal">
              {{ SCENE_LABELS[locale][sceneId] }}
            </FieldLabel>
          </div>
          <FieldContent class="min-w-0">
            <Select
              :model-value="scenes[sceneId]"
              :disabled="!(sceneId in scenes)"
              @update:model-value="(value) => setPlaylist(sceneId, value)"
            >
              <SelectTrigger
                class="min-w-0 w-full max-w-full"
                :aria-label="`${SCENE_LABELS[locale][sceneId]}: ${copy.scenes.playlist}`"
                :aria-invalid="attempted && assignmentInvalid(sceneId)"
                :aria-describedby="attempted && assignmentInvalid(sceneId) ? `scene-error-${sceneId}` : undefined"
                :title="scenes[sceneId] || undefined"
              >
                <SelectValue :placeholder="copy.scenes.choosePlaylist" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem v-for="playlist in playlists" :key="playlist.name" :value="playlist.name">
                    {{ copy.scenes.playlistOption(playlist.name, playlist.item_count) }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <FieldError
              v-if="attempted && assignmentInvalid(sceneId)"
              :id="`scene-error-${sceneId}`"
              :errors="[scenes[sceneId] ? copy.scenes.unavailablePlaylist : copy.scenes.bindingRequired]"
            />
          </FieldContent>
        </Field>
      </FieldGroup>
    </FieldSet>

    <FieldError
      v-if="(attempted && !valid) || errors.length"
      :errors="[
        ...(attempted && !valid ? [copy.scenes.required] : []),
        ...errors,
      ]"
    />
  </section>
</template>
