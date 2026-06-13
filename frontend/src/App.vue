<script setup lang="ts">
import {
  PhCheckCircle,
  PhClock,
  PhCloudSun,
  PhCpu,
  PhMoonStars,
  PhPauseCircle,
  PhPulse,
  PhStack,
} from '@phosphor-icons/vue'

const signals = [
  { label: '活动窗口', value: 'Code Review', detail: 'chrome.exe', icon: PhPulse },
  { label: '空闲时间', value: '42s', detail: '已超过 20s 阈值', icon: PhClock },
  { label: 'CPU', value: '18%', detail: '负载稳定', icon: PhCpu },
  { label: '天气', value: 'Clouds', detail: '数据新鲜', icon: PhCloudSun },
]

const policies = [
  { name: '活动策略', tag: 'focus', weight: '0.74' },
  { name: '日内时间', tag: 'night', weight: '0.42' },
  { name: '天气策略', tag: 'cloud', weight: '0.18' },
]
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <section class="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-8 lg:px-10">
      <header class="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div class="flex max-w-3xl flex-col gap-3">
          <div
            class="inline-flex w-fit items-center gap-2 rounded-full border bg-card px-3 py-1 text-sm text-muted-foreground shadow-sm"
          >
            <PhMoonStars :size="16" weight="duotone" />
            诊断预览
          </div>
          <div>
            <h1 class="text-3xl font-semibold tracking-tight md:text-5xl">
              Context Aware WE Scheduler
            </h1>
            <p class="mt-3 max-w-2xl text-base leading-7 text-muted-foreground">
              一个静态示例界面，用来确认前端初始化、主题变量、字体、图标和构建流程已经就绪。
            </p>
          </div>
        </div>

        <div
          class="flex w-fit items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-4 py-2 text-sm font-medium text-primary"
        >
          <PhCheckCircle :size="18" weight="fill" />
          前端可独立打开
        </div>
      </header>

      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="signal in signals"
          :key="signal.label"
          class="rounded-xl border bg-card p-5 text-card-foreground shadow-sm"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-sm text-muted-foreground">{{ signal.label }}</p>
              <p class="mt-2 text-2xl font-semibold tracking-tight">{{ signal.value }}</p>
            </div>
            <component :is="signal.icon" :size="24" class="text-primary" weight="duotone" />
          </div>
          <p class="mt-4 text-sm text-muted-foreground">{{ signal.detail }}</p>
        </article>
      </section>

      <section class="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <article class="rounded-xl border bg-card p-6 text-card-foreground shadow-sm">
          <div class="flex flex-col gap-2">
            <div class="flex items-center gap-2 text-sm font-medium text-primary">
              <PhStack :size="18" weight="duotone" />
              当前匹配
            </div>
            <h2 class="text-2xl font-semibold tracking-tight">Focus Flow</h2>
            <p class="text-sm leading-6 text-muted-foreground">
              调度器倾向保持当前播放列表池。匹配分数稳定，语义连续性仍然有效。
            </p>
          </div>

          <div class="mt-6 grid gap-3">
            <div
              v-for="policy in policies"
              :key="policy.name"
              class="flex items-center justify-between gap-4 rounded-lg border bg-muted/30 px-4 py-3"
            >
              <div>
                <p class="font-medium">{{ policy.name }}</p>
                <p class="text-sm text-muted-foreground">{{ policy.tag }}</p>
              </div>
              <span class="rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary">
                {{ policy.weight }}
              </span>
            </div>
          </div>
        </article>

        <article class="rounded-xl border bg-card p-6 text-card-foreground shadow-sm">
          <div class="flex items-center gap-2 text-sm font-medium text-primary">
            <PhPauseCircle :size="18" weight="duotone" />
            执行状态
          </div>
          <h2 class="mt-2 text-2xl font-semibold tracking-tight">Hold</h2>
          <p class="mt-3 text-sm leading-6 text-muted-foreground">
            本 tick 没有触发播放列表切换。后续会在真实 API 接入后展示完整的感知、匹配、计划、决策和执行链路。
          </p>

          <div class="mt-6 h-2 overflow-hidden rounded-full bg-muted">
            <div class="h-full w-[68%] rounded-full bg-primary" />
          </div>
          <div class="mt-3 flex justify-between text-sm text-muted-foreground">
            <span>similarity</span>
            <span>0.682</span>
          </div>
        </article>
      </section>
    </section>
  </main>
</template>
