# ilLumenate System Designer — Product Plan

**Working name:** ilLumenate System Designer (dealer-facing project documentation and support tool)
**Status:** Proposal for review · Written 2026-10-06
**Inputs investigated:**

1. This repository: the ERPNext app and Dealer Portal (`illumenate_lighting/`).
2. `kevinschern-illumenate/riser-diagram-generator` v1.2.0 (React + TypeScript; inspected at its `main` HEAD).
3. The single-file **LED Tape System Visualizer** (Three.js r128; 3D model, system diagram, training visuals, install guide), supplied in chat.

This plan combines the three into one product that runs inside the Dealer Portal and takes every product fact from ERPNext. Section 0 is the summary; sections 1–3 are the investigation; 4–14 define the product; 15–21 cover architecture, delivery and risk; the appendices hold the field mappings.

---

## Contents

0. [Executive summary](#0-executive-summary)
1. [What exists today](#1-what-exists-today)
2. [The core problem: three copies of the product data](#2-the-core-problem-three-copies-of-the-product-data)
3. [Gap analysis: what ERPNext must hold for the designer to work](#3-gap-analysis-what-erpnext-must-hold-for-the-designer-to-work)
4. [Product vision, users and jobs](#4-product-vision-users-and-jobs)
5. [Product principles](#5-product-principles)
6. [The end-to-end workflow](#6-the-end-to-end-workflow)
7. [Module 1 — Project and schedule intake](#7-module-1--project-and-schedule-intake)
8. [Module 2 — Site model (spaces, locations, distances)](#8-module-2--site-model-spaces-locations-distances)
9. [Module 3 — Run builder](#9-module-3--run-builder)
10. [Module 4 — Power and control assignment](#10-module-4--power-and-control-assignment)
11. [Module 5 — Engineering checks and recommendations](#11-module-5--engineering-checks-and-recommendations)
12. [Module 6 — Outputs: riser, presentation diagram, plan view, 3D](#12-module-6--outputs-riser-presentation-diagram-plan-view-3d)
13. [Module 7 — Install guides, training and support visuals](#13-module-7--install-guides-training-and-support-visuals)
14. [Module 8 — Documentation package, review, sharing and commerce](#14-module-8--documentation-package-review-sharing-and-commerce)
15. [Architecture](#15-architecture)
16. [Data model in ERPNext](#16-data-model-in-erpnext)
17. [API surface](#17-api-surface)
18. [Consolidating the calculation engines](#18-consolidating-the-calculation-engines)
19. [What happens to each proof of concept](#19-what-happens-to-each-proof-of-concept)
20. [Phased roadmap](#20-phased-roadmap)
21. [Testing, quality and acceptance](#21-testing-quality-and-acceptance)
22. [Risks, liability and open decisions](#22-risks-liability-and-open-decisions)
23. [Success metrics](#23-success-metrics)
24. [Appendices](#24-appendices)

---

## 0. Executive summary

**The opportunity.** You already have the three hard parts, built separately:

| Asset | What it does well | What holds it back |
|---|---|---|
| **ERPNext Dealer Portal** | Projects, fixture schedules, configured builds (segments, runs, run watts, cut lengths, leader/jumper cables), an exact power-supply allocator, driver eligibility, spec submittals, document requests with drawing review, dealer permissions, quotes and Sales Orders. | No system-level view. Power is planned per build, never across a site. No riser, no wiring, no visuals. |
| **Riser Diagram Generator** | A pure, tested electrical engine (graph, loads, CV/CC checks, voltage drop, wire selection, DMX, BOM, 39 validation codes); a paper-inch drawing model with column layout, cable routing and pagination; vector PDF with layers, native DXF (AutoCAD AUDIT 0 errors) and SVG. | Local-only (IndexedDB), its own product library with EXAMPLE data, and an ERP pull that expects a JSON blob (`custom_riser_specs`) that ERPNext does not have. |
| **LED Tape System Visualizer** | Beautiful, on-brand 3D scenes (cove, under-cabinet, toe-kick, shelf, niche), lit renders, exploded and cross-section views, a flat system diagram, 40+ training visuals, a parameterized install guide with video and printable output. | Everything is hard-coded (`ZONES`, `PROFILES`, `EXAMPLE`, `JOB`, `CAD_SH01`). One 6,000-line file on Three.js r128. No persistence. |

**The product.** One dealer-facing tool, opened from a fixture schedule in the portal, that:

1. Pulls the schedule (by number or picker) and expands every line into the physical runs ERPNext already computed.
2. Lets the dealer place power supplies, cabinets, dimmers and controllers, and link runs to supply outputs (drag-and-drop or auto-assign).
3. Checks everything as they go: supply load against the 80% rule and per-output limits, maximum run length, voltage drop on every home run, wire gauge and cable type for the install environment, breaker load, Class 2 limits, dimmer compatibility, DMX addressing.
4. Produces four views of the same design: an **engineering riser** (PDF/DXF), a **presentation diagram** for homeowners and designers, a **plan view** over the dealer's floor plan, and a **3D project view** with supply locations and wire routes.
5. Generates **install guides**, **labels** and a **documentation package**, and sends the design to ilLumenate for **engineering review** using the drawing-review records that already exist.
6. Writes the supplies, controllers, wire and accessories it added back to the schedule as lines, so the quote and Sales Order match the design.

**The rule that makes it work:** ERPNext is the only place product data lives. The designer reads a versioned, permission-scoped **Design Catalog** generated from the spec doctypes. Nothing in the designer is typed in twice.

**Recommended architecture.** A React + TypeScript app built with Vite, committed as a bundle inside this app (the same pattern as the Product Finder, because Frappe Cloud runs `bench build`, not Vite), mounted at `/portal/schedules/<schedule>/design`. The riser engine, drawing model and serializers move in as packages. The visualizer is rebuilt as a modular Three.js scene package. Designs are saved in a new `ilL-System-Design` doctype linked to the schedule version.

**Delivery.** Eight phases (section 20). The first dealer-visible release (Phase 3) gives intake, power assignment, live checks and the engineering riser on real ERP data. Presentation diagram, 3D and install guides follow. Phase 0 is mostly ERP data work: the spec doctypes need roughly 30 electrical fields the riser engine requires (section 3).

---

## 1. What exists today

### 1.1 ERPNext app and Dealer Portal (this repository)

**Commercial structure**

- `ilL-Project` → `ilL-Project-Fixture-Schedule` (versioned: `version`, `version_parent`, `is_locked`, `locked_by`) → `ilL-Child-Fixture-Schedule-Line`.
- Each line has `line_id` (Fixture Type), `qty`, `location`, `product_type`, links to the template and the configured record (`configured_fixture`, `configured_tape_neon`, `configured_led_sheet`, `configured_group`), third-party fields for "Other" manufacturers (`manufacturer_name`, `fixture_model_number`, `driver_model_number`, `dimming_protocol`, `input_voltage` as text), and power-supply linkage (`power_supply_for_line`, `power_supply_qty_per_build`).
- Portal routes in `hooks.py`: `/portal/projects`, `/portal/schedules/<schedule>`, `/portal/configure*`, `/portal/drawings`, `/portal/quotes`, `/portal/orders`, `/portal/resources`, `/portal/product-finder`.
- Schedule → quote → Sales Order (`create_schedule_sales_order`, `quote_from_schedule.py`), dealer pricing (`get_schedule_dealer_pricing`), versioning (`create_schedule_version`).

**Configured builds carry the electrical facts the designer needs**

- `ilL-Configured-Fixture` (linear): `runs` child table (`run_index`, `segment_index`, `run_len_mm`, `run_watts`, `leader_item`, `leader_len_mm`), `segments` (profile/lens/tape cut lengths, end caps, start leader, end jumper), `max_run_ft_by_watts`, `max_run_ft_by_voltage_drop`, `max_run_ft_effective`, `total_watts`, `power_feed_type`, `feed_direction_start/end`, `environment_rating`, `tape_offering`, plus canonical JSON snapshots: `build_snapshot_json`, `component_manifest_json`, `power_plan_json`, `cable_manifest_json`.
- `ilL-Configured-Tape-Neon` (tape, COB, neon): `segments` with start/end feed types, lead lengths, jumpers and watts per segment, `cut_increment_mm`, `is_free_cutting`, `watts_per_foot`, `power_plan_json`.
- `linear_build.cable_manifest()` already lists every physical feed, additional feed, jumper and end leader with its Item and length. This is the starting point for wiring.

**Power planning**

- `api/power_planner.py` `plan_power(circuits, candidates)`: exact bounded search (≤12 circuits, ≤32 candidate drivers). One circuit per output, outputs never paralleled, honours total and per-output capacity × `usable_load_factor`, minimizes supply count, then cost, then priority. Returns `drivers` and per-output `allocations` (`supply`, `output`, `run_key`, `watts`).
- `tape_neon_power.connected_runs()` merges jumper-connected runs and rejects ones over `max_run_ft_effective`.
- `driver_catalog.candidates()` resolves eligible drivers per template from `ilL-Rel-Driver-Eligibility` filtered by tape voltage and protocol; `independent_outputs()` refuses to treat color channels as independent feeds.
- `power_supply_lines.py` turns selected supplies into ACCESSORY schedule lines under their fixture line, quantity × builds.
- Engine rule today: `max_run_ft_by_watts = 85 W / W·ft⁻¹` (`configurator_engine.py`), capped by the tape spec's static `voltage_drop_max_run_length_ft`. `docs/MVP_CONSTRAINTS.md` notes the voltage-drop table is not implemented.

**Product specification doctypes (the catalog)**

- `ilL-Spec-LED Tape`: `input_voltage`, `watts_per_foot`, `voltage_drop_max_run_length_ft`, `input_protocol`, `supported_dimming_protocols`, `lumens_per_foot`, `led_pitch_mm`, `cut_increment_mm`, `is_free_cutting`, `leader_cable_item`.
- `ilL-Rel-Tape Offering`: CCT/CRI/output combinations with `watts_per_ft_override`, `cut_increment_mm_override`.
- `ilL-Spec-Driver`: input voltage range and type, `voltage_output`, `outputs_count`, `independent_outputs_count`, `output_type`, `output_protocol`, `input_protocols`, `max_wattage`, `max_wattage_per_output`, `usable_load_factor`, dimensions, certifications, cost.
- `ilL-Spec-Controller`: type, input range, `max_load_watts`, `max_load_amps`, `channels`, `zones`, input/output/wireless protocols, `compatible_drivers`, dimensions.
- `ilL-Spec-Profile`: width, height, stock and max assembled length, joiner system, lens interface. `ilL-Spec-Lens`, `ilL-Spec-Accessory`, `ilL-Attribute-Leader Cable` (`no_conductors`, `awg`, `jacket_rating`).
- Templates: `ilL-Fixture-Template` (e.g. SH01), `ilL-Tape-Neon-Template`, `ilL-LED-Sheet-Template`, `ilL-Driver-Template`, `ilL-Controller-Template`.

**Documents and review**

- `spec_submittal.py` fills PDF submittal templates per line; `ilL-Line-Document` attaches files to schedule lines with SHA-256.
- `ilL-Document-Request` (request types with custom fields, deliverables, comments, SLA, `technical_reviewer`, `fixture_schedule`) and `ilL-Drawing-Review` (`revision`, `revision_token`, `file_sha256`, `build_hash`, `decision`, `reviewed_by`). A design review fits this exactly.

**Frontend pattern**

- Portal pages are Jinja templates with vanilla JS bundles (`public/js/portal*.js`, `public/js/configurator/*`).
- The Product Finder is a React app in `tools/configurator_ui`, built with Vite into committed bundles under `public/product_finder/{portal,public}`; the portal page mounts it with a CSRF token. **The System Designer should copy this pattern.**

**Known portal debt that affects this project** (from `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md`): P0 permission defects (non-dealer company users get write access; schedule list vs direct access mismatch; globally scoped document request lists; drawing requests accepting arbitrary projects), `portal.py` owning too many domains (4,448 lines), inconsistent error contracts, unescaped dynamic HTML. The designer adds a new write surface to schedules, so those P0 items are prerequisites (Phase 0).

### 1.2 Riser Diagram Generator v1.2.0

**Stack:** React 19, strict TypeScript, Vite 8, Zod 4 (schemas are the source of truth), Zustand + immer + zundo (undo/redo), AG Grid Community, Dexie (IndexedDB), `@cantoo/pdf-lib` + fontkit, JSZip, PapaParse, Vitest, Playwright. 97 unit/integration tests; engine coverage ~97% lines.

**Data model (`src/schemas`)**

- `Project`: `meta` (name, number, client, designer, checker, sheet prefix, stamp), `settings` (NEC edition, termination temperature, voltage-drop targets for line/low-voltage/landscape, distributed vs lumped VD, PSU derate 80%, continuous load factor 1.25, breaker limit 80%, tape margin, DMX max unit loads/length, SPI max data length, units, sheet size and flow, wire waste, wire label template).
- `sources` (panel, circuit, voltage, phase, breaker A, poles, switching), `equipment` (catalog item, qty, location, enclosure, `fedFrom` port, feed length, `controlFrom`, control length, DMX universe/address, environment), `loads` (type tag, zone, catalog item, qty **or** tape length, `fedFrom`, home-run length, inter-fixture length, feed method `end|double-end|center|multi-feed`, environment), `controlLinks`, wire overrides, layout pins, notes, revisions, W-tags.
- `CatalogItem` with discriminated `specs` for `psu`, `driver`, `decoder`, `controller`, `tape`, `fixture`, `accessory`, plus `incomplete` (keeps known facts, lists missing fields, blocks calculation). Every item has `erpItemCode`, provenance and `localOverrides`.
- Wire library (`WireType`: conductors, listing, rated V, temperature, plenum/riser/wet/burial/sunlight flags, resistance, ampacity basis) and code tables (NEC Ch. 9 Table 8 resistance, Table 9 effective Z, 310.16 ampacity, 402.5 fixture wire) as editable JSON with citations.

**Engine (`src/engine`)** — pure, no React: graph resolution and cycle detection; load profiles (tape W/ft, multichannel, pixel, fixtures, CC); input current with efficiency and PF; voltage drop (lumped or distributed, multichannel common return); wire selection by environment, ampacity, terminal size and VD target; DMX patching, segments, unit loads, termination; BOM. 39 typed validation codes, e.g. `PSU_OVERLOAD`, `PSU_ABOVE_DERATE`, `CLASS2_OVER_100VA`, `TAPE_RUN_TOO_LONG`, `TAPE_UNDERVOLTAGE`, `VD_OVER_TARGET`, `NO_VALID_WIRE`, `BREAKER_OVERLOAD`, `INRUSH_LIMIT`, `PHASE_DIMMER_COMPAT_UNKNOWN`, `DMX_ADDRESS_OVERLAP`, `DMX_NO_TERMINATOR`, `SUGGEST_SPLIT_FEED`, `CC_COMPLIANCE`.

**Drawing (`src/drawing`)** — paper-inch geometry model; 26 symbol files (PSU, driver, decoder, DMX controller, Lutron, keypad, relay, gateway, wireless TX/RX, pixel controller, opto splitter, distribution, junction, panel, tape, linear, downlight, landscape, terminator, off-sheet…); fixed functional columns (panels → enclosures → supplies → controls → loads); one orthogonal router with lane occupancy, clearances and crossing bridges; pagination with continuation bubbles; title blocks (ARCH C/D, ANSI B/D); schedules and legends; manual pins. Runs in a Web Worker; 200 loads lay out in < 2 s.

**Serializers** — SVG preview, layered PDF (OCG layers, embedded TrueType), native R2007 DXF with blocks and attributes.

**ERP integration today** — `server/proxy.mjs` (loopback-only Express, pull-only, reads `/api/resource/Item` by item group) and `features/erp/sync.ts` (maps ERP fields through `erp-mapping.example.json`; expects `custom_riser_category` and a `custom_riser_specs` JSON blob on Item; preview/commit with conflict detection against local overrides). **Those custom fields do not exist in this ERP.** The integration was designed for a schema that was never built; this plan replaces it with a server-generated catalog (section 15.4).

### 1.3 LED Tape System Visualizer (single-file HTML)

**Engine:** Three.js r128 (UMD from cdnjs), custom orbit controls, procedural PMREM environment, stencil-capped cross-sections, a 2D overlay canvas for labels that is composited into exports.

**What it renders**

- **3D model**: a room (floor, walls, ceiling, cove ledge, base and upper cabinets, bookcase, shower niche, closet, framing) and five zones (cove, under-cabinet, toe-kick, shelving, niche) with channel, tape, diffuser, clips, end caps, connectors, supplies, wall dimmer bank, breaker panel, line- and low-voltage wiring, light washes, CCT and dimming, 24 toggleable layers, camera presets, saved views, exploded view, cross-section.
- **System diagram**: a one-line schematic (breaker → dimmer → supply → tape, one row per zone) in brand style.
- **Training visuals**: about 40 slide-ready visuals for the Intermediate and Advanced curricula (load and supply sizing, max run, feed methods, wire voltage drop, gauge table, cut intervals, corners, takeoff, dimming, DMX, optics, thermal, code checklist), many with build steps and animation.
- **Install guide**: a parameterized cove installation (SH01 St. Helens SF + LED-HD-SW) with a cut list, clip marks, tape pieces, corner routes, jumpers, feed routes, testing and troubleshooting; it plays as a captioned walkthrough, records MP4/WebM, and prints a self-contained HTML guide. It already contains CAD outlines of the SH01 body, lens, clip and swivel bracket (`CAD_SH01`).
- **Export**: PNG at 1×/2×/4× with labels, transparent backgrounds, all build steps, video, saved views.

**Brand system:** full ilLumenate tokens (primary navy, secondary blue, accent gold, Kelvin swatches, RGB product colors, radii, strokes), Manrope + Poppins embedded, logo artwork. This becomes the visual language for the presentation outputs.

**Data:** all hard-coded. Every product fact (W/ft, max run, cut interval, supply sizes, clip spacing, channel dimensions) duplicates something ERPNext owns or should own.

---

## 2. The core problem: three copies of the product data

Today a single fact, such as "LED-HD-SW is 4.4 W/ft, cuts every 50 mm and runs 16.4 ft from one end," lives in up to three places:

| Fact | ERPNext | Riser generator | Visualizer |
|---|---|---|---|
| Tape W/ft | `ilL-Spec-LED Tape.watts_per_foot` (+ offering override) | `TapeSpecs.wPerFtMax` (local library) | `JOB.wPerFt`, `EXAMPLE.wPerFt`, `ZONES[].wPerFt` |
| Cut interval | `cut_increment_mm` (+ override) | `cutIntervalIn` | `JOB.cutIntervalIn`, `EXAMPLE.cutIntervalIn` |
| Max run | `voltage_drop_max_run_length_ft`, 85 W rule | `maxRunFtSingleFeed`, `maxRunFtDoubleFeed` | `JOB.maxRunFt`, `EXAMPLE.maxRunFt` |
| Supply sizes | `ilL-Spec-Driver` rows | `PsuSpecs` (EXAMPLE) | `JOB.supplySizes`, `EXAMPLE.supplySizes` |
| Channel geometry | `ilL-Spec-Profile.width_mm/height_mm` | not modelled | `PROFILES`, `CAD_SH01` |
| Wire resistance | not modelled | NEC Table 8 JSON | `AWG_OHMS_PER_1000FT` |

Every price change, spec revision or new product means three manual updates, and the tools disagree with each other and with the quote. The combined product removes the second and third copies:

- **Product facts** come only from ERPNext, through one adapter that produces the Design Catalog.
- **Engineering reference data** (NEC tables, wire types) is versioned data owned by ilLumenate engineering. Wire types move into ERPNext as a new spec doctype so they can be stocked, priced and added to quotes. Code tables ship with the app as cited, versioned JSON (they are not products).
- **Project facts** (runs, distances, supply placement) live in the saved design, linked to the schedule version.

---

## 3. Gap analysis: what ERPNext must hold for the designer to work

The riser engine refuses to calculate with `incomplete` products, which is the correct behaviour. Each table lists the fields the engine needs, what ERPNext has now, and the proposed change. Full mapping tables are in Appendix A.

### 3.1 LED tape (`ilL-Spec-LED Tape`, `ilL-Rel-Tape Offering`)

| Engine field | ERPNext today | Action |
|---|---|---|
| `voltage` (12/24/48) | `input_voltage` → Link to `ilL-Attribute-Output Voltage` (label) | Add numeric `nominal_voltage_v` to the attribute; adapter reads it. |
| `drive` (CV / CV-CC-IC) | — | Add `drive_type` Select (CV, CV with CC IC). |
| `wPerFtMax` | `watts_per_foot` (+ `watts_per_ft_override` per offering) | Use offering override when present. Document that the value is maximum, not typical. |
| `channels`, `channelMap`, `channelWPerFtMax` | — (implied by LED package: single, TW, RGB, RGBW) | Add `channels` Int and a child table `channel_name`, `max_w_per_ft`. Default 1. |
| `powerBasis`, `maxSimultaneousPct` | — | Add with defaults (`all-channel-max`, `channels × 100`). |
| `maxRunFtSingleFeed` | `voltage_drop_max_run_length_ft`, 85 W rule in engine | Add explicit `max_run_single_feed_ft`; keep the old field as the source during migration. |
| `maxRunFtDoubleFeed` | — | Add `max_run_double_feed_ft`. |
| `minOperatingV` | — | Add `min_operating_voltage_v` (needed for `TAPE_UNDERVOLTAGE` and real VD-at-tape checks). |
| `cutIntervalIn`, `freeCutting` | `cut_increment_mm`, `is_free_cutting` | Convert mm → in in the adapter. |
| `reelLengthFt` | — | Add `reel_length_m` (also used by takeoffs and install guides). |
| `pixel` (protocol, px/ft, A/px) | — | Add a pixel section for addressable tape. |
| Visual facts | `led_pitch_mm`, `lumens_per_foot` | Add `tape_width_mm`, `leds_per_segment` (install guide, 3D). |

### 3.2 Power supplies and drivers (`ilL-Spec-Driver`)

| Engine field | ERPNext today | Action |
|---|---|---|
| `inputType`, `inputVMin/Max`, `inputPhase` | `input_voltage_type`, `input_voltage_min/max` | Add `input_phase` (default 1PH). |
| `outputType` CV/CC, `outputV`, `outputmA`, `outputVMin/Max` | `output_type`, `voltage_output` (Link) | Add `output_current_ma`, `compliance_v_min/max` for CC drivers. |
| `ratedW`, `outputs[]` (name, maxW, class2) | `max_wattage`, `max_wattage_per_output`, `outputs_count`, `independent_outputs_count` | Add `class2_outputs` Check (or per-output table when outputs differ). |
| `efficiency`, `powerFactor` | — | Add both (needed for input current and breaker loading). |
| `maxInputA`, `maxInputAAtV` | — | Add. |
| `inrushA`, `maxUnitsPer20ABreaker` | — | Add (needed for `INRUSH_LIMIT`, supplies per circuit). |
| `dimming[]` | `input_protocols` child table | Map protocol names to the engine's protocol enum (Appendix B). |
| `terminalMinAwg`, `terminalMaxAwg` | — | Add (needed for `TERMINAL_OVERSIZE`). |
| `listings[]` | `certifications` | Map. |
| Derate | `usable_load_factor` (e.g. 0.8) | Keep as the authority. The engine's `psuDeratePct` setting becomes "ERP default, override only with staff role". |
| Physical | width/height/depth/weight | Already present; used for 3D and cabinet fit. Add `mounting` (DIN, screw, plug-in), `location_rating` (dry, damp, wet). |

### 3.3 Controllers, dimmers, decoders (`ilL-Spec-Controller`)

The riser engine splits controls into `decoder` and `controller` kinds with ports. ERPNext has one doctype with `controller_type`.

| Engine field | ERPNext today | Action |
|---|---|---|
| Kind (decoder / controller / converter / keypad / gateway…) | `controller_type` Select | Map values to engine categories (Appendix B); add missing values. |
| `channels`, `maxAPerChannel`, `maxATotal`, `maxWPerChannel`, `maxWTotal` | `channels`, `max_load_amps`, `max_load_watts` | Add per-channel limits. |
| `dmxFootprint`, `unitLoad`, `dmxThru` | — | Add. |
| `ports[]` (name, direction, protocol, maxDevices) | input/output protocol tables | Add a ports child table. |
| `powerType`, `outputDimming` (AC phase-cut decoders) | `input_voltage_type` | Add `output_dimming` for AC decoders and wall dimmers. |
| Phase dimmer limits: min load, LED max W, supplies per dimmer, neutral required | — | Add (the training visuals already teach these: `DIMMER` in section 1c). |
| `maxUniverses`, `maxPixels`, `maxDataLengthFt`, `maxBusDevices` | — | Add for pixel controllers and gateways. |
| `terminalMinAwg/MaxAwg`, `ownPowerW` | `standby_power_watts` | Map / add. |

### 3.4 Linear fixtures (configured)

Configured linear fixtures already store everything per build: run lengths, run watts, feed types, leaders and jumpers. The adapter models each configured fixture build as a `fixture` (or a tape-like `load` per run, see section 9.2) with its actual runs. No new fields are needed beyond the tape specs above, because the tape offering drives the electrical rules.

### 3.5 Profiles, lenses and visuals

| Need | ERPNext today | Action |
|---|---|---|
| Cross-section outline for 3D, exploded views and install guides | width/height only | Add a `cross_section_file` (DXF) attachment plus a generated `cross_section_json` (closed polylines for body, lens, clip, in 1/1000 in, the same format as `CAD_SH01`). Staff upload the DXF once per profile family; a server job flattens it. |
| Mounting hardware geometry (clip, swivel bracket) | `ilL-Spec-Accessory` (type, mounting method) | Add the same cross-section fields; add `clip_spacing_max_in`, `clip_end_offset_in`, `screw_spec`. |
| Lens transmission and diffusion class | `ilL-Spec-Lens` | Add `transmission_pct`, `diffusion_class` (clear, frosted, opal) for optics visuals. |
| Thermal limit | — | Add `max_w_per_ft` per profile (the Advanced thermal table) and tape `max_case_temp_c`. |
| Product imagery for presentation | Webflow product images | Reuse `ilL-Webflow-Product` gallery and add a transparent "diagram icon" per template. |

### 3.6 Wire and cable (new)

ERPNext has `ilL-Attribute-Leader Cable` (conductors, AWG, jacket) for factory leaders only. The designer recommends field wire, so a wire library is required.

- New doctype **`ilL-Spec-Wire`** linked to an `Item` (so it can be stocked, priced and quoted): category (Class 2 power, building wire, data, control, landscape), conductor groups (count, AWG, material, role, colors, resistance override), listing (CL2, CL3, CL2P, CL3R, CMP, NM-B, UF…), rated V, temperature rating, plenum/riser/wet/burial/sunlight/shielded flags, OD, applications (the engine's run types), `riser_label`, verification flag and provenance.
- Seed from the riser repo's `wires.seed.json` after engineering review (it is marked EXAMPLE today).
- Code tables (NEC Table 8, Table 9, 310.16, 402.5) ship with the app as JSON with edition and citation, exactly as the riser repo does. Staff can switch the default edition; a project records which edition it used.

### 3.7 Third-party ("Other manufacturer") schedule lines

Lines for other manufacturers carry text fields only. To include them in a riser the dealer must enter watts, input voltage and dimming as numbers, or the line stays `incomplete` and is drawn with a "data required" flag (never silently calculated). Add numeric `watts_each`, `input_voltage_v`, `voltage_class` (line/low) to the schedule line.

### 3.8 Catalog readiness reporting

Extend `product_readiness.py` (or add `design_readiness`) so the Catalog Builder shows, per tape, driver, controller and wire, which design fields are missing. A product can be published for quoting before it is design-ready; the designer then shows it as `incomplete` with the missing field names, and staff get a work list.

---

## 4. Product vision, users and jobs

### 4.1 Vision

> A dealer opens a fixture schedule, and twenty minutes later has a checked power plan, a riser an electrician will accept, a picture the homeowner will love, and install instructions the crew can follow — all built from the same products they are quoting.

### 4.2 Users

| Persona | Who | Primary jobs | Mode |
|---|---|---|---|
| **Dealer designer** | AV/lighting integrator's designer or project manager | Assign supplies, check runs, produce the riser and package | Designer (full) |
| **Dealer sales** | Integrator's salesperson | Show the homeowner what they are buying; make the quote match | Presenter (simplified) |
| **Installer / electrician** | Field crew, often the dealer's subcontractor | Read the riser and install guide; know wire types and lengths; label | Viewer (shared link / PDF / QR) |
| **Applications engineer** | ilLumenate staff | Review designs, mark up, approve; handle exceptions | Reviewer (staff) |
| **Specifier / lighting designer** | Architect or LD on the project | Receive submittals and a professional riser | Viewer |
| **Homeowner / GC** | End client | Understand and approve the design | Viewer (presentation only) |
| **Catalog owner** | ilLumenate product team | Keep design fields complete | Desk (Catalog Builder) |

### 4.3 Jobs to be done

1. "Turn my fixture schedule into a power plan I can trust without calling the factory."
2. "Tell me where the supplies can go and what wire to pull before rough-in."
3. "Give my electrician a drawing that looks like engineering made it."
4. "Help me sell the job with something beautiful that isn't a spec sheet."
5. "Give my crew step-by-step instructions for *this* cove, not a generic one."
6. "Make sure the quote has every supply, dimmer and foot of wire the design needs."
7. "Let ilLumenate check my work and stamp it when I need that."

### 4.4 Two experience levels in one tool

- **Guided (default for dealers):** a step-by-step flow (section 6), plain language, defaults filled in, checks shown as cards with a fix button, technical settings hidden.
- **Engineering (opt-in, staff and power users):** the riser repo's grid tables (sources, equipment, loads, control links), all settings, manual pins, wire overrides, parallel conductors, code-edition choice.

Both edit the same design document. Switching never loses data.

---

## 5. Product principles

1. **ERPNext is the only product source.** The designer never stores a product spec it can't trace to an ERP record and revision. Local overrides exist only for staff, are recorded, and are flagged on every output.
2. **The schedule is the bill of quantities.** The designer reads lines and writes back the lines it adds (supplies, controllers, wire, accessories). It never edits configured builds; to change a build the dealer reopens the configurator.
3. **One engine, one drawing model, many outputs.** The riser rule carries over: the engine computes; the riser, presentation diagram, plan view, 3D, install guide and BOM consume engine output and never recompute electrical values.
4. **Never invent data.** Missing facts produce `incomplete` with named missing fields, not guesses. EXAMPLE products never appear in dealer projects.
5. **Honest checks with a fix.** Every warning says what is wrong, why it matters, and the smallest change that fixes it ("Move PS-2 within 18 ft of the run or use 14 AWG").
6. **Deterministic and reproducible.** The same design, catalog snapshot and engine version produce byte-identical outputs. Every output carries a build hash, so a reviewed drawing can be proven unchanged (this is what `ilL-Drawing-Review.build_hash` is for).
7. **Beautiful for people, precise for trades.** Presentation outputs use the brand system (Manrope/Poppins, navy/blue/gold, zone colors). Engineering outputs use drafting conventions (Arimo/Roboto Condensed, black lines, title blocks).
8. **Respect the existing permission model.** Dealers see only their customers' projects; no cost data leaves the server; share links are signed and expire.
9. **Line voltage belongs to the electrician.** The tool sizes and draws 120/277 V circuits for coordination but labels them "by licensed electrician" and never presents them as stamped engineering unless staff review approved them.

---

## 6. The end-to-end workflow

```
Portal schedule ──► 1 Intake ──► 2 Site ──► 3 Runs ──► 4 Power & controls ──► 5 Check ──► 6 Outputs ──► 7 Package / Review / Quote
       ▲                                                                                                          │
       └──────────────────────── supplies, controllers, wire written back as schedule lines ──────────────────────┘
```

The guided flow is a stepper with these screens; each step can be revisited, and the check panel is visible throughout.

| Step | Screen | Dealer does | System does |
|---|---|---|---|
| 1 | **Start** | Opens "Design system" from a schedule, or enters a schedule number, or picks project → schedule | Loads schedule version, lines, configured builds, Design Catalog snapshot; shows readiness |
| 2 | **Spaces** | Names rooms/areas, marks the electrical room and panel, optionally uploads a floor plan | Groups lines by `location`; suggests spaces from location text |
| 3 | **Runs** | Confirms each run's space, feed end, environment (dry, damp, wet, in-wall, plenum, outdoor) and distance to its supply | Expands lines × qty into physical runs with ERP lengths and watts |
| 4 | **Power** | Places supplies (or accepts auto-plan), drags runs onto supply outputs, assigns supplies to circuits and cabinets, adds dimmers/controllers | Live load bars per supply and output; eligible supplies only |
| 5 | **Check** | Reviews cards, applies fixes | Runs the engine; voltage drop, wire selection, breaker load, DMX, compatibility |
| 6 | **Views** | Chooses outputs: riser, presentation, plan, 3D | Renders from one model; exports |
| 7 | **Finish** | Builds the package, requests review, updates the quote | Writes lines back; creates deliverables; opens a review request |

---

## 7. Module 1 — Project and schedule intake

### 7.1 Entry points

- **From the schedule page** (`/portal/schedules/<schedule>`): a "Design system" button. Opens `/portal/schedules/<schedule>/design`.
- **From the projects list:** a "Designs" tab per project listing designs per schedule.
- **Direct:** `/portal/design` with a search box that accepts a schedule number (`naming_series` value) or project name, scoped to what the user may access (reuse `get_user_projects_for_configurator`, `get_schedules_for_project`).
- **Staff:** a Desk button on `ilL-Project-Fixture-Schedule` opens the same app in reviewer mode.

### 7.2 What intake loads

1. The schedule header, version and lock state.
2. All lines, including accessory and power lines (`power_supply_for_line`).
3. For each configured line: the configured record's runs, segments, feed types, leader/jumper cable manifest, environment rating, tape offering, `power_plan_json` and `max_run_ft_effective`.
4. The Design Catalog snapshot (section 15.4), limited to products relevant to the schedule plus all design-ready supplies, controllers and wires.
5. Any existing `ilL-System-Design` for this schedule.

### 7.3 Readiness screen

Before the dealer starts, show a short readiness summary:

- Lines ready (configured and design-ready products).
- Lines that need data (third-party lines without numeric watts, products with missing design fields) with a "Complete" action for third-party lines and a "Notify ilLumenate" action for catalog gaps (creates a catalog-readiness task, deduplicated).
- Lines not yet configured (link to the configurator).
- Whether the schedule is locked (designs on a locked version are read-only; offer "design on a new version").

### 7.4 Keeping the design in sync with the schedule

The design stores the schedule version and a hash per line (`line_key`, configured record name, `config_hash`, qty). On open:

- **Unchanged:** proceed.
- **Changed lines:** show a reconcile dialog: added lines (new runs to assign), removed lines (their assignments are dropped, listed), changed builds (lengths/watts differ; assignments kept, checks rerun), qty changes (extra builds to assign, or surplus assignments removed).
- **New schedule version:** offer "copy design to the new version" (the design is versioned with the schedule; see section 16.1).

### 7.5 Acceptance

- Opening a 150-line schedule with configured builds takes < 3 s to first paint on a typical connection (lines and catalog loaded in parallel; catalog cached by hash).
- A dealer can never load a schedule they cannot open in the portal (same permission function).

---

## 8. Module 2 — Site model (spaces, locations, distances)

The visualizer and riser both need "where." The schedule only has a free-text `location`. A light site model fills the gap without becoming CAD.

### 8.1 Entities

- **Space:** name, level (Basement, Level 1…), type (kitchen, living, bath, exterior, mechanical…), optional archetype for 3D (section 12.4).
- **Electrical location:** panel (with circuits), cabinet/enclosure (a named supply location: "Mechanical room rack," "Sink base," "Attic over hall"), each in a space, with environment and access notes.
- **Distances:** home-run lengths are entered per run (to its supply) and per supply (to its circuit/panel). The tool offers quick estimates: "same space" (default 10 ft), "adjacent," "another level," or a measured number. On a floor plan (section 12.3) distances are measured from placed points with a slack factor.

### 8.2 Behaviour

- Auto-create spaces from distinct `location` values; dealers merge or rename.
- Cabinets become riser enclosures (the riser layout already treats enclosures as compound units with supply/control/load columns).
- Environment defaults cascade: space → cabinet → run, overridable per run (in-wall, plenum ceiling, wet, outdoor, direct burial).

---

## 9. Module 3 — Run builder

### 9.1 Expanding schedule lines into physical runs

A schedule line `F3 · qty 4 · Kitchen` with a configured linear fixture of 2 runs becomes 8 physical runs: `F3-1.1`, `F3-1.2`, `F3-2.1` … `F3-4.2`. Each run carries:

- `run_key` = `{line_key}:{build_index}:{run_index}` (stable across reopen; tied to `line_key`, not row index).
- Length and watts from the configured record's `runs` (ERP authority, read-only).
- Feed type and direction from the configured segments; the number of feeds (`end`, `double-end`, `center`, `multi-feed`) follows the build's feed plan.
- Environment rating, tape spec and offering (for VD, min voltage, max run).
- The factory leader/jumper cable from `cable_manifest_json` (the first part of the wire path: factory leader to the field junction).

**Large quantities.** Where qty is large and builds are identical (e.g. 24 identical shelf lights), runs can be handled as a **group**: assign once, applied to all, drawn on the riser as a stacked bank (the riser drawing already supports parallel receiver banks). The group can be split at any time.

### 9.2 How runs map into the engine

| Product family | Engine representation |
|---|---|
| LED Tape / COB / Neon (configured) | One `load` per run: `catalogId` = tape catalog item from the offering, `lengthFt` = run length, `feedMethod` from the build, `homeRunLengthFt` from the site model |
| Linear fixture (configured) | One `load` per run, same as tape, with the build's tape offering as the electrical item; the fixture's part number is carried for labels |
| LED Sheet | One `load` per sheet feed using the sheet's power plan |
| Configured group | One `load` per member run; group label kept for drawings |
| Third-party low-voltage fixture | `fixture` load with qty, watts, input V, drive; `incomplete` until numeric data is entered |
| Third-party line-voltage fixture | `fixture` load (`voltageClass: line`) on a source circuit; drawn for coordination |
| Accessory and driver lines already on the schedule | Become equipment candidates in the supply pool (section 10.2) |

### 9.3 Run editor

A table (guided mode: cards per space) with: run key, fixture type, space, length (read-only), watts (read-only), feed end(s), environment, home-run length, assigned supply/output, status chip. Bulk edit for environment and distance. A strip preview shows the run and its feed points (reusing the visualizer's strip renderer, `drawStrip`).

### 9.4 Run-level checks (before power assignment)

- Run length vs `max_run_single_feed_ft` / `max_run_double_feed_ft` (ERP already enforces this in the configurator; the designer re-checks because jumpers and site feeds can combine runs).
- Feed method feasibility (e.g. double-end needs a second home run; center feed needs mid-run access).
- Jumper-connected runs are one circuit (`tape_neon_power.connected_runs` logic).

---

## 10. Module 4 — Power and control assignment

This is the heart of "link power supplies to specific runs."

### 10.1 The power board (guided mode)

A two-pane workspace:

- **Left — Runs to power:** unassigned runs grouped by space, each a card showing watts and length.
- **Right — Supplies:** each supply is a card with its model, location (cabinet), a load bar (used vs `max_wattage × usable_load_factor`, with the 80% line), and its output slots. Each output slot shows its own load bar against `max_wattage_per_output × usable_load_factor` and its Class 2 status.
- **Drag** a run onto an output. A run that would overload the output or supply is refused with the reason. Multi-select drags several runs.
- **Add supply:** picker filtered to drivers eligible for every run you intend to put on it: voltage match, protocol match (the dimming method chosen for the zone), driver eligibility (`ilL-Rel-Driver-Eligibility` for the runs' templates), location rating vs the cabinet environment. Sorted by fit (fewest supplies, then size).
- **Auto-plan:** see 10.3.
- Supplies are placed in a cabinet (Module 2). Cabinets show combined load, heat (W lost = load × (1/efficiency − 1)) and the circuit they're on.

### 10.2 Starting point from ERP

When the configurator already planned power for a build (`include_power_supply` with `power_plan_json` allocations, and supply lines under the fixture line), the designer pre-places those supplies and allocations as the **default** assignment, marked "from configurator." The dealer can keep them, consolidate across builds, or move supplies to a shared cabinet. Consolidation is the main value: per-build planning often yields more supplies than a site-level plan.

### 10.3 Auto-plan (site-level allocator)

Extend `plan_power` into a site-level planner:

- **Inputs:** runs (watts, voltage, protocol, space), candidate supplies per run (eligibility), cabinets with allowed supply types and capacity, maximum home-run length or VD budget per run, policy (fewest supplies, fewest cabinets, shortest wire, lowest cost).
- **Constraints:** one run per output (never paralleled); per-output and total limits × `usable_load_factor`; all runs on a supply share voltage and dimming protocol; a run can only go to cabinets within its distance/VD budget; supply location rating ≥ cabinet environment; Class 2 per output.
- **Algorithm:** the existing exact search covers ≤12 circuits. For a site, partition by voltage + protocol + cabinet reachability, then run exact search per partition when small, and a first-fit-decreasing with local improvement (swap/merge) when large. Report optimality ("exact" or "heuristic, within N supplies of the lower bound").
- **Output:** proposed supplies per cabinet and allocations, shown as a diff to accept wholesale or per cabinet.
- Implemented in the shared TypeScript engine (instant feedback) with a Python mirror for server verification (section 18).

### 10.4 Sources, circuits and breakers

- Each cabinet or supply is fed from a source: panel, circuit, voltage (120/208/240/277…), breaker A, switching (none, relay, phase-forward, phase-reverse, 0-10V, Lutron module) — the riser `Source` schema.
- Breaker loading uses supply input current (from efficiency, PF and `maxInputA`), continuous load factor 1.25 and the 80% limit; supplies per 20 A breaker and inrush limits are enforced.
- Guided mode asks one question per cabinet: "Which circuit feeds this? (Panel, circuit number, switched by…)." Engineering mode shows the full sources grid.

### 10.5 Controls

- **Zones and dimming method:** a zone is a set of runs dimmed together. The dealer picks the method per zone (ELV/TRIAC phase-cut, 0-10V, DALI-2, DMX512, Lutron QS/EcoSystem, wireless). This filters supply choices (driver input protocols) and adds the needed devices.
- **Phase-cut zones:** wall dimmer from the controller catalog; checks min load, LED max W, supplies per dimmer, neutral requirement (`PHASE_DIMMER_COMPAT_UNKNOWN` when the pairing isn't on a tested list).
- **DMX zones:** controller → decoders → supplies; decoder channels per run (TW = 2, RGB = 3, RGBW = 4); auto-patch addresses by chain order; universe, unit loads, cable length and terminator checks (riser engine `dmx.ts`).
- **0-10V:** controller sink capacity vs number of drivers.
- Control links are drawn as their own layer on every output.

### 10.6 Acceptance

- Assigning a run updates load bars and checks in < 100 ms for designs up to 300 runs.
- Undo/redo for every assignment (zundo, as in the riser repo).
- Auto-plan on a 60-run residential design returns in < 2 s.

---

## 11. Module 5 — Engineering checks and recommendations

### 11.1 Check catalogue

Every check is an engine validation code (riser list, extended). Each has: severity, plain-language title, explanation, the numbers, and one or more **fix actions** that edit the design.

| Area | Checks | Example fix actions |
|---|---|---|
| Supply loading | `PSU_OVERLOAD`, `PSU_ABOVE_DERATE` (80% / `usable_load_factor`), `CHANNEL_OVERCURRENT`, per-output limit | Move run to another output; add a supply; switch to a larger supply |
| Class 2 | `CLASS2_OVER_100VA` per output | Split across outputs; use a Class 2 output |
| Run length | `TAPE_RUN_TOO_LONG`, `MAX_LENGTH_HINT`, `SUGGEST_SPLIT_FEED` | Change to double-end feed; add an injection feed; split the run |
| Voltage at the tape | `TAPE_UNDERVOLTAGE` (supply V − home-run drop − in-tape drop < `min_operating_voltage_v`), `VD_OVER_TARGET` | Upsize wire; move supply closer; feed from both ends |
| Wire selection | `NO_VALID_WIRE`, `WIRE_REQUIRES_VERIFICATION`, `TERMINAL_OVERSIZE`, `PARALLEL_REVIEW_REQUIRED` | Choose listed alternative; split the circuit |
| Wire type for environment | In-wall → CL2/CL3 minimum; plenum → CL2P/CL3P; riser → CL2R/CL3R; wet/outdoor → wet-rated, sunlight-resistant; burial → direct-burial rated | Auto-select compliant wire type |
| Line voltage | `BREAKER_OVERLOAD`, `INRUSH_LIMIT`, minimum line-voltage AWG | Split cabinets across circuits |
| Compatibility | `VOLTAGE_MISMATCH`, `DRIVE_MISMATCH` (CV/CC), `PROTOCOL_MISMATCH`, `INPUT_V_OUT_OF_RANGE`, `CC_COMPLIANCE`, `PHASE_DIMMER_COMPAT_UNKNOWN` | Swap to an eligible supply |
| Controls | `DMX_ADDRESS_OVERLAP/OVERFLOW`, `DMX_UNIT_LOADS`, `DMX_LENGTH`, `DMX_NO_TERMINATOR`, `DMX_TOPOLOGY`, `SPI_DATA_LENGTH`, `DEVICE_CAPACITY` | Re-patch; add splitter; add terminator |
| Data quality | `INCOMPLETE_SPEC`, `EXAMPLE_PRODUCT_IN_USE`, `UNRESOLVED_REF`, `CYCLE` | Complete third-party data; notify catalog team |
| Thermal (new) | W/ft vs profile `max_w_per_ft`; supply heat in enclosed cabinets | Choose deeper profile; ventilate cabinet |
| Placement (new) | Supply in a location it isn't rated for; no service access marked | Move supply; mark access |

### 11.2 Voltage drop and wire gauge (closing the MVP gap)

The riser engine already computes VD per run (lumped or distributed, multichannel common return) with NEC Table 8 resistance and selects the smallest wire that meets the target and ampacity in the run's environment. The designer shows, per run:

- Home-run wire type and gauge, one-way length, current, drop in volts and percent, voltage at the tape, and the margin to `min_operating_voltage_v`.
- A **"what gauge if…" slider** (distance) showing where the recommendation steps up (the visualizer's gauge cheat-sheet, now live).
- Project-level targets (3% Class 2 default; 5% landscape) set by staff policy; dealers can tighten but not loosen without review.

This replaces the static `voltage_drop_max_run_length_ft` heuristic for site wiring and resolves the limitation noted in `docs/MVP_CONSTRAINTS.md`.

### 11.3 Wire takeoff

Every home run, control link and line-voltage branch gets a W-tag (`W-01`…), length (with waste %), wire type and a quoting Item. Totals per wire Item roll up into the BOM and can be written to the schedule as accessory lines (section 14.5).

### 11.4 Explanations and learning

Each check card has a "Why?" link that opens the relevant training visual with the dealer's own numbers (e.g. `PSU_ABOVE_DERATE` opens the 3.1 load-and-supply visual with this supply and load). This turns the training library into contextual help.

### 11.5 Overrides

- Dealers can acknowledge warnings with a reason; errors cannot be overridden by dealers.
- Staff can override errors with a reason; the override and reviewer are printed in the QA notes and drawing revision block.

---

## 12. Module 6 — Outputs: riser, presentation diagram, plan view, 3D

All four views read the same design and engine result. Changes in any editor update every view.

### 12.1 Engineering riser (from the riser generator)

- The riser layout, router, pagination, title blocks, schedules and serializers move in unchanged where possible.
- **Title block:** ilLumenate brand plus a dealer logo slot (from the dealer's Customer record), project/schedule/version, design revision, designer, checker (ilLumenate reviewer when approved), stamp (`PRELIMINARY`, `FOR REFERENCE`, `NOT FOR CONSTRUCTION`, or "REVIEWED BY ILLUMENATE" when approved).
- **Schedules on the sheets:** fixture schedule (from the ERP schedule, Fixture Type / qty / location / part number), power-supply schedule (tag, model, cabinet, circuit, outputs used, load, % of rating), wire schedule (W-tag, from/to, type, AWG, length, VD), panel/circuit schedule, DMX patch, BOM, general and key notes.
- **Labels:** equipment tags (`PS-01`), run tags (`F3-2.1`), wire tags printed on the drawing and on labels (section 13.4).
- **Formats:** layered PDF (OCG layers: power, control, annotations, schedules), native DXF (blocks/attributes for CAD import), SVG; sheet sizes ARCH C/D, ANSI B/D, plus a new **Letter/Tabloid** sheet for dealer packages.

### 12.2 Presentation diagram ("system story")

A non-technical, brand-styled diagram that generalizes the visualizer's schematic mode.

- **Layout:** one band per space (or per zone), flowing left to right: power source → cabinet/supplies → control → light. Each band shows the space name, the zone color, an icon per product (template diagram icon from ERP), and a lit strip with the run's CCT.
- **Content:** product names and finishes, CCT and dimming method, supply locations as friendly labels ("Supplies in the mechanical room"), total connected light. No gauges or W-tags.
- **Variants:** homeowner (simplest), designer (adds CCT/CRI/output/profile), installer (adds supply tags and wire types, still brand-styled).
- **Formats:** PNG (1×/2×/4×), PDF page, embeddable image for proposals.
- **Rendering:** a 2D canvas/SVG renderer built from the visualizer's slide kit (`card`, `pill`, `drawStrip`, `drawPSU`, brand tokens, Manrope/Poppins). SVG output is preferred so PDFs stay vector.

### 12.3 Plan view (floor-plan overlay)

The missing piece between "diagram" and "3D": where things physically are.

- Dealer uploads a floor plan (PDF page or image) per level and sets scale with a two-point calibration.
- Places **runs** (polylines along the cove/cabinet line), **supplies/cabinets**, **dimmers/keypads**, **panel**. Draws or auto-routes **wire paths** (orthogonal Manhattan routes with a slack factor).
- Measured path lengths become the home-run lengths in the engine (with "measured on plan" provenance), replacing estimates.
- Output: plan sheet PDF with symbols, run tags, supply tags, wire tags and a legend; a brand-styled version for presentations.
- Phase 6 scope; Phases 3–5 work with entered distances.

### 12.4 3D project view

Rebuilt from the visualizer as a modular scene system (section 19.3).

- **Space archetypes:** parameterized scene kits for the common residential applications already modelled — cove (rectangular, L, U, linear), under-cabinet, toe-kick, shelving/bookcase, shower niche — plus new ones: ceiling reveal/mud-in, stair nosing, vanity/mirror back-light, closet rod, exterior soffit. Each archetype has parameters (lengths, heights, depth) filled from the runs assigned to the space.
- **Products from ERP:** channel cross-sections from the profile's `cross_section_json`, tape width and LED density from tape specs, lens type/finish from the configured build, supply box dimensions from the driver spec.
- **Power and wiring shown:** supplies in their cabinets (attic, closet, sink base, rack), routed low-voltage wires per run in zone color, line-voltage legs, dimmers/keypads, panel. Layers and zone toggles as in the visualizer.
- **Lighting:** glow, washes, CCT, dim level; tunable white and RGB colour preview.
- **Detail views:** exploded and cross-section of any run's assembly (the visualizer's stencil-capped section with ERP geometry).
- **Camera:** presets (perspective, isometric, plan, elevations, section close-up), saved views, framing presets (16:9, 4:3, 1:1).
- **Exports:** PNG with labels, turntable/flythrough video (MP4/WebM via MediaRecorder), all saved views.
- **Scope limits:** this is a representative model, not a survey. Each render carries "Representative — not to scale" unless built from a calibrated plan (12.3) in a later phase ("extrude walls from the plan").

### 12.5 Output consistency rules

- Tags, colors and names come from one design dictionary: zone color (brand ramp), equipment tag, run tag, W-tag.
- A view never shows a number the engine didn't produce (principle 3).
- Each export embeds design ID, revision, engine version, catalog snapshot hash and build hash in metadata (PDF info, DXF header variables, PNG tEXt, SVG `<metadata>`).

---

## 13. Module 7 — Install guides, training and support visuals

### 13.1 Install guides per run or per space

The visualizer's install guide (section 21 of the HTML) becomes a generator driven by the design:

- **Inputs from ERP:** profile cut lengths, lens cuts and end caps (`ilL-Child-Configured-Segment`), tape cut lengths and segment counts, cut interval, feed and jumper plan (`cable_manifest_json`), clip type, spacing and screw spec (accessory spec), cross-section geometry.
- **Inputs from the design:** supply location, feed route, home-run wire type/gauge/length, split point, dimmer/controller, labels.
- **Steps (templated per product family):** at a glance, parts and tools, lay out and mark, mount clips, cut channel and lens, cut tape, corners (routes), jumpers, power to the feed point, wiring diagram, assembly, test, troubleshooting, finished view.
- **Factory-built vs field-built:** configured linear fixtures arrive cut and assembled, so their guide skips cutting and covers mounting, joining shipped pieces (`SHIP_PIECES`), feeding and testing. Tape/neon field builds get the full guide.
- **Outputs:** captioned walkthrough in the portal, MP4/WebM video, printable HTML/PDF, and a per-space QR code that opens the guide on a phone (signed link).

### 13.2 Training visuals library

The ~40 training visuals become a library in the portal's Resources page:

- Default numbers come from real ERP products (a representative tape, supply and wire) instead of `EXAMPLE`.
- Every visual can be opened with the dealer's design values ("show this with my run").
- Staff keep curriculum text in ERP (a simple `ilL-Training-Visual` config: id, section, title, captions, product bindings), so the copy changes without a code release.
- Export PNG per build step and video, as today, for slide decks.

### 13.3 Contextual help

Check cards, run editor fields and supply cards link to the matching visual (section 11.4). The guided flow shows a short visual on first use of each step.

### 13.4 Labels

Printable label sheets (Avery-compatible PDF) for supplies (`PS-01 · 96 W · Cabinet: Mech room · Circuit 12 · Zones Z1/Z2`), wire ends (`W-07 · PS-01 OUT 2 → F3-2.1`) and runs, each with a QR code to the design's installer view.

---

## 14. Module 8 — Documentation package, review, sharing and commerce

### 14.1 Documentation package

A one-click bundle assembled from the design:

1. Cover (brand, project, dealer, revision, stamp).
2. Fixture schedule (existing schedule export path).
3. System summary (presentation diagram + totals: connected watts, supplies, circuits).
4. Engineering riser sheets.
5. Plan view sheets (when present).
6. 3D renders (saved views).
7. Supply, wire and panel schedules; DMX patch; BOM.
8. Install guides per space.
9. Spec submittals for every line and every added supply/controller (existing `spec_submittal.py`).
10. Code and listing checklist (Advanced 4 content, filled with the products' certifications).

Delivered as a merged PDF plus a ZIP (PDF, DXF, PNG, labels). Stored as private files linked to the design revision with SHA-256 (the `ilL-Line-Document` pattern).

### 14.2 Engineering review by ilLumenate

- "Request review" creates an `ilL-Document-Request` of a new request type **System Design Review**, linked to the schedule and the design revision, with priority and due date.
- Staff open the design in reviewer mode: comment pins on any view (riser, plan, 3D), check overrides, approve or request changes.
- Approval writes an `ilL-Drawing-Review` with `revision`, `revision_token`, `file_sha256` of the package and `build_hash` of the design. Outputs then carry "Reviewed by ilLumenate · <reviewer> · <date>". Any later edit creates a new revision and removes the stamp until re-reviewed.
- Optional policy: review required before Sales Order for designs over a threshold (e.g. > 1 kW, any DMX, any line-voltage dimming).

### 14.3 Sharing

- Signed, expiring read-only links per audience: **homeowner** (presentation + 3D), **installer** (riser, plan, guides, labels; no prices), **specifier** (riser + submittals).
- Share views never expose prices, costs or other projects.
- Collaborators on the project (existing `ilL-Child-Project-Collaborator`) get in-portal access with their role.

### 14.4 Versioning

- A design has revisions (A, B, C…). Saving a revision freezes its inputs, catalog snapshot hash, engine version and outputs.
- When the schedule gets a new version (`create_schedule_version`), the design can be copied forward; diffs are listed (section 7.4).

### 14.5 Commerce loop: writing back to the schedule

- Supplies, controllers, dimmers, decoders, terminators, wire (by Item and length) and accessories the design adds become schedule lines through one endpoint, using the `power_supply_lines.py` pattern (a marker field ties each line to the design, so the design can update or remove only its own lines).
- When the design consolidates supplies that the configurator had added per build, the per-build supply lines are replaced by the design's site-level lines (the dealer confirms the diff first).
- Pricing then flows through the normal quote → Sales Order path; the design shows the price impact of changes when the user has the pricing role.
- A schedule with a design shows a "Designed" badge and a link; the quote PDF can append the system summary page.

---

## 15. Architecture

### 15.1 Options considered

| Option | Description | Verdict |
|---|---|---|
| A. Keep three apps, sync data | Riser stays local, visualizer stays a file, both pull from ERP | Rejected: still three UIs, three storage models, no write-back, no review |
| B. Rebuild everything in Frappe/Jinja + vanilla JS | Match the existing portal pages | Rejected: discards a mature TypeScript engine, router and serializers; vanilla JS is the source of the portal's current quality problems |
| C. Separate hosted app (e.g. Vercel) calling ERP APIs | Modern stack, independent deploys | Rejected for v1: second auth system, CORS, a second deployment, cost data risk; the Product Finder already retired a Vercel prototype for these reasons |
| **D. React/TS app inside this Frappe app, committed bundle** | Same pattern as the Product Finder; portal session and CSRF; Python endpoints | **Recommended** |

### 15.2 Recommended structure

```
tools/system_designer/                 # Vite + React + TS workspace (npm workspaces)
  packages/
    core-schemas/                      # Zod schemas (from riser src/schemas), JSON Schema export
    engine/                            # pure calc engine (from riser src/engine) + site allocator
    drawing/                           # paper-inch drawing model, symbols, layout, router (riser)
    serializers/                       # SVG, PDF (OCG), DXF (riser)
    present/                           # brand 2D renderer: presentation diagram, labels, training kit
    scene3d/                           # Three.js scene system: archetypes, products, wiring, export
    guides/                            # install-guide generator (from visualizer section 21)
    erp-client/                        # typed client for the Frappe endpoints
  app/                                 # the portal SPA (routes, stores, screens)
  tests/                               # Vitest + Playwright
illumenate_lighting/public/system_designer/   # committed build output (bench build serves it)
illumenate_lighting/templates/pages/system_design.html|py   # mounts the SPA with CSRF + context
illumenate_lighting/illumenate_lighting/system_design/       # Python package (new domain module)
  catalog.py          # Design Catalog generation
  designs.py          # load/save/revise designs, schedule reconcile
  verify.py           # server-side verification (Python mirror of critical checks)
  writeback.py        # schedule line write-back
  outputs.py          # package assembly, file storage, review hooks
  share.py            # signed share links
```

The new Python package keeps this work out of `portal.py` (consistent with the portal plan's domain-consolidation phase).

### 15.3 Frontend stack

- React 19 + strict TypeScript + Vite (align `tools/configurator_ui` later; the Finder is on React 18/Vite 6 today).
- Zustand + immer + zundo (undo/redo), Zod, Tailwind (brand tokens from the visualizer's `DS`), Radix primitives, AG Grid Community for engineering tables, lucide icons.
- Three.js current release as an ES module (replacing r128 UMD).
- `@cantoo/pdf-lib` + fontkit for PDFs, JSZip for bundles.
- Web Workers for layout, auto-plan and PDF generation.
- **Bundle budget:** initial route < 400 KB gzipped; riser layout, PDF/DXF, AG Grid and Three.js load on demand (the riser repo already lazy-loads heavy modules).

### 15.4 The Design Catalog adapter (ERP → designer)

The key integration piece.

- A Python function builds catalog items in the engine's `CatalogItem` shape from the spec doctypes:
  - `ilL-Spec-LED Tape` × active `ilL-Rel-Tape Offering` → `tape` items (one per offering where W/ft or cut increment differ; otherwise per spec).
  - `ilL-Spec-Driver` → `psu` (CV) or `driver` (CC).
  - `ilL-Spec-Controller` → `decoder` / `controller` by type mapping.
  - `ilL-Spec-Wire` → wire library entries.
  - Configured fixture templates → metadata (diagram icon, profile cross-section, names) used by presentation and 3D.
- Units converted (mm → in/ft), protocol names mapped to the engine enum (Appendix B), every item tagged with ERP doctype, name and `modified` timestamp (provenance).
- Items missing required fields are emitted as `incomplete` with `missingFields`, never dropped silently.
- **No cost fields** are ever serialized (driver `cost` is used server-side only for auto-plan ranking, applied as an opaque rank).
- The snapshot is content-hashed (SHA-256 of canonical JSON) and cached (Redis + a stored `ilL-Design-Catalog-Snapshot` per hash). Designs record the hash they were calculated with. Opening an old revision can load its exact snapshot.
- The same adapter can serve the standalone riser repo (section 19.1) through an authenticated endpoint, replacing its `custom_riser_specs` mapping.

### 15.5 Persistence

- Server is the system of record: `ilL-System-Design` (section 16).
- Client keeps an IndexedDB draft (Dexie, as in the riser repo) for crash recovery and offline edits; it syncs on save with optimistic concurrency (`modified` / revision number). Conflicts show a merge dialog (most edits are independent assignments).
- Autosave every 5 s while editing (debounced), explicit "Save revision" for frozen revisions.
- Large outputs (PDF, DXF, video) are generated client-side and uploaded as private files; the server stores SHA-256 and links them to the revision. A server-side re-render path exists for staff (section 15.7).

### 15.6 Security and permissions

- Mount page requires a logged-in portal user with access to the schedule (single permission function shared with the schedule page; fix P0.2 first).
- All endpoints check schedule/project access and the user's role (dealer designer, dealer read-only, staff reviewer).
- No pricing in designer payloads unless the user has "Can View Pricing"; never costs.
- Uploaded floor plans and generated files are private (`private_storage.py` pattern).
- Share links: HMAC-signed tokens with audience, design revision and expiry; revocable; access logged as `ilL-Portal-Event`.
- Server re-validates design JSON against the JSON Schema exported from Zod, with size limits (e.g. 5 MB) and a maximum run count.
- Escape every server string in the UI (React does this by default; ban `dangerouslySetInnerHTML` by lint rule).

### 15.7 Server-side rendering

Some outputs must be generated without a browser: package regeneration by staff, the quote PDF's system page, scheduled re-issue. Options:

1. **Client-only generation** (v1): the browser generates and uploads; staff use their browser.
2. **Headless render worker** (later): a small Node service (or Frappe Cloud background worker with Node available) runs the same packages to render PDF/DXF/PNG. Verify Frappe Cloud support before committing; fall back to a separate container if needed.

Start with option 1; design the packages to be environment-neutral (no DOM in engine, drawing, serializers, present SVG output) so option 2 is a deployment, not a rewrite.

### 15.8 Performance budgets

| Operation | Budget |
|---|---|
| Open design (150 lines, cached catalog) | < 3 s to interactive |
| Engine recalculation (300 runs) | < 150 ms (worker) |
| Riser layout (200 loads) | < 2 s (proven in the riser repo) |
| Auto-plan (60 runs) | < 2 s |
| 3D scene build (5 spaces, 40 runs) | < 1.5 s, 60 fps orbit on a mid laptop |
| Package generation (20 sheets + guides) | < 30 s with progress |

---

## 16. Data model in ERPNext

### 16.1 New doctypes

**`ilL-System-Design`** (submittable-like lifecycle via status, not Frappe submit)

| Field | Type | Notes |
|---|---|---|
| `fixture_schedule` | Link → ilL-Project-Fixture-Schedule | required |
| `schedule_version` | Int | version the design was built on |
| `ill_project` | Link → ilL-Project | denormalized for permissions/listing |
| `customer` | Link → Customer | owner customer |
| `title` | Data | |
| `status` | Select | Draft, In Review, Changes Requested, Approved, Issued, Superseded |
| `revision` | Data | A, B, C… |
| `revision_parent` | Link → ilL-System-Design | previous revision |
| `design_json` | Long Text (JSON) | the design document (site, runs, equipment, sources, links, settings, layout pins, views) |
| `design_schema_version` | Int | |
| `engine_version` | Data | |
| `catalog_snapshot` | Link → ilL-Design-Catalog-Snapshot | |
| `line_fingerprint_json` | Long Text | per-line hashes for reconcile |
| `result_summary_json` | Long Text | totals, check counts by severity (for lists) |
| `build_hash` | Data | SHA-256 of canonical inputs + engine version + snapshot hash |
| `error_count`, `warning_count` | Int | for list filters and gating |
| `review_request` | Link → ilL-Document-Request | |
| `approved_review` | Link → ilL-Drawing-Review | |
| `deliverables` | Table → ilL-Child-Design-Deliverable | kind (riser PDF, DXF ZIP, presentation PNG, package PDF, guide, labels, video), file, SHA-256, created |
| `share_links` | Table → ilL-Child-Design-Share | audience, token hash, expires, revoked |
| `collaborators` | inherits project/schedule collaborators | |

**`ilL-Design-Catalog-Snapshot`**: `snapshot_hash` (unique), `generated_on`, `engine_contract_version`, `catalog_json` (compressed), `item_count`, `incomplete_count`.

**`ilL-Spec-Wire`** (section 3.6) with child **`ilL-Child-Wire-Conductor`**.

**`ilL-Training-Visual`** (section 13.2): `visual_id`, `section`, `title`, `subtitle`, `captions_json`, product bindings, `is_published`.

**Request type seed:** `System Design Review` for `ilL-Document-Request`.

### 16.2 Field additions to existing doctypes

- `ilL-Spec-LED Tape`, `ilL-Spec-Driver`, `ilL-Spec-Controller`, `ilL-Spec-Profile`, `ilL-Spec-Lens`, `ilL-Spec-Accessory`, `ilL-Attribute-Output Voltage`: fields listed in section 3 / Appendix A.
- `ilL-Child-Fixture-Schedule-Line`: `watts_each`, `input_voltage_v`, `voltage_class` (third-party lines); `system_design` (Link, for lines written back by a design); `design_line_role` (supply, controller, wire, accessory).
- `ilL-Fixture-Template` / `ilL-Tape-Neon-Template`: `diagram_icon` (Attach, SVG), `scene_archetypes` (which 3D archetypes it can appear in).
- `Customer`: `dealer_logo` (Attach) for title blocks.

All via patches with defaults so existing records stay valid.

### 16.3 Design JSON shape (summary)

The riser `Project` schema extended with:

- `schedule`: name, version, line fingerprints.
- `site`: spaces, levels, cabinets, panels, floor plans (file refs + calibration), placed symbols and wire paths.
- `runs`: run records keyed by `run_key` with source (ERP line/build/run), site placement, environment, home-run length + provenance (estimated / entered / measured on plan).
- `equipment`, `sources`, `controlLinks`, `loads` (generated from runs but stored for engine determinism), `wireOverrides`, `layoutOverrides`.
- `zones`: dimming zones with method, color, scenes (optional).
- `views`: saved 3D views, presentation variant settings, riser sheet settings.
- `overrides`: acknowledged warnings and staff overrides with reasons.

Zod remains the source of truth; a JSON Schema is exported at build time and committed for server-side validation (Python `jsonschema`).

---

## 17. API surface

All under `illumenate_lighting.illumenate_lighting.system_design.*`, whitelisted, POST for writes, uniform `{success, data | error}` contract (portal plan §6.5).

| Endpoint | Purpose |
|---|---|
| `designs.find_schedule(query)` | Search accessible schedules by number or project name |
| `designs.open(schedule, design=None)` | Schedule, lines, configured builds (runs, segments, cable manifest, power plan), existing design, catalog snapshot hash, readiness, permissions |
| `catalog.get(snapshot_hash)` | Design Catalog snapshot (cached, ETag) |
| `catalog.eligible_supplies(run_keys \| templates, voltage, protocol)` | Driver eligibility for a set of runs (no costs) |
| `designs.save(design, design_json, expected_modified)` | Autosave draft (schema-validated, concurrency-checked) |
| `designs.create_revision(design, note)` | Freeze a revision |
| `designs.reconcile(design)` | Diff against current schedule version |
| `designs.copy_to_version(design, schedule_version)` | Carry a design forward |
| `verify.run(design)` | Server-side verification of critical checks; stores summary |
| `planner.auto_plan(design, policy)` | Server-side site allocator (mirror of the client one; used for verification and very large designs) |
| `writeback.preview(design)` / `writeback.apply(design, accepted)` | Schedule line diff and apply |
| `outputs.upload(design, kind, file, sha256)` | Store a generated deliverable |
| `outputs.package(design)` | Assemble the package (merge PDFs incl. spec submittals) |
| `review.request(design, priority, due, note)` | Create the review request |
| `review.decide(design, decision, note)` | Staff decision → `ilL-Drawing-Review` |
| `review.comments(design)` / `review.add_comment(...)` | Pinned comments |
| `share.create(design, audience, expires)` / `share.revoke(token_id)` / `share.open(token)` | Share links |
| `floorplan.upload(design, file)` | Private floor plan upload; returns rendered page images |
| `training.list()` / `training.get(visual_id)` | Training visual config |

---

## 18. Consolidating the calculation engines

### 18.1 Two engines exist today

- **Python (ERP):** build math (segments, cut lengths, runs, run watts), 85 W rule, per-build `plan_power`, driver eligibility. It decides what gets manufactured and sold.
- **TypeScript (riser):** site electrical math (VD, wire selection, breakers, DMX, CV/CC, Class 2), tested and fast in the browser.

### 18.2 Ownership rule

| Concern | Owner | The other side |
|---|---|---|
| Build geometry, cut lengths, run split, run watts, factory leaders | ERP (Python) | Designer reads, never recomputes |
| Max run per build (configurator) | ERP | Designer re-checks for site-combined runs only |
| Driver eligibility (which supplies may feed which templates) | ERP | Designer filters by it |
| Per-build supply suggestion | ERP `plan_power` | Designer uses as default |
| Site supply allocation, consolidation | Designer engine (TS) | Python mirror verifies |
| Voltage drop, wire selection, breaker load, Class 2, DMX, compatibility | Designer engine (TS) | Python mirror verifies the subset that gates review/orders |
| Pricing | ERP | Designer displays only |

### 18.3 Parity and verification

- A shared folder of **golden fixtures** (design JSON + catalog snapshot → expected results), seeded from the riser repo's `examples/engineering-results.json` and new residential cases (the visualizer's cove/under-cabinet/toe-kick/shelf/niche set).
- TypeScript runs them in Vitest; Python runs the critical subset in the bench test suite. CI fails on divergence.
- The Python mirror covers: supply/output loading and derate, Class 2, max run, VD with Table 8 resistance and wire selection for Class 2 DC runs, protocol/voltage match. Everything else is computed client-side and recorded with the engine version.
- Version the engine (`engine_version` already exists on configured records; the designer gets its own). Changing a rule bumps the version; old revisions remain reproducible because the engine package for each version is kept in the bundle manifest (or the result is stored and only re-verified on demand).

### 18.4 Rule alignment work items

- Replace the configurator's fixed 85 W per-run rule with spec-driven limits (`max_run_single_feed_ft`, supply output limits) once the tape fields exist, so the configurator and designer agree. Keep 85 W as a staff-configurable fallback.
- Align derate: engine `psuDeratePct` defaults to each driver's `usable_load_factor`.
- Align protocol vocabulary (Appendix B) in one shared table used by Python and TypeScript.

---

## 19. What happens to each proof of concept

### 19.1 Riser Diagram Generator

| Part | Fate |
|---|---|
| `src/schemas` | Moves to `packages/core-schemas`; extended for site, runs, zones, views |
| `src/engine` | Moves to `packages/engine`; add site allocator, thermal and placement checks; keep 100% purity and coverage rules |
| `src/drawing`, `src/serializers` | Move largely unchanged; add Letter/Tabloid sheets, dealer logo slot, ERP schedules |
| `src/features/tables`, `library`, `review`, `drawing`, `export` | Become the Engineering mode screens (adapted to server persistence) |
| `src/features/erp`, `server/proxy.mjs` | Retired; replaced by the Design Catalog endpoint |
| `src/storage` (Dexie) | Kept for drafts/offline only |
| `src/data` NEC tables | Kept as cited, versioned reference data |
| `wires.seed.json`, `products.example.json` | Wires → seed for `ilL-Spec-Wire` after review; example products → test fixtures only |

**Repository strategy:** import the riser source into this repo with history (`git subtree add`) under `tools/system_designer/packages/*`, then develop here. Keep the standalone riser repo for one release as the engineering desktop tool, pointed at the new authenticated catalog endpoint, then archive it. (Decision D1, section 22.3.)

### 19.2 LED Tape System Visualizer

| Part | Fate |
|---|---|
| Brand tokens, fonts, logo (`DS`, `BRAND`, brand assets) | `packages/present/brand` and Tailwind theme; shared by all presentation output |
| Geometry builders (architecture, LED assembly, power, wiring) | `packages/scene3d` modules; architecture becomes parameterized archetypes; LED assembly reads ERP cross-sections |
| Orbit rig, materials, lighting, exploded/section | `packages/scene3d/core` (ported to current Three.js; or adopt the maintained OrbitControls) |
| Labels/callouts/dimension overlay | `packages/scene3d/overlay` (shared with plan view) |
| Flat system diagram (section 14) | Superseded by the presentation diagram renderer |
| Training visuals (sections 19, 20) | `packages/present/training`, data bound to ERP |
| Install guide (section 21) | `packages/guides`, data bound to ERP + design |
| Hard-coded data (`ZONES`, `PROFILES`, `EXAMPLE`, `JOB`, `CAD_SH01`, `PARTS`) | Removed; replaced by ERP catalog + design; `CAD_SH01` becomes the first `cross_section_json` (for profile SH01) |

**Three.js r128 → current:** cdnjs's three.js package stops at r128 (UMD); current releases ship as ES modules only. Expect changes in: `outputEncoding` → `outputColorSpace`, physically correct lights by default (light intensities need retuning), `Geometry` already absent in r128 (no impact), PMREM API minor changes, `InstancedMesh` unchanged. Budget a week for the port with visual regression snapshots.

### 19.3 The schedule page and configurators

No rewrite. Add the "Design system" button, a "Designed" badge, and the line write-back markers. The configurators keep producing builds; the designer consumes them.

---

## 20. Phased roadmap

Sizes are relative effort for one full-stack developer with domain support (S ≈ 1 week, M ≈ 2–3 weeks, L ≈ 4–6 weeks). Phases 0 and 1 can overlap.

### Phase 0 — Foundations and prerequisites (M)

- Fix portal P0 permission defects that touch schedules, document requests and drawing requests (portal plan Phase 1 items P0.1–P0.4, P0.6).
- Create the `system_design` Python package skeleton and uniform error contract.
- Set up `tools/system_designer` workspace, build to `public/system_designer`, mount page with CSRF, CI (lint, typecheck, Vitest, Playwright, "committed bundle matches build" check like the Finder).
- Import riser source with history; get its test suite green in the new workspace.
- **Exit:** empty designer opens from a schedule for authorized users only; riser tests pass in CI.

### Phase 1 — ERP data readiness (M, mostly catalog work)

- Add design fields to tape, driver, controller, profile, lens, accessory, voltage attribute, schedule line (patches with defaults).
- Create `ilL-Spec-Wire`; seed reviewed wire types; ship NEC tables.
- Design readiness report in Catalog Builder.
- Fill fields for the products dealers use most (target: the top 20 tapes/offerings, all active drivers, the dimmers/decoders on the price list).
- **Exit:** readiness report shows ≥ 90% of schedule-line volume (last 6 months) design-ready.

### Phase 2 — Design Catalog and intake (M)

- Design Catalog adapter, snapshot storage, caching, protocol/unit mapping, golden tests.
- `designs.open`, run expansion (lines × qty × runs), readiness screen, schedule reconcile.
- `ilL-System-Design` doctype, save/autosave, revisions.
- **Exit:** a real schedule opens with every run listed, ERP lengths/watts shown, and incomplete items named.

### Phase 3 — Power assignment, checks, engineering riser (L) — **first dealer release (beta)**

- Spaces and cabinets (entered distances), run editor, power board with drag-and-drop, eligible supply picker, configurator power plans as defaults.
- Sources/circuits, zones and dimming method, phase-cut and 0-10V controls (DMX in Phase 5).
- Live engine checks with fix actions; VD and wire gauge per run; wire takeoff.
- Engineering riser PDF/DXF/SVG with ERP schedules, title block with dealer logo, stamps.
- Python verification for critical checks; golden parity tests.
- **Exit:** 5 pilot dealers complete real projects; riser accepted by their electricians; zero cost-data exposure in a security review.

### Phase 4 — Commerce loop and review (M)

- Schedule write-back (supplies, controllers, wire, accessories) with diff; consolidation replacing per-build supply lines.
- System Design Review request type, reviewer mode, pinned comments, approval → `ilL-Drawing-Review` with build hash; stamped outputs; optional review gating before Sales Order.
- **Exit:** a design-driven schedule converts to a Sales Order whose supply/wire lines match the design exactly.

### Phase 5 — Presentation diagram, labels, DMX and advanced controls (M)

- Presentation diagram (three variants), labels with QR, DMX zones (decoders, patching, termination), Lutron/DALI devices, auto-plan (site allocator) with policy options.
- **Exit:** sales pilot uses presentation output in proposals; DMX designs pass engine checks and render on the riser.

### Phase 6 — 3D project view and plan view (L)

- `scene3d` port to current Three.js; archetypes from runs; ERP cross-sections; supplies and wire routing; exports and video.
- Floor plan upload, calibration, placement, measured wire paths feeding the engine; plan sheet output.
- **Exit:** a cove + kitchen project renders in 3D from real data with supply locations; plan-measured distances replace estimates.

### Phase 7 — Install guides, training library, documentation package, sharing (M)

- Guide generator per space (field-built and factory-built paths), video and printable output.
- Training visuals library bound to ERP data and contextual help links.
- Documentation package (merged PDF + ZIP incl. spec submittals), signed share links per audience.
- **Exit:** a full package for a pilot project is produced in one click and shared with homeowner and installer links.

### Phase 8 — Hardening and scale (ongoing)

- Server-side render worker (if Frappe Cloud allows), performance at 500+ runs, accessibility (WCAG 2.2 AA for the app shell), localization of units (metric), analytics, retire the standalone riser repo.

### Milestone summary

| Milestone | After phase | Dealer value |
|---|---|---|
| M1 Data ready | 1 | — (internal) |
| M2 Open any schedule as a design | 2 | See runs and readiness |
| M3 **Beta: power plan + checked riser** | 3 | The main ask: link supplies, check, riser |
| M4 Quote matches design; ilLumenate review | 4 | Fewer errors, stamped drawings |
| M5 Sell it: presentation + labels + DMX | 5 | Proposals and complex control |
| M6 See it: 3D + plan | 6 | Visual project, supply locations, routing |
| M7 Build it: guides + package + sharing | 7 | Complete documentation |

---

## 21. Testing, quality and acceptance

### 21.1 Automated

- **Engine:** keep the riser rule — every calculation and validation branch unit-tested; coverage gates (lines ≥ 95% for engine).
- **Golden parity:** TS and Python run the same fixtures (section 18.3).
- **Adapter:** Python unit tests for every spec → catalog mapping, unit conversion, protocol mapping, incomplete detection; a test that no cost field appears in any payload.
- **Schemas:** round-trip and migration tests for `design_json` versions.
- **Drawing/serializers:** existing riser tests (collisions, separation, continuations, pagination, DXF round trip with `dxf-parser`, PDF structure); add snapshot tests for presentation SVG and 3D (headless WebGL screenshots with tolerance).
- **API:** permission matrix tests (dealer A cannot open dealer B's schedule/design/share), concurrency, schema rejection, size limits (extend `test_portal_access_matrix.py`).
- **E2E (Playwright):** open schedule → assign → fix a check → export riser → request review → approve → write back → Sales Order.

### 21.2 Manual and field

- AutoCAD import of DXF (AUDIT 0 errors) per sheet size, as the riser acceptance report does.
- Electrician review of 5 pilot risers.
- Engineering spot-check: 10 designs recalculated by hand (load, VD, gauge).
- Visual QA of presentation and 3D on brand guidelines.

### 21.3 Definition of done per output

Every output must: carry design ID, revision, engine version, snapshot hash, build hash; render identically from the same inputs; show the correct stamp; contain no prices unless permitted.

---

## 22. Risks, liability and open decisions

### 22.1 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Catalog data incomplete | Designer shows many `incomplete` items; low adoption | Phase 1 before dealer release; readiness report; prioritize by sales volume |
| Engine disagreement (configurator vs designer) | Dealer confusion, wrong supplies | Ownership rule (18.2), golden parity tests, align 85 W rule |
| Liability for engineering advice | Legal exposure | Stamps and disclaimers; line voltage "by licensed electrician"; staff review as the only path to "Reviewed" outputs; record code edition; terms of use acceptance on first open |
| Scope creep into CAD | Delays | 3D is representative; plan view is overlay-only; no wall editing in v1 |
| Frappe Cloud constraints (no Node at runtime) | No server rendering | Client-side generation first; render worker later (15.7) |
| Bundle size/performance on dealer laptops | Slow UX | Lazy loading, workers, budgets (15.8) |
| Portal security debt | Data leaks | Phase 0 fixes; permission tests; single access function |
| Three.js port regressions | Visual bugs | Snapshot tests; port in isolation before binding data |
| Dealers bypass the tool and order without design | Lower value | Make write-back the easiest way to add supplies; review gating policy for larger jobs |

### 22.2 Legal and safety content

- Every engineering output: "Design aid. Verify against product documentation and local code. Line-voltage work by a licensed electrician." The riser repo already has stamp options; keep `NOT FOR CONSTRUCTION` as the default until ilLumenate review approves.
- Record NEC edition and VD targets on each sheet.
- Never print a UL listing claim the product's certification table doesn't support.

### 22.3 Decisions needed from you

| # | Decision | Recommendation |
|---|---|---|
| D1 | Keep the standalone riser repo after migration? | Keep one release pointed at ERP, then archive |
| D2 | Product name | "ilLumenate System Designer" (portal: "Design system") |
| D3 | Who may approve designs (role) | New role "Applications Engineer" |
| D4 | Review gating before Sales Order | Required for DMX, line-voltage dimming, or > 1.5 kW; optional otherwise |
| D5 | Default VD target for Class 2 runs | 3% (matches riser default and visualizer guidance) |
| D6 | Do dealers see auto-plan cost ranking? | No; rank silently, show supply count and wire totals only |
| D7 | Wire types as quotable Items | Yes; adds revenue and makes the BOM complete |
| D8 | Third-party fixtures on risers | Allowed with dealer-entered data, flagged "data by dealer" |
| D9 | 3D archetype priority after cove | Under-cabinet, toe-kick, shelving, niche (already modelled), then ceiling reveal and stair |
| D10 | Share link default expiry | 90 days, renewable |
| D11 | Metric support | Phase 8 (engine already supports `units: m`) |
| D12 | Webflow/public use of presentation diagram | Later; portal-only first |

---

## 23. Success metrics

| Metric | Target (6 months after beta) |
|---|---|
| Share of quoted schedules with a design | ≥ 40% of schedules over $5k |
| Supply-related order changes after Sales Order | −50% vs baseline |
| Factory calls/tickets about power/wiring | −40% |
| Median time from schedule to checked riser | < 30 min |
| Designs approved on first review | ≥ 70% |
| Dealer satisfaction (in-app survey) | ≥ 4.3 / 5 |
| Average supplies per kW (consolidation) | −15% vs per-build planning |
| Attach rate of wire/control lines on designed schedules | ≥ 60% |

---

## 24. Appendices

### Appendix A — Field mapping: ERP → engine catalog

**A.1 Tape (`kind: 'tape'`)**

| Engine | ERP source | Transform |
|---|---|---|
| `id` | `tape:{spec}:{offering}` | — |
| `sku` / `erpItemCode` | `ilL-Spec-LED Tape.item` (offering-level Item when present) | — |
| `voltage` | `input_voltage` → `ilL-Attribute-Output Voltage.nominal_voltage_v` (new) | must be 12/24/48 else `incomplete` |
| `drive` | `drive_type` (new) | CV / CV-CC-IC |
| `wPerFtMax` | offering `watts_per_ft_override` ‖ spec `watts_per_foot` | — |
| `powerBasis` / `maxSimultaneousPct` | new fields | defaults |
| `channels` / `channelMap` / `channelWPerFtMax` | new channel table; default from LED package | — |
| `maxRunFtSingleFeed` | `max_run_single_feed_ft` (new) ‖ `voltage_drop_max_run_length_ft` | — |
| `maxRunFtDoubleFeed` | `max_run_double_feed_ft` (new) | else `incomplete` |
| `freeCutting` / `cutIntervalIn` | `is_free_cutting` / offering `cut_increment_mm_override` ‖ `cut_increment_mm` | mm ÷ 25.4 |
| `minOperatingV` | `min_operating_voltage_v` (new) | — |
| `reelLengthFt` | `reel_length_m` (new) | m × 3.2808 |
| `pixel` | new pixel section | — |
| (visual) | `led_pitch_mm`, `tape_width_mm`, `leds_per_segment`, `lumens_per_foot`, CCT/CRI from offering | presentation/3D only |

**A.2 Supply / driver (`kind: 'psu' | 'driver'`)**

| Engine | ERP source |
|---|---|
| `inputType`, `inputVMin`, `inputVMax` | `input_voltage_type`, `input_voltage_min`, `input_voltage_max` |
| `inputPhase` | `input_phase` (new) |
| `outputType` | `output_type` (CV→psu, CC→driver) |
| `outputV` | `voltage_output` → attribute `nominal_voltage_v` |
| `outputmA`, `outputVMin/Max` | `output_current_ma`, `compliance_v_min/max` (new) |
| `ratedW` | `max_wattage` |
| `outputs[]` | `independent_outputs_count` × `{maxW: max_wattage_per_output, class2: class2_outputs}` |
| `efficiency`, `powerFactor` | new |
| `maxInputA`, `maxInputAAtV`, `inrushA`, `maxUnitsPer20ABreaker` | new |
| `dimming[]` | `input_protocols` → protocol map |
| `terminalMinAwg/MaxAwg` | new |
| `listings[]` | `certifications` |
| derate | `usable_load_factor` |

**A.3 Controls (`kind: 'decoder' | 'controller'`)**

| Engine | ERP source |
|---|---|
| category | `controller_type` → map (A.5) |
| `channels`, `maxAPerChannel`, `maxATotal`, `maxWPerChannel`, `maxWTotal` | `channels`, new per-channel fields, `max_load_amps`, `max_load_watts` |
| `dmxFootprint`, `unitLoad`, `dmxThru` | new |
| `protocolIn/Out`, `ports[]` | `input_protocols`, `output_protocols`, new ports table |
| `powerType`, `outputDimming` | `input_voltage_type`, `output_dimming` (new) |
| `ownPowerW` | `standby_power_watts` |
| dimmer limits | `min_load_w`, `led_max_w`, `max_supplies`, `neutral_required` (new) |

**A.4 Schedule line → design run**

| Design | Source |
|---|---|
| `run_key` | `{line_key}:{build_index}:{run_index}` |
| type tag | `line_id` |
| space | `location` (mapped to a space) |
| electrical item | configured record `tape_offering` / `tape_spec` |
| length | `ilL-Child-Configured-Run.run_len_mm` (linear) or segment/run plan (tape/neon) |
| watts | `run_watts` |
| feeds | segment `start/end_power_feed_type`, `power_feed_type` attribute (`connection_type`, `directionality`) |
| factory leader | `cable_manifest_json` entry for the run |
| environment | `environment_rating` (default), overridable |
| default supply | `power_plan_json.allocations` for that run |

**A.5 Controller type → engine category**

`ilL-Spec-Controller.controller_type` today offers: DMX Controller, Wireless Receiver, Wall Dimmer, Scene Controller, Sensor, Gateway, Repeater. That is too coarse for the engine, which needs decoders, converters and dimmer types to be distinct.

| `controller_type` (ERP) | Engine category | Action |
|---|---|---|
| DMX Controller | `dmx-controller` | — |
| Wireless Receiver | `wireless-rx` | — |
| Wall Dimmer | `phase-dimmer` (new engine category) or `0-10v-dimmer` | Split by `output_dimming` (phase-forward / phase-reverse / 0-10V) |
| Scene Controller | `keypad` | — |
| Gateway | `sacn-gateway` | — |
| Repeater | `opto-splitter` | Confirm intent |
| Sensor | not modelled | Add an engine `sensor` category later, or draw as a control-only device |
| *(missing)* DMX Decoder | `dmx-decoder` | Add option |
| *(missing)* DMX to 0-10V Converter | `dmx-0-10v-converter` | Add option |
| *(missing)* Pixel Controller | `pixel-controller` | Add option |
| *(missing)* Wireless Transmitter | `wireless-tx` | Add option |
| *(missing)* Relay, Lutron Module | `relay`, `lutron-module` | Add options |

Add the missing options and the `phase-dimmer` engine category in Phase 1.

### Appendix B — Protocol vocabulary

One shared mapping table (Python and TS) from `ilL-Attribute-Dimming Protocol` names to the engine enum: `none`, `phase-forward` (TRIAC, leading edge), `phase-reverse` (ELV, trailing edge), `0-10V`, `1-10V`, `DALI-2`, `DMX512`, `RDM`, `sACN`, `Art-Net`, `CRMX-wireless`, `Lutron-QS`, `Lutron-EcoSystem`, `PWM`, `SPI`. Unmapped ERP values make the item `incomplete` with "unmapped protocol: X," never a silent default.

### Appendix C — Validation codes added by the designer

| Code | Meaning |
|---|---|
| `PROFILE_THERMAL_LIMIT` | Tape W/ft above the profile's thermal limit |
| `SUPPLY_LOCATION_RATING` | Supply rated dry placed in a damp/wet location |
| `SUPPLY_NO_ACCESS` | Supply location has no service access marked |
| `CABINET_HEAT` | Enclosed cabinet heat above guideline |
| `DIMMER_MIN_LOAD` / `DIMMER_LED_MAX` / `DIMMER_SUPPLY_COUNT` / `DIMMER_NEUTRAL` | Phase dimmer limits |
| `SCHEDULE_OUT_OF_SYNC` | Design built on an older schedule version |
| `CONFIG_PLAN_REPLACED` | Configurator supply lines superseded by the design (info) |
| `DATA_BY_DEALER` | Third-party product data entered by the dealer (info, printed) |

### Appendix D — Key source references

**ERP (this repo):** `illumenate_lighting/illumenate_lighting/api/power_planner.py`, `tape_neon_power.py`, `linear_power.py`, `driver_catalog.py`, `power_supply_lines.py`, `linear_build.py` (`cable_manifest`), `configurator_engine.py` (max run rules), `spec_submittal.py`, `document_requests.py`, `portal.py` (schedule endpoints), `doctype/ill_project_fixture_schedule`, `doctype/ill_child_fixture_schedule_line`, `doctype/ill_configured_fixture`, `doctype/ill_configured_tape_neon`, `doctype/ill_spec_*`, `doctype/ill_drawing_review`, `doctype/ill_line_document`, `tools/configurator_ui` (bundle pattern), `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md`, `docs/MVP_CONSTRAINTS.md`.

**Riser repo:** `src/schemas/{project,catalog,wire,common,library}.ts`, `src/engine/{calculate,loads,voltageDrop,wireSelect,dmx,bom,graph}.ts`, `src/drawing/` (layout, symbols, sheet), `src/serializers/{svg,pdf,dxf}`, `src/features/erp/sync.ts`, `server/proxy.mjs`, `src/data/nec/*.json`, `docs/acceptance-report.md`, `docs/drawing-revision-1.1.md`.

**Visualizer (single HTML file):** sections 0 (brand), 1–1d (data to be replaced by ERP), 7–10 (3D builders), 11 (labels overlay), 13 (exploded/section), 14 (schematic), 17 (export), 19–20 (training visuals), 21 (install guide, `CAD_SH01`).

### Appendix E — Glossary

- **Run:** a continuous electrically connected length of tape or a fixture's internal circuit, fed by one supply output.
- **Feed:** a point where power enters a run (end, both ends, center, injection).
- **Home run:** the field wire from a supply output to a run's feed (or from a junction to the factory leader).
- **Cabinet / enclosure:** a named location holding supplies and controls.
- **Design Catalog:** the versioned, engine-shaped product snapshot generated from ERP specs.
- **Build hash:** SHA-256 of a design's canonical inputs, engine version and catalog snapshot; proves an output is unchanged.
- **Archetype:** a parameterized 3D scene kit for a common application (cove, under-cabinet…).
