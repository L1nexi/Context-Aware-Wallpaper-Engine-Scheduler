<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import type { TickState } from '@/composables/useApi'
import { Monitor, Timer, Cpu } from '@element-plus/icons-vue'

const state = inject<Ref<TickState | null>>('state')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const loading = inject<Ref<boolean>>('loading')!

const activeWindow = computed(() => state.value?.active_window || 'N/A')
const idleTime = computed(() => state.value?.idle_time ?? 0)
const cpu = computed(() => state.value?.cpu ?? 0)
const isEmpty = computed(() => !loading.value && !state.value)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <span>{{ t('context') }}</span>
    </div>
    <div class="panel-body">
      <el-skeleton v-if="loading" :rows="3" animated />
      <el-empty v-else-if="isEmpty" :description="t('noData')" :image-size="60" />
      <div v-else class="context-stats">
        <div class="context-row">
          <span class="context-label">
            <el-icon><Monitor /></el-icon>
            {{ t('activeWindow') }}
          </span>
          <span class="context-value">{{ activeWindow }}</span>
        </div>
        <div class="context-row">
          <span class="context-label">
            <el-icon><Timer /></el-icon>
            {{ t('idle') }}
          </span>
          <span class="context-value">{{ idleTime }}s</span>
        </div>
        <div class="context-row">
          <span class="context-label">
            <el-icon><Cpu /></el-icon>
            {{ t('cpu') }}
          </span>
          <span class="context-value">{{ cpu }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>
