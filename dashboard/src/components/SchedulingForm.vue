<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import type { SchedulingConfig } from '@/composables/useConfig'

const scheduling = inject<Ref<SchedulingConfig>>('editingScheduling')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

const sliders = computed(() => [
  { key: 'startup_delay' as keyof SchedulingConfig, min: 0, max: 120, step: 5, unit: 's' },
  { key: 'idle_threshold' as keyof SchedulingConfig, min: 0, max: 300, step: 5, unit: 's' },
  { key: 'switch_cooldown' as keyof SchedulingConfig, min: 0, max: 7200, step: 30, unit: 's' },
  { key: 'cycle_cooldown' as keyof SchedulingConfig, min: 0, max: 3600, step: 30, unit: 's' },
  { key: 'force_after' as keyof SchedulingConfig, min: 0, max: 86400, step: 300, unit: 's' },
  { key: 'cpu_threshold' as keyof SchedulingConfig, min: 50, max: 100, step: 1, unit: '%' },
  { key: 'cpu_sample_window' as keyof SchedulingConfig, min: 1, max: 60, step: 1, unit: 's' },
])
</script>

<template>
  <div class="scheduling-form">
    <div v-for="s in sliders" :key="s.key" class="field-row">
      <div class="field-label">
        <span>{{ t('sched_' + s.key) }}</span>
        <el-tooltip :content="t('sched_' + s.key + '_tip')" placement="right">
          <el-icon :size="14"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
      <el-slider
        v-model="scheduling[s.key]"
        :min="s.min" :max="s.max" :step="s.step"
        :format-tooltip="(val: number) => `${val}${s.unit}`"
        style="flex: 1; margin: 0 12px"
      />
      <span class="field-value">{{ scheduling[s.key] }}{{ s.unit }}</span>
    </div>
    <div class="field-row">
      <div class="field-label">
        <span>{{ t('sched_pause_on_fullscreen') }}</span>
        <el-tooltip :content="t('sched_pause_on_fullscreen_tip')" placement="right">
          <el-icon :size="14"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
      <el-switch v-model="scheduling.pause_on_fullscreen" />
    </div>
  </div>
</template>

<style scoped>
.scheduling-form { padding: 8px 0; }
.field-row {
  display: flex; align-items: center;
  padding: 10px 0; border-bottom: 1px solid var(--el-border-color, #e4e7ed);
}
.field-label {
  width: 180px; display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: #606266;
}
.field-value {
  min-width: 64px; text-align: right; font-size: 13px;
  font-variant-numeric: tabular-nums; color: #909399;
}
</style>
