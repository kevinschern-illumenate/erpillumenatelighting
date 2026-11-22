# Web Drawing Editor (browser CAD, synced to the AutoCAD toolkit): PDR and Implementation Plan

2026-11-22 · branch `claude/browser-autocad-interface-plan-x3cq28` · status: **for review, nothing built**

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

**Size.** About 20–30 weeks for one full-stack developer across Phases 0–7, or 12–16 weeks for a
"tape runs over a PDF, to a quote" first release (§10.9). Phase 0 has four spikes that can stop or reshape
the plan before most of the money is spent.

**Decisions I need from you** are in §12. The ones that matter most are the sync approach (§6.1), DWG
(§6.15) and the first-release cut (§10.9).

---

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
- **Hashing**: `il-package-content` text is produced by the LISP, and its SHA-256 is computed with WebCrypto
  (fast). A parity test asserts it equals `il-sha256` on the fixtures.
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
plan's convention).

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
and quote". About **12–16 weeks**. Controls, DXF interchange, sheets and plotting follow.

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

## 12. Decisions needed from you

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | **Sync approach**: run the toolkit's pure LISP in the browser (option B) with a command manifest for the interactive layer? | **Yes**, subject to spike 0.1. |
| Q2 | **DWG** in v1? | **No.** DXF and PDF in v1; APS Automation spike in Phase 6 if pilots need DWG. |
| Q3 | **Audience**: dealers without AutoCAD first, or replace AutoCAD for staff too? | Both can use it; target non-CAD dealers and AEs first. Keep the AutoCAD toolkit supported. |
| Q4 | **Round trip** to AutoCAD (DXF with XData) required for GA? | **Yes** (Phase 6); it is what makes the two front ends one product. |
| Q5 | **First release**: the full plan (20–30 weeks) or the faster cut (§10.9, 12–16 weeks)? | **Faster cut**, then Phases 4.5–4.6, 6 and the rest of 2–3. |
| Q6 | **Where it lives**: inside the System Designer workspace and bundle (lazy entry), replacing the designer's planned plan view? | **Yes.** |
| Q7 | **Multi-user**: single editor with lock, or live co-editing? | **Lock** in v1. |
| Q8 | **Tablets**: view only, or editing? | View and light edits later; desktop first. |
| Q9 | Who runs the **AutoCAD release checks** (spike 0.3, G6) on real installs? | A staff Windows machine with full AutoCAD and LT; Mac if a dealer uses it. |

---

## 13. Success metrics

- Share of CAD imports with `source_tool = web` at 90 days after GA (target: 40% of drawing imports).
- Time from "plan received" to "schedule built" for a 20-run job (target: under 45 minutes for a trained
  dealer).
- CAD BOM Match for web-drawn jobs ≥ 98% (same as the toolkit target).
- Quote requests blocked by unverified scale that later need AE correction: under 5%.
- Zero G1–G4 drift incidents reaching production.

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
