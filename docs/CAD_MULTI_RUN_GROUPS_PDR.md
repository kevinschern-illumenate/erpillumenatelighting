# Multi-Run Groups in the AutoCAD Draw-to-Quote Tool: PDR and Implementation Plan

2026-11-25 · branch `claude/autocad-multi-run-groups-for8vj` · status: **implemented** (see "Drawn
multi-run groups" in `docs/CAD_TOOLKIT_IMPLEMENTATION.md`; staging acceptance still to run)

Deviations from this plan, decided while building it:

- Style keys a group does not share (such as a tape style's `feed_type`) are reported on the row as
  "Not used by a group" instead of being an error (5.3.3). The portal group editor drops them silently;
  making them errors would refuse most existing presets.
- Group checks are run by the import itself and left out of its catalog-based server checks, so a
  group's problems show once whether or not the catalog builds.
- No new layer: the group tag is on `E-ANNO-TAGS` with the other tags.
- `ILCONNECT` and `ILPSU` were not changed to accept a group tag (5.1); select the runs as before.

Audience: the engineer (or chat bot) who implements this. Every claim about current behaviour below was read
from the code at HEAD `5e146b1`; file paths are repo-relative. Nothing was run: the unit suites, the AutoLISP
interpreter tests and the portal were not executed for this investigation, so treat "tested" statements as
"has tests", not "passes today".

---

## 1. Summary

A plan-view line sometimes stands for several physical fixtures. Example: one drawn line is four shelves
stacked on top of each other, all fed by one power supply. Today the AutoCAD toolkit can only say "one drawn
run = one fixture line", so the shelves are either under-quoted (one run) or drawn four times on top of each
other and quoted as four unrelated lines with four separately planned supplies.

The portal already has the right product object: a **multi-run group** (`ilL-Configured-Group`), several
independently built runs sharing one family, template and power plan, saved as one schedule line. The System
Designer already reads that object. **The gap is only in the draw-to-quote path**: the `ilq/2` package, the
toolkit and the drawing import have no way to express or build a group.

**Proposal:** let the drawing carry groups, and make the drawing import build them through the same
`group_request` path the dealer portal's group editor uses. No new DocType, no new configurator engine, no
change to the System Designer's data model. Two ways to draw a group:

- **Stack**: pick one drawn run and say it is N stacked runs (`ILSTACK`). The plan still shows one line.
- **Gather**: pick several drawn runs and group them (`ILGROUP`), for runs that differ in length or sit apart.

Both end as one schedule line, one group part number, N members, one power plan whose supplies sit on their own
lines under it, and N runs in the System Designer.

## 2. Goals and non-goals

Goals

1. Call out a group in AutoCAD (draw it, tag it, list it in the drawing's schedule).
2. Import it through the dealer portal as a multi-run group, editable and re-importable in place.
3. The group's runs and supplies work in the System Designer exactly as a hand-built portal group does.
4. Existing drawings and toolkit versions are unaffected.

Non-goals (v1)

- Pinning a drawn PSU model onto the group (the group's power plan stays the planner's choice; see 5.6).
- Groups that span rooms, or mix products, families or electrical specs. The portal forbids mixing; so does this.
- Extrusion Kit and LED Sheet groups (a kit is a kit line plus a tape build; a Sheet group is made of coverage
  areas, not drawn runs).
- Merging identical drawn groups into one line with quantity N (each drawn group stays its own line, as runs do).
- Bluebeam/PDF and DXF front ends (DXF is a later phase, 9.3).
- Any price in the package or the import responses (design rule D6 stays).

## 3. What exists today (investigation findings)

### 3.1 The portal group is a finished product

| Fact | Where |
| --- | --- |
| A group is a normalized `group_request` (`schema_version` 3): `family`, `template`, `shared`, `power`, `members[{input:{segments}}]`. Members, labels, order and quantity are not part of identity; geometry, template, power inclusion and policy are. | `api/group_contract.py::normalize` |
| Limits: 1 to 12 members, 1 to 24 segments per member, one family and template, shared specs chosen once, a member's last segment must be an Endcap, sheets take areas only, no max-run override for sheets. | `group_contract.py` |
| Included supplies are planned across all members' real circuit loads (exact search, at most 12 circuits). `power_allocation` `per_run` (default) or `grouped` (circuits may share an output). | `api/power_planner.py` (`MAX_CIRCUITS = 12`) |
| Preview and save already accept `selections.group_request`: `portal.configuration.calculate` returns `fixture_group_configurator.preview`, `persist_artifact` calls `fixture_group_bom.persist`, `save` attaches it to a line (`configured_group`). | `portal/configuration.py` lines 89-139, 181 |
| The portal editor saves with `power.separate_supply_line = true`: supplies stay out of the group's BOM and price and become `ACCESSORY` lines with `power_supply_for_line` set to the group's line key; `reconcile` keeps their quantity, type and location in step. | `api/power_supply_lines.py::split_power`, `set_power_lines`; `public/js/configurator/fixture_group_editor.js::request` |
| Group part number `TEMPLATE-PROJECT-TYPE-LOCATION-XXXX` is assigned on the line; ordering builds each run plus a Product Bundle; the pinned `ilL-Configured-Group` is the engineering source. | `api/group_part_number.py`, `api/fixture_group_order.py`, `api/fixture_group_bom.py` |
| Flag `ill_portal_fixture_groups` (code default **on**). The acceptance doc says to enable it only on test sites first; production state was not checked. | `portal/site_flags.py::fixture_groups_enabled`; `docs/B2B_CLOUD_ACCEPTANCE.md` row "Independent groups" |

### 3.2 The System Designer already reads groups

- `system_design/expansion.py::group_build` flattens every member's circuits into the build's runs (in member
  order, each run carrying its member's own part number), keeps the pinned power plan's allocations keyed by
  that run order, and picks one catalog id when all members share a tape.
- `packages/engine/src/expand.ts` turns each line copy times each build run into a design run
  (`{line}:{copy}:{run}`); `labels.ts` labels them `<member part number>.1, .2, ...`.
- `packages/engine/src/power.ts::placeConfiguratorSupplies` places the configurator's own supply allocation
  (supply number, output) on the supply lines that belong to the fixture line, so a group's supplies arrive as
  "from the configurator".
- Test cover exists for groups in expansion (`tests/portal_unit/test_system_design_expansion.py`,
  `tools/system_designer/packages/engine/src/labels.test.ts`).

So **if the import produces a normal group line, the designer needs no new model**. The risks are in how the
drawing's *site* data (rooms, cabinets, measured home runs) is applied to a group line; see 3.4.

### 3.3 The draw-to-quote path has no group concept

- `portal/drawing_import.py::requests_for` returns one build request per run; `Planner.plan_run` and
  `commit_drawing_import` save one schedule line per run (`cad_run_id` = the run id, plus `.K` for a kit's
  second line). Every drawn run is quantity 1.
- The `ilq/2` package (`tools/system_designer/packages/core-schemas/src/ilq.ts`, mirrored by
  `system_design/ilq_schema.py` and the JSON Schema in `public/system_designer/schema/ilq.schema.json`) is
  `.strict()`: runs, rooms, cabinets, `psus`, `wire_paths`, `controls`, `zones`, `counts`, `other_lines`.
  There is no `groups` and no per-run count.
- `psus[].runs` ("this PSU feeds these runs", drawn with `ILPSU` / `ILCONNECT`) is **not used to build
  anything**. It only feeds the `PSU_OVERLOAD` check (`drawing_checks.py::_psu_issues`, `il-check`), and the
  check's message says "the System Designer will reassign outputs". The designer sizes and assigns supplies
  itself.
- `site_seed` writes one `lines[line_key]` entry per run (room, cabinet, feed method, longest measured wire
  into the run).

### 3.4 Constraints the group design must respect

1. **One site entry per line, applied to every run of the line.** `tools/system_designer/packages/engine/src/cadSite.ts::applyCadSite`
   looks up `site.lines[run.lineKey]` and sets room, environment, measured home run and `feedMethod` on *every*
   design run of that line (all members and all copies). A group therefore has one room, one home-run length and
   one feed method. This also matches the schedule: a line has one `location`.
2. **Identity and member order.** `normalize` sorts members canonically, so `member_key` (`M1`, `M2`, ...) is by
   sorted geometry, not drawing order. `group_contract.member_presentation` maps the dealer's labels back and
   consumes duplicate geometries once each. The import must use it to know which drawn run became which member
   (identical shelves are interchangeable, but the receipt must still give each a stable pairing).
3. **Preview returns prices.** `fixture_group_configurator.preview` is `@price_scoped` and adds tier pricing.
   The import must strip it (D6).
4. **Style to shared-spec mapping.** `group_contract.SHARED_FIELDS` is a fixed key list per family and
   `normalize` rejects anything else (`Unsupported shared specifications`). A CAD style's `selections` come from
   a configuration preset or the catalog's template options and are in the configurator's engine shape. The
   mapping from one to the other must be confirmed by the first work package (7.1) rather than assumed.
5. **Locked/quoted schedules, idempotency, re-import by `cad_run_id` / `erp.line_key`, price-free receipts**
   all exist and must keep working for group lines.

## 4. Product requirements

| # | Requirement |
| --- | --- |
| R1 | In AutoCAD I can mark one drawn run as N stacked runs, and mark a set of drawn runs as one group. Both appear on the plan (a tag with the group id, type and count) and in the drawing's run schedule (`ILOUT`). |
| R2 | A group has one fixture Type (`line_id`), one room/location, one style (family, template, selections), and one power policy (include supplies yes/no, allocation, optional max-run override). |
| R3 | The import shows a group as one row with its members (drawn length, built length, splits, watts each), its supplies, and any errors or open choices. Prices never appear. |
| R4 | Committing creates or updates **one** schedule line per group: `configured_group` set, group part number assigned, supplies on their own lines under it (when power is included), `cad_run_id` = the group id. |
| R5 | Re-import is in place: same line key, unchanged groups are skipped, a changed count or length updates the line and its supplies, a group removed from the drawing is removed only on confirmation (with its supply lines). |
| R6 | The receipt tells AutoCAD, per group and per member run, the line key, part number, built lengths and watts, so the drawing can be stamped and `ILOUT` can draw the schedule. |
| R7 | A new design in the System Designer starts from the drawing with the group's runs in the drawn room, cabinet and measured home run, and the group's supplies placed as configurator supplies. |
| R8 | ILCHECK and the server catch group mistakes before import: mixed styles, mixed types or rooms, more than 12 members, a run in two groups, an unsupported family. |
| R9 | The group line behaves downstream exactly like a portal group: quote request, Quotation/Sales Order conversion (Product Bundle of member builds), manufacturing, stock. No change expected there. |
| R10 | Drawings without groups, older toolkit versions and older packages behave exactly as before (same content hash, same import result). |

## 5. Design

### 5.1 Drawing model (AutoCAD)

New entity kind **GROUP** (a tag block with XData, like PSUs): no geometry of its own, it lists member run ids.
New run properties **`copies`** (1 to 12, default 1) and optional **`label`**.

Commands (all AutoLISP, no ActiveX/reactors/DCL, LT and Mac safe, per the toolkit rules):

| Command | Does |
| --- | --- |
| `ILSTACK` | Pick a run. Ask "How many stacked runs?" (2 to 12; 1 removes the stack) and an optional label stem ("Shelf" gives "Shelf 1".."Shelf N"). Sets `copies`/`label` on the run. If the run is in no group, creates a one-run group (next free `G-nn`) and places its tag next to the run tag. The run tag reads `L1-01 x4`. |
| `ILGROUP` | Select runs. Ask group id (default next `G-nn`), Type (default the first run's), power policy (include supplies Y/n, allocation Per-run/Grouped, default **Grouped**). Refuses runs whose style, Type or room differ (offers to copy the first run's style). Options Add/Remove/Delete like `ILCONNECT`. Places the tag at a picked point. |
| `ILCONNECT` / `ILPSU` | Unchanged, but also accept a group tag: connecting a PSU to a group connects it to every member run (sets `psus[].runs` to the member ids). |
| `ILOUT` | The run schedule gains group rows with indented member rows (server built length, watts) and the supply list from the receipt. |
| `ILUPDATE` / `ILCHECK` / `ILQUOTE` / `ILRECEIPT` | Read, check, write and stamp groups (5.4, 5.5). |

Copy rules (`il-fix-copies`): a copied group tag gets a new id and loses its run list; a copied member run
leaves its group; a copied run keeps `copies` and `label`. This matches how PSU tags already behave.

Plan appearance: a new `IL-GROUPTAG` block and layer (for example `E-ANNO-GRUP`) added through the generated
asset pipeline (`packages/drawing/src/cadAssets.ts`, `packages/data/src/layers.json` `planLayers`,
`npm run cad:export`), not hand-edited in `il-assets.lsp`. Tag text: `G-01  L1  x4  (8 ft)`.

### 5.2 Package contract (`ilq/2`, additive)

Keep `schema: "ilq/2"`. Add optional keys; strictness stays, so old servers refuse packages that use them
(that is the signal to deploy the server first, 8).

```jsonc
// runs[] gains:
"copies": 4,                 // int 1..12, default 1
"label":  "Shelf",           // optional member label stem

// new top-level, default []
"groups": [{
  "id": "G-01",              // CadId; unique across runs, psus, cabinets, controls, zones, groups
  "handle": "2A3F",          // hex handle of the tag entity (duplicate-handle rule shared with runs/controls)
  "fixture_type": "L1",
  "room": "R-01",            // optional, must exist
  "sheet": "Model",          // optional, must exist
  "location": "Kitchen shelves",   // optional
  "runs": ["L1-01"],         // member run ids, drawing order, at least one
  "power": {
    "include_supplies": true,      // default true
    "allocation": "grouped",       // "per_run" | "grouped", default "grouped"
    "override_max_run_ft": null    // optional, > 0
  },
  "notes": "",
  "erp": { "line_key": "", "configured_name": "", "config_hash": "" }   // written back by the receipt
}]
```

Validation rules (Zod `superRefine` and Python `reference_problems` must match, as they do today):

- `groups[].runs` each exist; a run is in at most one group; each group has at least one run.
- Total members per group, counting `copies`, is at most 12.
- `copies > 1` is allowed only for a run that is in a group (the toolkit always creates one).
- Group ids are unique and do not collide with other ids; group handles join the duplicate-handle set.
- `room`/`sheet` exist when given.

The content hash (`il-package-content`) must not change for a drawing with no groups (R10): emit `groups` only
when non-empty and omit `copies` when it is 1.

### 5.3 Import: planning a group

In `portal/drawing_import.py`:

1. `Planner.plan()` splits runs into grouped and ungrouped. Ungrouped runs go through the existing path
   unchanged. Each group becomes one row from a new `Planner.plan_group(group, runs)`.
2. **Group checks first** (model-level, no catalog): all member runs have identical `style` (family, template,
   selections, preset); same `fixture_type`; same `room`; same `feed.method`; family is Linear Fixture, LED Tape,
   COB Tape or LED Neon; members including copies at most 12; `fixture_groups_enabled()` is true. Failures make
   the row `error` with the GROUP_* text (5.5).
3. **Build the request**: `group_request_for(group, runs, style)` returns
   `{"schema_version": 3, "family", "template", "shared", "power", "members"}`.
   - `shared` = the style's selections restricted to `group_contract.SHARED_FIELDS[family]`. Power-related keys
     (`include_power_supply`, `dimming_protocol_code`, `override_max_run_ft`, `equal_length_runs`,
     `power_allocation`) are moved into `power`. Any other key is an `error` naming the key (not silently
     dropped); the mapping is confirmed in WP 7.1.
   - `power` = `{include_power_supply: group.power.include_supplies, power_allocation, override_max_run_ft,
     dimming_protocol_code, separate_supply_line: true}`. `separate_supply_line` is true so the line behaves like a
     portal-saved group.
   - `members` = each member run's segments through the existing `tape_segments(run, style)` /
     `linear_segments(run, style)`, repeated `copies` times, each with a `label` (`label or run id`, plus the
     copy number). Segment keys are already what `group_contract._segment` expects.
4. **Preview** with `portal.configuration.calculate(family, {"group_request": req}, template=...)`
   (`preview` underneath), then **strip the `pricing` block** before it enters the row. Row fields: group id,
   family, template, status (`ok` / `needs_choice` / `error`), per-member rows from the result's `runs`
   (`member_key`, label, circuits, watts, requested/manufactured length, leader, jumpers), the power plan's
   supplies and allocations, messages. `needs_choice`: a group has one style, so `choice_groups` and
   `previous_choices` key choices by **group id** and one answer fills every member.
5. **Matching and change detection**: `cad_run_id` = group id; fall back to `erp.line_key` like runs.
   `_same_request` compares the stored `ill_configurator_request` with
   `{family, template, selections: {group_request}, segments: null}` as `configuration.save` stores it, so an
   unchanged group is `unchanged` and skipped. Labels are presentation only and must not trigger an update.
6. **Removals**: add group ids to the `kept` set. A run that was a standalone line in an earlier import and is
   now a group member appears in `removals` ("now part of group G-01"), confirmed like any removal. Removing a
   line already removes its supply lines (`_remove_lines`).

### 5.4 Import: commit, receipt, site seed

- **Commit** reuses `_save_build`: `configuration.save(schedule, family, {"group_request": req}, key,
  expected_modified, line_key=..., metadata={line_id, location, qty: 1, notes}, template=...)`. `save` already
  runs `split_power`, `persist_artifact`, `apply_artifact`, `set_power_lines` and stores
  `ill_configurator_request`. Idempotency key uses the group id. The whole commit stays inside `atomic_build`.
- **Receipt** (`ilq-receipt/1`, additive): keep `runs[]` (each member run gets a part pointing at the group's
  line) and add `groups[]`:
  `{id, line_key, configured_name, part_number, members: [{run, member_key, label, built_length_in, watts}],
  supplies: [{item_code, qty}]}`. Pair drawn runs to `member_key` with `member_presentation` (it consumes
  duplicate geometry once each). `receipt_for` currently loops `package["runs"]` against per-run plan rows; it
  needs a group-aware branch. `config_hash` for a group line is currently skipped (`!= "ilL-Configured-Group"`);
  read it from the group doc.
- **Site seed** (`site_seed`): one `lines[group line key]` entry per group (room, cabinet, feed method; home run
  = the longest low-voltage wire into **any** member run or into the group tag). Use a separate
  member-run-to-line-key map; do not add member ids to the cad-id to line-key map that `_store` and the
  receipt use. Zones list run ids: map each member to the group's line key and de-duplicate
  (`site_seed` zones and `applyZones`).
- `ilL-CAD-Import` counters: count one group as one add/update. No schema change is needed; put member counts in
  the receipt and in telemetry `details` (`groups`, `group_members`).

### 5.5 Checks (toolkit and server, with parity)

New codes, all model-level (no catalog needed), implemented in both `il-model.lsp::il-check` and
`system_design/drawing_checks.py`, with golden cases added to
`tools/system_designer/fixtures/cad/check-cases.json` (the repo already tests LISP/Python parity through
`mini_lisp`):

| Code | Severity | When |
| --- | --- | --- |
| `GROUP_EMPTY` | error | A group lists no run, or a listed run is gone |
| `GROUP_UNKNOWN_RUN` | error | A listed run id is not in the drawing |
| `GROUP_RUN_IN_TWO_GROUPS` | error | A run is listed by two groups |
| `GROUP_MIXED_STYLE` | error | Members differ in family, template, selections or preset |
| `GROUP_MIXED_TYPE` | error | Members' schedule Types differ from the group's |
| `GROUP_MIXED_ROOM` | error | Members are in different rooms (the line has one location) |
| `GROUP_MIXED_FEED` | warning | Members' feed methods differ (the design applies one per line) |
| `GROUP_TOO_MANY` | error | Members including copies exceed 12 |
| `GROUP_FAMILY` | error | Style family is Extrusion Kit |
| `COPIES_NOT_IN_GROUP` | error | `copies > 1` on a run in no group (repair: run `ILUPDATE`) |

Changes to existing checks: `RUN_UNCONNECTED` treats a group member as fed when any PSU, wire or cabinet touches
the group or any member. `PSU_OVERLOAD` multiplies each member's load by `copies`. Server-only: the group row's
configurator errors (no compatible supply, more than 12 circuits when supplies are included, incompatible
electrical specs between members) surface as row `error` text; the existing "`ILCHECK` errors block import"
rule applies unchanged.

### 5.6 Power, PSUs and the System Designer

- **The group's power plan is authoritative.** Supplies come from `power_planner.plan_power` over every member
  circuit and land on supply lines. The designer then places them as configurator supplies
  (`placeConfiguratorSupplies`). A PSU drawn with `ILPSU` and connected with `ILCONNECT` is a **location and
  load hint** in v1: it gives the cabinet and measured home run through the site seed, and drives
  `PSU_OVERLOAD`. Pinning the drawn PSU's model onto the plan would need `power_planner` to accept a forced
  driver; it is listed as a later phase (9.3), not v1.
- **Default allocation `grouped`.** The stated intent is that the runs "share a power supply". Under `per_run`
  each circuit needs its own output, so four shelves need a supply with four outputs or four supplies. Under
  `grouped` circuits may share an output when the load fits, which ranks fewer, larger supplies first. It is a
  per-group choice in `ILGROUP`; it joins the group identity only when `grouped` (existing behaviour).
- **Designer behaviour to verify, not rebuild:** the cad-site entry for the group line applies room, measured
  home run and feed method to all of the line's design runs (3.4). Add a TypeScript test with a group line of
  several runs and a site entry, and an `open_design` test with a drawing import whose line is a group
  (`tests/portal_unit/test_system_design_expansion.py`, `tools/system_designer/packages/engine/src/cadSite.test.ts`).
  If a group's members need different home runs later, `cad-site/1` needs per-run entries; not needed for v1
  because a group is one room and one cabinet.

### 5.7 UI

- Portal import dialog (`public/js/portal/schedule/drawing_import.js`) and Desk dialog
  (`public/js/desk_drawing_import.js`): a group row is expandable, showing member rows (label, drawn vs built
  length, watts, splits) and a supplies line ("2 x XYZ-60W, 4 runs on 3 outputs"). A group with open choices
  uses the existing choice picker keyed by group id. Counts say "N groups" next to "N runs".
- Schedule page: nothing new. A group line already shows its members (`portal/group_display.py`, schedule
  templates), and an import-made group is indistinguishable from a portal-made one except `cad_run_id`.
- Resources page: add the group commands to the toolkit notes (`templates/pages/resources.html`) and the dealer
  tutorial.

## 6. Acceptance criteria (the scenario that defines "done")

A dealer draws one 8 ft Linear Fixture run `L1-01`, runs `ILSTACK` and enters 4 (label "Shelf"), places a PSU
tag and connects it to the group, then `ILCHECK`, `ILQUOTE` and imports into a schedule.

1. Preview: one group row `G-01` with four member rows (`Shelf 1`..`Shelf 4`), each with built length and watts,
   a supply summary, no prices.
2. Commit: exactly one new schedule line with `configured_group` set, `cad_run_id = G-01`, `line_id = L1`,
   `qty = 1`, a group part number, and one supply line per planned supply under it
   (`power_supply_for_line` = the group's line key, `qty` follows the line).
3. The group's pinned build has four members, and `ilL-Configured-Group` is the same record the portal group
   editor would have made for the same request (same `config_hash`).
4. Re-importing the unchanged drawing: row action `unchanged`, no write.
5. Changing the stack to 5, or one length: the same line key is updated in place; supply lines follow; a
   standalone run turned into a stack member shows as a removal that needs confirmation.
6. The receipt lists the group and four members; `ILRECEIPT` stamps them; `ILOUT` draws the group with its
   members.
7. Opening a new System Designer design from the import: four runs labelled from the group's part number, in the
   drawn room, with the measured home run, and the group's supplies placed "from the configurator" with
   outputs matching the plan.
8. Portal editor: opening the line's configuration shows the four runs as a normal group (labels from the
   request), and saving it unchanged does not create a different build.
9. Quote request, Quotation and Sales Order conversion and Work Order behave as for a portal group (one
   commercial line, a Product Bundle of member builds).
10. Error cases give a named, row-level message: mixed style, mixed room, 13 members, Extrusion Kit style, flag
    off, no compatible supply, a run in two groups.
11. A drawing with no groups produces a byte-identical package hash and the same import result as before.

## 7. Implementation plan

Sequence: contract, then server, then designer verification, then toolkit, then release. The server work can be
proven end to end with hand-written package fixtures before any LISP exists.

### WP 7.1 Spike (small; do first, report findings)

- Confirm, with a real preset and a catalog template of each of Linear Fixture and LED Tape/Neon, that a CAD
  style's `selections` map into `group_contract.SHARED_FIELDS` plus power keys with nothing left over. Record
  the exact key mapping (the engine-shaped linear keys vs the legacy portal keys in
  `configured_product_builder._fixture_payload_from_portal_selections`).
- Run `configuration.calculate` and `save` with a `group_request` built from a CAD-shaped run on a test site and
  confirm the stored `ill_configurator_request` round-trips through `portal/group_display.run_labels` and the
  portal editor.
- Check the production/staging value of `ill_portal_fixture_groups` and `ill_cad_import`.
- Outcome decides whether `group_request_for` needs a mapping table or a small adapter module.

### WP 7.2 Contract (TypeScript, JSON Schema, Python, fixtures)

Files: `tools/system_designer/packages/core-schemas/src/ilq.ts`, `public/system_designer/schema/ilq.schema.json`
(regenerate with `npm run schema:export`), `system_design/ilq_schema.py` (`reference_problems`, `with_defaults`:
`groups` default `[]`, `copies` default 1), fixtures under `tools/system_designer/fixtures/cad/packages/valid|invalid`
(add valid stack, valid gather, and invalid: unknown run, run in two groups, copies outside a group, over 12,
duplicate id, id collision). Tests: `tests/portal_unit/test_cad_ilq_schema.py` and the Zod tests.

### WP 7.3 Server import

Files: `portal/drawing_import.py` (`plan`, `plan_group`, `group_request_for`, `_save_build`, `receipt_for`,
`site_seed`, `choice_groups`, `previous_choices`, `kept`, counts, telemetry),
`system_design/drawing_checks.py` (group checks, `PSU_OVERLOAD` copies, `RUN_UNCONNECTED`), `check-cases.json`,
`portal/site_flags.py` (use `fixture_groups_enabled`), `portal/drawing_review.py`/`drawing_list.py`/`diff_receipts`
if they read receipt runs. Tests: extend `tests/portal_unit/test_drawing_import.py` (stack, gather, mixed style,
unchanged, count change, removal, flag off, price stripped from the row), `test_drawing_checks.py`.

### WP 7.4 UI

Files: `public/js/portal/schedule/drawing_import.js`, `public/js/desk_drawing_import.js`, CSS if needed;
tests `tests/portal_ui/drawing_import.test.cjs` (group row render, expand, choices keyed by group id).

### WP 7.5 System Designer verification

Files: `tools/system_designer/packages/engine/src/cadSite.ts` (+ test), `system_design/designs.py` /
`open_design` tests. Add group cases; change `cadSite` only if the verification shows a defect.

### WP 7.6 AutoCAD toolkit 0.6.0

Files under `tools/cad_toolkit/lisp/`: `il-model.lsp` (model, checks, `il-package`, `il-package-run`, new
`il-package-groups`, content hash), `il-commands.lsp` (`ILSTACK`, `ILGROUP`, `ILCONNECT`/`ILPSU` group support,
`ILUPDATE`, `ILOUT`, `ILRECEIPT`, `il-model` reading GROUP entities, `il-fix-copies`), `il-core.lsp` (XData
kind), assets via the generator (`IL-GROUPTAG`, layer), bump `*il-version*` in `il-util.lsp` to 0.6.0, README
and `ILHELP` text. Tests: `tools/cad_toolkit/test/mini_lisp.py` runs the pure files in CI
(`tests/portal_unit/test_cad_lisp.py`), so keep all new logic in the pure files and AutoCAD-only code thin. Add
LISP golden cases for the new checks and for the package writer (compare with the Python-validated fixtures).
Rebuild the reproducible bundle (`python -m tools.cad_toolkit.package_bundle --out dist --publish`) and commit
`public/cad_toolkit/ilLumenate-cad-toolkit-0.6.0.zip`.
Manual: the `accoreconsole` runner (`test/run_tests.bat`) and a drawing session on full AutoCAD and LT, which
only a person with those installs can do.

### WP 7.7 Docs and release

`docs/CAD_TOOLKIT_IMPLEMENTATION.md` (status section), `tools/cad_toolkit/README.md`, the resources page,
`docs/B2B_CLOUD_ACCEPTANCE.md` (new "CAD groups" row), release notes. See 8 for rollout.

## 8. Rollout and compatibility

1. Deploy the server first (it accepts packages with and without groups). Old toolkit packages keep working.
2. Publish toolkit 0.6.0; set `settings.min_toolkit_version` only after pilots have it, as before
   (`ill_cad_min_versions`).
3. An old server receiving a 0.6.0 package that uses groups refuses it at schema validation with a clear
   message; keep "deploy server first" in the release checklist.
4. Flags: groups need both `ill_cad_import` (and the pilot/all-dealers gate) and `ill_portal_fixture_groups`.
   With groups off the row errors with "Multi-run groups are not enabled for this site".
5. Run the staging acceptance in section 6 before pilot dealers get 0.6.0.

## 9. Risks, open questions, later phases

### 9.1 Risks

| Risk | Mitigation |
| --- | --- |
| Style selections do not map cleanly to `SHARED_FIELDS` | WP 7.1 spike; unknown keys are named errors, never dropped |
| Groups over 12 circuits cannot get included supplies | The configurator error is shown on the row; dealer can exclude power or split the group; checks warn earlier at 12 members |
| One site entry per line hides per-member home runs | Documented v1 limit (one room, one cabinet); `cad-site/1` per-run entries are a later change |
| `receipt_for`/`site_seed`/`diff_receipts` assume one part per run | Group branches plus tests that the old paths are untouched |
| LISP/Python check parity drift | Add every new code to `check-cases.json` first |
| Two stacks of identical geometry produce identical `member_key`s | `member_presentation` consumes duplicates once each; test with four identical shelves |

### 9.2 Open questions (defaults used if unanswered)

1. Are stacked shelves usually the same length? **Default:** `ILSTACK` makes identical copies; different lengths
   use `ILGROUP` on separate runs.
2. Should a drawn PSU's model be forced onto the group? **Default:** no, planner chooses (v1).
3. Many identical bays (10 bays of 4 shelves): 10 lines or one line with qty 10? **Default:** 10 lines; a later
   "merge identical lines" step could set qty.
4. Groups across rooms? **Default:** not allowed (one location per line).
5. Default power allocation `grouped`? **Default:** yes for CAD groups (intent is a shared supply); changeable per group.
6. Should power be excluded by default for dealers who supply their own supplies? **Default:** include, same as the portal.
7. Label wording ("Shelf", "Run")? **Default:** the dealer's stem, else the run id.

### 9.3 Later phases

DXF ingest of groups (an `ILM-GROUP-<id>` layer or callout text; `dxf_ingest.py` and the dealer checklist);
pinning a drawn PSU model onto the plan; merging identical groups into quantity; per-member sites; Bluebeam and
PDF front ends from the Bluebeam spike; a group editor in the Desk import dialog that lets staff change copies
without redrawing.

### 9.4 Things not verified here

Whether `ill_portal_fixture_groups` or `ill_cad_import` are on in production; the real preset key shapes
(WP 7.1); AutoCAD behaviour on LT/Mac for the new commands; any test result.
