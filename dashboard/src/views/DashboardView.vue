<script setup lang="ts">
import { ref } from 'vue'
import StatusBar from '@/components/StatusBar.vue'
import CurrentPlaylist from '@/components/CurrentPlaylist.vue'
import ConfidencePanel from '@/components/ConfidencePanel.vue'
import TagChart from '@/components/TagChart.vue'
import ContextPanel from '@/components/ContextPanel.vue'
import HistoryView from '@/views/HistoryView.vue'

const activeTab = ref('live')
</script>

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
    </el-tabs>
  </div>
</template>
