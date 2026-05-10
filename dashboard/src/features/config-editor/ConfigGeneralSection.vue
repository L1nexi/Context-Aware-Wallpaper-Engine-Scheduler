<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { Search } from 'lucide-vue-next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useI18n } from '@/composables/useI18n'
import { detectWallpaperEnginePath } from '@/lib/configDocument'
import { cn } from '@/lib/utils'
import { useConfigDocumentStore } from '@/stores/configDocument'

import ConfigFieldRow from './ConfigFieldRow.vue'
import ConfigRestoreDefaultsDialog from './ConfigRestoreDefaultsDialog.vue'
import ConfigSectionPanel from './ConfigSectionPanel.vue'
import ConfigTextField from './ConfigTextField.vue'

const { t } = useI18n()
const configStore = useConfigDocumentStore()
const { draft, saving } = storeToRefs(configStore)

const restoreDialogOpen = ref(false)
const detectingPath = ref(false)
const detectMessage = ref<string | null>(null)
const detectTone = ref<'success' | 'warning' | 'error'>('warning')

const generalErrors = computed(() => configStore.sectionMessages('general'))

const wallpaperEnginePath = computed({
  get: () => draft.value?.wallpaper_engine_path ?? '',
  set: (value: string) => {
    detectMessage.value = null
    configStore.updateWallpaperEnginePath(value)
  },
})

const languageSelection = computed({
  get: () => draft.value?.language ?? 'auto',
  set: (value: string) => {
    configStore.updateLanguage(value === 'auto' ? null : value)
  },
})

async function handleDetectWallpaperEnginePath(): Promise<void> {
  detectingPath.value = true
  detectMessage.value = null

  try {
    const result = await detectWallpaperEnginePath()
    if (result.valid && result.path) {
      configStore.updateWallpaperEnginePath(result.path)
      detectTone.value = 'success'
      detectMessage.value = t('config_we_detect_success', { path: result.path })
    } else {
      detectTone.value = 'warning'
      detectMessage.value = t('config_we_detect_empty')
    }
  } catch (cause) {
    detectTone.value = 'error'
    detectMessage.value = t('config_we_detect_failed', {
      error: cause instanceof Error ? cause.message : String(cause),
    })
  } finally {
    detectingPath.value = false
  }
}

function restoreDefaults(): void {
  configStore.restoreGeneralDefaults()
  restoreDialogOpen.value = false
  detectMessage.value = null
}
</script>

<template>
  <ConfigSectionPanel
    :eyebrow="t('config_editor_eyebrow')"
    :title="t('config_general_title')"
    :description="t('config_general_body')"
    :restore-label="t('config_restore_general')"
    :errors="generalErrors"
    :disabled="draft === null || saving"
    @restore="restoreDialogOpen = true"
  >
    <template #error-title>
      {{ t('config_section_errors') }}
    </template>

    <div v-if="draft !== null" class="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{{ t('config_group_runtime') }}</CardTitle>
          <CardDescription>
            {{ t('config_group_runtime_body') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="divide-y divide-border/70">
          <ConfigTextField
            v-model="wallpaperEnginePath"
            path-key="wallpaper_engine_path"
            :label="t('config_we_path')"
            :description="t('config_we_path_body')"
            :placeholder="t('config_we_placeholder')"
            :disabled="saving"
          >
            <template #actions>
              <Button
                type="button"
                variant="outline"
                :disabled="saving || detectingPath"
                class="shrink-0"
                @click="handleDetectWallpaperEnginePath"
              >
                <Search class="size-4" aria-hidden="true" />
                {{ detectingPath ? t('config_we_detecting') : t('config_detect_we') }}
              </Button>
            </template>
          </ConfigTextField>

          <p
            v-if="detectMessage"
            :class="
              cn(
                'px-0 pb-4 pt-1 text-sm leading-5 md:ml-[calc(16rem+1.5rem)]',
                detectTone === 'success' && 'text-primary',
                detectTone === 'warning' && 'text-muted-foreground',
                detectTone === 'error' && 'text-destructive',
              )
            "
          >
            {{ detectMessage }}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{{ t('config_group_locale') }}</CardTitle>
          <CardDescription>
            {{ t('config_group_locale_body') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="divide-y divide-border/70">
          <ConfigFieldRow
            path-key="language"
            :label="t('config_language')"
            :description="t('config_language_body')"
            :errors="configStore.fieldMessages('language')"
          >
            <template #default="{ id, invalid }">
              <Select v-model="languageSelection" :disabled="saving">
                <SelectTrigger :id="id" :aria-invalid="invalid" class="w-full sm:w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">
                    {{ t('config_language_auto') }}
                  </SelectItem>
                  <SelectItem value="en"> English </SelectItem>
                  <SelectItem value="zh"> 中文 </SelectItem>
                </SelectContent>
              </Select>
            </template>
          </ConfigFieldRow>
        </CardContent>
      </Card>
    </div>

    <ConfigRestoreDefaultsDialog
      v-model:open="restoreDialogOpen"
      :title="t('config_restore_general_title')"
      :description="t('config_restore_general_body')"
      :confirm-label="t('config_restore_defaults_confirm')"
      @confirm="restoreDefaults"
    />
  </ConfigSectionPanel>
</template>
