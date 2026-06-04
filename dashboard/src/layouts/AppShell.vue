<script setup lang="ts">
import { RouterView } from 'vue-router'

import { WorkbenchShell, WorkbenchWorkspace } from '@/components/ui/workbench'
</script>

<template>
  <WorkbenchShell class="!grid-cols-[minmax(0,1fr)]">
    <WorkbenchWorkspace>
      <RouterView />
    </WorkbenchWorkspace>
  </WorkbenchShell>
</template>
