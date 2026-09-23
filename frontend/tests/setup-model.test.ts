import assert from "node:assert/strict"
import test from "node:test"

import {
  isNonNegativeInteger,
  parseNumberInput,
  validationIssueField,
} from "../src/setup/model.ts"
import { stepForIssue } from "../src/setup/flow.ts"

test("number input parsing preserves valid and invalid numeric edits", () => {
  assert.equal(parseNumberInput("42"), 42)
  assert.equal(parseNumberInput("1.5"), 1.5)
  assert.equal(parseNumberInput("-1"), -1)
  assert.equal(parseNumberInput(""), null)
})

test("disturbance values must be non-negative integers", () => {
  assert.equal(isNonNegativeInteger(0), true)
  assert.equal(isNonNegativeInteger(42), true)
  assert.equal(isNonNegativeInteger(1.5), false)
  assert.equal(isNonNegativeInteger(-1), false)
  assert.equal(isNonNegativeInteger(null), false)
})

test("server validation paths map to setup fields", () => {
  assert.equal(validationIssueField(["weather", "api_key"]), "weather.api_key")
  assert.equal(validationIssueField(["weather", "location", "latitude"]), "weather.location.latitude")
  assert.equal(validationIssueField(["activity", "work_processes", 0]), "activity")
  assert.equal(validationIssueField(["scenes", "day_work"]), "scenes")
})

test("server validation paths map to the owning setup step", () => {
  assert.equal(stepForIssue(["wallpaper_engine_path"]), "wallpaper")
  assert.equal(stepForIssue(["weather", "api_key"]), "weather")
  assert.equal(stepForIssue(["weather", "location"]), "location")
  assert.equal(stepForIssue(["scenes"]), "scenes")
  assert.equal(stepForIssue(["disturbance", "startup_grace_seconds"]), "scheduling")
  assert.equal(stepForIssue(["activity"]), "activity")
})
