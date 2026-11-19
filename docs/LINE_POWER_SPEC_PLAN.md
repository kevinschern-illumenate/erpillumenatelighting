# Plan: spec and power line under catalog LED Tape, Neon and Sheet rows

Status: **implemented** (see §0) · Written 2026-11-18 · Scope: Quotation and Sales Order

## 0. Implementation notes (2026-11-18)

Built as planned, with these deviations, all found by running the math over every live
tape / neon / sheet row (1,023 rows on Quotations and Sales Orders):

- **No template fallback.** The only template that has a spec, `LED-HD-SW`, has no W/ft,
  and its variants range from 0.8 to 14.4 W/ft by output. Borrowing it would print a
  wrong voltage, run or load, so a variant without its own spec is treated as having
  none: "No LED spec on file", and it is listed by the missing-spec report. That report
  now returns 136 Items: the 99 below plus the 37 `LED-HD-SW-O-*` variants.
- **No per-request spec cache.** One save resolves once in 3 queries; a cache only added
  stale-state risk.
- `preview` returns `{"rows": {key: values}, "total_watts": float}`.
- **Print, after the shared ilL print template landed (PR #434):** the spec line and the
  total live in `templates/print/ill_print.html`, not in each format. `line_power(item)`
  prints a muted "Spec" line inside the line's description cell, after its specs and
  before its notes, so it stays on the same table row and page as its line. It is called
  from `priced_items`, so it shows on every quote and order format (dealer and MSRP) and
  stays empty on Sales Invoices, which have no `ill_lp_*` fields. `connected_load()` puts
  the **Connected load (tape / neon / sheet)** total (decision D3) in the aside beside the
  totals on ilL Quotation, ilL Sales Order and both MSRP formats, leaving out alternative
  rows, and only when a row has a load. §4.5 below is the original plan for the old formats.
- The dealer portal (§4.9) is **not** done; it stays optional.
- `add_line_power_fields` also runs from `install.py` `after_install`, because a fresh
  install marks every listed patch as done without running it.

Results on live data: loads computed for 536 rows, a spec without a load (the
`LED-HD-SW` W/ft gap) on 53, no spec on 431. Eleven rows in `Feet` and two in
`16.4ft Reel` at conversion factor 1.0 are computed from the UOM and flagged in their
Spec Note.

## 1. What we are building

When someone adds a **catalog** (non-configured) LED Tape, COB Tape, LED Neon or LED
Sheet Item to a Quotation or Sales Order:

1. The row keeps linking to the Fixture Schedule exactly as it does today (no change
   to `schedule_sync.py` behaviour; see §3.1 and decision D2).
2. The row shows the product's specification from its spec record:
   - Tape / COB / Neon (`ilL-Spec-LED Tape`): **input voltage**, **max run length (ft)**,
     **watts per foot**.
   - LED Sheet (`ilL-Spec-LED-Sheet`): **input voltage**, **watts per sq ft**,
     **watts per sheet**, **max sq ft per 100 W**, and **max panels per feed** when set.
3. The row's quantity is converted to feet (tape/neon) or square feet (sheet) from its
   **UOM**, multiplied by the spec's W/ft (or W/sq ft), and the resulting **line load in
   watts** is shown **underneath the item**:
   - on the printed Quotation and Sales Order (`ilL Quotation`, `ilL Sales Order`), as
     its own row directly below the item row;
   - on the desk form, in the row's detail fields, as a "Load (W)" grid column, and in a
     summary panel directly under the Items grid.

Example, from live data (NON-COW-SW-67-27K-150, Cowlitz neon, 24VDC, 2.74 W/ft,
16.4 ft max run), a row of 864 Inch prints:

```
Cowlitz Series, Dual-bending Neon …            NON-COW-SW-67-27K-150   Inch 864   …
  Spec: 24VDC · 2.74 W/ft · Max run 16.4 ft    Length 72.00 ft · Load 197.3 W
```

Configured rows (`ill_configured_*` set) already carry `ill_total_watts` and are out of
scope (decision D5).

## 2. What the investigation found (codebase + live site)

All live numbers below were read from `illumenatelighting.v.frappe.cloud` on 2026-11-18.

### 2.1 Spec doctypes

| Family | DocType (exact name) | Named by | Fields we use |
|---|---|---|---|
| LED Tape, COB Tape, LED Neon | **`ilL-Spec-LED Tape`** (note the space, not a hyphen) | `field:item`, so **spec name == Item code** | `item`, `product_category`, `input_voltage` (Link → `ilL-Attribute-Output Voltage`, values like `24VDC`), `watts_per_foot`, `voltage_drop_max_run_length_ft`, `max_run_single_feed_ft`, `max_run_double_feed_ft` |
| LED Sheet | `ilL-Spec-LED-Sheet` | name == Item code on every live record, but `item` is not unique, so look up by `item` | `item`, `is_active`, `input_voltage`, `sheet_area_sqft`, `sheet_width_ft`, `sheet_height_ft`, `watts_per_sqft`, `total_sheet_watts`, `max_sqft_per_100w`, `max_panels_per_feed` |

- Neon has **no separate spec doctype**; it is `ilL-Spec-LED Tape` with
  `product_category = "LED Neon"`.
- Live counts: 334 tape specs (256 LED Tape, 41 LED Neon, 37 COB Tape); 12 sheet specs.
- `product_category` on the spec does **not** always match the Item's group (some COB
  Items have specs filed as "LED Tape"). Never branch on `product_category` for math.
  Branch only on which doctype the spec came from.
- "Max run length": the configurator uses `voltage_drop_max_run_length_ft`
  (`tape_neon_configurator.py:672`, `:3136-3167`). Use that, falling back to
  `max_run_single_feed_ft`. On live data the two are equal on every record that has both.
  Show `max_run_double_feed_ft` too when it is set (decision D6).
- The repo fixture `illumenate_lighting/illumenate_lighting/fixtures/ill_spec_led_tape.json`
  is a single stale sample row. Ignore it.

### 2.2 Items and units of measure (this drives the conversion design)

- Tape / COB / Neon catalog Items: `stock_uom = "Inch"`, `sales_uom = "Inch"`,
  `purchase_uom = "Meter"`. Most are **variants** (`variant_of = COB-SD-SW`, …).
- LED Sheet Items: `stock_uom = "Ea"` (one sheet).
- Per-Item conversion tables seen on live Items (factor = inches per UOM):
  `Inch 1`, `Foot 12` (often stored as `11.999999695`), `Feet 12` (9 Items use "Feet"
  instead of "Foot"), `Meter 39.3701`, `16.4ft Reel 196.8 / 196.85 / 196.8504 / 196.92`
  (inconsistent), `50ft Reel 600`, `70ft Reel 840`, `100ft Reel 1200`. 33 Items have
  **only** `Inch`. Sheets: `Ea 1`, `1ft x 2ft Sheet 1`, `1ft x 1ft Sheet 0.5`.
- Other length UOMs that exist on the site: `1,000ft`, `3.28ft Piece`, `6.56ft Piece`,
  `8.2ft Piece`, `Millimeter`, `Centimeter`, `Yard`.

**Live transaction rows with these Items:** 599 Quotation rows (111 quotes) and 422
Sales Order rows (141 orders). UOMs used: Inch (most), Foot, Feet, 16.4ft Reel,
50ft Reel, 100ft Reel, Meter, Ea, `1ft x 2ft Sheet`.

**Data traps found in those rows. The design must survive all of them:**

| Trap | Example | Consequence if we trusted `conversion_factor` |
|---|---|---|
| `Feet` with `conversion_factor = 1.0` on an Inch-stocked Item | SAL-ORD-2026-00071 (6 neon rows), SAL-QTN-2026-00011, ilL-SAL-ORD-Cascade Integration-00003 | Load 12× too low |
| Reel with `conversion_factor = 1.0` | `16.4ft Reel` cf 1.0 on SAL-ORD-2026-00046, ilL-SAL-ORD-Tech Integrated-00002, ilL-SAL-ORD-Cascade Integration-00012 | Load 197× too low |
| Row `item_group` is a stale snapshot | `LED-SNF-…` sheets appear on old rows as group "LED Tape", in UOM `Ea` | Wrong family if detected by group |
| Fractional inch quantities | 143 Quotation rows and 62 Sales Order rows (e.g. 45.5, 56.375) | None for power. Matters for schedule linking (§3.1) |
| Tape sample Items stocked in `Ea` | `SMPL-PNC-…-2FT-…` | No spec, no length: must show nothing |

Therefore: **detect the family by spec lookup, and convert length from the UOM's
physical meaning (its name), not from the row's `conversion_factor`** (decision D1).

### 2.3 Spec coverage (important for expectations)

- 417 sellable, enabled, non-template tape/COB/neon Items: 281 have their own spec,
  37 have a spec only on their **template** Item (`variant_of`), and **99 have no spec at
  all** (e.g. `COB-HD-SW-*` 12 Items, `COB-TL-SW-*`, `COB-SD-CC-*`, `LED-HD-DW-*`).
- On existing transaction rows: Quotations 299 own spec, 39 via template, 21 sheet,
  **240 no spec**; Sales Orders 206 / 14 / 11 / **191 no spec**. Many of the misses are
  disabled legacy Items.
- So: show a clear "No LED spec on file" note when there is none, and ship a
  missing-spec report (§4.8) so the catalog can be completed. (Template fallback was
  dropped during implementation; see §0.)

### 2.4 Permissions

- `ilL-Spec-LED Tape` grants read to role `All`. `ilL-Spec-LED-Sheet` is System Manager
  in its JSON (widened on the site by `patches/catalog_builder_permissions.py`).
- The `purchasing@` API user can read both. Server code must read specs with
  `frappe.db.get_value` / `frappe.get_all` (no permission check), exactly as
  `schedule_sync._sellable_stock_item` reads Item, so the stamp works for any user who
  can save the transaction.

### 2.5 How rows link to the Fixture Schedule today (unchanged by this plan)

`illumenate_lighting/illumenate_lighting/api/schedule_sync.py`:

- Transaction → schedule (`on_transaction_validate` → `plan_transaction_changes` →
  `push_to_schedule` → `_line_from_row`): a new row with no configured links becomes an
  **ACCESSORY** schedule line (`accessory_item = item_code`) when the Item is a stock,
  sales, enabled, non-template Item, and the row's **stock quantity is a whole number**
  (`stock_qty()` → `_whole()`; the schedule line `qty` is `Int`). The row is stamped with
  `ill_schedule_line_id` and `ill_fixture_type`.
- Schedule → transaction (`ill_project_fixture_schedule.py` `append_quote_lines`,
  ACCESSORY branch, around line 950): the row is written with `uom = stock_uom` (Inch)
  and `conversion_factor = 1`.
- Rows whose stock qty is fractional (e.g. 45.5 Inch) are reported "Kept on this
  document only" and **do not** link. See decision D2.

Nothing in this plan changes `schedule_sync.py`. The new fields are derived values and
must **not** be added to `PRODUCT_FIELDS`, `LABEL_FIELDS` or any sync comparison.

### 2.6 Why we must not reuse `ill_total_watts`

`ill_total_watts` already exists on Quotation Item / Sales Order Item, but:

- `portal/commercial_lineage.py` lists it in `FIELDS`, and it is **not** in `DESCRIPTIVE`,
  so it is a **lineage** field. A plain tape row carrying it would be treated as a
  configured build on Delivery Note / Sales Invoice validate: the source-row checks run,
  and the row is forced to copy from its source.
- `public/js/desk/dialog/state.js` `BUILD_FIELDS` and `api/build_links.py` `build_values`
  treat it as configured-build output.

→ Add **new** fields (all prefixed `ill_lp_` for "line power") and keep them out of
`commercial_lineage.FIELDS`, `offer_contract.LINE_FIELDS` comparisons,
`state.js BUILD_FIELDS` and `build_links`.

### 2.7 Where things live

| Concern | File |
|---|---|
| Doc events (bug magnet; edit with care) | `illumenate_lighting/hooks.py` (Quotation ~line 397, Sales Order ~line 410, `doctype_js` line 60) |
| Desk JS | `illumenate_lighting/public/js/quotation.js`, `illumenate_lighting/public/js/sales_order.js` |
| Print formats (rendered from the `.html` on disk; `custom_format: 1`) | `illumenate_lighting/illumenate_lighting/print_format/ill_quotation/ill_quotation.html`, `…/ill_sales_order/ill_sales_order.html` |
| Custom-field patches pattern | `illumenate_lighting/patches/add_build_points_fields.py` (fields created only by a patch; **not** added to the module `fixtures/custom_field.json`. `tests/portal_unit/test_unsynced_custom_fields.py` enforces that every field in that JSON has a creating patch) |
| Unit-test harness (no bench) | `tests/portal_unit/test_services.py` (`load_service`, `Record`), run in CI by `python -B -m unittest discover -s tests/portal_unit` |
| Hook audit test (no network I/O in doc events) | `tests/portal_unit/test_doc_events_audit.py` |
| Length constants | `illumenate_lighting/illumenate_lighting/api/unit_conversion.py` (`MM_PER_INCH`, `MM_PER_FOOT`) |

## 3. Design

### 3.1 Principles

1. **Server is the source of truth.** A `validate` hook stamps the fields on every save.
   The desk JS only previews (by calling the same server function) so users see numbers
   before saving.
2. **Never block a save.** Any failure in the stamp is logged to Error Log and leaves the
   row's power fields blank with a note.
3. **No N+1.** Resolve all specs for a document in at most 4 batched queries (Items,
   tape specs, template tape specs, sheet specs).
4. **Pure math, separately testable.** Put the UOM parsing and the arithmetic in pure
   functions with no `frappe` import, the way `api/led_sheet_math.py` is split from its
   callers.

### 3.2 Length / area conversion (decision D1 = trust the UOM's name)

```
FT_PER_UOM = {
    "inch": 1/12, "foot": 1, "feet": 1, "ft": 1, "yard": 3,
    "meter": 3.280839895, "metre": 3.280839895,
    "centimeter": 0.03280839895, "millimeter": 0.003280839895,
}
REEL_OR_PIECE = r"^\s*([\d,]+(?:\.\d+)?)\s*ft\b"   # "16.4ft Reel", "50ft Reel", "3.28ft Piece", "1,000ft"
SHEET_AREA    = r"^\s*(\d+(?:\.\d+)?)\s*ft\s*x\s*(\d+(?:\.\d+)?)\s*ft\b"  # "1ft x 2ft Sheet" -> 2 sq ft
```

`uom_length_ft(uom) -> float | None`: case-insensitive lookup in `FT_PER_UOM`, else the
`REEL_OR_PIECE` regex (strip commas), else `None`.

`row_length_ft(qty, uom, conversion_factor, stock_uom) -> (feet | None, warning | None)`:

1. `per = uom_length_ft(uom)`. If known: `feet = qty * per`.
2. Else, if `uom_length_ft(stock_uom)` is known: `feet = qty * conversion_factor * that`.
3. Else: `(None, None)` (e.g. a tape Item sold in `Ea`).
4. Consistency check, when both `uom` and `stock_uom` are length UOMs:
   `expected_cf = uom_length_ft(uom) / uom_length_ft(stock_uom)`. If
   `abs(cf - expected_cf) / expected_cf > 0.02`, return the warning
   `"UOM {uom} should convert at {expected_cf:g} {stock_uom}; this row uses {cf:g}. Load uses {expected_cf:g}."`.
   The 2 % tolerance absorbs 196.8 vs 196.85 and 11.999999695.

Sheet area, `row_area_sqft(qty, uom, conversion_factor, stock_uom, spec) -> (sqft | None, warning)`:

1. If the `SHEET_AREA` regex matches `uom`: `sqft = qty * w * h`.
2. Else, if `uom` is a count UOM (`Ea`, `Nos`, `Unit`, `Each`, case-insensitive), or
   `uom == stock_uom`: `sqft = qty * conversion_factor * spec.sheet_area_sqft`.
3. Else `sqft = qty * conversion_factor * spec.sheet_area_sqft` (stock is one sheet).
4. If `spec.sheet_area_sqft` is falsy, use `sheet_width_ft * sheet_height_ft`; if that is
   also unknown, return `(None, "Sheet size missing on spec")`.

### 3.3 Load

- Tape/neon: `watts = round(feet * watts_per_foot, 1)`. No `watts_per_foot` → no watts
  (note "Spec has no W/ft").
- Sheet: `watts = round(sqft * watts_per_sqft, 1)`. If `watts_per_sqft` is missing but
  `total_sheet_watts` and `sheet_area_sqft` are set, use
  `sqft / sheet_area_sqft * total_sheet_watts`.
- Display rounding: feet and sq ft to 2 decimals, W/ft as stored, watts to 1 decimal.
- Do not apply driver headroom or `max_simultaneous_pct`. This is connected load at the
  spec's rating; label it "Load". `power_basis` on live specs is "All Channel Max".

### 3.4 Spec resolution

`resolve_specs(item_codes) -> {item_code: spec_dict}`, batched:

1. `frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "variant_of", "item_group", "stock_uom"])`.
2. Tape: `frappe.get_all("ilL-Spec-LED Tape", filters={"name": ["in", codes + templates]}, fields=[…])`.
   An Item uses its own spec, else its `variant_of` template's spec (37 live Items need
   this fallback).
3. Sheet: `frappe.get_all("ilL-Spec-LED-Sheet", filters={"item": ["in", codes + templates]}, fields=[…], order_by="is_active desc, modified desc")`.
   First row per `item` wins. Same template fallback.
4. If an Item has both a tape and a sheet spec (none do today), prefer the sheet spec when
   its stock UOM is a count UOM, else tape.
5. Each `spec_dict` carries `family` (`"tape"` or `"sheet"`), `spec_doctype`, `spec_name`,
   the fields from §2.1, and `via_template` (bool).
6. Cache the result on `frappe.local` per request (key: sorted codes) so the validate
   hook and the print do not repeat it.

"Tape-like" Items (only these get a "No LED spec on file" note when unresolved): current
`Item.item_group` in `("LED Tape", "COB Tape", "LED Neon", "LED Sheet")`. Use the
**Item's** group, never the row's snapshot.

### 3.5 Which rows are stamped

Stamp a row when **all** are true:

- `item_code` set;
- no configured link: `ill_configured_fixture`, `ill_configured_tape_neon`,
  `ill_configured_led_sheet`, `ill_configured_group`, `ill_configured_product` all empty;
- not `ill_is_power_supply_line`;
- the Item resolves to a spec, **or** is tape-like (then only the note is set).

Every other row: clear all `ill_lp_*` fields if any are set (an item changed from tape
to something else must not keep a stale load).

`is_alternative` rows: stamp them (they print), but exclude them from the document total
(§4.5).

## 4. Implementation steps

### 4.1 New pure module: `illumenate_lighting/illumenate_lighting/api/line_power_math.py`

No `frappe` import. Contents:

- `FT_PER_UOM`, `COUNT_UOMS = {"ea", "nos", "unit", "each"}`, the two regexes.
- `uom_length_ft(uom)`, `sheet_uom_area_sqft(uom)`.
- `row_length_ft(qty, uom, conversion_factor, stock_uom)` → `(feet, warning)`.
- `row_area_sqft(qty, uom, conversion_factor, stock_uom, spec)` → `(sqft, warning)`.
- `compute_row(row_values: dict, spec: dict | None, tape_like: bool) -> dict` returning
  exactly the `ill_lp_*` field values (§4.3), including `ill_lp_summary` and
  `ill_lp_note`. `row_values` holds `qty`, `uom`, `conversion_factor`, `stock_uom`.
- `format_summary(values) -> str`, e.g.:
  - tape: `"24VDC · 3.05 W/ft · Max run 16.4 ft (32.8 ft double feed) · Length 32.80 ft · Load 100.0 W"`
  - sheet: `"24VDC · 5 W/sq ft · 10 W/sheet · Max 16 sq ft per 100 W · Area 18.00 sq ft · Load 90.0 W"`
  - missing pieces are dropped from the string. When there is no load, end with the note.
- `document_total_watts(rows) -> float`: sum of `ill_lp_watts`, skipping `is_alternative`.

### 4.2 Frappe adapter: `illumenate_lighting/illumenate_lighting/api/line_power.py`

```python
LP_FIELDS = ("ill_lp_spec_doctype", "ill_lp_spec", "ill_lp_family", "ill_lp_input_voltage",
             "ill_lp_watts_per_ft", "ill_lp_max_run_ft", "ill_lp_max_run_double_ft",
             "ill_lp_watts_per_sqft", "ill_lp_watts_per_sheet", "ill_lp_max_sqft_per_100w",
             "ill_lp_length_ft", "ill_lp_area_sqft", "ill_lp_watts", "ill_lp_summary", "ill_lp_note")

def resolve_specs(item_codes) -> dict: ...          # §3.4, batched, cached on frappe.local
def stamp_rows(rows) -> None: ...                   # §3.5, sets via _set() guard (row.meta.has_field)
def stamp_line_power(doc, method=None): ...         # doc_events entry point
@frappe.whitelist()
def preview(rows): ...                              # desk preview, §4.6
```

- `_set(row, field, value)`: copy the guard from `schedule_sync._set` so the code is
  safe before the patch runs.
- `stamp_line_power`: return if `doc.docstatus == 2` or
  `frappe.flags.in_import / in_migrate / in_install / in_patch`; then
  `try: stamp_rows(doc.get("items")) except Exception: frappe.log_error(title=f"Line power: {doc.doctype} {doc.name}", message=frappe.get_traceback())`.
  **Never raise.** No network calls (the doc-events audit test checks this).
- `preview(rows)`:
  - `rows` is a JSON string or list of `{key, item_code, qty, uom, conversion_factor, stock_uom}`.
    Cap at 500 rows.
  - Require `frappe.has_permission("Quotation", "read") or frappe.has_permission("Sales Order", "read")`,
    else `frappe.throw(..., frappe.PermissionError)`.
  - Return `{key: {field: value}}` plus `"total_watts"`.
  - Read-only; writes nothing.

### 4.3 Custom fields patch: `illumenate_lighting/patches/add_line_power_fields.py`

Model it on `add_build_points_fields.py`. Call `create_custom_fields({...}, update=True)`
for **both** `Quotation Item` and `Sales Order Item`, inserted after
`ill_schedule_line_id` (it exists on both):

| fieldname | type | label | notes |
|---|---|---|---|
| `ill_lp_section` | Section Break | Spec & Power | `collapsible: 1` |
| `ill_lp_summary` | Small Text | Spec & Power | what the print shows |
| `ill_lp_note` | Data | Spec Note | e.g. "No LED spec on file", UOM warning |
| `ill_lp_watts` | Float | Load (W) | `precision: 1`, `in_list_view: 1`, `columns: 1` |
| `ill_lp_length_ft` | Float | Length (ft) | `precision: 2` |
| `ill_lp_area_sqft` | Float | Area (sq ft) | `precision: 2` |
| `ill_lp_column` | Column Break | | |
| `ill_lp_family` | Select | Spec Family | options `\nTape\nSheet` |
| `ill_lp_input_voltage` | Data | Input Voltage | |
| `ill_lp_watts_per_ft` | Float | W/ft | |
| `ill_lp_max_run_ft` | Float | Max Run (ft) | |
| `ill_lp_max_run_double_ft` | Float | Max Run, Double Feed (ft) | |
| `ill_lp_watts_per_sqft` | Float | W/sq ft | |
| `ill_lp_watts_per_sheet` | Float | W/Sheet | |
| `ill_lp_max_sqft_per_100w` | Float | Max sq ft per 100 W | |
| `ill_lp_spec_doctype` | Link → DocType | Spec DocType | `hidden: 1` |
| `ill_lp_spec` | Dynamic Link → `ill_lp_spec_doctype` | Spec | |

Set on every non-break field: `read_only: 1`, `allow_on_submit: 1` (so the backfill and
Sales Order "Update Items" can refresh them), `print_hide: 1` (the custom print formats
render the summary themselves), `no_copy: 0` (they carry Quotation → Sales Order; validate
recomputes anyway).

On the parents `Quotation` and `Sales Order`, add `ill_lp_panel` (HTML, label
"Tape / Neon / Sheet Power"), inserted after `items`. This is the desk summary
"underneath" the grid. HTML fields have no DB column.

Add `illumenate_lighting.patches.add_line_power_fields` to the end of
`illumenate_lighting/patches.txt`. Do **not** add these fields to
`illumenate_lighting/illumenate_lighting/fixtures/custom_field.json`. Recent field
patches don't, and `test_unsynced_custom_fields.py` would then need a `NEW_PATCHES` entry.

`in_list_view` on `ill_lp_watts`: the grid already shows Section/Room and Fixture Type.
Check the Quotation and Sales Order Items grid on staging still fits. If it is too
crowded, set `in_list_view: 0` and rely on the panel and print (decision D4).

### 4.4 Hooks: `illumenate_lighting/hooks.py`

Make the smallest possible edits. This file is the repo's top bug-fix hotspot.

```python
"Quotation": {
    "validate": [
        "…api.build_links.follow_items",
        "…api.schedule_sync.on_transaction_validate",
        # Last: schedule sync may rescale row quantities above.
        "illumenate_lighting.illumenate_lighting.api.line_power.stamp_line_power",
    ],
    …
},
"Sales Order": {
    "validate": [
        "…api.build_links.follow_items",
        "…portal.order_review.validate_order",
        "…api.schedule_sync.on_transaction_validate",
        "…api.build_points.roll_up_sales_order",
        "illumenate_lighting.illumenate_lighting.api.line_power.stamp_line_power",
    ],
    # "Update Items" on a submitted order changes qty/uom without running validate.
    "before_update_after_submit": [
        "illumenate_lighting.illumenate_lighting.portal.order_review.validate_order",
        "illumenate_lighting.illumenate_lighting.api.line_power.stamp_line_power",
    ],
    …
},
```

Ordering matters. `schedule_sync.push_to_schedule` can rescale `row.qty` for rows whose
line quantity the schedule changed, so the stamp must run **after**
`on_transaction_validate`. `push_to_transaction` saves target drafts with
`ill_skip_schedule_sync`, but that flag only skips sync; validate (and so the stamp) still
runs, so drafts updated from the schedule are re-stamped.

`doctype_js`: add `"public/js/line_power.js"` for **Quotation** and **Sales Order**.
`"Quotation"` is currently a bare string. Make it a list:
`"Quotation": ["public/js/quotation.js", "public/js/line_power.js"]`, and append to the
Sales Order list. The helpdesk / portal-link loops below already normalize strings and
lists.

### 4.5 Print formats

In **both** `ill_quotation.html` and `ill_sales_order.html`, each file has two item
loops: the sectioned loop (~line 331 / ~376) and the flat loop (~line 367 / ~412).

1. Add one macro near the top of the file and call it in both loops, **between the item
   `<tr>` and the `additional_notes` row**:

```jinja
{%- macro ill_lp_row(item) -%}
  {%- if item.get("ill_lp_summary") -%}
  <tr class="ill-spec-row">
    <td class="table-sr"></td>
    <td colspan="5"><span class="ill-inline-label">Spec</span>{{ item.ill_lp_summary | e }}</td>
  </tr>
  {%- endif -%}
{%- endmacro -%}
```

2. CSS, next to `.ill-note-row` (match its padding; muted colour; smaller font):
   `.ill-doc .ill-spec-row td { font-size: 9px; color: #555; padding-top: 0; border-top: 0; }`.
3. Optional (decision D3): in the totals block, when any row has `ill_lp_watts` and is
   not `is_alternative`, print
   `Estimated connected load (tape / neon / sheet): {{ total }} W`.
   Compute the total in Jinja with a namespace sum.
4. Section subtotals and the `row_ns.sr` numbering must not change. The spec row has no
   serial number, like the Fixture Type and notes rows.

### 4.6 Desk JS: `illumenate_lighting/public/js/line_power.js`

One file, registered for both doctypes:

```js
(function () {
  const CHILD = { 'Quotation': 'Quotation Item', 'Sales Order': 'Sales Order Item' };
  const METHOD = 'illumenate_lighting.illumenate_lighting.api.line_power.preview';

  function rowsFor(frm) { /* items with item_code → {key: row.name, item_code, qty, uom, conversion_factor, stock_uom} */ }
  const refreshPreview = frappe.utils.debounce(function (frm) {
    if (frm.doc.docstatus !== 0) return;                       // submitted: server values only
    frappe.call({ method: METHOD, args: { rows: rowsFor(frm) } }).then(r => {
      const result = (r && r.message) || {};
      (frm.doc.items || []).forEach(row => {
        const values = result[row.name]; if (!values) return;
        Object.keys(values).forEach(f => { if (row[f] !== values[f]) row[f] = values[f]; }); // local write; avoid set_value storms
      });
      frm.refresh_field('items');
      renderPanel(frm, result.total_watts);
    });
  }, 400);

  function renderPanel(frm, total) { /* write a small table into frm.fields_dict.ill_lp_panel.$wrapper:
     Fixture Type | Item | Qty UOM | Length/Area | W/ft or W/sq ft | Load (W), then a Total row.
     Escape every value with frappe.utils.escape_html. Hide the field (frm.toggle_display) when no row has ill_lp_summary. */ }

  Object.keys(CHILD).forEach(parent => {
    frappe.ui.form.on(parent, { refresh: frm => renderPanel(frm), items_remove: frm => refreshPreview(frm) });
    frappe.ui.form.on(CHILD[parent], {
      item_code: frm => refreshPreview(frm), qty: frm => refreshPreview(frm),
      uom: frm => refreshPreview(frm), conversion_factor: frm => refreshPreview(frm),
    });
  });
})();
```

Notes for the implementer:

- `frappe.ui.form.on` handlers **add to** the existing ones in `quotation.js` /
  `sales_order.js`; don't edit those files.
- On `refresh`, render the panel from saved `ill_lp_*` values only. Don't call the
  server: writing on refresh would mark a clean form dirty.
- ERPNext sets `conversion_factor` asynchronously after a `uom` change. The `uom` and
  `conversion_factor` triggers plus the 400 ms debounce cover it.
- The values written locally are overwritten by the server on save, so a stale preview
  can't persist.

### 4.7 Backfill patch: `illumenate_lighting/patches/backfill_line_power.py`

Run after `add_line_power_fields` in `patches.txt`.

- For `Quotation` and `Sales Order` with `docstatus in (0, 1)`, select item rows whose
  `item_code` is in the set of Items that have a tape or sheet spec, or whose Item is in a
  tape-like group (live: ~1,000 rows across ~250 documents).
- Reuse `resolve_specs` + `compute_row`, and write with
  `frappe.db.set_value(child_doctype, row_name, values, update_modified=False)`.
- Skip configured and power-supply rows (§3.5).
- Wrap each parent in try/except → `frappe.log_error`. Print a count. Never fail the
  migrate, the same as `add_build_points_fields.py` does for its backfill.
- Print formats of already-submitted documents then show the line immediately.

### 4.8 Missing-spec report (catalog clean-up aid)

Add a whitelisted, System-Manager-only `line_power.missing_specs()`. It returns enabled,
sellable, non-template Items in the four groups that resolve to no spec (own or
template), with `item_group` and `variant_of`. Expose it as a button
**"Tape Items Missing Spec"** under the `Tools` group on the Quotation form for System
Managers, showing the list in a dialog. Live today it returns 99 Items. Optional; can be
deferred (decision D7).

### 4.9 Portal (optional, decision D3)

`portal/offer_contract.py` `LINE_FIELDS` snapshots quote rows for dealers. To show the
spec line on the dealer quote page:

- Add `"ill_lp_summary"` and `"ill_lp_watts"` to `LINE_FIELDS`. Do **not** add them to
  the keys compared in `assert_conversion_matches`.
- In `illumenate_lighting/templates/pages/quote_detail.html` (line ~48, inside
  `ill-lines__meta`), append `{% if line.ill_lp_summary %}<div class="ill-lines__spec">{{ line.ill_lp_summary | e }}</div>{% endif %}`.
  Old snapshots lack the key, and the `if` handles that.
- Run `python -B tools/check_portal_templates.py`.

## 5. Tests

Add `tests/portal_unit/test_line_power.py` (pure tests import `line_power_math` directly;
adapter tests use `load_service(ROOT + ".api.line_power")` from `test_services.py`, as
`test_build_links.py` does):

**UOM parsing.** `uom_length_ft` for Inch → 1/12, Foot/Feet/foot → 1, Meter → 3.2808,
`16.4ft Reel` → 16.4, `50ft Reel` → 50, `70ft Reel` → 70, `100ft Reel` → 100,
`1,000ft` → 1000, `3.28ft Piece` → 3.28, `Ea` → None, `Box` → None.
`sheet_uom_area_sqft("1ft x 2ft Sheet")` → 2, `"1ft x 1ft Sheet"` → 1.

**Length and warnings, using live cases:**

| qty | uom | cf | stock_uom | feet | warning? |
|---|---|---|---|---|---|
| 864 | Inch | 1 | Inch | 72.0 | no |
| 10 | Foot | 11.999999695 | Inch | 10.0 | no |
| 10 | Feet | 1.0 | Inch | 10.0 | **yes** |
| 1 | 16.4ft Reel | 196.8 | Inch | 16.4 | no (within 2 %) |
| 1 | 16.4ft Reel | 1.0 | Inch | 16.4 | **yes** |
| 0.5 | 16.4ft Reel | 1.0 | Inch | 8.2 | **yes** |
| 2 | Meter | 39.37 | Inch | 6.5617 | no |
| 1 | Ea | 1 | Ea | None | no |

**Load and summary:**

- NON-COW-SW-67-27K-150 (24VDC, 2.74 W/ft, 16.4 / 32.8 ft) × 864 Inch → 72.00 ft,
  **197.3 W**, summary contains `24VDC`, `2.74 W/ft`, `Max run 16.4 ft`.
- COB-SD-DW-20-1830K-500-3M-WH (6.67 W/ft, 12 ft) × 1 `16.4ft Reel` → **109.4 W**.
- COB-FC-SW-20-27K-300-3M-WH-8MM (3.05 W/ft) × 10 Feet with cf 1.0 → **30.5 W** plus
  the UOM warning in `ill_lp_note`.
- Sheet LED-SNF-SW-O-27K-10W-3M-WH (2 sq ft, 5 W/sq ft, 10 W/sheet, 16 sq ft/100 W)
  × 9 Ea → 18.00 sq ft, **90.0 W**. × 2 `1ft x 1ft Sheet` → 2.00 sq ft, 10.0 W.
- Sheet spec without `watts_per_sqft` but with `total_sheet_watts` → uses total per sheet.
- Tape spec without `watts_per_foot` (live: `LED-HD-SW`) → no watts, note "Spec has no W/ft".

**Resolution and stamping (adapter, mocked `frappe.get_all`):**

- A variant with no own spec uses its `variant_of` spec (`via_template`).
- A tape-group Item with no spec → only `ill_lp_note = "No LED spec on file"`.
- A non-tape Item (e.g. a driver) → nothing set, and stale `ill_lp_*` values are cleared.
- Configured rows (`ill_configured_tape_neon` set) and `ill_is_power_supply_line` rows
  are untouched.
- `resolve_specs` makes at most 4 `get_all` calls for 50 rows (no N+1).
- `stamp_line_power` swallows an exception from `get_all` and calls `frappe.log_error`.
- `stamp_line_power` returns early for `docstatus == 2` and when `frappe.flags.in_migrate`.
- `document_total_watts` skips `is_alternative` rows.

**`preview`:** permission denied without Quotation/Sales Order read; a list longer than
500 rows → throws; returns `total_watts`.

**Hook wiring** (parse `hooks.py` with `ast` as `test_doc_events_audit.py` does):

- `stamp_line_power` is the **last** Quotation `validate` handler and comes **after**
  `schedule_sync.on_transaction_validate` in Sales Order `validate`.
- It appears in Sales Order `before_update_after_submit`.
- `public/js/line_power.js` is in `doctype_js` for both doctypes.
- The existing `test_doc_events_audit.py` must still pass (no network in the new handler).

**Patch:** `add_line_power_fields.execute()` calls `create_custom_fields` with both child
doctypes and both parents, and every non-break field has `read_only`, `allow_on_submit`
and `print_hide`. Use `run_patch` from `test_unsynced_custom_fields.py` as the model.

**Regression:** run the whole suite: `python -B -m unittest discover -s tests/portal_unit`,
especially `test_schedule_sync.py`, `test_build_links.py`,
`test_quote_schedule_links.py`. Lint with `ruff check .` and `ruff format .`.

## 6. Manual acceptance on staging

1. Run `bench migrate`, and confirm both patches ran and the backfill count is printed.
2. New Quotation linked to a draft Fixture Schedule. Add `NON-COW-SW-67-27K-150`,
   qty 864, UOM Inch. Before saving, the row shows Length 72.00 ft and Load 197.3 W, and
   the panel under Items shows the row and the total. Save. The values persist, and the
   schedule gains an ACCESSORY line for the Item with qty 864, the same as today.
3. Change the UOM to Foot and qty to 72. The load stays 197.3 W, and the schedule line
   stays 864 (stock qty is unchanged).
4. Add `COB-SD-DW-20-1830K-500-3M-WH` as 1 × `16.4ft Reel` → 109.4 W.
5. Add `LED-SNF-SW-O-27K-10W-3M-WH` × 9 Ea → 90.0 W, with the sheet spec line.
6. Add a tape Item with no spec (e.g. `COB-HD-SW-20-27K-300-3M-WH-8MM`) → note
   "No LED spec on file" and no load.
7. Add a driver Item → no spec fields, no panel row.
8. Print `ilL Quotation`. Each tape/neon/sheet row has a muted "Spec" line directly
   under it, above any notes, and serial numbers and section subtotals are unchanged.
9. Make a Sales Order from the Quotation. The fields carry over. Submit it, then use
   **Update Items** to change a tape qty: the load updates.
10. Open SAL-ORD-2026-00071 (neon rows in `Feet` with cf 1.0) after the backfill. The
    load is computed as feet (×12 vs the stored stock qty), and the row's Spec Note
    shows the UOM warning.
11. Delivery Note from that Sales Order: it saves normally. The new fields are not on
    Delivery Note Item, and `commercial_lineage` is not triggered for plain rows.

## 7. Decisions for Kevin (defaults chosen; the implementer can proceed with them)

- **D1, UOM name vs row conversion factor.** Default: compute length from the UOM's
  name (Feet = 12 in, 16.4ft Reel = 16.4 ft) and show a warning when the row's conversion
  factor disagrees by more than 2 %. Six-plus live Sales Order rows have `Feet` /
  `16.4ft Reel` at cf 1.0, so their stock quantity (and inventory deduction) is wrong
  today. Separately from this feature, those rows and the Items' UOM tables are worth
  cleaning up.
- **D2, fractional-inch tape rows don't link to the schedule.** Today a row whose stock
  quantity isn't a whole inch (205 live rows, e.g. 45.5") stays on the quote only,
  because schedule line `qty` is an integer. Default: unchanged ("link like it does
  now"). The alternative is to round tape ACCESSORY lines up to the next whole inch when
  creating the line. That touches `schedule_sync._line_from_row` / `stock_qty` and its
  tests, so it's a separate change.
- **D3, where else to show it.** Default: desk and PDF. Optional: the document-level
  "Estimated connected load" total on the PDF (§4.5.3) and the dealer portal quote page
  (§4.9).
- **D4, the Load (W) grid column.** Default on. Turn it off if the Items grid gets
  crowded.
- **D5, configured tape/neon/sheet rows.** Default: unchanged (they already carry
  `ill_total_watts` from the build). Showing a spec line for them too would be a small
  follow-up using the same print macro.
- **D6, max run shown.** Default: `voltage_drop_max_run_length_ft` (the configurator's
  limit), plus the double-feed max when set.
- **D7, missing specs.** 99 sellable tape/neon Items have no spec (own or template). The
  feature shows "No LED spec on file" for them until specs are added. The optional
  report (§4.8) lists them.

## 8. Files touched (checklist)

- [ ] `illumenate_lighting/illumenate_lighting/api/line_power_math.py` (new, pure)
- [ ] `illumenate_lighting/illumenate_lighting/api/line_power.py` (new: resolver, hook, `preview`, optional `missing_specs`)
- [ ] `illumenate_lighting/patches/add_line_power_fields.py` (new)
- [ ] `illumenate_lighting/patches/backfill_line_power.py` (new)
- [ ] `illumenate_lighting/patches.txt` (append both)
- [ ] `illumenate_lighting/hooks.py` (Quotation validate, Sales Order validate + `before_update_after_submit`, `doctype_js`)
- [ ] `illumenate_lighting/public/js/line_power.js` (new)
- [ ] `illumenate_lighting/illumenate_lighting/print_format/ill_quotation/ill_quotation.html`
- [ ] `illumenate_lighting/illumenate_lighting/print_format/ill_sales_order/ill_sales_order.html`
- [ ] `tests/portal_unit/test_line_power.py` (new)
- [ ] Optional: `portal/offer_contract.py`, `templates/pages/quote_detail.html`

Must **not** change: `api/schedule_sync.py`, `portal/commercial_lineage.py`,
`api/build_links.py`, `public/js/desk/dialog/state.js`, the existing `ill_total_watts`
semantics, or the module `fixtures/custom_field.json`.
