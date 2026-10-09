# ilLumenate System Designer — Product Plan and Implementation Handbook

**Product:** ilLumenate System Designer (portal button and menu label: **"Design system"**)
**Status:** Approved for implementation · Decisions D1–D12 final (section 22) · Revised 2026-10-06
**Audience:** Kevin (owner), ilLumenate staff, and the agent that will implement it.

**Inputs investigated:**

1. This repository: the ERPNext app and Dealer Portal (`illumenate_lighting/`).
2. `kevinschern-illumenate/riser-diagram-generator` v1.2.0 (React + TypeScript; inspected at its `main` HEAD).
3. The single-file **LED Tape System Visualizer** (Three.js r128; 3D model, system diagram, training visuals, install guide), supplied in chat. **It is not in any repository yet; work package WP-0.4 commits it.**

**How this document is organized**

- **Part I — Product plan (sections 0–23):** what exists, what we are building, why, and the decisions.
- **Part II — Implementation handbook (sections H1–H12):** rules for the implementing agent, repository conventions, exact data specs, contracts, algorithms, and a numbered work-package list with files, steps, tests and acceptance criteria.
- **Appendices A–E:** field mappings, vocabularies, validation codes, references, glossary.

> **Implementing agent: read section H1 first, then Part I sections 0, 5, 15, 16, 18 and 22, then the work package you are assigned.** Do not start a work package whose dependencies are not merged.

---

## Contents

**Part I — Product plan**

0. [Executive summary](#0-executive-summary)
1. [What exists today](#1-what-exists-today)
2. [The core problem: three copies of the product data](#2-the-core-problem-three-copies-of-the-product-data)
3. [Gap analysis: what ERPNext must hold](#3-gap-analysis-what-erpnext-must-hold)
4. [Product vision, users and jobs](#4-product-vision-users-and-jobs)
5. [Product principles](#5-product-principles)
6. [The end-to-end workflow](#6-the-end-to-end-workflow)
7. [Module 1 — Project and schedule intake](#7-module-1--project-and-schedule-intake)
8. [Module 2 — Site model](#8-module-2--site-model)
9. [Module 3 — Run builder](#9-module-3--run-builder)
10. [Module 4 — Power and control assignment](#10-module-4--power-and-control-assignment)
11. [Module 5 — Engineering checks and recommendations](#11-module-5--engineering-checks-and-recommendations)
12. [Module 6 — Outputs: riser, presentation, plan view, 3D](#12-module-6--outputs-riser-presentation-plan-view-3d)
13. [Module 7 — Install guides, training, labels](#13-module-7--install-guides-training-labels)
14. [Module 8 — Package, review, sharing, commerce](#14-module-8--package-review-sharing-commerce)
15. [Architecture](#15-architecture)
16. [Data model in ERPNext](#16-data-model-in-erpnext)
17. [API surface](#17-api-surface)
18. [Consolidating the calculation engines](#18-consolidating-the-calculation-engines)
19. [What happens to each proof of concept](#19-what-happens-to-each-proof-of-concept)
20. [Phased roadmap](#20-phased-roadmap)
21. [Testing, quality and acceptance](#21-testing-quality-and-acceptance)
22. [Decisions (final), risks and liability](#22-decisions-final-risks-and-liability)
23. [Success metrics](#23-success-metrics)

**Part II — Implementation handbook**

- [H1. Rules for the implementing agent](#h1-rules-for-the-implementing-agent)
- [H2. Repository conventions you must follow](#h2-repository-conventions-you-must-follow)
- [H3. Target file tree](#h3-target-file-tree)
- [H4. DocType specifications](#h4-doctype-specifications)
- [H5. Design document schema (TypeScript / Zod)](#h5-design-document-schema-typescript--zod)
- [H6. API contracts](#h6-api-contracts)
- [H7. Design Catalog adapter specification](#h7-design-catalog-adapter-specification)
- [H8. Algorithms](#h8-algorithms)
- [H9. UI specification](#h9-ui-specification)
- [H10. Golden fixtures and parity tests](#h10-golden-fixtures-and-parity-tests)
- [H11. Work packages](#h11-work-packages)
- [H12. Pull-request sequence and review checklist](#h12-pull-request-sequence-and-review-checklist)

**Appendices:** [A. Field mappings](#appendix-a--field-mapping-erp--engine-catalog) · [B. Protocol vocabulary](#appendix-b--protocol-vocabulary) · [C. Validation codes](#appendix-c--validation-codes) · [D. Source references](#appendix-d--source-references) · [E. Glossary](#appendix-e--glossary)

---

# Part I — Product plan

## 0. Executive summary

**The opportunity.** You already have the three hard parts, built separately:

| Asset | What it does well | What holds it back |
|---|---|---|
| **ERPNext Dealer Portal** | Projects, fixture schedules, configured builds (segments, runs, run watts, cut lengths, leader/jumper cables), an exact power-supply allocator, driver eligibility, spec submittals, document requests with drawing review, dealer permissions, quotes and Sales Orders. | No system-level view. Power is planned per build, never across a site. No riser, no wiring, no visuals. |
| **Riser Diagram Generator** | A pure, tested electrical engine (graph, loads, CV/CC checks, voltage drop, wire selection, DMX, BOM, 39 validation codes); a paper-inch drawing model with column layout, cable routing and pagination; vector PDF with layers, native DXF (AutoCAD AUDIT 0 errors) and SVG. | Local-only (IndexedDB), its own product library with EXAMPLE data, and an ERP pull that expects a JSON blob (`custom_riser_specs`) that ERPNext does not have. |
| **LED Tape System Visualizer** | On-brand 3D scenes (cove, under-cabinet, toe-kick, shelf, niche), lit renders, exploded and cross-section views, a flat system diagram, ~40 training visuals, a parameterized install guide with video and printable output. | Everything is hard-coded (`ZONES`, `PROFILES`, `EXAMPLE`, `JOB`, `CAD_SH01`). One 6,000-line file on Three.js r128. No persistence. |

**The product.** One dealer-facing tool, opened with **"Design system"** from a fixture schedule in the portal, that:

1. Pulls the schedule (by number or picker) and expands every line into the physical runs ERPNext already computed.
2. Lets the dealer place power supplies, cabinets, dimmers and controllers, and link runs to supply outputs (drag-and-drop or auto-assign).
3. Checks everything as they go: supply load against the 80% rule and per-output limits, maximum run length, voltage drop on every home run against a **3% Class 2 target** (D5), wire gauge and cable type for the install environment, breaker load, Class 2 limits, dimmer compatibility, DMX addressing.
4. Produces four views of the same design: an **engineering riser** (PDF/DXF), a **presentation diagram** for homeowners and designers, a **plan view** over the dealer's floor plan, and a **3D project view** with supply locations and wire routes.
5. Generates **install guides**, **labels** and a **documentation package**, and sends the design to an ilLumenate **Applications Engineer** (D3) for review using the drawing-review records that already exist.
6. Writes supplies, controllers, **wire as quotable Items** (D7) and accessories back to the schedule as lines, so the quote and Sales Order match the design. Review approval is **required before a Sales Order** when a schedule uses DMX, line-voltage (phase-cut) dimming, or exceeds 1.5 kW (D4).

**The rule that makes it work:** ERPNext is the only place product data lives. The designer reads a versioned, permission-scoped **Design Catalog** generated from the spec doctypes. Nothing is typed in twice. Third-party fixtures are the one exception: the dealer enters their data, and every output flags it **"Data by dealer"** (D8).

**Architecture.** A React + TypeScript app built with Vite, committed as a bundle inside this app (the Product Finder pattern, because Frappe Cloud runs `bench build`, not Vite), mounted at `/portal/schedules/<schedule>/design`. The riser engine, drawing model and serializers move in as packages. The visualizer is rebuilt as a modular Three.js package. Designs are saved in a new `ilL-System-Design` doctype linked to the schedule version.

**Delivery.** Phases 0–8 (section 20, work packages in H11). The first dealer-visible release (Phase 3) gives intake, power assignment, live checks and the engineering riser on real ERP data. The standalone riser repo gets one ERP-connected release and is then archived (D1).

---

## 1. What exists today

### 1.1 ERPNext app and Dealer Portal (this repository)

**Platform:** Frappe/ERPNext **version 16** (`pyproject.toml`: `frappe >=16.0.0-dev,<17`); production runs Python 3.14 (CI `ci.yml`). Module name: `ilLumenate Lighting`.

**Commercial structure**

- `ilL-Project` → `ilL-Project-Fixture-Schedule` (versioned: `version`, `version_parent`, `is_locked`, `locked_by`) → `ilL-Child-Fixture-Schedule-Line`.
- Each line has `line_id` (Fixture Type), `qty`, `location`, `product_type`, links to the template and the configured record (`configured_fixture`, `configured_tape_neon`, `configured_led_sheet`, `configured_group`), third-party fields for "Other" manufacturers (`manufacturer_name`, `fixture_model_number`, `driver_model_number`, `dimming_protocol`, `input_voltage` as text), power-supply linkage (`power_supply_for_line`, `power_supply_qty_per_build`) and a stable `line_key`.
- Portal routes in `illumenate_lighting/hooks.py` `website_route_rules`: `/portal/projects`, `/portal/schedules/<schedule>`, `/portal/configure*`, `/portal/drawings`, `/portal/quotes`, `/portal/orders`, `/portal/resources`, `/portal/product-finder`.
- Schedule → quote → Sales Order: `api/portal.py create_schedule_sales_order` → `can_request_schedule_order(doc, user)` in `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py` (the single policy for the button, the endpoint and the conversion; **D4's gate plugs in here**) → `schedule.create_sales_order_result()`.

**Access control (already consolidated)** — `portal/access.py`: `get_actor`, `project_permission`, `schedule_permission(schedule, ptype, user)`, `can_read_schedule`, `can_edit_schedule`, `schedule_query_conditions`, `can_view_catalog`, `can_read_configured_record`. Staff capabilities in `portal/staff.py` (`CAPABILITIES = {"engineering": {"ilL Engineering"}, "sales": …}`, `allowed(capability)`, `require(capability)`). Optional site flags in `portal/site_flags.py` (`conf_flag(key, default)`). Pricing visibility uses the `Can View Pricing` role.

**Configured builds carry the electrical facts the designer needs**

- `ilL-Configured-Fixture` (linear): `runs` child (`run_index`, `segment_index`, `run_len_mm`, `run_watts`, `leader_item`, `leader_len_mm`), `segments` (profile/lens/tape cut lengths, end caps, start leader, end jumper), `max_run_ft_by_watts`, `max_run_ft_by_voltage_drop`, `max_run_ft_effective`, `total_watts`, `power_feed_type`, `feed_direction_start/end`, `environment_rating`, `tape_offering`, plus canonical JSON: `build_snapshot_json`, `component_manifest_json`, `power_plan_json`, `cable_manifest_json`, and `config_hash`.
- `ilL-Configured-Tape-Neon` (tape, COB, neon): `segments` with start/end feed types, lead lengths, jumpers and watts, `cut_increment_mm`, `is_free_cutting`, `watts_per_foot`, `power_plan_json`, `config_hash`.
- `api/linear_build.py cable_manifest()` lists every physical feed, additional feed, jumper and end leader with Item and length.

**Power planning**

- `api/power_planner.py plan_power(circuits, candidates)`: exact bounded search (`MAX_CIRCUITS = 12`, `MAX_CANDIDATES = 32`), one circuit per output, never paralleled, honours total and per-output capacity × `usable_load_factor`, minimizes (supply count, cost, priority, capacity). Returns `drivers` and per-output `allocations` (`supply`, `output`, `run_key`, `watts`).
- `api/tape_neon_power.py connected_runs()` merges jumper-connected runs and rejects ones over `max_run_ft_effective`; `select_plan()` builds circuits from actual run loads.
- `api/driver_catalog.py candidates()` resolves eligible drivers per template from `ilL-Rel-Driver-Eligibility`; `independent_outputs()` refuses to treat color channels as independent feeds.
- `api/power_supply_lines.py` writes selected supplies as ACCESSORY schedule lines under the fixture line (`power_supply_for_line`, `power_supply_qty_per_build`) — **the write-back pattern the designer copies**.
- `api/configurator_engine.py`: `max_run_ft_by_watts = MAX_WATTS_PER_RUN (85 W) / W·ft⁻¹`, capped by the tape spec's static `voltage_drop_max_run_length_ft`. `docs/MVP_CONSTRAINTS.md` notes the voltage-drop table is not implemented.

**Product specification doctypes (the catalog)** — field lists in section 3 and Appendix A: `ilL-Spec-LED Tape`, `ilL-Rel-Tape Offering`, `ilL-Spec-Driver`, `ilL-Spec-Controller` (`controller_type` options today: DMX Controller, Wireless Receiver, Wall Dimmer, Scene Controller, Sensor, Gateway, Repeater), `ilL-Spec-Profile`, `ilL-Spec-Lens`, `ilL-Spec-Accessory`, `ilL-Attribute-Leader Cable`, templates (`ilL-Fixture-Template` e.g. **SH01**, `ilL-Tape-Neon-Template`, `ilL-LED-Sheet-Template`, `ilL-Driver-Template`, `ilL-Controller-Template`).

**Documents and review**

- `api/spec_submittal.py` fills PDF submittals (pypdf); `ilL-Line-Document` attaches files to lines with SHA-256.
- `ilL-Document-Request` (request types with custom fields, deliverables with `is_published_to_portal`, `published_file_sha256`, `published_build_hash`, comments, SLA, `technical_reviewer`, `fixture_schedule`).
- `portal/drawing_review.py`: `detail(request)` and `decide(request_name, revision_token, decision, note)` create `ilL-Drawing-Review` (`revision_token` = fingerprint of request + revision + file SHA-256 + build hash; only the `technical_reviewer` decides). **The design review reuses this mechanism.**

**Frontend and test patterns**

- Portal pages: Jinja templates + vanilla JS bundles (`public/js/portal*.js`).
- Product Finder: React app in `tools/configurator_ui`, built by Vite into **committed** bundles under `public/product_finder/{portal,public}`; `templates/pages/product_finder.py` builds the context (login redirect, access check, `csrf_token`) and the HTML mounts `IllConfigurator.mount(...)`.
- CI `b2b-contracts.yml`: `python -m unittest discover -s tests/portal_unit` (service tests with Frappe doubles via `tests/portal_unit/test_services.py load_service`), template render checks, Node DOM tests, **"bundle is fresh" steps** (`npm run build … && git diff --exit-code public/…`), `tools/check_b2b_changes.py` (changed-file lint + schema checks). CI `ci.yml`: installed-site bench tests and a double `bench migrate` rehearsal.

### 1.2 Riser Diagram Generator v1.2.0

**Stack:** React 19, strict TypeScript, Vite 8, Zod 4, Zustand + immer + zundo, AG Grid Community, Dexie, `@cantoo/pdf-lib` + fontkit, JSZip, PapaParse, Vitest, Playwright. 97 unit/integration tests; engine ~97% line coverage. Node ≥ 22.13.

**Schemas (`src/schemas`)**

- `Project`: `meta` (name, number, client, designer, checker, date, brand, sheet prefix, stamp), `settings` (NEC edition, termination °C, VD targets line/low-voltage/landscape = 3/3/5%, VD method lumped/distributed, AC VD method, PSU derate 80%, continuous load factor 1.25, breaker limit 80%, tape margin, min line-voltage AWG 12, DMX max unit loads 32 / length 1000 ft, SPI 15 ft, units ft/m, font, schedules on/off, sheet size/flow, wire waste 10%, label template, parallel-conductor policy).
- `sources`, `equipment` (with `fedFrom`, `controlFrom`, DMX, `enclosure`, `env`), `loads` (qty **or** `lengthFt`, `feedMethod` end/double-end/center/multi-feed, home-run and inter-fixture lengths), `controlLinks`, `wireOverrides`, `layoutOverrides`, notes, revisions, `wireTagMap`.
- `CatalogItem` with discriminated `specs` (`psu`, `driver`, `decoder`, `controller`, `tape`, `fixture`, `accessory`, `incomplete`), `erpItemCode`, provenance, `localOverrides`. Wire library and code tables (NEC Ch. 9 Table 8, Table 9, 310.16, 402.5) as cited JSON.

**Engine (`src/engine`)** — pure: graph + cycles; loads (tape, multichannel, pixel, fixtures, CC); input current with efficiency/PF; VD lumped/distributed/multichannel; wire selection by environment, ampacity, terminals, VD; DMX patch/segments/unit loads/termination; BOM; 39 validation codes (Appendix C).

**Drawing (`src/drawing`)** — paper-inch model; 26 symbol files; functional columns; one orthogonal router with lane occupancy and crossing bridges; pagination with continuations; title blocks (ARCH C/D, ANSI B/D); schedules/legends; manual pins; Web Worker; 200 loads < 2 s.

**Serializers** — SVG, layered PDF (OCG), native R2007 DXF (AutoCAD AUDIT 0 errors).

**ERP integration today** — `server/proxy.mjs` (loopback Express, pull-only, `/api/resource/Item` by item group) and `src/features/erp/sync.ts` (maps through `erp-mapping.example.json`, expects `custom_riser_category` / `custom_riser_specs` on Item). **Those fields do not exist in this ERP**; replaced by the Design Catalog (section 15.4, D1).

### 1.3 LED Tape System Visualizer (single-file HTML)

Three.js r128 (UMD), custom orbit rig, procedural PMREM environment, stencil-capped sections, 2D label overlay composited into exports. Renders: a room with five zones and 24 layers; an exploded/section detail; a one-line schematic; ~40 training visuals (Intermediate 3–5, Advanced 1–4) with build steps and animation; a parameterized cove install guide (SH01 St. Helens SF + LED-HD-SW) with cut list, clip marks, tape pieces, corner routes, jumpers, feed routes, testing, troubleshooting, captioned playback, MP4/WebM recording and printable HTML. Contains CAD outlines `CAD_SH01` (body, lens, clip, swivel bracket). Brand system: full ilLumenate tokens (`DS`), Manrope + Poppins, logo artwork. **All data hard-coded.**

---

## 2. The core problem: three copies of the product data

| Fact | ERPNext | Riser generator | Visualizer |
|---|---|---|---|
| Tape W/ft | `ilL-Spec-LED Tape.watts_per_foot` (+ offering override) | `TapeSpecs.wPerFtMax` | `JOB.wPerFt`, `EXAMPLE.wPerFt`, `ZONES[].wPerFt` |
| Cut interval | `cut_increment_mm` (+ override) | `cutIntervalIn` | `JOB.cutIntervalIn`, `EXAMPLE.cutIntervalIn` |
| Max run | `voltage_drop_max_run_length_ft`, 85 W rule | `maxRunFtSingleFeed/DoubleFeed` | `JOB.maxRunFt`, `EXAMPLE.maxRunFt` |
| Supply sizes | `ilL-Spec-Driver` | `PsuSpecs` (EXAMPLE) | `JOB.supplySizes`, `EXAMPLE.supplySizes` |
| Channel geometry | `ilL-Spec-Profile.width_mm/height_mm` | — | `PROFILES`, `CAD_SH01` |
| Wire resistance | — | NEC Table 8 JSON | `AWG_OHMS_PER_1000FT` |

The combined product removes the second and third copies:

- **Product facts** come only from ERPNext through one adapter (the Design Catalog).
- **Wire types** become ERP spec records linked to sellable Items (D7).
- **Code tables** ship with the app as cited, versioned JSON (they are not products).
- **Project facts** (runs, distances, placement) live in the saved design.
- **Third-party products** are dealer-entered on the schedule line and flagged "Data by dealer" everywhere (D8).

---

## 3. Gap analysis: what ERPNext must hold

The riser engine refuses to calculate with `incomplete` products — correct behaviour, kept. Exact field specs (fieldname, type, default) are in **H4.3**; mappings in **Appendix A**.

### 3.1 LED tape (`ilL-Spec-LED Tape`, `ilL-Rel-Tape Offering`)

| Engine field | ERPNext today | Action |
|---|---|---|
| `voltage` (12/24/48) | `input_voltage` → Link `ilL-Attribute-Output Voltage` (label) | Add `nominal_voltage_v` (Float) to the attribute |
| `drive` | — | Add `drive_type` Select: `CV`, `CV with CC IC` |
| `wPerFtMax` | `watts_per_foot`, offering `watts_per_ft_override` | Use override when present |
| channels | — (implied by LED package) | Add `channels` Int (default 1) + child table `ilL-Child-Tape-Channel` (`channel_name`, `max_w_per_ft`) |
| `powerBasis`, `maxSimultaneousPct` | — | Add with defaults |
| `maxRunFtSingleFeed` | `voltage_drop_max_run_length_ft` | Add `max_run_single_feed_ft`; fall back to old field |
| `maxRunFtDoubleFeed` | — | Add `max_run_double_feed_ft` |
| `minOperatingV` | — | Add `min_operating_voltage_v` |
| `cutIntervalIn`, `freeCutting` | `cut_increment_mm`, `is_free_cutting` | Convert mm → in |
| `reelLengthFt` | — | Add `reel_length_m` |
| `pixel` | — | Add `pixel_protocol`, `pixels_per_m`, `amps_per_pixel_max` |
| Visual | `led_pitch_mm`, `lumens_per_foot` | Add `tape_width_mm`, `leds_per_cut_segment`, `max_case_temp_c` |

### 3.2 Power supplies and drivers (`ilL-Spec-Driver`)

| Engine field | ERPNext today | Action |
|---|---|---|
| Input type/range/phase | `input_voltage_type`, `input_voltage_min/max` | Add `input_phase` (default `1PH`) |
| CV/CC output | `output_type` (Constant Voltage / Constant Current), `voltage_output` | Add `output_current_ma`, `compliance_v_min`, `compliance_v_max` |
| Rated W, outputs | `max_wattage`, `max_wattage_per_output`, `outputs_count`, `independent_outputs_count` | Add `class2_outputs` Check |
| Efficiency, PF | — | Add `efficiency` (0–1), `power_factor` (0–1) |
| Input current, inrush | — | Add `max_input_a`, `max_input_a_at_v`, `inrush_a`, `max_units_per_20a_breaker` |
| Dimming | `input_protocols` child | Map via Appendix B |
| Terminals | — | Add `terminal_min_awg`, `terminal_max_awg` |
| Listings | `certifications` | Map |
| Derate | `usable_load_factor` | Authority for the 80% rule |
| Physical | dims, weight | Add `mounting` (DIN Rail, Screw, Plug-in, Junction Box), `location_rating` (Dry, Damp, Wet) |

### 3.3 Controllers, dimmers, decoders (`ilL-Spec-Controller`)

Add `controller_type` options **DMX Decoder, DMX to 0-10V Converter, Pixel Controller, Wireless Transmitter, Relay, Lutron Module** (Appendix A.5); add per-channel limits, `dmx_footprint`, `unit_load`, `dmx_thru`, ports child table, `output_dimming`, phase-dimmer limits (`min_load_w`, `led_max_w`, `max_supplies`, `neutral_required`), `max_universes`, `max_pixels`, `max_data_length_ft`, `max_bus_devices`, terminal sizes.

### 3.4 Linear fixtures (configured)

No new fields: configured records already store runs, run watts, feeds, leaders, jumpers. The build's tape offering drives the electrical rules.

### 3.5 Profiles, lenses, accessories (visual data)

- `ilL-Spec-Profile`: `cross_section_file` (Attach, DXF), `cross_section_json` (Long Text, generated), `max_w_per_ft` (thermal).
- `ilL-Spec-Accessory`: `cross_section_file`, `cross_section_json`, `clip_spacing_max_in`, `clip_end_offset_in`, `screw_spec`.
- `ilL-Spec-Lens`: `transmission_pct`, `diffusion_class` (Clear, Frosted, Opal).
- Templates: `diagram_icon` (Attach SVG), `scene_archetypes` (Small Text, comma list).

### 3.6 Wire and cable — new, quotable (D7)

New doctype **`ilL-Spec-Wire`** linked to a sellable **Item** (H4.1). Wire is stocked, priced through Item Price, and written to schedules as accessory lines. Seed from the riser repo's `wires.seed.json` after engineering review (it is EXAMPLE today). Code tables ship as JSON.

### 3.7 Third-party fixtures — allowed, flagged (D8)

Add to `ilL-Child-Fixture-Schedule-Line`: `watts_each` (Float), `input_voltage_v` (Float), `voltage_class` (Select: Low Voltage, Line Voltage), `third_party_drive` (Select: CV, CC, Integral Driver), `third_party_ma` (Float), `third_party_dimming` (Link to dimming protocol). Lines with these filled are calculated and flagged `DATA_BY_DEALER` on every output; lines without them stay `incomplete`.

### 3.8 Catalog readiness reporting

A design-readiness report (Desk page + Catalog Builder badge) per tape offering, driver, controller and wire, listing missing design fields. Products can be quoted before they are design-ready; the designer shows them as `incomplete` with field names.

---

## 4. Product vision, users and jobs

### 4.1 Vision

> A dealer opens a fixture schedule, and twenty minutes later has a checked power plan, a riser an electrician will accept, a picture the homeowner will love, and install instructions the crew can follow — all built from the same products they are quoting.

### 4.2 Users

| Persona | Who | Primary jobs | Access |
|---|---|---|---|
| **Dealer designer** | Integrator's designer or PM (`Dealer` role, schedule write access) | Assign supplies, check runs, produce riser and package, request review | Edit |
| **Dealer sales** | Integrator's salesperson (schedule read access) | Show the homeowner; check the quote | Read + presentation exports |
| **Installer / electrician** | Field crew | Read riser and guides; wire types/lengths; labels | Installer share link (D10) |
| **Applications Engineer** | ilLumenate staff, role **`ilL Applications Engineer`** (D3) | Review, comment, approve, override errors | Reviewer |
| **Order approver** | ilLumenate staff (`ilL Order Approver`) | Override the D4 gate with a reason in exceptional cases | Gate override |
| **Specifier / homeowner / GC** | External | Receive submittals, riser, presentation | Share links |
| **Catalog owner** | ilLumenate product team (`ilL Catalog Publisher`) | Keep design fields complete | Desk |

### 4.3 Jobs to be done

1. "Turn my fixture schedule into a power plan I can trust without calling the factory."
2. "Tell me where the supplies can go and what wire to pull before rough-in."
3. "Give my electrician a drawing that looks like engineering made it."
4. "Help me sell the job with something beautiful that isn't a spec sheet."
5. "Give my crew step-by-step instructions for *this* cove, not a generic one."
6. "Make sure the quote has every supply, dimmer and foot of wire the design needs."
7. "Let ilLumenate check my work and approve it when the job needs that."

### 4.4 Two experience levels

- **Guided (default):** stepper (section 6), plain language, defaults filled in, check cards with fix buttons, technical settings hidden.
- **Engineering (opt-in; always on for staff):** the riser repo's grids (sources, equipment, loads, control links), all settings, pins, wire overrides, code edition.

Both edit the same design document.

---

## 5. Product principles

1. **ERPNext is the only product source.** Every catalog item traces to an ERP record and `modified` timestamp. Staff-only local overrides are recorded and flagged on outputs.
2. **The schedule is the bill of quantities.** The designer reads lines and writes back only lines it owns. It never edits configured builds.
3. **One engine, one drawing model, many outputs.** Views consume engine output and never recompute electrical values.
4. **Never invent data.** Missing facts → `incomplete` with named fields. EXAMPLE products never appear in dealer projects. Dealer-entered third-party data is calculated but always labelled "Data by dealer" (D8).
5. **Honest checks with a fix.** Each warning states what, why, the numbers, and the smallest fix.
6. **Deterministic and reproducible.** Same inputs + catalog snapshot + engine version → byte-identical outputs and the same `build_hash`.
7. **Beautiful for people, precise for trades.** Presentation uses brand type and color; engineering uses drafting conventions.
8. **Respect permissions.** Dealers see only their own projects; **no cost data and no cost-derived numbers leave the server** (D6); share links are signed and expire after 90 days unless renewed (D10).
9. **Line voltage belongs to the electrician.** Line-voltage circuits are drawn for coordination, labelled "By licensed electrician," never stamped unless an Applications Engineer approved the design.
10. **Portal-only presentation for now (D12).** Nothing in the designer is exposed to Webflow or public endpoints in this plan; packages are written so a public mode can be added later without refactoring.
11. **Imperial now, metric later (D11).** All UI and outputs use feet/inches; internal storage follows ERP (mm) and the engine (ft). No metric UI until Phase 8.

---

## 6. The end-to-end workflow

```
Schedule page ─"Design system"─► 1 Start ─► 2 Spaces ─► 3 Runs ─► 4 Power ─► 5 Check ─► 6 Views ─► 7 Finish
       ▲                                                                                       │
       └──── supplies, controllers, wire (Items), accessories written back as schedule lines ──┘
                                     │
                     D4 gate: DMX / phase dimming / > 1.5 kW ⇒ approved review before Sales Order
```

| Step | Screen | Dealer does | System does |
|---|---|---|---|
| 1 | **Start** | Opens from a schedule, or enters a schedule number, or picks project → schedule | Loads schedule version, lines, configured builds, Design Catalog; shows readiness and whether review will be required (D4) |
| 2 | **Spaces** | Names rooms, marks electrical room/panel and supply cabinets, optional floor plan (Phase 6) | Groups lines by `location` |
| 3 | **Runs** | Confirms space, feed end, environment, distance to supply per run | Expands lines × qty into runs with ERP lengths/watts |
| 4 | **Power** | Places supplies or accepts auto-plan; drags runs onto outputs; circuits; dimmers/controllers | Live load bars; eligible supplies only; auto-plan shows supply count and wire totals only (D6) |
| 5 | **Check** | Reviews cards, applies fixes | Engine: VD (3% Class 2 target, D5), wire selection, breakers, DMX, compatibility |
| 6 | **Views** | Riser, presentation, plan, 3D | Renders from one model; exports |
| 7 | **Finish** | Builds package, requests review, updates the quote | Writes lines back; deliverables; review request; D4 status |

---

## 7. Module 1 — Project and schedule intake

### 7.1 Entry points

- **Schedule page** (`/portal/schedules/<schedule>`): a **"Design system"** button (primary when no design exists, "Open design" otherwise) and a design status badge.
- **Project page:** "Designs" tab listing designs per schedule with status and review state.
- **Direct:** `/portal/design` — search by schedule number or project name, scoped by `schedule_query_conditions`.
- **Staff:** Desk button on `ilL-Project-Fixture-Schedule` and `ilL-System-Design` opens reviewer mode.

### 7.2 What intake loads

Schedule header/version/lock; all lines incl. accessory and power lines; for each configured line the runs, segments, feeds, cable manifest, environment, offering, `power_plan_json`, `max_run_ft_effective`, `config_hash`; the Design Catalog snapshot hash; existing designs; the D4 requirement and reasons.

### 7.3 Readiness screen

- Ready lines; lines needing data (third-party lines → "Enter data" form; catalog gaps → "Notify ilLumenate", deduplicated per product per day); unconfigured lines (link to configurator); lock state (locked → read-only, offer "Design on a new version").
- **Review banner (D4):** "This schedule uses DMX / phase-cut dimming / 2.1 kW. ilLumenate review is required before ordering." (or "Review optional").

### 7.4 Keeping in sync with the schedule

The design stores schedule version and per-line fingerprints (`line_key`, configured record, `config_hash`, qty, third-party fields). On open: unchanged → proceed; changed → reconcile dialog (added, removed, changed builds, qty changes); new schedule version → "Copy design to version N". Algorithm in H8.4.

### 7.5 Acceptance

- 150-line schedule interactive in < 3 s with a cached catalog.
- A user can never open a design for a schedule `can_read_schedule` denies.

---

## 8. Module 2 — Site model

- **Space:** name, level, type, optional 3D archetype.
- **Cabinet (enclosure):** a named supply location in a space with environment (Dry/Damp/Wet), access note, optional size limit. Becomes a riser enclosure.
- **Panel:** name, location, voltage, circuits.
- **Distances:** per run (to its supply) and per cabinet (to its circuit) with provenance: `estimate` (quick picks: same space 10 ft, adjacent 25 ft, other level 40 ft), `entered`, `measured` (plan view, Phase 6).
- Spaces auto-created from distinct `location` values (normalized: trimmed, case-folded); dealers merge/rename.
- Environment cascades space → cabinet → run, overridable per run: Dry concealed, In-wall, Plenum, Riser, Raceway, Damp, Wet, Outdoor exposed, Direct burial (maps to engine `EnvironmentSchema` per Appendix B.2).

---

## 9. Module 3 — Run builder

### 9.1 Expansion

`F3 · qty 4 · Kitchen` with 2 runs per build → `F3-1.1 … F3-4.2`. Each run: `run_key = {line_key}:{build}:{run}`, length and watts from ERP (read-only), feeds from segments, environment, tape spec/offering, factory leader from `cable_manifest_json`. Identical builds with qty ≥ 6 default to a **group** (assign once, drawn as a stacked bank), splittable anytime. Algorithm: H8.1.

### 9.2 Engine mapping

| Family | Engine representation |
|---|---|
| Tape / COB / Neon (configured) | one `load` per run: tape catalog item from offering, `lengthFt`, `feedMethod`, `homeRunLengthFt` |
| Linear fixture (configured) | one `load` per run, tape offering as the electrical item; part number kept for labels |
| LED Sheet | one `load` per sheet feed from its power plan |
| Configured group | one `load` per member run |
| Third-party low voltage (D8) | `fixture` load with dealer data, `DATA_BY_DEALER` info |
| Third-party line voltage (D8) | `fixture` load (`voltageClass: line`) on a source circuit, `DATA_BY_DEALER` |
| Existing accessory/driver lines | supply pool candidates |

### 9.3 Run editor and run-level checks

Table/cards: key, type, space, length, watts, feeds, environment, home-run length + provenance, assignment, status. Bulk edit. Strip preview. Checks: run vs single/double-feed max; feed feasibility; jumper-connected runs are one circuit.

---

## 10. Module 4 — Power and control assignment

### 10.1 Power board

Left: unassigned runs by space. Right: supply cards per cabinet with total load bar (vs `max_wattage × usable_load_factor`, 80% line) and output slots (vs `max_wattage_per_output × usable_load_factor`, Class 2 badge). Drag runs onto outputs; refusal shows the reason. "Add supply" picker filtered by voltage, protocol, eligibility, location rating; sorted by **fit** (smallest supply that fits, fewest added supplies) — **never by price** (D6). Cabinet totals show load and heat.

### 10.2 Starting point from ERP

Configurator-selected supplies (`power_plan_json` allocations and existing power lines) are pre-placed as "from configurator". Consolidation into shared cabinets is the main value.

### 10.3 Auto-plan

Site-level allocator (H8.2). Policies: fewest supplies (default), fewest cabinets, shortest wire. Cost enters only as a server-computed opaque `rank` integer per supply (D6). The proposal panel shows **supply count, cabinets used, total wire by type (ft)** and per-cabinet changes — no prices, no cost deltas.

### 10.4 Sources, circuits, breakers

Each cabinet/supply fed from a source (panel, circuit, voltage, breaker A, switching). Input current from efficiency, PF and `max_input_a`; continuous load factor 1.25; 80% breaker limit; supplies per 20 A breaker; inrush.

### 10.5 Controls

Zones with a dimming method (ELV/TRIAC phase-cut, 0-10V, DALI-2, DMX512, Lutron QS/EcoSystem, wireless). Method filters supplies and adds devices. Phase-cut: min load, LED max W, supplies per dimmer, neutral. DMX: controller → decoders → supplies, auto-patch, universes, unit loads, length, terminator. 0-10V: sink capacity. **Selecting DMX or phase-cut, or exceeding 1.5 kW, shows the D4 "review required" chip.**

### 10.6 Acceptance

Assignment updates checks < 100 ms (≤ 300 runs); undo/redo; auto-plan < 2 s for 60 runs.

---

## 11. Module 5 — Engineering checks and recommendations

### 11.1 Check catalogue

| Area | Checks | Fix actions |
|---|---|---|
| Supply loading | `PSU_OVERLOAD`, `PSU_ABOVE_DERATE`, `CHANNEL_OVERCURRENT`, per-output | Move run; add supply; larger supply |
| Class 2 | `CLASS2_OVER_100VA` | Split outputs; Class 2 output |
| Run length | `TAPE_RUN_TOO_LONG`, `MAX_LENGTH_HINT`, `SUGGEST_SPLIT_FEED` | Double-end feed; injection; split |
| Voltage at tape | `TAPE_UNDERVOLTAGE`, `VD_OVER_TARGET` (3% Class 2, D5) | Upsize wire; move supply; feed both ends |
| Wire | `NO_VALID_WIRE`, `WIRE_REQUIRES_VERIFICATION`, `TERMINAL_OVERSIZE`, `PARALLEL_REVIEW_REQUIRED` | Pick listed alternative; split circuit |
| Wire type by environment | In-wall ≥ CL2/CL3; plenum CL2P/CL3P; riser CL2R/CL3R; wet/outdoor wet + sunlight-resistant; burial direct-burial | Auto-select compliant wire Item |
| Line voltage | `BREAKER_OVERLOAD`, `INRUSH_LIMIT`, min line AWG | Split across circuits |
| Compatibility | `VOLTAGE_MISMATCH`, `DRIVE_MISMATCH`, `PROTOCOL_MISMATCH`, `INPUT_V_OUT_OF_RANGE`, `CC_COMPLIANCE`, `PHASE_DIMMER_COMPAT_UNKNOWN` | Swap to eligible supply |
| Controls | DMX codes, `SPI_DATA_LENGTH`, `DEVICE_CAPACITY`, dimmer codes | Re-patch; splitter; terminator |
| Data | `INCOMPLETE_SPEC`, `EXAMPLE_PRODUCT_IN_USE`, `UNRESOLVED_REF`, `CYCLE`, `DATA_BY_DEALER` (info) | Enter data; notify catalog team |
| Thermal / placement | `PROFILE_THERMAL_LIMIT`, `SUPPLY_LOCATION_RATING`, `SUPPLY_NO_ACCESS`, `CABINET_HEAT` | Deeper profile; move supply; ventilate |
| Review | `REVIEW_REQUIRED` (info, D4), `SCHEDULE_OUT_OF_SYNC` | Request review; reconcile |

### 11.2 Voltage drop and wire gauge

Per run: wire Item and gauge, one-way length, current, drop (V, %), voltage at tape, margin to `min_operating_voltage_v`. **Default targets (D5): 3% Class 2 low-voltage, 3% line voltage, 5% landscape.** Stored in `ilL-System-Designer-Settings`; a project may **tighten** targets; loosening requires an Applications Engineer override recorded on the design. A "what gauge if…" distance slider shows where the recommendation steps up.

### 11.3 Wire takeoff (D7)

Every home run, control link and line branch gets a W-tag, length (+ waste %, default 10%), wire type and **wire Item**. Totals per Item roll into the BOM and write back to the schedule as accessory lines (qty in the Item's sales UOM; spool rounding per H8.6).

### 11.4 Explanations

Each check card links "Why?" to the matching training visual rendered with the dealer's numbers.

### 11.5 Overrides

Dealers may acknowledge warnings with a reason; errors cannot be overridden by dealers. Applications Engineers may override errors with a reason; overrides print in QA notes and the revision block.

---

## 12. Module 6 — Outputs: riser, presentation, plan view, 3D

### 12.1 Engineering riser

Riser layout, router, pagination, title blocks, schedules, serializers moved in. Title block: ilLumenate brand + dealer logo (`Customer.dealer_logo`), project/schedule/version, design revision, designer, checker (Applications Engineer when approved), stamp: `PRELIMINARY` (default), `NOT FOR CONSTRUCTION`, `FOR REFERENCE`, or `REVIEWED BY ILLUMENATE` (only when the current revision is approved). Sheet schedules: fixture, power supply, wire (W-tag, from/to, Item, AWG, length, VD), panel/circuit, DMX patch, BOM, notes. Third-party loads show a **"DATA BY DEALER"** tag on their symbol and a general note (D8). Formats: layered PDF, DXF ZIP, SVG; sheets ARCH C/D, ANSI B/D, plus **Letter and Tabloid** for dealer packages.

### 12.2 Presentation diagram (portal-only, D12)

Brand-styled "system story": one band per space/zone, flowing source → cabinet/supplies → control → light; product icons (template `diagram_icon`), lit strip per run in its CCT, product names/finishes, friendly supply locations. Variants: homeowner, designer, installer. PNG (1×/2×/4×), SVG, PDF page. Rendered by `packages/present` (SVG first).

### 12.3 Plan view (Phase 6)

Upload floor plan (PDF page/image), two-point scale calibration, place runs/supplies/cabinets/dimmers/panel, draw or auto-route orthogonal wire paths with slack factor (default 15%); measured lengths become home-run lengths (`measured`). Output: plan sheet PDF (drafting and brand variants).

### 12.4 3D project view (Phase 6)

Modular `packages/scene3d` rebuilt from the visualizer on current Three.js. **Archetype order (D9):** cove first, then **under-cabinet, toe-kick, shelving, niche** (already modelled in the visualizer), then **ceiling reveal and stair** (Phase 8). Products from ERP (profile `cross_section_json`, tape width/LED density, lens class, supply dimensions). Supplies in cabinets, routed LV wires in zone color, line legs, dimmers, panel; glow, washes, CCT, dim; exploded/section; presets; PNG and video export. Every render carries "Representative — not to scale."

### 12.5 Consistency

One design dictionary for tags/colors/names. Every export embeds design ID, revision, engine version, catalog snapshot hash and build hash (PDF info dict, DXF header, PNG tEXt, SVG `<metadata>`).

---

## 13. Module 7 — Install guides, training, labels

- **Install guides** per space from ERP build data + design (supply location, feed route, wire, split point, controls). Field-built (tape/neon) guides include cutting; factory-built (linear) guides cover mounting, joining shipped pieces, feeding, testing. Outputs: captioned walkthrough, MP4/WebM, printable HTML/PDF, per-space QR (installer share token, D10).
- **Training library** in `/portal/resources`: ~40 visuals bound to representative ERP products, openable with the dealer's design values; copy in `ilL-Training-Visual` records.
- **Contextual help** from check cards and fields.
- **Labels** (Avery 5160/5163 PDF): supplies, wire ends (`W-07 · PS-01 OUT 2 → F3-2.1`), runs, each with QR to the installer view.

---

## 14. Module 8 — Package, review, sharing, commerce

### 14.1 Documentation package

Cover · fixture schedule · system summary (presentation + totals) · riser sheets · plan sheets · 3D renders · supply/wire/panel schedules, DMX patch, BOM · install guides · spec submittals for every line and added supply/controller (`spec_submittal.py`) · code & listing checklist · "Data by dealer" appendix listing every third-party value the dealer entered (D8). Merged PDF + ZIP, private files with SHA-256.

### 14.2 Review by an Applications Engineer (D3)

- New role **`ilL Applications Engineer`**, staff capability `"design_review"` in `portal/staff.py`.
- "Request review" creates an `ilL-Document-Request` of type **System Design Review** linked to the schedule and design revision; `technical_reviewer` is assigned from users with the role (round-robin or manual in Desk).
- Reviewer mode: pinned comments on riser/plan/3D, error overrides, approve / request changes.
- Approval → `ilL-Drawing-Review` via the existing fingerprint scheme (request + revision + package SHA-256 + design `build_hash`). Outputs then carry `REVIEWED BY ILLUMENATE · <name> · <date>`. Any edit after approval creates a new revision and removes the stamp.

### 14.3 Review gating before Sales Order (D4)

- **Required** when the schedule (or its design) has any of: DMX zone or DMX device; line-voltage (phase-cut ELV/TRIAC) dimming; total connected load **> 1.5 kW** (1500 W).
- **Optional** otherwise (the dealer can still request review).
- Enforced in `can_request_schedule_order` (single policy for button, endpoint and conversion) behind site flag `ill_system_design_review_gate` (default **off** at release, switched on after the pilot) and the Settings toggle. Algorithm: H8.5.
- Satisfied only by an **Approved** design revision whose line fingerprints match the schedule being converted.
- `ilL Order Approver` or `ilL Applications Engineer` can override with a recorded reason (audit as `ilL-Portal-Event`).

### 14.4 Sharing (D10)

Signed read-only links per audience (homeowner: presentation + 3D; installer: riser, plan, guides, labels; specifier: riser + submittals). **Default expiry 90 days; "Renew" extends to 90 days from today**; revocable; access logged. Never prices or costs. Portal-only routes (`/portal/design-share/<token>`), no public embed (D12).

### 14.5 Versioning

Revisions A, B, C… freeze inputs, snapshot hash, engine version and outputs. New schedule versions can receive a copied design with diffs.

### 14.6 Commerce loop

Supplies, controllers, dimmers, decoders, terminators, **wire Items (D7)** and accessories become schedule lines owned by the design (`system_design`, `design_line_role`). Consolidation replaces configurator per-build supply lines after a confirmed diff. Pricing flows through the normal quote → Sales Order path; users with `Can View Pricing` see the price impact of a write-back diff (prices only, never cost).

---

## 15. Architecture

### 15.1 Options considered

| Option | Verdict |
|---|---|
| A. Keep three apps, sync data | Rejected: three UIs, no write-back/review |
| B. Rebuild in Jinja + vanilla JS | Rejected: discards the TS engine/router/serializers |
| C. Separate hosted app | Rejected: second auth, CORS, cost-data risk (Finder retired its Vercel prototype for these reasons) |
| **D. React/TS app inside this app, committed bundle** | **Chosen** |

### 15.2 Structure

See H3 for the full file tree. Summary:

```
tools/system_designer/           npm workspaces: packages/* + app/
illumenate_lighting/public/system_designer/      committed build output
illumenate_lighting/templates/pages/system_design.{py,html}, design_share.{py,html}
illumenate_lighting/illumenate_lighting/system_design/   Python domain package
```

### 15.3 Frontend stack

React 19, strict TS, Vite, Zustand + immer + zundo, Zod 4, Tailwind with brand tokens, Radix, AG Grid Community, lucide-react, Three.js (current, ES modules), `@cantoo/pdf-lib` + fontkit, JSZip, Web Workers. Initial route < 400 KB gzipped; heavy modules lazy.

### 15.4 Design Catalog adapter

Python builds engine-shaped catalog items from spec doctypes (H7). Units converted, protocols mapped, provenance attached, missing fields → `incomplete`, **no cost fields; supplies carry an opaque `rank` integer only (D6)**. Content-hashed, cached (Redis key `ill:design_catalog:<hash>` + `ilL-Design-Catalog-Snapshot` record). Also served to the standalone riser 1.3 release through a staff-only endpoint (D1).

### 15.5 Persistence

Server is the system of record (`ilL-System-Design`). Client keeps an IndexedDB draft for recovery; autosave every 5 s (debounced) with optimistic concurrency on `modified`; explicit "Save revision". Client generates outputs and uploads them as private files with SHA-256.

### 15.6 Security

Mount and every endpoint check `can_read_schedule`/`can_edit_schedule`; staff actions check capabilities; prices only with `Can View Pricing`; never costs; private files; HMAC share tokens (H8.7); server validates design JSON against committed JSON Schema with size limits (5 MB, 1,000 runs); React escapes by default; lint bans `dangerouslySetInnerHTML`.

### 15.7 Server-side rendering

v1 client-only. Packages stay DOM-free (engine, drawing, serializers, present SVG) so a headless render worker can be added later (verify Frappe Cloud Node availability first).

### 15.8 Performance budgets

| Operation | Budget |
|---|---|
| Open design (150 lines, cached catalog) | < 3 s |
| Engine recalculation (300 runs, worker) | < 150 ms |
| Riser layout (200 loads) | < 2 s |
| Auto-plan (60 runs) | < 2 s |
| 3D scene (5 spaces, 40 runs) | < 1.5 s build, 60 fps orbit |
| Package (20 sheets + guides) | < 30 s with progress |

---

## 16. Data model in ERPNext

Summary here; exact fields in **H4**.

- **New doctypes:** `ilL-System-Design`, `ilL-Child-Design-Deliverable`, `ilL-Child-Design-Share`, `ilL-Child-Design-Comment`, `ilL-Design-Catalog-Snapshot`, `ilL-Spec-Wire`, `ilL-Child-Wire-Conductor`, `ilL-Child-Tape-Channel`, `ilL-Child-Controller-Port`, `ilL-Training-Visual`, `ilL-System-Designer-Settings` (Single).
- **New role:** `ilL Applications Engineer` (D3). **New request type:** `System Design Review`.
- **Field additions:** spec doctypes (section 3), schedule line (third-party data, `system_design`, `design_line_role`, `design_line_key`), templates (`diagram_icon`, `scene_archetypes`), `Customer.dealer_logo`, `ilL-Attribute-Output Voltage.nominal_voltage_v`, `ilL-Attribute-Dimming Protocol.engine_protocol`.
- **Design JSON:** riser `Project` extended with schedule fingerprints, site, runs, zones, views, overrides (H5).

---

## 17. API surface

All endpoints live in `illumenate_lighting.illumenate_lighting.system_design.api` (one facade module delegating to services), return `{"success": true, "data": …}` or `{"success": false, "error": "…", "code": "…"}`. Writes are `@frappe.whitelist(methods=["POST"])`. Full request/response contracts in **H6**.

| Endpoint | Purpose | Access |
|---|---|---|
| `find_schedules` | Search accessible schedules | Portal user |
| `open_design` | Schedule + lines + builds + design + catalog hash + readiness + D4 status | Read schedule |
| `get_catalog` | Catalog snapshot by hash | Catalog access |
| `eligible_supplies` | Driver eligibility for runs (rank only) | Read schedule |
| `save_design` | Autosave draft | Edit schedule |
| `create_revision` | Freeze revision | Edit schedule |
| `reconcile_design` | Diff vs schedule | Read schedule |
| `copy_design_to_version` | Carry forward | Edit target schedule |
| `verify_design` | Python verification of critical checks | Read schedule |
| `auto_plan` | Server allocator (verification / large designs) | Edit schedule |
| `writeback_preview` / `writeback_apply` | Schedule line diff/apply | Edit schedule |
| `upload_deliverable` | Store generated file | Edit schedule |
| `request_review` | Create review request | Edit schedule |
| `review_decide` | Approve / request changes | `design_review` capability + assigned reviewer |
| `list_comments` / `add_comment` / `resolve_comment` | Pinned comments | Read schedule (add: dealer editor or reviewer) |
| `create_share` / `renew_share` / `revoke_share` | Share links (90 days, D10) | Edit schedule |
| `open_share` | Token → read-only payload | Token |
| `review_requirement` | D4 evaluation for a schedule | Read schedule |
| `override_review_gate` | D4 override with reason | `sales` or `design_review` capability |
| `get_catalog_for_desktop` | Catalog for standalone riser 1.3 (D1) | `engineering` capability, API key |
| `list_training_visuals` / `get_training_visual` | Training config | Catalog access |

---

## 18. Consolidating the calculation engines

### 18.1 Ownership

| Concern | Owner | Other side |
|---|---|---|
| Build geometry, cuts, runs, run watts, factory leaders | ERP (Python) | Designer reads only |
| Max run per build | ERP | Designer re-checks site-combined runs |
| Driver eligibility | ERP | Designer filters |
| Per-build supply suggestion | ERP `plan_power` | Designer default |
| Site allocation, consolidation | Designer engine (TS) | Python mirror verifies |
| VD, wire selection, breakers, Class 2, DMX, compatibility | Designer engine (TS) | Python mirror verifies the gating subset |
| Pricing and cost | ERP | Designer shows prices only to `Can View Pricing`; never cost (D6) |

### 18.2 Parity

Shared golden fixtures (H10) run in Vitest and Python unittest; CI fails on divergence. Python mirror covers supply/output loading and derate, Class 2, max run, VD + wire selection for Class 2 DC runs (Table 8), voltage/protocol match, D4 triggers.

### 18.3 Rule alignment

- Configurator max run moves from the fixed 85 W rule to spec fields (`max_run_single_feed_ft`, output limits) once filled; 85 W stays as a Settings fallback.
- Engine derate defaults to each driver's `usable_load_factor`.
- One protocol vocabulary table (Appendix B) used by Python and TS.
- Engine version `system-designer-engine@<semver>` recorded on every revision.

---

## 19. What happens to each proof of concept

### 19.1 Riser Diagram Generator (D1)

| Part | Fate |
|---|---|
| `src/schemas` | → `packages/core-schemas`, extended |
| `src/engine` | → `packages/engine` + site allocator, thermal, placement, review-trigger checks |
| `src/drawing`, `src/serializers` | → `packages/drawing`, `packages/serializers` + Letter/Tabloid, dealer logo, ERP schedules, "DATA BY DEALER" tag |
| `src/features/*` | → Engineering-mode screens in `app/` |
| `src/features/erp`, `server/proxy.mjs` | Retired in the designer; **in the standalone repo, replaced by the authenticated catalog client for release 1.3.0** |
| `src/data/nec` | Kept as cited reference data |
| `wires.seed.json` | Template for `ilL-Spec-Wire` import after review |

**D1 plan:** import riser source with history via `git subtree` (WP-0.3). Ship **riser-diagram-generator 1.3.0 "ERP edition"** (WP-2.6): the Libraries → ERPNext Sync screen calls `get_catalog_for_desktop` with a staff API key through the existing loopback proxy (still pull-only, credentials in `.env`), the field mapping is removed, and products come in read-only. After System Designer reaches general availability (end of Phase 7), mark the repo archived on GitHub with a README pointing to the System Designer.

### 19.2 LED Tape System Visualizer

| Part | Fate |
|---|---|
| Brand tokens, fonts, logo | → `packages/present/brand` + Tailwind theme |
| Geometry builders | → `packages/scene3d` (archetypes, products, wiring) |
| Orbit rig, materials, lighting, exploded/section | → `packages/scene3d/core` (current Three.js) |
| Label/dimension overlay | → `packages/scene3d/overlay` |
| Flat schematic | Superseded by presentation diagram |
| Training visuals | → `packages/present/training` (ERP-bound) |
| Install guide | → `packages/guides` |
| Hard-coded data | Removed; `CAD_SH01` becomes SH01's `cross_section_json` |

**Three.js r128 → current:** cdnjs's three.js package stops at r128 (UMD); current releases ship as ES modules only. Expect: `outputEncoding` → `outputColorSpace`, physically correct lighting by default (retune intensities), PMREM API changes; the custom OrbitRig keeps working. Budget one week with visual snapshots.

### 19.3 Schedule page and configurators

No rewrite: add the "Design system" button, design badge, review-required banner, and write-back markers.

---

## 20. Phased roadmap

S ≈ 1 week, M ≈ 2–3 weeks, L ≈ 4–6 weeks (one full-stack developer with domain support). Work packages are in H11.

| Phase | Name | Size | Work packages | Exit criteria |
|---|---|---|---|---|
| 0 | Foundations | M | WP-0.1 … WP-0.6 | Empty designer opens from a schedule for authorized users only; riser tests green in this repo's CI; visualizer committed |
| 1 | ERP data readiness | M | WP-1.1 … WP-1.7 | Readiness report ≥ 90% of last-6-months schedule-line volume design-ready; wire Items exist and price |
| 2 | Catalog, intake, persistence | M | WP-2.1 … WP-2.6 | Real schedule opens with all runs and named gaps; drafts save; **riser 1.3.0 released (D1)** |
| 3 | **Beta:** power, checks, riser | L | WP-3.1 … WP-3.9 | 5 pilot dealers complete real projects; electricians accept risers; zero cost leakage in security review |
| 4 | Commerce loop and review | M | WP-4.1 … WP-4.6 | Design-driven schedule converts to an SO matching the design; D4 gate verified on staging, then flag on |
| 5 | Presentation, labels, DMX, auto-plan | M | WP-5.1 … WP-5.5 | Presentation used in proposals; DMX designs pass and render |
| 6 | 3D and plan view | L | WP-6.1 … WP-6.6 | Cove + 4 archetypes (D9) render from real data; plan-measured lengths feed the engine |
| 7 | Guides, training, package, sharing | M | WP-7.1 … WP-7.5 | One-click package; 90-day share links (D10); **GA**; riser repo archived (D1) |
| 8 | Hardening and scale | ongoing | WP-8.1 … WP-8.6 | Ceiling reveal + stair archetypes (D9); **metric units (D11)**; 500+ runs; accessibility; optional render worker |

---

## 21. Testing, quality and acceptance

- **Engine:** every branch tested; engine line coverage ≥ 95%.
- **Golden parity:** TS and Python on the same fixtures (H10).
- **Adapter:** mapping, conversion, protocol, incomplete detection; **a test that walks every payload and fails on any forbidden key (H7.4)**.
- **Schemas:** round-trip and migration of `design_json`.
- **Drawing/serializers:** existing riser tests + Letter/Tabloid + "DATA BY DEALER"; presentation SVG snapshots; 3D screenshot snapshots with tolerance.
- **API:** permission matrix (dealer A vs B, collaborator read vs write, staff capabilities, share tokens expired/revoked/renewed), concurrency, schema rejection, size limits, D4 gate cases.
- **E2E:** open → assign → fix → riser export → request review → approve → write back → SO.
- **Manual:** AutoCAD DXF import AUDIT 0 errors per sheet size; electrician review of pilot risers; 10 hand-calculated designs; brand QA.
- **Definition of done per output:** metadata embedded, deterministic, correct stamp, no prices unless permitted, never costs.

---

## 22. Decisions (final), risks and liability

### 22.1 Decisions — final as of 2026-10-06

| # | Decision | Where it is implemented |
|---|---|---|
| **D1** | Keep the standalone riser repo for **one release pointed at ERP (1.3.0)**, then **archive** it at GA | §19.1, WP-2.6, WP-7.5 |
| **D2** | Product name **"ilLumenate System Designer"**; portal label **"Design system"** | App title, page title, button, menu, PDF metadata `Creator`, file names `ilLumenate-System-Designer_…` |
| **D3** | New role **"Applications Engineer"** approves designs. Created as `ilL Applications Engineer` to follow the repo's `ilL …` role naming; staff capability `design_review` | §14.2, H4.4, WP-0.5, WP-4.3 |
| **D4** | Review **required before Sales Order** for DMX, line-voltage (phase-cut) dimming, or **> 1.5 kW**; optional otherwise | §14.3, H8.5, WP-4.4 |
| **D5** | Default VD target **3% for Class 2 runs** (also 3% line voltage, 5% landscape); projects may tighten; loosening needs an Applications Engineer override | §11.2, Settings H4.1, WP-3.5 |
| **D6** | Dealers **do not see cost ranking**; auto-plan ranks silently by an opaque server rank and shows **supply count and wire totals only** | §10.3, H7.4, H8.2, WP-5.4 |
| **D7** | **Wire types are quotable Items** (`ilL-Spec-Wire` → Item) and are written to schedules | §3.6, §11.3, H4.1, H8.6, WP-1.4, WP-4.1 |
| **D8** | **Third-party fixtures allowed on risers** with dealer-entered data, flagged **"Data by dealer"** on every output | §3.7, §12.1, §14.1, H4.3, WP-1.6, WP-3.2 |
| **D9** | 3D archetypes after cove: **under-cabinet, toe-kick, shelving, niche**, then **ceiling reveal and stair** | §12.4, WP-6.2, WP-6.3, WP-8.2 |
| **D10** | Share links default to **90 days, renewable** | §14.4, H8.7, WP-7.4 |
| **D11** | **Metric support in Phase 8** (engine already supports `units: m`) | §5 principle 11, WP-8.3 |
| **D12** | Presentation diagram **portal-only**; Webflow/public use later | §5 principle 10, §12.2, §14.4, WP-8.6 |

### 22.2 Risks

| Risk | Mitigation |
|---|---|
| Catalog data incomplete | Phase 1 before dealer release; readiness report by sales volume |
| Engine disagreement | Ownership rule; golden parity; align 85 W rule |
| Engineering liability | Stamps/disclaimers; line voltage "by licensed electrician"; only Applications Engineers stamp; code edition recorded; first-open terms acceptance |
| D4 gate blocks orders unexpectedly | Flag default off; pilot; clear banner from Start screen; staff override with reason; gate evaluates from schedule data even without a design |
| Scope creep into CAD | 3D representative; plan view overlay-only |
| Frappe Cloud has no runtime Node | Client-side generation first |
| Bundle/performance | Lazy loading, workers, budgets |
| Three.js port regressions | Snapshot tests; port before binding data |
| Wire Item pricing gaps (D7) | Readiness report includes wire Items without Item Price |
| Dealer-entered data wrong (D8) | Flag everywhere; reviewer checklist item; listed in package appendix |

### 22.3 Legal and safety content

- Engineering outputs: "Design aid. Verify against product documentation and local code. Line-voltage work by a licensed electrician."
- Default stamp `PRELIMINARY`; `REVIEWED BY ILLUMENATE` only on approved revisions.
- NEC edition and VD targets printed on each riser sheet.
- No listing claim beyond the product's certifications table.
- Third-party data note: "Third-party product data entered by <dealer>; not verified by ilLumenate" (D8).

---

## 23. Success metrics

| Metric | Target (6 months after beta) |
|---|---|
| Quoted schedules over $5k with a design | ≥ 40% |
| Supply-related order changes after SO | −50% vs baseline |
| Factory power/wiring tickets | −40% |
| Median schedule → checked riser | < 30 min |
| First-review approvals | ≥ 70% |
| Dealer satisfaction | ≥ 4.3 / 5 |
| Supplies per kW | −15% vs per-build planning |
| Wire/control line attach rate on designed schedules (D7) | ≥ 60% |
| Orders blocked by D4 then approved within 2 business days | ≥ 90% |

---

# Part II — Implementation handbook

## H1. Rules for the implementing agent

1. **Read before you write.** For each work package, read every file it lists under "Read first". Do not assume a function or field exists because this plan names it; confirm it in code. If the code disagrees with the plan, the code wins — note the difference in your PR description.
2. **One work package per PR** unless H12 groups them. Each PR is independently mergeable, keeps CI green, and does not break existing portal flows.
3. **Never invent product data.** Seeds and tests use clearly marked `EXAMPLE`/`TEST` records. Real wire, driver and tape values come from staff, not from you.
4. **Engine purity.** Nothing in `packages/engine`, `packages/core-schemas`, `packages/drawing`, `packages/serializers` may import React, the DOM, `window`, IndexedDB or network code.
5. **Views never recompute electrical values.** If a view needs a number, add it to the engine result.
6. **No cost data.** Never serialize the forbidden keys in H7.4 or any number derived from them. Prices only through existing pricing-role checks.
7. **Permissions first.** Every endpoint starts with an access check from `portal/access.py` or `portal/staff.py`. Never use `ignore_permissions=True` on user-supplied writes without an explicit preceding check.
8. **Migrations are additive.** New fields have safe defaults; patches are idempotent (CI runs `bench migrate` twice).
9. **Commit generated bundles.** After changing anything under `tools/system_designer`, run the build and commit `illumenate_lighting/public/system_designer/` (CI fails if stale).
10. **Imperial UI only** until WP-8.3 (D11). Store ERP lengths in mm, engine lengths in ft, display ft/in.
11. **Keep this plan current.** If you change a contract (H5/H6) or a decision's implementation, update this document in the same PR.
12. **Git hygiene.** Work on the branch you are given; do not force-push shared branches; no model identifiers in commits, code or docs.
13. **Ask, don't guess, on product decisions.** Anything not covered by D1–D12 or this handbook (e.g. a new threshold, a new audience for sharing) goes back to Kevin as a question in the PR.

## H2. Repository conventions you must follow

**Python**

- Frappe v16 / ERPNext v16; production Python 3.14, CI contract job Python 3.11 — write code valid on both (no PEP 695 generics or `type` alias statements).
- Format: **tabs**, double quotes, line length 110 (`pyproject.toml [tool.ruff]`). Run `ruff check` and `ruff format` on changed files; run `python -B tools/check_b2b_changes.py` before pushing.
- Copyright header on new files: `# Copyright (c) 2026, ilLumenate Lighting and contributors` / `# For license information, please see license.txt`.
- Whitelisted endpoints: `@frappe.whitelist()` for reads, `@frappe.whitelist(methods=["POST"])` for writes. Accept `Union[str, dict]` JSON bodies and `json.loads` strings (pattern in `api/portal.py`).
- Errors to the portal: return `{"success": False, "error": msg, "code": …}`; use `api/portal.py _safe_error(e, log_prefix)` for unexpected exceptions (it logs and returns a generic message).
- Roles are created in a `[pre_model_sync]` patch (pattern: `patches/create_product_finder_role.py`) so new DocType permissions can reference them.
- Patches: add module paths to `illumenate_lighting/patches.txt` in the right section; make them idempotent.
- DocTypes: folder `illumenate_lighting/illumenate_lighting/doctype/<snake_name>/` with `<snake_name>.json`, `<snake_name>.py`, `__init__.py`; module `ilLumenate Lighting`; copy the Document class naming used by neighbouring doctypes.
- Custom fields on core doctypes (Customer, Item): add to `illumenate_lighting/illumenate_lighting/fixtures/custom_field.json` **and** create them in a patch for existing sites (follow how `ill_build_id` was added).
- Site flags: `portal/site_flags.conf_flag("ill_system_design_review_gate", default=False)`.

**Python tests**

- Service tests: `tests/portal_unit/test_system_design_*.py`, using `test_services.load_service(ROOT + ".system_design.<module>", deps)` with Frappe doubles; run `python -B -m unittest discover -s tests/portal_unit`.
- Installed-site tests (doctype JSON, patches, real queries): `illumenate_lighting/illumenate_lighting/system_design/test_*.py`; add gating ones to the `ci.yml` "installed-site regression suites" step.

**TypeScript / frontend**

- Node 22 in the CI contract job (Node 24 in the bench job). npm workspaces under `tools/system_designer`.
- Scripts in `tools/system_designer/package.json`: `dev`, `build` (writes to `../../illumenate_lighting/public/system_designer`), `test` (Vitest), `typecheck`, `lint`, `test:e2e`, `schema:export`.
- Base public path `/assets/illumenate_lighting/system_designer/`. Entry names stable (`designer.js`, `designer.css`); lazy chunks may be hashed; `emptyOutDir: true` to remove stale chunks.
- CI: add a step to `.github/workflows/b2b-contracts.yml` mirroring "Product Finder bundles are fresh": `npm ci`, `npm test`, `npm run typecheck`, `npm run build`, `npm run schema:export`, `git diff --exit-code illumenate_lighting/public/system_designer`.
- Portal mount pattern: copy `templates/pages/product_finder.{py,html}` (login redirect, access check, `csrf_token`, `no_cache = 1`). All fetches send `X-Frappe-CSRF-Token`.
- In cloud sessions, Playwright uses the pre-installed Chromium (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`); do not run `playwright install`.

**Portal templates**

- Run `python -B tools/check_portal_templates.py` after template edits.
- Route rules: add `{"from_route": "/portal/schedules/<schedule>/design", "to_route": "system_design"}` **before** the `/portal/schedules/<schedule>` rule in `hooks.py`, plus `/portal/design` → `system_design` and `/portal/design-share/<token>` → `design_share`.

## H3. Target file tree

```
tools/system_designer/
  package.json                    # workspaces: ["packages/*", "app"]
  tsconfig.base.json
  vite.config.ts                  # builds app/ → public/system_designer
  vitest.workspace.ts
  playwright.config.ts
  reference/
    led-tape-system-visualizer.html   # WP-0.4, unchanged reference, not served
    README.md
  vendor/riser/                   # git subtree of the riser repo (WP-0.3); source of truth for the move
  fixtures/
    golden/                       # H10 shared fixtures (*.input.json, *.expected.json)
    schedules/                    # sample open_design payloads (TEST data)
  packages/
    core-schemas/src/             # riser schemas + design.ts (H5); scripts/export-schema.ts
    engine/src/                   # riser engine + expand.ts, allocator.ts, thermal.ts, placement.ts, review.ts
    drawing/src/                  # riser drawing
    serializers/src/              # riser serializers
    data/src/                     # NEC tables, protocols.ts (Appendix B), environments.ts, brand.json
    present/src/                  # brand/, diagram/, labels/, training/
    scene3d/src/                  # core/, archetypes/, products/, wiring/, overlay/, export/
    guides/src/                   # guide model, step templates, renderers
    erp-client/src/               # typed client for H6 endpoints
  app/
    index.html
    src/
      main.tsx                    # window.IllSystemDesigner.mount(el, options)
      routes/                     # start, spaces, runs, power, check, views, finish, engineering, review, share
      stores/                     # design (zustand + zundo), catalog, ui
      workers/                    # engine.worker.ts, layout.worker.ts, pdf.worker.ts
      components/                 # cards, load bars, check cards, pickers
illumenate_lighting/public/system_designer/                       # committed build output
illumenate_lighting/public/system_designer/schema/design.schema.json   # committed JSON Schema (H5)
illumenate_lighting/templates/pages/system_design.{py,html}
illumenate_lighting/templates/pages/design_share.{py,html}
illumenate_lighting/illumenate_lighting/system_design/
  __init__.py
  api.py            # whitelisted facade (H6)
  access.py         # design-level access helpers on top of portal/access.py
  catalog.py        # Design Catalog adapter (H7)
  protocols.py      # Appendix B table (mirrors packages/data)
  units.py          # mm/ft/in helpers
  designs.py        # open/save/revise/copy, JSON Schema validation
  expansion.py      # schedule → runs (H8.1)
  reconcile.py      # H8.4
  verify.py         # Python mirror checks (H10)
  allocator.py      # server site allocator (H8.2)
  review.py         # request/decide/comments (wraps portal/drawing_review.py)
  gate.py           # D4 (H8.5)
  writeback.py      # H8.6
  shares.py         # H8.7
  deliverables.py   # uploads, package assembly
  geometry.py       # cross-section extraction (H8.8)
  readiness.py      # design readiness report
  settings.py       # typed access to ilL-System-Designer-Settings
  code_tables/      # NEC JSON copies used by verify.py (generated from packages/data; parity-tested)
  seed/sh01_cross_section.json
  test_*.py         # installed-site tests
tests/portal_unit/test_system_design_*.py   # service tests with Frappe doubles
```

## H4. DocType specifications

Conventions: **Req** = mandatory; defaults apply on insert and in migration patches.

### H4.1 New doctypes

**`ilL-System-Design`** (naming `SYSD-.YYYY.-.#####`; track changes; perms: System Manager full, `ilL Applications Engineer` read/write, `ilL Engineering` read; portal access only through H6 endpoints and a `has_permission` hook delegating to schedule access)

| Fieldname | Label | Type | Options / default | Req | Notes |
|---|---|---|---|---|---|
| `title` | Title | Data | | ✓ | default "<schedule_name> design" |
| `fixture_schedule` | Fixture Schedule | Link | ilL-Project-Fixture-Schedule | ✓ | |
| `schedule_version` | Schedule Version | Int | | ✓ | |
| `ill_project` | Project | Link | ilL-Project | ✓ | denormalized |
| `customer` | Customer | Link | Customer | | owner customer |
| `status` | Status | Select | Draft / In Review / Changes Requested / Approved / Superseded | ✓ | default Draft |
| `revision` | Revision | Data | | ✓ | A, B, C… |
| `revision_parent` | Previous Revision | Link | ilL-System-Design | | |
| `is_current` | Current Revision | Check | 1 | | one current per schedule version |
| `design_json` | Design | Long Text | | ✓ | validated JSON (H5) |
| `design_schema_version` | Design Schema Version | Int | 1 | ✓ | |
| `engine_version` | Engine Version | Data | | ✓ | |
| `catalog_snapshot` | Catalog Snapshot | Link | ilL-Design-Catalog-Snapshot | ✓ | |
| `line_fingerprint_json` | Line Fingerprints | Long Text | | ✓ | H8.4 |
| `result_summary_json` | Result Summary | Long Text | | | totals, counts by severity |
| `build_hash` | Build Hash | Data | | | SHA-256 hex |
| `error_count` | Errors | Int | 0 | | |
| `warning_count` | Warnings | Int | 0 | | |
| `total_connected_w` | Connected Load (W) | Float | 0 | | D4 |
| `uses_dmx` | Uses DMX | Check | 0 | | D4 |
| `uses_phase_dimming` | Uses Phase-cut Dimming | Check | 0 | | D4 |
| `review_required` | Review Required | Check | 0 | | D4 |
| `review_required_reasons` | Review Reasons | Small Text | | | |
| `has_dealer_data` | Contains Dealer Data | Check | 0 | | D8 |
| `review_request` | Review Request | Link | ilL-Document-Request | | |
| `approved_review` | Approved Review | Link | ilL-Drawing-Review | | |
| `approved_by` | Approved By | Link | User | | read-only |
| `approved_on` | Approved On | Datetime | | | read-only |
| `vd_override_reason` | VD Target Override Reason | Small Text | | | D5 loosening |
| `deliverables` | Deliverables | Table | ilL-Child-Design-Deliverable | | |
| `shares` | Share Links | Table | ilL-Child-Design-Share | | |
| `comments` | Review Comments | Table | ilL-Child-Design-Comment | | |
| `terms_accepted_by` | Terms Accepted By | Link | User | | first-open acceptance |
| `terms_accepted_on` | Terms Accepted On | Datetime | | | |

**`ilL-Child-Design-Deliverable`** (istable): `kind` Select (Riser PDF / Riser DXF ZIP / Riser SVG / Presentation PNG / Presentation SVG / Presentation PDF / Plan PDF / 3D PNG / 3D Video / Install Guide PDF / Install Guide Video / Labels PDF / Package PDF / Package ZIP), `variant` Data, `file` Attach (private), `file_sha256` Data, `revision` Data, `build_hash` Data, `created_by` Link User, `created_on` Datetime.

**`ilL-Child-Design-Share`** (istable): `audience` Select (Homeowner / Installer / Specifier), `token_id` Data (16 hex), `token_hash` Data (SHA-256 of the secret), `created_by` Link User, `created_on` Datetime, `expires_on` Datetime (default now + 90 days, D10), `renewed_count` Int, `revoked` Check, `revoked_on` Datetime, `last_opened_on` Datetime, `open_count` Int.

**`ilL-Child-Design-Comment`** (istable): `comment_id` Data, `view` Select (Riser / Presentation / Plan / 3D / Run / Supply / General), `anchor_json` Small Text (sheet + x/y, entity ref, or camera + point), `body` Small Text, `author` Link User, `created_on` Datetime, `resolved` Check, `resolved_by` Link User, `resolved_on` Datetime.

**`ilL-Design-Catalog-Snapshot`** (named by `snapshot_hash`; read: System Manager, Engineering, Applications Engineer): `snapshot_hash` Data unique ✓, `engine_contract_version` Data ✓, `generated_on` Datetime, `catalog_json` Long Text (gzip + base64), `item_count` Int, `incomplete_count` Int, `wire_count` Int.

**`ilL-Spec-Wire`** (D7; named by `item`; perms mirror `ilL-Spec-Driver`)

| Fieldname | Type | Options / default | Req | Notes |
|---|---|---|---|---|
| `item` | Link Item | | ✓ | must be `is_sales_item = 1` |
| `wire_name` | Data | | ✓ | e.g. "18/2 CL3R" |
| `category` | Select | Class 2 Power / Building Wire / Cable Assembly / Data / Control / Landscape / Flex Cord | ✓ | |
| `applications` | Small Text | comma list of engine run types | ✓ | e.g. `class2-dc,lv-branch` |
| `conductors` | Table | ilL-Child-Wire-Conductor | ✓ | |
| `listing` | Data | | ✓ | CL2, CL3, CL2P, CL3R, CMP, NM-B, UF-B… |
| `rated_v` | Float | | ✓ | |
| `temp_rating_c` | Select | 60 / 75 / 90 / 105 | ✓ | |
| `plenum`, `riser`, `wet`, `direct_burial`, `sunlight_resistant`, `shielded` | Check | 0 | | |
| `impedance_ohm` | Float | | | data cables |
| `resistance_ohm_per_kft` | Float | | | overrides Table 8 |
| `ampacity_a` | Float | | | manufacturer value |
| `ampacity_basis` | Select | 310.16 / 402.5 fallback / Manufacturer | | |
| `od_in` | Float | | | |
| `riser_label` | Data | | ✓ | printed on riser |
| `sales_uom_mode` | Select | Per Foot / Per Spool | ✓ | default Per Foot |
| `spool_length_ft` | Float | | | required when Per Spool |
| `is_verified` | Check | 0 | | engineering verified |
| `source_reference` | Small Text | | ✓ | datasheet / standard |
| `is_active` | Check | 1 | | |

**`ilL-Child-Wire-Conductor`** (istable): `count` Int ✓, `awg` Select (24…4/0) ✓, `material` Select Cu/Al ✓, `stranding` Select Solid/Stranded ✓, `role` Select Power/Ground/Signal/Data Pair/Channel ✓, `colors` Small Text, `resistance_ohm_per_kft` Float, `ampacity_a` Float.

**`ilL-Child-Tape-Channel`** (istable): `channel_name` Data ✓ (W, C, R, G, B…), `max_w_per_ft` Float ✓.

**`ilL-Child-Controller-Port`** (istable): `port_name` Data ✓, `direction` Select In/Out/Bidirectional ✓, `protocol` Link ilL-Attribute-Dimming Protocol ✓, `max_devices` Int.

**`ilL-Training-Visual`**: `visual_id` Data unique ✓, `section` Data, `group` Data, `title` Data ✓, `subtitle` Small Text, `captions_json` Long Text (array per build step), `product_bindings_json` Small Text (e.g. `{"tape": "<offering>", "supply": "<driver spec>"}`), `is_published` Check.

**`ilL-System-Designer-Settings`** (Single; write: System Manager, Applications Engineer)

| Fieldname | Type | Default | Decision |
|---|---|---|---|
| `enabled` | Check | 0 | rollout switch |
| `pilot_customers` | Table MultiSelect → Customer (child doctype with one Link field) | | Phase 3 pilot |
| `vd_target_class2_pct` | Float | 3.0 | D5 |
| `vd_target_line_pct` | Float | 3.0 | D5 |
| `vd_target_landscape_pct` | Float | 5.0 | D5 |
| `nec_edition` | Select 2020/2023/2026 | 2023 | |
| `wire_waste_pct` | Float | 10 | D7 |
| `max_watts_per_run_fallback` | Float | 85 | §18.3 |
| `review_gate_enabled` | Check | 0 | D4 (also needs site flag) |
| `review_gate_watts` | Float | 1500 | D4 |
| `review_gate_dmx` | Check | 1 | D4 |
| `review_gate_phase_dimming` | Check | 1 | D4 |
| `share_default_days` | Int | 90 | D10 |
| `share_max_days` | Int | 90 | D10 (renew extends to now + this) |
| `group_threshold_qty` | Int | 6 | §9.1 |
| `default_distance_same_space_ft` / `_adjacent_ft` / `_other_level_ft` | Float | 10 / 25 / 40 | §8 |
| `plan_route_slack_pct` | Float | 15 | §12.3 |
| `terms_text` | Text Editor | legal copy (§22.3) | |
| `reviewer_assignment` | Select Manual / Round Robin | Round Robin | D3 (falls back to the request type's `default_assignee_role`) |

### H4.2 Request type seed

`ilL-Request-Type` record: `type_name = "System Design Review"`, `category = "Technical"`, `is_active = 1`, `portal_label = "System design review"`, `default_priority = "Normal"`, `sla_hours_normal = 16`, `sla_hours_high = 8`, `sla_hours_rush = 4` (business-hour SLA ≈ 2 days normal), `default_assignee_role = "ilL Applications Engineer"` (D3), `show_project_field = 1`, `show_fixture_field = 0`, no custom fields. Created in a post-model-sync patch (the role exists from the pre-model-sync patch).

### H4.3 Field additions to existing doctypes

| DocType | Fieldname | Type | Default / notes |
|---|---|---|---|
| ilL-Attribute-Output Voltage | `nominal_voltage_v` | Float | parsed from label in patch ("24VDC" → 24) |
| ilL-Attribute-Dimming Protocol | `engine_protocol` | Select (Appendix B values) | mapped in patch |
| ilL-Spec-LED Tape | `drive_type` | Select CV / CV with CC IC | CV |
| | `channels` | Int | 1 |
| | `channel_limits` | Table ilL-Child-Tape-Channel | |
| | `power_basis` | Select All Channel Max / Max Operating | All Channel Max |
| | `max_simultaneous_pct` | Float | 100 × channels |
| | `max_run_single_feed_ft` | Float | copy of `voltage_drop_max_run_length_ft` |
| | `max_run_double_feed_ft` | Float | |
| | `min_operating_voltage_v` | Float | |
| | `reel_length_m` | Float | |
| | `pixel_protocol` | Select None / WS2811 / WS2815 / SK6812 / SPI Other | None |
| | `pixels_per_m`, `amps_per_pixel_max` | Float | |
| | `tape_width_mm`, `leds_per_cut_segment`, `max_case_temp_c` | Float / Int / Float | |
| ilL-Spec-Driver | `input_phase` | Select 1PH / 3PH | 1PH |
| | `output_current_ma`, `compliance_v_min`, `compliance_v_max` | Float | CC only |
| | `class2_outputs` | Check | 0 |
| | `efficiency`, `power_factor` | Float (0–1) | |
| | `max_input_a`, `max_input_a_at_v`, `inrush_a` | Float | |
| | `max_units_per_20a_breaker` | Int | |
| | `terminal_min_awg`, `terminal_max_awg` | Select AWG | |
| | `mounting` | Select DIN Rail / Screw / Plug-in / Junction Box | |
| | `location_rating` | Select Dry / Damp / Wet | Dry |
| ilL-Spec-Controller | `controller_type` options | + DMX Decoder, DMX to 0-10V Converter, Pixel Controller, Wireless Transmitter, Relay, Lutron Module | |
| | `max_a_per_channel`, `max_w_per_channel` | Float | |
| | `dmx_footprint` | Int | |
| | `unit_load` | Float | 1 |
| | `dmx_thru` | Check | 1 |
| | `ports` | Table ilL-Child-Controller-Port | |
| | `output_dimming` | Select None / Phase Forward / Phase Reverse / 0-10V | None |
| | `min_load_w`, `led_max_w` | Float | phase dimmers |
| | `max_supplies` | Int | |
| | `neutral_required` | Check | 0 |
| | `max_universes`, `max_pixels`, `max_bus_devices` | Int | |
| | `max_data_length_ft` | Float | |
| | `terminal_min_awg`, `terminal_max_awg` | Select AWG | |
| ilL-Spec-Profile | `cross_section_file` | Attach | DXF |
| | `cross_section_json` | Long Text | generated (H8.8) |
| | `max_w_per_ft` | Float | thermal |
| ilL-Spec-Accessory | `cross_section_file`, `cross_section_json` | Attach / Long Text | |
| | `clip_spacing_max_in`, `clip_end_offset_in` | Float | |
| | `screw_spec` | Data | |
| ilL-Spec-Lens | `transmission_pct` | Float | |
| | `diffusion_class` | Select Clear / Frosted / Opal | |
| ilL-Fixture-Template, ilL-Tape-Neon-Template, ilL-LED-Sheet-Template | `diagram_icon` | Attach | SVG |
| | `scene_archetypes` | Small Text | e.g. `cove,under-cabinet` |
| ilL-Child-Fixture-Schedule-Line | `watts_each` | Float | D8 |
| | `input_voltage_v` | Float | D8 |
| | `voltage_class` | Select Low Voltage / Line Voltage | D8 |
| | `third_party_drive` | Select CV / CC / Integral Driver | D8 |
| | `third_party_ma` | Float | D8 |
| | `third_party_dimming` | Link ilL-Attribute-Dimming Protocol | D8 |
| | `system_design` | Link ilL-System-Design | write-back owner |
| | `design_line_role` | Select Supply / Controller / Wire / Accessory | write-back role |
| | `design_line_key` | Data | stable upsert key |
| Customer (custom field) | `dealer_logo` | Attach Image | title blocks |

### H4.4 Role and capability (D3)

- Patch `patches/create_applications_engineer_role.py` in `[pre_model_sync]`: create Role `ilL Applications Engineer` (`desk_access = 1`) if missing.
- `portal/staff.py`: `CAPABILITIES["design_review"] = {"ilL Applications Engineer"}`.
- DocPerms: `ilL-System-Design` read/write; `ilL-Drawing-Review` create; `ilL-System-Designer-Settings` read/write; check `doctype/ill_document_request/ill_document_request.py has_permission` — if it grants staff by an explicit role list, add the new role.

## H5. Design document schema (TypeScript / Zod)

Location: `packages/core-schemas/src/design.ts`. The riser `ProjectSchema` remains the engine input; the design wraps it with site and ERP context. **Version 1:**

```ts
export const RunKeySchema = z.string().regex(/^[^:]+:\d+:\d+$/);           // {line_key}:{build}:{run}
export const LengthProvenanceSchema = z.enum(['estimate', 'entered', 'measured', 'erp']);
export const EnvSchema = EnvironmentSchema;                                   // riser enum; UI labels map via Appendix B.2

export const SpaceSchema = z.object({
  id: IdSchema, name: z.string().min(1).max(120), level: z.string().max(60).default(''),
  type: z.enum(['kitchen','living','dining','bedroom','bath','hall','stair','exterior','mechanical','closet','other']).default('other'),
  archetype: z.enum(['cove','under-cabinet','toe-kick','shelving','niche','ceiling-reveal','stair','none']).default('none'),
  env: EnvSchema.default('dry-concealed'),
}).strict();

export const CabinetSchema = z.object({
  id: IdSchema, tag: IdSchema, name: z.string().max(120), spaceId: IdSchema,
  locationRating: z.enum(['Dry','Damp','Wet']), env: EnvSchema,
  accessNote: z.string().max(300).default(''), sourceId: IdSchema.optional(),
  feedLengthFt: NonnegativeSchema.default(0), feedLengthProvenance: LengthProvenanceSchema.default('estimate'),
}).strict();

export const RunSchema = z.object({
  key: RunKeySchema,
  lineKey: IdSchema, lineId: IdSchema, buildIndex: CountSchema, runIndex: CountSchema,
  groupId: IdSchema.optional(),
  source: z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('configured'),
               doctype: z.enum(['ilL-Configured-Fixture','ilL-Configured-Tape-Neon','ilL-Configured-LED-Sheet','ilL-Configured-Group']),
               name: IdSchema, configHash: IdSchema }).strict(),
    z.object({ kind: z.literal('third-party') }).strict(),                 // D8
  ]),
  catalogId: IdSchema,                       // tape item id, or tp:{line_key} for third-party
  lengthFt: PositiveSchema.optional(),       // ERP, read-only
  watts: PositiveSchema,                     // ERP or dealer (D8)
  feedMethod: z.enum(['end','double-end','center','multi-feed']),
  feeds: CountSchema.optional(),
  spaceId: IdSchema, env: EnvSchema,
  homeRunLengthFt: NonnegativeSchema, homeRunProvenance: LengthProvenanceSchema,
  assignment: z.object({ equipmentId: IdSchema, port: IdSchema }).strict().optional(),
  zoneId: IdSchema.optional(),
}).strict();

export const ZoneSchema = z.object({
  id: IdSchema, name: z.string().max(120), color: z.string().regex(/^#[0-9a-f]{6}$/i),
  method: z.enum(['phase-forward','phase-reverse','0-10V','DALI-2','DMX512','Lutron-QS','Lutron-EcoSystem','CRMX-wireless','none']),
}).strict();

export const OverrideSchema = z.object({
  code: IdSchema, entityRef: IdSchema, kind: z.enum(['acknowledge','staff-override']),
  reason: z.string().min(3).max(1000), by: z.string(), at: z.iso.datetime(),
}).strict();

export const DesignSchema = z.object({
  schemaVersion: z.literal(1),
  engineVersion: z.string(),
  catalogSnapshotHash: z.string().regex(/^[0-9a-f]{64}$/),
  schedule: z.object({ name: IdSchema, version: z.number().int().nonnegative() }).strict(),
  site: z.object({ spaces: z.array(SpaceSchema), cabinets: z.array(CabinetSchema),
                   floorPlans: z.array(z.unknown()).default([]) }).strict(),   // FloorPlanSchema replaces unknown in WP-6.5 (schema v2)
  runs: z.array(RunSchema).max(1000),
  zones: z.array(ZoneSchema),
  project: ProjectSchema,                    // riser engine input (sources, equipment, loads, controlLinks, settings…)
  views: z.object({ saved3d: z.array(z.unknown()).default([]), presentation: z.unknown().optional(),
                    riser: z.unknown().optional() }).strict().default({}),
  overrides: z.array(OverrideSchema).default([]),
}).strict();
```

Rules:

- `project.loads` are **derived** from `runs` by `deriveLoads(design, catalog)` (engine package) before every calculation and stored so the saved design is self-contained. The UI never edits `project.loads` directly.
- `project.settings` VD targets are initialised from Settings (D5). A validator rejects values above Settings unless an override with `kind: 'staff-override'` and `code: 'VD_TARGET_LOOSENED'` exists.
- Bump `schemaVersion` for any breaking change and add a migration (`migrateDesign(v1 → v2)`) plus a Python migration for stored rows.
- Export JSON Schema with Zod 4 `z.toJSONSchema(DesignSchema)` via `packages/core-schemas/scripts/export-schema.ts` to `illumenate_lighting/public/system_designer/schema/design.schema.json` (committed; CI freshness). Python validates with `jsonschema` — **check whether `jsonschema` is importable on the bench; if not, add it to `pyproject.toml` dependencies in the same PR.**
- `build_hash = sha256(canonicalJson({design minus views, engineVersion, catalogSnapshotHash}))`. Canonical JSON: keys sorted, no whitespace, lengths/watts rounded to 3 decimals before hashing in both languages. Python: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. A parity test hashes the same fixtures in both.

## H6. API contracts

Module: `illumenate_lighting.illumenate_lighting.system_design.api`. Responses: `{"success": true, "data": {...}}` or `{"success": false, "error": str, "code": str}` with `code` ∈ `NOT_FOUND | FORBIDDEN | INVALID | CONFLICT | LOCKED | GATE | INTERNAL`. Return `NOT_FOUND` (not `FORBIDDEN`) for records the user can't see, so guessed names reveal nothing.

| Endpoint | Method | Request | `data` on success | Access / notes |
|---|---|---|---|---|
| `find_schedules` | GET | `query` (≥ 2 chars), `limit ≤ 20` | `[{name, schedule_name, project, project_name, version, has_design}]` | `schedule_query_conditions` |
| `open_design` | GET | `schedule`, `design?` | `{schedule:{name, schedule_name, version, is_locked, status}, lines:[Line], builds:{<doctype>:{<name>: Build}}, design \| null, design_meta:{name, revision, status, modified} \| null, catalog_hash, readiness:{ready, needs_data, unconfigured, catalog_gaps}, review_requirement:{required, reasons}, permissions:{can_edit, can_review, can_view_pricing}, settings:{vd targets, waste, distance defaults, group threshold}}` | `can_read_schedule`; `Build` = runs, segments, feeds, cable manifest, environment, offering, power-plan allocations, `max_run_ft_effective`, `config_hash` |
| `get_catalog` | GET | `hash` | `{hash, engine_contract_version, items:[CatalogItem], wires:[WireType], code_tables_version}` + `ETag` | `can_view_catalog`; `NOT_FOUND` for unknown hash |
| `eligible_supplies` | POST | `schedule`, `run_keys` | `[{catalog_id, item_code, rank}]` | opaque `rank` (D6) |
| `save_design` | POST | `schedule`, `design_name?`, `design_json`, `expected_modified?` | `{name, revision, modified, build_hash, summary}` | `can_edit_schedule`; `CONFLICT` on stale `modified`; `LOCKED` if schedule locked; schema-validated; ≤ 5 MB |
| `create_revision` | POST | `design`, `note` | `{name, revision}` | old `is_current = 0`; new status Draft |
| `reconcile_design` | GET | `design` | `{added, removed, changed, qty}` | H8.4 |
| `copy_design_to_version` | POST | `design`, `target_schedule` | `{name}` | edit on target |
| `verify_design` | POST | `design` | `{ok, mismatches:[{code, entityRef, client, server}], summary}` | stores summary |
| `auto_plan` | POST | `design`, `policy` (`fewest_supplies` \| `fewest_cabinets` \| `shortest_wire`) | `{proposal:{equipment, assignments}, totals:{supplies, cabinets, wire_ft_by_item}, optimality}` | no prices or costs (D6) |
| `writeback_preview` | GET | `design` | `{add, update, remove, replaces_configurator_lines, price_delta?}` | `price_delta` only with `Can View Pricing` |
| `writeback_apply` | POST | `design`, `accepted_keys` | `{added, updated, removed}` | transactional (H8.6) |
| `upload_deliverable` | POST multipart | `design`, `kind`, `variant`, `file`, `sha256` | `{file_url, row}` | server recomputes SHA-256; private |
| `request_review` | POST | `design`, `priority`, `due_date?`, `note?` | `{request}` | saved revision with 0 errors required |
| `review_decide` | POST | `design`, `decision` (`Approved` \| `Changes Requested`), `note` | `{review, status}` | `design_review` + assigned `technical_reviewer`; uses `portal/drawing_review.decide` |
| `list_comments` / `add_comment` / `resolve_comment` | GET/POST | `design` + comment fields | comment rows | |
| `create_share` | POST | `design`, `audience`, `days?` (≤ 90) | `{url, token_id, expires_on}` | full URL returned once only |
| `renew_share` | POST | `design`, `token_id` | `{expires_on}` | now + 90 days (D10) |
| `revoke_share` | POST | `design`, `token_id` | `{}` | |
| `open_share` | GET | `token` | audience-filtered payload | no login (H8.7) |
| `review_requirement` | GET | `schedule` | `{required, reasons:[{code, detail}], satisfied, approved_design?}` | H8.5 |
| `override_review_gate` | POST | `schedule`, `reason` | `{override_id}` | `sales` or `design_review` capability |
| `get_catalog_for_desktop` | GET | — | as `get_catalog`, current snapshot | `engineering` capability, token auth (D1) |
| `list_training_visuals` / `get_training_visual` | GET | `visual_id?` | config rows | `can_view_catalog` |

## H7. Design Catalog adapter specification

File: `system_design/catalog.py`. Entry points: `build_snapshot() -> str` (returns hash) and `current_snapshot_hash() -> str`.

### H7.1 Algorithm

```
def build_snapshot():
    items = []
    for spec in active ilL-Spec-LED Tape:
        offerings = active ilL-Rel-Tape Offering where tape_spec = spec
        groups = group offerings by (effective W/ft, effective cut increment)
        for group in groups: items.append(tape_item(spec, group))        # id: tape:{spec}:{w}:{cut}
    for d in ilL-Spec-Driver whose Item is enabled and a sales item:
        items.append(psu_or_driver_item(d))                              # id: drv:{d.name}
    for c in active ilL-Spec-Controller:
        items.append(control_item(c))                                    # id: ctl:{c.name}
    wires = [wire_type(w) for w in active ilL-Spec-Wire]                 # id: wire:{w.item}
    payload = {"engine_contract_version": CONTRACT, "items": sorted(items, key=id),
               "wires": sorted(wires, key=id), "code_tables_version": CODE_TABLES}
    h = sha256(canonical_json(payload))
    upsert ilL-Design-Catalog-Snapshot(h); cache "ill:design_catalog:" + h (24 h); cache "ill:design_catalog:current" = h
    return h
```

- **Invalidation:** `doc_events` in `hooks.py` for spec doctypes, offerings, wires, voltage/protocol attributes and driver eligibility call `system_design.catalog.invalidate` (deletes `ill:design_catalog:current`). `current_snapshot_hash()` rebuilds lazily. Old snapshots stay stored for reproducibility. Avoid N+1 queries: bulk-load child tables with `frappe.get_all(..., filters={"parent": ["in", names]})`.
- **Third-party items (D8)** are not in the snapshot. The client synthesizes `fixture` items with id `tp:{line_key}`, `isExample: false`, provenance `{kind: 'user-supplied', reference: 'Data by dealer: <customer>'}`.

### H7.2 `incomplete` rules

An item becomes `{"kind": "incomplete", "intendedKind": k, "available": {...}, "missingFields": [...], "notes": []}` when any Req field in Appendix A is missing or unmappable (voltage not 12/24/48, unmapped protocol). `missingFields` uses **ERP fieldnames** so the readiness report links straight to them.

### H7.3 Unit conversions

mm → in `/25.4`; mm → ft `/304.8`; m → ft `×3.28084`; per m → per ft `/3.28084`. Round to 4 decimals in the payload.

### H7.4 No-cost rule and rank (D6)

- Forbidden keys at any depth of any designer or share payload: `cost`, `valuation_rate`, `last_purchase_rate`, `standard_rate`, `selection_cost`, `buying_price`. Price fields (`rate`, `price_list_rate`, `amount`) appear only in `writeback_preview.price_delta` and only for `Can View Pricing` users.
- Supply `rank` = dense rank over `(ilL-Rel-Driver-Eligibility.priority desc, ilL-Spec-Driver.cost asc, item_code asc)`, integers from 1. It reveals order, never magnitude.
- Unit test: build every payload from a TEST fixture and assert none of the forbidden keys appears.

### H7.5 Desktop variant (D1)

`get_catalog_for_desktop` returns the same payload. Auth: API key/secret of a staff user with the `engineering` capability (`Authorization: token key:secret`, which the riser proxy already sends).

## H8. Algorithms

### H8.1 Schedule → runs (`expansion.py`, `packages/engine/src/expand.ts`)

```
for line in schedule.lines:
    if line.design_line_role: continue                       # write-back output, not input
    if line is an accessory / power line: supply_pool.add(line.accessory_item, line.qty); continue
    if line has a configured record:
        build = configured record
        runs = linear: build.runs | tape/neon: connected_runs(computed plan) | sheet: feeds from power plan | group: member runs
        for b in 1..line.qty:
            for r in runs:
                yield Run(key=f"{line.line_key}:{b}:{r.run_index}", lengthFt=r.run_len_mm/304.8, watts=r.run_watts,
                          feedMethod=feed_method(build, r), env=map_env(build.environment_rating),
                          source=configured(doctype, name, build.config_hash), catalogId=tape_catalog_id(build))
    elif line is third-party and line.watts_each:              # D8
        for b in 1..line.qty: yield Run(key=f"{line.line_key}:{b}:1", watts=line.watts_each, source=third-party,
                                        catalogId=f"tp:{line.line_key}", feedMethod="end")
    else:
        readiness.needs_data.append(line)
group identical builds when line.qty >= settings.group_threshold_qty
```

`feed_method`: one start feed → `end`; start and end feeds on the same run → `double-end`; a centre feed type → `center`; ≥ 3 feeds → `multi-feed` with `feeds = n`. Map `ilL-Attribute-Power Feed Type.connection_type` / `directionality` in one table in `expansion.py` after reading the attribute records (values are data, not constants). If `line_key` is empty on an old line, fall back to `line_id + idx` and report it in readiness so staff can backfill.

### H8.2 Site allocator (`packages/engine/src/allocator.ts`, mirror `allocator.py`)

```
input: runs R (watts, voltage, protocol, reachable cabinets, maxHomeRunFt), supplies S (catalog items with rank),
       cabinets C (locationRating), policy
1. partition R by (voltage, protocol)
2. for each partition P:
     candidates = S eligible for every run in P (intersection), matching voltage and protocol, locationRating ≥ cabinet rating
     reachable(run) = cabinets whose distance ≤ maxHomeRunFt (largest length meeting the VD target with the heaviest allowed Class 2 wire)
     assign runs to cabinets: greedy — cabinet covering the most unassigned runs first (ties: policy)
     for each cabinet group G:
         if |G| ≤ 12 and |candidates| ≤ 32: exact search (port of power_planner.plan_power) with objective:
              fewest_supplies → (count, rank_sum, capacity)
              fewest_cabinets → cabinet step minimizes cabinets, then fewest_supplies
              shortest_wire   → (total home-run ft, count, rank_sum)
         else: first-fit decreasing by watts onto outputs of the best-ranked smallest supply that fits,
               then local search (merge two least-loaded supplies; swap runs to free a supply) until no improvement or 200 iterations
3. lower bound = ceil(total watts / largest usable capacity among candidates); optimality = "exact" if every group was exact
output: equipment (supplies with cabinet, tags PS-01…), assignments run → (equipment, "OUT n"), totals (supplies, cabinets, wire ft by wire item)
```

Always enforced: one run per output; per-output and total limits × `usable_load_factor`; Class 2 per output where required; never parallel outputs. **Output contains no cost or price** (D6). The Python mirror runs the same fixtures (H10).

### H8.3 VD targets (D5)

`effective_target = settings.vd_target_class2_pct` unless the project tightened it (lower) or a `VD_TARGET_LOOSENED` staff override exists. Engine uses riser `voltageDrop` and `selectWire`; candidates are `ilL-Spec-Wire` entries whose `applications` include the run type and whose flags satisfy the environment (riser `environmentMatches`, plus the in-wall rule in Appendix B.2).

### H8.4 Reconcile (`reconcile.py`, mirrored in TS)

Fingerprint per line: `sha256(line_key | configured doctype | configured name | config_hash | qty | watts_each | input_voltage_v | voltage_class | third_party_drive | third_party_ma | third_party_dimming)`.

- Key in design, not schedule → **removed** (drop runs; list dropped assignments).
- Key in schedule, not design → **added** (new unassigned runs).
- Same key, `config_hash` changed → **changed** (replace length/watts; keep assignments by `run_index` where the run still exists).
- Same key, only qty changed → **qty** (add/remove builds from the end).
- Write-back lines are ignored.

### H8.5 Review gate (D4) (`gate.py`)

```
def review_requirement(schedule):
    s = settings()
    if not (s.review_gate_enabled and conf_flag("ill_system_design_review_gate", default=False)):
        return {required: False, reasons: [], satisfied: True}
    reasons = []
    total_w = Σ lines (configured.total_watts × qty) + Σ third-party (watts_each × qty)
    if total_w > s.review_gate_watts: reasons.append({code: "LOAD_OVER_THRESHOLD", detail: f"{total_w:.0f} W"})
    if s.review_gate_dmx and has_dmx(schedule): reasons.append({code: "DMX"})
        # DMX if any: configured record's requested protocol / power-plan driver input protocol maps to DMX512;
        #             accessory line whose Item has an ilL-Spec-Controller of a DMX type; third_party_dimming maps to DMX512;
        #             current design.uses_dmx
    if s.review_gate_phase_dimming and has_phase(schedule): reasons.append({code: "PHASE_DIMMING"})
        # phase-cut if any protocol above maps to phase-forward/phase-reverse, or a Wall Dimmer controller with phase output,
        # or current design.uses_phase_dimming
    required = bool(reasons)
    approved = current ilL-System-Design for the schedule with status "Approved"
    satisfied = (not required) or (approved and approved.line_fingerprint_json == fingerprints(schedule)) or active_override(schedule)
    return {required, reasons, satisfied, approved_design: approved and approved.name}
```

Integration: at the end of `can_request_schedule_order`, after existing checks pass, call `gate.review_requirement(doc)`; if `required and not satisfied`, return `(False, _("ilLumenate review of the system design is required before ordering: {0}").format(reason text))`. Overrides are `ilL-Portal-Event` rows (`event_key = "system_design_gate_override:<schedule>:<fingerprint-hash>"`, `reference_type = "ilL-Project-Fixture-Schedule"`, `reference_name = schedule`, `subject` = user, `message` = reason). Because the fingerprint hash is in the key, an override stops applying as soon as the schedule changes. Read `doctype/ill_portal_event` and its existing writers first; if `event_key` must be unique, this format already is. Wrap the gate call so an unexpected exception logs and **fails closed only when the flag is on** (returns not-allowed with a support message), and never affects behaviour when the flag is off.

### H8.6 Write-back (`writeback.py`)

- Desired lines from the engine BOM: supplies (Item, qty), controllers/dimmers/decoders/terminators (Item, qty), wire (D7) — Per Foot: `qty = ceil(total_ft × (1 + waste_pct/100))`; Per Spool: `qty = ceil(total_ft × (1 + waste_pct/100) / spool_length_ft)` — and accessories.
- `design_line_key = f"{role}:{item_code}"`.
- Upsert by (`system_design`, `design_line_key`); remove owned lines no longer desired; never touch lines without `system_design`.
- Consolidation: list configurator power lines (`power_supply_for_line` set) for builds the design re-powers as `replaces_configurator_lines`; on apply, remove them using `power_supply_lines.clear_power_lines` (read it first; do not reimplement).
- New lines: `manufacturer_type = "ACCESSORY"`, `accessory_item`, `accessory_item_name`, `qty`, `location` = cabinet name (wire: "Field wire"), `line_id` prefixes `PS`, `CTRL`, `WIRE`, `ACC` + index (suffix if taken). Reuse `api/portal.py add_schedule_line` validation (active, sellable, non-template SKU) instead of raw row writes.
- One transaction; on error `frappe.db.rollback()` and return `INTERNAL` via `_safe_error`.

### H8.7 Share tokens (D10) (`shares.py`)

- Secret: `secrets.token_urlsafe(32)`; token id: `secrets.token_hex(8)`. URL `/portal/design-share/<token_id>.<secret>`. Store `token_hash = sha256(secret)` only.
- `open_share`: split, find row by `token_id`, `hmac.compare_digest` on hashes, require `revoked = 0` and `expires_on > now`, update `last_opened_on`/`open_count`, log `ilL-Portal-Event`, return the audience payload for the latest **approved** revision if one exists, else the current revision; prices always stripped.
- `create_share`: `expires_on = now + min(days or settings.share_default_days, settings.share_max_days)`. `renew_share`: `expires_on = now + settings.share_max_days`, `renewed_count += 1`. `revoke_share`: sets `revoked`, `revoked_on`.
- Rate-limit `open_share` (Frappe `rate_limit` decorator, ~60/min per IP; confirm the decorator signature in v16).

### H8.8 Cross-section extraction (`geometry.py`)

On save of a profile/accessory with `cross_section_file`, enqueue a background job that parses the DXF (use `ezdxf` only if available on the bench; otherwise accept a JSON upload in the same format and defer DXF parsing — check before adding dependencies), keeps closed LWPOLYLINEs on layers `BODY`, `LENS`, `CLIP`, normalizes to 1/1000 inch with origin at the channel bottom centre, and writes `cross_section_json` as `{"body": [x, y, …], "lens": [...], "clip": [...]}` (the `CAD_SH01` format). SH01 is seeded from `system_design/seed/sh01_cross_section.json`, extracted from the reference visualizer's `CAD_SH01` constant.

## H9. UI specification

**Shell:** full-height app in the portal layout. Header: brand, "ilLumenate System Designer" (D2), schedule name/version, revision chip, status chip, review chip (D4: "Review required" / "Review optional" / "Approved"), save state ("Saved · 12:04"), Guided/Engineering toggle, help. Left: stepper (Guided) or tabs (Engineering). Right: collapsible check panel with severity counts.

| Screen | Key components | Empty / error states |
|---|---|---|
| Start | Readiness list, review banner, terms modal on first open, Continue | Locked schedule → read-only banner + "Design on a new version" |
| Spaces | Space list (rename/merge), cabinet cards (location rating, access, circuit), panel card | No locations → single "Project" space |
| Runs | Run table/cards, bulk edit, strip preview, group chips, "Data by dealer" chips (D8) | Unconfigured lines listed with configurator links |
| Power | Run pool, supply cards with load bars and output slots, Add-supply picker (fit-sorted, no prices — D6), Auto-plan → proposal drawer (supplies, cabinets, wire totals) | No eligible supply → explanation + "Ask ilLumenate" |
| Check | Check cards (severity, title, numbers, Why?, fix buttons), acknowledge dialog | All-clear state |
| Views | Riser (sheet thumbnails, export), Presentation (variant), Plan (Phase 6), 3D (Phase 6) | Export progress modal |
| Finish | Write-back diff (price delta only with pricing role), Request review, Package builder, Share links (90-day expiry, Renew, Revoke — D10) | Errors block review request with a list |
| Engineering | Riser AG Grid tables, settings | — |
| Review (staff) | Views + comment pins, override dialog, Approve / Request changes | — |
| Share (external) | Read-only audience view, downloads, "Data by dealer" note | Expired / revoked page |

**Visual language:** visualizer brand tokens (`--primary-600` text, `--secondary-600` actions, `--accent-500` highlights, radii ≤ 20 px, Manrope headings, Poppins body); zone colors from the `ZONE_COLORS` ramp; severity colors error `#D63B2F`, warning `--accent-800`, info `--secondary-600`.

**Accessibility:** keyboard alternative to drag ("Assign to…" menu), visible focus, icons alongside severity colors, WCAG 2.2 AA contrast.

## H10. Golden fixtures and parity tests

Folder `tools/system_designer/fixtures/golden/`. Each case: `<name>.input.json` (design + catalog subset) and `<name>.expected.json` (engine result subset: loading, run VD, selected wire ids, message codes, D4 triggers, build hash).

| Case | Content |
|---|---|
| `riser-example` | From riser `examples/example.riser.json` + `engineering-results.json` |
| `cove-24v-single` | 20 ft cove, 4.5 W/ft, one 100 W supply, 15 ft 18 AWG home run (the visualizer's running example) |
| `cove-too-long` | 30 ft single-end → `TAPE_RUN_TOO_LONG`, `SUGGEST_SPLIT_FEED` |
| `vd-over-target` | 40 ft 18 AWG at 3 A → `VD_OVER_TARGET` at 3% (D5); recommends a heavier gauge |
| `class2-over` | 120 W on one Class 2 output → `CLASS2_OVER_100VA` |
| `kitchen-five-zones` | The visualizer's five zones with cabinets |
| `phase-dimmer-min-load` | 6 W run on an ELV dimmer → `DIMMER_MIN_LOAD`; D4 `PHASE_DIMMING` |
| `dmx-tw-rgbw` | DMX decoders, patch, missing terminator → `DMX_NO_TERMINATOR`; D4 `DMX` |
| `load-over-1500` | 1,600 W total → D4 `LOAD_OVER_THRESHOLD`; `load-at-1500` → no trigger |
| `third-party-mixed` | Dealer-entered fixtures → `DATA_BY_DEALER` (D8) |
| `allocator-12-exact` | 12 runs, exact supply count |
| `allocator-40-heuristic` | 40 runs, heuristic ≤ lower bound + 1 |

Runners: `packages/engine/test/golden.test.ts` (all fields) and `tests/portal_unit/test_system_design_parity.py` (Python subset). Update expected files only via `UPDATE_GOLDEN=1` with a PR note explaining why.

## H11. Work packages

Format: **ID — title (size)** · Depends · Read first · Do · Tests · Done when. Decisions referenced in brackets.

### Phase 0 — Foundations

**WP-0.1 — Portal access audit for designer surfaces (S)**
- Depends: —
- Read first: `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md` §5, `portal/access.py`, `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py` (`has_permission`, `can_request_schedule_order`), `api/document_requests.py` (`list_requests`, `_scoped_request_conditions`), `api/portal.py create_drawing_request`, the access-matrix tests (`api/test_portal_access_matrix.py` and `tests/portal_unit`).
- Do: check each P0 item (P0.1–P0.4, P0.6) against current code — the access layer has since been consolidated in `portal/access.py`, so several may already be fixed. Record a status table in the PR. Fix only items still open that touch schedules, document requests or drawing requests.
- Tests: extend access-matrix tests for any fix.
- Done when: every P0 item is "fixed earlier (evidence)" or "fixed here (test)".

**WP-0.2 — Workspace scaffold and bundle pipeline (M)**
- Depends: —
- Read first: `tools/configurator_ui/{package.json,vite.config.js,vite.portal.config.js}`, `templates/pages/product_finder.{py,html}`, `.github/workflows/b2b-contracts.yml`, `hooks.py` route rules.
- Do: create `tools/system_designer` (H3) with npm workspaces, strict TS, ESLint (ban `dangerouslySetInnerHTML`), Vitest, Playwright; `app/src/main.tsx` exposes `window.IllSystemDesigner.mount(el, {schedule, csrfToken, apiBase})` rendering a placeholder titled "ilLumenate System Designer" (D2); build to `public/system_designer/`; templates `system_design.{py,html}` (login redirect, `can_read_schedule`, Settings `enabled` or pilot-customer check, `csrf_token`); route rules (H2); CI "System Designer bundle is fresh" step.
- Tests: template render check; Playwright smoke; Python unit test for page context (unauthorized user redirected).
- Done when: `/portal/schedules/<s>/design` shows the placeholder for an authorized pilot user only; CI green.

**WP-0.3 — Import riser source with history (S)** [D1]
- Depends: WP-0.2
- Read first: riser `package.json`, `tsconfig.json`, `vitest.config.ts`, `src/*/README.md`.
- Do: `git subtree add --prefix=tools/system_designer/vendor/riser https://github.com/kevinschern-illumenate/riser-diagram-generator main` (history kept). Move `src/schemas`, `src/engine`, `src/drawing`, `src/serializers`, `src/data`, `src/workers/layout.worker.ts` into packages (H3) with path aliases; keep riser feature screens under `app/src/engineering/legacy` for WP-3.8; do not carry `server/proxy.mjs` or `src/features/erp` into the designer. Leave `vendor/riser` untouched as the reference copy.
- Tests: all riser unit tests pass in the workspace; coverage thresholds kept.
- Done when: `npm test` runs the riser suite green in CI.

**WP-0.4 — Commit the visualizer as a reference asset (S)**
- Depends: —
- Do: save the supplied visualizer HTML unchanged as `tools/system_designer/reference/led-tape-system-visualizer.html` with a README (provenance, "reference only, EXAMPLE data, not served"). Kevin supplies the file if it is not available in the session.
- Done when: committed.

**WP-0.5 — Applications Engineer role, capability and Settings (S)** [D3, D4, D5, D10]
- Depends: —
- Read first: `patches/create_product_finder_role.py`, `portal/staff.py`, `patches.txt`.
- Do: H4.4 patch and capability; `ilL-System-Designer-Settings` with H4.1 defaults; `system_design/settings.py` typed accessor (returns defaults when the single doc is unsaved).
- Tests: `staff.allowed("design_review")` with the role; installed-site test that defaults are 3.0 / 3.0 / 5.0 / 1500 / 90 / 90.
- Done when: migrate twice cleanly.

**WP-0.6 — Python package skeleton and error contract (S)**
- Depends: WP-0.5
- Do: create `system_design/` modules (H3) with docstrings; `api.py` with `respond(data)` / `fail(code, msg)`; `access.py` (`require_read(schedule)`, `require_edit(schedule)`, `require_reviewer()`, `require_capability(name)`).
- Tests: contract and access wrappers with Frappe doubles.

### Phase 1 — ERP data readiness

**WP-1.1 — Tape spec fields (S)**
- Read first: `doctype/ill_spec_led_tape/*`, `doctype/ill_rel_tape_offering/*`, `doctype/ill_attribute_output_voltage/*`, `doctype/ill_attribute_dimming_protocol/*`, `doctype/ill_attribute_led_package/*`.
- Do: H4.3 tape fields + `ilL-Child-Tape-Channel`; `nominal_voltage_v` and `engine_protocol` on attributes. Patch: parse voltage from labels (regex `(\d+(?:\.\d+)?)\s*V`); pre-fill `engine_protocol` by label (Appendix B.1); copy `voltage_drop_max_run_length_ft` → `max_run_single_feed_ft`; set `channels` from LED package where unambiguous (single 1, TW 2, RGB 3, RGBW 4), else leave 1 and surface in readiness.
- Tests: parser and mapping unit tests; patch idempotency (installed-site).
- Done when: migrate twice; values populated where derivable.

**WP-1.2 — Driver spec fields (S)** · Read: `doctype/ill_spec_driver/*`, `api/driver_catalog.py`. Do: H4.3 driver fields in an "Electrical (design)" section. Tests: existing driver/configurator tests unchanged. Done: migrate twice.

**WP-1.3 — Controller spec fields and types (S)** · Read: `doctype/ill_spec_controller/*`, `api/driver_controller_configurator.py`. Do: new `controller_type` options, fields, `ilL-Child-Controller-Port`. Tests: existing controller configurator tests unchanged.

**WP-1.4 — Wire spec and Items (M)** [D7]
- Read first: riser `src/schemas/wire.ts`, `src/data/wires.seed.json`; `api/unit_conversion.py`; how `linear_build.py` uses `cable_stock_quantity`.
- Do: `ilL-Spec-Wire`, `ilL-Child-Wire-Conductor`; Item Group "Field Wire" (patch creates if missing); Desk CSV import (CSV → wire specs + Items with `is_sales_item = 1`, UOM Foot or a spool UOM). **Do not import the EXAMPLE seed.** Provide `tools/seed_imports/field_wire_TEMPLATE.csv` with the seed's columns and blank values for staff.
- Tests: Per Spool requires `spool_length_ft`; Item must be sellable; CSV parser tests.
- Done when: staff can import reviewed wire, and wire Items price through Item Price.

**WP-1.5 — Visual fields and SH01 seed (S)** · Do: H4.3 profile/accessory/lens/template fields; extract `CAD_SH01` from the reference HTML into `system_design/seed/sh01_cross_section.json`; patch sets it on the SH01 profile spec(s) if empty. Done: SH01 shows `cross_section_json`.

**WP-1.6 — Schedule line third-party fields and write-back markers (S)** [D8]
- Read first: `doctype/ill_child_fixture_schedule_line/*`, `api/portal.py add_schedule_line/update_schedule_line`, third-party editing in `templates/pages/schedule.html` and its JS.
- Do: H4.3 schedule-line fields; dealers set D8 fields via `update_schedule_line` with validation (0 < watts ≤ 2000; voltage ∈ {12, 24, 48, 120, 208, 240, 277}; CC requires `third_party_ma`); show them in the third-party line editor; write-back fields are read-only to dealers.
- Tests: validation tests in `tests/portal_unit` (pattern: `test_add_schedule_line.py`); template check.
- Done when: a dealer can enter third-party data on the schedule page.

**WP-1.7 — Design readiness report (M)**
- Read first: `api/product_readiness.py`, the Catalog Builder page.
- Do: `system_design/readiness.py` with the H7.2 rule table (shared with WP-2.1); Desk page "Design readiness" with product-type filters and a volume column (schedule lines using each product in the last 180 days); includes wire Items without an Item Price (D7); Catalog Builder badge.
- Tests: rule-table tests.
- Done when: the report shows the Phase 1 exit metric.

### Phase 2 — Catalog, intake, persistence

**WP-2.1 — Design Catalog adapter (M)** [D6] · Depends: WP-1.1–1.4 · Do: H7 (`catalog.py`, `protocols.py`, `units.py`), snapshot doctype, cache, invalidation hooks, `get_catalog`. Tests: per-kind mapping, incomplete, conversion, **forbidden-key test**, hash stability. Done: snapshot builds in < 5 s on a production-sized copy.

**WP-2.2 — Schema package and JSON Schema export (S)** · Depends: WP-0.3 · Do: `design.ts` (H5), `deriveLoads`, `schema:export`, committed schema + CI freshness, Python `designs.validate_design_json`, canonical-JSON hash in both languages. Tests: Zod round-trip; Python accepts/rejects the same samples; hash parity. Done: both sides validate the same fixtures.

**WP-2.3 — Expansion and `open_design` (M)** [D4, D8] · Depends: WP-2.1, WP-2.2 · Read: `api/tape_neon_power.py connected_runs`, `api/linear_build.py`, configured doctypes, `portal.py get_schedule_lines_for_configurator`. Do: H8.1 (Python for builds/readiness; TS for runs), `open_design`, `find_schedules`, `review_requirement` (returns not-required while the gate is off). Tests: linear multi-run, jumpered tape, sheet, group, third-party, qty > 1, grouping threshold, missing `line_key`. Done: Start and Runs list a real schedule's runs.

**WP-2.4 — `ilL-System-Design`, save and revisions (M)** · Do: H4.1 doctypes; `save_design`, `create_revision`, concurrency, size limit, lock handling, `has_permission` hook; client store with zundo and IndexedDB draft. Tests: conflict, locked schedule, permission matrix. Done: edits survive reload; conflicting saves detected.

**WP-2.5 — Reconcile and copy-forward (S)** · Do: H8.4 + dialog. Tests: each diff category. Done: changing a qty on the schedule triggers the dialog.

**WP-2.6 — Riser 1.3.0 "ERP edition" (S)** [D1] · Depends: WP-2.1 · Works in the riser repo (needs push access; if unavailable, produce `tools/system_designer/vendor/riser-1.3.patch` and ask Kevin to apply it). Do: `get_catalog_for_desktop` (H7.5) in this repo; in the riser repo, proxy route `/api/erp/catalog` calling it; replace Libraries → ERPNext Sync with "Load ilLumenate catalog" (ERP items read-only, local overrides disabled for them); remove `erp-mapping.example.json` and the `custom_riser_*` mapping; README "ERP edition" + deprecation notice pointing to the System Designer; version 1.3.0. Tests: proxy tests with mocked upstream; updated sync tests. Done: tag `v1.3.0`.

### Phase 3 — Beta: power, checks, riser

**WP-3.1 — Guided shell, stepper, terms (S)** · H9 shell; terms modal writes `terms_accepted_by/on`; check panel scaffold; D2 naming everywhere.

**WP-3.2 — Spaces, cabinets, distances (M)** [D8] · §8; quick distance picks from Settings; environment cascade; third-party runs with "Data by dealer" chips.

**WP-3.3 — Runs screen (S)** · §9.3; bulk edit; strip preview; group/split.

**WP-3.4 — Power board (L)** [D6] · Read: `power_planner.py`, `driver_catalog.py`. Do: §10.1–10.2; `eligible_supplies`; fit-sorted picker with no prices; configurator defaults; sources/circuits; zones (phase-cut, 0-10V); keyboard assign. Tests: store tests; Playwright drag/assign; refusal reasons.

**WP-3.5 — Engine integration and checks UI (M)** [D5, D8] · Engine worker; `deriveLoads`; check cards with fix actions; VD targets tighten-only + staff override; wire selection from catalog wires; Appendix C additions. Tests: golden cases; fix-action tests.

**WP-3.6 — Python verification mirror (M)** · `verify.py` subset (§18.2) with code tables; `verify_design`; parity runner. Tests: parity on all golden cases.

**WP-3.7 — Engineering riser outputs (M)** [D2, D8] · Riser from design; `Customer.dealer_logo` custom field + patch; Letter/Tabloid title blocks; ERP-sourced schedules; "DATA BY DEALER" tag + general note; stamps (default PRELIMINARY); metadata embedding (`Creator: ilLumenate System Designer`); `upload_deliverable`. Tests: riser drawing tests; DXF round trip; metadata test.

**WP-3.8 — Engineering mode (S)** · Riser grids bound to the design store; on for staff, opt-in for dealers.

**WP-3.9 — Pilot enablement and telemetry (S)** · Settings pilot customers; `ilL-Portal-Event` rows with `event_key` prefixes `system_design:opened`, `:saved`, `:riser_exported`, `:check_fixed` (append design name + timestamp so keys stay unique); feedback prompt. Done: Phase 3 metrics measurable.

### Phase 4 — Commerce loop and review

**WP-4.1 — Write-back (M)** [D7] · Read: `power_supply_lines.py`, `portal.py add_schedule_line`. Do: H8.6; preview diff with price delta for pricing role only; apply. Tests: idempotent re-apply; consolidation replacing configurator lines; spool rounding; rollback.

**WP-4.2 — Review request type and flow (S)** [D3] · H4.2 seed; `request_review` (0 errors required); round-robin reviewer assignment over enabled users holding `ilL Applications Engineer`.

**WP-4.3 — Reviewer mode, comments, decisions (M)** [D3] · Read: `portal/drawing_review.py`. Do: comment pins; error overrides; `review_decide` publishing the package PDF as the request deliverable with `published_file_sha256` and `published_build_hash = design.build_hash` so the existing fingerprint works; stamp switch; status transitions. Tests: only the assigned reviewer decides; edit after approval → new revision, stamp removed.

**WP-4.4 — D4 review gate (M)** [D4] · Read: `can_request_schedule_order`, `portal/site_flags.py`. Do: H8.5; banners on the schedule page and Start screen; `override_review_gate`; order button disabled with reason. Tests: 1500 W (no trigger) vs 1500.1 W (trigger); DMX via configured protocol, controller line, third-party dimming, design flag; phase via protocol and dimmer line; satisfied by matching approved design; unsatisfied after a schedule change; override valid then invalidated; no effect when flag or setting is off; exception path. Done: verified on staging, then the flag is turned on (ops change).

**WP-4.5 — Schedule page integration (S)** [D2] · "Design system" button, design badge, review chip, project page "Designs" tab. Template checks.

**WP-4.6 — End-to-end commerce test (S)** · Playwright: open → assign → riser → review → approve → write back → SO allowed.

### Phase 5 — Presentation, labels, DMX, auto-plan

**WP-5.1 — Brand package and presentation diagram (M)** [D12] · Read: reference visualizer sections 0, 14, 19 helpers (`card`, `pill`, `drawStrip`, `drawPSU`). Do: `packages/present` SVG renderer, three variants, PNG rasterization, portal-only. Tests: SVG snapshots.

**WP-5.2 — Labels (S)** [D10] · Avery 5160/5163 PDFs with QR codes to an installer share link created on demand.

**WP-5.3 — DMX and advanced controls (M)** [D4] · DMX zones, decoders, auto-patch, terminator, Lutron/DALI devices; sets `uses_dmx`. Tests: `dmx-tw-rgbw`.

**WP-5.4 — Auto-plan (M)** [D6] · H8.2 in TS + Python mirror; proposal drawer with supply count, cabinets, wire totals only. Tests: allocator golden cases; payload forbidden-key test.

**WP-5.5 — Contextual "Why?" links (S)** · Map check codes → training visual ids (stub viewer until WP-7.2).

### Phase 6 — 3D and plan view

**WP-6.1 — Scene core port (M)** · Port orbit rig, materials, environment, lighting, overlay, exploded/section to current Three.js in `packages/scene3d/core`; screenshot snapshot harness.

**WP-6.2 — Cove archetype from data (M)** [D9] · Cove kit parameterized by assigned runs (linear, L, U, rectangle); SH01 cross-section from ERP; supplies in cabinet; wires.

**WP-6.3 — Under-cabinet, toe-kick, shelving, niche (L)** [D9, in this order] · Port the visualizer builders, parameterize, compose per space.

**WP-6.4 — 3D exports (S)** · PNG with labels, turntable video, saved views.

**WP-6.5 — Plan view (L)** · Private floor plan upload, PDF page render, calibration, placement, orthogonal routing with slack, measured lengths → runs; plan sheet PDF; design schema v2 (`FloorPlanSchema`) with migration.

**WP-6.6 — Archetype selection UI (S)** · Per-space archetype pick with template `scene_archetypes` hints.

### Phase 7 — Guides, training, package, sharing

**WP-7.1 — Install guide generator (L)** · Read: reference visualizer section 21. `packages/guides` step templates (field-built vs factory-built), data from ERP build + design; walkthrough, video, printable PDF, QR.

**WP-7.2 — Training library (M)** · `ilL-Training-Visual` seed for the ~40 visuals; `packages/present/training` bound to representative ERP products; Resources entry.

**WP-7.3 — Documentation package (M)** [D8] · §14.1 merge (server-side pypdf merge of uploaded PDFs + spec submittals); "Data by dealer" appendix; ZIP.

**WP-7.4 — Share links (S)** [D10] · H8.7; `design_share.{py,html}`; Finish screen controls. Tests: expiry, renew to now + 90 days, revoke, constant-time compare, audience filtering, no prices.

**WP-7.5 — GA and riser archive (S)** [D1] · Settings `enabled = 1` for all dealers (ops). Riser repo final README notice; Kevin archives the repository on GitHub.

### Phase 8 — Hardening

- **WP-8.1** Performance at 500+ runs (worker batching, virtualized lists).
- **WP-8.2** Ceiling reveal and stair archetypes [D9].
- **WP-8.3** Metric units [D11]: per-user unit toggle, engine `units: m`, outputs in m/mm, Settings default.
- **WP-8.4** Accessibility audit (WCAG 2.2 AA) and fixes.
- **WP-8.5** Optional headless render worker (after confirming Frappe Cloud support).
- **WP-8.6** Public presentation embed: design review only [D12]; implement only after a new decision.

## H12. Pull-request sequence and review checklist

**Sequence** (one PR per line unless noted):

1. WP-0.1 · 2. WP-0.5 + WP-0.6 · 3. WP-0.2 · 4. WP-0.3 · 5. WP-0.4 · 6. WP-1.1 · 7. WP-1.2 · 8. WP-1.3 · 9. WP-1.4 · 10. WP-1.5 · 11. WP-1.6 · 12. WP-2.2 · 13. WP-2.1 · 14. WP-1.7 · 15. WP-2.3 · 16. WP-2.4 · 17. WP-2.5 · 18. WP-2.6 (riser repo) · 19–27. WP-3.1 … WP-3.9 · 28–33. WP-4.1 … WP-4.6 · then Phases 5–8 in WP order.

**Every PR must:**

- [ ] Name the work package and decisions it implements.
- [ ] List files read and any plan/code discrepancies found.
- [ ] Pass `ruff check` / `ruff format --check` on changed Python, `python -B tools/check_b2b_changes.py`, `python -B -m unittest discover -s tests/portal_unit`, `python -B tools/check_portal_templates.py` (if templates changed), and in `tools/system_designer` (if TS changed) `npm test && npm run typecheck && npm run build && npm run schema:export` with outputs committed.
- [ ] Add tests for every new branch; change golden fixtures only with an explanation.
- [ ] Keep patches idempotent and new fields defaulted.
- [ ] Contain no forbidden cost keys in any payload; prices only behind `Can View Pricing`.
- [ ] Update this plan if a contract or decision implementation changed.

---

## Appendix A — Field mapping: ERP → engine catalog

**Req** = required for a complete (non-`incomplete`) item.

**A.1 Tape (`kind: 'tape'`)**

| Engine | ERP source | Transform | Req |
|---|---|---|---|
| `id` | `tape:{spec}:{w}:{cut}` | — | ✓ |
| `sku` / `erpItemCode` | `ilL-Spec-LED Tape.item` | — | ✓ |
| `voltage` | `input_voltage` → `nominal_voltage_v` | must be 12/24/48 | ✓ |
| `drive` | `drive_type` | CV → `CV`; CV with CC IC → `CV-CC-IC` | ✓ |
| `wPerFtMax` | offering `watts_per_ft_override` ‖ `watts_per_foot` | — | ✓ |
| `powerBasis`, `maxSimultaneousPct` | `power_basis`, `max_simultaneous_pct` | All Channel Max → `all-channel-max` | ✓ (defaults) |
| `channels`, `channelMap`, `channelWPerFtMax` | `channels`, `channel_limits` | names from table, else `CH1…` | ✓ (defaults) |
| `maxRunFtSingleFeed` | `max_run_single_feed_ft` ‖ `voltage_drop_max_run_length_ft` | — | ✓ |
| `maxRunFtDoubleFeed` | `max_run_double_feed_ft` | — | ✓ |
| `freeCutting`, `cutIntervalIn` | `is_free_cutting`, offering `cut_increment_mm_override` ‖ `cut_increment_mm` | mm ÷ 25.4 | ✓ |
| `minOperatingV` | `min_operating_voltage_v` | — | ✓ |
| `reelLengthFt` | `reel_length_m` | × 3.28084 | |
| `pixel` | `pixel_protocol`, `pixels_per_m`, `amps_per_pixel_max` | per m → per ft | if pixel |
| visual | `led_pitch_mm`, `tape_width_mm`, `leds_per_cut_segment`, `lumens_per_foot`, CCT/CRI | presentation/3D only | |

**A.2 Supply / driver**

| Engine | ERP source | Req |
|---|---|---|
| `inputType`, `inputVMin`, `inputVMax` | `input_voltage_type`, `input_voltage_min/max` | ✓ |
| `inputPhase` | `input_phase` | ✓ (default) |
| `outputType` | `output_type` (Constant Voltage → `CV` psu; Constant Current → `CC` driver) | ✓ |
| `outputV` | `voltage_output` → `nominal_voltage_v` | CV ✓ |
| `outputmA`, `outputVMin/Max` | `output_current_ma`, `compliance_v_min/max` | CC ✓ |
| `ratedW` | `max_wattage` | ✓ |
| `outputs[]` | `independent_outputs_count` × `{maxW: max_wattage_per_output, class2: class2_outputs}` | ✓ |
| `efficiency`, `powerFactor` | same names | ✓ |
| `maxInputA`, `maxInputAAtV`, `inrushA`, `maxUnitsPer20ABreaker` | same names | |
| `dimming[]` | `input_protocols` → Appendix B | ✓ |
| `terminalMinAwg/MaxAwg` | same | ✓ |
| `listings[]` | `certifications` | |
| derate | `usable_load_factor` | ✓ |
| `rank` (D6) | H7.4 | ✓ |

**A.3 Controls**

| Engine | ERP source | Req |
|---|---|---|
| category | `controller_type` (A.5) | ✓ |
| `channels`, `maxAPerChannel`, `maxATotal`, `maxWPerChannel`, `maxWTotal` | `channels`, `max_a_per_channel`, `max_load_amps`, `max_w_per_channel`, `max_load_watts` | decoder ✓ |
| `dmxFootprint`, `unitLoad`, `dmxThru` | same | DMX ✓ |
| `protocolIn/Out`, `ports[]` | `input_protocols`, `output_protocols`, `ports` | ✓ |
| `powerType`, `outputDimming` | `input_voltage_type`, `output_dimming` | AC decoder ✓ |
| `ownPowerW` | `standby_power_watts` | |
| dimmer limits | `min_load_w`, `led_max_w`, `max_supplies`, `neutral_required` | phase dimmer ✓ |

**A.4 Schedule line → design run** — see H8.1.

**A.5 Controller type → engine category**

| `controller_type` | Engine category | Action |
|---|---|---|
| DMX Controller | `dmx-controller` | — |
| Wireless Receiver | `wireless-rx` | — |
| Wall Dimmer | `phase-dimmer` (new engine category) or `0-10v-dimmer` | split by `output_dimming` |
| Scene Controller | `keypad` | — |
| Gateway | `sacn-gateway` | — |
| Repeater | `opto-splitter` | confirm intent with staff |
| Sensor | not modelled | draw as a control-only device (later) |
| DMX Decoder *(new)* | `dmx-decoder` | WP-1.3 |
| DMX to 0-10V Converter *(new)* | `dmx-0-10v-converter` | WP-1.3 |
| Pixel Controller *(new)* | `pixel-controller` | WP-1.3 |
| Wireless Transmitter *(new)* | `wireless-tx` | WP-1.3 |
| Relay, Lutron Module *(new)* | `relay`, `lutron-module` | WP-1.3 |

**A.6 Wire (D7)** — `ilL-Spec-Wire` → riser `WireType`: `id = wire:{item}`, `name = wire_name`, `category` lower-kebab, `applications` split, `conductors` from child rows, `listing`, `ratedV`, `tempRatingC`, flags, `resistanceOhmPerKft`, `ampacityA`, `ampacityBasis`, `odIn`, `riserLabel`, `isExample: false`, `verify: !is_verified`, `source: {kind: 'manufacturer', reference: source_reference}`, plus `erpItemCode = item`, `salesUom`, `spoolLengthFt`.

## Appendix B — Protocol vocabulary

**B.1 Dimming protocols.** One table (`system_design/protocols.py` and `packages/data/src/protocols.ts`, kept identical by a parity test) from `ilL-Attribute-Dimming Protocol.engine_protocol` to the engine enum: `none`, `phase-forward` (TRIAC, leading edge), `phase-reverse` (ELV, trailing edge), `0-10V`, `1-10V`, `DALI-2`, `DMX512`, `RDM`, `sACN`, `Art-Net`, `CRMX-wireless`, `Lutron-QS`, `Lutron-EcoSystem`, `PWM`, `SPI`. The WP-1.1 patch pre-fills `engine_protocol` by case-insensitive label match (TRIAC → phase-forward, ELV → phase-reverse, 0-10V, DALI → DALI-2, DMX → DMX512, SPI); unmatched values stay blank and make dependent items `incomplete` ("unmapped protocol: X").

**B.2 Environments.** UI labels → engine `EnvironmentSchema`: Dry concealed → `dry-concealed`; In-wall → `dry-concealed` plus a rule requiring CL2/CL3 or better listing; Plenum → `plenum`; Riser → `riser`; Raceway → `raceway`; Damp → `wet` for wire selection (conservative) and `Damp` for supply location rating; Wet → `wet`; Outdoor exposed → `outdoor-exposed`; Direct burial → `direct-burial`. ERP `environment_rating` values map in one table in `expansion.py` (read the attribute records first).

## Appendix C — Validation codes

**Riser engine (kept):** `INCOMPLETE_SPEC`, `UNRESOLVED_REF`, `CYCLE`, `VOLTAGE_MISMATCH`, `DRIVE_MISMATCH`, `PROTOCOL_MISMATCH`, `INPUT_V_OUT_OF_RANGE`, `PSU_OVERLOAD`, `CHANNEL_OVERCURRENT`, `BREAKER_OVERLOAD`, `TAPE_UNDERVOLTAGE`, `NO_VALID_WIRE`, `DMX_ADDRESS_OVERLAP`, `DMX_ADDRESS_OVERFLOW`, `PSU_ABOVE_DERATE`, `CLASS2_OVER_100VA`, `VD_OVER_TARGET`, `TAPE_RUN_TOO_LONG`, `TERMINAL_OVERSIZE`, `DMX_UNIT_LOADS`, `DMX_LENGTH`, `DMX_NO_TERMINATOR`, `SPI_DATA_LENGTH`, `INRUSH_LIMIT`, `PHASE_DIMMER_COMPAT_UNKNOWN`, `EXAMPLE_PRODUCT_IN_USE`, `MAX_LENGTH_HINT`, `SUGGEST_SPLIT_FEED`, `CODE_TABLE_UNAVAILABLE`, `WIRE_REQUIRES_VERIFICATION`, `INVALID_SPEC`, `INVALID_PORT`, `DMX_TOPOLOGY`, `PARALLEL_REVIEW_REQUIRED`, `DATA_LENGTH`, `CC_COMPLIANCE`, `INPUT_CURRENT_ESTIMATED`, `QTY_DISTRIBUTION`, `DEVICE_CAPACITY`.

**Added by the designer** (extend `ValidationMessageSchema.code` in WP-3.5):

| Code | Severity | Meaning |
|---|---|---|
| `PROFILE_THERMAL_LIMIT` | warning | Tape W/ft above the profile's `max_w_per_ft` |
| `SUPPLY_LOCATION_RATING` | error | Supply location rating below the cabinet's |
| `SUPPLY_NO_ACCESS` | warning | Cabinet has no access note |
| `CABINET_HEAT` | warning | Enclosed cabinet heat above guideline |
| `DIMMER_MIN_LOAD` / `DIMMER_LED_MAX` / `DIMMER_SUPPLY_COUNT` | error | Phase dimmer limits |
| `DIMMER_NEUTRAL` | warning | Dimmer needs a neutral; confirm the box has one |
| `VD_TARGET_LOOSENED` | info | Staff loosened a VD target (D5) |
| `SCHEDULE_OUT_OF_SYNC` | warning | Design built on an older schedule version/fingerprint |
| `CONFIG_PLAN_REPLACED` | info | Configurator supply lines superseded by the design |
| `DATA_BY_DEALER` | info | Third-party data entered by the dealer (D8) |
| `REVIEW_REQUIRED` | info | D4 requires approval before ordering |

## Appendix D — Source references

**ERP (this repo):** `api/power_planner.py`, `api/tape_neon_power.py`, `api/linear_power.py`, `api/driver_catalog.py`, `api/power_supply_lines.py`, `api/linear_build.py` (`cable_manifest`), `api/configurator_engine.py` (max run), `api/spec_submittal.py`, `api/document_requests.py`, `api/portal.py` (schedule endpoints, `create_schedule_sales_order`, `add_schedule_line`, `_safe_error`), `api/product_readiness.py`, `portal/access.py`, `portal/staff.py`, `portal/site_flags.py`, `portal/drawing_review.py`, `doctype/ill_project_fixture_schedule` (`can_request_schedule_order`), `doctype/ill_child_fixture_schedule_line`, `doctype/ill_configured_fixture`, `doctype/ill_configured_tape_neon`, `doctype/ill_spec_*`, `doctype/ill_drawing_review`, `doctype/ill_line_document`, `templates/pages/product_finder.{py,html}`, `tools/configurator_ui`, `tests/portal_unit/test_services.py`, `.github/workflows/{ci,b2b-contracts}.yml`, `patches/create_product_finder_role.py`, `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md`, `docs/MVP_CONSTRAINTS.md`.

**Riser repo:** `src/schemas/{project,catalog,wire,common,library}.ts`, `src/engine/{calculate,loads,voltageDrop,wireSelect,dmx,bom,graph}.ts`, `src/drawing/`, `src/serializers/`, `src/features/erp/sync.ts`, `server/proxy.mjs`, `src/data/nec/*.json`, `src/data/wires.seed.json`, `examples/`, `docs/acceptance-report.md`, `docs/drawing-revision-1.1.md`.

**Visualizer (`tools/system_designer/reference/led-tape-system-visualizer.html` after WP-0.4):** section 0 (brand), 1–1d (EXAMPLE data to replace), 7–10 (3D builders), 11 (overlay), 13 (exploded/section), 14 (schematic), 17 (export), 19–20 (training), 21 (install guide, `CAD_SH01`).

## Appendix E — Glossary

- **Run:** a continuous electrically connected length of tape or a fixture's internal circuit, fed by one supply output.
- **Feed:** a point where power enters a run (end, both ends, center, injection).
- **Home run:** field wire from a supply output to a run's feed.
- **Cabinet / enclosure:** a named location holding supplies and controls.
- **Design Catalog:** the versioned, engine-shaped product snapshot generated from ERP specs.
- **Build hash:** SHA-256 of a design's canonical inputs, engine version and catalog snapshot.
- **Archetype:** a parameterized 3D scene kit (cove, under-cabinet, …).
- **Applications Engineer:** ilLumenate staff role that reviews and approves designs (D3).
- **Review gate:** the D4 rule blocking Sales Orders for DMX, phase-cut dimming or > 1.5 kW schedules without an approved design.
- **Data by dealer:** third-party product data entered by the dealer; calculated, always flagged (D8).
