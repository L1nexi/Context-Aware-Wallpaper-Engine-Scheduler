<script setup lang="ts">
import { computed, ref } from 'vue'
import { VisArea, VisAxis, VisXYContainer } from '@unovis/vue'
import { AxisType, Position } from '@unovis/ts'
import type { ChartConfig } from '@/components/ui/chart'
import { ChartContainer } from '@/components/ui/chart'
import { Slider } from '@/components/ui/slider'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useBuckets, playlists, type PlaylistKey } from '@/composables/useBuckets'

const {
  aggregated,
  viewport,
  viewportStart,
  viewportSize,
  maxStart,
  aggSize,
  aggSeconds,
  powerExponent,
  applyPowerTransform,
  normalizeScores,
  formatAxisTick,
} = useBuckets()

const curveType = ref('natural')

const chartConfig = Object.fromEntries(
  playlists.map((item) => [item.key, { label: item.label, color: item.color }]),
) satisfies ChartConfig

interface DisplayBucket {
  index: number
  transformedScores: Record<PlaylistKey, number>
}

const displayBuckets = computed<DisplayBucket[]>(() => {
  const p = powerExponent.value[0]
  return viewport.value.map((raw, i) => ({
    index: i,
    transformedScores: normalizeScores(applyPowerTransform(raw.scores, p)),
  }))
})

const yAccessors = playlists.map((item) => (bucket: DisplayBucket) => bucket.transformedScores[item.key])

const xTicks = computed(() => {
  const size = viewportSize.value
  if (size <= 0) return []
  const step = Math.max(1, Math.floor(size / 6))
  return Array.from({ length: Math.ceil(size / step) }, (_, i) => i * step).filter((v) => v < size)
})

const scoreAreaColor = (_areaData: DisplayBucket[], stackIndex?: number): string =>
  playlists[stackIndex ?? 0]?.color ?? playlists[playlists.length - 1].color

const scoreAreaLineColor = (_areaData: DisplayBucket[], stackIndex?: number): string =>
  playlists[stackIndex ?? 0]?.color ?? playlists[playlists.length - 1].color

const scoreAreaOpacity = () => 0.5
</script>

<template>
  <section class="rounded-lg border bg-card p-5 text-card-foreground">
    <div class="mb-4 flex items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-semibold">Playlist Score 堆叠面积图</h2>
        <p class="mt-1 text-sm text-muted-foreground">
          {{ viewportSize }} 点 · 每点 {{ aggSeconds }}s · f(s)=s^{{ powerExponent[0].toFixed(1) }} · {{ curveType }}
        </p>
      </div>
      <p class="text-sm text-muted-foreground">高度恒定 · 悬停读取比例</p>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16">曲线</label>
      <ToggleGroup v-model="curveType" type="single" variant="outline" size="sm">
        <ToggleGroupItem value="natural">natural</ToggleGroupItem>
        <ToggleGroupItem value="monotoneX">monotoneX</ToggleGroupItem>
        <ToggleGroupItem value="basis">basis</ToggleGroupItem>
      </ToggleGroup>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16">窗口</label>
      <ToggleGroup v-model="viewportSize" type="single" variant="outline" size="sm">
        <ToggleGroupItem :value="240">240</ToggleGroupItem>
        <ToggleGroupItem :value="120">120</ToggleGroupItem>
        <ToggleGroupItem :value="60">60</ToggleGroupItem>
        <ToggleGroupItem :value="30">30</ToggleGroupItem>
        <ToggleGroupItem :value="15">15</ToggleGroupItem>
      </ToggleGroup>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16">聚合</label>
      <ToggleGroup v-model="aggSize" type="single" variant="outline" size="sm">
        <ToggleGroupItem :value="1">1</ToggleGroupItem>
        <ToggleGroupItem :value="2">2</ToggleGroupItem>
        <ToggleGroupItem :value="3">3</ToggleGroupItem>
        <ToggleGroupItem :value="4">4</ToggleGroupItem>
        <ToggleGroupItem :value="5">5</ToggleGroupItem>
        <ToggleGroupItem :value="8">8</ToggleGroupItem>
      </ToggleGroup>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16">幂指数 p</label>
      <Slider
        v-model="powerExponent"
        :min="0"
        :max="5"
        :step="0.1"
        class="w-[200px]"
      />
      <span class="text-sm font-mono text-foreground tabular-nums w-12">{{ powerExponent[0].toFixed(1) }}</span>
    </div>

    <div class="mb-4 flex items-center gap-4">
      <label class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16">位置</label>
      <Slider
        v-model="viewportStart"
        :min="0"
        :max="maxStart"
        :step="1"
        class="flex-1"
      />
      <span class="text-sm font-mono text-foreground tabular-nums w-24">
        {{ viewportStart[0] }}-{{ Math.min(viewportStart[0] + viewportSize, aggregated.length) }}
      </span>
    </div>

    <ChartContainer
      :config="chartConfig"
      class="h-[520px] w-full [--vis-area-cursor:pointer] [--vis-area-fill-opacity:0.5] [--vis-area-hover-fill-opacity:0.8] [--vis-area-hover-stroke-width:2px] [--vis-area-stroke-opacity:0.9] [--vis-area-stroke-width:1px]"
    >
      <VisXYContainer
        :data="displayBuckets"
        :x-domain="[0, viewportSize - 1]"
        :y-domain="[0, 1]"
        :auto-margin="true"
      >
        <VisArea
          :x="(bucket: DisplayBucket) => bucket.index"
          :y="yAccessors"
          :color="scoreAreaColor"
          :line-color="scoreAreaLineColor"
          :opacity="scoreAreaOpacity"
          :curve-type="curveType"
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
</template>
