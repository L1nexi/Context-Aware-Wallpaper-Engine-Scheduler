import type { VueWrapper } from "@vue/test-utils"
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import type { Profile } from "@/api/profile"
import { ApiError } from "@/api/profile"
import SetupWorkspace from "@/components/setup/SetupWorkspace.vue"

vi.mock("@/theme", async () => {
  const { ref } = await import("vue")
  return { themeMode: ref("auto") }
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

const api = vi.hoisted(() => ({
  applyProfile: vi.fn(),
  createInitialProfile: vi.fn(),
  detectLocation: vi.fn(),
  getSceneCatalog: vi.fn(),
  scanPlaylists: vi.fn(),
}))

vi.mock("@/api/profile", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/profile")>()),
  ...api,
}))

const profile: Profile = {
  version: 1,
  setup_complete: true,
  wallpaper_engine_path: "C:\\Wallpaper Engine",
  language: "en",
  weather: {
    api_key: "weather-key",
    location: {
      name: "Shanghai",
      latitude: 31.23,
      longitude: 121.47,
    },
  },
  scenes: { day_work: "Work" },
  matching: { response_style: "balanced" },
  disturbance: {
    startup_grace_seconds: 15,
    idle_before_switch_seconds: 20,
    maximum_deferral_minutes: 60,
    cycle_interval_minutes: 15,
  },
  activity: {
    work_processes: [],
    leisure_processes: [],
    work_title_keywords: [],
    leisure_title_keywords: [],
  },
}

let mountedWrapper: VueWrapper | null = null

function mountWorkspace(initialProfile: Profile | null): VueWrapper {
  mountedWrapper = mount(SetupWorkspace, {
    props: {
      initialProfile,
      initialLocale: "en",
    },
  })
  return mountedWrapper
}

beforeEach(() => {
  vi.resetAllMocks()
  api.getSceneCatalog.mockResolvedValue([{ id: "day_work" }])
  api.scanPlaylists.mockResolvedValue({
    wallpaper_engine_path: profile.wallpaper_engine_path,
    playlists: [{ name: "Work", item_count: 2 }],
  })
  api.applyProfile.mockResolvedValue(profile)
  api.createInitialProfile.mockResolvedValue(profile)
})

afterEach(() => {
  mountedWrapper?.unmount()
  mountedWrapper = null
})

test("saving shows a server field error in its owning setup step", async () => {
  api.applyProfile.mockRejectedValue(
    new ApiError(422, {
      error: "profile_invalid",
      issues: [
        {
          path: ["weather", "api_key"],
          code: "weather_api_key_invalid",
          message: "invalid API key",
        },
      ],
    }),
  )

  const wrapper = mountWorkspace(profile)
  await flushPromises()

  const reviewButton = wrapper.findAll("button").find((button) => button.text().includes("Review and save"))
  expect(reviewButton).toBeDefined()
  await reviewButton!.trigger("click")

  const saveButton = wrapper.findAll("button").find((button) => button.text().trim() === "Save and apply")
  expect(saveButton).toBeDefined()
  await saveButton!.trigger("click")
  await flushPromises()

  expect(wrapper.get("h1").text()).toBe("Connect weather")
  expect(wrapper.get("#weather-api-key").attributes("aria-invalid")).toBe("true")
  expect(wrapper.text()).toContain("This API key is invalid.")
})

test("first-run setup can inspect other categories but cannot save incomplete settings", async () => {
  api.scanPlaylists.mockResolvedValue({
    wallpaper_engine_path: "",
    playlists: [],
  })

  const wrapper = mountWorkspace(null)
  await flushPromises()

  await wrapper.findAll("button").find((button) => button.text().trim() === "Weather service")!.trigger("click")
  expect(wrapper.get("h1").text()).toBe("Connect weather")

  await wrapper.findAll("button").find((button) => button.text().trim() === "Review and finish")!.trigger("click")
  expect(wrapper.get("h1").text()).toBe("Review and finish")
  expect(wrapper.findAll("button").find((button) => button.text().trim() === "Finish setup")?.attributes("disabled")).toBeDefined()
})

test("editing one step keeps server errors that belong to another step", async () => {
  api.applyProfile.mockRejectedValue(
    new ApiError(422, {
      error: "profile_invalid",
      issues: [
        {
          path: ["weather", "api_key"],
          code: "weather_api_key_invalid",
          message: "invalid API key",
        },
        {
          path: ["activity"],
          code: "activity_invalid",
          message: "Activity targets conflict",
        },
      ],
    }),
  )

  const wrapper = mountWorkspace(profile)
  await flushPromises()

  await wrapper.findAll("button").find((button) => button.text().includes("Review and save"))!.trigger("click")
  await wrapper.findAll("button").find((button) => button.text().trim() === "Save and apply")!.trigger("click")
  await flushPromises()

  await wrapper.get("#weather-api-key").setValue("replacement-key")
  await wrapper.findAll("button").find((button) => button.text().includes("Activity detection"))!.trigger("click")

  expect(wrapper.get("h1").text()).toBe("Recognize activity")
  expect(wrapper.text()).toContain("Activity targets conflict")
  expect(wrapper.text()).not.toContain("This API key is invalid.")
})

test("an older playlist scan cannot replace results for a newer path", async () => {
  const olderScan = deferred<{
    wallpaper_engine_path: string
    playlists: Array<{ name: string; item_count: number }>
  }>()
  const newerScan = deferred<{
    wallpaper_engine_path: string
    playlists: Array<{ name: string; item_count: number }>
  }>()
  api.scanPlaylists.mockReturnValueOnce(olderScan.promise).mockReturnValueOnce(newerScan.promise)

  const wrapper = mountWorkspace(profile)
  await vi.waitFor(() => expect(api.scanPlaylists).toHaveBeenCalledTimes(1))

  await wrapper.get("#wallpaper-engine-path").setValue("D:\\New Wallpaper Engine")
  const scanButton = wrapper.findAll("button").find((button) => button.text().trim() === "Scan playlists")
  expect(scanButton).toBeDefined()
  await scanButton!.trigger("click")
  await vi.waitFor(() => expect(api.scanPlaylists).toHaveBeenCalledTimes(2))

  newerScan.resolve({
    wallpaper_engine_path: "D:\\New Wallpaper Engine",
    playlists: [{ name: "New list", item_count: 3 }],
  })
  await flushPromises()
  expect(wrapper.text()).toContain("New list")

  olderScan.resolve({
    wallpaper_engine_path: profile.wallpaper_engine_path,
    playlists: [{ name: "Old list", item_count: 4 }],
  })
  await flushPromises()

  expect(wrapper.get<HTMLInputElement>("#wallpaper-engine-path").element.value).toBe("D:\\New Wallpaper Engine")
  expect(wrapper.text()).toContain("New list")
  expect(wrapper.text()).not.toContain("Old list")
})

test("a failed Scene catalog load can be retried from the Scene step", async () => {
  api.getSceneCatalog
    .mockRejectedValueOnce(
      new ApiError(503, {
        error: "scene_catalog_unavailable",
        detail: "Scene catalog unavailable",
      }),
    )
    .mockResolvedValueOnce([{ id: "day_work" }])

  const wrapper = mountWorkspace(profile)
  await flushPromises()

  await wrapper.findAll("button").find((button) => button.text().includes("Scene assignments"))!.trigger("click")
  expect(wrapper.text()).toContain("Scene catalog unavailable")
  expect(wrapper.text()).not.toContain("Day work")

  const retryButton = wrapper.findAll("button").find((button) => button.text().trim() === "Retry")
  expect(retryButton).toBeDefined()
  await retryButton!.trigger("click")
  await flushPromises()

  expect(wrapper.text()).not.toContain("Scene catalog unavailable")
  expect(wrapper.text()).toContain("Day work")
})
