# Config UI Completion Spec

## Context

The config GUI MVP (`2026-04-30-gui-config-editor-design.md`) shipped with Playlist CRUD, Scheduling sliders, and an "Advanced" placeholder tab. This iteration fills the gap: Policies configuration, Tag fallback graph editing, plus UX polish (dirty-state guard, validation, batch tag add). The goal is that **no `scheduler_config.json` key requires manual JSON editing**.

## Design Decisions

| Decision             | Choice                                                                                                    |
| -------------------- | --------------------------------------------------------------------------------------------------------- |
| Top-level tabs       | Playlists \| Policies \| Tags \| Scheduling (4 tabs)                                                      |
| WE path placement    | Compact bar above tabs (always visible)                                                                   |
| Language field       | Removed (auto-detected from OS locale)                                                                    |
| Tab intro text       | Each tab has a 1-2 sentence description at the top                                                        |
| Policies sub-layout  | Left: policy selector list. Right: enabled toggle + weight_scale + type-specific form for selected policy |
| Tag fallback editing | Left: tag selector list. Right: fallback table (target + weight slider) for selected tag                  |
| API key display      | `el-input type="password" show-password` with built-in toggle — no custom masking needed                   |
| Policy common fields | Enabled toggle + weight_scale slider on each policy card                                                  |
| Unknown policies     | Silently preserved on save (not shown in UI)                                                              |
| Validation           | Real-time per-field, mirrors backend Pydantic rules                                                       |
| API granularity      | Unchanged: full GET/POST `/api/config`                                                                    |
| Dirty state          | `beforeunload` guard on page close; tab switches preserve unsaved state                                   |
| Playlist tags        | Batch-add: multi-select tags, set weight once for all selected                                            |

## File Changes

| File                                        | Action       | Scope                                                                                                              |
| ------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------ |
| `dashboard/src/views/ConfigView.vue`        | Major rework | 4-tab structure, WE bar, dirty-state tracking, orchestrate new components                                          |
| `dashboard/src/views/PlaylistEditor.vue`    | Modify       | Batch tag add (multi-select + batch weight)                                                                        |
| `dashboard/src/components/PolicyEditor.vue` | **NEW**      | Left policy list + right detail panel: enabled toggle, weight_scale slider, type-specific form for selected policy |
| `dashboard/src/components/TagEditor.vue`    | **NEW**      | Left tag list + right fallback table (target tag selector, weight slider, add/delete rows)                         |
| `dashboard/src/composables/useConfig.ts`    | Modify       | Dirty-state tracking (`isDirty` ref, snapshot comparison)                                                          |
| `dashboard/src/i18n/en.json`                | Add keys     | ~25-30 keys for policy fields, tag editor, intro text, validation                                                  |
| `dashboard/src/i18n/zh.json`                | Add keys     | Same keys, Chinese translations                                                                                    |

**No backend changes.** `ui/dashboard.py` and `utils/config_loader.py` are untouched.

## Component Design

### PolicyEditor.vue

Two-column layout (same pattern as TagEditor):

- **Left** (`width: 180px`): scrollable policy list. Each item shows policy name + enabled indicator (colored dot). Highlights selected policy. Only shows policies that exist in the config (unknown policies silently skipped).
- **Right**: detail panel for selected policy:
  - Header: policy name + enabled `el-switch`
  - `weight_scale`: `el-slider` (0-3, step 0.1) with `show-input` — combines slider + numeric input in one control
  - Type-specific form below

**Type-specific forms (rendered in right panel):**

| Policy   | Fields                                                                                                                                                                                                  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Activity | `process_rules`: key-value rows (process name input → tag `el-select` with `filterable` + `allow-create`, add/delete row). `title_rules`: same layout. `smoothing_window`: `el-input-number` (min=1, seconds) |
| Time     | `auto`: el-switch. `day_start_hour` / `night_start_hour`: `el-input-number` (min=0, max=24). Auto enabled → inputs read-only; auto disabled → manual inputs enabled |
| Season   | 4× `el-input-number` (min=1, max=365): spring/summer/autumn/winter peak day-of-year. Each with label and default |
| Weather  | `api_key`: `el-input type="password" show-password`. `lat`/`lon`: `el-input-number` (precision=4, lat: -90..90, lon: -180..180). `fetch_interval`, `request_timeout`, `warmup_timeout`: `el-input-number` (min=1, seconds) |

Data flow: v-model binds to `config.policies`. Selection state tracked by `selectedPolicy: string | null` ref.

### TagEditor.vue

Two-column layout:

- **Left** (`width: 180px`): scrollable tag list. Highlights selected tag. "Add tag" button at bottom.
- **Right**: fallback table for selected tag.
  - Header row: "Target Tag" | "Weight" | [delete]
  - Each row: tag dropdown (filterable, allow-create) | weight slider (0-2, step 0.1) | delete button
  - "Add fallback" button below table

Data flow: v-model binds to `config.tags` (the full `Record<string, { fallback: Record<string, number> }>` object). Edits mutate this object directly (Vue reactivity tracks nested changes for dirty-state detection).

### ConfigView.vue (rework)

Structure:

```
┌─ WE path bar (always visible) ──────────────────────────┐
│  [input: wallpaper_engine_path]  [Auto-detect button]    │
├─ el-tabs ───────────────────────────────────────────────┤
│  Playlists | Policies | Tags | Scheduling                │
├─ intro text (varies per tab) ───────────────────────────┤
├─ tab body ──────────────────────────────────────────────┤
│  Playlists: existing playlist list + Add/Edit            │
│  Policies:  PolicyEditor (left list + right detail)       │
│  Tags:      TagEditor                                    │
│  Scheduling: existing SchedulingForm                     │
├─ save bar ──────────────────────────────────────────────┤
│  [unsaved indicator]              [Save Configuration]   │
└──────────────────────────────────────────────────────────┘
```

## Dirty-State Tracking

In `useConfig.ts`:

- On `fetchConfig()` success, store `savedSnapshot = JSON.stringify(config)`
- `isDirty` computed: `JSON.stringify(currentConfig) !== savedSnapshot`
- On `saveConfig()` success, update snapshot
- ConfigView registers `window.onbeforeunload` when `isDirty` is true

## Validation Rules (Frontend)

| Field                                | Rule                                 | Trigger   |
| ------------------------------------ | ------------------------------------ | --------- |
| `wallpaper_engine_path`              | Non-empty, ends with `.exe`          | on blur   |
| Playlist `name`                      | Non-empty, matches `^[A-Za-z0-9_]+$` | on input  |
| Playlist `tags`                      | ≥ 1 tag, all weights > 0             | on change |
| Fallback `weight`                    | 0.0 – 2.0                            | on change |
| `weight_scale`                       | ≥ 0                                  | on input  |
| Hour fields (day_start, night_start) | 0 – 24                               | on input  |
| `lat` / `lon`                        | -90..90 / -180..180                  | on blur   |
| `cpu_threshold`                      | 0 – 100                              | on input  |
| Season peak days                     | 1 – 365                              | on input  |

All validation errors display inline below the field. Implementation: use `el-form` with `rules` per `el-form-item`, `trigger: 'change'` (or `['blur', 'change']` for path/coords) for real-time feedback. Custom validator functions for cross-field rules (e.g. day_start < night_start). Backend 422 errors are mapped back to fields as a fallback via `formRef.validateField()`.

## Implementation Notes (from Element Plus / Vue 3 docs)

- **`el-input type="password" show-password`**: Built-in eye-icon toggle for reveal/hide. No custom masking logic needed for Weather API key.
- **`el-slider show-input`**: Combines slider + numeric input. Use for all `weight_scale` sliders and Scheduling sliders.
- **`el-tab-pane lazy`**: Set on Policies and Tags tab-panes so `PolicyEditor`/`TagEditor` are not instantiated until first visit.
- **`el-form-item` inline `rules`**: Each field carries its own `rules` array with `trigger` per rule. No need for a central `rules` object — cleaner for dynamic forms like process_rules table.
- **`window.onbeforeunload`**: Browser API for "unsaved changes" dialog. Not a Vue composable — set directly in ConfigView's `onMounted`.
- **`el-select` with `filterable` + `allow-create`**: Enables typing arbitrary tag names that aren't in presets. Use `default-first-option` for Enter-to-select. For batch tag add in PlaylistEditor: add `multiple`.
- **`el-input-number` over `el-input`**: Use for ALL numeric fields — built-in `:min`/`:max`/`:step`/`:precision` provide free validation and prevent invalid keystrokes.

## i18n Keys to Add

```
# Tab intros
config_playlists_intro, config_policies_intro, config_tags_intro, config_scheduling_intro

# Policy card
policy_activity, policy_time, policy_season, policy_weather
policy_enabled, policy_weight_scale, policy_weight_scale_tip

# Activity policy
activity_process_rules, activity_title_rules, activity_smoothing_window
activity_add_rule, activity_process_placeholder, activity_title_placeholder

# Time policy
time_auto, time_day_start, time_night_start, time_day_start_tip, time_night_start_tip

# Season policy
season_spring_peak, season_summer_peak, season_autumn_peak, season_winter_peak

# Weather policy
weather_api_key, weather_lat, weather_lon
weather_fetch_interval, weather_request_timeout, weather_warmup_timeout

# Tag editor
tags_add_tag, tags_fallbacks_for, tags_target_tag, tags_add_fallback, tags_weight
tags_no_fallbacks

# Validation
validation_required, validation_invalid_path, validation_invalid_name
validation_need_tags, validation_weight_range, validation_hour_range
validation_lat_range, validation_lon_range

# Dirty state
config_unsaved_changes
```

## Verification

```bash
cd dashboard && npm run type-check && npm run build
```

Build must pass with zero errors.

Manual verification:

1. Launch with `--no-tray`, open dashboard → Config tab
2. WE path bar visible and editable; auto-detect button works
3. Playlists tab: create a playlist with batch tag add (multi-select → set weight)
4. Policies tab: select Activity in left list → toggle enabled, adjust weight_scale, add/remove process/title rules in right panel
5. Policies tab: select Time/Season/Weather, verify type-specific forms render correctly. Weather API key uses `show-password` toggle (built-in eye icon)
6. Tags tab: select #dawn, edit its fallback edges, add new tag
7. Scheduling tab: existing sliders still work
8. Make a change without saving, try to close page → confirm dialog appears
9. Save config, verify `scheduler_config.json` on disk reflects changes
10. Unknown policy keys (mood) survive round-trip: edit something else, save, verify mood section untouched
