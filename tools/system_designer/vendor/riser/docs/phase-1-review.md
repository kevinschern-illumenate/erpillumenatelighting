# Phase 1 review checkpoint

## Demo

Open **http://127.0.0.1:5173/#/libraries** while the local Vite server is running. Restart with `Start Riser.cmd` or `npm run dev` from the project folder.

Search Products for **tunable** and inspect the explicit maximum-operating watts/ft basis with separate channel limits. Search wire templates by listing or application. In Code tables, edit a value, validate and save, reload, and reopen the tab; Restore seed removes the override. Drawing standards shows all four formats and the preview-only QA layer. General notes contains 12 draft notes for project review.

The Project page retains autosave, recent projects and undo/redo. Existing Phase 0 records migrate automatically with their original metadata, defaults and scratchpad preserved. Original records and migration archives remain in IndexedDB.

## Delivered

- Full strict Zod schemas and inferred TypeScript types for project settings, sources, equipment, loads, control links, overrides, catalog specs, wires and reference data.
- 24 clearly labelled synthetic example products, covering the requested categories and tape types.
- 61 wire templates covering all requested run types, including explicit fine-gauge resistance and mixed-gauge conductor groups. Every template requires verification before use.
- Three populated 2023 NEC reference tables with source and unit metadata. Ampacity and small-conductor OCPD limits are separate. Table 9 has an explicit unavailable record instead of fabricated values.
- Browser-persisted code-table overrides with schema validation and seed restoration.
- 16 drawing layers, seven line types and four title-block templates in paper inches. Minimum text size and the reference square are validated. QA cannot be exported.
- 12 authored draft general notes, copied into new and migrated projects.
- Safe version-0 to version-1 project migration, original archives, negative validation tests and updated source/decision documentation.

Kevin's TW decision is recorded as **maximum operating watts/ft with channel limits stored separately**. The example uses 4.4 W/ft total permitted operating power, with each channel limited to 4.4 W/ft and shared operation capped at 100%. These are synthetic example ratings.

## Validation

`npm run ci` passed on September 24, 2026: formatting, lint, **37 unit tests**, strict TypeScript, production build and **8 Playwright browser tests**. Unit coverage for included schema/state/storage modules is 93.19% of lines and 91.59% of branches. No engine exists yet, so this is not engine coverage.

Tests load every seed file; reject malformed and inconsistent inputs; verify migration of an actual version-1 IndexedDB database; preserve original records; prevent repeat migration from overwriting later edits; roll back invalid migrations; and reject corrupt code-table records. Browser checks cover product/wire searches, TW metadata, invalid JSON/units/edition changes, valid override persistence after reload, seed restoration, drawing standards, project history, route/theme behavior and responsive layouts. Screenshots were visually reviewed in light and dark themes, including a 390-pixel viewport. Wide reference tables scroll within their panel on narrow screens.

The production bundle has a non-blocking Vite size advisory (737.41 kB before gzip, 213.95 kB gzip). Bundle splitting remains in the planned performance phase. Windows browser-test validation ran outside the sandbox because its local test-server shutdown was previously blocked there.

## Limits and next checkpoint

Schema-valid data is not a certification of manufacturer ratings or installation compliance. Examples and generic wire suitability flags remain explicitly unverified. Only the 2023 code-table seed edition is included; effective-Z data is pending. The 9729 reference in the plan conflicts with the current manufacturer's nominal 100 Ω specification, so it is not mapped to the generic 120 Ω two-pair template. See [schema and source decisions](schema-and-seed-decisions.md) for source links and details.

The workbook remains unchanged; its prices and identities were not converted into guessed electrical specifications. SVG logos were not available and remain placeholders. Full library CRUD/import, engineering grids, calculations, drawing generation, file exports and ERPNext sync remain future phases. The JSON code-table buffer uses native text undo; project toolbar history still applies to project fields. Full library edit history belongs to Phase 2.

**Stopped after Phase 1 as requested.** The next checkpoint is Phase 2: library managers and CSV import/export, including mapping, per-row errors and preview before commit.
