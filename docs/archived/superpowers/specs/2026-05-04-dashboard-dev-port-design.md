# Dashboard Dev Port Design

## Context

The tray host currently starts the local Bottle dashboard server on `127.0.0.1:0`, allowing the OS to pick a free port. That works for the embedded pywebview dashboard because the host passes the selected port to the dashboard subprocess, but it breaks stable frontend development against `dashboard-v2`:

- `npm run dev` cannot assume a stable backend origin
- browser-based testing and Playwright automation cannot reliably bind to a moving API port
- developers must restart or reconfigure the frontend whenever the host restarts

The goal is to make development-time frontend testing stable without weakening the current production behavior.

## Goals

- Keep production and packaged runtime behavior unchanged by default
- Allow the tray host to expose the dashboard HTTP server on a fixed port during development
- Let `dashboard-v2` use `npm run dev` and still call `/api/*` without CORS handling in application code
- Preserve the embedded dashboard flow that opens the local page in pywebview

## Non-Goals

- No redesign of dashboard API shapes
- No removal of the existing internal `--port` argument used by the dashboard subprocess
- No CORS support in the Bottle app for this workflow
- No automatic environment detection based on source mode vs packaged mode

## Chosen Approach

Use an explicit host-side CLI argument for the dashboard HTTP server port, and keep the existing subprocess argument separate.

### Decision Summary

| Concern | Choice |
| --- | --- |
| Host-visible CLI | Add `--dashboard-api-port` |
| Default value | `0` |
| Production behavior | Still dynamic by default |
| Development behavior | Developer starts host with a fixed port, for example `38417` |
| Frontend dev transport | Vite dev server proxies `/api/*` to the fixed host port |
| Frontend API calls | Keep relative `/api/...` requests |
| CORS | Not needed for the supported dev flow |
| Port conflict behavior | Fail startup clearly when an explicit fixed port cannot be bound |

## CLI and Runtime Design

### `main.py`

Add a new public host argument:

```text
--dashboard-api-port <int>
```

Rules:

- Default is `0`
- `0` means keep current dynamic-port behavior
- Any positive integer means bind the Bottle dashboard server to that exact port
- This argument applies to the host process only

The existing hidden `--port` flag remains internal and continues to mean:

- "the already-selected dashboard server port to be passed into the dashboard subprocess"

These two arguments must not be merged because they belong to different phases of the startup flow.

### `ui/dashboard.py`

Update `DashboardHTTPServer` so the caller can provide a requested port.

Design:

- Constructor accepts `requested_port: int = 0`
- `start()` binds `make_server("127.0.0.1", requested_port, ...)`
- `self.port` continues to store the actual bound port

Expected outcomes:

- With `requested_port == 0`, behavior stays exactly as today
- With `requested_port > 0`, the server binds to that exact port or raises a bind error

### Error handling

If an explicit `--dashboard-api-port` cannot be bound:

- startup must fail fast
- the log message must include the requested port
- the user-facing error should make it clear that this is a dashboard API port conflict, not a scheduler failure

Do not silently fall back to a random port in this case, because that would defeat the purpose of stable frontend tooling.

## Frontend Development Design

### `dashboard-v2`

Keep application fetch logic on relative paths such as `/api/analysis/window`.

Do not require frontend code to know a dev-only base URL for the standard workflow.

### `vite.config.ts`

Add a dev-server proxy for `/api`:

- proxy target: `http://127.0.0.1:<fixed-host-port>`
- recommended default development port: `38417`

This keeps browser requests same-origin from the page's perspective:

- page origin: `http://127.0.0.1:5173`
- browser requests: `/api/...` on `5173`
- Vite forwards those requests to `38417`

Result:

- no browser CORS preflight issues
- Playwright can interact with the `npm run dev` page directly
- backend restarts do not require rebuilding or rewriting frontend API addresses as long as the host uses the same fixed port

## Supported Workflows

### Embedded dashboard

Command:

```bash
python main.py
```

Behavior:

- host uses dynamic port by default
- pywebview still opens the correct URL because it receives the chosen runtime port from the host

### Stable frontend development

Host:

```bash
python main.py --dashboard-api-port 38417
```

Frontend:

```bash
cd dashboard-v2
npm run dev
```

Behavior:

- host listens on `127.0.0.1:38417`
- Vite proxies `/api/*` to `38417`
- browser and Playwright only need to target the Vite page origin

## File Changes

| File | Change |
| --- | --- |
| `main.py` | Add `--dashboard-api-port`, pass it into `DashboardHTTPServer` |
| `ui/dashboard.py` | Accept requested bind port and use it in `make_server` |
| `dashboard-v2/vite.config.ts` | Add `/api` dev proxy to the fixed local dashboard API port |
| `tests/test_dashboard_api.py` | Add coverage for explicit port binding behavior if practical without flaky socket assumptions |
| `dashboard-v2` docs or README-adjacent notes | Add a short dev workflow note if a suitable location exists |

## Testing and Verification

### Backend

At minimum:

```bash
pytest -q tests/test_dashboard_api.py
```

### Frontend

At minimum:

```bash
cd dashboard-v2
npm run type-check
```

If `vite.config.ts` changes are made, also run:

```bash
cd dashboard-v2
npm run build-only
```

### Manual verification

1. Start the host with `python main.py --dashboard-api-port 38417`
2. Confirm the log reports `http://127.0.0.1:38417`
3. Start `dashboard-v2` with `npm run dev`
4. Open the Vite page and confirm dashboard data loads through `/api/*`
5. Restart only the host with the same fixed port and confirm the Vite page can recover without code changes
6. Try launching a second host on the same fixed port and confirm startup fails with a clear port-conflict message

## Self-Review

- No placeholders remain
- Production default behavior stays unchanged
- Development workflow is explicit rather than inferred
- CORS is intentionally avoided by using the Vite proxy path
