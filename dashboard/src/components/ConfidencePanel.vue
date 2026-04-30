<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import VChart from 'vue-echarts'
import type { TickState } from '@/composables/useApi'
import { TrendCharts } from '@element-plus/icons-vue'

const state = inject<Ref<TickState | null>>('state')!
const ticks = inject<Ref<TickState[]>>('ticks')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const loading = inject<Ref<boolean>>('loading')!

const playlistName = computed(() => state.value?.current_playlist_display || state.value?.current_playlist || '')
const similarity = computed(() => state.value?.similarity ?? 0)
const gap = computed(() => state.value?.similarity_gap ?? 0)
const magnitude = computed(() => state.value?.max_policy_magnitude ?? 0)
const isEmpty = computed(() => !loading.value && !state.value)

const sparklineOption = computed(() => {
  const raw = ticks.value.map((t: TickState) => t.similarity)
  if (raw.length < 2) {
    return {
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: 'value', show: false },
      yAxis: { type: 'value', show: false, min: 0, max: 1 },
      series: [{ type: 'line', data: [], showSymbol: false }],
    }
  }
  const dataMin = Math.min(...raw)
  const dataMax = Math.max(...raw)
  const range = dataMax - dataMin || 0.01
  const pad = range * 0.2
  const yMin = Math.max(0, dataMin - pad)
  const yMax = Math.min(1, dataMax + pad)

  const data = ticks.value.map((t: TickState) => [t.ts * 1000, t.similarity])
  return {
    grid: { left: 8, right: 8, top: 4, bottom: 4 },
    xAxis: { type: 'time', show: false },
    yAxis: {
      type: 'value',
      show: true,
      min: yMin,
      max: yMax,
      axisLabel: { fontSize: 10, color: '#909399', formatter: (v: number) => v.toFixed(2) },
      splitLine: { lineStyle: { color: '#ebeef5', type: 'dashed' } },
      splitNumber: 3,
    },
    series: [{
      type: 'line', data, showSymbol: false,
      lineStyle: { color: '#a0c4ff', width: 1.5 },
      areaStyle: { color: 'rgba(160,196,255,0.08)' },
    }],
  }
})
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

      <div v-else class="sim-layout">
        <div class="sim-current">
          <span class="sim-current-label">{{ t('currentPlaylist') }}</span>
          <span class="sim-current-name">{{ playlistName || '—' }}</span>
          <span class="sim-current-pct">{{ (similarity * 100).toFixed(1) }}%</span>
        </div>
        <div class="sim-sparkline" v-if="ticks.length >= 2">
          <VChart :option="sparklineOption" autoresize style="height: 72px" />
        </div>
        <div class="sim-stats">
          <div class="sim-stat">
            <span class="sim-stat-label">{{ t('gap') }}</span>
            <span class="sim-stat-value">{{ gap.toFixed(4) }}</span>
          </div>
          <div class="sim-stat">
            <span class="sim-stat-label">{{ t('magnitude') }}</span>
            <span class="sim-stat-value">{{ magnitude.toFixed(4) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sim-layout {
  display: flex;
  align-items: center;
  gap: 20px;
}

.sim-current {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-width: 140px;
}

.sim-current-label {
  font-size: 11px;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sim-current-name {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  text-align: center;
  word-break: break-word;
}

.sim-current-pct {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.sim-sparkline {
  flex: 1;
  min-width: 0;
}

.sim-stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.sim-stat {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.sim-stat-label {
  font-size: 11px;
  color: #909399;
}

.sim-stat-value {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  font-variant-numeric: tabular-nums;
}
</style>
