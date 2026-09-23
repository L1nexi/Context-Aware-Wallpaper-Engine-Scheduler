<script setup lang="ts">
import type { Component } from "vue"
import {
  AppWindowIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClipboardCheckIcon,
  CloudSunIcon,
  ExternalLinkIcon,
  EyeIcon,
  EyeOffIcon,
  FolderOpenIcon,
  LayersIcon,
  LocateFixedIcon,
  MapPinIcon,
  MonitorIcon,
  RefreshCwIcon,
  SlidersHorizontalIcon,
  TriangleAlertIcon,
} from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { toast } from "vue-sonner"

import type {
  ValidationIssue,
  Locale,
  PlaylistScanResult,
  Profile,
  ResponseStyle,
  SceneCatalogItem,
  SceneId,
} from "@/api/profile"
import {
  ApiError,
  applyProfile,
  createInitialProfile,
  detectLocation,
  getSceneCatalog,
  scanPlaylists,
} from "@/api/profile"
import ActivityListInput from "@/components/setup/ActivityListInput.vue"
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
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"
import { Progress } from "@/components/ui/progress"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  COPY,
  DISTURBANCE_LABELS,
  RESPONSE_STYLE_LABELS,
  SCENE_LABELS,
} from "@/setup/copy"
import {
  activityConflicts,
  applyDisturbancePreset,
  buildProfile,
  createProfileDraft,
  detectDisturbancePreset,
  DISTURBANCE_PRESETS,
  isNonNegativeInteger,
  parseNumberInput,
  profileFingerprint,
  validationIssueField,
  validationIssueStep,
} from "@/setup/model"
import type { DisturbancePreset, ProfileDraft } from "@/setup/model"

const props = defineProps<{
  initialProfile: Profile | null
  initialLocale: Locale
}>()

const mode = computed<"setup" | "settings">(() => (props.initialProfile === null ? "setup" : "settings"))
const locale = ref<Locale>(props.initialProfile?.language ?? props.initialLocale)
const copy = computed(() => COPY[locale.value])
const draft = reactive<ProfileDraft>(createProfileDraft(props.initialProfile, locale.value))
const baseline = ref(profileFingerprint(draft))
const currentStep = ref(0)
const furthestStep = ref(mode.value === "settings" ? 6 : 0)
const stepError = ref("")
const submissionError = ref("")
const fieldErrors = ref<Record<string, string[]>>({})
const submitting = ref(false)
const locating = ref(false)
const locationDetectionStatus = ref<"idle" | "success" | "error">("idle")
const showApiKey = ref(false)
const timingOpen = ref(false)
const closeDialogOpen = ref(false)
const hasNativeBridge = ref(Boolean(window.pywebview?.api))

type ScanStatus = "idle" | "loading" | "success" | "empty" | "error"
const scanStatus = ref<ScanStatus>("idle")
const scanDetail = ref("")
const scannedPath = ref("")
const playlists = ref<PlaylistScanResult["playlists"]>([])
const sceneCatalog = ref<SceneCatalogItem[]>([])
let latestScanRequest = 0
let requestedScanPath = ""

const stepIcons: Component[] = [
  MonitorIcon,
  CloudSunIcon,
  MapPinIcon,
  LayersIcon,
  SlidersHorizontalIcon,
  AppWindowIcon,
  ClipboardCheckIcon,
]

const steps = computed(() =>
  copy.value.steps.map((step, index) => ({ ...step, icon: stepIcons[index] as Component })),
)

const usablePlaylists = computed(() => playlists.value.filter((playlist) => playlist.item_count > 0))
const wallpaperReady = computed(
  () =>
    scanStatus.value === "success" &&
    scannedPath.value === draft.wallpaper_engine_path &&
    usablePlaylists.value.length > 0,
)
const locationValid = computed(
  () =>
    draft.weather.location.name.trim().length > 0 &&
    draft.weather.location.latitude !== null &&
    Number.isFinite(draft.weather.location.latitude) &&
    draft.weather.location.latitude >= -90 &&
    draft.weather.location.latitude <= 90 &&
    draft.weather.location.longitude !== null &&
    Number.isFinite(draft.weather.location.longitude) &&
    draft.weather.location.longitude >= -180 &&
    draft.weather.location.longitude <= 180,
)
const scenesValid = computed(() => {
  const available = new Set(usablePlaylists.value.map((playlist) => playlist.name))
  const assignments = Object.values(draft.scenes)
  return assignments.length > 0 && assignments.every((playlist) => playlist && available.has(playlist))
})
const preferencesValid = computed(
  () =>
    Object.values(draft.disturbance).every(isNonNegativeInteger) &&
    Boolean(draft.matching.response_style),
)
const conflicts = computed(() => activityConflicts(draft))
const stepValidity = computed(() => [
  wallpaperReady.value,
  draft.weather.api_key.trim().length > 0,
  locationValid.value,
  scenesValid.value,
  preferencesValid.value,
  conflicts.value.length === 0,
  wallpaperReady.value &&
    draft.weather.api_key.trim().length > 0 &&
    locationValid.value &&
    scenesValid.value &&
    preferencesValid.value &&
    conflicts.value.length === 0,
])
const allValid = computed(() => stepValidity.value[6] === true)
const isDirty = computed(() => profileFingerprint(draft) !== baseline.value)
const progressValue = computed(() => ((currentStep.value + 1) / steps.value.length) * 100)
const disturbancePreset = computed(() => detectDisturbancePreset(draft))
const activityRuleCount = computed(
  () =>
    draft.activity.work_processes.length +
    draft.activity.leisure_processes.length +
    draft.activity.work_title_keywords.length +
    draft.activity.leisure_title_keywords.length,
)

const sceneGroups = computed(() => [
  {
    id: "context",
    title: copy.value.scenes.groups.context,
    scenes: ["day_work", "day_leisure", "night_work", "night_leisure"] as SceneId[],
  },
  {
    id: "season",
    title: copy.value.scenes.groups.season,
    scenes: ["spring", "summer", "autumn", "winter"] as SceneId[],
  },
  {
    id: "weather",
    title: copy.value.scenes.groups.weather,
    scenes: ["sunset", "rain"] as SceneId[],
  },
])

const supportedScenes = computed(() => new Set(sceneCatalog.value.map((scene) => scene.id)))

watch(
  () => draft.wallpaper_engine_path,
  (path) => {
    const normalizedPath = path.trim()
    if (normalizedPath === scannedPath.value) return
    if (scanStatus.value === "loading" && normalizedPath === requestedScanPath) return
    latestScanRequest += 1
    scanStatus.value = "idle"
    scanDetail.value = ""
  },
)

watch(locale, (value) => {
  draft.language = value
  document.documentElement.lang = value === "zh" ? "zh-CN" : "en"
  document.title = value === "zh" ? "WEScheduler 设置" : "WEScheduler Settings"
})

watch(
  draft,
  () => {
    fieldErrors.value = {}
    stepError.value = ""
    submissionError.value = ""
  },
  { deep: true },
)

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
  try {
    sceneCatalog.value = await getSceneCatalog()
  } catch (error) {
    submissionError.value = describeError(error)
  }
  await performScan(draft.wallpaper_engine_path)
})

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload)
  window.removeEventListener("pywebviewready", updateNativeBridgeAvailability)
})

async function performScan(path: string): Promise<void> {
  const normalizedPath = path.trim()
  const requestId = ++latestScanRequest
  requestedScanPath = normalizedPath
  scanStatus.value = "loading"
  scanDetail.value = ""
  try {
    const result = await scanPlaylists(normalizedPath)
    if (requestId !== latestScanRequest) return
    scannedPath.value = result.wallpaper_engine_path
    draft.wallpaper_engine_path = result.wallpaper_engine_path
    playlists.value = result.playlists
    scanStatus.value = result.playlists.some((playlist) => playlist.item_count > 0) ? "success" : "empty"
  } catch (error) {
    if (requestId !== latestScanRequest) return
    playlists.value = []
    scannedPath.value = ""
    scanStatus.value = "error"
    scanDetail.value = describeScanError(error)
  }
}

async function chooseWallpaperEngine(): Promise<void> {
  if (!window.pywebview?.api) return
  const path = await window.pywebview.api.choose_wallpaper_engine()
  if (!path) return
  draft.wallpaper_engine_path = path
  await performScan(path)
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
  const messages: Record<string, Record<Locale, string>> = {
    wallpaper_engine_executable_not_found: {
      zh: "没有找到 wallpaper64.exe。请手动选择安装位置。",
      en: "wallpaper64.exe was not found. Choose the installation manually.",
    },
    wallpaper_engine_config_not_found: {
      zh: "没有找到 Wallpaper Engine config.json。请先启动一次 Wallpaper Engine，然后重试。",
      en: "Wallpaper Engine config.json was not found. Start Wallpaper Engine once, then try again.",
    },
    wallpaper_engine_config_read_failed: {
      zh: "Wallpaper Engine 配置暂时无法读取。请关闭可能正在写入配置的窗口后重试。",
      en: "Wallpaper Engine configuration could not be read. Close anything writing it, then try again.",
    },
    unexpected_wallpaper_engine_config_format: {
      zh: "Wallpaper Engine 配置格式无法识别。",
      en: "The Wallpaper Engine configuration format was not recognized.",
    },
  }
  return messages[error.payload.error]?.[locale.value] ?? error.message
}

function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) return copy.value.errors.generic
  if (error.payload.error === "profile_already_exists") return copy.value.errors.profileAlreadyExists
  if (error.payload.error === "profile_apply_timeout") return copy.value.errors.applyTimeout
  if (error.payload.error === "profile_apply_unavailable") return copy.value.errors.applyUnavailable
  if (error.payload.error === "weather_validation_unavailable") return copy.value.errors.weatherValidationUnavailable
  if (error.payload.stage) {
    const stage = copy.value.errors.stages[error.payload.stage]
    return `${stage}: ${error.payload.detail || error.payload.error}`
  }
  return error.message || copy.value.errors.generic
}

function localizedIssueMessage(issue: ValidationIssue): string {
  const knownMessages = copy.value.errors.issueCodes as Record<string, string>
  return knownMessages[issue.code] ?? issue.message
}

function applyValidationIssues(error: unknown): boolean {
  if (!(error instanceof ApiError) || !error.payload.issues?.length) return false

  const grouped: Record<string, string[]> = {}
  for (const issue of error.payload.issues) {
    const field = validationIssueField(issue.path)
    grouped[field] ??= []
    grouped[field].push(localizedIssueMessage(issue))
  }
  fieldErrors.value = grouped

  const targetStep = Math.min(...error.payload.issues.map((issue) => validationIssueStep(issue.path)))
  currentStep.value = targetStep
  furthestStep.value = Math.max(furthestStep.value, targetStep)
  if (error.payload.issues.some((issue) => issue.path[0] === "disturbance")) timingOpen.value = true
  stepError.value = copy.value.errors.fieldValidation
  submissionError.value = ""
  return true
}

function hasFieldError(...fields: string[]): boolean {
  return fields.some((field) => Boolean(fieldErrors.value[field]?.length))
}

function fieldErrorMessages(...fields: string[]): string[] {
  return fields.flatMap((field) => fieldErrors.value[field] ?? [])
}

async function detectCity(): Promise<void> {
  locating.value = true
  locationDetectionStatus.value = "idle"
  try {
    const detected = await detectLocation()
    draft.weather.location.name = detected.name
    draft.weather.location.latitude = detected.latitude
    draft.weather.location.longitude = detected.longitude
    locationDetectionStatus.value = "success"
  } catch {
    locationDetectionStatus.value = "error"
  } finally {
    locating.value = false
  }
}

function canNavigateTo(index: number): boolean {
  return mode.value === "settings" || index <= furthestStep.value
}

function navigateTo(index: number): void {
  if (!canNavigateTo(index)) return
  currentStep.value = index
  stepError.value = ""
  submissionError.value = ""
}

function goNext(): void {
  if (!stepValidity.value[currentStep.value]) {
    stepError.value = copy.value.errors.validation
    return
  }
  const next = Math.min(currentStep.value + 1, steps.value.length - 1)
  furthestStep.value = Math.max(furthestStep.value, next)
  currentStep.value = next
  stepError.value = ""
}

function goBack(): void {
  currentStep.value = Math.max(0, currentStep.value - 1)
  stepError.value = ""
}

function setLocale(value: unknown): void {
  if (value === "zh" || value === "en") locale.value = value
}

function setLatitude(value: string | number): void {
  const parsed = value === "" ? null : Number(value)
  draft.weather.location.latitude = parsed !== null && Number.isFinite(parsed) ? parsed : null
}

function setLongitude(value: string | number): void {
  const parsed = value === "" ? null : Number(value)
  draft.weather.location.longitude = parsed !== null && Number.isFinite(parsed) ? parsed : null
}

type DisturbanceKey = keyof ProfileDraft["disturbance"]

function setDisturbanceValue(field: DisturbanceKey, value: string | number): void {
  draft.disturbance[field] = parseNumberInput(value)
}

function setResponseStyle(value: unknown): void {
  if (typeof value === "string" && value) draft.matching.response_style = value as ResponseStyle
}

function setDisturbancePreset(value: unknown): void {
  if (typeof value !== "string" || !(value in DISTURBANCE_PRESETS)) return
  applyDisturbancePreset(draft, value as DisturbancePreset)
}

function toggleScene(sceneId: SceneId, enabled: boolean | "indeterminate"): void {
  if (enabled === true) {
    draft.scenes[sceneId] ??= usablePlaylists.value[0]?.name ?? ""
    return
  }
  delete draft.scenes[sceneId]
}

function setScenePlaylist(sceneId: SceneId, value: unknown): void {
  if (typeof value === "string") draft.scenes[sceneId] = value
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
    const invalidIndex = stepValidity.value.slice(0, 6).findIndex((valid) => !valid)
    currentStep.value = Math.max(0, invalidIndex)
    furthestStep.value = Math.max(furthestStep.value, currentStep.value)
    stepError.value = copy.value.errors.validation
    return
  }

  submitting.value = true
  submissionError.value = ""
  try {
    const profile = buildProfile(draft)
    const committed = mode.value === "setup" ? await createInitialProfile(profile) : await applyProfile(profile)
    Object.assign(draft, createProfileDraft(committed, locale.value))
    baseline.value = profileFingerprint(draft)
    if (mode.value === "setup") {
      toast.success(copy.value.review.setupSuccess)
      await closeWindow()
    } else {
      toast.success(copy.value.review.success)
    }
  } catch (error) {
    if (!applyValidationIssues(error)) submissionError.value = describeError(error)
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
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            :model-value="locale"
            aria-label="Language"
            @update:model-value="setLocale"
          >
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
            :key="step.title"
            type="button"
            :variant="currentStep === index ? 'secondary' : 'ghost'"
            class="h-auto min-w-52 justify-start px-3 py-2.5 text-left md:min-w-0"
            :disabled="!canNavigateTo(index)"
            @click="navigateTo(index)"
          >
            <component :is="step.icon" data-icon="inline-start" />
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium">{{ step.title }}</span>
              <span class="mt-0.5 block truncate text-xs font-normal text-muted-foreground">{{ step.short }}</span>
            </span>
            <CheckIcon
              v-if="stepValidity[index] && (mode === 'settings' || index < furthestStep) && index !== currentStep"
              data-icon="inline-end"
            />
          </Button>
        </nav>

        <div class="mt-auto flex flex-col gap-2">
          <Progress :model-value="progressValue" />
          <p class="text-xs text-muted-foreground">{{ currentStep + 1 }} / {{ steps.length }}</p>
        </div>
      </aside>

      <Card class="min-w-0 min-h-[calc(100dvh-3rem)] md:h-[calc(100dvh-3rem)]">
        <CardHeader class="shrink-0">
          <CardTitle>{{ steps[currentStep]?.title }}</CardTitle>
          <CardDescription>{{ steps[currentStep]?.short }}</CardDescription>
        </CardHeader>

        <Separator />

        <CardContent class="min-h-0 flex-1 overflow-y-auto py-6">
          <Alert v-if="stepError" variant="destructive" class="mb-6">
            <TriangleAlertIcon />
            <AlertTitle>{{ copy.common.needsAttention }}</AlertTitle>
            <AlertDescription>{{ stepError }}</AlertDescription>
          </Alert>

          <Alert v-if="submissionError" variant="destructive" class="mb-6">
            <TriangleAlertIcon />
            <AlertTitle>{{ copy.errors.generic }}</AlertTitle>
            <AlertDescription>{{ submissionError }}</AlertDescription>
          </Alert>

          <section v-if="currentStep === 0" class="flex flex-col gap-6">
            <div class="max-w-2xl">
              <h1 class="text-2xl font-semibold tracking-tight">{{ copy.wallpaper.title }}</h1>
              <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.wallpaper.description }}</p>
            </div>

            <FieldGroup>
              <Field :data-invalid="(Boolean(stepError) && !wallpaperReady) || hasFieldError('wallpaper_engine_path')">
                <FieldLabel for="wallpaper-engine-path">{{ copy.wallpaper.pathLabel }}</FieldLabel>
                <InputGroup>
                  <InputGroupInput
                    id="wallpaper-engine-path"
                    v-model="draft.wallpaper_engine_path"
                    :placeholder="copy.wallpaper.pathPlaceholder"
                    :aria-invalid="(Boolean(stepError) && !wallpaperReady) || hasFieldError('wallpaper_engine_path')"
                  />
                  <InputGroupAddon align="inline-end">
                    <InputGroupButton
                      v-if="hasNativeBridge"
                      :aria-label="copy.wallpaper.choose"
                      @click="chooseWallpaperEngine"
                    >
                      <FolderOpenIcon />
                      <span>{{ copy.wallpaper.choose }}</span>
                    </InputGroupButton>
                  </InputGroupAddon>
                </InputGroup>
                <FieldDescription>{{ copy.wallpaper.pathDescription }}</FieldDescription>
                <FieldError
                  v-if="hasFieldError('wallpaper_engine_path')"
                  :errors="fieldErrorMessages('wallpaper_engine_path')"
                />
              </Field>
            </FieldGroup>

            <div class="flex flex-wrap gap-2">
              <Button
                :disabled="scanStatus === 'loading'"
                @click="performScan(draft.wallpaper_engine_path)"
              >
                <Spinner v-if="scanStatus === 'loading'" data-icon="inline-start" />
                <RefreshCwIcon v-else data-icon="inline-start" />
                {{ scanStatus === "loading" ? copy.wallpaper.scanning : draft.wallpaper_engine_path ? copy.wallpaper.scan : copy.wallpaper.detect }}
              </Button>
            </div>

            <Alert v-if="scanStatus === 'error'" variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>{{ copy.wallpaper.emptyTitle }}</AlertTitle>
              <AlertDescription>{{ scanDetail }}</AlertDescription>
            </Alert>

            <Empty v-else-if="scanStatus === 'empty'">
              <EmptyHeader>
                <EmptyMedia variant="icon"><LayersIcon /></EmptyMedia>
                <EmptyTitle>{{ copy.wallpaper.emptyTitle }}</EmptyTitle>
                <EmptyDescription>{{ copy.wallpaper.emptyDescription }}</EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button variant="outline" @click="performScan(draft.wallpaper_engine_path)">
                  <RefreshCwIcon data-icon="inline-start" />
                  {{ copy.wallpaper.scanAgain }}
                </Button>
              </EmptyContent>
            </Empty>

            <div v-else-if="scanStatus === 'success'" class="flex flex-col gap-4">
              <Alert>
                <CheckIcon />
                <AlertTitle>{{ copy.wallpaper.found }}</AlertTitle>
                <AlertDescription>{{ copy.wallpaper.foundDescription(usablePlaylists.length) }}</AlertDescription>
              </Alert>
              <div class="grid gap-2 sm:grid-cols-2">
                <div
                  v-for="playlist in playlists"
                  :key="playlist.name"
                  class="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
                >
                  <span class="truncate text-sm font-medium">{{ playlist.name }}</span>
                  <Badge :variant="playlist.item_count > 0 ? 'secondary' : 'outline'">
                    {{ playlist.item_count > 0 ? playlist.item_count : copy.wallpaper.zeroItem }}
                  </Badge>
                </div>
              </div>
            </div>
          </section>

          <section v-else-if="currentStep === 1" class="flex flex-col gap-6">
            <div class="max-w-2xl">
              <h1 class="text-2xl font-semibold tracking-tight">{{ copy.weather.title }}</h1>
              <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.weather.description }}</p>
            </div>

            <FieldGroup>
              <Field
                :data-invalid="(Boolean(stepError) && !draft.weather.api_key.trim()) || hasFieldError('weather.api_key')"
              >
                <FieldLabel for="weather-api-key">{{ copy.weather.keyLabel }}</FieldLabel>
                <InputGroup>
                  <InputGroupInput
                    id="weather-api-key"
                    v-model="draft.weather.api_key"
                    :type="showApiKey ? 'text' : 'password'"
                    :placeholder="copy.weather.keyPlaceholder"
                    autocomplete="off"
                    :aria-invalid="(Boolean(stepError) && !draft.weather.api_key.trim()) || hasFieldError('weather.api_key')"
                  />
                  <InputGroupAddon align="inline-end">
                    <InputGroupButton
                      :aria-label="showApiKey ? copy.common.hide : copy.common.show"
                      @click="showApiKey = !showApiKey"
                    >
                      <EyeOffIcon v-if="showApiKey" />
                      <EyeIcon v-else />
                    </InputGroupButton>
                  </InputGroupAddon>
                </InputGroup>
                <FieldDescription>{{ copy.weather.keyDescription }}</FieldDescription>
                <FieldError
                  v-if="hasFieldError('weather.api_key')"
                  :errors="fieldErrorMessages('weather.api_key')"
                />
              </Field>
            </FieldGroup>

            <div class="flex flex-wrap gap-2">
              <Button variant="outline" @click="openExternal('https://home.openweathermap.org/api_keys')">
                <ExternalLinkIcon data-icon="inline-start" />
                {{ copy.weather.getKey }}
              </Button>
            </div>

            <Alert>
              <CloudSunIcon />
              <AlertDescription>{{ copy.weather.validationOnSubmit }}</AlertDescription>
            </Alert>
          </section>

          <section v-else-if="currentStep === 2" class="flex flex-col gap-6">
            <div class="max-w-2xl">
              <h1 class="text-2xl font-semibold tracking-tight">{{ copy.location.title }}</h1>
              <p class="mt-2 leading-relaxed text-muted-foreground">
                {{ mode === "setup" ? copy.location.setupDescription : copy.location.settingsDescription }}
              </p>
            </div>

            <div class="flex flex-col items-start gap-2">
              <Button variant="outline" :disabled="locating" @click="detectCity">
                <Spinner v-if="locating" data-icon="inline-start" />
                <LocateFixedIcon v-else data-icon="inline-start" />
                {{ locating ? copy.location.detecting : copy.location.detect }}
              </Button>
              <p class="text-sm text-muted-foreground">{{ copy.location.detectHint }}</p>
            </div>

            <Alert v-if="locationDetectionStatus === 'success'">
              <MapPinIcon />
              <AlertDescription>{{ copy.location.detected }}</AlertDescription>
            </Alert>

            <Alert v-else-if="locationDetectionStatus === 'error'" variant="destructive">
              <TriangleAlertIcon />
              <AlertDescription>{{ copy.location.detectionUnavailable }}</AlertDescription>
            </Alert>

            <FieldGroup>
              <Field
                :data-invalid="(Boolean(stepError) && !draft.weather.location.name.trim()) || hasFieldError('weather.location.name')"
              >
                <FieldLabel for="location-name">{{ copy.location.nameLabel }}</FieldLabel>
                <Input
                  id="location-name"
                  v-model="draft.weather.location.name"
                  :placeholder="copy.location.namePlaceholder"
                  :aria-invalid="(Boolean(stepError) && !draft.weather.location.name.trim()) || hasFieldError('weather.location.name')"
                />
                <FieldError
                  v-if="hasFieldError('weather.location.name')"
                  :errors="fieldErrorMessages('weather.location.name')"
                />
              </Field>

              <div class="grid gap-5 sm:grid-cols-2">
                <Field
                  :data-invalid="(Boolean(stepError) && (draft.weather.location.latitude === null || draft.weather.location.latitude < -90 || draft.weather.location.latitude > 90)) || hasFieldError('weather.location', 'weather.location.latitude')"
                >
                  <FieldLabel for="latitude">{{ copy.location.latitudeLabel }}</FieldLabel>
                  <Input
                    id="latitude"
                    :model-value="draft.weather.location.latitude ?? ''"
                    type="number"
                    min="-90"
                    max="90"
                    step="0.0001"
                    :placeholder="copy.location.latitudePlaceholder"
                    :aria-invalid="(Boolean(stepError) && (draft.weather.location.latitude === null || draft.weather.location.latitude < -90 || draft.weather.location.latitude > 90)) || hasFieldError('weather.location', 'weather.location.latitude')"
                    @update:model-value="setLatitude"
                  />
                  <FieldError
                    v-if="Boolean(stepError) && (draft.weather.location.latitude === null || draft.weather.location.latitude < -90 || draft.weather.location.latitude > 90)"
                    :errors="[copy.location.invalidLatitude]"
                  />
                  <FieldError
                    v-if="hasFieldError('weather.location.latitude')"
                    :errors="fieldErrorMessages('weather.location.latitude')"
                  />
                </Field>
                <Field
                  :data-invalid="(Boolean(stepError) && (draft.weather.location.longitude === null || draft.weather.location.longitude < -180 || draft.weather.location.longitude > 180)) || hasFieldError('weather.location', 'weather.location.longitude')"
                >
                  <FieldLabel for="longitude">{{ copy.location.longitudeLabel }}</FieldLabel>
                  <Input
                    id="longitude"
                    :model-value="draft.weather.location.longitude ?? ''"
                    type="number"
                    min="-180"
                    max="180"
                    step="0.0001"
                    :placeholder="copy.location.longitudePlaceholder"
                    :aria-invalid="(Boolean(stepError) && (draft.weather.location.longitude === null || draft.weather.location.longitude < -180 || draft.weather.location.longitude > 180)) || hasFieldError('weather.location', 'weather.location.longitude')"
                    @update:model-value="setLongitude"
                  />
                  <FieldError
                    v-if="Boolean(stepError) && (draft.weather.location.longitude === null || draft.weather.location.longitude < -180 || draft.weather.location.longitude > 180)"
                    :errors="[copy.location.invalidLongitude]"
                  />
                  <FieldError
                    v-if="hasFieldError('weather.location.longitude')"
                    :errors="fieldErrorMessages('weather.location.longitude')"
                  />
                </Field>
              </div>
              <FieldError
                v-if="hasFieldError('weather.location')"
                :errors="fieldErrorMessages('weather.location')"
              />
            </FieldGroup>
          </section>

          <section v-else-if="currentStep === 3" class="flex flex-col gap-6">
            <div class="max-w-2xl">
              <h1 class="text-2xl font-semibold tracking-tight">{{ copy.scenes.title }}</h1>
              <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.scenes.description }}</p>
            </div>

            <Alert v-if="usablePlaylists.length === 0" variant="destructive">
              <TriangleAlertIcon />
              <AlertDescription>{{ copy.scenes.unavailable }}</AlertDescription>
            </Alert>

            <FieldSet v-for="group in sceneGroups" :key="group.id">
              <FieldLegend>{{ group.title }}</FieldLegend>
              <FieldGroup class="gap-2">
                <Field
                  v-for="sceneId in group.scenes.filter((id) => supportedScenes.has(id))"
                  :key="sceneId"
                  orientation="responsive"
                  class="rounded-lg border p-3"
                >
                  <div class="flex min-w-44 items-center gap-3">
                    <Checkbox
                      :id="`scene-${sceneId}`"
                      :model-value="sceneId in draft.scenes"
                      :disabled="usablePlaylists.length === 0"
                      @update:model-value="(value) => toggleScene(sceneId, value)"
                    />
                    <FieldLabel :for="`scene-${sceneId}`" class="font-normal">
                      {{ SCENE_LABELS[locale][sceneId] }}
                    </FieldLabel>
                  </div>
                  <Select
                    :model-value="draft.scenes[sceneId]"
                    :disabled="!(sceneId in draft.scenes)"
                    @update:model-value="(value) => setScenePlaylist(sceneId, value)"
                  >
                    <SelectTrigger :aria-label="`${SCENE_LABELS[locale][sceneId]}: ${copy.scenes.playlist}`">
                      <SelectValue :placeholder="copy.scenes.choosePlaylist" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem v-for="playlist in usablePlaylists" :key="playlist.name" :value="playlist.name">
                          {{ playlist.name }} ({{ playlist.item_count }})
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
              </FieldGroup>
            </FieldSet>

            <FieldError
              v-if="(stepError && !scenesValid) || hasFieldError('scenes')"
              :errors="[
                ...(stepError && !scenesValid ? [copy.scenes.required] : []),
                ...fieldErrorMessages('scenes'),
              ]"
            />
          </section>

          <section v-else-if="currentStep === 4" class="flex flex-col gap-8">
            <div class="max-w-2xl">
              <h1 class="text-2xl font-semibold tracking-tight">{{ copy.preferences.title }}</h1>
              <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.preferences.description }}</p>
            </div>

            <FieldSet :data-invalid="hasFieldError('matching.response_style')">
              <FieldLegend>{{ copy.preferences.responseTitle }}</FieldLegend>
              <FieldDescription>{{ copy.preferences.responseDescription }}</FieldDescription>
              <ToggleGroup
                type="single"
                variant="outline"
                :spacing="2"
                class="w-full flex-wrap"
                :model-value="draft.matching.response_style"
                @update:model-value="setResponseStyle"
              >
                <ToggleGroupItem
                  v-for="style in (Object.keys(RESPONSE_STYLE_LABELS[locale]) as ResponseStyle[])"
                  :key="style"
                  :value="style"
                  class="min-w-28 flex-1"
                >
                  {{ RESPONSE_STYLE_LABELS[locale][style] }}
                </ToggleGroupItem>
              </ToggleGroup>
              <FieldError
                v-if="hasFieldError('matching.response_style')"
                :errors="fieldErrorMessages('matching.response_style')"
              />
            </FieldSet>

            <FieldSet>
              <FieldLegend>{{ copy.preferences.disturbanceTitle }}</FieldLegend>
              <FieldDescription>{{ copy.preferences.disturbanceDescription }}</FieldDescription>
              <ToggleGroup
                type="single"
                variant="outline"
                :spacing="2"
                class="w-full flex-wrap"
                :model-value="disturbancePreset === 'custom' ? undefined : disturbancePreset"
                @update:model-value="setDisturbancePreset"
              >
                <ToggleGroupItem
                  v-for="preset in (Object.keys(DISTURBANCE_PRESETS) as DisturbancePreset[])"
                  :key="preset"
                  :value="preset"
                  class="min-w-24 flex-1"
                >
                  {{ DISTURBANCE_LABELS[locale][preset] }}
                </ToggleGroupItem>
              </ToggleGroup>
              <Badge v-if="disturbancePreset === 'custom'" variant="outline">{{ copy.common.custom }}</Badge>
            </FieldSet>

            <Collapsible v-model:open="timingOpen">
              <CollapsibleTrigger as-child>
                <Button variant="ghost">
                  <SlidersHorizontalIcon data-icon="inline-start" />
                  {{ copy.preferences.fineTune }}
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent class="pt-4">
                <FieldGroup>
                  <div class="grid gap-5 sm:grid-cols-2">
                    <Field v-for="field in ([
                      ['startup_grace_seconds', copy.preferences.startupGrace, copy.preferences.seconds],
                      ['idle_before_switch_seconds', copy.preferences.idleBeforeSwitch, copy.preferences.seconds],
                      ['maximum_deferral_minutes', copy.preferences.maximumDeferral, copy.preferences.minutes],
                      ['cycle_interval_minutes', copy.preferences.cycleInterval, copy.preferences.minutes],
                    ] as const)" :key="field[0]" :data-invalid="!isNonNegativeInteger(draft.disturbance[field[0]]) || hasFieldError('disturbance', `disturbance.${field[0]}`)">
                      <FieldLabel :for="field[0]">{{ field[1] }}</FieldLabel>
                      <InputGroup>
                        <InputGroupInput
                          :id="field[0]"
                          :model-value="draft.disturbance[field[0]] ?? ''"
                          type="number"
                          min="0"
                          step="1"
                          :aria-invalid="!isNonNegativeInteger(draft.disturbance[field[0]]) || hasFieldError('disturbance', `disturbance.${field[0]}`)"
                          @update:model-value="(value: string | number) => setDisturbanceValue(field[0], value)"
                        />
                        <InputGroupAddon align="inline-end">{{ field[2] }}</InputGroupAddon>
                      </InputGroup>
                      <FieldError
                        v-if="!isNonNegativeInteger(draft.disturbance[field[0]])"
                        :errors="[copy.preferences.nonNegative]"
                      />
                      <FieldError
                        v-if="hasFieldError('disturbance', `disturbance.${field[0]}`)"
                        :errors="fieldErrorMessages('disturbance', `disturbance.${field[0]}`)"
                      />
                    </Field>
                  </div>
                </FieldGroup>
              </CollapsibleContent>
            </Collapsible>
          </section>

          <section v-else-if="currentStep === 5" class="flex flex-col gap-6">
            <div class="max-w-2xl">
              <h1 class="text-2xl font-semibold tracking-tight">{{ copy.activity.title }}</h1>
              <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.activity.description }}</p>
            </div>

            <Alert v-if="conflicts.length" variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>{{ copy.activity.conflictTitle }}</AlertTitle>
              <AlertDescription>{{ copy.activity.conflictDescription(conflicts.join(", ")) }}</AlertDescription>
            </Alert>

            <Alert v-if="hasFieldError('activity')" variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>{{ copy.common.needsAttention }}</AlertTitle>
              <AlertDescription>{{ fieldErrorMessages('activity').join('; ') }}</AlertDescription>
            </Alert>

            <div class="grid gap-6 lg:grid-cols-2">
              <FieldSet class="rounded-xl border p-4">
                <FieldLegend>{{ copy.activity.workTitle }}</FieldLegend>
                <FieldGroup>
                  <Field>
                    <FieldLabel for="work-processes">{{ copy.activity.processLabel }}</FieldLabel>
                    <ActivityListInput
                      id="work-processes"
                      v-model="draft.activity.work_processes"
                      :placeholder="copy.activity.processPlaceholder"
                      :add-label="copy.activity.add"
                      :remove-label="copy.common.remove"
                      :empty-label="copy.activity.empty"
                    />
                  </Field>
                  <Field>
                    <FieldLabel for="work-title-keywords">{{ copy.activity.titleKeywordLabel }}</FieldLabel>
                    <ActivityListInput
                      id="work-title-keywords"
                      v-model="draft.activity.work_title_keywords"
                      :placeholder="copy.activity.keywordPlaceholder"
                      :add-label="copy.activity.add"
                      :remove-label="copy.common.remove"
                      :empty-label="copy.activity.empty"
                    />
                  </Field>
                </FieldGroup>
              </FieldSet>

              <FieldSet class="rounded-xl border p-4">
                <FieldLegend>{{ copy.activity.leisureTitle }}</FieldLegend>
                <FieldGroup>
                  <Field>
                    <FieldLabel for="leisure-processes">{{ copy.activity.processLabel }}</FieldLabel>
                    <ActivityListInput
                      id="leisure-processes"
                      v-model="draft.activity.leisure_processes"
                      :placeholder="copy.activity.processPlaceholder"
                      :add-label="copy.activity.add"
                      :remove-label="copy.common.remove"
                      :empty-label="copy.activity.empty"
                    />
                  </Field>
                  <Field>
                    <FieldLabel for="leisure-title-keywords">{{ copy.activity.titleKeywordLabel }}</FieldLabel>
                    <ActivityListInput
                      id="leisure-title-keywords"
                      v-model="draft.activity.leisure_title_keywords"
                      :placeholder="copy.activity.keywordPlaceholder"
                      :add-label="copy.activity.add"
                      :remove-label="copy.common.remove"
                      :empty-label="copy.activity.empty"
                    />
                  </Field>
                </FieldGroup>
              </FieldSet>
            </div>
          </section>

          <section v-else class="flex flex-col gap-6">
            <div class="max-w-2xl">
              <h1 class="text-2xl font-semibold tracking-tight">{{ copy.review.title }}</h1>
              <p class="mt-2 leading-relaxed text-muted-foreground">{{ copy.review.description }}</p>
            </div>

            <div class="rounded-xl border">
              <div
                v-for="row in [
                  [copy.review.wallpaper, draft.wallpaper_engine_path || copy.common.notSet],
                  [copy.review.weather, draft.weather.api_key ? copy.review.apiKeySet : copy.common.notSet],
                  [copy.review.location, draft.weather.location.name || copy.common.notSet],
                  [copy.review.scenes, copy.review.sceneCount(Object.keys(draft.scenes).length)],
                  [copy.review.response, RESPONSE_STYLE_LABELS[locale][draft.matching.response_style]],
                  [copy.review.disturbance, disturbancePreset === 'custom' ? copy.common.custom : DISTURBANCE_LABELS[locale][disturbancePreset]],
                  [copy.review.activity, copy.review.activityCount(activityRuleCount)],
                ]"
                :key="row[0]"
                class="grid min-w-0 gap-1 border-b px-4 py-3 last:border-b-0 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4"
              >
                <span class="text-sm text-muted-foreground">{{ row[0] }}</span>
                <span class="min-w-0 text-sm font-medium [overflow-wrap:anywhere]">{{ row[1] }}</span>
              </div>
            </div>

            <Alert v-if="!allValid" variant="destructive">
              <TriangleAlertIcon />
              <AlertDescription>{{ copy.errors.validation }}</AlertDescription>
            </Alert>
          </section>
        </CardContent>

        <Separator />

        <CardFooter class="shrink-0 justify-between gap-3">
          <div class="flex gap-2">
            <Button v-if="currentStep > 0" variant="outline" :disabled="submitting" @click="goBack">
              <ChevronLeftIcon data-icon="inline-start" />
              {{ copy.common.back }}
            </Button>
            <Button v-else variant="ghost" :disabled="submitting" @click="requestClose">
              {{ copy.common.cancel }}
            </Button>
          </div>

          <Button v-if="currentStep < steps.length - 1" :disabled="submitting" @click="goNext">
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
