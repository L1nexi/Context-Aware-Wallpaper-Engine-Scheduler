import assert from "node:assert/strict"
import test from "node:test"

import {
  isNonNegativeInteger,
  parseNumberInput,
  validationIssueField,
  validationIssueStep,
} from "../src/setup/model.ts"

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
  assert.equal(validationIssueStep(["wallpaper_engine_path"]), 0)
  assert.equal(validationIssueStep(["weather", "api_key"]), 1)
  assert.equal(validationIssueStep(["weather", "location"]), 2)
  assert.equal(validationIssueStep(["scenes"]), 3)
  assert.equal(validationIssueStep(["disturbance", "startup_grace_seconds"]), 4)
  assert.equal(validationIssueStep(["activity"]), 5)
})
