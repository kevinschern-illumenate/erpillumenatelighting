# Draw-to-Quote CAD Toolkit: Implementation Status

2026-11-20 · branch `claude/admiring-mayer-31nsbk` · plan: "Draw-to-Quote CAD Toolkit: PRD Review and
Implementation Plan" (same date).

The toolkit is a thin AutoCAD front end to the fixture schedule and the System Designer. AutoCAD draws
geometry; the portal's configurators build every run; the System Designer sizes supplies and wire; the
schedule becomes the quote. Everything ships behind `ill_cad_import` (default **off**).

## Decisions recorded (Phase 0.5)

| Question | Answer |
| --- | --- |
| 1. Product shape | Front end to the System Designer and schedule (decided in the plan). |
| 2. Who draws first | Applications engineering, then pilot dealers by customer. |
| 3. AutoCAD versions | Full AutoCAD on Windows plus LT 2024+ and Mac: the core uses no ActiveX, reactors or DCL. |
| 4. Run styles | A saved configuration preset, or a tape/neon template with options picked from the CAD catalog. No loose SKUs. |
| 5. Extrusion runs | Per style: a Linear Fixture style makes a linear build; an Extrusion Kit style makes a kit line plus a tape build. |
| 8. Distribution | Staff first; dealers through `ill_cad_pilot_customers` (or the designer's pilot list); `ill_cad_all_dealers` opens it to every catalog user. |
| 10. Branch | This work branch, for a PR to `main` (the designer lives there). |

Still open for Kevin: 6 (which field wire Items before the pilot; live has one, unverified), 7 (controls in v1;
treated as later), 9 (whether the earlier dynamic-block system has geometry worth reusing).

## What was built

### Phase 1 — ERP contracts

| # | Done | Where |
| --- | --- | --- |
| 1.1 | `min_bend_radius_mm` on `ilL-Spec-LED Tape`, `is_curve_capable` on `ilL-Spec-Profile` (doctype JSON); readiness note when the bend radius is missing (informational, guarded read). The CAD catalog falls back to half the template's `minimum_side_bend_diameter_mm`. | doctype JSON, `system_design/readiness.py` |
| 1.2 | `cad_run_id` on schedule lines. Versions keep it (same drawing); line copies drop it (a copy is not that run). | doctype JSON, `portal/line_copy.py` |
| 1.3 | `cad-catalog/1` projection: tape/neon templates with options and every (spec, offering) variant in inches, linear and kit templates, profiles with outlines, drivers/controllers/wire from the designer snapshot, the user's presets as run styles. `forbidden_keys` refuses price, MSRP, adders, cost and rank. | `system_design/cad_catalog.py` |
| 1.4 | `system_design.api.get_cad_catalog` (token or session) and `download_cad_catalog` (file download linked from the import dialog). Access: `system_design/cad_access.py`. | `system_design/api.py` |
| 1.5 | `ilq/2` in Zod with the exported JSON Schema (`public/system_designer/schema/ilq.schema.json`) and the Python validator with the same cross-reference rules. | `packages/core-schemas/src/ilq.ts`, `system_design/ilq_schema.py` |
| 1.6 | Plan layers (`E-LITE-TAPE`, `E-LITE-EXTR`, `E-LITE-FEED`, `E-LITE-DATA`, `E-POWR-CABN`, `E-POWR-WIRE-LINE`, `E-ANNO-ROOM`, `E-ANNO-ISSU` no-plot) as `planLayers` in `layers.json` (the riser output is unchanged); the DWT layer script. | `packages/data/src/layers.json`, `tools/cad_toolkit/build/layers.py` |
| 1.7 | Golden cases for cut snap, max run and equal split, PSU load and path length; the Python reference is tested against `whole_increments` and `_compute_run_split` themselves. | `tools/system_designer/fixtures/cad/lisp-subset.json`, `tools/cad_toolkit/reference/cad_subset.py` |

### Phase 2 — Portal drawing import

`portal/drawing_import.py`:

- **Preview** plans every run through `portal.configuration.calculate` (tape, neon, linear) or
  `validate_kit_configuration` (kits: one kit per profile stick covering the run, plus the tape build).
  Each run is `ok`, `needs_choice` (an option the style leaves open, answered in the dialog) or `error`
  (template no longer offered, configurator refusal). Drawn against built length, splits and watts are
  shown; prices are stripped on the way in and out.
- **Commit** plans again, refuses errors, open choices, toolkit ILCHECK errors and unconfirmed removals,
  then saves every build through `portal.configuration.save` / `portal.kit_configuration.save` (receipts
  make retries idempotent), other-manufacturer lines through `line_add.append_line`, all in one
  `atomic_build`. Lines carry `cad_run_id`; kits are `<run id>.K`; other lines `OTHER.<type>`.
- **Re-import** matches by `cad_run_id` (or the receipt's `erp.line_key`), skips unchanged runs, updates
  changed ones in place (line keys kept), and removes lines whose runs left the drawing only when confirmed.
- **Locked or quoted** schedules import into a new version on request (`create_new_version`, lines keep `line_key`).
- **Receipt** (`ilq-receipt/1`): per run line key, configured record, `config_hash`, part number, built
  length and cut list; downloadable again from the dialog for `ILRECEIPT`.
- **Record**: `ilL-CAD-Import` keeps the package, receipt, SHA-256, counts and the design site
  (`cad-site/1`); `ilL-Portal-Event` `system_design:cad_import`.
- **UI**: "Import Drawing" on the schedule page (portal) and a CAD › Import Drawing button on the Desk form.
- **System Designer**: `open_design` returns `cad_site`; a new design starts from the drawing's rooms
  (environment, level), cabinets (measured feed) and measured home runs (`homeRunProvenance: measured`).
  The designer still adds route slack and wire waste. (Deviation: the plan said the import creates the
  design; it seeds it instead, because a design needs the terms accepted by a person and the designer's
  own project model. An existing design is left untouched.)

### Phase 3 — AutoCAD toolkit (`tools/cad_toolkit`)

See `tools/cad_toolkit/README.md`. Commands: ILSETUP, ILCATALOG, ILSTYLE, ILTAPE, ILCONVERT, ILJUMPER,
ILFEED, ILSCALE, ILROOM, ILCAB, ILPSU, ILCONNECT, ILWIRE, ILOTHER, ILOVERRIDE, ILUPDATE, ILCHECK, ILQUOTE,
ILRECEIPT, ILOUT, ILRISER, ILSTRIP, ILVERSION, ILHELP. Blocks and layers are generated from the riser's
symbols, layer standard and title blocks (`npm run cad:export`). CI runs the pure LISP (JSON, hint math,
SHA-256, catalog, model, ILCHECK, `ilq/2` writer, receipt) through a small AutoLISP interpreter against
the golden cases and validates the written package with the portal's validator. `accoreconsole` runner,
bundle packager and the Phase 0.2 spike (`spike/il-spike.lsp`, command ILSPIKE) are included.

### Phase 4 — Round trip and outputs

ILRISER attaches the designer's riser (saved from its DXF as DWG); ILOUT draws the run schedule and cut
list from the receipt (server values); ILSTRIP saves an architect copy without ilLumenate data; ILCHECK
warns when the drawing changed since its last import; the plotted plan PDF can travel with the import
and is added to the current design as a `Plan PDF` deliverable. PSU, wire and circuit schedules and the
BOM stay designer outputs; labels follow the Dymo label plan.

### Phase 5 — Pilot measurement

Report **CAD BOM Match**: per Sales Order from a schedule, order lines against Delivery Note lines by item
and quantity, with "only drawing imports" to compare toolkit jobs with the rest (target 98%).

### Phase 6 — DXF ingest

`portal/dxf_ingest.py`: an ASCII DXF on `ILM-TAPE-<template>` / `ILM-LINEAR-<template>` layers, rooms on
`ILM-ROOM-<name>`, cabinets as `ILM-CAB` blocks, `$INSUNITS` required, becomes an `ilq/2` package for the
same import (upload a `.dxf` in the dialog). Pure Python, no ezdxf. Dealer checklist:
`public/cad_toolkit/ilLumenate-DXF-drafting-checklist.pdf` (source `tools/cad_toolkit/build/dxf_checklist.md`).

### Phase 7 — Later (not built)

Controls and pixel addressing (4 controller specs, none for Pharos/Advatek), 206 brand mode, metric (D11),
optional online mode for full AutoCAD on Windows.

## Phase 0 live data (read-only, 2026-11-20)

| Data | Live | Effect |
| --- | --- | --- |
| Tape specs with single and double feed max run | 333 of 334 | Ready; `LED-HD-SW` lacks W/ft and max runs. |
| Tape specs with voltage-drop run (what the configurator splits on) | 333 | Hints match the configurator. |
| Tape specs with tape width | 20 of 334 | "Tape wider than profile" check runs only where set. |
| Templates with a side-bend diameter | 10 of 26 active | Bend check limited until `min_bend_radius_mm` is entered. |
| Profiles | 140, all 2000 mm stock | Kit quantity per stick works. |
| Profiles with `cross_section_json` | 6 of 140 | Outlines only for those six. |
| Active tape offerings | 329 | Variant W/ft and cut overrides included. |
| Configuration presets | **0** | Linear and kit runs need presets: create the pilot's presets in the portal configurator. |
| Drivers / controllers / wire specs | 15 / 4 / 1 (`FML-2C-BK`, unverified) | Questions 6 and 7. |
| System Designer | `enabled = 0`, 0 designs, review gate off | Phase 0.3 E2E on staging still to do. |
| Fixture schedules | 156 | |

## Turning it on

1. Deploy and `bench migrate` (new fields, `ilL-CAD-Import`, the report).
2. Site config: `ill_cad_import: true`; pilot customers in `ill_cad_pilot_customers` (JSON list) or the
   designer's Settings pilot list; `ill_cad_all_dealers: true` later.
3. Create the pilot's run presets in the configurator (live has none).
4. Build the bundle (`python -m tools.cad_toolkit.package_bundle --out dist`) and publish it.
5. Fill the capability matrix with ILSPIKE results on full AutoCAD, LT 2025 and Mac (Phase 0.2) and run
   `tools/cad_toolkit/test/run_tests.bat` in `accoreconsole` (Phase 3.10).

## Needs people, not code

0.1 dealer version survey · 0.2 spike runs on real installs · 0.3 designer E2E on staging · 0.4 live data
fixes (`LED-HD-SW`, three drivers, verify the wire, field wire Items; read-only here) · 3.4 Kevin reviews
each block's look · 5.1–5.3 pilot jobs, tutorial, review gate on a DMX job.

## Capability matrix (fill from ILSPIKE)

| Capability | Full (Win) | LT 2024/25 | Mac |
| --- | --- | --- | --- |
| entmake/entmod, XData, dictionaries | | | |
| `command` PLINE with pause | | | |
| getfiled / file write | | | |
| vl- string and list functions | | | |
| logand/lsh/boole (SHA-256) | | | |
| `.bundle` autoload | | | |
| ActiveX, reactors, DCL (not used) | | | |
