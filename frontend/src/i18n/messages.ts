export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const

const zhCN = {
  diagnosticPreview: '诊断预览',
  frontendReady: '前端可独立打开',
  staticPreviewDescription:
    '一个静态示例界面，用来确认前端初始化、主题变量、字体、图标和构建流程已经就绪。',
  activeWindow: '活动窗口',
  idleTime: '空闲时间',
  cpu: 'CPU',
  weather: '天气',
  currentMatch: '当前匹配',
  executionState: '执行状态',
} as const

export type AppLocale = (typeof SUPPORTED_LOCALES)[number]
export type MessageKey = keyof typeof zhCN

const enUS: Record<MessageKey, string> = {
  diagnosticPreview: 'Diagnostic preview',
  frontendReady: 'Frontend opens independently',
  staticPreviewDescription:
    'A static preview for checking frontend initialization, theme variables, fonts, icons, and build flow.',
  activeWindow: 'Active window',
  idleTime: 'Idle time',
  cpu: 'CPU',
  weather: 'Weather',
  currentMatch: 'Current match',
  executionState: 'Execution state',
}

export const messages: Record<AppLocale, Record<MessageKey, string>> = {
  'zh-CN': zhCN,
  'en-US': enUS,
}
