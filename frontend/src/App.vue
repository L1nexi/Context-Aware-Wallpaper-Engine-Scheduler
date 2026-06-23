<script setup lang="ts">
import { useBuckets } from '@/composables/useBuckets'
import MultiLineChart from '@/features/diagnostic/MultiLineChart.vue'

const { data, aggregated, viewportTimeRange } = useBuckets()
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <section class="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-6 py-6">
      <header class="flex items-end justify-between gap-4">
        <div class="flex flex-col gap-1">
          <h1 class="text-2xl font-semibold tracking-tight">Match 分数可视化</h1>
          <p class="text-sm text-muted-foreground">
            真实运行数据 · 幂函数变换
          </p>
        </div>
        <div class="rounded-md border bg-card px-3 py-2 text-sm text-muted-foreground">
          {{ data.length }} raw → {{ aggregated.length }} agg · {{ viewportTimeRange }}
        </div>
      </header>

      <MultiLineChart />
    </section>
  </main>
</template>
