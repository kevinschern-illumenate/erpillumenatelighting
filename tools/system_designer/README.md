# ilLumenate System Designer (frontend workspace)

The dealer-facing system design tool opened with **Design system** from a fixture schedule. Plan:
[`docs/SYSTEM_DESIGNER_PRODUCT_PLAN.md`](../../docs/SYSTEM_DESIGNER_PRODUCT_PLAN.md); progress:
[`docs/SYSTEM_DESIGNER_IMPLEMENTATION_STATUS.md`](../../docs/SYSTEM_DESIGNER_IMPLEMENTATION_STATUS.md).

## Layout

| Path | What |
|---|---|
| `app/` | The React app. `app/src/main.tsx` sets `window.IllSystemDesigner.mount(el, {schedule, csrfToken, apiBase})`. |
| `packages/*` | npm workspaces: pure engine, schemas, drawing and serializer packages (no DOM in the pure ones). |
| `vendor/riser/` | Reference copy of the riser-diagram-generator repository, history kept. Do not edit. |
| `reference/` | The LED Tape System Visualizer, unchanged. Reference only, EXAMPLE data, not served. |
| `fixtures/` | Golden parity fixtures (H10) and sample `open_design` payloads (TEST data). |
| `tests/e2e/` | Playwright smoke tests against the committed bundle. |

## Commands

Node 22.13+.

```sh
npm ci
npm test            # Vitest
npm run typecheck
npm run lint
npm run build       # writes ../../illumenate_lighting/public/system_designer (commit it)
npm run test:e2e    # Playwright; in cloud sessions set SYSTEM_DESIGNER_CHROMIUM to the pre-installed Chromium
```

Frappe Cloud runs `bench build`, not Vite, so the build output is committed. CI rebuilds it and fails if
`illumenate_lighting/public/system_designer` differs from what is committed.
