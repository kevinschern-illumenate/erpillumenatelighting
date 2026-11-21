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

| 6. Field wire | Pull the most commonly stocked wires and create the data: 33 sourced wires in `tools/seed_imports/field_wire_common.csv`. |
| 7. Controls in v1 | Yes: controllers, decoders and zones in CAD, the package, the import and the design seed; controller import with Pharos and Advatek data. |
| 9. Earlier dynamic blocks | Not reused; the generated blocks keep all their functions. |
| Pushes | Not now; future pushes go to `staging`. |

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

**0.5.0** (WP 1.1, 1.3, 1.4, 1.12): packages carry `source` (`autocad`, toolkit version, platform, `ilq`)
and `sheets` (one per layout with runs, CadId slug of the layout name, scale `verified` after ILSCALE else
`declared`); runs carry `sheet` and `identity: "xdata"`, rooms their `sheet`. The content hash ignores
source, sheets and layouts, so it matches 0.4.x for an unchanged drawing. A catalog's optional
`settings.min_toolkit_version` newer than the toolkit prints a download warning on load and adds the
ILCHECK warning `TOOLKIT_OUTDATED`. The bundle zip is reproducible and committed as
`public/cad_toolkit/ilLumenate-cad-toolkit-0.5.0.zip` (CI checks its name and version match `*il-version*`).

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

### Field wire data (question 6)

`tools/seed_imports/field_wire_common.py` writes `field_wire_common.csv` for the existing Desk field wire
import (`system_design.wire_import.import_field_wire`, dry run first): CL3R and CL3P 18-12 AWG, 18/4,
16/4 and 18/5 (RGB, RGBW) and 18/3 (pixel) CL3R, landscape direct burial 16-8 AWG, NM-B 14/2 and 12/2,
THHN/THWN #14-#10 raceway sets, MC-AP 12/2, Belden 9841, 9842 and 82841 (DMX), Cat 6 CMR and CMP, 0-10 V
dimming (CL2 and plenum), 18/2 shielded control, and Lutron QS cable (plain and plenum). Every row cites
its manufacturer or distributor sheet; conflicting values use the conservative one; resistances are NEC
Chapter 9 Table 8 or the measured DCR. Rows import as unverified and without prices: each passes the
readiness rules except `item_price` (test `test_field_wire_common.py`). Cat 6 is 23 AWG; the spec form's
nearest size, 24 AWG, is recorded and noted.

### Controls in v1 (question 7)

- **AutoCAD**: `ILCTRL` places a controller or decoder from the catalog (tag, cabinet, room, DMX universe
  and start address or auto, the control that sends its signal); `ILZONE` groups runs under a control
  output in a protocol (DMX512, CRMX, 0-10 V, DALI-2, Lutron QS/EcoSystem, phase, none); `ILDMX` previews
  the DMX patch (fixed addresses kept, auto ones filled) and can draw it as a table; `ILWIRE` Data cables
  connect controls. ILCHECK adds `CONTROL_UNKNOWN`, `CONTROL_NO_SIGNAL`, `DMX_ADDRESS_OVERLAP`,
  `DMX_UNIVERSE_FULL`, `PROTOCOL_MISMATCH`, `ZONE_NO_CONTROL`, `RUN_IN_TWO_ZONES`, `DATA_TOO_LONG`
  (`lisp/il-controls.lsp`, tested in CI).
- **Package**: optional `controls` and `zones` sections in `ilq/2` (TypeScript, JSON Schema, Python,
  fixtures).
- **Import**: each control becomes an accessory line for its Item (checked against the active controller
  specs; updated in place on re-import, removed only when confirmed); a zone naming a port the control
  does not have is an error. The receipt returns each control's line key.
- **System Designer**: a new design gets the drawn controls tied to their schedule lines (so the power
  board's schedule sync keeps them), their DMX addresses and signal sources, and the zones with their runs.
  Power, outputs, links and the final DMX patch stay the designer's.
- **Controller data**: `system_design.controller_import.import_controllers` (Desk, dry run first) creates
  Items, `ilL-Spec-Controller` records with protocols and ports, and the sACN and Art-Net protocol records
  the site lacks. `tools/seed_imports/controls_common.csv`: Pharos LPC 1, LPC 2, LPC X 10, Advatek PixLite
  A4-S Mk3 and PixLite 16 Mk2, sourced; terminal sizes (and the PixLite 16 input range) are left for
  engineering, so readiness lists them.

### Phase 7 — Later (not built)

206 brand mode, metric (D11), optional online mode for full AutoCAD on Windows.

## Runs-to-Quote implementation plan, Phase 1 (2026-11-21)

From the PDR "Runs-to-Quote Drawing Tools (AutoCAD + Bluebeam)" and its implementation plan. Live check on
2026-11-21: production does not have this code yet (no `ilL-CAD-Import`, no `cad_run_id`); `main` and
`staging` do. Phase 0 (deploy, real installs, live data, dealer survey) is people work.

| WP | Built | Where |
| --- | --- | --- |
| 1.1 | `ilq/2` gains optional `source`, `sheets` (scale status per sheet), `counts`, `runs[].sheet`/`identity`, `rooms[].sheet`; Python derives `source` for older packages. The import records source tool, version, platform and input. | `core-schemas/src/ilq.ts`, `ilq_schema.py`, `drawing_import._store`, `ilL-CAD-Import` |
| 1.2 | Drawing styles: `cad_code`/`cad_enabled` on presets, `set_preset_cad`, `find_by_cad_code`, catalog style `code`, DXF layers `ILM-STYLE-<code>`, the "Drawing styles" panel, the starter-preset seed script; Desk saves validate codes too. | `portal/presets.py`, `cad_catalog.py`, `dxf_ingest.py`, `schedule/presets.js`, `tools/seed_imports/cad_starter_presets.py` |
| 1.3 | Scale status (`verified`, `declared`, `unverified`) per sheet and per import; preview warnings; an unverified scale blocks `quotes.request_quote` until an Applications Engineer confirms it (`confirm_drawing_scale`, button on the import record). DXF uploads are `declared`, no longer `scale_verified`. | `drawing_import.scale_summary`, `quote_blockers`, `quotes.py`, `ill_cad_import.js` |
| 1.4 | `ill_cad_min_versions` (site config, JSON object per tool) blocks older packages; the CAD catalog publishes `settings.min_toolkit_version`; toolkit 0.5.0 warns (`TOOLKIT_OUTDATED`). | `site_flags.cad_min_versions`, `drawing_import.version_check`, `cad_catalog.py`, `il-catalog.lsp` |
| 1.5 | Telemetry `cad_preview`, `cad_preview_failed`, richer `cad_import`; report **CAD Import Funnel**; CAD BOM Match has a "Drawing tool" filter and column. | `drawing_import.py`, `report/cad_import_funnel`, `report/cad_bom_match` |
| 1.6 | "New schedule from drawing" on the project page and the new-schedule form; the schedule opens Import Drawing (`?import=1`). | `project.html`, `schedule.html`, `schedule/new.js`, `schedule/drawing_import.js` |
| 1.7 | Desk dialog accepts DXF, answers choices, sends layer styles and Types and the plan PDF; imports by staff into a dealer's schedule are recorded `on_behalf`. | `desk_drawing_import.js`, `drawing_import.on_behalf_of` |
| 1.8 | Choice groups with allowed values (one answer fills every run), remembered answers (`choices_json`), DXF layer pickers (`options.presets`/`types`), layer report from DXF ingest. | `drawing_import.choice_groups`, `option_values`, `previous_choices`, `dxf_ingest.layer_report` |
| 1.9 | Server-side checks with the toolkit's codes (`BEND_RADIUS`, `PROFILE_NOT_CURVE_CAPABLE`, `TAPE_WIDER_THAN_PROFILE`, `TEMPLATE_DISCONTINUED`, `PSU_OVERLOAD`, DMX and control rules) run for every front end; overrides honoured; parity with `il-check` tested through `mini_lisp`. | `system_design/drawing_checks.py`, `drawing_import.server_issues`, `fixtures/cad/check-cases.json` |
| 1.10 | Previous imports listed in the dialog with tool and scale; `diff_drawing_imports`; staff `replay_drawing_import`; quote requests link the import (`ilL-Quote-Request.cad_import`). | `drawing_import.py`, `quotes.py`, `ill_cad_import.js` |
| 1.11 | After an import the dialog offers "Request a quote", disabled with the reasons from `get_quote_blockers`. | `schedule/drawing_import.js` |
| 1.12 | Toolkit 0.5.0 (`source`, `sheets`, version warning), reproducible bundle committed in `public/cad_toolkit/`, "Drawing tools" section on `/portal/resources`. | `tools/cad_toolkit`, `templates/pages/resources.*` |

Turning Phase 1 on, after the steps below: `bench migrate` runs `patches.backfill_cad_import_source`;
confirm `ill_portal_presets` is on (styles and `ILM-STYLE-` layers need it); set
`ill_cad_min_versions` to `{"autocad": "0.5.0"}` once pilots have 0.5.0.

Known cost: preview and commit build the user's CAD catalog once each for the server checks; watch the
preview time on large catalogs and cache by snapshot hash if needed.

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
fixes (`LED-HD-SW`, three drivers; run the field wire and controller imports, then add their prices and
have engineering verify them; read-only here) · 3.4 Kevin reviews
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
