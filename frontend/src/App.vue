<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { ApiError, getProfile } from "@/api/profile"

type AppMode = "loading" | "setup" | "settings" | "unavailable"
type Locale = "zh" | "en"

const locale: Locale = new URLSearchParams(window.location.search).get("locale") === "zh" ? "zh" : "en"
const messages: Record<Locale, Record<AppMode, { heading: string; description: string }>> = {
  zh: {
    loading: { heading: "正在连接 WEScheduler", description: "正在读取本地 Profile 状态。" },
    setup: {
      heading: "开始设置 WEScheduler",
      description: "首次启动环境已就绪，可以开始配置 Wallpaper Engine、天气与场景绑定。",
    },
    settings: { heading: "WEScheduler 设置", description: "当前 Profile 已载入，可以进入设置编辑流程。" },
    unavailable: { heading: "无法连接到 WEScheduler", description: "请确认 WEScheduler 主程序仍在运行。" },
  },
  en: {
    loading: { heading: "Connecting to WEScheduler", description: "Reading the local Profile state." },
    setup: {
      heading: "Set up WEScheduler",
      description: "First-run setup is ready for Wallpaper Engine, weather, and Scene assignments.",
    },
    settings: { heading: "WEScheduler Settings", description: "The current Profile is ready to edit." },
    unavailable: { heading: "WEScheduler is unavailable", description: "Make sure WEScheduler is still running." },
  },
}

const mode = ref<AppMode>("loading")
const detail = ref("")
const copy = computed(() => messages[locale][mode.value])

document.documentElement.lang = locale === "zh" ? "zh-CN" : "en"
document.title = locale === "zh" ? "WEScheduler 设置" : "WEScheduler Setup"

onMounted(async () => {
  try {
    mode.value = (await getProfile()) === null ? "setup" : "settings"
  } catch (error) {
    mode.value = "unavailable"
    detail.value = error instanceof ApiError ? error.message : locale === "zh" ? "发生未知错误。" : "Unknown error."
  }
})
</script>

<template>
  <main class="flex min-h-screen items-center justify-center bg-background px-6 py-12 text-foreground">
    <section class="flex max-w-xl flex-col gap-3 text-center" aria-live="polite">
      <p class="text-sm font-medium text-muted-foreground">WEScheduler</p>
      <h1 class="text-3xl font-semibold tracking-tight">{{ copy.heading }}</h1>
      <p class="text-balance text-muted-foreground">{{ detail || copy.description }}</p>
    </section>
  </main>
</template>
