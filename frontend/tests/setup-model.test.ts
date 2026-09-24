import { expect, test } from "vitest"

import {
  isNonNegativeInteger,
  parseNumberInput,
  validationIssueField,
} from "../src/setup/model.ts"
import { stepForIssue } from "../src/setup/flow.ts"

test("number input parsing preserves valid and invalid numeric edits", () => {
  expect(parseNumberInput("42")).toBe(42)
  expect(parseNumberInput("1.5")).toBe(1.5)
  expect(parseNumberInput("-1")).toBe(-1)
  expect(parseNumberInput("")).toBeNull()
})

test("disturbance values must be non-negative integers", () => {
  expect(isNonNegativeInteger(0)).toBe(true)
  expect(isNonNegativeInteger(42)).toBe(true)
  expect(isNonNegativeInteger(1.5)).toBe(false)
  expect(isNonNegativeInteger(-1)).toBe(false)
  expect(isNonNegativeInteger(null)).toBe(false)
})

test("server validation paths map to setup fields", () => {
  expect(validationIssueField(["weather", "api_key"])).toBe("weather.api_key")
  expect(validationIssueField(["weather", "location", "latitude"])).toBe("weather.location.latitude")
  expect(validationIssueField(["activity", "work_processes", 0])).toBe("activity")
  expect(validationIssueField(["scenes", "day_work"])).toBe("scenes")
})

test("server validation paths map to the owning setup step", () => {
  expect(stepForIssue(["wallpaper_engine_path"])).toBe("wallpaper")
  expect(stepForIssue(["weather", "api_key"])).toBe("weather")
  expect(stepForIssue(["weather", "location"])).toBe("location")
  expect(stepForIssue(["scenes"])).toBe("scenes")
  expect(stepForIssue(["disturbance", "startup_grace_seconds"])).toBe("scheduling")
  expect(stepForIssue(["activity"])).toBe("activity")
})
