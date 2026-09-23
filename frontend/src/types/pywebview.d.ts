export {}

declare global {
  interface Window {
    pywebview?: {
      api: {
        choose_wallpaper_engine(): Promise<string | null>
        close(): Promise<void>
        open_external(url: string): Promise<void>
      }
    }
  }
}
