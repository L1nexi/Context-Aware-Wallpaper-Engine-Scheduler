<script setup lang="ts">
import { TriangleAlertIcon } from "@lucide/vue"
import { onMounted, ref } from "vue"

import type { Locale, Profile } from "@/api/profile"
import { ApiError, getProfile } from "@/api/profile"
import SetupWorkspace from "@/components/setup/SetupWorkspace.vue"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Toaster } from "@/components/ui/sonner"
import { COPY } from "@/setup/copy"

type AppState = "loading" | "ready" | "unavailable"

const initialLocale: Locale = new URLSearchParams(window.location.search).get("locale") === "zh" ? "zh" : "en"
const state = ref<AppState>("loading")
const profile = ref<Profile | null>(null)
const detail = ref("")

document.documentElement.lang = initialLocale === "zh" ? "zh-CN" : "en"
document.title = initialLocale === "zh" ? "WEScheduler 设置" : "WEScheduler Settings"

async function loadProfile(): Promise<void> {
  state.value = "loading"
  detail.value = ""
  try {
    profile.value = await getProfile()
    state.value = "ready"
  } catch (error) {
    state.value = "unavailable"
    detail.value = error instanceof ApiError ? error.message : COPY[initialLocale].errors.generic
  }
}

onMounted(loadProfile)
</script>

<template>
  <SetupWorkspace
    v-if="state === 'ready'"
    :initial-profile="profile"
    :initial-locale="initialLocale"
  />

  <main v-else class="grid min-h-[100dvh] place-items-center bg-muted/40 p-6 text-foreground">
    <Card v-if="state === 'loading'" class="w-full max-w-lg">
      <CardHeader>
        <CardTitle>{{ COPY[initialLocale].loading.title }}</CardTitle>
        <CardDescription>{{ COPY[initialLocale].loading.description }}</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-col gap-4">
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-24 w-full" />
        <Skeleton class="h-10 w-2/3" />
      </CardContent>
    </Card>

    <Card v-else class="w-full max-w-lg">
      <CardHeader>
        <CardTitle>{{ COPY[initialLocale].unavailable.title }}</CardTitle>
        <CardDescription>{{ COPY[initialLocale].unavailable.description }}</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-col gap-4">
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>{{ COPY[initialLocale].unavailable.title }}</AlertTitle>
          <AlertDescription>{{ detail }}</AlertDescription>
        </Alert>
        <Button class="self-start" @click="loadProfile">{{ COPY[initialLocale].unavailable.retry }}</Button>
      </CardContent>
    </Card>
  </main>

  <Toaster position="top-center" />
</template>
