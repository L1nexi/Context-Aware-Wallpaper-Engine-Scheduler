<script setup lang="ts">
import { computed } from 'vue'
import { VisArea, VisAxis, VisTimeline, VisXYContainer } from '@unovis/vue'
import { Arrangement, AxisType, Position } from '@unovis/ts'
import type { ChartConfig } from '@/components/ui/chart'
import { ChartContainer } from '@/components/ui/chart'

const BUCKET_COUNT = 120
const COLLECTED_BUCKETS = 96
const FIRST_DATA_INDEX = BUCKET_COUNT - COLLECTED_BUCKETS
const TOP_PLAYLIST_COUNT = 5
const TAIL_SCORE_CAP = 0.035
const LANE_COUNT = 3
const BUCKET_SECONDS = 60

const playlists = [
  { key: 'rainy', label: '雨落时分', color: '#168a96' },
  { key: 'focus', label: '深度专注', color: '#3f6df6' },
  { key: 'night', label: '夜间低语', color: '#6d55e8' },
  { key: 'summer', label: '夏日余温', color: '#e38200' },
  { key: 'casual', label: '闲适日常', color: '#58a861' },
  { key: 'cloud', label: '云影漫游', color: '#8da0b7' },
  { key: 'storm', label: '雷声将近', color: '#9a6a3a' },
  { key: 'city', label: '城市霓虹', color: '#c04f8a' },
  { key: 'dawn', label: '晨光预热', color: '#c9a227' },
  { key: 'quiet', label: '安静留白', color: '#7b8794' },
] as const

type PlaylistKey = (typeof playlists)[number]['key']
type BlockerType = 'cooldown' | 'fullscreen' | 'cpu' | 'idle'

interface Bucket {
  index: number
  secondsFromStart: number
  rawScores: Record<PlaylistKey, number>
  displayScores: Record<PlaylistKey, number>
  ranks: Record<PlaylistKey, number>
  activePool: PlaylistKey[]
  hasCycle: boolean
  blockers: Partial<Record<BlockerType, number>>
}

interface TimelineSegment {
  id: string
  lane: string
  playlistKey: PlaylistKey
  start: number
  duration: number
  startsWithCycle: boolean
  blockers: Partial<Record<BlockerType, number>>
}

const chartConfig = Object.fromEntries(
  playlists.map((item) => [item.key, { label: item.label, color: item.color }]),
) satisfies ChartConfig

function wave(index: number, phase: number, amplitude: number): number {
  return Math.sin(index / 10 + phase) * amplitude + Math.cos(index / 25 + phase * 0.6) * amplitude
}

function smoothStep(edge0: number, edge1: number, value: number): number {
  const x = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)))
  return x * x * (3 - 2 * x)
}

function smoothWindow(index: number, start: number, end: number, edge = 8): number {
  return smoothStep(start - edge, start + edge, index) * (1 - smoothStep(end - edge, end + edge, index))
}

function clampScore(value: number): number {
  return Math.max(0.01, value)
}

function makeRawScores(index: number): Record<PlaylistKey, number> {
  const t = index
  return {
    rainy: clampScore(0.56 + wave(t, 0.4, 0.07) + smoothWindow(t, 32, 76, 9) * 0.2),
    focus: clampScore(0.5 + wave(t, 1.6, 0.06) + smoothWindow(t, 18, 58, 8) * 0.16),
    night: clampScore(0.34 + t / 330 + wave(t, 2.4, 0.05) + smoothWindow(t, 62, 112, 12) * 0.12),
    summer: clampScore(0.38 + wave(t, 3.1, 0.07) + smoothWindow(t, 78, 116, 10) * 0.15),
    casual: clampScore(0.42 + wave(t, 4.4, 0.055) + smoothStep(84, 114, t) * 0.18),
    cloud: clampScore(0.28 + wave(t, 5.2, 0.045) + smoothWindow(t, 24, 46, 6) * 0.12),
    storm: clampScore(0.24 + wave(t, 6.3, 0.04) + smoothWindow(t, 38, 58, 5) * 0.18),
    city: clampScore(0.26 + wave(t, 7.1, 0.045) + smoothWindow(t, 70, 102, 8) * 0.16),
    dawn: clampScore(0.2 + wave(t, 8.4, 0.035) + smoothWindow(t, 94, 118, 7) * 0.22),
    quiet: clampScore(0.22 + wave(t, 9.5, 0.035)),
  }
}

function rankScores(scores: Record<PlaylistKey, number>): Record<PlaylistKey, number> {
  const ordered = playlists
    .map((playlist) => ({ key: playlist.key, score: scores[playlist.key] }))
    .sort((a, b) => b.score - a.score)

  return Object.fromEntries(ordered.map((item, index) => [item.key, index + 1])) as Record<PlaylistKey, number>
}

function makeDisplayScores(
  scores: Record<PlaylistKey, number>,
  ranks: Record<PlaylistKey, number>,
): Record<PlaylistKey, number> {
  return Object.fromEntries(
    playlists.map((playlist) => {
      const score = scores[playlist.key]
      const displayScore = ranks[playlist.key] <= TOP_PLAYLIST_COUNT ? score : Math.min(score * 0.12, TAIL_SCORE_CAP)
      return [playlist.key, displayScore]
    }),
  ) as Record<PlaylistKey, number>
}

function makeActivePool(index: number): PlaylistKey[] {
  if (index < 36) return ['focus', 'rainy']
  if (index < 58) return ['rainy', 'storm', 'focus']
  if (index < 74) return ['rainy', 'night', 'summer']
  if (index < 92) return ['night', 'casual']
  if (index < 108) return ['casual', 'city', 'night']
  return ['dawn', 'casual']
}

function makeBlockers(index: number): Partial<Record<BlockerType, number>> {
  const blockers: Partial<Record<BlockerType, number>> = {}
  if (index >= 43 && index <= 50) blockers.cooldown = 60
  if (index >= 65 && index <= 70) blockers.fullscreen = 42
  if (index >= 96 && index <= 101) blockers.cpu = 38
  return blockers
}

function makeBucket(index: number): Bucket {
  const rawScores = makeRawScores(index)
  const ranks = rankScores(rawScores)
  return {
    index,
    secondsFromStart: index * BUCKET_SECONDS,
    rawScores,
    displayScores: makeDisplayScores(rawScores, ranks),
    ranks,
    activePool: makeActivePool(index),
    hasCycle: index === 52 || index === 83 || index === 104,
    blockers: makeBlockers(index),
  }
}

const buckets = Array.from({ length: COLLECTED_BUCKETS }, (_, offset) => makeBucket(FIRST_DATA_INDEX + offset))
const yAccessors = playlists.map((item) => (bucket: Bucket) => bucket.displayScores[item.key])
const xTicks = [0, 29, 59, 89, 119]

const scoreAreaColor = (_areaData: Bucket[], stackIndex?: number): string =>
  playlists[stackIndex ?? 0]?.color ?? playlists[playlists.length - 1].color

const scoreAreaLineColor = (_areaData: Bucket[], stackIndex?: number): string =>
  playlists[stackIndex ?? 0]?.color ?? playlists[playlists.length - 1].color

const scoreAreaOpacity = () => 0.5

function formatElapsed(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours <= 0) return `${minutes} 分`
  return `${hours} 小时 ${minutes.toString().padStart(2, '0')} 分`
}

function formatAxisTick(value: number | Date): string {
  if (value instanceof Date) return ''
  return formatElapsed(value * BUCKET_SECONDS)
}

function getPlaylistMeta(key: PlaylistKey): (typeof playlists)[number] {
  return playlists.find((playlist) => playlist.key === key) ?? playlists[0]
}

function getBlockerLabel(blockers: Partial<Record<BlockerType, number>>): string {
  const labels = Object.entries(blockers).map(([type, seconds]) => {
    const label =
      {
        cooldown: '冷却',
        fullscreen: '全屏',
        cpu: 'CPU',
        idle: '空闲',
      }[type] ?? type
    return `${label} ${seconds}s`
  })
  return labels.join(' / ')
}

function mergeBlockers(
  base: Partial<Record<BlockerType, number>>,
  next: Partial<Record<BlockerType, number>>,
): Partial<Record<BlockerType, number>> {
  const merged = { ...base }
  for (const [type, seconds] of Object.entries(next) as [BlockerType, number][]) {
    merged[type] = (merged[type] ?? 0) + seconds
  }
  return merged
}

function assignPoolLanes(sourceBuckets: Bucket[]): Array<{ bucket: Bucket; lanes: Map<PlaylistKey, number> }> {
  const previous = new Map<PlaylistKey, number>()

  return sourceBuckets.map((bucket) => {
    const lanes = new Map<PlaylistKey, number>()
    const usedLanes = new Set<number>()

    for (const playlistKey of bucket.activePool) {
      const previousLane = previous.get(playlistKey)
      if (previousLane !== undefined && !usedLanes.has(previousLane)) {
        lanes.set(playlistKey, previousLane)
        usedLanes.add(previousLane)
      }
    }

    for (const playlistKey of bucket.activePool) {
      if (lanes.has(playlistKey)) continue
      const lane = Array.from({ length: LANE_COUNT }, (_, index) => index).find((candidate) => !usedLanes.has(candidate))
      if (lane === undefined) continue
      lanes.set(playlistKey, lane)
      usedLanes.add(lane)
    }

    previous.clear()
    for (const [playlistKey, lane] of lanes) previous.set(playlistKey, lane)

    return { bucket, lanes }
  })
}

function makeTimelineSegments(sourceBuckets: Bucket[]): TimelineSegment[] {
  const assigned = assignPoolLanes(sourceBuckets)
  const segments: TimelineSegment[] = []
  const latestByLane = new Map<string, TimelineSegment>()

  function startSegment(bucket: Bucket, playlistKey: PlaylistKey, lane: number, startsWithCycle: boolean): TimelineSegment {
    return {
      id: `${playlistKey}-${lane}-${bucket.index}`,
      lane: `pool-${lane + 1}`,
      playlistKey,
      start: bucket.index,
      duration: 1,
      startsWithCycle,
      blockers: { ...bucket.blockers },
    }
  }

  for (const { bucket, lanes } of assigned) {
    for (const [playlistKey, lane] of lanes) {
      const laneKey = `pool-${lane + 1}`
      const previous = latestByLane.get(laneKey)
      const canExtend =
        previous?.playlistKey === playlistKey &&
        previous.start + previous.duration === bucket.index &&
        !bucket.hasCycle

      if (canExtend) {
        previous.duration += 1
        previous.blockers = mergeBlockers(previous.blockers, bucket.blockers)
      } else {
        const nextSegment = startSegment(bucket, playlistKey, lane, bucket.hasCycle)
        segments.push(nextSegment)
        latestByLane.set(laneKey, nextSegment)
      }
    }
  }

  return segments
}

const timelineSegments = makeTimelineSegments(buckets)
const timelineSvgDefs = `
  <symbol id="cycle-start" viewBox="0 0 12 12">
    <circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" stroke-width="2" />
    <path d="M8.5 2.8 10 2.2 10.1 3.9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
  </symbol>
`

const collectedDuration = computed(() => formatElapsed(COLLECTED_BUCKETS * BUCKET_SECONDS))
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <section class="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-6 py-6">
      <header class="flex items-end justify-between gap-4">
        <div class="flex flex-col gap-1">
          <h1 class="text-2xl font-semibold tracking-tight">诊断图表原型</h1>
          <p class="text-sm text-muted-foreground">
            120 个横向点 · Area 全量播单 · Top5 正常显示 · Timeline 播单池槽位
          </p>
        </div>
        <div class="rounded-md border bg-card px-3 py-2 text-sm text-muted-foreground">
          已收集 {{ collectedDuration }}
        </div>
      </header>

      <section class="rounded-lg border bg-card p-5 text-card-foreground">
        <div class="mb-3 flex items-center justify-between gap-4">
          <div>
            <h2 class="text-base font-semibold">Playlist Score 堆叠面积图</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              固定窗口按 2 小时理解，左侧留出 warmup 空白；Top5 外播单压缩为细微面积。
            </p>
          </div>
          <p class="text-sm text-muted-foreground">无 y 轴，悬停读取具体 score</p>
        </div>

        <ChartContainer
          :config="chartConfig"
          class="h-[520px] w-full [--vis-area-cursor:pointer] [--vis-area-fill-opacity:0.5] [--vis-area-hover-fill-opacity:0.8] [--vis-area-hover-stroke-width:2px] [--vis-area-stroke-opacity:0.9] [--vis-area-stroke-width:1px]"
        >
          <VisXYContainer
            :data="buckets"
            :x-domain="[0, BUCKET_COUNT - 1]"
            :y-domain="[0, undefined]"
            :auto-margin="true"
          >
            <VisArea
              :x="(bucket: Bucket) => bucket.index"
              :y="yAccessors"
              :color="scoreAreaColor"
              :line-color="scoreAreaLineColor"
              :opacity="scoreAreaOpacity"
              curve-type="basis"
              :line="true"
              :line-width="1"
              cursor="pointer"
            />
            <VisAxis
              :type="AxisType.X"
              :position="Position.Bottom"
              :tick-values="xTicks"
              :tick-format="formatAxisTick"
              :grid-line="false"
              :domain-line="false"
              :tick-line="false"
            />
          </VisXYContainer>
        </ChartContainer>

        <div class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <div v-for="item in playlists" :key="item.key" class="flex items-center gap-2">
            <span class="size-3 rounded-sm" :style="{ backgroundColor: item.color }" />
            <span>{{ item.label }}</span>
          </div>
        </div>
      </section>

      <section class="rounded-lg border bg-card p-5 text-card-foreground">
        <div class="mb-3 flex items-center justify-between gap-4">
          <div>
            <h2 class="text-base font-semibold">Decide Active Playlists Timeline</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              三条槽位 lane 表示播单池容量；同一 lane 可随时间换成不同播单颜色。
            </p>
          </div>
          <div class="text-sm text-muted-foreground">CYCLE 用 segment 起点标记，blocker 走悬停</div>
        </div>

        <ChartContainer
          :config="chartConfig"
          class="h-[132px] w-full [--vis-timeline-cursor:pointer] [--vis-timeline-label-font-size:11px] [--vis-timeline-line-stroke-width:1px] [--vis-timeline-row-background-opacity:0.55] [--vis-timeline-row-even-fill-color:var(--muted)] [--vis-timeline-row-odd-fill-color:var(--muted)]"
        >
          <VisXYContainer
            :data="timelineSegments"
            :svg-defs="timelineSvgDefs"
            :x-domain="[0, BUCKET_COUNT - 1]"
            :auto-margin="true"
          >
            <VisTimeline
              :x="(segment: TimelineSegment) => segment.start"
              :length="(segment: TimelineSegment) => segment.duration"
              :type="(segment: TimelineSegment) => segment.lane"
              :color="(segment: TimelineSegment) => getPlaylistMeta(segment.playlistKey).color"
              :lineWidth="10"
              :rowHeight="26"
              :lineCap="true"
              :showLabels="true"
              :rowLabelFormatter="(key: string) => key.replace('pool-', '槽位 ')"
              :cursor="() => 'pointer'"
              :lineStartIcon="(segment: TimelineSegment) => (segment.startsWithCycle ? '#cycle-start' : '')"
              :lineStartIconColor="(segment: TimelineSegment) => getPlaylistMeta(segment.playlistKey).color"
              :lineStartIconSize="14"
              :lineStartIconArrangement="Arrangement.Outside"
            />
            <VisAxis
              :type="AxisType.X"
              :position="Position.Bottom"
              :tick-values="xTicks"
              :tick-format="formatAxisTick"
              :grid-line="false"
              :domain-line="false"
              :tick-line="false"
            />
          </VisXYContainer>
        </ChartContainer>

        <div class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
          <span>同色连续：同一播单保持 active</span>
          <span>换色：播单池变化</span>
          <span>起点标记：CYCLE 后 segment</span>
          <span>
            示例 blocker：
            {{ timelineSegments.filter((segment) => getBlockerLabel(segment.blockers)).length }} 段可悬停查看
          </span>
        </div>
      </section>
    </section>
  </main>
</template>
