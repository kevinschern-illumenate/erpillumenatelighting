# Multi-run group part numbers: PDR and implementation plan

Status: implemented 2026-11-25. The business confirmed D1 (`-GRP(A1B2)`) and D3 (total square feet, written `48SF`). Sections 3-8 are the original plan; section 9 records what shipped.

## 1. Problem

1. A multi-run group added through the desk **Configure & Add Fixture** dialog shows
   `ILL-GRP-<64 hex characters>` as the Item on the Quotation and Sales Order.
   The same group converted from a fixture schedule shows a short readable part number.
2. The readable number is itself unlike a standard configured part number. It is built from
   dealer-entered words: `TEMPLATE-PROJECT-FIXTURETYPE-LOCATION-XXXX`.

## 2. Goals

- G1. Every surface (desk dialog, schedule, Quotation, Sales Order, portal, exports) shows one short readable group part number.
- G2. The number follows the standard configured-fixture format. The run's feed segments are replaced by `GRP` plus a four-character code.
- G3. No change to what is built or priced (per-run builds, Product Bundle, BOMs, work orders).

Non-goals: renaming existing Items or already-issued documents; changing group pricing, power planning or the group engineering identity (`config_hash`).

## 3. Investigation findings

### 3.1 Two code paths create a group "Item", and only one is readable

| Path | Entry point | Item created | Item code |
|---|---|---|---|
| A. Desk dialog | `api/desk_configurator.py` ~L706-755 -> `portal/configuration.persist_artifact` -> `api/fixture_group_bom.persist` -> `ensure_artifacts` (`fixture_group_bom.py:145`) | Stock Item + one BOM | `"ILL-GRP-" + config_hash` (the ugly code) |
| B. Schedule -> Quote/SO | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py:669-686` -> `api/fixture_group_order.ensure_order_bundle` | Non-stock Item + Product Bundle of the per-run builds | `line.group_part_number` (readable) |

- Path A's row takes `artifact["item_code"]` in `quote_order_configurator._apply_artifact_to_row` (`:476`). So the quote row is the hash code even when the dialog is linked to a schedule. The schedule line gets a readable `group_part_number` from `group_part_number.assign()`, but the document row ignores it.
- The screenshot is path A. It also shows "Not linked to a fixture schedule", where no schedule line exists at all.
- Path B cannot be used from the dialog today because `ensure_order_bundle(schedule, line, target_doc)` and `_part_number` need a schedule line (project, fixture type, location) to name the Item.
- The hash Item cannot simply be deleted. `ilL-Configured-Group.configured_item` / `.bom` must be set (schedule `validate`, `ill_project_fixture_schedule.py:160`), and `ensure_artifacts` raises if `configured_item != "ILL-GRP-"+hash`. Keep it as the internal engineering Item; it just must not be the Item on documents.
- Manufacturing already supports both shapes. `manufacturing_order.create_for_line` uses `bundle_members()` for bundles (one Work Order per run) and falls back to `pinned_build` for the legacy single-BOM group Item. Switching the dialog to bundles is therefore safe for production.
- The dialog UI already handles bundles: `_built_summary` returns `product_bundle`, and `public/js/desk/dialog/save.js:171-173` renders Item / BOM / Product Bundle rows, with BOM omitted when null.

### 3.2 Current readable number (path B)

`api/group_part_number.py`: `prefix(template, project, fixture_type, location)` + `-` + 4 random uppercase letters.
Notable properties:
- It embeds dealer project name, fixture type and location in a **global** Item code, visible across dealers.
- `assign()` keeps a number only while `current.rpartition("-")[0] == base`. **If the format changes, every existing line fails that test and is re-numbered on its next schedule save.** This must be neutralized (see 5.4).
- `is_taken()` checks Items and schedule lines.

### 3.3 The standard configured part number to mimic

Linear (`doctype/ill_configured_fixture/ill_configured_fixture.py:310 _generate_part_number`):

```
ILL-{Series}-{LEDpkg}-{Env}-{CCT}-{Output}-{Lens}-{Mount}-{Finish}-{LengthIn}-{FeedType}{LeaderFt}-{C | EndFeed+Ft}     single segment
ILL-{Series}-{LEDpkg}-{Env}-{CCT}-{Output}-{Lens}-{Mount}-{Finish}-{LengthIn}-J({4-hex segment hash})                   jumpered
```
`LengthIn` is `requested_overall_length_mm/25.4` with one decimal (e.g. `120.0`).

Tape/neon (`tape_neon_configurator.py:3752, 3900`): `{spec item}[-{cct}-{output}]-{total length in, int or 1 dp}-{feed}{ft}-C` or `...-J({hash})`.
LED Sheet (`ill_configured_led_sheet.py:96`): `{series}-{env}-{cct}-{output}-{mount}-{finish}`, no length and no feed tail.

All runs in a group share family, template and every spec field (`group_contract.SHARED_FIELDS`). So the part-number prefix before the length is identical for every run. Only the length differs.

## 4. Requirements

R1. Group part number = standard prefix for the group's family, then the **total length of all runs in inches**, then `GRP`, then a four-character code. The run-level feed segments (feed type, leader length, end feed or `C`, and `J(hash)`) are replaced by `GRP(XXXX)`.

Example (linear, two runs of 96" and 48"):
`ILL-ABC-XX-DR-27-HO-FR-SM-WH-144.0-GRP(A1B2)`

LED Sheet (two 4 x 6 ft areas): `LS01-DR-30-HO-AD-WH-48SF-GRP(A1B2)`

R2. Length format follows the family's own convention: linear `{mm/25.4:.1f}`; tape/neon int-or-1-dp of manufacturable inches. Sum across every segment of every run. Linear uses requested length (as the standard number does), tape/neon uses manufacturable length (as the standard number does).

R3. The four-character code is **derived from the group's `config_hash`**, not random and not from project, line or location. Uppercase hex, first 4 characters. On collision with a different group's Item, lengthen (5, 6, ... characters), as `build_artifacts.build_item_code` does. Same group => same number on the schedule, dialog, quote and sales order, with no schedule line required.

R4. The desk dialog uses the readable bundle for groups, with or without a schedule, on Quotation and Sales Order.

R5. Existing Items, Product Bundles, schedule lines, quotes and orders keep their current codes. Nothing is renamed or regenerated.

R6. Item code length stays well under `ITEM_CODE_MAX_LENGTH` (140).

## 5. Implementation plan

### 5.1 New numbering in `api/group_part_number.py`
- Add `build(build_snapshot_or_group, members) -> str` (pure; no DB except attribute-code lookups already used by the families) returning `{prefix}-{length}-GRP-{code}`.
- Add `code_for(config_hash, taken)` implementing R3.
- Remove the project/type/location prefix, `generate()` and the random suffix. Drop the schedule-line check from `is_taken`. Keep the Item-owner check: a code is "taken" only if an Item with that code exists with a **different** `ill_configured_group`.
- **Prefix source (recommended):** add pure helpers that return the prefix parts, refactored out of the existing builders, so there is no string-splitting of finished part numbers (attribute codes may contain hyphens):
  - Linear: extract the part-number segments before `length_inches` in `_generate_part_number` into `_part_number_prefix_parts()`; `_generate_part_number` calls it, so behaviour is unchanged.
  - Tape/neon: extract `[_spec_item_code(spec), *_offering_codes(...)]` from `_build_tape_part_number` / `_build_neon_part_number`.
  - Sheet: the six existing sku segments.
- Do **not** add the prefix to the group snapshot. That would change `config_hash` for new groups and duplicate group records for identical requests.
- Open point for the implementer: at schedule-save time (`assign()`) members are not yet persisted, so the helpers must work from the group's pinned member `build` (`inputs`, `resolved_items`, `computed`). Confirm every needed attribute code is recoverable from the member build; if one is not, resolve it in `fixture_group_configurator._preview_member` where the engine result is in hand and store only a derived value outside the hashed build. If neither works, fall back to generating the number in `ensure_order_bundle` and have `assign()` only reserve it.

### 5.2 Decouple the bundle from a schedule line (`api/fixture_group_order.py`)
- Change `ensure_order_bundle(schedule, line, target_doc=None)` to `ensure_order_bundle(group_name, labels=None, target_doc=None, line=None)`. `labels` replaces the `run_labels(line)` call; the schedule path passes `run_labels(line)`.
- Rewrite `_part_number` to return `group_part_number.build(...)`. Keep the guard that an existing Item with that code must belong to this group and (if a bundle exists) match `_bundle_matches`.
- When a `line` is given, still write `line.group_part_number` / `line.ill_item_code`.
- Update the caller at `ill_project_fixture_schedule.py:680`.

### 5.3 Desk dialog (`api/desk_configurator.py`)
- In the group branch (~L706-755) build the quote artifact with the new `ensure_order_bundle(...)` after `persist_artifact` (which still creates the pinned group record and its internal `ILL-GRP-<hash>` Item). Use the bundle's artifact for the row, MSRP and `_built_summary`.
- Pass `labels = run_labels({"ill_configurator_request": ...})` as today.
- Keep `split_power` / `_power_supply_rows` unchanged.
- `bom` is `None` on bundle artifacts. Check every use of `artifact["bom"]` on this path: `_apply_artifact_to_row` (`bom_no` is skipped when falsy, fine), `_write_schedule_line`, `_built_summary`, and the toast in `public/js/desk/dialog/pricing.js:153`.
- Work Order parent: groups are already disabled there (`groups_enabled`, L308); keep that.
- When a schedule is linked, `assign()` on save yields the same code (deterministic), so the schedule line, row and Item agree.

### 5.4 Schedule assignment (`group_part_number.assign`)
- Rule: if a line already has a `group_part_number` **and** the group is unchanged, keep it, regardless of format (this grandfathers old numbers). Only compute a number when the line has none or its `configured_group` changed.
- Remove the `rpartition("-")[0] == base` test and the duplicate-suffix redraw. Duplicated lines for the same group legitimately share one code now.
- Keep `line.ill_item_code = current`.

### 5.5 Leave alone
- `fixture_group_bom.ensure_artifacts` and the `ILL-GRP-<hash>` Item (internal engineering Item; historical rows depend on it). Update its docstring to say it is internal.
- `portal/*`, `exports.py`, `printing.py`, `packets.py`, `compare.py` and `drawing_import.py` already read `group_part_number`. They get the new format for free.

### 5.6 Docs
- Update `docs/CONFIGURATOR_GROUPING_ALIGNMENT_PLAN.md:174` (still describes `ILL-GRP-<hash>`), and the module docstrings of `group_part_number.py` and `fixture_group_order.py`.
- Note the format in `docs/B2B_STAFF_OPERATIONS.md` next to the Configure & Add Fixture section.

## 6. Tests

Update (`tests/portal_unit/`):
- `test_group_order_bundles.py`: `prefix`/`generate`/`assign` cases (L26-67), line fixtures (L139, L242).
- `test_compare.py` (L163-171): only if its sample code is asserted against the new format.

Add:
- **Invariant test (most valuable):** for a one-run single-segment group, the group number equals the standalone fixture's part number with its feed tail replaced by `GRP-XXXX`. Cover linear, tape, neon and sheet.
- Total length sums across runs and segments, with the family's number formatting.
- Same group => same code; a different group with the same prefix and length => different code; collision => longer code.
- `assign()` keeps a legacy-format number untouched; re-numbers only on a group change; duplicate lines share a code.
- Desk: a group added with no schedule yields row `item_code == group part number` (not `ILL-GRP-`), a Product Bundle exists, `bom_no` empty, work-order creation from the resulting Sales Order produces per-run Work Orders (`tests/portal_unit/test_desk_configurator_save.py` is the closest existing harness).
- Desk with a linked schedule: row code, schedule line code and Item code are all equal.
- JS (`tests/portal_ui/desk_*`): done screen with `bom: null` shows Item and Product Bundle only.

## 7. Risks and decisions

| # | Item | Recommendation |
|---|---|---|
| D1 | Separator for the code: `-GRP-A1B2` vs fixture style `-GRP(A1B2)` (fixtures write `J(A1B2)`) | **Decided: `-GRP(A1B2)`.** |
| D2 | Deterministic hash code vs random letters | Deterministic (R3). Same group shares one Item across projects, like standard fixtures, and removes the need for a schedule line. Trade-off: two dealers configuring an identical group share one Item. |
| D3 | LED Sheet groups have no length | **Decided: total area in square feet, written with an `SF` unit** (e.g. `48SF`) so it is not read as inches. |
| D4 | Old format embedded dealer project/location in a global Item code | Fixed as a side effect; mention in the release notes. |
| R-a | `assign()` re-numbering existing lines when the format changes | Mitigated by 5.4; covered by a test. |
| R-b | Prefix not recoverable from stored member build for some family | See 5.1 open point; the invariant test will catch it. |
| R-c | Rows already on open Quotations still show `ILL-GRP-` | Out of scope (R5). Reconfiguring the row re-applies the readable code. |

## 8. Suggested order of work

1. Prefix helpers + `group_part_number.build/code_for` + unit tests (incl. invariant test).
2. `assign()` grandfathering.
3. Decouple `ensure_order_bundle`; update the schedule caller and tests.
4. Desk dialog group branch; desk tests and JS test.
5. Docs.
6. Manual check on staging: group on a Quotation with no schedule, with a schedule, convert to Sales Order, create Work Orders, print the quote.

## 9. As implemented

- `api/group_part_number.py`:
  - `run_prefix` reads the shared prefix from a run's own stored part number (every family's member build carries `part_number`). It cuts at that run's length token, computed from the run itself, so a feed segment such as `10` with no type code is never mistaken for the length.
  - `total_length`, `base` and `for_group` build the number. The code comes from the hash and is lengthened on collision; `accept` lets the bundle reject its own Item when the bundle rows differ.
  - `assign` keeps any number a line already holds while the group is unchanged, or while that number is already the group's Item.
  - If a run has no part number, the prefix falls back to the template name.
- No change to group snapshots or `config_hash`; existing groups keep their identity.
- `api/fixture_group_order.py`: `ensure_order_bundle(group_name, labels=None, target_doc=None, line=None)` and `_part_number(group, build, rows, line=None)`.
- `api/desk_configurator.py`:
  - On a Quotation or Sales Order the group branch sells the bundle (`_group_order_bundle`). The bundle keeps the selling-company brand and only mirrors its MSRP to the document's price list.
  - The schedule line stores the same `group_part_number` and keeps the group's pinned engineering BOM.
  - Purchase Order / RFQ / Material Request still use the internal group Item. Work Orders still exclude groups.
- Tests: `tests/portal_unit/test_group_order_bundles.py` (`GroupPartNumber`, the no-schedule case) and `tests/portal_unit/test_desk_configurator_save.py` (`DeskGroupPartNumber`).
