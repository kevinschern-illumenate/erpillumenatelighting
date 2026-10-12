# Phase 0 review checkpoint

## Demo

Open **http://127.0.0.1:5173/#/project** while the local Vite server is running. Restart with `Start Riser.cmd` or `npm run dev` from the project folder.

The visible project form is the undo/redo acceptance demo. It also preserves real metadata and the provided sheet and PSU defaults. Future-phase screens clearly state when their features become available.

## Delivered

- React + Vite, strict TypeScript, Tailwind and configured local shadcn/Radix components.
- Project, Tables, Review, Drawing, Export and Libraries routes; ERPNext Sync placeholder.
- Editable metadata, drawing defaults and internal scratchpad.
- Cross-field undo/redo, keyboard shortcuts, no-op filtering and bounded history.
- Dexie autosave after a 400 ms debounce; recent-project switching; explicit Save now.
- Serialized writes, invalid-record handling, save failures/retry, and a versioned migration boundary.
- Light/dark modes, responsive navigation, keyboard focus, accessible form labels.
- Vitest, Playwright, lint/format commands, production build, lockfile and GitHub Actions CI script.
- Dependency review and read-only workbook intake notes.

## Verification

17 unit tests and four Playwright browser tests pass. Unit coverage for the draft schemas, store, and storage modules is 100% of lines and 95.45% of branches; this is scaffold coverage, not engine coverage. Lint, formatting, strict TypeScript and the production build pass. Tests cover history transitions, storage reopen, per-project isolation, unsupported versions, failed writes/retry, and browser reload recovery. Browser checks include both themes, all navigation routes, ERPNext placeholder, and 1440/900/390-pixel widths.

Vite reports a non-blocking bundle-size advisory (approximately 600 kB JavaScript before gzip). Splitting and performance work remain in the planned polish phase. The Windows sandbox interfered with Playwright's test-server shutdown; final CI validation was rerun outside it. This does not affect the standalone local app.

The first browser run found recent-project buttons covered by the sidebar footer at shorter heights. The sidebar now scrolls without shrinking content to zero; the project-switch test was rerun successfully.

## Explicitly pending

Full engineering schemas, product/wire/NEC seed libraries, notes, grids, calculation engine, drawing geometry/layout, schedules, PDF/DXF/CSV exports, project-file save/open, and ERPNext sync remain their scheduled later phases. No electrical results or CAD files are being presented as validated in this scaffold.

SVG brand logos were not present in the supplied files. Dependency caveats and input ambiguities for future phases are documented separately. The workbook has not been altered or uploaded.

The requested stop after each phase is honored here. Next checkpoint is Phase 1: schemas and seed data.
