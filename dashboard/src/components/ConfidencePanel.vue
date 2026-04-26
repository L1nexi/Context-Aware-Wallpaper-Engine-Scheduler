<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import type { TickState } from '@/composables/useApi'
import { TrendCharts } from '@element-plus/icons-vue'

const state = inject<Ref<TickState | null>>('state')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const loading = inject<Ref<boolean>>('loading')!

const similarity = computed(() => state.value?.similarity ?? 0)
const gap = computed(() => state.value?.similarity_gap ?? 0)
const magnitude = computed(() => state.value?.max_policy_magnitude ?? 0)
const isEmpty = computed(() => !loading.value && !state.value)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><TrendCharts /></el-icon>
      <span>{{ t('similarity') }}</span>
    </div>
    <div class="panel-body">
      <el-skeleton v-if="loading" :rows="3" animated />
      <el-empty v-else-if="isEmpty" :description="t('noData')" :image-size="60" />
      <div v-else class="confidence-values">
        <div class="confidence-row">
          <span class="confidence-label">{{ t('similarity') }}</span>
          <span class="confidence-number">{{ (similarity * 100).toFixed(1) }}%</span>
        </div>
        <div class="confidence-row">
          <span class="confidence-label">{{ t('gap') }}</span>
          <span class="confidence-number">{{ gap.toFixed(4) }}</span>
        </div>
        <div class="confidence-row">
          <span class="confidence-label">{{ t('magnitude') }}</span>
          <span class="confidence-number">{{ magnitude.toFixed(4) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
