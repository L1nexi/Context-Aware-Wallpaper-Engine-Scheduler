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

// These are provided by the parent ConfigView
const tagPresets = inject<string[]>('tagPresets')!
const wePlaylists = inject<string[]>('wePlaylists')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

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
  name: [{ required: true, message: t('config_playlist_name_required'), trigger: 'blur' }],
}

const validateTags = (_rule: unknown, value: TagRow[], callback: (e?: Error) => void) => {
  const filled = value.filter(r => r.tag.trim())
  if (filled.length === 0) {
    callback(new Error(t('config_at_least_one_tag')))
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
    :title="playlist ? t('config_edit_playlist') : t('config_new_playlist')"
    width="560px"
    destroy-on-close
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item :label="t('config_name')" prop="name">
        <el-input
          v-model="form.name"
          :placeholder="t('config_playlist_name_placeholder')"
        />
      </el-form-item>

      <el-form-item :label="t('config_display_name')">
        <el-input v-model="form.display" :placeholder="t('config_display_name_placeholder')" />
      </el-form-item>

      <el-form-item :label="t('config_tags')" prop="tags" :rules="[{ validator: validateTags, trigger: 'blur' }]">
        <el-table :data="form.tags" size="small">
          <el-table-column :label="t('config_tags')" width="200">
            <template #default="scope">
              <el-select
                v-model="scope.row.tag"
                :placeholder="t('config_tags')"
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

          <el-table-column :label="t('config_weight')" width="200">
            <template #default="scope">
              <el-slider
                v-model="scope.row.weight"
                :min="0" :max="2" :step="0.1"
                :format-tooltip="(val: number) => val.toFixed(1)"
                style="width: 140px"
              />
            </template>
          </el-table-column>

          <el-table-column width="60">
            <template #default="scope">
              <el-button size="small" type="danger" :icon="Delete" circle @click="removeTag(scope.$index)" />
            </template>
          </el-table-column>
        </el-table>

        <el-button size="small" :icon="Plus" style="margin-top: 8px" @click="addTag">
          {{ t('config_add_tag') }}
        </el-button>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('config_cancel') }}</el-button>
      <el-button type="primary" @click="handleSave">{{ t('config_save_btn') }}</el-button>
    </template>
  </el-dialog>
</template>
