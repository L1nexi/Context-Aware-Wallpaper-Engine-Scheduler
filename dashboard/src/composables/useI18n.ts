import { computed } from 'vue'
import en from '@/i18n/en.json'
import zh from '@/i18n/zh.json'

const messages: Record<string, Record<string, string>> = { en, zh }

function getLocale(): string {
  const params = new URLSearchParams(window.location.search)
  const lang = params.get('locale')
  if (lang && messages[lang]) return lang
  return 'en'
}

const locale = getLocale()

export function useI18n() {
  function t(key: string, params?: Record<string, string | number>): string {
    let text = messages[locale]?.[key] ?? messages.en?.[key] ?? key
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        text = text.replace(`{${k}}`, String(v))
      }
    }
    return text
  }

  const lang = computed(() => locale)

  return { t, lang }
}
