<script setup lang="ts">
import { computed, ref } from 'vue'
import { VisArea, VisAxis, VisXYContainer } from '@unovis/vue'
import { AxisType, CurveType, Position } from '@unovis/ts'
import type { ChartConfig } from '@/components/ui/chart'
import { ChartContainer } from '@/components/ui/chart'

const BUCKET_COUNT = 120
const REST_FIXED_SCORE = 0.24

const topScoreSeries = [
  { key: 'rainy', label: '雨落时分', color: '#2f7d8c' },
  { key: 'focus', label: '深度专注', color: '#4d6fd9' },
  { key: 'night', label: '夜间低语', color: '#6d5bd0' },
  { key: 'summer', label: '夏日余温', color: '#d18b2c' },
  { key: 'casual', label: '闲适日常', color: '#6aa26f' },
] as const

const chartSeries = [
  { key: 'rest', label: '其余', color: '#c7cbd1' },
  ...topScoreSeries,
] as const

type SeriesKey = (typeof chartSeries)[number]['key']

interface Bucket {
  index: number
  secondsFromStart: number
  scores: Record<SeriesKey, number>
  rawRest: number
  displayRest: number
  activePool: SeriesKey[] | null
  hasSwitch: boolean
  hasCycle: boolean
  blockers: Partial<Record<'cooldown' | 'fullscreen' | 'cpu' | 'idle', number>>
}

const chartConfig = Object.fromEntries(
  chartSeries.map((item) => [item.key, { label: item.label, color: item.color }]),
) satisfies ChartConfig

const railHeight = ref(44)

function wave(index: number, phase: number, amplitude: number): number {
  return Math.sin(index / 11 + phase) * amplitude + Math.cos(index / 23 + phase * 0.7) * amplitude
}

function smoothStep(edge0: number, edge1: number, value: number): number {
  const x = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)))
  return x * x * (3 - 2 * x)
}

function smoothWindow(index: number, start: number, end: number, edge = 8): number {
  return smoothStep(start - edge, start + edge, index) * (1 - smoothStep(end - edge, end + edge, index))
}

function makeBucket(index: number): Bucket {
  const rainy = 0.52 + wave(index, 0.4, 0.08) + smoothWindow(index, 36, 82, 9) * 0.18
  const focus = 0.48 + wave(index, 1.7, 0.07) + smoothWindow(index, 14, 55, 8) * 0.14
  const night = 0.28 + index / 280 + wave(index, 2.6, 0.055)
  const summer = 0.34 + wave(index, 3.1, 0.08)
  const casual = 0.38 + wave(index, 4.5, 0.06) + smoothStep(84, 112, index) * 0.16
  const rawRest =
    0.76 +
    Math.sin(index / 13) * 0.13 +
    smoothWindow(index, 31, 47, 7) * 0.28 +
    smoothStep(88, 116, index) * 0.18

  const top5 = {
    rainy: Math.max(0.02, rainy),
    focus: Math.max(0.02, focus),
    night: Math.max(0.02, night),
    summer: Math.max(0.02, summer),
    casual: Math.max(0.02, casual),
  }
  const hasSwitch = index === 36 || index === 74
  const hasCycle = !hasSwitch && (index === 21 || index === 52 || index === 103)

  let activePool: SeriesKey[] | null = ['rainy', 'focus']
  if (index >= 36 && index < 74) activePool = ['rainy', 'night', 'summer']
  if (index >= 74) activePool = ['casual', 'night']
  if (hasSwitch) activePool = null

  const blockers: Bucket['blockers'] = {}
  if (index >= 40 && index <= 48) blockers.cooldown = 60
  if (index >= 64 && index <= 69) blockers.fullscreen = 42
  if (index >= 94 && index <= 99) blockers.cpu = 38

  return {
    index,
    secondsFromStart: index * 60,
    scores: {
      rest: REST_FIXED_SCORE,
      ...top5,
    },
    rawRest,
    displayRest: REST_FIXED_SCORE,
    activePool,
    hasSwitch,
    hasCycle,
    blockers,
  }
}

const buckets = Array.from({ length: BUCKET_COUNT }, (_, index) => makeBucket(index))
const yAccessors = chartSeries.map((item) => (bucket: Bucket) => bucket.scores[item.key])
const totalRawRest = buckets.reduce((sum, bucket) => sum + bucket.rawRest, 0)
const totalDisplayRest = buckets.reduce((sum, bucket) => sum + bucket.displayRest, 0)
const restCompressionRatio = totalDisplayRest / totalRawRest
const xTicks = [0, 29, 59, 89, 119]

const stackedAreaColor = (_areaData: Bucket[], stackIndex?: number): string =>
  chartSeries[stackIndex ?? 0]?.color ?? chartSeries[chartSeries.length - 1].color

const stackedAreaOpacity = (_areaData: Bucket[], stackIndex?: number): number =>
  chartSeries[stackIndex ?? 0]?.key === 'rest' ? 1 : 0.92

function formatElapsed(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours <= 0) return `${minutes} 分`
  return `${hours} 小时 ${minutes.toString().padStart(2, '0')} 分`
}

function formatAxisTick(value: number | Date): string {
  if (value instanceof Date) return ''
  return formatElapsed(value * 60)
}

function getTrackBackground(bucket: Bucket): string {
  if (bucket.hasSwitch || !bucket.activePool) {
    return 'repeating-linear-gradient(135deg, hsl(0 0% 18%) 0 6px, hsl(0 0% 34%) 6px 12px)'
  }
  const step = 100 / bucket.activePool.length
  const stops = bucket.activePool
    .map((key, index) => {
      const color = chartSeries.find((item) => item.key === key)?.color ?? '#c7cbd1'
      const start = index * step
      const end = (index + 1) * step
      return `${color} ${start}% ${end}%`
    })
    .join(', ')
  return `linear-gradient(to bottom, ${stops})`
}

function getBlockerLabel(bucket: Bucket): string {
  const labels = Object.entries(bucket.blockers).map(([type, seconds]) => {
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

const railHeightOptions = [36, 44, 52]
const restStats = computed(
  () =>
    `其余原始总量 ${totalRawRest.toFixed(1)}，底部固定显示 ${totalDisplayRest.toFixed(1)}，约 ${(restCompressionRatio * 100).toFixed(0)}%`,
)
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <section class="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-6 py-6">
      <header class="flex items-end justify-between gap-4">
        <div class="flex flex-col gap-1">
          <h1 class="text-2xl font-semibold tracking-tight">诊断图表原型</h1>
          <p class="text-sm text-muted-foreground">
            120 个横向点 · Top5 原始分数 · 其余固定底座 · Decide 轨道高度可切换
          </p>
        </div>
        <div class="flex items-center gap-2 text-sm">
          <span class="text-muted-foreground">轨道高度</span>
          <button
            v-for="height in railHeightOptions"
            :key="height"
            type="button"
            class="rounded-md border px-3 py-1.5 font-medium"
            :class="height === railHeight ? 'border-primary bg-primary text-primary-foreground' : 'bg-card'"
            @click="railHeight = height"
          >
            {{ height }}px
          </button>
        </div>
      </header>

      <section class="rounded-lg border bg-card p-5 text-card-foreground">
        <div class="mb-3 flex items-center justify-between gap-4">
          <div>
            <h2 class="text-base font-semibold">Playlist Score 堆叠面积图</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              目标窗口按 2 小时理解，当前每点约 1 分钟。这里使用 mock 数据验证密度。
            </p>
          </div>
          <p class="text-sm text-muted-foreground">{{ restStats }}</p>
        </div>

        <ChartContainer :config="chartConfig" class="h-[520px] w-full">
          <VisXYContainer
            :data="buckets"
            :x-domain="[0, BUCKET_COUNT - 1]"
            :y-domain="[0, undefined]"
            :auto-margin="true"
          >
            <VisArea
              :x="(bucket: Bucket) => bucket.index"
              :y="yAccessors"
              :color="stackedAreaColor"
              :opacity="stackedAreaOpacity"
              :curve-type="CurveType.MonotoneX"
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
            <VisAxis
              :type="AxisType.Y"
              :position="Position.Left"
              :num-ticks="4"
              :tick-line="false"
              :domain-line="false"
            />
          </VisXYContainer>
        </ChartContainer>

        <div class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <div v-for="item in chartSeries" :key="item.key" class="flex items-center gap-2">
            <span class="size-3 rounded-sm" :style="{ backgroundColor: item.color }" />
            <span :class="item.key === 'rest' ? 'text-muted-foreground' : ''">
              {{ item.label }}
            </span>
          </div>
        </div>
      </section>

      <section class="rounded-lg border bg-card p-5 text-card-foreground">
        <div class="mb-3 flex items-center justify-between gap-4">
          <div>
            <h2 class="text-base font-semibold">Decide Active Playlists 轨道</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              同一桶内发生 SWITCH 时不声明唯一 Active，使用斜纹块；CYCLE 用顶部短线标记。
            </p>
          </div>
          <div class="text-sm text-muted-foreground">当前高度 {{ railHeight }}px</div>
        </div>

        <div
          class="grid w-full overflow-hidden rounded-md border bg-muted/30"
          :style="{ gridTemplateColumns: `repeat(${BUCKET_COUNT}, minmax(0, 1fr))`, height: `${railHeight}px` }"
        >
          <div
            v-for="bucket in buckets"
            :key="bucket.index"
            class="relative min-w-0 border-r border-background/60 last:border-r-0"
            :style="{ background: getTrackBackground(bucket) }"
            :title="`${formatElapsed(bucket.secondsFromStart)} ${getBlockerLabel(bucket)}`"
          >
            <span
              v-if="bucket.hasCycle"
              class="absolute left-1/2 top-1 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-foreground"
            />
            <span
              v-if="getBlockerLabel(bucket)"
              class="absolute bottom-1 left-1/2 h-1 w-4 -translate-x-1/2 rounded-full bg-background/80"
            />
          </div>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
          <span>斜纹：SWITCH</span>
          <span>顶部点：CYCLE</span>
          <span>底部短线：该桶存在 blocker，悬停看类型和时长</span>
        </div>
      </section>
    </section>
  </main>
</template>
