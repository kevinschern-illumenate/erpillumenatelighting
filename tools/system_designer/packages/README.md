# Workspace packages

Moved from `vendor/riser/src` (riser-diagram-generator v1.2.0) in WP-0.3. Imports between packages use the
package name (`@ill/engine/calculate`); each package exports its `src/` files by path.

| Package | From | Notes |
|---|---|---|
| `@ill/core-schemas` | `src/schemas` | Also holds `general-notes.seed.json`, which `workspace.ts` needs (breaks the schemas ↔ data cycle). |
| `@ill/data` | `src/data` | NEC tables, title blocks, brand data, EXAMPLE seeds. `library.ts` holds `seedLibrary()` (was in `src/state/library-store.ts`). |
| `@ill/engine` | `src/engine` | Pure electrical engine. |
| `@ill/drawing` | `src/drawing` | Paper-inch drawing model, layout and router. |
| `@ill/serializers` | `src/serializers` | SVG, PDF, DXF. Fonts in `fonts/` (OFL). The browser font fetch moved to `app/src/lib/fonts.ts`. |

The pure packages may not import React, storage or network code, or touch DOM globals; ESLint enforces it.
Products in `@ill/data` seeds are **EXAMPLE** data for tests only and must never reach a dealer design.

Not moved yet: the riser's screens, stores and storage (`src/app`, `src/features`, `src/state`, `src/storage`)
come into `app/src/engineering` with WP-3.8. `src/features/erp` and `server/proxy.mjs` are not carried
into the designer (D1). The library import/editor model is in `app/src/engineering/legacy/library` because
three engine/schema integration tests exercise it.
