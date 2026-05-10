<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { RouterView, onBeforeRouteLeave, useRoute } from 'vue-router'
import { AlertCircle, CheckCircle2, RotateCcw, Save } from 'lucide-vue-next'

import { Button } from '@/components/ui/button'
import { WorkbenchHeader, WorkbenchMain, WorkbenchPanel } from '@/components/ui/workbench'
import { useI18n } from '@/composables/useI18n'
import ConfigUnsavedChangesDialog from '@/features/config-editor/ConfigUnsavedChangesDialog.vue'
import { cn } from '@/lib/utils'
import { useConfigDocumentStore } from '@/stores/configDocument'

const { t } = useI18n()
const route = useRoute()
const configStore = useConfigDocumentStore()

const {
  canSave,
  draft,
  firstClientError,
  globalErrors,
  hasClientErrors,
  hasServerErrors,
  isDirty,
  loadError,
  loadErrorCode,
  loadErrorDetails,
  loading,
  saveError,
  saving,
  serverErrors,
} = storeToRefs(configStore)

const leaveDialogOpen = ref(false)
let pendingLeaveResolve: ((value: boolean) => void) | null = null

const currentSectionTitle = computed(() => {
  if (route.path === '/config/scheduling') {
    return t('config_scheduling')
  }

  if (route.path === '/config/playlists') {
    return t('config_playlists')
  }

  if (route.path === '/config/tags') {
    return t('config_tags_tab')
  }

  if (route.path === '/config/policies') {
    return t('config_policies')
  }

  return t('config_general')
})

const statusLabel = computed(() => {
  if (saving.value) {
    return t('config_status_saving')
  }

  if (isDirty.value) {
    return t('config_unsaved_indicator')
  }

  return t('config_status_saved')
})

const statusClass = computed(() =>
  cn(
    'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium',
    isDirty.value
      ? 'border-border bg-muted text-foreground'
      : 'border-primary/20 bg-primary/10 text-primary',
  ),
)

const saveErrorText = computed(() => {
  if (saveError.value === null) {
    return null
  }

  if (saveError.value === 'client_errors') {
    return firstClientError.value ?? t('config_client_errors_summary')
  }

  if (saveError.value === 'validation_failed') {
    return t('config_validation_failed_summary')
  }

  return saveError.value
})

const hasSummary = computed(
  () =>
    saveErrorText.value !== null ||
    globalErrors.value.length > 0 ||
    hasClientErrors.value ||
    hasServerErrors.value,
)

const loadErrorTitle = computed(() => {
  if (loadErrorCode.value === 'config_not_found') {
    return t('config_load_not_found_title')
  }

  if (loadErrorCode.value === 'invalid_config') {
    return t('config_load_invalid_title')
  }

  return t('config_load_failed')
})

const loadErrorBody = computed(() => {
  if (loadErrorCode.value === 'config_not_found') {
    return t('config_load_not_found_body')
  }

  if (loadErrorCode.value === 'invalid_config') {
    return t('config_load_invalid_body')
  }

  return t('config_load_http_body')
})

onMounted(() => {
  if (draft.value === null && !loading.value) {
    void configStore.load()
  }
})

function confirmLeave(): Promise<boolean> {
  return new Promise((resolve) => {
    pendingLeaveResolve = resolve
    leaveDialogOpen.value = true
  })
}

function resolveLeave(value: boolean): void {
  const resolve = pendingLeaveResolve
  pendingLeaveResolve = null
  leaveDialogOpen.value = false
  resolve?.(value)
}

watch(leaveDialogOpen, (open) => {
  if (!open && pendingLeaveResolve !== null) {
    resolveLeave(false)
  }
})

onBeforeRouteLeave(async (to) => {
  if (to.path === '/config' || to.path.startsWith('/config/')) {
    return true
  }

  if (!isDirty.value) {
    return true
  }

  const confirmed = await confirmLeave()
  if (confirmed) {
    configStore.discard()
  }

  return confirmed
})
</script>

<template>
  <WorkbenchHeader class="justify-between">
    <div class="min-w-0">
      <p class="chrome-kicker">{{ t('config_editor_eyebrow') }}</p>
      <div class="mt-1 flex min-w-0 flex-wrap items-center gap-3">
        <h2 class="truncate text-lg font-semibold tracking-tight">
          {{ currentSectionTitle }}
        </h2>
        <span :class="statusClass">
          <CheckCircle2 v-if="!isDirty" class="size-3.5" aria-hidden="true" />
          <AlertCircle v-else class="size-3.5" aria-hidden="true" />
          {{ statusLabel }}
        </span>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        :disabled="loading || saving || !isDirty"
        @click="configStore.discard()"
      >
        <RotateCcw class="size-4" aria-hidden="true" />
        {{ t('config_discard') }}
      </Button>
      <Button size="sm" :disabled="!canSave" @click="configStore.save()">
        <Save class="size-4" aria-hidden="true" />
        {{ saving ? t('config_saving') : t('config_save_btn') }}
      </Button>
    </div>
  </WorkbenchHeader>

  <WorkbenchMain>
    <WorkbenchPanel
      v-if="loading && draft === null"
      padding="lg"
      class="flex min-h-[28rem] flex-1 flex-col justify-center"
    >
      <div class="mx-auto flex max-w-xl flex-col items-center gap-4 text-center">
        <p class="chrome-kicker">{{ t('dashboard_config') }}</p>
        <h3 class="text-2xl font-semibold tracking-tight">
          {{ t('config_loading_title') }}
        </h3>
        <p class="max-w-lg text-sm leading-6 text-muted-foreground">
          {{ t('config_loading_body') }}
        </p>
      </div>
    </WorkbenchPanel>

    <WorkbenchPanel
      v-else-if="loadError !== null"
      padding="lg"
      class="flex min-h-[28rem] flex-1 flex-col justify-center"
    >
      <div class="mx-auto flex max-w-xl flex-col items-center gap-5 text-center">
        <p class="chrome-kicker">{{ t('dashboard_config') }}</p>
        <h3 class="text-2xl font-semibold tracking-tight">
          {{ loadErrorTitle }}
        </h3>
        <p class="max-w-lg text-sm leading-6 text-muted-foreground">
          {{ loadErrorBody }}
        </p>
        <div
          class="w-full rounded-lg border border-destructive/15 bg-destructive/6 px-4 py-3 text-left"
        >
          <p class="chrome-kicker text-destructive">
            {{ t('dashboard_last_error') }}
          </p>
          <p class="mt-2 break-all text-sm text-foreground">
            {{ loadErrorDetails ?? loadError }}
          </p>
        </div>
        <Button @click="configStore.load()">
          {{ t('config_retry') }}
        </Button>
      </div>
    </WorkbenchPanel>

    <template v-else>
      <div
        v-if="hasSummary"
        class="rounded-lg border border-destructive/20 bg-destructive/8 px-4 py-3"
      >
        <div class="flex items-start gap-3">
          <AlertCircle class="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
          <div class="space-y-2">
            <div>
              <p class="text-sm font-medium text-destructive">
                {{ t('config_error_summary_title') }}
              </p>
              <p v-if="saveErrorText" class="mt-1 text-sm text-destructive/90">
                {{ saveErrorText }}
              </p>
              <p v-else-if="hasClientErrors" class="mt-1 text-sm text-destructive/90">
                {{ t('config_client_errors_summary') }}
              </p>
            </div>

            <ul v-if="globalErrors.length > 0" class="space-y-1">
              <li
                v-for="error in globalErrors"
                :key="`${error.code}-${error.message}`"
                class="text-sm text-destructive/90"
              >
                {{ error.message }}
              </li>
            </ul>

            <p
              v-if="serverErrors.length > 0 && globalErrors.length === 0"
              class="text-sm text-destructive/90"
            >
              {{ t('config_server_errors_summary', { count: serverErrors.length }) }}
            </p>
          </div>
        </div>
      </div>

      <RouterView />
    </template>
  </WorkbenchMain>

  <ConfigUnsavedChangesDialog
    v-model:open="leaveDialogOpen"
    @confirm="resolveLeave(true)"
    @cancel="resolveLeave(false)"
  />
</template>
