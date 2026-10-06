# Implementation and acceptance report

Completed implementation through Phase 11 on 2026-09-25, without intermediate review stops, as Kevin requested. The maintained Cantoo PDF fork is used. ERPNext defaults to temporary demo records; no live endpoint or credentials were configured.

Drawing revision 1.1 replaces the initial glyph-based presentation and ELK arrangement with plain equipment blocks, fixed functional columns, dedicated attachment points, shared cable-lane routing, crossing bridges and clear callouts. See [drawing revision details](drawing-revision-1.1.md). Version 1.2.0 adds restrained brand colors to the workspace and the supplied vector logo to title blocks; see [branding and artwork provenance](branding.md). Software checks and CAD imports below were rerun against version 1.2.0.

## Validation results

| Check                                                   | Result                                                                                                              |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Unit/integration suite                                  | **97 tests passed**, 16 test files                                                                                  |
| Production browser suite                                | **11 tests passed** in Microsoft Edge                                                                               |
| Formatting, ESLint, strict TypeScript, production build | Passed                                                                                                              |
| Prior 1.1 measured unit line coverage                   | 96.22%                                                                                                              |
| Prior 1.1 engine measured unit coverage                 | 96.73% lines, 94.96% statements, 87.00% branches, 98.70% functions                                                  |
| Prior 1.1 PDF / DXF unit line coverage                  | 100% / 100%                                                                                                         |
| 200-load layout                                         | Under the **2,000 ms** test limit on this machine, with all 208 nodes retained and polylines inside paper bounds    |
| 40-load pagination                                      | Passed; paired continuations and persistent pins tested                                                             |
| AutoCAD 2026 native DXF                                 | Imports successfully; **AUDIT 0 errors, 0 fixed**                                                                   |
| AutoCAD native DXF extraction                           | 22 INSERTs, 176 ATTRIBs, 365 TEXT, 98 MTEXT, 52 HATCH; two exact 1-inch squares                                     |
| PDF structure and rendering                             | Whole-string operations, full fonts, true OCG layers, no raster/clipping; both example pages rendered and inspected |
| AutoCAD PDFIMPORT                                       | Correct physical scale and geometry layers/weights; text-import deviations described below                          |

Coverage percentages above are the recorded 1.1 baseline, not a new coverage run for 1.2.0; the engine does **not** claim 100% branch coverage. Browser tests cover worker startup, first-download behavior, drag/pin persistence, CSV import, ERP demo, history, storage reload, themes and responsive layouts. No real ERP server or ODA Viewer was available for a live/manual integration test.

## Phase delivery

| Phase | Implemented result                                                                                                                                                       |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0     | Vite/React/strict TS, Radix components, theme/routes, Zustand/Immer/Zundo, Dexie, CI                                                                                     |
| 1     | Zod schemas, 24 example products, 61 wire templates, cited editable reference tables, 16 layers, four title blocks, draft notes                                          |
| 2     | Product/wire CRUD, category templates, mapped CSV preview/errors/upsert, JSON library backup, library undo                                                               |
| 3     | Four AG Grid Community tables, searchable compatible pickers, atomic TSV paste, explicit fill-down/bulk operations, row QA, complete example                             |
| 4     | Pure graph/calculation engine, required numeric test cases, CV/CC/3PH checks, operating/channel loads, cable selection and overrides, DMX, device limits, BOM and Review |
| 5     | Shared inch-based geometry, all 23 base symbols, tape channel/length labels, gallery, layered SVG                                                                        |
| 6     | Worker column layout, explicit terminals, shared wire-lane routing, crossing bridges, enclosure outlines, pagination and collision-aware callouts                        |
| 7     | Title blocks, schedules, notes, revisions, legends, true-size text, drag/pin and persisted overrides                                                                     |
| 8     | Layered vector PDF with embedded fonts, deterministic bytes and actual CAD import validation; literal TEXT/layer acceptance is limited by observed PDFIMPORT behavior    |
| 9     | Native R2007 DXF, per-sheet ZIP and tiled mode, required tables, blocks/attributes, text and geometry; AutoCAD audit passes                                              |
| 10    | Keyboard controls, error recovery, print/responsive styles, lazy loading, 200-load benchmark, user/CAD guides and reproducible tests                                     |
| 11    | Demo and optional local ERPNext pull proxy, pagination/filtering, temporary mapping, preview/conflicts, protected overrides, atomic commit and undo                      |

## Explicit boundaries

- **PDFIMPORT:** AutoCAD 2026 imports whole strings as MTEXT on `PDF_Text`, prefixes geometry layers with `PDF_`, and remaps nominal text height through font metrics. That does not satisfy the original literal “TEXT on identical layers/heights” condition. Native DXF preserves the exact CAD structure. See [CAD evidence and instructions](cad-import-test.md).
- **Product/brand inputs:** electrical datasheets and actual ERP custom-field names were not supplied. ilLumenate Lighting artwork now comes directly from the supplied guidelines PDF; the referenced shared-drive SVG was not accessible. The price workbook was left unchanged; ratings remain visibly synthetic examples. No numerical data was invented for missing Table 9 or other NEC editions.
- **ERPNext:** demo and mocked transport checks pass. Live configuration/validation is deferred at Kevin's request. The proxy is pull-only and no secrets are embedded in the package.
- **ODA:** not installed; its separate viewing check is unperformed.
- **Grouping:** fixture quantity is shown as one `xN` symbol. Distinct load rows retain their identities/runs. Extremely dense callouts may shorten to W-tags with full details in the wire schedule and a layout note.
- **Fonts:** PDF/SVG embed OFL fonts. Default DXF uses Arial references; condensed DXF requires the bundled fonts to be installed. Workspace Manrope/Poppins use installed faces when available, with a self-hosted Arimo fallback until full brand font files are available.

## Delivered files

`examples/` contains the editable example project/library, engineering results, two-sheet PDF, per-sheet DXF ZIP and tiled DXF. `docs/evidence/` contains measured CAD results and final page/browser images. The source package also includes a production build, pinned dependency lockfile, local launcher and test suites. It excludes dependencies, credentials, browser profiles and temporary test output.

Run `npm run ci` after installing dependencies to reproduce software checks. Browser tests run against `dist/`, so use `npm run build` before `npm run test:e2e` when invoking it alone. CAD verification was performed against the actual installed AutoCAD reader, separately from unit-parser tests.
