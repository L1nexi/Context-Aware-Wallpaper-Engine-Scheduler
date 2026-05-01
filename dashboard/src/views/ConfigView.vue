<script setup lang="ts">
import { ref, provide, inject, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, InfoFilled } from '@element-plus/icons-vue'
import { useConfig, type PlaylistConfig, type SchedulingConfig, type AppConfig } from '@/composables/useConfig'
import PlaylistEditor from '@/components/PlaylistEditor.vue'
import SchedulingForm from '@/components/SchedulingForm.vue'
import PolicyEditor from '@/components/PolicyEditor.vue'
import TagEditor from '@/components/TagEditor.vue'

const {
  config, loading, saveError, saving, isDirty,
  tagPresets, wePlaylists,
  fetchConfig, saveConfig, fetchTagPresets, scanPlaylists,
} = useConfig()

const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

provide('tagPresets', tagPresets)
provide('wePlaylists', wePlaylists)
provide('config', config)

const activeTab = ref('playlists')
const showEditor = ref(false)
const editingPlaylist = ref<PlaylistConfig | null>(null)
let editingOriginalName: string | null = null
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

provide('editingScheduling', editingScheduling)

watch(editingScheduling, (val) => {
  if (config.value) config.value.scheduling = val
}, { deep: true })

watch(wallpaperEnginePath, (val) => {
  if (config.value) config.value.wallpaper_engine_path = val
})

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (isDirty.value) {
    e.preventDefault()
    e.returnValue = t('config_unsaved_changes')
    return t('config_unsaved_changes')
  }
}

onMounted(async () => {
  await Promise.all([fetchConfig(), fetchTagPresets(), scanPlaylists()])
  if (config.value) {
    wallpaperEnginePath.value = config.value.wallpaper_engine_path || ''
    editingScheduling.value = { ...config.value.scheduling }
  }
  window.addEventListener('beforeunload', onBeforeUnload)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
})

function openNewPlaylist() {
  editingPlaylist.value = null
  showEditor.value = true
}

function openEditPlaylist(pl: PlaylistConfig) {
  editingOriginalName = pl.name
  editingPlaylist.value = { ...pl }
  showEditor.value = true
}

function deletePlaylist(index: number) {
  if (!config.value) return
  config.value.playlists.splice(index, 1)
}

async function handleRetry() {
  saveError.value = null
  await fetchConfig()
  if (config.value) {
    wallpaperEnginePath.value = config.value.wallpaper_engine_path || ''
    editingScheduling.value = { ...config.value.scheduling }
  }
}

function handlePlaylistSave(pl: PlaylistConfig) {
  if (!config.value) return
  const searchName = editingOriginalName ?? pl.name
  const idx = config.value.playlists.findIndex(p => p.name === searchName)
  if (idx >= 0) {
    config.value.playlists[idx] = pl
  } else {
    config.value.playlists.push(pl)
  }
  editingOriginalName = null
}

async function handleSave() {
  if (!config.value) return
  const data: AppConfig = {
    ...config.value,
    wallpaper_engine_path: wallpaperEnginePath.value,
    scheduling: { ...editingScheduling.value },
  }
  for (const key of Object.keys(data.tags)) {
    const fb = data.tags[key]?.fallback
    if (fb && '' in fb) delete fb['']
  }
  const result = await saveConfig(data)
  if (result.ok) {
    ElMessage.success(t('config_saved'))
  }
}

async function autoDetectWePath() {
  const detected = await (window as any).pywebview?.api?.we_path?.()
  if (detected) wallpaperEnginePath.value = detected
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ t('config') }}</span>
    </div>
    <div class="panel-body config-body">
      <el-skeleton v-if="loading" :rows="6" animated />

      <div v-else-if="!config" class="config-error">
        <el-alert v-if="saveError" :title="saveError" type="error" show-icon />
        <el-empty v-else :image-size="48" :description="t('config_load_failed')" />
        <el-button style="margin-top: 12px; display: block; margin-left: auto; margin-right: auto;" type="primary" @click="handleRetry">{{ t('config_retry') }}</el-button>
      </div>

      <template v-else>
        <!-- WE Path bar -->
        <div class="we-bar">
          <span class="we-bar-label">{{ t('config_we_path') }}</span>
          <el-input v-model="wallpaperEnginePath" :placeholder="t('config_we_placeholder')" size="small" style="flex: 1" />
          <el-button size="small" @click="autoDetectWePath">{{ t('config_auto_detect') }}</el-button>
        </div>

        <!-- Tabs -->
        <el-tabs v-model="activeTab">
          <el-tab-pane :label="t('config_playlists')" name="playlists">
            <p class="tab-intro">{{ t('config_playlists_intro') }}</p>
            <div class="playlist-list">
              <div
                v-for="(pl, idx) in config.playlists" :key="pl.name"
                class="playlist-card"
              >
                <div class="pl-info">
                  <span class="pl-name">{{ pl.display || pl.name }}</span>
                  <span class="pl-display">{{ pl.display ? pl.name : '' }}</span>
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
                {{ t('config_add_playlist') }}
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="t('config_policies')" name="policies" lazy>
            <p class="tab-intro">{{ t('config_policies_intro') }}</p>
            <PolicyEditor />
          </el-tab-pane>

          <el-tab-pane :label="t('config_tags_tab')" name="tags" lazy>
            <p class="tab-intro">{{ t('config_tags_intro') }}</p>
            <TagEditor />
          </el-tab-pane>

          <el-tab-pane :label="t('config_scheduling')" name="scheduling">
            <p class="tab-intro">{{ t('config_scheduling_intro') }}</p>
            <SchedulingForm />
          </el-tab-pane>
        </el-tabs>

        <!-- Save bar -->
        <div class="save-bar">
          <span v-if="isDirty" style="font-size: 12px; color: #e6a23c">● {{ t('config_unsaved_indicator') }}</span>
          <el-alert v-if="saveError" :title="saveError" type="error" show-icon closable @close="saveError = null" />
          <el-button type="primary" :loading="saving" @click="handleSave">
            {{ t('config_save') }}
          </el-button>
        </div>
      </template>
    </div>

    <PlaylistEditor
      v-model="showEditor"
      :playlist="editingPlaylist"
      @save="handlePlaylistSave"
    />
  </div>
</template>

<style scoped>
.config-body { padding: 16px; overflow-y: auto; }

/* WE path bar */
.we-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 6px; margin-bottom: 12px;
}
.we-bar-label { font-size: 13px; font-weight: 600; white-space: nowrap; }

/* Tab intro text */
.tab-intro {
  font-size: 12px; color: #909399; margin: 0 0 12px 0; line-height: 1.5;
}

/* Playlist cards (unchanged) */
.playlist-list { display: flex; flex-direction: column; gap: 8px; }
.playlist-card {
  display: flex; align-items: center; gap: 16px;
  padding: 12px; background: #f0f2f5;
  border-radius: 8px;
}
.pl-info { min-width: 140px; }
.pl-name { font-weight: 600; display: block; }
.pl-display { font-size: 12px; color: #909399; display: block; }
.pl-tags { flex: 1; display: flex; gap: 4px; flex-wrap: wrap; }
.pl-actions { display: flex; gap: 4px; }

/* Save bar */
.save-bar {
  margin-top: 16px; padding-top: 16px;
  border-top: 1px solid var(--el-border-color, #e4e7ed);
  display: flex; flex-direction: column; gap: 8px; align-items: flex-end;
}

/* Error state */
.config-error {
  padding: 24px; text-align: center;
}
</style>
