<script setup lang="ts">
import { provide } from 'vue'
import { RouterView } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { useHistory } from '@/composables/useHistory'
import { useI18n } from '@/composables/useI18n'
import TopBar from '@/components/TopBar.vue'

const { state, ticks, error, zombie, loading, countdown } = useApi()
const { t, lang } = useI18n()
const { segments, events, fetchHistory, loading: historyLoading } = useHistory(state)

provide('state', state)
provide('ticks', ticks)
provide('error', error)
provide('zombie', zombie)
provide('loading', loading)
provide('t', t)
provide('lang', lang)
provide('segments', segments)
provide('events', events)
provide('fetchHistory', fetchHistory)
provide('historyLoading', historyLoading)
</script>

<template>
  <TopBar />
  <RouterView />
  <div v-if="zombie" class="zombie-overlay">
    <div class="zombie-content">
      <h2>{{ t('connectionLost') }}</h2>
      <p v-if="countdown > 0">{{ t('closeCountdown', { n: countdown }) }}</p>
      <p v-else>{{ t('closing') }}</p>
    </div>
  </div>
</template>
