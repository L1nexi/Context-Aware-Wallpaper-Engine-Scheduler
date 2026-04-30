<script setup lang="ts">
import { ref, inject } from 'vue'
import StatusBar from '@/components/StatusBar.vue'
import CurrentPlaylist from '@/components/CurrentPlaylist.vue'
import ConfidencePanel from '@/components/ConfidencePanel.vue'
import TagChart from '@/components/TagChart.vue'
import ContextPanel from '@/components/ContextPanel.vue'
import HistoryView from '@/views/HistoryView.vue'
import ConfigView from '@/views/ConfigView.vue'

const activeTab = ref('live')
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
</script>

<template>
  <div class="dashboard-container">
    <div class="status-bar-wrap">
      <StatusBar />
    </div>
    <el-tabs v-model="activeTab" class="main-tabs">
      <el-tab-pane :label="t('dashboard_live')" name="live">
        <div class="dashboard-grid">
          <CurrentPlaylist />
          <ConfidencePanel />
          <TagChart />
          <ContextPanel />
        </div>
      </el-tab-pane>
      <el-tab-pane :label="t('dashboard_history')" name="history">
        <HistoryView />
      </el-tab-pane>
      <el-tab-pane :label="t('dashboard_config')" name="config">
        <ConfigView />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.status-bar-wrap { flex-shrink: 0; }
.main-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.main-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.main-tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow: auto;
}
</style>
