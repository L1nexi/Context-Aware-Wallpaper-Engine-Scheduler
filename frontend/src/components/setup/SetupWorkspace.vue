<script setup lang="ts">
import type { Component } from "vue"
import {
  AppWindowIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClipboardCheckIcon,
  CloudSunIcon,
  LayersIcon,
  MapPinIcon,
  MonitorIcon,
  SlidersHorizontalIcon,
  TriangleAlertIcon,
} from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, toRef, watch } from "vue"
import { toast } from "vue-sonner"

import type { Locale, Profile, SceneCatalogItem, ValidationIssue } from "@/api/profile"
import { ApiError, applyProfile, createInitialProfile, detectLocation, getSceneCatalog, validateWeatherKey } from "@/api/profile"
import ActivityRulesStep from "@/components/setup/steps/ActivityRulesStep.vue"
import LocationStep from "@/components/setup/steps/LocationStep.vue"
import ReviewStep from "@/components/setup/steps/ReviewStep.vue"
import SceneBindingsStep from "@/components/setup/steps/SceneBindingsStep.vue"
import SchedulingStep from "@/components/setup/steps/SchedulingStep.vue"
import WallpaperStep from "@/components/setup/steps/WallpaperStep.vue"
import WeatherKeyStep from "@/components/setup/steps/WeatherKeyStep.vue"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { COPY } from "@/setup/copy"
import { evaluateSteps, STEP_ORDER, stepForIssue } from "@/setup/flow"
import type { StepId } from "@/setup/flow"
import { buildProfile, createProfileDraft, profileFingerprint, validationIssueField } from "@/setup/model"
import type { ProfileDraft } from "@/setup/model"
import { usePlaylistScan } from "@/setup/usePlaylistScan"

const props = defineProps<{
  initialProfile: Profile | null
  initialLocale: Locale
}>()

const mode = computed<"setup" | "settings">(() => props.initialProfile === null ? "setup" : "settings")
const locale = ref<Locale>(props.initialProfile?.language ?? props.initialLocale)
const copy = computed(() => COPY[locale.value])
const draft = reactive<ProfileDraft>(createProfileDraft(props.initialProfile, locale.value))
const baseline = ref(profileFingerprint(draft))
const scan = usePlaylistScan(toRef(draft, "wallpaper_engine_path"))

const currentIndex = ref(0)
const furthestIndex = ref(mode.value === "settings" ? STEP_ORDER.length - 1 : 0)
const activeStep = computed<StepId>(() => STEP_ORDER[currentIndex.value] ?? "wallpaper")
const stepError = ref<"validation" | "fieldValidation" | null>(null)
const validationIssues = ref<ValidationIssue[]>([])
const submissionFailure = shallowRef<unknown>(null)
const catalogFailure = shallowRef<unknown>(null)
const submitting = ref(false)
const locating = ref(false)
const locationDetectionStatus = ref<"idle" | "success" | "error">("idle")
const locationDetectionError = ref("")
const validatingWeather = ref(false)
const weatherValidationStatus = ref<"idle" | "success" | "error">("idle")
const weatherValidationError = ref("")
const timingOpen = ref(false)
const closeDialogOpen = ref(false)
const hasNativeBridge = ref(Boolean(window.pywebview?.api))
const sceneCatalog = ref<SceneCatalogItem[]>([])

const stepIcons: Record<StepId, Component> = {
  wallpaper: MonitorIcon,
  weather: CloudSunIcon,
  location: MapPinIcon,
  scenes: LayersIcon,
  scheduling: SlidersHorizontalIcon,
  activity: AppWindowIcon,
  review: ClipboardCheckIcon,
}
const steps = computed(() => STEP_ORDER.map((id) => ({ id, ...copy.value.steps[id], icon: stepIcons[id] })))
const evaluation = computed(() => evaluateSteps(draft, scan.ready.value, scan.usablePlaylists.value))
const allValid = computed(() => Object.values(evaluation.value.validity).every(Boolean))
const isDirty = computed(() => profileFingerprint(draft) !== baseline.value)
const progressValue = computed(() => ((currentIndex.value + 1) / STEP_ORDER.length) * 100)
const stepErrorText = computed(() => stepError.value ? copy.value.errors[stepError.value] : "")
const submissionError = computed(() => submissionFailure.value ? describeError(submissionFailure.value) : "")
const catalogError = computed(() => catalogFailure.value ? describeError(catalogFailure.value) : "")
const scanDetail = computed(() => scan.error.value ? describeScanError(scan.error.value) : "")

const issuesByStep = computed<Record<StepId, Record<string, string[]>>>(() => {
  const grouped = Object.fromEntries(STEP_ORDER.map((id) => [id, {}])) as Record<StepId, Record<string, string[]>>
  for (const issue of validationIssues.value) {
    const fields = grouped[stepForIssue(issue.path)]
    const field = validationIssueField(issue.path)
    fields[field] ??= []
    fields[field].push(copy.value.errors.issueCodes[issue.code as keyof typeof copy.value.errors.issueCodes] ?? issue.message)
  }
  return grouped
})

function isStepValid(id: StepId): boolean {
  return id === "review" ? allValid.value : evaluation.value.validity[id]
}

function clearStepFeedback(id: StepId): void {
  validationIssues.value = validationIssues.value.filter((issue) => stepForIssue(issue.path) !== id)
  if (activeStep.value === id) stepError.value = null
  submissionFailure.value = null
}

function updatePath(value: string): void {
  draft.wallpaper_engine_path = value
  clearStepFeedback("wallpaper")
}

function updateApiKey(value: string): void {
  draft.weather.api_key = value
  weatherValidationStatus.value = "idle"
  weatherValidationError.value = ""
  clearStepFeedback("weather")
}

function updateLocation(value: ProfileDraft["weather"]["location"]): void {
  draft.weather.location = value
  locationDetectionStatus.value = "idle"
  locationDetectionError.value = ""
  clearStepFeedback("location")
}

function updateScenes(value: ProfileDraft["scenes"]): void {
  draft.scenes = value
  clearStepFeedback("scenes")
}

function updateMatching(value: ProfileDraft["matching"]): void {
  draft.matching = value
  clearStepFeedback("scheduling")
}

function updateDisturbance(value: ProfileDraft["disturbance"]): void {
  draft.disturbance = value
  clearStepFeedback("scheduling")
}

function updateActivity(value: ProfileDraft["activity"]): void {
  draft.activity = value
  clearStepFeedback("activity")
}

watch(locale, (value, previous) => {
  if (previous !== undefined) draft.language = value
  document.documentElement.lang = value === "zh" ? "zh-CN" : "en"
  document.title = value === "zh" ? "WEScheduler 设置" : "WEScheduler Settings"
}, { immediate: true })

function handleBeforeUnload(event: BeforeUnloadEvent): void {
  if (!isDirty.value) return
  event.preventDefault()
}

function updateNativeBridgeAvailability(): void {
  hasNativeBridge.value = Boolean(window.pywebview?.api)
}

onMounted(async () => {
  window.addEventListener("beforeunload", handleBeforeUnload)
  window.addEventListener("pywebviewready", updateNativeBridgeAvailability)
  updateNativeBridgeAvailability()
  await loadSceneCatalog()
  await scan.scan()
})

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload)
  window.removeEventListener("pywebviewready", updateNativeBridgeAvailability)
})

async function loadSceneCatalog(): Promise<void> {
  catalogFailure.value = null
  try {
    sceneCatalog.value = await getSceneCatalog()
  } catch (error) {
    catalogFailure.value = error
  }
}

async function scanWallpaper(): Promise<void> {
  clearStepFeedback("wallpaper")
  await scan.scan()
}

async function chooseWallpaperEngine(): Promise<void> {
  if (!window.pywebview?.api) return
  const path = await window.pywebview.api.choose_wallpaper_engine()
  if (!path) return
  updatePath(path)
  await scan.scan()
}

async function openExternal(url: string): Promise<void> {
  if (window.pywebview?.api) {
    await window.pywebview.api.open_external(url)
    return
  }
  window.open(url, "_blank", "noopener,noreferrer")
}

function describeScanError(error: unknown): string {
  if (!(error instanceof ApiError)) return copy.value.errors.generic
  const messages = copy.value.errors.scanCodes as Record<string, string>
  return messages[error.payload.error] ?? error.message
}

function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) return copy.value.errors.generic
  if (error.payload.error === "profile_already_exists") return copy.value.errors.profileAlreadyExists
  if (error.payload.error === "profile_apply_timeout") return copy.value.errors.applyTimeout
  if (error.payload.error === "profile_apply_unavailable") return copy.value.errors.applyUnavailable
  if (error.payload.error === "weather_validation_unavailable") {
    return `${copy.value.errors.weatherValidationUnavailable} ${describeNetworkFailure(error)}`.trim()
  }
  if (error.payload.stage) {
    const stage = copy.value.errors.stages[error.payload.stage]
    return `${stage}: ${error.payload.detail || error.payload.error}`
  }
  return error.message || copy.value.errors.generic
}

function describeNetworkFailure(error: ApiError): string {
  const { reason, http_status: status } = error.payload
  if (reason === "http_status" && status !== undefined) {
    if (status === 429) return copy.value.errors.httpRateLimited
    if (status === 403) return copy.value.errors.httpForbidden
    if (status >= 500) return copy.value.errors.httpServerError
    return copy.value.errors.httpOther(status)
  }
  const messages = copy.value.errors.networkReasons as Record<string, string>
  return reason ? (messages[reason] ?? "") : ""
}

function describeWeatherTestError(error: unknown): string {
  if (!(error instanceof ApiError)) return copy.value.errors.generic
  const issue = error.payload.issues?.[0]
  if (issue) {
    const messages = copy.value.errors.issueCodes as Record<string, string>
    return messages[issue.code] ?? copy.value.errors.generic
  }
  if (error.payload.error === "weather_validation_unavailable") {
    return `${copy.value.errors.weatherValidationUnavailable} ${describeNetworkFailure(error)}`.trim()
  }
  return copy.value.errors.generic
}

async function testWeatherKey(): Promise<void> {
  const apiKey = draft.weather.api_key.trim()
  if (!apiKey) {
    weatherValidationStatus.value = "error"
    weatherValidationError.value = copy.value.weather.validationMissing
    return
  }
  validatingWeather.value = true
  weatherValidationStatus.value = "idle"
  try {
    await validateWeatherKey(apiKey)
    if (draft.weather.api_key.trim() === apiKey) weatherValidationStatus.value = "success"
  } catch (error) {
    if (draft.weather.api_key.trim() === apiKey) {
      weatherValidationStatus.value = "error"
      weatherValidationError.value = describeWeatherTestError(error)
    }
  } finally {
    validatingWeather.value = false
  }
}

function applyValidationIssues(error: unknown): boolean {
  if (!(error instanceof ApiError) || !error.payload.issues?.length) return false
  validationIssues.value = error.payload.issues
  const target = Math.min(...error.payload.issues.map((issue) => STEP_ORDER.indexOf(stepForIssue(issue.path))))
  currentIndex.value = target
  furthestIndex.value = Math.max(furthestIndex.value, target)
  if (error.payload.issues.some((issue) => issue.path[0] === "disturbance")) timingOpen.value = true
  stepError.value = "fieldValidation"
  submissionFailure.value = null
  return true
}

async function detectCity(): Promise<void> {
  locating.value = true
  locationDetectionStatus.value = "idle"
  locationDetectionError.value = ""
  try {
    const detected = await detectLocation()
    updateLocation(detected)
    locationDetectionStatus.value = "success"
  } catch (error) {
    locationDetectionStatus.value = "error"
    const detail = error instanceof ApiError ? describeNetworkFailure(error) : ""
    locationDetectionError.value = `${copy.value.errors.locationValidationUnavailable} ${detail}`.trim()
  } finally {
    locating.value = false
  }
}

function canNavigateTo(index: number): boolean {
  return mode.value === "settings" || index <= furthestIndex.value
}

function navigateTo(index: number): void {
  if (!canNavigateTo(index)) return
  currentIndex.value = index
  stepError.value = null
  submissionFailure.value = null
}

function goNext(): void {
  if (!isStepValid(activeStep.value)) {
    stepError.value = "validation"
    return
  }
  const next = Math.min(currentIndex.value + 1, STEP_ORDER.length - 1)
  furthestIndex.value = Math.max(furthestIndex.value, next)
  currentIndex.value = next
  stepError.value = null
}

function goBack(): void {
  currentIndex.value = Math.max(0, currentIndex.value - 1)
  stepError.value = null
}

function setLocale(value: unknown): void {
  if (value === "zh" || value === "en") locale.value = value
}

function requestClose(): void {
  if (isDirty.value) {
    closeDialogOpen.value = true
    return
  }
  void closeWindow()
}

async function closeWindow(): Promise<void> {
  if (window.pywebview?.api) await window.pywebview.api.close()
}

async function submitProfile(): Promise<void> {
  if (!allValid.value) {
    const invalidIndex = STEP_ORDER.findIndex((id) => !isStepValid(id))
    currentIndex.value = Math.max(0, invalidIndex)
    furthestIndex.value = Math.max(furthestIndex.value, currentIndex.value)
    stepError.value = "validation"
    return
  }

  submitting.value = true
  submissionFailure.value = null
  try {
    const profile = buildProfile(draft)
    const committed = mode.value === "setup" ? await createInitialProfile(profile) : await applyProfile(profile)
    Object.assign(draft, createProfileDraft(committed, locale.value))
    baseline.value = profileFingerprint(draft)
    validationIssues.value = []
    stepError.value = null
    if (mode.value === "setup") {
      toast.success(copy.value.review.setupSuccess)
      await closeWindow()
    } else {
      toast.success(copy.value.review.success)
    }
  } catch (error) {
    if (!applyValidationIssues(error)) submissionFailure.value = error
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="min-h-[100dvh] bg-muted/40 p-4 text-foreground md:p-6">
    <div class="mx-auto grid max-w-6xl gap-4 md:grid-cols-[15rem_minmax(0,1fr)]">
      <aside class="flex min-w-0 flex-col gap-5 rounded-xl bg-sidebar p-4 text-sidebar-foreground ring-1 ring-sidebar-border md:min-h-[calc(100dvh-3rem)]">
        <header class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold">{{ copy.appName }}</p>
            <p class="mt-1 text-sm text-muted-foreground">{{ copy.mode[mode] }}</p>
          </div>
          <ToggleGroup type="single" variant="outline" size="sm" :model-value="locale" aria-label="Language" @update:model-value="setLocale">
            <ToggleGroupItem value="zh" aria-label="中文">中</ToggleGroupItem>
            <ToggleGroupItem value="en" aria-label="English">EN</ToggleGroupItem>
          </ToggleGroup>
        </header>

        <p class="text-sm leading-relaxed text-muted-foreground">
          {{ mode === "setup" ? copy.nav.setupDescription : copy.nav.settingsDescription }}
        </p>

        <nav class="flex gap-1 overflow-x-auto pb-1 md:flex-col md:overflow-visible" aria-label="Setup progress">
          <Button
            v-for="(step, index) in steps"
            :key="step.id"
            type="button"
            :variant="currentIndex === index ? 'secondary' : 'ghost'"
            class="h-auto min-w-52 justify-start px-3 py-2.5 text-left md:min-w-0"
            :disabled="!canNavigateTo(index)"
            @click="navigateTo(index)"
          >
            <component :is="step.icon" data-icon="inline-start" />
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium">{{ step.title }}</span>
              <span class="mt-0.5 block truncate text-xs font-normal text-muted-foreground">{{ step.short }}</span>
            </span>
            <CheckIcon v-if="isStepValid(step.id) && (mode === 'settings' || index < furthestIndex) && index !== currentIndex" data-icon="inline-end" />
          </Button>
        </nav>

        <div class="mt-auto flex flex-col gap-2">
          <Progress :model-value="progressValue" />
          <p class="text-xs text-muted-foreground">{{ currentIndex + 1 }} / {{ steps.length }}</p>
        </div>
      </aside>

      <Card class="min-w-0 min-h-[calc(100dvh-3rem)] md:h-[calc(100dvh-3rem)]">
        <CardHeader class="shrink-0">
          <CardTitle>{{ steps[currentIndex]?.title }}</CardTitle>
          <CardDescription>{{ steps[currentIndex]?.short }}</CardDescription>
        </CardHeader>
        <Separator />

        <CardContent class="min-h-0 flex-1 overflow-y-auto py-6">
          <Alert v-if="stepErrorText" variant="destructive" class="mb-6">
            <TriangleAlertIcon />
            <AlertTitle>{{ copy.common.needsAttention }}</AlertTitle>
            <AlertDescription>{{ stepErrorText }}</AlertDescription>
          </Alert>
          <Alert v-if="submissionError" variant="destructive" class="mb-6">
            <TriangleAlertIcon />
            <AlertTitle>{{ copy.errors.generic }}</AlertTitle>
            <AlertDescription>{{ submissionError }}</AlertDescription>
          </Alert>

          <WallpaperStep
            v-if="activeStep === 'wallpaper'"
            :locale="locale"
            :path="draft.wallpaper_engine_path"
            :status="scan.status.value"
            :detail="scanDetail"
            :playlists="scan.playlists.value"
            :usable-count="scan.usablePlaylists.value.length"
            :native-bridge="hasNativeBridge"
            :invalid="Boolean(stepError) && !isStepValid('wallpaper')"
            :errors="issuesByStep.wallpaper.wallpaper_engine_path ?? []"
            @update:path="updatePath"
            @scan="scanWallpaper"
            @choose="chooseWallpaperEngine"
          />
          <WeatherKeyStep
            v-else-if="activeStep === 'weather'"
            :locale="locale"
            :api-key="draft.weather.api_key"
            :invalid="Boolean(stepError) && !isStepValid('weather')"
            :errors="issuesByStep.weather['weather.api_key'] ?? []"
            :validating="validatingWeather"
            :validation-status="weatherValidationStatus"
            :validation-error="weatherValidationError"
            @update:api-key="updateApiKey"
            @validate="testWeatherKey"
            @open-key-page="openExternal('https://home.openweathermap.org/api_keys')"
          />
          <LocationStep
            v-else-if="activeStep === 'location'"
            :locale="locale"
            :mode="mode"
            :location="draft.weather.location"
            :locating="locating"
            :detection-status="locationDetectionStatus"
            :detection-error="locationDetectionError"
            :attempted="Boolean(stepError)"
            :errors="issuesByStep.location"
            @update:location="updateLocation"
            @detect="detectCity"
          />
          <SceneBindingsStep
            v-else-if="activeStep === 'scenes'"
            :locale="locale"
            :mode="mode"
            :scenes="draft.scenes"
            :catalog="sceneCatalog"
            :playlists="scan.usablePlaylists.value"
            :catalog-error="catalogError"
            :valid="isStepValid('scenes')"
            :attempted="Boolean(stepError)"
            :errors="issuesByStep.scenes.scenes ?? []"
            @update:scenes="updateScenes"
            @retry-catalog="loadSceneCatalog"
          />
          <SchedulingStep
            v-else-if="activeStep === 'scheduling'"
            :locale="locale"
            :matching="draft.matching"
            :disturbance="draft.disturbance"
            :timing-open="timingOpen"
            :errors="issuesByStep.scheduling"
            @update:matching="updateMatching"
            @update:disturbance="updateDisturbance"
            @update:timing-open="timingOpen = $event"
          />
          <ActivityRulesStep
            v-else-if="activeStep === 'activity'"
            :locale="locale"
            :activity="draft.activity"
            :conflicts="evaluation.conflicts"
            :errors="issuesByStep.activity.activity ?? []"
            @update:activity="updateActivity"
          />
          <ReviewStep v-else :locale="locale" :draft="draft" :valid="allValid" />
        </CardContent>

        <Separator />
        <CardFooter class="shrink-0 justify-between gap-3">
          <div class="flex gap-2">
            <Button v-if="currentIndex > 0" variant="outline" :disabled="submitting" @click="goBack">
              <ChevronLeftIcon data-icon="inline-start" />
              {{ copy.common.back }}
            </Button>
            <Button v-else variant="ghost" :disabled="submitting" @click="requestClose">{{ copy.common.cancel }}</Button>
          </div>

          <Button v-if="activeStep !== 'review'" :disabled="submitting" @click="goNext">
            {{ copy.common.next }}
            <ChevronRightIcon data-icon="inline-end" />
          </Button>
          <Button v-else :disabled="submitting || !allValid" @click="submitProfile">
            <Spinner v-if="submitting" data-icon="inline-start" />
            <CheckIcon v-else data-icon="inline-start" />
            {{ submitting
              ? (mode === "setup" ? copy.review.creating : copy.review.saving)
              : (mode === "setup" ? copy.review.create : copy.review.save) }}
          </Button>
        </CardFooter>
      </Card>
    </div>

    <AlertDialog v-model:open="closeDialogOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ mode === "setup" ? copy.common.cancel : copy.common.close }}</AlertDialogTitle>
          <AlertDialogDescription>{{ copy.nav.settingsDescription }}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ copy.common.back }}</AlertDialogCancel>
          <AlertDialogAction @click="closeWindow">{{ copy.common.close }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>
