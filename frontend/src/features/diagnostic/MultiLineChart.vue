<script setup lang="ts">
import { computed, ref } from "vue";
import { VisLine, VisXYContainer } from "@unovis/vue";
import type { ChartConfig } from "@/components/ui/chart";
import { ChartContainer } from "@/components/ui/chart";
import { Slider } from "@/components/ui/slider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  useBuckets,
  playlists,
  type PlaylistKey,
} from "@/composables/useBuckets";

const {
  aggregated,
  viewport,
  viewportStart,
  viewportSize,
  maxStart,
  aggSize,
  aggSeconds,
} = useBuckets();

const curveType = ref("monotoneX");
const topN = ref(2);
const ghostOpacity = ref([0.6]);

const chartConfig = Object.fromEntries(
  playlists.map((item) => [item.key, { label: item.label, color: item.color }]),
) satisfies ChartConfig;

interface DisplayBucket {
  index: number;
  scores: Record<PlaylistKey, number>;
}

const displayBuckets = computed<DisplayBucket[]>(() => {
  return viewport.value.map((raw, i) => ({
    index: i,
    scores: raw.scores,
  }));
});

/**
 * 窗口内全 Top N：每个 tick 取 Top N，所有 tick 的并集。
 * 即窗口内任一时刻进过 Top N 的播单都是焦点线。
 */
const focusPlaylists = computed(() => {
  const buckets = displayBuckets.value;
  const n = topN.value;
  const focusKeys = new Set<PlaylistKey>();

  for (const bucket of buckets) {
    const sorted = [...playlists].sort(
      (a, b) => (bucket.scores[b.key] ?? 0) - (bucket.scores[a.key] ?? 0),
    );
    for (const p of sorted.slice(0, n)) {
      focusKeys.add(p.key);
    }
  }

  return playlists.filter((p) => focusKeys.has(p.key));
});

const ghostPlaylists = computed(() =>
  playlists.filter((p) => !focusPlaylists.value.includes(p)),
);

function ghostColor(): string {
  const a = ghostOpacity.value[0];
  return `rgba(136,136,136,${a})`;
}
</script>

<template>
  <section class="rounded-lg border bg-card p-5 text-card-foreground">
    <div class="mb-4 flex items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-semibold">Playlist Score 趋势</h2>
        <p class="mt-1 text-sm text-muted-foreground">
          {{ viewportSize }} 点 · 每点 {{ aggSeconds }}s · {{ curveType }}
        </p>
      </div>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label
        class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16"
        >曲线</label
      >
      <ToggleGroup
        v-model="curveType"
        type="single"
        variant="outline"
        size="sm"
      >
        <ToggleGroupItem value="natural">natural</ToggleGroupItem>
        <ToggleGroupItem value="monotoneX">monotoneX</ToggleGroupItem>
      </ToggleGroup>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label
        class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16"
        >Top N</label
      >
      <ToggleGroup v-model="topN" type="single" variant="outline" size="sm">
        <ToggleGroupItem :value="2">2</ToggleGroupItem>
        <ToggleGroupItem :value="3">3</ToggleGroupItem>
        <ToggleGroupItem :value="4">4</ToggleGroupItem>
      </ToggleGroup>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label
        class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16"
        >窗口</label
      >
      <ToggleGroup
        v-model="viewportSize"
        type="single"
        variant="outline"
        size="sm"
      >
        <ToggleGroupItem :value="30">30</ToggleGroupItem>
        <ToggleGroupItem :value="20">20</ToggleGroupItem>
        <ToggleGroupItem :value="15">15</ToggleGroupItem>
        <ToggleGroupItem :value="10">10</ToggleGroupItem>
      </ToggleGroup>
    </div>

    <div class="mb-3 flex items-center gap-4">
      <label
        class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16"
        >聚合</label
      >
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
      <label
        class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16"
        >位置</label
      >
      <Slider
        v-model="viewportStart"
        :min="0"
        :max="maxStart"
        :step="1"
        class="flex-1"
      />
      <span class="text-sm font-mono text-foreground tabular-nums w-24">
        {{ viewportStart[0] }}-{{
          Math.min(viewportStart[0] + viewportSize, aggregated.length)
        }}
      </span>
    </div>

    <div class="mb-4 flex items-center gap-4">
      <label
        class="text-sm font-medium text-muted-foreground whitespace-nowrap w-16"
        >幽灵透明度</label
      >
      <Slider
        v-model="ghostOpacity"
        :min="0"
        :max="1"
        :step="0.05"
        class="w-[200px]"
      />
      <span class="text-sm font-mono text-foreground tabular-nums w-12">{{
        ghostOpacity[0].toFixed(2)
      }}</span>
    </div>

    <ChartContainer :config="chartConfig" class="h-[520px] w-full">
      <VisXYContainer
        :data="displayBuckets"
        :x-domain="[0, viewportSize - 1]"
        :auto-margin="true"
      >
        <!-- Focus lines: Top 4, colored, 2px -->
        <VisLine
          :x="(d: DisplayBucket) => d.index"
          :y="focusPlaylists.map((p) => (d: DisplayBucket) => d.scores[p.key])"
          :color="(_d: DisplayBucket, i: number) => focusPlaylists[i].color"
          :curve-type="curveType"
          :line-width="2"
        />
        <!-- Ghost lines: remaining, gray, 1px, dashed -->
        <VisLine
          :x="(d: DisplayBucket) => d.index"
          :y="ghostPlaylists.map((p) => (d: DisplayBucket) => d.scores[p.key])"
          :color="ghostColor"
          :curve-type="curveType"
          :line-width="1"
          :line-dash-array="[4, 4]"
        />
      </VisXYContainer>
    </ChartContainer>
  </section>
</template>
