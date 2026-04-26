<script setup lang="ts">
import StatusBar from '@/components/StatusBar.vue'
import CurrentPlaylist from '@/components/CurrentPlaylist.vue'
import ConfidencePanel from '@/components/ConfidencePanel.vue'
import TagChart from '@/components/TagChart.vue'
import ContextPanel from '@/components/ContextPanel.vue'
</script>

<template>
  <div class="dashboard-container">
    <StatusBar />
    <div class="dashboard-grid">
      <CurrentPlaylist />
      <ConfidencePanel />
      <TagChart />
      <ContextPanel />
    </div>
  </div>
</template>
