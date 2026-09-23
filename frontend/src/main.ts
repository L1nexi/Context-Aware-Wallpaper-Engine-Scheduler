import { createApp } from "vue"

import App from "./App.vue"
import "./style.css"

const colorScheme = window.matchMedia("(prefers-color-scheme: dark)")

function applyColorScheme(): void {
  document.documentElement.classList.toggle("dark", colorScheme.matches)
}

applyColorScheme()
colorScheme.addEventListener("change", applyColorScheme)

createApp(App).mount("#app")
