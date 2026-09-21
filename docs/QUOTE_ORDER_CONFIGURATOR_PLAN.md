# Quotation / Sales Order — Embedded Configurator with Project & Fixture-Schedule Sync

> **Audience:** an AI coding agent (or developer) implementing this end-to-end.
> **Repo:** `illumenate_lighting` Frappe/ERPNext custom app. No bench is available in this
> workspace — verify with static checks (`python -m compileall -q illumenate_lighting`,
> `node --check <file>.js`, Pylance) and hand the `bench run-tests` command back to the user.
> **Do not** install frappe/erpnext locally.

---

## 0. Goal (what the user asked for)

From a **draft Quotation or Sales Order** in the desk, open a tool that shows the **same
`/portal/configure` experience**, lets the user pick/create the **ilL-Project + ilL-Project-
Fixture-Schedule** the work belongs to, enter **Fixture Type** (e.g. `A1`), **Section / Room**
(location), qty and notes, configure the product, and on save:

1. persist the configured record (ilL-Configured-Fixture / ilL-Configured-Tape-Neon), Item,
   BOM and MSRP Item Price exactly as the portal does;
2. **write / update the fixture-schedule line** (`line_id`, `location`, `qty`, `notes`,
   configured links) so the customer sees it in the portal — no double entry;
3. **insert a new item row** into the Quotation / Sales Order with `ill_section_label`
   (= location), `ill_fixture_type` (= line_id), `ill_schedule_line_id`, all `ill_*`
   configured-product fields, correct pricing, and set the header `ill_fixture_schedule` link;
4. be robust: works on **new / unsaved** documents, supports "add another" in a loop, prevents
   linking two schedules to one transaction, and fails loudly with actionable messages.

---

## 1. Investigation findings — what already exists

### 1.1 Previous attempt (present in the repo, partially working)

| Piece | File | Status |
|---|---|---|
| Desk dialog controller (`IllDesk.addConfiguratorButton`, `IllDesk.openConfiguratorDialog`, `DialogController`) | `illumenate_lighting/public/js/desk/desk_dialog.js` | Works for saved drafts; 2 steps (pick type + qty → embedded configurator). No project/schedule, no fixture type / location. |
| Shim exposing `window.illumenate_lighting.quote_order_configurator.{add_buttons,show_dialog}` | `illumenate_lighting/public/js/quote_order_configurator.js` | Fine. Loaded via `frappe.require` from quotation.js / sales_order.js. |
| Form scripts that call the shim (`Tools ▸ Configure & Add Fixture`) | `illumenate_lighting/public/js/quotation.js`, `illumenate_lighting/public/js/sales_order.js` | Fine. Also contain `Set Section / Room` tool and `Get Items From ▸ Fixture Schedule`. |
| Global desk assets | `illumenate_lighting/hooks.py` → `app_include_js` = shared_configurator.js, fixture_steps.js, tape_neon_steps.js, desk/desk_dialog.js; `app_include_css` incl. `css/configurator/desk_configurator.css` | Fine. |
| Server-rendered configurator partial for embedding | `illumenate_lighting/templates/pages/configure.py::get_configurator_markup(product_category, product_slug, selected_template)` → renders `templates/includes/configurator_fixture_form.html` or `configurator_tape_neon_form.html` | Fine. Refuses LED Sheet. |
| Scoped configurator classes (multi-instance safe, `this.$()` scoped DOM) | `public/js/configurator/shared_configurator.js` (`IllConfigurator.Base`, project/schedule/line loaders), `fixture_steps.js` (`IllConfigurator.Fixture`, **single-segment wizard**), `tape_neon_steps.js` (`IllConfigurator.TapeNeon`) | Both classes honour `context.saveHandler(payload)`; when present they skip their own schedule save. |
| Builder API | `illumenate_lighting/illumenate_lighting/api/configured_product_builder.py`: `calculate_and_lookup`, `preview_bom`, `preview_prospective_bom`, `save_and_apply`, `save_and_apply_from_portal`, `_fixture_payload_from_portal_selections`, `_dispatch_save`, `_ensure_fixture_artifacts`, `_ensure_tape_neon_artifacts` | Solid engine/Item/BOM layer. `save_and_apply` **requires a saved parent** and calls `parent_doc.save()`. |
| Row writer + pricing | `illumenate_lighting/illumenate_lighting/api/quote_order_configurator.py`: `_get_editable_parent`, `_get_or_add_item_row`, `_apply_artifact_to_row`, `_apply_pricing_to_row` (uses `erpnext.stock.get_item_details.get_item_details` so Pricing Rules apply), `apply_existing_configured_product`, `get_bom_preview`, `qoc_get_product_types` | Good, but **never stamps `ill_section_label`, `ill_fixture_type`, `ill_schedule_line_id`, `additional_notes`**. |
| Custom fields | `illumenate_lighting/illumenate_lighting/fixtures/custom_field.json` (canonical) + legacy patches `patches/add_quote_order_configurator_fields.py`, `patches/add_configured_variant_fields.py`, `patches/consolidate_section_label_field.py` | **All needed fields already exist**: Quotation Item & Sales Order Item: `ill_section_label`, `ill_fixture_type`, `ill_product_type`, `ill_configured_fixture`, `ill_configured_tape_neon`, `ill_configured_led_sheet`, `ill_configured_product_doctype`, `ill_configured_product`, `ill_configured_item`, `ill_bom`, `ill_configuration_json`, `ill_bom_override_json`, `ill_template_code`, `ill_requested_length_mm`, `ill_mfg_length_mm`, `ill_runs_count`, `ill_total_watts`, `ill_finish`, `ill_lens`, `ill_engine_version`, `ill_schedule_line_id`, `ill_is_power_supply_line`, `ill_power_supply_for`, `ill_parent_configured_fixture`. Headers: Quotation.`ill_fixture_schedule`, Sales Order.`ill_fixture_schedule` (read-only Link). **No new custom fields are required.** |
| Tests | `api/test_quote_order_configurator.py` (LED sheet pricing only) | Thin. |

### 1.2 Schedule-side building blocks to reuse

| Need | Existing code |
|---|---|
| Portal → schedule save for fixtures | `api/webflow_schedule.py::add_to_schedule(schedule_id, configuration, quantity, fixture_type_id, notes)` — appends a line with `line_id`, `configured_fixture`, `qty`, `notes`, `ill_item_code`; **does not accept `location`**. `_get_next_fixture_type_id(schedule)` generates `A1, A2 … B1`. |
| Portal → schedule save for tape/neon | `api/tape_neon_configurator.py::save_tape_to_schedule(schedule_name, line_idx, configuration_result)` and `save_tape_neon_template_to_schedule(...)` — set `product_type`, `configured_tape_neon`, `tape_neon_template`, `ill_item_code`, `manufacturable_length_mm`, `notes=build_description`, and **`variant_selections` JSON (required: `_validate_configuration_status` treats a tape/neon line as configured only if `variant_selections` is set)**. |
| Generic line add/update from portal | `api/portal.py::add_schedule_line(schedule_name, line_data)`, `update_schedule_line(...)`, `save_configured_fixture_to_schedule(schedule_name, configured_fixture_id, manufacturable_length_mm, line_idx)`, `update_configured_fixture_on_schedule(...)`. |
| Project / schedule pickers | `api/portal.py::get_user_projects_for_configurator()` (internal users → all active projects), `get_schedules_for_project(project_name)`, `get_schedule_lines_for_configurator(schedule_name)`; `portal.create_project(project_data)`, `portal.create_schedule(schedule_data)`. `webflow_schedule.create_quick_project_and_schedule` exists but **omits the required `ilL-Project.customer` → will raise MandatoryError**. |
| Schedule → transaction rows (the reverse direction) | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py::append_quote_lines(...)` and `_stamp_group_fields()` — the canonical mapping: `ill_section_label ← line.location`, `ill_fixture_type ← line.line_id`, `ill_schedule_line_id ← line.name`, `additional_notes ← line.notes`. `api/quote_from_schedule.py::_add_schedule_to_transaction` enforces **one transaction ↔ one schedule** via header `ill_fixture_schedule`. |
| Permissions | `portal/access.py` (`get_actor`, `can_attach_configured_record`), `ill_project_fixture_schedule.has_permission`, `ill_project.has_permission`, `_is_internal_user`. |
| Status lifecycle | `ill_project_fixture_schedule.py`: `PORTAL_SETTABLE_STATUSES`, `transition_schedule_status(schedule, new_status)` (leaving QUOTED auto-versions), `set_lifecycle_status`, `on_sales_order_submit/cancel/trash` hooks (registered in hooks.py `doc_events["Sales Order"]`). **No Quotation hooks exist.** |
| Pricing | `manufacturing_generator._create_item_price_at_msrp(item_code, msrp, messages)`; `ilLProjectFixtureSchedule._check_and_update_item_pricing(item_code, configured_fixture)` / `_check_and_update_tape_neon_item_pricing(...)` ensure the MSRP Item Price exists so `get_item_details` returns a rate. |

### 1.3 Why the previous attempt "did not work as intended" (root causes)

1. **Deadlock on new quotes.** `desk_dialog.js::canConfigure()` hides the button when `frm.is_new()`; `save_and_apply` needs a persisted parent and calls `parent_doc.save()`. A brand-new Quotation cannot be saved with zero items (`items` is mandatory), so the tool is unusable on a fresh quote until the user adds some other item first.
2. **No schedule / project linkage at all.** Rows land only on the transaction; the customer-facing schedule is never written, so the "double work" remains.
3. **Grouping fields missing.** `_apply_artifact_to_row` never sets `ill_section_label` / `ill_fixture_type` / `ill_schedule_line_id` / `additional_notes`, so print formats can't group the rows and there is no traceability back to a schedule line.
4. **No inputs for Fixture Type / Section-Room / Notes** in the dialog (only qty).
5. **Product coverage is narrower than `/portal/configure`.** The dialog embeds the *wizard* fixture class (single segment) and the tape/neon class. The default portal "coordinator" mode (multi-segment fixtures, jumper-chained tape runs, bulk reel, LED Sheet, Extrusion Kit) is ~3,100 lines of **inline JS inside `templates/pages/configure.html`** and is not embeddable as-is.
6. Minor: `create_quick_project_and_schedule` is broken (missing customer); `qoc_get_product_types()` references `webflow_configurator.get_configurator_init_by_template`, which should be verified to exist or removed.

---

## 2. Target design

### 2.1 Principles

* **Reuse the scoped-class embedding** (Fixture wizard + TapeNeon) and the builder/engine layer. Don't rewrite engines.
* **Server builds, client inserts.** The server persists everything that is *independent of the transaction* (configured record, Item, BOM, Item Price, **schedule line**) and returns a fully-priced **row values dict**. The client inserts the row with `frm.add_child('items', values)`. This works for **new/unsaved** documents and removes the "must save first" constraint. Keep `save_and_apply` for API/tests, but the dialog no longer depends on it.
* **Schedule is the source of truth for location / fixture type.** The row is stamped from the schedule line exactly like `_stamp_group_fields` does.
* **One transaction ↔ one schedule** (existing rule). The dialog locks to `frm.doc.ill_fixture_schedule` when set and sets it on first add.
* Every server entry point validates permissions and status and returns `{success: False, error: "..."}` rather than raising where the UI can recover; raise `frappe.throw` for programmer errors.

### 2.2 User flow (dialog)

```
[Configure & Add Fixture]  (toolbar button + button under the Items grid; visible on draft docs incl. new)
   │  prerequisite: customer set (Quotation.party_name w/ quotation_to=Customer, or SO.customer)
   ▼
Step 1  Project & Schedule
   • Project   : Link ilL-Project filtered {customer, is_active=1}  ── or ── [Create new] name (default: quote title / customer name)
   • Schedule  : Link ilL-Project-Fixture-Schedule filtered {ill_project} ── or ── [Create new] name (default "Main Schedule")
     - if frm.doc.ill_fixture_schedule is set → both pre-filled & read-only, with "linked" badge
     - schedule status badge; if status ∉ {DRAFT, READY} or is_locked → explain + offer "Create new version" (calls schedule.create_new_version)
   • ☐ Skip schedule (add to this document only)  — allowed, shown with a warning
   ▼
Step 2  Line details
   • Product type pills: Linear Fixture | LED Tape | LED Neon  (LED Sheet / Extrusion Kit: see §6)
   • Schedule line: [+ New line] (default) or pick an existing *Pending* line of the schedule → prefills Fixture Type / Location / Qty / Notes
   • Fixture Type (Data, reqd)  default = next free id from server (`A1`, `A2`…) considering BOTH schedule lines and frm.doc.items[].ill_fixture_type
   • Section / Room (Data, reqd if linked to schedule) with suggestions = distinct ill_section_label on frm + distinct location on schedule
   • Qty (Int ≥1), Notes (Small Text)
   ▼
Step 3  Configure  (embedded scoped configurator, as today)
   • configurator's own Validate / Calculate / Add button → saveHandler → server `build_configured_line`
   • on success: insert row client-side, set header link, toast "Added A1 · ILL-…", then
     [Add another] (back to Step 2 with fixture type auto-incremented, same project/schedule)  |  [Done]
```

---

## 3. Backend implementation

### 3.1 New module `illumenate_lighting/illumenate_lighting/api/desk_configurator.py`

All functions `@frappe.whitelist()`; import helpers from `configured_product_builder`, `quote_order_configurator`, `webflow_schedule`, `tape_neon_configurator`, `ill_project_fixture_schedule`.

```python
PARENT_DOCTYPES = {"Quotation", "Sales Order"}
EDITABLE_SCHEDULE_STATUSES = ("DRAFT", "READY")

@frappe.whitelist()
def get_desk_context(parent_doctype: str, customer: str | None = None,
                     linked_schedule: str | None = None) -> dict:
    """Bootstrap payload for Step 1/2.
    Returns {
      success, customer,
      linked_schedule: {name, schedule_name, status, is_locked, ill_project, project_name} | None,
      projects: [{value, label, customer}],            # active projects for customer (all if internal & no customer)
      product_types: [{value,label}],                  # Linear Fixture, LED Tape, LED Neon
      can_create_project: bool, can_create_schedule: bool
    }"""

@frappe.whitelist()
def get_schedule_picker_data(schedule: str) -> dict:
    """{success, status, is_locked, can_write, lines:[{idx, name, line_id, location, qty, notes,
        manufacturer_type, product_type, configuration_status, configured_fixture,
        configured_tape_neon, summary}], locations:[...distinct], next_fixture_type}"""

@frappe.whitelist()
def ensure_project_and_schedule(customer: str, project: str | None = None,
                                project_name: str | None = None,
                                schedule: str | None = None,
                                schedule_name: str | None = None) -> dict:
    """Create-or-get. Rules:
       - customer required; project.customer must equal customer (else error)
       - new project: project_name reqd, status ACTIVE, is_active 1, customer set   (fixes the bug in
         webflow_schedule.create_quick_project_and_schedule — set customer!)
       - new schedule: schedule_name default "Main Schedule", status DRAFT, ill_project set
       - permission: frappe.has_permission("ilL-Project","create") / has_permission(project,"write")
       Returns {success, project, project_name, schedule, schedule_name, status, created_project, created_schedule}"""

@frappe.whitelist()
def build_configured_line(
    parent_doctype: str,
    product_type: str,                     # "Linear Fixture" | "LED Tape" | "LED Neon"
    selections_json: str | dict,           # portal-shaped selections from the scoped class
    header_json: str | dict,               # subset of frm.doc (see 3.1.3)
    qty: float = 1,
    fixture_type: str | None = None,       # → schedule line_id + row.ill_fixture_type
    location: str | None = None,           # → schedule line.location + row.ill_section_label
    notes: str | None = None,              # → line.notes + row.additional_notes
    schedule: str | None = None,           # None → skip schedule write
    line_idx: int | None = None,           # existing line to overwrite (0-based), None → append
    product_slug: str | None = None,       # fixture: template code / webflow slug
    segments_json: str | list | None = None,  # neon
    tape_neon_template: str | None = None, # tape/neon
    parent_name: str | None = None,        # only if the doc is saved (used for pricing-rule context)
    variant_origin: str | None = None,     # default from parent_doctype ("Quotation Tool"/"Sales Order Tool")
) -> dict:
```

#### 3.1.1 `build_configured_line` algorithm

1. `product_type = _normalize_product_type(product_type)`; `qty = flt(qty) or 1`; validate `parent_doctype in PARENT_DOCTYPES`; `frappe.has_permission(parent_doctype, "write")` (and on `parent_name` if given).
2. **Schedule preflight** (if `schedule`): load doc, `has_permission(schedule,"write")`, `not is_locked`, `status in EDITABLE_SCHEDULE_STATUSES`, validate `line_idx` bounds, `fixture_type = fixture_type or _get_next_fixture_type_id(schedule)`. Fail early → `{success: False, error}` **before** any engine write.
3. **Persist configured record** via existing code:
   * fixture → `payload = _fixture_payload_from_portal_selections(product_slug, selections, qty)`; keep `override_max_run_ft`, `start/end_feed_direction`, leader lengths if present (extend `_fixture_payload_from_portal_selections` to pass `start_feed_direction_code`, `end_feed_direction_code`, `start_leader_len_mm`, `end_leader_len_mm`, `dimming_protocol_code`, `override_max_run_ft` when the engine accepts them — mirror `webflow_schedule.add_to_schedule`).
   * tape/neon → payload as in `save_and_apply_from_portal`.
   * `validation = _dispatch_save(product_type, payload, parent_configured_*=None, tape_neon_template=..., variant_origin=...)`; if `not validation["is_valid"]` return error via `_error_text_from_messages`.
4. **Artifacts**: `artifact = _ensure_fixture_artifacts(name)` or `_ensure_tape_neon_artifacts(name, product_type)`. Then **ensure MSRP Item Price** (the builder path currently relies on the schedule flow for this): reuse `ilLProjectFixtureSchedule._check_and_update_item_pricing` logic — extract it into a module-level helper in `manufacturing_generator` (e.g. `ensure_configured_item_price(item_code, configured_doc, product_type)`) and call it from both places. Attach `msrp_unit` from `validation["pricing"]` to `artifact` so the fallback path in `_apply_pricing_to_row` has a value.
5. **Schedule line write** (if `schedule`), wrapped in `frappe.db.savepoint("ill_desk_cfg_line")`:
   * `line = schedule.lines[line_idx]` or `schedule.append("lines", {})`.
   * common: `manufacturer_type="ILLUMENATE"`, `line_id=fixture_type`, `location`, `qty=cint(qty)`, `notes` (fixture: user notes; tape/neon: user notes if given else `build_description`), `configuration_status="Configured"`, `ill_item_code=artifact["item_code"]`, `manufacturable_length_mm=artifact["mfg_length_mm"]`.
   * fixture: `product_type="Linear Fixture"`, `fixture_template=artifact["template_code"]`, `configured_fixture=name`, clear `configured_tape_neon`/`variant_selections`.
   * tape/neon: `product_type`, `tape_neon_template`, `configured_tape_neon=name`, and **`variant_selections = json.dumps({product_category, part_number, build_description, computed, resolved_items, selections})`** — factor the body of `save_tape_to_schedule` into `tape_neon_configurator._write_tape_neon_line(line, result, template_code)` and call it from both `save_tape_to_schedule`, `save_tape_neon_template_to_schedule` and here.
   * `schedule.save()` (runs validate → customer sync). Capture `line.name`, `line.idx`.
6. **Row values**: build an in-memory parent to reuse the existing writer & pricing:
   ```python
   tmp = frappe.new_doc(parent_doctype); tmp.update(_safe_header(header_json)); tmp.name = parent_name or None
   row = tmp.append("items", {})
   _apply_artifact_to_row(tmp, row, artifact, qty, _serialize_json(artifact["configuration_snapshot"]))
   _set_child_value(row, "ill_section_label", location)
   _set_child_value(row, "ill_fixture_type", fixture_type)
   _set_child_value(row, "ill_schedule_line_id", line_name)
   _set_child_value(row, "additional_notes", notes)
   row_values = {k: v for k, v in row.as_dict().items()
                 if k not in EXCLUDED and frappe.get_meta(f"{parent_doctype} Item").has_field(k) and v is not None}
   ```
   `EXCLUDED = {"name","idx","parent","parentfield","parenttype","doctype","docstatus","owner","creation","modified","modified_by","__islocal","__unsaved"}`.
   `_safe_header` whitelists: `customer, party_name, quotation_to, company, currency, price_list_currency, selling_price_list, conversion_rate, plc_conversion_rate, transaction_date, delivery_date, customer_group, territory, ignore_pricing_rule`.
7. Return:
   ```json
   {"success": true, "row_values": {...}, "header_values": {"ill_fixture_schedule": "<schedule or null>"},
    "schedule": "...", "schedule_line_name": "...", "schedule_line_idx": 3, "fixture_type": "A1",
    "product_type": "...", "configured_fixture": "...", "configured_tape_neon": null,
    "item_code": "...", "bom": "...", "next_fixture_type": "A2", "messages": [...]}
   ```
8. Error handling: any exception after step 3 → `frappe.db.rollback(save_point=...)` for the schedule write only (configured record/Item/BOM are idempotent by config hash and safe to keep), `frappe.log_error`, return `{success: False, error}`.

#### 3.1.2 Also add

```python
@frappe.whitelist()
def get_next_fixture_type(schedule: str | None, used_json: str | list | None = None) -> str
    # union of schedule line_ids and ids already used on the form (frm.doc.items[].ill_fixture_type)

@frappe.whitelist()
def create_schedule_version(schedule: str) -> dict   # thin wrapper over doc.create_new_version() for the "locked/QUOTED" case
```

#### 3.1.3 Fix `quote_order_configurator._apply_artifact_to_row`

Add optional kwargs `section_label=None, fixture_type=None, schedule_line_id=None, additional_notes=None` and stamp them with `_set_child_value`. Update `save_and_apply` / `apply_existing_configured_product` signatures to accept and forward `fixture_type`, `location`, `notes`, `schedule_line_id` (keeps the server-side path at parity).

#### 3.1.4 Fix `webflow_schedule.create_quick_project_and_schedule`

Add `customer: str | None = None`; resolve `customer or _get_user_customer(user)`; error if still empty (ilL-Project.customer is `reqd`).

#### 3.1.5 Optional lifecycle hook (decision — see §7)

`hooks.py doc_events["Quotation"]["on_submit"]` → `ill_project_fixture_schedule.on_quotation_submit(doc)`: if `doc.ill_fixture_schedule` and schedule status in (DRAFT, READY) → `transition_schedule_status(schedule, "QUOTED")`. Mirror `on_sales_order_*` style and add `on_cancel` that leaves status untouched (log a comment only).

### 3.2 Tests — `illumenate_lighting/illumenate_lighting/api/test_desk_configurator.py`

`FrappeTestCase`; reuse fixture helpers from `test_quote_order_configurator.py` / `doctype/ill_project_fixture_schedule/test_ill_project_fixture_schedule.py` (they build a template, tape offering, configured fixture with `profile_item`).

* `test_ensure_project_and_schedule_creates_with_customer` — project has customer, schedule DRAFT, idempotent on second call.
* `test_ensure_project_rejects_customer_mismatch`.
* `test_build_configured_line_fixture_writes_schedule_and_row` — line has `line_id`, `location`, `qty`, `configured_fixture`, `ill_item_code`; `row_values` has `item_code`, `rate>0`, `ill_section_label==location`, `ill_fixture_type==line_id`, `ill_schedule_line_id==line.name`, `ill_configured_fixture`, `ill_bom`; `header_values.ill_fixture_schedule==schedule`.
* `test_build_configured_line_tape_sets_variant_selections` — then `schedule.status="READY"; schedule.save()` does not raise.
* `test_build_configured_line_overwrites_existing_pending_line` (`line_idx`).
* `test_build_configured_line_without_schedule` — no schedule write, row still stamped from args.
* `test_build_configured_line_refuses_locked_or_quoted_schedule` — no engine write happened (count ilL-Configured-Fixture before/after).
* `test_next_fixture_type_considers_form_ids`.
* `test_row_values_only_contain_child_meta_fields` and are `frm.add_child`-safe (no `name`/`parent`).
* Regression: `test_apply_artifact_to_row_stamps_grouping_fields`.

Run: `bench --site <site> run-tests --app illumenate_lighting --module illumenate_lighting.illumenate_lighting.api.test_desk_configurator`.

---

## 4. Frontend implementation

### 4.1 `illumenate_lighting/public/js/desk/desk_dialog.js` (rewrite the controller; keep public API)

Keep `IllDesk.addConfiguratorButton(frm)` / `IllDesk.openConfiguratorDialog(frm, opts)` so the shim and form scripts keep working.

**Button placement**

```js
IllDesk.addConfiguratorButton = function (frm) {
  if (!canConfigure(frm)) return;                       // docstatus 0 && !read_only (ALLOW is_new)
  // Toolbar: standalone (not buried in Tools) — appears with the other action buttons
  frm.add_custom_button(__('Configure & Add Fixture'), () => IllDesk.openConfiguratorDialog(frm))
     .addClass('btn-primary');
  // Items grid: button right next to "Add Row" so it is where users build lines
  const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
  if (grid && !grid.__ill_cfg_btn) {
    grid.add_custom_button(__('Configure & Add Fixture'), () => IllDesk.openConfiguratorDialog(frm));
    grid.__ill_cfg_btn = true;
  }
};
```
> Frappe cannot place custom buttons in the page's top-left title area without DOM hacks; the grid button (bottom-left of the Items table) plus a standalone toolbar button is the supported equivalent. Remove the old `Tools` group entry.

**Prerequisite check** before opening: if no customer (`frm.doc.customer` or `quotation_to==='Customer' && party_name`) → `frappe.msgprint` "Set the Customer first" and focus the field.

**State** kept on the controller for the whole session: `customer, project, schedule, scheduleStatus, skipSchedule, productType, lineIdx, fixtureType, location, qty, notes, rowName(selected existing row), lastNextFixtureType`.

**Step 1 – Project & Schedule** (use real Frappe controls via `frappe.ui.form.make_control` inside the HTML body, or define them as dialog `fields` and show/hide by step):
* `project` Link (`options: 'ilL-Project'`, `get_query → {filters:{customer, is_active:1}}`), `new_project` Check + `new_project_name` Data (default `frm.doc.title || customer_name`).
* `schedule` Link (`options: 'ilL-Project-Fixture-Schedule'`, `get_query → {filters:{ill_project}}`), `new_schedule` Check + `new_schedule_name` Data (default "Main Schedule").
* `skip_schedule` Check.
* If `frm.doc.ill_fixture_schedule` → call `get_desk_context(..., linked_schedule)` and render read-only summary; disable pickers.
* On `Continue`: call `ensure_project_and_schedule` (unless skip) → store ids/status; if status not editable → show "Create new version" inline action (`create_schedule_version`) and re-check.

**Step 2 – Line details**: product-type pills (existing), `line_select` (Select, from `get_schedule_picker_data(schedule).lines` filtered to `configuration_status != 'Configured' || manufacturer_type==='OTHER'`, label `A1 — Lobby (Pending)`), `fixture_type` Data (default `next_fixture_type`), `location` Data with `<datalist>` suggestions (schedule `locations` ∪ `frm.doc.items.map(r=>r.ill_section_label)`), `qty` Int, `notes` Small Text. Selecting an existing line prefills the four fields and stores `lineIdx`. Validation: `fixture_type` required; `location` required when not skipping schedule; duplicate fixture type on the form → confirm.

**Step 3 – Configure**: unchanged mounting (`get_configurator_markup` + `IllConfigurator.Fixture` / `IllConfigurator.TapeNeon` with `saveHandler`). Pass `context.qty` so classes could show it (optional).

**saveHandler → `build_configured_line`** with `header_json: pickHeader(frm.doc)`, `parent_name: frm.is_new() ? null : frm.doc.name`. On success:

```js
applyRowToForm(frm, msg) {
  let row;
  if (this.rowName) { row = locals[frm.doc.doctype + ' Item'][this.rowName]; Object.assign(row, msg.row_values); }
  else { row = frm.add_child('items', msg.row_values); }
  if (msg.header_values.ill_fixture_schedule && !frm.doc.ill_fixture_schedule)
      frm.set_value('ill_fixture_schedule', msg.header_values.ill_fixture_schedule);
  frm.refresh_field('items');
  if (frm.cscript && frm.cscript.calculate_taxes_and_totals) frm.cscript.calculate_taxes_and_totals();
  frm.dirty();
  frappe.show_alert({message: __('Added {0} · {1}', [msg.fixture_type, msg.item_code]), indicator: 'green'});
}
```
Then show a small footer with **Add another** (→ Step 2, `fixtureType = msg.next_fixture_type`, keep location, reset configurator via `renderConfigure()`) and **Done** (hide dialog). Never auto-save the parent; show a sticky hint "Remember to save the {Quotation}" if `frm.is_dirty()` on close.

**Robustness details**
* Guard double-submit (`this.saving`), disable configurator Add button while saving.
* If the dialog is closed mid-way after schedule lines were written, nothing is lost (schedule is saved server-side). Show that in the toast text: "Saved to schedule <name>".
* `escapeHtml` everything user-provided; never inject `row_values` into HTML.
* Handle `r.exc` / network errors with `frappe.msgprint` and re-enable buttons.
* If `frm.doc.ill_fixture_schedule` is set and the user tries to pick another → block with the same message as `_add_schedule_to_transaction`.

### 4.2 `quotation.js` / `sales_order.js`

* Keep calling `configurator.add_buttons(frm)` in `refresh`. Remove the `is_read_only` gating differences so both behave the same.
* Add a child-table trigger: when a row with `ill_schedule_line_id` is removed (`items_remove`), show a non-blocking alert "Schedule line <fixture type> still exists on the fixture schedule" (no auto-delete).
* Optional: `Reconfigure` row action (grid row button) that opens the dialog with `rowName` and the row's `ill_schedule_line_id` → `line_idx` (server: resolve idx by child name). Nice-to-have.

### 4.3 CSS — `public/css/configurator/desk_configurator.css`

Add rules for `.ill-desk-stepper`, `.ill-desk-type-pill`, the line-details grid, and the "Add another / Done" footer. Keep everything scoped under `.ill-desk-configurator` / `.modal-dialog .ill-configurator` to avoid leaking into desk.

### 4.4 Asset loading

Keep `app_include_js` as is (simplest). Optional optimisation: replace the four global includes with a `frappe.require([...])` bundle inside `quote_order_configurator.js` so non-sales desk pages don't pay for the configurator; if you do this, `IllDesk` must be awaited before `add_buttons`.

---

## 5. Step-by-step task list (implement in order)

1. **Backend fixes (small, independent)**
   1. `_apply_artifact_to_row`: add grouping kwargs (§3.1.3). Update callers.
   2. `webflow_schedule.create_quick_project_and_schedule`: add `customer` (§3.1.4).
   3. Extract `tape_neon_configurator._write_tape_neon_line(line, result, template_code)`; refactor `save_tape_to_schedule` and `save_tape_neon_template_to_schedule` to use it.
   4. Extract `manufacturing_generator.ensure_configured_item_price(...)` from `ilLProjectFixtureSchedule._check_and_update_item_pricing` / `_check_and_update_tape_neon_item_pricing`; keep the methods as thin wrappers.
   5. Extend `configured_product_builder._fixture_payload_from_portal_selections` to forward feed directions / leader lengths / `override_max_run_ft` / `dimming_protocol_code` (mirror `webflow_schedule.add_to_schedule`).
2. **New `api/desk_configurator.py`** (§3.1) + tests (§3.2).
3. **Rewrite `desk_dialog.js`** (§4.1) + CSS (§4.3). Keep `IllDesk` API names.
4. **Form scripts** (§4.2).
5. **Optional Quotation submit hook** (§3.1.5) — only after decision in §7.
6. **Docs/QA**: append a "Desk configurator" section to `docs/QA_CHECKLIST.md` (§8). Update `docs/DEMO_SCRIPT.md` if it references `/portal/configure` for quoting.
7. **Cleanup**: remove or fix `qoc_get_product_types` dead references; delete `patches/add_quote_order_configurator_fields.py` duplication only if `patches.txt` no longer references it (check first — do not break migrate history).

**Static verification before hand-back**: `python -m compileall -q illumenate_lighting`, `node --check illumenate_lighting/public/js/desk/desk_dialog.js`, `ruff check .`, Pylance clean on touched files, JSON fixtures still valid.

---

## 6. Phase 2 — product coverage parity with `/portal/configure` (after §5 ships)

| Product | Today in desk | Path to parity |
|---|---|---|
| Linear Fixture **multi-segment** | ✗ (wizard is single-segment) | Add a "Segments" panel to `fixture_steps.js` producing `segments_json` (shape used by `configurator_engine.validate_and_quote_multisegment` — see the inline `configure.html` coordinator code around lines 2200-2260 for the exact segment fields), and route `_dispatch_save` via the `segments_json` branch that already exists. |
| LED Tape **jumper-chained runs / bulk reel** | ✗ | `validate_tape_configuration` already accepts `segments_json`; add the run-builder UI to `tape_neon_steps.js`. Bulk reel needs the `bulk_reel_*` endpoints used in `configure.html` (~line 3000-3500). |
| LED Sheet | ✗ (`get_configurator_markup` refuses) | Port `public/js/configure_sheet.js` (DOM-id based) to a scoped `IllConfigurator.LedSheet` class + `templates/includes/configurator_led_sheet_form.html`; server: `led_sheet_configurator.validate_sheet_configuration` / `save_sheet_configuration`; artifacts via `quote_order_configurator._ensure_configured_artifacts(PRODUCT_TYPE_SHEET, ...)` (already exists). |
| Extrusion Kit | ✗ | Reuse the existing Frappe dialog `ill_open_kit_configurator` in `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.js` and `extrusion_kit_configurator.create_kit_so_lines` (multi-row explode) — the row insertion helper must accept a list of rows. |
| Accessories / power supplies as separate rows | partially (BOM only) | Offer "Add accessory row" using `line.manufacturer_type='ACCESSORY'` + `append_quote_lines` semantics. |
| "Use existing configured product" | server exists (`apply_existing_configured_product`) | Add a 4th product-type pill "Existing part #" with a Link to ilL-Configured-Fixture / ilL-Configured-Tape-Neon; still writes schedule line + grouping fields. |

---

## 7. Decisions to confirm with the user before/while implementing

1. **Button location** — toolbar (standalone, primary) + Items-grid button, instead of literal top-left (not supported by Frappe). OK?
    - Yes, ok.
2. **Skip-schedule allowed?** Proposed: yes, with warning. Alternative: mandatory schedule.
    - Yes, with warning.
3. **Auto QUOTED on Quotation submit** (§3.1.5)? Proposed: yes for DRAFT/READY schedules.
    - Yes
4. **Schedule in QUOTED/locked state** — proposed: refuse and offer "Create new version" (auto-version semantics already exist in `transition_schedule_status`).
    - Yes create new version.
5. **Deleting a configured row** — proposed: never delete the schedule line automatically; just warn.
     - Yes
6. **Dealer access in desk** — dealers have SO create in `dealer_permissions.py`; the endpoints rely on doc-level `has_permission`, so dealers could use it on their own SOs. Confirm that's desired.
    - No dealer access in desk!

---

## 8. QA checklist (append to `docs/QA_CHECKLIST.md`)

- [ ] New Quotation (unsaved, customer set) → button visible → full flow → row appears, totals update, `ill_fixture_schedule` set, save succeeds.
- [ ] Same on an existing draft Sales Order; `bom_no` set on the row; `delivery_date` populated.
- [ ] Project + schedule created from the dialog have `customer` = document customer; schedule DRAFT.
- [ ] Schedule line shows in `/portal/schedules/<name>` with Fixture Type, Location, qty, configured part number, stock badge.
- [ ] Row fields: `ill_section_label`, `ill_fixture_type`, `ill_schedule_line_id`, `ill_configured_*`, `rate` (MSRP × pricing rule), `additional_notes`.
- [ ] Print format groups the new row under the Section / Room and shows the Fixture Type row.
- [ ] "Add another" increments Fixture Type (`A1 → A2`), keeps project/schedule, resets configurator.
- [ ] Picking an existing *Pending* portal-created line configures it in place (no duplicate line).
- [ ] Linked-schedule lock: cannot pick a different schedule once `ill_fixture_schedule` is set.
- [ ] Locked / QUOTED schedule → clear message + "Create new version" works.
- [ ] LED Tape and LED Neon lines are accepted by `status = READY` (variant_selections written).
- [ ] `Get Items From ▸ Fixture Schedule` on the same document does not duplicate rows already stamped with the same `ill_schedule_line_id` (verify current behaviour; add a skip if needed).
- [ ] Quotation → Sales Order (`make_sales_order`) carries `ill_fixture_schedule`, `ill_section_label`, `ill_fixture_type`, `ill_schedule_line_id`.
- [ ] Permission denial (user without schedule write) returns a readable error, no partial schedule write.
- [ ] Console has no JS errors; dialog teardown removes configurator instances (`IllConfigurator` registry).
