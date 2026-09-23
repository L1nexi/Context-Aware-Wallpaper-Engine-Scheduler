import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

const profile = {
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

async function mockSetupApi(page: Page, hasProfile: boolean): Promise<void> {
  await page.route("**/api/profile", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill(hasProfile ? { json: { profile } } : { status: 404, json: { error: "profile_not_found" } })
      return
    }
    await route.fulfill({ json: { status: "applied", profile } })
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
  await expect(page.getByText(/请为每个已选场景指定播放列表/)).toBeVisible()
  await page.getByRole("button", { name: "继续" }).click()
  await expect(page.getByText("至少启用并绑定一个场景。")).toBeVisible()
})

test("天气页测试 Key 时说明代理失败原因", async ({ page }) => {
  await mockSetupApi(page, true)
  await page.route("**/api/weather-key-validations", async (route) => {
    await route.fulfill({ status: 503, json: { error: "weather_validation_unavailable", reason: "proxy_error" } })
  })
  await page.goto("/?locale=zh")
  await page.getByRole("button", { name: /天气服务/ }).click()
  await expect(page.getByText("如何获取 API Key")).toBeVisible()
  await expect(page.getByText("进入账户", { exact: true })).toBeVisible()
  await expect(page.getByText("复制到的是 Key 本身，不含网址或参数名。")).toBeVisible()
  await page.getByRole("button", { name: "测试连接" }).click()
  await expect(page.getByText(/代理连接失败/)).toBeVisible()
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
