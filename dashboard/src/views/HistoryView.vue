<script setup lang="ts">
import { ref, computed, inject, watch, onMounted, type Ref, type Component } from 'vue'
import { FixedSizeList } from 'element-plus'
import type { FixedSizeListInstance } from 'element-plus'
import VChart from 'vue-echarts'
import { EventType, type Segment, type HistoryEvent } from '@/composables/useHistory'
import {
  RefreshRight, VideoPlay, VideoPause, Switch, CircleClose,
  Loading, Connection,
} from '@element-plus/icons-vue'

const segments = inject<Ref<Segment[]>>('segments')!
const filteredEvents = inject<Ref<HistoryEvent[]>>('filteredEvents')!
const fetchHistory = inject<(params?: Record<string, string>) => Promise<void>>('fetchHistory')!
const loading = inject<Ref<boolean>>('historyLoading')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

// ── Filter bar ──
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

// ── Playlist color map ──
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

// ── Bidirectional linking state ──
const highlightedSegment = ref<number | null>(null)
const virtualListRef = ref<FixedSizeListInstance>()

const segmentToFirstEvent = computed(() => {
  const evts = filteredEvents.value
  const segs = segments.value
  const map: (number | null)[] = new Array(segs.length).fill(null)
  let evtIdx = 0
  for (let segIdx = 0; segIdx < segs.length; segIdx++) {
    const seg = segs[segIdx]!
    while (evtIdx < evts.length && evts[evtIdx]!.ts < seg.start) evtIdx++
    if (evtIdx < evts.length && evts[evtIdx]!.ts < seg.end) map[segIdx] = evtIdx
  }
  return map
})

function findSegmentForEvent(evtTs: string): number | null {
  const idx = segments.value.findIndex(s => evtTs >= s.start && evtTs < s.end)
  return idx >= 0 ? idx : null
}

// ── Gantt chart option ──
const ganttOption = computed(() => {
  const hlIdx = highlightedSegment.value

  if (segments.value.length === 0) {
    return {}
  }

  const data = segments.value.map((seg, i) => {
    let color: string
    let label: string
    switch (seg.type) {
      case 'pause':
        color = '#c0c4cc'
        label = t('dashboard_paused')
        break
      case 'dead':
        color = 'transparent'
        label = ''
        break
      default:
        color = playlistColor(seg.playlist)
        label = seg.playlist || '?'
    }
    const opacity = (hlIdx !== null && hlIdx !== i) ? 0.25 : 1

    return {
      name: label,
      value: [seg.start, seg.end, 0],
      itemStyle: {
        color,
        opacity,
        borderColor: seg.type === 'dead' ? '#c0c4cc' : undefined,
        borderType: seg.type === 'dead' ? 'dashed' : undefined,
        borderWidth: seg.type === 'dead' ? 1 : 0,
        borderRadius: [4, 4, 4, 4],
      },
      _label: label,
      _type: seg.type || 'active',
    }
  })

  const rangeMs = segments.value.length >= 2
    ? new Date(segments.value[segments.value.length - 1]!.end).getTime()
      - new Date(segments.value[0]!.start).getTime()
    : 3600000
  const useDaily = rangeMs > 24 * 3600000

  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const d = p.data
        if (!d) return ''
        const s = new Date(d.value[0])
        const e = new Date(d.value[1])
        const fmt = (dt: Date) => dt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
        const dur = Math.round((e.getTime() - s.getTime()) / 60000)
        return `${d.name}<br/>${fmt(s)} → ${fmt(e)}<br/>${dur}min`
      },
    },
    grid: { left: 0, right: 0, top: 8, bottom: 24 },
    xAxis: {
      type: 'time',
      show: true,
      axisLabel: {
        fontSize: 10,
        color: '#909399',
        formatter: useDaily ? '{MM}-{dd}' : '{HH}:{mm}',
      },
      splitLine: {
        show: true,
        lineStyle: { color: '#ebeef5', type: 'dashed' },
      },
      minorTick: { show: true },
    },
    yAxis: { show: false, data: [''] },
    series: [{
      type: 'custom',
      renderItem: (params: any, api: any) => {
        const item = params.data as { _label?: string, _type?: string }
        const start = api.coord([api.value(0), 0])
        const end = api.coord([api.value(1), 0])
        const height = 28
        const y = start[1] - height / 2
        const segWidth = Math.max(end[0] - start[0], 2)
        const label = item._label || ''
        const segType = item._type || 'active'

        const rect: any = {
          type: 'rect',
          shape: { x: start[0], y, width: segWidth, height },
          style: api.style(),
        }

        if (segWidth > 60 && segType !== 'dead' && label) {
          return {
            type: 'group',
            children: [
              rect,
              {
                type: 'text',
                style: {
                  text: label,
                  fill: '#fff',
                  font: '600 11px "Segoe UI", sans-serif',
                },
                x: start[0] + 6,
                y: y + 18,
              },
            ],
          }
        }
        return rect
      },
      encode: { x: [0, 1], y: 2 },
      data,
    }],
  }
})

// ── Gantt click → scroll event list ──
function onGanttClick(params: any) {
  if (params.dataIndex == null) return
  const eventIdx = segmentToFirstEvent.value[params.dataIndex]
  if (eventIdx == null) return
  virtualListRef.value?.scrollToItem(eventIdx)
}

// ── Event helpers ──
function eventIcon(type: EventType): Component {
  const map: Record<string, Component> = {
    [EventType.PLAYLIST_SWITCH]: Switch,
    [EventType.WALLPAPER_CYCLE]: RefreshRight,
    [EventType.PAUSE]: VideoPause,
    [EventType.RESUME]: VideoPlay,
    [EventType.START]: Loading,
    [EventType.STOP]: CircleClose,
  }
  return map[type] || Connection
}

function eventDesc(evt: HistoryEvent): string {
  switch (evt.type) {
    case EventType.PLAYLIST_SWITCH:
      return `${evt.data.playlist_from || '?'} → ${evt.data.playlist_to || '?'}`
    case EventType.WALLPAPER_CYCLE:
      return evt.data.playlist || '?'
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

// ── Event hover → highlight Gantt segment ──
function onEventHover(evt: HistoryEvent) {
  highlightedSegment.value = findSegmentForEvent(evt.ts)
}

function onEventLeave() {
  highlightedSegment.value = null
}

// ── Virtual list height measurement ──
const eventSectionRef = ref<HTMLElement>()
const eventListHeight = ref(300)
let resizeObserver: ResizeObserver | null = null

watch(eventSectionRef, (el, _prev, onCleanup) => {
  if (el) {
    resizeObserver = new ResizeObserver(entries => {
      for (const entry of entries) {
        eventListHeight.value = entry.contentRect.height
      }
    })
    resizeObserver.observe(el)
  }
  onCleanup(() => resizeObserver?.disconnect())
})

// ── Initial load ──
onMounted(() => applyPreset(1))
</script>

<template>
  <div class="panel history-panel">
    <div class="panel-header">
      <el-icon><Connection /></el-icon>
      <span>{{ t('dashboard_show') }}</span>
    </div>

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

    <!-- Body: 50/50 Gantt + Events -->
    <div class="history-body">
      <el-skeleton v-if="loading" :rows="6" animated />

      <template v-else>
        <!-- Top half: Gantt chart -->
        <div class="gantt-section">
          <VChart
            v-if="segments.length"
            :option="ganttOption"
            autoresize
            style="width: 100%; height: 100%"
            @click="onGanttClick"
          />
          <el-empty v-else :image-size="48" :description="t('noData')" />
        </div>

        <!-- Divider -->
        <div class="history-divider" />

        <!-- Bottom half: Event list (virtual scroll) -->
        <div ref="eventSectionRef" class="event-section">
          <FixedSizeList
            v-if="filteredEvents.length"
            ref="virtualListRef"
            :data="filteredEvents"
            :total="filteredEvents.length"
            :item-size="44"
            :height="eventListHeight"
            class="event-virtual-list"
          >
            <template #default="{ index, style }">
              <div
                class="event-row"
                :style="style"
                @mouseenter="onEventHover(filteredEvents[index]!)"
                @mouseleave="onEventLeave"
              >
                <el-icon :size="14"><component :is="eventIcon(filteredEvents[index]!.type)" /></el-icon>
                <span class="event-time">{{ formatTs(filteredEvents[index]!.ts) }}</span>
                <span class="event-desc">{{ eventDesc(filteredEvents[index]!) }}</span>
                <span v-if="filteredEvents[index]!.data.tags" class="event-tags">
                  <template
                    v-for="([tag, w], idx) in Object.entries(
                      filteredEvents[index]!.data.tags as Record<string, number>
                    ).slice(0, 3)"
                    :key="tag"
                  >
                    <el-tag size="small" type="info">{{ tag }} {{ (w as number).toFixed(2) }}</el-tag>
                  </template>
                </span>
              </div>
            </template>
          </FixedSizeList>
          <el-empty v-else :image-size="48" :description="t('noData')" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.history-panel {
  height: 100%;
}

.history-filters {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 0 0 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.history-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.gantt-section {
  flex: 1;
  min-height: 80px;
  position: relative;
}

.history-divider {
  height: 1px;
  background: var(--el-border-color, #dcdfe6);
  margin: 4px 0;
  flex-shrink: 0;
}

.event-section {
  flex: 1;
  min-height: 0;
}

.event-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;
  font-size: 13px;
  height: 44px;
  box-sizing: border-box;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
  cursor: pointer;
  transition: background 0.15s;
}

.event-row:hover {
  background: var(--el-fill-color-light, #f5f7fa);
}

.event-time {
  color: #909399;
  min-width: 48px;
  font-variant-numeric: tabular-nums;
}

.event-desc {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-tags {
  display: flex;
  gap: 4px;
  flex-wrap: nowrap;
  flex-shrink: 0;
}
</style>
