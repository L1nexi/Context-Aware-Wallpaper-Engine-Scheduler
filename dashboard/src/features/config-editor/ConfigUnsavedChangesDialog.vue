<script setup lang="ts">
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useI18n } from '@/composables/useI18n'

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  (event: 'confirm'): void
  (event: 'cancel'): void
}>()

const { t } = useI18n()
</script>

<template>
  <AlertDialog v-model:open="open">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ t('config_leave_title') }}</AlertDialogTitle>
        <AlertDialogDescription>
          {{ t('config_leave_body') }}
        </AlertDialogDescription>
      </AlertDialogHeader>

      <AlertDialogFooter>
        <AlertDialogCancel @click="emit('cancel')">
          {{ t('config_stay') }}
        </AlertDialogCancel>
        <AlertDialogAction
          class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          @click="emit('confirm')"
        >
          {{ t('config_leave_discard') }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
