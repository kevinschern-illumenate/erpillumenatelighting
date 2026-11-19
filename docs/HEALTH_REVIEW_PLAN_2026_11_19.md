# Health review and hardening plan — dealer portal, Desk Configure & Add, configurators

Reviewed: `main` at `3f9fad1` (2026-11-19). Production (`illumenatelighting.v.frappe.cloud`, Frappe 16.60.2 / ERPNext 16.60.0) has every patch through `add_supplier_part_line_fields`, so it is effectively running `main`.

## Verdict

Things are mostly healthy. The recent commits did not break the dealer portal, the configurator engines or the schedule → quote → order flow.

- **Recent regressions:** two Desk dialog bugs (from 3432d38) and one failed data patch (from 4240833).
- **Older breaks:** a handful of portal bugs that the review surfaced.
- **One urgent site setting:** a guest-open Server Script (P0).
- **Error Log:** most production errors are noise or come from outside API clients, not from the app.

How the review was done:

- **Local suites, all passing:**
  - `tests/portal_unit`: 2171 tests
  - `tools/fixture_builder/tests`: 134 tests
  - `tests/portal_ui`: 357 tests
  - `tools/check_portal_templates.py`: 57 templates
  - The changed-file lint gate.
- **Code review** of every portal, Desk dialog, configurator, hooks and patches commit from 2026-11-03 to 2026-11-19.
- **Read-only checks against production:** Error Log, Patch Log, Custom Fields, page renders, Email Queue and Scheduled Job Log.

## Rules for whoever implements this

- Work on a feature branch and open one PR per numbered group below. Don't bundle them, so each can be reverted on its own.
- **Production is read-only for you.** If you have API access, use GET requests only. Never call write methods, and never run patches or `bench execute` against production. Anything that needs a write on production is marked **OWNER ACTION**; leave it for the owner.
- Run these before every PR (they need no bench):
  ```bash
  python3 -B -m unittest discover -s tests/portal_unit
  ```
  ```bash
  python3 -B -m unittest discover -s tools/fixture_builder/tests
  ```
  ```bash
  python3 -B tools/check_portal_templates.py
  ```
  ```bash
  node --test tests/portal_ui/*.test.cjs
  ```
  ```bash
  B2B_BASE_REF=origin/main python3 -B tools/check_b2b_changes.py
  ```
  (`npm ci --prefix tests/portal_ui` first. Python deps: `ruff PyYAML Jinja2 Pillow pillow-heif pypdf reportlab pypdfium2 jsonschema`.)
- Leave out-of-scope behaviour alone. Every item says what it must **not** change.

---

## P0 — OWNER ACTION, today (site setting, no code)

### 0. Disable the guest-accessible `perm_debug` Server Script

- **Evidence:** On production, Server Script `perm_debug` (API, `api_method=perm_debug`) has `allow_guest=1` and `disabled=0` (last modified 2026-09-28).
- **What it exposes:** Given `?user=<email>`, it returns that user's roles, User Permissions, File create permission and the File Custom DocPerms. Anyone on the internet can call it without logging in.
- **Fix:** Desk → Server Script → `perm_debug` → tick **Disabled** (or delete it). It is not in the repo, so there is no code change.

---

## P1 — Fix what is broken (small, targeted)

### 1. Line-power backfill wrote nothing (regression from 4240833)

- **Evidence:** Patch `backfill_line_power` ran on 2026-11-18 at 19:33. It logged **906** Error Log rows titled "Line power backfill: …" (322 rows on 113 Sales Orders, 584 rows on 104 Quotations), each raising `IntegrityError 1048 Column 'ill_lp_watts_per_ft' / 'ill_lp_watts_per_sqft' cannot be null`. The per-row try/except hid the failures, so Patch Log still shows the patch as done.
  - Example: SAL-ORD-2026-00080 has all 35 rows without spec/load stamps.
  - As a result, submitted documents print without the new spec/load line.
- **Cause:**
  - `line_power_math.compute_row()` returns `None` for fields that don't apply to a line type: sheet fields on tape rows, per-foot fields on sheet rows, everything except the note on no-spec rows.
  - Frappe v16 creates Float, Int, Currency, Percent and Check columns as `NOT NULL`.
  - `frappe.db.set_value` (in `illumenate_lighting/illumenate_lighting/api/line_power.py`, `backfill()`, ~L310–319) writes `None` straight to SQL.
- **Normal saves are not affected:** `stamp_line_power` runs on validate and goes through `doc.save`, which turns `None` into 0. Confirm this with the smoke test in item 10.
- **Change** in `backfill()`: when building `values`, use 0 instead of `None` for numeric fieldtypes, read from `meta.get_field(field).fieldtype in ("Check","Int","Currency","Float","Percent")`. Leave everything else as it is. This matches what a normal save stores.
- **Also (low risk):**
  - Count failures. Return `{"stamped": n, "failed": m}` per child doctype and have `patches/backfill_line_power.py` print it, so a 100% failure is visible during migrate.
  - Write one summary Error Log at the end listing the failed parents (cap the list at about 50) instead of one log per row.
- **Re-run:** add a new line `illumenate_lighting.patches.backfill_line_power #2026-11-19 rerun after None fix` to `patches.txt`. This repo already re-runs patches this way, with a comment suffix. The patch must stay idempotent; it already overwrites with computed values.
- **Tests** in `tests/portal_unit/test_line_power.py`, using the existing stubs. Stub `frappe.get_meta` with the Float fields from `patches/add_line_power_fields._row_fields` and capture `frappe.db.set_value`. Assert that:
  - a tape row, a sheet row and a no-spec LED row are all written;
  - no numeric field value is `None`;
  - `log_error` is not called.
  Add a second test where `set_value` raises: the failure is counted, and only one summary log is written.
- **Must not change:** `stamp_line_power`, `line_power_math` outputs, the print templates.
- **OWNER ACTION after deploy:** confirm SAL-ORD-2026-00080 rows now have `ill_lp_summary`, then clear the 906 "Line power backfill:" Error Log rows.

### 2. Desk "Configure & Add Fixture" (Quotation / Sales Order): reconfigure with a blank Fixture Type (regression from 3432d38)

The dialog is wired through `hooks.py` `app_include_js` → `illumenate_desk.bundle.js` and the buttons in `public/js/quotation.js` and `public/js/sales_order.js`. The code is in `illumenate_lighting/public/js/desk/dialog/{state,family_steps,pricing,save}.js` and `illumenate_lighting/illumenate_lighting/api/desk_configurator.py`. No production data is affected yet, because no Quotation or Sales Order rows have been written since the deploy. A reviewer reproduced both bugs with a jsdom probe that loads the real dialog files.

**2a. Clearing Fixture Type (or Section, or notes) on "Reconfigure Row" does nothing for document-only rows.**

- **What happens:**
  - The server leaves blank values out of `row_values` (`desk_configurator.py` ~L1409; `_apply_artifact_to_row` skips a `None` fixture type).
  - `pricing.js` ~L90 copies only the keys that are present, so the main row keeps "L3" while its new power-supply rows get no type.
  - After that, `state.js:244` `sameType` can't link the supplies to their owner, and the next reconfigure leaves duplicate supply rows.
- **Change** in `pricing.js`, just before `Object.keys(values).forEach(...)`: for the dialog-owned fields `ill_fixture_type`, `ill_section_label` and `additional_notes`, set `row[k] = null` when `k` is not in `values`. This uses the same pattern as the `BUILD_FIELDS` line right above it.
- **Test:** `tests/portal_ui/desk_reconfigure.test.cjs` (or a similar existing desk dialog test). Clearing the type on reconfigure clears it on the main row and its new supply row, and leaves no duplicate supply rows.

**2b. Type comparisons treat `''`, `null` and `undefined` as different values.**

- Production already mixes them: kit components have `''` and supplies have `None`.
- **Change:** compare with `(a || '') === (b || '')`:
  - in `state.js:244` (`sameType`);
  - in the `r.ill_fixture_type !== previousType` check in `pricing.js` (~L77).
- **Test:** a supply row with a `null` type still finds an owner row with `''`.

**2c. Two identical document-only builds with no Fixture Type: reconfiguring one deletes the other.**

- **What happens:** the stale-row filter in `pricing.js` ~L77–81 falls back to matching on `ill_configurator_request` (or `ill_configured_led_sheet`), which identical builds share. Before 3432d38, the Fixture Type kept them apart.
- **Change:**
  - In `illumenate_lighting/illumenate_lighting/portal/desk_build_receipt.py` (~L77), stamp the build's `ill_configuration_save_key` on every `accessory_rows` entry as well as on the main row.
  - In `pricing.js`, for document-only rows (`!r.ill_schedule_line_id`), match stale rows by the reopened row's save key when it has one. Keep the request/sheet match only as the fallback for legacy rows with no save key.
- **Risk:** low to medium (it touches stale-row selection), so give it its own PR.
- **Test:** add the same extrusion kit twice with a blank type, reconfigure one, and check the other's rows are untouched. Also check the existing reconfigure tests still pass.

**2d. The server fallback for the next fixture type ignores ids already on the form.**

- **Where:** `desk_configurator.py` L619 and L863 call `_next_fixture_type(schedule_doc, [])`.
- **Change:** accept an optional `used_json` on those two endpoints and pass `_coerce_list(used_json)` through. The client already sends `used` to `get_next_fixture_type`; send it here too. This only adds an optional argument.
- **Test:** the fallback skips ids already used on the form (extend `api/test_desk_configurator.py` or the matching `tests/portal_unit` test).

**Must not change:** the schedule-linked reconfigure path (`ill_schedule_line_id` matches), `schedule_sync.py`, pricing.

### 3. The "Link Helpdesk Tickets" dialog on Project and Fixture Schedule is broken (from 79bdf68)

- **Evidence:** In `illumenate_lighting/public/js/helpdesk_tickets.js:28`, `get_query` returns `{ filters: [["HD Ticket", fieldname, "!=", frm.doc.name]] }`. `MultiSelectDialog` reads that as a dict and builds `HD Ticket.0`. Live error on 2026-11-18.
- **Change:** `return { filters: { [fieldname]: ["!=", frm.doc.name] } };`
- **Test:** a node test that loads the script with a fake `MultiSelectDialog` and checks that `get_query().filters` is a plain object keyed by the field name.

### 4. `/portal/configure-sheet` and `/configure-sheet` return 404

- **Evidence:** `templates/pages/configure_sheet.py` exists but `configure_sheet.html` does not, so the redirect code never runs. `configure-tape` correctly returns 301.
- **Change:** add a minimal `templates/pages/configure_sheet.html` that copies the `configure_tape.html` redirect page.
- **Test:** add to `tools/check_portal_templates.py` or `tests/portal_unit`: every `to_route` in `hooks.py` `website_route_rules` has a matching `templates/pages/<route>.html` or `www/` page.

### 5. Orders whose names contain spaces or "/" break portal links

- **Evidence:**
  - Customer "Backcountry Electric / LINX Audio Visual" has 4 orders named like `ilL-SAL-ORD-Backcountry Electric / LINX Audio Visual-00001`. `/portal/orders/<name>` returns 404 for these, with or without `%2F`, because the route `"/portal/orders/<order>"` (`hooks.py` ~L163) never matches "/".
  - 168 Sales Order names contain spaces.
  - Branded emails (fd53202) build `get_url(f"/portal/orders/{name}")` without encoding. The locations are:
    - `portal/notifications.py` L115, L165, L215
    - `portal/order_changes.py:270`
    - `email_templates/context.py` L714, L900
    - plus `conversations.py`, `offers.py` and `verification.py` if they build order links.
- **Change A (low risk):** build these URLs with `urllib.parse.quote(name, safe="")`, preferably through one helper. `portal/routes.py` already has a route table (`"order": "/portal/orders/{name}"`), and `notification_center.link` already encodes correctly; reuse that. This fixes spaces.
- **Change B ("/" names, verify on staging first):** change the rule to `/portal/orders/<path:order>`. It is the only nested rule under `/portal/orders/`. Check that `order_detail.py` reads the full name and that the existing permission check still applies.
- **Tests:** an email built for an order name with spaces contains `%20` and no raw space. A route test covers a "/" name.

### 6. Dealer double-submits on schedule line actions show a raw "has been modified" error

- **Evidence:** dealer `joshp@cascadeintegration.com` hit 7 `TimestampMismatchError`s on ILL-SCHED-2026-00155 on 2026-11-16: 5 delete, 1 duplicate, 1 update. Each competing write landed 0.25–52 ms earlier, which means two identical POSTs (a double-click on the confirm button). No data was duplicated, but the dealer saw Frappe's raw text, and each one was logged.
- **Changes:**
  - In `public/js/portal/schedule/lines.js`, the delete, duplicate and edit-save handlers (~L1266–1420) ignore a second click while a request is in flight, and clear the flag on success or error. Also pass `freeze: true` where the call goes through `frappe.call`.
  - In `illumenate_lighting/illumenate_lighting/api/portal.py` `_safe_error` (L30), map `frappe.TimestampMismatchError` to the same response as a stale schedule: `STALE_MESSAGE`, `error_code: "stale"`, plus the `conflict` details when the schedule is known, so `ScheduleConflict.handle` offers a reload. Don't write an Error Log entry for this case or for `StaleScheduleError`.
- **Tests:**
  - A node test where two clicks send one request.
  - A unit test in `tests/portal_unit/test_portal_errors.py` where a `TimestampMismatchError` returns `error_code == "stale"` and `log_error` is not called.
- **Must not change:** the success paths or the `expected_modified` check itself.

### 7. Deleting a draft schedule that has configuration receipts fails with a raw LinkExistsError

- **Evidence:** `delete_schedule` (`api/portal.py` L2312) raises because `ilL-Configuration-Receipt` links to the schedule, and receipts deliberately refuse deletion in `on_trash`. Error on 2026-11-17. Since 79bdf68, a linked HD Ticket also blocks deletion.
- **Low-risk change (do this):** catch `frappe.LinkExistsError` in `delete_schedule` and return a clear dealer message, for example: "This schedule has configuration history and can't be deleted. Archive it or ask ilLumenate to remove it." Don't write an Error Log entry for it.
- **Owner decision (do not implement without sign-off):** whether to add `"ilL-Configuration-Receipt"` to `ignore_links_on_delete` (`hooks.py:674`). That would orphan audit receipts.
- **Test:** `delete_schedule` with a stubbed `LinkExistsError` returns `success: False` with the friendly message.

---

## P2 — Low-risk hardening

### 8. Stop log spam that buries real errors

- **"Webflow retries: n8n is not configured":** 176 rows so far, one every 4 minutes, from `illumenate_lighting/illumenate_lighting/webflow_auto_push.py:267`.
  - **Change:** check the n8n config before claiming retry jobs, and log at most once per day using a `frappe.cache` key.
  - **Test:** two ticks with no config write one log.
- **"Webflow Spec Enrichment Skipped":** 616 rows, logged on every API read for about 10 kit products with no source link. Sources: `api/webflow_export.py:1190`, `1690`; `api/webflow_export_v2.py:1544`, `2044`.
  - **Change:** log once per product per day (cache key `spec-enrich-skip:<product>:<date>`).
  - **Test:** two reads write one log.
- **"Scheduler ran. Campaigns found: 0":** 5,025 rows. **OWNER ACTION:** the site Server Script "Postmark Campaign Scheduler" (not in the repo) calls `frappe.log_error` on every run. Change it to log only when campaigns > 0.

### 9. A failing Item save blocks the whole Purchase Order / RFQ save

- **Where:** `illumenate_lighting/illumenate_lighting/api/supplier_parts.py` `_save_items` (L115–127) throws "Could not update item …" if any one Item fails validation.
- **Change:** catch the error per item, add the item to `skipped` with the reason, and show one message listing the skipped items. The PO/RFQ save itself goes ahead.
- **Test:** an Item whose save raises does not stop the others or the parent save.

### 10. Run a smoke test of hooks that haven't run in production yet (OWNER ACTION, needs writes)

Since the 2026-11-18 migrate there have been no Quotation, Sales Order, schedule, configured-fixture, Delivery Note or BOM saves, and no outgoing email. So `stamp_line_power`, `roll_up_sales_order`, the branded email templates and the sender-name change haven't been exercised live. A staff member should:

1. Save a draft Quotation that has a tape line and a sheet line, and check the spec/load line appears.
2. Run Desk "Configure & Add Fixture" on a draft Sales Order: one add, one reconfigure.
3. Have a dealer test account add, edit and delete a schedule line on the portal.
4. Send one password reset to a test account and check the branded email arrives.

### 11. Small consistency fixes

- Wrap schedule IDs in `encodeURIComponent` in the JS redirects at `public/js/portal/edit_fixture/page.js:1062`, `schedule/actions.js:44`, `schedule/new.js:35` and `schedule/versions.js:81`. This brings them in line with plan 2.9; today's IDs are safe, so nothing changes in behaviour.
- `invite_project_collaborator` (`api/portal.py` ~L3152): its `except frappe.PermissionError` can no longer trigger since ce93548 wrapped accounts in `service_endpoint`, so dealers now see raw permission text. Map the `service_endpoint` failure back to "You cannot invite a collaborator to this project". Test it.

### 12. Close test-coverage gaps (tests only)

Add tests for:
- every route rule having a template (item 4);
- URL-encoding in order email links (item 5);
- the double-submit guard (item 6);
- the Helpdesk filter format (item 3);
- backfill payloads never containing `None` for numeric fields (item 1);
- `catalog_drift` cache invalidation when a configured record changes (currently up to 10 minutes stale by design; just pin the behaviour).

---

## Watch list — do not change now

- **Ship-in-pieces builds (d3a6807):** behind `fixture_fulfillment_split`, which is 0 on production, so it isn't exercised. Before turning it on, run a full-bench pass. One known gap: `fixture_fulfillment.ensure_artifacts` raises a plain `ValueError` outside its try block, which would surface as a 500 instead of a readable message.
- **Blank Fixture Type + "Skip schedule", later linked to a schedule:** `schedule_sync.py` ~L597–660 would give each row (kit components and supplies) its own L-number. This needs a design decision; it is not a quick fix.
- **Mixed numbering on older schedules:** 00150 has A1–A50 and its next line becomes L1; 00147 has "L2-1…". This is cosmetic, but tell staff.
- **Site-only code not in the repo:** the Command Center still calls the legacy `ill_command_center` Server Script.
- **External API clients** using the `purchasing@` and `sales@` keys query child tables directly (`/api/resource/Dynamic Link`, `Payment Entry Reference`, …) and guess Item codes (`LED-HD-SW-YBARRA-RESIDENCE-L2-n-RUN-n-*`). Together that's about 250 Error Log rows. Point those clients (n8n, assistants) at parent doctypes with child filters, and give them a dedicated read-only API user.
- **Data issues, not code:** spec submittal PDF templates point at absolute `app.illumenate.lighting` URLs (90 errors, last seen 2026-11-12); some stock and account validation errors come from item-group defaults.

## Verified healthy (no action)

- All 149 portal JS → Python method paths and all 216 Desk JS → server references resolve to whitelisted functions; GET-only methods are called with GET.
- `hooks.py`: all 365 dotted paths resolve, every `doctype_js` / `list_js` file exists, and there are no duplicated or clobbered keys.
- `patches.txt`: every module exists with `execute`, and every entry is in production's Patch Log.
- Production schema has every repo DocType field and every custom field from the recent patches: `ill_lp_*`, `custom_value_label`, supplier part fields, build points, HD Ticket links, Delivery Note contact fields.
- These portal pages render 200 with no traceback on production (as staff): portal, projects, project, schedule, edit fixture, configure, quotes, orders, support, resources, account, products, drawings, design, request-access and accept-invitation.
- The live `edit_fixture/page.js` is byte-identical to `main`.
- Desk dialog modules load in order (state → family_steps → pricing → save) with every needed export.
- Blank Fixture Type is handled safely by `quote_from_schedule`, exports, print formats, portal pages, emails, order review, drawing impact and build links.
- The option projection cache (6.5) is keyed by catalog revision, deep-copied, and prices are still stripped per caller. Build-points writes use `or 0` fallbacks. Per-foot adder math (ce93548) is consistent. The tier-pricing split (f8eced9) is equivalent to the old code.
- Email Queue: 0 errors since 2026-11-05. Scheduled Job Log: 0 failures out of 10,162 since 2026-11-12.

## Suggested PR order

1. Item 1 (backfill fix + re-run line). Highest value; it fixes printed documents.
2. Items 3 and 4 (one-line fixes, each with a test).
3. Items 2a, 2b and 2d together; then 2c as its own PR.
4. Items 6 and 7 (portal error handling).
5. Item 5A; then 5B after a staging check.
6. Items 8, 9, 11 and 12.
