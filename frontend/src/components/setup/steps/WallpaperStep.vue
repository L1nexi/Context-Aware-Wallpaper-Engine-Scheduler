<script setup lang="ts">
import { CheckIcon, FolderOpenIcon, LayersIcon, RefreshCwIcon, TriangleAlertIcon } from "@lucide/vue"
import { computed } from "vue"

import type { Locale, PlaylistScanResult } from "@/api/profile"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { COPY } from "@/setup/copy"
import type { ScanStatus } from "@/setup/usePlaylistScan"

const props = defineProps<{
  locale: Locale
  path: string
  status: ScanStatus
  detail: string
  playlists: PlaylistScanResult["playlists"]
  usableCount: number
  nativeBridge: boolean
  invalid: boolean
  errors: string[]
}>()

const emit = defineEmits<{
  "update:path": [value: string]
  scan: []
  choose: []
}>()

const copy = computed(() => COPY[props.locale])
</script>

<template>
  <section class="flex flex-col gap-6">
    <FieldGroup>
      <Field :data-invalid="invalid || errors.length > 0">
        <FieldLabel for="wallpaper-engine-path">{{ copy.wallpaper.pathLabel }}</FieldLabel>
        <InputGroup>
          <InputGroupInput
            id="wallpaper-engine-path"
            :model-value="path"
            :placeholder="copy.wallpaper.pathPlaceholder"
            :aria-invalid="invalid || errors.length > 0"
            @update:model-value="(value: string | number) => emit('update:path', String(value))"
          />
          <InputGroupAddon align="inline-end">
            <InputGroupButton v-if="nativeBridge" :aria-label="copy.wallpaper.choose" @click="emit('choose')">
              <FolderOpenIcon />
              <span>{{ copy.wallpaper.choose }}</span>
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
        <FieldDescription>{{ copy.wallpaper.pathDescription }}</FieldDescription>
        <FieldError v-if="errors.length" :errors="errors" />
      </Field>
    </FieldGroup>

    <div class="flex flex-wrap gap-2">
      <Button :disabled="status === 'loading'" @click="emit('scan')">
        <Spinner v-if="status === 'loading'" data-icon="inline-start" />
        <RefreshCwIcon v-else data-icon="inline-start" />
        {{ status === "loading" ? copy.wallpaper.scanning : path ? copy.wallpaper.scan : copy.wallpaper.detect }}
      </Button>
    </div>

    <Alert v-if="status === 'error'" variant="destructive">
      <TriangleAlertIcon />
      <AlertTitle>{{ copy.wallpaper.emptyTitle }}</AlertTitle>
      <AlertDescription>{{ detail }}</AlertDescription>
    </Alert>

    <Empty v-else-if="status === 'empty'">
      <EmptyHeader>
        <EmptyMedia variant="icon"><LayersIcon /></EmptyMedia>
        <EmptyTitle>{{ copy.wallpaper.emptyTitle }}</EmptyTitle>
        <EmptyDescription>{{ copy.wallpaper.emptyDescription }}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" @click="emit('scan')">
          <RefreshCwIcon data-icon="inline-start" />
          {{ copy.wallpaper.scanAgain }}
        </Button>
      </EmptyContent>
    </Empty>

    <div v-else-if="status === 'success'" class="flex flex-col gap-4">
      <Alert>
        <CheckIcon />
        <AlertTitle>{{ copy.wallpaper.found }}</AlertTitle>
        <AlertDescription>{{ copy.wallpaper.foundDescription(usableCount) }}</AlertDescription>
      </Alert>
      <p class="text-sm text-muted-foreground">{{ copy.wallpaper.englishNames }}</p>
      <div class="overflow-hidden rounded-lg border">
        <Table class="table-fixed">
          <TableCaption class="sr-only">{{ copy.wallpaper.scanResultsLabel }}</TableCaption>
          <TableHeader class="bg-muted/40">
            <TableRow>
              <TableHead>{{ copy.wallpaper.playlistName }}</TableHead>
              <TableHead class="w-28 text-right">{{ copy.wallpaper.wallpaperCount }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="playlist in playlists" :key="playlist.name">
              <TableCell class="min-w-0">
                <span class="block truncate font-medium" :title="playlist.name">{{ playlist.name }}</span>
              </TableCell>
              <TableCell class="text-right" :class="playlist.item_count > 0 ? 'text-foreground' : 'text-muted-foreground'">
                {{ playlist.item_count > 0 ? copy.wallpaper.itemCount(playlist.item_count) : copy.wallpaper.zeroItem }}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>
  </section>
</template>
