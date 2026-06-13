import { computed, ref } from 'vue'

import { messages, type AppLocale, type MessageKey } from '@/i18n/messages'

const DEFAULT_LOCALE: AppLocale = 'zh-CN'
const locale = ref<AppLocale>(resolveInitialLocale())

function resolveInitialLocale(): AppLocale {
  if (typeof window === 'undefined') {
    return DEFAULT_LOCALE
  }

  const params = new URLSearchParams(window.location.search)
  const requestedLocale = params.get('locale')
  if (requestedLocale === 'zh-CN' || requestedLocale === 'en-US') {
    return requestedLocale
  }

  return DEFAULT_LOCALE
}

export function setLocale(nextLocale: AppLocale): void {
  locale.value = nextLocale
}

export function useI18n() {
  function t(key: MessageKey, params?: Record<string, string | number>): string {
    let text = messages[locale.value][key] ?? messages[DEFAULT_LOCALE][key] ?? key

    if (params) {
      for (const [name, value] of Object.entries(params)) {
        text = text.replace(`{${name}}`, String(value))
      }
    }

    return text
  }

  return {
    locale: computed(() => locale.value),
    t,
  }
}
