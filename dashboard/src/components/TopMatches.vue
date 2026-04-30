<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import type { TickState } from '@/composables/useApi'
import { Medal } from '@element-plus/icons-vue'

const state = inject<Ref<TickState | null>>('state')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const loading = inject<Ref<boolean>>('loading')!

const topMatches = computed(() => state.value?.top_matches ?? [])
const isEmpty = computed(() => !loading.value && topMatches.value.length === 0)

const maxScore = computed(() => {
  if (topMatches.value.length === 0) return 1
  return Math.max(...topMatches.value.map(([, s]) => s), 0.001)
})
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><Medal /></el-icon>
      <span>{{ t('topMatches') }}</span>
    </div>
    <div class="panel-body">
      <el-skeleton v-if="loading" :rows="3" animated />
      <el-empty v-else-if="isEmpty" :description="t('noData')" :image-size="60" />
      <div v-else class="top5-list">
        <div
          v-for="([name, score], index) in topMatches"
          :key="name"
          class="top5-row"
          :class="{ 'is-best': index === 0 }"
        >
          <span class="top5-rank">#{{ index + 1 }}</span>
          <span class="top5-name">{{ name }}</span>
          <span class="top5-pct">{{ (score * 100).toFixed(1) }}%</span>
          <div class="top5-bar-bg">
            <div
              class="top5-bar-fill"
              :style="{ width: (score / maxScore * 100).toFixed(1) + '%' }"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.top5-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.top5-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.top5-rank {
  width: 28px;
  font-size: 11px;
  color: #c0c4cc;
  flex-shrink: 0;
}

.top5-row.is-best .top5-rank {
  color: var(--el-color-primary);
  font-weight: 600;
}

.top5-name {
  width: 140px;
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top5-row.is-best .top5-name {
  color: #303133;
  font-weight: 600;
}

.top5-pct {
  width: 52px;
  font-size: 12px;
  color: #909399;
  text-align: right;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.top5-row.is-best .top5-pct {
  color: var(--el-color-primary);
  font-weight: 600;
}

.top5-bar-bg {
  flex: 1;
  height: 14px;
  background: #ebeef5;
  border-radius: 3px;
  overflow: hidden;
}

.top5-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--el-color-primary-light-5), var(--el-color-primary-light-3));
  border-radius: 3px;
  transition: width 0.6s ease;
}

.top5-row.is-best .top5-bar-fill {
  background: linear-gradient(90deg, var(--el-color-primary-light-3), var(--el-color-primary));
}
</style>
