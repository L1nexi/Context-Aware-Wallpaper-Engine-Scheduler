# GUI Config Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Config tab to the Dashboard SPA that lets users edit playlists, scheduling params, and WE path through structured forms — eliminating JSON hand-editing.

**Architecture:** Three new Bottle API endpoints (`/api/config` GET/POST, `/api/tags/presets`, `/api/playlists/scan`) in the existing dashboard HTTP server. Frontend adds `ConfigView.vue` as a third tab in `DashboardView.vue`, with `useConfig.ts` composable for API communication. Tag vocabulary centralized as `KNOWN_TAGS` in `core/policies.py`.

**Tech Stack:** Python (Bottle, Pydantic v2, getpass, winreg), Vue 3 + TypeScript + Element Plus (el-form, el-table, el-slider, el-dialog)

---

## File Structure

| Action | File | Purpose |
|--------|------|---------|
| Modify | `core/policies.py` | Add `KNOWN_TAGS` constant |
| Modify | `ui/dashboard.py` | Add 4 endpoints + config_path wiring |
| Create | `utils/we_path.py` | WE installation path detection |
| Modify | `main.py` | Pass config_path to DashboardHTTPServer |
| Create | `dashboard/src/composables/useConfig.ts` | Config API composable |
| Create | `dashboard/src/views/ConfigView.vue` | Config editor main view |
| Create | `dashboard/src/components/PlaylistEditor.vue` | Playlist edit dialog |
| Create | `dashboard/src/components/SchedulingForm.vue` | Scheduling params form |
| Modify | `dashboard/src/views/DashboardView.vue` | Add Config tab |
| Create | `dashboard/src/components/ConfigSection.vue` | Reusable section wrapper |

---

### Task 1: Centralize tag vocabulary in `core/policies.py`

**Files:**
- Modify: `core/policies.py`

- [ ] **Step 1: Add KNOWN_TAGS constant**

At end of `core/policies.py`, before `POLICY_REGISTRY`:

```python
# ── Known Tags ─────────────────────────────────────────────────────
# Central vocabulary of all tags that policies may emit.
# Drive the UI tag palette via GET /api/tags/presets.
# When adding a new policy output tag, add it here.

KNOWN_TAGS: list[str] = sorted({
    # ActivityPolicy
    "#focus", "#chill",
    # TimePolicy
    "#dawn", "#day", "#sunset", "#night",
    # SeasonPolicy
    "#spring", "#summer", "#autumn", "#winter",
    # WeatherPolicy
    "#clear", "#cloudy", "#rain", "#storm", "#snow", "#fog",
})
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from core.policies import KNOWN_TAGS; assert len(KNOWN_TAGS) >= 15; print('KNOWN_TAGS OK:', KNOWN_TAGS[:5])"
```

---

### Task 2: WE installation path detection via Steam registry

**Files:**
- Create: `utils/we_path.py`

- [ ] **Step 1: Create we_path.py**

```python
"""
WE installation path detection.

Resolves wallpaper_engine_path in three tiers:
1. From scheduler_config (already configured)
2. Via Steam registry → libraryfolders.vdf search
3. Returns None if not found

Does NOT require WE to be running.
"""

from __future__ import annotations
import os
import sys
import logging

logger = logging.getLogger("WEScheduler.WEPath")


def _steam_install_path() -> str | None:
    """Read Steam install path from Windows registry."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for subkey in (r"Software\Valve\Steam", r"SOFTWARE\Valve\Steam"):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "SteamPath")
                    return val.replace("/", "\\")
            except OSError:
                continue
    return None


def _parse_library_folders(steam_path: str) -> list[str]:
    """Parse libraryfolders.vdf to get all Steam library roots."""
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf_path):
        return [steam_path]

    libraries = [steam_path]
    try:
        with open(vdf_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith('"path"'):
                    # Format: "path"\t\t"E:\\SteamLibrary"
                    parts = line.split('"')
                    if len(parts) >= 4:
                        lib = parts[3].replace("\\\\", "\\")
                        libraries.append(lib)
    except Exception:
        pass
    return libraries


def find_wallpaper_engine(config_wallpaper_engine_path: str) -> str | None:
    """Find wallpaper64.exe, returning the full path or None.

    Tier 1: Use the path from scheduler_config if it exists.
    Tier 2: Search Steam library folders for the WE installation.
    """
    # Tier 1: configured path
    if config_wallpaper_engine_path and os.path.isfile(config_wallpaper_engine_path):
        return config_wallpaper_engine_path

    # Tier 2: Steam library search
    steam = _steam_install_path()
    if steam:
        for lib in _parse_library_folders(steam):
            candidate = os.path.join(
                lib, "steamapps", "common", "wallpaper_engine", "wallpaper64.exe"
            )
            if os.path.isfile(candidate):
                logger.info("Found WE at: %s", candidate)
                return candidate

    return None


def find_we_config_json(config_wallpaper_engine_path: str) -> str | None:
    """Find WE's config.json given the wallpaper_engine_path from scheduler_config.

    Returns the full path to WE's config.json, or None.
    """
    we_exe = find_wallpaper_engine(config_wallpaper_engine_path)
    if we_exe:
        config_json = os.path.join(os.path.dirname(we_exe), "config.json")
        if os.path.isfile(config_json):
            return config_json
    return None
```

- [ ] **Step 2: Verify import**

```bash
python -c "from utils.we_path import find_wallpaper_engine, find_we_config_json; print('we_path OK')"
```

---

### Task 3: Add API endpoints to `ui/dashboard.py`

**Files:**
- Modify: `ui/dashboard.py`

- [ ] **Step 1: Add imports at top of dashboard.py**

After the existing `from core.scheduler import WEScheduler, Context, MatchResult`:

```python
import getpass
import os

from core.event_logger import EventType
from utils.config_loader import AppConfig
from utils.we_path import find_we_config_json
```

- [ ] **Step 2: Add _flatten_errors helper**

After `build_tick_state()` function:

```python
def _flatten_errors(exc) -> list[dict]:
    """Flatten Pydantic ValidationError to [{field, message}]."""
    errors: list[dict] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        errors.append({"field": loc, "message": err["msg"]})
    return errors
```

- [ ] **Step 3: Add _resolve_config_path**

```python
def _resolve_config_path() -> str:
    """Return the absolute path to scheduler_config.json."""
    import utils.app_context
    return os.path.join(utils.app_context.get_app_root(), "scheduler_config.json")
```

- [ ] **Step 4: Add 4 API routes inside `_build_app`**

In `_build_app()`, after the `@app.route('/api/history')` block:

```python
    # ── Config API routes ──────────────────────────────────────

    @app.route('/api/config')
    def api_config():
        bottle.response.content_type = 'application/json; charset=utf-8'
        config_path = _resolve_config_path()
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            AppConfig.model_validate(raw)  # ensure existing config is valid
        except FileNotFoundError:
            bottle.response.status = 404
            return json.dumps({"error": "config_not_found"})
        except ValueError as e:
            bottle.response.status = 500
            return json.dumps({"error": "invalid_config", "details": str(e)})
        return json.dumps(raw)

    @app.route('/api/config', method='POST')
    def api_config_save():
        bottle.response.content_type = 'application/json; charset=utf-8'
        data = bottle.request.json
        if data is None:
            bottle.response.status = 400
            return json.dumps({"error": "no_json_body"})
        try:
            AppConfig.model_validate(data)
        except ValueError as e:
            bottle.response.status = 422
            return json.dumps({
                "error": "validation_failed",
                "details": _flatten_errors(e),
            })

        config_path = _resolve_config_path()
        tmp = config_path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, config_path)
        except OSError as e:
            bottle.response.status = 500
            return json.dumps({"error": "write_failed", "details": str(e)})
        logger.info("Config saved via API")
        return json.dumps({"ok": True})

    @app.route('/api/tags/presets')
    def api_tags_presets():
        bottle.response.content_type = 'application/json; charset=utf-8'
        from core.policies import KNOWN_TAGS
        return json.dumps(list(KNOWN_TAGS))

    @app.route('/api/playlists/scan')
    def api_playlists_scan():
        bottle.response.content_type = 'application/json; charset=utf-8'
        config_path = _resolve_config_path()
        wallpaper_engine_path = ""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            wallpaper_engine_path = raw.get("wallpaper_engine_path", "")
        except Exception:
            pass

        we_config = find_we_config_json(wallpaper_engine_path)
        if we_config is None:
            return json.dumps({"playlists": [], "error": "we_config_not_found"})

        try:
            with open(we_config, 'r', encoding='utf-8') as f:
                we_data = json.load(f)
        except Exception:
            return json.dumps({"playlists": [], "error": "we_config_read_failed"})

        username = getpass.getuser()
        playlists = we_data.get(username, {}).get("general", {}).get("playlists", [])
        names = [p["name"] for p in playlists if isinstance(p, dict) and "name" in p]
        return json.dumps({"playlists": names})
```

The `config_path` is passed to `_build_app` and captured by the route handler closures. Remove the standalone `_resolve_config_path()` and use the closure variable throughout.

- [ ] **Step 6: Update `DashboardHTTPServer.__init__`**

```python
def __init__(
    self,
    state_store: StateStore,
    history_logger: EventLogger | None = None,
    config_path: str = "",
):
    self._state_store = state_store
    self._history: EventLogger | None = history_logger
    self._config_path = config_path
    self._httpd: _ThreadingWSGIServer | None = None
    self._thread: threading.Thread | None = None
    self.port: int = 0
```

- [ ] **Step 7: Pass config_path to `_build_app` in `start()`**

```python
def start(self) -> None:
    os.makedirs(_resolve_static_root(), exist_ok=True)
    app = _build_app(self._state_store, self._history, self._config_path)

    self._httpd = make_server("127.0.0.1", 0, app, server_class=_ThreadingWSGIServer)
    self.port = self._httpd.server_address[1]

    self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
    self._thread.start()
    logger.info("Dashboard HTTP server (bottle) on http://127.0.0.1:%d", self.port)
```

- [ ] **Step 8: Verify imports and route registration**

```bash
python -c "
from ui.dashboard import _build_app, StateStore
app = _build_app(StateStore(), config_path='test')
routes = [r.rule for r in app.routes]
for r in ['/api/config', '/api/tags/presets', '/api/playlists/scan', '/api/state']:
    assert r in routes, f'Missing route: {r}'
print('All routes OK')
"
```

---

### Task 4: Pass config_path to DashboardHTTPServer in main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Pass config_path in _run_tray_mode**

In `_run_tray_mode()`, change:
```python
httpd = DashboardHTTPServer(state_store, scheduler.history_logger)
```
To:
```python
httpd = DashboardHTTPServer(state_store, scheduler.history_logger, config_path)
```

---

### Task 5: useConfig composable

**Files:**
- Create: `dashboard/src/composables/useConfig.ts`

- [ ] **Step 1: Create useConfig.ts**

```typescript
import { ref } from 'vue'

export interface PlaylistConfig {
  name: string
  display?: string
  tags: Record<string, number>
}

export interface SchedulingConfig {
  startup_delay: number
  idle_threshold: number
  switch_cooldown: number
  cycle_cooldown: number
  force_after: number
  cpu_threshold: number
  cpu_sample_window: number
  pause_on_fullscreen: boolean
}

export interface AppConfig {
  wallpaper_engine_path: string
  language?: string | null
  playlists: PlaylistConfig[]
  tags: Record<string, { fallback: Record<string, number> }>
  policies: Record<string, unknown>
  scheduling: SchedulingConfig
}

export interface FieldError {
  field: string
  message: string
}

export interface SaveResult {
  ok: boolean
  errors?: FieldError[]
  message?: string
}

export interface ScanResult {
  playlists: string[]
  error?: string
}

export function useConfig() {
  const config = ref<AppConfig | null>(null)
  const loading = ref(false)
  const saveError = ref<string | null>(null)
  const saveSuccess = ref(false)
  const saving = ref(false)
  const tagPresets = ref<string[]>([])
  const wePlaylists = ref<string[]>([])

  async function fetchConfig(): Promise<void> {
    loading.value = true
    try {
      const res = await fetch('/api/config')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      config.value = await res.json()
    } catch (e) {
      saveError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function saveConfig(data: AppConfig): Promise<SaveResult> {
    saving.value = true
    saveError.value = null
    saveSuccess.value = false
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      const result = await res.json()
      if (!res.ok) {
        saveError.value = result.details?.[0]?.message || result.error || 'Unknown error'
        return { ok: false, errors: result.details, message: result.error }
      }
      saveSuccess.value = true
      config.value = data
      setTimeout(() => { saveSuccess.value = false }, 3000)
      return { ok: true }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      saveError.value = msg
      return { ok: false, message: msg }
    } finally {
      saving.value = false
    }
  }

  async function fetchTagPresets(): Promise<void> {
    try {
      const res = await fetch('/api/tags/presets')
      if (res.ok) tagPresets.value = await res.json()
    } catch { /* silent */ }
  }

  async function scanPlaylists(): Promise<void> {
    try {
      const res = await fetch('/api/playlists/scan')
      if (res.ok) {
        const data: ScanResult = await res.json()
        wePlaylists.value = data.playlists || []
      }
    } catch { /* silent */ }
  }

  return {
    config, loading, saveError, saveSuccess, saving,
    tagPresets, wePlaylists,
    fetchConfig, saveConfig, fetchTagPresets, scanPlaylists,
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd dashboard && npx vue-tsc --noEmit src/composables/useConfig.ts
```

---

### Task 6: SchedulingForm.vue component

**Files:**
- Create: `dashboard/src/components/SchedulingForm.vue`

- [ ] **Step 1: Create SchedulingForm.vue**

```vue
<script setup lang="ts">
import { inject, type Ref } from 'vue'
import type { SchedulingConfig } from '@/composables/useConfig'

const scheduling = inject<Ref<SchedulingConfig>>('editingScheduling')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

const sliders: { key: keyof SchedulingConfig; label: string; min: number; max: number; step: number; unit: string; tip: string }[] = [
  { key: 'startup_delay', label: 'startup_delay', min: 0, max: 120, step: 5, unit: 's', tip: 'Delay before first switch after startup' },
  { key: 'idle_threshold', label: 'idle_threshold', min: 0, max: 300, step: 5, unit: 's', tip: 'User must be idle this long before switching' },
  { key: 'switch_cooldown', label: 'switch_cooldown', min: 0, max: 7200, step: 30, unit: 's', tip: 'Minimum interval between playlist switches' },
  { key: 'cycle_cooldown', label: 'cycle_cooldown', min: 0, max: 3600, step: 30, unit: 's', tip: 'Minimum interval between wallpaper cycles within a playlist' },
  { key: 'force_after', label: 'force_after', min: 0, max: 86400, step: 300, unit: 's', tip: 'Force a switch if no change for this long' },
  { key: 'cpu_threshold', label: 'cpu_threshold', min: 50, max: 100, step: 1, unit: '%', tip: 'Defer switching when CPU exceeds this' },
  { key: 'cpu_sample_window', label: 'cpu_sample_window', min: 1, max: 60, step: 1, unit: 's', tip: 'CPU averaging window duration' },
]
</script>

<template>
  <div class="scheduling-form">
    <div v-for="s in sliders" :key="s.key" class="field-row">
      <div class="field-label">
        <span>{{ s.key.replace(/_/g, ' ') }}</span>
        <el-tooltip :content="s.tip" placement="right">
          <el-icon :size="14"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
      <el-slider
        v-model="scheduling[s.key]"
        :min="s.min" :max="s.max" :step="s.step"
        :format-tooltip="(val: number) => `${val}${s.unit}`"
        style="flex: 1; margin: 0 12px"
      />
      <span class="field-value">{{ scheduling[s.key] }}{{ s.unit }}</span>
    </div>
    <div class="field-row">
      <div class="field-label">
        <span>pause_on_fullscreen</span>
        <el-tooltip content="Pause switching when a fullscreen or presentation app is active" placement="right">
          <el-icon :size="14"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
      <el-switch v-model="scheduling.pause_on_fullscreen" />
    </div>
  </div>
</template>

<style scoped>
.scheduling-form { padding: 8px 0; }
.field-row {
  display: flex; align-items: center;
  padding: 10px 0; border-bottom: 1px solid var(--border-color, #2a3a5c);
}
.field-label {
  width: 180px; display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--text-secondary, #a0a0b8);
  text-transform: capitalize;
}
.field-value {
  min-width: 64px; text-align: right; font-size: 13px;
  font-variant-numeric: tabular-nums; color: var(--text-muted, #6c6c80);
}
</style>
```

---

### Task 7: PlaylistEditor.vue component

**Files:**
- Create: `dashboard/src/components/PlaylistEditor.vue`

- [ ] **Step 1: Create PlaylistEditor.vue**

```vue
<script setup lang="ts">
import { ref, reactive, watch, inject } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { PlaylistConfig } from '@/composables/useConfig'

const props = defineProps<{
  modelValue: boolean
  playlist: PlaylistConfig | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'save', playlist: PlaylistConfig): void
}>()

const tagPresets = inject<string[]>('tagPresets')!
const wePlaylists = inject<string[]>('wePlaylists')!

interface TagRow {
  key: number
  tag: string
  weight: number
}

const formRef = ref<FormInstance>()
const form = reactive({
  name: '',
  display: '',
  tags: [] as TagRow[],
})

const rules: FormRules = {
  name: [{ required: true, message: 'Playlist name is required', trigger: 'blur' }],
}

const validateTags = (_rule: unknown, value: TagRow[], callback: (e?: Error) => void) => {
  const filled = value.filter(r => r.tag.trim())
  if (filled.length === 0) {
    callback(new Error('At least one tag is required'))
  } else {
    callback()
  }
}

function initForm() {
  if (props.playlist) {
    form.name = props.playlist.name
    form.display = props.playlist.display || ''
    form.tags = Object.entries(props.playlist.tags).map(([tag, weight]) => ({
      key: Date.now() + Math.random(),
      tag,
      weight,
    }))
  } else {
    form.name = ''
    form.display = ''
    form.tags = [{ key: Date.now(), tag: '', weight: 1.0 }]
  }
}

watch(() => props.modelValue, (val) => {
  if (val) initForm()
})

function addTag() {
  form.tags.push({ key: Date.now(), tag: '', weight: 1.0 })
}

function removeTag(index: number) {
  form.tags.splice(index, 1)
}

function handleSave() {
  formRef.value?.validate((valid) => {
    if (!valid) return
    const tags: Record<string, number> = {}
    for (const row of form.tags) {
      if (row.tag.trim()) {
        tags[row.tag.trim()] = row.weight
      }
    }
    emit('save', {
      name: form.name.trim(),
      display: form.display.trim() || undefined,
      tags,
    })
    emit('update:modelValue', false)
  })
}

const dialogVisible = ref(props.modelValue)
watch(() => props.modelValue, (val) => { dialogVisible.value = val })
watch(dialogVisible, (val) => { emit('update:modelValue', val) })
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="playlist ? 'Edit Playlist' : 'New Playlist'"
    width="560px"
    destroy-on-close
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="Name" prop="name">
        <el-input
          v-model="form.name"
          placeholder="WE playlist name (e.g. CASUAL_ANIME)"
          :autocomplete="{
            fetchSuggestions: (qs: string, cb: (list: {value: string}[]) => void) => {
              cb(wePlaylists.filter(n => n.toLowerCase().includes(qs.toLowerCase())).map(n => ({ value: n })))
            },
          }"
        />
      </el-form-item>

      <el-form-item label="Display Name">
        <el-input v-model="form.display" placeholder="Optional display name (e.g. 次元日常)" />
      </el-form-item>

      <el-form-item label="Tags" prop="tags" :rules="[{ validator: validateTags, trigger: 'blur' }]">
        <el-table :data="form.tags" size="small">
          <el-table-column label="Tag" width="200">
            <template #default="scope">
              <el-select
                v-model="scope.row.tag"
                placeholder="Select tag"
                filterable
                allow-create
                style="width: 100%"
              >
                <el-option
                  v-for="t in tagPresets" :key="t"
                  :label="t" :value="t"
                />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="Weight" width="200">
            <template #default="scope">
              <el-slider
                v-model="scope.row.weight"
                :min="0" :max="2" :step="0.1"
                :format-tooltip="(val: number) => val.toFixed(1)"
                style="width: 140px"
              />
            </template>
          </el-table-column>

          <el-table-column label="Weight (value)" width="80">
            <template #default="scope">
              {{ scope.row.weight.toFixed(1) }}
            </template>
          </el-table-column>

          <el-table-column width="60">
            <template #default="scope">
              <el-button size="small" type="danger" :icon="Delete" circle @click="removeTag(scope.$index)" />
            </template>
          </el-table-column>
        </el-table>

        <el-button size="small" :icon="Plus" style="margin-top: 8px" @click="addTag">
          Add Tag
        </el-button>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="dialogVisible = false">Cancel</el-button>
      <el-button type="primary" @click="handleSave">Save</el-button>
    </template>
  </el-dialog>
</template>
```

---

### Task 8: ConfigView.vue main view

**Files:**
- Create: `dashboard/src/views/ConfigView.vue`

- [ ] **Step 1: Create ConfigView.vue**

```vue
<script setup lang="ts">
import { ref, provide, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, InfoFilled } from '@element-plus/icons-vue'
import { useConfig, type PlaylistConfig, type AppConfig } from '@/composables/useConfig'
import PlaylistEditor from '@/components/PlaylistEditor.vue'
import SchedulingForm from '@/components/SchedulingForm.vue'
import type { SchedulingConfig } from '@/composables/useConfig'

const {
  config, loading, saveError, saveSuccess, saving,
  tagPresets, wePlaylists,
  fetchConfig, saveConfig, fetchTagPresets, scanPlaylists,
} = useConfig()

provide('tagPresets', tagPresets)
provide('wePlaylists', wePlaylists)

const activeSubTab = ref('playlists')
const showEditor = ref(false)
const editingPlaylist = ref<PlaylistConfig | null>(null)
const editingScheduling = ref<SchedulingConfig>({
  startup_delay: 15,
  idle_threshold: 60,
  switch_cooldown: 1800,
  cycle_cooldown: 600,
  force_after: 14400,
  cpu_threshold: 85,
  cpu_sample_window: 10,
  pause_on_fullscreen: true,
})
const wallpaperEnginePath = ref('')
const wePathDetected = ref(false)

provide('editingScheduling', editingScheduling)

onMounted(async () => {
  await Promise.all([fetchConfig(), fetchTagPresets(), scanPlaylists()])
  if (config.value) {
    wallpaperEnginePath.value = config.value.wallpaper_engine_path || ''
    editingScheduling.value = { ...config.value.scheduling }
  }
})

watch(() => config.value?.wallpaper_engine_path, (val) => {
  if (val && !wePathDetected.value) {
    wallpaperEnginePath.value = val
  }
})

function openNewPlaylist() {
  editingPlaylist.value = null
  showEditor.value = true
}

function openEditPlaylist(pl: PlaylistConfig) {
  editingPlaylist.value = { ...pl }
  showEditor.value = true
}

function deletePlaylist(index: number) {
  if (!config.value) return
  config.value.playlists.splice(index, 1)
}

function handlePlaylistSave(pl: PlaylistConfig) {
  if (!config.value) return
  // Find existing by name and replace, or add
  const idx = config.value.playlists.findIndex(p => p.name === pl.name)
  if (idx >= 0) {
    config.value.playlists[idx] = pl
  } else {
    config.value.playlists.push(pl)
  }
}

async function handleSave() {
  if (!config.value) return
  const data: AppConfig = {
    ...config.value,
    wallpaper_engine_path: wallpaperEnginePath.value,
    scheduling: { ...editingScheduling.value },
  }
  const result = await saveConfig(data)
  if (result.ok) {
    ElMessage.success('Configuration saved')
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><InfoFilled /></el-icon>
      <span>Configuration</span>
    </div>
    <div class="panel-body config-body">
      <el-skeleton v-if="loading" :rows="6" animated />

      <template v-else-if="config">
        <!-- WE Path (always visible) -->
        <div class="config-section">
          <div class="section-title">Wallpaper Engine Path</div>
          <el-input v-model="wallpaperEnginePath" placeholder="C:\...\wallpaper64.exe" />
          <div v-if="wePathDetected" class="path-hint">Auto-detected from Steam installation</div>
        </div>

        <!-- Sub-tabs -->
        <el-tabs v-model="activeSubTab">
          <el-tab-pane label="Playlists" name="playlists">
            <div class="playlist-list">
              <div
                v-for="(pl, idx) in config.playlists" :key="pl.name"
                class="playlist-card"
              >
                <div class="pl-info">
                  <span class="pl-name">{{ pl.name }}</span>
                  <span v-if="pl.display" class="pl-display">{{ pl.display }}</span>
                </div>
                <div class="pl-tags">
                  <el-tag
                    v-for="(w, t) in pl.tags" :key="t"
                    size="small" type="info"
                  >
                    {{ t }} {{ (w as number).toFixed(1) }}
                  </el-tag>
                </div>
                <div class="pl-actions">
                  <el-button size="small" :icon="Edit" circle @click="openEditPlaylist(pl)" />
                  <el-button size="small" :icon="Delete" circle type="danger" @click="deletePlaylist(idx)" />
                </div>
              </div>
              <el-button :icon="Plus" style="margin-top: 8px" @click="openNewPlaylist">
                Add Playlist
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane label="Scheduling" name="scheduling">
            <SchedulingForm />
          </el-tab-pane>

          <el-tab-pane label="Advanced" name="advanced">
            <div class="placeholder-tab">
              <p>Policy configuration and tag fallback editing coming soon.</p>
              <p>For now, edit these sections directly in <code>scheduler_config.json</code>.</p>
            </div>
          </el-tab-pane>
        </el-tabs>

        <!-- Save bar -->
        <div class="save-bar">
          <el-alert v-if="saveError" :title="saveError" type="error" show-icon closable @close="saveError = null" />
          <el-button type="primary" :loading="saving" @click="handleSave">
            Save Configuration
          </el-button>
        </div>
      </template>

      <el-empty v-else :image-size="48" description="Failed to load configuration" />
    </div>

    <PlaylistEditor
      v-model="showEditor"
      :playlist="editingPlaylist"
      @save="handlePlaylistSave"
    />
  </div>
</template>

<style scoped>
.config-body { padding: 16px; }
.config-section {
  padding: 12px 0; border-bottom: 1px solid var(--border-color, #2a3a5c);
  margin-bottom: 12px;
}
.section-title {
  font-size: 13px; color: var(--text-secondary, #a0a0b8);
  margin-bottom: 8px;
}
.path-hint {
  font-size: 12px; color: var(--success, #67c23a); margin-top: 4px;
}
.playlist-list { display: flex; flex-direction: column; gap: 8px; }
.playlist-card {
  display: flex; align-items: center; gap: 16px;
  padding: 12px; background: var(--bg-card, #1f2b47);
  border-radius: var(--radius, 8px);
}
.pl-info { min-width: 140px; }
.pl-name { font-weight: 600; display: block; }
.pl-display { font-size: 12px; color: var(--text-muted, #6c6c80); }
.pl-tags { flex: 1; display: flex; gap: 4px; flex-wrap: wrap; }
.pl-actions { display: flex; gap: 4px; }
.placeholder-tab { padding: 24px; text-align: center; color: var(--text-muted, #6c6c80); }
.placeholder-tab code { background: var(--bg-card, #1f2b47); padding: 2px 6px; border-radius: 4px; }
.save-bar {
  margin-top: 16px; padding-top: 16px;
  border-top: 1px solid var(--border-color, #2a3a5c);
  display: flex; flex-direction: column; gap: 8px; align-items: flex-end;
}
</style>
```

---

### Task 9: Add Config tab to DashboardView.vue

**Files:**
- Modify: `dashboard/src/views/DashboardView.vue`

- [ ] **Step 1: Import ConfigView and add tab**

Change the `<script setup>` block:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import StatusBar from '@/components/StatusBar.vue'
import CurrentPlaylist from '@/components/CurrentPlaylist.vue'
import ConfidencePanel from '@/components/ConfidencePanel.vue'
import TagChart from '@/components/TagChart.vue'
import ContextPanel from '@/components/ContextPanel.vue'
import HistoryView from '@/views/HistoryView.vue'
import ConfigView from '@/views/ConfigView.vue'

const activeTab = ref('live')
</script>
```

Add Config tab pane in template:

```vue
      <el-tab-pane label="Config" name="config">
        <ConfigView />
      </el-tab-pane>
```

The template becomes:

```vue
<template>
  <div class="dashboard-container">
    <StatusBar />
    <el-tabs v-model="activeTab">
      <el-tab-pane label="Live" name="live">
        <div class="dashboard-grid">
          <CurrentPlaylist />
          <ConfidencePanel />
          <TagChart />
          <ContextPanel />
        </div>
      </el-tab-pane>
      <el-tab-pane label="History" name="history">
        <HistoryView />
      </el-tab-pane>
      <el-tab-pane label="Config" name="config">
        <ConfigView />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
```

---

### Task 10: Build and verify

**Files:** None (verification only)

- [ ] **Step 1: Frontend type-check**

```bash
cd dashboard && npm run type-check
```
Expected: no errors.

- [ ] **Step 2: Frontend build**

```bash
cd dashboard && npm run build
```
Expected: successful build to `dashboard/dist/`.

- [ ] **Step 3: Python import chain**

```bash
python -c "
from core.policies import KNOWN_TAGS
from utils.we_path import find_wallpaper_engine, find_we_config_json
from ui.dashboard import _build_app, StateStore
app = _build_app(StateStore(), config_path='test')
routes = [r.rule for r in app.routes]
for expected in ['/api/config', '/api/tags/presets', '/api/playlists/scan']:
    assert expected in routes, f'Missing: {expected}'
print('All imports and routes OK')
"
```

- [ ] **Step 4: Integration smoke test**

```bash
python main.py --no-tray
# Ctrl+C after a few seconds. Verify in logs:
# - "Dashboard HTTP server (bottle) on http://127.0.0.1:XXXXX"
# - No import errors
```

- [ ] **Step 5: API endpoint smoke test** (while main.py --no-tray is running in background)

```bash
# In another terminal:
PORT=<from startup log>
curl http://127.0.0.1:$PORT/api/tags/presets
# Expected: ["#autumn","#chill","#clear",...]

curl http://127.0.0.1:$PORT/api/config | python -m json.tool
# Expected: pretty-printed config JSON

curl http://127.0.0.1:$PORT/api/playlists/scan
# Expected: {"playlists": [...]}
```

- [ ] **Step 6: Verify hot-reload after config save**

Edit config via the API, then check logs to confirm the scheduler detected and reloaded the config change.

---

### Task 11 (optional): WE path auto-detection integration

**Files:**
- Modify: `dashboard/src/views/ConfigView.vue`

- [ ] **Step 1: Add auto-detect hint in ConfigView**

In `onMounted()`, after loading config, call `findWallpaperEngine()` via a new `/api/we-path/detect` endpoint:

OR simpler: `/api/playlists/scan` already runs `find_we_config_json` which internally calls `find_wallpaper_engine`. If the scan succeeds, we know WE is found. Add a `detected_we_path` field to the scan response:

In `api_playlists_scan()`, also return the detected WE exe path:

```python
we_exe = find_wallpaper_engine(wallpaper_engine_path)
return json.dumps({
    "playlists": names,
    "detected_we_path": we_exe or "",
})
```

Then in `ConfigView.vue`, when `detected_we_path` is returned and `wallpaperEnginePath` is empty, autofill:

```typescript
async function onMountedTasks() {
  await Promise.all([fetchConfig(), fetchTagPresets(), scanPlaylists()])
  // ... if wallpaperEnginePath is empty but we detected one, use it
}
```

This avoids a separate endpoint. The scan already locates WE. Just add the field to the response.
