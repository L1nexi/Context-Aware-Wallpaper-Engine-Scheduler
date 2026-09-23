import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"
import type { Profile } from "../src/api/profile"

const profile: Profile = {
  version: 1,
  setup_complete: true,
  wallpaper_engine_path: "C:\\Wallpaper Engine\\wallpaper64.exe",
  language: "zh",
  weather: {
    api_key: "saved-key",
    location: { name: "上海", latitude: 31.2304, longitude: 121.4737 },
  },
  scenes: { day_work: "CASUAL_ANIME" },
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

async function mockSetupApi(page: Page, hasProfile: boolean, settingsProfile: Profile = profile): Promise<void> {
  await page.route("**/api/profile", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill(hasProfile ? { json: { profile: settingsProfile } } : { status: 404, json: { error: "profile_not_found" } })
      return
    }
    await route.fulfill({ json: { status: "applied", profile: settingsProfile } })
  })
  await page.route("**/api/scenes", async (route) => {
    await route.fulfill({ json: { scenes: ["day_work", "day_leisure", "night_work", "night_leisure", "rain", "sunset"].map((id) => ({ id })) } })
  })
  await page.route("**/api/wallpaper-engine/playlist-scans", async (route) => {
    await route.fulfill({ json: { wallpaper_engine_path: profile.wallpaper_engine_path, playlists: [{ name: "CASUAL_ANIME", item_count: 60 }] } })
  })
}

test("首次设置清楚标出播单壁纸数，并预选需要手工绑定的推荐场景", async ({ page }) => {
  await mockSetupApi(page, false)
  await page.goto("/?locale=zh")

  await expect(page.getByRole("navigation", { name: "设置步骤" })).toBeVisible()
  await expect(page.getByRole("table", { name: "扫描到的播放列表及壁纸数量" })).toBeVisible()
  await expect(page.getByText("Wallpaper Engine 中的播放列表名称")).toBeVisible()
  await expect(page.getByText("CASUAL_ANIME")).toBeVisible()
  await expect(page.getByText("60 张")).toBeVisible()
  await expect(page.getByText(/英文名称/)).toBeVisible()

  await page.getByRole("button", { name: "继续" }).click()
  await page.getByRole("textbox", { name: "OpenWeatherMap API Key" }).fill("test-key")
  await page.getByRole("button", { name: "继续" }).click()
  await page.getByRole("textbox", { name: "地点名称" }).fill("上海")
  await page.getByRole("spinbutton", { name: "纬度" }).fill("31.2304")
  await page.getByRole("spinbutton", { name: "经度" }).fill("121.4737")
  await page.getByRole("button", { name: "继续" }).click()

  for (const name of ["日间工作", "日间休闲", "夜间工作", "夜间休闲", "雨天"]) {
    await expect(page.getByRole("checkbox", { name })).toBeChecked()
  }
  await expect(page.getByText("推荐", { exact: true })).toHaveCount(0)
  await expect(page.getByText(/请为每个已选场景指定播放列表/)).toBeVisible()
  await page.getByRole("combobox", { name: "日间工作: 播放列表" }).click()
  await expect(page.getByRole("option", { name: /CASUAL_ANIME.*60 张壁纸/ })).toBeVisible()
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "继续" }).click()
  await expect(page.getByText("至少启用并绑定一个场景。")).toBeVisible()
  await expect(page.getByRole("combobox", { name: "日间工作: 播放列表" })).toHaveAttribute("aria-invalid", "true")
})

test("天气页测试 Key 时说明代理失败原因", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.route("**/api/weather-key-validations", async (route) => {
    await route.fulfill({ status: 503, json: { error: "weather_validation_unavailable", reason: "proxy_error" } })
  })
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /天气服务/ }).click()
  await expect(page.getByText("如何获取 API Key")).toBeVisible()
  await expect(page.getByText(/Generate/)).toBeVisible()
  await expect(page.getByText("确认该 Key 的 Status 为 Active，再复制 Key 本身并粘贴到上方输入框。")).toBeVisible()
  await page.getByRole("button", { name: "测试连接" }).click()
  await expect(page.getByText(/代理连接失败/)).toBeVisible()
})

test("无效 Key 的提示不推测激活状态", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.route("**/api/weather-key-validations", async (route) => {
    await route.fulfill({ status: 422, json: { error: "weather_validation_failed", issues: [{ path: ["weather", "api_key"], code: "weather_api_key_invalid", message: "weather_api_key_invalid" }] } })
  })
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /天气服务/ }).click()
  await page.getByRole("button", { name: "测试连接" }).click()
  await expect(page.getByText("这个 API Key 无效。", { exact: true })).toBeVisible()
})

test("天气页测试当前草稿 Key 后显示成功", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.route("**/api/weather-key-validations", async (route) => {
    await route.fulfill({ json: { status: "valid" } })
  })
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /天气服务/ }).click()
  await page.getByRole("textbox", { name: "OpenWeatherMap API Key" }).fill("another-key")
  const keyTestRequest = page.waitForRequest((request) => request.url().endsWith("/api/weather-key-validations") && request.method() === "POST")
  await page.getByRole("button", { name: "测试连接" }).click()
  expect((await keyTestRequest).postDataJSON()).toEqual({ api_key: "another-key" })
  await expect(page.getByText("API Key 已通过联网测试。保存时仍会验证你填写的地点。")).toBeVisible()
})

test("自动定位失败说明原因，仍可手填地点", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.route("**/api/location-estimates", async (route) => {
    await route.fulfill({ status: 503, json: { error: "location_detection_unavailable", reason: "proxy_error" } })
  })
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /所在地点/ }).click()
  await page.getByRole("button", { name: "自动定位城市" }).click()
  await expect(page.getByText(/代理连接失败/)).toBeVisible()
  await page.getByRole("textbox", { name: "地点名称" }).fill("北京")
  await expect(page.getByRole("textbox", { name: "地点名称" })).toHaveValue("北京")
})

test("保存成功提示出现在窗口顶部", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /检查并完成/ }).click()
  const saveRequest = page.waitForRequest((request) => request.url().endsWith("/api/profile") && request.method() === "PUT")
  await page.getByRole("button", { name: "保存并应用" }).click()
  expect((await saveRequest).postDataJSON().scenes).toEqual({ day_work: "CASUAL_ANIME" })

  const notice = page.getByText("已保存并生效")
  await expect(notice).toBeVisible()
  const bounds = await notice.boundingBox()
  expect(bounds).not.toBeNull()
  expect(bounds!.y).toBeLessThan(200)
})

test("检查页显示路径、测试状态、坐标及两类 Activity 规则数", async ({ page }) => {
  const configuredProfile: Profile = {
    ...profile,
    activity: {
      work_processes: ["code"],
      leisure_processes: ["steam"],
      work_title_keywords: ["IDE"],
      leisure_title_keywords: ["游戏"],
    },
  }
  await mockSetupApi(page, true, configuredProfile)
  await page.route("**/api/weather-key-validations", async (route) => {
    await route.fulfill({ json: { status: "valid" } })
  })
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /检查并完成/ }).click()

  await expect(page.getByText("Wallpaper Engine 路径")).toBeVisible()
  await expect(page.getByText(configuredProfile.wallpaper_engine_path)).toBeVisible()
  await expect(page.getByText("天气服务可用性")).toBeVisible()
  await expect(page.getByText("尚未测试")).toBeVisible()
  await expect(page.getByText(/上海.*31\.2304.*121\.4737/)).toBeVisible()
  await expect(page.getByText("窗口 2 条，进程名 2 条")).toBeVisible()

  await page.getByRole("button", { name: "测试连接" }).click()
  await expect(page.getByText("本次草稿测试通过")).toBeVisible()
})

test("桌面布局使用宽屏空间，窄窗口没有外层纵向滚动", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.route("**/api/wallpaper-engine/playlist-scans", async (route) => {
    await route.fulfill({ json: {
      wallpaper_engine_path: profile.wallpaper_engine_path,
      playlists: Array.from({ length: 11 }, (_, index) => ({ name: `PLAYLIST_${index + 1}`, item_count: index + 1 })),
    } })
  })
  await page.setViewportSize({ width: 2560, height: 1350 })
  await page.goto("/?locale=zh")
  await expect(page.getByText("找到安装位置并读取播放列表", { exact: true })).toHaveCount(1)
  const wideBounds = await page.locator("main > div").first().boundingBox()
  expect(wideBounds).not.toBeNull()
  expect(wideBounds!.width).toBeGreaterThan(1500)

  await page.setViewportSize({ width: 1100, height: 800 })
  const hasOuterScroll = await page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight)
  expect(hasOuterScroll).toBe(false)
  await expect(page.getByRole("button", { name: "继续" })).toBeVisible()
})

test("长播单名称不会让场景绑定横向溢出", async ({ page }) => {
  const longName = `LONG_PLAYLIST_${"WALLPAPER_".repeat(20)}`
  await mockSetupApi(page, true, { ...profile, scenes: { day_work: longName } })
  await page.route("**/api/wallpaper-engine/playlist-scans", async (route) => {
    await route.fulfill({ json: {
      wallpaper_engine_path: profile.wallpaper_engine_path,
      playlists: [{ name: longName, item_count: 60 }],
    } })
  })
  await page.setViewportSize({ width: 1200, height: 780 })
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /场景绑定/ }).click()
  await expect(page.getByRole("heading", { name: "绑定使用场景" })).toBeVisible()

  const content = page.locator('[data-slot="card-content"]')
  const hasHorizontalOverflow = await content.evaluate((element) => element.scrollWidth > element.clientWidth)
  expect(hasHorizontalOverflow).toBe(false)
})

test("设置页可切换主题，记住选择并继续跟随系统", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.emulateMedia({ colorScheme: "light" })
  await page.goto("/?locale=zh")

  const theme = page.getByRole("group", { name: "外观" })
  await expect(theme.getByRole("button", { name: "跟随系统" })).toHaveAttribute("aria-pressed", "true")
  await expect(page.locator("html")).not.toHaveClass(/dark/)
  const lightBackground = await page.locator("body").evaluate((body) => getComputedStyle(body).backgroundColor)

  await theme.getByRole("button", { name: "深色" }).click()
  await expect(page.locator("html")).toHaveClass(/dark/)
  const darkBackground = await page.locator("body").evaluate((body) => getComputedStyle(body).backgroundColor)
  expect(darkBackground).not.toBe(lightBackground)
  await page.reload()
  await expect(page.getByRole("group", { name: "外观" }).getByRole("button", { name: "深色" })).toHaveAttribute("aria-pressed", "true")
  await expect(page.locator("html")).toHaveClass(/dark/)

  await page.getByRole("group", { name: "外观" }).getByRole("button", { name: "跟随系统" }).click()
  await expect(page.locator("html")).not.toHaveClass(/dark/)
  await page.emulateMedia({ colorScheme: "dark" })
  await expect(page.locator("html")).toHaveClass(/dark/)

  await page.getByRole("group", { name: "外观" }).getByRole("button", { name: "浅色" }).click()
  await expect(page.locator("html")).not.toHaveClass(/dark/)
})
