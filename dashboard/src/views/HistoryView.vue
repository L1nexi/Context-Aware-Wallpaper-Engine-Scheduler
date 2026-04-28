<script setup lang="ts">
import { ref, computed, inject, watch, type Ref } from 'vue'
import VChart from 'vue-echarts'
import { EventType, type Segment, type HistoryEvent } from '@/composables/useHistory'
import {
  RefreshRight, VideoPlay, VideoPause, Switch, CircleClose,
  Loading, Timer, Connection,
} from '@element-plus/icons-vue'

const segments = inject<Ref<Segment[]>>('segments')!
const events = inject<Ref<HistoryEvent[]>>('events')!
const fetchHistory = inject<(params?: Record<string, string>) => Promise<void>>('fetchHistory')!
const loading = inject<Ref<boolean>>('historyLoading')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

const presets = [
  { label: '1h', value: 1 },
  { label: '6h', value: 6 },
  { label: '24h', value: 24 },
  { label: '7d', value: 168 },
]
const activePreset = ref(1)
const fromDate = ref('')
const toDate = ref('')

function applyPreset(hours: number) {
  activePreset.value = hours
  const to = new Date()
  const from = new Date(to.getTime() - hours * 3600000)
  fromDate.value = from.toISOString().slice(0, 16)
  toDate.value = to.toISOString().slice(0, 16)
  fetchHistory({ from: from.toISOString(), to: to.toISOString() })
}

function applyCustom() {
  activePreset.value = 0
  if (fromDate.value && toDate.value) {
    fetchHistory({ from: new Date(fromDate.value).toISOString(), to: new Date(toDate.value).toISOString() })
  }
}

// Playlist color map
const PALETTE = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc']
const colorMap = new Map<string, string>()
let colorIdx = 0

function playlistColor(name: string | null): string {
  if (!name) return '#909399'
  if (!colorMap.has(name)) {
    colorMap.set(name, PALETTE[colorIdx % PALETTE.length]!)
    colorIdx++
  }
  return colorMap.get(name)!
}

// ── Gantt chart option ──
const ganttOption = computed(() => {
  const data = segments.value.map((seg) => {
    const color = seg.type === 'pause' ? '#909399'
      : seg.type === 'dead' ? 'transparent'
      : playlistColor(seg.playlist)
    const label = seg.type === 'pause' ? t('dashboard_paused')
      : seg.type === 'dead' ? '—'
      : (seg.playlist || '?')
    return {
      name: label,
      value: [seg.start, seg.end],
      itemStyle: {
        color,
        borderColor: seg.type === 'dead' ? '#909399' : undefined,
        borderType: seg.type === 'dead' ? 'dashed' : undefined,
        borderWidth: seg.type === 'dead' ? 1 : 0,
        borderRadius: 4,
      },
    }
  })

  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const d = p.data
        if (!d) return ''
        return `${d.name}<br/>${d.value[0]}<br/>→ ${d.value[1]}`
      },
    },
    grid: { left: 0, right: 0, top: 8, bottom: 0 },
    xAxis: { type: 'time', axisLabel: { fontSize: 10 }, splitLine: { show: false } },
    yAxis: { show: false, data: [''] },
    series: [{
      type: 'custom',
      renderItem: (_params: any, api: any) => {
        const start = api.coord([api.value(0), 0])
        const end = api.coord([api.value(1), 0])
        const height = 24
        const y = api.coord([0, 0])[1] - height / 2
        return {
          type: 'rect',
          shape: { x: start[0], y, width: Math.max(end[0] - start[0], 2), height },
          style: api.style(),
        }
      },
      encode: { x: [0, 1], y: 0 },
      data,
    }],
  }
})

// ── Event list helpers ──
function eventIcon(type: EventType) {
  const map: Record<EventType, any> = {
    [EventType.PLAYLIST_SWITCH]: Switch,
    [EventType.WALLPAPER_CYCLE]: RefreshRight,
    [EventType.PAUSE]: VideoPause,
    [EventType.RESUME]: VideoPlay,
    [EventType.START]: Loading,
    [EventType.STOP]: CircleClose,
  }
  return map[type] || Timer
}

function eventDesc(evt: HistoryEvent): string {
  switch (evt.type) {
    case EventType.PLAYLIST_SWITCH:
      return `${evt.data.playlist_from || '?'} → ${evt.data.playlist_to || '?'}`
    case EventType.WALLPAPER_CYCLE:
      return `${evt.data.playlist || '?'}`
    case EventType.PAUSE:
      return evt.data.duration != null
        ? `${Math.round(evt.data.duration / 60)}min`
        : t('pause_indefinitely')
    case EventType.RESUME: return t('resume')
    case EventType.START: return 'Started'
    case EventType.STOP: return 'Stopped'
    default: return evt.type
  }
}

function formatTs(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

// Initial load
applyPreset(1)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><Connection /></el-icon>
      <span>{{ t('dashboard_show') }}</span>
    </div>
    <div class="panel-body history-body">
      <!-- Filter bar -->
      <div class="history-filters">
        <el-button-group size="small">
          <el-button
            v-for="p in presets" :key="p.value"
            :type="activePreset === p.value ? 'primary' : 'default'"
            @click="applyPreset(p.value)"
          >{{ p.label }}</el-button>
        </el-button-group>
        <el-date-picker
          v-model="fromDate" type="datetime" size="small"
          placeholder="From" format="MM-DD HH:mm"
          @change="applyCustom"
        />
        <el-date-picker
          v-model="toDate" type="datetime" size="small"
          placeholder="To" format="MM-DD HH:mm"
          @change="applyCustom"
        />
      </div>

      <el-skeleton v-if="loading" :rows="4" animated />

      <template v-else>
        <!-- Gantt -->
        <div class="gantt-wrap">
          <VChart v-if="segments.length" :option="ganttOption" autoresize style="height: 64px" />
          <el-empty v-else :image-size="48" />
        </div>

        <!-- Event list -->
        <div class="event-list">
          <div
            v-for="(evt, i) in events" :key="i"
            class="event-row"
          >
            <el-icon :size="14"><component :is="eventIcon(evt.type)" /></el-icon>
            <span class="event-time">{{ formatTs(evt.ts) }}</span>
            <span class="event-desc">{{ eventDesc(evt) }}</span>
            <span v-if="evt.data.tags" class="event-tags">
              <template v-for="([tag, w], idx) in Object.entries(evt.data.tags as Record<string, number>).slice(0, 3)" :key="tag">
                <el-tag size="small" type="info">{{ tag }} {{ w.toFixed(2) }}</el-tag>
              </template>
            </span>
          </div>
          <el-empty v-if="!events.length" :image-size="48" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.history-body { padding: 8px 0; }
.history-filters {
  display: flex; gap: 8px; align-items: center;
  padding: 8px 16px; flex-wrap: wrap;
}
.gantt-wrap { padding: 4px 16px 12px; }
.event-list { padding: 0 16px; }
.event-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0; font-size: 13px;
  border-bottom: 1px solid var(--border-color, #333);
}
.event-time { color: #909399; min-width: 48px; font-variant-numeric: tabular-nums; }
.event-desc { flex: 1; }
.event-tags { display: flex; gap: 4px; flex-wrap: wrap; }
</style>
