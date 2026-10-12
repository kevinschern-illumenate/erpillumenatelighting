# ilLumenate Lighting Riser Generator 1.2.0

Local lighting-system workspace: enter system tables, review electrical calculations, arrange riser sheets, and export vector PDF, native DXF, SVG and schedules. React, strict TypeScript and Vite; projects and libraries stay in browser IndexedDB. The optional ERPNext proxy is pull-only.

## Start

Requires Node.js 22.13+ and npm. Dependencies are already installed in Kevin's working folder. For an extracted source package:

```sh
npm ci
npm run dev
```

Open [the local workspace](http://127.0.0.1:5173/#/project). Windows users can start it with `Start Riser.cmd` after installing dependencies. Keep its terminal open. Use the same browser and origin; `localhost` and `127.0.0.1` have separate storage.

For the demo, create a new project, then choose **Tables → Load complete example → Review → Drawing → Export**. Loading the example replaces the active design tables.

Defaults: ARCH D 36 × 24 inches, `L-#` numbering, 80% PSU target, 2023 reference tables. Seed products and wires are **EXAMPLE** data. The supplied price workbook was inspected without modification; it lacks the electrical ratings required for an engineering catalog. The supplied ilLumenate Lighting vector logo appears in monochrome on title blocks; workspace colors follow the brand palette. See `docs/branding.md` for artwork provenance and typography.

## Documentation

- [Drawing revision 1.1](docs/drawing-revision-1.1.md): clean equipment blocks, separated cable lanes and explicit crossings.
- [User guide](docs/user-guide.md): entry, imports, calculations, drawings, backups and ERP setup.
- [CAD import test](docs/cad-import-test.md): AutoCAD results and PDFIMPORT behavior.
- [Acceptance report](docs/acceptance-report.md): implementation, evidence and external inputs.
- [Schema/data provenance](docs/schema-and-seed-decisions.md) and [dependency verification](docs/dependency-verification.md).

The original plan and Phase 0/1 checkpoints remain as historical records. Kevin's later instruction superseded their phase-review stops. The maintained Cantoo PDF fork and temporary ERP demo configuration were expressly accepted.

## Validate and build

```sh
npm run ci
```

Runs formatting, lint, unit/integration coverage, TypeScript, production build and Playwright. Browser tests use installed Microsoft Edge; another machine may need `npx playwright install msedge`. Proxy tests use a local test server and mocked upstream responses.

`npm run test:e2e` tests the production preview; run `npm run build` first when invoking it separately.

```sh
npm run build
npm run preview
```

The production preview is at `http://127.0.0.1:4173`. Its storage origin differs from development; transfer a project and library backup when needed. Serve `dist/` over HTTP instead of opening its HTML as a local file.

## Architecture

- `src/schemas`: Zod source of truth and project migrations; legacy originals are preserved.
- `src/engine`: pure graph, loading, CV/CC checks, voltage drop, wire selection, DMX and BOM calculations.
- `src/drawing`: shared paper-inch primitives, 23 plain equipment symbols, aligned column layout, pin rerouting, pagination and schedules; the browser uses a worker.
- `src/serializers`: SVG, embedded TrueType PDF with optional-content layers, and native R2007 DXF blocks/attributes.
- `src/features`: project, four grids, library imports, review, drawing, exports and ERP preview.
- `server/proxy.mjs`: optional loopback-only Express transport; credentials stay in local `.env`.

Heavy grids, layout and PDF modules load on demand. Development prebundles lazy export dependencies to prevent a first-download reload. Large dependency chunks produce a non-blocking build advisory.

## ERPNext later

**Libraries → ERPNext Sync → Demo** works without credentials. To connect later, copy `.env.example` to `.env`, configure the endpoint/token locally, run `npm run proxy`, and replace the temporary field mapping with actual ERP custom fields. The integration never writes to ERPNext.

No hosted deployment, cloud storage or telemetry is included.
