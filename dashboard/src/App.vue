<script setup lang="ts">
import { provide } from 'vue'
import { RouterView } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { useI18n } from '@/composables/useI18n'
import TopBar from '@/components/TopBar.vue'

const { state, error, zombie, loading } = useApi()
const { t, lang } = useI18n()

provide('state', state)
provide('error', error)
provide('zombie', zombie)
provide('loading', loading)
provide('t', t)
provide('lang', lang)
</script>

<template>
  <TopBar />
  <RouterView />
  <div v-if="zombie" class="zombie-overlay">
    <div class="zombie-content">
      <h2>{{ t('connectionLost') }}</h2>
      <p>{{ t('closeCountdown', { n: 5 }) }}</p>
    </div>
  </div>
</template>
