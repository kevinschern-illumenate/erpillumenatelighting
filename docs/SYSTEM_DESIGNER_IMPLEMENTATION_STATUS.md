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
  - A required review always reports `satisfied: false`; approval and overrides land in WP-4.4.
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
