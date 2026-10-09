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
