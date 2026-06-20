<script setup lang="ts">
import { ref } from 'vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useBuckets } from '@/composables/useBuckets'
import StackedAreaChart from '@/features/diagnostic/StackedAreaChart.vue'
import MatchHeatmap from '@/features/diagnostic/MatchHeatmap.vue'

const { data, aggregated, viewportTimeRange } = useBuckets()

const activeTab = ref('stacked-area')
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <section class="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-6 py-6">
      <header class="flex items-end justify-between gap-4">
        <div class="flex flex-col gap-1">
          <h1 class="text-2xl font-semibold tracking-tight">Match 分数可视化</h1>
          <p class="text-sm text-muted-foreground">
            真实运行数据 · 幂函数变换 · 相对比例归一化
          </p>
        </div>
        <div class="rounded-md border bg-card px-3 py-2 text-sm text-muted-foreground">
          {{ data.length }} raw → {{ aggregated.length }} agg · {{ viewportTimeRange }}
        </div>
      </header>

      <Tabs v-model="activeTab" default-value="stacked-area">
        <TabsList>
          <TabsTrigger value="stacked-area">堆叠面积图</TabsTrigger>
          <TabsTrigger value="heatmap">热力图</TabsTrigger>
        </TabsList>

        <TabsContent value="stacked-area">
          <StackedAreaChart />
        </TabsContent>

        <TabsContent value="heatmap">
          <MatchHeatmap />
        </TabsContent>
      </Tabs>
    </section>
  </main>
</template>
