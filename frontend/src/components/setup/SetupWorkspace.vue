<script setup lang="ts">
import type { Component } from "vue"
import {
  AppWindowIcon,
  CheckIcon,
  ChevronRightIcon,
  ClipboardCheckIcon,
  CloudSunIcon,
  LayersIcon,
  MapPinIcon,
  MonitorIcon,
  MoonIcon,
  SlidersHorizontalIcon,
  SunIcon,
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
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { COPY, ZH_WEATHER_SAVE_PROMPT } from "@/setup/copy"
import { evaluateSteps, STEP_ORDER, stepForIssue } from "@/setup/flow"
import type { StepId } from "@/setup/flow"
import { buildProfile, createProfileDraft, profileFingerprint, validationIssueField } from "@/setup/model"
import type { ProfileDraft } from "@/setup/model"
import { usePlaylistScan } from "@/setup/usePlaylistScan"
import { themeMode } from "@/theme"

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
const previousSectionIndex = ref(0)
const activeStep = computed<StepId>(() => STEP_ORDER[currentIndex.value] ?? "wallpaper")
const stepError = ref<"validation" | "fieldValidation" | null>(null)
const validationIssues = ref<ValidationIssue[]>([])
const submissionFailure = shallowRef<unknown>(null)
const catalogFailure = shallowRef<unknown>(null)
const submitting = ref(false)
const locating = ref(false)
const locationDetectionStatus = ref<"idle" | "success" | "error">("idle")
const locationDetectionError = ref("")
const locationDetectionCity = ref<string | null>(null)
const validatingWeather = ref(false)
const weatherValidationStatus = ref<"idle" | "success" | "error">("idle")
const weatherValidationError = ref("")
const weatherValidationFailure = shallowRef<unknown>(null)
const verifiedWeatherKey = ref<string | null>(null)
const weatherSaveDialogOpen = ref(false)
const weatherSaveFailure = ref("")
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
const themeIcon = computed(() => ({ auto: MonitorIcon, light: SunIcon, dark: MoonIcon })[themeMode.value])
const themeLabel = computed(() => ({
  auto: copy.value.nav.themeSystem,
  light: copy.value.nav.themeLight,
  dark: copy.value.nav.themeDark,
})[themeMode.value])
const missingSteps = computed(() => steps.value.filter((step) => step.id !== "review" && !isStepValid(step.id)))
const activeHeading = computed(() => {
  const content = copy.value
  switch (activeStep.value) {
    case "wallpaper": return { title: content.wallpaper.title, description: content.wallpaper.description }
    case "weather": return { title: content.weather.title, description: content.weather.description }
    case "location": return {
      title: content.location.title,
      description: mode.value === "setup" ? content.location.setupDescription : content.location.settingsDescription,
    }
    case "scenes": return { title: content.scenes.title, description: content.scenes.description }
    case "scheduling": return { title: content.preferences.title, description: content.preferences.description }
    case "activity": return { title: content.activity.title, description: content.activity.description }
    case "review": return {
      title: mode.value === "setup" ? content.nav.reviewSetup : content.nav.reviewSettings,
      description: content.review.description,
    }
  }
})
const evaluation = computed(() => evaluateSteps(draft, scan.ready.value, scan.usablePlaylists.value))
const allValid = computed(() => Object.values(evaluation.value.validity).every(Boolean))
const isDirty = computed(() => profileFingerprint(draft) !== baseline.value)
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

function setTheme(value: unknown): void {
  if (value === "auto" || value === "light" || value === "dark") themeMode.value = value
}

function updatePath(value: string): void {
  draft.wallpaper_engine_path = value
  clearStepFeedback("wallpaper")
}

function updateApiKey(value: string): void {
  draft.weather.api_key = value
  weatherValidationStatus.value = verifiedWeatherKey.value !== null && value.trim() === verifiedWeatherKey.value ? "success" : "idle"
  weatherValidationError.value = ""
  weatherValidationFailure.value = null
  clearStepFeedback("weather")
}

function updateLocation(value: ProfileDraft["weather"]["location"]): void {
  draft.weather.location = value
  locationDetectionStatus.value = "idle"
  locationDetectionError.value = ""
  locationDetectionCity.value = null
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

function isSoftWeatherFailure(error: unknown): boolean {
  return error instanceof ApiError && (
    error.payload.error === "weather_validation_unavailable"
    || error.payload.issues?.some((issue) => issue.code === "weather_api_quota_exceeded") === true
  )
}

async function testWeatherKey(): Promise<void> {
  const apiKey = draft.weather.api_key.trim()
  if (!apiKey) {
    weatherValidationStatus.value = "error"
    weatherValidationError.value = copy.value.weather.validationMissing
    return
  }
  validatingWeather.value = true
  weatherValidationStatus.value = verifiedWeatherKey.value === apiKey ? "success" : "idle"
  weatherValidationError.value = ""
  weatherValidationFailure.value = null
  try {
    await validateWeatherKey(apiKey)
    if (draft.weather.api_key.trim() === apiKey) {
      verifiedWeatherKey.value = apiKey
      weatherValidationStatus.value = "success"
    }
  } catch (error) {
    if (draft.weather.api_key.trim() === apiKey) {
      const keyRejected = error instanceof ApiError && error.payload.issues?.some((issue) => issue.code === "weather_api_key_invalid")
      if (keyRejected) verifiedWeatherKey.value = null
      weatherValidationStatus.value = verifiedWeatherKey.value === apiKey ? "success" : "error"
      weatherValidationError.value = describeWeatherTestError(error)
      weatherValidationFailure.value = error
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
  if (error.payload.issues.some((issue) => issue.path[0] === "disturbance")) timingOpen.value = true
  stepError.value = "fieldValidation"
  submissionFailure.value = null
  return true
}

async function detectCity(): Promise<void> {
  locating.value = true
  locationDetectionStatus.value = "idle"
  locationDetectionError.value = ""
  locationDetectionCity.value = null
  try {
    const detected = await detectLocation()
    updateLocation({ latitude: detected.latitude, longitude: detected.longitude })
    locationDetectionCity.value = detected.city ?? null
    locationDetectionStatus.value = "success"
  } catch (error) {
    locationDetectionStatus.value = "error"
    const detail = error instanceof ApiError ? describeNetworkFailure(error) : ""
    locationDetectionError.value = `${copy.value.errors.locationValidationUnavailable} ${detail}`.trim()
  } finally {
    locating.value = false
  }
}

function navigateTo(index: number): void {
  if (activeStep.value !== "review" && index === STEP_ORDER.length - 1) previousSectionIndex.value = currentIndex.value
  currentIndex.value = index
  stepError.value = null
  submissionFailure.value = null
}

function navigateToStep(id: StepId): void {
  const needsAttention = activeStep.value === "review" && !isStepValid(id)
  navigateTo(STEP_ORDER.indexOf(id))
  if (needsAttention) stepError.value = "validation"
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

async function submitProfile(allowUnverifiedWeather = false): Promise<void> {
  if (!allValid.value) {
    const invalidIndex = STEP_ORDER.findIndex((id) => !isStepValid(id))
    currentIndex.value = Math.max(0, invalidIndex)
    stepError.value = "validation"
    return
  }

  const hasVerifiedKey = verifiedWeatherKey.value === draft.weather.api_key.trim()
  if (!allowUnverifiedWeather && !hasVerifiedKey && isSoftWeatherFailure(weatherValidationFailure.value)) {
    weatherSaveFailure.value = describeWeatherTestError(weatherValidationFailure.value)
    weatherSaveDialogOpen.value = true
    return
  }

  submitting.value = true
  submissionFailure.value = null
  try {
    const profile = buildProfile(draft)
    const skipWeatherValidation = allowUnverifiedWeather || hasVerifiedKey
    const committed = mode.value === "setup"
      ? await createInitialProfile(profile, skipWeatherValidation)
      : await applyProfile(profile, skipWeatherValidation)
    Object.assign(draft, createProfileDraft(committed, locale.value))
    baseline.value = profileFingerprint(draft)
    validationIssues.value = []
    stepError.value = null
    weatherValidationFailure.value = null
    weatherSaveFailure.value = ""
    if (mode.value === "setup") {
      toast.success(copy.value.review.setupSuccess)
      await closeWindow()
    } else {
      toast.success(copy.value.review.success)
    }
  } catch (error) {
    if (isSoftWeatherFailure(error) && !allowUnverifiedWeather) {
      weatherSaveFailure.value = describeWeatherTestError(error)
      weatherSaveDialogOpen.value = true
    } else if (!applyValidationIssues(error)) submissionFailure.value = error
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="min-h-[100dvh] bg-muted/40 p-4 text-foreground md:h-[100dvh] md:overflow-hidden">
    <div class="mx-auto grid w-full max-w-[100rem] gap-4 md:h-full md:min-h-0 md:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[18rem_minmax(0,1fr)]">
      <aside class="flex min-w-0 flex-col gap-5 rounded-xl bg-sidebar p-4 text-sidebar-foreground ring-1 ring-sidebar-border md:h-full md:min-h-0 md:overflow-hidden">
        <header>
          <p class="text-2xl leading-8 font-semibold tracking-tight">{{ copy.appName }}</p>
          <p class="mt-1 text-sm leading-5 text-muted-foreground">{{ copy.mode[mode] }}</p>
        </header>

        <nav class="flex gap-1 overflow-x-auto pb-1 md:min-h-0 md:flex-1 md:flex-col md:overflow-y-auto" :aria-label="mode === 'setup' ? copy.nav.setupNavigation : copy.nav.settingsNavigation">
          <p class="hidden px-3 pb-1 text-xs font-medium text-muted-foreground md:block">{{ mode === 'setup' ? copy.nav.setupNavigation : copy.nav.settingsNavigation }}</p>
          <Button
            v-for="(step, index) in steps"
            :key="step.id"
            type="button"
            :variant="currentIndex === index ? 'secondary' : 'ghost'"
            :aria-current="currentIndex === index ? 'page' : undefined"
            class="min-w-44 justify-start px-3 text-left md:min-w-0"
            @click="navigateTo(index)"
          >
            <component :is="step.icon" data-icon="inline-start" />
            <span class="min-w-0 flex-1 truncate font-medium">{{ step.id === 'review' ? (mode === 'setup' ? copy.nav.reviewSetup : copy.nav.reviewSettings) : step.title }}</span>
          </Button>
        </nav>

        <div class="mt-auto flex items-center justify-between border-t border-sidebar-border pt-3">
          <ToggleGroup type="single" size="sm" :spacing="1" class="shrink-0 rounded-xl border border-sidebar-border bg-muted/40 p-0.5" :model-value="locale" :aria-label="copy.nav.languageLabel" @update:model-value="setLocale">
            <ToggleGroupItem value="zh" class="rounded-lg data-[state=on]:bg-background" aria-label="中文">中</ToggleGroupItem>
            <ToggleGroupItem value="en" class="rounded-lg data-[state=on]:bg-background" aria-label="English">EN</ToggleGroupItem>
          </ToggleGroup>
          <Select :model-value="themeMode" @update:model-value="setTheme">
            <SelectTrigger class="size-9 justify-center gap-0 rounded-xl border border-sidebar-border bg-transparent p-0 hover:bg-sidebar-accent [&_svg:last-child]:hidden" :aria-label="`${copy.nav.themeLabel}: ${themeLabel}`" :title="`${copy.nav.themeLabel}: ${themeLabel}`">
              <component :is="themeIcon" class="size-4" />
            </SelectTrigger>
            <SelectContent position="popper" align="end">
              <SelectGroup>
                <SelectItem value="auto">{{ copy.nav.themeSystem }}</SelectItem>
                <SelectItem value="light">{{ copy.nav.themeLight }}</SelectItem>
                <SelectItem value="dark">{{ copy.nav.themeDark }}</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </aside>

      <Card class="min-w-0 min-h-[32rem] md:h-full md:min-h-0">
        <CardHeader class="shrink-0">
          <CardTitle><h1 class="text-[1.375rem] leading-7 font-semibold tracking-tight">{{ activeHeading.title }}</h1></CardTitle>
          <CardDescription v-if="activeHeading.description">{{ activeHeading.description }}</CardDescription>
        </CardHeader>
        <CardContent class="min-h-0 flex-1 overflow-y-auto pt-0 pb-6">
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
            :location="draft.weather.location"
            :locating="locating"
            :detection-status="locationDetectionStatus"
            :detection-error="locationDetectionError"
            :detection-city="locationDetectionCity"
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
            @open-wallpaper="navigateToStep('wallpaper')"
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
          <ReviewStep
            v-else
            :locale="locale"
            :draft="draft"
            :valid="allValid"
            :missing-steps="missingSteps"
            :weather-status="weatherValidationStatus"
            :weather-error="weatherValidationError"
            :validating-weather="validatingWeather"
            @validate-weather="testWeatherKey"
            @open-step="navigateToStep"
          />
        </CardContent>

        <Separator />
        <CardFooter class="shrink-0 justify-between gap-3">
          <Button v-if="activeStep === 'review'" variant="outline" :disabled="submitting" @click="navigateTo(previousSectionIndex)">{{ copy.nav.backToSettings }}</Button>
          <Button v-else variant="ghost" :disabled="submitting" @click="requestClose">{{ mode === 'setup' ? copy.common.cancel : copy.common.close }}</Button>

          <Button v-if="activeStep !== 'review'" :disabled="submitting" @click="navigateToStep('review')">
            {{ mode === 'setup' ? copy.nav.reviewSetup : copy.nav.reviewSettings }}
            <ChevronRightIcon data-icon="inline-end" />
          </Button>
          <Button v-else :disabled="submitting || !allValid" @click="submitProfile()">
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
          <AlertDialogDescription v-if="copy.nav.settingsDescription">{{ copy.nav.settingsDescription }}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ copy.common.back }}</AlertDialogCancel>
          <AlertDialogAction @click="closeWindow">{{ copy.common.close }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog v-model:open="weatherSaveDialogOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ locale === "zh" ? ZH_WEATHER_SAVE_PROMPT.title : copy.errors.weatherValidationUnavailable }}</AlertDialogTitle>
          <AlertDialogDescription>
            {{ weatherSaveFailure }}
            <template v-if="locale === 'zh'">{{ ZH_WEATHER_SAVE_PROMPT.description }}</template>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ copy.common.back }}</AlertDialogCancel>
          <AlertDialogAction :disabled="submitting" @click="submitProfile(true)">{{ mode === "setup" ? copy.review.create : copy.review.save }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>
