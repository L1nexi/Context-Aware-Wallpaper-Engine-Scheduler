<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { useI18n } from '@/composables/useI18n'
import { useConfigDocumentStore } from '@/stores/configDocument'

import ConfigFieldRow from './ConfigFieldRow.vue'
import ConfigNumberField from './ConfigNumberField.vue'
import ConfigRestoreDefaultsDialog from './ConfigRestoreDefaultsDialog.vue'
import ConfigSectionPanel from './ConfigSectionPanel.vue'

const { t } = useI18n()
const configStore = useConfigDocumentStore()
const { draft, saving } = storeToRefs(configStore)

const restoreDialogOpen = ref(false)
const scheduling = computed(() => draft.value?.scheduling ?? null)
const schedulingErrors = computed(() => configStore.sectionMessages('scheduling'))

function restoreDefaults(): void {
  configStore.restoreSchedulingDefaults()
  restoreDialogOpen.value = false
}
</script>

<template>
  <ConfigSectionPanel
    :eyebrow="t('config_editor_eyebrow')"
    :title="t('config_scheduling_title')"
    :description="t('config_scheduling_body')"
    :restore-label="t('config_restore_scheduling')"
    :errors="schedulingErrors"
    :disabled="draft === null || saving"
    @restore="restoreDialogOpen = true"
  >
    <template #error-title>
      {{ t('config_section_errors') }}
    </template>

    <div v-if="scheduling !== null" class="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{{ t('config_group_startup') }}</CardTitle>
          <CardDescription>
            {{ t('config_group_startup_body') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="divide-y divide-border/70">
          <ConfigNumberField
            path-key="scheduling.startup_delay"
            :label="t('sched_startup_delay')"
            :description="t('sched_startup_delay_tip')"
            :model-value="scheduling.startup_delay"
            :min="0"
            :disabled="saving"
            @update:model-value="configStore.updateSchedulingNumber('startup_delay', $event)"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{{ t('config_group_switching') }}</CardTitle>
          <CardDescription>
            {{ t('config_group_switching_body') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="divide-y divide-border/70">
          <ConfigNumberField
            path-key="scheduling.switch_cooldown"
            :label="t('sched_switch_cooldown')"
            :description="t('sched_switch_cooldown_tip')"
            :model-value="scheduling.switch_cooldown"
            :min="0"
            :disabled="saving"
            @update:model-value="configStore.updateSchedulingNumber('switch_cooldown', $event)"
          />
          <ConfigNumberField
            path-key="scheduling.force_after"
            :label="t('sched_force_after')"
            :description="t('sched_force_after_tip')"
            :model-value="scheduling.force_after"
            :min="0"
            :disabled="saving"
            @update:model-value="configStore.updateSchedulingNumber('force_after', $event)"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{{ t('config_group_cycling') }}</CardTitle>
          <CardDescription>
            {{ t('config_group_cycling_body') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="divide-y divide-border/70">
          <ConfigNumberField
            path-key="scheduling.cycle_cooldown"
            :label="t('sched_cycle_cooldown')"
            :description="t('sched_cycle_cooldown_tip')"
            :model-value="scheduling.cycle_cooldown"
            :min="0"
            :disabled="saving"
            @update:model-value="configStore.updateSchedulingNumber('cycle_cooldown', $event)"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{{ t('config_group_idle') }}</CardTitle>
          <CardDescription>
            {{ t('config_group_idle_body') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="divide-y divide-border/70">
          <ConfigNumberField
            path-key="scheduling.idle_threshold"
            :label="t('sched_idle_threshold')"
            :description="t('sched_idle_threshold_tip')"
            :model-value="scheduling.idle_threshold"
            :min="0"
            :disabled="saving"
            @update:model-value="configStore.updateSchedulingNumber('idle_threshold', $event)"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{{ t('config_group_gates') }}</CardTitle>
          <CardDescription>
            {{ t('config_group_gates_body') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="divide-y divide-border/70">
          <ConfigNumberField
            path-key="scheduling.cpu_threshold"
            :label="t('sched_cpu_threshold')"
            :description="t('sched_cpu_threshold_tip')"
            :model-value="scheduling.cpu_threshold"
            :min="0"
            :max="100"
            unit="percent"
            :disabled="saving"
            @update:model-value="configStore.updateSchedulingNumber('cpu_threshold', $event)"
          />
          <ConfigNumberField
            path-key="scheduling.cpu_sample_window"
            :label="t('sched_cpu_sample_window')"
            :description="t('sched_cpu_sample_window_tip')"
            :model-value="scheduling.cpu_sample_window"
            :min="1"
            integer
            :disabled="saving"
            @update:model-value="configStore.updateSchedulingNumber('cpu_sample_window', $event)"
          />
          <ConfigFieldRow
            path-key="scheduling.pause_on_fullscreen"
            :label="t('sched_pause_on_fullscreen')"
            :description="t('sched_pause_on_fullscreen_tip')"
            :errors="configStore.fieldMessages('scheduling.pause_on_fullscreen')"
          >
            <template #default="{ id }">
              <Switch
                :id="id"
                :model-value="scheduling.pause_on_fullscreen"
                :disabled="saving"
                @update:model-value="configStore.updatePauseOnFullscreen(Boolean($event))"
              />
            </template>
          </ConfigFieldRow>
        </CardContent>
      </Card>
    </div>

    <ConfigRestoreDefaultsDialog
      v-model:open="restoreDialogOpen"
      :title="t('config_restore_scheduling_title')"
      :description="t('config_restore_scheduling_body')"
      :confirm-label="t('config_restore_defaults_confirm')"
      @confirm="restoreDefaults"
    />
  </ConfigSectionPanel>
</template>
