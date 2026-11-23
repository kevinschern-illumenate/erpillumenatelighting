# Web Drawing Editor (browser CAD, synced to the AutoCAD toolkit): PDR and Implementation Plan

2026-11-22 · branch `claude/browser-autocad-interface-plan-x3cq28` · status: **decisions accepted
2026-11-23 (§12); implementation handbook in Part II; nothing built yet**

Part I is the PDR (what and why). Part II is the implementation handbook (how, work package by work
package).

Related: `docs/CAD_TOOLKIT_IMPLEMENTATION.md` (the AutoCAD toolkit and drawing import),
`tools/cad_toolkit/README.md`, `docs/SYSTEM_DESIGNER_PRODUCT_PLAN.md` (§12.3 plan view, §15 architecture),
`docs/BLUEBEAM_SPIKE_REPORT.md`.

---

## 0. Summary

**Can it be done?** Yes. Dealers and staff can draw runs in a browser: polylines with lines and arcs, a
floor plan underlay scaled by two picked points, layers, moving, copying and scaling. The drawing goes to
the fixture schedule through the import the AutoCAD toolkit already uses. Most of the hard parts exist:

- the `ilq/2` package already lists `web` as a source tool (`ILQ_SOURCE_TOOLS` in `core-schemas/src/ilq.ts`,
  `source_tool` on `ilL-CAD-Import`);
- the server import, the checks, scale gating, receipts, re-import and the System Designer seed all work
  for any front end;
- the toolkit's rules are already written as *pure* AutoLISP (about 1,900 lines), and CI already runs them
  outside AutoCAD through a small interpreter (`tools/cad_toolkit/test/mini_lisp.py`);
- layers, linetypes, symbols and title blocks already come from one source (`packages/data/src/layers.json`
  and the riser's symbols, `npm run cad:export`);
- the System Designer workspace (React 19, TypeScript, Vite, committed bundle) already has a DXF writer
  that passes AutoCAD AUDIT, a PDF writer and the brand assets.

**How "synced to the AutoCAD code" works.** The website runs **the same AutoLISP files** as AutoCAD. A
TypeScript port of the CI interpreter runs them in a Web Worker. The run hints, ILCHECK rules, `ilq/2`
package writer and receipt handling are not re-implemented. Change `il-model.lsp` and rebuild, and the
website's checks, lengths and package change with it. CI blocks a merge when the web bundle was built from
different LISP than the repository holds. The interactive part (prompts versus mouse tools) cannot be
shared code, because AutoCAD's command line and a browser canvas work differently. For that part, a
**command manifest** is the contract: every `c:IL*` command must be listed with its web status, so a new
AutoCAD command fails CI until someone builds it for the web or marks it AutoCAD-only. Drawings also move
both ways as **DXF with the toolkit's own XData**: a web drawing opens in AutoCAD as live toolkit runs, and
an AutoCAD drawing opens on the web as live runs.

**What it is not.** It is not a rebuild of AutoCAD. It covers about 35 general drafting commands that a
lighting layout needs, plus every ilLumenate command. 3D, DWG editing, xref management, constraints,
sheet sets and user scripting are out of scope (§3.2).

**Size (revised 2026-11-23).** Added up work package by work package (Part II, W8), Release 1 (tape and
linear runs, rooms, cabinets and PSUs over a calibrated PDF, to a quote) is about **40–50 developer-weeks**,
and Release 2 (to GA) about **25–30 more**. With two developers working in parallel (one on the VM, core
and server, one on the canvas and UI), Release 1 takes about 5–6 calendar months. The first draft's phase-level
figure (20–30 weeks for everything) was too low once each package was sized. Phase 0 has four spikes that
can stop or reshape the plan before most of the money is spent.

**Decisions** are in §12: all recommendations were accepted on 2026-11-23. Release 1 is the faster cut
(§10.9); Release 2 brings controls, DXF round trip with AutoCAD, sheets and plotting, and the full drafting
set. Part II is the implementation handbook.

---

# Part I — PDR

## 1. The request, restated

> Can we do this all in the browser, with a simple interface that lets the user do the same things as
> AutoCAD (draw polylines with arcs and lines, scale drawings, layers and so on), and have it synced to the
> AutoCAD code? As that gets updated, so does our website interface.

"Synced" can mean three different things, and the plan covers all three:

| Layer | Meaning | How (section) |
| --- | --- | --- |
| **Logic** | Lengths, cut snap, max run, splits, watts, PSU load, ILCHECK codes and texts, the `ilq/2` package, receipt handling: identical results in AutoCAD and on the web. | Run the same `.lsp` files in the browser (§6.5) and gate it in CI (§7). |
| **Contracts** | Same package schema, catalog, XData keys and schema version, layers, blocks, check codes, minimum versions. | Shared schemas and fixtures that already exist, plus new CI gates (§7). |
| **Drawings** | A drawing started on the web can be finished in AutoCAD, and the other way round. | DXF export and import carrying `ILLUMENATE` XData and the drawing dictionary (§6.14). |
| *Interaction* | *The same commands are available.* | *The command manifest (§6.8, §7 G3). The UI itself is written for the browser.* |

---

## 2. What exists today

| Piece | Where | Reused how |
| --- | --- | --- |
| Pure AutoLISP: helpers, JSON, hint math, SHA-256, catalog, model, ILCHECK, `ilq/2` writer, receipt, controls | `tools/cad_toolkit/lisp/il-util, il-json, il-math, il-sha256, il-catalog, il-model, il-controls.lsp` | **Run as-is in the browser** (§6.5). |
| AutoCAD host side: commands, XData, dictionary, `entmake` blocks | `il-core.lsp`, `il-blocks.lsp`, `il-commands.lsp` (27 commands) | Reference behaviour for the web tools; the XData and dictionary formats are copied exactly (§6.4). |
| AutoLISP interpreter for CI | `tools/cad_toolkit/test/mini_lisp.py` (800 lines) | Ported to TypeScript (`packages/cad-lisp`). |
| Golden cases | `tools/system_designer/fixtures/cad/` (`lisp-subset.json`, `check-cases.json`, `packages/valid|invalid`) | Run by Python, LISP and now TypeScript. |
| `ilq/2` schema (Zod, JSON Schema, Python) | `packages/core-schemas/src/ilq.ts`, `system_design/ilq_schema.py` | Unchanged; the web writes `source.tool: "web"`. |
| CAD catalog `cad-catalog/1` (price-free) | `system_design/cad_catalog.py`, `api.get_cad_catalog` | Fetched live by session; no file download. |
| Import: preview, choices, commit, receipt, re-import, versions, scale gate, quote blockers | `portal/drawing_import.py` | Called directly with the package; the dialog is reused. |
| Server checks with the toolkit's codes | `system_design/drawing_checks.py` | Stays the authority at import. |
| DXF ingest (layer convention, bulges) | `portal/dxf_ingest.py` | Extended to read toolkit XData (§6.14). |
| Layer standard, linetypes, symbols, title blocks | `packages/data/src/layers.json` (`planLayers`), `packages/drawing/src/cadAssets.ts` | One source for AutoCAD and web. |
| DXF / PDF / SVG writers | `packages/serializers/src/{dxf,pdf,svg}` | DXF export and plotting. |
| App stack and bundle pattern | `tools/system_designer` (React 19, Zustand + immer + zundo, Zod, Dexie, Radix, Tailwind), bundle in `public/system_designer/` | Same workspace, new lazy entry. |
| System Designer plan view (planned, Phase 6, §12.3) | not built | **This editor becomes the designer's plan view.** |

---

## 3. Goals and non-goals

### 3.1 Goals

1. A dealer with no AutoCAD can draw a lighting layout over the architect's plan (PDF or DXF) and send it to
   a schedule for a quote, with the same accuracy and checks as the AutoCAD toolkit.
2. A drafter who knows AutoCAD feels at home: command line, aliases, typed coordinates, object snaps, ortho,
   polar, Enter to repeat.
3. A beginner can do it from a toolbar, without the command line.
4. Toolkit logic changes reach the website without a second implementation, and CI catches drift.
5. Drawings move between AutoCAD and the web in both directions without losing toolkit data.

### 3.2 Non-goals (v1)

3D; DWG read or write in the browser (§6.15); editing xrefs or a background's own entities beyond hiding
layers; hatches beyond solid room fills; parametric constraints, dynamic blocks or attribute editing beyond
our tags; sheet sets; user LISP or scripts; real-time multi-user editing; metric units (D11 stays Phase 8);
phone editing.

---

## 4. Users and jobs

| User | Job | Today |
| --- | --- | --- |
| Dealer sales or designer, no CAD | "Mark up this plan with tape runs and get a quote." | Bluebeam (spike pending), hand takeoff, or asks ilLumenate. |
| Dealer drafter with AutoCAD or LT | "Lay out, check and quote; send the architect a clean DWG." | AutoCAD toolkit 0.5.0. |
| Applications Engineer (staff) | "Draw or fix a dealer's job, verify scale, check controls." | AutoCAD toolkit; Desk import. |
| Estimator (staff) | "Open what was drawn, check lengths, compare imports." | `ilL-CAD-Import` record, diff. |

---

## 5. Requirements

Numbered for traceability; **v1** is in the first general release, **later** is after it.

### 5.1 General drafting (FR-D)

| # | AutoCAD | Web tool | Scope | Notes |
| --- | --- | --- | --- | --- |
| D1 | PLINE (PL) | Polyline | v1 | Line and Arc modes; arc by end point (tangent), Second point, CEnter, Radius, Angle; Close; Undo last vertex. Stored as LWPOLYLINE vertices with bulge, exactly like AutoCAD. |
| D2 | LINE (L) | Line | v1 | |
| D3 | ARC (A) | Arc | v1 | 3-point, start-center-end, start-end-radius. |
| D4 | CIRCLE (C) | Circle | v1 | |
| D5 | RECTANG (REC) | Rectangle | v1 | Also used by Room. |
| D6 | MOVE (M), COPY (CO) | Move, Copy | v1 | Base point and second point, or displacement. Copy follows the toolkit's copy rules (§5.2 ILUPDATE). |
| D7 | ROTATE (RO) | Rotate | v1 | Including Reference. |
| D8 | SCALE (SC) | Scale | v1 | Factor or **Reference** (pick two points, type the real length). This is how a whole drawing is scaled. |
| D9 | MIRROR (MI) | Mirror | v1 | |
| D10 | OFFSET (O) | Offset | v1 | Distance or Through. Important for coves and valances. |
| D11 | FILLET (F) | Fillet | v1 | Radius on polyline corners, which makes the arc in place. The bend check uses the result. |
| D12 | TRIM (TR), EXTEND (EX) | Trim, Extend | later | v1 has Break at point instead. |
| D13 | BREAK (BR), JOIN (J), EXPLODE (X) | Break, Join, Explode | v1 | JOIN also serves ILCONVERT chains. |
| D14 | STRETCH (S), grips | Grip edit | v1 | Drag vertex and midpoint grips (midpoint grip of an arc changes its bulge, like AutoCAD). |
| D15 | ERASE (E), Delete | Erase | v1 | |
| D16 | UNDO (U) / REDO, Ctrl+Z / Ctrl+Y | Undo / Redo | v1 | One step per command, like AutoCAD. |
| D17 | DIST (DI), MEASUREGEOM | Measure | v1 | Distance, polyline length, area. |
| D18 | TEXT (DT), MTEXT (T) | Text | v1 | Single-line and simple multi-line. |
| D19 | DIMLINEAR (DLI), DIMALIGNED (DAL) | Dimension | v1 | Linear and aligned, architectural units. |
| D20 | LAYER (LA) | Layers panel | v1 | §5.4. |
| D21 | PROPERTIES (Ctrl+1), MATCHPROP (MA) | Properties panel, Match | v1 | Layer, color, linetype, geometry; toolkit data for our objects. |
| D22 | ZOOM (Z) / PAN (P) | Wheel, drag, Extents, Window, Previous | v1 | |
| D23 | OSNAP (F3) | Snaps | v1 | Endpoint, Midpoint, Center, Intersection, Perpendicular, Nearest, Tangent (arc mode), Quadrant. |
| D24 | ORTHO (F8), POLAR (F10), SNAP (F9), GRID (F7) | Same toggles | v1 | Polar increments 15, 30, 45, 90. |
| D25 | Dynamic input | Typed values at the cursor | v1 | Absolute `x,y`, relative `@dx,dy`, polar `@dist<angle`, direct distance with ortho or polar; **feet-inches entry** (`10'6-1/2"`, `126.5`). |
| D26 | Selection | Click, Shift-click, window (left-to-right), crossing (right-to-left), Select All, Select Similar | v1 | |
| D27 | Command line | Same | v1 | Aliases, Enter or Space repeats the last command, Esc cancels, prompts with bracketed options. |
| D28 | UNITS | Architectural inches | v1 | Metric later (D11). |

### 5.2 ilLumenate commands (FR-IL)

Every `c:IL*` command in `il-commands.lsp`, with its web form. "Auto" means the web does it continuously,
so there is no button.

| AutoCAD | Web | Scope |
| --- | --- | --- |
| ILSETUP | Drawing settings dialog (schedule, project, sheet size, plot scale, title block); created from the schedule, so mostly pre-filled. | v1 |
| ILCATALOG | Auto: the catalog is fetched live for the signed-in user; a banner appears when the snapshot hash changes. | v1 |
| ILSTYLE | Style picker (presets with drawing codes, tape/neon templates and options). | v1 |
| ILTAPE | Draw Run: the polyline tool in the current style and Type, from the feed end; live hint at the cursor ("120.25 in · 44.1 W · 54% max"). Over-max prompt as a small choice (Split / Double-end / Center). | v1 |
| ILCONVERT | Convert to runs (selected lines, arcs and polylines; chains joined). | v1 |
| ILJUMPER | Jumper: toggle a break at a vertex, or add one at a picked point; jumper spans. | v1 |
| ILFEED | Feed: pick the feed end (reverses the run), feed method. | v1 |
| ILSCALE | Calibrate: pick two points on the underlay or drawing, type the real length; the sheet's scale becomes `verified`. | v1 |
| ILROOM | Room: pick inside a closed outline, or draw a rectangle or polygon; name, level, environment. | v1 |
| ILCAB | Cabinet: place a symbol; location rating, access note. | v1 |
| ILPSU | Power supply: place a symbol in a cabinet; model from the catalog. | v1 |
| ILCONNECT | Connect: pick a PSU, then runs (add or remove). | v1 |
| ILWIRE | Wire: a polyline from one end to another (LV, line or data); measured length. | v1 |
| ILCTRL | Control: place a controller or decoder; DMX universe and address. | v1 |
| ILZONE | Zone: group runs under a control output with a protocol. | v1 |
| ILDMX | DMX patch panel, with "place as table". | v1 |
| ILOTHER | Other-manufacturer lines (a table panel). | v1 |
| ILOVERRIDE | Override from the check panel (reason required). | v1 |
| ILUPDATE | Auto: tags, feed and jumper markers, colors and copy rules (`il-fix-copies`) run after every command. | v1 |
| ILCHECK | Auto: a live check panel; clicking an issue zooms to it. "Check with portal" runs the server preview. | v1 |
| ILQUOTE | Send to schedule (§5.6), with no file to save and upload. | v1 |
| ILRECEIPT | Auto after commit (line keys, part numbers, server lengths written to the runs). | v1 |
| ILOUT | Place run schedule and cut list tables from the receipt. | v1 |
| ILRISER | "Open in System Designer" and place the designer's riser sheet. | later |
| ILSTRIP | Export clean DXF for the architect (no ilLumenate data). | v1 |
| ILVERSION / ILHELP | About panel (web and toolkit versions), help drawer generated from the command manifest. | v1 |
| ILSPIKE | AutoCAD-only (capability probe). | n/a |

### 5.3 Underlays and scale (FR-U)

- U1 Upload a **PDF** (choose a page), **PNG/JPEG**, or **DXF** as an underlay on a sheet. v1.
- U2 Underlays are locked, dimmable (opacity) and clippable (rectangle), and you can snap to them: endpoint,
  intersection and nearest on DXF geometry; nearest on PDF vector paths when the page has them (spike 0.2).
- U3 **Calibrate** (ILSCALE): two points and a real length set the underlay's transform. The sheet's scale
  status follows the existing rules: `verified` after calibration, `declared` for a DXF with `$INSUNITS`,
  `unverified` otherwise. An unverified scale blocks quote requests until an Applications Engineer confirms
  it. That gate already exists.
- U4 A **check dimension**: after calibrating, the user measures one known length, which is stored as
  `check_dimension_in`.
- U5 A DXF underlay's layers show in the layers panel as a read-only group (`XREF|<layer>`) that can be turned
  off or frozen.

### 5.4 Layers (FR-L)

- L1 A layers panel with on/off, freeze, lock, color (ACI and true color), linetype, lineweight, plot/no-plot,
  current layer, new, rename, delete (if empty), filter and search.
- L2 New drawings start with the plan layer standard (`planLayers`: `E-LITE-TAPE`, `E-LITE-EXTR`,
  `E-LITE-FEED`, `E-LITE-DATA`, `E-POWR-CABN`, `E-POWR-WIRE-LINE`, `E-ANNO-ROOM`, `E-ANNO-ISSU`) from the
  same `layers.json` the AutoCAD DWT uses.
- L3 ilLumenate tools put entities on their standard layer (as `il-run-layer` does); users can add their own
  layers for notes and geometry.
- L4 Layer states (save and restore visibility) come later.

### 5.5 Sheets and plotting (FR-S)

- S1 Model space plus one or more **sheets** (layouts). Each sheet has a sheet size (ARCH C/D, ANSI B/D,
  Letter, Tabloid), a title block from `cadAssets`, one viewport onto model space at a plot scale
  (`1/8" = 1'-0"`, `1/4" = 1'-0"`, etc.) and its own scale status. Runs are assigned to sheets, which matches
  the toolkit's `sheets[]` and `runs[].sheet`.
- S2 Plot a sheet or all sheets to vector PDF (`@cantoo/pdf-lib` through `packages/serializers`), honouring
  plot/no-plot layers and lineweights. The PDF can go with the import as the `Plan PDF` deliverable, as it does
  for AutoCAD.
- S3 Multiple viewports per sheet come later.

### 5.6 Send to schedule (FR-Q)

- Q1 The editor is opened **from a schedule** ("Draw layout" on the schedule and project pages; "New schedule
  from drawing" for a new one). It is bound to that schedule.
- Q2 "Send to schedule" builds the `ilq/2` package through the LISP VM (`il-package`), with
  `source: {tool: "web", version, platform: "<browser>", input: "ilq"}` and `identity: "xdata"`. It then calls
  `preview_drawing_import`, shows the **existing** choices, warnings and removals dialog, and commits with
  `commit_drawing_import`.
- Q3 The receipt is applied to the drawing automatically (line keys, configured names, part numbers, server
  lengths); runs turn "imported" color as in AutoCAD.
- Q4 Re-sending updates the same lines (matched by `cad_run_id`); removals need confirmation; locked or quoted
  schedules go to a new version on request. All of this is existing server behaviour.
- Q5 After commit: "Request a quote" (with blockers explained) and "Open in System Designer" (the new design
  is seeded from rooms, cabinets and measured home runs).

### 5.7 Interchange (FR-X)

- X1 **Export DXF** (R2018 ASCII) with layers, linetypes, `IL-*` blocks, `ILLUMENATE` XData on every toolkit
  entity and the `ILLUMENATE` dictionary (SETTINGS, STYLES, ZONES, OVERRIDES). Opened in AutoCAD with toolkit
  0.5+, ILCHECK and ILQUOTE work on it as if it had been drawn there. AUDIT reports 0 errors.
- X2 **Import DXF from AutoCAD**: toolkit XData becomes live web runs, rooms, cabinets, PSUs, wires and
  controls; the rest becomes editable geometry or an underlay (the user chooses).
- X3 **Export clean DXF** (ILSTRIP): no XData or dictionary, with toolkit layers kept or merged.
- X4 Export the package (`.ilq`) and import a receipt, for staff troubleshooting.
- X5 DWG: §6.15.

### 5.8 Non-functional (NFR)

| # | Requirement |
| --- | --- |
| N1 | Pan and zoom at 60 fps with 1,000 runs plus a 20,000-entity DXF underlay or a 24×36 PDF page on a mid-range laptop. Snap search under 4 ms per mouse move. |
| N2 | Live hints under 16 ms per vertex while drawing (TypeScript geometry); the full LISP check and package for 200 runs under 300 ms in the worker, and for 1,000 runs under 2 s (spike 0.1 confirms). |
| N3 | Editor first load under 600 KB gzipped (lazy: pdf.js, DXF parser, LISP VM in a worker). |
| N4 | Latest two versions of Chrome, Edge, Safari and Firefox; desktop 1280 px and wider; a tablet can view and make light edits (later). Mouse, trackpad pinch and keyboard. |
| N5 | No lost work: IndexedDB draft every 2 s, server autosave every 10 s (debounced), optimistic concurrency, recovery prompt. |
| N6 | Accessibility: keyboard-reachable panels, visible focus, color is never the only signal (issue icons as well as colored runs), WCAG 2.2 AA for panels. The canvas itself is pointer-first by nature. |
| N7 | Security: no prices or costs anywhere (catalog is already price-free; the import strips prices). Uploaded files are parsed in a worker with size limits. Server-side validation of every package and document. |
| N8 | Precision: world coordinates in float64 inches; lengths agree with the LISP within 0.001 in on the golden cases. |

---

## 6. Architecture

### 6.1 Options considered for keeping the web in sync with the AutoCAD code

| Option | What it means | Verdict |
| --- | --- | --- |
| A. Port the LISP to TypeScript by hand | A third copy (LISP, Python `drawing_checks.py`, TS), kept equal by golden fixtures. | Rejected as the primary approach: every toolkit change must be made twice, and drift is caught only where fixtures reach. It is kept as the **fallback** for hot paths if spike 0.1 shows the VM is too slow. |
| **B. Run the pure LISP in the browser** | A TypeScript AutoLISP interpreter (a port of `mini_lisp.py`) runs `il-util … il-controls.lsp` unchanged in a worker. | **Chosen for logic.** One source. CI already proves the subset works outside AutoCAD. |
| C. Also run `il-commands.lsp` on an emulated AutoCAD | Emulate the entity database, `ssget`, `command "_.PLINE"`, `getpoint`, `getkword` and so on, so the AutoCAD commands run in the browser. | Rejected for v1: it means emulating a large part of AutoCAD, and the result is command-line prompt UX on a web page, which is the opposite of "simple". It can be reconsidered later for single non-interactive commands. |
| D. Run real AutoCAD in the cloud | Autodesk Platform Services **Automation API** (formerly Design Automation) runs AutoLISP headless on AutoCAD; its docs say basic AutoLISP (`entget`, `ssget`, `entmod`) runs, and `vla-`/`vlax-` do not, which suits our LT-safe core. | Rejected for interactive editing (latency, cost per job, Autodesk account). **Kept as an option** for DWG conversion and a "real AutoCAD" release check (§6.15, §7 G6). |
| E. One declarative spec that generates LISP, TS and Python | Rewrite the rules as data and generate all three. | Rejected: it means rewriting a shipped, tested toolkit to save work we avoid with B anyway. |

The interactive layer is solved with a **command manifest** (§6.8) rather than shared code.

### 6.2 Chosen architecture

```
                       tools/cad_toolkit/lisp/*.lsp   (one source)
                         │ pure files          │ host files (AutoCAD only)
             ┌───────────┴──────────┐          │
             ▼                      ▼          ▼
   mini_lisp.py (CI)      cad-lisp VM (browser)   AutoCAD / LT / Mac
             │                      │              (il-commands.lsp)
             │            ┌─────────┴───────────────────────────┐
             │            │ Web Drawing Editor (React)          │
   golden fixtures ◄──────┤  canvas · tools · layers · sheets   │
   (Python = TS = LISP)   │  doc ilw/1 ──host adapter──► model  │──► il-check / il-run-hint
             │            │                                     │──► il-package ─► ilq/2 (source: web)
             │            └──────────────┬──────────────────────┘
             │                           │ JSON package          ▲ receipt (il-run-with-receipt)
             ▼                           ▼                       │
   drawing_checks.py ◄────── portal/drawing_import.py (preview / commit) ──► schedule lines
                                         │
                                         ▼
                              ilL-CAD-Import · System Designer seed

   DXF + ILLUMENATE XData  ◄──── export / import ────►  AutoCAD toolkit
```

### 6.3 Packages and files

New code in the existing `tools/system_designer` npm workspace, so it shares the schemas, assets,
serializers, UI kit and build pipeline:

```
tools/system_designer/packages/
  cad-lisp/            AutoLISP reader + interpreter (TS port of mini_lisp.py), worker entry,
                       loads ../../../cad_toolkit/lisp/*.lsp via Vite ?raw, lisp-manifest.json (hashes)
  cad-core/            DOM-free: ilw/1 schema (Zod), geometry (bulge math, offsets, fillet, intersections),
                       spatial index, snaps, command state machines, undo, host adapter (doc → LISP model),
                       copy rules, DXF read (dxf-parser) and write (extends serializers/dxf), migrations
tools/system_designer/app/src/plan/
  PlanEditor.tsx, canvas/ (renderer, underlays), tools/ (one file per command), panels/ (layers,
  properties, checks, styles, DMX), CommandLine.tsx, StatusBar.tsx, SendDialog.tsx (reuses the import UI)
tools/cad_toolkit/commands.json        the command manifest (§6.8)
illumenate_lighting/illumenate_lighting/system_design/web_drawing.py    API (§6.12)
illumenate_lighting/illumenate_lighting/doctype/ill_web_drawing/         doctype (§6.11)
illumenate_lighting/templates/pages/plan_editor.{py,html}                mount
illumenate_lighting/public/system_designer/                              committed bundle (as today)
```

Route: `/portal/schedules/<schedule>/plan`, added before the schedule route in `hooks.py`, like the
designer's `/design`. (`/portal/drawings` is taken by drawing requests.)

### 6.4 Document model `ilw/1`

The web drawing deliberately **mirrors DXF and the toolkit's XData**, so export and import are direct and the
host adapter is simple:

```ts
{
  schema: 'ilw/1', units: 'in', handseed: '2F3A',           // hex handles, like AutoCAD
  settings: { schedule, schedule_version, project, sheet_size, plot_scale, title_block },
  layers:   [{ name, aci, color, linetype, lineweightMm, on, frozen, locked, plot }],
  linetypes:[...], blocks: 'cadAssets@<hash>',              // symbols come from cadAssets, not stored
  sheets:   [{ id, label, size, viewport: { center, scale }, scale: { status, ratio, check_dimension_in } }],
  underlays:[{ id, sheet, kind: 'pdf'|'image'|'dxf', file, page, transform, clip, opacity, locked }],
  entities: [{
    handle: '1A7', type: 'LWPOLYLINE'|'LINE'|'ARC'|'CIRCLE'|'TEXT'|'MTEXT'|'INSERT'|'DIMENSION',
    layer, color?, linetype?, layout: 'Model'|'<sheet>',
    vertices?: [[x, y, bulge], ...], closed?, ...,           // type-specific geometry
    xdata?: { ILLUMENATE: { sv: '1', kind: 'RUN', id: 'L1-01', type: 'L1', style, start_feed,
                            lead_in, feed, breaks, spans, cabinet, line_key, part_number, ... } }
  }],
  dictionary: { ILLUMENATE: { SETTINGS, STYLES, ZONES, OVERRIDES } }   // same JSON as the DWG's XRECORDs
}
```

- The XData keys, value encoding (text, 250 characters), `sv` schema version and migrations match
  `il-xget`/`il-xset`/`il-xmigrate`. A CI gate keeps them equal (§7 G4).
- Handles are hex, unique and never reused, so `ilq/2` `handle` and `identity: "xdata"` mean the same thing
  as in AutoCAD.
- Limits: 10 MB document JSON (underlays are separate files), 1,000 runs (`ILQ_MAX_RUNS`), 50,000 entities.
- Zod schema, exported JSON Schema and a Python validator, like `ilq/2`.

### 6.5 The LISP VM in the browser (`packages/cad-lisp`)

- **Port** `mini_lisp.py` to TypeScript with the same semantics it documents: dynamic scope, 32-bit integer
  wrap and integer division, case-insensitive symbols, `nil` as the empty list, dotted pairs,
  `vl-catch-all-apply`, `rtos`/`itoa`/`atof` formatting, and the builtin subset the pure files use. About
  1,000–1,200 lines of TS.
- **Load** the pure files in the same order `package_bundle.py` joins them. They are imported as raw text at
  build time and stamped into `lisp-manifest.json` with each file's SHA-256 and `*il-version*`.
- **Run** in a Web Worker. The API is `hint(run)`, `check(model, catalog, today)`, `package(model, catalog,
  issues, platform)`, `applyReceipt(model, receipt)` and `dmxPatch(model, catalog)`, each calling the LISP
  function of the same name (`il-run-hint`, `il-check` + `il-check-controls`, `il-package`,
  `il-run-with-receipt`, `il-dmx-patch`). Values cross the boundary as JSON ↔ association lists through the
  toolkit's own `il-json`.
- **Incremental**: per-run hints are cached by a run fingerprint, so only edited runs are recomputed. The whole
  check runs debounced (300 ms after the last edit) and on demand.
- **Hashing**: `il-package-content` text is produced by the LISP; its SHA-256 is computed by a native,
  synchronous builtin bound over `il-sha256` (WebCrypto's `digest` is asynchronous and the interpreter is
  synchronous). A parity test asserts the native builtin equals the LISP `il-sha256` on the fixtures.
- **What stays TypeScript**: geometry needed at 60 fps (snaps, hit tests, live length while the mouse moves).
  It is tested against the LISP: the `lisp-subset.json` cases plus property tests over random bulged
  polylines comparing `il-path-length` in the VM with `cad-core` (tolerance 1e-6 in).
- **Fallback**: if spike 0.1 misses the N2 budget after profiling, the hottest functions move to TS one at a
  time, each with a parity test against the VM on the fixtures. The VM stays the reference.

### 6.6 The host adapter (document → LISP model)

In AutoCAD, `il-model` (in `il-commands.lsp`) collects entities into the model association list. The web
adapter does the same from `ilw/1`: runs from LWPOLYLINEs with `kind: RUN` XData (fields exactly as
`il-run-from-entity`), rooms, cabinets, PSUs, wires, controls, zones, others and overrides from the
dictionary, and layouts mapped to sheets. A CI test feeds the **same fixture drawings** through both
collectors: AutoCAD's via a recorded entity dump replayed in `mini_lisp`, and the web's via `cad-core`. It
asserts that the model and the resulting package are identical.

### 6.7 Rendering

- **Canvas 2D** for the editable drawing: a world→screen affine in float64, an R-tree (`rbush`, MIT) for
  culling and hit tests, per-layer cached paths, and overlay layers for grips, snaps, the rubber band and the
  dynamic input tooltip. Lineweights are shown in screen pixels (toggle), and linetypes come from
  `layers.json`.
- **PDF underlays**: `pdf.js` (Apache-2.0) renders the page into zoom-level tiles in a worker. Vector path
  extraction for snapping is a spike 0.2 question.
- **DXF underlays**: `dxf-parser` (already a dev dependency, MIT) → read-only entities drawn from a cached
  bitmap at rest and from vectors while zoomed in. If the 20,000-entity budget fails on Canvas 2D, the
  underlay uses WebGL through `dxf-viewer` (MIT, three.js, instanced blocks), and the editable layer stays
  Canvas 2D.
- Symbols (`IL-*` blocks) come from `cadAssets.ts`, drawn in paper inches and scaled by the plot scale, as in
  the toolkit (`il-symbol-scale`).

### 6.8 Commands, input and the command manifest

- Every tool is a **state machine** in `cad-core` (DOM-free, unit-testable). It consumes events (point picked,
  value typed, option chosen, Enter, Esc) and emits prompts and preview geometry. Mouse tools and the command
  line drive the same machines.
- The **command line** accepts commands and aliases (`PL`, `L`, `A`, `C`, `M`, `CO`, `RO`, `SC`, `MI`, `O`,
  `F`, `BR`, `J`, `X`, `E`, `U`, `LA`, `DI`, `DT`, `DLI`, `Z`, `MA`, and every `IL*` name). Prompts use
  AutoCAD's style ("Specify next point or [Arc/Close/Undo]:"), with options clickable. Enter or Space repeats
  the last command, and Esc cancels.
- **Toolbar** (beginner mode): Draw · Modify · Lighting · Annotate · View groups with icons and labels; a
  guided "Draw a run" flow (pick style → Type → draw → done). Both modes are always available.
- **Command manifest** `tools/cad_toolkit/commands.json`, one source for AutoCAD help and the web UI:

  ```json
  { "name": "ILTAPE", "aliases": ["ILT"], "group": "Lighting",
    "summary": "Draw a run from its feed end (lines and arcs).",
    "prompts": ["Schedule Type for these runs", "Draw the run from its feed end"],
    "autocad": "il-commands.lsp", "web": "implemented", "web_tool": "drawRun", "wp": "4.2" }
  ```

  `web` is `implemented`, `planned` (needs a WP number) or `autocad-only` (needs a reason). ILHELP in AutoCAD
  and the web help drawer are both generated from it.

### 6.9 Snaps, ortho, polar, dynamic input

Snap candidates come from the R-tree near the cursor (editable entities and DXF underlays). Priority:
Endpoint > Intersection > Center > Midpoint > Perpendicular > Tangent > Quadrant > Nearest. There is an
AutoCAD-like marker glyph per snap and a tooltip. Tracking from snap points is "later". The toolkit's snapped
vertex tolerance (`*il-snap-tolerance*`, 0.01 in) is shared, so jumper and feed picks behave as in AutoCAD.

### 6.10 Undo and redo

One command is one undo step (`zundo` over immer patches on the document store, as the designer does). The
automatic ILUPDATE pass (tags, markers, copy rules) is folded into the command's step, so Undo never leaves
stale tags.

### 6.11 Persistence: `ilL-Web-Drawing`

| Field | Type | Notes |
| --- | --- | --- |
| `title` | Data | |
| `fixture_schedule`, `schedule_version`, `ill_project`, `customer` | Link / Int | Permissions follow the schedule (`can_read_schedule` / `can_edit_schedule`). |
| `document_json` | Long Text (or private File over 1 MB) | `ilw/1`, validated server-side. |
| `document_sha256`, `doc_rev` | Data / Int | Optimistic concurrency and the package's `drawing.rev`. |
| `underlays` | Table (`ilL-Web-Drawing-Underlay`: file, kind, page, sha256) | Private files. |
| `lisp_version`, `web_version`, `catalog_snapshot` | Data | Provenance. |
| `editing_user`, `editing_heartbeat` | Link / Datetime | Soft lock: one editor at a time; others open read-only with "Take over". |
| `last_import` | Link `ilL-CAD-Import` | |
| `revisions` | via Version tracking plus named snapshots ("Save revision") | |

Client: Dexie draft per drawing (draft every 2 s), server autosave every 10 s, conflict dialog on a stale
`modified`.

### 6.12 Server API (`system_design/web_drawing.py`)

`create_web_drawing(schedule, from_import=None)` · `get_web_drawing(name)` ·
`save_web_drawing(name, document, expected_rev)` · `upload_underlay(name, file)` ·
`take_over_editing(name)` · `export_web_drawing_dxf(name, clean=0)` (server copy of the client export, for
Desk and staff) · `import_dxf_to_web_drawing(schedule, file)`. Sending to the schedule uses the **existing**
`preview_drawing_import` / `commit_drawing_import` with the package as `.ilq` content; no new import path.
Every endpoint goes through `cad_access.py` and the new flag (§6.16).

### 6.13 Import path

Unchanged server behaviour. Additions: `ill_cad_min_versions` gains a `web` key; telemetry tags
`source_tool=web` (the CAD Import Funnel and CAD BOM Match already filter by tool); the `ilL-CAD-Import`
record links back to the web drawing.

### 6.14 DXF interchange with AutoCAD

- **Export**: extend `packages/serializers/src/dxf` (already AUDIT-clean) with LWPOLYLINE bulges, TEXT,
  DIMENSION (as blocks), `IL-*` INSERTs with attributes, the `APPID` table entry `ILLUMENATE`, XData groups
  `1001 ILLUMENATE` + `1000` key/value pairs, and the `ILLUMENATE` named dictionary with XRECORDs of group-1
  chunks of 250 characters, exactly as `il-store` writes them. `$INSUNITS = 1`, `$HANDSEED` from the
  document.
- **Import**: a client reader (`dxf-parser` does not keep XData or OBJECTS fully, so `cad-core` adds a small
  group-code pass for XData and the ILLUMENATE dictionary). `portal/dxf_ingest.py` gains the same XData read,
  so an AutoCAD DXF with toolkit data imports with `identity: "xdata"` rather than the layer convention.
- **Round-trip acceptance**: web → DXF → AutoCAD (ILCHECK, ILQUOTE) → package **content hash equal** to the
  web's package for the same drawing. AutoCAD → DXF → web → package hash equal to AutoCAD's.

### 6.15 DWG

Most dealers receive DWG backgrounds. Options:

| Option | Notes | Recommendation |
| --- | --- | --- |
| Ask for DXF or PDF | Any AutoCAD or LT saves DXF; architects can send PDF. Zero cost, no licence risk. | **v1.** |
| LibreDWG in WebAssembly | Every LibreDWG-based browser build found (libredwg-web, dwg2dxf-converter, libdxfrw-web) is GPL-licensed. Bundling it into our app has copyleft consequences. | **Do not use** without a legal review. |
| Autodesk APS Automation API | Real AutoCAD in the cloud converts DWG→DXF on upload and DXF→DWG on export. Needs an Autodesk account and a per-job cost, and the call goes from the server (or n8n) to Autodesk. | **Spike in Phase 6** if pilots ask for DWG. |
| ODA SDK / File Converter | Commercial membership for the SDK; the free converter is a desktop binary that Frappe Cloud cannot run. | Not recommended. |

### 6.16 Access, flags and security

- Site flag `ill_cad_web` (default **off**). Pilots use the existing `ill_cad_pilot_customers` or the
  designer's pilot list; `ill_cad_all_dealers` opens it to everyone (same rules as the toolkit).
- Prices never appear (D6): the catalog is price-free (`forbidden_keys`), the package is price-free, and
  the import strips prices anyway.
- Uploaded files are private; PDF up to 50 MB, DXF up to 20 MB (`MAX_DXF_BYTES`), images up to 20 MB. Files
  are parsed in workers, and the editor has no `dangerouslySetInnerHTML` (designer lint rule).
- The server validates `ilw/1` and `ilq/2` against JSON Schema with size limits, and rate-limits saves.

---

## 7. The sync contract: how an AutoCAD change reaches the website

**Release flow.** A developer changes a `.lsp` file → runs the toolkit tests → runs
`npm run build --prefix tools/system_designer` (embeds the LISP, rebuilds the toolkit zip as today) → commits
the source, the toolkit zip and the web bundle → CI passes the gates below → after deploy, **web users get
the change at once**, and AutoCAD users get the "download the current toolkit" warning when
`min_toolkit_version` is raised.

| Gate | Checks | Fails when |
| --- | --- | --- |
| **G1 LISP hash** | `lisp-manifest.json` in the committed bundle against the SHA-256 of `tools/cad_toolkit/lisp/*.lsp` and `*il-version*` (like `test_cad_bundle.py`). | The LISP changed but the web bundle was not rebuilt. |
| **G2 Three-way parity** | Every case in `fixtures/cad/` (hints, checks, packages, receipts) through `mini_lisp.py`, the TS VM and, for checks, `drawing_checks.py`: identical JSON. | Interpreter drift, or a server rule not updated. |
| **G3 Command manifest** | Every `(defun c:IL…)` in `il-commands.lsp` is in `commands.json`; every `implemented` entry has a registered web tool; `planned` entries have a WP; `autocad-only` entries have a reason. | A new or renamed AutoCAD command with no web decision. |
| **G4 XData schema** | `*il-xdata-schema*` and the XData keys read in `il-run-from-entity` (and the other collectors) against the `ilw/1` XData Zod keys; a version bump needs a migration step in both `il-xmigrate` and the web migrator. | Schema drift between AutoCAD and web drawings. |
| **G5 Assets** | Layers, linetypes and blocks come from `layers.json` / `cadAssets` (already one source); a test asserts the web's layer defaults equal `planLayers`. | A hand-edited layer list. |
| **G6 Round trip** | CI: web fixture → DXF → XData reader → model equal. Release, on a staff Windows machine: `accoreconsole` opens the web DXF, runs ILQUOTE, and the package content hash equals the web's (added to `run_tests.scr`). | Export loses data, or AutoCAD and web disagree. |
| **G7 Versions** | The web reports `source.version = "<web>+lisp.<il-version>"`; `ill_cad_min_versions.web` can block stale tabs (a long-open tab gets "reload to update" when the server's LISP hash differs). | An old tab sends a package from old rules. |

**What does not sync automatically**, by design: a new *interactive* AutoCAD command still needs its web
tool (G3 forces the decision), and the AutoCAD prompt wording is mirrored in the manifest rather than
generated into the UI copy.

---

## 8. UX specification

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ ilLumenate · Smith Residence · Schedule v3 · Plan     [Saved 10:42]  Send to schedule ▸    │
├──────┬───────────────────────────────────────────────────────────────────┬────────────────┤
│ Draw │                                                                   │ Properties     │
│ ▭ PL │                                                                   │  L1-03 · Run   │
│ ╱ L  │                 canvas (model or sheet)                           │  Style: Cove…  │
│ ◠ A  │       underlay at 40%, runs colored by state, tags, markers        │  Type: L1      │
│ Modify│                                                                   │  120.25 in     │
│ Light│                                                                   ├────────────────┤
│ ▬ Run│                                                                   │ Layers         │
│ ⌂ Rm │                                                                   │ Checks (2 ⚠)   │
│ ▣ Cab│                                                                   │ Styles         │
├──────┴───────────────────────────────────────────────────────────────────┴────────────────┤
│ Command: PL  Specify next point or [Arc/Close/Undo]:  @48<0                               │
│ Model | Sheet E-1 (1/4"=1'-0", verified) | +        SNAP GRID ORTHO POLAR OSNAP  x 312.5   │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

- Runs are colored like the toolkit's `il-color-run`: green ok, yellow warning, red error, layer color once
  imported. Issues also show an icon.
- Feet-inches everywhere in the UI (`10'-0 1/4"`), with inches in tables.
- First-run tour: load plan → calibrate → pick style → draw a run → send. Help is generated from the
  manifest.
- Keyboard shortcuts follow AutoCAD (F3, F7, F8, F9, F10, Ctrl+Z/Y, Ctrl+C/V with base point, Delete, Esc,
  Enter/Space).
- Paper prototype reviewed with two dealers (one non-CAD, one LT user) and an Applications Engineer in
  Phase 0.

---

## 9. Testing and acceptance

| Level | What |
| --- | --- |
| Unit (Vitest) | VM builtins against `mini_lisp` semantics; geometry (bulge arcs, offset, fillet, intersections, nearest); every tool's state machine (prompt sequences and results); copy rules; DXF writer/reader; schema migrations. |
| Parity (CI) | G2, G4, G6 above; property tests for path length. |
| Python | `ilw/1` validator; `web_drawing.py` permissions (dealer A cannot read dealer B), locks, concurrency; XData DXF ingest; import with `source_tool=web`. |
| E2E (Playwright, `--trace off`) | Upload PDF → calibrate → draw a run with two arcs and a jumper → room → cabinet → PSU → check panel clean → send → choices → commit → receipt shown → re-send unchanged = 0 changes; undo/redo through all of it; DXF export → import equals. |
| Performance | N1/N2 benchmarks in CI on a fixed large fixture (fail at +25% regression). |
| AutoCAD (release) | Web DXF in full AutoCAD, LT 2025 and Mac: AUDIT 0 errors, ILCHECK same issues, ILQUOTE same content hash. |
| Pilot acceptance | 3 dealers × 2 real jobs each; drawn lengths within 0.5% of an AutoCAD toolkit takeoff of the same plan; CAD BOM Match ≥ 98% on resulting orders (existing report). |

---

## 10. Phased plan

S ≈ 1 week, M ≈ 2–3 weeks, L ≈ 4–6 weeks, for one full-stack developer with domain support (the designer
plan's convention). The size after each phase name is the phase as a whole; Part II sizes each work package,
and W8 adds them up in developer-weeks. Where they differ, W8 is the estimate.

### Phase 0: Spikes and decisions (M)

| WP | Work | Exit |
| --- | --- | --- |
| 0.1 | TS port of `mini_lisp` (minimal), load the pure LISP in a worker, run `check-cases.json` and `packages/valid`, measure. | Results equal `mini_lisp.py` on all fixtures; timings against N2. **Go/no-go for option B.** |
| 0.2 | Renderer prototype: pan, zoom, snap and polyline drawing over three real backgrounds (PDF 24×36, PDF scanned, 20k-entity DXF). | N1 met on Canvas 2D, or the WebGL underlay decision taken. |
| 0.3 | Hand-written DXF with toolkit XData and dictionary opened in AutoCAD full, LT 2025 and Mac; ILCHECK and ILQUOTE run. *Needs a staff Windows/Mac machine.* | Toolkit reads web-written runs. |
| 0.4 | Paper or Figma prototype with two dealers and an AE. | Toolbar and command line flows agreed. |
| 0.5 | Decisions in §12 recorded here. | Signed off. |

### Phase 1: Foundations (M)

1.1 `packages/cad-lisp` complete, with G1 and G2 in CI · 1.2 `ilw/1` schema (Zod, JSON Schema, Python) and
migrations · 1.3 `cad-core` geometry with parity tests · 1.4 `ilL-Web-Drawing` doctype, `web_drawing.py`,
access, flag · 1.5 route, mount, empty editor opening from a schedule, autosave and lock ·
1.6 `commands.json` with G3 (all IL commands initially `planned`).
**Exit:** an authorized user opens an empty plan from a schedule, it saves and reloads, and the CI gates are
green.

### Phase 2: Drafting core (L)

2.1 renderer, viewport, R-tree, selection · 2.2 command system, command line, aliases, prompts, toolbar ·
2.3 PLINE (line and arc modes), LINE, ARC, CIRCLE, RECTANG · 2.4 MOVE, COPY, ROTATE, SCALE (Reference),
MIRROR, OFFSET, FILLET, BREAK, JOIN, EXPLODE, ERASE, grips · 2.5 snaps, ortho, polar, grid, dynamic input,
feet-inches parsing · 2.6 undo/redo · 2.7 layers panel and properties panel · 2.8 MEASURE, TEXT,
DIMLINEAR/ALIGNED.
**Exit:** a drafter can reproduce a test plan's geometry in the web within 0.01 in, using only the keyboard,
or only the toolbar.

### Phase 3: Underlays, scale and sheets (M)

3.1 PDF and image underlay (tiles, opacity, clip, lock) · 3.2 DXF underlay with read-only layers ·
3.3 Calibrate (ILSCALE) and check dimension, sheet scale status · 3.4 sheets with title block and viewport ·
3.5 plot to PDF.
**Exit:** a calibrated plan measures a known 20 ft wall within 0.25%; the plotted PDF matches the screen.

### Phase 4: ilLumenate tools (L)

4.1 style picker (live catalog, presets, options) · 4.2 Draw Run with live hints and over-max choice ·
4.3 Convert, Jumper, Feed · 4.4 Room, Cabinet, PSU, Connect, Wire · 4.5 Control, Zone, DMX patch ·
4.6 Other lines, Override · 4.7 automatic ILUPDATE (tags, markers, `il-fix-copies` semantics) ·
4.8 live check panel through the VM, plus "Check with portal" · 4.9 ILOUT tables.
**Exit:** every manifest entry for these is `implemented`; for the 20-run fixture job (`job-20-runs.json`),
the web package equals the AutoCAD package for the same geometry.

### Phase 5: Send to schedule (M)

5.1 package via VM, send dialog reusing the import UI (choices, warnings, removals, new version) · 5.2 receipt
write-back and imported state · 5.3 re-send, diff against the previous import · 5.4 Plan PDF with the
import · 5.5 Request a quote with blockers; Open in System Designer (seed) · 5.6 entry points on the schedule
and project pages, "New schedule from drawing" · 5.7 telemetry and `ill_cad_min_versions.web`.
**Exit:** the E2E in §9 passes on staging; CAD Import Funnel shows `web`.

### Phase 6: AutoCAD interchange (M)

6.1 DXF export with XData, dictionary, blocks; AUDIT clean · 6.2 DXF import of toolkit drawings (client
and `dxf_ingest.py`) · 6.3 clean export (ILSTRIP) · 6.4 G6 round trip in CI and `accoreconsole` ·
6.5 DWG spike with the APS Automation API (if §12 Q2 says so).
**Exit:** both round trips give equal content hashes on the fixture jobs.

### Phase 7: Pilot and hardening (M)

7.1 pilot with three dealers (one non-CAD, one LT, one full AutoCAD) and the AE team · 7.2 performance at
1,000 runs, accessibility pass, error reporting · 7.3 tour, help, a dealer guide and a short video ·
7.4 Resources page entry next to the toolkit download · 7.5 GA criteria review.
**GA criteria:** pilot acceptance in §9 met; zero price or cost exposure in a security review; no P1 bugs open
for two weeks.

### 10.9 Faster first release (optional cut)

Phases 0, 1, a reduced 2 (PLINE, LINE, MOVE, COPY, ROTATE, SCALE, ERASE, snaps, undo, layers), 3.1 + 3.3,
4.1–4.4 + 4.7–4.8, and 5.1–5.3: "draw tape and linear runs, rooms, cabinets and PSUs over a calibrated PDF,
and quote". This is **Release 1** (§12 Q5): about 40–50 developer-weeks (W8). Controls, DXF interchange,
sheets and plotting follow in Release 2.

### 10.10 Relationship to the System Designer roadmap

This editor delivers the designer's **plan view** (§12.3, Phase 6 of that plan): measured home runs and wire
paths from ILWIRE feed the designer's engine as they already do for AutoCAD imports. The designer's
WP-6.x for plan view should be replaced by a link to this plan rather than built twice.

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Scope creep toward "all of AutoCAD" | High | High | The command list in §5.1 is the contract; additions go through the manifest with a WP. |
| LISP VM too slow, or subtly different | Medium | High | Spike 0.1 first; G2 three-way parity; TS fallback per hot function. |
| Canvas performance on big backgrounds | Medium | Medium | Spike 0.2; tiles; WebGL underlay option. |
| Dealers mostly have DWG | High | Medium | DXF/PDF guidance in v1; APS spike in Phase 6; never GPL code in the bundle. |
| Web drawings and AutoCAD drawings drift | Medium | High | G3, G4, G6; XData schema versioning with migrations on both sides. |
| PDF scale mistakes cause wrong quotes | Medium | High | Existing scale gate (unverified blocks quote, AE confirms); check dimension; server lengths win. |
| Lost work in the browser | Low | High | Dexie drafts, autosave, lock, recovery prompt, revision snapshots. |
| Frappe Cloud runs `bench build`, not Vite | Known | Low | Committed bundle pattern already used by the designer and finder. |
| Two editors on one drawing | Low | Medium | Soft lock with heartbeat and take-over; read-only for others. |
| Third-party licences | Low | Medium | Only MIT/Apache dependencies (`pdf.js`, `dxf-parser`, `rbush`, optionally `dxf-viewer`); licence check in CI. |

---

## 12. Decisions (accepted 2026-11-23)

Kevin accepted every recommendation on 2026-11-23. Part II builds to these; a change goes back to Kevin
and is recorded here in the same PR.

| # | Question | Decision |
| --- | --- | --- |
| Q1 | **Sync approach** | Run the toolkit's pure LISP in the browser (option B) with a command manifest for the interactive layer. Subject to spike 0.1: if it fails, W-0.1 records the fallback (option A for the failing functions only) and Kevin confirms it. |
| Q2 | **DWG** in v1 | **No.** DXF and PDF in v1. APS Automation spike in Phase 6 (W-6.5) only if pilots ask for DWG. No GPL code in the bundle. |
| Q3 | **Audience** | Non-CAD dealers and Applications Engineers first; AutoCAD users may use it too. The AutoCAD toolkit stays supported. |
| Q4 | **Round trip** to AutoCAD | Required for GA (Release 2, Phase 6). |
| Q5 | **First release** | The faster cut (§10.9) is **Release 1**; everything else is **Release 2** (Part II, W8). |
| Q6 | **Where it lives** | System Designer workspace and bundle, as a lazy entry; it replaces the designer's planned plan view (§10.10). |
| Q7 | **Multi-user** | Single editor with a soft lock in v1. |
| Q8 | **Tablets** | Desktop first; tablet view and light edits after GA. |
| Q9 | **AutoCAD release checks** | A staff Windows machine with full AutoCAD and LT; Mac if a pilot dealer uses it. |

---

## 13. Success metrics

- Share of CAD imports with `source_tool = web` at 90 days after GA (target: 40% of drawing imports).
- Time from "plan received" to "schedule built" for a 20-run job (target: under 45 minutes for a trained
  dealer).
- CAD BOM Match for web-drawn jobs ≥ 98% (same as the toolkit target).
- Quote requests blocked by unverified scale that later need AE correction: under 5%.
- Zero G1–G4 drift incidents reaching production.

---

# Part II — Implementation handbook

Work package IDs are `W-<phase>.<n>`. Each WP says which release it belongs to (**R1** = Release 1, the
faster cut; **R2** = Release 2, to GA). The format follows the System Designer handbook:
**ID — title (size, release)** · Depends · Read first · Do · Tests · Done when.

## W1. Rules for the implementing agent

1. **Read before you write.** Read every file a WP lists under "Read first". If the code disagrees with this
   plan, the code wins; note the difference in the PR description and update this document in the same PR.
2. **One WP per PR** unless W7 groups them. Every PR keeps CI green and leaves existing portal and AutoCAD
   flows working.
3. **The LISP is the source of the rules.** Never re-implement in TypeScript a rule that lives in the pure
   LISP files (`il-util`, `il-json`, `il-math`, `il-sha256`, `il-catalog`, `il-model`, `il-controls`). Call
   it through the VM. The only TypeScript copies allowed are (a) interactive geometry needed at 60 fps
   (W5.4) and (b) a fallback approved under Q1, each with a parity test against the VM.
4. **Move, don't copy, host-independent LISP.** When the web needs logic that currently sits in a host file
   (`il-core`, `il-commands`) but uses no AutoCAD function, move it into a pure file, call it from both
   hosts, and bump the toolkit version (W4.9).
5. **Pure packages stay pure.** `packages/cad-lisp` and `packages/cad-core` may not import React, the DOM,
   `window`, IndexedDB, `fetch` or workers' globals except in their explicit `worker.ts` entry. ESLint
   enforces it (the rule the other packages already use).
6. **No prices, no costs.** The catalog is price-free (`forbidden_keys`); nothing in the editor may fetch,
   store or display a price. Packages go to the import unchanged, and the import strips prices anyway.
7. **Permissions first.** Every endpoint starts with `system_design.access.require_read` / `require_edit`
   and `system_design.cad_access.require_cad` plus the web flag (W4.7).
8. **Migrations are additive** and idempotent (CI runs `bench migrate` twice).
9. **Commit generated output.** After changing `tools/system_designer` or `tools/cad_toolkit/lisp`, run
   `npm run build --prefix tools/system_designer` and commit `illumenate_lighting/public/system_designer/`;
   after changing LISP, follow the toolkit release checklist (`tools/cad_toolkit/README.md`) too.
10. **Imperial only** (D11). World units are inches, float64; the UI shows feet-inches.
11. **Git hygiene.** Work on the branch you are given; no force-push on shared branches; no model
    identifiers in commits, code or docs.
12. **Ask, don't guess, on product decisions** not covered by §12 or this handbook.

## W2. Repository conventions

Follow the System Designer handbook's H2 (`docs/SYSTEM_DESIGNER_PRODUCT_PLAN.md`) for Python (tabs, ruff,
copyright header, whitelisting, error contract, doctypes, patches, site flags), Python tests
(`tests/portal_unit` with `test_services.load_service`, installed-site tests), TypeScript (strict, npm
workspaces, Vitest, Playwright with the pre-installed Chromium and `--trace off`) and portal templates
(`tools/check_portal_templates.py`). Additions for this work:

- **Second bundle entry.** `vite.config.ts` gains a second input `app/src/plan/main.tsx` with the stable
  entry name `plan.js` (and its CSS in `plan.css`), so the designer's `designer.js` is not loaded on the plan
  page. Shared code goes to hashed chunks.
- **Workers.** `packages/cad-lisp/src/worker.ts` (the VM) and `app/src/plan/canvas/underlay.worker.ts`
  (pdf.js tiles, DXF parse) are built as Vite worker chunks.
- **Raw LISP imports.** `packages/cad-lisp/src/sources.ts` imports the seven pure files with `?raw`, in the
  order of `PURE` in `tests/portal_unit/test_cad_lisp.py`. A build script writes `lisp-manifest.json`
  (W4.3).
- **Python checks before pushing.** `python -B tools/check_b2b_changes.py`, `ruff check`, `ruff format`.
- **CI.** The existing "System Designer bundle is fresh" step in `.github/workflows/b2b-contracts.yml`
  already builds, tests and diffs the bundle; W6 adds the new gates to it and to the Python unit run.

## W3. Target file tree

```
tools/cad_toolkit/
  commands.json                       NEW  command manifest (W4.2)
  lisp/il-model.lsp                   EDIT *il-source-tool*, il-quote-package (W4.9)
  lisp/il-math.lsp                    EDIT receives pure helpers moved from il-core (W4.9)
  test/mini_lisp.py                   EDIT entity-dump replay for collector parity (W-1.7)
tools/system_designer/
  packages/cad-lisp/src/
    reader.ts  types.ts  interp.ts  builtins.ts  json-bridge.ts  vfs.ts  sha256.ts
    sources.ts  manifest.ts  api.ts  worker.ts  *.test.ts
  packages/cad-core/src/
    schema/ilw.ts  schema/migrate.ts                         document schema and migrations
    geom/{bulge,path,offset,fillet,intersect,nearest,transform}.ts
    index/rtree.ts  snap/snap.ts  units/feet-inches.ts
    commands/{machine,registry}.ts  commands/draw/*.ts  commands/modify/*.ts  commands/il/*.ts
    adapter/model.ts                                         ilw/1 → LISP model (W4.5)
    adapter/receipt.ts  adapter/copies.ts  adapter/update.ts automatic ILUPDATE (W5.8)
    dxf/{read,xdata,write}.ts                                R2: DXF interchange (W5.9)
  packages/data/src/layers.json       (unchanged, read by both)
  app/src/plan/
    main.tsx  mount.tsx  PlanEditor.tsx  store.ts  api.ts  drafts.ts
    canvas/{Canvas.tsx,renderer.ts,overlay.ts,underlays.ts,underlay.worker.ts}
    panels/{Layers,Properties,Checks,Styles,Dmx,Others}.tsx
    CommandLine.tsx  Toolbar.tsx  StatusBar.tsx  SendDialog.tsx  Help.tsx  Tour.tsx
  fixtures/cad/web/                   NEW  ilw/1 documents and entity dumps for parity (W-1.7)
  tests/e2e/plan.spec.ts              NEW
illumenate_lighting/
  hooks.py                            EDIT route /portal/schedules/<schedule>/plan
  templates/pages/plan_editor.{py,html}                      NEW mount (copy system_design.py)
  illumenate_lighting/system_design/web_drawing.py           NEW API (W4.7)
  illumenate_lighting/system_design/ilw_schema.py            NEW Python validator for ilw/1
  illumenate_lighting/doctype/ill_web_drawing/               NEW doctype (W4.8)
  illumenate_lighting/doctype/ill_web_drawing_underlay/      NEW child table
  illumenate_lighting/portal/site_flags.py                   EDIT cad_web_enabled()
  illumenate_lighting/portal/dxf_ingest.py                   EDIT R2: ILLUMENATE XData read
  public/system_designer/{plan.js,plan.css,chunks/…}         generated, committed
  public/system_designer/schema/ilw.schema.json              generated, committed
tests/portal_unit/
  test_cad_web_parity.py  test_cad_commands_manifest.py  test_web_drawing.py  test_ilw_schema.py   NEW
```

## W4. Contracts

### W4.1 `ilw/1` (Zod, `packages/cad-core/src/schema/ilw.ts`)

```ts
export const ILW_SCHEMA = 'ilw/1';
export const ILW_MAX_BYTES = 10 * 1024 * 1024;
export const ILW_MAX_ENTITIES = 50_000;

const Handle = z.string().regex(/^[0-9A-F]{1,16}$/);           // upper-case hex, never reused
const Pt = z.tuple([z.number().finite(), z.number().finite()]);
const Vertex = z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]); // x, y, bulge
const XText = z.string().max(250);                              // AutoCAD XData string limit
const IlXData = z.record(z.string().regex(/^[a-z_]{1,40}$/), XText); // ILLUMENATE pairs, sv included

const Base = {
  handle: Handle, layer: z.string().min(1).max(255), layout: z.string().max(255).default('Model'),
  color: z.number().int().min(0).max(256).nullish(),           // ACI; 256 = ByLayer (default)
  trueColor: z.string().regex(/^#[0-9a-f]{6}$/i).nullish(),
  linetype: z.string().max(255).nullish(),                      // null = ByLayer
  xdata: z.object({ ILLUMENATE: IlXData }).partial().strict().optional(),
};
export const EntitySchema = z.discriminatedUnion('type', [
  z.object({ ...Base, type: z.literal('LWPOLYLINE'), vertices: z.array(Vertex).min(2).max(5000), closed: z.boolean().default(false) }),
  z.object({ ...Base, type: z.literal('LINE'), a: Pt, b: Pt }),
  z.object({ ...Base, type: z.literal('ARC'), center: Pt, radius: z.number().positive(), start: z.number(), end: z.number() }), // radians, CCW
  z.object({ ...Base, type: z.literal('CIRCLE'), center: Pt, radius: z.number().positive() }),
  z.object({ ...Base, type: z.literal('TEXT'), at: Pt, height: z.number().positive(), rotation: z.number().default(0), text: z.string().max(2000), align: z.enum(['left','center','right']).default('left') }),
  z.object({ ...Base, type: z.literal('MTEXT'), at: Pt, height: z.number().positive(), width: z.number().nonnegative(), text: z.string().max(10_000) }),
  z.object({ ...Base, type: z.literal('INSERT'), block: z.string().max(255), at: Pt, scale: z.number().positive().default(1), rotation: z.number().default(0), attributes: z.record(z.string(), z.string().max(250)).default({}) }),
  z.object({ ...Base, type: z.literal('DIMENSION'), kind: z.enum(['linear','aligned']), a: Pt, b: Pt, line: Pt, override: z.string().max(250).nullish() }),
]);

export const IlwDocumentSchema = z.object({
  schema: z.literal(ILW_SCHEMA),
  units: z.literal('in'),
  handseed: Handle,                                            // next handle to issue
  settings: z.object({
    schedule: z.string().max(140), schedule_version: z.number().int().nonnegative(), project: z.string().max(140),
    title: z.string().max(140), rev: z.number().int().nonnegative().default(0),
  }).strict(),
  layers: z.array(LayerSchema).max(2000),                      // name, aci, color, linetype, lineweightMm, on, frozen, locked, plot
  sheets: z.array(SheetSchema).max(200),                       // id (CadId), label, size, titleBlock, viewport {center, scale}, scale {status, ratio, check_dimension_in}
  underlays: z.array(UnderlaySchema).max(50),                  // id, sheet, kind pdf|image|dxf, file (private URL), sha256, page, transform [a,b,c,d,e,f], clip, opacity, locked
  entities: z.array(EntitySchema).max(ILW_MAX_ENTITIES),
  dictionary: z.object({ ILLUMENATE: z.record(z.enum(['SETTINGS','STYLES','ZONES','OVERRIDES','OTHERS']), z.unknown()) }).strict(),
}).strict().superRefine(uniqueHandlesAndKnownLayersAndLayouts);
```

- Model space is the layout `Model`; every other layout is a sheet `label` (AutoCAD layout name), and its
  sheet `id` is `il-sheet-slug` of that name, computed by the VM, not by TypeScript.
- Dictionary values are the same JSON the toolkit stores in XRECORDs (`il-store-json`).
- `schema:export` writes `public/system_designer/schema/ilw.schema.json`; `system_design/ilw_schema.py`
  validates against it plus the cross-reference rules (unique handles, known layers and layouts, XData `sv`
  present on every `ILLUMENATE` entity).
- Migrations: `migrate.ts` lifts older `ilw/*` documents and applies the same XData `sv` steps as
  `il-xmigrate`; G4 keeps the two in step.

### W4.2 Command manifest (`tools/cad_toolkit/commands.json`)

```json
{
  "schema": "il-commands/1",
  "commands": [
    { "name": "ILTAPE", "aliases": [], "group": "Lighting", "kind": "il",
      "summary": "Draw runs of the current style from their feed end (lines and arcs).",
      "prompts": ["Schedule Type for these runs (for example L1)", "Draw the run from its feed end (lines and arcs). Enter finishes the run."],
      "web": "implemented", "web_tool": "il.drawRun", "release": "R1", "wp": "W-4.2" },
    { "name": "PLINE", "aliases": ["PL"], "group": "Draw", "kind": "general",
      "summary": "Polyline of lines and arcs.", "web": "implemented", "web_tool": "draw.pline", "release": "R1", "wp": "W-2.3" },
    { "name": "ILSPIKE", "group": "Admin", "kind": "il", "web": "autocad-only", "reason": "AutoCAD capability probe." }
  ]
}
```

- `kind: "il"` entries must match a `(defun c:<NAME>` in `il-commands.lsp` or `spike/il-spike.lsp`, and
  every such defun must have an entry (G3). `kind: "general"` entries are the web's drafting commands (§5.1).
- `web`: `implemented` (then `web_tool` must be in the web registry), `planned` (then `release` and `wp` are
  required), or `autocad-only` (then `reason` is required).
- The web help drawer, command-line completion, toolbar tooltips and the About panel read it. In R2,
  `package_bundle.py` checks that ILHELP lists the same `il` commands (W-7.3).

### W4.3 `lisp-manifest.json` (written by the build into the bundle)

```json
{ "schema": "il-lisp-manifest/1", "il_version": "0.6.0",
  "files": [{ "name": "il-util.lsp", "sha256": "…" }, …],
  "combined_sha256": "…" }
```

`combined_sha256` is the SHA-256 of the seven files' contents joined in order with `\n`. The server reads
the committed manifest (W4.7 `lisp_hash`), so an open tab can tell that a newer LISP is deployed (G7).

### W4.4 VM worker protocol (`packages/cad-lisp/src/api.ts`)

```ts
export interface LispVm {
  ready(): Promise<{ ilVersion: string; combinedSha256: string }>;
  setCatalog(catalogJson: string): Promise<void>;                 // il-catalog-read on a virtual file
  hint(run: ModelRun, styleId: string): Promise<RunHint>;          // il-run-hint (+ il-hint-text)
  hints(runs: ModelRun[]): Promise<Record<string, RunHint>>;       // batched, cached by fingerprint
  check(model: Model, today: string): Promise<Issue[]>;            // il-check + il-check-controls
  quotePackage(model: Model, today: string, platform: string, rev: number): Promise<{ package: unknown; hash: string; issues: Issue[]; counts: [number, number] }>; // il-quote-package (W4.9)
  applyReceipt(model: Model, receipt: unknown): Promise<ReceiptUpdates>; // il-receipt-index + il-run-with-receipt
  dmxPatch(model: Model): Promise<DmxRow[]>;                       // il-dmx-patch
  sheetSlug(layout: string, used: string[]): Promise<string>;      // il-sheet-slug + il-unique-slug
}
```

- Messages are JSON. `json-bridge.ts` converts JSON ↔ LISP values exactly as `il-json-parse` /
  `il-json-text` do (objects are `(IL-OBJ (key . value) …)`, arrays `(IL-ARR …)`, `true`/`false` are
  `IL-TRUE`/`IL-FALSE`), so a value round-trips the same as in AutoCAD.
- Models passed to the VM use the association-list shape that `il-model` builds (W4.5); `json-bridge`
  builds plain alists for them (not `IL-OBJ`), as `il-model` does.
- Errors: a LISP error becomes `{ code: 'LISP_ERROR', function, message }`; the editor shows "Checks are
  unavailable" and still lets the user save, but disables Send.

### W4.5 Host adapter: `ilw/1` → LISP model (`packages/cad-core/src/adapter/model.ts`)

The web equivalent of `il-model` and `il-run-from-entity` in `il-commands.lsp`. Keys and conversions must
match exactly; collector parity (G2b) proves it.

| Model key | AutoCAD source | Web source |
| --- | --- | --- |
| `drawing.file` | `DWGNAME` | `settings.title` + `.ilw` |
| `drawing.rev` | SETTINGS `rev` | `settings.rev` |
| `drawing.scale_verified` | SETTINGS `scale_verified` | every sheet with runs has scale `verified` |
| `drawing.schedule`, `schedule_version`, `project` | SETTINGS | `settings` |
| `rooms[]`: `id name level env layout` | ROOM XData `id name level env`, group 410 | same XData keys; `layout` |
| `runs[]` | `il-run-from-entity` | LWPOLYLINE with `kind=RUN`: `id handle`, `fixture_type`←`type`, `room location style`, `vertices`←entity vertices, `closed`, `breaks`/`spans` (comma lists → integer lists), `start_feed`, `lead_in`/`jumper_in` (numbers), `feed_method`←`feed` (default `end`), `feed_handles` (comma list), `cabinet psu_hint notes line_key configured_name config_hash part_number`, `server_in` (number), `layout` |
| `cabinets[]`: `id room location_rating access_note` | CABINET XData `id room rating access` | same |
| `psus[]`: `id cabinet item_code runs` | PSU XData (`runs` comma list) | same |
| `wires[]`: `id from to kind length_in` | WIRE XData `id from to wire`; length from `il-path-length` | same; **length computed by the VM** (`il-path-length`), not TypeScript |
| `controls[]` | CONTROL XData (`universe` integer, `start` integer or `"auto"`) | same |
| `styles`, `zones`, `others`, `overrides` | dictionary STYLES, ZONES, OTHERS, OVERRIDES | `dictionary.ILLUMENATE` |
| ordering | runs and controls sorted by id (`vl-sort … <`), the rest in entity order | same: sort with the VM's string `<` (AutoLISP compares by character code) |

Value rules: XData values are strings (as AutoCAD returns them); numbers are converted where `il-model`
converts them (`il-number`, `atoi`), and the adapter calls the VM's own `il-number` / `il-split` through
`json-bridge` helpers, so parsing quirks (e.g. `"1.50"`) match.

### W4.6 XData register (keys written per kind)

| Kind | Keys (besides `sv`, `kind`, `id`, `self`) |
| --- | --- |
| `RUN` | `type style room location start_feed lead_in jumper_in feed feed_handles breaks spans cabinet psu_hint notes line_key configured_name config_hash part_number server_in` |
| `ROOM` | `name level env` |
| `CABINET` | `room rating access` |
| `PSU` | `cabinet item_code runs` |
| `WIRE` | `from to wire` |
| `CONTROL` | `item_code cabinet room universe start control_from notes line_key` |
| `TAG` | `owner` plus the keys `il-tag-run`, `il-tag-wire` and `il-run-markers` write (run tags, wire tags, feed and jumper markers are owned by their entity and redrawn) |

`self` is the entity's own handle, which the copy rules (`il-copies`) use to tell an original from a copy.
W-1.2 generates this table from the LISP as a test fixture, so G4 can compare it with the Zod schema rather
than relying on this copy.

### W4.7 Server API (`illumenate_lighting.illumenate_lighting.system_design.web_drawing`)

Responses use the designer's `respond` / `fail` contract (`system_design/api.py`). Every call: login →
`site_flags.cad_web_enabled()` → `cad_access.require_cad()` → `access.require_read`/`require_edit` on the
schedule.

| Method | HTTP | Body / args | Returns |
| --- | --- | --- | --- |
| `create_web_drawing` | POST | `schedule`, `title?`, `from_import?` (an `ilL-CAD-Import` to start from, R2) | `{name, document, doc_rev}` |
| `get_web_drawing` | GET | `name` | `{document, doc_rev, modified, lock: {user, since, mine}, lisp_hash, catalog_snapshot, read_only}` |
| `list_web_drawings` | GET | `schedule` | `[{name, title, modified, doc_rev, last_import}]` |
| `save_web_drawing` | POST | `name`, `document`, `expected_rev` | `{doc_rev, modified}`, or `fail("STALE", …)` with the server's `doc_rev` |
| `heartbeat` | POST | `name` | `{lock}` (holds the soft lock for 90 s) |
| `take_over_editing` | POST | `name` | `{lock}`; the previous holder's next save fails with `LOCK_LOST` |
| `upload_underlay` | POST (multipart) | `name`, `file`, `kind` | `{id, file, sha256}` (private File, size limits §6.16) |
| `save_revision` | POST | `name`, `label` | `{revision}` (named snapshot) |
| `lisp_hash` | GET | — | `{combined_sha256, il_version}` from the committed `lisp-manifest.json` |
| `export_web_drawing_dxf` | GET | `name`, `clean?` | DXF file (R2) |
| `import_dxf_to_web_drawing` | POST | `schedule`, `file`, `mode` (`live`/`underlay`) | `{name}` (R2) |

Sending to the schedule calls the existing `portal.drawing_import.preview_drawing_import` and
`commit_drawing_import` with `filename="<title>.ilq"` and `content` = the package JSON, plus a new optional
`web_drawing` argument that links the `ilL-CAD-Import` record to the drawing (stored in a new
`web_drawing` Link field on `ilL-CAD-Import`).

### W4.8 Doctypes

**`ilL-Web-Drawing`** (module ilLumenate Lighting, naming `WDR-.YYYY.-.#####`, track changes on):
`title` Data (req) · `fixture_schedule` Link schedule (req) · `schedule_version` Int · `ill_project` Link ·
`customer` Link Customer · `status` Select `Draft/Sent/Archived` · `doc_rev` Int · `document_json` Long Text
· `document_file` Attach (used instead of `document_json` above 1 MB) · `document_sha256` Data ·
`lisp_version` Data · `web_version` Data · `catalog_snapshot` Data · `editing_user` Link User ·
`editing_heartbeat` Datetime · `last_import` Link `ilL-CAD-Import` · `underlays` Table
`ilL-Web-Drawing-Underlay` · `revisions_json` Long Text (named snapshots: label, doc_rev, sha256, file).

**`ilL-Web-Drawing-Underlay`** (child): `underlay_id` Data · `kind` Select `pdf/image/dxf` · `file` Attach
(private) · `sha256` Data · `page` Int · `bytes` Int.

Permissions: System Manager and `ilL Applications Engineer` full; portal access goes through the endpoints
only (`has_permission` delegates to the schedule, as `ilL-System-Design` does via `design_permission`).

### W4.9 Toolkit changes (AutoCAD 0.6.0)

Small, behaviour-preserving LISP changes so both hosts share orchestration:

1. `*il-source-tool*` (default `"autocad"`) and `*il-source-version*` (default `*il-version*`) used by
   `il-package` for `source.tool` / `source.version`. The web sets `"web"` and `"<web>+lisp.<il-version>"`.
   The content hash excludes `source`, so hashes are unchanged.
2. `il-quote-package (model catalog today platform rev)` in `il-model.lsp`: the pure steps of ILQUOTE (check,
   counts, `il-model-hash`, put `rev` and `hash` into `drawing`, `il-package`), returning
   `(package hash issues counts)`. `c:ILQUOTE` calls it, so AutoCAD and web build packages the same way.
3. Move pure helpers out of the host files: `il-point-in-polygon`, `il-midpoint`, `il-centroid` from
   `il-core.lsp` into `il-math.lsp` (room assignment and tag placement); `il-worst-severity`,
   `il-room-slug` and `il-next-zone-id` from `il-commands.lsp` into `il-model.lsp` (run colors, room ids,
   zone ids). Any other pure function the web needs while building Phase 4 moves the same way, listed in that
   WP's PR.
4. Pure room assignment `il-assign-rooms (runs rooms-with-vertices)` extracted from `il-update-all`, so
   ILUPDATE's room logic is shared.
5. Bump `*il-version*` to `0.6.0`, rebuild and commit the bundle zip, and run the `accoreconsole` release
   check (README release checklist).

## W5. Algorithms

### W5.1 The interpreter (`packages/cad-lisp`)

Port `mini_lisp.py` function for function; keep its comments that explain AutoLISP semantics.

- **Values.** `Sym` (interned, upper-cased name); `nil` = `null`; proper lists = JS arrays (as the Python
  uses lists); `Pair` for dotted pairs whose cdr is not a list; strings = JS strings; `T` = the interned
  `Sym('T')`; functions = `LispFunction { params, locals, body }` or native closures.
- **Integers versus reals.** AutoLISP distinguishes `2` and `2.0` (`(/ 7 2)` is `3`, `itoa`, `type`,
  `rtos`). JS numbers cannot, so **reals are JS numbers and integers are a small class `LInt { v }`**
  (32-bit wrap via `| 0` on every operation, integer division truncating toward zero). The reader makes
  `LInt` for integer tokens; arithmetic returns `LInt` only when every argument is `LInt`. Spike 0.1
  measures this choice; if boxing integers is too slow, try the reverse (box reals) before anything else.
- **Scope.** Dynamic scope with shallow binding exactly as `Interpreter.apply`: save each parameter and local
  symbol's global value, bind, run, restore in `finally`.
- **Special forms.** `quote setq if cond while repeat foreach progn and or defun lambda function` (the
  `SPECIAL` table).
- **Builtins.** Exactly the `builtins(interp)` table in `mini_lisp.py` (arithmetic and comparison, list
  functions, string functions, `rtos itoa atoi atof fix float`, trig, `logand logior lsh boole`, `vl-*`
  string and list functions, `vl-catch-all-*`, `open read-line write-line close` on a virtual file system,
  `princ prin1 print` to a log). A test asserts the TS table and the Python table have the same names.
- **Virtual files** (`vfs.ts`): `setCatalog` writes `catalog.json`; `il-catalog-read` opens it with
  `open`/`read-line` unchanged. Writes go to an in-memory map (nothing in the pure files writes today).
- **Native overrides**, each with a parity test against the LISP original on fixtures: `il-sha256` (sync
  SHA-256 in TS) and, only if spike 0.1 needs it, `il-json-parse` / `il-json-text`.
- **Load.** `sources.ts` evaluates the seven files in order once per worker; the worker then answers W4.4
  calls. Startup budget: under 150 ms.

### W5.2 Hint caching

A run's fingerprint is the SHA-256 of `JSON.stringify` of its model alist fields used by `il-run-hint`
(vertices, closed, breaks, spans, jumper_in, style id) plus the catalog snapshot hash. Hints are cached by
fingerprint; the cache clears when the catalog changes. While a vertex is being dragged, the live readout uses
TypeScript geometry (W5.4) for the length and the last VM hint's watts per inch and max run; the VM hint
replaces it on mouse-up.

### W5.3 Package build (Send)

Run the automatic update (W5.8) → `adapter.model(doc)` → `vm.quotePackage(model, today, platform,
settings.rev + 1)` → if `counts[0] > 0`, show errors and stop (the portal refuses them anyway) → call
`preview_drawing_import` → choices dialog → `commit_drawing_import` → `vm.applyReceipt` → write receipt
fields into run XData → `settings.rev += 1`, SETTINGS `last_package_hash = hash` → save. One undo step;
the save happens even if the user then undoes, and the receipt fields stay correct.

### W5.4 Interactive geometry (`packages/cad-core/src/geom`)

- A bulge `b` on vertex `i` describes the arc to vertex `i+1`: included angle `θ = 4·atan(|b|)`, counter-
  clockwise when `b > 0`. Chord `c = |p1 − p0|`, radius `r = c / (2·sin(θ/2))`, arc length `r·θ`, sagitta
  `|b|·c/2`. Centre: the chord midpoint offset by `r·cos(θ/2)` along the chord normal (side by sign of `b`).
  Use the same formulas as `il-bulge-arc` / `il-segment-length` in `il-math.lsp`.
- Arc-mode PLINE: the next arc is tangent to the previous segment by default; for end point `p` and
  incoming tangent direction `t`, `θ = 2·angle(t, p − p0)` and `b = tan(θ/4)` with the turn's sign.
  Options Second point, CEnter, Radius and Angle each reduce to a bulge for the segment.
- Fillet at vertex `i` with radius `R`: interior angle `φ` between the two segments, setback
  `d = R / tan(φ/2)`; trim both neighbours by `d`, insert one vertex, and set the new arc's bulge to
  `± tan((π − φ)/4)`, signed by the turn direction. Refuse if `d` exceeds either segment.
- Offset: offset each segment (lines parallel; arcs radius `± distance`, dropped if the radius reaches 0),
  rejoin neighbours at their intersections, or with an arc on convex corners. Self-intersection cleanup is
  R2; R1 refuses an offset that self-intersects and says so.
- Nearest point on a bulged segment and distance to a path: port `il-segment-nearest` and
  `il-distance-to-path`.
- Parity: `lisp-subset.json` path cases, plus 500 seeded random polylines (bulges in −2..2, closed and open),
  comparing `geom/path.ts` lengths and smallest radius with the VM's `il-path-length` to 1e-6 in.

### W5.5 Feet-inches input (`units/feet-inches.ts`)

Grammar (spaces optional, `-` between inches and a fraction):
`length := sign? (feet "'" (sep? inches)? | inches) ; feet := number ; inches := number ("-"? fraction)? | fraction ;
fraction := int "/" int ; inches may end with '"' ; number := int ("." digits)?`.
Examples: `10'` = 120, `10'6` = 126, `10'-6 1/2"` = 126.5, `6-1/2` = 6.5, `126.5` = 126.5, `-3'` = −36.
Display: `il-num->str`-compatible inches in tables; feet-inches to the nearest 1/16" in the UI.
Coordinates: `x,y`, `@dx,dy`, `@d<angle` (degrees, 0 = east, CCW), each part a `length`.

### W5.6 Snaps

On each pointer move: query the R-tree with a box of the snap aperture (10 px in world units), gather
candidates from entities on visible, unfrozen layers and from DXF underlays, score by type priority (§6.9)
then distance, and keep the best within the aperture. Intersections are computed only between the few
nearest segments (at most 20) to keep the search under 4 ms. Toolkit picks (Jumper, Feed) then apply
`*il-snap-tolerance*` (0.01 in) through the VM's `il-jumper-target`, as in AutoCAD.

### W5.7 Undo

The store keeps `document` under `zundo` (as `app/src/design/store.ts` does). Each command commits once at
its end (`temporal.pause()` during a command, `resume()` + one `set` at the end), and the automatic update
(W5.8) runs inside that set. Selection, view and panels are not undoable.

### W5.8 Automatic ILUPDATE (`adapter/update.ts`)

After every committed command, in one pass:

1. **Copy rules**: build records `(id handle self kind)` for every `ILLUMENATE` entity and call the VM's
   `il-copies`; for each renumbered copy apply the drops `il-fix-copies` applies (a run's `line_key`,
   `configured_name`, `config_hash`, `part_number`, `server_in`; a PSU's `runs`; a fixed DMX `start`), set
   `self` to the new handle, and hand copied room and wire tags to the nearer owner.
2. **Rooms**: `il-assign-rooms` (W4.9) sets each run's `room` from the closed room outlines.
3. **Markers and tags**: regenerate the owned `TAG` entities (run tag at mid-path via `il-path-point`, feed and
   jumper markers, PSU load hint) on `E-LITE-FEED` and the run's layer, using the block definitions from
   `cadAssets`.
4. **Colors**: run color from the worst issue on it (`il-worst-severity`) once the debounced check returns:
   1 red error, 2 yellow warning, 3 green ok, 256 ByLayer when imported and unchanged.

### W5.9 DXF interchange (R2, `packages/cad-core/src/dxf`)

- **Write** (extends `packages/serializers/src/dxf/dxf.ts`): header `$ACADVER AC1032`, `$INSUNITS 1`,
  `$HANDSEED`; tables LTYPE, LAYER (from the document), STYLE, APPID with `ACAD` and `ILLUMENATE`; BLOCKS
  from `cadAssets`; ENTITIES with handle group 5, owner 330, layer 8, color 62, linetype 6; LWPOLYLINE
  vertices `10/20/42`, flag `70` (1 = closed); then XData `1001 ILLUMENATE` followed by alternating
  `1000 key`, `1000 value` pairs exactly as `il-xset` writes them (empty values skipped, values cut at 250
  characters). OBJECTS: the root dictionary gains `3 ILLUMENATE` / `350 <handle>` pointing at a DICTIONARY
  whose entries `3 SETTINGS` … `350 <xrecord>` are XRECORDs with `100 AcDbXrecord` and the JSON in `1`
  groups of at most 250 characters (`il-store`).
- **Read**: `dxf-parser` for geometry, plus a pass over the raw group codes for each entity's `1001
  ILLUMENATE` XData and for the `ILLUMENATE` dictionary in OBJECTS. Entities with `ILLUMENATE` XData become
  live; the rest become geometry or an underlay, as chosen.
- **Python**: `dxf_ingest.py` gets the same XData and dictionary read, so a toolkit DXF uploaded to Import
  Drawing builds its package from XData (`identity: "xdata"`) instead of the layer convention.

## W6. CI wiring

| Gate | Where | How |
| --- | --- | --- |
| G1 LISP hash | `tests/portal_unit/test_cad_web_parity.py::LispManifest` | Recompute the seven files' hashes and `il_version`; compare with `public/system_designer/lisp-manifest.json`. |
| G2a Rule parity | `packages/cad-lisp/src/parity.test.ts` + `test_cad_web_parity.py` | Vitest runs every case in `lisp-subset.json`, `check-cases.json` and `packages/valid` through the TS VM and writes `fixtures/cad/web/vm-results.json` during the test (not committed); the Python test runs the same cases through `mini_lisp.py` and compares with a committed golden file `fixtures/cad/web/expected-results.json`, which the Vitest run also compares with. Both must equal the golden file; regenerate it only on purpose (`npm run fixtures:lisp`). |
| G2b Collector parity | `test_cad_web_parity.py::Collectors` + `adapter/model.test.ts` | `fixtures/cad/web/*.dump.json` (entity dumps: handle, type, layer, layout, vertices, XData, dictionary) replayed into `mini_lisp` by a small `il-model`-equivalent harness, and the same dumps converted to `ilw/1` and run through `adapter.model`; models and package content hashes equal. |
| G3 Manifest | `tests/portal_unit/test_cad_commands_manifest.py` + `registry.test.ts` | Parse `(defun c:…` names from the LISP; check W4.2 rules both ways. |
| G4 XData | `test_cad_web_parity.py::XData` | Extract `*il-xdata-schema*` and the key register (W4.6) from the LISP sources; compare with `ilw.schema.json`'s XData key list and the migrator's version. |
| G5 Assets | `cad-core` test | Default layers equal `layers.json` `planLayers`. |
| G6 Round trip | `dxf/roundtrip.test.ts` (CI); `tools/cad_toolkit/test/run_tests.scr` (release) | CI: write DXF, read DXF, documents equal (modulo handles' order). Release: AutoCAD package hash equals the web's. |
| G7 Versions | `web_drawing.lisp_hash` + editor banner | Tab polls every 10 minutes and on focus; on mismatch, "A new version is available: save and reload". |
| Bundle | existing b2b-contracts step | Unchanged; now also covers `plan.js`, `lisp-manifest.json` and `ilw.schema.json`. |
| Licences | `scripts/check-licences.mjs` in the same step | Production dependencies must be MIT, ISC, BSD-2/3 or Apache-2.0. |

## W7. Work packages

### Phase 0 — Spikes and decisions

**W-0.1 — LISP VM spike (M, R1)**
- Depends: —
- Read first: `tools/cad_toolkit/test/mini_lisp.py` (all), `tests/portal_unit/test_cad_lisp.py`
  (`interpreter`, `plain`, `GoldenMath`, `Model`, `Controls`, `Sha256`), `lisp/il-model.lsp`,
  `fixtures/cad/check-cases.json`.
- Do: minimal TS interpreter in a scratch package (W5.1); run all golden cases; benchmark `il-check` +
  `il-package` for 20, 200 and 1,000 runs (generated from `job-20-runs.json`) in a worker in Chromium; try
  both integer representations. Write the results into a "Spike results" section of this document.
- Done when: results equal `mini_lisp.py` on every case, and N2 is met, or a named fallback is proposed and
  Kevin confirms it (Q1).

**W-0.2 — Renderer spike (M, R1)**
- Depends: —
- Read first: §6.7; `packages/drawing/src/view.ts`; `packages/serializers/src/svg.ts`.
- Do: a scratch page with pan, zoom, R-tree snap and polyline drawing over a 24×36 vector PDF, a scanned
  PDF and a 20,000-entity DXF (staff supply real backgrounds; nothing customer-identifying is committed).
- Done when: frame times and snap times measured against N1; Canvas 2D or WebGL underlay decided and
  recorded here.

**W-0.3 — AutoCAD reads a web-style DXF (S, R2 gate, needs a staff machine)**
- Depends: —
- Do: hand-write (script) a DXF per W5.9 with two runs, a room, a cabinet and a PSU; open in full AutoCAD,
  LT 2025 and Mac (Q9) with toolkit 0.5.0; run ILCHECK and ILQUOTE; AUDIT.
- Done when: the toolkit sees the runs and writes a package; results recorded here.

**W-0.4 — UX prototype (S, R1)**
- Do: clickable prototype of §8 (load plan, calibrate, style, draw run, send) with two dealers (one non-CAD,
  one LT) and an Applications Engineer.
- Done when: findings recorded here, and §8 updated.

### Phase 1 — Foundations

**W-1.1 — `packages/cad-lisp` (M, R1)**
- Depends: W-0.1
- Read first: W-0.1 results; W5.1; W4.4.
- Do: the full interpreter, `json-bridge`, `vfs`, native `il-sha256`, `sources.ts`, the worker and the
  `LispVm` API; the build script writing `lisp-manifest.json` into the bundle.
- Tests: builtin-by-builtin unit tests mirroring `mini_lisp` behaviour (integer wrap, `rtos`, `vl-sort`
  stability, `vl-catch-all-apply`); builtin table equality with Python; G1; G2a.
- Done when: G1 and G2a green in CI.

**W-1.2 — `ilw/1` schema, JSON Schema, Python validator, migrations (M, R1)**
- Depends: —
- Read first: `core-schemas/src/ilq.ts`, `system_design/ilq_schema.py`, `scripts/export-schema.mjs`.
- Do: W4.1 in Zod; export to `public/system_designer/schema/ilw.schema.json`; `system_design/ilw_schema.py`
  with the cross-reference rules and size limits; `migrate.ts`; the XData key register fixture (W4.6)
  generated from the LISP.
- Tests: valid and invalid fixtures in `fixtures/cad/web/` validated by Zod and Python with identical
  outcomes; G4.
- Done when: both validators agree on every fixture.

**W-1.3 — Geometry, units and R-tree (M, R1)**
- Depends: W-1.1 (for parity)
- Do: `geom/*`, `units/feet-inches.ts`, `index/rtree.ts` (wrap `rbush`).
- Tests: W5.4 parity (golden plus 500 random); W5.5 table; fillet and offset cases with known answers.
- Done when: parity within 1e-6 in.

**W-1.4 — Doctype, API, flag, access (M, R1)**
- Depends: W-1.2
- Read first: `system_design/access.py`, `system_design/cad_access.py`, `portal/site_flags.py`,
  `system_design/designs.py` (save, optimistic concurrency), `doctype/ill_system_design/*`,
  `doctype/ill_cad_import/*`.
- Do: W4.8 doctypes; `web_drawing` Link on `ilL-CAD-Import`; `site_flags.cad_web_enabled()`
  (`ill_cad_web`, default off; pilot and all-dealer rules as `cad_access.enabled_for`); W4.7 endpoints except
  the R2 DXF ones; soft lock; size limits; rate limit on save (30 per minute per user).
- Tests: `tests/portal_unit/test_web_drawing.py` with Frappe doubles: dealer A cannot read dealer B's
  drawing; flag off hides everything; stale `expected_rev` returns `STALE`; lock take-over; oversize refused;
  installed-site test: migrate twice.
- Done when: CI green; migrate twice cleanly.

**W-1.5 — Mount, route and empty editor (S, R1)**
- Depends: W-1.4
- Read first: `templates/pages/system_design.{py,html}`, `hooks.py` route rules, `app/src/mount.tsx`,
  `vite.config.ts`.
- Do: `plan_editor.{py,html}` (copy `system_design.py`: login redirect, schedule read check, flag check,
  CSRF token); route `/portal/schedules/<schedule>/plan` before the schedule route; second Vite entry
  `plan.js`; `app/src/plan/mount.tsx` and an empty `PlanEditor` that loads or creates the schedule's drawing,
  drafts to Dexie every 2 s, autosaves every 10 s, heartbeats the lock and shows read-only mode.
- Tests: template check script; page context test (unauthorized → not found; flag off → redirect);
  Playwright smoke.
- Done when: a pilot user opens `/portal/schedules/<s>/plan`, and it saves and reloads.

**W-1.6 — Command manifest (S, R1)**
- Depends: —
- Do: `tools/cad_toolkit/commands.json` with every IL command (`planned` with release and WP from §5.2) and
  the general commands of §5.1; G3 tests.
- Done when: G3 green.

**W-1.7 — Collector parity harness (M, R1)**
- Depends: W-1.1, W-1.2
- Read first: `il-commands.lsp` `il-model`, `il-run-from-entity`; W4.5.
- Do: entity-dump format; a `mini_lisp` harness that turns a dump into the model with the same logic as
  `il-model` (a LISP test file that reads dumps through `vfs`-style virtual `entget`/`il-xget` stubs, kept in
  `tools/cad_toolkit/test/`); `adapter/model.ts`; three dumps (straight runs; arcs, jumpers and spans across two
  layouts; controls and zones).
- Tests: G2b.
- Done when: models and package hashes equal for all three dumps.

**W-1.8 — Toolkit 0.6.0 refactors (S, R1)**
- Depends: W-1.1
- Read first: W4.9; `il-commands.lsp` `c:ILQUOTE`, `il-update-all`; README release checklist.
- Do: W4.9 items 1–5.
- Tests: all existing `test_cad_lisp.py` tests unchanged and green; new tests for `il-quote-package` and
  `il-assign-rooms`; `test_cad_bundle.py` with 0.6.0; `accoreconsole` run by staff before release.
- Done when: CI green; package hashes for the fixture jobs unchanged from 0.5.0.

### Phase 2 — Drafting core

**W-2.1 — Renderer, viewport, selection (L, R1)**
- Depends: W-0.2, W-1.3, W-1.5
- Do: `canvas/renderer.ts` (world→screen float64 affine, culling via R-tree, layer colors and linetypes from
  `layers.json`, lineweight toggle), overlay (grips, rubber band, snap glyphs, tooltip), click / Shift-click /
  window / crossing selection, Select All, Select Similar, zoom wheel/extents/window/previous, pan.
- Tests: hit-test unit tests; Playwright: selection modes; a performance benchmark against N1.
- Done when: N1 met on the W-0.2 backgrounds with 1,000 synthetic runs.

**W-2.2 — Command system, command line, toolbar (M, R1)**
- Depends: W-1.6
- Do: `commands/machine.ts` (event → prompt/preview state machine), registry keyed by manifest `web_tool`,
  `CommandLine.tsx` (aliases, history, Enter/Space repeat, Esc, clickable options), `Toolbar.tsx`
  (Draw, Modify, Lighting, Annotate, View), dynamic input tooltip.
- Tests: machine unit tests; registry vs manifest (G3).
- Done when: a no-op command can be run from the toolbar and the command line.

**W-2.3 — Draw commands (M, R1: PLINE, LINE, RECTANG; R2: ARC, CIRCLE)**
- Depends: W-2.2
- Do: PLINE with Line/Arc modes, Close, Undo (W5.4); LINE; RECTANG; ARC (3 forms); CIRCLE.
- Tests: prompt sequences produce exact vertices and bulges (table tests); Playwright: draw an L-shaped cove
  with two tangent arcs by typed input and by mouse.
- Done when: drawn geometry matches expected to 1e-9 in.

**W-2.4 — Modify commands (L, R1: MOVE, COPY, ROTATE, SCALE, ERASE, grips; R2: MIRROR, OFFSET, FILLET,
BREAK, JOIN, EXPLODE, MATCHPROP)**
- Depends: W-2.3
- Do: each command as a machine; grips (vertex, midpoint, arc bulge); SCALE with Reference; COPY runs the
  automatic update (W5.8) copy rules.
- Tests: per command; copying a run renumbers it and drops its line key (parity with `CopiedEntities` cases in
  `test_cad_lisp.py`).
- Done when: all listed commands pass.

**W-2.5 — Snaps, ortho, polar, grid, typed input (M, R1)**
- Depends: W-2.1, W-2.2
- Do: W5.6; F3/F7/F8/F9/F10; W5.5 parsing in the command line and tooltip.
- Tests: snap selection cases; parsing table; snap time under 4 ms on the benchmark.
- Done when: N1 snap budget met.

**W-2.6 — Undo/redo (S, R1)**
- Depends: W-2.2
- Do: W5.7.
- Tests: every command undoes in one step, including its automatic update.

**W-2.7 — Layers and properties panels (M, R1)**
- Depends: W-2.1
- Do: §5.4 L1–L3; properties for geometry, layer, color, linetype, and toolkit fields for our kinds (read and
  write through XData with validation).
- Tests: freeze/lock behaviour (frozen not drawn or snapped; locked not selectable); defaults equal
  `planLayers` (G5).

**W-2.8 — Measure, text, dimensions (M, R1: MEASURE; R2: TEXT, MTEXT, DIMLINEAR, DIMALIGNED)**
- Depends: W-2.3
- Tests: measured polyline length equals the VM's `il-path-length`.

### Phase 3 — Underlays, scale and sheets

**W-3.1 — PDF and image underlays (M, R1)**
- Depends: W-2.1, W-1.4 (`upload_underlay`)
- Do: upload, choose page, pdf.js tiles in `underlay.worker.ts`, opacity, clip rectangle, lock, show/hide;
  images likewise.
- Tests: tile cache unit tests; Playwright: upload, dim, clip.
- Done when: a 24×36 PDF pans at 60 fps.

**W-3.2 — DXF underlays (M, R2)**
- Depends: W-3.1
- Do: parse in the worker, `XREF|<layer>` read-only layer group, snapping to underlay geometry.

**W-3.3 — Calibrate and check dimension (S, R1)**
- Depends: W-3.1, W-2.5
- Do: ILSCALE on an underlay (two points + real length → transform) or on the drawing (SCALE Reference);
  sheet scale status and `check_dimension_in`; the status bar shows the scale status per sheet.
- Tests: a calibrated fixture measures a known length within 0.25%; package `sheets[].scale` and
  `drawing.scale_verified` match the toolkit rules (via the VM's `il-package-sheets`).

**W-3.4 — Sheets, title blocks, plot to PDF (L, R2)**
- Depends: W-3.3
- Do: §5.5 S1–S2 with `cadAssets` title blocks and `packages/serializers/src/pdf`; plot/no-plot layers.
- Tests: PDF snapshot tests; the plan PDF attaches to the import.

### Phase 4 — ilLumenate tools

**W-4.1 — Styles from the live catalog (M, R1)**
- Depends: W-1.1, W-1.5
- Read first: `system_design/cad_catalog.py`, `api.get_cad_catalog`, `c:ILSTYLE`, `il-new-tape-style`,
  `portal/presets.py` (drawing codes).
- Do: fetch the catalog per session, `vm.setCatalog`, the styles panel (presets, tape/neon templates and
  options, kit styles with their tape), STYLES in the dictionary, catalog-changed banner.
- Tests: style objects written equal what ILSTYLE writes for the same choices (fixture comparison).

**W-4.2 — Draw Run, Convert, Jumper, Feed (L, R1)**
- Depends: W-4.1, W-2.3, W-2.4
- Read first: `c:ILTAPE`, `il-make-run`, `il-over-max`, `c:ILCONVERT`, `c:ILJUMPER`, `c:ILFEED`,
  `il-jumper-span`, `il-run-pieces`.
- Do: §5.2 rows; live hint readout (W5.2); over-max choice writes `feed` or the `TAPE_RUN_TOO_LONG` override
  as `il-over-max` does; Convert joins chains with `il-chain-pieces` through the VM.
- Tests: for each command, the resulting XData equals the AutoCAD command's on the same input (fixtures
  from the LISP tests); Playwright: draw, add a jumper, flip the feed.

**W-4.3 — Rooms, cabinets, PSUs, connect, wires (L, R1)**
- Depends: W-4.2
- Read first: `c:ILROOM`, `c:ILCAB`, `c:ILPSU`, `c:ILCONNECT`, `c:ILWIRE`, `il-room-slug`.
- Do: §5.2 rows; symbols from `cadAssets` at the plot scale; wire lengths from the VM.
- Tests: XData parity as W-4.2; package `wire_paths` lengths equal the VM's.

**W-4.4 — Automatic update and live checks (M, R1)**
- Depends: W-4.2, W-1.8
- Do: W5.8; the checks panel (debounced `vm.check`, click to zoom, overrides with reason → OVERRIDES);
  "Check with portal" calls `preview_drawing_import` and shows server issues next to local ones.
- Tests: issue lists equal `il-check` on the collector fixtures; override flow.

**W-4.5 — Controls, zones, DMX (L, R2)**
- Depends: W-4.4
- Read first: `il-controls.lsp`, `c:ILCTRL`, `c:ILZONE`, `c:ILDMX`.
- Do: §5.2 rows; DMX patch panel and "place as table".
- Tests: parity with the `Controls` cases in `test_cad_lisp.py`.

**W-4.6 — Other lines and ILOUT tables (M, R2)**
- Depends: W-5.2
- Do: ILOTHER panel (OTHERS); ILOUT run schedule and cut list from the receipt as TEXT/INSERT tables.

### Phase 5 — Send to schedule

**W-5.1 — Send dialog (M, R1)**
- Depends: W-4.4, W-1.8
- Read first: `portal/drawing_import.py` (`preview_drawing_import`, `commit_drawing_import`,
  `choice_groups`, `previous_choices`), `public/js/portal/schedule/drawing_import.js`.
- Do: W5.3; reuse the import dialog's choice, warning and removal UI (extract it into a shared module that both
  the schedule page and the editor import, or wrap it if extraction is too invasive; record which); the
  optional `web_drawing` argument on preview and commit.
- Tests: `test_drawing_import.py` cases for `source_tool=web` and the `web_drawing` link; Playwright E2E (§9).
- Done when: the §9 E2E passes on a dev site.

**W-5.2 — Receipt write-back and re-send (M, R1)**
- Depends: W-5.1
- Do: `vm.applyReceipt` → XData; imported colors; re-send unchanged → zero changes; diff against the last
  import (`diff_drawing_imports`); locked or quoted schedule → new version prompt.
- Tests: re-send idempotency; removal confirmation.

**W-5.3 — Entry points and quote handoff (S, R1)**
- Depends: W-5.1
- Read first: `templates/pages/project.html`, `schedule.html`, `schedule/new.js`.
- Do: "Draw layout" on the schedule page and "New schedule from drawing → Draw in browser"; after commit,
  "Request a quote" with `get_quote_blockers` and "Open in System Designer".
- Tests: template check; Playwright.

**W-5.4 — Telemetry and versions (S, R1)**
- Depends: W-5.1
- Do: `ilL-Portal-Event` `cad_web_open`, `cad_web_send`; `ill_cad_min_versions.web`; the G7 banner.
- Tests: CAD Import Funnel shows `web` rows (`report/cad_import_funnel` test).

**W-5.5 — Plan PDF with the import (S, R2)**
- Depends: W-3.4, W-5.1

### Phase 6 — AutoCAD interchange (R2)

**W-6.1 — DXF export with XData and dictionary (M, R2)** · Depends: W-0.3, W-4.5 · Do: W5.9 write; clean
export (ILSTRIP) · Tests: G6 CI; AUDIT 0 errors on the release machine.

**W-6.2 — DXF import, client and server (M, R2)** · Depends: W-6.1 · Read first: `portal/dxf_ingest.py`,
`tests/portal_unit/test_dxf_ingest.py` · Do: W5.9 read; `import_dxf_to_web_drawing`; `dxf_ingest.py` XData
path · Tests: toolkit DXF → live runs; Python ingest builds a package equal to AutoCAD's for the fixture.

**W-6.3 — Round trip in the release check (S, R2, needs a staff machine)** · Do: extend `run_tests.scr` to
open a web DXF and compare ILQUOTE's hash with the web's · Done when: equal on the fixture jobs; recorded in
`test/report.txt`.

**W-6.4 — Open an AutoCAD import on the web (S, R2)** · Do: `create_web_drawing(from_import=…)` when the
import came from a DXF with XData; packages from `.ilq` files alone have no geometry and are refused with a
message.

**W-6.5 — DWG spike (S, R2, only if pilots ask, Q2)** · Do: APS Automation API DWG↔DXF from the server or
n8n with an ilLumenate Autodesk account; cost per job, latency, failure modes; recommendation recorded here.

### Phase 7 — Pilot and hardening

**W-7.1 — Pilot (M)** R1 after W-5.4 with two dealers and the AE team; R2 with a third dealer (full
AutoCAD) after Phase 6. Measure §9 pilot acceptance and §13 metrics.

**W-7.2 — Performance and accessibility (M)** 1,000-run benchmark in CI (fail on +25%); WCAG 2.2 AA pass on
panels; error reporting through the portal's existing client error logging.

**W-7.3 — Help, tour and dealer guide (S)** Help drawer from the manifest; first-run tour (§8); a
one-page dealer guide on `/portal/resources` next to the toolkit download; `package_bundle.py` ILHELP check.

**W-7.4 — GA review (S)** §10 Phase 7 GA criteria; switch `ill_cad_all_dealers` when Kevin approves.

## W8. Releases and rollout

| Release | Contents (WPs) | Size | Turn on |
| --- | --- | --- | --- |
| **R1** | W-0.1, 0.2, 0.4; W-1.1 to 1.8; W-2.1, 2.2, 2.3 (R1 part), 2.4 (R1 part), 2.5, 2.6, 2.7, 2.8 (MEASURE); W-3.1, 3.3; W-4.1 to 4.4; W-5.1 to 5.4; W-7.1 (R1 pilot) | 40–50 dev-weeks | Deploy, `bench migrate` twice, `ill_cad_web: true` with `ill_cad_pilot_customers`, `ill_cad_min_versions: {"autocad": "0.6.0", "web": "<R1 version>"}` once pilots have 0.6.0. |
| **R2** | W-0.3; the R2 parts of W-2.3, 2.4, 2.8; W-3.2, 3.4; W-4.5, 4.6; W-5.5; W-6.1 to 6.4 (6.5 if asked); W-7.1 (R2), 7.2, 7.3, 7.4 | 25–30 dev-weeks | Same flags; GA review, then `ill_cad_all_dealers`. |

Developer-weeks per group (central estimates; ranges come from the spikes):

| Group | R1 | R2 |
| --- | ---: | ---: |
| Phase 0 spikes and prototype | 4 | 0.5 |
| Phase 1 foundations (VM, schema, geometry, server, mount, manifest, parity, toolkit 0.6.0) | 11.5 | — |
| Phase 2 drafting core | 13 | 6 |
| Phase 3 underlays, scale, sheets | 3 | 4.5 |
| Phase 4 ilLumenate tools | 9.5 | 4.5 |
| Phase 5 send to schedule | 4.5 | 0.5 |
| Phase 6 AutoCAD interchange | — | 5 (6 with the DWG spike) |
| Phase 7 pilot and hardening | 2 | 5.5 |
| **Total** | **≈ 47.5** | **≈ 26.5** |

Two developers in parallel: one on W-1.1, 1.2, 1.3, 1.7, 1.8 and Phase 4–5 logic; one on W-1.4, 1.5 and
Phases 2–3 UI. Phase 4 needs both. With that split, R1 is about 5–6 calendar months.

Rollback: turn `ill_cad_web` off. Drawings stay stored; imports already committed are ordinary imports and
are not affected. Toolkit 0.6.0 is behaviour-compatible with 0.5.0 drawings and packages.

## W9. PR checklist

- [ ] WP ID and release in the title; "Read first" files read; plan deviations listed.
- [ ] `ruff check`, `ruff format`, `python -B tools/check_b2b_changes.py`, `tools/check_portal_templates.py`
      (if templates changed).
- [ ] `npm run lint`, `npm test`, `npm run typecheck`, `npm run build`, `npm run schema:export` in
      `tools/system_designer`; bundle committed.
- [ ] `python -B -m unittest discover -s tests/portal_unit` green, including G1–G4.
- [ ] LISP changed? Toolkit version bumped, bundle zip rebuilt, `accoreconsole` run noted.
- [ ] No price or cost key added anywhere; no `dangerouslySetInnerHTML`.
- [ ] This document updated if a contract (W4) or decision (§12) changed.

---

## Appendix A: Sources for third-party facts

- Autodesk APS Automation API (formerly Design Automation), AutoCAD engine runs AutoLISP and scripts in the
  cloud: [overview](https://aps.autodesk.com/en/docs/design-automation/v3/developers_guide/overview),
  [rename notice](https://aps.autodesk.com/blog/name-change-design-automation-api-now-automation-api),
  [headless AutoLISP limits (no vla-/vlax-)](https://aps.autodesk.com/blog/one-skill-one-lisp-one-automation-migrating-1998-autolisp-dialog-aps-automation).
- LibreDWG is GPLv3, and its WebAssembly builds are GPL:
  [LibreDWG](https://www.gnu.org/software/libredwg/),
  [libredwg-web](https://awesome.ecosyste.ms/projects/github.com%2Fmlightcad%2Flibredwg-web),
  [dwg2dxf-converter README](https://cdn.jsdelivr.net/npm/dwg2dxf-converter@1.0.4/README.md),
  [libdxfrw-web](https://www.jsdelivr.com/package/npm/@mlightcad/libdxfrw-web).
- `dxf-viewer` (three.js/WebGL, MIT): [GitHub](https://github.com/vagran/dxf-viewer),
  [package page](https://socket.dev/npm/package/dxf-viewer). Confirm each licence file before adding a
  dependency.
