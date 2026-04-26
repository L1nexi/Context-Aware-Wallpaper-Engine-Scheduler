R1 Dashboard — Implementation Plan

Context

The scheduler is a black box — users have zero visibility into what it's "thinking." Every tick computes aggregated_tags, similarity, MatchResult, and Context data, all
thrown away except one console print line. The Dashboard gives users a real-time window into the scheduler's internal state.

v0.5.0 already added similarity_gap and max_policy_magnitude to MatchResult specifically to feed this dashboard. The data plumbing is done; only the presentation layer is
missing.

Architecture: Two-Process Model

The architecture is naturally split (HTTP server ↔ SPA frontend), so we go directly to two processes:

Process 1: Tray Host (existing, now + HTTP server)
MAIN THREAD — pystray event loop (unchanged)
Daemon [1] — WEScheduler 1s tick loop
Daemon [2] — DashboardHTTPServer (serves static + /api/\*)

Process 2: Dashboard Window (spawned on demand)
MAIN THREAD — pywebview, loads http://127.0.0.1:{port}?locale={zh|en}
Single window, normal close = destroy process, no hide/show tricks

Lifecycle: Tray "Status..." → subprocess.Popen spawns dashboard process. User closes window → process exits. No persistent window, no hide-on-close hacks, no WM_CLOSE
interception.

Zombie prevention: If the tray process dies while the dashboard is open, the frontend's 1s polling loop will fail. After 3 consecutive failures → show "Connection lost"
overlay → 5s countdown → window.close() (or pywebview API) → process exits cleanly.

Spawn overhead: Cold start ~1.5s (WebView2 init), warm start ~0.8s. Acceptable for an occasionally-opened dashboard.

Tech Stack

┌──────────────┬──────────────────────────────────┬────────────────────────────────────────────────────────────┐
│ Layer │ Choice │ Notes │
├──────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────────┤
│ Window shell │ pywebview (Edge Chromium) │ Win10+ built-in WebView2, no extra runtime │
├──────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────────┤
│ Frontend │ Vue 3 + Element Plus + Vite │ SPA, polished components │
├──────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────────┤
│ Python↔JS │ stdlib HTTP server │ Serves static files AND /api/\* from same origin, zero CORS │
├──────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────────┤
│ Build │ Pre-built dashboard/dist/ in git │ No Node.js at packaging time │
└──────────────┴──────────────────────────────────┴────────────────────────────────────────────────────────────┘

Data Flow

Scheduler tick
→ build_tick_state(context, result)
→ StateStore.update(tick_state) [lock-protected]

HTTP handler GET /api/state
→ StateStore.read()
→ JSON response

HTTP handler GET /\*
→ static file from {app_root}/dashboard/dist/

Vue SPA (http://127.0.0.1:{port}/)
→ fetch('/api/state') every 1s
→ 3 consecutive failures → "Connection lost" → 5s → close window

Same origin for static + API = no CORS, no cross-origin headaches.

Files to Create

core/dashboard.py — Data + HTTP server

- TickState dataclass:
  ts, current_playlist, similarity, similarity_gap, max_policy_magnitude,
  top_tags (top 8), paused, pause_until,
  active_window, idle_time, cpu, fullscreen, locale
- StateStore: update() / read() with threading.Lock
- DashboardHTTPServer: http.server.ThreadingHTTPServer, binds 127.0.0.1:0, exposes .port. Single request handler dispatches:
- GET /api/state → json.dumps(dataclasses.asdict(state))
- GET /api/health → {"ok": true} (heartbeat target)
- GET /\* → static file from {app_root}/dashboard/dist/, proper MIME types
- build_tick_state(scheduler, context, result): constructs TickState from current tick

Static root resolves via app_context.get_app_root():

- Source: {repo_root}/dashboard/dist/
- Frozen (PyInstaller): {sys.\_MEIPASS}/dashboard/dist/

core/webview.py — Dashboard process entry point

- DashboardWindow: thin wrapper — create_and_block(), no show/hide
  class DashboardWindow:
  def **init**(self, api_port: int, locale: str):
  self.\_url = f'http://127.0.0.1:{api_port}?locale={locale}'

      def create_and_block(self):
          webview.create_window(
              title=t('dashboard_title'),
              url=self._url,
              width=900, height=650,
              resizable=True,
              text_select=True,
          )
          webview.start(gui='edgechromium')
          # Returns when window is closed — process exits

- No show() / hide() / destroy() — window close = process exit, tray just spawns a new one
- Simple module, basically a config wrapper around pywebview

dashboard/ — Vue 3 SPA

dashboard/
index.html
package.json # vue 3, element-plus, @element-plus/icons-vue, vite
vite.config.js # base: './'
src/
main.js
App.vue # Root: title bar + 2-col grid + heartbeat error overlay
style.css
i18n/
index.js # useI18n composable, reads ?locale= from URL
en.json / zh.json
composables/
useApi.js # fetch /api/state 1s, tracks consecutive failures
components/
TopBar.vue # Title + window control buttons
StatusBar.vue # Running/Paused/Fullscreen badges
CurrentPlaylist.vue # Large playlist name or "Waiting..."
ConfidencePanel.vue # Similarity gauge + gap + magnitude
TagChart.vue # Top-8 tag horizontal bars (pure CSS)
ContextPanel.vue # Window, idle, CPU mini stats

Every component handles: loading (el-skeleton), empty (el-empty + description), error (warning), populated.

Heartbeat / zombie detection in useApi.js:
let failures = 0
const MAX_FAILURES = 3

async function fetchState() {
try {
const res = await fetch(`${baseUrl}/api/state`)
if (!res.ok) throw new Error(`HTTP ${res.status}`)
state.value = await res.json()
failures = 0
error.value = null
} catch (e) {
failures++
if (failures >= MAX_FAILURES) {
zombie.value = true // triggers overlay
setTimeout(() => window.close(), 5000) // or pywebview API
}
error.value = e.message
}
}

When zombie === true, App.vue shows a full-screen overlay: "Scheduler connection lost. This window will close in 5 seconds."

Files to Modify

core/scheduler.py

- self.state_store: StateStore | None = None (set externally by main.py)
- In \_run_loop, after \_update_status():
  if self.state_store:
  self.state_store.update(build_tick_state(self, context, result))

core/tray.py

- **init** accepts api_port: int | None = None
- Add t("dashboard_show") menu item → \_on_show_dashboard():
  def \_on_show_dashboard(self, icon, item):
  if self.\_api_port is None:
  return
  locale = i18n.\_current_lang
  exe = sys.executable
  script = os.path.join(get_app_root(), 'main.py')
  subprocess.Popen(
  [exe, script, '--dashboard', f'--port={self._api_port}', f'--locale={locale}'],
  creationflags=subprocess.CREATE_NO_WINDOW if getattr(sys, 'frozen', False) else 0,
  )
- When frozen (PyInstaller), use sys.executable directly (it IS the exe). When running from source, use sys.executable + main.py.

utils/i18n.py

- Add ~15 dashboard translation keys

main.py

- Add --dashboard and --port and --locale CLI flags (used only by the dashboard subprocess)
- When --dashboard is set: skip scheduler/tray init, create DashboardWindow(port, locale), call create_and_block(), exit
- When --no-tray: unchanged (console mode)
- Default (tray mode):
  a. Create scheduler, initialize, start
  b. Create StateStore, set scheduler.state_store
  c. Create DashboardHTTPServer, start → get api_port
  d. Create TrayIcon(scheduler, api_port=api_port)
  e. Call tray.run() (blocks main thread, as today)

The tray process never touches pywebview. Only the dashboard subprocess imports webview.

requirements.txt

- Add pywebview>=4.4,<5.0

scripts/build.bat

- Add --add-data "dashboard\dist;dashboard\dist" to PyInstaller
- npm build is a developer step; dist/ is committed; build.bat needs no Node.js

PyInstaller Path Handling

- app_context.get_app_root() → sys.\_MEIPASS when frozen, repo root when source
- HTTP server static root: os.path.join(get_app_root(), 'dashboard', 'dist')
- --add-data "dashboard\dist;dashboard\dist" in PyInstaller command ensures dist/ lands in \_MEIPASS
- pywebview loads http://127.0.0.1:{port} — no file path in URL

When frozen, spawning the dashboard subprocess: sys.executable is the exe itself. The --dashboard flag triggers the dashboard code path without re-creating scheduler/tray.

Implementation Order

┌─────┬────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────┐
│ # │ What │ Verification │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 1 │ pip install pywebview │ import works │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 2 │ utils/i18n.py — dashboard keys │ t('dashboard_title') prints │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 3 │ core/dashboard.py — TickState, StateStore, HTTP server │ StateStore().read(), start server, curl /api/state │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 4 │ core/scheduler.py — state_store + tick hook │ --no-tray runs, no regressions │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 5 │ Scaffold dashboard/ Vue project │ npm run build, verify via HTTP server │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 6 │ Implement Vue components + heartbeat │ browser test all states │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 7 │ core/webview.py — DashboardWindow │ import works │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 8 │ main.py — add --dashboard mode + wire tray mode │ python main.py --dashboard --port=N --locale=en opens window │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 9 │ core/tray.py — spawn subprocess on "Status..." │ click tray → window opens, close → exits │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 10 │ End-to-end: python main.py │ full flow, live data, pause/resume reflected │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 11 │ build.bat — add --add-data │ dist/WEScheduler.exe runs, dashboard opens │
├─────┼────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 12 │ Edge cases │ zombie detection, no match, hot reload, rapid open/close, exit while dashboard open │
└─────┴────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────┘

Verification

1. Source run: python main.py → tray icon → "Status..." → dashboard window with live data → close window → "Status..." again → new window → Exit tray
2. No-tray unchanged: python main.py --no-tray → identical console output
3. Empty state: No Wallpaper Engine → dashboard shows "Waiting..."
4. Pause state: Pause from tray → dashboard StatusBar updates within 1s
5. Zombie detection: Kill tray process while dashboard open → "Connection lost" overlay → 5s → window closes
6. Exe build: build.bat → exe runs, dashboard spawns correctly
7. Rapid open/close: 5 quick open-close cycles, no leaks, no errors
