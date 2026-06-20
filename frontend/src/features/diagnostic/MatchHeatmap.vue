<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Slider } from '@/components/ui/slider'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useBuckets, playlists } from '@/composables/useBuckets'

const {
  data,
  aggregated,
  viewport,
  viewportStart,
  viewportSize,
  maxStart,
  aggSize,
  aggSeconds,
  powerExponent,
  applyPowerTransform,
  formatTimestamp,
  viewportTimeRange,
} = useBuckets()

type ColorMode = 'theme' | 'representative'
const colorMode = ref<ColorMode>('theme')

// oklch L range for brightness mapping
const L_MIN = 0.3
const L_MAX = 0.95

// Fixed chroma for heatmap (primary's chroma is too low, ~0.012)
const HEATMAP_CHROMA = 0.12

// Read --primary CSS variable and extract oklch hue
const primaryHue = ref(250)

function readPrimaryColor() {
  const style = getComputedStyle(document.documentElement)
  const primary = style.getPropertyValue('--primary').trim()
  const match = primary.match(/oklch\(([\d.]+)%?\s+([\d.]+)\s+([\d.]+)\)/)
  if (match) {
    primaryHue.value = parseFloat(match[3])
  }
}

onMounted(() => {
  readPrimaryColor()
})

// Representative color hues (evenly spaced)
const representativeHues = playlists.map((_, i) => (i * 360) / playlists.length)

// Render heatmap to canvas (1 pixel per data cell, CSS scaling handles interpolation)
function renderHeatmap(canvas: HTMLCanvasElement) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const buckets = viewport.value
  if (buckets.length === 0) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    return
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const p = powerExponent.value[0]

  // First pass: find min/max scores in viewport for relative normalization
  let minScore = Infinity
  let maxScore = -Infinity
  for (const bucket of buckets) {
    const transformed = applyPowerTransform(bucket.scores, p)
    for (const pl of playlists) {
      const s = transformed[pl.key] ?? 0
      minScore = Math.min(minScore, s)
      maxScore = Math.max(maxScore, s)
    }
  }
  const range = maxScore - minScore || 1

  // Second pass: render with viewport-relative normalization
  for (let x = 0; x < buckets.length; x++) {
    const transformed = applyPowerTransform(buckets[x].scores, p)

    for (let y = 0; y < playlists.length; y++) {
      const playlist = playlists[y]
      const score = transformed[playlist.key] ?? 0
      const normalized = (score - minScore) / range
      const l = L_MIN + normalized * (L_MAX - L_MIN)

      const chroma = colorMode.value === 'theme' ? HEATMAP_CHROMA : 0.12
      const hue = colorMode.value === 'theme' ? primaryHue.value : representativeHues[y]

      ctx.fillStyle = `oklch(${l} ${chroma} ${hue})`
      ctx.fillRect(x, y, 1, 1)
    }
  }
}

const canvasRef = ref<HTMLCanvasElement | null>(null)

async function redraw() {
  await nextTick()
  if (canvasRef.value) {
    renderHeatmap(canvasRef.value)
  }
}

watch([viewport, powerExponent, colorMode, primaryHue], redraw, { deep: true })
onMounted(redraw)

// X-axis ticks
const xTicks = computed(() => {
  const buckets = viewport.value
  if (buckets.length === 0) return []
  const step = Math.max(1, Math.floor(buckets.length / 6))
  return Array.from({ length: Math.ceil(buckets.length / step) }, (_, i) => {
    const idx = i * step
    return {
      position: idx / buckets.length,
      label: formatTimestamp(buckets[idx]?.tsStart ?? 0),
    }
  }).filter((t) => t.position < 1)
})
</script>

<template>
  <section class="rounded-lg border bg-card p-5 text-card-foreground">
    <div class="mb-4 flex items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-semibold">Match 热力图</h2>
        <p class="mt-1 text-sm text-muted-foreground">
          {{ viewportSize }} 点 · 每点 {{ aggSeconds }}s · f(s)=s^{{ powerExponent[0].toFixed(1) }} · {{ colorMode === 'theme' ? '主题色' : '代表色' }}
        </p>
      </div>
      <div class="rounded-md border bg-card px-3 py-2 text-sm text-muted-foreground">
        {{ data.length }} raw → {{ aggregated.length }} agg · {{ viewportTimeRange }}
      </div>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16">颜色</label>
      <ToggleGroup v-model="colorMode" type="single" variant="outline" size="sm">
        <ToggleGroupItem value="theme">主题色</ToggleGroupItem>
        <ToggleGroupItem value="representative">代表色</ToggleGroupItem>
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

    <div class="relative">
      <!-- Y-axis labels -->
      <div class="absolute left-0 top-0 bottom-0 flex flex-col justify-between py-1 pr-3 text-xs text-muted-foreground">
        <span v-for="item in playlists" :key="item.key">{{ item.label }}</span>
      </div>

      <!-- Heatmap canvas -->
      <div class="ml-20">
        <canvas
          ref="canvasRef"
          :width="viewport.length"
          :height="playlists.length"
          class="w-full h-[400px] [image-rendering:auto]"
        />
      </div>

      <!-- X-axis labels -->
      <div class="ml-20 relative h-6 mt-1">
        <span
          v-for="tick in xTicks"
          :key="tick.position"
          class="absolute text-xs text-muted-foreground -translate-x-1/2"
          :style="{ left: `${tick.position * 100}%` }"
        >
          {{ tick.label }}
        </span>
      </div>
    </div>

    <!-- Color legend -->
    <div class="mt-4 flex items-center gap-4">
      <span class="text-sm text-muted-foreground">亮度映射：</span>
      <div class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">0</span>
        <div
          class="h-4 w-32 rounded-sm"
          :style="{
            background: `linear-gradient(to right, oklch(${L_MIN} ${HEATMAP_CHROMA} ${primaryHue}), oklch(${L_MAX} ${HEATMAP_CHROMA} ${primaryHue}))`
          }"
        />
        <span class="text-xs text-muted-foreground">1</span>
      </div>
    </div>
  </section>
</template>
