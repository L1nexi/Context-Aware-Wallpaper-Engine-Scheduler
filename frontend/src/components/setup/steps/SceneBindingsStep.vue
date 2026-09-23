<script setup lang="ts">
import { LightbulbIcon, TriangleAlertIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale, PlaylistScanResult, SceneCatalogItem, SceneId } from "@/api/profile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Field, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field"
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
const recommendedScenes = new Set<SceneId>(["day_work", "day_leisure", "night_work", "night_leisure", "rain"])
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
</script>

<template>
  <section class="flex flex-col gap-6">
    <div class="max-w-2xl">
      <h1 class="text-2xl font-semibold tracking-tight">{{ copy.scenes.title }}</h1>
      <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.scenes.description }}</p>
    </div>

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
          class="rounded-lg border p-3"
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
            <Badge v-if="recommendedScenes.has(sceneId)" variant="secondary">{{ copy.scenes.recommended }}</Badge>
          </div>
          <Select
            :model-value="scenes[sceneId]"
            :disabled="!(sceneId in scenes)"
            @update:model-value="(value) => setPlaylist(sceneId, value)"
          >
            <SelectTrigger :aria-label="`${SCENE_LABELS[locale][sceneId]}: ${copy.scenes.playlist}`">
              <SelectValue :placeholder="copy.scenes.choosePlaylist" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem v-for="playlist in playlists" :key="playlist.name" :value="playlist.name">
                  {{ playlist.name }} ({{ playlist.item_count }})
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
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
