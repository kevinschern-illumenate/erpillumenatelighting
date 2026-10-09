# ilLumenate System Designer — Implementation Status

Tracks work packages from [SYSTEM_DESIGNER_PRODUCT_PLAN.md](SYSTEM_DESIGNER_PRODUCT_PLAN.md) (Part II, H11).
Each entry records what landed, where, and any place the code disagreed with the plan (H1 rule 1).

| WP | Title | Status |
|---|---|---|
| WP-0.1 | Portal access audit for designer surfaces | Done (no code change needed, see below) |
| WP-0.2 | Workspace scaffold and bundle pipeline | Done |
| WP-0.3 | Import riser source | Done (see notes) |
| WP-0.4 | Commit the visualizer as a reference asset | Done |
| WP-0.5 | Applications Engineer role, capability and Settings | Done |
| WP-0.6 | Python package skeleton and error contract | Done |
| WP-1.1 | Tape, voltage and protocol design fields | Done |
| WP-1.2 | Driver design fields | Done |
| WP-1.3 | Controller types, design fields and ports | Done |
| WP-1.4 | Wire spec and Items | Done |
| WP-1.5 | Visual fields and SH01 seed | Done |
| WP-1.6 | Schedule line third-party fields and write-back markers | Done (see `system_design` link note) |
| WP-1.7 | Design readiness report | Done |
| WP-2.2 | Schema package and JSON Schema export | Done |
| WP-2.1 | Design Catalog adapter and snapshots | Done |
| WP-2.3 | Open design: schedule lines, builds, readiness, review requirement | Done (gate approval in WP-4.4) |
| WP-2.4 | `ilL-System-Design`, save and revisions | Done (UI wiring in Phase 3) |
| WP-2.5 | Reconcile and copy-forward | Done (dialog UI in Phase 3) |
| WP-2.6 | Riser 1.3.0 ERP edition | Draft PR riser-diagram-generator#1; tag `v1.3.0` after merge |
| WP-3.1 | Guided shell, stepper, terms | Done |
| WP-3.2 | Spaces, cabinets, distances | Done |
| WP-3.3 | Runs screen | Done |
| WP-3.4 | Power board | Done (auto-plan in WP-4.x; dimmer devices with WP-3.5 checks) |
| WP-3.5 – WP-3.9 | Checks, verification, riser export, engineering mode, pilot telemetry | Done |
| WP-4.1 | Write-back to the schedule | Done |
| WP-4.2 | Review request type and flow | Done |
| WP-4.3 | Reviewer mode: comments, overrides, decisions | Done |
| WP-4.4 | D4 review gate before ordering | Done (flag off by default) |
| WP-4.5 | Schedule and project page integration | Done |
| WP-4.6 | End-to-end commerce test | Done |

## WP-0.1 — Portal access audit

Checked every P0 item from `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md` §5 that touches
schedules, document requests or drawing requests against the current code. All were already fixed when
the access layer was consolidated into `portal/access.py`; each has a regression test in
`illumenate_lighting/illumenate_lighting/api/test_portal_access_matrix.py` (installed-site suite).

| Item | Status | Evidence |
|---|---|---|
| P0.1 Non-dealer company users receive write/delete | Fixed earlier | `portal/access.py project_permission` grants company members read-like ptypes only (`_is_read(ptype) and not project.is_private`); schedules delegate through `schedule_permission`. Tests: `test_same_company_member_is_read_only`, `test_same_company_member_cannot_mutate_via_api` |
| P0.2 Schedule list visibility disagrees with direct access | Fixed earlier | `ill_project_fixture_schedule.get_permission_query_conditions` returns `access.schedule_query_conditions`, which mirrors `schedule_permission` including the collaborator branch. Tests: `test_schedule_list_matches_direct_access`, `test_collaborator_discovers_inherited_schedule` |
| P0.3 Document request list/count globally scoped | Fixed earlier | `api/document_requests._scoped_request_conditions` applies the doctype's `get_permission_query_conditions` to both `list_requests` and `get_request_counts`. Test: `test_request_list_and_counts_are_scoped` |
| P0.4 Drawing request accepts an arbitrary project | Fixed earlier | Both `api/portal.create_drawing_request` and `api/document_requests.create_request` go through `create_portal_document_request`, which requires `can_read_project` and resolves only active request types (never creates masters). Tests: `test_request_creation_requires_project_access`, `test_drawing_request_never_creates_request_type`, `test_request_creation_rejects_guest` |
| P0.6 Collaborator mutation policy inconsistent | Fixed earlier | `access.can_manage_project_collaborators` is the single rule, used by `update_project_collaborators`, the remove endpoint, `invite_project_collaborator` and `portal/accounts.py`. Tests: `test_collaborator_management_policy`, `test_edit_collaborator_cannot_manage_collaborators_or_privacy`, `test_other_company_dealer_cannot_invite` |

Note for WP-4.2: `ill_document_request._is_request_staff` grants request staff through the `engineering`
capability, not an explicit role list, so H4.4's "add the new role" step does not apply as written. An
Applications Engineer reaches a review request as its `technical_reviewer` (read) — WP-4.2 decides whether
`design_review` should also count as request staff.

## WP-0.5 / WP-0.6 — Role, Settings, package skeleton

- Role `ilL Applications Engineer` is created by `patches/create_applications_engineer_role.py` in
  `[pre_model_sync]`; `portal/staff.py` maps capability `design_review` to it.
- `ilL-System-Designer-Settings` (Single) holds the H4.1 defaults. The pilot list is a Table MultiSelect
  over the new child doctype `ilL-Child-Designer-Pilot-Customer` (one `customer` Link).
- `system_design/settings.py` returns the H4.1 defaults for any value the Single has never stored.
- `system_design/api.py` defines the response contract (`respond`, `fail`, `DesignError`, `endpoint`);
  `system_design/access.py` wraps `portal/access.py` and `portal/staff.py`. Unreadable and missing
  schedules both return `NOT_FOUND`.
- Discrepancy: the plan's `require_read(schedule)` takes a name; `portal/access.schedule_permission`
  takes a document, so the wrappers load the schedule and return it.

## WP-0.2 — Workspace and mount

- `tools/system_designer` is an npm workspace (`packages/*`, `app`). `npm run build` writes
  `illumenate_lighting/public/system_designer/{designer.js,designer.css}`; CI checks it is fresh.
- Routes `/portal/schedules/<schedule>/design` and `/portal/design` render `templates/pages/system_design`.
  The share route (`/portal/design-share/<token>`) is added with WP-7.4, when its page exists.
- Who sees the page: logged-in users who can read the schedule **and** for whom the designer is enabled —
  Settings `enabled`, the user's Customer in `pilot_customers`, or staff (`engineering` / `design_review`
  capability or System Manager) so the team can test before the pilot. Everyone else is redirected
  to the schedule page (or `/portal/projects` from `/portal/design`).

## WP-0.3 — Riser source

- `git subtree add` imported riser-diagram-generator `main` (v1.2.0) with history at
  `tools/system_designer/vendor/riser`. It is the untouched reference copy.
- Schemas, data, engine, drawing and serializers were copied into `packages/{core-schemas,data,engine,
  drawing,serializers}` with cross-package imports rewritten to package names; the layout worker is in
  `app/src/workers`. See `tools/system_designer/packages/README.md`.
- 21 test files / 120 tests pass (`npm test`): every riser test of the moved code plus the library
  import/editor tests.
- Discrepancies:
  - `schemas` and `data` imported each other; `general-notes.seed.json` moved to `core-schemas` to break
    the cycle. `seedLibrary()` moved from the riser's zustand store into `@ill/data/library`.
  - `serializers/pdf/fonts.ts` fetched fonts over the network; that loader moved to `app/src/lib/fonts.ts`
    so the serializer is pure. ESLint now enforces purity for the five packages.
  - The riser's screens, stores and storage (and their 5 tests) are not moved yet. They come with WP-3.8
    (engineering mode); `vendor/riser` keeps them meanwhile. The proxy and ERP sync are not carried (D1).
  - Riser has no coverage thresholds to keep. The heaviest drawing test takes ~8 s on a shared runner, so
    `testTimeout` is 30 s.

## WP-0.4 — Visualizer reference

`tools/system_designer/reference/led-tape-system-visualizer.html` is the supplied file, unchanged.

## WP-1.1 to WP-1.3 — Catalog design fields

- New fields sit in a "System Designer" section on `ilL-Spec-LED Tape`, `ilL-Spec-Driver` and
  `ilL-Spec-Controller`, plus `nominal_voltage_v` on Output Voltage and `engine_protocol` on Dimming
  Protocol. New child doctypes: `ilL-Child-Tape-Channel`, `ilL-Child-Controller-Port`.
- `patches/system_designer_tape_fields.py` fills only empty values: voltage from the attribute's text,
  engine protocol from the attribute's `protocol`/label (`system_design/protocols.py`, kept in step with
  `@ill/data/protocols.json` by a parity test), tape single-feed run from `voltage_drop_max_run_length_ft`,
  channels from the LED package's spectrum.
- The Catalog Builder's schema snapshot and bundle are regenerated whenever spec doctypes change.

## WP-1.4 — Wire spec and Items (D7)

- `ilL-Spec-Wire` (named by `item`, perms mirror `ilL-Spec-Driver`) and `ilL-Child-Wire-Conductor`.
  Rules live in `system_design/wire.py`: the Item must be sellable, enabled and not a template; Per Foot
  wire needs stock UOM Foot, Per Spool wire needs a spool length and a non-length UOM; applications must be
  engine run types; data pairs need an even count.
- `patches/create_field_wire_item_group.py` creates Item Group "Field Wire" and UOMs Foot and Spool when
  missing.
- Desk import: the "Import Field Wire CSV" button on the `ilL-Spec-Wire` list checks the file first and
  imports only when every row is valid (`system_design/wire_import.import_field_wire`, catalog staff).
  Start from `tools/seed_imports/field_wire_TEMPLATE.csv`. Conductors are written
  `2x18 Cu stranded power (red/black); 1x18 Cu stranded ground`.
- The riser's EXAMPLE `wires.seed.json` is not imported, and rows whose source reference says "example"
  are refused.
- Pricing: wire Items are ordinary sales Items, so staff add Item Price rows as for any other Item. The
  import never writes prices (D6).
- Discrepancy: the plan says "UOM Foot or a spool UOM" without naming the spool UOM; the import uses a
  whole-number UOM named `Spool`, and the spool's length lives on the spec.

## WP-1.5 — Visual fields and SH01 seed

- H4.3 fields in a collapsible "System Designer" section: profile `cross_section_file`,
  `cross_section_json`, `max_w_per_ft`; accessory cross-section fields, `clip_spacing_max_in`,
  `clip_end_offset_in`, `screw_spec`; lens `transmission_pct`, `diffusion_class`; `diagram_icon` and
  `scene_archetypes` on the fixture, tape/neon and LED sheet templates.
- `system_design/seed/sh01_cross_section.json` is the visualizer's `CAD_SH01` constant, unchanged
  (1/1000 inch, origin at the channel bottom centre). A unit test keeps it equal to the reference file.
- `patches/seed_sh01_cross_section.py` writes it to every SH01 profile spec (family or series SH01, plus
  the SH01 template's default profile) whose `cross_section_json` is empty.
- Profile and accessory saves reject malformed `cross_section_json` (`system_design/geometry.py`). DXF
  extraction from `cross_section_file` is still to come (H8.8); until then staff can paste JSON.
- The seed keeps the swivel bracket views (`swivelFront`, `swivelPlan`) because the install guide uses them.

## WP-1.6 — Third-party design data on schedule lines (D8)

- Third-party (`OTHER`) lines gain `watts_each`, `input_voltage_v`, `voltage_class`, `third_party_drive`,
  `third_party_ma` and `third_party_dimming` in a "Design Data (Data by dealer)" section.
- Dealers set them through `add_schedule_line` / `update_schedule_line`; `system_design/dealer_data.py`
  validates the merged values (0 < W ≤ 2000; V in 12/24/48/120/208/240/277; CC needs mA; dimming must be
  an existing protocol). Voltage class follows the voltage when left blank and must agree with it.
- The schedule page's add/edit third-party forms have a "System design data" block marked "Data by
  dealer", and the line shows a "Data by dealer" badge with the values.
- Write-back markers `design_line_role` and `design_line_key` are read-only and never set from the portal.
- Discrepancy: H4.3's `system_design` Link to `ilL-System-Design` is added with WP-2.2, which creates that
  doctype; a Link to a doctype that does not exist yet would fail migrate.

## WP-1.7 — Design readiness

- `system_design/readiness.py` holds the H7.2 rule table as pure functions (`tape_issues`, `driver_issues`,
  `controller_issues`, `wire_issues`, plus the A.5 `controller_category` map). Each returns
  `{status, missing, notes}`, with `missing` as ERP fieldnames. WP-2.1's catalog uses the same functions.
- Desk page **Design Readiness** (`/app/design-readiness`; catalog, engineering and Applications Engineer
  roles): product-type filter, "only incomplete", links to each record, and a volume column counting
  schedule lines from schedules changed in the last 180 days (tape through configured tape/neon and
  fixtures; drivers, controllers and wire through accessory lines and fixture driver allocations).
- Wire Items with no selling Item Price are incomplete (D7).
- The Catalog Builder shows a "Design readiness" link with the incomplete count (ERP mode only).
- Choices where Appendix A is loose:
  - Decoders need all four limits (A and W per channel and total), since A.3 lists them all as required.
  - DMX footprint and unit load are required for DMX decoders and DMX-to-0-10V converters (the DMX receivers).
  - Every controller needs at least one mapped protocol and at least one port row.
  - Sensors are reported as "not modelled", not as incomplete.
  - A multichannel tape with no channel limits is a note, not incomplete (names default to CH1…).
- WP-2.1 added the checks the engine schema enforces, so a "ready" record always parses: tape minimum
  voltage, double-feed vs single-feed run, simultaneous % vs channels, channel limit count and names;
  driver input range, DC with 3PH, terminal order, rated-current voltage, compliance range; controller
  input voltage and terminal size, decoder phase output by supply type, port rows, converter protocols
  and ports; wire listing, riser label, source, conductors, 22/24 AWG resistance, direct burial needs wet,
  building wire on 310.16, and no "wireless" cable. Decoders no longer need port rows (the engine's
  decoder has none).

## WP-2.2 — Design schema, JSON Schema and build hash

- `@ill/core-schemas/design` is the H5 `DesignSchema` (version 1) with its cross-reference rules
  (unique run keys; runs and cabinets in known spaces). `@ill/engine/derive` has `deriveLoads`.
- `npm run schema:export` (also run by `npm run build`, since Vite empties the output folder) writes
  `public/system_designer/schema/design.schema.json`. CI's bundle-freshness step covers it.
- `system_design/design_schema.py`: `validate_design_json` (JSON Schema via `jsonschema`, then the same
  cross-reference rules, then the Settings VD ceiling unless a `VD_TARGET_LOOSENED` staff override exists)
  and `build_hash`. `jsonschema` is now a declared app dependency.
- Both languages test against `packages/core-schemas/fixtures/designs` (valid, invalid, hashes, rounding).
- Discrepancies:
  - The zone colour pattern is `^#[0-9a-fA-F]{6}$` instead of `/…/i`, because JSON Schema patterns
    have no flags and the server would otherwise reject upper-case colours.
  - `deriveLoads(design)` takes no catalog: loads carry `catalogId` and the engine reads watts from the
    catalog itself. Only assigned runs become loads (a riser load needs `fedFrom`).
  - Rounding is JavaScript's `Math.round(x * 1000) / 1000` in both languages (Python's `round` is
    banker's rounding and would break parity).

## WP-2.1 — Design Catalog adapter

- `system_design/catalog.py` maps the records `readiness.load_*` loads (bulk queries, no N+1) into riser
  `CatalogItem` / `WireType` shapes (Appendix A). A record that fails a readiness rule becomes an
  `incomplete` item with the same ERP fieldnames in `missingFields`, so the report and the designer agree.
- Ids: `tape:{spec}:{W/ft}:{cut mm | free}` (one per W/ft and cut group of active offerings),
  `drv:{spec}`, `ctl:{spec}`, `wire:{item}`. Units per H7.3, rounded to 4 decimals.
- D6: `rank` is a dense rank over (eligibility priority desc, driver cost asc, item code asc) for ready
  supplies. Cost is read only for that ordering; `build_payload` refuses any payload carrying a forbidden
  key, and both test suites walk the payload for them.
- `ilL-Design-Catalog-Snapshot` stores each payload once, gzip + base64, named by its SHA-256 (read:
  System Manager, ilL Engineering, ilL Applications Engineer). Cache keys `ill:design_catalog:<hash>`
  (24 h) and `ill:design_catalog:current`; `doc_events` on the mapped doctypes (and Item, Item Price)
  call `catalog.invalidate`, and the next read rebuilds lazily.
- Endpoints in `system_design/api.py`: `get_catalog(hash?)` (`can_view_catalog`; `NOT_FOUND` for an
  unknown hash) and `get_catalog_for_desktop()` (engineering capability, for WP-2.6).
- Parity: `packages/core-schemas/fixtures/catalog/erp-records.json` (TEST records) builds the committed
  `payload.json`; Python checks the mapping still produces it and Vitest parses it with
  `CatalogItemSchema`, `ProductLibrarySchema` and `WireLibrarySchema`.
- Schema additions (optional, so the riser's own data still parses): `CatalogItem.rank`,
  `usableLoadFactor` on supplies and drivers, and `erpItemCode`, `salesUom`, `spoolLengthFt` on `WireType`.
- Discrepancies and choices:
  - Phase dimmers stay out of the snapshot: the engine has no `phase-dimmer` category yet. The readiness
    report still checks their data and says so in a note.
  - Wires that are not ready (including no selling Item Price, D7) are left out of `wires`; there is no
    incomplete wire shape in the engine.
  - A controller with no standby power counts 0 W, with a readiness note.
  - Tape specs have no active flag, so a tape is in the catalog when its Item is enabled and it has an
    active offering. Drivers need an enabled sales Item; wires an enabled sales Item.
  - A tape spec split into several groups gets a distinct `sku` per group (the library requires unique
    SKUs); `erpItemCode` stays the tape Item.
  - Empty Float fields read as 0 in Frappe, so wire rules now treat 0 as "not entered" and only refuse
    negative resistance, ampacity, impedance and diameter.
  - Snapshots built while serving a GET request are committed explicitly (Frappe does not commit GETs).
  - `ENGINE_CONTRACT_VERSION = "catalog-1"`, `CODE_TABLES_VERSION = "nec-2023-1"` until WP-3 owns them.

## WP-2.3 — Open design

- `system_design/expansion.py` turns a schedule into `lines` (camelCase, one per schedule line with its
  `kind`: configured, third-party, accessory, unconfigured or writeback), `builds` (per configured doc:
  runs, allocations, catalogId, environment, protocols, issues) and a `readiness` summary (ready,
  needs_data, unconfigured, catalog_gaps, missing_line_keys). Builders cover Configured Fixture,
  Configured Tape/Neon, LED Sheet and Configured Group; docs load in bulk.
- `system_design/gate.py` answers the D4 review requirement. It is off unless the Settings switch and the
  `ill_system_design_review_gate` site flag are both on. Reasons: total load over the threshold, DMX,
  phase dimming.
- Endpoints (GET, designer flag required): `open_design(schedule, design?)`, `find_schedules(query,
  limit)` and `review_requirement(schedule)`.
- TypeScript: `core-schemas/src/open-design.ts` parses the payload; `engine/src/expand.ts` expands lines
  and builds into spaces and runs (`{key}:{copy}:{runIndex}`; a line with qty at or above the group
  threshold gets one group id).
- Parity: `fixtures/open-design/erp-records.json` builds the committed `expected.json`; Python checks it
  and Vitest expands it.
- Discrepancies and choices:
  - Feed method: tape and neon are end-fed; linear fixtures map Middle to center and end-fed
    `feed_direction` to double-end, otherwise end.
  - LED sheets have no engine product yet, so they report a catalog gap (`sheet:{spec}`).
  - A group takes its catalogId from its members and has no environment of its own; the space
    environment applies. Unknown environment values also fall back to the space environment.
  - Spaces come from line locations (`space-{slug}`, or `unassigned`).
  - A line with no `line_key` gets `{line_id}-{idx}` and is listed in `missing_line_keys`.
  - A required review always reports `satisfied: false`; approval and overrides landed in WP-4.4.
  - `has_design` in `find_schedules` and the `design` argument of `open_design` wait for the
    `ilL-System-Design` doctype (WP-2.4); a design argument returns `NOT_FOUND` until then.

## WP-2.4 — Saved designs and revisions

- Doctypes: `ilL-System-Design` (`SYSD-.YYYY.-.#####`, track changes) with `ilL-Child-Design-Deliverable`,
  `ilL-Child-Design-Share` and `ilL-Child-Design-Comment`, as H4.1. Role rights: System Manager full,
  ilL Applications Engineer read/write/create, ilL Engineering read. Schedule lines gain the read-only
  `system_design` Link (H4.3), completing the WP-1.6 note.
- `has_permission` and `permission_query_conditions` hooks: design staff (`design_review` or
  `engineering`) and Administrator keep their role rights; anyone else gets the schedule's decision
  (`read` for read types, otherwise `write`). Dealers have no role rights on the doctype, so they reach
  designs only through the endpoints.
- `save_design(schedule, design_json, design_name?, expected_modified?)` (POST): requires schedule edit
  rights (`LOCKED` on a locked schedule), the designer flag, ≤ 5 MB, a valid design (H5 schema, references,
  D5 ceiling), the same schedule and version, and a known catalog snapshot. Updates lock the row and compare
  `expected_modified` (`CONFLICT` when stale); only the current revision in Draft or Changes Requested can
  change (`LOCKED` otherwise). A second new design for the same schedule version is a `CONFLICT`.
- Stored per save: canonical design JSON, build hash, H8.4 line fingerprints (`reconcile.fingerprints`),
  a result summary and the D4/D8 flags (connected load, DMX, phase dimming, dealer data, review reasons).
- `create_revision(design, note?)` (POST): copies the current revision to the next letter (A … Z, AA …)
  as a Draft, clears review, approval, terms, deliverables, shares and comments, and sets the old one
  `is_current = 0`. The note becomes a comment on the new revision.
- `open_design` now returns the current revision for the schedule version (or the named one, `NOT_FOUND`
  if it belongs to another schedule) with `design_meta`; `find_schedules` fills `has_design`.
- Client (`app/src/design/`): a zustand store with zundo undo (design only, 100 steps), a Dexie
  IndexedDB draft per schedule, and an endpoint client. A draft is restored only when it was made on the
  same saved revision and timestamp; a successful save drops it, a conflict keeps it.
- Discrepancies and choices:
  - `error_count` and `warning_count` stay 0 until server verify (WP-3) computes them.
  - `expected_modified` is required when updating an existing design.
  - `create_revision` needs schedule edit rights, so a locked schedule cannot start a revision.
  - The old revision keeps its status; only `is_current` changes, as H6 states.
  - The store is not wired into the page yet; the designer UI arrives in Phase 3.

## WP-2.5 — Reconcile and copy-forward

- `system_design/reconcile.py` and `packages/engine/src/reconcile.ts` compute the same H8.4 line
  fingerprint and the same diff: `added`, `removed` (with the runs and assignments that drop), `changed`
  and `qty`, plus `in_sync`. `fixtures/reconcile/case.json` (one change per category) is generated by
  Python and checked by Vitest.
- `applyReconcile` (engine) updates a design's runs: removed lines drop their runs, added lines arrive
  unassigned, changed lines take the new ERP values but keep the designer's fields (space, environment,
  home run, assignment, zone) by run key, and a quantity change adds or drops copies from the end.
  Spaces for new runs are added.
- `open_design` returns `reconcile` for a saved design; `reconcile_design(design)` (GET) returns the
  same diff. `save_design` refuses an update while the schedule has changed (`CONFLICT`) unless the
  client sends `reconciled=1` after applying the diff; the save then stores fresh fingerprints.
- `copy_design_to_version(design, target_schedule)` (POST) starts revision A on another version of the
  same schedule (same `version_parent` root), pointing `revision_parent` at the source. It keeps the
  source's fingerprints, so opening the copy shows what changed between versions.
- Client: the store holds the pending diff; a save is blocked until `acceptReconcile` (undoable) runs.
- Discrepancies and choices:
  - Fingerprints are stored as `{key: {fingerprint, qty}}` rather than bare hashes, so a quantity-only
    change can be told apart from a changed build. Bare hashes are still read; any difference then
    counts as `changed`.
  - Copying is limited to versions of the same schedule; the plan does not say whether other schedules
    in the project qualify.
  - The reconcile dialog itself is part of the Phase 3 designer UI; the data it shows is ready.

## WP-2.6 — Riser 1.3.0 "ERP edition"

- In `riser-diagram-generator` (draft PR #1): the loopback proxy's `GET /api/erp/catalog` calls
  `get_catalog_for_desktop` with the staff API key from `.env`. Libraries → **ilLumenate catalog**
  replaces ERPNext Sync. The Item pull, the demo records and the `custom_riser_*` mapping are removed.
- Catalog products are read-only, with no local overrides. Duplicate makes a local variant. Products that
  leave the catalog stay, read-only, so existing projects open.
- README and user guide carry the deprecation notice pointing to the System Designer.
- Discrepancies and choices:
  - The riser schema gained the optional `usableLoadFactor` (it is strict, and the catalog sends it). The
    riser engine uses it only to tighten the operating-target warning.
  - The planner `rank` (D6) is stripped on load.
  - The catalog test fixture is a copy of `fixtures/catalog/payload.json`. Update it there when the
    contract changes.
  - Tagging waits for the merge so the tag points at `main`.

## WP-3.1 — Guided shell, stepper, terms

- The designer now opens the schedule (`open_design`), starts a design from its lines when none is saved
  (`app/src/shell/open.ts`, `newDesign`: spaces and runs from `expandRuns`, VD targets, waste and NEC
  edition from Settings), and restores a matching browser draft.
- Shell (H9):
  - The header has the product name (D2), schedule and version, revision, status and review chips, save
    state ("Saved · 12:04"), Save (also Ctrl+S), the Guided/Engineering toggle and help.
  - Guided mode shows a stepper (Start, Spaces, Runs, Power, Check, Views, Finish) with Back and Continue.
    Engineering mode shows the same screens as tabs.
  - A collapsible check panel shows severity counts with icons.
- Start: readiness counts, the D4 review banner with its reasons, a banner to apply schedule changes
  (`applyReconcile`, undoable, then the save sends `reconciled`), and the locked-version banner.
  "Design on version N" copies the design forward (`copy_design_to_version`) and opens it; without a
  newer version it links to the schedule page.
- Terms: a modal on first open of a revision the user can edit. `save_design` refuses a revision that
  nobody accepted (`INVALID`) and stamps `terms_accepted_by/on` from the first save that sends
  `terms_accepted`. `design_meta.terms_accepted` tells the client.
- Discrepancies and choices:
  - Terms acceptance is per revision, recorded with the save, because a design record does not exist
    until the first save. A new revision asks again (its terms fields are reset).
  - `terms_text` is a Text Editor field; `open_design` sends it as plain text because the designer renders
    no HTML (plan 15.6).
  - The check panel starts from the readiness gaps; engine checks join it in WP-3.5.
  - Steps after Start show their purpose until their work packages land.
  - The Engineering toggle is shown to everyone for now; WP-3.8 limits it.
  - `crypto.randomUUID` needs a secure context, so the bundle smoke test runs on an HTTPS origin, as the
    portal does.

## WP-3.2 — Spaces, cabinets, distances

- `packages/engine/src/site.ts` holds the site edits; the app runs each inside one undoable store edit:
  - Rename and merge spaces.
  - Add, edit and remove cabinets. A cabinet holding equipment cannot be removed.
  - Add, edit and remove panel circuits (riser sources), and link a cabinet to one.
  - Set home-run and cabinet-feed lengths.
- Distances: the quick picks (same space, adjacent space, other level) come from Settings, with the plan's
  10 / 25 / 40 ft as fallbacks. A quick pick is an `estimate`; a typed length is `entered`.
- Environments: `packages/data/src/environments.ts` is the Appendix B.2 table.
  - Space, cabinet and run gained an optional `envChoice` that keeps the dealer's pick (in-wall, damp);
    `env` stays the engine value. This is an additive field in schema version 1.
  - A space's change cascades to the cabinets and runs that still follow it. Ones set separately, or
    taken from an ERP environment rating, keep theirs. A cabinet's location rating follows its
    environment and can be changed.
- The Spaces screen shows space cards (name, level, environment, merge), cabinet cards (tag, name,
  environment, rating, access note, circuit, feed length) and the runs in each space. Third-party runs
  carry the "Data by dealer" chip (D8). Bulk "set all home runs" picks apply per space. Panel circuits
  are listed at the end.
- The header gained Undo and Redo (Ctrl+Z, Ctrl+Y or Ctrl+Shift+Z outside text fields).
- Discrepancies and choices:
  - A line without a location now lands in a space named "Project" (H9), not "Unassigned".
  - Cabinet → run environment cascade needs supply assignments, so it comes with the Power board
    (WP-3.4).
  - The in-wall listing rule is recorded (`needsInWallListing`) and applied in wire selection
    (WP-3.5).

## WP-3.3 — Runs screen

- `packages/engine/src/runs.ts` holds run labels, product type, feed positions, grouping and the
  run-level checks. The app shows the checks on each row, in the strip preview and in the check panel,
  and recomputes them on every edit.
- Checks (§9.3, Appendix C codes):
  - `TAPE_RUN_TOO_LONG` (error) when a run is longer than its build's `maxRunFtEffective`.
  - `MAX_LENGTH_HINT` (info) above 90% of that length.
  - `INVALID_SPEC` (warning) when a double-end run lists other than 2 feeds, or a multi-feed run has no
    feed count.
  - Jumper-connected tape runs already arrive as one run from the ERP expansion (`connected_runs`), so
    each run is one circuit and needs no separate check.
- The Runs screen is a table: run, type, space, length, watts, feed, environment, home run with
  provenance, supply and status. It filters by space.
  - Select runs to move them to a space, set their environment or home run (typed or quick pick)
    together. Each bulk edit is one undo step.
  - Identical copies fold into one group row (threshold from Settings). Groups can be expanded, split,
    and rebuilt from runs of one schedule line. Runs on different supplies cannot be grouped.
  - Choosing a run shows its strip to scale against the build maximum, with its feed points.
- Discrepancies and choices:
  - Lengths, watts and feeds stay read-only (they come from the configured build), so "split" means
    splitting a group. A run that is too long is fixed in the configurator, which the check says.
  - Run labels moved from the Spaces screen into the engine package.

## WP-3.4 — Power board

- Server: `eligible_supplies(schedule, run_keys, location_rating?)` in `system_design/supplies.py`.
  - A supply qualifies when it is a complete constant-voltage catalog supply at the runs' voltage, is
    allowed for every configured product's template (`ilL-Rel-Driver-Eligibility`), accepts the
    supply-dimmed protocol a product needs (phase-cut, 0-10V, DALI-2), and its `location_rating` on
    `ilL-Spec-Driver` is at least the cabinet's.
  - Rows are `{catalog_id, item_code, rank, location_rating}`: the opaque D6 rank and nothing about cost.
  - Line-voltage third-party lines are refused: they are fed from a panel circuit.
- Engine: `packages/engine/src/power.ts`.
  - Supplies are sized against `ratedW × usableLoadFactor` and each output against
    `maxW × usableLoadFactor` (the project operating target when the ERP has no factor).
  - Assignment refusals give the reason: line voltage, constant-current supply, voltage, protocol, zone
    method, two zones on one output, output or supply over its usable rating.
  - Add, move and remove supplies. A supply takes its cabinet's environment, circuit and feed length, and
    follows later cabinet changes (the WP-3.2 cascade). Removing a circuit unlinks what it fed.
  - Picker order is by fit: one supply that carries the runs first, then fewest supplies, then smallest,
    then rank. Never by price.
  - "Start from configurator supplies" places one supply per build copy and allocation, marked "From
    configurator", in a cabinet in the run's space (added when the space has none).
  - Zones carry a dimming method. Runs in a zone must be on supplies that accept a supply-dimmed method.
    DMX or phase-cut zones, or more than 1.5 kW, show the D4 review note on the board.
- App: the Power step. Unassigned runs by space on the left; cabinets with supply cards, load bars (80%
  guide line), outputs with Class 2 badges, assigned runs and the circuit on the right.
  - Drag runs onto an output, or select them and press "Assign here" (keyboard).
  - The catalog snapshot is loaded once per hash with `get_catalog`; example products are dropped.
- Tests: engine `power.test.ts`; Python `test_system_design_supplies.py`; installed
  `test_open_design.test_eligible_supplies`; jsdom `PowerStep.test.tsx`; Playwright drag and refusal in
  `tests/e2e/smoke.spec.ts`.
- Discrepancies and choices:
  - DMX zones dim through decoders, so the supply is not checked against DMX; decoders, dimmers and
    phase-cut device limits come with the checks in WP-3.5.
  - Run environments stay as set on the Spaces and Runs steps; the cabinet cascade applies to the
    supplies inside the cabinet.

## WP-3.5 — Engine integration and checks UI

- Engine: `packages/engine/src/designCheck.ts`.
  - `checkDesign` runs the riser engine on the design's derived loads, then adds the run-level checks
    and the designer's Appendix C checks. It is pure and runs in a Web Worker
    (`app/src/workers/engine.worker.ts`), re-running a short pause after each edit; stale answers are dropped.
  - Voltage-drop targets (D5) come from Settings. A project may tighten them. Only an Applications
    Engineer loosens one, with a reason, recorded as a `VD_TARGET_LOOSENED` staff override; a saved looser
    value without that override is ignored.
  - In-wall runs are sized only from CL2 or CL3 listed cable (CL2, CL2R, CL2P, CL3, CL3R, CL3P).
  - Wire selection uses the catalog's wire types. "Use a heavier wire" pins the next heavier passing size
    as a wire override; "Back to automatic" removes the pin.
  - Third-party lines (D8) become `tp:{key}` fixture items marked "Data by dealer". Line-voltage
    third-party fixtures are fed from a panel circuit on the Power step.
  - Designer checks added: run not on a supply or circuit (one per space), supply not on a circuit yet,
    cabinet with no access note, data by dealer (one per line), schedule changed since the design was
    built, ilLumenate review required, and a note when a target was loosened.
  - Acknowledgements (§11.5): dealers accept warnings with a reason; errors need an Applications
    Engineer override. Accepted checks show as notes with the reason and can be withdrawn.
- App: the Check step shows the targets, every check with its fix (heavier wire in place, or the step
  where it is fixed), accept and withdraw, sized home runs (wire, length, current, voltage drop against
  the target, end voltage) and pinned wires. The checks panel follows the same results on every step.
- Server: `open_design` returns the signed-in `user`, recorded on acknowledgements and overrides.
- Bundle: the engine worker is a separate committed asset under `public/system_designer/assets/`.
- Tests: engine `designCheck.test.ts`; jsdom `CheckStep.test.tsx` and the line-voltage case in
  `PowerStep.test.tsx`; Playwright runs the checks in a real worker in `tests/e2e/smoke.spec.ts`.
- Discrepancies and choices:
  - The NEC code tables ship in the bundle on their own (`@ill/data/codeTables`) so the EXAMPLE seed
    products never reach the browser.
  - Run-length checks already listed by the Runs step are not repeated from the engine.
  - Dimmer minimum load, LED maximum and neutral checks have codes reserved but wait on dimmer data in
    the catalog; they are not reported yet.

## WP-3.6 — Python verification mirror

- Golden fixtures: `tools/system_designer/fixtures/golden/`, 14 cases. Each is `<name>.input.json`
  (design, catalog subset, wires, VD limits) and `<name>.expected.json` (engine runs, all messages,
  build hash and the `verify` subset). `packages/engine/test/golden.test.ts` builds the cases and
  checks the engine against them; `UPDATE_GOLDEN=1` rebuilds both files.
  - Cases: cove-24v-single, cove-too-long, class2-over, vd-over-target, tape-undervoltage, in-wall,
    third-party-mixed, voltage-mismatch, pixel-tape, two-output-supply, kitchen-zones, load-over-1500,
    load-at-1500, incomplete-product.
- Engine: `packages/engine/src/verify.ts` (`verifySubset`) and `reviewTriggers` in `power.ts` (the
  D4 triggers from the design, which `reviewHints` now uses).
- Python: `system_design/verify.py` re-computes the §18.2 subset: supply and output loading against
  ratings and the operating target, Class 2 output load, tape run length, voltage drop and wire
  selection on single-channel Class 2 DC runs (Chapter 9 Table 8), the in-wall CL2/CL3 rule, voltage
  match, dealer data (D8) and the D4 triggers. `compare` lists each disagreement with both values.
  - The NEC tables are copied to `system_design/code_tables/` by `npm run schema:export`; CI fails when
    the copies are stale.
- Endpoint: `verify_design(design, client?)` (POST) re-checks a saved design against its catalog
  snapshot and stores the outcome in the new `verification_json` field on `ilL-System-Design`.
  Returns `{ok, mismatches:[{code, entityRef, client, server}], summary}`.
- App: after each save the designer sends its own subset; a disagreement shows a banner and stays on
  the design for the reviewer. A failed verify call never blocks the dealer.
- Tests: `golden.test.ts`; `tests/portal_unit/test_system_design_parity.py` (all golden cases, dealer
  items, code tables, compare, targets); installed `test_designs.test_verify_design_on_the_server`;
  jsdom save-and-verify in `App.test.tsx`.
- Discrepancies and choices:
  - The plan's `riser-example`, `phase-dimmer-min-load`, `dmx-tw-rgbw` and allocator cases wait on
    their features (riser import, dimmer data, DMX patching in the designer, WP-5 allocator).
  - Protocol match is enforced when runs are put in zones (WP-3.4); the engine's control-link
    `PROTOCOL_MISMATCH` joins the mirror when the designer draws control links.
  - Multichannel and line-voltage wire sizing stay with the engine; their loading is still verified.

## WP-3.7 — Engineering riser outputs

- Riser from the design: `packages/engine/src/riser.ts` (`riserProject`) turns the project the checks
  ran on (now on `DesignCheck.project` and `.library`, in-wall wires included) into the drawing input:
  title block from the ERP (project, number, site, dealer, designer, checker), sheet, stamp, a design
  revision row, the design-aid general note and, when any load has dealer data, "Third-party product
  data entered by <dealer>; not verified by ilLumenate" (D8, §22.3).
  - `open_design` now returns `title_block` (`project_name`, `project_number`, `site_address`,
    `customer`, `dealer_logo`), `deliverables`, and `design_meta.approved_by` on approved revisions.
- Stamps: PRELIMINARY by default; NOT FOR CONSTRUCTION and FOR REFERENCE; REVIEWED BY ILLUMENATE only
  on an approved revision, which also names the approving Applications Engineer as checker. Another
  stamp on an unapproved revision falls back to PRELIMINARY.
- Sheets: Letter (`ANSI_A`, 11 × 8.5 in, new title block) and Tabloid (`ANSI_B`) join ARCH C/D and
  ANSI D. Every sheet now prints the NEC edition and the voltage-drop targets under the sheet count.
- DATA BY DEALER: dealer fixtures show maker, model and the tag on their symbol and LOAD SCHEDULE row;
  their BOM row shows the tag in place of the internal `tp:` id.
- Dealer logo: `Customer.dealer_logo` (Attach Image) by patch `add_customer_dealer_logo`. The browser
  reads it, scales it to at most 800 px and passes it as a PNG data URL (`DrawingOptions.dealerLogo`);
  the brand cell shows ilLumenate above and the dealer below. Sheets carry it as `images`: PDF and SVG
  embed it; DXF has no raster and leaves it out.
- Metadata (D2): `serializePdf(…, {creator, keywords})` writes `Creator: ilLumenate System Designer`
  and schedule/design/revision keywords; DXF starts with a `999 Creator:` comment; SVG gets a
  `<metadata>` line. The riser generator keeps its own creator by default.
- Views step: pick sheet and stamp, draw the riser (layout worker), preview each sheet, download PDF,
  DXF ZIP (with fonts) or the shown sheet as SVG. Files are named
  `ilLumenate-System-Designer_<schedule>_rev<rev>_<sheet>.<ext>`. When the design is saved with no
  unsaved changes and the user can edit the schedule, each download is also stored on the revision.
  - Drawing fonts are now published with the bundle (`?url` imports, about 0.9 MB).
- `upload_deliverable(design, kind, variant, sha256, build_hash?)` (POST multipart, file in `file`):
  checks edit access (a locked schedule may still export), kind (Riser PDF / DXF ZIP / SVG), the file
  itself (PDF via `validate_content`; ZIP of `.dxf` drawings and their fonts only, with size and count
  limits; SVG without scripts, event handlers, entities or external links), recomputes the SHA-256,
  stores a private File and inserts the `ilL-Child-Design-Deliverable` row alone so the design's
  `modified` is unchanged. The same file sent twice returns the existing row.
- Tests: `packages/drawing/src/riser.test.ts` (title block, tags, notes, stamps, Letter with logo,
  PDF metadata, DXF round trip), `ViewsStep.test.tsx`, `test_system_design_deliverables.py`,
  installed `test_designs.test_upload_a_riser_deliverable`.
- Discrepancies and choices:
  - Schedules on the riser are the engine's tables from the ERP-sourced design; the plan's separate
    panel/circuit table is part of the equipment schedule's feed column.
  - The DXF ZIP has no dealer logo (no raster in DXF); PDF and SVG do.
  - The default sheet is Tabloid; Letter suits small systems.

## WP-3.8 — Engineering mode

- Access: always on for ilLumenate staff (new `permissions.can_engineer`: the `engineering` or
  `design_review` capability), who open in Engineering mode. Dealers turn it on with "Engineering
  tools" in the header; the choice is kept in the browser (`ill-sd:engineering-opt-in`).
- Engineering mode shows the steps as tabs plus a Grids tab (`app/src/engineering/EngineeringTab.tsx`,
  loaded on demand with AG Grid, the riser's grid):
  - Circuits, Equipment and Control links edit `design.project` through the design store, so undo,
    drafts and the checks work as on the guided steps. Each edit is checked against the project schema
    (`app/src/engineering/grids.ts`); tags stay unique; removing supplies or circuits uses the guided
    helpers, which release runs and cabinets, and drops control links to removed equipment.
  - Loads are read-only: they come from the runs (change them on the Runs step).
  - A QA column shows each row's engine messages.
  - Settings: NEC edition, units, drawing font, schedules on the riser, riser flow, wire waste and DMX
    patch rounding for everyone; operating target, continuous load factor, breaker limit, tape margin,
    termination rating, smallest line-voltage wire, VD methods and DMX/SPI limits for staff only.
    Voltage-drop targets stay on the Check step (Settings limits, D5).
- Tests: `grids.test.ts`, `EngineeringTab.test.tsx`, App opt-in and staff tests, and an e2e test that
  edits equipment in the grid of the committed bundle.
- Discrepancies and choices:
  - Settings that make a design less conservative are staff-only; the plan says "all settings" for
    engineering mode without separating dealers and staff.
  - Riser layout pins are edited on the drawing, which the designer does not show interactively yet.

## WP-3.9 — Pilot enablement and telemetry

- Pilot customers are the Settings `pilot_customers` table (WP-0.5); `is_enabled_for` admits their
  users before the global switch.
- Events: `system_design/telemetry.py` writes `ilL-Portal-Event` rows keyed
  `system_design:<event>:<design or schedule>:<timestamp>:<nonce>`, with `subject` = user and a JSON
  `message` (event, schedule, design, small details; never prices). No delivery rows, so no email.
  A failed insert rolls back to a savepoint and is logged; it never fails the work it describes.
  - Server-recorded: `opened` (`open_design`), `saved` (`save_design`, with the revision) and
    `riser_exported` for stored files (`upload_deliverable`).
  - Browser-reported through `log_event(schedule, event, design?, details?)`: `riser_exported` for a
    download that was not stored, `check_fixed` (codes of errors or warnings that went away after an
    edit; accepting a check does not count) and `feedback` (rating 1–5, optional comment). Details are
    typed and trimmed server-side; other events are refused.
- Feedback prompt: after the first riser export on the Views step, once per design per browser.
- Metrics: Script Report **System Designer Pilot** (System Manager, ilL Engineering, ilL Applications
  Engineer): per schedule, customer, users, opens, saves, risers, checks fixed, minutes from first open
  to first riser (plan §23 "schedule → checked riser"), average rating and comments.
- Tests: `test_system_design_telemetry.py`, `test_system_designer_pilot_report.py`, installed
  `test_designs.test_pilot_telemetry_rows`, CheckStep and ViewsStep jsdom tests.
- Discrepancies and choices:
  - An undo that removes a problem's cause also counts as a fixed check.
  - The key adds a short nonce after the timestamp so two events in the same microsecond stay unique.

## WP-4.1 — Write-back

- `system_design/writeback.py`, endpoints `writeback_preview` and `writeback_apply`, Finish step
  (`app/src/shell/FinishStep.tsx`).
- Desired lines: equipment of the saved design, by catalog snapshot item → Item code and role (psu and
  driver → Supply; decoder and controller → Controller; accessory → Accessory), summed per Item, with the
  cabinet names as location; wire by the engine's BOM footage (waste included), whole feet or whole
  spools (D7). Example, tape, fixture and unknown products are listed as "blocked" and never written.
- Lines are ACCESSORY lines keyed `design_line_key = "<role>:<item>"` with `system_design` and
  `design_line_role`; line ids `PS1`, `CTRL1`, `WIRE1`, `ACC1`, skipping ids in use. Lines without
  `design_line_role` are never touched. Item checks reuse `api/portal.py orderable_item_problem`, now
  shared with `add_schedule_line`.
- Consolidation: configurator supply lines (`power_supply_for_line`) of lines with a run assigned in the
  design are offered as `replace:<owner line_key>` and removed with `power_supply_lines.clear_power_lines`.
- Apply writes only accepted keys in one transaction (rolled back on any error), then stores the
  schedule's new fingerprints on the design without changing its `modified`, so the open editor still
  saves. Preview and apply refuse (`CONFLICT`) a design that is not current or not in step with its
  schedule.
- Price delta: `Standard Selling` Item Prices of the changes, only for users with `Can View Pricing`;
  Items without a price are named, never guessed.
- Tests: `tests/portal_unit/test_system_design_writeback.py` (rounding, re-apply idempotence,
  consolidation, price delta), installed `test_designs.test_write_back_supplies_and_wire` (apply,
  idempotent preview, rollback), `FinishStep.test.tsx`.
- Discrepancies and choices:
  - Wire selection for every run type runs in the browser, so the client sends `wire_feet`; the server
    checks each wire is a catalog wire with an Item and the footage is a sane number. A dealer could send
    other footage, but could add the same wire lines by hand anyway.
  - `writeback_preview` also accepts POST (the footage would make a long query string).
  - Write-back lines from an earlier revision count as the design's own and move to the current one.

## WP-4.2 — Review request type and flow

- Patch `add_system_design_review_request_type` seeds the H4.2 `ilL-Request-Type` (post model sync;
  an existing record is left as staff edited it).
- `system_design/review.py request_review(design, priority, due_date?, note?, error_count, warning_count)`
  and the Finish step's review card. The revision must be current, Draft or Changes Requested, saved,
  and free of errors: the browser sends its open error and warning counts (overrides excluded), and the
  server re-runs its gating subset and refuses PSU_OVERLOAD, VOLTAGE_MISMATCH or TAPE_UNDERVOLTAGE
  without an Applications Engineer override.
- The request links the project, schedule and design (`reference_doctype` = ilL-System-Design), is
  owned by the schedule's customer and starts Submitted, so the SLA, assignment, task and notification
  run as for any request. Changes Requested → sending again reuses the revision's request.
- Reviewer: Settings `reviewer_assignment` "Round Robin" picks the next enabled System User with
  `ilL Applications Engineer` after the last one assigned (name order); "Manual" leaves it to Desk.
- Access (the WP-0.1 open point): on System Design Review requests, `design_review` counts as request
  staff (`_is_request_staff`), Applications Engineers list them, and a reviewer needs no project
  collaboration. Design staff read the schedules behind designs (`system_design/access.require_read`).
- `drawing_impact.request_build_hash` returns the design's `build_hash` for requests that reference a
  design, so published reviews fingerprint the saved design build (WP-4.3).
- The generic portal request form no longer offers "System Design Review"; only the designer files it.
- Tests: `tests/portal_unit/test_system_design_review.py`, installed `test_designs.test_request_review`,
  `FinishStep.test.tsx`.
- Discrepancies and choices:
  - The plan requires "0 errors"; full checks run in the browser, so the server trusts the reported
    count and enforces only the errors it can recompute.
  - Inserting the request skips the portal request validation once (a dealer may not link a schedule
    or name a reviewer); the Draft → Submitted save then runs it as usual.

## WP-4.3 — Reviewer mode

- `system_design/review.py`:
  - Comments: `list_comments`, `add_comment(design, body, view, anchor?)`, `resolve_comment`. Anchors are
    `{sheet, x, y}` fractions of the sheet and/or `{entityRef}`. Applications Engineers and people who
    can edit the schedule comment; comment rows are inserted without saving the design, so an open
    editor's `expected_modified` still holds.
  - `override_check(design, code, entity_ref, reason)`: the reviewer accepts one error on a design in
    review. The override is written into `design_json` (kind `staff-override`) and the build hash is
    recomputed, so the riser must be drawn and kept again before deciding.
  - `review_decide(design, "Approved" | "Changes Requested", note)`: only the request's
    `technical_reviewer`; asking for changes needs a note. The newest Riser PDF kept on the current
    build is published on the request as a "System design riser" deliverable, then the decision goes
    through `portal/drawing_review.decide` with the current revision token. Approval sets
    `approved_review/by/on`; the request becomes Completed (approved) or Waiting on Customer.
- `deliverables.upload_deliverable`: Applications Engineers keep files on designs they review; a
  re-upload of the same bytes is new when the build hash changed.
- Browser: the Finish step's review card shows the reviewer panel (overrides with a reason, note,
  Approve / Request changes; Approve waits until no error is open), a "Start the next revision" action
  on an approved revision, and the general comment thread. The Views step keeps the riser for
  reviewers and pins comments on a sheet (click the preview with "Pin a comment" ticked).
- Tests: `tests/portal_unit/test_system_design_review.py` (anchors, overrides), installed
  `test_designs.test_review_comments_override_and_decision`, `FinishStep.test.tsx`, `ViewsStep.test.tsx`.
- Choices:
  - Overrides are done on the server while the design is In Review (read-only in the editor), rather
    than as editor changes saved by the reviewer.
  - Pins store sheet fractions, so they stay put when the sheet is redrawn at another size but may
    drift if a later revision changes the layout; the comment text still applies.

## WP-4.4 — D4 review gate

- `system_design/gate.py`:
  - `review_requirement(lines, builds, values, design?, prints?, override?)` adds the current design's
    DMX / phase-cut zones to the line reasons and is satisfied by an Approved current design whose
    `line_fingerprint_json` equals the schedule's fingerprints now, or by an active override.
  - `schedule_requirement(schedule_doc)` loads all of that for one schedule; `open_design` and the
    `review_requirement` endpoint use it.
  - `override_review_gate(schedule, reason)` (`sales` or `design_review` capability; endpoint of the same
    name) records an `ilL-Portal-Event` keyed `system_design_gate_override:<schedule>:<sha256 of the
    fingerprints>`, so it lapses when the lines change; repeating it is a no-op.
  - `order_block(schedule_doc)` runs at the end of `can_request_schedule_order` (button, endpoint and
    conversion). With the `ill_system_design_review_gate` site flag off it returns at once and never
    blocks; with it on, an unexpected failure is logged and blocks with a support message.
- Schedule page: when the gate is what stops ordering, its reason shows under the order buttons.
- Designer: the review card says whether the approved design or an override allows ordering, warns
  when the schedule changed after approval, and lets Applications Engineers allow ordering without
  review with a reason. The header chip reads "Review overridden" in that case.
- Tests: `test_system_design_expansion.Gate`, installed `test_designs.test_review_gate_before_ordering`,
  `FinishStep.test.tsx`.
- Choices:
  - A write-back after approval keeps the approval valid: write-back lines are outputs of the design
    and are left out of the fingerprints, and replaced configurator supplies update the design's
    stored fingerprints in the same transaction.
  - Order Approvers override through the endpoint; the designer shows the override only to
    Applications Engineers (a schedule-page control can follow if sales wants one).

## WP-4.5 — Schedule and project pages

- `system_design/portal_pages.py`:
  - `schedule_card(schedule_doc)` → `{url, design: {name, revision, status, tone}, review: {label, tone}}`
    for the schedule page, or `None` when the designer is not enabled for the user.
  - `project_designs(schedules)` → the current designs of the project's readable schedule versions,
    newest first, or `None` to hide the tab.
  - `review_chip(requirement, status)`: Review required / In review / Review approved / Review
    overridden; nothing when the gate does not apply.
  - Both log and return `None` on any failure, so the pages render as before.
- `schedule.html`: "Design System" (no design yet, editors only) or "Open System Design" button, a
  design badge (revision and status, linking to the designer) and the review chip beside the status.
- `project.html`: a "Designs" tab listing the current designs, shown only when the designer is on for
  the user.
- Tests: `tests/portal_unit/test_system_design_portal_pages.py`, installed
  `test_designs.test_schedule_and_project_pages`, `tools/check_portal_templates.py`.

## WP-4.6 — End-to-end commerce test

- `tools/system_designer/tests/e2e/commerce.spec.ts` (Playwright, committed bundle, in-memory fake of
  the H6 endpoints): a dealer assigns a run, saves, keeps the riser and requests review; an
  Applications Engineer opens the design, keeps the riser and approves; the dealer sees ordering
  allowed and writes the design's supply back to the schedule.
- Installed `test_designs.test_reviewed_design_lets_the_schedule_be_ordered` runs the same loop on
  Frappe: with the gate on the schedule cannot be ordered, review is requested and approved, and
  `can_request_schedule_order` then allows it.
- Found and fixed: the review card lost the reviewer's confirmation when the panel closed after a
  decision; the outcome now shows on the card.
- The designer's Playwright suite is run locally (`npm run test:e2e` with
  `SYSTEM_DESIGNER_CHROMIUM` set); CI runs the unit, type and bundle checks.

## Client diagram and single-line low-voltage wire

- Low-voltage wire on both styles: parallel runs from one output to one load (a double-end feed) are
  drawn as one line. Its callout lists every cable tag and the total conductors, for example
  `W-01, W-02 / OUT1 · 2 × 18/2 CL3R · 4 COND`. The schedules still list each cable
  (`packages/drawing/src/wires.ts`).
- Views step: a Style choice, "Riser diagram (installer)" or "Client diagram (homeowner)". The client
  diagram uses the riser's layout, colour-codes product families and wire families, and replaces the
  engineering schedules with a "FIXTURE SCHEDULE & ORDERING" page. That page has a colour key, the
  dealer's schedule lines (type, product, part number, quantity, location), power supplies and
  controls, wire to order (gauge, conductors, estimated length) and notes. It has no prices.
- Client cards keep the voltages in and out (a supply fed off the drawing shows its datasheet input
  range, e.g. `100-277 V AC IN`), the port names (AC IN, OUT1, DC IN, DMX IN) and a `CONTROL:` line
  naming the protocols on the card's control wiring. Watts, loading and DMX addresses stay on the riser.
- Wire callouts on the client diagram are "LV Wire · 18 AWG · 2 conductors", with the gauge taken from
  the wire the engine chose. Line voltage is marked "by electrician".
- A configured fixture shows its own part number, not its tape's. `open_design` builds now carry
  `partNumber`, taken from `display_part_number`, then `part_number`, then `configured_item`.
- Client exports are PDF and SVG only (no DXF). They are kept as "Presentation PDF" and "Presentation
  SVG", with `_Client` in the file name. Pins and comments on the client diagram use the Presentation
  view.
- The serializers paint fills first on every sheet. Colour is written only on colour-coded sheets, so
  the riser PDF and SVG stay monochrome.
- Tests: `packages/drawing/src/client.test.ts`, `app/src/shell/ViewsStep.test.tsx`, and
  `tests/portal_unit/test_system_design_expansion.py` and `test_system_design_deliverables.py`.
